# Review package: 47d1c2c..aee4e2f

## Commits
aee4e2f fix(radar): rank truncated buckets instead of discarding ninety percent of reddit

## Files changed
 personal_apps/features/radar/scoring.py   | 23 ++++++++++++----
 personal_apps/tests/test_radar_scoring.py | 45 ++++++++++++++++++++++++++++++-
 2 files changed, 62 insertions(+), 6 deletions(-)

## Diff
diff --git a/personal_apps/features/radar/scoring.py b/personal_apps/features/radar/scoring.py
index 9c4cd31..63efa85 100644
--- a/personal_apps/features/radar/scoring.py
+++ b/personal_apps/features/radar/scoring.py
@@ -22,20 +22,32 @@ from models import RadarBucketSource
 from . import baselines, profile
 from .config import (ELEVATED_Z, MIN_DISTINCT_AUTHORS, MIN_DISTINCT_CHANNELS,
                      MIN_DISTINCT_TEXT_RATIO, MIN_MENTIONS,
                      SUSTAINED_HOURS_CONSIDERED, SUSTAINED_HOURS_REQUIRED,
                      VARIANCE_FLOOR, expand_sources, source_config_version)
 
 # Weight of the cold-start prior, in units of observed mass. 0.05 of a week is
 # about eight hours: enough to dominate on day one and vanish by week two.
 PRIOR_WEIGHT = 0.05
 
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
 
 def _rows_by_ticker(source, since, until, config_version):
     """Every row a ticker may be scored or baselined from, THIS generation only.
 
     Filtered here rather than trusted to baselines.usable() downstream: usable()
     only screens what feeds the RATE estimate, but the write loop below scores
     every `ok` row it is handed. Without this filter, a ticker straddling a
     generation boundary -- some current rows plus an old-generation row that
     invalidate_incompatible_scores has not yet reached -- would have the old
     row overwritten with a freshly computed z from the CURRENT baseline, which
@@ -133,23 +145,24 @@ def score_source(source, now, lookback_days=30, excluded=None):
         if not good:
             continue
 
         rate, _ = baselines.weekly_rate(good, prof, prior_rate=prior_rate,
                                         prior_weight=PRIOR_WEIGHT)
         k = baselines.dispersion(good, prof, rate)
         span = max(o.bucket_start for o in good) - min(o.bucket_start for o in good)
         baseline_days = span.days
 
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
@@ -159,22 +172,22 @@ def score_source(source, now, lookback_days=30, excluded=None):
 
 
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
 
     `sources` is a selection and expands STRICTLY: this reads `expected` and
     `variance`, and the pre-split root `reddit` rows were baselined against a
     different population (config.expand_sources).
     """
     sources = expand_sources(sources)
     rows = (RadarBucketSource.query
             .filter(RadarBucketSource.ticker == ticker,
                     RadarBucketSource.bucket_start == bucket_start,
                     RadarBucketSource.source.in_(list(sources)),
diff --git a/personal_apps/tests/test_radar_scoring.py b/personal_apps/tests/test_radar_scoring.py
index 4ea00bc..f212893 100644
--- a/personal_apps/tests/test_radar_scoring.py
+++ b/personal_apps/tests/test_radar_scoring.py
@@ -16,21 +16,22 @@ from features.radar import scoring
 from features.radar.config import source_config_version
 
 MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)
 # A concrete stored Reddit source name. Since 2026-08-26 every Reddit
 # observation is written under `reddit:<sub>`; the bare root is a SELECTION,
 # and pooled_z expands it to all eight configured subs.
 REDDIT = 'reddit:pennystocks'
 NOW = MONDAY + dt.timedelta(days=35)
 _OWNED_TICKERS = (
     'SSA', 'SSB', 'SSNEW', 'SSOLD', 'SSNULL',
-    'ZZGEN', 'ZZSCORED', 'ZZSCOPE', 'ZZUNSCORED',
+    'ZZGEN', 'ZZSCORED', 'ZZSCOPE', 'ZZUNSCORED', 'ZZTRUNCATED',
+    'ZZMISSING',
 )
 
 
 def _clear_owned_rows():
     RadarBucketSource.query.filter(
         RadarBucketSource.ticker.in_(_OWNED_TICKERS)).delete(
             synchronize_session=False)
     db.session.commit()
 
 
@@ -127,20 +128,62 @@ def test_missing_buckets_are_never_scored(rows):
     db.session.commit()
     RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=gap).update(
         {'status': 'missing', 'mention_count': 0})
     db.session.commit()
 
     scoring.score_source('bluesky', NOW)
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
     scoring.score_source('bluesky', NOW)
     reference = RadarBucketSource.query.filter_by(
         ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z
 
     outage_start = MONDAY + dt.timedelta(days=5)
