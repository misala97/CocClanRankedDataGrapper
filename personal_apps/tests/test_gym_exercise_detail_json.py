"""The exercise-detail JSON endpoint.

It must agree with the HTML route about which position is selected -- they
share _exercise_detail_payload precisely so the default-slot rule cannot drift
between them. That rule is ~20 lines (best-performing slot with at least two
sessions, falling back to the most-used one), and two copies of it would
disagree the first time either was touched.
"""
import pytest

from conftest import _admin_id, acting_as


def _an_exercise_id():
    from app import app as flask_app
    from models import Exercise
    with flask_app.app_context():
        ex = (Exercise.query.filter_by(user_id=_admin_id())
              .order_by(Exercise.id).first())
        assert ex is not None, 'the dev database needs at least one gym exercise'
        return ex.id


def _an_exercise_with_history():
    """An exercise that actually has plotted sessions, so the position tests
    exercise the branch that matters rather than the empty one."""
    from app import app as flask_app
    from features.gym.routes import _exercise_detail_payload
    from features.gym.scope import my_exercises, owned_exercise
    with flask_app.app_context():
        with acting_as(_admin_id()):
            for exercise in my_exercises().all():
                payload = _exercise_detail_payload(owned_exercise(exercise.id), None)
                if len(payload.available_positions) > 1:
                    return exercise.id
    return None


def test_returns_the_payload_shape(client):
    response = client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json')
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) >= {
        'exercise', 'table', 'available_positions', 'selected_position',
        'chart', 'state', 'can_delete', 'muscle_groups', 'equipment_labels',
    }
    assert body['exercise']['id'] == _an_exercise_id()


def test_position_all_clears_the_filter(client):
    response = client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json?position=all')
    assert response.status_code == 200
    assert response.get_json()['selected_position'] is None


def test_an_explicit_position_is_honoured(client):
    exercise_id = _an_exercise_with_history()
    if exercise_id is None:
        pytest.skip('the dev database has no exercise used in two positions')

    body = client.get(f'/gym/exercises/{exercise_id}/detail.json').get_json()
    other = next(p for p in body['available_positions']
                 if p != body['selected_position'])

    scoped = client.get(
        f'/gym/exercises/{exercise_id}/detail.json?position={other}').get_json()
    assert scoped['selected_position'] == other
    assert all(row['position'] == other for row in scoped['table'])


def test_agrees_with_the_html_route_on_the_default_slot(client):
    """The whole reason the helper is shared. If these disagree, the page and
    any later refetch show different slots."""
    from app import app as flask_app
    from features.gym.routes import _exercise_detail_payload
    from features.gym.scope import owned_exercise

    exercise_id = _an_exercise_id()
    with flask_app.app_context():
        with acting_as(_admin_id()):
            direct = _exercise_detail_payload(owned_exercise(exercise_id), None)

    from_endpoint = client.get(f'/gym/exercises/{exercise_id}/detail.json').get_json()
    assert from_endpoint['selected_position'] == direct.selected_position
    assert from_endpoint['selected_position_is_default'] == direct.selected_position_is_default


def test_the_html_page_embeds_the_payload_and_the_bundle(client):
    """The page is a React shell: it carries the payload inline so the first
    render needs no fetch, and a module script for the built bundle. The body
    markup itself is now the island's, so there is nothing else to assert on
    here -- the components are covered by vitest."""
    import json
    import re

    response = client.get(f'/gym/exercises/{_an_exercise_id()}')
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert '<div id="gym-root"></div>' in body
    assert re.search(r'<script type="module" src="/static/gym/dist/assets/exercise-[^"]+\.js">', body), \
        'the built bundle is not referenced -- run `npm run build` in personal_apps/'

    embedded = re.search(
        r'<script type="application/json" id="gym-data">(.*?)</script>', body, re.S)
    assert embedded, 'the payload is not embedded'
    payload = json.loads(embedded.group(1))
    assert payload['exercise']['id'] == _an_exercise_id()
    assert 'table' in payload and 'chart' in payload


def test_requires_a_login(anon_client):
    response = anon_client.get(f'/gym/exercises/{_an_exercise_id()}/detail.json')
    assert response.status_code in (302, 401, 403)


def test_every_exercise_builds_a_valid_payload():
    """The guard the single-exercise tests above cannot provide.

    They pick the first exercise, which happens to have history, so they all
    passed while the payload raised for any exercise without it -- state is
    None for a stable lift and the schema had typed it str. Whichever exercise
    sorts first is not a sample.
    """
    from app import app as flask_app
    from features.gym.routes import _exercise_detail_payload
    from features.gym.scope import my_exercises, owned_exercise

    failures = []
    with flask_app.app_context():
        with acting_as(_admin_id()):
            exercise_ids = [e.id for e in my_exercises().all()]
            assert exercise_ids, 'the dev database needs gym exercises'
            for exercise_id in exercise_ids:
                for raw_position in (None, 'all'):
                    try:
                        _exercise_detail_payload(
                            owned_exercise(exercise_id), raw_position)
                    except Exception as exc:
                        failures.append(f'{exercise_id} ({raw_position!r}): {exc}')

    assert not failures, 'payload failed for:\n' + '\n'.join(failures)


def test_every_exercise_page_renders(client):
    """Same breadth for the HTML route, which shares the helper. A 500 on an
    exercise with no history would otherwise reach the browser."""
    from app import app as flask_app
    from features.gym.scope import my_exercises

    with flask_app.app_context():
        with acting_as(_admin_id()):
            exercise_ids = [e.id for e in my_exercises().all()]

    bad = [(i, client.get(f'/gym/exercises/{i}').status_code)
           for i in exercise_ids]
    assert all(status == 200 for _, status in bad), \
        f'non-200 responses: {[p for p in bad if p[1] != 200]}'
