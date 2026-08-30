"""add radar market instruments

Revision ID: a4c8e2f19b70
Revises: 35c3ae366677
Create Date: 2026-08-28

Expand-only by design. The daemon deployed before this migration writes
ticker-only price rows, so the new context columns stay nullable until every
writer has moved to the market-aware contract. Existing rows are backfilled;
new legacy writes remain valid during the overlap.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'a4c8e2f19b70'
down_revision = '35c3ae366677'
branch_labels = None
depends_on = None


MIC_CASE = """CASE u.exchange
    WHEN 'Q' THEN 'XNGS'
    WHEN 'G' THEN 'XNMS'
    WHEN 'S' THEN 'XNCM'
    WHEN 'N' THEN 'XNYS'
    WHEN 'P' THEN 'ARCX'
    WHEN 'A' THEN 'XASE'
    WHEN 'Z' THEN 'BATS'
    WHEN 'V' THEN 'IEXG'
    ELSE 'XXXX'
END"""

VENUE_CASE = """CASE u.exchange
    WHEN 'Q' THEN 'Nasdaq Global Select'
    WHEN 'G' THEN 'Nasdaq Global Market'
    WHEN 'S' THEN 'Nasdaq Capital Market'
    WHEN 'N' THEN 'NYSE'
    WHEN 'P' THEN 'NYSE Arca'
    WHEN 'A' THEN 'NYSE American'
    WHEN 'Z' THEN 'Cboe BZX'
    WHEN 'V' THEN 'IEX'
    ELSE 'Unknown US venue'
END"""

MAPPED_CASE = """CASE
    WHEN u.exchange IN ('Q', 'G', 'S', 'N', 'P', 'A', 'Z', 'V')
    THEN 'mapped'
    ELSE 'unverified'
END"""


def _context_update(table):
    """Portable correlated update used by both MySQL and isolated SQLite QA."""
    return sa.text(f"""
        UPDATE {table}
        SET market = 'us',
            currency = 'USD',
            provider_symbol = ticker,
            mic = COALESCE((
                SELECT {MIC_CASE}
                FROM radar_ticker_universe AS u
                WHERE u.symbol = {table}.ticker
                LIMIT 1
            ), 'XXXX')
    """)


def upgrade():
    op.create_table(
        'radar_instruments',
        # SQLite only auto-increments a column compiled as exactly INTEGER;
        # production MySQL still receives BIGINT. The variant lets the
        # migration's preservation test execute the real DDL and backfill.
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
                  autoincrement=True, nullable=False),
        sa.Column('ticker', sa.String(length=12, collation='utf8mb4_bin'),
                  nullable=False),
        sa.Column('market', sa.String(length=2), nullable=False),
        sa.Column('venue', sa.String(length=48), nullable=False),
        sa.Column('mic', sa.String(length=4), nullable=False),
        sa.Column('provider_symbol', sa.String(length=32), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('isin', sa.String(length=12), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.Column('mapping_status', sa.String(length=12), nullable=False),
        sa.Column('mapping_source', sa.String(length=24), nullable=True),
        sa.Column('mapped_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticker', 'market', 'mic',
                            name='uq_radar_instrument'),
        sa.CheckConstraint("market IN ('us', 'de')",
                           name='ck_radar_instrument_market'),
        mysql_charset='utf8mb4',
    )
    with op.batch_alter_table('radar_instruments', schema=None) as batch_op:
        batch_op.create_index(
            'ix_radar_instrument_primary',
            ['ticker', 'market', 'is_primary'], unique=False)

    with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('market', sa.String(length=2),
                                      nullable=True))
        batch_op.add_column(sa.Column('mic', sa.String(length=4),
                                      nullable=True))
        batch_op.add_column(sa.Column('currency', sa.String(length=3),
                                      nullable=True))
        batch_op.add_column(sa.Column('provider_symbol', sa.String(length=32),
                                      nullable=True))
        batch_op.create_check_constraint(
            'ck_radar_quotes_market',
            "market IS NULL OR market IN ('us', 'de')")

    with op.batch_alter_table('radar_daily_closes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('market', sa.String(length=2),
                                      nullable=True))
        batch_op.add_column(sa.Column('mic', sa.String(length=4),
                                      nullable=True))
        batch_op.add_column(sa.Column('currency', sa.String(length=3),
                                      nullable=True))
        batch_op.create_check_constraint(
            'ck_radar_daily_closes_market',
            "market IS NULL OR market IN ('us', 'de')")

    op.execute(_context_update('radar_quotes'))
    # Daily closes have no provider_symbol column.
    op.execute(sa.text(f"""
        UPDATE radar_daily_closes
        SET market = 'us',
            currency = 'USD',
            mic = COALESCE((
                SELECT {MIC_CASE}
                FROM radar_ticker_universe AS u
                WHERE u.symbol = radar_daily_closes.ticker
                LIMIT 1
            ), 'XXXX')
    """))

    op.execute(sa.text(f"""
        INSERT INTO radar_instruments
            (ticker, market, venue, mic, provider_symbol, currency, isin,
             is_primary, mapping_status, mapping_source, mapped_at)
        SELECT u.symbol, 'us', {VENUE_CASE}, {MIC_CASE}, u.symbol, 'USD', NULL,
               1, {MAPPED_CASE}, 'nasdaq-directory', CURRENT_TIMESTAMP
        FROM radar_ticker_universe AS u
        WHERE u.delisted_at IS NULL
    """))


def downgrade():
    # Old ticker-only keys cannot distinguish a German venue price from its
    # US counterpart. Keep US and mixed-version NULL rows, but remove every
    # non-US context row before dropping the context that identifies it.
    op.execute(sa.text(
        "DELETE FROM radar_quotes WHERE market IS NOT NULL AND market <> 'us'"))
    op.execute(sa.text(
        "DELETE FROM radar_daily_closes "
        "WHERE market IS NOT NULL AND market <> 'us'"))

    with op.batch_alter_table('radar_daily_closes', schema=None) as batch_op:
        batch_op.drop_constraint('ck_radar_daily_closes_market', type_='check')
        batch_op.drop_column('currency')
        batch_op.drop_column('mic')
        batch_op.drop_column('market')

    with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
        batch_op.drop_constraint('ck_radar_quotes_market', type_='check')
        batch_op.drop_column('provider_symbol')
        batch_op.drop_column('currency')
        batch_op.drop_column('mic')
        batch_op.drop_column('market')

    op.drop_table('radar_instruments')
