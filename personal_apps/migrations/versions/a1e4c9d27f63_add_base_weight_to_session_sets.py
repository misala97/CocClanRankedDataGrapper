"""add base_weight to session sets

Revision ID: a1e4c9d27f63
Revises: f2a7c31d9b48
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1e4c9d27f63'
down_revision = 'f2a7c31d9b48'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable with no server_default: existing rows are not deloaded, and
    # NULL is exactly what "no baseline stored" means.
    op.add_column('gym_session_sets', sa.Column('base_weight', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('gym_session_sets', 'base_weight')
