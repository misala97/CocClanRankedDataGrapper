"""One structural write on a workout at a time.

Reordering, removing, skipping, adding and replacing an exercise all read the
session's rows, rearrange them and write back the difference. Two of them
overlapping -- two drops in quick succession on gym wifi, the arrow-key path
(one POST per key press), or a leader's change landing in a follower's session
while the follower edits it -- each read the same starting state, and the
result was a blend: two exercises in one slot, none in another, and before the
plan was rewritten in place, every pending set twice. Both requests answered
200, so nothing on screen said so.

The lock is the WorkoutSession row, taken with SELECT ... FOR UPDATE. What
matters as much as taking it is WHEN this transaction first reads: under
InnoDB's REPEATABLE READ every plain SELECT sees the snapshot established by
the transaction's first plain SELECT, and by the time a route runs, the login
check has already made one. A request that then waited for the lock would go
on to read the state from BEFORE the other request committed, and write its
blend anyway. So the transaction is ended first (nothing is pending at that
point -- callers lock before they change anything), which makes the locking
read the new transaction's first statement. A locking read does not establish
the snapshot; the first plain SELECT after it does, and that is after the
other request has committed.

Not a Flask route module and imported by both routes and sharing.py, for the
same reason seeding.py is its own module: sharing cannot import routes.
"""
from extensions import db
from models import WorkoutSession


def lock_sessions(session_ids):
    """Serialise against every other structural write on these workouts, and
    read what is committed NOW from here on. Call before changing anything:
    this ends the current transaction, so pending changes would be lost, and
    every ORM object loaded earlier is expired and re-read on next access
    (or gone -- re-fetch a row that another request may have deleted).

    Ids are locked in ascending order so two callers can never wait on each
    other. Held until the caller's commit or rollback."""
    ids = sorted({int(session_id) for session_id in session_ids if session_id})
    if not ids:
        return
    db.session.rollback()
    (WorkoutSession.query
     .filter(WorkoutSession.id.in_(ids))
     .order_by(WorkoutSession.id)
     .with_for_update()
     .all())
