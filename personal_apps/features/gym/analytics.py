"""All-time aggregates for Verlauf.

The split from stats.py mirrors the split between the pages themselves:

    stats.py      windowed, per-session JUDGEMENTS -- is this a record, is
                  this stalling, what does the last 28 days look like.
                  Feeds Start, the exercise pages and the session pages.

    analytics.py  all-time AGGREGATES -- the months, the weeks, every record
                  -- over the whole history. Feeds Verlauf, which took them
                  over when Statistik was folded into Start and Verlauf (M3,
                  D7-C); what only Statistik read went with it.

The same question that decides which page a figure belongs on decides which
module it lives in: is this about now, or about everything?

This module may import from stats.py; stats.py must never import from here.
Like stats.py it is deliberately free of SQLAlchemy, Flask and Jinja -- it
sees stats.PerformedExercise and plain data, nothing else.

It also contains NO German prose. Every function returns figures plus a
`statable` flag where a finding is involved; the page writes the sentence.
Copy belongs in one place, and a module that returns numbers is one that can
be unit-tested.
"""
import datetime as dt
from collections import defaultdict

from . import stats

# A stated finding must never outrun its sample: a share of three weeks says
# nothing about how regular someone trains.
MIN_WEEKS_FOR_CONSISTENCY = 4


def monthly_tonnage(rows, now, first=None):
    """Every month since the first workout, in order, with its tonnage.

    Verlauf's month index (M3; it was Statistik's career strip). Start keeps
    eight weeks and nothing kept the rest, so the one figure an all-time page
    should obviously hold did not exist anywhere. `first` starts the strip
    at an earlier moment than the first row: Verlauf lists a workout that
    logged nothing, and its month has a band to link to.

    Months with no training are still emitted, with zero volume and
    `is_gap` set. Skipping them would compress a three-month break into a
    single bar gap and quietly redraw the timeline as though it never happened
    -- the point of this strip is that it is a real calendar.

    `records` counts the month's records -- record_timeline()'s entries, so
    the two agree. It was a yes/no mark, and with a record in every month it
    sat on every bar and said nothing (G-026). `deload_volume` is the part of
    the month's tonnage lifted in deload workouts: a month with one light
    week was hatched whole, the biggest two months of the year included.
    Deloads still count in `volume`: a light workout was still lifted.
    """
    starts = [row.started_at for row in rows] + ([first] if first is not None else [])
    if not starts:
        return []

    volume = defaultdict(float)
    deload_volume = defaultdict(float)
    for row in rows:
        # Local month: a session at 23:30 on the 31st is stored under the next
        # month in UTC, so it was banded into a month it did not happen in.
        local = stats.to_local(row.started_at)
        key = (local.year, local.month)
        volume[key] += stats.row_volume(row)
        if row.is_deload:
            deload_volume[key] += stats.row_volume(row)

    records = defaultdict(int)
    for record in record_timeline(rows):
        record_local = stats.to_local(record['started_at'])
        records[(record_local.year, record_local.month)] += 1

    oldest = stats.to_local(min(starts))
    year, month = oldest.year, oldest.month
    # `now` is UTC too: on the 1st before 02:00 it is still last month there.
    today = stats.to_local(now)
    last = (today.year, today.month)

    out = []
    while (year, month) <= last:
        key = (year, month)
        out.append({
            'year': year,
            'month': month,
            'volume': round(volume.get(key, 0.0), 1),
            'is_gap': key not in volume,
            'deload_volume': round(deload_volume.get(key, 0.0), 1),
            'records': records.get(key, 0),
        })
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def _week_index(moment, origin):
    """Whole weeks between two moments, counted from Monday to Monday, so two
    sessions in the same calendar week always land on the same number."""
    local = stats.to_local(moment).date()
    start = stats.to_local(origin).date()
    return ((local - dt.timedelta(days=local.weekday()))
            - (start - dt.timedelta(days=start.weekday()))).days // 7


def consistency(rows, now):
    """Showing up, measured in weeks rather than in tonnage.

    The month index already says how much was lifted per month; nothing said
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


def record_timeline(rows):
    """Every record ever set, newest first -- one entry per exercise and
    workout, with the e1RM it reached and the best it beat.

    The one meaning (stats.record_marks, D3): against every EARLIER workout,
    e1RM only, deloads counted like any other workout. The same records
    Verlauf's rows and Start count, so no two surfaces disagree about a
    month (G-126), and a workout's debut is never one: there was nothing to
    beat.
    """
    by_workout = {}
    for row, mark in stats.record_marks(rows).items():
        key = (row.exercise_id, row.session_id)
        entry = by_workout.get(key)
        # The same exercise twice in one workout: its stronger showing.
        if entry is None or mark['value'] > entry['e1rm']['value']:
            by_workout[key] = {'started_at': row.started_at, 'session_id': row.session_id,
                               'exercise_id': row.exercise_id, 'name': row.name,
                               'e1rm': {'value': mark['value'], 'previous': mark['previous']}}
    timeline = list(by_workout.values())
    timeline.sort(key=lambda entry: (entry['started_at'], entry['name']), reverse=True)
    return timeline
