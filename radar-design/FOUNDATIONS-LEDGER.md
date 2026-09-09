# Foundations progress ledger

Plan: docs/superpowers/plans/2026-09-09-radar-foundations.md
Spec: radar-design/IMPLEMENTATION-SPEC.md
Updated: 2026-09-09

| Step | Status | Evidence / next action |
| --- | --- | --- |
| Planning/source inspection | Complete | Code reviewed at 7a9ffe445076e57d02fea5627e8cd185ec9cb39f; spec/plan written; no runtime test claim |
| Workspace/baseline gate | Complete | Worktree + branch below; package committed 9e8d446; DB `personal_apps_radar_wt` asserted; baseline recorded below |
| F1 run recording | Complete | e4a27e9, fixes in d79da27 |
| F1 independent review | Complete | No blocking findings; 3 should-fix + 6 minor, all resolved in d79da27 |
| F2 board archive | Complete | 3d22902, fixes in 236f862 |
| F2 independent review | Complete | No blocking findings; 4 should-fix + 5 minor, resolved in 236f862 |
| F3 activity/ops APIs | Complete | 328074a, fixes in a178ba6 |
| F3 independent review | Complete | No blocking findings; 7 should-fix + 4 minor, resolved in a178ba6 |
| R2 activity volume measured | Complete | ffbdd37 + the review's fixes; ~2,880 was 5x low on firings. Measured 14,652 rows / 64.2 MiB / 1.6 s / 228 MiB peak heap at days=30 |
| R2 activity cost decision | Open, Codex's | Five options below, two needing no migration. NOT implemented, per the owner's instruction |
| Staging enablement/deploy | Outside scope | Capture defaults off; separate release step |

Implementation workspace: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations
Branch: codex/radar-foundations, branched from dev_personal at 7a9ffe445076e57d02fea5627e8cd185ec9cb39f.
Planning source: C:/Users/michi/Desktop/CodingStuff, dev_personal, HEAD above. Package copied from
C:/Users/michi/Desktop/CodingStuff/radar-design and .../docs/superpowers/plans, committed as 9e8d446.

## Workspace/baseline gate evidence (2026-09-09)

Database. The worktree had no `.env`, so `dotenv.find_dotenv()` returned empty and app.py fell back to
`root` with an empty password: `(1045, "Access denied for user 'root'@'localhost' (using password: NO)")`.
The repository-root `.env` does carry DB_PASS; copying it into the worktree resolved the credentials.
`PERSONAL_DB_NAME` in the worktree's untracked `.env` now names **personal_apps_radar_wt**, a disposable
full clone of the local dev database (43 base tables, 0 views, 456 MB, every row count equal, alembic
version b3d9e1f5a274, one seeded admin, 557,604 radar_buckets). Asserted before any test:
`resolved engine database: personal_apps_radar_wt` / `select database(): personal_apps_radar_wt`.
Local server is MySQL 8.0.46; production is MariaDB, so DDL stays portable.

Migration head. `migrations/versions` has exactly one head, b3d9e1f5a274, matching the clone.

Baseline, before any application change:
- `npm ci` clean install, exit 0.
- `npm test`: 32 files / 403 tests passed (root config) and 26 files / 267 tests passed (radar config).
- `npm run build`: exit 0.
- `py -3.12 -m pytest tests/test_radar_watch_api.py tests/test_radar_api.py -q`: **62 passed**.

The first backend run reported `3 failed, 59 passed`
(`test_human_page_bad_market_falls_back_to_the_default_payload`,
`test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch`,
`test_the_page_falls_back_to_the_default_board_on_a_bad_query`). Cause: a fresh worktree has no
`static/*/dist`, so the page templates could not resolve their built assets. Running `npm run build`
fixed all three with no source change. Not a pre-existing product defect; a workspace prerequisite.

## F1 evidence (2026-09-09)

Commit e4a27e9. Files: `models.py` (RadarIngestRun, RadarBoardObservation),
`features/radar/activity.py` (new), `run_radar_ingest.py` (tick, `_recorder_now`),
`tests/test_radar_activity.py` (new), `migrations/versions/d82f9afb5898_add_radar_observations.py` (new).

Tests, all against `personal_apps_radar_wt`:
- `pytest tests/test_radar_activity.py -q` -> **14 passed**.
- `pytest tests/test_radar_activity.py tests/test_radar_watch_api.py tests/test_radar_api.py tests/test_radar_daemon.py -q`
  -> **147 passed** (3m13s).
- Migration: `flask db upgrade` -> downgrade -> upgrade on the disposable database. A column-shape
  fingerprint of all 43 tables plus `radar_watch` and `radar_buckets` row counts was taken before and
  after; the downgrade removed exactly `radar_ingest_runs` and `radar_board_observations` and nothing
  else, and the re-upgraded fingerprint is byte-identical to the first.

Known environment failure, not caused by this work: `tests/test_radar_ingest.py` fails three tests on
any run after the first against a persistent database
(`test_an_empty_healthy_source_stays_ok_without_database_artifacts`,
`test_fresh_mentions_carry_the_local_model_version`, `test_a_parent_context_comment_keeps_its_ticker`).
Its `_wipe()` helper does not delete `RadarMention` rows for its own ticker, so each run leaves ~25
behind and the next run's `.one()` reads raise `MultipleResultsFound`. Reproduced identically at the
base commit 7a9ffe4 in a separate probe worktree with no source changes, and reproduced again after
deleting the leftovers by hand (a single run re-created them). Left unfixed here because it is an
unrelated suite; raised as a separate task.

### F1 review findings and how they were resolved (d79da27)

Reviewer verdict: nothing blocking. Transaction isolation, the error path, failure containment,
idempotency and the migration head were all confirmed correct against the source.

- The test fixture claimed to be `run_cycle`'s real return and was not: it invented a `status` key
  and typed `per_source` as a count when it is a source-to-health map. Fixed, and pinned by calling
  `run_cycle` for real and comparing keys.
- Three contracts the plan required had no test: the migration round-trip, the status CHECK (parsed
  and silently ignored on older MySQL/MariaDB, and production is MariaDB), and "a failed recorder
  does not roll back successful intake" (the old test did no database work). All three added.
- "No open run" conflated a designed retry with a lost start marker. Now distinguished, with the
  terminal check reading the row `FOR UPDATE`.
- Minor: dead `TERMINAL` constant (now used), imprecise docstring about which path holds pending
  work, redundant `drop_index` before `drop_table` (removed -- it fails when the index is already
  absent), missing index on `observed_at` (added), non-idempotent slot test (now clears first).
- Accepted without change: `uuid4` and `start_run` sitting outside their `try` blocks (the plan
  prescribes that placement and the containment lives in activity.py), and a JSON-serialisation
  failure in `finish_run` leaving a row `running` (readers classify it as incomplete, which is
  what it is).
- Running alembic in-process calls `fileConfig`, which disables every existing logger; that broke
  three unrelated caplog assertions in the daemon suite. The migration test restores logging.

## F2 evidence (2026-09-09)

Files: `features/radar/observations.py` (new),
`tests/test_radar_observations.py` (new), `run_radar_ingest.py` (`_scheduled_observations` plus its
`radar_board_observations` registration, interval 15 minutes, max_instances=1, coalesce=True).

- `pytest tests/test_radar_observations.py -q` -> **15 passed**.
- `pytest tests/test_radar_observations.py tests/test_radar_activity.py tests/test_radar_scheduling.py tests/test_radar_daemon.py -q`
  -> **117 passed** (2m11s).

Size, measured locally and explicitly NOT a production capacity claim: built the real pair against the
cloned database at 2026-09-01 18:22 (the newest bucket the snapshot holds; at today's wall clock both
boards return 0 rows because the snapshot is older than a 24h window). 16 rows per board, one
observation serialising to **77,869 bytes** of JSON. At 96 slots a day that is ~7.1 MiB/day,
~49.9 MiB/7d, ~213.9 MiB/30d uncompressed, before storage-engine overhead. Production row counts,
retention and compression are unmeasured here.

The strip is verified against the real serializer, not only against a fixture: a live build returns 26
top-level keys and the archive keeps 21, dropping exactly `watching`, `watch_rows`, `spend`,
`sentiment_ops` and `market_data_ops`.

Configuration: `RADAR_OBSERVATION_CAPTURE_ENABLED` (default false) and `RADAR_PRODUCER_REVISION`
(unset means NULL). Neither is set anywhere in this worktree, so capture is off.

### F2 review findings and how they were resolved (236f862)

Reviewer verdict: nothing blocking. Immutability, pair-atomicity, the configured-source spelling
(including that `segment=''` really means All and does not fall through to the server's Discover
default), null and provenance preservation, absence of user data and the scheduler's mechanics were
all confirmed correct.

- `except sa.exc.IntegrityError` swallowed *any* integrity failure as "already recorded" while the
  docstring and commit claimed only the slot conflict. Reachable on MariaDB, which gives a JSON
  column its own `json_valid` CHECK. Now re-reads the slot and re-raises when it is absent.
- Nothing pinned the real serializer: every test replaced `build_payload`, so `EXCLUDED` could drift
  while a new account-scoped field entered the archive. Two tests now build a real board.
- The job's registration was untested in a suite that grew a job-capturing helper because a job once
  shipped unscheduled. Tested, including its aligned start.
- The row `limit` was left to the server default and recorded nowhere; sent explicitly now. The
  source roots could not say which subreddits were searched, so the expansion is stored beside them.
- Minor: three assertions that could not fail (archive age, contained-failure, non-duplicate path),
  cleanup only at teardown, and an interval whose phase came from process start time (now aligned to
  the quarter-hour).
- Accepted without change: `capture()` will still accept a backdated `now` -- the tests need it, the
  single production caller passes the wall clock, and the guarantee that matters (`observed_at` is
  never manufactured) is structural. Recorded here rather than asserted in code.

## F3 evidence (2026-09-09)

Commits 328074a and a178ba6. Files: `features/radar/activity.py` (the reading half),
`features/radar/routes/operations.py` (new), `features/radar/routes/__init__.py`,
`tests/test_radar_operations_api.py` (new).

- `pytest tests/test_radar_operations_api.py -q` -> **25 passed**.
- `pytest tests/test_radar_operations_api.py tests/test_radar_activity.py tests/test_radar_observations.py tests/test_radar_api.py tests/test_radar_daemon.py -q`
  -> **194 passed** (2m42s).
- Not vacuous, checked by mutation: with the routes module unregistered, 9 of the endpoint tests
  fail; with `summary()` renamed away, all of them do. Both mutations were reverted and the suite
  re-run green. Note the limit of that exercise, which the first F3 commit message overstated: it
  proves each test touches the code, not that each pins a contract.

### F3 review findings and how they were resolved (a178ba6)

Reviewer verdict: nothing blocking. The Berlin/DST arithmetic, the null-versus-zero contract for
every case reachable today, the authorization split, the absence of remote work and the index on
`started_at` were all confirmed correct, as was `MIN(started_at)` resolving as an index seek rather
than a growing scan.

- `.get(name) or 0` fabricated a zero for a counter added under the module's own "never bump on add"
  policy. A counter missing from any summary being added is now null for that day.
- Off-version runs were skipped from the sums but counted in `completed_runs`, invisibly. Added
  `counted_runs`. **This is one key beyond the daily shape the plan enumerates** -- an additive,
  nullable-free diagnostic that no other key's meaning depends on. Recorded as a deliberate
  deviation; if Codex wants the payload to match the plan exactly, removing it is a one-line change
  and the misreading it prevents comes back.
- `test_ops_makes_no_provider_requests` patched two names `market_data` does not define, guarded by
  `hasattr`, so it patched nothing and duplicated the test above it. Now patches the real entry
  points unguarded and clears the 60-second ops memo first.
- Both signed-out tests accepted `in (302, 401, 403)`, which is the exact distinction the endpoint
  pair is built on. Both pin 302 now, and a non-admin reading `/api/activity` is tested.
- Missing tests added: a run at each DST boundary landing in the right Berlin day, a seven-day
  window across the autumn change measuring 169 hours, a mixed-schema-version day, and `summary()`
  refusing an unsupported window itself.
- Minor: `days=7 ` was read as 7 (now refused), naive-UTC is asserted where an aware value would be
  relabelled, a run outside the rendered days raises instead of vanishing, and the non-admin fixture
  clears its unique username before inserting.
- **Known limit, accepted deliberately** (every figure in this bullet is SUPERSEDED -- measured
  under R2 below: the run count was five times low and "single-digit MB" is 64.2 MiB): the day
  query selects three columns rather than whole ORM
  rows, but still transfers each run's `summary_json`. At a 15-minute cadence `days=30` is ~2,880
  envelopes, each carrying a per-source map -- single-digit MB per request on a `login_required`,
  uncached endpoint. Extracting the four counters in SQL would remove the transfer and was not
  taken: it needs JSON path functions whose behaviour on the production MariaDB cannot be verified
  from this environment. Worth revisiting with a measurement against the real server.
- Documented rather than changed: the admin gate on `/api/ops` is a front door, not a new wall --
  `/api/board` already serves `spend`, `sentiment_ops` and `market_data_ops` to any signed-in
  reader, and the spec explicitly defers removing them.

## R2 evidence -- what the activity endpoint actually reads (2026-09-09)

Commits **ffbdd37** (first pass) and the R2 review's fixes. Files:
`features/radar/activity.py` (the capacity note), `features/radar/observations.py` and
`tests/test_radar_observations.py` (the `capture(now)` wording, and the test it claimed
but that did not exist), `scratchpad/bench_activity.py` (new, repeatable).

### The estimate was wrong because it named the wrong writer

F3's note divided the window by the board archive's 15-minute cadence and got ~2,880 runs
over 30 days. `RadarIngestRun` rows are not written by that job at all. They are written by
`tick`, and **two** scheduler jobs call `tick`:

- `radar_cycle` reschedules itself after every run at `interval_for(session_state(now))` --
  180 s in pre-market and regular hours, 600 s after hours, 1800 s overnight and at weekends.
- `radar_reddit` runs at a fixed `ARCTIC_SHIFT_INTERVAL_SECONDS` = 300 s, all day, every day.

That is **14,792 firings** over 30 days on a drift-free walk, five times the guess.
APScheduler rebuilds the interval trigger on reschedule with `start_date = now + interval`,
so the next firing is *finish* + interval; feeding a 38 s cycle back in gives **12,855**.
`coalesce=True` with `max_instances=1` on the reddit job can only reduce it further. The
drift-free number is therefore an upper bound, and the script prints both.

### And the first measurement of it was itself ~2x too high

Caught by the R2 review, and it is the same class of error the task existed to remove: a
constructed envelope asserted as a measurement. The first benchmark keyed all four
per-source maps by all 36 concrete sources. `run_cycle` does not do that
(`ingest.py:288,306`): `aggregate_status` and `catchup_depth` are keyed by the **root**
fetcher name and only `per_source` by concrete names. And the two schedulers pass disjoint
fetcher sets -- `session_fetchers` is everything but reddit (`run_radar_ingest.py:1348`),
the reddit job gets `{'reddit': fetcher}` alone (`:1128`). No run has ever written a 36-key
`aggregate_status`.

| envelope, as the server stores it | radar_cycle | radar_reddit |
| --- | --- | --- |
| `per_source` | 2 | 34 |
| `aggregate_status` | 2 | **1** |
| `catchup_depth` | 2 | **1** |
| `intake_reasons` | <=2 | <=34 |
| bytes | **631** | **7,447** |

### Measured, against the disposable clone

MySQL 8.0.46; production is MariaDB. Anchor 2019-06-26 12:00, **a Wednesday** --
deliberately: one Sunday is 336 firings against a weekday's 568, so a weekend anchor would
have flattered the cheapest window. Rows and bytes are asked of the **database** over the
same Berlin-calendar-day window `summary()` queries, rather than counted over a rolling
`24h * days` and multiplied by a Python re-serialization -- which is how the first table
came to carry three numbers drawn from two different row sets.

| window | rows | JSON | `summary()` | endpoint | same rows, no `summary_json` | peak heap |
| --- | --- | --- | --- | --- | --- | --- |
| 1 day | 276 | 1.3 MiB | 29 ms | 27 ms | 5 ms | 4 MiB |
| 7 days | 3,212 | 14.3 MiB | 326 ms | 322 ms | 42 ms | 50 MiB |
| 30 days | 14,652 | 64.2 MiB | 1,577 ms | 1,567 ms | 183 ms | **228 MiB** |

Milliseconds are best of five on a warm buffer pool -- a **lower** bound. Every seeded row
is `status='ok'` carrying a full envelope with all eight intake reasons on every source, so
the bytes are an upper bound. The newest day is partial, seeding stopping at the 12:00
anchor exactly as a reader opening it mid-day would find it.

The last two columns are the finding, and neither existed in the first pass. **The envelopes
are ~88% of the time** -- the same rows without `summary_json` take 183 ms against 1,577.
And `summary()` ends in `.all()`, holding every row *and* every decoded dict at once:
**228 MiB of Python heap for one request** on a `login_required`, uncached route that any
signed-in reader can repeat. On a small host that is the number that ends the process, not
the seconds.

### Not implemented. This is Codex's decision.

Recorded per the owner's instruction to bring evidence and a recommendation rather than act.
Two of these need no migration at all:

1. **Memoise completed days.** Days 1..N-1 are immutable once Berlin midnight passes, so
   `days=30` becomes one partial day's work. Portable, no schema change, and the largest
   single win. Needs a cache keyed by the Berlin date and an eviction story.
2. **Drop 30 from `ALLOWED_DAYS`** until a real fix lands. One line in `activity.py:48`, and
   the only option that removes the exposure today. Costs the reader the month view.
3. **Typed counter columns** written at `finish_run`, beside the envelope, which stays as
   provenance. Portable -- no JSON functions. **But `SUM()` alone breaks the null contract**
   the ruling requires: SQL `SUM` skips NULLs, so a day mixing a run that reported
   `posts_seen` with one that did not would return a number where `_counters` deliberately
   returns `None`. Equivalence needs, per counter,
   `CASE WHEN COUNT(*) <> COUNT(col) THEN NULL ELSE SUM(col) END`, with `counted_runs`
   counted separately. Costs a migration; there are no production rows yet, which makes now
   the cheapest this will ever be.
4. **A daily rollup table.** Smallest read, but a second writer to keep correct and a repair
   path for when a run closes late.
5. **JSON path extraction in SQL.** No migration, and still **rejected**: it needs
   `JSON_EXTRACT`/`JSON_VALUE` behaviour that cannot be verified against the production
   MariaDB from here, and the null-versus-zero contract turns on telling an absent key from
   a zero -- exactly where the two engines' JSON functions are least alike.

**Recommendation: 2 now, 1 next, 3 when a migration is being cut anyway.** Note what is not
urgent: at `days=1` and `days=7` the endpoint answers in 27 ms and 322 ms. Only `days=30` is
bad, and it is bad in memory before it is bad in time.

### Also corrected

`capture(now)`'s docstring claimed the function guarantees a real-time observation. It does
not and cannot: `now` is an injected clock and the parameter exists for deterministic tests.
The wording now says what is true -- `observed_at` is the instant the caller supplied,
copied verbatim; the guarantee belongs to the call path.

That docstring then cited a test that **did not exist**, and CODEX-DECISIONS.md:29 asked to
"preserve" it. `_scheduled_observations` could have passed `_next_quarter_hour(...)` or a
local time and the whole suite would have stayed green.
`test_the_scheduled_job_captures_the_wall_clock` now pins it, and the docstring names it so
the claim is checkable. Mutation-checked: passing `observations._slot(_utcnow())` instead
fails **that test and only that test**.

### Verification

- `pytest tests/test_radar_activity.py tests/test_radar_observations.py tests/test_radar_operations_api.py -q`
  -> **66 passed** (65 before the new test). No behaviour changed under R2 outside that test;
  the rest is comments and docstrings, and the benchmark lives in `scratchpad/`.
- `PYTHONPATH=. py -3.12 scratchpad/bench_activity.py` -> the tables above. It refuses any
  database but `personal_apps_radar_wt` -- checked with `raise SystemExit`, not `assert`,
  which `-O` compiles away -- seeds into 2019 and clears in a `finally`.

### Limits of the measurement, stated

- MySQL 8.0.46, not the production MariaDB.
- Warm buffer pool, best of five: the milliseconds are lower bounds.
- Envelopes are constructed to the real shapes, not captured from a production run -- this
  machine has none. Every key is `run_cycle`'s own and every map is keyed the way
  `run_cycle` keys it, which is what makes them representative in the dimension that matters
  here.
- The 2019 window is shared with the backend suite's fixtures, which run the same blanket
  `started_at < 2020-01-01` delete. No test anchor falls inside 05-27..06-26, so there is no
  collision today; do not run the benchmark concurrently with that suite.

For each completed step append commit, exact tests/results, reviewer findings, fixes/rulings and next step. Never mark an unrun check passed. Keep environmentally blocked tasks open with exact failure evidence. Takeover verifies this ledger against Git and reports.
