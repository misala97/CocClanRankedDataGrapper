"""Statistik's answers where the lifter reads them (M3, D7-C).

Verlauf says what the whole history holds -- the lede, the months as an
index, the biggest workout, each record -- and Start what goes up and what
stands still. The helpers are pure; the routes run as a throwaway lifter
(tests/gym_lifter.py), so the admin's real history in the local dev database
moves no figure.
"""
import datetime as dt
from types import SimpleNamespace

from app import app as flask_app
from conftest import embedded_payload
from extensions import db
from features.gym import stats
from features.gym.routes.reports import _biggest_session, _month_index, _summary
from gym_lifter import lifter  # noqa: F401 -- the fixture

DAY = dt.timedelta(days=1)


def _session(id):
    return SimpleNamespace(id=id)


def test_the_biggest_workout_is_the_one_that_moved_the_most():
    newest_first = [_session(3), _session(2), _session(1)]
    assert _biggest_session(newest_first, {1: 900.0, 2: 1500.0, 3: 1200.0}) == 2


def test_a_tie_stays_with_the_workout_that_lifted_it_first():
    newest_first = [_session(3), _session(2), _session(1)]
    assert _biggest_session(newest_first, {1: 1500.0, 2: 900.0, 3: 1500.0}) == 1


def test_one_workout_is_not_called_the_biggest():
    assert _biggest_session([_session(1)], {1: 1500.0}) is None


def test_workouts_that_logged_nothing_have_no_biggest():
    assert _biggest_session([_session(2), _session(1)], {}) is None


def test_a_workout_left_empty_does_not_make_the_other_the_biggest():
    # Workout 2 was opened and left empty: listed, but it "zählt nicht mit".
    assert _biggest_session([_session(2), _session(1)], {1: 1500.0}) is None


def _started(id, at):
    return SimpleNamespace(id=id, started_at=at)


def test_the_lede_counts_dates_and_measures_breaks_by_the_workouts_that_count():
    # Newest first; 3 and 1 were opened and left empty.
    sessions = [_started(4, dt.datetime(2026, 9, 20, 16)), _started(3, dt.datetime(2026, 9, 1, 16)),
                _started(2, dt.datetime(2026, 8, 20, 16)), _started(1, dt.datetime(2026, 8, 1, 16))]
    summary = _summary(sessions, {4: 500.0, 2: 800.0}, 1300.0, dt.datetime(2026, 9, 25, 12))
    # Not 4 workouts since 01.08. with a longest break of 19 days.
    assert summary == {'workouts': 2, 'first_at': dt.datetime(2026, 8, 20, 16),
                       'tonnage': 1300.0, 'longest_gap': 31}


def test_the_longest_break_is_measured_as_the_pause_lines_measure_it():
    # Sat 24.10. 10:00 CEST to Sat 31.10. 09:30 CET: the pause line between
    # the two rows, on local times, says 6 days; in UTC it was 7.
    sessions = [_started(2, dt.datetime(2026, 10, 31, 8, 30)), _started(1, dt.datetime(2026, 10, 24, 8))]
    summary = _summary(sessions, {1: 100.0, 2: 100.0}, 200.0, dt.datetime(2026, 10, 31, 9))
    assert summary['longest_gap'] == 6


def test_a_history_of_empty_workouts_has_no_lede():
    assert _summary([_started(1, dt.datetime(2026, 9, 1, 16))], {}, 0.0,
                    dt.datetime(2026, 9, 25, 12)) is None


def _row(weight, started_at, session_id, is_deload=False):
    return stats.PerformedExercise(
        exercise_id=1, name='Bankdruecken', muscle_group='Brust', is_unilateral=False,
        position=1, session_id=session_id, started_at=started_at, sets=((weight, 5),),
        is_deload=is_deload, weight_increment=None, stack_kg=None)


def test_the_index_is_a_calendar_of_the_listed_workouts():
    june, august = dt.datetime(2026, 6, 10, 16), dt.datetime(2026, 8, 20, 16)
    # September's only workout logged nothing: listed, so no gap in the index.
    september = dt.datetime(2026, 9, 2, 16)
    rows = [_row(100.0, june, 1), _row(105.0, august, 2, is_deload=True)]
    index = _month_index(rows, [september, august, june], dt.datetime(2026, 9, 25, 12))
    assert [(m['slug'], m['label'], m['short'], m['is_gap'], m['is_current']) for m in index] == [
        ('2026-06', 'Juni 2026', 'Jun', False, False),
        ('2026-07', 'Juli 2026', 'Jul', True, False),
        ('2026-08', 'August 2026', 'Aug', False, False),
        ('2026-09', 'September 2026', 'Sep', False, True),
    ]
    assert [(m['volume'], m['deload_volume'], m['records']) for m in index] == [
        (500.0, 0, 0), (0, 0, 0), (525.0, 525.0, 1), (0, 0, 0)]


def test_an_empty_history_has_no_index():
    assert _month_index([], [], dt.datetime(2026, 9, 25, 12)) == []


# ---- the routes, as a throwaway lifter --------------------------------------

def _done(lifter, days_ago, lifts):
    """A finished workout `days_ago` days back: `lifts` is [(exercise,
    [(weight, reps), ...])]; an empty list leaves its one set open, so the
    workout logs nothing."""
    workout = lifter.workout(days_ago * DAY, finished=True)
    for position, (exercise, sets) in enumerate(lifts, start=1):
        lifter.row(workout, exercise, position, done=sets, open_=0 if sets else 1)
    return workout


def _month(at):
    return stats.to_local(at).strftime('%Y-%m')


def test_verlauf_says_what_the_whole_history_holds(lifter):
    with flask_app.app_context():
        bank = lifter.exercise('verlauf bank')
        first = _done(lifter, 40, [(bank, [(100.0, 5)])])
        record = _done(lifter, 20, [(bank, [(105.0, 5), (90.0, 5)])])
        empty = _done(lifter, 5, [(bank, [])])
        db.session.commit()
        bank_id, first_id, first_at = bank.id, first.id, first.started_at
        record_id, empty_id, empty_at = record.id, empty.id, empty.started_at

    payload = embedded_payload(lifter.client().get('/gym/verlauf').get_data(as_text=True))

    summary = payload['summary']
    # The empty workout is listed, but "zählt nicht mit".
    assert (summary['workouts'], summary['tonnage'], summary['longest_gap']) == (2, 1475.0, 20)
    assert dt.datetime.fromisoformat(summary['first_at']) == first_at
    assert payload['weeks'] is not None and payload['weeks']['weeks_trained'] == 2
    assert set(payload['weeks']) == {'weeks_trained', 'weeks_total', 'longest_streak'}

    entries = {e['session_id']: e for month in payload['months'] for e in month['entries']}
    assert entries[record_id]['records'] == [{
        'exercise_id': bank_id, 'name': 'pytest gym verlauf bank', 'weight': 105.0, 'reps': 5,
        'e1rm': 122.5, 'previous': 116.7,
    }]
    assert entries[record_id]['record_count'] == 1
    assert entries[first_id]['records'] == [] and entries[empty_id]['records'] == []
    assert payload['biggest_session_id'] == record_id

    index = payload['index']
    assert index[0]['slug'] == _month(first_at)
    assert index[-1]['slug'] == _month(dt.datetime.utcnow()) and index[-1]['is_current']
    assert not any(month['is_current'] for month in index[:-1])
    assert next(m for m in index if m['slug'] == _month(empty_at))['is_gap'] is False


def test_a_first_workout_is_no_biggest_and_says_no_weeks_yet(lifter):
    with flask_app.app_context():
        bank = lifter.exercise('verlauf bank')
        _done(lifter, 2, [(bank, [(100.0, 5)])])
        # Opened and left empty: listed, but no second workout.
        _done(lifter, 1, [(bank, [])])
        db.session.commit()
    payload = embedded_payload(lifter.client().get('/gym/verlauf').get_data(as_text=True))
    assert payload['total'] == 2
    assert payload['summary']['workouts'] == 1
    assert payload['biggest_session_id'] is None
    assert payload['weeks'] is None
    assert payload['index'][-1]['is_current'] is True


def test_an_empty_history_says_nothing_of_itself(lifter):
    payload = embedded_payload(lifter.client().get('/gym/verlauf').get_data(as_text=True))
    assert (payload['summary'], payload['weeks'], payload['index'], payload['biggest_session_id']) \
        == (None, None, [], None)


def test_start_says_what_goes_up_and_leaves_a_stalled_lift_to_steht_still(lifter):
    with flask_app.app_context():
        bank = lifter.exercise('verlauf bank')
        squat = lifter.exercise('verlauf kniebeuge')
        # Bankdrücken: a record a week, four weeks running -- it goes up.
        for i, weight in enumerate((80.0, 82.5, 85.0, 87.5)):
            _done(lifter, 22 - 7 * i, [(bank, [(weight, 5)])])
        # Kniebeuge: a heavy first day, then six lighter weeks climbing. The
        # line rises, but nothing has beaten the first day: it stands still.
        _done(lifter, 43, [(squat, [(120.0, 5)])])
        for i, weight in enumerate((100.0, 101.0, 102.0, 103.0, 104.0, 105.0)):
            _done(lifter, 36 - 7 * i, [(squat, [(weight, 5)])])
        db.session.commit()
        bank_id, squat_id = bank.id, squat.id

    payload = embedded_payload(lifter.client().get('/gym').get_data(as_text=True))

    assert 'recent_sessions' not in payload
    progress = payload['progress']
    assert [lift['exercise_id'] for lift in progress['up']] == [bank_id]
    # Both lifts have a pace; only the one not standing still goes up.
    assert (progress['with_trend'], progress['min_workouts'], progress['min_days']) == (2, 4, 14)
    [lift] = progress['up']
    assert len(lift['points']) == 4 and lift['per_month'] > 0
    assert lift['best']['e1rm'] == 102.1 and lift['best']['is_record'] is True
    [stall] = [entry for entry in payload['stalls'] if entry['exercise_id'] == squat_id]
    assert stall['last_record_at'] is None
    assert stall['sessions_since_pr'] == 6
