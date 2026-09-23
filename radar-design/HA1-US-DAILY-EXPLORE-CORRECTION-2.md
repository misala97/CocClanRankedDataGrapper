You are Radar's Implementer. Complete HA1-US-DAILY-EXPLORE-CORRECTION-2, a bounded harness-only correction.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore
Branch: codex/radar-ha1-us-daily-explore
Expected base/HEAD: 1ac39fe4e1a5dd7d04830e96a96563183687b447; no upstream; existing work uncommitted.

Read both HANDOFF.md files and HA1 ledger completely. Read radar-design/WORKFLOW.md and HA1-US-DAILY-EXPLORE-{SPEC,PLAN,CORRECTION-1-RULING,REVIEW-2-RETURN,REVIEW-2-RULING}.md plus artifacts/ha1/review-2/evidence.md and relevant reproductions. Verify path/branch/HEAD/status/diff/log. Most HA1 files are untracked; HEAD is not a pre-correction baseline. Preserve all prior dirt and reports.

Product corrections are independently reviewed; do not reopen or change application code. Authorized edits: personal_apps/scratchpad/ha1/{local_runtime,verify_preview,probe_analysis,ha1_harness,ha1_fixtures,preview_fixtures}.py as needed, tests/test_radar_analysis_api.py, focused DB-free harness tests, new correction evidence and continuity only. No DB/provider/production access, API integration/fixture/probe/preview/server/browser execution, provisioning, registry/service/migration changes, workers/subagents, commits/pushes/deployment. A target appearing does not lift the hold.

Required corrections:
- U1: runtime Git uses per-command safe.directory scoped to the resolved candidate and reports failure as a clear SystemExit. No global Git config. Add a real DB-free foreign-owner subprocess regression rather than mocking away Git.
- U2: assert search selection plus canonical pin adds exactly one history entry; Back returns to pre-selection Analysis, not ticker-only intermediate. Pin itself replaces.
- U3: prepare safe runtime checks for root and hub alias, legacy route/mount/auth, valid ?t= bookmark, invalid-hash fallback, filter-only bookmark, canonical Analysis links, Back/refresh and no recurring /radar/api/board requests while Analysis is active. Respect permitted cold-shell bootstrap. Use owned identities; do not restore unsafe suites.
- U4: establish the non-admin session cookie on the actual FULL_ACCESS_HOST test-client host and assert exactly 403; separately assert permitted loopback access. Never accept a login redirect as evidence of member-policy enforcement. Keep application authorization unchanged. Add a DB-free toy-host regression that would fail if the member gate disappeared.
- U6: zero-check cases and empty required selector matches fail. Unsupported colours must fail explicitly, not be skipped. Resolve/composite alpha against the actual background or report unverified failure. Require evaluated text contrast pairs and meaningful graphics pairs at SPEC thresholds (4.5:1 normal text, 3:1 meaningful graphics). Unit-test empty/unparsed/translucent/low-contrast paths and check attribution.

Also include these bounded evidence repairs in the same pass:
- U5: prepare a sub-second CPU timeout case (e.g. 0.250s) through production timeout logic, retaining same-connection and recovery evidence. Record requested/effective limit, elapsed time and overshoot; no fabricated runtime pass.
- U7: structured reports retain both original failure and cleanup failure/remaining owned identities. Exit nonzero and preserve actionable cleanup evidence without secrets.
- U8: bind runtime and preview validation to a deterministic digest of relevant candidate application/harness source and served build assets, including untracked HA1 files. Explicitly list covered inputs. Exclude mutable logs, runtime records, fixture manifests and caches so the fingerprint does not invalidate itself. Reject drift and require deliberate rebuild/restart; do not automatically stop another process.
- U9: strengthen existing checks for actual touch selection and scroll-box reachability, usable 200% zoom, rendered/requested range after refresh, positive adjacent-price lines plus weekend breaks, chart/control alignment, Tab/skip-link/Escape behavior where applicable. Fix nested-case attribution and distinguish unsupported checks from success. Keep checks tied to SPEC; no UI redesign.
- U10: record timeout dialect only after the already-authorized future connection initializes it. Do not add an eager connection now or change production reader code.

Disposition of remaining notes:
U11 EXPLAIN-shape concern is a runtime hypothesis. Do not weaken indexed-plan checks speculatively; record actual plan evidence later and escalate any false-fail.
U12 ambiguous-primary copy is deferred product polish, not this assignment.
U13 repeated pin-effect hypothesis is deferred; strengthen behavioral pin-history check under U2, report a demonstrated material failure without changing product code.

Binding deadline ruling:
Five seconds is a monotonic Analysis reader/resolver budget, excluding pre-reader authentication/pool wait. Each statement gets <=min(2s, remaining budget), ms-floored and never zero. No new statement after expiry; post-materialization/reduction expiry refuses success. This is not a hard HTTP wall-clock/cancellation guarantee. The ruling explicitly qualifies SPEC section 7's broader 'no request survives' sentence; original text stays as history.
Runtime must measure statement interruption delay, reader elapsed time/overshoot and full-request duration separately, plus recovery. Do not call post-hoc refusal proof that server work stopped at exactly five seconds. Warm full data-request p95<=1s over twenty max-row runs and all row/source/bytes/memory limits remain unchanged. Unexpected/material overrun returns to Mastermind; no self-approved tolerance or silent waiver.

Verification now: focused DB-free harness tests and new reproductions, Python compile and git diff --check. Confirm tests cannot connect/import the application inadvertently; reuse the reviewed socket-blocking approach where appropriate. Do not rerun full product/frontend suites for harness-only changes without a concrete reason. No DB/API/browser/preview script execution. New runtime assertions remain UNEXECUTED.

Write radar-design/HA1-US-DAILY-EXPLORE-CORRECTION-2-RETURN.md and artifacts/ha1/correction-2/ evidence. Update HA1 ledger, both handoffs and current assignment/state with exact ownership, each U disposition, commands/results/open gates. Preserve original spec, reviews and reproductions. Protect main/other worktrees, B1C DB/5021, default3306, promotion3399/5033 and prior artifacts. Capture OFF/shared boards ON/migration b7e3f9c1a2d4 are release-attributed, not probed.

Stop after this list and DB-free verification. Next is Mastermind's focused assessment against this list, not another automatic full review loop. If satisfactory, next planning is separately authorized disposable environment/QA for C02/C11/C13-C16. No deployment or dispatch.

FINAL RESPONSE MUST INCLUDE A FULLY POPULATED COPY/PASTE RETURN PROMPT:
You are Radar's Mastermind / Overview. Assess HA1-US-DAILY-EXPLORE-CORRECTION-2.
Workspace: [absolute]
Branch/base/HEAD/upstream: [verified]
Git status/ownership: [exact correction files, prior dirt preserved, no commits/pushes]
Binding artifacts: [absolute ruling/assignment/ledger/review/return paths]
Finding dispositions: [U1-U10 as assigned; U11-U13 deferred status]
Fresh verification: [commands/results/evidence paths]
Attribution: [executed DB-free vs static vs earlier review]
Deadline handling: [ruling implemented in measurement plan; no runtime guarantee claimed]
Open gates: [C02/C11/C13/C14/C15/C16 runtime, explicitly unexecuted]
Remaining defects/deviations: [specific evidence]
Protected state/actions not taken: [details]
Updated continuity/artifacts: [absolute paths]
Requested decision: focused Mastermind assessment of this harness delta; if satisfactory prepare separately authorized disposable environment/QA, not another full product review.
Read continuity and verify Git/artifacts. Do not implement/deploy or dispatch workers.

---

Status 2026-09-15 (appended by the Implementer; assignment text above unchanged): DISPATCHED by the owner and RETURNED. Return: HA1-US-DAILY-EXPLORE-CORRECTION-2-RETURN.md; evidence: artifacts/ha1/correction-2/evidence.md. Harness only; no application change; new runtime assertions unexecuted; C02/C11/C13–C16 open.

