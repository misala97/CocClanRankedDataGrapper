"""Selected price charts: the bounded local reader.

For one selected ticker and one computed window it answers, from the store
and nothing else:

- identity: the current catalogue company and its one eligible native-USD US
  primary instrument, by HA1's eligibility rule (referenced, not edited);
- chatter: the selected concrete sources' retained 15-minute buckets for
  exactly the window, reduced to the window's own slots;
- tone: retained recorded-judgment partitions of those buckets, optional;
- fallback: the instrument's own retained event-time quotes (1D) or stored
  daily closes, when the provider series is not ready.

Every statement is statement-scoped to at most `STATEMENT_TIMEOUT_S` by
HA1's SqlStore technique (MariaDB `SET STATEMENT max_statement_time=... FOR`)
inside one monotonic budget of `READER_DEADLINE_S`, checked again after each
statement's rows are materialized. A cold request sends at most six SELECTs:
two identity, one bucket, at most two fallback, at most one tone. Tone is the
only optional read: when it times out, overflows or fails, the counts and the
price stand and tone is unavailable.

What the budget does NOT bound (as in HA1): waiting for a pooled connection,
transfer of an already produced result, and whether the server cancels
promptly. No provider I/O ever happens here.

A 30-second process-local cache keyed by identity fingerprint, window and
source selection avoids re-running the count/tone/fallback reads during a
pending poll. It holds the WINDOW it was read for, so a reused entry answers
with the same from/to its counts were read over. Store failures are never
cached.

Binding: radar-design/MD-SELECTED-PRICE-SPEC.md sections 4, 5 and 7.
"""
from __future__ import annotations

import collections
import contextlib
import datetime as dt
import json
import threading
import time

import sqlalchemy as sa
from sqlalchemy import exc as sa_exc

from . import analysis
from . import analysis_contract
from . import config
from . import price_chart_contract as contract
from .analysis_contract import ContractError
from .price_chart_contract import ChartError

STATEMENT_TIMEOUT_S = 1.0
READER_DEADLINE_S = 3.0
LOCAL_CACHE_SECONDS = 30.0
LOCAL_CACHE_ENTRIES = 64
LOCAL_CACHE_BYTES = 16 * 1024 * 1024

BUCKET_ROWS = """
SELECT bucket_start, source, mention_count, status, source_config_version
FROM radar_bucket_sources
WHERE ticker = :ticker AND source IN :sources
  AND bucket_start >= :window_start AND bucket_start < :window_end
ORDER BY bucket_start, source
LIMIT :row_limit
"""

QUOTE_ROWS = """
SELECT quote_ts, price, source, price_basis, currency, market, mic, fetched_at, is_shadow
FROM radar_quotes
WHERE ticker = :ticker AND market = 'us' AND mic = :mic AND is_shadow = 0
  AND quote_ts IS NOT NULL AND quote_ts >= :window_start AND quote_ts <= :window_end
  AND fetched_at <= :read_start
ORDER BY quote_ts, fetched_at
LIMIT :row_limit
"""

DAILY_ROWS = """
SELECT close_date, close, currency, source, price_basis, adjustment_basis,
       fetched_at, market, mic, is_shadow
FROM radar_daily_closes
WHERE ticker = :ticker AND market = 'us' AND mic = :mic AND is_shadow = 0
  AND close_date >= :from_date AND close_date <= :to_date
  AND fetched_at <= :read_start
ORDER BY close_date
LIMIT :row_limit
"""

_CONFLICT = ("CASE WHEN m.sentiment_relevance = 'irrelevant' "
             "OR m.sentiment_content_origin = 'broadcast_or_automated' THEN 1 ELSE 0 END")

#: chatter_tone._event_partitions as bounded SQL text, the classification in
#: classify_recorded_tone's order. One event is valid only with exactly one
#: joined mention and no eligibility conflict; an invalid event is
#: unavailable. tests/selected_price_unit/test_reader.py runs this against
#: SQLite and compares every attitude/verdict pair to classify_recorded_tone.
TONE_ROWS = f"""
SELECT er.source AS source, er.bucket_start AS bucket_start, COUNT(*) AS total,
       SUM(er.eligibility_conflicts) AS eligibility_conflicts,
       SUM(CASE WHEN er.category = 'bullish' THEN 1 ELSE 0 END) AS bullish,
       SUM(CASE WHEN er.category = 'bearish' THEN 1 ELSE 0 END) AS bearish,
       SUM(CASE WHEN er.category = 'neutral' THEN 1 ELSE 0 END) AS neutral,
       SUM(CASE WHEN er.category = 'unjudged' THEN 1 ELSE 0 END) AS unjudged,
       SUM(CASE WHEN er.category = 'unavailable' THEN 1 ELSE 0 END) AS unavailable
FROM (
  SELECT e.id AS event_id, e.source AS source, e.bucket_start AS bucket_start,
         SUM({_CONFLICT}) AS eligibility_conflicts,
         CASE
           WHEN COUNT(m.id) <> 1 OR SUM({_CONFLICT}) <> 0 THEN 'unavailable'
           WHEN MAX(m.sentiment_attitude) = 'positive' THEN 'bullish'
           WHEN MAX(m.sentiment_attitude) = 'negative' THEN 'bearish'
           WHEN MAX(m.sentiment_attitude) IN ('mixed', 'none') THEN 'neutral'
           WHEN MAX(m.llm_sentiment) = 'bullish' THEN 'bullish'
           WHEN MAX(m.llm_sentiment) = 'bearish' THEN 'bearish'
           WHEN MAX(m.llm_sentiment) = 'neutral' THEN 'neutral'
           ELSE 'unjudged'
         END AS category
  FROM radar_mention_events e
  LEFT OUTER JOIN radar_posts p ON p.source = e.source AND p.external_id = e.external_id
  LEFT OUTER JOIN radar_mentions m ON m.post_id = p.id AND m.ticker = e.ticker
  WHERE e.ticker = :ticker AND e.source IN :sources
    AND e.bucket_start >= :lower AND e.bucket_start < :upper
    AND (e.confidence = 'high' OR e.promoted = 1)
    AND (e.counts_as_human_chatter IS NULL OR e.counts_as_human_chatter = 1)
  GROUP BY e.id, e.source, e.bucket_start
) er
GROUP BY er.source, er.bucket_start
ORDER BY er.bucket_start, er.source
LIMIT :row_limit
"""


class ChartSqlStore(analysis.SqlStore):
    """HA1's store with this feature's reads. Identity SELECTs are inherited
    unchanged; the new ones use the same statement-scoped timeout."""

    def _select(self, sql: str, timeout_s: float, *, expanding=(), **params) -> list[dict]:
        statement = sa.text(self._timed(sql, timeout_s))
        if expanding:
            statement = statement.bindparams(
                *[sa.bindparam(name, expanding=True) for name in expanding])
        try:
            result = self.session.execute(statement, params)
            return [dict(row) for row in result.mappings().all()]
        except sa_exc.DBAPIError as exc:
            self.session.rollback()
            if analysis._errno(exc) in analysis.TIMEOUT_ERRNOS:
                raise ChartError('read_limit', 503,
                                 'the store did not answer within the bounded time') from exc
            raise ChartError('store_unavailable', 503, 'the store could not be read') from exc
        except sa_exc.SQLAlchemyError as exc:
            self.session.rollback()
            raise ChartError('store_unavailable', 503, 'the store could not be read') from exc

    def bucket_rows(self, ticker, sources, start, end, *, timeout_s):
        return self._select(BUCKET_ROWS, timeout_s, expanding=('sources',), ticker=ticker,
                            sources=list(sources), window_start=start, window_end=end,
                            row_limit=contract.SOURCE_ROW_LIMIT + 1)

    def quote_rows(self, ticker, mic, start, end, read_start, *, timeout_s):
        return self._select(QUOTE_ROWS, timeout_s, ticker=ticker, mic=mic,
                            window_start=start, window_end=end, read_start=read_start,
                            row_limit=contract.QUOTE_ROW_LIMIT + 1)

    def daily_rows(self, ticker, mic, from_date, to_date, read_start, *, timeout_s):
        return self._select(DAILY_ROWS, timeout_s, ticker=ticker, mic=mic,
                            from_date=from_date, to_date=to_date, read_start=read_start,
                            row_limit=contract.DAILY_ROW_LIMIT + 1)

    def tone_rows(self, ticker, sources, lower, upper, *, timeout_s):
        return self._select(TONE_ROWS, timeout_s, expanding=('sources',), ticker=ticker,
                            sources=list(sources), lower=lower, upper=upper,
                            row_limit=contract.SOURCE_ROW_LIMIT + 1)


_TRANSLATED = {
    'analysis_limit': ('read_limit', 503),
    'analysis_unavailable': ('store_unavailable', 503),
    'invalid_ticker': ('invalid_ticker', 400),
}


@contextlib.contextmanager
def translated():
    """HA1's budget and store raise its own codes; this feature has its own."""
    try:
        yield
    except ContractError as error:
        code, status = _TRANSLATED.get(error.code, ('store_unavailable', 503))
        raise ChartError(code, status, error.message) from error


def new_budget() -> analysis.ReaderBudget:
    return analysis.ReaderBudget(seconds=READER_DEADLINE_S, statement_cap=STATEMENT_TIMEOUT_S)


def _as_datetime(value):
    """MariaDB returns datetimes; SQLite (tests) returns text."""
    if isinstance(value, str):
        return dt.datetime.fromisoformat(value.replace('Z', ''))
    return contract.naive_utc(value)


def _as_date(value):
    if isinstance(value, str):
        return dt.date.fromisoformat(value[:10])
    if isinstance(value, dt.datetime):
        return value.date()
    return value


# --- identity -----------------------------------------------------------------

def resolve_identity(ticker: str, now: dt.datetime, *, store, budget) -> dict:
    """Two SELECTs. Unknown or delisted: 404. Anything but exactly one eligible
    native-USD US primary with positive IDs: 422. Nothing is borrowed from
    another venue and the mapping is never changed."""
    read_start = contract.naive_utc(contract.aware_utc(now))
    with translated():
        symbol = analysis_contract.valid_ticker(ticker)
        companies = store.company_by_symbol(symbol, timeout_s=budget.statement_timeout())
        budget.check()
    if not companies or companies[0].get('delisted_at') is not None:
        raise ChartError('unknown_ticker', 404, 'no such company in the current catalogue')
    company = companies[0]
    with translated():
        candidates = store.primary_candidates(symbol, timeout_s=budget.statement_timeout())
        budget.check()
    eligible = [row for row in candidates if analysis._eligibility(row, read_start) is None]
    if len(eligible) != 1:
        reasons = sorted({analysis._eligibility(row, read_start) or 'more than one eligible primary'
                          for row in candidates}) or ['none mapped']
        raise ChartError('unsupported_instrument', 422,
                         'no single eligible native-USD US primary instrument: ' + '; '.join(reasons))
    row = eligible[0]
    try:
        company_id, instrument_id = int(company['id']), int(row['id'])
    except (TypeError, ValueError, KeyError):
        company_id = instrument_id = 0
    if company_id <= 0 or instrument_id <= 0:
        raise ChartError('unsupported_instrument', 422, 'the mapping does not carry positive IDs')
    mapped_at = _as_datetime(row['mapped_at'])
    instrument = {
        'ticker': symbol, 'company_id': company_id, 'instrument_id': instrument_id,
        'mic': (row.get('mic') or '').strip(), 'venue': (row.get('venue') or '').strip(),
        'currency': row.get('currency'),
        'provider_symbol': (row.get('provider_symbol') or '').strip(),
        'mapped_at': contract.iso_z(mapped_at),
        'mapped_at_dt': mapped_at,
        'first_seen_dt': _as_datetime(company.get('first_seen')),
    }
    instrument['fingerprint'] = contract.fingerprint(
        company_id, instrument_id, instrument['provider_symbol'], instrument['currency'],
        instrument['mic'], mapped_at)
    return instrument


# --- local reads --------------------------------------------------------------

def _bucket_rows(identity, window, sources, *, store, budget):
    with translated():
        rows = store.bucket_rows(identity['ticker'], sources,
                                 contract.naive_utc(window.start), contract.naive_utc(window.end),
                                 timeout_s=budget.statement_timeout())
        budget.check()
    if len(rows) > contract.SOURCE_ROW_LIMIT:
        raise ChartError('read_limit', 503, 'more retained bucket rows than the bounded reader supports')
    for row in rows:
        row['bucket_start'] = _as_datetime(row.get('bucket_start'))
    return rows


def read_fallback(identity, window, *, store, budget, now) -> tuple[dict | None, list[str]]:
    """One coherent stored dataset: 1D quotes, else daily closes; 1W daily
    closes. An overflowing read refuses the fallback rather than sampling."""
    if window.waiting:
        return None, []
    read_start = contract.naive_utc(contract.aware_utc(now))
    warnings: list[str] = []
    if window.span == '1D':
        with translated():
            rows = store.quote_rows(identity['ticker'], identity['mic'],
                                    contract.naive_utc(window.start), contract.naive_utc(window.end),
                                    read_start, timeout_s=budget.statement_timeout())
            budget.check()
        for row in rows:
            row['quote_ts'] = _as_datetime(row.get('quote_ts'))
            row['fetched_at'] = _as_datetime(row.get('fetched_at'))
        if len(rows) > contract.QUOTE_ROW_LIMIT:
            return None, ['price: stored quotes exceed the bounded read; the fallback was refused']
        price, warnings = contract.quote_fallback(rows, identity, window, read_start=read_start)
        if price is not None:
            return price, warnings
    with translated():
        rows = store.daily_rows(identity['ticker'], identity['mic'], window.session_dates[0],
                                window.session_dates[-1], read_start,
                                timeout_s=budget.statement_timeout())
        budget.check()
    for row in rows:
        row['close_date'] = _as_date(row.get('close_date'))
        row['fetched_at'] = _as_datetime(row.get('fetched_at'))
    price, daily_warnings = contract.daily_fallback(rows, identity, window, read_start=read_start)
    return price, warnings + daily_warnings


def read_tone(identity, window, sources, chatter, *, store, budget, now) -> tuple[list, list[str]]:
    """Optional. Limited to the window intersected with retained events."""
    now = contract.aware_utc(now)
    retained_from = max(window.start, now - dt.timedelta(hours=config.MENTION_EVENT_RETENTION_HOURS))
    lower = contract.naive_utc(retained_from)
    upper = contract.naive_utc(min(window.end, now))
    needed = any(cell[1] >= lower for cells in chatter['counted_cells'] for cell in cells)
    aggregates: dict = {}
    if needed and lower < upper:
        try:
            with translated():
                rows = store.tone_rows(identity['ticker'], sources, lower, upper,
                                       timeout_s=budget.statement_timeout())
                budget.check()
        except ChartError as error:
            return (contract.tone_slots(chatter, {}, retained_from=lower, failure=error.code),
                    [f'tone: unavailable ({error.code}); counts are unaffected'])
        if len(rows) > contract.SOURCE_ROW_LIMIT:
            return (contract.tone_slots(chatter, {}, retained_from=lower, failure='read_limit'),
                    ['tone: unavailable (read_limit); counts are unaffected'])
        aggregates = {(row['source'], _as_datetime(row['bucket_start'])): row for row in rows}
    warnings = ['tone: colours use retained recorded judgments only; older chatter is unavailable']
    return contract.tone_slots(chatter, aggregates, retained_from=lower), warnings


# --- the 30-second local cache ------------------------------------------------

_cache_lock = threading.Lock()
_cache: 'collections.OrderedDict[tuple, dict]' = collections.OrderedDict()
_cache_bytes = 0


def local_key(identity, window, sources) -> tuple:
    return (identity['fingerprint'], window.span,
            tuple(day.isoformat() for day in window.session_dates),
            contract.iso_z(window.start), tuple(sources))


def cached_local(key, *, clock=time.monotonic):
    global _cache_bytes
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if clock() - entry['created'] >= LOCAL_CACHE_SECONDS:
            _cache.pop(key)
            _cache_bytes -= entry['size']
            return None
        _cache.move_to_end(key)
        return entry


def _entry_size(entry) -> int:
    return len(json.dumps([entry['chatter']['slots'], entry['tone'], entry.get('fallback')],
                          default=str))


def store_local(key, entry, *, clock=time.monotonic) -> None:
    global _cache_bytes
    entry['created'] = entry.get('created', clock())
    entry['size'] = _entry_size(entry)
    if entry['size'] > LOCAL_CACHE_BYTES:
        return
    with _cache_lock:
        old = _cache.pop(key, None)
        if old is not None:
            _cache_bytes -= old['size']
        _cache[key] = entry
        _cache_bytes += entry['size']
        while len(_cache) > LOCAL_CACHE_ENTRIES or _cache_bytes > LOCAL_CACHE_BYTES:
            _, evicted = _cache.popitem(last=False)
            _cache_bytes -= evicted['size']


def clear_local_cache() -> None:
    global _cache_bytes
    with _cache_lock:
        _cache.clear()
        _cache_bytes = 0


# --- the whole answer ---------------------------------------------------------

def build_response(ticker: str, sources, span: str, now: dt.datetime, *, coordinator,
                   store=None, clock=time.monotonic) -> dict:
    """Identity, then acquisition admission, then the local reads -- never
    provider I/O. `coordinator.get_or_start` only admits and returns what the
    process already holds."""
    store = store or ChartSqlStore()
    budget = new_budget()
    now = contract.aware_utc(now)
    identity = resolve_identity(ticker, now, store=store, budget=budget)
    fresh_window = contract.window_for(span, now)
    key = local_key(identity, fresh_window, sources)
    entry = cached_local(key, clock=clock)
    window = entry['window'] if entry is not None else fresh_window

    acquisition = coordinator.get_or_start(identity, window, now=now)
    warnings: list[str] = []
    price = None
    series = acquisition.get('series')
    if series is not None:
        price = contract.yahoo_price(series, window, identity, now=now)
        warnings += contract.yahoo_warnings(series)
        if price is None:
            warnings.append('price: the provider series has no valid bar inside this window')

    if entry is None:
        bucket_rows = _bucket_rows(identity, window, sources, store=store, budget=budget)
        chatter = contract.chatter_slots(bucket_rows, window, identity_floor=identity['first_seen_dt'])
        with translated():
            budget.check()
        fallback = None
        if price is None:
            fallback = read_fallback(identity, window, store=store, budget=budget, now=now)
        tone, tone_warnings = read_tone(identity, window, sources, chatter,
                                        store=store, budget=budget, now=now)
        entry = {'window': window, 'chatter': chatter, 'tone': tone,
                 'tone_warnings': tone_warnings, 'fallback': fallback}
        store_local(key, entry, clock=clock)
    elif price is None and entry.get('fallback') is None:
        entry['fallback'] = read_fallback(identity, window, store=store, budget=budget, now=now)

    if price is None:
        price, fallback_warnings = entry['fallback']
        warnings += fallback_warnings
        if price is None and not window.waiting:
            warnings.append('price: no usable price observation inside this window')
    if window.waiting:
        warnings.append('window: the session has only just begun; nothing to plot yet')

    warnings += entry['chatter']['warnings'] + entry['tone_warnings']
    if identity['provider_symbol'] and contract.yahoo_symbol(identity['provider_symbol']) is None:
        warnings.append('price: the mapped symbol has no supported provider form; stored data only')
    return contract.assemble(identity=identity, window=window, now=now,
                             acquisition=acquisition, price=price,
                             chatter=entry['chatter'], tone=entry['tone'], warnings=warnings)
