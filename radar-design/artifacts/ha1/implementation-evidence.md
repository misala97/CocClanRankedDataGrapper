# HA1 implementation evidence — fresh execution 2026-09-15

Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`, branch `codex/radar-ha1-us-daily-explore`, HEAD = base `1ac39fe4e1a5dd7d04830e96a96563183687b447`, nothing committed. Every line below is this Implementer's own run in this candidate unless marked otherwise. All data in tests is synthetic; no production, provider or protected database was touched.

## T0

- `git worktree add -b codex/radar-ha1-us-daily-explore .worktrees/radar-ha1-us-daily-explore 1ac39fe4...` -> `HEAD is now at 1ac39fe`; no pre-existing directory or branch.
- 22 manifest files copied; `sha256sum` source vs destination: 22 OK, 0 mismatch.
- Gate: `RADAR_DESTRUCTIVE_TEST_TARGET` and `RADAR_DESTRUCTIVE_TEST_REGISTRY` unset; `netstat -an` showed only `0.0.0.0:3306` (protected default) listening among 3306/3399/5021/5041. No HA1 target -> DB integration and actual-app gates OPEN.
- `npm ci --no-audit --no-fund` (exit 0) from the existing `package-lock.json`; lockfile unchanged.

## T1 — `tests/ha1_unit/test_analysis_contract.py`

- First run (module absent): `ImportError: cannot import name 'analysis_contract' from 'features.radar'` — collection error, i.e. the expected missing-behaviour failure.
- After implementation: `65 passed in 0.38s` (one fixture bug in the test file fixed on the way: `Decimal(None)`).
- Covers C01 (default/1-7 days/reversed/8 days/today/future/leap/duplicate/unknown/missing/id), C03 (planner oracle incl. adjacent-two-close = [], edges, unknown calendar = null), C04 (invalid vs excluded rows with reasons/provenance), C05 (A->B->A three runs; no event inferred from a jump), C06-C09 (unavailable vs observed zero, 95+absent partial, ok/truncated/missing, negative/misaligned/unknown-status invalid, config transition in-day and across days, null stamp, bare-reddit/child overlap, retired/root-only sources, pre-first_seen slot exclusion), C10 (half-open bounds, 96 slots on a DST day, date not a timestamp), plus 65-source/43,009-row limits and duplicate-key rows.

## T2 — reader

- `tests/ha1_unit/test_analysis_reader.py` (fake store): `30 passed` within the `95 passed in 1.08s` ha1_unit run. Covers resolve 404/409/422/400 and read 404/409/422, statement order company->instrument->closes->buckets, sentinel 503 `analysis_limit`, store failure 503 `analysis_unavailable` with rollback and no SQL in the message, deadline abort, unknown-MIC calendar warning, dialect-specific timeout syntax (`SET STATEMENT max_statement_time=2 FOR ...` on MariaDB; hint on MySQL; none on SQLite).
- Routes registered (import only, no connection): `['/radar/api/analysis/company/<int:company_id>', '/radar/api/analysis/resolve']`.
- `tests/test_radar_analysis_api.py` written and compiles; module-scoped autouse gate calls `radar_disposable.require` before the conftest admin lookup. NOT executed: no authorized target. `py -3.12 scratchpad/ha1/local_runtime.py test` -> `HA1 target not authorized: ... nothing was bound`.

## T3 — frontend

- `navigation.test.ts` before routing change: `6 failed | 32 passed`; after: `38 passed`.
- Focused suite (navigation, Hub, queries, analysisApi, analysisQueries, Analysis, AnalysisChart, Chatter, ChatterWorkspace): `Test Files 9 passed (9)`, `Tests 210 passed (210)`.
- Whole radar Vitest: `Test Files 1 failed | 48 passed (49)`, `Tests 28 failed | 777 passed (805)`; the failing file is `pending.test.tsx`. Baseline check in the untouched planning-source worktree (same base, application files clean): `28 failed | 30 passed` in the same file — pre-existing, not from this slice.
- `npx tsc --noEmit`: clean. `npm run build`: passed (`built in 1.99s`, `built in 1.85s`).
- `git diff --check`: clean (CRLF autocrlf warnings only).

## T4 — open

- `scratchpad/ha1/{local_runtime.py,probe_analysis.py,verify_preview.py}`: `py_compile` OK; each refuses before importing the app without `RADAR_HA1_TARGET` + `RADAR_HA1_REGISTRY`. Python Playwright 1.61.0 is installed locally.
- No screenshots, EXPLAIN plans, latency, allocation, timeout-cancellation or 43,009-row evidence exists. These remain gates, not passes.

## Attribution

MD-01C coverage figures are the Researcher's production report and were not rerun. No production, VPS, provider, B1C, port 5021/5033, migration, capture or service action of any kind.

## Dated correction — 2026-09-15, HA1-US-DAILY-EXPLORE-CORRECTION-1

The T4 line above ("each refuses before importing the app without `RADAR_HA1_TARGET` + `RADAR_HA1_REGISTRY`") was unsupported for `verify_preview.py`: that version refused only on missing `RADAR_HA1_USER`/`RADAR_HA1_PASSWORD` and checked neither the HA1 target/registry nor the listening server's identity (REVIEW-1 R4). It was accurate for `local_runtime.py` and `probe_analysis.py`. The historical text above is preserved unchanged. The corrected `verify_preview.py` gates first; see `radar-design/artifacts/ha1/correction-1/evidence.md`. None of the three scripts has been executed.
