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
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource

from . import baselines, profile
from .config import (ELEVATED_Z, MIN_DISTINCT_AUTHORS, MIN_DISTINCT_CHANNELS,
                     MIN_DISTINCT_TEXT_RATIO, MIN_MENTIONS,
                     SUSTAINED_HOURS_CONSIDERED, SUSTAINED_HOURS_REQUIRED,
                     VARIANCE_FLOOR, source_config_version)

# Weight of the cold-start prior, in units of observed mass. 0.05 of a week is
# about eight hours: enough to dominate on day one and vanish by week two.
PRIOR_WEIGHT = 0.05


def _rows_by_ticker(source, since, until, config_version):
    """Every row a ticker may be scored or baselined from, THIS generation only.

    Filtered here rather than trusted to baselines.usable() downstream: usable()
    only screens what feeds the RATE estimate, but the write loop below scores
    every `ok` row it is handed. Without this filter, a ticker straddling a
    generation boundary -- some current rows plus an old-generation row that
    invalidate_incompatible_scores has not yet reached -- would have the old
    row overwritten with a freshly computed z from the CURRENT baseline, which
    disguises it as current data while its own source_config_version still
    says otherwise.
    """
    rows = (RadarBucketSource.query
            .filter(RadarBucketSource.source == source,
                    RadarBucketSource.source_config_version == config_version,
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


def invalidate_incompatible_scores(version, since, source=None):
    """Clear expected/variance/mention_z/baseline_days from rows this
    generation cannot vouch for. Returns rows cleared.

    Two ways a row is incompatible: an explicit different stamp, or SQL NULL
    -- a row scored before source_config_version existed, or one a bootstrap
    recovered without yet being restamped. `!= version` alone does not match
    NULL in SQL (NULL compares unequal to everything, including itself), so
    it is tested for explicitly rather than trusted to fall out of the
    inequality.

    Restricted to rows carrying at least one non-NULL score column so a row
    that was never scored -- already the honest absence this whole change
    protects -- is not written to for no reason.
    """
    query = RadarBucketSource.query.filter(
        RadarBucketSource.bucket_start >= since,
        sa.or_(RadarBucketSource.source_config_version.is_(None),
               RadarBucketSource.source_config_version != version),
        sa.or_(RadarBucketSource.expected.isnot(None),
               RadarBucketSource.variance.isnot(None),
               RadarBucketSource.mention_z.isnot(None),
               RadarBucketSource.baseline_days.isnot(None)))
    if source is not None:
        query = query.filter(RadarBucketSource.source == source)
    return query.update({'expected': None, 'variance': None, 'mention_z': None,
                         'baseline_days': None}, synchronize_session=False)


def score_source(source, now, lookback_days=30, excluded=None):
    """Score every bucket of every ticker on one source. Returns rows written.

    `excluded` is the set of bucket starts to keep out of baselines, wired to
    open spikes in Plan 3 so a ticker that squeezed last week does not carry
    the squeeze into its own expectation.
    """
    excluded = excluded or set()
    since = now - dt.timedelta(days=lookback_days)
    version = source_config_version()

    # Defensive, not the primary defence: startup already clears the
    # migration overlap window once (run_radar_ingest._prepare_rollup_
    # generation). This is the steady-state backstop for whatever that
    # window does not reach -- scoped to lookback_days rather than a full
    # history scan, because _rows_by_ticker's own version filter already
    # keeps an uncleared old row out of the ticker-level loop below; this
    # only stops it sitting there forever still LOOKING scored to anything
    # that reads the column directly (spec: leaderboard ranks on mention_z
    # IS NOT NULL).
    invalidate_incompatible_scores(version, since, source=source)

    prof = profile.build_profile(source, now, version)
    grouped = _rows_by_ticker(source, since, now, version)

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


def pooled_z(ticker, bucket_start, sources):
    """Combined z over the selected sources. Returns (z, contributing count).

    Sums the components rather than averaging the z-scores, because a weighted
    mean of z-scores is not a z-score (spec 6.2). Two sources each two sigma
    over is stronger evidence than either alone; averaging reports the same two
    sigma and throws the corroboration away.

    A source with no scored row for this bucket -- down, or truncated -- drops
    out of all three sums rather than contributing zero.
    """
    rows = (RadarBucketSource.query
            .filter(RadarBucketSource.ticker == ticker,
                    RadarBucketSource.bucket_start == bucket_start,
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.mention_z.isnot(None))
            .all())
    if not rows:
        return None, 0

    observed = sum(r.mention_count for r in rows)
    expected = sum(r.expected for r in rows)
    variance = sum(r.variance for r in rows)

    return (observed - expected) / max(variance, VARIANCE_FLOOR) ** 0.5, len(rows)


@dataclasses.dataclass
class Contribution:
    """What one kind of venue contributed to a ticker in a window.

    `voices` is deliberately not called `authors`. It is whatever counts as an
    independent voice for that kind -- distinct authors on a forum, distinct
    channels on a broadcast network -- and naming it after the forum case is
    what made the gate untranslatable in the first place.
    """
    mentions: int
    voices: int
    text_ratio: float


# Independent voices each kind needs. An unknown kind gets the forum floor,
# which is the stricter of the two.
_VOICE_FLOOR = {
    'forum': MIN_DISTINCT_AUTHORS,
    'broadcast': MIN_DISTINCT_CHANNELS,
}


def is_eligible(contributions):
    """Whether a reading is worth ranking at all.

    `contributions` maps source kind to Contribution. A ticker is eligible if
    ANY kind clears its own gate -- a union, not an intersection. A ticker
    carried by three Bluesky authors qualifies on the forum gate with no
    broadcast traffic at all; one carried by two Telegram channels qualifies
    on the broadcast gate even though its author count is two.

    Three gates per kind, because each is blind to what the others catch: raw
    volume means nothing at low counts, one determined voice can supply any
    volume, and fifty voices pasting one message defeat the voice gate
    completely. Volume and distinct wording are universal; only what counts as
    a voice differs.
    """
    return any(
        part.mentions >= MIN_MENTIONS
        and part.voices >= _VOICE_FLOOR.get(kind, MIN_DISTINCT_AUTHORS)
        and part.text_ratio >= MIN_DISTINCT_TEXT_RATIO
        for kind, part in contributions.items())


def window_z(ticker, sources, end, hours):
    """Pooled z over a time window. Returns (z, component parts).

    Components are summed across both time and sources for the same reason
    pooled_z sums them: the sum of independent counts has the sum of their
    expectations and variances, and no other combination is a z-score.
    """
    start = end - dt.timedelta(hours=hours)
    rows = (RadarBucketSource.query
            .filter(RadarBucketSource.ticker == ticker,
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < end,
                    RadarBucketSource.mention_z.isnot(None))
            .all())
    if not rows:
        return None, {}

    parts = {
        'mentions': sum(r.mention_count for r in rows),
        'expected': sum(r.expected for r in rows),
        'variance': sum(r.variance for r in rows),
        'authors': max((r.distinct_authors for r in rows), default=0),
        'text_ratio': min((r.distinct_text_ratio for r in rows), default=1.0),
        'buckets': len(rows),
    }
    z = ((parts['mentions'] - parts['expected'])
         / max(parts['variance'], VARIANCE_FLOOR) ** 0.5)
    return z, parts


def is_sustained(ticker, sources, end):
    """Elevated across most of the last four separate hours.

    Not "elevated in the 1h, 4h and 24h windows" -- those are nested, so one
    loud hour lifts all three and their agreement means nothing. Consecutive
    non-overlapping hours are independent evidence (spec 6.9).
    """
    elevated = 0
    for step in range(SUSTAINED_HOURS_CONSIDERED):
        z, _ = window_z(ticker, sources, end - dt.timedelta(hours=step), hours=1)
        if z is not None and z >= ELEVATED_Z:
            elevated += 1
    return elevated >= SUSTAINED_HOURS_REQUIRED
