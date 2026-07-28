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
