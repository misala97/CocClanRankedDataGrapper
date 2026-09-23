# HA1 US Daily Explore Implementation Plan

> For the later owner-selected Implementer: execute sequentially using the executing-plans discipline. User assignment overrides skill defaults: one worker, no automatic subagents, no commits or deployment. This document is a prepared prompt, not dispatch or current implementation authorization.

**Goal:** Add one usable retrospective Analysis/Explore path for selected mapped US-primary daily USD closes and independent retained chatter counts.
**Architecture:** Bounded existing-store reader with a dedicated authenticated route module and independent frontend query/cache. Reuse the real dark hub shell; keep data semantics outside the chart renderer.
**Tech stack:** Existing Flask/SQLAlchemy/MariaDB, React/TypeScript/TanStack Query, Vite/Vitest, pytest and Python Playwright. No new chart framework or schema required.
**Spec:** `HA1-US-DAILY-EXPLORE-SPEC.md` beside this file; carry it, the ledger and handoff together.
**Base:** `1ac39fe4e1a5dd7d04830e96a96563183687b447`.

## Global constraints

- 1–7 completed UTC dates; default seven, no hidden range widening or data-seeking shift.
- Explicit current company/instrument identity; native USD only in this slice; no cross-venue/FX/basis fallback.
- Missing is not zero; truncated counts are partial; config and ambiguous Reddit overlap remain visible. Never aggregate mention_z.
- Retrospective only; no return calculation, studies/replay/tone archive, providers or capture.
- Preserve Human Chatter ranking, DE/international behavior, legacy links, shared-board behavior, other apps/worktrees and B1C DB/port5021.
- No protected DB access or testing; no service changes, migrations, commits, pushes, deployment, automatic tasks or workers.
- Ledger statuses and fresh evidence determine what remains, not old handoff notices. Record exact candidate path/branch/HEAD, commands/results and environmental failures.

## T0 — Verify isolated workspace and carry continuity

Owner: Implementer after owner dispatch. No application files edited by this task.

- [ ] Read the complete spec, plan, ledger, current handoff and rulings; verify source worktree branch/HEAD/status/diff/log with `git -c safe.directory=<exact path>` if ownership requires it. Do not persist a global safe.directory change.
- [ ] Create the intended candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`, branch `codex/radar-ha1-us-daily-explore`, from exact base above. These names are proposed reserved destinations, NOT existing-worktree claims. If either exists, inspect Git/ledger first and resume only if it is this assignment; otherwise return the collision. No checkout/reset/clean of another workspace.
- [ ] Copy the explicit carry list below, preserving destination dirty files. Compare SHA256 source/destination before changing continuity. In the candidate's root/radar handoffs put a new current notice with the actual candidate path/branch/HEAD, ownership and first open task; preserve carried history.
- [ ] Inspect applicable AGENTS.md and existing test runtime. Identify an **independently registered, assignment-authorized disposable target** before any DB imports/queries/tests. No such target has been verified by this planner. Existing promotion launcher is read-only reference, not target authorization; never execute it for HA1.
- [ ] Record isolation/target gate separately: frontend and DB-free pure tests can proceed; DB integration and actual-app verification stay OPEN if no target is supplied. Do not invent registration/provision a DB to bypass the gate.

Exit: candidate identity/carry checks recorded, target safe or explicitly unavailable; no completed historical tasks redispatched.

## T1 — Pure analysis contracts and meaningful regression fixtures

Create `personal_apps/features/radar/analysis_contract.py` for validated range and pure aggregation; `personal_apps/tests/ha1_unit/test_analysis_contract.py` for DB-free tests. Avoid inheriting `personal_apps/tests/conftest.py` for this suite (run with `--confcutdir=tests/ha1_unit`). No app/DB/provider imports in this pure module. Use standard-library dataclasses/date/Decimal where useful; no dependency installation merely for this slice.

Interfaces owned here, all NEW:

```python
parse_range(args, now_utc) -> tuple[date, date]  # repeated-key-aware args
price_days(rows, instrument, company_first_seen, start, end, calendar) -> dict
chatter_days(rows, start, end, company_first_seen) -> dict
interior_missing(usable_dates: set[date], expected_dates: set[date] | None) -> list[date] | None
```

Return dictionaries serialize exactly to SPEC §4 price/chatter objects. `rows` are bounded mappings of named stored fields, never ORM objects requiring lazy reads. `calendar` returns modeled-open/closed/unknown for a date; its provenance is explicit. Raise a local typed contract exception with stable error code for bad input/resource limits. Date conversion is UTC and no local-machine date defaults enter the helper.

- [ ] Write failing tests from matrix C01–C10 below. Execute once and record expected missing-behavior failure, not an import/environment crash as proof.
- [ ] Implement strict date/ID/query validation and pure reducers. Iterate requested dates/slots; retain per-source counts and uncertainty, enforce sentinel/source caps. Exclude pre-first_seen buckets individually; partial first day retains partial identity coverage. Price close_date before first_seen UTC date is identity_unverified; same-day date precision cannot prove exact mapping time and remains disclosed.
- [ ] Implement interior missing using set membership, not outer-join row counts. Minimal oracle:

```python
def interior_missing(usable_dates, expected_dates):
    if len(usable_dates) < 2 or expected_dates is None:
        return None
    first, last = min(usable_dates), max(usable_dates)
    return sorted(d for d in expected_dates
                  if d is not None and first < d < last and d not in usable_dates)
```

Required examples with `date(2026, 9, day)` abbreviated as day:

```text
usable={8,9}, expected={8,9}      => []
usable={8,10}, expected={8,9,10}  => [9]
usable={8}, expected={8,9}       => null
usable={8,11}, expected=null    => null
```

- [ ] Rerun `py -3.12 -m pytest --confcutdir=tests/ha1_unit tests/ha1_unit/test_analysis_contract.py -q` from candidate/personal_apps, after verifying available runtime. Record exact runner if py alias differs. No DB or service needed; if imports open DB, fix test isolation before running.

Exit: deterministic fixtures reconcile counts and gaps, no statistical/provenance inference; T1 recorded complete only with results.

## T2 — Bounded authenticated reader and routes

Create `personal_apps/features/radar/analysis.py`, `personal_apps/features/radar/routes/analysis.py`, `personal_apps/tests/test_radar_analysis_api.py`; modify `personal_apps/features/radar/routes/__init__.py` to register new routes. No model/schema/history/detail/coverage changes.

Interfaces NEW: `resolve_company(ticker, now_utc) -> {company,instrument}`; `read_company(company_id, instrument_id, start, end, now_utc) -> AnalysisPayload`. They call T1 reducers. Resolve validates ticker syntax like current board ticker validation, length <=12, exact indexed identity only. Transport maps contract errors per SPEC §4; route auth follows `routes/api.py:668` and `auth.login_required`.

- [ ] Add API tests C01/C02/C11–C14 with provider/history/coverage/board builders made fail-if-called. Seed only on authorized disposable target with gate BEFORE importing app or executing SQL. Use bounded synthetic selected ticker fixtures, rollback/cleanup only assignment-owned records.
- [ ] Read company/instrument separately, then price and chatter with narrow selected projections. Representative query shape (bind parameters, do not paste literals into SQL):

```sql
SELECT close_date, close, currency, source, price_basis,
       adjustment_basis, fetched_at
FROM radar_daily_closes
WHERE ticker=:ticker AND market='us' AND mic=:mic AND is_shadow=0
  AND close_date>=:from_date AND close_date<=:to_date
  AND fetched_at<=:read_start
ORDER BY close_date LIMIT 8;

SELECT bucket_start, source, mention_count, status, source_config_version
FROM radar_bucket_sources
WHERE ticker=:ticker AND bucket_start>=:utc_start AND bucket_start<:utc_end
ORDER BY bucket_start, source LIMIT 43009;
```

Use SQLAlchemy equivalent and isolated-engine EXPLAIN; no FORCE INDEX copied from universe measurement. Limit+1 refuses overflow; never convert an incomplete read into availability. Do not filter unusable status/price metadata in SQL because invalid rows must remain distinguishable.
- [ ] Add statement-scoped MariaDB two-second timeout and five-second reader deadline, with session/connection state unchanged on pool return. Explicitly test SQL error, timeout, abort and fresh next request; 503 returns stable public code. Record dialect handling; SQLite mocks do not prove MariaDB timeout behavior.
- [ ] Revalidate mapping/ID at read, suppress pre-first_seen evidence with reasons, echo bounded read timestamps and exact requested range. No data mutation, provider calls, source expansion using today's config or board computation.
- [ ] Run the new API suite through the guarded runner specified under verification; inspect EXPLAIN/query count/row cap. Record unavailable target as an open gate, never a fake pass.

Exit: authenticated selected reads implement the exact transport; no data-dependent N+1, empty success on failure, or universe scans.

## T3 — Actual hub route, query lifecycle and Explore view

Create under `personal_apps/static/radar/src/hub/`: `analysisTypes.ts`, `analysisApi.ts`, `analysisQueries.ts`, `Analysis.tsx`, `AnalysisChart.tsx`, `analysis.css`, and corresponding `analysisApi.test.ts`, `analysisQueries.test.tsx`, `Analysis.test.tsx`, `AnalysisChart.test.tsx`. Modify `navigation.ts`, `navigation.test.ts`, `Hub.tsx`, `Hub.test.tsx`, and `queries.ts`/`queries.test.ts` only for Analysis board-poll gating. Existing `Search.tsx` interaction and global search API can remain unchanged; route its callback in Hub.

Interfaces NEW: TypeScript definitions matching SPEC §4; `fetchAnalysisResolve(ticker, signal)`, `fetchAnalysis(companyId, instrumentId, range, signal)`, `analysisKey(companyId,instrumentId,ticker,range)`, `useAnalysis(...)`. `Analysis` receives the route/range and navigation callback; `AnalysisChart` receives only payload/day selection, no fetch or local range aggregation. Parse `analysis_from/to` outside board Selection; urlFor preserves them only for Analysis routes and preserves board context independently. Extend HubRoute explicitly for unresolved and resolved Analysis; do not cast unknown page names into the union.

- [ ] Write failing navigation/API/lifecycle tests C01/C02/C12/C15; verify failure, then implement route parse/serialize, resolver canonical replace, range push/back/refresh. A canonical numeric ID pair plus ticker is checked against returned identity. Wrong ticker/ID never displays another company under old labels.
- [ ] Implement fetch AbortSignal/8-second timeout, typed HTTP errors, login redirect/content-type detection, no auto retries/polling/refocus fetch, 60s stale and five-minute GC, no previous-key placeholder. On session errors clear hub cache and render signed-out state. Empty price/chatter is a successful independent data state, not an HTTP error.
- [ ] Add actual Analysis nav and Page branch before board-dependent rendering. Disable recurring useBoard activity only on Analysis using a dedicated enabled input if visible=false alone does not disable the initial query; ensure returning to other pages resumes correctly. Retain shell bootstrap and unrelated pages' behavior. Suppress unrelated stale-board banners/market-session wording on Analysis in favor of explicit US-primary context.
- [ ] Build heading, controls, identity, separate plot panels, coverage/day detail and table as SPEC §3. Use existing .rh variables via new scoped stylesheet, not a CSS overhaul. Mark zeros as selectable baseline points/labels, unavailable as gaps, partial bars by pattern+text; selected detail exposes source/config values and basis. No return headline/score/tone.
- [ ] Test loading, error/manual retry, stale same-key refresh, session expiry, range/identity change race, keyboard, no-chart zero/one-close states and independent price/chatter availability with real-shaped fixture payloads.
- [ ] Run focused Vitest command below and `npm run build`. No npm install/update by default; report missing dependencies rather than changing lockfile incidentally.

Exit: C15/C16 component evidence plus build; no standalone mockup. Visual acceptance remains T4 until actual app screenshots inspected.

## T4 — Safe actual-app QA and bounded reader measurement

Create `personal_apps/scratchpad/ha1/local_runtime.py`, `personal_apps/scratchpad/ha1/verify_preview.py`, `personal_apps/scratchpad/ha1/probe_analysis.py` in the later candidate only, plus generated `radar-design/artifacts/ha1/` evidence. No edit/execute of earlier promotion/B1C launchers or production_smoke.py. Scripts guard exact independently authorized HA1 target before app import and any fixture operation, following destructive_target.require. Verify resolved root/branch, target and unused loopback port; bind only loopback with reload OFF, no ingestion/background jobs or provider egress. Proposed port 5041 is not reserved or verified; if occupied choose an unused local port and record it, never stop its owner.

- [ ] Run authenticated Flask endpoints with seeded valid/sparse/partial/config/identity cases in the actual candidate, not API mocks alone. Capture fixture provenance and mark all visuals “synthetic local acceptance data” in report.
- [ ] Use Python Playwright headless Chromium through shell; batch 1440x1000, 1920x1080, 768x1024, 390x844, 320x844 screenshots and assertions in one script. No embedded browser unless owner asks to interact live. View generated PNGs using the image-reading tool; JSON checks alone are not visual review.
- [ ] Verify navigation, search, explicit dates, refresh/back, DE-entry US-label honesty, one/no close, no chatter, observed zero, partial/truncated/config transition, price-source boundary, model-calendar warning, errors/retry/session expiry. Keyboard Tab/Enter/Arrow/Escape/day values, skip link, visible focus and 200% zoom; pointer selection and touch emulation. Check actual colors/contrast, label clipping and no document overflow. Report touch emulation separately from physical-device testing.
- [ ] Measure C13/C14 on isolated MariaDB with zero, typical and 43008-row/64-source fixtures, selected-only query plans, 20 warm requests per fixture and one cold request. Emit engine/hardware, median/p95, statements, rows read/returned, response bytes, allocation and timeout/cancellation evidence. No production extrapolation. A 43009th row is a separate refusal case.
- [ ] Run focused regressions once after final changes, inspect diff scope/whitespace, update ledger/handoffs and write `radar-design/HA1-US-DAILY-EXPLORE-IMPLEMENTATION-RETURN.md` with mandatory return prompt. Stop; do not dispatch reviewer.

Exit: bounded candidate ready for independent review OR precise environmental/product limitations returned with still-open gates. No “complete/release ready” if API/actual-app verification is missing.

## Acceptance matrix (test oracles, not measured population promises)

| ID | Fixture / action | Required result |
| --- | --- | --- |
| C01 | Fixed now Sep14; bare/default, Sep7–13, one day, reversed, 8 days, today/future, invalid leap date, duplicate/unknown args | Exact default; 1–7 completed days accepted; invalid input rejected before reads; no silent clamping |
| C02 | Unknown/delisted company; USD mapped unique US primary; two primaries; null IDs/MIC/provider; wrong/nonprimary/remapped ID | 404/422/409 as spec; no fallback; stale canonical link recoverable by explicit reselection |
| C03 | 0,1,2 adjacent closes and an interior missing date; weekend/holiday; unknown calendar | Independent empty/dot/points; adjacent no-interior = []; <2/unknown = null; edges not interior; official completeness unknown |
| C04 | Null source/basis/MIC, EUR/DE/shadow/zero/negative price, future fetched row | Invalid or excluded with correct reason; no splicing or phantom zero; valid selected price retained |
| C05 | A→B→A source, different basis; split-like jump with same stamp | Three segment runs; no cross-boundary line/return; no invented corporate-action event or validated-comparability claim |
| C06 | No source rows; 96 ok-zero slots; 95 ok plus absent; one ok-zero and one missing | null unavailable vs observed zero; partial-zero wording; missing source never borrowed from peers |
| C07 | ok3 + truncated2 + missing99; negative count; misaligned slot | retained count5 with partial coverage; missing99 excluded; invalid flagged, no silent zero or extrapolation |
| C08 | Two configs in day and across day boundary; null stamp; root Reddit + child same slot | Count/config evidence retained; transition warning; null config no full claim; pooled ambiguous day=null, breakdown intact |
| C09 | Source absent one day, retired source, root-only older Reddit, count data before first_seen | Historical source included; absent day unknown; no current-source filtering; pre-identity evidence excluded and marked |
| C10 | UTC midnight/DST boundary, data exactly at end, price close-date without time | Half-open chatter bounds; 96 UTC slots even DST days; end excluded; date not fabricated UTC price timestamp |
| C11 | Signed-out route/API, ordinary authenticated user, injection-style ticker/query | Existing auth enforced; no admin requirement; validation/binding and JSON escaping; no SQL/secret leakage |
| C12 | Slow A reply after selection B, range change, expiry/login HTML, retry failure | Correct key/identity always; old A never shown under B; cache cleared on expiry; honest failed refresh |
| C13 | Selected instrument amid unrelated fixtures; max input, extra sentinel/source | <=4 data SELECTs, index-constrained reads, <=43008 input rows, <=1MiB/32MiB, no global scan/provider/raw joins; overflow 503 |
| C14 | DB timeout/connection error; 20 warm max-fixture requests | 2s statement/5s reader bounds, 503 and no retry storm, clean pooled connection; p95<=1s local or reported failing gate |
| C15 | Root/alias/legacy, old t/filter links, invalid hash, Analysis canonical link, Back/refresh, DE entry | Existing bookmark semantics intact; Analysis identities/dates restore; board context stays independent; no Analysis board poll |
| C16 | Desktop/mobile/zoom, loading/error/empty/partial states, keyboard/day table | Correct actual-app rendering and text alternatives; no overflow/clipping; price/count timing and provenance visible |

## Commands and environment strategy

From **candidate/personal_apps**, after dependencies/runtime inspection:

```text
py -3.12 -m pytest --confcutdir=tests/ha1_unit tests/ha1_unit/test_analysis_contract.py -q
npx vitest run -c vite.radar.config.ts static/radar/src/hub/navigation.test.ts static/radar/src/hub/Hub.test.tsx static/radar/src/hub/queries.test.ts static/radar/src/hub/analysisApi.test.ts static/radar/src/hub/analysisQueries.test.tsx static/radar/src/hub/Analysis.test.tsx static/radar/src/hub/AnalysisChart.test.tsx
npm run build
py -3.12 scratchpad/ha1/local_runtime.py test
py -3.12 scratchpad/ha1/probe_analysis.py
py -3.12 scratchpad/ha1/verify_preview.py
```

The last three scripts are **planned files**, not current runnable capabilities. `local_runtime.py test` must first gate the bound target and then run `tests/test_radar_analysis_api.py tests/test_radar_hub_page.py tests/test_radar_board_sort.py tests/test_radar_search.py -q`. Do not run broad conftest-backed pytest directly against default app settings. Focused Human Chatter frontend suites `Chatter.test.tsx` and `ChatterWorkspace.test.tsx` must also run if Hub/query gating affects their lifecycle. Reviewer rechecks scope and relevant evidence; expand tests only for actual changed behavior/findings.

Prior `127.0.0.1:3399/personal_apps_radar_human_chatter_release` and port5033 were promotion evidence, not a guaranteed available HA1 environment. B1C `personal_apps_radar_b1c`/5021 and default `personal_apps`/3306 are protected. No DB provisioning, registration creation, broad deletion, migrations, Docker/service starts or production SELECTs authorized by this packet. If a safe HA1 target is absent, finish pure/frontend work and return the exact unavailable integration/preview gates; Mastermind can route one narrow environment assignment separately.

## Explicit carry manifest

Copy from `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion` into the candidate at the SAME relative paths before updating its handoff. Uncommitted documents do not follow git worktree creation. Copy these exact files, not the whole dirty tree:

```text
HANDOFF.md
radar-design/HANDOFF.md
radar-design/WORKFLOW.md
radar-design/MASTERMIND-STATE.md
radar-design/ASSIGNMENTS.md
radar-design/HA1-PLANNING-PROMPT.md
radar-design/HA1-US-DAILY-EXPLORE-SPEC.md
radar-design/HA1-US-DAILY-EXPLORE-PLAN.md
radar-design/HA1-US-DAILY-EXPLORE-LEDGER.md
radar-design/HA1-US-DAILY-EXPLORE-PLANNING-RETURN.md
radar-design/MD-01-ASSESSMENT.md
radar-design/MD-01B-RETURN.md
radar-design/MD-01B-RULING.md
radar-design/MD-01C-RETURN.md
radar-design/MD-01C-RULING.md
radar-design/HISTORY-ANALYSIS-PLAN.md
radar-design/HISTORY-ANALYSIS-LEDGER.md
radar-design/ROADMAP.md
radar-design/MARKET-DATA-ROADMAP.md
radar-design/HUB-PROMOTION-PLAN.md
radar-design/HUB-PROMOTION-LEDGER.md
docs/superpowers/specs/2026-09-10-radar-openterminal-comparison-REVIEW.md
```

Application code comes from exact Git base. Preserve all preview PNGs/scripts/logs/results in the source; no need to carry/execute them. Source paths remain reachable if reviewer needs historical evidence. No .env, DB, credentials, node_modules, ignored caches, other worktrees or production material copied. Compare source/destination hashes for all manifest files; record omissions as blocked, not silently stale. On base drift record delta and ask Mastermind for bounded reconciliation; no unrequested merge/rebase.

## Copy-ready Implementer prompt

```text
You are Radar's Implementer. Return your result to the Mastermind.
Assignment: HA1-US-DAILY-EXPLORE-IMPLEMENT.

This prompt is prepared, not dispatched. When the owner assigns it, implement only the binding HA1 slice below. Work sequentially yourself; no subagents or automatic tasks. Owner selects your model. An independent owner-selected Reviewer/QA follows your return; do not dispatch them or switch roles.

Planning source workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion
Source branch: codex/radar-hub-promotion
Verified source HEAD/local origin/main and implementation base: 1ac39fe4e1a5dd7d04830e96a96563183687b447
Source has no upstream and contains uncommitted planner documents and preserved preview artifacts.
Intended isolated candidate: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore
Intended candidate branch: codex/radar-ha1-us-daily-explore
Candidate is not created by this planning packet. Follow T0 collision/base/carry checks before editing. Do not implement in the planning source or main checkout.

Read completely, in order, from the planning source:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/WORKFLOW.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/MASTERMIND-STATE.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/ASSIGNMENTS.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/HANDOFF.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/MD-01C-RULING.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/MD-01C-RETURN.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/HA1-US-DAILY-EXPLORE-SPEC.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/HA1-US-DAILY-EXPLORE-PLAN.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/HA1-US-DAILY-EXPLORE-LEDGER.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion/radar-design/HA1-US-DAILY-EXPLORE-PLANNING-RETURN.md
Then read the carried history plan, market-data roadmap and OpenTerminal source review for continuity; their old status/scoring/prototype proposals do not override the current ruling/spec. Re-read the copied candidate handoff/ledger and verify Git/artifact hashes before implementing the first open task.

Objective: authenticated Analysis/Explore in the actual dark hub. Select a current company and explicit mapped native-USD US primary; show daily closes and independent UTC daily retained mention counts for 1–7 completed days, default seven. Preserve missing vs observed zero, truncated/config-transition/identity/basis limits. Retrospective only. Exact proposed routes, payload, query/deadline limits, UI and test oracles are SPEC §§3–7 and PLAN T1–T4/C01–C16. All new endpoints/helpers are to be implemented, not assumed to exist.

Accepted evidence: MD-01C Researcher reported Sep7–13 current catalogue 12,599 eligible, 12,294 daily available (12,075 >=2; 219 one; 305 none), 8,037 with buckets, 4,562 none, 2,146 positive mentions, no DE rescue. No global/long-history claim. Sequential production SELECTs were mutable; no independent rerun needed. Q4 195/225 gaps is provisional due synthetic NULL outer-join counting; do not use as oracle. Adjacent two closes/no interior date must produce zero interior missing dates. The local calendar is modeled, not authoritative. Price source/split stamps do not prove adjustment-vintage consistency.

Owned scope: exact NEW/modified files and interfaces in PLAN T1–T4, candidate progress ledger, root/radar handoffs and implementation return. Preserve carried planner history and unrelated dirt. Do not modify shared-board producer/ranking, existing history fallback, providers, schema, ingestion/capture, source config, B1C tone or other apps. Use existing tokens and patterns; no separate interactive prototype or redesigning-pages-from-data.

Authorized on owner dispatch: create the isolated candidate at the named base, explicitly carry manifest documents, local application/test/document edits for this slice, DB-free tests/build and guarded tests/preview on an independently authorized disposable HA1 target only. No target has been verified for you; do not infer authorization from an old launcher or registry. Gate exact target before app imports/SQL, keep registration independent. No provisioning/registry edits, migration, default or B1C DB, production/provider access, service changes, capture activation, commits, pushes, merge/rebase or deployment. Do not reuse promotion services/fixtures or port5021. If target absent finish independent work and return open integration/visual gates, not a fake pass.

Protected: all other worktrees/main checkout; B1C DB and port5021; promotion preview artifacts; PERF3/shared-board architecture and accepted latency; closed/live B/B1C/ranking/promotion. Capture OFF, shared boards ON and migration b7e3f9c1a2d4 are release-attributed facts, not permission to probe production. The 6.5-hour assumption stays out of scope.

Acceptance: C01–C16 with actual commands and outcomes; real-shaped API fixtures, selected-only EXPLAIN/row/query/deadline/latency evidence, typecheck/build, actual-app desktop/mobile/keyboard screenshots visually inspected using Python Playwright. Distinguish your fresh execution from historical reports and synthetic data from live evidence. No automatic broad testing loop or source research. Wider ranges/provider work remain a later packet MD-02/07 + MD-05 + MD-10, ahead of portfolio/news; MD-03/08 separate.

Stop after the candidate and evidence return, or a precise blocking finding after independent work is done. Do not deploy, commit, dispatch Reviewer or claim final acceptance. Update candidate ledger/HANDOFF and write C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore/radar-design/HA1-US-DAILY-EXPLORE-IMPLEMENTATION-RETURN.md (use actual verified candidate root if a Mastermind ruling changed it). List protected files, exact dirty ownership, remaining gates and next bounded recommendation.

MANDATORY: end your response with the following self-contained copy/paste prompt, replacing every bracket with actual evidence even when blocked:

You are Radar's Mastermind / Overview. Assess this Implementer return for assignment HA1-US-DAILY-EXPLORE-IMPLEMENT.
Workspace: [absolute candidate path]
Branch / base / current HEAD: [exact values]
Working tree: [all dirty/untracked paths and ownership; commit/push status]
Binding artifacts: [absolute candidate spec/plan/ledger/planning-return/implementation-return paths]
Objective and authorized scope: [bounded actual-app daily Explore summary]
Completed work: [T0–T4 status, not unverified completion]
Evidence: [exact test/build/probe commands, counts, engine/target, timings, query plans, inspected PNG paths and cases]
Evidence attribution: [your execution versus MD-01C/historical reports; synthetic versus production]
Findings and limitations: [severity/repro/open gates including calendar/identity/config/adjustment and environment limits]
Actions taken: [application/tests/docs; commits/push/deploy/config/service actions or explicitly none]
Protected state: [other worktrees/main/B1C/5021/preview artifacts/capture/shared boards/schema preserved]
Subagents: none
Updated artifacts: [absolute handoff/ledger/return paths, local/uncommitted]
Requested Mastermind decision: [accept for independent Reviewer/QA or rule on precise finding]
Next bounded action recommendation: [one owner-selected independent Reviewer/QA, or specific missing environment/fix gate; not dispatched]
Read current handoff and ledger completely, verify relevant Git/artifact evidence, make the product ruling and update continuity. Do not implement or deploy yourself.
```

## Independent review and later release

Mastermind assesses implementation return before owner selects a separate Reviewer with QA duties. Reviewer inspects source-bound identity, count algebra, regime segmentation, bounded query plans/failure handling, protected diff scope and actual-app evidence; executes only relevant safe checks and records attribution/gaps. Reviewer is read-only for application code, no fixes. Findings return to Mastermind for a bounded correction assignment; rerun changed/unresolved cases only. Deployer is a distinct later owner-authorized assignment after candidate disposition and actual-app owner review. No automatic release, model selection, commit or next-role dispatch is contained here.
