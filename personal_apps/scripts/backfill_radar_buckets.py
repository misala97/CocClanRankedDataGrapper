"""Repair bucket counts the pre-2026-08-26 rollup truncated.

roll_up rebuilt each bucket from one cycle's cursor slice and overwrote, so a
quarter-hour touched by several cycles kept only the last one. Measured across
the live corpus: 14.1% of Bluesky's high-confidence mentions and 16.0% of
Reddit's never reached a bucket, rising to 42.9% on the 10+ mention buckets.

Also clears the scoring columns off rows that changed status after being
scored. Task 3 stopped roll_up producing those, but could not reach the 399
that already existed -- a closed quarter-hour is never touched again.

PARTIAL BY CONSTRUCTION. radar_mentions holds every mention of every STORED
post, which is exactly the `high` set. Promoted `medium` mentions came from
posts that were never stored -- the journal that would have kept them did not
exist -- so they cannot be recovered and mention_count stays understated by
that amount. low_count likewise. Neither is read by any surface.

Read-only until --apply. Run from personal_apps/:

    python -m scripts.backfill_radar_buckets            # report
    python -m scripts.backfill_radar_buckets --apply    # write
"""
import argparse
import datetime as dt
import math
import sys

import sqlalchemy as sa

sys.path.insert(0, '.')

from app import app                                        # noqa: E402
from extensions import db                                  # noqa: E402
from models import RadarBucketSource                       # noqa: E402
from features.radar import buckets                         # noqa: E402
from features.radar.config import (SCOREABLE_STATUSES,      # noqa: E402
                                   source_config_version)

_TRUTH = sa.text("""
    SELECT p.source AS src, m.ticker AS tk,
           DATE_ADD(DATE_FORMAT(p.created_utc, '%Y-%m-%d %H:00:00'),
                    INTERVAL FLOOR(MINUTE(p.created_utc)/15)*15 MINUTE) AS bs,
           COUNT(*) AS n_high,
           COUNT(DISTINCT p.author) AS n_authors,
           COUNT(DISTINCT p.simhash) AS n_hashes,
           SUM(p.score + p.num_comments) AS engagement
      FROM radar_mentions m
      JOIN radar_posts p ON p.id = m.post_id
     WHERE m.confidence = 'high'
     GROUP BY 1, 2, 3
""")

# distinct_text_ratio and engagement_weighted_count are MySQL FLOAT columns --
# 4-byte single precision, not the 8-byte double Python computes n_hashes /
# n_high in. A value like 2/3 is stored as the nearest float32 and reread as a
# double that no longer equals the freshly recomputed truth, so a strict `==`
# never short-circuits and every rerun "repairs" a row that has nothing left
# to fix. Confirmed against the real dev database: 2/3 round-trips through
# `distinct_text_ratio` as 0.6666666865348816, not 0.6666666666666666.
# rel_tol=1e-6 comfortably clears float32's ~1e-7 relative precision without
# masking a genuine difference (engagement_weighted_count is always a sum of
# integers, so this never matters there in practice, but the columns share a
# type and a rounding failure mode, so both get the tolerant compare).
_FLOAT_FIELDS = ('distinct_text_ratio', 'engagement_weighted_count')


def _unchanged(field, old, new):
    if field in _FLOAT_FIELDS:
        return math.isclose(old, new, rel_tol=1e-6, abs_tol=1e-9)
    return old == new


def repair(apply=False, ticker_prefix=None):
    """Repair retained lower bounds; return integer report counters.

    The whole transaction runs under the bucket writers' guard. The ORM
    autoflushes each row's mutation when the next row's lookup runs, so
    the writes happen throughout the loop, not at the commit -- and every
    one of them is a bucket write that a live rollup or a recovery must
    not interleave with. It is held for the run: this is a one-shot
    historical repair, run by hand and rarely.
    """
    with app.app_context(), buckets.bucket_write_guard():
        rows = db.session.execute(_TRUTH).all()
        repaired = examined = 0

        for src, tk, bs, n_high, n_authors, n_hashes, engagement in rows:
            if ticker_prefix and not tk.startswith(ticker_prefix):
                continue
            # sa.text() applies no DateTime type processor to a computed
            # DATE_ADD(...) expression, so bs comes back a str, not a
            # datetime, on this driver. MySQL 8 coerces the string implicitly
            # for the filter_by() comparison below, but that coercion is not
            # something this codebase can verify on MariaDB (production), so
            # make the conversion explicit instead of leaning on it. Tolerate
            # a driver that already hands back a real datetime.
            if isinstance(bs, str):
                bs = dt.datetime.strptime(bs, '%Y-%m-%d %H:%M:%S')
            bucket = RadarBucketSource.query.filter_by(
                ticker=tk, bucket_start=bs, source=src).one_or_none()
            if bucket is None:
                continue
            examined += 1
            # int() at the boundary: COUNT and SUM come back Decimal from both
            # MySQL and MariaDB, and Decimal against a float column is a
            # TypeError waiting for the first row that needs it.
            n_high = int(n_high)
            n_authors = int(n_authors)
            n_hashes = int(n_hashes)
            engagement = float(engagement or 0)
            candidate = {
                'high_confidence_count': max(
                    int(bucket.high_confidence_count), n_high),
                'mention_count': max(int(bucket.mention_count), n_high),
                'distinct_authors': max(int(bucket.distinct_authors),
                                        n_authors),
                'distinct_text_ratio': min(
                    float(bucket.distinct_text_ratio),
                    (n_hashes / n_high) if n_high else 1.0),
                'engagement_weighted_count': max(
                    float(bucket.engagement_weighted_count), engagement),
            }
            if all(_unchanged(field, getattr(bucket, field), value)
                   for field, value in candidate.items()):
                continue

            bucket.high_confidence_count = candidate['high_confidence_count']
            # mention_count stays >= high: the promoted mediums it also counted
            # are unrecoverable, so take whichever is larger rather than
            # overwriting a real figure with an incomplete one.
            bucket.mention_count = candidate['mention_count']
            bucket.distinct_authors = candidate['distinct_authors']
            bucket.distinct_text_ratio = candidate['distinct_text_ratio']
            bucket.engagement_weighted_count = candidate[
                'engagement_weighted_count']
            # The score was computed from the understated count. Keeping it
            # would make the repair cosmetic while the board continues to rank
            # on the old number. Task 3c also keeps this old rollup generation
            # out of current baselines; NULL is the honest state until a
            # compatible scorer can recompute it.
            bucket.expected = None
            bucket.variance = None
            bucket.mention_z = None
            bucket.baseline_days = None
            repaired += 1

        # The stale scores Task 3 stopped PRODUCING, which it could not
        # retroactively clear: roll_up only revisits a (ticker, bucket_start,
        # source) row when that window is touched again, and a closed
        # historical quarter-hour never is. 399 rows in production carry a
        # mention_z written under a status or source generation the final
        # scorer cannot vouch for. Current-generation `truncated` is scoreable;
        # missing/unrecognised statuses and old/NULL generations are not.
        #
        # NULL, never 0: a zero z claims the bucket was exactly average, which
        # is a different fact from not having been scored.
        current_version = source_config_version()
        stale = (RadarBucketSource.query
                 .filter(
                     sa.or_(
                         RadarBucketSource.status.is_(None),
                         ~RadarBucketSource.status.in_(SCOREABLE_STATUSES),
                         RadarBucketSource.source_config_version.is_(None),
                         RadarBucketSource.source_config_version !=
                         current_version),
                     sa.or_(RadarBucketSource.expected.isnot(None),
                            RadarBucketSource.variance.isnot(None),
                            RadarBucketSource.mention_z.isnot(None),
                            RadarBucketSource.baseline_days.isnot(None))))
        if ticker_prefix:
            stale = stale.filter(
                RadarBucketSource.ticker.like(ticker_prefix + '%'))
        stale_count = stale.count()
        if apply and stale_count:
            stale.update({'expected': None, 'variance': None,
                          'mention_z': None, 'baseline_days': None},
                         synchronize_session=False)

        print('examined %d bucket rows, %d understated' % (examined, repaired))
        print('%d rows carry a score outside the final status/generation policy'
              % stale_count)
        if apply:
            db.session.commit()
            print('written')
        else:
            db.session.rollback()
            print('dry run -- nothing written, pass --apply')
        return {'examined': int(examined), 'repaired': int(repaired),
                'stale_scores': int(stale_count)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true',
                        help='write the repaired counts')
    args = parser.parse_args()
    repair(apply=args.apply)


if __name__ == '__main__':
    main()
