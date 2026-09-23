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
| L1 | THE list: complete exercise library as data (German names, config per entry, EN aliases) + prod mapping + review page | draft done — awaiting owner review + 5 decisions (see ledger) |
| G1 | Spec: one global read-only exercise list for every user; per-user settings (increment, rest, uneven stack stops); custom exercises yes/no; stats scoped by user | open (after L1 review) |
| G2 | Migration: map the 41 prod exercises onto list entries (mapping table owner-approved), re-point sessions/routines/shared rows, drop the copies | open |
| G3 | Shared sessions on shared ids: retire matching/mapping, confirm page = one tap | open |
| V1 | Add sheet = pick from the list (search + groups), no create-first — mockup round, then build | open (after G1) |
| V2 | First set of a never-done exercise (no invented plan) — mockup round, then build | open |
| V3 | Personal exercise settings (replaces the 9-field form) — mockup round, then build | open (after G1) |

Direction change (owner, 2026-09-23 mid-round): "One list of preconfigured read only
exercises for every user" -- replaces per-user exercise rows (per-user since 2026-08-02).
Shared sessions then log the same exercise id on both sides. Order: L1 -> review -> G1.

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
