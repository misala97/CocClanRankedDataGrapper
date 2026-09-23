# HANDOFF — gym first-run workflows + global exercise list (current state, 2026-09-23)

Plan + ledger (binding): `docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md`.
Read its task table and ledger before doing anything; never redo a task marked done.

## Workspace
- Checkout `C:\Users\michi\Desktop\CodingStuff`, branch `dev_personal` (no worktree).
- Code HEAD `bdbc2e2`; this file is committed right after it.
- Dirty but NOT ours (leave alone): `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`, and the many untracked files (`.research/`,
  scratchpad probes, `brag-output/`, ...).
- UNMERGED + unpushed, waiting on the owner's explicit OK to merge/push to main:
  0d37a43 bfb147e 7b7c373 4d6aa08 (the earlier audit round), 36d3b30 (F1-F4) and bdbc2e2 (L1).

## Done
- A1: read-only production exercise audit. Output is in the old session's scratchpad
  (`%TEMP%\claude\C--Users-michi-Desktop-CodingStuff\6873abbb-66c9-4cd0-829b-e18d182cb9c8\scratchpad\prod_audit.txt`).
- F1-F4 (36d3b30): the add sheet no longer adds a second copy of the exercise just made,
  focus lands in the search field, the UI says "Routine" everywhere, and the rest
  countdown is labelled "Pause".
- L1 draft (bdbc2e2):
  - `personal_apps/features/gym/library.py`: 173 entries, SEEDABLE = 158; the 15
    bodyweight entries are left out.
  - `library_mapping.py`: the 21 production names mapped to keys, plus OPEN (3 calls).
  - `tests/test_gym_library.py`: 12 tests, DB-free.

## Waiting on the owner (the next action is to apply the answers)
1. Private exercises as a fallback? (Recommended: yes, asking the same 3 facts the list
   answers, not the 9-field form.)
2. Per-user step, rest, uneven stack stops and bar weight on top of the list?
   (Recommended: yes. The owner's 8 kg stacks and 150 s rest can't live in a global row.)
3. History takes the German names, with the old English names findable in search?
4. Bodyweight: a new loading type "Körpergewicht + Zusatzgewicht" plus reps-based
   records — now, later, or drop?
5. One entry per loading, not per gym? The "(Good)" and "Hauptbahnhof" labels would go.
- Mapping calls (library_mapping.OPEN):
  - Front Raises: one arm on the cable, both hands, or dumbbells?
  - Military Press: standing or seated?
  - Cable curl: one entry, with no entry per attachment. Fine?
- Plus any list edits (renames, additions, removals) from the review page.

## Then, in order
- G1: spec for the global read-only list. Include per-user settings, custom
  exercises and stats scoped by user, per the answers.
- G2: migrate production.
  - Re-point sessions, routines and shared rows onto the list and drop the copies.
  - PRODUCTION DB WRITES ONLY WITH AN EXPLICIT OK. The mapping table needs owner approval.
- G3: shared sessions on shared ids. Retire matching/mapping; the confirm page becomes one tap.
- V1 (add sheet = pick from the list), V2 (first set of a never-done exercise, no
  invented 3 × 20 × 8 plan), V3 (personal settings sheet):
  - Each needs a mockup round first: real HTML on the real CSS, 390×844, 3 lanes, one
    screen per turn, through the impeccable skill.
  - Code only after the owner picks.

## Tools / tests
- Library: `cd personal_apps && python -m pytest tests/test_gym_library.py -q -p no:cacheprovider`
  → 12 passed.
- Review page: `lib_review.py` + `lib_review.tpl.html` in the old scratchpad (path above).
  - Run it from personal_apps with `PYTHONIOENCODING=utf-8 PYTHONPATH=.`.
  - It writes `lib_review.html` next to itself.
  - Copy both files if that directory is gone.
- F1-F4 checks: vitest 479 passed, tsc clean, `npm run build` ok. The gym pytest suite was
  not re-run for F1-F4 or L1: the Python change was one comment plus new standalone modules.
- Browser checks: python-playwright via Bash. User 4 on the dev DB is the throwaway
  first-run account; restore it to empty afterwards.

## Rules that bind
- Never commit `.claude/skills/`. Commit only the files you touched, on `dev_personal`.
- No push or merge to main without the owner's explicit OK. The owner deploys.
- Nothing is wired to the library yet, so there are no deploy carries.
