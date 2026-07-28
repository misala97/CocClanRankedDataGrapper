"""Tests for features.gym.analytics -- all-time aggregates. Pure functions, so
no app context, no database, no fixtures beyond plain data."""
import datetime as dt

from features.gym import analytics, stats


def perf(sets, started_at=None, session_id=1, exercise_id=1, name='Bankdruecken',
         muscle_group='Brust', is_unilateral=False, position=1, is_deload=False):
    """Build one PerformedExercise. `sets` is [(weight, reps), ...]."""
    return stats.PerformedExercise(
        exercise_id=exercise_id, name=name, muscle_group=muscle_group,
        is_unilateral=is_unilateral, position=position, session_id=session_id,
        started_at=started_at or dt.datetime(2026, 6, 1, 18, 0),
        sets=tuple(sets), is_deload=is_deload,
    )


def day(n):
    return dt.datetime(2026, 6, 1, 18, 0) + dt.timedelta(days=n)


NOW = dt.datetime(2026, 7, 1, 18, 0)


def test_totals_sums_tonnage_sets_and_reps():
    rows = [
        perf([(100.0, 10), (100.0, 8)], started_at=day(0), session_id=1),
        perf([(50.0, 5)], started_at=day(2), session_id=2),
    ]
    result = analytics.totals(rows, NOW)
    assert result['tonnage'] == 100.0 * 10 + 100.0 * 8 + 50.0 * 5
    assert result['sets'] == 3
    assert result['reps'] == 23
    assert result['sessions'] == 2


def test_totals_counts_a_unilateral_row_at_double_volume():
    # matches stats.set_volume: both sides did the work
    rows = [perf([(20.0, 10)], is_unilateral=True)]
    assert analytics.totals(rows, NOW)['tonnage'] == 400.0


def test_totals_includes_deload_sessions_because_the_work_happened():
    rows = [
        perf([(100.0, 10)], started_at=day(0), session_id=1),
        perf([(60.0, 10)], started_at=day(2), session_id=2, is_deload=True),
    ]
    result = analytics.totals(rows, NOW)
    assert result['sessions'] == 2
    assert result['tonnage'] == 1000.0 + 600.0


def test_totals_reports_the_training_span_from_the_first_session():
    rows = [perf([(100.0, 10)], started_at=day(0)), perf([(100.0, 10)], started_at=day(10), session_id=2)]
    result = analytics.totals(rows, NOW)
    assert result['first_session'] == day(0)
    assert result['days_training'] == (NOW - day(0)).days


def test_totals_names_the_biggest_session_by_tonnage_with_its_date():
    rows = [
        perf([(100.0, 10)], started_at=day(0), session_id=1),   # 1000
        perf([(100.0, 20)], started_at=day(3), session_id=2),   # 2000
    ]
    best = analytics.totals(rows, NOW)['best_session']
    assert best['session_id'] == 2
    assert best['volume'] == 2000.0
    assert best['started_at'] == day(3)


def test_totals_on_no_history_is_zeroed_not_broken():
    result = analytics.totals([], NOW)
    assert result['tonnage'] == 0
    assert result['sessions'] == 0
    assert result['first_session'] is None
    assert result['days_training'] is None
    assert result['best_session'] is None


def test_totals_treats_rows_sharing_a_session_id_as_one_session():
    """Rows are one-exercise-per-session, so a workout with several exercises
    produces several rows carrying the same session_id. Counting rows instead
    of sessions, or comparing a single row's volume instead of the session's
    summed total, both pass every other test in this file -- neither ever puts
    two rows in one session.
    """
    rows = [
        # session 1: two exercises, 600 + 600 = 1200 kg together
        perf([(60.0, 10)], session_id=1, exercise_id=1, name='Bank'),
        perf([(60.0, 10)], session_id=1, exercise_id=2, name='Rudern'),
        # session 2: one exercise, 1000 kg -- bigger than either single row
        # above, but smaller than session 1 once its rows are summed
        perf([(100.0, 10)], session_id=2, exercise_id=3, name='Kniebeuge'),
    ]
    result = analytics.totals(rows, NOW)
    assert result['sessions'] == 2, 'counted rows instead of sessions'
    assert result['best_session']['session_id'] == 1, 'compared rows instead of summed sessions'
    assert result['best_session']['volume'] == 1200.0
