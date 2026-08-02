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
