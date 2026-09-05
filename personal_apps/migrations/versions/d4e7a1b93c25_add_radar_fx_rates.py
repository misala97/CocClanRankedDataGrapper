"""add radar_fx_rates

One published reference rate per day and currency pair, so a US listing's
closes can be drawn on a euro axis. Plain DDL -- MariaDB in production.

Revision ID: d4e7a1b93c25
Revises: c8d2e5f7a1b4
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e7a1b93c25'
down_revision = 'c8d2e5f7a1b4'
branch_labels = None
depends_on = None


def upgrade():
    # MariaDB commits DDL. Keep the table, unique key, and lookup index in one
    # atomic CREATE so a retry never meets a half-created schema.
    op.execute(sa.text("""
        CREATE TABLE radar_fx_rates (
            id BIGINT NOT NULL AUTO_INCREMENT,
            rate_date DATE NOT NULL,
            base VARCHAR(3) NOT NULL,
            quote VARCHAR(3) NOT NULL,
            rate NUMERIC(18, 8) NOT NULL,
            source VARCHAR(16) NOT NULL,
            fetched_at DATETIME(6) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_radar_fx_rate_day
                UNIQUE (rate_date, base, quote),
            KEY ix_radar_fx_rates_pair_day (base, quote, rate_date)
        ) DEFAULT CHARSET=utf8mb4
    """))


def downgrade():
    op.execute(sa.text('DROP TABLE radar_fx_rates'))
