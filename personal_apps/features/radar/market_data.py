# personal_apps/features/radar/market_data.py
"""German delayed-file collection: selection, transactions, orchestration.

The collector's contract (spec §7, plan Task 7): for every ACCEPTED file,
one transaction commits the durable cursor, the trade-event journal rows,
and the shadow/live quote snapshots together. A crash between any two of
them must be impossible to observe: either the file happened entirely or it
did not, and the cursor can never advance past data that was not stored.
One cycle row per (MIC, channel, scheduled instant) records the aggregate
outcome -- the unique key models a scheduled attempt, not a file.

Only instruments in the active Radar set are materialized into quote rows;
one file download already carries the whole venue, so there is no
per-ticker request amplification to manage.
"""
import dataclasses
import datetime as dt
import hashlib
import json
import logging
import time

import sqlalchemy as sa

from extensions import db
from models import (RadarMarketDataCursor, RadarMarketDataCycle,
                    RadarMarketTradeEvent)

from . import config as _config
from . import quotes as quotes_mod
from . import watch as _watch
from .instruments import MappingDecision, VENUE_BY_MIC
from .prices import Quote
from .prices.deutsche_boerse import FeedRejected

logger = logging.getLogger(__name__)

# The provider deletes files roughly a day after publication ("available
# until midnight of the following business day"). A download failure on a
# file older than this is expiry, not an outage: the file is skipped and
# the cursor advances, because retrying a deleted file wedges the channel
# forever (observed in production 2026-09-01).
STALE_SKIP_AGE = dt.timedelta(hours=26)

# A trade or book older than this cannot be the current price (spec §4.3).
SELECTION_HORIZON_SECONDS = 1800

# R8: XETR pre-trade is ~20 MB compressed / ~200 MB uncompressed per minute
# file; its caps are raised for exactly that one channel.
XETR_PRETRADE_LIMITS = {'max_compressed': 31_457_280,
                        'max_uncompressed': 314_572_800}


@dataclasses.dataclass(frozen=True)
class Selected:
    """One instrument's selected price for a poll."""
    price: object
    price_basis: str
    event_ts: dt.datetime
    bid: object = None
    ask: object = None


@dataclasses.dataclass(frozen=True)
class CycleSummary:
    mode: str
    status: str
    files_seen: int
    files_accepted: int
    selected_quotes: int
    rejected_records: int
    error_code: str | None

    @classmethod
    def accepted(cls, selected_quotes: int) -> 'CycleSummary':
        return cls('shadow', 'accepted', 1, 1, selected_quotes, 0, None)


def select_price(*, now, trades, book, isin=None):
    """The deterministic spec §4.3 selection for one instrument.

    Newest valid executed trade within 30 minutes; otherwise a fresh
    two-sided book's midpoint as ``indicative``; otherwise None -- the
    caller retains the previous observation with its growing age.
    """
    horizon = now - dt.timedelta(seconds=SELECTION_HORIZON_SECONDS)
    candidates = [
        event for event in trades
        if event.action == 'new' and event.price is not None
        and event.price > 0
        and (isin is None or event.isin == isin)
        and event.event_ts >= horizon]
    if candidates:
        newest = max(candidates,
                     key=lambda event: (event.event_ts, event.event_id))
        return Selected(price=newest.price, price_basis='trade',
                        event_ts=newest.event_ts)
    if book is not None and (isin is None or book.isin == isin) and \
            book.event_ts >= horizon and 0 < book.bid <= book.ask:
        return Selected(price=(book.bid + book.ask) / 2,
                        price_basis='midpoint', event_ts=book.event_ts,
                        bid=book.bid, ask=book.ask)
    return None


def _mapped_decisions(generation_id, active_tickers):
    """Mapped decisions for the active set, indexed by (mic, isin).

    Reads the generation PAYLOAD, not RadarInstrument.is_primary: a shadow
    generation is deliberately not active for the board.
    """
    from models import RadarMappingGeneration
    generation = RadarMappingGeneration.query.get(generation_id)
    if generation is None:
        raise ValueError(f'no mapping generation {generation_id}')
    payload = json.loads(generation.payload_json)
    active = set(active_tickers)
    by_identity = {}
    for item in payload['decisions']:
        decision = MappingDecision(**item)
        if decision.status != 'mapped' or decision.ticker not in active:
            continue
        identity = (decision.mic, decision.isin)
        if identity in by_identity and \
                by_identity[identity].ticker != decision.ticker:
            raise ValueError(
                f'generation {generation_id}: identity {identity} assigned '
                f'to two social tickers')
        by_identity[identity] = decision
    return by_identity


def _journal_upsert(events, remote_id, now):
    """Stage new trade events; byte-identical repeats are idempotent."""
    if not events:
        return 0
    existing = {
        row.event_id: row for row in RadarMarketTradeEvent.query.filter(
            RadarMarketTradeEvent.mic == events[0].mic,
            RadarMarketTradeEvent.event_id.in_(
                [event.event_id for event in events]))}
    staged = 0
    for event in events:
        known = existing.get(event.event_id)
        if known is not None:
            if (known.isin, known.event_ts, known.price) != (
                    event.isin, event.event_ts, event.price):
                raise FeedRejected(
                    f'{remote_id}: event {event.event_id} conflicts with '
                    f'the retained journal')
            continue
        db.session.add(RadarMarketTradeEvent(
            mic=event.mic, isin=event.isin, event_id=event.event_id,
            original_event_id=event.original_event_id, action=event.action,
            event_ts=event.event_ts, price=event.price, volume=event.volume,
            is_official_close=event.is_official_close,
            source_remote_id=remote_id, received_at=now))
        staged += 1
    return staged


def _journal_trades(mic, isins, since):
    return (RadarMarketTradeEvent.query
            .filter(RadarMarketTradeEvent.mic == mic,
                    RadarMarketTradeEvent.isin.in_(isins),
                    RadarMarketTradeEvent.event_ts >= since)
            .order_by(RadarMarketTradeEvent.event_ts).all())


def _advance_cursor(mic, channel, batch, checksum, now):
    cursor = RadarMarketDataCursor.query.get(
        ('deutsche_boerse_delayed', mic, channel))
    if cursor is None:
        cursor = RadarMarketDataCursor(
            source='deutsche_boerse_delayed', mic=mic, channel=channel,
            remote_id=batch.remote_id, source_ts=batch.source_ts,
            checksum=checksum, fetched_at=now)
        db.session.add(cursor)
    else:
        cursor.remote_id = batch.remote_id
        cursor.source_ts = batch.source_ts
        cursor.checksum = checksum
        cursor.fetched_at = now
    return cursor


# ---- the host's quota (config.py explains the 2026-09-01 outage) -----------
DE_FILES_PER_CYCLE = _config.DE_FILES_PER_CYCLE
DE_DOWNLOAD_BUDGET_24H = _config.DE_DOWNLOAD_BUDGET_24H
DE_THROTTLE_BACKOFF_SECONDS = _config.DE_THROTTLE_BACKOFF_SECONDS
# MICs the collector actually spends downloads on.
#
# XGAT only: Tradegate is the venue that supplies German QUOTES, and Xetra's
# daily closes come from the history path (features/radar/history.py), not
# from this feed. Collecting both doubled the download cost for a series
# nothing reads.
DE_COLLECT_MICS = ('XGAT',)
# One state for the whole feed, not per channel: the host throttles the IP.
# In-process on purpose -- a restart forgets it and the first cycle probes
# once, which is the right amount of optimism after a deploy.
_THROTTLE = {}


def _throttled_until(now):
    state = _THROTTLE.get('feed')
    return state['until'] if state and state['until'] > now else None


def _note_throttle(now):
    """HTTP 429 seen: wait twice as long as last time, up to the cap."""
    state = _THROTTLE.setdefault('feed', {'failures': 0, 'until': now})
    state['failures'] += 1
    first, longest = DE_THROTTLE_BACKOFF_SECONDS
    state['until'] = now + dt.timedelta(
        seconds=min(longest, first * 2 ** (state['failures'] - 1)))


def _clear_throttle():
    _THROTTLE.pop('feed', None)


def downloads_last_24h(now):
    """Downloads attempted against the host in the trailing day. The cycle
    rows are the ledger: files_seen counts files a download was asked for,
    never files merely listed.

    Rows written before the cap carried files LISTED (31 a cycle) while
    attempting one download and breaking on it; counted at face value they
    spent the budget for a day after the deploy ('download budget spent
    5056/300', 2026-09-02). A row over the cap is one attempt.
    """
    seen = RadarMarketDataCycle.files_seen
    attempts = sa.case((seen > DE_FILES_PER_CYCLE, 1), else_=seen)
    return int(db.session.query(sa.func.coalesce(sa.func.sum(attempts), 0))
               .filter(RadarMarketDataCycle.source == 'deutsche_boerse_delayed',
                       RadarMarketDataCycle.completed_at >= now - dt.timedelta(hours=24))
               .scalar() or 0)


def collect_german_cycle(provider, generation_id, active_tickers, now,
                         *, mode='shadow'):
    """One five-minute collection pass over both XGAT quote channels."""
    from .market_calendars import session_state

    aware = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    if session_state('de', aware, mic='XGAT') == 'closed':
        # A file published while the venue is shut is a file the board will
        # never draw, and the budget it costs is the one the session needs.
        return CycleSummary(
            mode=mode, status='closed', files_seen=0, files_accepted=0,
            selected_quotes=0, rejected_records=0, error_code=None)

    by_identity = _mapped_decisions(generation_id, active_tickers)
    mics = [mic for mic in sorted({mic for mic, _ in by_identity})
            if mic in DE_COLLECT_MICS] or list(DE_COLLECT_MICS)
    is_shadow = mode == 'shadow'

    total_seen = 0
    total_accepted = 0
    selected_total = 0
    rejected_total = 0
    overall_status = 'no_newer'
    overall_error = None

    for mic in mics:
        isins = [isin for candidate_mic, isin in by_identity
                 if candidate_mic == mic]
        latest_books = {}
        for channel in ('pretrade', 'posttrade'):
            outcome = _collect_channel(
                provider, mic, channel, by_identity, isins, latest_books,
                now, mode, is_shadow)
            total_seen += outcome['seen']
            total_accepted += outcome['accepted']
            selected_total += outcome['selected']
            rejected_total += outcome['rejected']
            if outcome['status'] == 'accepted' and \
                    overall_status in ('no_newer', 'duplicate'):
                overall_status = 'accepted'
            elif outcome['status'] in ('rejected', 'transport_error'):
                overall_status = outcome['status']
                overall_error = outcome['error_code']
            elif outcome['error_code'] and overall_error is None:
                # Informational (e.g. expired-file skips) without failure.
                overall_error = outcome['error_code']

    return CycleSummary(
        mode=mode, status=overall_status, files_seen=total_seen,
        files_accepted=total_accepted, selected_quotes=selected_total,
        rejected_records=rejected_total, error_code=overall_error)


def _collect_channel(provider, mic, channel, by_identity, isins,
                     latest_books, now, mode, is_shadow):
    """One channel's pass, committed as ONE transaction plus one cycle row.

    Spec §7: one poll stores at most one snapshot per selected instrument,
    so quote selection happens once per pass over the accumulated journal
    and books -- and the cursor, journal events, quotes, and the pass's
    outcome stand or fall together. A structural rejection rolls back
    everything staged and leaves the cursor on the last accepted file.
    """
    outcome = {'seen': 0, 'accepted': 0, 'selected': 0, 'rejected': 0,
               'status': 'no_newer', 'error_code': None,
               'newest': None, 'records': 0, 'compressed': 0,
               'parse_ms': 0}
    # The host's quota, before a single request: a backoff in force or a
    # spent budget records the cycle and asks for nothing.
    until = _throttled_until(now)
    if until is not None:
        outcome['status'] = 'transport_error'
        outcome['error_code'] = f'throttled until {until:%H:%M} UTC'[:48]
        _record_cycle_row(mic, channel, now, mode, outcome)
        return outcome
    spent = downloads_last_24h(now)
    if spent >= DE_DOWNLOAD_BUDGET_24H:
        outcome['status'] = 'transport_error'
        outcome['error_code'] = (f'download budget spent '
                                 f'{spent}/{DE_DOWNLOAD_BUDGET_24H}')[:48]
        _record_cycle_row(mic, channel, now, mode, outcome)
        return outcome
    cursor = RadarMarketDataCursor.query.get(
        ('deutsche_boerse_delayed', mic, channel))
    try:
        files = provider.files_after(mic, channel, cursor)
    except Exception as exc:
        if 'HTTP 429' in str(exc):
            _note_throttle(now)
        outcome['status'] = 'transport_error'
        outcome['error_code'] = str(exc)[:48]
        _record_cycle_row(mic, channel, now, mode, outcome)
        return outcome
    # Newest first, under the cap. The files come oldest-first for the
    # cursor's sake; what a live board needs is the latest snapshot, and a
    # backlog of minute-files is exactly what filled the host's quota.
    backlog_skipped = 0
    if len(files) > DE_FILES_PER_CYCLE:
        backlog_skipped = len(files) - DE_FILES_PER_CYCLE
        files = files[-DE_FILES_PER_CYCLE:]

    newest_accepted = None
    newest_checksum = None
    duplicate_only = None
    stale_skipped = None
    stale_skips = 0
    failed = False
    for file in files:
        outcome['seen'] += 1
        limits = (XETR_PRETRADE_LIMITS
                  if (mic, channel) == ('XETR', 'pretrade') else {})
        try:
            compressed = provider.download(file, **limits)
        except Exception as exc:
            if 'HTTP 429' in str(exc):
                _note_throttle(now)
            if now - file.source_ts > STALE_SKIP_AGE:
                # Expired upstream; skip past it instead of wedging here.
                stale_skipped = file
                stale_skips += 1
                logger.warning('radar de %s/%s: skipping expired file '
                               '%s (%s)', mic, channel, file.remote_id, exc)
                continue
            db.session.rollback()
            outcome['status'] = 'transport_error'
            outcome['error_code'] = str(exc)[:48]
            outcome['accepted'] = 0
            outcome['selected'] = 0
            failed = True
            break
        try:
            checksum = hashlib.sha256(compressed).hexdigest()
            reference = (newest_checksum or
                         (cursor.checksum if cursor is not None else None))
            if reference is not None and checksum == reference:
                # Later remote id, same verified content: remembered so the
                # final commit advances the cursor past it.
                duplicate_only = (file, checksum)
                if outcome['status'] == 'no_newer':
                    outcome['status'] = 'duplicate'
                continue
            started = time.perf_counter()
            parse_limits = {key: value for key, value in limits.items()
                            if key != 'max_compressed'}
            batch = provider.parse(file, compressed, **parse_limits)
            outcome['parse_ms'] += int(
                (time.perf_counter() - started) * 1000)
        except FeedRejected as exc:
            db.session.rollback()
            outcome['status'] = 'rejected'
            outcome['error_code'] = str(exc)[:48]
            outcome['accepted'] = 0
            outcome['selected'] = 0
            failed = True
            break
        except Exception as exc:
            db.session.rollback()
            outcome['status'] = 'transport_error'
            outcome['error_code'] = str(exc)[:48]
            outcome['accepted'] = 0
            outcome['selected'] = 0
            failed = True
            break

        try:
            if channel == 'posttrade':
                relevant = [event for event in batch.trades
                            if event.isin in isins]
                _journal_upsert(relevant, batch.remote_id, now)
            else:
                for event in batch.books:
                    if event.isin not in isins:
                        continue
                    current = latest_books.get(event.isin)
                    if current is None or event.event_ts > current.event_ts:
                        latest_books[event.isin] = event
        except FeedRejected as exc:
            db.session.rollback()
            outcome['status'] = 'rejected'
            outcome['error_code'] = str(exc)[:48]
            outcome['accepted'] = 0
            outcome['selected'] = 0
            failed = True
            break

        newest_accepted = batch
        newest_checksum = checksum
        outcome['rejected'] += batch.rejected_records
        outcome['records'] += batch.record_count
        outcome['compressed'] += len(compressed)
        outcome['newest'] = batch
        outcome['accepted'] += 1
        outcome['status'] = 'accepted'

    if not failed and stale_skips and outcome['status'] == 'no_newer':
        outcome['error_code'] = f'{stale_skips} expired files skipped'[:48]
    if not failed and backlog_skipped and not outcome['error_code']:
        outcome['error_code'] = f'skipped {backlog_skipped} backlog files'[:48]
    if not failed and outcome['seen']:
        # A download the host accepted: the throttle is over. An empty
        # listing proves nothing and must not reset the backoff counter.
        _clear_throttle()
    if not failed and (newest_accepted is not None or
                       duplicate_only is not None or
                       stale_skipped is not None):
        try:
            if channel == 'posttrade' and newest_accepted is not None:
                selected_quotes = {}
                since = now - dt.timedelta(
                    seconds=SELECTION_HORIZON_SECONDS)
                journal = _journal_trades(mic, isins, since)
                for (candidate_mic, isin), decision in by_identity.items():
                    if candidate_mic != mic:
                        continue
                    picked = select_price(
                        now=now,
                        trades=[event for event in journal
                                if event.isin == isin],
                        book=latest_books.get(isin), isin=isin)
                    if picked is None:
                        continue
                    selected_quotes[isin] = _quote_for(decision, picked, now)
                if selected_quotes:
                    quotes_mod.record_quotes(
                        selected_quotes, now, is_shadow=is_shadow,
                        commit=False)
                    outcome['selected'] = len(selected_quotes)

            if newest_accepted is not None:
                _advance_cursor(mic, channel, newest_accepted,
                                newest_checksum, now)
            elif duplicate_only is not None:
                _advance_cursor(mic, channel, duplicate_only[0],
                                duplicate_only[1], now)
            elif stale_skipped is not None:
                # Files come oldest-first, so anything accepted above is
                # newer than every skipped file; this branch only fires
                # when the pass yielded nothing but expiries. The cursor
                # checksum column is NOT NULL; an unobtainable payload
                # gets an all-zero sentinel no real sha256 can equal.
                _advance_cursor(mic, channel, stale_skipped, '0' * 64, now)
            # THE commit: cursor + journal + quotes stand together.
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    _record_cycle_row(mic, channel, now, mode, outcome)
    return outcome


def _record_cycle_row(mic, channel, scheduled_at, mode, outcome):
    newest = outcome['newest']
    db.session.add(RadarMarketDataCycle(
        source='deutsche_boerse_delayed', mic=mic, channel=channel,
        scheduled_at=scheduled_at,
        completed_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        mode=mode, status=outcome['status'],
        newest_remote_id=newest.remote_id if newest else None,
        newest_source_ts=newest.source_ts if newest else None,
        files_seen=outcome['seen'], files_accepted=outcome['accepted'],
        record_count=outcome['records'], selected_count=outcome['selected'],
        rejected_records=outcome['rejected'],
        compressed_bytes=outcome['compressed'], uncompressed_bytes=0,
        parse_ms=outcome['parse_ms'],
        error_code=outcome['error_code']))
    db.session.commit()


def materialize_native_closes(generation_id, now, *, mode='shadow'):
    """Daily closes from the retained trade journal (spec §8.3).

    Per mapped (MIC, ISIN) and completed Berlin trading day inside the
    48-hour journal: prefer the newest valid event MARKED official close;
    otherwise the final non-revoked executed trade at or before the venue
    close. Never a midpoint. Idempotent; re-running a day restates it and
    may replace Yahoo at higher source priority.
    """
    import zoneinfo
    from . import history
    from .market_calendars import session_bounds

    berlin = zoneinfo.ZoneInfo('Europe/Berlin')
    by_identity = _mapped_decisions(
        generation_id,
        [decision.ticker for decision in _all_decisions(generation_id)])
    is_shadow = mode == 'shadow'
    written = 0
    for (mic, isin), decision in by_identity.items():
        events = (RadarMarketTradeEvent.query
                  .filter(RadarMarketTradeEvent.mic == mic,
                          RadarMarketTradeEvent.isin == isin,
                          RadarMarketTradeEvent.action == 'new',
                          RadarMarketTradeEvent.price.isnot(None))
                  .order_by(RadarMarketTradeEvent.event_ts).all())
        by_day = {}
        for event in events:
            local_day = event.event_ts.replace(
                tzinfo=dt.timezone.utc).astimezone(berlin).date()
            by_day.setdefault(local_day, []).append(event)
        for local_day, day_events in by_day.items():
            probe = dt.datetime.combine(
                local_day, dt.time(12), tzinfo=berlin)
            bounds = session_bounds('de', probe.astimezone(dt.timezone.utc),
                                    mic=mic)
            closes_at = bounds.closes_at.astimezone(
                dt.timezone.utc).replace(tzinfo=None)
            if now < closes_at:
                continue  # the session has not completed yet
            official = [event for event in day_events
                        if event.is_official_close]
            if official:
                chosen = max(official, key=lambda event: event.event_ts)
            else:
                in_session = [event for event in day_events
                              if event.event_ts <= closes_at]
                if not in_session:
                    continue
                chosen = max(in_session, key=lambda event: event.event_ts)
            written += history.record_closes(
                decision.ticker, [(local_day, chosen.price)], now,
                market='de', mic=mic, currency=decision.currency,
                source='deutsche_boerse_delayed', adjustment_basis='split',
                is_shadow=is_shadow)
    return written


def _all_decisions(generation_id):
    from models import RadarMappingGeneration
    generation = RadarMappingGeneration.query.get(generation_id)
    if generation is None:
        raise ValueError(f'no mapping generation {generation_id}')
    return [MappingDecision(**item)
            for item in json.loads(generation.payload_json)['decisions']]


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
                                  is_shadow=False):
    """Mapped active US symbols eligible to trade on each historical day.

    ``ipo_date`` is provider metadata, so a known future IPO excludes that
    ticker only before it listed.  A symbol that Massive first returned on a
    later accepted day is likewise ineligible before that observed provider
    availability date.  Missing dates stay in the denominator: unknown is
    not evidence that a provider omission is harmless.
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
    return {
        day: {
            symbol: identity for symbol, identity in candidates.items()
            if ipo_dates.get(identity.ticker) is None or
            ipo_dates[identity.ticker] <= day
            if first_observed.get(identity.ticker) is None or
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
    touches the MIC-keyed German cursor.
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
    import sqlalchemy as sa
    from models import (RadarGroupedCloseDay, RadarMappingGeneration,
                        RadarProviderSessionState, RadarQuote)

    if _OPS_MEMO['at'] is not None and \
            (now - _OPS_MEMO['at']).total_seconds() < 60 and \
            _OPS_MEMO['value'] is not None:
        return _OPS_MEMO['value']

    cycles = {}
    rows = (RadarMarketDataCycle.query
            .order_by(RadarMarketDataCycle.mic, RadarMarketDataCycle.channel,
                      RadarMarketDataCycle.scheduled_at.desc()).all())
    for row in rows:
        key = f'{row.mic}:{row.channel}'
        if key in cycles:
            continue
        cycles[key] = {
            'status': row.status, 'scheduled_at': row.scheduled_at.isoformat(),
            'files_seen': row.files_seen, 'files_accepted': row.files_accepted,
            'selected': row.selected_count, 'rejected': row.rejected_records,
            'parse_ms': row.parse_ms, 'error_code': row.error_code,
        }

    generations = dict(
        db.session.query(RadarMappingGeneration.status,
                         sa.func.count()).group_by(
            RadarMappingGeneration.status).all())

    basis_counts = dict(
        db.session.query(RadarQuote.price_basis, sa.func.count())
        .filter(RadarQuote.fetched_at >= now - dt.timedelta(hours=24))
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
        for row in RadarProviderSessionState.query.all()}

    de_budget_spent = downloads_last_24h(now)

    value = {
        'cycles': cycles,
        'mapping_generations': generations,
        'quote_basis_24h': {key or 'legacy': count
                            for key, count in basis_counts.items()},
        'grouped_closes': grouped,
        'post_close_claims': claims,
        'de_download_budget_24h': {
            'spent': de_budget_spent,
            'limit': DE_DOWNLOAD_BUDGET_24H,
            'remaining': max(0, DE_DOWNLOAD_BUDGET_24H - de_budget_spent),
        },
    }
    _OPS_MEMO.update(at=now, value=value)
    return value


def _quote_for(decision, picked, now):
    kwargs = dict(
        ticker=decision.ticker, market='de',
        venue=VENUE_BY_MIC[decision.mic], mic=decision.mic,
        provider_symbol=decision.symbol, currency=decision.currency,
        quote_ts=picked.event_ts,
        provider_delay='delayed', source='deutsche_boerse_delayed',
        price_basis=picked.price_basis, fetched_at=now)
    if picked.price_basis == 'midpoint':
        return Quote(bid=picked.bid, ask=picked.ask, **kwargs)
    return Quote(price=picked.price, **kwargs)
