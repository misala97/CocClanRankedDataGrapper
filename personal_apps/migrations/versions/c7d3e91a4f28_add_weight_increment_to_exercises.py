"""add weight_increment to exercises

Revision ID: c7d3e91a4f28
Revises: a1e4c9d27f63
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d3e91a4f28'
down_revision = 'a1e4c9d27f63'
branch_labels = None
depends_on = None


def upgrade():
    # Deliberately no server_default and no backfill: NULL is the correct
    # resting state and means "use stats.DEFAULT_INCREMENT", so every existing
    # exercise keeps the behaviour it had before this column existed.
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('weight_increment', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.drop_column('weight_increment')
