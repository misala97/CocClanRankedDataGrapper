"""gym: a routine's rows carry the plan -- how many sets, in which rep range

Revision ID: c5f2a8d4e1b7
Revises: b4e1d7c3a9f2
Create Date: 2026-09-24 21:00:00.000000

Walkthrough D2 P1 (G-050, G-051, G-035): a routine said which exercises, in
which order, and nothing else, so each start copied the set count of ONE
earlier workout -- and one short test workout shrank the routine for good.
Each row now stores its set count and its rep range. They are filled from
the lifter's history the first time the routine is started after this, and
from then on only an explicit edit changes them.

All three are NULL until then: a routine not started since keeps today's
rule, and so does a workout already running when this lands.

Downgrade drops the three columns; the next start derives the plan the old
way again.
"""
import sqlalchemy as sa
from alembic import op

revision = 'c5f2a8d4e1b7'
down_revision = 'b4e1d7c3a9f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gym_template_exercises',
                  sa.Column('target_sets', sa.SmallInteger(), nullable=True))
    op.add_column('gym_template_exercises',
                  sa.Column('rep_min', sa.SmallInteger(), nullable=True))
    op.add_column('gym_template_exercises',
                  sa.Column('rep_max', sa.SmallInteger(), nullable=True))


def downgrade():
    op.drop_column('gym_template_exercises', 'rep_max')
    op.drop_column('gym_template_exercises', 'rep_min')
    op.drop_column('gym_template_exercises', 'target_sets')
