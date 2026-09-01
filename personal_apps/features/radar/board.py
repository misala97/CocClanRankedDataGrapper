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

from . import coverage, leaderboard, phrasing
from .market_calendars import session_bounds, session_state
from .quotes import _quote_matches
from .config import (SEGMENT_GROUPS, VARIANCE_FLOOR, expand_sources,
                     expand_sources_for_history, segments_in)

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
    # Price per hour over the same grid as `series`, None where no quote
    # landed -- the chart-row draws both on one time axis.
    price_series: list
    # The ticker's own normal chatter rate, as mentions per hour, or None
    # when the baseline is too thin to divide by (phrasing.ratio_value's
    # guard). The chart draws it as the dashed line "above normal" is
    # measured against.
    normal_per_hour: object
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
    market: str
    display_timezone: str
    market_venue: str
    next_boundary_label: str
    next_boundary_at: dt.datetime
    # Several, and a union. Empty means no filter.
    segments: list
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


def _next_boundary(market, now, session, mic=None):
    """The selected market's next meaningful open/close in aware UTC."""
    aware_now = now.replace(tzinfo=dt.timezone.utc)
    bounds = session_bounds(market, aware_now, mic=mic)
    if session == 'premarket':
        return 'opens', bounds.regular_opens_at
    if session == 'regular':
        return 'closes', bounds.regular_closes_at
    if session == 'afterhours':
        return 'closes', bounds.closes_at

    # Before the local premarket opens, the current calendar day is useful.
    if (bounds.opens_at > aware_now and
            session_state(market, bounds.opens_at, mic=mic) == 'premarket'):
        return 'opens', bounds.opens_at
    # Xetra has a closed gap between its 08:55 extended session and the 09:00
    # regular session.  It is still today's trading day, so do not skip to the
    # next premarket opening.
    if (bounds.regular_opens_at > aware_now and
            session_state(market, bounds.regular_opens_at,
                          mic=mic) == 'regular'):
        return 'opens', bounds.regular_opens_at
    # Nights, weekends and closures need the next actual trading day rather
    # than a calendar date that happens to contain no session.
    for days in range(1, 8):
        candidate = aware_now + dt.timedelta(days=days)
        future = session_bounds(market, candidate, mic=mic)
        if session_state(market, future.opens_at, mic=mic) == 'premarket':
            return 'opens', future.opens_at
    raise RuntimeError(f'no trading boundary found for {market}')


def _covered_hours(sources, since, now):
    """Hours in which any bucket at all was written for these sources.

    The proxy for "ingest was alive". It is a proxy and not a record: a genuine
    board-wide silence reads the same as a stopped daemon. Both resolve to
    "not measured", which is the honest half of the ambiguity -- the dishonest
    half would be drawing a zero.

    The scan itself lives in coverage.py, hinted and memoised, shared with
    the panel chart's watched_slots -- see that module's header for the
    measured reasons.
    """
    starts = coverage.covered_bucket_starts(sources, since, now)
    return {_hour_floor(start) for start in starts}


def _hourly_counts(tickers, sources, since, now):
    """Pooled mention count per (ticker, hour)."""
    if not tickers:
        return {}

    sources = expand_sources_for_history(sources)
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


def _hourly_prices(ranked, since, now):
    """Last quoted price per (ticker, hour), for the rows' own quote identity.

    The chart-rows draw price against chatter on one axis, so this walks the
    same 24 hours the chatter series covers. One query for the whole board --
    the per-ticker version of this on the detail page is fine there because
    the panel shows one ticker, but a board did that once for quotes and it
    was the 1.58s TTFB bug.

    Identity per row, not per market: each row's quote already names the
    venue that answered (market, mic), including the US-fallback case on the
    German board, and the history drawn beside a quote must be the history
    OF that quote. `_quote_matches` is reused so the two cannot disagree.

    No carry-forward, same as the detail chart: an hour nobody priced is
    None, and the line breaks rather than flat-lining through it.
    """
    if not ranked:
        return {}

    identity = sa.or_(*[
        sa.and_(*_quote_matches(row.ticker, row.quote.market or 'us',
                                row.quote.mic))
        for row in ranked])
    rows = (db.session.query(RadarQuote.ticker, RadarQuote.fetched_at,
                             RadarQuote.price)
            .filter(identity,
                    RadarQuote.fetched_at >= since,
                    RadarQuote.fetched_at < now)
            .order_by(RadarQuote.fetched_at)
            .all())

    prices = {}
    for ticker, fetched_at, price in rows:
        # Ascending order, so the last write per hour is that hour's close.
        prices[(ticker, _hour_floor(fetched_at))] = float(price)
    return prices


def _price_series_for(ticker, prices, since, now):
    """One price per hour across the window, oldest first; None is a gap.

    Not gated on `covered` -- that set says whether CHATTER ingest was alive,
    which proves nothing about the quote poller. Price coverage is its own
    fact: a slot is None exactly when no quote landed in it.
    """
    series = []
    hour = _hour_floor(since)
    end = _hour_floor(now)
    while hour <= end:
        series.append(prices.get((ticker, hour)))
        hour += dt.timedelta(hours=1)
    return series


def _triplets(tickers, sources, now):
    """mention_z at each triplet window, per ticker.

    One query over the longest window, sliced in Python. Three queries would
    read the same rows three times, and the longest window contains the other
    two by construction.
    """
    if not tickers:
        return {}

    # STRICT: every figure below comes off `expected` and `variance`, which
    # are relative to a baseline. The pre-split root `reddit` rows were
    # baselined against a different population and may not enter a z.
    sources = expand_sources(sources)
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

    sources = expand_sources_for_history(sources)
    # Attitude first (sentiment v2, spec §7.1), the legacy projection next,
    # the local float last. A DECIDED attitude that is not positive/negative
    # (mixed, none) blocks the fallbacks the same way a legacy
    # neutral/unclear verdict does. Judgments arrive on a scheduled pass, so
    # fresh rows carry none and the fallback chain is the normal path.
    att = RadarMention.sentiment_attitude
    legacy = RadarMention.llm_sentiment
    score = RadarMention.lexicon_sentiment
    rel = RadarMention.sentiment_relevance
    origin = RadarMention.sentiment_content_origin
    bullish = sa.case(
        (att == 'positive', 1),
        (att.isnot(None), 0),
        (legacy == 'bullish', 1),
        (legacy.isnot(None), 0),
        (score > 0, 1), else_=0)
    bearish = sa.case(
        (att == 'negative', 1),
        (att.isnot(None), 0),
        (legacy == 'bearish', 1),
        (legacy.isnot(None), 0),
        (score < 0, 1), else_=0)
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
                    RadarMention.confidence.in_(('high', 'medium')),
                    # NULL-safe eligibility: unjudged (NULL) rows stay
                    # counted; only a FINAL irrelevant/broadcast verdict
                    # leaves the DENOMINATOR (spec §7.2), `uncertain` stays.
                    # Written as AND of OR-IS-NULL legs because
                    # NOT(a OR b) is NULL -- and therefore filtered out --
                    # for every unjudged row under three-valued logic.
                    sa.or_(rel.is_(None), rel != 'irrelevant'),
                    sa.or_(origin.is_(None),
                           origin != 'broadcast_or_automated'))
            .group_by(RadarMention.ticker).all())

    out = {}
    for ticker, bullish, bearish, total in rows:
        bullish, bearish = int(bullish or 0), int(bearish or 0)
        out[ticker] = Tone(bullish=bullish, bearish=bearish,
                           neutral=max(0, int(total) - bullish - bearish))
    return out


def build(sources, now, window_hours=4, segments=(), limit=50,
          leads=LEAD_COUNT, min_venues=1, market='us'):
    """The whole board.

    `sources` is the viewer's SELECTION, root-level (`reddit`) or concrete
    (`reddit:pennystocks`) -- not an expanded list. Each query below expands
    it for itself, because the two expansions differ: see config.expand_sources
    and config.expand_sources_for_history.

    Segment counts are taken before the segment filter, because the counts
    label the filter's own buttons -- computing them after it would report the
    selected segment's size in every slot.
    """
    # The board-wide Germany clock is Tradegate-first: XGAT is the
    # preferred venue and carries the longer retail session. A row or
    # fallback chart still uses its actual selected quote MIC.
    board_mic = 'XGAT' if market == 'de' else None
    session = session_state(market, now.replace(tzinfo=dt.timezone.utc),
                            mic=board_mic)
    boundary_label, boundary_at = _next_boundary(market, now, session,
                                                 mic=board_mic)
    ranking = leaderboard.build_rows(sources, now, window_hours=window_hours,
                                     segments=(), limit=None, market=market)
    ranked = ranking.rows

    counts = collections.Counter(row.segment for row in ranked)
    segment_counts = dict(counts)
    segment_counts['all'] = len(ranked)
    segment_counts['discover'] = sum(
        1 for row in ranked if row.segment in SEGMENT_GROUPS['discover'])

    # Both venue counts come from the same unfiltered pass, for the reason the
    # segment counts do: they label the control, and counting after the filter
    # would report the filtered size in every slot.
    #
    # A VENUE IS A ROOT. `row.sources` is concrete, so two subreddits are two
    # names -- but they are one platform, one user population and one
    # rate-limit budget. The breadth control's whole claim is that a second
    # venue is INDEPENDENT corroboration, and r/wallstreetbets agreeing with
    # r/pennystocks is not that. `row.venues` is the rooted count.
    venue_counts = {
        'any': len(ranked),
        'multi': sum(1 for row in ranked if row.venues > 1),
    }

    allowed = segments_in(segments)
    if allowed:
        ranked = [row for row in ranked if row.segment in allowed]
    if min_venues > 1:
        kept = [row for row in ranked if row.venues >= min_venues]
        removed = len(ranked) - len(kept)
        if removed:
            ranking.excluded['one_venue'] = (
                ranking.excluded.get('one_venue', 0) + removed)
        ranked = kept
    ranked = ranked[:limit]

    tickers = [row.ticker for row in ranked]
    since = now - dt.timedelta(hours=SERIES_HOURS)

    covered = _covered_hours(sources, since, now)
    totals = _hourly_counts(tickers, sources, since, now)
    prices = _hourly_prices(ranked, since, now)
    triplets = _triplets(tickers, sources, now)
    # The lean arrows must agree with the detail panel's chatter breakdown,
    # which counts the SELECTED window -- not the sparkline's 24h axis.
    tones = _tones(tickers, sources,
                   now - dt.timedelta(hours=window_hours), now)

    empty_triplet = {hours: None for hours in TRIPLET_HOURS}
    rows = [BoardRow(
        rank=row,
        series=_series_for(row.ticker, totals, covered, since, now),
        price_series=_price_series_for(row.ticker, prices, since, now),
        # Guarded by the same rule as the ratio wording: an expected under
        # the baseline floor is noise, and drawing a "normal" line off it
        # would be the bar version of "200x normal".
        normal_per_hour=(row.expected / window_hours
                         if phrasing.ratio_value(row.mentions,
                                                 row.expected) is not None
                         else None),
        triplet=triplets.get(row.ticker, empty_triplet),
        tone=tones.get(row.ticker, Tone(0, 0, 0)),
        clauses=phrasing.row_clauses(row, row.quote.session),
    ) for row in ranked]

    return Board(generated_at=now, sources=list(sources), market=market,
                 display_timezone='Europe/Berlin',
                 market_venue='Xetra' if market == 'de' else 'US markets',
                 next_boundary_label=boundary_label, next_boundary_at=boundary_at,
                  segments=list(segments),
                 window_hours=window_hours, segment_counts=segment_counts,
                 rows=rows, session=session, venue_counts=venue_counts,
                 min_venues=min_venues, excluded=ranking.excluded)
