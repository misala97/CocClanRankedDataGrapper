# Selected-price Alpaca C2 correction return ruling

Date: 2026-09-16  
Decision: **CORRECTION ACCEPTED FOR FRESH-SESSION FINAL C2 REVIEW**  
Release status: not yet accepted for activation, commit or deployment

## Assessment

The correction return is supported by the current repository state and clears the four accepted findings without reopening the source or rendering design.

The Mastermind independently reran the smallest sufficient gates against the corrected uncommitted candidate:

- selected-price backend: **245 passed**;
- focused Radar frontend: **5 files / 97 tests passed**;
- `git diff --check`: clean;
- branch/HEAD/origin-main remain `codex/radar-selected-price-charts` / `f632e5db5dd92e27480cbfccdf7b0638b26533ed` / the same SHA.

The inspected corrected sparse desktop artifact shows the reported FT line, after-hours dot, price-axis gutter and session-end label together. The 390px artifact still prioritizes the latest real observation when the line and gutter cannot both fit.

## Correction rulings

1. **Unknown source validation — accepted.** `_settle()` now rejects an `ok` result whose effective source is not in `PROVIDER_PROFILES`, while preserving the historical missing-source Yahoo default. Tests prove invalid accounting, no cache, bounded cooldown and a non-raising fallback path.
2. **Sparse pan positioning — accepted.** The pure pan calculation chooses the rightmost position when it can retain at least half a viewport of line; otherwise it retains the latest-observation position. Desktop/tablet regain the gutter without regressing narrow mobile.
3. **Reader scroll ownership — accepted.** Explicit refs replace `scrollLeft === 0` as state. Tests/browser evidence cover initial placement, intermediate history, exact zero across refresh/resize and repositioning after ticker change.
4. **Operations source truth — accepted.** The payload now identifies Alpaca, Yahoo or no selected source truthfully; the Admin type and rendering admit `null`. The one-word type widening was necessary to represent the corrected backend contract and is accepted.

No cleanup-only rename, credential helper, provider-contract change, segment change or area-language change entered the patch.

## Remaining gate

This ruling accepts the correction, not the release. The required independent review has still not occurred. `MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-PROMPT.md` is **READY / NOT DISPATCHED** and must be run in a genuinely fresh task/session by a reviewer who did not implement C1, perform the same-session C2 review or implement this correction.

Do not activate provider flags, inspect real credentials, make a live provider request, touch production, commit, push or deploy before that return is assessed.
