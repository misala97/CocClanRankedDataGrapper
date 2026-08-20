"""Rollup from mentions to (ticker x 15 minutes).

Two rules carry the weight here.

A source that failed writes no row at all. Writing zero would be
indistinguishable from a genuinely quiet quarter-hour, would drag the trailing
mean down, and would manufacture a spike the moment ingest resumed -- which is
the whole reason status is per source rather than per bucket (spec 4.5).

A rerun of the same window replaces its counts rather than adding to them.
Cycles overlap by design, since catch-up re-reads the boundary, and additive
rollup would inflate every bucket that spans two cycles.
"""
import dataclasses
import datetime as dt
import statistics

from extensions import db
from models import RadarBucket

from .config import BUCKET_MINUTES, source_config_version

SOURCES = ('reddit', 'stocktwits')

# Statuses whose counts are real enough to store. `missing` is not one:
# see the module docstring.
_COUNTABLE = {'ok', 'truncated'}


@dataclasses.dataclass
class MentionRow:
    """One extracted mention, flattened for rollup."""
    ticker: str
    created_utc: dt.datetime
    source: str
    author: str | None
    simhash: int
    confidence: str
    sentiment: float | None
    engagement: float


def bucket_start_for(when):
    """Floor a UTC instant to its 15-minute bucket."""
    return when.replace(minute=(when.minute // BUCKET_MINUTES) * BUCKET_MINUTES,
                        second=0, microsecond=0)


def _summarize(rows):
    authors = {r.author for r in rows if r.author}
    hashes = {r.simhash for r in rows}
    sentiments = [r.sentiment for r in rows if r.sentiment is not None]

    return {
        'mention_count': len(rows),
        'high_confidence_count': sum(1 for r in rows if r.confidence == 'high'),
        'distinct_authors': len(authors),
        'distinct_text_ratio': (len(hashes) / len(rows)) if rows else 1.0,
        'engagement_weighted_count': sum(r.engagement for r in rows),
        'count_reddit': sum(1 for r in rows if r.source == 'reddit'),
        'count_stocktwits': sum(1 for r in rows if r.source == 'stocktwits'),
        'sentiment_mean': (sum(sentiments) / len(sentiments)) if sentiments else None,
        'sentiment_stdev': (statistics.pstdev(sentiments)
                            if len(sentiments) > 1 else None),
    }


def roll_up(rows, statuses, touched):
    """Write buckets for `touched` windows from `rows`.

    statuses maps source name to 'ok' | 'missing' | 'truncated' for this
    cycle. touched is the set of bucket starts the cycle covered, passed in
    rather than derived from rows so that a window which produced no mentions
    from a healthy source still records a genuine zero.

    Returns the number of bucket rows written.
    """
    countable = [source for source in SOURCES
                 if statuses.get(source, 'missing') in _COUNTABLE]
    if not countable:
        return 0

    version = source_config_version()
    sources_ok = sum(1 for source in SOURCES
                     if statuses.get(source, 'missing') == 'ok')

    grouped = {}
    for row in rows:
        if row.source not in countable:
            continue
        key = (row.ticker, bucket_start_for(row.created_utc))
        grouped.setdefault(key, []).append(row)

    written = 0
    for (ticker, start), bucket_rows in grouped.items():
        if start not in touched:
            continue

        values = _summarize(bucket_rows)
        existing = RadarBucket.query.filter_by(
            ticker=ticker, bucket_start=start).one_or_none()

        if existing is None:
            existing = RadarBucket(ticker=ticker, bucket_start=start)
            db.session.add(existing)

        for field, value in values.items():
            setattr(existing, field, value)
        existing.status_reddit = statuses.get('reddit', 'missing')
        existing.status_stocktwits = statuses.get('stocktwits', 'missing')
        existing.sources_ok = sources_ok
        existing.source_config_version = version
        written += 1

    db.session.commit()
    return written
