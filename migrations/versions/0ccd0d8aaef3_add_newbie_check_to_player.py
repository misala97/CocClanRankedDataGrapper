"""add newbie_check to player

Revision ID: 0ccd0d8aaef3
Revises: e27639be8099
Create Date: 2026-06-05 20:33:29.278481

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0ccd0d8aaef3'
down_revision = 'e27639be8099'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.add_column(sa.Column('newbie_check', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('newbie_check')
