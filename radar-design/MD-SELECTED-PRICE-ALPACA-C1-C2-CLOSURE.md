# MD-SELECTED-PRICE-ALPACA C1/C2 — final implementation and review closure

Date: 2026-09-16

## Decision

**C1 implementation and C2 review are CLOSED.**

The final M1 correction is accepted. The selected-price Alpaca candidate is
ready for the owner's separate activation/deployment decision. No further
Implementer, correction, or independent review is required for C1/C2.

This closure does not itself authorize activation, configuration, commit,
push, deployment, credential inspection, or a live provider request.

## Final correction accepted

- `_supervise()` passes the admitted request spec into `_settle()`.
- An `ok` result is publishable only when its effective source equals the
  admitted source.
- Equality does not hash the untrusted JSON value, so arrays and objects are
  refused as invalid instead of escaping the supervisor thread.
- Known-but-wrong, unknown, null, empty, unhashable, and missing-for-Alpaca
  sources are invalid, uncached, and cooled for 60 seconds.
- Matching Alpaca, matching Yahoo, and the historical source-less Yahoo shape
  remain valid.
- Source mismatch now has an accurate refusal reason.

The changed lines are confined to:

- `personal_apps/features/radar/price_chart_acquisition.py`
- `personal_apps/tests/selected_price_unit/test_acquisition.py`

## Mastermind verification

Freshly run on the final working tree:

- focused acquisition tests: **63 passed in 0.28 s**;
- complete selected-price unit suite: **256 passed in 18.39 s**;
- `git diff --check`: exit 0, with line-ending warnings only.

The patch matches
`MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RULING.md`. HEAD and `origin/main`
remain `f632e5db5dd92e27480cbfccdf7b0638b26533ed`; the complete candidate remains
uncommitted and all provider flags remain off.

## Closed evidence chain

- C0 provider validation: accepted.
- C1 implementation: accepted after bounded corrections.
- Same-session C2 findings: corrected.
- Fresh-session independent C2 review: accepted with no Critical or Important
  findings.
- Final M1 changed-lines correction: accepted by Mastermind with fresh focused
  verification.

## Non-blocking release carries

These do not reopen C1/C2:

- The browser harness's saved refresh/200% framing evidence can be improved
  later; the fresh reviewer independently proved actual refresh behavior.
- Non-finite `received_at` hardening is pre-existing/out of scope and
  unreachable through the fixed child encoder.
- Restricting Alpaca credentials to Alpaca children only is optional
  least-privilege follow-up.
- The release must explicitly include the untracked
  `personal_apps/features/radar/prices/alpaca.py` and
  `personal_apps/tests/selected_price_unit/test_alpaca_bounded.py` files.
- Rebuild distributable frontend assets during the release workflow.
- Production/runtime validation still includes POSIX/gunicorn child behavior,
  expected environment variable name presence, MariaDB/DB-backed checks, real
  `WEB_CONCURRENCY`, health/smoke checks, and rollback readiness.
- No live Alpaca path has been exercised by this implementation/review closure.

## Next action

The next action is the owner's activation/deployment decision. Activation of
`RADAR_SELECTED_PRICE_ALPACA_ENABLED` and any restart/deployment remain separate
owner-authorized work. Recorded production state remains charts ON, Yahoo OFF,
Alpaca OFF until that decision is executed and verified.

