# Prompt — MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW

You are Radar's final independent C2 Reviewer/QA. Review the complete corrected, uncommitted selected-price Alpaca C1 candidate and return an acceptance verdict. This must be a genuinely fresh task/session.

## Independence gate — mandatory

Before doing any review work, confirm all three statements:

1. You did not implement `MD-SELECTED-PRICE-ALPACA-C1` in this session.
2. You did not perform the same-session `MD-SELECTED-PRICE-ALPACA-C2` review in this session.
3. You did not implement `MD-SELECTED-PRICE-ALPACA-C2-FIX` in this session.

If any statement is false, stop immediately and return `REVIEW DISQUALIFIED — FRESH SESSION REQUIRED`. Do not inspect or edit the repository. Do not spawn subagents.

This prompt is prepared but not self-dispatching. Start only when the owner deliberately pastes it into a separate fresh review task.

## Workspace and candidate identity

```text
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
branch: codex/radar-selected-price-charts
base/current HEAD: f632e5db5dd92e27480cbfccdf7b0638b26533ed
origin/main: f632e5db5dd92e27480cbfccdf7b0638b26533ed
candidate: complete uncommitted tracked + untracked working-tree delta
```

Base and current HEAD are identical. A commit-range diff is not the candidate. Inspect `git status --short`, the full tracked `git diff`, and the authorized untracked implementation/test files directly. Preserve all dirty and untracked work. Never reset, clean, stash, restore, checkout, stage, commit or push.

## Read completely

1. root `HANDOFF.md`
2. `radar-design/MD-SELECTED-PRICE-LEDGER.md`
3. `radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md`
4. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`
5. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-PLAN.md`
6. `radar-design/MD-SELECTED-PRICE-ALPACA-C1-RULING.md`
7. `radar-design/MD-SELECTED-PRICE-ALPACA-C2-RETURN.md`
8. `radar-design/MD-SELECTED-PRICE-ALPACA-C2-RULING.md`
9. `radar-design/MD-SELECTED-PRICE-ALPACA-C2-FIX-RETURN.md`
10. `radar-design/MD-SELECTED-PRICE-ALPACA-C2-FIX-RULING.md`
11. `radar-design/artifacts/md-selected-price-alpaca-c1/evidence.md`
12. `radar-design/artifacts/md-selected-price-alpaca-c1/browser/results.json`

Evidence and code win over prose if they conflict.

## Review scope

Review the complete C1-owned backend, frontend and focused-test delta, including untracked `personal_apps/features/radar/prices/alpaca.py` and `personal_apps/tests/selected_price_unit/test_alpaca_bounded.py`. Separate it from unrelated pre-existing planning/research artifacts.

### Independently sample the original contract

- One pinned US/USD symbol, one fixed-host request, ruled 1Min/5Min SIP/raw/ascending/limit parameters and 16-minute clamp.
- No retry, redirect following, ambient proxy/netrc, cookies, pagination, IEX, asset call, alternate-symbol fallthrough or whole-universe path.
- Exact response symbol, strictly increasing RFC-3339 timestamps, finite positive closes, non-null page-token rejection and bounded body/result/point counts.
- Exact-close timestamp excluded from 1W regular and retained only as a separate eligible 1D after-hours segment.
- Child environment limited to platform minimum plus the two named credentials; no value can reach arguments, spec, output, logs, errors, operations or fixtures.
- Default-off independent flags, truthful admission/refusal states, coherent whole-series fallback and no provider/stored splice.
- Actual observations only; hard session/state/source-regime segments; real chatter/tone unchanged.
- Accepted segmented area language, truthful delayed/raw provenance, keyboard/focus/readout behavior and no invented inspectable values.

### Verify every correction

1. **C2-1:** forge an `ok` child result with an unknown source using local/in-process test machinery only. It must count invalid, cache nothing, cool boundedly and let the reader fall back without an exception. Valid Alpaca, valid Yahoo and missing-source legacy shapes must still work.
2. **C2-2:** inspect/test sparse FT-like 1200/768/390 placement. When the gutter and useful line can coexist, both must be visible; at 390 the latest observation must remain preferred. Dense 1D, 1W and stored fallback must remain sound.
3. **C2-3:** prove an intermediate reader position and exactly zero survive ordinary data refresh and resize; switching ticker or span must position the new chart; programmatic initial placement must not masquerade as reader input.
4. **C2-4:** prove operations and Admin report `alpaca_sip`, `yahoo_chart` or no source according to flags/admission, never inventing Alpaca and never exposing credential values.

Look specifically for regression risk in the pan effect's event/ref lifecycle and the supervisor's cached-result boundary. Do not expand into cleanup or unrelated historical behavior.

## Verification

Run at minimum:

```powershell
cd personal_apps
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider
npx vitest run -c vite.radar.config.ts static/radar/src/hub/selectedPriceGeometry.test.ts static/radar/src/hub/SelectedPriceChart.test.tsx static/radar/src/hub/SelectedPriceSection.test.tsx static/radar/src/hub/priceChart.test.ts static/radar/src/hub/Admin.test.tsx
npx tsc --noEmit
```

Run the deterministic local browser harness or a smaller independent Playwright probe for the corrected pan/scroll cases, with zero unmocked/outbound requests. Inspect the actual sparse 1200 and 390 PNGs, plus one 1W or fallback control. Sample broader recorded gates only as needed to resolve a finding.

Do not install dependencies, contact Alpaca or another provider, run DB/production tests, or inspect the private root `.env`.

## Review boundaries

This is read-only product/test review. The only permitted repository write is the return file named below. Use synthetic credential sentinels only. Do not open, parse, hash, search for or otherwise inspect real credential values. Do not activate flags, change configuration, touch a database/service/production host, commit, push or deploy.

Report only evidenced findings with exact file and line references:

- **Critical:** security exposure, wrong source/identity, fabricated/spliced data, uncontrolled provider behavior or broken primary path.
- **Important:** binding breach, uncaught request-path error, meaningful fallback/segment/accessibility defect or missing proof that blocks acceptance.
- **Minor:** bounded non-blocking issue.

Do not repeat the already-recorded process exceptions as new code findings. Do not require cleanup-only renaming or a credential-presence helper without a demonstrated defect.

## Verdict

Choose exactly one:

1. `ACCEPT C1 FOR OWNER ACTIVATION/DEPLOYMENT DECISION` — no Critical or Important findings.
2. `FIX REQUIRED BEFORE C1 ACCEPTANCE` — Critical/Important finding exists; provide the smallest correction.
3. `REVIEW BLOCKED` — required evidence cannot be obtained within scope.

An accept verdict does not itself authorize activation, configuration changes, commit, push or deployment.

## Return contract

Create `radar-design/MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RETURN.md` as the only repository write. Do not update continuity files. Return a copy/paste Mastermind prompt containing:

- explicit fresh-session independence attestation;
- exact verdict;
- strengths and findings grouped Critical / Important / Minor;
- file:line, impact and smallest fix for every finding;
- exact commands/results;
- corrected C2-1 through C2-4 conclusions;
- original source/isolation/fallback/observation sample conclusions;
- screenshots inspected and visual/accessibility ruling;
- remaining release carries;
- branch/HEAD/origin-main and final dirty status;
- confirmation of no real credential inspection, outbound provider call, product/test edit, activation, DB/service/production action, commit, push or deploy.
