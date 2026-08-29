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
            sa.Column('ticker', sa.String(length=12), nullable=False),
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
            sa.Column('ticker', sa.String(length=12), primary_key=True),
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
    inspector = sa.inspect(op.get_bind())
    quote_uniques = {item['name'] for item in inspector.get_unique_constraints(
        'radar_quotes')}
    quote_indexes = {item['name'] for item in inspector.get_indexes('radar_quotes')}
    if ('uq_radar_quote' in quote_uniques or
            'ix_radar_quotes_ticker_fetched' in quote_indexes):
        with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
            if 'uq_radar_quote' in quote_uniques:
                batch_op.drop_constraint('uq_radar_quote', type_='unique')
            if 'uq_radar_quote_market' not in quote_uniques:
                batch_op.create_unique_constraint(
                    'uq_radar_quote_market',
                    ['ticker', 'market', 'mic', 'fetched_at'])
            if 'ix_radar_quotes_ticker_fetched' in quote_indexes:
                batch_op.drop_index('ix_radar_quotes_ticker_fetched')
            if 'ix_radar_quotes_ticker_market_mic_fetched' not in quote_indexes:
                batch_op.create_index(
                    'ix_radar_quotes_ticker_market_mic_fetched',
                    ['ticker', 'market', 'mic', 'fetched_at'], unique=False)

    _rebuild_daily_closes(with_market_key=True)


def downgrade():
    # The old ticker/date key cannot retain a German daily bar beside a US one.
    op.execute(sa.text(
        "DELETE FROM radar_quotes WHERE market IS NOT NULL AND market <> 'us'"))
    op.execute(sa.text(
        "DELETE FROM radar_daily_closes WHERE market IS NOT NULL AND market <> 'us'"))

    _rebuild_daily_closes(with_market_key=False)

    with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
        batch_op.drop_index('ix_radar_quotes_ticker_market_mic_fetched')
        batch_op.drop_constraint('uq_radar_quote_market', type_='unique')
        batch_op.create_index('ix_radar_quotes_ticker_fetched',
                              ['ticker', 'fetched_at'], unique=False)
        batch_op.create_unique_constraint('uq_radar_quote', ['ticker', 'fetched_at'])
