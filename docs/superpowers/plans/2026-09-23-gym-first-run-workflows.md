# Gym first-run workflows (2026-09-23) — plan + ledger

Source: inline analysis of two workflows as a brand-new account (user 4 on the dev DB,
390x844, python-playwright): (1) a first workout without a routine, adding exercises as
you go; (2) creating and configuring an exercise the first time. Owner: "YES to
everything", plus: the starter list becomes a COMPLETE exercise library, and a read-only
audit of the production exercises. Branch `dev_personal`; commit only files touched here.
No push to main without an explicit OK. Prod DB writes only with an explicit OK.

Decisions (owner): library names in German, pattern `Bewegung (Gerät[, Variante])`, e.g.
`Bankdrücken (Langhantel)`; the library is complete, not a starter subset; one term:
**Routine** (never Vorlage) in UI copy.

## Findings (evidence: screenshots t_* in the session scratchpad)

Workflow 1: every exercise typed from memory (no library); after "Anlegen" the only row
under the thumb is the new exercise and tapping it adds a 2nd copy (confirmed: "2× drin");
the sheet opens with focus on "Fertig" and keeps the old query after a create; every new
exercise gets an invented plan 3 x 20 kg x 8 shown like a real plan (60 kg = 16 taps; typing
not hinted); mid-workout creation = name only (stack, no group, bilateral, 2.5 step, 180 s);
empty workout screen noisy (rail labels, 0-totals, add button x2 + menu); Vorlage/Routine
mixed; rest countdown unlabelled.

Workflow 2: catalogue create = 9-field jargon form, submit below the fold, placeholders
look like values (180 / 2,5 / 0), no defaults derived from equipment; after the first
workout the catalogue shows 10 empty group bands before your own exercises (all under
"Ohne Gruppe"); a created row lands off-screen (y=1563, page at top); detail link names
the wrong fields; edit sheet "Einseitig" label in caps style.

Prod audit (read-only, 2026-09-23): 2 lifters (u1 mgemmel 21 exercises, u3 jglaser 20).
No cross-user references, no odd sets, no 0 kg sets. Every exercise created mid-workout
(4 on 2026-09-12, copied to u3 via the shared session) is unconfigured: no muscle group,
equipment left on stack, no increment, rest 180 vs the usual 150; names drift from the
English pattern (`Bizeps SZ Kabel`, `Hammer Curl (Kabel)`, `Front Raises`, typo
`Later Raise Iso`, `Lat Pulldown Kabelzug`, `Preacher Curl Bilateral`). u1 `Front Raises`:
flagged unilateral on a stack, stack_kg spells out an even 5..50 grid (duplicates increment
5), one set logged at the invented 20 kg. u3 `Preacher Curl (Machine, Good)` has no
increment -> steps 1.25 (the August bug, again). u3 `Lat Pulldown Kabelzug` never used.
Code: the invite-accept 'new' branch (partners.py) copies name/group/rest/unilateral only,
while the mid-session copy (sharing.follower_exercise_for) also copies equipment, bar,
stack and secondary groups -- the two creation paths disagree.

## Tasks

| id | what | status |
|----|------|--------|
| A1 | Read-only prod exercise audit | done (report to owner; data fixes folded into G2) |
| F1 | Add sheet: after add/create clear the query, keep focus, confirm "✓ X ist drin"; re-adding an exercise already in the workout needs a confirming 2nd tap | done |
| F2 | Add sheet opens with focus in the search field | done |
| F3 | "Routine" everywhere in UI copy | done |
| F4 | Rest countdown labelled "Pause" | done |
| F5 | Catalogue: new row in view; own exercises before empty groups | folded into G (the catalogue's job changes) |
| F6 | Detail edit link + Einseitig label | folded into G (the edit form becomes personal settings) |
| F7 | Start muscle chart for ungrouped sets | folded into G (every list exercise has a group) |
| F8 | Invite-accept 'new' branch copies equipment facts | folded into G (no follower copies at all) |
| L1 | THE list: complete exercise library as data (German names, config per entry, EN aliases) + prod mapping + review page | done — owner-approved with edits (rulings below) |
| G1 | Spec: `library.py` becomes the one read-only exercise list for both lifters; NO custom exercises; per-user overrides of step/rest/stack stops/bar defaulting to the list; stats scoped by user | done — 80a833a spec, 3e81749 cf65778 9141915; shipped in b439e44, deployed 2026-09-23 |
| G2 | Migration: map the 41 prod exercises onto list entries (mapping table owner-approved), re-point sessions/routines/shared rows, drop the copies | done — 812dad8; ran on prod 2026-09-23 (41 -> 41 by mapping, 0 retired) |
| G3 | Shared sessions on shared ids: retire matching/mapping, confirm page = one tap | done in code — 39bc25c on dev_personal, UNMERGED; migration 4b8e2d6f1a93 drops `gym_shared_session_exercises` on prod, ships only with the owner's OK |
| V1 | Add sheet = pick from the list (search per `library.matches`, groups; variants of one movement grouped, the one you mainly do first), no create path — mockup round, then build | done in code, 84dda2b (unmerged) — lane D from the mockup round (owner: "Build it like that") |
| V2 | First set of a never-done exercise (no invented plan) — mockup round, then build | done in code, 4cd8bf2 (unmerged) — lane A "Du tippst" (owner: "Ja A siehr am besten aus"); migration c5a1d8e3f207 blanks open placeholder sets on prod, ships only with the owner's OK |
| V3 | Personal exercise settings (replaces the 9-field form) — mockup round, then build | open — G1 T4 cut the form to the four personal fields; the redesign remains |

Direction change (owner, 2026-09-23 mid-round): "One list of preconfigured read only
exercises for every user" -- replaces per-user exercise rows (per-user since 2026-08-02).
Shared sessions then log the same exercise id on both sides. Order: L1 -> review -> G1.

Owner rulings on the L1 review (2026-09-23), binding for G1-V3:
1. No custom exercises. Two lifters, one gym: the list is static and grows in code.
2. Per-user settings yes (step, rest, uneven stack stops, bar), with sensible defaults
   from the list. Migrated values that differ from the list become personal settings.
3. German names for everyone; English names stay searchable ("chest fly" and
   "butterfly" both work) -- `library.matches` is the contract.
4. Bodyweight dropped for now.
5. One entry per kind of machine: the "(Good)"/"Hauptbahnhof" labels go. Think about
   variants: "we have 2 preacher curls and we only do one mainly" -> the picker groups
   the variants of one movement and puts the one you mainly do first.
6. Front Raises = cable, one-handed. Military Press = standing, Langhantel. One cable
   curl entry; the attachment does not matter.
7. List content is fine for now; a broader list (~800, e.g. free-exercise-db) may be
   downloaded and adjusted later -- not now.

## Ledger

(append: date, task, commit, tests)

- 2026-09-23 — A1: `gym_ex_audit.py` run on the VPS inside `START TRANSACTION READ ONLY`
  + rollback, script deleted after. Findings above.
- 2026-09-23 — F1-F4 in one commit. Add sheet: focus via `[data-autofocus]` after
  showModal (Sheet.tsx); query clears only once the payload holds one more of the
  exercise (a failed write keeps it for a retry); a row already in the workout arms on
  the first tap ("Nochmal hinzufügen?", attention hue) and adds on the second. Routine
  replaces Vorlage in every UI string. Countdown: "Pause" stacked above the time (beside
  it left 5px at 390). Tests: vitest 479 (3 new), tsc clean, build ok. Driven at
  390x844 as user 4: focus lands in the field, create -> field empty + "✓ Bankdrücken
  ist drin.", 1st tap on the row arms (1 row in workout), 2nd adds (2 rows); countdown
  gap to the label 44px at 390, 29 at 360, 9 at 320. User 4 restored empty.
- 2026-09-23 — L1 draft: `features/gym/library.py` (173 entries: 158 loggable, 15
  bodyweight held out of SEEDABLE), `features/gym/library_mapping.py` (the 21 prod names
  -> keys, 3 OPEN calls), `tests/test_gym_library.py` (12, DB-free). Curated from domain
  knowledge for a German commercial gym, no external dataset downloaded. The Gerät in
  the name decides loading/bar/step; `(Maschine)` = stack, `(Maschine, Scheiben)` =
  plate-loaded and must state per side. Aliases are generic EN/DE search terms; prod
  names live only in the mapping. Review page (scratchpad `lib_review.py` renders it from
  the module) sent to the owner. Decisions asked: (1) private exercises as a fallback?
  (2) per-user step/rest/stack stops/bar on top of the list? (3) history takes the
  German names? (4) bodyweight type now/later/never? (5) one entry per loading, so the
  "(Good)"/"Hauptbahnhof" labels go? Rest defaults 180/150/90/60 vs the owner's 150
  everywhere -- per-user rest is what (2) decides.
- 2026-09-23 — L1 approved (rulings above). Applied: 15 bodyweight entries and the
  Körpergewicht Gerät removed (158 entries, SEEDABLE gone); `fold()`/`matches()` added
  as the search contract (all words, any order, fragments, ae/ä/a, hyphens); the
  lifters' English names added as aliases minus gym markers; `library_mapping` OPEN
  resolved (mapping unchanged, now approved; GYM_MARKERS lists the dropped words).
  Tests: `test_gym_library.py` 15 passed (+ matching 11).
- 2026-09-23 — G1 spec + plan: `docs/superpowers/specs/2026-09-23-gym-global-exercise-list.md`
  (80a833a), plan `docs/superpowers/plans/2026-09-23-gym-global-exercise-list.md` (T1-T5).
  Every DB test and run on the scratch copy `personal_apps_g1`; the shared dev DB untouched.
- 2026-09-23 — G1 T1 (3e81749): `features/gym/exercises.py` pure core (`sync_plan`,
  `Setup`, `resolve`, `to_store`), DB-free tests in `tests/test_gym_exercises.py`.
- 2026-09-23 — G2 (812dad8): revision `e2c7a9f41b86` on main's head `b7e3f9c1a2d4`
  (additive DDL, one DML transaction ending in invariant checks, guarded drops;
  `downgrade()` refuses). `library_mapping.py` folded into the revision as the frozen
  `PRODUCTION_2026_09`; helpers tested by path. On a fresh dev copy: 36 per-user rows ->
  34 by mapping, 2 retired ('Probe Neu'), 25 settings rows, 158 list rows.
- 2026-09-23 — G1 T3 (cf65778): backend on the global list -- `Exercise` global by
  `library_key` with `list_*` values, `ExerciseSettings` holds only differences, every
  read resolves through the session's/routine's lifter, create/rename/delete routes gone
  (name-only add/replace = 400), shared sessions on the leader's ids (identity map),
  `_GoneFromExercise` makes the old attribute names fail loudly. Gym suite on the
  migrated scratch DB: 716 passed + 1 xfailed (the form/route pairing test, T4 scope);
  pre-G1 baseline 688. `test_scripts` 7 passed.
- 2026-09-23 — G1 T4 (9141915): UI without create paths. Add sheet searches the whole
  list on the `matches` contract (`search` per row + TS `fold` in `src/search.ts`, cases
  = Python's outputs), no create row, "Keine Übung in der Liste passt zu …". Replace
  picks same group, else the whole list. Catalogue: no create sheet/"anlegen"; empty
  bands/state point to "Übung hinzufügen" in a workout. Detail: no delete; settings
  sheet = step/rest/bar/(stack) prefilled, list values as placeholders, identity as
  text. Shared confirm: no `new`. Payloads lose can_delete/added_id/name_taken and the
  create sheet's fields; dead CSS removed; pairing test un-xfailed. vitest 488 passed,
  tsc + build clean, gym pytest 718 passed. One earlier run failed
  `test_an_empty_account_gets_the_checklist` once: it overlapped `npm run build`
  rewriting the vite manifest while `GET /gym` rendered; alone, in its file pair and
  in a clean full rerun it passes.
- 2026-09-23 — G1 T5: python-playwright at 390x844 on the scratch DB (serve_g1.py,
  :5002), 23/23 checks as user 4 and u1: 158 rows in the add sheet, no create row,
  "bench press" finds Bankdrücken (Langhantel); rest from the lifter's setting (u1 Latzug
  180) else the list (u4 150, bench 180 both); detail saves step 8 as u4's own, blank
  drops it (back to the list's 5); catalogue = touched only (u4 0 -> empty state, then
  2; u1 20). Screenshots read back; sessions and settings the run made removed. Graph:
  temp worktree at `dev_personal-main-sync` (1097afc) + `git merge dev_personal` -> clean,
  alembic heads = [e2c7a9f41b86], a fresh dev copy upgraded b7e3f9c1a2d4 -> e2c7a9f41b86;
  worktree and copy removed.
- 2026-09-23 — Release + deploy (owner: "merge this", then an explicit OK to push to
  main and deploy; the nightly backup is the rollback, no gym activity since it).
  b439e44 = 64f5eee + 1097afc, built in a temp worktree. Checks on that tree: alembic
  heads [e2c7a9f41b86], tsc clean, vitest 488, build clean, gym pytest 718 passed on the
  scratch DB. G2 reviewed for MariaDB 10.11 first: portable SQL only; the user_id FK and
  every index holding user_id drop before the column. Pushed main 0f3a0e7..b439e44 and
  dev_personal 22b3191..b439e44; `update_coc.sh` on the VPS: "release succeeded",
  migration 41 per-user rows -> 41 by mapping, 0 retired, 32 settings rows, 158 list
  rows; all services active, no errors in the web/notifier logs, `/gym` answers.
  Main checkout fast-forwarded after stashing (c3d92e8) and copying the 85 untracked
  files main now tracks, then restoring them byte for byte (18 `radar-design/*.md`
  differ from main and show as modified). Temp worktree and helper branches removed.
  Dev DB upgrade refused by the permission guard; gym tables copied to
  `personal_apps_gymbak_20260923`. Radar carry noted in radar-selected-price-charts'
  HANDOFF.
- 2026-09-23 — G3 done in code, 39bc25c (dev_personal, unmerged). `matching.py` +
  `test_gym_matching.py` deleted; `SharedSessionExercise` model and
  `sharing.follower_exercise_for` removed; `reconcile_follower` gives a new follower row
  the leader row's exercise id; accept reads no `match_` answers (a stale page's are
  ignored) and writes no map rows; the confirm payload's `proposals` became `exercises`
  (the leader's, in order, each once). Confirm page = one card ending in Mitmachen; the
  optional routine picker stays (preselect rule unchanged), its disclosure reads
  "Routine ändern" / "Routine wählen" and is absent without a covering routine; dead CSS
  (`.confirm__ask`, `.confirm__tick`, the in-card field rules) removed. Migration
  4b8e2d6f1a93 (down e2c7a9f41b86) drops `gym_shared_session_exercises`, guarded both
  ways; downgrade recreates it empty with the old FK/unique/index names. On the scratch
  DB: up, up (no-op), down (shape checked), down (no-op), up; counts unchanged; alembic
  heads = [4b8e2d6f1a93]. tsc clean, vitest 481 passed, build clean, gym pytest 702
  passed. Browser check (in-process server on the scratch DB, 390x844, u1 leader -> u4):
  14/14 — card lists the three exercises, no select or `match_` field without a
  routine, "Zählt als G3 Brust." + "Routine ändern" with one, Mitmachen lands on the
  follower session logging the leader's ids in order under that routine. The live
  session page never fires `load` and headless capture hangs on it (polls sync.json),
  so that step checks text. Rows the runs made removed (checked). NOT shipped: the
  migration drops a prod table, so push to main + deploy wait for the owner's OK.
- 2026-09-23 — V1 mockup round: lanes A/B/C, then lane D = the owner's mix of C and B
  ("my common ones first and the rest in a properly ordered list by movement"); mockups
  committed in 5727236 (`personal_apps/scratchpad/puls/v1_picker/`). Owner: "Build it
  like that".
- 2026-09-23 — V1 done in code, 84dda2b (dev_personal, unmerged; no migration).
  Server: `exercises.usage` (finished workouts with a completed set, counted once per
  workout; weight = sum of 0.5^(age_days/42); rank by weight, workouts, last done;
  common = 2+ workouts and >= 15% of the lifter's own top weight, so a break does not
  empty "Deine"; only exercises the picker offers are ranked, so a retired row cannot
  set the bar). `library.MOVEMENT_GROUP` / `LIST_GROUPS` / `Entry.label`. Catalogue
  rows gained movement, label, movement_group, workouts, days_ago, rank, common; the
  payload gained list_groups. Client: `session/picker.ts` (clusters, sections, search
  order, metas) and a rewritten `AddExerciseSheet`: "Deine" clusters, "Alle Übungen"
  by muscle A-Z, one-tap add for one-variant movements, a movement page (level 2) for
  the rest with Zurück (`Sheet` got `onBack`), "meistens" only when there is a choice.
  No autofocus; a list tap keeps the keyboard down and focus on the row (aria-disabled
  while busy -- `disabled` dropped focus onto the page behind, found in the browser
  check); the sheet keeps one height at every level (it collapsed on level 2 and on an
  empty search, moving the field under the thumb). Fixture regenerated from the
  scratch DB; `make_session_fixture._stabilise` now anonymises partners. Checks: tsc
  clean, vitest 498, build clean, gym pytest 709 passed (scratch DB). Browser check
  `v1_check.py` (in-process server, scratch DB, 390x844 + 1280x800 + dark): all pass —
  no overflow, every control >= 44px, sticky group head at 72px, level 2 focus/scroll
  both ways, add from level 2 lands with focus held, first run for u4, no console
  errors. Solo live session pages screenshot fine; only follower pages poll.
- 2026-09-23 — V2 mockup round: lanes A "Du tippst" (blank fields, the button asks
  for each number), B "Vom Gerät" (tap one of the machine's real weights, then the
  reps), C "Probesatz" (set 1 is a trial, then a step up or down), each at three moments
  (Langhantel with other variants known, Maschine with nothing known, while typing).
  Owner picked A. Lane A committed in cb026e5 (`personal_apps/scratchpad/puls/v2_first_set/`
  a1-a3 + `cmp_a.html`; B/C left untracked).
- 2026-09-23 — V2 done in code, 4cd8bf2 (dev_personal, unmerged). Server: a blank plan
  is NULL weight/reps with `is_default_seeded` kept; `_seeded_sets` plans 3 blank sets
  (DEFAULT_PLAN_WEIGHT/REPS gone). Migration c5a1d8e3f207 (down 4b8e2d6f1a93): both
  columns nullable, open flagged sets lose the 20 kg and (where still 8) the reps;
  downgrade writes 20 x 8 into every NULL. `gym_toggle_set_complete` refuses a set
  with a blank (stays open, keeps the number it had, no rest -- the same quiet refusal
  as `gym_add_set`) and, live only, `_fill_blanks_after` gives the open sets after a
  logged one its numbers. The flag-based `_propagate_default_correction` is unchanged
  (owner ruling); None -> value always counts as a change. Deload skips flagged and
  blank sets. Payload: `live_floor` (bar, else lightest stack stop, else one step) and
  `first_time` {se id: up to 2 VariantRefs -- the lifter's other variants of the
  movement by usage rank, top set of the latest non-deload workout; information only}.
  Export emits null for a blank open set. Client: `Stepper` blank state (dashed slot,
  "-" disabled, "+" lands on `live_floor`, `open()` handle focusing inside the tap so
  iOS raises the keypad, `enterKeyHint` "next" chaining kg -> Wdh., `onDraft`); the go
  button reads "Gewicht eintippen" / "Wdh. eintippen" / "Satz geschafft"; chips "Satz N";
  "Erstes Mal" note with the refs; queue "neu"; optimistic tick mirrors the fill.
  Checks: tsc clean, vitest 512 passed, build clean, gym pytest 718 passed (scratch DB,
  now at c5a1d8e3f207); migration up/down/up on the scratch DB with marker rows.
  Browser check `v2_check.py` (in-process server, scratch DB, 390x844 + 1280x800 +
  dark): all pass — blank chips, note, empty slots, keypad Enter flow, ring while
  typing, sets 2/3 take 40 x 10 on screen and in the DB, note gone after set 1, queue
  "neu", u1's refs, "+" lands on the 20 kg bar, no overflow, controls >= 44px, no
  console errors. NOT shipped: the migration rewrites open sets on prod.
