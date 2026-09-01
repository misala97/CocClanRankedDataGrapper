"""Behavioral guards for Radar migrations that must never touch the live DB."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_source_width_migration():
    path = (Path(__file__).parents[1] / 'migrations' / 'versions' /
            '08316d3e4d77_widen_radar_source_columns.py')
    spec = importlib.util.spec_from_file_location('radar_source_width', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_market_migration():
    path = (Path(__file__).parents[1] / 'migrations' / 'versions' /
            'a4c8e2f19b70_add_radar_market_instruments.py')
    assert path.exists(), 'market-instrument migration is missing'
    spec = importlib.util.spec_from_file_location('radar_market_instruments', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_market_key_migration():
    path = (Path(__file__).parents[1] / 'migrations' / 'versions' /
            'f5a8c2d91e30_partition_radar_prices_by_market.py')
    assert path.exists(), 'market-key migration is missing'
    spec = importlib.util.spec_from_file_location('radar_market_keys', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_regular_close_migration():
    path = (Path(__file__).parents[1] / 'migrations' / 'versions' /
            '8b7f2d1c4e90_add_radar_quote_regular_close.py')
    assert path.exists(), 'regular-close migration is missing'
    spec = importlib.util.spec_from_file_location('radar_regular_close', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_quote_quality_migration():
    path = (Path(__file__).parents[1] / 'migrations' / 'versions' /
            'd0a4b9c72e11_add_radar_quote_provider_delay.py')
    assert path.exists(), 'quote-provider-delay migration is missing'
    spec = importlib.util.spec_from_file_location('radar_quote_provider_delay', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def market_migration_db():
    """A real isolated schema, never the configured development database."""
    engine = sa.create_engine('sqlite://')
    connection = engine.connect()
    raw = connection.connection.driver_connection
    raw.create_collation('utf8mb4_bin', lambda left, right: (left > right) - (left < right))

    metadata = sa.MetaData()
    sa.Table(
        'radar_ticker_universe', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('symbol', sa.String(12), nullable=False, unique=True),
        sa.Column('name', sa.String(255)),
        sa.Column('exchange', sa.String(32)),
        sa.Column('first_seen', sa.DateTime, nullable=False),
        sa.Column('delisted_at', sa.DateTime),
    )
    sa.Table(
        'radar_quotes', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('ticker', sa.String(12, collation='utf8mb4_bin'), nullable=False),
        sa.Column('fetched_at', sa.DateTime, nullable=False),
        sa.Column('quote_ts', sa.DateTime),
        sa.Column('price', sa.Numeric(18, 6), nullable=False),
        sa.Column('prev_close', sa.Numeric(18, 6)),
        sa.Column('volume', sa.BigInteger),
        sa.UniqueConstraint('ticker', 'fetched_at', name='uq_radar_quote'),
    )
    sa.Table(
        'radar_daily_closes', metadata,
        sa.Column('ticker', sa.String(12, collation='utf8mb4_bin'), primary_key=True),
        sa.Column('close_date', sa.Date, primary_key=True),
        sa.Column('close', sa.Numeric(18, 4), nullable=False),
        sa.Column('fetched_at', sa.DateTime, nullable=False),
    )
    metadata.create_all(connection)
    connection.execute(sa.text(
        "INSERT INTO radar_ticker_universe "
        "(id, symbol, name, exchange, first_seen, delisted_at) VALUES "
        "(1, 'AAPL', 'Apple Inc', 'Q', '2026-01-01', NULL), "
        "(2, 'ODD', 'Unknown Venue Inc', 'TEST', '2026-01-01', NULL)"))
    connection.execute(sa.text(
        "INSERT INTO radar_quotes "
        "(id, ticker, fetched_at, quote_ts, price, prev_close, volume) VALUES "
        "(1, 'AAPL', '2026-08-28 12:00:00', '2026-08-28 11:59:00', "
        "194.2, 193.5, NULL)"))
    connection.execute(sa.text(
        "INSERT INTO radar_daily_closes "
        "(ticker, close_date, close, fetched_at) VALUES "
        "('AAPL', '2026-08-27', 193.5, '2026-08-28 12:00:00')"))
    connection.commit()

    yield connection
    connection.close()
    engine.dispose()


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeBind:
    def __init__(self, lengths, events):
        self.lengths = lengths
        self.events = events

    def execute(self, statement):
        sql = str(statement)
        table = next(name for name in self.lengths if name in sql)
        self.events.append(('check', table))
        return _ScalarResult(self.lengths[table])


class _FakeOp:
    def __init__(self, lengths):
        self.events = []
        self.bind = _FakeBind(lengths, self.events)

    def get_bind(self):
        return self.bind

    def alter_column(self, table, column, **kwargs):
        self.events.append(('alter', table, column))

    def execute(self, statement):
        self.events.append(('execute', str(statement)))


@pytest.mark.parametrize('violating_table', [
    'radar_poll_state',
    'radar_bucket_sources',
])
def test_source_width_downgrade_aborts_before_ddl_for_either_violation(
        monkeypatch, violating_table):
    migration = _load_source_width_migration()
    lengths = {'radar_poll_state': 24, 'radar_bucket_sources': 24}
    lengths[violating_table] = 25
    fake_op = _FakeOp(lengths)
    monkeypatch.setattr(migration, 'op', fake_op)

    with pytest.raises(RuntimeError, match=violating_table):
        migration.downgrade()

    assert fake_op.events == [
        ('check', 'radar_poll_state'),
        ('check', 'radar_bucket_sources'),
    ]


def test_source_width_downgrade_checks_both_tables_before_ordered_ddl(
        monkeypatch):
    migration = _load_source_width_migration()
    fake_op = _FakeOp(
        {'radar_poll_state': 24, 'radar_bucket_sources': 22})
    monkeypatch.setattr(migration, 'op', fake_op)

    migration.downgrade()

    assert fake_op.events[:2] == [
        ('check', 'radar_poll_state'),
        ('check', 'radar_bucket_sources'),
    ]
    assert fake_op.events[2:] == [
        ('alter', 'radar_poll_state', 'source'),
        ('alter', 'radar_bucket_sources', 'source'),
        ('execute', "UPDATE radar_posts SET source = 'reddit' "
                    "WHERE source LIKE 'reddit:%'"),
        ('alter', 'radar_posts', 'source'),
    ]


def test_market_migration_backfills_us_context_and_seeds_instruments(
        market_migration_db):
    """Omitting either backfill would make pre-feature prices disappear."""
    connection = market_migration_db
    migration = _load_market_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()

    quote = connection.execute(sa.text(
        "SELECT market, mic, currency, provider_symbol FROM radar_quotes "
        "WHERE ticker='AAPL'")) .one()
    close = connection.execute(sa.text(
        "SELECT market, mic, currency FROM radar_daily_closes "
        "WHERE ticker='AAPL'")) .one()
    apple = connection.execute(sa.text(
        "SELECT market, venue, mic, provider_symbol, currency, "
        "mapping_status FROM radar_instruments WHERE ticker='AAPL'")) .one()
    odd = connection.execute(sa.text(
        "SELECT mic, mapping_status FROM radar_instruments "
        "WHERE ticker='ODD'")) .one()

    assert tuple(quote) == ('us', 'XNGS', 'USD', 'AAPL')
    assert tuple(close) == ('us', 'XNGS', 'USD')
    assert tuple(apple) == (
        'us', 'Nasdaq Global Select', 'XNGS', 'AAPL', 'USD', 'mapped')
    assert tuple(odd) == ('XXXX', 'unverified')


def test_market_migration_keeps_legacy_writes_valid_during_overlap(
        market_migration_db):
    """The old daemon writes none of the new fields until Task 5."""
    connection = market_migration_db
    migration = _load_market_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()

    connection.execute(sa.text(
        "INSERT INTO radar_quotes "
        "(id, ticker, fetched_at, quote_ts, price, prev_close, volume) VALUES "
        "(2, 'AAPL', '2026-08-28 12:05:00', '2026-08-28 12:04:00', "
        "194.3, 193.5, NULL)"))
    connection.commit()

    row = connection.execute(sa.text(
        "SELECT market, mic, currency, provider_symbol FROM radar_quotes "
        "WHERE id=2")) .one()
    assert tuple(row) == (None, None, None, None)


def test_market_key_migration_keeps_same_time_us_and_xetra_prices_distinct(
        market_migration_db):
    """The writer cannot isolate markets while the old ticker-only keys remain."""
    connection = market_migration_db
    market = _load_market_migration()
    market.op = Operations(MigrationContext.configure(connection))
    market.upgrade()
    keys = _load_market_key_migration()
    keys.op = Operations(MigrationContext.configure(connection))
    keys.upgrade()

    connection.execute(sa.text("""
        INSERT INTO radar_quotes
            (id, ticker, market, mic, currency, provider_symbol, fetched_at,
             quote_ts, price, prev_close, volume)
        VALUES
            (2, 'AAPL', 'de', 'XETR', 'EUR', 'APC',
             '2026-08-28 12:00:00', '2026-08-28 11:59:00', 194.2, 193.5, NULL)
    """))
    connection.execute(sa.text("""
        INSERT INTO radar_daily_closes
            (ticker, market, mic, currency, close_date, close, fetched_at)
        VALUES
            ('AAPL', 'de', 'XETR', 'EUR', '2026-08-27', 194.2,
             '2026-08-28 12:00:00')
    """))
    connection.commit()

    assert connection.execute(sa.text(
        "SELECT count(*) FROM radar_quotes WHERE ticker='AAPL'")).scalar_one() == 2
    assert connection.execute(sa.text(
        "SELECT count(*) FROM radar_daily_closes WHERE ticker='AAPL'")) \
        .scalar_one() == 2


def test_regular_close_migration_keeps_mixed_version_quote_writes_valid(
        market_migration_db):
    """The new baseline is additive: old writers can still omit it safely."""
    connection = market_migration_db
    market = _load_market_migration()
    market.op = Operations(MigrationContext.configure(connection))
    market.upgrade()
    keys = _load_market_key_migration()
    keys.op = Operations(MigrationContext.configure(connection))
    keys.upgrade()
    migration = _load_regular_close_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()

    columns = {column['name'] for column in
               sa.inspect(connection).get_columns('radar_quotes')}
    assert 'regular_close' in columns
    assert connection.execute(sa.text(
        "SELECT regular_close FROM radar_quotes WHERE id=1")).scalar_one() is None

    connection.execute(sa.text("""
        INSERT INTO radar_quotes
            (id, ticker, market, mic, fetched_at, quote_ts, price, prev_close,
             volume)
        VALUES
            (2, 'OLDWRITER', 'us', 'XNAS', '2026-08-28 12:05:00',
             '2026-08-28 12:04:00', 194.3, 193.5, NULL)
    """))
    connection.commit()
    assert connection.execute(sa.text(
        "SELECT regular_close FROM radar_quotes WHERE id=2")).scalar_one() is None

    migration.downgrade()
    assert 'regular_close' not in {
        column['name'] for column in sa.inspect(connection).get_columns(
            'radar_quotes')}
    assert connection.execute(sa.text(
        "SELECT count(*) FROM radar_quotes WHERE id=2")).scalar_one() == 1


def test_quote_quality_migration_preserves_old_rows_and_accepts_new_quality(
        market_migration_db):
    connection = market_migration_db
    market = _load_market_migration()
    market.op = Operations(MigrationContext.configure(connection))
    market.upgrade()
    keys = _load_market_key_migration()
    keys.op = Operations(MigrationContext.configure(connection))
    keys.upgrade()
    regular_close = _load_regular_close_migration()
    regular_close.op = Operations(MigrationContext.configure(connection))
    regular_close.upgrade()
    quality = _load_quote_quality_migration()
    quality.op = Operations(MigrationContext.configure(connection))

    quality.upgrade()

    assert connection.execute(sa.text(
        "SELECT provider_delay FROM radar_quotes WHERE id=1")).scalar_one() is None
    connection.execute(sa.text("""
        INSERT INTO radar_quotes
            (id, ticker, market, mic, fetched_at, quote_ts, price, provider_delay)
        VALUES
            (2, 'QUALITY', 'de', 'XETR', '2026-08-28 12:05:00',
             '2026-08-28 12:04:00', 194.3, 'eod')
    """))
    connection.commit()
    assert connection.execute(sa.text(
        "SELECT provider_delay FROM radar_quotes WHERE id=2")).scalar_one() == 'eod'

    quality.downgrade()
    assert 'provider_delay' not in {
        column['name'] for column in sa.inspect(connection).get_columns(
            'radar_quotes')}
    assert connection.execute(sa.text(
        "SELECT count(*) FROM radar_quotes WHERE id=2")).scalar_one() == 1


def test_market_key_downgrade_keeps_legacy_us_rows_when_keys_collide(
        market_migration_db):
    """A NULL legacy identity wins over a same-key market-aware US rewrite."""
    connection = market_migration_db
    market = _load_market_migration()
    market.op = Operations(MigrationContext.configure(connection))
    market.upgrade()
    keys = _load_market_key_migration()
    keys.op = Operations(MigrationContext.configure(connection))
    keys.upgrade()

    connection.execute(sa.text("""
        INSERT INTO radar_quotes
            (id, ticker, market, mic, fetched_at, quote_ts, price, prev_close,
             volume)
        VALUES
            (2, 'COLLIDE', NULL, NULL, '2026-08-28 13:00:00', NULL,
             100.0, NULL, NULL),
            (3, 'COLLIDE', 'us', 'XNGS', '2026-08-28 13:00:00', NULL,
             200.0, NULL, NULL)
    """))
    connection.execute(sa.text("""
        INSERT INTO radar_daily_closes
            (ticker, market, mic, close_date, close, fetched_at)
        VALUES
            ('COLLIDE', NULL, NULL, '2026-08-27', 100.0,
             '2026-08-28 13:00:00'),
            ('COLLIDE', 'us', 'XNGS', '2026-08-27', 200.0,
             '2026-08-28 13:00:00')
    """))
    connection.commit()

    keys.downgrade()

    quote = connection.execute(sa.text("""
        SELECT market, mic, price FROM radar_quotes
        WHERE ticker = 'COLLIDE' AND fetched_at = '2026-08-28 13:00:00'
    """)).one()
    close = connection.execute(sa.text("""
        SELECT market, mic, close FROM radar_daily_closes
        WHERE ticker = 'COLLIDE' AND close_date = '2026-08-27'
    """)).one()
    assert tuple(quote) == (None, None, 100)
    assert tuple(close) == (None, None, 100)

    quote_ddl = connection.execute(sa.text(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'radar_quotes'")) \
        .scalar_one()
    close_ddl = connection.execute(sa.text(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'radar_daily_closes'")) \
        .scalar_one()
    assert 'utf8mb4_bin' in quote_ddl
    assert 'utf8mb4_bin' in close_ddl


def test_market_migration_rejects_unknown_market_but_keeps_null_price_rows(
        market_migration_db):
    """A typo cannot create a third market while the old writer uses NULL."""
    connection = market_migration_db
    migration = _load_market_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()
    connection.commit()

    invalid_inserts = (
        "INSERT INTO radar_instruments "
        "(ticker, market, venue, mic, provider_symbol, currency, isin, "
        "is_primary, mapping_status, mapping_source, mapped_at) VALUES "
        "('BADINST', 'uk', 'Test', 'XTST', 'BADINST', 'GBP', NULL, 0, "
        "'unverified', NULL, CURRENT_TIMESTAMP)",
        "INSERT INTO radar_quotes "
        "(id, ticker, market, fetched_at, quote_ts, price, prev_close, volume) "
        "VALUES (20, 'BADQUOTE', 'uk', '2026-08-28 12:10:00', NULL, "
        "1.0, NULL, NULL)",
        "INSERT INTO radar_daily_closes "
        "(ticker, market, close_date, close, fetched_at) VALUES "
        "('BADCLOSE', 'uk', '2026-08-28', 1.0, '2026-08-28 12:10:00')",
    )
    for statement in invalid_inserts:
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text(statement))
        connection.rollback()

    connection.execute(sa.text(
        "INSERT INTO radar_quotes "
        "(id, ticker, fetched_at, quote_ts, price, prev_close, volume) VALUES "
        "(21, 'LEGACY', '2026-08-28 12:11:00', NULL, 1.0, NULL, NULL)"))
    connection.execute(sa.text(
        "INSERT INTO radar_daily_closes "
        "(ticker, close_date, close, fetched_at) VALUES "
        "('LEGACY', '2026-08-28', 1.0, '2026-08-28 12:11:00')"))
    connection.commit()

    quote = connection.execute(sa.text(
        "SELECT market FROM radar_quotes WHERE id=21")).scalar_one()
    close = connection.execute(sa.text(
        "SELECT market FROM radar_daily_closes WHERE ticker='LEGACY'")) \
        .scalar_one()
    assert quote is None
    assert close is None


def test_market_migration_downgrade_prunes_de_context_but_keeps_us_and_null(
        market_migration_db):
    """Old ticker-only keys cannot safely represent a German price row."""
    connection = market_migration_db
    migration = _load_market_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()
    connection.commit()

    connection.execute(sa.text(
        "INSERT INTO radar_quotes "
        "(id, ticker, market, fetched_at, quote_ts, price, prev_close, volume) "
        "VALUES (30, 'USROW', 'us', '2026-08-28 12:20:00', NULL, "
        "1.0, NULL, NULL), "
        "(31, 'DEROW', 'de', '2026-08-28 12:21:00', NULL, "
        "1.0, NULL, NULL), "
        "(32, 'NULLROW', NULL, '2026-08-28 12:22:00', NULL, 1.0, NULL, NULL)"))
    connection.execute(sa.text(
        "INSERT INTO radar_daily_closes "
        "(ticker, market, close_date, close, fetched_at) VALUES "
        "('USCLOSE', 'us', '2026-08-28', 1.0, '2026-08-28 12:20:00'), "
        "('DECLOSE', 'de', '2026-08-28', 1.0, '2026-08-28 12:21:00'), "
        "('NULLCLOSE', NULL, '2026-08-28', 1.0, '2026-08-28 12:22:00')"))
    connection.commit()

    migration.downgrade()

    quote_tickers = connection.execute(sa.text(
        "SELECT ticker FROM radar_quotes ORDER BY id")).scalars().all()
    close_tickers = connection.execute(sa.text(
        "SELECT ticker FROM radar_daily_closes ORDER BY ticker")).scalars().all()
    assert quote_tickers == ['AAPL', 'USROW', 'NULLROW']
    assert close_tickers == ['AAPL', 'NULLCLOSE', 'USCLOSE']


def test_market_migration_downgrade_preserves_legacy_price_rows(
        market_migration_db):
    connection = market_migration_db
    migration = _load_market_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()
    migration.downgrade()

    quote_columns = {column['name'] for column in
                     sa.inspect(connection).get_columns('radar_quotes')}
    close_columns = {column['name'] for column in
                     sa.inspect(connection).get_columns('radar_daily_closes')}
    assert quote_columns == {
        'id', 'ticker', 'fetched_at', 'quote_ts', 'price', 'prev_close',
        'volume'}
    assert close_columns == {'ticker', 'close_date', 'close', 'fetched_at'}
    assert connection.execute(sa.text(
        "SELECT COUNT(*) FROM radar_quotes WHERE ticker='AAPL'")) .scalar_one() == 1
    assert connection.execute(sa.text(
        "SELECT COUNT(*) FROM radar_daily_closes WHERE ticker='AAPL'")) .scalar_one() == 1


# --- Market data v2 expand migration (plan Task 2) ---------------------------

def _load_market_data_v2_migration():
    path = (Path(__file__).parents[1] / 'migrations' / 'versions' /
            '6a21d4e8c9f0_add_radar_market_data_v2.py')
    assert path.exists(), 'market-data v2 migration is missing'
    spec = importlib.util.spec_from_file_location('radar_market_data_v2', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pre_v2_schema(connection, *, with_close_server_default=True):
    """The exact pre-6a21d4e8c9f0 shapes of the three touched tables.

    ``with_close_server_default`` exists for the broken-variant proof: the
    real migration must give is_shadow a server default so old-column-list
    inserts keep working.
    """
    metadata = sa.MetaData()
    sa.Table(
        'radar_quotes', metadata,
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.String(12), nullable=False),
        sa.Column('market', sa.String(2)),
        sa.Column('mic', sa.String(4)),
        sa.Column('currency', sa.String(3)),
        sa.Column('provider_symbol', sa.String(32)),
        sa.Column('fetched_at', sa.DateTime, nullable=False),
        sa.Column('quote_ts', sa.DateTime),
        sa.Column('price', sa.Numeric(18, 6), nullable=False),
        sa.Column('prev_close', sa.Numeric(18, 6)),
        sa.Column('regular_close', sa.Numeric(18, 6)),
        sa.Column('provider_delay', sa.String(8)),
        sa.Column('volume', sa.BigInteger),
        sa.UniqueConstraint('ticker', 'market', 'mic', 'fetched_at',
                            name='uq_radar_quote_market'),
    )
    sa.Table(
        'radar_daily_closes', metadata,
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.String(12), nullable=False),
        sa.Column('market', sa.String(2)),
        sa.Column('mic', sa.String(4)),
        sa.Column('currency', sa.String(3)),
        sa.Column('close_date', sa.Date, nullable=False),
        sa.Column('close', sa.Numeric(18, 4), nullable=False),
        sa.Column('fetched_at', sa.DateTime, nullable=False),
        sa.UniqueConstraint('ticker', 'market', 'mic', 'close_date',
                            name='uq_radar_daily_close_market'),
    )
    sa.Table(
        'radar_instruments', metadata,
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.String(12), nullable=False),
        sa.Column('market', sa.String(2), nullable=False),
        sa.Column('venue', sa.String(48), nullable=False),
        sa.Column('mic', sa.String(4), nullable=False),
        sa.Column('provider_symbol', sa.String(32), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('isin', sa.String(12)),
        sa.Column('is_primary', sa.Boolean, nullable=False),
        sa.Column('mapping_status', sa.String(12), nullable=False),
        sa.Column('mapping_source', sa.String(24)),
        sa.Column('mapped_at', sa.DateTime, nullable=False),
    )
    metadata.create_all(connection)
    connection.execute(sa.text(
        "INSERT INTO radar_quotes (id, ticker, market, mic, currency,"
        " provider_symbol, fetched_at, price) VALUES"
        " (1, 'AAPL', 'us', 'XNAS', 'USD', 'AAPL',"
        " '2026-08-28 12:00:00', 100.0)"))
    connection.execute(sa.text(
        "INSERT INTO radar_daily_closes (id, ticker, market, mic, currency,"
        " close_date, close, fetched_at) VALUES"
        " (1, 'AAPL', 'us', 'XNAS', 'USD', '2026-08-27', 99.0,"
        " '2026-08-28 12:00:00')"))
    return metadata


@pytest.fixture()
def v2_migration_db():
    engine = sa.create_engine('sqlite://')
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


def test_v2_upgrade_keeps_old_writers_valid_and_downgrade_preserves_rows(
        v2_migration_db):
    connection = v2_migration_db
    _pre_v2_schema(connection)
    migration = _load_market_data_v2_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()

    # An old writer's column list still inserts, and the new fields default.
    connection.execute(sa.text(
        "INSERT INTO radar_quotes (id, ticker, market, mic, currency,"
        " provider_symbol, fetched_at, price) VALUES"
        " (2, 'AAPL', 'us', 'XNAS', 'USD', 'AAPL',"
        " '2026-08-28 12:05:00', 101.0)"))
    connection.execute(sa.text(
        "INSERT INTO radar_daily_closes (id, ticker, market, mic, currency,"
        " close_date, close, fetched_at) VALUES"
        " (2, 'AAPL', 'us', 'XNAS', 'USD', '2026-08-28', 100.5,"
        " '2026-08-29 12:00:00')"))
    rows = connection.execute(sa.text(
        "SELECT is_shadow, source, price_basis FROM radar_quotes"
        " ORDER BY id")).all()
    assert [tuple(row) for row in rows] == [(0, None, None), (0, None, None)]

    # Live and shadow closes coexist for the same identity/date...
    connection.execute(sa.text(
        "INSERT INTO radar_daily_closes (id, ticker, market, mic, currency,"
        " close_date, close, fetched_at, source, price_basis,"
        " adjustment_basis, is_shadow) VALUES"
        " (3, 'AAPL', 'us', 'XNAS', 'USD', '2026-08-28', 100.6,"
        " '2026-08-29 12:00:00', 'massive_grouped', 'close', 'split', 1)"))
    # ...but a second live row for that identity/date still collides.
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_daily_closes (id, ticker, market, mic,"
            " currency, close_date, close, fetched_at) VALUES"
            " (4, 'AAPL', 'us', 'XNAS', 'USD', '2026-08-28', 100.7,"
            " '2026-08-29 12:01:00')"))

    migration.downgrade()
    close_columns = {column['name'] for column in
                     sa.inspect(connection).get_columns('radar_daily_closes')}
    assert 'is_shadow' not in close_columns
    assert 'adjustment_basis' not in close_columns
    # Both legacy rows survive; only the shadow row was removed.
    assert connection.execute(sa.text(
        "SELECT COUNT(*) FROM radar_daily_closes")).scalar_one() == 2
    assert connection.execute(sa.text(
        "SELECT COUNT(*) FROM radar_quotes")).scalar_one() == 2
    tables = set(sa.inspect(connection).get_table_names())
    assert 'radar_mapping_generations' not in tables
    assert 'radar_grouped_close_days' not in tables


def test_v2_broken_variant_four_column_close_key_rejects_shadow_pair(
        v2_migration_db):
    """Teeth: under the ORIGINAL four-column unique key the live+shadow pair
    the migration enables would collide -- proving the five-column key is
    what carries the behavior."""
    connection = v2_migration_db
    _pre_v2_schema(connection)
    connection.execute(sa.text(
        "ALTER TABLE radar_daily_closes ADD COLUMN is_shadow BOOLEAN"
        " NOT NULL DEFAULT 0"))
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_daily_closes (id, ticker, market, mic,"
            " currency, close_date, close, fetched_at, is_shadow) VALUES"
            " (5, 'AAPL', 'us', 'XNAS', 'USD', '2026-08-27', 99.5,"
            " '2026-08-28 13:00:00', 1)"))


def test_v2_broken_variant_missing_server_default_breaks_old_writers(
        v2_migration_db):
    """Teeth: without the server default an old-column-list insert dies,
    which is exactly what the expand contract forbids."""
    connection = v2_migration_db
    metadata = sa.MetaData()
    sa.Table(
        'radar_quotes', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('ticker', sa.String(12), nullable=False),
        sa.Column('fetched_at', sa.DateTime, nullable=False),
        sa.Column('price', sa.Numeric(18, 6), nullable=False),
        # The deliberately broken shape: NOT NULL without a server default.
        sa.Column('is_shadow', sa.Boolean, nullable=False),
    )
    metadata.create_all(connection)
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_quotes (id, ticker, fetched_at, price)"
            " VALUES (9, 'AAPL', '2026-08-28 12:06:00', 102.0)"))


def test_v2_operational_tables_round_trip_and_enforce_keys(v2_migration_db):
    connection = v2_migration_db
    _pre_v2_schema(connection)
    migration = _load_market_data_v2_migration()
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()

    connection.execute(sa.text(
        "INSERT INTO radar_grouped_close_days (source, close_date,"
        " is_shadow, status, fetched_at) VALUES"
        " ('massive_grouped', '2026-08-28', 1, 'accepted',"
        " '2026-08-29 00:00:00')"))
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_grouped_close_days (source, close_date,"
            " is_shadow, status, fetched_at) VALUES"
            " ('massive_grouped', '2026-08-28', 1, 'accepted',"
            " '2026-08-29 01:00:00')"))
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_grouped_close_days (source, close_date,"
            " is_shadow, status, fetched_at) VALUES"
            " ('massive_grouped', '2026-08-29', 1, 'made_up_status',"
            " '2026-08-30 00:00:00')"))

    connection.execute(sa.text(
        "INSERT INTO radar_provider_session_states (source, market,"
        " last_post_close_session_date, claimed_at) VALUES"
        " ('finnhub', 'us', '2026-08-28', '2026-08-28 21:05:00')"))
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_provider_session_states (source, market)"
            " VALUES ('finnhub', 'us')"))

    # Modern adjustment provenance is split-only; migration-era NULL passes.
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_daily_closes (id, ticker, market, mic,"
            " currency, close_date, close, fetched_at, source, price_basis,"
            " adjustment_basis) VALUES"
            " (6, 'MSFT', 'us', 'XNAS', 'USD', '2026-08-28', 55.0,"
            " '2026-08-29 12:00:00', 'yahoo_chart', 'close', 'dividend')"))
    connection.execute(sa.text(
        "INSERT INTO radar_daily_closes (id, ticker, market, mic, currency,"
        " close_date, close, fetched_at) VALUES"
        " (7, 'MSFT', 'us', 'XNAS', 'USD', '2026-08-27', 54.0,"
        " '2026-08-28 12:00:00')"))
    # massive_grouped can never be a QUOTE source.
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text(
            "INSERT INTO radar_quotes (id, ticker, market, mic, currency,"
            " provider_symbol, fetched_at, price, source, price_basis)"
            " VALUES (8, 'MSFT', 'us', 'XNAS', 'USD', 'MSFT',"
            " '2026-08-28 12:07:00', 54.5, 'massive_grouped', 'close')"))
