"""Which venue's closes a panel chart is actually drawn from.

The rule being pinned: the venue that QUOTES a ticker and the venue that has
its HISTORY are different questions. A Nasdaq listing quoted at Tradegate has
three years of dollars and two days of euros, and the chart that reads the
quote's venue draws the two days.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import fx, history
from models import RadarDailyClose, RadarFxRate, RadarInstrument

TODAY = dt.date(2026, 9, 4)
NOW = dt.datetime(2026, 9, 4, 20, 0, 0)
PREFIX = 'HB'


class FakeQuote:
    """Only the four fields resolve_basis reads off a quote view."""

    def __init__(self, market, mic, venue, currency):
        self.market = market
        self.mic = mic
        self.venue = venue
        self.currency = currency


DE_QUOTE = FakeQuote('de', 'XGAT', 'Tradegate BSX', 'EUR')
US_QUOTE = FakeQuote('us', 'XNMS', 'Nasdaq Global Market', 'USD')


@pytest.fixture()
def clean():
    def wipe():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        RadarInstrument.query.filter(
            RadarInstrument.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        RadarFxRate.query.filter_by(source='test-basis').delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def close(ticker, days_back, price, *, market, mic, currency):
    db.session.add(RadarDailyClose(
        ticker=ticker, market=market, mic=mic, currency=currency,
        close_date=TODAY - dt.timedelta(days=days_back),
        close=decimal.Decimal(price), fetched_at=NOW))


def instrument(ticker, market, mic, venue, currency, isin, primary=True):
    db.session.add(RadarInstrument(
        ticker=ticker, market=market, mic=mic, venue=venue,
        provider_symbol=ticker, currency=currency, isin=isin,
        is_primary=primary, mapping_status='mapped', mapped_at=NOW))


def parity_rates():
    fx.record_rates(
        [(TODAY - dt.timedelta(days=n), decimal.Decimal('2.0000'))
         for n in range(0, 40)], NOW, source='test-basis')


def test_native_venue_wins_when_it_has_the_depth(clean):
    ticker = f'{PREFIX}NAT'
    for n in range(1, 11):
        close(ticker, n, '10.00', market='de', mic='XGAT', currency='EUR')
    for n in range(1, 4):
        close(ticker, n, '20.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()
    parity_rates()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.mic == 'XGAT'
    assert basis.converted_from is None
    assert len(basis.closes) == 10


def test_isin_matched_sibling_wins_over_a_two_day_native_stub(clean):
    ticker = f'{PREFIX}SIB'
    for n in range(1, 3):
        close(ticker, n, '10.00', market='de', mic='XGAT', currency='EUR')
    for n in range(1, 21):
        close(ticker, n, '11.00', market='de', mic='XETR', currency='EUR')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'DE000TEST001')
    instrument(ticker, 'de', 'XETR', 'Xetra', 'EUR', 'DE000TEST001',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.mic == 'XETR'
    assert basis.venue == 'Xetra'
    assert basis.currency == 'EUR'
    assert basis.converted_from is None


def test_a_sibling_with_a_different_isin_is_not_a_sibling(clean):
    ticker = f'{PREFIX}ISIN'
    for n in range(1, 21):
        close(ticker, n, '11.00', market='de', mic='XETR', currency='EUR')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'DE000TEST002')
    instrument(ticker, 'de', 'XETR', 'Xetra', 'EUR', 'DE000OTHER99',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.mic != 'XETR'


def test_converted_us_history_wins_when_germany_has_nothing(clean):
    """RZLV's exact shape: a German quote, no Xetra listing, deep US closes."""
    ticker = f'{PREFIX}RZLV'
    for n in range(1, 21):
        close(ticker, n, '10.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'GB00TEST0001')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()
    parity_rates()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.market == 'us'
    assert basis.mic == 'XNMS'
    assert basis.currency == 'EUR'
    assert basis.converted_from == 'USD'
    # Parity rate of 2.0 -- ten dollars is five euros.
    assert basis.closes[0][1] == decimal.Decimal('5.0000')


def test_conversion_is_skipped_without_stored_rates(clean):
    ticker = f'{PREFIX}NOFX'
    for n in range(1, 21):
        close(ticker, n, '10.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'GB00TEST0002')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.closes == ()


def test_a_us_quote_never_converts(clean):
    ticker = f'{PREFIX}USQ'
    for n in range(1, 21):
        close(ticker, n, '10.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()
    parity_rates()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert basis.currency == 'USD'
    assert basis.converted_from is None
    assert basis.closes[0][1] == decimal.Decimal('10.0000')


def test_a_single_close_is_not_a_line(clean):
    ticker = f'{PREFIX}ONE'
    close(ticker, 1, '10.00', market='de', mic='XGAT', currency='EUR')
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis == history.EMPTY_BASIS


def test_nothing_stored_yields_the_empty_basis(clean):
    basis = history.resolve_basis(f'{PREFIX}VOID', DE_QUOTE, 30, TODAY)
    assert basis == history.EMPTY_BASIS
    assert basis.closes == ()
