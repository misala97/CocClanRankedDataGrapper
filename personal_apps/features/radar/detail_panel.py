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
from models import RadarBucketSource, RadarMention, RadarPost, TickerUniverse

from . import detail as chart_mod
from . import phrasing
from . import history, universe
from . import quotes as quotes_mod
from .config import (expand_sources, expand_sources_for_history, source_kind,
                     source_root)

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
    # How often the word list and the model read the same post the opposite
    # way. Both scores are kept precisely so this is answerable -- a
    # disagreement is the sarcasm the lexicon alone cannot see.
    disagreements: int
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
    baseline_days: float | None
    market: str = 'us'
    quote: object = None


def window_figures(ticker, sources, since, now):
    """Mentions, expected and baseline age across the scoring window.

    Read from buckets rather than taken from a leaderboard row, because the
    panel is reachable for a ticker the board filtered out -- and refusing to
    describe one because it did not rank is the wrong answer to "tell me about
    this".

    STRICT expansion, unlike the breakdown below: `expected` and
    `baseline_days` are baseline-relative, and the written read quotes
    `mentions` against `expected` in the same sentence. Pooling a pre-split
    root count into an expectation computed for the post-split population
    would compare two different populations' numbers to each other.
    """
    sources = expand_sources(sources)
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
    sources = expand_sources_for_history(sources)
    base = (db.session.query(RadarPost)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(RadarMention.ticker == ticker,
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium'))))
    rows = base.order_by(RadarPost.created_utc.desc()).limit(POST_LIMIT).all()
    return rows, base.count()


def _tone_of(lexicon, verdict):
    """'bullish', 'bearish' or None, from the two scores together.

    The model outranks the word list where both spoke. The lexicon is forty
    words with a negation window: it reads "great, another green day" after a
    crash as bullish, which is exactly the case spec 6.11 specified a re-read
    for.

    `unclear` votes neither way and BLOCKS the lexicon. It means the post named
    the ticker without expressing a view, and that read is better informed than
    the word list it overrides.

    A NULL verdict falls back to the lexicon rather than counting as toneless:
    verdicts arrive on a scheduled pass, so a fresh mention has none, and
    treating that as silence would make the newest posts look even-handed.
    """
    if verdict == 'bullish':
        return 'bullish'
    if verdict == 'bearish':
        return 'bearish'
    if verdict is not None:            # 'neutral' or 'unclear'
        return None
    if lexicon and lexicon > 0:
        return 'bullish'
    if lexicon and lexicon < 0:
        return 'bearish'
    return None


def breakdown_for(ticker, sources, since, now):
    """One pass over the window's mentions, taken apart several ways.

    Loaded rather than aggregated in SQL because the same rows answer five
    questions -- per venue, per author, per hour, the concentration, and the
    totals -- and five GROUP BY queries would read them five times over for a
    set that is at most a few thousand rows.
    """
    sources = expand_sources_for_history(sources)
    score = RadarMention.lexicon_sentiment
    verdict = RadarMention.llm_sentiment
    rows = (db.session.query(RadarPost.source, RadarPost.author,
                             RadarPost.channel, RadarPost.created_utc, score,
                             verdict)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(RadarMention.ticker == ticker,
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium'))).all())

    by_source = {}
    by_author = collections.Counter()
    by_hour = collections.Counter()
    bullish = bearish = disagreements = 0

    for source, author, channel, when, sentiment, llm in rows:
        # A VENUE IS A ROOT. Every stored Reddit name -- the eight
        # `reddit:<sub>` and the pre-split bare `reddit` -- pools into one
        # `reddit` row, which is what this table showed before the subreddit
        # split and what `venues=len(b.venues)` in the written read counts.
        #
        # Splitting it into eight rows with eight voice counts and eight
        # shares-of-mentions would be a product decision about what this
        # surface is FOR; the split that produced these names was a decision
        # about how status and scoring are partitioned. Shipping the first as
        # a side effect of the second would foreclose it silently.
        venue = source_root(source)
        entry = by_source.setdefault(venue, [0, set()])
        entry[0] += 1
        # The independent unit differs by kind, the same way the eligibility
        # gate's does: an author on a forum, a channel on a broadcast network.
        entry[1].add(channel if source_kind(source) == 'broadcast' else author)
        by_author[author] += 1
        by_hour[when.replace(minute=0, second=0, microsecond=0)] += 1
        tone = _tone_of(sentiment, llm)
        if tone == 'bullish':
            bullish += 1
        elif tone == 'bearish':
            bearish += 1
        # A post the word list read one way and the model read the other is a
        # post that was being sarcastic. Both scores are kept precisely so this
        # comparison is possible; nothing performed it until now.
        lexicon_only = _tone_of(sentiment, None)
        if llm is not None and lexicon_only is not None and tone != lexicon_only:
            disagreements += 1

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
        disagreements=disagreements,
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


def build(ticker, sources, now, window_hours=4, span=chart_mod.DEFAULT_SPAN,
          market='us'):
    """One ticker's panel. Raises UnknownTicker if it is not in the universe.

    `sources` is the viewer's SELECTION, unexpanded -- each query below picks
    its own expansion, because the chart and the breakdown may see the
    pre-split root `reddit` history and window_figures may not. See
    config.expand_sources.
    """
    if not chart_mod.known_span(span):
        raise ValueError('unknown span')

    profile = TickerUniverse.query.filter_by(symbol=ticker).one_or_none()
    if profile is None:
        raise chart_mod.UnknownTicker(ticker)

    since = now - dt.timedelta(hours=window_hours)
    quote = quotes_mod.quote_views_for([ticker], market, now)[ticker]
    session = quote.session
    status = quote.tape_status
    move = (quotes_mod.move_since(ticker, hours=window_hours, now=now,
                                  market=quote.market, mic=quote.mic)
            if quote.score_eligible else None)

    # Intraday spans price from radar_quotes and slot by minutes; the daily
    # ones price from radar_daily_closes and slot by calendar day. Different
    # sources, different granularity, same array shape out.
    if chart_mod.is_intraday(span):
        chart = chart_mod.intraday_chart_for(
            ticker, sources, now, span, market=quote.market, mic=quote.mic)
    else:
        days = chart_mod.SPAN_DAYS[span]
        start = now.date() - dt.timedelta(days=days - 1)
        from_dt = dt.datetime.combine(start, dt.time.min)
        stored = dict(history.closes_for([ticker], days=days,
                                          today=now.date(), market=quote.market,
                                          mic=quote.mic).get(ticker, []))
        chart = chart_mod.chart_for(
            ticker, start, days, stored,
            chart_mod.daily_counts([ticker], sources, from_dt, now),
            chart_mod.first_watched_day(sources, from_dt, now))

    breakdown = breakdown_for(ticker, sources, since, now)
    breakdown.first_seen = first_mention_day(ticker)
    posts, post_total = _posts(ticker, sources, since, now)
    mentions, expected, baseline_days = window_figures(
        ticker, sources, since, now)

    # The chart's own-normal line, through the same guard as the "n x normal"
    # wording -- the drawing and the words must not disagree about whether a
    # baseline is thick enough to mean anything.
    if phrasing.ratio_value(mentions, expected) is not None:
        per_hour = expected / window_hours
        chart.normal_per_slot = per_hour * (chart.step_minutes / 60.0)

    return Detail(
        ticker=ticker,
        name=profile.name,
        exchange=profile.exchange,
        segment=universe.segment_for(profile.market_cap, profile.ipo_date,
                                      quote.price,
                                     now.date(), profile.name,
                                     profile.is_etf),
        market_cap=profile.market_cap,
        ipo_date=profile.ipo_date,
        price=quote.price,
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
        market=market,
        quote=quote,
    )
