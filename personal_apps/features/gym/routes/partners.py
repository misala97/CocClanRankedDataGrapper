"""Invites and shared sessions: inviting a partner, and the confirm /
accept / decline flow they land in."""

from features.gym.schemas import SharedConfirmPayload
from .. import push
from .. import plan, sharing
import datetime as dt

from flask import (
    abort, flash, redirect, render_template, request, url_for,
)
from sqlalchemy.orm import joinedload
from extensions import (
    db,
)
from models import (
    AppUser, SharedSession, WorkoutSession, WorkoutTemplate,
)
from auth import (
    login_required,
)
from features.gym.scope import (
    current_user_id, my_templates, owned_session,
)
from ..locking import lock_sessions, lock_user
from .helpers import (
    _discard_session, _get_active_session, _is_abandoned, _settle_if_abandoned, _to_int,
    _username,
)
from .history import counts
from ._blueprint import (
    gym_bp,
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
    # A screen left open for hours invited a partner into a workout that was
    # over: it is ended first, and then refused below (B4 re-review).
    if _settle_if_abandoned(session_) == 'discarded':
        return redirect(url_for('gym.gym_heute'))
    # Checked and inserted under the workout's lock: a double tap used to run
    # both halves past the check below, and the second insert hit the
    # (session, partner) unique key -- a 500 (G-136). Now it waits, then
    # finds the invite the first one made. Read again: it may be gone.
    lock_sessions([session_id])
    session_ = db.session.get(WorkoutSession, session_id)
    if session_ is None:
        return redirect(url_for('gym.gym_heute'))

    if not partner_id or partner_id == current_user_id():
        flash('Kein Trainingspartner ausgewählt.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))
    if session_.finished_at is not None:
        flash('Das Workout ist schon vorbei.', 'error')
        return redirect(url_for('gym.session_detail', session_id=session_.id))
    # A follower's workout follows the leader's order, and a third lifter
    # invited from it followed a follower: the leader's changes reached only
    # the first, and the mirror of a mirror drifted (G-085). The leader
    # invites; a follower's screen offers no picker.
    if sharing.is_live_follower(session_.id):
        flash('Einladen kann nur, wer das gemeinsame Training leitet.', 'error')
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
        # Off the request's thread: the invite is saved, and the answer must
        # not wait on -- or fail with -- the partner's push service (G-133).
        push.send_push_later(partner_id, {
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
    # Abandoned counts as over, though nothing of the partner's ends the
    # leader's workout (B4 re-review): joining it seeded a workout three
    # hours cold, and the leader's next page files it anyway.
    if (leader_session is None or leader_session.finished_at is not None
            or _is_abandoned(leader_session)):
        return 'Das Workout ist schon vorbei.'
    active = _get_active_session()
    if active is None:
        return None
    # A workout with nothing logged in it is given up on joining -- see
    # _discardable_active. Before this, opening the app on the way to the gym
    # (which starts one) locked you out of your partner's invite until you
    # found the way to finish an empty workout.
    if any(counts(s) for se in active.exercises for s in se.sets):
        return 'Du hast schon Sätze in einem laufenden Workout — beende es zuerst.'
    if sharing.active_links_led_by(active.id) or sharing.is_live_follower(active.id):
        # Nothing logged yet, but somebody else is training it with you --
        # discarding it would pull their link out from under them.
        return 'Du trainierst gerade mit jemandem — beende das Workout zuerst.'
    return None


def _discardable_active():
    """The caller's running workout that joining will throw away, or None.

    Only ever an empty one: _invite_refusal refuses the join outright when
    the running workout has a logged set or a live partner, so by the time
    this is asked, whatever is running holds nothing worth keeping.
    """
    return _get_active_session()


@gym_bp.route('/gym/shared/<int:shared_id>/confirm')
@login_required
def gym_shared_confirm(shared_id):
    """The invite as one card: who trains what, and Mitmachen.

    Nothing to confirm about the exercises since the one list (2026-09-23):
    the follower logs the leader's own rows, each with their own settings and
    history, and one the leader adds later arrives the same way. The one
    choice left is optional -- which of the follower's routines, if any, the
    workout counts as.
    """
    shared = _invite_for_recipient(shared_id)
    refusal = _invite_refusal(shared)

    exercises = []
    templates = []
    if refusal is None:
        leader_session = db.session.get(WorkoutSession, shared.leader_session_id)
        # In order, de-duplicated: an original and the substitute that
        # replaced it are two rows but can name one exercise.
        for se in sorted(leader_session.exercises, key=lambda se: se.position):
            if se.exercise_id not in [exercise['id'] for exercise in exercises]:
                exercises.append({'id': se.exercise_id, 'name': se.exercise.name})

        # The follower's own routines. joinedload because each one's exercise
        # ids are read below: without it this is a query per routine, the
        # N+1 this codebase refuses to create.
        templates = [
            {'id': template.id, 'name': template.name,
             'exercise_ids': [te.exercise_id for te in template.exercises]}
            for template in (my_templates()
                             .options(joinedload(WorkoutTemplate.exercises))
                             .order_by(WorkoutTemplate.name)
                             .all())
        ]

    leader_session = db.session.get(WorkoutSession, shared.leader_session_id)
    payload = SharedConfirmPayload(
        shared_id=shared.id,
        leader_name=_username(shared.leader_user_id),
        session_name=leader_session.name if leader_session else None,
        started_at=leader_session.started_at if leader_session else None,
        refusal=refusal,
        discards_active=refusal is None and _discardable_active() is not None,
        exercises=exercises,
        templates=templates,
    )
    # `leader_name` is passed separately too: the shell's <title> block reads
    # it before any JavaScript runs.
    return render_template('gym/shared_confirm.html',
                           leader_name=payload.leader_name,
                           payload_json=payload.model_dump(mode='json'))


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

    Also reads a posted `template_id`: one of YOUR OWN routines to book this
    session under, resolved through my_templates() so an id belonging to
    somebody else -- the leader's routine, most obviously -- resolves to no
    routine rather than being claimed.
    """
    # Under the lifter's lock, like a start: "Mitmachen" tapped twice made two
    # workouts, and the link kept the second while the first ran on unlinked
    # (G-136). The second tap now waits and finds the join already done.
    # An abandoned workout is ended first: that commits, which would release
    # the lock (B4 review).
    _get_active_session()
    lock_user(current_user_id())
    joined = db.session.get(SharedSession, shared_id)
    if (joined is not None and joined.follower_user_id == current_user_id()
            and joined.accepted_at is not None and joined.follower_session_id is not None):
        return redirect(url_for('gym.session_detail', session_id=joined.follower_session_id))

    shared = _invite_for_recipient(shared_id)
    refusal = _invite_refusal(shared)
    if refusal is not None:
        flash(refusal, 'error')
        return redirect(url_for('gym.gym_heute'))

    leader_session = db.session.get(WorkoutSession, shared.leader_session_id)

    # The confirm page said so above the button: an empty workout of your own
    # is dropped, not left running beside this one.
    abandoned = _discardable_active()
    if abandoned is not None:
        # Not committed yet: that would let go of lock_user, and a second
        # "Mitmachen" would run on unguarded. The join commits it below.
        _discard_session(abandoned, commit=False)

    # The routine THIS lifter books the workout under, if they picked one on
    # the confirm page. Resolved through my_templates(), so a posted id that
    # belongs to somebody else -- the leader's own routine, most obviously --
    # resolves to None rather than claiming it.
    chosen_template = None
    posted_template_id = _to_int(request.form.get('template_id', ''))
    if posted_template_id:
        chosen_template = my_templates().filter_by(id=posted_template_id).first()
    if chosen_template is not None:
        # Booked under it, the workout is planned by it like a start (D2 P1):
        # filled from THIS lifter's history the first time.
        plan.fill_routine_plan(chosen_template, current_user_id())

    follower_session = WorkoutSession(
        # The name is copied once so the workout reads as the same one. It is
        # not synced afterwards: from here the session is theirs.
        name=leader_session.name,
        started_at=dt.datetime.utcnow(),
        user_id=current_user_id(),
        # The leader's routine is never inherited: it is the leader's, and
        # claiming it would tell routine_memory() this lifter had performed
        # a routine that is not theirs.
        # One of their OWN routines is a different matter -- that is what the
        # confirm page's picker posts, and booking it there is the only way a
        # shared workout ever reaches their routine bookkeeping.
        template_id=chosen_template.id if chosen_template else None,
    )
    db.session.add(follower_session)
    db.session.flush()

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
