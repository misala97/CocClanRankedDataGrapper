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
| S2 cross-process reuse and cold miss | **Done** — `run_s2_reuse.py`. Warm PASSES; cold FAILS the 2 s target, as designed |
| S3 refresh capacity | **Done** — `run_s3_capacity.py`. 120 s fits, 49% duty cycle |
| S4 semantics parity | **Done** — `run_s4_parity.py`. 12/12 identical; two of Part I.1's five predictions were wrong |
| S5 account isolation | **Done** — `run_s5_isolation.py`. No leak |
| S6 bounded failure | **Done** — `run_s6_failure.py`. One design defect found and fixed |
| S7 restart, empty, expired | **Done** — `run_s7_lifecycle.py`. All four |
| S8 filter switching and browser | **Done** — `run_s8_switching.py`, `run_s8_browser.py`. Warm PASSES; the `pending` render is a FALSE EMPTY STATE |
| S9 ingest contention | **Done** — `run_s9_contention.py`. Producer costs the write +7%; the write costs the producer far more |
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

### CORRECTION — the first five tasks ran on the wrong schema

Found on 2026-09-10 while writing S9, which asserts the held index is absent
before it measures a write.

**It was present.** `codex/radar-perf2` does not carry migration
`c4e17b90d3f2` and never did — but the branch's *code* and the fixture's
*storage* are two different things. `perf1-bench/acceptance.py` BUILDS
`ix_radar_bucket_sources_agg` physically, with the migration's own statement,
and never drops it. It had been sitting on `personal_apps_radar_perf1` since
PERF1 ran.

So **every build time recorded in S1 through S8 before this point was measured
WITH the held index**, which PERF1 measured as worth about 0.9 s of a build.
The store-side numbers — payload bytes, ready-read latency, parity digests,
isolation, fencing, ages — do not depend on it. The BUILD numbers do.

**What was done.** `perf2-spike/fixture_schema.py --fix` dropped
`ix_radar_bucket_sources_agg` and left `ix_radar_bucket_sources_start` and
`ix_radar_bucket_sources_coverage` alone, which is what `models.py` declares
and what Codex's ruling requires. `env_check.preflight` now asserts the index
set on every run, so no later script can quietly measure the wrong schema
again — the same class of guard as the buffer-pool assertion.

**Then S1, S2, S3, S8 and S9 were re-run on the deployed schema.** The tables
below are the re-run numbers unless a heading says otherwise. Where a section
was not re-run, it says so and says which of its numbers move.

---

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

---

### S2 — cross-process reuse, and the cold miss measured apart

`radar-design/perf2-spike/run_s2_reuse.py`, **re-run on the deployed schema**
after the held index was found and dropped, 2026-09-10. Every concurrency
claim below is made with `subprocess.Popen`. **No thread is used anywhere in
this task**, because the two-reader pair PERF1 had to retract was two threads
in one interpreter.

**Step 1 — two independent OS processes reuse one published result.**

| | |
| --- | --- |
| Producer process, wall | 11.61 s (build 6,294 ms; the rest is interpreter start) |
| Reader A, own process | 0.602 s, 50 rows, digest `bf55fe5595a48e4d` |
| Reader B, own process | 0.616 s, 50 rows, digest `bf55fe5595a48e4d` |
| Digests | **IDENTICAL** |
| `fence` after both reads | **1** — exactly one build happened |

The 0.6 s each reader reports is a **fresh-process first read**: SQLAlchemy
pool creation, the lazy imports of `board`/`watch`, first statement compile,
and the first per-account `watch_rows` build. A gunicorn worker pays it once
at boot, not per request (S7 step 1 measures the same first read with no
account at 57–66 ms, which isolates the account half). The per-request number
is Step 2's.

**Step 2 — ready reads on their own. THIS IS THE WARM NUMBER.** Twenty serial
reads per window through `reader.read_payload`, including the per-account
`watch_rows` query for an account watching three tickers.

| Window | n | median | p95 | max | payload |
| --- | ---: | ---: | ---: | ---: | --- |
| 12h All companies US | 20 | **34.3 ms** | **41.5 ms** | 59.3 ms | 50 rows + 3 watch rows |
| 24h All companies US | 20 | **33.5 ms** | **37.6 ms** | 95.8 ms | 50 rows + 3 watch rows |
| 24h, no account at all | 20 | 3.1 ms | 3.7 ms | 3.9 ms | store read alone |

**Warm target 500 ms: PASS, by more than a factor of twelve.** And the split
matters: the store read is 3.1 ms of it and the per-account `watch_rows` build
is the other ~30 ms. The store is not the cost of a warm read; the account's
own pinned rows are. Neither depends on the held index, which is why these
numbers barely moved when it was dropped.

**Step 3 — the first-ever miss, in three parts.** A `sort=lean` 24h key that
had never been built, with a producer daemon **already running** so its
interpreter start is not counted — the real producer is a long-lived loop.

| | |
| --- | ---: |
| (a) the reader answers `pending` | **8.8 ms** |
| (b) enqueue → `state='ready'` | **6,856.6 ms** (producer build 6,740 ms) |
| (c) until a reader can SEE that board | **6,901.5 ms** |
| the follow-up ready read itself | 36.1 ms |

**(a) IS NOT A BOARD.** It is an 8.8 ms acknowledgement that no result exists
yet. Reporting 8.8 ms as a cold success would be the same lie in a new place.

**(c) 6.90 s is the cold number, against a 2 s target. It FAILS by a factor
of three and a half**, and moving the build off the request path does not
shorten it — that is exactly what Part I.8 predicted and what Part V.1 asks
Codex to rule on.

**And a line the earlier, index-present run hid.** With the held index this
same number was 5.28 s. Without it, **6.90 s against a client abort of
8,000 ms leaves 1.1 s of margin.** A single unwarmed selection on a busier
database, or one queued behind another build, exceeds the abort. That is not
an argument for the index — the index is worth about a second of a build that
now happens in the background — it is an argument that **`pending` plus
client-side polling is not optional for unwarmed keys**, because the
alternative is a request that sometimes dies in the browser. The screenshot in
S8 step 3 is the other half of that argument.

**Step 4 — two processes race one missing key.** Two reader subprocesses
released at the same wall-clock instant (`2026-09-10T19:36:35.477095`, both).

| | |
| --- | ---: |
| Rows in the table for that key | **1** |
| `request_count` | 2 — both readers registered demand |
| Producer builds afterwards | 1 (`fence = 1`) |

**Exactly one row and exactly one queued job across two OS processes.** This
is the global deduplication the in-process single-flight structurally could
not do, and the primary key is what does it.

---

### S3 — one producer, sixteen keys, and the cadence it can sustain

`radar-design/perf2-spike/run_s3_capacity.py`, **re-run on the deployed
schema** after the held index was found and dropped, 2026-09-10. Concurrency
1, in-process, because the real producer is a long-lived loop and its module
memos (notably `market_data`'s 91 ms one) are warm between builds exactly as
they are here. **`now` advances per CLAIM, not per sweep** — see "the
deviation Step 4 forced" below.

**Steps 1 and 2 — the sweeps.**

| Sweep | Total |
| --- | ---: |
| first, cold pages (Step 1) | **102.1 s** |
| warm sweep 1 | 67.5 s |
| warm sweep 2 | 65.8 s |
| warm sweep 3 | 65.0 s |
| **median warm sweep** | **65.8 s** |
| worst warm sweep | 67.5 s |

Per-key build, median across the warm sweeps, with the cold first pass beside
it:

| Key | warm | cold first pass |
| --- | ---: | ---: |
| 1h All DE | 2,440 ms | 2,581 ms |
| 1h All US | 2,402 ms | **13,090 ms** |
| 1h 4-segment DE | 2,455 ms | 2,829 ms |
| 1h 4-segment US | 2,449 ms | 2,548 ms |
| 4h All DE | 4,183 ms | **19,864 ms** |
| 4h All US | 4,251 ms | 6,046 ms |
| 4h 4-segment DE | 4,153 ms | 4,176 ms |
| 4h 4-segment US | 4,213 ms | 4,391 ms |
| 12h All DE | 4,301 ms | 4,234 ms |
| 12h All US | 4,367 ms | 4,531 ms |
| 12h 4-segment DE | 4,251 ms | 9,230 ms |
| 12h 4-segment US | 4,209 ms | 5,047 ms |
| 24h All DE | **5,409 ms** | 6,259 ms |
| 24h All US | **5,541 ms** | 6,016 ms |
| 24h 4-segment DE | 5,475 ms | 5,537 ms |
| 24h 4-segment US | 5,311 ms | 5,444 ms |

The 24h builds at 5.4–5.5 s line up with PERF1's without-index 5.38 s median,
which is the check that dropping the index put the fixture back where the
target is. The same run with the held index present measured 4.3 s, so the
index is worth about 1.1 s of a 24h build here — consistent with PERF1's 0.9 s.

**Step 3 — the sustainable cadence.** A sweep has to *finish* inside the
cadence with margin, so the constraint is the worst sweep times 1.30.

| | |
| --- | ---: |
| worst warm sweep × 1.30 margin | 87.7 s needed |
| **sustainable `REFRESH_EVERY`** | **120 s — the proposed value still FITS** |
| duty cycle at 120 s | **55% of one producer process** |
| headroom | about 1.4x the current warm set before 120 s stops fitting |

**Part V.2 and V.5 are answered: sixteen keys at 120 s.** The headroom is real
but thinner than it looks — S9 measured the sweep collapsing to a fifth of
this rate while ingest writes, so this is a quiet-database number.

**Step 4 — the worst age a warm key reaches.** Measured, not reasoned: the
interval between one key's consecutive `as_of` stamps *is* its refresh
interval.

| | |
| --- | ---: |
| back-to-back sweeping, per-key `as_of` interval | 65.4 s best, **67.0 s worst** (24h All DE) |
| drift beyond the median sweep | 1.2 s |
| **worst warm-key age at a 120 s cadence** | **about 121 s** |

`MAX_AGE = 300 s` is therefore honest with 179 s to spare on a quiet database,
and it is also the margin that absorbs S9's ingest contention.
`HARD_MAX_AGE = 3600 s` is thirty sweeps away.

**The deviation Step 4 forced.** The first version of this script pinned one
`now` for a whole sweep. That publishes the *last* key of a sweep already
66 s stale at the instant it is published, and pushes the worst warm-key age
to cadence **plus the whole sweep** — about 186 s rather than 121 s. The fix
is one line and it belongs in the design: **the producer stamps `as_of` when
it CLAIMS, per key, not once per sweep.** Part I.3 does not say which; it must.
Both were measured; the per-claim one is what the table above reports.

---

### S4 — the semantics do not move

`radar-design/perf2-spike/run_s4_parity.py`, one run, 2026-09-10. **Step 1:
`now` pinned at `2026-09-10T12:00:00` for every comparison in the task.**

**Step 0, which is not in the plan and had to be added.** Before the store can
be compared against a direct build, the direct build has to be compared
against itself. It is not obviously deterministic: `serialize` embeds three
health blocks, and `llm_sentiment.ops_summary()` is called with **no
argument**, so it takes `dt.datetime.utcnow()` rather than the board's `now`
and derives `p95_age_minutes` from it.

| | |
| --- | --- |
| Two builds of one selection at one `now` | **identical on this fixture** |
| `llm_sentiment` pending backlog here | **0**, so `p95_age_minutes` is `None` |
| On a box with a backlog | that field moves with the wall clock between two builds of the same board |

**This is a second, independent reason to freeze the ops blocks into the
stored payload** (S1 Step 3 gave the first, 98.7 ms). Recomputed per read,
`sentiment_ops` makes two readers of one stored board disagree about a field
neither of them asked to be live. The fixture cannot demonstrate the drift
because it has no backlog; the code path is quoted above and is not in doubt.

**Step 2 — the store against a direct build, twelve selections.** SHA-256 of
the full serialized payload, read-time freshness fields removed.

| Selection | digest | verdict | rows |
| --- | --- | --- | ---: |
| 12h All US | `273361f7e40570f8` | IDENTICAL | 50 |
| 24h All US | `3c575ece5d74ccc9` | IDENTICAL | 50 |
| 24h All DE | `fddecec8dabed585` | IDENTICAL | 50 |
| 12h default segments US | `bda244a8ae0c7b92` | IDENTICAL | 50 |
| 1h All US | `25cfb93eba8289d8` | IDENTICAL | 50 |
| 4h All US | `bdf7f87a2c5f9e72` | IDENTICAL | 50 |
| 24h venues=2 US | `5ddf7da254083468` | IDENTICAL | 50 |
| 24h limit=100 US | `a853ef5299255682` | IDENTICAL | 54 |
| 24h sort=lean desc US | `c0243f2f5dbc6fd0` | IDENTICAL | 50 |
| 24h sort=mentions asc US | `74a2065abbab0103` | IDENTICAL | 50 |
| `sources=reddit` 24h US | `af72440c251fc4b1` | IDENTICAL | 50 |
| `sources=reddit:wallstreetbets` 24h US | `b63edb9f1f9c74bd` | IDENTICAL | 50 |

**Twelve of twelve identical**, and the full payload with the three ops blocks
*included* also agrees in 12 of 12 on this fixture. **No parity failure.**

**Step 3 — the normalization candidates, ruled by measurement.** Each
candidate built both ways and the payloads digested. **Two of Part I.1's five
predictions were wrong, in opposite directions.**

| Candidate | Part I.1 predicted | MEASURED | what differs |
| --- | --- | --- | --- |
| dedupe `sources` | "none expected" | **ADOPT** | byte-identical |
| sort `sources` | "likely a risk — order must not reach the payload" | **ADOPT** | byte-identical |
| dedupe `segments` | "none expected" | **REJECT** | `segments` |
| sort `segments` | "likely rejected" | **REJECT** | `segments` |
| force `dir='desc'` when `sort is None` | "the payload echoes `dir`" | **REJECT** | `dir` |

Why the two surprises. `sources` survives both transformations because
`build_payload` overwrites `board.sources` with
`sorted({source_root(s) for s in query.sources})` — a rooted, sorted *set*,
which absorbs both duplicates and ordering before the payload is built.
`segments` does not, because the payload echoes `list(segments)` verbatim, so
`?segment=mid,micro,mid` is a different payload from `?segment=mid,micro`
even though it is the same board. **A duplicated segment name is a distinct
key.** That is a larger key space than Part I.1 assumed, and it is still
cheaper than a wrong board.

**Step 4 — sort before limit.** `sort=lean` at `limit=50`: the store's rows
equal the direct build's rows **in order**, asserted.

**And a negative result the plan did not anticipate: the lean case cannot
test the contract on this fixture.** 0 of 50 rows carry any tone at all —
nothing has been judged — so every `_lean_value` is `None`, every row lands in
the same sort bucket, and Python's stable sort returns the default ranking
unchanged. The lean sort provably moved nothing here.

So the contract is proven on a sort this fixture *can* move:

| | |
| --- | --- |
| Candidate pool before the limit | 54 rows, limit 50 |
| `sort=mentions asc`: order differs from the default ranking | **yes** |
| membership differs from the default top 50 | **4 of 50 rows** |

A limit applied *before* the sort could not change membership at all. It
changed by four, which is the entire pool above the limit. The mechanism is
`board.py:585` — `sort_rows(ranked, ...)` then `ranked[:limit]`.

**Teeth.** The order assertion was mutated: swapping the top two rows of the
stored board makes it **fail**, as it must, and a set comparison — which is
what a weaker test would have used — does **not** catch that swap. Both
printed by the script.

---

### S5 — private data stays private

`radar-design/perf2-spike/run_s5_isolation.py`, one run, 2026-09-10. Two
accounts read one stored key; the two reads also ran as **separate OS
processes**.

**The test is built so it can fail.** Both watch lists are drawn from tickers
that are *absent* from the stored blob, checked before the accounts are made —
a raw-byte search for a ticker that is legitimately on the board would pass
for the wrong reason.

| | |
| --- | --- |
| Stored blob | 10,801 bytes compressed, 128,448 bytes JSON |
| A watches | `T00000, T00001, T00002` |
| B watches | `T00003, T00004` |
| `watching` in the stored payload | **absent** |
| `watch_rows` in the stored payload | **absent** |
| Raw-byte search for each of the five tickers | **absent, all five** |
| Account id or username in the blob | **absent** |
| A's response | A's three tickers, 3 watch rows, **none of B's** |
| B's response | B's two tickers, 2 watch rows, **none of A's** |
| The shared half of the two responses | **IDENTICAL** |

**Teeth:** the same byte search *does* find `T03960`, which is on the board,
so it is capable of finding something. And the two responses' digests differ
(`f4f30cd9f9d4` vs `076bc7f4b545`) — proof the per-account half is actually in
the response and not silently missing.

**No isolation failure.**

---

### S6 — failure is bounded

`radar-design/perf2-spike/run_s6_failure.py`, one run, 2026-09-10. Steps 1 and
2 use a **20-second lease** rather than `store.py`'s 120: a test cannot wait
out the real one, and the statement is the same either way. Every reader call
in this task runs under a tripwire that replaces `board.build` and
`leaderboard.build_rows` with something that raises — so "the read path never
builds" is enforced, not asserted.

**Step 1 — kill a producer mid-build.**

| | |
| --- | --- |
| Killed | 1.0 s into its build |
| State immediately after | `building`, `lease_owner=victim`, fence 1 |
| A second producer claiming before expiry | **blocked**, correctly |
| A reader meanwhile | got `pending`, **built nothing** |
| Lease expired and became reclaimable | 18.9 s after the kill (20 s lease) |
| Rescuer published | fence **2**, 10,981 payload bytes |
| **Recovery, kill → ready board** | **29.8 s** |

A hung builder cannot poison its key: the lease expires and the reclaim
increments the fence past it.

**Step 2 — fence an overtaken builder.** Producer 1 claimed at fence 3 and was
held past its lease. Producer 2 reclaimed at fence 4 and published. Producer 1
then tried to publish:

| | |
| --- | --- |
| Producer 1's publish | **`PUBLISHED False` — zero rows affected** |
| The row afterwards | producer 2's `as_of`, fence 4 |

**The older result cannot replace the newer one.** This is the second of the
two defects Codex named in the in-process single-flight, and it is closed by
one `AND fence = :fence` in the `UPDATE`.

**Step 3 — a build that always raises. THIS FOUND A DEFECT IN PART I.3.**

Part I.3 says a key that has failed `MAX_ATTEMPTS` times "stops being retried
until a reader asks again, which resets `attempts`". **Readers ask
constantly** — the island polls. Simulated: thirty minutes of a permanently
broken key with a reader polling every five seconds.

| Rule | reader polls | **build attempts** | backoff schedule |
| --- | ---: | ---: | --- |
| **Part I.3 as written** | 360 | **360** | 30 s, 30 s, 30 s, 30 s, … — never grows |
| **the park timer (implemented)** | 360 | **6** | 30, 60, 120, 240, 480, 900 s |

Under the plan's own rule the backoff does not exist: every poll resets
`attempts` to zero and the next producer pass rebuilds the broken key
immediately. That is the unbounded duplicated work Codex's ruling forbids,
reintroduced through the reset clause.

**The deviation, and it is in `store.py`:**
- `enqueue` records demand (`requested_at`, `request_count`) and **never**
  touches `attempts` or `next_attempt_at`. A key inside a live backoff keeps
  its state; the queue index picks it up when the backoff expires.
- `attempts` is clamped at `MAX_ATTEMPTS` by the claim, and resets **only** on
  a successful publish.
- At `MAX_ATTEMPTS` the key is **parked**: `next_attempt_at = now + 900 s`,
  a retry *rate* rather than a stop. Recovery still needs no manual step, and
  no number of readers can make it faster.

The rest of the step, under the fix: backoff grows monotonically, `attempts`
clamps at 6, `claim` returns `None` inside a backoff so **nothing builds
unclaimed**, and throughout all 360 polls the reader got the last good board —
50 rows, 364 s old, `stale=true`, **zero builds on the read path**.

**Step 4 — producer outage longer than `MAX_AGE`.**

| Into the outage | What the reader got | Age it reported | Rows |
| ---: | --- | ---: | ---: |
| 60 s | fresh board | 60 s | 50 |
| 360 s | **stale board** | 360 s | 50 |
| 3,540 s | **stale board** | 3,540 s | 50 |
| 3,660 s | `pending` | n/a | 0 |

Every reported age is the **real** age, to under two seconds. Past
`HARD_MAX_AGE` the board is correctly treated as missing rather than served as
an hour-old description of a rolling window. **No web-path build was started
at any point** — the tripwire would have raised. The producer coming back
returned the key to `ready` with **no manual step**.

**Step 5 — no long transactions.** Every transaction on the engine during one
produce cycle, timed by SQLAlchemy `begin`/`commit`/`rollback` events with its
first statement recorded.

| Duration | End | First statement |
| ---: | --- | --- |
| **4.128 s** | rollback | `SELECT radar_bucket_sources.ticker …` |
| 0.003 s | commit | `SELECT state FROM radar_board_results …` |
| 0.002 s | commit | `UPDATE radar_board_results SET state='ready', payload=… ` |
| 0.002 s | commit | `UPDATE radar_board_results SET state='building', lease_owner=…` |
| 0.001 s | rollback | `SELECT key_hash FROM radar_board_results WHERE …` |

| | |
| --- | ---: |
| Longest transaction touching `radar_board_results` | **0.003 s** |
| Longest transaction of any kind | **4.128 s** |

**The claim commits before the build and the publish opens its own
transaction after it. Nothing holds a transaction across `board.build`** —
which is what Codex's ruling requires.

**But a finding the plan does not mention: the build itself is one 4.1-second
read transaction.** The ORM session opens on its first `SELECT` and does not
close until the session does, so every produce cycle pins a read view on
`radar_bucket_sources` for the length of a build. On the target that is a
history-list cost paid every 120 seconds by the warm sweep, against a table
ingest is writing to. It is not a blocker and it is not new — the deployed
synchronous path does exactly the same thing on a web worker — but it is real
and it belongs in the release package's list of things to watch.

---

### S7 — restart, empty, expired, redeployed

`radar-design/perf2-spike/run_s7_lifecycle.py`, one run, 2026-09-10.

**Step 1 — the result outlives the process that read it.** Two *separate*
fresh interpreters, the first exited before the second started, three reads
each.

| | |
| --- | --- |
| Worker A (fresh process) | 57 ms, 3 ms, 3 ms |
| Worker B (a different fresh process) | 66 ms, 3 ms, 4 ms |
| Digests | identical; neither built anything |

The result survived the process. **The in-process dict never did** — it starts
empty in every worker at every restart, and with two sync workers that is two
independent cold starts per deploy. The 57–66 ms first read is pool creation
and lazy imports, paid once per worker boot, not per request. (S2's 0.6 s
first read was the same effect plus the first per-account `watch_rows` build;
this run reads with no account.)

**Step 2 — a completely empty store.**

| | |
| --- | ---: |
| First request against an empty store | **`pending` in 8.6 ms** |
| Producer builds it | 4.1 s |
| Next read is a board | 2.7 ms |
| **First request → a board** | **4.1 s** |

The 8.6 ms is an acknowledgement, not a board.

**Step 3 — the three age behaviours.** `MAX_AGE=300 s`, `HARD_MAX_AGE=3600 s`.

| Age | Answer | Age it reported | Error | Rows |
| ---: | --- | ---: | ---: | ---: |
| 0 s | fresh board | 0 s | +0.000 s | 50 |
| 299 s | fresh board | 299 s | +0.000 s | 50 |
| 301 s | **stale board** | 301 s | +0.000 s | 50 |
| 3,599 s | **stale board** | 3,599 s | +0.000 s | 50 |
| 3,601 s | `pending` | — | — | 0 |

Serve, serve-stale, treat-as-missing — and the reported age is the real age to
the millisecond in every served case. The stale read also **queued a refresh**
(`state=pending`) while continuing to serve.

**Step 4 — deployment invalidation.**

| Stored version | Running version | Result |
| ---: | ---: | --- |
| 1 | 1 | a board — so the case can fail |
| 0 | 1 | **`pending`, treated as missing** |

Re-queued for rebuild with `payload_version` still 0 — the column describes
the *blob*, and writing the running version there before the rebuild lands
would be a lie about bytes nobody has replaced. After the rebuild:
`payload_version=1`, `state=ready`, 50 rows.

---

### S8 — rapid filter switching, and a real browser

`run_s8_switching.py` and `run_s8_browser.py`, one run each, 2026-09-10.

**A correction to PERF1's churn list.** `acceptance.py` spelled its second
step `sort='mention_z'` and passed it straight into `board_mod.build`,
bypassing `parse_query`. `mention_z` is not in `board.SORT_KEYS`, and
`sort_rows` returns the list unchanged for a key it does not know — so
**PERF1's second churn step built the same board as its first**, and the API
would answer that URL with a 400. This run substitutes `sort=divergence`,
which is a real sort key and a genuinely different board.

**Steps 1 and 2 — seven selections back to back.** Four of the seven are in
the warm set of Part I.6; three are not.

| | total | worst single |
| --- | ---: | ---: |
| PERF1, deployed code, every selection built | 34.54 s | 5.41 s |
| **store, all seven warm** | **0.03 s** | **0.01 s** |
| store, three unwarmed — 3 of 7 answer `pending` | 0.04 s | 0.01 s |
| store, three unwarmed, **until all seven are BOARDS** | **12.43 s** | — |

The middle row is the one that must not be quoted alone. Three of its seven
answers are not boards. Turning them into boards costs three builds at
12.37 s on one producer, and the honest end-to-end is **12.43 s**.

Note the 100 ms local-interaction target is about sort and mode changes the
client can make without a new server result. Every row above is a new server
result.

**Step 3 — a real browser.** python-playwright, headless chromium, the real
Flask app on port 5001 with a session cookie minted from the app's own signing
serializer. `build_payload` is rebound **in the serving process only**
(`serve_store_app.py`); nothing under `personal_apps/` is modified and
`git status` is unaffected.

| Case | Response | Rows visible | Age | What actually rendered |
| --- | ---: | ---: | ---: | --- |
| warm | 157 ms | **1,040 ms** | 36 s | board, 50 rows |
| unwarmed | 185 ms | — | — | **`pending` — not a board** |
| stale | 42 ms | **130 ms** | 465 s | stale board, 50 rows |

Against the 3,000 ms browser target: **warm MET (1,040 ms, and that includes
chromium's first bundle parse — the stale case a moment later was 130 ms),
stale MET, unwarmed MISSED because no board rendered at all.**

**And the finding this step exists to produce.** Screenshots in
`radar-design/perf2-spike/shots/`.

1. **The `pending` render is a FALSE EMPTY STATE.** `s8-unwarmed.png` shows
   the board's genuine empty state: *"Nothing cleared the bar in this window.
   Try a longer window, or the All view."* That is not what happened. The
   board was never built. The current client has no `pending` concept, so it
   renders "no results" for "no result yet" — and tells the reader to change
   a filter that was working fine. **This is stale-as-fresh's twin: absent
   presented as empty.** Part I.7 lists the client change as the one
   product-visible piece and puts it outside this design's authorization;
   this screenshot is the evidence that it is not optional but a
   precondition.

2. **A stale board renders with no sign it is stale.** `s8-stale.png` is a
   complete board — 50 rows, the detail panel, the header reading "updated
   19:20 CEST". `stale: true` and `age_seconds: 465` are both in the payload
   and neither reaches the screen. `generated_at` is truthful, so the header
   is not lying; but nothing distinguishes a thirty-second-old board from a
   seven-minute-old one, which is what the freshness contract exists to make
   visible. (The 465 s here is artificial — the run ages `as_of` backwards —
   so `as_of` and `generated_at` disagree in this shot in a way they never
   would in production, where Part I.5 makes them the same instant.)

---

### S9 — what the producer does to ingest, and what ingest does to the producer

`radar-design/perf2-spike/run_s9_contention.py`, one run, 2026-09-10, on the
**deployed schema** (the held index dropped — this task is what found it). The
write is `perf1-bench/write_cost.py`'s, unchanged in shape: one bulk `UPDATE`
of `mention_z` across 16,793 existing rows in the live partition, restored
afterwards. The producer runs as a **separate OS process**, because a thread
in the measuring interpreter would contend for the GIL rather than for the
database, and the question is about the database.

**Steps 1 and 2.**

| | run 1 | run 2 | run 3 | median |
| --- | ---: | ---: | ---: | ---: |
| write, no producer | 6.10 s | 5.86 s | 5.91 s | **5.91 s** |
| write, under a producer sweep | 6.32 s | 6.33 s | 6.22 s | **6.32 s** |

**The producer costs the write path +7%.** That is inside run-to-run variance
for this write and is not a measurable delay.

**But the traffic is not symmetric, and this is the finding.** While those
three writes ran, the sweep managed **3 of 16 keys in 38.4 s — 12.8 s per
key**, against 4.1 s per key unloaded (S3's 65.8 s median sweep over
sixteen keys), with **13 keys still queued** when the
writes finished. Three bulk writes of about six seconds each were enough to
take the producer from a sixty-second sweep to a rate that would not finish
one inside four minutes.

**Step 3 — the ruling on the host.** By the letter of the plan's test, the
producer does not measurably delay the write path, so **the ingest daemon is
not ruled OUT by this measurement**. But the ruling that matters points the
other way: **ingest delays the producer**, so a warm-set cadence has to be
stated as a claim about a quiet database, and a scoring pass will push warm
keys past `MAX_AGE`. `MAX_AGE = 300 s` has the margin for that;
`REFRESH_EVERY = 120 s` does not mean every key is under 120 s old while
ingest is writing.

**What the daemon's scheduler actually does, read rather than guessed**
(`run_radar_ingest.py`):

| | |
| --- | --- |
| `add_job` calls | **11** |
| `max_instances` | on every job, and **every value in the file is `1`** |
| `coalesce` | on every job |
| `misfire_grace_time` | **0 occurrences** — APScheduler's default of 1 s applies |
| Scheduler | `BackgroundScheduler(timezone='UTC')` |
| `executors=` | **absent** — the default thread pool runs all 11 jobs |

So overlap of a producer job *with itself* would be prevented by
`max_instances=1`, and the fenced lease makes that belt-and-braces. What is
not prevented is a multi-second producer job sitting in the same default
thread pool as the scoring pass and the fetch loops. **Codex's ruling asks for
the daemon's execution and overlap behaviour to be checked before multi-second
work goes into its scheduler; that is the check, and it says the scheduler
would not double-fire the job but would run it beside ten others in one
pool.**

**Not measured here:** APScheduler's actual behaviour under load, the scoring
pass, retention and partition maintenance, or the Reddit fetch loop. This box
runs neither the real ingest cycle nor MariaDB.
