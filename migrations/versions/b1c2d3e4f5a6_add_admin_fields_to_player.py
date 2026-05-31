"""add admin_comment and in_group_chat to player

Revision ID: b1c2d3e4f5a6
Revises: 138728b2a169
Create Date: 2026-05-31 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c2d3e4f5a6'
down_revision = 'a21ca9607055'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.add_column(sa.Column('admin_comment', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('in_group_chat', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('in_group_chat')
        batch_op.drop_column('admin_comment')
