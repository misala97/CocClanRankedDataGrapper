"""Ownership rules for gym data.

The single place that knows how a gym object is tied to a user. Routes call
these instead of db.get_or_404 -- doing the check inline at 25 call sites is
how a leak arrives on the twenty-sixth.

Ownership lives on three roots (WorkoutSession, WorkoutTemplate,
PushSubscription); everything else inherits through its parent foreign key.
Exercises were a fourth root from 2026-08-02 until 2026-09-23. Since then
they are one list that belongs to nobody (features/gym/exercises.py), and
what is private about an exercise -- a lifter's history on it, their
settings for it -- is scoped by the session, routine or settings row.

Every failure is 404, never 403: a 403 confirms the object exists -- or
409 for the live workout screen (_missing).
"""
from flask import abort, request, session as flask_session

from extensions import db
from models import SessionExercise, SessionSet, WorkoutSession, WorkoutTemplate


# The live workout screen names itself on every write with this header;
# the debrief posts to the same set routes without it (routes/helpers.py).
# Here because a missing row is answered by the surface that asked (_missing).
LIVE_SURFACE_HEADER = 'X-Gym-Surface'


def _missing():
    """404 -- or 409 when the live workout screen asks.

    A row the live screen writes to that is not there for it means the screen
    is stale: the workout was finished (its open sets deleted, D5) or
    discarded. The island answers 409 by reloading into what is true now; a
    404 read as a lost connection and was retried forever (B4 review). 409 for
    somebody else's row too, so the answer still says nothing about whether it
    exists."""
    abort(409 if request.headers.get(LIVE_SURFACE_HEADER) == 'live' else 404)


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
        _missing()
    return row


def owned_template(template_id):
    row = db.session.get(WorkoutTemplate, template_id)
    if row is None or row.user_id != current_user_id():
        abort(404)
    return row


def owned_session_exercise(session_exercise_id):
    row = db.session.get(SessionExercise, session_exercise_id)
    if row is None or row.session.user_id != current_user_id():
        _missing()
    return row


def owned_set(set_id):
    row = db.session.get(SessionSet, set_id)
    if row is None or row.session_exercise.session.user_id != current_user_id():
        _missing()
    return row
