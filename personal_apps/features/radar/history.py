# personal_apps/features/radar/history.py
"""Daily closes: what a ticker's price has been doing, over months.

Divergence measures hours, which is the right question about a stock you
already know and the wrong one the first time you see a ticker. Flat over four
hours while down 80% on the year and flat over four hours having tripled since
June are opposite situations behind an identical score. This is the context
that separates them -- read beside the score, never folded into it.

The provider allows eight requests a minute, so the interesting decision here
is not how to fetch but WHOM to ask about. A ticker with no history at all is
the one the board cannot describe, so it goes first.
"""
import collections
import datetime as dt

from extensions import db
from models import RadarDailyClose

# A full trading year. 252 is the usual count; 260 covers a run of holidays
# without needing a second request.
HISTORY_DAYS = 260

# How old the newest stored close may be before it is worth re-asking.
#
# Two days, not one. Over a weekend the provider has nothing newer than
# Friday, so a one-day rule would mark every ticker stale all weekend and
# spend the entire per-cycle budget re-fetching rows that cannot change --
# starving the tickers with no history at all, which are the only ones the
# board actually cannot draw.
STALE_AFTER_DAYS = 2


def record_closes(ticker, closes, now):
    """Upsert (date, close) pairs for one ticker. Returns rows written.

    Upsert rather than append: providers restate recent bars, and a second
    write for the same day must replace it or every overlapping point would be
    drawn twice.
    """
    if not closes:
        return 0

    existing = {row.close_date: row for row in RadarDailyClose.query.filter(
        RadarDailyClose.ticker == ticker,
        RadarDailyClose.close_date.in_([day for day, _ in closes])).all()}

    for day, close in closes:
        row = existing.get(day)
        if row is None:
            db.session.add(RadarDailyClose(
                ticker=ticker, close_date=day, close=close, fetched_at=now))
        else:
            row.close = close
            row.fetched_at = now

    db.session.commit()
    return len(closes)


def closes_for(tickers, days=HISTORY_DAYS, today=None):
    """{ticker: [(date, close)]} oldest first, for tickers that have any.

    A ticker with nothing stored is ABSENT from the result rather than mapped
    to an empty list. The two mean different things downstream -- absent
    becomes a null payload and draws a dashed "not known" rule, while an empty
    series would draw a flat line and assert a price that held steady.
    """
    if not tickers:
        return {}

    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)

    rows = (db.session.query(RadarDailyClose.ticker,
                             RadarDailyClose.close_date,
                             RadarDailyClose.close)
            .filter(RadarDailyClose.ticker.in_(list(tickers)),
                    RadarDailyClose.close_date >= since,
                    RadarDailyClose.close_date <= today)
            .order_by(RadarDailyClose.close_date.asc()).all())

    series = collections.defaultdict(list)
    for ticker, day, close in rows:
        series[ticker].append((day, close))
    return dict(series)


def tickers_needing_history(candidates, today, stale_after_days=STALE_AFTER_DAYS):
    """Which of `candidates` to spend requests on, most urgent first.

    Missing before stale, each keeping the caller's order -- the caller passes
    them loudest first, and among tickers we cannot draw at all the loudest is
    the one most likely to be looked at next.
    """
    if not candidates:
        return []

    newest = dict(db.session.query(
        RadarDailyClose.ticker, db.func.max(RadarDailyClose.close_date))
        .filter(RadarDailyClose.ticker.in_(list(candidates)))
        .group_by(RadarDailyClose.ticker).all())

    cutoff = today - dt.timedelta(days=stale_after_days)
    missing = [t for t in candidates if t not in newest]
    stale = [t for t in candidates if t in newest and newest[t] < cutoff]
    return missing + stale


def fetch_into_store(provider, tickers, now):
    """Fetch a year of closes for each ticker and store it.

    Returns how many tickers came back with anything. A provider answering
    nothing leaves the stored rows alone: blanking a year of history because
    one call failed would empty the column for that ticker until the next
    cycle, which is worse than showing yesterday's.
    """
    stored = 0
    for ticker in tickers:
        closes = provider.daily_closes(ticker, HISTORY_DAYS)
        if not closes:
            continue
        record_closes(ticker, closes, now)
        stored += 1
    return stored
