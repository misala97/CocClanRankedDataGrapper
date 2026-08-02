"""Ownership rules for gym data.

The single place that knows how a gym object is tied to a user. Routes call
these instead of db.get_or_404 -- doing the check inline at 25 call sites is
how a leak arrives on the twenty-sixth.

Ownership lives on four roots (WorkoutSession, WorkoutTemplate,
PushSubscription, Exercise); everything else inherits through its parent foreign key.
Exercises became per-user on 2026-08-02: a third lifter joined who trains at
the same gym but uses none of the same exercises, so one global list put
everyone's lifts in everyone's picker.

Every failure is 404, never 403: a 403 confirms the object exists.
"""
from flask import abort, session as flask_session

from extensions import db
from models import Exercise, SessionExercise, SessionSet, WorkoutSession, WorkoutTemplate


def current_user_id():
    """The logged-in user's id, or None. The gate in app.py means routes
    reached through the app always have one."""
    return flask_session.get('user_id')


def my_sessions():
    """WorkoutSession query filtered to the caller. Use for every list,
    history and aggregate read."""
    return WorkoutSession.query.filter(WorkoutSession.user_id == current_user_id())


def my_templates():
    return WorkoutTemplate.query.filter(WorkoutTemplate.user_id == current_user_id())


def owned_session(session_id):
    row = db.session.get(WorkoutSession, session_id)
    if row is None or row.user_id != current_user_id():
        abort(404)
    return row


def owned_template(template_id):
    row = db.session.get(WorkoutTemplate, template_id)
    if row is None or row.user_id != current_user_id():
        abort(404)
    return row


def owned_session_exercise(session_exercise_id):
    row = db.session.get(SessionExercise, session_exercise_id)
    if row is None or row.session.user_id != current_user_id():
        abort(404)
    return row


def owned_set(set_id):
    row = db.session.get(SessionSet, set_id)
    if row is None or row.session_exercise.session.user_id != current_user_id():
        abort(404)
    return row


def my_exercises():
    """Exercise query filtered to the caller.

    The catalogue was shared until 2026-08-02. It is owned now: a third lifter
    joined who trains at the same gym but uses none of the same exercises, so
    one global list put everyone's lifts in everyone's picker.
    """
    return Exercise.query.filter(Exercise.user_id == current_user_id())


def owned_exercise(exercise_id):
    row = db.session.get(Exercise, exercise_id)
    if row is None or row.user_id != current_user_id():
        abort(404)
    return row
