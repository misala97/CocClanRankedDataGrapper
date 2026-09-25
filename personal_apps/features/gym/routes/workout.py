"""The live workout: starting a session, the session screen, and every
mutation the screen performs.

This is the domain the React port replaces. `_live_context` is the seam --
it is what session_detail.html renders from today and what the JSON payload
will wrap, so the page and the endpoint cannot disagree about which exercise
is live.

Moved verbatim from the pre-split routes.py.
"""
import datetime as dt

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, load_only, selectinload

from extensions import db
from models import (
    AppUser, WorkoutTemplate, TemplateExercise, WorkoutSession,
    SessionExercise, SessionSet, PendingPush, SharedSession, MUSCLE_GROUPS,
)
from auth import login_required
from features.gym import art, plan, stats
from features.gym.library import BY_KEY, LIST_GROUPS, MOVEMENT_GROUP
from features.gym.schemas import FinishedPayload, HeutePayload, SessionDetailPayload
from features.gym.exercises import (
    REST_MAX_SECONDS, REST_NUDGE_SECONDS,
    exercise_or_404, library_exercises, search_text,
    setup as exercise_setup, setups as exercise_setups, touched_exercises,
    usage as exercise_usage,
)
from features.gym.scope import (
    current_user_id, my_sessions, my_templates,
    owned_session, owned_session_exercise, owned_set,
)
from .. import sharing
from ..locking import lock_sessions, lock_user
from ..seeding import (
    _deload_applies, _pick_session_exercises, _seed_source, _seeded_sets, _seeded_suggestion,
    missing_planned_sets, reseed_for_slot,
)
from ._blueprint import gym_bp
from .helpers import (
    NON_MUSCLE_GROUPS, ONBOARDING_WORKOUTS, RECENT_SESSIONS, WEEKDAY_SHORT, InvalidInput,
    _cancel_pending_push, _debrief_args, _discard_session, _finish_session,
    _get_active_session, _page_active_session, _refuse_live_write_if_finished,
    _refuse_structure_edit_if_finished, _settle_if_abandoned, _to_bodyweight, _to_client_key, _to_int, _to_name, _to_note,
    _to_reps, _to_rest_seconds, _to_weight, _was_discarded, _write_time,
    _username, _wants_json,
)
from .history import counts, done_sets, load_performed, performed_from_session, _session_rest_entries


def _template_exercises_from_session(session_):
    """Build ordered, deduped TemplateExercise rows from a session's current
    exercises.

    No rest is carried over (V3): the rest is the lifter's setting, and a
    routine holding a copy outvoted every later change of it -- "Eine für
    alle" would never have reached a workout started from a routine. A
    workout's own "Pause heute" is for that workout only.

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
        result.append(TemplateExercise(exercise_id=se.exercise_id, position=position))
        position += 1
    return result


def _locked_session_exercise(session_exercise_id, with_partners=False):
    """owned_session_exercise, holding its workout's structural lock (see
    locking.py). Read twice on purpose: once to learn which workout to lock,
    and again under the lock -- the request this one waited for may have been
    a second tap on "remove", and the row is then simply gone (404).

    `with_partners` also locks the session of every partner following this
    workout, for the one route that writes into theirs BEFORE its own commit
    (removing an exercise -- see sharing.remove_mirrors_of)."""
    session_id = owned_session_exercise(session_exercise_id).session_id
    partner_ids = ([link.follower_session_id
                    for link in sharing.active_links_led_by(session_id)]
                   if with_partners else [])
    lock_sessions([session_id, *partner_ids])
    return owned_session_exercise(session_exercise_id)


def _close_position_gaps(session_):
    """Renumber the session's slots 1..n, keeping their order.

    Slots are what seeding reads as a fatigue proxy and what the queue prints,
    so a hole in them is a lie in both: removing the second of five exercises
    left the last one claiming slot 5 of 4, and the next reorder -- even one
    that put a row back where it was -- then "moved" everything after the hole
    and re-seeded it.

    A substitute shares its slot with the hidden rows behind it, however long
    the chain, so they count as ONE slot and move together. Only a visible row
    is re-seeded: a replaced original is not on screen and its plan is not
    going to be lifted.
    """
    rows = sorted(session_.exercises, key=lambda se: (se.position, se.id))
    by_id = {se.id: se for se in rows}
    hidden_ids = {se.replaces_id for se in rows if se.replaces_id}

    def root_id(se):
        while se.replaces_id and se.replaces_id in by_id:
            se = by_id[se.replaces_id]
        return se.id

    slots = {}
    for se in rows:
        slots.setdefault(root_id(se), []).append(se)
    for number, members in enumerate(slots.values(), start=1):
        for se in members:
            old_position = se.position
            if old_position == number:
                continue
            se.position = number
            if se.id not in hidden_ids:
                reseed_for_slot(session_, se, old_position, number)


def _schedule_rest(session_set):
    """Start (or restart) the rest timer for this set's session, based on the
    exercise's configured rest time. Called whenever a set is confirmed done.

    Never on a finished workout: a set added from the debrief was lifted a
    while ago, and a countdown -- with its push -- for a workout that is over
    is the one thing gym_finish_session exists to cancel."""
    session_exercise = session_set.session_exercise
    if session_exercise.session.finished_at is not None:
        return
    session_ = session_exercise.session
    rest_seconds = session_exercise.rest_seconds
    if rest_seconds is None:
        rest_seconds = exercise_setup(session_.user_id, session_exercise.exercise).default_rest_seconds
    if not rest_seconds:
        # No rest after this one, but the last rest is over all the same: the
        # band must not go on counting up from a rest before this set.
        session_.rest_ends_at = None
        session_.resting_set_id = None
        _cancel_pending_push(session_)
        return
    # From the set's own stamp: the rest runs from the moment the set landed,
    # and its length reads back off the two stamps (_rest_total_seconds).
    started = session_set.completed_at or dt.datetime.utcnow()
    rest_ends_at = started + dt.timedelta(seconds=rest_seconds)
    session_.rest_ends_at = rest_ends_at
    session_.resting_set_id = session_set.id
    # Replace any still-pending push for this session rather than stacking
    # multiple -- a new completed set means a new (possibly shorter) rest period.
    _cancel_pending_push(session_)
    # A set the phone held while offline arrives with its own stamp, and its
    # rest may be over by then: the notifier sends a push due in the past at
    # once, for a rest nobody is waiting out (B6).
    if rest_ends_at > dt.datetime.utcnow():
        db.session.add(PendingPush(session_id=session_.id, fire_at=rest_ends_at))


def _rest_total_seconds(session_, setups):
    """How long the running rest is, for the bar that charges through it:
    from the set that started it to rest_ends_at.

    Read off the two stamps, because the end moves after the rest starts --
    "−15" and "+15" shift it -- while "Pause heute" changes the setting and
    leaves a countdown already running alone, so a total re-read from the
    setting made the bar jump. A set with no stamp falls back to the rest set
    on the exercise that owns it, which after an exercise's last set is not
    the one now live. `setups` covers every exercise of the session."""
    for se in session_.exercises:
        for set_ in se.sets:
            if set_.id != session_.resting_set_id:
                continue
            if set_.completed_at is not None:
                return max(0, round((session_.rest_ends_at - set_.completed_at).total_seconds()))
            return se.rest_seconds or setups[se.exercise_id].default_rest_seconds or 0
    return 0


def _as_routine(template, last_done, days_ago):
    """A routine as the Start page reads it: its name, its exercises in order,
    and when it was last trained."""
    ordered = sorted(template.exercises, key=lambda te: te.position)
    return {
        'template_id': template.id,
        'name': template.name,
        'exercises': [te.exercise.name for te in ordered],
        'exercise_ids': [te.exercise_id for te in ordered],
        'last_done': last_done,
        'days_ago': days_ago,
    }


def _heute_payload():
    """The whole Start page as a validated payload. Shared by the page render
    and by the template mutations' JSON answers (rename/delete), so an edit
    made from the page re-renders from exactly what a fresh load would show.
    Needs a request context: scope.py reads the session."""
    now = dt.datetime.utcnow()
    active_session = _page_active_session()

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
        | {exercise.muscle_group or stats.NO_GROUP_LABEL
           for exercise in touched_exercises(current_user_id())}
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

    # First run: the steps from an empty account to a routine on this page.
    # Counted off `performed` like everything above, so "1 Workout" here and
    # "Zuletzt heute" in the header are the same fact.
    onboarding = None
    if not templates and len(volume_by_session) < ONBOARDING_WORKOUTS:
        last = recent_sessions[0]['session'] if recent_sessions else None
        onboarding = {
            'workouts': len(volume_by_session),
            'last': last and {
                'session_id': last.id, 'name': last.name,
                'started_at': last.started_at, 'finished_at': last.finished_at,
                'exercises': sum(1 for row in performed if row.session_id == last.id),
            },
        }

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

    active_exercise = _live_exercise_name(active_session) if active_session else None

    return HeutePayload.model_validate({
            'now': now,
            'active_session_id': active_session.id if active_session else None,
            'active_session_name': active_session.name if active_session else None,
            'active_session_started_at': active_session.started_at if active_session else None,
            'active_session_exercise': active_exercise,
            'active_session_rest_ends_at': active_session.rest_ends_at if active_session else None,
            # Start offers push activation to a device that has none -- only
            # the browser knows whether THIS device is subscribed.
            'vapid_public_key': current_app.config.get('VAPID_PUBLIC_KEY'),
            'consistency': stats.consistency(list(session_started_at.values()), now),
            'routines': [_as_routine(r['template'], r['last_done'], r['days_ago'])
                         for r in stats.routine_memory(templates, routine_sessions, now)],
            'recent_sessions': [
                {'session_id': r['session'].id, 'name': r['session'].name,
                 'started_at': r['session'].started_at,
                 'finished_at': r['session'].finished_at,
                 'is_deload': r['session'].is_deload,
                 'volume': r['volume'], 'records': r['records']}
                for r in recent_sessions
            ],
            'stalls': stalls,
            'deload_suggestion': deload_suggestion,
            'balance': stats.muscle_group_volume(performed, catalogue_groups, now),
            'tonnage': tonnage,
            'tonnage_peak': max((week['volume'] for week in tonnage), default=0.0),
            'templates': [_as_routine(t, None, None) for t in templates],
            'pending_invites': pending_invites,
            'onboarding': onboarding,
        })


@gym_bp.route('/gym', strict_slashes=False)
@login_required
def gym_heute():
    return render_template(
        'gym/heute.html',
        payload_json=_heute_payload().model_dump(mode='json'),
    )


@gym_bp.route('/gym/start', methods=['POST'])
@login_required
def gym_start():
    # Checked and inserted under the lifter's lock: two starts at once -- two
    # tabs, two devices -- both saw no running workout and made two (G-091).
    # An abandoned workout is ended BEFORE the lock: ending it commits, and
    # the commit would release the lock (B4 review).
    _get_active_session()
    lock_user(current_user_id())
    active_session = _get_active_session()
    if active_session:
        return redirect(url_for('gym.session_detail', session_id=active_session.id))

    template_id = request.form.get('template_id', type=int)
    name = _to_name(request.form.get('name', '')) or None
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
        # The routine's plan, filled from history the first time it is
        # started (D2 P1) -- before the rows below are seeded by it.
        plan.fill_routine_plan(template, current_user_id())
        for i, te in enumerate(template.exercises, start=1):
            # No rest on the row: it follows the lifter's setting, read at
            # each set, so "Deine Pause" changed mid-workout counts from the
            # next set. A routine holds no rest to read (G-076).
            session_exercise = SessionExercise(exercise_id=te.exercise_id, position=i)
            session_exercise.sets.extend(_seeded_sets(session_, te.exercise_id, i))
            session_.exercises.append(session_exercise)

    db.session.add(session_)
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id))


def _load_rows(session_):
    """Every row of the workout with its sets and its exercise, in two
    queries, before anything walks them. Walked lazily, each row cost a query
    for its sets and one for its exercise -- two per exercise on every live
    payload, each set tick's included (walkthrough G-140).

    The rows land in the identity map, so session_.exercises and each row's
    .sets and .exercise read them from there -- for as long as the caller
    holds the list this returns: the map only keeps weak references, and a
    row nobody holds is gone again before session_.exercises is read."""
    return (SessionExercise.query
            .filter(SessionExercise.session_id == session_.id)
            .options(joinedload(SessionExercise.exercise), selectinload(SessionExercise.sets))
            .all())


def _live_context(session_, keep_started=False):
    """The ordered, visible exercise list and which one of them is live.

    `keep_started` is True for the follower half of a live shared workout --
    see the branch below for what it changes and why only there.

    session_detail computes both anyway for its own purposes (suggestions,
    the tick strip, the rest lookup...), so this is a straight extraction --
    not a new computation. It was extracted for the queue-polling endpoint,
    which the React port removed; it stays because _live_data still builds on
    it, and having one rule for "which exercise is live" is the point either
    way.
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
    if keep_started:
        # The follower half of a live shared workout: whatever they have
        # STARTED stays live until it is finished or skipped. They are
        # physically at that exercise, and the order is not theirs -- so the
        # leader dragging another row to the top used to swap this panel
        # under their thumb, and the next "Satz geschafft" logged a set on a
        # lift they never touched. Alone, or leading, the rule below is left
        # as it was: there the drag is the lifter's own instruction, and
        # pulling another exercise above a started one is how you step away
        # from a busy machine. Most recently logged wins if there are two.
        started = [
            se for se in visible_exercises
            if not se.skipped
            and any(s.completed for s in se.sets)
            and not all(s.completed for s in se.sets)]
        if started:
            live_se = max(started, key=lambda se: max(
                (s.completed_at or dt.datetime.min) for s in se.sets if s.completed))
    if live_se is None:
        for se in visible_exercises:
            done = sum(1 for s in se.sets if s.completed)
            if not se.skipped and not (se.sets and done == len(se.sets)):
                live_se = se
                break
    if live_se is None:
        # Everything is logged: the last exercise that still counts stays live,
        # so "Satz geschafft" appends to it. Never a skipped one -- skipping the
        # last exercise and finishing the rest used to bring it back as "Jetzt"
        # with an empty plan, and a set logged there counted nowhere. With
        # everything skipped nothing is live, and the panel says so.
        counting = [se for se in visible_exercises if not se.skipped]
        if counting:
            live_se = counting[-1]

    return {'visible_exercises': visible_exercises,
            'live_id': live_se.id if live_se else None}


def _live_exercise_name(session_):
    """What the live screen has live, by name, for the lines that say what
    the lifter was on: Heute's card and the strip every other gym page
    carries (_nav.html). The screen's own rule, the follower's "keep started"
    included -- the strip's copy of it in Jinja named another exercise than
    the screen for a partner, and paid a query per row for the sets
    (walkthrough G-143). None while nothing is live."""
    held_rows = _load_rows(session_)  # noqa: F841 -- held, not read: see _load_rows
    live_ctx = _live_context(session_, keep_started=sharing.is_live_follower(session_.id))
    live_se = next((se for se in live_ctx['visible_exercises']
                    if se.id == live_ctx['live_id']), None)
    return live_se.exercise.name if live_se else None


@gym_bp.context_processor
def _inject_live_exercise_name():
    """For the resume strip, asked only on the pages that show it."""
    return {'gym_live_exercise_name': _live_exercise_name}


def _replaced_done(session_, visible_exercises):
    """What the hidden originals behind each visible row did, as {se.id:
    {'sets': n, 'volume': kg}} -- zero where nothing was replaced.

    A substitute can itself be substituted, so the walk follows replaces_id
    all the way down. Each original's volume is its own exercise's: the swap
    may have been from a two-arm movement to a one-arm one.
    """
    by_id = {se.id: se for se in session_.exercises}
    carried = {}
    for se in visible_exercises:
        sets = volume = 0
        hidden = by_id.get(se.replaces_id)
        while hidden is not None:
            for s in hidden.sets:
                if counts(s):
                    sets += 1
                    volume += stats.set_volume(s.weight, s.reps, hidden.exercise.is_unilateral)
            hidden = by_id.get(hidden.replaces_id)
        carried[se.id] = {'sets': sets, 'volume': volume}
    return carried


def _typed_bests(history, session_):
    """The heaviest weight and the most reps each exercise has seen, as
    {exercise_id: {'weight', 'reps'}}: past twice either, a typed number gets
    a "Sicher?" before it is kept (Q5, G-070) -- a fat-fingered 9999 kg used
    to stay the record for good.

    From the lifter's other finished workouts (`history`, this workout's own
    rows left out), then raised by this workout's counted sets: a jump the
    lifter already said yes to is not asked about again. Only raised, never
    set -- with no history the first set of the day, a 20 kg warm-up, was the
    bar the 50 after it was asked about (B7 review). No history, no question.
    """
    bests = {}
    for row in history:
        if row.session_id == session_.id:
            continue
        for weight, reps in row.sets:
            best = bests.setdefault(row.exercise_id, {'weight': 0.0, 'reps': 0})
            best['weight'] = max(best['weight'], weight)
            best['reps'] = max(best['reps'], reps)
    for se in session_.exercises:
        best = bests.get(se.exercise_id)
        if best is None:
            continue
        for s in se.sets:
            if counts(s):
                best['weight'] = max(best['weight'], s.weight)
                best['reps'] = max(best['reps'], s.reps)
    return bests


def _live_data(session_, catalogue=True):
    """Every value session_detail.html renders from, ORM objects included.

    Split out so _session_payload can serialize this same computation
    rather than repeat it: the page and the JSON endpoint must not be
    able to disagree about which exercise is live.

    `catalogue`: whether the add sheet's list is wanted (see _session_payload).
    """
    # visible_exercises and which one is live: see _live_context's own
    # docstring for why this is a call rather than the computation itself.
    # Whether THIS session is the FOLLOWER half of a live link. Decides which
    # exercise is live (_live_context), marks the shared rows, and gates the
    # page's poll: only the follower's structure ever changes out from under
    # them, so only the follower needs to ask. Deliberately NOT "either half":
    # the leader's own structure_version is never bumped by anything, so a
    # leader polling sync.json would burn a request every 5s forever for a
    # version that can never change.
    session_is_shared = sharing.is_live_follower(session_.id)
    held_rows = _load_rows(session_)  # noqa: F841 -- held, not read: see _load_rows
    live_ctx = _live_context(session_, keep_started=session_is_shared)
    visible_exercises = live_ctx['visible_exercises']
    live_se = next((se for se in visible_exercises if se.id == live_ctx['live_id']), None)
    # This lifter's step, rest and stack stops for every exercise in the session.
    setups = exercise_setups(session_.user_id, [se.exercise for se in session_.exercises])
    # One history pick per exercise, read twice: for the numbers the steppers
    # pre-fill with, and for the line that says where those numbers came from.
    # All of them in one query (G-140).
    batch = _pick_session_exercises([(se.exercise_id, se.position) for se in visible_exercises],
                                    exclude_session_id=session_.id)
    picks = {se.id: batch[(se.exercise_id, se.position)] for se in visible_exercises}
    suggestions = {se.id: _seeded_suggestion(session_, se.exercise, se.position,
                                             picked=picks[se.id],
                                             setup=setups[se.exercise_id])
                   for se in visible_exercises}
    seed_sources = {se.id: _seed_source(picks[se.id]) for se in visible_exercises}
    history = load_performed(exercise_ids=[se.exercise_id for se in visible_exercises])
    # The workouts BEFORE this one: the bar every set here is judged against
    # (D3). "Every other finished workout" let one finished later -- a
    # partner's, one entered for an earlier day -- judge this one.
    by_exercise = {}
    for row in stats.earlier_rows(history, session_.started_at, session_.id):
        by_exercise.setdefault(row.exercise_id, []).append(row)
    bests = _typed_bests(history, session_)
    stagnation_counts = {}
    record_set_ids = set()
    record_details = {}
    for se in visible_exercises:
        prior = by_exercise.get(se.exercise_id, [])
        # A record is a record, deload or not (D3), and the flare says so the
        # instant the set is confirmed -- the same judgement the debrief's
        # records make, per set. One judgement, two outputs: the ids the chips
        # read, and what each record beat, for the takeover to say.
        record_today = False
        for s in se.sets:
            if not counts(s):
                continue
            detail = stats.record_detail(s.weight, s.reps, prior)
            if detail is None:
                continue
            record_set_ids.add(s.id)
            record_details[s.id] = detail
            record_today = True
        # A stall is a progress judgement, and a deload workout is no attempt
        # at progress: a "go heavier" nudge is wrong advice beside
        # deliberately reduced weights. A record today has ended it: the card
        # said "Stagniert" beside "Rekord" (M5 mockup, 09-24).
        if not session_.is_deload and not record_today:
            count = stats.sessions_since_pr(prior)
            if count is not None and count >= stats.STAGNATION_THRESHOLD:
                stagnation_counts[se.id] = count
    # What to lift, set by set (D2 P1, G-035): double progression from the
    # last workout of the exercise -- "+1 rep each time". Not from the seed
    # pick, the best e1RM of four weeks: after a step up in weight the
    # lighter sets never beat it, and the card asked for the same step up
    # workout after workout (B5 review). The one answer to "what do I lift":
    # the "Bereit" line and the stall line's own step-up said it twice more,
    # and could disagree. Said, never seeded, like they were. None in a
    # deload: a light week aims at nothing.
    routine = plan.routine_rows(session_)
    next_targets = {}
    if not session_.is_deload:
        for se in visible_exercises:
            last = picks[se.id].newest
            if last is None:
                continue
            setup = setups[se.exercise_id]
            earlier = sorted(by_exercise.get(se.exercise_id, []), key=stats.session_order,
                             reverse=True)
            target = plan.target_for(
                se, routine, list(done_sets(last)),
                [row.sets for row in earlier if not row.is_deload],
                stats.resolve_increment(setup.weight_increment, se.exercise.is_unilateral),
                setup.stack_kg)
            if target:
                next_targets[se.id] = target

    # D4: a deload marked after the first set only labels the workout, and
    # nothing rescales mid-workout (08-12 rule) -- so an exercise not started
    # yet says what the deload would have planned: its working weight, the
    # heaviest set of the workout it was seeded from, taken down as seeding
    # takes it down (_seeded_sets).
    deload_hints = {}
    if session_.is_deload and session_.deload_pct and not _deload_applies(session_):
        for se in visible_exercises:
            picked = picks[se.id][0]
            if picked is None or se.skipped or any(counts(s) for s in se.sets):
                continue
            top = max(weight for weight, _ in done_sets(picked))
            if top <= 0:
                continue
            setup = setups[se.exercise_id]
            deload_hints[se.id] = stats.deload_weight(
                top, session_.deload_pct,
                stats.resolve_increment(setup.weight_increment, se.exercise.is_unilateral),
                stack_kg=setup.stack_kg)
    # Where the sheet's "Routine" steppers start (D2 P1): the plan the
    # workout's routine keeps for each exercise it holds -- the lifter's own
    # routine only. A substitute is not in it and has none -- not even when
    # its exercise has a row of its own elsewhere in the routine: that row is
    # another slot's plan.
    routine_plans = {}
    if session_.template is not None and session_.template.user_id == session_.user_id:
        slots = [(se, routine.get(se.exercise_id)) for se in visible_exercises
                 if se.replaces_id is None and se.exercise_id in routine]
        plans = plan.row_plans([row for _, row in slots], session_.user_id, session_.template_id)
        for (se, _), (sets, rep_min, rep_max) in zip(slots, plans):
            routine_plans[se.id] = {'sets': sets, 'rep_min': rep_min, 'rep_max': rep_max}
    # The exercises this lifter meets for the first time: no history to plan
    # from -- so _seeded_sets planned them blank -- and nothing of them logged
    # in this workout yet either. The live screen marks these "Erstes Mal".
    logged_here = {se.exercise_id for se in session_.exercises
                   if any(counts(s) for s in se.sets)}
    first_rows = [se for se in visible_exercises
                  if picks[se.id][0] is None and se.exercise_id not in logged_here]
    # The list and what the owner of this session does with it -- the add
    # sheet leads with it. The session's lifter, not the request's: the same
    # rule as their setups. Only read when the payload carries the list or a
    # first time needs the lifter's other variants.
    exercises, usage, usage_now = [], {}, dt.datetime.utcnow()
    if catalogue or first_rows:
        exercises = library_exercises()
        usage = exercise_usage(session_.user_id, usage_now)
    first_time = _first_time_refs(first_rows, exercises, usage)

    # One tick per set in the whole workout, in order, so the strip reads as
    # the session filling up rather than as a chart. 'now' is the single set
    # about to be performed -- the same set the steppers are bound to.
    #
    # What was done is counts() (Q1), on every row: a set lifted before its
    # exercise was skipped, or before it was replaced, was lifted all the
    # same. The count used to leave both out while the volume kept the
    # skipped one, and the debrief, Heute and Statistik each had a third
    # answer (G-064). A replaced original is hidden, so its done sets ride on
    # the substitute that took its slot, ahead of the substitute's own.
    replaced_done = _replaced_done(session_, visible_exercises)
    sets_done = sets_total = 0
    tick_states = []
    next_set_id = None
    if live_se is not None:
        next_set_id = next((s.id for s in live_se.sets if not s.completed), None)
    for se in visible_exercises:
        carried = replaced_done[se.id]['sets']
        sets_done += carried
        sets_total += carried
        tick_states.extend(['done'] * carried)
        for s in se.sets:
            if counts(s):
                sets_done += 1
                sets_total += 1
                tick_states.append('done')
            elif se.skipped or s.completed:
                # Skipped: its open sets are not going to be lifted. Done but
                # no reps (a legacy row; G-038): not a set.
                continue
            else:
                sets_total += 1
                tick_states.append('now' if s.id == next_set_id else 'open')

    session_volume = sum(
        stats.set_volume(s.weight, s.reps, se.exercise.is_unilateral)
        for se in visible_exercises for s in se.sets if counts(s)
    ) + sum(carry['volume'] for carry in replaced_done.values())

    resting = bool(session_.rest_ends_at and session_.rest_ends_at > dt.datetime.utcnow())
    rest_total_seconds = _rest_total_seconds(session_, setups) if resting else 0

    # Everyone else with an account. Three people use this app; a picker is
    # the whole feature, and a friends list would be ceremony. Nobody for a
    # follower: the invite is the leader's (G-085, gym_invite_partner).
    partners = [] if session_is_shared else (AppUser.query
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

    return dict(
        session=session_,
        live_se=live_se,
        **live_ctx,
        # Resolved here, not in Jinja: the template must never re-implement the
        # fallback, or the two copies drift the moment DEFAULT_INCREMENT moves.
        live_increment=stats.resolve_increment(
            setups[live_se.exercise_id].weight_increment, live_se.exercise.is_unilateral,
        ) if live_se else stats.resolve_increment(None, False),
        live_floor=_weight_floor(setups[live_se.exercise_id], live_se.exercise) if live_se else None,
        live_index=(visible_exercises.index(live_se) + 1) if live_se else 0,
        tick_states=tick_states,
        sets_done=sets_done,
        sets_total=sets_total,
        sets_open=sets_total - sets_done,
        session_volume=session_volume,
        replaced_done=replaced_done,
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
        seed_sources=seed_sources,
        stagnation_counts=stagnation_counts,
        next_targets=next_targets,
        deload_hints=deload_hints,
        routine_plans=routine_plans,
        bests=bests,
        record_set_ids=record_set_ids,
        record_details=record_details,
        first_time=first_time,
        exercises=exercises,
        usage=usage,
        usage_now=usage_now,
        catalogue=catalogue,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY'),
        # Scoped to the caller: PushSubscription.endpoint is a global table
        # (one row per browser installation, re-pointed on re-subscribe), so
        # "any row at all" would leak whether some OTHER user has push set up.
        # has_completed_set: the deload toggle's rule (session_admin), which
        # is counts() like every other "was anything done".
        has_completed_set=any(counts(s) for se in session_.exercises for s in se.sets),
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
        setups=setups,
    )


def _session_payload(session_, catalogue=True):
    """_live_data as a validated, JSON-safe payload.

    Fields are listed explicitly rather than dumping ORM rows. extra='forbid'
    on the schema then means a new database column cannot silently widen the
    wire format, which is the whole point of the schema being a mirror.

    Three conversions are not cosmetic. record_set_ids is a set in _live_data
    and json.dumps cannot serialize one. suggestions and stagnation_counts are
    keyed by SessionExercise.id, and record_details by Set.id -- all ints, and
    JSON object keys are always strings, so doing it here rather than letting
    Pydantic coerce keeps the client contract explicit.

    `catalogue=False` leaves the add sheet's list out (None), for a write's
    answer: see SessionDetailPayload.exercises.
    """
    data = _live_data(session_, catalogue)
    row = data['session']

    def as_exercise(se):
        setup = data['setups'][se.exercise_id]
        return {
            'id': se.id,
            'exercise_id': se.exercise_id,
            'name': se.exercise.name,
            'muscle_group': se.exercise.muscle_group,
            'position': se.position,
            'skipped': se.skipped,
            # The leader's structure, carried here by a LIVE link: the follower
            # can skip or substitute it, but not remove it. False for an
            # exercise they added themselves, and for every row once the link
            # has ended -- the session is fully theirs again from then on.
            'mirrored': data['session_is_shared'] and se.mirrors_id is not None,
            'is_unilateral': se.exercise.is_unilateral,
            'rest_seconds': se.rest_seconds,
            'rest_setting': setup.default_rest_seconds,
            'rest_setting_mine': ('default_rest_seconds' in setup.changed
                                  or setup.rest_for_all is not None),
            # Resolved, never raw: the fallback lives in stats and a second
            # copy would drift the moment DEFAULT_INCREMENT moves.
            'increment': stats.resolve_increment(setup.weight_increment, se.exercise.is_unilateral),
            # live_floor for this row: offline, the screen moves on to the
            # next exercise by itself (B6) and needs its floor to do it.
            'floor': _weight_floor(setup, se.exercise),
            'notes': se.notes,
            'pain': se.pain,
            'best': data['bests'].get(se.exercise_id),
            'picture': art.picture_url(se.exercise.library_key),
            # The done sets of the hidden originals this row replaced, so the
            # client's retally can count them in place (Q1).
            'replaced_sets_done': data['replaced_done'][se.id]['sets'],
            'replaced_volume': data['replaced_done'][se.id]['volume'],
            # Removed, a substitute brings its original back: the screen
            # cannot draw that row, so it does not draw the removal at all.
            'is_substitute': se.replaces_id is not None,
            'sets': [{
                'id': s.id, 'weight': s.weight, 'reps': s.reps,
                'completed': s.completed, 'base_weight': s.base_weight,
                'key': s.client_key,
            } for s in se.sets],
        }

    return SessionDetailPayload.model_validate({
        'session': {
            'id': row.id,
            'name': row.name,
            'started_at': row.started_at,
            'finished_at': row.finished_at,
            'is_deload': row.is_deload,
            'deload_pct': row.deload_pct,
            'rest_ends_at': row.rest_ends_at,
            'resting_set_id': row.resting_set_id,
            'template_id': row.template_id,
            'template_name': row.template.name if row.template else None,
            'bodyweight_kg': row.bodyweight_kg,
            'notes': row.notes,
            'structure_version': row.structure_version,
        },
        'visible_exercises': [as_exercise(se) for se in data['visible_exercises']],
        'live_id': data['live_id'],
        'live_index': data['live_index'],
        'live_increment': data['live_increment'],
        'live_floor': data['live_floor'],
        'tick_states': data['tick_states'],
        'sets_done': data['sets_done'],
        'sets_total': data['sets_total'],
        'sets_open': data['sets_open'],
        'session_volume': data['session_volume'],
        'resting': data['resting'],
        'rest_total_seconds': data['rest_total_seconds'],
        'suggestions': {str(k): v for k, v in data['suggestions'].items()},
        'seed_sources': {str(k): v for k, v in data['seed_sources'].items()},
        'stagnation_counts': {str(k): v for k, v in data['stagnation_counts'].items()},
        'next_targets': {str(k): v for k, v in data['next_targets'].items()},
        'deload_hints': {str(k): v for k, v in data['deload_hints'].items()},
        'routine_plans': {str(k): v for k, v in data['routine_plans'].items()},
        'record_set_ids': sorted(data['record_set_ids']),
        'record_details': {str(k): v for k, v in data['record_details'].items()},
        'first_time': {str(k): v for k, v in data['first_time'].items()},
        'exercises': ([_catalogue_entry(e, data['usage'].get(e.id), data['usage_now'])
                       for e in data['exercises']] if data['catalogue'] else None),
        'list_groups': list(LIST_GROUPS) if data['catalogue'] else None,
        'vapid_public_key': data['vapid_public_key'],
        'has_completed_set': data['has_completed_set'],
        'deload_applied': data['deload_applied'],
        'deload_pcts': list(data['deload_pcts']),
        'deload_default_pct': data['deload_default_pct'],
        'partners': [
            {'id': p.id, 'username': p.username} for p in data['partners']
        ],
        'partner_status': data['partner_status'],
        'session_is_shared': data['session_is_shared'],
    })


def _catalogue_entry(exercise, used, now):
    """One row of the add sheet's list: the exercise, the movement it is a
    variant of, and what this lifter has done with it (`used`, an
    exercises.Usage, or None for never)."""
    entry = BY_KEY[exercise.library_key]
    return {
        'id': exercise.id, 'name': exercise.name, 'muscle_group': exercise.muscle_group,
        'search': search_text(exercise),
        'movement': entry.movement, 'label': entry.label,
        'movement_group': MOVEMENT_GROUP[entry.movement],
        'workouts': used.workouts if used else 0,
        'days_ago': stats.calendar_days_between(used.last_done, now) if used else None,
        'rank': used.rank if used else None,
        'common': used.common if used else False,
    }


def _first_time_refs(rows, exercises, usage):
    """{SessionExercise.id: [VariantRef dicts]} for `rows`, the exercises the
    lifter meets for the first time. Each gets up to two of the lifter's other
    variants of the same movement, most-done first (usage rank), with the top
    set of the latest workout that had them. A deload's numbers are
    deliberately light, so those workouts do not count; a variant done only in
    a deload gives way to the next one.

    Information only -- another variant's numbers are not this one's, so the
    screen shows them and never plans with them."""
    if not rows:
        return {}
    by_movement = {}
    for exercise in exercises:
        by_movement.setdefault(BY_KEY[exercise.library_key].movement, []).append(exercise)
    done = {}
    for se in rows:
        entry = BY_KEY.get(se.exercise.library_key)
        variants = by_movement.get(entry.movement, []) if entry else []
        done[se.id] = sorted((e for e in variants if e.id != se.exercise_id and e.id in usage),
                             key=lambda e: usage[e.id].rank)
    latest = {}
    wanted = sorted({e.id for variants in done.values() for e in variants})
    if wanted:
        # Oldest first, so the last row kept per exercise is its latest.
        for row in load_performed(exercise_ids=wanted):
            if not row.is_deload:
                latest[row.exercise_id] = row
    refs = {}
    for se_id, variants in done.items():
        refs[se_id] = []
        for exercise in variants:
            row = latest.get(exercise.id)
            if row is None:
                continue
            weight, reps = max(row.sets)
            refs[se_id].append({'label': BY_KEY[exercise.library_key].label,
                                'weight': weight, 'reps': reps,
                                'per_side': exercise.is_unilateral})
            if len(refs[se_id]) == 2:
                break
    return refs


def _weight_floor(setup, exercise):
    """Where a blank kg stepper's "+" lands: the empty bar where the lift has
    one, the lightest stop of a known stack, else one step up from nothing."""
    if setup.bar_weight:
        return setup.bar_weight
    if setup.stack_kg:
        return min(setup.stack_kg)
    return stats.resolve_increment(setup.weight_increment, exercise.is_unilateral)


def _mutation_response(session_, endpoint, **values):
    """JSON for the island, the original redirect for a plain form post.

    Negotiated on the existing URL rather than served from a parallel /json
    route: each of these routes carries an ownership check, a mutation and in
    several cases a propagation rule, and duplicating a route to change only
    its return type duplicates all of that. The 2a split exists because that
    kind of duplication already drifted once at file scale.

    The negotiation rule itself lives in helpers._wants_json -- the template
    mutations on Heute answer through it too.
    """
    if _wants_json():
        # The island that asked gets the payload for the page it is: a
        # correction saved from the debrief re-renders the debrief, not the
        # live screen's shape wearing a finished_at.
        if session_.finished_at:
            return jsonify(_finished_payload(session_).model_dump(mode='json'))
        # Without the add sheet's list when the island says it keeps its own
        # (session/api.ts, from the page or detail.json -- G-140). A page
        # from before that client, open across a deploy, reads the list off
        # every answer and would come apart without it: it still gets it.
        if request.headers.get('X-Gym-Catalogue') == 'kept':
            return jsonify(_session_payload(session_, catalogue=False)
                           .model_dump(mode='json', exclude={'exercises', 'list_groups'}))
        return jsonify(_session_payload(session_).model_dump(mode='json'))
    return redirect(url_for(endpoint, **values))


@gym_bp.route('/gym/session/<int:session_id>/detail.json')
@login_required
def gym_session_detail_json(session_id):
    """The live workout as JSON.

    Distinct from gym_session_sync, which answers only "has the structure
    changed" for the follower's poll. This is the whole screen.
    """
    session_ = owned_session(session_id)
    return jsonify(_session_payload(session_).model_dump(mode='json'))


def _finished_payload(session_):
    """The debrief as a validated payload -- session_report plus everything it
    structurally cannot know (real set ids, the session's own deload state,
    measured rest). Shared by the page render and by _mutation_response, so a
    correction saved from the finished page answers with the same shape the
    page was mounted from.

    Re-queries with eager loads regardless of how `session_` arrived:
    performed_from_session walks se.sets and se.exercise per row, both lazy --
    21 queries on a 7-exercise session without this.

    `just_finished` reads the request args, so it is False on every mutation
    POST; the island preserves its own flag across payload swaps because the
    flare celebrates the visit, not the data.
    """
    # The finished workout is one page now (spec 6.5): build the report
    # and hand off to session_finished.html instead of session_detail.html.
    #
    # Eager-loaded first. performed_from_session walks se.sets and
    # se.exercise per row, both lazy -- 21 queries on a 7-exercise session.
    session_ = (
        my_sessions()
        .options(
            joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise),
            joinedload(WorkoutSession.exercises).joinedload(SessionExercise.sets),
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
    # session_.exercises -- every row with a set that counts, a replaced-away
    # original included (Q1). Re-deriving that exact filter and zipping
    # lines each entry back up with its real SessionExercise.
    reported_session_exercises = [se for se in session_.exercises if done_sets(se)]
    # Seeded before the zip: the template guarded on the presence of these
    # keys, and the payload has to carry them either way rather than let a
    # short zip drop a field the contract requires.
    for entry in data['exercises']:
        entry['set_rows'] = []
        entry['session_exercise_id'] = None
        entry['notes'] = None
        entry['pain'] = False
    # The rest of the workout: rows that ran but carry nothing logged. The
    # correction sheet offers them an add row, so a set lost to a flaky
    # connection or never ticked can still be entered after finishing --
    # otherwise the only exercises it could correct were the ones already
    # right. A replaced-away original with nothing done stays out: it was
    # swapped before it was lifted. From replaces_id, already loaded on
    # every row, like _live_context -- se.replaced_by would lazy-load a query
    # per row.
    replaced_ids = {se.replaces_id for se in session_.exercises if se.replaces_id}
    # "Nachtragen" and a correction are typed numbers too, and counted the
    # moment they land: the same "Sicher?" as the live screen's (Q5, B7
    # review). `history` above holds only the exercises with a counted set.
    bests = _typed_bests(
        load_performed(exercise_ids=[se.exercise_id for se in session_.exercises]), session_)
    data['unlogged'] = [
        {'session_exercise_id': se.id, 'name': se.exercise.name,
         'best': bests.get(se.exercise_id)}
        for se in sorted(session_.exercises, key=lambda row: row.position)
        if se.id not in replaced_ids and not done_sets(se)
    ]
    for entry in data['exercises']:
        entry['best'] = bests.get(entry['exercise_id'])
    for entry, se in zip(data['exercises'], reported_session_exercises):
        entry['set_rows'] = [{'id': s.id, 'weight': s.weight, 'reps': s.reps}
                             for s in se.sets if counts(s)]
        # Same reason as set_rows above: the note-and-pain fields
        # (the debrief's "Sätze & Notizen" sheet) post to
        # gym_update_session_exercise_meta, which needs the real
        # SessionExercise id and its current notes/pain -- session_report's
        # own entries carry neither.
        entry['session_exercise_id'] = se.id
        entry['notes'] = se.notes
        entry['pain'] = se.pain
    # session_report only sees PerformedExercise rows, which do not carry
    # the percentage -- it belongs to the session row, and is carried there.
    data.pop('deload_pct')
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
    # Gold is a record SET: its own e1RM beat the best of every workout
    # before this one (D3) -- the live flare's judgement, set by set, so the
    # strip lights exactly the sets that flared. It used to gild the first
    # set matching a weight record's number, found by exercise name.
    prior = {}
    for row in stats.earlier_rows(history, session_.started_at, session_.id):
        prior.setdefault(row.exercise_id, []).append(row)
    tick_states = []
    for entry in data['exercises']:
        bar = prior.get(entry['exercise_id'], [])
        for set_row in entry['set_rows']:
            is_record = stats.record_detail(set_row['weight'], set_row['reps'], bar) is not None
            tick_states.append('record' if is_record else 'done')
    data['tick_states'] = tick_states
    # Measured pace: the average gap between consecutive sets, which exists
    # only for sessions logged since completed_at was added. A pace, not a
    # rest total: each gap runs from one confirm to the next, so it holds the
    # next set itself -- summed, it read "107 min, davon 96 min Pause" as if
    # nine tenths of the workout had been spent sitting. None means "no
    # timestamps", which the page renders as silence, not as zero.
    rest_gaps = stats.rest_gaps(_session_rest_entries(session_))
    data['set_pace_seconds'] = (
        round(sum(actual for actual, _ in rest_gaps) / len(rest_gaps)) if rest_gaps else None)
    data['weekday_short'] = list(WEEKDAY_SHORT)
    # Reading a three-week-old session from Verlauf is not celebrating, so
    # the flare only fires on arrival. A query argument, not state -- the
    # redirect that lands here is the only thing that sets it.
    data['just_finished'] = request.args.get('just_finished') is not None
    # The update prompt's diff, both halves server-computed. "Before" is the
    # template's current list; "after" comes from the SAME function
    # gym_update_template writes with, so the preview cannot drift from the
    # write -- and it is NOT the performed list: skipped and zero-set slots
    # go into a template, substitutes never do.
    if session_.template:
        data['template_exercises'] = [
            te.exercise.name for te in session_.template.exercises]
        names_by_id = {se.exercise_id: se.exercise.name for se in session_.exercises}
        data['template_next_exercises'] = [
            names_by_id[te.exercise_id]
            for te in _template_exercises_from_session(session_)]
    else:
        data['template_exercises'] = None
        data['template_next_exercises'] = None
    data['session'] = {
        'id': session_.id, 'name': session_.name,
        'started_at': session_.started_at, 'finished_at': session_.finished_at,
        'auto_finished': session_.auto_finished,
        'is_deload': session_.is_deload, 'deload_pct': session_.deload_pct,
        'bodyweight_kg': session_.bodyweight_kg, 'notes': session_.notes,
        'template_id': session_.template_id,
        'template_name': session_.template.name if session_.template else None,
    }
    return FinishedPayload(**data)


@gym_bp.route('/gym/session/<int:session_id>')
@login_required
def session_detail(session_id):
    session_ = None if _was_discarded(session_id) else owned_session(session_id)
    # Settled before anything is built from it: the nav's context processor
    # used to end an abandoned workout halfway through rendering it as
    # running, and the page came up live on a workout already filed (B4
    # review). Discarded -- now, or while a screen still showed it -- the
    # answer is Heute, where the reason is flashed, not a 404.
    if session_ is None or _settle_if_abandoned(session_) == 'discarded':
        return redirect(url_for('gym.gym_heute'))

    if session_.finished_at:
        # The finished workout is one page now (spec 6.5): hand off to
        # session_finished.html with the debrief payload.
        return render_template(
            'gym/session_finished.html',
            session=session_,
            payload_json=_finished_payload(session_).model_dump(mode='json'),
        )

    # mode='json' so datetimes are ISO strings the island can parse. `session`
    # is still passed separately because the shell's <title> block reads its
    # name before any JavaScript runs.
    return render_template(
        'gym/session_detail.html',
        session=session_,
        payload_json=_session_payload(session_).model_dump(mode='json'),
    )


@gym_bp.route('/gym/session/<int:session_id>/exercises/add', methods=['POST'])
@login_required
def gym_add_session_exercise(session_id):
    session_ = owned_session(session_id)
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal
    # Before anything is created: taking the lock ends the transaction.
    lock_sessions([session_id])

    exercise_id = request.form.get('exercise_id', type=int)
    if not exercise_id and request.form.get('new_exercise_name', '').strip():
        # The exercise list is read-only (2026-09-23): an exercise is picked,
        # never typed into existence. A page from before that still posts a
        # name; refusing is better than guessing which entry it meant.
        abort(400)

    if exercise_id:
        # Any row of the list. The id is attacker-chosen, but it no longer
        # carries anyone's history: _seeded_sets reads this session's owner's.
        exercise_or_404(exercise_id)
        next_position = max([se.position for se in session_.exercises], default=0) + 1
        # No rest on the row: it follows the lifter's setting (see gym_start).
        session_exercise = SessionExercise(
            session_id=session_.id, exercise_id=exercise_id, position=next_position,
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

    return _mutation_response(
        session_, 'gym.session_detail', session_id=session_.id)


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/replace', methods=['POST'])
@login_required
def gym_replace_session_exercise(session_exercise_id):
    """Swap an exercise mid-workout for a same-category substitute (e.g. its
    usual equipment is taken) without touching history: the original row and
    its already-logged sets are left untouched (still counting toward its own
    exercise's history/PRs), a new SessionExercise is created for the
    replacement at the same position, and _template_exercises_from_session
    skips substitutes entirely so this never gets written into a template."""
    original = _locked_session_exercise(session_exercise_id)
    session_id = original.session_id
    refusal = _refuse_structure_edit_if_finished(original.session)
    if refusal is not None:
        return refusal

    exercise_id = request.form.get('exercise_id', type=int)
    if not exercise_id and request.form.get('new_exercise_name', '').strip():
        abort(400)   # read-only list: see gym_add_session_exercise
    if not exercise_id:
        raise InvalidInput('Keine Übung ausgewählt — nichts ersetzt.')
    exercise_or_404(exercise_id)

    # Every no-op used to answer 200 as if the swap had happened (G-149).
    # Under the workout's lock the substitute a second tap or another tab
    # made is visible here: the same exercise is a swap already done, a
    # different one is refused with the reason.
    already = original.replaced_by
    if already is not None and already.exercise_id != exercise_id:
        raise InvalidInput(f'Die Übung ist schon durch {already.exercise.name} ersetzt.')

    if already is None and exercise_id != original.exercise_id:
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
        # With the set count of the slot it stands in for (D2 P1): the
        # routine plans the slot, whichever exercise fills it today.
        substitute.sets.extend(
            _seeded_sets(original.session, exercise_id, original.position,
                         count=plan.slot_count(original.session, original)))
        db.session.add(substitute)

    # No IntegrityError to swallow any more: a concurrent replace of the same
    # original waits for the lock above and then sees its substitute.
    db.session.commit()
    sharing.propagate_structure(original.session)

    return _mutation_response(
        original.session, 'gym.session_detail', session_id=session_id)


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/rest', methods=['POST'])
@login_required
def gym_update_session_exercise_rest(session_exercise_id):
    """This workout's own rest for the exercise ("Pause heute"). The
    lifter's setting itself -- or a blank -- stores nothing: the row follows
    the setting again, so a change to it still reaches this workout."""
    session_exercise = owned_session_exercise(session_exercise_id)
    refusal = _refuse_structure_edit_if_finished(session_exercise.session)
    if refusal is not None:
        return refusal
    seconds = _to_rest_seconds(request.form.get('rest_seconds', ''))
    if seconds is not None and seconds == exercise_setup(
            session_exercise.session.user_id, session_exercise.exercise).default_rest_seconds:
        seconds = None
    session_exercise.rest_seconds = seconds
    session_id = session_exercise.session_id
    db.session.commit()
    return _mutation_response(
        session_exercise.session, 'gym.session_detail', session_id=session_id)


def _to_whole(value, low, high):
    """A whole number from `low` to `high`, else None: "2.5", "drei" and a
    blank are none."""
    number = _to_int(value)
    return number if number is not None and low <= number <= high else None


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/routine-plan', methods=['POST'])
@login_required
def gym_update_routine_plan(session_exercise_id):
    """The routine's plan for the exercise, from the live sheet (D2 P1): how
    many sets it gets and the rep range it aims at. The routine keeps it, so
    it plans the next workout. This workout's sets stay as they were seeded;
    only its target, which reads the routine, follows at once."""
    session_exercise = owned_session_exercise(session_exercise_id)
    session_ = session_exercise.session
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal
    if session_.template is None or session_.template.user_id != session_.user_id:
        raise InvalidInput('Dieses Workout hat keine Routine.')
    if session_exercise.replaces_id is not None:
        raise InvalidInput('Ein Ersatz hat in der Routine keinen eigenen Plan.')
    row = plan.routine_row(session_, session_exercise.exercise_id)
    if row is None:
        raise InvalidInput('Die Routine dieses Workouts hat die Übung nicht.')
    sets = _to_whole(request.form.get('sets'), 1, stats.MAX_PLAN_SETS)
    rep_min = _to_whole(request.form.get('rep_min'), 1, stats.MAX_PLAN_REPS)
    rep_max = _to_whole(request.form.get('rep_max'), 1, stats.MAX_PLAN_REPS)
    if None in (sets, rep_min, rep_max) or rep_min > rep_max:
        raise InvalidInput(f'Sätze 1 bis {stats.MAX_PLAN_SETS}, Wiederholungen 1 bis '
                           f'{stats.MAX_PLAN_REPS} — „von“ nicht über „bis“.')
    row.target_sets, row.rep_min, row.rep_max = sets, rep_min, rep_max
    session_id = session_.id
    db.session.commit()
    return _mutation_response(session_, 'gym.session_detail', session_id=session_id)


@gym_bp.route('/gym/sessions/<int:session_id>/meta', methods=['POST'])
@login_required
def gym_update_session_meta(session_id):
    """Bodyweight and a note for this workout. Both optional, both editable
    at any point -- during the session, or weeks later from Verlauf. The
    start path deliberately does not ask for either: a field between "start"
    and the first set is a field you skip anyway."""
    session = owned_session(session_id)
    refusal = _refuse_live_write_if_finished(session)
    if refusal is not None:
        return refusal
    # Each field only when sent, so either one can be saved on its own. Both
    # are read before either is written: a refused bodyweight must not leave
    # the note half-saved, or the other way round.
    fields = {}
    if 'bodyweight_kg' in request.form:
        fields['bodyweight_kg'] = _to_bodyweight(request.form['bodyweight_kg'])
    if 'notes' in request.form:
        fields['notes'] = _to_note(request.form['notes'])
    for field, value in fields.items():
        setattr(session, field, value)
    db.session.commit()
    return _mutation_response(
        session, 'gym.session_detail', session_id=session.id)


@gym_bp.route('/gym/session-exercises/<int:session_exercise_id>/meta', methods=['POST'])
@login_required
def gym_update_session_exercise_meta(session_exercise_id):
    """A note and a twinge flag, for this exercise in this workout. Both
    belong to the session rather than the catalogue: "shoulder pinched
    today" is not a property of the machine."""
    session_exercise = owned_session_exercise(session_exercise_id)
    refusal = _refuse_live_write_if_finished(session_exercise.session)
    if refusal is not None:
        return refusal
    session_exercise.notes = _to_note(request.form.get('notes', ''))
    session_exercise.pain = request.form.get('pain') == 'on'
    db.session.commit()
    return _mutation_response(
        session_exercise.session, 'gym.session_detail', session_id=session_exercise.session_id)


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/sets/add', methods=['POST'])
@login_required
def gym_add_set(session_exercise_id):
    session_exercise = owned_session_exercise(session_exercise_id)
    refusal = _refuse_live_write_if_finished(session_exercise.session)
    if refusal is not None:
        return refusal

    weight = _to_weight(request.form.get('weight', ''))
    reps = _to_reps(request.form.get('reps', ''))
    # The live screen's outbox names every set it adds, and sends the add
    # again whenever its answer was lost on the way back (B6, D6-A): the
    # copy's insert meets the unique index and finds the set already there.
    key = _to_client_key(request.form.get('key'))
    if weight is not None and reps is not None:
        next_position = max([s.position for s in session_exercise.sets], default=0) + 1
        session_ = session_exercise.session
        finished = session_.finished_at is not None
        # "Anhängen" in the live sheet plans one more set, open, ticked on the
        # card like the rest (Q2, G-060): added done, it jumped the open sets,
        # started a rest and was judged a record before anyone lifted it.
        # "Satz geschafft" with nothing open and the debrief's "Nachtragen"
        # still add a set done.
        planned = not finished and request.form.get('open') == '1'
        new_set = SessionSet(
            session_exercise_id=session_exercise.id,
            position=next_position,
            weight=weight,
            reps=reps,
            completed=not planned,
            # Added from the debrief, it was lifted at some unknown point during
            # the workout. A stamp of "now" would read as a rest of hours after
            # the last real set; no stamp is the honest answer, and every rest
            # measurement already treats NULL as silence. Live, it is the moment
            # the lifter tapped (B6); planned, it has not been lifted yet.
            completed_at=None if finished or planned
            else (_write_time(session_) or dt.datetime.utcnow()),
            client_key=key,
        )
        db.session.add(new_set)
        try:
            db.session.flush()
        except IntegrityError:
            # A copy: its set is the one -- landed before, or a moment ago
            # by the copy racing this one.
            db.session.rollback()
        else:
            if not planned:
                _schedule_rest(new_set)
            db.session.commit()

    return _mutation_response(
        session_exercise.session, 'gym.session_detail', session_id=session_exercise.session_id)


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/delete', methods=['POST'])
@login_required
def gym_delete_session_exercise(session_exercise_id):
    session_exercise = _locked_session_exercise(session_exercise_id, with_partners=True)
    refusal = _refuse_structure_edit_if_finished(session_exercise.session)
    if refusal is not None:
        return refusal
    # Captured before the delete: walking session_exercise.session afterwards
    # would traverse a row that no longer exists.
    _doomed_session = session_exercise.session
    session_id = session_exercise.session_id
    session_ = session_exercise.session
    # A shared exercise is not the follower's to remove while the link is
    # live: the row is the leader's structure, and the leader's next change
    # would only bring it back. Skipping it is theirs, and sticks. The screen
    # does not offer this (payload `mirrored`); this is the stale tab.
    if session_exercise.mirrors_id is not None and sharing.is_live_follower(session_id):
        return _mutation_response(
            _doomed_session, 'gym.session_detail', session_id=session_id)
    # `done`: the done sets the screen showed when the lifter asked. A remove
    # that lands later -- a swap's undo sent again once the connection came
    # back -- took every set logged on the row since with it (B7 review). The
    # screen answers a 409 by asking the server, and draws the row it gets.
    shown = request.form.get('done')
    if shown is not None:
        shown = _to_int(shown)
        if shown is None:
            raise InvalidInput('Übung entfernen: die Zahl der Sätze fehlt.')
        if sum(1 for s in session_exercise.sets if s.completed) > shown:
            if _wants_json():
                return jsonify({'changed': True}), 409
            return redirect(url_for('gym.session_detail', session_id=session_id))
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
    # Flushed and re-read before renumbering: the collection still holds the
    # doomed row until then, and the database has only now cleared a
    # substitute's replaces_id (ON DELETE SET NULL) if this was its original.
    db.session.flush()
    db.session.expire(session_, ['exercises'])
    _close_position_gaps(session_)
    db.session.commit()
    sharing.propagate_structure(session_)
    return _mutation_response(
        _doomed_session, 'gym.session_detail', session_id=session_id)


@gym_bp.route('/gym/session-exercise/<int:session_exercise_id>/skip', methods=['POST'])
@login_required
def gym_toggle_skip_session_exercise(session_exercise_id):
    """Skip: mark this exercise as intentionally not done this session,
    without deleting it -- unlike gym_delete_session_exercise, the row stays
    in session_.exercises, so _template_exercises_from_session still picks
    it up if this session is later saved/updated as a template (no change
    needed there: it already includes every non-substitute row). Toggling
    back off (undo) plans the sets it still owes: what a fresh start would
    seed, after the ones done before the skip (missing_planned_sets)."""
    session_exercise = _locked_session_exercise(session_exercise_id)
    session_ = session_exercise.session
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal

    # The state wanted, like the set tick: the live screen's outbox sends a
    # write again whenever its answer was lost (B6), and a flip sent twice
    # was undone by its own copy -- an un-skip sent twice planned the
    # missing sets twice. A page from before that sends nothing: a flip.
    wanted = request.form.get('skipped')
    skipped = (wanted == '1') if wanted in ('0', '1') else not session_exercise.skipped
    if skipped == session_exercise.skipped:
        return _mutation_response(
            session_, 'gym.session_detail', session_id=session_.id)
    session_exercise.skipped = skipped
    if session_exercise.skipped:
        # Drop only the not-yet-confirmed sets -- anything already completed
        # (e.g. 2 of 4 sets done, then the lifter decides to skip the rest)
        # stays untouched, still counting toward that exercise's history.
        for s in list(session_exercise.sets):
            if not s.completed:
                db.session.delete(s)
    else:
        session_exercise.sets.extend(missing_planned_sets(session_, session_exercise))

    db.session.commit()
    # The skip itself is what travels -- once, as this event. Reconciliation
    # no longer mirrors the flag, so that a partner's own skip survives it.
    sharing.propagate_structure(session_, skip_changed=session_exercise)
    return _mutation_response(
        session_, 'gym.session_detail', session_id=session_.id)


@gym_bp.route('/gym/set/<int:set_id>/delete', methods=['POST'])
@login_required
def gym_delete_set(set_id):
    set_ = owned_set(set_id)
    refusal = _refuse_live_write_if_finished(set_.session_exercise.session)
    if refusal is not None:
        return refusal
    # Captured before the delete, for the same reason as
    # gym_delete_session_exercise.
    _doomed_session = set_.session_exercise.session
    session_ = set_.session_exercise.session
    session_id = session_.id
    if session_.resting_set_id == set_.id:
        session_.resting_set_id = None
        session_.rest_ends_at = None
        _cancel_pending_push(session_)
    db.session.delete(set_)
    db.session.commit()
    return _mutation_response(
        _doomed_session, 'gym.session_detail', session_id=session_id)


def _propagate_default_correction(set_, weight, reps):
    """Numbers typed into a set that was still sitting on the blank plan
    seeding._seeded_sets makes for an exercise with no history carry forward
    to any LATER set of the same SessionExercise that is itself still
    untouched -- `completed` is False and `is_default_seeded` is still True.
    (The plan was 3 x 20 kg x 8 before migration c5a1d8e3f207 blanked it, and
    this carried a correction of that placeholder the same way.)

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
    change on `set_` -- a field that did not change says nothing new, and must
    not stomp a number the sibling already has.

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


def _fill_blanks_after(set_):
    """A logged set's numbers fill every blank of the still-open sets after
    it. A blank is never a choice -- it is a plan waiting for its number -- so
    taking the one just lifted overrides nothing, unlike carrying changes
    forward in general (rejected by the owner, see
    _propagate_default_correction).

    That carry needs `set_` still flagged is_default_seeded, which an earlier
    edit can have cleared: a weight typed into the exercise sheet before the
    first set was logged carries the weight and clears the flags, and the reps
    logged later then had nowhere to go. This catches what it leaves blank.
    A filled sibling's flag goes too, for the same reason the carry clears it:
    the number is the plan now, not a guess."""
    for sibling in set_.session_exercise.sets:
        if sibling.position <= set_.position or sibling.completed:
            continue
        if sibling.weight is None or sibling.reps is None:
            if sibling.weight is None:
                sibling.weight = set_.weight
            if sibling.reps is None:
                sibling.reps = set_.reps
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
    # An empty field is not an edit: None leaves the stored number standing,
    # exactly like a field the form never sent. An impossible one is refused
    # with a 400 that says why (helpers.InvalidInput), before anything is
    # written -- it used to be dropped just as quietly as a blank.
    weight = _to_weight(request.form.get('weight', ''))
    reps = _to_reps(request.form.get('reps', ''))
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
    refusal = _refuse_live_write_if_finished(session_)
    if refusal is not None:
        return refusal

    # See _apply_typed_weight_reps for why was_default_seeded has to be read
    # before this call rather than after: it clears the flag itself.
    was_default_seeded, weight_changed, reps_changed = _apply_typed_weight_reps(set_)

    wanted = request.form.get('completed')
    was_completed = set_.completed
    set_.completed = (wanted == '1') if wanted in ('0', '1') else (not set_.completed)
    if set_.completed and (set_.weight is None or set_.reps is None):
        # A set with a blank cannot be logged: there is no lift for it to say.
        # The live screen never asks -- its button asks for the missing
        # number first -- so this is a stale page or a replay. It gets the set
        # back open with whatever number it did carry, the same quiet refusal
        # gym_add_set gives a set without both numbers.
        set_.completed = False
    # The stamp follows the flag in both directions. Leaving it behind on an
    # un-complete would make the next tick measure the wrong interval. Only a
    # CHANGE moves it: a duplicate "done" used to re-stamp a set already
    # logged. And a tick on a finished workout gets no stamp at all -- the set
    # was lifted at some unknown point during it, not hours later when the
    # debrief was corrected (G-090; gym_add_set does the same). Live, it is
    # the moment the lifter tapped, which the outbox says when it sent the
    # tick late (B6).
    if set_.completed != was_completed:
        live = session_.finished_at is None
        set_.completed_at = ((_write_time(session_) or dt.datetime.utcnow())
                             if set_.completed and live else None)

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
    if set_.completed and not was_completed and session_.finished_at is None:
        # Live only, like gym_update_set's carry: a finished workout's open
        # sets were never lifted and stay as they were.
        _fill_blanks_after(set_)

    if set_.completed and was_completed:
        # already logged, and the caller asked for logged: a duplicate request.
        # Persist any weight/reps it carried, but do NOT restart the rest --
        # that would extend a countdown the lifter is already part-way through.
        db.session.commit()
        return _mutation_response(
        session_, 'gym.session_detail', session_id=session_.id)
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
    return _mutation_response(
        session_, 'gym.session_detail', session_id=session_.id)


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
    refusal = _refuse_live_write_if_finished(session_)
    if refusal is not None:
        return refusal
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
    # ?just_finished carried through: the debrief's "Routine aktualisieren"
    # offer is gated on it, and this redirect dropped it -- so correcting one
    # mistyped set silently destroyed the offer, permanently, with no other
    # route to it. gym_session_summary already does exactly this.
    return _mutation_response(
        session_, 'gym.session_detail', session_id=set_.session_exercise.session_id,
        **_debrief_args())


@gym_bp.route('/gym/session/<int:session_id>/exercises/reorder', methods=['POST'])
@login_required
def gym_reorder_session_exercises(session_id):
    session_ = owned_session(session_id)
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal
    # Training together means one order, and it is the leader's. A follower's
    # own reorder was undone by the leader's next change -- any change -- so it
    # is refused outright rather than allowed and then silently reverted. The
    # screen hides the mode for a follower; this is the stale tab. Once either
    # side finishes the link is over and the order is theirs again.
    if sharing.is_live_follower(session_.id):
        return _mutation_response(
            session_, 'gym.session_detail', session_id=session_id)
    lock_sessions([session_id])
    data = request.get_json(silent=True)
    # A JSON body that is not {"order": [...]} is no order at all: a bare
    # array used to reach `.get` and answer 500 (G-135).
    order = data.get('order') if isinstance(data, dict) else None
    if not isinstance(order, list):
        # The React island posts through the shared form path (postForm), so
        # the order arrives as one comma-joined field; the JSON body shape the
        # old inline script used stays accepted.
        order = [x for x in request.form.get('order', '').split(',') if x]
    session_exercises_by_id = {se.id: se for se in session_.exercises}
    position = 1
    for raw_id in order:
        se = session_exercises_by_id.get(_to_int(raw_id))
        if se:
            old_position = se.position
            se.position = position
            # A substitute shares its slot with the original it replaced (which
            # is hidden from `order` -- it's not rendered while the session is
            # active) -- keep every hidden row behind it in step, all the way
            # down: a substitute can itself be substituted, and syncing one
            # link only left the root original at its old slot, colliding with
            # an unrelated exercise and deciding the order a saved template
            # gets (_template_exercises_from_session reads originals only).
            hidden = se.replaces if se.replaces_id else None
            while hidden is not None:
                hidden.position = position
                hidden = hidden.replaces if hidden.replaces_id else None
            # Its pending sets (if any) were pre-filled from history matched to
            # the OLD position -- e.g. at gym_start, or a previous reorder --
            # which is now stale for the new slot. reseed_for_slot re-derives
            # them, and owns the rule for when it must NOT: a logged set, a
            # skipped exercise, or a plan the lifter has made their own.
            reseed_for_slot(session_, se, old_position, position)
            position += 1
    # A posted order can miss a row -- a second tab, or a partner's addition
    # that landed mid-drag. It keeps its old number, which may now be somebody
    # else's; settle that here rather than serve two rows in one slot.
    _close_position_gaps(session_)
    db.session.commit()
    sharing.propagate_structure(session_)
    return _mutation_response(
        session_, 'gym.session_detail', session_id=session_id)


@gym_bp.route('/gym/session/<int:session_id>/rest/skip', methods=['POST'])
@login_required
def gym_skip_rest(session_id):
    """End the running rest now.

    New with the Puls session screen, which gives the rest the confirm
    button's own slot -- once the countdown occupies the control your thumb is
    on, "I'm ready, go" needs a real action behind it. Before, the only way out
    of a rest was to wait it out or to confirm the next set through it.

    Ending the rest also cancels the pending push, for the same reason
    finishing early does: the notifier daemon would otherwise fire a
    "Pause vorbei" for a rest the lifter already ended themselves.

    The end is stamped now rather than cleared: the band stays until the next
    set, counting up from the rest's end, so nothing on the screen moves under
    the lifter's thumb (round 4). A rest that already ran out keeps its end.
    """
    session_ = owned_session(session_id)
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal
    lock_sessions([session_id])
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal
    # When the lifter tapped, which the outbox says when it sent the skip
    # late (B6): the band counts up from there.
    now = (_write_time(session_) or dt.datetime.utcnow()).replace(microsecond=0)
    if session_.rest_ends_at and session_.rest_ends_at > now:
        session_.rest_ends_at = now
    _cancel_pending_push(session_)
    db.session.commit()
    return _mutation_response(
        session_, 'gym.session_detail', session_id=session_.id)


@gym_bp.route('/gym/session/<int:session_id>/rest/shift', methods=['POST'])
@login_required
def gym_shift_rest(session_id):
    """Move the running rest's end by REST_NUDGE_SECONDS either way: the
    "−15" and "+15" on the countdown band above the confirm button (G-055).

    The push moves with it, or it fires at the old end. "−15" with less than
    that left ends the rest, as the skip does. "+15" stops at the longest rest
    the steppers offer, counted from the set that started it -- but never
    shortens one that is already longer (saved before rests had a cap). A
    rest that has already run out stays over -- nothing clears rest_ends_at
    when it passes, and a stale screen must not bring the countdown back.
    """
    session_ = owned_session(session_id)
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal
    seconds = _to_int(request.form.get('seconds'))
    if seconds not in (-REST_NUDGE_SECONDS, REST_NUDGE_SECONDS):
        raise InvalidInput(f'Pause: {REST_NUDGE_SECONDS} Sekunden mehr oder weniger.')
    # Two quick taps are two requests, and each must move the end the other
    # left, not the end both of them read.
    lock_sessions([session_id])
    # Finished by the other phone between the check above and the lock.
    refusal = _refuse_structure_edit_if_finished(session_)
    if refusal is not None:
        return refusal
    # Whole seconds, as the column stores them: MariaDB rounds a fraction
    # to the nearest second, so a cap of now + 600 could land half a second
    # past itself. The stamps compared against are whole seconds already.
    now = dt.datetime.utcnow().replace(microsecond=0)
    if session_.rest_ends_at and session_.rest_ends_at > now:
        ends = session_.rest_ends_at + dt.timedelta(seconds=seconds)
        if seconds > 0:
            resting_set = (db.session.get(SessionSet, session_.resting_set_id)
                           if session_.resting_set_id else None)
            started = resting_set.completed_at if resting_set is not None else None
            cap = (started or now) + dt.timedelta(seconds=REST_MAX_SECONDS)
            ends = min(ends, max(session_.rest_ends_at, cap))
        _cancel_pending_push(session_)
        if ends <= now:
            # Over, as a skip leaves it: the band counts up from here.
            session_.rest_ends_at = now
        else:
            session_.rest_ends_at = ends
            db.session.add(PendingPush(session_id=session_.id, fire_at=ends))
        db.session.commit()
    return _mutation_response(
        session_, 'gym.session_detail', session_id=session_.id)


@gym_bp.route('/gym/session/<int:session_id>/finish', methods=['POST'])
@login_required
def gym_finish_session(session_id):
    session_ = None if _was_discarded(session_id) else owned_session(session_id)
    # Nobody came back to it: it ends at its last set, not now -- "Beenden"
    # on a screen left open overnight filed a 20-hour workout (B4 review).
    if session_ is None or _settle_if_abandoned(session_) == 'discarded':
        return redirect(url_for('gym.gym_heute'))
    # Two tabs, or a double submit: the second waits here and then sees the
    # first one's finish below. Read again: the other may have discarded it.
    lock_sessions([session_id])
    session_ = db.session.get(WorkoutSession, session_id)
    if session_ is None:
        return redirect(url_for('gym.gym_heute'))
    if session_.finished_at is not None:
        # A second finish -- a double submit, or a live screen restored hours
        # later -- used to re-stamp the workout and stretch its duration to
        # however long the phone sat in a pocket. The first stamp stands.
        return redirect(url_for('gym.session_detail', session_id=session_.id))
    if not any(counts(s) for se in session_.exercises for s in se.sets):
        # Nothing lifted: there is nothing to file, only a workout to throw
        # away (D5, G-023). The finish sheet offers "verwerfen" alone here;
        # this is the answer to a screen that thought otherwise.
        flash('Kein Satz erfasst — ein leeres Workout lässt sich nur verwerfen.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))
    # The rest timer's pending push goes with it, the open sets go, and the
    # sharing ends -- see _finish_session.
    _finish_session(session_, dt.datetime.utcnow())
    db.session.commit()
    return redirect(url_for('gym.session_detail', session_id=session_.id, just_finished=1))


@gym_bp.route('/gym/session/<int:session_id>/discard', methods=['POST'])
@login_required
def gym_discard_session(session_id):
    """Throw away a running workout that has nothing logged in it.

    Tapping the wrong routine used to leave two ways out, both wrong: finish
    it (an empty workout on the books) or finish it and then delete it from
    the debrief. Only while no set is logged -- once one is, the workout has
    happened and finishing is the honest way out; gym_delete_session remains
    for removing it afterwards. Ends any partner link it held, like finishing
    does: the other side trains on alone.
    """
    if _was_discarded(session_id):
        return redirect(url_for('gym.gym_heute'))
    # Nobody came back to it: settled first, like a finish -- filed at its
    # last set, or gone already when nothing in it counts.
    if _settle_if_abandoned(owned_session(session_id)) == 'discarded':
        return redirect(url_for('gym.gym_heute'))
    # A double submit, or a discard racing a finish or a tick: the second
    # waits here and reads what the first left (B4 re-review).
    lock_sessions([session_id])
    session_ = db.session.get(WorkoutSession, session_id)
    if session_ is None:
        return redirect(url_for('gym.gym_heute'))
    if session_.finished_at is not None:
        return redirect(url_for('gym.session_detail', session_id=session_id))
    # counts(), the one rule: the finish sheet offers "verwerfen" off the same
    # count (sets_done), so it never offers what this refuses (G-131).
    if any(counts(s) for se in session_.exercises for s in se.sets):
        # A screen that missed a set of its own -- the other phone's. It
        # used to come back without a word, as if the tap did nothing.
        flash('Das Workout hat schon Sätze — beende es statt es zu verwerfen.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_id))
    _discard_session(session_)
    return redirect(url_for('gym.gym_heute'))


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


