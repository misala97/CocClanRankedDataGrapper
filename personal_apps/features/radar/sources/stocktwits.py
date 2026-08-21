# personal_apps/features/radar/sources/stocktwits.py
"""StockTwits ingest.

Finance-native and dense -- messages arrive already $TICKER-tagged and about
half carry a native bull/bear label -- but narrow: the discovery surface is the
30 trending symbols, so the standing set in the scheduler is what widens it.

Crypto is dropped here rather than downstream, using the explicit
instrument_class field rather than guessing at the .X suffix (spec 3.7).
"""
import concurrent.futures
import datetime as dt

import requests

from . import FetchResult, RawPost

API_BASE = 'https://api.stocktwits.com/api/2'
USER_AGENT_DEFAULT = 'personal_apps-radar/0.1 (personal research)'

# The API returns at most this many messages per stream call. A full page of
# messages newer than `since` means there were probably more we never saw.
PAGE_SIZE = 30

# Measured: a stream call takes ~43 seconds, and trending the same, with
# timings identical enough to be a deliberate throttle rather than load.
# Serially that is five minutes for seven symbols against a three-minute
# cycle, so the calls run concurrently. Kept low because the rate limit is
# undocumented and a burst is the wrong thing to guess with.
MAX_CONCURRENCY = 4


class StockTwitsUnavailable(Exception):
    """This symbol's stream did not arrive. Never turns into a zero count."""


class StockTwitsClient:
    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=25):
        self._headers = {'User-Agent': user_agent}
        self._timeout = timeout

    def get(self, path, params=None):
        try:
            response = requests.get(API_BASE + path, params=params,
                                    headers=self._headers, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise StockTwitsUnavailable('%s: %s' % (path, exc)) from exc


def trending(client):
    """Trending equity symbols. Crypto is excluded by instrument_class."""
    payload = client.get('/trending/symbols.json')
    return [s['symbol'] for s in payload.get('symbols', [])
            if (s.get('instrument_class') or '').upper() != 'CRYPTO']


def _to_raw_post(message, symbol):
    created = dt.datetime.strptime(message['created_at'], '%Y-%m-%dT%H:%M:%SZ')
    user = message.get('user') or {}
    entities = message.get('entities') or {}
    sentiment = (entities.get('sentiment') or {}).get('basic')
    likes = (message.get('likes') or {}).get('total') or 0
    symbols = [s['symbol'] for s in (message.get('symbols') or [])] or [symbol]

    return RawPost(
        source='stocktwits',
        external_id='stocktwits:%s' % message['id'],
        channel=symbol,
        author=user.get('username'),
        created_utc=created,
        title=None,
        body=message.get('body') or '',
        score=int(likes),
        num_comments=0,
        url='https://stocktwits.com/message/%s' % message['id'],
        native_tickers=symbols,
        native_sentiment=sentiment,
    )


def _fetch_one(client, symbol, since):
    """One symbol's stream. Returns (posts, rate, truncated) or raises."""
    payload = client.get('/streams/symbol/%s.json' % symbol)
    messages = payload.get('messages') or []

    fresh = [p for p in (_to_raw_post(m, symbol) for m in messages)
             if p.created_utc > since]

    rate = None
    if messages:
        stamps = [dt.datetime.strptime(m['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                  for m in messages]
        span = (max(stamps) - min(stamps)).total_seconds() / 3600
        rate = (len(messages) / span) if span > 0 else float(len(messages))

    # A full page, all of it new, means the window very likely overflowed.
    return fresh, rate, len(fresh) >= PAGE_SIZE


def fetch(since, client, symbols, max_workers=MAX_CONCURRENCY):
    """Every message newer than `since` across `symbols`.

    Requests run concurrently because each takes ~43 seconds against a
    three-minute cycle; serially, seven symbols would not fit.

    Also reports observed messages/hour per symbol, which is what lets the
    scheduler poll a hot symbol often and a quiet one rarely (spec 3.5).
    """
    if not symbols:
        return FetchResult(posts=[], status='ok')

    posts, rates = [], {}
    failures = 0
    truncated = False

    workers = max(1, min(max_workers, len(symbols)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, client, symbol, since): symbol
                   for symbol in symbols}
        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                fresh, rate, overflowed = future.result()
            except StockTwitsUnavailable:
                failures += 1
                continue
            posts.extend(fresh)
            if rate is not None:
                rates[symbol] = rate
            truncated = truncated or overflowed

    if failures == len(symbols):
        return FetchResult(posts=[], status='missing')

    status = 'truncated' if (truncated or failures) else 'ok'
    return FetchResult(posts=posts, status=status, rates=rates)
