# personal_apps/features/radar/coverage.py
"""Which bucket slots ingest was alive for -- shared, hinted, and cached.

The board's hourly series and the panel chart's slot lane both need the same
fact: the set of bucket_starts any source wrote in a range, because a quiet
slot is zero only where ingest was watching (absence is never zero). Both
used to run their own DISTINCT over radar_bucket_sources, and both were
slow for the same two reasons, measured 2026-08-30 against production data:

* The per-subreddit split multiplied rows until ~95% of the table sits
  inside any 7-day range -- 826k of 864k rows -- so the range predicate
  excludes almost nothing.
* The optimizer prefers the (bucket_start, source) index, which does not
  carry `status`, so every one of those entries costs a heap read: 5.9-8.9s
  per panel fetch. Forced onto the covering (source, status, bucket_start)
  index the same query is index-only and takes ~1.0s.

The hint fixes the plan; the cache fixes the repetition. Coverage is
viewer-invariant (the same rule as the bulk-standing cache in coc_stats:
cache what does not depend on who is asking) and advances only as ingest
writes, so a 60-second memo is safely fresh -- the newest slot is partial
for longer than that anyway. Span clicks across the panel and the board's
2-minute refetches collapse onto one scan.
"""
import datetime as dt
import threading

from extensions import db
from models import RadarBucketSource

from .config import expand_sources_for_history

_TTL_SECONDS = 60

_lock = threading.Lock()
_memo: dict = {}


def covered_bucket_starts(sources, start, now):
    """Every bucket_start any of `sources` wrote in [start, now), ok or
    truncated. Returns a set of naive-UTC datetimes at bucket grain."""
    expanded = tuple(sorted(expand_sources_for_history(sources)))
    key = (expanded,
           start.replace(second=0, microsecond=0),
           now.replace(second=0, microsecond=0))

    at = dt.datetime.utcnow()
    with _lock:
        hit = _memo.get(key)
        if hit is not None and hit[0] > at:
            return hit[1]

    rows = (db.session.query(RadarBucketSource.bucket_start)
            .with_hint(RadarBucketSource,
                       'FORCE INDEX (ix_radar_bucket_sources_coverage)',
                       dialect_name='mysql')
            .filter(RadarBucketSource.source.in_(list(expanded)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now,
                    RadarBucketSource.status.in_(('ok', 'truncated')))
            .distinct().all())
    covered = {bucket_start for (bucket_start,) in rows}

    with _lock:
        _memo[key] = (at + dt.timedelta(seconds=_TTL_SECONDS), covered)
        # The board and the panel produce a handful of distinct keys per
        # minute; anything beyond that is old keys aging out.
        if len(_memo) > 64:
            expired = [k for k, (expires, _) in _memo.items() if expires <= at]
            for k in expired:
                del _memo[k]
    return covered


def clear_memo():
    """Tests only."""
    with _lock:
        _memo.clear()
