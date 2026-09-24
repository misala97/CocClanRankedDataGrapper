"""How a workout ends (walkthrough D5: G-080, G-010, G-023, G-086, G-124).

- Finishing deletes what was never lifted, after storing how many sets the
  workout held (planned_sets, which the debrief's comparison needs: D10).
- A workout with nothing lifted is never filed: it can only be discarded.
- An abandoned workout ends three hours after its LAST set, at that set, marked
  auto_finished -- or is discarded when nothing in it counts.

Runs against the local development database with a throwaway lifter, so the
"one running workout" lookup can only ever find this file's rows.
"""
import datetime as dt
from urllib.parse import urlsplit

import pytest
from flask import session as flask_session
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from models import (
    STALE_SESSION_TIMEOUT, AppUser, Exercise, ExerciseSettings, LifterSettings, SessionExercise,
    SessionSet, SharedSession, WorkoutSession,
)


class Lifter:
    """A fresh user with workouts built to order; everything is deleted
    afterwards, whatever the test does."""

    def __init__(self):
        with flask_app.app_context():
            user = AppUser(username='pytest b4 lifter',
                           password_hash=generate_password_hash('x'), is_admin=False)
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id
        self.exercise_ids = []
        self.partner_ids = []
        self.now = dt.datetime.utcnow().replace(microsecond=0)

    def partner(self):
        """A second throwaway user, deleted with the first."""
        with flask_app.app_context():
            user = AppUser(username=f'pytest b4 partner {len(self.partner_ids)}',
                           password_hash=generate_password_hash('x'), is_admin=False)
            db.session.add(user)
            db.session.commit()
            self.partner_ids.append(user.id)
            return user.id

    def client(self, user_id=None):
        flask_app.config['TESTING'] = True
        test_client = flask_app.test_client()
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = user_id or self.user_id
        return test_client

    def exercise(self, name):
        exercise = Exercise(name=f'pytest b4 {name}', muscle_group='Brust')
        db.session.add(exercise)
        db.session.flush()
        self.exercise_ids.append(exercise.id)
        return exercise

    def workout(self, started_ago, user_id=None):
        workout = WorkoutSession(name='pytest b4', user_id=user_id or self.user_id,
                                 started_at=self.now - started_ago)
        db.session.add(workout)
        db.session.flush()
        return workout

    def row(self, workout, exercise, position, done=(), ticked_empty=0, open_=0,
            skipped=False, replaces=None, done_ago=None):
        """`done`: (weight, reps) pairs, ticked `done_ago` (a list of
        timedeltas, one per set) before now -- unstamped when None."""
        row = SessionExercise(session_id=workout.id, exercise_id=exercise.id, position=position,
                              skipped=skipped,
                              replaces_id=replaces.id if replaces is not None else None)
        db.session.add(row)
        db.session.flush()
        number = 0
        for index, (weight, reps) in enumerate(done):
            number += 1
            stamp = self.now - done_ago[index] if done_ago is not None else None
            db.session.add(SessionSet(session_exercise_id=row.id, position=number, weight=weight,
                                      reps=reps, completed=True, completed_at=stamp))
        for _ in range(ticked_empty):
            number += 1
            db.session.add(SessionSet(session_exercise_id=row.id, position=number, weight=40.0,
                                      reps=0, completed=True, completed_at=self.now))
        for _ in range(open_):
            number += 1
            db.session.add(SessionSet(session_exercise_id=row.id, position=number, weight=40.0,
                                      reps=8, completed=False))
        db.session.flush()
        return row

    def delete(self):
        with flask_app.app_context():
            user_ids = [self.user_id, *self.partner_ids]
            SharedSession.query.filter(db.or_(
                SharedSession.leader_user_id.in_(user_ids),
                SharedSession.follower_user_id.in_(user_ids))).delete(synchronize_session=False)
            db.session.commit()
            for workout in WorkoutSession.query.filter(WorkoutSession.user_id.in_(user_ids)).all():
                workout.resting_set_id = None
                db.session.commit()
                db.session.delete(workout)
                db.session.commit()
            for model in (ExerciseSettings, LifterSettings):
                model.query.filter(model.user_id.in_(user_ids)).delete(synchronize_session=False)
            for exercise_id in self.exercise_ids:
                exercise = db.session.get(Exercise, exercise_id)
                if exercise is not None:
                    db.session.delete(exercise)
            db.session.commit()
            for user_id in user_ids:
                user = db.session.get(AppUser, user_id)
                if user is not None:
                    db.session.delete(user)
                    db.session.commit()


@pytest.fixture()
def lifter():
    made = Lifter()
    try:
        yield made
    finally:
        made.delete()


def _sets(workout_id):
    """Every set left in the workout as (row position, reps, completed)."""
    with flask_app.app_context():
        workout = db.session.get(WorkoutSession, workout_id)
        return sorted((se.position, s.reps, s.completed)
                      for se in workout.exercises for s in se.sets)


def _workout(workout_id):
    with flask_app.app_context():
        return db.session.get(WorkoutSession, workout_id)


def test_finishing_deletes_what_was_never_lifted_and_keeps_the_plan_size(lifter):
    """G-080: finished workouts kept their open sets, invisible everywhere
    but the export. What they said -- the size of the plan -- stays, as the
    same number the finish sheet showed ("von Y")."""
    with flask_app.app_context():
        press, row_, curl, dips = (lifter.exercise(n) for n in ('press', 'row', 'curl', 'dips'))
        workout = lifter.workout(started_ago=dt.timedelta(minutes=50))
        lifter.row(workout, press, 1, done=[(60.0, 8), (60.0, 8)], ticked_empty=1, open_=2)
        lifter.row(workout, row_, 2, done=[(50.0, 10)], skipped=True)
        original = lifter.row(workout, curl, 3, done=[(20.0, 12)], open_=1)
        lifter.row(workout, dips, 3, open_=3, replaces=original)
        db.session.commit()
        workout_id = workout.id
    client = lifter.client()
    shown = embedded_payload(client.get(f'/gym/session/{workout_id}').get_data(as_text=True))

    response = client.post(f'/gym/session/{workout_id}/finish')

    assert response.status_code == 302
    assert 'just_finished=1' in response.headers['Location']
    finished = _workout(workout_id)
    assert finished.finished_at is not None and finished.auto_finished is False
    # 4 lifted + 2 open on the press + 3 open on the substitute; the
    # original's open set was not ahead, the ticked 0-rep set is no set.
    assert finished.planned_sets == 9 == shown['sets_total']
    assert _sets(workout_id) == [(1, 8, True), (1, 8, True), (2, 10, True), (3, 12, True)]


def test_an_empty_workout_cannot_be_finished_only_discarded(lifter):
    """G-023 / D5 b-A: "Trotzdem beenden" filed empty workouts, and Verlauf
    counted 44 where Statistik counted 42."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=dt.timedelta(minutes=20))
        lifter.row(workout, lifter.exercise('empty'), 1, ticked_empty=1, open_=3)
        db.session.commit()
        workout_id = workout.id
    client = lifter.client()

    response = client.post(f'/gym/session/{workout_id}/finish')

    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/gym/session/{workout_id}')
    assert _workout(workout_id).finished_at is None
    assert len(_sets(workout_id)) == 4
    page = client.get(response.headers['Location']).get_data(as_text=True)
    assert 'ein leeres Workout lässt sich nur verwerfen' in page


def test_an_abandoned_workout_ends_at_its_last_set(lifter):
    """G-086 / G-124: it ended at start + 3 h and was filed as 180 minutes,
    whatever happened in between."""
    last = STALE_SESSION_TIMEOUT + dt.timedelta(minutes=5)
    with flask_app.app_context():
        workout = lifter.workout(started_ago=last + dt.timedelta(minutes=40))
        lifter.row(workout, lifter.exercise('abandoned'), 1, done=[(60.0, 8), (60.0, 8)],
                   done_ago=[last + dt.timedelta(minutes=3), last], open_=2)
        db.session.commit()
        workout_id = workout.id

    lifter.client().get('/gym')

    ended = _workout(workout_id)
    assert ended.finished_at == lifter.now - last
    assert ended.auto_finished is True
    assert ended.planned_sets == 4
    assert _sets(workout_id) == [(1, 8, True), (1, 8, True)]


def test_a_set_an_hour_ago_keeps_a_long_workout_running(lifter):
    """G-124: a workout opened at home, or a long partner session, was closed
    at start + 3 h while its lifter was still logging."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=STALE_SESSION_TIMEOUT + dt.timedelta(hours=1))
        lifter.row(workout, lifter.exercise('long'), 1, done=[(60.0, 8)],
                   done_ago=[dt.timedelta(hours=1)], open_=2)
        db.session.commit()
        workout_id = workout.id

    lifter.client().get('/gym')

    assert _workout(workout_id).finished_at is None
    assert len(_sets(workout_id)) == 3


def test_an_abandoned_workout_with_nothing_lifted_is_discarded(lifter):
    """D5 b-A: auto-finish discards empty workouts instead of filing them."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=STALE_SESSION_TIMEOUT + dt.timedelta(minutes=1))
        lifter.row(workout, lifter.exercise('never'), 1, ticked_empty=1, open_=3)
        db.session.commit()
        workout_id = workout.id

    lifter.client().get('/gym')

    assert _workout(workout_id) is None


# Everything below is from the B4 review: the three-hour rule has to hold on
# every way back into an abandoned workout, not only on a rendered page.

LIVE = {'Accept': 'application/json', 'X-Gym-Surface': 'live'}
LAST = STALE_SESSION_TIMEOUT + dt.timedelta(minutes=5)
HEUTE_PATHS = ('/gym', '/gym/')


def _abandoned(lifter, name, lifted=True):
    """A workout nobody came back to, two open sets left: its last set was
    ticked LAST ago -- or, lifted=False, nothing counts and it was started
    longer ago than that. Returns (workout id, an open set's id)."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=LAST + dt.timedelta(minutes=40))
        if lifted:
            row = lifter.row(workout, lifter.exercise(name), 1, done=[(60.0, 8), (60.0, 8)],
                             done_ago=[LAST + dt.timedelta(minutes=3), LAST], open_=2)
        else:
            row = lifter.row(workout, lifter.exercise(name), 1, ticked_empty=1, open_=2)
        db.session.commit()
        return workout.id, next(s.id for s in row.sets if not s.completed)


def _path(response):
    return urlsplit(response.headers['Location']).path


def test_the_page_of_an_abandoned_workout_is_its_debrief(lifter):
    """It was built as a running workout, then the nav's context processor
    ended the workout halfway through the render: a live screen on a
    workout already filed."""
    workout_id, _ = _abandoned(lifter, 'page')

    page = lifter.client().get(f'/gym/session/{workout_id}').get_data(as_text=True)

    assert 'class="finished" id="gym-root"' in page
    assert _workout(workout_id).finished_at == lifter.now - LAST


def test_the_page_of_an_abandoned_empty_workout_goes_home_and_says_why(lifter):
    workout_id, _ = _abandoned(lifter, 'empty page', lifted=False)
    client = lifter.client()

    response = client.get(f'/gym/session/{workout_id}')

    assert response.status_code == 302 and _path(response) in HEUTE_PATHS
    assert _workout(workout_id) is None
    assert 'ohne Satz verworfen' in client.get('/gym').get_data(as_text=True)
    # Still the answer when the screen reloads it again later, not a 404.
    assert client.get(f'/gym/session/{workout_id}').status_code == 302


def test_beenden_on_an_abandoned_workout_ends_it_at_its_last_set(lifter):
    """A screen left open overnight filed its workout as ending on the
    morning's tap: a 20-hour workout."""
    workout_id, _ = _abandoned(lifter, 'late finish')

    response = lifter.client().post(f'/gym/session/{workout_id}/finish')

    assert response.status_code == 302
    finished = _workout(workout_id)
    assert finished.finished_at == lifter.now - LAST
    assert finished.auto_finished is True


def test_beenden_on_an_abandoned_empty_workout_discards_it(lifter):
    workout_id, _ = _abandoned(lifter, 'late empty', lifted=False)

    response = lifter.client().post(f'/gym/session/{workout_id}/finish')

    assert response.status_code == 302 and _path(response) in HEUTE_PATHS
    assert _workout(workout_id) is None


def test_a_set_ticked_on_an_abandoned_workout_ends_it_instead(lifter):
    """Today's set landed in a workout left three hours before; the screen
    reloads into that workout's debrief instead."""
    workout_id, open_set = _abandoned(lifter, 'late tick')

    response = lifter.client().post(f'/gym/set/{open_set}/toggle_complete',
                                    data={'completed': '1'}, headers=LIVE)

    assert response.status_code == 409
    assert _workout(workout_id).finished_at == lifter.now - LAST
    assert _sets(workout_id) == [(1, 8, True), (1, 8, True)]


def test_a_live_write_to_a_set_that_is_gone_reloads_the_screen(lifter):
    """The finish deletes the open sets (D5), so a live screen that missed
    the finish writes to rows that are gone. A 404 read as a lost connection
    and was retried forever; a 409 reloads the screen. Elsewhere it stays
    404."""
    client = lifter.client()
    gone = 2_000_000_000

    assert client.post(f'/gym/set/{gone}/toggle_complete', headers=LIVE).status_code == 409
    assert client.post(f'/gym/set/{gone}/update', headers=LIVE).status_code == 409
    assert client.post(f'/gym/set/{gone}/toggle_complete',
                       headers={'Accept': 'application/json'}).status_code == 404


def test_the_island_refetch_learns_its_workout_was_ended(lifter):
    """detail.json served an abandoned workout as running: only a rendered
    page ended it. The island reloads once the refetch says finished."""
    workout_id, _ = _abandoned(lifter, 'refetch')

    payload = lifter.client().get(f'/gym/session/{workout_id}/detail.json').get_json()

    assert payload['session']['finished_at'] is not None


def test_settling_a_workout_another_request_just_discarded(lifter):
    """Two requests noticing the same abandoned workout both deleted it, and
    the second one's delete was a 500: the settle takes the workout's lock
    and reads it again."""
    from features.gym.routes import helpers
    workout_id, _ = _abandoned(lifter, 'race', lifted=False)
    with flask_app.test_request_context():
        seen = db.session.get(WorkoutSession, workout_id)
        assert seen.finished_at is None
        with flask_app.app_context():
            helpers._delete_session_and_links(db.session.get(WorkoutSession, workout_id))

        assert helpers._settle_if_abandoned(seen) == 'discarded'
        # The request that lost the race goes home too, on its next reload
        # as well: only the one that deleted it used to remember it.
        assert flask_session.get(helpers.DISCARDED_SESSION_KEY) == workout_id


# From the B4 re-review.

def _statements(run):
    """How many SQL statements `run()` sends."""
    sent = []

    def count(*_):
        sent.append(1)

    engine = db.engine
    event.listen(engine, 'before_cursor_execute', count)
    try:
        run()
    finally:
        event.remove(engine, 'before_cursor_execute', count)
    return len(sent)


def test_the_three_hour_check_is_one_query(lifter):
    """Every gym GET asks whether the running workout was abandoned
    (routes._settle_an_abandoned_workout_first). It walked the workout
    row by row: a query per exercise, on every page and every refetch."""
    from features.gym.routes import helpers
    with flask_app.app_context():
        workout = lifter.workout(started_ago=dt.timedelta(minutes=30))
        for position, name in enumerate(('one', 'two', 'three'), start=1):
            lifter.row(workout, lifter.exercise(f'queries {name}'), position,
                       done=[(50.0, 8)], done_ago=[dt.timedelta(minutes=10)], open_=2)
        db.session.commit()
        workout_id = workout.id
    with flask_app.test_request_context():
        seen = db.session.get(WorkoutSession, workout_id)

        assert _statements(lambda: helpers._settle_if_abandoned(seen)) == 1


def test_deleting_a_workout_under_a_callers_lock_does_not_commit(lifter):
    """A join discards the joiner's empty workout while it holds lock_user,
    which a commit lets go of: the second tap of a double "Mitmachen" ran
    on unguarded."""
    from features.gym.routes import helpers
    with flask_app.app_context():
        workout = lifter.workout(started_ago=dt.timedelta(minutes=5))
        db.session.commit()
        workout_id = workout.id
    with flask_app.app_context():
        helpers._delete_session_and_links(db.session.get(WorkoutSession, workout_id),
                                          commit=False)
        db.session.rollback()

    assert _workout(workout_id) is not None


def test_inviting_from_an_abandoned_workout_ends_it_instead(lifter, monkeypatch):
    """An invite from a screen left open for hours went out for a workout
    that was over: the partner joined a workout three hours cold."""
    from features.gym import push
    sent = []
    monkeypatch.setattr(push, 'send_push_later', lambda *args: sent.append(args))
    partner_id = lifter.partner()
    workout_id, _ = _abandoned(lifter, 'late invite')
    client = lifter.client()

    response = client.post(f'/gym/session/{workout_id}/invite', data={'partner_id': partner_id})

    assert response.status_code == 302
    assert _workout(workout_id).finished_at == lifter.now - LAST
    with flask_app.app_context():
        assert SharedSession.query.filter_by(leader_session_id=workout_id).count() == 0
    assert sent == []
    assert 'schon vorbei' in client.get(response.headers['Location']).get_data(as_text=True)


def test_an_invite_to_an_abandoned_workout_cannot_be_taken_up(lifter):
    """The leader's screen went quiet three hours ago, and nothing of the
    partner's own ends it: joining it seeded a workout already over."""
    partner_id = lifter.partner()
    workout_id, _ = _abandoned(lifter, 'cold invite')
    with flask_app.app_context():
        invite = SharedSession(leader_session_id=workout_id, leader_user_id=lifter.user_id,
                               follower_user_id=partner_id)
        db.session.add(invite)
        db.session.commit()
        invite_id = invite.id
    client = lifter.client(partner_id)

    confirm = embedded_payload(client.get(f'/gym/shared/{invite_id}/confirm')
                               .get_data(as_text=True))
    response = client.post(f'/gym/shared/{invite_id}/accept')

    assert confirm['refusal'] == 'Das Workout ist schon vorbei.'
    assert response.status_code == 302 and _path(response) in HEUTE_PATHS
    with flask_app.app_context():
        assert WorkoutSession.query.filter_by(user_id=partner_id).count() == 0


def test_discarding_a_workout_that_has_sets_says_why_not(lifter):
    """The refusal was a silent redirect back to the workout: the tap
    seemed to do nothing."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=dt.timedelta(minutes=30))
        lifter.row(workout, lifter.exercise('keep'), 1, done=[(60.0, 8)],
                   done_ago=[dt.timedelta(minutes=5)], open_=1)
        db.session.commit()
        workout_id = workout.id
    client = lifter.client()

    response = client.post(f'/gym/session/{workout_id}/discard')

    assert response.status_code == 302
    assert _path(response) == f'/gym/session/{workout_id}'
    assert _workout(workout_id) is not None
    page = client.get(response.headers['Location']).get_data(as_text=True)
    assert 'beende es statt es zu verwerfen' in page


def test_a_second_discard_goes_home(lifter):
    """A double submit, or a second tab: the second found the workout gone
    and answered 404."""
    with flask_app.app_context():
        workout = lifter.workout(started_ago=dt.timedelta(minutes=3))
        db.session.commit()
        workout_id = workout.id
    client = lifter.client()

    first = client.post(f'/gym/session/{workout_id}/discard')
    second = client.post(f'/gym/session/{workout_id}/discard')

    assert _path(first) in HEUTE_PATHS and _workout(workout_id) is None
    assert second.status_code == 302 and _path(second) in HEUTE_PATHS
    assert client.get(f'/gym/session/{workout_id}').status_code == 302
