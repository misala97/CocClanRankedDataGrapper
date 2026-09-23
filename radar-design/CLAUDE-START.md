# Claude implementation entrypoint

Implement the Radar recording foundations and first research hub according to these repository artifacts. Codex prepared design and plans; Claude implements. Work one task at a time with independent read-only review after each task. Do not deploy or replace the main Radar route in this pass.

1. Read radar-design/HANDOFF.md, IMPLEMENTATION-SPEC.md, FOUNDATIONS-LEDGER.md and HUB-LEDGER.md completely.
2. Verify Git state and preserve unrelated dirty work. Follow the workspace/baseline gate in docs/superpowers/plans/2026-09-09-radar-foundations.md. The radar-design directory and dated plans are untracked in the planning checkout: explicitly carry them into the implementation worktree and commit only that package there. A bare worktree from HEAD will omit them.
3. Execute foundations F1–F3 with reviews, then docs/superpowers/plans/2026-09-09-radar-research-hub.md H1–H4. H1–H3 can progress if the recording environment is blocked, but keep one worker active and record the sequencing change. H4 requires F3.
4. Use radar-design/index.html and DESIGN.md as visual references. No fake production data. Do not use redesigning-pages-from-data: owner explicitly rejected it for Radar.
5. Update each ledger after tasks. Before a session switch update HANDOFF.md with exact worktree/branch/HEAD, dirty ownership, completed/open tasks, findings, tests, next action and deployment carries. Never redispatch completed work.
6. Return the reviewed opt-in /radar/hub/ for owner review. If code evidence contradicts the plan, record the discrepancy. Material product-contract changes go back to Codex/owner rather than silently changing scope.

Inspection date: 2026-09-09. Codex has not implemented or runtime-tested these plans. Existing ML/source development is separate and protected.
