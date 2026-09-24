"""The exercise rows, and each lifter's view of them.

Since 2026-09-23 there is one exercise list for everyone (owner: "One list
of preconfigured read only exercises for every user"). library.py holds it
as data; every entry has exactly one row in gym_exercises, keyed by
`library_key`, so a routine, a session and a shared workout all name an
exercise by the same id. Nobody creates, renames or deletes one -- the list
grows in code.

Four values stay personal, because they are facts about one lifter's gym or
habits rather than about the movement: the step, the rest, the real stops
of an uneven stack and the bar inside the number (PERSONAL_FIELDS). The row
holds the list's value for each (Exercise.list_*); gym_exercise_settings
holds a lifter's own value only while it differs, so a later change to the
list still reaches everyone who never changed it. `Setup` is the result:
what one lifter's copy of an exercise effectively is.

The rest has one more level (V3, "Deine Pause"): a lifter may set one rest
for all of their exercises (LifterSettings). It sits between the two -- the
exercise's own rest, else the rest for all, else the list's -- and an
exercise's own rest is then an exception to it: submitting the rest for all
stores nothing, and switching the rest for all on absorbs the own rests
equal to it (set_rest_for_all).

The user for a Setup always comes from the data being built -- the
session's or the routine's owner -- never from the request: the leader's
request reconciles the follower's rows, and those take the follower's rest.
And because an exercise id no longer implies a user, every read from an
exercise into sessions, sets or routines filters by the lifter reading.
"""
import logging
import math
import threading
from dataclasses import dataclass

from flask import abort
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (Exercise, ExerciseSettings, LifterSettings, SessionExercise, SessionSet,
                    TemplateExercise, WorkoutSession, WorkoutTemplate)

from .library import BY_KEY, LIBRARY, REST_TIERS, fold

log = logging.getLogger(__name__)

PERSONAL_FIELDS = ('weight_increment', 'default_rest_seconds', 'stack_kg', 'bar_weight')

# The Exercise attribute that holds the list's value for each personal field.
# The columns keep their old names; the attributes do not, so a leftover read
# of `exercise.weight_increment` fails instead of quietly answering with the
# list's value where the lifter's was meant.
LIST_ATTR = {
    'weight_increment': 'list_increment',
    'default_rest_seconds': 'list_rest_seconds',
    'stack_kg': 'list_stack_kg',
    'bar_weight': 'list_bar_weight',
}


def entry_values(entry):
    """The gym_exercises columns for one library entry. The list states no
    stack stops -- a gym's uneven stack is a lifter's setting."""
    return {
        'library_key': entry.key,
        'name': entry.name,
        'muscle_group': entry.group,
        'secondary_muscle_groups': list(entry.secondary),
        'equipment': entry.equipment,
        'is_unilateral': entry.unilateral,
        'weight_increment': entry.increment,
        'default_rest_seconds': entry.rest,
        'bar_weight': entry.bar,
        'stack_kg': None,
    }


def _same(stored, wanted):
    if isinstance(wanted, float) and isinstance(stored, (int, float)):
        # FLOAT columns are single precision in MySQL.
        return math.isclose(stored, wanted, rel_tol=1e-6)
    if isinstance(wanted, list) and stored is not None:
        return list(stored) == wanted
    return stored == wanted


def sync_plan(existing, library=LIBRARY):
    """What it takes to make the rows match the list.

    `existing` maps library_key to that row's columns. Returns (inserts,
    updates): the column values of every missing entry, and for each stored
    entry that drifted, (key, {column: new value}) with only what changed.
    Never a delete -- a key that left the list keeps its row, and its
    history, and is simply not offered any more.
    """
    inserts, updates = [], []
    for entry in library:
        wanted = entry_values(entry)
        stored = existing.get(entry.key)
        if stored is None:
            inserts.append(wanted)
            continue
        changed = {column: value for column, value in wanted.items()
                   if column != 'library_key' and not _same(stored.get(column), value)}
        if changed:
            updates.append((entry.key, changed))
    return inserts, updates


@dataclass(frozen=True)
class Setup:
    """One lifter's effective values for one exercise."""
    weight_increment: float | None
    default_rest_seconds: int | None
    stack_kg: list | None
    bar_weight: float | None
    # The fields where the lifter's own value is in use.
    changed: frozenset = frozenset()
    # The lifter's rest for all their exercises, where they set one: what an
    # exercise without its own rest takes before the list's.
    rest_for_all: int | None = None


def list_values(exercise):
    return {field: getattr(exercise, attr) for field, attr in LIST_ATTR.items()}


def resolve(list_values, stored, rest_for_all=None):
    """The lifter's value where one is stored, the list's everywhere else --
    except the rest, where the lifter's rest for all their exercises comes
    between the two. `stored` is a settings row's values (or None for no
    row)."""
    stored = stored or {}
    values, changed = {}, set()
    for field in PERSONAL_FIELDS:
        own = stored.get(field)
        if own is not None and own != []:
            values[field] = own
            changed.add(field)
        elif field == 'default_rest_seconds' and rest_for_all is not None:
            values[field] = rest_for_all
        else:
            values[field] = list_values.get(field)
    return Setup(**values, changed=frozenset(changed), rest_for_all=rest_for_all)


def to_store(list_values, submitted, equipment, rest_for_all=None):
    """What a settings row holds for the values a lifter submitted.

    `submitted` maps each field the form sent to its parsed value, None for a
    blank. A blank or the value the field falls back to stores None: the
    list's, or for the rest the lifter's rest for all where they set one --
    so an own rest is exactly an exception to it. A bar of 0 means nothing
    sits inside the number, which is only worth storing where the list has a
    bar to switch off. Stack stops mean something on a stack only, ascending.
    """
    stored = {}
    for field, value in submitted.items():
        base = list_values.get(field)
        if field == 'default_rest_seconds' and rest_for_all is not None:
            base = rest_for_all
        if field == 'stack_kg':
            value = sorted(value) if value and equipment == 'stack' else None
            if value is not None and base and value == sorted(base):
                value = None
        elif field == 'bar_weight':
            if value is not None and _same(base or 0.0, float(value)):
                value = None
        elif value is not None and base is not None and _same(base, value):
            value = None
        stored[field] = value
    return stored


# -- the rows -----------------------------------------------------------------

_synced = False
_sync_lock = threading.Lock()


def sync_library(connection):
    """Make gym_exercises match library.py on `connection`; (inserted,
    updated). Core statements only, so it can run on a connection of its
    own and never commits a request's pending ORM work."""
    table = Exercise.__table__
    columns = [table.c[name] for name in entry_values(LIBRARY[0])]
    stored = {row['library_key']: dict(row) for row in connection.execute(
        select(*columns).where(table.c.library_key.isnot(None))).mappings()}
    inserts, updates = sync_plan(stored)
    if inserts:
        connection.execute(table.insert(), inserts)
    for key, values in updates:
        for fact in ('is_unilateral', 'equipment'):
            if fact in values:
                # Every history on the row is re-read through it: a changed
                # side doubles or halves all of its volume.
                log.warning('exercise list: %s %s %r -> %r', key, fact,
                            stored[key][fact], values[fact])
        connection.execute(table.update().where(table.c.library_key == key).values(**values))
    return len(inserts), len(updates)


def ensure_library():
    """sync_library() once per process, before the first gym request.

    A list that grows in code needs no deploy step this way. With several
    workers starting at once, the loser of a race on a new key gets an
    IntegrityError from the unique library_key and simply syncs again.
    """
    global _synced
    if _synced:
        return
    with _sync_lock:
        if _synced:
            return
        for attempt in (1, 2):
            try:
                with db.engine.begin() as connection:
                    sync_library(connection)
                break
            except IntegrityError:
                if attempt == 2:
                    raise
        _synced = True


def library_exercises():
    """What the picker offers: every row whose key is in today's list."""
    keys = [entry.key for entry in LIBRARY]
    return Exercise.query.filter(Exercise.library_key.in_(keys)).order_by(Exercise.name).all()


def touched_exercises(user_id):
    """A lifter's own exercises: logged in one of their sessions, kept in one
    of their routines, or set up in their settings."""
    logged = (select(SessionExercise.exercise_id)
              .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
              .where(WorkoutSession.user_id == user_id))
    kept = (select(TemplateExercise.exercise_id)
            .join(WorkoutTemplate, TemplateExercise.template_id == WorkoutTemplate.id)
            .where(WorkoutTemplate.user_id == user_id))
    set_up = select(ExerciseSettings.exercise_id).where(ExerciseSettings.user_id == user_id)
    return (Exercise.query
            .filter(or_(Exercise.id.in_(logged), Exercise.id.in_(kept), Exercise.id.in_(set_up)))
            .order_by(Exercise.name).all())


# -- what a lifter actually does ------------------------------------------------

# How fast an old workout stops counting towards the exercise you mainly do:
# one six weeks ago weighs half of one today.
USAGE_HALF_LIFE_DAYS = 42
# The add sheet's "Deine": done in at least two workouts -- once is a try, not
# a habit -- and still weighing 15% of your most-done exercise, so what you
# moved on from sinks out by itself. Beside a weekly regular that is about two
# workouts in the last three weeks. Relative, not absolute: after a break
# every weight has shrunk alike, and your usual exercises are exactly what you
# come back to.
COMMON_MIN_WORKOUTS = 2
COMMON_MIN_SHARE = 0.15


@dataclass(frozen=True)
class Usage:
    """One lifter's record with one exercise."""
    workouts: int       # finished workouts with a completed set of it
    last_done: object   # the latest of them, naive UTC
    rank: int           # 1 = what they do most, recent weeks weighing more
    common: bool        # listed under "Deine" in the add sheet


def usage(user_id, now):
    """{exercise_id: Usage} for every list exercise the lifter has done: in a
    finished workout of theirs, with at least one completed set. A workout
    counts once however often the exercise was in it.

    Only what the picker offers (library_exercises) is ranked: a row that has
    left the list can't be added again, and a big old habit on one would
    still set the bar for what counts as common."""
    rows = (db.session.query(SessionExercise.exercise_id, WorkoutSession.id,
                             WorkoutSession.started_at)
            .join(WorkoutSession, SessionExercise.session_id == WorkoutSession.id)
            .join(SessionSet, SessionSet.session_exercise_id == SessionExercise.id)
            .join(Exercise, SessionExercise.exercise_id == Exercise.id)
            .filter(WorkoutSession.user_id == user_id,
                    WorkoutSession.finished_at.isnot(None),
                    Exercise.library_key.in_([entry.key for entry in LIBRARY]),
                    SessionSet.completed == True)  # noqa: E712
            .distinct()
            .all())
    done = {}
    for exercise_id, session_id, started_at in rows:
        done.setdefault(exercise_id, {})[session_id] = started_at
    weight = {
        exercise_id: sum(0.5 ** (max((now - started).total_seconds(), 0) / 86400
                                 / USAGE_HALF_LIFE_DAYS)
                         for started in sessions.values())
        for exercise_id, sessions in done.items()
    }
    # Ties go to more workouts, then the more recent; the id only keeps the
    # order stable.
    ranked = sorted(sorted(done), reverse=True,
                    key=lambda i: (weight[i], len(done[i]), max(done[i].values())))
    top = weight[ranked[0]] if ranked else 0.0
    return {
        exercise_id: Usage(
            workouts=len(done[exercise_id]),
            last_done=max(done[exercise_id].values()),
            rank=place,
            common=(len(done[exercise_id]) >= COMMON_MIN_WORKOUTS
                    and weight[exercise_id] >= COMMON_MIN_SHARE * top),
        )
        for place, exercise_id in enumerate(ranked, start=1)
    }


def search_text(exercise):
    """What the add sheet searches (library.matches): the entry's folded name
    and aliases -- which hold every name the lifters used before the list --
    or, for a row that has left the list, its folded name."""
    entry = BY_KEY.get(exercise.library_key)
    return entry.search_text if entry else fold(exercise.name)


def exercise_or_404(exercise_id):
    """Any exercise row. No ownership check: the row is everyone's, and the
    history hanging off it is scoped where it is read."""
    row = db.session.get(Exercise, exercise_id)
    if row is None:
        abort(404)
    return row


# -- a lifter's settings -----------------------------------------------------

def _stored(row):
    return {field: getattr(row, field) for field in PERSONAL_FIELDS}


def rest_for_all(user_id):
    """The lifter's rest for all their exercises, or None: by kind of
    exercise, the list's rest for each."""
    if user_id is None:
        return None
    row = db.session.get(LifterSettings, user_id)
    return row.rest_seconds if row is not None else None


def setups(user_id, exercises):
    """{exercise_id: Setup} for one lifter, in two queries."""
    exercises = [exercise for exercise in exercises if exercise is not None]
    ids = {exercise.id for exercise in exercises}
    stored, everyone = {}, None
    if ids and user_id is not None:
        stored = {row.exercise_id: _stored(row) for row in ExerciseSettings.query.filter(
            ExerciseSettings.user_id == user_id, ExerciseSettings.exercise_id.in_(ids))}
        everyone = rest_for_all(user_id)
    return {exercise.id: resolve(list_values(exercise), stored.get(exercise.id), everyone)
            for exercise in exercises}


def setup(user_id, exercise):
    return setups(user_id, [exercise])[exercise.id]


def save_setup(user_id, exercise, submitted):
    """Store what a lifter submitted for an exercise (see to_store); fields
    not in `submitted` keep their stored value. The caller commits."""
    everyone = rest_for_all(user_id)
    values = to_store(list_values(exercise), submitted, exercise.equipment, everyone)
    row = ExerciseSettings.query.filter_by(user_id=user_id, exercise_id=exercise.id).first()
    if row is None:
        if all(value is None for value in values.values()):
            return resolve(list_values(exercise), None, everyone)
        row = ExerciseSettings(user_id=user_id, exercise_id=exercise.id)
        db.session.add(row)
    for field, value in values.items():
        setattr(row, field, value)
    stored = _stored(row)
    if all(value is None for value in stored.values()):
        db.session.delete(row)
        return resolve(list_values(exercise), None, everyone)
    return resolve(list_values(exercise), stored, everyone)


# The rest for all is set in 15-second steps between these; an exercise's own
# rest in the same range (the settings form refuses nothing, but a stepper
# needs ends).
REST_MIN_SECONDS, REST_MAX_SECONDS = 15, 600
# One tap of "−15" / "+15" on a running rest's countdown band.
REST_NUDGE_SECONDS = 15
# Where "Eine für alle" starts when the lifter has no rest of their own yet.
REST_FOR_ALL_START = 120


def set_rest_for_all(user_id, seconds):
    """Set a lifter's rest for all their exercises; None goes back to "by
    kind of exercise" (the list's rest for each). The caller commits.

    Switching it on absorbs: every exercise rest of theirs equal to it is
    dropped, so twelve single rests, ten of them 2:30, become 2:30 for all
    and two exceptions -- which a later change of the rest for all then
    moves together. Changing it, or switching it off, touches no exercise:
    the stepper walks through values, and an exception it passed over must
    still be one when it stops.
    """
    row = db.session.get(LifterSettings, user_id)
    switching_on = seconds is not None and (row is None or row.rest_seconds is None)
    if seconds is None:
        if row is not None:
            db.session.delete(row)
        return
    if row is None:
        row = LifterSettings(user_id=user_id)
        db.session.add(row)
    row.rest_seconds = seconds
    if not switching_on:
        return
    for settings in ExerciseSettings.query.filter_by(user_id=user_id,
                                                     default_rest_seconds=seconds).all():
        settings.default_rest_seconds = None
        if all(value is None for value in _stored(settings).values()):
            db.session.delete(settings)


def rest_overview(user_id):
    """"Deine Pause" as the Übungen page shows it: the rest for all (None:
    by kind of exercise), every exercise with a rest of its own -- the
    exceptions -- by name, where "Eine für alle" starts (the rest for all,
    else the lifter's most common own rest, the longer on a tie, else
    REST_FOR_ALL_START) and the list's range, which "by kind" means."""
    everyone = rest_for_all(user_id)
    own = (db.session.query(Exercise.id, Exercise.name, ExerciseSettings.default_rest_seconds)
           .join(ExerciseSettings, ExerciseSettings.exercise_id == Exercise.id)
           .filter(ExerciseSettings.user_id == user_id,
                   ExerciseSettings.default_rest_seconds.isnot(None))
           .order_by(Exercise.name).all())
    counts = {}
    for _, _, seconds in own:
        counts[seconds] = counts.get(seconds, 0) + 1
    start = everyone
    if start is None:
        start = max(counts, key=lambda s: (counts[s], s)) if counts else REST_FOR_ALL_START
    return {
        'rest_for_all': everyone,
        'exceptions': [{'exercise_id': exercise_id, 'name': name, 'rest_seconds': seconds}
                       for exercise_id, name, seconds in own],
        'start_seconds': start,
        'list_min_seconds': min(REST_TIERS),
        'list_max_seconds': max(REST_TIERS),
        'min_seconds': REST_MIN_SECONDS,
        'max_seconds': REST_MAX_SECONDS,
    }


def settle_rests(session_):
    """Write the rest in force into every row of a finishing workout that
    followed the lifter's setting (rest_seconds NULL): the setting may
    change tomorrow, and the history ("Pause geplant" against the time
    taken) must keep the rest that applied. The caller commits."""
    rows = [se for se in session_.exercises if se.rest_seconds is None]
    if not rows:
        return
    resolved = setups(session_.user_id, [se.exercise for se in rows])
    for se in rows:
        se.rest_seconds = resolved[se.exercise_id].default_rest_seconds
