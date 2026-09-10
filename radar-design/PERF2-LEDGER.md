# PERF2 progress

Binding plan: `PERF2-PLAN.md`. Binding ruling: `PERF1-CODEX-RULING.md`, also
appended to `CODEX-DECISIONS.md`.

| Item | State |
| --- | --- |
| Isolated continuation established | **Done** — `codex/radar-perf2` off `4221196` |
| PERF1 summaries corrected | **Done** — see below |
| PERF1 benchmark artifacts located and carried | **Done** — `radar-design/perf1-bench/` |
| PERF2 design written | **Done** — `PERF2-PLAN.md` Part I |
| S1 store and payload weight | **Done** — `run_s1_payload.py` |
| S2 cross-process reuse and cold miss | Not started |
| S3 refresh capacity | Not started |
| S4 semantics parity | Not started |
| S5 account isolation | Not started |
| S6 bounded failure | Not started |
| S7 restart, empty, expired | Not started |
| S8 filter switching and browser | Not started |
| S9 ingest contention | Not started |
| T1 worker threading (prepare only) | Not started |
| T2 access-log proposal (prepare only) | Not started |
| Independent read-only review | Not started |
| Deployment | **Not authorized.** Full product implementation follows Codex's review of this return. |

## Workspace

| Fact | Value |
| --- | --- |
| Worktree | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf2` |
| Branch | `codex/radar-perf2` |
| Base | **`4221196`** — the deployed SHA |
| Migration head | `a7c31f0b52d4`, unchanged from production |
| Local database | `personal_apps_radar_perf1` (`PERSONAL_DB_NAME` in this worktree's `.env`) |
| Fixture | 9,272,064 `radar_bucket_sources` rows, verified present on 2026-09-10 |
| Buffer pool | 2560 MB, matching the target, verified on 2026-09-10 |

**Why the base is the deployed SHA and not PERF1's head.** Codex's ruling holds
the index migration and says the next release candidate must exclude it so a
routine `flask db upgrade` cannot apply it by accident. Branching from
`4221196` and carrying PERF1's *documentation* forward does that structurally
rather than by discipline. `codex/radar-perf1` at `691f33a` is untouched and is
the evidence for everything PERF1 measured. `codex/radar-b1` at `6c63959` is
untouched too.

Verified at takeover, before anything was changed: `codex/radar-perf1` at
`691f33a`, twelve commits from `4221196`, working tree clean apart from Codex's
two intentional uncommitted edits to `CODEX-DECISIONS.md` and `HANDOFF.md`.
Both were carried forward into this workspace unmodified; Codex's handoff notice
is still the first thing in `HANDOFF.md`.

## The PERF1 corrections, and what they were

Codex ruled that the return and the leading handoff text still quoted retracted
concurrency conclusions, and that later caveats do not undo a leading claim.
Three places led with it. All three now state the retraction where the claim
was, not below it.

| Document | Was | Now |
| --- | --- | --- |
| `HANDOFF.md`, PERF1 dispatch | "THE BOTTLENECK IS PROVEN, AND IT IS NOT ONE SLOW QUERY", with the 8.02/7.87s pair as the finding | "PERF1 — closed as an investigation, and corrected", leading with what is retracted, then what survives with its limits |
| `PERF1-LEDGER.md`, leading status | "Done" with no disposition | Codex's disposition as a row, and the retraction of the concurrency conclusion above the fold |
| `PERF1-LEDGER.md`, corrected evidence | "THE BOTTLENECK: it was never one slow query" | "It was never one slow query — and the concurrency answer is retracted", with the thread caveat inside the table |
| `PERF1-LEDGER.md`, before/after table | four rows labelled "THE PRODUCTION SHAPE" | every two-reader row labelled as two threads in one process; the "production shape" label withdrawn |

**What was retracted, in one sentence:** the two-reader pair that motivated the
single-flight was two threads in one process, production runs two
single-threaded sync worker processes, so the measurement is evidence about
threads and not about the owner's timeout.

**What survives:** a serial 24h All-companies build is median 5.38 s / p95
5.72 s on the fixture, 4.50 s / 4.72 s with the held index, so the index is
worth about 0.9 s per build and the build still misses the 2 s target by more
than a factor of two. That is the fact PERF2 exists to address.

## The benchmark artifacts, located

Codex's ruling recorded that the Git delta did not contain the profiling and
acceptance scripts the PERF1 ledger cites, and that a search of the PERF1
worktree's scratchpad did not find them.

**Found.** They were in the previous session's own ephemeral scratchpad:

```
C:/Users/michi/AppData/Local/Temp/claude/c--Users-michi-Desktop-CodingStuff/
  a3929e28-aa68-4694-9a01-afcc650a3538/scratchpad/
```

That directory is session-scoped and is not a reachable artifact by any
definition. Thirteen scripts and four supporting files are now carried into
`radar-design/perf1-bench/`, tracked, with `README.md` giving each one's
purpose, the ledger section it backs, and the full prerequisites — the fixture
database, its row count, and the 2560 MB buffer pool without which every ratio
in that ledger is an artifact.

**Repeatability is claimed only to that extent**: the scripts exist, they name
their database, and their prerequisites are written down. They have not been
re-run in this workstream, and no claim here rests on re-running them.

---

## Measurements

Every entry names the script that produced it, the database it ran against and
the buffer pool that run reported. **Every run below reported
`personal_apps_radar_perf1`, 9,272,064 `radar_bucket_sources` rows and a
2560 MB buffer pool**; each script asserts the pool and refuses to continue
below 2000 MB, so a number here cannot have come from a 128 MB run.

**The engine is MySQL 8.0.46. The target is MariaDB 10.11.14.** The mechanism
transfers; the seconds do not. Every plan-shaped finding says so where it
appears.

### The one substitution every run makes, and why

The plan spells the warm set's source selection `('bluesky', 'fourchan',
'reddit')`. On this fixture the root `reddit` expands through
`config.REDDIT_SUBS` to thirty-five real subreddit names of which the fixture
holds **three** — it stores `reddit:sub03`..`reddit:sub32` as placeholders.
PERF1 retracted a whole round of evidence for exactly this: the `IN (...)`
then matched 41% of the rows.

So every run here spells "every root" as the fixture's own `SELECT DISTINCT
source` — thirty-five names, asserted in `env_check.fixture_sources` to cover
100% of the rows, rooting to exactly `['bluesky', 'fourchan', 'reddit']` in
the payload. `perf1-bench/acceptance.py` did the same thing for the same
reason.

---

### S1 — the store, and what a board weighs

`radar-design/perf2-spike/run_s1_payload.py`, one run, 2026-09-10.

**Step 1 — the table and the key exist and round-trip.** `enqueue` →
`claim` (fence 1) → build → `publish` → `read` → `decompress` returned a
payload **identical** to the one built, asserted in the script.

| | |
| --- | --- |
| `key_json`, fixture selection | 644 chars |
| `key_json`, **worst case with production's real source names** | **939 chars** |

Part I.2 specified `VARCHAR(1024)`. It fits — with 85 characters to spare,
which is two more subreddits. **Deviation: the spike's column is
`VARCHAR(2048)`**, because the margin is thinner than the rate at which
`REDDIT_SUBS` has been growing and a key that will not store is a board that
will not build.

**Step 2 — one payload, weighed.** `now` fixed at `2026-09-10T12:00:00`.

| Selection | JSON bytes | zlib-6 bytes | ratio | compress | decompress | json.loads |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1h All companies US | 131,981 | 8,999 | 14.7x | 1.4 ms | 0.2 ms | 1.5 ms |
| 4h All companies US | 156,610 | 11,486 | 13.6x | 1.8 ms | 0.2 ms | 1.8 ms |
| 12h All companies US | 150,508 | **12,640** | 11.9x | 1.9 ms | 0.2 ms | 1.7 ms |
| 24h All companies US | 128,448 | 10,801 | 11.9x | 1.6 ms | 0.2 ms | 1.6 ms |
| 24h default 4 segments US | 64,774 | 6,140 | 10.5x | 0.7 ms | 0.1 ms | 0.8 ms |
| 24h All companies US limit=100 | 138,336 | 11,252 | 12.3x | 2.1 ms | 0.2 ms | 1.9 ms |

**A board is 6–13 KB stored and costs about 2 ms to read back into Python.**
That is the whole of what the store adds to a warm read.

**The build cost beside it, first pass against second in the same process** —
reported apart rather than averaged, because averaging cold into warm is what
PERF1 had to retract:

| Selection | first | second |
| --- | ---: | ---: |
| 1h All companies US | **25,137 ms** | 2,782 ms |
| 4h All companies US | **12,931 ms** | 4,140 ms |
| 12h All companies US | 3,663 ms | 3,608 ms |
| 24h All companies US | 4,265 ms | 4,318 ms |
| 24h default 4 segments US | 4,216 ms | 4,163 ms |
| 24h All companies US limit=100 | 4,330 ms | 4,167 ms |

The 1h and 4h first passes are pages this process had not touched; 12h and 24h
were already warm from the round-trip above. **A cold-page build is five to six
times a warm one**, and S3 pays that on its first sweep.

**Step 3 — what `serialize` costs beyond the board.** The decision Part V.4
asks for.

| Call | median | notes |
| --- | ---: | --- |
| `spend.summary()` | 4.5 ms | two aggregate queries, no memo |
| `llm_sentiment.ops_summary()` | 3.0 ms | no memo |
| `market_data.ops_summary(now)` | **91.2 ms** | memo cleared before each sample |
| `market_data.ops_summary(now)` | 0.0 ms | its own 60-second memo, hit |
| **all three** | **98.7 ms** | per `serialize` |

**Ruling for Part V.4: freeze all three into the stored payload.** 98.7 ms is
20% of the 500 ms warm target for three health readouts, and `market_data` is
91 ms of it. They are *already* accepted as up-to-60-seconds stale by their own
memo, and a stored board's `age_seconds` describes them at least as honestly as
that memo does. Recomputing them per read would put a 91 ms query on the read
path the whole design exists to empty — and the first reader after each memo
expiry would pay it in full. The measured cost of freezing is that the ops
numbers age with the board; the measured cost of not freezing is 91 ms on
every cold-memo read.

**Step 4 — the storage bound.** Largest measured compressed payload 12,640 B ×
(16 warm + `MAX_ON_DEMAND_KEYS` 128) = **1.7 MB**. The bound is a rounding
error against the 1798 MB `radar_bucket_sources` already carries.
