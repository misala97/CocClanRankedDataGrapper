# HANDOFF — gym first-run workflows + global exercise list (current state, 2026-09-23, after V2)

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
   `b7e3f9c1a2d4`. Before it ships, its `down_revision` must be main's head at that
   moment: `e2c7a9f41b86` today, `c5a1d8e3f207` once G3 + V2 are merged, or
   `flask db upgrade` stops on two heads. The note at the top of that worktree's
   `HANDOFF.md` says so (updated after V2).
3. Main checkout: 18 `radar-design/*.md` show as modified. They are the local copies that
   sat untracked before main tracked the folder; main's versions are newer (diff
   +389/-4348). Not ours; the owner decides. Byte copies of all 85 formerly untracked
   files: `C:\Users\michi\Desktop\CodingStuff-untracked-backup-2026-09-23`, and stash
   c3d92e8 ("85 untracked files main now tracks ...").

## Done in code, NOT shipped: G3, V1, V2 (dev_personal only, pushed)
- G3, 39bc25c: joining a partner is one tap. `matching.py`, the `SharedSessionExercise`
  model and `follower_exercise_for` are gone; follower rows take the leader row's
  exercise id; the confirm page is one card with an optional routine picker. Migration
  `4b8e2d6f1a93` (down `e2c7a9f41b86`) drops `gym_shared_session_exercises`. Rollback
  is clean: `flask db downgrade e2c7a9f41b86` recreates the table empty, and b439e44's
  code refills it with identity rows as its links need them.
- V1, 84dda2b: the add sheet leads with "Deine" (common exercises, clustered by
  movement), then every movement by muscle; variants open a movement page. No migration.
- V2, 4cd8bf2 (mockups cb026e5): a never-done exercise gets 3 blank planned sets. The
  live screen asks for the numbers ("Gewicht eintippen" -> "Wdh. eintippen" -> "Satz
  geschafft"), set 1's numbers fill sets 2 and 3, an "Erstes Mal" note names the
  lifter's other variants (information only), the queue shows "neu". The older owner
  ruling against carrying weight changes forward stands (`_propagate_default_correction`
  unchanged); filling a blank overrides no choice, so it is not such a carry. Migration
  `c5a1d8e3f207` (down `4b8e2d6f1a93`): weight/reps nullable; open placeholder sets
  (flagged, not completed, including ones left open in finished workouts) lose the
  20 kg and, where still 8, the reps. NULL is only ever on an open set: an empty edit
  never writes NULL, completing a set with a blank is refused, and every stats,
  history and record reader filters completed sets (re-audited before the commit).
  Rollback: with the V2 checkout still in place run `flask db downgrade 4b8e2d6f1a93`
  (writes 20 x 8 into every NULL, restores NOT NULL), then reset the checkout to a
  pre-V2 commit, rebuild, restart.
- Ledger entries "G3 done in code", "V1 done in code", "V2 done in code" have the checks.
- Shipping = one merge of dev_personal into main (main is b439e44), push,
  `update_coc.sh`. It carries a prod table drop (G3) and a column change with a data
  rewrite (V2), so it needs Michi's explicit OK. Don't nag. Afterwards alembic heads on
  main = [c5a1d8e3f207].

## Next work
- V3: personal settings UI (G1 cut the form to step/rest/bar/stack). Mockup round first:
  real HTML on the real CSS, 390x844, 3 lanes, one screen per turn, via the impeccable
  skill.
- Possible V1 follow-up (not asked for): the exercise sheet's swap select could put
  the same movement's variants first.
- Optional: an independent review of G1-V2 (subagent), only if Michi names the size.

## Workspace
- Checkout `C:\Users\michi\Desktop\CodingStuff`, branch `dev_personal` (no worktree).
  HEAD is the commit that last updated this file; main is b439e44.
- Dirty but NOT ours; leave alone: `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`, the 18 `radar-design/*.md`, many untracked
  files (`.research/`, scratchpad probes, `brag-output/`, the V2 mock lanes b/c ...).

## Tools / tests
- Harness (session scratchpad):
  `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\acbf7aa7-35c4-4fcf-8a0f-df0174b324ef\scratchpad\`
  - `g1env.py` points the app at `personal_apps_g1` (import before `app`); `G1_DB`
    picks another DB, `G1_APP_DIR` another checkout's code (the .env stays the main one).
  - The scratch DB `personal_apps_g1` is at `c5a1d8e3f207` (V2) and clean.
  - `make_scratch_db.py [name]` copies the dev DB; `run_g1_migration.py` migrates it;
    `run_g3_migration.py` / `run_v2_migration.py` = those migrations both ways.
  - `run_g1_tests.py [args]`: no path argument = every `tests/test_gym*.py` (718 now).
  - `t3rest.sh -W ignore::DeprecationWarning` = full gym suite, compact (`--tb=no`).
  - Browser checks: `v1_check.py` (add sheet), `v2_check.py` (first-time live screen),
    `g3_check.py` (confirm page) serve the app in-process on the scratch DB and clear
    their own leftovers by name. `heads_check.py` = alembic heads + which `app` loads;
    `collide_check.py` = untracked files a ref would overwrite.
  - `mock_privacy_check.py FILES` before committing mock HTML built from real pages:
    usernames, CSRF, VAPID, session ids, emails (prints kinds only).
  - A direct POST from a browser check needs the page's `meta[name=csrf-token]` sent
    as the `csrf_token` form field.
  - Headless capture hangs on a FOLLOWER's live session page (it polls sync.json and
    never fires `load`): use `wait_until='commit'` and check text. Solo pages capture.
- Frontend, from `personal_apps`: `npx vitest run` (512), `npx tsc --noEmit`,
  `npm run build`.
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
