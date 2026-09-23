"""Features for longitudinal health-observation anomaly detection.

One feature row per observation, describing that observation *relative to the
history before it*. A weight of 30 kg means nothing on its own — for a small
dog it is alarming, for a large one routine. What carries signal is how a
reading compares with what that dog has been doing.

Strictly causal: a row for observation i is built only from observations
0..i-1 plus i itself. Nothing later is ever read, so a feature row is the same
whether it is computed today or recomputed in a year with more history after
it. test_health_anomaly.py checks this by recomputing prefixes.

Missing data is not filled in. A dog without enough history, or a reading with
no weight, yields no feature row for the affected measurements rather than a
zero — a fabricated zero would read as "no change", which is a different claim
from "unknown".
"""

from __future__ import annotations

import numpy as np

# Readings used to form the rolling baseline an observation is compared against.
# Three is the smallest window with a meaningful spread; more would make the
# model blind until a dog had a long history.
BASELINE_WINDOW = 5
MIN_BASELINE = 3

# Rows needed before a dog can be scored at all: MIN_BASELINE prior readings
# plus the one being scored.
MIN_OBSERVATIONS = MIN_BASELINE + 1

# Guards against dividing by a near-zero spread when a dog's readings have been
# identical, which would send a deviation to infinity.
MIN_STD_WEIGHT = 0.15   # kg
MIN_STD_TEMP = 0.10     # °C

FEATURE_NAMES = [
    "weight_pct_change",        # % change from the previous weight
    "weight_dev_from_baseline", # % away from the rolling mean
    "weight_z",                 # deviation in rolling standard deviations
    "weight_slope_pct",         # % change per day since the previous weight
    "temp_change",              # °C change from the previous temperature
    "temp_dev_from_baseline",   # °C away from the rolling mean
    "temp_z",                   # deviation in rolling standard deviations
    "days_since_previous",      # gap to the previous observation
    "interval_ratio",           # that gap against the dog's usual gap
]


def _as_row(observation) -> dict:
    """Accept either an ORM row or a plain dict, so the trainer can use
    generated data and the service can use database rows."""
    if isinstance(observation, dict):
        return observation
    return {
        "id": getattr(observation, "id", None),
        "observation_date": observation.observation_date,
        "weight_kg": observation.weight_kg,
        "temperature_c": observation.temperature_c,
    }


def _days(later, earlier) -> int:
    return (later - earlier).days


def _stats(values: list[float], floor: float) -> tuple[float, float]:
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return mean, max(std, floor)


def sort_observations(observations) -> list[dict]:
    """Oldest first. Ties broken by id so the order is total and stable."""
    rows = [_as_row(o) for o in observations]
    return sorted(rows, key=lambda r: (r["observation_date"], r.get("id") or 0))


def feature_row(history: list[dict], current: dict) -> dict | None:
    """Features for `current` given everything recorded before it.

    Returns None when there is not enough history, or when neither measurement
    can be compared — there is nothing to say, and saying it with zeros would
    be a lie.
    """
    if len(history) < MIN_BASELINE:
        return None

    values: dict[str, float] = {}
    reasons: dict[str, dict] = {}

    # --- weight -----------------------------------------------------------
    weights = [h for h in history if h.get("weight_kg") is not None]
    if current.get("weight_kg") is not None and len(weights) >= MIN_BASELINE:
        window = weights[-BASELINE_WINDOW:]
        series = [w["weight_kg"] for w in window]
        mean, std = _stats(series, MIN_STD_WEIGHT)
        previous = weights[-1]
        weight = current["weight_kg"]

        pct = (weight - previous["weight_kg"]) / previous["weight_kg"] * 100
        gap = max(_days(current["observation_date"], previous["observation_date"]), 1)
        values["weight_pct_change"] = pct
        values["weight_dev_from_baseline"] = (weight - mean) / mean * 100
        values["weight_z"] = (weight - mean) / std
        values["weight_slope_pct"] = pct / gap
        reasons["weight"] = {
            "current_kg": round(weight, 2),
            "previous_kg": round(previous["weight_kg"], 2),
            "previous_date": previous["observation_date"].isoformat(),
            "baseline_mean_kg": round(mean, 2),
            "baseline_std_kg": round(std, 2),
            "baseline_readings": len(window),
            "percent_change": round(pct, 1),
            "percent_from_baseline": round(values["weight_dev_from_baseline"], 1),
            "z_score": round(values["weight_z"], 2),
            "days_since_previous_weight": gap,
        }

    # --- temperature ------------------------------------------------------
    temps = [h for h in history if h.get("temperature_c") is not None]
    if current.get("temperature_c") is not None and len(temps) >= MIN_BASELINE:
        window = temps[-BASELINE_WINDOW:]
        series = [t["temperature_c"] for t in window]
        mean, std = _stats(series, MIN_STD_TEMP)
        previous = temps[-1]
        temp = current["temperature_c"]

        values["temp_change"] = temp - previous["temperature_c"]
        values["temp_dev_from_baseline"] = temp - mean
        values["temp_z"] = (temp - mean) / std
        reasons["temperature"] = {
            "current_c": round(temp, 2),
            "previous_c": round(previous["temperature_c"], 2),
            "previous_date": previous["observation_date"].isoformat(),
            "baseline_mean_c": round(mean, 2),
            "baseline_std_c": round(std, 2),
            "baseline_readings": len(window),
            "change_c": round(values["temp_change"], 2),
            "difference_from_baseline_c": round(values["temp_dev_from_baseline"], 2),
            "z_score": round(values["temp_z"], 2),
        }

    if not values:
        return None

    # --- cadence ----------------------------------------------------------
    # How often a dog is checked is itself a signal: a long silence, or a
    # sudden burst of checks, is a change in how it is being looked after.
    previous = history[-1]
    gap = _days(current["observation_date"], previous["observation_date"])
    gaps = [
        _days(b["observation_date"], a["observation_date"])
        for a, b in zip(history, history[1:])
    ]
    typical = float(np.median(gaps)) if gaps else float(gap)
    values["days_since_previous"] = float(gap)
    values["interval_ratio"] = gap / typical if typical > 0 else 1.0
    reasons["cadence"] = {
        "days_since_previous": gap,
        "usual_interval_days": round(typical, 1),
        "interval_ratio": round(values["interval_ratio"], 2),
    }

    # Anything not measured stays absent from `values` and is filled with the
    # neutral value below — "no evidence of change", which is what an unknown
    # comparison should contribute. Which parts were real is recorded in
    # `available`, and the service only ever explains those.
    vector = [float(values.get(name, NEUTRAL[name])) for name in FEATURE_NAMES]

    return {
        "observation_id": current.get("id"),
        "observation_date": current["observation_date"],
        "features": np.array(vector, dtype=float),
        "values": {k: round(v, 4) for k, v in values.items()},
        "evidence": reasons,
        "available": sorted(reasons),
        "history_length": len(history),
    }


# The value that means "nothing unusual" for each feature, used only where a
# measurement is absent. Chosen so a missing comparison pulls the row towards
# ordinary rather than towards an extreme.
NEUTRAL = {
    "weight_pct_change": 0.0,
    "weight_dev_from_baseline": 0.0,
    "weight_z": 0.0,
    "weight_slope_pct": 0.0,
    "temp_change": 0.0,
    "temp_dev_from_baseline": 0.0,
    "temp_z": 0.0,
    "days_since_previous": 30.0,
    "interval_ratio": 1.0,
}


def build_rows(observations) -> list[dict]:
    """Feature rows for one dog's observations, oldest first.

    Each row sees only what came before it, so this is the same function used
    at training time and at inference time.
    """
    ordered = sort_observations(observations)
    rows = []
    for index, current in enumerate(ordered):
        row = feature_row(ordered[:index], current)
        if row is not None:
            rows.append(row)
    return rows


def matrix(rows: list[dict]) -> np.ndarray:
    """Feature rows stacked for scikit-learn, in FEATURE_NAMES order."""
    if not rows:
        return np.empty((0, len(FEATURE_NAMES)), dtype=float)
    return np.vstack([r["features"] for r in rows])
