"""add clan_config table

Revision ID: b3e7c1a9f042
Revises: 0decdc6ed02b
Create Date: 2026-06-06

"""
from alembic import op
import sqlalchemy as sa

revision = 'b3e7c1a9f042'
down_revision = '0decdc6ed02b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'clan_config',
        sa.Column('clan_tag',        sa.String(30), nullable=False),
        sa.Column('cwl_league_name', sa.String(60), nullable=True),
        sa.PrimaryKeyConstraint('clan_tag'),
    )


def downgrade():
    op.drop_table('clan_config')
