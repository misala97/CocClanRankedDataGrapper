"""add is_etf to the ticker universe

A fund has no market cap to look up -- Finnhub's /stock/profile2 returns an
empty payload for SPY and QQQ, verified against the live API 2026-08-24 -- so
every ETF fell through universe.segment_for() into Unknown, and Unknown sits
inside the Small group. SPY was listed in the tab meant for penny stocks
nobody has heard of.

Nothing downstream can infer it, and the names do not carry it: `Invesco QQQ
Trust`, `SPDR Dow Jones Industrial` and `SPDR Gold Shares` contain no fund
word between them, and `trust` cannot be pattern-matched because Adamas Trust
is an operating company. The Nasdaq Trader directory files DO carry it, as an
ETF column both of them spell the same way, and the seed script was simply not
reading it.

NULLABLE on purpose, and left NULL for existing rows. NULL means the directory
has not been read for this row, which is not the same as "this is a stock" --
segment_for falls back to the name pattern there rather than asserting.
Existing rows fill in on the next run of scripts/seed_radar_universe.py.

Revision ID: c7a3e1f92b04
Revises: ef00e6c43e25
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c7a3e1f92b04'
down_revision = 'ef00e6c43e25'
branch_labels = None
depends_on = None

TABLE = 'radar_ticker_universe'


def upgrade():
    op.add_column(TABLE, sa.Column('is_etf', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column(TABLE, 'is_etf')
