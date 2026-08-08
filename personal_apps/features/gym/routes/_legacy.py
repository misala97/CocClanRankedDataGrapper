import datetime as dt
import os

from flask import Blueprint, abort, current_app, flash, jsonify, render_template, request, redirect, send_from_directory, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, load_only

from extensions import db
from models import (
    AppUser, Exercise, WorkoutTemplate, TemplateExercise, WorkoutSession, SessionExercise, SessionSet,
    PushSubscription, PendingPush, SharedSession, SharedSessionExercise, STALE_SESSION_TIMEOUT, MUSCLE_GROUPS,
    EQUIPMENT_TYPES, EQUIPMENT_LABELS,
)
from auth import login_required
from features.gym import export
from features.gym import stats
from features.gym.scope import (
    current_user_id, my_exercises, my_sessions, my_templates,
    owned_exercise, owned_session, owned_session_exercise, owned_set, owned_template,
)
from features.gym.push import is_valid_push_endpoint
from features.gym.schemas import ExerciseDetailPayload
from .. import analytics
from .. import matching
from .. import push
from .. import sharing
# The history -> pending-sets pipeline (_last_session_exercise,
# _last_performance, _last_full_performance, _seeded_sets,
# _seeded_suggestion) lives in seeding.py, not here -- sharing.py needs to
# call _seeded_sets too, to seed a follower's mid-session additions (see
# sharing.reconcile_follower), and sharing.py cannot import routes.py.
from ..seeding import (
    _last_session_exercise, _last_performance, _last_full_performance,
    _seeded_sets, _seeded_suggestion,
)

from ._blueprint import gym_bp
from .helpers import (
    DEFAULT_REST_SECONDS, DAYPART_NAMES, WEEKDAY_NAMES, MONTH_NAMES,
    EXERCISE_STATE_CHIP,
    _to_float, _to_increment, _to_int, _clean_muscle_group, _clean_equipment,
    _to_stack_steps, _clean_secondary_groups, _get_active_session,
    _cancel_pending_push, _username,
    WEEKDAY_SHORT, NON_MUSCLE_GROUPS, RECENT_SESSIONS,
)
from .history import (
    load_performed, _to_performed, _session_rest_entries, performed_from_session,
)
# gym_save_as_template rebuilds a template from a finished session, so the
# session-admin routes reach back into the workout domain for this one builder.
from .workout import _template_exercises_from_session


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

@gym_bp.route('/gym/session/<int:session_id>/invite', methods=['POST'])
@login_required
def gym_invite_partner(session_id):
    """Ask someone to train this workout with you.

    The invite is pending until they accept; your session started already and
    is never blocked on them. Their session does not exist yet on purpose --
    it is seeded from your structure when they accept, so anything you add
    while they walk to the gym is included.
    """
    session_ = owned_session(session_id)
    partner_id = request.form.get('partner_id', type=int)

    if not partner_id or partner_id == current_user_id():
        flash('Kein Trainingspartner ausgewählt.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))
    if session_.finished_at is not None:
        flash('Das Workout ist schon vorbei.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))

    partner = db.session.get(AppUser, partner_id)
    if partner is None:
        flash('Kein Trainingspartner ausgewählt.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))

    # NOT filtered on ended_at: uq_gym_shared_sessions_leader_session_follower
    # is on (leader_session_id, follower_user_id) alone, so a row surviving
    # here after ending is exactly why a genuinely fresh invite is
    # impossible for this (session, partner) pair -- the insert below would
    # collide with it regardless of end state. The three branches below have
    # to tell those apart, or a picker re-submission after the partner
    # already finished flashes success while creating nothing and sending no
    # push, with no way to ever retry.
    existing = SharedSession.query.filter_by(
        leader_session_id=session_.id, follower_user_id=partner_id).first()
    if existing is None:
        db.session.add(SharedSession(
            leader_session_id=session_.id,
            leader_user_id=current_user_id(),
            follower_user_id=partner_id,
        ))
        db.session.commit()
        push.send_push_to_user(partner_id, {
            'title': f'{_username(current_user_id())} trainiert',
            'body': f'{session_.name or "Workout"} — mitmachen?',
        })
        flash(f'{partner.username} wurde eingeladen.', 'success')
    elif existing.ended_at is not None:
        flash(f'Das gemeinsame Training mit {partner.username} ist bereits beendet '
              f'und kann für dieses Workout nicht neu gestartet werden.', 'error')
    else:
        flash(f'{partner.username} ist bereits eingeladen.', 'error')
    return redirect(url_for('gym.session_detail', session_id=session_.id))


def _invite_for_recipient(shared_id):
    """The pending invite addressed to the caller, or 404.

    404 rather than 403 throughout, like every other ownership failure in the
    gym: a 403 would confirm the invite exists.
    """
    shared = db.session.get(SharedSession, shared_id)
    if shared is None or shared.follower_user_id != current_user_id():
        abort(404)
    if shared.accepted_at is not None or shared.ended_at is not None:
        abort(404)
    return shared


def _invite_refusal(shared):
    """Why this invite cannot be taken up, or None.

    Two states get their own sentence here. A generic failure would read as
    the app being broken, when in fact both are ordinary. The third state --
    an invite that is already accepted, already ended, or was never addressed
    to this caller -- never reaches this function: _invite_for_recipient 404s
    on it first, with no sentence, since a sentence would confirm to someone
    who may not be the invite's recipient that it exists at all.
    """
    leader_session = db.session.get(WorkoutSession, shared.leader_session_id)
    if leader_session is None or leader_session.finished_at is not None:
        return 'Das Workout ist schon vorbei.'
    if _get_active_session() is not None:
        return 'Du hast bereits ein laufendes Workout.'
    return None


@gym_bp.route('/gym/shared/<int:shared_id>/confirm')
@login_required
def gym_shared_confirm(shared_id):
    """Match the leader's exercises against your own catalogue, once, before
    the workout starts.

    Confirmation belongs at the door rather than in the middle of a set --
    which is also why an exercise the leader adds LATER resolves silently
    (see sharing.follower_exercise_for).
    """
    shared = _invite_for_recipient(shared_id)
    refusal = _invite_refusal(shared)

    proposals = []
    if refusal is None:
        leader_session = db.session.get(WorkoutSession, shared.leader_session_id)
        leader_rows = sorted(leader_session.exercises, key=lambda se: se.position)
        # Exercise ids, in order, de-duplicated: an original and the substitute
        # that replaced it are two rows but at most two exercises to match.
        leader_exercises = []
        for se in leader_rows:
            if se.exercise_id not in [row.id for row in leader_exercises]:
                leader_exercises.append(se.exercise)
        catalogue = [(row.id, row.name) for row in my_exercises().all()]
        proposals = [
            dict(proposal, leader_exercise_id=exercise.id)
            for exercise, proposal in zip(
                leader_exercises,
                matching.propose_matches([e.name for e in leader_exercises], catalogue))
        ]

    return render_template(
        'gym/shared_confirm.html',
        shared=shared,
        leader_name=_username(shared.leader_user_id),
        refusal=refusal,
        proposals=proposals,
    )


@gym_bp.route('/gym/shared/<int:shared_id>/accept', methods=['POST'])
@login_required
def gym_shared_accept(shared_id):
    """Create your own session and join.

    Seeded from the leader's structure AS IT STANDS NOW, not as it stood when
    the invite was sent: anything added while you walked to the gym is
    included. sharing.reconcile_follower() below does the seeding too --
    every row it creates is brand new here, so no row skips its branch --
    reading YOUR history rather than the leader's because it takes
    shared.follower_user_id explicitly instead of defaulting to
    current_user_id(), which inside reconcile_follower's normal caller
    (a leader's mid-workout structural change) would otherwise name the
    leader.
    """
    shared = _invite_for_recipient(shared_id)
    refusal = _invite_refusal(shared)
    if refusal is not None:
        flash(refusal, 'error')
        return redirect(url_for('gym.gym_heute'))

    leader_session = db.session.get(WorkoutSession, shared.leader_session_id)

    follower_session = WorkoutSession(
        # The name is copied once so the workout reads as the same one. It is
        # not synced afterwards: from here the session is theirs.
        name=leader_session.name,
        started_at=dt.datetime.utcnow(),
        user_id=current_user_id(),
        # Deliberately no template_id: the routine belongs to the leader's
        # catalogue, and claiming it would tell routine_memory() this lifter
        # has done a routine they have never owned.
        template_id=None,
    )
    db.session.add(follower_session)
    db.session.flush()

    # The confirmed matches, before any structure is built -- reconciliation
    # reads this map rather than guessing.
    for key, value in request.form.items():
        if not key.startswith('match_'):
            continue
        leader_exercise_id = _to_int(key[len('match_'):])
        if not leader_exercise_id:
            continue
        leader_exercise = db.session.get(Exercise, leader_exercise_id)
        if leader_exercise is None or leader_exercise.user_id != shared.leader_user_id:
            continue
        if value == 'new':
            # Reuse an owned exercise of that name if one exists, same as
            # gym_replace_session_exercise's new_name branch -- without this,
            # overriding an auto-selected exact match back to "Neu anlegen"
            # for a name already owned hits uq_gym_exercises_user_id_name.
            chosen = my_exercises().filter_by(name=leader_exercise.name).first()
            if chosen is None:
                chosen = Exercise(
                    name=leader_exercise.name,
                    muscle_group=leader_exercise.muscle_group,
                    default_rest_seconds=leader_exercise.default_rest_seconds,
                    # A property of the movement, not the person -- see
                    # sharing.follower_exercise_for's identical copy for why
                    # this travels while weight_increment does not.
                    is_unilateral=leader_exercise.is_unilateral,
                    user_id=current_user_id(),
                )
                db.session.add(chosen)
                db.session.flush()
            chosen_id = chosen.id
        else:
            # Attacker-chosen: without owned_exercise a lifter could map their
            # slot onto somebody else's row and log against its history.
            chosen_id = owned_exercise(_to_int(value)).id
        db.session.add(SharedSessionExercise(
            shared_session_id=shared.id,
            leader_exercise_id=leader_exercise_id,
            follower_exercise_id=chosen_id,
        ))

    shared.follower_session_id = follower_session.id
    shared.accepted_at = dt.datetime.utcnow()
    db.session.flush()

    # Builds AND seeds every row (see reconcile_follower's docstring) --
    # nothing further to seed here.
    sharing.reconcile_follower(shared)
    db.session.commit()

    return redirect(url_for('gym.session_detail', session_id=follower_session.id))


@gym_bp.route('/gym/shared/<int:shared_id>/decline', methods=['POST'])
@login_required
def gym_shared_decline(shared_id):
    """Declining is not an event. The card disappears and nobody is notified."""
    shared = _invite_for_recipient(shared_id)
    db.session.delete(shared)
    db.session.commit()
    return redirect(url_for('gym.gym_heute'))


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

    A set seeded from _seeded_sets' no-history default plan is skipped
    entirely -- see the is_default_seeded check below -- because there is no
    real working weight underneath it to scale. The same hand-typed edit that
    drops base_weight/base_reps also clears is_default_seeded, so a lifter who
    turns the invented number into a real one makes it deload-eligible from
    then on.
    """
    session_ = owned_session(session_id)

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
                if s.is_default_seeded:
                    # An invented default-plan set (_seeded_sets, no history)
                    # has no real working weight to take a percentage of --
                    # scaling it would present a fabricated prescription as a
                    # real one. Leave it exactly as seeded, regardless of
                    # whether the exercise was added before or after this
                    # toggle: previously that ordering decided the outcome,
                    # because base_weight was only filled in here, on the way
                    # in, so "deload already on when the exercise arrived"
                    # skipped scaling (base_weight never got a chance to be
                    # filled) while "deload switched on afterwards" scaled it
                    # anyway. is_default_seeded makes the set itself say so,
                    # so both orders behave the same.
                    continue
                if on:
                    # Capture the baseline the first time only. Re-applying the
                    # toggle, or changing the percentage, then always scales
                    # from the working weight rather than from the already
                    # reduced one -- without this, 70 % followed by 60 % gives
                    # 32.5 kg instead of 47.5 kg, and a double-tap compounds.
                    if s.base_weight is None:
                        s.base_weight = s.weight
                    s.weight = stats.deload_weight(
                        s.base_weight, pct, increment,
                        stack_kg=session_exercise.exercise.stack_kg)
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
    owned_session(session_id)   # 404 for a stranger rather than a redirect that then 404s
    # Kept as a redirect: a finished workout is one page now, and this URL is
    # in browser history and bookmarks.
    return redirect(url_for('gym.session_detail', session_id=session_id,
                            **request.args.to_dict()))


@gym_bp.route('/gym/session/<int:session_id>/delete', methods=['POST'])
@login_required
def gym_delete_session(session_id):
    session_ = owned_session(session_id)
    if session_.finished_at is not None:  # never delete the active workout by accident
        # Null the self-referencing rest-timer FK first -- deleting a session
        # whose resting_set_id still points at one of its own (about to be
        # cascade-deleted) sets would otherwise violate the FK constraint.
        session_.resting_set_id = None
        db.session.commit()
        # Plain FKs with no ondelete point at this session from both halves of
        # any link it took part in. Deleting the workout without clearing them
        # is a constraint violation -- and the link is spent anyway, since a
        # session can only be deleted once it has finished.
        #
        # SharedSessionExercise.shared_session_id is itself a plain FK, with
        # no ondelete and no ORM-level cascade -- SharedSession carries no
        # relationship to it at all. A bulk delete() bypasses ORM cascades in
        # any case, so the exercise-map rows have to be cleared explicitly
        # first, or deleting the link row 500s on exactly the same kind of
        # constraint this comment is already warning about, one table deeper.
        doomed_link_ids = [row.id for row in SharedSession.query.filter(
            db.or_(SharedSession.leader_session_id == session_.id,
                   SharedSession.follower_session_id == session_.id)).all()]
        if doomed_link_ids:
            SharedSessionExercise.query.filter(
                SharedSessionExercise.shared_session_id.in_(doomed_link_ids)).delete(
                synchronize_session=False)
            SharedSession.query.filter(SharedSession.id.in_(doomed_link_ids)).delete(
                synchronize_session=False)
        db.session.delete(session_)
        db.session.commit()
    return redirect(url_for('gym.gym_verlauf'))


@gym_bp.route('/gym/session/<int:session_id>/update_template', methods=['POST'])
@login_required
def gym_update_template(session_id):
    session_ = owned_session(session_id)
    if session_.template_id:
        template = my_templates().filter_by(id=session_.template_id).first()
        if template:
            template.exercises.clear()
            db.session.flush()
            template.exercises.extend(_template_exercises_from_session(session_))
            db.session.commit()
            flash(f'Routine „{template.name}“ auf diese Übungsliste aktualisiert.', 'success')
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/session/<int:session_id>/save_as_template', methods=['POST'])
@login_required
def gym_save_as_template(session_id):
    session_ = owned_session(session_id)
    template_name = request.form.get('template_name', '').strip()
    if template_name:
        template = WorkoutTemplate(name=template_name, user_id=current_user_id())
        template.exercises.extend(_template_exercises_from_session(session_))
        db.session.add(template)
        # Start reads "last done" off WorkoutSession.template_id, so a routine
        # saved from a workout you have just finished announced itself as never
        # performed: the one instance of it that certainly exists was not
        # pointing at it.
        #
        # Only an unlinked session is claimed. Re-pointing one that already
        # belongs to a routine would quietly remove it from that routine's
        # history and move its last-done date -- and on the finished page this
        # prompt is only offered for a freeform session anyway.
        if session_.template_id is None:
            db.session.flush()
            session_.template_id = template.id
        db.session.commit()
        flash(f'Als Routine „{template_name}“ gespeichert.', 'success')
    else:
        flash('Kein Name eingegeben — nichts gespeichert.', 'error')
    return redirect(url_for('gym.session_detail', session_id=session_.id))


@gym_bp.route('/gym/templates/<int:template_id>/rename', methods=['POST'])
@login_required
def gym_rename_template(template_id):
    """Heute's small per-routine edit affordance. WorkoutTemplate.name carries
    no unique constraint (unlike Exercise.name), so unlike gym_update_exercise
    there is no collision case to reject -- any non-empty name is accepted."""
    template = owned_template(template_id)
    new_name = request.form.get('name', '').strip()
    if new_name:
        template.name = new_name
        db.session.commit()
        flash(f'Routine heißt jetzt „{new_name}“.', 'success')
    else:
        flash('Kein Name eingegeben — die Routine heißt weiter wie vorher.', 'error')
    return redirect(url_for('gym.gym_heute'))


@gym_bp.route('/gym/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def gym_delete_template(template_id):
    template = owned_template(template_id)
    # Null out references instead of cascading -- deleting a template must not
    # delete the workout history of sessions that were started from it.
    my_sessions().filter_by(template_id=template.id).update({'template_id': None}, synchronize_session=False)
    name = template.name
    db.session.delete(template)
    db.session.commit()
    flash(f'Routine „{name}“ gelöscht. Die Workouts daraus bleiben im Verlauf.', 'success')
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
        my_sessions()
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

    # Gaps are built PER SESSION and then concatenated, never across the whole
    # history at once: rest_gaps() measures consecutive pairs, and two different
    # workouts are not consecutive -- the interval from Monday's last set to
    # Wednesday's first is not a rest, it is a rest day. The cap would drop it
    # anyway, but only by accident, and an accident is not a rule.
    #
    # Pooled rather than averaged per session, because the question is what a
    # typical rest of yours looks like: a twenty-set session carries more
    # evidence about that than a six-set one.
    # Eager-loaded for the same reason session_detail's finished branch is
    # (see the comment there): this walks se.sets and se.exercise per row,
    # lazily, for every finished session in the whole history -- 1 + S query
    # became 1 + S + 2*S*E, thousands of queries at real-world scale.
    habit_gaps = []
    for session_ in (
        my_sessions()
        .filter(WorkoutSession.finished_at.isnot(None))
        .options(
            joinedload(WorkoutSession.exercises).joinedload(SessionExercise.sets),
            joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise),
        )
    ):
        habit_gaps.extend(stats.rest_gaps(_session_rest_entries(session_)))
    rest_habit = stats.rest_medians(habit_gaps)

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
        rest_habit=rest_habit,
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
    swap is fully traceable. The payload shape is schema v2 and lives in
    features/gym/export.py."""
    ids_param = request.args.get('ids', '')
    session_ids = []
    for raw_id in ids_param.split(','):
        raw_id = raw_id.strip()
        if raw_id.isdigit():
            session_ids.append(int(raw_id))

    sessions = (
        my_sessions()
        .filter(
            WorkoutSession.finished_at.isnot(None),
            WorkoutSession.id.in_(session_ids),
        )
        .order_by(WorkoutSession.started_at.asc())
        .all()
    ) if session_ids else []

    payload = export.build_payload(sessions, session_ids, dt.datetime.utcnow())

    resp = jsonify(payload)
    filename = f"gym-export-{len(sessions)}-workouts.json"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@gym_bp.route('/gym/uebungen')
@login_required
def gym_uebungen():
    now = dt.datetime.utcnow()
    exercises = my_exercises().order_by(Exercise.name).all()

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
        equipment_labels=EQUIPMENT_LABELS,
        open_by_default=len(exercises) <= UEBUNGEN_FOLD_ABOVE,
        # The sheet's rest placeholder said 90 while this is what a blank field
        # actually stores.
        default_rest_seconds=DEFAULT_REST_SECONDS,
        added_id=_to_int(request.args.get('added')),
        name_taken=bool(request.args.get('name_taken')),
    )




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


def _exercise_detail_payload(exercise, raw_position):
    """Everything the exercise page shows, for one exercise and one requested
    position.

    Shared by the HTML route and the JSON route so the default-slot rule below
    cannot drift between them -- two copies of it would disagree the first time
    either was touched, and the page and a refetch would then show different
    slots.

    The default view is one slot, not all of them. "Alle" draws every position
    at once, which is the comparison view -- useful when you want it, and a
    poor thing to land on: the answer to "how is this lift going" is a single
    line, and overlapping slots bury it.

    Which slot: the best-performing one, meaning highest best-e1RM -- but only
    among slots with at least two sessions. A slot used once is a data point,
    not a track record, and defaulting to it would show a flattering line
    built from a single lucky day. With nothing qualifying, fall back to the
    slot the exercise actually lives in (the most sessions).

    `?position=all` is how the page asks for the comparison view, so the
    default stays reachable in one click and the URL stays honest about what
    it is showing.
    """
    rows = load_performed(exercise_ids=[exercise.id], include_active=True)

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
    return ExerciseDetailPayload.model_validate({
        'exercise': {
            'id': exercise.id,
            'name': exercise.name,
            'muscle_group': exercise.muscle_group,
            'is_unilateral': exercise.is_unilateral,
            'default_rest_seconds': exercise.default_rest_seconds,
            'weight_increment': exercise.weight_increment,
            'equipment': exercise.equipment,
            'bar_weight': exercise.bar_weight,
            'stack_kg': exercise.stack_kg,
            'secondary_muscle_groups': exercise.secondary_muscle_groups,
        },
        'selected_position_is_default': position_is_default,
        'selected_position_reason': default_reason,
        'chart': _chart_geometry(data['series'], data.get('pr_e1rm')),
        'chip_class': chip_class,
        'chip_label': chip_label,
        # Only offer deletion when nothing depends on it -- same test the
        # catalogue used before this moved off the list.
        'can_delete': not exercise.session_exercises and not exercise.template_exercises,
        'muscle_groups': list(MUSCLE_GROUPS),
        'equipment_labels': dict(EQUIPMENT_LABELS),
        **data,
    })


@gym_bp.route('/gym/exercises/<int:exercise_id>')
@login_required
def exercise_detail(exercise_id):
    exercise = owned_exercise(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    # mode='json' so datetimes are ISO strings the island can parse. `exercise`
    # is still passed separately because the shell's <title> block reads its
    # name before any JavaScript runs.
    return render_template(
        'gym/exercise_detail.html',
        exercise=exercise,
        payload_json=payload.model_dump(mode='json'),
    )


@gym_bp.route('/gym/exercises/<int:exercise_id>/detail.json')
@login_required
def gym_exercise_detail_json(exercise_id):
    """The full exercise page as JSON.

    Distinct from gym_exercise_progress_json below, which backs the in-workout
    quick-glance modal and deliberately falls back to all-time data when the
    requested slot is empty. This one honours the filter exactly, because the
    page's pills have to mean what they say.
    """
    exercise = owned_exercise(exercise_id)
    payload = _exercise_detail_payload(exercise, request.args.get('position'))
    return jsonify(payload.model_dump(mode='json'))


@gym_bp.route('/gym/exercises/<int:exercise_id>/progress.json')
@login_required
def gym_exercise_progress_json(exercise_id):
    """Backs the in-workout quick-glance modal. Scoped to a position when
    one is given (same slot in the workout order = comparable fatigue
    state), but unlike the full exercise page's explicit filter, this falls
    back to all-time data if that exact slot has no history yet -- the
    modal should always show *something* useful rather than an empty state
    just because you haven't done this exercise in this position before."""
    exercise = owned_exercise(exercise_id)
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
    # No flash on either branch: the input is `required`, so an empty name does
    # not reach here through the UI, and ?name_taken already renders a banner on
    # the page that says this in context. A flash would say it twice.
    if my_exercises().filter_by(name=name).first():
        return redirect(url_for('gym.gym_uebungen', name_taken=1))

    muscle_group = _clean_muscle_group(request.form.get('muscle_group', ''))
    equipment = _clean_equipment(request.form.get('equipment', ''))
    exercise = Exercise(
        name=name,
        muscle_group=muscle_group,
        default_rest_seconds=_to_int(request.form.get('default_rest_seconds', ''), DEFAULT_REST_SECONDS),
        weight_increment=_to_increment(request.form.get('weight_increment', '')),
        is_unilateral=request.form.get('is_unilateral') == 'on',
        equipment=equipment,
        bar_weight=_to_increment(request.form.get('bar_weight', '')),
        # Stack steps only mean something for a stack machine -- the hidden
        # Stack-Stufen input still submits its old value even when Art has
        # been switched away from stack, and increment_kg/stack_kg are meant
        # to be mutually exclusive (the export derives one from the other).
        stack_kg=_to_stack_steps(request.form.get('stack_kg', '')) if equipment == 'stack' else None,
        secondary_muscle_groups=_clean_secondary_groups(
            request.form.getlist('secondary_muscle_groups'), muscle_group),
        user_id=current_user_id(),
    )
    db.session.add(exercise)
    db.session.commit()
    return redirect(url_for('gym.gym_uebungen', added=exercise.id))


@gym_bp.route('/gym/exercises/<int:exercise_id>/update', methods=['POST'])
@login_required
def gym_update_exercise(exercise_id):
    exercise = owned_exercise(exercise_id)
    new_name = request.form.get('name', '').strip()
    name_taken = False
    if new_name and new_name != exercise.name:
        if my_exercises().filter_by(name=new_name).first():
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
    exercise.equipment = _clean_equipment(request.form.get('equipment', ''),
                                          current=exercise.equipment)
    exercise.bar_weight = _to_increment(request.form.get('bar_weight', ''))
    # Stack steps only mean something for a stack machine -- the hidden
    # Stack-Stufen input still submits its old value even when Art has been
    # switched away from stack, and increment_kg/stack_kg are meant to be
    # mutually exclusive (the export derives one from the other).
    exercise.stack_kg = (
        _to_stack_steps(request.form.get('stack_kg', '')) if exercise.equipment == 'stack' else None
    )
    exercise.secondary_muscle_groups = _clean_secondary_groups(
        request.form.getlist('secondary_muscle_groups'), exercise.muscle_group)
    db.session.commit()
    return redirect(url_for(
        'gym.exercise_detail', exercise_id=exercise.id, name_taken=1 if name_taken else None,
    ))


@gym_bp.route('/gym/exercises/<int:exercise_id>/delete', methods=['POST'])
@login_required
def gym_delete_exercise(exercise_id):
    exercise = owned_exercise(exercise_id)
    if exercise.session_exercises or exercise.template_exercises:
        # Silently refusing looked identical to deleting, so the row just
        # stayed there with no reason given.
        flash(f'„{exercise.name}“ steckt noch in einem Workout oder einer Routine '
              f'und wurde nicht gelöscht.', 'error')
        return redirect(url_for('gym.gym_uebungen'))
    name = exercise.name
    db.session.delete(exercise)
    db.session.commit()
    flash(f'Übung „{name}“ gelöscht.', 'success')
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

    # Looked up by endpoint alone, NOT by (endpoint, user): the column is
    # globally unique, one row per browser installation. Scoping the lookup to
    # the caller would return None for a device the other lifter last
    # subscribed from, and the insert below would then hit the unique
    # constraint and 500. Re-pointing the row is the correct answer anyway --
    # the subscription belongs to whoever is logged in on that device now.
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if sub:
        sub.p256dh_key = p256dh
        sub.auth_key = auth_key
        sub.user_id = current_user_id()
    else:
        db.session.add(PushSubscription(endpoint=endpoint, p256dh_key=p256dh,
                                        auth_key=auth_key, user_id=current_user_id()))
    db.session.commit()
    return jsonify({'status': 'ok'})


@gym_bp.route('/gym/push/unsubscribe', methods=['POST'])
@login_required
def gym_push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user_id()).delete()
        db.session.commit()
    return jsonify({'status': 'ok'})
