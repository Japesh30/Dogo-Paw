"""Shared feature encoding.

Every model here reads adopters and dogs through this module, so "an adopter's
energy level" means the same number to the recommender, the success predictor
and the clustering. The 0-1 scales are the ones the recommender already uses —
they are imported rather than redefined, so the two can never drift apart.
"""

from __future__ import annotations

import numpy as np

from recommender import (
    ACTIVITY_SCALE,
    ENERGY_SCALE,
    EXPERIENCE_SCALE,
    HOME_SPACE_SCALE,
    MEDICAL_EXPERIENCE_BUMP,
    SIZE_SPACE_SCALE,
    TEMPERAMENT_EXPERIENCE_SCALE,
)

# Fixed order so a saved model and a live request always agree on column
# meaning. Never reorder this without retraining.
TEMPERAMENTS = sorted(TEMPERAMENT_EXPERIENCE_SCALE)

ADOPTER_FEATURES = [
    "adopter_activity",
    "adopter_space",
    "adopter_experience",
    "adopter_has_kids",
    "adopter_has_other_pets",
]

DOG_FEATURES = [
    "dog_energy",
    "dog_space",
    "dog_experience_required",
    "dog_medical_needs",
    "dog_good_with_kids",
    "dog_good_with_other_pets",
]

# The interaction terms. A raw pair of values does not say whether they match;
# the gap does, and it is what the rescue actually reasons about.
GAP_FEATURES = [
    "energy_gap",
    "space_gap",
    "experience_gap",
    "experience_shortfall",
    "kid_conflict",
    "pet_conflict",
]

ONEHOT_FEATURES = [f"temperament_{t}" for t in TEMPERAMENTS]

# Temperament is already encoded ordinally in `dog_experience_required` (via
# TEMPERAMENT_EXPERIENCE_SCALE), so the 10 one-hot columns are largely
# redundant. Measured on the 300-row training set they cost ~1.7 points of
# cross-validated accuracy — 67.3% with them, 69.0% without — because they add
# variance without adding signal. Off by default; flip the flag to reproduce.
INCLUDE_TEMPERAMENT_ONEHOT = False


def feature_names(include_onehot: bool = INCLUDE_TEMPERAMENT_ONEHOT) -> list[str]:
    names = ADOPTER_FEATURES + DOG_FEATURES + GAP_FEATURES
    return names + ONEHOT_FEATURES if include_onehot else names


FEATURE_NAMES = feature_names()


def adopter_vector(adopter: dict) -> np.ndarray:
    """The 5 numbers describing what an adopter offers."""
    return np.array(
        [
            ACTIVITY_SCALE.get(str(adopter["activity_level"]).lower(), 0.5),
            HOME_SPACE_SCALE.get(str(adopter["home_type"]).lower(), 0.5),
            EXPERIENCE_SCALE.get(str(adopter["experience_level"]).lower(), 0.5),
            float(bool(adopter["has_kids"])),
            float(bool(adopter["has_other_pets"])),
        ],
        dtype=float,
    )


def dog_vector(dog: dict) -> np.ndarray:
    """The 6 numbers describing what a dog requires/offers."""
    experience = TEMPERAMENT_EXPERIENCE_SCALE.get(
        str(dog["temperament"]).lower(), 0.5
    )
    if dog["medical_needs"]:
        experience = min(1.0, experience + MEDICAL_EXPERIENCE_BUMP)

    return np.array(
        [
            ENERGY_SCALE.get(str(dog["energy_level"]).lower(), 0.5),
            SIZE_SPACE_SCALE.get(str(dog["size"]).lower(), 0.5),
            experience,
            float(bool(dog["medical_needs"])),
            float(bool(dog["good_with_kids"])),
            float(bool(dog["good_with_other_pets"])),
        ],
        dtype=float,
    )


def pair_features(
    adopter: dict, dog: dict, include_onehot: bool = INCLUDE_TEMPERAMENT_ONEHOT
) -> np.ndarray:
    """One row for the success model: adopter + dog + how well they fit."""
    a = adopter_vector(adopter)
    d = dog_vector(dog)

    energy_gap = abs(a[0] - d[0])
    space_gap = abs(a[1] - d[1])
    experience_gap = abs(a[2] - d[2])
    # Signed, not absolute: an adopter with *more* experience than the dog needs
    # is not a risk, but one with less is.
    experience_shortfall = max(0.0, d[2] - a[2])

    kid_conflict = float(a[3] == 1.0 and d[4] == 0.0)
    pet_conflict = float(a[4] == 1.0 and d[5] == 0.0)

    parts = [
        a,
        d,
        [
            energy_gap,
            space_gap,
            experience_gap,
            experience_shortfall,
            kid_conflict,
            pet_conflict,
        ],
    ]

    if include_onehot:
        temperament = str(dog["temperament"]).lower()
        parts.append([1.0 if t == temperament else 0.0 for t in TEMPERAMENTS])

    return np.concatenate(parts)


def clustering_vector(adopter: dict) -> np.ndarray:
    """Adopters only — what k-means groups on."""
    return adopter_vector(adopter)
