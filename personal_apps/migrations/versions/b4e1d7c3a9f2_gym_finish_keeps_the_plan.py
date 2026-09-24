"""gym: a finished workout keeps its plan size and says when it ended itself

Revision ID: b4e1d7c3a9f2
Revises: a3c9e5f1b7d2
Create Date: 2026-09-24 18:00:00.000000

Finishing now deletes the sets that were never lifted (walkthrough D5,
G-080): they stayed in the database, invisible everywhere but the export.
What they said -- how big the workout was meant to be -- is kept as a
number, `planned_sets`, because the debrief's comparison leaves cut-short
workouts out of its baseline (D10) and could no longer tell one otherwise.
NULL on every workout finished before this.

`auto_finished` marks a workout the app ended itself, three hours after its
last set (D5 c-A): the debrief and Verlauf say so ("automatisch beendet").
`notes` is the lifter's own text and stays theirs.

Downgrade drops both. The deleted open sets are not restored by it; they
were never lifted.
"""
import sqlalchemy as sa
from alembic import op

revision = 'b4e1d7c3a9f2'
down_revision = 'a3c9e5f1b7d2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gym_workout_sessions',
                  sa.Column('planned_sets', sa.SmallInteger(), nullable=True))
    op.add_column('gym_workout_sessions',
                  sa.Column('auto_finished', sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade():
    op.drop_column('gym_workout_sessions', 'auto_finished')
    op.drop_column('gym_workout_sessions', 'planned_sets')
