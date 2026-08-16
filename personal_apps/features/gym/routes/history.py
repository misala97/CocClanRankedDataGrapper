"""The performed-history pipeline.

Turns stored sessions into the `performed` rows that seeding, stats and the
exercise pages all read. Kept apart from the routes that call it because
sharing.py and seeding.py need it too, and neither may import a module that
registers routes.

Moved verbatim from the pre-split routes.py.
"""
from sqlalchemy.orm import joinedload

from models import SessionExercise, WorkoutSession
from features.gym import stats
from features.gym.scope import current_user_id


def load_performed(exercise_ids=None, since=None, include_active=False, exclude_session_exercise_ids=None):
    """Every exercise-as-performed with at least one completed set, as the
    single flat shape stats.py consumes.

    This exists to be called ONCE per request. The pages that need per-exercise
    verdicts need them for the whole catalogue at once, and asking per exercise
    would mean one query per row -- roughly forty on the catalogue page today,
    and worse every time an exercise is added.

    `include_active` also includes the current active (unfinished) session's
    own completed sets. The exercise-detail page and its live progress modal
    need this -- a set just logged mid-workout must show up immediately, not
    only once the workout is finished. Callers building historical
    comparisons (stagnation checks, past-session averages) must leave this
    False: an in-progress workout's still-changing numbers must not leak into
    an average or a "sessions since PR" count before the workout is actually
    done.

    `exclude_session_exercise_ids`, if given, drops those specific
    SessionExercise rows outright before they ever become a PerformedExercise
    -- gym_verlauf uses this to exclude a replaced-away original from its
    own session's totals, the same exclusion performed_from_session() already
    applies when building a single session's `current` for session_report().
    Default (None) excludes nothing, so every other caller here is unaffected.
    """
    query = (
        SessionExercise.query
        .options(
            joinedload(SessionExercise.exercise),
            joinedload(SessionExercise.session),
            joinedload(SessionExercise.sets),
        )
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(WorkoutSession.user_id == current_user_id())
    )
    if not include_active:
        query = query.filter(WorkoutSession.finished_at.isnot(None))
    if exercise_ids is not None:
        query = query.filter(SessionExercise.exercise_id.in_(exercise_ids))
    if since is not None:
        query = query.filter(WorkoutSession.started_at >= since)

    exclude_ids = exclude_session_exercise_ids or ()
    performed = []
    for session_exercise in query.order_by(WorkoutSession.started_at).all():
        if session_exercise.id in exclude_ids:
            continue
        completed = tuple(
            (s.weight, s.reps) for s in session_exercise.sets if s.completed
        )
        if not completed:
            continue
        performed.append(_to_performed(session_exercise, completed))
    return performed


def _to_performed(session_exercise, completed_sets):
    exercise = session_exercise.exercise
    return stats.PerformedExercise(
        exercise_id=session_exercise.exercise_id,
        name=exercise.name,
        muscle_group=exercise.muscle_group,
        is_unilateral=exercise.is_unilateral,
        weight_increment=exercise.weight_increment,
        stack_kg=tuple(exercise.stack_kg) if exercise.stack_kg else None,
        position=session_exercise.position,
        session_id=session_exercise.session_id,
        started_at=session_exercise.session.started_at,
        finished_at=session_exercise.session.finished_at,
        sets=completed_sets,
        # session is already joinedload()ed by load_performed(), so this costs
        # no extra query.
        is_deload=session_exercise.session.is_deload,
    )


def _session_rest_entries(session_):
    """(completed_at, planned_seconds) for every completed set in a session,
    in the shape stats.rest_gaps() expects. Planned time falls back to the
    exercise's default when the session didn't override it.

    Shared by session_detail's finished branch and gym_statistik's habit
    figure -- the planned-rest fallback chain is a business rule, and having
    it written out twice meant either copy could drift from the other with
    nothing to catch it.
    """
    return [
        (s.completed_at, se.rest_seconds if se.rest_seconds is not None
         else se.exercise.default_rest_seconds)
        for se in session_.exercises for s in se.sets
        if s.completed and s.completed_at is not None
    ]


def performed_from_session(session_):
    """This session's exercises as performed.

    A replaced-away original is skipped: its slot is represented by the
    substitute that took over, and counting both would inflate the session's
    totals with an exercise the historical comparison was never scoped to.
    """
    performed = []
    for session_exercise in session_.exercises:
        if session_exercise.replaced_by:
            continue
        completed = tuple(
            (s.weight, s.reps) for s in session_exercise.sets if s.completed
        )
        if not completed:
            continue
        performed.append(_to_performed(session_exercise, completed))
    return performed
