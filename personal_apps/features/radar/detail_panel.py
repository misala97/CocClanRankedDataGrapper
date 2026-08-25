# personal_apps/features/radar/detail_panel.py
"""The panel body: identity, breakdown, posts, and the window figures.

Split from detail.py, which holds the chart. Two files because the chart is
pure geometry over stored series and this is a set of queries about one
ticker's recent window -- different shapes, different reasons to change, and
detail.py's chart pieces are also what the tests for calendar alignment
exercise directly.
"""
import collections
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import (RadarBucketSource, RadarMention, RadarPost, RadarQuote,
                    TickerUniverse)

from . import detail as chart_mod
from . import history, market_calendar, universe
from . import quotes as quotes_mod
from .config import source_kind

# How many posts the panel shows. Enough to form an opinion, few enough to
# read; the count of the rest sits beside them.
POST_LIMIT = 25


@dataclasses.dataclass
class Venue:
    source: str
    mentions: int
    voices: int


@dataclasses.dataclass
class Breakdown:
    """The chatter, taken apart.

    `top_author_share` is the pump tell, and the reason this section exists at
    all: one account posting forty times reads as forty mentions everywhere
    else on the surface, and no other figure the board computes exposes it.
    """
    venues: list
    bullish: int
    neutral: int
    bearish: int
    top_author_share: float | None
    top_two_share: float | None
    peak_hour: dt.datetime | None
    peak_count: int
    first_seen: dt.date | None
    mentions: int
    voices: int


@dataclasses.dataclass
class Detail:
    ticker: str
    name: str | None
    exchange: str | None
    segment: str
    market_cap: object
    ipo_date: object
    price: object
    price_move: object
    price_status: str
    session: str
    span: str
    chart: object
    breakdown: Breakdown
    posts: list
    post_total: int
    # The window figures the written read needs. Carried here rather than
    # recomputed by the serializer, so the panel and the row phrase describe
    # the same numbers.
    mentions: int
    expected: float
    baseline_days: int | None


def window_figures(ticker, sources, since, now):
    """Mentions, expected and baseline age across the scoring window.

    Read from buckets rather than taken from a leaderboard row, because the
    panel is reachable for a ticker the board filtered out -- and refusing to
    describe one because it did not rank is the wrong answer to "tell me about
    this".
    """
    rows = (db.session.query(RadarBucketSource.mention_count,
                             RadarBucketSource.expected,
                             RadarBucketSource.baseline_days)
            .filter(RadarBucketSource.ticker == ticker,
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.bucket_start < now).all())
    mentions = sum(row[0] for row in rows)
    expected = sum(row[1] or 0.0 for row in rows)
    ages = [row[2] for row in rows if row[2] is not None]
    return mentions, expected, (min(ages) if ages else None)


def _posts(ticker, sources, since, now):
    """The newest posts, and how many there were in all."""
    base = (db.session.query(RadarPost)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(RadarMention.ticker == ticker,
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium'))))
    rows = base.order_by(RadarPost.created_utc.desc()).limit(POST_LIMIT).all()
    return rows, base.count()


def breakdown_for(ticker, sources, since, now):
    """One pass over the window's mentions, taken apart several ways.

    Loaded rather than aggregated in SQL because the same rows answer five
    questions -- per venue, per author, per hour, the concentration, and the
    totals -- and five GROUP BY queries would read them five times over for a
    set that is at most a few thousand rows.
    """
    score = RadarMention.lexicon_sentiment
    rows = (db.session.query(RadarPost.source, RadarPost.author,
                             RadarPost.channel, RadarPost.created_utc, score)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(RadarMention.ticker == ticker,
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium'))).all())

    by_source = {}
    by_author = collections.Counter()
    by_hour = collections.Counter()
    bullish = bearish = 0

    for source, author, channel, when, sentiment in rows:
        entry = by_source.setdefault(source, [0, set()])
        entry[0] += 1
        # The independent unit differs by kind, the same way the eligibility
        # gate's does: an author on a forum, a channel on a broadcast network.
        entry[1].add(channel if source_kind(source) == 'broadcast' else author)
        by_author[author] += 1
        by_hour[when.replace(minute=0, second=0, microsecond=0)] += 1
        if sentiment and sentiment > 0:
            bullish += 1
        elif sentiment and sentiment < 0:
            bearish += 1

    total = len(rows)
    ranked = by_author.most_common(2)
    peak = by_hour.most_common(1)

    return Breakdown(
        venues=[Venue(source=name, mentions=counts[0], voices=len(counts[1]))
                for name, counts in sorted(by_source.items(),
                                           key=lambda kv: -kv[1][0])],
        bullish=bullish,
        bearish=bearish,
        # Every mention whose text carried no lexicon word at all, which is
        # most of them. Hiding it would turn a handful of scored posts into a
        # confident-looking sentiment reading.
        neutral=total - bullish - bearish,
        top_author_share=(ranked[0][1] / total) if total and ranked else None,
        top_two_share=((sum(count for _, count in ranked) / total)
                       if total and ranked else None),
        peak_hour=peak[0][0] if peak else None,
        peak_count=peak[0][1] if peak else 0,
        first_seen=None,
        mentions=total,
        voices=len(by_author),
    )


def first_mention_day(ticker):
    """The first day this ticker was ever mentioned.

    From buckets, which are retained forever. Posts prune at 30 days, so
    reading it from them would report "first seen" as a rolling month ago for
    every ticker the radar has followed longer than that.
    """
    first = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
             .filter(RadarBucketSource.ticker == ticker).scalar())
    return first.date() if first else None


def build(ticker, sources, now, window_hours=4, span=chart_mod.DEFAULT_SPAN):
    """One ticker's panel. Raises UnknownTicker if it is not in the universe."""
    if not chart_mod.known_span(span):
        raise ValueError('unknown span')

    profile = TickerUniverse.query.filter_by(symbol=ticker).one_or_none()
    if profile is None:
        raise chart_mod.UnknownTicker(ticker)

    since = now - dt.timedelta(hours=window_hours)
    session = market_calendar.session_state(now.replace(tzinfo=dt.timezone.utc))
    status = quotes_mod.price_status(ticker, now, session=session)
    move = quotes_mod.move_since(ticker, hours=window_hours, now=now)

    latest = None
    if status != 'unknown':
        latest = (RadarQuote.query
                  .filter(RadarQuote.ticker == ticker,
                          RadarQuote.fetched_at <= now)
                  .order_by(RadarQuote.fetched_at.desc()).first())

    # Intraday spans price from radar_quotes and slot by minutes; the daily
    # ones price from radar_daily_closes and slot by calendar day. Different
    # sources, different granularity, same array shape out.
    if chart_mod.is_intraday(span):
        chart = chart_mod.intraday_chart_for(ticker, sources, now, span)
    else:
        days = chart_mod.SPAN_DAYS[span]
        start = now.date() - dt.timedelta(days=days - 1)
        from_dt = dt.datetime.combine(start, dt.time.min)
        stored = dict(history.closes_for([ticker], days=days,
                                         today=now.date()).get(ticker, []))
        chart = chart_mod.chart_for(
            ticker, start, days, stored,
            chart_mod.daily_counts([ticker], sources, from_dt, now),
            chart_mod.first_watched_day(sources, from_dt, now))

    breakdown = breakdown_for(ticker, sources, since, now)
    breakdown.first_seen = first_mention_day(ticker)
    posts, post_total = _posts(ticker, sources, since, now)
    mentions, expected, baseline_days = window_figures(
        ticker, sources, since, now)

    return Detail(
        ticker=ticker,
        name=profile.name,
        exchange=profile.exchange,
        segment=universe.segment_for(profile.market_cap, profile.ipo_date,
                                     latest.price if latest else None,
                                     now.date(), profile.name,
                                     profile.is_etf),
        market_cap=profile.market_cap,
        ipo_date=profile.ipo_date,
        price=latest.price if latest else None,
        price_move=move,
        price_status=status,
        session=session,
        span=span,
        chart=chart,
        breakdown=breakdown,
        posts=posts,
        post_total=post_total,
        mentions=mentions,
        expected=expected,
        baseline_days=baseline_days,
    )
