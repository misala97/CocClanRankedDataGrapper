"""add bodyweight, notes and the pain flag to workouts

Revision ID: b2d5f9c31a42
Revises: a1c4e8b20f31
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2d5f9c31a42'
down_revision = 'a1c4e8b20f31'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gym_workout_sessions', sa.Column('bodyweight_kg', sa.Float(), nullable=True))
    op.add_column('gym_workout_sessions', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('gym_session_exercises', sa.Column('notes', sa.Text(), nullable=True))
    # server_default: NOT NULL against a table with rows.
    op.add_column('gym_session_exercises',
                  sa.Column('pain', sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade():
    op.drop_column('gym_session_exercises', 'pain')
    op.drop_column('gym_session_exercises', 'notes')
    op.drop_column('gym_workout_sessions', 'notes')
    op.drop_column('gym_workout_sessions', 'bodyweight_kg')
