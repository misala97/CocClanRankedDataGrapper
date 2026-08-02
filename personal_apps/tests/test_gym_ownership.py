"""Ownership of gym data.

The IDOR table test at the bottom of this file is the durable guarantee that
no gym route leaks another user's data: it loops over every route that takes an
object id, so a new unscoped route fails the moment it is added.

Runs against the real local development database. Every row created here is
deleted in a finally.
"""
import pytest

from app import app as flask_app


def test_the_three_roots_carry_an_owner():
    from models import PushSubscription, WorkoutSession, WorkoutTemplate
    for model in (WorkoutSession, WorkoutTemplate, PushSubscription):
        assert hasattr(model, 'user_id'), f'{model.__name__} has no user_id'
        # __table__.c, not the mapped attribute: an InstrumentedAttribute has
        # no .nullable of its own.
        assert model.__table__.c.user_id.nullable is False, \
            f'{model.__name__}.user_id must be NOT NULL'


def test_every_pre_existing_row_was_backfilled_to_the_admin():
    """Rows created by this suite's own fixtures are excluded by name -- they
    are deliberately owned by throwaway users, and this assertion is about what
    the migration did to the data that already existed."""
    import sqlalchemy as sa
    from models import AppUser, PushSubscription, WorkoutSession, WorkoutTemplate
    with flask_app.app_context():
        admin = AppUser.query.filter_by(is_admin=True).order_by(AppUser.id).first()
        assert admin is not None
        for model in (WorkoutSession, WorkoutTemplate):
            orphans = model.query.filter(
                model.user_id != admin.id,
                # WorkoutSession.name is nullable, and NOT LIKE is NULL (not
                # true) for a NULL -- without the is_(None) arm an unnamed row
                # owned by someone else would slip past this check.
                sa.or_(model.name.is_(None), model.name.notlike('pytest%')),
            ).count()
            assert orphans == 0, f'{model.__name__} has rows not owned by the admin'

        # The migration backfills all three roots from one table-agnostic loop,
        # so leaving this one unchecked would let a fault isolated to it pass
        # silently. PushSubscription has no name column -- its scratch rows are
        # identified by the endpoint path this suite mints.
        orphan_subscriptions = PushSubscription.query.filter(
            PushSubscription.user_id != admin.id,
            PushSubscription.endpoint.notlike('%/pytest/%'),
        ).count()
        assert orphan_subscriptions == 0, 'PushSubscription has rows not owned by the admin'


import datetime as dt


@pytest.fixture()
def two_users():
    """Owner A (admin) with a full object graph, and intruder B (non-admin).

    Yields a dict of A's object ids plus B's user id. Everything is deleted
    afterwards, in dependency order.
    """
    from extensions import db
    from models import (AppUser, Exercise, SessionExercise, SessionSet,
                        TemplateExercise, WorkoutSession, WorkoutTemplate)
    from werkzeug.security import generate_password_hash

    created = {}
    with flask_app.app_context():
        owner = AppUser(username='pytest owner A',
                        password_hash=generate_password_hash('a'), is_admin=True)
        intruder = AppUser(username='pytest intruder B',
                           password_hash=generate_password_hash('b'), is_admin=False)
        db.session.add_all([owner, intruder])
        db.session.flush()

        exercise = Exercise(name='pytest ownership lift', muscle_group='Brust')
        db.session.add(exercise)
        db.session.flush()

        template = WorkoutTemplate(name='pytest ownership template', user_id=owner.id)
        template.exercises.append(TemplateExercise(exercise_id=exercise.id, position=1))
        db.session.add(template)
        db.session.flush()

        workout = WorkoutSession(name='pytest ownership session',
                                 started_at=dt.datetime.utcnow(), user_id=owner.id)
        session_exercise = SessionExercise(exercise_id=exercise.id, position=1)
        session_exercise.sets = [SessionSet(position=1, weight=123.5, reps=7, completed=True)]
        workout.exercises.append(session_exercise)
        db.session.add(workout)
        db.session.commit()

        created = {
            'owner_id': owner.id,
            'intruder_id': intruder.id,
            'exercise_id': exercise.id,
            'template_id': template.id,
            'session_id': workout.id,
            'session_exercise_id': workout.exercises[0].id,
            'set_id': workout.exercises[0].sets[0].id,
        }
    yield created

    with flask_app.app_context():
        doomed_session = db.session.get(WorkoutSession, created['session_id'])
        if doomed_session is not None:
            doomed_session.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed_session)
            db.session.commit()
        doomed_template = db.session.get(WorkoutTemplate, created['template_id'])
        if doomed_template is not None:
            db.session.delete(doomed_template)
            db.session.commit()
        doomed_exercise = db.session.get(Exercise, created['exercise_id'])
        if doomed_exercise is not None:
            db.session.delete(doomed_exercise)
            db.session.commit()
        for user_id in (created['owner_id'], created['intruder_id']):
            doomed_user = db.session.get(AppUser, user_id)
            if doomed_user is not None:
                db.session.delete(doomed_user)
        db.session.commit()


@pytest.fixture()
def intruder_client(two_users):
    """A client logged in as B, who owns nothing."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['intruder_id']
        yield test_client


# (method, url template, which id from the two_users fixture fills the {})
SESSION_ROUTES = [
    ('GET',  '/gym/session/{}',                    'session_id'),
    ('POST', '/gym/session/{}/exercises/add',      'session_id'),
    ('POST', '/gym/session/{}/exercises/reorder',  'session_id'),
    ('POST', '/gym/session/{}/rest/skip',          'session_id'),
    ('POST', '/gym/session/{}/finish',             'session_id'),
    ('POST', '/gym/session/{}/deload',             'session_id'),
    ('GET',  '/gym/session/{}/summary',            'session_id'),
    ('POST', '/gym/session/{}/delete',             'session_id'),
    ('POST', '/gym/session/{}/update_template',    'session_id'),
    ('POST', '/gym/session/{}/save_as_template',   'session_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', SESSION_ROUTES)
def test_a_stranger_gets_404_on_someone_elses_session(
        intruder_client, two_users, method, url_template, id_key):
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 404, f'{method} {url} returned {response.status_code}'


def test_the_owners_session_still_works(two_users):
    """The scoping must not break the owner -- a 404 for everyone is not a fix."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['owner_id']
        assert owner_client.get('/gym/session/{}'.format(two_users['session_id'])).status_code == 200


def test_starting_a_workout_stamps_the_owner(two_users):
    """gym_start builds a WorkoutSession directly, and Task 4 made user_id NOT
    NULL -- so an unstamped insert now fails outright. This covers ownership
    and the fact that the route works at all.

    Runs as B, who owns nothing: gym_start redirects instead of creating when
    _get_active_session() finds an unfinished workout, and A's fixture session
    is unfinished. That only holds once that helper is scoped, which is why it
    moves into this task.
    """
    from extensions import db
    from models import WorkoutSession
    created_id = None
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client_b:
        with client_b.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['intruder_id']
        response = client_b.post('/gym/start', data={'name': 'pytest ownership start'})
        assert response.status_code in (302, 303)
    try:
        with flask_app.app_context():
            created = WorkoutSession.query.filter_by(name='pytest ownership start').one()
            created_id = created.id
            assert created.user_id == two_users['intruder_id']
    finally:
        with flask_app.app_context():
            if created_id is not None:
                doomed = db.session.get(WorkoutSession, created_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()


def test_saving_a_session_as_a_template_stamps_the_owner(two_users):
    from extensions import db
    from models import WorkoutTemplate
    created_id = None
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['owner_id']
        response = owner_client.post(
            '/gym/session/{}/save_as_template'.format(two_users['session_id']),
            data={'template_name': 'pytest ownership saved template'})
        assert response.status_code in (302, 303)
    try:
        with flask_app.app_context():
            created = WorkoutTemplate.query.filter_by(name='pytest ownership saved template').one()
            created_id = created.id
            assert created.user_id == two_users['owner_id']
    finally:
        with flask_app.app_context():
            if created_id is not None:
                doomed = db.session.get(WorkoutTemplate, created_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_subscribing_to_push_stamps_the_owner(two_users):
    from extensions import db
    from models import PushSubscription
    endpoint = 'https://fcm.googleapis.com/pytest/ownership-subscribe'
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['owner_id']
        response = owner_client.post('/gym/push/subscribe', json={
            'endpoint': endpoint, 'keys': {'p256dh': 'k', 'auth': 'a'}})
        assert response.status_code == 200
    try:
        with flask_app.app_context():
            stored = PushSubscription.query.filter_by(endpoint=endpoint).one()
            assert stored.user_id == two_users['owner_id']
    finally:
        with flask_app.app_context():
            PushSubscription.query.filter_by(endpoint=endpoint).delete()
            db.session.commit()
