"""The two rollout scripts. They run once each against production, so their
guards matter more than their happy paths."""
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


def test_delete_user_removes_the_account_its_templates_and_its_exercises(throwaway_user):
    """Exercises became the fourth root a user owns, and gym_exercises.user_id
    is NOT NULL with a foreign key and no cascade -- deleting the user while
    they still own one used to fail with an unhandled IntegrityError. The
    exercise here is also used by the template, which pins the fix's order:
    templates (and their TemplateExercise rows, ORM-cascaded with them) must
    go before the exercise they reference, or the exercise delete hits the
    same class of foreign-key violation, this time against
    gym_template_exercises."""
    from extensions import db
    from models import AppUser, Exercise, TemplateExercise, WorkoutTemplate
    from scripts.delete_user import delete_user

    template_id = None
    exercise_id = None
    try:
        with flask_app.app_context():
            exercise = Exercise(name='pytest deletable exercise', muscle_group='Brust',
                                user_id=throwaway_user)
            db.session.add(exercise)
            db.session.flush()
            template = WorkoutTemplate(name='pytest deletable template',
                                       user_id=throwaway_user)
            template.exercises.append(
                TemplateExercise(exercise_id=exercise.id, position=1))
            db.session.add(template)
            db.session.commit()
            template_id = template.id
            exercise_id = exercise.id

        with flask_app.app_context():
            delete_user('pytest deletable', commit=True)

        with flask_app.app_context():
            assert db.session.get(AppUser, throwaway_user) is None
            assert WorkoutTemplate.query.filter_by(user_id=throwaway_user).count() == 0
            assert db.session.get(Exercise, exercise_id) is None
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


def test_copy_templates_forks_the_exercises_into_the_destination(throwaway_user):
    """After the catalogue became per-user, copied template rows cannot point
    at the source's exercises. Each one is recreated in the destination's own
    catalogue -- once per distinct exercise, even when two templates share it,
    and carrying the values that make a suggestion correct."""
    from extensions import db
    from models import AppUser, Exercise, TemplateExercise, WorkoutTemplate
    from scripts.copy_templates import copy_templates

    made = []
    try:
        with flask_app.app_context():
            source_id = _admin_id()
            shared = Exercise(name='pytest fork lift', muscle_group='Brust',
                              weight_increment=9.0, is_unilateral=True,
                              user_id=source_id)
            db.session.add(shared)
            db.session.flush()
            made.append(('exercise', shared.id))
            # Two templates referencing the SAME exercise -- a plain create
            # would give the destination two copies of it.
            for name in ('pytest fork A', 'pytest fork B'):
                template = WorkoutTemplate(name=name, user_id=source_id)
                template.exercises.append(
                    TemplateExercise(exercise_id=shared.id, position=1, rest_seconds=150))
                db.session.add(template)
                db.session.flush()
                made.append(('template', template.id))
            db.session.commit()

            destination = db.session.get(AppUser, throwaway_user).username
            copy_templates(db.session.get(AppUser, source_id).username, destination,
                           commit=True)

        with flask_app.app_context():
            copies = Exercise.query.filter_by(user_id=throwaway_user,
                                              name='pytest fork lift').all()
            assert len(copies) == 1, f'expected one forked exercise, got {len(copies)}'
            assert copies[0].weight_increment == 9.0
            assert copies[0].is_unilateral is True
            assert copies[0].id != made[0][1], 'pointed at the source exercise'

            for template in WorkoutTemplate.query.filter_by(user_id=throwaway_user):
                for te in template.exercises:
                    assert te.exercise.user_id == throwaway_user, \
                        'a copied template row points at another user exercise'
    finally:
        with flask_app.app_context():
            for template in WorkoutTemplate.query.filter_by(user_id=throwaway_user):
                db.session.delete(template)
            for exercise in Exercise.query.filter_by(user_id=throwaway_user):
                db.session.delete(exercise)
            db.session.commit()
            for kind, row_id in reversed(made):
                model = {'exercise': Exercise, 'template': WorkoutTemplate}[kind]
                doomed = db.session.get(model, row_id)
                if doomed is not None:
                    db.session.delete(doomed)
            db.session.commit()
