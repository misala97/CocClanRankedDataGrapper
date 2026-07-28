"""All-time analytics for the Statistik page.

The split from stats.py mirrors the split between the pages themselves:

    stats.py      windowed, per-session JUDGEMENTS -- is this a record, is
                  this stalling, what does the last 28 days look like.
                  Feeds Heute and the session pages.

    analytics.py  all-time AGGREGATES and DESCRIPTIONS -- totals, rankings,
                  distributions, behavioural patterns over the whole history.
                  Feeds Statistik.

The same question that decides which page a figure belongs on decides which
module it lives in: is this about now, or about everything?

This module may import from stats.py; stats.py must never import from here.
Like stats.py it is deliberately free of SQLAlchemy, Flask and Jinja -- it
sees stats.PerformedExercise and plain data, nothing else.

It also contains NO German prose. Every function returns figures plus a
`statable` flag where a finding is involved; the template writes the sentence.
Copy belongs in one place, and a module that returns numbers is one that can
be unit-tested.
"""
import datetime as dt
from collections import defaultdict

from . import stats

# --- silence thresholds -----------------------------------------------------
# A stated finding must never outrun its sample. Each figure below is the
# point at which a pattern stops being plausibly coincidental for one lifter's
# log, set deliberately low enough that the page says something in its first
# months. They gate the SENTENCE only -- the chart always renders, annotated
# with its own sample size, so nothing is ever hidden.
MIN_SETS_FOR_REP_RANGE = 50
MIN_ROWS_FOR_FATIGUE = 30


def _sessions(rows):
    """{session_id: started_at} across the given rows."""
    return {row.session_id: row.started_at for row in rows}


def totals(rows, now):
    """Das Werk: the cumulative body of work, all time.

    Deload sessions are included -- this describes what was actually lifted,
    and a deliberately light session was still lifted.

    `days_training` counts from the first session to `now` rather than to the
    last session: the span is how long you have been at it, not how long the
    log happens to cover.
    """
    if not rows:
        return {'tonnage': 0, 'sets': 0, 'reps': 0, 'sessions': 0,
                'first_session': None, 'days_training': None, 'best_session': None}

    volume_by_session = defaultdict(float)
    for row in rows:
        volume_by_session[row.session_id] += stats.row_volume(row)

    started = _sessions(rows)
    best_id = max(volume_by_session, key=lambda sid: volume_by_session[sid])
    first = min(started.values())

    return {
        'tonnage': round(sum(volume_by_session.values()), 1),
        'sets': sum(len(row.sets) for row in rows),
        'reps': sum(reps for row in rows for _, reps in row.sets),
        'sessions': len(volume_by_session),
        'first_session': first,
        'days_training': (now - first).days,
        'best_session': {
            'session_id': best_id,
            'started_at': started[best_id],
            'volume': round(volume_by_session[best_id], 1),
        },
    }


def progression_ranking(rows):
    """Fortschritt: every exercise ranked by all-time change in estimated 1RM.

    A judgement, so deload rows are dropped via stats.progression_rows() --
    a deliberately light session is not an attempt at a heavier one, and a
    200 kg typo in a deload week must not become anyone's "current".

    An exercise needs two qualifying sessions: with one there is no
    first-versus-current to compute, and reporting 0 % would be a claim the
    data does not make.

    `points` is the per-session best e1RM in chronological order, for the
    sparkline. One point per session, not per set.
    """
    by_exercise = defaultdict(list)
    for row in stats.progression_rows(rows):
        by_exercise[row.exercise_id].append(row)

    ranking = []
    for exercise_id, exercise_rows in by_exercise.items():
        # one entry per session: an exercise performed twice in a session
        # (two slots) is still one data point on its curve
        best_per_session = {}
        for row in exercise_rows:
            current = stats.best_e1rm(row)
            seen = best_per_session.get(row.session_id)
            if seen is None or current > seen[1]:
                best_per_session[row.session_id] = (row.started_at, current)

        ordered = sorted(best_per_session.values())
        if len(ordered) < 2:
            continue

        first_e1rm = ordered[0][1]
        current_e1rm = ordered[-1][1]

        # No baseline, no percentage. epley_1rm() returns 0 for a bodyweight
        # set (weight 0), which this app supports deliberately -- see
        # stats.deload_weight()'s own bodyweight branch. Dividing by it would
        # raise inside this loop and take the whole ranking down with it, so
        # the exercise is skipped for the same reason a single-session one is:
        # there is nothing to measure the change against.
        if first_e1rm <= 0:
            continue

        ranking.append({
            'exercise_id': exercise_id,
            'name': exercise_rows[0].name,
            'sessions': len(ordered),
            'first_e1rm': round(first_e1rm, 1),
            'current_e1rm': round(current_e1rm, 1),
            'change_pct': round((current_e1rm - first_e1rm) / first_e1rm * 100, 1),
            'best_weight': max(stats.best_weight(row) for row in exercise_rows),
            'points': [round(value, 1) for _, value in ordered],
        })

    ranking.sort(key=lambda entry: (-entry['change_pct'], entry['name']))
    return ranking


# Rep buckets, and the boundaries the app already uses when it talks about
# rep ranges: heavy / working / hypertrophy / endurance.
REP_BUCKETS = (('1-5', 1, 5), ('6-8', 6, 8), ('9-12', 9, 12), ('13+', 13, None))


def rep_range_distribution(rows):
    """How the lifter's sets distribute across rep ranges, all time.

    A description, so deload sets are included -- eight reps in a light week
    is still eight reps.
    """
    counts = {label: 0 for label, _, _ in REP_BUCKETS}
    for row in rows:
        for _, reps in row.sets:
            for label, low, high in REP_BUCKETS:
                if reps >= low and (high is None or reps <= high):
                    counts[label] += 1
                    break

    sample = sum(counts.values())
    buckets = [
        {'label': label, 'sets': counts[label],
         'share': round(counts[label] / sample * 100, 1) if sample else 0.0}
        for label, _, _ in REP_BUCKETS
    ]
    dominant = max(buckets, key=lambda b: b['sets']) if sample else None
    return {
        'buckets': buckets,
        'sample': sample,
        'dominant': dominant,
        'statable': sample >= MIN_SETS_FOR_REP_RANGE,
    }


def fatigue_curve(rows):
    """How much the lifter drops off within one exercise: first set vs last.

    Only rows with at least two sets can answer this; a single-set row has no
    drop-off to measure and is excluded from the sample rather than counted as
    zero, which would flatten the average toward nothing.

    A description, so deloads are included.
    """
    weight_deltas = []
    first_reps = []
    last_reps = []
    for row in rows:
        if len(row.sets) < 2:
            continue
        (first_weight, first_rep) = row.sets[0]
        (last_weight, last_rep) = row.sets[-1]
        if first_weight > 0:
            weight_deltas.append((last_weight - first_weight) / first_weight * 100)
        first_reps.append(first_rep)
        last_reps.append(last_rep)

    sample = len(first_reps)
    if not sample:
        return {'sample': 0, 'statable': False, 'weight_change_pct': None,
                'first_reps': None, 'last_reps': None}

    return {
        'sample': sample,
        'statable': sample >= MIN_ROWS_FOR_FATIGUE,
        'weight_change_pct': (round(sum(weight_deltas) / len(weight_deltas), 1)
                              if weight_deltas else None),
        'first_reps': round(sum(first_reps) / sample, 1),
        'last_reps': round(sum(last_reps) / sample, 1),
    }
