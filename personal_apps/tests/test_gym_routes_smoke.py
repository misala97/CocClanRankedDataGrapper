"""Smoke checks that every gym GET route renders. Needs the real database, so
these are run manually rather than in the pure-stats suite."""
import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['logged_in'] = True
        yield test_client


def test_dashboard_renders(client):
    assert client.get('/gym').status_code == 200


def test_exercise_detail_renders_for_every_exercise(client):
    with flask_app.app_context():
        from models import Exercise
        ids = [row.id for row in Exercise.query.all()]
    for exercise_id in ids:
        response = client.get('/gym/exercises/{}'.format(exercise_id))
        assert response.status_code == 200, exercise_id


def test_session_pages_render_for_every_finished_session(client):
    with flask_app.app_context():
        from models import WorkoutSession
        ids = [row.id for row in WorkoutSession.query.filter(
            WorkoutSession.finished_at.isnot(None)).all()]
    for session_id in ids:
        assert client.get('/gym/session/{}'.format(session_id)).status_code == 200
        assert client.get('/gym/session/{}/summary'.format(session_id)).status_code == 200
