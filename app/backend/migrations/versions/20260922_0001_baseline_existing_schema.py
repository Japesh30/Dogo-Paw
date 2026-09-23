"""Baseline: the schema as it stood before migrations were adopted.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-22

Exactly the seven tables `db.create_all()` built from models.py up to Phase 8,
including the later `dogs.photo_url` / `dogs.bio` columns and the current
`dogs.medical_needs` flag.

How it is applied depends on the database (see schema.py):

* Empty database   -> `upgrade` runs this and creates the tables.
* Existing database built by create_all(), i.e. production Supabase and older
  local SQLite files -> the tables are verified and the revision is *stamped*
  instead. This file's upgrade() never runs there, so it cannot collide with
  tables that already exist.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dogs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('age', sa.Float(), nullable=False),
    sa.Column('energy_level', sa.String(length=20), nullable=False),
    sa.Column('size', sa.String(length=20), nullable=False),
    sa.Column('temperament', sa.String(length=40), nullable=False),
    sa.Column('medical_needs', sa.Boolean(), nullable=False),
    sa.Column('good_with_kids', sa.Boolean(), nullable=False),
    sa.Column('good_with_other_pets', sa.Boolean(), nullable=False),
    sa.Column('photo_url', sa.String(length=255), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('revoked_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('jti', sa.String(length=36), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_revoked_tokens_expires_at'), 'revoked_tokens', ['expires_at'], unique=False)
    op.create_index(op.f('ix_revoked_tokens_jti'), 'revoked_tokens', ['jti'], unique=True)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('volunteers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('mobile', sa.String(length=32), nullable=False),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('state', sa.String(length=80), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_volunteers_email'), 'volunteers', ['email'], unique=False)
    op.create_index(op.f('ix_volunteers_submitted_at'), 'volunteers', ['submitted_at'], unique=False)
    op.create_table('adopters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('activity_level', sa.String(length=20), nullable=False),
    sa.Column('home_type', sa.String(length=30), nullable=False),
    sa.Column('experience_level', sa.String(length=20), nullable=False),
    sa.Column('has_kids', sa.Boolean(), nullable=False),
    sa.Column('has_other_pets', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('chatbot_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('predicted_intent', sa.String(length=40), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('low_confidence', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chatbot_logs_created_at'), 'chatbot_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_chatbot_logs_predicted_intent'), 'chatbot_logs', ['predicted_intent'], unique=False)
    op.create_table('match_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('adopter_id', sa.Integer(), nullable=False),
    sa.Column('top_dog_id', sa.Integer(), nullable=True),
    sa.Column('top_score', sa.Float(), nullable=True),
    sa.Column('results_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['adopter_id'], ['adopters.id'], ),
    sa.ForeignKeyConstraint(['top_dog_id'], ['dogs.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_match_requests_created_at'), 'match_requests', ['created_at'], unique=False)


def downgrade():
    # Undoing the baseline means dropping every table, including all users,
    # volunteers and match history. That is never a migration step; if it is
    # genuinely wanted locally, `python seed.py --reset` exists for it.
    raise RuntimeError(
        "Refusing to downgrade past the baseline: it would drop every table."
    )
