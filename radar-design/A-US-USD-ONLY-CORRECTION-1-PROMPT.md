# Prompt — A-US-USD-ONLY-CORRECTION-1

You are Radar's correction Implementer. Apply exactly the two corrections accepted in `A-US-USD-ONLY-REVIEW-1-RULING.md` to the existing uncommitted A candidate. Do not broaden the work.

## Workspace and candidate

```text
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
branch: codex/radar-selected-price-charts
base/current HEAD: 38591e0f5e98faccb5228d84d1677843fcdb2aea
candidate: existing uncommitted working-tree delta
```

Inspect `git status --short` before editing. Preserve every pre-existing tracked and untracked change. Never reset, clean, stash, restore, checkout, stage, commit or push. Do not spawn subagents.

## Read completely

1. root `HANDOFF.md`
2. `radar-design/A-US-USD-ONLY-LEDGER.md`
3. `radar-design/A-US-USD-ONLY-SPEC.md`
4. `radar-design/A-US-USD-ONLY-VERIFY-1-RULING.md`
5. `radar-design/A-US-USD-ONLY-PLAN.md`
6. `radar-design/A-US-USD-ONLY-IMPLEMENT-1-RETURN.md`
7. `radar-design/A-US-USD-ONLY-REVIEW-1-RETURN.md`
8. `radar-design/A-US-USD-ONLY-REVIEW-1-RULING.md`

Repository evidence and the review ruling are binding when prose conflicts.

## Authorized correction C1 — test-only retired-source vocabulary

In `personal_apps/static/radar/src/hub/selectedPriceGeometry.test.ts`, replace the positive `deutsche_boerse_delayed` `sourceWord()` example with a neutral unknown value such as `some_future_feed`. Update only the surrounding test title/comment needed to describe generic unknown-source passthrough.

Do not change `sourceWord()` or any runtime frontend behavior.

Test first: make the residual requirement explicit, apply the small test correction, then run:

```powershell
cd personal_apps
npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts
rg -n "deutsche_boerse_delayed" static/radar/src --glob "*.ts" --glob "*.tsx"
```

Expected: focused Vitest passes and the TypeScript sweep has no matches.

## Authorized correction C2 — repeated market values

The board/ticker parser and HTML route guard currently read only the first `market` parameter. Correct them so **every supplied value** is validated:

- omitted `market` → US;
- `market=` → US, preserving the current board-route contract;
- `market=us` → US;
- repeated values containing only empty/`us` values → US;
- if any supplied value is anything else, including when it follows `market=us`, return the existing unsupported-market 400;
- preserve the HTML pre-fallback rejection and ensure no board/hub payload is embedded in the 400 page;
- do not change the selected-price endpoint, which already has its own strict duplicate-query rejection.

Implement at the narrow shared validation boundary. Keep `parse_query` compatible with both Flask `MultiDict` inputs and the plain mapping inputs used by existing unit tests. Do not refactor unrelated query parsing.

Add focused regressions for both parameter orderings:

```text
market=us&market=de
market=de&market=us
```

Cover the board API, ticker API, `/radar/`, `/radar/hub/` and `/radar/legacy/`. Also prove repeated supported values still select US and unrelated malformed-filter friendly fallback remains unchanged.

Run the narrowest safe tests first. Any DB-backed execution must independently prove both the engine URL and `select database()` are the disposable `personal_apps_radar_wt` clone and must refuse non-loopback sockets. Never bind `personal_apps` or production; do not invent or enable destructive-test authorization.

At minimum run the focused new tests, then:

```powershell
cd personal_apps
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m pytest tests/test_radar_api.py tests/test_radar_hub_page.py -q -p no:cacheprovider
npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts
npx tsc --noEmit
git diff --check
```

If the safe DB clone cannot be proven, do not run the DB-backed command; report it unavailable and use direct pure parsing plus Flask client tests only where they cannot bind an unsafe database.

## Scope exclusions

Do not modify `ChartHover.currency`, restore unrelated comments, remove `mauerstrassenwetten`, clean up other query semantics, alter selected-price duplicate handling, edit models/migrations, touch historical rows, fix F1/F5/network-test hygiene, rerun the full review, or change anything else.

No credential inspection, provider/network request, environment-file edit, service/production access, commit, push or deployment.

## Return contract

Create `radar-design/A-US-USD-ONLY-CORRECTION-1-RETURN.md`. Besides that return, edit only the application/test paths strictly required for C1/C2. Do not update continuity files.

Return a copy/paste Mastermind prompt containing:

- exact files and lines changed;
- C1 and C2 behavior before/after;
- new regression cases;
- exact commands/results and any unavailable gate;
- TypeScript residual sweep result;
- branch/HEAD, index and final dirty status;
- confirmation that models/migrations and unrelated candidate files were untouched;
- confirmation of no subagent, stage, commit, push, environment, DB-history, service, provider or deployment action.

After this return, the Mastermind performs a changed-lines assessment and focused verification. Do not request another full Reviewer cycle.
