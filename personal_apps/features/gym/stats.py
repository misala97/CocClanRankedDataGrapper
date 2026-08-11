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

# What an exercise with no history at all plans for. A template stores only an
# ordered list of exercises -- no set count, no weight, no reps -- so the first
# run of a NEW template hits this too, not just a freestyle workout. Before
# these existed such an exercise arrived with no sets, and the live screen (which
# assumes a plan throughout) called it finished the moment one set was logged.
#
# Three sets is the shape almost every plan starts at. The weight is a
# placeholder and is expected to be wrong -- it is cheap to correct because the
# steppers' readout can be typed into (see session_detail.html).
DEFAULT_PLAN_SETS = 3
DEFAULT_PLAN_REPS = 8
DEFAULT_PLAN_WEIGHT = 20.0


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
    # function below that makes a *judgement* (records, stagnation, averages)
    # drops these rows via _progression_rows(); every function that reports
    # what actually happened (tonnage, balance, consistency) keeps them.
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


def is_new_best(weight, reps, prior_rows):
    """True if one just-logged (weight, reps) pair beats every OTHER
    session's best for this exercise -- the same "beats every OTHER
    session, regardless of when it happened" semantics session_report's own
    is_weight_pr/is_e1rm_pr already use (unscoped by position there too, so
    a set flagged live here always agrees with the flare that same exercise
    gets at session end), just applied to one set the moment it's checked
    instead of a whole session's aggregate after the fact. False with no
    prior history to beat -- a first attempt at an exercise isn't a record
    of anything yet.

    Deload sessions are excluded from `prior_rows`: a light week must not
    lower the bar a normal set is judged against. If deloads are the only
    history, this is False, the same as having no history at all.
    """
    prior_rows = _progression_rows(prior_rows)
    if not prior_rows:
        return False
    return (
        weight > max(best_weight(row) for row in prior_rows)
        or epley_1rm(weight, reps) > max(best_e1rm(row) for row in prior_rows)
    )


def _chronological(rows):
    return sorted(rows, key=lambda row: (row.started_at, row.session_id))


def progression_rows(rows):
    """Only the rows that count as an attempt at progress.

    A deload session is deliberately light: its numbers are not a failed
    attempt at a record, and treating them as one manufactures exactly the
    plateau the deload existed to break. Every function that makes a
    *judgement* -- records, stagnation, volume averages -- starts here.
    Functions that report what actually happened (tonnage, balance,
    consistency, the history table) deliberately do not.

    Public (and called directly from routes.py) because the exercise
    catalogue route has to make the same judgement/report split on its own
    unfiltered rows before handing them to dominant_position/best_e1rm/
    best_weight -- see gym_uebungen()'s own comment for why.
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


def sessions_since_pr(rows, position=None):
    """How many completed sessions in a row have passed without a new best
    estimated 1RM. None when there is too little history to say anything.
    Deload sessions are not counted -- see _progression_rows()."""
    scoped = _scoped(_progression_rows(rows), position)
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


def ready_for_more(rows, position=None):
    """Whether the last comparable session says the working weight has become
    easy -- two or more sets at that session's own heaviest weight, each run
    to a full set's worth of reps.

    Returns the evidence rather than a bare yes: the badge quotes it, the way
    the stagnation line beside it quotes its count. A lifter who cannot see
    why a nudge appeared has to go looking for the reason.

    "That session's heaviest", not an all-time best: the question is whether
    the weight you are actually working at has room left in it, and a ramp-up
    set says nothing about that. Two sets, not one, because one good set is a
    good set and two is a pattern.

    Deload sessions are excluded (progression_rows): light weight for ten reps
    is what a deload IS, so counting it would leave this permanently lit. The
    position lens and its fallback come from _scoped() -- exercise order
    decides how fatigued you were, and a slot with too little history borrows
    from the others rather than going silent.

    This badge and the set chips beside it can name different sessions as
    their evidence, because they use two different lenses on the same
    history:

    - This function, via _scoped(): same slot once that slot has two or more
      sessions logged, ever -- no time limit -- else every position.
    - routes._last_session_exercise(), which pre-fills the chips' weight/
      reps: same slot only while that slot's own record is still younger
      than ROLLING_WINDOW_DAYS, else the most recent session at ANY
      position.

    The two agree while a slot is trained regularly. Once a slot's own
    history goes stale, they can disagree: the badge can still be quoting an
    old same-slot session (this lens has no staleness cutoff) while the chip
    has already fallen back to a different, more recent slot -- so the badge
    reads "Letztes Mal ... 35,0 kg" beside a chip prefilled at 40,0. This is
    a known divergence, not a bug: the badge is answering "was the last time
    in THIS slot easy", the chip is answering "what should I load RIGHT
    NOW", and those are legitimately different questions. Unifying the two
    lenses is a design decision, not a fix -- left alone on purpose.

    What IS a bug is stating that divergence as if it were not one: the
    returned dict carries `is_latest`, true only when the evidence session is
    also the most recent session in `rows` at ANY position. The caller uses
    it to say "Letztes Mal" (a dated claim) only when it is true, and a
    slot-scoped "Zuletzt in diesem Slot" otherwise -- so the sentence never
    asserts a false "last time" about a session that was not, in fact, last.
    """
    prog = progression_rows(rows)
    scoped = _scoped(prog, position)
    if not scoped:
        return None
    last = scoped[-1]
    top = max(weight for weight, _ in last.sets)
    # A bodyweight set (weight 0) has no weight to add -- every set trivially
    # "matches the heaviest weight", so this would otherwise fire forever on
    # a pure-bodyweight exercise instead of only when there is genuinely room
    # to load more.
    if top == 0:
        return None
    qualifying = [reps for weight, reps in last.sets
                  if weight == top and reps >= DELOAD_REPS]
    if len(qualifying) < 2:
        return None
    # "Newest" among the sessions that COUNT, not among all of them: a deload
    # logged after the evidence must not downgrade the wording, because
    # nothing on screen treats that deload as the last time either -- the
    # chips' prefill skips it for the same reason this judgement does.
    newest = _chronological(prog)[-1]
    return {'sets': len(qualifying), 'weight': top, 'is_latest': last is newest}


def exercise_state(rows, position=None, threshold=STAGNATION_THRESHOLD):
    """One of 'neu', 'rekord', 'stagniert', 'steigend', or None for stable.
    Mutually exclusive; first match wins. Deload sessions are excluded
    throughout -- an exercise whose only history is deloads reads 'neu',
    because there is no honest basis for comparison."""
    rows = _progression_rows(rows)
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

    The slot an exercise is judged in (`dominant_position`) is chosen from
    these deload-filtered rows too, so a deload session cannot skew which
    position counts as dominant.
    """
    report = []
    for exercise_id, rows in rows_by_exercise.items():
        # Filtered here; exercise_state() and sessions_since_pr() below each
        # filter again internally. That's by design, not dead code -- both
        # are called elsewhere on unfiltered rows and must stay correct on
        # their own, so _progression_rows() being idempotent means calling
        # it again here costs nothing but keeps this loop honest too.
        rows = _progression_rows(rows)
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
        '{:.1f}'.format(weight).replace('.', ',') + ' × {}'.format(reps)
        for weight, reps in row.sets
    )


def _pr_weight(rows):
    """The heaviest single set ever logged. A deload cannot hold a record."""
    best = None
    for row in _progression_rows(rows):
        for weight, reps in row.sets:
            if best is None or weight > best['weight']:
                best = {'weight': weight, 'reps': reps, 'session_id': row.session_id,
                        'started_at': row.started_at, 'position': row.position}
    return best


def _pr_e1rm(rows):
    """The single set with the highest estimated 1RM -- not always the
    heaviest one, since more reps at less weight can estimate higher. A
    deload cannot hold a record."""
    best = None
    for row in _progression_rows(rows):
        for weight, reps in row.sets:
            value = epley_1rm(weight, reps)
            if best is None or value > best['e1rm']:
                best = {'e1rm': round(value, 1), 'weight': weight, 'reps': reps,
                        'session_id': row.session_id,
                        'started_at': row.started_at, 'position': row.position}
    return best


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
    the chart. The PR and state fields below exclude them.
    """
    chronological = _chronological(rows)
    available_positions = sorted({row.position for row in chronological})
    shown = ([row for row in chronological if row.position == position]
             if position is not None else chronological)

    table = [
        {
            'session_id': row.session_id,
            'started_at': row.started_at,
            'position': row.position,
            'is_deload': row.is_deload,
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
        'sessions_since_pr': sessions_since_pr(rows, position=position),
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


def _verdict(entry, since):
    if not entry['has_history']:
        return 'neu'
    if entry['is_weight_pr'] or entry['is_volume_pr'] or entry['is_e1rm_pr']:
        return 'rekord'
    if since is not None and since >= STAGNATION_THRESHOLD:
        return 'stagniert'
    if entry['volume_delta_pct'] is not None and entry['volume_delta_pct'] > 0:
        return 'steigend'
    return None


def session_report(current, history, comparable_session_volumes=()):
    """The finished-workout page.

    `current` is this session's performed exercises -- the caller must already
    have dropped any exercise that was replaced mid-workout, since its slot is
    represented by the substitute that took over and counting both would
    inflate the total. `history` is every other performed row for those same
    exercises. `comparable_session_volumes` holds the total volume of past
    sessions built from the same template, and is empty for freeform workouts:
    averaging a leg day into a push day produces a number that is arithmetically
    correct and completely meaningless.

    A deload session awards no records and produces no stagnation advice: it
    was never an attempt at either. Past deloads are dropped from `history`
    so they cannot become a baseline or deflate an average.
    """
    # This session's own deload state. Every row in `current` comes from the
    # same session, so any of them answers it; an empty session (no completed
    # sets) is not a deload.
    is_deload = bool(current) and current[0].is_deload

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
        has_history = bool(past_volumes)
        avg_volume = (sum(past_volumes) / len(past_volumes)) if has_history else None

        entry = {
            'exercise_id': row.exercise_id,
            'name': row.name,
            'position': row.position,
            'sets': row.sets,
            'sets_display': _sets_display(row),
            'volume': round(volume, 1),
            'best_weight': weight,
            'e1rm': round(e1rm, 1),
            'has_history': has_history,
            'avg_volume': round(avg_volume, 1) if has_history else None,
            'volume_delta_pct': (round((volume - avg_volume) / avg_volume * 100)
                                 if avg_volume else None),
            'is_weight_pr': (not is_deload) and has_history and weight > max(best_weight(p) for p in past),
            'is_volume_pr': (not is_deload) and has_history and volume > max(past_volumes),
            'is_e1rm_pr': (not is_deload) and has_history and e1rm > max(best_e1rm(p) for p in past),
        }

        since = sessions_since_pr(past + ([] if is_deload else [row]), position=row.position)
        entry['sessions_since_pr'] = since
        entry['verdict'] = None if is_deload else _verdict(entry, since)
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

    # One record per exercise, strongest kind first -- three badges on one
    # lift is noise, and a weight PR already implies the others matter less.
    #
    # Grouped per EXERCISE, not per row: a session that (rarely) logs the same
    # exercise in two slots is one performance of that lift, and
    # session_record_counts() already judges it that way for Heute and Verlauf.
    # Counting each slot separately here is how the same session read
    # "6 Rekorde" in every list and "7 neue Rekorde" as its own headline. The
    # volume bar is per past SESSION (summed across its slots) for the same
    # reason, matching session_record_counts' session_values exactly.
    if not is_deload:
        current_by_exercise = {}
        for row in current:
            current_by_exercise.setdefault(row.exercise_id, []).append(row)

        for exercise_id, rows in current_by_exercise.items():
            past = by_exercise.get(exercise_id, [])
            if not past:
                continue
            weight = max(best_weight(r) for r in rows)
            e1rm = max(best_e1rm(r) for r in rows)
            volume = sum(row_volume(r) for r in rows)

            past_by_session = {}
            for p in past:
                past_by_session.setdefault(p.session_id, []).append(p)
            past_session_volumes = {
                session_id: sum(row_volume(p) for p in session_rows)
                for session_id, session_rows in past_by_session.items()
            }

            if weight > max(best_weight(p) for p in past):
                lead = max(rows, key=best_weight)
                previous_row = max(past, key=best_weight)
                records.append({'kind': 'weight', 'name': lead.name, 'position': lead.position,
                                'exercise_id': exercise_id,
                                'value': weight, 'previous': best_weight(previous_row),
                                'previous_at': previous_row.started_at})
            elif e1rm > max(best_e1rm(p) for p in past):
                lead = max(rows, key=best_e1rm)
                previous_row = max(past, key=best_e1rm)
                records.append({'kind': 'e1rm', 'name': lead.name, 'position': lead.position,
                                'exercise_id': exercise_id,
                                'value': round(e1rm, 1), 'previous': round(best_e1rm(previous_row), 1),
                                'previous_at': previous_row.started_at})
            elif volume > max(past_session_volumes.values()):
                best_session_id = max(past_session_volumes, key=lambda s: past_session_volumes[s])
                records.append({'kind': 'volume', 'name': rows[0].name, 'position': rows[0].position,
                                'exercise_id': exercise_id,
                                'value': round(volume, 1),
                                'previous': round(past_session_volumes[best_session_id], 1),
                                'previous_at': max(p.started_at for p in past_by_session[best_session_id])})

    # NOT by raw value: `value` is kilograms-lifted for a weight record and
    # kilograms-of-volume for a volume one, and a session total is two orders of
    # magnitude larger than anything you actually put on a bar. Sorted that way,
    # a 1.656 kg volume sum outranked a real 62 -> 72 kg strength PR, so the page
    # led with a number nobody lifted.
    #
    # Kind first, because that is the order these mean something in, then by how
    # much the record beat the old one -- relative, so a heavy lift's +2 kg does
    # not automatically outrank a light lift's +5 kg.
    def _record_rank(record):
        kind_order = {'weight': 0, 'e1rm': 1, 'volume': 2}
        previous = record.get('previous') or 0
        gain = ((record['value'] - previous) / previous) if previous else 1.0
        return (kind_order.get(record['kind'], 9), -gain)

    records.sort(key=_record_rank)
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
    """The {session_id: record_count} companion to session_report()'s own
    per-session record_count -- every finished session's count, computed in
    one pass, for a page (Verlauf) that needs all of them at once rather
    than paying an N+1 by calling session_report() once per session.

    Uses the exact same "beats every OTHER session, regardless of when it
    happened" semantics as session_report's is_weight_pr / is_e1rm_pr /
    is_volume_pr -- not "beats only the sessions that came before it" -- so
    a session's number here always agrees with what session_report() would
    compute for that same session, which is what its own detail page shows.
    `rows` is every already-loaded PerformedExercise across every session;
    the caller must already have dropped any exercise that was replaced
    mid-workout (see performed_from_session), the same requirement
    session_report's own `current` carries -- a replaced-away original's
    slot is represented by the substitute that took over, and counting both
    would inflate a session's own totals.

    One pass per exercise, per metric (best weight, best e1RM, summed
    volume): the session holding the single highest value can only be
    compared against the second-highest, since it cannot be said to beat
    itself; every other session is compared against the single highest
    value, since that is the highest bar anyone else has set. That is
    mathematically the same question session_report asks per row (does this
    beat the max of every OTHER session), just answered for every session
    in one sweep instead of one query's worth of "current" at a time.

    A session can (rarely) log the same exercise twice, in two different
    slots -- its rows for that exercise are combined into one per-session
    value first (max weight, max e1RM, summed volume) so that session is
    judged as a single performance on that exercise, not as two rows that
    could otherwise shadow or double-count each other. This mirrors
    session_report itself: two rows in `current` for one exercise would each
    be compared independently against the very same `history`, so a
    stronger row could earn a record while a weaker sibling row from the
    same session correctly does not -- combining first collapses that
    per-exercise decision into the single best-of-both-rows number, which is
    the same one-record-per-exercise-per-session outcome session_report
    produces in the overwhelmingly common case of one row per exercise.

    Deload sessions are excluded outright: they can neither hold a record nor
    be the bar another session has to clear.
    """
    rows_by_exercise = {}
    for row in _progression_rows(rows):
        by_session = rows_by_exercise.setdefault(row.exercise_id, {})
        by_session.setdefault(row.session_id, []).append(row)

    record_counts = {}
    for sessions in rows_by_exercise.values():
        session_values = {
            session_id: {
                'weight': max(best_weight(row) for row in session_rows),
                'e1rm': max(best_e1rm(row) for row in session_rows),
                'volume': sum(row_volume(row) for row in session_rows),
            }
            for session_id, session_rows in sessions.items()
        }

        record_here = set()
        for metric in ('weight', 'e1rm', 'volume'):
            ranked = sorted(session_values.items(), key=lambda item: -item[1][metric])
            top_session_id, top_value = ranked[0][0], ranked[0][1][metric]
            second_value = ranked[1][1][metric] if len(ranked) > 1 else None
            for session_id, values in session_values.items():
                threshold = second_value if session_id == top_session_id else top_value
                if threshold is not None and values[metric] > threshold:
                    record_here.add(session_id)

        for session_id in record_here:
            record_counts[session_id] = record_counts.get(session_id, 0) + 1

    return record_counts


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
