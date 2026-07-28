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


def test_progression_ranking_reports_first_to_current_change():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
    ]
    entry = analytics.progression_ranking(rows)[0]
    assert entry['sessions'] == 2
    assert entry['first_e1rm'] == round(stats.epley_1rm(100.0, 8), 1)
    assert entry['current_e1rm'] == round(stats.epley_1rm(110.0, 8), 1)
    assert entry['change_pct'] == 10.0
    assert entry['best_weight'] == 110.0
    assert len(entry['points']) == 2


def test_progression_ranking_sorts_biggest_gain_first():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1, exercise_id=1, name='Klein'),
        perf([(105.0, 8)], started_at=day(7), session_id=2, exercise_id=1, name='Klein'),
        perf([(50.0, 8)], started_at=day(0), session_id=1, exercise_id=2, name='Gross'),
        perf([(75.0, 8)], started_at=day(7), session_id=2, exercise_id=2, name='Gross'),
    ]
    assert [e['name'] for e in analytics.progression_ranking(rows)] == ['Gross', 'Klein']


def test_progression_ranking_excludes_deload_sessions():
    # a 200 kg deload must not become the "current" figure
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
        perf([(200.0, 8)], started_at=day(14), session_id=3, is_deload=True),
    ]
    entry = analytics.progression_ranking(rows)[0]
    assert entry['sessions'] == 2
    assert entry['current_e1rm'] == round(stats.epley_1rm(110.0, 8), 1)


def test_progression_ranking_skips_an_exercise_with_one_session():
    rows = [perf([(100.0, 8)], started_at=day(0), session_id=1)]
    assert analytics.progression_ranking(rows) == []


def test_progression_ranking_skips_an_exercise_whose_history_is_all_deloads():
    rows = [
        perf([(60.0, 8)], started_at=day(0), session_id=1, is_deload=True),
        perf([(60.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert analytics.progression_ranking(rows) == []


def test_progression_ranking_on_no_history_is_empty():
    assert analytics.progression_ranking([]) == []


def test_progression_ranking_treats_one_exercise_twice_in_a_session_as_one_point():
    """An exercise performed in two slots of the same workout is one data
    point on its curve -- its best showing that day -- not two sessions.
    Every other test here has at most one row per exercise per session, so an
    implementation that counted both would pass all of them.
    """
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1, position=1),
        # same workout, second slot, heavier
        perf([(105.0, 8)], started_at=day(0), session_id=1, position=4),
        perf([(110.0, 8)], started_at=day(7), session_id=2, position=1),
    ]
    entry = analytics.progression_ranking(rows)[0]
    assert entry['sessions'] == 2, 'counted two slots as two sessions'
    assert len(entry['points']) == 2, 'plotted two slots as two points'
    # the first session contributes its BEST showing, 105 not 100
    assert entry['first_e1rm'] == round(stats.epley_1rm(105.0, 8), 1)


def test_progression_ranking_reports_the_latest_session_not_the_best_one():
    """Current means most recent, not peak. With a dip at the end, an
    implementation using min()/max() instead of first-and-last-by-date would
    report 120 as current -- every other test here rises monotonically, where
    the two readings coincide and nothing would catch the difference.
    """
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(120.0, 8)], started_at=day(7), session_id=2),
        perf([(110.0, 8)], started_at=day(14), session_id=3),
    ]
    entry = analytics.progression_ranking(rows)[0]
    assert entry['first_e1rm'] == round(stats.epley_1rm(100.0, 8), 1)
    assert entry['current_e1rm'] == round(stats.epley_1rm(110.0, 8), 1)
    assert entry['points'][-1] == round(stats.epley_1rm(110.0, 8), 1)


def test_progression_ranking_skips_an_exercise_that_started_at_bodyweight():
    """A bodyweight first session gives an e1RM of 0, and a percentage change
    from zero is not a number. The exercise is omitted rather than crashing
    the ranking it sits in.
    """
    rows = [
        perf([(0.0, 10)], started_at=day(0), session_id=1),
        perf([(20.0, 10)], started_at=day(7), session_id=2),
    ]
    assert analytics.progression_ranking(rows) == []


def test_rep_range_distribution_buckets_every_set():
    rows = [perf([(100.0, 3), (100.0, 7), (100.0, 10), (100.0, 15)])]
    result = analytics.rep_range_distribution(rows)
    counts = {b['label']: b['sets'] for b in result['buckets']}
    assert counts == {'1-5': 1, '6-8': 1, '9-12': 1, '13+': 1}
    assert result['sample'] == 4


def test_rep_range_distribution_reports_the_dominant_bucket_share():
    rows = [perf([(100.0, 7)] * 3 + [(100.0, 10)])]
    result = analytics.rep_range_distribution(rows)
    assert result['dominant']['label'] == '6-8'
    assert result['dominant']['share'] == 75.0


def test_rep_range_distribution_is_not_statable_below_the_threshold():
    rows = [perf([(100.0, 8)] * (analytics.MIN_SETS_FOR_REP_RANGE - 1))]
    assert analytics.rep_range_distribution(rows)['statable'] is False


def test_rep_range_distribution_is_statable_at_the_threshold():
    rows = [perf([(100.0, 8)] * analytics.MIN_SETS_FOR_REP_RANGE)]
    assert analytics.rep_range_distribution(rows)['statable'] is True


def test_rep_range_distribution_includes_deloads_because_it_describes():
    rows = [perf([(60.0, 8)] * analytics.MIN_SETS_FOR_REP_RANGE, is_deload=True)]
    assert analytics.rep_range_distribution(rows)['sample'] == analytics.MIN_SETS_FOR_REP_RANGE


def test_rep_range_distribution_on_no_history_is_empty_not_broken():
    result = analytics.rep_range_distribution([])
    assert result['sample'] == 0
    assert result['statable'] is False
    assert result['dominant'] is None


def test_fatigue_curve_averages_first_versus_last_set():
    rows = [perf([(100.0, 10), (90.0, 8)])]        # -10 % weight, 10 -> 8 reps
    result = analytics.fatigue_curve(rows)
    assert result['weight_change_pct'] == -10.0
    assert result['first_reps'] == 10.0
    assert result['last_reps'] == 8.0
    assert result['sample'] == 1


def test_fatigue_curve_ignores_rows_with_a_single_set():
    rows = [perf([(100.0, 10)]), perf([(100.0, 10), (90.0, 8)], session_id=2)]
    assert analytics.fatigue_curve(rows)['sample'] == 1


def test_fatigue_curve_is_not_statable_below_the_threshold():
    rows = [perf([(100.0, 10), (90.0, 8)], session_id=i)
            for i in range(analytics.MIN_ROWS_FOR_FATIGUE - 1)]
    assert analytics.fatigue_curve(rows)['statable'] is False


def test_fatigue_curve_on_no_history_is_empty_not_broken():
    result = analytics.fatigue_curve([])
    assert result['sample'] == 0
    assert result['statable'] is False
    assert result['weight_change_pct'] is None


def test_rep_range_distribution_excludes_a_zero_rep_set_and_says_so():
    """A failed attempt logged at 0 reps is not a rep range. It is excluded
    deliberately and reported, rather than silently shrinking the sample."""
    rows = [perf([(100.0, 8), (100.0, 0)])]
    result = analytics.rep_range_distribution(rows)
    assert result['sample'] == 1
    assert result['skipped'] == 1


def test_rep_range_distribution_boundaries_are_inclusive_as_labelled():
    """Every label names an inclusive range, so each edge value belongs to the
    bucket it is named in. Interior values alone cannot catch an off-by-one."""
    rows = [perf([(100.0, 1), (100.0, 5), (100.0, 6), (100.0, 8),
                  (100.0, 9), (100.0, 12), (100.0, 13)])]
    counts = {b['label']: b['sets'] for b in analytics.rep_range_distribution(rows)['buckets']}
    assert counts == {'1-5': 2, '6-8': 2, '9-12': 2, '13+': 1}


def test_fatigue_curve_is_statable_at_the_threshold():
    """Pins >= rather than >. The below-threshold test alone would still pass
    if the comparison were weakened."""
    rows = [perf([(100.0, 10), (90.0, 8)], session_id=i)
            for i in range(analytics.MIN_ROWS_FOR_FATIGUE)]
    assert analytics.fatigue_curve(rows)['statable'] is True


def test_fatigue_curve_survives_a_bodyweight_row():
    """Weight 0 is legitimate here (see stats.deload_weight's own bodyweight
    branch). The percentage is undefined for such a row, so it contributes
    only its reps -- and must not divide by zero doing so."""
    rows = [perf([(0.0, 12), (0.0, 9)])]
    result = analytics.fatigue_curve(rows)
    assert result['sample'] == 1
    assert result['first_reps'] == 12.0
    assert result['last_reps'] == 9.0
    assert result['weight_change_pct'] is None


def test_fatigue_curve_averages_across_rows_rather_than_reporting_one():
    """Two rows with different drop-offs: the result must be their mean, not
    either row's own numbers."""
    rows = [
        perf([(100.0, 10), (90.0, 8)], session_id=1),    # -10 %, 10 -> 8
        perf([(100.0, 12), (80.0, 6)], session_id=2),    # -20 %, 12 -> 6
    ]
    result = analytics.fatigue_curve(rows)
    assert result['sample'] == 2
    assert result['weight_change_pct'] == -15.0
    assert result['first_reps'] == 11.0
    assert result['last_reps'] == 7.0
