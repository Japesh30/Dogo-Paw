"""
Checks for the ML anomaly layer: features, training, evaluation, inference,
its integration with the deterministic analysis, and its fallbacks.

    python test_health_anomaly.py

The feature and model sections need no database. The API section runs the real
app against a throwaway SQLite file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail != "" and not condition else ""))
    if not condition:
        FAILURES.append(label)


def section(title: str) -> None:
    print(f"\n{title}")


def obs(day: date, weight=None, temp=None, id=None) -> dict:
    return {"id": id, "observation_date": day, "weight_kg": weight, "temperature_c": temp}


def run_checks() -> None:
    import numpy as np

    import health_intelligence
    from ml import health_anomaly_data as data
    from ml import health_anomaly_service as service
    from ml import health_features as features
    from ml import train_health_anomaly_model as trainer

    start = date(2026, 1, 1)
    steady = [
        obs(start + timedelta(days=i * 20), weight=20 + (i % 2) * 0.1, temp=38.5, id=i)
        for i in range(6)
    ]

    # ------------------------------------------------------------- features
    section("1. Feature engineering")
    rows = features.build_rows(steady)
    check("a row is produced only once enough history exists",
          len(rows) == len(steady) - features.MIN_BASELINE, len(rows))
    check("rows carry the observation they describe",
          all(r["observation_id"] is not None for r in rows))
    check("every feature is present and finite",
          all(len(r["features"]) == len(features.FEATURE_NAMES)
              and np.all(np.isfinite(r["features"])) for r in rows))
    check("a steady dog produces near-zero change features",
          abs(rows[-1]["values"].get("weight_pct_change", 0)) < 2)

    check("too little history produces no row",
          features.build_rows(steady[:3]) == [])
    check("no observations produce no rows", features.build_rows([]) == [])

    # Missing values must not become zeros, which would read as "no change".
    no_weight = [obs(start + timedelta(days=i * 20), temp=38.5, id=i) for i in range(6)]
    weightless = features.build_rows(no_weight)
    check("a history without weights still scores temperature",
          weightless and "temperature" in weightless[-1]["evidence"])
    check("...and reports that weight was not considered",
          "weight" not in weightless[-1]["available"], weightless[-1]["available"])
    check("...and records no invented weight values",
          "weight_pct_change" not in weightless[-1]["values"])
    check("a history with neither measurement produces nothing",
          features.build_rows([obs(start + timedelta(days=i * 20), id=i) for i in range(6)]) == [])

    section("2. Ordering and leakage")
    shuffled = [steady[3], steady[0], steady[5], steady[1], steady[4], steady[2]]
    check("input order does not matter; rows are sorted by date",
          [r["observation_date"] for r in features.build_rows(shuffled)]
          == [r["observation_date"] for r in rows])

    # The decisive one: a row must never change when later observations are
    # added, which is what "no future leakage" means in practice.
    plus_future = steady + [obs(start + timedelta(days=200), weight=9.0, temp=41.0, id=99)]
    before = features.build_rows(steady)
    after = features.build_rows(plus_future)
    check("adding a later observation does not change earlier feature rows",
          all(np.array_equal(a["features"], b["features"])
              for a, b in zip(before, after[: len(before)])))
    check("the later observation adds its own row", len(after) == len(before) + 1)
    check("feature output is deterministic",
          all(np.array_equal(a["features"], b["features"])
              for a, b in zip(features.build_rows(steady), before)))

    section("3. Features respond to the patterns they are meant to catch")
    drop = steady[:5] + [obs(start + timedelta(days=100), weight=17.0, temp=38.5, id=5)]
    drop_row = features.build_rows(drop)[-1]
    check("a weight drop shows a negative percent change",
          drop_row["values"]["weight_pct_change"] < -10, drop_row["values"])
    check("...and a large deviation from baseline", drop_row["values"]["weight_z"] < -3)
    spike = steady[:5] + [obs(start + timedelta(days=100), weight=20.0, temp=40.4, id=5)]
    spike_row = features.build_rows(spike)[-1]
    check("a temperature spike shows a positive change",
          spike_row["values"]["temp_change"] > 1.5)
    gap = steady[:5] + [obs(start + timedelta(days=300), weight=20.0, temp=38.5, id=5)]
    gap_row = features.build_rows(gap)[-1]
    check("a long silence shows a large interval ratio",
          gap_row["values"]["interval_ratio"] > 5, gap_row["values"]["interval_ratio"])

    # --------------------------------------------------------------- data
    section("4. Synthetic development data")
    histories = data.generate(n_dogs=70)
    check("every scenario is generated",
          {h[0]["scenario"] for h in histories} == set(data.SCENARIOS),
          {h[0]["scenario"] for h in histories})
    check("data generation is reproducible",
          [o["weight_kg"] for o in data.generate(n_dogs=5)[0]]
          == [o["weight_kg"] for o in data.generate(n_dogs=5)[0]])
    check("normal scenarios plant nothing",
          all(not o["is_planted"] for h in histories
              for o in h if not data.SCENARIOS[o["scenario"]]))
    check("anomalous scenarios plant something",
          all(any(o["is_planted"] for o in h) for h in histories
              if data.SCENARIOS[h[0]["scenario"]]))
    train_set, test_set = data.split(histories)
    check("train and holdout are disjoint sets of dogs",
          not {id(h) for h in train_set} & {id(h) for h in test_set})
    check("the split keeps whole dogs together",
          len(train_set) + len(test_set) == len(histories))

    # -------------------------------------------------------------- model
    section("5. Trained model")
    check("the artifact exists", trainer.MODEL_PATH.exists(),
          "run python -m ml.train_health_anomaly_model")
    bundle = service.load_model()
    metadata = bundle["metadata"]
    check("the bundle carries the model, features and metadata",
          {"model", "features", "metadata"} <= set(bundle))
    check("feature names match the feature module", bundle["features"] == features.FEATURE_NAMES)
    check("the model is versioned", metadata["model_version"] == trainer.MODEL_VERSION)
    check("parameters are recorded, not left implicit",
          {"n_estimators", "contamination", "random_state", "max_samples"}
          <= set(metadata["parameters"]))
    check("the training set is described as synthetic",
          "synthetic" in metadata["dataset"]["source"])
    check("metadata states it is not a diagnosis", "not_a_diagnosis" in metadata)
    check("training metadata records when and with what",
          metadata["trained_at"] and metadata["sklearn_version"])
    check("the JSON report matches the artifact",
          json.loads(trainer.REPORT_PATH.read_text(encoding="utf-8"))["model_version"]
          == metadata["model_version"])
    check("model_info reports the version without loading twice",
          service.model_info()["model_version"] == trainer.MODEL_VERSION)

    section("6. Evaluation")
    evaluation = metadata["evaluation"]
    check("evaluation ran on held-out dogs",
          metadata["dataset"]["dogs_holdout"] > 0
          and metadata["dataset"]["dogs_train"] > metadata["dataset"]["dogs_holdout"])
    check("training and evaluation rows are separate",
          evaluation["evaluation_rows"] != metadata["dataset"]["train_rows"])
    check("a confusion matrix is reported", {"true_positive", "false_positive",
          "false_negative", "true_negative"} <= set(evaluation["confusion_matrix"]))
    check("planted anomalies are detected more often than not",
          evaluation["recall_on_planted_anomalies"] > 0.5,
          evaluation["recall_on_planted_anomalies"])
    check("normal dogs are mostly left alone",
          evaluation["per_scenario"]["stable"]["false_positive_rate"] < 0.1,
          evaluation["per_scenario"]["stable"]["false_positive_rate"])
    check("not everything is called an anomaly", evaluation["flagged_share"] < 0.2)
    check("sudden weight drops are caught",
          evaluation["per_scenario"]["sudden_weight_drop"]["detection_rate"] > 0.7)
    check("gradual weight decline is caught",
          evaluation["per_scenario"]["gradual_weight_decline"]["detection_rate"] > 0.5)
    check("temperature spikes are caught",
          evaluation["per_scenario"]["isolated_temperature_spike"]["detection_rate"] > 0.7)
    check("the evaluation says the labels are synthetic, not clinical",
          "not veterinary ground truth" in evaluation["note"])

    section("7. Reproducible training")
    # Retrain into a temp artifact path and compare scores, not file bytes:
    # joblib output embeds timestamps, so identical models differ on disk.
    sample = features.matrix(features.build_rows(steady))
    first = bundle["model"].decision_function(sample)
    rows_train, X_train = trainer.rows_from(data.split(data.generate())[0])
    retrained = trainer.build_pipeline(metadata["parameters"]["contamination"])
    retrained.fit(X_train)
    check("retraining with the same seed gives the same scores",
          np.allclose(first, retrained.decision_function(sample)),
          (first[:2], retrained.decision_function(sample)[:2]))

    # Release the training matrices before the rest of the suite: they are tens
    # of megabytes, and the API section below starts a full app (scikit-learn,
    # scrypt password hashing) in the same process.
    del rows_train, X_train, retrained
    import gc
    gc.collect()

    # ---------------------------------------------------------- inference
    section("8. Inference service")
    result = service.analyse_observations(steady)
    check("a steady history is available and quiet",
          result["available"] and result["anomaly_count"] == 0, result.get("anomaly_count"))
    check("the response names the model", result["model_version"] == trainer.MODEL_VERSION)
    check("the response says it is not a probability",
          "not a probability" in result["score_scale"]["note"])
    check("the response disclaims diagnosis", "does not diagnose" in result["disclaimer"])

    unusual = service.analyse_observations(
        steady[:5] + [obs(start + timedelta(days=100), weight=16.5, temp=40.2, id=5)])
    check("a sharp change is flagged", unusual["anomaly_count"] >= 1, unusual["anomaly_count"])
    anomaly = unusual["anomalies"][0]
    check("the anomaly has the documented shape",
          {"observation_id", "observation_date", "is_anomaly", "anomaly_score",
           "severity", "reasons", "evidence", "model_version"} <= set(anomaly))
    check("severity is one of the known bands",
          anomaly["severity"] in ("low", "moderate", "high"))
    check("reasons quote real numbers from the history",
          any("kg" in r for r in anomaly["reasons"])
          and any("baseline" in r for r in anomaly["reasons"]), anomaly["reasons"])
    check("reasons avoid diagnostic language",
          not any(word in " ".join(anomaly["reasons"]).lower()
                  for word in ("diagnos", "disease", "illness", "infection")))
    check("evidence keeps the underlying measurements",
          anomaly["evidence"]["weight"]["current_kg"] == 16.5)
    check("scoring is deterministic",
          service.analyse_observations(steady[:5] + [obs(start + timedelta(days=100),
              weight=16.5, temp=40.2, id=5)])["anomalies"][0]["anomaly_score"]
          == anomaly["anomaly_score"])

    section("9. Fallbacks")
    short = service.analyse_observations(steady[:2])
    check("too little history is reported, not raised",
          short["available"] is False and short["reason"] == "insufficient_history")
    check("...and says how much is needed",
          short["observations_required"] == features.MIN_OBSERVATIONS)
    check("no observations at all is handled",
          service.analyse_observations([])["reason"] == "insufficient_history")
    check("an unavailable result still carries an empty anomaly list",
          short["anomalies"] == [])

    # A malformed row must not escape as an exception.
    broken = [dict(o) for o in steady]
    broken[-1]["observation_date"] = "not-a-date"
    fallback = service.analyse_observations(broken)
    check("malformed data returns a reason rather than raising",
          fallback["available"] is False and fallback["reason"] in
          ("scoring_failed", "insufficient_history"), fallback.get("reason"))
    check("a missing artifact is reported as model_unavailable",
          service.unavailable("model_unavailable")["reason"] == "model_unavailable")

    from models import Dog as Dog_

    section("9b. Failure and chaos handling")
    import importlib
    import shutil
    import tempfile as _tempfile
    from pathlib import Path as _Path

    import joblib as _joblib

    original_path = service.MODEL_PATH
    original_cache = service._cached

    def with_artifact(make) -> dict:
        """Point the service at a temporary artifact and score a known history."""
        with _tempfile.TemporaryDirectory() as tmp:
            path = _Path(tmp) / "artifact.joblib"
            make(path)
            service.MODEL_PATH = path
            service._cached = None
            try:
                return service.analyse_observations(steady)
            finally:
                service.MODEL_PATH = original_path
                service._cached = original_cache

    missing = with_artifact(lambda path: None)  # never created
    check("a missing artifact reports model_unavailable",
          missing["available"] is False and missing["reason"] == "model_unavailable")

    corrupt = with_artifact(lambda path: path.write_bytes(b"this is not a joblib file"))
    check("a corrupt artifact reports model_unavailable, not a crash",
          corrupt["available"] is False and corrupt["reason"] == "model_unavailable",
          corrupt.get("reason"))

    def mismatched(path):
        bundle = _joblib.load(original_path)
        # An artifact trained before a feature was added or reordered.
        bundle["features"] = bundle["features"][:-1]
        _joblib.dump(bundle, path)

    stale = with_artifact(mismatched)
    check("an artifact with a different feature schema is refused",
          stale["available"] is False and stale["reason"] == "feature_schema_mismatch",
          stale.get("reason"))
    check("...rather than silently scoring the wrong columns", stale["anomalies"] == [])

    def reordered(path):
        bundle = _joblib.load(original_path)
        bundle["features"] = list(reversed(bundle["features"]))
        _joblib.dump(bundle, path)

    check("a reordered feature schema is refused",
          with_artifact(reordered)["reason"] == "feature_schema_mismatch")

    def not_a_bundle(path):
        _joblib.dump(["not", "a", "bundle"], path)

    check("an artifact that is not a model bundle is refused",
          with_artifact(not_a_bundle)["reason"] == "feature_schema_mismatch")
    check("the real model still works afterwards",
          service.analyse_observations(steady)["available"] is True)

    # A detector that blows up must not take the analysis with it.
    def exploding(_observations):
        raise RuntimeError("detector exploded")

    try:
        health_intelligence.analyse(
            Dog_(id=1, name="Chaos"), vaccinations=[], medications=[], observations=[],
            follow_ups=[], records=[], today=date(2026, 5, 1), ml_detector=exploding)
        raised = False
    except RuntimeError:
        raised = True
    check("a detector exception is visible to the caller, not swallowed silently", raised)
    check("the built-in detector never raises for malformed rows",
          health_intelligence.detect_ml_anomalies(
              [{"observation_date": "bad"}])["available"] is False)

    # --------------------------------------------- deterministic untouched
    section("10. The deterministic analysis is unchanged")
    from models import Dog, HealthObservation

    dog = Dog(id=1, name="Test")
    rows_orm = [
        HealthObservation(id=i, dog_id=1, observation_date=o["observation_date"],
                          weight_kg=o["weight_kg"], temperature_c=o["temperature_c"])
        for i, o in enumerate(steady)
    ]
    quiet = lambda _obs: {"available": False, "reason": "model_unavailable", "anomalies": []}  # noqa: E731
    base = health_intelligence.analyse(
        dog, vaccinations=[], medications=[], observations=rows_orm, follow_ups=[],
        records=[], today=date(2026, 5, 1), ml_detector=quiet)
    with_ml = health_intelligence.analyse(
        dog, vaccinations=[], medications=[], observations=rows_orm, follow_ups=[],
        records=[], today=date(2026, 5, 1))
    check("risk score does not depend on the ML layer",
          base["risk_score"] == with_ml["risk_score"], (base["risk_score"], with_ml["risk_score"]))
    check("risk level does not depend on the ML layer",
          base["risk_level"] == with_ml["risk_level"])
    check("findings do not depend on the ML layer", base["findings"] == with_ml["findings"])
    check("data quality does not depend on the ML layer",
          base["data_quality"]["findings"] == with_ml["data_quality"]["findings"])
    check("the score breakdown contains no ML entry",
          not any("ml" in f["code"] for f in with_ml["score_breakdown"]["points_by_finding"]))
    check("ML results are reported in their own section",
          "ml_anomalies" in with_ml and with_ml["ml_anomalies"]["available"] is True)
    check("a model failure leaves the analysis intact",
          base["ml_anomalies"]["available"] is False and base["risk_score"] == with_ml["risk_score"])
    check("the summary reports the ML state",
          health_intelligence.summarise(with_ml)["ml_anomalies"]["model_version"]
          == trainer.MODEL_VERSION)


def api_checks() -> None:
    """The endpoint and the alert integration, against a real database."""
    from datetime import date, timedelta

    import app as app_module
    from models import Dog, HealthAlert, HealthObservation, db

    app = app_module.app
    client = app.test_client()
    today = date.today()

    def login(email, password):
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {r.json['token']}"}

    admin, user = login("admin@dogo-paw.org", "admin123"), login("demo@dogo-paw.org", "demo123")

    with app.app_context():
        db.session.add(Dog(id=9300, name="Anomaly", age=4, energy_level="low",
                           size="medium", temperament="calm"))
        db.session.add(Dog(id=9301, name="Quiet", age=4, energy_level="low",
                           size="medium", temperament="calm"))
        db.session.commit()
        # A clean history ending in a sharp, simultaneous weight drop and fever.
        for index, (weight, temp) in enumerate(
                [(20.0, 38.4), (20.2, 38.5), (19.9, 38.6), (20.1, 38.4),
                 (20.0, 38.5), (17.2, 40.1)]):
            db.session.add(HealthObservation(
                dog_id=9300, observation_date=today - timedelta(days=(6 - index) * 20),
                weight_kg=weight, temperature_c=temp))
        # A short history, below the threshold for scoring.
        db.session.add(HealthObservation(
            dog_id=9301, observation_date=today - timedelta(days=5), weight_kg=12.0))
        db.session.commit()

    section("11. API")
    check("anonymous cannot read the analysis",
          client.get("/api/dogs/9300/medical/health-analysis").status_code == 401)
    check("a signed-in user can read it",
          client.get("/api/dogs/9300/medical/health-analysis", headers=user).status_code == 200)
    check("an unknown dog gives 404",
          client.get("/api/dogs/9999/medical/health-analysis", headers=admin).status_code == 404)

    body = client.get("/api/dogs/9300/medical/health-analysis", headers=admin).get_json()
    ml = body["ml_anomalies"]
    check("the analysis carries the ML section", ml["available"] is True)
    check("an anomaly is reported for the odd observation", ml["anomaly_count"] >= 1)
    check("the section names the model version", ml["model_version"] == "health-anomaly-v1")
    check("the deterministic sections are still present",
          {"risk_score", "findings", "data_quality", "positive_signals"} <= set(body))
    check("no response field exposes a traceback",
          "Traceback" not in json.dumps(body))

    quiet = client.get("/api/dogs/9301/medical/health-analysis", headers=admin).get_json()
    check("a short history reports insufficient_history",
          quiet["ml_anomalies"]["available"] is False
          and quiet["ml_anomalies"]["reason"] == "insufficient_history")
    check("...and the rest of the analysis still works",
          isinstance(quiet["risk_score"], int) and "data_quality" in quiet)

    summary = client.get("/api/dogs/9300/medical/health-analysis/summary",
                         headers=admin).get_json()
    check("the summary endpoint reports the ML state",
          summary["ml_anomalies"]["available"] is True)

    section("12. Alert integration")
    first = client.post("/api/dogs/9300/medical/health-alerts/sync", headers=admin).get_json()
    with app.app_context():
        ml_alerts = HealthAlert.query.filter_by(dog_id=9300, finding_code="ml.health_anomaly").all()
        check("a strong anomaly becomes an alert", len(ml_alerts) == 1, len(ml_alerts))
        if ml_alerts:
            alert = ml_alerts[0]
            check("the ML alert uses its own finding code",
                  alert.finding_code == "ml.health_anomaly")
            check("it is categorised as an ML anomaly", alert.category == "ml_anomaly")
            check("it records the model version",
                  alert.evidence.get("model_version") == "health-anomaly-v1")
            check("it records the anomaly score", "anomaly_score" in alert.evidence)
            check("it keeps the reasons as evidence", alert.evidence.get("reasons"))
            check("it is tied to the observation, so a second one is a second alert",
                  alert.entity_key.startswith("observation_id:"), alert.entity_key)
            check("it says it is not a diagnosis", "not a diagnosis" in alert.reason)
            check("it is recorded at moderate severity", alert.severity == "moderate")

        deterministic = HealthAlert.query.filter(
            HealthAlert.dog_id == 9300,
            HealthAlert.finding_code != "ml.health_anomaly").all()
        check("deterministic alerts are still raised separately", len(deterministic) >= 1)
        check("deterministic alerts keep their own codes",
              all(not a.finding_code.startswith("ml.") for a in deterministic))

    again = client.post("/api/dogs/9300/medical/health-alerts/sync", headers=admin).get_json()
    check("re-running creates no duplicate ML alert", again["created"] == 0, again)
    with app.app_context():
        check("still exactly one ML alert",
              HealthAlert.query.filter_by(dog_id=9300, finding_code="ml.health_anomaly").count() == 1)
    check("the risk score is unchanged by the ML alert",
          first["risk_score"] == again["risk_score"])

    with app.app_context():
        scored = client.get("/api/dogs/9300/medical/health-analysis", headers=admin).get_json()
        moderate = [a for a in scored["ml_anomalies"]["anomalies"] if a["severity"] != "high"]
        check("only high-severity anomalies become alerts",
              HealthAlert.query.filter_by(dog_id=9300, finding_code="ml.health_anomaly").count()
              == len([a for a in scored["ml_anomalies"]["anomalies"] if a["severity"] == "high"]),
              f"{len(moderate)} non-high anomalies present")


def main() -> int:
    # The two halves run in separate processes. The model checks allocate large
    # training matrices, and doing that in the same process that later starts a
    # full Flask app (scikit-learn plus scrypt password hashing) exhausts the
    # allocator on a memory-constrained machine.
    if "--child-model" in sys.argv:
        run_checks()
        print(f"\n{'all passed' if not FAILURES else f'{len(FAILURES)} FAILED: {FAILURES}'}")
        return 1 if FAILURES else 0

    if "--child-api" in sys.argv:
        api_checks()
        print(f"\n{'all passed' if not FAILURES else f'{len(FAILURES)} FAILED: {FAILURES}'}")
        return 1 if FAILURES else 0

    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ,
               "DATABASE_URL": f"sqlite:///{Path(tmp) / 'anomaly.db'}",
               "APP_ENV": "development", "RATE_LIMIT_ENABLED": "false",
               "PYTHONIOENCODING": "utf-8"}
        code = 0
        for stage in ("--child-model", "--child-api"):
            code = subprocess.run(
                [sys.executable, __file__, stage], cwd=HERE, env=env, timeout=900,
            ).returncode or code
        return code


if __name__ == "__main__":
    sys.exit(main())
