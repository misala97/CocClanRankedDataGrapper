# HANDOFF — gym first-run workflows + global exercise list (current state, 2026-09-23)

Plan + ledger (binding): `docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md`.
Read its task table, the "Owner rulings on the L1 review" block and the ledger before
doing anything. Never redo a task marked done.

G1 spec: `docs/superpowers/specs/2026-09-23-gym-global-exercise-list.md`.
G1 plan: `docs/superpowers/plans/2026-09-23-gym-global-exercise-list.md` (T1-T5, all done).

## State: G1 + G2 done in code, nothing merged
- One global read-only exercise list (158 rows from `features/gym/library.py`, synced
  by `library_key`), per-lifter settings in `gym_exercise_settings` (differences only),
  no create/rename/delete anywhere, German names with English search.
- G2 migration `e2c7a9f41b86` (down_revision main's `b7e3f9c1a2d4`) is committed but has
  NOT run on prod. It is irreversible (`downgrade()` refuses; nightly backups exist).
- Verified: vitest 488, tsc + build clean, gym pytest 718 passed on the migrated scratch
  DB, T5 browser checks 23/23 at 390×844 (u4 + u1), merged-tree graph check (single head,
  fresh dev copy upgrades). Details in the ledger.

## Waiting on the owner (do not proceed without an explicit OK)
1. Merge origin/main into dev_personal? 85 untracked radar files in the main checkout
   collide (61 identical, 24 differ). The resolved merge is on branch
   `dev_personal-main-sync` (1097afc); merging dev_personal into it is clean (checked).
2. G2 ships only with explicit confirmation, even though the mapping is approved.
3. At merge time `flask db heads` must show one head. On the merged tree it is
   `e2c7a9f41b86`. The radar worktree's untracked `3f82a7e5b5dc` also sits on
   `b7e3f9c1a2d4`; if it lands first it is a second head and needs a merge revision.
4. The shared dev DB is untouched (at `b7e3f9c1a2d4`); it needs `flask db upgrade` after
   the merge.
5. An independent review of G1/G2 (subagent) runs only if Michi names the size.

## Next work (after the owner's calls)
- G3: shared sessions already log the leader's ids (identity map); retire `matching.py`,
  the map table and the confirm page's picker -> one tap.
- V1: add-sheet picker that groups variants of one movement, the one you mainly do first
  (G1 did the functional list-only search). Mockup round first.
- V2: first set of a never-done exercise, no invented plan. Mockup round first.
- V3: personal settings UI (G1 cut the form to step/rest/bar/stack). Mockup round first.
- Mockup rounds: real HTML on the real CSS, 390×844, 3 lanes, one screen per turn, via
  the impeccable skill.

## Workspace
- Checkout `C:\Users\michi\Desktop\CodingStuff`, branch `dev_personal` (no worktree).
  HEAD is the commit that last updated this file.
- Dirty but NOT ours; leave alone: `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`, many untracked files (`.research/`,
  scratchpad probes, `brag-output/`, ...).
- UNMERGED and unpushed (merge/push to main only after the owner's explicit OK):
  - 0d37a43 bfb147e 7b7c373 4d6aa08 — the earlier audit round
  - 36d3b30 — F1-F4; bdbc2e2 883375e 002991b — L1 draft, handoff, approval
  - 80a833a — G1 spec; 3e81749 — T1 core; 812dad8 — G2 migration
  - cf65778 — T3 backend; 9141915 — T4 UI; plus the docs commit carrying this file

## Tools / tests
- Harness (session scratchpad):
  `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\acbf7aa7-35c4-4fcf-8a0f-df0174b324ef\scratchpad\`
  - `g1env.py` points the app at `personal_apps_g1` (import before `app`).
  - `make_scratch_db.py [name]` copies the dev DB; `run_g1_migration.py` migrates it.
  - `run_g1_tests.py [args]`: no path argument = every `tests/test_gym*.py`.
  - `t3rest.sh -W ignore::DeprecationWarning` = full gym suite, compact (`--tb=no`).
  - `serve_g1.py` (:5002) + `t5_check.py` = the T5 browser checks; `graph_check.py` =
    heads + upgrade against a worktree; `drop_scratch_db.py`, `alembic_rev.py`.
  - The scratch DB `personal_apps_g1` is migrated and clean (T5 removed what it made).
- Frontend, from `personal_apps`: `npx vitest run`, `npx tsc --noEmit`, `npm run build`.
- Do NOT run `npm run build` while the pytest suite runs: rewriting the vite manifest
  races template rendering (one spurious failure seen, ledger T4).
- Non-gym failures on the scratch DB, not checked against a baseline: test_radar_yahoo
  (3), test_radar_api (1), test_diagnose_extractor_feedback (1); most likely because the
  scratch DB has no radar data.
- Browser checks: python-playwright via Bash; mint the session cookie (see memory
  reference-personal-apps-local-run). User 4 is the throwaway first-run account.

## Owner rulings (short form; full text in the plan)
1. No custom exercises; the list grows in code.
2. Per-user step, rest, stack stops and bar, defaulting to the list.
3. German names for everyone, English search.
4. No bodyweight.
5. One entry per kind of machine. The picker groups variants and shows the one you
   mainly do first.
6. Front Raises: cable, one-handed. Military Press: standing, Langhantel.
7. List content OK; a broader ~800 list maybe later (ask first).

## Rules that bind
- Never commit `.claude/skills/`. Commit only the files you touched, on `dev_personal`.
- No push or merge to main without the owner's explicit OK. The owner deploys; never
  remind him.
- Production DB writes only with an explicit OK.
- No downloads without asking.
- No subagents or other quota spend unless Michi names the size.
