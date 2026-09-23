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
import math
from dataclasses import dataclass

from .library import LIBRARY

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
