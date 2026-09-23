# HANDOFF — gym first-run workflows + global exercise list (current state, 2026-09-23)

Plan + ledger (binding): `docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md`.
Read its task table, the "Owner rulings on the L1 review" block and the ledger before
doing anything. Never redo a task marked done.

## Workspace
- Checkout `C:\Users\michi\Desktop\CodingStuff`, branch `dev_personal` (no worktree).
- HEAD is the commit that last updated this file.
- Dirty but NOT ours; leave alone:
  - `personal_apps/scripts/discover_telegram_sources.py`
  - `personal_apps/telegram_candidates.json`
  - many untracked files (`.research/`, scratchpad probes, `brag-output/`, ...)
- UNMERGED and unpushed; merge/push to main only after the owner's explicit OK:
  - 0d37a43 bfb147e 7b7c373 4d6aa08 — the earlier audit round
  - 36d3b30 — F1-F4
  - bdbc2e2 — L1 draft
  - plus the L1-approval commit after it

## Done
- A1: read-only production exercise audit. Findings are in the plan.
- F1-F4 (36d3b30): add-sheet double-add trap, search focus, "Routine" wording, "Pause" label.
- L1: approved by the owner with edits.
  - `personal_apps/features/gym/library.py`: 158 entries.
    - No bodyweight.
    - `fold()` and `matches()` are the search contract: English and German names both
      find an exercise.
  - `library_mapping.py`: 21 production names mapped to keys (approved), plus
    GYM_MARKERS.
  - `tests/test_gym_library.py`: 15 tests, DB-free.

## Owner rulings (short form; full text in the plan)
1. No custom exercises; the list grows in code.
2. Per-user step, rest, stack stops and bar, defaulting to the list.
3. German names for everyone, English search.
4. No bodyweight.
5. One entry per kind of machine. The picker groups variants and shows the one you
   mainly do first.
6. Front Raises: cable, one-handed. Military Press: standing, Langhantel.
7. List content OK; a broader ~800 list maybe later.

## Immediate next action: G1 spec
Write `docs/superpowers/specs/2026-09-2x-gym-global-exercise-list.md`, then implement
on `dev_personal`.

Starting points to verify in code; this is a sketch, not binding:
- Today `gym_exercises` is per user:
  - `UniqueConstraint(user_id, name)`.
  - `SessionExercise.exercise_id` and `TemplateExercise.exercise_id` point at it.
  - Copies are made by `sharing.follower_exercise_for` (mid-session) and by
    `routes/partners.py` (invite accept, 'new' branch).
  - `matching.py` proposes name matches for the shared-session confirm page.
- Likely shape:
  - Global exercise rows keyed by `library_key` and synced from `library.py`
    (idempotent upsert by key).
  - A per-user settings table (user_id, exercise_id, increment, rest, stack_kg, bar)
    holding only the values that differ from the list.
  - Every per-user read goes through one resolver that returns the settings value or
    the list default.
- Audit every query that filters `Exercise.user_id`: catalogue, exercise_detail,
  ownership checks, analytics, export, sharing, partners, seeding and stats. Stats must
  scope by the session's user, not the exercise's.
- G2 migration:
  - Map both users' rows through `PRODUCTION_2026_09`; u3's copies land on the same
    global rows.
  - Re-point session/template rows. Carry differing values into settings (e.g. u1
    Butterfly step 8, rest 150 everywhere). Delete the per-user rows.
  - Irreversible on prod. The owner deploys (`flask db upgrade`); confirm with the owner
    before G2 ships even though the mapping is approved. Nightly DB backups exist.
- UI that must change with G1 (visual reworks need a mockup round first — real HTML on
  the real CSS, 390×844, 3 lanes, one screen per turn, via the impeccable skill):
  - The add sheet loses "Anlegen" (V1).
  - The catalogue's 9-field create/edit form becomes personal settings (V3).
  - V2: the first set of a never-done exercise has no invented 3 × 20 × 8 plan.
  - G3: the shared-session confirm page goes one tap, matching retires.

## Tools / tests
- Library tests, from `personal_apps`:
  `python -m pytest tests/test_gym_library.py -q -p no:cacheprovider`
  → 15 passed; with `tests/test_gym_matching.py`, 26.
- Frontend: vitest 479 passed, tsc clean, `npm run build` ok (as of 36d3b30).
- The gym pytest suite (`-k gym`) binds the LOCAL dev DB and was not re-run this round.
  The only Python change outside the new modules was one comment.
- Browser checks: python-playwright via Bash. User 4 on the dev DB is the throwaway
  first-run account; restore it to empty after use.
- Old review-page generator: `lib_review.py` in the previous session's scratchpad. It
  is obsolete: it imports the removed OPEN/SEEDABLE, and the review is done.

## Rules that bind
- Never commit `.claude/skills/`. Commit only the files you touched, on `dev_personal`.
- No push or merge to main without the owner's explicit OK. The owner deploys; never
  remind him.
- Production DB writes only with an explicit OK.
- No downloads without asking.
