"""Which venue's closes a panel chart is actually drawn from.

The rule being pinned: the venue that QUOTES a ticker and the venue that has
its HISTORY are different questions. A Nasdaq listing whose exact-ISIN NYSE
sibling holds the deeper series draws the sibling's dollars, and says so.
Nothing is ever converted: archived non-US closes stay in the table and are
never a candidate, even beside stored reference rates.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import history
from models import RadarDailyClose, RadarFxRate, RadarInstrument

# Deliberately predates every real stored series, so these fixtures can never
# overwrite or delete the local development store's real rows.
TODAY = dt.date(1990, 1, 7)
NOW = dt.datetime(1990, 1, 7, 20, 0, 0)
PREFIX = 'HB'
OWNED_TICKERS = frozenset({
    'HBARC', 'HBBND', 'HBISIN', 'HBNAT', 'HBONE', 'HBSIB', 'HBUSQ', 'HBVOID',
})


class FakeQuote:
    """Only the four fields resolve_basis reads off a quote view."""

    def __init__(self, market, mic, venue, currency):
        self.market = market
        self.mic = mic
        self.venue = venue
        self.currency = currency


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


def close(ticker, days_back, price, *, market='us', mic='XNMS',
          currency='USD'):
    db.session.add(RadarDailyClose(
        ticker=ticker, market=market, mic=mic, currency=currency,
        close_date=TODAY - dt.timedelta(days=days_back),
        close=decimal.Decimal(price), fetched_at=NOW))


def instrument(ticker, market, mic, venue, currency, isin, primary=True):
    db.session.add(RadarInstrument(
        ticker=ticker, market=market, mic=mic, venue=venue,
        provider_symbol=ticker, currency=currency, isin=isin,
        is_primary=primary, mapping_status='mapped', mapped_at=NOW))


def archived(ticker, isin, days=20, price='5.00'):
    """An archived non-US listing, deeper than any US series here, and the
    stored reference rates the retired conversion would have used."""
    instrument(ticker, 'de', 'XETR', 'Xetra', 'EUR', isin)
    for n in range(0, days):
        close(ticker, n, price, market='de', mic='XETR', currency='EUR')
    for n in range(0, 40):
        db.session.add(RadarFxRate(
            rate_date=TODAY - dt.timedelta(days=n), base='EUR', quote='USD',
            rate=decimal.Decimal('2.0'), source='test-basis', fetched_at=NOW))


def test_native_venue_wins_when_it_has_the_depth(clean):
    ticker = f'{PREFIX}NAT'
    for n in range(1, 11):
        close(ticker, n, '10.00')
    for n in range(1, 4):
        close(ticker, n, '20.00', mic='XNYS')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD',
               'US000TEST001')
    instrument(ticker, 'us', 'XNYS', 'NYSE', 'USD', 'US000TEST001',
               primary=False)
    archived(ticker, 'US000TEST001')
    db.session.commit()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert (basis.market, basis.mic, basis.currency) == ('us', 'XNMS', 'USD')
    assert not hasattr(basis, 'converted_from')
    assert len(basis.closes) == 10


def test_isin_matched_sibling_wins_over_a_two_day_native_stub(clean):
    ticker = f'{PREFIX}SIB'
    for n in range(1, 3):
        close(ticker, n, '10.00')
    for n in range(1, 21):
        close(ticker, n, '11.00', mic='XNYS')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD',
               'US000TEST002')
    instrument(ticker, 'us', 'XNYS', 'NYSE', 'USD', 'US000TEST002',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert basis.mic == 'XNYS'
    assert basis.venue == 'NYSE'
    assert basis.currency == 'USD'


def test_basis_counts_only_closes_visible_in_the_requested_span(clean):
    ticker = f'{PREFIX}BND'
    # closes_for includes TODAY-days, but a `days`-wide chart begins one day
    # later. The invisible native row must not defeat two visible siblings.
    close(ticker, 3, '10.00')
    close(ticker, 1, '10.00')
    close(ticker, 2, '11.00', mic='XNYS')
    close(ticker, 1, '12.00', mic='XNYS')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD',
               'US000TESTBND')
    instrument(ticker, 'us', 'XNYS', 'NYSE', 'USD', 'US000TESTBND',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, US_QUOTE, 3, TODAY)

    assert basis.mic == 'XNYS'
    assert [day for day, _ in basis.closes] == [
        TODAY - dt.timedelta(days=2), TODAY - dt.timedelta(days=1)]


def test_a_sibling_with_a_different_isin_is_not_a_sibling(clean):
    ticker = f'{PREFIX}ISIN'
    for n in range(1, 21):
        close(ticker, n, '11.00', mic='XNYS')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD',
               'US000TEST003')
    instrument(ticker, 'us', 'XNYS', 'NYSE', 'USD', 'US000OTHER99',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert basis.mic != 'XNYS'


def test_an_archived_listing_is_never_a_basis(clean):
    """RZLV's old shape, reversed: deep archived closes, a matching ISIN and
    stored reference rates -- and no US series. The answer is no line."""
    ticker = f'{PREFIX}ARC'
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD',
               'US000TEST004')
    archived(ticker, 'US000TEST004')
    db.session.commit()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert basis == history.EMPTY_BASIS


def test_a_us_quote_never_converts(clean):
    ticker = f'{PREFIX}USQ'
    for n in range(1, 21):
        close(ticker, n, '10.00')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    archived(ticker, None, price='99.00')
    db.session.commit()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert basis.currency == 'USD'
    assert basis.closes[0][1] == decimal.Decimal('10.0000')
    assert all(price == decimal.Decimal('10.0000')
               for _, price in basis.closes)


def test_a_non_us_quote_has_no_basis_at_all(clean):
    archived_quote = FakeQuote('de', 'XGAT', 'Tradegate BSX', 'EUR')
    with pytest.raises(ValueError, match='unknown market'):
        history.resolve_basis(f'{PREFIX}VOID', archived_quote, 30, TODAY)


def test_a_single_close_is_not_a_line(clean):
    ticker = f'{PREFIX}ONE'
    close(ticker, 1, '10.00')
    db.session.commit()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert basis == history.EMPTY_BASIS


def test_nothing_stored_yields_the_empty_basis(clean):
    basis = history.resolve_basis(f'{PREFIX}VOID', US_QUOTE, 30, TODAY)
    assert basis == history.EMPTY_BASIS
    assert basis.closes == ()
