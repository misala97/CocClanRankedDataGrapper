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

from . import leaderboard, market_calendar, phrasing
from .config import SEGMENT_GROUPS, VARIANCE_FLOOR, segments_in

# The windows the triplet reports, shortest first. Fixed rather than derived
# from the selected window: the point of the triplet is that all three are
# always visible together, so "building" and "fading" can be told apart at a
# glance instead of by switching the window control and remembering.
TRIPLET_HOURS = (1, 4, 24)

# How much history the sparkline and the lead charts draw.
SERIES_HOURS = 24

# How many rows get the full treatment at the top of the page.
LEAD_COUNT = 3


@dataclasses.dataclass
class Point:
    """One hour of the chatter series. `count` is None when unmeasured."""
    hour: dt.datetime
    count: int | None


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
    # Why this row is on the list, in words -- see phrasing.py. The client
    # styles by clause kind and never re-derives the wording, so there is
    # exactly one implementation of that judgement.
    #
    # The year-long price chart used to live here and now belongs to the
    # detail panel: at three years it is ~780 numbers, and a twenty-row board
    # would have shipped sixteen thousand of them to draw twenty sparklines.
    clauses: list


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
    # Breadth. `any` is every ranked row, `multi` the ones more than one venue
    # is talking about -- both counted before the filter, because they label
    # the control that applies it.
    venue_counts: dict
    min_venues: int
    # What the eligibility floor and the breadth filter left out, by reason.
    # Without it a quiet board and a stopped ingest look the same.
    excluded: dict


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

    # A model verdict outranks the word list on the same post, and a NULL
    # verdict falls back to it rather than counting as toneless. The lexicon
    # is forty words with a negation window: it reads "great, another green
    # day" after a crash as bullish, which is exactly the case spec 6.11
    # specified a re-read for. Verdicts arrive on a scheduled pass, so most
    # rows carry none at any given moment and the fallback is the normal path,
    # not the exception.
    #
    # `unclear` deliberately votes neither way AND blocks the lexicon from
    # voting: it means the post named the ticker without saying anything about
    # it, and the read is better informed than the word list it overrides.
    score = RadarMention.lexicon_sentiment
    verdict = RadarMention.llm_sentiment
    bullish = sa.case(
        (verdict.is_(None), sa.case((score > 0, 1), else_=0)),
        (verdict == 'bullish', 1), else_=0)
    bearish = sa.case(
        (verdict.is_(None), sa.case((score < 0, 1), else_=0)),
        (verdict == 'bearish', 1), else_=0)
    rows = (db.session.query(
                RadarMention.ticker,
                sa.func.sum(bullish),
                sa.func.sum(bearish),
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


def build(sources, now, window_hours=4, segment=None, limit=50,
          leads=LEAD_COUNT, min_venues=1):
    """The whole board.

    Segment counts are taken before the segment filter, because the counts
    label the filter's own buttons -- computing them after it would report the
    selected segment's size in every slot.
    """
    session = market_calendar.session_state(now.replace(tzinfo=dt.timezone.utc))
    ranking = leaderboard.build_rows(sources, now, window_hours=window_hours,
                                     segment=None, limit=None, session=session)
    ranked = ranking.rows

    counts = collections.Counter(row.segment for row in ranked)
    segment_counts = dict(counts)
    segment_counts['all'] = len(ranked)
    segment_counts['small'] = sum(
        1 for row in ranked if row.segment in SEGMENT_GROUPS['small'])

    # Both venue counts come from the same unfiltered pass, for the reason the
    # segment counts do: they label the control, and counting after the filter
    # would report the filtered size in every slot.
    venue_counts = {
        'any': len(ranked),
        'multi': sum(1 for row in ranked if len(row.sources) > 1),
    }

    allowed = segments_in(segment)
    if allowed:
        ranked = [row for row in ranked if row.segment in allowed]
    if min_venues > 1:
        ranked = [row for row in ranked if len(row.sources) >= min_venues]
    ranked = ranked[:limit]

    tickers = [row.ticker for row in ranked]
    since = now - dt.timedelta(hours=SERIES_HOURS)

    covered = _covered_hours(sources, since, now)
    totals = _hourly_counts(tickers, sources, since, now)
    triplets = _triplets(tickers, sources, now)
    tones = _tones(tickers, sources, since, now)

    empty_triplet = {hours: None for hours in TRIPLET_HOURS}
    rows = [BoardRow(
        rank=row,
        series=_series_for(row.ticker, totals, covered, since, now),
        triplet=triplets.get(row.ticker, empty_triplet),
        tone=tones.get(row.ticker, Tone(0, 0, 0)),
        clauses=phrasing.row_clauses(row, session),
    ) for row in ranked]

    return Board(generated_at=now, sources=list(sources), segment=segment,
                 window_hours=window_hours, segment_counts=segment_counts,
                 rows=rows, session=session, venue_counts=venue_counts,
                 min_venues=min_venues, excluded=ranking.excluded)
