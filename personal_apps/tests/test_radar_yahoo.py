# personal_apps/tests/test_radar_yahoo.py
"""The Yahoo chart adapter: identity-checked, bounded, and dormant.

Yahoo is an unofficial source without an availability contract, so the
adapter's job is mostly refusal: wrong symbol, wrong currency, wrong
exchange, missing timestamps, and provider errors all make an instrument
absent for the cycle instead of a guessed price.
"""
import datetime as dt
import decimal
import threading
import time
from types import SimpleNamespace

import pytest

from features.radar.prices import Quote
from features.radar.prices import yahoo


def instrument(ticker='AAPL', mic='XNAS', currency='USD',
               provider_symbol=None, market='us', venue='NASDAQ'):
    return SimpleNamespace(
        ticker=ticker, market=market, venue=venue, mic=mic,
        provider_symbol=provider_symbol or ticker, currency=currency)


def chart_payload(symbol='AAPL', currency='USD', exchange='NMS',
                  timestamps=(1788170400, 1788171300),
                  closes=(100.0, 101.0), volumes=(10, 20),
                  adjclose=None):
    quote = {'close': list(closes), 'volume': list(volumes)}
    indicators = {'quote': [quote]}
    indicators['adjclose'] = [{
        'adjclose': list(adjclose if adjclose is not None else closes)}]
    return {'chart': {'result': [{
        'meta': {'symbol': symbol, 'currency': currency,
                 'exchangeName': exchange, 'chartPreviousClose': 99.0},
        'timestamp': list(timestamps),
        'indicators': indicators,
    }], 'error': None}}


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_chart(self, symbol, *, interval, period1, period2,
                  include_prepost):
        self.calls.append(symbol)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_quote_uses_last_non_null_chart_print():
    provider = yahoo.YahooProvider(FakeHttp(chart_payload()))
    found = provider.quotes_for_instruments([instrument('AAPL')])
    quote = found['AAPL']
    assert isinstance(quote, Quote)
    assert quote.price == decimal.Decimal('101.0')
    assert quote.quote_ts == dt.datetime.fromtimestamp(
        1788171300, dt.timezone.utc).replace(tzinfo=None)
    assert (quote.source, quote.price_basis, quote.provider_delay) == (
        'yahoo_chart', 'trade', 'delayed')


def test_null_final_bar_falls_back_to_the_earlier_valid_print():
    payload = chart_payload(closes=(100.0, None), volumes=(10, None))
    quote = yahoo.YahooProvider(FakeHttp(payload)).quotes_for_instruments(
        [instrument('AAPL')])['AAPL']
    assert quote.price == decimal.Decimal('100.0')
    assert quote.quote_ts == dt.datetime.fromtimestamp(
        1788170400, dt.timezone.utc).replace(tzinfo=None)


@pytest.mark.parametrize('payload', [
    {'chart': {'result': None, 'error': {'code': 'Not Found'}}},
    {'chart': {'result': [], 'error': None}},
    chart_payload(symbol='OTHER'),
    chart_payload(currency='EUR'),
    chart_payload(exchange='GER'),
    chart_payload(timestamps=(), closes=(), volumes=()),
    chart_payload(closes=(0.0, -1.0)),
    chart_payload(timestamps=(1788170400,), closes=(100.0, 101.0)),
    {'not': 'a chart'},
])
def test_dishonest_payloads_make_the_instrument_absent(payload):
    provider = yahoo.YahooProvider(FakeHttp(payload))
    assert provider.quotes_for_instruments([instrument('AAPL')]) == {}


def test_transport_errors_make_the_instrument_absent_not_raised():
    from features.radar.prices import PriceUnavailable
    provider = yahoo.YahooProvider(FakeHttp(PriceUnavailable('nope')))
    assert provider.quotes_for_instruments([instrument('AAPL')]) == {}


def test_unknown_mic_rejects_rather_than_weakening_identity():
    provider = yahoo.YahooProvider(FakeHttp(chart_payload(exchange='NMS')))
    assert provider.quotes_for_instruments(
        [instrument('AAPL', mic='XXXX')]) == {}


def test_xetr_instrument_accepts_german_metadata():
    payload = chart_payload(symbol='SAP.DE', currency='EUR', exchange='GER')
    quote = yahoo.YahooProvider(FakeHttp(payload)).quotes_for_instruments(
        [instrument('SAP', mic='XETR', currency='EUR',
                    provider_symbol='SAP.DE', market='de',
                    venue='Xetra')])['SAP.DE']
    assert quote.currency == 'EUR'
    assert quote.mic == 'XETR'


def test_daily_closes_use_the_split_only_close_series_not_adjclose():
    """[A1] Yahoo adjclose is split AND dividend adjusted; Massive and the
    incumbent store are split-only. Selecting adjclose would manufacture a
    dividend seam. A dividend makes the two series differ; the adapter must
    return quote.close."""
    day1 = 1788170400
    day2 = day1 + 86400
    payload = chart_payload(
        timestamps=(day1, day2), closes=(100.0, 101.0), volumes=(1, 1),
        adjclose=(98.5, 101.0))  # dividend-adjusted history differs
    closes = yahoo.YahooProvider(FakeHttp(payload)).daily_closes('AAPL', 5)
    assert closes == [
        (dt.datetime.fromtimestamp(day1, dt.timezone.utc).date(),
         decimal.Decimal('100.0')),
        (dt.datetime.fromtimestamp(day2, dt.timezone.utc).date(),
         decimal.Decimal('101.0')),
    ]


def test_daily_closes_survive_a_split_shaped_series():
    day1 = 1788170400
    day2 = day1 + 86400
    payload = chart_payload(
        timestamps=(day1, day2), closes=(500.0, 50.5), volumes=(1, 1),
        adjclose=(50.0, 50.5))
    closes = yahoo.YahooProvider(FakeHttp(payload)).daily_closes('AAPL', 5)
    assert closes[0][1] == decimal.Decimal('500.0')


def test_daily_closes_deduplicate_by_date_and_sort_oldest_first():
    day = 1788170400
    payload = chart_payload(
        timestamps=(day + 3600, day, day + 86400),
        closes=(100.5, 100.0, 101.0), volumes=(1, 1, 1))
    closes = yahoo.YahooProvider(FakeHttp(payload)).daily_closes('AAPL', 5)
    dates = [entry[0] for entry in closes]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates)) == 2


@pytest.mark.parametrize('payload', [
    chart_payload(symbol='MSFT'),
    chart_payload(currency='EUR'),
    chart_payload(exchange='GER'),
])
def test_daily_closes_reject_mismatched_instrument_metadata(payload):
    provider = yahoo.YahooProvider(FakeHttp(payload))
    assert provider.daily_closes('AAPL', 5, mic_code='XNAS') == []


def test_backoff_stops_requests_after_auth_failures(monkeypatch):
    clock = {'now': 1000.0}
    monkeypatch.setattr(yahoo.time, 'monotonic', lambda: clock['now'])

    class Auth401:
        status_code = 401

    http = yahoo.YahooHttp()

    class FakeSession:
        def get(self, url, params=None, timeout=None, headers=None):
            response = SimpleNamespace(status_code=401)

            def raise_for_status():
                error = yahoo.requests.HTTPError('401')
                error.response = response
                raise error
            response.raise_for_status = raise_for_status
            response.json = lambda: {}
            return response

    http._session = FakeSession()
    with pytest.raises(yahoo.PriceUnavailable):
        http.get_chart('AAPL', interval='5m', period1=1, period2=2,
                       include_prepost=True)
    # Inside the backoff window no network request happens at all.
    calls = []
    http._session.get = lambda *a, **k: calls.append(1)
    with pytest.raises(yahoo.PriceUnavailable, match='backoff'):
        http.get_chart('AAPL', interval='5m', period1=1, period2=2,
                       include_prepost=True)
    assert calls == []
    # After the first window expires the next request is attempted again.
    clock['now'] += 61
    with pytest.raises(Exception):
        http.get_chart('AAPL', interval='5m', period1=1, period2=2,
                       include_prepost=True)
    assert calls == [1]


def test_containment_and_concurrency_bounds():
    """One success, one timeout, one wrong currency: only the success
    returns, and active requests never exceed the semaphore's four."""
    active = {'now': 0, 'peak': 0}
    lock = threading.Lock()

    class MixedHttp:
        def get_chart(self, symbol, **kwargs):
            with lock:
                active['now'] += 1
                active['peak'] = max(active['peak'], active['now'])
            try:
                time.sleep(0.01)
                if symbol == 'SLOW':
                    raise yahoo.PriceUnavailable('timeout')
                if symbol == 'WRONG':
                    return chart_payload(symbol='WRONG', currency='EUR')
                return chart_payload(symbol=symbol)
            finally:
                with lock:
                    active['now'] -= 1

    provider = yahoo.YahooProvider(MixedHttp())
    instruments = [instrument('AAPL')] + [
        instrument(f'ZZ{i}', provider_symbol='SLOW' if i % 2 else 'WRONG')
        for i in range(8)]
    found = provider.quotes_for_instruments(instruments)
    assert set(found) == {'AAPL'}
    assert active['peak'] <= 4


def test_the_concurrency_bound_has_teeth():
    """Broken variant: without the semaphore the same fixture exceeds four
    concurrent requests."""
    active = {'now': 0, 'peak': 0}
    lock = threading.Lock()

    class CountingHttp:
        def get_chart(self, symbol, **kwargs):
            with lock:
                active['now'] += 1
                active['peak'] = max(active['peak'], active['now'])
            try:
                time.sleep(0.01)
                return chart_payload(symbol=symbol)
            finally:
                with lock:
                    active['now'] -= 1

    provider = yahoo.YahooProvider(CountingHttp())
    provider._semaphore = threading.Semaphore(1000)
    provider._max_workers = 1000
    provider.quotes_for_instruments(
        [instrument(f'A{i}', provider_symbol=f'A{i}') for i in range(10)])
    assert active['peak'] > 4
