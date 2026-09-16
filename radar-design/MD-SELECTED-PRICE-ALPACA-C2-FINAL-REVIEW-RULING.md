# MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW — Mastermind ruling

Date: 2026-09-16

## Decision

The fresh-session review is **accepted**. Its independence attestation satisfies
the required gate, and its evidence closes C2 for the corrected C1 candidate.
There are no Critical or Important findings.

The candidate is **not yet ready for an owner activation/deployment decision**.
Minor finding M1 must be corrected before release. This is a narrow pre-release
hardening correction, not a reopening of the source contract, isolation design,
segment model, area language, or C2-2 through C2-4.

No activation, configuration, commit, push, deploy, live provider call, or
credential inspection is authorized by this ruling.

## Evidence accepted

- The reviewer ran in a genuinely fresh task/session and attested that it did
  not implement C1, conduct the earlier same-session C2 review, or implement
  C2-FIX.
- Focused backend: **245 passed**, and **245 passed** again under a non-loopback
  socket guard with zero outbound attempts.
- Focused frontend: **5 files / 97 tests passed**.
- `tsc --noEmit` and `git diff --check` exited 0.
- Independent probes confirmed the Alpaca request bounds and isolation,
  admission/ops truth table, coherent whole-series fallback, and pan ownership
  across real data refreshes and responsive/DPR contexts.
- C2-1 through C2-4 are confirmed for the ruled scope.
- HEAD and `origin/main` remain
  `f632e5db5dd92e27480cbfccdf7b0638b26533ed`; the candidate remains an
  uncommitted working-tree delta and all provider flags remain off.

## Finding rulings

### M1 — require before release

The current `_settle()` guard proves only that the returned `source` is a known
profile. It does not prove that it equals the source admitted for this child.
It also performs set/dict membership on untrusted JSON, so an array or object
raises `TypeError` in the supervisor thread instead of counting an invalid
result and cooling the key.

This is unreachable through the current fixed child, so the reviewer correctly
classified it Minor rather than Important. It is nevertheless the exact child
result trust boundary introduced by C2-1. A known-but-wrong source can be cached
under the admitted provider's key, and an unhashable source bypasses the intended
invalid-result accounting. The correction is localized and low-risk; carrying
it into an activation/deployment decision would create avoidable ambiguity.

Required correction:

1. Give `_settle()` the admitted `spec` (or the admitted source derived from it).
2. Compare the result source by equality with the admitted source, retaining
   the historical missing-source Yahoo default.
3. Ensure malformed/unhashable source values count `invalid`, cache nothing,
   and receive the normal 60-second cooldown without a supervisor exception.
4. Add focused tests for an unhashable source and for a known source that does
   not match the admitted source.

No new provider, fallback, retry, cache, or public-response behavior is allowed.

### M2 — carry, non-blocking

The candidate browser harness does not itself perform the claimed data refresh,
and its saved 200% zoom frames do not frame the chart drawing. This is an
evidence-harness defect, not a product defect. The independent reviewer closed
the material refresh gap with real fake-clock refetches across six viewport/DPR
contexts and supplied DPR-2 element captures. Do not modify the browser harness
in the M1 correction.

### Other notes

The pre-existing non-finite `received_at` observation is out of scope and
unreachable through the fixed child encoder. Credential scoping to Alpaca-only
children is a least-privilege carry, not part of this correction. Do not bundle
either item into the M1 patch.

## Next bounded action

Dispatch exactly one Implementer with
`MD-SELECTED-PRICE-ALPACA-C2-M1-FIX-PROMPT.md`. After its return, Mastermind
performs a changed-lines review and focused verification. No second full
fresh-session C2 review is required if the patch stays within this ruling.

