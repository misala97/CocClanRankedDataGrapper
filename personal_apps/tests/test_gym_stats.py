"""Tests for features.gym.stats -- pure functions, so no app context, no
database, and no fixtures beyond plain data."""
import datetime as dt

from features.gym import stats


def perf(sets, position=1, started_at=None, is_unilateral=False,
         exercise_id=1, name='Bankdruecken', muscle_group='Brust', session_id=1,
         is_deload=False):
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
    assert stats.deload_weight(80.0, 70, False) == 55.0


def test_deload_weight_rounds_down_not_to_nearest():
    # 100 * 0.70 = 70.0 exactly; 90 * 0.70 = 63.0 -> 62.5, not 65.0
    assert stats.deload_weight(100.0, 70, False) == 70.0
    assert stats.deload_weight(90.0, 70, False) == 62.5


def test_deload_weight_uses_the_half_step_for_unilateral():
    # 20 * 0.70 = 14.0 -> 13.75 in 1.25 kg steps, not 12.5 in 2.5 kg steps
    assert stats.deload_weight(20.0, 70, True) == 13.75


def test_deload_weight_leaves_a_bodyweight_set_alone():
    assert stats.deload_weight(0.0, 70, False) == 0.0


def test_deload_weight_never_floors_a_light_weight_to_zero():
    # 2.5 * 0.70 = 1.75 -> would floor to 0.0; one increment is the minimum.
    assert stats.deload_weight(2.5, 70, False) == 2.5
    assert stats.deload_weight(1.25, 70, True) == 1.25


def test_deload_weight_preserves_the_shape_of_a_ramped_session():
    session = [80.0, 80.0, 75.0]
    assert [stats.deload_weight(w, 70, False) for w in session] == [55.0, 55.0, 52.5]
