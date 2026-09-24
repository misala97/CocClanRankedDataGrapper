"""gym: routines carry no rest

Revision ID: a3c9e5f1b7d2
Revises: fc72f159a49f
Create Date: 2026-09-24 12:00:00.000000

Since V3 (fc72f159a49f) a routine's exercises hold no rest of their own: the
lifter's setting decides. Starting a workout stopped reading
gym_template_exercises.rest_seconds then, and "Routine aktualisieren" wrote
NULL into it (walkthrough 2026-09-23, G-076) -- the column was dead data and
the owner ruled it dropped.

Downgrade brings the column back empty. What it held had stopped reaching any
workout before this ran, so there is nothing a rollback would miss.
"""
import sqlalchemy as sa
from alembic import op

revision = 'a3c9e5f1b7d2'
down_revision = 'fc72f159a49f'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('gym_template_exercises', 'rest_seconds')


def downgrade():
    op.add_column('gym_template_exercises',
                  sa.Column('rest_seconds', sa.Integer(), nullable=True))
