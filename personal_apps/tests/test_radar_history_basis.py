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

# Deliberately predates the ECB's 1999 series, so these EUR/USD fixtures can
# never overwrite or delete the local development store's real rows.
TODAY = dt.date(1990, 1, 7)
NOW = dt.datetime(1990, 1, 7, 20, 0, 0)
PREFIX = 'HB'
OWNED_TICKERS = frozenset({
    'HBBND', 'HBEDGE', 'HBISIN', 'HBNAT', 'HBNOFX', 'HBONE', 'HBRZLV', 'HBSIB',
    'HBUSQ', 'HBVOID',
})


class FakeQuote:
    """Only the four fields resolve_basis reads off a quote view."""

    def __init__(self, market, mic, venue, currency):
        self.market = market
        self.mic = mic
        self.venue = venue
        self.currency = currency


DE_QUOTE = FakeQuote('de', 'XGAT', 'Tradegate BSX', 'EUR')
US_QUOTE = FakeQuote('us', 'XNMS', 'Nasdaq Global Market', 'USD')


def _wipe_owned_rows():
    RadarDailyClose.query.filter(
        RadarDailyClose.ticker.in_(OWNED_TICKERS)).delete(
            synchronize_session=False)
    RadarInstrument.query.filter(
        RadarInstrument.ticker.in_(OWNED_TICKERS)).delete(
            synchronize_session=False)
    RadarFxRate.query.filter_by(source='test-basis').delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def clean():

    with flask_app.app_context():
        _wipe_owned_rows()
        yield
        _wipe_owned_rows()


def test_cleanup_preserves_a_non_test_hb_identity():
    """Exact ownership must survive future additions of real HB* symbols."""
    ticker = 'HB!SAFEFIX'
    with flask_app.app_context():
        assert RadarInstrument.query.filter_by(ticker=ticker).count() == 0
        assert RadarDailyClose.query.filter_by(ticker=ticker).count() == 0
        db.session.add(RadarInstrument(
            ticker=ticker, market='us', mic='XNMS',
            venue='Nasdaq Global Market', provider_symbol=ticker,
            currency='USD', is_primary=True, mapping_status='mapped',
            mapped_at=NOW))
        db.session.add(RadarDailyClose(
            ticker=ticker, market='us', mic='XNMS', currency='USD',
            close_date=TODAY, close=decimal.Decimal('10.00'),
            fetched_at=NOW))
        db.session.commit()
        try:
            _wipe_owned_rows()

            assert RadarInstrument.query.filter_by(ticker=ticker).count() == 1
            assert RadarDailyClose.query.filter_by(ticker=ticker).count() == 1
        finally:
            RadarDailyClose.query.filter_by(ticker=ticker).delete()
            RadarInstrument.query.filter_by(ticker=ticker).delete()
            db.session.commit()


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


def test_basis_counts_only_closes_visible_in_the_requested_span(clean):
    ticker = f'{PREFIX}BND'
    # closes_for includes TODAY-days, but a `days`-wide chart begins one day
    # later. The invisible native row must not defeat two visible siblings.
    close(ticker, 3, '10.00', market='de', mic='XGAT', currency='EUR')
    close(ticker, 1, '10.00', market='de', mic='XGAT', currency='EUR')
    close(ticker, 2, '11.00', market='de', mic='XETR', currency='EUR')
    close(ticker, 1, '12.00', market='de', mic='XETR', currency='EUR')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'DE000TESTBND')
    instrument(ticker, 'de', 'XETR', 'Xetra', 'EUR', 'DE000TESTBND',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 3, TODAY)

    assert basis.mic == 'XETR'
    assert [day for day, _ in basis.closes] == [
        TODAY - dt.timedelta(days=2), TODAY - dt.timedelta(days=1)]


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


def test_conversion_loads_the_rate_before_a_non_publication_day(clean):
    """A Saturday close can use Friday's rate at the query-window edge."""
    ticker = f'{PREFIX}EDGE'
    for day in (dt.date(1990, 1, 6), dt.date(1990, 1, 7)):
        db.session.add(RadarDailyClose(
            ticker=ticker, market='us', mic='XNMS', currency='USD',
            close_date=day, close=decimal.Decimal('10.00'), fetched_at=NOW))
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR',
               'GB00TEST0003')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    fx.record_rates([(dt.date(1990, 1, 5), decimal.Decimal('2.0000'))],
                    NOW, source='test-basis')
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.converted_from == 'USD'
    assert basis.closes == (
        (dt.date(1990, 1, 6), decimal.Decimal('5.0000')),
        (dt.date(1990, 1, 7), decimal.Decimal('5.0000')),
    )


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
