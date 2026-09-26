"""The read-only history page, plus the JSON export."""

from features.gym import stats
from features.gym.schemas import HistoryPayload
from features.gym import export
from .. import analytics
import datetime as dt

from flask import (
    jsonify, redirect, render_template, request, url_for,
)
from sqlalchemy.orm import (
    joinedload, selectinload,
)
from models import (
    SessionExercise, WorkoutSession,
)
from auth import (
    login_required,
)
from features.gym.exercises import search_text, setups as exercise_setups
from features.gym.library import fold_apart
from features.gym.scope import (
    current_user_id, my_sessions,
)
from .helpers import (
    MONTH_NAMES, WEEKDAY_SHORT, InvalidInput, _page_active_session,
)
from .history import (
    done_sets, load_performed,
)
from .partner_view import partner_refs
from ._blueprint import (
    gym_bp,
)


@gym_bp.route('/gym/verlauf')
@login_required
def gym_verlauf():
    """Every finished workout, newest first, with its own total volume and
    records -- spec 6.6, one of the four real nav destinations. Since M3
    (D7-C) it also carries what Statistik said about the whole history: the
    lede, the months as an index, the biggest workout, each record."""
    now = dt.datetime.utcnow()
    # Eager-loaded for the exercise-list column: WorkoutSession.exercises and
    # SessionExercise.exercise are lazy relationships (models.py). This page
    # can list every finished session ever logged, and touching either per
    # row without this would be exactly the N+1 the bulk-loading discipline
    # below exists to avoid, just on a different relationship than
    # load_performed().
    sessions = (
        my_sessions()
        .filter(WorkoutSession.finished_at.isnot(None))
        .options(joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise),
                 joinedload(WorkoutSession.exercises).joinedload(SessionExercise.sets))
        .order_by(WorkoutSession.started_at.desc())
        .all()
    )

    # Replaced-away originals, from replaces_id (a plain, already-loaded
    # column) rather than the replaced_by backref, which would lazy-load once
    # per row. Their done sets count like any other (Q1), so they are in the
    # totals below -- and in the name list only when they have some: one
    # swapped out before its first set contributed nothing.
    replaced_away_ids = {
        se.replaces_id
        for s in sessions for se in s.exercises
        if se.replaces_id is not None
    }

    # The one bulk load this whole page runs on -- every completed set ever
    # logged, across every exercise, in a single query (see load_performed()'s
    # own docstring). Every session's volume and record count below is
    # derived from this one result set in Python; must not be recomputed per
    # session (spec 5.4, same discipline as gym_heute/gym_uebungen).
    performed = load_performed()

    volume_by_session = {}
    for row in performed:
        volume_by_session[row.session_id] = volume_by_session.get(row.session_id, 0.0) + stats.row_volume(row)

    # Against the sessions BEFORE each one (stats.record_marks, D3), so a
    # session keeps its records when a later one goes higher -- the same
    # records its own debrief names and Start counts.
    records_by_session = stats.session_records(performed)

    # The same exercises the volume beside each row was computed from. The row
    # listed every SessionExercise including ones swapped out mid-workout, so
    # a session showed 10 names next to a total built from 7 -- and opening it
    # revealed the 7.
    shown = {s.id: [se.exercise for se in s.exercises
                    if se.id not in replaced_away_ids or done_sets(se)]
             for s in sessions}
    history = [
        {
            'session': s,
            'volume': round(volume_by_session.get(s.id, 0.0), 1),
            'records': records_by_session.get(s.id, []),
            'exercises': [exercise.name for exercise in shown[s.id]],
            # The name and the date words, folded, so "31.07" or "juli"
            # works: item 5 stopped appending the date to new session names,
            # and date search was degrading to nothing as history grew. The
            # exercises' own texts come once, in exercise_search. Apart, so
            # "Push 2" is a workout's whole name and not Push on the 23rd.
            'search': fold_apart((
                s.name or 'Workout',
                '%s %s %d' % (
                    stats.to_local(s.started_at).strftime('%d.%m.%Y'),
                    MONTH_NAMES[stats.to_local(s.started_at).month - 1],
                    stats.to_local(s.started_at).year,
                ),
            )),
        }
        for s in sessions
    ]
    # What the search looks in for each exercise: the add sheet's text, so a
    # word finds a workout here that finds its exercise there (G-145) --
    # Verlauf matched the bare names, and "bench" or "Bankdrucken" found
    # nothing. Once per exercise, not once per row it is in.
    # Whom each workout was done with ("mit <Name>", D14): four queries for
    # the whole history, never one per row.
    partners = partner_refs(s.id for s in sessions)
    exercise_search = {exercise.name: search_text(exercise)
                       for exercises in shown.values() for exercise in exercises}

    # Month bands, grouped here rather than in the template: Jinja can detect a
    # change of month while looping, but it cannot count the rows in a group it
    # has not reached yet, and faking that with filters over the whole list is
    # how a template starts doing arithmetic. German month names live here for
    # the same reason -- strftime('%B') follows the server's locale, which is
    # not the UI's.
    # LOCAL month, not the stored UTC one. Every row renders its date through
    # the `|local` filter, so an unconverted key put a row dated 01.07. under a
    # heading reading "Juni" and inflated June's count -- and on 1 January it
    # misfiles by a year.
    #
    # Each band also carries its own totals, and each entry the gap that
    # precedes it. Both are sums over rows already in hand: the route computed
    # volume_by_session and records_by_session above and was throwing away
    # everything but the count, on the only page that sees the whole history.
    months = []
    previous_started = None
    for entry in history:
        started = stats.to_local(entry['session'].started_at)
        key = (started.year, started.month)
        if not months or months[-1]['key'] != key:
            months.append({
                'key': key,
                'label': '%s %d' % (MONTH_NAMES[started.month - 1], started.year),
                'slug': '%04d-%02d' % key,
                'entries': [],
                'volume': 0.0,
                'records': 0,
            })
        # history is newest-first, so `previous_started` is the session AFTER
        # this one in time; the gap belongs to the row below the break.
        entry['gap_days'] = ((previous_started - started).days
                             if previous_started is not None else None)
        previous_started = started
        months[-1]['entries'].append(entry)
        months[-1]['volume'] += entry['volume']
        months[-1]['records'] += len(entry['records'])

    for month in months:
        month['volume'] = round(month['volume'], 1)

    # What Statistik said about the whole history, now said here (M3).
    summary = _summary(sessions, volume_by_session,
                       round(sum(entry['volume'] for entry in history), 1), now)
    consistency = analytics.consistency(performed, now)
    weeks = ({key: consistency[key] for key in ('weeks_trained', 'weeks_total', 'longest_streak')}
             if consistency['statable'] else None)

    payload = HistoryPayload.model_validate({
        'months': [
            {
                'label': month['label'],
                'slug': month['slug'],
                'volume': month['volume'],
                'records': month['records'],
                'entries': [
                    {
                        'session_id': entry['session'].id,
                        'name': entry['session'].name,
                        'started_at': entry['session'].started_at,
                        'finished_at': entry['session'].finished_at,
                        'is_deload': entry['session'].is_deload,
                        'auto_finished': entry['session'].auto_finished,
                        'volume': entry['volume'],
                        'record_count': len(entry['records']),
                        'records': entry['records'],
                        'exercises': entry['exercises'],
                        'partners': partners.get(entry['session'].id, []),
                        'search': entry['search'],
                        'gap_days': entry['gap_days'],
                    }
                    for entry in month['entries']
                ],
            }
            for month in months
        ],
        'total': len(history),
        'summary': summary,
        'weeks': weeks,
        'index': _month_index(performed, [s.started_at for s in sessions], now),
        'biggest_session_id': _biggest_session(sessions, volume_by_session),
        'gap_threshold': VERLAUF_GAP_DAYS,
        'weekday_short': list(WEEKDAY_SHORT),
        'exercise_search': exercise_search,
        'running_session_id': running.id if (running := _page_active_session()) else None,
    })
    return render_template('gym/verlauf.html',
                           payload_json=payload.model_dump(mode='json'))


# A break this long or longer gets called out in the history. Below it the
# date column already tells the story; above it, a layoff was represented by
# nothing at all -- rows sit at equal spacing one day or six weeks apart, and a
# month with no sessions simply had no band.
VERLAUF_GAP_DAYS = 10


def _longest_break_days(session_dates, now):
    """The longest run of days without a workout, the one still going included.

    Only the gaps BETWEEN workouts used to count, so a lifter three weeks into
    a break was told their longest one was eight days -- the page understated
    exactly the break it was most likely being opened about.
    """
    dates = sorted(session_dates)
    if not dates:
        return 0
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    gaps.append((now - dates[-1]).days)
    return max(gaps)


def _month_index(performed, started, now):
    """Verlauf's month index (M3): every month since the first listed workout,
    oldest first, with its tonnage and records.

    A calendar, so a month without a workout still has a band -- but "without
    a workout" means none listed: a month whose only workout logged nothing
    has its row right there on the page. The running month is the lifter's,
    not UTC's: at 00:30 on the 1st it is already the new one.
    """
    listed = {(local.year, local.month) for local in map(stats.to_local, started)}
    today = stats.to_local(now)
    return [
        dict(month,
             label='%s %d' % (MONTH_NAMES[month['month'] - 1], month['year']),
             short=MONTH_NAMES[month['month'] - 1][:3],
             slug='%04d-%02d' % (month['year'], month['month']),
             is_gap=(month['year'], month['month']) not in listed,
             is_current=(month['year'], month['month']) == (today.year, today.month))
        for month in analytics.monthly_tonnage(performed, now, first=min(started, default=None))
    ]


def _summary(sessions, volume_by_session, tonnage, now):
    """Verlauf's lede (M3): how many workouts, since when, how much, and the
    longest break -- the one still running included, or a lifter three weeks
    into a break is told about an eight-day one.

    Over the workouts that count: `volume_by_session` holds every one with a
    set that counts (Q1), at 0 kg too. One opened and left empty stays listed,
    but its debrief said "dieses Workout zählt nicht mit" -- so it is not
    counted, does not date the history and does not split a break. Days run
    between LOCAL times, as the pause lines between the rows measure them:
    in UTC the two disagreed by one across a clock change."""
    counted = [s for s in sessions if s.id in volume_by_session]
    if not counted:
        return None
    return {
        'workouts': len(counted),
        'first_at': counted[-1].started_at,
        'tonnage': tonnage,
        'longest_gap': _longest_break_days([stats.to_local(s.started_at) for s in counted],
                                           stats.to_local(now)),
    }


def _biggest_session(sessions, volume_by_session):
    """The workout that moved the most, marked on its row -- none under two
    workouts that count (`volume_by_session` holds those, as in _summary),
    where the only one is trivially the biggest. `sessions` runs newest
    first; the scan runs oldest first, so a tie stays with the workout that
    lifted it first."""
    if sum(1 for s in sessions if s.id in volume_by_session) < 2:
        return None
    biggest_id, biggest = None, 0.0
    for s in reversed(sessions):
        if volume_by_session.get(s.id, 0.0) > biggest:
            biggest_id, biggest = s.id, volume_by_session[s.id]
    return biggest_id


@gym_bp.route('/gym/statistik')
@login_required
def gym_statistik():
    """Statistik is gone (M3, D7-C): Start says what moves and what stands
    still, Verlauf what the whole history holds. A bookmark or an installed
    shortcut lands on Verlauf rather than on a 404."""
    return redirect(url_for('gym.gym_verlauf'), code=301)


# More workouts than anyone exports at once, and fewer than a URL can carry.
MAX_EXPORT_IDS = 1000


def _export_ids(raw):
    """The ids in `?ids=`, in order, each once.

    An id is one to ten ASCII digits -- a database id, not whatever int()
    happens to take: '²' passed isdigit() and then failed int(), and a
    5000-digit id went past Python's limit for parsing one; both answered 500
    (G-135). Anything else in the list is skipped, as a stray comma always was.
    """
    ids, seen = [], set()
    for part in raw.split(','):
        part = part.strip()
        if not (part.isascii() and part.isdigit() and len(part) <= 10):
            continue
        value = int(part)
        if value not in seen:
            seen.add(value)
            ids.append(value)
    if len(ids) > MAX_EXPORT_IDS:
        raise InvalidInput(
            f'Zu viele Workouts auf einmal — höchstens {MAX_EXPORT_IDS} pro Export.')
    return ids


@gym_bp.route('/gym/export')
@login_required
def gym_export():
    """Downloadable JSON of specific finished workouts, picked by id from
    Verlauf's own checklist (the 30/90-day presets there just bulk-check
    matching rows client-side -- this route only ever sees the final id
    list, never a date range). Full detail (every set, not just aggregates)
    so nothing useful is thrown away up front. Both original and substitute
    SessionExercise rows are exported (mirroring what a finished session's
    own detail view already shows -- see session_detail's visible_exercises
    computation), each carrying replaces/replaced_by exercise names so a
    swap is fully traceable. The payload shape is schema v2 and lives in
    features/gym/export.py."""
    session_ids = _export_ids(request.args.get('ids', ''))

    # Everything export.py reads, loaded up front: lazily it was a query per
    # row for its exercise, its sets, its substitute and what it replaced --
    # about 15 per workout, 677 for 44 of them (walkthrough G-095).
    rows = selectinload(WorkoutSession.exercises)
    sessions = (
        my_sessions()
        .filter(
            WorkoutSession.finished_at.isnot(None),
            WorkoutSession.id.in_(session_ids),
        )
        .options(joinedload(WorkoutSession.template),
                 rows.joinedload(SessionExercise.exercise),
                 rows.selectinload(SessionExercise.sets),
                 rows.selectinload(SessionExercise.replaces),
                 rows.selectinload(SessionExercise.replaced_by))
        .order_by(WorkoutSession.started_at.asc())
        .all()
    ) if session_ids else []

    setups = exercise_setups(current_user_id(),
                             {se.exercise for s in sessions for se in s.exercises})
    payload = export.build_payload(sessions, session_ids, dt.datetime.utcnow(), setups)

    resp = jsonify(payload)
    filename = f"gym-export-{len(sessions)}-workouts.json"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp
