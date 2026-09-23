"""Train the longitudinal health-anomaly detector.

    python -m ml.train_health_anomaly_model            # train, evaluate, save
    python -m ml.train_health_anomaly_model --report   # print saved metadata

Model: IsolationForest over the per-observation features in health_features.py,
inside a StandardScaler pipeline.

Why this model
--------------
The question is "does this reading look like the ones before it?", with no
labels available in the application — no vet has marked any observation as
concerning, and inventing such labels would be inventing medicine. That rules
out a classifier and leaves unsupervised detection.

IsolationForest fits because:

* It needs no assumption about how the features are distributed. Percentage
  changes and z-scores are skewed and heavy-tailed; a Gaussian method would
  flag ordinary readings in the tails.
* It isolates points by random splits, so a row that is unusual in *any
  combination* of features stands out — a small weight drop that comes with a
  temperature rise and an unusually long gap is caught, though no single
  feature crosses a threshold. That is exactly what the deterministic rules,
  which look at one signal at a time, cannot do.
* It is cheap to train, cheap to score, and its output is a continuous score
  rather than a black-box probability, which suits "worth a look" rather than
  a verdict.

Deliberately NOT chosen: a one-class SVM (slower, needs careful kernel
tuning for little gain here), LOF (no clean way to score a new point against a
stored model), and any supervised model (there are no real labels).

Parameters, and why
-------------------
n_estimators=300   more trees than the default 100; scores stop moving and
                   training still takes under a second.
max_samples=256    the library default heuristic, which keeps each tree looking
                   at a small subsample — that is what makes isolation work.
contamination      set from the generator's planted rate rather than guessed,
                   so the decision boundary matches the data it was fitted on.
                   It only sets the threshold, not the ranking.
random_state       fixed, so the artifact is reproducible.

Evaluation is on dogs never seen in training; see evaluate() and REASONING.md.
Labels exist only in the synthetic generator and are used only to measure.
Training itself never sees them.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml import health_anomaly_data as data
from ml.health_features import FEATURE_NAMES, build_rows, matrix

# One definition, owned by the inference side, so the API never imports this
# module. Re-exported here because that is where callers expect them.
from ml.health_anomaly_service import (  # noqa: E402  (after the doc block)
    MODEL_DIR, MODEL_PATH, MODEL_VERSION, REPORT_PATH,
)

RANDOM_STATE = 20260923
N_ESTIMATORS = 300
MAX_SAMPLES = 256


def rows_from(histories: list[list[dict]]) -> tuple[list[dict], np.ndarray]:
    """Feature rows for every dog, with the evaluation labels carried alongside."""
    rows = []
    for dog_index, history in enumerate(histories):
        built = build_rows(history)
        by_id = {o["id"]: o for o in history}
        for row in built:
            source = by_id[row["observation_id"]]
            row["is_planted"] = source["is_planted"]
            row["scenario"] = source["scenario"]
            row["dog_index"] = dog_index
            rows.append(row)
    return rows, matrix(rows)


def build_pipeline(contamination: float) -> Pipeline:
    return Pipeline(
        [
            # The features are on wildly different scales (% change, °C, days).
            # IsolationForest splits per feature so scaling does not change the
            # ranking much, but it keeps the stored thresholds interpretable.
            ("scale", StandardScaler()),
            (
                "forest",
                IsolationForest(
                    n_estimators=N_ESTIMATORS,
                    max_samples=MAX_SAMPLES,
                    contamination=contamination,
                    random_state=RANDOM_STATE,
                    n_jobs=1,  # deterministic; the dataset is small
                ),
            ),
        ]
    )


def evaluate(model: Pipeline, rows: list[dict], X: np.ndarray) -> dict:
    """How the model does on dogs it never trained on.

    The labels are the generator's: "we deliberately made this reading odd".
    They are NOT clinical ground truth, and nothing here should be read as
    diagnostic accuracy.
    """
    if not rows:
        return {"note": "no evaluation rows"}

    predicted = model.predict(X) == -1  # IsolationForest: -1 is an outlier
    actual = np.array([r["is_planted"] for r in rows], dtype=bool)

    tp = int(np.sum(predicted & actual))
    fp = int(np.sum(predicted & ~actual))
    fn = int(np.sum(~predicted & actual))
    tn = int(np.sum(~predicted & ~actual))

    recall = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    # Per scenario: which planted patterns are actually caught, and how often
    # a normal dog is disturbed. This matters more than the headline number —
    # a detector that catches sudden drops but misses slow decline is useful
    # to know about.
    per_scenario = {}
    for name in data.SCENARIOS:
        mask = np.array([r["scenario"] == name for r in rows], dtype=bool)
        if not mask.any():
            continue
        if data.SCENARIOS[name]:
            planted = mask & actual
            dogs = {r["dog_index"] for r, m in zip(rows, mask) if m}
            caught = {
                r["dog_index"]
                for r, flagged, is_planted in zip(rows, predicted, actual)
                if flagged and is_planted and r["scenario"] == name
            }
            per_scenario[name] = {
                "type": "anomalous",
                "planted_observations": int(planted.sum()),
                "detected": int(np.sum(predicted & planted)),
                "detection_rate": round(
                    float(np.sum(predicted & planted) / planted.sum()) if planted.sum() else 0.0, 3
                ),
                # What an admin actually sees: was this dog surfaced at all?
                "dogs": len(dogs),
                "dogs_flagged_at_least_once": len(caught),
            }
        else:
            per_scenario[name] = {
                "type": "normal",
                "observations": int(mask.sum()),
                "flagged": int(np.sum(predicted & mask)),
                "false_positive_rate": round(float(np.sum(predicted & mask) / mask.sum()), 3),
            }

    # Dog-level recall: an admin is told about a dog, not a row, so surfacing
    # any one of a dog's planted readings counts as catching that dog.
    dogs_with_anomaly = {r["dog_index"] for r, a in zip(rows, actual) if a}
    dogs_caught = {
        r["dog_index"] for r, flagged, a in zip(rows, predicted, actual) if flagged and a
    }

    return {
        "note": (
            "Measured against the synthetic generator's labels, not veterinary "
            "ground truth. These numbers say how reliably the model reproduces "
            "the patterns the generator planted."
        ),
        "evaluation_rows": len(rows),
        "confusion_matrix": {
            "true_positive": tp, "false_positive": fp,
            "false_negative": fn, "true_negative": tn,
        },
        "recall_on_planted_anomalies": round(recall, 3),
        "precision": round(precision, 3),
        "f1": round(f1, 3),
        "flagged_share": round(float(predicted.mean()), 3),
        "per_scenario": per_scenario,
        "dogs_with_planted_anomaly": len(dogs_with_anomaly),
        "dogs_flagged_at_least_once": len(dogs_caught),
        "dog_level_recall": round(
            len(dogs_caught) / len(dogs_with_anomaly) if dogs_with_anomaly else 0.0, 3
        ),
    }


def train(verbose: bool = True) -> dict:
    histories = data.generate()
    train_histories, test_histories = data.split(histories)

    train_rows, X_train = rows_from(train_histories)
    test_rows, X_test = rows_from(test_histories)

    planted_rate = float(np.mean([r["is_planted"] for r in train_rows]))
    # The fitted contamination is the planted rate, clipped to a sane band.
    contamination = float(np.clip(planted_rate, 0.02, 0.25))

    model = build_pipeline(contamination)
    # Unsupervised: only the feature matrix is passed. No labels.
    model.fit(X_train)

    metrics = evaluate(model, test_rows, X_test)
    scores = -model.decision_function(X_train)  # higher = more unusual

    metadata = {
        "model_version": MODEL_VERSION,
        "algorithm": "IsolationForest (StandardScaler pipeline)",
        "task": "unsupervised anomaly detection over longitudinal health observations",
        "not_a_diagnosis": (
            "Scores how unusual an observation is against the same dog's recent "
            "history. It does not identify, diagnose or rule out any condition."
        ),
        "dataset": {
            "source": "synthetic development data (ml/health_anomaly_data.py)",
            "why_synthetic": (
                "The application holds only a small local demo fixture of real "
                "observations, far too few to train on. No real medical data was used."
            ),
            "dogs_total": len(histories),
            "dogs_train": len(train_histories),
            "dogs_holdout": len(test_histories),
            "train_rows": len(train_rows),
            "holdout_rows": len(test_rows),
            "planted_anomaly_rate_train": round(planted_rate, 4),
            "scenarios": {k: ("anomalous" if v else "normal") for k, v in data.SCENARIOS.items()},
        },
        "features": FEATURE_NAMES,
        "parameters": {
            "n_estimators": N_ESTIMATORS,
            "max_samples": MAX_SAMPLES,
            "contamination": round(contamination, 4),
            "random_state": RANDOM_STATE,
        },
        "score_reference": {
            "note": (
                "An anomaly score is the negated IsolationForest decision function, "
                "rescaled to 0-1 for display. It is NOT a probability and NOT a "
                "likelihood of illness."
            ),
            "train_score_p50": round(float(np.percentile(scores, 50)), 4),
            "train_score_p90": round(float(np.percentile(scores, 90)), 4),
            "train_score_p99": round(float(np.percentile(scores, 99)), 4),
            "train_score_min": round(float(scores.min()), 4),
            "train_score_max": round(float(scores.max()), 4),
        },
        "evaluation": metrics,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": __import__("sklearn").__version__,
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "features": FEATURE_NAMES, "metadata": metadata}, MODEL_PATH
    )
    REPORT_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if verbose:
        print("HEALTH ANOMALY DETECTOR — IsolationForest")
        print(f"  trained on {len(train_rows)} rows from {len(train_histories)} synthetic dogs")
        print(f"  contamination {contamination:.3f}, {N_ESTIMATORS} trees, seed {RANDOM_STATE}")
        print(f"\n  Held-out dogs: {len(test_histories)} ({len(test_rows)} rows)")
        print(f"  recall on planted anomalies : {metrics['recall_on_planted_anomalies']}")
        print(f"  precision                   : {metrics['precision']}")
        print(f"  flagged share               : {metrics['flagged_share']}")
        print("\n  Per scenario:")
        for name, result in metrics["per_scenario"].items():
            if result["type"] == "anomalous":
                print(f"    {name:32} detected {result['detected']:4}/"
                      f"{result['planted_observations']:<4} = {result['detection_rate']}")
            else:
                print(f"    {name:32} false positives {result['flagged']:4}/"
                      f"{result['observations']:<4} = {result['false_positive_rate']}")
        print(f"\n  saved -> {MODEL_PATH.name}, {REPORT_PATH.name}")
        print("\n  Synthetic labels only. Not veterinary ground truth.")

    return metadata


def report() -> dict:
    if not REPORT_PATH.exists():
        raise FileNotFoundError(
            f"{REPORT_PATH} is missing — run `python -m ml.train_health_anomaly_model` first."
        )
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    if "--report" in sys.argv:
        print(json.dumps(report(), indent=2))
    else:
        train()
