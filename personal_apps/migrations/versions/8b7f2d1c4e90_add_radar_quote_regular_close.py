"""add radar quote regular close

Revision ID: 8b7f2d1c4e90
Revises: f5a8c2d91e30
Create Date: 2026-08-29

The column is nullable because the deployed quote writers overlap with older
versions that do not yet send this same-day regular-session baseline.
"""
from alembic import op
import sqlalchemy as sa


revision = '8b7f2d1c4e90'
down_revision = 'f5a8c2d91e30'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('regular_close', sa.Numeric(precision=18, scale=6),
                      nullable=True))


def downgrade():
    with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
        batch_op.drop_column('regular_close')
