"""add previous_name to exercises

Revision ID: 7e14cc7ed388
Revises: d4f8b2a91c6e
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e14cc7ed388'
down_revision = 'd4f8b2a91c6e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('previous_name', sa.String(length=150), nullable=True))


def downgrade():
    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.drop_column('previous_name')
