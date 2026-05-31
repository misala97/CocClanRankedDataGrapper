"""add perm_create_reminder_ranked to app_user

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-31 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('perm_create_reminder_ranked', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.drop_column('perm_create_reminder_ranked')
