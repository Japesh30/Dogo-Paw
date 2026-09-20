"""Part A — Adoption Success Predictor (supervised learning).

Predicts P(adoption does not end in a return) for an adopter-dog pair, from a
trained logistic regression rather than hand-written rules.

    python -m ml.success_model            # train, evaluate, save
    python -m ml.success_model --report   # just print the saved coefficients

Why the labels are generated the way they are
---------------------------------------------
There is no real return-rate data for a student project, so the training set is
synthetic. Purely random labels would leave the model nothing to learn, so each
row's success probability is built from things that genuinely drive returns —
energy mismatch, too little space, a dog needing more handling than the adopter
has, and ignored kid/pet constraints — then sampled with noise. The model still
has to *discover* those relationships; they are not fed to it as rules. The
noise floor is deliberately high enough that perfect accuracy is impossible,
which keeps the reported number honest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.features import FEATURE_NAMES, pair_features

MODEL_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = MODEL_DIR / "success_model.joblib"
COEF_PATH = MODEL_DIR / "success_model_coefficients.json"

RANDOM_STATE = 42

ACTIVITY = ["low", "medium", "high"]
HOMES = ["apartment", "house_no_yard", "house_with_yard"]
EXPERIENCE = ["none", "some", "experienced"]
ENERGY = ["low", "medium", "high"]
SIZES = ["small", "medium", "large"]
TEMPERAMENTS = [
    "calm", "friendly", "gentle", "playful", "energetic",
    "independent", "shy", "anxious", "protective", "stubborn",
]


# --------------------------------------------------------------------------- #
# Synthetic dataset
# --------------------------------------------------------------------------- #
def generate_dataset(n: int = 300, seed: int = RANDOM_STATE):
    """Build `n` past adopter-dog pairs with a plausible success label."""
    rng = np.random.default_rng(seed)
    rows, labels, raw = [], [], []

    for _ in range(n):
        adopter = {
            "activity_level": rng.choice(ACTIVITY),
            "home_type": rng.choice(HOMES),
            "experience_level": rng.choice(EXPERIENCE),
            "has_kids": bool(rng.random() < 0.4),
            "has_other_pets": bool(rng.random() < 0.45),
        }
        dog = {
            "energy_level": rng.choice(ENERGY),
            "size": rng.choice(SIZES),
            "temperament": rng.choice(TEMPERAMENTS),
            "medical_needs": bool(rng.random() < 0.25),
            "good_with_kids": bool(rng.random() < 0.7),
            "good_with_other_pets": bool(rng.random() < 0.7),
        }

        x = pair_features(adopter, dog)
        idx = {name: i for i, name in enumerate(FEATURE_NAMES)}

        # Start optimistic; most adoptions do work out.
        p = 0.92
        p -= 0.35 * x[idx["energy_gap"]]           # under/over-exercised dog
        p -= 0.22 * x[idx["space_gap"]]            # wrong amount of room
        p -= 0.45 * x[idx["experience_shortfall"]]  # dog is too much to handle
        if x[idx["kid_conflict"]]:
            p -= 0.40
        if x[idx["pet_conflict"]]:
            p -= 0.30
        if x[idx["dog_medical_needs"]]:
            p -= 0.08

        p = float(np.clip(p, 0.03, 0.97))
        rows.append(x)
        labels.append(int(rng.random() < p))
        raw.append((adopter, dog, p))

    return np.array(rows), np.array(labels), raw


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #
def train(n: int = 300, seed: int = RANDOM_STATE, verbose: bool = True) -> dict:
    X, y, raw = generate_dataset(n, seed)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y
    )

    # Scaling matters here: the 0-1 scales and the one-hot columns have very
    # different spreads, and the coefficients are meant to be compared.
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "clf",
                LogisticRegression(max_iter=2000, random_state=seed, C=1.0),
            ),
        ]
    )
    model.fit(X_train, y_train)

    train_acc = accuracy_score(y_train, model.predict(X_train))
    test_acc = accuracy_score(y_test, model.predict(X_test))
    proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba)
    cv = cross_val_score(model, X, y, cv=5, scoring="accuracy")

    # Coefficients, in the scaled space, so magnitudes are comparable.
    coefs = model.named_steps["clf"].coef_[0]
    importances = sorted(
        (
            {
                "feature": name,
                "coefficient": round(float(c), 4),
                "effect": "increases success" if c > 0 else "reduces success",
                "abs": abs(float(c)),
            }
            for name, c in zip(FEATURE_NAMES, coefs)
        ),
        key=lambda d: d["abs"],
        reverse=True,
    )

    # Labels are sampled Bernoulli(p), so even a model that knew p exactly would
    # only be right max(p, 1-p) of the time. That average is the ceiling, and it
    # is what the accuracy below should be judged against — not 100%.
    ps = np.array([r[2] for r in raw])
    bayes_ceiling = float(np.mean(np.maximum(ps, 1 - ps)))

    metrics = {
        "n_samples": int(n),
        "n_features": int(X.shape[1]),
        "train_accuracy": round(float(train_acc), 4),
        "test_accuracy": round(float(test_acc), 4),
        "roc_auc": round(float(auc), 4),
        "cv_accuracy_mean": round(float(cv.mean()), 4),
        "cv_accuracy_std": round(float(cv.std()), 4),
        "bayes_ceiling": round(bayes_ceiling, 4),
        "pct_of_ceiling": round(float(cv.mean()) / bayes_ceiling, 4),
        "positive_rate": round(float(y.mean()), 4),
        "confusion_matrix": confusion_matrix(y_test, model.predict(X_test)).tolist(),
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURE_NAMES}, MODEL_PATH)
    COEF_PATH.write_text(
        json.dumps(
            {
                "metrics": metrics,
                "coefficients": [
                    {k: v for k, v in d.items() if k != "abs"} for d in importances
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if verbose:
        print("=" * 62)
        print("ADOPTION SUCCESS PREDICTOR — Logistic Regression")
        print("=" * 62)
        print(f"  samples              {metrics['n_samples']}")
        print(f"  features             {metrics['n_features']}")
        print(f"  successful in data   {metrics['positive_rate'] * 100:.1f}%")
        print(f"  train accuracy       {metrics['train_accuracy'] * 100:.2f}%")
        print(f"  TEST ACCURACY        {metrics['test_accuracy'] * 100:.2f}%")
        print(f"  ROC AUC              {metrics['roc_auc']:.4f}")
        print(
            f"  5-fold CV accuracy   {metrics['cv_accuracy_mean'] * 100:.2f}% "
            f"(+/- {metrics['cv_accuracy_std'] * 100:.2f})"
        )
        print(f"  Bayes ceiling        {metrics['bayes_ceiling'] * 100:.2f}%  "
              "(the most any model could score on this data)")
        print(f"  reached              {metrics['pct_of_ceiling'] * 100:.1f}% of the ceiling")
        print(f"\n  confusion matrix (test)  {metrics['confusion_matrix']}")
        print("\n  classification report (test):")
        print(
            classification_report(
                y_test,
                model.predict(X_test),
                target_names=["returned", "successful"],
                zero_division=0,
            )
        )
        print("  top 10 factors by influence:")
        for d in importances[:10]:
            arrow = "+" if d["coefficient"] > 0 else "-"
            print(f"    {arrow} {d['feature']:<28} {d['coefficient']:+.4f}")
        print(f"\n  saved model        -> {MODEL_PATH.name}")
        print(f"  saved coefficients -> {COEF_PATH.name}")

    return metrics


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #
_cached = None


def load_model():
    """Loaded once and kept in memory — never retrain on a request."""
    global _cached
    if _cached is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"{MODEL_PATH} is missing — run `python -m ml.success_model` first."
            )
        _cached = joblib.load(MODEL_PATH)
    return _cached


def predict_success(adopter: dict, dog: dict) -> float:
    """Probability 0-100 that this pairing works out."""
    bundle = load_model()
    x = pair_features(adopter, dog).reshape(1, -1)
    return round(float(bundle["model"].predict_proba(x)[0, 1]) * 100, 1)


def predict_success_batch(adopter: dict, dogs: list[dict]) -> list[float]:
    """One matrix, one call — the results page scores every dog at once."""
    if not dogs:
        return []
    bundle = load_model()
    X = np.vstack([pair_features(adopter, d) for d in dogs])
    return [round(float(p) * 100, 1) for p in bundle["model"].predict_proba(X)[:, 1]]


def coefficient_report() -> dict:
    if not COEF_PATH.exists():
        raise FileNotFoundError("Coefficients not found — train the model first.")
    return json.loads(COEF_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    if "--report" in sys.argv:
        print(json.dumps(coefficient_report(), indent=2))
    else:
        train()
