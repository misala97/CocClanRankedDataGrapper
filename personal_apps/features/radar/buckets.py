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

from .config import (BUCKET_MINUTES, MAX_BARE_PER_VOUCHER,
                     source_config_version)

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
    # The mention's identity in the journal, with source. Without it a rebuild
    # cannot tell one author's second post apart from the same post arriving in
    # a second cycle, and overlapping cycles would double-count the boundary.
    external_id: str
    created_utc: dt.datetime
    source: str
    # The venue inside the source. Journalled because a broadcast network's
    # independent unit is the channel rather than the author.
    channel: str
    author: str | None
    simhash: int
    confidence: str
    sentiment: float | None
    engagement: float


def bucket_start_for(when):
    """Floor a UTC instant to its 15-minute bucket."""
    return when.replace(minute=(when.minute // BUCKET_MINUTES) * BUCKET_MINUTES,
                        second=0, microsecond=0)


# Deferred until after MentionRow and bucket_start_for exist: journal imports
# both of those from this module at IMPORT time (`from .buckets import ...`),
# so when this module is the one imported first -- the common case, since
# ingest.py and every test import `buckets` rather than `journal` -- the names
# journal asks for must already be bound before this line runs, or the import
# fails with "cannot import name 'MentionRow' from partially initialized
# module" instead of resolving. Importing the MODULE here rather than a name
# from it is still what makes the cycle resolvable at all: this binding itself
# needs nothing from journal yet, only roll_up() does, at call time.
from . import journal


def _promote(rows):
    """Award `medium` to bare mentions another author has cashtagged.

    A `low` is an uncorroborated bare token -- measured at roughly 85% false
    positives against the real universe, which is why it is never scored on its
    own. A `high` from a DIFFERENT author in the same bucket is what vouches
    for it. One person writing both ZZA and $ZZA is a single opinion twice, not
    corroboration, which is why the author must differ.

    Two limits, both added 2026-08-25 after seven days of live data put ICE,
    IA, MAGA and GOP in the scored set:

    THE WINDOW IS THE BUCKET. Vouchers were keyed by ticker alone while this
    runs over the whole cycle's rows, so a cashtag at 14:03 corroborated a bare
    token at 14:47 -- and a catch-up cycle spans hours, which made the window
    unbounded in practice rather than the quarter-hour the rule describes.

    THE RATIO IS CAPPED. See config.MAX_BARE_PER_VOUCHER: a cashtag is one
    person's act of notation and cannot vouch for an unlimited crowd. Over the
    ceiling the whole group is refused rather than truncated, because there is
    no principled way to choose which four of two hundred deserve it, and the
    excess is itself the evidence that a common word has collided with a
    ticker.

    Returns a new list; the input is not mutated.
    """
    vouchers = collections.defaultdict(set)
    bare = collections.Counter()
    for row in rows:
        key = (row.ticker, bucket_start_for(row.created_utc))
        if row.confidence == 'high' and row.author:
            vouchers[key].add(row.author)
        elif row.confidence == 'low':
            bare[key] += 1

    credible = {key for key, authors in vouchers.items()
                if bare[key] <= MAX_BARE_PER_VOUCHER * len(authors)}

    promoted = []
    for row in rows:
        key = (row.ticker, bucket_start_for(row.created_utc))
        if (row.confidence == 'low' and key in credible
                and (vouchers[key] - {row.author})):
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

    # Store first, then rebuild from EVERYTHING in these windows -- not from
    # `usable`, which is one cycle's cursor slice. A bucket is recomputed from
    # scratch on every pass, which is right because cycles overlap and additive
    # rollup would double-count the boundary; it is only correct if the
    # recompute sees the whole quarter-hour. It did not, and production lost
    # 42.9% of its 10+ mention buckets to that (audit 2026-08-26).
    journal.record(usable)

    windows = {(r.ticker, bucket_start_for(r.created_utc)) for r in usable
               if bucket_start_for(r.created_utc) in touched}
    complete = journal.events_for(windows)

    grouped = collections.defaultdict(list)
    for row in _promote(complete):
        key = (row.ticker, bucket_start_for(row.created_utc))
        # A window the journal answered for that this cycle did not touch --
        # possible when two tickers share a bucket_start -- is not this cycle's
        # to rewrite.
        if key in windows:
            grouped[key].append(row)

    written = 0
    for (ticker, start), bucket_rows in grouped.items():
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
            child.source_config_version = version

        written += 1

    db.session.commit()
    return written
