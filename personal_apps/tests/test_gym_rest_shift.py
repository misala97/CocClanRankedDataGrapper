"""The rest between sets, moved while it runs (G-055, D8 variant B).

The countdown band above the confirm button carries "−15", "+15" and a skip.
A shift moves the running rest's end, the "rest over" push with it, and the
total the progress bar is drawn against -- which is why that total is now
measured from the set that started the rest, not re-read from a setting that
can change underneath a running countdown.
"""
import datetime as dt

import pytest

from app import app as flask_app


JSON = {'Accept': 'application/json'}
LIVE = {'Accept': 'application/json', 'X-Gym-Surface': 'live'}


def _rest_state(session_id):
    """(rest_ends_at, resting_set_id, [fire_at of each unsent push])."""
    from extensions import db
    from models import PendingPush, WorkoutSession
    with flask_app.app_context():
        row = db.session.get(WorkoutSession, session_id)
        pushes = [p.fire_at for p in
                  PendingPush.query.filter_by(session_id=session_id, sent=False).all()]
        return row.rest_ends_at, row.resting_set_id, pushes


def _set_rest(session_id, set_id, started, seconds):
    """A rest started by `set_id` at `started`, `seconds` long, with its push --
    what _schedule_rest leaves behind, placed where a test needs it."""
    from extensions import db
    from models import PendingPush, SessionSet, WorkoutSession
    with flask_app.app_context():
        db.session.get(SessionSet, set_id).completed_at = started
        row = db.session.get(WorkoutSession, session_id)
        row.rest_ends_at = started + dt.timedelta(seconds=seconds)
        row.resting_set_id = set_id
        PendingPush.query.filter_by(session_id=session_id).delete()
        db.session.add(PendingPush(session_id=session_id, fire_at=row.rest_ends_at))
        db.session.commit()


def _rest_seconds(se_id, seconds):
    from extensions import db
    from models import SessionExercise
    with flask_app.app_context():
        db.session.get(SessionExercise, se_id).rest_seconds = seconds
        db.session.commit()


def _start_rest(client, ids, seconds=90):
    """Log the open set through the real route, with this workout's rest at
    `seconds`, and return the payload it answers with."""
    _rest_seconds(ids['se'], seconds)
    response = client.post(f"/gym/set/{ids['open_set']}/toggle_complete",
                           data={'completed': '1', 'weight': '60', 'reps': '8'},
                           headers=LIVE)
    assert response.status_code == 200
    return response.get_json()


def _shift(client, session_id, seconds, headers=LIVE):
    return client.post(f'/gym/session/{session_id}/rest/shift',
                       data={} if seconds is None else {'seconds': seconds},
                       headers=headers)


def test_plus_fifteen_moves_the_end_the_push_and_the_total(client, live_session):
    before = _start_rest(client, live_session)
    assert before['resting'] is True
    assert before['rest_total_seconds'] == 90
    ends_before, _, _ = _rest_state(live_session['session'])

    response = _shift(client, live_session['session'], '15')

    assert response.status_code == 200
    ends, resting_set, pushes = _rest_state(live_session['session'])
    assert ends - ends_before == dt.timedelta(seconds=15)
    assert resting_set == live_session['open_set']
    # Moved, not stacked: one push, at the new end.
    assert pushes == [ends]
    payload = response.get_json()
    assert payload['resting'] is True
    assert payload['rest_total_seconds'] == 105


def test_minus_fifteen_shortens_it(client, live_session):
    _start_rest(client, live_session)
    ends_before, _, _ = _rest_state(live_session['session'])

    response = _shift(client, live_session['session'], '-15')

    ends, _, pushes = _rest_state(live_session['session'])
    assert ends_before - ends == dt.timedelta(seconds=15)
    assert pushes == [ends]
    assert response.get_json()['rest_total_seconds'] == 75


def test_a_shift_past_the_end_ends_the_rest_like_the_skip(client, live_session):
    """Ten seconds left and "−15": what is left of the rest is less than the
    step, so the rest is over -- and its push goes with it, or the notifier
    announces a rest the lifter already ended. Over as a skip leaves it: the
    end stamped now and the set kept, for the band's count-up (round 4)."""
    now = dt.datetime.utcnow()
    _set_rest(live_session['session'], live_session['done_set'],
              started=now - dt.timedelta(seconds=80), seconds=90)

    response = _shift(client, live_session['session'], '-15')

    assert response.status_code == 200
    ends, resting_set, pushes = _rest_state(live_session['session'])
    assert now.replace(microsecond=0) <= ends <= dt.datetime.utcnow()
    assert (resting_set, pushes) == (live_session['done_set'], [])
    payload = response.get_json()
    assert payload['resting'] is False
    assert payload['rest_total_seconds'] == 0


def test_the_skip_ends_the_rest_now_and_keeps_it_for_the_band(client, live_session):
    """The band stays until the next set, counting up from the rest's end
    (round 4), so the skip stamps that end instead of clearing it. The push
    goes: the lifter ended the rest, nothing is left to announce."""
    now = dt.datetime.utcnow()
    _set_rest(live_session['session'], live_session['done_set'],
              started=now - dt.timedelta(seconds=30), seconds=90)

    response = client.post(f"/gym/session/{live_session['session']}/rest/skip", headers=LIVE)

    assert response.status_code == 200
    ends, resting_set, pushes = _rest_state(live_session['session'])
    assert now.replace(microsecond=0) <= ends <= dt.datetime.utcnow()
    assert (resting_set, pushes) == (live_session['done_set'], [])
    payload = response.get_json()
    assert payload['resting'] is False
    assert payload['session']['resting_set_id'] == live_session['done_set']


def test_a_skip_after_the_rest_ran_out_keeps_its_end(client, live_session):
    """The count-up runs from when the rest ended, not from a late tap."""
    now = dt.datetime.utcnow()
    _set_rest(live_session['session'], live_session['done_set'],
              started=now - dt.timedelta(seconds=120), seconds=90)
    ends_before, _, _ = _rest_state(live_session['session'])

    client.post(f"/gym/session/{live_session['session']}/rest/skip", headers=LIVE)

    assert _rest_state(live_session['session']) == (ends_before, live_session['done_set'], [])


def test_the_next_set_replaces_an_ended_rest(client, live_session):
    """"Until the next set": logging it starts that set's own rest, and with
    no rest configured after it the old one is cleared, not counted on."""
    now = dt.datetime.utcnow()
    _set_rest(live_session['session'], live_session['done_set'],
              started=now - dt.timedelta(seconds=300), seconds=90)

    _start_rest(client, live_session, seconds=0)

    assert _rest_state(live_session['session']) == (None, None, [])


@pytest.mark.parametrize('path, data', [('rest/shift', {'seconds': '15'}), ('rest/skip', {})],
                         ids=['shift', 'skip'])
def test_a_workout_finished_while_the_request_waited_is_refused(client, live_session, monkeypatch,
                                                                path, data):
    """The other phone finishes the workout while this request waits for the
    lock: a shift or a skip answers 409 like any finished workout, not 200
    with the debrief's payload for the live screen to choke on (I1 review).

    The finish commits from inside the lock call, after the first check has
    passed, so only a check after the lock can see it (fix-round review: a
    workout finished up front was refused wherever the check sat)."""
    from sqlalchemy import text

    from extensions import db
    from features.gym.routes import workout

    real_lock = workout.lock_sessions

    def finished_meanwhile(session_ids):
        with db.engine.begin() as other_phone:
            other_phone.execute(
                text('UPDATE gym_workout_sessions SET finished_at = :now WHERE id = :id'),
                {'now': dt.datetime.utcnow().replace(microsecond=0), 'id': live_session['session']})
        real_lock(session_ids)

    monkeypatch.setattr(workout, 'lock_sessions', finished_meanwhile)
    now = dt.datetime.utcnow()
    _set_rest(live_session['session'], live_session['done_set'],
              started=now - dt.timedelta(seconds=30), seconds=90)
    before = _rest_state(live_session['session'])

    response = client.post(f"/gym/session/{live_session['session']}/{path}", data=data,
                           headers=LIVE)

    assert response.status_code == 409
    assert response.get_json() == {'finished': True}
    assert _rest_state(live_session['session']) == before


def test_plus_fifteen_never_shortens_a_rest_longer_than_the_cap(client, live_session):
    """A 15-minute rest saved before rests had a cap: "+15" leaves it be,
    "−15" still takes 15 seconds off (I1 review)."""
    now = dt.datetime.utcnow().replace(microsecond=0)
    started = now - dt.timedelta(seconds=60)
    _set_rest(live_session['session'], live_session['done_set'], started=started, seconds=900)

    _shift(client, live_session['session'], '15')
    ends, _, pushes = _rest_state(live_session['session'])
    assert ends == started + dt.timedelta(seconds=900)
    assert pushes == [ends]

    response = _shift(client, live_session['session'], '-15')
    assert _rest_state(live_session['session'])[0] == started + dt.timedelta(seconds=885)
    assert response.get_json()['rest_total_seconds'] == 885


def test_a_rest_whose_set_has_no_stamp_falls_back_to_the_setting_and_to_now(client, live_session):
    """Sets logged before completed_at existed: the total is the exercise's
    rest, and "+15" caps at the longest rest from now."""
    from extensions import db
    from models import SessionSet

    now = dt.datetime.utcnow().replace(microsecond=0)
    _rest_seconds(live_session['se'], 120)
    _set_rest(live_session['session'], live_session['done_set'],
              started=now - dt.timedelta(seconds=5), seconds=595)
    with flask_app.app_context():
        db.session.get(SessionSet, live_session['done_set']).completed_at = None
        db.session.commit()

    detail = client.get(f"/gym/session/{live_session['session']}/detail.json", headers=JSON)
    assert detail.get_json()['rest_total_seconds'] == 120

    _shift(client, live_session['session'], '15')
    ends, _, _ = _rest_state(live_session['session'])
    assert now + dt.timedelta(seconds=600) <= ends <= dt.datetime.utcnow() + dt.timedelta(seconds=600)


def test_the_rest_stops_growing_at_the_longest_rest_there_is(client, live_session):
    """Ten minutes is the longest rest the steppers offer (REST_MAX_SECONDS);
    "+15" takes a rest up to it and no further."""
    now = dt.datetime.utcnow().replace(microsecond=0)
    started = now - dt.timedelta(seconds=10)
    _set_rest(live_session['session'], live_session['done_set'], started=started, seconds=590)

    first = _shift(client, live_session['session'], '15')
    second = _shift(client, live_session['session'], '15')

    ends, _, pushes = _rest_state(live_session['session'])
    assert ends == started + dt.timedelta(seconds=600)
    assert pushes == [ends]
    assert first.get_json()['rest_total_seconds'] == 600
    assert second.get_json()['rest_total_seconds'] == 600


def test_nothing_moves_when_no_rest_runs(client, live_session):
    response = _shift(client, live_session['session'], '15')

    assert response.status_code == 200
    assert response.get_json()['resting'] is False
    assert _rest_state(live_session['session']) == (None, None, [])


def test_a_rest_that_already_ran_out_is_not_brought_back(client, live_session):
    """rest_ends_at outlives its countdown -- nothing clears it when it passes.
    "+15" on a stale screen must not restart a rest that is over."""
    now = dt.datetime.utcnow()
    _set_rest(live_session['session'], live_session['done_set'],
              started=now - dt.timedelta(seconds=120), seconds=90)
    ends_before, _, pushes_before = _rest_state(live_session['session'])

    _shift(client, live_session['session'], '15')

    assert _rest_state(live_session['session']) == (ends_before, live_session['done_set'],
                                                     pushes_before)


def test_only_fifteen_seconds_either_way(client, live_session):
    _start_rest(client, live_session)
    before = _rest_state(live_session['session'])

    for seconds in ('30', '-30', '0', 'abc', '', None, '15.5'):
        response = _shift(client, live_session['session'], seconds)
        assert response.status_code == 400, seconds
        assert _rest_state(live_session['session']) == before, seconds


def test_the_total_is_the_rest_that_is_running_not_todays_setting(client, live_session):
    """Changing "Pause heute" mid-rest leaves the running countdown alone, so
    the bar must too: it used to re-read the setting and jump."""
    _start_rest(client, live_session, seconds=90)

    response = client.post(f"/gym/session-exercise/{live_session['se']}/rest",
                           data={'rest_seconds': '120'}, headers=LIVE)

    assert response.status_code == 200
    assert response.get_json()['rest_total_seconds'] == 90


def test_a_plain_form_post_is_sent_back_to_the_workout(client, live_session):
    _start_rest(client, live_session)

    response = _shift(client, live_session['session'], '15', headers={})

    assert response.status_code == 302
    assert response.headers['Location'].endswith(f"/gym/session/{live_session['session']}")
