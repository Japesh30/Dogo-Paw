"""Advance dogs_id_seq past the seeded rows (PostgreSQL only).

Revision ID: 0004_dog_id_sequence
Revises: 0003_health_alerts
Create Date: 2026-09-23

seed.py inserts the 18 dogs with explicit ids (1-18), which is how the source
dataset numbers them and what the API exposes as `dog_id`. PostgreSQL only
advances a SERIAL sequence when it supplies the value itself, so on every
Postgres database built this way `dogs_id_seq` is still at 1 while `max(id)` is
18. The first dog inserted *without* an explicit id therefore gets id 1 and
fails with a duplicate key — and the next 17 attempts fail the same way.

Nothing hits this today because no endpoint creates dogs, which is exactly why
it is worth fixing now rather than during whatever feature first adds one.

This migration only moves a sequence counter: it reads max(id) and sets the
sequence past it. No row is inserted, updated or deleted, and no schema
changes, so it is safe to run against a live database with real data.

SQLite has no sequences — its AUTOINCREMENT/rowid logic derives the next id
from the table itself — so there it is a deliberate no-op.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004_dog_id_sequence'
down_revision = '0003_health_alerts'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite: nothing to advance

    # setval(..., is_called=true) means "the next value handed out is this + 1".
    # COALESCE covers an empty dogs table, where the sequence should stay at 1.
    # GREATEST makes this forward-only: on a database whose sequence is already
    # ahead of MAX(id) — because rows were inserted normally and later deleted —
    # rewinding it to MAX(id) would hand out ids that those rows had used, and
    # any row still referencing them would collide. Moving a sequence backwards
    # is never the safe direction.
    bind.execute(sa.text("""
        SELECT setval(
            pg_get_serial_sequence('dogs', 'id'),
            GREATEST(
                COALESCE((SELECT MAX(id) FROM dogs), 1),
                (SELECT last_value FROM dogs_id_seq)
            ),
            true
        )
    """))


def downgrade():
    # Deliberately does nothing. Rewinding the sequence would reintroduce the
    # duplicate-key bug, and a sequence position is not schema worth reverting.
    pass
