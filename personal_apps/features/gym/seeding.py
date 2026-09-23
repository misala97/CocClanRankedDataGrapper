"""Turning history into a session's pending sets.

Split out of routes.py so sharing.py can call it too, without a circular
import -- sharing.py's module docstring already states it cannot import
routes.py, since routes.py imports sharing. No Flask blueprint here, same as
push.py: this is a concern module, not a route surface.

Every history lookup here takes an explicit `user_id`, defaulting to the
caller's own id (current_user_id()) so every existing call site in routes.py
is unchanged. sharing.reconcile_follower is the one caller that must pass it
explicitly: reconciliation runs inside the LEADER's request, where
current_user_id() names the wrong person. Since the one exercise list
(2026-09-23) both lifters log the same exercise_id, so defaulting there
would not find nothing -- it would quietly seed the follower from the
LEADER's history, which is worse.
"""
import datetime as dt

from sqlalchemy.orm import contains_eager, selectinload

from extensions import db
from models import Exercise, SessionExercise, SessionSet, WorkoutSession
from features.gym import stats
from features.gym.exercises import setup as exercise_setup
from features.gym.scope import current_user_id


def _owner(session_, user_id):
    """Whose step and stack stops a deload is scaled on: the session's lifter.
    session_ always carries them; the fallbacks cover a session still being
    built."""
    return session_.user_id or user_id or current_user_id()


def _session_exercise_e1rm(session_exercise):
    """The best estimated 1RM among this row's completed sets. What "best"
    means when two past performances compete: 60x12 beats 62x6, because more
    reps at similar weight is the stronger performance, and comparing raw top
    weight would seed the six-rep session as the better one."""
    return max(
        (stats.epley_1rm(s.weight, s.reps) for s in session_exercise.sets if s.completed),
        default=0.0,
    )


def _last_session_exercise(exercise_id, position=None, user_id=None, exclude_session_id=None):
    """The SessionExercise to seed from -- see _pick_session_exercise, which
    also says which rule picked it."""
    return _pick_session_exercise(exercise_id, position=position, user_id=user_id,
                                  exclude_session_id=exclude_session_id)[0]


def _seed_source(picked):
    """Where a plan's numbers come from, for the screen to say out loud.

    `picked` is _pick_session_exercise's return value. None when there is no
    history at all (the default plan names no workout). The owner kept the
    'earlier_slot' fallback on 2026-09-20 on the condition that it is visible:
    a slot later than anything in the fresh window is seeded from a fresher
    one, so the numbers may run heavy, and the lifter should be told rather
    than left to wonder why moving an exercise down changed nothing.
    """
    session_exercise, basis = picked
    if session_exercise is None:
        return None
    return {'date': session_exercise.session.started_at,
            'position': session_exercise.position,
            'basis': basis}


def _pick_session_exercise(exercise_id, position=None, user_id=None, exclude_session_id=None):
    """(SessionExercise to seed from, which rule picked it) -- or (None, None).

    `exclude_session_id` is the workout being seeded, which is never its own
    history. It qualifies on every other count the moment one set is logged --
    fresh, and quite possibly the best e1RM on record -- so without this the
    running workout won its own pick: the source line named today, and a
    second row of the same lift was seeded from the first.

    The second value is 'slot', 'earlier_slot' or 'layoff', matching rules 2,
    2's fallback and 3 below. Owner-decided rules, in order:

    1. **Fresh history wins, best first.** Among sessions inside
       stats.ROLLING_WINDOW_DAYS, pick the highest e1RM -- not the most
       recent. You were provably that strong within the window; the seed
       should say so.

    2. **Fatigue direction.** Position is a fatigue proxy: a result at the
       SAME OR A LATER position is at least as impressive at this one (you
       did it more tired), while a result from an earlier, fresher slot
       overstates what this slot can do. So fresh candidates at
       position >= `position` are preferred; only when the fresh window has
       nothing at or after this slot do fresher-slot sessions compete. This
       is what makes "did it better in slot 5 last week" beat "did it
       moderately in slot 2 three weeks ago" when seeding slot 2.

    3. **A layoff seeds the last thing you did, never your best.** With
       nothing inside the window at all, fall back to the most recent
       session at any position. Best-ever would hand a detrained body its
       all-time PR; most-recent is the honest re-entry point, adjusted in
       the moment.

    Deload sessions are skipped entirely -- they are a deliberately light
    week, not what you should come back to, and seeding from one would carry
    the reduction forward into every session after it. History is always the
    lifter's own (`user_id`), never a partner's.
    """
    if user_id is None:
        user_id = current_user_id()
    query = (
        SessionExercise.query
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(
            SessionExercise.exercise_id == exercise_id,
            SessionExercise.sets.any(SessionSet.completed == True),
            # Never seed from a deload -- see the docstring.
            WorkoutSession.is_deload == False,
            WorkoutSession.user_id == user_id,
        ))
    if exclude_session_id is not None:
        query = query.filter(WorkoutSession.id != exclude_session_id)
    pool = (
        query
        .order_by(WorkoutSession.started_at.desc())
        # Both are read for every row below (started_at for the window, the
        # sets for the e1RM). Lazily that is two queries per past workout of
        # this exercise, and a reorder asks this for every row it moves.
        .options(contains_eager(SessionExercise.session),
                 selectinload(SessionExercise.sets))
        .all()
    )
    if not pool:
        return None, None

    cutoff = dt.datetime.utcnow() - dt.timedelta(days=stats.ROLLING_WINDOW_DAYS)
    fresh = [se for se in pool if se.session.started_at >= cutoff]
    if not fresh:
        # Layoff: rule 3. `pool` is newest-first.
        return pool[0], 'layoff'

    # Best e1RM; the newest wins a tie because the lists are newest-first
    # and max() keeps the first of equals.
    at_or_after = [se for se in fresh if position is None or se.position >= position]
    if at_or_after:
        return max(at_or_after, key=_session_exercise_e1rm), 'slot'
    return max(fresh, key=_session_exercise_e1rm), 'earlier_slot'


def _last_performance(exercise_id, position=None, user_id=None, picked=None):
    """The last completed set of the session _last_session_exercise picks
    (best fresh e1RM, fatigue-direction preferred, most-recent after a
    layoff), used to pre-fill the steppers and the add-set form.

    `picked` is an already-made _pick_session_exercise result for the same
    arguments, for a caller that needs the pick for something else too."""
    if picked is None:
        picked = _pick_session_exercise(exercise_id, position=position, user_id=user_id)
    last_session_exercise = picked[0]
    if not last_session_exercise:
        return None
    completed_sets = [s for s in last_session_exercise.sets if s.completed]
    if not completed_sets:
        return None
    last_set = completed_sets[-1]
    return {'weight': last_set.weight, 'reps': last_set.reps}


def _last_full_performance(exercise_id, position=None, user_id=None, exclude_session_id=None):
    """All completed sets of the session _last_session_exercise picks, in
    order -- used to pre-fill a new session's sets, mirroring the strongest
    recent performance that is valid evidence for this slot."""
    last_session_exercise = _last_session_exercise(
        exercise_id, position=position, user_id=user_id,
        exclude_session_id=exclude_session_id)
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
    # session_.id is None while gym_start is still building the workout --
    # nothing to exclude yet, and nothing of it is in the database to find.
    seeded = _last_full_performance(exercise_id, position=position, user_id=user_id,
                                    exclude_session_id=session_.id)
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
    setup = (exercise_setup(_owner(session_, user_id), exercise)
             if exercise else None)
    increment = stats.resolve_increment(
        setup.weight_increment if setup else None,
        bool(exercise and exercise.is_unilateral),
    )
    return [
        SessionSet(
            position=j,
            weight=stats.deload_weight(prev['weight'], pct, increment,
                                       stack_kg=setup.stack_kg if setup else None),
            base_weight=prev['weight'],
            reps=stats.DELOAD_REPS,
            base_reps=prev['reps'],
            completed=False,
        )
        for j, prev in enumerate(seeded, start=1)
    ]


def _plan_signature(sets):
    """What a plan says, without which rows say it."""
    return [(s.weight, s.reps) for s in sets]


def reseed_for_slot(session_, session_exercise, old_position, new_position, user_id=None):
    """Re-derive a moved exercise's pending sets for the slot it landed in.
    Returns True when a set changed.

    Position is a fatigue proxy (see _last_session_exercise), so a plan seeded
    for one slot is stale in another. But only a plan nobody has touched is
    ours to replace, and three things say somebody has:

    - a completed set: the lifter has started, and these are real data;
    - a skipped exercise: it carries no pending sets at all, by
      gym_toggle_skip_session_exercise's own rule;
    - pending sets that are no longer what seeding handed out for the OLD
      slot: a typed weight, a set removed to do three instead of four, or a
      deload that was flagged after the first set and so never rescaled the
      plan. The plan is the lifter's from that point on. This is derived by
      asking seeding the same question again rather than kept as a flag on the
      row, so it needs no schema and cannot drift from what seeding does.

    Moving ONE exercise renumbers every row between its old and new slot, so
    this runs for rows the lifter never touched -- which is exactly why the
    old clear-and-reseed destroyed typed weights on exercises nobody dragged.

    The rows are rewritten IN PLACE, keeping their ids: the live screen keys
    its editors and its confirm button on set ids, and a partner's phone may be
    about to post against one.

    `user_id` is whose history to read -- see _seeded_sets.
    """
    if old_position == new_position or session_exercise.skipped:
        return False
    current = list(session_exercise.sets)
    if any(s.completed for s in current):
        return False
    exercise_id = session_exercise.exercise_id
    seeded_for_old_slot = _seeded_sets(session_, exercise_id, old_position, user_id=user_id)
    if _plan_signature(current) != _plan_signature(seeded_for_old_slot):
        return False
    wanted = _seeded_sets(session_, exercise_id, new_position, user_id=user_id)
    if _plan_signature(current) == _plan_signature(wanted):
        return False

    for kept, fresh in zip(current, wanted):
        kept.weight, kept.reps = fresh.weight, fresh.reps
        kept.base_weight, kept.base_reps = fresh.base_weight, fresh.base_reps
        kept.is_default_seeded = bool(fresh.is_default_seeded)
        kept.position = fresh.position
    for surplus in current[len(wanted):]:
        session_exercise.sets.remove(surplus)
    for extra in wanted[len(current):]:
        session_exercise.sets.append(extra)
    return True


def _seeded_suggestion(session_, exercise, position, user_id=None, picked=None):
    """The single weight/reps pair the steppers pre-fill with, deload-aware.

    The scalar sibling of _seeded_sets, and it honours the deload for exactly
    the same reason: history is recorded at full working weight, so offering
    it untouched during a deload hands the lifter straight back the
    prescription they just asked for.

    _seeded_sets alone was not enough because a session started WITHOUT a
    template has no sets for gym_toggle_deload to scale, so on that path the
    suggestion is the only number the lifter ever sees. (Mid-session adds used
    to be a second such gap; gym_add_session_exercise seeds a full plan now,
    like every other path that puts an exercise into a session.)
    """
    if picked is None:
        picked = _pick_session_exercise(exercise.id, position=position, user_id=user_id,
                                        exclude_session_id=session_.id)
    last = _last_performance(exercise.id, position=position, user_id=user_id, picked=picked)
    if not last:
        return None
    pct = session_.deload_pct if session_.is_deload else None
    if not pct:
        return last
    setup = exercise_setup(_owner(session_, user_id), exercise)
    increment = stats.resolve_increment(setup.weight_increment, exercise.is_unilateral)
    return {'weight': stats.deload_weight(last['weight'], pct, increment, stack_kg=setup.stack_kg),
            'reps': stats.DELOAD_REPS}
