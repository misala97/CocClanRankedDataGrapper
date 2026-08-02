"""add base_reps to session sets

Revision ID: e9b4c2a71d63
Revises: c7d3e91a4f28
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9b4c2a71d63'
down_revision = 'c7d3e91a4f28'
branch_labels = None
depends_on = None


def upgrade():
    # No backfill: NULL means "reps are the real ones", which is true of every
    # set that predates the deload rep override -- including the sets in past
    # deload sessions, whose 10s were typed by hand and so ARE the real reps.
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('base_reps', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.drop_column('base_reps')
