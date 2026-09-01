# personal_apps/features/radar/prices/massive.py
"""The one module that knows Massive's grouped-daily JSON.

[A1] One request per US trading day returns every US stock's OHLCV -- the
universe-wide daily-close source of market-data v2. This module owns
transport (key, pacing, backoff) and payload truth (envelope, per-row
validation, exact-date resolution, duplicate handling) and returns exact
uppercase provider symbols. It deliberately does NOT import models, join to
Radar identities, or own any progress cursor: identity and persistence
belong to market_data, where RadarInstrument exists.

Base URL is configuration because of the Polygon->Massive rebrand: the
default is api.massive.com; api.polygon.io is the documented
legacy-compatibility value, announced for phase-out during 2026.
"""
import dataclasses
import datetime as dt
import decimal
import hashlib
import json
import logging
import os
import threading
import time
import zoneinfo

import requests

logger = logging.getLogger('radar.massive')

DEFAULT_BASE_URL = 'https://api.massive.com'

# Free tier: five calls per minute. The pacer is process-local and
# monotonic; tests inject the clock so nothing sleeps for real.
CALLS_PER_MINUTE = 5

_BACKOFF_STEPS = (60, 120, 240)

# Grouped rows carry epoch-millisecond event times; a row belongs to the
# requested day only if that instant falls on the requested date in the US
# exchange timezone.
_US_EASTERN = zoneinfo.ZoneInfo('America/New_York')


class MassiveTransportError(Exception):
    """Transport-level failure: network, HTTP status, quota, missing key."""

    def __init__(self, message, http_status=None, backoff_until=None):
        super().__init__(message)
        self.http_status = http_status
        self.backoff_until = backoff_until


@dataclasses.dataclass(frozen=True)
class ProviderGroupedDay:
    """One accepted day's validated closes, keyed by exact provider symbol."""
    closes: dict
    payload_sha256: str
    provider_rows: int
    malformed_rows: int
    duplicate_conflicts: int
    adjustment_basis: str = 'split'


@dataclasses.dataclass(frozen=True)
class GroupedFetch:
    """Every attempt's typed outcome, so failure never reads as progress."""
    status: str  # accepted | no_data | rejected | transport_error
    day: ProviderGroupedDay | None = None
    error_code: str | None = None
    http_status: int | None = None
    backoff_until: dt.datetime | None = None


class MassiveHttp:
    """Keyed transport with the free tier's pacing and 429 backoff."""

    def __init__(self, timeout=(3.05, 30), clock=time.monotonic,
                 sleep=time.sleep):
        self._session = requests.Session()
        self._timeout = timeout
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._recent_calls = []
        self._backoff_index = -1
        self._backoff_until = 0.0
        self._warned_missing_key = False

    def get_grouped_daily(self, day):
        key = os.getenv('RADAR_MASSIVE_API_KEY')
        if not key:
            if not self._warned_missing_key:
                logger.warning('RADAR_MASSIVE_API_KEY is not set -- the '
                               'Massive adapter stays dormant')
                self._warned_missing_key = True
            raise MassiveTransportError('no API key configured')
        base = os.getenv('RADAR_MASSIVE_BASE_URL', DEFAULT_BASE_URL)

        with self._lock:
            now = self._clock()
            if now < self._backoff_until:
                raise MassiveTransportError(
                    'massive backoff active for %d more seconds'
                    % int(self._backoff_until - now),
                    http_status=429)
            self._recent_calls = [
                stamp for stamp in self._recent_calls if now - stamp < 60]
            if len(self._recent_calls) >= CALLS_PER_MINUTE:
                wait = 60 - (now - self._recent_calls[0])
                if wait > 0:
                    self._sleep(wait)
            self._recent_calls.append(self._clock())

        url = '%s/v2/aggs/grouped/locale/us/market/stocks/%s' % (
            base.rstrip('/'), day.isoformat())
        try:
            response = self._session.get(
                url, params={'adjusted': 'true', 'apiKey': key},
                timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, 'response', None),
                             'status_code', None)
            if status == 429:
                with self._lock:
                    self._backoff_index = min(self._backoff_index + 1,
                                              len(_BACKOFF_STEPS) - 1)
                    self._backoff_until = self._clock() + _BACKOFF_STEPS[
                        self._backoff_index]
            raise MassiveTransportError(
                'grouped %s: %s' % (day, exc), http_status=status) from exc
        except (requests.RequestException, ValueError) as exc:
            raise MassiveTransportError(
                'grouped %s: %s' % (day, exc)) from exc

        with self._lock:
            self._backoff_index = -1
            self._backoff_until = 0.0
        return payload


def _valid_close(row, day):
    """The (symbol, Decimal close) of one valid row, else None."""
    symbol = row.get('T')
    close = row.get('c')
    stamp = row.get('t')
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    if not isinstance(close, (int, float)) or isinstance(close, bool):
        return None
    if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
        return None
    try:
        price = decimal.Decimal(str(close))
    except decimal.InvalidOperation:
        return None
    if price <= 0 or not price.is_finite():
        return None
    event = dt.datetime.fromtimestamp(stamp / 1000, tz=dt.timezone.utc)
    if event.astimezone(_US_EASTERN).date() != day:
        return None
    return symbol.strip().upper(), price


class MassiveProvider:
    source = 'massive_grouped'

    def __init__(self, http):
        self._http = http

    def grouped_closes(self, day):
        """One ``GroupedFetch`` per attempt; never raises."""
        try:
            payload = self._http.get_grouped_daily(day)
        except MassiveTransportError as exc:
            return GroupedFetch(
                status='transport_error',
                error_code=str(exc)[:48], http_status=exc.http_status)
        except Exception as exc:  # a hostile payload must not kill the job
            return GroupedFetch(status='transport_error',
                                error_code=str(exc)[:48])

        if not isinstance(payload, dict) or payload.get('status') != 'OK':
            return GroupedFetch(status='rejected', error_code='bad_envelope')
        rows = payload.get('results')
        if rows == [] :
            # A structurally valid but EMPTY grouped result for an expected
            # trading day is incomplete evidence, never accepted progress.
            return GroupedFetch(status='no_data')
        if not isinstance(rows, list):
            return GroupedFetch(status='rejected', error_code='bad_results')

        sha = hashlib.sha256(
            json.dumps(payload, sort_keys=True,
                       separators=(',', ':')).encode('utf-8')).hexdigest()

        closes = {}
        conflicted = set()
        malformed = 0
        conflicts = 0
        for row in rows:
            if not isinstance(row, dict):
                malformed += 1
                continue
            valid = _valid_close(row, day)
            if valid is None:
                malformed += 1
                continue
            symbol, price = valid
            if symbol in conflicted:
                continue
            existing = closes.get(symbol)
            if existing is None:
                closes[symbol] = price
            elif existing != price:
                # Last-row-wins is forbidden: a conflicting duplicate refuses
                # the symbol entirely and is counted for the day's ledger.
                del closes[symbol]
                conflicted.add(symbol)
                conflicts += 1
            # An identical duplicate deduplicates silently.

        return GroupedFetch(
            status='accepted',
            day=ProviderGroupedDay(
                closes=closes, payload_sha256=sha, provider_rows=len(rows),
                malformed_rows=malformed, duplicate_conflicts=conflicts))
