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


def at(hour, days=0, session_id=1, weight=100.0, reps=10):
    """`hour` is the STORED hour, i.e. UTC. June is CEST, so local = UTC + 2.
    The bucketing under test is local, so a test that means "08:00 in the
    morning" passes 6 here."""
    return perf([(weight, reps)], session_id=session_id,
                started_at=dt.datetime(2026, 6, 1, hour, 0) + dt.timedelta(days=days))


def test_daypart_volume_separates_morning_from_evening():
    rows = [at(9, days=0, session_id=1), at(20, days=1, session_id=2)]
    parts = {p['label']: p for p in analytics.daypart_volume(rows)['parts']}
    assert parts['morning']['sessions'] == 1
    assert parts['evening']['sessions'] == 1


def test_daypart_volume_reports_volume_per_session_not_total():
    rows = [at(9, days=0, session_id=1, reps=10), at(9, days=1, session_id=2, reps=30)]
    parts = {p['label']: p for p in analytics.daypart_volume(rows)['parts']}
    # 1000 + 3000 across two sessions -> 2000 average
    assert parts['morning']['avg_volume'] == 2000.0


def test_daypart_volume_averages_over_sessions_not_rows():
    """A workout is several rows sharing one session_id, so averaging rows
    would quietly weight long sessions higher. Every other daypart test gives
    each session a single row, where the two readings coincide and nothing
    would catch the difference.

    Session 1 is one 1000 kg row; session 2 is two, 2000 kg together.
    Per session: (1000 + 2000) / 2 = 1500. Per row: 3000 / 3 = 1000.
    """
    rows = [
        at(9, days=0, session_id=1, weight=100.0, reps=10),
        at(9, days=1, session_id=2, weight=100.0, reps=10),
        at(9, days=1, session_id=2, weight=100.0, reps=10),
    ]
    parts = {p['label']: p for p in analytics.daypart_volume(rows)['parts']}
    assert parts['morning']['sessions'] == 2, 'counted rows as sessions'
    assert parts['morning']['avg_volume'] == 1500.0, 'averaged rows instead of sessions'


def test_daypart_boundaries_are_half_open():
    """08:00 and 19:00 LOCAL are inside their parts; 14:00 and 23:00 have
    fallen out of them. Interior hours alone cannot catch a < / <= slip.
    Stored hours are UTC, so each is two lower than the local hour it means."""
    rows = [
        at(6, days=0, session_id=1),    # 08:00 local -- first morning hour
        at(12, days=1, session_id=2),   # 14:00 local -- just past morning
        at(17, days=2, session_id=3),   # 19:00 local -- first evening hour
        at(21, days=3, session_id=4),   # 23:00 local -- just past evening
    ]
    parts = {p['label']: p for p in analytics.daypart_volume(rows)['parts']}
    assert parts['morning']['sessions'] == 1
    assert parts['evening']['sessions'] == 1
    assert parts['other']['sessions'] == 2


def test_dayparts_bucket_by_local_clock_not_utc():
    """The stored hour is UTC; "morgens" and "abends" are wall-clock words.
    Read off the raw UTC hour, an 08:00 session counted as 06:00 and fell out
    of the morning bucket, and a 20:00 one fell out of the evening bucket --
    both landing in "other"."""
    rows = [
        at(6, days=0, session_id=1),    # 08:00 local
        at(18, days=1, session_id=2),   # 20:00 local
    ]
    parts = {p['label']: p for p in analytics.daypart_volume(rows)['parts']}
    assert parts['morning']['sessions'] == 1
    assert parts['evening']['sessions'] == 1
    assert parts['other']['sessions'] == 0


def test_weekday_distribution_uses_the_local_weekday():
    """A Monday 00:30 session is stored as Sunday 22:30 UTC."""
    monday_early = perf([(100.0, 10)], session_id=1,
                        started_at=dt.datetime(2026, 6, 7, 22, 30))   # Sun 7 Jun UTC
    days = {d['weekday']: d['sessions'] for d in analytics.weekday_distribution([monday_early])['days']}
    assert days[0] == 1, 'Monday'
    assert days[6] == 0, 'Sunday'


def test_daypart_volume_needs_both_buckets_to_clear_the_threshold():
    # plenty of mornings, one evening -- not a comparison
    rows = [at(9, days=i, session_id=i) for i in range(analytics.MIN_SESSIONS_PER_DAYPART)]
    rows.append(at(20, days=99, session_id=99))
    assert analytics.daypart_volume(rows)['statable'] is False


def test_daypart_volume_is_statable_when_both_buckets_clear_it():
    n = analytics.MIN_SESSIONS_PER_DAYPART
    rows = [at(9, days=i, session_id=i) for i in range(n)]
    rows += [at(20, days=100 + i, session_id=100 + i) for i in range(n)]
    assert analytics.daypart_volume(rows)['statable'] is True


def test_daypart_volume_on_no_history_is_empty_not_broken():
    result = analytics.daypart_volume([])
    assert result['statable'] is False
    assert all(p['sessions'] == 0 for p in result['parts'])


def test_weekday_distribution_counts_sessions_per_weekday():
    # 2026-06-01 is a Monday
    rows = [at(9, days=0, session_id=1), at(9, days=0, session_id=1),
            at(9, days=1, session_id=2)]
    days = {d['weekday']: d['sessions'] for d in analytics.weekday_distribution(rows)['days']}
    assert days[0] == 1      # Monday: one session, two rows
    assert days[1] == 1
    assert days[6] == 0      # Sunday: never trained, still present


def test_weekday_distribution_lists_monday_first_and_carries_no_copy():
    days = analytics.weekday_distribution([])['days']
    assert [d['weekday'] for d in days] == [0, 1, 2, 3, 4, 5, 6]
    assert all('label' not in d for d in days), 'weekday copy belongs in the template'


def test_weekday_distribution_is_statable_at_the_threshold():
    """Pins the >= comparison and proves the flag can ever be True -- the
    only other assertion on it is the empty case, which a hardcoded False
    would also satisfy."""
    rows = [at(9, days=i, session_id=i) for i in range(analytics.MIN_SESSIONS_FOR_WEEKDAY)]
    result = analytics.weekday_distribution(rows)
    assert result['sample'] == analytics.MIN_SESSIONS_FOR_WEEKDAY
    assert result['statable'] is True


def test_weekday_distribution_is_not_statable_below_the_threshold():
    rows = [at(9, days=i, session_id=i) for i in range(analytics.MIN_SESSIONS_FOR_WEEKDAY - 1)]
    assert analytics.weekday_distribution(rows)['statable'] is False


def test_rest_gap_effect_buckets_by_days_since_the_previous_session():
    rows = [at(9, days=0, session_id=1), at(9, days=1, session_id=2),
            at(9, days=5, session_id=3)]
    buckets = {b['label']: b for b in analytics.rest_gap_effect(rows)['buckets']}
    assert buckets['0-1']['sessions'] == 1     # session 2, one day after session 1
    assert buckets['4+']['sessions'] == 1      # session 3, four days after session 2


def test_rest_gap_effect_is_not_statable_on_tiny_buckets():
    rows = [at(9, days=i * 2, session_id=i) for i in range(4)]
    assert analytics.rest_gap_effect(rows)['statable'] is False


def test_rest_gap_effect_on_no_history_is_empty_not_broken():
    result = analytics.rest_gap_effect([])
    assert result['statable'] is False
    assert all(b['sessions'] == 0 for b in result['buckets'])


def test_effort_distribution_splits_tonnage_by_muscle_group():
    rows = [
        perf([(100.0, 10)], muscle_group='Brust', exercise_id=1, name='Bank'),
        perf([(50.0, 10)], muscle_group='Ruecken', exercise_id=2, name='Rudern', session_id=2),
    ]
    groups = {g['label']: g for g in analytics.effort_distribution(rows)['groups']}
    assert groups['Brust']['volume'] == 1000.0
    assert groups['Brust']['share'] == round(1000 / 1500 * 100, 1)
    assert groups['Ruecken']['volume'] == 500.0


def test_effort_distribution_sorts_biggest_share_first():
    rows = [
        perf([(10.0, 10)], muscle_group='Klein', exercise_id=1, name='A'),
        perf([(100.0, 10)], muscle_group='Gross', exercise_id=2, name='B', session_id=2),
    ]
    assert [g['label'] for g in analytics.effort_distribution(rows)['groups']] == ['Gross', 'Klein']


def test_effort_distribution_also_breaks_down_per_exercise():
    rows = [perf([(100.0, 10)], exercise_id=1, name='Bankdruecken')]
    exercises = analytics.effort_distribution(rows)['exercises']
    assert exercises[0]['label'] == 'Bankdruecken'
    assert exercises[0]['sets'] == 1


def test_effort_distribution_labels_an_exercise_without_a_group():
    rows = [perf([(100.0, 10)], muscle_group=None)]
    assert analytics.effort_distribution(rows)['groups'][0]['label'] == stats.NO_GROUP_LABEL


def test_effort_distribution_includes_deloads_because_it_describes():
    rows = [perf([(60.0, 10)], muscle_group='Brust', is_deload=True)]
    assert analytics.effort_distribution(rows)['groups'][0]['volume'] == 600.0


def test_effort_distribution_on_no_history_is_empty_not_broken():
    result = analytics.effort_distribution([])
    assert result['groups'] == []
    assert result['exercises'] == []


def test_effort_distribution_counts_sets_not_rows():
    """One row can hold several sets, so counting rows would undercount every
    real workout. Every other test here gives each row a single set, where the
    two readings coincide and nothing would catch the difference.
    """
    rows = [
        perf([(100.0, 10), (100.0, 8), (100.0, 6)], muscle_group='Brust',
             exercise_id=1, name='Bank'),
        perf([(50.0, 10)], muscle_group='Brust', exercise_id=2, name='Fly',
             session_id=2),
    ]
    groups = {g['label']: g for g in analytics.effort_distribution(rows)['groups']}
    assert groups['Brust']['sets'] == 4, 'counted rows instead of sets'
    exercises = {e['label']: e for e in analytics.effort_distribution(rows)['exercises']}
    assert exercises['Bank']['sets'] == 3
    assert exercises['Fly']['sets'] == 1


def test_effort_distribution_breaks_volume_ties_alphabetically():
    """Equal volumes must order predictably, or the table reshuffles between
    page loads for no visible reason."""
    rows = [
        perf([(100.0, 10)], muscle_group='Zebra', exercise_id=1, name='Z'),
        perf([(100.0, 10)], muscle_group='Alpha', exercise_id=2, name='A', session_id=2),
    ]
    assert [g['label'] for g in analytics.effort_distribution(rows)['groups']] == ['Alpha', 'Zebra']


def test_record_timeline_reports_a_beaten_previous_best():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
    ]
    weight_records = [r for r in analytics.record_timeline(rows) if r['weight']]
    assert len(weight_records) == 1
    assert weight_records[0]['weight']['value'] == 110.0
    assert weight_records[0]['weight']['previous'] == 100.0
    assert weight_records[0]['started_at'] == day(7)


def test_record_timeline_does_not_count_the_first_session():
    rows = [perf([(100.0, 8)], started_at=day(0), session_id=1)]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_is_newest_first():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
        perf([(120.0, 8)], started_at=day(14), session_id=3),
    ]
    dates = [r['started_at'] for r in analytics.record_timeline(rows) if r['weight']]
    assert dates == [day(14), day(7)]


def test_record_timeline_excludes_deload_sessions():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(200.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_reports_an_e1rm_only_record():
    # more reps at the same weight: an e1RM record but not a weight record
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(100.0, 12)], started_at=day(7), session_id=2),
    ]
    timeline = analytics.record_timeline(rows)
    assert len(timeline) == 1
    assert timeline[0]['weight'] is None
    assert timeline[0]['e1rm']['previous'] < timeline[0]['e1rm']['value']


def test_record_timeline_merges_both_bests_of_one_exercise_day():
    """A heavier top set almost always drags an e1RM best along with it. That
    is one lift, not two milestones, so it is one row carrying both figures --
    otherwise the timeline doubles in length and its own count stops describing
    what happened."""
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(120.0, 10)], started_at=day(7), session_id=2),
    ]
    timeline = analytics.record_timeline(rows)
    assert len(timeline) == 1
    assert timeline[0]['weight']['value'] == 120.0
    assert timeline[0]['weight']['previous'] == 100.0
    assert timeline[0]['e1rm'] is not None


def test_record_timeline_on_no_history_is_empty():
    assert analytics.record_timeline([]) == []


def test_record_timeline_collapses_two_slots_of_one_session_before_judging():
    """An exercise performed twice in the same workout (two slots) is one
    session, not two attempts to beat -- so a heavier second slot must not
    register as beating the first slot's showing. Every test above gives
    each session at most one row, where a per-row implementation and a
    per-session one agree; this is the first session ever for the exercise,
    so if either row were compared against the other one would wrongly look
    like a beaten record even though there is no earlier SESSION to beat.
    """
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1, position=1),
        perf([(120.0, 8)], started_at=day(0), session_id=1, position=4),
    ]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_judges_a_later_session_against_the_earlier_ones_best_slot():
    """Continuing the above: once a session has two slots, the LATER session
    must be compared against that session's best showing, not against
    whichever slot happens to be seen first. Session 1's best is 120 kg
    (across two slots); session 2's 110 kg does not beat it and must not
    appear as a record, even though 110 beats session 1's WORSE slot (100).
    """
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1, position=1),
        perf([(120.0, 8)], started_at=day(0), session_id=1, position=4),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
    ]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_collapses_a_session_to_its_best_slot_whatever_the_order():
    """The heavier slot is logged FIRST here. Both existing collapse tests put
    the heavier slot second, where "keep whichever row came last" produces the
    same answer as max() and neither test can tell them apart.

    Session 1's best is 120 kg. A later 110 kg session is therefore NOT a
    record -- but a keep-last implementation would collapse session 1 to 100
    and emit one.
    """
    rows = [
        perf([(120.0, 8)], started_at=day(0), session_id=1, position=1),
        perf([(100.0, 8)], started_at=day(0), session_id=1, position=4),
        perf([(110.0, 8)], started_at=day(7), session_id=2, position=1),
    ]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_orders_same_day_records_predictably():
    """Two exercises setting a record on the same day must come out in a
    stable order, or the list reshuffles between page loads."""
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1, exercise_id=1, name='Alpha'),
        perf([(100.0, 8)], started_at=day(0), session_id=1, exercise_id=2, name='Zebra'),
        perf([(120.0, 8)], started_at=day(7), session_id=2, exercise_id=1, name='Alpha'),
        perf([(120.0, 8)], started_at=day(7), session_id=2, exercise_id=2, name='Zebra'),
    ]
    weight_records = [r for r in analytics.record_timeline(rows) if r['weight']]
    assert [r['name'] for r in weight_records] == ['Zebra', 'Alpha']


# ---- monthly_tonnage: the career strip -------------------------------------

def test_monthly_tonnage_emits_every_month_including_empty_ones():
    """A break has to stay visible as a break. Skipping empty months would
    compress a gap into a shorter strip and redraw the timeline."""
    rows = [
        perf([(100.0, 10)], started_at=dt.datetime(2026, 1, 5), session_id=1),
        perf([(100.0, 10)], started_at=dt.datetime(2026, 4, 5), session_id=2),
    ]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 4, 20))
    assert [(m['year'], m['month']) for m in months] == [
        (2026, 1), (2026, 2), (2026, 3), (2026, 4)]
    assert [m['is_gap'] for m in months] == [False, True, True, False]
    assert months[1]['volume'] == 0


def test_monthly_tonnage_runs_to_now_not_to_the_last_session():
    """The strip is a calendar, so months since you last trained are part of
    the picture -- that silence is the most interesting thing on it."""
    rows = [perf([(100.0, 10)], started_at=dt.datetime(2026, 1, 5), session_id=1)]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 3, 2))
    assert [(m['year'], m['month']) for m in months] == [(2026, 1), (2026, 2), (2026, 3)]
    assert months[-1]['is_gap'] is True


def test_monthly_tonnage_sums_volume_and_counts_deloads():
    rows = [
        perf([(100.0, 10)], started_at=dt.datetime(2026, 1, 5), session_id=1),
        perf([(50.0, 10)], started_at=dt.datetime(2026, 1, 12), session_id=2, is_deload=True),
    ]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 1, 20))
    assert months[0]['volume'] == 1500.0     # deloads still count toward tonnage
    assert months[0]['has_deload'] is True


def test_monthly_tonnage_crosses_a_year_boundary():
    rows = [perf([(100.0, 10)], started_at=dt.datetime(2025, 11, 5), session_id=1)]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 2, 1))
    assert [(m['year'], m['month']) for m in months] == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_monthly_tonnage_is_empty_without_rows():
    assert analytics.monthly_tonnage([], NOW) == []
