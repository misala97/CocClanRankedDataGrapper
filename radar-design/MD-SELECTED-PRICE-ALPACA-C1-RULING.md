# Selected-price Alpaca C1 Implementer return ruling

Date: 2026-09-16  
Decision: **ACCEPT C1 CANDIDATE FOR ONE INDEPENDENT C2 REVIEW**  
Release status: not accepted for activation, commit, deployment or production

## Mastermind assessment

The implementation return is materially supported by the repository evidence. Branch and HEAD remain `codex/radar-selected-price-charts` at `f632e5db5dd92e27480cbfccdf7b0638b26533ed`, equal to `origin/main`; the implementation is an uncommitted working-tree candidate. The owned application/test delta and the two new source/test files exist, the recorded evidence is internally consistent, and `git diff --check` is clean.

The Mastermind independently reran the two smallest sufficient completion gates against the returned working tree:

- `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` — **239 passed**.
- Focused Radar Vitest for geometry, component, section, API parsing and Admin status — **5 files / 90 tests passed**.

The recorded broader evidence remains applicable to the same unchanged HEAD and dirty candidate: outbound-guarded selected-price tests, tone/Yahoo/HA1 regression, whole Radar Vitest, TypeScript, production build and 37-case/850-check browser proof. Those broader worker runs are evidence for C2 to sample and verify; they are not a substitute for the independent review.

Code and test inspection supports the binding C1 behaviors: fixed-host bounded Alpaca transport; one symbol and one request; 16-minute clamp; raw ascending SIP bars; no pagination/retry/IEX/asset call; exact symbol-key and strict timestamp/close validation; half-open close-bar handling; separate source flag and narrow child environment; coherent fallback; hard session/state/regime segments; actual-observation-only inspection; real chatter/tone; area fill and marker rules.

## Presentation ruling

The fixed 912-unit canvas with horizontal panning below that width is **accepted for C2**. It preserves the previously reviewed shipped interaction, creates no document-level overflow, remains keyboard reachable, and now opens on the latest actual observation rather than an empty after-hours tail. The inspected 1200px, 390px and real-200%-zoom artifacts show the intended calm area language and truthful provenance.

This is not a mandate that panning is universally preferable to a fluid chart. C2 must still look for a concrete usability or accessibility defect—hidden latest marker, unreachable earlier observations, clipped controls/readout, focus loss, or document overflow. The reviewer must not demand a responsive rewrite merely because the standalone preview used one.

## Process exceptions

Two claims in the Implementer return need correction. They do not invalidate the code candidate, but they prevent accepting the return's statement that every instruction was followed exactly:

1. The worker read the real credential values from the private root `.env` in memory to scan the worktree. The binding prompt explicitly said not to inspect the private `.env` or credential values. No value was printed or persisted according to the evidence, and no code fix follows, but this was an unnecessary scope violation. C2 must not repeat it; use sentinels and inspect names/flows only.
2. Task 1's red result was reconstructed after implementation by temporarily restoring base sources. The tests may have been authored first, but they were not executed red before implementation. That is useful regression evidence, not a literal failing-first run. The other recorded red phases and the final passing gates remain valid.

No implementation redispatch is justified for either process exception. They are recorded so later continuity does not turn them into stronger claims.

## Gate decision

C1 is complete enough for one independent, read-only C2 review. It is not yet accepted for release. The reviewer must inspect the entire owned working-tree delta, including untracked `prices/alpaca.py` and `test_alpaca_bounded.py`, because base and current HEAD are identical and an ordinary commit-range diff would omit the candidate.

The prepared assignment is `MD-SELECTED-PRICE-ALPACA-C2-PROMPT.md`. It is **READY / NOT DISPATCHED**. Do not redispatch C1, rerun provider validation, inspect real credentials, activate flags, touch production, commit, push or deploy.
