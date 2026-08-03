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

from flask import current_app
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (Exercise, PendingPush, SessionExercise, SharedSession,
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
    checks this before calling in. `shared is None` is checked first for the
    same reason -- reconcile_follower checks it before calling in, but this
    function must not borrow that invariant either.
    """
    if shared is None or shared.accepted_at is None or shared.ended_at is not None:
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
            # Unilaterality is a property of the MOVEMENT (a one-arm row is
            # one-arm for anyone doing it), so it travels with the name --
            # unlike weight_increment, which is genuinely per-person equipment
            # and correctly stays behind. Dropping this left every volume
            # figure for the follower's copy at half its real value.
            is_unilateral=leader_exercise.is_unilateral,
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
    """Delete the follower row mirroring this one -- BEFORE it is deleted.

    Must run before db.session.delete(session_exercise) is called AT ALL --
    not merely before the commit. Flask-SQLAlchemy autoflushes before the
    SessionExercise.query below runs, so calling this after
    db.session.delete(session_exercise) but before commit still flushes the
    pending DELETE first: MySQL applies mirrors_id's database-level
    ON DELETE SET NULL, and the query below then matches zero rows -- a
    silent no-op that leaves the follower with a phantom exercise. Row
    identity is the whole point: this deletes exactly the row whose
    mirrors_id IS this row's id, and nothing else. Any heuristic recovery
    after the fact -- matching on exercise_id, say -- cannot tell an orphaned
    mirror from a row the follower added on their own initiative, so it would
    eventually delete the follower's own work along with their sets.

    One follower row mirrors one leader row, always, per link -- mirrors_id
    carries no uniqueness constraint at the database level, but nothing in
    this module ever creates a second follower row for the same leader row,
    and reconcile_follower's `mirrored` map (keyed on mirrors_id) depends on
    that being true, silently collapsing a second row rather than erroring.
    This queries with .first() rather than .all() to match that invariant
    instead of contradicting it.

    Guards its own link state rather than trusting the caller, exactly like
    reconcile_follower does: this deletes cascading to logged SessionSet
    rows, which is more destructive than reconciliation, not less, so it
    must refuse for at least the same reasons reconciliation does -- a
    corrupted or forged link naming the wrong sessions, or a follower who
    finished their workout while this delete was in flight.
    """
    if session_exercise.id is None or session_exercise in db.session.deleted:
        raise RuntimeError(
            'remove_mirrors_of must run BEFORE db.session.delete(session_exercise): '
            'mirrors_id carries ON DELETE SET NULL, so once the delete is flushed the '
            'link to the follower row is already gone and this would silently match nothing.')

    for shared in active_links_led_by(session_exercise.session_id):
        if shared.follower_session_id is None:
            continue
        leader = db.session.get(WorkoutSession, shared.leader_session_id)
        follower = db.session.get(WorkoutSession, shared.follower_session_id)
        if leader is None or follower is None:
            continue
        # Same guards as reconcile_follower, applied locally rather than
        # inherited from the caller. Concrete failure this prevents: the
        # follower finishes their workout while the leader's delete request
        # is in flight, before finished_at is stamped -- without this check,
        # the leader's delete would remove an exercise, and its logged sets,
        # from a workout the follower has already completed.
        if leader.user_id != shared.leader_user_id:
            continue
        if follower.user_id != shared.follower_user_id:
            continue
        if follower.finished_at is not None:
            continue

        row = SessionExercise.query.filter_by(
            session_id=shared.follower_session_id,
            mirrors_id=session_exercise.id,
        ).first()
        if row is None:
            continue
        # Deleting an exercise cascades to its sets, so clear the session's
        # pointer at a resting set first or the foreign key blocks it -- and
        # cancel any pending push for this session at the same time, exactly
        # as routes._cancel_pending_push's contract requires whenever
        # resting_set_id/rest_ends_at is cleared: an orphaned PendingPush row
        # has no way to tell the notifier daemon the set it was scheduled for
        # is gone, and the daemon fires it regardless. sharing.py cannot
        # import from routes (circular once routes calls into this module),
        # so this is inlined rather than shared.
        if follower.resting_set_id in [s.id for s in row.sets]:
            follower.resting_set_id = None
            follower.rest_ends_at = None
            PendingPush.query.filter_by(session_id=follower.id, sent=False).delete()
        db.session.delete(row)
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
    which must run BEFORE db.session.delete() is called on the leader's row
    at all, not merely before the commit. mirrors_id carries a database-level
    ON DELETE SET NULL, so by the time reconciliation could look for a leader
    row that's gone, the follower's mirrors_id pointing at it would already
    be NULL and the two rows unrecoverably unlinked. The removal loop below
    only cleans up a leader row that vanished from the live set some other
    way, and that clean-up is the one sanctioned exception to "reconciliation
    never deletes a SessionSet": deleting a SessionExercise whose leader row
    is gone cascades to its sets, and it must -- an exercise the leader
    genuinely removed cannot keep its sets on the follower's side either.

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

    # Keyed on mirrors_id, which silently collapses a second row sharing the
    # same mirrors_id rather than erroring -- fine only because one follower
    # row mirrors one leader row, always (remove_mirrors_of enforces the same
    # invariant with .first() rather than .all(), so the two agree).
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
        # A mirrors_id absent from THIS link's live_leader_ids is not enough
        # on its own: follower_session_id carries no uniqueness constraint,
        # so this follower session could be the follower half of a second,
        # unrelated link, and that link's mirror rows show up in `mirrored`
        # too -- keyed on a mirrors_id that was never one of this leader's
        # rows to begin with. Only delete when the leader row is genuinely
        # gone: db.session.get() returns None. If it returns a row instead,
        # that row is alive under a different session (it can't be this
        # link's leader session, or leader_row_id would already be in
        # live_leader_ids above) -- i.e. it belongs to another link, and this
        # one must leave it alone.
        leader_row = db.session.get(SessionExercise, leader_row_id)
        if leader_row is not None and leader_row.session_id != shared.leader_session_id:
            continue
        # Deleting an exercise cascades to its sets, so clear the session's
        # pointer at a resting set first or the foreign key blocks it -- and
        # cancel any pending push for the same reason remove_mirrors_of does.
        if follower.resting_set_id in [s.id for s in row.sets]:
            follower.resting_set_id = None
            follower.rest_ends_at = None
            PendingPush.query.filter_by(session_id=follower.id, sent=False).delete()
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
        # SessionExercise.replaces_id carries a TABLE-WIDE unique constraint
        # (models.py), not one scoped to a session -- so `wanted` may already
        # be claimed by a row this function structurally cannot see: the
        # follower's OWN mid-workout substitute for the same original, which
        # has mirrors_id IS NULL and therefore never enters `mirrored` above.
        # Concrete case this guards: both partners swap the same occupied
        # machine. The follower replaces theirs first (their new row claims
        # replaces_id = their original's id); the leader then replaces
        # theirs too and propagates. Assigning `wanted` here regardless would
        # collide on the unique index at commit time -- an unhandled
        # IntegrityError 500 on every subsequent structural action by the
        # LEADER, from a write that is entirely about the follower's row.
        # The follower's own swap wins for their own session (consistent
        # with "the follower's session is otherwise fully theirs"): leave
        # this row unlinked instead of overwriting/colliding with it.
        if wanted is not None:
            claimed_by_other = SessionExercise.query.filter(
                SessionExercise.replaces_id == wanted,
                SessionExercise.id != row.id,
            ).first()
            if claimed_by_other is not None:
                wanted = None
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

    Guarded end to end: this runs entirely inside the LEADER's request, after
    the leader's own change already committed durably. A constraint violation
    originating in the FOLLOWER's data (Fix 1's replaces_id collision before
    it was closed off, or a race on uq_gym_shared_session_exercises_link_leader
    / uq_gym_exercises_user_id_name) must never turn into a 500 on someone
    else's request over a write the leader has no way to see or retry. The
    worst case here is the partner falling out of sync until the next
    structural change reconciles cleanly -- never a crash.
    """
    try:
        for shared in active_links_led_by(session_.id):
            reconcile_follower(shared)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.exception(
            'propagate_structure: reconciliation failed for session %s, '
            'partner(s) left out of sync until the next structural change',
            session_.id)


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
