"""add radar_instruments.history_due_at

A durable per-instrument history schedule, so the fetch queue drains instead
of re-competing with today's chatter ranking. Plain DDL -- MariaDB in prod.

Revision ID: e5f8b2ca4d36
Revises: d4e7a1b93c25
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'e5f8b2ca4d36'
down_revision = 'd4e7a1b93c25'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('radar_instruments',
                  sa.Column('history_due_at', mysql.DATETIME(fsp=6),
                            nullable=True))
    op.create_index('ix_radar_instruments_history_due', 'radar_instruments',
                    ['market', 'history_due_at'])


def downgrade():
    op.drop_index('ix_radar_instruments_history_due',
                  table_name='radar_instruments')
    op.drop_column('radar_instruments', 'history_due_at')
