"""Shared live sessions: the link's lifecycle, and the one cross-user write.

Two people training together share structure and nothing else. Each owns an
ordinary WorkoutSession; a SharedSession links them and SharedSessionExercise
translates between their per-user catalogues.

Propagation is a RECONCILIATION rather than a per-operation replay. After any
structural change the leader's route calls propagate_structure(), which makes
the follower's exercise rows mirror the leader's. One idempotent function
instead of five translations -- and being idempotent, it is correct after any
operation, including ones added later.

This module contains the only code in the app that writes into another user's
rows. Every such write goes through reconcile_follower(), which refuses unless
the link is real, accepted, live, and internally consistent. It is deliberately
the mirror image of scope.py: that module is the one place reads are gated,
this is the one place a cross-user write can happen.
"""
import datetime as dt

from extensions import db
from models import (Exercise, SessionExercise, SharedSession,
                    SharedSessionExercise, WorkoutSession)

from .matching import normalise


def active_links_led_by(session_id):
    """Accepted, unfinished links where this session is the leader."""
    return (SharedSession.query
            .filter(SharedSession.leader_session_id == session_id,
                    SharedSession.accepted_at.isnot(None),
                    SharedSession.ended_at.is_(None))
            .all())


def follower_exercise_for(shared, leader_exercise_id):
    """The follower's exercise corresponding to one of the leader's.

    Reuses the mapping if it exists, then an exact name match in the follower's
    catalogue, and only then creates one. The created row is owned by the
    FOLLOWER -- the name travels, the ownership never does.

    This queries Exercise directly rather than through scope.my_exercises(),
    because it runs inside the LEADER's request and needs the follower's
    catalogue. That is the deliberate cross-user reach, and it is confined to
    this function.

    Guards its own link state rather than trusting the caller: this writes
    across users (creates an Exercise owned by the follower, plus a mapping
    row) on its own, so it must not do that for a link that was never
    accepted or has since ended, even though its one caller today already
    checks this before calling in.
    """
    if shared.accepted_at is None or shared.ended_at is not None:
        return None

    mapped = (SharedSessionExercise.query
              .filter_by(shared_session_id=shared.id,
                         leader_exercise_id=leader_exercise_id)
              .first())
    if mapped is not None:
        return mapped.follower_exercise_id

    leader_exercise = db.session.get(Exercise, leader_exercise_id)
    if leader_exercise is None:
        return None

    target = normalise(leader_exercise.name)
    match = None
    for candidate in Exercise.query.filter_by(user_id=shared.follower_user_id).all():
        if normalise(candidate.name) == target:
            match = candidate
            break

    if match is None:
        match = Exercise(
            name=leader_exercise.name,
            muscle_group=leader_exercise.muscle_group,
            default_rest_seconds=leader_exercise.default_rest_seconds,
            user_id=shared.follower_user_id,
        )
        db.session.add(match)
        db.session.flush()

    db.session.add(SharedSessionExercise(
        shared_session_id=shared.id,
        leader_exercise_id=leader_exercise_id,
        follower_exercise_id=match.id,
    ))
    db.session.flush()
    return match.id


def remove_mirrors_of(session_exercise):
    """Delete every follower row mirroring this one -- BEFORE it is deleted.

    Must run before the leader's own delete commits. mirrors_id carries a
    database-level ON DELETE SET NULL, so the moment the leader's row is gone
    the database has already erased the only marker saying which follower row
    corresponded to it. Reconciliation would then have nothing to key on, and
    any heuristic recovery -- matching on exercise_id, say -- cannot tell an
    orphaned mirror from a row the follower added on their own initiative, so
    it would eventually delete the follower's own work along with their sets.

    Row identity is the whole point: this deletes exactly the rows whose
    mirrors_id IS this row's id, and nothing else.
    """
    for shared in active_links_led_by(session_exercise.session_id):
        if shared.follower_session_id is None:
            continue
        mirrors = SessionExercise.query.filter_by(
            session_id=shared.follower_session_id,
            mirrors_id=session_exercise.id,
        ).all()
        if not mirrors:
            continue
        follower = db.session.get(WorkoutSession, shared.follower_session_id)
        for row in mirrors:
            # Deleting an exercise cascades to its sets, so clear the
            # session's pointer at a resting set first or the foreign key
            # blocks it -- the same guard the removal pass in
            # reconcile_follower applies.
            if follower is not None and follower.resting_set_id in [s.id for s in row.sets]:
                follower.resting_set_id = None
                follower.rest_ends_at = None
            db.session.delete(row)
        if follower is not None:
            follower.structure_version = (follower.structure_version or 0) + 1


def reconcile_follower(shared):
    """Make the follower's structure mirror the leader's. Returns True if
    anything changed.

    Idempotent by construction: it compares the two sides and applies the
    difference, so calling it twice is the same as calling it once, and it is
    correct after any structural operation rather than one per operation.

    Rows are matched on SessionExercise.mirrors_id, never on exercise_id. The
    two catalogues use different ids for the same lift, and one exercise can
    legitimately appear twice in a session -- an original plus the substitute
    that replaced it.

    Removing a leader row is NOT handled here -- see remove_mirrors_of(),
    which must run BEFORE the leader's delete commits. mirrors_id carries a
    database-level ON DELETE SET NULL, so by the time reconciliation could
    look for a leader row that's gone, the follower's mirrors_id pointing at
    it would already be NULL and the two rows unrecoverably unlinked. The
    removal loop below only cleans up a leader row that vanished from the
    live set some other way, and that clean-up is the one sanctioned
    exception to "reconciliation never deletes a SessionSet": deleting a
    SessionExercise whose leader row is gone cascades to its sets, and it
    must -- an exercise the leader genuinely removed cannot keep its sets on
    the follower's side either.

    NOTHING here seeds sets. This runs inside the LEADER's request, where
    current_user_id() is the leader, so any history lookup would pre-fill the
    follower's sets from the wrong person's training. An exercise added
    mid-session therefore arrives as an empty slot; the follower's own steppers
    still pre-fill from their history when the page renders in THEIR request.
    Seeding at accept time is correct for the same reason -- that runs in the
    follower's request.
    """
    if shared is None or shared.accepted_at is None or shared.ended_at is not None:
        return False
    if shared.follower_session_id is None:
        return False

    leader = db.session.get(WorkoutSession, shared.leader_session_id)
    follower = db.session.get(WorkoutSession, shared.follower_session_id)
    if leader is None or follower is None:
        return False
    # A corrupted or forged link must not become a way to write into an
    # arbitrary session. Both halves have to agree with the sessions they name.
    if leader.user_id != shared.leader_user_id:
        return False
    if follower.user_id != shared.follower_user_id:
        return False
    # The follower finishing ends their participation even if the link has not
    # been stamped yet.
    if follower.finished_at is not None:
        return False

    mirrored = {se.mirrors_id: se for se in follower.exercises
                if se.mirrors_id is not None}
    changed = False

    for leader_row in sorted(leader.exercises, key=lambda se: se.position):
        row = mirrored.get(leader_row.id)
        if row is None:
            follower_exercise_id = follower_exercise_for(shared, leader_row.exercise_id)
            if follower_exercise_id is None:
                continue
            follower_exercise = db.session.get(Exercise, follower_exercise_id)
            row = SessionExercise(
                session_id=follower.id,
                exercise_id=follower_exercise_id,
                position=leader_row.position,
                # Rest follows the person, so this is the FOLLOWER's default,
                # never the leader's per-session override.
                rest_seconds=follower_exercise.default_rest_seconds if follower_exercise else None,
                skipped=leader_row.skipped,
                mirrors_id=leader_row.id,
            )
            db.session.add(row)
            mirrored[leader_row.id] = row
            changed = True
            continue
        if row.position != leader_row.position:
            row.position = leader_row.position
            changed = True
        if row.skipped != leader_row.skipped:
            row.skipped = leader_row.skipped
            changed = True

    live_leader_ids = {se.id for se in leader.exercises}
    for leader_row_id, row in list(mirrored.items()):
        if leader_row_id in live_leader_ids:
            continue
        # Deleting an exercise cascades to its sets, so clear the session's
        # pointer at a resting set first or the foreign key blocks it.
        if follower.resting_set_id in [s.id for s in row.sets]:
            follower.resting_set_id = None
            follower.rest_ends_at = None
        db.session.delete(row)
        del mirrored[leader_row_id]
        changed = True

    # Substitutes second, once every row exists and has an id: a leader row
    # that replaces another must point at the follower's counterpart of that
    # other row, not at the leader's.
    db.session.flush()
    for leader_row in leader.exercises:
        row = mirrored.get(leader_row.id)
        if row is None:
            continue
        original = mirrored.get(leader_row.replaces_id) if leader_row.replaces_id else None
        wanted = original.id if original is not None else None
        if row.replaces_id != wanted:
            row.replaces_id = wanted
            changed = True

    if changed:
        follower.structure_version = (follower.structure_version or 0) + 1
    return changed


def propagate_structure(session_):
    """Carry this session's structure to every partner who accepted.

    Called by the leader's structural routes after they commit their own
    change. Safe to call on any session: one that leads no link does nothing.
    """
    for shared in active_links_led_by(session_.id):
        reconcile_follower(shared)
    db.session.commit()


def end_links_for(session_):
    """Stamp every live link this session takes part in, on either side.

    Whoever finishes first ends the sharing; the other trains on alone, which
    is the whole point -- a workout must never be cut short by someone else's.
    """
    links = (SharedSession.query
             .filter(SharedSession.ended_at.is_(None))
             .filter(db.or_(SharedSession.leader_session_id == session_.id,
                            SharedSession.follower_session_id == session_.id))
             .all())
    for shared in links:
        shared.ended_at = dt.datetime.utcnow()
