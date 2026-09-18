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

from dataclasses import dataclass

from features.radar.prices import (CurrencyMismatch, Profile, PriceUnavailable,
                                   Quote, normalize_snapshot)
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


@dataclass(frozen=True)
class Instrument:
    ticker: str = 'BRK.B'
    market: str = 'us'
    venue: str = 'NYSE'
    mic: str = 'XNYS'
    provider_symbol: str = 'BRKB'
    currency: str = 'USD'


def test_currency_mismatch_rejects_provider_snapshot():
    """A non-USD provider price for a US instrument is refused, never
    relabelled as dollars."""
    raw = Quote(
        ticker='BRK.B', market='us', venue='NYSE', mic='XNYS',
        provider_symbol='BRKB', currency='EUR', price=decimal.Decimal('194.20'),
        previous_close=None, regular_close=None, quote_ts=None, volume=None,
        provider_delay='delayed',
    )

    with pytest.raises(CurrencyMismatch):
        normalize_snapshot(Instrument(), raw)


def test_provider_identity_mismatch_rejects_a_relabelled_snapshot():
    raw = Quote(
        ticker='WRONG', market='us', venue='NYSE', mic='XNYS',
        provider_symbol='WRONG', currency='USD', price=decimal.Decimal('194.20'))

    with pytest.raises(ValueError, match='provider symbol'):
        normalize_snapshot(Instrument(), raw)


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


def test_a_finnhub_quote_declares_live_trade_provenance():
    """[A2] Finnhub is the permanent real-time US source; the legacy
    constructor default 'delayed' must not leak through."""
    http = FakeHttp({'/quote': {'c': 123.45, 'pc': 120.0, 'v': 900000,
                                't': 1786000000}})
    quote = finnhub.FinnhubProvider(http).quotes(['AAA'])['AAA']
    assert (quote.source, quote.price_basis, quote.provider_delay) == (
        'finnhub', 'trade', 'live')


def test_a_massive_quote_cannot_exist():
    """[A1] massive_grouped is a daily-close source, never an intraday quote."""
    with pytest.raises(ValueError, match='quote source'):
        Quote(ticker='AAA', price=decimal.Decimal('1'), mic='XNGS',
              source='massive_grouped', price_basis='close')


def test_a_quote_cannot_be_built_without_an_explicit_mic():
    """D8: the constructor used to default to `mic='XNAS'`.

    `XNAS` is Nasdaq's *operating* MIC and no listing resolves to it, so a
    defaulted row was indistinguishable from a legitimately-Nasdaq one while
    belonging to no instrument at all. Whoever builds a quote now has to say
    what venue it came from, even if the honest answer is that they do not
    know.
    """
    with pytest.raises(TypeError):
        Quote(ticker='AAA', price=decimal.Decimal('1'))

    assert Quote(ticker='AAA', price=decimal.Decimal('1'), mic=None).mic is None
    assert Quote(ticker='AAA', price=decimal.Decimal('1'),
                 mic='XNGS').mic == 'XNGS'


def test_a_provider_that_cannot_name_a_venue_says_so_instead_of_guessing():
    """Finnhub's `/quote` answers a price and nothing about the listing, so
    its raw snapshot carries no MIC. `normalize_snapshot` supplies the
    instrument's MIC on the mapped path; the unmapped path has no instrument
    and `record_quotes` refuses the row rather than inventing one."""
    http = FakeHttp({'/quote': {'c': 123.45, 'pc': 120.0, 't': 1786000000}})
    quote = finnhub.FinnhubProvider(http).quotes(['BRKB'])['BRKB']
    assert quote.mic is None

    bound = normalize_snapshot(Instrument(), quote)
    assert bound.mic == Instrument.mic
    assert bound.venue == Instrument.venue


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


def test_malformed_finnhub_numeric_field_is_contained_to_its_symbol():
    class Mixed(FakeHttp):
        def get(self, path, params):
            if params['symbol'] == 'BAD':
                return {'c': 'not-a-number', 'pc': 9, 't': 1786000000}
            return {'c': 10, 'pc': 9, 't': 1786000000}

    quotes = finnhub.FinnhubProvider(Mixed({})).quotes(['BAD', 'GOOD'])

    assert set(quotes) == {'GOOD'}


def test_out_of_range_finnhub_timestamp_is_contained_to_its_symbol():
    class Mixed(FakeHttp):
        def get(self, path, params):
            if params['symbol'] == 'BAD':
                return {'c': 10, 'pc': 9, 't': 10 ** 100}
            return {'c': 10, 'pc': 9, 't': 1786000000}

    quotes = finnhub.FinnhubProvider(Mixed({})).quotes(['BAD', 'GOOD'])

    assert set(quotes) == {'GOOD'}


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


def test_quote_without_a_status_field_is_a_usable_snapshot():
    """Twelve Data's successful /quote shape does not require a status flag."""
    http = FakeHttp({'/quote': {
        'symbol': 'BRKB', 'close': '194.20', 'previous_close': '193.50',
        'currency': 'USD', 'timestamp': 1787313600}})

    quote = twelvedata.TwelveDataProvider(http).quotes(['BRKB'])['BRKB']

    assert quote.price == decimal.Decimal('194.20')
    assert quote.currency == 'USD'


def test_a_quote_request_is_mic_qualified_and_identity_bound():
    http = FakeHttp({'/quote': {
        'symbol': 'BRKB', 'mic_code': 'XNYS', 'close': '194.20',
        'previous_close': '193.50', 'currency': 'USD',
        'timestamp': 1787313600}})

    quotes = twelvedata.TwelveDataProvider(http).quotes_for_instruments(
        [Instrument()])

    assert http.calls == [('/quote', {'symbol': 'BRKB', 'mic_code': 'XNYS'})]
    assert quotes['BRKB'].mic == 'XNYS'
    assert quotes['BRKB'].provider_symbol == 'BRKB'


def test_malformed_twelve_data_optional_number_does_not_abort_the_batch():
    class Mixed(FakeHttp):
        def get(self, path, params):
            if params['symbol'] == 'BAD':
                return {'symbol': 'BAD', 'close': '10',
                        'previous_close': 'not-a-number', 'currency': 'USD'}
            return {'symbol': 'GOOD', 'close': '11',
                    'previous_close': '10', 'currency': 'USD'}

    instruments = [
        Instrument(ticker='BAD', provider_symbol='BAD'),
        Instrument(ticker='GOOD', provider_symbol='GOOD'),
    ]

    quotes = twelvedata.TwelveDataProvider(Mixed({})).quotes_for_instruments(
        instruments)

    assert set(quotes) == {'GOOD'}


def test_out_of_range_twelve_data_timestamp_is_contained_to_its_symbol():
    class Mixed(FakeHttp):
        def get(self, path, params):
            if params['symbol'] == 'BAD':
                return {'symbol': 'BAD', 'close': '10', 'timestamp': 10 ** 100,
                        'currency': 'USD'}
            return {'symbol': 'GOOD', 'close': '11', 'timestamp': 1787313600,
                    'currency': 'USD'}

    instruments = [
        Instrument(ticker='BAD', provider_symbol='BAD'),
        Instrument(ticker='GOOD', provider_symbol='GOOD'),
    ]

    quotes = twelvedata.TwelveDataProvider(Mixed({})).quotes_for_instruments(
        instruments)

    assert set(quotes) == {'GOOD'}


def test_no_provider_offers_a_reference_catalog():
    """The retired mapper's directory readers are gone with it."""
    assert not hasattr(finnhub.FinnhubProvider, 'stock_catalog')
    assert not hasattr(twelvedata.TwelveDataProvider, 'stock_catalog')
    assert not hasattr(finnhub, 'FINNHUB_EXCHANGE_BY_MIC')


def test_the_retired_feed_is_not_an_active_source():
    """Its archived rows keep their spelling in the database; no active
    validator accepts it."""
    from features.radar.prices import (CLOSE_SOURCES, QUOTE_SOURCES,
                                       validate_close_source)

    assert 'deutsche_boerse_delayed' not in QUOTE_SOURCES
    assert 'deutsche_boerse_delayed' not in CLOSE_SOURCES
    with pytest.raises(ValueError, match='unknown quote source'):
        Quote('AAPL', decimal.Decimal('1'), mic='XNGS',
              source='deutsche_boerse_delayed')
    with pytest.raises(ValueError, match='unknown close source'):
        validate_close_source('deutsche_boerse_delayed', 'close', 'split')
