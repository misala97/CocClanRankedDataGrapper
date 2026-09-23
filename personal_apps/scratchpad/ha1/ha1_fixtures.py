"""Owned HA1 fixture rows and the statement-timeout probe, on a gated target.

Import only AFTER scratchpad/ha1/local_runtime.py gate() and bind(), or the
API suite's module gate, have passed: this module imports the models and its
functions execute SQL.

Ownership (REVIEW-1 P1-1, CORRECTION-1): every symbol and username is
generated for the run; `ha1_harness.OwnedFixtures` refuses before any
mutation when any of them already exists in a touched table; every created
row's exact key is recorded; cleanup deletes only those keys (ids together
with their owning symbol, bucket rows by full primary key) and verifies none
remain. No LIKE, no prefix match, no adoption of a row the run did not create.

CORRECTION-1 (2026-09-15): written; its statements are compiled DB-free in
tests/ha1_unit/test_ha1_harness.py. Not executed against any database.
"""
from __future__ import annotations

import datetime as dt
import decimal
import time

import sqlalchemy as sa
from sqlalchemy import orm
from werkzeug.security import generate_password_hash

from models import (AppUser, RadarBucketSource, RadarDailyClose, RadarInstrument,
                    TickerUniverse)

import ha1_harness as harness

CHUNK = 500
FIRST_SEEN = dt.datetime(2026, 1, 1)
MAPPED_AT = dt.datetime(2026, 8, 1)

_ID_TABLES = {
    'company': (TickerUniverse.__table__, 'symbol', 'symbol'),
    'instrument': (RadarInstrument.__table__, 'ticker', 'ticker'),
    'close': (RadarDailyClose.__table__, 'ticker', 'ticker'),
    'user': (AppUser.__table__, 'username', 'username'),
}


def _chunks(items, size=CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _predicate(kind, keys):
    if kind == 'bucket':
        table = RadarBucketSource.__table__
        return table, sa.tuple_(table.c.ticker, table.c.bucket_start, table.c.source).in_(
            [(key['ticker'], key['bucket_start'], key['source']) for key in keys])
    table, column, key_name = _ID_TABLES[kind]
    return table, sa.and_(
        table.c.id.in_([int(key['id']) for key in keys]),
        table.c[column].in_(sorted({key[key_name] for key in keys})))


def delete_statements(kind, keys):
    for chunk in _chunks(keys):
        table, predicate = _predicate(kind, chunk)
        yield sa.delete(table).where(predicate)


def count_statements(kind, keys):
    for chunk in _chunks(keys):
        table, predicate = _predicate(kind, chunk)
        yield sa.select(sa.func.count()).select_from(table).where(predicate)


def existence_statements(symbols, usernames):
    symbols, usernames = sorted(symbols), sorted(usernames)
    statements = []
    if symbols:
        statements += [
            ('radar_ticker_universe',
             sa.select(TickerUniverse.symbol).where(TickerUniverse.symbol.in_(symbols))),
            ('radar_instruments',
             sa.select(RadarInstrument.ticker).where(RadarInstrument.ticker.in_(symbols)).distinct()),
            ('radar_daily_closes',
             sa.select(RadarDailyClose.ticker).where(RadarDailyClose.ticker.in_(symbols)).distinct()),
            ('radar_bucket_sources',
             sa.select(RadarBucketSource.ticker).where(RadarBucketSource.ticker.in_(symbols)).distinct()),
        ]
    if usernames:
        statements.append(
            ('app_user', sa.select(AppUser.username).where(AppUser.username.in_(usernames))))
    return statements


class SqlFixtureStore:
    """The OwnedFixtures store on a SQLAlchemy session (or a callable that
    returns one inside whichever app context is active)."""

    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session() if isinstance(self._session, type(lambda: None)) else self._session

    def existing(self, symbols, usernames):
        session = self.session
        found = {table: list(session.execute(statement).scalars().all())
                 for table, statement in existence_statements(symbols, usernames)}
        session.rollback()
        return found

    def prepare_cleanup(self):
        self.session.rollback()

    def delete(self, kind, keys):
        session = self.session
        for statement in delete_statements(kind, keys):
            session.execute(statement)
        session.commit()

    def count_owned(self, kind, keys):
        session = self.session
        total = sum(int(session.execute(statement).scalar() or 0)
                    for statement in count_statements(kind, keys))
        session.rollback()
        return total


# --- seeding (every row recorded by exact key) ----------------------------------------

def add_company(owned, session, symbol, *, first_seen=FIRST_SEEN, name=None, delisted_at=None):
    row = TickerUniverse(symbol=symbol, name=name if name is not None else f'{symbol} HA1 fixture',
                         exchange='N', first_seen=first_seen, delisted_at=delisted_at,
                         market_cap=decimal.Decimal('1000000'))
    session.add(row)
    session.flush()
    owned.record('company', {'id': int(row.id), 'symbol': symbol})
    return int(row.id)


def add_instrument(owned, session, symbol, *, market='us', mic='XNYS', venue='NYSE',
                   currency='USD', primary=True, status='mapped', mapped_at=MAPPED_AT,
                   provider=None):
    row = RadarInstrument(ticker=symbol, market=market, mic=mic, venue=venue,
                          provider_symbol=provider if provider is not None else symbol,
                          currency=currency, is_primary=primary, mapping_status=status,
                          mapped_at=mapped_at)
    session.add(row)
    session.flush()
    owned.record('instrument', {'id': int(row.id), 'ticker': symbol})
    return int(row.id)


def add_close(owned, session, symbol, day, *, close='10.50', market='us', mic='XNYS',
              currency='USD', source='massive_grouped', basis='close', adjustment='split',
              shadow=False, fetched_at=None):
    row = RadarDailyClose(ticker=symbol, market=market, mic=mic, currency=currency,
                          close_date=day, close=decimal.Decimal(close), source=source,
                          price_basis=basis, adjustment_basis=adjustment, is_shadow=shadow,
                          fetched_at=fetched_at or dt.datetime.combine(day, dt.time(23)))
    session.add(row)
    session.flush()
    owned.record('close', {'id': int(row.id), 'ticker': symbol})
    return int(row.id)


def bucket_rows(symbol, day, source, *, slots=range(96), count=1, status='ok', config='cfgA'):
    return [{'ticker': symbol, 'source': source, 'mention_count': count, 'status': status,
             'source_config_version': config,
             'bucket_start': dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=15 * slot)}
            for slot in slots]


def add_buckets(owned, session, rows):
    rows = list(rows)
    for row in rows:
        owned.record('bucket', {'ticker': row['ticker'], 'bucket_start': row['bucket_start'],
                                'source': row['source']})
    for chunk in _chunks(rows, 5000):
        session.execute(sa.insert(RadarBucketSource), chunk)
    return len(rows)


def add_user(owned, session, username, password, *, is_admin=False):
    row = AppUser(username=username, password_hash=generate_password_hash(password),
                  is_admin=is_admin)
    session.add(row)
    session.flush()
    owned.record('user', {'id': int(row.id), 'username': username})
    return int(row.id)


# --- statement timeout on ONE physical connection --------------------------------------

def timeout_probe(engine, limit_s: float, *, sleep_s: int = 3,
                  subsecond_s: float = harness.SUBSECOND_REQUEST_S):
    """Run a SLEEP and a CPU-bound SELECT through the production SqlStore
    under `limit_s`, on one checked-out connection, and record the
    connection id and its session max_statement_time before and after.
    Classification and pass/fail are ha1_harness.timeout_failures.

    CORRECTION-2 (U5): then a CPU-bound SELECT under a SUB-SECOND limit that
    the production logic computes -- ReaderBudget(subsecond_s)
    .statement_timeout(), rendered by SqlStore._timed/seconds_literal -- with
    requested and effective limits, the rendered prefix, elapsed time and
    overshoot recorded, the budget's post-hoc check outcome, and a normal
    statement on the same connection afterwards (recovery). Not executed."""
    from features.radar import analysis as analysis_mod
    from features.radar.analysis_contract import ContractError

    result = {'limit_s': limit_s, 'probes': {},
              'dialect': 'mariadb:set_statement' if getattr(engine.dialect, 'is_mariadb', False)
              else f'{engine.dialect.name}:not-mariadb'}
    if not result['dialect'].startswith('mariadb'):
        return result
    with engine.connect() as conn:
        result['connection_id_before'] = int(conn.exec_driver_sql('SELECT CONNECTION_ID()').scalar())
        result['session_max_statement_time_before'] = str(
            conn.exec_driver_sql('SELECT @@session.max_statement_time').scalar())
        conn.rollback()
        session = orm.Session(bind=conn)
        try:
            store = analysis_mod.SqlStore(session)
            result['dialect'] = store.timeout_dialect()
            for kind, sql, params, requested in (
                    ('sleep', 'SELECT SLEEP(:seconds) AS value', {'seconds': sleep_s}, float(sleep_s)),
                    ('cpu', harness.CPU_PROBE_SQL, {}, None)):
                errno = returned = code = None
                started = time.perf_counter()
                try:
                    rows = store._rows(sql, limit_s, **params)
                    value = rows[0].get('value') if rows else None
                    returned = int(value) if value is not None else None
                except ContractError as error:
                    code = error.code
                    errno = analysis_mod._errno(error.__cause__)
                elapsed = time.perf_counter() - started
                result['probes'][kind] = {
                    'errno': errno, 'code': code, 'returned': returned,
                    'elapsed_s': round(elapsed, 3), 'requested_s': requested,
                    'classification': harness.classify_timeout(kind, errno, returned, elapsed, requested),
                }

            # U5: sub-second, through the production budget and rendering.
            budget = analysis_mod.ReaderBudget(seconds=subsecond_s)
            effective = budget.statement_timeout()
            rendered = store._timed('SELECT 1', effective)
            errno = returned = code = None
            started = time.perf_counter()
            try:
                rows = store._rows(harness.CPU_PROBE_SQL, effective)
                value = rows[0].get('value') if rows else None
                returned = int(value) if value is not None else None
            except ContractError as error:
                code = error.code
                errno = analysis_mod._errno(error.__cause__)
            elapsed = time.perf_counter() - started
            try:
                budget.check()
                post_hoc = 'budget_not_expired'
            except ContractError as error:
                post_hoc = f'refused:{error.code}'
            result['probes']['cpu_subsecond'] = {
                'errno': errno, 'code': code, 'returned': returned,
                'requested_s': subsecond_s, 'effective_s': effective,
                'rendered': rendered.split(' FOR ')[0] + ' FOR',
                'elapsed_s': round(elapsed, 3),
                'overshoot_s': round(elapsed - effective, 3),
                'budget_check_after': post_hoc,
                'classification': harness.classify_timeout('cpu', errno, returned, elapsed, None),
            }
            try:
                recovered = store._rows('SELECT 1 AS value', analysis_mod.STATEMENT_TIMEOUT_S)
                result['recovery_ok'] = bool(recovered) and int(recovered[0].get('value')) == 1
            except ContractError as error:
                result['recovery_ok'] = False
                result['recovery_error'] = error.code
        finally:
            session.close()
        result['connection_id_after'] = int(conn.exec_driver_sql('SELECT CONNECTION_ID()').scalar())
        result['session_max_statement_time_after'] = str(
            conn.exec_driver_sql('SELECT @@session.max_statement_time').scalar())
        conn.rollback()
    return result
