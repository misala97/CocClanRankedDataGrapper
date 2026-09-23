# PERF1 progress

Binding brief: `radar-design/CLAUDE-PERF1.md`, copied into this workspace.

| Item | State |
| --- | --- |
| Workspace and base established | **Done** |
| P0 — VPS facts: SHA, engine, workers, cardinalities, indexes | **Done** |
| P0 — bottleneck proof | **Done** — plan flip confirmed on the target with the real query shape |
| P0 — production-scale local reproduction | **Done** — 9,269,184 rows, six partitions, pool matched |
| P1 — implement | **Done** — one covering index, `c4e17b90d3f2` |
| P2 — acceptance and independent review | **Done** — review found nine confirmed defects; see the retraction below |
| Deployment | Not authorized by this brief |
| **Codex ruling, 2026-09-10** | **Accepted as an investigation with a useful negative result. Product performance acceptance is OPEN. Index HELD. Single-flight not approved and not to be polished further.** |

**Read the retraction section before quoting any number from the first
half of this file.** The independent review invalidated the P1 evidence as
first written, and the corrected numbers are much smaller.

**And the concurrency conclusion that replaced it is retracted too.** The
two-reader pair was measured with two THREADS in one process; production runs
two single-threaded SYNC worker processes. Nothing in this file establishes
what causes the owner's timeout on the target, and the target has no latency
telemetry with which to establish it. The corrected serial numbers -- 24h
median **4.50s**, p95 **4.72s** with the held index -- miss the <=2s cold
target, which is why PERF2 takes the build off the request path. See
`PERF1-CODEX-RULING.md`.

## Workspace

| Fact | Value |
| --- | --- |
| Worktree | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf1` |
| Branch | `codex/radar-perf1` |
| Base | **`4221196`** — the SHA actually deployed, read from the target |
| Local database | `personal_apps_radar_perf1` (named in this worktree's `.env`; not yet created) |

**Base chosen deliberately.** The brief says the defect predates B1 and affects
the original `/radar/` too, so the fix has to be deployable without B1, which
the owner has not yet approved. Basing on the deployed SHA makes the return a
clean release delta. B1 rebases onto it afterwards.

**Deployment differences from B1.** `codex/radar-b1` at `6c63959` is six code
commits and two documentation commits ahead of `4221196`: the B1 shell and
workspace, and the `detail_panel` measured-move change. None of it is
deployed. Codex's B1 ruling item 3 (the shared price-narrative correction) is
a separate deployment carry and is NOT part of PERF1.

## P0 facts, read from the target

Read-only. No code, configuration, schema, service, cache or authentication
action was taken on the target, and no owner session was minted.

| Fact | Value |
| --- | --- |
| Deployed SHA | **`4221196`** |
| Working tree there | clean apart from untracked `venv/`, `reports/`, two ticker files and a scratch JSON |
| Engine | **MariaDB 10.11.14**-0ubuntu0.24.04.1 |
| Web workers | `gunicorn --workers 2 --bind 127.0.0.1:5001` |
| `personal_apps_web`, `radar_ingest` | both active |

**`RELEASE-RECORD-VC1.md` names `1f8016c` as deployed; it is stale.** The
target is at `4221196`, which is what the handoff already suspected. Recorded
here so the next reader stops having to rediscover it.

### Cardinalities (approximate, from `information_schema`, cheap)

| Table | Rows | Size |
| --- | --- | --- |
| `radar_bucket_sources` | **9,333,403** | 1,961 MB |
| `radar_daily_closes` | 5,678,006 | 850 MB |
| `radar_buckets` | 1,257,051 | 246 MB |
| `radar_mention_events` | 1,153,330 | 512 MB |
| `radar_mentions` | 267,766 | 62 MB |
| `radar_posts` | 212,985 | 141 MB |
| `radar_quotes` | 110,742 | 27 MB |
| `radar_ticker_universe` | 12,415 | 2 MB |

### The 24h window, exactly

| Measure | Value |
| --- | --- |
| Scored bucket-source rows in the window | **405,582** |
| Distinct tickers | **5,505** |
| `(ticker, source)` groups the aggregate produces | **51,255** |

### Indexes on `radar_bucket_sources`

| Index | Columns, in order |
| --- | --- |
| `PRIMARY` | `ticker`, `bucket_start`, `source` |
| `ix_radar_bucket_sources_coverage` | `source`, `status`, `bucket_start` |
| `ix_radar_bucket_sources_start` | `bucket_start`, `source` |

The pass-one aggregate filters a `bucket_start` RANGE plus `source IN (...)`
plus `mention_z IS NOT NULL`, and groups by `(ticker, source)`. A range on the
leading column of `ix_..._start` cannot also order the group, so the group is
a sort or a temporary table over the matched rows — 405,582 of them at 24h.
That is a plausible mechanism and is **not yet proven**; the plan says to
establish the plan before moving anything.

### Measured: the pass-one aggregate alone

One run per window, on the target, serially.

| Window | Aggregate wall time |
| --- | --- |
| 4h | **0.32 s** |
| 12h | **1.66 s** |
| 24h | **2.46 s** |

**This does not yet explain the reported wait.** It scales the right way with
the window, and 12h/24h are where the owner reports pain — but 2.46 s is not
"unusable". Something else carries the rest, and PERF1 does not get to guess
which: the remaining suspects are listed below, unproven.

### What the code already records, and what has changed under it

These are prior measurements written into the source, not mine. Every one of
them was taken at a smaller data volume than today's:

- `leaderboard.py`: *"3,497 tickers have a scored bucket in a 24h window and
  41 clear the floor"* (2026-08-24). Today that first number is **5,505**. If
  the ratio holds, pass two enriches a few dozen tickers and is cheap — which
  is why pass two is not currently the prime suspect.
- `leaderboard.py`: asking for voice counts on all tickers rather than only
  those at or above `MIN_MENTIONS` was *"3.3s of an 8s build"* (2026-09-01).
  So an 8-second build was already the baseline six weeks ago.
- `journal.py`: the forced index on the voice query, *"7.53s planner-chosen
  against 0.17s forced"* (2026-09-04), taken when Arctic Shift had brought the
  journal to ~700k rows. **It now holds 1,153,330.** The standing note on this
  hint is to re-measure it after volume changes. That re-measurement is
  exactly what is blocked below.

## Measured locally: the SHAPE of the work

Query counts and code paths are volume-independent -- an N+1 is an N+1 at any
table size -- so this ran against the seeded B1 database (31,892 bucket rows
against the target's 9.3M). **The timings below are not production scale and
are not offered as such.** Only the counts carry.

| Window | tickers with a scored bucket | survivors | queries in `board.build` |
| --- | --- | --- | --- |
| 4h | 14 | 13 | **11** |
| 12h | 14 | 13 | **11** |
| 24h | 14 | 14 | **11** |

**Eleven queries, and the number does not move with the window.** That is a
real negative result and it rules a whole class of cause out: there is no
N+1 in the board path, no per-row lookup, nothing that multiplies with the
candidate count. `_entries` adds three or four statements, not fifty. The cost
is therefore inside individual statements and scales with the ROWS each one
touches, not with how many times they run.

That matches the target measurement exactly: one aggregate, 405,582 rows,
2.46s.

## Measured locally: two things the brief asked about, confirmed by reading

**The client gives up at eight seconds.** `static/radar/src/api.ts:15`,
`TIMEOUT_MS = 8000`, aborted through an `AbortController`. Past that the
reader does not get a slow board, they get the error string *"The board did
not answer in time."* The journal's own index-hint comment records this
happening before: the planner's 7.53s choice *"put the 12h and 24h boards past
the island's 8s timeout, so the reader saw ... instead of a board."*

So "unusable" may not be a long wait at all. It may be a failure, and the
threshold is 8 seconds.

**The 60-second board cache builds outside its own lock.**
`features/radar/routes/api.py:446-469`: `BOARD_TTL` is 60 seconds, the read is
taken under `_board_lock` and the write is taken under `_board_lock`, but the
BUILD happens between them, unlocked. Two readers missing the same key
therefore build the same board twice, concurrently. With
`gunicorn --workers 2` there are also two independent copies of the cache, so
a cold key can be built up to twice per worker-pair. Not yet measured under
load; recorded as a mechanism with its line numbers.

## P0 CONCLUSION — the bottleneck, proven

Every figure below is a single serial run on the target, read-only.

### Where the 24h board's SQL time goes

208 tickers clear `MIN_MENTIONS` at 24h, so the pass-two reads were timed
against that list — an upper bound on the survivor set.

| Query | Rows it touches | Wall |
| --- | --- | --- |
| **pass-one aggregate** | 405,582 → 51,255 groups | **2.46 s** |
| latest quote per ticker (window function) | 110,742 table | 0.83 s |
| sigma daily closes, 780 days | 140,676 | 0.64 s |
| voice counts, app's `IN`-list shape | 563,744 in window | 0.54 s |
| `_entries` hourly buckets | — | 0.31 s |
| moves in window | — | 0.12 s |
| **measured subtotal, 6 of 13 statements** | | **≈ 4.90 s** |

Add the seven smaller statements, the Python that materialises 140,676 close
rows and 51,255 groups, and serialization, and an 8-second client abort is
not a surprise — **the owner confirms hitting it regularly on 12h/24h.**

### The mechanism

```
EXPLAIN, 24h:  type ALL   key NULL   rows 2,912,959   Using temporary; Using filesort
EXPLAIN,  4h:  type range key ix_radar_bucket_sources_start  rows 80,369
```

**At 4h the planner uses the `bucket_start` index. At 24h it abandons it and
full-scans all 9.3M rows of a 1,961 MB table**, then builds a temporary table
and filesorts to satisfy `GROUP BY ticker, source`.

It is right to. Forced back onto the range index at 24h the query is **slower,
3.25 s against 2.46 s** — because `ix_radar_bucket_sources_start` is
`(bucket_start, source)` and carries none of `mention_z`, `mention_count`,
`expected`, `variance`, `distinct_authors`, `distinct_text_ratio`,
`baseline_days` or `status`. Every one of the 405,582 range hits then needs a
heap lookup. Around 4% selectivity that stops being worth it, which is exactly
where 24h sits (405,582 / 9,333,403 = 4.3%) and 4h does not (0.9%).

**This is why the pain is specific to 12h and 24h.** It is not a gradual
slope; it is a plan flip.

### What this rules out

- **Not an N+1.** 13 statements at 4h, 12h and 24h alike.
- **Not the voice query.** 0.54 s in the app's real shape. A JOIN-shaped proxy
  measured 3.67 s and would have sent this in the wrong direction — the app's
  `IN`-list form with its forced index is still healthy at 1.15M rows.
- **Not pass-two enrichment per se.** 208 tickers, sub-second reads.

### The candidate fix, not yet proven

A **covering index** carrying every column the aggregate touches would make
the range scan index-only, removing both the heap lookups and the planner's
reason to give up on it. Whether it beats the full scan — and what it costs in
write throughput on a table the ingest appends to constantly — has to be
measured on a production-scale local copy. **Creating an index on the target
is not authorized by this brief and has not been done.**

Alternatives to measure against it: pushing the eligibility floor into the
aggregate so fewer groups materialise, and a per-window rollup. The brief is
explicit that this is a choice to justify with evidence.

### Ruling from the owner, 2026-09-10

Hitting the 8-second abort is the SYMPTOM, not the thing to fix: *"nothing
should ever take 8 seconds."* The timeout does not move. PERF1's targets
stand — cold p95 <= 2 s — and the aggregate alone currently exceeds that.

## Blocked, and why

Two diagnostic commands were refused by this session's command classifier:

1. **Piping a local profiling script to the target's Python** over ssh, to
   time `board.build`, `build_rows` and `_chatter_survivors` separately with a
   SQL counter attached. This is the single most decisive P0 measurement.
2. **A timed run of the voice-count query** with its `FORCE INDEX` hint and a
   subquery selecting the `worth_asking` tickers.

Both are read-only. Neither was retried or routed around. The refusals are
recorded rather than worked past, and the decision belongs to the owner.

## Unresolved, and the next action

The bottleneck is **not proven**. The aggregate is measured and real; the
remaining candidates, in the order the evidence points:

1. **`journal.distinct_voice_counts` at 1.15M journal rows**, against a forced
   index last measured at ~700k. This is now the leading suspect by
   elimination: the aggregate accounts for 2.46s of a budget that fails at
   8s, the query count is flat, and this is the only other statement known to
   have been near-catastrophic when the planner got it wrong.
2. `_entries` — hourly counts, prices, triplets and tones for the rows that
   survive the limit.
3. `routes/api.py`'s 60-second per-process board cache: with **two** gunicorn
   workers there are two copies of it, builds run outside the lock, and the
   TTL starts at request time — so concurrent misses can duplicate a whole
   build.
4. The frontend: cancellation, redundant requests, refreshes and
   stale-response races.

**Next action: the owner decides the two questions in the return, then P0
finishes against a production-scale local database.** Nothing is implemented
and no fix is proposed on the evidence gathered so far.

## Confirmed on the target, without touching its schema

The brief requires a plan-shaped finding to be confirmed against the target's
own planner before it is believed. MariaDB confirmed it, with no DDL, by
exploiting the fact that InnoDB carries the primary key inside every secondary
index — so a query selecting only `ticker`, `source` and `bucket_start` over
the same 24h range can already be served index-only:

| Variant, same 24h range and same GROUP BY | Plan | Wall |
| --- | --- | --- |
| the real query, eight payload columns | `ALL`, key NULL, full scan | **2.46 s** |
| index-only (columns `ix_..._start` already carries) | `range`, **`Using index`** | **1.19 s** |

**The heap lookups are the reason the planner gives up.** Given an index it can
stay inside, MariaDB uses the range scan and halves the time — while still
paying `Using temporary; Using filesort` separately for the group. That is
two distinct costs, and a fix may address either or both.

1.19 s is the floor this shape can reach on the target without also fixing the
group; it is not a target, it is an anchor for the local trial.

## A second candidate: the board recomputes a sigma that is already stored

`_quote_sigmas` (leaderboard.py:115) calls `history.closes_for(...,
days=HISTORY_DAYS)` — **780 days of daily closes for every survivor**,
measured at 140,676 rows and 0.64 s of SQL for a 208-ticker upper bound, plus
the Python that materialises them, to produce one float per ticker.

`quotes.refresh_sigma` (quotes.py:435) already computes exactly that from the
same read and persists it to `radar_ticker_universe.daily_sigma` /
`sigma_refreshed_at`. On the target: **970 of 12,599 rows carry one**, newest
`2026-09-10 00:53`.

Not a free win, and the reason it was not already done is in the source: a
company-level sigma "is not evidence about its Xetra listing", so
`_quote_sigmas` keys by quote identity while the stored column is
company-level. For `market='us'` — the default board — `refresh_sigma`'s own
call uses the same default, so the two coincide. A German board, and any
ticker among the 11,629 without a stored value, would still need the read.

Measured against the other candidates in the local trial, not assumed.

## RETRACTION — the coverage query is not slow

An earlier turn reported `SELECT DISTINCT bucket_start` at **3.94 s** and
called it a second pathological query. **That was wrong, and it was my own
measurement error.**

The query I timed omitted `status IN ('ok','truncated')`. The shipped query in
`coverage.py:_scan` includes it — and that predicate is exactly what lets
`ix_radar_bucket_sources_coverage` `(source, status, bucket_start)` use all
three of its columns. Without it the range cannot be reached and the scan runs
the whole index; with it, the index works as designed.

Measured with the real shape, on the target:

| Coverage query, real shape | Wall |
| --- | --- |
| forced, as shipped | **0.47 s** |
| planner left alone | 0.50 s |

**The `FORCE INDEX` hint is correct and the query is healthy.** Nothing to fix.

This is the second time a hand-written proxy misled this investigation — the
voice query was the first, at 3.67 s as a JOIN against 0.54 s in its real
`IN`-list shape. Both times the correction came from matching the source. No
query gets reported here again unless its shape was taken from the code.

## Also retracted: that the measured SQL explains the timeout

An earlier turn totalled six statements at ~4.9 s and let it imply the 8-second
abort. It did not: 4.9 s is not 8 s, seven statements were unmeasured, Python
was unmeasured, and the pass-two figures used a 208-ticker upper bound. The
production-scale profile below is what actually settles it.

## THE MEASUREMENT — full board build at production scale

`personal_apps_radar_perf1`, cold, MySQL 8.0.46. One run per window.

| Window | `board.build` wall | SQL | Python | **the pass-one aggregate** | survivors |
| --- | --- | --- | --- | --- | --- |
| 4h | ~7.5 s | 7.2 s | 1.61 s | **5.92 s** | 13 |
| 12h | 14.1 s | 13.6 s | 0.48 s | **11.97 s** | 988 |
| 24h | **19.6 s** | 19.3 s | 0.27 s | **17.03 s** | 78 |

**One statement is 88% of the 24h build.** Every other query is under 2.2 s and
most are under 0.2 s. Python is negligible. There is no pile of small costs —
there is one query.

The second-largest at 24h is the voice count at 2.12 s, an order of magnitude
behind, and it is healthy in its real shape on the target.

### How this fixture differs from the target, stated plainly

| | target | fixture |
| --- | --- | --- |
| `radar_bucket_sources` | 9,333,403 | **9,269,184** |
| ...in the 24h window | 405,582 | 369,424 |
| distinct tickers, 24h | 5,505 | **5,505** |
| `radar_quotes` | 110,742 | 110,400 |
| `radar_daily_closes` | 5,678,006 | 3,071,790 |
| `radar_mention_events` | 1,153,330 | 576,000 |
| engine | MariaDB 10.11.14 | MySQL 8.0.46 |
| buffer pool state | warm, 0 physical reads measured | cold |

The table the bottleneck lives in is reproduced to within 0.7%. Closes and
journal are short and their queries are correspondingly optimistic here — both
were measured directly on the target instead (0.64 s and 0.54 s).

**Absolute times are NOT comparable between the two.** The aggregate is 17.0 s
here and 2.46 s on the target: different engine, different hardware, cold
against a warm pool. What transfers is the plan pathology and the ratio — one
query dominating everything else — and that is identical in both.

Survivor counts are a fixture artifact: 988 at 12h against 78 at 24h is not
monotonic and does not match the target's ~41, because the synthetic mention
distribution is uniform where the real one is not. It does not affect the
aggregate, which runs before the floor.

## P1 — THE FIX, and the candidates it beat

`migrations/versions/c4e17b90d3f2_cover_the_board_aggregate.py`, one index:

```
ix_radar_bucket_sources_agg (bucket_start, source, ticker, mention_z,
    mention_count, expected, variance, distinct_authors,
    distinct_text_ratio, baseline_days, status)
```

Every column `leaderboard._aggregate` touches, so the range scan is index-only
and the planner has no reason to abandon it.

### The aggregate alone, candidates measured against each other

Median of 5 serial samples, production-scale copy.

| | 4h | 12h | **24h** |
| --- | --- | --- | --- |
| baseline, the indexes the target has | 3.30 s | 5.18 s | **12.34 s** |
| **A — covering, range-leading** | 0.72 s | 1.39 s | **1.79 s** |
| A and B together | 0.72 s | 1.38 s | 1.83 s |
| B — covering, group-leading | 3.01 s | 4.50 s | 6.55 s |

**B was rejected on evidence.** Leading with `(ticker, source)` removes the
GROUP BY's filesort but loses the `bucket_start` range, and it is 3.7x worse
than A at 24h. Adding it alongside A changes nothing measurable. One index.

### End to end, through `board.build`

Median of 3, same dataset, same fixed input time, same process.

| Window | before | after | |
| --- | --- | --- | --- |
| 4h | 4.87 s | **2.94 s** | 1.7x |
| 12h | 5.02 s | **1.89 s** | 2.7x |
| **24h** | **15.05 s** | **2.09 s** | **7.2x** |

### What it costs

| | |
| --- | --- |
| index build | 44 s on 9.27M rows, `ALGORITHM=INPLACE, LOCK=NONE` |
| added index bytes | ~500 MB (table's indexes go to 961 MB) |
| write cost, 20,000 bucket rows | 0.52 s before, **0.44 s** after — no detectable penalty |

The added bytes are worth stating plainly for the deployment decision: the
target holds 3,871 MB of radar data against a 2,500 MB buffer pool, so it is
already over-subscribed. Against that, the board's own working set SHRINKS —
it reads an index instead of scanning a 1,961 MB table — so the expected
effect on the pool is favourable. Not measured under the target's memory
pressure, and it should be watched after any deployment.

### Correctness

- **Payload parity**: `board.build` output hashed with and without the index
  at 4h, 12h and 24h — **identical, all three**. It is a read optimisation and
  changes no value.
- **Migration rehearsed both ways**: upgrade creates it, downgrade drops it,
  upgrade restores. Recovery proven, not asserted.
- **148 backend tests pass** across `test_radar_leaderboard`,
  `test_radar_detail`, `test_radar_coverage` and `test_radar_board`.
- The `ALGORITHM=INPLACE, LOCK=NONE` clause was rehearsed on MySQL 8.0.46.
  The target runs MariaDB 10.11 and creating an index there to test the clause
  is not authorized, so the migration **falls back to a plain CREATE INDEX**
  if the engine rejects it. Identical index either way; only the concurrency
  of the build differs.

### Not done, and why

- **Nothing was changed on the target.** No index, no configuration, no
  restart, no code. Deployment is not authorized by this brief.
- Whether MariaDB's planner picks this index up as MySQL's does is **not
  proven** and cannot be without creating it there. The mechanism is the same
  and MariaDB was already shown to prefer a range scan when it can stay inside
  an index (1.19 s against 2.46 s), which is the behaviour this index exists
  to trigger.
- The persisted-sigma candidate was **not implemented**. At 0.64 s it is an
  order of magnitude behind the aggregate, and with the aggregate fixed the
  24h build already meets the 2 s target. It stays recorded as the next
  candidate if more is wanted.

---

## RETRACTION — the first P1 evidence was wrong, and how

An independent read-only review of `772e170` returned nine confirmed defects.
Three of them invalidate the headline. They are recorded here in full rather
than quietly corrected, because the same class of error had already been
retracted twice in this file and clearly needed naming rather than fixing.

### 1. The migration could never have built the index online

`CREATE INDEX ... (cols) ALGORITHM=INPLACE, LOCK=NONE` is a **parse error**.
The comma-separated form belongs to `ALTER TABLE`; `CREATE INDEX` takes those
options space-separated. Verified on both engines, without executing anything:

```
local MySQL 8.0.46, PREPARE:  comma form  FAILS (1064)   space form  PARSES
target MariaDB 10.11, PREPARE: ERROR 1064 ... near ' LOCK=NONE'
```

The migration wrapped that statement in `try/except Exception` with a plain
`CREATE INDEX` fallback, so the broken branch **always** failed and the
fallback **always** ran. The index would still have been created — with a
lock, on a table the ingest daemon writes to continuously. The commit's
"Builds in 44 seconds, in place, so ingest keeps writing" was false, and the
try/except is precisely why no rehearsal could ever have caught it.

Worse, `tests/test_radar_migration.py` already encodes the rule this broke:
one atomic DDL per direction, because MariaDB commits DDL even when a later
statement in the same migration fails. The migration is now a single
`ALTER TABLE` per direction with no exception handling, both directions
parse-checked on the target's own MariaDB, and it is registered in that guard
test.

### 2. Every local timing was disk-bound, so every ratio was an artifact

The local server ran a **128 MB** buffer pool against a **1,798 MB** table.
The target runs **2,500 MB**. Nothing on the local box could stay resident, so
the "before" numbers measured disk, not the planner. With the pool raised to
2,560 MB and nothing else changed:

| the aggregate, 24h | |
| --- | --- |
| as first reported (128 MB pool, proxy query) | 12.34 s |
| the same statement, pool matched, real query | **3.32 s** |

The target's own measurement was 2.46 s all along, and the ledger had it. The
discrepancy should have been read as a broken fixture, not as headroom.

### 3. The fixture answered a question production never asks

`config.expand_sources` expands `reddit` to the 34 real subreddit names.
The generator wrote `reddit:sub00 … reddit:sub32`. So `source IN (...)`
matched **only bluesky and fourchan — 3,767,952 of 9,269,184 rows, 41%**.
Every end-to-end number was taken over a workload less than half the size of
the one being modelled.

Renaming 5.5M rows of a primary-key column was measured at roughly two hours,
so instead the scripts now take the source list **from the fixture**, which
gives the same 100% coverage and the same 35-name `IN` list production has.
What that does not reproduce is string length — the fixture's names average
12 bytes against production's ~17 — so the target's copy of this index will be
somewhat larger than the figure measured here. Every script now asserts the
coverage before it measures anything.

### 4. The candidate that should have won was never on the list

The candidate trial ran a **hand-written** query that omitted
`source IN (...)`. That predicate is the entire motivation for a
source-leading index, so candidate C was structurally invisible. This file had
already written the rule — "no query gets reported here again unless its shape
was taken from the code" — and the commit broke it anyway. The trial now
builds its statement from `leaderboard`'s own SQLAlchemy expression, and
`explain_check.py` records what the real code paths send through a
`before_cursor_execute` listener rather than reconstructing anything.

### 5. The write-cost test measured an empty B-tree

It inserted 20,000 rows at `utcnow() + 400 days`, which lands in `p_max`.
Indexes on a partitioned table are local per partition, so those inserts
maintained an index with zero rows in it. "No detectable write penalty" was
unsupported — the *after* being faster than the *before* was the tell. The
probe now writes into the live partition, on keys that already exist, the way
ingest's `ON DUPLICATE KEY UPDATE` does.

### 6. Three claims had no artifact behind them

Payload parity, the migration rehearsal, and "~500 MB of added index" were all
stated as measured. The first two were run interactively and left nothing
reproducible; the third was a subtraction from a number that was never
recorded, taken from `INDEX_LENGTH`, which is served from stale persistent
statistics. Parity is now hashed in `acceptance.py`, and index size is read
from `mysql.innodb_index_stats` after `ANALYZE TABLE`, before and after.

### 7. Smaller, all confirmed

- `models.py` did not declare the index, so the next `flask db migrate` would
  have autogenerated a `drop_index` for it. Declared now.
- The status table at the top of this file still read "P1 — Not started"
  380 lines below a finished P1.
- The reported 4% selectivity threshold used the whole table as the
  denominator. Both windows **prune to one partition** of 2,874,477 rows, so
  the real figures are ~3.6% (4h, range) and ~14.1% (24h, scan).
- `ix_radar_bucket_sources_start (bucket_start, source)` is a strict prefix of
  the new index and is now redundant for the aggregate. Dropping it is the
  single largest saving available against a buffer pool the target has already
  over-subscribed — but `scoring.py` alone touches this table in 36 places and
  none of that is measured here, so it is recorded as a recommendation and
  deliberately left out of this patch.

---

## P1 AND P2 — the corrected evidence

> **Two rows of the before/after table below were corrected again after this
> section was written.** The single-flight cannot fire on the target as
> deployed, so the "threaded workers only" rows are NOT the production
> outcome; the rows marked THE PRODUCTION SHAPE are. And the write cost was
> re-measured on the write ingest actually performs. See the CORRECTION
> sections at the end of this file.

Everything below was measured after the retraction above: real query shape,
buffer pool matched to the target at 2560 MB, a source list covering all
9,269,184 fixture rows, `segments=()` (**All companies**, the case the owner
reports — not `parse_query`'s four-segment default), `market='us'` pinned, and
20 serial samples per critical window.

**The absolute numbers are this desktop's, not the target's.** The one
statement measured on both is the aggregate at 24h: 2.46s on the target
against 3.32s here, so the target is roughly 25% faster on the part that can
be compared. Ratios and mechanisms transfer; seconds do not.

### It was never one slow query -- and the concurrency answer is retracted

> **This heading used to read "THE BOTTLENECK, PROVEN". It was not proven.**
> The pair below is two THREADS in one process, so roughly a second of Python
> per build serialised on the GIL. Production runs two single-threaded SYNC
> worker processes, which do not. The pair is CHEAPER there, the in-process
> single-flight cannot fire there at all, and this table is therefore evidence
> about threads, not about the owner's timeout. Kept for the record, not as a
> finding.

| 24h, All companies | | |
| --- | --- | --- |
| one reader, 20 serial samples | median **5.38s**, p95 5.72s, max 5.77s | stands |
| two readers at once, **two threads in one process** | 7.85s and 7.92s | **not the production shape** |
| the island's abort (`static/radar/src/api.ts`) | **8.00s** | stands |

What stands: a serial 24h build is ~5.4s on this fixture, ~4.5s with the held
index, and the target is roughly 25% faster on the one statement measurable on
both. That is under the 8s abort with little room, and far over the 2s target.
What crosses the abort on the target is **unidentified**.

### Two changes

1. **`c4e17b90d3f2`** — one covering index, `ix_radar_bucket_sources_agg`.
2. **Per-key single-flight in `_build_board`** — the second reader waits for
   the first's board instead of building a second copy of it.

### The candidates, real query shape, pool matched

Median of 5. The proxy that hid candidate C is described in the retraction.

| the aggregate alone | 4h | 12h | 24h |
| --- | --- | --- | --- |
| baseline, the indexes the target has | 0.91s | 2.23s | 3.32s |
| **A range-leading (shipped)** | 0.86s | **1.83s** | **2.29s** |
| C source-leading | 0.84s | 1.92s | 2.58s |
| B group-leading | 0.89s | 2.25s | 3.31s — no effect |

B is inert: the optimizer never picks it. C is real but loses to A at every
window. One index.

### The whole board, before and after

| | before | after |
| --- | --- | --- |
| 12h, one reader, n=20 | median 4.69s, p95 6.53s | **median 4.10s, p95 4.39s** |
| 24h, one reader, n=20 | median 5.38s, p95 5.72s | **median 4.50s, p95 4.72s** |
| 12h, two readers, **single-flight bypassed, two threads** | 7.55 / 7.45s | 7.37 / 7.46s |
| 24h, two readers, **single-flight bypassed, two threads** | 7.85 / 7.92s | 6.85 / 6.98s |
| 12h, two readers, endpoint path — **threaded workers only** | 4.58 / 4.58s | 4.22 / 4.22s |
| 24h, two readers, endpoint path — **threaded workers only** | 5.23 / 5.23s | 4.50 / 4.50s |
| six filter changes back to back | 34.54s, worst 5.41s | 32.26s, worst 5.41s |
| worst anything measured here | **7.92s** | **7.46s** |

**Every two-reader row above is two threads in one process. None of them is
the production shape**, which is two separate sync processes on separate
cores; those rows were labelled "THE PRODUCTION SHAPE" here and that label is
withdrawn. The two-process pair is cheaper than the thread pair, by an amount
this workstream never measured.

What is left that transfers: **the index is worth ~0.9s per build**, serially,
which is the one number in this table that does not depend on the worker model.
The single-flight buys nothing on the target as configured, and PERF2 replaces
it rather than waiting for `--threads`.

### The single-flight, verified rather than assumed

Five pairs per window through `_build_board` with the shipped code:

| | slower reader, median | duplicate builds |
| --- | --- | --- |
| 12h | 3.99s | **0 / 5** |
| 24h | 3.96s | **0 / 5** |

Two defects were found in this code by measuring it rather than reading it:

- **The cache was written AFTER the waiters were woken.** A waiter wakes on
  the event and immediately reads the cache, so it could wake to an empty one
  and build a duplicate anyway — intermittently, and only under load. The
  first test passed on scheduling luck. Fixed by caching inside the `try`,
  before the `finally` that wakes; a test now asserts that ordering directly
  rather than asserting a build count.
- **`BUILD_WAIT` was 10s and a 33s build defeated it.** A pathological build
  (a cold 128 MB pool) pushed the waiter past its timeout and it built a
  second copy — adding load at the one moment the server was already failing.
  Raised to 30s: if a build is slower than the client's own abort then both
  readers have lost anyway, and duplicating makes every later request worse.
  The timeout now only rescues a thread that will never finish at all.

### Every plan, captured from the running code

Not reconstructed — recorded through a `before_cursor_execute` listener while
the real code paths ran, then EXPLAINed with their own parameters.

| the read | plan, index present |
| --- | --- |
| the pass-one aggregate | `key=ix_..._agg` **`Using index`** — index-only, filesort gone |
| coverage probe | `key=ix_..._coverage` — its FORCE INDEX holds, unchanged |
| `build_pinned`, watched tickers | `key=PRIMARY` rows=1100 — unchanged |
| `detail.daily_counts` | `key=PRIMARY` rows=9042 — unchanged |

That closes the review's one SUSPECTED finding: the new index does **not**
pull the small-ticker paths off `PRIMARY`.

### What it costs

| | |
| --- | --- |
| index build | **59s**, `ALGORITHM=INPLACE, LOCK=NONE`, ingest keeps writing |
| added index | **639 MB** (secondary indexes 1047 MB to 1686 MB) |
| writes — see the correction below; **+50%**, not the +12% first reported | |
| payload parity | **IDENTICAL** at 4h, 12h and 24h |
| tests | **227 passed**, 4 pre-existing environmental failures |

The four failures are the same four with this patch stashed: this worktree has
no `npm run build`, so there is no Vite manifest and the page routes 404.

**A cost worth stating plainly.** With the index the fixture's table plus
indexes is 3484 MB against a 2560 MB pool, so the working set no longer fits
and a cold first pair shows up in the tail — a reproducible ~14s outlier on
the first 12h pair of a run. The target is already worse off: 3871 MB of radar
data against 2500 MB. Per-index sizes here:

| | |
| --- | --- |
| PRIMARY | 1844 MB |
| `ix_radar_bucket_sources_agg` (new) | 639 MB |
| `ix_radar_bucket_sources_coverage` | 590 MB |
| `ix_radar_bucket_sources_start` | **458 MB** |

`ix_radar_bucket_sources_start (bucket_start, source)` is a strict prefix of
the new index, and no read the board performs uses it any more. Dropping it
would reclaim 458 MB of the 639 MB added — a net cost of 181 MB rather than
639. It is NOT in this patch: `scoring.py` touches this table in 36 places on
the ingest path and none of that is measured here. Recommended, measured, and
deferred to a decision.

### What this does NOT do

The board is still built while the reader waits. **A 4-5 second page is not a
fast page**, and no index will change that, because the work still happens on
the request. The aggregate is only ~40% of the build; the sigma, coverage and
voice reads plus roughly a second of Python are the rest.

Getting it genuinely fast means taking the build off the request path —
warming the popular boards in the background before the 60s TTL expires (the
smallest change, and the board is already viewer-invariant and already served
up to 60s stale), or precomputing the ranked list when ingest advances the
buckets every 15 minutes. Neither is in this brief; both are design decisions.

### Not measured, and why

- **The target's own end-to-end build.** Running code on the target
  (`python -c` over ssh) is refused by the session's command classifier, and
  was not routed around. Plain ssh reads, `mariadb -e`, `EXPLAIN` and
  `PREPARE` all work and were used.
- **Production has no latency telemetry to read instead**: nginx logs no
  `$request_time`, gunicorn runs with no access log, the slow query log is OFF
  with `long_query_time` at 10s, and `performance_schema` is OFF. Enabling any
  of it is a target configuration change this brief does not authorize.
- **Cross-worker duplication.** The single-flight is per process and the
  target runs two workers, so two readers in DIFFERENT workers still build
  twice. Fixing that needs shared state and is not attempted here.

---

## CORRECTION — the single-flight is inert on the target as deployed

Checked on the target after `af3feb4` was written, read-only:

```
PID     NLWP  COMMAND
121328     2  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (master)
121352     1  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (worker)
121355     1  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (worker)
```

`NLWP 1` on both workers, and there is no `gunicorn.conf.py` in the working
directory. They are **sync workers: single-threaded processes serving one
request at a time**. Two concurrent readers therefore land in two separate
PROCESSES, and the single-flight coalesces threads within one process. **It
cannot fire in production as the service is configured today.**

That invalidates the claim in `af3feb4`'s message that this is "the bigger
half" of the abort. It is not the bigger half; as deployed it is none of it.

### It also means the concurrency measurement over-stated the penalty

The `7.85s / 7.92s` pair was two THREADS in one process, so the roughly one
second of Python per build serialised on the GIL. Two processes on six vCPUs
do not serialise: each gets a core, and only the database work contends. The
concurrent pair in production is therefore **cheaper** than that number,
probably nearer 6-6.5s than 7.9s.

So concurrency is no longer established as *the* thing that crosses eight
seconds. What survives:

- a serial 24h build is ~5.4s on this fixture, and the target is ~25% faster
  on the one statement measurable on both, so call it ~4.5-5s there --
  **under the abort, without much room**
- the index removes ~0.9s of that, measured
- anything that adds ~3s tips it over, and the target has several candidates:
  3871 MB of radar data against a 2500 MB buffer pool, `radar_ingest` writing
  continuously, and coc_stats running three more gunicorn workers against the
  same MariaDB

Which of those it is cannot be settled from here, because the target has no
latency telemetry and running code on it is refused by the session's command
classifier.

### What the single-flight is still worth

It is correct code and it starts working the moment the service runs threaded
workers. That change is worth making for a reason that has nothing to do with
this patch: **with two sync workers, two five-second board builds occupy both
workers and block the whole of personal_apps**, not just Radar. `--threads 4`
on the unit would fix that and switch the single-flight on at the same time.

That is a target service-configuration change. It is not authorized by this
brief and has not been made.

Cross-process coalescing -- one board built once across both workers -- needs
shared state (a table, or a cache server) and is the same work as the warm- or
precomputed-board direction recommended above.

---

## SECOND REVIEW — what it found, and what it cost me

An independent read-only review of the concurrency patch reached the worker-
model conclusion above on its own, and then found three defects in the
single-flight by **executing** it rather than reading it. Two were real bugs
and one was a test that did not test what its name claimed.

### 1. A failed build started a herd

A woken waiter fell through and built **without claiming the key**, so every
waiter built, and each new arrival — finding `_board_builds` empty — started
another. The reviewer measured it:

```
one failing builder + 4 waiters -> 5 builds ran, 1 raised
(a single-flight should produce 2: the failure and ONE retry)
```

Firing precisely when the database is already unhealthy. `_build_board` now
loops back to the claim instead of falling through: the first waiter to wake
claims the retry and the rest wait on it. Bounded at two rounds so a
deterministically failing build cannot serialise every waiter behind
`BUILD_WAIT` apiece.

### 2. A hung build poisoned its key permanently

A build that neither returns nor raises never runs its `finally`, so its claim
stood forever and **every later reader of that selection paid the full
`BUILD_WAIT`** — indefinitely, and strictly worse than the code it replaced,
which cost only the hung request. The timeout path now clears that claim,
identity-checked so it can never clear a claim some other thread has since
made.

`BUILD_WAIT` came down from 30s to **8.0s**, matching the island's own abort.
The 30s reasoning — "a slow build should never be duplicated" — was right
about the board and wrong about everything else the waiter holds:
`login_required` has already checked a user out of the pool, so a parked
waiter holds one of fifteen connections and an open InnoDB read view against
a table `radar_ingest` writes to continuously.

### 3. The test I trusted was the one that did not work

`test_the_board_is_cached_before_the_waiters_are_woken` instrumented
`_board_builds.pop`, which happens after the cache write in **both** the
correct and the broken ordering. The reviewer reintroduced the bug and ran it
twenty times: it passed twenty times. The build-count test that `af3feb4`'s
message dismissed as passing "on scheduling luck" is in fact the only one that
ever caught it. Exactly inverted.

It now instruments `Event.set` itself — the thing whose order actually
matters.

### Every test is now mutation-checked

Each defect was put back and the suite re-run. A test that passes against the
bug it is named for is worse than no test, so this is no longer taken on
trust:

```
CAUGHT   cache written AFTER the waiters are woken
CAUGHT   waiter falls through unclaimed (the herd)
CAUGHT   timeout does not clear the dead claim (poisoning)
```

The poisoning test failed to catch its own bug on the first attempt, for a
reason worth keeping: the second reader's board was still in the cache, and a
cache hit never consults the claim. It expires the cache first now.

`conftest.py` clears `_board_builds` alongside `board_cache`; a claim left
behind by a killed builder would otherwise turn every later radar test on that
key into a `BUILD_WAIT` stall.

**229 backend tests pass**, four pre-existing environmental failures (this
worktree has no `npm run build`, so the page routes 404 — the same four with
this patch stashed).

---

## CORRECTION — the write cost was measured on the wrong write

The probe in `acceptance.py` INSERTed 20,000 rows at a `bucket_start` that did
not exist. Every fixture row sits on an exact hour and it wrote at `:30`, so
nothing collided: it measured 20,000 sequential appends at the right edge of a
`bucket_start`-leading B-tree, the cheapest pattern this index has. It claimed
to collide "the way ingest's `ON DUPLICATE KEY UPDATE` does" and did not. That
claim is in `31158f7`'s commit message too, and it is wrong there as well.

The real writers UPDATE columns this index carries — `scoring.py` bulk-updates
`expected`, `variance`, `mention_z` and `baseline_days`; `buckets.py` re-sets
`mention_count`, `distinct_authors`, `distinct_text_ratio` and `status` on the
live bucket every cycle. All eight are in the index, so each update
delete-marks and re-inserts a secondary-index entry instead of appending one.

Re-measured on that write — one bulk `UPDATE` of an indexed column across
16,793 rows that already exist, in the live partition, restored afterwards:

| | median of 3 |
| --- | --- |
| without the index | **0.42s** |
| with the index | **0.63s** |
| | **+50%** |

Roughly four times the penalty first reported. A per-row version of the same
test showed no difference at all (6.68s against 7.15s) because 16,793
separate statements are dominated by round-trip overhead — which is why the
bulk form is the one reported.

**+50% on the scoring pass is the number to weigh against the deployment.**
The pass already runs for tens of minutes.

## CORRECTION — two claims that had no artifact

The CORRECTION section above stated "six vCPUs" and "coc_stats running three
more gunicorn workers" as fact without evidence, in a document whose whole
discipline is that nothing is stated without one. The vCPU count comes from
the VPS build sheet, not from anything measured in this workstream. The
coc_stats workers ARE in the process listing quoted there, and the quote was
simply trimmed too far:

```
121326  gunicorn --workers 3 --bind 127.0.0.1:5000 app:app   (coc_stats)
121328  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (personal_apps)
```

Both apps share one MariaDB. The vCPU figure should be treated as unverified
until someone reads it off the target.
