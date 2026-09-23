# HANDOFF — gym first-run workflows + global exercise list (current state, 2026-09-23, after V1)

Plan + ledger (binding): `docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md`.
Read its task table, the "Owner rulings on the L1 review" block and the ledger before
doing anything. Never redo a task marked done.

G1 spec: `docs/superpowers/specs/2026-09-23-gym-global-exercise-list.md`.
G1 plan: `docs/superpowers/plans/2026-09-23-gym-global-exercise-list.md` (T1-T5, all done).

## State: G1 + G2 shipped and deployed (2026-09-23)
- One global read-only exercise list (158 rows from `features/gym/library.py`, synced
  by `library_key`), per-lifter settings in `gym_exercise_settings` (differences only),
  no create/rename/delete anywhere, German names with English search.
- Release merge b439e44 (dev_personal 64f5eee + origin/main 0f3a0e7, resolved via
  1097afc) is on main and dev_personal and deployed (`update_coc.sh`: "release
  succeeded", about 9 minutes including the radar cache warm-up).
- Prod migration `e2c7a9f41b86`: 41 per-user rows -> 41 by mapping, 0 retired; 32
  settings rows; 158 list rows. Full log on the VPS:
  `/root/deploy_gym_g1_20260923_1302.log`. Irreversible; never re-run or patch it.
- If prod breaks because of it: the new code cannot run on the old schema. Restore the
  backup AND reset the VPS checkout to 0f3a0e7, rebuild, restart
  (`personal_apps/DEPLOY_FRONTEND.md`, "Rollback").

## Open from the release
1. The shared local dev DB is still at `b7e3f9c1a2d4`. Claude's upgrade was refused by
   the auto-mode permission guard ("Modify Shared Resources"); the owner runs it or
   allows it (scratchpad `upgrade_dev_db.py`). Its gym tables were copied first to the
   schema `personal_apps_gymbak_20260923`; re-copy if gym rows change before the upgrade.
2. Radar: `.worktrees/radar-selected-price-charts` has an untracked `3f82a7e5b5dc` on
   `b7e3f9c1a2d4`. It must be re-parented onto `e2c7a9f41b86` before it ships, or
   `flask db upgrade` stops on two heads. A note sits at the top of that worktree's
   `HANDOFF.md`.
3. Main checkout: 18 `radar-design/*.md` show as modified. They are the local copies that
   sat untracked before main tracked the folder; main's versions are newer (diff
   +389/-4348). Not ours; the owner decides. Byte copies of all 85 formerly untracked
   files: `C:\Users\michi\Desktop\CodingStuff-untracked-backup-2026-09-23`, and stash
   c3d92e8 ("85 untracked files main now tracks ...").

## G3: done in code, NOT shipped
- 39bc25c on dev_personal (docs in the commit after it): joining a partner is one tap.
  `matching.py`, the `SharedSessionExercise` model and `follower_exercise_for` are gone;
  follower rows take the leader row's exercise id; the confirm page is one card with an
  optional routine picker. Ledger entry "G3 done in code" has the checks.
- Migration `4b8e2d6f1a93` (down `e2c7a9f41b86`) drops `gym_shared_session_exercises`.
  On prod that is a table drop, so merging to main and deploying need the owner's
  explicit OK. Tested both ways on the scratch DB; alembic heads = [4b8e2d6f1a93].
- Shipping it: merge dev_personal into main (main is b439e44; dev_personal is ahead by
  the docs commit 80c5dcf plus G3), push, `update_coc.sh`. The radar worktree's
  `3f82a7e5b5dc` then needs `down_revision = '4b8e2d6f1a93'` instead (its note says so).
- Rollback, unlike G2's, is clean: `flask db downgrade e2c7a9f41b86` recreates the table
  empty, and b439e44's code refills it with identity rows as its links need them.

## V1: done in code, NOT shipped
- 84dda2b on dev_personal: the add sheet leads with "Deine" (common exercises,
  clustered by movement), then every movement by muscle; variants open a movement page.
  No migration: the payload only gained fields. Ledger entry "V1 done in code".
- It ships with the next merge to main. Today that merge also carries G3, whose
  migration drops a prod table: shipping needs the owner's explicit OK either way.

## Next work
- V2: first set of a never-done exercise, no invented plan. Mockup round first.
- V3: personal settings UI (G1 cut the form to step/rest/bar/stack). Mockup round first.
- Mockup rounds: real HTML on the real CSS, 390x844, 3 lanes, one screen per turn, via
  the impeccable skill.
- Possible V1 follow-up (not asked for): the exercise sheet's swap select could put
  the same movement's variants first.
- Optional: an independent review of G1-V1 (subagent), only if Michi names the size.

## Workspace
- Checkout `C:\Users\michi\Desktop\CodingStuff`, branch `dev_personal` (no worktree).
  HEAD is the commit that last updated this file; main is b439e44.
- Dirty but NOT ours; leave alone: `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`, the 18 `radar-design/*.md`, many untracked
  files (`.research/`, scratchpad probes, `brag-output/`, ...).

## Tools / tests
- Harness (session scratchpad):
  `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\acbf7aa7-35c4-4fcf-8a0f-df0174b324ef\scratchpad\`
  - `g1env.py` points the app at `personal_apps_g1` (import before `app`); `G1_DB`
    picks another DB, `G1_APP_DIR` another checkout's code (the .env stays the main one).
  - `make_scratch_db.py [name]` copies the dev DB; `run_g1_migration.py` migrates it.
  - `run_g1_tests.py [args]`: no path argument = every `tests/test_gym*.py`.
  - `t3rest.sh -W ignore::DeprecationWarning` = full gym suite, compact (`--tb=no`).
  - `serve_g1.py` (:5002) + `t5_check.py` = browser checks; `g3_check.py` serves the app
    in-process instead (no separate server) and clears its own leftovers by name;
    `heads_check.py` = alembic heads + which `app` loads; `collide_check.py` = untracked
    files a ref would overwrite; `run_g3_migration.py` = G3 migration both ways.
  - The scratch DB `personal_apps_g1` is at `4b8e2d6f1a93` (G3) and clean.
  - `v1_check.py` = the V1 add-sheet check (in-process, u1 + u4, light/dark/desktop).
  - Headless capture hangs on a FOLLOWER's live session page (it polls sync.json and
    never fires `load`): use `wait_until='commit'` and check text. Solo pages capture.
- Frontend, from `personal_apps`: `npx vitest run`, `npx tsc --noEmit`, `npm run build`.
- Do NOT run `npm run build` while the pytest suite runs: rewriting the vite manifest
  races template rendering (one spurious failure seen, ledger T4).
- Browser checks: python-playwright via Bash; mint the session cookie (see memory
  reference-personal-apps-local-run). User 4 is the throwaway first-run account.
- Deploy: `/root/update_coc.sh` on the VPS takes about 9 minutes. Run it with its output
  in a log file; an interrupted SSH client does not stop it.

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
- No push or merge to main without the owner's explicit OK. The owner deploys unless the
  deploy is explicitly handed over.
- Production DB writes only with an explicit OK.
- No downloads without asking.
- No subagents or other quota spend unless Michi names the size.
