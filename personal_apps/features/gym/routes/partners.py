"""Invites and shared sessions: inviting a partner, and the confirm /
accept / decline flow they land in."""

from .. import matching
from .. import push
from .. import sharing
import datetime as dt

from flask import (
    abort, flash, redirect, render_template, request, url_for,
)
from extensions import (
    db,
)
from models import (
    AppUser, Exercise, SharedSession, SharedSessionExercise, WorkoutSession,
)
from auth import (
    login_required,
)
from features.gym.scope import (
    current_user_id, my_exercises, owned_exercise, owned_session,
)
from .helpers import (
    _get_active_session, _to_int, _username,
)
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
