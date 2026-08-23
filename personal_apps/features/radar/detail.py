# personal_apps/features/radar/detail.py
"""Everything one ticker's panel needs.

Separate from board.py because it answers a different question. The board
answers "which of these deserves my attention" across many tickers; this
answers "is this real" about one, and the two want opposite shapes -- the
board needs every row small, this needs one ticker deep.

That split is also why the panel has its own endpoint. Three years is ~780
closes, so carrying the chart per row would have a twenty-row board shipping
sixteen thousand numbers in order to draw twenty sparklines.
"""
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource

# Calendar days per span, not trading days: the arrays are indexed by calendar
# day so price and chatter stay aligned through weekends and holidays. A year
# holds ~252 trading days and 365 calendar ones, and indexing each by its own
# position would drift them apart by over a hundred days.
SPAN_DAYS = {'1M': 30, '6M': 182, '1Y': 365, '3Y': 1095}

DEFAULT_SPAN = '1Y'


class UnknownTicker(Exception):
    """No universe row for this symbol. Not a 500 -- a URL can name anything."""


@dataclasses.dataclass
class Chart:
    """Price and chatter over the same calendar days, sharing `start`.

    `closes[i]` is None where the market did not trade -- weekends, holidays.
    `chatter[i]` is None where we were not yet watching. Different absences and
    drawn differently: the price line spans its gaps because the price did not
    stop existing on a Saturday, while the chatter lane simply stops, because
    a day nobody observed is not a day with no mentions.
    """
    start: dt.date
    closes: list
    chatter: list
    watched_from: dt.date | None


def daily_counts(tickers, sources, start, now):
    """Pooled mention count per (ticker, calendar day).

    From buckets, which are retained forever -- unlike posts, which prune at
    30 days. That is what lets the chart's long spans fill in over time with
    no new collection.
    """
    if not tickers:
        return {}

    rows = (db.session.query(RadarBucketSource.ticker,
                             sa.func.date(RadarBucketSource.bucket_start),
                             sa.func.sum(RadarBucketSource.mention_count))
            .filter(RadarBucketSource.ticker.in_(list(tickers)),
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now)
            .group_by(RadarBucketSource.ticker,
                      sa.func.date(RadarBucketSource.bucket_start)).all())

    totals = {}
    for ticker, day, count in rows:
        # MySQL returns DATE() as a date object; MariaDB has been seen to
        # return a string. Normalise rather than trusting the driver.
        if isinstance(day, str):
            day = dt.date.fromisoformat(day)
        totals[(ticker, day)] = int(count or 0)
    return totals


def first_watched_day(sources, start, now):
    """Earliest calendar day any bucket exists for. Before it, chatter is
    unknown rather than zero."""
    earliest = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
                .filter(RadarBucketSource.source.in_(list(sources)),
                        RadarBucketSource.bucket_start >= start).scalar())
    return earliest.date() if earliest else None


def chart_for(ticker, start, days, closes_by_day, counts, watched_from):
    """One Chart, both arrays indexed by calendar day from `start`."""
    closes, chatter = [], []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        closes.append(closes_by_day.get(day))
        if watched_from is None or day < watched_from:
            chatter.append(None)
        else:
            chatter.append(counts.get((ticker, day), 0))
    return Chart(start=start, closes=closes, chatter=chatter,
                 watched_from=watched_from)
