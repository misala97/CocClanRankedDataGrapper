# personal_apps/features/radar/leaderboard.py
"""One ranked row per ticker.

Reads scored buckets, quotes and universe rows; decides nothing about
appearance. What it does decide is what is worth showing at all -- the
eligibility floor -- and that matters more on a thin board than a busy one,
because the temptation to pad is greatest when there is little to show.
"""
import collections
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource, RadarMention, RadarPost, TickerUniverse

from . import divergence as divergence_mod
from . import quotes as quotes_mod
from . import scoring, universe
from .config import PROVISIONAL_BASELINE_DAYS


@dataclasses.dataclass
class Row:
    ticker: str
    name: str | None
    segment: str
    divergence: float | None
    mention_z: float | None
    mentions: int
    expected: float
    authors: int
    text_ratio: float
    sources: list
    price: object
    price_move: object
    direction: str
    price_status: str
    baseline_days: int | None
    marks: list


def _distinct_authors(tickers, sources, since, now):
    """True distinct authors per ticker across the whole window.

    Buckets store distinct_authors as a COUNT, so aggregating them can only
    take a maximum -- and a maximum systematically undercounts. Two buckets
    holding {x, y} and {z, w} have four distinct authors between them and
    report two.

    Measured on live data the gap was severe: NVDA showed 26 real authors
    against a bucket maximum of 2, and SPY 21 against 2. The eligibility floor
    needs three, so the maximum was rejecting almost every ticker on the board
    -- including the ones with the broadest genuine participation.

    Counted from the mention rows instead, where the authors themselves are
    still available.
    """
    if not tickers:
        return {}

    rows = (db.session.query(RadarMention.ticker,
                             sa.func.count(sa.distinct(RadarPost.author)))
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.ticker.in_(list(tickers)),
                    RadarPost.source.in_(list(sources)),
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now,
                    RadarMention.confidence.in_(('high', 'medium')))
            .group_by(RadarMention.ticker).all())
    return {ticker: count for ticker, count in rows}


def _universe_rows(tickers):
    if not tickers:
        return {}
    rows = TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(list(tickers))).all()
    return {row.symbol: row for row in rows}


def build_rows(sources, now, window_hours=4, segment=None, limit=50):
    """Ranked leaderboard rows for the selected sources.

    The source list is a read-time filter: it re-pools components that were
    stored per source, and never touches how anything was scored (spec 8.6).
    """
    since = now - dt.timedelta(hours=window_hours)

    scored_rows = (RadarBucketSource.query
                   .filter(RadarBucketSource.source.in_(list(sources)),
                           RadarBucketSource.bucket_start >= since,
                           RadarBucketSource.bucket_start < now,
                           RadarBucketSource.mention_z.isnot(None))
                   .all())

    grouped = collections.defaultdict(list)
    for row in scored_rows:
        grouped[row.ticker].append(row)

    profiles = _universe_rows(grouped.keys())
    author_counts = _distinct_authors(grouped.keys(), sources, since, now)
    today = now.date()
    rows = []

    for ticker, buckets in grouped.items():
        mentions = sum(b.mention_count for b in buckets)
        expected = sum(b.expected or 0.0 for b in buckets)
        variance = sum(b.variance or 0.0 for b in buckets)
        # True count where the posts are still retained; the bucket maximum
        # only as a fallback once they have aged out. The fallback undercounts,
        # which is the safe direction -- it can hide a ticker but never invent
        # breadth that was not there.
        authors = author_counts.get(
            ticker, max(b.distinct_authors for b in buckets))
        text_ratio = min(b.distinct_text_ratio for b in buckets)

        # Below the floor there is nothing to rank. Showing it low would imply
        # it was measured and found wanting, when it was never measurable.
        if not scoring.is_eligible(mentions, authors, text_ratio):
            continue

        mention_z = ((mentions - expected)
                     / max(variance, 0.25) ** 0.5) if variance else None

        contributing = sorted({b.source for b in buckets})
        baseline_days = min((b.baseline_days for b in buckets
                             if b.baseline_days is not None), default=None)

        profile = profiles.get(ticker)
        status = quotes_mod.price_status(ticker, now)
        move = quotes_mod.move_since(ticker, hours=window_hours, now=now)

        latest = None
        if status != 'unknown':
            from models import RadarQuote
            latest = (RadarQuote.query
                      .filter(RadarQuote.ticker == ticker,
                              RadarQuote.fetched_at <= now)
                      .order_by(RadarQuote.fetched_at.desc()).first())

        # A frozen tape reports no movement while mentions explode because it
        # froze. That is maximum divergence produced by an artifact, so the
        # row carries the mark and no score rather than a flattering number.
        value = None
        if status == 'ok' and move is not None and mention_z is not None:
            sigma = profile.daily_sigma if profile else None
            move_z = divergence_mod.price_move_z(
                move, quotes_mod.scale_sigma(sigma, window_hours))
            if move_z is not None:
                value = divergence_mod.divergence(mention_z, move_z)

        marks = []
        if status == 'stale':
            marks.append('no-print')
        if len(contributing) == 1 and len(sources) > 1:
            marks.append('single-source')
        if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
            marks.append('provisional')
        if any(b.status == 'truncated' for b in buckets):
            marks.append('partial')

        row_segment = universe.segment_for(
            profile.market_cap if profile else None,
            profile.ipo_date if profile else None,
            latest.price if latest else None,
            today)
        if segment is not None and row_segment != segment:
            continue

        rows.append(Row(
            ticker=ticker,
            name=profile.name if profile else None,
            segment=row_segment,
            divergence=value,
            mention_z=mention_z,
            mentions=mentions,
            expected=expected,
            authors=authors,
            text_ratio=text_ratio,
            sources=contributing,
            price=latest.price if latest else None,
            price_move=move,
            direction=divergence_mod.direction(move),
            price_status=status,
            baseline_days=baseline_days,
            marks=marks,
        ))

    # Divergence first where it exists, then mention_z. A ticker with no price
    # is not evidence of anything about its price, so it sorts below one that
    # has been measured -- but it is not dropped.
    rows.sort(key=lambda r: (r.divergence is not None,
                             r.divergence if r.divergence is not None else 0,
                             r.mention_z or 0), reverse=True)
    return rows[:limit]
