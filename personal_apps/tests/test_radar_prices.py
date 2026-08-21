# personal_apps/tests/test_radar_prices.py
"""The provider adapter.

One module knows Finnhub's JSON. Everything else sees Quote and Profile, so
swapping providers is one file -- which matters, because free market data
tiers change terms often and this project has already lost one data source
mid-build.
"""
import datetime as dt
import decimal

import pytest

from features.radar.prices import Profile, PriceUnavailable, Quote
from features.radar.prices import finnhub, twelvedata


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, dict(params)))
        if path not in self.payloads:
            raise PriceUnavailable('404 %s' % path)
        return self.payloads[path]


def test_a_quote_is_normalized():
    http = FakeHttp({'/quote': {'c': 123.45, 'pc': 120.0, 'v': 900000,
                                't': 1786000000}})
    quotes = finnhub.FinnhubProvider(http).quotes(['AAA'])
    quote = quotes['AAA']
    assert isinstance(quote, Quote)
    assert quote.price == decimal.Decimal('123.45')
    assert quote.prev_close == decimal.Decimal('120.0')
    assert quote.volume == 900000
    # Timezone-aware conversion, then dropped to naive UTC -- the convention
    # every datetime in this codebase is stored in. utcfromtimestamp() would
    # read more naturally and is deprecated, which the suite's
    # -W error::DeprecationWarning gate turns into a failure.
    assert quote.quote_ts == dt.datetime.fromtimestamp(
        1786000000, dt.timezone.utc).replace(tzinfo=None, microsecond=0)


def test_prices_arrive_as_decimal_not_float():
    """Float here would quietly poison every forward return downstream."""
    http = FakeHttp({'/quote': {'c': 0.1, 'pc': 0.2, 'v': 1, 't': 1786000000}})
    quote = finnhub.FinnhubProvider(http).quotes(['AAA'])['AAA']
    assert isinstance(quote.price, decimal.Decimal)


def test_a_zero_price_is_not_a_quote():
    """Finnhub returns c=0 for an unknown symbol rather than an error. Storing
    that as a price would read as a 100% crash."""
    http = FakeHttp({'/quote': {'c': 0, 'pc': 0, 'v': 0, 't': 0}})
    assert finnhub.FinnhubProvider(http).quotes(['AAA']) == {}


def test_one_bad_symbol_does_not_lose_the_others():
    class Partial(FakeHttp):
        def get(self, path, params):
            if params.get('symbol') == 'BAD':
                raise PriceUnavailable('500')
            return {'c': 10.0, 'pc': 9.0, 'v': 5, 't': 1786000000}

    quotes = finnhub.FinnhubProvider(Partial({})).quotes(['AAA', 'BAD', 'BBB'])
    assert set(quotes) == {'AAA', 'BBB'}


def test_a_profile_is_normalized():
    http = FakeHttp({'/stock/profile2': {
        'marketCapitalization': 3500.5, 'ipo': '2004-08-19', 'exchange': 'NASDAQ'}})
    profile = finnhub.FinnhubProvider(http).profile('AAA')
    assert isinstance(profile, Profile)
    # Finnhub reports market cap in MILLIONS. Storing it raw would put every
    # mega cap in the micro segment.
    assert profile.market_cap == decimal.Decimal('3500500000')
    assert profile.ipo_date == dt.date(2004, 8, 19)


def test_a_profile_without_a_market_cap_is_still_returned():
    """Newly listed and OTC names often have no cap. They belong in the Unknown
    segment, which is a first-class tab, not a discard pile."""
    http = FakeHttp({'/stock/profile2': {'exchange': 'OTC'}})
    profile = finnhub.FinnhubProvider(http).profile('AAA')
    assert profile is not None
    assert profile.market_cap is None


def test_an_empty_profile_is_none():
    http = FakeHttp({'/stock/profile2': {}})
    assert finnhub.FinnhubProvider(http).profile('AAA') is None


def test_daily_closes_come_back_oldest_first():
    """From Twelve Data, not Finnhub: /stock/candle is 403 on Finnhub free,
    measured. Volatility is the whole reason daily closes exist here, and
    without it divergence cannot rank anything."""
    http = FakeHttp({'/time_series': {
        'status': 'ok',
        'values': [
            {'datetime': '2026-08-20', 'close': '12.0'},
            {'datetime': '2026-08-19', 'close': '11.0'},
            {'datetime': '2026-08-18', 'close': '10.0'},
        ]}})
    closes = twelvedata.TwelveDataProvider(http).daily_closes('AAA', days=3)
    # Twelve Data returns newest first; volatility wants chronological order.
    assert [c for _, c in closes] == [decimal.Decimal('10.0'),
                                      decimal.Decimal('11.0'),
                                      decimal.Decimal('12.0')]
    assert closes[0][0] < closes[-1][0]


def test_an_error_status_is_empty_not_an_exception():
    """Twelve Data reports an unknown symbol as status='error' with a 200."""
    http = FakeHttp({'/time_series': {'status': 'error',
                                      'message': 'symbol not found'}})
    assert twelvedata.TwelveDataProvider(http).daily_closes('AAA', days=30) == []


def test_a_rate_limited_response_is_empty_not_a_crash():
    """800 requests a day is ample for weekly volatility, but a burst can
    still trip it, and one tripped call must not take down the job."""
    http = FakeHttp({'/time_series': {'status': 'error', 'code': 429}})
    assert twelvedata.TwelveDataProvider(http).daily_closes('AAA', days=30) == []
