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
from features.gym import stats

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

# stats.exercise_state()'s return value -> (chip CSS modifier, display label),
# spec 5.6's table. A state of None means "no chip" and has no entry here --
# callers must check before indexing.
EXERCISE_STATE_CHIP = {
    'neu': ('neu', 'Neu'),
    'rekord': ('record', 'Rekord'),
    'stagniert': ('stall', 'Stagniert'),
    'steigend': ('up', 'Steigend'),
}


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
        position=session_exercise.position,
        session_id=session_exercise.session_id,
        started_at=session_exercise.session.started_at,
        sets=completed_sets,
    )


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


@gym_bp.route('/gym', strict_slashes=False)
@login_required
def gym_heute():
    now = dt.datetime.utcnow()
    active_session = _get_active_session()

    # Eager-loaded: each routine panel shows its own exercise list, and
    # walking .exercises / .exercise per template without this would be an
    # N+1 (one query per template, one more per template-exercise) -- exactly
    # the pattern this page exists to avoid (see load_performed() below).
    templates = (
        WorkoutTemplate.query
        .options(joinedload(WorkoutTemplate.exercises).joinedload(TemplateExercise.exercise))
        .order_by(WorkoutTemplate.name)
        .all()
    )
    routine_sessions = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None), WorkoutSession.template_id.isnot(None))
        .all()
    )
    recent_sessions = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None))
        .order_by(WorkoutSession.started_at.desc())
        .limit(5)
        .all()
    )
    catalogue_groups = {e.muscle_group or stats.NO_GROUP_LABEL for e in Exercise.query.all()}

    # The one bulk load this whole page runs on -- every completed set ever
    # logged, across every exercise. Every stats.py call below is fed from
    # this single result; must not be called again no matter how many of
    # them need it (see load_performed()'s own docstring).
    performed = load_performed()
    rows_by_exercise = {}
    session_started_at = {}
    for row in performed:
        rows_by_exercise.setdefault(row.exercise_id, []).append(row)
        session_started_at[row.session_id] = row.started_at

    return render_template(
        'gym/heute.html',
        now=now,
        active_session=active_session,
        consistency=stats.consistency(list(session_started_at.values()), now),
        routines=stats.routine_memory(templates, routine_sessions, now),
        recent_sessions=recent_sessions,
        stalls=stats.stall_report(rows_by_exercise),
        balance=stats.muscle_group_volume(performed, catalogue_groups, now),
        tonnage=stats.weekly_tonnage(performed, now),
        templates=templates,
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

    if session_.finished_at:
        # The finished workout is one page now (spec 6.5): build the report
        # and hand off to session_finished.html instead of session_detail.html.
        current = performed_from_session(session_)
        history = [
            row for row in load_performed(exercise_ids=[row.exercise_id for row in current])
            if row.session_id != session_.id
        ]
        comparable = []
        if session_.template_id:
            cohort = (
                WorkoutSession.query
                .filter(
                    WorkoutSession.id != session_.id,
                    WorkoutSession.finished_at.isnot(None),
                    WorkoutSession.template_id == session_.template_id,
                )
                .all()
            )
            cohort_ids = {other.id for other in cohort}
            volumes = {}
            for row in load_performed():
                if row.session_id in cohort_ids:
                    volumes[row.session_id] = volumes.get(row.session_id, 0.0) + stats.row_volume(row)
            comparable = [volume for volume in volumes.values() if volume > 0]
        data = stats.session_report(current, history, comparable_session_volumes=comparable)
        # session_report()'s entries carry only plain (weight, reps) tuples --
        # PerformedExercise is deliberately ORM-free (stats.py has zero
        # SQLAlchemy dependency, see its module docstring). The "correct a
        # past set" affordance needs a real SessionSet.id to POST to
        # gym_update_set, so attach the real rows here instead. `current`
        # (and therefore data['exercises'], built from it 1:1 in order) came
        # from performed_from_session()'s filtered/ordered walk of
        # session_.exercises -- skip a replaced-away original, skip an
        # exercise with no completed sets. Re-deriving that exact filter and
        # zipping lines each entry back up with its real SessionExercise.
        reported_session_exercises = [
            se for se in session_.exercises
            if not se.replaced_by and any(s.completed for s in se.sets)
        ]
        for entry, se in zip(data['exercises'], reported_session_exercises):
            entry['set_rows'] = [s for s in se.sets if s.completed]
        return render_template('gym/session_finished.html', session=session_, **data)

    # A replaced original is hidden from the active view, so its suggestion
    # would never be used -- skip computing it there. Visibility is derived
    # from replaces_id (already loaded on every row) rather than by touching
    # se.replaced_by, which would lazy-load a separate query per row.
    replaced_original_ids = {se.replaces_id for se in session_.exercises if se.replaces_id}
    visible_exercises = [se for se in session_.exercises if se.id not in replaced_original_ids]
    suggestions = {se.id: _last_performance(se.exercise_id, position=se.position) for se in visible_exercises}
    history = load_performed(exercise_ids=[se.exercise_id for se in visible_exercises])
    by_exercise = {}
    for row in history:
        if row.session_id != session_.id:
            by_exercise.setdefault(row.exercise_id, []).append(row)
    stagnation_counts = {}
    for se in visible_exercises:
        count = stats.sessions_since_pr(by_exercise.get(se.exercise_id, []), position=se.position)
        if count is not None and count >= stats.STAGNATION_THRESHOLD:
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


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/skip', methods=['POST'])
@login_required
def gym_toggle_skip_session_exercise(session_exercise_id):
    """Skip: mark this exercise as intentionally not done this session,
    without deleting it -- unlike gym_delete_session_exercise, the row stays
    in session_.exercises, so _template_exercises_from_session still picks
    it up if this session is later saved/updated as a template (no change
    needed there: it already includes every non-substitute row). Toggling
    back off (undo) re-derives pending sets the same way a fresh template
    start does, but only if nothing is left over from before the skip."""
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)
    session_ = session_exercise.session
    if session_.finished_at:
        return redirect(url_for('gym.session_detail', session_id=session_.id))

    session_exercise.skipped = not session_exercise.skipped
    if session_exercise.skipped:
        # Drop only the not-yet-confirmed sets -- anything already completed
        # (e.g. 2 of 4 sets done, then the lifter decides to skip the rest)
        # stays untouched, still counting toward that exercise's history.
        for s in list(session_exercise.sets):
            if not s.completed:
                db.session.delete(s)
    elif not session_exercise.sets:
        for j, prev_set in enumerate(_last_full_performance(session_exercise.exercise_id, position=session_exercise.position), start=1):
            session_exercise.sets.append(SessionSet(position=j, weight=prev_set['weight'], reps=prev_set['reps'], completed=False))

    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


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


@gym_bp.route('/gym/set/<int:set_id>/update', methods=['POST'])
@login_required
def gym_update_set(set_id):
    """Edit-history: correct a typo'd weight/reps on a set from a finished
    session. Deliberately narrow -- unlike gym_toggle_set_complete, this
    never touches `completed`, and works regardless of session.finished_at
    (that route's edit form is only shown for active sessions; this one's
    form is the quiet "Sätze korrigieren" disclosure in
    session_finished.html, one per exercise, shown only for finished
    sessions)."""
    set_ = db.get_or_404(SessionSet, set_id)
    weight = _to_float(request.form.get('weight', ''))
    reps = _to_int(request.form.get('reps', ''))
    if weight is not None:
        set_.weight = weight
    if reps is not None:
        set_.reps = reps
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=set_.session_exercise.session_id))


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
    return redirect(url_for('gym.session_detail', session_id=session_.id, just_finished=1))


@gym_bp.route('/gym/session/<int:session_id>/summary')
@login_required
def gym_session_summary(session_id):
    # Kept as a redirect: a finished workout is one page now, and this URL is
    # in browser history and bookmarks.
    return redirect(url_for('gym.session_detail', session_id=session_id,
                            **request.args.to_dict()))


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
    return redirect(url_for('gym.gym_verlauf'))


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


@gym_bp.route('/gym/templates/<int:template_id>/rename', methods=['POST'])
@login_required
def gym_rename_template(template_id):
    """Heute's small per-routine edit affordance. WorkoutTemplate.name carries
    no unique constraint (unlike Exercise.name), so unlike gym_update_exercise
    there is no collision case to reject -- any non-empty name is accepted."""
    template = db.get_or_404(WorkoutTemplate, template_id)
    new_name = request.form.get('name', '').strip()
    if new_name:
        template.name = new_name
        db.session.commit()
    return redirect(url_for('gym.gym_heute'))


@gym_bp.route('/gym/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def gym_delete_template(template_id):
    template = db.get_or_404(WorkoutTemplate, template_id)
    # Null out references instead of cascading -- deleting a template must not
    # delete the workout history of sessions that were started from it.
    WorkoutSession.query.filter_by(template_id=template.id).update({'template_id': None})
    db.session.delete(template)
    db.session.commit()
    return redirect(url_for('gym.gym_heute'))


@gym_bp.route('/gym/verlauf')
@login_required
def gym_verlauf():
    """Every finished workout, newest first, with its own total volume and
    record count -- spec 6.6, one of the three real nav destinations."""
    # Eager-loaded for the exercise-list column: WorkoutSession.exercises and
    # SessionExercise.exercise are lazy relationships (models.py). This page
    # can list every finished session ever logged, and touching either per
    # row without this would be exactly the N+1 the bulk-loading discipline
    # below exists to avoid, just on a different relationship than
    # load_performed().
    sessions = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None))
        .options(joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise))
        .order_by(WorkoutSession.started_at.desc())
        .all()
    )

    # Replaced-away originals must not contribute to their own session's
    # volume/record totals below -- the same exclusion performed_from_session()
    # already applies for session_report()/the detail page: the substitute
    # took over that slot, and counting both would inflate the session's
    # totals with an exercise the historical comparison was never scoped to.
    # `sessions` above already eager-loads every finished session's
    # .exercises (for the exercise-list column) -- reused here for zero extra
    # queries, reading replaces_id (a plain, already-loaded column) rather
    # than the replaced_by backref, which would lazy-load once per row (see
    # session_detail's identical replaced_original_ids, same reasoning).
    replaced_away_ids = {
        se.replaces_id
        for s in sessions for se in s.exercises
        if se.replaces_id is not None
    }

    # The one bulk load this whole page runs on -- every completed set ever
    # logged, across every exercise, in a single query (see load_performed()'s
    # own docstring). Every session's volume and record count below is
    # derived from this one result set in Python; must not be recomputed per
    # session (spec 5.4, same discipline as gym_heute/gym_uebungen).
    performed = load_performed(exclude_session_exercise_ids=replaced_away_ids)

    volume_by_session = {}
    for row in performed:
        volume_by_session[row.session_id] = volume_by_session.get(row.session_id, 0.0) + stats.row_volume(row)

    # Same "beats every OTHER session, regardless of when it happened"
    # semantics stats.session_report's own is_weight_pr/is_e1rm_pr/
    # is_volume_pr use -- computed for every session in this one pass so a
    # session's count here always agrees with what its own detail page
    # (session_report) shows, instead of the strictly weaker "beats only the
    # sessions before it" a chronological-only comparison would give.
    records_by_session = stats.session_record_counts(performed)

    history = [
        {
            'session': s,
            'volume': round(volume_by_session.get(s.id, 0.0), 1),
            'record_count': records_by_session.get(s.id, 0),
        }
        for s in sessions
    ]

    return render_template('gym/verlauf.html', history=history)


@gym_bp.route('/gym/export')
@login_required
def gym_export():
    """Downloadable JSON of finished workout history in a date range, for
    feeding into an external analysis tool later. Full detail (every set,
    not just aggregates) so nothing useful is thrown away up front. Both
    original and substitute SessionExercise rows are exported (mirroring
    what a finished session's own detail view already shows -- see
    session_detail's visible_exercises computation), each carrying
    replaces/replaced_by exercise names so a swap is fully traceable."""
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    try:
        from_date = dt.datetime.strptime(date_from, '%Y-%m-%d') if date_from else dt.datetime(1970, 1, 1)
    except ValueError:
        from_date = dt.datetime(1970, 1, 1)
    try:
        to_date = dt.datetime.strptime(date_to, '%Y-%m-%d') if date_to else dt.datetime.utcnow()
    except ValueError:
        to_date = dt.datetime.utcnow()
    to_date_exclusive = to_date + dt.timedelta(days=1)  # 'to' is inclusive of that whole calendar day

    sessions = (
        WorkoutSession.query
        .filter(
            WorkoutSession.finished_at.isnot(None),
            WorkoutSession.started_at >= from_date,
            WorkoutSession.started_at < to_date_exclusive,
        )
        .order_by(WorkoutSession.started_at.asc())
        .all()
    )

    payload = {
        'exported_at': dt.datetime.utcnow().isoformat() + 'Z',
        'range': {'from': date_from or None, 'to': date_to or None},
        'sessions': [
            {
                'id': s.id,
                'name': s.name,
                'template_name': s.template.name if s.template else None,
                'started_at': s.started_at.isoformat() + 'Z',
                'finished_at': s.finished_at.isoformat() + 'Z',
                'exercises': [
                    {
                        'exercise_name': se.exercise.name,
                        'muscle_group': se.exercise.muscle_group,
                        'position': se.position,
                        'rest_seconds': se.rest_seconds,
                        'skipped': se.skipped,
                        'replaces': se.replaces.exercise.name if se.replaces else None,
                        'replaced_by': se.replaced_by.exercise.name if se.replaced_by else None,
                        'sets': [
                            {'position': st.position, 'weight': st.weight, 'reps': st.reps, 'completed': st.completed}
                            for st in se.sets
                        ],
                    }
                    for se in s.exercises
                ],
            }
            for s in sessions
        ],
    }

    resp = jsonify(payload)
    filename = f"gym-export-{date_from or 'all'}_{date_to or 'now'}.json"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@gym_bp.route('/gym/uebungen')
@login_required
def gym_uebungen():
    exercises = Exercise.query.order_by(Exercise.name).all()

    # Delete-eligibility depends on ANY session_exercises/template_exercises
    # row existing, not just ones with a completed set -- so it can't reuse
    # rows_by_exercise below. Exercise.session_exercises/.template_exercises
    # are lazy relationships (models.py) that would issue one query per
    # exercise if touched per-row here; two bulk id sets instead, each
    # gathered once regardless of catalogue size.
    exercise_ids_with_sessions = {
        row.exercise_id for row in db.session.query(SessionExercise.exercise_id).distinct()
    }
    exercise_ids_with_templates = {
        row.exercise_id for row in db.session.query(TemplateExercise.exercise_id).distinct()
    }

    # The one bulk load this whole page runs on -- every completed set ever
    # logged, across the whole catalogue. Every exercise's state/last-done/
    # best-weight/best-e1RM below is computed from this single result,
    # grouped by exercise_id in Python; must not be queried again per
    # exercise (see load_performed()'s own docstring, spec 5.4).
    performed = load_performed()
    rows_by_exercise = {}
    for row in performed:
        rows_by_exercise.setdefault(row.exercise_id, []).append(row)

    entries_by_id = {}
    for exercise in exercises:
        rows = rows_by_exercise.get(exercise.id, [])
        # dominant_position() requires at least one row -- a brand new
        # exercise (no rows) has no position to speak of, and exercise_state
        # returns 'neu' from its own empty-rows check before position is
        # ever consulted, so None is a safe stand-in here.
        position = stats.dominant_position(rows) if rows else None
        best_e1rm = max((stats.best_e1rm(row) for row in rows), default=None)
        state = stats.exercise_state(rows, position=position)
        chip_class, chip_label = EXERCISE_STATE_CHIP.get(state, (None, None))
        entries_by_id[exercise.id] = {
            'exercise': exercise,
            'state': state,
            'chip_class': chip_class,
            'chip_label': chip_label,
            'last_done': max((row.started_at for row in rows), default=None),
            'best_weight': max((stats.best_weight(row) for row in rows), default=None),
            'best_e1rm': round(best_e1rm, 1) if best_e1rm is not None else None,
            'sessions_since_pr': stats.sessions_since_pr(rows, position=position) if rows else None,
            'can_delete': (
                exercise.id not in exercise_ids_with_sessions
                and exercise.id not in exercise_ids_with_templates
            ),
        }

    # Default/grouped view (spec 6.2's "nach Muskelgruppe"). The two flat
    # sorts ("am längsten ohne PR", "zuletzt gemacht") are client-side
    # re-orderings of these SAME rows in uebungen.html's own script, not a
    # second server round trip -- every exercise's data attributes carry
    # what that script needs (see the template).
    grouped = [
        (group_name, [entries_by_id[e.id] for e in group_exercises])
        for group_name, group_exercises in stats.group_exercises_by_muscle(exercises, MUSCLE_GROUPS)
    ]

    return render_template(
        'gym/uebungen.html',
        grouped=grouped,
        muscle_groups=MUSCLE_GROUPS,
    )


def _exercise_progress_shim(rows, position):
    """Temporary shim: the old templates predate stats.py's key names. Deleted
    when exercise_detail.html and session_finished.html are rebuilt.

    stats.exercise_progress() doesn't carry two things this old page's
    template still needs: the heaviest single SET by volume (a different
    number from stats.py's e1RM-based pr_e1rm, which the new pages use
    instead), and each row's lowest set weight (for the chart's low end).
    It also deliberately reports pr_weight/pr_e1rm across every position
    regardless of the position filter -- fine for the pages Task 10/12
    build, but this old page's PR cards were always scoped to whatever
    position is currently filtered. All of that is cheap to rebuild here
    from the same rows stats.exercise_progress() was given.
    """
    data = stats.exercise_progress(rows, position=position)
    shown = [row for row in rows if row.position == position] if position is not None else rows

    pr_max_weight = None   # {'weight', 'reps', 'date'}
    pr_max_volume = None   # {'weight', 'reps', 'volume', 'date'}
    for row in shown:
        for weight, reps in row.sets:
            if pr_max_weight is None or weight > pr_max_weight['weight']:
                pr_max_weight = {'weight': weight, 'reps': reps, 'date': row.started_at}
            volume = stats.set_volume(weight, reps, row.is_unilateral)
            if pr_max_volume is None or volume > pr_max_volume['volume']:
                pr_max_volume = {'weight': weight, 'reps': reps, 'volume': volume, 'date': row.started_at}

    return {
        'rows': [
            {
                'session': {'started_at': row.started_at},
                'position': row.position,
                'sets_display': ', '.join('{}kg×{}'.format(weight, reps) for weight, reps in row.sets),
                'volume': stats.row_volume(row),
            }
            for row in reversed(shown)
        ],
        'pr_max_weight': pr_max_weight,
        'pr_max_volume': pr_max_volume,
        'chart_labels': [row.started_at.strftime('%d.%m.%Y') for row in shown],
        'chart_weights': [stats.best_weight(row) for row in shown],
        'chart_min_weights': [min(weight for weight, _ in row.sets) for row in shown],
        'chart_volumes': [stats.row_volume(row) for row in shown],
        'available_positions': data['available_positions'],
        'selected_position': data['selected_position'],
    }


@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    position = request.args.get('position', type=int)
    rows = load_performed(exercise_ids=[exercise.id], include_active=True)
    data = _exercise_progress_shim(rows, position)
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
    rows = load_performed(exercise_ids=[exercise.id], include_active=True)
    progress = stats.exercise_progress(rows, position=position)
    if position is not None and not progress['table']:
        position = None
    data = _exercise_progress_shim(rows, position)

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
    return redirect(url_for('gym.gym_uebungen'))


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
    return redirect(url_for('gym.gym_uebungen'))


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
