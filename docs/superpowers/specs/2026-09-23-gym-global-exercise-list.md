# Gym: one global exercise list with personal settings (G1 + G2)

Status: spec, 2026-09-23. Plan + ledger: `docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md`
(tasks G1, G2). The owner's rulings there are binding and not repeated in full here.

## Goal (owner's words)

"One list of preconfigured read only exercises for every user." Every lifter picks from
`features/gym/library.py`; nobody creates, renames or deletes an exercise. Each lifter can
set four values for themselves — step, rest, uneven stack stops, bar — and everything else
(name, muscle groups, equipment, one side or both) is the list's. Two partners in a shared
workout log the same exercise id.

Observable end state:
- A first-time user finds all 158 exercises in the add sheet, already set up. There is no
  "Anlegen" anywhere.
- The production exercises (u1: 21, u3: 20) are gone as rows. Their history now sits on
  list exercises with German names. Every value that differed from the list survives as that
  lifter's personal setting (e.g. u1's Butterfly step 8, rest 150).
- Lifter A's settings never change what lifter B sees, and neither sees the other's
  history, on the same exercise id.

## Data model

`gym_exercises` becomes global: one row per list entry.
- New: `library_key` String(64), unique. It is NULL only on a *retired* row (see
  Migration) — a row kept for history that has no list entry.
- Kept as list facts, read-only: `name`, `muscle_group`, `secondary_muscle_groups`,
  `equipment`, `is_unilateral`.
- Kept as the list's defaults for the four personal values: DB columns `weight_increment`,
  `default_rest_seconds`, `stack_kg`, `bar_weight`. Their ORM attributes are renamed to
  `list_increment`, `list_rest_seconds`, `list_stack_kg` and `list_bar_weight`. A leftover
  read of `exercise.weight_increment` then fails loudly instead of quietly returning the
  list's value where the lifter's was meant.
- Dropped: `user_id` (with `fk_gym_exercises_user_id`, `ix_gym_exercises_user_id` and
  `uq_gym_exercises_user_id_name`) and `previous_name`. The relationships
  `Exercise.session_exercises` and `Exercise.template_exercises` go too. Their only
  readers were the two delete checks, and an unscoped walk from a shared row into history
  is exactly the leak to make impossible.

New `gym_exercise_settings` (model `ExerciseSettings`): one row per lifter per exercise
they changed.
- `id`; `user_id` FK `app_user`, indexed; `exercise_id` FK `gym_exercises` ON DELETE
  CASCADE.
- `weight_increment` Float, `default_rest_seconds` Integer, `stack_kg` JSON and
  `bar_weight` Float, all nullable. NULL means "the list's value".
- Unique `(user_id, exercise_id)`.

Rules for the stored values:
- A value is stored only while it differs from the list. Saving the list's value, or a
  blank, stores NULL. A row whose four values are all NULL is deleted. That way a later
  change to the list's default still reaches everyone who never changed it.
- `bar_weight`: 0 and NULL mean the same thing ("nothing inside the number"). 0 is stored
  only when the list has a bar, to switch it off.
- `stack_kg` follows today's rules: ascending real stops, only for `equipment == 'stack'`.
  While it is set it decides the steps, so the increment is not consulted.
- The effective value is `settings.value if not NULL else exercise.list_value`. A retired
  row can still lack an increment; `stats.resolve_increment` keeps supplying the default,
  as it does today.

## Module `features/gym/exercises.py`

This module holds the exercise rows and each lifter's view of them.

- `sync_library(connection)`: idempotent upsert of `library.LIBRARY` into
  `gym_exercises`, keyed by `library_key`. It inserts missing entries and updates changed
  facts and defaults. It never deletes. A key that leaves the list keeps its row (history)
  and simply stops being offered. It runs on Core statements over its own connection, so it
  never commits a request's pending ORM work.
- `ensure_library()`: runs `sync_library` once per process, from a `before_request` on
  the gym blueprint. With several workers, the loser of a duplicate-key race catches the
  IntegrityError and syncs again. A list that grows in code therefore needs no deploy step.
- `library_exercises()`: the rows the picker offers, i.e. every row whose key is in
  today's `LIBRARY`, by name.
- `touched_exercises(user_id)`: the lifter's own exercises — logged in one of their
  sessions, kept in one of their routines, or set up in their settings. The catalogue lists
  these, and Start's `catalogue_groups` reads them.
- `exercise_or_404(exercise_id)`: any row. No ownership: the row is global, and history
  is scoped where it is read.
- `Setup` (frozen dataclass): the four effective values plus the set of fields that differ
  from the list.
- `setups(user_id, exercises)` returns `{exercise_id: Setup}` in one query; `setup(user_id,
  exercise)` returns one.
- `save_setup(user_id, exercise, **values)`: stores only the differences, per the rules
  above.

The user always comes from the data being built, never from the request. Examples: the
session's `user_id` for a workout payload, and the follower's id when the leader's request
reconciles the follower's rows. Scope rule: an exercise id no longer implies a user, so
every read from an exercise into sets, sessions or routines filters by the reading lifter.
The inventory (2026-09-23) found every such query already joining `WorkoutSession.user_id`.
Only the two delete checks walked the relationships, and both go.

## What changes where (backend)

Personal values are resolved through `setups()`/`setup()` at every read site:
- `history.load_performed`: one `setups()` for the loaded rows, handed to `_to_performed`
  and `_session_rest_entries`. `PerformedExercise.weight_increment`/`stack_kg` therefore
  carry the lifter's values, and stats, analytics (`increment_ladder`, stall advice) and
  the catalogue inherit them.
- `seeding._seeded_sets` (deload branch) and `_seeded_suggestion`: user-scoped already, via
  their `user_id`.
- `workout.py`:
  - `_schedule_rest`, `gym_start`, `_live_data` (`step_up`, rest total, `live_increment`),
    `_session_payload.as_exercise` and `gym_add_session_exercise` all resolve through the
    session's user.
  - The add-sheet list becomes `library_exercises()`.
  - `catalogue_groups` becomes `touched_exercises()`.
- `session_admin.gym_toggle_deload`.
- `sharing.reconcile_follower` (rest): uses the follower's `Setup`.
- `export.exercise_payload`: resolves for the session's user. The format is unchanged.
- `catalogue._catalogue_payload`: lists `touched_exercises()`. `as_meta` sends the effective
  values plus the list's defaults (`list_defaults`) for the settings form.
- `exercise_detail._exercise_detail_payload`: likewise; `can_delete` goes.

Write paths:
- Removed: `POST /gym/exercises/add` (catalogue create) and `POST
  /gym/exercises/<id>/delete`. Also removed: creating by name in
  `gym_add_session_exercise` and `gym_replace_session_exercise`. Both now take an existing
  `exercise_id` only; a name-only post is a 400.
- `POST /gym/exercises/<id>/update` saves personal settings. It reads only the four fields
  and ignores name/group/equipment/unilateral/secondary if they are posted.
- `POST /gym/session-exercise/<id>/increment` saves the increment setting of the session's
  lifter.

Shared workouts, the minimum G1 needs; G3 retires the machinery:
- `sharing.follower_exercise_for` returns the leader's exercise id. It still records the
  identity map row, so `reconcile_follower` works unchanged, but it no longer creates or
  searches.
- `partners.gym_shared_confirm` hands `propose_matches` the whole list. Every leader
  exercise is then an exact match, so the one-tap confirm card from 4d6aa08 applies.
  `gym_shared_accept`'s `'new'` value resolves to the leader's id; an unknown id is a
  400. A retired row is still a valid id, since it can sit in a live workout.

Scripts:
- `copy_templates.py`: the same exercise ids; no forks.
- `delete_user.py`: deletes the user's settings rows, not exercises.
- `make_session_fixture.py`, `make_chart_fixture.py`: use `touched_exercises()`.

`scope.py` loses `my_exercises`/`owned_exercise`, and its docstring drops Exercise as an
ownership root. Docstrings that say exercises are per-user are corrected wherever the work
touches them.

## UI in G1 (interim; V1–V3 redesign after a mockup round)

Functional removals only, no new visual design:
- Add sheet (`AddExerciseSheet`):
  - No create row. The placeholder reads "Übung suchen".
  - It lists the whole list, searched as today (name substring). The `matches` port, alias
    search and variant grouping are V1.
- Live exercise sheet: "+ Neue Übung anlegen" / "Anlegen und ersetzen" go; replacing picks
  from the list.
- Catalogue: no create sheet, and the "anlegen" affordances go from empty bands and the
  empty state. The empty state points to the add sheet in a workout.
- Exercise detail:
  - No delete button.
  - `EditSheet` shows only step, rest, stack stops and bar, prefilled with the effective
    values. A blank field means "the list's value", which the field shows as its
    placeholder.
  - Name, group, equipment and one-side are shown as text, not inputs.
- Copy that says "anlegen" for exercises changes: SessionSheet row meta, Start
  onboarding line, and SharedConfirmPage's `new` option.

## Migration (G2) — one alembic revision after main's head `b7e3f9c1a2d4`

It runs on MySQL 8 (local) and MariaDB (prod). DDL commits implicitly on both, so the
revision is built to be re-runnable, not transactional:

1. Additive DDL, each step skipped if already present: create `gym_exercise_settings`; add
   `library_key` (nullable); make `user_id` nullable.
2. Data, in ONE transaction with no DDL inside it. Skipped entirely when no row has a
   `user_id`.
   1. Insert every `LIBRARY` entry that is missing (key, facts, defaults, `user_id` NULL),
      with an explicit column list defined in the migration.
   2. Map each per-user row:
      - its name in the migration's frozen copy of `PRODUCTION_2026_09`;
      - else, the one entry whose folded name or alias equals the folded name;
      - else, a retired row: one per distinct folded name, with the name, facts and values
        taken from the row with the most session rows.
   3. Settings: for each per-user row, every personal value that differs from its target's
      default becomes that user's setting on the target.
      - An old NULL is "no override". This also fixes u3's 1.25 step, since the list says
        2.5.
      - A `stack_kg` that is an even grid at the effective step is dropped as redundant
        (u1 Front Raises).
      - When one user has two rows on one target, the row with more session rows wins.
   4. Re-point `gym_session_exercises.exercise_id`, `gym_template_exercises.exercise_id`
      and both columns of `gym_shared_session_exercises`. Map rows that collide on
      `(shared_session_id, leader_exercise_id)` keep the lowest id.
   5. Delete the per-user rows.
   6. Check before commit: session/template/set counts unchanged; every reference points
      at a row with `user_id` NULL; no per-user row left. Otherwise raise, and the data
      step rolls back.
3. Dropping DDL, each step guarded by the inspector: the FK, index and unique constraint
   on `user_id`, then the columns `user_id` and `previous_name`, then a unique index on
   `library_key`.

`downgrade()` refuses with "restore from backup", following `c8e5f14a9b32`'s precedent: the
merged rows cannot be split back into the old per-user names. The rollback is a restore from
the nightly backup or from a dump taken right before `flask db upgrade`. `library_mapping.py`
is deleted. Its test moves to the migration's frozen copy, which is loaded by path, and
checks that every target key exists in `LIBRARY`.

Unmapped rows do not abort the migration. New exercises created in prod between the
2026-09-23 audit and the deploy must not turn the deploy into a broken app. They become
retired rows with their history intact, and the migration prints them.

## Testing

- DB-free: the sync diff, the `Setup` resolution and save rules, the migration's mapping
  resolution and even-grid check (pure functions), and the frozen mapping's keys.
- On a scratch copy of the dev DB (`personal_apps_g1`, never the shared dev DB):
  - Run the migration's `upgrade()` through alembic `Operations`, then assert the
    invariants and the carried settings: u1 machine_fly step 8, rest 150 where the list
    differs, u3 plate_preacher_curl step from the list, 'Probe Neu' retired. A second run is
    a no-op.
  - Then run the gym pytest suite against it. Tests that encoded per-user exercises are
    rewritten to the global semantics:
    - `test_gym_exercise_ownership.py`: A's settings and history are invisible to B on
      one id.
    - `test_gym_ownership.py` catalogue routes: detail pages are open, and history stays
      private.
    - Fixtures take list rows (by key) plus settings rows.
- Frontend: vitest, tsc and build. Then python-playwright at 390×844 on a server bound to
  the scratch DB: add sheet without create, detail settings save, catalogue.

## Out of scope

- V1: picker grouping of variants, most-used first, and alias search in the client.
- V2: first set without an invented plan.
- V3: redesign of the settings UI.
- G3: retiring `SharedSessionExercise`/`matching.py`, and the confirm page redesign.
- The ~800-entry list.
- The prod deploy itself: the owner deploys after an explicit merge OK.
