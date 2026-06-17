"""pubquiz points columns float for half-point support

Revision ID: d3e9f2a71c04
Revises: a9f88ac3f70a
Create Date: 2026-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e9f2a71c04'
down_revision = 'f4d12da7510b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pubquiz_teams', schema=None) as batch_op:
        batch_op.alter_column('round1_points', type_=sa.Float(), existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('round2_points', type_=sa.Float(), existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('round3_points', type_=sa.Float(), existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column('round4_points', type_=sa.Float(), existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table('pubquiz_teams', schema=None) as batch_op:
        batch_op.alter_column('round4_points', type_=sa.Integer(), existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('round3_points', type_=sa.Integer(), existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('round2_points', type_=sa.Integer(), existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('round1_points', type_=sa.Integer(), existing_type=sa.Float(), nullable=True)
