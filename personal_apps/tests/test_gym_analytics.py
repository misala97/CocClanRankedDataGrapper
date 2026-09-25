"""Tests for features.gym.analytics -- what Verlauf says about the whole
history. Pure functions, so no app context, no database, no fixtures beyond
plain data."""
import datetime as dt

from features.gym import analytics, stats


def perf(sets, started_at=None, session_id=1, exercise_id=1, name='Bankdruecken',
         muscle_group='Brust', is_unilateral=False, position=1, is_deload=False,
         minutes=None, weight_increment=None, stack_kg=None):
    """Build one PerformedExercise. `sets` is [(weight, reps), ...]. `minutes`
    is how long the session ran; None leaves it untimed, like every session
    logged before the app wrote finish stamps."""
    started = started_at or dt.datetime(2026, 6, 1, 18, 0)
    return stats.PerformedExercise(
        exercise_id=exercise_id, name=name, muscle_group=muscle_group,
        is_unilateral=is_unilateral, position=position, session_id=session_id,
        started_at=started, sets=tuple(sets), is_deload=is_deload,
        weight_increment=weight_increment, stack_kg=stack_kg,
        finished_at=None if minutes is None else started + dt.timedelta(minutes=minutes),
    )


def day(n):
    return dt.datetime(2026, 6, 1, 18, 0) + dt.timedelta(days=n)


NOW = dt.datetime(2026, 7, 1, 18, 0)


def week(n, weekday=0):
    """Monday of the n-th week after the first session's week."""
    base = dt.datetime(2026, 6, 1, 18, 0)          # a Monday
    return base + dt.timedelta(weeks=n, days=weekday)


def test_consistency_counts_the_weeks_that_held_a_workout():
    rows = [perf([(100.0, 10)], started_at=week(n), session_id=n) for n in (0, 1, 3)]
    result = analytics.consistency(rows, week(3, 6))
    assert result['weeks_trained'] == 3
    assert result['weeks_total'] == 4
    assert result['share'] == 75.0


def test_consistency_reports_the_current_and_the_longest_streak():
    # weeks 0,1,2 trained, week 3 missed, weeks 4,5 trained
    rows = [perf([(100.0, 10)], started_at=week(n), session_id=n) for n in (0, 1, 2, 4, 5)]
    result = analytics.consistency(rows, week(5, 6))
    assert result['longest_streak'] == 3
    assert result['current_streak'] == 2


def test_consistency_keeps_the_streak_alive_during_an_unfinished_week():
    """Monday is not a broken streak. The current week has not had its chance
    yet, so it only ever extends a streak, never ends one."""
    rows = [perf([(100.0, 10)], started_at=week(n), session_id=n) for n in (0, 1, 2)]
    result = analytics.consistency(rows, week(3, 0))
    assert result['current_streak'] == 3


def test_consistency_breaks_the_streak_once_a_whole_week_was_missed():
    rows = [perf([(100.0, 10)], started_at=week(n), session_id=n) for n in (0, 1, 2)]
    result = analytics.consistency(rows, week(4, 3))
    assert result['current_streak'] == 0
    assert result['longest_streak'] == 3


def test_consistency_on_no_history_is_empty_not_broken():
    result = analytics.consistency([], NOW)
    assert result['statable'] is False
    assert result['weeks_trained'] == 0
    assert result['current_streak'] == 0


def test_record_timeline_reports_a_beaten_previous_best():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
    ]
    timeline = analytics.record_timeline(rows)
    assert len(timeline) == 1
    assert timeline[0]['e1rm'] == {'value': 139.3, 'previous': 126.7}
    assert timeline[0]['started_at'] == day(7)


def test_record_timeline_does_not_count_the_first_session():
    rows = [perf([(100.0, 8)], started_at=day(0), session_id=1)]
    assert analytics.record_timeline(rows) == []


def test_record_timeline_is_newest_first():
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(110.0, 8)], started_at=day(7), session_id=2),
        perf([(120.0, 8)], started_at=day(14), session_id=3),
    ]
    dates = [r['started_at'] for r in analytics.record_timeline(rows)]
    assert dates == [day(14), day(7)]


def test_record_timeline_counts_deload_sessions_like_any_other():
    # D3 b-A: a record is a record, deload or not.
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(200.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert [r['session_id'] for r in analytics.record_timeline(rows)] == [2]


def test_record_timeline_reports_an_e1rm_only_record():
    # more reps at the same weight: an e1RM record but not a weight record
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(100.0, 12)], started_at=day(7), session_id=2),
    ]
    timeline = analytics.record_timeline(rows)
    assert len(timeline) == 1
    assert 'weight' not in timeline[0]
    assert timeline[0]['e1rm']['previous'] < timeline[0]['e1rm']['value']


def test_record_timeline_names_the_e1rm_when_the_weight_moved_too():
    """One lift, one row, one figure: weight is no kind of record (D3)."""
    rows = [
        perf([(100.0, 8)], started_at=day(0), session_id=1),
        perf([(120.0, 10)], started_at=day(7), session_id=2),
    ]
    timeline = analytics.record_timeline(rows)
    assert len(timeline) == 1
    assert timeline[0]['e1rm'] == {'value': 160.0, 'previous': 126.7}


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
    assert [r['name'] for r in analytics.record_timeline(rows)] == ['Zebra', 'Alpha']


# ---- monthly_tonnage: Verlauf's month index -------------------------------

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
    # Their share, not a yes/no over the whole month (G-026).
    assert months[0]['deload_volume'] == 500.0


def test_monthly_tonnage_counts_each_months_records():
    """A yes/no mark sat on every month and said nothing (G-026)."""
    rows = [
        perf([(100.0, 8)], started_at=dt.datetime(2026, 1, 5), session_id=1),
        perf([(110.0, 8)], started_at=dt.datetime(2026, 2, 5), session_id=2),
        perf([(120.0, 8)], started_at=dt.datetime(2026, 2, 19), session_id=3),
        perf([(115.0, 8)], started_at=dt.datetime(2026, 3, 5), session_id=4),
    ]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 3, 20))
    assert [m['records'] for m in months] == [0, 2, 0]
    assert [m['deload_volume'] for m in months] == [0, 0, 0]


def test_monthly_tonnage_runs_to_the_local_month():
    """00:30 on 1 April in Berlin is still 31 March in UTC; the strip ended a
    month short until 02:00 (G-129)."""
    rows = [perf([(100.0, 10)], started_at=dt.datetime(2026, 3, 5), session_id=1)]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 3, 31, 22, 30))
    assert [(m['year'], m['month']) for m in months] == [(2026, 3), (2026, 4)]


def test_monthly_tonnage_crosses_a_year_boundary():
    rows = [perf([(100.0, 10)], started_at=dt.datetime(2025, 11, 5), session_id=1)]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 2, 1))
    assert [(m['year'], m['month']) for m in months] == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_monthly_tonnage_is_empty_without_rows():
    assert analytics.monthly_tonnage([], NOW) == []


def test_monthly_tonnage_starts_at_an_earlier_first_workout():
    """Verlauf lists a workout that logged nothing, and its month heading
    needs a band in the index -- the strip starts there, not at the first
    set (M3)."""
    rows = [perf([(100.0, 10)], started_at=dt.datetime(2026, 3, 5), session_id=2)]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 3, 20),
                                       first=dt.datetime(2026, 1, 20))
    assert [(m['year'], m['month']) for m in months] == [(2026, 1), (2026, 2), (2026, 3)]
    assert [m['volume'] for m in months] == [0, 0, 1000.0]


def test_monthly_tonnage_starts_at_the_first_row_when_that_is_earlier():
    rows = [perf([(100.0, 10)], started_at=dt.datetime(2026, 1, 5), session_id=1)]
    months = analytics.monthly_tonnage(rows, dt.datetime(2026, 2, 20),
                                       first=dt.datetime(2026, 2, 3))
    assert [(m['year'], m['month']) for m in months] == [(2026, 1), (2026, 2)]


def test_monthly_tonnage_with_only_a_first_moment_is_its_months():
    months = analytics.monthly_tonnage([], dt.datetime(2026, 4, 2),
                                       first=dt.datetime(2026, 3, 30))
    assert [(m['year'], m['month'], m['volume']) for m in months] == [(2026, 3, 0), (2026, 4, 0)]
