# personal_apps/features/radar/profile.py
"""What a normal bucket looks like, per source.

Mention volume has a strong weekly shape. Comparing 03:00 on a Sunday against
15:00 on a Tuesday as though they were one population makes every weekday
afternoon look like a spike, which is most of what a naive z-score would report.

Built per source rather than market-wide, a deliberate departure from spec 6.1.
StockTwits follows US market hours, Bluesky is global and diurnal, /biz/ runs
around the clock. A shared profile would tell Bluesky to expect silence at
03:00 ET while half its users are awake, and every one of those buckets would
score as unusual.
"""
import collections
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource

from .config import BUCKET_MINUTES

BUCKETS_PER_WEEK = (7 * 24 * 60) // BUCKET_MINUTES      # 672

# Every bucket-of-week starts with this much pseudo-count before observations
# are added. A share of exactly zero makes `expected` zero, and any observation
# against a zero expectation is an infinite z -- so a single quiet hour in the
# sample window would manufacture a spike there forever. Smoothing is what
# stops "never seen" from meaning "impossible".
SMOOTHING = 1.0

DEFAULT_WEEKS = 8


def bucket_of_week(when):
    """0..671, counting 15-minute buckets from Monday 00:00 UTC."""
    minutes = (when.weekday() * 24 * 60) + (when.hour * 60) + when.minute
    return minutes // BUCKET_MINUTES


def build_profile(source, until, config_version, weeks=DEFAULT_WEEKS):
    """Share of this source's weekly volume falling in each bucket-of-week.

    Only `ok` buckets contribute. A `missing` bucket is a source that was down,
    not an hour that was quiet, and counting it would bend the profile towards
    silence at precisely the times ingest tends to fail. `truncated` is a known
    undercount and equally unusable as a description of normal.

    `config_version` is required, not optional: a bucket stamped under a
    different generation was aggregated from a different population (Task 3c
    -- rebuilding from the complete mention journal instead of one cursor
    slice changed measured volume even though the extractor's membership
    rules did not), and folding it into this sum would let understated
    pre-fix counts drag the expectation down right where corrected data is
    starting to arrive. There is no unversioned fallback mode; every caller
    scores against one exact generation or not at all.
    """
    since = until - dt.timedelta(weeks=weeks)

    rows = (db.session.query(RadarBucketSource.bucket_start,
                             sa.func.sum(RadarBucketSource.mention_count))
            .filter(RadarBucketSource.source == source,
                    RadarBucketSource.status == 'ok',
                    RadarBucketSource.source_config_version == config_version,
                    RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.bucket_start < until)
            .group_by(RadarBucketSource.bucket_start).all())

    weights = collections.defaultdict(float)
    for index in range(BUCKETS_PER_WEEK):
        weights[index] = SMOOTHING
    for bucket_start, total in rows:
        weights[bucket_of_week(bucket_start)] += float(total or 0)

    grand_total = sum(weights.values())
    return {index: weight / grand_total for index, weight in weights.items()}


def hour_share(profile, when):
    """This instant's share of a normal week for the profile's source."""
    return profile[bucket_of_week(when)]
