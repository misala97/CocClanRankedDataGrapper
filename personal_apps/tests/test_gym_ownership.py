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

        # A second, FINISHED session for the owner. The pages that list or
        # aggregate history (verlauf/statistik/uebungen) all filter to
        # finished_at IS NOT NULL, so the unfinished `workout` above -- kept
        # active on purpose for the active-session tests below -- is invisible
        # to every one of them. Without a finished sibling, their leak
        # assertions can never fail no matter how the scoping is written.
        finished_started = dt.datetime.utcnow() - dt.timedelta(days=3)
        finished_workout = WorkoutSession(
            name='pytest ownership finished', user_id=owner.id,
            started_at=finished_started,
            finished_at=finished_started + dt.timedelta(minutes=45))
        finished_session_exercise = SessionExercise(exercise_id=exercise.id, position=1)
        finished_session_exercise.sets = [
            SessionSet(position=1, weight=123.5, reps=7, completed=True)]
        finished_workout.exercises.append(finished_session_exercise)
        db.session.add(finished_workout)
        db.session.commit()

        created = {
            'owner_id': owner.id,
            'intruder_id': intruder.id,
            'exercise_id': exercise.id,
            'template_id': template.id,
            'session_id': workout.id,
            'session_exercise_id': workout.exercises[0].id,
            'set_id': workout.exercises[0].sets[0].id,
            'finished_session_id': finished_workout.id,
        }
    yield created

    with flask_app.app_context():
        doomed_finished_session = db.session.get(WorkoutSession, created['finished_session_id'])
        if doomed_finished_session is not None:
            doomed_finished_session.resting_set_id = None
            db.session.commit()
            db.session.delete(doomed_finished_session)
            db.session.commit()
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


DESCENDANT_ROUTES = [
    ('POST', '/gym/session-exercise/{}/replace',   'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/rest',      'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/increment', 'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/sets/add',  'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/delete',    'session_exercise_id'),
    ('POST', '/gym/session-exercise/{}/skip',      'session_exercise_id'),
    ('POST', '/gym/set/{}/delete',                 'set_id'),
    ('POST', '/gym/set/{}/toggle_complete',        'set_id'),
    ('POST', '/gym/set/{}/update',                 'set_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', DESCENDANT_ROUTES)
def test_a_stranger_gets_404_on_someone_elses_session_exercise_or_set(
        intruder_client, two_users, method, url_template, id_key):
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 404, f'{method} {url} returned {response.status_code}'


def test_a_rejected_write_changed_nothing(intruder_client, two_users):
    """A 404 is only half the guarantee -- the write must not have landed."""
    from extensions import db
    from models import SessionSet
    intruder_client.post('/gym/set/{}/update'.format(two_users['set_id']),
                         data={'weight': '999', 'reps': '1'})
    with flask_app.app_context():
        stored = db.session.get(SessionSet, two_users['set_id'])
        assert (stored.weight, stored.reps) == (123.5, 7)


TEMPLATE_ROUTES = [
    ('POST', '/gym/templates/{}/rename', 'template_id'),
    ('POST', '/gym/templates/{}/delete', 'template_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', TEMPLATE_ROUTES)
def test_a_stranger_gets_404_on_someone_elses_template(
        intruder_client, two_users, method, url_template, id_key):
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 404, f'{method} {url} returned {response.status_code}'


CATALOGUE_ADMIN_ROUTES = [
    ('POST', '/gym/exercises/{}/update', 'exercise_id'),
    ('POST', '/gym/exercises/{}/delete', 'exercise_id'),
]


@pytest.mark.parametrize('method,url_template,id_key', CATALOGUE_ADMIN_ROUTES)
def test_a_non_admin_cannot_edit_the_shared_catalogue(
        intruder_client, two_users, method, url_template, id_key):
    """The catalogue is shared, so there is no owner to check -- but curating
    it is the admin's job. 403 here, not 404: the exercise is legitimately
    visible to this user, only editing it is refused."""
    url = url_template.format(two_users[id_key])
    response = intruder_client.open(url, method=method)
    assert response.status_code == 403, f'{method} {url} returned {response.status_code}'


def test_the_shared_exercise_survived_the_rejected_writes(two_users):
    from extensions import db
    from models import Exercise
    with flask_app.app_context():
        assert db.session.get(Exercise, two_users['exercise_id']) is not None


def test_starting_from_another_users_template_seeds_nothing_and_stores_no_link(two_users):
    """The indirect path into a template: gym_start took template_id straight
    from the form, so a stranger could seed a session from a private template
    and the row kept the link, which update_template would then follow back."""
    from extensions import db
    from models import WorkoutSession
    created_id = None
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client_b:
        with client_b.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['intruder_id']
        response = client_b.post('/gym/start', data={
            'name': 'pytest stolen template start',
            'template_id': str(two_users['template_id']),
        })
        assert response.status_code in (302, 303)
    try:
        with flask_app.app_context():
            created = WorkoutSession.query.filter_by(name='pytest stolen template start').one()
            created_id = created.id
            assert created.template_id is None, 'stored a link to a template it does not own'
            assert created.exercises == [], 'seeded from another user\'s template'
    finally:
        with flask_app.app_context():
            if created_id is not None:
                doomed = db.session.get(WorkoutSession, created_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()


# The pages render weights German-style (123,5); progress.json emits a raw JSON
# number (123.5). Every leak assertion has to cover both, or an HTML check
# passes against markup that could never have contained the dotted form and
# proves nothing.
FOREIGN_WEIGHTS = ('123.5', '123,5')


LEAKY_PAGES = [
    '/gym',
    '/gym/verlauf',
    '/gym/statistik',
    # Weak coverage: with no ids param the export payload is empty before any
    # owner filter runs, so this case passes vacuously. The case with teeth is
    # /gym/export?ids=<foreign_session_id>, which is not exercised here.
    '/gym/export',
    '/gym/uebungen',
]


@pytest.mark.parametrize('path', LEAKY_PAGES)
def test_the_list_pages_show_none_of_another_users_numbers(intruder_client, two_users, path):
    """B has no training data at all, so A's distinctive 123.5 kg must not
    appear anywhere on a page B can open."""
    body = intruder_client.get(path).get_data(as_text=True)
    for rendering in FOREIGN_WEIGHTS:
        assert rendering not in body, f'{path} leaked another user\'s weight as {rendering}'
    for marker in ('pytest ownership session', 'pytest ownership finished',
                   'pytest ownership template'):
        assert marker not in body, f'{path} leaked {marker}'


def test_the_shared_exercise_page_shows_no_foreign_history(intruder_client, two_users):
    """The subtle one: the exercise itself is shared and B may open it, but
    the history rendered around it is A's and must not appear."""
    url = '/gym/exercises/{}'.format(two_users['exercise_id'])
    response = intruder_client.get(url)
    assert response.status_code == 200, 'the shared catalogue must stay readable'
    body = response.get_data(as_text=True)
    for rendering in FOREIGN_WEIGHTS:
        assert rendering not in body, f'exercise detail leaked another user\'s weight as {rendering}'


def test_the_progress_json_carries_no_foreign_history(intruder_client, two_users):
    url = '/gym/exercises/{}/progress.json'.format(two_users['exercise_id'])
    response = intruder_client.get(url)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for rendering in FOREIGN_WEIGHTS:
        assert rendering not in body, f'progress.json leaked another user\'s weight as {rendering}'


def test_a_stranger_does_not_inherit_the_active_session(intruder_client, two_users):
    """A's session is unfinished. _get_active_session must not hand it to B --
    B would land in someone else's workout on the dashboard."""
    body = intruder_client.get('/gym').get_data(as_text=True)
    assert 'pytest ownership session' not in body


def test_the_owner_still_sees_their_own_numbers(two_users):
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as owner_client:
        with owner_client.session_transaction() as flask_session:
            flask_session['user_id'] = two_users['owner_id']
        body = owner_client.get('/gym/exercises/{}'.format(two_users['exercise_id'])).get_data(as_text=True)
    assert any(rendering in body for rendering in FOREIGN_WEIGHTS), \
        'scoping hid the owner from their own history'


def test_update_template_cannot_overwrite_a_template_it_does_not_own(two_users):
    """The write half of the same chain. Reaches update_template with a session
    whose template_id points at A's template -- the state a pre-fix gym_start
    would have produced, forced directly here so the guard is tested even
    though that path can no longer create it."""
    from extensions import db
    from models import TemplateExercise, WorkoutSession, WorkoutTemplate
    created_id = None
    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        victim = db.session.get(WorkoutTemplate, two_users['template_id'])
        before = [(te.exercise_id, te.position) for te in victim.exercises]
        assert before, 'fixture template should have exercises to lose'
        theirs = WorkoutSession(name='pytest forged link', user_id=two_users['intruder_id'],
                                template_id=two_users['template_id'])
        db.session.add(theirs)
        db.session.commit()
        created_id = theirs.id
    try:
        with flask_app.test_client() as client_b:
            with client_b.session_transaction() as flask_session:
                flask_session['user_id'] = two_users['intruder_id']
            client_b.post(f'/gym/session/{created_id}/update_template')
        with flask_app.app_context():
            victim = db.session.get(WorkoutTemplate, two_users['template_id'])
            after = [(te.exercise_id, te.position) for te in victim.exercises]
            assert after == before, 'a stranger overwrote another user\'s template'
    finally:
        with flask_app.app_context():
            if created_id is not None:
                doomed = db.session.get(WorkoutSession, created_id)
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
