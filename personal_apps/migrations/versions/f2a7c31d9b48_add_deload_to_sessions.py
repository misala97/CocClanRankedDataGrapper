"""add deload flag and percentage to workout sessions

Revision ID: f2a7c31d9b48
Revises: 9c3e5a71f2b6
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a7c31d9b48'
down_revision = '9c3e5a71f2b6'
branch_labels = None
depends_on = None


def upgrade():
    # server_default is required: the column is NOT NULL and the table has
    # existing rows, which would otherwise fail the ALTER.
    op.add_column('gym_workout_sessions',
                  sa.Column('is_deload', sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.add_column('gym_workout_sessions',
                  sa.Column('deload_pct', sa.SmallInteger(), nullable=True))


def downgrade():
    op.drop_column('gym_workout_sessions', 'deload_pct')
    op.drop_column('gym_workout_sessions', 'is_deload')
