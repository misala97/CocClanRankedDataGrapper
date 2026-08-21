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
