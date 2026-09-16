# Assignment: MD-SELECTED-PRICE-ALPACA-C2-M1-FIX

You are the bounded Implementer for one final pre-release correction to Radar's
uncommitted selected-price Alpaca C1 candidate.

## Workspace and identity

- Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
- Branch: `codex/radar-selected-price-charts`
- Base/current HEAD: `f632e5db5dd92e27480cbfccdf7b0638b26533ed`
  (`origin/main`; candidate is uncommitted)
- Binding ruling:
  `radar-design/MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RULING.md`
- Reviewer evidence:
  `radar-design/MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RETURN.md`

Read the ruling and the relevant acquisition tests completely before editing.
Preserve every unrelated dirty or untracked file. Do not reset, clean, stash,
restore, checkout, stage, commit, push, or deploy.

## Objective

Make the supervisor accept an `ok` child result only when its effective source
equals the source admitted for that child. Malformed/unhashable sources must be
handled as invalid results rather than escaping `_settle()`.

## Required behavior

1. Pass the admitted request `spec` (or its admitted source) into `_settle()`.
2. Replace the current known-profile membership guard with equality against the
   admitted source.
3. Preserve the historical Yahoo compatibility rule: a result with no `source`
   has effective source `yahoo_chart`, and a spec with no `source` has admitted
   source `yahoo_chart`.
4. A result source such as `["alpaca_sip"]` must:
   - produce no supervisor-thread exception;
   - increment `invalid`, not `success`;
   - cache nothing;
   - apply the normal 60-second cooldown/backoff.
5. A `yahoo_chart` result for an admitted `alpaca_sip` spec (and vice versa)
   must be invalid and never cached.
6. Valid matching `alpaca_sip`, matching `yahoo_chart`, and the historical
   missing-source Yahoo shape must continue to succeed.
7. Use an accurate invalid-result reason rather than claiming a source mismatch
   exceeded the byte bound, if this can be done without widening the patch.

## Required tests

Add focused regression tests in
`personal_apps/tests/selected_price_unit/test_acquisition.py` for:

- an unhashable source value;
- a known source that differs from the admitted source.

Keep or strengthen the existing unknown-string/null/integer and valid-source
coverage. Follow the repository's existing Harness patterns; do not add a new
test framework or dependency.

Run from `personal_apps` with bytecode/cache writes disabled where supported:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m pytest tests/selected_price_unit/test_acquisition.py -q -p no:cacheprovider
py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider
```

Then run from the worktree root:

```powershell
git diff --check
```

## Hard scope limits

- Product edits are limited to
  `personal_apps/features/radar/price_chart_acquisition.py`.
- Test edits are limited to
  `personal_apps/tests/selected_price_unit/test_acquisition.py`.
- Do not edit the browser harness or frontend.
- Do not harden non-finite `received_at` in this assignment.
- Do not change child credential scoping, provider adapters, request bounds,
  retries, caching policy, fallback policy, ops/admin output, segment logic,
  rendering, or feature flags.
- Do not open/read/search/hash private credential values or `.env` contents.
- No network/provider request, dependency install, build, activation,
  configuration, DB/schema/service/production action, commit, push, or deploy.

## Return

Write exactly one new repository artifact:
`radar-design/MD-SELECTED-PRICE-ALPACA-C2-M1-FIX-RETURN.md`.

Report:

- exact files and behavior changed;
- tests/commands and exact results;
- resulting `git status --short`, HEAD, and `origin/main`;
- confirmation that the hard scope limits were respected;
- any residual risk or blocker;
- a self-contained prompt back to Radar's Mastermind / Overview requesting a
  changed-lines assessment.

Stop after the return. Do not prepare activation or deployment work.

