"""Which tickers the model pass reads.

Judging costs money per mention and most mentions are of tickers nobody
will ever see: the floor keeps them off the board, and the large and fund
segments are the ones the reader cares least about. So the pass reads a
ticker only when someone watches it, or when it is outside the skipped
segments and can reach the board in the trailing window. Three queries,
no state, recomputed every cycle -- reachability changes hour by hour.
"""
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarMention, RadarPost, RadarWatch, TickerUniverse

from . import universe
from .config import (JUDGE_FLOOR_HOURS, JUDGE_GATE_ENABLED, JUDGE_SKIP_SEGMENTS,
                     MIN_DISTINCT_AUTHORS, MIN_MENTIONS)


@dataclasses.dataclass(frozen=True)
class Gate:
    """The judgeable set and the numbers behind it, for the log line."""
    tickers: frozenset
    watched: int
    reachable: int
    skipped_segment: int
    hours: int = JUDGE_FLOOR_HOURS
    skip_segments: tuple = JUDGE_SKIP_SEGMENTS
    # False only under the kill switch: the pass then ignores `tickers`
    # and reads everything, the pre-gate behaviour.
    enabled: bool = True


def _reachable(now, hours):
    """Tickers that clear the floor in the trailing window: MIN_MENTIONS
    high-confidence mentions from MIN_DISTINCT_AUTHORS distinct authors.
    NULL authors do not count as voices, the same as the board's rule."""
    since = now - dt.timedelta(hours=hours)
    rows = (db.session.query(RadarMention.ticker)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.confidence == 'high',
                    RadarPost.created_utc >= since,
                    RadarPost.created_utc < now)
            .group_by(RadarMention.ticker)
            .having(sa.and_(
                sa.func.count(RadarMention.id) >= MIN_MENTIONS,
                sa.func.count(sa.distinct(RadarPost.author)) >= MIN_DISTINCT_AUTHORS))
            .all())
    return {ticker for (ticker,) in rows}


def _segments(tickers, today):
    """Segment per ticker, the way the board and the search decide it. No
    price at hand: the penny override only matters on a board row."""
    if not tickers:
        return {}
    profiles = {u.symbol: u for u in TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(list(tickers))).all()}
    out = {}
    for ticker in tickers:
        u = profiles.get(ticker)
        out[ticker] = ('unknown' if u is None else universe.segment_for(
            u.market_cap, u.ipo_date, None, today, u.name, u.is_etf))
    return out


def _watched():
    return {ticker for (ticker,) in db.session.query(RadarWatch.ticker).distinct().all()}


def judgeable_tickers(now=None):
    """The gate for this cycle."""
    now = now or dt.datetime.utcnow()
    if not JUDGE_GATE_ENABLED:
        return Gate(tickers=frozenset(), watched=0, reachable=0,
                    skipped_segment=0, enabled=False)
    reachable = _reachable(now, JUDGE_FLOOR_HOURS)
    segments = _segments(reachable, now.date())
    admitted = {t for t in reachable if segments[t] not in JUDGE_SKIP_SEGMENTS}
    watched = _watched()
    return Gate(tickers=frozenset(admitted | watched),
                watched=len(watched),
                reachable=len(reachable),
                skipped_segment=len(reachable) - len(admitted))
