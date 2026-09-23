"""Seed data: the 18-dog synthetic dataset plus a default admin account.

Run directly to (re)populate an empty database:

    python seed.py            # only seeds if the tables are empty
    python seed.py --reset    # drops everything and starts over

`photo` points at a file produced by the frontend's
`npm run build:dog-photos`, which crops the site's own rescue photographs into
one image per dog. The dogs themselves are synthetic, so these are stand-ins
grouped by build, not portraits of the individual animals — see app/README.md.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from models import Dog, User, db
from schema import migrate_to_head

IS_PRODUCTION = os.environ.get("APP_ENV", "development").strip().lower() == "production"

DOGS = [
    {
        "id": 1,
        "name": "Bruno",
        "age": 3.0,
        "energy_level": "high",
        "size": "large",
        "temperament": "energetic",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Bruno is a big, bouncing three-year-old who treats every walk like "
            "the best thing that has ever happened to him. He is brilliant with "
            "children and other dogs, and he will happily wear out anyone who "
            "runs, hikes or cycles. A quiet flat would break his heart."
        ),
    },
    {
        "id": 2,
        "name": "Tommy",
        "age": 1.5,
        "energy_level": "high",
        "size": "medium",
        "temperament": "playful",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Tommy is eighteen months of pure play — a tennis ball, a rolled-up "
            "sock, your shoelaces, it all counts. He learns fast when there is "
            "a treat involved and has never met a person or a dog he did not "
            "want to greet. He still needs someone to teach him that the "
            "kitchen counter is not his."
        ),
    },
    {
        "id": 3,
        "name": "Luna",
        "age": 5.0,
        "energy_level": "low",
        "size": "small",
        "temperament": "calm",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Luna is the easiest dog in our care. Five years old, small, "
            "unbothered by noise or visitors, and content with two short walks "
            "and a sunny patch of floor. She is a genuinely good first dog, and "
            "she suits a flat as well as a house."
        ),
    },
    {
        "id": 4,
        "name": "Rocky",
        "age": 7.0,
        "energy_level": "low",
        "size": "large",
        "temperament": "independent",
        "medical_needs": True,
        "good_with_kids": False,
        "good_with_other_pets": False,
        "bio": (
            "Rocky is a seven-year-old who has clearly had to look after "
            "himself, and he would rather be near you than on you. He needs an "
            "adults-only home with no other animals, and he is on ongoing "
            "medication that his adopter will need to keep up. For the right "
            "experienced person he is calm, undemanding company."
        ),
    },
    {
        "id": 5,
        "name": "Bella",
        "age": 2.0,
        "energy_level": "medium",
        "size": "medium",
        "temperament": "friendly",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Bella greets everyone — the postman, the neighbours, the other "
            "dogs at the park — as though she has been waiting for them all "
            "day. At two she is past the worst of the chewing and settles well "
            "indoors after a decent walk. She would slot into almost any home."
        ),
    },
    {
        "id": 6,
        "name": "Simba",
        "age": 4.0,
        "energy_level": "high",
        "size": "large",
        "temperament": "protective",
        "medical_needs": False,
        "good_with_kids": False,
        "good_with_other_pets": False,
        "bio": (
            "Simba is a strong, watchful four-year-old who bonds hard to one or "
            "two people and is wary of everyone else. He needs an experienced "
            "handler, a secure garden, and a home with no children and no other "
            "pets. Given structure and a job to do, he is loyal to a fault."
        ),
    },
    {
        "id": 7,
        "name": "Coco",
        "age": 0.8,
        "energy_level": "high",
        "size": "small",
        "temperament": "playful",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Coco is ten months old and still very much a puppy — small enough "
            "for a flat, loud enough to fill it. She adores children and other "
            "dogs and has not yet worked out that she is not one of the big "
            "ones. Expect training classes and a lot of laughing."
        ),
    },
    {
        "id": 8,
        "name": "Max",
        "age": 6.0,
        "energy_level": "medium",
        "size": "large",
        "temperament": "calm",
        "medical_needs": True,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Max is a steady six-year-old who has been gentle with every child "
            "and every animal his foster family has introduced him to. He does "
            "need daily medication and regular check-ups, which puts some "
            "adopters off — everything else about him is straightforward."
        ),
    },
    {
        "id": 9,
        "name": "Daisy",
        "age": 3.5,
        "energy_level": "low",
        "size": "small",
        "temperament": "shy",
        "medical_needs": False,
        "good_with_kids": False,
        "good_with_other_pets": True,
        "bio": (
            "Daisy came to us frightened of almost everything and has spent "
            "months learning that hands are kind. She is fine with other dogs, "
            "who give her confidence, but sudden noise and quick movement set "
            "her back, so we are only placing her in a home without children. "
            "Her progress with a patient adopter is worth the wait."
        ),
    },
    {
        "id": 10,
        "name": "Zoe",
        "age": 2.5,
        "energy_level": "medium",
        "size": "medium",
        "temperament": "gentle",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Zoe is soft-natured and careful, the sort of dog who sits down "
            "next to a toddler rather than jumping at one. She walks nicely on "
            "a lead, shares happily with other pets and asks for one proper "
            "outing a day. An easy dog for a busy family."
        ),
    },
    {
        "id": 11,
        "name": "Rex",
        "age": 5.5,
        "energy_level": "high",
        "size": "large",
        "temperament": "stubborn",
        "medical_needs": False,
        "good_with_kids": False,
        "good_with_other_pets": False,
        "bio": (
            "Rex knows exactly what you are asking and will decide for himself "
            "whether to do it. He is powerful, clever and easily bored, which "
            "is a difficult combination in the wrong home — he needs an "
            "experienced owner, no children and no other animals. With clear, "
            "consistent handling he is superb."
        ),
    },
    {
        "id": 12,
        "name": "Milo",
        "age": 1.0,
        "energy_level": "high",
        "size": "medium",
        "temperament": "energetic",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": False,
        "bio": (
            "Milo is a year old and has one speed. He is friendly with people "
            "of every age, but he chases anything smaller than him, so he needs "
            "to be the only pet. Give him a garden, a long walk and something "
            "to chew and he is a delight."
        ),
    },
    {
        "id": 13,
        "name": "Nala",
        "age": 8.0,
        "energy_level": "low",
        "size": "medium",
        "temperament": "calm",
        "medical_needs": True,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Nala is our eight-year-old and the calmest dog on this page. She "
            "gets on with children, cats and other dogs, sleeps most of the "
            "afternoon, and asks only for a gentle stroll. She has an ongoing "
            "joint condition that needs medication, and she deserves a quiet "
            "sofa for the years she has left."
        ),
    },
    {
        "id": 14,
        "name": "Buddy",
        "age": 4.5,
        "energy_level": "medium",
        "size": "large",
        "temperament": "friendly",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Buddy is a large, uncomplicated four-year-old who is good with "
            "absolutely everyone. He has lived with children, a cat and another "
            "dog in his foster home without a single problem. He needs a walk "
            "worth the name each day, and then he will lie down and let the "
            "house get on with itself."
        ),
    },
    {
        "id": 15,
        "name": "Pixie",
        "age": 2.0,
        "energy_level": "medium",
        "size": "small",
        "temperament": "anxious",
        "medical_needs": True,
        "good_with_kids": False,
        "good_with_other_pets": True,
        "bio": (
            "Pixie is small, sweet and worried about a great deal. She takes "
            "comfort from other dogs and would do best in a home that already "
            "has one, without young children to startle her. She is on "
            "medication for a skin condition and needs an adopter willing to "
            "move at her pace."
        ),
    },
    {
        "id": 16,
        "name": "Shadow",
        "age": 6.5,
        "energy_level": "low",
        "size": "large",
        "temperament": "independent",
        "medical_needs": False,
        "good_with_kids": False,
        "good_with_other_pets": True,
        "bio": (
            "Shadow is a quiet, self-contained six-year-old who will pick his "
            "own corner of the room and be perfectly happy there. He tolerates "
            "other dogs well but has no patience for being grabbed at, so we "
            "are placing him in a home without young children. He needs very "
            "little exercise and almost no fuss."
        ),
    },
    {
        "id": 17,
        "name": "Ginger",
        "age": 3.0,
        "energy_level": "medium",
        "size": "small",
        "temperament": "playful",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Ginger is three, small and endlessly game — she will play fetch "
            "until your arm gives out and then ask once more. She is gentle "
            "with children and sociable with other dogs and cats. A flat suits "
            "her fine as long as she gets out properly once a day."
        ),
    },
    {
        "id": 18,
        "name": "Thor",
        "age": 1.8,
        "energy_level": "high",
        "size": "large",
        "temperament": "energetic",
        "medical_needs": False,
        "good_with_kids": True,
        "good_with_other_pets": True,
        "bio": (
            "Thor is a not-quite-two-year-old in a very large body, which means "
            "he knocks things over without meaning to. He is affectionate with "
            "children and plays beautifully with other dogs, and he is clever "
            "enough to be worth training properly. He needs space, exercise and "
            "someone who finds all this funny."
        ),
    },
]

# Photos are generated per dog by app/frontend/scripts/build-dog-photos.mjs and
# served from the frontend's public folder, so the path is site-relative.
for _dog in DOGS:
    _dog["photo_url"] = f"/dogs/dog-{_dog['id']:02d}.jpg"

ADMIN_EMAIL = "admin@dogo-paw.org"
DEMO_EMAIL = "demo@dogo-paw.org"

# Development-only passwords. They are in the repository on purpose — they are
# convenience credentials for a local database that contains nothing but seed
# data, and `default_users()` refuses to use them when APP_ENV=production.
DEV_ADMIN_PASSWORD = "admin123"
DEV_DEMO_PASSWORD = "demo123"


def default_users() -> list[tuple[str, str, str, bool]]:
    """The accounts to seed, as (name, email, password, is_admin).

    The admin password comes from ADMIN_PASSWORD in production and startup fails
    without it. Shipping a known admin password to a public deployment would
    mean anyone who has seen this repository — or the old login page, which
    printed it — could sign in and read every volunteer's name, email, phone
    number and home address.

    The demo adopter is a development convenience and is not created in
    production at all. It holds no data and grants no privilege, but a public
    account with a published password is still a free foothold for spam, and
    nothing in the deployed site needs it.
    """
    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()

    if IS_PRODUCTION:
        if not admin_password:
            raise RuntimeError(
                "ADMIN_PASSWORD must be set when APP_ENV=production, so the "
                "seeded admin account does not ship with a known password."
            )
        if len(admin_password) < 12:
            raise RuntimeError(
                "ADMIN_PASSWORD must be at least 12 characters in production."
            )
        return [("Admin", ADMIN_EMAIL, admin_password, True)]

    return [
        ("Admin", ADMIN_EMAIL, admin_password or DEV_ADMIN_PASSWORD, True),
        ("Demo Adopter", DEMO_EMAIL, DEV_DEMO_PASSWORD, False),
    ]

# Columns added after the first databases were created, and the SQLite type to
# add them with.
LATER_COLUMNS = {"photo_url": "VARCHAR(255)", "bio": "TEXT"}


def ensure_columns() -> None:
    """Add any column that `dogs` is missing.

    Kept for databases older than migrations: create_all(), which built them,
    never touched an existing table, so a database created before Phase 6 has no `photo_url` or
    `bio` and every query against `dogs` fails. SQLite has no
    `ADD COLUMN IF NOT EXISTS`, so check first, then patch — that keeps existing
    users, volunteers and match history rather than dropping the file.
    """
    inspector = inspect(db.engine)
    if "dogs" not in inspector.get_table_names():
        return  # brand-new database; the baseline migration will build it

    existing = {column["name"] for column in inspector.get_columns("dogs")}
    added = [name for name in LATER_COLUMNS if name not in existing]
    for name in added:
        db.session.execute(text(f"ALTER TABLE dogs ADD COLUMN {name} {LATER_COLUMNS[name]}"))
    if added:
        db.session.commit()
        print(f"migrated dogs: added {', '.join(added)}")


SEED_LOCK_KEY = 4207311  # arbitrary but fixed; only this app uses it


@contextmanager
def seed_lock():
    """Serialise seeding across processes, on PostgreSQL only.

    `create_all()` checks for a table and then creates it, and the seed inserts
    check for a row and then insert it. Both are check-then-act, which is safe
    with one process and a local file, and unsafe the moment a hosted app boots
    several gunicorn workers against one database at the same time: two workers
    can both see "no table" and both try to create it, and the loser crashes the
    deploy with "relation already exists" or a duplicate key.

    A Postgres advisory lock is the smallest fix. It is just a named lock the
    database holds for us; the first worker in does the work while the others
    wait, then find everything already done and no-op. It touches no table and
    needs no migration tool.

    SQLite gets a plain no-op: one process, one file, nothing to serialise.
    """
    if not db.engine.dialect.name.startswith("postgresql"):
        yield
        return

    connection = db.engine.connect()
    try:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": SEED_LOCK_KEY})
        connection.commit()
        yield
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SEED_LOCK_KEY})
        connection.commit()
        connection.close()


def seed(force: bool = False) -> None:
    with seed_lock():
        _seed(force)



def sync_dog_id_sequence() -> None:
    """Advance dogs_id_seq past the seeded ids (PostgreSQL only).

    The rows above carry explicit ids, because the dataset numbers the dogs and
    the API exposes those numbers as `dog_id`. PostgreSQL only advances a
    SERIAL sequence when it generates the value itself, so after seeding, the
    sequence still points at 1 while the table holds 1-18 — and the first dog
    inserted without an explicit id fails on a duplicate key.

    Migration 0004_dog_id_sequence fixes databases that were already seeded,
    but migrations run *before* seeding inserts anything, so a freshly created
    database needs the same correction afterwards. Both are needed: neither
    covers the other's case. This runs on every start and only ever moves the
    sequence forward, so it is also self-healing and safe to repeat.

    SQLite has no sequences and needs nothing.
    """
    if db.engine.dialect.name != "postgresql":
        return
    # GREATEST(...) so this only ever moves the sequence forward. Rewinding a
    # sequence that is legitimately ahead would hand out ids that already exist.
    db.session.execute(text("""
        SELECT setval(
            pg_get_serial_sequence('dogs', 'id'),
            GREATEST(
                (SELECT COALESCE(MAX(id), 1) FROM dogs),
                (SELECT last_value FROM dogs_id_seq)
            ),
            true
        )
    """))
    db.session.commit()


def _seed(force: bool = False) -> None:
    if force:
        db.drop_all()
        # drop_all() only knows the model tables. Left behind, the version row
        # would tell Alembic the now-empty database is already up to date.
        db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()

    # ensure_columns() first: a database from before Phase 6 lacks photo_url
    # and bio, and must have them before it can be stamped as the baseline.
    ensure_columns()
    migrate_to_head()

    if Dog.query.first() is None:
        for row in DOGS:
            db.session.add(Dog(**row))
        db.session.commit()
        print(f"seeded {len(DOGS)} dogs")
    else:
        # The profile text and photos are seed-owned content, not user data, so
        # they are re-synced on every start. That is what backfills the rows in
        # a database that existed before these columns did.
        by_id = {row["id"]: row for row in DOGS}
        updated = 0
        for dog in Dog.query.all():
            row = by_id.get(dog.id)
            if row is None:
                continue
            if dog.photo_url != row["photo_url"] or dog.bio != row["bio"]:
                dog.photo_url = row["photo_url"]
                dog.bio = row["bio"]
                updated += 1
        if updated:
            print(f"refreshed photo/bio on {updated} dogs")

    # Whichever branch ran, leave the id sequence correct. Cheap, idempotent,
    # forward-only, and it heals a database seeded before this existed.
    sync_dog_id_sequence()

    for name, email, password, is_admin in default_users():
        if User.query.filter_by(email=email).first() is None:
            db.session.add(
                User(
                    name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                    is_admin=is_admin,
                )
            )
            # The email only — never the password, which would put the admin
            # credential straight into the host's log output.
            print(f"seeded user {email}")

    db.session.commit()


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        seed(force="--reset" in sys.argv)
    print("done")
