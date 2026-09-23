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
from models import (Exercise, ExerciseSettings, SessionExercise, TemplateExercise,
                    WorkoutSession, WorkoutTemplate)

from .library import BY_KEY, LIBRARY, fold

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


def list_values(exercise):
    return {field: getattr(exercise, attr) for field, attr in LIST_ATTR.items()}


def resolve(list_values, stored):
    """The lifter's value where one is stored, the list's everywhere else.
    `stored` is a settings row's values (or None for no row)."""
    stored = stored or {}
    values, changed = {}, set()
    for field in PERSONAL_FIELDS:
        own = stored.get(field)
        if own is None or own == []:
            values[field] = list_values.get(field)
        else:
            values[field] = own
            changed.add(field)
    return Setup(**values, changed=frozenset(changed))


def to_store(list_values, submitted, equipment):
    """What a settings row holds for the values a lifter submitted.

    `submitted` maps each field the form sent to its parsed value, None for a
    blank. A blank or the list's own value stores None ("the list's value").
    A bar of 0 means nothing sits inside the number, which is only worth
    storing where the list has a bar to switch off. Stack stops mean
    something on a stack only, ascending.
    """
    stored = {}
    for field, value in submitted.items():
        base = list_values.get(field)
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


def setups(user_id, exercises):
    """{exercise_id: Setup} for one lifter, in one query."""
    exercises = [exercise for exercise in exercises if exercise is not None]
    ids = {exercise.id for exercise in exercises}
    stored = {}
    if ids and user_id is not None:
        stored = {row.exercise_id: _stored(row) for row in ExerciseSettings.query.filter(
            ExerciseSettings.user_id == user_id, ExerciseSettings.exercise_id.in_(ids))}
    return {exercise.id: resolve(list_values(exercise), stored.get(exercise.id))
            for exercise in exercises}


def setup(user_id, exercise):
    return setups(user_id, [exercise])[exercise.id]


def save_setup(user_id, exercise, submitted):
    """Store what a lifter submitted for an exercise (see to_store); fields
    not in `submitted` keep their stored value. The caller commits."""
    values = to_store(list_values(exercise), submitted, exercise.equipment)
    row = ExerciseSettings.query.filter_by(user_id=user_id, exercise_id=exercise.id).first()
    if row is None:
        if all(value is None for value in values.values()):
            return resolve(list_values(exercise), None)
        row = ExerciseSettings(user_id=user_id, exercise_id=exercise.id)
        db.session.add(row)
    for field, value in values.items():
        setattr(row, field, value)
    stored = _stored(row)
    if all(value is None for value in stored.values()):
        db.session.delete(row)
        return resolve(list_values(exercise), None)
    return resolve(list_values(exercise), stored)
