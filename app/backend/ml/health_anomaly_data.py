"""DEVELOPMENT / TRAINING DATA ONLY — synthetic health observations.

None of this is real. It is generated to train and evaluate the anomaly
detector, because the application holds only a handful of real observations
(the local demo fixture), which is far too few to learn from.

What that means, stated plainly and repeated in the model metadata and the
documentation: the model has learned what "unusual" looks like **in this
generator's idea of a dog's history**, not from veterinary records. It is a
reasonable prior for "this reading does not look like the recent ones", and
nothing more. It is never a clinical finding.

Scenarios are labelled so evaluation can ask a real question — are the
observations we deliberately made odd the ones the model scores as odd? Labels
are used **only for evaluation**. Training is unsupervised and never sees them.

Nothing here is written to any database. `medical_demo_data.py` is the separate,
local-only fixture for the app itself.

    python -m ml.health_anomaly_data --summary
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import numpy as np

# Every dog starts from a plausible adult weight and a normal temperature; the
# scenarios below move them around. Ranges are deliberately wide so the model
# does not learn one dog's size as "normal".
WEIGHT_RANGE = (4.0, 40.0)
TEMP_NORMAL = 38.5
TEMP_NOISE = 0.18          # °C, ordinary measurement variation
WEIGHT_NOISE_PCT = 0.9     # %, ordinary weighing variation (scales, full stomach)
TYPICAL_INTERVAL_DAYS = 21
OBSERVATIONS_PER_DOG = 12

# Scenario names, and whether the observations they mark are expected to be
# unusual. "normal" scenarios must stay quiet; the rest plant something.
SCENARIOS = {
    "stable": False,
    "gradual_weight_gain": False,   # slow and steady is normal ageing/recovery
    "gradual_weight_decline": True,
    "sudden_weight_drop": True,
    "isolated_temperature_spike": True,
    "repeated_abnormal_temperature": True,
    "irregular_observation_spacing": True,
}

NORMAL_SCENARIOS = [name for name, anomalous in SCENARIOS.items() if not anomalous]
ANOMALOUS_SCENARIOS = [name for name, anomalous in SCENARIOS.items() if anomalous]


def _series(rng, scenario: str) -> list[dict]:
    """One synthetic dog's observation history.

    Each observation carries `is_planted`: True where the generator
    deliberately made this reading unusual. That is the evaluation label, and
    the only thing it is ever used for.
    """
    start_weight = float(rng.uniform(*WEIGHT_RANGE))
    start_date = date(2026, 1, 1) + timedelta(days=int(rng.integers(0, 120)))

    weights, temps, dates, planted = [], [], [], []
    weight = start_weight
    day = start_date

    # Where the planted event begins, always late enough that a baseline exists.
    event_at = int(rng.integers(6, OBSERVATIONS_PER_DOG - 1))

    for index in range(OBSERVATIONS_PER_DOG):
        is_planted = False
        temperature = TEMP_NORMAL + float(rng.normal(0, TEMP_NOISE))

        # Advance to this observation's date first, so the gap belongs to the
        # row it precedes. Labelling the row before the silence would mark an
        # observation whose own interval feature is perfectly ordinary.
        if index > 0:
            gap = TYPICAL_INTERVAL_DAYS + int(rng.integers(-4, 5))
            if scenario == "irregular_observation_spacing" and index == event_at:
                gap = int(rng.integers(150, 240))  # a long unexplained silence
                is_planted = True
            day = day + timedelta(days=gap)

        if scenario == "gradual_weight_gain":
            weight *= 1 + rng.uniform(0.004, 0.012)

        elif scenario == "gradual_weight_decline" and index >= event_at - 3:
            # A persistent downward drift, which is the pattern that matters
            # clinically and the one a single-reading rule misses.
            weight *= 1 - rng.uniform(0.030, 0.055)
            is_planted = index >= event_at

        elif scenario == "sudden_weight_drop" and index == event_at:
            weight *= 1 - rng.uniform(0.09, 0.16)
            is_planted = True

        elif scenario == "isolated_temperature_spike" and index == event_at:
            temperature = TEMP_NORMAL + float(rng.uniform(1.4, 2.4))
            is_planted = True

        elif scenario == "repeated_abnormal_temperature" and index >= event_at:
            temperature = TEMP_NORMAL + float(rng.uniform(1.0, 1.8))
            is_planted = True

        weight *= 1 + float(rng.normal(0, WEIGHT_NOISE_PCT / 100))

        dates.append(day)
        weights.append(round(weight, 2))
        temps.append(round(temperature, 2))
        planted.append(is_planted)

    return [
        {
            "id": index,
            "observation_date": dates[index],
            "weight_kg": weights[index],
            "temperature_c": temps[index],
            "is_planted": planted[index],
            "scenario": scenario,
        }
        for index in range(OBSERVATIONS_PER_DOG)
    ]


def generate(n_dogs: int = 420, seed: int = 20260923) -> list[list[dict]]:
    """`n_dogs` synthetic histories, one list of observations each.

    Most are normal: an anomaly detector trained on a population that is
    mostly odd learns nothing. The mix here is roughly 70% normal.
    """
    rng = np.random.default_rng(seed)
    histories = []
    normal_seen = anomalous_seen = 0
    for index in range(n_dogs):
        # Each group cycles through its own scenarios with a separate counter.
        # Indexing both by the dog index would skip scenarios whenever the
        # list length shared a factor with the 10-dog pattern.
        if index % 10 < 7:
            scenario = NORMAL_SCENARIOS[normal_seen % len(NORMAL_SCENARIOS)]
            normal_seen += 1
        else:
            scenario = ANOMALOUS_SCENARIOS[anomalous_seen % len(ANOMALOUS_SCENARIOS)]
            anomalous_seen += 1
        histories.append(_series(rng, scenario))
    return histories


def split(histories: list[list[dict]], holdout: float = 0.3, seed: int = 20260923):
    """Separate dogs into training and evaluation sets.

    Split by dog, never by observation: rows from one dog share a baseline, so
    splitting rows would put a dog's history on both sides and flatter the
    evaluation.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(histories))
    cut = int(len(histories) * (1 - holdout))
    return (
        [histories[i] for i in order[:cut]],
        [histories[i] for i in order[cut:]],
    )


if __name__ == "__main__":
    histories = generate()
    counts: dict[str, int] = {}
    planted = 0
    for history in histories:
        counts[history[0]["scenario"]] = counts.get(history[0]["scenario"], 0) + 1
        planted += sum(1 for o in history if o["is_planted"])

    print("SYNTHETIC DEVELOPMENT DATA (not real medical records)")
    print(f"  dogs:         {len(histories)}")
    print(f"  observations: {sum(len(h) for h in histories)}")
    print(f"  planted odd:  {planted}")
    for name in sorted(counts):
        print(f"    {name:34} {counts[name]:4} dogs  "
              f"({'anomalous' if SCENARIOS[name] else 'normal'})")
    if "--summary" not in sys.argv:
        print("\nPass --summary for this output only.")
