"""Mutations answer in JSON when asked, and redirect otherwise.

The redirect half is not a formality: session_detail.html still posts plain
forms and refreshBody still parses the HTML that comes back. Breaking that
while adding the JSON path would take the live workout screen down.
"""
import datetime as dt

import pytest

from conftest import _admin_id


JSON = {'Accept': 'application/json'}
# What a browser actually sends when a <form> is submitted. The */* at the end
# is why the negotiation cannot test accept_json alone -- it makes accept_json
# true for this header too.
FORM = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}


def test_a_form_post_still_redirects(client, live_session):
    """The path the current page uses. If this breaks, the live workout
    screen breaks."""
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=FORM)
    assert response.status_code in (302, 303)


def test_a_json_request_gets_the_session_payload(client, live_session):
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=JSON)
    assert response.status_code == 200
    assert response.mimetype == 'application/json'
    body = response.get_json()
    assert body['session']['id'] == live_session['session']
    assert 'visible_exercises' in body


def test_the_payload_reflects_the_mutation(client, live_session):
    """The point of returning it: the client needs the post-mutation state,
    not the state it already had."""
    before = client.get(
        f"/gym/session/{live_session['session']}/detail.json").get_json()
    assert before['sets_done'] == 1

    after = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers=JSON).get_json()
    assert after['sets_done'] == 2


def test_a_bare_fetch_does_not_get_json(client, live_session):
    """fetch() with no Accept header sends */*, which accepts HTML too. The
    island has to opt in explicitly, and this pins that it must."""
    response = client.post(
        f"/gym/set/{live_session['open_set']}/toggle_complete",
        data={'completed': '1'}, headers={'Accept': '*/*'})
    assert response.status_code in (302, 303)


def test_every_in_place_mutation_negotiates(client, live_session):
    """Table-driven so a new mutation route added without negotiation shows up
    here rather than being discovered from the client side.

    The two deletes are excluded: they destroy the fixture's rows and would
    make every case after them order-dependent. Each has its own test below.
    """
    ids = live_session
    cases = [
        (f"/gym/session/{ids['session']}/exercises/add", {'exercise_id': str(ids['exercise'])}),
        (f"/gym/session-exercise/{ids['se']}/rest", {'rest_seconds': '90'}),
        (f"/gym/sessions/{ids['session']}/meta", {'notes': 'x'}),
        (f"/gym/session-exercises/{ids['se']}/meta", {'notes': 'x'}),
        (f"/gym/session-exercise/{ids['se']}/increment", {'weight_increment': '2.5'}),
        (f"/gym/session-exercise/{ids['se']}/sets/add", {}),
        # Before skip: toggling skip re-seeds the exercise's sets, so the
        # fixture's open_set id stops resolving after it and every later case
        # 404s on a row that no longer exists.
        (f"/gym/set/{ids['open_set']}/update", {'weight': '62.5', 'reps': '8'}),
        (f"/gym/session-exercise/{ids['se']}/skip", {}),
        (f"/gym/session/{ids['session']}/exercises/reorder", {'order': str(ids['se'])}),
        (f"/gym/session/{ids['session']}/rest/skip", {}),
    ]
    problems = []
    for url, data in cases:
        response = client.post(url, data=data, headers=JSON)
        if response.status_code != 200 or response.mimetype != 'application/json':
            problems.append(f'{url}: {response.status_code} {response.mimetype}')
    assert not problems, 'routes that did not answer in JSON:\n' + '\n'.join(problems)


def test_reordering_via_form_csv_actually_reorders(client, live_session):
    """The React island posts `order` as one comma-joined form field through
    its shared form path. Until 2026-08-11 the route read only a JSON body, so
    that post parsed to an empty order and reordered nothing -- and the
    negotiation case above kept passing because it never checked effect. This
    checks effect.
    """
    # The same exercise a second time: a second slot, but no new Exercise row
    # to leak past live_session's teardown into later tests.
    added = client.post(
        f"/gym/session/{live_session['session']}/exercises/add",
        data={'exercise_id': str(live_session['exercise'])}, headers=JSON).get_json()
    ids = [se['id'] for se in added['visible_exercises']]
    assert len(ids) == 2

    flipped = list(reversed(ids))
    after = client.post(
        f"/gym/session/{live_session['session']}/exercises/reorder",
        data={'order': ','.join(str(i) for i in flipped)}, headers=JSON).get_json()
    assert [se['id'] for se in after['visible_exercises']] == flipped
    assert [se['position'] for se in after['visible_exercises']] == [1, 2]


def test_deleting_a_set_answers_with_the_surviving_session(client, live_session):
    """A route that destroys part of the payload still answers with the
    payload of what survives -- that is exactly what the client re-renders
    from. The session is captured before the delete for that reason."""
    response = client.post(
        f"/gym/set/{live_session['open_set']}/delete", headers=JSON)
    assert response.status_code == 200
    assert response.mimetype == 'application/json'
    body = response.get_json()
    assert body['sets_total'] == 1


def test_deleting_an_exercise_answers_with_the_surviving_session(client, live_session):
    response = client.post(
        f"/gym/session-exercise/{live_session['se']}/delete", headers=JSON)
    assert response.status_code == 200
    body = response.get_json()
    assert body['visible_exercises'] == []


def test_the_two_navigations_still_redirect(client, live_session):
    """gym_start and gym_finish_session go to a different page. Answering
    either with a live-session payload would describe a session that is no
    longer live."""
    response = client.post(
        f"/gym/session/{live_session['session']}/finish", headers=JSON)
    assert response.status_code in (302, 303)


def test_a_finished_session_mutation_answers_with_the_debrief(client, temp_finished_session):
    """The island that asked gets the page it is on. A correction saved from
    the finished page must come back as FinishedPayload -- the live screen's
    shape wearing a finished_at would blank the debrief on the first save."""
    from features.gym.schemas import FinishedPayload
    from extensions import db
    from models import SessionExercise

    from app import app as flask_app

    session_id, se_id, _ = temp_finished_session
    with flask_app.app_context():
        set_id = next(s.id for s in db.session.get(SessionExercise, se_id).sets if s.completed)

    response = client.post(f'/gym/set/{set_id}/update',
                           data={'weight': '41.0', 'reps': '9'},
                           headers={'Accept': 'application/json'})
    assert response.status_code == 200
    body = response.get_json()
    # Validate the whole contract, not two spot fields.
    payload = FinishedPayload.model_validate(body)
    assert payload.session.id == session_id
    corrected = [s for e in payload.exercises for s in e.set_rows if s.id == set_id]
    assert corrected and corrected[0].weight == 41.0 and corrected[0].reps == 9
    # A POST carries no ?just_finished; the island preserves its own flag.
    assert payload.just_finished is False


def test_a_finished_session_form_post_still_redirects(client, temp_finished_session):
    """The negotiation must not swallow the no-JS path."""
    from extensions import db
    from models import SessionExercise

    from app import app as flask_app

    session_id, se_id, _ = temp_finished_session
    with flask_app.app_context():
        set_id = next(s.id for s in db.session.get(SessionExercise, se_id).sets if s.completed)

    response = client.post(f'/gym/set/{set_id}/update', data={'weight': '42.0', 'reps': '8'})
    assert response.status_code in (302, 303)


@pytest.fixture()
def temp_template():
    """A throwaway routine owned by the admin. Yields its id."""
    from app import app as flask_app
    from extensions import db
    from models import WorkoutTemplate
    with flask_app.app_context():
        template = WorkoutTemplate(name='ZZ mutation json routine', user_id=_admin_id())
        db.session.add(template)
        db.session.commit()
        template_id = template.id
    yield template_id
    with flask_app.app_context():
        doomed = db.session.get(WorkoutTemplate, template_id)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()


def test_renaming_a_routine_answers_with_the_fresh_start_page(client, temp_template):
    """The island edits in place, so the answer is the whole HeutePayload --
    the same shape a fresh load renders from, with the new name in it."""
    from features.gym.schemas import HeutePayload

    response = client.post(f'/gym/templates/{temp_template}/rename',
                           data={'name': 'ZZ renamed routine'},
                           headers={'Accept': 'application/json'})
    assert response.status_code == 200
    payload = HeutePayload.model_validate(response.get_json())
    assert 'ZZ renamed routine' in [t.name for t in payload.templates]

    # And no flash left queued for some unrelated later page load: the row
    # changing IS the feedback on this path.
    html = client.get('/gym').get_data(as_text=True)
    assert 'Routine heißt jetzt' not in html


def test_deleting_a_routine_answers_with_the_fresh_start_page(client, temp_template):
    from features.gym.schemas import HeutePayload

    response = client.post(f'/gym/templates/{temp_template}/delete',
                           headers={'Accept': 'application/json'})
    assert response.status_code == 200
    payload = HeutePayload.model_validate(response.get_json())
    assert temp_template not in [t.template_id for t in payload.templates]

    html = client.get('/gym').get_data(as_text=True)
    assert 'gelöscht' not in html


def test_a_form_post_rename_still_redirects_and_flashes(client, temp_template):
    """The no-JS path keeps its feedback."""
    response = client.post(f'/gym/templates/{temp_template}/rename',
                           data={'name': 'ZZ form renamed'})
    assert response.status_code in (302, 303)
    html = client.get('/gym').get_data(as_text=True)
    assert 'Routine heißt jetzt' in html


def test_creating_an_exercise_answers_with_the_fresh_catalogue(client):
    """The sheet closes and the new row arrives highlighted -- added_id in the
    payload, exactly what the ?added= redirect used to deliver."""
    from app import app as flask_app
    from extensions import db
    from features.gym.schemas import CataloguePayload
    from models import Exercise

    exercise_id = None
    try:
        response = client.post('/gym/exercises/add',
                               data={'name': 'ZZ json created lift'},
                               headers={'Accept': 'application/json'})
        assert response.status_code == 200
        payload = CataloguePayload.model_validate(response.get_json())
        names = [e.exercise.name for g in payload.groups for e in g.entries]
        assert 'ZZ json created lift' in names
        exercise_id = next(e.exercise.id for g in payload.groups for e in g.entries
                           if e.exercise.name == 'ZZ json created lift')
        assert payload.added_id == exercise_id
        assert payload.name_taken is False

        # The collision is a page state, not an exception: same 200, banner up.
        collision = client.post('/gym/exercises/add',
                                data={'name': 'ZZ json created lift'},
                                headers={'Accept': 'application/json'})
        assert collision.status_code == 200
        assert CataloguePayload.model_validate(collision.get_json()).name_taken is True
    finally:
        with flask_app.app_context():
            doomed = db.session.get(Exercise, exercise_id) if exercise_id else None
            if doomed is not None:
                db.session.delete(doomed)
                db.session.commit()
