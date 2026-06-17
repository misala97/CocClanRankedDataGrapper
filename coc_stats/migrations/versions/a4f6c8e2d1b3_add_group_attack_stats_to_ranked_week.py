"""add group_total_attacks and group_full_attackers to ranked_week

Revision ID: a4f6c8e2d1b3
Revises: b3e7c1a9f042
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a4f6c8e2d1b3'
down_revision = 'b3e7c1a9f042'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ranked_week') as batch_op:
        batch_op.add_column(sa.Column('group_total_attacks',  sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('group_full_attackers', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('ranked_week') as batch_op:
        batch_op.drop_column('group_full_attackers')
        batch_op.drop_column('group_total_attacks')
