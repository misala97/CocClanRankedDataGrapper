# personal_apps/features/radar/prices/deutsche_boerse.py
"""The one module that knows the Deutsche Börse delayed-file contract.

Everything here is pinned to the captured supplement
(docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md);
no heuristic key search, no alternate spellings. The load-bearing rulings:

- R1: payloads are gzip NDJSON, one object per line.
- R2: /api/download 301s to a ~2-second signed URL on ONE exact bucket;
  the transport follows exactly that one redirect and nothing else.
- R3: access is public -- no cookie, no login. The terms disclaimer is a
  client-side dialog the operator accepted.
- R4: corrections were never observed. A modification indicator other than
  '-' is a rejected row with a counted reason, never guessed amend/cancel
  semantics. ``apply_trade_events`` keeps the reviewed correction algebra
  for the journal, but this parser only ever emits action='new'.
- R5: XETR marks its closing auction with lastTradeIndicator 'C'; XGAT has
  no marker and its native close is the last valid trade of the session.
- R7: rows carry sub-venue MICs finer than the channel; unknown ones are
  rejected and counted.
- R9: an empty gzip payload is a VALID market-closed file.
- R10: non-EUR rows exist (XGAT books quote USD/GBP names) and are
  filtered before selection.
"""
import collections.abc
import dataclasses
import datetime as dt
import decimal
import gzip
import json
import re

import requests

from . import PriceUnavailable

INDEX_BASE = 'https://mfs.deutsche-boerse.com'

# The exact signed-storage bucket observed for minute AND daily files (R2).
ALLOWED_REDIRECT_PREFIX = (
    'https://storage.googleapis.com/'
    'mv-cef-prod-europe-west3-private-min-by-min-files/')

# MIC <-> file-service source prefix, from the captured index pages.
SOURCE_BY_MIC = {'XGAT': 'DGAT', 'XETR': 'DETR'}

# First-ever cursor: only this much of the listed backlog is consumed.
COLD_START_WINDOW = dt.timedelta(minutes=15)

# Sub-venue execution MICs observed per channel MIC (R7).
OBSERVED_VENUE_MICS = {
    'XGAT': frozenset({'XGAT', 'XGRM'}),
    'XETR': frozenset({'XETA', 'XETB', 'XEMA', 'XETS', 'XEMI', 'XEMB',
                       'XETU'}),
}

_FILENAME_RE = re.compile(
    r'^(DGAT|DETR)-(pretrade|posttrade)'
    r'(?:-(\d{4})-(\d{2})-(\d{2})T(\d{2})_(\d{2})'
    r'|-daily-(\d{4})-(\d{2})-(\d{2}))\.json\.gz$')

_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}\d$')

_MIC_BY_SOURCE = {source: mic for mic, source in SOURCE_BY_MIC.items()}


class FeedRejected(Exception):
    """A structurally unusable file (or batch); the cursor must not advance."""


@dataclasses.dataclass(frozen=True)
class VenueReference:
    mic: str
    isin: str
    symbol: str
    name: str | None
    currency: str
    security_type: str


@dataclasses.dataclass(frozen=True)
class TradeEvent:
    mic: str
    isin: str
    event_id: str
    original_event_id: str | None
    action: str
    event_ts: dt.datetime
    price: decimal.Decimal | None
    volume: int | None
    is_official_close: bool
    # The row-level execution MIC (R7): provenance, not identity. The
    # channel MIC above remains the Radar market identity.
    venue_mic: str | None = None


@dataclasses.dataclass(frozen=True)
class BookEvent:
    mic: str
    isin: str
    event_ts: dt.datetime
    bid: decimal.Decimal
    ask: decimal.Decimal


@dataclasses.dataclass(frozen=True)
class FeedFile:
    mic: str
    channel: str
    remote_id: str
    source_ts: dt.datetime
    url: str
    is_daily: bool = False


@dataclasses.dataclass(frozen=True)
class FeedBatch:
    mic: str
    channel: str
    remote_id: str
    source_ts: dt.datetime
    references: tuple
    trades: tuple
    books: tuple
    reference_complete: bool
    record_count: int
    rejected_records: int = 0


@dataclasses.dataclass(frozen=True)
class ReferenceCatalog:
    mic: str
    rows: tuple
    complete: bool
    content_sha256: str


def parse_filename(name):
    """(mic, channel, source_ts, is_daily) for an exact feed filename.

    None for anything that does not match the captured grammar -- lookalike
    names, traversal attempts, other venues' files in a listing.
    """
    match = _FILENAME_RE.match(name)
    if match is None:
        return None
    source, channel = match.group(1), match.group(2)
    try:
        if match.group(3) is not None:
            stamp = dt.datetime(int(match.group(3)), int(match.group(4)),
                                int(match.group(5)), int(match.group(6)),
                                int(match.group(7)))
            is_daily = False
        else:
            stamp = dt.datetime(int(match.group(8)), int(match.group(9)),
                                int(match.group(10)))
            is_daily = True
    except ValueError:
        return None
    return _MIC_BY_SOURCE[source], channel, stamp, is_daily


class DeutscheBoerseHttp:
    """Index + download transport with the R2 one-redirect rule."""

    def __init__(self, timeout=(3.05, 20)):
        self._session = requests.Session()
        self._timeout = timeout

    def list_index(self, mic, channel):
        source = SOURCE_BY_MIC.get(mic)
        if source is None:
            raise PriceUnavailable(f'unsupported MIC {mic}')
        url = f'{INDEX_BASE}/api/{source}-{channel}'
        try:
            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable(f'index {mic}/{channel}: {exc}') from exc
        if not isinstance(payload, dict):
            raise PriceUnavailable(f'index {mic}/{channel}: not an object')
        return payload

    def download(self, file, *, max_compressed=52_428_800):
        """The compressed bytes of one feed file.

        The signed URL expires in ~2 seconds, so the redirect is followed
        immediately -- but manually: exactly one hop, only from the index
        host, only to the observed bucket prefix (R2).
        """
        # The reason leads every message: the cycle row truncates to 48
        # characters, and a filename-first message once left nothing but
        # 'download <name>:' in the stored diagnostics.
        try:
            first = self._session.get(file.url, timeout=self._timeout,
                                      allow_redirects=False)
        except requests.RequestException as exc:
            raise PriceUnavailable(f'{exc} ({file.remote_id})') from exc

        if first.status_code in (301, 302, 303, 307, 308):
            location = first.headers.get('Location', '')
            if not location.startswith(ALLOWED_REDIRECT_PREFIX):
                raise PriceUnavailable(
                    f'redirect outside the observed bucket '
                    f'({file.remote_id})')
            try:
                final = self._session.get(location, timeout=self._timeout,
                                          allow_redirects=False)
                final.raise_for_status()
            except requests.RequestException as exc:
                raise PriceUnavailable(f'{exc} ({file.remote_id})') from exc
        elif first.status_code == 200:
            final = first
        else:
            raise PriceUnavailable(
                f'HTTP {first.status_code} ({file.remote_id})')

        body = final.content
        if len(body) > max_compressed:
            raise PriceUnavailable(
                f'compressed size {len(body)} exceeds {max_compressed} '
                f'({file.remote_id})')
        return body


def _decimal(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        parsed = decimal.Decimal(str(value))
    except decimal.InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _event_time(value):
    """Naive-UTC datetime from the captured ISO-8601 'Z' format."""
    if not isinstance(value, str) or not value.endswith('Z'):
        return None
    text = value[:-1]
    # Nanosecond precision is real in the feed; fromisoformat takes at most
    # microseconds, so the fraction is truncated to six digits.
    if '.' in text:
        whole, fraction = text.split('.', 1)
        text = f'{whole}.{fraction[:6]}' if fraction else whole
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def _trade_from(row, mic):
    """One TradeEvent from a captured post-trade row, or None (rejected)."""
    venue_mic = row.get('venueOfExecution')
    if venue_mic not in OBSERVED_VENUE_MICS[mic]:
        return None
    isin = row.get('instrumentIdentificationCode')
    if not isinstance(isin, str) or not _ISIN_RE.match(isin):
        return None
    if row.get('priceCurrency') != 'EUR':
        return None
    # R4: the only observed modification indicator is '-'. Anything else is
    # an unobserved representation this parser must not guess a meaning for.
    if row.get('mmtModificationInd', '-') != '-':
        return None
    event_id = row.get('transactionIdentificationCode')
    if not isinstance(event_id, str) or not event_id:
        return None
    event_ts = _event_time(row.get('tradingDateAndTime'))
    if event_ts is None:
        return None
    price = _decimal(row.get('price'))
    if price is None or price <= 0:
        return None
    volume = row.get('quantity')
    if isinstance(volume, bool) or not isinstance(volume, (int, float)) or \
            volume < 0:
        return None
    return TradeEvent(
        mic=mic, isin=isin, event_id=event_id, original_event_id=None,
        action='new', event_ts=event_ts, price=price, volume=int(volume),
        # R5: only XETR carries the marker; 'C' is the closing auction.
        is_official_close=(row.get('lastTradeIndicator') == 'C'),
        venue_mic=venue_mic)


def _book_from(row, mic):
    """One BookEvent from a captured pre-trade row, or None.

    XGAT books are flat bid/ask rows; XETR top-of-book rows use the best*
    spelling. XETR depth rows (mdBidMktDepthGroup1 etc.) are not errors --
    they are simply not top-of-book events and yield None without counting.
    """
    isin = row.get('instrumentIdentificationCode')
    if not isinstance(isin, str) or not _ISIN_RE.match(isin):
        return None
    if row.get('priceCurrency') != 'EUR':
        return None
    if 'bid' in row or 'ask' in row:
        bid = _decimal(row.get('bid'))
        ask = _decimal(row.get('ask'))
        stamp = _event_time(row.get('updateDateAndTime'))
    elif 'bestBid' in row or 'bestAsk' in row:
        bid = _decimal(row.get('bestBid'))
        ask = _decimal(row.get('bestAsk'))
        stamp = _event_time(row.get('updateDateAndTime'))
    else:
        return None
    if bid is None or ask is None or stamp is None:
        return None
    if bid <= 0 or ask <= 0 or bid > ask:
        return None
    return BookEvent(mic=mic, isin=isin, event_ts=stamp, bid=bid, ask=ask)


def _is_depth_row(row):
    return isinstance(row, dict) and (
        'mdBidMktDepthGroup1' in row or 'mdAskMktDepthGroup1' in row)


class DeutscheBoerseProvider:
    source = 'deutsche_boerse_delayed'

    def __init__(self, http):
        self._http = http

    def files_after(self, mic, channel, cursor):
        """Unseen minute files for one channel, oldest first.

        Daily files are listed by the same index but consumed by the
        reconciliation path, not the five-minute cycle.
        """
        payload = self._http.list_index(mic, channel)
        names = payload.get('CurrentFiles')
        if not isinstance(names, list):
            raise PriceUnavailable(f'index {mic}/{channel}: no file list')
        seen_ts = cursor.source_ts if cursor is not None else None
        files = []
        for name in names:
            if not isinstance(name, str):
                continue
            parsed = parse_filename(name)
            if parsed is None:
                continue
            file_mic, file_channel, stamp, is_daily = parsed
            if file_mic != mic or file_channel != channel or is_daily:
                continue
            if seen_ts is not None and stamp <= seen_ts:
                continue
            files.append(FeedFile(
                mic=mic, channel=channel, remote_id=name, source_ts=stamp,
                url=f'{INDEX_BASE}/api/download/{name}', is_daily=False))
        # Filename source time is the order; HTML/JSON listing order is not.
        files.sort(key=lambda file: file.source_ts)
        if cursor is None and files:
            # Cold start: the index lists roughly a day of files, and the
            # oldest ones are already deleted upstream. A first-ever cursor
            # begins near the head of the feed; catch-up from the cursor is
            # for daemon downtime, and day-scale history has its own path
            # (the R11 daily files).
            cutoff = files[-1].source_ts - COLD_START_WINDOW
            files = [file for file in files if file.source_ts >= cutoff]
        return files

    def download(self, file, **limits):
        return self._http.download(file, **limits)

    def parse(self, file, compressed, *, max_uncompressed=262_144_000,
              max_ratio=100):
        """One FeedBatch from one file's compressed bytes.

        Per-row invalidity rejects THAT row and counts it; structural
        corruption (bad gzip, bad JSON, conflicting duplicate event ids)
        rejects the whole file so the cursor cannot advance past it.
        """
        pieces = []
        total = 0
        try:
            with gzip.GzipFile(fileobj=_Bytes(compressed)) as handle:
                while chunk := handle.read(1 << 20):
                    total += len(chunk)
                    if total > max_uncompressed:
                        raise FeedRejected(
                            f'{file.remote_id}: uncompressed size exceeds '
                            f'{max_uncompressed}')
                    if compressed and total / len(compressed) > max_ratio:
                        raise FeedRejected(
                            f'{file.remote_id}: decompression ratio exceeds '
                            f'{max_ratio}')
                    pieces.append(chunk)
        except (OSError, EOFError) as exc:
            raise FeedRejected(f'{file.remote_id}: invalid gzip: {exc}') \
                from exc

        try:
            text = b''.join(pieces).decode('utf-8')
        except UnicodeDecodeError as exc:
            raise FeedRejected(f'{file.remote_id}: not UTF-8: {exc}') from exc

        rows = []
        for number, line in enumerate(text.split('\n'), start=1):
            line = line.strip('\r').strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise FeedRejected(
                    f'{file.remote_id}: invalid JSON line {number}: '
                    f'{exc}') from exc

        trades = []
        books = []
        rejected = 0
        seen_events = {}
        for row in rows:
            if not isinstance(row, dict):
                rejected += 1
                continue
            if file.channel == 'posttrade':
                trade = _trade_from(row, file.mic)
                if trade is None:
                    rejected += 1
                    continue
                previous = seen_events.get(trade.event_id)
                if previous is not None:
                    if previous == trade:
                        continue  # byte-identical duplicate: idempotent
                    raise FeedRejected(
                        f'{file.remote_id}: conflicting duplicate event '
                        f'{trade.event_id}')
                seen_events[trade.event_id] = trade
                trades.append(trade)
            else:
                if _is_depth_row(row):
                    continue  # depth is not top-of-book; not an error
                book = _book_from(row, file.mic)
                if book is None:
                    rejected += 1
                    continue
                books.append(book)

        return FeedBatch(
            mic=file.mic, channel=file.channel, remote_id=file.remote_id,
            source_ts=file.source_ts, references=(), trades=tuple(trades),
            books=tuple(books),
            # R6: the delayed service carries no reference channel; absence
            # of references can never mark a mapping unavailable.
            reference_complete=False,
            record_count=len(trades) + len(books),
            rejected_records=rejected)


class _Bytes:
    """Minimal file-object over bytes; avoids importing io for one use."""

    def __init__(self, data):
        self._data = data
        self._pos = 0

    def read(self, size=-1):
        if size is None or size < 0:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
        else:
            chunk = self._data[self._pos:self._pos + size]
            self._pos += len(chunk)
        return chunk


def apply_trade_events(current, incoming):
    """The correction algebra over a normalized event set.

    The captured feed has never shown a correction (R4), so live parsing
    emits only action='new'; this function is the journal's reviewed rule
    for the day observation proves otherwise. A correction or cancellation
    whose original is absent from both the retained set and the same batch
    cannot silently revoke a guessed trade -- it rejects.
    """
    updated = dict(current)
    ordered = sorted(incoming, key=lambda item: (item.event_ts, item.event_id))
    known = set(updated) | {event.event_id for event in ordered
                            if event.action == 'new'}
    for event in ordered:
        if event.action == 'new':
            updated[event.event_id] = event
        elif event.action in ('correct', 'cancel'):
            if event.original_event_id not in known:
                raise FeedRejected(
                    f'{event.event_id}: unknown original event '
                    f'{event.original_event_id}')
            updated.pop(event.original_event_id, None)
            if event.action == 'correct':
                updated[event.event_id] = event
        else:
            raise FeedRejected(f'{event.event_id}: unknown action '
                               f'{event.action}')
    return updated
