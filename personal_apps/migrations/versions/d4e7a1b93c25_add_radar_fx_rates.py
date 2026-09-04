"""add radar_fx_rates

One published reference rate per day and currency pair, so a US listing's
closes can be drawn on a euro axis. Plain DDL -- MariaDB in production.

Revision ID: d4e7a1b93c25
Revises: c8d2e5f7a1b4
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'd4e7a1b93c25'
down_revision = 'c8d2e5f7a1b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'radar_fx_rates',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('base', sa.String(length=3), nullable=False),
        sa.Column('quote', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(18, 8), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('fetched_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rate_date', 'base', 'quote',
                            name='uq_radar_fx_rate_day'),
        mysql_charset='utf8mb4')
    op.create_index('ix_radar_fx_rates_pair_day', 'radar_fx_rates',
                    ['base', 'quote', 'rate_date'])


def downgrade():
    op.drop_index('ix_radar_fx_rates_pair_day', table_name='radar_fx_rates')
    op.drop_table('radar_fx_rates')
