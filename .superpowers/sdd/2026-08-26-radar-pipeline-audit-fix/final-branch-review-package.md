# Final branch review package: b9c8ef8..3782dd5 (code only, SDD docs excluded)

## Commits
```
200bde3 test(radar): pin the retention cutoff boundary
6f1afa8 feat(radar): prune the journal past its retention window
6d098e7 fix(radar): the discovery script yields to the running daemon
d7fc03d fix(radar): a baseline measured in hours reads like one
5ba81e1 docs(radar): the tone pass costs six times what the docstring claimed
bc42187 fix(radar): provisional now means a thin baseline, not every row
c9a4840 feat(radar): show where the model and the word list disagree
9629a86 fix(radar): the panel's tone bar reads the verdicts it has been paying for
d5997c9 fix(radar): account for breadth exclusions and extract once
e4de0b5 fix(radar): an outage mid-window is a gap in the chart, not quiet
8a23a26 fix(radar): an unpriced model reads as unknown, not as free
af11f2c fix(radar): an unread feed reports no rate rather than a rate of zero
aee4e2f fix(radar): rank truncated buckets instead of discarding ninety percent of reddit
cc2d278 fix(radar): keep historical Reddit visible and stop zero-count root rows
dedc90b feat(radar): give every subreddit its own source identity
3b74f32 test(radar): pin healthy empty source results
945c9d7 fix(radar): retire StockTwits, which Cloudflare has refused since launch
8b0a07d test(radar): pin backfill stale-score scoping and datetime coercion
d11ccb5 feat(radar): a one-shot repair for buckets the old rollup truncated
ee24d65 docs(radar): close config cleanup and pin backfill safety
c6ff071 fix(radar): wire source cashtag policy and remove page cap
48c5246 docs(radar): close generation review and harden backfill plan
fa66e70 test(radar): isolate scoring cleanup sentinels
4850c9a test(radar): scope shared scoring cleanup
c553c47 test(radar): pin generation invalidation safeguards
7791963 fix(radar): start corrected rollups as a new baseline generation
```

## Stat
```
 .../plans/2026-08-26-radar-pipeline-audit-fix.md   | 118 +++++---
 personal_apps/features/radar/board.py              |  30 +-
 personal_apps/features/radar/buckets.py            |  29 +-
 personal_apps/features/radar/config.py             | 167 ++++++++---
 personal_apps/features/radar/detail.py             |  52 ++--
 personal_apps/features/radar/detail_panel.py       |  90 +++++-
 personal_apps/features/radar/ingest.py             |  55 +++-
 personal_apps/features/radar/journal.py            |  52 +++-
 personal_apps/features/radar/leaderboard.py        |  52 +++-
 personal_apps/features/radar/llm_sentiment.py      |  18 +-
 personal_apps/features/radar/phrasing.py           |  18 +-
 personal_apps/features/radar/profile.py            |  14 +-
 personal_apps/features/radar/retention.py          |  43 ++-
 personal_apps/features/radar/routes/api.py         |  37 ++-
 personal_apps/features/radar/scheduling.py         |  20 +-
 personal_apps/features/radar/scoring.py            | 100 ++++++-
 personal_apps/features/radar/sources/__init__.py   |  21 ++
 personal_apps/features/radar/sources/reddit.py     |  25 +-
 personal_apps/features/radar/sources/stocktwits.py | 138 ----------
 personal_apps/features/radar/spend.py              |  32 ++-
 .../08316d3e4d77_widen_radar_source_columns.py     |  91 ++++++
 ...677_widen_radar_bucket_sources_baseline_days.py |  38 +++
 personal_apps/models.py                            |  16 +-
 personal_apps/run_radar_ingest.py                  | 171 +++++++-----
 personal_apps/scripts/backfill_radar_buckets.py    | 183 +++++++++++++
 personal_apps/scripts/discover_reddit_sources.py   |  38 ++-
 .../static/radar/src/board/BoardPage.test.tsx      |  10 +-
 .../static/radar/src/detail/Breakdown.tsx          |  10 +
 personal_apps/static/radar/src/format.test.ts      |  17 ++
 personal_apps/static/radar/src/format.ts           |  21 +-
 personal_apps/static/radar/src/list/ListPane.tsx   |  18 +-
 personal_apps/static/radar/src/list/Spend.test.tsx |  26 +-
 personal_apps/static/radar/src/list/Spend.tsx      |   9 +-
 personal_apps/static/radar/src/list/marks.test.tsx |  29 ++
 personal_apps/static/radar/src/types.ts            |   8 +-
 personal_apps/tests/test_radar_api.py              | 160 +++++++++++
 personal_apps/tests/test_radar_backfill.py         | 246 +++++++++++++++++
 personal_apps/tests/test_radar_board.py            | 171 ++++++++++++
 personal_apps/tests/test_radar_bucket_sources.py   |  12 +-
 personal_apps/tests/test_radar_buckets.py          |  39 ++-
 personal_apps/tests/test_radar_config.py           | 114 +++++++-
 personal_apps/tests/test_radar_daemon.py           | 282 +++++++++++++++----
 personal_apps/tests/test_radar_detail.py           | 181 +++++++++++-
 personal_apps/tests/test_radar_discovery.py        |  95 +++++++
 personal_apps/tests/test_radar_ingest.py           | 305 +++++++++++++++++----
 personal_apps/tests/test_radar_journal.py          | 153 ++++++++++-
 personal_apps/tests/test_radar_leaderboard.py      |  47 +++-
 personal_apps/tests/test_radar_llm_sentiment.py    |   6 +-
 personal_apps/tests/test_radar_phrasing.py         |  38 ++-
 personal_apps/tests/test_radar_profile.py          |  64 +++--
 personal_apps/tests/test_radar_reddit.py           |  88 +++++-
 personal_apps/tests/test_radar_retention.py        |  67 +++++
 personal_apps/tests/test_radar_scheduling.py       |   5 +-
 personal_apps/tests/test_radar_scoring.py          | 299 +++++++++++++++++---
 personal_apps/tests/test_radar_spend.py            |  45 ++-
 personal_apps/tests/test_radar_stocktwits.py       | 178 ------------
 56 files changed, 3587 insertions(+), 804 deletions(-)
```

## Diff
```diff
diff --git a/docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md b/docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md
index ae6e85c..2622c91 100644
--- a/docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md
+++ b/docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md
@@ -1348,28 +1348,56 @@ python -m pytest tests/test_radar_daemon.py \
 git add personal_apps/features/radar/config.py personal_apps/tests/test_radar_config.py
 git commit -m "fix(radar): delete the superseded page-cap config"
 ```
 
 ---
 
 ## Task 6: Backfill the buckets the old rollup truncated
 
 **Files:**
 - Create: `personal_apps/scripts/backfill_radar_buckets.py`
+- Create: `personal_apps/tests/test_radar_backfill.py`
 
 **Interfaces:**
 - Consumes: `models.RadarBucketSource`, `RadarPost`, `RadarMention`.
-- Produces: a one-shot script, run manually, no imports elsewhere.
+- Produces: a one-shot script plus
+  `repair(apply=False, ticker_prefix=None) -> dict`, callable by tests and by
+  `main()`, no production imports elsewhere. `ticker_prefix` is a test-safety
+  scope and is not exposed by the CLI.
 
 The repair is partial by construction. `high` counts are exactly recoverable from `radar_posts` × `radar_mentions`; promoted `medium` mentions are not, because the events that created them were never written anywhere. The unrecoverable half is `low`-derived, and `low_count` is read by no surface.
 
-- [ ] **Step 1: Write the script**
+- [ ] **Step 1: Write failing safety and repair tests**
+
+Create `personal_apps/tests/test_radar_backfill.py` with namespaced `ZZBF...`
+fixtures. Every call uses `ticker_prefix='ZZBF'`; tests run against the shared
+real dev database and must never mutate ordinary seeded radar rows. Prove:
+
+1. Dry-run reports an understated row but leaves every database field
+   unchanged after the function returns.
+2. Apply repairs an understated row from retained high mentions, converts SQL
+   aggregate values before float arithmetic, clears all four score columns,
+   preserves `status` and the old `source_config_version`, and a second apply
+   is idempotent (`repaired == 0`). The partial backfill must never restamp a
+   row as the current full-journal generation.
+3. Equal `high_confidence_count` does not short-circuit a real lower-bound
+   repair in `distinct_authors`, `distinct_text_ratio` or engagement. Retained
+   posts can refresh author/text/engagement after the old bucket was written;
+   equality of one count is not equality of the aggregate row.
+4. A historical non-`ok` row with any one scoring column non-NULL loses all
+   four columns on apply and stays untouched on dry-run. Do not key cleanup
+   only on `mention_z`; a partially written score is still stale.
+
+Watch each absence-shaped assertion fail against a targeted mutation before
+restoring the implementation.
+
+- [ ] **Step 2: Write the script**
 
 Create `personal_apps/scripts/backfill_radar_buckets.py`:
 
 ```python
 """Repair bucket counts the pre-2026-08-26 rollup truncated.
 
 roll_up rebuilt each bucket from one cycle's cursor slice and overwrote, so a
 quarter-hour touched by several cycles kept only the last one. Measured across
 the live corpus: 14.1% of Bluesky's high-confidence mentions and 16.0% of
 Reddit's never reached a bucket, rising to 42.9% on the 10+ mention buckets.
@@ -1393,77 +1421,81 @@ import argparse
 import sys
 
 import sqlalchemy as sa
 
 sys.path.insert(0, '.')
 
 from app import app                                        # noqa: E402
 from extensions import db                                  # noqa: E402
 from models import RadarBucketSource                       # noqa: E402
 
-# The 15-minute floor, in SQL. MariaDB and MySQL agree on this form; DATE_FORMAT
-# to the hour and then add the quarter, rather than arithmetic on a UNIX
-# timestamp, which loses the fractional-second precision the column carries.
-_BUCKET = sa.text(
-    "DATE_ADD(DATE_FORMAT(p.created_utc, '%Y-%m-%d %H:00:00'),"
-    " INTERVAL FLOOR(MINUTE(p.created_utc)/15)*15 MINUTE)")
-
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
 
 
-def main():
-    parser = argparse.ArgumentParser()
-    parser.add_argument('--apply', action='store_true',
-                        help='write the repaired counts')
-    args = parser.parse_args()
-
+def repair(apply=False, ticker_prefix=None):
+    """Repair retained lower bounds; return integer report counters."""
     with app.app_context():
         rows = db.session.execute(_TRUTH).all()
         repaired = examined = 0
 
         for src, tk, bs, n_high, n_authors, n_hashes, engagement in rows:
+            if ticker_prefix and not tk.startswith(ticker_prefix):
+                continue
             bucket = RadarBucketSource.query.filter_by(
                 ticker=tk, bucket_start=bs, source=src).one_or_none()
             if bucket is None:
                 continue
             examined += 1
             # int() at the boundary: COUNT and SUM come back Decimal from both
             # MySQL and MariaDB, and Decimal against a float column is a
             # TypeError waiting for the first row that needs it.
             n_high = int(n_high)
-            if bucket.high_confidence_count >= n_high:
+            n_authors = int(n_authors)
+            n_hashes = int(n_hashes)
+            engagement = float(engagement or 0)
+            candidate = {
+                'high_confidence_count': max(
+                    int(bucket.high_confidence_count), n_high),
+                'mention_count': max(int(bucket.mention_count), n_high),
+                'distinct_authors': max(int(bucket.distinct_authors),
+                                        n_authors),
+                'distinct_text_ratio': min(
+                    float(bucket.distinct_text_ratio),
+                    (n_hashes / n_high) if n_high else 1.0),
+                'engagement_weighted_count': max(
+                    float(bucket.engagement_weighted_count), engagement),
+            }
+            if all(getattr(bucket, field) == value
+                   for field, value in candidate.items()):
                 continue
 
-            bucket.high_confidence_count = n_high
+            bucket.high_confidence_count = candidate['high_confidence_count']
             # mention_count stays >= high: the promoted mediums it also counted
             # are unrecoverable, so take whichever is larger rather than
             # overwriting a real figure with an incomplete one.
-            bucket.mention_count = max(int(bucket.mention_count), n_high)
-            bucket.distinct_authors = max(int(bucket.distinct_authors),
-                                          int(n_authors))
-            bucket.distinct_text_ratio = min(
-                float(bucket.distinct_text_ratio),
-                (int(n_hashes) / n_high) if n_high else 1.0)
-            bucket.engagement_weighted_count = max(
-                float(bucket.engagement_weighted_count), float(engagement or 0))
+            bucket.mention_count = candidate['mention_count']
+            bucket.distinct_authors = candidate['distinct_authors']
+            bucket.distinct_text_ratio = candidate['distinct_text_ratio']
+            bucket.engagement_weighted_count = candidate[
+                'engagement_weighted_count']
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
@@ -1473,54 +1505,78 @@ def main():
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
-                         RadarBucketSource.mention_z.isnot(None)))
+                         sa.or_(RadarBucketSource.expected.isnot(None),
+                                RadarBucketSource.variance.isnot(None),
+                                RadarBucketSource.mention_z.isnot(None),
+                                RadarBucketSource.baseline_days.isnot(None))))
+        if ticker_prefix:
+            stale = stale.filter(
+                RadarBucketSource.ticker.like(ticker_prefix + '%'))
         stale_count = stale.count()
-        if args.apply and stale_count:
+        if apply and stale_count:
             stale.update({'expected': None, 'variance': None,
                           'mention_z': None, 'baseline_days': None},
                          synchronize_session=False)
 
         print('examined %d bucket rows, %d understated' % (examined, repaired))
         print('%d rows carry a score they earned under a different status'
               % stale_count)
-        if args.apply:
+        if apply:
             db.session.commit()
             print('written')
         else:
             db.session.rollback()
             print('dry run -- nothing written, pass --apply')
+        return {'examined': int(examined), 'repaired': int(repaired),
+                'stale_scores': int(stale_count)}
+
+
+def main():
+    parser = argparse.ArgumentParser()
+    parser.add_argument('--apply', action='store_true',
+                        help='write the repaired counts')
+    args = parser.parse_args()
+    repair(apply=args.apply)
 
 
 if __name__ == '__main__':
     main()
 ```
 
-- [ ] **Step 2: Dry-run it locally**
+- [ ] **Step 3: Run the automated suite**
+
+```bash
+python -m pytest tests/test_radar_backfill.py -v
+python -m pytest tests/ -k radar -q
+```
+
+- [ ] **Step 4: Dry-run it locally**
 
 ```bash
 python -m scripts.backfill_radar_buckets
 ```
 
 Expected: a line of the form `examined N bucket rows, M understated`, then `dry run -- nothing written`. On a local dev database with no radar data, `examined 0`.
 
-- [ ] **Step 3: Commit**
+- [ ] **Step 5: Commit**
 
 ```bash
-git add personal_apps/scripts/backfill_radar_buckets.py
+git add personal_apps/scripts/backfill_radar_buckets.py \
+        personal_apps/tests/test_radar_backfill.py
 git commit -m "feat(radar): a one-shot repair for buckets the old rollup truncated"
 ```
 
 The production run happens after deploy, against the live database, and is Michi's call to trigger.
 
 ---
 
 # Stage 2 - Sources that misrepresent themselves
 
 Execution order inside this stage is Task 7, then Task 9, then Task 8. The
diff --git a/personal_apps/features/radar/board.py b/personal_apps/features/radar/board.py
index d2a43fa..8fc4380 100644
--- a/personal_apps/features/radar/board.py
+++ b/personal_apps/features/radar/board.py
@@ -25,21 +25,22 @@ different clothes -- an absence is not a zero:
 import collections
 import dataclasses
 import datetime as dt
 
 import sqlalchemy as sa
 
 from extensions import db
 from models import RadarBucketSource, RadarMention, RadarPost, RadarQuote
 
 from . import leaderboard, market_calendar, phrasing
-from .config import SEGMENT_GROUPS, VARIANCE_FLOOR, segments_in
+from .config import (SEGMENT_GROUPS, VARIANCE_FLOOR, expand_sources,
+                     expand_sources_for_history, segments_in)
 
 # The windows the triplet reports, shortest first. Fixed rather than derived
 # from the selected window: the point of the triplet is that all three are
 # always visible together, so "building" and "fading" can be told apart at a
 # glance instead of by switching the window control and remembering.
 TRIPLET_HOURS = (1, 4, 24)
 
 # How much history the sparkline and the lead charts draw.
 SERIES_HOURS = 24
 
@@ -117,34 +118,36 @@ def _hour_floor(when):
 
 
 def _covered_hours(sources, since, now):
     """Hours in which any bucket at all was written for these sources.
 
     The proxy for "ingest was alive". It is a proxy and not a record: a genuine
     board-wide silence reads the same as a stopped daemon. Both resolve to
     "not measured", which is the honest half of the ambiguity -- the dishonest
     half would be drawing a zero.
     """
+    sources = expand_sources_for_history(sources)
     rows = (db.session.query(RadarBucketSource.bucket_start)
             .filter(RadarBucketSource.source.in_(list(sources)),
                     RadarBucketSource.bucket_start >= since,
                     RadarBucketSource.bucket_start < now,
                     RadarBucketSource.status.in_(('ok', 'truncated')))
             .distinct().all())
     return {_hour_floor(start) for (start,) in rows}
 
 
 def _hourly_counts(tickers, sources, since, now):
     """Pooled mention count per (ticker, hour)."""
     if not tickers:
         return {}
 
+    sources = expand_sources_for_history(sources)
     rows = (db.session.query(RadarBucketSource.ticker,
                              RadarBucketSource.bucket_start,
                              RadarBucketSource.mention_count)
             .filter(RadarBucketSource.ticker.in_(list(tickers)),
                     RadarBucketSource.source.in_(list(sources)),
                     RadarBucketSource.bucket_start >= since,
                     RadarBucketSource.bucket_start < now)
             .all())
 
     totals = collections.defaultdict(int)
@@ -170,20 +173,24 @@ def _series_for(ticker, totals, covered, since, now):
 def _triplets(tickers, sources, now):
     """mention_z at each triplet window, per ticker.
 
     One query over the longest window, sliced in Python. Three queries would
     read the same rows three times, and the longest window contains the other
     two by construction.
     """
     if not tickers:
         return {}
 
+    # STRICT: every figure below comes off `expected` and `variance`, which
+    # are relative to a baseline. The pre-split root `reddit` rows were
+    # baselined against a different population and may not enter a z.
+    sources = expand_sources(sources)
     longest = max(TRIPLET_HOURS)
     rows = (db.session.query(RadarBucketSource.ticker,
                              RadarBucketSource.bucket_start,
                              RadarBucketSource.mention_count,
                              RadarBucketSource.expected,
                              RadarBucketSource.variance)
             .filter(RadarBucketSource.ticker.in_(list(tickers)),
                     RadarBucketSource.source.in_(list(sources)),
                     RadarBucketSource.bucket_start >= now - dt.timedelta(hours=longest),
                     RadarBucketSource.bucket_start < now,
@@ -215,20 +222,21 @@ def _triplets(tickers, sources, now):
 def _tones(tickers, sources, since, now):
     """Bullish / neutral / bearish mention counts per ticker.
 
     Counted from the mention rows rather than derived from the stored bucket
     mean, for the reason in the module docstring: a mean cannot tell a balanced
     argument apart from a room that used no sentiment words at all.
     """
     if not tickers:
         return {}
 
+    sources = expand_sources_for_history(sources)
     # A model verdict outranks the word list on the same post, and a NULL
     # verdict falls back to it rather than counting as toneless. The lexicon
     # is forty words with a negation window: it reads "great, another green
     # day" after a crash as bullish, which is exactly the case spec 6.11
     # specified a re-read for. Verdicts arrive on a scheduled pass, so most
     # rows carry none at any given moment and the fallback is the normal path,
     # not the exception.
     #
     # `unclear` deliberately votes neither way AND blocks the lexicon from
     # voting: it means the post named the ticker without saying anything about
@@ -259,48 +267,64 @@ def _tones(tickers, sources, since, now):
         bullish, bearish = int(bullish or 0), int(bearish or 0)
         out[ticker] = Tone(bullish=bullish, bearish=bearish,
                            neutral=max(0, int(total) - bullish - bearish))
     return out
 
 
 def build(sources, now, window_hours=4, segments=(), limit=50,
           leads=LEAD_COUNT, min_venues=1):
     """The whole board.
 
+    `sources` is the viewer's SELECTION, root-level (`reddit`) or concrete
+    (`reddit:pennystocks`) -- not an expanded list. Each query below expands
+    it for itself, because the two expansions differ: see config.expand_sources
+    and config.expand_sources_for_history.
+
     Segment counts are taken before the segment filter, because the counts
     label the filter's own buttons -- computing them after it would report the
     selected segment's size in every slot.
     """
     session = market_calendar.session_state(now.replace(tzinfo=dt.timezone.utc))
     ranking = leaderboard.build_rows(sources, now, window_hours=window_hours,
                                      segments=(), limit=None, session=session)
     ranked = ranking.rows
 
     counts = collections.Counter(row.segment for row in ranked)
     segment_counts = dict(counts)
     segment_counts['all'] = len(ranked)
     segment_counts['small'] = sum(
         1 for row in ranked if row.segment in SEGMENT_GROUPS['small'])
 
     # Both venue counts come from the same unfiltered pass, for the reason the
     # segment counts do: they label the control, and counting after the filter
     # would report the filtered size in every slot.
+    #
+    # A VENUE IS A ROOT. `row.sources` is concrete, so two subreddits are two
+    # names -- but they are one platform, one user population and one
+    # rate-limit budget. The breadth control's whole claim is that a second
+    # venue is INDEPENDENT corroboration, and r/wallstreetbets agreeing with
+    # r/pennystocks is not that. `row.venues` is the rooted count.
     venue_counts = {
         'any': len(ranked),
-        'multi': sum(1 for row in ranked if len(row.sources) > 1),
+        'multi': sum(1 for row in ranked if row.venues > 1),
     }
 
     allowed = segments_in(segments)
     if allowed:
         ranked = [row for row in ranked if row.segment in allowed]
     if min_venues > 1:
-        ranked = [row for row in ranked if len(row.sources) >= min_venues]
+        kept = [row for row in ranked if row.venues >= min_venues]
+        removed = len(ranked) - len(kept)
+        if removed:
+            ranking.excluded['one_venue'] = (
+                ranking.excluded.get('one_venue', 0) + removed)
+        ranked = kept
     ranked = ranked[:limit]
 
     tickers = [row.ticker for row in ranked]
     since = now - dt.timedelta(hours=SERIES_HOURS)
 
     covered = _covered_hours(sources, since, now)
     totals = _hourly_counts(tickers, sources, since, now)
     triplets = _triplets(tickers, sources, now)
     tones = _tones(tickers, sources, since, now)
 
diff --git a/personal_apps/features/radar/buckets.py b/personal_apps/features/radar/buckets.py
index 6e6ba2c..1210213 100644
--- a/personal_apps/features/radar/buckets.py
+++ b/personal_apps/features/radar/buckets.py
@@ -13,21 +13,21 @@ rollup would inflate every bucket that spans two cycles.
 """
 import collections
 import dataclasses
 import datetime as dt
 import statistics
 
 from extensions import db
 from models import RadarBucket, RadarBucketSource
 
 from .config import (BUCKET_MINUTES, MAX_BARE_PER_VOUCHER,
-                     source_config_version)
+                     source_config_version, source_root)
 # Safe at the top because journal.py imports this module as `buckets` rather
 # than pulling MentionRow/bucket_start_for by name -- neither side touches an
 # attribute of the other until a function actually runs, so it no longer
 # matters which of the two a caller imports first. Verified all three orders
 # (`import buckets`, `import journal`, `import ingest`) after this change;
 # see the review that added this note for the command output.
 from . import journal
 
 # Statuses whose counts are real enough to store. `missing` is not one:
 # see the module docstring. There is deliberately no list of source names --
@@ -139,21 +139,29 @@ def roll_up(rows, statuses, touched):
     source names is open -- nothing here knows or cares which they are.
 
     Returns the number of bucket rows written.
     """
     countable = {source for source, status in statuses.items()
                  if status in _COUNTABLE}
     if not countable:
         return 0
 
     version = source_config_version()
-    sources_ok = sum(1 for status in statuses.values() if status == 'ok')
+    # Distinct ROOTS, not names. "How many sources were ok" is a count of
+    # venues, and eight subreddits reporting ok is Reddit reporting ok once --
+    # counting the names would make this rise and fall with
+    # REDDIT_SUBS_PER_CYCLE, which is a budget rather than a fact about
+    # coverage. Nothing outside tests reads the column yet; the point is that
+    # whatever starts reading it reads the same unit it always meant.
+    sources_ok = len({source_root(source)
+                      for source, status in statuses.items()
+                      if status == 'ok'})
 
     usable = [r for r in rows if r.source in countable]
 
     # Store first, then rebuild from EVERYTHING in these windows -- not from
     # `usable`, which is one cycle's cursor slice. A bucket is recomputed from
     # scratch on every pass, which is right because cycles overlap and additive
     # rollup would double-count the boundary; it is only correct if the
     # recompute sees the whole quarter-hour. It did not, and production lost
     # 42.9% of its 10+ mention buckets to that (audit 2026-08-26).
     journal.record(usable)
@@ -196,29 +204,44 @@ def roll_up(rows, statuses, touched):
             by_source[row.source].append(row)
 
         for source in countable:
             per = _summarize(by_source.get(source, []))
             child = RadarBucketSource.query.filter_by(
                 ticker=ticker, bucket_start=start, source=source).one_or_none()
             if child is None:
                 child = RadarBucketSource(ticker=ticker, bucket_start=start,
                                           source=source)
                 db.session.add(child)
+            # Read before this loop restamps the column below -- otherwise
+            # the comparison always reads current-against-current and a
+            # generation change could never be seen. A fresh row's version is
+            # Python None, which the `!=` below already treats as a mismatch.
+            previous_version = child.source_config_version
             for field, value in per.items():
                 setattr(child, field, value)
             child.status = statuses[source]
+            # Two independent reasons a stored score stops being trustworthy,
+            # cleared the same way:
+            #
             # scoring.score_source refuses any row that is not `ok`, so a row
             # leaving `ok` must lose the score it was given while it was one.
             # It kept it, and leaderboard ranks on mention_z IS NOT NULL --
             # 399 rows in production were being ranked on a z the scorer would
             # no longer compute for them (audit 2026-08-26).
-            if child.status != 'ok':
+            #
+            # A row whose generation is NULL or differs from the one about to
+            # be stamped was counted under a different aggregation -- Task 3c,
+            # generation 2 rebuilds from the complete journal where generation
+            # 1 rebuilt from one cursor slice. Restamping it to the current
+            # version without clearing first would disguise an old-population
+            # score as a current one, regardless of the row's status.
+            if child.status != 'ok' or previous_version != version:
                 child.expected = None
                 child.variance = None
                 child.mention_z = None
                 child.baseline_days = None
             child.source_config_version = version
 
         written += 1
 
     db.session.commit()
     return written
diff --git a/personal_apps/features/radar/config.py b/personal_apps/features/radar/config.py
index fdf1972..0f65257 100644
--- a/personal_apps/features/radar/config.py
+++ b/personal_apps/features/radar/config.py
@@ -7,57 +7,56 @@ stamped onto every bucket. Baselines are computed only over buckets sharing the
 current version, so adding a source starts a warm-up instead of reading
 straight through the discontinuity (spec 6.6).
 """
 import datetime as dt
 import hashlib
 import json
 import re
 
 # Active sources. Adding one is a module in sources/ plus an entry here --
 # nothing else in the pipeline names a source (spec 8.6).
-SOURCES = ('stocktwits', 'bluesky', 'fourchan', 'reddit')
+SOURCES = ('bluesky', 'fourchan', 'reddit')
 
 # Whether a bare uppercase token may be read as a ticker on a given source.
 #
 # Measured on live data with the same extractor: StockTwits' top mentions were
 # MRNA, DJT, AVGO, IOVA -- all real. Bluesky's were IA (Iowa), GOP (the party),
 # AP (the news agency) and BTC (the coin) -- all real tickers, none of them
 # about stocks. The difference is the population, not the code. Where everyone
 # is discussing markets, MRNA means Moderna; on a general network almost nobody
 # is, and three-letter words mean what they usually mean.
 #
 # Corroboration cannot rescue this. GOP's ETF is named "Subversive
 # Congressional Republicans Trading", so a political post corroborates it
 # perfectly, and thirty different people said "IA", so the distinct-author gate
 # passes too.
 #
 # Sources absent from this mapping default to cashtag-only, which is the safe
 # direction for a source nobody has characterised yet.
 BARE_TOKENS_ALLOWED = {
-    'stocktwits': True,    # finance-only by construction
     'fourchan': True,      # /biz/ is a finance board
     # Was False, set after the first live pass found IA (Iowa), GOP and AP
     # among the top bare tokens. Re-enabled 2026-08-23: an uncorroborated bare
     # token is stored `low` and never scored, so the junk that measurement
     # found now costs a row in a table and nothing on the board. What it buys
     # is the promotion path -- a distinctive company name in the same post, or
     # a different author cashtagging the same ticker in the same bucket --
     # which needs many independent authors and is therefore exactly this
     # source. Verified on Telegram, where channels whose bare tokens were RSI,
     # ROE, DMA and GROW produced zero high-confidence hits.
     #
     # See scripts/measure_bare_tokens.py. Revert if the top twenty scored
     # tickers stop looking like equities.
     'bluesky': True,
-    # A finance subreddit is finance-native the way /biz/ and StockTwits are:
-    # `AAPL` without a dollar sign is a ticker there in a way it is not on a
-    # general network. Measured 2026-08-24, the junk this admits is the same
+    # A finance subreddit is finance-native the way /biz/ is: `AAPL` without a
+    # dollar sign is a ticker there in a way it is not on a general network.
+    # Measured 2026-08-24, the junk this admits is the same
     # shape as elsewhere -- WTF and NATO topped r/StockMarket, OI and CC
     # topped r/options -- and lands as `low`, counted but never scored.
     'reddit': True,
 }
 
 
 # Ticker symbols that are also well-known crypto coins. The listed company is
 # genuinely not crypto -- BCH is Banco de Chile, LINK is Interlink Electronics,
 # ATOM is Atomera -- so the name-based crypto filter cannot see them, and
 # deleting them from the universe would cost real coverage.
@@ -71,64 +70,85 @@ BARE_TOKENS_ALLOWED = {
 # per-source judgement bare tokens already get.
 COIN_COLLISION_SYMBOLS = frozenset({
     'BCH', 'LTC', 'LINK', 'ATOM', 'DOT', 'ADA', 'SOL', 'XMR', 'TRX', 'ALGO',
     'ICP', 'FIL', 'APT', 'ARB', 'OP', 'INJ', 'SUI', 'SEI', 'TIA', 'NEAR',
     'HBAR', 'VET', 'EOS', 'XLM', 'ETC', 'XTZ', 'AAVE', 'MKR', 'SNX', 'CRV',
     'RUNE', 'FTM', 'GRT', 'IMX', 'LDO', 'STX', 'KAS', 'TON', 'PEPE', 'SHIB',
     'DOGE', 'BNB', 'AVAX', 'MATIC', 'UNI', 'CAKE', 'RNDR', 'JUP', 'WIF',
 })
 
 # Sources where a coin-shaped symbol should be read as the coin, not the
-# company. Finance-native populations are the exception.
+# company. Finance-native populations are the exception -- and since StockTwits
+# was retired 2026-08-26 there are none, so every symbol in
+# COIN_COLLISION_SYMBOLS is now dropped on every live source. That costs 49
+# real tickers their mentions, which is the price of not putting Chainlink
+# chatter under Interlink Electronics.
+#
+# Kept as a map rather than collapsed to a constant: Telegram is the next
+# source and will need its own entry, and the extension point is the point.
 COIN_SYMBOLS_MEAN_STOCKS = {
-    'stocktwits': True,
     'fourchan': False,     # /biz/ is crypto culture first
     'bluesky': False,
 }
 
 
 # What kind of venue each source is, which decides how its independent voices
 # get counted.
 #
 # The author gate is a proxy for one question -- how many independent voices
 # are saying this. On a forum that is distinct authors. On a BROADCAST network
 # one admin posts and thousands read, so every bucket has exactly one author
 # and the author gate can never be cleared however loud the ticker is. There
 # the independent unit is the CHANNEL: three channels carrying the same symbol
 # is corroboration, one channel posting it forty times is not.
 SOURCE_KIND = {
-    'stocktwits': 'forum',
     'bluesky': 'forum',
     'fourchan': 'forum',
     # Comments carry real distinct authors, so the forum gate applies
     # unchanged -- unlike a broadcast channel, where one admin is every voice.
     'reddit': 'forum',
 }
 
 
+def source_root(source):
+    """The policy-bearing part of a source name.
+
+    Reddit carries its subreddit -- `reddit:wallstreetbets` -- so that one
+    sub's feed rolling over between polls marks its own buckets truncated and
+    not every other sub's. Before 2026-08-26 they shared one name and one
+    status, and with REDDIT_SUBS_PER_CYCLE = 1 that meant whichever sub the
+    cycle happened to read decided the status of all of them. In production
+    that was 4372 truncated rows against 478 ok.
+
+    The policy must NOT split with the name. An unlisted sub inherits Reddit's
+    judgements rather than falling through to the strict default, which would
+    silently disable bare tokens on a source that has nothing else.
+    """
+    return source.split(':', 1)[0]
+
+
 def source_kind(source):
     """'forum' or 'broadcast'. Unknown sources are treated as forums.
 
     The strict direction: forum is the tighter gate, so a source nobody has
     characterised is judged by the harder standard rather than waved through.
     """
-    return SOURCE_KIND.get(source, 'forum')
+    return SOURCE_KIND.get(source_root(source), 'forum')
 
 
 # Single-letter cashtags. `$M`, `$B`, `$T` and `$K` are money shorthand far
 # more often than Macy's, Barnes Group, AT&T and Kellanova -- measured on live
 # Bluesky, 119 of 3302 cashtag matches were single letters and essentially all
 # of them were prose: "Tax @60% for over a $M", "make $B's", "is $B & can be
 # $T if we all do it". A finance-native population is the exception, the same
 # judgement bare tokens and coin collisions already get.
 SINGLE_LETTER_CASHTAGS = {
-    'stocktwits': True,
     'fourchan': False,
     'bluesky': False,
 }
 
 # Automated feeds, not people. A machine restating a template every few
 # seconds is ONE publisher however many tickers it names, so it is dropped
 # whole rather than symbol by symbol -- and per-symbol rules would have to
 # enumerate a list that changes weekly.
 #
 # Crypto exchange bots, prolific on general networks:
@@ -239,40 +259,40 @@ POOLED_VEHICLE_PATTERN = (
 # `republicans` it is evidence the post does not concern the fund.
 #
 # Funds remain reachable by cashtag, which scores directly. A person typing
 # the dollar sign means the fund.
 FUNDS_PROMOTE_BARE_TOKENS = False
 
 
 def looks_like_bot_feed(text):
     """True for machine-generated crypto exchange output.
 
-    Applied on every source. These bots do not post to StockTwits, so the rule
-    costs nothing there, and scoping it per source would only invite the
-    question of which sources are safe.
+    Applied on every source. A source these bots never touch pays nothing for
+    the check, and scoping it per source would only invite the question of
+    which sources are safe.
     """
     return bool(_BOT_FEED_RE.search(text or ''))
 
 
 def single_letter_cashtags_allowed(source):
-    return SINGLE_LETTER_CASHTAGS.get(source, False)
+    return SINGLE_LETTER_CASHTAGS.get(source_root(source), False)
 
 
 def coin_collision_dropped(source, symbol):
     """True when this symbol should be ignored on this source."""
-    if COIN_SYMBOLS_MEAN_STOCKS.get(source, False):
+    if COIN_SYMBOLS_MEAN_STOCKS.get(source_root(source), False):
         return False
     return symbol in COIN_COLLISION_SYMBOLS
 
 
 def bare_tokens_allowed(source):
-    return BARE_TOKENS_ALLOWED.get(source, False)
+    return BARE_TOKENS_ALLOWED.get(source_root(source), False)
 
 
 # What an UNCORROBORATED bare token is worth, per source. Measured 2026-08-25
 # by sampling what the extractor actually threw away, live, on each source:
 #
 #   bluesky   0 of 25 discards were real tickers. CNH is a Brazilian driving
 #             licence, HQ is comics, EU is the Portuguese word "I".
 #   reddit   14 of 15 were real -- NVDA three times, plus AIXI, AMST, APRE,
 #             CAST, CODX, DKS, GITS, GPUS, INHD, OLOX, SWVL. The one miss was
 #             GPT, in a sentence about Claude and ChatGPT.
@@ -283,21 +303,21 @@ def bare_tokens_allowed(source):
 # essentially never fires. The rule was discarding an entire source.
 #
 # `low` is the default on purpose: a new source has to opt in, or a general
 # network quietly inherits a stock forum's rules.
 BARE_TOKEN_CONFIDENCE = {
     'reddit': 'high',
 }
 
 
 def bare_token_confidence(source):
-    return BARE_TOKEN_CONFIDENCE.get(source, 'low')
+    return BARE_TOKEN_CONFIDENCE.get(source_root(source), 'low')
 
 # Subreddits to read, from
 # docs/superpowers/specs/2026-08-24-radar-subreddit-source-list.md. Tier 1 and
 # Tier 2 together, on Michi's call 2026-08-24: measure everything for a few
 # days from real stored data, then prune. The alternative was 25-comment
 # snapshots, which were too small a sample to decide on -- r/stocks measured
 # zero ticker density across 93 comments an hour, which is sampling noise
 # rather than truth.
 #
 # Regional subs are deliberately absent and must stay absent: TSX-V, NSE and
@@ -341,20 +361,94 @@ def bare_token_confidence(source):
 #
 # Hashed into source_config_version, so this starts a baseline warm-up. And
 # note run_radar_ingest retires the dropped subs' poll state -- due_symbols
 # filters by source rather than by this list, so without that they would keep
 # taking turns forever and the cut would be a silent no-op.
 REDDIT_SUBS = (
     'wallstreetbets', 'pennystocks', 'shortsqueeze', 'thetagang',
     'options', 'smallstreetbets', 'swingtrading', 'weedstocks',
 )
 
+
+# TWO expansions exist, and merging them back into one is a data-loss bug in
+# either direction. Read this before "simplifying" them.
+#
+# Before 2026-08-26 every Reddit observation was stored under the bare name
+# `reddit`. Since the split it is stored under `reddit:<sub>`, and that older
+# history is still sitting in radar_bucket_sources, radar_posts and
+# radar_mention_events -- buckets are retained forever, which is what lets the
+# detail chart's 1Y and 3Y spans fill in.
+#
+# Those old rows are readable for what they COUNTED and unreadable for what
+# they SCORED:
+#
+#   - a mention_count is a raw observation. `reddit` counted 40 mentions in an
+#     hour and `reddit:wallstreetbets` counted 12 in another; pooling them is
+#     addition, and leaving the older half out draws Reddit's real, still
+#     stored contribution as absent -- while Bluesky satisfies the same hour's
+#     coverage test, so the gap renders as a measured number rather than as a
+#     gap. That is an absence presented as a zero, which is the one thing this
+#     surface may never do.
+#
+#   - an expected/variance/mention_z is relative to a BASELINE, and the old
+#     rows carry the previous source_config_version. "All of Reddit" and
+#     "r/pennystocks" are different populations; admitting the old stamp to a
+#     scored read mixes two baselines into one z. That is what the stamp bump
+#     exists to prevent.
+#
+# So: `expand_sources` for anything that reads a score, and
+# `expand_sources_for_history` for anything that reads a count, a status or a
+# timestamp. Neither is a superset that can stand in for the other.
+
+
+def expand_sources(names):
+    """Concrete stored source names for a root-level selection.
+
+    STRICT -- this generation's names only. `reddit` means every configured
+    subreddit, because that is what the UI chip and the daemon source list
+    promise; a concrete subreddit stays concrete; and the pre-split root
+    `reddit` is deliberately NOT included, because rows written under it were
+    baselined against a different population.
+
+    For scored reads and for scoring itself: leaderboard.build_rows,
+    board._triplets, detail_panel.window_figures, scoring.pooled_z /
+    window_z, run_radar_ingest.score_all.
+    """
+    out = []
+    for name in names:
+        if name == 'reddit':
+            out.extend('reddit:%s' % sub for sub in REDDIT_SUBS)
+        else:
+            out.append(name)
+    return out
+
+
+def expand_sources_for_history(names):
+    """`expand_sources` plus the pre-split root name it deliberately drops.
+
+    For raw-count reads, which have no baseline dependency and so may see the
+    whole of what was actually observed: board._covered_hours / _hourly_counts
+    / _tones, detail.daily_counts / intraday_counts / first_watched_day /
+    _watched_from_index, detail_panel.breakdown_for / _posts,
+    journal.distinct_voices.
+
+    Only for a ROOT selection. A reader who asked for one subreddit gets that
+    subreddit, and the undifferentiated pre-split history is not it.
+    """
+    out = expand_sources(names)
+    if 'reddit' in names:
+        # Appended, not prepended: the order of an IN (...) list is
+        # irrelevant to the query and this keeps the strict expansion's
+        # ordering stable for anything that compares the two.
+        out.append('reddit')
+    return out
+
 # Feeds read per cycle. The cycle is three minutes at the fastest cadence, so
 # four is roughly one request every forty-five seconds -- deliberately below
 # the rate that earned a sustained 429 during measurement. Eighteen subs
 # therefore come round about every fourteen minutes, which is honest rather
 # than complete: r/wallstreetbets turns its 25-entry feed over in under two
 # minutes, so most of its comments will be missed and its buckets will say
 # `truncated`. Raise this only after watching for 429s in the daemon log.
 # One, because one is the entire budget. Measured against the live endpoint
 # on the VPS 2026-08-25: `x-ratelimit-remaining` reads 0.0 after a single
 # request, and successes landed at t=0, t=78 and t=198 seconds against
@@ -372,22 +466,22 @@ REDDIT_SUBS_PER_CYCLE = 1
 # The ingest cycle stretches to 1800s overnight because chatter follows the
 # session -- which is right for the sources it was built for and wrong here.
 # Measured 2026-08-24: four subs per 30-minute cycle meant a full rotation of
 # eighteen took over two hours, and r/wallstreetbets turns its 25-entry feed
 # over in under two minutes. Six hours of that produced ONE scorable mention.
 #
 # Reddit does not stop at the closing bell, and what a slow poll misses is
 # gone rather than late -- there is no cursor to catch up from.
 REDDIT_INTERVAL_SECONDS = 120  # ~1 feed/window, matching the measured budget
 
-# Bounds for this source's adaptive cadence. The scheduler's defaults are
-# StockTwits-shaped (15 min to 4 h) and its floor alone would lose most of
+# Bounds for this source's adaptive cadence. The scheduler's module defaults
+# (15 min to 4 h) do not fit here, and the floor alone would lose most of
 # r/wallstreetbets. The floor is what a busy sub gets; the ceiling is where a
 # silent one -- or a throttled one -- ends up.
 REDDIT_MIN_POLL = dt.timedelta(seconds=90)
 # Six hours, raised from 45 minutes on 2026-08-25.
 #
 # The ceiling was starving the subreddits that matter. Measured live: two
 # hours produced 179 mentions across 92 tickers and exactly ONE bucket cleared
 # the eligibility floor. interval_for_rate already sizes each interval so the
 # 25-entry feed cannot roll over, but clamping the result at 45 minutes meant
 # a subreddit producing 0.07 comments an hour was polled 1.33 times an hour --
@@ -395,33 +489,24 @@ REDDIT_MIN_POLL = dt.timedelta(seconds=90)
 # 1.8 minutes to keep up, fought seventeen near-dead subreddits for the same
 # thirty feeds an hour.
 #
 # Safe because SAFETY_FACTOR is 0.5, so a sub is pinned here only when its
 # rate is below 12.5/6 = 2.08 comments an hour -- and at that rate its feed
 # takes twelve hours to fill, twice the interval. Nothing pinned can lose a
 # comment. Subs above it are unaffected: r/stocks at 67/hour asks for eleven
 # minutes and gets eleven minutes, ceiling or no ceiling.
 REDDIT_MAX_POLL = dt.timedelta(hours=6)
 
-# StockTwits publishes no rate-limit headers and twenty consecutive requests
-# drew no 429, so this is a conservative budget rather than a documented
-# ceiling. The daemon backs off on 429 regardless.
-STOCKTWITS_REQUESTS_PER_HOUR = 150
-
 # 15-minute grain. Fine enough for the 1h window in spec 6.9, coarse enough
 # that a forever-retained table stays small.
 BUCKET_MINUTES = 15
 
-# Pages to walk per channel per cycle before giving up and
-# marking the affected buckets `truncated` (spec 4.3).
-PAGE_CAP = 10
-
 POST_RETENTION_DAYS = 30
 
 # How long the mention journal is kept. Buckets are the durable artifact; the
 # journal exists only so a bucket can be rebuilt while cycles are still
 # arriving in it. Two days is generous against a catch-up after an outage --
 # what it must outlast is the deepest cursor rewind, not the retention of
 # anything the board reads.
 MENTION_EVENT_RETENTION_HOURS = 48
 
 # How long a price snapshot is worth keeping. The longest window the board or
@@ -523,20 +608,32 @@ STOPWORDS = frozenset({
 #
 # Four, and expressed as a ratio rather than a fixed number: ten people
 # cashtagging in one quarter-hour is a real conversation and should carry more
 # bare mentions than one person can, so a flat cap would throttle exactly the
 # busy windows the board exists to surface. Over the ratio the promotion is
 # refused outright rather than truncated to the first N, because choosing
 # WHICH four to promote has no principled answer and the excess is itself the
 # evidence that a common word has collided with a ticker.
 MAX_BARE_PER_VOUCHER = 4
 
+# Counts written by generation 1 were rebuilt from one cursor slice and lost
+# up to 42.9% of the busiest buckets. Generation 2 rebuilds from the complete
+# mention journal. This is hashed because the two populations are not valid
+# inputs to one baseline, even though the extractor admitted the same symbols.
+ROLLUP_GENERATION = 2
+
+# Generation 1 stored every subreddit under the aggregate name `reddit`.
+# Generation 2 makes the subreddit part of the durable source name. The
+# configured roots and subreddit membership stay unchanged across that split,
+# so neither existing hash input can express this population discontinuity.
+SOURCE_NAME_GENERATION = 2
+
 
 def source_config_version():
     """A stable 16-char stamp for everything that decides what gets counted.
 
     Sorted before hashing so reordering a list is not a config change -- only
     membership is. Stamped onto every bucket; baselines are computed only over
     buckets sharing the current stamp, so a change starts a warm-up instead of
     reading straight through a discontinuity (spec 6.6).
 
     THE EXTRACTION RULES ARE PART OF THIS, and were not until 2026-08-22. The
@@ -560,34 +657,40 @@ def source_config_version():
         'bare_confidence': dict(sorted(BARE_TOKEN_CONFIDENCE.items())),
         'single_letter': dict(sorted(SINGLE_LETTER_CASHTAGS.items())),
         'coin_symbols': sorted(COIN_COLLISION_SYMBOLS),
         'coin_means_stocks': dict(sorted(COIN_SYMBOLS_MEAN_STOCKS.items())),
         'stopwords': sorted(STOPWORDS),
         'cashtag_re': CASHTAG_PATTERN,
         'bare_re': BARE_PATTERN,
         'bot_re': _BOT_FEED_RE.pattern,
         'name_df': [MAX_NAME_TOKEN_DF, MAX_NAME_TOKEN_RATIO,
                     MIN_NAME_TOKEN_LEN],
-        # Every subreddit shares the source name `reddit`, so adding or
-        # dropping one changes which mentions are counted under it while the
-        # source list stays identical. Exactly the false assurance the
-        # extraction rules gave before 2026-08-22.
+        # Adding or dropping a subreddit changes the set of concrete Reddit
+        # populations while the root source list stays identical.
         'reddit_subs': sorted(REDDIT_SUBS),
+        # The same roots and subreddits can still produce a different stored
+        # population when the source-name scheme changes.
+        'source_name_generation': SOURCE_NAME_GENERATION,
         'pooled_re': POOLED_VEHICLE_PATTERN,
         # The PATTERN alone was not enough: this flag changes what the same
         # pattern is used FOR, so flipping it changed which mentions were
         # counted while leaving the stamp identical.
         'fund_tokens': FUNDS_PROMOTE_BARE_TOKENS,
         # Corroboration decides which bare mentions become scored, so retuning
         # the ceiling mixes populations judged under two different rules
         # inside one baseline unless the stamp moves with it.
         'bare_per_voucher': MAX_BARE_PER_VOUCHER,
+        # Not an extraction rule -- the extractor admits the same symbols
+        # either way. What changed is how completely a bucket's count is
+        # aggregated (audit 2026-08-26), and that is exactly as valid a
+        # reason to start a new baseline as a membership change is.
+        'rollup_generation': ROLLUP_GENERATION,
     }, separators=(',', ':'), sort_keys=True)
     return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
 
 
 # Negative-binomial dispersion bounds. variance = mu + mu**2 / k, so a large k
 # approaches Poisson and a small k allows heavy bursting.
 #
 # The UPPER bound is the one doing work. Dispersion is estimated over buckets
 # that exclude known spikes, which makes the sample look calmer than the world
 # is and biases k upward -- and a k that is too high shrinks the variance,
diff --git a/personal_apps/features/radar/detail.py b/personal_apps/features/radar/detail.py
index b4444e0..95b0e70 100644
--- a/personal_apps/features/radar/detail.py
+++ b/personal_apps/features/radar/detail.py
@@ -11,20 +11,22 @@ closes, so carrying the chart per row would have a twenty-row board shipping
 sixteen thousand numbers in order to draw twenty sparklines.
 """
 import dataclasses
 import datetime as dt
 
 import sqlalchemy as sa
 
 from extensions import db
 from models import RadarBucketSource, RadarQuote
 
+from .config import expand_sources_for_history
+
 # Calendar days per span, not trading days: the arrays are indexed by calendar
 # day so price and chatter stay aligned through weekends and holidays. A year
 # holds ~252 trading days and 365 calendar ones, and indexing each by its own
 # position would drift them apart by over a hundred days.
 SPAN_DAYS = {'1M': 30, '6M': 182, '1Y': 365, '3Y': 1095}
 
 # Spans measured in minutes rather than days, as (slots, minutes_per_slot).
 #
 # These CANNOT be entries in SPAN_DAYS. That chart is indexed by calendar day,
 # so a one-day span is a single point and a week is seven -- a chart with
@@ -72,25 +74,28 @@ class Chart:
     # minutes from days on its own -- without this it labels a 24-hour chart
     # with month names.
     step_minutes: int = 1440
 
 
 def daily_counts(tickers, sources, start, now):
     """Pooled mention count per (ticker, calendar day).
 
     From buckets, which are retained forever -- unlike posts, which prune at
     30 days. That is what lets the chart's long spans fill in over time with
-    no new collection.
+    no new collection. Which is exactly why this expands FOR HISTORY: a 1Y
+    span reaches back well past the 2026-08-26 subreddit split, and Reddit's
+    contribution before it is stored under the bare name `reddit`.
     """
     if not tickers:
         return {}
 
+    sources = expand_sources_for_history(sources)
     rows = (db.session.query(RadarBucketSource.ticker,
                              sa.func.date(RadarBucketSource.bucket_start),
                              sa.func.sum(RadarBucketSource.mention_count))
             .filter(RadarBucketSource.ticker.in_(list(tickers)),
                     RadarBucketSource.source.in_(list(sources)),
                     RadarBucketSource.bucket_start >= start,
                     RadarBucketSource.bucket_start < now)
             .group_by(RadarBucketSource.ticker,
                       sa.func.date(RadarBucketSource.bucket_start)).all())
 
@@ -100,20 +105,21 @@ def daily_counts(tickers, sources, start, now):
         # return a string. Normalise rather than trusting the driver.
         if isinstance(day, str):
             day = dt.date.fromisoformat(day)
         totals[(ticker, day)] = int(count or 0)
     return totals
 
 
 def first_watched_day(sources, start, now):
     """Earliest calendar day any bucket exists for. Before it, chatter is
     unknown rather than zero."""
+    sources = expand_sources_for_history(sources)
     earliest = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
                 .filter(RadarBucketSource.source.in_(list(sources)),
                         RadarBucketSource.bucket_start >= start).scalar())
     return earliest.date() if earliest else None
 
 
 def chart_for(ticker, start, days, closes_by_day, counts, watched_from):
     """One Chart, both arrays indexed by calendar day from `start`."""
     closes, chatter = [], []
     for offset in range(days):
@@ -164,70 +170,78 @@ def intraday_prices(ticker, start, now, step_minutes, slots):
             prices[index] = float(price)
     return prices
 
 
 def intraday_counts(ticker, sources, start, now, step_minutes, slots):
     """Mentions per slot, and the first slot anything was observed in.
 
     Returns (counts, first_seen_index). Buckets are 15 minutes; a 1W slot is
     an hour, so four of them pool into one and must add rather than overwrite.
     """
+    sources = expand_sources_for_history(sources)
     rows = (db.session.query(RadarBucketSource.bucket_start,
                              sa.func.sum(RadarBucketSource.mention_count))
             .filter(RadarBucketSource.ticker == ticker,
                     RadarBucketSource.source.in_(list(sources)),
                     RadarBucketSource.bucket_start >= start,
                     RadarBucketSource.bucket_start < now)
             .group_by(RadarBucketSource.bucket_start).all())
 
     counts = [0] * slots
     seen = None
     for bucket_start, total in rows:
         index = _slot_index(bucket_start, start, step_minutes, slots)
         if index is None:
             continue
         counts[index] += int(total or 0)
         seen = index if seen is None else min(seen, index)
     return counts, seen
 
 
-def _watched_from_index(sources, start, now, step_minutes, slots):
-    """First slot ANY ticker was observed in.
+def watched_slots(sources, start, now, step_minutes, slots):
+    """Slots in which any bucket was written for the selected sources.
 
-    Per source rather than per ticker, exactly like first_watched_day: the
-    question is when we were watching, not when this symbol was mentioned.
+    This is the same coverage proxy board._covered_hours uses. A quiet source
+    is therefore zero only in a slot we observed; an interior ingest outage is
+    unknown rather than a fabricated run of quiet chatter.
     """
-    earliest = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
-                .filter(RadarBucketSource.source.in_(list(sources)),
-                        RadarBucketSource.bucket_start >= start,
-                        RadarBucketSource.bucket_start < now).scalar())
-    if earliest is None:
-        return None
-    return _slot_index(earliest, start, step_minutes, slots)
+    sources = expand_sources_for_history(sources)
+    rows = (db.session.query(RadarBucketSource.bucket_start)
+            .filter(RadarBucketSource.source.in_(list(sources)),
+                    RadarBucketSource.bucket_start >= start,
+                    RadarBucketSource.bucket_start < now,
+                    RadarBucketSource.status.in_(('ok', 'truncated')))
+            .distinct().all())
+    covered = set()
+    for (bucket_start,) in rows:
+        index = _slot_index(bucket_start, start, step_minutes, slots)
+        if index is not None:
+            covered.add(index)
+    return covered
 
 
 def intraday_chart_for(ticker, sources, now, span):
     """One Chart over slots of minutes rather than calendar days.
 
     Same array shape as the daily chart on purpose: the renderer draws evenly
     spaced slots and does not need to know what a slot means, beyond
     `step_minutes` for its axis labels.
     """
     slots, step_minutes = INTRADAY_SPANS[span]
     start = now - dt.timedelta(minutes=slots * step_minutes)
 
     closes = intraday_prices(ticker, start, now, step_minutes, slots)
     counts, _seen = intraday_counts(ticker, sources, start, now,
                                     step_minutes, slots)
-    watched = _watched_from_index(sources, start, now, step_minutes, slots)
+    covered = watched_slots(sources, start, now, step_minutes, slots)
 
     chatter = []
     for index in range(slots):
-        # A slot before observation began is unknown, not silent. Same rule
-        # the daily chart follows, and the reason chatter is nullable at all.
-        chatter.append(None if watched is None or index < watched
-                       else counts[index])
+        chatter.append(counts[index] if index in covered else None)
+
+    first_watched = min(covered) if covered else None
 
     return Chart(start=start, closes=closes, chatter=chatter,
-                 watched_from=(start + dt.timedelta(minutes=watched * step_minutes)
-                               if watched is not None else None),
+                 watched_from=(start + dt.timedelta(
+                     minutes=first_watched * step_minutes)
+                               if first_watched is not None else None),
                  step_minutes=step_minutes)
diff --git a/personal_apps/features/radar/detail_panel.py b/personal_apps/features/radar/detail_panel.py
index d53f98e..db24bba 100644
--- a/personal_apps/features/radar/detail_panel.py
+++ b/personal_apps/features/radar/detail_panel.py
@@ -13,21 +13,22 @@ import datetime as dt
 
 import sqlalchemy as sa
 
 from extensions import db
 from models import (RadarBucketSource, RadarMention, RadarPost, RadarQuote,
                     TickerUniverse)
 
 from . import detail as chart_mod
 from . import history, market_calendar, universe
 from . import quotes as quotes_mod
-from .config import source_kind
+from .config import (expand_sources, expand_sources_for_history, source_kind,
+                     source_root)
 
 # How many posts the panel shows. Enough to form an opinion, few enough to
 # read; the count of the rest sits beside them.
 POST_LIMIT = 25
 
 
 @dataclasses.dataclass
 class Venue:
     source: str
     mentions: int
@@ -39,20 +40,24 @@ class Breakdown:
     """The chatter, taken apart.
 
     `top_author_share` is the pump tell, and the reason this section exists at
     all: one account posting forty times reads as forty mentions everywhere
     else on the surface, and no other figure the board computes exposes it.
     """
     venues: list
     bullish: int
     neutral: int
     bearish: int
+    # How often the word list and the model read the same post the opposite
+    # way. Both scores are kept precisely so this is answerable -- a
+    # disagreement is the sarcasm the lexicon alone cannot see.
+    disagreements: int
     top_author_share: float | None
     top_two_share: float | None
     peak_hour: dt.datetime | None
     peak_count: int
     first_seen: dt.date | None
     mentions: int
     voices: int
 
 
 @dataclasses.dataclass
@@ -70,107 +75,166 @@ class Detail:
     span: str
     chart: object
     breakdown: Breakdown
     posts: list
     post_total: int
     # The window figures the written read needs. Carried here rather than
     # recomputed by the serializer, so the panel and the row phrase describe
     # the same numbers.
     mentions: int
     expected: float
-    baseline_days: int | None
+    baseline_days: float | None
 
 
 def window_figures(ticker, sources, since, now):
     """Mentions, expected and baseline age across the scoring window.
 
     Read from buckets rather than taken from a leaderboard row, because the
     panel is reachable for a ticker the board filtered out -- and refusing to
     describe one because it did not rank is the wrong answer to "tell me about
     this".
+
+    STRICT expansion, unlike the breakdown below: `expected` and
+    `baseline_days` are baseline-relative, and the written read quotes
+    `mentions` against `expected` in the same sentence. Pooling a pre-split
+    root count into an expectation computed for the post-split population
+    would compare two different populations' numbers to each other.
     """
+    sources = expand_sources(sources)
     rows = (db.session.query(RadarBucketSource.mention_count,
                              RadarBucketSource.expected,
                              RadarBucketSource.baseline_days)
             .filter(RadarBucketSource.ticker == ticker,
                     RadarBucketSource.source.in_(list(sources)),
                     RadarBucketSource.bucket_start >= since,
                     RadarBucketSource.bucket_start < now).all())
     mentions = sum(row[0] for row in rows)
     expected = sum(row[1] or 0.0 for row in rows)
     ages = [row[2] for row in rows if row[2] is not None]
     return mentions, expected, (min(ages) if ages else None)
 
 
 def _posts(ticker, sources, since, now):
     """The newest posts, and how many there were in all."""
+    sources = expand_sources_for_history(sources)
     base = (db.session.query(RadarPost)
             .join(RadarMention, RadarMention.post_id == RadarPost.id)
             .filter(RadarMention.ticker == ticker,
                     RadarPost.source.in_(list(sources)),
                     RadarPost.created_utc >= since,
                     RadarPost.created_utc < now,
                     RadarMention.confidence.in_(('high', 'medium'))))
     rows = base.order_by(RadarPost.created_utc.desc()).limit(POST_LIMIT).all()
     return rows, base.count()
 
 
+def _tone_of(lexicon, verdict):
+    """'bullish', 'bearish' or None, from the two scores together.
+
+    The model outranks the word list where both spoke. The lexicon is forty
+    words with a negation window: it reads "great, another green day" after a
+    crash as bullish, which is exactly the case spec 6.11 specified a re-read
+    for.
+
+    `unclear` votes neither way and BLOCKS the lexicon. It means the post named
+    the ticker without expressing a view, and that read is better informed than
+    the word list it overrides.
+
+    A NULL verdict falls back to the lexicon rather than counting as toneless:
+    verdicts arrive on a scheduled pass, so a fresh mention has none, and
+    treating that as silence would make the newest posts look even-handed.
+    """
+    if verdict == 'bullish':
+        return 'bullish'
+    if verdict == 'bearish':
+        return 'bearish'
+    if verdict is not None:            # 'neutral' or 'unclear'
+        return None
+    if lexicon and lexicon > 0:
+        return 'bullish'
+    if lexicon and lexicon < 0:
+        return 'bearish'
+    return None
+
+
 def breakdown_for(ticker, sources, since, now):
     """One pass over the window's mentions, taken apart several ways.
 
     Loaded rather than aggregated in SQL because the same rows answer five
     questions -- per venue, per author, per hour, the concentration, and the
     totals -- and five GROUP BY queries would read them five times over for a
     set that is at most a few thousand rows.
     """
+    sources = expand_sources_for_history(sources)
     score = RadarMention.lexicon_sentiment
+    verdict = RadarMention.llm_sentiment
     rows = (db.session.query(RadarPost.source, RadarPost.author,
-                             RadarPost.channel, RadarPost.created_utc, score)
+                             RadarPost.channel, RadarPost.created_utc, score,
+                             verdict)
             .join(RadarMention, RadarMention.post_id == RadarPost.id)
             .filter(RadarMention.ticker == ticker,
                     RadarPost.source.in_(list(sources)),
                     RadarPost.created_utc >= since,
                     RadarPost.created_utc < now,
                     RadarMention.confidence.in_(('high', 'medium'))).all())
 
     by_source = {}
     by_author = collections.Counter()
     by_hour = collections.Counter()
-    bullish = bearish = 0
-
-    for source, author, channel, when, sentiment in rows:
-        entry = by_source.setdefault(source, [0, set()])
+    bullish = bearish = disagreements = 0
+
+    for source, author, channel, when, sentiment, llm in rows:
+        # A VENUE IS A ROOT. Every stored Reddit name -- the eight
+        # `reddit:<sub>` and the pre-split bare `reddit` -- pools into one
+        # `reddit` row, which is what this table showed before the subreddit
+        # split and what `venues=len(b.venues)` in the written read counts.
+        #
+        # Splitting it into eight rows with eight voice counts and eight
+        # shares-of-mentions would be a product decision about what this
+        # surface is FOR; the split that produced these names was a decision
+        # about how status and scoring are partitioned. Shipping the first as
+        # a side effect of the second would foreclose it silently.
+        venue = source_root(source)
+        entry = by_source.setdefault(venue, [0, set()])
         entry[0] += 1
         # The independent unit differs by kind, the same way the eligibility
         # gate's does: an author on a forum, a channel on a broadcast network.
         entry[1].add(channel if source_kind(source) == 'broadcast' else author)
         by_author[author] += 1
         by_hour[when.replace(minute=0, second=0, microsecond=0)] += 1
-        if sentiment and sentiment > 0:
+        tone = _tone_of(sentiment, llm)
+        if tone == 'bullish':
             bullish += 1
-        elif sentiment and sentiment < 0:
+        elif tone == 'bearish':
             bearish += 1
+        # A post the word list read one way and the model read the other is a
+        # post that was being sarcastic. Both scores are kept precisely so this
+        # comparison is possible; nothing performed it until now.
+        lexicon_only = _tone_of(sentiment, None)
+        if llm is not None and lexicon_only is not None and tone != lexicon_only:
+            disagreements += 1
 
     total = len(rows)
     ranked = by_author.most_common(2)
     peak = by_hour.most_common(1)
 
     return Breakdown(
         venues=[Venue(source=name, mentions=counts[0], voices=len(counts[1]))
                 for name, counts in sorted(by_source.items(),
                                            key=lambda kv: -kv[1][0])],
         bullish=bullish,
         bearish=bearish,
         # Every mention whose text carried no lexicon word at all, which is
         # most of them. Hiding it would turn a handful of scored posts into a
         # confident-looking sentiment reading.
         neutral=total - bullish - bearish,
+        disagreements=disagreements,
         top_author_share=(ranked[0][1] / total) if total and ranked else None,
         top_two_share=((sum(count for _, count in ranked) / total)
                        if total and ranked else None),
         peak_hour=peak[0][0] if peak else None,
         peak_count=peak[0][1] if peak else 0,
         first_seen=None,
         mentions=total,
         voices=len(by_author),
     )
 
@@ -181,21 +245,27 @@ def first_mention_day(ticker):
     From buckets, which are retained forever. Posts prune at 30 days, so
     reading it from them would report "first seen" as a rolling month ago for
     every ticker the radar has followed longer than that.
     """
     first = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
              .filter(RadarBucketSource.ticker == ticker).scalar())
     return first.date() if first else None
 
 
 def build(ticker, sources, now, window_hours=4, span=chart_mod.DEFAULT_SPAN):
-    """One ticker's panel. Raises UnknownTicker if it is not in the universe."""
+    """One ticker's panel. Raises UnknownTicker if it is not in the universe.
+
+    `sources` is the viewer's SELECTION, unexpanded -- each query below picks
+    its own expansion, because the chart and the breakdown may see the
+    pre-split root `reddit` history and window_figures may not. See
+    config.expand_sources.
+    """
     if not chart_mod.known_span(span):
         raise ValueError('unknown span')
 
     profile = TickerUniverse.query.filter_by(symbol=ticker).one_or_none()
     if profile is None:
         raise chart_mod.UnknownTicker(ticker)
 
     since = now - dt.timedelta(hours=window_hours)
     session = market_calendar.session_state(now.replace(tzinfo=dt.timezone.utc))
     status = quotes_mod.price_status(ticker, now, session=session)
diff --git a/personal_apps/features/radar/ingest.py b/personal_apps/features/radar/ingest.py
index f2635a5..5cb8e1e 100644
--- a/personal_apps/features/radar/ingest.py
+++ b/personal_apps/features/radar/ingest.py
@@ -8,21 +8,22 @@ import datetime as dt
 import logging
 
 import sqlalchemy as sa
 
 from extensions import db
 from models import RadarMention, RadarPost, RadarSourceCursor
 
 from . import buckets, extraction, fingerprint, sentiment, universe
 from .config import (
     BUCKET_MINUTES, bare_token_confidence, bare_tokens_allowed,
-    coin_collision_dropped, looks_like_bot_feed)
+    coin_collision_dropped, looks_like_bot_feed,
+    single_letter_cashtags_allowed)
 
 logger = logging.getLogger('radar.ingest')
 
 def _utcnow():
     """Naive UTC, the convention every datetime in this codebase is stored in.
 
     datetime.utcnow() is deprecated and slated for removal, and it printed a
     warning into the service log on every cycle.
     """
     return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
@@ -58,70 +59,78 @@ def _advance_cursor(source, newest_seen):
     if row is None:
         row = RadarSourceCursor(source=source, cursor_utc=newest_seen)
         db.session.add(row)
     elif newest_seen > row.cursor_utc:
         row.cursor_utc = newest_seen
 
 
 def _extract_for(raw, lookup):
     """Extract under the policy that applies to this post's source.
 
-    Three per-source judgements, all about population rather than code:
+    Four per-source judgements, all about population rather than code:
     whether a bare token can be read as a ticker at all, what an
     uncorroborated one is WORTH, and whether a coin-shaped symbol means the
     company or the coin.
     """
     # An automated feed is one publisher however many tickers it names, and
     # it is not a person discussing anything. Dropped before extraction so the
     # whole post goes -- config.looks_like_bot_feed carries what counts and
     # why it matches the format's vocabulary rather than the symbols.
     if looks_like_bot_feed('%s %s' % (raw.title or '', raw.body or '')):
         return []
 
     tickers = extraction.extract_tickers(
         raw.title, raw.body, lookup,
         allow_bare=bare_tokens_allowed(raw.source),
+        allow_single_letter=single_letter_cashtags_allowed(raw.source),
         bare_confidence=bare_token_confidence(raw.source))
     return [(symbol, confidence) for symbol, confidence in tickers
             if not coin_collision_dropped(raw.source, symbol)]
 
 
 def _store_mentioning_posts(raw_posts, lookup, now):
     """Store only posts that mention a ticker, and their mentions.
 
     Extraction runs before storage rather than after, which is what keeps the
     firehose affordable: at 144k posts/hour, storing everything and extracting
     later would be 100 million rows a month to find roughly 250 thousand that
     matter.
 
-    Extraction still runs once per post -- an already-stored post is refreshed
-    for engagement but never re-extracted, so a stopword or universe change
-    cannot silently rewrite history under a bucket that was already counted.
+    Extraction runs once per post per cycle, and the journal keeps the result:
+    a post arriving again in a later cycle upserts its existing event rather
+    than re-deciding it, so a stopword or universe change cannot rewrite
+    history under a bucket that was already counted.
     """
     if not raw_posts:
         return [], 0
 
     # Whether to STORE a new post depends on extraction. Whether to REFRESH an
     # already-stored one does not: a post deleted upstream comes back with an
     # empty body, extracts nothing, and would never have its stored text
     # blanked if the two decisions were the same decision.
     existing = {}
     ids = [raw.external_id for raw in raw_posts]
     for start in range(0, len(ids), 1000):
         chunk = ids[start:start + 1000]
         for row in RadarPost.query.filter(RadarPost.external_id.in_(chunk)).all():
             existing[row.external_id] = row
 
     fresh, new_count = [], 0
+    extracted = {}
     for raw in raw_posts:
         row = existing.get(raw.external_id)
-        tickers = _extract_for(raw, lookup)
+        # An external identity can appear twice in a source batch. The second
+        # loop below needs the same decision, so cache it explicitly: a
+        # setdefault default would call _extract_for eagerly for duplicates.
+        if raw.external_id not in extracted:
+            extracted[raw.external_id] = _extract_for(raw, lookup)
+        tickers = extracted[raw.external_id]
 
         if row is None:
             # New, and only worth keeping if something scorable was found.
             #
             # `low` is an uncorroborated bare token -- ROM in "dinosaur fossils
             # at the ROM", and about 12000 an hour of its kind on the firehose.
             # Those are counted in the bucket but never scored, and there is no
             # reason to keep the text: it would be seven million rows a month
             # to store posts the leaderboard can never surface. Their mentions
             # still reach the rollup in memory, so counts and promotion are
@@ -151,24 +160,25 @@ def _store_mentioning_posts(raw_posts, lookup, now):
         row.title = raw.title
         row.body = raw.body
         row.author = raw.author
         row.simhash = fingerprint.simhash64('%s %s' % (raw.title or '', raw.body))
 
     db.session.flush()
 
     # Every extraction reaches the rollup, stored or not -- bucket counts and
     # corroboration are computed in memory from these rows.
     mention_rows = []
+    fresh_ids = {raw.external_id for raw, _, _ in fresh}
     for raw in raw_posts:
-        if raw.external_id in {r.external_id for r, _, _ in fresh}:
+        if raw.external_id in fresh_ids:
             continue
-        tickers = _extract_for(raw, lookup)
+        tickers = extracted[raw.external_id]
         if not tickers:
             continue
         score = sentiment.lexicon_score('%s %s' % (raw.title or '', raw.body))
         for symbol, confidence in tickers:
             mention_rows.append(buckets.MentionRow(
                 ticker=symbol, external_id=raw.external_id,
                 created_utc=raw.created_utc, source=raw.source,
                 channel=raw.channel,
                 author=raw.author, simhash=fingerprint.simhash64(
                     '%s %s' % (raw.title or '', raw.body)),
@@ -229,26 +239,49 @@ def run_cycle(now, fetchers):
         except Exception:
             # Isolated deliberately, and broadly. Each source declares an
             # exception type for "this fetch did not arrive", but a source can
             # also fail in ways it never anticipated -- a missing dependency
             # took down a whole cycle, StockTwits and 4chan included, because
             # ModuleNotFoundError is not JetstreamUnavailable. One source
             # failing must never cost the others their data (spec 4.5), and
             # `missing` is the honest record of it: no row, never a zero.
             logger.exception('radar source %s failed this cycle', source)
             statuses[source] = 'missing'
-            depths[source] = 0
+            # Not zero: no fetch arrived to measure a catch-up depth.
+            depths[source] = None
             continue
-        statuses[source] = result.status
+        # A fetcher covering several source names reports each. Reddit does:
+        # one cycle reads a slice of subreddits and each is its own source.
+        # When those concrete statuses exist, the aggregate fetch verdict must
+        # not become a zero-valued root child in the rollup population.
+        #
+        # `is not None`, NOT truthiness. An empty map is an explicit "no
+        # source was observed" -- Reddit with nothing due did not read Reddit
+        # -- and falling back to the aggregate verdict there would stamp
+        # `{'reddit': 'ok'}` onto the rollup, which writes a zero-count child
+        # row under a name no fetch produced. Only a MISSING map (None) means
+        # "this fetcher does not report per-source status", where the
+        # aggregate genuinely applies to the one name it fetched under.
+        if result.per_source_status is None:
+            result_statuses = {source: result.status}
+        else:
+            result_statuses = dict(result.per_source_status)
+        statuses.update(result_statuses)
         depths[source] = result.catchup_depth
 
-        if result.status == 'missing':
+        # Nothing observed at all, or everything observed failed. Either way
+        # there is no coverage this cycle: no buckets are touched on this
+        # source's behalf and no cursor moves. Aggregate status remains useful
+        # for cycle reporting, but it cannot discard an earlier successful sub
+        # when a later request was refused.
+        if not result_statuses or all(
+                status == 'missing' for status in result_statuses.values()):
             continue
 
         posts_seen += len(result.posts)
 
         # A source that could not reach as far back as it was asked did not
         # cover the earlier part of the window, and must not have buckets
         # written as though it had.
         effective_since = result.covered_since or since
         touched |= _touched_buckets([], effective_since, now)
 
diff --git a/personal_apps/features/radar/journal.py b/personal_apps/features/radar/journal.py
index f3b122e..ef5517d 100644
--- a/personal_apps/features/radar/journal.py
+++ b/personal_apps/features/radar/journal.py
@@ -5,30 +5,33 @@ The journal answers one question for roll_up: what is EVERYTHING that landed in
 this ticker's quarter-hour, regardless of which cycle carried it. Nothing else
 in the pipeline reads it, and nothing reads it after retention drops the row --
 the bucket is the durable artifact.
 """
 import collections
 
 import sqlalchemy as sa
 from sqlalchemy.dialects.mysql import insert as mysql_insert
 
 from extensions import db
-from models import RadarMentionEvent
+from models import RadarMention, RadarMentionEvent, RadarPost
 
 # Imported as a module, not `from .buckets import MentionRow, bucket_start_for`
 # -- a name import needs those names bound in buckets' namespace by the time
 # THIS line runs, which fails whenever buckets is the module still mid-import
 # (it imports journal at its own top). Importing the module and reaching
 # `buckets.MentionRow` / `buckets.bucket_start_for` only inside the functions
 # below defers that lookup to call time, when both modules are always fully
 # loaded, so it works regardless of which one a caller imports first.
 from . import buckets
+# Safe as a name import: config imports nothing from this package, so it is
+# never the module mid-import. Only `buckets` is in the cycle.
+from .config import expand_sources_for_history
 
 # Rows per INSERT. Large enough that a busy Bluesky cycle is a handful of
 # statements, small enough to stay well inside max_allowed_packet.
 _CHUNK = 500
 
 
 def record(rows):
     """Store this cycle's mentions. Idempotent on (source, external_id, ticker).
 
     Only `engagement` is updated on a duplicate. Everything else was decided at
@@ -61,20 +64,62 @@ def record(rows):
         'engagement': row.engagement,
     } for row in rows]
 
     for start in range(0, len(payload), _CHUNK):
         statement = mysql_insert(RadarMentionEvent).values(payload[start:start + _CHUNK])
         db.session.execute(statement.on_duplicate_key_update(
             engagement=statement.inserted.engagement))
     db.session.commit()
 
 
+def bootstrap_from_mentions(since):
+    """Recover retained extractor decisions before the first journal rollup.
+
+    The journal table is empty immediately after migration (Task 1), so an
+    already-open quarter-hour rebuilt from the first post-deploy cursor slice
+    alone would repeat the exact overwrite this whole generation exists to
+    fix. radar_posts x radar_mentions is the only place the pre-migration
+    decision still lives -- 30-day retention on posts outlasts the journal's
+    48 hours -- so this replays it back through the same `record()` path a
+    live cycle uses.
+
+    Idempotent through record()'s unique key on (source, external_id,
+    ticker): safe to call on every startup, not just the first one after a
+    migration.
+
+    `medium` is deliberately absent from the recovered confidence: the
+    extractor only ever stored high/low, and promotion is recomputed from the
+    full bucket at rollup, never invented here. A low-only post was never
+    retained at all -- Bluesky alone would be 100 million rows a month of
+    text nothing reads -- and stays honestly unrecoverable.
+    """
+    rows = (db.session.query(
+                RadarMention.ticker, RadarMention.confidence,
+                RadarMention.lexicon_sentiment,
+                RadarPost.source, RadarPost.external_id, RadarPost.channel,
+                RadarPost.author, RadarPost.created_utc, RadarPost.simhash,
+                RadarPost.score, RadarPost.num_comments)
+            .join(RadarPost, RadarPost.id == RadarMention.post_id)
+            .filter(RadarPost.created_utc >= since,
+                    RadarMention.confidence.in_(('high', 'low')))
+            .all())
+    recovered = [buckets.MentionRow(
+        ticker=ticker, external_id=external_id, created_utc=created_utc,
+        source=source, channel=channel, author=author, simhash=int(simhash),
+        confidence=confidence, sentiment=sentiment,
+        engagement=float((score or 0) + (num_comments or 0)))
+        for (ticker, confidence, sentiment, source, external_id, channel,
+             author, created_utc, simhash, score, num_comments) in rows]
+    record(recovered)
+    return len(recovered)
+
+
 def events_for(keys):
     """Every stored event in these (ticker, bucket_start) windows.
 
     Queried per bucket_start rather than per pair, because one cycle touches a
     handful of quarter-hours and hundreds of tickers -- an IN over the tickers
     inside each window uses the (ticker, bucket_start) index and takes one
     round trip per window instead of one per pair.
     """
     keys = list(keys)
     if not keys:
@@ -141,20 +186,25 @@ def distinct_voices(tickers, sources, since, now, field):
 
     Buckets store distinct_authors as a COUNT, so aggregating them can only
     take a maximum, and a maximum systematically undercounts: two buckets
     holding {x, y} and {z, w} have four distinct voices and report two.
     Measured on live data, NVDA showed 26 real authors against a bucket
     maximum of 2.
     """
     if not tickers:
         return {}
 
+    # A raw count of distinct people, with no baseline behind it, so the
+    # pre-split root `reddit` events count towards it -- they are the same
+    # readers on the same platform, and dropping them would undercount
+    # breadth for every ticker discussed before the split.
+    sources = expand_sources_for_history(sources)
     column = {'author': RadarMentionEvent.author,
               'channel': RadarMentionEvent.channel}[field]
     rows = (db.session.query(RadarMentionEvent.ticker,
                              sa.func.count(sa.distinct(column)))
             .filter(RadarMentionEvent.ticker.in_(list(tickers)),
                     RadarMentionEvent.source.in_(list(sources)),
                     RadarMentionEvent.created_utc >= since,
                     RadarMentionEvent.created_utc < now,
                     sa.or_(RadarMentionEvent.confidence == 'high',
                            RadarMentionEvent.promoted.is_(True)))
diff --git a/personal_apps/features/radar/leaderboard.py b/personal_apps/features/radar/leaderboard.py
index 1f6db17..7dcd5bd 100644
--- a/personal_apps/features/radar/leaderboard.py
+++ b/personal_apps/features/radar/leaderboard.py
@@ -13,21 +13,22 @@ import datetime as dt
 import sqlalchemy as sa
 
 from extensions import db
 from models import RadarBucketSource, TickerUniverse
 
 from . import divergence as divergence_mod
 from . import journal
 from . import market_calendar
 from . import quotes as quotes_mod
 from . import scoring, universe
-from .config import PROVISIONAL_BASELINE_DAYS, segments_in, source_kind
+from .config import (PROVISIONAL_BASELINE_DAYS, VARIANCE_FLOOR,
+                     expand_sources, segments_in, source_kind, source_root)
 
 
 @dataclasses.dataclass
 class Ranking:
     """Rows worth showing, and an account of what was left out.
 
     The account is not decoration. The eligibility floor is the single largest
     reason this board is short, and until now it dropped tickers with no trace
     -- so a quiet market and a stopped daemon rendered identically, and the
     reader had no way to tell which they were looking at.
@@ -41,26 +42,35 @@ class Ranking:
 class Row:
     ticker: str
     name: str | None
     segment: str
     divergence: float | None
     mention_z: float | None
     mentions: int
     expected: float
     authors: int
     text_ratio: float
+    # Concrete stored names that contributed -- `reddit:pennystocks`, not
+    # `reddit`. This is the breakdown, and it must stay concrete.
     sources: list
+    # How many INDEPENDENT venues those names represent, which is the count of
+    # their roots. Two subreddits are two entries in `sources` and one venue:
+    # they share a platform, a user population and a rate-limit budget, so the
+    # corroboration the breadth filter and the `single-source` mark claim is
+    # not there. Carried as its own field rather than recomputed by every
+    # reader, so the two can never drift apart.
+    venues: int
     price: object
     price_move: object
     direction: str
     price_status: str
-    baseline_days: int | None
+    baseline_days: float | None
     marks: list
 
 
 def _distinct_authors(tickers, sources, since, now):
     """True distinct authors per ticker across the whole window.
 
     Read from the mention journal rather than from radar_mentions. That table
     never holds `medium` -- promotion is decided at rollup over the whole
     bucket and written back onto the journal -- and a post whose tickers were
     all `low` is never stored there at all, so the count it gave was smaller
@@ -83,20 +93,27 @@ def _universe_rows(tickers):
         return {}
     rows = TickerUniverse.query.filter(
         TickerUniverse.symbol.in_(list(tickers))).all()
     return {row.symbol: row for row in rows}
 
 
 def build_rows(sources, now, window_hours=4, segments=(), limit=50,
                session=None, min_venues=1):
     """Ranked leaderboard rows for the selected sources.
 
+    `sources` is the viewer's SELECTION, root-level or concrete, not an
+    expanded list. The bucket query below is a SCORED read, so it expands
+    strictly: the pre-split root `reddit` rows carry a different
+    source_config_version and their z belongs to a different baseline
+    population (see config.expand_sources). The voice counts are raw and
+    expand for history.
+
     The source list is a read-time filter: it re-pools components that were
     stored per source, and never touches how anything was scored (spec 8.6).
 
     `session` is the exchange state. With the market shut no row gets a
     divergence, because there is no price movement to be surprised by -- so
     the sort falls through to mention_z and the board ranks on chatter alone.
     That is the useful answer at 23:00 on a Sunday (what is worth looking at
     on Monday), and it is only honest if the surface says which of the two
     rankings the reader is looking at. Computed once here rather than per
     ticker; the caller may pass it in to avoid computing it twice.
@@ -119,33 +136,38 @@ def build_rows(sources, now, window_hours=4, segments=(), limit=50,
     # 707ms of SQL and 1.8s of object construction, for figures the database
     # can produce in one pass.
     #
     # Grouped by SOURCE as well as ticker, not folded to kind here: which kind
     # a source belongs to is `source_kind`'s judgement and it stays in Python.
     # Sources are a handful, so this is ~3 rows per ticker rather than ~96.
     #
     # MIN over a nullable baseline_days skips NULLs, which is exactly what the
     # Python it replaces did. The columns that must not skip -- mention_count,
     # distinct_authors, distinct_text_ratio, status -- are all NOT NULL.
+    scored_sources = expand_sources(sources)
+    # How many venues the VIEWER switched on, rooted for the same reason the
+    # contributing count is: picking `reddit` is picking one venue, however
+    # many subreddits it expands to.
+    selected_venues = len({source_root(name) for name in sources})
     bucket = RadarBucketSource
     per_source = (db.session.query(
         bucket.ticker.label('ticker'),
         bucket.source.label('source'),
         sa.func.sum(bucket.mention_count).label('mentions'),
         sa.func.sum(sa.func.coalesce(bucket.expected, 0.0)).label('expected'),
         sa.func.sum(sa.func.coalesce(bucket.variance, 0.0)).label('variance'),
         sa.func.max(bucket.distinct_authors).label('authors'),
         sa.func.min(bucket.distinct_text_ratio).label('text_ratio'),
         sa.func.min(bucket.baseline_days).label('baseline_days'),
         sa.func.max(sa.case((bucket.status == 'truncated', 1), else_=0))
         .label('truncated'))
-        .filter(bucket.source.in_(list(sources)),
+        .filter(bucket.source.in_(scored_sources),
                 bucket.bucket_start >= since,
                 bucket.bucket_start < now,
                 bucket.mention_z.isnot(None))
         .group_by(bucket.ticker, bucket.source)
         .all())
 
     grouped = collections.defaultdict(list)
     for row in per_source:
         grouped[row.ticker].append(row)
 
@@ -219,27 +241,33 @@ def build_rows(sources, now, window_hours=4, segments=(), limit=50,
     # against 30ms for the detail panel doing the same three for one ticker.
     statuses = quotes_mod.statuses_for(survivors.keys(), now, session=session)
     moves = quotes_mod.moves_for(survivors.keys(), window_hours, now)
     today = now.date()
     rows = []
 
     for ticker, (mentions, expected, variance, authors,
                  text_ratio) in survivors.items():
         parts = grouped[ticker]
         mention_z = ((mentions - expected)
-                     / max(variance, 0.25) ** 0.5) if variance else None
+                     / max(variance, VARIANCE_FLOOR) ** 0.5) if variance else None
 
         contributing = sorted({part.source for part in parts})
+        # One venue per ROOT, not per stored name -- see Row.venues.
+        venues = len({source_root(name) for name in contributing})
         # MIN already skipped NULLs per source; this skips the sources that
         # had nothing but NULLs, so a row with no usable baseline anywhere
-        # still reports None rather than raising.
-        baseline_days = min((part.baseline_days for part in parts
+        # still reports None rather than raising. Coerced like the aggregates
+        # above for the same reason, even though MIN/MAX over a Float column
+        # (unlike SUM over an Integer one) do not promote to Decimal on
+        # MySQL/MariaDB -- matching the sibling pattern removes the ambiguity
+        # for a future reader rather than relying on that distinction silently.
+        baseline_days = min((float(part.baseline_days) for part in parts
                              if part.baseline_days is not None), default=None)
 
         profile = profiles.get(ticker)
         status, latest = statuses[ticker]
         move = moves[ticker]
         if status == 'unknown':
             # Kept explicit rather than relying on the batch: 'unknown' means
             # never quoted, so there is no snapshot to carry even though the
             # mapping always has an entry for every ticker asked about.
             latest = None
@@ -253,57 +281,63 @@ def build_rows(sources, now, window_hours=4, segments=(), limit=50,
         if status == 'ok' and move is not None and mention_z is not None:
             sigma = profile.daily_sigma if profile else None
             move_z = divergence_mod.price_move_z(
                 move, quotes_mod.scale_sigma(sigma, window_hours))
             if move_z is not None:
                 value = divergence_mod.divergence(mention_z, move_z)
 
         marks = []
         if status == 'stale':
             marks.append('no-print')
-        if len(contributing) == 1 and len(sources) > 1:
+        if venues == 1 and selected_venues > 1:
             marks.append('single-source')
         if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
-            marks.append('provisional')
+            # Two different facts wear this badge, and only one is about the
+            # ticker. A NEW ticker has thin history of its own; every ticker on
+            # the board has thin history when the extraction rules changed
+            # recently, because baselines are built per config version. Saying
+            # `provisional` for both made it fire on all of them.
+            marks.append('provisional' if baseline_days >= 1.0 else 'warming-up')
         if any(part.truncated for part in parts):
             marks.append('partial')
 
         row_segment = universe.segment_for(
             profile.market_cap if profile else None,
             profile.ipo_date if profile else None,
             latest.price if latest else None,
             today, profile.name if profile else None,
             profile.is_etf if profile else None)
         if allowed and row_segment not in allowed:
             continue
         # Breadth as a filter, not as a score. `contributing` is the list of
         # sources that actually said something, so this asks how many venues
         # are talking rather than how many the viewer has switched on.
         #
         # Counted apart from the floor: this is the reader's own filter doing
         # what they asked, not the data being too thin to measure. Merging the
         # two would tell them the data was worse than it is.
-        if len(contributing) < min_venues:
+        if venues < min_venues:
             excluded['one_venue'] += 1
             continue
 
         rows.append(Row(
             ticker=ticker,
             name=profile.name if profile else None,
             segment=row_segment,
             divergence=value,
             mention_z=mention_z,
             mentions=mentions,
             expected=expected,
             authors=authors,
             text_ratio=text_ratio,
             sources=contributing,
+            venues=venues,
             price=latest.price if latest else None,
             price_move=move,
             direction=divergence_mod.direction(move),
             price_status=status,
             baseline_days=baseline_days,
             marks=marks,
         ))
 
     # Divergence first where it exists, then mention_z. A ticker with no price
     # is not evidence of anything about its price, so it sorts below one that
diff --git a/personal_apps/features/radar/llm_sentiment.py b/personal_apps/features/radar/llm_sentiment.py
index 5e0b019..7d2a6d1 100644
--- a/personal_apps/features/radar/llm_sentiment.py
+++ b/personal_apps/features/radar/llm_sentiment.py
@@ -12,25 +12,33 @@ BOTH SCORES ARE KEPT. That is the design, not an accident of migration: spec
 6.11 wants the two to be comparable, because a post the lexicon reads as
 bullish and the model reads as bearish is a post that was being sarcastic.
 Overwriting lexicon_sentiment would throw the detector away to save a float.
 
 WHAT THIS DOES NOT TOUCH. source_config_version stamps everything that decides
 WHICH mentions get counted. Tone is not one of those -- it changes how a
 counted mention is scored, and rescoring re-reads the same buckets, so there
 is no discontinuity to warm up from. config.source_config_version's own
 docstring draws that line; this stays on the far side of it.
 
-COST. About 1335 scored mentions a day, ~100 input tokens each and one word
-back, batched. At Haiku's rates that is roughly twenty cents a day. The
-estimate in spec 6.11 -- "order of 150k input tokens/day, cents" -- turns out
-to have been accurate for exactly this population, and is wrong by two orders
-of magnitude for any larger one.
+COST. Measured, not estimated, on 2026-08-25: 344 calls, 798,198 input tokens,
+89,281 output, $1.2446 for the day. The earlier figure in this docstring --
+"about 1335 scored mentions a day ... roughly twenty cents" -- was 5x low on
+volume and 6x low on cost, because it counted the mentions a day's BUCKETS
+carry rather than the mentions the pass is handed. spec 6.11's own estimate
+("order of 150k input tokens/day, cents") is wrong by the same factor.
+
+No daily ceiling. PASS_LIMIT caps one pass at 400 and the pass runs every ten
+minutes, so the theoretical maximum is 57,600 mentions a day against an
+observed 6,880 -- the ceiling that matters is how many mentions ingest
+produces, and a spend cap would silently stop reading tone rather than
+signalling that something upstream had changed. The figure is on the board;
+watch it there.
 """
 import json
 import logging
 
 import anthropic
 import sqlalchemy as sa
 
 from extensions import db
 from models import RadarMention, RadarPost
 
diff --git a/personal_apps/features/radar/phrasing.py b/personal_apps/features/radar/phrasing.py
index f29dd85..80e4e72 100644
--- a/personal_apps/features/radar/phrasing.py
+++ b/personal_apps/features/radar/phrasing.py
@@ -92,21 +92,23 @@ def row_clauses(row, session):
 
 def _breadth_clauses(row):
     """How many independent things are saying it -- or, when too few are, one
     warning instead of two counts.
 
     Deliberately asymmetric. A broad row gets venues and people as separate
     facts because both are reassuring on their own; a narrow one gets a single
     warning, because "1 venue · 2 people" in the counting grammar reads as two
     small numbers rather than as the one thing that should stop you.
     """
-    venues = len(row.sources)
+    # The rooted count, not len(row.sources): "2 venues" must not mean two
+    # subreddits. See leaderboard.Row.venues.
+    venues = row.venues
     narrow = []
     if venues < 2:
         narrow.append('one venue only')
     if row.authors < NARROW_VOICES:
         narrow.append(f'{row.authors} voices')
 
     if narrow:
         return [Clause('warn', ', '.join(narrow))]
     return [Clause('venues', f'{venues} venues'),
             Clause('people', f'{row.authors} people')]
@@ -162,23 +164,33 @@ def read_clauses(detail, mentions, expected, voices, session,
                           f'{voices} distinct voices{where}, so this is not '
                           f'one account repeating itself.'))
     else:
         out.append(Clause('warn',
                           f'Only {voices} distinct voices — one account can '
                           f'produce this much on its own.'))
 
     out.extend(_read_price(detail, session))
 
     if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
-        days = 'day' if baseline_days == 1 else 'days'
+        # `baseline_days` is a fraction of a day, not a truncated int, since
+        # Task 16 (2026-08-27) -- an hour-old baseline is `0.0416...`, and
+        # interpolating that raw float into the sentence read as
+        # "0.041666666666666664 days old". Branch instead: sub-day spans are
+        # exactly the population 'warming-up' exists to describe, so they get
+        # their own words rather than a rounded-away lie of precision.
+        if baseline_days < 1:
+            span = 'under a day'
+        else:
+            whole = round(baseline_days)
+            span = f'{whole} day' if whole == 1 else f'{whole} days'
         out.append(Clause('warn',
-                          f'The baseline is {baseline_days} {days} old, not '
+                          f'The baseline is {span} old, not '
                           f'30, so this rests on very little history.'))
     return out
 
 
 def _read_price(detail, session):
     """What the tape did, or why there is nothing to say about it."""
     if session == 'closed' or detail.price_status == 'closed':
         return [Clause('plain',
                        'The market is shut, so there is no price move to '
                        'compare this against — divergence needs a live tape '
diff --git a/personal_apps/features/radar/profile.py b/personal_apps/features/radar/profile.py
index 0595afb..cae2e07 100644
--- a/personal_apps/features/radar/profile.py
+++ b/personal_apps/features/radar/profile.py
@@ -1,19 +1,19 @@
 # personal_apps/features/radar/profile.py
 """What a normal bucket looks like, per source.
 
 Mention volume has a strong weekly shape. Comparing 03:00 on a Sunday against
 15:00 on a Tuesday as though they were one population makes every weekday
 afternoon look like a spike, which is most of what a naive z-score would report.
 
 Built per source rather than market-wide, a deliberate departure from spec 6.1.
-StockTwits follows US market hours, Bluesky is global and diurnal, /biz/ runs
+Reddit follows US market hours, Bluesky is global and diurnal, /biz/ runs
 around the clock. A shared profile would tell Bluesky to expect silence at
 03:00 ET while half its users are awake, and every one of those buckets would
 score as unusual.
 """
 import collections
 import datetime as dt
 
 import sqlalchemy as sa
 
 from extensions import db
@@ -32,34 +32,44 @@ SMOOTHING = 1.0
 
 DEFAULT_WEEKS = 8
 
 
 def bucket_of_week(when):
     """0..671, counting 15-minute buckets from Monday 00:00 UTC."""
     minutes = (when.weekday() * 24 * 60) + (when.hour * 60) + when.minute
     return minutes // BUCKET_MINUTES
 
 
-def build_profile(source, until, weeks=DEFAULT_WEEKS):
+def build_profile(source, until, config_version, weeks=DEFAULT_WEEKS):
     """Share of this source's weekly volume falling in each bucket-of-week.
 
     Only `ok` buckets contribute. A `missing` bucket is a source that was down,
     not an hour that was quiet, and counting it would bend the profile towards
     silence at precisely the times ingest tends to fail. `truncated` is a known
     undercount and equally unusable as a description of normal.
+
+    `config_version` is required, not optional: a bucket stamped under a
+    different generation was aggregated from a different population (Task 3c
+    -- rebuilding from the complete mention journal instead of one cursor
+    slice changed measured volume even though the extractor's membership
+    rules did not), and folding it into this sum would let understated
+    pre-fix counts drag the expectation down right where corrected data is
+    starting to arrive. There is no unversioned fallback mode; every caller
+    scores against one exact generation or not at all.
     """
     since = until - dt.timedelta(weeks=weeks)
 
     rows = (db.session.query(RadarBucketSource.bucket_start,
                              sa.func.sum(RadarBucketSource.mention_count))
             .filter(RadarBucketSource.source == source,
                     RadarBucketSource.status == 'ok',
+                    RadarBucketSource.source_config_version == config_version,
                     RadarBucketSource.bucket_start >= since,
                     RadarBucketSource.bucket_start < until)
             .group_by(RadarBucketSource.bucket_start).all())
 
     weights = collections.defaultdict(float)
     for index in range(BUCKETS_PER_WEEK):
         weights[index] = SMOOTHING
     for bucket_start, total in rows:
         weights[bucket_of_week(bucket_start)] += float(total or 0)
 
diff --git a/personal_apps/features/radar/retention.py b/personal_apps/features/radar/retention.py
index 3e9dd36..1af22a7 100644
--- a/personal_apps/features/radar/retention.py
+++ b/personal_apps/features/radar/retention.py
@@ -3,24 +3,24 @@
 Buckets are never touched here. They are the queryable layer and are retained
 forever; raw posts exist only long enough to be extracted from and read on a
 detail page (spec 5).
 """
 import datetime as dt
 import time
 
 import sqlalchemy as sa
 
 from extensions import db
-from models import RadarPost, RadarQuote
+from models import RadarMentionEvent, RadarPost, RadarQuote
 
-from .config import (POST_RETENTION_DAYS, QUOTE_RETENTION_DAYS,
-                     STALE_QUOTE_POLLS)
+from .config import (MENTION_EVENT_RETENTION_HOURS, POST_RETENTION_DAYS,
+                     QUOTE_RETENTION_DAYS, STALE_QUOTE_POLLS)
 
 # Breathing room between chunks so the daemon's next cycle is not queued behind
 # a long delete on the same connection.
 _CHUNK_PAUSE_SECONDS = 0.05
 
 
 def prune_posts(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS):
     """Delete posts older than the retention window, in chunks.
 
     Mentions follow via ON DELETE CASCADE. Returns the number deleted.
@@ -93,10 +93,47 @@ def prune_quotes(now, keep=STALE_QUOTE_POLLS, chunk_size=5000,
     for start in range(0, len(doomed), chunk_size):
         batch = doomed[start:start + chunk_size]
         db.session.query(RadarQuote).filter(RadarQuote.id.in_(batch)).delete(
             synchronize_session=False)
         db.session.commit()
         total += len(batch)
         if pause and start + chunk_size < len(doomed):
             time.sleep(pause)
 
     return total
+
+
+def prune_mention_events(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS):
+    """Delete journal rows whose bucket can no longer be rewritten.
+
+    By created_utc rather than by insertion time. A catch-up after an outage
+    ingests posts hours old, and what decides is when the POST was written --
+    once its quarter-hour is past the window, no cycle will touch that bucket
+    again and the events behind it have nothing left to answer.
+
+    Returns the number deleted.
+    """
+    cutoff = now - dt.timedelta(hours=MENTION_EVENT_RETENTION_HOURS)
+    total = 0
+
+    while True:
+        ids = [
+            row_id for (row_id,) in
+            db.session.query(RadarMentionEvent.id)
+            .filter(RadarMentionEvent.created_utc < cutoff)
+            .order_by(RadarMentionEvent.created_utc)
+            .limit(chunk_size).all()
+        ]
+        if not ids:
+            break
+
+        db.session.query(RadarMentionEvent).filter(
+            RadarMentionEvent.id.in_(ids)).delete(synchronize_session=False)
+        db.session.commit()
+        total += len(ids)
+
+        if len(ids) < chunk_size:
+            break
+        if pause:
+            time.sleep(pause)
+
+    return total
diff --git a/personal_apps/features/radar/routes/api.py b/personal_apps/features/radar/routes/api.py
index 3082d81..796c56c 100644
--- a/personal_apps/features/radar/routes/api.py
+++ b/personal_apps/features/radar/routes/api.py
@@ -2,27 +2,29 @@
 import dataclasses
 import datetime as dt
 
 from flask import jsonify, request
 
 from auth import login_required
 
 from .. import board as board_mod
 from .. import detail as detail_mod
 from .. import detail_panel, phrasing, spend
-from ..config import DEFAULT_SEGMENT, SOURCES
+from ..config import DEFAULT_SEGMENT, REDDIT_SUBS, SOURCES, source_root
 from ._blueprint import radar_bp
 
 SEGMENTS = ('large', 'mid', 'micro', 'unknown', 'recent_ipo', 'fund', 'small')
 WINDOWS = (1, 4, 24)
 VENUE_FLOORS = (1, 2)
 MAX_LIMIT = 100
+# Every root plus every configured subreddit. See parse_query.
+MAX_SOURCES = len(SOURCES) + len(REDDIT_SUBS)
 
 
 @dataclasses.dataclass
 class Query:
     """A validated query string.
 
     A dataclass rather than a tuple: five fields unpacked positionally in two
     call sites, three of them ints, is one transposition away from silently
     swapping limit and min_venues with nothing to complain about.
     """
@@ -46,22 +48,33 @@ class BadQuery(ValueError):
 def parse_query(args):
     """(sources, segment, window, limit) or raise BadQuery.
 
     Every parameter is validated rather than coerced. Silently ignoring an
     unknown source would return the default board under a selection the viewer
     never made, which is worse than an error.
     """
     raw_sources = args.get('sources')
     if raw_sources:
         selected = [s.strip() for s in raw_sources.split(',') if s.strip()]
-        if any(s not in SOURCES for s in selected):
+        # A prefixed name is valid when its ROOT is a known source: the UI
+        # offers `reddit` as one chip, and a link may name one subreddit.
+        if any(source_root(s) not in SOURCES for s in selected):
             raise BadQuery('unknown source')
+        # Bounded, because rooting the membership check unbounded it. Before
+        # the subreddit split every accepted name had to be one of three, so
+        # the list could hold at most three; now `reddit:<anything>` passes,
+        # and each accepted entry lands in six or more IN (...) clauses
+        # against a ~300k-row partitioned table. MAX_SOURCES is the largest
+        # selection that can name something real -- every root plus every
+        # configured subreddit.
+        if len(selected) > MAX_SOURCES:
+            raise BadQuery('too many sources')
     else:
         selected = list(SOURCES)
 
     # Comma-separated since 2026-08-25, and `?segment=small` still parses --
     # widening the parameter must not invalidate every bookmarked link.
     # `?segment=` with an empty value stays how the surface asks for All.
     raw_segments = args.get('segment', DEFAULT_SEGMENT)
     segments = [name.strip() for name in raw_segments.split(',') if name.strip()]
     # One bad name rejects the whole selection rather than being dropped:
     # answering with a board under a selection the viewer never made is the
@@ -156,23 +169,37 @@ def _row(entry):
         # Why this row is here, in words. The client styles by `kind` and
         # never parses `text` -- see phrasing.py.
         'clauses': [{'kind': c.kind, 'text': c.text} for c in entry.clauses],
     }
 
 
 def build_payload(args, now=None):
     """Validated query -> serialized board. Shared by the page and the API."""
     query = parse_query(args)
     now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
-    board = board_mod.build(query.sources, now, window_hours=query.window,
+    # The SELECTION, unexpanded. board.build hands it to each query, and the
+    # queries expand differently: a scored read may not see the pre-split root
+    # `reddit` rows and a raw-count read must (config.expand_sources vs
+    # expand_sources_for_history). Expanding once here would take that choice
+    # away from them -- and expanding for history afterwards is impossible,
+    # since the root is no longer in the list to recognise.
+    board = board_mod.build(query.sources, now,
+                            window_hours=query.window,
                             segments=query.segments, limit=query.limit,
                             min_venues=query.min_venues)
+    # ROOTED, because the payload's `sources` is what lights the chips and
+    # there is one chip per root. `?sources=reddit:wallstreetbets` filtered
+    # the board to that subreddit above and still lights the Reddit chip
+    # here; without the rooting it matched no chip at all and the control
+    # rendered every chip off -- a state it otherwise forbids, and one whose
+    # first click silently discarded the concrete selection.
+    board.sources = sorted({source_root(s) for s in query.sources})
     return serialize(board)
 
 
 @radar_bp.route('/api/board')
 @login_required
 def board():
     """Ranked rows for the selected sources, segment and window."""
     try:
         return jsonify(build_payload(request.args))
     except BadQuery as exc:
@@ -219,20 +246,24 @@ def serialize_detail(d):
             'chatter': d.chart.chatter,
             'watched_from': (d.chart.watched_from.isoformat()
                              if d.chart.watched_from else None),
         },
         'breakdown': {
             'venues': [{'source': v.source, 'mentions': v.mentions,
                         'voices': v.voices} for v in b.venues],
             'bullish': b.bullish,
             'neutral': b.neutral,
             'bearish': b.bearish,
+            # How often the word list and the model read the same post the
+            # opposite way. Both scores exist so this is answerable, and a
+            # disagreement is the sarcasm the lexicon cannot see.
+            'disagreements': b.disagreements,
             'top_author_share': b.top_author_share,
             'top_two_share': b.top_two_share,
             'peak_hour': b.peak_hour.isoformat() + 'Z' if b.peak_hour else None,
             'peak_count': b.peak_count,
             'first_seen': b.first_seen.isoformat() if b.first_seen else None,
             'mentions': b.mentions,
             'voices': b.voices,
         },
         'posts': [{
             'source': p.source,
diff --git a/personal_apps/features/radar/scheduling.py b/personal_apps/features/radar/scheduling.py
index ded2f99..eb80c8a 100644
--- a/personal_apps/features/radar/scheduling.py
+++ b/personal_apps/features/radar/scheduling.py
@@ -23,25 +23,25 @@ SAFETY_FACTOR = 0.5
 MIN_INTERVAL = dt.timedelta(minutes=15)
 MAX_INTERVAL = dt.timedelta(hours=4)
 
 
 def interval_for_rate(rate, floor=None, ceiling=None, page_size=None):
     """How long until this symbol should be polled again.
 
     A rate of None means never measured -- poll soon and find out. A measured
     rate of zero means genuinely silent, so wait the maximum.
 
-    The bounds are arguments because the defaults are StockTwits-shaped and a
-    second source borrowed this scheduler. Reddit's feed holds 25 comments and
-    r/wallstreetbets turns it over in under two minutes, so a fifteen-minute
-    floor would mean never seeing most of it -- and unlike a symbol stream,
-    what is missed is gone rather than merely late.
+    The bounds are arguments because the module defaults do not fit every
+    caller. Reddit's feed holds 25 comments and r/wallstreetbets turns it over
+    in under two minutes, so a fifteen-minute floor would mean never seeing
+    most of it -- and unlike a symbol stream, what is missed is gone rather
+    than merely late.
     """
     floor = floor or MIN_INTERVAL
     ceiling = ceiling or MAX_INTERVAL
     page = page_size or PAGE_SIZE
 
     if rate is None:
         return floor
     if rate <= 0:
         return ceiling
 
@@ -65,25 +65,25 @@ def ensure_tracked(source, symbols, now):
         db.session.add(RadarPollState(source=source, symbol=symbol,
                                       next_due_at=now, observed_rate=None))
         added += 1
     db.session.commit()
     return added
 
 
 def retire_untracked(source, symbols):
     """Drop poll state for symbols this source no longer tracks. Returns how many.
 
-    ONLY for a source whose configured list is the complete set -- Reddit,
-    where REDDIT_SUBS is exhaustive. StockTwits must never call this: its hot
-    set is a rolling window, a ticker falling out of it is temporary, and
-    deleting the row would throw away a real observed_rate that took hours to
-    learn.
+    ONLY for a source whose configured list is the COMPLETE set -- Reddit,
+    where REDDIT_SUBS is exhaustive. A source whose tracked set is a rolling
+    window must never call this: a symbol falling out of the window is
+    temporary, and deleting the row throws away a real observed_rate that took
+    hours to learn.
 
     Needed because due_symbols filters by SOURCE, not by the configured list.
     Without this, removing a subreddit leaves its row behind and the scheduler
     keeps handing it turns forever -- consuming exactly the request budget the
     removal was meant to free, and silently: the sub still appears in the
     logs, still costs feeds, and nothing looks wrong.
     """
     query = RadarPollState.query.filter(RadarPollState.source == source)
     if symbols:
         query = query.filter(RadarPollState.symbol.notin_(list(symbols)))
diff --git a/personal_apps/features/radar/scoring.py b/personal_apps/features/radar/scoring.py
index 6565669..c3c8eee 100644
--- a/personal_apps/features/radar/scoring.py
+++ b/personal_apps/features/radar/scoring.py
@@ -7,66 +7,132 @@ no-print detection need a market feed and belong to Plan 3.
 
 Per (ticker, source), never pooled before scoring: the sources have different
 populations, rhythms and histories, and a ticker can be loud on one while
 silent on another. Pooling happens at read time, over whichever sources the
 viewer selected (spec 8.6).
 """
 import collections
 import dataclasses
 import datetime as dt
 
+import sqlalchemy as sa
+
 from extensions import db
 from models import RadarBucketSource
 
 from . import baselines, profile
 from .config import (ELEVATED_Z, MIN_DISTINCT_AUTHORS, MIN_DISTINCT_CHANNELS,
                      MIN_DISTINCT_TEXT_RATIO, MIN_MENTIONS,
                      SUSTAINED_HOURS_CONSIDERED, SUSTAINED_HOURS_REQUIRED,
-                     VARIANCE_FLOOR, source_config_version)
+                     VARIANCE_FLOOR, expand_sources, source_config_version)
 
 # Weight of the cold-start prior, in units of observed mass. 0.05 of a week is
 # about eight hours: enough to dominate on day one and vanish by week two.
 PRIOR_WEIGHT = 0.05
 
-
-def _rows_by_ticker(source, since, until):
+# Statuses a score may be written onto. NOT the same set baselines are built
+# from: `truncated` counts are real but incomplete, so they are worth ranking
+# and worthless as a description of normal. baselines.usable and
+# profile.build_profile still take `ok` alone.
+#
+# Widened 2026-08-26. Refusing to score truncated rows excluded 90% of Reddit,
+# which produced four elevated rows in four and a half days. An undercounted
+# observation against a correctly-scaled expectation understates z, so the
+# error runs towards silence rather than towards a false spike -- and the row
+# carries the `partial` mark either way.
+SCOREABLE_STATUSES = frozenset({'ok', 'truncated'})
+
+
+def _rows_by_ticker(source, since, until, config_version):
+    """Every row a ticker may be scored or baselined from, THIS generation only.
+
+    Filtered here rather than trusted to baselines.usable() downstream: usable()
+    only screens what feeds the RATE estimate, but the write loop below scores
+    every `ok` row it is handed. Without this filter, a ticker straddling a
+    generation boundary -- some current rows plus an old-generation row that
+    invalidate_incompatible_scores has not yet reached -- would have the old
+    row overwritten with a freshly computed z from the CURRENT baseline, which
+    disguises it as current data while its own source_config_version still
+    says otherwise.
+    """
     rows = (RadarBucketSource.query
             .filter(RadarBucketSource.source == source,
+                    RadarBucketSource.source_config_version == config_version,
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
 
 
+def invalidate_incompatible_scores(version, since, source=None):
+    """Clear expected/variance/mention_z/baseline_days from rows this
+    generation cannot vouch for. Returns rows cleared.
+
+    Two ways a row is incompatible: an explicit different stamp, or SQL NULL
+    -- a row scored before source_config_version existed, or one a bootstrap
+    recovered without yet being restamped. `!= version` alone does not match
+    NULL in SQL (NULL compares unequal to everything, including itself), so
+    it is tested for explicitly rather than trusted to fall out of the
+    inequality.
+
+    Restricted to rows carrying at least one non-NULL score column so a row
+    that was never scored -- already the honest absence this whole change
+    protects -- is not written to for no reason.
+    """
+    query = RadarBucketSource.query.filter(
+        RadarBucketSource.bucket_start >= since,
+        sa.or_(RadarBucketSource.source_config_version.is_(None),
+               RadarBucketSource.source_config_version != version),
+        sa.or_(RadarBucketSource.expected.isnot(None),
+               RadarBucketSource.variance.isnot(None),
+               RadarBucketSource.mention_z.isnot(None),
+               RadarBucketSource.baseline_days.isnot(None)))
+    if source is not None:
+        query = query.filter(RadarBucketSource.source == source)
+    return query.update({'expected': None, 'variance': None, 'mention_z': None,
+                         'baseline_days': None}, synchronize_session=False)
+
+
 def score_source(source, now, lookback_days=30, excluded=None):
     """Score every bucket of every ticker on one source. Returns rows written.
 
     `excluded` is the set of bucket starts to keep out of baselines, wired to
     open spikes in Plan 3 so a ticker that squeezed last week does not carry
     the squeeze into its own expectation.
     """
     excluded = excluded or set()
     since = now - dt.timedelta(days=lookback_days)
     version = source_config_version()
 
-    prof = profile.build_profile(source, now)
-    grouped = _rows_by_ticker(source, since, now)
+    # Defensive, not the primary defence: startup already clears the
+    # migration overlap window once (run_radar_ingest._prepare_rollup_
+    # generation). This is the steady-state backstop for whatever that
+    # window does not reach -- scoped to lookback_days rather than a full
+    # history scan, because _rows_by_ticker's own version filter already
+    # keeps an uncleared old row out of the ticker-level loop below; this
+    # only stops it sitting there forever still LOOKING scored to anything
+    # that reads the column directly (spec: leaderboard ranks on mention_z
+    # IS NOT NULL).
+    invalidate_incompatible_scores(version, since, source=source)
+
+    prof = profile.build_profile(source, now, version)
+    grouped = _rows_by_ticker(source, since, now, version)
 
     # The prior a thin ticker is pulled towards: what a typical ticker on this
     # source does. Spec 6.8 wants a segment median, which needs market cap and
     # therefore Plan 3; a global median is the same shape with a coarser peer
     # group.
     rates = []
     for rows in grouped.values():
         good = baselines.usable(_observations(rows), version, excluded)
         if good:
             rate, _ = baselines.weekly_rate(good, prof)
@@ -76,26 +142,30 @@ def score_source(source, now, lookback_days=30, excluded=None):
     written = 0
     for rows in grouped.values():
         good = baselines.usable(_observations(rows), version, excluded)
         if not good:
             continue
 
         rate, _ = baselines.weekly_rate(good, prof, prior_rate=prior_rate,
                                         prior_weight=PRIOR_WEIGHT)
         k = baselines.dispersion(good, prof, rate)
         span = max(o.bucket_start for o in good) - min(o.bucket_start for o in good)
-        baseline_days = span.days
+        # Fractional. `.days` truncated twenty-three hours to zero, which put
+        # every row under PROVISIONAL_BASELINE_DAYS forever -- a mark that
+        # fires on 100% of a board carries no information.
+        baseline_days = span.total_seconds() / 86400.0
 
         for row in rows:
-            # A source that was down, or a known undercount, has nothing to be
-            # surprised about. Scoring it would invent a reading from a gap.
-            if row.status != 'ok':
+            # A source that was DOWN has nothing to be surprised about --
+            # scoring it would invent a reading from a gap. A source that was
+            # merely incomplete is a different fact: see SCOREABLE_STATUSES.
+            if row.status not in SCOREABLE_STATUSES:
                 continue
 
             expected = baselines.expected_for(rate, prof, row.bucket_start)
             variance = baselines.variance_for(expected, k)
             row.expected = expected
             row.variance = variance
             row.mention_z = ((row.mention_count - expected)
                              / max(variance, VARIANCE_FLOOR) ** 0.5)
             row.baseline_days = baseline_days
             written += 1
@@ -105,23 +175,28 @@ def score_source(source, now, lookback_days=30, excluded=None):
 
 
 def pooled_z(ticker, bucket_start, sources):
     """Combined z over the selected sources. Returns (z, contributing count).
 
     Sums the components rather than averaging the z-scores, because a weighted
     mean of z-scores is not a z-score (spec 6.2). Two sources each two sigma
     over is stronger evidence than either alone; averaging reports the same two
     sigma and throws the corroboration away.
 
-    A source with no scored row for this bucket -- down, or truncated -- drops
-    out of all three sums rather than contributing zero.
+    A source with no scored row for this bucket -- down or otherwise unscored
+    -- drops out of all three sums rather than contributing zero.
+
+    `sources` is a selection and expands STRICTLY: this reads `expected` and
+    `variance`, and the pre-split root `reddit` rows were baselined against a
+    different population (config.expand_sources).
     """
+    sources = expand_sources(sources)
     rows = (RadarBucketSource.query
             .filter(RadarBucketSource.ticker == ticker,
                     RadarBucketSource.bucket_start == bucket_start,
                     RadarBucketSource.source.in_(list(sources)),
                     RadarBucketSource.mention_z.isnot(None))
             .all())
     if not rows:
         return None, 0
 
     observed = sum(r.mention_count for r in rows)
@@ -174,21 +249,24 @@ def is_eligible(contributions):
         and part.text_ratio >= MIN_DISTINCT_TEXT_RATIO
         for kind, part in contributions.items())
 
 
 def window_z(ticker, sources, end, hours):
     """Pooled z over a time window. Returns (z, component parts).
 
     Components are summed across both time and sources for the same reason
     pooled_z sums them: the sum of independent counts has the sum of their
     expectations and variances, and no other combination is a z-score.
+
+    Strict expansion, for pooled_z's reason.
     """
+    sources = expand_sources(sources)
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
diff --git a/personal_apps/features/radar/sources/__init__.py b/personal_apps/features/radar/sources/__init__.py
index d99003e..16bc7c7 100644
--- a/personal_apps/features/radar/sources/__init__.py
+++ b/personal_apps/features/radar/sources/__init__.py
@@ -32,10 +32,31 @@ class FetchResult:
     status: str                      # 'ok' | 'missing' | 'truncated'
     catchup_depth: int = 0
     # Earliest instant this fetch actually covers. Anything the caller asked
     # for before this was not delivered -- Jetstream clamps a too-old cursor
     # silently, and a caller that assumed otherwise would carry a hole it
     # believed was complete. None means the full requested range was covered.
     covered_since: object = None
     # Observed messages/hour per symbol, for the poll scheduler. Empty for
     # sources that are not polled per symbol.
     rates: dict = dataclasses.field(default_factory=dict)
+    # Status per emitted source name, where one fetch covers several. Reddit
+    # reads a slice of subreddits and each is its own source; the rolled-up
+    # `status` above is what the cycle reports, and this is what the rollup
+    # stamps on each source's rows.
+    #
+    # THREE states, and the difference between the last two is the difference
+    # between an absence and a zero:
+    #
+    #   None  -- this fetcher does not report per-source status at all, so
+    #            `status` above applies to the single name it fetches under.
+    #            Bluesky and 4chan.
+    #   {...} -- these names were observed, with these verdicts.
+    #   {}    -- explicitly NO source was observed. Reddit with nothing due
+    #            did not read Reddit: there is no observation to record, so
+    #            the rollup must write no row at all. Not an `ok` zero (a
+    #            bucket child claiming coverage no fetch produced) and not a
+    #            `missing` (which means we tried and failed).
+    #
+    # Consumers must therefore test `is not None`, never truthiness -- the
+    # empty map and the absent map mean opposite things.
+    per_source_status: dict | None = None
diff --git a/personal_apps/features/radar/sources/reddit.py b/personal_apps/features/radar/sources/reddit.py
index 8408440..aa25114 100644
--- a/personal_apps/features/radar/sources/reddit.py
+++ b/personal_apps/features/radar/sources/reddit.py
@@ -123,25 +123,26 @@ def _to_raw_post(entry, sub):
     Zero rather than None: they are engagement weights, and a comment with no
     reported score genuinely contributed no measured engagement -- unlike a
     mention count, where zero and unknown are different facts.
     """
     author = entry.find('a:author/a:name', ATOM)
     link = entry.find('a:link', ATOM)
     created = _stamp(entry)
     if created is None:
         return None
     return RawPost(
-        source='reddit',
+        # The SUBREDDIT is part of the source, not only of the channel. One
+        # name meant one status for the whole cycle, and with one sub read per
+        # cycle that was whichever sub happened to be due -- r/wallstreetbets
+        # is permanently truncated and used to mark every quieter sub with it.
+        source='reddit:%s' % sub,
         external_id=entry.findtext('a:id', '', ATOM),
-        # The subreddit, not 'reddit'. Per-subreddit baselines are not built
-        # yet, but every stored comment records which sub it came from, so the
-        # decision about which subs are worth keeping can be made from data.
         channel=sub,
         author=author.text if author is not None else None,
         created_utc=created,
         title=entry.findtext('a:title', '', ATOM) or None,
         body=_text_of(entry),
         score=0,
         num_comments=0,
         url=link.get('href') if link is not None else '',
     )
 
@@ -155,21 +156,24 @@ def fetch_one(sub, since, client):
     """
     body = client.get_feed(sub)
     try:
         root = ET.fromstring(body)
     except ET.ParseError as exc:
         raise RedditUnavailable(f'r/{sub}: unparseable feed: {exc}') from exc
 
     entries = root.findall('a:entry', ATOM)
     posts = [p for p in (_to_raw_post(e, sub) for e in entries) if p]
     if not posts:
-        return [], 'ok', 0.0
+        # No rate, not a rate of zero. interval_for_rate reads zero as
+        # "genuinely silent" and backs the subreddit off to its ceiling;
+        # None means never measured and schedules a prompt retry instead.
+        return [], 'ok', None
 
     stamps = sorted(p.created_utc for p in posts)
     oldest, newest = stamps[0], stamps[-1]
 
     # Messages an hour, for the poll scheduler. Measured from the feed itself
     # rather than assumed, which is what lets a quiet sub fall to a slow
     # cadence and hand its budget to a busy one.
     span_hours = max((newest - oldest).total_seconds() / 3600, 1 / 3600)
     rate = len(posts) / span_hours
 
@@ -181,21 +185,21 @@ def fetch(since_by_sub, client, pause=REQUEST_INTERVAL_SECONDS):
     """Every subreddit in `since_by_sub`, each read from its OWN cursor.
 
     Per subreddit, not per source, and that is the whole point. One shared
     cursor is advanced to the newest comment seen across the batch, so polling
     r/wallstreetbets moves it to seconds ago and every quieter subreddit
     afterwards has its entire feed filtered out as "already seen". Measured
     2026-08-25: six of eight cycles returned nothing at all for that reason.
 
     `since_by_sub` is already the budgeted, rotated slice -- this module does
     not decide which subreddits are due, because that state belongs to the
-    scheduler that the StockTwits path already uses.
+    poll scheduler in features/radar/scheduling.py, not to this module.
 
     A 429 stops the cycle rather than moving to the next subreddit: the
     penalty is per-IP and asking again immediately deepens it. Whatever was
     collected before the refusal is still returned, because those comments
     were really read.
 
     `rates` carries ONLY the subreddits actually READ, and it is what the
     caller schedules from. The ones after a throttle were never requested, so
     stamping them as polled would push them down the queue for something that
     never happened to them -- and neither is the throttled one, for the same
@@ -203,43 +207,50 @@ def fetch(since_by_sub, client, pause=REQUEST_INTERVAL_SECONDS):
 
     Reversed 2026-08-25. A throttled sub used to be reported at rate zero, so
     the scheduler read it as silent and backed it off. The response headers
     disproved the reasoning behind that: `x-ratelimit-remaining` is 0.0 after
     a SINGLE request, so the budget is one feed per window and everything
     after the first is refused however long the pause. Whichever sub went
     second took the 429 -- two consecutive runs blamed a different one purely
     on ordering. A 429 is a fact about the budget, never about the subreddit.
     """
     posts, statuses, rates = [], [], {}
+    by_sub = {}
 
     for index, (sub, since) in enumerate(since_by_sub.items()):
         if index and pause:
             time.sleep(pause)
         try:
             found, status, rate = fetch_one(sub, since, client)
         except RedditThrottled:
             # Nothing recorded: it was refused, not read, so it stays due and
             # is retried rather than losing its turn.
             statuses.append('missing')
+            by_sub[sub] = 'missing'
             break
         except RedditUnavailable:
             # Attempted and learned nothing. Recorded as unknown so it is
             # retried soon -- unlike a throttle, a 500 says nothing about
             # whether the next request will work.
             statuses.append('missing')
+            by_sub[sub] = 'missing'
             rates[sub] = None
             continue
         posts.extend(found)
         statuses.append(status)
+        by_sub[sub] = status
         rates[sub] = rate
 
-    return FetchResult(posts=posts, status=_roll_up(statuses), rates=rates)
+    return FetchResult(
+        posts=posts, status=_roll_up(statuses), rates=rates,
+        per_source_status={'reddit:%s' % sub: status
+                           for sub, status in by_sub.items()})
 
 
 def _roll_up(statuses):
     """One status for the cycle, worst-case first.
 
     `missing` beats `truncated` beats `ok`, because a bucket may only claim
     the completeness of its least complete contributor. Nothing at all is
     `missing` rather than `ok`: a cycle that read no subreddit did not observe
     a quiet period, it observed nothing.
     """
diff --git a/personal_apps/features/radar/sources/stocktwits.py b/personal_apps/features/radar/sources/stocktwits.py
deleted file mode 100644
index e9f7293..0000000
--- a/personal_apps/features/radar/sources/stocktwits.py
+++ /dev/null
@@ -1,138 +0,0 @@
-# personal_apps/features/radar/sources/stocktwits.py
-"""StockTwits ingest.
-
-Finance-native and dense -- messages arrive already $TICKER-tagged and about
-half carry a native bull/bear label -- but narrow: the discovery surface is the
-30 trending symbols, so the standing set in the scheduler is what widens it.
-
-Crypto is dropped here rather than downstream, using the explicit
-instrument_class field rather than guessing at the .X suffix (spec 3.7).
-"""
-import concurrent.futures
-import datetime as dt
-
-import requests
-
-from . import FetchResult, RawPost
-
-API_BASE = 'https://api.stocktwits.com/api/2'
-USER_AGENT_DEFAULT = 'personal_apps-radar/0.1 (personal research)'
-
-# The API returns at most this many messages per stream call. A full page of
-# messages newer than `since` means there were probably more we never saw.
-PAGE_SIZE = 30
-
-# Measured: a stream call takes ~43 seconds, and trending the same, with
-# timings identical enough to be a deliberate throttle rather than load.
-# Serially that is five minutes for seven symbols against a three-minute
-# cycle, so the calls run concurrently. Kept low because the rate limit is
-# undocumented and a burst is the wrong thing to guess with.
-MAX_CONCURRENCY = 4
-
-
-class StockTwitsUnavailable(Exception):
-    """This symbol's stream did not arrive. Never turns into a zero count."""
-
-
-class StockTwitsClient:
-    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=25):
-        self._headers = {'User-Agent': user_agent}
-        self._timeout = timeout
-
-    def get(self, path, params=None):
-        try:
-            response = requests.get(API_BASE + path, params=params,
-                                    headers=self._headers, timeout=self._timeout)
-            response.raise_for_status()
-            return response.json()
-        except (requests.RequestException, ValueError) as exc:
-            raise StockTwitsUnavailable('%s: %s' % (path, exc)) from exc
-
-
-def trending(client):
-    """Trending equity symbols. Crypto is excluded by instrument_class."""
-    payload = client.get('/trending/symbols.json')
-    return [s['symbol'] for s in payload.get('symbols', [])
-            if (s.get('instrument_class') or '').upper() != 'CRYPTO']
-
-
-def _to_raw_post(message, symbol):
-    created = dt.datetime.strptime(message['created_at'], '%Y-%m-%dT%H:%M:%SZ')
-    user = message.get('user') or {}
-    entities = message.get('entities') or {}
-    sentiment = (entities.get('sentiment') or {}).get('basic')
-    likes = (message.get('likes') or {}).get('total') or 0
-    symbols = [s['symbol'] for s in (message.get('symbols') or [])] or [symbol]
-
-    return RawPost(
-        source='stocktwits',
-        external_id='stocktwits:%s' % message['id'],
-        channel=symbol,
-        author=user.get('username'),
-        created_utc=created,
-        title=None,
-        body=message.get('body') or '',
-        score=int(likes),
-        num_comments=0,
-        url='https://stocktwits.com/message/%s' % message['id'],
-        native_tickers=symbols,
-        native_sentiment=sentiment,
-    )
-
-
-def _fetch_one(client, symbol, since):
-    """One symbol's stream. Returns (posts, rate, truncated) or raises."""
-    payload = client.get('/streams/symbol/%s.json' % symbol)
-    messages = payload.get('messages') or []
-
-    fresh = [p for p in (_to_raw_post(m, symbol) for m in messages)
-             if p.created_utc > since]
-
-    rate = None
-    if messages:
-        stamps = [dt.datetime.strptime(m['created_at'], '%Y-%m-%dT%H:%M:%SZ')
-                  for m in messages]
-        span = (max(stamps) - min(stamps)).total_seconds() / 3600
-        rate = (len(messages) / span) if span > 0 else float(len(messages))
-
-    # A full page, all of it new, means the window very likely overflowed.
-    return fresh, rate, len(fresh) >= PAGE_SIZE
-
-
-def fetch(since, client, symbols, max_workers=MAX_CONCURRENCY):
-    """Every message newer than `since` across `symbols`.
-
-    Requests run concurrently because each takes ~43 seconds against a
-    three-minute cycle; serially, seven symbols would not fit.
-
-    Also reports observed messages/hour per symbol, which is what lets the
-    scheduler poll a hot symbol often and a quiet one rarely (spec 3.5).
-    """
-    if not symbols:
-        return FetchResult(posts=[], status='ok')
-
-    posts, rates = [], {}
-    failures = 0
-    truncated = False
-
-    workers = max(1, min(max_workers, len(symbols)))
-    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
-        futures = {pool.submit(_fetch_one, client, symbol, since): symbol
-                   for symbol in symbols}
-        for future in concurrent.futures.as_completed(futures):
-            symbol = futures[future]
-            try:
-                fresh, rate, overflowed = future.result()
-            except StockTwitsUnavailable:
-                failures += 1
-                continue
-            posts.extend(fresh)
-            if rate is not None:
-                rates[symbol] = rate
-            truncated = truncated or overflowed
-
-    if failures == len(symbols):
-        return FetchResult(posts=[], status='missing')
-
-    status = 'truncated' if (truncated or failures) else 'ok'
-    return FetchResult(posts=posts, status=status, rates=rates)
diff --git a/personal_apps/features/radar/spend.py b/personal_apps/features/radar/spend.py
index 0ef3e80..0f67317 100644
--- a/personal_apps/features/radar/spend.py
+++ b/personal_apps/features/radar/spend.py
@@ -25,29 +25,28 @@ from models import RadarLlmSpend
 MODEL_RATES = {
     'claude-haiku-4-5': (1.00, 5.00),
     'claude-sonnet-5': (3.00, 15.00),
     'claude-opus-5': (5.00, 25.00),
 }
 
 MICROS_PER_USD = 1_000_000
 
 
 def cost_micros(model, input_tokens, output_tokens):
-    """Integer micro-dollars for this usage at the current rate.
+    """Integer micro-dollars for this usage, or None at an unknown rate.
 
-    Zero for a model with no rate on file. Guessing one would produce a number
-    that looks authoritative and is invented; the tokens are still recorded, so
-    the omission is visible and fixable later.
+    None is not zero: zero says the call was free. The usage is still recorded,
+    and summary() exposes its tokens without inventing a dollar amount.
     """
     rate = MODEL_RATES.get(model)
     if rate is None:
-        return 0
+        return None
     per_in, per_out = rate
     return round((input_tokens * per_in + output_tokens * per_out)
                  * MICROS_PER_USD / 1_000_000)
 
 
 def record(model, calls, input_tokens, output_tokens, day=None):
     """Add one pass's usage to its day. Returns nothing.
 
     A call that used nothing writes nothing. A zero row would make an outage
     look like a quiet day, which is the confusion the bucket statuses exist to
@@ -60,48 +59,63 @@ def record(model, calls, input_tokens, output_tokens, day=None):
 
     row = RadarLlmSpend.query.filter_by(day=day, model=model).one_or_none()
     if row is None:
         row = RadarLlmSpend(day=day, model=model, calls=0, input_tokens=0,
                             output_tokens=0, cost_micros=0)
         db.session.add(row)
 
     row.calls += calls
     row.input_tokens += input_tokens
     row.output_tokens += output_tokens
-    # Added at the rate that applies NOW, so a later price change cannot reach
-    # backwards into a day that was already paid for.
-    row.cost_micros += cost_micros(model, input_tokens, output_tokens)
+    cost = cost_micros(model, input_tokens, output_tokens)
+    if cost is not None:
+        # Added at the rate that applies NOW, so a later price change cannot
+        # reach backwards into a day that was already paid for.
+        row.cost_micros += cost
     db.session.commit()
 
 
 def _usd(micros):
     """Micros to dollars, as a float.
 
     float() is not decoration. SUM() over a BIGINT returns Decimal on MySQL
     and MariaDB, Decimal divided by an int stays Decimal, and Flask's JSON
     encoder raises on Decimal -- so the board would 500 the moment the first
     spend row existed, and only then. The same trap cost an afternoon in
     leaderboard.build_rows.
     """
     return float(micros or 0) / MICROS_PER_USD
 
 
 def summary(today=None):
-    """Today and month-to-date, in dollars.
+    """Today and month-to-date dollars plus tokens at an unknown rate.
 
     Month-to-date rather than a rolling thirty days: this is read against what
     was loaded onto the account, and that is billed by calendar month.
     """
     if today is None:
         today = dt.datetime.now(dt.timezone.utc).date()
     first = today.replace(day=1)
 
     def total(since, until):
         return db.session.query(
             sa.func.coalesce(sa.func.sum(RadarLlmSpend.cost_micros), 0)).filter(
                 RadarLlmSpend.day >= since,
                 RadarLlmSpend.day <= until).scalar()
 
+    def unpriced(since, until):
+        """Tokens booked to models whose rate is absent from MODEL_RATES."""
+        total = db.session.query(
+            sa.func.coalesce(
+                sa.func.sum(RadarLlmSpend.input_tokens
+                            + RadarLlmSpend.output_tokens), 0)).filter(
+                RadarLlmSpend.day >= since,
+                RadarLlmSpend.day <= until,
+                RadarLlmSpend.model.notin_(list(MODEL_RATES))).scalar()
+        # SUM over BIGINT is Decimal on MySQL/MariaDB; JSON needs an int.
+        return int(total or 0)
+
     return {
         'today_usd': _usd(total(today, today)),
         'month_usd': _usd(total(first, today)),
+        'unpriced_tokens': unpriced(first, today),
     }
diff --git a/personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py b/personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py
new file mode 100644
index 0000000..434c154
--- /dev/null
+++ b/personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py
@@ -0,0 +1,91 @@
+"""widen radar source columns
+
+Revision ID: 08316d3e4d77
+Revises: 1d26ac48e744
+Create Date: 2026-08-27 02:01:16.469834
+
+"""
+from alembic import op
+import sqlalchemy as sa
+
+
+# revision identifiers, used by Alembic.
+revision = '08316d3e4d77'
+down_revision = '1d26ac48e744'
+branch_labels = None
+depends_on = None
+
+
+def upgrade():
+    # Expand before any writer emits `reddit:<sub>`. MySQL/MariaDB DDL is
+    # non-transactional, so each MODIFY may commit independently.
+    op.alter_column('radar_posts', 'source',
+                    existing_type=sa.String(length=16),
+                    type_=sa.String(length=48), existing_nullable=False)
+    # radar_bucket_sources is PARTITIONED, and `source` is part of its primary
+    # key. MODIFY COLUMN rebuilds the table; at ~300k rows that is seconds, but
+    # it is not online -- expect the ingest daemon's writes to block briefly.
+    op.alter_column('radar_bucket_sources', 'source',
+                    existing_type=sa.String(length=24),
+                    type_=sa.String(length=48), existing_nullable=False)
+    op.alter_column('radar_poll_state', 'source',
+                    existing_type=sa.String(length=24),
+                    type_=sa.String(length=48), existing_nullable=False)
+
+
+def downgrade():
+    """Narrow the three columns back. NOT semantically lossless -- read this.
+
+    What it restores: old code can write and read Reddit posts again, because
+    radar_posts.source is normalised back to the bare `reddit` below.
+
+    What it CANNOT restore: the per-subreddit bucket history. Rows in
+    radar_bucket_sources written as `reddit:<sub>` cannot be re-aggregated
+    into a single `reddit` row -- each carries its own mention_count,
+    distinct_authors, distinct_text_ratio and status, and summing counts while
+    taking a max of author counts and a worst-case of statuses invents an
+    aggregate that was never observed. They are left under their prefixed
+    names, where post-downgrade code reading `source = 'reddit'` will not see
+    them: the Reddit history written during the upgraded period reads as
+    absent rather than as a wrong number. radar_mention_events keeps its
+    prefixed names for the same reason (its column was already 48 and is not
+    touched here).
+
+    A re-upgrade therefore recovers the bucket history intact; it is only
+    invisible while rolled back.
+
+    WIDTH DEPENDENCY on radar_bucket_sources. Unlike radar_posts, that table
+    is narrowed 48 -> 24 with no normalisation, so every prefixed name it
+    holds must already fit in 24 characters. The longest configured name is
+    `reddit:smallstreetbets` at 22. Adding a subreddit whose name exceeds 17
+    characters -- RadarPollState.symbol's own comment cites the
+    20-character RobinHoodPennyStocks, which would give a 27-character source
+    -- makes this statement fail with MySQL 1406, AFTER the radar_poll_state
+    DDL above has already auto-committed. The check below turns that into a
+    readable error instead of a half-applied rollback.
+    """
+    op.alter_column('radar_poll_state', 'source',
+                    existing_type=sa.String(length=48),
+                    type_=sa.String(length=24), existing_nullable=False)
+    too_long = op.get_bind().execute(sa.text(
+        "SELECT COUNT(*) FROM radar_bucket_sources "
+        "WHERE CHAR_LENGTH(source) > 24")).scalar()
+    # int() at the boundary: COUNT is Decimal on MySQL and MariaDB alike.
+    if int(too_long or 0):
+        raise RuntimeError(
+            'radar_bucket_sources holds %d source name(s) longer than 24 '
+            'characters; narrowing the column would truncate them. Decide '
+            'what those rows should become and delete or rename them before '
+            'rolling this migration back.' % int(too_long))
+    op.alter_column('radar_bucket_sources', 'source',
+                    existing_type=sa.String(length=48),
+                    type_=sa.String(length=24), existing_nullable=False)
+    # Old code can only write/read aggregate Reddit posts. Atom comment IDs
+    # are globally unique, so collapsing the source component cannot collide
+    # on uq_radar_post_source_ext.
+    op.execute(sa.text(
+        "UPDATE radar_posts SET source = 'reddit' "
+        "WHERE source LIKE 'reddit:%'"))
+    op.alter_column('radar_posts', 'source',
+                    existing_type=sa.String(length=48),
+                    type_=sa.String(length=16), existing_nullable=False)
diff --git a/personal_apps/migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py b/personal_apps/migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py
new file mode 100644
index 0000000..09d6d79
--- /dev/null
+++ b/personal_apps/migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py
@@ -0,0 +1,38 @@
+"""widen radar bucket sources baseline days
+
+Revision ID: 35c3ae366677
+Revises: 08316d3e4d77
+Create Date: 2026-08-27 15:56:10.620302
+
+"""
+from alembic import op
+import sqlalchemy as sa
+from sqlalchemy.dialects import mysql
+
+# revision identifiers, used by Alembic.
+revision = '35c3ae366677'
+down_revision = '08316d3e4d77'
+branch_labels = None
+depends_on = None
+
+
+def upgrade():
+    # Float since 2026-08-26. SmallInteger stored span.days, and .days
+    # truncated twenty-three hours of history to zero -- which put every row
+    # on the board under PROVISIONAL_BASELINE_DAYS permanently (147,228 of
+    # 147,429 scored Bluesky rows in production).
+    op.alter_column('radar_bucket_sources', 'baseline_days',
+                    existing_type=mysql.SMALLINT(),
+                    type_=sa.Float(), existing_nullable=True)
+
+
+def downgrade():
+    # DESTRUCTIVE: narrows Float back to SMALLINT, which truncates any
+    # fractional value written since the upgrade (e.g. 0.375 -> 0) --
+    # silently reversing the fix this migration exists to make (see
+    # upgrade()'s comment: SmallInteger truncation put 147,228 of 147,429
+    # scored rows under PROVISIONAL_BASELINE_DAYS permanently). Do not run
+    # this against a database carrying real scored history.
+    op.alter_column('radar_bucket_sources', 'baseline_days',
+                    existing_type=sa.Float(),
+                    type_=mysql.SMALLINT(), existing_nullable=True)
diff --git a/personal_apps/models.py b/personal_apps/models.py
index f5e9a3f..6e06e0e 100644
--- a/personal_apps/models.py
+++ b/personal_apps/models.py
@@ -549,21 +549,22 @@ class RadarPost(db.Model):
     the 64KB TEXT limit once utf8mb4 puts up to 4 bytes behind each one.
     """
     __tablename__ = 'radar_posts'
     __table_args__ = (
         db.UniqueConstraint('source', 'external_id', name='uq_radar_post_source_ext'),
         db.Index('ix_radar_posts_created_utc', 'created_utc'),
         {'mysql_charset': 'utf8mb4'},
     )
 
     id           = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
-    source       = db.Column(db.String(16), nullable=False)
+    # Reddit carries the subreddit in the durable source name.
+    source       = db.Column(db.String(48), nullable=False)
     # 128, not 32: a Bluesky id is 'bluesky:<did>:<rkey>' and a DID alone is
     # 32 characters. The original width was sized for Reddit fullnames.
     external_id  = db.Column(db.String(128), nullable=False)
     channel      = db.Column(db.String(64), nullable=False)
     author       = db.Column(db.String(64), nullable=True)
     created_utc  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
     title        = db.Column(db.String(512), nullable=True)
     body         = db.Column(MEDIUMTEXT, nullable=True)
     score        = db.Column(db.Integer, nullable=False, default=0)
     num_comments = db.Column(db.Integer, nullable=False, default=0)
@@ -606,21 +607,21 @@ class RadarMention(db.Model):
     lexicon_sentiment = db.Column(db.Float, nullable=True)
     llm_sentiment     = db.Column(db.String(16), nullable=True)
 
     post = db.relationship('RadarPost', back_populates='mentions')
 
 
 class RadarBucket(db.Model):
     """(ticker x 15 minutes). Retained forever; this is what scoring reads.
 
     Status is per source, not per bucket. With one column and two sources,
-    StockTwits dropping while Reddit keeps working forces a choice between
+    Bluesky dropping while Reddit keeps working forces a choice between
     discarding good Reddit data and silently halving the count -- the second
     being exactly the baseline poisoning the status column exists to prevent
     (spec 4.5).
 
     The mention_z_* and baseline_days_* columns are written by Plan 2 and are
     NULL until then.
     """
     __tablename__ = 'radar_buckets'
     __table_args__ = (
         db.UniqueConstraint('ticker', 'bucket_start', name='uq_radar_bucket'),
@@ -671,21 +672,23 @@ class RadarBucketSource(db.Model):
     """
     __tablename__ = 'radar_bucket_sources'
     __table_args__ = (
         db.Index('ix_radar_bucket_sources_start', 'bucket_start', 'source'),
         {'mysql_charset': 'utf8mb4'},
     )
 
     ticker                    = db.Column(db.String(12, collation='utf8mb4_bin'),
                                           primary_key=True)
     bucket_start              = db.Column(MYSQL_DATETIME(fsp=6), primary_key=True)
-    source                    = db.Column(db.String(24), primary_key=True)
+    # 48, not 24: a Reddit source name carries its subreddit
+    # (`reddit:smallstreetbets` is 22 characters and the margin at 24 was two).
+    source                    = db.Column(db.String(48), primary_key=True)
 
     mention_count             = db.Column(db.Integer, nullable=False, default=0)
     high_confidence_count     = db.Column(db.Integer, nullable=False, default=0)
     low_count                 = db.Column(db.Integer, nullable=False, default=0)
     distinct_authors          = db.Column(db.Integer, nullable=False, default=0)
     distinct_text_ratio       = db.Column(db.Float, nullable=False, default=1.0)
     engagement_weighted_count = db.Column(db.Float, nullable=False, default=0.0)
     sentiment_mean            = db.Column(db.Float, nullable=True)
     sentiment_stdev           = db.Column(db.Float, nullable=True)
 
@@ -699,35 +702,38 @@ class RadarBucketSource(db.Model):
     #
     # Nullable because rows already written have no value, and back-filling a
     # version they were not collected under would be a lie. baselines.usable
     # treats a mismatch as unusable, so those rows simply age out of the window.
     source_config_version     = db.Column(db.String(16), nullable=True)
 
     # Written by the scoring pass.
     expected                  = db.Column(db.Float, nullable=True)
     variance                  = db.Column(db.Float, nullable=True)
     mention_z                 = db.Column(db.Float, nullable=True)
-    baseline_days             = db.Column(db.SmallInteger, nullable=True)
+    # Float since 2026-08-26. SmallInteger meant span.days, and .days truncated
+    # twenty-three hours of history to zero -- which put every row on the board
+    # under PROVISIONAL_BASELINE_DAYS permanently.
+    baseline_days             = db.Column(db.Float, nullable=True)
 
 
 class RadarPollState(db.Model):
     """When each symbol was last polled, and when it is next due.
 
     Per source, because the same symbol has a different message rate on each.
     """
     __tablename__ = 'radar_poll_state'
     __table_args__ = (
         db.Index('ix_radar_poll_state_due', 'source', 'next_due_at'),
         {'mysql_charset': 'utf8mb4'},
     )
 
-    source          = db.Column(db.String(24), primary_key=True)
+    source          = db.Column(db.String(48), primary_key=True)
     # 64, not 12. This holds whatever the source polls by, and that stopped
     # being a ticker when Reddit reused the scheduler with the SUBREDDIT as
     # the unit -- `RobinHoodPennyStocks` is 20 characters, and at 12 the whole
     # insert failed on the daemon's first cycle.
     symbol          = db.Column(db.String(64, collation='utf8mb4_bin'),
                                 primary_key=True)
     last_polled_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
     next_due_at     = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
     observed_rate   = db.Column(db.Float, nullable=True)   # messages per hour
 
diff --git a/personal_apps/run_radar_ingest.py b/personal_apps/run_radar_ingest.py
index 872cd48..2369263 100644
--- a/personal_apps/run_radar_ingest.py
+++ b/personal_apps/run_radar_ingest.py
@@ -2,62 +2,60 @@
 
 Mirrors run_gym_notifier.py: an APScheduler process holding a Flask app
 context, deployed as its own systemd unit and restarted by the VPS deploy
 script.
 
 Cadence is chosen per cycle from the NYSE session rather than fixed, because
 chatter volume follows the session and polling overnight at session rates is
 wasted work. The state comes from the exchange calendar, never from local time
 -- see the DST note in features/radar/market_calendar.py.
 
-Three sources run behind one contract. Nothing here branches on which source is
-which beyond building its fetcher; a fourth would be a module in sources/ plus
-an entry in config.SOURCES.
+Every source runs behind one contract. Nothing here branches on which source
+is which beyond building its fetcher; a new one is a module in sources/ plus
+an entry in config.SOURCES. StockTwits was one of these until 2026-08-26,
+when Cloudflare bot management -- refusing every request, from launch --
+made it not worth defeating a bot challenge to keep.
 """
 import datetime as dt
 import logging
 import time
 
 import sqlalchemy as sa
 from apscheduler.schedulers.background import BackgroundScheduler
 
 from app import app
 from extensions import db
 from models import RadarPollState
 from features.radar import (
-    history, ingest, llm_sentiment, market_calendar, quotes, retention,
-    scheduling, scoring, universe)
+    history, ingest, journal, llm_sentiment, market_calendar, quotes,
+    retention, scheduling, scoring, universe)
 from features.radar.prices import finnhub as finnhub_provider
 from features.radar.prices import twelvedata as twelvedata_provider
 from features.radar.config import (
-    REDDIT_INTERVAL_SECONDS, REDDIT_MAX_POLL, REDDIT_MIN_POLL, REDDIT_SUBS,
-    REDDIT_SUBS_PER_CYCLE, SOURCES, STOCKTWITS_REQUESTS_PER_HOUR,
-    prefer_ipv4_if_configured)
-from features.radar.sources import bluesky, fourchan, reddit, stocktwits
+    MENTION_EVENT_RETENTION_HOURS, REDDIT_INTERVAL_SECONDS, REDDIT_MAX_POLL,
+    REDDIT_MIN_POLL, REDDIT_SUBS, REDDIT_SUBS_PER_CYCLE, SOURCES,
+    expand_sources, prefer_ipv4_if_configured, source_config_version)
+from features.radar.sources import bluesky, fourchan, reddit
 from features.radar.sources import FetchResult
 
 logger = logging.getLogger('radar.ingest')
 
 INTERVALS = {
     'premarket': 180,
     'regular': 180,
     'afterhours': 600,
     'closed': 1800,
 }
 # An unrecognized state polls at the slowest rate. Failing towards fewer
 # requests is the safe direction when the alternative is hammering an API.
 FALLBACK_INTERVAL = 1800
 
-# Cycles per hour at the fastest cadence, used to divide the hourly budget.
-_CYCLES_PER_HOUR = 20
-SYMBOL_BUDGET_PER_CYCLE = max(1, STOCKTWITS_REQUESTS_PER_HOUR // _CYCLES_PER_HOUR)
-
 # Finnhub's free tier is 60 calls a minute. Quotes go to the tickers actually
 # on the board, not to all 12,000 in the universe -- a quote for a ticker
 # nobody is discussing answers a question nobody asked.
 QUOTE_LIMIT = 50
 QUOTE_INTERVAL_MINUTES = 5
 
 # Twelve Data allows 800 requests a day and volatility moves on the scale of
 # weeks, so this is deliberately slow and small.
 SIGMA_LIMIT = 60
 SIGMA_INTERVAL_HOURS = 12
@@ -92,130 +90,103 @@ def _utcnow():
     return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
 
 def interval_for(state):
     return INTERVALS.get(state, FALLBACK_INTERVAL)
 
 
 def current_state(now_utc):
     return market_calendar.session_state(now_utc)
 
 
-def _stocktwits_fetcher(client):
-    """Trending is both the discovery surface and how the polled set grows.
-
-    Symbols accumulate: every symbol that has ever trended stays tracked, so
-    the standing set builds itself rather than waiting on a market-cap source
-    the free tier does not provide.
-    """
-    def fetch(since):
-        now = _utcnow()
-        discovery_failed = False
-        try:
-            hot = stocktwits.trending(client)
-            scheduling.ensure_tracked('stocktwits', hot, now)
-        except stocktwits.StockTwitsUnavailable as exc:
-            # One bad trending call must not cost the cycle its polled set.
-            # The reason is logged: "unavailable" alone is not diagnosable, and
-            # a blocked IP looks identical to a rate limit without it.
-            discovery_failed = True
-            logger.warning('stocktwits trending unavailable this cycle: %s', exc)
-
-        symbols = scheduling.due_symbols('stocktwits', now,
-                                         limit=SYMBOL_BUDGET_PER_CYCLE)
-
-        if discovery_failed and not symbols:
-            # Nothing reached us and nothing was left to try, so this source
-            # saw nothing -- which is `missing`, not a quiet period. Reporting
-            # `ok` here wrote zero-count buckets for a source that was 403 on
-            # every request, and thirty days of those would make any later
-            # StockTwits data read as an enormous spike.
-            return FetchResult(posts=[], status='missing')
-
-        result = stocktwits.fetch(since, client, symbols)
-        for symbol in symbols:
-            scheduling.record_poll('stocktwits', symbol, now,
-                                   result.rates.get(symbol))
-        return result
-    return fetch
-
-
 def _reddit_fetcher(client):
     """Reddit, a budgeted slice of subreddits per cycle.
 
     The feed holds 25 comments and has no cursor, so how often a subreddit is
     read IS its coverage -- r/wallstreetbets turns over in under two minutes.
     Reading all eighteen every cycle would be six requests a minute, which is
     well past what earned a sustained 429 during measurement, so they rotate
-    through the same scheduler StockTwits symbols use: most-overdue first, so
+    through the poll scheduler's due-symbol ordering: most-overdue first, so
     a backlog larger than the budget rotates instead of starving the same subs
     forever.
 
     The observed rate comes back from the feed itself, which lets a quiet sub
     fall to a slow cadence and hand its share of the budget to a busy one.
     """
     def fetch(since):
         now = _utcnow()
+        # Poll state stays keyed by the bare source name with the subreddit as
+        # its symbol. Only what the POSTS carry is prefixed -- the scheduler's
+        # unit is the subreddit either way, and re-keying it would retire every
+        # learned observed_rate on deploy.
         scheduling.ensure_tracked('reddit', REDDIT_SUBS, now)
         # And drop the ones no longer configured. due_symbols filters by
         # SOURCE rather than by this list, so a removed subreddit would keep
         # its poll state and keep taking turns -- spending the very budget its
         # removal was meant to free, while still appearing in the logs as
-        # though nothing had changed. Reddit can do this and StockTwits
-        # cannot: REDDIT_SUBS is the complete set, while a hot ticker falling
-        # out of StockTwits' rolling window is temporary.
+        # though nothing had changed. Reddit can do this because REDDIT_SUBS
+        # is the complete set; a source whose tracked set is a rolling window
+        # must never call this, since a symbol falling out of it is temporary.
         retired = scheduling.retire_untracked('reddit', REDDIT_SUBS)
         if retired:
             logger.info('radar reddit retired %d subreddit(s) '
                         'no longer configured', retired)
         subs = scheduling.due_symbols('reddit', now, limit=REDDIT_SUBS_PER_CYCLE)
         if not subs:
             # Nothing due. Every subreddit was read inside its own interval,
             # so coverage IS current -- this is no work to do, not a failure.
             # `missing` here made six of eight cycles look like outages in the
             # log and hid the real ones among them.
-            return FetchResult(posts=[], status='ok')
+            #
+            # And an EXPLICITLY EMPTY per-source map, not the default None.
+            # Reddit was not read at all this cycle, so it made no observation
+            # -- there is nothing to record. None would fall through to
+            # ingest's `{source: result.status}` fallback, stamp
+            # `{'reddit': 'ok'}` onto the rollup and write a zero-count child
+            # row named `reddit` into every bucket any OTHER source touched,
+            # claiming coverage no fetch produced. This is the common path --
+            # six of eight cycles have nothing due -- so that zero would be
+            # the normal case rather than an edge one.
+            return FetchResult(posts=[], status='ok', per_source_status={})
 
         # Each subreddit reads from when IT was last polled, never from a
         # cursor shared across the source. Shared, the busiest sub sets a
         # watermark that permanently excludes every quieter one.
         rows = {row.symbol: row.last_polled_at for row in
                 RadarPollState.query.filter(
                     RadarPollState.source == 'reddit',
                     RadarPollState.symbol.in_(subs)).all()}
         since_by_sub = {sub: (rows.get(sub) or since) for sub in subs}
 
         result = reddit.fetch(since_by_sub, client)
         # Only what was actually attempted. A throttle stops the cycle, and
         # stamping the subreddits after it as polled would push them down the
         # queue for a request that was never made -- so they would lose their
         # turn to the ones that happened to be earlier in the batch.
         for sub, rate in (result.rates or {}).items():
-            # This source's own bounds. The scheduler's defaults are
-            # StockTwits-shaped, and a fifteen-minute floor would lose most of
-            # r/wallstreetbets -- whose feed holds 25 comments and turns over
-            # in under two minutes.
+            # This source's own bounds, not the scheduler's generic defaults:
+            # a fifteen-minute floor would lose most of r/wallstreetbets --
+            # whose feed holds 25 comments and turns over in under two
+            # minutes.
             scheduling.record_poll('reddit', sub, now, rate,
                                    floor=REDDIT_MIN_POLL,
                                    ceiling=REDDIT_MAX_POLL,
                                    page_size=reddit.FEED_LIMIT)
         return result
     return fetch
 
 
 def build_fetchers():
     """One callable per active source, each taking `since`."""
-    st_client = stocktwits.StockTwitsClient()
     fc_client = fourchan.FourChanClient()
     rd_client = reddit.RedditClient()
 
     return {
-        'stocktwits': _stocktwits_fetcher(st_client),
         'bluesky': lambda since: bluesky.fetch(since, bluesky.live_drain),
         'fourchan': lambda since: fourchan.fetch(
             since, fc_client, pause=fourchan.REQUEST_INTERVAL_SECONDS),
         'reddit': _reddit_fetcher(rd_client),
     }
 
 
 def tick(now_utc, fetchers):
     """One cycle across every source, with failures contained.
 
@@ -256,21 +227,21 @@ def score_all(now_utc):
 
     Separate from ingest and slower -- it walks thirty days of buckets per
     ticker, so it runs on its own schedule rather than inside a three-minute
     cycle.
 
     Failures are isolated per source for the same reason ingest isolates them:
     one source's baseline going wrong is not a reason to leave the rest
     unscored.
     """
     written = {}
-    for source in SOURCES:
+    for source in expand_sources(SOURCES):
         try:
             written[source] = scoring.score_source(
                 source, now_utc.replace(tzinfo=None))
         except Exception:
             logger.exception('radar scoring failed for %s', source)
             written[source] = 0
     return written
 
 
 def _scheduled_scoring():
@@ -477,20 +448,23 @@ def _scheduled_prune():
         now = _utcnow()
         deleted = retention.prune_posts(now)
         if deleted:
             logger.info('radar retention pruned %d posts', deleted)
         # Quotes were never pruned at all, and since the board began reading
         # them on every load (2026-08-24) that table is the one most likely to
         # slowly undo the work that made it fast.
         quotes = retention.prune_quotes(now)
         if quotes:
             logger.info('radar retention pruned %d quotes', quotes)
+        events = retention.prune_mention_events(now)
+        if events:
+            logger.info('radar retention pruned %d mention events', events)
 
 
 def _scheduled_sentiment():
     """The model re-read of tone, spec 6.11.
 
     Its own job rather than part of a cycle, and deliberately: ingest must
     never wait on an external API, and a source that failed must never be able
     to fail because sentiment did. Nothing downstream blocks on this -- a
     mention with no verdict simply keeps answering on its lexicon score.
     """
@@ -502,24 +476,93 @@ def _scheduled_sentiment():
             # API key raises at client construction, and taking the whole
             # daemon down over an optional enrichment would cost the ingest
             # this exists to decorate.
             logger.exception('radar sentiment pass failed')
             return
         if judged:
             logger.info('radar sentiment judged %d mentions, %d still waiting',
                         judged, llm_sentiment.pending_count())
 
 
+def _prepare_rollup_generation(now):
+    """Recover retained evidence and clear incompatible scores, once, before
+    any fetcher or scheduler exists.
+
+    Two things happen here and neither can wait for the first ingest cycle:
+
+    Bootstrap first. The mention journal is empty immediately after migration
+    (Task 1), so if the first cycle rebuilt an already-open quarter-hour
+    straight from its own cursor slice, that would repeat the exact overwrite
+    this generation exists to fix -- once, on the one window unlucky enough to
+    still be open at deploy time. journal.bootstrap_from_mentions replays the
+    retained radar_posts x radar_mentions evidence back through record() so
+    that window rebuilds complete instead.
+
+    Then the zero-recovery check. A fresh or genuinely quiet database recovers
+    zero events because there is nothing to recover, and must be allowed to
+    start. A migrated database whose retained evidence failed to bootstrap for
+    some other reason ALSO recovers zero events, and the two are
+    indistinguishable from the count alone -- an absence is never a zero. A
+    legacy RadarBucketSource already showing real high_confidence_count in the
+    same overlap window is what tells them apart: it is proof the evidence
+    existed, so recovering none of it means bootstrap is broken, not that the
+    world was quiet. Continuing anyway would serve relabelled scores over
+    evidence that never actually made it into the journal, so this raises
+    instead and lets the caller's lack of a try/except abort startup.
+
+    Finally, incompatible scores in the same window are cleared so nothing
+    still shows a generation-1 z-score under the generation-2 stamp before the
+    first cycle even runs. score_source repeats a narrower version of this
+    check every fifteen minutes as a backstop; this is the one-time pass for
+    the migration boundary itself.
+    """
+    from models import RadarBucketSource
+
+    with app.app_context():
+        since = now.replace(tzinfo=None) - dt.timedelta(
+            hours=MENTION_EVENT_RETENTION_HOURS)
+        recovered = journal.bootstrap_from_mentions(since)
+        if recovered == 0:
+            legacy = (RadarBucketSource.query
+                     .filter(RadarBucketSource.bucket_start >= since,
+                             RadarBucketSource.high_confidence_count > 0)
+                     .first())
+            if legacy is not None:
+                raise RuntimeError(
+                    'radar rollup bootstrap recovered zero mention events, '
+                    'but a legacy bucket in the same overlap window '
+                    '(ticker=%s source=%s bucket_start=%s) already carries '
+                    'high_confidence_count > 0 -- refusing to start ingest '
+                    'against evidence that failed to bootstrap' %
+                    (legacy.ticker, legacy.source, legacy.bucket_start))
+
+        invalidated = scoring.invalidate_incompatible_scores(
+            source_config_version(), since)
+        db.session.commit()
+        return recovered, invalidated
+
+
 def main():
     logging.basicConfig(level=logging.INFO)
     if prefer_ipv4_if_configured():
         logger.info('RADAR_FORCE_IPV4 set -- outbound HTTP will skip AAAA records')
+
+    # Ahead of build_fetchers and the scheduler, deliberately -- no cycle may
+    # run against a mixed-generation database, and the zero-recovery check
+    # above needs to see the pre-startup state before anything else touches
+    # it. Uncaught on purpose: a bootstrap or invalidation failure must abort
+    # the daemon rather than start ingest over evidence it could not recover.
+    recovered, invalidated = _prepare_rollup_generation(
+        dt.datetime.now(dt.timezone.utc))
+    logger.info('radar rollup generation prepared: recovered=%d invalidated=%d',
+               recovered, invalidated)
+
     fetchers = build_fetchers()
 
     scheduler = BackgroundScheduler(timezone='UTC')
     # next_run_time is not a nicety. An interval trigger otherwise fires only
     # after the first interval has elapsed, so starting the service overnight
     # means thirty minutes of silence before any evidence it works -- and the
     # same wait after every deploy restart. Catch-up is cursor-driven, so an
     # immediate first cycle costs nothing and collects the gap.
     # Reddit is pulled out of the session-driven cycle: it needs a fixed
     # cadence of its own, and the reason is in _scheduled_reddit.
diff --git a/personal_apps/scripts/backfill_radar_buckets.py b/personal_apps/scripts/backfill_radar_buckets.py
new file mode 100644
index 0000000..b00d2e8
--- /dev/null
+++ b/personal_apps/scripts/backfill_radar_buckets.py
@@ -0,0 +1,183 @@
+"""Repair bucket counts the pre-2026-08-26 rollup truncated.
+
+roll_up rebuilt each bucket from one cycle's cursor slice and overwrote, so a
+quarter-hour touched by several cycles kept only the last one. Measured across
+the live corpus: 14.1% of Bluesky's high-confidence mentions and 16.0% of
+Reddit's never reached a bucket, rising to 42.9% on the 10+ mention buckets.
+
+Also clears the scoring columns off rows that changed status after being
+scored. Task 3 stopped roll_up producing those, but could not reach the 399
+that already existed -- a closed quarter-hour is never touched again.
+
+PARTIAL BY CONSTRUCTION. radar_mentions holds every mention of every STORED
+post, which is exactly the `high` set. Promoted `medium` mentions came from
+posts that were never stored -- the journal that would have kept them did not
+exist -- so they cannot be recovered and mention_count stays understated by
+that amount. low_count likewise. Neither is read by any surface.
+
+Read-only until --apply. Run from personal_apps/:
+
+    python -m scripts.backfill_radar_buckets            # report
+    python -m scripts.backfill_radar_buckets --apply    # write
+"""
+import argparse
+import datetime as dt
+import math
+import sys
+
+import sqlalchemy as sa
+
+sys.path.insert(0, '.')
+
+from app import app                                        # noqa: E402
+from extensions import db                                  # noqa: E402
+from models import RadarBucketSource                       # noqa: E402
+
+_TRUTH = sa.text("""
+    SELECT p.source AS src, m.ticker AS tk,
+           DATE_ADD(DATE_FORMAT(p.created_utc, '%Y-%m-%d %H:00:00'),
+                    INTERVAL FLOOR(MINUTE(p.created_utc)/15)*15 MINUTE) AS bs,
+           COUNT(*) AS n_high,
+           COUNT(DISTINCT p.author) AS n_authors,
+           COUNT(DISTINCT p.simhash) AS n_hashes,
+           SUM(p.score + p.num_comments) AS engagement
+      FROM radar_mentions m
+      JOIN radar_posts p ON p.id = m.post_id
+     WHERE m.confidence = 'high'
+     GROUP BY 1, 2, 3
+""")
+
+# distinct_text_ratio and engagement_weighted_count are MySQL FLOAT columns --
+# 4-byte single precision, not the 8-byte double Python computes n_hashes /
+# n_high in. A value like 2/3 is stored as the nearest float32 and reread as a
+# double that no longer equals the freshly recomputed truth, so a strict `==`
+# never short-circuits and every rerun "repairs" a row that has nothing left
+# to fix. Confirmed against the real dev database: 2/3 round-trips through
+# `distinct_text_ratio` as 0.6666666865348816, not 0.6666666666666666.
+# rel_tol=1e-6 comfortably clears float32's ~1e-7 relative precision without
+# masking a genuine difference (engagement_weighted_count is always a sum of
+# integers, so this never matters there in practice, but the columns share a
+# type and a rounding failure mode, so both get the tolerant compare).
+_FLOAT_FIELDS = ('distinct_text_ratio', 'engagement_weighted_count')
+
+
+def _unchanged(field, old, new):
+    if field in _FLOAT_FIELDS:
+        return math.isclose(old, new, rel_tol=1e-6, abs_tol=1e-9)
+    return old == new
+
+
+def repair(apply=False, ticker_prefix=None):
+    """Repair retained lower bounds; return integer report counters."""
+    with app.app_context():
+        rows = db.session.execute(_TRUTH).all()
+        repaired = examined = 0
+
+        for src, tk, bs, n_high, n_authors, n_hashes, engagement in rows:
+            if ticker_prefix and not tk.startswith(ticker_prefix):
+                continue
+            # sa.text() applies no DateTime type processor to a computed
+            # DATE_ADD(...) expression, so bs comes back a str, not a
+            # datetime, on this driver. MySQL 8 coerces the string implicitly
+            # for the filter_by() comparison below, but that coercion is not
+            # something this codebase can verify on MariaDB (production), so
+            # make the conversion explicit instead of leaning on it. Tolerate
+            # a driver that already hands back a real datetime.
+            if isinstance(bs, str):
+                bs = dt.datetime.strptime(bs, '%Y-%m-%d %H:%M:%S')
+            bucket = RadarBucketSource.query.filter_by(
+                ticker=tk, bucket_start=bs, source=src).one_or_none()
+            if bucket is None:
+                continue
+            examined += 1
+            # int() at the boundary: COUNT and SUM come back Decimal from both
+            # MySQL and MariaDB, and Decimal against a float column is a
+            # TypeError waiting for the first row that needs it.
+            n_high = int(n_high)
+            n_authors = int(n_authors)
+            n_hashes = int(n_hashes)
+            engagement = float(engagement or 0)
+            candidate = {
+                'high_confidence_count': max(
+                    int(bucket.high_confidence_count), n_high),
+                'mention_count': max(int(bucket.mention_count), n_high),
+                'distinct_authors': max(int(bucket.distinct_authors),
+                                        n_authors),
+                'distinct_text_ratio': min(
+                    float(bucket.distinct_text_ratio),
+                    (n_hashes / n_high) if n_high else 1.0),
+                'engagement_weighted_count': max(
+                    float(bucket.engagement_weighted_count), engagement),
+            }
+            if all(_unchanged(field, getattr(bucket, field), value)
+                   for field, value in candidate.items()):
+                continue
+
+            bucket.high_confidence_count = candidate['high_confidence_count']
+            # mention_count stays >= high: the promoted mediums it also counted
+            # are unrecoverable, so take whichever is larger rather than
+            # overwriting a real figure with an incomplete one.
+            bucket.mention_count = candidate['mention_count']
+            bucket.distinct_authors = candidate['distinct_authors']
+            bucket.distinct_text_ratio = candidate['distinct_text_ratio']
+            bucket.engagement_weighted_count = candidate[
+                'engagement_weighted_count']
+            # The score was computed from the understated count. Keeping it
+            # would make the repair cosmetic while the board continues to rank
+            # on the old number. Task 3c also keeps this old rollup generation
+            # out of current baselines; NULL is the honest state until a
+            # compatible scorer can recompute it.
+            bucket.expected = None
+            bucket.variance = None
+            bucket.mention_z = None
+            bucket.baseline_days = None
+            repaired += 1
+
+        # The stale scores Task 3 stopped PRODUCING, which it could not
+        # retroactively clear: roll_up only revisits a (ticker, bucket_start,
+        # source) row when that window is touched again, and a closed
+        # historical quarter-hour never is. 399 rows in production carry a
+        # mention_z written while they were `ok` and are ranked on it now that
+        # they are `truncated` -- leaderboard filters on mention_z IS NOT NULL,
+        # so the scorer's refusal to score them buys nothing until this runs.
+        #
+        # NULL, never 0: a zero z claims the bucket was exactly average, which
+        # is a different fact from not having been scored.
+        stale = (RadarBucketSource.query
+                 .filter(RadarBucketSource.status != 'ok',
+                         sa.or_(RadarBucketSource.expected.isnot(None),
+                                RadarBucketSource.variance.isnot(None),
+                                RadarBucketSource.mention_z.isnot(None),
+                                RadarBucketSource.baseline_days.isnot(None))))
+        if ticker_prefix:
+            stale = stale.filter(
+                RadarBucketSource.ticker.like(ticker_prefix + '%'))
+        stale_count = stale.count()
+        if apply and stale_count:
+            stale.update({'expected': None, 'variance': None,
+                          'mention_z': None, 'baseline_days': None},
+                         synchronize_session=False)
+
+        print('examined %d bucket rows, %d understated' % (examined, repaired))
+        print('%d rows carry a score they earned under a different status'
+              % stale_count)
+        if apply:
+            db.session.commit()
+            print('written')
+        else:
+            db.session.rollback()
+            print('dry run -- nothing written, pass --apply')
+        return {'examined': int(examined), 'repaired': int(repaired),
+                'stale_scores': int(stale_count)}
+
+
+def main():
+    parser = argparse.ArgumentParser()
+    parser.add_argument('--apply', action='store_true',
+                        help='write the repaired counts')
+    args = parser.parse_args()
+    repair(apply=args.apply)
+
+
+if __name__ == '__main__':
+    main()
diff --git a/personal_apps/scripts/discover_reddit_sources.py b/personal_apps/scripts/discover_reddit_sources.py
index 378e10d..deeaa41 100644
--- a/personal_apps/scripts/discover_reddit_sources.py
+++ b/personal_apps/scripts/discover_reddit_sources.py
@@ -168,25 +168,57 @@ def passes(entry):
     talks constantly about nothing tradeable costs requests and contributes
     noise. Crypto-dominated subs are rejected outright -- coin tickers collide
     with live equity symbols and would manufacture fake spikes.
     """
     return ('skipped' not in entry
             and entry['equity_per_hour'] >= 1.0
             and entry['crypto_share'] <= 0.4
             and entry['distinct_authors'] >= 5)
 
 
-def main():
+def _daemon_is_running():
+    """True when radar_ingest holds the Reddit budget.
+
+    Reddit's anonymous feed budget is per IP and is one request per window --
+    `x-ratelimit-remaining` reads 0.0 after a single call, measured on the VPS
+    2026-08-25. This script asks every 45 seconds and the daemon every 120, so
+    run together they refuse each other, and the daemon's cycle then reports
+    `missing` and writes no buckets at all. Nothing else coordinates them.
+
+    systemctl only exists where the daemon is deployed. Anywhere else the
+    answer is no, which is right: a dev machine is not sharing the budget.
+    """
+    import shutil
+    import subprocess
+
+    if shutil.which('systemctl') is None:
+        return False
+    result = subprocess.run(['systemctl', 'is-active', 'radar_ingest'],
+                            capture_output=True, text=True)
+    return result.stdout.strip() == 'active'
+
+
+def main(argv=None):
     parser = argparse.ArgumentParser()
     parser.add_argument('--sleep', type=float, default=SLEEP,
                         help='seconds between requests; lower risks a 429')
-    args = parser.parse_args()
+    parser.add_argument('--anyway', action='store_true',
+                        help='run even while radar_ingest holds the budget')
+    args = parser.parse_args(argv)
+
+    if _daemon_is_running() and not args.anyway:
+        print('radar_ingest is running and shares this IP\'s Reddit budget --\n'
+              'one request per window, so the two will refuse each other and\n'
+              'the daemon will write no buckets while this runs.\n\n'
+              'Stop it first:  systemctl stop radar_ingest\n'
+              'Or override:    --anyway', file=sys.stderr)
+        return 1
 
     with app.app_context():
         lookup = universe.load_lookup()
     print(f'universe: {len(lookup)} symbols\n')
 
     profiles = []
     for n, sub in enumerate(CANDIDATES, 1):
         if sub.lower() in SINGLE_TICKER_SUBS:
             continue
         if n > 1:
@@ -214,11 +246,11 @@ def main():
               f'{p["suggested_poll"]:>6}s  {[t for t, _ in p["top"][:5]]}')
 
     import json
     with open('reddit_candidates.json', 'w', encoding='utf-8') as handle:
         json.dump({'kept': [p['sub'] for p in kept], 'profiles': profiles},
                   handle, indent=2)
     print('\n-> reddit_candidates.json')
 
 
 if __name__ == '__main__':
-    main()
+    sys.exit(main() or 0)
diff --git a/personal_apps/static/radar/src/board/BoardPage.test.tsx b/personal_apps/static/radar/src/board/BoardPage.test.tsx
index f4ceb08..2eae8e8 100644
--- a/personal_apps/static/radar/src/board/BoardPage.test.tsx
+++ b/personal_apps/static/radar/src/board/BoardPage.test.tsx
@@ -18,22 +18,22 @@ function row(over: Partial<Row> = {}): Row {
     tone: { bullish: 4, neutral: 10, bearish: 2 },
     clauses: [{ kind: 'ratio', text: '3x its normal' },
               { kind: 'venues', text: '2 venues' }],
     ...over,
   }
 }
 
 function payload(over: Partial<BoardPayload> = {}): BoardPayload {
   return {
     generated_at: '2026-08-22T19:00:00Z',
-    sources: ['stocktwits', 'bluesky', 'fourchan'],
-    all_sources: ['stocktwits', 'bluesky', 'fourchan'],
+    sources: ['bluesky', 'fourchan', 'reddit'],
+    all_sources: ['bluesky', 'fourchan', 'reddit'],
     segments: [], session: 'regular', window_hours: 4,
     min_venues: 1, venue_counts: { any: 4, multi: 2 },
     segment_counts: { all: 4, large: 4 },
     triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
     rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' }),
            row({ ticker: 'CCC' }), row({ ticker: 'DDD' })],
     excluded: {},
     ...over,
   }
 }
@@ -47,21 +47,21 @@ function detail(ticker = 'AAA'): Detail {
     },
     read: [{ kind: 'plain', text: `${ticker} is being discussed.` }],
     chart: {
       from: '2025-08-23T00:00:00Z', span: '1Y', step_minutes: 1440,
       closes: Array.from({ length: 365 }, (_, i) => 100 + i),
       chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
       watched_from: '2026-08-18',
     },
     breakdown: {
       venues: [{ source: 'bluesky', mentions: 20, voices: 9 }],
-      bullish: 4, neutral: 10, bearish: 2,
+      bullish: 4, neutral: 10, bearish: 2, disagreements: 1,
       top_author_share: 0.2, top_two_share: 0.3,
       peak_hour: '2026-08-22T14:00:00Z', peak_count: 9,
       first_seen: '2026-08-18', mentions: 20, voices: 9,
     },
     posts: [], post_total: 0,
   }
 }
 
 /** Route by URL. The page makes two different requests now, and a stub that
  *  answered both with a board payload would hand the panel the wrong shape. */
@@ -152,24 +152,24 @@ describe('selecting a ticker', () => {
 })
 
 describe('the controls', () => {
   it('refetches and rewrites the address bar when a source is dropped', async () => {
     render(<BoardPage initial={payload()} />)
 
     await userEvent.click(screen.getByRole('button', { name: /4chan/ }))
 
     await waitFor(() => expect(boardCalls()).toHaveLength(1))
     expect(boardCalls()[0]).toBe(
-      '/radar/api/board?sources=stocktwits%2Cbluesky&window=4&segment=')
+      '/radar/api/board?sources=bluesky%2Creddit&window=4&segment=')
     await waitFor(() =>
       expect(window.location.search)
-        .toContain('sources=stocktwits%2Cbluesky&window=4&segment='))
+        .toContain('sources=bluesky%2Creddit&window=4&segment='))
   })
 
   it('keeps All in the address bar rather than omitting it', async () => {
     /* The server's default segment is Small, so a URL with no segment param
        reloads as Small. Sharing the All view has to survive a reload, which
        means the empty value is the state, not the absence of one. */
     render(<BoardPage initial={payload({ segments: ['small'] })} />)
 
     await userEvent.click(screen.getByRole('button', { name: /^All/ }))
 
diff --git a/personal_apps/static/radar/src/detail/Breakdown.tsx b/personal_apps/static/radar/src/detail/Breakdown.tsx
index 6033255..f161c46 100644
--- a/personal_apps/static/radar/src/detail/Breakdown.tsx
+++ b/personal_apps/static/radar/src/detail/Breakdown.tsx
@@ -66,20 +66,30 @@ export function Breakdown({ breakdown, windowHours }: {
           {b.mentions > 0 && (
             <p className="wording">
               <span><b>{b.bullish}</b> bullish</span>
               <span><b>{b.bearish}</b> bearish</span>
               {/* Not padding. Most mentions carry no lexicon word at all, and
                   hiding them turns a handful of scored posts into a
                   confident-looking sentiment reading. */}
               <span className="q">
                 <b>{b.neutral}</b> carried no wording at all
               </span>
+              {/* Both scores are kept precisely so this comparison is
+                  possible -- a post the word list and the model read
+                  opposite ways is a post that was being sarcastic. Words,
+                  not colour: green and red mean price direction here and
+                  nothing else. */}
+              {b.disagreements > 0 && (
+                <span className="q">
+                  <b>{b.disagreements}</b> read differently by the model
+                </span>
+              )}
             </p>
           )}
 
           {/* The facts that are only facts, kept out of the column beside so
               that column stays five lines about one thing. */}
           <p className="plain">
             {b.peak_hour
               ? <>Peak hour <b>{b.peak_hour.slice(11, 16)}</b> at{' '}
                   <b>{b.peak_count}</b> mentions · </>
               : null}
diff --git a/personal_apps/static/radar/src/format.test.ts b/personal_apps/static/radar/src/format.test.ts
index f34ea0a..c946666 100644
--- a/personal_apps/static/radar/src/format.test.ts
+++ b/personal_apps/static/radar/src/format.test.ts
@@ -39,20 +39,37 @@ describe('signed numbers', () => {
 
 describe('labels', () => {
   it('renders a source the label table does not know', () => {
     // Adding a source must be a config entry plus an ingest module, never a
     // UI change (PRODUCT.md). An unknown key falling through as itself is
     // what keeps that true.
     expect(sourceLabel('bluesky')).toBe('Bluesky')
     expect(sourceLabel('discord')).toBe('discord')
     expect(segmentLabel('nonsense')).toBe('nonsense')
   })
+
+  it('names the venue, not the subreddit', () => {
+    // Since 2026-08-26 a stored Reddit source name carries its subreddit, so
+    // that one sub's feed rolling over marks its own buckets truncated
+    // rather than every other sub's. That is a decision about how status and
+    // scoring are partitioned, NOT a decision to put subreddits on the
+    // surface -- and without the rooting the raw key leaked through the
+    // fallback and post badges read `reddit:wallstreetbets` next to
+    // `Bluesky`.
+    expect(sourceLabel('reddit')).toBe('Reddit')
+    expect(sourceLabel('reddit:wallstreetbets')).toBe('Reddit')
+    expect(sourceLabel('reddit:pennystocks')).toBe('Reddit')
+  })
+
+  it('still falls through for an unknown root with a suffix', () => {
+    expect(sourceLabel('discord:general')).toBe('discord:general')
+  })
 })
 
 describe('the stamp', () => {
   it('is UTC, matching every other time on the page', () => {
     expect(stampTime('2026-08-22T19:04:11Z')).toBe('19:04 UTC')
   })
 
   it('does not crash on a malformed timestamp', () => {
     expect(stampTime('not a date')).toBe('—')
   })
diff --git a/personal_apps/static/radar/src/format.ts b/personal_apps/static/radar/src/format.ts
index cca6bb0..ea1bb8e 100644
--- a/personal_apps/static/radar/src/format.ts
+++ b/personal_apps/static/radar/src/format.ts
@@ -46,30 +46,41 @@ const SEGMENT_LABELS: Record<string, string> = {
  *  way back out. The three it covers stay listed -- Small is a shortcut to the
  *  common reading, not a replacement for reading them apart. */
 export const SEGMENT_ORDER = ['small', 'all', 'large', 'mid', 'micro',
                               'recent_ipo', 'unknown', 'fund']
 
 export function segmentLabel(key: string): string {
   return SEGMENT_LABELS[key] ?? key
 }
 
 const SOURCE_LABELS: Record<string, string> = {
-  stocktwits: 'StockTwits',
   bluesky: 'Bluesky',
   fourchan: '4chan /biz/',
   reddit: 'Reddit',
 }
 
 /** A source name the config knows but this file does not still renders --
- *  adding a source must not require touching the UI (PRODUCT.md). */
+ *  adding a source must not require touching the UI (PRODUCT.md).
+ *
+ *  Rooted at the colon first. Since 2026-08-26 a stored Reddit source name
+ *  carries its subreddit (`reddit:wallstreetbets`) so that one sub's feed
+ *  rolling over marks its own buckets truncated rather than every other
+ *  sub's. That is a decision about how STATUS and SCORING are partitioned,
+ *  and it is not a decision to put subreddits on the surface -- so the label
+ *  is the venue, `Reddit`, exactly as it was before the split. Showing
+ *  `r/wallstreetbets` here would be its own product call, and one worth
+ *  making deliberately rather than inheriting from a storage change. */
 export function sourceLabel(key: string): string {
-  return SOURCE_LABELS[key] ?? key
+  const root = key.split(':')[0] ?? key
+  // Falls through as the WHOLE key, not the root: an unknown source with a
+  // suffix must render as itself rather than silently losing half its name.
+  return SOURCE_LABELS[root] ?? key
 }
 
 /** Nasdaq's one-letter listing codes, as stored in radar_ticker_universe.
  *
  *  The panel printed the raw letter: `Q · large cap · $2.9T`. The tier is
  *  worth keeping rather than flattening all three Nasdaq codes to "Nasdaq" --
  *  Capital Market is the lowest listing standard and it is where most of what
  *  this board is for actually lists. Verified against the stored universe:
  *  F and GE are N, SPY and DIA are P, NVDA is Q, SOUN is G, HOWL is S. */
 const EXCHANGE_LABELS: Record<string, string> = {
@@ -95,20 +106,24 @@ export const MARK_WHY: Record<string, string> = {
     'row is not scored.',
   provisional:
     'Under 14 days of baseline history. The score is computed, but it is ' +
     'thinly supported and will move as history accumulates.',
   'single-source':
     'Only one of the selected sources contributed. The same reading from two ' +
     'independent sources is much stronger evidence.',
   partial:
     'A source was truncated during this window, so the count is real but ' +
     'incomplete. The true figure is higher.',
+  'warming-up':
+    'Under a day of baseline history, because the extraction rules changed ' +
+    'recently and older data no longer counts toward it. Not a new ticker -- ' +
+    'every ticker on the board is warming up together.',
 }
 
 /** "22:14 UTC" -- the board's own clock, always UTC.
  *
  *  Not localised on purpose. Market sessions, the ingest cadence and every
  *  stored timestamp are UTC; rendering the stamp in Berlin time would be the
  *  one number on the page in a different frame from all the others. */
 export function stampTime(iso: string): string {
   const at = new Date(iso)
   if (Number.isNaN(at.getTime())) return UNKNOWN
diff --git a/personal_apps/static/radar/src/list/ListPane.tsx b/personal_apps/static/radar/src/list/ListPane.tsx
index aab636f..82e4778 100644
--- a/personal_apps/static/radar/src/list/ListPane.tsx
+++ b/personal_apps/static/radar/src/list/ListPane.tsx
@@ -13,20 +13,24 @@ import type { BoardPayload, Mark, Row, Selection } from '../types'
  *  claim "baselines over 30 days" while every row it listed was flagged
  *  provisional, which is the opposite of true.
  */
 // Exhaustive over Mark on purpose: a new mark will not compile until
 // someone decides what the board says when every row carries it.
 const UNIVERSAL: Record<Mark, string> = {
   provisional: 'every baseline here is under 14 days old',
   'single-source': 'every row here came from a single source',
   'no-print': 'no tape has printed in this window',
   partial: 'every source here was truncated, so the counts are low',
+  // Distinct from `provisional`: this fires when the extraction rules
+  // changed recently, not when a ticker itself is new -- see marks.test.tsx.
+  'warming-up': 'the extraction rules changed recently, so every baseline '
+    + 'here is starting over',
 }
 
 /** Marks shared by the whole board, in the order they are written above.
  *
  *  Two rows minimum: on a one-row board "every row" is trivially true, and
  *  moving the only row's mark into the header would hide it from the place a
  *  reader is looking. */
 export function universalMarks(rows: Row[]): Mark[] {
   if (rows.length < 2) return []
   return (Object.keys(UNIVERSAL) as Mark[]).filter(
@@ -39,24 +43,30 @@ export function universalMarks(rows: Row[]): Mark[] {
  *  ranking falls through to chatter -- which is the useful answer at 23:00 on
  *  a Sunday, and only honest if the page says which of the two rankings the
  *  reader is looking at.
  */
 function Finding({ payload, shared }: {
   payload: BoardPayload
   shared: Mark[]
 }) {
   const count = payload.rows.length
   const tickers = count === 1 ? '1 ticker' : `${count} tickers`
-  const baselines = shared.includes('provisional')
-    ? UNIVERSAL.provisional
-    : 'baselines over 30 days'
-  const rest = shared.filter((mark) => mark !== 'provisional')
+  // The two never both apply to one row -- leaderboard.py picks exactly one
+  // per row, by age -- so at most one is ever universal at a time. Either
+  // way the header must not say "baselines over 30 days" while every row
+  // disagrees; that was the bug this whole section exists to fix.
+  const thinBaseline = shared.includes('provisional') ? 'provisional'
+    : shared.includes('warming-up') ? 'warming-up'
+    : null
+  const baselines = thinBaseline ? UNIVERSAL[thinBaseline] : 'baselines over 30 days'
+  const rest = shared.filter(
+    (mark) => mark !== 'provisional' && mark !== 'warming-up')
 
   return (
     <p className="finding">
       {payload.session === 'closed' ? (
         <>
           No price is moving, so these are ranked by <b>chatter against each
           ticker&rsquo;s own normal</b> — what to look at when it opens.
           {' '}<b>{tickers}</b> cleared the bar in the last
           {' '}<b>{payload.window_hours}h</b>,{' '}
           <span className={shared.length ? 'shared' : undefined}>{baselines}</span>.
diff --git a/personal_apps/static/radar/src/list/Spend.test.tsx b/personal_apps/static/radar/src/list/Spend.test.tsx
index 935539c..3f00d31 100644
--- a/personal_apps/static/radar/src/list/Spend.test.tsx
+++ b/personal_apps/static/radar/src/list/Spend.test.tsx
@@ -1,43 +1,57 @@
 import { render, screen } from '@testing-library/react'
 import { describe, expect, it } from 'vitest'
 import { Spend } from './Spend'
 import type { BoardPayload } from '../types'
 
-const payload = (spend?: { today_usd: number; month_usd: number }) =>
+const payload = (spend?: {
+  today_usd: number
+  month_usd: number
+  unpriced_tokens: number
+}) =>
   ({ spend, excluded: {}, rows: [] } as unknown as BoardPayload)
 
 describe('the spend footnote', () => {
   it('reports today and the month', () => {
-    render(<Spend payload={payload({ today_usd: 0.196, month_usd: 4.12 })} />)
+    render(<Spend payload={payload({ today_usd: 0.196, month_usd: 4.12, unpriced_tokens: 0 })} />)
 
     expect(screen.getByText(/\$0\.196/)).toBeTruthy()
     expect(screen.getByText(/\$4\.12/)).toBeTruthy()
   })
 
   it('says nothing before the first pass has booked anything', () => {
     /* A meter reading $0.00 is a claim that nothing was spent. Having nothing
        to report yet is a different fact, and the difference matters on the
        first day the key is installed -- when "$0.00" would look like proof
        the pass was running when it was not. */
     const { container } = render(<Spend payload={payload(undefined)} />)
 
     expect(container.textContent).toBe('')
   })
 
   it('is silent on a zero rather than drawing an empty band', () => {
     const { container } = render(
-      <Spend payload={payload({ today_usd: 0, month_usd: 0 })} />)
+      <Spend payload={payload({ today_usd: 0, month_usd: 0, unpriced_tokens: 0 })} />)
 
     expect(container.textContent).toBe('')
   })
 
   it('drops to cents once there are dollars to round', () => {
-    /* Three places below a dollar because a day costs about twenty cents and
-       "$0.20" reads as a rounding of something unknown. Above a dollar the
+    /* Three places below a dollar: at two decimal places a sub-dollar spend
+       ("$0.20") reads as a rounding of something unknown. Above a dollar the
        third place is noise. */
-    render(<Spend payload={payload({ today_usd: 1.5, month_usd: 12.345 })} />)
+    render(<Spend payload={payload({ today_usd: 1.5, month_usd: 12.345, unpriced_tokens: 0 })} />)
 
     expect(screen.getByText(/\$1\.50/)).toBeTruthy()
     expect(screen.getByText(/\$12\.35/)).toBeTruthy()
   })
+
+  it('surfaces tokens that have no price without inventing one', () => {
+    render(<Spend payload={payload({
+      today_usd: 0,
+      month_usd: 0,
+      unpriced_tokens: 501_000,
+    })} />)
+
+    expect(screen.getByText(/tokens at an unknown rate/)).toBeTruthy()
+  })
 })
diff --git a/personal_apps/static/radar/src/list/Spend.tsx b/personal_apps/static/radar/src/list/Spend.tsx
index ec2f46f..0e2f183 100644
--- a/personal_apps/static/radar/src/list/Spend.tsx
+++ b/personal_apps/static/radar/src/list/Spend.tsx
@@ -1,17 +1,17 @@
 import type { BoardPayload } from '../types'
 
 /** Money in USD, at the precision the number deserves.
  *
  *  Cents once there are dollars to round; three places below a dollar,
- *  because a day of this costs about twenty cents and "$0.20" reads as a
- *  rounding of something unknown while "$0.196" reads as a measurement.
+ *  because a sub-dollar spend reads as a rounding of something unknown at two
+ *  decimal places ("$0.20") and as a measurement at three ("$0.196").
  */
 function usd(amount: number): string {
   if (amount >= 1) return `$${amount.toFixed(2)}`
   return `$${amount.toFixed(3)}`
 }
 
 /** What the model re-read of tone has cost.
  *
  *  Counted from the token usage every API response carries, not asked for:
  *  there is no balance endpoint anywhere in the Claude API. The Cost API
@@ -21,19 +21,22 @@ function usd(amount: number): string {
  *  So this is spend, and it is read against whatever was last loaded onto the
  *  account. It deliberately does not claim to be a balance, because a number
  *  labelled "remaining" that was never told the top-ups would be worse than
  *  no number at all.
  */
 export function Spend({ payload }: { payload: BoardPayload }) {
   const spend = payload.spend
   // Absent until the first pass books something. Rendering "$0.00" before any
   // call has happened would look like a working meter reading zero, which is
   // a different claim from having nothing to report yet.
-  if (!spend || (!spend.today_usd && !spend.month_usd)) return null
+  if (!spend || (!spend.today_usd && !spend.month_usd && !spend.unpriced_tokens)) return null
 
   return (
     <p className="below">
       <b>{usd(spend.today_usd)}</b> spent reading tone today,
       {' '}<b>{usd(spend.month_usd)}</b> this month.
+      {spend.unpriced_tokens > 0 && (
+        <> plus {spend.unpriced_tokens.toLocaleString()} tokens at an unknown rate.</>
+      )}
     </p>
   )
 }
diff --git a/personal_apps/static/radar/src/list/marks.test.tsx b/personal_apps/static/radar/src/list/marks.test.tsx
index abc30e4..6e9f9ef 100644
--- a/personal_apps/static/radar/src/list/marks.test.tsx
+++ b/personal_apps/static/radar/src/list/marks.test.tsx
@@ -49,10 +49,39 @@ describe('a mark carried by every row', () => {
     /* The teeth check for the one above: if the row rendered no marks at all
        that test would pass on an empty string. */
     const { container } = render(
       <TickerRow row={row('A', ['provisional'])} selected={false}
                  onSelect={() => {}} />)
 
     expect(container.querySelector('.meta')!.textContent)
       .toContain('provisional')
   })
 })
+
+describe('warming-up, a second thin-baseline mark', () => {
+  /* leaderboard.py splits one badge into two: a NEW ticker is `provisional`,
+     but a board-wide config-version change makes EVERY ticker `warming-up`
+     instead -- see leaderboard.py's own comment where the mark is written.
+     A mark the client does not know about renders as a raw key or nothing at
+     all; these pin that it is lifted, rendered and worded the same way
+     `provisional` already is. */
+  it('is lifted off the rows when the whole board has it, like provisional', () => {
+    const rows = [row('A', ['warming-up']), row('B', ['warming-up'])]
+
+    expect(universalMarks(rows)).toEqual(['warming-up'])
+  })
+
+  it('stays on the row when only some rows carry it', () => {
+    const rows = [row('A', ['warming-up']), row('B', [])]
+
+    expect(universalMarks(rows)).toEqual([])
+  })
+
+  it('renders on the row like any other mark', () => {
+    const { container } = render(
+      <TickerRow row={row('A', ['warming-up'])} selected={false}
+                 onSelect={() => {}} />)
+
+    expect(container.querySelector('.meta')!.textContent)
+      .toContain('warming-up')
+  })
+})
diff --git a/personal_apps/static/radar/src/types.ts b/personal_apps/static/radar/src/types.ts
index 7ba675a..95d525c 100644
--- a/personal_apps/static/radar/src/types.ts
+++ b/personal_apps/static/radar/src/types.ts
@@ -14,21 +14,22 @@ export interface Point {
 }
 
 export interface Tone {
   bullish: number
   neutral: number
   bearish: number
 }
 
 /** Why a number on this row cannot be taken at face value. Rendered, never
  *  hidden behind a hover -- see PRODUCT.md. */
-export type Mark = 'no-print' | 'provisional' | 'single-source' | 'partial'
+export type Mark =
+  'no-print' | 'provisional' | 'single-source' | 'partial' | 'warming-up'
 
 /** `fund` is a pooled vehicle -- an ETF, an ETN, an index product. It is
  *  deliberately outside the `small` group and therefore off the default
  *  board: a fund has no market cap to look up, so before it had a segment
  *  of its own it fell through to `unknown`, and SPY sat in the tab meant
  *  for penny stocks nobody has heard of. */
 export type Segment = 'large' | 'mid' | 'micro' | 'unknown' | 'recent_ipo'
                     | 'fund'
 
 /** What the reader can filter BY, which is a wider vocabulary than what a row
@@ -87,20 +88,23 @@ export interface Venue {
   source: string
   mentions: number
   voices: number
 }
 
 export interface Breakdown {
   venues: Venue[]
   bullish: number
   neutral: number
   bearish: number
+  /** How often the word list and the model read the same post the opposite
+   *  way -- the sarcasm the lexicon alone cannot see. */
+  disagreements: number
   /** The pump tell: one account posting forty times reads as forty mentions
    *  everywhere else on the surface. */
   top_author_share: number | null
   top_two_share: number | null
   peak_hour: string | null
   peak_count: number
   first_seen: string | null
   mentions: number
   voices: number
 }
@@ -182,21 +186,21 @@ export interface BoardPayload {
   triplet_hours: number[]
   series_hours: number
   lead_count: number
   rows: Row[]
   /** What the eligibility floor and the breadth filter left out, by reason.
    *  Without it a quiet board and a stopped ingest look identical. */
   excluded: Record<string, number>
   /** What the model tone pass has cost. SPEND, never a balance -- the Claude
    *  API has no balance endpoint, so nothing here knows what is left. Absent
    *  until the first pass books something. */
-  spend?: { today_usd: number; month_usd: number }
+  spend?: { today_usd: number; month_usd: number; unpriced_tokens: number }
 }
 
 export interface Selection {
   sources: string[]
   /** Server-side filter, unlike the chart span -- changing it refetches. */
   minVenues: number
   /** Several, and a union -- picking a second chip asks to see more. Empty
    *  is no filter, which is what the All chip sets. */
   segments: SegmentFilter[]
   window: number
diff --git a/personal_apps/tests/test_radar_api.py b/personal_apps/tests/test_radar_api.py
index 19b1bda..875a75b 100644
--- a/personal_apps/tests/test_radar_api.py
+++ b/personal_apps/tests/test_radar_api.py
@@ -13,33 +13,150 @@ def test_the_board_requires_login(anon_client):
 
 def test_the_board_returns_json(client):
     response = client.get('/radar/api/board')
     assert response.status_code == 200
     payload = json.loads(response.data)
     assert 'rows' in payload
     assert 'sources' in payload
     assert isinstance(payload['rows'], list)
 
 
+def test_the_board_payload_surfaces_unpriced_tokens(client, monkeypatch):
+    """The spend summary crosses the API boundary without becoming dollars."""
+    from features.radar.routes import api
+
+    monkeypatch.setattr(api.spend, 'summary', lambda: {
+        'today_usd': 0.0,
+        'month_usd': 0.0,
+        'unpriced_tokens': 501_000,
+    })
+
+    payload = json.loads(client.get('/radar/api/board').data)
+
+    assert payload['spend']['unpriced_tokens'] == 501_000
+
+
 def test_the_selected_sources_are_echoed_back(client):
     """The surface needs to know which selection produced these rows, or a
     stale request and a fresh one look identical."""
     payload = json.loads(client.get('/radar/api/board?sources=bluesky').data)
     assert payload['sources'] == ['bluesky']
 
 
 def test_an_unknown_source_is_rejected(client):
     """Silently ignoring it would return the default board under a selection
     the viewer never made."""
     assert client.get('/radar/api/board?sources=nonsense').status_code == 400
 
 
+def test_a_concrete_reddit_source_is_accepted_but_an_unknown_root_is_not():
+    from features.radar.routes.api import BadQuery, parse_query
+    import pytest
+
+    assert parse_query({'sources': 'reddit:wallstreetbets'}).sources == [
+        'reddit:wallstreetbets']
+    with pytest.raises(BadQuery):
+        parse_query({'sources': 'notreddit:wallstreetbets'})
+
+
+def test_the_board_gets_the_selection_and_echoes_the_root(client, monkeypatch):
+    """The API hands the SELECTION down, not an expansion, and echoes a root.
+
+    Expanding here would take the choice away from the queries underneath,
+    which expand differently: a scored read may not see the pre-split root
+    `reddit` rows and a raw-count read must (config.expand_sources vs
+    expand_sources_for_history). Once the list is expanded the root is gone
+    and neither can tell it was ever asked for.
+
+    What the payload carries back is still the root, because that is what
+    lights the chip. The expansion itself is proved where it happens -- see
+    test_radar_board / test_radar_detail's historical-root tests.
+    """
+    from features.radar.routes import api
+
+    seen = {}
+    real_build = api.board_mod.build
+
+    def capture(sources, *args, **kwargs):
+        seen['sources'] = list(sources)
+        return real_build(sources, *args, **kwargs)
+
+    monkeypatch.setattr(api.board_mod, 'build', capture)
+    response = client.get('/radar/api/board?sources=reddit')
+    payload = json.loads(response.data)
+
+    assert response.status_code == 200
+    assert seen['sources'] == ['reddit']
+    assert payload['sources'] == ['reddit']
+
+
+def test_the_detail_panel_gets_the_selection(client, monkeypatch):
+    from features.radar.routes import api
+
+    seen = {}
+
+    def capture(ticker, sources, now, **kwargs):
+        seen['sources'] = list(sources)
+        return object()
+
+    monkeypatch.setattr(api.detail_panel, 'build', capture)
+    monkeypatch.setattr(api, 'serialize_detail', lambda built: {'ok': True})
+
+    response = client.get('/radar/api/ticker/ZZG?sources=reddit')
+
+    assert response.status_code == 200
+    assert seen['sources'] == ['reddit']
+
+
+def test_a_concrete_subreddit_link_lights_the_reddit_chip(client, monkeypatch):
+    """`?sources=reddit:wallstreetbets` filters to that sub AND lights Reddit.
+
+    The payload's `sources` is compared against `all_sources` -- three roots
+    -- to decide which chips are on. A concrete name matched none of them, so
+    the control rendered every chip off: a state it otherwise forbids, and
+    one whose first click silently discarded the concrete selection.
+    """
+    from features.radar.routes import api
+
+    seen = {}
+    real_build = api.board_mod.build
+
+    def capture(sources, *args, **kwargs):
+        seen['sources'] = list(sources)
+        return real_build(sources, *args, **kwargs)
+
+    monkeypatch.setattr(api.board_mod, 'build', capture)
+    payload = json.loads(
+        client.get('/radar/api/board?sources=reddit:wallstreetbets').data)
+
+    assert seen['sources'] == ['reddit:wallstreetbets']
+    assert payload['sources'] == ['reddit']
+    assert payload['sources'][0] in payload['all_sources']
+
+
+def test_a_selection_longer_than_every_real_name_is_rejected(client):
+    """Rooting the membership check unbounded the list's length.
+
+    `reddit:<anything>` passes validation, and each accepted entry lands in
+    six or more IN (...) clauses against a ~300k-row partitioned table. The
+    cap is the largest selection that can name something real.
+    """
+    from features.radar.routes.api import MAX_SOURCES
+
+    ok = ','.join(['reddit:x%d' % i for i in range(MAX_SOURCES)])
+    too_many = ok + ',reddit:overflow'
+
+    assert client.get('/radar/api/board?sources=' + ok).status_code == 200
+    assert client.get(
+        '/radar/api/board?sources=' + too_many).status_code == 400
+
+
 def test_an_unknown_segment_is_rejected(client):
     assert client.get('/radar/api/board?segment=nonsense').status_code == 400
 
 
 def test_the_window_is_bounded(client):
     """An unbounded window would scan the whole partitioned history on a page
     load."""
     assert client.get('/radar/api/board?window=99999').status_code == 400
 
 
@@ -300,10 +417,53 @@ def test_one_unknown_name_rejects_the_whole_selection():
     from features.radar.routes.api import BadQuery
     import pytest as _pytest
 
     with _pytest.raises(BadQuery):
         _parse(segment='small,nonsense')
 
 
 def test_whitespace_and_empty_entries_are_forgiven():
     """A person editing the address bar is not a bug."""
     assert _parse(segment=' small , large ,').segments == ['small', 'large']
+
+
+def _stub_detail(breakdown):
+    """The minimal detail_panel.build() return serialize_detail reads.
+
+    Built by hand from detail_panel.py's and detail.py's own dataclasses
+    rather than through detail_panel.build itself, so tests that use this do
+    not depend on which tickers the local database happens to hold.
+    """
+    import datetime as dt
+
+    from features.radar import detail, detail_panel
+
+    return detail_panel.Detail(
+        ticker='ZZSTUB', name='Stub Corp', exchange='Q', segment='micro',
+        market_cap=None, ipo_date=None, price=None, price_move=None,
+        price_status='ok', session='closed', span='1D',
+        chart=detail.Chart(start=dt.date(2026, 3, 12), closes=[], chatter=[],
+                           watched_from=None, step_minutes=15),
+        breakdown=breakdown, posts=[], post_total=0,
+        mentions=breakdown.mentions, expected=0.0, baseline_days=None)
+
+
+def test_the_detail_payload_carries_the_sarcasm_signal():
+    """Two sentiment scores are kept so their DISAGREEMENT can be read. Until
+    now nothing compared them, which made the second one decoration.
+
+    Asserted on the serializer rather than through a route, so it does not
+    depend on which tickers the local database happens to hold.
+    """
+    import dataclasses
+
+    from features.radar import detail_panel
+    from features.radar.routes import api
+
+    breakdown = detail_panel.Breakdown(
+        venues=[], bullish=3, neutral=1, bearish=2, disagreements=2,
+        top_author_share=None, top_two_share=None, peak_hour=None,
+        peak_count=0, first_seen=None, mentions=6, voices=4)
+    built = _stub_detail(breakdown)
+
+    payload = api.serialize_detail(built)
+    assert payload['breakdown']['disagreements'] == 2
diff --git a/personal_apps/tests/test_radar_backfill.py b/personal_apps/tests/test_radar_backfill.py
new file mode 100644
index 0000000..ce75257
--- /dev/null
+++ b/personal_apps/tests/test_radar_backfill.py
@@ -0,0 +1,246 @@
+# personal_apps/tests/test_radar_backfill.py
+"""One-shot repair for the buckets the pre-2026-08-26 rollup truncated.
+
+roll_up rebuilt each bucket from one cycle's cursor slice and overwrote, so a
+quarter-hour touched by several cycles kept only the last one. This suite
+pins scripts.backfill_radar_buckets.repair(): it must recover the retained
+`high` lower bound from radar_posts x radar_mentions, never regress a column,
+never restamp a partially-repaired row onto the current rollup generation,
+and clear a stale score off any row whose status is no longer `ok` -- keyed
+on ANY of the four scoring columns, not just mention_z.
+
+All fixtures live under the ZZBF ticker namespace and channel
+'zzbf-backfill-test', cleaned up by exact identity (never a broad LIKE 'ZZ%'
+sweep, which would reach other suites' and the user's real data) both before
+and after every test. Every call into repair() passes ticker_prefix='ZZBF' so
+a bug here cannot touch the live board's rows.
+"""
+import datetime as dt
+
+import pytest
+
+from app import app as flask_app
+from extensions import db
+from models import RadarBucketSource, RadarMention, RadarPost
+from scripts import backfill_radar_buckets as backfill
+
+BS = dt.datetime(2026, 4, 15, 14, 0, 0)
+CHANNEL = 'zzbf-backfill-test'
+TICKERS = ('ZZBF1', 'ZZBF2', 'ZZBF3', 'ZZBF4', 'ZZBF5')
+
+
+def _wipe():
+    RadarBucketSource.query.filter(
+        RadarBucketSource.ticker.in_(TICKERS)).delete(synchronize_session=False)
+    # ondelete='CASCADE' on radar_mentions.post_id (see models.py / migration
+    # 7883c6e08708) takes radar_mentions with it -- no separate delete needed.
+    RadarPost.query.filter(RadarPost.channel == CHANNEL).delete(
+        synchronize_session=False)
+    db.session.commit()
+
+
+@pytest.fixture()
+def clean():
+    with flask_app.app_context():
+        _wipe()
+        yield
+        _wipe()
+
+
+def _source_row(ticker, source='bluesky', bucket_start=BS, **overrides):
+    fields = dict(
+        ticker=ticker, bucket_start=bucket_start, source=source,
+        mention_count=1, high_confidence_count=1, low_count=0,
+        distinct_authors=1, distinct_text_ratio=1.0,
+        engagement_weighted_count=1.0, sentiment_mean=None,
+        sentiment_stdev=None, status='ok', source_config_version=None,
+        expected=None, variance=None, mention_z=None, baseline_days=None)
+    fields.update(overrides)
+    row = RadarBucketSource(**fields)
+    db.session.add(row)
+    return row
+
+
+_seq = [0]
+
+
+def _post(ticker, author, simhash, score=0, num_comments=0, source='bluesky',
+          minute=5, confidence='high'):
+    """A stored high-confidence post + its mention -- exactly the population
+    _TRUTH recovers. created_utc lands inside BS's quarter-hour by default."""
+    _seq[0] += 1
+    when = BS + dt.timedelta(minutes=minute)
+    external_id = 'zzbf-%d' % _seq[0]
+    post = RadarPost(source=source, external_id=external_id, channel=CHANNEL,
+                     author=author, created_utc=when, title=None, body='x',
+                     score=score, num_comments=num_comments,
+                     url='https://example.invalid/', simhash=simhash,
+                     first_seen=when, last_seen=when)
+    db.session.add(post)
+    db.session.flush()
+    db.session.add(RadarMention(post_id=post.id, ticker=ticker,
+                                confidence=confidence, lexicon_sentiment=0.0))
+
+
+def _reread(ticker, source='bluesky'):
+    """A genuinely fresh read, not just an in-memory one.
+
+    expire_all() alone clears this session's Python-side identity-map cache,
+    but repair() commits through its OWN nested app_context session (Flask-
+    SQLAlchemy scopes db.session per app-context id). If THIS session's own
+    transaction is still open from an earlier read -- MySQL's default
+    REPEATABLE READ fixes a snapshot at that read -- expire_all() forces a
+    requery but that requery runs inside the SAME frozen snapshot, so it can
+    still miss a commit repair() made from its own session in the meantime.
+    rollback() ends this session's transaction so the requery below opens a
+    new one and actually observes it.
+    """
+    db.session.rollback()
+    db.session.expire_all()
+    return RadarBucketSource.query.filter_by(
+        ticker=ticker, bucket_start=BS, source=source).one()
+
+
+# --- 1. Dry-run reports but never writes -------------------------------------
+
+def test_dry_run_reports_an_understated_row_but_writes_nothing(clean):
+    _source_row('ZZBF1', high_confidence_count=1, mention_count=1,
+               distinct_authors=1, distinct_text_ratio=1.0,
+               engagement_weighted_count=1.0, status='ok',
+               source_config_version='old-gen-1')
+    db.session.commit()
+    # Truth: 2 posts, 2 authors, 1 shared simhash (a copy-paste pair), engagement 6.
+    _post('ZZBF1', 'u1', simhash=999, score=3, num_comments=2)
+    _post('ZZBF1', 'u2', simhash=999, score=1, num_comments=0)
+    db.session.commit()
+
+    report = backfill.repair(apply=False, ticker_prefix='ZZBF')
+    assert report['examined'] == 1
+    assert report['repaired'] == 1
+    assert report['stale_scores'] == 0
+
+    row = _reread('ZZBF1')
+    assert row.high_confidence_count == 1
+    assert row.mention_count == 1
+    assert row.distinct_authors == 1
+    assert row.distinct_text_ratio == 1.0
+    assert row.engagement_weighted_count == 1.0
+    assert row.status == 'ok'
+    assert row.source_config_version == 'old-gen-1'
+    assert row.expected is None
+    assert row.variance is None
+    assert row.mention_z is None
+    assert row.baseline_days is None
+
+
+# --- 2. Apply repairs, converts Decimal, clears scores, preserves identity,
+#        never restamps the generation, and a second apply is a no-op --------
+
+def test_apply_repairs_clears_scores_preserves_generation_and_is_idempotent(clean):
+    _source_row('ZZBF2', high_confidence_count=1, mention_count=1,
+               distinct_authors=1, distinct_text_ratio=1.0,
+               engagement_weighted_count=1.0, status='ok',
+               source_config_version='old-gen-2',
+               expected=2.0, variance=0.5, mention_z=9.9, baseline_days=10)
+    db.session.commit()
+    # Truth: 3 posts / 3 authors, two share a simhash -> 2 distinct hashes,
+    # engagement (score+num_comments) 8 + 3 + 1 = 12.
+    _post('ZZBF2', 'u1', simhash=111, score=5, num_comments=3)
+    _post('ZZBF2', 'u2', simhash=111, score=2, num_comments=1)
+    _post('ZZBF2', 'u3', simhash=222, score=0, num_comments=1)
+    db.session.commit()
+
+    report = backfill.repair(apply=True, ticker_prefix='ZZBF')
+    assert report['examined'] == 1
+    assert report['repaired'] == 1
+
+    row = _reread('ZZBF2')
+    assert row.high_confidence_count == 3
+    assert row.mention_count == 3
+    assert row.distinct_authors == 3
+    assert row.distinct_text_ratio == pytest.approx(2 / 3)
+    assert row.engagement_weighted_count == pytest.approx(12.0)
+    # Identity preserved: apply repairs counts, it does not re-judge status,
+    # and a partial repair must never look like current-generation data.
+    assert row.status == 'ok'
+    assert row.source_config_version == 'old-gen-2'
+    # The score was computed off the understated count and must not survive.
+    assert row.expected is None
+    assert row.variance is None
+    assert row.mention_z is None
+    assert row.baseline_days is None
+
+    second = backfill.repair(apply=True, ticker_prefix='ZZBF')
+    assert second['repaired'] == 0
+
+
+# --- 3. Equality on one column must not short-circuit the others ------------
+
+def test_equal_high_confidence_count_does_not_block_other_repairs(clean):
+    _source_row('ZZBF3', high_confidence_count=2, mention_count=2,
+               distinct_authors=1, distinct_text_ratio=1.0,
+               engagement_weighted_count=1.0, status='ok',
+               source_config_version='old-gen-3')
+    db.session.commit()
+    # Truth: exactly 2 high mentions (matches high_confidence_count/mention_count
+    # already on the row) but 2 authors and a shared simhash and real engagement
+    # -- retained posts can refresh those columns after the bucket was written.
+    _post('ZZBF3', 'u1', simhash=555, score=4, num_comments=1)
+    _post('ZZBF3', 'u2', simhash=555, score=3, num_comments=2)
+    db.session.commit()
+
+    report = backfill.repair(apply=True, ticker_prefix='ZZBF')
+    assert report['repaired'] == 1
+
+    row = _reread('ZZBF3')
+    assert row.high_confidence_count == 2      # unchanged: already equal
+    assert row.mention_count == 2               # unchanged: already equal
+    assert row.distinct_authors == 2            # still repaired
+    assert row.distinct_text_ratio == pytest.approx(0.5)  # still repaired
+    assert row.engagement_weighted_count == pytest.approx(10.0)  # still repaired
+
+
+# --- 4. Stale scores clear on ANY non-NULL scoring column, keyed off status,
+#        and never on dry-run or on a row that is still `ok` ----------------
+
+def test_stale_scores_clear_on_any_column_and_only_for_non_ok_status(clean):
+    # No retained high mentions at all -- this row is reachable only through
+    # the second, status-driven pass, exactly the case the pre-existing
+    # rollup fix (Task 3) could never revisit.
+    _source_row('ZZBF4', status='truncated', source_config_version='old-gen-4',
+               expected=None, variance=None, mention_z=None, baseline_days=7)
+    # Control: still `ok`, so its (legitimately earned) score must survive.
+    _source_row('ZZBF5', status='ok', source_config_version='old-gen-5',
+               expected=1.1, variance=2.2, mention_z=3.3, baseline_days=14)
+    db.session.commit()
+
+    dry = backfill.repair(apply=False, ticker_prefix='ZZBF')
+    assert dry['stale_scores'] == 1
+    # A prefix that owns nothing here must scope the stale query to zero --
+    # otherwise this assertion only proves the repair loop is scoped, not the
+    # separate stale-score query, and the latter would silently pass by
+    # coincidence of whatever else happens to be in the database.
+    assert backfill.repair(apply=False, ticker_prefix='ZZNOPE')['stale_scores'] == 0
+
+    stale = _reread('ZZBF4')
+    assert stale.baseline_days == 7            # untouched on dry-run
+    assert stale.status == 'truncated'
+    ok_row = _reread('ZZBF5')
+    assert ok_row.mention_z == 3.3              # untouched on dry-run
+
+    applied = backfill.repair(apply=True, ticker_prefix='ZZBF')
+    assert applied['stale_scores'] == 1
+
+    stale = _reread('ZZBF4')
+    assert stale.expected is None
+    assert stale.variance is None
+    assert stale.mention_z is None
+    assert stale.baseline_days is None          # cleared though never set itself
+    assert stale.status == 'truncated'           # status is read, not rewritten
+    assert stale.source_config_version == 'old-gen-4'  # never restamped
+
+    ok_row = _reread('ZZBF5')
+    assert ok_row.mention_z == 3.3               # an `ok` row keeps its score
+    assert ok_row.expected == 1.1
+    assert ok_row.variance == 2.2
+    assert ok_row.baseline_days == 14
diff --git a/personal_apps/tests/test_radar_board.py b/personal_apps/tests/test_radar_board.py
index 7aedffb..f077c03 100644
--- a/personal_apps/tests/test_radar_board.py
+++ b/personal_apps/tests/test_radar_board.py
@@ -357,20 +357,191 @@ def test_venue_counts_are_taken_before_the_venue_filter(clean):
     bucket(f'{PREFIX}B', minutes_ago=30, source='bluesky')
     bucket(f'{PREFIX}B', minutes_ago=30, source='fourchan')
     db.session.commit()
 
     built = board.build(['bluesky', 'fourchan'], NOW, min_venues=2)
 
     assert built.venue_counts['any'] == 2
     assert built.venue_counts['multi'] == 1
 
 
+@pytest.fixture()
+def clean_breadth_reporting():
+    """Own exactly the one row used to test the breadth exclusion account."""
+    ticker = 'BDT13'
+
+    def wipe():
+        RadarBucketSource.query.filter_by(ticker=ticker).delete(
+            synchronize_session=False)
+        TickerUniverse.query.filter_by(symbol=ticker).delete(
+            synchronize_session=False)
+        db.session.commit()
+
+    with flask_app.app_context():
+        wipe()
+        yield ticker
+        wipe()
+
+
+def test_the_breadth_filter_reports_what_it_removed(clean_breadth_reporting):
+    universe(clean_breadth_reporting)
+    bucket(clean_breadth_reporting, minutes_ago=30, source='bluesky')
+    db.session.commit()
+
+    wide_open = board.build(['bluesky'], NOW, min_venues=1)
+    assert any(row.rank.ticker == clean_breadth_reporting
+               for row in wide_open.rows)
+
+    filtered = board.build(['bluesky'], NOW, min_venues=2)
+    assert not any(row.rank.ticker == clean_breadth_reporting
+                   for row in filtered.rows)
+    assert filtered.excluded.get('one_venue', 0) >= 1
+
+
+def test_the_leaderboard_uses_the_named_variance_floor(
+        clean_breadth_reporting, monkeypatch):
+    from features.radar import leaderboard
+
+    monkeypatch.setattr(leaderboard, 'VARIANCE_FLOOR', 4.0, raising=False)
+    universe(clean_breadth_reporting)
+    bucket(clean_breadth_reporting, minutes_ago=30, mentions=10,
+           expected=1.0, variance=0.01)
+    db.session.commit()
+
+    row = only(board.build(['bluesky'], NOW), clean_breadth_reporting).rank
+
+    assert row.mention_z == pytest.approx(4.5)
+
+
+def test_two_subreddits_are_one_venue(clean):
+    """The breadth filter's claim is INDEPENDENT corroboration.
+
+    Since 2026-08-26 each subreddit is its own stored source name, so a
+    ticker discussed in r/wallstreetbets and r/pennystocks now has two
+    entries in `sources`. It still has one venue: they share a platform, a
+    user population and a rate-limit budget, and "the same reading from two
+    independent sources" -- the words the surface puts on the
+    `single-source` mark -- is not what happened.
+    """
+    universe(f'{PREFIX}A')
+    universe(f'{PREFIX}B')
+    bucket(f'{PREFIX}A', minutes_ago=30, source='reddit:wallstreetbets')
+    bucket(f'{PREFIX}A', minutes_ago=45, source='reddit:pennystocks')
+    bucket(f'{PREFIX}B', minutes_ago=30, source='reddit:wallstreetbets')
+    bucket(f'{PREFIX}B', minutes_ago=30, source='bluesky')
+    db.session.commit()
+
+    built = board.build(['reddit', 'bluesky'], NOW, min_venues=2)
+
+    # A was in two subreddits and nowhere else: one venue, filtered out.
+    assert [e.rank.ticker for e in built.rows] == [f'{PREFIX}B']
+    assert built.venue_counts['multi'] == 1
+    a = only(board.build(['reddit', 'bluesky'], NOW), f'{PREFIX}A')
+    assert a.rank.venues == 1
+    # `sources` stays concrete -- that is the breakdown, and it is not the
+    # venue count.
+    assert a.rank.sources == ['reddit:pennystocks', 'reddit:wallstreetbets']
+    assert 'single-source' in a.rank.marks
+
+
+# ------------------------------------------------- pre-split root history ---
+#
+# Before 2026-08-26 every Reddit observation was stored under the bare name
+# `reddit`. Those rows are still in the table -- buckets are retained forever
+# -- and they are readable for what they COUNTED and unreadable for what they
+# SCORED. See config.expand_sources / expand_sources_for_history.
+
+def _old_root_bucket(ticker, minutes_ago, mentions):
+    """A bucket row exactly as production wrote it before the split."""
+    db.session.add(RadarBucketSource(
+        ticker=ticker, bucket_start=NOW - dt.timedelta(minutes=minutes_ago),
+        source='reddit', mention_count=mentions,
+        high_confidence_count=mentions, low_count=0, distinct_authors=6,
+        distinct_text_ratio=0.9, engagement_weighted_count=float(mentions),
+        # The real pre-split stamp, 16 hex characters -- which is also the
+        # column's whole width, so a descriptive placeholder does not fit.
+        status='ok', source_config_version='8106787f1fa72179',
+        expected=1.0, variance=2.0, mention_z=9.9, baseline_days=30))
+
+
+def test_the_pre_split_reddit_history_still_counts_on_the_series(clean):
+    """A raw count has no baseline behind it, so it may be pooled.
+
+    Leaving it out would be worse than a gap: Bluesky satisfies the same
+    hour's coverage test, so the hour is marked measured and the point is
+    drawn as a real number with Reddit's real, still-stored contribution
+    missing from the sum. That is an absence rendered as a zero.
+    """
+    universe(f'{PREFIX}A')
+    bucket(f'{PREFIX}A', minutes_ago=30, source='reddit:wallstreetbets',
+           mentions=10)
+    _old_root_bucket(f'{PREFIX}A', minutes_ago=45, mentions=7)
+    db.session.commit()
+
+    series = only(board.build(['reddit'], NOW), f'{PREFIX}A').series
+
+    assert at_hour(series, 1).count == 17
+
+
+def test_the_pre_split_reddit_history_is_kept_out_of_the_ranking(clean):
+    """The other half of the same rule: a z is relative to a BASELINE.
+
+    Those rows were baselined against "all of Reddit" under the previous
+    source_config_version. Admitting them to the scored read would sum two
+    populations' expectations into one z, which is what the stamp bump exists
+    to prevent.
+    """
+    universe(f'{PREFIX}A')
+    bucket(f'{PREFIX}A', minutes_ago=30, source='reddit:wallstreetbets',
+           mentions=10)
+    _old_root_bucket(f'{PREFIX}A', minutes_ago=45, mentions=7)
+    db.session.commit()
+
+    row = only(board.build(['reddit'], NOW), f'{PREFIX}A').rank
+
+    assert row.sources == ['reddit:wallstreetbets']
+    assert row.mentions == 10
+
+
+def test_one_named_subreddit_does_not_reach_the_undifferentiated_history(clean):
+    """`?sources=reddit:wallstreetbets` asks for that sub.
+
+    The pre-split rows are every subreddit pooled together and cannot be
+    attributed to one, so a concrete selection must not silently pick them
+    up -- only the root selection, which is what they actually were.
+    """
+    universe(f'{PREFIX}A')
+    bucket(f'{PREFIX}A', minutes_ago=30, source='reddit:wallstreetbets',
+           mentions=10)
+    _old_root_bucket(f'{PREFIX}A', minutes_ago=45, mentions=7)
+    db.session.commit()
+
+    series = only(board.build(['reddit:wallstreetbets'], NOW),
+                  f'{PREFIX}A').series
+
+    assert at_hour(series, 1).count == 10
+
+
+def test_the_pre_split_reddit_history_still_counts_towards_tone(clean):
+    """Same rule for the mention rows behind the tone split."""
+    universe(f'{PREFIX}A')
+    bucket(f'{PREFIX}A', minutes_ago=30, source='reddit:wallstreetbets')
+    post(f'{PREFIX}A', f'{PREFIX}new', 20, 0.6,
+         source='reddit:wallstreetbets')
+    post(f'{PREFIX}A', f'{PREFIX}old', 25, 0.6, source='reddit')
+    db.session.commit()
+
+    tone = only(board.build(['reddit'], NOW), f'{PREFIX}A').tone
+
+    assert tone.bullish == 2
+
+
 # ---------------------------------------------------------------- segments ---
 
 def test_small_unions_the_three_segments_below_mid(clean):
     """The tool is for penny stocks and unknowns. `Small` is what that means
     in the segment vocabulary: anything not large and not mid."""
     universe(f'{PREFIX}A', cap='50000000000')      # large
     universe(f'{PREFIX}B', cap='100000000')        # micro
     universe(f'{PREFIX}C', cap=None)               # unknown
     for suffix in 'ABC':
         bucket(f'{PREFIX}{suffix}', minutes_ago=30)
diff --git a/personal_apps/tests/test_radar_bucket_sources.py b/personal_apps/tests/test_radar_bucket_sources.py
index 4749376..f99a840 100644
--- a/personal_apps/tests/test_radar_bucket_sources.py
+++ b/personal_apps/tests/test_radar_bucket_sources.py
@@ -28,69 +28,69 @@ def ctx():
             RadarBucket.ticker.like('ZZ%')).delete(synchronize_session=False)
         db.session.commit()
         yield
         RadarBucketSource.query.filter(
             RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
         RadarBucket.query.filter(
             RadarBucket.ticker.like('ZZ%')).delete(synchronize_session=False)
         db.session.commit()
 
 
-def _row(source='stocktwits', ticker='ZZA', count=3, status='ok'):
+def _row(source='bluesky', ticker='ZZA', count=3, status='ok'):
     return RadarBucketSource(
         ticker=ticker, bucket_start=START, source=source,
         mention_count=count, high_confidence_count=count, low_count=0,
         distinct_authors=count, distinct_text_ratio=1.0,
         engagement_weighted_count=float(count), sentiment_mean=0.1,
         sentiment_stdev=None, status=status)
 
 
 def test_one_row_per_source_for_the_same_bucket(ctx):
-    for source in ('stocktwits', 'bluesky', 'fourchan'):
+    for source in ('reddit', 'bluesky', 'fourchan'):
         db.session.add(_row(source=source))
     db.session.commit()
     assert RadarBucketSource.query.filter_by(ticker='ZZA').count() == 3
 
 
 def test_the_same_source_twice_in_one_bucket_is_rejected(ctx):
     db.session.add(_row())
     db.session.commit()
     db.session.add(_row(count=99))
     with pytest.raises(sa.exc.IntegrityError):
         db.session.commit()
     db.session.rollback()
 
 
 def test_an_arbitrary_subset_pools_by_group_by(ctx):
     """The whole reason this table exists. The UI selector picks sources and
     the query sums over exactly those -- no schema knows their names."""
-    db.session.add(_row(source='stocktwits', count=10))
+    db.session.add(_row(source='reddit', count=10))
     db.session.add(_row(source='bluesky', count=4))
     db.session.add(_row(source='fourchan', count=1))
     db.session.commit()
 
-    chosen = ['stocktwits', 'bluesky']
+    chosen = ['reddit', 'bluesky']
     total = db.session.query(
         sa.func.sum(RadarBucketSource.mention_count)).filter(
         RadarBucketSource.ticker == 'ZZA',
         RadarBucketSource.bucket_start == START,
         RadarBucketSource.source.in_(chosen)).scalar()
     assert total == 14
 
 
 def test_a_source_can_be_missing_while_another_is_ok(ctx):
-    db.session.add(_row(source='stocktwits', status='ok'))
+    db.session.add(_row(source='reddit', status='ok'))
     db.session.add(_row(source='bluesky', status='truncated'))
     db.session.commit()
     statuses = {r.source: r.status for r in
                 RadarBucketSource.query.filter_by(ticker='ZZA').all()}
-    assert statuses == {'stocktwits': 'ok', 'bluesky': 'truncated'}
+    assert statuses == {'reddit': 'ok', 'bluesky': 'truncated'}
 
 
 def test_low_confidence_is_counted_separately_from_scored(ctx):
     """low is stored but never scored (spec 4.2). Keeping the count is what
     lets the extractor's false-positive rate be measured against real data."""
     row = _row(count=5)
     row.low_count = 40
     db.session.add(row)
     db.session.commit()
     db.session.expire(row)
diff --git a/personal_apps/tests/test_radar_buckets.py b/personal_apps/tests/test_radar_buckets.py
index 6081dbd..998f6d9 100644
--- a/personal_apps/tests/test_radar_buckets.py
+++ b/personal_apps/tests/test_radar_buckets.py
@@ -75,21 +75,21 @@ def test_distinct_text_ratio_catches_a_copy_paste_brigade(clean_buckets):
     this is the column that does."""
     rows = [row(author='u%d' % i, simhash=999) for i in range(4)]
     buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
     bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
     assert bucket.distinct_authors == 4
     assert bucket.distinct_text_ratio == pytest.approx(0.25)
 
 
 def test_per_source_status_is_stored_separately(clean_buckets):
     from models import RadarBucketSource
-    buckets.roll_up([row()], {'bluesky': 'ok', 'stocktwits': 'missing'},
+    buckets.roll_up([row()], {'bluesky': 'ok', 'reddit': 'missing'},
                     {dt.datetime(2026, 4, 15, 14, 0, 0)})
     assert RadarBucket.query.filter_by(ticker='ZZA').one().sources_ok == 1
     rows = {r.source: r.status for r in
             RadarBucketSource.query.filter_by(ticker='ZZA').all()}
     # A `missing` source writes no row at all -- that is the rule.
     assert rows == {'bluesky': 'ok'}
 
 
 def test_truncated_counts_are_kept_and_marked(clean_buckets):
     from models import RadarBucketSource
@@ -98,21 +98,21 @@ def test_truncated_counts_are_kept_and_marked(clean_buckets):
     bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
     assert bucket.mention_count == 1
     assert bucket.sources_ok == 0
     assert RadarBucketSource.query.filter_by(
         ticker='ZZA', source='bluesky').one().status == 'truncated'
 
 
 def test_a_missing_source_writes_no_bucket_rather_than_a_zero(clean_buckets):
     """The single most important rule in the ingest layer. A zero here would
     poison the baseline and manufacture a spike when ingest resumes."""
-    written = buckets.roll_up([], {'stocktwits': 'missing', 'bluesky': 'missing'},
+    written = buckets.roll_up([], {'reddit': 'missing', 'bluesky': 'missing'},
                               {dt.datetime(2026, 4, 15, 14, 0, 0)})
     assert written == 0
     assert RadarBucket.query.filter_by(ticker='ZZA').count() == 0
 
 
 def test_a_re_read_of_the_same_window_does_not_double(clean_buckets):
     """A cycle that re-reads a window it already read must not add to it.
 
     This is the overlap case, and it is the only one the old version of this
     test covered -- it fed the second call a SUPERSET, which no source
@@ -180,28 +180,53 @@ def test_scoring_columns_are_left_untouched(clean_buckets):
     buckets.roll_up([row(), row(author='u2', simhash=2)], ALL_OK,
                     {dt.datetime(2026, 4, 15, 14, 0, 0)})
     db.session.expire(source)
     assert source.status == 'ok'
     assert source.expected == 1.0
     assert source.variance == 2.0
     assert source.mention_z == 4.2
     assert source.baseline_days == 9
 
 
+@pytest.mark.parametrize('previous_version', [None, 'old-generation'])
+def test_a_generation_restamp_clears_every_stale_score(clean_buckets,
+                                                        previous_version):
+    """A restamp cannot make an old score look current."""
+    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
+    buckets.roll_up([row()], ALL_OK, start)
+    source = RadarBucketSource.query.filter_by(
+        ticker='ZZA', source='bluesky').one()
+    source.source_config_version = previous_version
+    source.expected = 1.0
+    source.variance = 2.0
+    source.mention_z = 4.2
+    source.baseline_days = 9
+    db.session.commit()
+
+    buckets.roll_up([row()], ALL_OK, start)
+
+    db.session.expire(source)
+    assert source.source_config_version == source_config_version()
+    assert source.expected is None
+    assert source.variance is None
+    assert source.mention_z is None
+    assert source.baseline_days is None
+
+
 def test_per_source_rows_are_written(clean_buckets):
-    rows = [row(source='stocktwits', author='u1', simhash=1),
+    rows = [row(source='reddit', author='u1', simhash=1),
             row(source='bluesky', author='u2', simhash=2)]
-    buckets.roll_up(rows, {'stocktwits': 'ok', 'bluesky': 'ok'},
+    buckets.roll_up(rows, {'reddit': 'ok', 'bluesky': 'ok'},
                     {dt.datetime(2026, 4, 15, 14, 0, 0)})
     per_source = {r.source: r.mention_count for r in
                   RadarBucketSource.query.filter_by(ticker='ZZA').all()}
-    assert per_source == {'stocktwits': 1, 'bluesky': 1}
+    assert per_source == {'reddit': 1, 'bluesky': 1}
     assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 2
 
 
 def test_an_unknown_source_name_needs_no_schema_change(clean_buckets):
     """The point of the child table. A source nobody has heard of writes a row
     like any other -- no migration, no column, no code that knows its name."""
     buckets.roll_up([row(source='some_new_source')], {'some_new_source': 'ok'},
                     {dt.datetime(2026, 4, 15, 14, 0, 0)})
     assert RadarBucketSource.query.filter_by(
         ticker='ZZA', source='some_new_source').one().mention_count == 1
@@ -248,22 +273,22 @@ def test_a_bucket_with_only_lows_still_records_its_source_status(clean_buckets):
                     {dt.datetime(2026, 4, 15, 14, 0, 0)})
     assert RadarBucketSource.query.filter_by(
         ticker='ZZA', source='bluesky').one().status == 'ok'
 
 
 def test_the_config_version_is_stamped_on_each_source_row(clean_buckets):
     """Baselines exclude history from before a config change, and that
     exclusion is per (ticker, source). Reading it off the parent bucket would
     mean joining a table the baseline query has no other reason to touch."""
     from features.radar.config import source_config_version
-    buckets.roll_up([row(source='stocktwits'), row(source='bluesky')],
-                    {'stocktwits': 'ok', 'bluesky': 'ok'},
+    buckets.roll_up([row(source='reddit'), row(source='bluesky')],
+                    {'reddit': 'ok', 'bluesky': 'ok'},
                     {dt.datetime(2026, 4, 15, 14, 0, 0)})
     versions = {r.source: r.source_config_version for r in
                 RadarBucketSource.query.filter_by(ticker='ZZA').all()}
     assert len(versions) == 2
     assert set(versions.values()) == {source_config_version()}
 
 
 # --- The promotion leak, measured on live data 2026-08-25 -------------------
 #
 # ICE 315, IA 393, MAGA 256 and GOP 210 sat in the SCORED set over seven days,
diff --git a/personal_apps/tests/test_radar_config.py b/personal_apps/tests/test_radar_config.py
index 876ed30..b2e190a 100644
--- a/personal_apps/tests/test_radar_config.py
+++ b/personal_apps/tests/test_radar_config.py
@@ -2,26 +2,48 @@
 """The source config version is what stops a source being added from
 manufacturing a market-wide spike the next morning (spec 6.6). It has to be
 stable across runs and sensitive to the list it hashes."""
 from features.radar import config
 
 
 def test_version_is_stable_across_calls():
     assert config.source_config_version() == config.source_config_version()
 
 
+def test_the_superseded_page_cap_is_gone():
+    from features.radar import config
+
+    assert not hasattr(config, 'PAGE_CAP')
+
+
 def test_version_changes_when_the_source_list_changes(monkeypatch):
     before = config.source_config_version()
     monkeypatch.setattr(config, 'SOURCES', config.SOURCES + ('newsource',))
     assert config.source_config_version() != before
 
 
+def test_version_changes_when_the_rollup_generation_changes(monkeypatch):
+    """A corrected aggregate population cannot share the old baseline."""
+    before = config.source_config_version()
+    monkeypatch.setattr(config, 'ROLLUP_GENERATION',
+                        config.ROLLUP_GENERATION + 1, raising=False)
+    assert config.source_config_version() != before
+
+
+def test_version_changes_when_the_source_name_generation_changes(monkeypatch):
+    """Aggregate Reddit and per-subreddit Reddit are different populations."""
+    before = config.source_config_version()
+    monkeypatch.setattr(config, 'SOURCE_NAME_GENERATION',
+                        config.SOURCE_NAME_GENERATION + 1)
+    assert config.source_config_version() != before
+
+
 def test_version_ignores_source_order():
     forward = config.source_config_version()
     reversed_list = tuple(reversed(config.SOURCES))
     import unittest.mock as mock
     with mock.patch.object(config, 'SOURCES', reversed_list):
         assert config.source_config_version() == forward
 
 
 def test_version_is_short_hex():
     version = config.source_config_version()
@@ -49,21 +71,20 @@ def test_ipv4_preference_applies_when_set(monkeypatch):
     original = urllib3_connection.allowed_gai_family
     monkeypatch.setenv('RADAR_FORCE_IPV4', '1')
     try:
         assert config.prefer_ipv4_if_configured() is True
         assert urllib3_connection.allowed_gai_family() == socket.AF_INET
     finally:
         urllib3_connection.allowed_gai_family = original
 
 
 def test_finance_native_sources_allow_bare_tokens():
-    assert config.bare_tokens_allowed('stocktwits') is True
     assert config.bare_tokens_allowed('fourchan') is True
 
 
 def test_bluesky_reads_bare_tokens_since_the_tiering_changed():
     """Reversed 2026-08-23. This asserted False, set after the first live pass
     found IA (Iowa), GOP and AP among Bluesky's top bare tokens.
 
     What changed is not the noise but what it costs: an uncorroborated bare
     token is stored `low` and never scored, so those three now occupy table
     rows and nothing else. Meanwhile the promotion path -- a distinctive
@@ -81,29 +102,35 @@ def test_an_uncharacterised_source_defaults_to_cashtags_only():
 
 
 def test_coin_shaped_symbols_are_dropped_on_general_sources():
     """BCH is Banco de Chile and LINK is Interlink Electronics, so the
     name-based crypto filter cannot see them. On the first live hour four of
     the ten loudest tickers were coins read as companies, BCH the largest."""
     assert config.coin_collision_dropped('bluesky', 'BCH') is True
     assert config.coin_collision_dropped('fourchan', 'LINK') is True
 
 
-def test_finance_native_sources_keep_them():
-    """On StockTwits, $LINK means Interlink -- the population is discussing
-    equities, so the company reading is the right one."""
-    assert config.coin_collision_dropped('stocktwits', 'LINK') is False
-    assert config.coin_collision_dropped('stocktwits', 'BCH') is False
+def test_a_finance_native_source_can_opt_into_coin_symbols(monkeypatch):
+    """The extension point, kept alive with no live source using it.
+
+    StockTwits was the only population where $LINK meant Interlink rather
+    than Chainlink. It is retired; this pins that a future finance-native
+    source can still opt in, rather than the map quietly becoming a constant
+    nobody can override.
+    """
+    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'bluesky', True)
+    assert config.coin_collision_dropped('bluesky', 'LINK') is False
+    assert config.coin_collision_dropped('bluesky', 'BCH') is False
 
 
 def test_ordinary_tickers_are_untouched_everywhere():
-    for source in ('bluesky', 'fourchan', 'stocktwits'):
+    for source in ('bluesky', 'fourchan', 'reddit'):
         assert config.coin_collision_dropped(source, 'MRNA') is False
         assert config.coin_collision_dropped(source, 'AAPL') is False
 
 
 def test_an_unknown_source_drops_them():
     """Same safe default as bare tokens: unmeasured sources get the strict
     reading."""
     assert config.coin_collision_dropped('some_new_network', 'BCH') is True
 
 
@@ -177,20 +204,61 @@ def test_every_configured_source_has_a_kind():
 
 
 def test_an_unknown_source_gets_the_stricter_gate():
     """Forum is the tighter of the two. A source nobody has characterised
     should be judged strictly, not leniently."""
     from features.radar.config import source_kind
 
     assert source_kind('something-new') == 'forum'
 
 
+def test_a_prefixed_source_inherits_its_roots_policy():
+    """`reddit:wallstreetbets` is Reddit for every per-source judgement.
+
+    Splitting the source name is what stops one sub's permanent feed rollover
+    from marking every other sub's buckets truncated. It must not also split
+    the policy: an unlisted sub inherits Reddit's rules rather than falling
+    through to the strict default, which would silently disable bare tokens on
+    a source that depends on them.
+    """
+    from features.radar import config
+
+    assert config.source_root('reddit:wallstreetbets') == 'reddit'
+    assert config.source_root('bluesky') == 'bluesky'
+    assert config.bare_tokens_allowed('reddit:wallstreetbets') is True
+    assert config.bare_token_confidence('reddit:pennystocks') == 'high'
+    assert config.source_kind('reddit:thetagang') == 'forum'
+    assert config.coin_collision_dropped('reddit:weedstocks', 'LINK') is True
+
+
+def test_every_policy_lookup_uses_the_prefixed_sources_root(monkeypatch):
+    """The less visible policy extension points must inherit the root too."""
+    monkeypatch.setitem(config.SOURCE_KIND, 'reddit', 'broadcast')
+    monkeypatch.setitem(config.SINGLE_LETTER_CASHTAGS, 'reddit', True)
+    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'reddit', True)
+
+    assert config.source_kind('reddit:wallstreetbets') == 'broadcast'
+    assert config.single_letter_cashtags_allowed(
+        'reddit:wallstreetbets') is True
+    assert config.coin_collision_dropped(
+        'reddit:wallstreetbets', 'LINK') is False
+
+
+def test_root_reddit_expands_to_every_configured_concrete_source():
+    expected = ['reddit:%s' % sub for sub in config.REDDIT_SUBS]
+
+    assert config.expand_sources(['bluesky', 'reddit']) == [
+        'bluesky', *expected]
+    assert config.expand_sources(['reddit:wallstreetbets']) == [
+        'reddit:wallstreetbets']
+
+
 def test_the_version_stamp_covers_the_distinctiveness_rule():
     """Distinctiveness decides whether a bare mention is promoted to `high`,
     so changing it changes WHICH mentions get counted -- the exact
     discontinuity the stamp warms up from. It hashed the source list and the
     extraction patterns but not this, which is the same omission that shipped
     three extraction fixes over stale baselines on 2026-08-22.
     """
     from features.radar import config
 
     before = config.source_config_version()
@@ -247,10 +315,42 @@ def test_an_empty_selection_still_means_everything():
     assert segments_in(None) == ()
 
 
 def test_a_single_string_selection_still_works():
     """Bookmarked URLs carry `?segment=small`, and the default is a bare
     string. Widening the parameter must not break either."""
     from features.radar.config import segments_in
 
     assert set(segments_in('small')) == {'micro', 'unknown', 'recent_ipo'}
     assert set(segments_in('large')) == {'large'}
+
+
+def test_stocktwits_is_retired():
+    """Cloudflare bot management, diagnosed 2026-08-26.
+
+    403 on every endpoint with every user agent, from two networks. It reported
+    `missing` honestly for five days and produced nothing, while remaining a
+    selectable venue in the UI -- an invitation to filter on a source that has
+    never returned a row.
+    """
+    from features.radar import config
+
+    assert 'stocktwits' not in config.SOURCES
+    assert 'stocktwits' not in config.BARE_TOKENS_ALLOWED
+    assert 'stocktwits' not in config.SINGLE_LETTER_CASHTAGS
+    assert 'stocktwits' not in config.SOURCE_KIND
+    assert not hasattr(config, 'STOCKTWITS_REQUESTS_PER_HOUR')
+
+
+def test_no_source_reads_a_coin_symbol_as_a_company():
+    """A consequence of the retirement, named so it is not rediscovered.
+
+    StockTwits was the only population where $LINK meant Interlink rather than
+    Chainlink. With it gone, COIN_COLLISION_SYMBOLS are dropped everywhere --
+    49 real tickers lose their mentions on every live source. The map stays a
+    map rather than collapsing to a constant, because Telegram will need its
+    own entry and the extension point is the point.
+    """
+    from features.radar import config
+
+    assert not any(config.COIN_SYMBOLS_MEAN_STOCKS.values())
+    assert config.coin_collision_dropped('bluesky', 'LINK') is True
diff --git a/personal_apps/tests/test_radar_daemon.py b/personal_apps/tests/test_radar_daemon.py
index d8e2da1..715fe32 100644
--- a/personal_apps/tests/test_radar_daemon.py
+++ b/personal_apps/tests/test_radar_daemon.py
@@ -1,20 +1,22 @@
 # personal_apps/tests/test_radar_daemon.py
 """Cadence follows the NYSE session, not a fixed interval and not German local
 time (spec 4.3, 4.4).
 
 The DST case is the one that would otherwise ship broken: for about three weeks
 each spring the US session starts an hour earlier in Berlin, and any cadence
 keyed on Berlin hours would poll at overnight rates through a live open.
 """
 import datetime as dt
 
+import pytest
+
 import run_radar_ingest as daemon
 
 
 def _utc(year, month, day, hour, minute=0):
     return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)
 
 
 def test_premarket_and_regular_poll_fastest():
     assert daemon.interval_for('premarket') == 180
     assert daemon.interval_for('regular') == 180
@@ -45,33 +47,33 @@ def test_interval_during_the_dst_desync_window():
     assert daemon.interval_for(state) == 180
 
 
 def test_tick_returns_the_cycle_summary(monkeypatch):
     monkeypatch.setattr(daemon.ingest, 'run_cycle',
                         lambda now, fetchers: {'per_source': {}, 'mentions': 3,
                                               'buckets_written': 1,
                                               'catchup_depth': 1,
                                               'posts_seen': 3, 'posts_new': 3})
     result = daemon.tick(_utc(2026, 4, 15, 14),
-                         fetchers={'stocktwits': lambda s: None})
+                         fetchers={'bluesky': lambda s: None})
     assert result['mentions'] == 3
 
 
 def test_a_cycle_that_raises_does_not_kill_the_daemon(monkeypatch):
     """APScheduler drops a job whose function raises. Losing ingest until the
     next restart is worse than losing one cycle."""
     def boom(now, fetchers):
         raise RuntimeError('provider exploded')
 
     monkeypatch.setattr(daemon.ingest, 'run_cycle', boom)
     result = daemon.tick(_utc(2026, 4, 15, 14),
-                         fetchers={'stocktwits': lambda s: None})
+                         fetchers={'bluesky': lambda s: None})
     assert result['status'] == 'error'
 
 
 def test_every_configured_source_gets_a_fetcher():
     fetchers = daemon.build_fetchers()
     assert set(fetchers) == set(daemon.SOURCES)
     assert all(callable(f) for f in fetchers.values())
 
 
 def test_reddit_reads_the_feeds_and_never_the_closed_api():
@@ -97,26 +99,20 @@ def test_reddit_reads_the_feeds_and_never_the_closed_api():
     # docstring necessarily mentions the .json route in order to explain why
     # it is not used, and a text search cannot tell an explanation from a call.
     urls = [value for value in vars(reddit).values()
             if isinstance(value, str) and value.startswith('http')]
 
     assert urls == [reddit.FEED], f'unexpected endpoint reachable: {urls}'
     assert '.rss' in reddit.FEED
     assert '.json' not in reddit.FEED
 
 
-def test_the_request_budget_is_a_sane_fraction_of_the_hourly_one():
-    """StockTwits publishes no limit; this is a conservative guess with
-    adaptive backoff, not a documented ceiling."""
-    assert 1 <= daemon.SYMBOL_BUDGET_PER_CYCLE <= 40
-
-
 def test_reddit_runs_on_its_own_clock_not_the_market_session():
     """The regression: four subs per 1800-second overnight cycle meant a full
     rotation of eighteen took over two hours, against a feed that turns over
     in under two minutes. Six hours of it produced one scorable mention.
 
     Reddit does not stop at the closing bell, and a missed comment is gone
     rather than late -- there is no cursor to catch up from.
     """
     import inspect
     source = inspect.getsource(daemon.main)
@@ -128,78 +124,87 @@ def test_reddit_runs_on_its_own_clock_not_the_market_session():
 
 def test_the_first_cycle_is_scheduled_immediately():
     """An interval trigger fires only after the interval elapses. Overnight
     that is thirty minutes of silence after starting the service, which reads
     as a dead daemon."""
     import inspect
     source = inspect.getsource(daemon.main)
     assert 'next_run_time' in source, 'first cycle would wait a full interval'
 
 
-def _stub_scheduling(monkeypatch, due):
-    monkeypatch.setattr(daemon.scheduling, 'ensure_tracked',
-                        lambda *a, **k: 0)
-    monkeypatch.setattr(daemon.scheduling, 'due_symbols',
-                        lambda *a, **k: list(due))
-    monkeypatch.setattr(daemon.scheduling, 'record_poll', lambda *a, **k: None)
-
-
-def test_a_blocked_source_reports_missing_not_ok(monkeypatch):
-    """Live on the VPS, StockTwits 403'd every request and the cycle recorded
-    it as `ok` with zero counts -- because trending failed, the poll set was
-    empty, and an empty symbol list short-circuits to success. Thirty days of
-    those zeros would make the first real data look like an enormous spike."""
-    import datetime as dt
-
-    def blocked(*a, **k):
-        raise daemon.stocktwits.StockTwitsUnavailable('403 Forbidden')
-
-    monkeypatch.setattr(daemon.stocktwits, 'trending', blocked)
-    _stub_scheduling(monkeypatch, due=[])
-
-    result = daemon._stocktwits_fetcher(object())(dt.datetime(2026, 8, 21))
-    assert result.status == 'missing'
-    assert result.posts == []
-
-
-def test_nothing_due_on_a_healthy_source_is_still_ok(monkeypatch):
-    """The distinction the bug collapsed: no work to do is a real zero, and
-    only a failure is `missing`."""
-    import datetime as dt
-
-    monkeypatch.setattr(daemon.stocktwits, 'trending', lambda c: ['AAA'])
-    _stub_scheduling(monkeypatch, due=[])
-
-    result = daemon._stocktwits_fetcher(object())(dt.datetime(2026, 8, 21))
-    assert result.status == 'ok'
-
-
 def test_scoring_covers_every_configured_source(monkeypatch):
     seen = []
     monkeypatch.setattr(daemon.scoring, 'score_source',
                         lambda source, now, **k: seen.append(source) or 1)
     daemon.score_all(_utc(2026, 8, 21, 14))
-    assert set(seen) == set(daemon.SOURCES)
+    expected = {'bluesky', 'fourchan'} | {
+        'reddit:%s' % sub for sub in daemon.REDDIT_SUBS}
+    assert set(seen) == expected
+    assert 'reddit' not in seen
+
+
+def test_reddit_poll_state_stays_keyed_to_the_root_source(monkeypatch):
+    """Concrete post names must not retire the scheduler's learned state."""
+    from app import app as flask_app
+    from extensions import db
+    from features.radar.sources import FetchResult
+    from models import RadarPollState
+
+    sub = 'zz_task9_sub'
+    root = 'reddit'
+    concrete = 'reddit:%s' % sub
+    owned_sources = (root, concrete)
+    now = dt.datetime(2026, 8, 27, 12, 0, 0)
+
+    def wipe_owned_state():
+        RadarPollState.query.filter(
+            RadarPollState.source.in_(owned_sources),
+            RadarPollState.symbol == sub).delete(synchronize_session=False)
+        db.session.commit()
+
+    with flask_app.app_context():
+        wipe_owned_state()
+        monkeypatch.setattr(daemon, 'REDDIT_SUBS', (sub,))
+        monkeypatch.setattr(daemon, '_utcnow', lambda: now)
+        monkeypatch.setattr(daemon.scheduling, 'retire_untracked',
+                            lambda source, symbols: 0)
+        monkeypatch.setattr(daemon.scheduling, 'due_symbols',
+                            lambda source, current, limit: [sub])
+        monkeypatch.setattr(
+            daemon.reddit, 'fetch',
+            lambda since_by_sub, client: FetchResult(
+                posts=[], status='ok', rates={sub: 0.0},
+                per_source_status={concrete: 'ok'}))
+
+        try:
+            daemon._reddit_fetcher(object())(now - dt.timedelta(minutes=5))
+            rows = RadarPollState.query.filter(
+                RadarPollState.source.in_(owned_sources),
+                RadarPollState.symbol == sub).all()
+            assert [(row.source, row.symbol) for row in rows] == [(root, sub)]
+        finally:
+            db.session.rollback()
+            wipe_owned_state()
 
 
 def test_one_source_failing_to_score_does_not_stop_the_others(monkeypatch):
     """Same rule as ingest. A bad baseline on one source is not a reason to
     leave the others unscored."""
     def flaky(source, now, **k):
         if source == 'bluesky':
             raise RuntimeError('bad baseline')
         return 3
 
     monkeypatch.setattr(daemon.scoring, 'score_source', flaky)
     result = daemon.score_all(_utc(2026, 8, 21, 14))
     assert result['bluesky'] == 0
-    assert result['stocktwits'] == 3
+    assert result['fourchan'] == 3
 
 
 def test_quote_polling_targets_the_loudest_tickers(monkeypatch):
     """The free tier is 60 calls a minute, so quotes go to the tickers actually
     on the board rather than to all 12,000 in the universe."""
     asked = {}
 
     class FakeProvider:
         def quotes(self, symbols):
             asked['symbols'] = list(symbols)
@@ -319,34 +324,43 @@ def test_a_failing_profile_provider_does_not_kill_the_cycle(monkeypatch):
 
 
 def test_the_nightly_prune_covers_quotes_as_well_as_posts():
     """The regression here is an omission, like the profile job's.
 
     retention.py handled posts and mentions and never touched radar_quotes,
     so that table grew without bound -- and since the board started reading it
     on every load it is the one most able to undo the work that made it fast.
     Asserting both are called, because the failure mode is a function that
     exists and is never reached.
+
+    All three pruners are faked here, never the real ones: the real
+    prune_mention_events would run against actual current time, and the
+    shared dev database's radar_mention_events rows are all older than the
+    48-hour retention window by the time this suite runs -- an unfaked call
+    would delete every real row in the table.
     """
     called = []
 
     daemon.retention.prune_posts, real_posts = (
         lambda now: called.append('posts') or 0, daemon.retention.prune_posts)
     daemon.retention.prune_quotes, real_quotes = (
         lambda now: called.append('quotes') or 0, daemon.retention.prune_quotes)
+    daemon.retention.prune_mention_events, real_events = (
+        lambda now: called.append('events') or 0, daemon.retention.prune_mention_events)
     try:
         daemon._scheduled_prune()
     finally:
         daemon.retention.prune_posts = real_posts
         daemon.retention.prune_quotes = real_quotes
+        daemon.retention.prune_mention_events = real_events
 
-    assert called == ['posts', 'quotes']
+    assert called == ['posts', 'quotes', 'events']
 
 
 def test_the_daemon_schedules_a_profile_job():
     """The regression this pins is an omission, not a bug: every other piece
     of the profile path existed and worked, and nothing called it."""
     import inspect
     source = inspect.getsource(daemon.main)
 
     assert "id='radar_profiles'" in source
     assert '_scheduled_profiles' in source
@@ -464,10 +478,180 @@ def test_the_daemon_retires_subreddits_dropped_from_the_config():
 
     So a subreddit removed from the list keeps its radar_poll_state row and
     keeps being handed turns -- consuming exactly the request budget the
     removal was meant to free, and silently. Ten subs were dropped on
     2026-08-25; without this the cut would have changed nothing at all.
     """
     import inspect
     source = inspect.getsource(daemon._reddit_fetcher)
 
     assert 'retire_untracked' in source
+
+
+# Task 3c: generation 2 rebuilds buckets from the complete mention journal
+# instead of one cursor slice, which changes measured volume even though the
+# extractor's membership rules do not. _prepare_rollup_generation is the
+# one-time startup pass that keeps that correction from silently mixing with
+# understated pre-fix history. The end-to-end version of this, against real
+# rows, lives in
+# tests/test_radar_journal.py::test_deploy_bootstrap_preserves_the_complete_open_bucket;
+# these pin the daemon's own wiring and its fail-closed branch in isolation.
+
+def test_prepare_rollup_generation_bootstraps_then_invalidates_then_commits(
+        monkeypatch):
+    """The call order is the contract: bootstrap has to land in the journal
+    before anything downstream reads it, and invalidation is what actually
+    clears the columns the leaderboard reads mention_z from."""
+    calls = []
+
+    def fake_bootstrap(since):
+        calls.append(('bootstrap', since))
+        return 3
+
+    def fake_invalidate(version, since):
+        calls.append(('invalidate', version, since))
+        return 5
+
+    monkeypatch.setattr(daemon.journal, 'bootstrap_from_mentions', fake_bootstrap)
+    monkeypatch.setattr(daemon.scoring, 'invalidate_incompatible_scores',
+                        fake_invalidate)
+    monkeypatch.setattr(daemon.db.session, 'commit',
+                        lambda: calls.append(('commit',)))
+
+    now = _utc(2026, 4, 15, 15, 0)
+    recovered, invalidated = daemon._prepare_rollup_generation(now)
+
+    assert (recovered, invalidated) == (3, 5)
+    assert [call[0] for call in calls] == ['bootstrap', 'invalidate', 'commit']
+    since = now.replace(tzinfo=None) - dt.timedelta(
+        hours=daemon.MENTION_EVENT_RETENTION_HOURS)
+    assert calls[0][1] == since, 'bootstrap must see the retention-window floor'
+    assert calls[1][2] == since, 'invalidation must share the same floor'
+    assert calls[1][1] == daemon.source_config_version(), (
+        'invalidation must receive the exact current generation')
+    assert calls[2] == ('commit',), (
+        'bootstrap and invalidation must be durable before startup continues')
+
+
+def test_prepare_rollup_generation_fails_closed_on_unrecovered_legacy_evidence(
+        monkeypatch):
+    """Zero recovered is ambiguous by itself -- a fresh database and a
+    migrated one whose bootstrap silently failed both report it. A legacy
+    bucket already carrying high_confidence_count in the overlap window is
+    what tells the two apart: it is proof the evidence existed, so recovering
+    none of it means bootstrap is broken, not that the world was quiet.
+    Continuing anyway would serve a relabelled score for evidence that never
+    actually made it into the journal.
+
+    The legacy-evidence check has no ticker filter -- production has to catch
+    ANY source's bootstrap failure, not one ticker's -- so `now` is
+    2027-06-01, beyond the real and seeded database history, so the global
+    legacy-evidence query cannot match unrelated rows.
+    """
+    from app import app as flask_app
+    from extensions import db
+    from models import RadarBucketSource
+
+    now = _utc(2027, 6, 1, 6, 0)
+    since = now.replace(tzinfo=None) - dt.timedelta(
+        hours=daemon.MENTION_EVENT_RETENTION_HOURS)
+    with flask_app.app_context():
+        RadarBucketSource.query.filter(
+            RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
+        db.session.add(RadarBucketSource(
+            ticker='ZZDAEMON', bucket_start=since + dt.timedelta(hours=1),
+            source='bluesky', mention_count=9, high_confidence_count=6,
+            low_count=0, distinct_authors=5, distinct_text_ratio=1.0,
+            engagement_weighted_count=9.0, status='ok',
+            source_config_version='old-generation'))
+        db.session.commit()
+
+    monkeypatch.setattr(daemon.journal, 'bootstrap_from_mentions', lambda s: 0)
+    invalidate_called = []
+    monkeypatch.setattr(daemon.scoring, 'invalidate_incompatible_scores',
+                        lambda v, s: invalidate_called.append(True) or 0)
+
+    try:
+        with pytest.raises(RuntimeError):
+            daemon._prepare_rollup_generation(now)
+        assert not invalidate_called, (
+            'a failed-closed bootstrap must never reach invalidation, or an '
+            'ingest cycle could still slip in before the process actually exits')
+    finally:
+        with flask_app.app_context():
+            RadarBucketSource.query.filter(
+                RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
+            db.session.commit()
+
+
+def test_prepare_rollup_generation_continues_when_the_database_is_genuinely_quiet(
+        monkeypatch):
+    """The complementary case: zero recovered with no legacy evidence in the
+    overlap window at all is a fresh or genuinely quiet database, and the
+    fail-closed check meant for a broken migration must not block it.
+
+    Uses the same 2027-06-01 window as the fail-closed test, beyond the real
+    and seeded database history.
+    """
+    from app import app as flask_app
+    from extensions import db
+    from models import RadarBucketSource
+
+    now = _utc(2027, 6, 1, 6, 0)
+    with flask_app.app_context():
+        RadarBucketSource.query.filter(
+            RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
+        db.session.add(RadarBucketSource(
+            ticker='ZZQUIET', bucket_start=now.replace(tzinfo=None),
+            source='bluesky', mention_count=0, high_confidence_count=0,
+            low_count=0, distinct_authors=0, distinct_text_ratio=1.0,
+            engagement_weighted_count=0.0, status='missing',
+            source_config_version='old-generation'))
+        db.session.commit()
+
+    monkeypatch.setattr(daemon.journal, 'bootstrap_from_mentions', lambda s: 0)
+    invalidate_called = []
+    monkeypatch.setattr(daemon.scoring, 'invalidate_incompatible_scores',
+                        lambda v, s: invalidate_called.append(True) or 0)
+
+    try:
+        recovered, invalidated = daemon._prepare_rollup_generation(now)
+
+        assert (recovered, invalidated) == (0, 0)
+        assert invalidate_called, 'the quiet path must still reach invalidation'
+    finally:
+        with flask_app.app_context():
+            RadarBucketSource.query.filter(
+                RadarBucketSource.ticker.like('ZZ%')).delete(
+                    synchronize_session=False)
+            db.session.commit()
+
+
+def test_main_prepares_the_rollup_generation_before_building_fetchers(monkeypatch):
+    """No cycle may run against a mixed-generation database, so a bootstrap or
+    invalidation failure has to prevent build_fetchers and the scheduler from
+    ever existing -- not merely appear earlier than them in main()'s source
+    text.
+
+    This replaces a source-inspection version of the test that only checked
+    substring order. The reviewer wrapped the _prepare_rollup_generation call
+    in main() with `try/except Exception: recovered, invalidated = 0, 0` --
+    the substrings stayed in the same order, so the old assertion kept
+    passing, and all 40 daemon tests were still green, while the daemon would
+    go on to start ingest over evidence it could not recover. Watching
+    build_fetchers actually run, or not, is the only way to tell a real raise
+    from one that got swallowed; main() raises on its first statement after
+    logging config, so it never reaches the blocking scheduler loop.
+    """
+    def explode(now):
+        raise RuntimeError('rollup generation bootstrap failed')
+
+    called = []
+    monkeypatch.setattr(daemon, '_prepare_rollup_generation', explode)
+    monkeypatch.setattr(daemon, 'build_fetchers', lambda: called.append(True))
+
+    with pytest.raises(RuntimeError):
+        daemon.main()
+
+    assert not called, ('a failed rollup-generation prepare must never reach '
+                        'build_fetchers, or a cycle could run before the '
+                        'process actually exits')
diff --git a/personal_apps/tests/test_radar_detail.py b/personal_apps/tests/test_radar_detail.py
index 32b5f59..5355400 100644
--- a/personal_apps/tests/test_radar_detail.py
+++ b/personal_apps/tests/test_radar_detail.py
@@ -154,36 +154,43 @@ def test_a_span_shorter_than_a_year_takes_the_recent_end(clean):
 
     month = chart_for(f'{PREFIX}A', detail.SPAN_DAYS['1M'])
 
     assert len(month.closes) == 30
     assert float(month.closes[-1]) == 99.0
     assert all(c is None for c in month.closes[:-1])
 
 
 # --------------------------------------------------------------- the panel ---
 
-def post_for(ticker, minutes_ago, author, text, source='bluesky', ext=None):
-    """One post carrying one scored mention of `ticker`."""
+def post_for(ticker, minutes_ago, author, text, source='bluesky', ext=None,
+             llm_sentiment=None):
+    """One post carrying one scored mention of `ticker`.
+
+    `llm_sentiment` defaults to None (no verdict yet, the common case);
+    passing 'bullish'/'bearish'/'unclear' lets a test drive the model side of
+    `_tone_of` against a real row instead of a hand-built one.
+    """
     from models import RadarMention, RadarPost
 
     when = NOW - dt.timedelta(minutes=minutes_ago)
     post = RadarPost(
         source=source, external_id=ext or f'{PREFIX}-{author}-{minutes_ago}',
         channel='feed', author=author, created_utc=when, title=None,
         body=text, score=0, num_comments=0,
         url=f'https://example.invalid/{author}/{minutes_ago}',
         simhash=abs(hash(text)) % (2 ** 63), first_seen=when, last_seen=when)
     db.session.add(post)
     db.session.flush()
     db.session.add(RadarMention(
         post_id=post.id, ticker=ticker, confidence='high',
-        lexicon_sentiment=0.4 if 'moon' in text else 0.0))
+        lexicon_sentiment=0.4 if 'moon' in text else 0.0,
+        llm_sentiment=llm_sentiment))
 
 
 @pytest.fixture()
 def panel_ticker(clean):
     from models import RadarMention, RadarPost
 
     RadarMention.query.filter(RadarMention.ticker.like(f'{PREFIX}%')).delete(
         synchronize_session=False)
     RadarPost.query.filter(
         RadarPost.external_id.like(f'{PREFIX}%')).delete(
@@ -264,20 +271,120 @@ def test_the_panel_describes_a_ticker_the_board_filtered_out(clean):
 def test_neutral_is_everything_the_lexicon_did_not_score(panel_ticker):
     """Most mentions carry no sentiment word at all. Folding them into one
     percentage would turn a handful of scored posts into a confident-looking
     reading."""
     b = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW).breakdown
 
     assert b.bullish + b.neutral + b.bearish == b.mentions
     assert b.neutral == 2
 
 
+def test_the_breakdown_counts_real_disagreements_not_just_the_tone_helper(
+        panel_ticker):
+    """`test_the_breakdown_prefers_the_model_verdict_over_the_lexicon` above
+    only drives `_tone_of` directly -- the pure function. Nothing before this
+    test ran the counting LOOP in `breakdown_for` (the thing Task 14 actually
+    built) against real rows with a genuine lexicon/model disagreement:
+    replacing that loop's condition with `if False:` left all 69 tests in
+    this file and test_radar_api.py green (fix-round-1 review, finding I2).
+
+    Three rows, one real disagreement:
+      - 'to the moon' (lexicon bullish) scored 'bearish' by the model: the
+        model outranks and reverses the read -> counted.
+      - 'to the moon' (lexicon bullish) scored 'bullish': they agree -> not
+        counted.
+      - 'still holding' (lexicon carried no directional word) scored
+        'bullish': the lexicon never took a side, so there is nothing to
+        disagree WITH -> not counted, even though the model's tone differs
+        from the row's final tone.
+    """
+    post_for(f'{PREFIX}A', 5, 'frank', 'to the moon',
+             ext=f'{PREFIX}-disagree-reversed', llm_sentiment='bearish')
+    post_for(f'{PREFIX}A', 6, 'grace', 'to the moon',
+             ext=f'{PREFIX}-disagree-agrees', llm_sentiment='bullish')
+    post_for(f'{PREFIX}A', 7, 'heidi', 'still holding',
+             ext=f'{PREFIX}-disagree-no-lexicon-side', llm_sentiment='bullish')
+    db.session.commit()
+
+    b = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW).breakdown
+
+    assert b.disagreements == 1
+
+
+# ------------------------------------------------- pre-split root history ---
+#
+# Before 2026-08-26 every Reddit observation was stored under the bare name
+# `reddit`. This chart's default span is 1Y and buckets are retained forever,
+# so most of what it draws for Reddit is under that older name.
+
+def _old_root_bucket(ticker, days_ago, mentions):
+    """A bucket row exactly as production wrote it before the split."""
+    db.session.add(RadarBucketSource(
+        ticker=ticker,
+        bucket_start=dt.datetime.combine(
+            NOW.date() - dt.timedelta(days=days_ago), dt.time(12, 0)),
+        source='reddit', mention_count=mentions,
+        high_confidence_count=mentions, low_count=0, distinct_authors=6,
+        distinct_text_ratio=0.9, engagement_weighted_count=float(mentions),
+        # The real pre-split stamp, 16 hex characters -- which is also the
+        # column's whole width, so a descriptive placeholder does not fit.
+        status='ok', source_config_version='8106787f1fa72179',
+        expected=1.0, variance=2.0, mention_z=9.9, baseline_days=30))
+
+
+def test_the_chart_still_draws_the_pre_split_reddit_history(clean):
+    """A 1Y span reaches back past the subreddit split.
+
+    Dropping those rows would not draw a gap: `first_watched_day` is
+    satisfied by the days after the split, so the earlier days are marked
+    watched and drawn as zeroes -- an absence rendered as a measurement.
+    """
+    db.session.add(TickerUniverse(
+        symbol=f'{PREFIX}H', name='History Corp', exchange='NASDAQ',
+        first_seen=dt.datetime(2020, 1, 1)))
+    _old_root_bucket(f'{PREFIX}H', days_ago=200, mentions=7)
+    db.session.commit()
+
+    start = NOW.date() - dt.timedelta(days=SPAN - 1)
+    from_dt = dt.datetime.combine(start, dt.time.min)
+    counts = detail.daily_counts([f'{PREFIX}H'], ['reddit'], from_dt, NOW)
+    watched = detail.first_watched_day(['reddit'], from_dt, NOW)
+
+    assert counts[(f'{PREFIX}H', NOW.date() - dt.timedelta(days=200))] == 7
+    assert watched == NOW.date() - dt.timedelta(days=200)
+
+
+def test_the_breakdown_still_shows_one_reddit_row(panel_ticker):
+    """Task 9 changed the POPULATION, not the presentation.
+
+    Splitting the source name is how one sub's feed rollover stops marking
+    every other sub truncated. It is not a decision to put subreddits on the
+    surface -- so the venue table keeps the single pooled `Reddit` row it had
+    before, with one voices count and one share of mentions, and the
+    pre-split root rows pool into it as well. Fragmenting it into eight rows
+    would be its own product call, worth making deliberately rather than
+    inheriting from a storage change.
+    """
+    post_for(f'{PREFIX}A', 40, 'carol', 'wsb says moon',
+             source='reddit:wallstreetbets')
+    post_for(f'{PREFIX}A', 50, 'dave', 'penny says moon',
+             source='reddit:pennystocks')
+    post_for(f'{PREFIX}A', 60, 'erin', 'older reddit view', source='reddit')
+    db.session.commit()
+
+    b = detail_panel.build(f'{PREFIX}A', ['bluesky', 'reddit'], NOW).breakdown
+    venues = {v.source: (v.mentions, v.voices) for v in b.venues}
+
+    assert set(venues) == {'bluesky', 'reddit'}
+    assert venues['reddit'] == (3, 3)
+
+
 @pytest.fixture()
 def panel_live(clean):
     """The same ticker, but anchored to real wall-clock time.
 
     The route reads `now` from the clock, deliberately -- a time parameter on
     a production endpoint is a way to ask the server for a board that never
     existed. So the fixed-NOW fixture above cannot reach it, and the HTTP
     tests get posts placed minutes before the actual present instead.
     """
     from models import RadarMention, RadarPost
@@ -506,30 +613,98 @@ def test_a_slot_before_observation_began_is_unknown_not_zero(clean_intraday):
     mentions."""
     with flask_app.app_context():
         bucket(f'{PREFIX}A', minutes_ago=10, mentions=7)
         db.session.commit()
 
         chart = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D')
 
         assert chart.chatter[0] is None
 
 
+@pytest.fixture()
+def clean_intraday_gap():
+    """Own only the rows used to prove an interior coverage gap."""
+    ticker = 'DTGAP12'
+
+    def wipe():
+        RadarBucketSource.query.filter_by(ticker=ticker).delete(
+            synchronize_session=False)
+        db.session.commit()
+
+    with flask_app.app_context():
+        wipe()
+        yield ticker
+        wipe()
+
+
+def test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet(
+        clean_intraday_gap):
+    """Coverage is per slot, so a resumed daemon cannot fill a gap with zero."""
+    now = dt.datetime(2026, 4, 15, 16, 0, 0)
+    first = dt.datetime(2026, 4, 15, 14, 0, 0)
+    last = dt.datetime(2026, 4, 15, 15, 0, 0)
+    db.session.add_all([
+        RadarBucketSource(
+            ticker=clean_intraday_gap, bucket_start=first, source='bluesky',
+            mention_count=3, high_confidence_count=3, low_count=0,
+            distinct_authors=3, distinct_text_ratio=1.0,
+            engagement_weighted_count=3.0, status='ok',
+            source_config_version=source_config_version()),
+        RadarBucketSource(
+            ticker=clean_intraday_gap, bucket_start=last, source='bluesky',
+            mention_count=0, high_confidence_count=0, low_count=0,
+            distinct_authors=0, distinct_text_ratio=0.0,
+            engagement_weighted_count=0.0, status='truncated',
+            source_config_version=source_config_version()),
+    ])
+    db.session.commit()
+
+    chart = detail.intraday_chart_for(
+        clean_intraday_gap, ['bluesky'], now, '1D')
+    first_index = detail._slot_index(first, chart.start, chart.step_minutes,
+                                     len(chart.chatter))
+    last_index = detail._slot_index(last, chart.start, chart.step_minutes,
+                                    len(chart.chatter))
+
+    assert chart.chatter[first_index] == 3
+    assert chart.chatter[last_index] == 0
+    assert all(value is None for value in chart.chatter[first_index + 1:last_index])
+    assert chart.watched_from == first
+
+
 def test_the_chart_reports_its_own_granularity(clean_intraday):
     """The renderer draws evenly spaced slots and cannot tell minutes from
     days. Without this it would label a 24-hour chart with month names."""
     with flask_app.app_context():
         db.session.commit()
 
         day = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D')
         week = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1W')
 
         assert day.step_minutes == 15
         assert week.step_minutes == 60
 
 
 def test_a_daily_chart_still_reports_a_days_step(clean):
     """Same field on both, so the renderer has one rule rather than a special
     case keyed on the span name."""
     with flask_app.app_context():
         chart = detail.chart_for(f'{PREFIX}A', NOW.date(), 3, {}, {}, None)
 
         assert chart.step_minutes == 1440
+
+
+def test_the_breakdown_prefers_the_model_verdict_over_the_lexicon():
+    """The one surface that draws a tone bar never read the verdicts.
+
+    Production 2026-08-26: 11,789 of 11,794 scored mentions carried a model
+    verdict, at $1.24 a day, and the panel rendered the forty-word lexicon.
+    """
+    from features.radar import detail_panel
+
+    assert detail_panel._tone_of(lexicon=0.8, verdict='bearish') == 'bearish'
+    assert detail_panel._tone_of(lexicon=0.8, verdict=None) == 'bullish'
+    # `unclear` votes neither way AND blocks the lexicon: it means the post
+    # named the ticker without saying anything about it, and that read is
+    # better informed than the word list it overrides.
+    assert detail_panel._tone_of(lexicon=0.8, verdict='unclear') is None
+    assert detail_panel._tone_of(lexicon=None, verdict=None) is None
diff --git a/personal_apps/tests/test_radar_discovery.py b/personal_apps/tests/test_radar_discovery.py
new file mode 100644
index 0000000..11aedaa
--- /dev/null
+++ b/personal_apps/tests/test_radar_discovery.py
@@ -0,0 +1,95 @@
+# personal_apps/tests/test_radar_discovery.py
+"""The discovery script and the daemon share one IP's Reddit budget.
+
+Reddit's anonymous feed budget is one request per window --
+`x-ratelimit-remaining` reads 0.0 after a single call, measured on the VPS
+2026-08-25. This script polls the same `/comments/.rss` feeds at SLEEP=45s
+while the daemon polls one feed per 120s against that same budget. Run
+together, they 429 each other and the daemon's cycle then reports `missing`
+and writes no buckets at all.
+
+These tests exercise the guard at the script boundary -- never by actually
+running a discovery pass. Running discovery for real would hit the network
+and overwrite personal_apps/reddit_candidates.json, which is the user's own
+unrelated work in progress and must not be touched by this suite.
+"""
+from types import SimpleNamespace
+from unittest.mock import Mock, mock_open
+
+import pytest
+
+import scripts.discover_reddit_sources as discovery
+
+
+class _FakeAppContext:
+    def __enter__(self):
+        return self
+
+    def __exit__(self, *exc_info):
+        return False
+
+
+class _FakeApp:
+    """Stands in for the real Flask app so entering it is observable and
+    costs no real database connection."""
+
+    def __init__(self):
+        self.entered = 0
+
+    def app_context(self):
+        self.entered += 1
+        return _FakeAppContext()
+
+
+def test_absent_systemctl_means_not_running_and_never_shells_out(monkeypatch):
+    monkeypatch.setattr('shutil.which', lambda name: None)
+    run = Mock()
+    monkeypatch.setattr('subprocess.run', run)
+
+    assert discovery._daemon_is_running() is False
+    assert run.call_count == 0
+
+
+def test_an_active_daemon_is_detected_via_the_exact_argv(monkeypatch):
+    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/systemctl')
+    run = Mock(return_value=SimpleNamespace(stdout='active\n'))
+    monkeypatch.setattr('subprocess.run', run)
+
+    assert discovery._daemon_is_running() is True
+    run.assert_called_once_with(
+        ['systemctl', 'is-active', 'radar_ingest'],
+        capture_output=True, text=True)
+
+
+def test_main_refuses_before_entering_the_app_context_when_daemon_runs(monkeypatch):
+    fake_app = _FakeApp()
+    monkeypatch.setattr(discovery, 'app', fake_app)
+    monkeypatch.setattr(discovery, '_daemon_is_running', lambda: True)
+
+    errors = []
+    monkeypatch.setattr('sys.stderr', SimpleNamespace(write=errors.append))
+
+    result = discovery.main([])
+
+    assert result == 1
+    assert fake_app.entered == 0
+    joined = ''.join(errors)
+    assert 'systemctl stop radar_ingest' in joined
+    assert '--anyway' in joined
+
+
+def test_anyway_proceeds_past_the_guard_when_daemon_runs(monkeypatch):
+    fake_app = _FakeApp()
+    monkeypatch.setattr(discovery, 'app', fake_app)
+    monkeypatch.setattr(discovery, '_daemon_is_running', lambda: True)
+    monkeypatch.setattr(discovery, 'CANDIDATES', [])
+    monkeypatch.setattr(discovery.universe, 'load_lookup', lambda: {})
+    fake_open = mock_open()
+    monkeypatch.setattr(discovery, 'open', fake_open, raising=False)
+
+    result = discovery.main(['--anyway'])
+
+    assert result in (None, 0)
+    assert fake_app.entered >= 1
+    fake_open.assert_called_once_with(
+        'reddit_candidates.json', 'w', encoding='utf-8')
diff --git a/personal_apps/tests/test_radar_ingest.py b/personal_apps/tests/test_radar_ingest.py
index 8382d8b..5da10a0 100644
--- a/personal_apps/tests/test_radar_ingest.py
+++ b/personal_apps/tests/test_radar_ingest.py
@@ -11,73 +11,78 @@ import datetime as dt
 import pytest
 
 from app import app as flask_app
 from extensions import db
 from models import (RadarBucket, RadarMention, RadarMentionEvent, RadarPost,
                     RadarSourceCursor, TickerUniverse)
 from features.radar import ingest
 from features.radar.sources import FetchResult, RawPost
 
 NOW = dt.datetime(2026, 4, 15, 14, 20, 0)
+TEST_CHANNEL = 'zz_task7_ingest'
+TEST_SOURCES = ('bluesky', 'reddit', 'reddit:wallstreetbets')
+TEST_TICKER = 'ZZG'
 
 
 def _wipe():
     from models import RadarBucketSource
-    RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
+    RadarPost.query.filter(RadarPost.channel == TEST_CHANNEL).delete(
         synchronize_session=False)
-    RadarBucketSource.query.filter(
-        RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
-    RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
+    RadarBucketSource.query.filter_by(ticker=TEST_TICKER).delete(
+        synchronize_session=False)
+    RadarBucket.query.filter_by(ticker=TEST_TICKER).delete(
         synchronize_session=False)
     # roll_up now rebuilds from the journal rather than from one cycle's rows
     # (Task 2), so a ZZG event this suite never cleans up outlives the test
     # that wrote it and inflates every later test's rebuild of the same
     # (ticker, bucket_start) -- caught live: leftover rows from earlier tests
     # in this file made mention_count read 4, 4 and 7 where fresh runs read
     # 1, 0 and 2.
-    RadarMentionEvent.query.filter(
-        RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
-    TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
+    RadarMentionEvent.query.filter_by(ticker=TEST_TICKER).delete(
+        synchronize_session=False)
+    TickerUniverse.query.filter_by(symbol=TEST_TICKER).delete(
         synchronize_session=False)
-    RadarSourceCursor.query.delete(synchronize_session=False)
+    RadarSourceCursor.query.filter(
+        RadarSourceCursor.source.in_(TEST_SOURCES)).delete(
+            synchronize_session=False)
 
 
 @pytest.fixture()
 def seeded(clean_radar):
     with flask_app.app_context():
-        db.session.add(TickerUniverse(symbol='ZZG', name='Zulu Games Corp',
+        db.session.add(TickerUniverse(symbol=TEST_TICKER, name='Zulu Games Corp',
                                       exchange='NYSE',
                                       first_seen=dt.datetime(2026, 1, 1)))
         db.session.commit()
         yield
 
 
 @pytest.fixture()
 def clean_radar():
     with flask_app.app_context():
         _wipe()
         db.session.commit()
         yield
         _wipe()
         db.session.commit()
 
 
 def post(ident='t3_1', body='$ZZG is ripping', score=5, author='u1',
-         minute=10, title=None):
-    return RawPost(source='stocktwits', external_id=ident, channel='testsub',
+         minute=10, title=None, source='bluesky'):
+    return RawPost(source=source, external_id=ident, channel=TEST_CHANNEL,
                    author=author,
                    created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
                    title=title, body=body, score=score, num_comments=0,
                    url='https://example.invalid/%s' % ident)
 
 
-def fetcher_for(result, source='stocktwits'):
+def fetcher_for(result, source='bluesky'):
     def fetcher(since):
         return result
     return {source: fetcher}
 
 
 def test_a_post_becomes_a_mention_and_a_bucket(seeded):
     result = ingest.run_cycle(
         NOW, fetcher_for(FetchResult(posts=[post()], status='ok')))
 
     assert result['posts_new'] == 1
@@ -116,39 +121,56 @@ def test_a_deleted_post_loses_its_text_but_keeps_its_counts(seeded):
         stored = RadarPost.query.filter_by(external_id='t3_1').one()
         assert stored.body == ''
         assert RadarMention.query.filter_by(post_id=stored.id).count() == 1
         assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1
 
 
 def test_a_missing_source_writes_nothing_at_all(seeded):
     result = ingest.run_cycle(
         NOW, fetcher_for(FetchResult(posts=[], status='missing')))
 
-    assert result['per_source'] == {'stocktwits': 'missing'}
+    assert result['per_source'] == {'bluesky': 'missing'}
     assert result['buckets_written'] == 0
     with flask_app.app_context():
-        assert RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).count() == 0
+        assert RadarBucket.query.filter_by(ticker=TEST_TICKER).count() == 0
+
+
+def test_an_empty_healthy_source_stays_ok_without_database_artifacts(seeded):
+    """No work due is current coverage, not a source outage or a zero row."""
+    result = ingest.run_cycle(
+        NOW, fetcher_for(FetchResult(posts=[], status='ok')))
+
+    assert result['per_source'] == {'bluesky': 'ok'}
+    assert result['buckets_written'] == 0
+    with flask_app.app_context():
+        from models import RadarBucketSource
+        assert RadarPost.query.filter_by(channel=TEST_CHANNEL).count() == 0
+        assert RadarMention.query.filter_by(ticker=TEST_TICKER).count() == 0
+        assert RadarBucket.query.filter_by(ticker=TEST_TICKER).count() == 0
+        assert RadarBucketSource.query.filter_by(ticker=TEST_TICKER).count() == 0
+        assert RadarMentionEvent.query.filter_by(ticker=TEST_TICKER).count() == 0
+        assert RadarSourceCursor.query.filter_by(source='bluesky').count() == 0
 
 
 def test_a_truncated_cycle_still_stores_its_mentions(seeded):
     result = ingest.run_cycle(
         NOW, fetcher_for(FetchResult(posts=[post()], status='truncated',
                                      catchup_depth=10)))
 
-    assert result['per_source'] == {'stocktwits': 'truncated'}
-    assert result['catchup_depth'] == {'stocktwits': 10}
+    assert result['per_source'] == {'bluesky': 'truncated'}
+    assert result['catchup_depth'] == {'bluesky': 10}
     with flask_app.app_context():
         bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
         assert bucket.mention_count == 1
         from models import RadarBucketSource
         assert RadarBucketSource.query.filter_by(
-            ticker='ZZG', source='stocktwits').one().status == 'truncated'
+            ticker='ZZG', source='bluesky').one().status == 'truncated'
 
 
 def test_posts_with_no_recognizable_ticker_are_not_stored_at_all(seeded):
     """Bluesky is 144k posts/hour and almost none are about stocks. Storing
     everything and extracting later would be 100 million rows a month to find
     the quarter-million that matter, so extraction runs first and a post that
     mentions nothing is never written."""
     result = ingest.run_cycle(
         NOW,
         fetcher_for(FetchResult(posts=[post(body='market feels weird today')],
@@ -162,108 +184,235 @@ def test_posts_with_no_recognizable_ticker_are_not_stored_at_all(seeded):
 
 
 def test_the_cursor_advances_even_when_nothing_was_stored(seeded):
     """The cursor tracks what was SEEN, not what was KEPT. Inferring it from
     stored rows would rewind every cycle and refetch the same window forever."""
     ingest.run_cycle(
         NOW,
         fetcher_for(FetchResult(posts=[post(body='no tickers here', minute=12)],
                                 status='ok')))
     with flask_app.app_context():
-        cursor = RadarSourceCursor.query.filter_by(source='stocktwits').one()
+        cursor = RadarSourceCursor.query.filter_by(source='bluesky').one()
         assert cursor.cursor_utc == dt.datetime(2026, 4, 15, 14, 12, 0)
 
 
 def test_since_advances_to_the_newest_post_seen(seeded):
     captured = {}
 
     def fetcher(since):
         captured['since'] = since
         return FetchResult(posts=[post(minute=10)], status='ok')
 
-    ingest.run_cycle(NOW, {'stocktwits': fetcher})
-    ingest.run_cycle(NOW, {'stocktwits': fetcher})
+    ingest.run_cycle(NOW, {'bluesky': fetcher})
+    ingest.run_cycle(NOW, {'bluesky': fetcher})
     assert captured['since'] == dt.datetime(2026, 4, 15, 14, 10, 0)
 
 
 def test_two_sources_ingest_in_one_cycle(seeded):
-    def st(since):
-        return FetchResult(posts=[post(ident='st1', body='$ZZG up')], status='ok')
+    def rd(since):
+        return FetchResult(
+            posts=[post(ident='st1', body='$ZZG up', source='reddit')],
+            status='ok')
 
     def bs(since):
         p = post(ident='bs1', body='$ZZG up')
         p.source = 'bluesky'
         return FetchResult(posts=[p], status='ok')
 
-    result = ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
+    result = ingest.run_cycle(NOW, {'reddit': rd, 'bluesky': bs})
     assert result['posts_new'] == 2
-    assert result['per_source'] == {'stocktwits': 'ok', 'bluesky': 'ok'}
+    assert result['per_source'] == {'reddit': 'ok', 'bluesky': 'ok'}
     with flask_app.app_context():
         from models import RadarBucketSource
         sources = {r.source for r in
                    RadarBucketSource.query.filter_by(ticker='ZZG').all()}
-        assert sources == {'stocktwits', 'bluesky'}
+        assert sources == {'reddit', 'bluesky'}
+
+
+def test_reddit_subreddits_write_only_their_own_status_rows(seeded):
+    """One rolled-over feed must not mark a quieter subreddit truncated."""
+    wallstreetbets = post(
+        ident='task9-wsb', body='$ZZG from wsb', author='task9-wsb',
+        source='reddit:wallstreetbets')
+    pennystocks = post(
+        ident='task9-penny', body='$ZZG from pennies', author='task9-penny',
+        source='reddit:pennystocks')
+    result = ingest.run_cycle(
+        NOW,
+        fetcher_for(FetchResult(
+            posts=[wallstreetbets, pennystocks], status='truncated',
+            per_source_status={
+                'reddit:wallstreetbets': 'truncated',
+                'reddit:pennystocks': 'ok',
+            }), source='reddit'))
+
+    assert result['per_source'] == {
+        'reddit:wallstreetbets': 'truncated',
+        'reddit:pennystocks': 'ok',
+    }
+    with flask_app.app_context():
+        from models import RadarBucketSource
+        rows = {row.source: row.status for row in
+                RadarBucketSource.query.filter_by(ticker=TEST_TICKER).all()}
+        assert rows == {
+            'reddit:wallstreetbets': 'truncated',
+            'reddit:pennystocks': 'ok',
+        }
+        assert RadarBucketSource.query.filter_by(
+            ticker=TEST_TICKER, source='reddit').count() == 0
+
+
+def test_a_successful_subreddit_survives_a_missing_aggregate_status(seeded):
+    """A later refusal cannot discard comments already fetched this cycle."""
+    successful = post(
+        ident='task9-partial', body='$ZZG survived', author='task9-partial',
+        source='reddit:pennystocks')
+    result = ingest.run_cycle(
+        NOW,
+        fetcher_for(FetchResult(
+            posts=[successful], status='missing',
+            per_source_status={
+                'reddit:pennystocks': 'ok',
+                'reddit:wallstreetbets': 'missing',
+            }), source='reddit'))
+
+    assert result['posts_new'] == 1
+    assert result['mentions'] == 1
+    with flask_app.app_context():
+        from models import RadarBucketSource
+        rows = {row.source: row.status for row in
+                RadarBucketSource.query.filter_by(ticker=TEST_TICKER).all()}
+        assert rows == {'reddit:pennystocks': 'ok'}
+        assert RadarPost.query.filter_by(external_id='task9-partial').count() == 1
+
+
+def test_a_source_that_observed_nothing_writes_no_row_at_all(seeded):
+    """An explicitly empty per-source map records NOTHING for that source.
+
+    Reddit's "nothing due" branch is the common path -- six of eight cycles
+    have no subreddit due -- and on it Reddit is not read at all. That is an
+    absence: no fetch was made, so there is no observation. It is not an `ok`
+    zero (a bucket child claiming coverage nothing produced, which also
+    inflates RadarBucket.sources_ok) and it is not a `missing` (which means we
+    tried and failed).
+
+    So the map is empty rather than absent, and ingest must tell the two
+    apart: `None` means "this fetcher does not report per-source status" and
+    falls back to the aggregate verdict; `{}` means "no source was observed"
+    and must not.
+    """
+    fetchers = fetcher_for(FetchResult(
+        posts=[post(ident='task9-quiet', body='$ZZG moving',
+                    author='task9-quiet')], status='ok'))
+    fetchers.update(fetcher_for(
+        FetchResult(posts=[], status='ok', per_source_status={}),
+        source='reddit'))
+
+    result = ingest.run_cycle(NOW, fetchers)
+
+    assert result['per_source'] == {'bluesky': 'ok'}
+    with flask_app.app_context():
+        from models import RadarBucket, RadarBucketSource
+        rows = {row.source: (row.status, row.mention_count) for row in
+                RadarBucketSource.query.filter_by(ticker=TEST_TICKER).all()}
+        assert rows == {'bluesky': ('ok', 1)}
+        assert RadarBucketSource.query.filter_by(
+            ticker=TEST_TICKER, source='reddit').count() == 0
+        # And the bucket does not claim two sources were ok.
+        assert {b.sources_ok for b in
+                RadarBucket.query.filter_by(ticker=TEST_TICKER).all()} == {1}
 
 
 def test_one_source_failing_does_not_stop_the_other(seeded):
     """The entire reason status is per source. A dead Bluesky must not cost a
-    healthy StockTwits cycle, and must not write a zero for itself."""
-    def st(since):
-        return FetchResult(posts=[post(ident='st1', body='$ZZG up')], status='ok')
+    healthy Reddit cycle, and must not write a zero for itself."""
+    def rd(since):
+        return FetchResult(
+            posts=[post(ident='st1', body='$ZZG up', source='reddit')],
+            status='ok')
 
     def bs(since):
         return FetchResult(posts=[], status='missing')
 
-    result = ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
-    assert result['per_source'] == {'stocktwits': 'ok', 'bluesky': 'missing'}
+    result = ingest.run_cycle(NOW, {'reddit': rd, 'bluesky': bs})
+    assert result['per_source'] == {'reddit': 'ok', 'bluesky': 'missing'}
     with flask_app.app_context():
         from models import RadarBucketSource
         rows = {r.source: r.status for r in
                 RadarBucketSource.query.filter_by(ticker='ZZG').all()}
-        assert rows == {'stocktwits': 'ok'}
+        assert rows == {'reddit': 'ok'}
 
 
 def test_each_source_keeps_its_own_cursor(seeded):
     """One source catching up must not drag the others back over ground they
     already covered."""
-    def st(since):
-        return FetchResult(posts=[post(ident='st1', body='$ZZG', minute=10)],
-                           status='ok')
+    def rd(since):
+        return FetchResult(
+            posts=[post(ident='st1', body='$ZZG', minute=10,
+                        source='reddit:wallstreetbets')],
+            status='ok')
 
     def bs(since):
         p = post(ident='bs1', body='$ZZG', minute=18)
         p.source = 'bluesky'
         return FetchResult(posts=[p], status='ok')
 
-    ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
+    ingest.run_cycle(NOW, {'reddit': rd, 'bluesky': bs})
     with flask_app.app_context():
         cursors = {c.source: c.cursor_utc for c in RadarSourceCursor.query.all()}
-    assert cursors['stocktwits'] == dt.datetime(2026, 4, 15, 14, 10, 0)
+    assert cursors['reddit'] == dt.datetime(2026, 4, 15, 14, 10, 0)
     assert cursors['bluesky'] == dt.datetime(2026, 4, 15, 14, 18, 0)
+    assert 'reddit:wallstreetbets' not in cursors
 
 
 def test_the_same_post_twice_in_one_batch_is_stored_once(seeded):
     """A StockTwits message tagged $ZZG and $OTHER is returned by both symbol
     streams, so one cycle sees the same external_id twice. Found in live data,
     not in tests -- every fixture until now used distinct ids."""
     duplicate = [post(ident='dup1', body='$ZZG and more'),
                  post(ident='dup1', body='$ZZG and more')]
     result = ingest.run_cycle(
         NOW, fetcher_for(FetchResult(posts=duplicate, status='ok')))
 
     assert result['posts_new'] == 1
     assert result['mentions'] == 1
     with flask_app.app_context():
         assert RadarPost.query.filter_by(external_id='dup1').count() == 1
         assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1
 
 
+def test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement(
+        seeded, monkeypatch):
+    """One identity means one extraction decision, even when it appears twice."""
+    calls = []
+    extract = ingest._extract_for
+
+    def counted(raw, lookup):
+        calls.append(raw.external_id)
+        return extract(raw, lookup)
+
+    monkeypatch.setattr(ingest, '_extract_for', counted)
+    duplicate = [post(ident='dup-extract', score=5),
+                 post(ident='dup-extract', score=900)]
+
+    result = ingest.run_cycle(
+        NOW, fetcher_for(FetchResult(posts=duplicate, status='ok')))
+
+    assert calls == ['dup-extract']
+    assert result['posts_new'] == 1
+    assert result['mentions'] == 1
+    with flask_app.app_context():
+        stored = RadarPost.query.filter_by(external_id='dup-extract').one()
+        assert stored.score == 900
+        assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1
+
+
 def test_a_low_only_post_is_counted_but_never_stored(seeded):
     """ROM in "dinosaur fossils at the ROM" is a real ticker and a real bare
     match, and about 12000 an hour of its kind cross the firehose. It is
     counted so the extractor's false-positive rate stays measurable, but the
     text is never kept -- seven million rows a month for posts the leaderboard
     can never surface."""
     result = ingest.run_cycle(
         NOW,
         fetcher_for(FetchResult(posts=[post(ident='low1', body='ZZG rumours')],
                                 status='ok')))
@@ -294,59 +443,77 @@ def test_a_low_is_still_promoted_by_a_stored_high(seeded):
 
 def test_an_unexpected_source_error_does_not_kill_the_cycle(seeded):
     """A missing dependency once took down a whole live cycle -- StockTwits and
     4chan included -- because ModuleNotFoundError is not the exception type the
     Bluesky module declares. Sources fail in ways they never anticipated, so
     the isolation has to be broad."""
     def exploding(since):
         raise ModuleNotFoundError("No module named 'websockets'")
 
     def healthy(since):
-        return FetchResult(posts=[post(ident='ok1', body='$ZZG up')], status='ok')
+        return FetchResult(
+            posts=[post(ident='ok1', body='$ZZG up', source='reddit')],
+            status='ok')
 
-    result = ingest.run_cycle(NOW, {'bluesky': exploding, 'stocktwits': healthy})
+    result = ingest.run_cycle(NOW, {'bluesky': exploding, 'reddit': healthy})
 
-    assert result['per_source'] == {'bluesky': 'missing', 'stocktwits': 'ok'}
+    assert result['per_source'] == {'bluesky': 'missing', 'reddit': 'ok'}
     assert result['mentions'] == 1
     with flask_app.app_context():
         from models import RadarBucketSource
         rows = {r.source for r in RadarBucketSource.query.filter_by(ticker='ZZG')}
-        assert rows == {'stocktwits'}   # no bluesky row, and no zero
+        assert rows == {'reddit'}   # no bluesky row, and no zero
+
+
+def test_a_failed_fetch_reports_no_catchup_depth(seeded):
+    """Depth zero says the source reached back nowhere; failure reached nothing."""
+    def explode(since):
+        raise RuntimeError('nope')
+
+    summary = ingest.run_cycle(NOW, {'bluesky': explode})
+
+    assert summary['per_source']['bluesky'] == 'missing'
+    assert summary['catchup_depth']['bluesky'] is None
 
 
 def test_a_coin_collision_is_dropped_on_a_general_source(seeded, monkeypatch):
     """$BCH on Bluesky means Bitcoin Cash, not Banco de Chile.
 
     ZZG stands in for a coin-shaped symbol so the test does not depend on
     which real tickers happen to collide this year.
     """
     from features.radar import config
     monkeypatch.setattr(config, 'COIN_COLLISION_SYMBOLS', frozenset({'ZZG'}))
 
     p = post(ident='bs_coin', body='$ZZG pumping')
     p.source = 'bluesky'
     result = ingest.run_cycle(
         NOW, {'bluesky': lambda s: FetchResult(posts=[p], status='ok')})
     assert result['mentions'] == 0
 
 
-def test_the_same_symbol_still_counts_on_a_finance_source(seeded, monkeypatch):
-    """On StockTwits the population is discussing equities, so the company
-    reading is the right one."""
-    from features.radar import config
-    monkeypatch.setattr(config, 'COIN_COLLISION_SYMBOLS', frozenset({'ZZG'}))
+def test_a_source_can_opt_into_reading_coin_symbols_as_companies(monkeypatch):
+    """The extension point, kept alive with no live source using it.
 
-    p = post(ident='st_coin', body='$ZZG pumping')
-    p.source = 'stocktwits'
-    result = ingest.run_cycle(
-        NOW, {'stocktwits': lambda s: FetchResult(posts=[p], status='ok')})
-    assert result['mentions'] == 1
+    StockTwits was the only population where $LINK meant Interlink. It is
+    retired; this pins that a future finance-native source can still opt in,
+    rather than the map quietly becoming a constant nobody can override.
+    """
+    from features.radar import config, ingest
+
+    monkeypatch.setattr(config, 'COIN_COLLISION_SYMBOLS', frozenset({'LINK'}))
+    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'bluesky', True)
+    lookup = {'LINK': {'name': 'Interlink Electronics Inc.', 'exchange': 'NASDAQ',
+                       'distinctive': set()}}
+    raw = post(ident='coin-link', body='$LINK is breaking out', source='bluesky')
+
+    assert ingest._extract_for(raw, lookup) == [('LINK', 'high')]
 
 
 # --- Automated feeds, wired in 2026-08-25 -----------------------------------
 #
 # config.looks_like_bot_feed (was looks_like_exchange_bot) had been defined
 # since 2026-08-22 and hashed into source_config_version, and called by
 # NOTHING. The pattern was written and then never reached the pipeline, which
 # is a defect shaped like an absence: the board looked normal, it just counted
 # machines.
 
@@ -374,10 +541,48 @@ def test_a_person_naming_the_same_tickers_still_counts():
     """Teeth. If the filter swallowed the tickers rather than the feed, the
     assertion above would pass while Barrick became untrackable."""
     from features.radar import ingest, universe
 
     lookup = universe.annotate_distinctive({
         'GOLD': {'name': 'Barrick Mining Corporation', 'exchange': 'NYSE'},
     })
     raw = post(body='$GOLD breaking out, miners finally waking up')
 
     assert ingest._extract_for(raw, lookup) == [('GOLD', 'high')]
+
+
+def test_a_single_letter_cashtag_is_refused_on_a_general_network():
+    """`$M` on Bluesky is money shorthand, not Macy's.
+
+    Measured on live Bluesky: 119 of 3302 cashtag matches were single letters
+    and essentially all were prose -- "Tax @60% for over a $M", "make $B's".
+    config.SINGLE_LETTER_CASHTAGS has said so since it was written; nothing
+    passed it to the extractor until now, and 353 such mentions reached the
+    production corpus, 3.0% of the whole high-confidence set.
+    """
+    from features.radar import ingest
+
+    lookup = {'B': {'name': 'Barnes Group Inc.', 'exchange': 'NYSE',
+                    'distinctive': set()}}
+    general = post(ident='zz-single', body='make $B and youre set',
+                   source='bluesky')
+
+    assert ingest._extract_for(general, lookup) == []
+
+
+def test_a_source_can_opt_into_single_letter_cashtags(monkeypatch):
+    """The extension point, kept alive with no live source using it.
+
+    StockTwits was the only population where a bare `$B` was worth reading as
+    Barnes Group rather than money shorthand. It is retired; this pins that a
+    future finance-native source can still opt in, rather than the map
+    quietly becoming a constant nobody can override.
+    """
+    from features.radar import config, ingest
+
+    monkeypatch.setitem(config.SINGLE_LETTER_CASHTAGS, 'bluesky', True)
+    lookup = {'B': {'name': 'Barnes Group Inc.', 'exchange': 'NYSE',
+                    'distinctive': set()}}
+    finance = post(ident='zz-single-2', body='make $B and youre set',
+                   source='bluesky')
+
+    assert ingest._extract_for(finance, lookup) == [('B', 'high')]
diff --git a/personal_apps/tests/test_radar_journal.py b/personal_apps/tests/test_radar_journal.py
index 4d1fd30..b9d2db9 100644
--- a/personal_apps/tests/test_radar_journal.py
+++ b/personal_apps/tests/test_radar_journal.py
@@ -5,64 +5,96 @@ roll_up used to recompute a bucket from one cycle's in-memory mentions and
 overwrite the result. Every source advances a cursor, so each cycle carries
 only a slice, and a bucket touched by several cycles kept the last slice.
 Measured in production 2026-08-26: 43% of the 10+ mention buckets lost.
 """
 import datetime as dt
 
 import pytest
 
 from app import app as flask_app
 from extensions import db
-from models import RadarMentionEvent
+from models import RadarMention, RadarMentionEvent, RadarPost
 
 
 @pytest.fixture()
 def clean_events():
     with flask_app.app_context():
         RadarMentionEvent.query.filter(
             RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
         db.session.commit()
         yield
         RadarMentionEvent.query.filter(
             RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
         db.session.commit()
 
 
+@pytest.fixture()
+def clean_retained_mentions():
+    def clear():
+        ids = [post.id for post in RadarPost.query.filter(
+            RadarPost.external_id.like('zz-bootstrap-%')).all()]
+        if ids:
+            RadarMention.query.filter(RadarMention.post_id.in_(ids)).delete(
+                synchronize_session=False)
+            RadarPost.query.filter(RadarPost.id.in_(ids)).delete(
+                synchronize_session=False)
+        db.session.commit()
+
+    with flask_app.app_context():
+        clear()
+        yield
+        clear()
+
+
 @pytest.fixture()
 def clean_buckets():
     from models import RadarBucket, RadarBucketSource
     with flask_app.app_context():
         for model in (RadarBucketSource, RadarBucket):
             model.query.filter(model.ticker.like('ZZ%')).delete(
                 synchronize_session=False)
         db.session.commit()
         yield
         for model in (RadarBucketSource, RadarBucket):
             model.query.filter(model.ticker.like('ZZ%')).delete(
                 synchronize_session=False)
         db.session.commit()
 
 
 _ALL_OK = {'bluesky': 'ok'}
 
 
 def _row(external_id, ticker='ZZA', minute=3, source='bluesky', author='u1',
          simhash=111, confidence='high', sentiment=0.5, engagement=10.0,
-         channel='c'):
+         channel='c', created_utc=None):
     from features.radar import buckets
     return buckets.MentionRow(
         ticker=ticker, external_id=external_id,
-        created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
+        created_utc=created_utc or dt.datetime(2026, 4, 15, 14, minute, 0),
         source=source, channel=channel, author=author, simhash=simhash,
         confidence=confidence, sentiment=sentiment, engagement=engagement)
 
 
+def _retained_post(external_id, ticker, confidence, created_utc, *, author,
+                   simhash, sentiment, score, comments):
+    post = RadarPost(
+        source='bluesky', external_id=external_id, channel='radar-test',
+        author=author, created_utc=created_utc, title='title', body='body',
+        score=score, num_comments=comments, url='https://example.test/post',
+        simhash=simhash, first_seen=created_utc, last_seen=created_utc)
+    post.mentions.append(RadarMention(
+        ticker=ticker, confidence=confidence,
+        lexicon_sentiment=sentiment))
+    db.session.add(post)
+    return post
+
+
 def test_a_second_poll_inside_one_bucket_does_not_erase_the_first(clean_buckets,
                                                                   clean_events):
     """The production shape, which the old regression test never modelled.
 
     tests/test_radar_buckets.py fed its second roll_up call a SUPERSET of the
     first, modelling a full re-read of the window. No source does that: every
     one advances a cursor, so cycle N+1 carries a DISJOINT tail. The assertion
     encoded the assumption instead of testing it, and passed for months while
     production lost 43% of its busiest buckets.
     """
@@ -175,53 +207,146 @@ def test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions(
 
 
 def test_a_down_sources_mentions_never_reach_the_journal(clean_buckets, clean_events):
     """The corollary of 'an absence is never a zero' (buckets.py's module
     docstring): a fabricated count from a source that was actually down would
     poison that source's own baseline the moment it recovers.
 
     roll_up must journal only `usable` (this cycle's rows filtered to
     countable sources), never `rows` (everything handed to it, missing
     sources included). Reviewer's mutation swapped one for the other: a cycle
-    reporting `{'bluesky': 'ok', 'stocktwits': 'missing'}` still journalled
-    the stocktwits row, and the NEXT cycle -- once stocktwits reports 'ok'
+    reporting `{'bluesky': 'ok', 'reddit': 'missing'}` still journalled
+    the reddit row, and the NEXT cycle -- once reddit reports 'ok'
     again -- rebuilds from the journal and folds that leaked row into a brand
-    new RadarBucketSource stamped status='ok', exactly as if stocktwits had
+    new RadarBucketSource stamped status='ok', exactly as if reddit had
     been up the whole time.
     """
     from features.radar import buckets
     from models import RadarBucketSource
 
     start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
 
-    # Cycle 1: stocktwits is down but still handed roll_up a row (a fetch
+    # Cycle 1: reddit is down but still handed roll_up a row (a fetch
     # that parsed a post before the failure was detected, or a source whose
     # cursor moved before its client raised). bluesky is up, so `countable`
     # is non-empty and roll_up does not return 0 before reaching journal.record.
     buckets.roll_up(
-        [_row(external_id='zz-down', source='stocktwits', author='u1',
+        [_row(external_id='zz-down', source='reddit', author='u1',
              simhash=1, minute=3),
          _row(external_id='zz-a', source='bluesky', author='u2',
              simhash=2, minute=3)],
-        {'bluesky': 'ok', 'stocktwits': 'missing'}, start)
+        {'bluesky': 'ok', 'reddit': 'missing'}, start)
 
-    # Cycle 2: stocktwits has recovered and contributes nothing new itself.
+    # Cycle 2: reddit has recovered and contributes nothing new itself.
     # bluesky activity in the same window still forces a full rebuild of it,
     # which re-reads everything the journal is holding for (ZZA, 14:00).
     buckets.roll_up(
         [_row(external_id='zz-b', source='bluesky', author='u3',
              simhash=3, minute=5)],
-        {'bluesky': 'ok', 'stocktwits': 'ok'}, start)
+        {'bluesky': 'ok', 'reddit': 'ok'}, start)
+
+    reddit_row = RadarBucketSource.query.filter_by(
+        ticker='ZZA', source='reddit').one()
+    assert reddit_row.mention_count == 0
+
+
+def test_bootstrap_recovers_retained_mentions_with_field_fidelity(
+        clean_events, clean_retained_mentions):
+    """bootstrap_from_mentions carries no ticker filter -- production has to
+    recover EVERY retained decision in the window, not one ticker's -- so
+    unlike the rest of this file it cannot lean on ZZ-namespacing alone for
+    isolation. The dev database seeds 1432 real RadarPost x RadarMention rows
+    dated before this test's 2027-06-01 window. This future window stays clear
+    of all real and seeded rows while preserving the same bootstrap behaviour.
+    """
+    from features.radar import journal
+
+    since = dt.datetime(2027, 6, 1, 13, 0, 0)
+    _retained_post('zz-bootstrap-high', 'ZZH', 'high',
+                   dt.datetime(2027, 6, 1, 14, 2, 0), author='high-author',
+                   simhash=101, sentiment=0.75, score=7, comments=4)
+    _retained_post('zz-bootstrap-low', 'ZZL', 'low',
+                   dt.datetime(2027, 6, 1, 14, 7, 0), author='low-author',
+                   simhash=202, sentiment=-0.25, score=-2, comments=5)
+    db.session.commit()
+
+    assert journal.bootstrap_from_mentions(since) == 2
+    assert journal.bootstrap_from_mentions(since) == 2
+
+    events = {event.ticker: event for event in
+              RadarMentionEvent.query.filter(
+                  RadarMentionEvent.ticker.in_(['ZZH', 'ZZL'])).all()}
+    assert set(events) == {'ZZH', 'ZZL'}
+    assert RadarMentionEvent.query.filter(
+        RadarMentionEvent.ticker.in_(['ZZH', 'ZZL'])).count() == 2
+    high = events['ZZH']
+    assert (high.source, high.external_id, high.channel, high.author) == (
+        'bluesky', 'zz-bootstrap-high', 'radar-test', 'high-author')
+    assert high.created_utc == dt.datetime(2027, 6, 1, 14, 2, 0)
+    assert high.bucket_start == dt.datetime(2027, 6, 1, 14, 0, 0)
+    assert (high.simhash, high.confidence, high.sentiment, high.engagement) == (
+        101, 'high', 0.75, 11.0)
+    low = events['ZZL']
+    assert (low.confidence, low.sentiment, low.engagement) == ('low', -0.25, 3.0)
+
+
+def test_deploy_bootstrap_preserves_the_complete_open_bucket(
+        clean_buckets, clean_events, clean_retained_mentions):
+    """Same real-data constraint as the fidelity test above:
+    _prepare_rollup_generation's bootstrap call and its legacy-evidence check
+    both scan unbounded by ticker, so this test uses a 2027-06-01 window,
+    beyond real and seeded rows, instead of this file's usual 2026-04-15.
+    """
+    import run_radar_ingest as daemon
+    from features.radar import buckets
+    from features.radar.config import source_config_version
+    from models import RadarBucket, RadarBucketSource
+
+    pre_deploy = dt.datetime(2027, 6, 1, 14, 2, 0)
+    post_deploy = dt.datetime(2027, 6, 1, 14, 9, 0)
+    start = {dt.datetime(2027, 6, 1, 14, 0, 0)}
+    before = _row('zz-bootstrap-pre', author='predeploy', simhash=301,
+                 created_utc=pre_deploy)
+    buckets.roll_up([before], _ALL_OK, start)
+    RadarMentionEvent.query.filter_by(
+        source='bluesky', external_id='zz-bootstrap-pre', ticker='ZZA').delete()
+    _retained_post('zz-bootstrap-pre', 'ZZA', 'high', before.created_utc,
+                   author=before.author, simhash=before.simhash,
+                   sentiment=before.sentiment, score=6, comments=4)
+    source = RadarBucketSource.query.filter_by(
+        ticker='ZZA', source='bluesky').one()
+    source.source_config_version = 'old-generation'
+    source.expected = 1.0
+    source.variance = 2.0
+    source.mention_z = 4.2
+    source.baseline_days = 9
+    db.session.commit()
+
+    recovered, invalidated = daemon._prepare_rollup_generation(
+        dt.datetime(2027, 6, 1, 16, 0, 0))
+    buckets.roll_up([
+        _row('zz-bootstrap-post', author='postdeploy', simhash=302,
+            created_utc=post_deploy),
+    ], _ALL_OK, start)
 
-    stocktwits_row = RadarBucketSource.query.filter_by(
-        ticker='ZZA', source='stocktwits').one()
-    assert stocktwits_row.mention_count == 0
+    db.session.expire_all()
+    source = RadarBucketSource.query.filter_by(
+        ticker='ZZA', source='bluesky').one()
+    assert recovered == 1
+    assert invalidated == 1
+    assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 2
+    assert source.mention_count == 2
+    assert source.source_config_version == source_config_version()
+    assert source.expected is None
+    assert source.variance is None
+    assert source.mention_z is None
+    assert source.baseline_days is None
 
 
 def test_the_table_accepts_one_event(clean_events):
     db.session.add(RadarMentionEvent(
         source='bluesky', external_id='zz-1', ticker='ZZA', channel='c',
         created_utc=dt.datetime(2026, 4, 15, 14, 3, 0),
         bucket_start=dt.datetime(2026, 4, 15, 14, 0, 0),
         author='u1', simhash=111, confidence='high',
         sentiment=0.5, engagement=10.0))
     db.session.commit()
diff --git a/personal_apps/tests/test_radar_leaderboard.py b/personal_apps/tests/test_radar_leaderboard.py
index ab16052..41209fe 100644
--- a/personal_apps/tests/test_radar_leaderboard.py
+++ b/personal_apps/tests/test_radar_leaderboard.py
@@ -189,21 +189,40 @@ def test_a_ticker_with_no_quote_still_appears_without_divergence(board):
     db.session.commit()
     row = build_rows(['bluesky'], NOW)[0]
     assert row.divergence is None
     assert row.price is None
 
 
 def test_a_thin_baseline_is_marked_provisional(board):
     universe_row('LBH')
     scored('LBH', baseline_days=3)
     db.session.commit()
-    assert 'provisional' in build_rows(['bluesky'], NOW)[0].marks
+    row = build_rows(['bluesky'], NOW)[0]
+    assert 'provisional' in row.marks
+    # A ticker with genuine multi-day history is not "warming up" -- that
+    # word is reserved for a baseline thinner than a day.
+    assert 'warming-up' not in row.marks
+
+
+def test_a_baseline_under_a_day_is_marked_warming_up_not_provisional(board):
+    """Two different facts wear the same badge otherwise: a NEW ticker has
+    thin history of its own, but a config-version change gives EVERY ticker
+    on the board under a day of history at once. Production: baseline_days
+    truncated to 0 on 147,228 of 147,429 scored Bluesky rows, which fired
+    `provisional` on the whole board -- a mark that fires on every row is not
+    a mark."""
+    universe_row('LBW')
+    scored('LBW', baseline_days=0.5)
+    db.session.commit()
+    row = build_rows(['bluesky'], NOW)[0]
+    assert 'warming-up' in row.marks
+    assert 'provisional' not in row.marks
 
 
 def test_a_truncated_source_is_marked_partial(board):
     universe_row('LBI')
     scored('LBI', status='truncated')
     db.session.commit()
     assert 'partial' in build_rows(['bluesky'], NOW)[0].marks
 
 
 def test_segment_filtering(board):
@@ -291,20 +310,46 @@ def test_authors_are_counted_across_the_window_not_per_bucket(board):
 def test_the_bucket_maximum_is_the_fallback(board):
     """Once posts age out of retention the authors are gone, and the bucket
     count is all that remains. It undercounts, which can hide a ticker but can
     never invent breadth that was not there."""
     universe_row('LBX')
     scored('LBX', mentions=10, authors=7)
     db.session.commit()
     assert build_rows(['bluesky'], NOW)[0].authors == 7
 
 
+def test_the_pre_split_reddit_voices_still_count(board):
+    """The journal's voice count is raw, so it sees the older root name.
+
+    Distinct authors are people, not baselines: the person who posted under
+    the pre-split `reddit` name and the person who posted under
+    `reddit:wallstreetbets` are the same population. Dropping the older half
+    would undercount breadth for every ticker discussed before 2026-08-26 and
+    could push it below the eligibility floor -- the board reading thinner
+    than the evidence it holds.
+    """
+    from features.radar import journal
+
+    universe_row('LBH')
+    scored('LBH', source='reddit:wallstreetbets', mentions=4, authors=2)
+    _mention('LBH', 'newvoice1', 30, source='reddit:wallstreetbets')
+    _mention('LBH', 'newvoice2', 30, source='reddit:wallstreetbets')
+    _mention('LBH', 'oldvoice1', 45, source='reddit')
+    _mention('LBH', 'oldvoice2', 45, source='reddit')
+    db.session.commit()
+
+    voices = journal.distinct_voices(
+        ['LBH'], ['reddit'], NOW - dt.timedelta(hours=4), NOW, 'author')
+
+    assert voices['LBH'] == 4
+
+
 def test_a_genuinely_concentrated_ticker_is_still_rejected(board):
     """The gate must keep working after the fix. Live data had PH at 14
     mentions from one author -- exactly what it exists to catch."""
     universe_row('LBY')
     scored('LBY', mentions=14, authors=1)
     for index in range(14):
         _mention('LBY', 'onlyvoice', 30)
     db.session.commit()
     assert build_rows(['bluesky'], NOW) == []
 
diff --git a/personal_apps/tests/test_radar_llm_sentiment.py b/personal_apps/tests/test_radar_llm_sentiment.py
index 0b8c4cb..80f78da 100644
--- a/personal_apps/tests/test_radar_llm_sentiment.py
+++ b/personal_apps/tests/test_radar_llm_sentiment.py
@@ -169,23 +169,23 @@ def test_the_post_text_is_delimited_as_data():
 
     sent = client.messages.requests[0]
     prompt = sent['messages'][0]['content']
     assert llm_sentiment.POST_OPEN in prompt and llm_sentiment.POST_CLOSE in prompt
     schema = sent['output_config']['format']['schema']
     enum = schema['properties']['verdicts']['items']['properties']['sentiment']['enum']
     assert set(enum) == set(llm_sentiment.VERDICTS)
 
 
 def test_the_model_is_haiku():
-    """Deliberate, and the one place it is decided. 1335 scored mentions a day
-    at Haiku's rates is about twenty cents; the same pass on an Opus-tier
-    model is not a hobby board's bill."""
+    """Deliberate, and the one place it is decided. Measured 2026-08-25: 344
+    calls and $1.2446 for the day at Haiku's rates; the same pass on an
+    Opus-tier model is not a hobby board's bill."""
     client = FakeClient([answer([(1, 'neutral')])])
 
     llm_sentiment.judge([item('a')], client=client)
 
     assert client.messages.requests[0]['model'] == 'claude-haiku-4-5'
 
 
 def test_no_effort_is_sent_because_haiku_rejects_it():
     """`output_config.effort` is an Opus-tier parameter.
 
diff --git a/personal_apps/tests/test_radar_phrasing.py b/personal_apps/tests/test_radar_phrasing.py
index a9957c3..ea7e9bf 100644
--- a/personal_apps/tests/test_radar_phrasing.py
+++ b/personal_apps/tests/test_radar_phrasing.py
@@ -4,34 +4,42 @@
 The live board's failure was not that the numbers were wrong. It was that the
 biggest number on the page belonged to the row that scored nothing, and
 nothing said why. Michi's words on 2026-08-23: "i have no real idea why and
 what is worth looking at."
 
 So the wording IS the feature, and these pin it.
 """
 import dataclasses
 
 from features.radar import phrasing
+from features.radar.config import source_root
 
 
 @dataclasses.dataclass
 class FakeRow:
     ticker: str = 'ZZZ'
     mentions: int = 40
     expected: float = 1.0
     authors: int = 11
     sources: tuple = ('bluesky', 'fourchan')
     price_move: float | None = 0.182
     price_status: str = 'ok'
-    baseline_days: int | None = 30
+    baseline_days: float | None = 30
     mention_z: float | None = 4.1
 
+    @property
+    def venues(self):
+        """Derived rather than a field, so the fake cannot claim a breadth
+        its own source list does not support. One venue per ROOT: two
+        subreddits are one venue, which is what the real Row.venues counts."""
+        return len({source_root(name) for name in self.sources})
+
 
 def kinds(clauses):
     return [c.kind for c in clauses]
 
 
 def text(clauses):
     return ' '.join(c.text for c in clauses)
 
 
 def test_a_measurable_row_says_how_unusual_how_broad_and_what_price_did():
@@ -160,20 +168,48 @@ def test_the_read_names_its_own_weak_baseline():
 
 
 def test_a_full_baseline_earns_no_caveat():
     clauses = phrasing.read_clauses(
         FakeDetail(), mentions=284, expected=7.0, voices=11,
         session='regular', baseline_days=30)
 
     assert not any('baseline' in c.text for c in clauses)
 
 
+def test_a_fractional_baseline_reads_as_words_not_a_raw_float():
+    """Task 16 made `baseline_days` a fraction of a day, not a truncated int.
+    An hour-old baseline is `0.041666666666666664` -- interpolated straight
+    into the sentence, that read "The baseline is 0.041666666666666664 days
+    old", which is exactly the population 'warming-up' exists to describe
+    correctly. The sentence must not leak the float."""
+    clauses = phrasing.read_clauses(
+        FakeDetail(), mentions=284, expected=7.0, voices=11,
+        session='regular', baseline_days=1 / 24)
+
+    warn = next(c for c in clauses if c.kind == 'warn' and 'baseline' in c.text)
+    assert warn.text == ('The baseline is under a day old, not 30, so this '
+                         'rests on very little history.')
+
+
+def test_a_multi_day_fractional_baseline_rounds_to_a_whole_day():
+    """A span like 2.7 days must round for display, not truncate (`.days`
+    truncation is the exact bug Task 16 fixed) and must not print the
+    fraction either."""
+    clauses = phrasing.read_clauses(
+        FakeDetail(), mentions=284, expected=7.0, voices=11,
+        session='regular', baseline_days=2.7)
+
+    warn = next(c for c in clauses if c.kind == 'warn' and 'baseline' in c.text)
+    assert '3 days' in warn.text
+    assert '2.7' not in warn.text
+
+
 def test_the_read_does_not_paraphrase_what_people_said():
     """Cut during mockup review. The page cannot summarise content it never
     understood, and the posts are directly below it."""
     joined = ' '.join(c.text for c in phrasing.read_clauses(
         FakeDetail(), mentions=284, expected=7.0, voices=11,
         session='regular')).lower()
 
     for word in ('filing', 'squeeze', 'announced', 'news about'):
         assert word not in joined
 
diff --git a/personal_apps/tests/test_radar_profile.py b/personal_apps/tests/test_radar_profile.py
index 3c06431..c392232 100644
--- a/personal_apps/tests/test_radar_profile.py
+++ b/personal_apps/tests/test_radar_profile.py
@@ -1,120 +1,144 @@
 # personal_apps/tests/test_radar_profile.py
 """What a normal bucket looks like, per source.
 
 Chatter has a strong weekly shape, and comparing 03:00 Sunday against 15:00
 Tuesday as one population makes every weekday afternoon a spike. The profile is
 what removes that shape before anything is called unusual.
 
-Per source, not market-wide: StockTwits follows US market hours, Bluesky is
+Per source, not market-wide: Reddit follows US market hours, Bluesky is
 global and diurnal, /biz/ runs around the clock. One shared profile would tell
 Bluesky to expect silence when half its users are awake.
 """
 import datetime as dt
 
 import pytest
 
 from app import app as flask_app
 from extensions import db
 from models import RadarBucketSource
 from features.radar import profile
+from features.radar.config import source_config_version
 
 MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)      # a Monday, 00:00 UTC
 
 
 @pytest.fixture()
 def buckets():
     with flask_app.app_context():
         RadarBucketSource.query.filter(
             RadarBucketSource.ticker.like('PP%')).delete(synchronize_session=False)
         db.session.commit()
         yield
         RadarBucketSource.query.filter(
             RadarBucketSource.ticker.like('PP%')).delete(synchronize_session=False)
         db.session.commit()
 
 
-def add(source, when, count, ticker='PPA', status='ok'):
+def add(source, when, count, ticker='PPA', status='ok', version=None):
     db.session.add(RadarBucketSource(
         ticker=ticker, bucket_start=when, source=source,
         mention_count=count, high_confidence_count=count, low_count=0,
         distinct_authors=count, distinct_text_ratio=1.0,
-        engagement_weighted_count=float(count), status=status))
+        engagement_weighted_count=float(count), status=status,
+        source_config_version=(version if version is not None
+                               else source_config_version())))
 
 
 def test_bucket_of_week_is_zero_at_monday_midnight():
     assert profile.bucket_of_week(MONDAY) == 0
 
 
 def test_bucket_of_week_advances_every_fifteen_minutes():
     assert profile.bucket_of_week(MONDAY + dt.timedelta(minutes=15)) == 1
     assert profile.bucket_of_week(MONDAY + dt.timedelta(hours=1)) == 4
 
 
 def test_bucket_of_week_wraps_after_a_week():
     assert profile.bucket_of_week(MONDAY + dt.timedelta(days=7)) == 0
     assert profile.bucket_of_week(
         MONDAY + dt.timedelta(days=6, hours=23, minutes=45)) == 671
 
 
 def test_a_profile_sums_to_one(buckets):
     for hour in (2, 14, 20):
-        add('stocktwits', MONDAY + dt.timedelta(hours=hour), count=hour)
+        add('bluesky', MONDAY + dt.timedelta(hours=hour), count=hour)
     db.session.commit()
-    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
+    built = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1),
+                                  source_config_version())
     assert sum(built.values()) == pytest.approx(1.0)
 
 
 def test_busy_buckets_get_a_larger_share(buckets):
-    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
-    add('stocktwits', MONDAY + dt.timedelta(hours=3), count=1)
+    add('bluesky', MONDAY + dt.timedelta(hours=14), count=100)
+    add('bluesky', MONDAY + dt.timedelta(hours=3), count=1)
     db.session.commit()
-    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
+    built = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1),
+                                  source_config_version())
     busy = profile.hour_share(built, MONDAY + dt.timedelta(hours=14))
     quiet = profile.hour_share(built, MONDAY + dt.timedelta(hours=3))
     assert busy > quiet * 10
 
 
 def test_every_bucket_has_a_nonzero_share(buckets):
     """Smoothing is load-bearing. A share of zero makes expected zero, and any
     observation against it is an infinite z -- so one quiet hour in the sample
     window would manufacture a spike there forever after."""
-    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=50)
+    add('bluesky', MONDAY + dt.timedelta(hours=14), count=50)
     db.session.commit()
-    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
+    built = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1),
+                                  source_config_version())
     assert len(built) == 672
     assert all(share > 0 for share in built.values())
 
 
 def test_profiles_are_per_source(buckets):
-    """StockTwits peaks in the US session; a 24/7 source does not. Sharing one
+    """Reddit peaks in the US session; a 24/7 source does not. Sharing one
     profile would read half of Bluesky's normal traffic as unusual."""
-    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
+    add('reddit', MONDAY + dt.timedelta(hours=14), count=100)
     add('bluesky', MONDAY + dt.timedelta(hours=3), count=100)
     db.session.commit()
-    st = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
-    bs = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1))
-    assert profile.hour_share(st, MONDAY + dt.timedelta(hours=14)) > \
+    version = source_config_version()
+    rd = profile.build_profile('reddit', MONDAY + dt.timedelta(days=1),
+                               version)
+    bs = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1), version)
+    assert profile.hour_share(rd, MONDAY + dt.timedelta(hours=14)) > \
         profile.hour_share(bs, MONDAY + dt.timedelta(hours=14))
 
 
 def test_missing_and_truncated_buckets_are_ignored(buckets):
     """A source that was down did not observe a quiet hour. Counting the gap
     would bend the profile towards silence at exactly the wrong times."""
-    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
-    add('stocktwits', MONDAY + dt.timedelta(hours=15), count=0, status='missing')
-    add('stocktwits', MONDAY + dt.timedelta(hours=16), count=5, status='truncated')
+    add('bluesky', MONDAY + dt.timedelta(hours=14), count=100)
+    add('bluesky', MONDAY + dt.timedelta(hours=15), count=0, status='missing')
+    add('bluesky', MONDAY + dt.timedelta(hours=16), count=5, status='truncated')
     db.session.commit()
-    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
+    built = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1),
+                                  source_config_version())
     fifteen = profile.hour_share(built, MONDAY + dt.timedelta(hours=15))
     sixteen = profile.hour_share(built, MONDAY + dt.timedelta(hours=16))
     # Both fall back to the smoothing floor, and are equal because neither
     # contributed an observation.
     assert fifteen == pytest.approx(sixteen)
 
 
 def test_an_empty_history_gives_a_flat_profile(buckets):
     """Day one. Flat means "no idea yet", which is the honest prior and cannot
     on its own make anything look unusual."""
-    built = profile.build_profile('stocktwits', MONDAY)
+    built = profile.build_profile('bluesky', MONDAY, source_config_version())
     assert len(built) == 672
     assert len(set(round(v, 12) for v in built.values())) == 1
+
+
+def test_a_profile_uses_only_its_exact_config_generation(buckets):
+    current = source_config_version()
+    old_slot = MONDAY + dt.timedelta(hours=3)
+    current_slot = MONDAY + dt.timedelta(hours=14)
+    add('bluesky', old_slot, count=10_000, ticker='PPO', version='old-version')
+    add('bluesky', current_slot, count=100, ticker='PPC', version=current)
+    db.session.commit()
+
+    built = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1),
+                                  current)
+
+    assert profile.hour_share(built, current_slot) > \
+        profile.hour_share(built, old_slot) * 10
diff --git a/personal_apps/tests/test_radar_reddit.py b/personal_apps/tests/test_radar_reddit.py
index a2fe0c7..35c7dd8 100644
--- a/personal_apps/tests/test_radar_reddit.py
+++ b/personal_apps/tests/test_radar_reddit.py
@@ -45,33 +45,32 @@ class FakeClient:
 
     def get_feed(self, sub):
         self.asked.append(sub)
         answer = self.feeds[sub]
         if isinstance(answer, Exception):
             raise answer
         return answer
 
 
 def test_a_comment_becomes_a_post_with_its_subreddit_on_it():
-    """The subreddit rides on `channel`, not on `source`.
+    """The subreddit rides on both the stored source name and channel.
 
-    Per-subreddit baselines are not built yet, so which sub a comment came
-    from is only recoverable if it is stored -- and deciding which subs are
-    worth keeping is the entire reason this ships wide.
+    The concrete source is what gives each subreddit its own coverage status;
+    channel remains the original venue label carried by the stored comment.
     """
     client = FakeClient({'pennystocks': feed([entry('t1_aaa', 5)])})
 
     posts, status, _rate = reddit.fetch_one('pennystocks', NOW - dt.timedelta(hours=1), client)
 
     assert len(posts) == 1
     post = posts[0]
-    assert post.source == 'reddit'
+    assert post.source == 'reddit:pennystocks'
     assert post.channel == 'pennystocks'
     assert post.external_id == 't1_aaa'
     assert post.author == '/u/someone'
     assert 'AAPL' in post.body
     assert status == 'ok'
 
 
 def test_html_is_stripped_from_the_body():
     """The extractor reads text. Left as markup, `<b>AAPL</b>` is not a
     word-boundary match and the mention is silently lost."""
@@ -146,20 +145,22 @@ def test_a_throttle_stops_the_cycle_instead_of_asking_again():
         'a': feed([entry('t1_a', 5)]),
         'b': reddit.RedditThrottled('r/b: 429'),
         'c': feed([entry('t1_c', 5)]),
     })
 
     since = NOW - dt.timedelta(hours=1)
     result = reddit.fetch({'a': since, 'b': since, 'c': since}, client, pause=0)
 
     assert client.asked == ['a', 'b']
     assert [p.external_id for p in result.posts] == ['t1_a']
+    assert result.per_source_status == {
+        'reddit:a': 'ok', 'reddit:b': 'missing'}
 
     # 'c' was never requested, so it must not be scheduled as though it had
     # been -- it would lose its turn to whatever happened to sort earlier.
     assert 'c' not in result.rates
 
 
 def test_a_throttled_subreddit_keeps_its_place_rather_than_being_backed_off():
     """Reversed 2026-08-25, after measuring what the 429s actually were.
 
     This used to report a throttled sub at rate 0.0 -- a deliberate lie,
@@ -210,20 +211,22 @@ def test_one_unreachable_sub_does_not_cost_the_others():
     client = FakeClient({
         'a': reddit.RedditUnavailable('r/a: HTTP 500'),
         'b': feed([entry('t1_b', 5)]),
     })
 
     since = NOW - dt.timedelta(hours=1)
     result = reddit.fetch({'a': since, 'b': since}, client, pause=0)
 
     assert client.asked == ['a', 'b']
     assert [p.external_id for p in result.posts] == ['t1_b']
+    assert result.per_source_status == {
+        'reddit:a': 'missing', 'reddit:b': 'ok'}
     # Attempted and told nothing. Unknown, not zero -- a 500 says nothing
     # about whether the next request will work, so it is retried soon.
     assert result.rates['a'] is None
 
 
 def test_a_cycle_that_read_nothing_is_missing_not_ok():
     """`ok` with no posts means a genuinely quiet period, and the rollup
     writes zero counts for it. A cycle where every request failed observed
     nothing at all, which is a different fact."""
     client = FakeClient({'a': reddit.RedditUnavailable('down')})
@@ -254,29 +257,39 @@ def test_the_observed_rate_comes_from_the_feed():
 
     # Three comments across one hour.
     assert rate == pytest.approx(3.0, abs=0.1)
 
 
 def test_an_empty_feed_is_quiet_rather_than_broken():
     client = FakeClient({'x': feed([])})
 
     posts, status, rate = reddit.fetch_one('x', NOW - dt.timedelta(hours=1), client)
 
-    assert posts == [] and status == 'ok' and rate == 0.0
+    assert posts == [] and status == 'ok' and rate is None
+
+
+def test_an_unparseable_feed_is_unknown_to_the_scheduler():
+    """A bad response was attempted but supplied no rate measurement."""
+    client = FakeClient({'x': '<not atom'})
+
+    result = reddit.fetch({'x': NOW - dt.timedelta(hours=1)}, client, pause=0)
+
+    assert result.status == 'missing'
+    assert result.rates['x'] is None
 
 
 def test_every_configured_subreddit_fits_the_column_it_is_stored_in():
     """The bug this suite did not catch, 2026-08-24.
 
-    Reddit reuses the StockTwits poll scheduler with the SUBREDDIT as the
-    polled unit, and `radar_poll_state.symbol` was String(12) because
-    everything it had ever held was a ticker. Six of the eighteen names are
+    Reddit reuses the same poll scheduler every polled source shares, with the
+    SUBREDDIT as the polled unit, and `radar_poll_state.symbol` was String(12)
+    because everything it had ever held was a ticker. Six of the eighteen names are
     longer -- `RobinHoodPennyStocks` is 20 -- so `ensure_tracked` failed the
     whole batch insert on the daemon's first cycle and the source silently
     produced nothing at all.
 
     Asserted against the column rather than a literal, so widening the column
     moves this test with it and adding a longer subreddit fails here instead
     of in a log at 23:41.
     """
     from features.radar.config import REDDIT_SUBS
     from models import RadarPollState
@@ -319,10 +332,67 @@ def test_each_subreddit_is_read_from_its_own_cursor():
     })
 
     result = reddit.fetch({
         'busy': NOW - dt.timedelta(minutes=5),      # read 5 minutes ago
         'quiet': NOW - dt.timedelta(minutes=90),    # last read 90 minutes ago
     }, client, pause=0)
 
     got = {p.external_id for p in result.posts}
     assert got == {'t1_busy', 't1_quiet'}, (
         "the quiet subreddit was filtered out by another sub cursor")
+
+
+def test_all_three_prefixed_source_columns_are_wide_in_model_and_database():
+    """The longest configured Reddit name must survive the durable boundary."""
+    import sqlalchemy as sa
+
+    from app import app as flask_app
+    from extensions import db
+    from features.radar.config import REDDIT_SUBS
+    from models import RadarBucketSource, RadarPollState, RadarPost
+
+    concrete = max(('reddit:%s' % sub for sub in REDDIT_SUBS), key=len)
+    models = (RadarPost, RadarBucketSource, RadarPollState)
+    assert {model.__tablename__: model.__table__.c.source.type.length
+            for model in models} == {
+                'radar_posts': 48,
+                'radar_bucket_sources': 48,
+                'radar_poll_state': 48,
+            }
+
+    external_id = 'zz-task9-longest-source'
+    channel = 'zz_task9_source_width'
+    with flask_app.app_context():
+        inspector = sa.inspect(db.engine)
+        live = {
+            model.__tablename__: next(
+                column['type'].length
+                for column in inspector.get_columns(model.__tablename__)
+                if column['name'] == 'source')
+            for model in models
+        }
+        assert live == {
+            'radar_posts': 48,
+            'radar_bucket_sources': 48,
+            'radar_poll_state': 48,
+        }
+
+        def wipe_owned_post():
+            RadarPost.query.filter_by(
+                external_id=external_id, channel=channel).delete(
+                    synchronize_session=False)
+            db.session.commit()
+
+        wipe_owned_post()
+        try:
+            stamp = dt.datetime(2026, 8, 24, 12, 0, 0)
+            db.session.add(RadarPost(
+                source=concrete, external_id=external_id, channel=channel,
+                author='zz-task9', created_utc=stamp, title=None, body='$AAPL',
+                score=0, num_comments=0, url='', simhash=1,
+                first_seen=stamp, last_seen=stamp))
+            db.session.commit()
+            assert RadarPost.query.filter_by(
+                source=concrete, external_id=external_id).one().source == concrete
+        finally:
+            db.session.rollback()
+            wipe_owned_post()
diff --git a/personal_apps/tests/test_radar_retention.py b/personal_apps/tests/test_radar_retention.py
index dfc6734..f4cd073 100644
--- a/personal_apps/tests/test_radar_retention.py
+++ b/personal_apps/tests/test_radar_retention.py
@@ -77,10 +77,77 @@ def test_buckets_survive_their_posts(aged_posts):
 
 
 def test_chunking_deletes_everything_across_several_passes(aged_posts):
     deleted = retention.prune_posts(NOW, chunk_size=1)
     assert deleted == 2
 
 
 def test_pruning_an_empty_window_is_a_no_op(aged_posts):
     retention.prune_posts(NOW)
     assert retention.prune_posts(NOW) == 0
+
+
+# --- mention journal pruning -------------------------------------------------
+#
+# `clean_events` here cleans up by EXACT identity (ticker='ZZA', the two
+# external_ids this suite creates) rather than a broad `ticker.like('ZZ%')`
+# sweep. prune_mention_events's own delete query is unscoped by ticker -- it
+# is a real production pruner, not a test helper -- so the `now` chosen below
+# is deliberately a 2026-04-20 cutoff: the real dev database's
+# radar_mention_events rows are all from 2026-08-22/23 (checked directly
+# against the shared dev DB before writing this test), months after that
+# cutoff, so no real row can ever be `< cutoff` here regardless of what this
+# fixture does or does not clean up.
+
+@pytest.fixture()
+def clean_events():
+    from models import RadarMentionEvent
+    idents = ('zz-new', 'zz-old', 'zz-boundary')
+
+    def clear():
+        RadarMentionEvent.query.filter(
+            RadarMentionEvent.ticker == 'ZZA',
+            RadarMentionEvent.external_id.in_(idents)).delete(
+            synchronize_session=False)
+        db.session.commit()
+
+    with flask_app.app_context():
+        clear()
+        yield
+        clear()
+
+
+def test_the_journal_is_pruned_by_when_the_post_was_written(clean_events):
+    """By created_utc, not by when the row was inserted. A catch-up after an
+    outage ingests posts hours old, and once their bucket is past the retention
+    window nothing will rewrite it -- so that is what decides.
+
+    The third row sits at EXACTLY the cutoff (now - MENTION_EVENT_RETENTION_HOURS),
+    still safely inside this test's own April-2026 `now` -- nowhere near the real
+    dev database's Aug-2026 rows. `created_utc < cutoff` is strict, so a row
+    exactly at the cutoff has not yet aged out and must survive. This pins the
+    boundary: flipping the implementation's `<` to `<=` must fail this test.
+    """
+    from models import RadarMentionEvent
+
+    now = dt.datetime(2026, 4, 20, 12, 0, 0)
+    rows = (
+        (1, 'zz-new'),
+        (72, 'zz-old'),
+        (retention.MENTION_EVENT_RETENTION_HOURS, 'zz-boundary'),
+    )
+    for hours, ident in rows:
+        created = now - dt.timedelta(hours=hours)
+        db.session.add(RadarMentionEvent(
+            source='bluesky', external_id=ident, ticker='ZZA', channel='c',
+            created_utc=created,
+            bucket_start=created.replace(minute=0, second=0, microsecond=0),
+            author='u1', simhash=1, confidence='high',
+            sentiment=None, engagement=0.0))
+    db.session.commit()
+
+    deleted = retention.prune_mention_events(now)
+    assert deleted == 1
+    assert isinstance(deleted, int)
+    remaining = {e.external_id for e in
+                 RadarMentionEvent.query.filter_by(ticker='ZZA').all()}
+    assert remaining == {'zz-new', 'zz-boundary'}
diff --git a/personal_apps/tests/test_radar_scheduling.py b/personal_apps/tests/test_radar_scheduling.py
index f699e1c..419992f 100644
--- a/personal_apps/tests/test_radar_scheduling.py
+++ b/personal_apps/tests/test_radar_scheduling.py
@@ -193,28 +193,29 @@ def test_a_dropped_subreddit_stops_being_polled(ctx):
     scheduling.ensure_tracked('testsource', ['ZZA', 'ZZB'], NOW)
 
     retired = scheduling.retire_untracked('testsource', ['ZZA'])
 
     assert retired == 1
     assert scheduling.due_symbols('testsource', NOW, limit=10) == ['ZZA']
 
 
 def test_retiring_leaves_other_sources_alone(ctx):
     """One shared table, one row per (source, symbol). A reddit list edit must
-    not reach into StockTwits' state."""
+    not reach into another source's state."""
     scheduling.ensure_tracked('testsource', ['ZZA'], NOW)
     scheduling.ensure_tracked('othersource2', ['ZZB'], NOW)
 
     scheduling.retire_untracked('testsource', [])
 
     assert scheduling.due_symbols('othersource2', NOW, limit=10) == ['ZZB']
 
 
 def test_retiring_nothing_is_not_retiring_everything(ctx):
     """The empty-list trap. `symbols` empty has to mean "this source tracks
     nothing", but an accidental empty config would then wipe live state -- so
     the caller that owns a fixed list is the only one allowed to call this,
-    and StockTwits, whose hot set legitimately empties, never does."""
+    and a source whose tracked set is a rolling window -- which legitimately
+    empties -- must never call it."""
     scheduling.ensure_tracked('testsource', ['ZZA', 'ZZB'], NOW)
 
     assert scheduling.retire_untracked('testsource', ['ZZA', 'ZZB']) == 0
     assert len(scheduling.due_symbols('testsource', NOW, limit=10)) == 2
diff --git a/personal_apps/tests/test_radar_scoring.py b/personal_apps/tests/test_radar_scoring.py
index ea97ca8..a538835 100644
--- a/personal_apps/tests/test_radar_scoring.py
+++ b/personal_apps/tests/test_radar_scoring.py
@@ -1,224 +1,402 @@
 # personal_apps/tests/test_radar_scoring.py
 """Turning counts into surprise.
 
 Everything here reads radar_bucket_sources and writes back onto the same rows.
 No prices and no divergence -- those need a market feed and are Plan 3.
 """
 import datetime as dt
+import uuid
 
 import pytest
 
 from app import app as flask_app
 from extensions import db
 from models import RadarBucketSource
-from features.radar import scoring
+from features.radar import buckets, scoring
 from features.radar.config import source_config_version
+from test_radar_buckets import clean_buckets  # noqa: F401
 
 MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)
+# A concrete stored Reddit source name. Since 2026-08-26 every Reddit
+# observation is written under `reddit:<sub>`; the bare root is a SELECTION,
+# and pooled_z expands it to all eight configured subs.
+REDDIT = 'reddit:pennystocks'
 NOW = MONDAY + dt.timedelta(days=35)
+_OWNED_TICKERS = (
+    'SSA', 'SSB', 'SSNEW', 'SSOLD', 'SSNULL',
+    'ZZGEN', 'ZZSCORED', 'ZZSCOPE', 'ZZUNSCORED', 'ZZTRUNCATED',
+    'ZZMISSING',
+)
+
+
+def _clear_owned_rows():
+    RadarBucketSource.query.filter(
+        RadarBucketSource.ticker.in_(_OWNED_TICKERS)).delete(
+            synchronize_session=False)
+    db.session.commit()
 
 
 @pytest.fixture()
 def rows():
     with flask_app.app_context():
-        RadarBucketSource.query.filter(
-            RadarBucketSource.ticker.like('SS%')).delete(synchronize_session=False)
-        db.session.commit()
+        _clear_owned_rows()
         yield
-        RadarBucketSource.query.filter(
-            RadarBucketSource.ticker.like('SS%')).delete(synchronize_session=False)
-        db.session.commit()
+        _clear_owned_rows()
 
 
-def add(when, count, ticker='SSA', source='stocktwits', status='ok',
+def add(when, count, ticker='SSA', source='bluesky', status='ok',
         version=None):
     db.session.add(RadarBucketSource(
         ticker=ticker, bucket_start=when, source=source,
         mention_count=count, high_confidence_count=count, low_count=0,
         distinct_authors=count, distinct_text_ratio=1.0,
         engagement_weighted_count=float(count), status=status,
         source_config_version=version or source_config_version()))
 
 
-def steady_history(ticker='SSA', per_bucket=2, days=30, source='stocktwits'):
+def steady_history(ticker='SSA', per_bucket=2, days=30, source='bluesky'):
     """A boringly consistent ticker, so anything unusual is the test's doing.
 
     2880 rows at 15-minute grain. Added to the session and committed once by
     the caller -- committing per row makes this suite take minutes.
     """
     for step in range(days * 96):
         add(MONDAY + dt.timedelta(minutes=15 * step), per_bucket,
             ticker=ticker, source=source)
 
 
+def test_row_cleanup_preserves_an_unowned_zz_sentinel():
+    """This file's shared-DB cleanup must never claim another ZZ namespace."""
+    sentinel = 'ZZX' + uuid.uuid4().hex[:9].upper()
+    with flask_app.app_context():
+        db.session.add(RadarBucketSource(
+            ticker=sentinel, bucket_start=NOW, source='sentinel',
+            mention_count=1, high_confidence_count=1, low_count=0,
+            distinct_authors=1, distinct_text_ratio=1.0,
+            engagement_weighted_count=1.0, status='ok',
+            source_config_version='sentinel'))
+        db.session.commit()
+        try:
+            _clear_owned_rows()
+            assert RadarBucketSource.query.filter_by(ticker=sentinel).count() == 1
+        finally:
+            RadarBucketSource.query.filter_by(ticker=sentinel).delete(
+                synchronize_session=False)
+            db.session.commit()
+
+
 def test_a_normal_bucket_scores_near_zero(rows):
     steady_history()
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
 
     row = RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
     assert row.mention_z is not None
     assert abs(row.mention_z) < 2
 
 
 def test_a_spike_scores_high(rows):
     steady_history()
     loud = MONDAY + dt.timedelta(days=20)
     db.session.commit()
     RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
         {'mention_count': 60})
     db.session.commit()
 
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
     assert RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=loud).one().mention_z > 5
 
 
 def test_expected_and_variance_are_stored_too(rows):
     """Pooling a user-selected subset means summing components, so the parts
     have to survive, not just the z (spec 6.2)."""
     steady_history()
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
 
     row = RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
     assert row.expected > 0
     assert row.variance >= row.expected
 
 
 def test_missing_buckets_are_never_scored(rows):
     """A source that was down has nothing to be surprised about."""
     steady_history()
     gap = MONDAY + dt.timedelta(days=12)
     db.session.commit()
     RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=gap).update(
         {'status': 'missing', 'mention_count': 0})
     db.session.commit()
 
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
     assert RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=gap).one().mention_z is None
 
 
+def test_a_truncated_bucket_is_scored_from_ok_baselines(rows):
+    """Known undercounts remain rankable against an `ok`-only normal."""
+    steady_history(ticker='ZZTRUNCATED')
+    truncated_at = NOW - dt.timedelta(minutes=15)
+    add(truncated_at, 3, ticker='ZZTRUNCATED', status='truncated')
+    db.session.commit()
+
+    scoring.score_source('bluesky', NOW)
+
+    truncated = RadarBucketSource.query.filter_by(
+        ticker='ZZTRUNCATED', source='bluesky',
+        bucket_start=truncated_at).one()
+    assert truncated.status == 'truncated'
+    assert truncated.expected is not None
+    assert truncated.variance is not None
+    assert truncated.mention_z is not None
+    assert truncated.baseline_days is not None
+
+
+def test_scoreable_statuses_exclude_missing():
+    """The scoring eligibility contract admits incomplete observations only."""
+    assert scoring.SCOREABLE_STATUSES == frozenset({'ok', 'truncated'})
+
+
+def test_a_current_generation_missing_bucket_keeps_all_scores_null(rows):
+    """A source outage is an absence, even when its `ok` history is scoreable."""
+    steady_history(ticker='ZZMISSING')
+    missing_at = NOW - dt.timedelta(minutes=15)
+    add(missing_at, 0, ticker='ZZMISSING', status='missing')
+    db.session.commit()
+
+    scoring.score_source('bluesky', NOW)
+
+    missing = RadarBucketSource.query.filter_by(
+        ticker='ZZMISSING', source='bluesky', bucket_start=missing_at).one()
+    assert missing.status == 'missing'
+    assert missing.expected is None
+    assert missing.variance is None
+    assert missing.mention_z is None
+    assert missing.baseline_days is None
+
+
 def test_a_gap_does_not_depress_the_baseline(rows):
     """The observed-mass property, end to end. A week of outage must not make
     the ticker look like it went quiet, or everything after would spike."""
     steady_history()
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
     reference = RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z
 
     outage_start = MONDAY + dt.timedelta(days=5)
     RadarBucketSource.query.filter(
         RadarBucketSource.ticker == 'SSA',
         RadarBucketSource.bucket_start >= outage_start,
         RadarBucketSource.bucket_start < outage_start + dt.timedelta(days=7)
     ).update({'status': 'missing', 'mention_count': 0}, synchronize_session=False)
     db.session.commit()
 
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
     after = RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z
     assert after == pytest.approx(reference, abs=0.5)
 
 
 def test_baseline_days_is_recorded(rows):
     steady_history(days=30)
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
     row = RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
     assert row.baseline_days >= 14
 
 
 def test_a_brand_new_ticker_is_provisional(rows):
     """Two days of history cannot support a z-score anyone should act on."""
     for step in range(2 * 96):
         add(NOW - dt.timedelta(days=2) + dt.timedelta(minutes=15 * step), 3,
             ticker='SSNEW')
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
 
     row = (RadarBucketSource.query.filter_by(ticker='SSNEW')
            .order_by(RadarBucketSource.bucket_start.desc()).first())
     assert row.baseline_days < 14
 
 
 def test_scoring_only_touches_its_own_source(rows):
-    steady_history(source='stocktwits')
-    steady_history(ticker='SSB', source='bluesky')
+    steady_history(source='bluesky')
+    steady_history(ticker='SSB', source='reddit')
+    db.session.commit()
+    scoring.score_source('bluesky', NOW)
+
+    assert RadarBucketSource.query.filter_by(
+        ticker='SSB', source='reddit').first().mention_z is None
+
+
+def test_scoring_passes_the_current_generation_to_the_profile(rows,
+                                                               monkeypatch):
+    steady_history()
+    db.session.commit()
+    seen = {}
+    real_build_profile = scoring.profile.build_profile
+
+    def watched_build_profile(source, until, config_version, **kwargs):
+        seen['version'] = config_version
+        return real_build_profile(source, until, config_version, **kwargs)
+
+    monkeypatch.setattr(scoring.profile, 'build_profile', watched_build_profile)
+
+    scoring.score_source('bluesky', NOW)
+
+    assert seen['version'] == source_config_version()
+
+
+def test_scoring_clears_old_and_sql_null_scores_inside_its_lookback(rows):
+    steady_history()
+    scored_at = NOW - dt.timedelta(days=1)
+    for ticker, version in (('SSOLD', 'old-generation'), ('SSNULL', None)):
+        db.session.add(RadarBucketSource(
+            ticker=ticker, bucket_start=scored_at, source='bluesky',
+            mention_count=9, high_confidence_count=9, low_count=0,
+            distinct_authors=9, distinct_text_ratio=1.0,
+            engagement_weighted_count=9.0, status='ok',
+            source_config_version=version, expected=3.0, variance=4.0,
+            mention_z=3.0, baseline_days=20))
+    db.session.commit()
+
+    scoring.score_source('bluesky', NOW)
+
+    incompatible = (RadarBucketSource.query
+                    .filter(RadarBucketSource.ticker.in_(['SSOLD', 'SSNULL']))
+                    .order_by(RadarBucketSource.ticker).all())
+    assert len(incompatible) == 2
+    for row in incompatible:
+        assert row.expected is None
+        assert row.variance is None
+        assert row.mention_z is None
+        assert row.baseline_days is None
+
+
+def test_scoring_never_rescores_an_old_generation_row_mixed_with_current_history(rows):
+    """A current baseline must not make an incompatible row look current."""
+    steady_history(ticker='ZZGEN')
+    old_at = NOW - dt.timedelta(minutes=15)
+    add(old_at, 500, ticker='ZZGEN', version='old-generation')
+    db.session.commit()
+
+    scoring.score_source('bluesky', NOW)
+
+    old = RadarBucketSource.query.filter_by(
+        ticker='ZZGEN', bucket_start=old_at, source='bluesky').one()
+    assert old.mention_z is None
+
+
+def test_invalidation_skips_an_already_unscored_incompatible_row(rows):
+    since = NOW - dt.timedelta(days=1)
+    for ticker, score in (('ZZSCORED', 3.0), ('ZZUNSCORED', None)):
+        db.session.add(RadarBucketSource(
+            ticker=ticker, bucket_start=NOW - dt.timedelta(hours=1),
+            source='bluesky', mention_count=5, high_confidence_count=5,
+            low_count=0, distinct_authors=5, distinct_text_ratio=1.0,
+            engagement_weighted_count=5.0, status='ok',
+            source_config_version='old-generation', expected=2.0 if score else None,
+            variance=3.0 if score else None, mention_z=score,
+            baseline_days=10 if score else None))
+    db.session.commit()
+
+    cleared = scoring.invalidate_incompatible_scores(
+        source_config_version(), since)
+
+    assert cleared == 1
+    assert RadarBucketSource.query.filter_by(ticker='ZZUNSCORED').one().mention_z is None
+
+
+def test_scoring_invalidates_only_its_active_source(rows):
+    since = NOW - dt.timedelta(hours=1)
+    for source in ('reddit', 'bluesky'):
+        db.session.add(RadarBucketSource(
+            ticker='ZZSCOPE', bucket_start=NOW - dt.timedelta(minutes=15),
+            source=source, mention_count=5, high_confidence_count=5,
+            low_count=0, distinct_authors=5, distinct_text_ratio=1.0,
+            engagement_weighted_count=5.0, status='ok',
+            source_config_version='old-generation', expected=2.0, variance=3.0,
+            mention_z=3.0, baseline_days=10))
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
+
+    scoring.score_source('reddit', NOW)
 
     assert RadarBucketSource.query.filter_by(
-        ticker='SSB', source='bluesky').first().mention_z is None
+        ticker='ZZSCOPE', source='reddit').one().mention_z is None
+    assert RadarBucketSource.query.filter_by(
+        ticker='ZZSCOPE', source='bluesky').one().mention_z == 3.0
 
 
 def test_pooling_sums_components_not_z_scores(rows):
     """A weighted mean of z-scores is not a z-score. Two sources each two
     sigma over is stronger evidence than either alone, and averaging would
-    report the same two."""
-    for source in ('stocktwits', 'bluesky'):
+    report the same two.
+
+    The second source is a CONCRETE subreddit name. pooled_z takes a viewer
+    selection and expands it strictly, so the bare `reddit` would now expand
+    to the eight configured subs and match nothing these fixtures wrote."""
+    for source in (REDDIT, 'bluesky'):
         steady_history(source=source)
     loud = MONDAY + dt.timedelta(days=20)
     db.session.commit()
     RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
         {'mention_count': 12})
     db.session.commit()
 
-    for source in ('stocktwits', 'bluesky'):
+    for source in (REDDIT, 'bluesky'):
         scoring.score_source(source, NOW)
 
-    single, n_single = scoring.pooled_z('SSA', loud, ['stocktwits'])
-    both, n_both = scoring.pooled_z('SSA', loud, ['stocktwits', 'bluesky'])
+    single, n_single = scoring.pooled_z('SSA', loud, [REDDIT])
+    both, n_both = scoring.pooled_z('SSA', loud, [REDDIT, 'bluesky'])
     assert n_single == 1 and n_both == 2
     assert both > single
 
 
 def test_pooling_ignores_unselected_sources(rows):
-    for source in ('stocktwits', 'bluesky'):
+    for source in (REDDIT, 'bluesky'):
         steady_history(source=source)
     when = MONDAY + dt.timedelta(days=10)
     db.session.commit()
-    for source in ('stocktwits', 'bluesky'):
+    for source in (REDDIT, 'bluesky'):
         scoring.score_source(source, NOW)
 
     _, n = scoring.pooled_z('SSA', when, ['bluesky'])
     assert n == 1
 
 
 def test_a_missing_source_drops_out_rather_than_contributing_zero(rows):
     """The rule, at read time. A source that was down must not drag the pooled
     reading towards nothing."""
-    for source in ('stocktwits', 'bluesky'):
+    for source in (REDDIT, 'bluesky'):
         steady_history(source=source)
     when = MONDAY + dt.timedelta(days=10)
     db.session.commit()
     RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=when, source='bluesky').update(
         {'status': 'missing', 'mention_count': 0})
     db.session.commit()
-    for source in ('stocktwits', 'bluesky'):
+    for source in (REDDIT, 'bluesky'):
         scoring.score_source(source, NOW)
 
-    pooled, n = scoring.pooled_z('SSA', when, ['stocktwits', 'bluesky'])
-    only, _ = scoring.pooled_z('SSA', when, ['stocktwits'])
+    pooled, n = scoring.pooled_z('SSA', when, [REDDIT, 'bluesky'])
+    only, _ = scoring.pooled_z('SSA', when, [REDDIT])
     assert n == 1
     assert pooled == pytest.approx(only)
 
 
 def test_pooling_nothing_returns_none(rows):
-    assert scoring.pooled_z('SSNOPE', MONDAY, ['stocktwits']) == (None, 0)
+    assert scoring.pooled_z('SSNOPE', MONDAY, ['bluesky']) == (None, 0)
 
 
 def _forum(mentions=10, voices=6, text_ratio=0.9):
     return {'forum': scoring.Contribution(mentions, voices, text_ratio)}
 
 
 def _broadcast(mentions=10, voices=2, text_ratio=0.9):
     return {'broadcast': scoring.Contribution(mentions, voices, text_ratio)}
 
 
@@ -270,48 +448,87 @@ def test_nothing_at_all_is_not_eligible():
 
 
 def test_an_unknown_kind_is_judged_as_a_forum():
     unknown = {'something-new': scoring.Contribution(10, 2, 0.9)}
     assert scoring.is_eligible(unknown) is False
 
 
 def test_a_window_aggregates_its_buckets(rows):
     steady_history()
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
+    scoring.score_source('bluesky', NOW)
     end = MONDAY + dt.timedelta(days=20)
 
-    _, parts_1h = scoring.window_z('SSA', ['stocktwits'], end, hours=1)
-    _, parts_4h = scoring.window_z('SSA', ['stocktwits'], end, hours=4)
+    _, parts_1h = scoring.window_z('SSA', ['bluesky'], end, hours=1)
+    _, parts_4h = scoring.window_z('SSA', ['bluesky'], end, hours=4)
     assert parts_4h['mentions'] > parts_1h['mentions']
     assert parts_4h['expected'] > parts_1h['expected']
 
 
 def test_a_window_with_no_scored_buckets_is_none(rows):
-    assert scoring.window_z('SSNOPE', ['stocktwits'], NOW, hours=1) == (None, {})
+    assert scoring.window_z('SSNOPE', ['bluesky'], NOW, hours=1) == (None, {})
 
 
 def test_sustained_needs_several_non_overlapping_hours(rows):
     """1h, 4h and 24h are nested, so one loud hour lifts all three and
     "elevated in all three" would just restate it. Sustained is measured over
     consecutive separate hours instead (spec 6.9)."""
     steady_history()
     end = MONDAY + dt.timedelta(days=20)
     db.session.commit()
 
     for step in range(4):                      # one loud hour only
         RadarBucketSource.query.filter_by(
             ticker='SSA',
             bucket_start=end - dt.timedelta(minutes=15 * (step + 1))).update(
             {'mention_count': 40})
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
-    assert scoring.is_sustained('SSA', ['stocktwits'], end) is False
+    scoring.score_source('bluesky', NOW)
+    assert scoring.is_sustained('SSA', ['bluesky'], end) is False
 
     for step in range(12):                     # three of the last four hours
         RadarBucketSource.query.filter_by(
             ticker='SSA',
             bucket_start=end - dt.timedelta(minutes=15 * (step + 1))).update(
             {'mention_count': 40})
     db.session.commit()
-    scoring.score_source('stocktwits', NOW)
-    assert scoring.is_sustained('SSA', ['stocktwits'], end) is True
+    scoring.score_source('bluesky', NOW)
+    assert scoring.is_sustained('SSA', ['bluesky'], end) is True
+
+
+def row(external_id, minute=0, hour=14, ticker='ZZA', source='bluesky'):
+    """A MentionRow for the fractional-baseline test below.
+
+    test_radar_buckets.row() (whose clean_buckets fixture is reused above)
+    hardcodes hour=14, which would collapse all three of that test's
+    roll_up calls onto the same 14:00 bucket -- span would be zero and the
+    assertion the test exists to make would never pass, before or after the
+    fix. This local row() takes `hour` explicitly so the three calls land in
+    three separate buckets, the way the scenario needs.
+    """
+    return buckets.MentionRow(
+        ticker=ticker, external_id=external_id,
+        created_utc=dt.datetime(2026, 4, 15, hour, minute, 0),
+        source=source, channel='c', author='u1', simhash=111,
+        confidence='high', sentiment=0.5, engagement=10.0)
+
+
+def test_a_baseline_shorter_than_a_day_is_not_reported_as_zero_days(clean_buckets):
+    """span.days truncates. Twenty-three hours of history is not no history,
+    and reporting it as zero put every row on the board permanently
+    provisional -- 147,228 of 147,429 in production."""
+    import datetime as dt
+
+    from features.radar import buckets, scoring
+    from models import RadarBucketSource
+
+    now = dt.datetime(2026, 4, 16, 14, 0, 0)
+    for hour in (14, 20, 23):
+        start = dt.datetime(2026, 4, 15, hour, 0, 0)
+        buckets.roll_up([row(external_id='zz-%d' % hour, minute=0, hour=hour)],
+                        {'bluesky': 'ok'}, {start})
+
+    scoring.score_source('bluesky', now)
+
+    scored = RadarBucketSource.query.filter_by(
+        ticker='ZZA', source='bluesky').first()
+    assert 0 < scored.baseline_days < 1
diff --git a/personal_apps/tests/test_radar_spend.py b/personal_apps/tests/test_radar_spend.py
index aed89b6..c3df418 100644
--- a/personal_apps/tests/test_radar_spend.py
+++ b/personal_apps/tests/test_radar_spend.py
@@ -6,42 +6,52 @@ than remaining credit, needs a separate Admin API key, and the docs say twice
 that the Admin API is unavailable for individual accounts. So this counts the
 tokens the responses already carry, which is exact, free, and attributable to
 radar rather than to the whole key.
 
 Money is stored in integer MICROS. A float here accumulates rounding every
 call and then reports a total nobody can reconcile against a bank statement.
 """
 import datetime as dt
 
 import pytest
+import sqlalchemy as sa
 
 from app import app as flask_app
 from extensions import db
 from models import RadarLlmSpend
 from features.radar import spend
 
 TODAY = dt.date(2026, 8, 25)
 MODEL = 'claude-haiku-4-5'
+SPEND_IDENTITIES = (
+    (TODAY, MODEL),
+    (TODAY - dt.timedelta(days=5), MODEL),
+    (dt.date(2026, 8, 1), MODEL),
+    (dt.date(2026, 7, 31), MODEL),
+    (TODAY, 'claude-some-future-model'),
+    (dt.date(2026, 4, 15), MODEL),
+    (dt.date(2026, 4, 15), 'claude-unknown-9'),
+)
 
 
 @pytest.fixture()
 def clean_spend():
-    with flask_app.app_context():
-        RadarLlmSpend.query.filter(
-            RadarLlmSpend.day >= dt.date(2026, 8, 1)).delete(
-                synchronize_session=False)
+    def wipe():
+        RadarLlmSpend.query.filter(sa.tuple_(
+            RadarLlmSpend.day, RadarLlmSpend.model).in_(SPEND_IDENTITIES)
+        ).delete(synchronize_session=False)
         db.session.commit()
+
+    with flask_app.app_context():
+        wipe()
         yield
-        RadarLlmSpend.query.filter(
-            RadarLlmSpend.day >= dt.date(2026, 8, 1)).delete(
-                synchronize_session=False)
-        db.session.commit()
+        wipe()
 
 
 def test_a_days_first_call_creates_its_row(clean_spend):
     with flask_app.app_context():
         spend.record(MODEL, calls=1, input_tokens=2000, output_tokens=300,
                      day=TODAY)
 
         row = RadarLlmSpend.query.filter_by(day=TODAY, model=MODEL).one()
         assert row.calls == 1
         assert row.input_tokens == 2000
@@ -104,20 +114,39 @@ def test_an_unpriced_model_records_tokens_and_no_cost(clean_spend):
     """
     with flask_app.app_context():
         spend.record('claude-some-future-model', calls=1, input_tokens=500,
                      output_tokens=50, day=TODAY)
 
         row = RadarLlmSpend.query.filter_by(model='claude-some-future-model').one()
         assert row.input_tokens == 500
         assert row.cost_micros == 0
 
 
+def test_an_unpriced_model_costs_null_not_nothing():
+    """Zero is a price. Not knowing the price is not one."""
+    assert spend.cost_micros('claude-not-a-real-model', 1000, 100) is None
+    assert spend.cost_micros(MODEL, 1_000_000, 0) == 1_000_000
+
+
+def test_the_summary_surfaces_what_it_could_not_price(clean_spend):
+    day = dt.date(2026, 4, 15)
+    spend.record(MODEL, calls=1, input_tokens=1_000_000,
+                 output_tokens=0, day=day)
+    spend.record('claude-unknown-9', calls=1, input_tokens=500_000,
+                 output_tokens=1000, day=day)
+
+    result = spend.summary(today=day)
+
+    assert result['today_usd'] == 1.0
+    assert result['unpriced_tokens'] == 501_000
+
+
 def test_nothing_is_written_for_a_call_that_used_nothing(clean_spend):
     """A failed batch reports no usage. A zero row would make an outage look
     like a quiet day, which is the same confusion the bucket statuses exist to
     prevent."""
     with flask_app.app_context():
         spend.record(MODEL, calls=0, input_tokens=0, output_tokens=0, day=TODAY)
 
         assert RadarLlmSpend.query.filter_by(day=TODAY).count() == 0
 
 
diff --git a/personal_apps/tests/test_radar_stocktwits.py b/personal_apps/tests/test_radar_stocktwits.py
deleted file mode 100644
index e5ffbab..0000000
--- a/personal_apps/tests/test_radar_stocktwits.py
+++ /dev/null
@@ -1,178 +0,0 @@
-# personal_apps/tests/test_radar_stocktwits.py
-"""StockTwits: finance-native, dense, and narrow.
-
-Measured at ~23 messages/hour on a trending symbol with 20-27 distinct authors
-per 30 messages. Its discovery surface is only the 30 trending symbols, which
-is why the standing set exists (spec 3.5).
-"""
-import datetime as dt
-
-from features.radar.sources import FetchResult
-from features.radar.sources import stocktwits
-
-
-class FakeClient:
-    def __init__(self, payloads):
-        self.payloads = payloads
-        self.calls = []
-
-    def get(self, path, params=None):
-        self.calls.append(path)
-        if path not in self.payloads:
-            raise stocktwits.StockTwitsUnavailable('404 %s' % path)
-        return self.payloads[path]
-
-
-def _message(ident, created, body='$ZZA to the moon', user=1, sentiment='Bullish'):
-    return {
-        'id': ident,
-        'body': body,
-        'created_at': created.strftime('%Y-%m-%dT%H:%M:%SZ'),
-        'user': {'id': user, 'username': 'user%d' % user},
-        'symbols': [{'symbol': 'ZZA'}],
-        'entities': {'sentiment': {'basic': sentiment}} if sentiment else {},
-        'likes': {'total': 3},
-    }
-
-
-BASE = dt.datetime(2026, 8, 21, 14, 0, 0)
-
-
-def test_trending_filters_crypto_by_instrument_class():
-    """instrument_class is explicit, so the filter is a field check rather than
-    a guess at what .X means (spec 3.7)."""
-    client = FakeClient({'/trending/symbols.json': {'symbols': [
-        {'symbol': 'ZZA', 'instrument_class': 'Stock'},
-        {'symbol': 'BTC.X', 'instrument_class': 'CRYPTO'},
-        {'symbol': 'ZZB', 'instrument_class': 'Stock'},
-    ]}})
-    assert stocktwits.trending(client) == ['ZZA', 'ZZB']
-
-
-def test_a_stream_becomes_rawposts():
-    client = FakeClient({'/streams/symbol/ZZA.json': {
-        'messages': [_message(2, BASE), _message(1, BASE - dt.timedelta(minutes=5))]}})
-    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
-    assert isinstance(result, FetchResult)
-    assert result.status == 'ok'
-    assert len(result.posts) == 2
-    post = result.posts[0]
-    assert post.source == 'stocktwits'
-    assert post.external_id == 'stocktwits:2'
-    assert post.native_tickers == ['ZZA']
-    assert post.native_sentiment == 'Bullish'
-    assert post.author == 'user1'
-
-
-def test_messages_older_than_since_are_dropped():
-    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': [
-        _message(2, BASE),
-        _message(1, BASE - dt.timedelta(hours=4)),
-    ]}})
-    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
-    assert [p.external_id for p in result.posts] == ['stocktwits:2']
-
-
-def test_a_full_page_of_new_messages_is_truncated():
-    """30 is the page size. All 30 newer than `since` means there are probably
-    more we did not see, and an undercount must never reach a baseline."""
-    messages = [_message(i, BASE - dt.timedelta(seconds=i)) for i in range(30)]
-    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': messages}})
-    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
-    assert result.status == 'truncated'
-    assert len(result.posts) == 30
-
-
-def test_one_symbol_failing_does_not_lose_the_others():
-    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': [_message(1, BASE)]}})
-    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA', 'MISSING'])
-    assert [p.external_id for p in result.posts] == ['stocktwits:1']
-    assert result.status == 'truncated'
-
-
-def test_every_symbol_failing_is_missing_with_no_posts():
-    client = FakeClient({})
-    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA', 'ZZB'])
-    assert result.status == 'missing'
-    assert result.posts == []
-
-
-def test_message_rate_is_reported_per_symbol():
-    """The scheduler derives each symbol's poll interval from this, because the
-    API returns 30 messages whatever their timespan (spec 3.5)."""
-    messages = [_message(i, BASE - dt.timedelta(minutes=i * 2)) for i in range(30)]
-    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': messages}})
-    result = stocktwits.fetch(BASE - dt.timedelta(hours=6), client, ['ZZA'])
-    # 30 messages spanning 58 minutes -> a bit over 30/hour.
-    assert 25 < result.rates['ZZA'] < 40
-
-
-def test_an_empty_stream_is_ok_not_missing():
-    """A healthy source that saw nothing is a real zero. Only a failure is
-    `missing` (spec 4.5)."""
-    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': []}})
-    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
-    assert result.status == 'ok'
-    assert result.posts == []
-
-
-def test_symbols_are_fetched_concurrently():
-    """Measured: a stream call takes ~43 seconds, throttled rather than loaded.
-    Serially, a cycle's worth of symbols would not fit inside the cycle."""
-    import threading
-    import time
-
-    peak = {'n': 0, 'now': 0}
-    lock = threading.Lock()
-
-    class SlowClient:
-        def get(self, path, params=None):
-            with lock:
-                peak['now'] += 1
-                peak['n'] = max(peak['n'], peak['now'])
-            time.sleep(0.2)
-            with lock:
-                peak['now'] -= 1
-            return {'messages': [_message(1, BASE)]}
-
-    stocktwits.fetch(BASE - dt.timedelta(hours=1), SlowClient(),
-                     ['A', 'B', 'C', 'D'], max_workers=4)
-    assert peak['n'] > 1, 'requests ran serially'
-
-
-def test_concurrency_never_exceeds_the_cap():
-    """The rate limit is undocumented, so a burst is the wrong thing to guess
-    with."""
-    import threading
-    import time
-
-    peak = {'n': 0, 'now': 0}
-    lock = threading.Lock()
-
-    class SlowClient:
-        def get(self, path, params=None):
-            with lock:
-                peak['now'] += 1
-                peak['n'] = max(peak['n'], peak['now'])
-            time.sleep(0.1)
-            with lock:
-                peak['now'] -= 1
-            return {'messages': []}
-
-    stocktwits.fetch(BASE - dt.timedelta(hours=1), SlowClient(),
-                     ['A', 'B', 'C', 'D', 'E', 'F'], max_workers=2)
-    assert peak['n'] <= 2
-
-
-def test_no_symbols_is_ok_and_costs_nothing():
-    """A cycle where nothing is DUE must not look like a failure.
-
-    Narrow on purpose. This function cannot tell "nothing was scheduled" from
-    "the source is dead", because both arrive as an empty symbol list -- and
-    reading the second as `ok` wrote zero-count buckets for a source that was
-    403 on every request. The caller knows which it is and decides; see
-    run_radar_ingest._stocktwits_fetcher.
-    """
-    result = stocktwits.fetch(BASE, FakeClient({}), [])
-    assert result.status == 'ok'
-    assert result.posts == []
```
