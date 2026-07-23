"""add equip_last_seen_at to app_user

Revision ID: f7a3c9d1e2b4
Revises: c3d5f7a9b1e3
Create Date: 2026-07-23 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f7a3c9d1e2b4'
down_revision = 'c3d5f7a9b1e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('equip_last_seen_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.drop_column('equip_last_seen_at')
