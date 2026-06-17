"""add clan_name to clan_war

Revision ID: 138728b2a169
Revises: 0fc036606227
Create Date: 2026-05-31 15:53:16.212000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '138728b2a169'
down_revision = '0fc036606227'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clan_war', schema=None) as batch_op:
        batch_op.add_column(sa.Column('clan_name', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('clan_war', schema=None) as batch_op:
        batch_op.drop_column('clan_name')
