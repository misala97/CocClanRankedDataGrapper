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

The hint fixes the plan. The cache used to be a 60-second memo keyed by
(start, now) at minute grain -- which meant the whole scan again every
minute, and by 2026-09-01 (1.1M rows) that scan was 1.8s: the entire wait
of the 1W panel. The set of covered slots only ever GAINS members, so it is
now kept whole per source selection and topped up from the newest slots on
each call -- a range a few slots wide, milliseconds -- with a full rescan
every FULL_RESCAN to catch a backfill into an older slot (a Reddit
catch-up, a journal rebuild). Viewer-invariant, like the board memo: what
does not depend on who is asking can be shared.
"""
import datetime as dt
import threading

from extensions import db
from models import RadarBucketSource

from .config import expand_sources_for_history

# How much of the newest range every call re-reads. Wider than one slot on
# purpose: a bucket is written for a slot some minutes after the slot began,
# and ingest can run late.
TOPUP = dt.timedelta(minutes=30)
# How long an older slot's backfill can go unseen.
FULL_RESCAN = dt.timedelta(minutes=10)
# Selections are a handful; anything past this is old keys.
_MAX_ENTRIES = 16

_lock = threading.Lock()
_cache: dict = {}


def _clock():
    """Patched by tests; the TTLs are wall-clock, the ranges are the caller's."""
    return dt.datetime.utcnow()


def _scan(expanded, start, end):
    rows = (db.session.query(RadarBucketSource.bucket_start)
            .with_hint(RadarBucketSource,
                       'FORCE INDEX (ix_radar_bucket_sources_coverage)',
                       dialect_name='mysql')
            .filter(RadarBucketSource.source.in_(list(expanded)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < end,
                    RadarBucketSource.status.in_(('ok', 'truncated')))
            .distinct().all())
    return {bucket_start for (bucket_start,) in rows}


def covered_bucket_starts(sources, start, now):
    """Every bucket_start any of `sources` wrote in [start, now), ok or
    truncated. Returns a set of naive-UTC datetimes at bucket grain."""
    expanded = tuple(sorted(expand_sources_for_history(sources)))
    at = _clock()
    with _lock:
        entry = _cache.get(expanded)

    stale = entry is None or at >= entry['full_at'] + FULL_RESCAN
    if stale or start < entry['start']:
        # The whole range, widened to the earliest start ever asked, so a
        # 1W panel after a 4h board does not evict what the board built.
        base = start if entry is None else min(start, entry['start'])
        entry = {'slots': _scan(expanded, base, now), 'start': base,
                 'scanned_to': now, 'full_at': at}
    elif now > entry['scanned_to'] - TOPUP:
        fresh = _scan(expanded, entry['scanned_to'] - TOPUP, now)
        entry = {**entry, 'slots': entry['slots'] | fresh,
                 'scanned_to': max(entry['scanned_to'], now)}

    with _lock:
        _cache[expanded] = entry
        if len(_cache) > _MAX_ENTRIES:
            oldest = min(_cache, key=lambda k: _cache[k]['full_at'])
            del _cache[oldest]
    return {slot for slot in entry['slots'] if start <= slot < now}


def clear_memo():
    """Tests only."""
    with _lock:
        _cache.clear()
