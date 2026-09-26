"""One-time: make every workout the old finish closed look as today's finish leaves one.

    python scripts/gym_finish_cleanup.py                  (dry run: the report and its digest)
    python scripts/gym_finish_cleanup.py --commit DIGEST  (does what that dry run reported)
    python scripts/gym_finish_cleanup.py --restore FILE   (puts a backup's rows back)

Workouts finished before the 09-25 deploy (2b4ad68) -- planned_sets NULL:
every finish since is today's _finish_session, which stores it, and B4's
migration added the column without a backfill -- kept what today's finish
never leaves behind (the gym walkthrough's P, DECISIONS "P2"):

- One without a set that counts (helpers._counted) is thrown away, as the
  auto-finish throws away an empty one: its rows, its sets, its pushes and
  every partner link it took part in (helpers._delete_session_and_links).
  The partner's workout stays; a row of theirs that mirrored one of its rows
  loses that pointer (the database's ON DELETE SET NULL).
- One that kept sets that do not count -- open ones, or ticked without reps,
  like the 0 kg x 0 set 39678 --, a push still waiting or a rest still
  running keeps its planned count first (planned_sets: the debrief reads the
  open sets for it until then), then loses them, as the finish does
  (helpers._finish_session). Its rows stay.
- A partner link neither side of which still runs is stamped ended, at the
  first of the two finishes. One whose other side still runs is left to the
  app, which ends it at that side's finish or discard.

A workout today's finish closed (planned_sets stored) is left as it is: what
it holds since is the debrief's doing, which the app keeps -- even with its
last set deleted.
Running workouts are never classified, trimmed or deleted; the one write that
can reach one is that pointer. The rules are the app's own helpers, so the
script says what the app says.

--commit DIGEST locks every row it touches, reads everything again and stops
unless that is exactly what the dry run printing this digest reported. It
writes the backup (every row it deletes, whole; every row it changes, with the
columns it changes) to disk before it changes anything, and commits only once
a new survey finds nothing left to do. --backup PATH (default
~/gym_cleanup_<UTC time>.json; an existing file is refused). --user ID,
repeatable, limits it to those lifters' workouts; a link to another lifter's
workout that goes is left to a run for them.
"""
import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import DateTime, or_, select, update  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app import app  # noqa: E402  (needs the path insert above)
from extensions import db  # noqa: E402
from features.gym import stats  # noqa: E402
from features.gym.locking import lock_sessions  # noqa: E402
from features.gym.routes.helpers import (  # noqa: E402
    _counted, _delete_session_and_links, planned_set_count,
)
from models import (  # noqa: E402
    PendingPush, SessionExercise, SessionSet, SharedSession, WorkoutSession,
)

WORKOUTS = WorkoutSession.__table__
ROWS = SessionExercise.__table__
SETS = SessionSet.__table__
PUSHES = PendingPush.__table__
LINKS = SharedSession.__table__
TABLES = {table.name: table for table in (WORKOUTS, ROWS, SETS, PUSHES, LINKS)}


@dataclasses.dataclass(frozen=True)
class Empty:
    """A workout the old finish closed without a set that counts: thrown away."""
    user_id: int
    started_at: dt.datetime
    finished_at: dt.datetime
    rows: int
    sets: int
    pushes: int
    #: (link id, the other workout's id or None): they go with it.
    links: tuple
    #: What the lifter put on it, said in the report: it goes too.
    bodyweight: object
    #: The exercises of its rows flagged with pain.
    pain: tuple
    #: The notes on it, the workout's first, then its rows'.
    notes: tuple


@dataclasses.dataclass(frozen=True)
class Trim:
    """A workout the old finish closed that keeps what today's finish takes."""
    user_id: int
    finished_at: dt.datetime
    #: planned_sets to store, counted before anything goes.
    planned: int
    #: Every set that does not count: open, or ticked without reps.
    sets: tuple
    #: The ticked ones among them.
    ticked: tuple
    #: Pushes still waiting.
    pushes: tuple
    #: A rest still running (rest_ends_at or resting_set_id).
    rest: bool


@dataclasses.dataclass(frozen=True)
class Plan:
    empty: dict
    #: (workout id, row id) of every row of another workout whose pointer to
    #: a row that goes the database sets NULL.
    pointers: tuple
    trimmed: dict
    #: link id -> (ended_at, leader workout id, follower workout id or None)
    links: dict
    #: link id -> why it is left alone.
    left: dict

    def nothing(self):
        return not (self.empty or self.trimmed or self.links)

    def workouts(self):
        """Every workout the plan writes to, or deletes a link of."""
        ids = set(self.empty) | set(self.trimmed)
        for empty in self.empty.values():
            ids.update(other for _, other in empty.links if other is not None)
        for _, leader, follower in self.links.values():
            ids.update(i for i in (leader, follower) if i is not None)
        return sorted(ids)


def digest(plan):
    """Names exactly this plan: the dry run prints it, --commit wants it back."""
    return hashlib.sha256(repr(plan).encode('utf-8')).hexdigest()[:12]


def _mine(query, column, user_ids):
    return query if user_ids is None else query.filter(column.in_(user_ids))


def _goes(workout):
    """Closed by the old finish with nothing in it that counts."""
    return (workout.finished_at is not None and workout.planned_sets is None
            and not _counted(workout))


def survey(user_ids):
    """What the cleanup would do for these lifters (None: everyone). Reads only."""
    closed = _mine(WorkoutSession.query
                   .filter(WorkoutSession.finished_at.isnot(None),
                           # Stored by today's finish: such a workout is the app's.
                           WorkoutSession.planned_sets.is_(None))
                   .options(selectinload(WorkoutSession.exercises)
                            .selectinload(SessionExercise.sets),
                            selectinload(WorkoutSession.exercises)
                            .selectinload(SessionExercise.exercise),
                            selectinload(WorkoutSession.pending_pushes))
                   .order_by(WorkoutSession.id),
                   WorkoutSession.user_id, user_ids).all()
    empty, trimmed = {}, {}
    for workout in closed:
        # In reading order, and the same in every process -- the digest reads
        # the notes in it: the relationship orders by position alone, and a
        # substitute shares its original's.
        rows = sorted(workout.exercises, key=lambda row: (row.position, row.id))
        sets = [s for row in rows for s in row.sets]
        if _goes(workout):
            links = SharedSession.query.filter(or_(
                SharedSession.leader_session_id == workout.id,
                SharedSession.follower_session_id == workout.id)).order_by(SharedSession.id)
            empty[workout.id] = Empty(
                user_id=workout.user_id, started_at=workout.started_at,
                finished_at=workout.finished_at, rows=len(rows), sets=len(sets),
                pushes=len(workout.pending_pushes),
                links=tuple((link.id, link.follower_session_id
                             if link.leader_session_id == workout.id else link.leader_session_id)
                            for link in links.all()),
                bodyweight=workout.bodyweight_kg,
                pain=tuple(row.exercise.name for row in rows if row.pain),
                notes=tuple(text.strip() for text in [workout.notes, *(row.notes for row in rows)]
                            if (text or '').strip()))
            continue
        doomed = [s for s in sets if not stats.set_counts(s.completed, s.reps)]
        pushes = tuple(push.id for push in workout.pending_pushes if not push.sent)
        rest = workout.rest_ends_at is not None or workout.resting_set_id is not None
        if doomed or pushes or rest:
            trimmed[workout.id] = Trim(
                user_id=workout.user_id, finished_at=workout.finished_at,
                # Counted before anything goes, as the finish counts it.
                planned=planned_set_count(workout),
                sets=tuple(sorted(s.id for s in doomed)),
                ticked=tuple(sorted(s.id for s in doomed if s.completed)),
                pushes=tuple(sorted(pushes)), rest=rest)

    pointers = ()
    if empty:
        gone = select(ROWS.c.id).where(ROWS.c.session_id.in_(empty))
        pointers = tuple(sorted(tuple(row) for row in db.session.execute(
            select(ROWS.c.session_id, ROWS.c.id).where(
                or_(ROWS.c.replaces_id.in_(gone), ROWS.c.mirrors_id.in_(gone)),
                ROWS.c.session_id.notin_(empty)))))

    stamps, left = {}, {}
    links = SharedSession.query.filter(SharedSession.ended_at.is_(None))
    if user_ids is not None:
        links = links.filter(or_(SharedSession.leader_user_id.in_(user_ids),
                                 SharedSession.follower_user_id.in_(user_ids)))
    for link in links.order_by(SharedSession.id).all():
        sides = [db.session.get(WorkoutSession, link.leader_session_id)]
        if link.follower_session_id is not None:
            sides.append(db.session.get(WorkoutSession, link.follower_session_id))
        if any(side.id in empty for side in sides):
            continue  # goes with the empty workout
        going = [side for side in sides if _goes(side)]
        if going:
            left[link.id] = (f'workout {going[0].id} of user {going[0].user_id} goes, '
                             'and the link with it, in a run for that lifter')
            continue
        ends = [side.finished_at for side in sides if side.finished_at is not None]
        if not ends:
            continue  # live, or an invite still open: not this script's
        if len(ends) < len(sides):
            left[link.id] = 'one side still runs: the app ends it'
            continue
        stamps[link.id] = (min(ends), link.leader_session_id, link.follower_session_id)
    return Plan(empty=empty, pointers=pointers, trimmed=trimmed, links=stamps, left=left)


def _lock(plan):
    """Holds every row `plan` reads or writes until the commit or rollback,
    in the app's order: the workouts first (lock_sessions -- which ends the
    transaction, so what is read from here on is what is there now), then
    their rows, sets, pushes and links. The debrief writes sets and rows
    without the workout's lock; a set added to a held row waits too."""
    ids = plan.workouts()
    lock_sessions(ids)

    def hold(table, column, values):
        if not values:
            return []
        return [row.id for row in db.session.execute(
            select(table.c.id).where(column.in_(sorted(values)))
            .order_by(table.c.id).with_for_update())]

    rows = hold(ROWS, ROWS.c.session_id, ids)
    hold(ROWS, ROWS.c.id, [row for _, row in plan.pointers])
    hold(SETS, SETS.c.session_exercise_id, rows)
    hold(PUSHES, PUSHES.c.session_id, ids)
    # Every link the plan writes has its leader among the workouts.
    hold(LINKS, LINKS.c.leader_session_id, ids)


def apply(plan):
    """Does what `plan` says, flushed, not committed."""
    for workout_id in plan.empty:
        _delete_session_and_links(db.session.get(WorkoutSession, workout_id), commit=False)
    for workout_id, trim in plan.trimmed.items():
        workout = db.session.get(WorkoutSession, workout_id)
        workout.planned_sets = trim.planned
        workout.rest_ends_at = None
        # Before the sets go: the pointer is a foreign key to one of them.
        workout.resting_set_id = None
        db.session.flush()
        doomed, pushes = set(trim.sets), set(trim.pushes)
        for row in workout.exercises:
            for s in [s for s in row.sets if s.id in doomed]:
                row.sets.remove(s)
        for push in [push for push in workout.pending_pushes if push.id in pushes]:
            workout.pending_pushes.remove(push)
    for link_id, (ended_at, _, _) in plan.links.items():
        db.session.get(SharedSession, link_id).ended_at = ended_at
    db.session.flush()


def _json(row):
    return {key: value.isoformat() if isinstance(value, dt.datetime) else value
            for key, value in row.items()}


def _rows(table, ids):
    if not ids:
        return []
    found = db.session.execute(
        select(table).where(table.c.id.in_(sorted(ids))).order_by(table.c.id)).mappings()
    return [_json(row) for row in found]


def backup_of(plan):
    """Every row `plan` deletes, whole, and every row it changes, with the
    columns it changes -- read before anything is changed."""
    empty = sorted(plan.empty)
    rows = [r.id for r in db.session.execute(
        select(ROWS.c.id).where(ROWS.c.session_id.in_(empty)))] if empty else []
    sets = {s.id for s in db.session.execute(
        select(SETS.c.id).where(SETS.c.session_exercise_id.in_(rows)))} if rows else set()
    pushes = {p.id for p in db.session.execute(
        select(PUSHES.c.id).where(PUSHES.c.session_id.in_(empty)))} if empty else set()
    links = {link.id for link in db.session.execute(select(LINKS.c.id).where(or_(
        LINKS.c.leader_session_id.in_(empty),
        LINKS.c.follower_session_id.in_(empty))))} if empty else set()
    for trim in plan.trimmed.values():
        sets.update(trim.sets)
        pushes.update(trim.pushes)
    return {
        'made_at': dt.datetime.utcnow().isoformat(),
        'database': db.engine.url.database,
        'digest': digest(plan),
        'deleted': {
            WORKOUTS.name: _rows(WORKOUTS, empty),
            ROWS.name: _rows(ROWS, rows),
            SETS.name: _rows(SETS, sets),
            PUSHES.name: _rows(PUSHES, pushes),
            LINKS.name: _rows(LINKS, links),
        },
        'changed': {
            WORKOUTS.name: {'columns': ['planned_sets', 'rest_ends_at', 'resting_set_id'],
                            'rows': _rows(WORKOUTS, list(plan.trimmed))},
            LINKS.name: {'columns': ['ended_at'], 'rows': _rows(LINKS, list(plan.links))},
            # The database sets these pointers NULL (ON DELETE SET NULL).
            ROWS.name: {'columns': ['replaces_id', 'mirrors_id'],
                        'rows': _rows(ROWS, [row for _, row in plan.pointers])},
        },
    }


def _durable(path):
    """The backup's directory entry on disk as well as its bytes: a crash
    just after the commit must not take the file with it. POSIX only --
    Windows cannot open a directory."""
    if os.name == 'nt':
        return
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _typed(table, row):
    return {key: (dt.datetime.fromisoformat(value)
                  if value is not None and isinstance(table.c[key].type, DateTime) else value)
            for key, value in row.items()}


def restore(backup):
    """Puts a backup's rows back, in one transaction: the deleted ones as
    they were, then the changed columns. Committed."""
    deleted, changed = backup['deleted'], backup['changed']
    for name, rows in deleted.items():
        table = TABLES[name]
        ids = [row['id'] for row in rows]
        if ids and db.session.execute(select(table.c.id).where(table.c.id.in_(ids))).first():
            sys.exit(f'{name}: rows of this backup are there already -- restored before? '
                     'Nothing written.')
    workouts = [_typed(WORKOUTS, row) for row in deleted[WORKOUTS.name]]
    rows = [_typed(ROWS, row) for row in deleted[ROWS.name]]
    # Pointers into rows not back yet are set once everything is.
    if workouts:
        db.session.execute(WORKOUTS.insert(), [{**w, 'resting_set_id': None} for w in workouts])
    if rows:
        db.session.execute(ROWS.insert(), [{**r, 'replaces_id': None, 'mirrors_id': None}
                                           for r in rows])
    for name in (SETS.name, PUSHES.name, LINKS.name):
        if deleted[name]:
            db.session.execute(TABLES[name].insert(),
                               [_typed(TABLES[name], row) for row in deleted[name]])
    for r in rows:
        db.session.execute(update(ROWS).where(ROWS.c.id == r['id']).values(
            replaces_id=r['replaces_id'], mirrors_id=r['mirrors_id']))
    for w in workouts:
        db.session.execute(update(WORKOUTS).where(WORKOUTS.c.id == w['id']).values(
            resting_set_id=w['resting_set_id']))
    for name, block in changed.items():
        table = TABLES[name]
        for row in block['rows']:
            row = _typed(table, row)
            db.session.execute(update(table).where(table.c.id == row['id']).values(
                {column: row[column] for column in block['columns']}))
    db.session.commit()


def _count(n, one, many):
    return f'{n} {one if n == 1 else many}'


def _said(text, limit=120):
    text = ' '.join(text.split())
    return f'"{text if len(text) <= limit else text[:limit - 3] + "..."}"'


def _when(moment):
    """Stored in UTC; said as the app shows it, in local time -- the report
    is checked against Verlauf."""
    return stats.to_local(moment)


def report(plan, say=print):
    say('Times are local, as the app shows them.')
    say('Workouts the old finish closed without a set that counts, thrown away: '
        f'{len(plan.empty)}')
    for workout_id, e in plan.empty.items():
        parts = [f'{_count(e.rows, "row", "rows")}, {_count(e.sets, "set", "sets")}, '
                 f'{_count(e.pushes, "push", "pushes")}']
        if e.links:
            parts.append('links ' + ', '.join(
                f'{link_id} (with workout {other})' if other is not None
                else f'{link_id} (an invite)' for link_id, other in e.links))
        if e.bodyweight is not None:
            parts.append(f'bodyweight {e.bodyweight:g} kg')
        if e.pain:
            parts.append('pain: ' + ', '.join(e.pain))
        if e.notes:
            parts.append('notes: ' + ' / '.join(map(_said, e.notes)))
        start, end = _when(e.started_at), _when(e.finished_at)
        span = f'{start:%Y-%m-%d %H:%M} to ' + (
            f'{end:%H:%M}' if end.date() == start.date() else f'{end:%Y-%m-%d %H:%M}')
        say(f'  {workout_id}  user {e.user_id}  {span}  ' + '; '.join(parts))
    if plan.pointers:
        say('Rows of other workouts that lose their pointer to a row thrown away '
            f'(the database sets it NULL; their sets stay): {len(plan.pointers)}')
        say('  ' + ', '.join(f'row {row} of workout {workout}' for workout, row in plan.pointers))
    say('Workouts the old finish closed that keep what today\'s finish takes: '
        f'{len(plan.trimmed)}')
    for workout_id, t in plan.trimmed.items():
        parts = [f'planned_sets {t.planned} stored']
        if len(t.sets) > len(t.ticked):
            parts.append(f'open sets go: {len(t.sets) - len(t.ticked)}')
        if t.ticked:
            parts.append('ticked without reps go: ' + ', '.join(map(str, t.ticked)))
        if t.pushes:
            parts.append('waiting pushes go: ' + ', '.join(map(str, t.pushes)))
        if t.rest:
            parts.append('a rest still running is cleared')
        say(f'  {workout_id}  user {t.user_id}  finished {_when(t.finished_at):%Y-%m-%d}  '
            + '; '.join(parts))
    say(f'Partner links neither side of which runs, stamped ended: {len(plan.links)}')
    for link_id, (ended_at, leader, follower) in plan.links.items():
        say(f'  {link_id}  workouts {leader} and {follower if follower is not None else "-"}'
            f'  ended_at {_when(ended_at):%Y-%m-%d %H:%M:%S}')
    if plan.left:
        say(f'Partner links left alone: {len(plan.left)}')
        for link_id, why in plan.left.items():
            say(f'  {link_id}  {why}')


def run(user_ids, commit=None, backup_path=None, say=print):
    """The dry run, or with `commit` -- the digest a dry run printed -- the
    cleanup that dry run reported. Returns the plan it did or would do;
    exits, writing nothing, when the rows are not what that dry run read."""
    url = db.engine.url
    say(f'database {url.database} on {url.host}'
        + (f', lifters {", ".join(map(str, user_ids))}' if user_ids is not None else ''))
    plan = survey(user_ids)
    if commit is None or plan.nothing():
        report(plan, say)
        db.session.rollback()
        say('Nothing to do.' if plan.nothing() else
            f'Dry run -- nothing written. To do exactly this: --commit {digest(plan)}')
        return plan
    path = Path(backup_path) if backup_path else (
        Path.home() / f'gym_cleanup_{dt.datetime.utcnow():%Y%m%d-%H%M%S}.json')
    if path.exists():
        db.session.rollback()
        sys.exit(f'{path} is there already. Nothing written; name another with --backup.')
    if digest(plan) == commit:
        _lock(plan)
        plan = survey(user_ids)
    report(plan, say)
    if digest(plan) != commit:
        db.session.rollback()
        sys.exit(f'That is not what the dry run printing {commit} reported: above is what is '
                 'there now. Nothing written; run the dry run again.')
    with open(path, 'x', encoding='utf-8') as out:
        json.dump(backup_of(plan), out, indent=1)
        out.flush()
        os.fsync(out.fileno())
    _durable(path)
    apply(plan)
    if not survey(user_ids).nothing():
        db.session.rollback()
        sys.exit(f'A survey after the cleanup still found work. Rolled back, nothing written '
                 f'(the backup {path} holds rows that are all still there).')
    db.session.commit()
    say(f'Done. Backup: {path}')
    say(f'To undo: python scripts/gym_finish_cleanup.py --restore {path}')
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='One-time: make every workout the old finish closed look as today\'s '
                    'finish leaves one.')
    parser.add_argument('--commit', metavar='DIGEST',
                        help='do what the dry run printing this digest reported')
    parser.add_argument('--user', type=int, action='append', dest='users',
                        help='only this lifter (repeatable)')
    parser.add_argument('--backup', help='where the backup goes (default ~/gym_cleanup_<UTC>.json)')
    parser.add_argument('--restore', metavar='FILE', help='put a backup\'s rows back')
    args = parser.parse_args(argv)
    with app.app_context():
        if args.restore:
            with open(args.restore, encoding='utf-8') as source:
                restore(json.load(source))
            print(f'Restored {args.restore}.')
            return
        run(args.users, args.commit, args.backup)


if __name__ == '__main__':
    main()
