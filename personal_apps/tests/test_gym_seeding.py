"""The seeding pick: which past session pre-fills a slot.

Owner-decided rules (2026-08-11), each pinned here:

1. Fresh history wins, BEST first -- highest e1RM inside the rolling window,
   not the most recent.
2. Fatigue direction -- a result at the same or a later position outranks a
   fresher-slot result, because it was done more tired.
3. A layoff seeds the last thing you did, never your best.

Runs against the real local development database; every row created here is
deleted in the fixture's teardown.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def history_builder():
    """Yields (build, exercise_id): build(days_ago, position, sets,
    is_deload=False) creates one finished session containing the exercise.
    Everything created is torn down afterwards."""
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession

    created = {'sessions': [], 'exercise': None}
    with flask_app.app_context():
        exercise = Exercise(name='pytest seeding pick lift', user_id=_admin_id())
        db.session.add(exercise)
        db.session.commit()
        created['exercise'] = exercise.id

    def build(days_ago, position, sets, is_deload=False):
        with flask_app.app_context():
            started = dt.datetime.utcnow() - dt.timedelta(days=days_ago)
            session_ = WorkoutSession(
                name=f'pytest seeding {days_ago}d p{position}',
                started_at=started, finished_at=started + dt.timedelta(hours=1),
                is_deload=is_deload, user_id=_admin_id(),
            )
            se = SessionExercise(exercise_id=created['exercise'], position=position)
            se.sets = [
                SessionSet(position=j, weight=w, reps=r, completed=True)
                for j, (w, r) in enumerate(sets, start=1)
            ]
            session_.exercises.append(se)
            db.session.add(session_)
            db.session.commit()
            created['sessions'].append(session_.id)

    yield build, created

    with flask_app.app_context():
        for session_id in created['sessions']:
            doomed = db.session.get(WorkoutSession, session_id)
            if doomed is not None:
                doomed.resting_set_id = None
                db.session.commit()
                db.session.delete(doomed)
                db.session.commit()
        doomed = db.session.get(Exercise, created['exercise'])
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()


def _seed(exercise_id, position):
    from features.gym.seeding import _last_full_performance
    with flask_app.app_context():
        return _last_full_performance(exercise_id, position=position,
                                      user_id=_admin_id())


def test_a_stronger_later_slot_beats_the_same_slot(history_builder):
    """Rule 2, the owner's own example: you did it better in a LATER slot
    since -- you were already stronger while more tired, so that is the
    evidence this slot seeds from."""
    build, created = history_builder
    # The weaker same-slot session is the NEWER one, so a most-recent-first
    # rule would pick it -- the whole point is that best-fresh does not.
    build(days_ago=12, position=5, sets=[(70.0, 8)])
    build(days_ago=5, position=2, sets=[(60.0, 8)])
    seeded = _seed(created['exercise'], position=2)
    assert [s['weight'] for s in seeded] == [70.0]


def test_best_means_e1rm_not_top_weight(history_builder):
    """60x12 beats 62x6: comparing raw top weight would seed the six-rep
    session as the better one."""
    build, created = history_builder
    # The heavier-but-shallower session is the newer one on purpose: both a
    # most-recent rule and a top-weight rule would pick the 62x6.
    build(days_ago=10, position=2, sets=[(60.0, 12)])
    build(days_ago=5, position=2, sets=[(62.0, 6)])
    seeded = _seed(created['exercise'], position=2)
    assert [s['weight'] for s in seeded] == [60.0]
    assert [s['reps'] for s in seeded] == [12]


def test_a_fresher_slot_does_not_outrank_valid_evidence(history_builder):
    """Fatigue direction: slot 1 is fresher than slot 3, so its bigger number
    is NOT proof of what slot 3 can do. The slot-3 session wins even at a
    lower e1RM."""
    build, created = history_builder
    build(days_ago=5, position=1, sets=[(80.0, 6)])    # e1RM 96, but fresher
    build(days_ago=10, position=3, sets=[(75.0, 8)])   # e1RM 95, valid
    seeded = _seed(created['exercise'], position=3)
    assert [s['weight'] for s in seeded] == [75.0]


def test_fresher_slot_evidence_still_seeds_when_it_is_all_there_is(history_builder):
    """The preference is a preference, not a veto: with nothing fresh at or
    after the slot, a fresh earlier-slot session still beats falling back to
    stale history."""
    build, created = history_builder
    build(days_ago=40, position=3, sets=[(70.0, 8)])   # stale, right slot
    build(days_ago=5, position=1, sets=[(65.0, 8)])    # fresh, fresher slot
    seeded = _seed(created['exercise'], position=3)
    assert [s['weight'] for s in seeded] == [65.0]


def test_a_layoff_seeds_the_last_session_not_the_best(history_builder):
    """Rule 3: nothing inside the window -> the most recent session, however
    modest. Best-ever would hand a detrained body its all-time PR."""
    build, created = history_builder
    build(days_ago=40, position=2, sets=[(100.0, 8)])  # the old peak
    build(days_ago=35, position=2, sets=[(60.0, 8)])   # the last real session
    seeded = _seed(created['exercise'], position=2)
    assert [s['weight'] for s in seeded] == [60.0]


def test_a_fresh_deload_never_seeds(history_builder):
    """Deloads are excluded before any ranking happens -- a deliberately
    light week must not become next week's plan."""
    build, created = history_builder
    build(days_ago=3, position=2, sets=[(80.0, 10)], is_deload=True)
    build(days_ago=9, position=2, sets=[(70.0, 8)])
    seeded = _seed(created['exercise'], position=2)
    assert [s['weight'] for s in seeded] == [70.0]


def test_an_e1rm_tie_goes_to_the_newer_session(history_builder):
    build, created = history_builder
    build(days_ago=12, position=2, sets=[(60.0, 8), (60.0, 8)])
    build(days_ago=4, position=2, sets=[(60.0, 8)])
    seeded = _seed(created['exercise'], position=2)
    # One set, not two: the newer of the equals won.
    assert len(seeded) == 1


def test_the_whole_winning_session_seeds_in_order(history_builder):
    """The pick chooses a session; the seed then mirrors ALL of its completed
    sets in order, ramps included -- unchanged from before."""
    build, created = history_builder
    build(days_ago=5, position=2, sets=[(60.0, 10), (65.0, 8), (70.0, 6)])
    seeded = _seed(created['exercise'], position=2)
    assert [(s['weight'], s['reps']) for s in seeded] == [
        (60.0, 10), (65.0, 8), (70.0, 6)]
