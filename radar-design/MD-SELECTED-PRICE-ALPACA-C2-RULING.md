# Selected-price Alpaca C2 Reviewer/QA return ruling

Date: 2026-09-16  
Decision: **FIX REQUIRED BEFORE C1 ACCEPTANCE**  
Review qualification: useful same-session QA, not the required independent second opinion

## Assessment

The Reviewer/QA return is technically useful and its findings are consistent with the current working tree. It does not complete C2 because it ran in the same session that implemented C1. The explicit requirement was a separate, independent review task. A genuinely fresh-session review remains required after the correction return.

The candidate remains uncommitted at `f632e5db5dd92e27480cbfccdf7b0638b26533ed`, equal to `origin/main`. No activation or release decision is authorized.

## Finding rulings

### C2-1 — accepted as Important and required

`price_chart_acquisition.Coordinator._settle()` accepts an `ok` child result without validating its `source`. The cached result is counted as success, while `provider_price()` later indexes `PROVIDER_PROFILES[source]` on the Flask request thread. An unknown source therefore produces an uncaught `KeyError` instead of coherent fallback.

The fixed child does not emit this shape today, but `_settle()` is the supervisor boundary responsible for validating child output before caching it. The binding specification permits publication only for a fully valid provider result. Add source-membership validation and a regression test proving unknown source means invalid, no cache and bounded cooldown/fallback behavior.

### C2-2 — accepted as Minor and included

The latest-observation pan rule can leave the price-axis gutter and window-end label off screen for the sparse FT case at widths where both the useful line and gutter fit. Keep the mobile preference for the latest data, but choose the rightmost position when it still leaves at least half a viewport of the plotted line visible. Add deterministic component/browser proof for the fit and cannot-fit cases.

### C2-3 — accepted as Minor and included

`scrollLeft === 0` cannot distinguish an unpositioned chart from a reader deliberately viewing the oldest history. A refresh can snap that reader back to the latest data. Replace the overloaded check with explicit auto-position state: position once for a new chart identity/range selection, then preserve reader scrolling—including exactly zero—across ordinary data refreshes and resize callbacks. Switching ticker or span must still position the new chart appropriately.

### C2-4 — partially accepted and included only where behavioral

Operations output must report the actually selected source when Yahoo is active instead of always claiming `alpaca_sip`. Add backend and Admin regression coverage. Renaming `ALPACA_REFUSALS` is cleanup with no behavioral defect and is excluded from this surgical patch. The suggestion to add a credential-presence helper is also excluded: the parent already owns those environment values to pass them to the child, and a helper would still need to inspect nonblank values without changing the exposure boundary.

## Independence ruling

The same-session review does not count as the independent C2 gate. After the correction is locally verified, one fresh-session Reviewer/QA must inspect the corrected owned delta. That review may be concise and focus on C2-1 through C2-4 plus regression risk, but it must independently sample the original source, isolation, fallback and observation-preservation contract before recommending acceptance.

## Next action

`MD-SELECTED-PRICE-ALPACA-C2-FIX-PROMPT.md` is **READY / NOT DISPATCHED**. One Implementer should apply only the four bounded corrections above, produce a return, and stop. Do not reopen the provider decision, source contract, child isolation design, segment model or accepted area language. Do not inspect real credentials, make a live provider request, activate flags, touch production, commit, push or deploy.
