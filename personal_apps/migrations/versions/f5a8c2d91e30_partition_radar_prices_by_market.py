"""partition radar price identities by market instrument

Revision ID: f5a8c2d91e30
Revises: a4c8e2f19b70
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'f5a8c2d91e30'
down_revision = 'a4c8e2f19b70'
branch_labels = None
depends_on = None


def _rebuild_quotes(with_market_key):
    """Replace the quote key while retaining its MySQL binary ticker identity."""
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    id_type = sa.Integer() if is_sqlite else mysql.BIGINT()
    timestamp_type = sa.DateTime() if is_sqlite else mysql.DATETIME(fsp=6)
    table_options = {} if is_sqlite else {'mysql_charset': 'utf8mb4'}
    table_name = '_radar_quotes_new' if with_market_key else '_radar_quotes_old'
    unique_name = 'uq_radar_quote_market' if with_market_key else 'uq_radar_quote'
    unique_columns = (['ticker', 'market', 'mic', 'fetched_at']
                      if with_market_key else ['ticker', 'fetched_at'])
    index_name = ('ix_radar_quotes_ticker_market_mic_fetched'
                  if with_market_key else 'ix_radar_quotes_ticker_fetched')
    index_columns = (['ticker', 'market', 'mic', 'fetched_at']
                     if with_market_key else ['ticker', 'fetched_at'])

    op.create_table(
        table_name,
        sa.Column('id', id_type, primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.String(length=12, collation='utf8mb4_bin'),
                  nullable=False),
        sa.Column('market', sa.String(length=2), nullable=True),
        sa.Column('mic', sa.String(length=4), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True),
        sa.Column('provider_symbol', sa.String(length=32), nullable=True),
        sa.Column('fetched_at', timestamp_type, nullable=False),
        sa.Column('quote_ts', timestamp_type, nullable=True),
        sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('prev_close', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('volume', sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(*unique_columns, name=unique_name),
        sa.CheckConstraint("market IS NULL OR market IN ('us', 'de')",
                           name='ck_radar_quotes_market'),
        **table_options,
    )
    op.create_index(index_name, table_name, index_columns, unique=False)
    op.execute(sa.text(f"""
        INSERT INTO {table_name}
            (id, ticker, market, mic, currency, provider_symbol, fetched_at,
             quote_ts, price, prev_close, volume)
        SELECT id, ticker, market, mic, currency, provider_symbol, fetched_at,
               quote_ts, price, prev_close, volume
        FROM radar_quotes
    """))
    op.drop_table('radar_quotes')
    op.rename_table(table_name, 'radar_quotes')


def _rebuild_daily_closes(with_market_key):
    """Replace the legacy composite key without losing any stored close."""
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    id_type = sa.Integer() if is_sqlite else mysql.BIGINT()
    timestamp_type = sa.DateTime() if is_sqlite else mysql.DATETIME(fsp=6)
    table_options = {} if is_sqlite else {'mysql_charset': 'utf8mb4'}
    if with_market_key:
        op.create_table(
            '_radar_daily_closes_new',
            sa.Column('id', id_type, primary_key=True, autoincrement=True),
            sa.Column('ticker', sa.String(length=12, collation='utf8mb4_bin'),
                      nullable=False),
            sa.Column('market', sa.String(length=2), nullable=True),
            sa.Column('mic', sa.String(length=4), nullable=True),
            sa.Column('currency', sa.String(length=3), nullable=True),
            sa.Column('close_date', sa.Date(), nullable=False),
            sa.Column('close', sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column('fetched_at', timestamp_type, nullable=False),
            sa.UniqueConstraint('ticker', 'market', 'mic', 'close_date',
                                name='uq_radar_daily_close_market'),
            sa.CheckConstraint("market IS NULL OR market IN ('us', 'de')",
                               name='ck_radar_daily_closes_market'),
            **table_options,
        )
        op.execute(sa.text("""
            INSERT INTO _radar_daily_closes_new
                (ticker, market, mic, currency, close_date, close, fetched_at)
            SELECT ticker, market, mic, currency, close_date, close, fetched_at
            FROM radar_daily_closes
        """))
    else:
        op.create_table(
            '_radar_daily_closes_old',
            sa.Column('ticker', sa.String(length=12, collation='utf8mb4_bin'),
                      primary_key=True),
            sa.Column('market', sa.String(length=2), nullable=True),
            sa.Column('mic', sa.String(length=4), nullable=True),
            sa.Column('currency', sa.String(length=3), nullable=True),
            sa.Column('close_date', sa.Date(), primary_key=True),
            sa.Column('close', sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column('fetched_at', timestamp_type, nullable=False),
            sa.CheckConstraint("market IS NULL OR market IN ('us', 'de')",
                               name='ck_radar_daily_closes_market'),
            **table_options,
        )
        op.execute(sa.text("""
            INSERT INTO _radar_daily_closes_old
                (ticker, market, mic, currency, close_date, close, fetched_at)
            SELECT ticker, market, mic, currency, close_date, close, fetched_at
            FROM radar_daily_closes
        """))
    op.drop_table('radar_daily_closes')
    op.rename_table(
        '_radar_daily_closes_new' if with_market_key else '_radar_daily_closes_old',
        'radar_daily_closes')


def upgrade():
    _rebuild_quotes(with_market_key=True)
    _rebuild_daily_closes(with_market_key=True)


def _dedupe_legacy_us_identities(table, key_column):
    """Keep one canonical US row for each legacy ticker/key identity.

    The expanded unique keys allow `(NULL, NULL)` legacy writes alongside a
    market-aware US/MIC write at the exact same old key.  Before restoring the
    old key, keep the legacy row when it exists; otherwise retain the first US
    row deterministically.  Reading the candidates then deleting by primary
    key works on both production MySQL and the isolated SQLite migration QA.
    """
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"""
        SELECT id, ticker, {key_column}, market, mic
        FROM {table}
        WHERE (market IS NULL AND mic IS NULL) OR market = 'us'
        ORDER BY ticker, {key_column},
                 CASE WHEN market IS NULL AND mic IS NULL THEN 0 ELSE 1 END,
                 id
    """)).mappings()

    seen = set()
    duplicate_ids = []
    for row in rows:
        identity = (row['ticker'], row[key_column])
        if identity in seen:
            duplicate_ids.append(row['id'])
        else:
            seen.add(identity)

    for row_id in duplicate_ids:
        bind.execute(sa.text(f"DELETE FROM {table} WHERE id = :id"),
                     {'id': row_id})


def downgrade():
    # The old ticker/date key cannot retain a German daily bar beside a US one.
    op.execute(sa.text(
        "DELETE FROM radar_quotes WHERE market IS NOT NULL AND market <> 'us'"))
    op.execute(sa.text(
        "DELETE FROM radar_daily_closes WHERE market IS NOT NULL AND market <> 'us'"))

    _dedupe_legacy_us_identities('radar_quotes', 'fetched_at')
    _dedupe_legacy_us_identities('radar_daily_closes', 'close_date')

    _rebuild_quotes(with_market_key=False)
    _rebuild_daily_closes(with_market_key=False)
