"""Scoring a dog's observations with the trained anomaly detector.

Loads the artifact once and keeps it, the same pattern as the success model and
the chatbot. Nothing here trains; training is `python -m ml.train_health_anomaly_model`.

What this answers: "does this reading look unlike the ones before it, for this
dog?" What it does not answer: what is wrong with the dog. There is no
diagnosis, no condition, no probability of illness. The score is a distance
from ordinary, produced by a model fitted on synthetic development data.

Every failure is a quiet, reported unavailability rather than an exception:
a missing artifact, a short history or a malformed row must never take down
the health analysis that surrounds it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np

from ml.health_features import FEATURE_NAMES, MIN_OBSERVATIONS, build_rows, matrix

# Where the artifact lives and what it is called. Defined here, in the
# inference path, rather than imported from the trainer: importing the trainer
# would pull scikit-learn's estimators and the synthetic data generator into
# every API process, for two constants. The trainer imports these from here.
MODEL_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = MODEL_DIR / "health_anomaly_model.joblib"
REPORT_PATH = MODEL_DIR / "health_anomaly_model.json"

MODEL_VERSION = "health-anomaly-v1"

logger = logging.getLogger(__name__)

# Severity from where a flagged score sits against the training distribution,
# which the artifact records. Bands, not thresholds invented here.
SEVERITY_HIGH_PERCENTILE = "train_score_p99"
SEVERITY_MODERATE_PERCENTILE = "train_score_p90"

# Only anomalies at this severity are worth an admin's attention as an alert;
# see health_alerts.py for the policy.
ALERTABLE_SEVERITY = "high"

_cached = None


def load_model():
    """Loaded once and kept in memory — never trained or reloaded per request."""
    global _cached
    if _cached is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"{MODEL_PATH} is missing — run "
                "`python -m ml.train_health_anomaly_model` first."
            )
        bundle = joblib.load(MODEL_PATH)
        check_schema(bundle)
        _cached = bundle
    return _cached


class SchemaMismatch(Exception):
    """The artifact was trained on different features than this code builds."""


def check_schema(bundle) -> None:
    """Refuse an artifact whose feature contract does not match this code.

    Features are positional: the model reads column 3 as `weight_slope_pct`
    because that is where it sat during training. If health_features.py later
    gains, loses or reorders a feature, an older artifact would still accept
    the matrix and score it — silently, against the wrong columns, producing
    numbers that look plausible and mean nothing. Refusing is the only safe
    answer; the layer then reports itself unavailable and the rest of the
    analysis carries on.
    """
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise SchemaMismatch("artifact is not a model bundle")
    stored = bundle.get("features")
    if stored != FEATURE_NAMES:
        raise SchemaMismatch(
            "artifact feature schema does not match health_features.py "
            f"(artifact: {stored}, expected: {FEATURE_NAMES}). "
            "Retrain with `python -m ml.train_health_anomaly_model`."
        )


def model_info() -> dict:
    """Version and training provenance, for the dashboard and the API."""
    try:
        metadata = load_model()["metadata"]
    except Exception:
        # Missing, corrupt or incompatible artifact — all reported the same way.
        logger.warning("health anomaly model metadata unavailable", exc_info=True)
        return {"available": False, "model_version": MODEL_VERSION}
    return {
        "available": True,
        "model_version": metadata["model_version"],
        "algorithm": metadata["algorithm"],
        "trained_at": metadata["trained_at"],
        "dataset": metadata["dataset"]["source"],
        "features": metadata["features"],
    }


def _severity(score: float, reference: dict) -> str:
    if score >= reference.get(SEVERITY_HIGH_PERCENTILE, float("inf")):
        return "high"
    if score >= reference.get(SEVERITY_MODERATE_PERCENTILE, float("inf")):
        return "moderate"
    return "low"


def _reasons(row: dict) -> list[str]:
    """Plain-English evidence, in the model's own terms.

    Deliberately worded as comparisons against this dog's own recent readings,
    so an ML reason can never be mistaken for a deterministic rule ("weight
    declined by >= 10%") or for a clinical statement.
    """
    reasons = []
    evidence = row["evidence"]

    weight = evidence.get("weight")
    if weight:
        direction = "below" if weight["percent_from_baseline"] < 0 else "above"
        reasons.append(
            f"Weight {weight['current_kg']} kg is {abs(weight['percent_from_baseline'])}% "
            f"{direction} this dog's recent baseline of {weight['baseline_mean_kg']} kg "
            f"(last {weight['baseline_readings']} weigh-ins)."
        )
        if abs(weight["z_score"]) >= 2:
            reasons.append(
                f"That is {abs(weight['z_score'])} times the dog's usual weight variation "
                f"(±{weight['baseline_std_kg']} kg)."
            )
        if abs(weight["percent_change"]) >= 3:
            reasons.append(
                f"Change of {weight['percent_change']}% since the previous weight on "
                f"{weight['previous_date']} ({weight['days_since_previous_weight']} days)."
            )

    temperature = evidence.get("temperature")
    if temperature:
        direction = "below" if temperature["difference_from_baseline_c"] < 0 else "above"
        reasons.append(
            f"Temperature {temperature['current_c']} °C is "
            f"{abs(temperature['difference_from_baseline_c'])} °C {direction} this dog's "
            f"recent baseline of {temperature['baseline_mean_c']} °C."
        )
        if abs(temperature["z_score"]) >= 2:
            reasons.append(
                f"That is {abs(temperature['z_score'])} times its usual variation "
                f"(±{temperature['baseline_std_c']} °C)."
            )

    cadence = evidence.get("cadence")
    if cadence and cadence["interval_ratio"] >= 2:
        reasons.append(
            f"Recorded {cadence['days_since_previous']} days after the previous "
            f"observation, against a usual gap of about "
            f"{cadence['usual_interval_days']} days."
        )

    return reasons


def unavailable(reason: str, detail: str | None = None) -> dict:
    """The shape returned whenever scoring cannot happen. Always safe to render."""
    return {
        "available": False,
        "reason": reason,
        "detail": detail,
        "model_version": MODEL_VERSION,
        "anomalies": [],
    }


def analyse_observations(observations) -> dict:
    """Score one dog's observation history.

    Returns `available: False` with a machine-readable reason rather than
    raising, because this sits inside the health analysis and must never be
    what breaks it.
    """
    rows_in = list(observations or [])
    if len(rows_in) < MIN_OBSERVATIONS:
        return {
            **unavailable("insufficient_history"),
            "observations_available": len(rows_in),
            "observations_required": MIN_OBSERVATIONS,
        }

    try:
        bundle = load_model()
    except FileNotFoundError as exc:
        # Expected when the artifact has not been trained; a warning, not a crash.
        logger.warning("health anomaly model unavailable: %s", exc)
        return unavailable("model_unavailable")
    except SchemaMismatch as exc:
        # A stale artifact against newer feature code. Distinct from a missing
        # one, because the fix is different: retrain, do not just install.
        logger.error("health anomaly model schema mismatch: %s", exc)
        return unavailable("feature_schema_mismatch")
    except Exception:
        # A corrupt or incompatible artifact. The detail goes to the server log
        # only; the caller gets a reason, never a trace.
        logger.exception("health anomaly model failed to load")
        return unavailable("model_unavailable")

    try:
        rows = build_rows(rows_in)
        if not rows:
            return {
                **unavailable("insufficient_history"),
                "observations_available": len(rows_in),
                "observations_required": MIN_OBSERVATIONS,
            }

        X = matrix(rows)
        model = bundle["model"]
        flags = model.predict(X) == -1
        scores = -model.decision_function(X)
    except Exception:
        logger.exception("health anomaly scoring failed")
        return unavailable("scoring_failed")

    reference = bundle["metadata"]["score_reference"]
    anomalies = []
    for row, flagged, score in zip(rows, flags, scores):
        if not flagged:
            continue
        severity = _severity(float(score), reference)
        anomalies.append(
            {
                "observation_id": row["observation_id"],
                "observation_date": row["observation_date"].isoformat(),
                "is_anomaly": True,
                "anomaly_score": round(float(score), 4),
                "severity": severity,
                "measurements_considered": row["available"],
                "reasons": _reasons(row),
                "evidence": row["evidence"],
                "model_version": bundle["metadata"]["model_version"],
            }
        )

    anomalies.sort(key=lambda a: -a["anomaly_score"])

    return {
        "available": True,
        "model_version": bundle["metadata"]["model_version"],
        "algorithm": bundle["metadata"]["algorithm"],
        "trained_on": bundle["metadata"]["dataset"]["source"],
        "observations_scored": len(rows),
        "observations_available": len(rows_in),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "score_scale": {
            "higher_is_more_unusual": True,
            "typical": reference.get(SEVERITY_MODERATE_PERCENTILE),
            "unusual": reference.get(SEVERITY_HIGH_PERCENTILE),
            "note": (
                "An anomaly score, not a probability. It measures distance from "
                "this dog's recent pattern, not the likelihood of any illness."
            ),
        },
        "disclaimer": (
            "Identifies unusual patterns in recorded observations for human review. "
            "It does not diagnose, and it is not veterinary advice."
        ),
    }
