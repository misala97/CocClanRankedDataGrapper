"""add gain_settings to app_user

Revision ID: ed406b91c2dd
Revises: a5e95f655592
Create Date: 2026-06-15 16:20:57.067175

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ed406b91c2dd'
down_revision = 'a5e95f655592'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gain_settings', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.drop_column('gain_settings')
