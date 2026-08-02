"""Per-user exercise catalogues.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import pytest

from app import app as flask_app
from conftest import _admin_id


def test_the_exercise_table_carries_an_owner():
    from models import Exercise
    assert hasattr(Exercise, 'user_id'), 'Exercise has no user_id'
    assert Exercise.__table__.c.user_id.nullable is False, 'Exercise.user_id must be NOT NULL'


def test_every_pre_existing_exercise_was_backfilled_to_the_admin():
    from models import AppUser, Exercise
    with flask_app.app_context():
        admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
        assert admin is not None
        orphans = Exercise.query.filter(
            Exercise.user_id != admin.id,
            Exercise.name.notlike('pytest%'),
        ).count()
        assert orphans == 0, 'Exercise has rows not owned by the admin'


def test_two_users_can_hold_an_exercise_with_the_same_name():
    """The constraint swap: unique(name) globally would reject this outright."""
    from extensions import db
    from models import AppUser, Exercise
    from werkzeug.security import generate_password_hash

    created = []
    try:
        with flask_app.app_context():
            other = AppUser(username='pytest samename user',
                            password_hash=generate_password_hash('irrelevant'),
                            is_admin=False)
            db.session.add(other)
            db.session.flush()
            mine = Exercise(name='pytest shared name lift', user_id=_admin_id())
            theirs = Exercise(name='pytest shared name lift', user_id=other.id)
            db.session.add_all([mine, theirs])
            db.session.commit()
            created = [mine.id, theirs.id, other.id]
            assert mine.id != theirs.id
    finally:
        with flask_app.app_context():
            for exercise_id in created[:2]:
                doomed = db.session.get(Exercise, exercise_id)
                if doomed is not None:
                    db.session.delete(doomed)
            db.session.commit()
            if len(created) == 3:
                doomed_user = db.session.get(AppUser, created[2])
                if doomed_user is not None:
                    db.session.delete(doomed_user)
                    db.session.commit()


@pytest.fixture()
def two_lifters():
    """An admin-owned exercise and a second account that owns nothing.

    Yields {'owner_id', 'stranger_id', 'exercise_id'}.
    """
    from extensions import db
    from models import AppUser, Exercise
    from werkzeug.security import generate_password_hash

    ids = {}
    with flask_app.app_context():
        stranger = AppUser(username='pytest catalogue stranger',
                           password_hash=generate_password_hash('irrelevant'),
                           is_admin=False)
        db.session.add(stranger)
        db.session.flush()
        exercise = Exercise(name='pytest owned lift', muscle_group='Brust',
                            weight_increment=9.0, user_id=_admin_id())
        db.session.add(exercise)
        db.session.commit()
        ids = {'owner_id': _admin_id(), 'stranger_id': stranger.id,
               'exercise_id': exercise.id}
    yield ids
    with flask_app.app_context():
        doomed = db.session.get(Exercise, ids['exercise_id'])
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()
        doomed_user = db.session.get(AppUser, ids['stranger_id'])
        if doomed_user is not None:
            db.session.delete(doomed_user)
            db.session.commit()


@pytest.fixture()
def stranger_client(two_lifters):
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_lifters['stranger_id']
        yield test_client


def test_a_new_accounts_exercise_list_is_empty(stranger_client, two_lifters):
    """The whole point of the change: she opens the picker and sees nothing of
    theirs, not thirty lifts she will never do."""
    body = stranger_client.get('/gym/uebungen').get_data(as_text=True)
    assert 'pytest owned lift' not in body


def test_the_owner_still_sees_their_own_exercise(two_lifters):
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_lifters['owner_id']
        body = owner_client.get('/gym/uebungen').get_data(as_text=True)
    assert 'pytest owned lift' in body, 'scoping hid the owner from their own catalogue'


def test_adding_an_exercise_whose_name_another_user_has_creates_your_own(
        stranger_client, two_lifters):
    """Unscoped, the name lookup finds the other user's row and the route
    redirects with name_taken -- so she could never create her own 'Bankdruecken',
    and any path that linked instead of created would hand her their increment
    and put her sets in their history."""
    from extensions import db
    from models import Exercise

    response = stranger_client.post('/gym/exercises/add', data={
        'name': 'pytest owned lift', 'muscle_group': 'Brust'})
    assert response.status_code in (302, 303)

    created_id = None
    try:
        with flask_app.app_context():
            hers = Exercise.query.filter_by(name='pytest owned lift',
                                            user_id=two_lifters['stranger_id']).first()
            assert hers is not None, 'the name lookup matched another user and refused'
            created_id = hers.id
            assert hers.id != two_lifters['exercise_id'], 'linked to their row instead of creating'
            assert hers.weight_increment is None, 'inherited their increment'
    finally:
        with flask_app.app_context():
            if created_id is not None:
                doomed = db.session.get(Exercise, created_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
