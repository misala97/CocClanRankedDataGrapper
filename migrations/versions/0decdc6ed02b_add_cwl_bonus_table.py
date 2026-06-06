"""add cwl_bonus table

Revision ID: 0decdc6ed02b
Revises: 0ccd0d8aaef3
Create Date: 2026-06-06 01:11:20.905786

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '0decdc6ed02b'
down_revision = '0ccd0d8aaef3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cwl_bonus',
        sa.Column('id',         sa.Integer(),  autoincrement=True, nullable=False),
        sa.Column('player_tag', sa.String(50), nullable=False),
        sa.Column('month',      sa.String(7),  nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_tag', 'month', name='uq_cwl_bonus'),
    )


def downgrade():
    op.drop_table('cwl_bonus')
