"""The exercise page's payload (D9, M2) and its JSON endpoint.

The HTML route embeds it and detail.json serves it: both call
_exercise_detail_payload, so the page and a refresh after a settings change
cannot say two different things. Every part is the whole exercise; a pill
("Als N. Übung") lenses the Rekordtreppe alone, and every pill's stair comes
with the page.
"""
import datetime as dt

import pytest

from conftest import _admin_id, acting_as
from gym_lifter import lifter  # noqa: F401 -- the fixture

DAY = dt.timedelta(days=1)

FIELDS = {
    'exercise', 'table', 'goal', 'weights', 'pr_e1rm', 'trend', 'stairs', 'position_pills',
    'selected_position', 'state', 'sessions_since_pr', 'chip_class', 'chip_label', 'about',
    'equipment_labels', 'on_list', 'running', 'routines',
}

#: (slot, weight) per workout: first and third by turns, three each, and
#: second twice -- a stair of its own, one workout short of a pill.
THREE_SLOTS = [(1, 60), (3, 61), (1, 62), (3, 63), (1, 64), (3, 65), (2, 66), (2, 67)]


def _an_exercise_id():
    """The admin's first exercise with history of theirs."""
    from app import app as flask_app
    from features.gym.exercises import touched_exercises
    with flask_app.app_context():
        touched = sorted(touched_exercises(_admin_id()), key=lambda e: e.id)
        assert touched, 'the dev database needs a gym exercise the admin has logged'
        return touched[0].id


def _every_exercise_id():
    """Every row a lifter can open: the list, and anything retired."""
    from app import app as flask_app
    from models import Exercise
    with flask_app.app_context():
        return [e.id for e in Exercise.query.order_by(Exercise.id).all()]


def _lift(lifter, done):
    """An exercise done once per finished workout, a day apart and oldest
    first: `done` is (slot, weight) per workout, each a set of five."""
    from app import app as flask_app
    from extensions import db
    with flask_app.app_context():
        press = lifter.exercise('press')
        for index, (position, weight) in enumerate(done):
            workout = lifter.workout((len(done) - index) * DAY, finished=True)
            lifter.row(workout, press, position, done=[(weight, 5)])
        db.session.commit()
        return press.id


def _page(lifter, exercise_id, query=''):
    return lifter.client().get(f'/gym/exercises/{exercise_id}/detail.json{query}').get_json()


def test_returns_the_payload_shape(client):
    response = client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json')
    assert response.status_code == 200
    body = response.get_json()
    # Exactly these: the list is everyone's (no delete flag, no group picker),
    # and the chart, the slot the page chose and its reason are gone (D9).
    assert set(body) == FIELDS
    assert body['exercise']['id'] == _an_exercise_id()


def test_opens_on_alle_with_a_pill_per_slot_of_three_workouts(lifter):
    """D9: "Alle" is the default -- the page used to open on the slot it
    judged strongest and filter everything by it. A slot with fewer than
    three workouts gets no pill (G-036)."""
    exercise_id = _lift(lifter, THREE_SLOTS)
    page = _page(lifter, exercise_id)
    assert page['selected_position'] is None
    assert page['position_pills'] == [1, 3]
    assert [stair['position'] for stair in page['stairs']] == [None, 1, 3]
    assert [len(stair['cols']) for stair in page['stairs']] == [8, 3, 3]


def test_a_pill_lenses_the_stair_and_nothing_else(lifter):
    exercise_id = _lift(lifter, [(1, 60), (3, 61), (1, 62), (3, 63), (1, 64), (3, 65)])
    whole = _page(lifter, exercise_id)
    lensed = _page(lifter, exercise_id, '?position=3')
    assert lensed['selected_position'] == 3
    # The log, the record, the goal and every stair are the same page.
    assert {key: value for key, value in lensed.items() if key != 'selected_position'} \
        == {key: value for key, value in whole.items() if key != 'selected_position'}
    assert len(lensed['table']) == 6


@pytest.mark.parametrize('query', ['?position=2', '?position=all', '?position=x', '?position=9'])
def test_an_address_that_names_no_pill_opens_on_alle(lifter, query):
    exercise_id = _lift(lifter, THREE_SLOTS)
    assert _page(lifter, exercise_id, query)['selected_position'] is None


def test_a_lift_done_in_one_slot_gets_no_pills(lifter):
    # One pill would lens nothing: its stair is "Alle".
    exercise_id = _lift(lifter, [(2, 60 + n) for n in range(5)])
    page = _page(lifter, exercise_id, '?position=2')
    assert page['position_pills'] == []
    assert page['selected_position'] is None
    assert [stair['position'] for stair in page['stairs']] == [None]


def test_only_alle_says_the_drought_and_the_stall(lifter):
    """The drought is the lift's, not a slot's: under a pill the stair says
    no count. Six workouts without a record after the first: stagniert."""
    exercise_id = _lift(lifter, [(1, 70), (3, 60), (1, 61), (3, 62), (1, 63), (3, 64), (1, 65)])
    page = _page(lifter, exercise_id)
    assert page['state'] == 'stagniert'
    assert [(stair['since'], stair['stalled']) for stair in page['stairs']] == [
        (page['sessions_since_pr'], True), (None, False), (None, False)]
    assert page['sessions_since_pr'] == 6


def test_a_bodyweight_lift_has_no_record_and_no_drought(lifter):
    """G-038: five workouts at 0 kg are no failed attempts at a record --
    the page said "Noch kein Rekord" and then "Seit 4 Workouts ohne Rekord",
    and the header "Stagniert"."""
    exercise_id = _lift(lifter, [(1, 0.0)] * 5)
    page = _page(lifter, exercise_id)
    assert (page['pr_e1rm'], page['sessions_since_pr'], page['state'], page['stairs']) \
        == (None, None, None, [])
    assert len(page['table']) == 5


def test_a_lift_with_one_workout_draws_no_stair(lifter):
    exercise_id = _lift(lifter, [(1, 60)])
    page = _page(lifter, exercise_id)
    assert (page['stairs'], page['position_pills']) == ([], [])
    assert page['pr_e1rm']['weight'] == 60.0


def test_the_page_and_its_refresh_say_the_same(client):
    """The page embeds the payload so its first render needs no fetch, and a
    module script for the built bundle; detail.json is the same object."""
    import json
    import re

    exercise_id = _an_exercise_id()
    response = client.get(f'/gym/exercises/{exercise_id}')
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert '<div id="gym-root"></div>' in body
    assert re.search(r'<script type="module" src="/static/gym/dist/assets/exercise-[^"]+\.js">', body), \
        'the built bundle is not referenced -- run `npm run build` in personal_apps/'

    embedded = re.search(
        r'<script type="application/json" id="gym-data">(.*?)</script>', body, re.S)
    assert embedded, 'the payload is not embedded'
    assert json.loads(embedded.group(1)) \
        == client.get(f'/gym/exercises/{exercise_id}/detail.json').get_json()


def test_requires_a_login(anon_client):
    response = anon_client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json')
    assert response.status_code in (302, 401, 403)


def test_every_exercise_builds_a_valid_payload():
    """The guard the single-exercise tests above cannot provide, and what
    holds the schema to real output (extra='forbid' both ways).

    They pick the first exercise, which happens to have history, so they all
    passed while the payload raised for any exercise without it -- state is
    None for a stable lift and the schema had typed it str. Whichever exercise
    sorts first is not a sample.
    """
    from app import app as flask_app
    from features.gym.exercises import exercise_or_404
    from features.gym.routes import _exercise_detail_payload

    failures = []
    exercise_ids = _every_exercise_id()
    assert exercise_ids, 'the dev database needs gym exercises'
    with flask_app.app_context():
        with acting_as(_admin_id()):
            for exercise_id in exercise_ids:
                for raw_position in (None, 'all', '1'):
                    try:
                        _exercise_detail_payload(
                            exercise_or_404(exercise_id), raw_position)
                    except Exception as exc:
                        failures.append(f'{exercise_id} ({raw_position!r}): {exc}')

    assert not failures, 'payload failed for:\n' + '\n'.join(failures)


def test_every_exercise_page_renders(client):
    """Same breadth for the HTML route, which shares the helper. A 500 on an
    exercise with no history -- most of the list, for most lifters -- would
    otherwise reach the browser."""
    bad = [(i, client.get(f'/gym/exercises/{i}').status_code)
           for i in _every_exercise_id()]
    assert all(status == 200 for _, status in bad), \
        f'non-200 responses: {[p for p in bad if p[1] != 200]}'


def test_the_running_workout_stays_off_the_page(lifter):
    """A workout still running is not history yet (G-109, Q3), as on
    Übungen and Start: mid-workout the page already counted it, said "Seit 1
    Workout kein neuer e1RM-PR" and moved its projection with it."""
    from app import app as flask_app
    from extensions import db
    with flask_app.app_context():
        press = lifter.exercise('press')
        done = lifter.workout(dt.timedelta(days=3), finished=True)
        lifter.row(done, press, 1, done=[(60.0, 8), (60.0, 8)])
        running = lifter.workout(dt.timedelta(minutes=20))
        lifter.row(running, press, 1, done=[(80.0, 8)])
        db.session.commit()
        press_id = press.id

    page = _page(lifter, press_id)
    assert len(page['table']) == 1
    assert page['goal']['last_sets'] == [{'weight': 60.0, 'reps': 8}] * 2


def test_the_exercise_names_the_other_variants_of_its_movement():
    """M6 screen 2's "auch mit N Varianten": every other list entry of the
    movement, by what sets it apart, never the exercise itself."""
    from app import app as flask_app
    from features.gym.library import LIBRARY
    from features.gym.routes.exercise_detail import _about
    from models import Exercise

    with flask_app.test_request_context():
        rows = {row.library_key: row for row in
                Exercise.query.filter(Exercise.library_key.isnot(None)).all()}
        movements = {}
        for entry in LIBRARY:
            if entry.key in rows:
                movements.setdefault(entry.movement, []).append(entry)
        movement, entries = next((name, found) for name, found in movements.items() if len(found) >= 3)
        exercise = rows[entries[0].key]
        about = _about(exercise)
        others = sorted(((rows[e.key].id, e.label) for e in entries[1:]), key=lambda v: v[1].casefold())

    assert about['movement'] == movement
    assert [(variant['id'], variant['label']) for variant in about['variants']] == others
    assert about['picture'] is None or about['picture'].startswith('/static/gym/art/')


def test_an_exercise_off_the_list_has_nothing_to_say_about_itself(lifter):
    exercise_id = _lift(lifter, [(1, 60)])
    assert _page(lifter, exercise_id)['about'] == {'picture': None, 'movement': None, 'variants': []}
