"""add war_log_public to clan_war

Revision ID: 08c2e4aac896
Revises: 587c62459737
Create Date: 2026-06-07 18:28:02.633087

"""
from alembic import op
import sqlalchemy as sa

revision = '08c2e4aac896'
down_revision = '587c62459737'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clan_war', schema=None) as batch_op:
        batch_op.add_column(sa.Column('war_log_public', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('opponent_war_log_public', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('clan_war', schema=None) as batch_op:
        batch_op.drop_column('opponent_war_log_public')
        batch_op.drop_column('war_log_public')
