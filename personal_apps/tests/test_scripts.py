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


def test_delete_user_removes_the_account_and_its_templates(throwaway_user):
    from extensions import db
    from models import AppUser, WorkoutTemplate
    from scripts.delete_user import delete_user

    with flask_app.app_context():
        db.session.add(WorkoutTemplate(name='pytest deletable template',
                                       user_id=throwaway_user))
        db.session.commit()

    with flask_app.app_context():
        delete_user('pytest deletable', commit=True)

    with flask_app.app_context():
        assert db.session.get(AppUser, throwaway_user) is None
        assert WorkoutTemplate.query.filter_by(user_id=throwaway_user).count() == 0


def test_delete_user_refuses_a_user_with_a_logged_session(throwaway_user):
    """The guard that separates removing an empty placeholder from destroying
    someone's training history because a username was mistyped."""
    import datetime as dt
    from extensions import db
    from models import AppUser, WorkoutSession
    from scripts.delete_user import delete_user

    session_id = None
    try:
        with flask_app.app_context():
            logged = WorkoutSession(name='pytest deletable session',
                                    started_at=dt.datetime.utcnow(),
                                    user_id=throwaway_user)
            db.session.add(logged)
            db.session.commit()
            session_id = logged.id

        with flask_app.app_context():
            with pytest.raises(SystemExit):
                delete_user('pytest deletable', commit=True)
            assert db.session.get(AppUser, throwaway_user) is not None
    finally:
        with flask_app.app_context():
            if session_id is not None:
                doomed = db.session.get(WorkoutSession, session_id)
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
