# personal_apps/features/radar/prices/yahoo.py
"""The one module that knows Yahoo's chart JSON.

Yahoo is unofficial and unsupported: no key, no contract, and endpoints
that change without notice. Market-data v2 therefore keeps it to three
bounded roles -- the German Xetra history backfill, the deep US history
tail, and a flag-gated US quote fallback that is not a planned activation
[A2] -- and this adapter is built around refusal: identity mismatch,
missing timestamps, auth walls, and malformed parallel arrays all make an
instrument absent for the cycle. No cookie scraping, no browser
automation, no escalating retries; a 401/403/429 opens an exponential
backoff window during which no request leaves the process at all.

Only the per-symbol /v8/finance/chart endpoint is used. The batch quote
endpoint requires authorization Yahoo does not grant and is deliberately
not depended on.
"""
import concurrent.futures
import datetime as dt
import decimal
import threading
import time
import urllib.parse

import requests

from . import PriceUnavailable, Quote

API_BASE = 'https://query1.finance.yahoo.com/v8/finance/chart/'

# Exchange metadata allowlists per MIC: every MIC the universe migration
# seeds, and nothing else. Unknown MICs or mismatched metadata reject the
# response rather than weakening identity validation.
_EXCHANGE_ALLOWLIST = {
    'XNAS': {'NMS', 'NGM', 'NCM', 'NAS'},
    'XNGS': {'NMS', 'NGM', 'NAS'},
    'XNMS': {'NMS', 'NGM', 'NAS'},
    'XNCM': {'NCM', 'NAS', 'NMS'},
    'XNYS': {'NYQ', 'NYS'},
    'ARCX': {'PCX', 'ARC'},
    'XASE': {'ASE', 'AMX'},
    'BATS': {'BTS', 'CBT'},
    'IEXG': {'IEX'},
    'XETR': {'GER', 'XETRA', 'EBS'},
}

_BACKOFF_STEPS = (60, 120, 240, 480, 960, 1800)
_CACHE_TTL_SECONDS = 60


class YahooHttp:
    """Bounded transport: one session, cache, and auth-aware backoff."""

    def __init__(self, timeout=(3.05, 15)):
        self._session = requests.Session()
        self._timeout = timeout
        self._lock = threading.Lock()
        self._cache = {}
        self._backoff_index = -1
        self._backoff_until = 0.0

    def get_chart(self, symbol, *, interval, period1, period2,
                  include_prepost):
        now = time.monotonic()
        key = (symbol, interval, period1, period2, include_prepost)
        with self._lock:
            if now < self._backoff_until:
                raise PriceUnavailable(
                    'yahoo backoff active for %d more seconds'
                    % int(self._backoff_until - now))
            cached = self._cache.get(key)
            if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
                return cached[1]

        params = {
            'interval': interval, 'period1': period1, 'period2': period2,
            'includePrePost': 'true' if include_prepost else 'false',
        }
        try:
            response = self._session.get(
                API_BASE + urllib.parse.quote(symbol), params=params,
                timeout=self._timeout,
                headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, 'response', None),
                             'status_code', None)
            if status in (401, 403, 429):
                with self._lock:
                    self._backoff_index = min(self._backoff_index + 1,
                                              len(_BACKOFF_STEPS) - 1)
                    self._backoff_until = time.monotonic() + _BACKOFF_STEPS[
                        self._backoff_index]
            raise PriceUnavailable('chart %s: %s' % (symbol, exc)) from exc
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable('chart %s: %s' % (symbol, exc)) from exc

        with self._lock:
            # A successful request resets the ladder.
            self._backoff_index = -1
            self._backoff_until = 0.0
            self._cache[key] = (time.monotonic(), payload)
        return payload


def _decimal(value):
    return decimal.Decimal(str(value))


def _result(payload):
    """The single chart result dict, or None for any dishonest envelope."""
    if not isinstance(payload, dict):
        return None
    chart = payload.get('chart')
    if not isinstance(chart, dict):
        return None
    results = chart.get('result')
    if not isinstance(results, list) or len(results) != 1:
        return None
    result = results[0]
    return result if isinstance(result, dict) else None


def _identity_ok(meta, provider_symbol, currency, mic):
    allowed = _EXCHANGE_ALLOWLIST.get(mic)
    if allowed is None:
        return False
    if not isinstance(meta, dict):
        return False
    if meta.get('symbol') != provider_symbol:
        return False
    if meta.get('currency') != currency:
        return False
    exchange = meta.get('exchangeName')
    return exchange in allowed


def _bars(result):
    """Validated (timestamp, close, volume) triples from parallel arrays."""
    timestamps = result.get('timestamp')
    indicators = result.get('indicators')
    if not isinstance(timestamps, list) or not isinstance(indicators, dict):
        return None
    quote_groups = indicators.get('quote')
    if not isinstance(quote_groups, list) or len(quote_groups) != 1 or \
            not isinstance(quote_groups[0], dict):
        return None
    closes = quote_groups[0].get('close')
    volumes = quote_groups[0].get('volume')
    if not isinstance(closes, list) or len(closes) != len(timestamps):
        return None
    if not isinstance(volumes, list) or len(volumes) != len(timestamps):
        volumes = [None] * len(timestamps)
    bars = []
    for stamp, close, volume in zip(timestamps, closes, volumes):
        if not isinstance(stamp, int) or isinstance(stamp, bool):
            return None
        bars.append((stamp, close, volume))
    return bars


class YahooProvider:
    source = 'yahoo_chart'

    def __init__(self, http):
        self._http = http
        self._semaphore = threading.Semaphore(4)
        # The semaphore is the binding concurrency guarantee; the pool size
        # only right-sizes the thread count to it.
        self._max_workers = 4

    def _fetch(self, symbol, *, interval, period1, period2, include_prepost):
        with self._semaphore:
            return self._http.get_chart(
                symbol, interval=interval, period1=period1, period2=period2,
                include_prepost=include_prepost)

    def quotes_for_instruments(self, instruments):
        """Current quotes keyed by provider symbol; invalid ones absent."""
        instruments = list(instruments)
        if not instruments:
            return {}
        found = {}
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(self._quote_for, instrument): instrument
                for instrument in instruments}
            for future in concurrent.futures.as_completed(futures):
                quote = future.result()
                if quote is not None:
                    found[quote.provider_symbol] = quote
        return found

    def _quote_for(self, instrument):
        now = int(time.time())
        try:
            payload = self._fetch(
                instrument.provider_symbol, interval='5m',
                period1=now - 86400, period2=now, include_prepost=True)
        except PriceUnavailable:
            return None
        result = _result(payload)
        if result is None:
            return None
        meta = result.get('meta')
        if not _identity_ok(meta, instrument.provider_symbol,
                            instrument.currency, instrument.mic):
            return None
        bars = _bars(result)
        if not bars:
            return None
        selected = None
        for stamp, close, volume in reversed(bars):
            if close is None:
                continue
            try:
                price = _decimal(close)
            except decimal.InvalidOperation:
                return None
            if price <= 0:
                return None
            selected = (stamp, price, volume)
            break
        if selected is None:
            return None
        stamp, price, volume = selected

        previous_close = None
        for name in ('chartPreviousClose', 'previousClose'):
            value = meta.get(name)
            if isinstance(value, (int, float)) and value > 0:
                previous_close = _decimal(value)
                break
        regular_close = None
        regular_price = meta.get('regularMarketPrice')
        regular_time = meta.get('regularMarketTime')
        if (isinstance(regular_price, (int, float)) and regular_price > 0 and
                isinstance(regular_time, int)):
            same_day = (
                dt.datetime.fromtimestamp(regular_time, dt.timezone.utc).date()
                == dt.datetime.fromtimestamp(stamp, dt.timezone.utc).date())
            if same_day:
                regular_close = _decimal(regular_price)

        try:
            return Quote(
                ticker=instrument.ticker, market=instrument.market,
                venue=instrument.venue, mic=instrument.mic,
                provider_symbol=instrument.provider_symbol,
                currency=instrument.currency, price=price,
                previous_close=previous_close, regular_close=regular_close,
                quote_ts=dt.datetime.fromtimestamp(
                    stamp, dt.timezone.utc).replace(tzinfo=None),
                volume=int(volume) if volume is not None else None,
                provider_delay='delayed', source='yahoo_chart',
                price_basis='trade')
        except (ValueError, TypeError, OSError, OverflowError):
            return None

    def daily_closes(self, symbol, days, mic_code=None):
        """[(date, close)] oldest-first; [] on any failure.

        [A1] Reads the split-only ``quote.close`` series, never ``adjclose``:
        Yahoo's adjusted close folds dividends in as well, while Massive
        ``adjusted=true`` and the incumbent Twelve Data default are
        split-only. Mixing the bases would manufacture a seam at every
        dividend.
        """
        now = int(time.time())
        try:
            payload = self._fetch(
                symbol, interval='1d',
                period1=now - (days + 3) * 86400, period2=now,
                include_prepost=False)
        except PriceUnavailable:
            return []
        result = _result(payload)
        if result is None:
            return []
        meta = result.get('meta')
        if mic_code is not None:
            currency = 'EUR' if mic_code == 'XETR' else 'USD'
            if not _identity_ok(meta, symbol, currency, mic_code):
                return []
        elif not isinstance(meta, dict) or meta.get('symbol') != symbol:
            # Compatibility callers may omit the MIC, but an exact symbol
            # match is still mandatory. Production v2 callers supply MIC and
            # therefore receive the full symbol/currency/exchange check.
            return []
        bars = _bars(result)
        if bars is None:
            return []
        by_date = {}
        for stamp, close, _ in bars:
            if close is None:
                continue
            try:
                price = _decimal(close)
            except decimal.InvalidOperation:
                return []
            if price <= 0:
                continue
            day = dt.datetime.fromtimestamp(stamp, dt.timezone.utc).date()
            # First bar of a date wins; a later intraday repeat of the same
            # date must not overwrite the daily bar.
            by_date.setdefault(day, price)
        floor = (dt.datetime.now(dt.timezone.utc)
                 - dt.timedelta(days=days + 3)).date()
        return sorted(
            (day, price) for day, price in by_date.items() if day >= floor)
