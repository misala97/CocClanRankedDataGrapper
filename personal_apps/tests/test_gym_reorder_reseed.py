"""What moving an exercise does to the plan underneath it -- alone, and on a
training partner's side.

Both lifters train the same four exercises -- one set of rows, as on the one
list -- with two fresh workouts of history each, so every plan here also shows
that seeding reads the lifter's own history off a row both of them use.
'raise' is the slot-sensitive one: it was done at slot 4 ten days ago (lighter)
and at slot 3 five days ago (heavier), so seeding it at slot 3 hands out the
heavier session and seeding it at slot 4 hands out the lighter one -- position
>= slot is what counts as valid evidence (see seeding._last_session_exercise).
The other three seed the same numbers wherever they sit.
"""
import datetime as dt

import pytest

from app import app as flask_app

PRESS, ROW, RAISE, CURL = ('pytest rs press', 'pytest rs row',
                           'pytest rs raise', 'pytest rs curl')
# Nobody has history on these: what a lifter adds mid-workout.
OWN, EXTRA, CABLE_ROW, FILLER = ('pytest rs own', 'pytest rs leader extra',
                                 'pytest rs cable row', 'pytest rs filler')

# (slot in the workout ten days ago, slot five days ago, sets then, sets now)
LEADER_HISTORY = {
    PRESS: (1, 1, [(100.0, 5), (100.0, 5)], [(100.0, 5), (100.0, 5)]),
    ROW:   (2, 2, [(80.0, 8), (80.0, 8)], [(80.0, 8), (80.0, 8)]),
    CURL:  (3, 4, [(20.0, 10), (20.0, 10)], [(20.0, 10), (20.0, 10)]),
    RAISE: (4, 3, [(50.0, 10), (50.0, 9), (45.0, 10)], [(55.0, 9), (55.0, 8), (50.0, 10)]),
}
FOLLOWER_HISTORY = {
    PRESS: (1, 1, [(60.0, 5), (60.0, 5)], [(60.0, 5), (60.0, 5)]),
    ROW:   (2, 2, [(50.0, 8), (50.0, 8)], [(50.0, 8), (50.0, 8)]),
    CURL:  (3, 4, [(12.0, 10), (12.0, 10)], [(12.0, 10), (12.0, 10)]),
    RAISE: (4, 3, [(30.0, 10), (30.0, 9), (25.0, 10)], [(35.0, 9), (35.0, 8), (30.0, 10)]),
}

LEADER_RAISE_AT_3 = [(55.0, 9), (55.0, 8), (50.0, 10)]
LEADER_RAISE_AT_4 = [(50.0, 10), (50.0, 9), (45.0, 10)]
FOLLOWER_RAISE_AT_3 = [(35.0, 9), (35.0, 8), (30.0, 10)]
FOLLOWER_RAISE_AT_4 = [(30.0, 10), (30.0, 9), (25.0, 10)]


def _client_for(user_id):
    flask_app.config['TESTING'] = True
    test_client = flask_app.test_client()
    with test_client.session_transaction() as flask_session:
        flask_session['user_id'] = user_id
    return test_client


def _build_lifts():
    """The exercises both lifters use, key-less. Returns {name: id}."""
    from extensions import db
    from models import Exercise

    lifts = {name: Exercise(name=name, list_rest_seconds=0)
             for name in (PRESS, ROW, RAISE, CURL, OWN, EXTRA, CABLE_ROW, FILLER)}
    db.session.add_all(lifts.values())
    db.session.flush()
    return {name: row.id for name, row in lifts.items()}


def _build_lifter(username, history, lifts):
    """A user, two finished workouts and two routines on `lifts`.
    Returns (user_id, {'raise_third': template_id, 'raise_last': template_id})."""
    from extensions import db
    from models import (AppUser, SessionExercise, SessionSet,
                        TemplateExercise, WorkoutSession, WorkoutTemplate)
    from werkzeug.security import generate_password_hash

    user = AppUser(username=username, password_hash=generate_password_hash('x'),
                   is_admin=False)
    db.session.add(user)
    db.session.flush()

    now = dt.datetime.utcnow()
    for days_ago, which in ((10, 0), (5, 1)):
        started = now - dt.timedelta(days=days_ago)
        workout = WorkoutSession(name='pytest rs history', user_id=user.id,
                                 started_at=started,
                                 finished_at=started + dt.timedelta(hours=1))
        for name, spec in history.items():
            row = SessionExercise(exercise_id=lifts[name], position=spec[which])
            row.sets = [SessionSet(position=j, weight=w, reps=r, completed=True,
                                   completed_at=started)
                        for j, (w, r) in enumerate(spec[2 + which], start=1)]
            workout.exercises.append(row)
        db.session.add(workout)

    templates = {}
    for key, order in (('raise_third', (PRESS, ROW, RAISE, CURL)),
                       ('raise_last', (PRESS, ROW, CURL, RAISE))):
        template = WorkoutTemplate(name=f'pytest rs {key}', user_id=user.id)
        template.exercises = [TemplateExercise(exercise_id=lifts[name], position=i)
                              for i, name in enumerate(order, start=1)]
        db.session.add(template)
        db.session.flush()
        templates[key] = template.id
    return user.id, templates


def _destroy_lifter(user_id):
    from extensions import db
    from models import (AppUser, ExerciseSettings, PendingPush, SharedSession,
                        WorkoutSession, WorkoutTemplate)

    for shared in SharedSession.query.filter(
            db.or_(SharedSession.leader_user_id == user_id,
                   SharedSession.follower_user_id == user_id)).all():
        db.session.delete(shared)
    db.session.commit()
    for row in WorkoutSession.query.filter_by(user_id=user_id).all():
        row.resting_set_id = None
        PendingPush.query.filter_by(session_id=row.id).delete()
        db.session.commit()
        db.session.delete(row)
    db.session.commit()
    for row in WorkoutTemplate.query.filter_by(user_id=user_id).all():
        db.session.delete(row)
    ExerciseSettings.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    doomed = db.session.get(AppUser, user_id)
    if doomed is not None:
        db.session.delete(doomed)
    db.session.commit()


def _destroy_lifts():
    """Every key-less 'pytest rs' row -- run once no session uses them."""
    from extensions import db
    from models import Exercise

    Exercise.query.filter(Exercise.library_key.is_(None),
                          Exercise.name.like('pytest rs %')).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def lifters():
    """{'leader', 'follower', 'leader_templates', 'follower_templates'} of ids,
    and 'lifts': {name: exercise id}."""
    from extensions import db
    from models import AppUser

    with flask_app.app_context():
        # A crashed earlier run must not block this one on the unique username.
        for stale in AppUser.query.filter(AppUser.username.like('pytest rs %')).all():
            _destroy_lifter(stale.id)
        _destroy_lifts()
        lifts = _build_lifts()
        leader, leader_templates = _build_lifter('pytest rs leader', LEADER_HISTORY, lifts)
        follower, follower_templates = _build_lifter('pytest rs follower', FOLLOWER_HISTORY, lifts)
        db.session.commit()
        made = {'leader': leader, 'follower': follower, 'lifts': lifts,
                'leader_templates': leader_templates,
                'follower_templates': follower_templates}
    yield made
    with flask_app.app_context():
        _destroy_lifter(made['leader'])
        _destroy_lifter(made['follower'])
        _destroy_lifts()


def _start(user_id, template_id):
    import re
    response = _client_for(user_id).post('/gym/start', data={'template_id': template_id})
    assert response.status_code == 302
    return int(re.search(r'/gym/session/(\d+)', response.headers['Location']).group(1))


def _rows(session_id):
    """[{'id', 'name', 'position', 'skipped', 'sets': [(weight, reps)], 'set_ids',
    'completed': [bool]}] in the order the app serves them."""
    from extensions import db
    from models import WorkoutSession

    with flask_app.app_context():
        session_ = db.session.get(WorkoutSession, session_id)
        out = []
        for se in sorted(session_.exercises, key=lambda se: (se.position, se.id)):
            out.append({
                'id': se.id, 'name': se.exercise.name, 'position': se.position,
                'skipped': se.skipped, 'mirrors_id': se.mirrors_id,
                'replaces_id': se.replaces_id,
                'sets': [(s.weight, s.reps) for s in se.sets],
                'set_ids': [s.id for s in se.sets],
                'completed': [s.completed for s in se.sets],
                'base_weights': [s.base_weight for s in se.sets],
            })
        db.session.remove()
        return out


def _row(session_id, name):
    return next(r for r in _rows(session_id) if r['name'] == name)


def _reorder(user_id, session_id, names):
    by_name = {r['name']: r['id'] for r in _rows(session_id)}
    response = _client_for(user_id).post(
        f'/gym/session/{session_id}/exercises/reorder',
        data={'order': ','.join(str(by_name[n]) for n in names)},
        headers={'Accept': 'application/json'})
    assert response.status_code == 200
    return response.get_json()


def _post(user_id, url, **fields):
    response = _client_for(user_id).post(url, data=fields,
                                         headers={'Accept': 'application/json'})
    assert response.status_code == 200, (url, response.status_code)
    return response.get_json()


@pytest.fixture()
def solo(lifters):
    """The leader alone, started from the routine that has raise in slot 3."""
    return dict(lifters, session=_start(lifters['leader'],
                                        lifters['leader_templates']['raise_third']))


@pytest.fixture()
def pair(lifters):
    """Leader started from the raise-in-slot-3 routine; follower joined through
    the real invite and accept routes."""
    from extensions import db
    from models import SharedSession

    leader_session = _start(lifters['leader'], lifters['leader_templates']['raise_third'])
    _client_for(lifters['leader']).post(f'/gym/session/{leader_session}/invite',
                                        data={'partner_id': lifters['follower']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(leader_session_id=leader_session).first().id
        db.session.remove()
    response = _client_for(lifters['follower']).post(f'/gym/shared/{shared_id}/accept')
    assert response.status_code == 302
    with flask_app.app_context():
        follower_session = db.session.get(SharedSession, shared_id).follower_session_id
        db.session.remove()
    return dict(lifters, shared=shared_id, leader_session=leader_session,
                follower_session=follower_session)


# --- the fixture itself -----------------------------------------------------

def test_the_fixture_seeds_raise_by_slot(solo):
    """Guards every test below: if this stops holding, they prove nothing."""
    assert _row(solo['session'], RAISE)['sets'] == LEADER_RAISE_AT_3
    _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE])
    assert _row(solo['session'], RAISE)['sets'] == LEADER_RAISE_AT_4


# --- a shared workout: the follower's plan follows the slot too ---------------

def test_the_leaders_reorder_reseeds_the_followers_untouched_rows_from_their_own_history(pair):
    assert _row(pair['follower_session'], RAISE)['sets'] == FOLLOWER_RAISE_AT_3

    _reorder(pair['leader'], pair['leader_session'], [PRESS, ROW, CURL, RAISE])

    follower_raise = _row(pair['follower_session'], RAISE)
    assert follower_raise['position'] == 4
    assert follower_raise['sets'] == FOLLOWER_RAISE_AT_4, (
        'the follower kept the plan seeded for the slot the exercise left')


def test_the_leaders_reorder_leaves_a_follower_row_with_a_logged_set_alone(pair):
    raise_row = _row(pair['follower_session'], RAISE)
    _post(pair['follower'], f"/gym/set/{raise_row['set_ids'][0]}/toggle_complete",
          completed='1', weight=36, reps=9)

    _reorder(pair['leader'], pair['leader_session'], [PRESS, ROW, CURL, RAISE])

    after = _row(pair['follower_session'], RAISE)
    assert after['sets'] == [(36.0, 9)] + FOLLOWER_RAISE_AT_3[1:]
    assert after['completed'] == [True, False, False]


def test_the_leaders_reorder_keeps_a_weight_the_follower_typed(pair):
    raise_row = _row(pair['follower_session'], RAISE)
    _post(pair['follower'], f"/gym/set/{raise_row['set_ids'][0]}/update", weight=32.5, reps=12)

    _reorder(pair['leader'], pair['leader_session'], [PRESS, ROW, CURL, RAISE])

    assert _row(pair['follower_session'], RAISE)['sets'] == (
        [(32.5, 12)] + FOLLOWER_RAISE_AT_3[1:])


# --- reordering alone: only an untouched plan is ours to replace --------------

def test_reorder_keeps_a_weight_typed_into_a_pending_set(solo):
    """Dragging ONE exercise renumbers every row between its old and new slot,
    so this is about rows the lifter never dragged."""
    raise_row = _row(solo['session'], RAISE)
    _post(solo['leader'], f"/gym/set/{raise_row['set_ids'][0]}/update", weight=99, reps=5)

    _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE])

    assert _row(solo['session'], RAISE)['sets'] == [(99.0, 5)] + LEADER_RAISE_AT_3[1:]


def test_reorder_does_not_bring_back_a_pending_set_the_lifter_removed(solo):
    raise_row = _row(solo['session'], RAISE)
    _post(solo['leader'], f"/gym/set/{raise_row['set_ids'][-1]}/delete")

    _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE])

    assert _row(solo['session'], RAISE)['sets'] == LEADER_RAISE_AT_3[:2]


def test_reorder_rewrites_an_untouched_plan_in_place(solo):
    """Same rows, new numbers: the live screen keys its editors on set ids."""
    before = _row(solo['session'], RAISE)

    _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE])

    after = _row(solo['session'], RAISE)
    assert after['sets'] == LEADER_RAISE_AT_4
    assert after['set_ids'] == before['set_ids']


def test_reorder_does_not_seed_a_skipped_exercise(solo):
    raise_row = _row(solo['session'], RAISE)
    _post(solo['leader'], f"/gym/session-exercise/{raise_row['id']}/skip")
    assert _row(solo['session'], RAISE)['sets'] == []

    _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE])

    assert _row(solo['session'], RAISE)['sets'] == [], (
        'a skipped exercise carries no pending sets')


def test_reorder_after_a_late_deload_does_not_scale_only_the_rows_that_moved(solo):
    """Flagging a deload after the first set deliberately leaves the plan at
    working weight. A reorder then used to re-seed just the rows it moved --
    at the deload percentage -- and leave a half-scaled workout."""
    press = _row(solo['session'], PRESS)
    _post(solo['leader'], f"/gym/set/{press['set_ids'][0]}/toggle_complete",
          completed='1', weight=100, reps=5)
    _post(solo['leader'], f"/gym/session/{solo['session']}/deload", on='1', pct=60)

    _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE])

    raise_row = _row(solo['session'], RAISE)
    assert raise_row['sets'] == LEADER_RAISE_AT_3
    assert raise_row['base_weights'] == [None, None, None]


def test_reorder_moves_the_whole_substitute_chain(solo):
    """A substitute of a substitute: the visible row is two links away from
    the original, and all three share one slot."""
    from extensions import db
    from models import Exercise

    lifts = solo['lifts']
    with flask_app.app_context():
        extra = Exercise(name='pytest rs pushdown')
        db.session.add(extra)
        db.session.commit()
        extra_id = extra.id
        db.session.remove()
    row_id = _row(solo['session'], ROW)['id']
    _post(solo['leader'], f'/gym/session-exercise/{row_id}/replace', exercise_id=lifts[CURL])
    first_substitute = next(r for r in _rows(solo['session'])
                            if r['replaces_id'] == row_id)
    _post(solo['leader'], f"/gym/session-exercise/{first_substitute['id']}/replace",
          exercise_id=extra_id)
    chain = {row_id, first_substitute['id']}
    visible = next(r for r in _rows(solo['session']) if r['replaces_id'] == first_substitute['id'])
    chain.add(visible['id'])

    others = [r['id'] for r in _rows(solo['session']) if r['id'] not in chain]
    response = _client_for(solo['leader']).post(
        f"/gym/session/{solo['session']}/exercises/reorder",
        data={'order': ','.join(map(str, others + [visible['id']]))},
        headers={'Accept': 'application/json'})
    assert response.status_code == 200

    positions = {r['id']: r['position'] for r in _rows(solo['session'])}
    assert {positions[i] for i in chain} == {4}, positions
    assert sorted(positions[i] for i in others) == [1, 2, 3]


# --- removing an exercise: the slots stay 1..n --------------------------------

def test_removing_an_exercise_closes_the_gap(solo):
    """A hole in the numbering is what made the NEXT reorder -- even one that
    dropped a row back where it was -- renumber and re-seed everything after
    it, and what made the queue read 1, 3, 4."""
    _post(solo['leader'], f"/gym/session-exercise/{_row(solo['session'], ROW)['id']}/delete")

    assert [(r['name'], r['position']) for r in _rows(solo['session'])] == [
        (PRESS, 1), (RAISE, 2), (CURL, 3)]


def test_removing_an_exercise_reseeds_the_rows_that_moved_up(lifters):
    session_id = _start(lifters['leader'], lifters['leader_templates']['raise_last'])
    assert _row(session_id, RAISE)['sets'] == LEADER_RAISE_AT_4

    _post(lifters['leader'], f"/gym/session-exercise/{_row(session_id, CURL)['id']}/delete")

    raise_row = _row(session_id, RAISE)
    assert raise_row['position'] == 3
    assert raise_row['sets'] == LEADER_RAISE_AT_3


def test_removing_a_substitute_leaves_its_original_in_the_same_slot(solo):
    row_id = _row(solo['session'], ROW)['id']
    _post(solo['leader'], f'/gym/session-exercise/{row_id}/replace',
          exercise_id=solo['lifts'][CURL])
    substitute = next(r for r in _rows(solo['session']) if r['replaces_id'] == row_id)

    _post(solo['leader'], f"/gym/session-exercise/{substitute['id']}/delete")

    assert [(r['name'], r['position']) for r in _rows(solo['session'])] == [
        (PRESS, 1), (ROW, 2), (RAISE, 3), (CURL, 4)]


def test_posting_the_same_order_back_changes_nothing(solo):
    _post(solo['leader'], f"/gym/session-exercise/{_row(solo['session'], ROW)['id']}/delete")
    before = _rows(solo['session'])

    _reorder(solo['leader'], solo['session'], [r['name'] for r in before])

    assert _rows(solo['session']) == before


# --- a shared workout: the follower's own choices stick -----------------------
#
# Owner decision, 2026-09-20. The leader's changes carry what the leader
# CHANGED; they do not re-impose the leader's whole structure. Order is the
# exception -- it always follows the leader, which is what training together
# means -- so the follower cannot reorder, and cannot remove a shared exercise
# (they skip it instead).

def _swap_first_two(pair):
    """A change by the leader that has nothing to do with raise or curl."""
    _reorder(pair['leader'], pair['leader_session'], [ROW, PRESS, RAISE, CURL])


def test_the_followers_skip_survives_an_unrelated_change_by_the_leader(pair):
    raise_id = _row(pair['follower_session'], RAISE)['id']
    _post(pair['follower'], f'/gym/session-exercise/{raise_id}/skip')

    _swap_first_two(pair)

    after = _row(pair['follower_session'], RAISE)
    assert after['skipped'] is True, 'the leader\'s unrelated change un-skipped it'
    assert after['sets'] == []


def test_the_leaders_skip_carries_and_drops_the_followers_pending_sets(pair):
    _post(pair['leader'],
          f"/gym/session-exercise/{_row(pair['leader_session'], RAISE)['id']}/skip")

    after = _row(pair['follower_session'], RAISE)
    assert after['skipped'] is True
    assert after['sets'] == [], 'a skipped exercise carries no pending sets'


def test_the_leaders_unskip_carries_and_reseeds_from_the_followers_history(pair):
    leader_raise = _row(pair['leader_session'], RAISE)['id']
    _post(pair['leader'], f'/gym/session-exercise/{leader_raise}/skip')
    _post(pair['leader'], f'/gym/session-exercise/{leader_raise}/skip')

    after = _row(pair['follower_session'], RAISE)
    assert after['skipped'] is False
    assert after['sets'] == FOLLOWER_RAISE_AT_3


def test_the_followers_unskip_of_a_leader_skipped_exercise_survives(pair):
    _post(pair['leader'],
          f"/gym/session-exercise/{_row(pair['leader_session'], RAISE)['id']}/skip")
    follower_raise = _row(pair['follower_session'], RAISE)
    _post(pair['follower'], f"/gym/session-exercise/{follower_raise['id']}/skip")
    first_set = _row(pair['follower_session'], RAISE)['set_ids'][0]
    _post(pair['follower'], f'/gym/set/{first_set}/toggle_complete',
          completed='1', weight=35, reps=9)

    _swap_first_two(pair)

    after = _row(pair['follower_session'], RAISE)
    assert after['skipped'] is False, 'the follower chose to do it; that is theirs to choose'
    assert after['completed'][0] is True


def test_the_leaders_skip_leaves_an_exercise_the_follower_has_started_alone(pair):
    first_set = _row(pair['follower_session'], RAISE)['set_ids'][0]
    _post(pair['follower'], f'/gym/set/{first_set}/toggle_complete',
          completed='1', weight=35, reps=9)

    _post(pair['leader'],
          f"/gym/session-exercise/{_row(pair['leader_session'], RAISE)['id']}/skip")

    after = _row(pair['follower_session'], RAISE)
    assert after['skipped'] is False
    assert after['sets'] == FOLLOWER_RAISE_AT_3


def test_a_follower_cannot_reorder_while_linked(pair):
    before = [(r['name'], r['position']) for r in _rows(pair['follower_session'])]

    _reorder(pair['follower'], pair['follower_session'], [CURL, RAISE, ROW, PRESS])

    assert [(r['name'], r['position']) for r in _rows(pair['follower_session'])] == before


def test_a_follower_can_reorder_again_once_the_link_has_ended(pair):
    _client_for(pair['leader']).post(f"/gym/session/{pair['leader_session']}/finish")

    _reorder(pair['follower'], pair['follower_session'], [CURL, RAISE, ROW, PRESS])

    assert [r['name'] for r in _rows(pair['follower_session'])] == [CURL, RAISE, ROW, PRESS]


def test_a_follower_cannot_remove_a_shared_exercise_while_linked(pair):
    raise_id = _row(pair['follower_session'], RAISE)['id']

    _post(pair['follower'], f'/gym/session-exercise/{raise_id}/delete')

    assert RAISE in [r['name'] for r in _rows(pair['follower_session'])]


def test_a_follower_can_remove_an_exercise_they_added_themselves(pair):
    _post(pair['follower'], f"/gym/session/{pair['follower_session']}/exercises/add",
          exercise_id=pair['lifts'][OWN])
    own_id = _row(pair['follower_session'], OWN)['id']

    _post(pair['follower'], f'/gym/session-exercise/{own_id}/delete')

    assert OWN not in [r['name'] for r in _rows(pair['follower_session'])]


def test_the_followers_own_exercise_stays_after_the_shared_ones(pair):
    _post(pair['follower'], f"/gym/session/{pair['follower_session']}/exercises/add",
          exercise_id=pair['lifts'][OWN])

    _post(pair['leader'], f"/gym/session/{pair['leader_session']}/exercises/add",
          exercise_id=pair['lifts'][EXTRA])

    rows = _rows(pair['follower_session'])
    assert [(r['name'], r['position']) for r in rows] == [
        (PRESS, 1), (ROW, 2), (RAISE, 3), (CURL, 4), (EXTRA, 5), (OWN, 6)]


def test_the_followers_substitute_moves_with_the_exercise_it_replaced(pair):
    row_id = _row(pair['follower_session'], ROW)['id']
    _post(pair['follower'], f'/gym/session-exercise/{row_id}/replace',
          exercise_id=pair['lifts'][CABLE_ROW])

    _reorder(pair['leader'], pair['leader_session'], [PRESS, RAISE, CURL, ROW])

    rows = {r['name']: r for r in _rows(pair['follower_session'])}
    assert rows[ROW]['position'] == 4
    assert rows[CABLE_ROW]['position'] == 4, (
        'the substitute was left behind in the slot its original moved out of')
    assert sorted(r['position'] for r in rows.values()) == [1, 2, 3, 4, 4]


def test_the_leader_removing_an_exercise_keeps_the_followers_logged_sets(pair):
    first_set = _row(pair['follower_session'], RAISE)['set_ids'][0]
    _post(pair['follower'], f'/gym/set/{first_set}/toggle_complete',
          completed='1', weight=35, reps=9)

    _post(pair['leader'],
          f"/gym/session-exercise/{_row(pair['leader_session'], RAISE)['id']}/delete")

    rows = _rows(pair['follower_session'])
    kept = next((r for r in rows if r['name'] == RAISE), None)
    assert kept is not None, 'the leader\'s remove deleted work the follower had logged'
    assert kept['completed'][0] is True
    assert kept['mirrors_id'] is None, 'it is the follower\'s own exercise from here on'
    assert [(r['name'], r['position']) for r in rows] == [
        (PRESS, 1), (ROW, 2), (CURL, 3), (RAISE, 4)]


def test_the_leader_removing_an_untouched_exercise_removes_it_for_the_follower_too(pair):
    _post(pair['leader'],
          f"/gym/session-exercise/{_row(pair['leader_session'], RAISE)['id']}/delete")

    assert [(r['name'], r['position']) for r in _rows(pair['follower_session'])] == [
        (PRESS, 1), (ROW, 2), (CURL, 3)]


# --- two structural writes at once --------------------------------------------

def test_two_overlapping_reorders_end_as_one_of_them(solo, monkeypatch):
    """Two drops in quick succession on a slow link, or the arrow-key path
    (one POST per key press), put two reorders on the server at once. Each
    loaded the same starting order and wrote only the slots IT changed, so the
    result was a blend of both: two exercises in one slot, none in another.

    The barrier holds each request after it has read and rearranged but before
    it commits, which is the overlap made deterministic. Serialised requests
    never meet at it: the second is still waiting for the first's lock, so the
    first times out alone and carries on -- that timeout is the passing path.
    """
    import threading

    from features.gym.routes import workout

    meet = threading.Barrier(2, timeout=3)
    real = workout._close_position_gaps

    def held(session_):
        try:
            meet.wait()
        except threading.BrokenBarrierError:
            pass
        return real(session_)

    monkeypatch.setattr(workout, '_close_position_gaps', held)

    by_name = {r['name']: r['id'] for r in _rows(solo['session'])}
    orders = ([RAISE, PRESS, ROW, CURL], [PRESS, ROW, CURL, RAISE])
    statuses = []

    def drop(names):
        response = _client_for(solo['leader']).post(
            f"/gym/session/{solo['session']}/exercises/reorder",
            data={'order': ','.join(str(by_name[n]) for n in names)},
            headers={'Accept': 'application/json'})
        statuses.append(response.status_code)

    threads = [threading.Thread(target=drop, args=(names,)) for names in orders]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert statuses == [200, 200]
    rows = _rows(solo['session'])
    assert [r['position'] for r in rows] == [1, 2, 3, 4], (
        'two reorders blended into one numbering')
    assert [r['name'] for r in rows] in [list(order) for order in orders]
    assert [len(r['sets']) for r in sorted(rows, key=lambda r: r['name'])] == [2, 2, 3, 2]


def test_a_leaders_change_and_the_followers_own_add_do_not_share_a_slot(pair, monkeypatch):
    """The one write that crosses users. The leader's addition lands in the
    follower's session at the same moment the follower adds an exercise of
    their own; each computed "the next free slot" from the same rows."""
    import threading

    from features.gym import sharing
    from features.gym.routes import workout

    meet = threading.Barrier(2, timeout=3)

    def wait():
        try:
            meet.wait()
        except threading.BrokenBarrierError:
            pass

    real_reconcile = sharing.reconcile_follower
    real_seeded_sets = workout._seeded_sets

    def held_reconcile(shared):
        wait()
        return real_reconcile(shared)

    def held_seeded_sets(*args, **kwargs):
        # The leader's own add seeds too; only the follower's is the other
        # half of this overlap.
        if threading.current_thread().name == 'follower':
            wait()
        return real_seeded_sets(*args, **kwargs)

    monkeypatch.setattr(sharing, 'reconcile_follower', held_reconcile)
    monkeypatch.setattr(workout, '_seeded_sets', held_seeded_sets)

    statuses = []

    def add(user_id, session_id, exercise_id):
        response = _client_for(user_id).post(
            f'/gym/session/{session_id}/exercises/add',
            data={'exercise_id': exercise_id}, headers={'Accept': 'application/json'})
        statuses.append(response.status_code)

    threads = [
        threading.Thread(name='leader', target=add,
                         args=(pair['leader'], pair['leader_session'], pair['lifts'][EXTRA])),
        threading.Thread(name='follower', target=add,
                         args=(pair['follower'], pair['follower_session'], pair['lifts'][OWN])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert statuses == [200, 200]
    rows = _rows(pair['follower_session'])
    assert sorted(r['name'] for r in rows) == sorted(
        [PRESS, ROW, RAISE, CURL, EXTRA, OWN])
    assert [r['position'] for r in rows] == [1, 2, 3, 4, 5, 6]


def _payload(user_id, session_id):
    return _client_for(user_id).get(f'/gym/session/{session_id}/detail.json').get_json()


def _live_name(payload):
    return next((e['name'] for e in payload['visible_exercises']
                 if e['id'] == payload['live_id']), None)


# --- which exercise is live: the follower stays on what they started ----------

def test_a_follower_stays_on_the_exercise_they_started_when_the_leader_reorders(pair):
    """Owner decision 2026-09-20. The follower is physically AT an exercise;
    the leader dragging another one to the top used to swap the panel under
    their thumb within five seconds, and the next 'Satz geschafft' logged a
    set on a lift they never touched."""
    press = _row(pair['follower_session'], PRESS)
    _post(pair['follower'], f"/gym/set/{press['set_ids'][0]}/toggle_complete",
          completed='1', weight=60, reps=5)

    _reorder(pair['leader'], pair['leader_session'], [RAISE, PRESS, ROW, CURL])

    payload = _payload(pair['follower'], pair['follower_session'])
    assert [e['name'] for e in payload['visible_exercises']][0] == RAISE
    assert _live_name(payload) == PRESS


def test_the_leaders_order_takes_over_once_the_follower_finishes_what_they_started(pair):
    press = _row(pair['follower_session'], PRESS)
    _post(pair['follower'], f"/gym/set/{press['set_ids'][0]}/toggle_complete",
          completed='1', weight=60, reps=5)
    _reorder(pair['leader'], pair['leader_session'], [RAISE, PRESS, ROW, CURL])

    payload = _post(pair['follower'], f"/gym/set/{press['set_ids'][1]}/toggle_complete",
                    completed='1', weight=60, reps=5)

    assert _live_name(payload) == RAISE


def test_your_own_reorder_still_switches_you_away_from_a_started_exercise(solo):
    """Alone -- or leading -- the drag IS the instruction: the machine is
    taken after set one, so you pull another exercise above it."""
    press = _row(solo['session'], PRESS)
    _post(solo['leader'], f"/gym/set/{press['set_ids'][0]}/toggle_complete",
          completed='1', weight=100, reps=5)

    payload = _reorder(solo['leader'], solo['session'], [RAISE, PRESS, ROW, CURL])

    assert _live_name(payload) == RAISE


# --- where a plan's numbers come from, said out loud --------------------------

def _source(payload, name):
    row = next(e for e in payload['visible_exercises'] if e['name'] == name)
    return payload['seed_sources'][str(row['id'])]


def _days_ago(iso):
    """Whole days since `iso`, to the nearest day. MySQL rounds a DATETIME's
    fractional seconds UP, so a workout stored "5 days ago" can read back up
    to half a second later -- and a fast run then measured 4 days 23:59:59,
    which `.days` floors to 4."""
    delta = dt.datetime.utcnow() - dt.datetime.fromisoformat(iso)
    return round(delta.total_seconds() / 86400)


def test_the_payload_says_which_workout_a_plan_was_seeded_from(solo):
    source = _source(_payload(solo['leader'], solo['session']), RAISE)
    assert source['basis'] == 'slot'
    assert source['position'] == 3
    days_ago = _days_ago(source['date'])
    assert days_ago == 5


def test_the_source_carries_its_sets_and_whether_it_was_the_last_time(solo):
    """The Vorgabe is one line of numbers now (G-053): what was lifted that
    day, and "Letztes Mal" only when that workout really was the last one --
    the best at a later slot ten days ago is not what you did last time."""
    source = _source(_payload(solo['leader'], solo['session']), RAISE)
    assert source['is_latest'] is True
    assert [(s['weight'], s['reps']) for s in source['sets']] == LEADER_RAISE_AT_3

    source = _source(_reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE]), RAISE)
    assert (source['basis'], source['position']) == ('slot', 4)
    assert source['is_latest'] is False
    assert [(s['weight'], s['reps']) for s in source['sets']] == LEADER_RAISE_AT_4


def test_the_source_follows_the_exercise_to_its_new_slot(solo):
    payload = _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, RAISE])

    source = _source(payload, RAISE)
    assert (source['basis'], source['position']) == ('slot', 4)


def test_a_slot_later_than_any_history_says_it_fell_back_to_an_earlier_one(solo):
    """The owner kept 'best overall' as the fallback (2026-09-20) on the
    condition that the screen says so: nothing was ever lifted this late in a
    workout, so the numbers come from a fresher slot and may run heavy."""
    _post(solo['leader'], f"/gym/session/{solo['session']}/exercises/add",
          exercise_id=solo['lifts'][FILLER])

    payload = _reorder(solo['leader'], solo['session'], [PRESS, ROW, CURL, FILLER, RAISE])

    source = _source(payload, RAISE)
    assert (source['basis'], source['position']) == ('earlier_slot', 3)
    assert _row(solo['session'], RAISE)['sets'] == LEADER_RAISE_AT_3


def test_the_workout_in_progress_is_never_its_own_history(solo):
    """A set logged today is fresh and may well be the best e1RM on record --
    which made the running workout win its own seeding pick: the source line
    named today, and a second row of the same lift was seeded from the first."""
    raise_row = _row(solo['session'], RAISE)
    payload = _post(solo['leader'], f"/gym/set/{raise_row['set_ids'][0]}/toggle_complete",
                    completed='1', weight=60, reps=12)

    source = _source(payload, RAISE)
    days_ago = _days_ago(source['date'])
    assert days_ago == 5, 'the plan was seeded from the workout five days ago, not from today'

    _post(solo['leader'], f"/gym/session/{solo['session']}/exercises/add",
          exercise_id=solo['lifts'][RAISE])
    second = [r for r in _rows(solo['session']) if r['name'] == RAISE][-1]
    assert second['position'] == 5
    assert second['sets'] == LEADER_RAISE_AT_3, 'seeded from today\'s own sets'


def test_an_exercise_without_history_has_no_source(solo):
    payload = _post(solo['leader'], f"/gym/session/{solo['session']}/exercises/add",
                    exercise_id=solo['lifts'][FILLER])

    assert _source(payload, FILLER) is None


def test_a_layoff_says_the_plan_is_the_last_workout_not_the_best(solo):
    from extensions import db
    from models import Exercise, SessionExercise, SessionSet, WorkoutSession

    with flask_app.app_context():
        lift = Exercise(name='pytest rs stale lift')
        db.session.add(lift)
        db.session.flush()
        long_ago = dt.datetime.utcnow() - dt.timedelta(days=60)
        old = WorkoutSession(name='pytest rs history', user_id=solo['leader'],
                             started_at=long_ago, finished_at=long_ago + dt.timedelta(hours=1))
        row = SessionExercise(exercise_id=lift.id, position=2)
        row.sets = [SessionSet(position=1, weight=70.0, reps=6, completed=True)]
        old.exercises.append(row)
        db.session.add(old)
        db.session.commit()
        lift_id = lift.id
        db.session.remove()

    payload = _post(solo['leader'], f"/gym/session/{solo['session']}/exercises/add",
                    exercise_id=lift_id)

    source = _source(payload, 'pytest rs stale lift')
    assert (source['basis'], source['position']) == ('layoff', 2)


def test_the_payload_marks_which_rows_are_shared(pair):
    _post(pair['follower'], f"/gym/session/{pair['follower_session']}/exercises/add",
          exercise_id=pair['lifts'][OWN])

    payload = _client_for(pair['follower']).get(
        f"/gym/session/{pair['follower_session']}/detail.json").get_json()
    flags = {e['name']: e['mirrored'] for e in payload['visible_exercises']}
    assert flags == {PRESS: True, ROW: True, RAISE: True, CURL: True, OWN: False}

    leader_payload = _client_for(pair['leader']).get(
        f"/gym/session/{pair['leader_session']}/detail.json").get_json()
    assert not any(e['mirrored'] for e in leader_payload['visible_exercises'])
