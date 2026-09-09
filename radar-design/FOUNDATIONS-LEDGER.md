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
- **Known limit, accepted deliberately:** the day query selects three columns rather than whole ORM
  rows, but still transfers each run's `summary_json`. At a 15-minute cadence `days=30` is ~2,880
  envelopes, each carrying a per-source map -- single-digit MB per request on a `login_required`,
  uncached endpoint. Extracting the four counters in SQL would remove the transfer and was not
  taken: it needs JSON path functions whose behaviour on the production MariaDB cannot be verified
  from this environment. Worth revisiting with a measurement against the real server.
- Documented rather than changed: the admin gate on `/api/ops` is a front door, not a new wall --
  `/api/board` already serves `spend`, `sentiment_ops` and `market_data_ops` to any signed-in
  reader, and the spec explicitly defers removing them.

For each completed step append commit, exact tests/results, reviewer findings, fixes/rulings and next step. Never mark an unrun check passed. Keep environmentally blocked tasks open with exact failure evidence. Takeover verifies this ledger against Git and reports.
