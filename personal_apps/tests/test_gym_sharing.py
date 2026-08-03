"""Shared live sessions: the link, the exercise map, and the one function
that writes into another user's session."""
import datetime as dt

import pytest

from app import app as flask_app


def test_a_shared_session_links_two_sessions_and_starts_pending():
    from extensions import db
    from models import AppUser, SharedSession, WorkoutSession
    from werkzeug.security import generate_password_hash

    made = {}
    try:
        with flask_app.app_context():
            leader = AppUser(username='pytest link leader',
                             password_hash=generate_password_hash('a'), is_admin=False)
            follower = AppUser(username='pytest link follower',
                               password_hash=generate_password_hash('b'), is_admin=False)
            db.session.add_all([leader, follower])
            db.session.flush()
            made['leader_user'], made['follower_user'] = leader.id, follower.id

            leader_session = WorkoutSession(name='pytest link session',
                                            started_at=dt.datetime.utcnow(),
                                            user_id=leader.id)
            db.session.add(leader_session)
            db.session.flush()
            made['leader_session'] = leader_session.id

            shared = SharedSession(leader_session_id=leader_session.id,
                                   leader_user_id=leader.id,
                                   follower_user_id=follower.id)
            db.session.add(shared)
            db.session.commit()
            made['shared'] = shared.id

            fresh = db.session.get(SharedSession, shared.id)
            assert fresh.accepted_at is None, 'a new invite must start pending'
            assert fresh.ended_at is None
            assert fresh.follower_session_id is None, (
                'no follower session exists until the invite is accepted')
            assert fresh.created_at is not None
            assert list(fresh.exercise_map) == []
    finally:
        with flask_app.app_context():
            if made.get('shared'):
                doomed = db.session.get(SharedSession, made['shared'])
                if doomed is not None:
                    db.session.delete(doomed)
                    db.session.commit()
            if made.get('leader_session'):
                doomed = db.session.get(WorkoutSession, made['leader_session'])
                if doomed is not None:
                    doomed.resting_set_id = None
                    db.session.commit()
                    db.session.delete(doomed)
                    db.session.commit()
            for key in ('leader_user', 'follower_user'):
                if made.get(key):
                    doomed = db.session.get(AppUser, made[key])
                    if doomed is not None:
                        db.session.delete(doomed)
            db.session.commit()


def test_a_session_exercise_can_mirror_another_users_row():
    """mirrors_id is how reconciliation knows which follower row corresponds to
    which leader row -- exercise_id cannot serve, because the two catalogues
    have different ids for the same lift."""
    from extensions import db
    from models import SessionExercise, WorkoutSession
    from conftest import _admin_id

    with flask_app.app_context():
        column = SessionExercise.__table__.columns['mirrors_id']
        assert column.nullable, 'every non-shared session leaves this NULL'
        version = WorkoutSession.__table__.columns['structure_version']
        assert not version.nullable
        assert version.default.arg == 0
