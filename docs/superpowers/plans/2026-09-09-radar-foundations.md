# Radar Recording Foundations Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Implement one task at a time, followed by an independent read-only review. Update the per-plan ledger before switching sessions. Claude implements; Codex owns planning and resolves product/spec changes.

**Goal:** Begin honest operational recording and preserve a bounded history of board observations without changing current research behavior.

**Architecture:** Add append-only observation tables and small recorder modules beside existing Radar services. The ingest runner records run outcomes; a separate scheduler job records a fixed pair of viewer-independent boards. Read APIs expose recorded activity and existing operational summaries.

**Tech Stack:** Existing Flask, SQLAlchemy, Alembic, MySQL, APScheduler, pytest.

**Spec:** `radar-design/IMPLEMENTATION-SPEC.md` (repository-root relative).

## Global Constraints

- Missing measurements remain missing; zero means measured zero.
- UTC instants travel with explicit timezone; display Europe/Berlin and state the selected price market and currency.
- No production deployment or live database migration is included in this handoff.
- Preserve unrelated changes, including discovery scripts, source candidates, classifier artifacts, and other apps.
- All constraints in the binding spec apply. Recording changes must not redefine extraction, sentiment, ranking, or existing retention.

## Entry gate: establish the implementation workspace

- [ ] Read `radar-design/HANDOFF.md`, this plan, the binding spec, and `radar-design/FOUNDATIONS-LEDGER.md` completely.
- [ ] Inspect root AGENTS.md and feature instructions. Old product exclusions are superseded by the new spec; engineering constraints still apply.
- [ ] Run `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, `git log -5 --oneline`, and inspect the actual diff. Planning baseline was dev_personal at 7a9ffe445076e57d02fea5627e8cd185ec9cb39f. Record drift; do not reset it.
- [ ] Create an isolated implementation worktree using the worktree skill on a `codex/radar-foundations` branch, or continue the exact existing worktree recorded in the ledger. Never create a duplicate after a takeover. Copy the untracked radar-design package into that worktree if it is not yet committed. Record absolute source and destination paths, and commit only the planning package there before implementation so another session can retrieve it.
- [ ] Read `personal_apps/tests/conftest.py` and `personal_apps/app.py` before testing. The database selector is PERSONAL_DB_NAME, not DB_NAME. app.py calls load_dotenv(override=True), so shell overrides alone do not prove isolation. Configure the isolated worktree's untracked .env for a disposable database, then assert the resolved engine database name before tests or schema changes. Record its nonsecret name. Never copy credentials into reports or run migrations against the working/live database by inference.
- [ ] In personal_apps, run baseline `npm test` and `npm run build`; run existing `py -3.12 -m pytest tests/test_radar_watch_api.py tests/test_radar_api.py -q` only against the verified test database. Record exact failures; do not call them pre-existing without before-change evidence.

## Task F1: persist ingest-run outcomes

**Files:** Modify `personal_apps/models.py`, `personal_apps/run_radar_ingest.py` (`tick`); create `personal_apps/features/radar/activity.py`, `personal_apps/tests/test_radar_activity.py`, and `personal_apps/migrations/versions/<generated_revision>_add_radar_observations.py`. Alembic must generate the revision against the actual single current head; do not invent a down_revision.

**Interfaces:** `start_run(now: datetime) -> str`; `finish_run(run_id: str, now: datetime, *, summary: dict | None, error_code: str | None) -> None`. Each recorder owns its transaction, does not commit pending ingest work, and uses an independent SQLAlchemy session bound to db.engine. Start returns a UUID even if persistence fails; recorder failures log a stable message and do not prevent ingestion. Terminal update is idempotent; an existing completed run cannot change its totals.

- [ ] Add model/migration tests verifying nullable summary, unique UUID, status fields, and upgrade/downgrade of only the two new tables. Define the second table from F2 in this same additive migration; implement it without altering existing tables.
- [ ] Add a contract test for idempotency and failure representation. Use a test-owned run and remove only that run during cleanup:

```python
def test_error_has_no_manufactured_counts(app_context):
    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    activity.finish_run(run_id, dt.datetime(2026, 9, 9, 12, 1),
                        summary=None, error_code='ingest_failed')
    run = db.session.get(RadarIngestRun, run_id)
    assert run.status == 'error'
    assert run.summary_json is None
```

`app_context` is a new fixture in this test module wrapping `flask_app.app_context()`; import flask_app from app, dt from datetime, activity from features.radar, db from extensions, and both models from models. Use the verified disposable DB. Add success twice with the same run_id and assert totals remain unchanged; mock recorder DB failure and assert tick still invokes ingest once.
- [ ] Run `py -3.12 -m pytest tests/test_radar_activity.py -q`; confirm failures name the unimplemented contract, not DB connectivity.
- [ ] Implement tables exactly as specified. In tick, place start before ingest; record finish in both success and exception branches, preserving existing return shape and log behavior. Use actual finish wall time. Do not map existing error-return zero fields into stored counters.

```python
run_id = activity.start_run(now_utc.replace(tzinfo=None))
# Existing ingest try/except remains the source of truth.
# Success branch:
activity.finish_run(run_id, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                    summary=summary, error_code=None)
# Exception branch, before the existing return:
activity.finish_run(run_id, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                    summary=None, error_code='ingest_failed')
```

- [ ] Run `py -3.12 -m pytest tests/test_radar_activity.py tests/test_radar_ingest.py -q`. Add tick integration cases in test_radar_activity.py because no separate runner suite was found. Verify failed recorder does not roll back successful intake or stop later cycles.
- [ ] Commit only F1 files. Independent reviewer checks transaction isolation, definition of each counter, migration head, and failure containment. Record commit and findings before F2.

## Task F2: archive fixed board observations

**Files:** Create `personal_apps/features/radar/observations.py`, `personal_apps/tests/test_radar_observations.py`; modify `personal_apps/run_radar_ingest.py` scheduler registration. The model and additive migration are from F1.

**Interfaces:** `capture(now: datetime, *, producer_revision: str | None = None) -> bool` returns true when it persisted a new complete pair, false for an existing slot. Exceptions are contained by the scheduler wrapper, logged, and leave no row. `latest_observed_at() -> datetime | None` is a DB-only read. Configuration reads RADAR_OBSERVATION_CAPTURE_ENABLED and RADAR_PRODUCER_REVISION; no subprocess Git commands per cycle.

- [ ] Test captured query parameters and exclusion of private/operational fields using a monkeypatched `routes.api.build_payload`. Verify missing one market inserts nothing, repeat slot inserts once, next slot inserts a second row, and a late capture retains its actual observed_at.

```python
def test_slot_is_immutable(app_context, monkeypatch):
    monkeypatch.setattr(observations, 'build_payload', lambda args, **kw:
                        {'market': args['market'], 'rows': [], 'watching': ['PRIVATE']})
    now = dt.datetime(2026, 9, 9, 12, 1)
    assert observations.capture(now, producer_revision='test') is True
    assert observations.capture(now, producer_revision='changed') is False
    record = RadarBoardObservation.query.filter_by(
        slot_start=dt.datetime(2026, 9, 9, 12)).one()
    assert record.producer_revision == 'test'
    assert 'watching' not in record.payload_json['us']
```

Use test-owned dates and cleanup only the test rows. `app_context` follows F1's fixture definition, copied into this module or a narrow shared Radar fixture module.
- [ ] Run `py -3.12 -m pytest tests/test_radar_observations.py -q` and inspect intended failures.
- [ ] Implement normalization and capture. Do not pass the slot boundary as now when building; it would misrepresent observation time:

```python
slot = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
queries = {market: {'market': market, 'sources': ','.join(SOURCES),
                   'segment': '', 'window': '24', 'venues': '1'}
           for market in ('us', 'de')}
excluded = {'watching', 'watch_rows', 'spend', 'sentiment_ops', 'market_data_ops'}
payloads = {market: {k: v for k, v in build_payload(query, now=now, user_id=None).items()
                     if k not in excluded}
            for market, query in queries.items()}
```

The existing serializer reads ops as a side effect; do not archive those results. Check resulting payload generated_at: the board uses a 60-second cache, so observed_at is capture time while generated_at remains board time. Do not rewrite it. Enforce unique slot in SQL and treat only that unique conflict as idempotency; unrelated DB errors remain errors. Roll back only the recorder session.
- [ ] Register a separate job with a stable ID `radar_board_observations`, interval minutes=15, max_instances=1, coalesce=true. Disabled by default. Use app context and contain exceptions. Do not put it in tick or score_all.
- [ ] Run focused tests plus scheduler tests. With the test scheduler, simulate capture failure followed by normal ingest; verify ingest still executes. Measure row size from a representative staging capture and record it without claiming production capacity.
- [ ] Commit F2; independent review checks immutability, configured sources, null/provenance preservation, no user data, and no claims of full replay capability.

## Task F3: activity and admin read APIs

**Files:** Extend `activity.py`; create `personal_apps/features/radar/routes/operations.py`, `personal_apps/tests/test_radar_operations_api.py`; modify `personal_apps/features/radar/routes/__init__.py` to register the module.

**Interfaces:** `activity.summary(now: datetime, days: int) -> dict`; endpoints exactly as binding spec. Ops keys: generated_at, spend, sentiment, market_data, capture. Capture contains latest_observed_at. Activity daily keys: date, posts_seen, posts_new, mentions, buckets_written, completed_runs, incomplete_runs, error_runs, completeness. `completeness='partial'` when completed runs exist, otherwise `'unknown'`; none of these proves full source coverage.

- [ ] Write API tests: invalid days=2 returns400; anonymous cannot read activity; nonadmin ops returns403; admin can read ops; no runs gives null counters; one successful empty run gives zero; error/running rows do not add zeros; Berlin DST transition bounds are 23/25 hours as applicable. Use two temporary test users for auth, following auth.py session user_id and existing ownership tests; cleanup only users created by this test.

```python
def test_activity_rejects_unsupported_window(client):
    assert client.get('/radar/api/activity?days=2').status_code == 400

def test_empty_day_is_unobserved(client):
    payload = client.get('/radar/api/activity?days=1').get_json()
    # Freeze now and isolate run rows for the test's Berlin day.
    assert payload['days'][0]['posts_seen'] is None
    assert payload['days'][0]['completeness'] == 'unknown'
```

- [ ] Confirm tests fail for missing routes/contracts. Implement days validation before querying; construct Berlin midnight boundaries using zoneinfo.ZoneInfo('Europe/Berlin'), convert to UTC for DB comparison. Assign runs by started_at date and describe that in API documentation; incomplete runs remain in that day. Never infer a day's time span by subtracting 86400 seconds.
- [ ] Decorate activity with login_required and ops with admin_required. Serialize datetimes with explicit Z. For ops call existing spend.summary(), llm_sentiment.ops_summary(), market_data.ops_summary(now), observations.latest_observed_at(). Do not add new remote fetches.
- [ ] Run F1–F3 tests and existing Radar API/watch tests. Verify migration upgrade/downgrade/upgrade on the disposable DB, preserving an existing watch row. Record exact counts and environment failures.
- [ ] Commit and obtain independent review. Update FOUNDATIONS-LEDGER.md and HANDOFF.md. Completion means reviewed code and test evidence, not deployment. Capture remains disabled until a separate staging rollout enables it.
