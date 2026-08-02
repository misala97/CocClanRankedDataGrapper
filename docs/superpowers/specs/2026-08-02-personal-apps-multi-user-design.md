# personal_apps: multi-user accounts, gym partitioned per user

**Date:** 2026-08-02
**Status:** Approved design, not yet implemented
**Scope:** `personal_apps/` only. No change to `coc_stats/`.

## Why

The Gym Tracker has a second user. A training partner has used the app alongside its
author for weeks and wants his own copy of it, in preference to the commercial gym app
they used before.

Nothing in personal_apps can express "belongs to someone". Authentication is a single
hardcoded credential pair read from the environment (`PERSONAL_ADMIN_USER` /
`PERSONAL_ADMIN_PASS`) that sets `session['logged_in'] = True`. There is no user table,
no password hashing, and no owner column on any of the eight gym tables. Ownership is
implicit and universal: every row belongs to the one person who can log in.

This spec adds real accounts and partitions gym data per user.

### What makes it tractable

`features/gym/stats.py` (878 lines) and `features/gym/analytics.py` (511 lines) import
nothing from the database — they are pure functions fed by their caller. The entire
data-access surface is `features/gym/routes.py`, `features/gym/push.py`, and
`run_gym_notifier.py`: roughly 25 model-query sites in total, spread across 35 routes.

(Coincidentally, 25 also happens to be the number of routes taking an id parameter — see
Query enforcement. The two counts are unrelated.)

The audit is one file plus two small ones, not 7,477 lines.

## Decisions

Each of these was chosen against alternatives; the rejected options are recorded so they
are not relitigated.

### 1. Only the gym app is partitioned

Everyone logs in with a real account. Gym data is per user. Pub Quiz, Quiz Bank, Tips and
Delivery Shifts remain the author's — they check `is_admin` and are absent from a
non-admin's navigation.

*Rejected:* partitioning every app. The other apps have no per-user meaning, and the
audit surface would grow several-fold for a case nobody has.

### 2. The exercise catalog is shared

`gym_exercises` gets no owner column. Both users pick from one global list; only an admin
renames, edits, or sets `weight_increment`. A non-admin may add a new exercise, which
becomes global.

Correct here because both users train at the same gym: the equipment is literally the
same, so `weight_increment` and `is_unilateral` are the same facts for both of them.
It also keeps the existing `Exercise.name` unique constraint, keeps `previous_name`
rename-tracking coherent, and means "Bankdrücken" denotes one thing in both accounts.

*Rejected:* per-user catalogs (duplicate rows, drop the unique constraint, and any future
comparison feature needs fuzzy name matching); shared catalog with a per-user override
table (an extra table and an override lookup at every increment/rest read, for a
difference that does not exist while they share a gym).

### 3. Accounts are created by the admin

No `/register` route. The admin creates accounts and hands over the password out of band;
the recipient can change it afterwards at `/account`.

*Rejected:* mirroring coc_stats' open registration with an `is_approved` gate (an
unapproved-account state and a public form to defend, for an app with two users); invite
codes (a shared secret with no expiry unless rotation is also built).

### 4. Users cannot see each other's training data

Every gym query filters to the logged-in user. No shared records board, no read-only view
of the other person's sessions.

Chosen partly on merit and partly because it is the only rule simple enough to verify
across 25 query sites. A comparison feature, if wanted later, is its own spec written
against a codebase that is already correctly partitioned.

### 5. Templates are owned, and copied once by hand

`gym_workout_templates.user_id` is NOT NULL, exactly like sessions. Every template belongs
to exactly one user. The partner's starting templates are inserted once, directly in the
database, after deployment (SQL in the Rollout section).

The two users run the same split, which initially argued for a shared-template concept —
a nullable `user_id` where NULL means "shared, admin-curated". That was rejected in favour
of the uniform rule: nullable-means-shared would put admin-vs-owner branching inside all
four template write routes (`save_as_template`, `update_template`, `rename`, `delete`),
and a single uniform ownership rule is both simpler to build and simpler to audit — and
auditing is the actual risk in this change.

The accepted cost is drift: when the author changes the split, the partner's copy stays
old until re-copied. Weak in practice, because they train together — the partner is
present for the change and updates his own template from the same session.

The shared catalog makes the copy trivial: `exercise_id` values stay valid across users,
so it is a plain row duplication with no ID remapping.

## Auth model

New table `app_user` in personal_apps, mirroring `coc_stats.AppUser` in shape:

| column | notes |
| --- | --- |
| `id` | pk, autoincrement |
| `username` | `String(80)`, unique, not null |
| `password_hash` | `String(256)`, not null, werkzeug `generate_password_hash` |
| `created_at` | datetime, default now |
| `is_admin` | boolean, not null, default false |

No `is_approved` (no self-registration). No per-app permission columns.

**The permission rule, in full: an admin sees every app; a non-admin sees Gym only.** A
per-app permission table is the thing to add if a third person ever needs a different
slice — not before.

### Login

`auth.py`'s environment-credential comparison is replaced by a username lookup plus
`check_password_hash`. The coc_stats timing defence is carried over: a module-level
`_DUMMY_PASSWORD_HASH` is checked when the username misses, so a wrong username and a
wrong password take the same time.

### Session

`session['user_id']` replaces `session['logged_in']`. `_is_logged_in()` becomes "the
session carries a `user_id` that still resolves to an `app_user` row", so deleting a user
invalidates their live sessions.

### The author's account

The migration seeds one admin row from `PERSONAL_ADMIN_USER` / `PERSONAL_ADMIN_PASS`,
hashed. The author logs in after deployment with exactly the credentials used before.

Environment-credential authentication is then deleted from `auth.py`. No second code path,
no break-glass backdoor outliving its usefulness. Recovery from a lost password is an
`UPDATE app_user SET password_hash = ...`; the author owns the database.

### Access gate

`app.py` already runs `_require_login_on_full_access_host` as a `before_request` on every
request. It gains a second check: a non-admin requesting a non-gym blueprint gets 403.

The `APPS` list rendered by `/` is filtered by the same rule, so a non-admin's landing page
shows one tile rather than four, three of which would bounce him.

## Data ownership

Owner columns go on aggregate roots only. Child tables inherit ownership through their
parent foreign key.

| table | owner |
| --- | --- |
| `gym_workout_sessions` | `user_id` NOT NULL |
| `gym_workout_templates` | `user_id` NOT NULL |
| `gym_push_subscriptions` | `user_id` NOT NULL |
| `gym_exercises` | none — shared catalog |
| `gym_template_exercises` | inherits via `template_id` |
| `gym_session_exercises` | inherits via `session_id` |
| `gym_session_sets` | inherits via `session_exercise_id` |
| `gym_pending_pushes` | inherits via `session_id` |

Stamping `user_id` on all eight tables was rejected: it allows a set row and its session
row to disagree about who owns them, and nothing in the schema would forbid it. One source
of truth per object graph. Sets are never loaded except through their session.

`gym_push_subscriptions` needs an owner because it is a root with no parent — and because
`push.py` currently sends to every subscription row, which after this change would buzz
the wrong person's phone.

### Migration chain

Split into steps so that step 3 has an id to point at, and so a failure between steps 2
and 4 leaves a readable database rather than a violated constraint.

1. Create `app_user`; seed the admin row from the environment.
2. Add `user_id` as **nullable** to `gym_workout_sessions`, `gym_workout_templates`,
   `gym_push_subscriptions`.
3. Backfill every existing row to the seeded admin id — all existing data is the author's.
4. Alter each to NOT NULL; add the foreign key and an index on each.

Reversibility is verified before the branch is considered done, as with every prior
migration in this app.

### Cross-user foreign keys

`WorkoutSession.template_id` could in principle point at another user's template. Prevented
by filtering templates per user at the route that starts a session.

## Query enforcement

**The rule: every gym query is scoped to `session['user_id']`. No route reads an object by
URL id without proving ownership first.**

25 of the 35 gym routes take an object id from the URL. Enforcing the rule by hand at each
site is how a leak arrives on route 26. A new module `features/gym/scope.py` holds the
loaders, and routes stop calling `.query.get()` on gym models:

```
current_user_id()
my_sessions()                 my_templates()            -> pre-filtered queries
owned_session(id)             owned_template(id)        -> 404 if not the caller's
owned_session_exercise(id)    owned_set(id)             -> join up to the session, then 404
```

**404, never 403.** A 403 confirms the object exists. Same reasoning as hashing against a
dummy on a missing username.

The 25 routes fall into three groups.

**Owned roots — 12 routes.** `session_id` (10), `template_id` (2). Direct swap to
`owned_session()` / `owned_template()`.

**Owned descendants — 9 routes.** `session_exercise_id` (6), `set_id` (3). The loader joins
up to the session and checks there. Done inside the loader rather than walked by hand in
each route, because a hand-walk is nine chances to forget.

**Shared catalog — 4 routes.** `exercise_id`. The object is deliberately shared, so there
is no ownership check to make on it, and that is precisely the trap:

- `/gym/exercises/<id>` and `/gym/exercises/<id>/progress.json` render **training
  history** around a shared object. The bug is not in loading the exercise; it is in the
  history query beside it. Both need explicit user scoping, or the partner opens
  Bankdrücken and reads the author's numbers.
- `/gym/exercises/<id>/update` and `/delete` are catalog curation: admin only.

### Push notifications

`push.py` must send to the owning user's subscriptions rather than all rows.
`run_gym_notifier.py` resolves `PendingPush -> session -> user -> that user's
subscriptions`. This path fails silently and out of hours, so it gets its own test.

## Admin UI and CSRF

Consistent with decision 5, rare operations go through SQL rather than UI.

Both routes live on the existing `auth_bp` in `auth.py` (79 lines today) rather than a new
blueprint — they are account management, which is what that file is for. `/admin/users`
carries its own admin check; it must not rely on the `before_request` blueprint rule, which
only distinguishes gym from non-gym.

- **`/admin/users`** — admin only. List users; create a user (username, password,
  `is_admin` checkbox). No edit, no delete: deleting a user is a rare event and is one SQL
  statement when it comes.
- **`/account`** — any logged-in user. Change own password. Worth one route: otherwise the
  partner's password is permanently the one he was sent, and the author knows it.
- Passwords: minimum 8 characters, checked server-side. No complexity rules.

### CSRF

personal_apps has no CSRF protection today. That was survivable when the only form action
was logging a bench press. It is not once a form can mint an admin account: a CSRF against
`/admin/users` is a full takeover.

**Decision: hand-rolled tokens on exactly three forms** — login, create-user,
change-password — mirroring the existing `_get_csrf_token` / `_valid_csrf` helpers in
`coc_stats/features/auth/routes.py`. Those three are the account-takeover paths.

App-wide `CSRFProtect` would require a hidden token in every existing form across 13 gym
templates plus the pubquiz, tips and quizbank templates, with real odds of silently
breaking a form that is only used monthly. It is recorded below as a follow-up rather than
bundled here.

## Testing

Added to the existing `tests/test_gym_stats.py`, `test_gym_analytics.py`,
`test_gym_routes_smoke.py`:

- **IDOR table test — the centrepiece.** A loop over the route table: for every route
  carrying an id param, user B requests user A's object and must receive 404. For the four
  shared-catalog routes, the response must contain none of user A's data. Written as a loop
  so that route 36 fails the moment it is added unscoped.
- **Auth:** hashing round-trip; a wrong username and a wrong password are indistinguishable;
  a session whose `user_id` no longer resolves logs out cleanly.
- **Permissions:** a non-admin receives 403 from `/tips`, `/quizbank`, the pubquiz admin
  routes and `/admin/users`; `/` renders one app tile for a non-admin and four for an admin.
- **Push isolation:** a pending push for user A's session resolves only to user A's
  subscriptions.
- **Migration reversibility**, as with every prior migration here.

## Rollout

On `dev_personal`, merged to `main` to deploy.

1. Migration and code, verified against the local dev database (disposable data; normal
   care applies).
2. **Back up the production database before migrating.** This is the first migration in
   this app that rewrites ownership of every row.
3. Merge to `main`, deploy, run `flask db upgrade` on the VPS, restart the web service
   **and** the notifier daemon — `push.py` changes, and a stale daemon keeps the old
   broadcast behaviour.
4. Create the partner's account at `/admin/users`.
5. Run the one-time template copy (below).
6. Verify as the partner: his own login works; the author's templates are present; history
   is empty; exercise detail pages show none of the author's numbers.

### One-time template copy

Run once, after step 4, from a Flask shell on the VPS. `SRC` is the author's user id, `DST`
the partner's. `exercise_id` needs no remapping because the catalog is shared.

```python
for t in WorkoutTemplate.query.filter_by(user_id=SRC).all():
    copy = WorkoutTemplate(name=t.name, user_id=DST)
    db.session.add(copy)
    db.session.flush()          # need copy.id before the children
    for te in t.exercises:
        db.session.add(TemplateExercise(
            template_id=copy.id,
            exercise_id=te.exercise_id,
            position=te.position,
            rest_seconds=te.rest_seconds,
        ))
db.session.commit()
```

Deliberately the ORM rather than two `INSERT ... SELECT` statements. Pairing source to
destination templates in pure SQL means joining on `name`, and
`WorkoutTemplate.name` is not unique — two templates called "Push" would cross-join and
silently give the partner duplicated exercise rows. Carrying each new id in a variable
avoids the question entirely.

### Expected side effect

The session cookie changes shape from `logged_in: True` to `user_id: N`, so every existing
session is invalidated on deploy. Both users log in once more. Expected, not a bug.

## Out of scope

- **App-wide CSRF protection.** Named above; its own piece of work.
- **Any cross-user visibility** — shared records, comparisons, leaderboards. Decision 4.
- **Per-user exercise settings** (rest seconds, increments). Decision 2; revisit only if
  the two stop sharing a gym.
- **A template-copy UI.** Decision 5; the SQL runs once.
- **Partitioning the other four apps.** Decision 1.
- **Password reset by email.** No mail infrastructure in personal_apps; the admin resets a
  password, and the user changes it at `/account`.
