"""Pure analysis for the gym tracker.

No Flask, no SQLAlchemy, no queries, no I/O. Every function takes
already-loaded data and returns plain Python, which is what makes the maths
checkable without an app context or a database (see tests/test_gym_stats.py).
If something here needs a query, it belongs in routes.py instead.

The single input shape is PerformedExercise: one exercise as it was actually
performed in one session, carrying only *completed* sets. routes.py builds
these from the ORM in one pass and everything here consumes them.
"""
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

# Sessions in a row without a new estimated-1RM PR before an exercise counts
# as stagnating. 4 is roughly a month of training a lift once or twice a week
# -- long enough that it is a real plateau, short enough to still act on.
STAGNATION_THRESHOLD = 4

# Rolling window for "how am I doing lately" figures: balance, consistency.
ROLLING_WINDOW_DAYS = 28

# How many ISO weeks of tonnage to plot, including the current partial one.
TONNAGE_WEEKS = 8

# A muscle group with fewer than this share of the best-served group's working
# sets counts as under-trained. Relative rather than absolute so the flag stays
# meaningful as overall training volume changes.
UNDER_TRAINED_RATIO = 0.25

NO_GROUP_LABEL = 'Ohne Muskelgruppe'


@dataclass(frozen=True)
class PerformedExercise:
    """One exercise, as actually performed in one session.

    `sets` holds only *completed* sets as (weight, reps) pairs in the order
    they were logged -- a set prefilled from a template but never confirmed
    did not happen and must never reach this shape. Rows are therefore
    guaranteed to have at least one set, and every function here relies on
    that rather than defending against empty rows.

    weight and reps are as logged. For a unilateral exercise that means *per
    side*; volume doubles them, display never does.
    """
    exercise_id: int
    name: str
    muscle_group: Optional[str]
    is_unilateral: bool
    position: int
    session_id: int
    started_at: dt.datetime
    sets: Tuple


def epley_1rm(weight, reps):
    """Estimated one-rep max. No real single-rep test happens mid-workout, so
    this is the standard estimate every mainstream lifting tracker uses for
    the same reason. It is the yardstick for progress throughout this module,
    rather than raw weight, so that more reps at the same weight still counts
    as getting stronger."""
    return weight * (1 + reps / 30.0)


def set_volume(weight, reps, is_unilateral):
    """Volume for one logged set. A unilateral exercise logs the per-side
    weight and reps, so both sides did this and the real volume is double."""
    return weight * reps * (2 if is_unilateral else 1)


def best_weight(row):
    return max(weight for weight, _ in row.sets)


def best_e1rm(row):
    return max(epley_1rm(weight, reps) for weight, reps in row.sets)


def row_volume(row):
    return sum(set_volume(weight, reps, row.is_unilateral) for weight, reps in row.sets)


def _chronological(rows):
    return sorted(rows, key=lambda row: (row.started_at, row.session_id))


def dominant_position(rows):
    """The slot this exercise is most often performed in -- the fair default
    lens when nobody has asked for a specific one. Ties go to the lower slot
    so the answer is stable across calls."""
    counts = {}
    for row in rows:
        counts[row.position] = counts.get(row.position, 0) + 1
    return max(sorted(counts), key=lambda position: counts[position])


def _scoped(rows, position):
    """Position-scoped history, with an all-positions fallback.

    Exercise order changes how fatigued you are, so the same slot is the fair
    comparison -- but a slot with fewer than two sessions cannot support a
    judgement, and answering "no idea" would be worse than answering from
    every position. So it falls back rather than going empty.
    """
    if position is None:
        return _chronological(rows)
    scoped = [row for row in rows if row.position == position]
    return _chronological(scoped if len(scoped) >= 2 else rows)


def sessions_since_pr(rows, position=None):
    """How many completed sessions in a row have passed without a new best
    estimated 1RM. None when there is too little history to say anything."""
    scoped = _scoped(rows, position)
    if len(scoped) < 2:
        return None
    best_ever = None
    since = 0
    for row in scoped:
        current = best_e1rm(row)
        if best_ever is None or current > best_ever:
            best_ever = current
            since = 0
        else:
            since += 1
    return since


def exercise_state(rows, position=None, threshold=STAGNATION_THRESHOLD):
    """One of 'neu', 'rekord', 'stagniert', 'steigend', or None for stable.
    Mutually exclusive; first match wins."""
    if not rows:
        return 'neu'
    scoped = _scoped(rows, position)
    if len(scoped) >= 2 and best_e1rm(scoped[-1]) > max(best_e1rm(row) for row in scoped[:-1]):
        return 'rekord'
    since = sessions_since_pr(rows, position=position)
    if since is not None and since >= threshold:
        return 'stagniert'
    if len(scoped) >= 2 and best_e1rm(scoped[-1]) > best_e1rm(scoped[-2]):
        return 'steigend'
    return None


def stall_report(rows_by_exercise, threshold=STAGNATION_THRESHOLD):
    """Every exercise currently stagnating, worst first.

    `rows_by_exercise` maps exercise_id -> list of PerformedExercise. Each
    entry reports the slot it was judged in, the weight it is stuck at, and
    when the plateau started, so the page can say something specific rather
    than just flagging a name.
    """
    report = []
    for exercise_id, rows in rows_by_exercise.items():
        if not rows:
            continue
        position = dominant_position(rows)
        if exercise_state(rows, position=position, threshold=threshold) != 'stagniert':
            continue
        scoped = _scoped(rows, position)
        peak = max(scoped, key=best_e1rm)
        report.append({
            'exercise_id': exercise_id,
            'name': rows[0].name,
            'position': position,
            'stuck_at': best_weight(scoped[-1]),
            'since': peak.started_at,
            'sessions_since_pr': sessions_since_pr(rows, position=position),
        })
    report.sort(key=lambda entry: (-entry['sessions_since_pr'], entry['name']))
    return report
