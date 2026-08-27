# Review package: 4264036..d5997c9

## Commits
d5997c9 fix(radar): account for breadth exclusions and extract once
e4de0b5 fix(radar): an outage mid-window is a gap in the chart, not quiet
8a23a26 fix(radar): an unpriced model reads as unknown, not as free
af11f2c fix(radar): an unread feed reports no rate rather than a rate of zero

## Files changed
 personal_apps/features/radar/board.py              |  7 ++-
 personal_apps/features/radar/detail.py             | 42 ++++++++++--------
 personal_apps/features/radar/ingest.py             | 23 +++++++---
 personal_apps/features/radar/leaderboard.py        |  6 +--
 personal_apps/features/radar/sources/reddit.py     |  5 ++-
 personal_apps/features/radar/spend.py              | 32 ++++++++++----
 personal_apps/static/radar/src/list/Spend.test.tsx | 22 ++++++++--
 personal_apps/static/radar/src/list/Spend.tsx      |  5 ++-
 personal_apps/static/radar/src/types.ts            |  2 +-
 personal_apps/tests/test_radar_api.py              | 15 +++++++
 personal_apps/tests/test_radar_board.py            | 48 ++++++++++++++++++++
 personal_apps/tests/test_radar_detail.py           | 51 ++++++++++++++++++++++
 personal_apps/tests/test_radar_ingest.py           | 37 ++++++++++++++++
 personal_apps/tests/test_radar_reddit.py           | 12 ++++-
 personal_apps/tests/test_radar_spend.py            | 45 +++++++++++++++----
 15 files changed, 298 insertions(+), 54 deletions(-)

## Diff
diff --git a/personal_apps/features/radar/board.py b/personal_apps/features/radar/board.py
index 3996575..8fc4380 100644
--- a/personal_apps/features/radar/board.py
+++ b/personal_apps/features/radar/board.py
@@ -305,21 +305,26 @@ def build(sources, now, window_hours=4, segments=(), limit=50,
     # r/pennystocks is not that. `row.venues` is the rooted count.
     venue_counts = {
         'any': len(ranked),
         'multi': sum(1 for row in ranked if row.venues > 1),
     }
 
     allowed = segments_in(segments)
     if allowed:
         ranked = [row for row in ranked if row.segment in allowed]
     if min_venues > 1:
-        ranked = [row for row in ranked if row.venues >= min_venues]
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
 
diff --git a/personal_apps/features/radar/detail.py b/personal_apps/features/radar/detail.py
index 80cf0b8..95b0e70 100644
--- a/personal_apps/features/radar/detail.py
+++ b/personal_apps/features/radar/detail.py
@@ -190,52 +190,58 @@ def intraday_counts(ticker, sources, start, now, step_minutes, slots):
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
     sources = expand_sources_for_history(sources)
-    earliest = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
-                .filter(RadarBucketSource.source.in_(list(sources)),
-                        RadarBucketSource.bucket_start >= start,
-                        RadarBucketSource.bucket_start < now).scalar())
-    if earliest is None:
-        return None
-    return _slot_index(earliest, start, step_minutes, slots)
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
diff --git a/personal_apps/features/radar/ingest.py b/personal_apps/features/radar/ingest.py
index bea0a5b..5cb8e1e 100644
--- a/personal_apps/features/radar/ingest.py
+++ b/personal_apps/features/radar/ingest.py
@@ -88,42 +88,49 @@ def _extract_for(raw, lookup):
 
 
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
@@ -153,24 +160,25 @@ def _store_mentioning_posts(raw_posts, lookup, now):
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
@@ -231,21 +239,22 @@ def run_cycle(now, fetchers):
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
         # A fetcher covering several source names reports each. Reddit does:
         # one cycle reads a slice of subreddits and each is its own source.
         # When those concrete statuses exist, the aggregate fetch verdict must
         # not become a zero-valued root child in the rollup population.
         #
         # `is not None`, NOT truthiness. An empty map is an explicit "no
         # source was observed" -- Reddit with nothing due did not read Reddit
         # -- and falling back to the aggregate verdict there would stamp
         # `{'reddit': 'ok'}` onto the rollup, which writes a zero-count child
diff --git a/personal_apps/features/radar/leaderboard.py b/personal_apps/features/radar/leaderboard.py
index cb630d0..028c148 100644
--- a/personal_apps/features/radar/leaderboard.py
+++ b/personal_apps/features/radar/leaderboard.py
@@ -13,22 +13,22 @@ import datetime as dt
 import sqlalchemy as sa
 
 from extensions import db
 from models import RadarBucketSource, TickerUniverse
 
 from . import divergence as divergence_mod
 from . import journal
 from . import market_calendar
 from . import quotes as quotes_mod
 from . import scoring, universe
-from .config import (PROVISIONAL_BASELINE_DAYS, expand_sources, segments_in,
-                     source_kind, source_root)
+from .config import (PROVISIONAL_BASELINE_DAYS, VARIANCE_FLOOR,
+                     expand_sources, segments_in, source_kind, source_root)
 
 
 @dataclasses.dataclass
 class Ranking:
     """Rows worth showing, and an account of what was left out.
 
     The account is not decoration. The eligibility floor is the single largest
     reason this board is short, and until now it dropped tickers with no trace
     -- so a quiet market and a stopped daemon rendered identically, and the
     reader had no way to tell which they were looking at.
@@ -241,21 +241,21 @@ def build_rows(sources, now, window_hours=4, segments=(), limit=50,
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
         # One venue per ROOT, not per stored name -- see Row.venues.
         venues = len({source_root(name) for name in contributing})
         # MIN already skipped NULLs per source; this skips the sources that
         # had nothing but NULLs, so a row with no usable baseline anywhere
         # still reports None rather than raising.
         baseline_days = min((part.baseline_days for part in parts
                              if part.baseline_days is not None), default=None)
 
diff --git a/personal_apps/features/radar/sources/reddit.py b/personal_apps/features/radar/sources/reddit.py
index c3d56c8..aa25114 100644
--- a/personal_apps/features/radar/sources/reddit.py
+++ b/personal_apps/features/radar/sources/reddit.py
@@ -156,21 +156,24 @@ def fetch_one(sub, since, client):
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
diff --git a/personal_apps/static/radar/src/list/Spend.test.tsx b/personal_apps/static/radar/src/list/Spend.test.tsx
index 935539c..21ceb63 100644
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
     /* Three places below a dollar because a day costs about twenty cents and
        "$0.20" reads as a rounding of something unknown. Above a dollar the
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
index ec2f46f..a8128ed 100644
--- a/personal_apps/static/radar/src/list/Spend.tsx
+++ b/personal_apps/static/radar/src/list/Spend.tsx
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
diff --git a/personal_apps/static/radar/src/types.ts b/personal_apps/static/radar/src/types.ts
index 7ba675a..4bc19cf 100644
--- a/personal_apps/static/radar/src/types.ts
+++ b/personal_apps/static/radar/src/types.ts
@@ -182,21 +182,21 @@ export interface BoardPayload {
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
index 1be32c4..4fe0dd5 100644
--- a/personal_apps/tests/test_radar_api.py
+++ b/personal_apps/tests/test_radar_api.py
@@ -13,20 +13,35 @@ def test_the_board_requires_login(anon_client):
 
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
diff --git a/personal_apps/tests/test_radar_board.py b/personal_apps/tests/test_radar_board.py
index 8f0e020..f077c03 100644
--- a/personal_apps/tests/test_radar_board.py
+++ b/personal_apps/tests/test_radar_board.py
@@ -357,20 +357,68 @@ def test_venue_counts_are_taken_before_the_venue_filter(clean):
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
 def test_two_subreddits_are_one_venue(clean):
     """The breadth filter's claim is INDEPENDENT corroboration.
 
     Since 2026-08-26 each subreddit is its own stored source name, so a
     ticker discussed in r/wallstreetbets and r/pennystocks now has two
     entries in `sources`. It still has one venue: they share a platform, a
     user population and a rate-limit budget, and "the same reading from two
     independent sources" -- the words the surface puts on the
     `single-source` mark -- is not what happened.
     """
diff --git a/personal_apps/tests/test_radar_detail.py b/personal_apps/tests/test_radar_detail.py
index 6b83fc9..e25b1a8 100644
--- a/personal_apps/tests/test_radar_detail.py
+++ b/personal_apps/tests/test_radar_detail.py
@@ -574,20 +574,71 @@ def test_a_slot_before_observation_began_is_unknown_not_zero(clean_intraday):
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
diff --git a/personal_apps/tests/test_radar_ingest.py b/personal_apps/tests/test_radar_ingest.py
index 539f21a..5da10a0 100644
--- a/personal_apps/tests/test_radar_ingest.py
+++ b/personal_apps/tests/test_radar_ingest.py
@@ -373,20 +373,46 @@ def test_the_same_post_twice_in_one_batch_is_stored_once(seeded):
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
@@ -431,20 +457,31 @@ def test_an_unexpected_source_error_does_not_kill_the_cycle(seeded):
     result = ingest.run_cycle(NOW, {'bluesky': exploding, 'reddit': healthy})
 
     assert result['per_source'] == {'bluesky': 'missing', 'reddit': 'ok'}
     assert result['mentions'] == 1
     with flask_app.app_context():
         from models import RadarBucketSource
         rows = {r.source for r in RadarBucketSource.query.filter_by(ticker='ZZG')}
         assert rows == {'reddit'}   # no bluesky row, and no zero
 
 
+def test_a_failed_fetch_reports_no_catchup_depth(seeded):
+    """Depth zero says the source reached back nowhere; failure reached nothing."""
+    def explode(since):
+        raise RuntimeError('nope')
+
+    summary = ingest.run_cycle(NOW, {'bluesky': explode})
+
+    assert summary['per_source']['bluesky'] == 'missing'
+    assert summary['catchup_depth']['bluesky'] is None
+
+
 def test_a_coin_collision_is_dropped_on_a_general_source(seeded, monkeypatch):
     """$BCH on Bluesky means Bitcoin Cash, not Banco de Chile.
 
     ZZG stands in for a coin-shaped symbol so the test does not depend on
     which real tickers happen to collide this year.
     """
     from features.radar import config
     monkeypatch.setattr(config, 'COIN_COLLISION_SYMBOLS', frozenset({'ZZG'}))
 
     p = post(ident='bs_coin', body='$ZZG pumping')
diff --git a/personal_apps/tests/test_radar_reddit.py b/personal_apps/tests/test_radar_reddit.py
index 9d92c27..35c7dd8 100644
--- a/personal_apps/tests/test_radar_reddit.py
+++ b/personal_apps/tests/test_radar_reddit.py
@@ -257,21 +257,31 @@ def test_the_observed_rate_comes_from_the_feed():
 
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
 
     Reddit reuses the same poll scheduler every polled source shares, with the
     SUBREDDIT as the polled unit, and `radar_poll_state.symbol` was String(12)
     because everything it had ever held was a ticker. Six of the eighteen names are
     longer -- `RobinHoodPennyStocks` is 20 -- so `ensure_tracked` failed the
     whole batch insert on the daemon's first cycle and the source silently
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
 
 
