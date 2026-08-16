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
MIN_SESSIONS_PER_DAYPART = 8
MIN_SESSIONS_PER_GAP_BUCKET = 5
MIN_SESSIONS_FOR_WEEKDAY = 14
MIN_TIMED_SESSIONS = 5
MIN_WEEKS_FOR_CONSISTENCY = 4

# Beyond this, a session says more about the finish button than about the
# workout: the stamp is written when the lifter remembers, and a workout
# closed the next morning would drag a mean badly and sit in a median as a
# real six-hour training day. Six hours is deliberately far past any honest
# session rather than close to the observed maximum -- this is a filter for
# broken stamps, not a judgement about training length.
MAX_PLAUSIBLE_SESSION_MINUTES = 360


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
        # Local month: a session at 23:30 on the 31st is stored under the next
        # month in UTC, so it was banded into a month it did not happen in.
        local = stats.to_local(row.started_at)
        key = (local.year, local.month)
        volume[key] += stats.row_volume(row)
        session_month[row.session_id] = key
        if row.is_deload:
            deload_months.add(key)

    record_months = set()
    for record in record_timeline(rows):
        record_local = stats.to_local(record['started_at'])
        record_months.add((record_local.year, record_local.month))

    first = stats.to_local(min(row.started_at for row in rows))
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
# LOCAL clock hours -- "morgens" and "abends" are wall-clock words. Read off
# the stored UTC hour they were two hours out in CEST: an 08:00 workout counted
# as 06:00 and fell out of the morning bucket entirely, and a 20:00 one landed
# outside 19-23 and was filed as "other". Every consumer below converts first.
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
        hour = stats.to_local(started_at).hour
        for label, low, high in DAYPARTS:
            if low <= hour < high:
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
    volume = {index: 0.0 for index in WEEKDAYS}
    for started_at, session_volume in sessions:
        # Local weekday: a Monday 00:30 session is stored as Sunday 22:30 UTC
        # and was being counted against Sunday.
        index = stats.to_local(started_at).weekday()
        counts[index] += 1
        volume[index] += session_volume

    total = len(sessions)
    return {
        # `avg_volume` per session, not summed: the favourite day would
        # otherwise win on volume by definition, having been trained most
        # often, and "your best day" would just restate "your usual day".
        'days': [
            {'weekday': index, 'sessions': counts[index],
             'share': round(counts[index] / total * 100, 1) if total else 0.0,
             'avg_volume': round(volume[index] / counts[index], 1) if counts[index] else 0.0}
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
         'avg_volume': round(sum(buckets[label]) / len(buckets[label]), 1) if buckets[label] else 0.0,
         'shown': len(buckets[label]) >= MIN_SESSIONS_PER_GAP_BUCKET}
        for label, _, _ in GAP_BUCKETS
    ]
    return {
        'buckets': result,
        # Buckets are judged one at a time, not as a set. Demanding that EVERY
        # populated bucket clear the threshold sounds strict but is perverse:
        # it lets the rarest gap veto the commonest ones, so the card gets
        # quieter the more lopsided a real training habit is. Measured on this
        # log at 29 sessions -- 0-1 days (17) and 2 days (5) both well past the
        # bar, sunk by 3 days (4) and 4+ days (2) -- and unreachable in
        # practice, because someone who trains every other day never
        # accumulates five four-day breaks to unlock the comparison they are
        # already entitled to.
        #
        # A bucket short of the threshold is simply not drawn, and `thin` names
        # it in the caption so the missing bar reads as "not yet" rather than
        # as a bar nobody designed. Two shown buckets are still required: one
        # bar is a number, not a relationship.
        'thin': [b for b in result if b['sessions'] and not b['shown']],
        'statable': len([b for b in result if b['shown']]) >= 2,
    }


def _median(values):
    """Middle value, averaging the two middles on an even count."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def session_length(rows):
    """How long a workout takes, and how much gets moved per minute.

    Medians, not means. The stamps this reads are written by a human pressing
    a button, so the tail is made of forgetting rather than of training, and
    one session closed the next morning would drag a mean by half an hour.

    A session with no finish stamp is `untimed`, never zero: this log's first
    eight sessions predate the stamp entirely, and counting them as
    zero-minute workouts would halve every figure here. The count is reported
    so the page can say what its median is actually built from.
    """
    sessions = {}
    for row in rows:
        started, finished, volume = sessions.get(
            row.session_id, (row.started_at, row.finished_at, 0.0))
        sessions[row.session_id] = (started, finished, volume + stats.row_volume(row))

    minutes = []
    densities = []
    untimed = 0
    for started, finished, volume in sessions.values():
        span = (finished - started).total_seconds() / 60 if finished else 0
        if not 0 < span <= MAX_PLAUSIBLE_SESSION_MINUTES:
            untimed += 1
            continue
        minutes.append(span)
        densities.append(volume / span)

    return {
        'sample': len(minutes),
        'untimed': untimed,
        'statable': len(minutes) >= MIN_TIMED_SESSIONS,
        'median_minutes': round(_median(minutes)) if minutes else None,
        'volume_per_minute': round(_median(densities), 1) if densities else None,
    }


def _week_index(moment, origin):
    """Whole weeks between two moments, counted from Monday to Monday, so two
    sessions in the same calendar week always land on the same number."""
    local = stats.to_local(moment).date()
    start = stats.to_local(origin).date()
    return ((local - dt.timedelta(days=local.weekday()))
            - (start - dt.timedelta(days=start.weekday()))).days // 7


def consistency(rows, now):
    """Showing up, measured in weeks rather than in tonnage.

    The career strip already says how much was lifted per month; nothing said
    how regular it was, and a heavy fortnight followed by nothing looks the
    same as steady training once it is summed into a bar.

    The week is the unit because training splits are weekly -- a day-level
    streak would punish every rest day the plan asks for.

    The CURRENT week can only ever extend a streak, never end one: it has not
    had its chance yet, and a streak that collapses every Monday morning
    measures the calendar rather than the lifter.
    """
    if not rows:
        return {'weeks_trained': 0, 'weeks_total': 0, 'share': 0.0,
                'current_streak': 0, 'longest_streak': 0, 'statable': False}

    first = min(row.started_at for row in rows)
    trained = {_week_index(row.started_at, first) for row in rows}
    this_week = _week_index(now, first)

    longest = streak = 0
    for index in range(this_week + 1):
        streak = streak + 1 if index in trained else 0
        longest = max(longest, streak)

    # Count back from the current week, or from last week while the current
    # one is still open.
    current = 0
    cursor = this_week if this_week in trained else this_week - 1
    while cursor >= 0 and cursor in trained:
        current += 1
        cursor -= 1

    weeks_total = this_week + 1
    return {
        'weeks_trained': len(trained),
        'weeks_total': weeks_total,
        'share': round(len(trained) / weeks_total * 100, 1),
        'current_streak': current,
        'longest_streak': longest,
        'statable': weeks_total >= MIN_WEEKS_FOR_CONSISTENCY,
    }


DRIFT_WINDOW_DAYS = 28
MIN_SESSIONS_PER_DRIFT_PERIOD = 4
MIN_SESSIONS_FOR_DROUGHT = 3


def balance_drift(rows, now):
    """What the training has been made of lately, against what it used to be.

    effort_distribution() answers the same question over the whole history,
    which is exactly why it cannot answer this one: a group neglected for a
    month still carries its lifetime share, so the page can show a balanced
    split while the last four weeks were anything but.

    Shares rather than tonnage on both sides. Absolute volume moves with how
    much was trained at all, and a lifter who simply did less last month would
    read as having abandoned every muscle group at once.

    Both periods must hold real training. Everything before the window is the
    comparison, so a lifter one window into their history has nothing to have
    drifted from -- that is silence, not a drift of zero.
    """
    cutoff = now - dt.timedelta(days=DRIFT_WINDOW_DAYS)
    recent_volume = defaultdict(float)
    earlier_volume = defaultdict(float)
    recent_sessions = set()
    earlier_sessions = set()

    for row in rows:
        recent = row.started_at >= cutoff
        volume = (recent_volume if recent else earlier_volume)
        sessions = (recent_sessions if recent else earlier_sessions)
        volume[row.muscle_group] += stats.row_volume(row)
        sessions.add(row.session_id)

    recent_total = sum(recent_volume.values())
    earlier_total = sum(earlier_volume.values())
    groups = []
    for label in set(recent_volume) | set(earlier_volume):
        recent_share = round(recent_volume[label] / recent_total * 100, 1) if recent_total else 0.0
        earlier_share = round(earlier_volume[label] / earlier_total * 100, 1) if earlier_total else 0.0
        groups.append({
            'label': label,
            'recent_share': recent_share,
            'earlier_share': earlier_share,
            'delta': round(recent_share - earlier_share, 1),
        })
    groups.sort(key=lambda g: (-g['delta'], g['label'] or ''))

    return {
        'window_days': DRIFT_WINDOW_DAYS,
        'groups': groups,
        'recent_sessions': len(recent_sessions),
        'earlier_sessions': len(earlier_sessions),
        'statable': (len(recent_sessions) >= MIN_SESSIONS_PER_DRIFT_PERIOD
                     and len(earlier_sessions) >= MIN_SESSIONS_PER_DRIFT_PERIOD),
    }


def _notch_count(from_weight, to_weight, increment, stack):
    """How many real positions of this machine separate two weights.

    A percentage would be the honest general answer, but it is not the one the
    gym gives back: the next weight is the next pin hole or the next pair of
    dumbbells, and on an uneven stack those are not evenly spaced at all.
    """
    if stack:
        # The position itself, which stats.snap_to_stack cannot give back --
        # it answers with a weight, and the distance between two stops of an
        # uneven stack is exactly what a weight cannot express.
        steps = sorted(stack)

        def position(weight):
            return sum(1 for step in steps if step <= weight)

        return position(to_weight) - position(from_weight)
    step = increment or stats.DEFAULT_INCREMENT
    return int(round((to_weight - from_weight) / step))


def increment_ladder(rows):
    """Progress counted in the steps this equipment actually has.

    A judgement, so deload rows are dropped -- a deliberately light week is
    not a rung anyone climbed down.

    Per exercise, from the working weight of its first session to the heaviest
    ever worked. First SESSION rather than lightest ever: the question is how
    far the lift has come from where it started, and a bad day two months in
    is not a starting point.
    """
    by_exercise = defaultdict(dict)
    for row in stats.progression_rows(rows):
        best = stats.best_weight(row)
        seen = by_exercise[row.exercise_id].get(row.session_id)
        by_exercise[row.exercise_id][row.session_id] = (
            row.started_at, max(best, seen[1]) if seen else best, row)

    exercises = []
    for sessions in by_exercise.values():
        ordered = sorted(sessions.values(), key=lambda entry: entry[0])
        first_weight = ordered[0][1]
        best_weight = max(weight for _, weight, _ in ordered)
        sample_row = ordered[0][2]
        notches = _notch_count(first_weight, best_weight,
                               sample_row.weight_increment, sample_row.stack_kg)
        exercises.append({
            'exercise_id': sample_row.exercise_id,
            'name': sample_row.name,
            'notches': notches,
            'from_weight': round(first_weight, 1),
            'to_weight': round(best_weight, 1),
            'sessions': len(ordered),
        })

    exercises.sort(key=lambda entry: (-entry['notches'], entry['name']))
    return {
        'exercises': exercises,
        'total_notches': sum(entry['notches'] for entry in exercises),
        'statable': bool(exercises),
    }


def record_drought(rows):
    """How long each lift has gone without beating itself.

    The mirror of progression_ranking(), and the more actionable half: knowing
    which lifts moved most is pleasant, knowing which one has not moved in two
    months is what changes next week's session.

    Sessions, not days. A lift trained twice a month and one trained twice a
    week have not stalled equally after four weeks, and the count of attempts
    is what "stale" actually means here.

    An exercise that never set a record counts from its debut. The debut is
    deliberately not a record (see record_timeline), but it is still the last
    time the number moved, so the drought runs from there rather than being
    reported as unanswerable.
    """
    last_record = {}
    for record in record_timeline(rows):
        exercise_id = record['exercise_id']
        if exercise_id not in last_record:      # newest first, so the first wins
            last_record[exercise_id] = record['started_at']

    by_exercise = defaultdict(dict)
    for row in stats.progression_rows(rows):
        by_exercise[row.exercise_id][row.session_id] = (row.started_at, row.name)

    exercises = []
    for exercise_id, sessions in by_exercise.items():
        ordered = sorted(sessions.values())
        if len(ordered) < MIN_SESSIONS_FOR_DROUGHT:
            continue
        anchor = last_record.get(exercise_id, ordered[0][0])
        exercises.append({
            'exercise_id': exercise_id,
            'name': ordered[0][1],
            'sessions': len(ordered),
            'sessions_since': sum(1 for started_at, _ in ordered if started_at > anchor),
            'last_record_at': last_record.get(exercise_id),
        })

    exercises.sort(key=lambda entry: (-entry['sessions_since'], entry['name']))
    return {'exercises': exercises, 'statable': bool(exercises)}


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
    worth stating because neither is local: `rows` is already scoped to one
    user by load_performed(), and the catalogue's uniqueness constraint is
    (user_id, name) -- so within that one user's rows a name is unique and two
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
            # ONE entry per exercise-day, carrying whichever bests it set.
            #
            # These used to be two rows. They are not two events: e1RM is Epley
            # arithmetic over the same set, so it moves whenever weight or reps
            # move, and a weight PB almost always drags an e1RM PB along with
            # it -- 43 of 57 rows on a real history were e1RM, and 12 dates
            # carried both kinds for the same lift. Two rows made one lift look
            # like two milestones and made the timeline's own count untrue to
            # what happened. Nothing is dropped: both figures ride on the row.
            entry = None
            if best_weight is not None and weight > best_weight:
                entry = {'started_at': started_at, 'session_id': session_id,
                         'exercise_id': exercise_id, 'name': name,
                         'weight': {'value': round(weight, 1), 'previous': round(best_weight, 1)},
                         'e1rm': None}
            if best_e1rm is not None and e1rm > best_e1rm:
                gain = {'value': round(e1rm, 1), 'previous': round(best_e1rm, 1)}
                if entry is None:
                    entry = {'started_at': started_at, 'session_id': session_id,
                             'exercise_id': exercise_id, 'name': name,
                             'weight': None, 'e1rm': gain}
                else:
                    entry['e1rm'] = gain
            if entry is not None:
                timeline.append(entry)
            best_weight = weight if best_weight is None else max(best_weight, weight)
            best_e1rm = e1rm if best_e1rm is None else max(best_e1rm, e1rm)

    timeline.sort(key=lambda entry: (entry['started_at'], entry['name']), reverse=True)
    return timeline
