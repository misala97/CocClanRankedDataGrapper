"""M6 (D13-A; I6): Übungen lists the lifter's exercises, then the rest of
the list, "Noch nie gemacht" (G-004, G-013); an exercise's page offers its
two ways on, into a workout and into a routine (G-041)."""
import datetime as dt

from sqlalchemy import event

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from features.gym.library import BY_KEY, LIBRARY, LIST_GROUPS, MOVEMENT_GROUP
from features.gym.routes import session_admin
from features.gym.stats import NO_GROUP_LABEL
from gym_lifter import lifter  # noqa: F401 -- the fixture
from models import Exercise, SessionExercise, TemplateExercise, WorkoutSession

MIN = dt.timedelta(minutes=1)
DAY = dt.timedelta(days=1)
JSON = {'Accept': 'application/json'}

SQUAT = 'Kniebeugen (Langhantel)'
BENCH = 'Bankdrücken (Kurzhantel)'
PULLDOWN = 'Latzug (Kabel)'


def _listed(name):
    """The list's own row of `name`."""
    entry = next(entry for entry in LIBRARY if entry.name == name)
    return Exercise.query.filter_by(library_key=entry.key).one()


def _uebungen(lifter, user_id=None):
    response = lifter.client(user_id).get('/gym/uebungen')
    assert response.status_code == 200
    return embedded_payload(response.get_data(as_text=True))


def _page(lifter, exercise_id):
    response = lifter.client().get(f'/gym/exercises/{exercise_id}/detail.json')
    assert response.status_code == 200
    return response.get_json()


def _queries(call):
    """(response, number of SQL statements) for `call()`."""
    seen = []

    def count(*_args):
        seen.append(1)

    with flask_app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', count)
    try:
        response = call()
    finally:
        event.remove(engine, 'before_cursor_execute', count)
    assert response.status_code == 200, response.status_code
    return response, len(seen)


# --- Übungen ------------------------------------------------------------------

def test_uebungen_lists_the_rest_of_the_list_after_yours(lifter):
    with flask_app.app_context():
        bench = _listed(BENCH)
        own = lifter.exercise('leg thing', muscle_group='Beine')
        workout = lifter.workout(2 * DAY, finished=True)
        lifter.row(workout, bench, 1, done=[(20, 10)])
        lifter.row(workout, own, 2, done=[(50, 8)])
        db.session.commit()
        bench_id, own_id = bench.id, own.id
        every = {exercise.id: exercise.library_key
                 for exercise in Exercise.query.filter(
                     Exercise.library_key.in_([entry.key for entry in LIBRARY]))}

    payload = _uebungen(lifter)
    # The list's order, every group of it, an empty one too (G-013).
    assert [group['name'] for group in payload['groups']] == list(LIST_GROUPS)
    assert payload['list_groups'] == list(LIST_GROUPS)
    bands = {group['name']: [entry['exercise']['id'] for entry in group['entries']]
             for group in payload['groups']}
    assert bands['Brust'] == [bench_id] and bands['Beine'] == [own_id]
    assert all(not ids for name, ids in bands.items() if name not in ('Brust', 'Beine'))
    pictures = {entry['exercise']['id']: entry['picture']
                for group in payload['groups'] for entry in group['entries']}
    assert pictures[bench_id].startswith('/static/gym/art/') and pictures[own_id] is None

    # The rest: every list exercise but yours, with its movement and band.
    rest = {entry['id']: entry for entry in payload['library']}
    assert set(rest) == set(every) - {bench_id}
    for exercise_id, entry in rest.items():
        listed = BY_KEY[every[exercise_id]]
        assert (entry['name'], entry['movement'], entry['label'], entry['movement_group']) == (
            listed.name, listed.movement, listed.label, MOVEMENT_GROUP[listed.movement])
        assert entry['search'] == listed.search_text
        assert entry['picture'].startswith('/static/gym/art/')
    assert set(next(iter(rest.values()))) == {
        'id', 'name', 'movement', 'label', 'movement_group', 'search', 'picture'}


def test_a_new_lifter_is_offered_the_whole_list(lifter):
    """G-004: "Noch keine Übungen" and a button to Start, while 158
    exercises waited behind a workout."""
    payload = _uebungen(lifter)
    assert [group['entries'] for group in payload['groups']] == [[]] * len(LIST_GROUPS)
    assert len(payload['library']) == len(LIBRARY)


def test_groups_off_the_list_order_come_after_it(lifter):
    """Cardio and Sonstiges only when filled, then anything else."""
    with flask_app.app_context():
        cardio = lifter.exercise('rower', muscle_group='Cardio')
        none = lifter.exercise('mystery', muscle_group=None)
        workout = lifter.workout(DAY, finished=True)
        lifter.row(workout, cardio, 1, done=[(0, 10)])
        lifter.row(workout, none, 2, done=[(10, 10)])
        db.session.commit()

    names = [group['name'] for group in _uebungen(lifter)['groups']]
    assert names == [*LIST_GROUPS, 'Cardio', NO_GROUP_LABEL]


def test_a_routine_or_a_setting_makes_an_exercise_yours(lifter):
    """Yours is what you logged, keep in a routine or set up: none of it is
    listed again under "Noch nie gemacht"."""
    with flask_app.app_context():
        squat, pulldown = _listed(SQUAT), _listed(PULLDOWN)
        lifter.routine('legs', [squat])
        db.session.commit()
        squat_id, pulldown_id = squat.id, pulldown.id
    lifter.client().post(f'/gym/exercises/{pulldown_id}/update',
                         data={'default_rest_seconds': '90'})

    payload = _uebungen(lifter)
    yours = {entry['exercise']['id'] for group in payload['groups'] for entry in group['entries']}
    rest = {entry['id'] for entry in payload['library']}
    assert {squat_id, pulldown_id} <= yours
    assert not {squat_id, pulldown_id} & rest


def test_uebungen_knows_what_the_running_workout_lifted_of_yours(lifter):
    """The rows read finished workouts only, so a first go, sets in, said
    "Noch kein Satz" while its page said "Heute im laufenden Workout". A
    replaced original's sets count (Q1), a tick without reps does not."""
    with flask_app.app_context():
        squat, bench, pulldown = _listed(SQUAT), _listed(BENCH), _listed(PULLDOWN)
        done = lifter.workout(2 * DAY, finished=True)
        lifter.row(done, bench, 1, done=[(20, 10)])
        workout = lifter.workout(20 * MIN)
        lifter.row(workout, squat, 1, done=[(60, 5)])
        replaced = lifter.row(workout, pulldown, 2, done=[(40, 10)])
        lifter.row(workout, squat, 3, replaces=replaced)
        lifter.row(workout, bench, 4, ticked_empty=1)
        db.session.commit()
        squat_id, bench_id, pulldown_id = squat.id, bench.id, pulldown.id

    def lifted(payload):
        return {entry['exercise']['id']: entry['in_running']
                for group in payload['groups'] for entry in group['entries']}

    assert lifted(_uebungen(lifter)) == {squat_id: True, pulldown_id: True, bench_id: False}

    with flask_app.app_context():
        running = WorkoutSession.query.filter_by(user_id=lifter.user_id, finished_at=None).one()
        running.finished_at = dt.datetime.utcnow()
        db.session.commit()
    assert set(lifted(_uebungen(lifter)).values()) == {False}


# --- The exercise's page ------------------------------------------------------

def test_the_page_knows_the_running_workout_and_what_it_holds_of_the_exercise(lifter):
    """Counted as the add sheet counts it: the visible rows, a skipped one
    too, never a replaced original. What was lifted of it today is what the
    page will show once the workout is finished: the sets that count (Q1),
    a replaced original's among them, a tick without reps never."""
    with flask_app.app_context():
        squat, pulldown = _listed(SQUAT), _listed(PULLDOWN)
        workout = lifter.workout(20 * MIN)
        lifter.row(workout, squat, 1, done=[(60, 5)], open_=2)
        replaced = lifter.row(workout, squat, 2, done=[(50, 5), (50, 5)])
        lifter.row(workout, pulldown, 3, replaces=replaced)
        lifter.row(workout, squat, 4, skipped=True, ticked_empty=1)
        db.session.commit()
        workout_id, squat_id, pulldown_id = workout.id, squat.id, pulldown.id

    # 1 + 2: the replaced row's two; not the empty tick (4 with it, 1
    # without the replaced row's).
    assert _page(lifter, squat_id)['running'] == {
        'session_id': workout_id, 'name': 'pytest gym', 'count': 2, 'logged': 3}
    assert _page(lifter, pulldown_id)['running'] == {
        'session_id': workout_id, 'name': 'pytest gym', 'count': 1, 'logged': 0}

    with flask_app.app_context():
        db.session.get(WorkoutSession, workout_id).name = None
        db.session.commit()
    assert _page(lifter, squat_id)['running']['name'] is None


def test_without_a_running_workout_the_page_offers_to_begin_one(lifter):
    with flask_app.app_context():
        squat = _listed(SQUAT)
        workout = lifter.workout(DAY, finished=True)
        lifter.row(workout, squat, 1, done=[(60, 5)])
        db.session.commit()
        squat_id = squat.id
    assert _page(lifter, squat_id)['running'] is None


def test_the_page_says_only_the_lifters_own_running_workout(lifter):
    """A partner's running workout, the squat in it, is not the lifter's:
    not named, not counted, not added to."""
    with flask_app.app_context():
        squat = _listed(SQUAT)
        theirs = lifter.workout(5 * MIN, user_id=lifter.partner())
        lifter.row(theirs, squat, 1, done=[(60, 5)])
        db.session.commit()
        squat_id = squat.id
    assert _page(lifter, squat_id)['running'] is None

    with flask_app.app_context():
        mine = lifter.workout(20 * MIN)
        db.session.commit()
        mine_id = mine.id
    assert _page(lifter, squat_id)['running'] == {
        'session_id': mine_id, 'name': 'pytest gym', 'count': 0, 'logged': 0}


def test_the_page_lists_the_lifters_routines_a_to_z_and_says_which_hold_it(lifter):
    with flask_app.app_context():
        squat, bench, pulldown = _listed(SQUAT), _listed(BENCH), _listed(PULLDOWN)
        lifter.routine('Beine', [squat, pulldown])
        lifter.routine('arme', [bench])
        stranger = lifter.partner()
        lifter.routine('theirs', [squat], user_id=stranger)
        db.session.commit()
        squat_id = squat.id

    routines = _page(lifter, squat_id)['routines']
    assert [(r['name'], r['count'], r['has']) for r in routines] == [
        ('pytest gym arme', 1, False), ('pytest gym Beine', 2, True)]
    assert set(routines[0]) == {'id', 'name', 'count', 'has'}


def test_only_an_exercise_on_the_list_is_offered_a_way_on(lifter):
    with flask_app.app_context():
        squat = _listed(SQUAT)
        retired = lifter.exercise('retired')
        db.session.commit()
        squat_id, retired_id = squat.id, retired.id
    assert _page(lifter, squat_id)['on_list'] is True
    assert _page(lifter, retired_id)['on_list'] is False


def test_the_page_costs_the_same_for_eight_routines_as_for_two(lifter):
    """And for five rows of the exercise in the running workout as for one."""
    with flask_app.app_context():
        squat, bench = _listed(SQUAT), _listed(BENCH)
        for n in range(2):
            lifter.routine(f'r{n}', [squat, bench])
        workout = lifter.workout(10 * MIN)
        lifter.row(workout, squat, 1, done=[(60, 5)])
        db.session.commit()
        squat_id = squat.id
    client = lifter.client()

    def page():
        return client.get(f'/gym/exercises/{squat_id}')

    page()
    _, few = _queries(page)
    with flask_app.app_context():
        squat, bench = _listed(SQUAT), _listed(BENCH)
        for n in range(2, 8):
            lifter.routine(f'r{n}', [squat, bench])
        workout = WorkoutSession.query.filter_by(user_id=lifter.user_id).one()
        for position in range(2, 6):
            lifter.row(workout, squat, position, done=[(60, 5)])
        db.session.commit()
    body, many = _queries(page)
    assert embedded_payload(body.get_data(as_text=True))['running']['count'] == 5
    assert many == few


# --- "Zur Routine" --------------------------------------------------------------

def _add_to_routine(lifter, template_id, exercise_id, user_id=None, headers=JSON):
    return lifter.client(user_id).post(f'/gym/templates/{template_id}/exercises/add',
                                       data={'exercise_id': exercise_id}, headers=headers)


def _rows(template_id):
    with flask_app.app_context():
        rows = (TemplateExercise.query.filter_by(template_id=template_id)
                .order_by(TemplateExercise.position).all())
        return [(row.exercise_id, row.position, row.target_sets, row.rep_min, row.rep_max)
                for row in rows]


def test_zur_routine_puts_the_exercise_at_the_end_with_its_plan_left_to_the_next_start(lifter):
    with flask_app.app_context():
        bench, squat = _listed(BENCH), _listed(SQUAT)
        routine = lifter.routine('push', [bench], plan={bench.id: (3, 8, 12)})
        db.session.commit()
        routine_id, bench_id, squat_id = routine.id, bench.id, squat.id

    response = _add_to_routine(lifter, routine_id, squat_id)
    assert response.status_code == 200
    assert response.get_json() == {'routines': [
        {'id': routine_id, 'name': 'pytest gym push', 'count': 2, 'has': True}]}
    assert _rows(routine_id) == [(bench_id, 1, 3, 8, 12), (squat_id, 2, None, None, None)]


def test_zur_routine_twice_adds_it_once(lifter):
    """The plan is read from one row per exercise: a double tap, or a second
    tab, gets the same answer and no second row."""
    with flask_app.app_context():
        bench, squat = _listed(BENCH), _listed(SQUAT)
        routine = lifter.routine('push', [bench, squat])
        db.session.commit()
        routine_id, bench_id, squat_id = routine.id, bench.id, squat.id

    response = _add_to_routine(lifter, routine_id, squat_id)
    assert response.status_code == 200
    assert response.get_json()['routines'][0]['has'] is True
    assert _rows(routine_id) == [(bench_id, 1, None, None, None), (squat_id, 2, None, None, None)]


def test_zur_routine_refuses_what_it_cannot_add(lifter):
    with flask_app.app_context():
        squat = _listed(SQUAT)
        retired = lifter.exercise('retired')
        mine = lifter.routine('mine', [])
        stranger = lifter.partner()
        theirs = lifter.routine('theirs', [], user_id=stranger)
        db.session.commit()
        squat_id, retired_id, mine_id, theirs_id = squat.id, retired.id, mine.id, theirs.id

    assert _add_to_routine(lifter, theirs_id, squat_id).status_code == 404
    assert _add_to_routine(lifter, mine_id, 10 ** 9).status_code == 404
    assert _add_to_routine(lifter, mine_id, retired_id).status_code == 400
    assert lifter.client().post(f'/gym/templates/{mine_id}/exercises/add',
                                data={}).status_code == 400
    assert _rows(mine_id) == [] and _rows(theirs_id) == []


def test_zur_routine_without_script_goes_back_to_the_exercise(lifter):
    with flask_app.app_context():
        squat = _listed(SQUAT)
        routine = lifter.routine('legs', [])
        db.session.commit()
        routine_id, squat_id = routine.id, squat.id
    response = _add_to_routine(lifter, routine_id, squat_id, headers={})
    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/gym/exercises/{squat_id}')
    assert [row[0] for row in _rows(routine_id)] == [squat_id]


def test_zur_routine_takes_the_lifters_lock_before_it_reads_the_routine(lifter, monkeypatch):
    """Two taps at once must not both find the routine without the exercise."""
    with flask_app.app_context():
        squat = _listed(SQUAT)
        routine = lifter.routine('legs', [])
        db.session.commit()
        routine_id, squat_id = routine.id, squat.id
    steps = []
    lock, owned = session_admin.lock_user, session_admin.owned_template
    monkeypatch.setattr(session_admin, 'lock_user',
                        lambda user_id: (steps.append(('lock', user_id)), lock(user_id))[1])
    monkeypatch.setattr(session_admin, 'owned_template',
                        lambda template_id: (steps.append(('read', template_id)),
                                             owned(template_id))[1])
    assert _add_to_routine(lifter, routine_id, squat_id).status_code == 200
    assert steps == [('lock', lifter.user_id), ('read', routine_id)]


# --- "Workout damit beginnen" -----------------------------------------------------

def _start(lifter, **fields):
    return lifter.client().post('/gym/start', data=fields)


def _flashes(client):
    """What the next page will say, as (category, message) pairs."""
    with client.session_transaction() as flask_session:
        return [tuple(flashed) for flashed in flask_session.get('_flashes', [])]


def _workouts(lifter):
    with flask_app.app_context():
        return [(w.id, w.name, w.template_id, w.finished_at is None,
                 [(row.exercise_id, row.position, len(row.sets),
                   sum(1 for s in row.sets if s.completed)) for row in w.exercises])
                for w in WorkoutSession.query.filter_by(user_id=lifter.user_id)
                .order_by(WorkoutSession.id)]


def test_workout_damit_beginnen_starts_a_free_workout_with_the_exercise(lifter):
    with flask_app.app_context():
        squat = _listed(SQUAT)
        db.session.commit()
        squat_id = squat.id

    response = _start(lifter, exercise_id=squat_id)
    [(workout_id, name, template_id, running, rows)] = _workouts(lifter)
    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/gym/session/{workout_id}')
    assert (name, template_id, running) == (None, None, True)
    # Seeded as a routine's rows are: sets to lift, none lifted.
    [(exercise_id, position, sets, completed)] = rows
    assert (exercise_id, position, completed) == (squat_id, 1, 0) and sets > 0


def test_a_workout_begun_elsewhere_sends_the_lifter_back_to_the_exercise(lifter):
    """Not entered with nothing of it, not appended to unasked: the page,
    read again, offers "Zu „…“ hinzufügen"."""
    with flask_app.app_context():
        squat, bench = _listed(SQUAT), _listed(BENCH)
        workout = lifter.workout(10 * MIN)
        lifter.row(workout, bench, 1, open_=3)
        db.session.commit()
        squat_id, workout_id = squat.id, workout.id
    before = _workouts(lifter)

    client = lifter.client()
    response = client.post('/gym/start', data={'exercise_id': squat_id})
    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/gym/exercises/{squat_id}')
    assert _workouts(lifter) == before
    # Told why: the button it tapped is another now.
    assert _flashes(client) == [
        ('error', 'Es läuft schon ein Workout — die Übung lässt sich dort hinzufügen.')]
    # Start's own button still goes into the running workout, unflashed.
    plain = lifter.client()
    assert plain.post('/gym/start').headers['Location'].endswith(f'/gym/session/{workout_id}')
    assert _flashes(plain) == []


def test_a_workout_finished_elsewhere_sends_the_lifter_back_to_the_exercise(lifter):
    """"Zu „…“ hinzufügen" read before the workout was finished on another
    phone: back to the page, which now offers to begin one, told why -- it
    landed on the debrief, without the exercise and without a word."""
    with flask_app.app_context():
        squat, bench = _listed(SQUAT), _listed(BENCH)
        workout = lifter.workout(DAY, finished=True)
        lifter.row(workout, bench, 1, done=[(20, 10)])
        db.session.commit()
        squat_id, workout_id = squat.id, workout.id
    before = _workouts(lifter)
    url = f'/gym/session/{workout_id}/exercises/add'

    client = lifter.client()
    response = client.post(url, data={'exercise_id': squat_id, 'back': 'exercise'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/gym/exercises/{squat_id}')
    assert _flashes(client) == [('error', 'Das Workout ist schon beendet — nichts hinzugefügt.')]
    assert _workouts(lifter) == before
    # Anyone else asking gets what they always got: the debrief, unflashed,
    # or a 409.
    plain = lifter.client()
    response = plain.post(url, data={'exercise_id': squat_id})
    assert response.headers['Location'].endswith(f'/gym/session/{workout_id}')
    assert _flashes(plain) == []
    response = lifter.client().post(url, data={'exercise_id': squat_id, 'back': 'exercise'},
                                    headers=JSON)
    assert response.status_code == 409
    assert _workouts(lifter) == before


def test_workout_damit_beginnen_refuses_what_it_cannot_begin(lifter):
    with flask_app.app_context():
        squat = _listed(SQUAT)
        retired = lifter.exercise('retired')
        routine = lifter.routine('legs', [squat])
        db.session.commit()
        squat_id, retired_id, routine_id = squat.id, retired.id, routine.id

    assert _start(lifter, exercise_id=retired_id).status_code == 400
    assert _start(lifter, exercise_id=squat_id, template_id=routine_id).status_code == 400
    assert _start(lifter, exercise_id=10 ** 9).status_code == 404
    assert _workouts(lifter) == []
