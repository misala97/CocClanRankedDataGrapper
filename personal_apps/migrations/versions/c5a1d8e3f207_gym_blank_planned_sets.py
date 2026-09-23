"""gym: a planned set can wait for its numbers -- blank means NULL

Revision ID: c5a1d8e3f207
Revises: 4b8e2d6f1a93
Create Date: 2026-09-23 22:00:00.000000

A never-done exercise used to arrive planned at 3 x 20 kg x 8 -- a placeholder
the lifter was expected to correct. V2 of the first-run work
(docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md) plans the three
sets with no numbers at all: the lifter types the first one, the rest take it.
weight and reps become nullable; NULL means "not decided yet" and only ever
sits on a set that is not completed.

Data: the placeholder sets still open in the database -- is_default_seeded and
not completed -- lose their placeholder. The weight goes blank outright: any
typed weight clears is_default_seeded, so a flagged set's weight is the
placeholder by construction. The reps go blank only while they still read the
placeholder 8: a typed rep count leaves the flag alone, so any other number
was typed and stays.

Downgrade writes the placeholder back into every blank before the columns turn
NOT NULL again.
"""
import sqlalchemy as sa
from alembic import op

revision = 'c5a1d8e3f207'
down_revision = '4b8e2d6f1a93'
branch_labels = None
depends_on = None

TABLE = 'gym_session_sets'
# The placeholder this revision retires (stats.DEFAULT_PLAN_WEIGHT/REPS before
# it), frozen here so the migration never follows later code.
PLACEHOLDER_WEIGHT = 20.0
PLACEHOLDER_REPS = 8

sets = sa.table(TABLE, sa.column('weight', sa.Float()), sa.column('reps', sa.Integer()),
                sa.column('completed', sa.Boolean()), sa.column('is_default_seeded', sa.Boolean()))


def upgrade():
    op.alter_column(TABLE, 'weight', existing_type=sa.Float(), nullable=True)
    op.alter_column(TABLE, 'reps', existing_type=sa.Integer(), nullable=True)
    open_placeholder = sa.and_(sets.c.is_default_seeded == sa.true(),
                               sets.c.completed == sa.false())
    op.execute(sets.update().where(open_placeholder).values(weight=None))
    op.execute(sets.update()
               .where(sa.and_(open_placeholder, sets.c.reps == PLACEHOLDER_REPS))
               .values(reps=None))


def downgrade():
    op.execute(sets.update().where(sets.c.weight.is_(None)).values(weight=PLACEHOLDER_WEIGHT))
    op.execute(sets.update().where(sets.c.reps.is_(None)).values(reps=PLACEHOLDER_REPS))
    op.alter_column(TABLE, 'weight', existing_type=sa.Float(), nullable=False)
    op.alter_column(TABLE, 'reps', existing_type=sa.Integer(), nullable=False)
