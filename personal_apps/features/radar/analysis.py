"""HA1 US Daily Explore: the bounded authenticated reader.

Two questions, answered from the existing store with at most two and four
SELECTs respectively and nothing else:

- `resolve_company(ticker)`: the current catalogue company for a symbol and
  its one eligible native-USD US primary instrument, by ID.
- `read_company(company_id, instrument_id, start, end)`: that pair
  revalidated, then the selected instrument's live daily closes and the
  ticker's retained per-source buckets for the requested completed UTC days,
  reduced by `analysis_contract` into two independent series.

What it deliberately does not do: call `history.resolve_basis` (which picks
the most populated venue/currency and drops one-close candidates), expand
today's source configuration, join posts/judgments, scan the universe or a
peer calendar, retry, cache, or fall back to another instrument. A store
error is an honest 503, never a 200 with an empty series.

The time budget. One monotonic budget of `READER_DEADLINE_S` covers the whole
read. Each SELECT is statement-scoped (MariaDB `SET STATEMENT
max_statement_time=... FOR`, which leaves the pooled connection's session
untouched) to min(`STATEMENT_TIMEOUT_S`, what is left of the budget), in
millisecond-floored fractional seconds; a statement with less than a
millisecond left is refused before it is sent, because a zero
max_statement_time would mean "unlimited". The budget is checked again after
each statement's rows are materialized and after the reducers run.

What the budget does NOT bound, pending runtime proof on a MariaDB target:
waiting for a pooled connection before the statement starts, the network
transfer of an already-produced result, and whether the server cancels the
statement promptly when the limit fires. Those are recorded, not claimed.

Binding: radar-design/HA1-US-DAILY-EXPLORE-SPEC.md sections 4-7.
"""
from __future__ import annotations

import datetime as dt
import math
import time

import sqlalchemy as sa
from sqlalchemy import exc as sa_exc

from extensions import db

from . import analysis_contract as contract
from .analysis_contract import ContractError

STATEMENT_TIMEOUT_S = 2.0
READER_DEADLINE_S = 5.0
#: The smallest statement limit worth sending. MariaDB reads
#: max_statement_time=0 as NO limit, so nothing below this is ever rendered.
MIN_STATEMENT_S = 0.001
SCHEMA_VERSION = 1

#: MariaDB 1969 "Query execution was interrupted (max_statement_time
#: exceeded)"; MySQL 3024 "Query execution was interrupted, maximum statement
#: execution time exceeded". Anything else is a store failure.
TIMEOUT_ERRNOS = frozenset({1969, 3024})

COMPANY_BY_SYMBOL = """
SELECT id, symbol, name, first_seen, delisted_at
FROM radar_ticker_universe
WHERE symbol = :ticker
LIMIT 2
"""

COMPANY_BY_ID = """
SELECT id, symbol, name, first_seen, delisted_at
FROM radar_ticker_universe
WHERE id = :company_id
LIMIT 1
"""

PRIMARY_CANDIDATES = """
SELECT id, ticker, market, venue, mic, provider_symbol, currency,
       is_primary, mapping_status, mapped_at
FROM radar_instruments
WHERE ticker = :ticker AND market = 'us' AND is_primary = 1
LIMIT 2
"""

INSTRUMENT_BY_ID = """
SELECT id, ticker, market, venue, mic, provider_symbol, currency,
       is_primary, mapping_status, mapped_at
FROM radar_instruments
WHERE id = :instrument_id
LIMIT 1
"""

DAILY_CLOSES = """
SELECT close_date, close, currency, source, price_basis,
       adjustment_basis, fetched_at, market, mic, is_shadow
FROM radar_daily_closes
WHERE ticker = :ticker AND market = 'us' AND mic = :mic AND is_shadow = 0
  AND close_date >= :from_date AND close_date <= :to_date
  AND fetched_at <= :read_start
ORDER BY close_date
LIMIT :row_limit
"""

BUCKET_SOURCES = """
SELECT bucket_start, source, mention_count, status, source_config_version
FROM radar_bucket_sources
WHERE ticker = :ticker AND bucket_start >= :utc_start AND bucket_start < :utc_end
ORDER BY bucket_start, source
LIMIT :row_limit
"""


def utc_window(start: dt.date, end: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """[start 00:00Z, end+1 00:00Z), naive UTC, the chatter read's bounds."""
    return (dt.datetime.combine(start, dt.time()),
            dt.datetime.combine(end + dt.timedelta(days=1), dt.time()))


def closes_params(ticker, mic, start, end, read_start) -> dict:
    return {'ticker': ticker, 'mic': mic, 'from_date': start, 'to_date': end,
            'read_start': read_start, 'row_limit': contract.DAILY_ROW_SENTINEL}


def buckets_params(ticker, start, end) -> dict:
    utc_start, utc_end = utc_window(start, end)
    return {'ticker': ticker, 'utc_start': utc_start, 'utc_end': utc_end,
            'row_limit': contract.BUCKET_ROW_SENTINEL}


def data_statements(company_id, instrument_id, ticker, mic, start, end, read_start):
    """The four data SELECTs of `read_company`, in order, as the named SQL
    and the exact binds the store sends. The measurement harness EXPLAINs
    these rather than re-wrapping driver-level SQL it captured."""
    return [
        ('company_by_id', COMPANY_BY_ID, {'company_id': company_id}),
        ('instrument_by_id', INSTRUMENT_BY_ID, {'instrument_id': instrument_id}),
        ('daily_closes', DAILY_CLOSES, closes_params(ticker, mic, start, end, read_start)),
        ('bucket_sources', BUCKET_SOURCES, buckets_params(ticker, start, end)),
    ]


def seconds_literal(timeout_s: float) -> str:
    """A MariaDB max_statement_time value: fractional seconds, floored to the
    millisecond. Never `0`, which MariaDB reads as no limit at all."""
    millis = math.floor(timeout_s * 1000)
    if millis < 1:
        raise ContractError('analysis_limit', 503,
                            'the read exceeded its total deadline')
    return f'{millis / 1000:.3f}'


def millis_literal(timeout_s: float) -> int:
    """A MySQL MAX_EXECUTION_TIME value: whole milliseconds, floored, never 0."""
    millis = math.floor(timeout_s * 1000)
    if millis < 1:
        raise ContractError('analysis_limit', 503,
                            'the read exceeded its total deadline')
    return millis


class SqlStore:
    """The selected reads, on the application's engine.

    A store's only job is to run one bounded statement under the limit the
    reader hands it and give back plain mappings. The reader owns identity
    rules, limits and the budget.
    """

    def __init__(self, session=None):
        self._session = session

    @property
    def session(self):
        return self._session if self._session is not None else db.session

    def _timed(self, sql: str, timeout_s: float) -> str:
        """Statement-scoped timeout in the dialect's own syntax, or none.

        MariaDB: `SET STATEMENT max_statement_time=N.NNN FOR <select>` --
        scoped to this statement, so the pooled connection's session is
        unchanged on return. MySQL: the optimizer hint in milliseconds. Other
        engines (SQLite in tests) have no statement timeout; that is
        recorded, not disguised.
        """
        dialect = self.session.get_bind().dialect
        stripped = sql.strip()
        if dialect.name == 'mysql' and getattr(dialect, 'is_mariadb', False):
            return f'SET STATEMENT max_statement_time={seconds_literal(timeout_s)} FOR {stripped}'
        if dialect.name == 'mysql':
            return stripped.replace(
                'SELECT', f'SELECT /*+ MAX_EXECUTION_TIME({millis_literal(timeout_s)}) */', 1)
        return stripped

    def timeout_dialect(self) -> str:
        dialect = self.session.get_bind().dialect
        if dialect.name == 'mysql' and getattr(dialect, 'is_mariadb', False):
            return 'mariadb:set_statement'
        if dialect.name == 'mysql':
            return 'mysql:max_execution_time'
        return f'{dialect.name}:none'

    def _rows(self, sql: str, timeout_s: float, **params) -> list[dict]:
        timed = self._timed(sql, timeout_s)
        try:
            result = self.session.execute(sa.text(timed), params)
            return [dict(row) for row in result.mappings().all()]
        except sa_exc.DBAPIError as exc:
            # Nothing was written, but a failed statement leaves the session
            # in a state the next request must not inherit.
            self.session.rollback()
            errno = _errno(exc)
            if errno in TIMEOUT_ERRNOS:
                raise ContractError('analysis_limit', 503,
                                    'the store did not answer within the bounded time') from exc
            raise ContractError('analysis_unavailable', 503,
                                'the store could not be read') from exc
        except sa_exc.SQLAlchemyError as exc:
            self.session.rollback()
            raise ContractError('analysis_unavailable', 503,
                                'the store could not be read') from exc

    def company_by_symbol(self, ticker: str, *, timeout_s: float) -> list[dict]:
        return self._rows(COMPANY_BY_SYMBOL, timeout_s, ticker=ticker)

    def company_by_id(self, company_id: int, *, timeout_s: float) -> list[dict]:
        return self._rows(COMPANY_BY_ID, timeout_s, company_id=company_id)

    def primary_candidates(self, ticker: str, *, timeout_s: float) -> list[dict]:
        return self._rows(PRIMARY_CANDIDATES, timeout_s, ticker=ticker)

    def instrument_by_id(self, instrument_id: int, *, timeout_s: float) -> list[dict]:
        return self._rows(INSTRUMENT_BY_ID, timeout_s, instrument_id=instrument_id)

    def daily_closes(self, ticker, mic, start, end, read_start, *, timeout_s: float) -> list[dict]:
        return self._rows(DAILY_CLOSES, timeout_s,
                          **closes_params(ticker, mic, start, end, read_start))

    def bucket_sources(self, ticker, start, end, *, timeout_s: float) -> list[dict]:
        return self._rows(BUCKET_SOURCES, timeout_s, **buckets_params(ticker, start, end))


def _errno(exc) -> int | None:
    orig = getattr(exc, 'orig', None)
    args = getattr(orig, 'args', None) or ()
    if args and isinstance(args[0], int):
        return args[0]
    return None


def _now_naive(now_utc: dt.datetime) -> dt.datetime:
    if now_utc.tzinfo is None:
        raise ValueError('now_utc must be timezone-aware')
    return now_utc.astimezone(dt.timezone.utc).replace(tzinfo=None)


class ReaderBudget:
    """The whole read's monotonic time budget.

    `statement_timeout()` is what the next statement may use: min(the
    per-statement cap, what is left), refused outright when under a
    millisecond is left. `check()` refuses once the budget is spent; the
    reader calls it after each statement's rows are materialized and after
    reduction.
    """

    def __init__(self, seconds: float = None, statement_cap: float = None):
        self.seconds = READER_DEADLINE_S if seconds is None else seconds
        self.statement_cap = STATEMENT_TIMEOUT_S if statement_cap is None else statement_cap
        self.started = time.monotonic()

    def remaining(self) -> float:
        return self.seconds - (time.monotonic() - self.started)

    def statement_timeout(self) -> float:
        remaining = self.remaining()
        if remaining < MIN_STATEMENT_S:
            raise ContractError('analysis_limit', 503,
                                'the read exceeded its total deadline')
        return min(self.statement_cap, remaining)

    def check(self):
        if self.remaining() <= 0:
            raise ContractError('analysis_limit', 503,
                                'the read exceeded its total deadline')


# --- identity -----------------------------------------------------------------

def _company(row) -> dict:
    return {'id': int(row['id']), 'ticker': row['symbol'], 'name': row.get('name'),
            'first_seen': contract._iso_z(contract._naive_utc(row['first_seen']))}


def _instrument(row) -> dict:
    return {'id': int(row['id']), 'ticker': row['ticker'], 'market': row['market'],
            'mic': (row.get('mic') or '').strip(), 'venue': (row.get('venue') or '').strip(),
            'currency': row.get('currency'),
            'provider_symbol': (row.get('provider_symbol') or '').strip(),
            'mapped_at': contract._iso_z(contract._naive_utc(row['mapped_at']))}


def _eligibility(row, read_start) -> str | None:
    """Why an instrument row is not an eligible native-USD US primary, or
    None. The MD-01C predicate, applied to at most two rows in Python so a
    second primary is refused rather than hidden by `.first()`."""
    if row.get('market') != 'us':
        return 'not a US instrument'
    if not row.get('is_primary'):
        return 'not the primary instrument'
    if row.get('mapping_status') != 'mapped':
        return 'mapping is not confirmed'
    if row.get('currency') != 'USD':
        return 'not a native USD instrument'
    for field in ('mic', 'provider_symbol', 'venue'):
        if not (row.get(field) or '').strip():
            return f'{field} is missing'
    mapped_at = contract._naive_utc(row.get('mapped_at'))
    if mapped_at is None or mapped_at > read_start:
        return 'mapping date is missing or later than this read'
    return None


def _active_company(rows, *, missing_code: str) -> dict:
    if not rows:
        raise ContractError(missing_code, 404, 'no such company in the current catalogue')
    row = rows[0]
    if row.get('delisted_at') is not None:
        raise ContractError('delisted_company', 404,
                            'that symbol is delisted in the current catalogue')
    return row


def resolve_company(ticker: str, now_utc: dt.datetime, store=None) -> dict:
    """The current company for `ticker` and its one eligible US primary.

    Two SELECTs. Zero eligible candidates is 422; two is 409; an unknown or
    delisted symbol is 404. Nothing is guessed from another venue.
    """
    symbol = contract.valid_ticker(ticker)
    store = store or SqlStore()
    read_start = _now_naive(now_utc)
    budget = ReaderBudget()
    company = _active_company(
        store.company_by_symbol(symbol, timeout_s=budget.statement_timeout()),
        missing_code='unknown_company')
    budget.check()
    candidates = store.primary_candidates(symbol, timeout_s=budget.statement_timeout())
    budget.check()
    eligible = [row for row in candidates if _eligibility(row, read_start) is None]
    if len(eligible) > 1:
        raise ContractError('ambiguous_primary', 409,
                            'more than one eligible US primary instrument is mapped')
    if not eligible:
        reasons = sorted({_eligibility(row, read_start) for row in candidates})
        raise ContractError('ineligible_instrument', 422,
                            'no eligible native-USD US primary instrument: '
                            + ('; '.join(r for r in reasons if r) or 'none mapped'))
    return {'company': _company(company), 'instrument': _instrument(eligible[0])}


def read_company(company_id: int, instrument_id: int, start: dt.date, end: dt.date,
                 now_utc: dt.datetime, store=None) -> dict:
    """The full retrospective payload for one pinned (company, instrument).

    Four data SELECTs in order: company, instrument, closes, buckets. The
    chosen mapping is revalidated on every call; an old bookmark whose IDs no
    longer name the same eligible current mapping fails with 409 rather than
    being retargeted. A pinned read does not scan for a later second primary
    (the resolver refuses ambiguity), so it claims nothing about global
    uniqueness.
    """
    if (end - start).days + 1 > contract.MAX_DAYS or end < start:
        raise ContractError('range_too_long', 400, 'invalid range')
    store = store or SqlStore()
    read_start = _now_naive(now_utc)
    budget = ReaderBudget()

    company_row = _active_company(
        store.company_by_id(company_id, timeout_s=budget.statement_timeout()),
        missing_code='unknown_company')
    budget.check()
    instrument_rows = store.instrument_by_id(instrument_id, timeout_s=budget.statement_timeout())
    budget.check()
    if not instrument_rows:
        raise ContractError('unknown_instrument', 404, 'no such instrument')
    instrument_row = instrument_rows[0]
    if instrument_row.get('ticker') != company_row.get('symbol'):
        raise ContractError('identity_changed', 409,
                            'the instrument no longer belongs to that company')
    reason = _eligibility(instrument_row, read_start)
    if reason in ('not a US instrument', 'not the primary instrument',
                  'mapping is not confirmed'):
        raise ContractError('identity_changed', 409,
                            f'the mapped primary changed: {reason}')
    if reason is not None:
        raise ContractError('ineligible_instrument', 422, reason)

    company = _company(company_row)
    instrument = _instrument(instrument_row)
    close_rows = store.daily_closes(instrument['ticker'], instrument['mic'],
                                    start, end, read_start,
                                    timeout_s=budget.statement_timeout())
    budget.check()
    if len(close_rows) > contract.DAILY_ROW_LIMIT:
        raise ContractError('analysis_limit', 503,
                            'more retained daily rows than the bounded reader expects')
    bucket_rows = store.bucket_sources(instrument['ticker'], start, end,
                                       timeout_s=budget.statement_timeout())
    budget.check()
    if len(bucket_rows) > contract.BUCKET_ROW_LIMIT:
        raise ContractError('analysis_limit', 503,
                            'more retained bucket rows than the bounded reader supports')

    first_seen = contract._naive_utc(company_row['first_seen'])
    price = contract.price_days(close_rows, instrument, first_seen, start, end,
                                contract.calendar_for(instrument['mic']),
                                read_started_at=read_start)
    chatter = contract.chatter_days(bucket_rows, start, end, first_seen)
    budget.check()
    warnings = ['identity: current mapping applied retrospectively; the '
                'company record is a conservative boundary, not a verified '
                'historical identity']
    warnings += price.pop('warnings')
    warnings += chatter.pop('warnings')
    if instrument['mic'] not in contract.KNOWN_US_MICS:
        warnings.append(f'calendar: no modeled calendar for MIC {instrument["mic"]}; '
                        'trading-day hints are unknown')
    read_finished = _now_naive(dt.datetime.now(dt.timezone.utc))
    return {
        'schema_version': SCHEMA_VERSION,
        'mode': 'retrospective',
        'company': company,
        'instrument': instrument,
        'identity_scope': 'current_mapping_retrospective',
        'request': {'from': start.isoformat(), 'to': end.isoformat(),
                    'chatter_timezone': 'UTC', 'max_days': contract.MAX_DAYS},
        'read_started_at': contract._iso_z(read_start),
        'read_finished_at': contract._iso_z(read_finished),
        'price': price,
        'chatter': chatter,
        'warnings': warnings,
    }
