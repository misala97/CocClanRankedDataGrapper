"""A throwaway lifter for gym tests that need history built to order.

Fresh users, exercises, routines and workouts, all deleted afterwards
whatever the test does. They run against the local development database, so
the "one running workout" lookup can only ever find these rows.
"""
import datetime as dt

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from extensions import db
from models import (
    AppUser, Exercise, ExerciseSettings, LifterSettings, SessionExercise, SessionSet,
    SharedSession, TemplateExercise, WorkoutSession, WorkoutTemplate,
)


class Lifter:
    """A fresh user with exercises, routines and workouts built to order."""

    def __init__(self):
        with flask_app.app_context():
            user = AppUser(username='pytest gym lifter',
                           password_hash=generate_password_hash('x'), is_admin=False)
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id
        self.exercise_ids = []
        self.partner_ids = []
        self.now = dt.datetime.utcnow().replace(microsecond=0)

    def partner(self):
        """A second throwaway user, deleted with the first."""
        with flask_app.app_context():
            user = AppUser(username=f'pytest gym partner {len(self.partner_ids)}',
                           password_hash=generate_password_hash('x'), is_admin=False)
            db.session.add(user)
            db.session.commit()
            self.partner_ids.append(user.id)
            return user.id

    def client(self, user_id=None):
        flask_app.config['TESTING'] = True
        test_client = flask_app.test_client()
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = user_id or self.user_id
        return test_client

    def exercise(self, name, muscle_group='Brust'):
        exercise = Exercise(name=f'pytest gym {name}', muscle_group=muscle_group)
        db.session.add(exercise)
        db.session.flush()
        self.exercise_ids.append(exercise.id)
        return exercise

    def routine(self, name, exercises, plan=None, user_id=None):
        """A routine of `exercises` in this order. `plan` maps an exercise id
        to its row's (target_sets, rep_min, rep_max); left out: not filled."""
        template = WorkoutTemplate(name=f'pytest gym {name}', user_id=user_id or self.user_id)
        for position, exercise in enumerate(exercises, start=1):
            target_sets, rep_min, rep_max = (plan or {}).get(exercise.id, (None, None, None))
            template.exercises.append(TemplateExercise(
                exercise_id=exercise.id, position=position,
                target_sets=target_sets, rep_min=rep_min, rep_max=rep_max))
        db.session.add(template)
        db.session.flush()
        return template

    def workout(self, started_ago, user_id=None, template=None, finished=False,
                is_deload=False):
        """A workout started `started_ago` before now; finished an hour after
        its start when `finished`."""
        started_at = self.now - started_ago
        workout = WorkoutSession(
            name='pytest gym', user_id=user_id or self.user_id, started_at=started_at,
            template_id=template.id if template is not None else None,
            finished_at=started_at + dt.timedelta(hours=1) if finished else None,
            is_deload=is_deload)
        db.session.add(workout)
        db.session.flush()
        return workout

    def row(self, workout, exercise, position, done=(), ticked_empty=0, open_=0,
            skipped=False, replaces=None, done_ago=None):
        """`done`: (weight, reps) pairs, ticked `done_ago` (a list of
        timedeltas, one per set) before now -- unstamped when None."""
        row = SessionExercise(session_id=workout.id, exercise_id=exercise.id, position=position,
                              skipped=skipped,
                              replaces_id=replaces.id if replaces is not None else None)
        db.session.add(row)
        db.session.flush()
        number = 0
        for index, (weight, reps) in enumerate(done):
            number += 1
            stamp = self.now - done_ago[index] if done_ago is not None else None
            db.session.add(SessionSet(session_exercise_id=row.id, position=number, weight=weight,
                                      reps=reps, completed=True, completed_at=stamp))
        for _ in range(ticked_empty):
            number += 1
            db.session.add(SessionSet(session_exercise_id=row.id, position=number, weight=40.0,
                                      reps=0, completed=True, completed_at=self.now))
        for _ in range(open_):
            number += 1
            db.session.add(SessionSet(session_exercise_id=row.id, position=number, weight=40.0,
                                      reps=8, completed=False))
        db.session.flush()
        return row

    def delete(self):
        _destroy([self.user_id, *self.partner_ids], self.exercise_ids)


def _sweep_stale():
    """What a crashed run left behind: its fixed names would refuse this
    run's users on the unique index, and every test here would fail."""
    with flask_app.app_context():
        user_ids = [user.id for user in
                    AppUser.query.filter(AppUser.username.like('pytest gym %'))]
        exercise_ids = [exercise.id for exercise in
                        Exercise.query.filter(Exercise.name.like('pytest gym %'))]
    if user_ids or exercise_ids:
        _destroy(user_ids, exercise_ids)


def _destroy(user_ids, exercise_ids):
    """The users' workouts, links, settings and routines, the exercises, then
    the users."""
    with flask_app.app_context():
        SharedSession.query.filter(db.or_(
            SharedSession.leader_user_id.in_(user_ids),
            SharedSession.follower_user_id.in_(user_ids))).delete(synchronize_session=False)
        db.session.commit()
        for workout in WorkoutSession.query.filter(WorkoutSession.user_id.in_(user_ids)).all():
            workout.resting_set_id = None
            db.session.commit()
            db.session.delete(workout)
            db.session.commit()
        for model in (ExerciseSettings, LifterSettings):
            model.query.filter(model.user_id.in_(user_ids)).delete(synchronize_session=False)
        for template in WorkoutTemplate.query.filter(
                WorkoutTemplate.user_id.in_(user_ids)).all():
            db.session.delete(template)
        db.session.commit()
        for exercise_id in exercise_ids:
            exercise = db.session.get(Exercise, exercise_id)
            if exercise is not None:
                db.session.delete(exercise)
        db.session.commit()
        for user_id in user_ids:
            user = db.session.get(AppUser, user_id)
            if user is not None:
                db.session.delete(user)
                db.session.commit()


@pytest.fixture()
def lifter():
    _sweep_stale()
    made = Lifter()
    try:
        yield made
    finally:
        made.delete()
