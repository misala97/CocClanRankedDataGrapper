# personal_apps/tests/test_radar_stocktwits.py
"""StockTwits: finance-native, dense, and narrow.

Measured at ~23 messages/hour on a trending symbol with 20-27 distinct authors
per 30 messages. Its discovery surface is only the 30 trending symbols, which
is why the standing set exists (spec 3.5).
"""
import datetime as dt

from features.radar.sources import FetchResult
from features.radar.sources import stocktwits


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path not in self.payloads:
            raise stocktwits.StockTwitsUnavailable('404 %s' % path)
        return self.payloads[path]


def _message(ident, created, body='$ZZA to the moon', user=1, sentiment='Bullish'):
    return {
        'id': ident,
        'body': body,
        'created_at': created.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'user': {'id': user, 'username': 'user%d' % user},
        'symbols': [{'symbol': 'ZZA'}],
        'entities': {'sentiment': {'basic': sentiment}} if sentiment else {},
        'likes': {'total': 3},
    }


BASE = dt.datetime(2026, 8, 21, 14, 0, 0)


def test_trending_filters_crypto_by_instrument_class():
    """instrument_class is explicit, so the filter is a field check rather than
    a guess at what .X means (spec 3.7)."""
    client = FakeClient({'/trending/symbols.json': {'symbols': [
        {'symbol': 'ZZA', 'instrument_class': 'Stock'},
        {'symbol': 'BTC.X', 'instrument_class': 'CRYPTO'},
        {'symbol': 'ZZB', 'instrument_class': 'Stock'},
    ]}})
    assert stocktwits.trending(client) == ['ZZA', 'ZZB']


def test_a_stream_becomes_rawposts():
    client = FakeClient({'/streams/symbol/ZZA.json': {
        'messages': [_message(2, BASE), _message(1, BASE - dt.timedelta(minutes=5))]}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    assert len(result.posts) == 2
    post = result.posts[0]
    assert post.source == 'stocktwits'
    assert post.external_id == 'stocktwits:2'
    assert post.native_tickers == ['ZZA']
    assert post.native_sentiment == 'Bullish'
    assert post.author == 'user1'


def test_messages_older_than_since_are_dropped():
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': [
        _message(2, BASE),
        _message(1, BASE - dt.timedelta(hours=4)),
    ]}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert [p.external_id for p in result.posts] == ['stocktwits:2']


def test_a_full_page_of_new_messages_is_truncated():
    """30 is the page size. All 30 newer than `since` means there are probably
    more we did not see, and an undercount must never reach a baseline."""
    messages = [_message(i, BASE - dt.timedelta(seconds=i)) for i in range(30)]
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': messages}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert result.status == 'truncated'
    assert len(result.posts) == 30


def test_one_symbol_failing_does_not_lose_the_others():
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': [_message(1, BASE)]}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA', 'MISSING'])
    assert [p.external_id for p in result.posts] == ['stocktwits:1']
    assert result.status == 'truncated'


def test_every_symbol_failing_is_missing_with_no_posts():
    client = FakeClient({})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA', 'ZZB'])
    assert result.status == 'missing'
    assert result.posts == []


def test_message_rate_is_reported_per_symbol():
    """The scheduler derives each symbol's poll interval from this, because the
    API returns 30 messages whatever their timespan (spec 3.5)."""
    messages = [_message(i, BASE - dt.timedelta(minutes=i * 2)) for i in range(30)]
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': messages}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=6), client, ['ZZA'])
    # 30 messages spanning 58 minutes -> a bit over 30/hour.
    assert 25 < result.rates['ZZA'] < 40


def test_an_empty_stream_is_ok_not_missing():
    """A healthy source that saw nothing is a real zero. Only a failure is
    `missing` (spec 4.5)."""
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': []}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert result.status == 'ok'
    assert result.posts == []


def test_symbols_are_fetched_concurrently():
    """Measured: a stream call takes ~43 seconds, throttled rather than loaded.
    Serially, a cycle's worth of symbols would not fit inside the cycle."""
    import threading
    import time

    peak = {'n': 0, 'now': 0}
    lock = threading.Lock()

    class SlowClient:
        def get(self, path, params=None):
            with lock:
                peak['now'] += 1
                peak['n'] = max(peak['n'], peak['now'])
            time.sleep(0.2)
            with lock:
                peak['now'] -= 1
            return {'messages': [_message(1, BASE)]}

    stocktwits.fetch(BASE - dt.timedelta(hours=1), SlowClient(),
                     ['A', 'B', 'C', 'D'], max_workers=4)
    assert peak['n'] > 1, 'requests ran serially'


def test_concurrency_never_exceeds_the_cap():
    """The rate limit is undocumented, so a burst is the wrong thing to guess
    with."""
    import threading
    import time

    peak = {'n': 0, 'now': 0}
    lock = threading.Lock()

    class SlowClient:
        def get(self, path, params=None):
            with lock:
                peak['now'] += 1
                peak['n'] = max(peak['n'], peak['now'])
            time.sleep(0.1)
            with lock:
                peak['now'] -= 1
            return {'messages': []}

    stocktwits.fetch(BASE - dt.timedelta(hours=1), SlowClient(),
                     ['A', 'B', 'C', 'D', 'E', 'F'], max_workers=2)
    assert peak['n'] <= 2


def test_no_symbols_is_ok_and_costs_nothing():
    """A cycle where nothing is DUE must not look like a failure.

    Narrow on purpose. This function cannot tell "nothing was scheduled" from
    "the source is dead", because both arrive as an empty symbol list -- and
    reading the second as `ok` wrote zero-count buckets for a source that was
    403 on every request. The caller knows which it is and decides; see
    run_radar_ingest._stocktwits_fetcher.
    """
    result = stocktwits.fetch(BASE, FakeClient({}), [])
    assert result.status == 'ok'
    assert result.posts == []
