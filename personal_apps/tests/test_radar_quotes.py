# personal_apps/tests/test_radar_quotes.py
"""Quote storage.

Snapshots rather than a single current price: no-print detection compares
consecutive polls, so the previous one has to still be there to compare
against.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from models import RadarQuote, TickerUniverse

NOW = dt.datetime(2026, 8, 21, 14, 0, 0)


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        RadarQuote.query.filter(RadarQuote.ticker.like('QQ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarQuote.query.filter(RadarQuote.ticker.like('QQ%')).delete(
            synchronize_session=False)
        db.session.commit()


def add(when, price, volume=1000, ticker='QQA', quote_ts=None):
    db.session.add(RadarQuote(
        ticker=ticker, fetched_at=when,
        quote_ts=quote_ts or when, price=decimal.Decimal(str(price)),
        prev_close=decimal.Decimal('100.000000'), volume=volume))


def test_a_quote_round_trips_exactly(ctx):
    """DECIMAL, not float. Return arithmetic compounds, and the history log is
    the last place drift belongs."""
    add(NOW, '123.456789')
    db.session.commit()
    stored = RadarQuote.query.filter_by(ticker='QQA').one()
    assert stored.price == decimal.Decimal('123.456789')


def test_consecutive_snapshots_are_both_kept(ctx):
    """No-print detection compares one poll against the last, so the last one
    has to still exist."""
    add(NOW, '100.0')
    add(NOW + dt.timedelta(minutes=2), '101.0')
    db.session.commit()
    assert RadarQuote.query.filter_by(ticker='QQA').count() == 2


def test_the_same_instant_twice_is_rejected(ctx):
    add(NOW, '100.0')
    db.session.commit()
    add(NOW, '999.0')
    import sqlalchemy as sa
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_universe_carries_the_profile_fields(ctx):
    """Segments need market cap; the earnings slice needs the date. Both come
    from the same profile call, refreshed weekly."""
    for field in ('market_cap', 'ipo_date', 'next_earnings_date',
                  'profile_refreshed_at'):
        assert hasattr(TickerUniverse, field)


def test_market_cap_holds_a_large_number(ctx):
    """Mega caps are into the trillions; an INTEGER column would overflow."""
    row = TickerUniverse(symbol='QQBIG', name='Huge Corp', exchange='NASDAQ',
                         first_seen=NOW,
                         market_cap=decimal.Decimal('3500000000000'))
    db.session.add(row)
    db.session.commit()
    db.session.expire(row)
    assert row.market_cap == decimal.Decimal('3500000000000')
    db.session.delete(row)
    db.session.commit()


from features.radar import quotes as quotes_mod


def test_a_moving_tape_is_ok(ctx):
    add(NOW, '100.0', volume=1000, quote_ts=NOW)
    add(NOW + dt.timedelta(minutes=2), '101.0', volume=1200,
        quote_ts=NOW + dt.timedelta(minutes=2))
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=3)) == 'ok'


def test_an_unchanged_tape_is_stale(ctx):
    """A halted stock keeps its last price while mentions explode BECAUSE it
    halted -- maximum divergence produced entirely by an artifact. The same
    signature comes from a stock too illiquid to trade, which is why the mark
    says NO PRINT rather than HALT: the data cannot tell them apart, and both
    are untradeable."""
    frozen = NOW - dt.timedelta(minutes=5)
    for step in range(3):
        add(NOW + dt.timedelta(minutes=2 * step), '100.0', volume=5000,
            quote_ts=frozen)
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=5)) == 'stale'


def test_one_unchanged_poll_is_not_yet_stale(ctx):
    """Two identical polls could be one slow second. Three is a pattern."""
    frozen = NOW - dt.timedelta(minutes=5)
    add(NOW, '100.0', volume=5000, quote_ts=frozen)
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=1)) != 'stale'


def test_volume_moving_while_the_stamp_sticks_is_still_ok(ctx):
    """Both have to be frozen. A stale timestamp with rising volume is a
    provider quirk, not a stopped tape."""
    frozen = NOW - dt.timedelta(minutes=5)
    for step in range(3):
        add(NOW + dt.timedelta(minutes=2 * step), '100.0',
            volume=5000 + step, quote_ts=frozen)
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=5)) == 'ok'


def test_no_quotes_at_all_is_unknown_not_stale(ctx):
    """Never quoted is a different fact from quoted and frozen, and only one
    of them is evidence about the stock."""
    assert quotes_mod.price_status('QQNONE', NOW) == 'unknown'


def test_daily_sigma_of_a_flat_series_is_zero(ctx):
    closes = [(dt.date(2026, 7, day), decimal.Decimal('100')) for day in range(1, 20)]
    assert quotes_mod.daily_sigma(closes) == pytest.approx(0.0)


def test_daily_sigma_grows_with_volatility(ctx):
    calm = [(dt.date(2026, 7, d), decimal.Decimal(100 + (d % 2)))
            for d in range(1, 25)]
    wild = [(dt.date(2026, 7, d), decimal.Decimal(100 + 20 * (d % 2)))
            for d in range(1, 25)]
    assert quotes_mod.daily_sigma(wild) > quotes_mod.daily_sigma(calm) * 5


def test_daily_sigma_needs_enough_history(ctx):
    assert quotes_mod.daily_sigma([]) is None
    assert quotes_mod.daily_sigma(
        [(dt.date(2026, 7, 1), decimal.Decimal('100'))]) is None


def test_move_since_measures_against_the_oldest_quote_in_the_window(ctx):
    add(NOW - dt.timedelta(hours=2), '100.0')
    add(NOW - dt.timedelta(minutes=30), '104.0')
    add(NOW, '110.0')
    db.session.commit()
    move = quotes_mod.move_since('QQA', hours=1, now=NOW + dt.timedelta(minutes=1))
    # From 104 to 110 is roughly +5.8%; the two-hour-old quote is out of window.
    assert 0.05 < float(move) < 0.065


def test_move_since_is_none_without_two_quotes(ctx):
    add(NOW, '100.0')
    db.session.commit()
    assert quotes_mod.move_since('QQA', hours=1, now=NOW) is None
