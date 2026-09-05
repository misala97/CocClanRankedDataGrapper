"""add radar_instruments.history_due_at

A durable per-instrument history schedule, so the fetch queue drains instead
of re-competing with today's chatter ranking. Plain DDL -- MariaDB in prod.

Revision ID: e5f8b2ca4d36
Revises: d4e7a1b93c25
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f8b2ca4d36'
down_revision = 'd4e7a1b93c25'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        ALTER TABLE radar_instruments
        ADD COLUMN history_due_at DATETIME(6) NULL,
        ADD INDEX ix_radar_instruments_history_due (market, history_due_at)
    """))


def downgrade():
    op.execute(sa.text("""
        ALTER TABLE radar_instruments
        DROP INDEX ix_radar_instruments_history_due,
        DROP COLUMN history_due_at
    """))
