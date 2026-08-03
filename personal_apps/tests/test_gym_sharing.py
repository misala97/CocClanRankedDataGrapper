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
