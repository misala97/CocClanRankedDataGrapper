# Gym global exercise list (G1 + G2) Implementation Plan

> Inline execution (owner rule: no subagent-driven). Spec (binding):
> `docs/superpowers/specs/2026-09-23-gym-global-exercise-list.md`. Ledger: the G rows and
> Ledger section of `docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md`.
> Steps use checkboxes.

**Goal:** `library.py` becomes the one read-only exercise list; the four personal values live
in `gym_exercise_settings`; the production rows migrate onto list rows.

**Architecture:** Global `gym_exercises` rows synced from `library.py` (once per process,
before the first gym request). `features/gym/exercises.py` owns rows and each lifter's
`Setup`. Every read of a personal value resolves through `setups()` with the user taken from
the data (the session's or routine's owner). One alembic revision, re-runnable, does the
schema and the data (G2).

**Tech stack:** Flask + SQLAlchemy 2 + Flask-Migrate/alembic, MySQL 8 locally and MariaDB in
prod. React/TS islands (vite, vitest). pytest.

## Global constraints

- Branch `dev_personal`, in the main checkout. Commit only the files the task touched. No
  push or merge to main without the owner's explicit OK.
- Every DB-backed test and run uses the scratch DB `personal_apps_g1`, never the shared dev
  DB. Recreate it with `python <scratch>/make_scratch_db.py`; tests run via
  `python <scratch>/run_g1_tests.py [args]`.
  - `<scratch>` = `C:\Users\michi\AppData\Local\Temp\claude\C--Users-michi-Desktop-CodingStuff\acbf7aa7-35c4-4fcf-8a0f-df0174b324ef\scratchpad`
  - Both scripts import `g1env.py`, which reads `.env`, swaps `PERSONAL_DB_NAME` and makes
    `load_dotenv` a no-op.
- No migration test in `tests/`: a suite test would run the migration against whatever DB
  the suite binds. The migration runs through `<scratch>/run_g1_migration.py` (alembic
  `Operations` on the scratch DB). The tests in `tests/` cover only its pure helpers,
  loaded by path.
- The migration's `down_revision` is main's head `b7e3f9c1a2d4`. dev_personal lacks main's
  radar migrations, so `flask db` cannot resolve the graph on dev_personal alone. The
  resolved merge sits on branch `dev_personal-main-sync` (1097afc). T5 checks the graph
  there.
- Copy: German, "Routine" not "Vorlage". No "anlegen" for exercises anywhere.
- Owner rulings 1–7 (first-run plan) bind. Nothing lets a lifter create, rename or delete
  an exercise.

## File map

- Create `personal_apps/features/gym/exercises.py`: sync, queries, `Setup`, save rules.
- Create `personal_apps/migrations/versions/e2c7a9f41b86_gym_global_exercise_list.py`: schema
  and data (G2).
- Create `personal_apps/tests/test_gym_exercises.py`: DB-free core, plus DB tests of sync,
  setups and save.
- Create `personal_apps/tests/test_gym_global_migration_helpers.py`: the migration's pure
  helpers and the frozen mapping, loaded by path.
- Delete `personal_apps/features/gym/library_mapping.py`. Its test in `test_gym_library.py`
  moves to the file above.
- Modify:
  - `models.py` (Exercise, ExerciseSettings), `scope.py`, `history.py`, `seeding.py`
  - `routes/workout.py`, `routes/session_admin.py`, `routes/catalogue.py`,
    `routes/exercise_detail.py`, `routes/partners.py`, `routes/__init__.py`
    (before_request)
  - `sharing.py`, `export.py`, `schemas.py`
  - `scripts/copy_templates.py`, `scripts/delete_user.py`, `scripts/make_session_fixture.py`,
    `scripts/make_chart_fixture.py`
  - the tests listed in T3
- Frontend (T4): `session/components/AddExerciseSheet.tsx`, `ExerciseSheet.tsx`,
  `SessionSheet.tsx`, `session/api.ts`, `SessionIsland.tsx`, `SessionPage.tsx`,
  `catalogue/CataloguePage.tsx` (drop `NewExerciseSheet.tsx`), `components/EditSheet.tsx`,
  `pages/ExerciseDetail.tsx`, `start/StartPage.tsx`, `shared/SharedConfirmPage.tsx`,
  `types.ts`, `session/types.ts`, `catalogue/types.ts`, plus their tests and fixtures.

## Interfaces (fixed here; later tasks use exactly these)

`features/gym/exercises.py`:
```python
PERSONAL_FIELDS = ('weight_increment', 'default_rest_seconds', 'stack_kg', 'bar_weight')
LIST_ATTR = {'weight_increment': 'list_increment', 'default_rest_seconds': 'list_rest_seconds',
             'stack_kg': 'list_stack_kg', 'bar_weight': 'list_bar_weight'}

def entry_values(entry) -> dict            # DB column -> value for one library.Entry
def sync_plan(existing: dict, library=LIBRARY) -> tuple[list[dict], list[tuple[str, dict]]]
                                            # existing: {key: {column: value}}; (inserts, updates)
@dataclass(frozen=True)
class Setup:
    weight_increment: float | None
    default_rest_seconds: int | None
    stack_kg: list | None
    bar_weight: float | None
    changed: frozenset = frozenset()        # fields where the lifter's own value is in use
def resolve(list_values: dict, stored: dict | None) -> Setup
def to_store(list_values: dict, submitted: dict, equipment: str) -> dict  # field -> value|None
def list_values(exercise) -> dict           # {field: exercise.<LIST_ATTR[field]>}
# DB layer (T3)
def sync_library(connection) -> tuple[int, int]      # (inserted, updated)
def ensure_library() -> None
def library_exercises() -> list          # rows whose key is in LIBRARY, by name
def touched_exercises(user_id) -> list   # logged / in a routine / set up, by name
def exercise_or_404(exercise_id)
def setups(user_id, exercises) -> dict[int, Setup]
def setup(user_id, exercise) -> Setup
def save_setup(user_id, exercise, submitted: dict) -> Setup   # submitted: parsed values
```

Models:
- `Exercise`: `library_key`, `name`, `muscle_group`, `secondary_muscle_groups`, `equipment`,
  `is_unilateral`.
  - Plus `list_increment`/`list_rest_seconds`/`list_stack_kg`/`list_bar_weight`, mapped to
    the old column names.
  - No `user_id`, no `previous_name`, no `session_exercises`/`template_exercises`.
- `ExerciseSettings`: `user_id`, `exercise_id`, `weight_increment`, `default_rest_seconds`,
  `stack_kg`, `bar_weight`.

Migration helpers (module-level in the revision file, pure):
- `resolve_key(name, index)`
- `alias_index(library)`
- `is_even_grid(stops, step)`
- `carried(row, target)` returns `{field: value}` to store
- `winner(rows)`: the row with the most session rows, then the lowest id.

## Tasks

### T1: exercises.py pure core
- [x] Write `tests/test_gym_exercises.py` DB-free cases:
  - `entry_values` of `barbell_bench_press` gives a bar of 20 and rest 180; `stack_kg` is
    None and `secondary_muscle_groups` is a list.
  - `sync_plan({})` inserts all 158 entries. `sync_plan` over its own inserts is empty.
  - A changed name or a changed rest yields exactly one update with only the changed
    columns. A key missing from the library is left alone.
  - `resolve`:
    - with None stored, every value is the list's and `changed` is empty;
    - a stored increment 8 over a list 5 gives 8 and `changed={'weight_increment'}`;
    - a stored bar 0 over a list 20 gives 0.
  - `to_store`:
    - the list value gives None;
    - blank (None) gives None;
    - an increment 8 over a list 5 gives 8;
    - a bar 0 over a list None gives None, and a bar 0 over a list 20 gives 0;
    - `stack_kg` on a non-stack gives None;
    - a stack list gives a sorted list;
    - a rest equal to the list gives None.
- [x] Run: `python <scratch>/run_g1_tests.py tests/test_gym_exercises.py -q -p no:cacheprovider`
  and expect an ImportError.
- [x] Implement the pure part of `exercises.py`, with the module docstring from the spec.
- [x] Re-run and expect everything to pass. Then run `test_gym_library.py` and expect 15
  passed.
- [x] Commit: `feat(gym): the exercise list's core -- sync plan, a lifter's setup, what gets
  stored`.

### T2: the migration (G2) and its harness
- [x] Write `tests/test_gym_global_migration_helpers.py`: load the revision file by path
  (importlib).
  - Every value of the frozen `PRODUCTION_2026_09` is a `LIBRARY` key, and it holds 21
    names.
  - `resolve_key`: the mapping wins; an exact folded name or alias gives its key; 'Probe
    Neu' gives None; an alias shared by two entries gives None.
  - `is_even_grid([5,10,...,50], 5)` is True; `([5,12,19], 5)` is False; `([], 5)` is False.
  - `carried`:
    - an old NULL increment gives no key;
    - 8 vs a list 5 gives 8;
    - rest 150 vs a list 90 gives 150, and 150 vs 150 gives no key;
    - an even-grid stack gives no key;
    - a stack on a non-stack target gives no key;
    - a bar of 0 or None vs a list None gives no key.
  - `winner` picks the most session rows, then the lowest id.
- [x] Run it and expect a failure (no file).
- [x] Write the revision. `revision='e2c7a9f41b86'`, `down_revision='b7e3f9c1a2d4'`. The
  three phases follow the spec's Migration section:
  - additive DDL, each step guarded;
  - DML in one transaction, skipped when no row has a `user_id`, ending in the invariant
    checks;
  - guarded drops.
  - It prints its mapping summary. `downgrade()` raises RuntimeError("... restore from
    backup").
- [x] Remove `library_mapping.py`. Move its test out of `test_gym_library.py` into the
  helpers test.
- [x] Write `<scratch>/run_g1_migration.py`. It runs `upgrade()` through
  `MigrationContext.configure(conn)` and `Operations.context(ctx)` on the scratch DB, then
  sets `alembic_version` to `e2c7a9f41b86`. Assertions on the dev copy:
  - 0 rows with a `user_id`; every session and template exercise points at a global row;
  - session_exercises, template_exercises and sets counts unchanged;
  - u1 `machine_fly` setting increment 8; u1 `machine_row` increment 8; u3
    `plate_preacher_curl` with no increment setting (list 2.5);
  - rest settings of 150 wherever the list is not 150;
  - the 'Probe Neu' rows land on one retired row (key NULL) carrying 2 session rows;
  - a second `upgrade()` changes nothing (same counts, no error).
- [x] Run the helpers test and expect it to pass. Recreate the scratch DB, run the
  migration harness, and expect all assertions OK.
- [x] Commit: `feat(gym): G2 -- the migration that puts every lifter's history on the one
  list`.

### T3: backend on the global list
- [x] `models.py`: Exercise and ExerciseSettings per the Interfaces section. Drop the
  relationships and `back_populates` on both sides, and fix the per-user comments.
- [x] `exercises.py` DB layer. `routes/__init__.py`: `gym_bp.before_request` calls
  `ensure_library`.
- [x] Add DB tests to `test_gym_exercises.py`:
  - `sync_library` is idempotent: the second run gives (0, 0);
  - `setups` for two users on one exercise give different increments;
  - `save_setup` stores only differences and deletes an all-NULL row;
  - `touched_exercises` holds a logged exercise and not an untouched list row;
  - `library_exercises` holds 158 rows and no retired row.
- [x] Read sites (spec "What changes where"):
  - `history.load_performed` / `_to_performed` / `_session_rest_entries`;
  - `seeding._seeded_sets` / `_seeded_suggestion`;
  - `workout.py`: `_schedule_rest`, `gym_start`, `_live_data`, `_session_payload`,
    `gym_add_session_exercise`, the add-sheet list, `catalogue_groups`;
  - `session_admin.gym_toggle_deload`;
  - `sharing.reconcile_follower`;
  - `export.exercise_payload`;
  - `catalogue._catalogue_payload`;
  - `exercise_detail._exercise_detail_payload`.
  - Each takes the user from the session or routine being built.
- [x] Write sites:
  - remove `gym_add_exercise` and `gym_delete_exercise`;
  - `gym_update_exercise` becomes `save_setup`;
  - `gym_update_exercise_increment` becomes `save_setup`;
  - `gym_add_session_exercise`/`gym_replace_session_exercise` take ids only, and a
    name-only post is a 400;
  - `partners.gym_shared_confirm`/`gym_shared_accept` and `sharing.follower_exercise_for`
    use the identity.
- [x] `scope.py`, the scripts, and `schemas.py`, which gains `list_defaults` on
  ExerciseMeta. The payload fields the UI reads stay until T4.
- [x] Rewrite the tests to the global semantics.
  - Fixtures build key-less rows (`Exercise(name=..., list_increment=...)`, no user) or use
    list rows. Per-user values come as `ExerciseSettings` rows.
  - Files: conftest, test_gym_sharing, test_gym_routes_smoke, test_gym_exercise_ownership
    (rewritten), test_gym_cold_start, test_gym_reorder_reseed, test_gym_rest, test_scripts,
    test_gym_equipment, test_gym_ownership, test_gym_exercise_detail_json,
    test_gym_schemas, test_gym_mutation_json, test_gym_audit_fixes, test_gym_export,
    test_gym_seeding, test_gym_session_fields, test_gym_session_json.
- [x] `grep -rn "weight_increment\|default_rest_seconds\|bar_weight\|stack_kg" features/gym`
  must show only `exercises.py`, the settings model, the PerformedExercise fields, `stats`
  and the payload/schema names. `grep -rn "user_id" models.py` shows no Exercise hit.
  `grep -rn "my_exercises\|owned_exercise\|previous_name\|session_exercises\b" features
  scripts` is empty.
- [x] Run the gym suite on the migrated scratch DB and expect all to pass. Its size will
  differ from 688 by exactly the removed and added tests; write the count in the ledger.
- [x] Commit: `feat(gym): G1 -- one exercise list for every lifter, and settings that are
  theirs`.

### T4: UI without create paths
- [x] Update the vitest tests first:
  - sheets.test: no "Anlegen:" row, and the placeholder is "Übung suchen";
  - ExerciseSheet.test: no "+ Neue Übung anlegen";
  - CataloguePage.test: no create sheet;
  - ExerciseDetail.test: no delete button, and EditSheet has 4 fields;
  - SharedConfirmPage.test: no `new` option.
- [x] Components per the spec's "UI in G1" section. Payload fields removed on both sides:
  `can_delete`, `added_id`, `name_taken`. `list_defaults` is typed and used as
  placeholders.
- [x] Run `npx vitest run`, `npx tsc --noEmit` and `npm run build` (in `personal_apps`),
  and expect all green.
- [x] Commit: `feat(gym): no more "anlegen" -- the add sheet, catalogue and detail page pick
  from the list`.

### T5: verification and handoff
- [x] python-playwright at 390×844 against a server on the scratch DB
  (`<scratch>/serve_g1.py`, port 5002) as u1 and as user 4:
  - the add sheet lists the list and has no create row;
  - adding "Bankdrücken (Langhantel)" gets rest 180 for user 4 and the setting for u1;
  - the detail page saves step 8, then blank restores the list value;
  - the catalogue shows touched exercises only.
  - Screenshots are read back.
- [x] Graph check: a temp worktree from `dev_personal-main-sync` merged with dev_personal.
  `flask db heads` gives a single head, `e2c7a9f41b86`. `flask db upgrade` on a fresh
  scratch copy passes. Then remove the worktree.
- [x] Ledger entries (first-run plan), HANDOFF rewrite, and a memory update. Commit the docs.
