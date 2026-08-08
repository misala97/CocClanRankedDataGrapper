"""Turning history into a session's pending sets.

Split out of routes.py so sharing.py can call it too, without a circular
import -- sharing.py's module docstring already states it cannot import
routes.py, since routes.py imports sharing. No Flask blueprint here, same as
matching.py and push.py: this is a concern module, not a route surface.

Every history lookup here takes an explicit `user_id`, defaulting to the
caller's own id (current_user_id()) so every existing call site in routes.py
is unchanged. sharing.reconcile_follower is the one caller that must pass it
explicitly: reconciliation runs inside the LEADER's request, where
current_user_id() names the wrong person, and the exercise_id it is paired
with is already the FOLLOWER's own catalogue row -- silently defaulting to
current_user_id() there would look up the leader's history (or, since the
leader's WorkoutSessions never carry the follower's exercise_id, more likely
find nothing and silently fall back to the default plan even when the
follower has real history for that exercise).
"""
import datetime as dt

from extensions import db
from models import Exercise, SessionExercise, SessionSet, WorkoutSession
from features.gym import stats
from features.gym.scope import current_user_id


def _last_session_exercise(exercise_id, position=None, user_id=None):
    """The most recent SessionExercise (across any session) with at least one
    *completed* set for this exercise.

    If `position` is given, prefers a match where the exercise was performed
    in that same position within its session -- exercise order affects
    fatigue (the same exercise done 1st is fresher than done 3rd), so a
    suggestion should reflect what you actually did in that same slot
    before, not just the most recent time you did the exercise at all.

    That preference is only honoured while the slot's own history is still
    CURRENT (within stats.ROLLING_WINDOW_DAYS). Reorder an exercise and never
    update the template, and months later the template still names the old
    slot -- without the recency guard the pre-fill would resurrect whatever
    you lifted there back then, which can be far below your actual working
    weight today. Seated Row, real data: slot 2 is on 69 kg while slot 3 still
    remembered 61 kg from months earlier, so starting the template pre-filled
    61 and had to be corrected by hand every time.

    The fatigue argument is about being fresher or more tired in a given
    slot, and it only holds while both numbers describe the same training
    period. Once the slot's record is stale, "most recent, any position" is
    the more honest answer, and the lifter adjusts in the moment.

    Falls back to the most recent regardless of position if you've never done
    it in that position, or if that record has gone stale.

    Deload sessions are skipped entirely. They are a deliberately light week,
    not what you should come back to -- seeding from one would carry the
    reduction forward into every session after it.
    """
    if user_id is None:
        user_id = current_user_id()
    base_query = (
        SessionExercise.query
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(
            SessionExercise.exercise_id == exercise_id,
            SessionExercise.sets.any(SessionSet.completed == True),
            # Never seed from a deload. Pre-filling the next session at 70 %
            # would make the following one seed from *that*, and the lifter
            # would silently never return to their real working weight.
            WorkoutSession.is_deload == False,
            # Suggestions come from your own training, never your partner's.
            WorkoutSession.user_id == user_id,
        )
    )
    if position is not None:
        match = base_query.filter(SessionExercise.position == position).order_by(WorkoutSession.started_at.desc()).first()
        # same slot, but only while that record still describes current
        # training -- see the docstring for why staleness overrides fatigue
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=stats.ROLLING_WINDOW_DAYS)
        if match and match.session.started_at >= cutoff:
            return match
    return base_query.order_by(WorkoutSession.started_at.desc()).first()


def _last_performance(exercise_id, position=None, user_id=None):
    """Most recent completed set for this exercise (optionally position-
    matched, see _last_session_exercise), used to pre-fill the add-set form."""
    last_session_exercise = _last_session_exercise(exercise_id, position=position, user_id=user_id)
    if not last_session_exercise:
        return None
    completed_sets = [s for s in last_session_exercise.sets if s.completed]
    if not completed_sets:
        return None
    last_set = completed_sets[-1]
    return {'weight': last_set.weight, 'reps': last_set.reps}


def _last_full_performance(exercise_id, position=None, user_id=None):
    """All completed sets from the most recent (optionally position-matched)
    session that logged this exercise, in order -- used to pre-fill a new
    session's sets when starting from a template, mirroring what was
    actually done last time in that same slot."""
    last_session_exercise = _last_session_exercise(exercise_id, position=position, user_id=user_id)
    if not last_session_exercise:
        return []
    return [{'weight': s.weight, 'reps': s.reps} for s in last_session_exercise.sets if s.completed]


def _seeded_sets(session_, exercise_id, position, user_id=None):
    """Pending sets for `exercise_id` in `position` -- pre-filled from history
    when there is any (honouring the session's deload), and a plain default plan
    when there is none.

    `user_id` is whose history to read, not whose session this is (`session_`
    already carries that): the two agree at every call site except
    sharing.reconcile_follower, which seeds the FOLLOWER's row from inside the
    LEADER's request -- see the module docstring.

    History is always recorded at full working weight (_last_session_exercise
    skips deload sessions on purpose), so seeding raw would hand a deload
    session the untouched working weights. Every call site that re-seeds a
    slot -- reorder, un-skip -- can run *after* the deload was switched on,
    which is exactly when that silently undid the prescription. Scaling here,
    at the one place sets are derived from history, keeps the two in step
    wherever a new one is added.

    base_weight is set the same way gym_toggle_deload sets it, so switching
    the deload back off restores these sets to the working weight like any
    other.
    """
    seeded = _last_full_performance(exercise_id, position=position, user_id=user_id)
    if not seeded:
        # No history: a plain default plan, NOT a deload-scaled one. A deload is
        # a percentage of a real working weight, and there isn't one here --
        # scaling an invented number would dress a placeholder up as a
        # prescription. base_weight stays None for the same reason: there is no
        # working weight for gym_toggle_deload to restore this to. Marked
        # is_default_seeded so gym_toggle_deload can tell these apart from a
        # real set that happens to sit at the same weight, regardless of
        # which order add-exercise and the deload toggle happen in.
        return [
            SessionSet(position=j, weight=stats.DEFAULT_PLAN_WEIGHT,
                       reps=stats.DEFAULT_PLAN_REPS, completed=False,
                       is_default_seeded=True)
            for j in range(1, stats.DEFAULT_PLAN_SETS + 1)
        ]

    pct = session_.deload_pct if session_.is_deload else None
    if not pct:
        return [
            SessionSet(position=j, weight=prev['weight'], reps=prev['reps'], completed=False)
            for j, prev in enumerate(seeded, start=1)
        ]

    exercise = db.session.get(Exercise, exercise_id)
    increment = stats.resolve_increment(
        exercise.weight_increment if exercise else None,
        bool(exercise and exercise.is_unilateral),
    )
    return [
        SessionSet(
            position=j,
            weight=stats.deload_weight(prev['weight'], pct, increment,
                                       stack_kg=exercise.stack_kg if exercise else None),
            base_weight=prev['weight'],
            reps=stats.DELOAD_REPS,
            base_reps=prev['reps'],
            completed=False,
        )
        for j, prev in enumerate(seeded, start=1)
    ]


def _seeded_suggestion(session_, exercise, position, user_id=None):
    """The single weight/reps pair the steppers pre-fill with, deload-aware.

    The scalar sibling of _seeded_sets, and it honours the deload for exactly
    the same reason: history is recorded at full working weight, so offering
    it untouched during a deload hands the lifter straight back the
    prescription they just asked for.

    _seeded_sets alone was not enough because it only runs where sets are
    created -- starting from a template, un-skipping, reordering. An exercise
    added mid-session gets no sets at all, and a session started WITHOUT a
    template has none for gym_toggle_deload to scale either, so on that path
    the suggestion is the only number the lifter ever sees.
    """
    last = _last_performance(exercise.id, position=position, user_id=user_id)
    if not last:
        return None
    pct = session_.deload_pct if session_.is_deload else None
    if not pct:
        return last
    increment = stats.resolve_increment(exercise.weight_increment, exercise.is_unilateral)
    return {'weight': stats.deload_weight(last['weight'], pct, increment, stack_kg=exercise.stack_kg),
            'reps': stats.DELOAD_REPS}
