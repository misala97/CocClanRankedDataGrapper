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
MIN_SESSIONS_PER_DAYPART = 8
MIN_SESSIONS_PER_GAP_BUCKET = 5
MIN_SESSIONS_FOR_WEEKDAY = 14


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


def monthly_tonnage(rows, now):
    """Every month since the first workout, in order, with its tonnage.

    The career strip on Statistik. Heute keeps eight weeks and nothing kept the
    rest, so the one figure an all-time page should obviously hold did not
    exist anywhere.

    Months with no training are still emitted, with zero volume and
    `is_gap` set. Skipping them would compress a three-month break into a
    single bar gap and quietly redraw the timeline as though it never happened
    -- the point of this strip is that it is a real calendar.

    `has_record` marks a month containing at least one all-time best (weight or
    e1RM), computed against every row, so the marks agree with what
    record_timeline() lists. `has_deload` marks a month containing a deload
    session; deloads still contribute their tonnage, exactly as they do to
    totals().
    """
    if not rows:
        return []

    volume = defaultdict(float)
    deload_months = set()
    session_month = {}
    for row in rows:
        key = (row.started_at.year, row.started_at.month)
        volume[key] += stats.row_volume(row)
        session_month[row.session_id] = key
        if row.is_deload:
            deload_months.add(key)

    record_months = set()
    for record in record_timeline(rows):
        record_months.add((record['started_at'].year, record['started_at'].month))

    first = min(row.started_at for row in rows)
    year, month = first.year, first.month
    last = (now.year, now.month)

    out = []
    while (year, month) <= last:
        key = (year, month)
        out.append({
            'year': year,
            'month': month,
            'volume': round(volume.get(key, 0.0), 1),
            'is_gap': key not in volume,
            'has_deload': key in deload_months,
            'has_record': key in record_months,
        })
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


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
    skipped = 0
    for row in rows:
        for _, reps in row.sets:
            for label, low, high in REP_BUCKETS:
                if reps >= low and (high is None or reps <= high):
                    counts[label] += 1
                    break
            else:
                # A set logged at zero (or fewer) reps is a failed attempt, not
                # a rep range -- filing it under "1-5" would be a lie, and
                # letting it fall through the buckets unnoticed would quietly
                # shrink the sample this function's finding is judged against.
                # Excluded on purpose, and counted so the caller can say so.
                skipped += 1

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
        'skipped': skipped,
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


# The two clusters the training log actually contains. Sessions outside both
# fall into `other`, which is reported but never carries a finding -- a
# bucket defined as "everything else" cannot support a claim about behaviour.
DAYPARTS = (('morning', 8, 14), ('evening', 19, 23))
WEEKDAYS = tuple(range(7))   # 0 = Monday, matching datetime.weekday()
GAP_BUCKETS = (('0-1', 0, 1), ('2', 2, 2), ('3', 3, 3), ('4+', 4, None))


def _session_volumes(rows):
    """[(started_at, volume)] per session, chronological."""
    volume = defaultdict(float)
    started = {}
    for row in rows:
        volume[row.session_id] += stats.row_volume(row)
        started[row.session_id] = row.started_at
    return sorted((started[sid], volume[sid]) for sid in volume)


def daypart_volume(rows):
    """Volume per session by time of day.

    Per session, not total: a bucket with more sessions in it would otherwise
    always "win", which measures how often you train then, not how well.

    Statable only when BOTH named buckets clear the threshold -- eleven
    mornings against two evenings is not a comparison, it is one bucket.
    """
    sessions = _session_volumes(rows)
    buckets = {label: [] for label, _, _ in DAYPARTS}
    buckets['other'] = []
    for started_at, volume in sessions:
        for label, low, high in DAYPARTS:
            if low <= started_at.hour < high:
                buckets[label].append(volume)
                break
        else:
            buckets['other'].append(volume)

    parts = [
        {'label': label,
         'sessions': len(buckets[label]),
         'volume': round(sum(buckets[label]), 1),
         'avg_volume': round(sum(buckets[label]) / len(buckets[label]), 1) if buckets[label] else 0.0}
        for label in list(dict.fromkeys([label for label, _, _ in DAYPARTS] + ['other']))
    ]
    named = [p for p in parts if p['label'] != 'other']
    return {
        'parts': parts,
        'statable': all(p['sessions'] >= MIN_SESSIONS_PER_DAYPART for p in named),
    }


def weekday_distribution(rows):
    """Sessions per weekday, Monday first, as an INDEX (0-6) not a label --
    this module holds no user-visible copy.

    Every weekday is always present, including the ones never trained: a
    missing Sunday and a Sunday at zero are different facts, and only one of
    them is true."""
    sessions = _session_volumes(rows)
    counts = {index: 0 for index in WEEKDAYS}
    for started_at, _ in sessions:
        counts[started_at.weekday()] += 1

    total = len(sessions)
    return {
        'days': [
            {'weekday': index, 'sessions': counts[index],
             'share': round(counts[index] / total * 100, 1) if total else 0.0}
            for index in WEEKDAYS
        ],
        'sample': total,
        'statable': total >= MIN_SESSIONS_FOR_WEEKDAY,
    }


def rest_gap_effect(rows):
    """Volume as a function of days since the previous session.

    The first session has no previous one and is excluded -- it has no gap,
    which is not the same as a gap of zero.
    """
    sessions = _session_volumes(rows)
    buckets = {label: [] for label, _, _ in GAP_BUCKETS}
    for index in range(1, len(sessions)):
        gap = (sessions[index][0] - sessions[index - 1][0]).days
        for label, low, high in GAP_BUCKETS:
            if gap >= low and (high is None or gap <= high):
                buckets[label].append(sessions[index][1])
                break

    result = [
        {'label': label,
         'sessions': len(buckets[label]),
         'avg_volume': round(sum(buckets[label]) / len(buckets[label]), 1) if buckets[label] else 0.0}
        for label, _, _ in GAP_BUCKETS
    ]
    populated = [b for b in result if b['sessions']]
    return {
        'buckets': result,
        # every bucket that exists at all must be big enough, and there must be
        # at least two of them -- one bucket is a number, not a relationship
        'statable': (len(populated) >= 2
                     and all(b['sessions'] >= MIN_SESSIONS_PER_GAP_BUCKET for b in populated)),
    }


def _share_table(pairs, total):
    """[{label, volume, sets, share}] sorted by volume, biggest first."""
    table = [
        {'label': label, 'volume': round(volume, 1), 'sets': sets,
         'share': round(volume / total * 100, 1) if total else 0.0}
        for label, (volume, sets) in pairs.items()
    ]
    table.sort(key=lambda entry: (-entry['volume'], entry['label']))
    return table


def effort_distribution(rows):
    """Wohin die Arbeit geht: where the tonnage actually went, all time.

    Split two ways -- by muscle group and by exercise -- because they answer
    different questions: whether the body is trained evenly, and which lifts
    the training is actually made of.

    A description, so deloads are included.

    Nothing is synthesised at zero. An exercise never performed has no row
    here at all, and a group with no trained exercises simply does not appear.
    Heute's muscle_group_volume() deliberately does the opposite, because
    there a group at zero IS the finding; here absence is just absence.

    Exercises are keyed by name rather than id, which is safe for two reasons
    worth stating because neither is local: Exercise.name is unique, so two
    exercises can never collapse into one bucket; and _to_performed() resolves
    the name through a live join, so every row carries the CURRENT name and a
    rename moves an exercise's whole history rather than splitting it. If that
    join were ever changed to snapshot the name at log time, this function
    would start silently splitting renamed exercises in two.
    """
    groups = defaultdict(lambda: [0.0, 0])
    exercises = defaultdict(lambda: [0.0, 0])
    total = 0.0
    for row in rows:
        volume = stats.row_volume(row)
        total += volume
        group = row.muscle_group or stats.NO_GROUP_LABEL
        groups[group][0] += volume
        groups[group][1] += len(row.sets)
        exercises[row.name][0] += volume
        exercises[row.name][1] += len(row.sets)

    return {
        'groups': _share_table({k: tuple(v) for k, v in groups.items()}, total),
        'exercises': _share_table({k: tuple(v) for k, v in exercises.items()}, total),
        'total_volume': round(total, 1),
    }


def record_timeline(rows):
    """Rekorde: every personal best ever set, newest first.

    A judgement, so deload rows are dropped -- a light week cannot hold a
    record.

    Chronological by construction: a record is a session that beat every
    EARLIER session for that exercise. stats.session_record_counts() asks a
    deliberately different question ("beats every OTHER session") so a page can
    show a count that does not change as later sessions arrive. A timeline is a
    history, and history is what was true on the day.

    The first session of an exercise is never a record: there was nothing to
    beat, and calling it one would make every exercise's debut a milestone.
    """
    by_exercise = defaultdict(dict)
    for row in stats.progression_rows(rows):
        seen = by_exercise[row.exercise_id].get(row.session_id)
        candidate = (row.started_at, stats.best_weight(row), stats.best_e1rm(row), row.name)
        if seen is None:
            by_exercise[row.exercise_id][row.session_id] = candidate
        else:
            # same exercise twice in one session: judge it as its best showing
            by_exercise[row.exercise_id][row.session_id] = (
                seen[0], max(seen[1], candidate[1]), max(seen[2], candidate[2]), seen[3])

    timeline = []
    for exercise_id, sessions in by_exercise.items():
        ordered = sorted(sessions.items(), key=lambda item: item[1][0])
        best_weight = None
        best_e1rm = None
        for session_id, (started_at, weight, e1rm, name) in ordered:
            if best_weight is not None and weight > best_weight:
                timeline.append({'started_at': started_at, 'session_id': session_id,
                                 'exercise_id': exercise_id, 'name': name,
                                 'kind': 'weight', 'value': round(weight, 1),
                                 'previous': round(best_weight, 1)})
            if best_e1rm is not None and e1rm > best_e1rm:
                timeline.append({'started_at': started_at, 'session_id': session_id,
                                 'exercise_id': exercise_id, 'name': name,
                                 'kind': 'e1rm', 'value': round(e1rm, 1),
                                 'previous': round(best_e1rm, 1)})
            best_weight = weight if best_weight is None else max(best_weight, weight)
            best_e1rm = e1rm if best_e1rm is None else max(best_e1rm, e1rm)

    timeline.sort(key=lambda entry: (entry['started_at'], entry['name']), reverse=True)
    return timeline
