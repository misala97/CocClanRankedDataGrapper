"""add ranked_week_analysis table

Revision ID: b2c4e6f8a0d2
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c4e6f8a0d2'
down_revision = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ranked_week_analysis',
        sa.Column('app_user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('league_group_tag', sa.String(length=50), nullable=True),
        sa.Column('league_season_id', sa.String(length=50), nullable=True),
        sa.Column('player_tag', sa.String(length=50), nullable=True),
        sa.Column('progress_done', sa.Integer(), nullable=True),
        sa.Column('progress_total', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('results_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['app_user_id'], ['app_user.id']),
        sa.PrimaryKeyConstraint('app_user_id'),
    )


def downgrade():
    op.drop_table('ranked_week_analysis')
