"""The live workout: starting a session, the session screen, and every
mutation the screen performs.

This is the domain the React port replaces. `_live_context` is the seam --
it is what session_detail.html renders from today and what the JSON payload
will wrap, so the page and the endpoint cannot disagree about which exercise
is live.

Moved verbatim from the pre-split routes.py.
"""
import datetime as dt

from flask import current_app, jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, load_only

from extensions import db
from models import (
    AppUser, Exercise, WorkoutTemplate, TemplateExercise, WorkoutSession,
    SessionExercise, SessionSet, PendingPush, SharedSession, MUSCLE_GROUPS,
)
from auth import login_required
from features.gym import stats
from features.gym.scope import (
    current_user_id, my_exercises, my_sessions, my_templates,
    owned_exercise, owned_session, owned_session_exercise, owned_set,
)
from .. import sharing
from ..seeding import _seeded_sets, _seeded_suggestion
from ._blueprint import gym_bp
from .helpers import (
    DEFAULT_REST_SECONDS, NON_MUSCLE_GROUPS, RECENT_SESSIONS, WEEKDAY_SHORT,
    _cancel_pending_push, _clean_muscle_group, _get_active_session,
    _to_float, _to_increment, _to_int, _username,
)
from .history import load_performed, performed_from_session, _session_rest_entries


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
        my_templates()
        .options(joinedload(WorkoutTemplate.exercises).joinedload(TemplateExercise.exercise))
        .order_by(WorkoutTemplate.name)
        .all()
    )
    routine_sessions = (
        my_sessions()
        .filter(WorkoutSession.finished_at.isnot(None), WorkoutSession.template_id.isnot(None))
        .all()
    )
    recent = (
        my_sessions()
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
           for row in my_exercises().with_entities(Exercise.muscle_group).distinct()}
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
        my_sessions()
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

    # Addressed to one person: an invite is only ever visible to its recipient.
    pending_invites = [
        {'shared_id': link.id,
         'leader_name': _username(link.leader_user_id),
         'session_name': (db.session.get(WorkoutSession, link.leader_session_id).name
                          or 'Workout')}
        for link in SharedSession.query.filter(
            SharedSession.follower_user_id == current_user_id(),
            SharedSession.accepted_at.is_(None),
            SharedSession.ended_at.is_(None)).all()
    ]

    return render_template(
        'gym/heute.html',
        now=now,
        active_session=active_session,
        # Start now offers push activation to a device that has none -- see the
        # notify-prompt in heute.html for why it moved out of the ⋮ sheet.
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
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
        pending_invites=pending_invites,
    )


@gym_bp.route('/gym/start', methods=['POST'])
@login_required
def gym_start():
    active_session = _get_active_session()
    if active_session:
        return redirect(url_for('gym.session_detail', session_id=active_session.id))

    template_id = request.form.get('template_id', type=int)
    name = request.form.get('name', '').strip() or None
    # Resolved before the session is built, and scoped to the caller: a
    # template_id belonging to someone else must not be seeded from *or*
    # stored, or the row keeps a link that update_template would later follow
    # back into a template this user cannot see.
    template = my_templates().filter_by(id=template_id).first() if template_id else None
    session_ = WorkoutSession(name=name, template_id=template.id if template else None,
                              user_id=current_user_id())

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


def _live_context(session_):
    """Exactly the Jinja names templates/gym/_session_queue.html reads that it
    does not define itself: the ordered, visible exercise list and which one
    is live.

    session_detail computes both anyway for its own purposes (suggestions,
    the tick strip, the rest lookup...), so this is a straight extraction --
    not a new computation -- moved here so gym_session_queue (the polling
    endpoint) renders from the identical rule instead of a second copy that
    could drift from the page's own.
    """
    # A replaced original is hidden from the active view, so its suggestion
    # would never be used -- skip computing it there. Visibility is derived
    # from replaces_id (already loaded on every row) rather than by touching
    # se.replaced_by, which would lazy-load a separate query per row.
    replaced_original_ids = {se.replaces_id for se in session_.exercises if se.replaces_id}
    visible_exercises = [se for se in session_.exercises if se.id not in replaced_original_ids]

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

    return {'visible_exercises': visible_exercises,
            'live_id': live_se.id if live_se else None}


@gym_bp.route('/gym/session/<int:session_id>')
@login_required
def session_detail(session_id):
    session_ = owned_session(session_id)

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
            my_sessions()
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
                my_sessions()
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
            # Same reason as set_rows above: the note-and-pain fields
            # (session_finished.html's "Sätze & Notizen" sheet)
            # post to gym_update_session_exercise_meta, which needs the real
            # SessionExercise id and its current notes/pain -- session_report's
            # own entries carry neither.
            entry['session_exercise'] = se
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
        # Rest measured rather than planned: the gap between consecutive sets, which
        # exists only for sessions logged since completed_at was added. None means
        # "no timestamps", which the template must render as silence, not as zero.
        rest_gaps = stats.rest_gaps(_session_rest_entries(session_))
        rest_taken_seconds = sum(actual for actual, _ in rest_gaps) or None
        return render_template('gym/session_finished.html', session=session_,
                               weekday_short=WEEKDAY_SHORT, rest_taken_seconds=rest_taken_seconds, **data)

    # visible_exercises and which one is live: see _live_context's own
    # docstring for why this is a call rather than the computation itself.
    live_ctx = _live_context(session_)
    visible_exercises = live_ctx['visible_exercises']
    live_se = next((se for se in visible_exercises if se.id == live_ctx['live_id']), None)
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
    ready_for_more = None
    if not session_.is_deload and live_se is not None:
        # Only the live exercise: the queue below is an overview, and seven
        # badges at once is decoration rather than a decision.
        ready_for_more = stats.ready_for_more(
            by_exercise.get(live_se.exercise_id, []), position=live_se.position)
        # "That weight went easy" is only advice while that weight is what you
        # are about to lift. Above it, the lifter has already acted -- or the
        # evidence is older than what the prefill found, and the nudge would
        # argue with the chips underneath it.
        planned_top = max((s.weight for s in live_se.sets), default=None)
        if ready_for_more and planned_top is not None and planned_top > ready_for_more['weight']:
            ready_for_more = None
    exercises = my_exercises().order_by(Exercise.name).all()

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

    # Everyone else with an account. Three people use this app; a picker is
    # the whole feature, and a friends list would be ceremony.
    partners = (AppUser.query
                .filter(AppUser.id != current_user_id())
                .order_by(AppUser.username)
                .all())
    shared_out = (SharedSession.query
                  .filter(SharedSession.leader_session_id == session_.id,
                          SharedSession.ended_at.is_(None))
                  .all())
    partner_status = [
        {'username': _username(link.follower_user_id),
         'accepted': link.accepted_at is not None}
        for link in shared_out
    ]
    # Whether THIS session is the FOLLOWER half of a live link -- gates the
    # polling script in session_detail.html. Only the follower's structure
    # ever changes out from under them, so only the follower needs to poll.
    # Deliberately NOT db.or_(leader_session_id == ..., follower_session_id
    # == ...): the leader's own structure_version is never bumped by
    # anything (only reconcile_follower bumps it, and only on the FOLLOWER's
    # session), so a leader polling sync.json would burn a request every 5s
    # forever for a version that can never change.
    session_is_shared = SharedSession.query.filter(
        SharedSession.ended_at.is_(None),
        SharedSession.accepted_at.isnot(None),
        SharedSession.follower_session_id == session_.id).first() is not None

    return render_template(
        'gym/session_detail.html',
        session=session_,
        live_se=live_se,
        **live_ctx,
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
        ready_for_more=ready_for_more,
        # Passed in rather than hardcoded in the template, so the badge's
        # copy cannot drift from the rule that decides it.
        min_full_reps=stats.DELOAD_REPS,
        default_plan_weight=stats.DEFAULT_PLAN_WEIGHT,
        default_plan_reps=stats.DEFAULT_PLAN_REPS,
        exercises=exercises,
        muscle_groups=MUSCLE_GROUPS,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
        # Scoped to the caller: PushSubscription.endpoint is a global table
        # (one row per browser installation, re-pointed on re-subscribe), so
        # "any row at all" would leak whether some OTHER user has push set up.
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
        partners=partners,
        partner_status=partner_status,
        session_is_shared=session_is_shared,
    )


@gym_bp.route('/gym/session/<int:session_id>/exercises/add', methods=['POST'])
@login_required
def gym_add_session_exercise(session_id):
    session_ = owned_session(session_id)

    exercise_id = request.form.get('exercise_id', type=int)
    new_name = request.form.get('new_exercise_name', '').strip()
    if not exercise_id and new_name:
        exercise = my_exercises().filter_by(name=new_name).first()
        if not exercise:
            exercise = Exercise(
                name=new_name,
                muscle_group=_clean_muscle_group(request.form.get('muscle_group', '')),
                default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
                user_id=current_user_id(),
            )
            db.session.add(exercise)
            db.session.flush()
        exercise_id = exercise.id

    if exercise_id:
        # exercise_id arrives from a submitted form, so it is attacker-chosen:
        # without this check a lifter could graft another user's exercise --
        # and its history, through _seeded_sets -- into their own session.
        exercise = owned_exercise(exercise_id)
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
        # with no history now seeds the default plan too, the same as every
        # other seeding path -- there is no longer an empty slot for a
        # deload to miss.
        session_exercise.sets.extend(
            _seeded_sets(session_, exercise_id, next_position))
        db.session.add(session_exercise)
        db.session.commit()
        sharing.propagate_structure(session_)

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
    original = owned_session_exercise(session_exercise_id)
    session_id = original.session_id

    exercise_id = request.form.get('exercise_id', type=int)
    new_name = request.form.get('new_exercise_name', '').strip()
    if not exercise_id and new_name:
        exercise = my_exercises().filter_by(name=new_name).first()
        if not exercise:
            exercise = Exercise(
                name=new_name,
                muscle_group=original.exercise.muscle_group,
                default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
                user_id=current_user_id(),
            )
            db.session.add(exercise)
            db.session.flush()
        exercise_id = exercise.id

    if exercise_id:
        # Attacker-chosen whenever it came from the form rather than from the
        # branch above that just created it. Re-checking the freshly created
        # one costs a primary-key lookup and keeps this to a single rule.
        owned_exercise(exercise_id)

    if exercise_id and exercise_id != original.exercise_id and not original.replaced_by:
        substitute = SessionExercise(
            session_id=session_id, exercise_id=exercise_id, position=original.position,
            rest_seconds=original.rest_seconds, replaces_id=original.id,
        )
        # Seeded the same way every other path that creates a SessionExercise
        # does (gym_add_session_exercise, gym_start from a template, un-skip,
        # reorder) -- see _seeded_sets. This route used to create the
        # substitute with zero sets, which is exactly the shape _live_context
        # treats as "live until one set lands, then finished": the first
        # logged set on the substitute both created and completed its list
        # and the screen advanced early. At the substitute's own position
        # (== original.position, above), so a substitute with its own history
        # seeds from that and one without gets the default plan -- the
        # ORIGINAL row and its already-logged sets are left untouched, only
        # the new substitute row is seeded.
        substitute.sets.extend(
            _seeded_sets(original.session, exercise_id, original.position))
        db.session.add(substitute)

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
    sharing.propagate_structure(original.session)

    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/rest', methods=['POST'])
@login_required
def gym_update_session_exercise_rest(session_exercise_id):
    session_exercise = owned_session_exercise(session_exercise_id)
    session_exercise.rest_seconds = _to_int(request.form.get('rest_seconds', ''))
    session_id = session_exercise.session_id
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/sessions/<int:session_id>/meta', methods=['POST'])
@login_required
def gym_update_session_meta(session_id):
    """Bodyweight and a note for this workout. Both optional, both editable
    at any point -- during the session, or weeks later from Verlauf. The
    start path deliberately does not ask for either: a field between "start"
    and the first set is a field you skip anyway."""
    session = owned_session(session_id)
    session.bodyweight_kg = _to_increment(request.form.get('bodyweight_kg', ''))
    session.notes = request.form.get('notes', '').strip() or None
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session.id))


@gym_bp.route('/gym/session-exercises/<int:session_exercise_id>/meta', methods=['POST'])
@login_required
def gym_update_session_exercise_meta(session_exercise_id):
    """A note and a twinge flag, for this exercise in this workout. Both
    belong to the session rather than the catalogue: "shoulder pinched
    today" is not a property of the machine."""
    session_exercise = owned_session_exercise(session_exercise_id)
    session_exercise.notes = request.form.get('notes', '').strip() or None
    session_exercise.pain = request.form.get('pain') == 'on'
    db.session.commit()
    return redirect(url_for('gym.session_detail',
                            session_id=session_exercise.session_id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/increment', methods=['POST'])
@login_required
def gym_update_exercise_increment(session_exercise_id):
    """Write the EXERCISE's increment from inside a running session.

    Reached from the per-exercise sheet, beside the rest field -- but unlike
    rest, which is genuinely per session, a loadable step is a property of the
    equipment and so lands on the Exercise itself and stays. Keyed on the
    SessionExercise regardless, because that is the id the sheet has and it
    keeps the redirect back to the workout trivial.

    @login_required only -- there is no separate admin gate to sit behind.
    owned_session_exercise already guarantees the session, and therefore the
    exercise it points at, belongs to the caller: the catalogue is per user
    now, so this is an ordinary write to a row the caller owns, no different
    from the rename/recategorise in gym_update_exercise.
    """
    session_exercise = owned_session_exercise(session_exercise_id)
    session_exercise.exercise.weight_increment = _to_increment(
        request.form.get('weight_increment', ''))
    session_id = session_exercise.session_id
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/sets/add', methods=['POST'])
@login_required
def gym_add_set(session_exercise_id):
    session_exercise = owned_session_exercise(session_exercise_id)

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
            completed_at=dt.datetime.utcnow(),
        )
        db.session.add(new_set)
        db.session.flush()
        _schedule_rest(new_set)
        db.session.commit()

    return redirect(url_for('gym.session_detail', session_id=session_exercise.session_id))


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/delete', methods=['POST'])
@login_required
def gym_delete_session_exercise(session_exercise_id):
    session_exercise = owned_session_exercise(session_exercise_id)
    session_id = session_exercise.session_id
    session_ = session_exercise.session
    # If the currently-resting set belongs to this exercise, clear the
    # reference first -- otherwise deleting it (cascades to its sets) would
    # violate the WorkoutSession.resting_set_id foreign key.
    if session_exercise.session.resting_set_id in [s.id for s in session_exercise.sets]:
        session_exercise.session.resting_set_id = None
        session_exercise.session.rest_ends_at = None
        _cancel_pending_push(session_exercise.session)
    # BEFORE the delete, not after: mirrors_id carries a database-level
    # ON DELETE SET NULL, so the moment this row is gone the database has
    # already erased the only marker saying which follower row mirrored it.
    # Reconciliation would have nothing left to key on, and a heuristic
    # recovery -- matching on exercise_id, say -- cannot tell an orphaned
    # mirror from a row the partner added on their own initiative, so it
    # would eventually delete their own work and the sets they logged on it.
    sharing.remove_mirrors_of(session_exercise)
    db.session.delete(session_exercise)
    db.session.commit()
    sharing.propagate_structure(session_)
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
    session_exercise = owned_session_exercise(session_exercise_id)
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
    sharing.propagate_structure(session_)
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/set/<int:set_id>/delete', methods=['POST'])
@login_required
def gym_delete_set(set_id):
    set_ = owned_set(set_id)
    session_ = set_.session_exercise.session
    session_id = session_.id
    if session_.resting_set_id == set_.id:
        session_.resting_set_id = None
        session_.rest_ends_at = None
        _cancel_pending_push(session_)
    db.session.delete(set_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_id))


def _propagate_default_correction(set_, weight, reps):
    """A hand-typed correction to a set that was still sitting on the
    invented default plan (3 sets at DEFAULT_PLAN_WEIGHT x DEFAULT_PLAN_REPS,
    see seeding._seeded_sets) carries forward to any LATER set of the same
    SessionExercise that is itself still untouched -- `completed` is False
    and `is_default_seeded` is still True.

    This is deliberately narrower than "always carry a weight change
    forward": the owner was asked and explicitly rejected that, because it
    would override a deliberate drop set or ramp-up on a normal templated
    workout. Restricting it to is_default_seeded siblings makes it fire only
    on the cold-start path this exists for -- a real history-seeded exercise
    is never touched (see test_correcting_a_history_seeded_set_does_not_propagate).

    Earlier sets, and any sibling the lifter has already hand-edited (its own
    is_default_seeded already cleared) or already completed, are left alone
    entirely -- only `weight`/`reps` was already established for `set_`
    before this widened to its neighbours, so the same "already logged, or
    already a real choice" guards apply to them too.

    `weight`/`reps` are passed in as None when that particular field did not
    change on `set_` -- e.g. correcting only the weight (the default reps of
    8 already being right) must not stomp a sibling's reps with the same
    unchanged 8 it already has.

    The propagated-to sibling has its OWN is_default_seeded cleared too: the
    correction is now the plan, not a guess. Leaving it set would mean a
    second, later correction elsewhere in the exercise keeps re-propagating
    past sets the lifter already silently accepted at the first corrected
    number -- which is exactly the always-carry-forward behaviour rejected
    above, just deferred by one set instead of skipped outright.
    """
    for sibling in set_.session_exercise.sets:
        if sibling.id == set_.id:
            continue
        if sibling.position <= set_.position:
            continue
        if sibling.completed or not sibling.is_default_seeded:
            continue
        if weight is not None:
            sibling.weight = weight
        if reps is not None:
            sibling.reps = reps
        sibling.is_default_seeded = False


def _apply_typed_weight_reps(set_):
    """Read weight/reps off the request form and write them onto `set_`,
    exactly as both weight/reps editors on the live screen have always done:
    an actual change clears `base_weight`/`base_reps` (a hand-typed value is
    ground truth, so a later deload-toggle must not overwrite it) and clears
    `is_default_seeded` (it was invented, not a real working weight -- a
    hand-typed number stops that being true). An unchanged value is just the
    form echoing what is already stored and must NOT count as an edit, or a
    completed-then-un-completed set would lose its way back to its own
    working weight.

    Shared by gym_toggle_set_complete and gym_update_set -- the two
    affordances session_detail.html renders for the same set (the confirm
    button's own fields, and the per-exercise sheet's editor) -- so this half
    of the logic cannot drift between them. What is NOT shared is each
    route's own decision about when to call _propagate_default_correction:
    see the comment at each call site for why that condition differs and
    must keep differing.

    Returns (was_default_seeded, weight_changed, reps_changed) -- read
    BEFORE the writes above, since was_default_seeded here is what the
    caller needs to know about `set_` as it arrived, not as it now stands.
    `set_.weight`/`set_.reps` already hold the new values on return, so a
    caller that wants to propagate reads them from `set_` directly rather
    than from a separate local.
    """
    was_default_seeded = set_.is_default_seeded
    weight = _to_float(request.form.get('weight', ''))
    reps = _to_int(request.form.get('reps', ''))
    weight_changed = False
    reps_changed = False
    if weight is not None:
        if weight != set_.weight:
            weight_changed = True
            set_.base_weight = None
            set_.is_default_seeded = False
        set_.weight = weight
    if reps is not None:
        if reps != set_.reps:
            reps_changed = True
            set_.base_reps = None
        set_.reps = reps
    return was_default_seeded, weight_changed, reps_changed


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
    set_ = owned_set(set_id)
    session_ = set_.session_exercise.session

    # See _apply_typed_weight_reps for why was_default_seeded has to be read
    # before this call rather than after: it clears the flag itself.
    was_default_seeded, weight_changed, reps_changed = _apply_typed_weight_reps(set_)

    wanted = request.form.get('completed')
    was_completed = set_.completed
    set_.completed = (wanted == '1') if wanted in ('0', '1') else (not set_.completed)
    # The stamp follows the flag in both directions. Leaving it behind on an
    # un-complete would make the next tick measure the wrong interval.
    set_.completed_at = dt.datetime.utcnow() if set_.completed else None

    if set_.completed and was_default_seeded and (weight_changed or reps_changed):
        # A correction to the invented default plan, being confirmed done --
        # carry it to the sets that are still sitting on that same untouched
        # default. `set_.completed` gates this route's trigger and NOT
        # gym_update_set's (see its own call site below) because this is the
        # route that decides completed/not -- an edit typed here but not yet
        # confirmed is exactly the drop-set-in-progress case propagation must
        # NOT fire on. See _propagate_default_correction for the rest of the
        # reasoning.
        _propagate_default_correction(
            set_, set_.weight if weight_changed else None, set_.reps if reps_changed else None)

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
    """Edit a set's weight/reps without touching `completed`. Works
    regardless of session.finished_at (a finished session's edit form is the
    quiet "Sätze & Notizen" disclosure in session_finished.html), but it is
    not exclusive to that page: session_detail.html's per-exercise sheet
    posts here too for a set on a still-live session, alongside
    gym_toggle_set_complete's own weight/reps fields on the same screen --
    two affordances for the same edit. They apply the edit itself
    identically (see _apply_typed_weight_reps), but propagation to sibling
    sets is gated differently in each -- see the comment on the trigger
    below for why, and the finished-session guard next to it for the one
    case where this route must still apply the edit but must NOT propagate."""
    set_ = owned_set(set_id)
    session_ = set_.session_exercise.session
    # See _apply_typed_weight_reps for why was_default_seeded has to be read
    # before this call rather than after: it clears the flag itself.
    was_default_seeded, weight_changed, reps_changed = _apply_typed_weight_reps(set_)

    # No `completed` gate here, unlike gym_toggle_set_complete's trigger --
    # this route never sets `completed` at all, so requiring it (as the
    # other route's comment once wrongly implied both routes should) would
    # make propagation never fire through this editor. Firing on the edit
    # alone is correct here: this form's whole point is a correction typed
    # after the fact, not a confirmation.
    #
    # But: only while the session is still live. A finished session's
    # "Sätze & Notizen" disclosure posts here too, and rewriting sibling
    # sets that were never performed inside an already-closed historical
    # record is wrong even though most readers filter on `completed` -- the
    # JSON export does not, and the cold-start propagation feature was
    # scoped to the live screen throughout. Correcting a typo on a finished
    # set must still update THAT set (the call to _apply_typed_weight_reps
    # above already did, unconditionally); only the fan-out to siblings
    # stops.
    if session_.finished_at is None and was_default_seeded and (weight_changed or reps_changed):
        # This is the OTHER route that can correct a still-pending default
        # set -- session_detail.html's sheet posts here, not just
        # gym_toggle_set_complete's confirm button. Without this, a
        # correction typed through this form both bypassed propagation AND
        # disabled the later one: is_default_seeded was already cleared
        # above, so was_default_seeded reads False the next time the lifter
        # confirms a sibling set on the live screen. See
        # _propagate_default_correction for the rest of the reasoning.
        _propagate_default_correction(
            set_, set_.weight if weight_changed else None, set_.reps if reps_changed else None)

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
    session_ = owned_session(session_id)
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
    sharing.propagate_structure(session_)
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
    session_ = owned_session(session_id)
    session_.rest_ends_at = None
    session_.resting_set_id = None
    _cancel_pending_push(session_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/session/<int:session_id>/finish', methods=['POST'])
@login_required
def gym_finish_session(session_id):
    session_ = owned_session(session_id)
    session_.finished_at = dt.datetime.utcnow()
    session_.rest_ends_at = None
    session_.resting_set_id = None
    # Finishing early (before a running rest timer naturally elapses) must
    # cancel its still-pending push -- otherwise the notifier daemon fires it
    # later for a workout that's already over.
    _cancel_pending_push(session_)
    # Whoever finishes first ends the sharing. The other trains on alone --
    # a workout must never be cut short by someone else's.
    sharing.end_links_for(session_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id, just_finished=1))


@gym_bp.route('/gym/session/<int:session_id>/sync.json')
@login_required
def gym_session_sync(session_id):
    """What the follower's page polls.

    Reads the caller's OWN session. Propagation is a write, so by the time this
    is asked the change is already in their rows -- there is no cross-user read
    on this path at all.
    """
    session_ = owned_session(session_id)
    shared = SharedSession.query.filter(
        SharedSession.ended_at.is_(None),
        SharedSession.accepted_at.isnot(None),
        db.or_(SharedSession.leader_session_id == session_.id,
               SharedSession.follower_session_id == session_.id)).first()
    return jsonify({'version': session_.structure_version or 0,
                    'shared': shared is not None})


@gym_bp.route('/gym/session/<int:session_id>/queue.html')
@login_required
def gym_session_queue(session_id):
    """The queue alone, for the polling swap.

    Rendered from the same partial the page uses, so the two cannot drift.
    """
    session_ = owned_session(session_id)
    return render_template('gym/_session_queue.html', **_live_context(session_))
