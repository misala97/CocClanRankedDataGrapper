"""Which exercise of a workout is live, and the rows that is read from.

A leaf module: it imports no other routes module. The live screen
(workout._live_data) and the partner's view of it (partner_view) both need
the one rule, and partner_view is imported BY workout -- so the rule lives
here, where both can import it. Moved verbatim from workout.py (I5).
"""
from sqlalchemy.orm import joinedload, selectinload

from models import SessionExercise

from ..sharing import started_row


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
        # from a busy machine. Most recently logged wins if there are two
        # (sharing.started_row, which the link's end hands over).
        live_se = started_row(visible_exercises)
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
