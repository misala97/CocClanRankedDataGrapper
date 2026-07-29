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
    return ', '.join('{:g} kg x {}'.format(weight, reps) for weight, reps in row.sets)


def _pr_weight(rows):
    """The heaviest single set ever logged. A deload cannot hold a record."""
    best = None
    for row in _progression_rows(rows):
        for weight, reps in row.sets:
            if best is None or weight > best['weight']:
                best = {'weight': weight, 'reps': reps,
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


def _next_weight(weight, is_unilateral):
    """The smallest honest jump up. 2.5 kg is the smallest pair of plates on
    most bars; a unilateral lift moves one side at a time, so half that."""
    return weight + (1.25 if is_unilateral else 2.5)


def deload_weight(weight, pct, is_unilateral):
    """`pct` of a working weight, rounded DOWN to a loadable increment.

    Down, not to nearest: rounding a deload up makes it heavier than
    prescribed, which is the one direction that defeats the point. The
    increments mirror _next_weight() -- 2.5 kg is the smallest pair of plates
    on most bars, and a unilateral lift moves one side at a time.

    Applied per set by the caller, never to the top set alone, so any ramping
    or drop-off in the session's shape survives the deload.
    """
    if weight <= 0:
        return weight          # a bodyweight set stays bodyweight
    step = 1.25 if is_unilateral else 2.5
    return max(step, math.floor(weight * pct / 100.0 / step) * step)


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

        # One record per exercise, strongest kind first -- three badges on one
        # lift is noise, and a weight PR already implies the others matter less.
        if entry['is_weight_pr']:
            previous_row = max(past, key=best_weight)
            records.append({'kind': 'weight', 'name': row.name, 'position': row.position,
                            'value': weight, 'previous': best_weight(previous_row),
                            'previous_at': previous_row.started_at})
        elif entry['is_e1rm_pr']:
            previous_row = max(past, key=best_e1rm)
            records.append({'kind': 'e1rm', 'name': row.name, 'position': row.position,
                            'value': round(e1rm, 1), 'previous': round(best_e1rm(previous_row), 1),
                            'previous_at': previous_row.started_at})
        elif entry['is_volume_pr']:
            previous_row = max(past, key=row_volume)
            records.append({'kind': 'volume', 'name': row.name, 'position': row.position,
                            'value': round(volume, 1), 'previous': round(row_volume(previous_row), 1),
                            'previous_at': previous_row.started_at})

        if entry['verdict'] == 'stagniert':
            advice.append({
                'exercise_id': row.exercise_id,
                'name': row.name,
                'stuck_at': weight,
                'sessions': since,
                'suggested_weight': _next_weight(weight, row.is_unilateral),
            })

    records.sort(key=lambda record: -record['value'])
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
    """Monday 00:00 of the ISO week `moment` falls in."""
    monday = moment.date() - dt.timedelta(days=moment.weekday())
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
        'days_since_last': (now - latest).days if latest else None,
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
            'days_ago': (now - last).days if last else None,
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
