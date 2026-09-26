"""Shared live sessions: the link's lifecycle, and the one cross-user write.

Two people training together share structure, as writes. Each owns an
ordinary WorkoutSession; a SharedSession links them. What each of them lifts
is only ever SHOWN to the other, read-only (D14, M5), and routes/partner_view.py
is the one place that reads it. Since the one exercise
list (2026-09-23) both log the same exercise rows, so a lift needs no
translating: the follower's row names the leader's exercise, and what differs
between them -- settings, history, plans -- is keyed by user, not by row.

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
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import aliased

from extensions import db
from models import PendingPush, SessionExercise, SharedSession, WorkoutSession

from . import plan, stats
from .locking import lock_sessions
from .seeding import _seeded_sets, missing_planned_sets, reseed_for_slot


def _live_links():
    """Accepted links not ended whose two workouts both still run. A finished
    workout ends the sharing even where no stamp says so -- a link from before
    finishing stamped it, or one written by hand (B11): its partner kept
    following the leader's order, and the leader kept writing into a workout
    that was over."""
    leader = aliased(WorkoutSession)
    follower = aliased(WorkoutSession)
    return (SharedSession.query
            .join(leader, leader.id == SharedSession.leader_session_id)
            .join(follower, follower.id == SharedSession.follower_session_id)
            .filter(SharedSession.accepted_at.isnot(None),
                    SharedSession.ended_at.is_(None),
                    leader.finished_at.is_(None),
                    follower.finished_at.is_(None)))


def active_links_led_by(session_id):
    """The live links (_live_links) where this session is the leader."""
    return _live_links().filter(SharedSession.leader_session_id == session_id).all()


def live_links_of(session_id):
    """The live links (_live_links) this session takes part in, either side."""
    return (_live_links()
            .filter(db.or_(SharedSession.leader_session_id == session_id,
                           SharedSession.follower_session_id == session_id))
            .all())


def handover_session_ids(session_id):
    """The workouts a finish of this one writes into besides its own: each
    live follower's, whose order is handed over as the link ends (end_link).
    Locked with the finisher's, in one lock_sessions call, before anything
    changes; a link accepted after this read has nothing started to hand
    over."""
    return [link.follower_session_id for link in active_links_led_by(session_id)]


def started_row(visible_exercises):
    """The row a live follower's card holds (live._live_context's
    keep_started): what they have started and not finished, the most recently
    ticked if there are two, or None. Here, not in routes: the order handover
    (end_link) picks the same row, and sharing cannot import routes."""
    started = [
        se for se in visible_exercises
        if not se.skipped
        and any(s.completed for s in se.sets)
        and not all(s.completed for s in se.sets)]
    if not started:
        return None
    return max(started, key=lambda se: max(
        (s.completed_at or dt.datetime.min) for s in se.sets if s.completed))


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
        _release_mirror(follower, row)
        follower.structure_version = (follower.structure_version or 0) + 1


def is_live_follower(session_id):
    """Whether this session is the follower half of a live link (_live_links).

    While it is, its ORDER is the leader's: the follower's own reorder would be
    undone by the leader's next change, so the route refuses it rather than
    pretend. The same test gates the follower's page polling for changes.
    """
    return (_live_links()
            .filter(SharedSession.follower_session_id == session_id)
            .first()) is not None


def _release_mirror(follower, row):
    """What becomes of a follower row whose leader row is going away.
    Returns True if the row was kept.

    Work the follower has LOGGED is theirs: the leader deciding not to do an
    exercise says nothing about the sets a partner already lifted, and deleting
    those was data loss on somebody else's phone. Such a row is kept and simply
    stops being shared -- mirrors_id goes, so from here on it is an exercise
    the follower added themselves. An untouched row still disappears.
    """
    # Logged is the one counting rule (Q1): a ticked set with no reps is
    # no work, and it goes with the row.
    if any(stats.set_counts(s.completed, s.reps) for s in row.sets):
        row.mirrors_id = None
        return True
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
    return False


def _place_own_rows(shared, leader, follower, doomed):
    """Slot the follower's OWN rows around the shared ones. Returns True if
    any of them moved.

    The shared rows take the leader's slot numbers, so a row the follower
    created themselves has to be put somewhere those numbers never reach, or
    two exercises end up in one slot in an order the database does not define:

    - a substitute goes wherever the row it stands in for went, however long
      the chain. The follower swapped a busy machine for a free one; when the
      leader moves that exercise, the swap moves with it.
    - everything else -- an exercise they added, or one the leader has since
      removed that they had already logged -- queues up after the last shared
      slot, in the order it already had.
    """
    rows = [se for se in follower.exercises if se not in doomed]
    by_id = {se.id: se for se in rows}
    hidden_ids = {se.replaces_id for se in rows if se.replaces_id}

    def root(se):
        while se.replaces_id and se.replaces_id in by_id:
            se = by_id[se.replaces_id]
        return se

    moved = False

    def move(se, slot):
        nonlocal moved
        if se.position == slot:
            return
        old_position = se.position
        se.position = slot
        if se.id not in hidden_ids:
            reseed_for_slot(follower, se, old_position, slot,
                            user_id=shared.follower_user_id)
        moved = True

    own = sorted((se for se in rows if se.mirrors_id is None),
                 key=lambda se: (se.position, se.id))
    next_slot = max((se.position for se in leader.exercises), default=0)
    for se in own:
        if root(se) is se:
            next_slot += 1
            move(se, next_slot)
    for se in own:
        if root(se) is not se:
            move(se, root(se).position)
    return moved


def _carry_skip(shared, leader_row):
    """The leader just skipped, or un-skipped, one exercise: carry THAT.
    Returns True if the follower's row changed.

    An event rather than part of reconciliation -- see the note in
    reconcile_follower for what mirroring the flag on every structural change
    did to the follower's own choices. Applied with the same meaning a skip
    has on your own screen (gym_toggle_skip_session_exercise): skipping drops
    the pending sets, un-skipping plans the sets still owed -- from the
    FOLLOWER's history, at the follower's slot.

    An exercise the follower has already started is left alone. Their logged
    sets say they are doing it, and yanking it out from under them mid-set is
    exactly the surprise this module exists to avoid.
    """
    if shared is None or shared.accepted_at is None or shared.ended_at is not None:
        return False
    if shared.follower_session_id is None:
        return False
    leader = db.session.get(WorkoutSession, shared.leader_session_id)
    follower = db.session.get(WorkoutSession, shared.follower_session_id)
    if leader is None or follower is None:
        return False
    if leader.user_id != shared.leader_user_id or follower.user_id != shared.follower_user_id:
        return False
    if follower.finished_at is not None or leader_row.session_id != leader.id:
        return False

    row = SessionExercise.query.filter_by(
        session_id=follower.id, mirrors_id=leader_row.id).first()
    if row is None or row.skipped == leader_row.skipped:
        return False
    if leader_row.skipped:
        if any(stats.set_counts(s.completed, s.reps) for s in row.sets):
            return False
        row.skipped = True
        # Only what is still pending, as on your own screen: a ticked set
        # with no reps stays where the lifter left it.
        for pending in [s for s in row.sets if not s.completed]:
            row.sets.remove(pending)
    else:
        row.skipped = False
        row.sets.extend(missing_planned_sets(follower, row,
                                             user_id=shared.follower_user_id))
    follower.structure_version = (follower.structure_version or 0) + 1
    return True


def reconcile_follower(shared):
    """Make the follower's structure mirror the leader's. Returns True if
    anything changed.

    "Structure" is WHICH exercises and in WHAT ORDER -- the two things that
    make it one workout. It is deliberately not everything (owner decision,
    2026-09-20): the follower's own choices stick. A skip travels once, as an
    event (_carry_skip), and is never re-imposed here; a substitute the
    follower made, an exercise they added and work they have logged all
    survive, slotted around the shared rows by _place_own_rows. Order is the
    exception that stays absolute -- the routes refuse a follower's reorder
    while the link is live -- and a row that moves is re-seeded for its new
    slot from the FOLLOWER's history, unless its plan is no longer untouched
    (seeding.reseed_for_slot).

    Idempotent by construction: it compares the two sides and applies the
    difference, so calling it twice is the same as calling it once, and it is
    correct after any structural operation rather than one per operation.

    Rows are matched on SessionExercise.mirrors_id, never on exercise_id: one
    exercise can legitimately appear twice in a session -- an original plus
    the substitute that replaced it -- and a row the follower added on their
    own can name it too.

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

    A newly created follower row IS seeded here, through the same
    _seeded_sets every other path uses (template start, un-skip, reorder,
    gym_add_session_exercise) -- an exercise the leader adds mid-workout used
    to arrive on the follower's side as an empty slot, which is exactly the
    shape that made the first confirmed set complete the exercise and skip
    ahead (see stats.DEFAULT_PLAN_SETS / gym_add_session_exercise). This runs
    inside the LEADER's request, where current_user_id() names the leader, so
    the history lookup is passed shared.follower_user_id explicitly rather
    than left to default. The exercise row is the leader's own too (one
    list), so the user id is the only thing that makes the seeding read the
    FOLLOWER's history rather than the leader's.
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
            row = SessionExercise(
                session_id=follower.id,
                exercise_id=leader_row.exercise_id,
                position=leader_row.position,
                # No rest: the row follows the FOLLOWER's own setting (read at
                # each set), never the leader's per-session override.
                skipped=leader_row.skipped,
                mirrors_id=leader_row.id,
            )
            if not leader_row.skipped:
                # Seeded the same way every other path that creates pending
                # sets is -- see _seeded_sets. An exercise the leader adds
                # mid-workout used to arrive here with none at all, which
                # reproduced this feature's headline bug on the follower's
                # side too: the first confirmed set both created and
                # completed the plan (see stats.DEFAULT_PLAN_SETS and
                # gym_add_session_exercise). user_id is passed explicitly --
                # see the docstring above -- rather than left to default to
                # current_user_id(), which inside this request names the
                # leader. A skipped leader row gets none, matching
                # gym_toggle_skip_session_exercise's own rule that a skipped
                # exercise carries no pending sets.
                # A leader's substitute stands in the follower's own slot
                # too: their routine's count for the exercise it replaces,
                # as target_for and missing_planned_sets read it. The
                # follower row's replaces_id is only set further down, so
                # the leader's chain names the slot (B5 review).
                row.sets.extend(_seeded_sets(follower, leader_row.exercise_id, leader_row.position,
                                             user_id=shared.follower_user_id,
                                             count=plan.slot_count(follower, leader_row)))
            db.session.add(row)
            mirrored[leader_row.id] = row
            changed = True
            continue
        if row.position != leader_row.position:
            old_position = row.position
            row.position = leader_row.position
            # The slot moved, so the plan seeded for the old one is stale --
            # the same reason the leader's own reorder re-seeds. Read from the
            # FOLLOWER's history, and only ever a plan nobody has touched:
            # reseed_for_slot refuses a row with a logged set or a typed
            # weight, which is what keeps "the follower's sets are never
            # touched" true for every set that is actually theirs.
            reseed_for_slot(follower, row, old_position, leader_row.position,
                            user_id=shared.follower_user_id)
            changed = True
        # `skipped` is deliberately NOT compared here. Reconciliation runs
        # after every structural change, so mirroring the flag re-imposed the
        # leader's skips on each one: a follower who skipped an exercise had
        # it un-skipped (with no sets left) the next time the leader swapped
        # two unrelated rows, and one who chose to do an exercise the leader
        # skipped was thrown out of it mid-set. A skip travels once, as the
        # event it is -- see _carry_skip -- and a NEW row above still starts
        # from the leader's flag.

    doomed = set()
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
        # Logged work stays with the follower; an untouched row goes -- the
        # same rule, and the same code, as remove_mirrors_of.
        if not _release_mirror(follower, row):
            doomed.add(row)
        del mirrored[leader_row_id]
        changed = True

    if _place_own_rows(shared, leader, follower, doomed):
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


def propagate_structure(session_, skip_changed=None):
    """Carry this session's structure to every partner who accepted.

    Called by the leader's structural routes after they commit their own
    change. Safe to call on any session: one that leads no link does nothing.

    `skip_changed` is the leader's SessionExercise whose skipped flag the
    calling route just flipped, if that is what happened. Skips are carried as
    that one event (_carry_skip), never re-derived by reconciliation.

    Guarded end to end: this runs entirely inside the LEADER's request, after
    the leader's own change already committed durably. A constraint violation
    originating in the FOLLOWER's data (Fix 1's replaces_id collision before
    it was closed off, say) must never turn into a 500 on someone
    else's request over a write the leader has no way to see or retry. The
    worst case here is the partner falling out of sync until the next
    structural change reconciles cleanly -- never a crash.
    """
    session_id = session_.id
    follower_session_ids = [shared.follower_session_id
                            for shared in active_links_led_by(session_id)]
    if not follower_session_ids:
        return
    try:
        # The follower may be in the middle of a structural write of their
        # own -- adding an exercise, skipping one. Take their session's lock
        # and read their rows as they stand once it is ours (locking.py), or
        # both sides pick "the next free slot" from the same stale rows.
        lock_sessions(follower_session_ids)
        for shared in active_links_led_by(session_id):
            if skip_changed is not None:
                _carry_skip(shared, skip_changed)
            reconcile_follower(shared)
        db.session.commit()
    except (IntegrityError, OperationalError):
        # OperationalError: a lock wait timeout or a deadlock on the
        # partner's rows. It used to escape as a 500 for a change that had
        # already committed -- the screen said "nicht gespeichert", and a
        # retry of "add exercise" added it twice (G-136).
        db.session.rollback()
        current_app.logger.exception(
            'propagate_structure: reconciliation failed for session %s, '
            'partner(s) left out of sync until the next structural change',
            session_id)


def end_links_for(session_):
    """End every link this session takes part in, on either side (end_link):
    pending and declined invites too.

    Whoever finishes first ends the sharing; the other trains on alone, which
    is the whole point -- a workout must never be cut short by someone else's.
    The caller holds the followers' workout locks (handover_session_ids).

    Invites nobody joined are stamped in one statement that expects no row
    count: the leader's "zurückziehen" deletes one under the invitee's lock
    and their OK on a "no" under none, neither under this workout's, so one
    may be gone by the time this writes -- and an update of a row gone was a
    StaleDataError, a 500 for the finish (B11a review). A joined link is only
    ever deleted with a workout, under the lock the caller holds.
    """
    links = (SharedSession.query
             .filter(SharedSession.ended_at.is_(None))
             .filter(db.or_(SharedSession.leader_session_id == session_.id,
                            SharedSession.follower_session_id == session_.id))
             .all())
    unjoined = [shared.id for shared in links if shared.accepted_at is None]
    if unjoined:
        (SharedSession.query
         .filter(SharedSession.id.in_(unjoined), SharedSession.ended_at.is_(None))
         .update({'ended_at': dt.datetime.utcnow()}, synchronize_session=False))
    for shared in links:
        if shared.accepted_at is not None:
            end_link(shared)


def end_link(shared):
    """End one joined link: the stamp, and the follower's order handed over
    (_hand_order_over). Every end goes through here: a finish or a settle
    (end_links_for), a leader's discard, "Nicht mehr mitmachen" and
    "Gemeinsames Training beenden" (the end route), a partner nobody came
    back to (helpers._end_stale_partner_links). The caller holds the
    follower's workout lock and commits."""
    shared.ended_at = dt.datetime.utcnow()
    _hand_order_over(shared)


def _hand_order_over(shared):
    """The ex-follower's order becomes their own without the card moving.
    Returns True if a row moved.

    While the link was live their card held what they had started
    (started_row), wherever the leader's order put it. Alone, the card is the
    first open row -- so an open row the leader had put above it took the
    card the moment the link ended, and the next "Satz geschafft" logged a
    set on a lift they were not at. The started row moves up in front of the
    first open row above it, as a drag there would: what is above stays,
    each slot it passes moves down one, and a replaced original moves with
    its substitute, as _close_position_gaps moves a slot. A row that moves
    is re-seeded for its new slot from the follower's history
    (reseed_for_slot leaves anything ticked, skipped or typed alone). The
    slots keep their numbers, only who holds them changes.

    No structure_version bump: the follower's page asks for the whole
    workout again as it stops following, and a bump would tell them the
    leader had changed the order."""
    if shared.accepted_at is None or shared.follower_session_id is None:
        return False
    follower = db.session.get(WorkoutSession, shared.follower_session_id)
    # The same guards as reconcile_follower: the one other cross-user write.
    if (follower is None or follower.user_id != shared.follower_user_id
            or follower.finished_at is not None):
        return False
    rows = sorted(follower.exercises, key=lambda se: (se.position, se.id))
    by_id = {se.id: se for se in rows}
    hidden_ids = {se.replaces_id for se in rows if se.replaces_id}
    held = started_row([se for se in rows if se.id not in hidden_ids])
    if held is None:
        return False

    def root_id(se):
        while se.replaces_id and se.replaces_id in by_id:
            se = by_id[se.replaces_id]
        return se.id

    slots = {}
    for se in rows:
        slots.setdefault(root_id(se), []).append(se)
    order = list(slots.values())

    def shown(members):
        return next((se for se in members if se.id not in hidden_ids), members[0])

    def is_open(members):
        # The live rule's own test (live._live_context): not skipped, and
        # not every set done -- a row without sets is open.
        row = shown(members)
        return not row.skipped and not (row.sets and all(s.completed for s in row.sets))

    held_at = next(index for index, members in enumerate(order) if held in members)
    first_open = next((index for index in range(held_at) if is_open(order[index])), None)
    if first_open is None:
        return False
    numbers = [shown(members).position for members in order[first_open:held_at + 1]]
    for members, number in zip([order[held_at], *order[first_open:held_at]], numbers):
        for se in members:
            if se.position == number:
                continue
            old_position = se.position
            se.position = number
            if se.id not in hidden_ids:
                reseed_for_slot(follower, se, old_position, number,
                                user_id=shared.follower_user_id)
    return True
