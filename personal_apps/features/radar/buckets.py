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
import collections
import dataclasses
import datetime as dt
import statistics

from extensions import db
from models import RadarBucket, RadarBucketSource

from .config import BUCKET_MINUTES, source_config_version

# Statuses whose counts are real enough to store. `missing` is not one:
# see the module docstring. There is deliberately no list of source names --
# the set is open, and a new source is a config entry plus one module.
_COUNTABLE = {'ok', 'truncated'}

# Confidences that count toward a score. `low` is stored and excluded.
_SCORED = {'high', 'medium'}


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


def _promote(rows):
    """Award `medium` to bare mentions another author has cashtagged.

    A `low` is an uncorroborated bare token -- measured at roughly 85% false
    positives against the real universe, which is why it is never scored on its
    own. A `high` from a DIFFERENT author in the same bucket is what vouches
    for it. One person writing both ZZA and $ZZA is a single opinion twice, not
    corroboration, which is why the author must differ.

    Returns a new list; the input is not mutated.
    """
    vouchers = collections.defaultdict(set)
    for row in rows:
        if row.confidence == 'high' and row.author:
            vouchers[row.ticker].add(row.author)

    promoted = []
    for row in rows:
        if row.confidence == 'low' and (vouchers[row.ticker] - {row.author}):
            promoted.append(dataclasses.replace(row, confidence='medium'))
        else:
            promoted.append(row)
    return promoted


def _summarize(rows):
    scored = [r for r in rows if r.confidence in _SCORED]
    authors = {r.author for r in scored if r.author}
    hashes = {r.simhash for r in scored}
    sentiments = [r.sentiment for r in scored if r.sentiment is not None]

    return {
        'mention_count': len(scored),
        'high_confidence_count': sum(1 for r in scored if r.confidence == 'high'),
        'low_count': sum(1 for r in rows if r.confidence == 'low'),
        'distinct_authors': len(authors),
        'distinct_text_ratio': (len(hashes) / len(scored)) if scored else 1.0,
        'engagement_weighted_count': sum(r.engagement for r in scored),
        'sentiment_mean': (sum(sentiments) / len(sentiments)) if sentiments else None,
        'sentiment_stdev': (statistics.pstdev(sentiments)
                            if len(sentiments) > 1 else None),
    }


def roll_up(rows, statuses, touched):
    """Write bucket totals and per-source rows for `touched` windows.

    statuses maps source name to 'ok' | 'missing' | 'truncated'. The set of
    source names is open -- nothing here knows or cares which they are.

    Returns the number of bucket rows written.
    """
    countable = {source for source, status in statuses.items()
                 if status in _COUNTABLE}
    if not countable:
        return 0

    version = source_config_version()
    sources_ok = sum(1 for status in statuses.values() if status == 'ok')

    usable = [r for r in rows if r.source in countable]
    grouped = collections.defaultdict(list)
    for row in _promote(usable):
        grouped[(row.ticker, bucket_start_for(row.created_utc))].append(row)

    written = 0
    for (ticker, start), bucket_rows in grouped.items():
        if start not in touched:
            continue

        totals = _summarize(bucket_rows)
        bucket = RadarBucket.query.filter_by(
            ticker=ticker, bucket_start=start).one_or_none()
        if bucket is None:
            bucket = RadarBucket(ticker=ticker, bucket_start=start)
            db.session.add(bucket)
        for field, value in totals.items():
            setattr(bucket, field, value)
        bucket.sources_ok = sources_ok
        bucket.source_config_version = version

        by_source = collections.defaultdict(list)
        for row in bucket_rows:
            by_source[row.source].append(row)

        for source in countable:
            per = _summarize(by_source.get(source, []))
            child = RadarBucketSource.query.filter_by(
                ticker=ticker, bucket_start=start, source=source).one_or_none()
            if child is None:
                child = RadarBucketSource(ticker=ticker, bucket_start=start,
                                          source=source)
                db.session.add(child)
            for field, value in per.items():
                setattr(child, field, value)
            child.status = statuses[source]

        written += 1

    db.session.commit()
    return written
