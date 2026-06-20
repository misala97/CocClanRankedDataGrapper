"""add trips to delivery_shifts

Revision ID: 1cdcdfc9d2d6
Revises: 550f78a86ec3
Create Date: 2026-06-20 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1cdcdfc9d2d6'
down_revision = '550f78a86ec3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('delivery_shifts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trips', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('delivery_shifts', schema=None) as batch_op:
        batch_op.drop_column('trips')
