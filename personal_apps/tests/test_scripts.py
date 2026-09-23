"""The two rollout scripts. They run once each against production, so their
guards matter more than their happy paths."""
import datetime as dt
import re

import pytest

from app import app as flask_app
from conftest import _admin_id


@pytest.fixture()
def throwaway_user():
    from extensions import db
    from models import AppUser
    from werkzeug.security import generate_password_hash
    with flask_app.app_context():
        user = AppUser(username='pytest deletable',
                       password_hash=generate_password_hash('irrelevant'),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield user_id
    with flask_app.app_context():
        doomed = db.session.get(AppUser, user_id)
        if doomed is not None:
            db.session.delete(doomed)
            db.session.commit()


def test_delete_user_dry_run_writes_nothing(throwaway_user):
    from extensions import db
    from models import AppUser
    from scripts.delete_user import delete_user

    with flask_app.app_context():
        delete_user('pytest deletable', commit=False)
        assert db.session.get(AppUser, throwaway_user) is not None


def test_delete_user_removes_the_account_its_templates_and_its_settings(throwaway_user):
    """Templates, push subscriptions and exercise settings each carry a
    foreign key to the user with no cascade, so the account cannot go while
    one remains -- an unhandled IntegrityError, back when the user owned
    exercises too. The exercise itself is everyone's since the one list
    (2026-09-23) and stays."""
    from extensions import db
    from models import AppUser, Exercise, ExerciseSettings, TemplateExercise, WorkoutTemplate
    from scripts.delete_user import delete_user

    template_id = None
    exercise_id = None
    try:
        with flask_app.app_context():
            exercise = Exercise(name='pytest deletable exercise', muscle_group='Brust')
            db.session.add(exercise)
            db.session.flush()
            template = WorkoutTemplate(name='pytest deletable template',
                                       user_id=throwaway_user)
            template.exercises.append(
                TemplateExercise(exercise_id=exercise.id, position=1))
            db.session.add(template)
            db.session.add(ExerciseSettings(user_id=throwaway_user, exercise_id=exercise.id,
                                            weight_increment=9.0))
            db.session.commit()
            template_id = template.id
            exercise_id = exercise.id

        with flask_app.app_context():
            delete_user('pytest deletable', commit=True)

        with flask_app.app_context():
            assert db.session.get(AppUser, throwaway_user) is None
            assert WorkoutTemplate.query.filter_by(user_id=throwaway_user).count() == 0
            assert ExerciseSettings.query.filter_by(user_id=throwaway_user).count() == 0
            assert db.session.get(Exercise, exercise_id) is not None, \
                'deleted an exercise every lifter uses'
    finally:
        with flask_app.app_context():
            if template_id is not None:
                doomed = db.session.get(WorkoutTemplate, template_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if exercise_id is not None:
                doomed = db.session.get(Exercise, exercise_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_delete_user_refuses_a_user_with_a_logged_session(throwaway_user):
    """The guard that separates removing an empty placeholder from destroying
    someone's training history because a username was mistyped."""
    import datetime as dt
    from extensions import db
    from models import AppUser, WorkoutSession, WorkoutTemplate
    from scripts.delete_user import delete_user

    session_id = None
    template_id = None
    try:
        with flask_app.app_context():
            logged = WorkoutSession(name='pytest deletable session',
                                    started_at=dt.datetime.utcnow(),
                                    user_id=throwaway_user)
            db.session.add(logged)
            template = WorkoutTemplate(name='pytest deletable template',
                                       user_id=throwaway_user)
            db.session.add(template)
            db.session.commit()
            session_id = logged.id
            template_id = template.id

        with flask_app.app_context():
            with pytest.raises(SystemExit) as excinfo:
                delete_user('pytest deletable', commit=True)
            assert 'refusing' in str(excinfo.value)
            assert db.session.get(AppUser, throwaway_user) is not None
            assert db.session.get(WorkoutTemplate, template_id) is not None
    finally:
        with flask_app.app_context():
            if session_id is not None:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if template_id is not None:
                doomed = db.session.get(WorkoutTemplate, template_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()


def test_copy_templates_names_the_same_exercises(throwaway_user):
    """Since the one list a copied routine points at the very exercises the
    original does -- no fork, no new rows, even when two routines share one
    -- and the source's personal settings stay behind: they describe the
    source's gym, not the destination's."""
    from extensions import db
    from models import AppUser, Exercise, ExerciseSettings, TemplateExercise, WorkoutTemplate
    from scripts.copy_templates import copy_templates

    made = []
    try:
        with flask_app.app_context():
            source_id = _admin_id()
            shared = Exercise(name='pytest fork lift', muscle_group='Brust', list_increment=2.5)
            db.session.add(shared)
            db.session.flush()
            made.append(('exercise', shared.id))
            db.session.add(ExerciseSettings(user_id=source_id, exercise_id=shared.id,
                                            weight_increment=9.0))
            for name in ('pytest fork A', 'pytest fork B'):
                template = WorkoutTemplate(name=name, user_id=source_id)
                template.exercises.append(
                    TemplateExercise(exercise_id=shared.id, position=1, rest_seconds=150))
                db.session.add(template)
                db.session.flush()
                made.append(('template', template.id))
            db.session.commit()
            before = Exercise.query.count()

            destination = db.session.get(AppUser, throwaway_user).username
            copy_templates(db.session.get(AppUser, source_id).username, destination,
                           commit=True)

        with flask_app.app_context():
            assert Exercise.query.count() == before, 'the copy created exercises'
            copies = WorkoutTemplate.query.filter(
                WorkoutTemplate.user_id == throwaway_user,
                WorkoutTemplate.name.like('pytest fork %')).all()
            assert [(te.exercise_id, te.rest_seconds) for t in copies for te in t.exercises] == \
                [(made[0][1], 150)] * 2
            assert ExerciseSettings.query.filter_by(user_id=throwaway_user).count() == 0, \
                'the source\'s settings were copied'
    finally:
        with flask_app.app_context():
            for template in WorkoutTemplate.query.filter_by(user_id=throwaway_user):
                db.session.delete(template)
            db.session.commit()
            for kind, row_id in reversed(made):
                model = {'exercise': Exercise, 'template': WorkoutTemplate}[kind]
                doomed = db.session.get(model, row_id)
                if doomed is not None:
                    db.session.delete(doomed)
            db.session.commit()


class TestPendingPushes:
    """run_gym_notifier's rest-timer queue."""

    def test_a_finished_sessions_pending_push_is_retired_not_fired(self, monkeypatch):
        # Every route that ends a session cancels its pending rows, so this
        # only happens when a session is finished some other way -- a manual
        # database edit, a restore. Before 2026-08-11 the daemon fired those
        # regardless: the phone buzzed "Rest complete" for a workout that had
        # ended hours earlier.
        from extensions import db
        from models import PendingPush, WorkoutSession
        import run_gym_notifier

        sent = []
        monkeypatch.setattr(run_gym_notifier, 'send_push_to_user',
                            lambda user_id, payload: sent.append(user_id))

        session_id = push_id = None
        try:
            with flask_app.app_context():
                started = dt.datetime.utcnow() - dt.timedelta(hours=3)
                session_ = WorkoutSession(name='ZZ orphan push', user_id=_admin_id(),
                                          started_at=started,
                                          finished_at=started + dt.timedelta(hours=1))
                db.session.add(session_)
                db.session.flush()
                pending = PendingPush(
                    session_id=session_.id,
                    fire_at=dt.datetime.utcnow() - dt.timedelta(minutes=5))
                db.session.add(pending)
                db.session.commit()
                session_id, push_id = session_.id, pending.id

            run_gym_notifier.check_pending_pushes()

            with flask_app.app_context():
                assert sent == [], 'a finished session must not buzz the phone'
                # Retired, so it stops being scanned every 20 seconds forever.
                assert db.session.get(PendingPush, push_id).sent is True
        finally:
            with flask_app.app_context():
                if push_id is not None:
                    doomed = db.session.get(PendingPush, push_id)
                    if doomed is not None:
                        db.session.delete(doomed)
                if session_id is not None:
                    doomed = db.session.get(WorkoutSession, session_id)
                    if doomed is not None:
                        db.session.delete(doomed)
                db.session.commit()


class TestWeeklyDigest:
    """run_gym_notifier's Sunday summary."""

    @staticmethod
    def _make_week(user_id, now):
        from extensions import db
        from models import Exercise, SessionExercise, SessionSet, WorkoutSession
        exercise = Exercise(name='ZZ digest lift')
        db.session.add(exercise)
        db.session.flush()
        made = []
        for n in range(2):
            started = now - dt.timedelta(days=n)
            session_ = WorkoutSession(name=f'ZZ digest {n}', user_id=user_id,
                                      started_at=started,
                                      finished_at=started + dt.timedelta(hours=1))
            se = SessionExercise(exercise_id=exercise.id, position=1)
            se.sets = [SessionSet(position=1, weight=50.0, reps=10, completed=True)]
            session_.exercises.append(se)
            db.session.add(session_)
            made.append(session_)
        db.session.commit()
        return exercise.id, [s.id for s in made]

    def test_sums_the_week_in_german(self):
        from app import app as flask_app
        from extensions import db
        from models import Exercise, WorkoutSession
        from run_gym_notifier import _weekly_digest_for

        # Mid-week anchor so both sessions (today and yesterday) stay inside
        # the Monday-start week.
        now = dt.datetime.utcnow()
        if now.weekday() < 2:
            now += dt.timedelta(days=2 - now.weekday())
        exercise_id, session_ids = None, []
        try:
            with flask_app.app_context():
                exercise_id, session_ids = self._make_week(_admin_id(), now)
            payload = _weekly_digest_for(_admin_id(), now)
            assert payload is not None
            assert payload['title'] == 'Deine Trainingswoche'
            # At least the two fixture sessions -- the dev DB may add its own
            # this week, the same reason the kg sum below is not pinned.
            count = re.search(r'(\d+) Workouts', payload['body'])
            assert count is not None, payload['body']
            assert int(count.group(1)) >= 2
            assert ' kg' in payload['body']
        finally:
            with flask_app.app_context():
                for session_id in session_ids:
                    doomed = db.session.get(WorkoutSession, session_id)
                    if doomed is not None:
                        doomed.resting_set_id = None
                        db.session.commit()
                        db.session.delete(doomed)
                        db.session.commit()
                if exercise_id:
                    doomed = db.session.get(Exercise, exercise_id)
                    if doomed is not None:
                        db.session.delete(doomed)
                        db.session.commit()

    def test_an_empty_week_sends_nothing(self):
        """Silence over nagging: no workouts, no push."""
        from app import app as flask_app
        from extensions import db
        from models import AppUser
        from werkzeug.security import generate_password_hash
        from run_gym_notifier import _weekly_digest_for

        user_id = None
        try:
            with flask_app.app_context():
                ghost = AppUser(username='ZZ digest ghost',
                                password_hash=generate_password_hash('x'), is_admin=False)
                db.session.add(ghost)
                db.session.commit()
                user_id = ghost.id
            assert _weekly_digest_for(user_id, dt.datetime.utcnow()) is None
        finally:
            with flask_app.app_context():
                doomed = db.session.get(AppUser, user_id) if user_id else None
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
