# personal_apps/features/radar/board.py
"""Everything one page load of the board needs, assembled in one place.

`leaderboard` answers "which tickers rank, and why". That is the ranking, and
it is deliberately not the page: the surface also has to show the SHAPE of each
spike over time, whether it is building or fading, and how one-sided the talk
is. Those are presentation questions, so they live here rather than being
bolted onto the ranking module.

Three things this module is careful about, all of them the same rule wearing
different clothes -- an absence is not a zero:

* An hour with no bucket row for a ticker is a zero only if ingest was alive
  that hour. There is no per-hour "ingest ran" record, so aliveness is inferred
  from whether ANY ticker has a bucket in that hour. Where nothing does, the
  point is null and the sparkline breaks rather than drawing a floor that was
  never measured.
* Lexicon sentiment scores 0.0 both for "balanced" and for "no lexicon word
  matched", and in practice the second dominates. A single "% bullish" computed
  over that is mostly noise wearing a percentage sign, so the split is returned
  as three real counts and the surface draws all three.
* The z triplet is computed from summed components, never averaged. A mean of
  z-scores is not a z-score (spec 6.2).
"""
import collections
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource, RadarMention, RadarPost, RadarQuote

from . import history, leaderboard, market_calendar
from .config import VARIANCE_FLOOR

# The windows the triplet reports, shortest first. Fixed rather than derived
# from the selected window: the point of the triplet is that all three are
# always visible together, so "building" and "fading" can be told apart at a
# glance instead of by switching the window control and remembering.
TRIPLET_HOURS = (1, 4, 24)

# How much history the sparkline and the lead charts draw.
SERIES_HOURS = 24

# How many rows get the full treatment at the top of the page.
LEAD_COUNT = 3

# One calendar year -- the chart's widest span.
CHART_DAYS = 365


@dataclasses.dataclass
class Point:
    """One hour of the chatter series. `count` is None when unmeasured."""
    hour: dt.datetime
    count: int | None


@dataclasses.dataclass
class Chart:
    """Price and chatter over the same calendar days.

    Both arrays are CHART_DAYS long and share `start`, so index i is the same
    date in each. That alignment is why this is one structure rather than two:
    a year holds ~252 trading days and 365 calendar days, and positioning each
    by its own index would drift them apart by over a hundred days.

    `closes[i]` is None where the market did not trade -- weekends, holidays.
    `chatter[i]` is None where we were not yet watching. Different absences,
    drawn differently: the price line spans its gaps, the chatter bars do not.
    """
    start: dt.date
    closes: list
    chatter: list


@dataclasses.dataclass
class Tone:
    """How one-sided the talk was, as counts rather than a percentage.

    `neutral` is not padding. It is every mention whose text contained no
    lexicon word at all, which is most of them, and hiding it would turn a
    handful of scored posts into a confident-looking sentiment reading.
    """
    bullish: int
    neutral: int
    bearish: int

    @property
    def scored(self):
        return self.bullish + self.bearish


@dataclasses.dataclass
class BoardRow:
    """A ranked row plus what the surface needs to draw it."""
    rank: leaderboard.Row
    series: list          # list[Point], oldest first
    triplet: dict         # hours -> z or None
    tone: Tone
    price_series: list    # list[(datetime, Decimal)], only for leads
    # Price and chatter over one calendar year, aligned. None when the ticker
    # has no stored closes at all.
    chart: object


@dataclasses.dataclass
class Board:
    generated_at: dt.datetime
    sources: list
    segment: str | None
    window_hours: int
    segment_counts: dict
    rows: list
    # 'premarket' | 'regular' | 'afterhours' | 'closed'. The surface needs it
    # because it changes what the ranking MEANS: with the exchange shut there
    # is no price movement to diverge from, so the board ranks on chatter
    # alone and has to say so rather than presenting the same column heading.
    session: str


def _hour_floor(when):
    return when.replace(minute=0, second=0, microsecond=0)


def _covered_hours(sources, since, now):
    """Hours in which any bucket at all was written for these sources.

    The proxy for "ingest was alive". It is a proxy and not a record: a genuine
    board-wide silence reads the same as a stopped daemon. Both resolve to
    "not measured", which is the honest half of the ambiguity -- the dishonest
    half would be drawing a zero.
    """
    rows = (db.session.query(RadarBucketSource.bucket_start)
            .filter(RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.bucket_start < now,
                    RadarBucketSource.status.in_(('ok', 'truncated')))
            .distinct().all())
    return {_hour_floor(start) for (start,) in rows}


def _hourly_counts(tickers, sources, since, now):
    """Pooled mention count per (ticker, hour)."""
    if not tickers:
        return {}

    rows = (db.session.query(RadarBucketSource.ticker,
                             RadarBucketSource.bucket_start,
                             RadarBucketSource.mention_count)
            .filter(RadarBucketSource.ticker.in_(list(tickers)),
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.bucket_start < now)
            .all())

    totals = collections.defaultdict(int)
    for ticker, start, count in rows:
        totals[(ticker, _hour_floor(start))] += count
    return totals


def _series_for(ticker, totals, covered, since, now):
    """One point per hour across the window, oldest first."""
    points = []
    hour = _hour_floor(since)
    end = _hour_floor(now)
    while hour <= end:
        if hour in covered:
            points.append(Point(hour=hour, count=totals.get((ticker, hour), 0)))
        else:
            points.append(Point(hour=hour, count=None))
        hour += dt.timedelta(hours=1)
    return points


def _triplets(tickers, sources, now):
    """mention_z at each triplet window, per ticker.

    One query over the longest window, sliced in Python. Three queries would
    read the same rows three times, and the longest window contains the other
    two by construction.
    """
    if not tickers:
        return {}

    longest = max(TRIPLET_HOURS)
    rows = (db.session.query(RadarBucketSource.ticker,
                             RadarBucketSource.bucket_start,
                             RadarBucketSource.mention_count,
                             RadarBucketSource.expected,
                             RadarBucketSource.variance)
            .filter(RadarBucketSource.ticker.in_(list(tickers)),
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= now - dt.timedelta(hours=longest),
                    RadarBucketSource.bucket_start < now,
                    RadarBucketSource.mention_z.isnot(None))
            .all())

    per_ticker = collections.defaultdict(list)
    for ticker, start, count, expected, variance in rows:
        per_ticker[ticker].append((start, count, expected or 0.0, variance or 0.0))

    out = {}
    for ticker, entries in per_ticker.items():
        scores = {}
        for hours in TRIPLET_HOURS:
            cutoff = now - dt.timedelta(hours=hours)
            inside = [e for e in entries if e[0] >= cutoff]
            if not inside:
                scores[hours] = None
                continue
            observed = sum(e[1] for e in inside)
            expected = sum(e[2] for e in inside)
            variance = sum(e[3] for e in inside)
            scores[hours] = ((observed - expected) / max(variance, VARIANCE_FLOOR) ** 0.5
                             if variance else None)
        out[ticker] = scores
    return out


def _tones(tickers, sources, since, now):
    """Bullish / neutral / bearish mention counts per ticker.

    Counted from the mention rows rather than derived from the stored bucket
    mean, for the reason in the module docstring: a mean cannot tell a balanced
    argument apart from a room that used no sentiment words at all.
    """
    if not tickers:
        return {}

    score = RadarMention.lexicon_sentiment
    rows = (db.session.query(
                RadarMention.ticker,
                sa.func.sum(sa.case((score > 0, 1), else_=0)),
                sa.func.sum(sa.case((score < 0, 1), else_=0)),
                sa.func.count())
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.ticker.in_(list(tickers)),
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium')))
            .group_by(RadarMention.ticker).all())

    out = {}
    for ticker, bullish, bearish, total in rows:
        bullish, bearish = int(bullish or 0), int(bearish or 0)
        out[ticker] = Tone(bullish=bullish, bearish=bearish,
                           neutral=max(0, int(total) - bullish - bearish))
    return out


def _daily_counts(tickers, sources, start, now):
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


def _first_watched_day(sources, start, now):
    """Earliest calendar day any bucket exists for. Before it, chatter is
    unknown rather than zero."""
    earliest = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
                .filter(RadarBucketSource.source.in_(list(sources)),
                        RadarBucketSource.bucket_start >= start).scalar())
    return earliest.date() if earliest else None


def _chart_for(ticker, start, days, closes_by_day, counts, watched_from):
    """One Chart, both arrays indexed by calendar day from `start`."""
    closes, chatter = [], []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        closes.append(closes_by_day.get(day))
        if watched_from is None or day < watched_from:
            chatter.append(None)
        else:
            chatter.append(counts.get((ticker, day), 0))
    return Chart(start=start, closes=closes, chatter=chatter)


def _price_series(tickers, since, now):
    """Every quote snapshot in the window, per ticker, oldest first."""
    if not tickers:
        return {}

    rows = (db.session.query(RadarQuote.ticker, RadarQuote.fetched_at,
                             RadarQuote.price)
            .filter(RadarQuote.ticker.in_(list(tickers)),
                    RadarQuote.fetched_at >= since,
                    RadarQuote.fetched_at <= now)
            .order_by(RadarQuote.fetched_at.asc()).all())

    out = collections.defaultdict(list)
    for ticker, fetched_at, price in rows:
        out[ticker].append((fetched_at, price))
    return out


def build(sources, now, window_hours=4, segment=None, limit=50,
          leads=LEAD_COUNT):
    """The whole board.

    Segment counts are taken before the segment filter, because the counts
    label the filter's own buttons -- computing them after it would report the
    selected segment's size in every slot.
    """
    session = market_calendar.session_state(now.replace(tzinfo=dt.timezone.utc))
    ranked = leaderboard.build_rows(sources, now, window_hours=window_hours,
                                    segment=None, limit=None, session=session)

    counts = collections.Counter(row.segment for row in ranked)
    segment_counts = dict(counts)
    segment_counts['all'] = len(ranked)

    if segment is not None:
        ranked = [row for row in ranked if row.segment == segment]
    ranked = ranked[:limit]

    tickers = [row.ticker for row in ranked]
    since = now - dt.timedelta(hours=SERIES_HOURS)

    covered = _covered_hours(sources, since, now)
    totals = _hourly_counts(tickers, sources, since, now)
    triplets = _triplets(tickers, sources, now)
    tones = _tones(tickers, sources, since, now)
    prices = _price_series(tickers[:leads], since, now)

    # The chart spans a calendar year regardless of the scoring window, so it
    # gets its own start rather than reusing `since`.
    chart_start = now.date() - dt.timedelta(days=CHART_DAYS - 1)
    chart_from = dt.datetime.combine(chart_start, dt.time.min)
    stored_closes = history.closes_for(tickers, days=CHART_DAYS,
                                       today=now.date())
    daily_counts = _daily_counts(tickers, sources, chart_from, now)
    watched_from = _first_watched_day(sources, chart_from, now)

    empty_triplet = {hours: None for hours in TRIPLET_HOURS}
    rows = [BoardRow(
        rank=row,
        series=_series_for(row.ticker, totals, covered, since, now),
        triplet=triplets.get(row.ticker, empty_triplet),
        tone=tones.get(row.ticker, Tone(0, 0, 0)),
        price_series=prices.get(row.ticker, []) if index < leads else [],
        chart=(_chart_for(row.ticker, chart_start, CHART_DAYS,
                          dict(stored_closes[row.ticker]), daily_counts,
                          watched_from)
               if row.ticker in stored_closes else None),
    ) for index, row in enumerate(ranked)]

    return Board(generated_at=now, sources=list(sources), segment=segment,
                 window_hours=window_hours, segment_counts=segment_counts,
                 rows=rows, session=session)
