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
from features.gym.exercises import setup as exercise_setup, setups as exercise_setups
from features.gym.scope import current_user_id


def counts(s):
    """Whether a logged set counts: stats.set_counts(), the one rule (Q1)."""
    return stats.set_counts(s.completed, s.reps)


def done_sets(session_exercise):
    """The sets of one exercise that count, as (weight, reps) in logged order."""
    return tuple((s.weight, s.reps) for s in session_exercise.sets if counts(s))


def load_performed(exercise_ids=None, since=None):
    """Every exercise-as-performed with at least one completed set, as the
    single flat shape stats.py consumes.

    This exists to be called ONCE per request. The pages that need per-exercise
    verdicts need them for the whole catalogue at once, and asking per exercise
    would mean one query per row -- roughly forty on the catalogue page today,
    and worse every time an exercise is added.

    Finished workouts only: an in-progress workout's still-changing numbers
    must not leak into an average or a "sessions since PR" count before it is
    done, and the exercise page leaves the running workout out too (Q3,
    G-109) -- that was the last caller that wanted it in.

    Only the sets that count (counts()); a replaced-away original's are
    among them, as everywhere (Q1).
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
        .filter(WorkoutSession.finished_at.isnot(None))
    )
    if exercise_ids is not None:
        query = query.filter(SessionExercise.exercise_id.in_(exercise_ids))
    if since is not None:
        query = query.filter(WorkoutSession.started_at >= since)

    rows = query.order_by(WorkoutSession.started_at).all()
    # Every row is the caller's own, so one lifter's settings cover them all.
    setups = exercise_setups(current_user_id(), {se.exercise for se in rows})
    performed = []
    for session_exercise in rows:
        completed = done_sets(session_exercise)
        if not completed:
            continue
        performed.append(_to_performed(session_exercise, completed,
                                       setups[session_exercise.exercise_id]))
    return performed


def _to_performed(session_exercise, completed_sets, setup=None):
    """`setup` is the session owner's Setup for the exercise; looked up here
    when the caller did not batch it."""
    exercise = session_exercise.exercise
    if setup is None:
        setup = exercise_setup(session_exercise.session.user_id, exercise)
    return stats.PerformedExercise(
        exercise_id=session_exercise.exercise_id,
        name=exercise.name,
        muscle_group=exercise.muscle_group,
        is_unilateral=exercise.is_unilateral,
        weight_increment=setup.weight_increment,
        stack_kg=tuple(setup.stack_kg) if setup.stack_kg else None,
        position=session_exercise.position,
        session_id=session_exercise.session_id,
        started_at=session_exercise.session.started_at,
        finished_at=session_exercise.session.finished_at,
        sets=completed_sets,
        # session is already joinedload()ed by load_performed(), so this costs
        # no extra query.
        is_deload=session_exercise.session.is_deload,
    )


def _session_rest_entries(session_, setups=None):
    """(completed_at, planned_seconds) for every completed set in a session,
    in the shape stats.rest_gaps() expects. Planned time falls back to the
    exercise's default when the session didn't override it.

    Shared by session_detail's finished branch and gym_statistik's habit
    figure -- the planned-rest fallback chain is a business rule, and having
    it written out twice meant either copy could drift from the other with
    nothing to catch it. The fallback is the session owner's rest for the
    exercise, not the list's: `setups` is theirs, looked up here when a
    caller walking many sessions did not batch it.
    """
    if setups is None:
        setups = exercise_setups(session_.user_id, {se.exercise for se in session_.exercises})
    return [
        (s.completed_at, se.rest_seconds if se.rest_seconds is not None
         else setups[se.exercise_id].default_rest_seconds)
        for se in session_.exercises for s in se.sets
        if s.completed and s.completed_at is not None
    ]


def performed_from_session(session_):
    """This session's exercises as performed.

    A replaced-away original is kept: the sets logged on it before the swap
    were done, and they count like any other (Q1). It used to be skipped
    here -- and so left out of the debrief's totals while Heute and Statistik
    counted it.
    """
    setups = exercise_setups(session_.user_id, {se.exercise for se in session_.exercises})
    performed = []
    for session_exercise in session_.exercises:
        completed = done_sets(session_exercise)
        if not completed:
            continue
        performed.append(_to_performed(session_exercise, completed,
                                       setups[session_exercise.exercise_id]))
    return performed
