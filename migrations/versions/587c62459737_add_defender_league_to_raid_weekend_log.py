"""add defender_league to raid_weekend_log

Revision ID: 587c62459737
Revises: e50811c0e395
Create Date: 2026-06-07 17:53:22.770924

"""
from alembic import op
import sqlalchemy as sa

revision = '587c62459737'
down_revision = 'e50811c0e395'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('raid_weekend_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('defender_league', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('defender_league_badge', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('raid_weekend_log', schema=None) as batch_op:
        batch_op.drop_column('defender_league_badge')
        batch_op.drop_column('defender_league')
