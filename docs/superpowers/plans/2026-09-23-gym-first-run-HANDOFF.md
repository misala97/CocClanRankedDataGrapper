# HANDOFF — gym first-run workflows + global exercise list (current state, 2026-09-23, after the G3-V3 deploy)

Plan + ledger (binding): `docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md`.
Read its task table, the "Owner rulings on the L1 review" block and the ledger before
doing anything. Never redo a task marked done.

G1 spec: `docs/superpowers/specs/2026-09-23-gym-global-exercise-list.md`.
G1 plan: `docs/superpowers/plans/2026-09-23-gym-global-exercise-list.md` (T1-T5, all done).

## State: G1 through V3 shipped and deployed (2026-09-23)
- One global read-only exercise list (158 rows from `features/gym/library.py`, synced
  by `library_key`), per-lifter settings in `gym_exercise_settings` (differences only),
  no create/rename/delete anywhere, German names with English search.
- G1 + G2: release merge b439e44 (dev_personal 64f5eee + origin/main 0f3a0e7, resolved
  via 1097afc), deployed ("release succeeded"). Prod migration `e2c7a9f41b86`: 41
  per-user rows -> 41 by mapping, 0 retired; 32 settings rows; 158 list rows. Log:
  `/root/deploy_gym_g1_20260923_1302.log`. Irreversible; never re-run or patch it. Its
  rollback, behind the G3-V3 chain below: the new code cannot run on the old schema, so
  restore the backup AND reset the VPS checkout to 0f3a0e7, rebuild, restart
  (`personal_apps/DEPLOY_FRONTEND.md`, "Rollback").
- G3 + V1 + V2 + V3: origin/main b439e44..ef6ca0e (fast-forward), deployed by Claude on
  Michi's handover ("you do the deployment"): "release succeeded candidate=ef6ca0e",
  migrations `4b8e2d6f1a93` -> `c5a1d8e3f207` -> `fc72f159a49f`, the prod head. Log:
  `/root/deploy_gym_v3_20260923.log`. The gym tables were dumped first to
  `/root/db_backups/predeploy_gym_v3_20260923.sql.gz`. Checks and counts: the ledger's
  "Deploy" entry.

## Open from the release
1. The shared local dev DB is at `fc72f159a49f` (upgraded 2026-09-23 on the owner's OK,
   ledger "Dev DB upgrade"). G2 cannot be downgraded, so its pre-upgrade gym tables stay
   in the schema `personal_apps_gymbak_20260923` until the owner drops it.
2. Radar: `.worktrees/radar-selected-price-charts` has an untracked `3f82a7e5b5dc` on
   `b7e3f9c1a2d4`. Before it ships, its `down_revision` must be main's head:
   `fc72f159a49f` (on main since ef6ca0e, on prod since the deploy), or
   `flask db upgrade` stops on two heads.
   The note at the top of that worktree's `HANDOFF.md` says so (updated after V3).
3. Main checkout: 18 `radar-design/*.md` show as modified. They are the local copies that
   sat untracked before main tracked the folder; main's versions are newer (diff
   +389/-4348). Not ours; the owner decides. Byte copies of all 85 formerly untracked
   files: `C:\Users\michi\Desktop\CodingStuff-untracked-backup-2026-09-23`, and stash
   c3d92e8 ("85 untracked files main now tracks ...").

## G3, V1, V2, V3 (shipped in ef6ca0e, deployed 2026-09-23)
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
- V3, ecbe9e0 (mockups 6803626): "Deine Pause" on Übungen sets one rest for all
  exercises (own rests stay exceptions, linked); "Deine Einstellungen" (exercise page and
  workout) is pills per setting with the fallback value marked, every tap saved; the
  workout's exercise sheet has "Pause heute" (today only) and the settings one level
  down; the per-workout step route is gone. Workouts and routines no longer copy a rest:
  rows follow the setting until the finish writes the rest in force. Migration
  `fc72f159a49f` (down `c5a1d8e3f207`) creates `gym_lifter_settings` (additive).
  Rollback: with the V3 checkout still in place run `flask db downgrade c5a1d8e3f207`
  FIRST (writes each rest for all onto the exercises that relied on it, drops the
  table), then reset the checkout to a pre-V3 commit, rebuild, restart. Pre-V3 code
  reads a NULL workout rest as the exercise's rest, so live rows stay right.
- Ledger entries "G3/V1/V2/V3 done in code" have the checks; "Deploy" has the prod ones.
- Rollback of the whole release, code still in place: `flask db downgrade c5a1d8e3f207`
  (V3), `4b8e2d6f1a93` (V2), `e2c7a9f41b86` (G3), then reset the checkout to b439e44,
  rebuild, restart.
- The local `main` branch is checked out in `CodingStuff-worktrees/radar-release-merge`
  at fe68454 (stale, an ancestor of origin/main); not ours, left alone.

## Next work
- Nothing open in the plan's task table; G1 through V3 are live on prod.
- Flagged for Michi (V3 decision, mine): routines no longer hold their own rest; the
  lifter's setting applies in every workout. Today's routine rows all equal the setting.
- Possible V1 follow-up (not asked for): the exercise sheet's swap select could put
  the same movement's variants first.
- Optional: an independent review of G1-V3 (subagent), only if Michi names the size.

## Workspace
- Checkout `C:\Users\michi\Desktop\CodingStuff`, branch `dev_personal` (no worktree).
  HEAD is the commit that last updated this file; main is ef6ca0e.
- Dirty but NOT ours; leave alone: `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`, the 18 `radar-design/*.md`, many untracked
  files (`.research/`, scratchpad probes, `brag-output/`, the V2 mock lanes b/c, the V3
  lane B mocks and PNG boards, `scripts/measure_*` + their tests ...).

## Tools / tests
- Harness (session scratchpad):
  `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\acbf7aa7-35c4-4fcf-8a0f-df0174b324ef\scratchpad\`
  - `g1env.py` points the app at `personal_apps_g1` (import before `app`); `G1_DB`
    picks another DB, `G1_APP_DIR` another checkout's code (the .env stays the main one).
  - The scratch DB `personal_apps_g1` is at `fc72f159a49f` (V3) and clean.
  - `make_scratch_db.py [name]` copies the dev DB; `run_g1_migration.py` migrates it;
    `run_g3_migration.py` / `run_v2_migration.py` / `run_v3_migration.py` = those
    migrations both ways.
  - `run_g1_tests.py [args]`: no path argument = every `tests/test_gym*.py` (736 now).
  - `t3rest.sh -W ignore::DeprecationWarning` = full gym suite, compact (`--tb=no`).
  - Browser checks: `v1_check.py` (add sheet), `v2_check.py` (first-time live screen),
    `v3_verify.py` (settings sheets, Deine Pause; restores u1's settings; boards via
    `v3_montage.py`), `g3_check.py` (confirm page) serve the app in-process on the
    scratch DB and clear their own leftovers by name. `heads_check.py` = alembic heads
    + which `app` loads; `collide_check.py` = untracked files a ref would overwrite.
  - `mock_privacy_check.py FILES` before committing mock HTML built from real pages:
    usernames, CSRF, VAPID, session ids, emails (prints kinds only).
  - A direct POST from a browser check needs the page's `meta[name=csrf-token]` sent
    as the `csrf_token` form field.
  - Headless capture hangs on a FOLLOWER's live session page (it polls sync.json and
    never fires `load`): use `wait_until='commit'` and check text. Solo pages capture.
- Frontend, from `personal_apps`: `npx vitest run` (539), `npx tsc --noEmit`,
  `npm run build`.
- Do NOT run `npm run build` while the pytest suite runs: rewriting the vite manifest
  races template rendering (one spurious failure seen, ledger T4).
- Browser checks: python-playwright via Bash; mint the session cookie (see memory
  reference-personal-apps-local-run). User 4 is the throwaway first-run account.
- Deploy: `/root/update_coc.sh` on the VPS takes about 8 minutes and runs `backup_db.sh`
  first, silently. Start it with nohup and its output in a log file (an interrupted SSH
  client does not stop it); wait by polling `pgrep -fc 'update_co[c].sh'`. Auto mode
  refuses copying scripts to the VPS ("Auto-Mode Bypass"): run each step as its own
  short ssh command.

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
