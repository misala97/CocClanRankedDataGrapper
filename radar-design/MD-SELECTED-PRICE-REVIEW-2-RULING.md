# MD-SELECTED-PRICE-REVIEW-2 — Mastermind ruling

2026-09-15. Accept REVIEW-2 as same-session executed verification, NOT an independent second review. Accept F1-F4 as locally corrected based on source/evidence; do not claim independent correction sign-off. Original independent REVIEW-1 stands for unchanged scope. One tiny CORRECTION-2 is prepared for R2-1; no full review/test cycle.

## Fresh evidence

Mastermind verified candidate branch codex/radar-selected-price-charts and HEAD/base daadf3868caedcb5db858378e919cba68b735f8a at C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts. Rehashed all 50 files in correction fingerprint-final.json with recorded normalization: zero mismatches at ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce. Read REVIEW-2 return, saved reproduction, current handoff/ledger and implicated supervisor source. Git ignore-file warning qualifies exhaustive untracked enumeration; all dirt preserved. No tests independently executed by Mastermind.

167 backend/117 frontend, tsc, scratch build and fake-process reproduction are same-session worker-executed, even though report calls them reviewer results. Hash recomputation by a second script is independent calculation, not an independent person/session. Browser remains correction-worker fixture evidence.

## Decisions

R2-1 confirmed in source plus saved fake-process reproduction: launcher suppresses failed cleanup then raises; supervisor has no returned Child, leaving confirmed=True. Another acquisition can start. Fix now rather than carry a known breach of the one-child/quarantine contract into activation.

Bounded remedy: make emergency cleanup return explicit confirmed-exit status; propagate unconfirmed cleanup through a dedicated exception/result to supervisor; mark cleanup_failed/quarantine before releasing admission. No new process manager, retry loop, scheduler, queue or platform abstraction. A missing/dead process must be distinguished from an unconfirmed exit using process evidence, not whether kill threw. Preserve original failure attribution where useful, no internal errors exposed to browser. Keep bounded cleanup and handle ownership.

One regression test should exercise real Coordinator/launcher with fake Popen ignoring kill/timing out and reader-start failure; assert quarantine, cleanup_failed, second request unavailable and only one Popen. Include the confirmed-cleanup/pre-Popen controls so ordinary start failures do not quarantine incorrectly. Existing normal Child.reap quarantine remains unchanged. Saved reproduction stays immutable; use a copied/adapted check.

N1: correct the two comments to coordinator creation on the first provider-enabled request reaching acquisition (not first admitted chart). No runtime/frontend changes for N1. No frontend/browser/build rerun for comment-only TypeScript; confirm generated assets remain unchanged. Tests scoped to backend lifecycle/acquisition/isolation are enough; broader selected-price suite only if needed. No repeat Yahoo/tone/HA1 or full Radar suites.

After correction, one DIFFERENT owner-selected session checks only the cleanup propagation delta and regression, with a brief source confirmation of F1-F4 against the binding ruling to resolve the disclosed independence gap. Reuse existing passing evidence; no fresh broad review/QA round. Do not dispatch automatically.

## State and carries

CORRECTION-2 PREPARED / NOT DISPATCHED. HA1 COMPLETE / DEPLOYED / CLOSED. Both flags default OFF; no commit/deploy/provider activation. POSIX/gunicorn/venv/cwd, live Yahoo epoch/closed sessions/usage conditions, MariaDB runtime and actual topology remain explicit release carries. D5/D14 closed and optional polish deferred except N1 comments. DEVNULL diagnostics remains accepted.

This turn owns this ruling, CORRECTION-2 prompt and latest candidate continuity notices only. Application/build/worker/reviewer artifacts and source/other-worktree dirt preserved. Remote Control sessions untouched.