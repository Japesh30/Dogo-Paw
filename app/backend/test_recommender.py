"""Sanity checks for the matching engine. Run with: python test_recommender.py"""

from __future__ import annotations

import math

from recommender import (
    KIDS_PENALTY,
    MAX_DISTANCE,
    OTHER_PETS_PENALTY,
    AdopterProfile,
    DogProfile,
    recommend,
    score_dog,
)
from seed import DOGS

# `photo_url` and `bio` live on the seed rows too, but the recommender takes
# neither, so only the scoring fields are lifted across.
SCORING_FIELDS = (
    "dog_id", "name", "age", "energy_level", "size", "temperament",
    "medical_needs", "good_with_kids", "good_with_other_pets",
)

ALL_DOGS = [
    DogProfile(**{f: row["id" if f == "dog_id" else f] for f in SCORING_FIELDS})
    for row in DOGS
]

failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    if condition:
        print(f"  PASS  {label}")
    else:
        failures += 1
        print(f"  FAIL  {label} {detail}")


print("scoring formula")

# Bruno: high energy, large, energetic -> vector [1.0, 1.0, 0.55]
bruno = next(d for d in ALL_DOGS if d.name == "Bruno")
perfect = AdopterProfile("high", "house_with_yard", "experienced", False, False)
res = score_dog(bruno, perfect)
check("active adopter + high-energy dog scores high", res.score > 70, f"got {res.score:.1f}")
check("no penalties applied", res.penalties == [])

worst = AdopterProfile("low", "apartment", "none", False, False)
res_worst = score_dog(bruno, worst)
check(
    "sedentary apartment adopter scores far lower",
    res_worst.score < res.score - 25,
    f"got {res_worst.score:.1f} vs {res.score:.1f}",
)

# The formula itself: score == (1 - d/sqrt(3)) * 100 when nothing is penalised.
expected = (1 - res.distance / MAX_DISTANCE) * 100
check("score matches (1 - d/sqrt(3)) * 100", math.isclose(res.score, expected, abs_tol=1e-9))
check("MAX_DISTANCE is sqrt(3)", math.isclose(MAX_DISTANCE, math.sqrt(3)))

print("\npenalty rules")

# Simba is good_with_kids=False, good_with_other_pets=False.
simba = next(d for d in ALL_DOGS if d.name == "Simba")
neutral = AdopterProfile("high", "house_with_yard", "experienced", False, False)
with_kids = AdopterProfile("high", "house_with_yard", "experienced", True, False)
with_pets = AdopterProfile("high", "house_with_yard", "experienced", False, True)
with_both = AdopterProfile("high", "house_with_yard", "experienced", True, True)

base = score_dog(simba, neutral).score
kids = score_dog(simba, with_kids)
pets = score_dog(simba, with_pets)
both = score_dog(simba, with_both)

check(
    "kids penalty is exactly 0.4x",
    math.isclose(kids.score, base * KIDS_PENALTY, abs_tol=1e-9),
    f"{kids.score:.2f} vs {base * KIDS_PENALTY:.2f}",
)
check(
    "other-pets penalty is exactly 0.5x",
    math.isclose(pets.score, base * OTHER_PETS_PENALTY, abs_tol=1e-9),
)
check(
    "both penalties stack multiplicatively",
    math.isclose(both.score, base * KIDS_PENALTY * OTHER_PETS_PENALTY, abs_tol=1e-9),
)
check("penalty is explained", len(both.penalties) == 2)

# A kid-friendly dog must not be penalised for the same adopter.
bella = next(d for d in ALL_DOGS if d.name == "Bella")
check("kid-friendly dog is not penalised", score_dog(bella, with_both).penalties == [])

print("\nranking")

family = AdopterProfile("medium", "house_with_yard", "some", True, True)
ranked = recommend(ALL_DOGS, family)

check("every dog is ranked", len(ranked) == len(ALL_DOGS))
check(
    "results are sorted descending",
    all(ranked[i].score >= ranked[i + 1].score for i in range(len(ranked) - 1)),
)
check("all scores are within 0-100", all(0 <= r.score <= 100 for r in ranked))
check(
    "no unsuitable dog tops the list for a family with kids and pets",
    ranked[0].dog.good_with_kids and ranked[0].dog.good_with_other_pets,
    f"top was {ranked[0].dog.name}",
)
check("top match has an explanation", len(ranked[0].reasons) > 0)
check("top_n truncates", len(recommend(ALL_DOGS, family, top_n=5)) == 5)

print(f"\ntop 5 for {family}:")
for r in ranked[:5]:
    print(f"  {r.score:5.1f}  {r.dog.name:8s} {', '.join(r.reasons)}")

print("\nbottom 3:")
for r in ranked[-3:]:
    note = r.penalties[0]["message"] if r.penalties else "-"
    print(f"  {r.score:5.1f}  {r.dog.name:8s} {note}")

print(f"\n{'ALL CHECKS PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}")
raise SystemExit(1 if failures else 0)
