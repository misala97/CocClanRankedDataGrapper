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
import time

from extensions import db
from models import (RadarMarketDataCursor, RadarMarketDataCycle,
                    RadarMarketTradeEvent)

from . import quotes as quotes_mod
from .instruments import MappingDecision, VENUE_BY_MIC
from .prices import Quote
from .prices.deutsche_boerse import FeedRejected

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


def collect_german_cycle(provider, generation_id, active_tickers, now,
                         *, mode='shadow'):
    """One five-minute collection pass over both channels of every mapped MIC."""
    by_identity = _mapped_decisions(generation_id, active_tickers)
    mics = sorted({mic for mic, _ in by_identity}) or ['XGAT']
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
    cursor = RadarMarketDataCursor.query.get(
        ('deutsche_boerse_delayed', mic, channel))
    try:
        files = provider.files_after(mic, channel, cursor)
    except Exception as exc:
        outcome['status'] = 'transport_error'
        outcome['error_code'] = str(exc)[:48]
        _record_cycle_row(mic, channel, now, mode, outcome)
        return outcome

    newest_accepted = None
    newest_checksum = None
    duplicate_only = None
    failed = False
    for file in files:
        outcome['seen'] += 1
        limits = (XETR_PRETRADE_LIMITS
                  if (mic, channel) == ('XETR', 'pretrade') else {})
        try:
            compressed = provider.download(file, **limits)
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

    if not failed and (newest_accepted is not None or
                       duplicate_only is not None):
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
