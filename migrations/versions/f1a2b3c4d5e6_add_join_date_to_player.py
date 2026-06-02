"""add join_date to player

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Branch_labels = None
Depends_on = None

Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.add_column(sa.Column('join_date', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('join_date')
