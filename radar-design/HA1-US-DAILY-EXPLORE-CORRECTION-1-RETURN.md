# HA1 US Daily Explore — CORRECTION-1 return

2026-09-15 · Assignment HA1-US-DAILY-EXPLORE-CORRECTION-1 · Radar Implementer (Claude Opus 5). Subagents/workers: none.

**Status: all ruled corrections (P1-1..P1-3, P2-1..P2-7, P3 integrity, P3 accessibility/layout, R3, R4/C11/C16, pinned-read ruling) implemented and DB-free verified. Runtime gates C02 (transport), C11, C13, C14, C15, C16 remain OPEN; no DB, preview, browser or harness was executed.** Not committed, pushed or deployed.

Command-level evidence and the per-finding table: `radar-design/artifacts/ha1/correction-1/evidence.md`.

## Git

- Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`; branch `codex/radar-ha1-us-daily-explore`; base = HEAD `1ac39fe4e1a5dd7d04830e96a96563183687b447`; no upstream; verified at start and end.
- Correction-modified existing HA1 files: `personal_apps/features/radar/{analysis.py,analysis_contract.py}`; `personal_apps/tests/ha1_unit/{test_analysis_contract.py,test_analysis_reader.py}`; `personal_apps/tests/test_radar_analysis_api.py`; `personal_apps/scratchpad/ha1/{local_runtime.py,probe_analysis.py,verify_preview.py}`; `personal_apps/static/radar/src/hub/{Analysis.tsx,AnalysisChart.tsx,analysis.css,analysisTypes.ts,analysisQueries.ts,analysisFixtures.ts,Analysis.test.tsx,AnalysisChart.test.tsx,analysisApi.test.ts,analysisQueries.test.tsx,Hub.test.tsx}`.
- Correction-new: `personal_apps/scratchpad/ha1/{ha1_harness.py,ha1_fixtures.py,preview_fixtures.py}`; `personal_apps/tests/ha1_unit/test_ha1_harness.py`; `personal_apps/static/radar/src/hub/analysisCss.test.ts`; this return; `radar-design/artifacts/ha1/correction-1/{evidence.md,pytest-ha1_unit.out.txt,vitest-focused.out.txt,contract_repro.after-correction.out.txt}`.
- Correction continuity edits (current notices / appended sections only): `HANDOFF.md`, `radar-design/HANDOFF.md`, `radar-design/HA1-US-DAILY-EXPLORE-LEDGER.md`, `radar-design/MASTERMIND-STATE.md`, `radar-design/ASSIGNMENTS.md`, `radar-design/HA1-US-DAILY-EXPLORE-CORRECTION-1.md` (status appended), `radar-design/artifacts/ha1/implementation-evidence.md` (dated correction appended).
- Preserved untouched: `routes/analysis.py`, `routes/__init__.py`, `analysisApi.ts`, `Hub.tsx`, `navigation.ts/.test.ts`, `queries.ts/.test.ts`, `tests/ha1_unit/__init__.py`; SPEC/PLAN, rulings, planning/implementation returns, REVIEW-RETURN and `artifacts/ha1/review/*`; all carried planner documents; other worktrees/main. Git-ignored `static/*/dist` rebuilt by `npm run build`.

## Fresh verification (this Implementer)

- `py -3.12 -m pytest -p no:cacheprovider --confcutdir=tests/ha1_unit tests/ha1_unit -q` -> `170 passed`.
- Focused Vitest (10 files incl. new `analysisCss.test.ts`, Chatter, ChatterWorkspace) -> `228 passed`.
- `npx tsc --noEmit` exit 0; `npm run build` passed; `py_compile` of 10 HA1 Python files OK; `git diff --check` exit 0.
- Reviewer's unmodified `contract_repro.py` rerun: slot partition 96, pre-identity-only source no longer represented.

## Unresolved findings and deviations

1. Runtime OPEN: MariaDB fractional `SET STATEMENT` acceptance, cancellation, same-connection hygiene, EXPLAIN plans, row/byte/allocation/p95 budgets, 65-source and 43,009-row refusals on an engine, non-admin HTTP, every C15/C16 screenshot/keyboard/zoom/touch/contrast check. Harness code is static and unit-tested only; it needs independent focused review before any execution.
2. Budget limits disclosed, not solved: pool connection wait, result transfer and prompt server-side cancellation are outside the statement limit until runtime proof.
3. Additive clarifications needing ruling (evidence §Additive): `excluded_rows`; narrowed `invalid_slots`; represented-source denominator; resolve `gcTime 0`; text date inputs; ms-floor statement limits; harness loopback/port refusals and runtime nonce header.
4. Non-admin production policy: `app.py` full-access host gate refuses non-admins on the whole radar blueprint; Analysis adds no admin rule. Mastermind may want to confirm this is the intended product scope.
5. `local_runtime.py test` no longer runs `test_radar_hub_page.py` or `test_radar_search.py` (unsafe fixture ownership, out of HA1 scope to rewrite); legacy route/bookmark runtime coverage for C15 therefore relies on component tests plus `verify_preview.py` until those suites are separately fixed.
6. Day buttons on phones reach 44 px width through an in-panel horizontal scroll box (≤560 px); rendered behaviour unverified.
7. The timeout probe's CPU statement size (BENCHMARK 50M SHA2) is an estimate; too-fast hardware would false-fail, never false-pass.
8. Not rerun: whole radar Vitest and the 28 prior `pending.test.tsx` failures (Implementer-reported, base-reproduced, out of scope).

## Protected state / actions not taken

No DB/provider/production access, no API integration/probe/preview/browser execution (a tool hook's preview suggestion was declined per assignment), no provisioning/registry/service/migration change, no commits/pushes/deploy, no workers. Main and other worktrees, B1C DB/5021, default DB 3306, promotion DB/3399/5033 and all prior artifacts untouched. Capture OFF / shared boards ON / migration `b7e3f9c1a2d4` remain release-attributed, not probed.

## Requested decision

Assess corrections and prepare an independent focused Reviewer/QA prompt over this delta (corrected harness first). Keep the DB/preview hold until that review and a separately authorized disposable HA1 environment.
