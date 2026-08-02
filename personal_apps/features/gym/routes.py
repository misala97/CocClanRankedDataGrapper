import datetime as dt
import os

from flask import Blueprint, current_app, jsonify, render_template, request, redirect, send_from_directory, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, load_only

from extensions import db
from models import (
    Exercise, WorkoutTemplate, TemplateExercise, WorkoutSession, SessionExercise, SessionSet,
    PushSubscription, PendingPush, STALE_SESSION_TIMEOUT, MUSCLE_GROUPS,
)
from auth import login_required
from features.gym import stats
from features.gym.push import is_valid_push_endpoint
from . import analytics

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

# The UI is German regardless of the server's locale, so month names are stated
# rather than taken from strftime('%B') -- which follows LC_TIME and would give
# English on this machine and German on the VPS, or vice versa.
# analytics.py speaks in keys and indexes, not in UI language: dayparts come
# back as 'morning'/'evening' and weekdays as 0-6. Naming them is presentation,
# so it happens here rather than in the analysis.
DAYPART_NAMES = {'morning': 'Vormittags', 'evening': 'Abends'}
WEEKDAY_NAMES = ('Montag', 'Dienstag', 'Mittwoch', 'Donnerstag',
                 'Freitag', 'Samstag', 'Sonntag')

MONTH_NAMES = (
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
)

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


def _to_increment(value):
    """A weight increment as typed, or None.

    Comma-tolerant: `type=number` normalises to a dot, but the field degrades
    to text without JS and a German keyboard produces `2,5`. Blank,
    unparseable and non-positive all store NULL, which
    stats.resolve_increment() reads as "use the default" -- so clearing the
    field is the way to put an exercise back on 2.5 kg.
    """
    parsed = _to_float(str(value).replace(',', '.').strip())
    return parsed if parsed and parsed > 0 else None


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


@gym_bp.app_template_filter('local')
def _local_filter(moment):
    """Naive UTC -> naive local, for anything a person reads as a date or time.

    Timestamps are stored naive-UTC and stay that way. Two hours of every CEST
    day fall on the previous UTC date, so an unconverted `strftime` filed a
    00:30 workout under yesterday -- next to a "vor 0 Tagen" that had already
    been corrected to local. Every human-readable render goes through here.

    NOT for durations. The elapsed clock's `data-started` stays UTC on purpose:
    GymClock appends 'Z' and subtracts from Date.now(), which is a difference
    between two instants and is the same number in any zone. Localising it
    would shift the clock by the offset.
    """
    return stats.to_local(moment)


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


def _seeded_sets(session_, exercise_id, position):
    """Pending sets pre-filled from history for `exercise_id` in `position`,
    honouring the session's deload if one is on.

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
    seeded = _last_full_performance(exercise_id, position=position)
    if not seeded:
        return []

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
            weight=stats.deload_weight(prev['weight'], pct, increment),
            base_weight=prev['weight'],
            reps=stats.DELOAD_REPS,
            base_reps=prev['reps'],
            completed=False,
        )
        for j, prev in enumerate(seeded, start=1)
    ]


def _seeded_suggestion(session_, exercise, position):
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
    last = _last_performance(exercise.id, position=position)
    if not last:
        return None
    pct = session_.deload_pct if session_.is_deload else None
    if not pct:
        return last
    increment = stats.resolve_increment(exercise.weight_increment, exercise.is_unilateral)
    return {'weight': stats.deload_weight(last['weight'], pct, increment),
            'reps': stats.DELOAD_REPS}


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
        weight_increment=exercise.weight_increment,
        position=session_exercise.position,
        session_id=session_exercise.session_id,
        started_at=session_exercise.session.started_at,
        sets=completed_sets,
        # session is already joinedload()ed by load_performed(), so this costs
        # no extra query.
        is_deload=session_exercise.session.is_deload,
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
    recent = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None))
        .order_by(WorkoutSession.started_at.desc())
        # Over-fetched, because the zero-set filter below runs after this and
        # would otherwise hand back fewer than RECENT_SESSIONS rows.
        .limit(RECENT_SESSIONS * 4)
        .all()
    )
    # The vocabulary is the app's own list, not "whichever groups happen to
    # own an exercise". Seeded from the catalogue, a group you have never built
    # an exercise for simply could not appear -- so the section that exists to
    # say "you have quietly stopped training X" was structurally unable to name
    # legs at all. Cardio and Sonstiges stay out: they are buckets, not muscle
    # groups, and would sit at zero forever flagged "zu wenig".
    catalogue_groups = (
        {group for group in MUSCLE_GROUPS if group not in NON_MUSCLE_GROUPS}
        | {row.muscle_group or stats.NO_GROUP_LABEL
           for row in db.session.query(Exercise.muscle_group).distinct()}
    )

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

    # stall_report() lists every stalled lift in the catalogue, which is what
    # the "Steht still" roster should show. The deload signal is a narrower
    # read of the same data -- only the active rotation -- so it is computed
    # here from the report rather than by changing stall_report itself.
    stalls = stats.stall_report(rows_by_exercise)
    last_deload = (
        WorkoutSession.query
        .filter(WorkoutSession.finished_at.isnot(None), WorkoutSession.is_deload.is_(True))
        .order_by(WorkoutSession.started_at.desc())
        .first()
    )
    deload_suggestion = stats.deload_signal(
        stalls, rows_by_exercise, now,
        last_deload_at=last_deload.started_at if last_deload else None,
    )

    # Volume and record count per recent session, both folded out of `performed`
    # -- the bulk load this page already ran. Verlauf shows these and Start did
    # not, which made the landing page the poorer of the two lists.
    volume_by_session = {}
    for row in performed:
        volume_by_session[row.session_id] = volume_by_session.get(row.session_id, 0.0) + stats.row_volume(row)
    records_by_session = stats.session_record_counts(performed)
    # Only sessions that actually logged something. `consistency` above is fed
    # from `performed`, which requires at least one COMPLETED set, while this
    # list filtered on finished_at alone -- so a session where nothing was
    # ticked off appeared under "Letzte Workouts" while "Zuletzt vor N Tagen"
    # ignored it, and the two could disagree by days.
    recent_sessions = [
        {'session': session_,
         'volume': volume_by_session[session_.id],
         'records': records_by_session.get(session_.id, 0)}
        for session_ in recent if session_.id in volume_by_session
    ][:RECENT_SESSIONS]

    tonnage = stats.weekly_tonnage(performed, now)

    return render_template(
        'gym/heute.html',
        now=now,
        active_session=active_session,
        consistency=stats.consistency(list(session_started_at.values()), now),
        routines=stats.routine_memory(templates, routine_sessions, now),
        recent_sessions=recent_sessions,
        stalls=stalls,
        deload_suggestion=deload_suggestion,
        balance=stats.muscle_group_volume(performed, catalogue_groups, now),
        tonnage=tonnage,
        # The scale the bars are drawn against, named on the page so their
        # heights mean something. Also the empty-state gate: 0 means there is
        # nothing to chart, and the section says so instead of drawing eight
        # stubs and asserting a running week over them.
        tonnage_peak=max((week['volume'] for week in tonnage), default=0.0),
        templates=templates,
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
                # Just the template name. With the date appended, every list
                # that prints a session rendered the date twice in two adjacent
                # lines -- "HBF Push 31.07.2026" over "31.07.2026 · 19 min".
                # The row already carries the date; the name should say which
                # workout it was.
                session_.name = template.name
            for i, te in enumerate(template.exercises, start=1):
                session_exercise = SessionExercise(
                    exercise_id=te.exercise_id, position=i,
                    rest_seconds=te.rest_seconds if te.rest_seconds is not None else te.exercise.default_rest_seconds,
                )
                session_exercise.sets.extend(_seeded_sets(session_, te.exercise_id, i))
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
        #
        # Eager-loaded first. performed_from_session walks se.sets, se.exercise
        # and se.replaced_by per row, all lazy -- 21 queries on a 7-exercise
        # session. The live branch below already avoids touching se.replaced_by
        # for exactly this reason and says so in its own comment; this branch
        # was doing it twice.
        session_ = (
            WorkoutSession.query
            .options(
                joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise),
                joinedload(WorkoutSession.exercises).joinedload(SessionExercise.sets),
                joinedload(WorkoutSession.exercises).joinedload(SessionExercise.replaced_by),
            )
            .filter(WorkoutSession.id == session_.id)
            .one()
        )
        current = performed_from_session(session_)
        history = [
            row for row in load_performed(exercise_ids=[row.exercise_id for row in current])
            if row.session_id != session_.id
        ]
        comparable = []
        previous_session = None
        if session_.template_id:
            cohort = (
                WorkoutSession.query
                .options(load_only(WorkoutSession.id, WorkoutSession.started_at))
                .filter(
                    WorkoutSession.id != session_.id,
                    WorkoutSession.finished_at.isnot(None),
                    WorkoutSession.template_id == session_.template_id,
                    # A deliberately light session must not deflate the average
                    # every later session of this template is compared against.
                    # session_report cannot do this itself -- it receives bare
                    # floats with no flag to filter on.
                    WorkoutSession.is_deload.is_(False),
                )
                .all()
            )
            cohort_ids = {other.id for other in cohort}
            volumes = {}
            for row in load_performed():
                if row.session_id in cohort_ids:
                    volumes[row.session_id] = volumes.get(row.session_id, 0.0) + stats.row_volume(row)
            comparable = [volume for volume in volumes.values() if volume > 0]

            # The session before this one, of the same routine. The mean is a
            # judgement -- half of all sessions fall below it by construction --
            # while "last time" is a fact, and the page had nothing to compare
            # against except the mean. Every volume needed for this was already
            # in `volumes`; only the mean survived.
            earlier = sorted(
                (other for other in cohort
                 if other.started_at < session_.started_at and volumes.get(other.id)),
                key=lambda other: other.started_at,
            )
            if earlier:
                last = earlier[-1]
                previous_session = {
                    'id': last.id,
                    'started_at': last.started_at,
                    'volume': round(volumes[last.id], 1),
                }
        data = stats.session_report(current, history, comparable_session_volumes=comparable)
        data['previous_session'] = previous_session
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
        # session_report only sees PerformedExercise rows, which do not carry
        # the percentage -- it belongs to the session row itself.
        data['deload_pct'] = session_.deload_pct
        # Whether the deload percentage was actually applied to these weights.
        # A finished session always has completed sets, so flagging one
        # retroactively never rewrites anything -- without this the page would
        # claim a percentage of the working weight over the real weights the
        # user lifted. Same test the live page uses.
        data['deload_applied'] = any(
            s.base_weight is not None for se in session_.exercises for s in se.sets)
        data['deload_default_pct'] = stats.DELOAD_DEFAULT_PCT
        # The closed tick strip: one tick per logged set, in order, so the
        # debrief finishes the thing the live screen spent the workout filling.
        #
        # A record is an exercise-level fact here (session_report awards one per
        # exercise), so only a WEIGHT record can honestly be attributed to a
        # single set -- the one that lifted it, first match only. Volume and
        # e1RM records belong to the exercise as a whole and are carried by the
        # flare and the per-exercise tag instead of by a gold tick that would be
        # pointing at an arbitrary set.
        records_by_name = {record['name']: record for record in data['records']}
        tick_states = []
        for entry in data['exercises']:
            record = records_by_name.get(entry['name'])
            claimed = False
            for set_row in entry.get('set_rows', []):
                is_record = (
                    record is not None and record['kind'] == 'weight'
                    and not claimed and set_row.weight == record['value']
                )
                if is_record:
                    claimed = True
                tick_states.append('record' if is_record else 'done')
        data['tick_states'] = tick_states
        return render_template('gym/session_finished.html', session=session_,
                               weekday_short=WEEKDAY_SHORT, **data)

    # A replaced original is hidden from the active view, so its suggestion
    # would never be used -- skip computing it there. Visibility is derived
    # from replaces_id (already loaded on every row) rather than by touching
    # se.replaced_by, which would lazy-load a separate query per row.
    replaced_original_ids = {se.replaces_id for se in session_.exercises if se.replaces_id}
    visible_exercises = [se for se in session_.exercises if se.id not in replaced_original_ids]
    suggestions = {se.id: _seeded_suggestion(session_, se.exercise, se.position) for se in visible_exercises}
    history = load_performed(exercise_ids=[se.exercise_id for se in visible_exercises])
    by_exercise = {}
    for row in history:
        if row.session_id != session_.id:
            by_exercise.setdefault(row.exercise_id, []).append(row)
    stagnation_counts = {}
    record_set_ids = set()
    # Both signals below are progress judgements, and a deload session is not
    # an attempt at progress -- so neither is computed during one. The PR flare
    # must agree with the recap screen (session_report awards no record on a
    # deload), and a "go heavier" nudge is wrong advice beside deliberately
    # reduced weights. Guarding the whole loop rather than `continue`-ing per
    # iteration: is_deload is loop-invariant, and a per-iteration skip would
    # let a later maintainer add work above it that silently never runs.
    if not session_.is_deload:
        for se in visible_exercises:
            prior = by_exercise.get(se.exercise_id, [])
            count = stats.sessions_since_pr(prior, position=se.position)
            if count is not None and count >= stats.STAGNATION_THRESHOLD:
                stagnation_counts[se.id] = count
            # Live equivalent of the finished-session PR flare (session_report's
            # is_weight_pr/is_e1rm_pr) -- checked per completed set, against the
            # same prior-sessions-only pool, so a set can light up cyan the
            # instant it's confirmed rather than only on the recap screen an
            # hour later.
            for s in se.sets:
                if s.completed and stats.is_new_best(s.weight, s.reps, prior):
                    record_set_ids.add(s.id)
    exercises = Exercise.query.order_by(Exercise.name).all()

    # The live exercise: the first visible, non-skipped one that is not yet
    # fully logged, or the last visible one when everything is done.
    #
    # This used to be computed in the template. It moved here because three
    # surfaces now have to agree on the answer -- the session body, the resume
    # strip's "current exercise", and the rail that marks which segment is
    # live -- and a rule expressed three times in Jinja is a rule that drifts.
    live_se = None
    for se in visible_exercises:
        done = sum(1 for s in se.sets if s.completed)
        if not se.skipped and not (se.sets and done == len(se.sets)):
            live_se = se
            break
    if live_se is None and visible_exercises:
        live_se = visible_exercises[-1]

    # One tick per set in the whole workout, in order, so the strip reads as
    # the session filling up rather than as a chart. 'now' is the single set
    # about to be performed -- the same set the steppers are bound to.
    sets_done = sets_total = 0
    tick_states = []
    next_set_id = None
    if live_se is not None:
        next_set_id = next((s.id for s in live_se.sets if not s.completed), None)
    for se in visible_exercises:
        if se.skipped:
            continue
        for s in se.sets:
            sets_total += 1
            if s.completed:
                sets_done += 1
                tick_states.append('done')
            elif s.id == next_set_id:
                tick_states.append('now')
            else:
                tick_states.append('open')

    session_volume = sum(
        stats.set_volume(s.weight, s.reps, se.exercise.is_unilateral)
        for se in visible_exercises for s in se.sets if s.completed
    )

    resting = bool(session_.rest_ends_at and session_.rest_ends_at > dt.datetime.utcnow())
    # Whose rest is it? The set that started it, which after the last set of an
    # exercise is no longer on the exercise that is now live.
    rest_total_seconds = 0
    if resting:
        for se in visible_exercises:
            if any(s.id == session_.resting_set_id for s in se.sets):
                rest_total_seconds = se.rest_seconds or se.exercise.default_rest_seconds or 0
                break

    return render_template(
        'gym/session_detail.html',
        session=session_,
        visible_exercises=visible_exercises,
        live_se=live_se,
        live_id=live_se.id if live_se else None,
        # Resolved here, not in Jinja: the template must never re-implement the
        # fallback, or the two copies drift the moment DEFAULT_INCREMENT moves.
        live_increment=stats.resolve_increment(
            live_se.exercise.weight_increment, live_se.exercise.is_unilateral,
        ) if live_se else stats.resolve_increment(None, False),
        live_index=(visible_exercises.index(live_se) + 1) if live_se else 0,
        tick_states=tick_states,
        sets_done=sets_done,
        sets_total=sets_total,
        sets_open=sets_total - sets_done,
        session_volume=session_volume,
        # A rest is running if it has not elapsed. Deliberately NOT scoped to
        # the live exercise: finishing an exercise's last set schedules a rest
        # and advances the live exercise at the same moment, so requiring the
        # resting set to belong to the live one hid the countdown for exactly
        # the rest between two exercises -- the longest one you actually take.
        #
        # It still has to test the clock, not just the flag: the server keeps
        # resting_set_id set until the NEXT set starts a rest, so the flag alone
        # would show a dead countdown where the confirm button belongs.
        resting=resting,
        # The bar's total comes from the exercise that OWNS the resting set, not
        # from whichever one is live now -- otherwise the fill is drawn against
        # the wrong rest length the moment the rest spans an exercise boundary.
        rest_total_seconds=rest_total_seconds,
        suggestions=suggestions,
        stagnation_counts=stagnation_counts,
        record_set_ids=record_set_ids,
        exercises=exercises,
        muscle_groups=MUSCLE_GROUPS,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
        # PushSubscription has no user/device scoping (single-user app, one
        # flat table keyed by endpoint) -- "any row at all" is the correct
        # "already set up" signal here, not something narrower the schema
        # doesn't actually track.
        has_push_subscription=PushSubscription.query.first() is not None,
        has_completed_set=any(s.completed for se in session_.exercises for s in se.sets),
        # Whether the deload percentage was actually applied to the weights.
        # base_weight is non-NULL exactly when a set's weight is deload-scaled,
        # so this is the honest test -- the session's is_deload flag is not,
        # because a session flagged after a set was already logged keeps its
        # full working weights and would otherwise display a percentage that
        # describes nothing on screen.
        deload_applied=any(
            s.base_weight is not None for se in session_.exercises for s in se.sets),
        deload_pcts=stats.DELOAD_QUICK_PCTS,
        deload_default_pct=stats.DELOAD_DEFAULT_PCT,
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
        session_exercise = SessionExercise(
            session_id=session_.id, exercise_id=exercise_id, position=next_position,
            rest_seconds=exercise.default_rest_seconds if exercise else None,
        )
        # Seeded like every other path that puts an exercise into a session
        # (gym_start from a template, un-skip, reorder). This one used to
        # create nothing, which left the exercise leaning on the suggestion
        # alone -- and on a session started without a template that was the
        # only number on screen, so a deload never reached it. An exercise
        # with no history still seeds nothing, which is the same empty slot
        # as before.
        session_exercise.sets.extend(
            _seeded_sets(session_, exercise_id, next_position))
        db.session.add(session_exercise)
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


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/increment', methods=['POST'])
@login_required
def gym_update_exercise_increment(session_exercise_id):
    """Write the EXERCISE's increment from inside a running session.

    Reached from the per-exercise sheet, beside the rest field -- but unlike
    rest, which is genuinely per session, a loadable step is a property of the
    equipment and so lands on the Exercise itself and stays. Keyed on the
    SessionExercise regardless, because that is the id the sheet has and it
    keeps the redirect back to the workout trivial.
    """
    session_exercise = db.get_or_404(SessionExercise, session_exercise_id)
    session_exercise.exercise.weight_increment = _to_increment(
        request.form.get('weight_increment', ''))
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
        session_exercise.sets.extend(
            _seeded_sets(session_, session_exercise.exercise_id, session_exercise.position)
        )

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
    in the form, and set done/not-done -- these were two separate buttons
    before, which was redundant since confirming a set's numbers and marking
    it done are the same real-world action.

    The caller states the TARGET state in `completed` (1/0) rather than asking
    for a flip. A blind toggle is only correct if exactly one request ever
    arrives, and on this screen that is not true: a double tap on the 326x64
    confirm button, a retry after a response was lost on gym wifi (the case the
    error banner exists for), or a second tab all send it twice -- and the
    second one silently UN-logs the set and cancels its rest. Stating the
    target makes the write idempotent, so the duplicate is a no-op.

    `completed` is optional and the flip is kept as the fallback, because a
    stale page or a form posted from anywhere else still has to do something
    sensible."""
    set_ = db.get_or_404(SessionSet, set_id)
    session_ = set_.session_exercise.session

    weight = _to_float(request.form.get('weight', ''))
    reps = _to_int(request.form.get('reps', ''))
    if weight is not None:
        if weight != set_.weight:
            # Changed by hand -- ground truth from now on, so drop any stale
            # deload baseline that would otherwise overwrite it later. An
            # unchanged value is just the form echoing what is already stored
            # (the weight input and the check button share one form), and must
            # NOT count as an edit: clearing the baseline there would leave a
            # completed-then-un-completed set unable to return to its working
            # weight.
            set_.base_weight = None
        set_.weight = weight
    if reps is not None:
        if reps != set_.reps:
            # Same rule as the weight above: a typed rep count is ground truth
            # from now on, so a later toggle-off must not overwrite it.
            set_.base_reps = None
        set_.reps = reps

    wanted = request.form.get('completed')
    was_completed = set_.completed
    set_.completed = (wanted == '1') if wanted in ('0', '1') else (not set_.completed)
    if set_.completed and was_completed:
        # already logged, and the caller asked for logged: a duplicate request.
        # Persist any weight/reps it carried, but do NOT restart the rest --
        # that would extend a countdown the lifter is already part-way through.
        db.session.commit()
        return redirect(url_for('gym.session_detail', session_id=session_.id))
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
        if weight != set_.weight:
            # Changed by hand -- ground truth from now on, so drop any stale
            # deload baseline that would otherwise overwrite it later. An
            # unchanged value is just the form echoing what is already stored
            # (the weight input and the check button share one form), and must
            # NOT count as an edit: clearing the baseline there would leave a
            # completed-then-un-completed set unable to return to its working
            # weight.
            set_.base_weight = None
        set_.weight = weight
    if reps is not None:
        if reps != set_.reps:
            # Same rule as the weight above: a typed rep count is ground truth
            # from now on, so a later toggle-off must not overwrite it.
            set_.base_reps = None
        set_.reps = reps
    db.session.commit()
    # request.args carried through: the debrief's "Vorlage aktualisieren" offer
    # is gated on ?just_finished, and this redirect dropped it -- so correcting
    # one mistyped set silently destroyed the offer, permanently, with no other
    # route to it. gym_session_summary already does exactly this.
    return redirect(url_for('gym.session_detail',
                            session_id=set_.session_exercise.session_id,
                            **request.args.to_dict()))


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
                se.sets.extend(_seeded_sets(session_, se.exercise_id, position))
            position += 1
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/session/<int:session_id>/rest/skip', methods=['POST'])
@login_required
def gym_skip_rest(session_id):
    """End the running rest now.

    New with the Puls session screen, which gives the rest the confirm
    button's own slot -- once the countdown occupies the control your thumb is
    on, "I'm ready, go" needs a real action behind it. Before, the only way out
    of a rest was to wait it out or to confirm the next set through it.

    Clearing the window also cancels the pending push, for the same reason
    finishing early does: the notifier daemon would otherwise fire a
    "Pause vorbei" for a rest the lifter already ended themselves.
    """
    session_ = db.get_or_404(WorkoutSession, session_id)
    session_.rest_ends_at = None
    session_.resting_set_id = None
    _cancel_pending_push(session_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


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


@gym_bp.route('/gym/session/<int:session_id>/deload', methods=['POST'])
@login_required
def gym_toggle_deload(session_id):
    """Mark (or unmark) a session as a deliberately light one.

    The flag is always editable -- including on a finished session, since
    labelling a workout you already did is a first-class flow and the reason
    this feature exists. What is gated is the *prescription*: weights are only
    rewritten when the session has no completed set, so nothing actually
    lifted is ever overwritten.

    That test is computed, not latched: un-completing a set re-enables the
    rewrite, so a mis-tap is always recoverable.

    Toggling off restores the persisted pre-deload baseline rather than
    dividing the weights back up. Reversing the arithmetic after
    deload_weight()'s floor is lossy (80 -> 55 -> 78.57 -> 77.5), so repeated
    toggling would walk the weights downward.

    Editing a set's weight by hand mid-deload drops that set's own baseline
    (see gym_toggle_set_complete/gym_update_set), so deload on -> edit one set
    by hand -> deload off leaves that set holding the typed number while every
    other set returns to its own working weight. This asymmetry is intended:
    each set independently reflects whatever the user most recently said
    about it, not a single all-or-nothing session state.
    """
    session_ = db.get_or_404(WorkoutSession, session_id)

    on = request.form.get('on') == '1'
    pct = _to_int(request.form.get('pct', ''), fallback=stats.DELOAD_DEFAULT_PCT)
    if pct not in stats.DELOAD_ALLOWED_PCTS:
        pct = stats.DELOAD_DEFAULT_PCT

    session_.is_deload = on
    session_.deload_pct = pct if on else None

    has_completed_set = any(
        s.completed for se in session_.exercises for s in se.sets
    )
    if not has_completed_set:
        for session_exercise in session_.exercises:
            increment = stats.resolve_increment(
                session_exercise.exercise.weight_increment,
                session_exercise.exercise.is_unilateral,
            )
            for s in session_exercise.sets:
                if on:
                    # Capture the baseline the first time only. Re-applying the
                    # toggle, or changing the percentage, then always scales
                    # from the working weight rather than from the already
                    # reduced one -- without this, 70 % followed by 60 % gives
                    # 32.5 kg instead of 47.5 kg, and a double-tap compounds.
                    if s.base_weight is None:
                        s.base_weight = s.weight
                    s.weight = stats.deload_weight(s.base_weight, pct, increment)
                    # Reps move with the weight, and for the same reason: a
                    # deload is a prescription, not a scaled-down copy of the
                    # last hard session. Captured first so switching the
                    # deload off returns the real set length too.
                    if s.base_reps is None:
                        s.base_reps = s.reps
                    s.reps = stats.DELOAD_REPS
                elif s.base_weight is not None or s.base_reps is not None:
                    if s.base_weight is not None:
                        s.weight = s.base_weight
                        s.base_weight = None
                    if s.base_reps is not None:
                        s.reps = s.base_reps
                        s.base_reps = None

    db.session.commit()
    # Same reason as gym_update_set: marking a finished workout as a deload
    # dropped ?just_finished and took the template offer with it.
    return redirect(url_for('gym.session_detail', session_id=session_.id,
                            **request.args.to_dict()))


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
    record count -- spec 6.6, one of the four real nav destinations."""
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
            # The same exercises the volume beside it was computed from. The
            # row listed every SessionExercise including ones swapped out
            # mid-workout, so a session showed 10 names next to a total built
            # from 7 -- and opening it revealed the 7.
            'exercises': [se.exercise.name for se in s.exercises
                          if se.id not in replaced_away_ids],
            # Searchable date text, so a query like "31.07" or "juli" works.
            # data-search carried only the name and the exercises, and item 5
            # stopped appending the date to new session names -- so date search
            # was degrading to nothing as history accumulated.
            'search_date': '%s %s %d' % (
                stats.to_local(s.started_at).strftime('%d.%m.%Y'),
                MONTH_NAMES[stats.to_local(s.started_at).month - 1],
                stats.to_local(s.started_at).year,
            ),
        }
        for s in sessions
    ]

    # Month bands, grouped here rather than in the template: Jinja can detect a
    # change of month while looping, but it cannot count the rows in a group it
    # has not reached yet, and faking that with filters over the whole list is
    # how a template starts doing arithmetic. German month names live here for
    # the same reason -- strftime('%B') follows the server's locale, which is
    # not the UI's.
    # LOCAL month, not the stored UTC one. Every row renders its date through
    # the `|local` filter, so an unconverted key put a row dated 01.07. under a
    # heading reading "Juni" and inflated June's count -- and on 1 January it
    # misfiles by a year.
    #
    # Each band also carries its own totals, and each entry the gap that
    # precedes it. Both are sums over rows already in hand: the route computed
    # volume_by_session and records_by_session above and was throwing away
    # everything but the count, on the only page that sees the whole history.
    months = []
    previous_started = None
    for entry in history:
        started = stats.to_local(entry['session'].started_at)
        key = (started.year, started.month)
        if not months or months[-1]['key'] != key:
            months.append({
                'key': key,
                'label': '%s %d' % (MONTH_NAMES[started.month - 1], started.year),
                'slug': '%04d-%02d' % key,
                'entries': [],
                'volume': 0.0,
                'records': 0,
            })
        # history is newest-first, so `previous_started` is the session AFTER
        # this one in time; the gap belongs to the row below the break.
        entry['gap_days'] = ((previous_started - started).days
                             if previous_started is not None else None)
        previous_started = started
        months[-1]['entries'].append(entry)
        months[-1]['volume'] += entry['volume']
        months[-1]['records'] += entry['record_count']

    for month in months:
        month['volume'] = round(month['volume'], 1)

    return render_template('gym/verlauf.html', history=history, months=months,
                           gap_threshold=VERLAUF_GAP_DAYS, weekday_short=WEEKDAY_SHORT)


# A break this long or longer gets called out in the history. Below it the
# date column already tells the story; above it, a layoff was represented by
# nothing at all -- rows sit at equal spacing one day or six weeks apart, and a
# month with no sessions simply had no band.
VERLAUF_GAP_DAYS = 10

# Here for the same reason MONTH_NAMES is: strftime('%a') follows the server's
# locale, which is not the UI's.
WEEKDAY_SHORT = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')

SPARK_W = 74.0
SPARK_H = 24.0


def _progression_view(ranking, limit=8):
    """Progression rows with their sparkline drawn and their bar sized.

    Geometry in Python for the same reason the exercise chart's is: Jinja doing
    coordinate arithmetic is unreadable, and an inline SVG inherits the palette
    where a canvas cannot.

    The bar is diverging from a centre line, so gains and losses read as
    directions rather than as two lists. It is scaled against the largest
    absolute change on the page -- against a fixed 100 % a typical +40 % lift
    would draw as a stub, and the ranking would look flat when it is not.

    Both ends are kept: the biggest movers AND the biggest losers, because a
    page that only shows what went up is a highlight reel, not a report.
    """
    if not ranking:
        return []
    head = ranking[:limit]
    tail = [entry for entry in ranking[limit:] if entry['change_pct'] < 0]
    shown = head + [entry for entry in tail if entry not in head]

    widest = max((abs(entry['change_pct']) for entry in shown), default=1.0) or 1.0
    out = []
    for entry in shown:
        points = entry['points']
        lo, hi = min(points), max(points)
        span = (hi - lo) or 1.0
        step = SPARK_W / max(len(points) - 1, 1)
        spark = ' '.join(
            '%.1f,%.1f' % (index * step, SPARK_H - 2 - (value - lo) / span * (SPARK_H - 4))
            for index, value in enumerate(points)
        )
        out.append(dict(
            entry,
            spark=spark,
            bar_pct=round(abs(entry['change_pct']) / widest * 50.0, 2),
            is_up=entry['change_pct'] >= 0,
        ))
    return out


@gym_bp.route('/gym/statistik')
@login_required
def gym_statistik():
    """All-time analytics (spec 2026-07-29). Desktop-only in the navigation,
    but the URL stays reachable: opening it on a phone renders the page
    single-column rather than redirecting, because hiding data the user asked
    for is worse than showing it in a cramped layout.

    Thin by construction. The one bulk load below feeds every figure on the
    page -- same discipline as Heute/Uebungen/Verlauf (spec 5.4): never one
    query per exercise, no matter how long the history gets. All analysis
    lives in analytics.py.

    Unlike gym_verlauf, this does NOT exclude a replaced-away original's sets.
    That is deliberate. Verlauf reports a session's volume as the sum of the
    slots it ran, so an abandoned original would double-count a slot the
    substitute already represents. Statistik describes what was lifted, and a
    set you performed before swapping the exercise out was still performed --
    the same reason deload sessions count toward tonnage here. The consequence
    is that "Groesstes Workout" can exceed the figure Verlauf shows for that
    same session; if that ever needs to change, change it here, not by
    quietly filtering one of them.
    """
    now = dt.datetime.utcnow()
    performed = load_performed()

    # The lede: one sentence built from the numbers, so the page answers before
    # it reports. The longest break is the only figure here not already in
    # analytics -- it is cheap from the session dates this page has loaded
    # anyway, and it is the fact that makes the sentence worth reading.
    session_dates = sorted({row.started_at for row in performed})
    longest_gap = max(
        ((b - a).days for a, b in zip(session_dates, session_dates[1:])),
        default=0,
    )

    # Records: the most recent RECENT_RECORDS shown flat, everything older
    # folded into year bands.
    #
    # Bounding by CALENDAR was the bug. Grouping by year and opening the first
    # band assumes a history that spans years -- and for every new account, and
    # for this one today, it does not: one band, forced open, every record in
    # it. Measured at 57 records that was 3,648px of a 5,249px page, i.e. worse
    # than the two-thirds the brief set out to fix. It also flipped overnight:
    # on 2 January the largest section on the page would collapse to one row.
    #
    # Bounding by COUNT is stable in both directions. The fold is still lossless
    # -- nothing is dropped, and the header still counts every record there is.
    RECENT_RECORDS = 12
    records = analytics.record_timeline(performed)
    recent_records = records[:RECENT_RECORDS]
    record_years = []
    for record in records[RECENT_RECORDS:]:
        year = record['started_at'].year
        if not record_years or record_years[-1]['year'] != year:
            record_years.append({'year': year, 'records': []})
        record_years[-1]['records'].append(record)

    return render_template(
        'gym/statistik.html',
        months=analytics.monthly_tonnage(performed, now),
        longest_gap=longest_gap,
        records=records,
        recent_records=recent_records,
        record_years=record_years,
        month_names=MONTH_NAMES,
        daypart_names=DAYPART_NAMES,
        weekday_names=WEEKDAY_NAMES,
        totals=analytics.totals(performed, now),
        progression=_progression_view(analytics.progression_ranking(performed)),
        rep_range=analytics.rep_range_distribution(performed),
        fatigue=analytics.fatigue_curve(performed),
        daypart=analytics.daypart_volume(performed),
        weekday=analytics.weekday_distribution(performed),
        rest_gap=analytics.rest_gap_effect(performed),
        min_sets_for_rep_range=analytics.MIN_SETS_FOR_REP_RANGE,
        effort=analytics.effort_distribution(performed),
    )


@gym_bp.route('/gym/export')
@login_required
def gym_export():
    """Downloadable JSON of specific finished workouts, picked by id from
    Verlauf's own checklist (the 30/90-day presets there just bulk-check
    matching rows client-side -- this route only ever sees the final id
    list, never a date range). Full detail (every set, not just aggregates)
    so nothing useful is thrown away up front. Both original and substitute
    SessionExercise rows are exported (mirroring what a finished session's
    own detail view already shows -- see session_detail's visible_exercises
    computation), each carrying replaces/replaced_by exercise names so a
    swap is fully traceable."""
    ids_param = request.args.get('ids', '')
    session_ids = []
    for raw_id in ids_param.split(','):
        raw_id = raw_id.strip()
        if raw_id.isdigit():
            session_ids.append(int(raw_id))

    sessions = (
        WorkoutSession.query
        .filter(
            WorkoutSession.finished_at.isnot(None),
            WorkoutSession.id.in_(session_ids),
        )
        .order_by(WorkoutSession.started_at.asc())
        .all()
    ) if session_ids else []

    payload = {
        'exported_at': dt.datetime.utcnow().isoformat() + 'Z',
        'requested_session_ids': session_ids,
        'sessions': [
            {
                'id': s.id,
                'name': s.name,
                'template_name': s.template.name if s.template else None,
                'started_at': s.started_at.isoformat() + 'Z',
                'finished_at': s.finished_at.isoformat() + 'Z',
                'is_deload': s.is_deload,
                'deload_pct': s.deload_pct,
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
    filename = f"gym-export-{len(sessions)}-workouts.json"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@gym_bp.route('/gym/uebungen')
@login_required
def gym_uebungen():
    now = dt.datetime.utcnow()
    exercises = Exercise.query.order_by(Exercise.name).all()

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
        # Judged slot, record weight and record e1RM must agree with what
        # the exercise's own detail page shows and with what stall_report()
        # judges on the dashboard, so deload rows are dropped BEFORE they
        # reach dominant_position/best_e1rm/best_weight/sessions_since_pr --
        # the same filter-before-judge order stall_report() uses (see its
        # own docstring). `last_done` stays on the unfiltered `rows`: "when
        # did I last do this" is a fact a deload session legitimately
        # answers, it is not a judgement.
        progression = stats.progression_rows(rows)
        # dominant_position() requires at least one row -- a brand new
        # exercise, or one whose only history is deloads, has no position to
        # speak of, and exercise_state returns 'neu' from its own
        # empty-rows check before position is ever consulted, so None is a
        # safe stand-in here.
        position = stats.dominant_position(progression) if progression else None
        best_e1rm = max((stats.best_e1rm(row) for row in progression), default=None)
        state = stats.exercise_state(progression, position=position)
        chip_class, chip_label = EXERCISE_STATE_CHIP.get(state, (None, None))
        last_done = max((row.started_at for row in rows), default=None)
        entries_by_id[exercise.id] = {
            'exercise': exercise,
            'chip_class': chip_class,
            'chip_label': chip_label,
            'last_done': last_done,
            'best_weight': max((stats.best_weight(row) for row in progression), default=None),
            # What you would load TODAY, which is the question a catalogue is
            # opened with. The row led with the all-time best -- unlabelled, so
            # "Military Press · 15,0 kg" could not be told apart from a working
            # weight -- and that figure is already on the exercise's own page
            # with a label on it.
            'last_weight': stats.best_weight(progression[-1]) if progression else None,
            'days_ago': (stats.calendar_days_between(last_done, now)
                         if last_done is not None else None),
            'sessions_since_pr': stats.sessions_since_pr(progression, position=position) if progression else None,
        }

    # Default/grouped view (spec 6.2's "nach Muskelgruppe"). The two flat
    # sorts ("am längsten ohne PR", "zuletzt gemacht") are client-side
    # re-orderings of these SAME rows in uebungen.html's own script, not a
    # second server round trip -- every exercise's data attributes carry
    # what that script needs (see the template).
    # Seeded from MUSCLE_GROUPS, so a group with nothing in it still gets a
    # band. group_exercises_by_muscle emits only non-empty groups, which made
    # the catalogue structurally unable to say "you have no leg exercises" --
    # the single strongest signal for the planning question, rendered as
    # nothing at all. Same fix Start's muscle balance got in item 5, and
    # Cardio/Sonstiges stay out for the same reason.
    filled = dict(stats.group_exercises_by_muscle(exercises, MUSCLE_GROUPS))
    grouped = []
    for group_name in MUSCLE_GROUPS:
        if group_name in NON_MUSCLE_GROUPS and group_name not in filled:
            continue
        grouped.append((group_name,
                        [entries_by_id[e.id] for e in filled.get(group_name, [])]))
    for group_name, group_exercises in filled.items():
        if group_name not in MUSCLE_GROUPS:      # NO_GROUP_LABEL and legacy values
            grouped.append((group_name, [entries_by_id[e.id] for e in group_exercises]))

    return render_template(
        'gym/uebungen.html',
        grouped=grouped,
        muscle_groups=MUSCLE_GROUPS,
        open_by_default=len(exercises) <= UEBUNGEN_FOLD_ABOVE,
        # The sheet's rest placeholder said 90 while this is what a blank field
        # actually stores.
        default_rest_seconds=DEFAULT_REST_SECONDS,
        added_id=_to_int(request.args.get('added')),
        name_taken=bool(request.args.get('name_taken')),
    )


# Buckets in MUSCLE_GROUPS that are not muscle groups, so a section built
# from the full vocabulary does not carry them at zero forever.
NON_MUSCLE_GROUPS = ('Cardio', 'Sonstiges')

# How many finished workouts the Start page lists.
RECENT_SESSIONS = 5

# Above this many exercises the catalogue opens folded; at or below it every
# group starts open. Hardcoded shut, the page's default state contained no
# exercises at all -- 0 of 17 visible on a phone AND on a 1280 desktop, with
# the fastest route to your own list being to press a SORT button, because the
# two flat sorts ignore the fold. Folding is right for a long catalogue and
# wrong for a short one, so it follows the length.
UEBUNGEN_FOLD_ABOVE = 30

CHART_W = 320.0
CHART_H = 128.0
CHART_PAD = 10.0

# Smallest y range the chart will draw, in kg. See _chart_geometry.
CHART_MIN_SPAN = 5.0

# How far apart same-day sessions are nudged on the x axis, in viewBox units.
SAME_DAY_SPREAD = 16.0

# A slot needs this many sessions before its numbers count as a track record
# rather than one good day.
MIN_SESSIONS_FOR_DEFAULT_POSITION = 2


def _default_position(series):
    """Which slot the exercise page opens on.

    The best-performing one by best e1RM, restricted to slots with real history
    (see the constant above) so a single lucky session cannot become the default
    view. Falls back to the slot with the most sessions, then to None, which
    renders every slot at once.

    Returns (position, reason); the reason is what the page tells the reader,
    because a slot picked FOR them has to say on what grounds.
    """
    if not series:
        return None, None
    proven = [entry for entry in series
              if len(entry['points']) >= MIN_SESSIONS_FOR_DEFAULT_POSITION]
    if proven:
        # ties break toward the slot with more sessions, then the earlier slot
        best = max(proven, key=lambda entry: (
            max(point['e1rm'] for point in entry['points']),
            len(entry['points']),
            -entry['position'],
        ))
        return best['position'], 'strongest'
    fallback = max(series, key=lambda entry: (len(entry['points']), -entry['position']))
    return fallback['position'], 'most'


def _chart_geometry(series, pr_e1rm=None):
    """Turn exercise_progress()'s series into SVG coordinates.

    Computed here rather than in the template because Jinja doing coordinate
    arithmetic is unreadable, and because this replaces Chart.js: an inline SVG
    inherits the palette directly, which a canvas cannot -- it can only read
    resolved rgb(), so a themed canvas silently loses its colours (this project
    has hit that before).

    One polyline PER POSITION, not one for the whole exercise. The old chart
    drew a line per slot, and collapsing them would quietly drop a dimension:
    the same lift in slot 1 and slot 3 is two different stories.

    Deload points stay in the data -- dropping them would leave holes -- but are
    marked so the template can draw their legs dotted. A solid line through a
    deliberately light week reads as a collapse that never happened.
    """
    values = [point['e1rm'] for entry in series for point in entry['points']]
    if not values:
        return None
    data_lo, data_hi = min(values), max(values)

    # The axis is padded to a floor, and that is not cosmetic. Auto-fitting to
    # the data alone means the y range is whatever the data happens to span, so
    # 0,7 kg of drift over a year gets stretched across the full plot height and
    # draws as a cliff. Every chart looked equally dramatic and none of them
    # said how much. Below the floor the range is widened symmetrically around
    # its own midpoint, so a flat lift renders flat -- and the tick labels below
    # state the range either way, which is what actually makes the shape legible.
    lo, hi = data_lo, data_hi
    if hi - lo < CHART_MIN_SPAN:
        mid = (hi + lo) / 2.0
        lo, hi = mid - CHART_MIN_SPAN / 2.0, mid + CHART_MIN_SPAN / 2.0
    span = hi - lo

    # x comes from the DATE, not from the point's index within its own series.
    # Indexing looked right with one line and was wrong the moment a second
    # appeared: a slot with two sessions got spread across the same width as a
    # slot with seven, so the two lines were drawn on different time axes and
    # crossed each other for no reason. One shared date axis is the only way
    # two slots can be compared at all, which is the whole point of drawing
    # them together.
    stamps = [point['started_at'] for entry in series for point in entry['points']]
    first, last = min(stamps), max(stamps)
    days = (last - first).total_seconds() / 86400.0 or 1.0

    # Sessions on the SAME DAY land on the same x and stack into a vertical
    # line you cannot read. They are nudged apart by a few units each, keeping
    # chronological order -- the date still places the group, the offset only
    # separates its members. Small enough that it cannot be mistaken for elapsed
    # time: a whole day of sessions occupies less width than two days do.
    same_day = {}
    for entry in series:
        for point in entry['points']:
            key = point['started_at'].date()
            same_day.setdefault(key, []).append(point['started_at'])
    def _base_x(stamp):
        return CHART_PAD + ((stamp - first).total_seconds() / 86400.0) / days * (CHART_W - 2 * CHART_PAD)

    nudge = {}
    for stamps in same_day.values():
        ordered = sorted(set(stamps))
        if len(ordered) < 2:
            continue
        spread = min(SAME_DAY_SPREAD, (CHART_W - 2 * CHART_PAD) / 8)
        step = spread / (len(ordered) - 1)
        offsets = [-spread / 2 + index * step for index in range(len(ordered))]
        # A day sitting on either edge -- and the newest one always does -- gets
        # the whole group shifted inward rather than each member clamped, which
        # would silently re-stack the very points this is separating. The shift
        # is measured from the members' OWN positions: within one day each still
        # has its own base x, so testing only the first one left the last one
        # hanging past the edge.
        placed = [_base_x(stamp) + offset for stamp, offset in zip(ordered, offsets)]
        shift = 0.0
        if max(placed) > CHART_W - CHART_PAD:
            shift = (CHART_W - CHART_PAD) - max(placed)
        elif min(placed) < CHART_PAD:
            shift = CHART_PAD - min(placed)
        for stamp, offset in zip(ordered, offsets):
            nudge[stamp] = offset + shift

    out = []
    for entry in series:
        points = []
        for point in entry['points']:
            offset = (point['started_at'] - first).total_seconds() / 86400.0
            points.append({
                'x': round(min(max(
                    CHART_PAD + offset / days * (CHART_W - 2 * CHART_PAD)
                    + nudge.get(point['started_at'], 0.0),
                    0.0), CHART_W), 2),
                'y': round(CHART_H - CHART_PAD - (point['e1rm'] - lo) / span * (CHART_H - 2 * CHART_PAD), 2),
                'is_deload': point['is_deload'],
                'e1rm': point['e1rm'],
                'started_at': point['started_at'],
            })
        out.append({'position': entry['position'], 'points': points})

    # Every series is the same rose, because 4.3 fixes the palette at three
    # semantic hues and a slot number is not a semantic state. With three slots
    # overlapping that was unreadable, so they separate by WEIGHT instead: the
    # slot the exercise actually lives in (most sessions) draws solid, the
    # occasional ones recede. Each line also carries its slot number at its last
    # point, so the ordering is stated and not merely implied by opacity.
    out.sort(key=lambda entry: -len(entry['points']))
    for rank, entry in enumerate(out):
        # Floored at 0.65: a line is non-text UI and owes 3:1 against its panel.
        # Measured on the light scheme, which is the binding one -- --done over
        # the light chassis is 7.29:1 at full, 3.27:1 at 0.65 and 2.94:1 at 0.6.
        # The old ramp bottomed out at 0.3 (1.63:1), so the third slot was
        # decoration rather than data. Stroke width carries the separation that
        # opacity can no longer afford to.
        entry['opacity'] = 1.0 if rank == 0 else (0.8 if rank == 1 else 0.65)
        entry['width'] = 2.5 if rank == 0 else (1.9 if rank == 1 else 1.4)
        entry['is_main'] = (rank == 0)
        # `tip`, not `last`: the date-axis bounds above are named first/last and
        # rebinding one of them here silently fed a point dict to the date
        # arithmetic further down.
        tip = entry['points'][-1] if entry['points'] else None
        # The last point is usually AT the right edge, so a label placed to its
        # right lands outside the viewBox and is clipped. Flip to the left there
        # and lift it clear of the line either way.
        near_edge = tip is not None and tip['x'] > CHART_W - 34
        entry['label_x'] = round((tip['x'] - 8) if near_edge else (tip['x'] + 8), 2) if tip else 0
        entry['label_y'] = round(max(tip['y'] - 8, 12), 2) if tip else 0
        entry['label_anchor'] = 'end' if near_edge else 'start'

    # Slots that ran in the same weeks end at the same date, so their labels are
    # placed at nearly the same point and land on top of each other -- P5 was
    # drawn through P2. Push apart any pair that shares a horizontal
    # neighbourhood, working down the chart and folding upward at the floor.
    LABEL_GAP, LABEL_NEAR = 13.0, 40.0
    placed = []
    for entry in sorted((e for e in out if e['points']), key=lambda e: e['label_y']):
        for other in placed:
            if abs(entry['label_x'] - other['label_x']) >= LABEL_NEAR:
                continue
            if abs(entry['label_y'] - other['label_y']) < LABEL_GAP:
                entry['label_y'] = round(other['label_y'] + LABEL_GAP, 2)
        if entry['label_y'] > CHART_H - 4:
            entry['label_y'] = round(min(e['label_y'] for e in placed) - LABEL_GAP, 2) if placed else 12.0
        placed.append(entry)

    # The gold dot is the EXERCISE's best -- the same number the PR band above
    # the chart prints -- not the best of whatever happens to be plotted.
    #
    # Marking per series was the first bug: a position with a single session was
    # trivially its own best and got a record dot, so one chart carried two
    # golds and one of them meant nothing. Taking the max of the plotted points
    # fixed that and introduced the next one: under `?position=N` the plotted
    # set is one slot, so the slot's ceiling was promoted to "Rekord" and the
    # chart gold-dotted 85,8 while the band directly above it read 87,4.
    #
    # pr_e1rm comes from the UNFILTERED history (stats.exercise_progress), so a
    # filtered view that contains no record now correctly shows no gold at all.
    # A deload can never hold it, matching every other record rule here.
    candidates = [p for entry in out for p in entry['points'] if not p['is_deload']]
    if pr_e1rm is not None:
        best = pr_e1rm.get('e1rm') if isinstance(pr_e1rm, dict) else pr_e1rm
    else:
        best = max((p['e1rm'] for p in candidates), default=None)
    claimed = False
    for entry in out:
        for point in entry['points']:
            point['is_best'] = (
                best is not None and not claimed
                and not point['is_deload'] and point['e1rm'] == best
            )
            claimed = claimed or point['is_best']

    # One label per gridline, as a percentage of the viewBox so the HTML gutter
    # can sit beside the SVG and stay at text size instead of being scaled up
    # with the drawing.
    #
    # The decimal is kept whenever there is one. Rounding the top tick to whole
    # kg printed 87 directly under a record band reading 87,4 -- two numbers for
    # the same point, which reads as a discrepancy rather than as rounding.
    def fmt(value):
        text = '%.1f' % value
        return (text[:-2] if text.endswith('.0') else text).replace('.', ',')

    ticks = [{'y_pct': round(y / CHART_H * 100, 3), 'text': fmt(lo + span * frac)}
             for frac, y in ((1.0, CHART_PAD), (0.5, CHART_H / 2), (0.0, CHART_H - CHART_PAD))]

    # The middle date, not the middle ROW. The template took the median session
    # out of the table and printed it under the centre of the axis -- which was
    # right only while x came from the point's index. On a real date axis the
    # median session sits wherever its date puts it, so a run of three sessions
    # in one week followed by a month off printed a date under the midpoint that
    # was nowhere near it.
    #
    # Deduped, because an exercise whose whole history is one day -- or one slot
    # filtered down to a single date -- printed "31.07. 31.07. 31.07." across
    # the axis. Order is preserved, so three marks stay left/centre/right and a
    # collapsed range falls back to one.
    middle = first + (last - first) / 2
    dates = []
    for stamp in (first, middle, last):
        text = stats.to_local(stamp).strftime('%d.%m.')
        if text not in dates:
            dates.append(text)

    # What the legend is allowed to claim. A key for a mark that is not on the
    # chart is noise, and the deload key was on every chart in a database that
    # contains no deload at all.
    plotted = [p for entry in out for p in entry['points']]

    return {'series': out, 'lo': data_lo, 'hi': data_hi, 'axis_lo': lo, 'axis_hi': hi,
            'ticks': ticks, 'dates': dates, 'width': CHART_W, 'height': CHART_H,
            'has_deload': any(p['is_deload'] for p in plotted),
            'has_record': any(p['is_best'] for p in plotted)}


@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = db.get_or_404(Exercise, exercise_id)
    rows = load_performed(exercise_ids=[exercise.id], include_active=True)

    # The default view is one slot, not all of them. "Alle" draws every position
    # at once, which is the comparison view -- useful when you want it, and a
    # poor thing to land on: the answer to "how is this lift going" is a single
    # line, and overlapping slots bury it.
    #
    # Which slot: the best-performing one, meaning highest best-e1RM -- but only
    # among slots with at least two sessions. A slot used once is a data point,
    # not a track record, and defaulting to it would show a flattering line
    # built from a single lucky day. With nothing qualifying, fall back to the
    # slot the exercise actually lives in (the most sessions).
    #
    # `?position=all` is how the template asks for the comparison view, so the
    # default stays reachable in one click and the URL stays honest about what
    # it is showing.
    raw_position = request.args.get('position')
    default_reason = None
    if raw_position == 'all':
        position = None
    else:
        position = _to_int(raw_position)
        if position is None:
            position, default_reason = _default_position(
                stats.exercise_progress(rows, position=None)['series'])

    # Whether the page CHOSE this slot or was told to. Without it the chart and
    # the session list were silently filtered on arrival: a pill was lit that
    # the reader never pressed, and everything below it counted one slot while
    # reading like the whole exercise.
    position_is_default = (raw_position is None and position is not None)
    if not position_is_default:
        default_reason = None

    data = stats.exercise_progress(rows, position=position)
    chip_class, chip_label = EXERCISE_STATE_CHIP.get(data['state'], (None, None))
    return render_template(
        'gym/exercise_detail.html', exercise=exercise, muscle_groups=MUSCLE_GROUPS,
        chip_class=chip_class, chip_label=chip_label,
        selected_position_is_default=position_is_default,
        selected_position_reason=default_reason,
        chart=_chart_geometry(data['series'], data.get('pr_e1rm')),
        # Only offer deletion when nothing depends on it -- same test the
        # catalogue used before this moved off the list.
        can_delete=not exercise.session_exercises and not exercise.template_exercises,
        **data,
    )


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
        progress = stats.exercise_progress(rows, position=None)

    def fmt_weight_pr(pr):
        if not pr:
            return None
        return {'weight': pr['weight'], 'reps': pr['reps'], 'position': pr['position'],
                'date': stats.to_local(pr['started_at']).strftime('%d.%m.%Y')}

    def fmt_e1rm_pr(pr):
        if not pr:
            return None
        return {'e1rm': pr['e1rm'], 'weight': pr['weight'], 'reps': pr['reps'], 'position': pr['position'],
                'date': stats.to_local(pr['started_at']).strftime('%d.%m.%Y')}

    return jsonify({
        'exercise_id': exercise.id,
        'name': exercise.name,
        'is_unilateral': exercise.is_unilateral,
        'selected_position': progress['selected_position'],
        'series': progress['series'],
        # The same geometry the exercise page draws from. The modal used to ship
        # raw series and let Chart.js lay them out on a category axis, which drew
        # a six-week gap and four same-day sessions at the same width -- so the
        # two charts in this app disagreed about what the x axis meant.
        'chart': _chart_geometry(progress['series'], progress.get('pr_e1rm')),
        'pr_weight': fmt_weight_pr(progress['pr_weight']),
        'pr_e1rm': fmt_e1rm_pr(progress['pr_e1rm']),
    })


@gym_bp.route('/gym/exercises/add', methods=['POST'])
@login_required
def gym_add_exercise():
    # The write reports itself. A duplicate name was a silent no-op and a
    # success landed the new exercise inside a collapsed band, so the only
    # difference between "saved" and "discarded" was a digit beside the h1.
    # gym_update_exercise already had the ?name_taken= convention; this is the
    # same one.
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('gym.gym_uebungen'))
    if Exercise.query.filter_by(name=name).first():
        return redirect(url_for('gym.gym_uebungen', name_taken=1))

    exercise = Exercise(
        name=name,
        muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
        default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
        weight_increment=_to_increment(request.form.get('weight_increment', '')),
        is_unilateral=request.form.get('is_unilateral') == 'on',
    )
    db.session.add(exercise)
    db.session.commit()
    return redirect(url_for('gym.gym_uebungen', added=exercise.id))


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
    exercise.weight_increment = _to_increment(request.form.get('weight_increment', ''))
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
    if not is_valid_push_endpoint(endpoint):
        return jsonify({'status': 'error', 'message': 'unrecognized push service endpoint'}), 400

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
