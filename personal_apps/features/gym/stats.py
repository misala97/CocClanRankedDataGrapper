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
import math
from dataclasses import dataclass
from itertools import groupby
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

# Timestamps are stored naive-UTC and stay that way -- durations are
# timezone-independent and every window here is a duration. CALENDAR questions
# are not: "heute", "gestern" and "which ISO week" are answered in the place the
# training happened, and UTC answers them wrong for the first two hours of every
# CEST day. A workout finished at 00:30 local was filed under the previous date,
# and the first two hours of every Monday landed in the previous week's tonnage
# bucket. Convert at the calendar boundary only; leave the arithmetic alone.
LOCAL_TZ = ZoneInfo('Europe/Berlin')


def to_local(moment):
    """Naive UTC -> naive local wall-clock. None passes through."""
    if moment is None:
        return None
    return moment.replace(tzinfo=dt.timezone.utc).astimezone(LOCAL_TZ).replace(tzinfo=None)


def calendar_days_between(earlier, later):
    """Whole CALENDAR days from `earlier` to `later`, both naive UTC.

    Not `(later - earlier).days`, which floors elapsed 24-hour periods: a
    workout at 18:00 read at 09:00 the next morning is 15 hours old, so that
    expression returns 0 and the page said "heute" about yesterday. What the
    reader means by "gestern" is a date boundary, so count date boundaries.
    """
    return (to_local(later).date() - to_local(earlier).date()).days

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

# The default depth of a deload: 70 % of normal working weight. Stored per
# session rather than read from here at display time, so changing this never
# rewrites what a past session claims to have been.
DELOAD_DEFAULT_PCT = 70
# The depths offered in the UI. Anything outside this falls back to the
# default rather than erroring -- losing the toggle is worse than an odd value.
DELOAD_ALLOWED_PCTS = (50, 60, 70, 80, 90)
# The depths actually offered as buttons. Narrower than DELOAD_ALLOWED_PCTS
# on purpose: that one is the input whitelist (what the route will accept),
# this one is the UI (what is worth one tap). A deload's depth is chosen a
# few times a year, so three options is a decision, five is a menu.
DELOAD_QUICK_PCTS = (60, 70, 80)

# A quick-pick the route would reject is a button that silently does something
# other than what it says.
assert set(DELOAD_QUICK_PCTS) <= set(DELOAD_ALLOWED_PCTS)

# How many exercises from the *active* rotation must be stalled at once before
# it reads as accumulated fatigue rather than a set of individual weak points.
# STAGNATION_THRESHOLD counts sessions, not weeks, and isolation lifts cross it
# routinely -- at 3 this would fire during ordinary training and be learned-
# ignored. With a rotation of roughly 12-15 exercises, 4 is about a third.
DELOAD_STALL_THRESHOLD = 4
# Don't re-suggest a deload this soon after one, so a stall that survives the
# deload doesn't nag every single session.
DELOAD_SUPPRESSION_DAYS = 21

# A deload prescribes a rep count as well as a weight: lighter, and always the
# same moderate set length rather than whatever the last hard session happened
# to grind out. Fixed rather than derived -- the point of a deload week is that
# it does not chase the previous one.
DELOAD_REPS = 10

NO_GROUP_LABEL = 'Ohne Muskelgruppe'

# The smallest pair of plates on most bars, and the step for any exercise that
# has no increment of its own. Halved for a unilateral lift, which moves one
# side at a time.
DEFAULT_INCREMENT = 2.5

# How many sets an exercise with no history at all plans for -- and the count a
# routine row is filled with when there is no history to read one from (D2 P1,
# plan_set_count). Before this existed such an exercise arrived with no sets,
# and the live screen (which assumes a plan throughout) called it finished the
# moment one set was logged.
#
# Three sets is the shape almost every plan starts at. The sets carry no
# numbers: a 20 kg x 8 placeholder used to fill them, which was wrong for
# almost every exercise and looked like advice. The lifter types the first set
# and the rest take it (workout._propagate_default_correction).
DEFAULT_PLAN_SETS = 3


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

    `is_deload` marks a row performed during a deliberate deload. It is a
    property of the session, not the exercise -- every row from one session
    carries the same value.
    """
    exercise_id: int
    name: str
    muscle_group: Optional[str]
    is_unilateral: bool
    position: int
    session_id: int
    started_at: dt.datetime
    sets: Tuple
    # True when this row was performed in a deliberately light session. Every
    # function below that judges PROGRESS (stagnation, trends, averages) drops
    # these rows via _progression_rows(); records do not (D3: a record is a
    # record, deload or not), and nor does anything that reports what actually
    # happened (tonnage, balance, consistency).
    # Defaulted so callers predating the flag keep working.
    is_deload: bool = False
    # The exercise's own loadable step, as stored -- None when it has none and
    # the default applies. Carried on the row rather than looked up because
    # this module never touches the ORM. Defaulted for the same reason
    # is_deload is.
    weight_increment: Optional[float] = None
    # The machine's real stops, when they are uneven enough to be worth
    # recording. None on everything that steps evenly -- see snap_to_stack.
    stack_kg: Optional[Tuple] = None
    # When the session this row belongs to was finished, or None while it is
    # still running -- and None on every session logged before the app started
    # writing the stamp at all, which is why anything reading it must treat a
    # missing value as "not timed" rather than as a zero-length workout.
    # Carried per row for the same reason started_at is: this module never
    # touches the ORM, and every row of one session repeats the session's value.
    finished_at: Optional[dt.datetime] = None


def set_counts(completed, reps):
    """Whether a logged set counts -- the one rule, everywhere (Q1): the set
    count, the volume, the debrief, records, the plan, and whether a workout
    counts at all. Done, and at least one rep (G-038: a 0 × 0 set counted as
    done and as a record). On any exercise of the workout, a skipped or
    replaced one included: the set was done. Takes the two fields rather than
    a set so this module stays free of the ORM; routes/history.counts() is
    the ORM-side spelling."""
    return bool(completed) and reps is not None and reps >= 1


def epley_1rm(weight, reps):
    """Estimated one-rep max. No real single-rep test happens mid-workout, so
    this is the standard estimate every mainstream lifting tracker uses for
    the same reason. It is the yardstick for progress throughout this module,
    rather than raw weight, so that more reps at the same weight still counts
    as getting stronger.

    A single IS a one-rep max: the formula's +3,3 % applies from two reps on,
    as Epley meant it (D3, walkthrough 2026-09-23 -- 100 × 1 read 103,3)."""
    if reps <= 1:
        return float(weight)
    return weight * (1 + reps / 30.0)


#: Above this many reps a set is still shown, but nothing is judged by it: no
#: record, no stall count, no seed pick (D3). The estimate drifts far past a
#: dozen reps -- 40 × 25 "beat" 55 × 8 -- and one burnout or typo set must not
#: decide what counts.
RECORD_MAX_REPS = 12


def judged_e1rm(weight, reps):
    """The e1RM a judgement may use, to the 0,1 kg it is shown at -- or None
    for a set nothing is judged by: no reps, or more than RECORD_MAX_REPS.

    Rounded before any comparison, so a tie on screen is a tie in the rule:
    90 × 10 and 100 × 6 both read 120,0, and one of them "beating" the other
    by a float's last digit was a record nobody could see."""
    if reps is None or reps < 1 or reps > RECORD_MAX_REPS:
        return None
    return round(epley_1rm(weight, reps), 1)


def judged_best(row):
    """A row's best judged e1RM, or None when none of its sets is judged."""
    values = [value for value in (judged_e1rm(w, r) for w, r in row.sets) if value is not None]
    return max(values) if values else None


def set_volume(weight, reps, is_unilateral):
    """Volume for one logged set. A unilateral exercise logs the per-side
    weight and reps, so both sides did this and the real volume is double."""
    return weight * reps * (2 if is_unilateral else 1)


def best_weight(row):
    return max(weight for weight, _ in row.sets)


def best_e1rm(row):
    """A row's e1RM as shown: its best judged set -- or, for a row with none
    (only sets above RECORD_MAX_REPS), the plain estimate of its best set.
    Shown, never judged: every judgement reads judged_best()."""
    judged = judged_best(row)
    if judged is not None:
        return judged
    return max(epley_1rm(weight, reps) for weight, reps in row.sets)


def row_volume(row):
    return sum(set_volume(weight, reps, row.is_unilateral) for weight, reps in row.sets)


# -- Records: one meaning, everywhere (D3, walkthrough 2026-09-23) -----------
#
# A set is a record when its judged e1RM beats the best of every EARLIER
# workout of its exercise. A tie is none; a first workout has nothing to beat;
# the badge stays as history when a later workout goes higher. Deload plays no
# part -- a light workout is neither excused from the bar nor barred from
# setting one. Weight and volume are facts, not kinds of record. There were
# seven definitions of "Rekord" before this; every screen now asks the walker
# below or record_detail(), and nothing else decides.

def session_order(row):
    """Workouts in the order they happened: by start, then by id -- a
    workout entered later for an earlier day is judged on its day."""
    return (row.started_at, row.session_id)


def earlier_rows(rows, started_at, session_id):
    """The rows of every workout before the one that started at
    `started_at` (ties broken by id): what a set of that workout is judged
    against."""
    return [row for row in rows if session_order(row) < (started_at, session_id)]


def record_detail(weight, reps, earlier):
    """What one set beat, or None when it is no record: its judged e1RM
    against the best of every workout in `earlier` -- which the caller limits
    to workouts before the set's own (earlier_rows).

    `previous_at` is the start of the FIRST workout that reached the old best,
    so "vorher" names the day the bar was set, not a later tie of it.
    """
    value = judged_e1rm(weight, reps)
    if value is None:
        return None
    best = None
    for row in sorted(earlier, key=session_order):
        row_best = judged_best(row)
        if row_best is not None and (best is None or row_best > best[0]):
            best = (row_best, row.started_at)
    if best is None or value <= best[0]:
        return None
    return {'kind': 'e1rm', 'value': value, 'previous': best[0], 'previous_at': best[1]}


def record_marks(rows):
    """Every row of `rows` that set a record, with what it beat:
    {row: {'value', 'previous', 'previous_at'}}. A row absent set none.

    Per exercise, workout by workout in order (session_order). A workout's own
    rows never judge each other: the same exercise twice in one workout is two
    tries at the same bar, and either may clear it.
    """
    by_exercise = {}
    for row in rows:
        by_exercise.setdefault(row.exercise_id, []).append(row)

    marks = {}
    for exercise_rows in by_exercise.values():
        best = None     # (value, started_at) of the best so far
        for _, workout in groupby(sorted(exercise_rows, key=session_order), key=session_order):
            workout = list(workout)
            workout_best = None
            for row in workout:
                value = judged_best(row)
                if value is None:
                    continue
                if best is not None and value > best[0]:
                    marks[row] = {'value': value, 'previous': best[0], 'previous_at': best[1]}
                if workout_best is None or value > workout_best:
                    workout_best = value
            if workout_best is not None and (best is None or workout_best > best[0]):
                best = (workout_best, workout[0].started_at)
    return marks


def _chronological(rows):
    return sorted(rows, key=lambda row: (row.started_at, row.session_id))


def progression_rows(rows):
    """Only the rows that count as an attempt at progress.

    A deload session is deliberately light: its numbers are not a failed
    attempt at progress, and treating them as one manufactures exactly the
    plateau the deload existed to break. The progress judgements --
    stagnation, the trend, volume averages -- start here. Records do not: a
    record a deload sets still counts (D3), so record_marks and drought read
    every row. Functions that report what actually happened (tonnage,
    balance, consistency, the history table) deliberately do not either.

    Public (and called directly from the routes) because the exercise
    catalogue route has to make the same judgement/report split on its own
    unfiltered rows before handing them to dominant_position and last_weight
    -- see gym_uebungen()'s own comment for why.
    """
    return [row for row in rows if not row.is_deload]


# Old name, kept so existing internal call sites and tests that reach past
# the public API keep working.
_progression_rows = progression_rows


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


def drought(rows):
    """How long one exercise has gone without a record, or None when it has
    no judged workout: {'since', 'anchor_at', 'last_record_at', 'workouts'}.

    Counted from the newest workout that set a record (record_marks: any
    slot, deload or not), else from the debut -- the first judged workout,
    the last time the number moved. `since` counts the attempts after it:
    workouts with a judged set that were no deload. A deload workout can set
    a record and so reset the count, but never adds to it -- a light week is
    no failed attempt -- and a workout with only sets above RECORD_MAX_REPS
    was no attempt at the number either. `workouts` counts every attempt.

    The one count behind "seit N Workouts ohne Rekord", "Stagniert", the
    live stall line, Start's stall list and Statistik's drought: it used to
    be judged per slot and blind to deloads, so a lift could read "Rekord"
    beside "2 Einheiten ohne PR" (B3 review; D16 has renamed both since)."""
    judged = [row for row in rows if judged_best(row) is not None]
    if not judged:
        return None
    last_record = max((session_order(row) for row in record_marks(judged)), default=None)
    anchor = last_record if last_record is not None else min(session_order(row) for row in judged)
    attempts = {session_order(row) for row in judged if not row.is_deload}
    return {
        'since': sum(1 for key in attempts if key > anchor),
        'anchor_at': anchor[0],
        'last_record_at': last_record[0] if last_record is not None else None,
        'workouts': len(attempts),
    }


def sessions_since_pr(rows):
    """Workouts in a row without a record (drought), or None while fewer
    than two attempts leave nothing to say."""
    counted = drought(rows)
    if counted is None or counted['workouts'] < 2:
        return None
    return counted['since']


def exercise_state(rows, position=None, threshold=STAGNATION_THRESHOLD):
    """One of 'neu', 'rekord', 'stagniert', 'steigend', or None for stable.
    Mutually exclusive; first match wins.

    'rekord' is the one meaning (record_marks): the exercise's newest workout
    set a record -- in any slot, deload or not. It used to be judged within
    the slot, so a slot's best below the lift's own best read "Rekord", and a
    tie did too (G-033). The rest are progress judgements and drop deload
    workouts: an exercise whose only history is deloads reads 'neu', because
    there is no honest basis for comparison. 'stagniert' counts from the last
    record (drought), so it reads every row: a deload record resets it.
    `position` only lenses 'steigend', last against previous in the slot."""
    if rows:
        newest = max(session_order(row) for row in rows)
        if any(session_order(row) == newest for row in record_marks(rows)):
            return 'rekord'
    progression = _progression_rows(rows)
    if not progression:
        return 'neu'
    since = sessions_since_pr(rows)
    if since is not None and since >= threshold:
        return 'stagniert'
    scoped = _scoped([row for row in progression if judged_best(row) is not None], position)
    if len(scoped) >= 2 and judged_best(scoped[-1]) > judged_best(scoped[-2]):
        return 'steigend'
    return None


def stall_report(rows_by_exercise, threshold=STAGNATION_THRESHOLD):
    """Every exercise currently stagnating, worst first.

    `rows_by_exercise` maps exercise_id -> list of PerformedExercise, deload
    workouts included: a deload record ends a drought like any other. Each
    entry reports the slot the lift is mostly done in, the top weight of its
    newest attempt, and when the number last moved (the drought's anchor), so
    the page can say something specific rather than just flagging a name.

    The slot (`dominant_position`) is chosen from the deload-filtered rows,
    so a deload session cannot skew which position counts as dominant.
    """
    report = []
    for exercise_id, rows in rows_by_exercise.items():
        progression = _progression_rows(rows)
        if not progression:
            continue
        position = dominant_position(progression)
        if exercise_state(rows, position=position, threshold=threshold) != 'stagniert':
            continue
        counted = drought(rows)
        # The newest ATTEMPT: a row with only sets above RECORD_MAX_REPS
        # was none, and its weight is no plateau (B3 review).
        attempts = _chronological([row for row in progression if judged_best(row) is not None])
        report.append({
            'exercise_id': exercise_id,
            'name': progression[0].name,
            'position': position,
            'stuck_at': best_weight(attempts[-1]),
            'since': counted['anchor_at'],
            'sessions_since_pr': counted['since'],
        })
    report.sort(key=lambda entry: (-entry['sessions_since_pr'], entry['name']))
    return report


def deload_signal(report, rows_by_exercise, now, last_deload_at=None,
                  days=ROLLING_WINDOW_DAYS, threshold=DELOAD_STALL_THRESHOLD,
                  suppression_days=DELOAD_SUPPRESSION_DAYS):
    """Whether the data says a deload is due, and the lifts that say so.

    `report` is stall_report()'s output and `rows_by_exercise` the map the
    caller already holds, so this costs no extra query.

    Only exercises actually trained inside the rolling window count. A lift
    abandoned six months ago drifts into 'stagniert' from disuse and says
    nothing about how recovered the lifter is; counting it would leave the
    suggestion permanently lit for anyone with a long catalogue.

    Unlike the progress judgements (which use _progression_rows to exclude
    deload rows), this recency check counts a deload session as recent
    training: the lift is still in the active rotation even though its
    numbers do not count toward a record.

    Returns None when the signal does not fire, otherwise the qualifying
    stalls so the page can name the lifts rather than assert a vague verdict.
    """
    if last_deload_at is not None and (now - last_deload_at).days < suppression_days:
        return None

    cutoff = now - dt.timedelta(days=days)
    active = []
    for entry in report:
        rows = rows_by_exercise.get(entry['exercise_id']) or []
        if any(row.started_at >= cutoff for row in rows):
            active.append(entry)

    if len(active) < threshold:
        return None
    return {'count': len(active), 'stalls': active}


def _sets_display(row):
    """A row's sets as one line: 63,0 x 9 . 63,0 x 8 . 63,0 x 7

    German decimal comma, a real multiplication sign, and a middot between
    sets. The unit is not repeated per set -- every weight in this app is
    kilograms, and "63 kg x 9, 63 kg x 8, 63 kg x 7" spends a third of the line
    saying so three times.
    """
    return ' · '.join(
        kg_text(weight) + ' × {}'.format(reps)
        for weight, reps in row.sets
    )


def kg_text(weight):
    """A weight to the hundredth the app keeps, one decimal at least: 80,0,
    62,5, 11,25 -- what the client's format.kg says. '%.1f' printed a logged
    11,25 as 11,2 here while the stepper said 11,3 (walkthrough G-146).
    """
    text = '{:.2f}'.format(weight)
    return (text[:-1] if text.endswith('0') else text).replace('.', ',')


def _pr_weight(rows):
    """The heaviest single set ever logged: a fact, not a kind of record (D3)
    -- deloads included, the first to reach it kept. None when nothing was
    loaded at all: "0,0 kg" is no heaviest set (G-038)."""
    best = None
    for row in _chronological(rows):
        for weight, reps in row.sets:
            if best is None or weight > best['weight']:
                best = {'weight': weight, 'reps': reps, 'session_id': row.session_id,
                        'started_at': row.started_at, 'position': row.position}
    return best if best is not None and best['weight'] > 0 else None


def _pr_e1rm(rows):
    """The set with the best judged e1RM -- not always the heaviest one,
    since more reps at less weight can estimate higher. The first set to
    reach it, deloads included (D3); None when no set is judged or the best
    is 0 kg (bodyweight: no estimate to speak of, G-038)."""
    best = None
    for row in _chronological(rows):
        for weight, reps in row.sets:
            value = judged_e1rm(weight, reps)
            if value is not None and (best is None or value > best['e1rm']):
                best = {'e1rm': value, 'weight': weight, 'reps': reps,
                        'session_id': row.session_id,
                        'started_at': row.started_at, 'position': row.position}
    return best if best is not None and best['e1rm'] > 0 else None


def exercise_progress(rows, position=None):
    """History table and chart series for one exercise.

    Position is a *series*, not a filter: every session is plotted, grouped by
    the slot it was performed in, so a slot sitting consistently higher than
    another is visible instead of having to be hunted for by hiding data.
    `position` still isolates one slot when the user explicitly asks.

    `available_positions` always describes the unfiltered data, so the page can
    keep offering the other slots even while one is isolated.

    `table` and `series` keep deload rows and mark them `is_deload`: they are
    the record of what was performed, and dropping them would leave holes in
    the chart. Both mark `is_record` on every row that set one -- history, so
    a later best does not take the tag back (D3) -- judged over the WHOLE
    exercise, whatever slot is shown.
    """
    chronological = _chronological(rows)
    available_positions = sorted({row.position for row in chronological})
    shown = ([row for row in chronological if row.position == position]
             if position is not None else chronological)
    marks = record_marks(chronological)

    table = [
        {
            'session_id': row.session_id,
            'started_at': row.started_at,
            'position': row.position,
            'is_deload': row.is_deload,
            'is_record': row in marks,
            'sets_display': _sets_display(row),
            'best_weight': best_weight(row),
            'volume': round(row_volume(row), 1),
            'e1rm': round(best_e1rm(row), 1),
        }
        for row in reversed(shown)
    ]

    series = []
    for slot in (available_positions if position is None else [position]):
        points = [row for row in shown if row.position == slot]
        if not points:
            continue
        series.append({
            'position': slot,
            'points': [
                {
                    'started_at': row.started_at,
                    'is_deload': row.is_deload,
                    'is_record': row in marks,
                    'e1rm': round(best_e1rm(row), 1),
                    'best_weight': best_weight(row),
                    'volume': round(row_volume(row), 1),
                }
                for row in points
            ],
        })

    return {
        'table': table,
        # The newest row of the WHOLE exercise, regardless of the position
        # filter. `table` is the filtered view, so a page reading table[0] for
        # "Zuletzt" reported the last session *in that slot* as the last time
        # the lift was done at all.
        'last_overall': ({
            'started_at': chronological[-1].started_at,
            'position': chronological[-1].position,
        } if chronological else None),
        'series': series,
        'available_positions': available_positions,
        'selected_position': position,
        'pr_weight': _pr_weight(chronological),
        'pr_e1rm': _pr_e1rm(chronological),
        'state': exercise_state(rows, position=position),
        'sessions_since_pr': sessions_since_pr(rows),
        # The newest row that counts as an attempt at progress. `table[0]` is
        # the newest row of ANY kind and can be a deload, so anything quoting
        # "the weight you are stuck at" must read this instead -- otherwise
        # the stagnation advice tells you to add 2.5 kg to a weight you went
        # deliberately light on. None when there is no non-deload history.
        'last_progression': next(
            (row for row in table if not row['is_deload']), None),
    }


def resolve_increment(increment, is_unilateral):
    """The smallest loadable jump for one exercise.

    An explicit per-exercise value is taken literally: it is already the number
    that moves when you tap, per side when the lift is unilateral (the live
    screen labels that field `kg je Seite`). Halving survives only as the
    fallback, so an exercise with nothing set behaves exactly as the whole app
    did before increments existed.

    Zero collapses to the fallback along with None -- a step of zero would
    freeze the stepper, so it is never a value worth honouring.
    """
    if increment:
        return increment
    return DEFAULT_INCREMENT / 2 if is_unilateral else DEFAULT_INCREMENT


def _next_weight(weight, increment):
    """The smallest honest jump up: one loadable step on this exercise's own
    equipment. Callers resolve `increment` through resolve_increment()."""
    return weight + increment


def snap_to_stack(weight, steps, direction):
    """The nearest real position of a machine whose stops are known.

    Almost nothing needs this: an evenly stepping stack is already fully
    described by its increment, and deload_weight's anchor-to-working-weight
    rule keeps even an offset grid (5, 13, 21 ...) honest without knowing the
    stops. It exists for the machine whose gaps are uneven, where counting
    increments from anywhere invents a position -- the first such exercise
    entered into the form computes correctly the same day instead of
    prescribing a weight nobody can select.

    `steps` falsy means the exercise has no recorded stops, and the weight
    passes through untouched.

    `direction` must be exactly 'down' or 'up' -- anything else raises rather
    than silently falling through to 'up', which for a deload is precisely
    the direction deload_weight()'s own docstring calls "the one direction
    that defeats the point".
    """
    # Checked before the falsy-steps shortcut, not after: no exercise carries
    # stops yet, so a typo'd direction would otherwise stay silent until the
    # day someone records one -- which is the latent failure this raise exists
    # to prevent.
    if direction not in ('down', 'up'):
        raise ValueError("direction must be 'down' or 'up', got {!r}".format(direction))
    if not steps:
        return weight
    ordered = sorted(steps)
    if direction == 'down':
        below = [s for s in ordered if s <= weight]
        return below[-1] if below else ordered[0]
    above = [s for s in ordered if s >= weight]
    return above[0] if above else ordered[-1]


def deload_weight(weight, pct, increment, stack_kg=None):
    """`pct` of a working weight, taken DOWN to a loadable weight.

    Down, not to nearest: rounding a deload up makes it heavier than
    prescribed, which is the one direction that defeats the point.

    The grid is anchored to `weight`, not to zero -- the result is always a
    whole number of increments below the weight the lifter is already on.
    Counting from zero assumes the machine has a position at every multiple of
    the increment, and real equipment does not: a stack sitting on a 5 kg
    carriage with 8 kg plates offers 5, 13, ... 53, 61, 69, so flooring 69 at
    70 % gave 48, which that machine cannot make. Stepping down from a
    position known to exist cannot invent one that does not. Where the grid
    does include zero -- a bar in 2.5s, dumbbells in 2s -- both rules agree.

    Applied per set by the caller, never to the top set alone, so any ramping
    or drop-off in the session's shape survives the deload.

    When the machine's real stops are known (`stack_kg`), the increment grid
    above is only a guess at them -- the 5/13/.../69 carriage is exactly the
    shape that guess can miss -- so the grid's result is snapped DOWN onto the
    nearest stop the machine actually has.
    """
    if weight <= 0:
        return weight          # a bodyweight set stays bodyweight
    # ceil, so the result lands at or below the prescription rather than above it
    steps = math.ceil((weight - weight * pct / 100.0) / increment)
    prescribed = max(increment, weight - steps * increment)
    # A recorded stack overrides the increment grid: its stops are the only
    # positions that exist, and the grid is at best a good guess at them.
    return snap_to_stack(prescribed, stack_kg, 'down')


def step_up(weight, increment, stack_kg=None):
    """One loadable step above `weight`, snapped UP onto the machine's real
    stops -- or None when topped out on a known stack, where snapping clamps
    back to the top stop and repeating that number is not advice. Callers
    resolve `increment` through resolve_increment()."""
    heavier = snap_to_stack(_next_weight(weight, increment), stack_kg, 'up')
    return heavier if heavier > weight else None


# --------------------------------------------------------------------------
# The plan model (D2 P1): how many sets, in which rep range, and what to lift
# next time. A routine's rows carry the count and the range; they are filled
# from history once and then changed only by an explicit edit -- a value
# derived afresh at every start is how one test workout shrank a routine
# (G-050).
# --------------------------------------------------------------------------

#: A routine row's set count stays within this.
MAX_PLAN_SETS = 10

#: And its rep range within this -- wide enough for any range a history
#: gives (derived_rep_range), narrow enough to catch a slip.
MAX_PLAN_REPS = 100

#: No history to read a range from. The owner trains 6-8; the range is wide
#: enough to hold that and leave room to climb.
DEFAULT_REP_RANGE = (6, 10)

#: A derived range spans this many reps either side of the median.
REP_RANGE_SPREAD = 2


def plan_set_count(counts):
    """A routine row's set count from the counted sets of the exercise in
    recent workouts: the most any of them held -- max, not mode, so a
    workout cut short does not shrink the plan. None there:
    DEFAULT_PLAN_SETS."""
    if not counts:
        return DEFAULT_PLAN_SETS
    return min(MAX_PLAN_SETS, max(1, max(counts)))


def derived_rep_range(reps):
    """A rep range centred on the median of `reps` -- the reps of the sets
    done at the top weight of recent workouts -- REP_RANGE_SPREAD either
    side, never starting below 1 nor ending past MAX_PLAN_REPS (the range
    moves down instead: the sheet posts it back as it is). Half a rep rounds
    up. None: DEFAULT_REP_RANGE."""
    if not reps:
        return DEFAULT_REP_RANGE
    middle = min(int(_median(reps) + 0.5), MAX_PLAN_REPS - REP_RANGE_SPREAD)
    return max(1, middle - REP_RANGE_SPREAD), middle + REP_RANGE_SPREAD


#: The rep range reads the top-weight sets of this many workouts.
RANGE_WORKOUTS = 5


def rep_range_from(workouts):
    """The rep range a lifter's history gives (derived_rep_range): centred on
    the reps done at the top weight of the newest RANGE_WORKOUTS workouts.
    `workouts` holds each one's counted sets as (weight, reps), newest first.
    High reps too, unlike a record (D3): a lift only ever done for 15 has its
    range there -- passed over, it got the default and a target of 6 -- and
    one light day among heavy ones barely moves a median."""
    reps = []
    read = 0
    for sets in workouts:
        if not sets:
            continue
        top = max(weight for weight, _ in sets)
        reps.extend(count for weight, count in sets if weight == top)
        read += 1
        if read == RANGE_WORKOUTS:
            break
    return derived_rep_range(reps)


def next_target(sets, rep_min, rep_max, target_sets, increment, stack_kg=None):
    """What to lift next time, set by set, by double progression (D2 P1,
    G-035): a {'weight', 'reps'} per planned set, or None with nothing
    lifted. Display only: nothing in the plan changes because of it.

    `sets` are the (weight, reps) of the counted sets it builds on, in order
    -- the live card passes the seed pick's, so it never shows a plan from
    one workout and a target from another. They are cut to `target_sets`,
    as seeding cuts the plan, or the last one repeated up to it: a set left
    out last time is aimed at like the one before it.
    - Every planned set done at the top of the range: each one loadable step
      up (snapped onto a known stack), back to the bottom of the range. A
      set left out was not done, so it holds the step back.
    - Else each set at its own weight, one rep more, up to the top of the
      range -- below the range too: one rep at a time. Set by set (Michi,
      M2 09-24): one weight for every set asked +5 kg of the back-off sets
      behind a heavy first one.
    Where no step up exists the only way on is reps: a bodyweight set (0 kg,
    which a plate would turn into another exercise) and the top stop of a
    known stack go on at their weight, one rep more, past the range.
    """
    if not sets:
        return None
    count = max(1, target_sets)
    base = (list(sets) + [sets[-1]] * count)[:count]
    if len(sets) >= count and all(reps >= rep_max for _weight, reps in base):
        return [_stepped_up(weight, reps, rep_min, increment, stack_kg) for weight, reps in base]
    # A set already past the top waits there for the others: not one rep less.
    return [{'weight': weight, 'reps': reps if reps >= rep_max else reps + 1}
            for weight, reps in base]


def _stepped_up(weight, reps, rep_min, increment, stack_kg):
    heavier = step_up(weight, increment, stack_kg) if weight > 0 else None
    if heavier is None:
        return {'weight': weight, 'reps': reps + 1}
    return {'weight': heavier, 'reps': rep_min}


def _verdict(entry, since, is_deload, is_judged=True):
    """A record is a record in any workout; everything else is a progress
    judgement, which a deload workout never was an attempt at."""
    if entry['is_record']:
        return 'rekord'
    if is_deload:
        return None
    if not entry['has_history']:
        return 'neu'
    # A row with no judged set (only sets above RECORD_MAX_REPS) was no
    # attempt at the number a stall counts by: no stall, no "go heavier".
    if since is not None and since >= STAGNATION_THRESHOLD and is_judged:
        return 'stagniert'
    if entry['volume_delta_pct'] is not None and entry['volume_delta_pct'] > 0:
        return 'steigend'
    return None


def session_report(current, history, comparable_session_volumes=()):
    """The finished-workout page.

    `current` is this session's performed exercises, a replaced-away original
    included: the sets done on it before the swap were done, and they count
    like any other (Q1). `history` is every other performed row for those same
    exercises. `comparable_session_volumes` holds the total volume of past
    sessions built from the same template, and is empty for freeform workouts:
    averaging a leg day into a push day produces a number that is arithmetically
    correct and completely meaningless.

    Records have the one meaning (record_marks, D3): e1RM only, against the
    workouts BEFORE this one. `history` may hold later ones -- a debrief read
    weeks on -- and they are no bar for it: the badge is what was true on the
    day. A deload workout keeps its records (G-078) but gets no stagnation
    advice or trend verdict: it was never an attempt at progress. Past
    deloads stay out of the averages and the stall count for the same reason.
    """
    # This session's own deload state. Every row in `current` comes from the
    # same session, so any of them answers it; an empty session (no completed
    # sets) is not a deload.
    is_deload = bool(current) and current[0].is_deload
    if current:
        history = earlier_rows(history, current[0].started_at, current[0].session_id)
    marks = record_marks(list(history) + list(current))
    done_before = {row.exercise_id for row in history}

    by_exercise = {}
    for row in _progression_rows(history):
        by_exercise.setdefault(row.exercise_id, []).append(row)

    exercises = []
    records = []
    advice = []
    total_volume = 0.0
    total_sets = 0

    for row in current:
        volume = row_volume(row)
        weight = best_weight(row)
        e1rm = best_e1rm(row)
        total_volume += volume
        total_sets += len(row.sets)

        past = by_exercise.get(row.exercise_id, [])
        past_volumes = [row_volume(p) for p in past]
        avg_volume = (sum(past_volumes) / len(past_volumes)) if past_volumes else None

        entry = {
            'exercise_id': row.exercise_id,
            'name': row.name,
            'position': row.position,
            'sets': row.sets,
            'sets_display': _sets_display(row),
            'volume': round(volume, 1),
            'best_weight': weight,
            'e1rm': round(e1rm, 1),
            # Done before at all, deloads included: "neu" is a fact, the
            # first time -- not a judgement.
            'has_history': row.exercise_id in done_before,
            'avg_volume': round(avg_volume, 1) if avg_volume is not None else None,
            'volume_delta_pct': (round((volume - avg_volume) / avg_volume * 100)
                                 if avg_volume else None),
            'is_record': row in marks,
        }

        # Counted from the last record (drought) with this workout in it: a
        # record here -- deload or not -- ends the drought, and a deload row
        # never adds to it.
        since = sessions_since_pr(past + [row])
        entry['sessions_since_pr'] = since
        entry['verdict'] = _verdict(entry, since, is_deload, judged_best(row) is not None)
        exercises.append(entry)

        if entry['verdict'] == 'stagniert':
            suggested_weight = snap_to_stack(
                _next_weight(weight, resolve_increment(row.weight_increment, row.is_unilateral)),
                row.stack_kg, 'up')
            # Topped out: on a machine whose real stops are known, snap_to_stack
            # clamps a jump past the heaviest stop back down to that stop -- so a
            # lifter already sitting on the top step gets suggested_weight ==
            # stuck_at, the exact number the plateau is already stuck at. Without
            # a stack (or one with room above the current weight) the jump is
            # always strictly upward, so this never fires on that path -- it
            # exists only for the one case where "go heavier" has no honest
            # answer, and dropping the entry beats repeating a number.
            if suggested_weight > weight:
                advice.append({
                    'exercise_id': row.exercise_id,
                    'name': row.name,
                    'stuck_at': weight,
                    'sessions': since,
                    'suggested_weight': suggested_weight,
                })

    # One record per exercise. Grouped per EXERCISE, not per row: a session
    # that (rarely) logs the same exercise in two slots is one performance of
    # that lift, as session_record_counts() counts it for Heute and Verlauf --
    # counting each slot is how one workout read "6 Rekorde" in every list and
    # "7 neue Rekorde" as its own headline. The stronger of its marked rows
    # leads; every marked row faced the same bar.
    current_by_exercise = {}
    for row in current:
        if row in marks:
            current_by_exercise.setdefault(row.exercise_id, []).append(row)
    for exercise_id, rows in current_by_exercise.items():
        lead = max(rows, key=lambda r: marks[r]['value'])
        mark = marks[lead]
        records.append({'kind': 'e1rm', 'name': lead.name, 'position': lead.position,
                        'exercise_id': exercise_id, 'value': mark['value'],
                        'previous': mark['previous'], 'previous_at': mark['previous_at']})

    # By how much each beat the old one -- relative, so a heavy lift's +2 kg
    # does not automatically outrank a light lift's +5 kg. A first load on a
    # bodyweight lift (from 0) is the biggest step there is.
    def _gain(record):
        previous = record['previous']
        return (record['value'] - previous) / previous if previous > 0 else math.inf

    records.sort(key=lambda record: -_gain(record))
    advice.sort(key=lambda item: -item['sessions'])

    avg_total = ((sum(comparable_session_volumes) / len(comparable_session_volumes))
                 if comparable_session_volumes else None)

    return {
        'exercises': exercises,
        'total_volume': round(total_volume, 1),
        'total_sets': total_sets,
        'avg_total_volume': round(avg_total, 1) if avg_total else None,
        'total_volume_delta_pct': (round((total_volume - avg_total) / avg_total * 100)
                                   if avg_total else None),
        'records': records,
        'record_count': len(records),
        'advice': advice,
        'is_deload': is_deload,
        # The percentage is a property of the session row, not of the
        # performed rows, so the route supplies it to the template directly.
        # Reported here as None so the shape is stable for any caller reading
        # the dict alone.
        'deload_pct': None,
    }


def session_record_counts(rows):
    """{session_id: how many exercises set a record in it} for every workout
    in `rows`, in one pass -- Heute and Verlauf need all of them at once.

    The one meaning (record_marks): against the workouts BEFORE each one, so
    a workout keeps its count when a later one goes higher. It used to ask
    "beats every OTHER workout", which took a badge back the moment a later
    workout beat it: Jun-Sep read 0/1/11/2 here and 8/46/41/3 on Statistik
    (G-126). A workout with records on two exercises counts two; the same
    exercise in two of its slots counts once. Workouts without one are absent.

    `rows` is every PerformedExercise of the lifter's finished workouts, a
    replaced-away original included: its sets were done (Q1).
    """
    marked = {(row.session_id, row.exercise_id) for row in record_marks(rows)}
    counts = {}
    for session_id, _exercise_id in marked:
        counts[session_id] = counts.get(session_id, 0) + 1
    return counts


def muscle_group_volume(rows, catalogue_groups, now, days=ROLLING_WINDOW_DAYS):
    """Working sets and volume per muscle group over a rolling window.

    `catalogue_groups` is every group with at least one exercise in the
    catalogue, so a group you have quietly stopped training still appears --
    at zero, flagged -- instead of vanishing from the page precisely when it
    most needs pointing out.
    """
    cutoff = now - dt.timedelta(days=days)
    totals = {group: {'group': group, 'sets': 0, 'volume': 0.0} for group in catalogue_groups}
    for row in rows:
        if row.started_at < cutoff:
            continue
        group = row.muscle_group or NO_GROUP_LABEL
        bucket = totals.setdefault(group, {'group': group, 'sets': 0, 'volume': 0.0})
        bucket['sets'] += len(row.sets)
        bucket['volume'] += row_volume(row)

    buckets = sorted(totals.values(), key=lambda bucket: (-bucket['sets'], bucket['group']))
    peak = buckets[0]['sets'] if buckets else 0
    for bucket in buckets:
        bucket['volume'] = round(bucket['volume'], 1)
        bucket['share'] = (bucket['sets'] / peak) if peak else 0.0
        bucket['under_trained'] = bucket['sets'] == 0 or bucket['sets'] < peak * UNDER_TRAINED_RATIO
    return buckets


def _week_start(moment):
    """Monday 00:00 of the ISO week `moment` falls in, in LOCAL time.

    Local, because a week boundary is a calendar fact. Both the current week
    and each row go through here, so the buckets stay consistent with each
    other either way -- but in UTC they were consistent and two hours off the
    week the training actually belongs to.
    """
    local = to_local(moment)
    monday = local.date() - dt.timedelta(days=local.weekday())
    return dt.datetime(monday.year, monday.month, monday.day)


def weekly_tonnage(rows, now, weeks=TONNAGE_WEEKS):
    """Total volume per ISO week, oldest first, ending with the current one.

    The last bucket is a partial week by definition. It is flagged
    `is_current` so the page can label it as still running -- unflagged, a
    Tuesday would always look like a collapse in training.

    `has_deload` marks a week containing at least one deload session, so the
    page can label the dip instead of leaving it looking like a collapse. The
    volume itself still totals every session, deload or not -- the work was
    done and the chart reports what happened.
    """
    current_start = _week_start(now)
    starts = [current_start - dt.timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]
    buckets = {start: 0.0 for start in starts}
    deload_weeks = set()
    for row in rows:
        start = _week_start(row.started_at)
        if start in buckets:
            buckets[start] += row_volume(row)
            if row.is_deload:
                deload_weeks.add(start)
    return [
        {'week_start': start, 'volume': round(buckets[start], 1),
         'is_current': start == current_start,
         'has_deload': start in deload_weeks}
        for start in starts
    ]


def consistency(finished_started_at, now, days=ROLLING_WINDOW_DAYS):
    """Training rate over the window, plus how long it has been since the last
    session. `finished_started_at` is a list of datetimes."""
    cutoff = now - dt.timedelta(days=days)
    recent = [moment for moment in finished_started_at if moment >= cutoff]
    latest = max(finished_started_at) if finished_started_at else None
    return {
        'sessions': len(recent),
        'per_week': len(recent) / (days / 7.0),
        'days_since_last': calendar_days_between(latest, now) if latest else None,
        'window_days': days,
    }


def routine_memory(templates, sessions, now):
    """Each routine with how long since it was last performed.

    Longest-ago first, because that is usually the one you are about to do.
    Routines never performed sort last: they are unproven rather than overdue,
    and putting them on top would bury the answer under noise.
    """
    latest = {}
    for session in sessions:
        if session.template_id is None:
            continue
        seen = latest.get(session.template_id)
        if seen is None or session.started_at > seen:
            latest[session.template_id] = session.started_at

    memory = []
    for template in templates:
        last = latest.get(template.id)
        memory.append({
            'template': template,
            'last_done': last,
            'days_ago': calendar_days_between(last, now) if last else None,
        })
    memory.sort(key=lambda entry: (entry['days_ago'] is None,
                                   -(entry['days_ago'] or 0),
                                   entry['template'].name))
    return memory


def group_exercises_by_muscle(exercises, muscle_groups):
    """Bucket exercises by muscle group in the vocabulary's own order.

    Anything that does not match a current group -- no group set, or a legacy
    free-text value from before the vocabulary existed -- lands in a trailing
    catch-all bucket rather than being silently dropped. `exercises` is
    expected pre-sorted by name so each bucket stays alphabetical.
    """
    grouped = {group: [] for group in muscle_groups}
    other = []
    for exercise in exercises:
        if exercise.muscle_group in grouped:
            grouped[exercise.muscle_group].append(exercise)
        else:
            other.append(exercise)
    result = [(group, grouped[group]) for group in muscle_groups if grouped[group]]
    if other:
        result.append((NO_GROUP_LABEL, other))
    return result


# A gap longer than this is an interruption, not rest -- a phone call between
# sets should not become part of what your rest looks like. Long enough for a
# genuinely slow superset, short enough to exclude walking away. Uncapped, one
# such gap distorts everything downstream.
REST_GAP_CAP_SECONDS = 600


def rest_gaps(entries):
    """Rest taken between consecutive sets of ONE session.

    `entries` is an iterable of (completed_at, planned_seconds) for that
    session's completed sets, in any order -- sorted here, because callers hand
    over whatever order the rows arrived in.

    Returns [(actual_seconds, planned_seconds), ...], one per consecutive pair.
    The plan comes from the set that ENDED the gap: you finish a set and rest
    that exercise's time. Gaps over REST_GAP_CAP_SECONDS are dropped entirely.

    Deliberately includes walking to the next machine and setting it up. That
    time is not lifting, and it is a real part of why a session takes as long
    as it does.
    """
    ordered = sorted((e for e in entries if e[0] is not None), key=lambda e: e[0])
    gaps = []
    for (earlier_at, earlier_planned), (later_at, _) in zip(ordered, ordered[1:]):
        actual = int((later_at - earlier_at).total_seconds())
        if 0 <= actual <= REST_GAP_CAP_SECONDS:
            gaps.append((actual, earlier_planned))
    return gaps


def rest_medians(gaps):
    """(median_planned, median_actual) over pooled gaps, or None.

    Pooled over every gap rather than averaged per session: the question is
    what a typical rest of yours looks like, and a twenty-set session carries
    more evidence about that than a six-set one.

    Median rather than mean so one slow day cannot move it -- which also makes
    the cap above less load-bearing, since an outlier that slips past it shifts
    a median far less than a mean.

    None when there is nothing to report, so the caller says "noch keine Daten"
    instead of a confident zero.
    """
    actuals = [actual for actual, _ in gaps]
    planned = [plan for _, plan in gaps if plan is not None]
    if not actuals or not planned:
        return None
    return int(_median(planned)), int(_median(actuals))


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


# --------------------------------------------------------------------------
# e1RM projection: "bei diesem Tempo".
# --------------------------------------------------------------------------

#: How far ahead a projection may claim. Past this the extrapolation is
#: fiction wearing a date, so the chart stays silent instead.
PROJECTION_HORIZON_DAYS = 112
#: Fit over at most this many of the newest points -- a year-old ramp says
#: nothing about the current one.
PROJECTION_FIT_POINTS = 8
#: Milestones are the next multiple of this above the fitted value.
PROJECTION_MILESTONE_KG = 5.0


def e1rm_projection(points, now):
    """Where the current trend puts the next round-number e1RM, or None.

    `points` is [(started_at, e1rm), ...] for ONE series, deloads already
    excluded. Least-squares over the newest PROJECTION_FIT_POINTS, and every
    gate errs toward silence -- a wrong date on a chart outlives any caveat:

    - fewer than 4 points: no trend to speak of;
    - newest point older than ROLLING_WINDOW_DAYS: the trend describes a
      lifter who stopped; projecting it forward is fiction;
    - slope <= 0: stagnation already has its own vocabulary (cold cyan and
      the word), a projected decline would just be a taunt;
    - milestone further than PROJECTION_HORIZON_DAYS away: too slow to
      promise a date on.

    Returns {'milestone', 'date', 'per_week'} -- per_week is the fitted slope
    in kg/week, carried for the copy.
    """
    if len(points) < 4:
        return None
    ordered = sorted(points, key=lambda p: p[0])[-PROJECTION_FIT_POINTS:]
    newest = ordered[-1][0]
    if (now - newest).days > ROLLING_WINDOW_DAYS:
        return None

    days = [(stamp - newest).total_seconds() / 86400.0 for stamp, _ in ordered]
    values = [value for _, value in ordered]
    n = float(len(ordered))
    mean_x = sum(days) / n
    mean_y = sum(values) / n
    denominator = sum((x - mean_x) ** 2 for x in days)
    if denominator == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(days, values)) / denominator
    if slope <= 0:
        return None

    # The fitted value NOW, not the last raw point: one hot day must not
    # anchor the whole line.
    at_newest = mean_y + slope * (0 - mean_x)
    milestone = math.floor(at_newest / PROJECTION_MILESTONE_KG) * PROJECTION_MILESTONE_KG + PROJECTION_MILESTONE_KG
    days_to = (milestone - at_newest) / slope
    lead_days = (now - newest).total_seconds() / 86400.0
    remaining = days_to - lead_days
    if remaining <= 0 or days_to > PROJECTION_HORIZON_DAYS:
        return None
    return {
        'milestone': milestone,
        'date': now + dt.timedelta(days=remaining),
        'per_week': round(slope * 7.0, 2),
        # For the drawing: the fitted anchor at the newest point, and the
        # slope in kg/day, so the route can turn the trend into coordinates
        # without re-fitting.
        'at_newest': at_newest,
        'slope_per_day': slope,
    }
