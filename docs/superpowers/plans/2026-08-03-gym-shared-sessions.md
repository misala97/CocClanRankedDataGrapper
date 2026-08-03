# Shared Live Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one lifter invite a training partner into a live workout so structural changes propagate to the partner's own session, while weights and reps stay private to each person.

**Architecture:** Each person owns an ordinary `WorkoutSession`. A `SharedSession` row links two of them and a `SharedSessionExercise` table translates between the two per-user exercise catalogues. Propagation is a **reconciliation**, not a per-operation replay: after any structural mutation the leader's route calls one idempotent function that makes the follower's exercise rows mirror the leader's, translated through the map. Because propagation is a write, the follower only ever reads their own rows — a poll against their own session is all their page needs.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy + Flask-SQLAlchemy, Flask-Migrate/Alembic, MySQL (pymysql), pywebpush, pytest.

**Spec:** `docs/superpowers/specs/2026-08-03-gym-shared-sessions-design.md`

## Global Constraints

- Branch: `dev_personal`. Do not commit to `main`.
- All paths relative to `personal_apps/`. Run pytest and `flask db upgrade` from there.
- Tests run against the **real local development database** — disposable dev data. Every fixture that creates rows deletes them afterwards, in FK-safe order: null `resting_set_id` and commit, delete sessions, delete templates, delete exercises, delete `AppUser` last.
- Tests must **not** use the shared `client` fixture for anything involving a live session. The seeded admin has a genuine in-progress workout in the dev database. Create a fresh `AppUser` per test and log in with your own `flask_app.test_client()`, following `tests/test_gym_ownership.py`'s `two_users` / `intruder_client` idiom.
- User-facing copy is **German**; code, comments and commit messages English.
- **Ownership rule: every failure is 404, never 403.** A 403 confirms the object exists. `features/gym/scope.py` is the only place read ownership is decided; do not inline ownership checks in routes.
- **Structure is leader-only.** The follower never mutates their own session's exercise list while a link is active.
- **Set count, weight, reps, `rest_seconds`, `is_deload`, `deload_pct` and session name never propagate.** Only: which exercises exist, their order, their `skipped` flag, and substitute relationships.
- **Reconciliation must not seed sets.** It runs inside the *leader's* request, where `current_user_id()` is the leader, so any history lookup would read the wrong person's history. Seeding happens only at accept time, which runs in the follower's request. See Task 3.
- Migration revision id `e4a91c7d20f8`, `down_revision = 'd1f6b83c25e9'`. Confirm with `flask db heads` first; if the head differs, stop and report.
- `tests/conftest.py` provides `_admin_id()`, `client`, `anon_client`, `acting_as`. Leave it unchanged.

---

## File Structure

**Created:**
- `features/gym/matching.py` — pure name-matching for the confirm screen. No ORM, like `stats.py`.
- `features/gym/sharing.py` — the link's lifecycle and the single cross-user write chokepoint.
- `templates/gym/shared_confirm.html` — the follower's confirm screen.
- `templates/gym/_session_queue.html` — the queue, extracted so it can be re-rendered alone.
- `migrations/versions/e4a91c7d20f8_add_shared_sessions.py`
- `tests/test_gym_matching.py`, `tests/test_gym_sharing.py`

**Modified:**
- `models.py` — `SharedSession`, `SharedSessionExercise`, `SessionExercise.mirrors_id`, `WorkoutSession.structure_version`.
- `features/gym/routes.py` — invite/accept/decline/sync routes; `propagate_structure()` calls in five structural routes; end the link on finish.
- `templates/gym/heute.html` — the pending-invite card.
- `templates/gym/session_detail.html` — the invite control and partner status.
- `templates/gym/_session_live.html` — replaced queue block with an include.
- `static/gym/gym.css` — invite card, confirm screen, partner status.

---

### Task 1: The tables

**Files:**
- Modify: `models.py`
- Create: `migrations/versions/e4a91c7d20f8_add_shared_sessions.py`
- Test: `tests/test_gym_sharing.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SharedSession` with `id`, `leader_session_id`, `follower_session_id`, `leader_user_id`, `follower_user_id`, `created_at`, `accepted_at`, `ended_at`, and relationship `exercise_map`.
  - `SharedSessionExercise` with `id`, `shared_session_id`, `leader_exercise_id`, `follower_exercise_id`.
  - `SessionExercise.mirrors_id: int | None` — the leader row this row mirrors.
  - `WorkoutSession.structure_version: int` — bumped whenever reconciliation changes this session's structure.

- [ ] **Step 1: Confirm the migration head**

Run: `flask db heads`
Expected: `d1f6b83c25e9 (head)`. If it differs, stop and report — do not guess a `down_revision`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_gym_sharing.py`:

```python
"""Shared live sessions: the link, the exercise map, and the one function
that writes into another user's session."""
import datetime as dt

import pytest

from app import app as flask_app


def test_a_shared_session_links_two_sessions_and_starts_pending():
    from extensions import db
    from models import AppUser, SharedSession, WorkoutSession
    from werkzeug.security import generate_password_hash

    made = {}
    try:
        with flask_app.app_context():
            leader = AppUser(username='pytest link leader',
                             password_hash=generate_password_hash('a'), is_admin=False)
            follower = AppUser(username='pytest link follower',
                               password_hash=generate_password_hash('b'), is_admin=False)
            db.session.add_all([leader, follower])
            db.session.flush()
            made['leader_user'], made['follower_user'] = leader.id, follower.id

            leader_session = WorkoutSession(name='pytest link session',
                                            started_at=dt.datetime.utcnow(),
                                            user_id=leader.id)
            db.session.add(leader_session)
            db.session.flush()
            made['leader_session'] = leader_session.id

            shared = SharedSession(leader_session_id=leader_session.id,
                                   leader_user_id=leader.id,
                                   follower_user_id=follower.id)
            db.session.add(shared)
            db.session.commit()
            made['shared'] = shared.id

            fresh = db.session.get(SharedSession, shared.id)
            assert fresh.accepted_at is None, 'a new invite must start pending'
            assert fresh.ended_at is None
            assert fresh.follower_session_id is None, (
                'no follower session exists until the invite is accepted')
            assert fresh.created_at is not None
            assert list(fresh.exercise_map) == []
    finally:
        with flask_app.app_context():
            if made.get('shared'):
                doomed = db.session.get(SharedSession, made['shared'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if made.get('leader_session'):
                doomed = db.session.get(WorkoutSession, made['leader_session'])
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            for key in ('leader_user', 'follower_user'):
                if made.get(key):
                    doomed = db.session.get(AppUser, made[key])
                    if doomed is not None:
                        db.session.delete(doomed)
            db.session.commit()


def test_a_session_exercise_can_mirror_another_users_row():
    """mirrors_id is how reconciliation knows which follower row corresponds to
    which leader row -- exercise_id cannot serve, because the two catalogues
    have different ids for the same lift."""
    from extensions import db
    from models import SessionExercise, WorkoutSession
    from conftest import _admin_id

    with flask_app.app_context():
        column = SessionExercise.__table__.columns['mirrors_id']
        assert column.nullable, 'every non-shared session leaves this NULL'
        version = WorkoutSession.__table__.columns['structure_version']
        assert not version.nullable
        assert version.default.arg == 0
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_sharing.py -v`
Expected: FAIL — `ImportError: cannot import name 'SharedSession' from 'models'`

- [ ] **Step 4: Add the models**

In `models.py`, immediately after the `SessionSet` class, add:

```python
class SharedSession(db.Model):
    """One live workout carried across to a training partner.

    Two people training together share structure -- which exercises, in what
    order -- and nothing else. Weight and reps are the one thing that cannot
    transfer between two bodies, so each side owns an ordinary WorkoutSession
    and this row only links them.

    State is derived from the timestamps rather than a status column:
    pending (accepted_at IS NULL), active (accepted, ended_at IS NULL), ended.
    """
    __tablename__ = 'gym_shared_sessions'
    id                  = db.Column(db.Integer, primary_key=True, autoincrement=True)
    leader_session_id   = db.Column(db.Integer, db.ForeignKey('gym_workout_sessions.id'), nullable=False, index=True)
    # NULL until the invite is accepted: the follower's session does not exist
    # before then, because it is seeded from the leader's structure at accept
    # time rather than at invite time.
    follower_session_id = db.Column(db.Integer, db.ForeignKey('gym_workout_sessions.id'), nullable=True)
    leader_user_id      = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False)
    follower_user_id    = db.Column(db.Integer, db.ForeignKey('app_user.id'), nullable=False, index=True)
    created_at          = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    accepted_at         = db.Column(db.DateTime, nullable=True)
    # Stamped when EITHER session finishes, whichever comes first. Propagation
    # stops from that moment; the follower trains on alone.
    ended_at            = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        # Inviting the same person twice to the same workout re-surfaces the
        # existing invite instead of creating a second one.
        db.UniqueConstraint('leader_session_id', 'follower_user_id',
                            name='uq_gym_shared_sessions_leader_session_follower'),
    )

    exercise_map = db.relationship('SharedSessionExercise', lazy=True,
                                   cascade="all, delete-orphan")


class SharedSessionExercise(db.Model):
    """One exercise, named twice.

    Exercises became per-user on 2026-08-02, so "Bankdruecken" in two
    catalogues is two rows with two ids. A structural change expressed in the
    leader's ids means nothing against the follower's data without this.
    """
    __tablename__ = 'gym_shared_session_exercises'
    id                   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    shared_session_id    = db.Column(db.Integer, db.ForeignKey('gym_shared_sessions.id'), nullable=False, index=True)
    leader_exercise_id   = db.Column(db.Integer, db.ForeignKey('gym_exercises.id'), nullable=False)
    follower_exercise_id = db.Column(db.Integer, db.ForeignKey('gym_exercises.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('shared_session_id', 'leader_exercise_id',
                            name='uq_gym_shared_session_exercises_link_leader'),
    )
```

In the `SessionExercise` class, after the `skipped` column, add:

```python
    # The leader's SessionExercise this row mirrors, when this session is the
    # follower half of a shared workout. Reconciliation keys on this rather
    # than exercise_id: the two catalogues use different ids for the same
    # lift, and one exercise can legitimately appear twice in a session (an
    # original plus the substitute that replaced it). NULL on every ordinary
    # session, which is almost all of them.
    mirrors_id   = db.Column(db.Integer, db.ForeignKey('gym_session_exercises.id', ondelete='SET NULL'), nullable=True)
```

In the `WorkoutSession` class, after the `deload_pct` column, add:

```python
    # Bumped whenever a shared workout's reconciliation actually changes this
    # session's structure. The follower's page polls it; an unchanged version
    # means the poll costs a few bytes and no re-render.
    structure_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
```

- [ ] **Step 5: Write the migration**

Create `migrations/versions/e4a91c7d20f8_add_shared_sessions.py`:

```python
"""add shared sessions

Revision ID: e4a91c7d20f8
Revises: d1f6b83c25e9
"""
from alembic import op
import sqlalchemy as sa

revision = 'e4a91c7d20f8'
down_revision = 'd1f6b83c25e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'gym_shared_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('leader_session_id', sa.Integer(), nullable=False),
        sa.Column('follower_session_id', sa.Integer(), nullable=True),
        sa.Column('leader_user_id', sa.Integer(), nullable=False),
        sa.Column('follower_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['leader_session_id'], ['gym_workout_sessions.id'],
                                name='fk_gym_shared_sessions_leader_session'),
        sa.ForeignKeyConstraint(['follower_session_id'], ['gym_workout_sessions.id'],
                                name='fk_gym_shared_sessions_follower_session'),
        sa.ForeignKeyConstraint(['leader_user_id'], ['app_user.id'],
                                name='fk_gym_shared_sessions_leader_user'),
        sa.ForeignKeyConstraint(['follower_user_id'], ['app_user.id'],
                                name='fk_gym_shared_sessions_follower_user'),
        sa.UniqueConstraint('leader_session_id', 'follower_user_id',
                            name='uq_gym_shared_sessions_leader_session_follower'),
    )
    op.create_index('ix_gym_shared_sessions_leader_session_id',
                    'gym_shared_sessions', ['leader_session_id'])
    op.create_index('ix_gym_shared_sessions_follower_user_id',
                    'gym_shared_sessions', ['follower_user_id'])

    op.create_table(
        'gym_shared_session_exercises',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('shared_session_id', sa.Integer(), nullable=False),
        sa.Column('leader_exercise_id', sa.Integer(), nullable=False),
        sa.Column('follower_exercise_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shared_session_id'], ['gym_shared_sessions.id'],
                                name='fk_gym_shared_session_exercises_link'),
        sa.ForeignKeyConstraint(['leader_exercise_id'], ['gym_exercises.id'],
                                name='fk_gym_shared_session_exercises_leader_exercise'),
        sa.ForeignKeyConstraint(['follower_exercise_id'], ['gym_exercises.id'],
                                name='fk_gym_shared_session_exercises_follower_exercise'),
        sa.UniqueConstraint('shared_session_id', 'leader_exercise_id',
                            name='uq_gym_shared_session_exercises_link_leader'),
    )
    op.create_index('ix_gym_shared_session_exercises_shared_session_id',
                    'gym_shared_session_exercises', ['shared_session_id'])

    op.add_column('gym_session_exercises',
                  sa.Column('mirrors_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_gym_session_exercises_mirrors',
                          'gym_session_exercises', 'gym_session_exercises',
                          ['mirrors_id'], ['id'], ondelete='SET NULL')

    op.add_column('gym_workout_sessions',
                  sa.Column('structure_version', sa.Integer(), nullable=False,
                            server_default='0'))


def downgrade():
    op.drop_column('gym_workout_sessions', 'structure_version')
    op.drop_constraint('fk_gym_session_exercises_mirrors',
                       'gym_session_exercises', type_='foreignkey')
    op.drop_column('gym_session_exercises', 'mirrors_id')
    op.drop_index('ix_gym_shared_session_exercises_shared_session_id',
                  table_name='gym_shared_session_exercises')
    op.drop_table('gym_shared_session_exercises')
    op.drop_index('ix_gym_shared_sessions_follower_user_id',
                  table_name='gym_shared_sessions')
    op.drop_index('ix_gym_shared_sessions_leader_session_id',
                  table_name='gym_shared_sessions')
    op.drop_table('gym_shared_sessions')
```

- [ ] **Step 6: Apply the migration**

Run: `flask db upgrade`
Expected: `Running upgrade d1f6b83c25e9 -> e4a91c7d20f8, add shared sessions`

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_sharing.py -v`
Expected: PASS, 2 passed

- [ ] **Step 8: Verify reversibility**

Run: `flask db downgrade` then `flask db upgrade`
Expected: both succeed. Report the output of both.

- [ ] **Step 9: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 10: Commit**

```bash
git add models.py migrations/versions/e4a91c7d20f8_add_shared_sessions.py tests/test_gym_sharing.py
git commit -m "feat(gym): tables for a workout shared with a training partner"
```

---

### Task 2: Name matching, as pure functions

The confirm screen has to propose which of the follower's exercises corresponds to each of the leader's. That is a string problem, and it belongs in a module with no ORM dependency so it can be tested with plain tuples — the same shape as `features/gym/stats.py`.

**Files:**
- Create: `features/gym/matching.py`
- Test: `tests/test_gym_matching.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces, in `features.gym.matching`:
  - `normalise(name) -> str` — casefolded, whitespace-collapsed.
  - `propose_matches(leader_names, follower_catalogue) -> list[dict]` where `follower_catalogue` is an iterable of `(id, name)`. Each dict has `name` (the leader's name, verbatim), `exact_id` (`int | None`), and `candidates` (a list of `(id, name)` ordered best-first).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gym_matching.py`:

```python
"""Pure name matching for the shared-session confirm screen. No ORM here --
these are plain tuples, like the tests for stats.py."""


def test_normalise_ignores_case_and_padding():
    from features.gym import matching
    assert matching.normalise('  Bankdrücken ') == matching.normalise('bankdrücken')


def test_normalise_collapses_inner_whitespace():
    from features.gym import matching
    assert matching.normalise('KH  Bankdrücken') == matching.normalise('KH Bankdrücken')


def test_an_exact_name_is_matched_and_asks_nothing():
    """Both people call it Bankdrücken. There is nothing to confirm, and asking
    seven times per shared workout would make the common path the annoying one."""
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'], [(4, 'Bankdrücken'), (5, 'Kniebeuge')])
    assert proposals[0]['exact_id'] == 4


def test_an_exact_match_ignores_case_and_padding():
    from features.gym import matching
    proposals = matching.propose_matches(['Bankdrücken'], [(4, ' bankdrücken')])
    assert proposals[0]['exact_id'] == 4


def test_a_name_with_no_counterpart_has_no_exact_match():
    from features.gym import matching
    proposals = matching.propose_matches(['Bankdrücken'], [(5, 'Kniebeuge')])
    assert proposals[0]['exact_id'] is None


def test_substring_candidates_come_first():
    """Deliberately dull: containment either way, then alphabetical. Enough to
    float "KH Bankdrücken" to the top without pretending to understand German
    gym vocabulary."""
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'],
        [(1, 'Zug zum Kinn'), (2, 'KH Bankdrücken'), (3, 'Beinpresse')])
    assert proposals[0]['candidates'][0] == (2, 'KH Bankdrücken')


def test_candidates_after_the_substring_hits_are_alphabetical():
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'], [(1, 'Zug zum Kinn'), (3, 'Beinpresse')])
    assert [name for _, name in proposals[0]['candidates']] == [
        'Beinpresse', 'Zug zum Kinn']


def test_every_candidate_is_offered_even_when_an_exact_match_exists():
    """The follower may disagree with the exact match -- two people can use the
    same word for different machines. The dropdown still lists everything."""
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'], [(4, 'Bankdrücken'), (5, 'Kniebeuge')])
    assert len(proposals[0]['candidates']) == 2


def test_the_leader_name_is_returned_verbatim():
    """It is what a newly created exercise will be called, so it must not
    arrive normalised."""
    from features.gym import matching
    proposals = matching.propose_matches(['  KH Bankdrücken '], [])
    assert proposals[0]['name'] == '  KH Bankdrücken '


def test_an_empty_catalogue_proposes_nothing_and_does_not_crash():
    """The third lifter's first shared workout: she owns no exercises at all."""
    from features.gym import matching
    proposals = matching.propose_matches(['Bankdrücken'], [])
    assert proposals == [{'name': 'Bankdrücken', 'exact_id': None, 'candidates': []}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.gym.matching'`

- [ ] **Step 3: Write the module**

Create `features/gym/matching.py`:

```python
"""Matching one lifter's exercise names against another's catalogue.

Exercises are per-user, so a shared workout has to be translated before it can
be carried across. This module decides what to propose; the follower decides
what is true. Pure functions over plain values -- no ORM, so the tests can pass
tuples.
"""


def normalise(name):
    """Casefolded and whitespace-collapsed, for comparison only.

    Never store this: a created exercise takes the name as typed.
    """
    return ' '.join((name or '').split()).casefold()


def propose_matches(leader_names, follower_catalogue):
    """What to show the follower for each of the leader's exercises.

    `follower_catalogue` is an iterable of (id, name) -- the follower's own
    exercises. Returns one dict per leader name, in the order given:

        {'name': str,            # the leader's name, VERBATIM
         'exact_id': int | None, # normalised-equal match, needs no question
         'candidates': [(id, name), ...]}  # best-first, always the full list

    Candidate order is deliberately dull: names that contain the leader's name
    (or are contained by it) first, then everything else alphabetically. Enough
    to float "KH Bankdruecken" to the top for "Bankdruecken" without pretending
    to understand German gym vocabulary -- and a wrong guess only costs a
    scroll, because the follower confirms.
    """
    catalogue = [(row_id, name) for row_id, name in follower_catalogue]

    proposals = []
    for leader_name in leader_names:
        target = normalise(leader_name)

        exact_id = None
        for row_id, name in catalogue:
            if normalise(name) == target:
                exact_id = row_id
                break

        def rank(row):
            name = normalise(row[1])
            related = target and (target in name or name in target)
            return (0 if related else 1, name)

        proposals.append({
            'name': leader_name,
            'exact_id': exact_id,
            'candidates': sorted(catalogue, key=rank),
        })
    return proposals
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_matching.py -v`
Expected: PASS, 10 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add features/gym/matching.py tests/test_gym_matching.py
git commit -m "feat(gym): propose exercise matches between two catalogues"
```

---

### Task 3: The chokepoint

The one function in the app that writes into another user's session. Everything about propagation goes through it, so there is one place to audit.

**Files:**
- Create: `features/gym/sharing.py`
- Test: `tests/test_gym_sharing.py`

**Interfaces:**
- Consumes: `SharedSession`, `SharedSessionExercise`, `SessionExercise.mirrors_id`, `WorkoutSession.structure_version` from Task 1.
- Produces, in `features.gym.sharing`:
  - `active_links_led_by(session_id) -> list[SharedSession]`
  - `follower_exercise_for(shared, leader_exercise_id) -> int | None` (None only when the leader's exercise row has vanished)
  - `reconcile_follower(shared) -> bool` — True when it changed anything.
  - `remove_mirrors_of(session_exercise) -> None` — deletes the follower rows mirroring this one. Must be called BEFORE the leader's row is deleted; see Task 6.
  - `propagate_structure(session_) -> None` — what routes call.
  - `end_links_for(session_) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gym_sharing.py`:

```python
@pytest.fixture()
def linked_pair():
    """An accepted link between two fresh lifters, each with a live session.

    The leader owns 'pytest shared bench'; the follower owns a same-named
    exercise of their own, already mapped. Yields a dict of ids.
    """
    from extensions import db
    from models import (AppUser, Exercise, SessionExercise, SharedSession,
                        SharedSessionExercise, WorkoutSession)
    from werkzeug.security import generate_password_hash

    made = {}
    with flask_app.app_context():
        leader = AppUser(username='pytest sharing leader',
                         password_hash=generate_password_hash('a'), is_admin=False)
        follower = AppUser(username='pytest sharing follower',
                           password_hash=generate_password_hash('b'), is_admin=False)
        db.session.add_all([leader, follower])
        db.session.flush()

        leader_bench = Exercise(name='pytest shared bench', user_id=leader.id)
        follower_bench = Exercise(name='pytest shared bench', user_id=follower.id)
        db.session.add_all([leader_bench, follower_bench])
        db.session.flush()

        now = dt.datetime.utcnow()
        leader_session = WorkoutSession(name='pytest shared workout',
                                        started_at=now, user_id=leader.id)
        leader_row = SessionExercise(exercise_id=leader_bench.id, position=1)
        leader_session.exercises.append(leader_row)
        follower_session = WorkoutSession(name='pytest shared workout',
                                          started_at=now, user_id=follower.id)
        db.session.add_all([leader_session, follower_session])
        db.session.flush()

        follower_row = SessionExercise(session_id=follower_session.id,
                                       exercise_id=follower_bench.id,
                                       position=1, mirrors_id=leader_row.id)
        db.session.add(follower_row)

        shared = SharedSession(leader_session_id=leader_session.id,
                               follower_session_id=follower_session.id,
                               leader_user_id=leader.id, follower_user_id=follower.id,
                               accepted_at=now)
        db.session.add(shared)
        db.session.flush()
        db.session.add(SharedSessionExercise(
            shared_session_id=shared.id,
            leader_exercise_id=leader_bench.id,
            follower_exercise_id=follower_bench.id))
        db.session.commit()

        made = {'leader_user': leader.id, 'follower_user': follower.id,
                'leader_exercise': leader_bench.id, 'follower_exercise': follower_bench.id,
                'leader_session': leader_session.id, 'follower_session': follower_session.id,
                'leader_row': leader_row.id, 'shared': shared.id}
    yield made

    with flask_app.app_context():
        doomed = db.session.get(SharedSession, made['shared'])
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()
        for key in ('leader_session', 'follower_session'):
            doomed = db.session.get(WorkoutSession, made[key])
            if doomed is not None:
                doomed.resting_set_id = None
                db.session.commit()
                db.session.delete(doomed)
                db.session.commit()
        for row in Exercise.query.filter(Exercise.name.like('pytest shared%')).all():
            db.session.delete(row)
        db.session.commit()
        for key in ('leader_user', 'follower_user'):
            doomed = db.session.get(AppUser, made[key])
            if doomed is not None:
                db.session.delete(doomed)
        db.session.commit()


def test_an_added_exercise_appears_on_the_followers_side(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        squat = Exercise(name='pytest shared squat', user_id=linked_pair['leader_user'])
        db.session.add(squat)
        db.session.flush()
        leader_session.exercises.append(
            SessionExercise(exercise_id=squat.id, position=2))
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        names = [se.exercise.name for se in follower_session.exercises]
        assert 'pytest shared squat' in names, 'the added exercise did not carry across'
        carried = [se for se in follower_session.exercises
                   if se.exercise.name == 'pytest shared squat'][0]
        assert carried.exercise.user_id == linked_pair['follower_user'], (
            'the follower was linked to the LEADER\'s exercise row')


def test_a_removed_exercise_disappears_from_the_followers_side(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        for se in list(leader_session.exercises):
            db.session.delete(se)
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert list(follower_session.exercises) == []


def test_reorder_carries_across_translated(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        squat = Exercise(name='pytest shared squat', user_id=linked_pair['leader_user'])
        db.session.add(squat)
        db.session.flush()
        leader_session.exercises.append(
            SessionExercise(exercise_id=squat.id, position=2))
        db.session.commit()
        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        # Now swap them on the leader's side.
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        for se in leader_session.exercises:
            se.position = 1 if se.position == 2 else 2
        db.session.commit()
        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        ordered = sorted(follower_session.exercises, key=lambda se: se.position)
        assert [se.exercise.name for se in ordered] == [
            'pytest shared squat', 'pytest shared bench']


def test_skipping_carries_across(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        row = db.session.get(SessionExercise, linked_pair['leader_row'])
        row.skipped = True
        db.session.commit()
        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert all(se.skipped for se in follower_session.exercises)


def test_the_followers_sets_are_never_touched(linked_pair):
    """Weight and reps are the one thing that cannot transfer between two
    bodies. Reconciliation must not so much as look at them."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SessionSet, SharedSession, WorkoutSession

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        row = follower_session.exercises[0]
        row.sets.append(SessionSet(position=1, weight=87.5, reps=6, completed=True))
        db.session.commit()
        set_id = row.sets[0].id

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        survivor = db.session.get(SessionSet, set_id)
        assert survivor is not None, 'reconciliation deleted a logged set'
        assert (survivor.weight, survivor.reps) == (87.5, 6)


def test_set_count_does_not_propagate(linked_pair):
    """Appending a fourth set is a decision about your own body mid-lift, not
    programming. If it propagated, an empty set would appear in your partner's
    queue because someone else felt strong."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SessionSet, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        leader_row.sets.append(SessionSet(position=1, weight=60.0, reps=10, completed=True))
        leader_row.sets.append(SessionSet(position=2, weight=60.0, reps=10, completed=True))
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert follower_session.exercises[0].sets == [], (
            'the leader\'s sets appeared in the follower\'s queue')


def test_reconciliation_refuses_a_link_that_was_never_accepted(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        shared.accepted_at = None
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        squat = Exercise(name='pytest shared squat', user_id=linked_pair['leader_user'])
        db.session.add(squat)
        db.session.flush()
        leader_session.exercises.append(SessionExercise(exercise_id=squat.id, position=2))
        db.session.commit()

        assert sharing.reconcile_follower(
            db.session.get(SharedSession, linked_pair['shared'])) is False
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert len(list(follower_session.exercises)) == 1


def test_reconciliation_refuses_an_ended_link(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        shared.ended_at = dt.datetime.utcnow()
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        squat = Exercise(name='pytest shared squat', user_id=linked_pair['leader_user'])
        db.session.add(squat)
        db.session.flush()
        leader_session.exercises.append(SessionExercise(exercise_id=squat.id, position=2))
        db.session.commit()

        assert sharing.reconcile_follower(
            db.session.get(SharedSession, linked_pair['shared'])) is False
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert len(list(follower_session.exercises)) == 1


def test_reconciliation_refuses_when_the_link_disagrees_with_the_session_owner(linked_pair):
    """A corrupted or forged link must not become a way to write into an
    arbitrary session."""
    from extensions import db
    from features.gym import sharing
    from models import SharedSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        shared.leader_user_id = linked_pair['follower_user']
        db.session.commit()

        assert sharing.reconcile_follower(
            db.session.get(SharedSession, linked_pair['shared'])) is False


def test_a_missing_exercise_is_created_in_the_followers_catalogue(linked_pair):
    """The third lifter shares no exercises at all. A mid-session addition
    resolves silently -- confirmation is upfront, never mid-set."""
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SharedSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        novel = Exercise(name='pytest shared novel lift',
                         user_id=linked_pair['leader_user'])
        db.session.add(novel)
        db.session.flush()

        resolved_id = sharing.follower_exercise_for(shared, novel.id)
        db.session.commit()

        created = db.session.get(Exercise, resolved_id)
        assert created.user_id == linked_pair['follower_user'], (
            'the created exercise must belong to the follower, never the leader')
        assert created.id != novel.id


def test_an_exact_name_links_instead_of_duplicating(linked_pair):
    """The follower already owns 'pytest shared bench'. Resolving it must reuse
    that row, not leave them with two."""
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SharedSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        resolved_id = sharing.follower_exercise_for(
            shared, linked_pair['leader_exercise'])
        db.session.commit()
        assert resolved_id == linked_pair['follower_exercise']
        owned = Exercise.query.filter_by(user_id=linked_pair['follower_user'],
                                         name='pytest shared bench').count()
        assert owned == 1


def test_a_change_bumps_the_followers_structure_version(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        before = db.session.get(
            WorkoutSession, linked_pair['follower_session']).structure_version
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        squat = Exercise(name='pytest shared squat', user_id=linked_pair['leader_user'])
        db.session.add(squat)
        db.session.flush()
        leader_session.exercises.append(SessionExercise(exercise_id=squat.id, position=2))
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        after = db.session.get(
            WorkoutSession, linked_pair['follower_session']).structure_version
        assert after == before + 1


def test_reconciling_an_unchanged_structure_does_not_bump_the_version(linked_pair):
    """Otherwise every action by the leader forces the follower's page to
    re-render, including logging a set."""
    from extensions import db
    from features.gym import sharing
    from models import SharedSession, WorkoutSession

    with flask_app.app_context():
        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()
        settled = db.session.get(
            WorkoutSession, linked_pair['follower_session']).structure_version

        assert sharing.reconcile_follower(
            db.session.get(SharedSession, linked_pair['shared'])) is False
        db.session.commit()

        assert db.session.get(
            WorkoutSession, linked_pair['follower_session']).structure_version == settled
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_sharing.py -v -k "linked_pair or added_exercise or removed_exercise or reorder or skipping or never_touched or set_count or refuses or created_in or links_instead or structure_version"`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.gym.sharing'`

- [ ] **Step 3: Write the module**

Create `features/gym/sharing.py`:

```python
"""Shared live sessions: the link's lifecycle, and the one cross-user write.

Two people training together share structure and nothing else. Each owns an
ordinary WorkoutSession; a SharedSession links them and SharedSessionExercise
translates between their per-user catalogues.

Propagation is a RECONCILIATION rather than a per-operation replay. After any
structural change the leader's route calls propagate_structure(), which makes
the follower's exercise rows mirror the leader's. One idempotent function
instead of five translations -- and being idempotent, it is correct after any
operation, including ones added later.

This module contains the only code in the app that writes into another user's
rows. Every such write goes through reconcile_follower(), which refuses unless
the link is real, accepted, live, and internally consistent. It is deliberately
the mirror image of scope.py: that module is the one place reads are gated,
this is the one place a cross-user write can happen.
"""
import datetime as dt

from extensions import db
from models import (Exercise, SessionExercise, SharedSession,
                    SharedSessionExercise, WorkoutSession)

from .matching import normalise


def active_links_led_by(session_id):
    """Accepted, unfinished links where this session is the leader."""
    return (SharedSession.query
            .filter(SharedSession.leader_session_id == session_id,
                    SharedSession.accepted_at.isnot(None),
                    SharedSession.ended_at.is_(None))
            .all())


def follower_exercise_for(shared, leader_exercise_id):
    """The follower's exercise corresponding to one of the leader's.

    Reuses the mapping if it exists, then an exact name match in the follower's
    catalogue, and only then creates one. The created row is owned by the
    FOLLOWER -- the name travels, the ownership never does.

    This queries Exercise directly rather than through scope.my_exercises(),
    because it runs inside the LEADER's request and needs the follower's
    catalogue. That is the deliberate cross-user reach, and it is confined to
    this function.
    """
    mapped = (SharedSessionExercise.query
              .filter_by(shared_session_id=shared.id,
                         leader_exercise_id=leader_exercise_id)
              .first())
    if mapped is not None:
        return mapped.follower_exercise_id

    leader_exercise = db.session.get(Exercise, leader_exercise_id)
    if leader_exercise is None:
        return None

    target = normalise(leader_exercise.name)
    match = None
    for candidate in Exercise.query.filter_by(user_id=shared.follower_user_id).all():
        if normalise(candidate.name) == target:
            match = candidate
            break

    if match is None:
        match = Exercise(
            name=leader_exercise.name,
            muscle_group=leader_exercise.muscle_group,
            default_rest_seconds=leader_exercise.default_rest_seconds,
            user_id=shared.follower_user_id,
        )
        db.session.add(match)
        db.session.flush()

    db.session.add(SharedSessionExercise(
        shared_session_id=shared.id,
        leader_exercise_id=leader_exercise_id,
        follower_exercise_id=match.id,
    ))
    db.session.flush()
    return match.id


def reconcile_follower(shared):
    """Make the follower's structure mirror the leader's. Returns True if
    anything changed.

    Idempotent by construction: it compares the two sides and applies the
    difference, so calling it twice is the same as calling it once, and it is
    correct after any structural operation rather than one per operation.

    Rows are matched on SessionExercise.mirrors_id, never on exercise_id. The
    two catalogues use different ids for the same lift, and one exercise can
    legitimately appear twice in a session -- an original plus the substitute
    that replaced it.

    NOTHING here seeds sets. This runs inside the LEADER's request, where
    current_user_id() is the leader, so any history lookup would pre-fill the
    follower's sets from the wrong person's training. An exercise added
    mid-session therefore arrives as an empty slot; the follower's own steppers
    still pre-fill from their history when the page renders in THEIR request.
    Seeding at accept time is correct for the same reason -- that runs in the
    follower's request.
    """
    if shared is None or shared.accepted_at is None or shared.ended_at is not None:
        return False
    if shared.follower_session_id is None:
        return False

    leader = db.session.get(WorkoutSession, shared.leader_session_id)
    follower = db.session.get(WorkoutSession, shared.follower_session_id)
    if leader is None or follower is None:
        return False
    # A corrupted or forged link must not become a way to write into an
    # arbitrary session. Both halves have to agree with the sessions they name.
    if leader.user_id != shared.leader_user_id:
        return False
    if follower.user_id != shared.follower_user_id:
        return False
    # The follower finishing ends their participation even if the link has not
    # been stamped yet.
    if follower.finished_at is not None:
        return False

    mirrored = {se.mirrors_id: se for se in follower.exercises
                if se.mirrors_id is not None}
    changed = False

    for leader_row in sorted(leader.exercises, key=lambda se: se.position):
        row = mirrored.get(leader_row.id)
        if row is None:
            follower_exercise_id = follower_exercise_for(shared, leader_row.exercise_id)
            if follower_exercise_id is None:
                continue
            follower_exercise = db.session.get(Exercise, follower_exercise_id)
            row = SessionExercise(
                session_id=follower.id,
                exercise_id=follower_exercise_id,
                position=leader_row.position,
                # Rest follows the person, so this is the FOLLOWER's default,
                # never the leader's per-session override.
                rest_seconds=follower_exercise.default_rest_seconds if follower_exercise else None,
                skipped=leader_row.skipped,
                mirrors_id=leader_row.id,
            )
            db.session.add(row)
            mirrored[leader_row.id] = row
            changed = True
            continue
        if row.position != leader_row.position:
            row.position = leader_row.position
            changed = True
        if row.skipped != leader_row.skipped:
            row.skipped = leader_row.skipped
            changed = True

    live_leader_ids = {se.id for se in leader.exercises}
    for leader_row_id, row in list(mirrored.items()):
        if leader_row_id in live_leader_ids:
            continue
        # Deleting an exercise cascades to its sets, so clear the session's
        # pointer at a resting set first or the foreign key blocks it.
        if follower.resting_set_id in [s.id for s in row.sets]:
            follower.resting_set_id = None
            follower.rest_ends_at = None
        db.session.delete(row)
        del mirrored[leader_row_id]
        changed = True

    # Substitutes second, once every row exists and has an id: a leader row
    # that replaces another must point at the follower's counterpart of that
    # other row, not at the leader's.
    db.session.flush()
    for leader_row in leader.exercises:
        row = mirrored.get(leader_row.id)
        if row is None:
            continue
        original = mirrored.get(leader_row.replaces_id) if leader_row.replaces_id else None
        wanted = original.id if original is not None else None
        if row.replaces_id != wanted:
            row.replaces_id = wanted
            changed = True

    if changed:
        follower.structure_version = (follower.structure_version or 0) + 1
    return changed


def propagate_structure(session_):
    """Carry this session's structure to every partner who accepted.

    Called by the leader's structural routes after they commit their own
    change. Safe to call on any session: one that leads no link does nothing.
    """
    for shared in active_links_led_by(session_.id):
        reconcile_follower(shared)
    db.session.commit()


def end_links_for(session_):
    """Stamp every live link this session takes part in, on either side.

    Whoever finishes first ends the sharing; the other trains on alone, which
    is the whole point -- a workout must never be cut short by someone else's.
    """
    links = (SharedSession.query
             .filter(SharedSession.ended_at.is_(None))
             .filter(db.or_(SharedSession.leader_session_id == session_.id,
                            SharedSession.follower_session_id == session_.id))
             .all())
    for shared in links:
        shared.ended_at = dt.datetime.utcnow()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_sharing.py -v`
Expected: PASS, 15 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Prove the security guard has teeth**

Temporarily comment out the two owner-agreement checks in `reconcile_follower`:

```python
    # if leader.user_id != shared.leader_user_id:
    #     return False
```

Run: `python -m pytest tests/test_gym_sharing.py -v -k disagrees`
Expected: FAIL. Restore the lines, re-run, expect PASS. Report both outputs — this is the evidence that the guard is load-bearing rather than decorative.

- [ ] **Step 6: Commit**

```bash
git add features/gym/sharing.py tests/test_gym_sharing.py
git commit -m "feat(gym): reconcile a partner's structure through one guarded chokepoint"
```

---

### Task 4: The invite

**Files:**
- Modify: `features/gym/routes.py`
- Modify: `templates/gym/session_detail.html`
- Modify: `templates/gym/heute.html`
- Modify: `static/gym/gym.css`
- Test: `tests/test_gym_sharing.py`

**Interfaces:**
- Consumes: `sharing.active_links_led_by` from Task 3.
- Produces:
  - `POST /gym/session/<int:session_id>/invite` (endpoint `gym.gym_invite_partner`), form field `partner_id`.
  - Template variable `partners` on `session_detail.html` — list of `AppUser` the caller can invite.
  - Template variable `shared_out` on `session_detail.html` — the caller's outgoing links for this session.
  - Template variable `pending_invites` on `heute.html` — list of dicts `{'shared_id', 'leader_name', 'session_name'}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gym_sharing.py`:

```python
@pytest.fixture()
def leader_with_partner():
    """A fresh leader with a live session, and a fresh partner to invite."""
    from extensions import db
    from models import AppUser, Exercise, SessionExercise, WorkoutSession
    from werkzeug.security import generate_password_hash

    made = {}
    with flask_app.app_context():
        leader = AppUser(username='pytest invite leader',
                         password_hash=generate_password_hash('a'), is_admin=False)
        partner = AppUser(username='pytest invite partner',
                          password_hash=generate_password_hash('b'), is_admin=False)
        db.session.add_all([leader, partner])
        db.session.flush()

        bench = Exercise(name='pytest invite bench', user_id=leader.id)
        db.session.add(bench)
        db.session.flush()

        session_ = WorkoutSession(name='pytest invite workout',
                                  started_at=dt.datetime.utcnow(), user_id=leader.id)
        session_.exercises.append(SessionExercise(exercise_id=bench.id, position=1))
        db.session.add(session_)
        db.session.commit()

        made = {'leader': leader.id, 'partner': partner.id,
                'session': session_.id, 'exercise': bench.id}
    yield made

    with flask_app.app_context():
        from models import SharedSession
        for shared in SharedSession.query.filter(
                db.or_(SharedSession.leader_user_id == made['leader'],
                       SharedSession.follower_user_id == made['partner'])).all():
            db.session.delete(shared)
        db.session.commit()
        for user_id in (made['leader'], made['partner']):
            for row in WorkoutSession.query.filter_by(user_id=user_id).all():
                row.resting_set_id = None
                db.session.commit()
                db.session.delete(row)
            db.session.commit()
            for row in Exercise.query.filter_by(user_id=user_id).all():
                db.session.delete(row)
            db.session.commit()
            doomed = db.session.get(AppUser, user_id)
            if doomed is not None:
                db.session.delete(doomed)
        db.session.commit()


def _client_for(user_id):
    flask_app.config['TESTING'] = True
    test_client = flask_app.test_client()
    with test_client.session_transaction() as flask_session:
        flask_session['user_id'] = user_id
    return test_client


def test_inviting_a_partner_creates_a_pending_link(leader_with_partner):
    from extensions import db
    from models import SharedSession

    client = _client_for(leader_with_partner['leader'])
    client.post(f"/gym/session/{leader_with_partner['session']}/invite",
                data={'partner_id': leader_with_partner['partner']})

    with flask_app.app_context():
        shared = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first()
        assert shared is not None, 'no invite was created'
        assert shared.follower_user_id == leader_with_partner['partner']
        assert shared.accepted_at is None
        assert shared.follower_session_id is None


def test_inviting_twice_does_not_create_a_second_invite(leader_with_partner):
    from extensions import db
    from models import SharedSession

    client = _client_for(leader_with_partner['leader'])
    for _ in range(2):
        client.post(f"/gym/session/{leader_with_partner['session']}/invite",
                    data={'partner_id': leader_with_partner['partner']})

    with flask_app.app_context():
        assert SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).count() == 1


def test_a_stranger_cannot_invite_into_someone_elses_session(leader_with_partner):
    """Ownership failures are 404 throughout the gym: a 403 would confirm the
    session exists."""
    from extensions import db
    from models import SharedSession

    client = _client_for(leader_with_partner['partner'])
    response = client.post(f"/gym/session/{leader_with_partner['session']}/invite",
                           data={'partner_id': leader_with_partner['partner']})
    assert response.status_code == 404

    with flask_app.app_context():
        assert SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).count() == 0


def test_you_cannot_invite_yourself(leader_with_partner):
    from extensions import db
    from models import SharedSession

    client = _client_for(leader_with_partner['leader'])
    client.post(f"/gym/session/{leader_with_partner['session']}/invite",
                data={'partner_id': leader_with_partner['leader']})

    with flask_app.app_context():
        assert SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).count() == 0


def test_the_partner_sees_the_invite_on_their_start_page(leader_with_partner):
    client = _client_for(leader_with_partner['leader'])
    client.post(f"/gym/session/{leader_with_partner['session']}/invite",
                data={'partner_id': leader_with_partner['partner']})

    partner_client = _client_for(leader_with_partner['partner'])
    html = partner_client.get('/gym').get_data(as_text=True)
    assert 'pytest invite leader' in html, 'the invite is not on the partner\'s Start page'
    assert 'invite-card' in html


def test_a_third_party_does_not_see_the_invite(leader_with_partner):
    """The invite is addressed to one person."""
    from extensions import db
    from models import AppUser
    from werkzeug.security import generate_password_hash

    client = _client_for(leader_with_partner['leader'])
    client.post(f"/gym/session/{leader_with_partner['session']}/invite",
                data={'partner_id': leader_with_partner['partner']})

    outsider_id = None
    try:
        with flask_app.app_context():
            outsider = AppUser(username='pytest invite outsider',
                               password_hash=generate_password_hash('c'), is_admin=False)
            db.session.add(outsider)
            db.session.commit()
            outsider_id = outsider.id

        html = _client_for(outsider_id).get('/gym').get_data(as_text=True)
        assert 'invite-card' not in html
    finally:
        with flask_app.app_context():
            if outsider_id:
                doomed = db.session.get(AppUser, outsider_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_sharing.py -v -k invite`
Expected: FAIL — 404 from `/gym/session/<id>/invite`, which does not exist yet.

- [ ] **Step 3: Add the invite route**

In `features/gym/routes.py`, add to the imports near the other `features.gym` imports:

```python
from . import sharing
```

and add `AppUser`, `SharedSession` to the existing `from models import (...)` list.

Add this route immediately after `gym_finish_session`:

```python
@gym_bp.route('/gym/session/<int:session_id>/invite', methods=['POST'])
@login_required
def gym_invite_partner(session_id):
    """Ask someone to train this workout with you.

    The invite is pending until they accept; your session started already and
    is never blocked on them. Their session does not exist yet on purpose --
    it is seeded from your structure when they accept, so anything you add
    while they walk to the gym is included.
    """
    session_ = owned_session(session_id)
    partner_id = request.form.get('partner_id', type=int)

    if not partner_id or partner_id == current_user_id():
        flash('Kein Trainingspartner ausgewählt.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))
    if session_.finished_at is not None:
        flash('Das Workout ist schon vorbei.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))

    partner = db.session.get(AppUser, partner_id)
    if partner is None:
        flash('Kein Trainingspartner ausgewählt.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))

    existing = SharedSession.query.filter_by(
        leader_session_id=session_.id, follower_user_id=partner_id).first()
    if existing is None:
        db.session.add(SharedSession(
            leader_session_id=session_.id,
            leader_user_id=current_user_id(),
            follower_user_id=partner_id,
        ))
        db.session.commit()
        push.send_push_to_user(partner_id, {
            'title': f'{_username(current_user_id())} trainiert',
            'body': f'{session_.name or "Workout"} — mitmachen?',
        })
    flash(f'{partner.username} wurde eingeladen.', 'success')
    return redirect(url_for('gym.session_detail', session_id=session_.id))
```

Add this helper immediately above `gym_invite_partner`:

```python
def _username(user_id):
    row = db.session.get(AppUser, user_id)
    return row.username if row is not None else 'Jemand'
```

Confirm `push` is imported in `routes.py` (`from . import push` or equivalent); if it is imported under a different name, use that name instead.

- [ ] **Step 4: Pass the partner list and link status to the session page**

In `features/gym/routes.py`, inside `session_detail`, immediately before its `render_template(...)` call for the LIVE (unfinished) branch, add:

```python
    # Everyone else with an account. Three people use this app; a picker is
    # the whole feature, and a friends list would be ceremony.
    partners = (AppUser.query
                .filter(AppUser.id != current_user_id())
                .order_by(AppUser.username)
                .all())
    shared_out = (SharedSession.query
                  .filter(SharedSession.leader_session_id == session_.id,
                          SharedSession.ended_at.is_(None))
                  .all())
    partner_status = [
        {'username': _username(link.follower_user_id),
         'accepted': link.accepted_at is not None}
        for link in shared_out
    ]
```

and pass into that render call:

```python
        partners=partners,
        partner_status=partner_status,
```

- [ ] **Step 5: Render the invite control**

In `templates/gym/session_detail.html`, immediately after the element that opens the session's `⋮` sheet content (search for the existing sheet that contains the "Übung hinzufügen" action and add this as a sibling block inside the same sheet), add:

```jinja
      {#- Three people use this app, so the picker IS the feature. The leader's
          session is never blocked on an answer: it started already, and the
          partner's is seeded from whatever the structure looks like when they
          say yes. -#}
      {% if partners %}
      <form method="post" action="{{ url_for('gym.gym_invite_partner', session_id=session.id) }}" class="field">
        <label class="field__label" for="invite-partner">Trainingspartner einladen</label>
        <select class="field__input" id="invite-partner" name="partner_id">
          {% for partner in partners %}
          <option value="{{ partner.id }}">{{ partner.username }}</option>
          {% endfor %}
        </select>
        <button type="submit" class="btn btn--ghost">Einladen</button>
      </form>
      {% endif %}
      {% for status in partner_status %}
      <p class="shared-status">
        {{ status.username }} {{ 'ist dabei' if status.accepted else 'wurde eingeladen' }}
      </p>
      {% endfor %}
```

- [ ] **Step 6: Pass pending invites to Heute**

In `features/gym/routes.py`, inside `gym_heute`, immediately before its `render_template(...)` call, add:

```python
    # Addressed to one person: an invite is only ever visible to its recipient.
    pending_invites = [
        {'shared_id': link.id,
         'leader_name': _username(link.leader_user_id),
         'session_name': (db.session.get(WorkoutSession, link.leader_session_id).name
                          or 'Workout')}
        for link in SharedSession.query.filter(
            SharedSession.follower_user_id == current_user_id(),
            SharedSession.accepted_at.is_(None),
            SharedSession.ended_at.is_(None)).all()
    ]
```

and pass it into the render call:

```python
        pending_invites=pending_invites,
```

- [ ] **Step 7: Render the pending-invite card**

In `templates/gym/heute.html`, immediately before the `<section class="sec" aria-labelledby="sec-routinen">` line, add:

```jinja
  {#- Someone is training right now and asked for you. Above the routines
      because it expires: the workout it belongs to is already running. -#}
  {% for invite in pending_invites %}
  <section class="sec">
    <div class="invite-card">
      <span class="invite-card__main stack">
        <span class="invite-card__who">{{ invite.leader_name }} trainiert</span>
        <span class="invite-card__what">{{ invite.session_name }}</span>
      </span>
      <a href="{{ url_for('gym.gym_shared_confirm', shared_id=invite.shared_id) }}" class="lead__go">
        Mitmachen
      </a>
    </div>
  </section>
  {% endfor %}
```

**Note:** `gym.gym_shared_confirm` is created in Task 5. Until then this template raises `BuildError`. Add the route stub now, in `features/gym/routes.py`, so Task 4's tests can render the page:

```python
@gym_bp.route('/gym/shared/<int:shared_id>/confirm')
@login_required
def gym_shared_confirm(shared_id):
    # Filled in by Task 5. The card on Heute links here, so the endpoint has to
    # resolve before that page can render at all.
    abort(404)
```

- [ ] **Step 8: Style it**

In `static/gym/gym.css`, next to the other `.lead` rules, add:

```css
/* An invite expires: the workout it belongs to is already running. Carries the
   same weight as the lead card because it is the same kind of decision. */
.invite-card {
  display: flex; align-items: center; gap: var(--sp-3);
  padding: var(--sp-3); border-radius: var(--r-card);
  box-shadow: inset 0 0 0 1px var(--stall-ink);
}
.invite-card__main { flex: 1; min-width: 0; }
.invite-card__who  { font-weight: 600; }
.invite-card__what { color: var(--dim); font-size: var(--t-meta); }

/* Quiet: whether your partner accepted is context, not an event. */
.shared-status { margin: var(--sp-2) 0 0; color: var(--dim); font-size: var(--t-meta); }
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_sharing.py -v -k invite`
Expected: PASS, 6 passed

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 10: Commit**

```bash
git add features/gym/routes.py templates/gym/session_detail.html templates/gym/heute.html static/gym/gym.css tests/test_gym_sharing.py
git commit -m "feat(gym): invite a training partner into a live workout"
```

---

### Task 5: The confirm screen

**Files:**
- Modify: `features/gym/routes.py`
- Create: `templates/gym/shared_confirm.html`
- Modify: `static/gym/gym.css`
- Test: `tests/test_gym_sharing.py`

**Interfaces:**
- Consumes: `matching.propose_matches` (Task 2); `sharing.reconcile_follower` (Task 3).
- Produces:
  - `GET /gym/shared/<int:shared_id>/confirm` (endpoint `gym.gym_shared_confirm`) — replaces the Task 4 stub.
  - `POST /gym/shared/<int:shared_id>/accept` (endpoint `gym.gym_shared_accept`), form fields `match_<leader_exercise_id>` each carrying either an exercise id or the literal `new`.
  - `POST /gym/shared/<int:shared_id>/decline` (endpoint `gym.gym_shared_decline`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gym_sharing.py`:

```python
def test_accepting_creates_the_followers_session_with_the_same_structure(leader_with_partner):
    from extensions import db
    from models import SharedSession, WorkoutSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})

    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id

    partner_client = _client_for(leader_with_partner['partner'])
    partner_client.post(f'/gym/shared/{shared_id}/accept',
                        data={f"match_{leader_with_partner['exercise']}": 'new'})

    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        assert shared.accepted_at is not None
        assert shared.follower_session_id is not None
        follower_session = db.session.get(WorkoutSession, shared.follower_session_id)
        assert follower_session.user_id == leader_with_partner['partner']
        assert [se.exercise.name for se in follower_session.exercises] == [
            'pytest invite bench']
        assert follower_session.exercises[0].exercise.user_id == (
            leader_with_partner['partner']), 'the follower was linked to the leader\'s row'


def test_the_followers_session_carries_no_template_link(leader_with_partner):
    """The routine belongs to the leader's catalogue. Pointing at it would be a
    cross-user reference, and would tell routine_memory() the follower has done
    a routine they have never owned."""
    from extensions import db
    from models import SharedSession, WorkoutSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id

    _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": 'new'})

    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        assert db.session.get(
            WorkoutSession, shared.follower_session_id).template_id is None


def test_accepting_seeds_from_the_leaders_current_structure(leader_with_partner):
    """Not from the routine as it stood at invite time -- exercises added while
    the partner was still walking to the gym are included."""
    from extensions import db
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})

    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id
        session_ = db.session.get(WorkoutSession, leader_with_partner['session'])
        late = Exercise(name='pytest invite late lift',
                        user_id=leader_with_partner['leader'])
        db.session.add(late)
        db.session.flush()
        session_.exercises.append(SessionExercise(exercise_id=late.id, position=2))
        db.session.commit()
        late_id = late.id

    _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": 'new',
              f'match_{late_id}': 'new'})

    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        follower_session = db.session.get(WorkoutSession, shared.follower_session_id)
        assert 'pytest invite late lift' in [
            se.exercise.name for se in follower_session.exercises]


def test_declining_removes_the_invite(leader_with_partner):
    from extensions import db
    from models import SharedSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id

    _client_for(leader_with_partner['partner']).post(f'/gym/shared/{shared_id}/decline')

    with flask_app.app_context():
        assert db.session.get(SharedSession, shared_id) is None


def test_a_partner_with_a_live_workout_is_refused(leader_with_partner):
    """One active session per person. Joining would mean abandoning theirs,
    which is not a decision to make on their behalf."""
    from extensions import db
    from models import SharedSession, WorkoutSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})

    own_session_id = None
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id
        own = WorkoutSession(name='pytest invite own workout',
                             started_at=dt.datetime.utcnow(),
                             user_id=leader_with_partner['partner'])
        db.session.add(own)
        db.session.commit()
        own_session_id = own.id

    html = _client_for(leader_with_partner['partner']).get(
        f'/gym/shared/{shared_id}/confirm').get_data(as_text=True)
    assert 'Du hast bereits ein laufendes Workout.' in html

    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        assert shared.accepted_at is None
        assert db.session.get(WorkoutSession, own_session_id) is not None, (
            'the partner\'s own workout was disturbed')


def test_an_invite_to_a_finished_workout_is_refused(leader_with_partner):
    from extensions import db
    from models import SharedSession, WorkoutSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id
        db.session.get(WorkoutSession,
                       leader_with_partner['session']).finished_at = dt.datetime.utcnow()
        db.session.commit()

    html = _client_for(leader_with_partner['partner']).get(
        f'/gym/shared/{shared_id}/confirm').get_data(as_text=True)
    assert 'Das Workout ist schon vorbei.' in html


def test_only_the_recipient_can_open_or_accept_an_invite(leader_with_partner):
    from extensions import db
    from models import SharedSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id

    leader_client = _client_for(leader_with_partner['leader'])
    assert leader_client.get(f'/gym/shared/{shared_id}/confirm').status_code == 404
    assert leader_client.post(f'/gym/shared/{shared_id}/accept',
                              data={}).status_code == 404

    with flask_app.app_context():
        assert db.session.get(SharedSession, shared_id).accepted_at is None


def test_an_exact_name_is_reused_rather_than_duplicated_on_accept(leader_with_partner):
    """The partner already owns 'pytest invite bench'. Accepting must link to
    it, not leave them with two."""
    from extensions import db
    from models import Exercise, SharedSession

    with flask_app.app_context():
        own_bench = Exercise(name='pytest invite bench',
                             user_id=leader_with_partner['partner'])
        db.session.add(own_bench)
        db.session.commit()
        own_bench_id = own_bench.id

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id

    _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": str(own_bench_id)})

    with flask_app.app_context():
        assert Exercise.query.filter_by(user_id=leader_with_partner['partner'],
                                        name='pytest invite bench').count() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_sharing.py -v -k "accepting or declining or refused or recipient or duplicated_on_accept or template_link"`
Expected: FAIL — the confirm stub aborts 404 and the accept/decline routes do not exist.

- [ ] **Step 3: Replace the stub with the real confirm route**

In `features/gym/routes.py`, replace the `gym_shared_confirm` stub from Task 4 entirely with:

```python
def _invite_for_recipient(shared_id):
    """The pending invite addressed to the caller, or 404.

    404 rather than 403 throughout, like every other ownership failure in the
    gym: a 403 would confirm the invite exists.
    """
    shared = db.session.get(SharedSession, shared_id)
    if shared is None or shared.follower_user_id != current_user_id():
        abort(404)
    if shared.accepted_at is not None or shared.ended_at is not None:
        abort(404)
    return shared


def _invite_refusal(shared):
    """Why this invite cannot be taken up, or None.

    Each state gets its own sentence. A generic failure here reads as the app
    being broken, when in fact all three are ordinary.
    """
    leader_session = db.session.get(WorkoutSession, shared.leader_session_id)
    if leader_session is None or leader_session.finished_at is not None:
        return 'Das Workout ist schon vorbei.'
    if _get_active_session() is not None:
        return 'Du hast bereits ein laufendes Workout.'
    return None


@gym_bp.route('/gym/shared/<int:shared_id>/confirm')
@login_required
def gym_shared_confirm(shared_id):
    """Match the leader's exercises against your own catalogue, once, before
    the workout starts.

    Confirmation belongs at the door rather than in the middle of a set --
    which is also why an exercise the leader adds LATER resolves silently
    (see sharing.follower_exercise_for).
    """
    shared = _invite_for_recipient(shared_id)
    refusal = _invite_refusal(shared)

    proposals = []
    if refusal is None:
        leader_session = db.session.get(WorkoutSession, shared.leader_session_id)
        leader_rows = sorted(leader_session.exercises, key=lambda se: se.position)
        # Exercise ids, in order, de-duplicated: an original and the substitute
        # that replaced it are two rows but at most two exercises to match.
        leader_exercises = []
        for se in leader_rows:
            if se.exercise_id not in [row.id for row in leader_exercises]:
                leader_exercises.append(se.exercise)
        catalogue = [(row.id, row.name) for row in my_exercises().all()]
        proposals = [
            dict(proposal, leader_exercise_id=exercise.id)
            for exercise, proposal in zip(
                leader_exercises,
                matching.propose_matches([e.name for e in leader_exercises], catalogue))
        ]

    return render_template(
        'gym/shared_confirm.html',
        shared=shared,
        leader_name=_username(shared.leader_user_id),
        refusal=refusal,
        proposals=proposals,
    )
```

Add to `features/gym/routes.py`'s imports:

```python
from . import matching
```

- [ ] **Step 4: Add the accept and decline routes**

In `features/gym/routes.py`, immediately after `gym_shared_confirm`, add:

```python
@gym_bp.route('/gym/shared/<int:shared_id>/accept', methods=['POST'])
@login_required
def gym_shared_accept(shared_id):
    """Create your own session and join.

    Seeded from the leader's structure AS IT STANDS NOW, not as it stood when
    the invite was sent: anything added while you walked to the gym is
    included. Your sets are seeded from YOUR history, which is why this runs
    here -- in your request -- and not inside reconciliation.
    """
    shared = _invite_for_recipient(shared_id)
    refusal = _invite_refusal(shared)
    if refusal is not None:
        flash(refusal, 'error')
        return redirect(url_for('gym.gym_heute'))

    leader_session = db.session.get(WorkoutSession, shared.leader_session_id)

    follower_session = WorkoutSession(
        # The name is copied once so the workout reads as the same one. It is
        # not synced afterwards: from here the session is theirs.
        name=leader_session.name,
        started_at=dt.datetime.utcnow(),
        user_id=current_user_id(),
        # Deliberately no template_id: the routine belongs to the leader's
        # catalogue, and claiming it would tell routine_memory() this lifter
        # has done a routine they have never owned.
        template_id=None,
    )
    db.session.add(follower_session)
    db.session.flush()

    # The confirmed matches, before any structure is built -- reconciliation
    # reads this map rather than guessing.
    for key, value in request.form.items():
        if not key.startswith('match_'):
            continue
        leader_exercise_id = _to_int(key[len('match_'):])
        if not leader_exercise_id:
            continue
        leader_exercise = db.session.get(Exercise, leader_exercise_id)
        if leader_exercise is None or leader_exercise.user_id != shared.leader_user_id:
            continue
        if value == 'new':
            chosen = Exercise(
                name=leader_exercise.name,
                muscle_group=leader_exercise.muscle_group,
                default_rest_seconds=leader_exercise.default_rest_seconds,
                user_id=current_user_id(),
            )
            db.session.add(chosen)
            db.session.flush()
            chosen_id = chosen.id
        else:
            # Attacker-chosen: without owned_exercise a lifter could map their
            # slot onto somebody else's row and log against its history.
            chosen_id = owned_exercise(_to_int(value)).id
        db.session.add(SharedSessionExercise(
            shared_session_id=shared.id,
            leader_exercise_id=leader_exercise_id,
            follower_exercise_id=chosen_id,
        ))

    shared.follower_session_id = follower_session.id
    shared.accepted_at = dt.datetime.utcnow()
    db.session.flush()

    sharing.reconcile_follower(shared)

    # Seed each slot from THIS lifter's history. Reconciliation cannot: it runs
    # in the leader's request, where a history lookup reads the wrong person.
    for row in follower_session.exercises:
        if not row.sets:
            row.sets.extend(_seeded_sets(follower_session, row.exercise_id, row.position))
    db.session.commit()

    return redirect(url_for('gym.session_detail', session_id=follower_session.id))


@gym_bp.route('/gym/shared/<int:shared_id>/decline', methods=['POST'])
@login_required
def gym_shared_decline(shared_id):
    """Declining is not an event. The card disappears and nobody is notified."""
    shared = _invite_for_recipient(shared_id)
    db.session.delete(shared)
    db.session.commit()
    return redirect(url_for('gym.gym_heute'))
```

- [ ] **Step 5: Write the confirm template**

Create `templates/gym/shared_confirm.html`:

```jinja
{% extends 'gym/_base.html' %}
{% block content %}
<section class="sec" aria-labelledby="sec-confirm">
  <div class="sec__head">
    <h2 class="label" id="sec-confirm">Mit {{ leader_name }} trainieren</h2>
  </div>

  {% if refusal %}
  <p class="empty">{{ refusal }}</p>
  <a class="btn btn--ghost" href="{{ url_for('gym.gym_heute') }}">Zurück</a>
  {% else %}
  {#- Exact matches are already resolved and say so. Only the genuinely
      ambiguous ones carry a decision, because asking seven times per shared
      workout would make the common path the annoying one. -#}
  <form method="post" action="{{ url_for('gym.gym_shared_accept', shared_id=shared.id) }}">
    {% for proposal in proposals %}
    <div class="field">
      <label class="field__label" for="match-{{ proposal.leader_exercise_id }}">
        {{ proposal.name }}
      </label>
      <select class="field__input" id="match-{{ proposal.leader_exercise_id }}"
              name="match_{{ proposal.leader_exercise_id }}">
        <option value="new" {{ 'selected' if not proposal.exact_id else '' }}>Neu anlegen</option>
        {% for candidate_id, candidate_name in proposal.candidates %}
        <option value="{{ candidate_id }}" {{ 'selected' if candidate_id == proposal.exact_id else '' }}>
          {{ candidate_name }}
        </option>
        {% endfor %}
      </select>
    </div>
    {% endfor %}
    <button type="submit" class="btn btn--go">Mitmachen</button>
  </form>

  <form method="post" action="{{ url_for('gym.gym_shared_decline', shared_id=shared.id) }}">
    <button type="submit" class="btn btn--ghost">Ablehnen</button>
  </form>
  {% endif %}
</section>
{% endblock %}
```

`_base.html` fills `{% block content %}`, matching every other gym page (see `templates/gym/uebungen.html`).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_sharing.py -v`
Expected: PASS, all sharing tests green.

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add features/gym/routes.py templates/gym/shared_confirm.html static/gym/gym.css tests/test_gym_sharing.py
git commit -m "feat(gym): confirm the exercise matches, then join the workout"
```

---

### Task 6: Wiring propagation into the routes

**Files:**
- Modify: `features/gym/routes.py`
- Test: `tests/test_gym_sharing.py`

**Interfaces:**
- Consumes: `sharing.propagate_structure`, `sharing.end_links_for` from Task 3.
- Produces: nothing new. Five structural routes and both finish paths now call into sharing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gym_sharing.py`:

```python
@pytest.fixture()
def joined_pair(leader_with_partner):
    """leader_with_partner, but the invite has been accepted through the real
    routes -- so the follower's session and exercise map are whatever the app
    actually builds."""
    from extensions import db
    from models import SharedSession

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id
    _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": 'new'})
    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        return dict(leader_with_partner, shared=shared_id,
                    follower_session=shared.follower_session_id)


def test_adding_an_exercise_propagates_through_the_route(joined_pair):
    from extensions import db
    from models import WorkoutSession

    _client_for(joined_pair['leader']).post(
        f"/gym/session/{joined_pair['session']}/exercises/add",
        data={'new_exercise_name': 'pytest invite fly'})

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, joined_pair['follower_session'])
        assert 'pytest invite fly' in [se.exercise.name for se in follower_session.exercises]


def test_reordering_propagates_through_the_route(joined_pair):
    from extensions import db
    from models import WorkoutSession

    leader_client = _client_for(joined_pair['leader'])
    leader_client.post(f"/gym/session/{joined_pair['session']}/exercises/add",
                       data={'new_exercise_name': 'pytest invite fly'})

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, joined_pair['session'])
        order = [se.id for se in sorted(leader_session.exercises,
                                        key=lambda se: se.position)][::-1]

    leader_client.post(f"/gym/session/{joined_pair['session']}/exercises/reorder",
                       json={'order': order})

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, joined_pair['follower_session'])
        ordered = sorted(follower_session.exercises, key=lambda se: se.position)
        assert [se.exercise.name for se in ordered] == [
            'pytest invite fly', 'pytest invite bench']


def test_deleting_an_exercise_propagates_through_the_route(joined_pair):
    from extensions import db
    from models import WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, joined_pair['session'])
        row_id = leader_session.exercises[0].id

    _client_for(joined_pair['leader']).post(f'/gym/session-exercise/{row_id}/delete')

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, joined_pair['follower_session'])
        assert list(follower_session.exercises) == []


def test_skipping_propagates_through_the_route(joined_pair):
    from extensions import db
    from models import WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, joined_pair['session'])
        row_id = leader_session.exercises[0].id

    _client_for(joined_pair['leader']).post(f'/gym/session-exercise/{row_id}/skip')

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, joined_pair['follower_session'])
        assert all(se.skipped for se in follower_session.exercises)


def test_logging_a_set_does_not_bump_the_followers_version(joined_pair):
    """Only structure travels. If logging bumped the version, the partner's
    page would re-render every time the leader ticked a set."""
    from extensions import db
    from models import SessionSet, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, joined_pair['session'])
        row = leader_session.exercises[0]
        row.sets.append(SessionSet(position=1, weight=60.0, reps=8, completed=False))
        db.session.commit()
        set_id = row.sets[0].id
        before = db.session.get(
            WorkoutSession, joined_pair['follower_session']).structure_version

    _client_for(joined_pair['leader']).post(f'/gym/set/{set_id}/toggle_complete')

    with flask_app.app_context():
        after = db.session.get(
            WorkoutSession, joined_pair['follower_session']).structure_version
        assert after == before


def test_the_leader_finishing_ends_the_link_and_leaves_the_follower_live(joined_pair):
    """A workout must never be cut short by someone else's."""
    from extensions import db
    from models import SharedSession, WorkoutSession

    _client_for(joined_pair['leader']).post(
        f"/gym/session/{joined_pair['session']}/finish")

    with flask_app.app_context():
        assert db.session.get(SharedSession, joined_pair['shared']).ended_at is not None
        follower_session = db.session.get(WorkoutSession, joined_pair['follower_session'])
        assert follower_session.finished_at is None, 'the follower\'s workout was ended too'


def test_nothing_propagates_after_the_link_ended(joined_pair):
    from extensions import db
    from models import WorkoutSession

    leader_client = _client_for(joined_pair['leader'])
    leader_client.post(f"/gym/session/{joined_pair['session']}/finish")
    leader_client.post(f"/gym/session/{joined_pair['session']}/exercises/add",
                       data={'new_exercise_name': 'pytest invite ghost'})

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, joined_pair['follower_session'])
        assert 'pytest invite ghost' not in [
            se.exercise.name for se in follower_session.exercises]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_sharing.py -v -k "through_the_route or ends_the_link or after_the_link"`
Expected: FAIL — the follower's session is unchanged, because no route calls `propagate_structure` yet.

- [ ] **Step 3: Call propagate_structure from the five structural routes**

In `features/gym/routes.py`, add `sharing.propagate_structure(...)` immediately before each route's `return redirect(...)`, passing that route's session:

1. `gym_add_session_exercise` — after `db.session.commit()` inside the `if exercise_id:` block, add `sharing.propagate_structure(session_)`.
2. `gym_replace_session_exercise` — before its final `return redirect(...)`, add `sharing.propagate_structure(session_exercise.session)`.
3. `gym_delete_session_exercise` — **two calls, and the order matters.** Capture the session at the top of the function (`session_ = session_exercise.session`, alongside the existing `session_id = session_exercise.session_id`). Then, **before `db.session.delete(session_exercise)`**, add:

```python
    # BEFORE the delete, not after: mirrors_id carries a database-level
    # ON DELETE SET NULL, so the moment this row is gone the database has
    # already erased the only marker saying which follower row mirrored it.
    # Reconciliation would have nothing left to key on, and a heuristic
    # recovery -- matching on exercise_id, say -- cannot tell an orphaned
    # mirror from a row the partner added on their own initiative, so it
    # would eventually delete their own work and the sets they logged on it.
    sharing.remove_mirrors_of(session_exercise)
```

and after the existing `db.session.commit()` add `sharing.propagate_structure(session_)` as the other four routes do.
4. `gym_toggle_skip_session_exercise` — before its final `return redirect(...)`, add `sharing.propagate_structure(session_)`.
5. `gym_reorder_session_exercises` — after `db.session.commit()`, add `sharing.propagate_structure(session_)`.

Each call is one line, placed after that route's own commit, so the leader's change is durable before it is carried across.

- [ ] **Step 4: End the link when either side finishes**

In `features/gym/routes.py`, inside `gym_finish_session`, immediately before its `db.session.commit()`, add:

```python
    # Whoever finishes first ends the sharing. The other trains on alone --
    # a workout must never be cut short by someone else's.
    sharing.end_links_for(session_)
```

Search `features/gym/routes.py` for every other assignment of `finished_at` on a session (`grep -n "finished_at = dt.datetime.utcnow()" features/gym/routes.py`) and add the same call before each one's commit. Report how many sites you found and changed.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_sharing.py -v`
Expected: PASS, all sharing tests green.

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add features/gym/routes.py tests/test_gym_sharing.py
git commit -m "feat(gym): carry structural changes to the partner as they happen"
```

---

### Task 7: The follower's page keeps up

**Files:**
- Modify: `features/gym/routes.py`
- Create: `templates/gym/_session_queue.html`
- Modify: `templates/gym/_session_live.html`
- Modify: `templates/gym/session_detail.html`
- Test: `tests/test_gym_sharing.py`

**Interfaces:**
- Consumes: `WorkoutSession.structure_version` (Task 1).
- Produces:
  - `GET /gym/session/<int:session_id>/sync.json` (endpoint `gym.gym_session_sync`) returning `{"version": int, "shared": bool}`.
  - `GET /gym/session/<int:session_id>/queue.html` (endpoint `gym.gym_session_queue`) returning the rendered queue only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gym_sharing.py`:

```python
def test_the_sync_endpoint_reports_the_structure_version(joined_pair):
    import json
    response = _client_for(joined_pair['partner']).get(
        f"/gym/session/{joined_pair['follower_session']}/sync.json")
    assert response.status_code == 200
    body = json.loads(response.get_data(as_text=True))
    assert 'version' in body and isinstance(body['version'], int)
    assert body['shared'] is True


def test_the_sync_version_rises_when_the_leader_changes_structure(joined_pair):
    import json
    partner_client = _client_for(joined_pair['partner'])
    before = json.loads(partner_client.get(
        f"/gym/session/{joined_pair['follower_session']}/sync.json"
    ).get_data(as_text=True))['version']

    _client_for(joined_pair['leader']).post(
        f"/gym/session/{joined_pair['session']}/exercises/add",
        data={'new_exercise_name': 'pytest invite raise'})

    after = json.loads(partner_client.get(
        f"/gym/session/{joined_pair['follower_session']}/sync.json"
    ).get_data(as_text=True))['version']
    assert after > before


def test_a_stranger_cannot_poll_someone_elses_session(joined_pair):
    assert _client_for(joined_pair['leader']).get(
        f"/gym/session/{joined_pair['follower_session']}/sync.json").status_code == 404
    assert _client_for(joined_pair['leader']).get(
        f"/gym/session/{joined_pair['follower_session']}/queue.html").status_code == 404


def test_the_queue_endpoint_renders_only_the_queue(joined_pair):
    html = _client_for(joined_pair['partner']).get(
        f"/gym/session/{joined_pair['follower_session']}/queue.html"
    ).get_data(as_text=True)
    assert 'queue' in html
    assert 'pytest invite bench' in html
    assert '<html' not in html.lower(), 'the queue endpoint returned a whole page'


def test_the_leader_cannot_read_the_followers_workout(joined_pair):
    """Structure travels; performance does not. Sharing must not have opened a
    door to the partner's numbers on any route that serves them."""
    leader_client = _client_for(joined_pair['leader'])
    follower_session = joined_pair['follower_session']
    for url in (f'/gym/session/{follower_session}',
                f'/gym/session/{follower_session}/sync.json',
                f'/gym/session/{follower_session}/queue.html',
                f'/gym/export?ids={follower_session}'):
        response = leader_client.get(url)
        assert response.status_code == 404 or (
            'pytest invite bench' not in response.get_data(as_text=True)), (
            f'{url} served the partner\'s workout to the leader')


def test_a_solo_session_reports_that_it_is_not_shared(leader_with_partner):
    import json
    body = json.loads(_client_for(leader_with_partner['leader']).get(
        f"/gym/session/{leader_with_partner['session']}/sync.json"
    ).get_data(as_text=True))
    assert body['shared'] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gym_sharing.py -v -k "sync or queue_endpoint or cannot_poll"`
Expected: FAIL — 404, the endpoints do not exist.

- [ ] **Step 3: Extract the queue into its own partial**

In `templates/gym/_session_live.html`, cut everything from the comment line beginning `{# The queue is the whole workout in order` through the **end of the file**, and paste it unchanged into a new file `templates/gym/_session_queue.html`.

In its place at the end of `templates/gym/_session_live.html`, put:

```jinja
  {#- Its own partial so a shared session can re-render just this when a
      training partner changes the structure -- without touching the panel,
      where a half-typed weight would be lost. -#}
  {% include 'gym/_session_queue.html' %}
```

- [ ] **Step 4: Add the two endpoints**

In `features/gym/routes.py`, immediately after `gym_finish_session`, add:

```python
@gym_bp.route('/gym/session/<int:session_id>/sync.json')
@login_required
def gym_session_sync(session_id):
    """What the follower's page polls.

    Reads the caller's OWN session. Propagation is a write, so by the time this
    is asked the change is already in their rows -- there is no cross-user read
    on this path at all.
    """
    session_ = owned_session(session_id)
    shared = SharedSession.query.filter(
        SharedSession.ended_at.is_(None),
        SharedSession.accepted_at.isnot(None),
        db.or_(SharedSession.leader_session_id == session_.id,
               SharedSession.follower_session_id == session_.id)).first()
    return jsonify({'version': session_.structure_version or 0,
                    'shared': shared is not None})


@gym_bp.route('/gym/session/<int:session_id>/queue.html')
@login_required
def gym_session_queue(session_id):
    """The queue alone, for the polling swap.

    Rendered from the same partial the page uses, so the two cannot drift.
    """
    session_ = owned_session(session_id)
    return render_template('gym/_session_queue.html', **_live_context(session_))
```

**Building `_live_context`.** Do this mechanically rather than by judgement:

1. Open `templates/gym/_session_queue.html` (created in Step 3) and list every Jinja variable it reads that is not defined inside the file itself by `{% set %}` or a loop. Read the whole file — the queue references `live_id` and the session's exercises at minimum, but take the list from the file, not from this plan.
2. In `session_detail`, find where each of those names is passed to `render_template`. They are all already computed there; you are moving, not writing.
3. Define `_live_context(session_)` as a module-level function in `features/gym/routes.py` returning a dict of exactly those names, moving the computation out of `session_detail`.
4. In `session_detail`'s live-branch render call, replace those individual keyword arguments with `**_live_context(session_)`.

If a name the queue needs turns out to depend on something only `session_detail` has (a form value, a query parameter), stop and report it as BLOCKED rather than duplicating the computation — one definition is the point of the extraction.

Confirm `jsonify` is imported in `routes.py`; if not, add it to the existing `from flask import ...` line.

- [ ] **Step 5: Poll from the live page**

In `templates/gym/session_detail.html`, inside the existing script block at the bottom of the live-session branch, add:

```javascript
// A shared workout only. Structure changes arrive as writes to this lifter's
// own session, so this asks about their own rows -- nothing here reads the
// partner's data. Paused while the page is hidden: a backgrounded phone in a
// gym should not be making requests.
(function () {
  var root = document.getElementById('session-root');
  if (!root || root.dataset.shared !== '1') { return; }
  var sessionId = root.dataset.sessionId;
  var known = parseInt(root.dataset.structureVersion || '0', 10);

  function poll() {
    if (document.hidden) { return; }
    fetch('/gym/session/' + sessionId + '/sync.json', {credentials: 'same-origin'})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || data.version === known) { return; }
        known = data.version;
        var open = document.querySelector('[data-se-id].is-now');
        var openId = open ? open.dataset.seId : null;
        return fetch('/gym/session/' + sessionId + '/queue.html',
                     {credentials: 'same-origin'})
          .then(function (r) { return r.ok ? r.text() : null; })
          .then(function (html) {
            if (html === null) { return; }
            var host = document.getElementById('queue');
            if (!host) { return; }
            host.outerHTML = html;
            // The panel is showing an exercise that no longer exists. There is
            // no honest way to keep it on screen, so start over -- this is the
            // one case a reload is right.
            if (openId && !document.querySelector('[data-se-id="' + openId + '"]')) {
              window.location.reload();
            }
          });
      })
      .catch(function () { /* a dropped poll is not worth telling anyone about */ });
  }

  setInterval(poll, 5000);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) { poll(); }
  });
})();
```

The queue partial's outermost element must be `<div class="queue" id="queue">` for `outerHTML` to swap cleanly — confirm this after Step 3 and adjust the selector if the id sits elsewhere.

Add the data attributes the script reads. In `templates/gym/session_detail.html`, find the outermost element of the live-session branch and give it:

```jinja
id="session-root"
data-session-id="{{ session.id }}"
data-shared="{{ '1' if session_is_shared else '0' }}"
data-structure-version="{{ session.structure_version or 0 }}"
```

and pass `session_is_shared` from `session_detail` by adding, before its live-branch `render_template(...)`:

```python
    session_is_shared = SharedSession.query.filter(
        SharedSession.ended_at.is_(None),
        SharedSession.accepted_at.isnot(None),
        db.or_(SharedSession.leader_session_id == session_.id,
               SharedSession.follower_session_id == session_.id)).first() is not None
```

and into the render call:

```python
        session_is_shared=session_is_shared,
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gym_sharing.py -v`
Expected: PASS, all sharing tests green.

Run: `python -m pytest tests/ -v`
Expected: PASS, no regressions. The queue extraction touches every live session page, so a failure here is a rendering regression, not a sharing one.

- [ ] **Step 7: Verify the page still renders for a solo session**

Run: `python -m pytest tests/test_gym_routes_smoke.py -v`
Expected: PASS. The queue moved into a partial; these are the tests that render real session pages.

- [ ] **Step 8: Commit**

```bash
git add features/gym/routes.py templates/gym/_session_queue.html templates/gym/_session_live.html templates/gym/session_detail.html tests/test_gym_sharing.py
git commit -m "feat(gym): keep a partner's queue current while they train"
```

---

## Deployment

Not a task. Merge to `main` and run the deploy script.

One migration, `e4a91c7d20f8`: two new tables plus two nullable/defaulted columns, no backfill. It cannot fail on existing data.

**The schema must land before the services restart.** `models.py` declares `structure_version` and `mirrors_id` unconditionally, so every `SessionExercise` and `WorkoutSession` SELECT issued by gunicorn or the notifier includes them. Confirm the deploy script runs `flask db upgrade` ahead of both restarts — the same ordering the per-user-exercises rollout established.

Nothing is retroactive and nothing changes for a solo workout: with no invite outstanding, `pending_invites` is empty, `active_links_led_by()` returns nothing, and the poll never starts.
