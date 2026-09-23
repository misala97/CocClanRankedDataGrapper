# MD-SELECTED-PRICE-IMPLEMENT-1 — Implementer return

2026-09-15. Radar Implementer (Claude Opus 5), one worker, no subagents. Return to the Mastermind.

## Summary

Selected US stock charts in Research and the Human Chatter research panel now have an additive, flag-gated contract: a 1D chart of the current or last modeled session including extended hours, a genuine five-session 1W chart of regular-session bars, and chatter counts with retained tone for exactly the same window at their own resolution. Unknown stays unknown, gaps stay gaps, adjustment basis stays unknown, bar closes are placed at bar end, and the fallback is one coherent stored dataset. Yahoo I/O never runs on the request thread: a per-process coordinator admits at most one supervised spawn child with a 6 s deadline, bounded body/result/cache, rolling start limits and a Retry-After-aware backoff, reported as process-scoped ops health. Headline quote, scores, poller, German behaviour, longer spans, HA1 and the legacy chart are unchanged. Both flags default off. Everything is local and uncommitted; the evidence is deterministic and fixture-based.

## Workspace

- Candidate: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
- Branch codex/radar-selected-price-charts; base = HEAD daadf3868caedcb5db858378e919cba68b735f8a; no commit, push, merge or deploy.
- Source (read/copy only): C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore, codex/radar-ha1-us-daily-explore at daadf38 before and after; its diff stat and dirt unchanged; 23/23 carry originals byte-identical at return.
- Carry: carry-manifest.json, 23/23 SHA-256 match at copy time.

## What changed (application and tests)

Modified (16): personal_apps/features/radar/config.py (two default-off flag functions), prices/yahoo.py (additive `cache`/`max_body_bytes` options and `fetch_chart_bounded`; defaults unchanged), routes/__init__.py (register), routes/operations.py (`selected_price_ops`), routes/views.py (shell flag); static/radar/src/detail/ChatterHistogram.tsx (export `TONE_COLORS` only), entries/hub.tsx (read shell flag), hub/Hub.tsx (context provider), hub/Research.tsx and hub/ChatterWorkspace.tsx (pass selection/visible), hub/ResearchContent.tsx (ChartSection chooses the new chart atomically, else the original), hub/queries.ts (`usePriceChart`, polling policy), hub/Admin.tsx + Admin.test.tsx (process-health panel), types.ts (optional ops field); tests/test_radar_operations_api.py (exact ops key set + `selected_price_ops`).

Added (27): features/radar/price_chart_contract.py, price_chart_reader.py, price_chart_acquisition.py, price_chart_fetch.py, routes/price_chart.py; hub/priceChart.ts, SelectedPriceChart.tsx, selectedPriceGeometry.ts, selectedPriceContext.ts, selected-price.css, priceChartFixtures.ts and tests priceChart.test.ts, selectedPriceGeometry.test.ts, SelectedPriceChart.test.tsx, SelectedPriceSection.test.tsx; tests/selected_price_unit/ (helpers, child_targets, eight test modules, fixtures/yahoo_saved_arrays.json copied from the saved research arrays).

Generated: static/radar/dist (Git-ignored) — hub-BtAJD2zg.js, hub-CfTgC9Wd.css, manifest. Gym build not run.

Routine decisions D1–D23 are in radar-design/artifacts/md-selected-price-implementation/decisions.md (e.g. tone SQL mirrored in the reader with SQLite parity tests instead of editing chatter_tone; receipt-time provisional bars; identity mismatch cooled 15 min; every daily close a separate dot; context-based flag; one-line ops test update).

## Acceptance matrix

| ID | Outcome | Proof (executed unless stated) |
| --- | --- | --- |
| P01 | PASS | Reader/route tests: unknown/delisted 404, zero/two/ineligible 422, invalid ticker 400, identity before admission and data reads, revalidation each request, mapping change misses cache; class-share symbol mapping and refusal of other forms; no mapping mutation |
| P02 | PASS | Hand-written UTC expectations: Tue 03:59/04:00/09:29/09:30/16:00/20:00 ET, weekend, Labor Day, 2026-11-27 early close, DST end, lookup bound, slot anchoring |
| P03 | PASS | Saved AAPL/GE/BRK.B arrays + synthetic meta: null gaps, off-grid omission, provisional from receipt, missing session, one point, identity/NaN/overflow refusals; geometry aligns different-length arrays by instant |
| P04 | PASS | Slots: observed/partial/unknown, duplicates, malformed, missing/truncated, Reddit overlap, config change, identity floor, bounds; tone reconciles to new totals; expired/conflicting/mismatched evidence unavailable; SQL classification parity on SQLite |
| P05 | PASS | One-source quote fallback, exclusions, daily-close dots, overflow refusal, no splicing, cache age/stale; stale/fallback/long browser states |
| P06 | PASS (local) | Real spawn: normal 0.81 s, bad-spec production child 0.77 s, hanging child killed at 6.22 s supervisor time, oversized cut at 1.11 s; request admission <1 ms; busy other key; fake-clock rolling cap, per-chart interval, cooldowns, Retry-After ladder/day cap, LRU/bytes, quarantine on unconfirmed cleanup |
| P07 | PASS (DB-free) | Minimal Flask app with the real blueprint: flag off 404 `feature_disabled`, signed-out 302 before work, only span/market/sources, store failure 503 with code, pending→ready, shell sends only the chart flag, ops admin-only and never creates/starts anything; existing Yahoo/tone/HA1 tests unchanged |
| P08 | PASS (fixture) | Built hub, both surfaces, 1440/768/390/320 and real 200% zoom: 57 cases, 744 checks, 0 failures; keyboard, overflow, dates, end label, request form, stale switch, 422 fallback, headline identical flag on/off; screenshots viewed |
| P09 | PARTIAL, disclosed | ≤6 cold SELECTs, ≤1 s statement cap in a 3 s budget, sentinels, MariaDB `SET STATEMENT` prefix captured, SQL executed on SQLite; no MariaDB runtime; live Yahoo request form not run |

## Evidence

radar-design/artifacts/md-selected-price-implementation/evidence.md has commands, counts and logs. Headlines:
- Baseline before edits: DB-free Yahoo/tone/HA1 269 passed, 1 skipped, 3 failed (date-dependent `test_radar_yahoo.py` daily-close tests); Radar Vitest 799 passed, 28 failed (`hub/pending.test.tsx`).
- `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` → 139 passed.
- Regression after: 269 passed, same 3 failures.
- `npx tsc --noEmit` → 0. `npx vitest run -c vite.radar.config.ts` → 847 passed, same 28 failures. `npx vite build -c vite.radar.config.ts` → 0.
- `verify_browser.py` run 3 → 0 failures; results.json, 109 PNGs.
- `git diff --check` clean. Fingerprint 218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159.

Attribution: all of the above executed by this worker locally. Yahoo arrays are the Researcher's saved 2026-09-15 capture reused as input; all other fixtures synthetic. No live provider, DB or production evidence exists in this return.

## Findings and limitations

1. Live provider unverified: the `period1/period2` form, closed-session, overnight, holiday, throttling and body-size behaviour of Yahoo were never requested. Research only tested `range=1d/5d`; no equivalence is claimed.
2. Usage condition carried unchanged from the ruling: automated Yahoo collection permission is not established; nothing here activates the source.
3. DB runtime unavailable: no MariaDB binary outside the protected HA1 environment; statement timeout firing, cancellation, plans and pool behaviour unverified. DB-backed suites (including the updated `test_radar_operations_api.py` key-set test and hub page tests) not run.
4. Limits are per web process: N workers allow N children and N× start caps; ingest daemon Yahoo traffic is separate; restarts reset counters. Spawn startup (~0.8 s here) counts inside the 6 s deadline. Supervisor deadlines are not an HTTP end-to-end guarantee.
5. Spawn re-imports the parent's `__main__` file in the child; harmless under gunicorn/pytest, but a dev server run as `python app.py` would execute that script's unguarded top level in the child (D17).
6. The tone aggregation now exists twice (chatter_tone ORM and reader SQL); parity is tested, but they must be kept in sync.
7. UX observations for review: the spec's continuous 1W axis gives most width to closed time, so session price segments are narrow; when a source is represented only briefly, every slot is `partial` and amber outlines dominate (visible in the `long` fixture); real-zoom top-anchored captures frame the headline (focus captures show the chart).
8. The ticker detail request still carries its own 1D/1W chart arrays, unused when the new chart draws (contract deliberately unchanged).
9. Pre-existing failures untouched: 3 Yahoo daily-close date tests; 28 `pending.test.tsx` tests.

## Actions and protection

Created the worktree/branch and copied the carry; implemented and tested locally; copied `node_modules` from the source workspace (no install/download); ran an in-process loopback server on 5042 and Chromium (headless and headed-offscreen for zoom), all stopped; no spawned child or QA process left. No commit, push, merge, deploy, production/DB access, live provider request or original probe script execution; no secrets read. Protected and untouched: source workspace and its dirt, main and other worktrees, B1C/5021, promotion/5033, databases 3306/3399, HA1 runtime/3461, C:/Users/michi/.radar-ha1-local-qa.

## Requested decision and next action

Accept the candidate for one focused independent Reviewer/QA of the changed scope with the limitations above recorded as release carries. Next bounded action: owner-selected Reviewer/QA on this candidate at fingerprint 218c1a53…2159 — no repeat of HA1 or research review, no provider activation or deployment.

## Copy/paste return prompt

```text
You are Radar's Mastermind / Overview. Assess the Implementer return
for MD-SELECTED-PRICE-IMPLEMENT-1.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts /
daadf3868caedcb5db858378e919cba68b735f8a / daadf3868caedcb5db858378e919cba68b735f8a
(verified at return; nothing committed).
Working tree: worker-owned, uncommitted: 16 modified + 27 added application/test
files under personal_apps (listed in the return), Git-ignored generated
personal_apps/static/radar/dist (hub-BtAJD2zg.js, hub-CfTgC9Wd.css),
radar-design/artifacts/md-selected-price-implementation/, the current notices in
HANDOFF.md and radar-design/MD-SELECTED-PRICE-LEDGER.md, and
radar-design/MD-SELECTED-PRICE-IMPLEMENT-1-RETURN.md. All other dirty/untracked
radar-design and docs files are the 23-file planner carry copied unchanged
(carry-manifest.json 23/23 SHA-256). Source workspace
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore unchanged
at daadf38 with its dirt preserved. No commit, push, merge or deploy.
Binding spec / plan / ledger / return:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-SPEC.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-PLAN.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-LEDGER.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-IMPLEMENT-1-RETURN.md
Objective and authorized scope: in an isolated candidate, implement the owner-
approved selected US stock chart for Research and the Human Chatter research
panel: 1D current/last modeled session incl. extended hours, genuine 1W of five
modeled regular sessions with explicit dates and partial today, chatter/retained
tone for the same window, honest coherent stored fallback, and bounded off-request
Yahoo acquisition with process-scoped health; Yahoo-only mapped US primary USD;
two default-off flags; headline, scores, poller, German, longer spans, HA1 and
legacy chart unchanged. Local deterministic implementation and fixture QA only;
no live provider, production, DB reuse, commits or deployment; one worker, no
subagents.
Completed work: all three PLAN tasks. Pure contract (windows/bands/slots, Yahoo
bar normalization, quote/daily fallback, chatter slots and tone reconciliation,
v1 assembly); bounded reader on HA1's SqlStore technique (<=6 cold SELECTs,
1 s statement cap, 3 s budget, sentinels, 30 s local cache, tone degrades alone);
coordinator + spawn fetch child (one in flight, 6 s deadline, terminate/kill/reap,
quarantine on unconfirmed cleanup, 512 KiB body/result, 10 starts/60 s, 60 s per
chart, 60->1800 s ladder + Retry-After with one-day cap, 128 keys/8 MiB/256 KiB
LRU, 60 s fresh/15 min stale); additive yahoo.py bounded mode; authenticated
GET /radar/api/ticker/<ticker>/price-chart (span/market/sources only, 404
feature_disabled when off, 422/404/400/503 codes); shell chart flag; admin-only
selected_price_ops; typed validation/fetch, usePriceChart polling policy,
SelectedPriceChart renderer with keyboard/hover readouts in both ChartSection
callers, original chart for flag off/422; compact Admin panel. P01-P07 PASS
locally (P07 DB-free), P08 PASS on fixtures, P09 PARTIAL with disclosed gaps.
Evidence: baseline before edits: DB-free Yahoo/tone/HA1 269 passed/3 failed
(date-dependent test_radar_yahoo daily-close tests)/1 skipped; Radar Vitest 799
passed/28 failed (hub/pending.test.tsx). After: pytest tests/selected_price_unit
139 passed; regression 269 passed with the same 3 failures; npx tsc --noEmit 0;
npx vitest run -c vite.radar.config.ts 847 passed with the same 28 failures;
npx vite build -c vite.radar.config.ts 0; git diff --check clean. Real spawned
children (child-lifecycle.json): admission <1 ms; normal 0.81 s exit 0 with no
flask/sqlalchemy/extensions/models/app/auth modules; production child bad spec
0.77 s; hanging child terminated at 6.22 s supervisor time (deadline 6.0 s,
cleanup 1.0 s), exit -15, other chart busy meanwhile; oversized child cut at
1.11 s, exit -15. Browser (verify_browser.py run 3, bundle hub-BtAJD2zg.js):
57 cases, 744 checks, 0 failures; Research and Chatter panel at 1440/768/390/320,
real 200% zoom at 320/390 CSS px (DPR 2), keyboard, no overflow, request keys,
dates, end labels, stale switch, 422 fallback, headline identical flag on/off;
109 screenshots in browser/screenshots, representative set viewed. Fixture
identities: fixtures/manifest.json (states ordinary AAPL 1W, partial_gap AAPL 1D,
stale AAPL 1D, fallback MSFT 1D, unavailable NVDA 1W, long BRK.B 1W). Candidate
fingerprint 218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159
(fingerprint.json). Carry hashes: carry-manifest.json 23/23.
Evidence attribution: everything above executed by this worker locally on
2026-09-15. Yahoo arrays are the Researcher's saved 2026-09-15 capture reused as
test input with synthetic meta; chatter, tone, quotes, closes, detail and board
payloads synthetic; price-chart browser payloads produced by the real reader over
a fake store. No live provider, DB runtime or production evidence.
Findings and limitations: live Yahoo period1/period2 request form, closed-
session/overnight/holiday and throttling behaviour unverified (research tested
range=1d/5d only); Yahoo usage permission not established (carry from ruling);
no MariaDB runtime (only binary is inside protected HA1 env) so statement timeout/
cancel/plans/pool unverified and DB-backed suites (incl. updated ops key-set test,
hub page tests) not run; limits are per web process (N workers = N children,
ingest traffic separate, restart resets); spawn re-imports a script __main__
(harmless under gunicorn, matters for `python app.py` dev runs); tone aggregation
duplicated as reader SQL with parity tests; UX notes: continuous 1W axis narrows
session price segments, dominant partial outlines when a source is briefly
represented, top-anchored real-zoom captures frame the headline; detail endpoint
still sends unused 1D/1W chart arrays; pre-existing 3 Yahoo and 28 pending test
failures untouched.
Actions taken: created the worktree/branch, copied and hash-verified the carry,
copied node_modules from the source workspace (no install/download), implemented
and tested locally, built the Radar bundle, ran an in-process loopback server on
127.0.0.1:5042 with Chromium (headless and headed-offscreen), all stopped and no
child/QA process left. No commit, push, merge, deployment, production/DB access,
live provider request, probe-script execution or secret reads.
Protected state: source workspace and its dirty continuity/research/HA1
artifacts; main and other worktrees; B1C/5021; promotion/5033; databases
3306/3399; HA1 runtime/3461 and C:/Users/michi/.radar-ha1-local-qa — untouched.
Subagents: none
Updated artifacts (local, uncommitted):
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-IMPLEMENT-1-RETURN.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-LEDGER.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/HANDOFF.md
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/md-selected-price-implementation/
Requested Mastermind decision: accept the candidate for one focused independent
Reviewer/QA of the changed scope, recording live-provider request form, usage
permission, DB runtime timeout and worker topology as release carries.
Next bounded action: owner-selected Reviewer/QA on this candidate at fingerprint
218c1a53...2159; no repeat HA1/research review, no provider activation or deploy.

Read candidate handoff and ledger completely, verify Git/artifact evidence,
assess the return and update planning continuity. HA1 stays closed.
Do not implement, deploy or dispatch workers automatically.
```
