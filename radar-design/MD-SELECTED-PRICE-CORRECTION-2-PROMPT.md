You are Radar's Implementer for MD-SELECTED-PRICE-CORRECTION-2. Return to the Mastermind.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Base/current HEAD: daadf3868caedcb5db858378e919cba68b735f8a
Starting fingerprint: ad06a94a4d4dcacbd024180a7a604743c5d9ba7e67b36b41c6b197e59f9466ce

Fix only R2-1 (unconfirmed cleanup after post-Popen failure) plus N1's two inaccurate comments. No architecture/UI change, no full review/research/HA1 cycle. One worker, no subagents.

Read candidate HANDOFF.md, radar-design/MD-SELECTED-PRICE-LEDGER.md, WORKFLOW.md, MD-SELECTED-PRICE-REVIEW-2-RETURN.md and MD-SELECTED-PRICE-REVIEW-2-RULING.md (all latter files under radar-design). Latest ruling governs. Inspect artifacts/md-selected-price-review-2/post_popen_cleanup_repro.py and .json, and correction-1/fingerprint-final.json under radar-design/artifacts/md-selected-price-correction-1/ (the fingerprint's actual path). Verify fresh branch/HEAD/status and starting fingerprint read-only; preserve original manifests and all dirt. Use per-command safe.directory if needed.

R2-1 scope: personal_apps/features/radar/price_chart_acquisition.py and the smallest relevant selected_price_unit test file(s).
- Emergency cleanup must explicitly report whether child exit was confirmed.
- If cleanup after a post-Popen exception is unconfirmed, propagate a dedicated exception/result to _supervise so cleanup_failed increments and the coordinator quarantines before admitting another request, even though no Child object was returned.
- Preserve bounded cleanup, handles, normal reap/quarantine, deadlines, admission/cache/backoff and original error attribution where useful. No retries/new abstractions. Distinguish confirmed exit from failed kill/wait using process evidence; do not equate a kill call with confirmed exit.
- Reproduce failing-first with real Coordinator/launcher and safe fake Popen that ignores kill/times out, plus reader-start failure. Then prove quarantine, cleanup_failed, second request unavailable and only one Popen. Include confirmed-cleanup and pre-Popen failure controls so ordinary start failures do not quarantine incorrectly. Keep old reproduction/evidence unchanged; copy/adapt into new evidence if needed.

N1: correct comments in _snapshot_shape and hub/priceChart.ts: coordinator is created on first provider-enabled request reaching acquisition, not first admitted chart. No functional frontend change.

Verification: focused backend acquisition/lifecycle/isolation tests and git diff --check; expand only for a concrete failure. No frontend/browser/build rerun for comment-only TypeScript; verify generated assets unchanged. No full Radar/Yahoo/tone/HA1 suite repeat. No live provider, DB, production, dependency install, commit/push/merge, flag activation or deployment. Both flags default OFF.

Protect source/main/other worktrees, B1C/5021, promotion/5033, databases3306/3399, HA1/3461, C:/Users/michi/.radar-ha1-local-qa and Remote Control sessions. HA1 remains closed. POSIX/gunicorn/venv/cwd, live Yahoo/usage conditions, MariaDB runtime and actual topology remain release carries.

Save evidence under radar-design/artifacts/md-selected-price-correction-2/ and a new final fingerprint without overwriting earlier manifests. Write radar-design/MD-SELECTED-PRICE-CORRECTION-2-RETURN.md, update candidate HANDOFF/ledger notices, report exact dirty ownership and stopped owned processes. Stop. No worker dispatch or self-labelled independent review.

MANDATORY FINAL OUTPUT — filled, complete copy/paste return prompt:

You are Radar's Mastermind / Overview. Assess MD-SELECTED-PRICE-CORRECTION-2.
Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch/base/current HEAD: [verified]. Starting/final fingerprints: [values].
Report: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/MD-SELECTED-PRICE-CORRECTION-2-RETURN.md
R2-1 disposition: [exact code change, failing-first result, quarantine/no-second-child and control proof]. N1: [comments corrected].
Fresh checks: [commands/results]. Carried evidence: [separate attribution].
Application/test/docs paths and generated assets: [changes/unchanged hashes].
Limitations/release carries: [POSIX/provider/usage/DB/topology].
Protected state/processes: [facts]. Subagents: none.
Requested decision: assess tiny correction; prepare a different-session changed-lines check plus brief F1-F4 source confirmation to resolve REVIEW-2's same-session qualification. No full review or test repeat.
Read report/handoff/ledger, verify artifacts and update continuity. Do not implement, deploy or dispatch workers automatically.