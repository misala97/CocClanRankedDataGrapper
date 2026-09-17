# personal_apps/features/radar/market_data.py
"""US market-data orchestration: the active set, grouped closes, claims, ops.

The grouped-close write keeps one non-negotiable shape: a trading date's
closes and its accepted state commit together, so accepted progress can never
exist without the rows it vouches for. Radar is US-only; the archived rows of
the retired non-US collector are never read, written or deleted here.
"""
import dataclasses
import datetime as dt
import logging

import sqlalchemy as sa

from extensions import db

from . import watch as _watch

logger = logging.getLogger(__name__)


def active_price_tickers(now):
    """The union of tickers any current board window can display.

    Exactly the 1h/4h/24h chatter judgements the leaderboard itself makes
    (Task 8 Step 7b) -- a cap here must not permanently starve a ticker the
    board can show.
    """
    from .config import SOURCES
    from . import leaderboard
    union = set()
    for hours in (1, 4, 24):
        union.update(leaderboard.chatter_candidates(list(SOURCES), now,
                                                    hours))
    # A starred ticker is watched whether or not anyone talks about it;
    # its row must not sit on a days-old quote (RZLV, 2026-09-02).
    union.update(_watch.all_tickers())
    return sorted(union)


@dataclasses.dataclass(frozen=True)
class GroupedInstrument:
    ticker: str
    mic: str
    currency: str


def grouped_instrument_map():
    """{exact provider symbol: GroupedInstrument} for grouped-close writes.

    Identity comes ONLY from mapped primary US ``RadarInstrument`` rows of
    non-delisted universe tickers. A provider symbol claimed by two
    identities is omitted and reported as ambiguous;
    ``universe.load_lookup()`` text is never an instrument identity.
    """
    from models import RadarInstrument, TickerUniverse
    rows = (RadarInstrument.query
            .join(TickerUniverse,
                  TickerUniverse.symbol == RadarInstrument.ticker)
            .filter(RadarInstrument.market == 'us',
                    RadarInstrument.is_primary.is_(True),
                    RadarInstrument.mapping_status == 'mapped',
                    TickerUniverse.delisted_at.is_(None))
            .order_by(RadarInstrument.ticker, RadarInstrument.mic).all())
    found = {}
    ambiguous = set()
    for row in rows:
        symbol = (row.provider_symbol or '').strip().upper()
        if not symbol:
            continue
        existing = found.get(symbol)
        candidate = GroupedInstrument(ticker=row.ticker, mic=row.mic,
                                      currency=row.currency)
        if existing is not None and existing != candidate:
            ambiguous.add(symbol)
            continue
        found[symbol] = candidate
    for symbol in ambiguous:
        found.pop(symbol, None)
    return found, sorted(ambiguous)


def grouped_active_symbols_by_day(days, now, instrument_map=None,
                                  is_shadow=False,
                                  observed_symbols_by_day=None):
    """Mapped active US symbols eligible to trade on each historical day.

    ``ipo_date`` is provider metadata, so a known future IPO excludes that
    ticker only before it listed.  A symbol that Massive first returned on a
    later accepted day is likewise ineligible before that observed provider
    availability date only when Massive did not return it for this day.
    Missing dates stay in the denominator: unknown is not evidence that a
    provider omission is harmless.
    """
    from models import RadarDailyClose, TickerUniverse

    days = tuple(days)
    if instrument_map is None:
        instrument_map, _ = grouped_instrument_map()
    active = set(active_price_tickers(now))
    candidates = {symbol: identity for symbol, identity in
                  instrument_map.items() if identity.ticker in active}
    if not candidates:
        return {day: {} for day in days}

    ipo_dates = dict(
        TickerUniverse.query.with_entities(
            TickerUniverse.symbol, TickerUniverse.ipo_date)
        .filter(TickerUniverse.symbol.in_(
            {identity.ticker for identity in candidates.values()})).all())
    first_observed = dict(
        db.session.query(RadarDailyClose.ticker,
                         sa.func.min(RadarDailyClose.close_date))
        .filter(RadarDailyClose.market == 'us',
                RadarDailyClose.source == 'massive_grouped',
                RadarDailyClose.is_shadow.is_(is_shadow),
                RadarDailyClose.ticker.in_(
                    {identity.ticker for identity in candidates.values()}))
        .group_by(RadarDailyClose.ticker).all())
    eligible_by_ipo = {
        day: {
            symbol: identity for symbol, identity in candidates.items()
            if ipo_dates.get(identity.ticker) is None or
            ipo_dates[identity.ticker] <= day
        }
        for day in days
    }
    if observed_symbols_by_day is None:
        return eligible_by_ipo

    return {
        day: {
            symbol: identity for symbol, identity in eligible_by_ipo[day].items()
            if symbol in observed_symbols_by_day.get(day, set()) or
            first_observed.get(identity.ticker) is None or
            first_observed[identity.ticker] <= day
        }
        for day in days
    }


@dataclasses.dataclass(frozen=True)
class GroupedDayResult:
    day: dt.date
    status: str
    written: int
    mapped: int
    unmatched_provider: int
    unmatched_universe: int
    active_expected: int
    active_matched: int


# Non-vacuous acceptance floors (spec §7): fewer provider rows than a real
# US trading day produces, or thin coverage of the board-active union, is
# incomplete evidence and never accepted progress.
GROUPED_MIN_PROVIDER_ROWS = 5000
GROUPED_MIN_ACTIVE_COVERAGE = 0.95


def _close_source_shadow_state():
    import os
    mode = os.getenv('RADAR_US_CLOSE_SOURCE', 'legacy')
    if mode == 'shadow':
        return True
    if mode == 'massive':
        return False
    raise RuntimeError(
        'grouped ingestion requires RADAR_US_CLOSE_SOURCE=shadow or '
        'massive; an ungated run under legacy would overwrite the '
        'incumbent live closes and make the agreement gate compare '
        'massive against itself')


def ingest_grouped_day(provider, day, now):
    """One Massive trading date, transactionally, into the correct lane.

    The shadow/live state is NEVER a caller choice: it derives from
    ``RADAR_US_CLOSE_SOURCE``. Accepted closes and the day's
    ``RadarGroupedCloseDay`` row commit together; every non-accepted
    attempt persists its typed status and stays retryable. Massive never
    touches an archived non-US row.
    """
    from models import RadarGroupedCloseDay
    from . import history

    is_shadow = _close_source_shadow_state()
    fetch = provider.grouped_closes(day)

    instrument_map, ambiguous = grouped_instrument_map()
    active_symbols = set(grouped_active_symbols_by_day(
        (day,), now, instrument_map, is_shadow=is_shadow)[day])

    def persist_state(status, *, written=0, mapped=0, unmatched_provider=0,
                      unmatched_universe=0, active_matched=0,
                      payload_sha256=None, provider_rows=0, malformed=0,
                      conflicts=0, error_code=None, http_status=None,
                      backoff_until=None, commit=True):
        state = RadarGroupedCloseDay.query.filter_by(
            source='massive_grouped', close_date=day,
            is_shadow=is_shadow).one_or_none()
        if state is None:
            state = RadarGroupedCloseDay(
                source='massive_grouped', close_date=day,
                is_shadow=is_shadow, status=status, fetched_at=now)
            db.session.add(state)
        state.status = status
        state.fetched_at = now
        state.completed_at = dt.datetime.now(
            dt.timezone.utc).replace(tzinfo=None)
        state.payload_sha256 = payload_sha256
        state.provider_rows = provider_rows
        state.mapped_rows = mapped
        state.written_rows = written
        state.unmatched_provider = unmatched_provider
        state.unmatched_universe = unmatched_universe
        state.active_expected = len(active_symbols)
        state.active_matched = active_matched
        state.malformed_rows = malformed
        state.duplicate_conflicts = conflicts
        state.error_code = error_code
        state.http_status = http_status
        state.backoff_until = backoff_until
        if commit:
            db.session.commit()
        return state

    if fetch.status != 'accepted':
        persist_state(fetch.status, error_code=fetch.error_code,
                      http_status=fetch.http_status,
                      backoff_until=fetch.backoff_until)
        return GroupedDayResult(
            day=day, status=fetch.status, written=0, mapped=0,
            unmatched_provider=0, unmatched_universe=0,
            active_expected=len(active_symbols), active_matched=0)

    grouped = fetch.day
    matched = {symbol: price for symbol, price in grouped.closes.items()
               if symbol in instrument_map}
    active_symbols = set(grouped_active_symbols_by_day(
        (day,), now, instrument_map, is_shadow=is_shadow,
        observed_symbols_by_day={day: set(matched)})[day])
    unmatched_provider = len(grouped.closes) - len(matched)
    unmatched_universe = len(set(instrument_map) - set(grouped.closes))
    active_matched = len(active_symbols & set(matched))

    if not active_symbols:
        persist_state('rejected', mapped=len(matched),
                      unmatched_provider=unmatched_provider,
                      unmatched_universe=unmatched_universe,
                      active_matched=0,
                      payload_sha256=grouped.payload_sha256,
                      provider_rows=grouped.provider_rows,
                      malformed=grouped.malformed_rows,
                      conflicts=grouped.duplicate_conflicts,
                      error_code='empty_active_denominator')
        return GroupedDayResult(
            day=day, status='rejected', written=0, mapped=len(matched),
            unmatched_provider=unmatched_provider,
            unmatched_universe=unmatched_universe,
            active_expected=0, active_matched=0)

    coverage = active_matched / len(active_symbols)
    if grouped.provider_rows < GROUPED_MIN_PROVIDER_ROWS or \
            coverage < GROUPED_MIN_ACTIVE_COVERAGE:
        persist_state('rejected', mapped=len(matched),
                      unmatched_provider=unmatched_provider,
                      unmatched_universe=unmatched_universe,
                      active_matched=active_matched,
                      payload_sha256=grouped.payload_sha256,
                      provider_rows=grouped.provider_rows,
                      malformed=grouped.malformed_rows,
                      conflicts=grouped.duplicate_conflicts,
                      error_code='below_acceptance_floor')
        return GroupedDayResult(
            day=day, status='rejected', written=0, mapped=len(matched),
            unmatched_provider=unmatched_provider,
            unmatched_universe=unmatched_universe,
            active_expected=len(active_symbols),
            active_matched=active_matched)

    try:
        written = 0
        for symbol, price in matched.items():
            identity = instrument_map[symbol]
            written += history.record_closes(
                identity.ticker, [(day, price)], now, market='us',
                mic=identity.mic, currency=identity.currency,
                source='massive_grouped', adjustment_basis='split',
                is_shadow=is_shadow, commit=False)
        persist_state('accepted', written=written, mapped=len(matched),
                      unmatched_provider=unmatched_provider,
                      unmatched_universe=unmatched_universe,
                      active_matched=active_matched,
                      payload_sha256=grouped.payload_sha256,
                      provider_rows=grouped.provider_rows,
                      malformed=grouped.malformed_rows,
                      conflicts=grouped.duplicate_conflicts, commit=False)
        # Closes and accepted progress stand or fall together.
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return GroupedDayResult(
        day=day, status='accepted', written=written, mapped=len(matched),
        unmatched_provider=unmatched_provider,
        unmatched_universe=unmatched_universe,
        active_expected=len(active_symbols), active_matched=active_matched)


def claim_post_close(source, market, now, session_date):
    """Durably claim ONE post-close cycle for one session date [A3].

    The claim commits BEFORE any provider request, under a row lock created
    with an idempotent insert so two first-ever callers cannot both win;
    a duplicate-key race retries the locked read. Once claimed, a failed
    cycle does not reopen the date -- the closing print gets one shot per
    session, which is what keeps a restarting daemon from repeating the
    weekend request loop.
    """
    import sqlalchemy as sa
    from models import RadarProviderSessionState

    insert = sa.text(
        'INSERT IGNORE INTO radar_provider_session_states '
        '(source, market) VALUES (:source, :market)')
    try:
        db.session.execute(insert, {'source': source, 'market': market})
        db.session.commit()
    except Exception:
        db.session.rollback()

    row = (RadarProviderSessionState.query
           .filter_by(source=source, market=market)
           .with_for_update().one())
    if row.last_post_close_session_date is not None and \
            row.last_post_close_session_date >= session_date:
        db.session.commit()
        return None
    row.last_post_close_session_date = session_date
    row.claimed_at = now
    db.session.commit()
    return session_date


_OPS_MEMO = {'at': None, 'value': None}


def clear_ops_memo():
    _OPS_MEMO.update(at=None, value=None)


def ops_summary(now):
    """A cached, database-only operational summary (spec §11).

    Never imports or calls a provider module; 60-second memo so the board
    serializer cannot turn health into a per-request query storm.
    """
    from models import (RadarGroupedCloseDay, RadarProviderSessionState,
                        RadarQuote)

    if _OPS_MEMO['at'] is not None and \
            (now - _OPS_MEMO['at']).total_seconds() < 60 and \
            _OPS_MEMO['value'] is not None:
        return _OPS_MEMO['value']

    basis_counts = dict(
        db.session.query(RadarQuote.price_basis, sa.func.count())
        .filter(RadarQuote.fetched_at >= now - dt.timedelta(hours=24),
                sa.or_(RadarQuote.market == 'us',
                       RadarQuote.market.is_(None)))
        .group_by(RadarQuote.price_basis).all())

    grouped_states = (RadarGroupedCloseDay.query
                      .filter_by(source='massive_grouped')
                      .order_by(RadarGroupedCloseDay.close_date.desc())
                      .limit(14).all())
    accepted_dates = [state.close_date.isoformat() for state in grouped_states
                      if state.status == 'accepted']
    grouped = {
        'latest_accepted_date': accepted_dates[0] if accepted_dates else None,
        'retryable_gaps': [state.close_date.isoformat()
                           for state in grouped_states
                           if state.status != 'accepted'],
        'counts': ({
            'provider_rows': grouped_states[0].provider_rows,
            'mapped': grouped_states[0].mapped_rows,
            'written': grouped_states[0].written_rows,
            'unmatched_provider': grouped_states[0].unmatched_provider,
            'unmatched_universe': grouped_states[0].unmatched_universe,
            'malformed': grouped_states[0].malformed_rows,
            'duplicate_conflicts': grouped_states[0].duplicate_conflicts,
        } if grouped_states else None),
        'error_code': grouped_states[0].error_code if grouped_states else None,
        'http_status': grouped_states[0].http_status if grouped_states else None,
        'backoff_until': (grouped_states[0].backoff_until.isoformat()
                          if grouped_states and grouped_states[0].backoff_until
                          else None),
    }

    claims = {
        f'{row.source}:{row.market}': (
            row.last_post_close_session_date.isoformat()
            if row.last_post_close_session_date else None)
        for row in RadarProviderSessionState.query.filter_by(market='us')}

    value = {
        'quote_basis_24h': {key or 'legacy': count
                            for key, count in basis_counts.items()},
        'grouped_closes': grouped,
        'post_close_claims': claims,
    }
    _OPS_MEMO.update(at=now, value=value)
    return value
