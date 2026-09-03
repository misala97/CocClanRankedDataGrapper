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
import time

import sqlalchemy.exc

from extensions import db
from models import RadarBucket, RadarBucketSource

from .config import (BUCKET_MINUTES, MAX_BARE_PER_VOUCHER, SCOREABLE_STATUSES,
                     VARIANCE_FLOOR, source_config_version, source_root)
# Safe at the top because journal.py imports this module as `buckets` rather
# than pulling MentionRow/bucket_start_for by name -- neither side touches an
# attribute of the other until a function actually runs, so it no longer
# matters which of the two a caller imports first. Verified all three orders
# (`import buckets`, `import journal`, `import ingest`) after this change;
# see the review that added this note for the command output.
from . import journal

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


# InnoDB picks a victim when two transactions grab the same rows in a
# different order and rolls it back whole; retrying the transaction is the
# documented remedy, not a workaround. It became reachable on 2026-09-03,
# when the Reddit cycle went from one subreddit's handful of rows to 34
# subreddits over 35-78 seconds and started overlapping the three-minute
# main cycle -- and scoring writes the same child rows every 15 minutes.
# Safe to repeat: a rollback undoes the whole attempt, and the rebuild
# reads the journal from scratch.
DEADLOCK_RETRIES = 3
DEADLOCK_BACKOFF_SECONDS = 0.5
_DEADLOCK_CODES = (1213, 1205)          # deadlock, lock wait timeout


def _is_deadlock(error):
    code = getattr(getattr(error, 'orig', None), 'args', (None,))[0]
    return code in _DEADLOCK_CODES


def roll_up(rows, statuses, touched, *, preserve_parent=False):
    """Write bucket totals and per-source rows, retrying a deadlock.

    See _roll_up_once for what the pass does. A losing transaction is
    retried whole rather than failed: the cycle above stores its posts and
    advances its cursors BEFORE this runs, so giving up here would leave
    those mentions journalled and never counted.
    """
    for attempt in range(DEADLOCK_RETRIES + 1):
        try:
            return _roll_up_once(rows, statuses, touched,
                                 preserve_parent=preserve_parent)
        except sqlalchemy.exc.OperationalError as error:
            if attempt >= DEADLOCK_RETRIES or not _is_deadlock(error):
                raise
            db.session.rollback()
            time.sleep(DEADLOCK_BACKOFF_SECONDS * (attempt + 1))


def _roll_up_once(rows, statuses, touched, *, preserve_parent=False):
    """One attempt at writing bucket totals and per-source rows for
    `touched` windows.

    statuses maps source name to 'ok' | 'missing' | 'truncated'. The set of
    source names is open -- nothing here knows or cares which they are.

    `preserve_parent=True` is the backfill's mode: a parent RadarBucket
    that already exists is left exactly as it is. The parent is rebuilt
    from the journal, and the journal keeps 48 h -- rebuilding an old
    window would erase every other source's totals from it. A parent that
    does not exist yet is created from these rows, which is the truth for
    a window nothing else observed.

    Returns the number of bucket rows written.
    """
    countable = {source for source, status in statuses.items()
                 if status in _COUNTABLE}
    if not countable:
        return 0

    version = source_config_version()
    # Distinct ROOTS, not names. "How many sources were ok" is a count of
    # venues, and eight subreddits reporting ok is Reddit reporting ok once --
    # counting the names would make this rise and fall with
    # REDDIT_SUBS_PER_CYCLE, which is a budget rather than a fact about
    # coverage. Nothing outside tests reads the column yet; the point is that
    # whatever starts reading it reads the same unit it always meant.
    sources_ok = len({source_root(source)
                      for source, status in statuses.items()
                      if status == 'ok'})

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

    promoted_rows = _promote(complete)
    journal.mark_promoted(promoted_rows)

    grouped = collections.defaultdict(list)
    for row in promoted_rows:
        key = (row.ticker, bucket_start_for(row.created_utc))
        # Guards a BUCKET_MINUTES change, not same-bucket_start collisions --
        # events_for matches on the STORED bucket_start column, so a row
        # journalled under a previous BUCKET_MINUTES can still come back for a
        # window whose boundaries have since changed. Recomputing the key from
        # created_utc under the CURRENT value is what catches that mismatch;
        # without this check such a row would be written into a bucket this
        # cycle never touched.
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
            existed = False
        else:
            existed = True
        if not (preserve_parent and existed):
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
            # Read before this loop restamps the column below -- otherwise
            # the comparison always reads current-against-current and a
            # generation change could never be seen. A fresh row's version is
            # Python None, which the `!=` below already treats as a mismatch.
            previous_version = child.source_config_version
            for field, value in per.items():
                setattr(child, field, value)
            child.status = statuses[source]
            # Two independent reasons a stored score stops being trustworthy,
            # cleared the same way:
            #
            # A status outside the shared final scoreable set cannot keep a
            # score. Both `ok` and current-generation `truncated` are valid:
            # truncated counts are incomplete but real, and their z errs
            # toward silence rather than a false spike.
            #
            # A row whose generation is NULL or differs from the one about to
            # be stamped was counted under a different aggregation -- Task 3c,
            # generation 2 rebuilds from the complete journal where generation
            # 1 rebuilt from one cursor slice. Restamping it to the current
            # version without clearing first would disguise an old-population
            # score as a current one, regardless of the row's status.
            if (child.status not in SCOREABLE_STATUSES
                    or previous_version != version):
                child.expected = None
                child.variance = None
                child.mention_z = None
                child.baseline_days = None
            child.source_config_version = version

        written += 1

    db.session.commit()
    return written


def rebuild_windows(windows):
    """Status-preserving re-rollup of specific windows from the journal.

    The chatter-eligibility correction path (spec §7.2): after a final
    irrelevant/broadcast verdict flips an event's flag -- or a review
    reversal flips it back -- the affected quarter-hours are recomputed
    from the complete, eligibility-filtered journal. Differences from the
    live roll_up, all deliberate:

    - Only windows with EXISTING child rows are touched; a window nothing
      ever counted has nothing to correct.
    - `status` is preserved from the stored children (source health is a
      fact about the cycle that observed it, not about this correction),
      and the parent's sources_ok likewise stays.
    - Removing the last eligible event leaves EXPLICIT ZEROS: a counted
      window whose chatter was all disqualified is a real measurement of
      zero, not an absence.
    - A same-generation scoreable child keeps expected/variance/
      baseline_days (the baseline inputs are still valid) and has its
      mention_z recomputed IMMEDIATELY from the corrected count -- a
      corrected bucket must not keep a stale z until the next scoring
      pass. A generation mismatch clears all four, exactly as the live
      path does.

    Idempotent: rebuilding twice from the same journal writes the same
    numbers.
    """
    windows = set(windows)
    if not windows:
        return 0

    version = source_config_version()
    complete = journal.events_for(windows)
    promoted_rows = _promote(complete)
    journal.mark_promoted(promoted_rows)

    grouped = collections.defaultdict(list)
    for row in promoted_rows:
        key = (row.ticker, bucket_start_for(row.created_utc))
        if key in windows:
            grouped[key].append(row)

    written = 0
    for ticker, start in windows:
        children = RadarBucketSource.query.filter_by(
            ticker=ticker, bucket_start=start).all()
        if not children:
            continue
        bucket_rows = grouped.get((ticker, start), [])

        bucket = RadarBucket.query.filter_by(
            ticker=ticker, bucket_start=start).one_or_none()
        if bucket is None:
            bucket = RadarBucket(ticker=ticker, bucket_start=start,
                                 sources_ok=0)
            db.session.add(bucket)
        totals = _summarize(bucket_rows)
        for field, value in totals.items():
            setattr(bucket, field, value)
        bucket.source_config_version = version

        by_source = collections.defaultdict(list)
        for row in bucket_rows:
            by_source[row.source].append(row)

        for child in children:
            per = _summarize(by_source.get(child.source, []))
            previous_version = child.source_config_version
            for field, value in per.items():
                setattr(child, field, value)
            if (child.status not in SCOREABLE_STATUSES
                    or previous_version != version):
                child.expected = None
                child.variance = None
                child.mention_z = None
                child.baseline_days = None
            elif child.expected is not None and child.variance is not None:
                child.mention_z = ((per['mention_count'] - child.expected)
                                   / max(child.variance,
                                         VARIANCE_FLOOR) ** 0.5)
            child.source_config_version = version

        written += 1

    db.session.commit()
    return written
