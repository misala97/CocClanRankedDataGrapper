"""add last_seen_at to push subscriptions

Revision ID: a1c95e7b4d02
Revises: c4a7e12f6d93
Create Date: 2026-08-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c95e7b4d02'
down_revision = 'c4a7e12f6d93'
branch_labels = None
depends_on = None


def upgrade():
    # Three steps rather than one, because the column is NOT NULL and the
    # existing rows need an honest value. Backfilled from created_at, not from
    # now(): a row that has been an orphan since July must look like one
    # immediately, and stamping every row with the deploy time would grant the
    # duplicates another full window of buzzing the same phone twice.
    with op.batch_alter_table('gym_push_subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(), nullable=True))

    op.execute('UPDATE gym_push_subscriptions SET last_seen_at = created_at '
               'WHERE last_seen_at IS NULL')

    with op.batch_alter_table('gym_push_subscriptions', schema=None) as batch_op:
        batch_op.alter_column('last_seen_at', existing_type=sa.DateTime(),
                              nullable=False)


def downgrade():
    with op.batch_alter_table('gym_push_subscriptions', schema=None) as batch_op:
        batch_op.drop_column('last_seen_at')
