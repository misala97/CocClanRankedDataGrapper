"""Tests for features.gym.stats -- pure functions, so no app context, no
database, and no fixtures beyond plain data."""
import datetime as dt

from features.gym import stats


def perf(sets, position=1, started_at=None, is_unilateral=False,
         exercise_id=1, name='Bankdruecken', muscle_group='Brust', session_id=1,
         is_deload=False, weight_increment=None):
    """Build one PerformedExercise. `sets` is [(weight, reps), ...]."""
    return stats.PerformedExercise(
        exercise_id=exercise_id,
        name=name,
        muscle_group=muscle_group,
        is_unilateral=is_unilateral,
        position=position,
        session_id=session_id,
        started_at=started_at or dt.datetime(2026, 7, 1, 18, 0),
        sets=tuple(sets),
        is_deload=is_deload,
        weight_increment=weight_increment,
    )


def test_performed_exercise_defaults_to_not_deload():
    assert perf([(80.0, 8)]).is_deload is False


def test_performed_exercise_carries_the_deload_flag():
    assert perf([(80.0, 8)], is_deload=True).is_deload is True


def test_epley_1rm_at_one_rep_is_the_weight_itself():
    assert stats.epley_1rm(100.0, 1) == 100.0 * (1 + 1 / 30.0)


def test_epley_1rm_at_zero_reps_is_the_weight():
    assert stats.epley_1rm(100.0, 0) == 100.0


def test_epley_1rm_rewards_more_reps_at_the_same_weight():
    assert stats.epley_1rm(80.0, 10) > stats.epley_1rm(80.0, 8)


def test_set_volume_is_weight_times_reps():
    assert stats.set_volume(80.0, 8, False) == 640.0


def test_set_volume_doubles_for_unilateral_because_both_sides_did_it():
    assert stats.set_volume(20.0, 10, True) == 400.0


def test_row_volume_sums_every_set():
    row = perf([(80.0, 8), (80.0, 8), (82.5, 6)])
    assert stats.row_volume(row) == 80.0 * 8 + 80.0 * 8 + 82.5 * 6


def test_row_volume_respects_unilateral():
    row = perf([(20.0, 10), (20.0, 10)], is_unilateral=True)
    assert stats.row_volume(row) == 800.0


def test_best_weight_and_best_e1rm_pick_different_sets_when_they_should():
    # The heaviest set is not always the best estimated 1RM: 5 reps at 100
    # estimates lower than 12 reps at 90.
    row = perf([(100.0, 5), (90.0, 12)])
    assert stats.best_weight(row) == 100.0
    assert stats.best_e1rm(row) == stats.epley_1rm(90.0, 12)


def day(n):
    return dt.datetime(2026, 6, 1, 18, 0) + dt.timedelta(days=n)


def test_sessions_since_pr_is_none_without_enough_history():
    assert stats.sessions_since_pr([]) is None
    assert stats.sessions_since_pr([perf([(80.0, 8)], started_at=day(0))]) is None


def test_sessions_since_pr_counts_sessions_after_the_best_one():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),   # the PR
        perf([(82.5, 8)], started_at=day(14)),
        perf([(82.5, 8)], started_at=day(21)),
    ]
    assert stats.sessions_since_pr(rows) == 2


def test_sessions_since_pr_is_zero_when_the_latest_session_is_the_best():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),
    ]
    assert stats.sessions_since_pr(rows) == 0


def test_more_reps_at_the_same_weight_counts_as_a_pr():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(80.0, 10)], started_at=day(7)),
    ]
    assert stats.sessions_since_pr(rows) == 0


def test_sessions_since_pr_scopes_to_position_when_that_slot_has_history():
    rows = [
        perf([(85.0, 8)], position=1, started_at=day(0)),
        perf([(70.0, 8)], position=3, started_at=day(7)),
        perf([(72.5, 8)], position=3, started_at=day(14)),
    ]
    # Slot 3 has 2 sessions and is climbing, so it has a fresh PR of its own --
    # the heavier slot-1 session must not mask that.
    assert stats.sessions_since_pr(rows, position=3) == 0


def test_sessions_since_pr_falls_back_to_all_positions_when_the_slot_is_thin():
    rows = [
        perf([(85.0, 8)], position=1, started_at=day(0)),
        perf([(80.0, 8)], position=1, started_at=day(7)),
        perf([(70.0, 8)], position=3, started_at=day(14)),
    ]
    # Slot 3 has only one session, too little to judge from, so the answer
    # comes from every position instead of being None.
    assert stats.sessions_since_pr(rows, position=3) == 2


def test_exercise_state_neu_when_never_performed():
    assert stats.exercise_state([]) == 'neu'


def test_exercise_state_rekord_when_the_latest_session_beat_everything():
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),
    ]
    assert stats.exercise_state(rows) == 'rekord'


def test_exercise_state_stagniert_at_the_threshold():
    rows = [perf([(85.0, 8)], started_at=day(0))]
    rows += [perf([(80.0, 8)], started_at=day(7 * n)) for n in range(1, 5)]
    assert stats.sessions_since_pr(rows) == 4
    assert stats.exercise_state(rows) == 'stagniert'


def test_exercise_state_steigend_when_improving_but_not_a_record():
    rows = [
        perf([(90.0, 8)], started_at=day(0)),   # all-time best
        perf([(80.0, 8)], started_at=day(7)),
        perf([(82.5, 8)], started_at=day(14)),  # better than last time only
    ]
    assert stats.exercise_state(rows) == 'steigend'


def test_exercise_state_is_none_when_flat_and_not_yet_stagnating():
    rows = [
        perf([(90.0, 8)], started_at=day(0)),
        perf([(80.0, 8)], started_at=day(7)),
        perf([(80.0, 8)], started_at=day(14)),
    ]
    assert stats.exercise_state(rows) is None


def test_dominant_position_breaks_ties_toward_the_lower_slot():
    rows = [
        perf([(80.0, 8)], position=3, started_at=day(0)),
        perf([(80.0, 8)], position=1, started_at=day(7)),
    ]
    assert stats.dominant_position(rows) == 1


def test_stall_report_lists_only_stagnating_exercises_worst_first():
    def stalled(exercise_id, name, gap):
        rows = [perf([(85.0, 8)], exercise_id=exercise_id, name=name, started_at=day(0))]
        rows += [
            perf([(80.0, 8)], exercise_id=exercise_id, name=name, started_at=day(7 * n))
            for n in range(1, gap + 1)
        ]
        return rows

    climbing = [
        perf([(80.0, 8)], exercise_id=9, name='Rudern', started_at=day(0)),
        perf([(85.0, 8)], exercise_id=9, name='Rudern', started_at=day(7)),
    ]
    report = stats.stall_report({
        1: stalled(1, 'Bankdruecken', 4),
        2: stalled(2, 'Beinpresse', 6),
        9: climbing,
    })

    assert [entry['name'] for entry in report] == ['Beinpresse', 'Bankdruecken']
    assert report[0]['sessions_since_pr'] == 6
    assert report[0]['stuck_at'] == 80.0
    assert report[0]['since'] == day(0)


class FakeTemplate:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class FakeSession:
    def __init__(self, template_id, started_at):
        self.template_id = template_id
        self.started_at = started_at


class FakeExercise:
    def __init__(self, name, muscle_group):
        self.name = name
        self.muscle_group = muscle_group


NOW = dt.datetime(2026, 7, 23, 12, 0)


def test_exercise_progress_returns_newest_first_table_and_per_position_series():
    rows = [
        perf([(80.0, 8)], position=1, started_at=day(0), session_id=1),
        perf([(70.0, 8)], position=3, started_at=day(7), session_id=2),
        perf([(82.5, 6)], position=1, started_at=day(14), session_id=3),
    ]
    result = stats.exercise_progress(rows)

    assert [entry['session_id'] for entry in result['table']] == [3, 2, 1]
    assert result['available_positions'] == [1, 3]
    assert [series['position'] for series in result['series']] == [1, 3]
    assert len(result['series'][0]['points']) == 2
    assert result['pr_weight']['weight'] == 82.5
    assert result['selected_position'] is None


def test_exercise_progress_isolates_a_single_position_when_asked():
    rows = [
        perf([(80.0, 8)], position=1, started_at=day(0), session_id=1),
        perf([(70.0, 8)], position=3, started_at=day(7), session_id=2),
    ]
    result = stats.exercise_progress(rows, position=3)

    assert [entry['session_id'] for entry in result['table']] == [2]
    assert [series['position'] for series in result['series']] == [3]
    # available_positions always describes the unfiltered data, so the page
    # can still offer the other slots as options.
    assert result['available_positions'] == [1, 3]


def test_exercise_progress_on_an_exercise_with_no_history_is_empty_not_broken():
    result = stats.exercise_progress([])
    assert result['table'] == []
    assert result['series'] == []
    assert result['pr_weight'] is None
    assert result['pr_e1rm'] is None
    assert result['state'] == 'neu'
    assert result['last_progression'] is None


def test_session_report_totals_and_flags_a_weight_record():
    current = [perf([(85.0, 8)], started_at=day(21), session_id=9)]
    history = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(80.0, 8)], started_at=day(7), session_id=2),
    ]
    report = stats.session_report(current, history)

    assert report['total_sets'] == 1
    assert report['total_volume'] == 680.0
    assert report['record_count'] == 1
    assert report['records'][0]['kind'] == 'weight'
    assert report['records'][0]['previous'] == 80.0
    assert report['exercises'][0]['verdict'] == 'rekord'


def test_session_report_marks_a_first_ever_exercise_as_neu_not_as_a_record():
    current = [perf([(60.0, 10)], started_at=day(0), session_id=1)]
    report = stats.session_report(current, [])

    assert report['record_count'] == 0
    assert report['exercises'][0]['verdict'] == 'neu'
    assert report['exercises'][0]['has_history'] is False
    assert report['exercises'][0]['avg_volume'] is None
    assert report['exercises'][0]['volume_delta_pct'] is None


def test_session_report_advises_on_a_stagnating_exercise():
    history = [perf([(85.0, 8)], started_at=day(0), session_id=1)]
    history += [
        perf([(80.0, 8)], started_at=day(7 * n), session_id=n + 1)
        for n in range(1, 4)
    ]
    current = [perf([(80.0, 8)], started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['exercises'][0]['verdict'] == 'stagniert'
    assert len(report['advice']) == 1
    assert report['advice'][0]['stuck_at'] == 80.0
    assert report['advice'][0]['suggested_weight'] == 82.5


def test_session_report_suggests_a_smaller_jump_for_unilateral_work():
    history = [perf([(22.5, 8)], is_unilateral=True, started_at=day(0), session_id=1)]
    history += [
        perf([(20.0, 8)], is_unilateral=True, started_at=day(7 * n), session_id=n + 1)
        for n in range(1, 4)
    ]
    current = [perf([(20.0, 8)], is_unilateral=True, started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['advice'][0]['suggested_weight'] == 21.25


def test_session_report_compares_against_the_template_cohort_when_given_one():
    current = [perf([(80.0, 10)], started_at=day(21), session_id=9)]
    report = stats.session_report(current, [], comparable_session_volumes=[400.0, 400.0])

    assert report['avg_total_volume'] == 400.0
    assert report['total_volume_delta_pct'] == 100


def test_session_report_omits_the_whole_workout_comparison_for_freeform_sessions():
    current = [perf([(80.0, 10)], started_at=day(21), session_id=9)]
    report = stats.session_report(current, [])

    assert report['avg_total_volume'] is None
    assert report['total_volume_delta_pct'] is None


def test_muscle_group_volume_lists_untrained_catalogue_groups_at_zero():
    rows = [
        perf([(80.0, 8)] * 5, muscle_group='Brust', started_at=NOW - dt.timedelta(days=3)),
        perf([(60.0, 8)], muscle_group='Waden', started_at=NOW - dt.timedelta(days=3)),
    ]
    result = stats.muscle_group_volume(rows, ['Brust', 'Waden', 'Bizeps'], NOW)
    by_group = {bucket['group']: bucket for bucket in result}

    assert by_group['Brust']['sets'] == 5
    assert by_group['Brust']['under_trained'] is False
    assert by_group['Waden']['sets'] == 1
    assert by_group['Waden']['under_trained'] is True   # 1 < 25% of 5
    assert by_group['Bizeps']['sets'] == 0
    assert by_group['Bizeps']['under_trained'] is True


def test_muscle_group_volume_ignores_work_outside_the_window():
    rows = [perf([(80.0, 8)], muscle_group='Brust', started_at=NOW - dt.timedelta(days=40))]
    result = stats.muscle_group_volume(rows, ['Brust'], NOW)

    assert result[0]['sets'] == 0


def test_weekly_tonnage_returns_one_bucket_per_week_oldest_first():
    rows = [perf([(100.0, 10)], started_at=NOW - dt.timedelta(days=1))]
    result = stats.weekly_tonnage(rows, NOW, weeks=4)

    assert len(result) == 4
    assert result[0]['week_start'] < result[-1]['week_start']
    assert result[-1]['is_current'] is True
    assert result[-1]['volume'] == 1000.0
    assert sum(bucket['is_current'] for bucket in result) == 1


def test_weekly_tonnage_buckets_by_iso_week_not_by_rolling_seven_days():
    monday = dt.datetime(2026, 7, 20, 9, 0)     # a Monday
    sunday_before = dt.datetime(2026, 7, 19, 9, 0)
    rows = [
        perf([(100.0, 10)], started_at=monday, session_id=1),
        perf([(100.0, 10)], started_at=sunday_before, session_id=2),
    ]
    result = stats.weekly_tonnage(rows, dt.datetime(2026, 7, 23, 12, 0), weeks=2)

    assert result[0]['volume'] == 1000.0
    assert result[1]['volume'] == 1000.0


def test_consistency_reports_rate_and_gap():
    finished = [NOW - dt.timedelta(days=n) for n in (2, 5, 9, 30)]
    result = stats.consistency(finished, NOW)

    assert result['sessions'] == 3          # the 30-day-old one is outside
    assert result['per_week'] == 0.75
    assert result['days_since_last'] == 2


# The recency figures are rendered as CALENDAR words ("heute" / "gestern"), and
# every fixture above offsets by whole days -- under which elapsed-hours
# arithmetic and calendar arithmetic agree, so the suite could not see the bug
# that shipped. These cross a midnight instead.
#
# All timestamps here are naive UTC, as stored. NOW is 01:00 UTC = 03:00 CEST,
# i.e. early morning on 1 August local.
LATE_NIGHT = dt.datetime(2026, 8, 1, 1, 0)


def test_consistency_counts_calendar_days_not_elapsed_hours():
    # 31 July 18:00 UTC = 20:00 local: yesterday evening, 7 hours ago.
    yesterday_evening = dt.datetime(2026, 7, 31, 18, 0)
    result = stats.consistency([yesterday_evening], LATE_NIGHT)

    assert result['days_since_last'] == 1, 'an evening workout read after midnight is gestern, not heute'


def test_consistency_says_zero_only_for_the_same_local_date():
    same_morning = dt.datetime(2026, 8, 1, 0, 30)     # 02:30 local, still 1 Aug
    assert stats.consistency([same_morning], LATE_NIGHT)['days_since_last'] == 0


def test_consistency_uses_local_midnight_not_utc_midnight():
    # 22:30 UTC on 31 July is already 00:30 on 1 August in CEST, so from
    # 03:00 local on 1 August it is the SAME calendar day.
    just_after_local_midnight = dt.datetime(2026, 7, 31, 22, 30)
    assert stats.consistency([just_after_local_midnight], LATE_NIGHT)['days_since_last'] == 0


def test_routine_memory_counts_calendar_days_not_elapsed_hours():
    templates = [FakeTemplate(1, 'Push')]
    sessions = [FakeSession(1, dt.datetime(2026, 7, 31, 18, 0))]
    result = stats.routine_memory(templates, sessions, LATE_NIGHT)

    assert result[0]['days_ago'] == 1


def test_week_start_buckets_by_local_week_not_utc_week():
    # Monday 3 Aug 2026, 00:30 local = Sunday 2 Aug 22:30 UTC. The local week
    # it belongs to starts Monday 3 August.
    sunday_night_utc = dt.datetime(2026, 8, 2, 22, 30)
    assert stats._week_start(sunday_night_utc) == dt.datetime(2026, 8, 3)


def test_consistency_with_no_history_does_not_divide_by_zero():
    result = stats.consistency([], NOW)

    assert result['sessions'] == 0
    assert result['per_week'] == 0.0
    assert result['days_since_last'] is None


def test_routine_memory_sorts_longest_ago_first_and_unused_last():
    templates = [FakeTemplate(1, 'Push'), FakeTemplate(2, 'Pull'), FakeTemplate(3, 'Beine')]
    sessions = [
        FakeSession(1, NOW - dt.timedelta(days=5)),
        FakeSession(1, NOW - dt.timedelta(days=12)),
        FakeSession(2, NOW - dt.timedelta(days=2)),
    ]
    result = stats.routine_memory(templates, sessions, NOW)

    assert [entry['template'].name for entry in result] == ['Push', 'Pull', 'Beine']
    assert result[0]['days_ago'] == 5        # most recent Push, not the older one
    assert result[2]['days_ago'] is None


def test_group_exercises_by_muscle_keeps_vocabulary_order_and_collects_strays():
    exercises = [
        FakeExercise('Bizepscurls', 'Bizeps'),
        FakeExercise('Bankdruecken', 'Brust'),
        FakeExercise('Etwas Altes', 'Legacy-Kategorie'),
        FakeExercise('Ohne Gruppe', None),
    ]
    result = stats.group_exercises_by_muscle(exercises, ('Bizeps', 'Brust'))

    assert [group for group, _ in result] == ['Bizeps', 'Brust', 'Ohne Muskelgruppe']
    assert [ex.name for ex in result[2][1]] == ['Etwas Altes', 'Ohne Gruppe']


# -- session_record_counts -- Verlauf's bulk companion to session_report()'s
# own per-session record_count. Every case here is chosen to mirror a real
# session_report() call: if these disagree with what session_report(current,
# history) would compute for the same session, Verlauf and the session's own
# detail page show two different "truths" for one fact (the bug this
# function exists to fix).

def test_session_record_counts_compares_the_top_session_against_the_second_best():
    # The session holding the single highest value can't be compared against
    # itself -- it must be judged against the next-best (here, the only
    # other session), the top-2 fallback the review called out explicitly.
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(90.0, 8)], started_at=day(7), session_id=2),
    ]
    counts = stats.session_record_counts(rows)

    assert counts.get(2, 0) == 1
    assert counts.get(1, 0) == 0


def test_session_record_counts_does_not_count_a_record_since_overtaken_by_a_later_session():
    # This is the exact real-world bug: session 2 was a record only against
    # what came before it (session 1), but session 3 has since beaten it --
    # session 2 must NOT count, because it does not beat *every other*
    # session, only the ones before it.
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(85.0, 8)], started_at=day(7), session_id=2),
        perf([(90.0, 8)], started_at=day(14), session_id=3),
    ]
    counts = stats.session_record_counts(rows)

    assert counts.get(1, 0) == 0
    assert counts.get(2, 0) == 0
    assert counts.get(3, 0) == 1


def test_session_record_counts_accumulates_across_multiple_exercises_for_one_session():
    rows = [
        perf([(80.0, 8)], exercise_id=1, name='Bankdruecken', started_at=day(0), session_id=1),
        perf([(90.0, 8)], exercise_id=1, name='Bankdruecken', started_at=day(7), session_id=2),
        perf([(50.0, 10)], exercise_id=2, name='Beinpresse', started_at=day(0), session_id=1),
        perf([(60.0, 10)], exercise_id=2, name='Beinpresse', started_at=day(7), session_id=2),
    ]
    counts = stats.session_record_counts(rows)

    assert counts[2] == 2
    assert counts.get(1, 0) == 0


def test_session_record_counts_is_zero_for_an_exercise_only_one_session_has_ever_done():
    # No other session exists to have "beaten" -- matches session_report's
    # own has_history=False -> never a record, regardless of the value.
    rows = [perf([(80.0, 8)], started_at=day(0), session_id=1)]
    counts = stats.session_record_counts(rows)

    assert counts.get(1, 0) == 0


def test_session_record_counts_ties_do_not_count_as_a_record():
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(80.0, 8)], started_at=day(7), session_id=2),
    ]
    counts = stats.session_record_counts(rows)

    assert counts.get(1, 0) == 0
    assert counts.get(2, 0) == 0


def test_session_record_counts_catches_an_e1rm_record_that_is_not_a_weight_record():
    # session 2 is not the heaviest, but 12 reps at 90 estimates a higher
    # 1RM than 5 reps at 100 -- it must still register as a record on the
    # e1RM axis alone. (session 1 legitimately also counts here, via the
    # separate weight axis: 100kg is still the heaviest of the two -- that
    # is a real, independent record, not a fixture mistake.)
    rows = [
        perf([(100.0, 5)], started_at=day(0), session_id=1),   # heaviest weight
        perf([(90.0, 12)], started_at=day(7), session_id=2),   # lighter but a higher e1RM
    ]
    assert stats.best_e1rm(rows[1]) > stats.best_e1rm(rows[0])
    assert stats.best_weight(rows[1]) < stats.best_weight(rows[0])

    counts = stats.session_record_counts(rows)

    assert counts.get(2, 0) == 1   # via e1RM
    assert counts.get(1, 0) == 1   # via weight (heaviest of the two)


def test_session_record_counts_combines_a_sessions_own_duplicate_rows_for_one_exercise():
    # A session can (rarely) log the same exercise twice, in two different
    # slots -- its best row must still be judged as one performance, not let
    # a weaker sibling row shadow it or double-count it.
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1, position=1),
        perf([(70.0, 8)], started_at=day(7), session_id=2, position=1),
        perf([(95.0, 8)], started_at=day(7), session_id=2, position=4),
    ]
    counts = stats.session_record_counts(rows)

    assert counts.get(2, 0) == 1
    assert counts.get(1, 0) == 0


def test_session_record_counts_agrees_with_session_report_for_every_session():
    # Belt-and-suspenders: independently recompute what session_report()
    # would say for every session in a nontrivial multi-session,
    # multi-exercise scenario, and require exact agreement -- this is the
    # actual contract the function exists to satisfy.
    all_rows = [
        perf([(80.0, 8)], exercise_id=1, name='Bankdruecken', started_at=day(0), session_id=1),
        perf([(85.0, 8)], exercise_id=1, name='Bankdruecken', started_at=day(7), session_id=2),
        perf([(90.0, 8)], exercise_id=1, name='Bankdruecken', started_at=day(14), session_id=3),
        perf([(50.0, 10)], exercise_id=2, name='Beinpresse', started_at=day(0), session_id=1),
        perf([(55.0, 10)], exercise_id=2, name='Beinpresse', started_at=day(7), session_id=2),
        perf([(52.0, 10)], exercise_id=2, name='Beinpresse', started_at=day(14), session_id=3),
    ]
    bulk_counts = stats.session_record_counts(all_rows)

    by_session = {}
    for row in all_rows:
        by_session.setdefault(row.session_id, []).append(row)

    for session_id, current in by_session.items():
        history = [row for row in all_rows if row.session_id != session_id]
        report = stats.session_report(current, history)
        assert bulk_counts.get(session_id, 0) == report['record_count'], session_id


def test_deload_weight_takes_the_percentage_and_rounds_down_to_a_plate():
    # 80 * 0.70 = 56.0, which is not loadable in 2.5 kg steps -> 55.0
    assert stats.deload_weight(80.0, 70, 2.5) == 55.0


def test_deload_weight_rounds_down_not_to_nearest():
    # 100 * 0.70 = 70.0 exactly; 90 * 0.70 = 63.0 -> 62.5, not 65.0
    assert stats.deload_weight(100.0, 70, 2.5) == 70.0
    assert stats.deload_weight(90.0, 70, 2.5) == 62.5


def test_deload_weight_rounds_down_even_when_nearest_would_round_up():
    # The discriminating case: 81 * 0.70 = 56.7, which is 22.68 increments of
    # 2.5 kg. Rounding to nearest would give 23 increments (57.5 kg) -- heavier
    # than the 81 kg lift's own prescription implies. Flooring gives 55.0.
    # Every other case in this file has a remainder below 0.5, where floor and
    # round-to-nearest agree, so only this one proves the direction.
    assert stats.deload_weight(81.0, 70, 2.5) == 55.0


def test_deload_weight_uses_the_half_step_for_unilateral():
    # 20 * 0.70 = 14.0 -> 13.75 in 1.25 kg steps, not 12.5 in 2.5 kg steps
    assert stats.deload_weight(20.0, 70, stats.resolve_increment(None, True)) == 13.75


def test_deload_weight_leaves_a_bodyweight_set_alone():
    assert stats.deload_weight(0.0, 70, 2.5) == 0.0


def test_deload_weight_never_floors_a_light_weight_to_zero():
    # 2.5 * 0.70 = 1.75 -> would floor to 0.0; one increment is the minimum.
    assert stats.deload_weight(2.5, 70, 2.5) == 2.5
    assert stats.deload_weight(1.25, 70, 1.25) == 1.25


def test_deload_weight_preserves_the_shape_of_a_ramped_session():
    session = [80.0, 80.0, 75.0]
    assert [stats.deload_weight(w, 70, 2.5) for w in session] == [55.0, 55.0, 52.5]


def test_deload_weight_floors_onto_a_stack_machines_grid():
    # A 90 kg stack at 70 % is 63.0, which is exactly seven 9 kg plates. The
    # old 2.5 grid would have prescribed 62.5 -- a weight the machine cannot
    # produce at all.
    assert stats.deload_weight(90.0, 70, 9.0) == 63.0
    # 100 * 0.70 = 70.0 is not on the 9 kg grid: floor to 63.0, never 72.0.
    assert stats.deload_weight(100.0, 70, 9.0) == 63.0


def test_deload_weight_never_floors_below_one_stack_plate():
    # 9 * 0.70 = 6.3 -> would floor to 0.0; the lightest real position is 9.
    assert stats.deload_weight(9.0, 70, 9.0) == 9.0


def test_next_weight_adds_the_exercises_own_increment():
    assert stats._next_weight(81.0, 9.0) == 90.0
    assert stats._next_weight(80.0, 2.5) == 82.5


def test_session_report_suggests_the_exercises_own_increment():
    # Same stagnation setup as the 82.5 case above, but on a 9 kg stack: the
    # advice has to name a weight the machine can actually make.
    history = [perf([(72.0, 8)], weight_increment=9.0, started_at=day(0), session_id=1)]
    history += [
        perf([(63.0, 8)], weight_increment=9.0, started_at=day(7 * n), session_id=n + 1)
        for n in range(1, 4)
    ]
    current = [perf([(63.0, 8)], weight_increment=9.0, started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['advice'][0]['stuck_at'] == 63.0
    assert report['advice'][0]['suggested_weight'] == 72.0


def test_deload_row_does_not_count_as_a_session_without_a_pr():
    # Without the exclusion this is 2 sessions since the PR; the deload in the
    # middle is not a failed attempt at one.
    rows = [
        perf([(80.0, 8)], started_at=day(0)),
        perf([(85.0, 8)], started_at=day(7)),                   # the PR
        perf([(60.0, 8)], started_at=day(14), is_deload=True),  # deliberately light
        perf([(85.0, 8)], started_at=day(21)),
    ]
    assert stats.sessions_since_pr(rows) == 1


def test_a_run_of_deloads_cannot_push_an_exercise_to_stagniert():
    rows = [perf([(80.0, 8)], started_at=day(0)), perf([(85.0, 8)], started_at=day(7))]
    rows += [perf([(60.0, 8)], started_at=day(14 + 7 * n), is_deload=True) for n in range(6)]
    assert stats.exercise_state(rows) != 'stagniert'


def test_a_deload_session_cannot_set_a_record():
    # 200 kg logged in a deload session must not become the exercise's PR.
    rows = [perf([(80.0, 8)], started_at=day(0)),
            perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    assert stats._pr_weight(rows)['weight'] == 80.0
    assert stats._pr_e1rm(rows)['weight'] == 80.0


def test_a_deload_row_is_not_the_baseline_a_later_set_is_judged_against():
    # The direction that actually depends on the filter: a heavy deload must
    # not BLOCK a real record. Asserting False here could never discriminate --
    # filtering only shrinks the set that max() runs over, so anything true
    # before the filter stays true after it.
    prior = [perf([(80.0, 8)], started_at=day(0)),
             perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    assert stats.is_new_best(85.0, 8, prior) is True


def test_is_new_best_is_false_when_only_deload_history_exists():
    # No real history to beat -- the same "a first attempt isn't a record"
    # rule the empty case already has.
    prior = [perf([(60.0, 8)], started_at=day(0), is_deload=True)]
    assert stats.is_new_best(200.0, 8, prior) is False


def test_stall_report_ignores_deload_sessions():
    rows = [perf([(80.0, 8)], started_at=day(0)), perf([(85.0, 8)], started_at=day(7))]
    rows += [perf([(60.0, 8)], started_at=day(14 + 7 * n), is_deload=True) for n in range(6)]
    assert stats.stall_report({1: rows}) == []


def test_exercise_state_is_neu_when_every_row_is_a_deload():
    rows = [perf([(60.0, 8)], started_at=day(0), is_deload=True),
            perf([(60.0, 8)], started_at=day(7), is_deload=True)]
    assert stats.exercise_state(rows) == 'neu'


def test_session_report_excludes_deloads_from_the_volume_average():
    current = [perf([(80.0, 10)], started_at=day(21))]                       # 800
    history = [
        perf([(80.0, 10)], started_at=day(0)),                               # 800
        perf([(40.0, 10)], started_at=day(7), is_deload=True),               # 400, ignored
    ]
    report = stats.session_report(current, history)
    assert report['exercises'][0]['avg_volume'] == 800.0
    assert report['exercises'][0]['volume_delta_pct'] == 0


def test_session_report_awards_no_record_when_the_session_is_a_deload():
    current = [perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    history = [perf([(80.0, 8)], started_at=day(0))]
    report = stats.session_report(current, history)
    assert report['records'] == []
    assert report['record_count'] == 0
    assert report['exercises'][0]['is_weight_pr'] is False


def test_session_report_gives_no_stagnation_advice_on_a_deload():
    current = [perf([(60.0, 8)], started_at=day(35), is_deload=True)]
    history = [perf([(85.0, 8)], started_at=day(0))]
    history += [perf([(80.0, 8)], started_at=day(7 * n)) for n in range(1, 5)]
    report = stats.session_report(current, history)
    assert report['advice'] == []
    assert report['exercises'][0]['verdict'] != 'stagniert'


def test_session_report_reports_its_own_deload_state():
    plain = stats.session_report([perf([(80.0, 8)])], [])
    assert plain['is_deload'] is False
    loaded = stats.session_report([perf([(80.0, 8)], is_deload=True)], [])
    assert loaded['is_deload'] is True


def test_session_report_on_an_empty_session_is_not_a_deload():
    assert stats.session_report([], [])['is_deload'] is False


def test_session_record_counts_ignores_deload_sessions():
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(200.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert stats.session_record_counts(rows) == {}


def test_exercise_progress_keeps_deload_rows_but_marks_them():
    rows = [perf([(80.0, 8)], started_at=day(0)),
            perf([(60.0, 8)], started_at=day(7), is_deload=True)]
    progress = stats.exercise_progress(rows)
    assert len(progress['table']) == 2
    # table is newest-first
    assert progress['table'][0]['is_deload'] is True
    assert progress['table'][1]['is_deload'] is False
    assert [point['is_deload'] for point in progress['series'][0]['points']] == [False, True]
    # ...but the deload still holds no record
    assert progress['pr_weight']['weight'] == 80.0


def test_exercise_progress_reports_the_last_non_deload_row():
    # Three rows so "newest non-deload" is distinguishable from "any
    # non-deload": an implementation returning the OLDEST would give 80.0.
    rows = [perf([(80.0, 8)], started_at=day(0)),
            perf([(85.0, 8)], started_at=day(7)),
            perf([(60.0, 8)], started_at=day(14), is_deload=True)]
    progress = stats.exercise_progress(rows)
    assert progress['table'][0]['is_deload'] is True          # newest overall
    assert progress['last_progression']['best_weight'] == 85.0


def test_exercise_progress_has_no_last_progression_when_only_deloads_exist():
    rows = [perf([(60.0, 8)], started_at=day(0), is_deload=True)]
    progress = stats.exercise_progress(rows)
    assert progress['last_progression'] is None
    assert progress['pr_weight'] is None
    assert progress['table'] != []      # the row is still reported


def stalled(exercise_id, name, last_trained):
    """One stall_report entry plus the history row that dates it."""
    entry = {'exercise_id': exercise_id, 'name': name, 'position': 1,
             'stuck_at': 80.0, 'since': last_trained, 'sessions_since_pr': 5}
    row = perf([(80.0, 8)], started_at=last_trained, exercise_id=exercise_id, name=name)
    return entry, row


def signal_input(count, last_trained_offsets=None, now=None):
    """Build (report, rows_by_exercise) for `count` stalled exercises."""
    now = now or DELOAD_NOW
    offsets = last_trained_offsets or [1] * count
    report, rows_by_exercise = [], {}
    for index, offset in enumerate(offsets, start=1):
        entry, row = stalled(index, 'Uebung {}'.format(index),
                             now - dt.timedelta(days=offset))
        report.append(entry)
        rows_by_exercise[index] = [row]
    return report, rows_by_exercise


DELOAD_NOW = dt.datetime(2026, 7, 28, 18, 0)


def test_deload_signal_fires_at_the_threshold():
    report, rows = signal_input(4)
    signal = stats.deload_signal(report, rows, DELOAD_NOW)
    assert signal is not None
    assert signal['count'] == 4
    assert len(signal['stalls']) == 4


def test_deload_signal_stays_quiet_below_the_threshold():
    report, rows = signal_input(3)
    assert stats.deload_signal(report, rows, DELOAD_NOW) is None


def test_deload_signal_ignores_exercises_not_trained_in_the_window():
    # Four stalls, but two are lifts abandoned months ago -- stagnating from
    # disuse, which says nothing about how recovered the lifter is.
    report, rows = signal_input(4, last_trained_offsets=[1, 3, 200, 300])
    assert stats.deload_signal(report, rows, DELOAD_NOW) is None


def test_deload_signal_counts_only_the_recently_trained_stalls():
    # Five stalls, four of them recent -- proves the filter SELECTS correctly,
    # not merely that it can suppress. The existing "ignores" test drops below
    # the threshold either way, so it cannot show which entries survived.
    report, rows = signal_input(5, last_trained_offsets=[1, 2, 3, 4, 200])
    signal = stats.deload_signal(report, rows, DELOAD_NOW)
    assert signal['count'] == 4
    assert 5 not in [entry['exercise_id'] for entry in signal['stalls']]


def test_deload_signal_is_suppressed_soon_after_a_deload():
    report, rows = signal_input(4)
    assert stats.deload_signal(report, rows, DELOAD_NOW,
                               last_deload_at=DELOAD_NOW - dt.timedelta(days=7)) is None


def test_deload_signal_fires_exactly_at_the_suppression_boundary():
    # DELOAD_SUPPRESSION_DAYS days out is NOT suppressed: the implementation
    # checks `(now - last_deload_at).days < suppression_days`, so equality
    # falls through to firing rather than being suppressed.
    report, rows = signal_input(4)
    boundary = DELOAD_NOW - dt.timedelta(days=stats.DELOAD_SUPPRESSION_DAYS)
    assert stats.deload_signal(report, rows, DELOAD_NOW,
                               last_deload_at=boundary) is not None


def test_deload_signal_fires_again_once_the_suppression_window_passes():
    report, rows = signal_input(4)
    assert stats.deload_signal(report, rows, DELOAD_NOW,
                               last_deload_at=DELOAD_NOW - dt.timedelta(days=22)) is not None


def test_deload_signal_fires_for_someone_who_has_never_deloaded():
    report, rows = signal_input(4)
    assert stats.deload_signal(report, rows, DELOAD_NOW, last_deload_at=None) is not None


def test_weekly_tonnage_marks_a_week_containing_a_deload():
    now = dt.datetime(2026, 7, 29, 18, 0)          # a Wednesday
    rows = [
        perf([(80.0, 10)], started_at=now - dt.timedelta(days=1)),
        perf([(60.0, 10)], started_at=now, is_deload=True),
        perf([(80.0, 10)], started_at=now - dt.timedelta(days=8)),
    ]
    weeks = stats.weekly_tonnage(rows, now)
    assert weeks[-1]['has_deload'] is True
    assert weeks[-2]['has_deload'] is False
    # the volume itself still totals everything
    assert weeks[-1]['volume'] == 800.0 + 600.0


def test_weekly_tonnage_marks_an_empty_week_as_no_deload():
    now = dt.datetime(2026, 7, 29, 18, 0)
    weeks = stats.weekly_tonnage([], now)
    assert all(week['has_deload'] is False for week in weeks)


def test_resolve_increment_falls_back_to_the_plate_pair():
    assert stats.resolve_increment(None, False) == 2.5


def test_resolve_increment_halves_the_fallback_for_unilateral_work():
    # One side at a time, so half the smallest pair of plates.
    assert stats.resolve_increment(None, True) == 1.25


def test_resolve_increment_takes_an_explicit_value_literally():
    # A selectorised stack moves in 9 kg steps; nothing about 2.5 applies.
    assert stats.resolve_increment(9.0, False) == 9.0


def test_resolve_increment_does_not_halve_an_explicit_unilateral_value():
    # The discriminating case for the whole feature: the live screen labels
    # this field "kg je Seite", so 2.0 already IS the per-side step. Halving it
    # would dial 1.0 kg on a pair of dumbbells that only exist in 2 kg jumps.
    assert stats.resolve_increment(2.0, True) == 2.0


def test_resolve_increment_treats_zero_as_unset():
    # A step of zero would freeze the stepper, so it collapses to the fallback
    # rather than being honoured.
    assert stats.resolve_increment(0, False) == 2.5
    assert stats.resolve_increment(0, True) == 1.25
