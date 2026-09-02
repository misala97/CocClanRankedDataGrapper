"""What one account is watching.

The reader's own marks -- never a signal from the tool. Per account, because
a star that lands on someone else's board is noise; idempotent, because a
double-tap must not be an error; shape-checked, because the ticker goes
straight into IN (...) clauses and URLs.
"""
import datetime as dt
import re

import sqlalchemy as sa

from extensions import db
from models import RadarWatch

# Letters, then a class suffix on some listings (BRK.B, RDS-A), never long.
# The same shape the island applies to `?t=`.
TICKER_SHAPE = re.compile(r'^[A-Za-z][A-Za-z0-9.-]{0,9}$')


class BadTicker(ValueError):
    """A ticker that is not shaped like one."""


def normalise(ticker):
    """The ticker uppercased, or BadTicker."""
    # fullmatch, not match: `$` alone forgives a trailing newline, and a
    # ticker that ends in one would ride into IN clauses and client URLs.
    if not ticker or not TICKER_SHAPE.fullmatch(ticker):
        raise BadTicker(ticker)
    return ticker.upper()


def tickers_for(user_id):
    """The account's marks, oldest first -- the order they were made in."""
    rows = (db.session.query(RadarWatch.ticker)
            .filter(RadarWatch.user_id == user_id)
            .order_by(RadarWatch.created_at, RadarWatch.id).all())
    return [ticker for (ticker,) in rows]


def add(user_id, ticker, now=None):
    """Mark a ticker. Returns the account's full list."""
    ticker = normalise(ticker)
    exists = RadarWatch.query.filter_by(user_id=user_id, ticker=ticker).one_or_none()
    if exists is None:
        db.session.add(RadarWatch(user_id=user_id, ticker=ticker,
                                  created_at=now or dt.datetime.utcnow()))
        try:
            db.session.commit()
        except sa.exc.IntegrityError:
            db.session.rollback()
            # Two taps racing past the SELECT above leave the row in place,
            # which is what was asked for. Any other integrity failure (an
            # account that does not exist, say) is a real error and must
            # not hide behind an empty list.
            if RadarWatch.query.filter_by(user_id=user_id, ticker=ticker).one_or_none() is None:
                raise
    return tickers_for(user_id)


def remove(user_id, ticker):
    """Unmark a ticker. Returns the account's full list; removing a ticker
    that was not marked is not an error."""
    ticker = normalise(ticker)
    RadarWatch.query.filter_by(user_id=user_id, ticker=ticker).delete()
    db.session.commit()
    return tickers_for(user_id)
