## Task 6: Backfill the buckets the old rollup truncated

**Files:**
- Create: `personal_apps/scripts/backfill_radar_buckets.py`
- Create: `personal_apps/tests/test_radar_backfill.py`

**Interfaces:**
- Consumes: `models.RadarBucketSource`, `RadarPost`, `RadarMention`.
- Produces: a one-shot script plus
  `repair(apply=False, ticker_prefix=None) -> dict`, callable by tests and by
  `main()`, no production imports elsewhere. `ticker_prefix` is a test-safety
  scope and is not exposed by the CLI.

The repair is partial by construction. `high` counts are exactly recoverable from `radar_posts` × `radar_mentions`; promoted `medium` mentions are not, because the events that created them were never written anywhere. The unrecoverable half is `low`-derived, and `low_count` is read by no surface.

- [ ] **Step 1: Write failing safety and repair tests**

Create `personal_apps/tests/test_radar_backfill.py` with namespaced `ZZBF...`
fixtures. Every call uses `ticker_prefix='ZZBF'`; tests run against the shared
real dev database and must never mutate ordinary seeded radar rows. Prove:

1. Dry-run reports an understated row but leaves every database field
   unchanged after the function returns.
2. Apply repairs an understated row from retained high mentions, converts SQL
   aggregate values before float arithmetic, clears all four score columns,
   preserves `status` and the old `source_config_version`, and a second apply
   is idempotent (`repaired == 0`). The partial backfill must never restamp a
   row as the current full-journal generation.
3. Equal `high_confidence_count` does not short-circuit a real lower-bound
   repair in `distinct_authors`, `distinct_text_ratio` or engagement. Retained
   posts can refresh author/text/engagement after the old bucket was written;
   equality of one count is not equality of the aggregate row.
4. A historical non-`ok` row with any one scoring column non-NULL loses all
   four columns on apply and stays untouched on dry-run. Do not key cleanup
   only on `mention_z`; a partially written score is still stale.

Watch each absence-shaped assertion fail against a targeted mutation before
restoring the implementation.

- [ ] **Step 2: Write the script**

Create `personal_apps/scripts/backfill_radar_buckets.py`:

```python
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
import sys

import sqlalchemy as sa

sys.path.insert(0, '.')

from app import app                                        # noqa: E402
from extensions import db                                  # noqa: E402
from models import RadarBucketSource                       # noqa: E402

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


def repair(apply=False, ticker_prefix=None):
    """Repair retained lower bounds; return integer report counters."""
    with app.app_context():
        rows = db.session.execute(_TRUTH).all()
        repaired = examined = 0

        for src, tk, bs, n_high, n_authors, n_hashes, engagement in rows:
            if ticker_prefix and not tk.startswith(ticker_prefix):
                continue
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
            if all(getattr(bucket, field) == value
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
        # mention_z written while they were `ok` and are ranked on it now that
        # they are `truncated` -- leaderboard filters on mention_z IS NOT NULL,
        # so the scorer's refusal to score them buys nothing until this runs.
        #
        # NULL, never 0: a zero z claims the bucket was exactly average, which
        # is a different fact from not having been scored.
        stale = (RadarBucketSource.query
                 .filter(RadarBucketSource.status != 'ok',
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
        print('%d rows carry a score they earned under a different status'
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
```

- [ ] **Step 3: Run the automated suite**

```bash
python -m pytest tests/test_radar_backfill.py -v
python -m pytest tests/ -k radar -q
```

- [ ] **Step 4: Dry-run it locally**

```bash
python -m scripts.backfill_radar_buckets
```

Expected: a line of the form `examined N bucket rows, M understated`, then `dry run -- nothing written`. On a local dev database with no radar data, `examined 0`.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/scripts/backfill_radar_buckets.py \
        personal_apps/tests/test_radar_backfill.py
git commit -m "feat(radar): a one-shot repair for buckets the old rollup truncated"
```

The production run happens after deploy, against the live database, and is Michi's call to trigger.

---

# Stage 2 - Sources that misrepresent themselves

Execution order inside this stage is Task 7, then Task 9, then Task 8. The
numbering is retained so existing reports and commit references remain stable.
Reddit's aggregate status is the wrong population; no truncated observation is
made scoreable until each subreddit owns its own status.

