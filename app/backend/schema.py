"""Bring the database schema up to date with Alembic, at startup.

Before migrations were adopted, `db.create_all()` built the schema. Databases
created that way (production Supabase, and every local SQLite file made before
this) have all the tables but no `alembic_version` row, so Alembic would think
they are empty and try to create everything again. `migrate_to_head()` handles
the three cases:

* Empty database: `upgrade` creates everything from the baseline onwards.
* Existing, unversioned database: every table and column the baseline
  describes is checked first. If they are all there, the baseline is
  *stamped*, which records the revision without running any DDL, and then
  `upgrade` applies anything newer. If something is missing the app refuses to
  start rather than guess, because stamping an incomplete schema would hide the
  gap for good.
* Versioned database: `upgrade` applies whatever is newer, or does nothing.

It runs inside seed_lock(), so on PostgreSQL only one gunicorn worker migrates
while the rest wait.
"""

from __future__ import annotations

from alembic.migration import MigrationContext
from flask_migrate import stamp, upgrade
from sqlalchemy import inspect

from models import db

BASELINE_REVISION = "0001_baseline"

# What 0001_baseline creates. Frozen here rather than read from models.py:
# models will gain tables and columns in later migrations, and those must not
# be required before the baseline can be stamped.
BASELINE_SCHEMA = {
    "users": {"id", "name", "email", "password_hash", "is_admin", "created_at"},
    "dogs": {
        "id", "name", "age", "energy_level", "size", "temperament",
        "medical_needs", "good_with_kids", "good_with_other_pets",
        "photo_url", "bio", "created_at",
    },
    "adopters": {
        "id", "user_id", "activity_level", "home_type", "experience_level",
        "has_kids", "has_other_pets", "created_at",
    },
    "chatbot_logs": {
        "id", "user_id", "question", "predicted_intent", "confidence",
        "low_confidence", "created_at",
    },
    "revoked_tokens": {"id", "jti", "expires_at", "revoked_at"},
    "volunteers": {
        "id", "name", "email", "mobile", "address", "state", "city",
        "submitted_at",
    },
    "match_requests": {
        "id", "user_id", "adopter_id", "top_dog_id", "top_score",
        "results_count", "created_at",
    },
}


def current_revision() -> str | None:
    with db.engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def baseline_gaps() -> list[str]:
    """Everything the baseline expects that this database does not have."""
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    gaps = []
    for table, columns in BASELINE_SCHEMA.items():
        if table not in tables:
            gaps.append(f"table {table}")
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        gaps.extend(f"column {table}.{name}" for name in sorted(columns - existing))
    return gaps


def migrate_to_head() -> None:
    if current_revision() is None:
        tables = set(inspect(db.engine).get_table_names())
        if tables & BASELINE_SCHEMA.keys():
            gaps = baseline_gaps()
            if gaps:
                raise RuntimeError(
                    "Database has tables from before migrations but does not "
                    f"match the baseline; missing: {', '.join(gaps)}. Not "
                    "stamping it. Fix the schema by hand, then restart."
                )
            stamp(revision=BASELINE_REVISION)
            print(f"stamped existing schema as {BASELINE_REVISION}")

    upgrade()
