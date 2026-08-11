"""What you do to a session rather than in it: deload, summary, delete,
and saving it back to a template."""

from features.gym import stats

from flask import (
    flash, jsonify, redirect, request, url_for,
)
from extensions import (
    db,
)
from models import (
    SharedSession, SharedSessionExercise, WorkoutTemplate,
)
from auth import (
    login_required,
)
from features.gym.scope import (
    current_user_id, my_sessions, my_templates, owned_session, owned_template,
)
from .helpers import (
    _to_int, _wants_json,
)
from .workout import (
    _heute_payload, _template_exercises_from_session,
)
from ._blueprint import (
    gym_bp,
)


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
    # The island's delayed-commit undo posts this via fetch; it needs an
    # answer, not a redirect it would have to parse HTML out of.
    if _wants_json():
        return jsonify({'deleted': True})
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
    # The island edits in place and re-renders from the fresh payload -- its
    # feedback is the row itself changing, so no flash on this path. flash()
    # here would sit queued in the session and surface on some unrelated
    # later full load.
    if _wants_json():
        return jsonify(_heute_payload().model_dump(mode='json'))
    if new_name:
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
    if _wants_json():
        return jsonify(_heute_payload().model_dump(mode='json'))
    flash(f'Routine „{name}“ gelöscht. Die Workouts daraus bleiben im Verlauf.', 'success')
    return redirect(url_for('gym.gym_heute'))
