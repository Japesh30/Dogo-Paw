"""Backfill a week of realistic match-request activity.

The dashboard is honest about an empty database — a single bar on the day you
first ran it — which is not much to look at during a demo. This replays real
recommendations through the real engine and writes real audit rows; nothing is
faked except the timestamps.

    python demo_data.py           # add ~40 requests spread over the last 7 days
    python demo_data.py --clear   # remove all activity and start clean
"""

from __future__ import annotations

import random
import sys
from datetime import timedelta

from models import Adopter, Dog, MatchRequest, User, Volunteer, db, utcnow
from recommender import AdopterProfile, DogProfile, recommend

ACTIVITY = ["low", "medium", "high"]
HOMES = ["apartment", "house_no_yard", "house_with_yard"]
EXPERIENCE = ["none", "some", "experienced"]

# Requests per day, oldest first — a plausible week with a weekend bump.
PER_DAY = [3, 5, 4, 6, 5, 9, 8]

# Volunteer sign-ups per day over the same window.
VOLUNTEERS_PER_DAY = [1, 0, 2, 1, 1, 3, 2]

VOLUNTEER_NAMES = [
    "Aditi Nair", "Rohan Kulkarni", "Sneha Iyer", "Vikram Desai",
    "Meera Joshi", "Arjun Pillai", "Kavya Reddy", "Nikhil Bose",
    "Farah Sheikh", "Tanvi Gokhale", "Imran Qureshi", "Divya Menon",
]

CITIES = [
    ("Mumbai", "Maharashtra"), ("Pune", "Maharashtra"),
    ("Bengaluru", "Karnataka"), ("Hyderabad", "Telangana"),
    ("Chennai", "Tamil Nadu"), ("Jaipur", "Rajasthan"),
]

STREETS = ["MG Road", "Hill Road", "Church Street", "Linking Road", "Park Lane"]


def clear() -> None:
    MatchRequest.query.delete()
    Adopter.query.delete()
    Volunteer.query.delete()
    db.session.commit()
    print("cleared all match requests, adopter profiles and volunteers")


def generate() -> None:
    rng = random.Random(42)  # deterministic, so re-running looks the same

    dogs = [
        DogProfile(
            dog_id=d.id,
            name=d.name,
            age=d.age,
            energy_level=d.energy_level,
            size=d.size,
            temperament=d.temperament,
            medical_needs=d.medical_needs,
            good_with_kids=d.good_with_kids,
            good_with_other_pets=d.good_with_other_pets,
        )
        for d in Dog.query.order_by(Dog.id).all()
    ]
    if not dogs:
        raise SystemExit("no dogs in the database — run seed.py first")

    users = User.query.filter_by(is_admin=False).all()
    today = utcnow().date()
    created = 0

    for day_offset, count in enumerate(PER_DAY):
        day = today - timedelta(days=6 - day_offset)
        for _ in range(count):
            # Roughly a third of visitors are signed in.
            user = rng.choice(users) if users and rng.random() < 0.35 else None
            stamp = utcnow().replace(
                year=day.year, month=day.month, day=day.day
            ) - timedelta(
                hours=rng.randint(0, 12),
                minutes=rng.randint(0, 59),
            )

            adopter = Adopter(
                user_id=user.id if user else None,
                activity_level=rng.choice(ACTIVITY),
                home_type=rng.choice(HOMES),
                experience_level=rng.choice(EXPERIENCE),
                has_kids=rng.random() < 0.4,
                has_other_pets=rng.random() < 0.45,
                created_at=stamp,
            )
            db.session.add(adopter)
            db.session.flush()

            results = recommend(
                dogs,
                AdopterProfile(
                    activity_level=adopter.activity_level,
                    home_type=adopter.home_type,
                    experience_level=adopter.experience_level,
                    has_kids=adopter.has_kids,
                    has_other_pets=adopter.has_other_pets,
                ),
            )
            top = results[0]

            db.session.add(
                MatchRequest(
                    user_id=adopter.user_id,
                    adopter_id=adopter.id,
                    top_dog_id=top.dog.dog_id,
                    top_score=top.score,
                    results_count=len(results),
                    created_at=stamp,
                )
            )
            created += 1

    # --- volunteer sign-ups over the same window ------------------------- #
    names = VOLUNTEER_NAMES.copy()
    rng.shuffle(names)
    volunteers = 0

    for day_offset, count in enumerate(VOLUNTEERS_PER_DAY):
        day = today - timedelta(days=6 - day_offset)
        for _ in range(count):
            if not names:
                break
            name = names.pop()
            city, state = rng.choice(CITIES)
            stamp = utcnow().replace(
                year=day.year, month=day.month, day=day.day
            ) - timedelta(hours=rng.randint(0, 12), minutes=rng.randint(0, 59))

            db.session.add(
                Volunteer(
                    name=name,
                    email=f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.com",
                    mobile=f"+91 9{rng.randint(1000000000, 9999999999) % 10**9:09d}",
                    address=f"{rng.randint(1, 120)} {rng.choice(STREETS)}",
                    state=state,
                    city=city,
                    submitted_at=stamp,
                )
            )
            volunteers += 1

    db.session.commit()
    print(
        f"created {created} match requests and {volunteers} volunteer sign-ups "
        "across the last 7 days"
    )


if __name__ == "__main__":
    from app import create_app

    with create_app().app_context():
        if "--clear" in sys.argv:
            clear()
        else:
            generate()
