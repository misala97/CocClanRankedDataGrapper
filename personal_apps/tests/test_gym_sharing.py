"""Shared live sessions: the link, the exercise map, and the one function
that writes into another user's session."""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import embedded_payload


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


def test_a_mid_workout_addition_seeds_the_followers_default_plan(linked_pair):
    """F4 (gym cold-start review): an exercise the leader adds mid-workout
    must not arrive on the follower's side as an empty slot -- that
    reproduces this feature's headline bug for the follower too, one
    confirmed set both creating and completing the plan. Neither side has
    ever performed this exercise, so the follower's mirrored row must get the
    same no-history default plan _seeded_sets hands every other empty slot."""
    from extensions import db
    from features.gym import sharing, stats
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        squat = Exercise(name='pytest shared mid workout squat', user_id=linked_pair['leader_user'])
        db.session.add(squat)
        db.session.flush()
        leader_session.exercises.append(
            SessionExercise(exercise_id=squat.id, position=2))
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        added = [se for se in follower_session.exercises
                 if se.exercise.name == 'pytest shared mid workout squat']
        assert len(added) == 1, 'the added exercise did not carry across'
        se = added[0]
        assert len(se.sets) == stats.DEFAULT_PLAN_SETS, (
            f'mid-workout addition arrived on the follower with {len(se.sets)} sets, '
            'not seeded like every other path that creates a SessionExercise')
        assert {s.weight for s in se.sets} == {stats.DEFAULT_PLAN_WEIGHT}
        assert {s.reps for s in se.sets} == {stats.DEFAULT_PLAN_REPS}
        assert {s.base_weight for s in se.sets} == {None}
        assert all(s.is_default_seeded for s in se.sets), (
            'default-seeded follower sets must carry the marker too, or a later '
            'deload on the follower\'s side could scale an invented number (F1)')


def test_a_mid_workout_addition_seeds_from_the_followers_own_history_not_the_leaders(linked_pair):
    """Reconciliation runs inside the LEADER's request. Seeding a newly
    created follower row must not default to current_user_id() there -- that
    would name the leader, and since the follower's own WorkoutSessions never
    carry the leader's user_id, the lookup would silently match nothing and
    always fall back to the default plan, even when the follower has real
    history for the exact same movement.

    Set up entirely independent of the linked_pair fixture's own bench
    mapping: the follower already owns 'pytest shared row lift' with real
    completed history at a weight the default plan could never produce by
    coincidence. The leader creates their OWN same-named exercise (a
    different id, same as linked_pair's own leader/follower bench pair) and
    adds it mid-workout -- follower_exercise_for matches it to the follower's
    existing row by name, exactly as it would for a real partner who happens
    to train the same lift.
    """
    import datetime as dt
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SessionSet, SharedSession, WorkoutSession

    made = {}
    try:
        with flask_app.app_context():
            follower_row_lift = Exercise(name='pytest shared row lift',
                                         user_id=linked_pair['follower_user'])
            db.session.add(follower_row_lift)
            db.session.flush()
            made['follower_row_lift'] = follower_row_lift.id

            past = WorkoutSession(
                name='pytest shared row lift history',
                started_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                finished_at=dt.datetime.utcnow() - dt.timedelta(days=2),
                user_id=linked_pair['follower_user'])
            past_se = SessionExercise(exercise_id=follower_row_lift.id, position=1)
            past_se.sets = [SessionSet(position=1, weight=55.0, reps=8, completed=True)]
            past.exercises.append(past_se)
            db.session.add(past)
            db.session.commit()
            made['past_session'] = past.id

            leader_row_lift = Exercise(name='pytest shared row lift',
                                       user_id=linked_pair['leader_user'])
            db.session.add(leader_row_lift)
            db.session.flush()

            leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
            leader_session.exercises.append(
                SessionExercise(exercise_id=leader_row_lift.id, position=2))
            db.session.commit()

            sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
            db.session.commit()

            follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
            added = [se for se in follower_session.exercises
                     if se.exercise_id == follower_row_lift.id]
            assert len(added) == 1, (
                'follower_exercise_for did not match the follower\'s existing '
                'same-named exercise')
            se = added[0]
            assert [(s.weight, s.reps) for s in se.sets] == [(55.0, 8)], (
                "the follower's mid-workout addition did not seed from THEIR OWN "
                f'history (got {[(s.weight, s.reps) for s in se.sets]})')
    finally:
        with flask_app.app_context():
            if made.get('past_session'):
                doomed = db.session.get(WorkoutSession, made['past_session'])
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            # leader_row_lift's mirrored follower SessionExercise cascades away
            # with follower_session in linked_pair's own teardown; both Exercise
            # rows are swept by that teardown's 'pytest shared%' name sweep.


def test_a_removed_exercise_disappears_from_the_followers_side(linked_pair):
    """Mirrors what the real delete route does: remove_mirrors_of() runs
    BEFORE the leader's row is deleted, while mirrors_id still resolves --
    the FK's ON DELETE SET NULL means that pointer is gone the instant the
    delete commits."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        for se in list(leader_session.exercises):
            sharing.remove_mirrors_of(se)
            db.session.delete(se)
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert list(follower_session.exercises) == []


def test_a_row_the_follower_added_themselves_survives(linked_pair):
    """The follower's session is otherwise fully theirs. Reconciliation must
    never reach a row they created, nor the sets they logged on it -- which a
    sweep keyed on exercise_id rather than row identity would do the moment
    the leader stopped doing that exercise."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SessionSet, SharedSession, WorkoutSession

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        own_row = SessionExercise(session_id=follower_session.id,
                                  exercise_id=linked_pair['follower_exercise'],
                                  position=2, mirrors_id=None)
        db.session.add(own_row)
        db.session.commit()
        own_row.sets.append(SessionSet(position=1, weight=40.0, reps=8, completed=True))
        db.session.commit()
        own_row_id = own_row.id
        own_set_id = own_row.sets[0].id

        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        sharing.remove_mirrors_of(leader_row)
        db.session.delete(leader_row)
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        assert db.session.get(SessionExercise, own_row_id) is not None, (
            'reconciliation deleted a row the follower added themselves')
        assert db.session.get(SessionSet, own_set_id) is not None, (
            'reconciliation deleted a set the follower logged themselves')


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
        assert len(list(follower_session.exercises)) == 1
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
    arbitrary session.

    Deviation from the brief: the brief's version of this test mutated
    leader_user_id but never gave the leader and follower sessions anything
    to actually disagree about, so the assertion held (returned False)
    whether or not the guard it targets was even present -- confirmed by the
    Step 5 teeth-proof, which passed with both `if ... return False` lines
    commented out. Adding a structural change on the leader's side, exactly
    like the sibling refuses_a_link_that_was_never_accepted and
    refuses_an_ended_link tests already do, makes the guard's absence
    observable: without it, the added exercise leaks into the follower.
    """
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        shared.leader_user_id = linked_pair['follower_user']
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


def test_reconciliation_refuses_when_the_link_disagrees_with_the_follower(linked_pair):
    """Sibling of the leader-side disagreement test above, but for the other
    half of the guard: `follower.user_id == shared.follower_user_id`. This
    stops a forged or corrupted link from naming a third party's session as
    the write target. The leader-side test only corrupts leader_user_id, so
    it never exercises this half; leaving it uncovered leaves the guard's
    other branch untested."""
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        shared.follower_user_id = linked_pair['leader_user']
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


# --- Hardening pass (security review before Task 6 wires this into routes) ---


def test_remove_mirrors_of_refuses_once_the_follower_has_finished(linked_pair):
    """Fix 1's concrete failure: the follower finishes their workout while
    the leader's delete request is in flight, before finished_at is stamped.
    Without this guard the leader's delete would remove an exercise -- and
    its logged sets -- from a workout the follower already completed."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SessionSet, WorkoutSession

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        follower_row = follower_session.exercises[0]
        follower_row.sets.append(SessionSet(position=1, weight=60.0, reps=5, completed=True))
        follower_session.finished_at = dt.datetime.utcnow()
        db.session.commit()
        follower_row_id = follower_row.id
        set_id = follower_row.sets[0].id

        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        sharing.remove_mirrors_of(leader_row)
        db.session.commit()

        assert db.session.get(SessionExercise, follower_row_id) is not None, (
            'remove_mirrors_of deleted a row from a workout the follower already finished')
        assert db.session.get(SessionSet, set_id) is not None, (
            'remove_mirrors_of deleted a set logged in a workout the follower already finished')


def test_remove_mirrors_of_refuses_when_the_link_disagrees_with_the_leader(linked_pair):
    """Sibling of reconcile_follower's ownership guard tests, for
    remove_mirrors_of: a corrupted or forged link must not become a way to
    delete rows out of an arbitrary session."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        shared.leader_user_id = linked_pair['follower_user']
        db.session.commit()

        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        sharing.remove_mirrors_of(leader_row)
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert len(list(follower_session.exercises)) == 1, (
            'remove_mirrors_of deleted a row despite the link disagreeing with the leader')


def test_remove_mirrors_of_refuses_when_the_link_disagrees_with_the_follower(linked_pair):
    """Other half of the ownership guard: a forged link must not name a
    third party's session as the delete target."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        shared.follower_user_id = linked_pair['leader_user']
        db.session.commit()

        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        sharing.remove_mirrors_of(leader_row)
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert len(list(follower_session.exercises)) == 1, (
            'remove_mirrors_of deleted a row despite the link disagreeing with the follower')


def test_remove_mirrors_of_raises_if_called_after_the_delete(linked_pair):
    """Fix 2: the ordering contract is 'before db.session.delete() is called
    at all', not merely 'before the commit'. Calling this after the delete
    would otherwise silently match zero rows once wired into a route -- this
    makes the misuse loud instead."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise

    with flask_app.app_context():
        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        db.session.delete(leader_row)
        with pytest.raises(RuntimeError):
            sharing.remove_mirrors_of(leader_row)
        db.session.rollback()


def test_remove_mirrors_of_cancels_the_followers_pending_push(linked_pair):
    """Fix 3: routes._cancel_pending_push's contract is that resting_set_id/
    rest_ends_at is never cleared without also cancelling the session's
    unsent pending push -- otherwise the notifier daemon buzzes the
    follower's phone for a rest timer on an exercise deleted out from under
    them."""
    from extensions import db
    from features.gym import sharing
    from models import PendingPush, SessionExercise, SessionSet, WorkoutSession

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        follower_row = follower_session.exercises[0]
        follower_row.sets.append(SessionSet(position=1, weight=40.0, reps=8, completed=True))
        db.session.commit()
        resting_set_id = follower_row.sets[0].id
        follower_session.resting_set_id = resting_set_id
        follower_session.rest_ends_at = dt.datetime.utcnow() + dt.timedelta(seconds=90)
        db.session.add(PendingPush(session_id=follower_session.id,
                                   fire_at=dt.datetime.utcnow() + dt.timedelta(seconds=90),
                                   sent=False))
        db.session.commit()

        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        sharing.remove_mirrors_of(leader_row)
        db.session.commit()

        assert PendingPush.query.filter_by(
            session_id=linked_pair['follower_session'], sent=False).count() == 0, (
            'a pending push survived the exercise it was scheduled for being removed')


def test_reconciles_own_removal_pass_also_clears_the_resting_set_id(linked_pair):
    """Fix 5's second half: reconcile_follower's own removal loop -- the one
    that cleans up a leader row that vanished 'some other way' than the
    normal remove_mirrors_of-then-delete route -- must apply the same
    resting_set_id/rest_ends_at/PendingPush cleanup remove_mirrors_of does.

    Reproducing that loop honestly is the hard part: in normal operation
    mirrors_id is already NULLed by the database's ON DELETE SET NULL the
    instant the leader row is deleted and flushed, so the row simply drops
    out of `mirrored` and this loop never sees it -- which is exactly why
    remove_mirrors_of exists. The one way the loop *can* still find a
    mirrors_id pointing at a genuinely-gone row is the same race the module's
    docstrings warn about: something reads (and caches) the follower's
    exercises before the leader row is deleted, then deletes and flushes
    without committing in between. flush() alone does not expire
    already-loaded attributes, so the follower row's in-memory mirrors_id
    stays stale even though the database has already nulled it -- while
    db.session.get() on the leader row correctly reports it gone. That is
    reproduced here deliberately, not accidentally.
    """
    from extensions import db
    from features.gym import sharing
    from models import PendingPush, SessionExercise, SessionSet, SharedSession, WorkoutSession

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        follower_row = follower_session.exercises[0]
        follower_row.sets.append(SessionSet(position=1, weight=45.0, reps=8, completed=True))
        db.session.commit()
        resting_set_id = follower_row.sets[0].id
        follower_session.resting_set_id = resting_set_id
        db.session.add(PendingPush(session_id=follower_session.id,
                                   fire_at=dt.datetime.utcnow(), sent=False))
        db.session.commit()

        # Force-load the follower's exercises (mirrors_id intact) before the
        # leader row is deleted.
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        list(follower_session.exercises)

        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        db.session.delete(leader_row)
        db.session.flush()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        refreshed = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert refreshed.resting_set_id is None, (
            'reconcile_follower\'s own removal pass left a dangling resting_set_id')
        assert PendingPush.query.filter_by(
            session_id=linked_pair['follower_session'], sent=False).count() == 0, (
            'reconcile_follower\'s own removal pass left an orphaned pending push')


def test_remove_mirrors_of_clears_the_followers_resting_set_id(linked_pair):
    """Fix 5: gym_workout_sessions.resting_set_id -> gym_session_sets.id has
    no ondelete, so it's RESTRICT -- a regression here is a 500 mid-workout
    for the follower, not a warning."""
    from extensions import db
    from features.gym import sharing
    from models import SessionExercise, SessionSet, WorkoutSession

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        follower_row = follower_session.exercises[0]
        follower_row.sets.append(SessionSet(position=1, weight=50.0, reps=5, completed=False))
        db.session.commit()
        resting_set_id = follower_row.sets[0].id
        follower_session.resting_set_id = resting_set_id
        db.session.commit()

        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        sharing.remove_mirrors_of(leader_row)
        db.session.commit()

        refreshed = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert refreshed.resting_set_id is None, (
            'the resting set pointer survived the row that held it being deleted')


def test_reconciling_one_link_leaves_a_second_links_mirror_alone(linked_pair):
    """Fix 4: follower_session_id carries no uniqueness constraint, so the
    same follower session could be the follower half of two active links at
    once. Reconciling one must not treat the other's mirror row as orphaned
    just because its mirrors_id isn't among the first link's own leader
    rows -- that would cascade-delete a row (and any logged sets) that a
    totally unrelated leader still owns."""
    from extensions import db
    from features.gym import sharing
    from models import (AppUser, Exercise, SessionExercise, SharedSession,
                        WorkoutSession)
    from werkzeug.security import generate_password_hash

    made = {}
    with flask_app.app_context():
        second_leader = AppUser(username='pytest sharing second leader',
                                password_hash=generate_password_hash('c'), is_admin=False)
        db.session.add(second_leader)
        db.session.flush()
        made['second_leader'] = second_leader.id

        second_leader_exercise = Exercise(name='pytest shared second leader row',
                                          user_id=second_leader.id)
        db.session.add(second_leader_exercise)
        db.session.flush()
        made['second_leader_exercise'] = second_leader_exercise.id

        second_leader_session = WorkoutSession(name='pytest second leader session',
                                               started_at=dt.datetime.utcnow(),
                                               user_id=second_leader.id)
        second_leader_row = SessionExercise(exercise_id=second_leader_exercise.id, position=1)
        second_leader_session.exercises.append(second_leader_row)
        db.session.add(second_leader_session)
        db.session.flush()
        made['second_leader_session'] = second_leader_session.id
        made['second_leader_row'] = second_leader_row.id

        second_shared = SharedSession(
            leader_session_id=second_leader_session.id,
            follower_session_id=linked_pair['follower_session'],
            leader_user_id=second_leader.id,
            follower_user_id=linked_pair['follower_user'],
            accepted_at=dt.datetime.utcnow())
        db.session.add(second_shared)
        db.session.flush()
        made['second_shared'] = second_shared.id

        second_mirror = SessionExercise(
            session_id=linked_pair['follower_session'],
            exercise_id=linked_pair['follower_exercise'],
            position=2, mirrors_id=second_leader_row.id)
        db.session.add(second_mirror)
        db.session.commit()
        made['second_mirror'] = second_mirror.id

    try:
        with flask_app.app_context():
            sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
            db.session.commit()

            survivor = db.session.get(SessionExercise, made['second_mirror'])
            assert survivor is not None, (
                "reconciling one link deleted a different link's mirror row")
            assert survivor.mirrors_id == made['second_leader_row']
    finally:
        with flask_app.app_context():
            doomed = db.session.get(SharedSession, made['second_shared'])
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()
            doomed = db.session.get(SessionExercise, made['second_mirror'])
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()
            doomed = db.session.get(WorkoutSession, made['second_leader_session'])
            if doomed is not None:
                doomed.resting_set_id = None
                db.session.commit()
                db.session.delete(doomed)
                db.session.commit()
            doomed = db.session.get(Exercise, made['second_leader_exercise'])
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()
            doomed = db.session.get(AppUser, made['second_leader'])
            if doomed is not None:
                db.session.delete(doomed)
            db.session.commit()


# --- The invite (Task 4) ---


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
        # Only present when a test (e.g. the template-link test) mutated the
        # yielded dict to add one; every session pointing at it is already
        # gone by now, and this must run before the AppUser it belongs to.
        if made.get('template'):
            from models import WorkoutTemplate
            doomed = db.session.get(WorkoutTemplate, made['template'])
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()
        for user_id in (made['leader'], made['partner']):
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


# --- The confirm screen: accept and decline (Task 5) ---


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
    a routine they have never owned.

    The leader's own session is given a real template_id here (the fixture
    leaves it NULL) so that copying it would actually be observable -- against
    a NULL leader template_id, this test could not tell the correct code
    (explicit template_id=None) apart from a regression that copies
    leader_session.template_id, since both leave the follower's template_id
    NULL either way.
    """
    from extensions import db
    from models import SharedSession, WorkoutSession, WorkoutTemplate

    with flask_app.app_context():
        template = WorkoutTemplate(name='pytest invite template',
                                   user_id=leader_with_partner['leader'])
        db.session.add(template)
        db.session.flush()
        leader_with_partner['template'] = template.id
        db.session.get(
            WorkoutSession, leader_with_partner['session']).template_id = template.id
        db.session.commit()

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


def test_a_partner_with_a_live_workout_is_refused_on_post_accept(leader_with_partner):
    """gym_shared_accept re-checks _invite_refusal itself rather than trusting
    that /confirm's GET already turned the follower away -- a refusal guarding
    only the GET would be trivially bypassable by posting straight to
    /accept. Sibling of test_a_partner_with_a_live_workout_is_refused, which
    only ever exercises the GET."""
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

    _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": 'new'})

    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        assert shared.accepted_at is None
        assert shared.follower_session_id is None
        assert db.session.get(WorkoutSession, own_session_id) is not None, (
            'the partner\'s own workout was disturbed')
        assert WorkoutSession.query.filter_by(
            user_id=leader_with_partner['partner']).count() == 1, (
            'a follower session was created despite the accept-time refusal')


def test_an_invite_to_a_finished_workout_is_refused_on_post_accept(leader_with_partner):
    """Sibling of test_an_invite_to_a_finished_workout_is_refused, which only
    ever exercises the GET -- the POST guard needs its own regression
    protection."""
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

    _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": 'new'})

    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        assert shared.accepted_at is None
        assert shared.follower_session_id is None
        assert WorkoutSession.query.filter_by(
            user_id=leader_with_partner['partner']).count() == 0, (
            'a follower session was created despite the accept-time refusal')


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


# --- The accept form's two security guards (review of 625cade) ---


def test_accept_rejects_a_match_value_naming_an_exercise_owned_by_a_third_party(leader_with_partner):
    """The value branch calls owned_exercise(...), so a follower cannot map a
    slot onto an exercise they do not own and log against its history."""
    from extensions import db
    from models import AppUser, Exercise, SharedSession
    from werkzeug.security import generate_password_hash

    third_party_id = None
    third_exercise_id = None
    try:
        with flask_app.app_context():
            third_party = AppUser(username='pytest invite third party',
                                  password_hash=generate_password_hash('c'), is_admin=False)
            db.session.add(third_party)
            db.session.flush()
            third_party_id = third_party.id
            third_exercise = Exercise(name='pytest invite third lift', user_id=third_party.id)
            db.session.add(third_exercise)
            db.session.commit()
            third_exercise_id = third_exercise.id

        _client_for(leader_with_partner['leader']).post(
            f"/gym/session/{leader_with_partner['session']}/invite",
            data={'partner_id': leader_with_partner['partner']})
        with flask_app.app_context():
            shared_id = SharedSession.query.filter_by(
                leader_session_id=leader_with_partner['session']).first().id

        response = _client_for(leader_with_partner['partner']).post(
            f'/gym/shared/{shared_id}/accept',
            data={f"match_{leader_with_partner['exercise']}": str(third_exercise_id)})
        assert response.status_code == 404

        with flask_app.app_context():
            shared = db.session.get(SharedSession, shared_id)
            assert shared.accepted_at is None
            assert shared.follower_session_id is None
    finally:
        with flask_app.app_context():
            if third_exercise_id:
                doomed = db.session.get(Exercise, third_exercise_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if third_party_id:
                doomed = db.session.get(AppUser, third_party_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_accept_skips_a_match_key_naming_an_exercise_the_leader_does_not_own(leader_with_partner):
    """The key branch: any leader_exercise_id whose exercise turns out not to
    really belong to the leader is skipped (`leader_exercise.user_id !=
    shared.leader_user_id` -> continue) rather than treated as a legitimate
    slot to fill. Posted alongside one legitimate key so the forged one's
    absence is what distinguishes pass from fail, not the whole request
    failing."""
    from extensions import db
    from models import Exercise, SharedSession, SharedSessionExercise

    with flask_app.app_context():
        forged = Exercise(name='pytest invite forged lift',
                          user_id=leader_with_partner['partner'])
        db.session.add(forged)
        db.session.commit()
        forged_id = forged.id

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id

    _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": 'new',
              f"match_{forged_id}": 'new'})

    with flask_app.app_context():
        shared = db.session.get(SharedSession, shared_id)
        assert shared.accepted_at is not None, 'the legitimate half of the post must still go through'
        mapped_leader_ids = {row.leader_exercise_id for row in
                             SharedSessionExercise.query.filter_by(shared_session_id=shared_id).all()}
        assert leader_with_partner['exercise'] in mapped_leader_ids, (
            'the legitimate match was not created')
        assert forged_id not in mapped_leader_ids, (
            'a match key naming an exercise the leader does not own produced a row')


# --- Fix 5: "Neu anlegen" must not 500 on a name the follower already owns ---


def test_accepting_with_new_reuses_an_owned_exercise_of_the_same_name(leader_with_partner):
    """A follower who overrides an auto-selected exact match back to 'Neu
    anlegen' for a name they already own must reuse the existing row, not hit
    uq_gym_exercises_user_id_name as an unhandled IntegrityError 500 -- same
    find-or-create pattern gym_replace_session_exercise's new_name branch
    already uses."""
    from extensions import db
    from models import Exercise, SharedSession, WorkoutSession

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

    response = _client_for(leader_with_partner['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{leader_with_partner['exercise']}": 'new'})
    assert response.status_code == 302, (
        'accepting with "Neu anlegen" on an already-owned name must not 500')

    with flask_app.app_context():
        assert Exercise.query.filter_by(user_id=leader_with_partner['partner'],
                                        name='pytest invite bench').count() == 1, (
            'the duplicate-name guard left the follower with two exercises')
        shared = db.session.get(SharedSession, shared_id)
        follower_session = db.session.get(WorkoutSession, shared.follower_session_id)
        assert follower_session.exercises[0].exercise_id == own_bench_id, (
            'the existing owned exercise was not reused')


# --- Wiring propagation into the routes (Task 6) ---


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


def test_deleting_a_finished_shared_session_clears_the_link_too(joined_pair):
    """Step 4b: SharedSession.leader_session_id/follower_session_id are plain
    FKs with no ondelete. Deleting a finished workout that was ever shared
    must clear both halves of any link it took part in first, or the FK
    constraint 500s."""
    from extensions import db
    from models import SharedSession, WorkoutSession

    leader_client = _client_for(joined_pair['leader'])
    leader_client.post(f"/gym/session/{joined_pair['session']}/finish")

    response = leader_client.post(f"/gym/session/{joined_pair['session']}/delete")
    assert response.status_code == 302, 'deleting a shared, finished session must not 500'

    with flask_app.app_context():
        assert db.session.get(WorkoutSession, joined_pair['session']) is None, (
            'the session was not deleted')
        assert db.session.get(SharedSession, joined_pair['shared']) is None, (
            'the link naming the deleted session survived it')


def test_a_stale_leader_session_auto_finishing_also_ends_the_link(joined_pair):
    """A second, differently-spelled site that stamps finished_at:
    _get_active_session() auto-finishes a session left open past
    STALE_SESSION_TIMEOUT, computing `started_at + STALE_SESSION_TIMEOUT`
    rather than `dt.datetime.utcnow()` -- so the brief's suggested
    `grep "finished_at = dt.datetime.utcnow()"` does not find it. Going
    stale ends the workout exactly as explicitly finishing it does, so it
    must end the link the same way, or a link tied to a session that quietly
    went stale is left dangling forever (accepted, never ended)."""
    from extensions import db
    from models import STALE_SESSION_TIMEOUT, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, joined_pair['session'])
        leader_session.started_at = (
            dt.datetime.utcnow() - STALE_SESSION_TIMEOUT - dt.timedelta(minutes=1))
        db.session.commit()

    # Any page load for the leader runs _get_active_session() via the nav
    # bar's context processor.
    _client_for(joined_pair['leader']).get('/gym')

    with flask_app.app_context():
        assert db.session.get(SharedSession, joined_pair['shared']).ended_at is not None, (
            'a session going stale did not end its link')
        follower_session = db.session.get(WorkoutSession, joined_pair['follower_session'])
        assert follower_session.finished_at is None, (
            'the follower\'s workout was ended too')


# --- The follower's page keeps up (Task 7) ---


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


# --- Final whole-branch review fixes ---------------------------------------


# --- Fix 1 / test gap 1: substitute propagation had zero coverage ----------


def test_a_leader_side_replace_propagates_with_the_substitute_translated(linked_pair):
    """Test gap 1a: substitute propagation is one of four behaviours the spec
    requires to propagate, and had no coverage anywhere before this."""
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        incline = Exercise(name='pytest shared incline', user_id=linked_pair['leader_user'])
        db.session.add(incline)
        db.session.flush()
        substitute = SessionExercise(session_id=leader_session.id, exercise_id=incline.id,
                                     position=leader_row.position, replaces_id=leader_row.id)
        db.session.add(substitute)
        db.session.commit()
        substitute_id = substitute.id

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        by_mirror = {se.mirrors_id: se for se in follower_session.exercises}
        follower_original = by_mirror[leader_row.id]
        follower_substitute = by_mirror[substitute_id]
        assert follower_substitute.exercise.name == 'pytest shared incline'
        assert follower_substitute.replaces_id == follower_original.id, (
            "the substitute must point at the FOLLOWER's counterpart of the original, "
            "not at the leader's row id")


def test_both_partners_swapping_the_same_exercise_does_not_500(linked_pair):
    """Fix 1 / test gap 1b (CRITICAL, teeth-proofed): SessionExercise.replaces_id
    carries a TABLE-WIDE unique constraint, not one scoped to a session. The
    follower swaps their mirrored row first -- a self-made substitute with
    mirrors_id IS NULL, invisible to reconciliation's `mirrored` map -- then
    the leader swaps theirs too and propagates. Before the fix, reconciliation
    assigned the leader's substitute's follower-side replaces_id without
    checking whether the follower's own substitute already claimed that same
    slot, colliding on the unique index: an unhandled IntegrityError on
    db.session.commit() below, 500ing every subsequent structural action by
    the LEADER even though their own change had already committed.

    Teeth-proof: with the `if wanted is not None: claimed_by_other = ...`
    guard in sharing.py's substitute pass commented out, this test fails with
    sqlalchemy.exc.IntegrityError on the commit below. Restored, it passes.
    """
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        follower_original = follower_session.exercises[0]
        follower_sub_exercise = Exercise(name='pytest shared follower swap',
                                         user_id=linked_pair['follower_user'])
        db.session.add(follower_sub_exercise)
        db.session.flush()
        follower_substitute = SessionExercise(
            session_id=follower_session.id, exercise_id=follower_sub_exercise.id,
            position=follower_original.position, replaces_id=follower_original.id)
        db.session.add(follower_substitute)
        db.session.commit()
        follower_original_id = follower_original.id
        follower_substitute_id = follower_substitute.id

        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        leader_row = db.session.get(SessionExercise, linked_pair['leader_row'])
        leader_sub_exercise = Exercise(name='pytest shared leader swap',
                                       user_id=linked_pair['leader_user'])
        db.session.add(leader_sub_exercise)
        db.session.flush()
        leader_substitute = SessionExercise(
            session_id=leader_session.id, exercise_id=leader_sub_exercise.id,
            position=leader_row.position, replaces_id=leader_row.id)
        db.session.add(leader_substitute)
        db.session.commit()
        leader_substitute_id = leader_substitute.id

        # This is the line that raised IntegrityError pre-fix -- reconciliation
        # itself, called and committed directly, exactly as propagate_structure
        # does inside the leader's request (bypassing Fix 2's try/except, which
        # would otherwise mask the very collision this test exists to prove).
        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        refreshed_follower_substitute = db.session.get(SessionExercise, follower_substitute_id)
        assert refreshed_follower_substitute.replaces_id == follower_original_id, (
            "the follower's own swap must keep winning for their own session")
        leader_mirror = next(se for se in follower_session.exercises
                             if se.mirrors_id == leader_substitute_id)
        assert leader_mirror.replaces_id is None, (
            "colliding with the follower's own substitute must leave this row "
            "unlinked rather than erroring or overwriting their swap")


# --- Test gap 2: only the leader-finishes direction was tested for ---------
# --- end_links_for -----------------------------------------------------


def test_the_follower_finishing_ends_the_link_and_leaves_the_leader_live(joined_pair):
    """Sibling of test_the_leader_finishing_ends_the_link_and_leaves_the_follower_live:
    gym_finish_session calls sharing.end_links_for(session_) regardless of
    which side of the link the finishing session is on, but only the
    leader-finishes direction had a test before this."""
    from extensions import db
    from models import SharedSession, WorkoutSession

    _client_for(joined_pair['partner']).post(
        f"/gym/session/{joined_pair['follower_session']}/finish")

    with flask_app.app_context():
        assert db.session.get(SharedSession, joined_pair['shared']).ended_at is not None
        leader_session = db.session.get(WorkoutSession, joined_pair['session'])
        assert leader_session.finished_at is None, "the leader's workout was ended too"


# --- Test gap 3: negative tests for the rest of what must never propagate --


def test_rest_seconds_does_not_propagate(linked_pair):
    """Among the seven things the spec says must never propagate, set count
    and weight/reps already had negative tests; rest_seconds did not.
    Reconciliation already does the right thing -- a newly mirrored row seeds
    rest_seconds from the FOLLOWER's own exercise default, never from the
    leader's per-session override -- so this pins existing correct behaviour."""
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SessionExercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_curl = Exercise(name='pytest shared curl', user_id=linked_pair['leader_user'],
                               default_rest_seconds=200)
        follower_curl = Exercise(name='pytest shared curl', user_id=linked_pair['follower_user'],
                                 default_rest_seconds=45)
        db.session.add_all([leader_curl, follower_curl])
        db.session.flush()

        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        leader_session.exercises.append(
            SessionExercise(exercise_id=leader_curl.id, position=2, rest_seconds=999))
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_session = db.session.get(WorkoutSession, linked_pair['follower_session'])
        new_row = next(se for se in follower_session.exercises if se.position == 2)
        assert new_row.exercise_id == follower_curl.id, (
            'the exact name-match should reuse the existing follower exercise')
        assert new_row.rest_seconds == 45, (
            "a newly mirrored row must seed rest_seconds from the FOLLOWER's own default")
        assert new_row.rest_seconds != 999, (
            "the leader's per-session rest override propagated to the follower")


def test_is_deload_and_deload_pct_do_not_propagate(linked_pair):
    """A deliberately light session is a decision about your own body, not
    something a training partner opts you into."""
    from extensions import db
    from features.gym import sharing
    from models import SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        leader_session.is_deload = True
        leader_session.deload_pct = 60
        db.session.commit()

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_after = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert follower_after.is_deload is False, 'a deload flag propagated to the follower'
        assert follower_after.deload_pct is None, 'a deload percentage propagated to the follower'


def test_the_session_name_does_not_propagate(linked_pair):
    """The name is copied once, at accept time, from whichever structure
    existed then -- never synced afterwards. From accept onward the session
    reads as theirs."""
    from extensions import db
    from features.gym import sharing
    from models import SharedSession, WorkoutSession

    with flask_app.app_context():
        leader_session = db.session.get(WorkoutSession, linked_pair['leader_session'])
        leader_session.name = 'pytest shared renamed leader workout'
        db.session.commit()
        follower_before_name = db.session.get(
            WorkoutSession, linked_pair['follower_session']).name

        sharing.reconcile_follower(db.session.get(SharedSession, linked_pair['shared']))
        db.session.commit()

        follower_after = db.session.get(WorkoutSession, linked_pair['follower_session'])
        assert follower_after.name == follower_before_name
        assert follower_after.name != 'pytest shared renamed leader workout'


# --- Fix 2: propagate_structure isolates a follower-side failure -----------


def test_propagate_structure_survives_a_follower_side_integrity_error(joined_pair, monkeypatch):
    """Any constraint violation originating in the FOLLOWER's data must
    degrade to 'the partner is out of sync until the next change', never a
    crash in the LEADER's request -- whose own change already committed
    durably before propagate_structure was ever called. Forces the failure
    directly (reconcile_follower is patched to raise) rather than relying on
    a specific collision, since Fix 1 already closes the concrete one this
    guard was written for."""
    from extensions import db
    from features.gym import sharing
    from models import WorkoutSession
    from sqlalchemy.exc import IntegrityError

    def boom(shared):
        raise IntegrityError('statement', {}, Exception('pytest forced collision'))

    monkeypatch.setattr(sharing, 'reconcile_follower', boom)

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, joined_pair['session'])
        sharing.propagate_structure(session_)  # must not raise
        db.session.rollback()  # nothing pending; matches the module's own rollback


# --- Fix 3: an exercise referenced only by a spent link's map ---------------


def test_deleting_an_exercise_referenced_only_by_a_shared_map_row_does_not_500(linked_pair):
    """Reproduces the map-with-no-SessionExercise state directly: a
    SharedSessionExercise row whose follower_exercise_id names an exercise no
    SessionExercise ever pointed to (e.g. the leader removed their side of the
    match between /confirm and /accept). gym_delete_exercise's in-use check
    only looks at session_exercises/template_exercises, so before the
    ondelete='CASCADE' migration this hit an unhandled IntegrityError instead
    of the route's existing friendly refusal."""
    from extensions import db
    from models import Exercise, SharedSessionExercise

    with flask_app.app_context():
        # A leader exercise NOT already mapped by the linked_pair fixture --
        # uq_gym_shared_session_exercises_link_leader is (shared_session_id,
        # leader_exercise_id), and the fixture already maps leader_exercise.
        vanished = Exercise(name='pytest shared vanished lift', user_id=linked_pair['leader_user'])
        orphan = Exercise(name='pytest shared orphaned lift', user_id=linked_pair['follower_user'])
        db.session.add_all([vanished, orphan])
        db.session.flush()
        db.session.add(SharedSessionExercise(
            shared_session_id=linked_pair['shared'],
            leader_exercise_id=vanished.id,
            follower_exercise_id=orphan.id))
        db.session.commit()
        orphan_id = orphan.id
        # Not referenced by any SessionExercise or TemplateExercise -- only by
        # the map row just added.
        assert orphan.session_exercises == []
        assert orphan.template_exercises == []

    response = _client_for(linked_pair['follower_user']).post(
        f'/gym/exercises/{orphan_id}/delete')
    assert response.status_code == 302, 'the delete must not 500'

    with flask_app.app_context():
        assert db.session.get(Exercise, orphan_id) is None, (
            'the exercise was not actually deleted')
        assert SharedSessionExercise.query.filter_by(follower_exercise_id=orphan_id).count() == 0, (
            "the spent map row must cascade away with the exercise it named")


# --- Fix 5: re-inviting after a link ended (or while still pending) --------


def test_reinviting_after_the_link_ended_gives_an_honest_message(joined_pair):
    """After the follower finishes first, ended_at is stamped and the leader's
    partner_status empties, but uq_gym_shared_sessions_leader_session_follower
    means a genuine retry can never work -- re-inviting must say so rather
    than flash success while creating nothing and sending no push."""
    from extensions import db
    from models import SharedSession

    _client_for(joined_pair['partner']).post(
        f"/gym/session/{joined_pair['follower_session']}/finish")

    response = _client_for(joined_pair['leader']).post(
        f"/gym/session/{joined_pair['session']}/invite",
        data={'partner_id': joined_pair['partner']}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert 'wurde eingeladen' not in html, (
        'a re-invite after the link ended must not claim success')
    assert 'bereits beendet' in html

    with flask_app.app_context():
        assert SharedSession.query.filter_by(
            leader_session_id=joined_pair['session']).count() == 1, (
            'no second invite row should have been created')


def test_reinviting_a_still_pending_invite_gives_an_honest_message(leader_with_partner):
    """The other non-None branch: an invite that exists but is neither
    accepted nor ended yet."""
    from extensions import db
    from models import SharedSession

    leader_client = _client_for(leader_with_partner['leader'])
    leader_client.post(f"/gym/session/{leader_with_partner['session']}/invite",
                       data={'partner_id': leader_with_partner['partner']})

    response = leader_client.post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert 'ist bereits eingeladen' in html

    with flask_app.app_context():
        assert SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).count() == 1


# --- Fix 7: is_unilateral must travel with the exercise's name -------------


def test_follower_exercise_for_copies_is_unilateral(linked_pair):
    from extensions import db
    from features.gym import sharing
    from models import Exercise, SharedSession

    with flask_app.app_context():
        shared = db.session.get(SharedSession, linked_pair['shared'])
        one_arm_row = Exercise(name='pytest shared one arm row',
                               user_id=linked_pair['leader_user'], is_unilateral=True)
        db.session.add(one_arm_row)
        db.session.flush()

        resolved_id = sharing.follower_exercise_for(shared, one_arm_row.id)
        db.session.commit()

        created = db.session.get(Exercise, resolved_id)
        assert created.is_unilateral is True, (
            'unilaterality is a property of the movement and must travel with the name, '
            'unlike weight_increment')


def test_accepting_with_new_copies_is_unilateral(leader_with_partner):
    from extensions import db
    from models import Exercise, SharedSession, WorkoutSession

    with flask_app.app_context():
        bench = db.session.get(Exercise, leader_with_partner['exercise'])
        bench.is_unilateral = True
        db.session.commit()

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
        follower_session = db.session.get(WorkoutSession, shared.follower_session_id)
        assert follower_session.exercises[0].exercise.is_unilateral is True, (
            "a follower joining a workout with a unilateral lift must not silently "
            "get a bilateral copy")


# --- Fix 6b: only the follower half of a live link should poll -------------


def test_the_leader_side_is_not_marked_shared_for_polling(joined_pair):
    """session_is_shared gates the polling script in session_detail.html. The
    leader's structure_version is never bumped by anything (only
    reconcile_follower bumps it, and only on the follower's session), so a
    leader polling sync.json every 5s would be pure waste."""
    html = _client_for(joined_pair['leader']).get(
        f"/gym/session/{joined_pair['session']}").get_data(as_text=True)
    assert embedded_payload(html)['session_is_shared'] is False,         "the leader's own session must not be marked shared"


def test_the_follower_side_is_marked_shared_for_polling(joined_pair):
    html = _client_for(joined_pair['partner']).get(
        f"/gym/session/{joined_pair['follower_session']}").get_data(as_text=True)
    assert embedded_payload(html)['session_is_shared'] is True,         "the follower's session must be marked shared"
