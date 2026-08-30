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
from models import RadarBucketSource, RadarQuote

from .config import expand_sources_for_history
from . import quotes as quotes_mod

# Calendar days per span, not trading days: the arrays are indexed by calendar
# day so price and chatter stay aligned through weekends and holidays. A year
# holds ~252 trading days and 365 calendar ones, and indexing each by its own
# position would drift them apart by over a hundred days.
SPAN_DAYS = {'1M': 30, '6M': 182, '1Y': 365, '3Y': 1095}

# Spans measured in minutes rather than days, as (slots, minutes_per_slot).
#
# These CANNOT be entries in SPAN_DAYS. That chart is indexed by calendar day,
# so a one-day span is a single point and a week is seven -- a chart with
# nothing in it. They need their own granularity and their own price source:
# radar_daily_closes holds one row per trading day, so the only intraday price
# this system stores is radar_quotes.
#
# 1D uses 15-minute slots because that is exactly the bucket grain. Anything
# coarser re-aggregates what the rollup already decided; anything finer
# invents resolution the chatter does not have. 1W uses an hour, pooling four
# buckets per slot.
INTRADAY_SPANS = {'1D': (96, 15), '1W': (168, 60)}

DEFAULT_SPAN = '1Y'


def is_intraday(span):
    return span in INTRADAY_SPANS


def known_span(span):
    return span in SPAN_DAYS or span in INTRADAY_SPANS


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
    # How wide one slot is. 1440 for the day-indexed spans, minutes for the
    # intraday ones. The renderer draws evenly spaced slots and cannot tell
    # minutes from days on its own -- without this it labels a 24-hour chart
    # with month names.
    step_minutes: int = 1440


def daily_counts(tickers, sources, start, now):
    """Pooled mention count per (ticker, calendar day).

    From buckets, which are retained forever -- unlike posts, which prune at
    30 days. That is what lets the chart's long spans fill in over time with
    no new collection. Which is exactly why this expands FOR HISTORY: a 1Y
    span reaches back well past the 2026-08-26 subreddit split, and Reddit's
    contribution before it is stored under the bare name `reddit`.
    """
    if not tickers:
        return {}

    sources = expand_sources_for_history(sources)
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
    sources = expand_sources_for_history(sources)
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


def _slot_index(when, start, step_minutes, slots):
    """Which slot an instant falls in, or None if outside the window."""
    offset = (when - start).total_seconds() / 60.0
    if offset < 0:
        return None
    index = int(offset // step_minutes)
    return index if index < slots else None


def intraday_prices(ticker, start, now, step_minutes, slots, *, market='us',
                    mic=None):
    """Last quoted price per slot, None where nothing was quoted.

    The previous price is NOT carried forward. Doing so would draw a flat line
    through a stretch nobody priced, which is the same lie as a zero for
    chatter nobody observed -- and the renderer already spans price gaps, so
    it only needs to be told they are gaps.

    Quotes exist only for the tickers that have been loud enough to be polled
    (run_radar_ingest.QUOTE_LIMIT) and only as far back as
    config.QUOTE_RETENTION_DAYS. A ticker that has never ranked has no
    intraday price at all, which is a real absence and drawn as one.
    """
    rows = (db.session.query(RadarQuote.fetched_at, RadarQuote.price)
            .filter(*quotes_mod._quote_matches(ticker, market, mic),
                    RadarQuote.fetched_at >= start,
                    RadarQuote.fetched_at < now)
            .order_by(RadarQuote.fetched_at).all())

    prices = [None] * slots
    for fetched_at, price in rows:
        index = _slot_index(fetched_at, start, step_minutes, slots)
        if index is not None:
            # Ordered ascending, so the last write per slot is the slot's
            # closing price -- the same convention a daily close follows.
            prices[index] = float(price)
    return prices


def intraday_counts(ticker, sources, start, now, step_minutes, slots):
    """Mentions per slot, and the first slot anything was observed in.

    Returns (counts, first_seen_index). Buckets are 15 minutes; a 1W slot is
    an hour, so four of them pool into one and must add rather than overwrite.
    """
    sources = expand_sources_for_history(sources)
    rows = (db.session.query(RadarBucketSource.bucket_start,
                             sa.func.sum(RadarBucketSource.mention_count))
            .filter(RadarBucketSource.ticker == ticker,
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now)
            .group_by(RadarBucketSource.bucket_start).all())

    counts = [0] * slots
    seen = None
    for bucket_start, total in rows:
        index = _slot_index(bucket_start, start, step_minutes, slots)
        if index is None:
            continue
        counts[index] += int(total or 0)
        seen = index if seen is None else min(seen, index)
    return counts, seen


def watched_slots(sources, start, now, step_minutes, slots):
    """Slots in which any bucket was written for the selected sources.

    This is the same coverage proxy board._covered_hours uses. A quiet source
    is therefore zero only in a slot we observed; an interior ingest outage is
    unknown rather than a fabricated run of quiet chatter.
    """
    sources = expand_sources_for_history(sources)
    rows = (db.session.query(RadarBucketSource.bucket_start)
            .filter(RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now,
                    RadarBucketSource.status.in_(('ok', 'truncated')))
            .distinct().all())
    covered = set()
    for (bucket_start,) in rows:
        index = _slot_index(bucket_start, start, step_minutes, slots)
        if index is not None:
            covered.add(index)
    return covered


def intraday_chart_for(ticker, sources, now, span, *, market='us', mic=None):
    """One Chart over slots of minutes rather than calendar days.

    Same array shape as the daily chart on purpose: the renderer draws evenly
    spaced slots and does not need to know what a slot means, beyond
    `step_minutes` for its axis labels.
    """
    slots, step_minutes = INTRADAY_SPANS[span]
    start = now - dt.timedelta(minutes=slots * step_minutes)

    closes = intraday_prices(ticker, start, now, step_minutes, slots,
                             market=market, mic=mic)
    counts, _seen = intraday_counts(ticker, sources, start, now,
                                    step_minutes, slots)
    covered = watched_slots(sources, start, now, step_minutes, slots)

    chatter = []
    for index in range(slots):
        chatter.append(counts[index] if index in covered else None)

    first_watched = min(covered) if covered else None

    return Chart(start=start, closes=closes, chatter=chatter,
                 watched_from=(start + dt.timedelta(
                     minutes=first_watched * step_minutes)
                               if first_watched is not None else None),
                 step_minutes=step_minutes)
