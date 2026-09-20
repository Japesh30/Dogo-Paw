"""
Dogo-Paw adoption matching engine.

Content-based recommender. Both the dog and the adopter are projected into the
same normalised 3-D space:

    [energy, space, experience]        each component in [0.0, 1.0]

The dog vector states what the dog *requires*; the adopter vector states what
the adopter *offers*. The closer the two vectors, the better the fit, so the
raw score is the euclidean distance normalised by the length of the unit cube's
diagonal (sqrt(3)):

    score = (1 - distance / sqrt(3)) * 100

Two hard rules then apply as multipliers, because they are safety constraints
rather than preferences:

    * adopter has children  and the dog is not kid-friendly   -> x0.4
    * adopter has other pets and the dog is not pet-friendly  -> x0.5

The breakdown (raw distance, per-axis gaps, penalties, human-readable reasons)
is returned alongside the score so the UI can explain every match.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Length of the diagonal of the unit cube — the largest distance two profiles
# can be apart, used to normalise the score onto 0-100.
MAX_DISTANCE = math.sqrt(3)

# --------------------------------------------------------------------------- #
# Feature encodings
# --------------------------------------------------------------------------- #

# How much exercise/stimulation a dog demands.
ENERGY_SCALE = {"low": 0.0, "medium": 0.5, "high": 1.0}

# How much room a dog needs, inferred from its size.
SIZE_SPACE_SCALE = {"small": 0.0, "medium": 0.5, "large": 1.0}

# How much handling skill a temperament demands.
TEMPERAMENT_EXPERIENCE_SCALE = {
    "calm": 0.0,
    "friendly": 0.15,
    "gentle": 0.15,
    "playful": 0.4,
    "energetic": 0.55,
    "independent": 0.7,
    "shy": 0.8,
    "anxious": 0.85,
    "protective": 0.9,
    "stubborn": 0.9,
}

# What the adopter offers, on the same three axes.
ACTIVITY_SCALE = {"low": 0.0, "medium": 0.5, "high": 1.0}
HOME_SPACE_SCALE = {
    "apartment": 0.0,
    "house_no_yard": 0.5,
    "house_with_yard": 1.0,
}
EXPERIENCE_SCALE = {"none": 0.0, "some": 0.5, "experienced": 1.0}

# Rule-based penalty multipliers.
KIDS_PENALTY = 0.4
OTHER_PETS_PENALTY = 0.5

# A dog with ongoing medical needs asks more of its owner, so it nudges the
# required-experience axis upwards.
MEDICAL_EXPERIENCE_BUMP = 0.2

AXES = ("energy", "space", "experience")


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DogProfile:
    """A dog as the recommender sees it."""

    dog_id: int
    name: str
    age: float
    energy_level: str
    size: str
    temperament: str
    medical_needs: bool
    good_with_kids: bool
    good_with_other_pets: bool

    # Carried through purely so a result card can show the photo and link to
    # the dog's profile page. Scoring never reads it. Defaulted so the tests and
    # any hand-built profile stay valid without one.
    photo_url: str | None = None

    def to_vector(self) -> np.ndarray:
        energy = ENERGY_SCALE.get(self.energy_level.lower(), 0.5)
        space = SIZE_SPACE_SCALE.get(self.size.lower(), 0.5)
        experience = TEMPERAMENT_EXPERIENCE_SCALE.get(
            self.temperament.lower(), 0.5
        )
        if self.medical_needs:
            experience = min(1.0, experience + MEDICAL_EXPERIENCE_BUMP)
        return np.array([energy, space, experience], dtype=float)


@dataclass(frozen=True)
class AdopterProfile:
    """The five answers collected by the /adopt-match questionnaire."""

    activity_level: str
    home_type: str
    experience_level: str
    has_kids: bool
    has_other_pets: bool

    def to_vector(self) -> np.ndarray:
        return np.array(
            [
                ACTIVITY_SCALE.get(self.activity_level.lower(), 0.5),
                HOME_SPACE_SCALE.get(self.home_type.lower(), 0.5),
                EXPERIENCE_SCALE.get(self.experience_level.lower(), 0.5),
            ],
            dtype=float,
        )


@dataclass
class MatchResult:
    dog: DogProfile
    score: float
    base_score: float
    distance: float
    axis_gaps: dict[str, float]
    penalties: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dog_id": self.dog.dog_id,
            "name": self.dog.name,
            "age": self.dog.age,
            "energy_level": self.dog.energy_level,
            "size": self.dog.size,
            "temperament": self.dog.temperament,
            "medical_needs": self.dog.medical_needs,
            "good_with_kids": self.dog.good_with_kids,
            "good_with_other_pets": self.dog.good_with_other_pets,
            "photo_url": self.dog.photo_url,
            "score": round(self.score, 1),
            "breakdown": {
                "base_score": round(self.base_score, 1),
                "distance": round(self.distance, 4),
                "max_distance": round(MAX_DISTANCE, 4),
                "axis_gaps": {k: round(v, 3) for k, v in self.axis_gaps.items()},
                "penalties": self.penalties,
                "reasons": self.reasons,
                "concerns": self.concerns,
            },
        }


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

# Per-axis wording, keyed by how large the gap on that axis is.
_AXIS_LABELS = {
    "energy": ("Energy levels line up well", "Energy needs differ noticeably"),
    "space": ("Your space suits this dog", "Space is a tighter fit than ideal"),
    "experience": (
        "Well within your handling experience",
        "This dog asks for more handling experience",
    ),
}

_CLOSE_GAP = 0.25  # gap at or below this counts as a strength
_WIDE_GAP = 0.5  # gap above this counts as a concern


def score_dog(dog: DogProfile, adopter: AdopterProfile) -> MatchResult:
    """Score one dog against one adopter, with a full explanation."""
    dog_vec = dog.to_vector()
    adopter_vec = adopter.to_vector()

    distance = float(np.linalg.norm(dog_vec - adopter_vec))
    base_score = (1 - distance / MAX_DISTANCE) * 100

    axis_gaps = {
        axis: float(abs(dog_vec[i] - adopter_vec[i])) for i, axis in enumerate(AXES)
    }

    reasons: list[str] = []
    concerns: list[str] = []
    for axis, gap in axis_gaps.items():
        good, bad = _AXIS_LABELS[axis]
        if gap <= _CLOSE_GAP:
            reasons.append(good)
        elif gap > _WIDE_GAP:
            concerns.append(bad)

    # --- rule-based penalties -------------------------------------------- #
    penalties: list[dict] = []
    score = base_score

    if adopter.has_kids and not dog.good_with_kids:
        score *= KIDS_PENALTY
        penalties.append(
            {
                "rule": "kids",
                "multiplier": KIDS_PENALTY,
                "message": f"{dog.name} is not currently recommended for homes with children.",
            }
        )

    if adopter.has_other_pets and not dog.good_with_other_pets:
        score *= OTHER_PETS_PENALTY
        penalties.append(
            {
                "rule": "other_pets",
                "multiplier": OTHER_PETS_PENALTY,
                "message": f"{dog.name} does better as the only pet in the home.",
            }
        )

    # Positive confirmations, so a clean match reads as reassuring.
    if adopter.has_kids and dog.good_with_kids:
        reasons.append("Good with children")
    if adopter.has_other_pets and dog.good_with_other_pets:
        reasons.append("Good with other pets")
    if dog.medical_needs:
        concerns.append("Has ongoing medical needs")

    return MatchResult(
        dog=dog,
        score=max(0.0, min(100.0, score)),
        base_score=base_score,
        distance=distance,
        axis_gaps=axis_gaps,
        penalties=penalties,
        reasons=reasons,
        concerns=concerns,
    )


def recommend(
    dogs: list[DogProfile], adopter: AdopterProfile, top_n: int | None = None
) -> list[MatchResult]:
    """Rank every dog for this adopter, best match first."""
    results = [score_dog(dog, adopter) for dog in dogs]
    results.sort(key=lambda r: (-r.score, r.dog.name))
    return results[:top_n] if top_n else results
