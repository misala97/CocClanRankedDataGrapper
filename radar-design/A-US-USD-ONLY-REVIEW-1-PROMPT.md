# Prompt — A-US-USD-ONLY-REVIEW-1

You are Radar's fresh independent Reviewer/QA for the complete uncommitted US/USD-only removal candidate. Review only; do not implement fixes.

## Independence gate — mandatory

Before doing review work, confirm all three statements:

1. You did not implement `A-US-USD-ONLY-IMPLEMENT-1`.
2. You did not perform `A-US-USD-ONLY-RESEARCH-1` or `A-US-USD-ONLY-VERIFY-1` in this task/session.
3. You have not previously reviewed this candidate in this task/session.

If any statement is false, stop and return `REVIEW DISQUALIFIED — FRESH TASK REQUIRED`. Do not inspect or edit the repository. Do not spawn subagents.

This prompt is prepared but not self-dispatching. Start only when the owner deliberately pastes it into a separate fresh review task.

## Workspace and candidate

```text
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
branch: codex/radar-selected-price-charts
base/current HEAD: 38591e0f5e98faccb5228d84d1677843fcdb2aea
candidate: complete uncommitted personal_apps tracked delta plus its tests and evidence
```

HEAD equals the base, so a commit-range diff is not the candidate. Inspect `git status --short`, the full `git diff -- personal_apps`, deletions, and the task evidence directly. Confirm the index is empty and `personal_apps/models.py` plus `personal_apps/migrations/` have no diff. Preserve all unrelated dirty/untracked work. Never reset, clean, stash, restore, checkout, stage, commit or push.

## Read completely

1. root `HANDOFF.md`
2. `radar-design/WORKFLOW.md`
3. `radar-design/A-US-USD-ONLY-SPEC.md`
4. `radar-design/A-US-USD-ONLY-LEDGER.md`
5. `radar-design/A-US-USD-ONLY-RESEARCH-1-RULING.md`
6. `radar-design/A-US-USD-ONLY-VERIFY-1-RULING.md`
7. `radar-design/A-US-USD-ONLY-PLAN.md`
8. `radar-design/A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md`
9. `radar-design/A-US-USD-ONLY-IMPLEMENT-1-PROMPT.md`
10. `radar-design/A-US-USD-ONLY-IMPLEMENT-1-RETURN.md`
11. `radar-design/A-US-USD-ONLY-IMPLEMENT-1-RULING.md`
12. `radar-design/artifacts/a-us-usd-only-implement-1/checkpoints.md`
13. the relevant baseline/final identity lists, sweep outputs, browser `results.json`, harness and screenshots under `radar-design/artifacts/a-us-usd-only-implement-1/`
14. `radar-design/MD-SELECTED-PRICE-ALPACA-RELEASE-CLOSURE.md`
15. `radar-design/US-UNIVERSE-REFRESH-2026-09-16.md`

Code, Git state and reproducible evidence win over prose when they conflict.

## Review scope

Review the entire candidate, not just the Implementer's file summary.

### 1. Public contract and cache/archive identity

- Omitted market means US across board, shared-board, ticker, HTML and selected-price routes.
- Every explicit non-US market is rejected with a clear 400; HTML rejection occurs before the broad friendly fallback.
- Selected price still requires `span`; its acquisition, stored fallback, admission/rate behavior and geometry are unchanged except for the market-input contract.
- Board key v3, payload v2 and observation schema v2 make old DE-capable artifacts unusable without corrupting archival rows.
- Warm production is exactly eight unique US queries: All and default Discover across 1h, 4h, 12h and 24h; `warm_limit` remains 8.

### 2. Historical-data safety and retention

- No migration/model/schema edit and no historical-row mutation, conversion, relabeling or deletion.
- Old DE/EUR data is unreachable through supported UI/API behavior.
- `prune_quotes` filters to `market='us' OR market IS NULL` inside the ranked subquery, before ranking/deletion.
- US/legacy-US daily-close and Massive shadow retention remains; DE event/cycle/close/quote/FX/mapping history is no longer selected or deleted.
- Writers reject non-US/non-USD rows without weakening valid US writes or transaction boundaries.

### 3. Atomic runtime removal

- No surviving import, scheduler, CLI, config branch, probe, backfill/report path or caller reaches deleted DE calendar/provider/mapping/reference/FX modules.
- `RADAR_DE_PRICE_MODE`, OpenFIGI/DBAG/XETR/XGAT/Tradegate/ECB and `.DE` active behavior is gone; Twelve Data US quotes/history and other protected US provider paths remain.
- Daemon jobs, operational summaries and readiness behavior are coherent after removal.

### 4. Frontend and visible behavior

- No market selector, Germany/EU/EUR option, German exchange/source label, fallback/conversion badge or German admin panel is reachable.
- URL/request/cache state has no selectable market dimension; embedded non-US payloads are refused, not silently relabelled.
- Money is strict USD (`$194.20` shape); unknown/non-USD values are not given a dollar sign.
- US provenance, selected-price interaction, layout, keyboard/focus behavior and 320/390/1200 responsive behavior remain sound.
- `de-DE`/`Europe/Berlin` may remain only for the explicitly preserved date/time and owner-clock behavior.

### 5. Mandatory residual rulings

Do not skip or silently excuse either item:

1. `features/radar/config.py` actively includes `mauerstrassenwetten` in `REDDIT_SUBS`. Decide whether this German-language Radar source violates the owner's remove-all-German/EU-functionality decision or is legitimately a US-equity chatter source outside the market-price boundary. Cite reachability and user-visible impact.
2. `static/radar/src/hub/selectedPriceGeometry.test.ts` names `deutsche_boerse_delayed` and expects `sourceWord()` to render the raw code. The binding verifier ruling permits that vocabulary only in immutable migrations and ORM CHECK strings. Decide whether this is a legitimate rejection fixture or an active retired-source rendering contract. If it breaches the ruling, report the smallest fix.

Also independently repeat the residual sweeps. Intentional rejection tests may contain DE/EUR tokens only when they prove rejection/non-rendering; a passing test that preserves retired behavior is not automatically allowed.

### 6. Regression and evidence integrity

- Compare exact final Vitest failures with baseline; do not accept only aggregate counts. The known 28 `hub/pending.test.tsx` identities may remain only if identical.
- Verify selected-price, HA1, Massive/grouped-close and US quote/history tests cover the protected paths.
- Inspect the changed tests for weakened/deleted assertions masquerading as green results.
- Reconcile the DB-backed baseline/final/post-Task-4 identity lists. Treat destructive-suite refusals, absent FK parity and the unguarded migration-test behavior as explicit unavailable/risk evidence, not passes.
- Inspect representative desktop/mobile screenshots yourself; do not rely on the Implementer's visual conclusion.

## Verification

Use the smallest sufficient fresh proof set. At minimum, from `personal_apps/`, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
npx tsc --noEmit
npm run build
npx vitest run -c vite.radar.config.ts
py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider
py -3.12 -m pytest tests/ha1_unit --confcutdir=tests/ha1_unit -q -p no:cacheprovider
py -3.12 -m pytest tests/test_radar_massive.py --confcutdir=tests -q -p no:cacheprovider
```

Run focused pure/unit contract checks for keys, parsing, warming and frontend formatting. For DB-backed checks, first independently prove both the engine URL and `select database()` name the disposable `personal_apps_radar_wt` clone and that sockets are loopback-only. Never point at `personal_apps` or production. Do not set or invent `RADAR_DESTRUCTIVE_TEST_TARGET`, alter a registry or bypass a refusal. If the destructive suites remain unavailable, inspect their changes and report that limitation exactly.

Run or independently sample the zero-outbound Playwright harness at 1200/390/320 and inspect representative PNGs. Do not contact Alpaca, Yahoo or any external provider.

## Boundaries

This is read-only product/test review. The only permitted repository write is the return file below. Do not implement a fix, edit tests/application/continuity, install dependencies, inspect real credential values, alter an environment file, mutate historical data, touch production/services, commit, push or deploy.

Report only evidenced findings with exact file and line references:

- **Critical:** historical-data damage, non-US/EUR data exposed or relabelled as USD, broken protected US primary path, or severe security/data-integrity failure.
- **Important:** binding scope breach, reachable retired path/label, incorrect HTTP/cache/retention behavior, meaningful regression, or missing proof that blocks acceptance.
- **Minor:** bounded non-blocking issue.

The pre-existing unguarded migration test and disposable-clone residue are known safety debt. Do not relabel them as candidate regressions without evidence, and do not fix them in this review.

## Verdict

Choose exactly one:

1. `ACCEPT A FOR COMMIT/DEPLOYMENT PLANNING` — no Critical or Important finding.
2. `FIX REQUIRED BEFORE A ACCEPTANCE` — at least one Critical or Important finding; specify the smallest bounded correction.
3. `REVIEW BLOCKED` — required evidence cannot safely be obtained within scope.

Acceptance does not authorize commit, push, production environment cleanup or deployment.

## Return contract

Create `radar-design/A-US-USD-ONLY-REVIEW-1-RETURN.md` as the only repository write. Do not update continuity files. Return a copy/paste Mastermind prompt containing:

- fresh-task independence attestation;
- exact verdict;
- findings first, grouped Critical / Important / Minor, each with file:line, impact and smallest fix;
- explicit rulings on both mandatory residuals;
- exact commands/results and baseline identity comparison;
- contract, warm-board, retention/historical-data, atomic-removal, frontend/USD and protected-US conclusions;
- screenshots inspected and visual/accessibility ruling;
- every unavailable gate and remaining risk;
- branch/HEAD and final dirty status;
- confirmation that only the return file was written and no fix, credential/provider, environment, DB-history, service, production, commit, push or deployment action occurred.
