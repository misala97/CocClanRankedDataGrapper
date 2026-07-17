"""add skipped to session exercises

Revision ID: 9c3e5a71f2b6
Revises: b3f9a1d5e7c2
Create Date: 2026-07-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c3e5a71f2b6'
down_revision = 'b3f9a1d5e7c2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('gym_session_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('skipped', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('gym_session_exercises', schema=None) as batch_op:
        batch_op.drop_column('skipped')
