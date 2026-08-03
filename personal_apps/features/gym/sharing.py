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
    """
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

    # mirrors_id carries a real ON DELETE SET NULL foreign key (see the
    # e4a91c7d20f8 migration). Deleting the leader's row -- which the
    # leader's own route commits BEFORE calling propagate_structure(), per
    # the propagate-after-commit design -- nulls this column at the database
    # level in that same commit, often before reconciliation ever runs. The
    # loop above, keyed on a live mirrors_id, can never see that row again:
    # by the time it reads follower.exercises, the link is already gone.
    #
    # Such an orphan is otherwise indistinguishable from an exercise the
    # follower added to their own session on their own initiative (out of
    # scope for this link, and must never be swept up here). The one thing
    # that tells them apart is this link's own exercise map: only an
    # exercise THIS link is known to have introduced is a candidate, and
    # only if the leader is not currently asking for it.
    linked_exercise_ids = {mapping.follower_exercise_id for mapping in shared.exercise_map}
    wanted_exercise_ids = {row.exercise_id for row in mirrored.values()}
    for row in list(follower.exercises):
        if row.mirrors_id is not None:
            continue
        if row.exercise_id not in linked_exercise_ids:
            continue
        if row.exercise_id in wanted_exercise_ids:
            continue
        if follower.resting_set_id in [s.id for s in row.sets]:
            follower.resting_set_id = None
            follower.rest_ends_at = None
        db.session.delete(row)
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
