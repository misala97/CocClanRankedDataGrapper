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
from typing import NamedTuple

from sqlalchemy.orm import contains_eager, selectinload

from extensions import db
from models import Exercise, SessionExercise, SessionSet, WorkoutSession
from features.gym import plan, stats
from features.gym.exercises import setup as exercise_setup
from features.gym.scope import current_user_id


def _owner(session_, user_id):
    """Whose step and stack stops a deload is scaled on: the session's lifter.
    session_ always carries them; the fallbacks cover a session still being
    built."""
    return session_.user_id or user_id or current_user_id()


def _done(session_exercise):
    """The row's sets that count (stats.set_counts): a 0-rep leftover is no
    set to copy into a plan (G-038)."""
    return [s for s in session_exercise.sets if stats.set_counts(s.completed, s.reps)]


def _session_exercise_e1rm(session_exercise):
    """The best judged e1RM among this row's sets. What "best" means when two
    past performances compete: 60x12 beats 62x6, because more reps at similar
    weight is the stronger performance, and comparing raw top weight would
    seed the six-rep session as the better one.

    Judged (stats.judged_e1rm, D3): a set above twelve reps does not make a
    workout the best one -- 40 × 25 "beat" 55 × 8, so one burnout or typo set
    decided the next plan (G-130). A row with no judged set ranks below every
    row with one."""
    return max(
        (value for value in (stats.judged_e1rm(s.weight, s.reps) for s in _done(session_exercise))
         if value is not None),
        default=-1.0,
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

    The live card says it as one line of numbers (G-053): the sets lifted
    that day, and "Letztes Mal" only when `is_latest` -- when the workout
    picked is also the newest one that counts. Deloads are left out of
    "newest" as they are out of the pick.
    """
    session_exercise, basis, newest = picked
    if session_exercise is None:
        return None
    return {'date': session_exercise.session.started_at,
            'position': session_exercise.position,
            'basis': basis,
            # By workout, not by row: the newest workout can hold the
            # exercise twice (added twice, or swapped for itself), and either
            # row of it is "last time".
            'is_latest': session_exercise.session_id == newest.session_id,
            'sets': [{'weight': s.weight, 'reps': s.reps}
                     for s in _done(session_exercise)]}


class Pick(NamedTuple):
    """_pick_session_exercise's answer: the row to seed from and the rule
    that chose it, plus the newest row that counts, so a caller can tell
    "last time" from "best lately" without asking again."""
    session_exercise: SessionExercise | None
    basis: str | None
    newest: SessionExercise | None


def _pick_session_exercise(exercise_id, position=None, user_id=None, exclude_session_id=None):
    """Pick(SessionExercise to seed from, which rule picked it, the newest
    row that counts) -- or Pick(None, None, None).

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
    return _pick_session_exercises([(exercise_id, position)], user_id=user_id,
                                   exclude_session_id=exclude_session_id)[(exercise_id, position)]


def _pick_session_exercises(wanted, user_id=None, exclude_session_id=None):
    """_pick_session_exercise for several (exercise_id, position) pairs, as
    {pair: Pick} -- one pool query for all of them. Asked one exercise at a
    time, the live payload spent two queries per exercise on it, every time
    it was built (walkthrough G-140). The rules are _pick_session_exercise's
    and live in _pick_from."""
    if user_id is None:
        user_id = current_user_id()
    exercise_ids = sorted({exercise_id for exercise_id, _ in wanted})
    pools = {exercise_id: [] for exercise_id in exercise_ids}
    if exercise_ids:
        query = (
            SessionExercise.query
            .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
            .filter(
                SessionExercise.exercise_id.in_(exercise_ids),
                # A set that counts (stats.set_counts): done, with reps.
                SessionExercise.sets.any((SessionSet.completed == True) & (SessionSet.reps >= 1)),
                # Never seed from a deload -- see _pick_session_exercise.
                WorkoutSession.is_deload == False,
                WorkoutSession.user_id == user_id,
            ))
        if exclude_session_id is not None:
            query = query.filter(WorkoutSession.id != exclude_session_id)
        rows = (
            query
            # Newest first; a lift twice in one workout, the later row first,
            # so the order does not depend on how the rows came back.
            .order_by(WorkoutSession.started_at.desc(), SessionExercise.id.desc())
            # Both are read for every row below (started_at for the window,
            # the sets for the e1RM). Lazily that is two queries per past
            # workout of the exercise, and a reorder asks this for every row
            # it moves.
            .options(contains_eager(SessionExercise.session),
                     selectinload(SessionExercise.sets))
            .all()
        )
        for row in rows:
            pools[row.exercise_id].append(row)
    return {(exercise_id, position): _pick_from(pools[exercise_id], position)
            for exercise_id, position in wanted}


def _pick_from(pool, position):
    """The pick among one exercise's `pool`, newest first -- the rules in
    _pick_session_exercise's docstring."""
    if not pool:
        return Pick(None, None, None)

    cutoff = dt.datetime.utcnow() - dt.timedelta(days=stats.ROLLING_WINDOW_DAYS)
    fresh = [se for se in pool if se.session.started_at >= cutoff]
    if not fresh:
        # Layoff: rule 3. `pool` is newest-first.
        return Pick(pool[0], 'layoff', pool[0])

    # Best e1RM; the newest wins a tie because the lists are newest-first
    # and max() keeps the first of equals.
    at_or_after = [se for se in fresh if position is None or se.position >= position]
    if at_or_after:
        return Pick(max(at_or_after, key=_session_exercise_e1rm), 'slot', pool[0])
    return Pick(max(fresh, key=_session_exercise_e1rm), 'earlier_slot', pool[0])


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
    completed_sets = _done(last_session_exercise)
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
    return [{'weight': s.weight, 'reps': s.reps} for s in _done(last_session_exercise)]


def _deload_applies(session_):
    """Whether a plan or suggestion made now starts at deload weights: the
    deload is on and it rescaled the plan -- some set carries base_weight --
    or nothing is done yet, so switching it on now would rescale everything.
    Marked after a set was done, the deload only labels the workout and every
    weight stays (session_admin's toggle, "Nur markiert"): a set planned then
    must not drop to 70 % behind a full-weight one (B3 review, un-skip)."""
    if not (session_.is_deload and session_.deload_pct):
        return False
    sets = [s for se in session_.exercises for s in se.sets]
    return (any(s.base_weight is not None for s in sets)
            or not any(stats.set_counts(s.completed, s.reps) for s in sets))


def _seeded_sets(session_, exercise_id, position, user_id=None, count=None):
    """Pending sets for `exercise_id` in `position` -- pre-filled from history
    when there is any (honouring the session's deload), and a blank plan (sets
    with no numbers yet) when there is none.

    How many (D2 P1): the routine row's set count (plan.planned_count) --
    the picked workout's sets cut to it, in order, or its last set repeated
    up to it; with no history, that many blank sets. It used to be however
    many sets the one picked workout held, so a short test workout shrank
    the routine (G-050). `count` names it for a row the routine does not
    hold by that exercise: a substitute stands in for its original's slot.
    No count at all -- no routine, an added exercise, a routine not started
    since the plan model -- keeps the old rule.

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
    if count is None:
        count = plan.planned_count(session_, exercise_id)
    # session_.id is None while gym_start is still building the workout --
    # nothing to exclude yet, and nothing of it is in the database to find.
    seeded = _last_full_performance(exercise_id, position=position, user_id=user_id,
                                    exclude_session_id=session_.id)
    if seeded and count is not None:
        seeded = (seeded + [seeded[-1]] * count)[:count]
    if not seeded:
        # No history: a blank plan -- the set count, no numbers. Any number
        # here would be invented, and an invented number reads as advice (the
        # 20 kg x 8 placeholder this replaced was wrong for almost every
        # exercise). The lifter types the first set; _propagate_default_correction
        # carries it to the rest. Never deload-scaled either: a deload is a
        # percentage of a real working weight, and there isn't one here.
        # Marked is_default_seeded, which both of those read.
        return [
            SessionSet(position=j, weight=None, reps=None, completed=False,
                       is_default_seeded=True)
            for j in range(1, (count or stats.DEFAULT_PLAN_SETS) + 1)
        ]

    pct = session_.deload_pct if _deload_applies(session_) else None
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


def missing_planned_sets(session_, session_exercise, user_id=None):
    """The sets a row coming back from a skip still owes: the plan a fresh
    start would seed (_seeded_sets), less as many sets as the row kept,
    numbered on after them (G-125).

    Skipping drops only the open sets, so what the row keeps was done.
    Un-skipping used to seed only a row with NO set left: one skipped at
    1 of 3 came back "fully done", and its plan was lost.

    A blank plan (no history) takes the numbers of the last set done here,
    as typing the first set carries them to the rest when nothing is skipped
    (routes' _propagate_default_correction) -- and clears the default flag
    the same way.
    """
    kept = sorted(session_exercise.sets, key=lambda s: s.position)
    done = _done(session_exercise)
    last = max(done, key=lambda s: s.position) if done else None
    planned = _seeded_sets(session_, session_exercise.exercise_id,
                           session_exercise.position, user_id=user_id,
                           count=plan.slot_count(session_, session_exercise))
    missing = planned[len(kept):]
    after = kept[-1].position if kept else 0
    for offset, pending in enumerate(missing, start=1):
        pending.position = after + offset
        if last is not None and pending.is_default_seeded:
            pending.weight, pending.reps = last.weight, last.reps
            pending.is_default_seeded = False
    return missing


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
      slot: a typed weight, or a set removed to do three instead of four.
      The plan is the lifter's from that point on. This is derived by asking
      seeding the same question again rather than kept as a flag on the row,
      so it needs no schema and cannot drift from what seeding does. (A
      deload flagged after the first set is no such change: it only labels
      the workout, so seeding plans at working weight then too --
      _deload_applies.)

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
    # Any tick, not the counting rule: the rewrite below keeps `completed`,
    # so a ticked 0-rep leftover would come out of it as a counted set.
    if any(s.completed for s in current):
        return False
    exercise_id = session_exercise.exercise_id
    # The count too: a substitute's plan is its slot's, and asking without
    # it would find every such plan "touched".
    count = plan.slot_count(session_, session_exercise)
    seeded_for_old_slot = _seeded_sets(session_, exercise_id, old_position, user_id=user_id,
                                       count=count)
    if _plan_signature(current) != _plan_signature(seeded_for_old_slot):
        return False
    wanted = _seeded_sets(session_, exercise_id, new_position, user_id=user_id, count=count)
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


def _seeded_suggestion(session_, exercise, position, user_id=None, picked=None, setup=None):
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

    `setup`: the session owner's Setup for the exercise, when the caller has
    them all already -- looked up here otherwise.
    """
    if picked is None:
        picked = _pick_session_exercise(exercise.id, position=position, user_id=user_id,
                                        exclude_session_id=session_.id)
    last = _last_performance(exercise.id, position=position, user_id=user_id, picked=picked)
    if not last:
        return None
    pct = session_.deload_pct if _deload_applies(session_) else None
    if not pct:
        return last
    if setup is None:
        setup = exercise_setup(_owner(session_, user_id), exercise)
    increment = stats.resolve_increment(setup.weight_increment, exercise.is_unilateral)
    return {'weight': stats.deload_weight(last['weight'], pct, increment, stack_kg=setup.stack_kg),
            'reps': stats.DELOAD_REPS}
