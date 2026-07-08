"""add is_unilateral to exercises

Revision ID: b3f9a1d5e7c2
Revises: 7e14cc7ed388
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f9a1d5e7c2'
down_revision = '7e14cc7ed388'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_unilateral', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.drop_column('is_unilateral')
