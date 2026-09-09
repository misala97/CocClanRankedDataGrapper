# Foundations progress ledger

Plan: docs/superpowers/plans/2026-09-09-radar-foundations.md

**Provenance of the SHAs below.** Rows for F1-F3, H1-H4, R1-R3 and P1 cite commits
on `codex/radar-foundations`, where that work was done and reviewed. The P2 rows
cite commits on `codex/radar-release-candidate`. The two are different branches:
the candidate transplants the former's release commits onto `origin/main`, so a
foundations SHA does **not** resolve there. Test evidence recorded against a
foundations SHA was re-run on the candidate and is recorded separately under
"P2 candidate".
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
| R2 activity volume measured | Complete | ffbdd37, corrected in 08c5b47; ~2,880 was 5x low on firings. Measured 14,652 rows / 64.2 MiB / 1.6 s / 228 MiB peak heap at days=30 |
| R2 independent review | Complete | 1 blocking + 9 should-fix + 8 minor + 2 nits; all 20 resolved in 08c5b47 |
| R2 correction re-review | Complete | No blocking; every committed figure re-derived independently and reproduced exactly. 4 should-fix + 3 minor + 5 nits resolved in 8bbd57e |
| R2 activity cost decision | Resolved by Codex | Option 3 chosen before first rollout; ALLOWED_DAYS stays (1,7,30). See CODEX-DECISIONS.md "Second return" |
| R3 typed activity counters | Complete | c4e0455 + 278625c; migration a7c31f0b52d4. Both acceptance targets pass: 0.8 MiB peak heap (<=16), 390 ms median endpoint (<=500) |
| R3 independent review | Complete | 1 blocking + 4 should-fix + 4 minor + 5 nits; all resolved in cfe39e7 |
| R3 acceptance | Accepted by Codex | Strict integers confirmed correct; counter contract accepted as implemented. CODEX-DECISIONS.md "Third return" |
| P1 MariaDB rehearsal | Complete | 01b056d + review fixes; MariaDB 10.11.14, 39 checks, all passing. Both migrations, both downgrades, both interruption points, recovery, refusal, and the app's own path |
| Release proposal | Approved by Codex | Architecture approved; the runbook was not release-ready. CODEX-DECISIONS.md "Fourth return" |
| P2 candidate branch | Complete | `codex/radar-release-candidate` off origin/main 2a83905; 38 transplanted, 12 excluded, no leak, regressions match the source branch |
| P2 first-migration recovery | Complete | rehearse_first_migration.py, MariaDB 10.11.14, 25 checks |
| P2 single-path runbook | Complete | RELEASE-RUNBOOK.md; the proposal's second path removed |
| P2 deploy-script inspection | **Blocked** | Needs /root/update_coc.sh and the unit files. No VPS access |
| P2 target preflight | **Blocked** | Needs read-only queries on the target. No VPS access |
| P2 backup restore | **Blocked** | Needs a consistent backup and a disposable MariaDB to restore into |
| Owner visual review | Open | Codex: nothing blocks it; the owner prefers to compare on the VPS |
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

Commits **ffbdd37** (first pass), **08c5b47** (the review's blocking finding) and **8bbd57e** (the re-review's). Files:
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

**Both scheduling models are seeded and measured**, not one measured and the other
asserted -- publishing only the drift-free walk this ledger calls an upper bound would have
been the same overstatement in a different place.

Start + interval, the drift-free upper bound:

| window | rows | JSON | `summary()` | endpoint | no `summary_json` | peak heap |
| --- | --- | --- | --- | --- | --- | --- |
| 1 day | 276 | 1.3 MiB | 27 ms | 31 ms | 4 ms | 4 MiB |
| 7 days | 3,212 | 14.3 MiB | 307 ms | 320 ms | 40 ms | 50 MiB |
| 30 days | 14,652 | 64.2 MiB | 1,609 ms | 1,586 ms | 196 ms | **228 MiB** |

Finish + interval with 38 s runs -- what APScheduler actually does:

| window | rows | JSON | `summary()` | endpoint | no `summary_json` | peak heap |
| --- | --- | --- | --- | --- | --- | --- |
| 1 day | 239 | 1.1 MiB | 26 ms | 25 ms | 4 ms | 4 MiB |
| 7 days | 2,791 | 12.6 MiB | 297 ms | 262 ms | 35 ms | 45 MiB |
| 30 days | 12,728 | 56.8 MiB | 1,390 ms | 1,413 ms | 160 ms | **201 MiB** |

The last two columns are the finding, and neither existed in the first pass. **The envelopes
dominate** -- the same window without `summary_json` takes 160 ms against 1,390. That control
is a bare two-column select rather than `summary()` minus the column, so it also skips the
grouping loop and somewhat overstates their share; the direction is not in doubt. And
`summary()` ends in `.all()`, holding every row *and* every decoded dict at once: **~201 MiB
of Python heap for one request** on a `login_required`, uncached route any signed-in reader
can repeat. On a small host that is the number that ends the process, not the seconds.

Bounds, in both directions. Milliseconds are best-of-five on a warm buffer pool: **lower**
bounds. The endpoint is timed last, over rows already read a dozen times, so it can come out
a few ms under the function it wraps -- that gap is the noise floor, not a saving. Peak heap
is `tracemalloc`, so Python allocations only; the driver is pymysql, pure Python, so its
buffers *are* counted, but allocator overhead is not -- a **floor** on RSS. Every seeded row
is `status='ok'` with a full envelope and all eight intake reasons on every source;
`intake_reasons` is 84% of the reddit envelope, so that is an **upper** bound on bytes. The
newest day is partial, seeding stopping at the 12:00 anchor exactly as a reader opening it
mid-day would find it.

### Not implemented. This is Codex's decision.

Recorded per the owner's instruction to bring evidence and a recommendation rather than act.
Three of the five need no migration; two of those are viable.

**First, a fact that constrains every option: a day is NOT immutable at Berlin midnight.**
`summary()` groups runs by `_berlin_date(started_at)` (`activity.py:258`), but `finish_run`
writes `status` and `summary_json` at *finish* time and never touches `started_at`
(`activity.py:66-104`). A run that starts at 23:59:5x Berlin and closes after midnight moves
the **previous** day's `incomplete_runs` into `completed_runs`/`counted_runs` and adds its
counters, after that day looked complete. At ~38 s runs against a 300 s reddit interval and a
600 s cycle interval at Berlin midnight, that is roughly **one day in five**, and more
whenever an Arctic Shift pass overruns -- which is exactly what `coalesce=True,
max_instances=1` on `radar_reddit` exists to absorb. Found by the R2 review; an earlier
version of this section asserted the opposite, and a memo built on it would have frozen a
wrong count into ~20% of days.

Nothing else invalidates a past day: `retention.prune_*` covers posts, quotes, mention events
and market data, and never `RadarIngestRun`, so rows are not deleted underneath a cache -- and
the 30-day steady state really is unbounded.

1. **Memoise completed days.** Days 1..N-1 become one partial day's work. Portable, no schema
   change, largest single win -- **but the cache key cannot be the Berlin date alone.** A day
   is only safe to freeze once it holds no `running` rows; a cheap
   `COUNT(*) WHERE status='running'` per candidate day gives that, and a day left `running`
   by a dead process is simply never memoised.
2. **Drop 30 from `ALLOWED_DAYS`** until a real fix lands. One line in `activity.py:48`, and
   the only option that removes the exposure today. Costs the reader the month view.
3. **Typed counter columns** written at `finish_run`, beside the envelope, which stays as
   provenance. Portable -- no JSON functions. Two traps, both load-bearing:
   - `SUM()` skips NULLs, so a day mixing a run that reported `posts_seen` with one that did
     not returns a number where `_counters` deliberately returns `None`. That needs
     `CASE WHEN COUNT(*) <> COUNT(col) THEN NULL ELSE SUM(col) END` per counter.
   - **That expression is still not equivalent over "the day's `status='ok'` rows"**, which is
     the only population typed columns can name. `_counted` (`activity.py:150-158`) *drops* an
     ok-run whose envelope is missing, malformed, or of another `schema_version`; `_counters`
     then sums what remains. The CASE would read NULL columns for such a row and null the
     whole day -- and, worse, an ok-run stored under an OLDER schema version would be silently
     summed, which is the cross-version addition `SCHEMA_VERSION` exists to prevent. Typed
     columns cannot distinguish "this run stored nothing countable" from "this run's summary
     omitted this counter"; both are NULL. So the migration also needs a stored
     `schema_version` column plus a countable marker, with the CASE filtered on it.
   Costs a migration; there are no production rows yet, which makes now the cheapest this will
   ever be.
4. **A daily rollup table.** Smallest read, but a second writer to keep correct and a repair
   path for when a run closes late -- the same hazard as 1, made explicit.
5. **JSON path extraction in SQL.** No migration either, and still **rejected**: it needs
   `JSON_EXTRACT`/`JSON_VALUE` behaviour that cannot be verified against the production
   MariaDB from here, and the null-versus-zero contract turns on telling an absent key from a
   zero -- exactly where the two engines' JSON functions are least alike.

**Recommendation: 2 now, 1 next with the `running`-row condition, 3 when a migration is being
cut anyway and only with the schema-version column.** What is not urgent: at `days=1` and
`days=7` the endpoint answers in 26 ms and 297 ms. Only `days=30` is bad, and it is bad in
memory before it is bad in time.

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

### What the R2 review found

One blocking, nine should-fix, eight minor, two nits. All twenty resolved in 08c5b47. The
blocking one is above; the rest, briefly:

- The `days=1` row paired a rolling-window row count with a Berlin-window timing -- three
  numbers from two row sets. Both now come from the same window, asked of the database.
- The byte figure was a Python re-serialization in a format nothing in the pipeline uses.
  Now `SUM(LENGTH(summary_json))`, which is also what would have caught the blocking finding.
- The docstring cited a call-path test that did not exist. It does now.
- HANDOFF.md and this ledger still carried the debunked ~2,880 figure, and `activity.py`
  pointed its evidence at HUB-LEDGER.md, which never held it. Both corrected; activity is
  foundations work and the evidence belongs here.
- The firing walk added the interval to each run's START. APScheduler rebuilds the trigger
  with `start_date = now + interval` on reschedule, so it is FINISH + interval. Both models
  are printed and the drift-free one is labelled as the upper bound it is.
- No control and no memory measurement -- the two numbers that turned out to matter most.
- No `try`/`finally`, so a failure in the timed region would have left ~15,000 rows behind;
  and the database guard was an `assert`, which `-O` compiles away. Both fixed.
- The recommendation named no option that avoids a migration, and its typed-counter sketch
  dropped the null semantics the ruling requires. Five options now, with the `CASE WHEN`.
- The endpoint's exposure was never stated: `login_required`, not admin-gated, uncached,
  repeatable. Said plainly now, in the source comment and above.
- Minor: `intake_reasons` used invented keys rather than the extractor's `REASONS`;
  `WEEKEND_ANCHOR` was unused while the commit quoted a weekend figure as if measured; the
  engine and version went unrecorded while the argument rests on MySQL and MariaDB
  differing; `reddit_interval()` re-implemented `_reddit_job_seconds()` instead of importing
  it; the seeded rows are all `status='ok'` with full envelopes, an upper bound now stated.

### What the re-review of the correction found

The corrected model was checked by a second reviewer who rebuilt both envelopes and both
scheduler walks from `market_calendar`, `REDDIT_SUBS` and `extraction.REASONS` outside the
repository, without running the benchmark. **Every committed figure reproduced exactly** --
632/7,447 bytes, 276/3,212/14,652 rows, 64.199 MiB, 14,792 and 12,855 firings, 336 on a
Sunday. No blocking finding. Four should-fix, three minor, five nits, all resolved:

- **The table was seeded from the drift-free walk** -- the upper bound this very section
  argues APScheduler does not produce -- and nothing said so. Both models are now seeded and
  measured, and the difference is 13% of the rows, not the phase effect the previous note
  blamed it on.
- **`activity.py` labelled the milliseconds a lower bound but never the bytes an upper one.**
  `intake_reasons` is 84% of the reddit envelope, so a quiet sub makes it markedly smaller.
  The source comment carries the caveat the ledger already had.
- **"Days 1..N-1 are immutable once Berlin midnight passes" was false**, and it was the
  premise of the leading recommendation. Corrected above, with the condition a memo needs.
- **The `CASE WHEN` expression was not equivalent** over the only population typed columns
  can name. `_counted` drops an ok-run with a missing, malformed or off-version envelope;
  the CASE would null the whole day for one and silently sum the other. Option 3 now names
  the `schema_version` column and countable marker it actually needs.
- Minor: the endpoint measured faster than the function it wraps in every row (warm-cache
  ordering -- the noise floor, now stated); "~88% of the cost" over-attributed, because the
  control is a bare select that also skips the grouping loop; "228 MiB of heap" now says
  Python heap and floor, since `tracemalloc` sees pymysql's pure-Python buffers but not
  allocator overhead.
- Nits: "two of the five need no migration" contradicted option 5 four lines below (three
  need none, two are viable); the new test's first docstring line overstated what it pins;
  34 subs is a ceiling, not a constant, because a 429 ends the cycle; `operations._utcnow`
  was mutated with no restore; `catchup_depth` for fourchan is a thread count, not 0.

Confirmed correct and left alone: the window alignment, the 32-day seeding reach, the
`SystemExit` guard ordering and `finally`, `LENGTH()` over a JSON column as a proxy for the
bytes on the wire (MariaDB stores `JSON` as `LONGTEXT`, so the same), and the new call-path
test -- including that `monkeypatch.setattr(runner, '_utcnow', ...)` reaches the name the
caller looks up, and that the sentinel's microseconds defeat any rounding.

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

## R3 evidence -- typed activity counters (2026-09-09)

Commits **c4e0455** (core), **278625c** (acceptance evidence, and two fixtures that
had outlived their schema), **cfe39e7** (the review's findings). Migration
**a7c31f0b52d4**, following the verified head d82f9afb5898. Single head after it.

Files: `models.py`, `features/radar/activity.py`,
`migrations/versions/a7c31f0b52d4_add_radar_run_counter_projection.py` (new),
`tests/test_radar_activity_projection.py` (new, 53),
`tests/test_radar_projection_migration.py` (new, 5),
`tests/test_radar_activity.py` and `tests/test_radar_operations_api.py` (fixtures),
`scratchpad/bench_activity.py`.

### What it does

Six additive columns beside `summary_json`, which is unchanged and remains the
record: `summary_schema_version` (nullable int), `summary_countable` (non-null bool,
server default false) and the four counters as nullable signed BIGINTs. `finish_run`
writes the projection in the SAME transaction and under the SAME terminal guard as
the envelope -- a row whose typed counters disagreed with its own JSON would be a row
with two answers and no way to tell which was the record.

The marker and the version answer different questions, and keeping them apart is what
makes parity possible. `summary_countable` says the envelope was structurally well
formed and carried an integer version; it does NOT say the version is one any reader
understands, which only a reader can decide against its own `SCHEMA_VERSION`. A
counter missing from an otherwise valid summary is null and leaves the row countable
-- exactly the case a nullable column alone cannot express, since NULL cannot separate
"stored nothing countable" from "omitted this one counter", and those have opposite
consequences.

The read names eight scalar columns and streams them with `yield_per`, folding into
at most 30 Berlin-day accumulators. One statement, so one snapshot: paging with
separate queries would assemble a window from several transactions and a cycle
closing between two of them could be counted twice or not at all. `_counted` and
`_counters` are gone from production; the old envelope reducer lives in the tests as
an oracle, because keeping a JSON fallback would leave the read able to fetch
envelopes -- the cost being removed.

### Measured, against the disposable clone

MySQL 8.0.46; production is MariaDB. Both scheduling models seeded and measured.

| | rows | `summary()` med/max | endpoint med/max | cold | peak heap |
| --- | --- | --- | --- | --- | --- |
| **upper bound**, 1 day | 276 | 10/11 ms | 10/11 ms | 9 ms | 0.1 MiB |
| 7 days | 3,212 | 85/183 ms | 92/328 ms | 86 ms | 0.8 MiB |
| **30 days** | 14,652 | 383/419 ms | **390/414 ms** | 394 ms | **0.8 MiB** |
| **finish+interval**, 1 day | 239 | 9/9 ms | 11/11 ms | 9 ms | 0.1 MiB |
| 7 days | 2,791 | 73/76 ms | 77/79 ms | 82 ms | 0.8 MiB |
| **30 days** | 12,728 | 332/369 ms | 333/351 ms | 346 ms | 0.8 MiB |

**Both acceptance targets pass**, on the 30-day upper-bound fixture Codex named:

| | before R3 | after | target |
| --- | --- | --- | --- |
| peak incremental Python heap | ~228 MiB | **0.8 MiB** | <= 16 MiB |
| median endpoint | ~1,586 ms | **390 ms** | <= 500 ms |

Four concurrent 30-day reads: **0 errors**, 1958/1971/1987/2042 ms, process RSS
135 -> 136 MiB (finish+interval: 1524-1663 ms, RSS 140 -> 140). Concurrency costs
roughly linear time and almost no memory, which is what a streaming read should look
like; it is not evidence of concurrency safety beyond "four readers did not fail".

Cold reads match warm (394 vs 390 ms at 30 days), which is the point: the improvement
is the read getting cheaper, not a second request getting lucky. The database buffer
pool is warm in every column -- what "cold" varies is application state, a fresh
client and session with the first call measured. Stated in the script's own output.

The 56.8-64.2 MiB of JSON is still stored and no longer read. That column is the size
of the problem, not of the request.

### Three deliberate divergences from the old reducer

Parity is exact for every shape production writes. It is deliberately NOT exact in
three places, and the R3 review was right that the test module claimed otherwise
while routing every disagreeing case around the oracle:

- `schema_version` of **`1.0`** counted before and does not now. `1.0 == 1` is true in
  Python, so the old equality check accepted it. **Undocumented and untested until the
  review found it.**
- `schema_version` of **`True`** likewise -- `isinstance(True, int)` is true.
- A counter of **-4, `True` or 1.5** was summed; **`'5'`** raised TypeError out of the
  endpoint. All are now null for that counter.

Each is the right behaviour: an Integer column recording `1` for a declared `1.0`
would claim the envelope said something it did not, and requirement 6 forbids
coercing counters. Four tests now assert the DIFFERENCE against the oracle, named
`..._before_and_..._now`, so the choice is on the record.

### The migration

Additive, and the backfill is Python rather than a JSON-path UPDATE: production is
MariaDB, local is MySQL, and their JSON functions differ exactly where this
projection is most delicate. Batched by primary key, 500 at a time, keyset paged. The
projection rules are a **frozen copy, not an import** -- a migration must keep
producing the same rows years from now -- pinned to the live rules by a 20-case test.

The domain scan runs **before any DDL**. That was a real defect in the first version:
MySQL commits implicitly on `ALTER TABLE`, so refusing after the columns were added
left them present with the revision unstamped, and the next `flask db upgrade` failed
on a duplicate column instead of retrying. I hit that state and repaired the clone by
hand. Refusing first leaves the schema untouched.

One state remains that cannot be made clean and is now documented in the migration:
if the BACKFILL dies part-way, the columns exist and the revision is unstamped.
Recovery is to drop the six columns and upgrade again; the SQL is in the docstring.
Nothing is lost, because every projected column is derived from `summary_json`.

Counter domain is non-negative integers fitting a signed BIGINT. Violations are
refused, never coerced or clamped, and the migration reports ids and value SHAPES,
never stored content (asserted). No such row exists in the clone, so there is no
compatibility exception to bring to Codex.

### Verification

- `pytest test_radar_activity + test_radar_observations + test_radar_operations_api +
  test_radar_activity_projection + test_radar_projection_migration + test_radar_api +
  test_radar_daemon -q` -> **253 passed**.
- Migration applied to `personal_apps_radar_wt`; upgrade/downgrade/upgrade with 11
  seeded row shapes preserves every envelope and a `show columns` fingerprint of every
  table.
- Mutation-checked: selecting `summary_json` fails the query-level test; a fixed-width
  `_day_bounds` fails the two new DST boundary tests and neither grouping test.
- `yield_per` verified to stream genuinely -- pymysql executes it on an `SSCursor`.

### What the R3 review found

One blocking, four should-fix, four minor, five nits; all resolved in cfe39e7. The
blocking one is above. Also fixed: the refusal test's assertion was guarded by "if the
column exists" and so asserted nothing once the scan moved above the DDL; both DST
tests passed under a naive 86,400-second day; `project()` sat outside `finish_run`'s
try, against this module's own first rule; a mid-backfill failure had no documented
retry; `_Day.add` treated any non-running, non-error status as completed where the
reducer required `ok`; `_out_of_domain` blocked on junk rows no reader could count;
`_batches` would skip an empty-string id; "seven scalar columns" is eight; and
"replacing either with `.all()` restores the original cost exactly" credited streaming
with a win the column list had already delivered.

Confirmed correct and left alone by the reviewer: oracle fidelity against 3c93ad8, the
marker/version split, null-semantics order independence, the write path's single
transaction and guard, `recording_started_at` sharing the window snapshot, keyset
paging correctness under the column collation, the downgrade being an exact inverse,
the refusal message not leaking values, and the midnight test's `db.session.rollback()`
modelling a request boundary rather than masking a failure.

## P1 rehearsal -- both migrations on MariaDB 10.11.14 (2026-09-09)

Commits **01b056d** and the review's fixes. `scratchpad/rehearse_mariadb.py`,
**39 checks, all passing**.

### The engine, and why it had to be this one

The target runs **MariaDB 10.11.14** (recorded in the workspace's own VPS notes, not
read from production). Local development is MySQL 8.0.46. They differ exactly where
these two migrations are most delicate: MariaDB aliases `JSON` to `LONGTEXT`, and its
DDL auto-commits so no surrounding transaction can undo a half-applied `ALTER`. A
MySQL result is not evidence about the target, and Codex's P1 said so explicitly.

**The machine had no such environment.** No MariaDB binary, no Docker, no Podman, and
WSL is not installed -- only the MySQL 8.0 service. With the owner's agreement a
portable MariaDB 10.11.14 was fetched from mariadb.org and run from the scratchpad on
port 3399 with its own datadir. Nothing was installed system-wide, no service was
registered, and the MySQL80 service was untouched.

The harness builds its own Flask app rather than importing `app`, because `app.py`
hard-codes port 3306 where MySQL already listens. **No application code was changed to
run it.**

Three guards, and it is worth being exact about what each does. The host must be
loopback, so no remote server can be reached whatever the environment says. The schema
must not be `personal_apps` or `coc_stats`. And the server must be MariaDB, checked
before anything is dropped -- the point being to make a substituted MySQL result
impossible rather than merely discouraged. What they do NOT do is protect an arbitrary
schema name on a loopback MariaDB: any other name is dropped and recreated. The first
version of the docstring claimed more than that, and the host guard was added after
review pointed out that `REHEARSAL_HOST` was unconstrained.

### What passed

| # | rehearsed | checks |
| --- | --- | --- |
| 1 | clean upgrade of both revisions over 12 pre-existing rows | 10 |
| 2 | both downgrades, then re-upgrade | 8 |
| 3 | interrupted after only THREE of six columns exist | 6 |
| 4 | interrupted partway through the backfill | 6 |
| 5 | the pre-DDL domain refusal, on this engine | 5 |
| 6 | the application's own writer and reader | 4 |

Section 2 covers **both** downgrades. The first version of this rehearsal only ever
downgraded to `d82f9afb5898`, so the `drop_table` in `d82f9afb5898.downgrade` -- the
one the runbook's rollback command actually reaches -- had never run on MariaDB while
a note beside it claimed "both revisions". It drops exactly the two tables, adds
nothing, and leaves `b3d9e1f5a274` stamped.

The twelve seeded rows are one of every shape the projection must classify: valid,
genuine zero, partial counters, an explicitly null counter, off-version,
**float-version**, unversioned, malformed summary, not-a-mapping, no envelope,
running, error. They are written as the PREVIOUS revision wrote them -- envelope only,
no projection -- which is what the backfill has to read.

Load-bearing results:

- **The backfill reproduces `activity.project` exactly for all twelve shapes**, checked
  row by row rather than in aggregate.
- **Every envelope is byte-identical after the upgrade**, after the downgrade, and
  after each recovery. Row count never moves.
- A `schema_version` of `1.0` stays uncountable on MariaDB too -- the case Codex ruled
  on, confirmed against the engine where `JSON` is text.
- **A blind re-upgrade over partially created columns fails loudly** with a duplicate
  column, which is exactly what the runbook warns an operator about. Dropping only the
  columns actually present and upgrading again reproduces the clean projection.
- The half-written backfill state is asserted to **differ** from the clean one, so
  step 4 cannot pass by accident.
- The refusal names the row id and the value shape and **does not leak the value**;
  it adds no column and leaves the revision unstamped, so the retry after fixing the
  data is clean.
- `finish_run` stores a readable envelope and its projection on MariaDB, `summary()`
  reads it back, and the read still never selects `summary_json`.

### What this does NOT establish

- It ran on a **fresh database stamped at b3d9e1f5a274**, not on a copy of the
  target's data.
- **The target has no `radar_ingest_runs` table at all.** `d82f9afb5898` creates it,
  and the deployed code declares no `RadarIngestRun` model
  (`git grep RadarIngestRun 7a9ffe4` is empty). So the twelve seeded rows rehearse the
  SECOND deployment and every one after it, not the first: on the first the table is
  created empty, the backfill projects zero rows, and the domain refusal cannot fire.
  An earlier version of this section warned about "the target's existing rows", which
  described a risk that cannot occur.
- The other 60 revisions below `b3d9e1f5a274` were stamped, not replayed. They are
  **expected** to be applied on the target -- asserted from the repository, not
  measured against it, since this workspace has no production access. The runbook
  checks `flask db current` before migrating.
- 10.11.14 was matched deliberately, but the build was not: this ran the mariadb.org
  binary distribution on a default configuration, and the VPS runs the Ubuntu package
  `10.11.14-MariaDB-0ubuntu0.24.04.1` with its own `99-tuning.cnf`. Same upstream
  version, different build and settings. A target on a different minor version is a
  gate, not a formality.

### How to repeat it

```
# portable server, throwaway datadir, spare port
mariadb-install-db.exe --datadir=<scratch>\data --password=""
mariadbd.exe --datadir=<scratch>\data --port=3399 --console
cd personal_apps && PYTHONPATH=. py -3.12 scratchpad/rehearse_mariadb.py
```

The script drops and recreates its schema on every run, so it is repeatable without
cleanup. Stop the server and delete the directory when finished; nothing else on the
machine is affected.

## P2 candidate and access gates (2026-09-09)

Prepared on branch **`codex/radar-release-candidate`**, in a separate worktree at
`C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate`. The
`codex/radar-foundations` branch and worktree are unchanged, as the ruling requires.

### The transplant

| | |
| --- | --- |
| branched from | fetched `origin/main` **2a83905** |
| selected | **38** commits, `7a9ffe4..codex/radar-foundations`, chronological |
| excluded | **12** unpublished research commits below the base |
| method | `git cherry-pick 7a9ffe4..codex/radar-foundations`, no conflicts |

The excluded twelve are the judge/encoder work: `473c4b9`, `d8e1bea`, `728f75f`,
`002c5bf`, `c50b73a`, `f6d2887`, `7e57a1b`, `8ad7899`, `ace9ead`, `7efee13`,
`40c9c7c`, `7a9ffe4`. None is a radar-hub change.

**Acceptance evidence** — `personal_apps/scratchpad/candidate_check.py` on the
candidate, which **exits non-zero if any claim fails**. The first version exited 0
whatever it printed and swallowed git's return code, so a mistyped revision read as
"nothing found, all clear"; the review caught that and both are fixed. The file
counts are quoted against the transplant tip **91d3e2b**, since documentation
commits land above it; ancestry and contamination are checked against HEAD.

- 38 selected, 38 transplanted, counts match.
- **No excluded commit is an ancestor of the candidate.** Checked individually with
  `git merge-base --is-ancestor` for all twelve: none.
- The twelve touch **19 paths**. The candidate changes **none** of them, so nothing
  entered through conflict resolution.
- Candidate diff against `origin/main`: **114 files, +14,287 / -32**.
- The candidate tree differs from the source branch by exactly those 19 files, which
  is the research work correctly left behind.

### A clean transplant is not dependency safety, so it was tested

Codex is explicit that a textual transplant proves nothing about whether the release
still works without the twelve. Run **on the candidate**, against the disposable
clone `personal_apps_radar_wt`:

- `npm ci` clean, `npm run build` exit 0.
- `npm test` -> **403 passed** (root config) and **438 passed** (radar config).
- `flask db heads` -> **a7c31f0b52d4**, single head.
- `pytest` over the seven radar suites -> **253 passed**.
- Shared-helper and old-surface regressions --
  `test_vite_assets.py`, `test_radar_hub_page.py`, `test_gym_routes_smoke.py`,
  `test_radar_watch_api.py` -> **96 passed**.
- Dependency grep: no release file imports `hard_negatives`, `compare_judges`,
  `freeze_newshape`, `tone_training`, `train_encoder`, `checkpointing` or
  `sample_new_shape`. **Nothing needs one of the twelve**, so no minimal dependency
  has to be brought back for scope review.

Every number matches the foundations branch exactly, which is what "no dependency on
the excluded work" should look like.

**The whole backend suite, disclosed rather than only the release subset.** The
evidence above is seven radar suites plus four shared ones, which is what the
release touches. `pytest tests/ -q` over everything is **FULL_SUITE_RESULT**. Every
failure reproduces at the pre-release baseline `7a9ffe4`, so none is caused by the
transplant -- but the release evidence set is a subset, and saying so matters more
than the subset looking clean. Three of them are the long-recorded
`test_radar_ingest.py` cleanup defect (see the workspace/baseline gate above); the
rest predate this work in suites it does not touch, two of which
(`test_radar_watch`) sit on the watch cascade, a surface the hub shares.

### First-migration failure recovery, rehearsed (item 6)

P1 covered a failure inside `a7c31f0b52d4`. It did **not** cover a failure inside
`d82f9afb5898`, and the projection-column recovery does not apply there --
assuming one recipe fixes both is how an operator drops something they should not.

`scratchpad/rehearse_first_migration.py`, MariaDB 10.11.14, **25 checks, all
passing**:

- Interruption after each of statements 1, 2 and 3 of the four that
  `d82f9afb5898` issues (two `create_table`, two `create_index`, each
  auto-committing).
- Inspection correctly reports which tables exist, which are absent, and whether the
  index was created -- the operator looks rather than assumes.
- A blind re-run fails loudly with "already exists" in every case.
- Recovery drops **only the partial tables that are present**, and the rebuilt schema
  is **byte-identical** to a clean run on `SHOW CREATE TABLE` for both tables.
- **It refuses to drop a table holding records**, naming the count so the operator
  can judge, and the row survives the refusal.
- **It refuses to run at all when the stamp shows the first migration completed**,
  pointing at the projection-column procedure instead.

No blanket `DROP TABLE`, and no stamp-to-skip anywhere.

### The runbook

`RELEASE-RUNBOOK.md` is now the single authoritative execution path. The proposal's
own runbook section was removed, so there is no second procedure and no
hand-migration branch: `/root/update_coc.sh` is the sole migration owner.

It carries the read-only preflight, service **and timer** inhibition (including
`radar-encoder-trial.timer`, whose pre-existence does not make it irrelevant),
verification with wall-clock deadlines derived from the scheduler's own
configuration, durable rollback that survives the deploy script's hard reset, and
the two distinct failure-recovery procedures above.

### Access gates, still pending

Three steps cannot be completed from this workspace. Each is a stop, not a caveat.

| gate | what is needed |
| --- | --- |
| **The deploy script** | The full text of `/root/update_coc.sh`, plus `systemctl cat personal_apps_web radar_ingest radar-encoder-trial.{service,timer}`. Specifically whether the script stops `personal_apps_web` and whether it exits without restarting on a failed migration or build. A report of what it does is not evidence. |
| **Target preflight** | Read-only: `version()`, `@@version_comment`, `sql_mode`, isolation, charset/collation, `alembic_version`, and whether `radar_ingest_runs` and `radar_board_observations` are absent. Plus the deployed SHA and the capture flag as the unit actually sees it. |
| **Backup restore** | A consistent `personal_apps` backup with timestamp, producing engine version, checksum and scope, and a disposable MariaDB to restore into. Verification must compare against **that snapshot**, not against the still-changing live database. |

This workspace has never had production access and has not attempted it. The
rehearsal harnesses must never be pointed at a restored backup or anything live:
both drop their schema, and both refuse a non-loopback host for that reason.

For each completed step append commit, exact tests/results, reviewer findings, fixes/rulings and next step. Never mark an unrun check passed. Keep environmentally blocked tasks open with exact failure evidence. Takeover verifies this ledger against Git and reports.
