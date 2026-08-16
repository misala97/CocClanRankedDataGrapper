"""Read-only history and statistics pages, plus the JSON export."""

from features.gym import stats
from features.gym.schemas import HistoryPayload, StatistikPayload
from features.gym import export
from .. import analytics
import datetime as dt

from flask import (
    jsonify, render_template, request,
)
from sqlalchemy.orm import (
    joinedload,
)
from models import (
    SessionExercise, WorkoutSession,
)
from auth import (
    login_required,
)
from features.gym.scope import (
    my_sessions,
)
from .helpers import (
    DAYPART_NAMES, MONTH_NAMES, WEEKDAY_NAMES, WEEKDAY_SHORT,
)
from .history import (
    _session_rest_entries, load_performed,
)
from ._blueprint import (
    gym_bp,
)


@gym_bp.route('/gym/verlauf')
@login_required
def gym_verlauf():
    """Every finished workout, newest first, with its own total volume and
    record count -- spec 6.6, one of the four real nav destinations."""
    # Eager-loaded for the exercise-list column: WorkoutSession.exercises and
    # SessionExercise.exercise are lazy relationships (models.py). This page
    # can list every finished session ever logged, and touching either per
    # row without this would be exactly the N+1 the bulk-loading discipline
    # below exists to avoid, just on a different relationship than
    # load_performed().
    sessions = (
        my_sessions()
        .filter(WorkoutSession.finished_at.isnot(None))
        .options(joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise))
        .order_by(WorkoutSession.started_at.desc())
        .all()
    )

    # Replaced-away originals must not contribute to their own session's
    # volume/record totals below -- the same exclusion performed_from_session()
    # already applies for session_report()/the detail page: the substitute
    # took over that slot, and counting both would inflate the session's
    # totals with an exercise the historical comparison was never scoped to.
    # `sessions` above already eager-loads every finished session's
    # .exercises (for the exercise-list column) -- reused here for zero extra
    # queries, reading replaces_id (a plain, already-loaded column) rather
    # than the replaced_by backref, which would lazy-load once per row (see
    # session_detail's identical replaced_original_ids, same reasoning).
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
    performed = load_performed(exclude_session_exercise_ids=replaced_away_ids)

    volume_by_session = {}
    for row in performed:
        volume_by_session[row.session_id] = volume_by_session.get(row.session_id, 0.0) + stats.row_volume(row)

    # Same "beats every OTHER session, regardless of when it happened"
    # semantics stats.session_report's own is_weight_pr/is_e1rm_pr/
    # is_volume_pr use -- computed for every session in this one pass so a
    # session's count here always agrees with what its own detail page
    # (session_report) shows, instead of the strictly weaker "beats only the
    # sessions before it" a chronological-only comparison would give.
    records_by_session = stats.session_record_counts(performed)

    history = [
        {
            'session': s,
            'volume': round(volume_by_session.get(s.id, 0.0), 1),
            'record_count': records_by_session.get(s.id, 0),
            # The same exercises the volume beside it was computed from. The
            # row listed every SessionExercise including ones swapped out
            # mid-workout, so a session showed 10 names next to a total built
            # from 7 -- and opening it revealed the 7.
            'exercises': [se.exercise.name for se in s.exercises
                          if se.id not in replaced_away_ids],
            # Searchable date text, so a query like "31.07" or "juli" works.
            # data-search carried only the name and the exercises, and item 5
            # stopped appending the date to new session names -- so date search
            # was degrading to nothing as history accumulated.
            'search_date': '%s %s %d' % (
                stats.to_local(s.started_at).strftime('%d.%m.%Y'),
                MONTH_NAMES[stats.to_local(s.started_at).month - 1],
                stats.to_local(s.started_at).year,
            ),
        }
        for s in sessions
    ]

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
        months[-1]['records'] += entry['record_count']

    for month in months:
        month['volume'] = round(month['volume'], 1)

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
                        'volume': entry['volume'],
                        'record_count': entry['record_count'],
                        'exercises': entry['exercises'],
                        'search_date': entry['search_date'],
                        'gap_days': entry['gap_days'],
                    }
                    for entry in month['entries']
                ],
            }
            for month in months
        ],
        'total': len(history),
        'gap_threshold': VERLAUF_GAP_DAYS,
        'weekday_short': list(WEEKDAY_SHORT),
    })
    return render_template('gym/verlauf.html',
                           payload_json=payload.model_dump(mode='json'))


# A break this long or longer gets called out in the history. Below it the
# date column already tells the story; above it, a layoff was represented by
# nothing at all -- rows sit at equal spacing one day or six weeks apart, and a
# month with no sessions simply had no band.
VERLAUF_GAP_DAYS = 10


SPARK_W = 74.0
SPARK_H = 24.0


# The windows the Fortschritt section offers. Plain day counts rather than
# calendar months: a month here is a rough span, and no consumer needs it to
# land on the same day of the month. None is all time.
#
# All four are precomputed rather than served per request: the client switches
# between them with no round trip, and every figure still comes from one Python
# function instead of a second implementation of "progress" in TypeScript.
PROGRESSION_WINDOWS = (('all', None), ('6m', 182), ('3m', 91), ('30d', 30))


def _progression_view(ranking):
    """Progression rows with their sparkline drawn and their bar sized.

    Geometry in Python for the same reason the exercise chart's is: Jinja doing
    coordinate arithmetic is unreadable, and an inline SVG inherits the palette
    where a canvas cannot.

    The bar is diverging from a centre line, so gains and losses read as
    directions rather than as two lists. It is scaled against the largest
    absolute change on the page -- against a fixed 100 % a typical +40 % lift
    would draw as a stub, and the ranking would look flat when it is not.

    Every ranked exercise is returned. There used to be a top-eight cap with
    an exception that kept every loser below it -- the exception existed only
    so truncation could not turn the section into a highlight reel, and with
    nothing truncated it has nothing left to protect. The cap also made the
    section grow only when things went wrong: bounded upward, unbounded down.

    `widest` is per call, so each window scales against its own biggest move
    rather than against the all-time one, which would draw a narrow window as
    a row of stubs.
    """
    if not ranking:
        return []
    shown = list(ranking)

    widest = max((abs(entry['change_pct']) for entry in shown), default=1.0) or 1.0
    out = []
    for entry in shown:
        points = entry['points']
        lo, hi = min(points), max(points)
        span = (hi - lo) or 1.0
        step = SPARK_W / max(len(points) - 1, 1)
        spark = ' '.join(
            '%.1f,%.1f' % (index * step, SPARK_H - 2 - (value - lo) / span * (SPARK_H - 4))
            for index, value in enumerate(points)
        )
        out.append(dict(
            entry,
            spark=spark,
            bar_pct=round(abs(entry['change_pct']) / widest * 50.0, 2),
            is_up=entry['change_pct'] >= 0,
        ))
    return out


@gym_bp.route('/gym/statistik')
@login_required
def gym_statistik():
    """All-time analytics (spec 2026-07-29). Desktop-only in the navigation,
    but the URL stays reachable: opening it on a phone renders the page
    single-column rather than redirecting, because hiding data the user asked
    for is worse than showing it in a cramped layout.

    Thin by construction. The one bulk load below feeds every figure on the
    page -- same discipline as Heute/Uebungen/Verlauf (spec 5.4): never one
    query per exercise, no matter how long the history gets. All analysis
    lives in analytics.py.

    Unlike gym_verlauf, this does NOT exclude a replaced-away original's sets.
    That is deliberate. Verlauf reports a session's volume as the sum of the
    slots it ran, so an abandoned original would double-count a slot the
    substitute already represents. Statistik describes what was lifted, and a
    set you performed before swapping the exercise out was still performed --
    the same reason deload sessions count toward tonnage here. The consequence
    is that "Groesstes Workout" can exceed the figure Verlauf shows for that
    same session; if that ever needs to change, change it here, not by
    quietly filtering one of them.
    """
    now = dt.datetime.utcnow()
    performed = load_performed()

    # The lede: one sentence built from the numbers, so the page answers before
    # it reports. The longest break is the only figure here not already in
    # analytics -- it is cheap from the session dates this page has loaded
    # anyway, and it is the fact that makes the sentence worth reading.
    session_dates = sorted({row.started_at for row in performed})
    longest_gap = max(
        ((b - a).days for a, b in zip(session_dates, session_dates[1:])),
        default=0,
    )

    # Records: the most recent RECENT_RECORDS shown flat, everything older
    # folded into year bands.
    #
    # Bounding by CALENDAR was the bug. Grouping by year and opening the first
    # band assumes a history that spans years -- and for every new account, and
    # for this one today, it does not: one band, forced open, every record in
    # it. Measured at 57 records that was 3,648px of a 5,249px page, i.e. worse
    # than the two-thirds the brief set out to fix. It also flipped overnight:
    # on 2 January the largest section on the page would collapse to one row.
    #
    # Bounding by COUNT is stable in both directions. The fold is still lossless
    # -- nothing is dropped, and the header still counts every record there is.
    RECENT_RECORDS = 12
    records = analytics.record_timeline(performed)
    recent_records = records[:RECENT_RECORDS]
    record_years = []
    for record in records[RECENT_RECORDS:]:
        year = record['started_at'].year
        if not record_years or record_years[-1]['year'] != year:
            record_years.append({'year': year, 'records': []})
        record_years[-1]['records'].append(record)

    # Gaps are built PER SESSION and then concatenated, never across the whole
    # history at once: rest_gaps() measures consecutive pairs, and two different
    # workouts are not consecutive -- the interval from Monday's last set to
    # Wednesday's first is not a rest, it is a rest day. The cap would drop it
    # anyway, but only by accident, and an accident is not a rule.
    #
    # Pooled rather than averaged per session, because the question is what a
    # typical rest of yours looks like: a twenty-set session carries more
    # evidence about that than a six-set one.
    # Eager-loaded for the same reason session_detail's finished branch is
    # (see the comment there): this walks se.sets and se.exercise per row,
    # lazily, for every finished session in the whole history -- 1 + S query
    # became 1 + S + 2*S*E, thousands of queries at real-world scale.
    habit_gaps = []
    for session_ in (
        my_sessions()
        .filter(WorkoutSession.finished_at.isnot(None))
        .options(
            joinedload(WorkoutSession.exercises).joinedload(SessionExercise.sets),
            joinedload(WorkoutSession.exercises).joinedload(SessionExercise.exercise),
        )
    ):
        habit_gaps.extend(stats.rest_gaps(_session_rest_entries(session_)))
    rest_habit = stats.rest_medians(habit_gaps)

    payload = StatistikPayload(
        months=analytics.monthly_tonnage(performed, now),
        longest_gap=longest_gap,
        # Only the count is read -- the rows themselves reach the page as
        # recent_records plus the year bands, and shipping all three would
        # send every record twice.
        records_total=len(records),
        recent_records=recent_records,
        record_years=record_years,
        month_names=list(MONTH_NAMES),
        daypart_names=dict(DAYPART_NAMES),
        weekday_names=list(WEEKDAY_NAMES),
        totals=analytics.totals(performed, now),
        progression=[
            {'key': key,
             'entries': _progression_view(analytics.progression_ranking(
                 performed,
                 since=None if days is None else now - dt.timedelta(days=days)))}
            for key, days in PROGRESSION_WINDOWS
        ],
        rep_range=analytics.rep_range_distribution(performed),
        fatigue=analytics.fatigue_curve(performed),
        daypart=analytics.daypart_volume(performed),
        weekday=analytics.weekday_distribution(performed),
        rest_gap=analytics.rest_gap_effect(performed),
        session_length=analytics.session_length(performed),
        consistency=analytics.consistency(performed, now),
        balance_drift=analytics.balance_drift(performed, now),
        increment_ladder=analytics.increment_ladder(performed),
        record_drought=analytics.record_drought(performed),
        min_sets_for_rep_range=analytics.MIN_SETS_FOR_REP_RANGE,
        effort=analytics.effort_distribution(performed),
        rest_habit=rest_habit,
    )
    return render_template('gym/statistik.html',
                           payload_json=payload.model_dump(mode='json'))


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
    ids_param = request.args.get('ids', '')
    session_ids = []
    for raw_id in ids_param.split(','):
        raw_id = raw_id.strip()
        if raw_id.isdigit():
            session_ids.append(int(raw_id))

    sessions = (
        my_sessions()
        .filter(
            WorkoutSession.finished_at.isnot(None),
            WorkoutSession.id.in_(session_ids),
        )
        .order_by(WorkoutSession.started_at.asc())
        .all()
    ) if session_ids else []

    payload = export.build_payload(sessions, session_ids, dt.datetime.utcnow())

    resp = jsonify(payload)
    filename = f"gym-export-{len(sessions)}-workouts.json"
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp
