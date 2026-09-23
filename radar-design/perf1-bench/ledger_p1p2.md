
---

## P1 AND P2 — the corrected evidence

Everything below was measured after the retraction above: real query shape,
buffer pool matched to the target at 2560 MB, a source list covering all
9,269,184 fixture rows, `segments=()` (**All companies**, the case the owner
reports — not `parse_query`'s four-segment default), `market='us'` pinned, and
20 serial samples per critical window.

**The absolute numbers are this desktop's, not the target's.** The one
statement measured on both is the aggregate at 24h: 2.46s on the target
against 3.32s here, so the target is roughly 25% faster on the part that can
be compared. Ratios and mechanisms transfer; seconds do not.

### THE BOTTLENECK: it was never one slow query

| 24h, All companies | |
| --- | --- |
| one reader, 20 serial samples | median **5.38s**, p95 5.72s, max 5.77s |
| **two readers at once** | **7.85s and 7.92s** |
| the island's abort | **8.00s** |

A serial build never reaches the abort. A concurrent pair lands on top of it —
7.92s against 8.00s, which is why the owner hit it *often* rather than
*always*. `_build_board` checked its cache under a lock and then RELEASED the
lock before building, so two readers wanting the same board inside the same
minute both built it, competing for one CPU and one buffer pool.
`gunicorn --workers 2` makes that ordinary: one person and a refresh is
enough.

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
| 12h, two readers duplicating (the old path) | 7.55 / 7.45s | 7.37 / 7.46s |
| 24h, two readers duplicating (the old path) | 7.85 / 7.92s | 6.85 / 6.98s |
| **12h, two readers, endpoint path** | **4.58 / 4.58s** | **4.22 / 4.22s** |
| **24h, two readers, endpoint path** | **5.23 / 5.23s** | **4.50 / 4.50s** |
| six filter changes back to back | 34.54s, worst 5.41s | 32.26s, worst 5.41s |
| worst anything | **7.92s** | **7.46s** |

Read the two "endpoint path" rows against the two "duplicating" rows above
them: that difference is the single-flight, and it is the larger of the two
fixes. The index is worth ~0.9s per build; not duplicating the build is worth
~2.7s at 24h.

Against the true old behaviour — duplicate concurrent builds, no index — the
24h case goes **7.9s to 4.5s**, and the abort has ~3.5s of margin instead of
0.08s.

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
| writes, 20,000 rows into the LIVE partition | 6.17s to **6.91s, +12%** |
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
