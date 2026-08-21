# personal_apps/features/radar/scoring.py
"""Counts into surprise.

Reads radar_bucket_sources and writes expected, variance, mention_z and
baseline_days back onto the same rows. No prices here -- divergence and
no-print detection need a market feed and belong to Plan 3.

Per (ticker, source), never pooled before scoring: the sources have different
populations, rhythms and histories, and a ticker can be loud on one while
silent on another. Pooling happens at read time, over whichever sources the
viewer selected (spec 8.6).
"""
import collections
import datetime as dt

from extensions import db
from models import RadarBucketSource

from . import baselines, profile
from .config import VARIANCE_FLOOR, source_config_version

# Weight of the cold-start prior, in units of observed mass. 0.05 of a week is
# about eight hours: enough to dominate on day one and vanish by week two.
PRIOR_WEIGHT = 0.05


def _rows_by_ticker(source, since, until):
    rows = (RadarBucketSource.query
            .filter(RadarBucketSource.source == source,
                    RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.bucket_start < until)
            .all())

    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row.ticker].append(row)
    return grouped


def _observations(rows):
    return [baselines.Observation(r.bucket_start, r.mention_count, r.status,
                                  r.source_config_version)
            for r in rows]


def score_source(source, now, lookback_days=30, excluded=None):
    """Score every bucket of every ticker on one source. Returns rows written.

    `excluded` is the set of bucket starts to keep out of baselines, wired to
    open spikes in Plan 3 so a ticker that squeezed last week does not carry
    the squeeze into its own expectation.
    """
    excluded = excluded or set()
    since = now - dt.timedelta(days=lookback_days)
    version = source_config_version()

    prof = profile.build_profile(source, now)
    grouped = _rows_by_ticker(source, since, now)

    # The prior a thin ticker is pulled towards: what a typical ticker on this
    # source does. Spec 6.8 wants a segment median, which needs market cap and
    # therefore Plan 3; a global median is the same shape with a coarser peer
    # group.
    rates = []
    for rows in grouped.values():
        good = baselines.usable(_observations(rows), version, excluded)
        if good:
            rate, _ = baselines.weekly_rate(good, prof)
            rates.append(rate)
    prior_rate = sorted(rates)[len(rates) // 2] if rates else 0.0

    written = 0
    for rows in grouped.values():
        good = baselines.usable(_observations(rows), version, excluded)
        if not good:
            continue

        rate, _ = baselines.weekly_rate(good, prof, prior_rate=prior_rate,
                                        prior_weight=PRIOR_WEIGHT)
        k = baselines.dispersion(good, prof, rate)
        span = max(o.bucket_start for o in good) - min(o.bucket_start for o in good)
        baseline_days = span.days

        for row in rows:
            # A source that was down, or a known undercount, has nothing to be
            # surprised about. Scoring it would invent a reading from a gap.
            if row.status != 'ok':
                continue

            expected = baselines.expected_for(rate, prof, row.bucket_start)
            variance = baselines.variance_for(expected, k)
            row.expected = expected
            row.variance = variance
            row.mention_z = ((row.mention_count - expected)
                             / max(variance, VARIANCE_FLOOR) ** 0.5)
            row.baseline_days = baseline_days
            written += 1

    db.session.commit()
    return written
