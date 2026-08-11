"""The live-workout JSON endpoint.

It must agree with the page, which is why both go through _live_data. The
breadth test below is the one that matters: step 1 shipped a real crash past
a green suite because every test sampled the first record, and whichever row
sorts first is not representative of an unfinished session, a deload, a
shared one, or an empty one.
"""
import datetime as dt

import pytest

from conftest import _admin_id, acting_as


def test_returns_the_payload_shape(client, live_session):
    session_id = live_session['session']
    response = client.get(f'/gym/session/{session_id}/detail.json')
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) >= {
        'session', 'visible_exercises', 'live_id', 'sets_done', 'sets_total',
        'resting', 'record_set_ids', 'exercises', 'session_is_shared',
    }
    assert body['session']['id'] == session_id


def test_agrees_with_the_page(client, live_session):
    """Both go through _live_data, so the live exercise cannot differ."""
    session_id = live_session['session']
    from app import app as flask_app
    from features.gym.routes import _session_payload
    from features.gym.scope import owned_session

    with flask_app.app_context():
        with acting_as(_admin_id()):
            direct = _session_payload(owned_session(session_id))

    from_endpoint = client.get(f'/gym/session/{session_id}/detail.json').get_json()
    assert from_endpoint['live_id'] == direct.live_id
    assert from_endpoint['sets_total'] == direct.sets_total


def test_every_unfinished_session_builds_a_valid_payload():
    """Breadth, not a sample."""
    from app import app as flask_app
    from features.gym.routes import _session_payload
    from features.gym.scope import my_sessions, owned_session
    from models import WorkoutSession

    failures = []
    with flask_app.app_context():
        with acting_as(_admin_id()):
            ids = [s.id for s in my_sessions()
                   .filter(WorkoutSession.finished_at.is_(None)).all()]
            for session_id in ids:
                try:
                    _session_payload(owned_session(session_id))
                except Exception as exc:
                    failures.append(f'{session_id}: {type(exc).__name__}: {exc}')
    assert not failures, 'payload failed for:\n' + '\n'.join(failures)


def test_every_session_page_still_renders(client):
    """Finished and unfinished both -- session_detail serves two pages and
    only one of them was restructured."""
    from app import app as flask_app
    from features.gym.scope import my_sessions

    with flask_app.app_context():
        with acting_as(_admin_id()):
            ids = [s.id for s in my_sessions().all()]
            assert ids, 'the dev database needs sessions'

    bad = [(i, client.get(f'/gym/session/{i}').status_code) for i in ids]
    assert all(status == 200 for _, status in bad), \
        f'non-200 responses: {[p for p in bad if p[1] != 200]}'


def test_int_keyed_dicts_reach_the_client_as_strings(client, live_session):
    """suggestions and stagnation_counts are keyed by SessionExercise.id.
    Pinned end-to-end, not just at the schema, because this is the detail the
    React port will trip over."""
    session_id = live_session['session']
    body = client.get(f'/gym/session/{session_id}/detail.json').get_json()
    assert all(isinstance(key, str) for key in body['suggestions'])
    assert all(isinstance(key, str) for key in body['stagnation_counts'])


def test_requires_a_login(anon_client, live_session):
    session_id = live_session['session']
    response = anon_client.get(f'/gym/session/{session_id}/detail.json')
    assert response.status_code in (302, 401, 403)


def test_a_stalling_live_exercise_carries_its_prescription():
    """The stall line's "auf X kg gehen" number: one increment up from the
    pre-fill, snapped UP onto the machine's real stops -- same math as the
    debrief's Nächstes-Mal advice. Display only, an owner decision: the
    steppers keep pre-filling the proven weight, the payload just says what
    going up would mean. 61 kg on a 5/12/18/29/33/61/68/92 stack must say
    68, not the 63.5 the default grid would invent."""
    import datetime as dt
    from app import app as flask_app
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession

    made = {'sessions': [], 'exercise': None}
    try:
        with flask_app.app_context():
            exercise = Exercise(name='pytest live stall stack lift',
                                user_id=_admin_id(),
                                stack_kg=[5.0, 12.0, 18.0, 29.0, 33.0, 61.0, 68.0, 92.0])
            db.session.add(exercise)
            db.session.flush()
            made['exercise'] = exercise.id
            # Five, not four: the first session IS the PR, so N sessions give
            # N-1 without one, and STAGNATION_THRESHOLD is 4.
            base = dt.datetime.utcnow() - dt.timedelta(days=27)
            for n in range(5):
                past = WorkoutSession(name=f'pytest live stall history {n}',
                                      started_at=base + dt.timedelta(days=5 * n),
                                      finished_at=base + dt.timedelta(days=5 * n, hours=1),
                                      user_id=_admin_id())
                se = SessionExercise(exercise_id=exercise.id, position=1)
                se.sets = [SessionSet(position=1, weight=61.0, reps=8, completed=True)]
                past.exercises.append(se)
                db.session.add(past)
                db.session.flush()
                made['sessions'].append(past.id)
            live = WorkoutSession(name='pytest live stall session',
                                  started_at=dt.datetime.utcnow(), user_id=_admin_id())
            live_se = SessionExercise(exercise_id=exercise.id, position=1)
            live_se.sets = [SessionSet(position=1, weight=61.0, reps=8, completed=False)]
            live.exercises.append(live_se)
            db.session.add(live)
            db.session.commit()
            made['sessions'].append(live.id)
            live_id, se_id = live.id, live_se.id

        flask_app.config['TESTING'] = True
        with flask_app.test_client() as test_client:
            with test_client.session_transaction() as flask_session:
                flask_session['user_id'] = _admin_id()
            body = test_client.get(f'/gym/session/{live_id}/detail.json').get_json()

        assert body['stagnation_counts'].get(str(se_id)) is not None, \
            'the fixture did not actually stagnate'
        assert body['stall_next_weight'] == {str(se_id): 68.0}
        # And the pre-fill is untouched: said, never seeded.
        assert body['suggestions'][str(se_id)]['weight'] == 61.0
    finally:
        with flask_app.app_context():
            for session_id in made['sessions']:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            doomed = db.session.get(Exercise, made['exercise'])
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()
