"""The plan model (walkthrough D2 P1): a routine row's set count and rep range.

A routine used to say which exercises, in which order, and nothing else, so
every start copied the set count of ONE earlier workout -- whichever the
seeding rules picked -- and one short test workout shrank the routine for
good (G-050). Each routine row now keeps `target_sets`, `rep_min` and
`rep_max` (TemplateExercise): filled from the lifter's history the first time
the routine is started, then changed only by an explicit edit, so nothing
derived afresh can drift them.

The weights still come from the seed pick (seeding._pick_session_exercise).
This module says how many sets there are, and the range "Nächstes Mal" aims
at (stats.next_target). No blueprint here, like seeding.py: sharing.py and
the routes both read it.
"""
from sqlalchemy.orm import selectinload

from extensions import db
from models import SessionExercise, SessionSet, TemplateExercise, WorkoutSession
from features.gym import stats

#: The set count reads this many of the routine's own last workouts.
COUNT_WORKOUTS = 3


def _counted(session_exercise):
    return [s for s in session_exercise.sets if stats.set_counts(s.completed, s.reps)]


def _recent_rows(exercise_id, user_id, limit, template_id=None):
    """The exercise's rows in the lifter's newest finished, non-deload
    workouts that hold a set of it that counts -- of one routine when
    `template_id` is given. Newest first, at most `limit`."""
    query = (
        SessionExercise.query
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(
            SessionExercise.exercise_id == exercise_id,
            SessionExercise.sets.any((SessionSet.completed == True) & (SessionSet.reps >= 1)),
            WorkoutSession.user_id == user_id,
            WorkoutSession.finished_at.isnot(None),
            # A deload is a light week on purpose, not the plan's shape.
            WorkoutSession.is_deload == False,
        ))
    if template_id is not None:
        query = query.filter(WorkoutSession.template_id == template_id)
    return (query.order_by(WorkoutSession.started_at.desc())
            .options(selectinload(SessionExercise.sets))
            .limit(limit)
            .all())


def history_set_count(exercise_id, user_id, template_id=None):
    """How many sets the exercise gets, from history: the most any of the
    routine's last COUNT_WORKOUTS workouts held of it (stats.plan_set_count
    -- a cut-short workout does not shrink it); none there, the lifter's
    last COUNT_WORKOUTS with it anywhere; none at all, the default."""
    rows = []
    if template_id is not None:
        rows = _recent_rows(exercise_id, user_id, COUNT_WORKOUTS, template_id=template_id)
    if not rows:
        rows = _recent_rows(exercise_id, user_id, COUNT_WORKOUTS)
    return stats.plan_set_count([len(_counted(row)) for row in rows])


def history_rep_range(exercise_id, user_id):
    """The rep range from history, any routine (stats.rep_range_from)."""
    rows = _recent_rows(exercise_id, user_id, stats.RANGE_WORKOUTS)
    return stats.rep_range_from([[(s.weight, s.reps) for s in _counted(row)] for row in rows])


def row_plan(row, user_id, template_id):
    """A row of routine `template_id` as (sets, rep_min, rep_max): its own
    plan, and for what it has none of yet, what `user_id`'s history gives --
    the numbers the next start fills in."""
    sets = row.target_sets
    if sets is None:
        sets = history_set_count(row.exercise_id, user_id, template_id=template_id)
    if row.rep_min is None or row.rep_max is None:
        rep_min, rep_max = history_rep_range(row.exercise_id, user_id)
    else:
        rep_min, rep_max = row.rep_min, row.rep_max
    return sets, rep_min, rep_max


def fill_routine_plan(template, user_id):
    """Give every row of `template` that has no plan yet one from `user_id`'s
    history. Once: a filled row is the lifter's from then on, and only an
    explicit edit changes it. Does not commit."""
    for row in template.exercises:
        row.target_sets, row.rep_min, row.rep_max = row_plan(row, user_id, template.id)


def replace_routine_rows(template, rows):
    """Make `rows` the routine's rows ("Routine aktualisieren"), each keeping
    the plan its exercise had in the routine: the rows are rebuilt from the
    workout, and a rebuild that dropped the plan would lose it the way rest
    was lost (G-076). An exercise new to the routine starts unfilled, and the
    next start fills it. Does not commit."""
    kept = {}
    for row in template.exercises:
        kept.setdefault(row.exercise_id, (row.target_sets, row.rep_min, row.rep_max))
    template.exercises.clear()
    db.session.flush()
    for row in rows:
        row.target_sets, row.rep_min, row.rep_max = kept.get(row.exercise_id,
                                                             (None, None, None))
    template.exercises.extend(rows)


def routine_row(session_, exercise_id):
    """The workout's routine row for this exercise -- None for a workout
    without a routine, or an exercise the routine does not hold (added or
    swapped in)."""
    if session_.template_id is None:
        return None
    return (TemplateExercise.query
            .filter_by(template_id=session_.template_id, exercise_id=exercise_id)
            .order_by(TemplateExercise.position)
            .first())


def planned_count(session_, exercise_id):
    """The set count the workout's routine keeps for this exercise, or None:
    no routine row, or one not filled yet (seeding keeps its old rule)."""
    row = routine_row(session_, exercise_id)
    return row.target_sets if row is not None else None


def slot_exercise_id(session_exercise):
    """The exercise whose routine slot a workout row fills: its own, or for a
    substitute the one it stands in for -- the original at the root of the
    chain, which is the one the routine holds."""
    root, seen = session_exercise, {session_exercise.id}
    while root.replaces is not None and root.replaces.id not in seen:
        root = root.replaces
        seen.add(root.id)
    return root.exercise_id


def slot_count(session_, session_exercise):
    """The set count the routine keeps for a workout row's slot, or None."""
    return planned_count(session_, slot_exercise_id(session_exercise))


def routine_rows(session_):
    """Every routine row of the workout by exercise -- routine_row for a
    whole workout at once, for a caller that asks for each of its rows."""
    rows = {}
    if session_.template is not None:
        for row in session_.template.exercises:
            rows.setdefault(row.exercise_id, row)
    return rows


def target_for(session_exercise, rows, base_sets, history, increment, stack_kg):
    """What to lift, set by set (stats.next_target), building on `base_sets`
    -- the counted sets of the lifter's last workout of the exercise.

    The rep range is the exercise's own routine row's; an exercise the
    routine does not hold (a freeform workout, one added or swapped in) takes
    the range its `history` gives -- counted sets per workout, newest first
    (stats.rep_range_from). The count is the slot's, as seeding plans it:
    the routine row's, else as many sets as the base."""
    own = rows.get(session_exercise.exercise_id)
    if own is not None and own.rep_min is not None and own.rep_max is not None:
        rep_min, rep_max = own.rep_min, own.rep_max
    else:
        rep_min, rep_max = stats.rep_range_from(history)
    slot = rows.get(slot_exercise_id(session_exercise))
    count = slot.target_sets if slot is not None and slot.target_sets else len(base_sets)
    return stats.next_target(base_sets, rep_min, rep_max, count, increment, stack_kg)
