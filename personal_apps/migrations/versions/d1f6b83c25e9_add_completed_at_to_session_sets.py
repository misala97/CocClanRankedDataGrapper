"""add completed_at to session sets

Revision ID: d1f6b83c25e9
Revises: c8e5f14a9b32
Create Date: 2026-08-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f6b83c25e9'
down_revision = 'c8e5f14a9b32'
branch_labels = None
depends_on = None


def upgrade():
    # No backfill. rest_ends_at is a countdown target, not a record of when a
    # set landed, so deriving history from it would invent data. Every existing
    # set keeps NULL and the readouts stay silent until real sessions arrive.
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.drop_column('completed_at')
