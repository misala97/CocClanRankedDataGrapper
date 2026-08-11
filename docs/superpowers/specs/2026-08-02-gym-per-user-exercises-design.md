# Gym: per-user exercise catalogues

**Date:** 2026-08-02
**Status:** Approved design, not yet implemented
**Scope:** `personal_apps/` gym feature only.
**Supersedes:** decision 2 of `2026-08-02-personal-apps-multi-user-design.md`, and the increment amendment made to it the same day.

## Why

A third person is joining: jglaser's girlfriend. She trains at the same gym as
mgemmel and jglaser, but uses **none** of the same exercises.

The shared catalogue shipped this morning was justified by two people at one gym
sharing equipment: `weight_increment` and `is_unilateral` are objective facts
about a machine, so one row per exercise was correct and a per-user catalogue
would have duplicated rows for no gain.

The premise holds and the conclusion no longer follows. The facts are still
shared — same gym — but the *lists* are not. One global list means she opens the
exercise picker to thirty lifts she will never do, and everything she adds
lands in theirs. The author's decision: exercises become per-user, and a new
account starts empty.

The cost is accepted explicitly: mgemmel and jglaser stop sharing equipment
facts. After the migration he holds his own copy of Bankdrücken; correcting an
increment on one does not correct the other, and nothing reports that two rows
describing the same machine disagree. This mirrors the template-drift trade
already accepted in decision 5 of the superseded spec.

## Decisions

### 1. `gym_exercises` becomes an owned root

`user_id` NOT NULL, foreign key to `app_user`, matching the other three roots.
That makes four owned roots and one rule with no exceptions: **every gym row
belongs to exactly one user.** The four child tables continue to inherit
ownership through their parent foreign key.

The global unique constraint on `name` (named `name` in MySQL) is replaced by a
unique constraint on `(user_id, name)`. Two users may each hold a "Rudern"
meaning whatever it means to them.

### 2. Editing an exercise is ownership, not admin

`@admin_required` comes off `/gym/exercises/<id>/update` and `/delete`, replaced
by `owned_exercise()`. The gate existed only because the catalogue was shared
and needed a curator; an exercise that belongs to one person needs no curation
by another. jglaser and the third user rename and delete their own lifts without
involving the admin.

This also dissolves the increment seam recorded in the superseded spec. The
question "who may set `weight_increment` on a shared row" stops existing — it is
your row.

*Rejected:* keeping the admin gate. It would mean a non-admin cannot correct a
typo in an exercise only they can see.

### 3. One shared row with per-user visibility was rejected

The alternative considered: keep one row per exercise and add a link table
naming whose list it appears on. Cheaper (no duplication, no repointing, no
constraint change) and it preserves shared equipment facts, which are genuinely
correct at one gym.

Rejected because it does not give real isolation: names stay global, so a third
user cannot name an exercise as she pleases, and any edit still reaches everyone
listing that row. The author chose isolation over shared facts knowing the
drift cost.

### 4. jglaser's account is deleted before the migration, not migrated through it

He has never used the app — two copied templates, no sessions, no push
subscriptions. Deleting him first means the migration runs against a
**single-user** database, which removes its most dangerous phase: duplicating
exercises and repointing live foreign keys inside an irreversible operation.

That forking logic does not disappear; it moves into `copy_templates.py`, which
has a dry run, is testable against the development database, and where a mistake
is a `git checkout` rather than a half-applied migration.

*Rejected:* implementing the fork in the migration. It would be correct but
untestable in place, for a case that exists only because of an account created
hours earlier with nothing in it.

## Schema

| column | change |
| --- | --- |
| `gym_exercises.user_id` | new, Integer, NOT NULL, FK `app_user.id`, indexed |
| `gym_exercises.name` | unique constraint `name` dropped |
| `(user_id, name)` | new unique constraint |

No other table changes. `gym_template_exercises.exercise_id` and
`gym_session_exercises.exercise_id` keep their foreign keys and continue to
inherit ownership through their parent.

### Migration

Four phases:

1. Add `user_id` nullable.
2. Backfill every row to the admin account with the lowest id — the same owner
   the `b7d93a5c1e40` migration used for the other three roots, so ownership
   stays consistent across all four. With jglaser deleted this is the only
   account, but the migration selects explicitly rather than assuming.
3. Drop the `name` unique constraint.
4. `NOT NULL`, foreign key, index, and the `(user_id, name)` unique constraint.

Steps 3 and 4 are a constraint swap and could be one phase; they are written
separately only because the drop is the irreversible half. Nothing inserts a
duplicate name *during* the migration — the database is single-user throughout.
The drop matters for what comes after: `copy_templates.py` will insert a second
row named "Bankdrücken" for jglaser, and the old constraint would reject it.

**Precondition guard.** Before touching anything, the migration asserts that no
`gym_template_exercises` or `gym_session_exercises` row references an exercise
whose owner differs from the referencing row's owner, and raises if it finds
one. Since the intended state is a single-user database this should be
trivially true; if jglaser was not deleted, or a fourth account appeared, it
stops with a clear message rather than leaving one user's templates pointing at
another's lifts.

**The downgrade is lossy and says so.** Reversing this means merging duplicate
rows and choosing whose `weight_increment` survives, which has no correct
answer. The downgrade drops the column and restores the global unique
constraint, but **raises and refuses** when two users hold same-named exercises,
because the restore cannot succeed in that state. Backup is the recovery path.

## Query enforcement

`features/gym/scope.py` gains two loaders, matching the existing idiom:

```
my_exercises()       -> Exercise query filtered to the caller
owned_exercise(id)   -> the row, or abort(404)
```

Fifteen call sites in `features/gym/routes.py`, in four groups.

**Pickers (2).** `gym_uebungen` and the session sheet's exercise list use
`my_exercises()`. This is what makes a new account's list empty.

**Own-exercise pages (4).** Detail, `progress.json`, update, delete use
`owned_exercise()`. Update and delete lose `@admin_required`.

**Name lookups (3).** `gym_add_exercise`, plus the add-by-name and replace paths
inside a session, currently ask whether an exercise with a given name exists
*globally*. Each becomes scoped to the caller. Unscoped, a new user typing
"Bankdrücken" silently matches another user's row and links to it — acquiring
their increment and contributing sets to their history. This is the specific
failure the change exists to prevent.

**Form-supplied ids (2).** `gym_add_session_exercise` and
`gym_replace_session_exercise` both read `exercise_id` from a submitted form and
use it unchecked. Harmless with one shared catalogue; an IDOR once exercises are
owned. Both go through `owned_exercise()`.

The remaining sites are internal — `_seeded_sets` resolving an increment from an
id its caller already validated — and are left as they are.

### Test-table changes

`tests/test_gym_ownership.py`'s route tables change meaning, which the
`url_map`-derived completeness check keeps honest while they are rewritten:

- `/gym/exercises/<id>` and `/gym/exercises/<id>/progress.json` move from the
  shared-catalogue group (asserting **200** with none of the owner's numbers) to
  the owned group (asserting **404**).
- `/gym/exercises/<id>/update` and `/delete` move from asserting **403** to
  asserting **404**.

## Scripts

Both live in `personal_apps/scripts/`, follow the existing `copy_templates.py`
shape: positional usernames, dry run by default, `--commit` to act.

### `delete_user.py` (new)

Removes an account: templates (their exercise rows cascade), push subscriptions,
then the user row, in that order.

**Refuses if the user has any logged session.** The guard is the point — it
separates removing an empty placeholder account from silently destroying a
training history because a username was mistyped. Deleting a user who has
trained is a deliberate act and can be a deliberate SQL statement.

### `copy_templates.py` (modified)

Currently copies template rows that point at the source user's exercise ids.
Those ids are no longer valid for the destination, so for each referenced
exercise the script does a **find-or-create in the destination's own catalogue**,
keyed on name and scoped to that user, then points the new template rows at the
destination's copy.

Find-*or-create*, not create: the source's templates overlap, and a plain create
would give the destination duplicate exercises for every lift appearing in more
than one template.

Copies carry `name`, `previous_name`, `muscle_group`, `default_rest_seconds`,
`weight_increment` and `is_unilateral` — the last two are what make a suggestion
correct.

## Testing

- The migration's precondition guard raises when a cross-owner reference exists
  — verified by creating one, not by reading the code.
- The downgrade refuses when two users hold same-named exercises.
- Two users can each hold an exercise with the same name (the constraint swap),
  tested directly.
- A newly created account's catalogue is empty.
- Every moved route asserts its new expectation; the `url_map` completeness
  check still passes.
- The two form-supplied-id routes 404 on another user's exercise, and the
  rejected request writes nothing.
- Scoped name lookups: a user creating an exercise whose name already exists for
  someone else gets their own row, not a link to the existing one.
- `delete_user` refuses a user with a session; removes templates and
  subscriptions when permitted.
- `copy_templates` creates exactly one exercise copy per distinct exercise across
  templates that share one, and preserves `weight_increment` and
  `is_unilateral`.

## Rollout

1. `delete_user.py jglaser` — dry run, then `--commit`.
2. **Back up the production database.**
3. Merge, deploy, migrate.
4. Recreate jglaser at `/admin/users`.
5. `copy_templates.py mgemmel jglaser --commit` — now forks his exercises too.
6. Create the third account. Nothing further: an empty catalogue is the default.
7. Verify per user — she sees an empty exercise list; jglaser sees his own copies
   of mgemmel's lifts with increments intact; neither can open the other's
   exercise detail page.

Confirm `PERSONAL_ADMIN_USER` / `PERSONAL_ADMIN_PASS` are still set before
migrating, as with the previous rollout: the earlier `a4c81f2e5b76` migration
reads them and a failed upgrade leaves the web service restarting onto a schema
it cannot authenticate against.

## Out of scope

- **Sharing equipment facts between users.** Explicitly traded away in decision
  1. If increment drift becomes annoying, the fix is a per-exercise "same
  machine as" link or a per-user override table — its own spec.
- **Merging duplicate exercises.** No UI, no script. Two rows for one machine is
  the accepted state.
- **Seeding a new account from a starter catalogue.** Empty by design; she adds
  what she uses.
- **A delete-user UI.** The script is deliberate friction.
- Everything already listed out of scope in the superseded spec, including
  app-wide CSRF.
