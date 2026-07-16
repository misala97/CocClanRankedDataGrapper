import datetime as dt
import os

from flask import Blueprint, current_app, jsonify, render_template, request, redirect, send_from_directory, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Exercise, WorkoutTemplate, TemplateExercise, WorkoutSession, SessionExercise, SessionSet,
    PushSubscription, PendingPush, STALE_SESSION_TIMEOUT, MUSCLE_GROUPS,
)
from auth import login_required

gym_bp = Blueprint('gym', __name__)


@gym_bp.route('/sw.js')
def gym_service_worker():
    # A service worker's default max scope is its own directory -- served
    # from /static/gym/sw.js, it could only ever control /static/gym/*, not
    # /gym/*. Serving it from the site root instead gives it the whole site
    # as its default scope, which covers /gym/. No @login_required: the
    # browser fetches this before any page context, and it's static JS with
    # no user data in it anyway.
    return send_from_directory(
        os.path.join(current_app.root_path, 'static', 'gym'),
        'sw.js',
        mimetype='application/javascript',
    )

DEFAULT_REST_SECONDS = 180  # fallback for newly created exercises when no rest time is given

STAGNATION_THRESHOLD = 4  # sessions without a new estimated-1RM PR before nudging toward progressive overload



def _to_float(value, fallback=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _to_int(value, fallback=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _clean_muscle_group(value, current=None):
    """Restricts new values to MUSCLE_GROUPS, but if the submitted value is
    just the exercise's existing value coming back unchanged (e.g. a legacy
    free-text category from before this enum existed), preserve it instead
    of silently nulling it out -- only an actual attempt to change it is
    held to the fixed list."""
    value = (value or '').strip()
    if value in MUSCLE_GROUPS:
        return value
    if current and value == current:
        return current
    return None


def _get_active_session():
    """The one in-progress workout, if any. Sessions left open past
    STALE_SESSION_TIMEOUT are treated as abandoned and auto-finished here,
    capped at started_at + timeout rather than "now"."""
    session_ = (
        WorkoutSession.query
        .filter_by(finished_at=None)
        .order_by(WorkoutSession.started_at.desc())
        .first()
    )
    if session_ and dt.datetime.utcnow() - session_.started_at > STALE_SESSION_TIMEOUT:
        session_.finished_at = session_.started_at + STALE_SESSION_TIMEOUT
        session_.rest_ends_at = None
        session_.resting_set_id = None
        _cancel_pending_push(session_)
        db.session.commit()
        return None
    return session_


@gym_bp.context_processor
def inject_gym_nav_context():
    """Makes the active session available to `_nav.html` on every gym page,
    not just the dashboard -- so the nav can show a "session running" dot
    and link straight to it from anywhere. Reuses `_get_active_session`,
    which is already idempotent (it only mutates state once, the first time
    it notices a session has gone stale past the timeout)."""
    return {'gym_active_session': _get_active_session()}


def _last_session_exercise(exercise_id, position=None):
    """The most recent SessionExercise (across any session) with at least one
    *completed* set for this exercise.

    If `position` is given, prefers a match where the exercise was performed
    in that same position within its session -- exercise order affects
    fatigue (the same exercise done 1st is fresher than done 3rd), so a
    suggestion should reflect what you actually did in that same slot
    before, not just the most recent time you did the exercise at all.
    Falls back to the most recent regardless of position if you've never
    done it in that position before.
    """
    base_query = (
        SessionExercise.query
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(SessionExercise.exercise_id == exercise_id, SessionExercise.sets.any(SessionSet.completed == True))
    )
    if position is not None:
        match = base_query.filter(SessionExercise.position == position).order_by(WorkoutSession.started_at.desc()).first()
        if match:
            return match
    return base_query.order_by(WorkoutSession.started_at.desc()).first()


def _last_performance(exercise_id, position=None):
    """Most recent completed set for this exercise (optionally position-
    matched, see _last_session_exercise), used to pre-fill the add-set form."""
    last_session_exercise = _last_session_exercise(exercise_id, position=position)
    if not last_session_exercise:
        return None
    completed_sets = [s for s in last_session_exercise.sets if s.completed]
    if not completed_sets:
        return None
    last_set = completed_sets[-1]
    return {'weight': last_set.weight, 'reps': last_set.reps}


def _last_full_performance(exercise_id, position=None):
    """All completed sets from the most recent (optionally position-matched)
    session that logged this exercise, in order -- used to pre-fill a new
    session's sets when starting from a template, mirroring what was
    actually done last time in that same slot."""
    last_session_exercise = _last_session_exercise(exercise_id, position=position)
    if not last_session_exercise:
        return []
    return [{'weight': s.weight, 'reps': s.reps} for s in last_session_exercise.sets if s.completed]


def _template_exercises_from_session(session_):
    """Build ordered, deduped TemplateExercise rows from a session's current
    exercises, carrying over each exercise's configured rest time so it's
    not lost when (re)saving a template.

    Mid-workout replacements (se.replaces_id is not None) are skipped here on
    purpose -- a substitute swapped in because the usual equipment wasn't
    available is a one-off for that session, not a change to the plan, so it
    must never get written into a template. Only the original slot can."""
    seen_exercise_ids = set()
    result = []
    position = 1
    for se in session_.exercises:
        if se.replaces_id is not None:
            continue
        if se.exercise_id in seen_exercise_ids:
            continue
        seen_exercise_ids.add(se.exercise_id)
        result.append(TemplateExercise(exercise_id=se.exercise_id, position=position, rest_seconds=se.rest_seconds))
        position += 1
    return result


def _cancel_pending_push(session_):
    """Cancel this session's still-pending push, if any. Must be called
    whenever resting_set_id/rest_ends_at is cleared or superseded -- an
    orphaned PendingPush row has no way to tell the notifier daemon that the
    set/exercise/session it was scheduled for is no longer current, and the
    daemon fires it regardless the moment it's due."""
    PendingPush.query.filter_by(session_id=session_.id, sent=False).delete()


def _schedule_rest(session_set):
    """Start (or restart) the rest timer for this set's session, based on the
    exercise's configured rest time. Called whenever a set is confirmed done."""
    session_exercise = session_set.session_exercise
    rest_seconds = session_exercise.rest_seconds
    if rest_seconds is None:
        rest_seconds = session_exercise.exercise.default_rest_seconds
    if not rest_seconds:
        return
    session_ = session_exercise.session
    rest_ends_at = dt.datetime.utcnow() + dt.timedelta(seconds=rest_seconds)
    session_.rest_ends_at = rest_ends_at
    session_.resting_set_id = session_set.id
    # Replace any still-pending push for this session rather than stacking
    # multiple -- a new completed set means a new (possibly shorter) rest period.
    _cancel_pending_push(session_)
    db.session.add(PendingPush(session_id=session_.id, fire_at=rest_ends_at))


def _epley_1rm(weight, reps):
    """Estimated one-rep max (Epley formula) -- there's no real single-rep
    test happening mid-workout, so this is the standard estimate used by
    every mainstream lifting tracker for the same reason."""
    return weight * (1 + reps / 30.0)


def _sessions_since_last_pr(exercise_id, position=None, exclude_session_id=None):
    """How many completed sessions in a row -- most recent first -- have
    passed without a new estimated-1RM PR for this exercise. e1RM (not raw
    weight) is the yardstick so a rep increase at the same weight still
    counts as progress. Returns None if there isn't enough history yet
    (fewer than 2 completed sessions) to say anything meaningful.

    Position-aware like _last_session_exercise: exercise order affects
    fatigue, so a stagnation read during an active workout should reflect
    history in that same slot, not muddy it with a fresher/more-fatigued
    performance from a different position. Falls back to all positions if
    there isn't enough position-matched history yet to judge from -- fetched
    in one query so the fallback doesn't cost a second DB round trip.
    """
    query = (
        SessionExercise.query
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(
            SessionExercise.exercise_id == exercise_id,
            SessionExercise.sets.any(SessionSet.completed == True),
            WorkoutSession.finished_at.isnot(None),
        )
    )
    if exclude_session_id is not None:
        query = query.filter(SessionExercise.session_id != exclude_session_id)
    all_session_exercises = query.order_by(WorkoutSession.started_at).all()

    session_exercises = [se for se in all_session_exercises if se.position == position] if position is not None else []
    if len(session_exercises) < 2:
        session_exercises = all_session_exercises
    if len(session_exercises) < 2:
        return None

    best_ever = None
    sessions_since = 0
    for se in session_exercises:
        session_best = max(_epley_1rm(s.weight, s.reps) for s in se.sets if s.completed)
        if best_ever is None or session_best > best_ever:
            best_ever = session_best
            sessions_since = 0
        else:
            sessions_since += 1
    return sessions_since


def _set_volume(exercise, s):
    """Volume for one logged set. Unilateral exercises log the per-side
    weight/reps, so both sides did this -- the real volume is double what's
    on the row. Centralized here so every volume computation stays in sync
    (weight and reps themselves are never doubled -- they're displayed as
    logged, per side)."""
    return s.weight * s.reps * (2 if exercise.is_unilateral else 1)


def _session_summary_data(session_):
    """Post-workout summary: per-exercise PRs (weight / estimated 1RM /
    single-session volume) and how this session's volume compares to your
    historical average -- per exercise, and for the workout as a whole."""
    exercise_rows = []
    total_volume = 0.0
    total_sets = 0

    for se in session_.exercises:
        # A replaced-away original isn't part of "what this workout looked
        # like" -- its slot is represented by the substitute that took over.
        # Skipping it here (unlike _exercise_progress_data, which still counts
        # its sets toward that exercise's own all-time history) keeps this
        # session's total_volume from being inflated by a one-off substitute
        # exercise the historical comparison below was never scoped to include.
        if se.replaced_by:
            continue
        completed_sets = [s for s in se.sets if s.completed]
        if not completed_sets:
            continue

        session_volume = sum(_set_volume(se.exercise, s) for s in completed_sets)
        session_best_weight = max(s.weight for s in completed_sets)
        session_best_e1rm = max(_epley_1rm(s.weight, s.reps) for s in completed_sets)
        total_volume += session_volume
        total_sets += len(completed_sets)

        past_session_exercises = (
            SessionExercise.query
            .filter(
                SessionExercise.exercise_id == se.exercise_id,
                SessionExercise.session_id != session_.id,
                SessionExercise.sets.any(SessionSet.completed == True),
            )
            .all()
        )

        past_volumes = []
        past_best_weight = None
        past_best_e1rm = None
        for past_se in past_session_exercises:
            past_completed = [s for s in past_se.sets if s.completed]
            if not past_completed:
                continue
            past_volumes.append(sum(_set_volume(se.exercise, s) for s in past_completed))
            for s in past_completed:
                if past_best_weight is None or s.weight > past_best_weight:
                    past_best_weight = s.weight
                e1rm = _epley_1rm(s.weight, s.reps)
                if past_best_e1rm is None or e1rm > past_best_e1rm:
                    past_best_e1rm = e1rm

        has_history = bool(past_volumes)
        avg_volume = (sum(past_volumes) / len(past_volumes)) if has_history else None
        best_volume_ever = max(past_volumes) if has_history else None

        exercise_rows.append({
            'name': se.exercise.name,
            'session_volume': round(session_volume, 1),
            'session_best_weight': session_best_weight,
            'session_best_e1rm': round(session_best_e1rm, 1),
            'has_history': has_history,
            'avg_volume': round(avg_volume, 1) if has_history else None,
            'volume_delta_pct': round((session_volume - avg_volume) / avg_volume * 100) if has_history and avg_volume else None,
            'is_weight_pr': has_history and session_best_weight > past_best_weight,
            'is_volume_pr': has_history and session_volume > best_volume_ever,
            'is_e1rm_pr': has_history and session_best_e1rm > past_best_e1rm,
        })

    # Whole-workout volume comparison only makes sense against past sessions
    # doing roughly the same exercises -- comparing against every finished
    # session ever (mixing e.g. a leg day into a push day's average) produces
    # a number that's technically correct but meaningless. Only template-
    # linked sessions have a reliable "same workout" cohort to compare
    # against; freeform sessions just skip this (per-exercise comparisons
    # below are still shown either way, since those ARE scoped correctly).
    past_total_volumes = []
    if session_.template_id:
        comparable_sessions = (
            WorkoutSession.query
            .options(joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise))
            .filter(
                WorkoutSession.id != session_.id,
                WorkoutSession.finished_at.isnot(None),
                WorkoutSession.template_id == session_.template_id,
            )
            .all()
        )
        for other in comparable_sessions:
            v = sum(
                _set_volume(se.exercise, s)
                for se in other.exercises for s in se.sets if s.completed
            )
            if v > 0:
                past_total_volumes.append(v)

    avg_total_volume = (sum(past_total_volumes) / len(past_total_volumes)) if past_total_volumes else None

    return {
        'exercises': exercise_rows,
        'total_volume': round(total_volume, 1),
        'total_sets': total_sets,
        'avg_total_volume': round(avg_total_volume, 1) if avg_total_volume else None,
        'total_volume_delta_pct': round((total_volume - avg_total_volume) / avg_total_volume * 100) if avg_total_volume else None,
        'pr_count': sum(1 for r in exercise_rows if r['is_weight_pr'] or r['is_volume_pr'] or r['is_e1rm_pr']),
    }


def _group_exercises_by_muscle(exercises):
    """Buckets exercises by MUSCLE_GROUPS (in that fixed vocabulary's
    order), with anything that doesn't match a current group -- no
    muscle_group set, or a legacy free-text value from before the enum
    existed -- collected into a trailing "Ohne Muskelgruppe" bucket instead
    of being silently dropped. `exercises` is expected pre-sorted by name
    (as gym_dashboard already queries it), so each bucket stays
    alphabetical."""
    grouped = {mg: [] for mg in MUSCLE_GROUPS}
    other = []
    for e in exercises:
        if e.muscle_group in grouped:
            grouped[e.muscle_group].append(e)
        else:
            other.append(e)
    result = [(mg, grouped[mg]) for mg in MUSCLE_GROUPS if grouped[mg]]
    if other:
        result.append(('Ohne Muskelgruppe', other))
    return result


@gym_bp.route('/gym', strict_slashes=False)
@login_required
def gym_dashboard():
    active_session = _get_active_session()
    exercises = Exercise.query.order_by(Exercise.name).all()
    templates = WorkoutTemplate.query.order_by(WorkoutTemplate.name).all()
    past_sessions = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None))
        .order_by(WorkoutSession.started_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        'gym/dashboard.html',
        active_session=active_session,
        exercises_by_group=_group_exercises_by_muscle(exercises),
        templates=templates,
        past_sessions=past_sessions,
        muscle_groups=MUSCLE_GROUPS,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
    )


@gym_bp.route('/gym/start', methods=['POST'])
@login_required
def gym_start():
    active_session = _get_active_session()
    if active_session:
        return redirect(url_for('gym.session_detail', session_id=active_session.id))

    template_id = request.form.get('template_id', type=int)
    name = request.form.get('name', '').strip() or None
    session_ = WorkoutSession(name=name, template_id=template_id or None)

    if template_id:
        template = db.session.get(WorkoutTemplate, template_id)
        if template:
            if not name:
                session_.name = f"{template.name} {dt.datetime.utcnow().strftime('%d.%m.%Y')}"
            for i, te in enumerate(template.exercises, start=1):
                session_exercise = SessionExercise(
                    exercise_id=te.exercise_id, position=i,
                    rest_seconds=te.rest_seconds if te.rest_seconds is not None else te.exercise.default_rest_seconds,
                )
                for j, prev_set in enumerate(_last_full_performance(te.exercise_id, position=i), start=1):
                    session_exercise.sets.append(SessionSet(
                        position=j, weight=prev_set['weight'], reps=prev_set['reps'], completed=False,
                    ))
                session_.exercises.append(session_exercise)

    db.session.add(session_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/session/<int:session_id>')
@login_required
def session_detail(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)
    # A replaced original is hidden from the active view, so its suggestion
    # would never be used -- skip computing it there. Visibility is derived
    # from replaces_id (already loaded on every row) rather than by touching
    # se.replaced_by, which would lazy-load a separate query per row.
    replaced_original_ids = {se.replaces_id for se in session_.exercises if se.replaces_id}
    visible_exercises = [
        se for se in session_.exercises
        if session_.finished_at or se.id not in replaced_original_ids
    ]
    suggestions = {se.id: _last_performance(se.exercise_id, position=se.position) for se in visible_exercises}
    stagnation_counts = {}
    if not session_.finished_at:  # only ever shown for an active workout -- skip the queries otherwise
        for se in visible_exercises:
            count = _sessions_since_last_pr(se.exercise_id, position=se.position, exclude_session_id=session_.id)
            if count is not None and count >= STAGNATION_THRESHOLD:
                stagnation_counts[se.id] = count
    exercises = Exercise.query.order_by(Exercise.name).all()
    return render_template(
        'gym/session_detail.html',
        session=session_,
        visible_exercises=visible_exercises,
        suggestions=suggestions,
        stagnation_counts=stagnation_counts,
        exercises=exercises,
        muscle_groups=MUSCLE_GROUPS,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
    )


@gym_bp.route('/gym/session/<int:session_id>/exercises/add', methods=['POST'])
@login_required
def gym_add_session_exercise(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)

    exercise_id = request.form.get('exercise_id', type=int)
    new_name = request.form.get('new_exercise_name', '').strip()
    if not exercise_id and new_name:
        exercise = Exercise.query.filter_by(name=new_name).first()
        if not exercise:
            exercise = Exercise(
                name=new_name,
                muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
                default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
            )
            db.session.add(exercise)
            db.session.flush()
        exercise_id = exercise.id

    if exercise_id:
        exercise = db.session.get(Exercise, exercise_id)
        next_position = max([se.position for se in session_.exercises], default=0) + 1
        db.session.add(SessionExercise(
            session_id=session_.id, exercise_id=exercise_id, position=next_position,
            rest_seconds=exercise.default_rest_seconds if exercise else None,
        ))
        db.session.commit()

    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/replace', methods=['POST'])
@login_required
def gym_replace_session_exercise(session_exercise_id):
    """Swap an exercise mid-workout for a same-category substitute (e.g. its
    usual equipment is taken) without touching history: the original row and
    its already-logged sets are left untouched (still counting toward its own
    exercise's history/PRs), a new SessionExercise is created for the
    replacement at the same position, and _template_exercises_from_session
    skips substitutes entirely so this never gets written into a template."""
    original = db.get_or_404(SessionExercise, session_exercise_id)
    session_id = original.session_id

    exercise_id = request.form.get('exercise_id', type=int)
    new_name = request.form.get('new_exercise_name', '').strip()
    if not exercise_id and new_name:
        exercise = Exercise.query.filter_by(name=new_name).first()
        if not exercise:
            exercise = Exercise(
                name=new_name,
                muscle_group=original.exercise.muscle_group,
                default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
            )
            db.session.add(exercise)
            db.session.flush()
        exercise_id = exercise.id

    if exercise_id and exercise_id != original.exercise_id and not original.replaced_by:
        db.session.add(SessionExercise(
            session_id=session_id, exercise_id=exercise_id, position=original.position,
            rest_seconds=original.rest_seconds, replaces_id=original.id,
        ))

    # Always commit -- even when the replacement itself didn't happen (e.g.
    # the guard above rejected it), a newly created Exercise from new_name
    # above must still be kept, or the user's typed name silently vanishes
    # with no feedback. A lost race against a concurrent replace of the same
    # original is caught here (the unique constraint on replaces_id rejects
    # the second insert) and treated as a no-op instead of a 500.
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/rest', methods=['POST'])
@login_required
def gym_update_session_exercise_rest(session_exercise_id):
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)
    session_exercise.rest_seconds = _to_int(request.form.get('rest_seconds', ''))
    session_id = session_exercise.session_id
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/sets/add', methods=['POST'])
@login_required
def gym_add_set(session_exercise_id):
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)

    weight = _to_float(request.form.get('weight', ''))
    reps = _to_int(request.form.get('reps', ''))
    if weight is not None and reps is not None:
        next_position = max([s.position for s in session_exercise.sets], default=0) + 1
        new_set = SessionSet(
            session_exercise_id=session_exercise.id,
            position=next_position,
            weight=weight,
            reps=reps,
            completed=True,  # logged live via this form, so it's inherently just-performed
        )
        db.session.add(new_set)
        db.session.flush()
        _schedule_rest(new_set)
        db.session.commit()

    return redirect(url_for('gym.session_detail', session_id=session_exercise.session_id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/delete', methods=['POST'])
@login_required
def gym_delete_session_exercise(session_exercise_id):
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)
    session_id = session_exercise.session_id
    # If the currently-resting set belongs to this exercise, clear the
    # reference first -- otherwise deleting it (cascades to its sets) would
    # violate the WorkoutSession.resting_set_id foreign key.
    if session_exercise.session.resting_set_id in [s.id for s in session_exercise.sets]:
        session_exercise.session.resting_set_id = None
        session_exercise.session.rest_ends_at = None
        _cancel_pending_push(session_exercise.session)
    db.session.delete(session_exercise)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/set/<int:set_id>/delete', methods=['POST'])
@login_required
def gym_delete_set(set_id):
    set_ = db.get_or_404(SessionSet, set_id)
    session_ = set_.session_exercise.session
    session_id = session_.id
    if session_.resting_set_id == set_.id:
        session_.resting_set_id = None
        session_.rest_ends_at = None
        _cancel_pending_push(session_)
    db.session.delete(set_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/set/<int:set_id>/toggle_complete', methods=['POST'])
@login_required
def gym_toggle_set_complete(set_id):
    """Single action for a set row: save whatever weight/reps are currently
    in the form, and toggle done/not-done -- these were two separate buttons
    before, which was redundant since confirming a set's numbers and marking
    it done are the same real-world action."""
    set_ = db.get_or_404(SessionSet, set_id)
    session_ = set_.session_exercise.session

    weight = _to_float(request.form.get('weight', ''))
    reps = _to_int(request.form.get('reps', ''))
    if weight is not None:
        set_.weight = weight
    if reps is not None:
        set_.reps = reps

    set_.completed = not set_.completed
    if set_.completed:
        # just confirmed done -- this is the moment to start the rest timer
        _schedule_rest(set_)
    elif session_.resting_set_id == set_.id:
        # un-marking the set that's currently resting -- a countdown attached
        # to a set that's no longer "done" doesn't make sense, cancel it
        session_.resting_set_id = None
        session_.rest_ends_at = None
        _cancel_pending_push(session_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/session/<int:session_id>/exercises/reorder', methods=['POST'])
@login_required
def gym_reorder_session_exercises(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)
    data = request.get_json(silent=True) or {}
    order = data.get('order') or []
    session_exercises_by_id = {se.id: se for se in session_.exercises}
    position = 1
    for raw_id in order:
        se = session_exercises_by_id.get(_to_int(raw_id))
        if se:
            old_position = se.position
            se.position = position
            # A substitute shares its slot with the original it replaced (which
            # is hidden from `order` -- it's not rendered while the session is
            # active) -- keep the hidden original's position in sync so the two
            # don't drift apart / collide with an unrelated exercise's position.
            if se.replaces_id and se.replaces:
                se.replaces.position = position
            # Its pending sets (if any) were pre-filled from history matched to
            # the OLD position -- e.g. at gym_start, or a previous reorder --
            # which is now stale for the new slot. Re-derive them for the new
            # position, but only when nothing has been logged for this exercise
            # yet this session: one completed set means the lifter has already
            # started on it, and overwriting sets at that point would destroy
            # real in-progress data rather than a stale suggestion.
            if position != old_position and not any(s.completed for s in se.sets):
                se.sets.clear()
                se.sets.extend(
                    SessionSet(position=j, weight=prev_set['weight'], reps=prev_set['reps'], completed=False)
                    for j, prev_set in enumerate(_last_full_performance(se.exercise_id, position=position), start=1)
                )
            position += 1
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/session/<int:session_id>/finish', methods=['POST'])
@login_required
def gym_finish_session(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)
    session_.finished_at = dt.datetime.utcnow()
    session_.rest_ends_at = None
    session_.resting_set_id = None
    # Finishing early (before a running rest timer naturally elapses) must
    # cancel its still-pending push -- otherwise the notifier daemon fires it
    # later for a workout that's already over.
    _cancel_pending_push(session_)
    db.session.commit()
    return redirect(url_for('gym.gym_session_summary', session_id=session_.id, just_finished=1))


@gym_bp.route('/gym/session/<int:session_id>/summary')
@login_required
def gym_session_summary(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)
    data = _session_summary_data(session_)
    return render_template('gym/session_summary.html', session=session_, **data)


@gym_bp.route('/gym/session/<int:session_id>/delete', methods=['POST'])
@login_required
def gym_delete_session(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)
    if session_.finished_at is not None:  # never delete the active workout by accident
        # Null the self-referencing rest-timer FK first -- deleting a session
        # whose resting_set_id still points at one of its own (about to be
        # cascade-deleted) sets would otherwise violate the FK constraint.
        session_.resting_set_id = None
        db.session.commit()
        db.session.delete(session_)
        db.session.commit()
    return redirect(url_for('gym.gym_dashboard'))


@gym_bp.route('/gym/session/<int:session_id>/update_template', methods=['POST'])
@login_required
def gym_update_template(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)
    if session_.template_id:
        template = db.session.get(WorkoutTemplate, session_.template_id)
        if template:
            template.exercises.clear()
            db.session.flush()
            template.exercises.extend(_template_exercises_from_session(session_))
            db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/session/<int:session_id>/save_as_template', methods=['POST'])
@login_required
def gym_save_as_template(session_id):
    session_ = db.get_or_404(WorkoutSession, session_id)
    template_name = request.form.get('template_name', '').strip()
    if template_name:
        template = WorkoutTemplate(name=template_name)
        template.exercises.extend(_template_exercises_from_session(session_))
        db.session.add(template)
        db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def gym_delete_template(template_id):
    template = db.get_or_404(WorkoutTemplate, template_id)
    # Null out references instead of cascading -- deleting a template must not
    # delete the workout history of sessions that were started from it.
    WorkoutSession.query.filter_by(template_id=template.id).update({'template_id': None})
    db.session.delete(template)
    db.session.commit()
    return redirect(url_for('gym.gym_dashboard'))


def _exercise_progress_data(exercise, position=None):
    """Shared by the full exercise-history page and the in-workout progress
    modal. Only counts *completed* sets -- a pending/unconfirmed set (e.g.
    freshly copied from a template) hasn't actually been performed yet and
    shouldn't count toward PRs or history.

    Exercise order affects performance (the same exercise done 1st is
    fresher than done 3rd), so mixing every position together can show
    swings in the chart/PRs that aren't really progress or regression --
    just a different slot that day. If `position` is given, only sessions
    where this exercise was done in that exact position are included, for
    an apples-to-apples view. `available_positions` is always computed from
    the *unfiltered* data so the caller can build a filter control.
    """
    all_session_exercises = (
        SessionExercise.query
        .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
        .filter(SessionExercise.exercise_id == exercise.id, SessionExercise.sets.any(SessionSet.completed == True))
        .order_by(WorkoutSession.started_at)
        .all()
    )
    available_positions = sorted({se.position for se in all_session_exercises})

    session_exercises = all_session_exercises
    if position is not None:
        session_exercises = [se for se in all_session_exercises if se.position == position]

    rows = []
    pr_max_weight = None   # {'weight', 'reps', 'date'}
    pr_max_volume = None   # {'weight', 'reps', 'volume', 'date'}
    for se in session_exercises:
        completed_sets = [s for s in se.sets if s.completed]
        if not completed_sets:
            continue
        best_weight = max(s.weight for s in completed_sets)
        worst_weight = min(s.weight for s in completed_sets)
        volume = sum(_set_volume(exercise, s) for s in completed_sets)
        sets_display = ', '.join(f'{s.weight}kg×{s.reps}' for s in completed_sets)
        rows.append({
            'session': se.session, 'sets': completed_sets, 'best_weight': best_weight,
            'worst_weight': worst_weight, 'volume': volume, 'sets_display': sets_display,
            'position': se.position,
        })

        for s in completed_sets:
            if pr_max_weight is None or s.weight > pr_max_weight['weight']:
                pr_max_weight = {'weight': s.weight, 'reps': s.reps, 'date': se.session.started_at}
            set_volume = _set_volume(exercise, s)
            if pr_max_volume is None or set_volume > pr_max_volume['volume']:
                pr_max_volume = {'weight': s.weight, 'reps': s.reps, 'volume': set_volume, 'date': se.session.started_at}

    rows.reverse()  # most recent first for the table
    chart_rows = list(reversed(rows))
    return {
        'rows': rows,
        'pr_max_weight': pr_max_weight,
        'pr_max_volume': pr_max_volume,
        'chart_labels': [r['session'].started_at.strftime('%d.%m.%Y') for r in chart_rows],
        'chart_weights': [r['best_weight'] for r in chart_rows],
        'chart_min_weights': [r['worst_weight'] for r in chart_rows],
        'chart_volumes': [r['volume'] for r in chart_rows],
        'available_positions': available_positions,
        'selected_position': position,
    }


@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    position = request.args.get('position', type=int)
    data = _exercise_progress_data(exercise, position=position)
    return render_template('gym/exercise_detail.html', exercise=exercise, muscle_groups=MUSCLE_GROUPS, **data)


@gym_bp.route('/gym/exercises/<int:exercise_id>/progress.json')
@login_required
def gym_exercise_progress_json(exercise_id):
    """Backs the in-workout quick-glance modal. Scoped to a position when
    one is given (same slot in the workout order = comparable fatigue
    state), but unlike the full exercise page's explicit filter, this falls
    back to all-time data if that exact slot has no history yet -- the
    modal should always show *something* useful rather than an empty state
    just because you haven't done this exercise in this position before."""
    exercise = db.get_or_404(Exercise, exercise_id)
    position = request.args.get('position', type=int)
    data = _exercise_progress_data(exercise, position=position)
    if position is not None and not data['rows']:
        data = _exercise_progress_data(exercise)
        position = None

    def fmt_pr(pr):
        if not pr:
            return None
        return {'weight': pr['weight'], 'reps': pr['reps'], 'date': pr['date'].strftime('%d.%m.%Y')}

    def fmt_pr_volume(pr):
        if not pr:
            return None
        return {'weight': pr['weight'], 'reps': pr['reps'], 'volume': pr['volume'], 'date': pr['date'].strftime('%d.%m.%Y')}

    return jsonify({
        'exercise_id': exercise.id,
        'name': exercise.name,
        'is_unilateral': exercise.is_unilateral,
        'position': position,
        'pr_max_weight': fmt_pr(data['pr_max_weight']),
        'pr_max_volume': fmt_pr_volume(data['pr_max_volume']),
        'chart_labels': data['chart_labels'],
        'chart_weights': data['chart_weights'],
        'chart_min_weights': data['chart_min_weights'],
        'chart_volumes': data['chart_volumes'],
    })


@gym_bp.route('/gym/exercises/add', methods=['POST'])
@login_required
def gym_add_exercise():
    name = request.form.get('name', '').strip()
    if name and not Exercise.query.filter_by(name=name).first():
        db.session.add(Exercise(
            name=name,
            muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
            default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
            is_unilateral=request.form.get('is_unilateral') == 'on',
        ))
        db.session.commit()
    return redirect(url_for('gym.gym_dashboard'))


@gym_bp.route('/gym/exercises/<int:exercise_id>/update', methods=['POST'])
@login_required
def gym_update_exercise(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    new_name = request.form.get('name', '').strip()
    name_taken = False
    if new_name and new_name != exercise.name:
        if Exercise.query.filter_by(name=new_name).first():
            name_taken = True  # surfaced to the user below instead of silently skipping the rename
        else:
            # Remember the old name so anything still referencing it (e.g.
            # historical data, or a rename made by mistake) can still
            # resolve to this exercise instead of creating a duplicate.
            exercise.previous_name = exercise.name
            exercise.name = new_name
    exercise.muscle_group = _clean_muscle_group(request.form.get('muscle_group', ''), current=exercise.muscle_group)
    exercise.default_rest_seconds = _to_int(request.form.get('default_rest_seconds', ''))
    exercise.is_unilateral = request.form.get('is_unilateral') == 'on'
    db.session.commit()
    return redirect(url_for(
        'gym.exercise_detail', exercise_id=exercise.id, name_taken=1 if name_taken else None,
    ))


@gym_bp.route('/gym/exercises/<int:exercise_id>/delete', methods=['POST'])
@login_required
def gym_delete_exercise(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    if not exercise.session_exercises and not exercise.template_exercises:
        db.session.delete(exercise)
        db.session.commit()
    return redirect(url_for('gym.gym_dashboard'))


@gym_bp.route('/gym/push/subscribe', methods=['POST'])
@login_required
def gym_push_subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys') or {}
    p256dh = keys.get('p256dh')
    auth_key = keys.get('auth')
    if not endpoint or not p256dh or not auth_key:
        return jsonify({'status': 'error', 'message': 'invalid subscription'}), 400

    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub:
        sub.p256dh_key = p256dh
        sub.auth_key = auth_key
    else:
        db.session.add(PushSubscription(endpoint=endpoint, p256dh_key=p256dh, auth_key=auth_key))
    db.session.commit()
    return jsonify({'status': 'ok'})


@gym_bp.route('/gym/push/unsubscribe', methods=['POST'])
@login_required
def gym_push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint).delete()
        db.session.commit()
    return jsonify({'status': 'ok'})
