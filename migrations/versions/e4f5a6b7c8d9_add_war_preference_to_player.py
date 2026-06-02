"""add war_preference_in_game and war_preference_custom to player

Revision ID: e4f5a6b7c8d9
Revises: 7d396e785c8d
Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f5a6b7c8d9'
down_revision = '7d396e785c8d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.add_column(sa.Column('war_preference_in_game', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('war_preference_custom',  sa.String(20), nullable=True))


def downgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('war_preference_custom')
        batch_op.drop_column('war_preference_in_game')
