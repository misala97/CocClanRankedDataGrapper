"""add radar observations

Two additive tables for the recording contract: what each ingest cycle did,
and what a fixed pair of board selections showed at a quarter-hour slot.
Nothing existing is altered, so the downgrade is a clean drop of exactly these
two and the retention of every other table is untouched.

Revision ID: d82f9afb5898
Revises: b3d9e1f5a274
Create Date: 2026-09-09 14:09:54.179502

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = 'd82f9afb5898'
down_revision = 'b3d9e1f5a274'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'radar_ingest_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('started_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('finished_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('status', sa.String(length=8), nullable=False),
        sa.Column('summary_json', sa.JSON(), nullable=True),
        sa.Column('error_code', sa.String(length=48), nullable=True),
        sa.CheckConstraint("status IN ('running', 'ok', 'error')",
                           name='ck_radar_ingest_run_status'),
        sa.PrimaryKeyConstraint('id'),
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_radar_ingest_runs_started', 'radar_ingest_runs',
                    ['started_at'], unique=False)
    op.create_table(
        'radar_board_observations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slot_start', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('observed_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('producer_revision', sa.String(length=64), nullable=True),
        sa.Column('selections_json', sa.JSON(), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        # The archive's immutability, enforced in SQL: a repeated capture of a
        # quarter-hour conflicts here rather than rewriting the first one.
        sa.UniqueConstraint('slot_start', name='uq_radar_board_observation_slot'),
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_radar_board_observations_observed',
                    'radar_board_observations', ['observed_at'], unique=False)


def downgrade():
    # Dropping the tables takes their indexes with them. Naming the indexes
    # here as well only adds a statement that fails if one of them is already
    # absent, which is a worse downgrade, not a more thorough one.
    op.drop_table('radar_board_observations')
    op.drop_table('radar_ingest_runs')
