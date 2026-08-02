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


def test_adding_a_session_exercise_by_name_does_not_link_to_another_users_exercise(
        stranger_client, two_lifters):
    """gym_add_session_exercise is find-or-create, not find-or-refuse like
    gym_add_exercise above. Unscoped, the find half would have matched the
    owner's 'pytest owned lift' and attached the stranger's session to that
    row -- handing her their weight_increment and writing her sets into
    their history."""
    import datetime as dt

    from extensions import db
    from models import Exercise, SessionExercise, WorkoutSession

    session_id = None
    created_exercise_id = None
    try:
        with flask_app.app_context():
            session_ = WorkoutSession(name='pytest find-or-create session',
                                      started_at=dt.datetime.utcnow(),
                                      user_id=two_lifters['stranger_id'])
            db.session.add(session_)
            db.session.commit()
            session_id = session_.id

        response = stranger_client.post(
            f'/gym/session/{session_id}/exercises/add',
            data={'new_exercise_name': 'pytest owned lift', 'muscle_group': 'Brust'})
        assert response.status_code in (302, 303)

        with flask_app.app_context():
            session_exercise = SessionExercise.query.filter_by(session_id=session_id).first()
            assert session_exercise is not None, 'the route did not attach an exercise to the session'
            linked = db.session.get(Exercise, session_exercise.exercise_id)
            assert linked.user_id == two_lifters['stranger_id'], \
                'the name lookup matched another user\'s exercise and linked to it'
            assert linked.id != two_lifters['exercise_id'], \
                'session exercise points at the owner\'s row instead of her own'
            created_exercise_id = linked.id
            assert linked.weight_increment is None, 'inherited their increment'
    finally:
        with flask_app.app_context():
            if session_id is not None:
                doomed_session = db.session.get(WorkoutSession, session_id)
                if doomed_session is not None:
                    doomed_session.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed_session)
                    db.session.commit()
            if created_exercise_id is not None:
                doomed_exercise = db.session.get(Exercise, created_exercise_id)
                if doomed_exercise is not None:
                    db.session.delete(doomed_exercise)
                    db.session.commit()


def test_a_stranger_cannot_add_another_users_exercise_to_their_session(
        stranger_client, two_lifters):
    """Both mid-session paths take exercise_id straight from a submitted form.
    Harmless while one catalogue was shared; an IDOR once exercises are owned."""
    from extensions import db
    from models import SessionExercise, WorkoutSession

    session_id = None
    try:
        with flask_app.app_context():
            theirs = WorkoutSession(name='pytest stranger session',
                                    user_id=two_lifters['stranger_id'])
            db.session.add(theirs)
            db.session.commit()
            session_id = theirs.id

        response = stranger_client.post(f'/gym/session/{session_id}/exercises/add',
                                        data={'exercise_id': str(two_lifters['exercise_id'])})
        assert response.status_code == 404, f'returned {response.status_code}'

        with flask_app.app_context():
            assert SessionExercise.query.filter_by(session_id=session_id).count() == 0, \
                'the rejected request added the exercise anyway'
    finally:
        with flask_app.app_context():
            if session_id is not None:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()


def test_a_non_admin_can_rename_an_exercise_they_own(stranger_client, two_lifters):
    """The whole point of ownership: gym_update_exercise checks ownership now,
    not @admin_required -- a non-admin owner must be able to rename what is
    hers without needing the admin flag the old gate demanded."""
    from extensions import db
    from models import Exercise

    exercise_id = None
    try:
        with flask_app.app_context():
            exercise = Exercise(name='pytest stranger owned lift', muscle_group='Ruecken',
                                user_id=two_lifters['stranger_id'])
            db.session.add(exercise)
            db.session.commit()
            exercise_id = exercise.id

        response = stranger_client.post(
            f'/gym/exercises/{exercise_id}/update',
            data={'name': 'pytest stranger renamed lift'})
        assert response.status_code in (302, 303), \
            f'a non-admin owner could not update their own exercise: {response.status_code}'

        with flask_app.app_context():
            renamed = db.session.get(Exercise, exercise_id)
            assert renamed.name == 'pytest stranger renamed lift', \
                'the rename did not take effect for a non-admin owner'
    finally:
        with flask_app.app_context():
            if exercise_id is not None:
                doomed = db.session.get(Exercise, exercise_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_a_non_admin_owner_sees_the_edit_control_on_their_exercise_page(stranger_client, two_lifters):
    """Pins the template fix: exercise_detail.html wrapped the manage section
    and the edit dialog in {% if is_admin %}, so a non-admin owner who could
    already rename via a direct POST (previous test) still had no button on
    the page to do it from. Fails again if that gate is re-added."""
    from extensions import db
    from models import Exercise

    exercise_id = None
    try:
        with flask_app.app_context():
            exercise = Exercise(name='pytest stranger detail lift', muscle_group='Beine',
                                user_id=two_lifters['stranger_id'])
            db.session.add(exercise)
            db.session.commit()
            exercise_id = exercise.id

        body = stranger_client.get(f'/gym/exercises/{exercise_id}').get_data(as_text=True)
        assert 'Name, Muskelgruppe, Standard-Pause bearbeiten' in body, \
            'a non-admin owner does not see the edit control on their own exercise page'
    finally:
        with flask_app.app_context():
            if exercise_id is not None:
                doomed = db.session.get(Exercise, exercise_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
