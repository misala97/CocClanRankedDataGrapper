"""Tests for features.gym.stats -- pure functions, so no app context, no
database, and no fixtures beyond plain data."""
import datetime as dt

import pytest

from features.gym import stats


def perf(sets, position=1, started_at=None, is_unilateral=False,
         exercise_id=1, name='Bankdruecken', muscle_group='Brust', session_id=1,
         is_deload=False, weight_increment=None, stack_kg=None):
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
        stack_kg=stack_kg,
    )


def test_performed_exercise_defaults_to_not_deload():
    assert perf([(80.0, 8)]).is_deload is False


@pytest.mark.parametrize('weight, text', [
    (80.0, '80,0'), (62.5, '62,5'), (11.25, '11,25'), (102.75, '102,75'),
    (11.125, '11,12'), (0.0, '0,0'),
])
def test_a_weight_reads_to_the_hundredth_the_app_keeps(weight, text):
    """What the client's format.kg says (G-146): '%.1f' printed a logged
    11,25 as 11,2 while the stepper said 11,3. Half-even, as there."""
    assert stats.kg_text(weight) == text


def test_a_rows_sets_read_with_the_hundredth():
    assert stats._sets_display(perf([(11.25, 8), (11.25, 7), (10.0, 9)])) == (
        '11,25 × 8 · 11,25 × 7 · 10,0 × 9')


def test_performed_exercise_carries_the_deload_flag():
    assert perf([(80.0, 8)], is_deload=True).is_deload is True


def test_performed_exercise_defaults_stack_kg_to_none():
    # Built directly, bypassing perf()'s own default -- perf() now always
    # passes stack_kg=, so calling it here would test the helper's default
    # rather than the dataclass's own.
    row = stats.PerformedExercise(
        exercise_id=1, name='Bankdruecken', muscle_group='Brust',
        is_unilateral=False, position=1, session_id=1,
        started_at=dt.datetime(2020, 1, 1), sets=((80.0, 8),),
    )
    assert row.stack_kg is None


def test_performed_exercise_carries_stack_kg():
    assert perf([(80.0, 8)], stack_kg=(5, 13, 21)).stack_kg == (5, 13, 21)


def test_epley_1rm_at_one_rep_is_the_weight_itself():
    # D3: a single IS a one-rep max; the formula read 103,3 for 100 × 1.
    assert stats.epley_1rm(100.0, 1) == 100.0


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
    assert stats.best_e1rm(row) == stats.judged_e1rm(90.0, 12)


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


def test_sessions_since_pr_counts_from_the_last_record_in_any_slot():
    """B3 review: the count ran per slot, so a climb in slot 3 below the
    lift's own best read as a fresh PR. A record is exercise-wide (D3), and
    so is the drought: nothing here beat the debut."""
    rows = [
        perf([(85.0, 8)], position=1, started_at=day(0)),
        perf([(70.0, 8)], position=3, started_at=day(7)),
        perf([(72.5, 8)], position=3, started_at=day(14)),
    ]
    assert stats.sessions_since_pr(rows) == 2


def test_a_deload_record_ends_the_drought_and_a_deload_never_adds_to_it():
    """B3 review: [100, 100, 100, deload 110] read "Rekord" beside
    "2 Einheiten ohne PR". The deload workout set a record (D3 b-A), so the
    count restarts there; a later deload is no failed attempt."""
    rows = [perf([(100.0, 5)], started_at=day(i), session_id=i + 1) for i in range(3)]
    rows.append(perf([(110.0, 5)], started_at=day(7), session_id=4, is_deload=True))
    assert stats.exercise_state(rows) == 'rekord'
    assert stats.sessions_since_pr(rows) == 0
    rows.append(perf([(90.0, 5)], started_at=day(14), session_id=5, is_deload=True))
    assert stats.sessions_since_pr(rows) == 0
    rows.append(perf([(100.0, 5)], started_at=day(21), session_id=6))
    assert stats.sessions_since_pr(rows) == 1


def test_ties_after_a_deload_record_never_read_as_a_stall():
    """B3 review: five ties then a deload record flared "Neuer
    e1RM-Rekord", and the next workout's live line said "Stagniert"."""
    rows = [perf([(100.0, 5)], started_at=day(i), session_id=i + 1) for i in range(6)]
    assert stats.exercise_state(rows) == 'stagniert'
    rows.append(perf([(110.0, 5)], started_at=day(10), session_id=7, is_deload=True))
    assert stats.exercise_state(rows) == 'rekord'
    assert stats.sessions_since_pr(rows) == 0
    assert stats.stall_report({1: rows}) == []


def test_a_workout_with_no_judged_set_adds_nothing_to_the_drought():
    """Sets above 12 reps are shown, never judged (D3 c-A): 8 x 15 was no
    attempt at the number the drought counts by."""
    rows = [
        perf([(10.0, 10)], started_at=day(0), session_id=1),
        perf([(10.0, 10)], started_at=day(7), session_id=2),
        perf([(8.0, 15)], started_at=day(14), session_id=3),
    ]
    assert stats.sessions_since_pr(rows) == 1


def test_a_bodyweight_set_is_judged_by_nothing():
    """0 kg estimates 0 kg, which is no estimate (G-038): no record, no
    drought, no stall. Reps climbing at bodyweight read "Seit 5 Workouts ohne
    Rekord" and "Stagniert" -- under "Noch kein Rekord" on the exercise page."""
    assert stats.judged_e1rm(0.0, 10) is None
    assert stats.judged_e1rm(2.5, 10) == 3.3
    rows = [perf([(0.0, 8 + i)], started_at=day(7 * i), session_id=i + 1) for i in range(6)]
    assert stats.drought(rows) is None
    assert stats.sessions_since_pr(rows) is None
    assert stats.exercise_state(rows) is None
    assert stats.stall_report({1: rows}) == []


def test_the_first_weighted_workout_after_bodyweight_ones_is_its_debut():
    """Nothing before it was an estimate, so it beat nothing."""
    rows = [perf([(0.0, 12)], started_at=day(0), session_id=1),
            perf([(0.0, 12)], started_at=day(7), session_id=2),
            perf([(5.0, 10)], started_at=day(14), session_id=3)]
    assert stats.record_marks(rows) == {}
    assert stats.sessions_since_pr(rows) is None


def test_the_stall_report_quotes_the_newest_attempt_and_the_last_record():
    """B3 review: `stuck_at` came from the last row of the slot, a
    15-rep row included, and `since` from the slot's peak."""
    rows = [
        perf([(10.0, 10)], started_at=day(0), session_id=1),
        perf([(11.0, 10)], started_at=day(7), session_id=2),      # the record
        *[perf([(10.0, 10)], started_at=day(14 + 7 * i), session_id=3 + i) for i in range(4)],
        perf([(8.0, 15)], started_at=day(50), session_id=9),
    ]
    [entry] = stats.stall_report({1: rows})
    assert entry['sessions_since_pr'] == 4
    assert entry['stuck_at'] == 10.0
    assert entry['since'] == day(7)
    assert entry['last_record_at'] == day(7)


def test_the_stall_report_says_when_a_lift_never_set_a_record():
    """Start's "Steht still" says "letzter am D" -- and of a lift whose debut
    is still its best, that there was none: its count runs from the debut."""
    rows = [perf([(11.0, 10)], started_at=day(0), session_id=1),
            *[perf([(10.0, 10)], started_at=day(7 * (i + 1)), session_id=2 + i) for i in range(4)]]
    [entry] = stats.stall_report({1: rows})
    assert entry['sessions_since_pr'] == 4
    assert entry['last_record_at'] is None
    assert entry['since'] == day(0)


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


def test_exercise_progress_is_the_whole_exercise_newest_first():
    # D9: no slot lenses the log, the record or the state -- the Rekordtreppe
    # is the one part a pill can.
    rows = [
        perf([(80.0, 8)], position=1, started_at=day(0), session_id=1),
        perf([(70.0, 8), (70.0, 7)], position=3, started_at=day(7), session_id=2),
        perf([(82.5, 6)], position=1, started_at=day(14), session_id=3),
    ]
    result = stats.exercise_progress(rows)

    assert set(result) == {'table', 'pr_e1rm', 'state', 'sessions_since_pr'}
    assert [(entry['session_id'], entry['position']) for entry in result['table']] == [
        (3, 1), (2, 3), (1, 1)]
    assert result['table'][1] == {
        'session_id': 2, 'started_at': day(7), 'position': 3, 'is_deload': False,
        'is_record': False, 'sets': [{'weight': 70.0, 'reps': 8}, {'weight': 70.0, 'reps': 7}],
        'volume': 1050.0, 'e1rm': 88.7,
    }
    # 80 x 8 estimates 101,3 -- above the heavier 82,5 x 6 at 99,0. The
    # debut's, so no record: nothing came before it (D3).
    assert (result['pr_e1rm']['weight'], result['pr_e1rm']['e1rm']) == (80.0, 101.3)
    assert result['pr_e1rm']['is_record'] is False


def test_the_pages_chip_judges_steigend_in_the_lifts_usual_slot_as_the_list_does():
    # routes.catalogue lenses "Steigend" by dominant_position; the page read
    # across slots, so one lift was "Steigend" in the list and had no chip on
    # its page (I2 review). Slot 1 rose, 82 over 80; across slots 81 fell.
    rows = [perf([(90.0, 1)], position=1, started_at=day(0), session_id=1),
            perf([(80.0, 1)], position=1, started_at=day(7), session_id=2),
            perf([(82.0, 1)], position=1, started_at=day(14), session_id=3),
            perf([(81.0, 1)], position=3, started_at=day(21), session_id=4)]
    assert stats.exercise_state(rows) is None
    assert stats.exercise_progress(rows)['state'] == 'steigend' \
        == stats.exercise_state(rows, position=stats.dominant_position(rows))


def test_exercise_progress_on_an_exercise_with_no_history_is_empty_not_broken():
    result = stats.exercise_progress([])
    assert result == {'table': [], 'pr_e1rm': None, 'state': 'neu', 'sessions_since_pr': None}


def test_session_report_totals_and_flags_an_e1rm_record():
    # A heavier set is an e1RM record, the only kind there is (D3).
    current = [perf([(85.0, 8)], started_at=day(21), session_id=9)]
    history = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(80.0, 8)], started_at=day(7), session_id=2),
    ]
    report = stats.session_report(current, history)

    assert report['total_sets'] == 1
    assert report['total_volume'] == 680.0
    assert report['record_count'] == 1
    assert report['records'][0]['kind'] == 'e1rm'
    assert report['records'][0]['value'] == 107.7
    assert report['records'][0]['previous'] == 101.3
    # The first workout that reached the bar, not the later tie of it.
    assert report['records'][0]['previous_at'] == day(0)
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


def test_session_record_counts_keeps_a_record_a_later_session_overtook():
    # D3 a-A: a record beats every EARLIER session and stays one. The old
    # "beats every OTHER session" rule took session 2's badge back the day
    # session 3 beat it (G-126: Verlauf 0/1/11/2 against Statistik 8/46/41/3).
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(85.0, 8)], started_at=day(7), session_id=2),
        perf([(90.0, 8)], started_at=day(14), session_id=3),
    ]
    counts = stats.session_record_counts(rows)

    assert counts.get(1, 0) == 0
    assert counts.get(2, 0) == 1
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
    # 1RM than 5 reps at 100 -- it registers on the e1RM alone. Session 1
    # does not: weight is no kind of record (D3), and a first session has
    # nothing to beat.
    rows = [
        perf([(100.0, 5)], started_at=day(0), session_id=1),   # heaviest weight
        perf([(90.0, 12)], started_at=day(7), session_id=2),   # lighter but a higher e1RM
    ]
    assert stats.best_e1rm(rows[1]) > stats.best_e1rm(rows[0])
    assert stats.best_weight(rows[1]) < stats.best_weight(rows[0])

    counts = stats.session_record_counts(rows)

    assert counts.get(2, 0) == 1
    assert counts.get(1, 0) == 0


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


def test_session_report_counts_a_duplicate_slot_session_like_the_bulk_does():
    # The 6-vs-7 bug (found 2026-08-11): a session logging one exercise in
    # TWO slots, both beating every other session, earned two records from
    # session_report (one per row) but one from session_record_counts
    # (slots combined) -- so the debrief said "7 neue Rekorde" while Heute
    # and Verlauf said "6 Rekorde" for the same session. One exercise is one
    # performance: both must say one.
    rows = [
        perf([(70.0, 8)], started_at=day(0), session_id=1, position=1),
        perf([(80.0, 8)], started_at=day(7), session_id=2, position=1),
        perf([(95.0, 8)], started_at=day(7), session_id=2, position=4),
    ]
    bulk = stats.session_record_counts(rows)
    report = stats.session_report(
        [row for row in rows if row.session_id == 2],
        [row for row in rows if row.session_id != 2])

    assert bulk.get(2, 0) == 1
    assert report['record_count'] == 1


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
    # The discriminating case for DIRECTION: 81 * 0.70 = 56.7. Stepping down
    # from 81 in 2.5 kg increments, 10 steps lands on 56.0 and 9 steps on 58.5
    # -- heavier than the lift's own prescription implies. The result must be
    # the one at or below 56.7. Every other case in this file has a remainder
    # below half a step, where the two directions agree, so only this one
    # proves it.
    assert stats.deload_weight(81.0, 70, 2.5) == 56.0


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
    # A 90 kg stack at 70 % is 63.0, which is exactly three 9 kg plates down.
    # The old 2.5 grid would have prescribed 62.5 -- a weight the machine
    # cannot produce at all.
    assert stats.deload_weight(90.0, 70, 9.0) == 63.0
    # 100 * 0.70 = 70.0. Stepping down from 100, four plates lands on 64.0;
    # three would give 73.0, above the prescription.
    assert stats.deload_weight(100.0, 70, 9.0) == 64.0


def test_deload_weight_stays_on_an_offset_stacks_own_grid():
    """The real Seated Row: an 8 kg stack sitting on a 5 kg carriage, so its
    positions are 5, 13, ... 53, 61, 69 -- none of them a multiple of 8.

    Counting increments from zero prescribes 48, which that machine cannot
    make. The prescription has to be reachable from the weight the lifter is
    actually on, which is the only position known to exist.
    """
    assert stats.deload_weight(69.0, 70, 8.0) == 45.0
    assert stats.deload_weight(61.0, 70, 8.0) == 37.0


def test_deload_weight_never_floors_below_one_stack_plate():
    # 9 * 0.70 = 6.3 -> would floor to 0.0; the lightest real position is 9.
    assert stats.deload_weight(9.0, 70, 9.0) == 9.0


def test_snap_to_stack_returns_the_weight_when_there_are_no_steps():
    """Everything in this gym steps evenly, so this is the path almost every
    exercise takes: no stops recorded, increment logic untouched."""
    assert stats.snap_to_stack(42.0, None, 'down') == 42.0
    assert stats.snap_to_stack(42.0, [], 'up') == 42.0


def test_snap_to_stack_lands_on_a_real_stop():
    steps = [5, 13, 21, 29, 37, 45]
    assert stats.snap_to_stack(42.0, steps, 'down') == 37
    assert stats.snap_to_stack(42.0, steps, 'up') == 45
    assert stats.snap_to_stack(37.0, steps, 'down') == 37, 'an exact stop stays put'
    assert stats.snap_to_stack(37.0, steps, 'up') == 37


def test_snap_to_stack_clamps_at_the_ends():
    steps = [5, 13, 21]
    assert stats.snap_to_stack(2.0, steps, 'down') == 5, 'below the lightest stop'
    assert stats.snap_to_stack(99.0, steps, 'up') == 21, 'above the heaviest'


def test_snap_to_stack_rejects_a_direction_that_is_not_down_or_up():
    # Anything other than the literal 'down' silently fell through to the
    # 'up' branch -- for a deload that is exactly the direction its sibling
    # deload_weight() calls "the one direction that defeats the point".
    with pytest.raises(ValueError):
        stats.snap_to_stack(42.0, [5, 13, 21], 'DOWN')


def test_deload_lands_on_a_real_stop_when_steps_are_known():
    """The bug this guards: 70 % of 69 on an 8 kg stack sitting on a 5 kg
    carriage is 48.3, and 48 is not a position the machine has."""
    steps = [5, 13, 21, 29, 37, 45, 53, 61, 69, 77]
    weight = stats.deload_weight(69.0, 70, 8, stack_kg=steps)
    assert weight in steps
    assert weight <= 69 * 0.7 + 0.001


def test_deload_snap_overrides_a_grid_position_the_stack_does_not_have():
    """The case the previous test cannot tell apart from plain anchoring:
    here the working weight (50) is itself a real stop, but the anchoring
    grid (stepping down in 6s from 50) lands on 32 -- not one of this
    machine's genuinely uneven stops (5, 12, 18, 29, 33, 50). Without the
    snap this prescribes a weight nobody can select; with it, the answer is
    the nearest stop at or below the grid's own 32, which is 29.
    """
    steps = [5, 12, 18, 29, 33, 50]
    assert stats.deload_weight(50.0, 70, 6, stack_kg=steps) == 29


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


def test_session_report_suggests_a_real_stack_stop_not_an_invented_position():
    # Same stagnation setup, but on a stack with uneven stops: weight + increment
    # (63 + 9 = 72) happens to land on a real stop here by coincidence, so use
    # a stack where the naive sum is NOT a stop -- 63 + 9 = 72 is not one of
    # these steps, and the honest "go heavier" answer is the nearest stop AT
    # OR ABOVE it, 77.
    steps = (5, 13, 21, 29, 37, 45, 53, 61, 69, 77)
    history = [perf([(72.0, 8)], weight_increment=9.0, stack_kg=steps, started_at=day(0), session_id=1)]
    history += [
        perf([(63.0, 8)], weight_increment=9.0, stack_kg=steps, started_at=day(7 * n), session_id=n + 1)
        for n in range(1, 4)
    ]
    current = [perf([(63.0, 8)], weight_increment=9.0, stack_kg=steps, started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['advice'][0]['stuck_at'] == 63.0
    assert report['advice'][0]['suggested_weight'] == 77.0


def test_session_report_drops_advice_when_already_topped_out_on_the_stack():
    """Same stagnation setup again, but stuck on the HEAVIEST stop this stack
    has. snap_to_stack('up') clamps a jump past the top back down to it, so
    the naive advice would tell the lifter to "go heavier" and then name the
    exact weight they are already stuck at -- worse than no advice. The right
    answer is no advice entry at all, not a same-number one."""
    steps = (5, 13, 21, 29, 37, 45, 53, 61, 69, 77)
    history = [
        perf([(77.0, 8)], weight_increment=9.0, stack_kg=steps, started_at=day(7 * n), session_id=n + 1)
        for n in range(4)
    ]
    current = [perf([(77.0, 8)], weight_increment=9.0, stack_kg=steps, started_at=day(28), session_id=9)]
    report = stats.session_report(current, history)

    assert report['exercises'][0]['verdict'] == 'stagniert'
    assert report['advice'] == []


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


def test_a_deload_session_can_hold_the_best():
    # D3 b-A: a record is a record, deload or not. (It was 'must not become
    # the PR'; the heaviest set is a fact either way.)
    rows = [perf([(80.0, 8)], started_at=day(0)),
            perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    assert stats._pr_e1rm(rows)['weight'] == 200.0


def test_a_deload_row_is_a_bar_like_any_other():
    prior = [perf([(80.0, 8)], started_at=day(0)),
             perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    assert stats.record_detail(85.0, 8, prior) is None


def test_deload_history_alone_is_a_bar_too():
    prior = [perf([(60.0, 8)], started_at=day(0), is_deload=True)]
    assert stats.record_detail(200.0, 8, prior)['previous'] == 76.0


def test_record_detail_names_what_it_beat_and_when():
    prior = [perf([(77.5, 8)], started_at=day(0)),
             perf([(80.0, 8)], started_at=day(7)),
             perf([(80.0, 6)], started_at=day(14))]
    detail = stats.record_detail(82.5, 7, prior)
    assert detail['kind'] == 'e1rm'
    assert detail['value'] == 101.8
    assert detail['previous'] == 101.3
    # The session that HELD the best, not the most recent one.
    assert detail['previous_at'] == day(7)


def test_record_detail_counts_more_reps_at_the_same_weight():
    prior = [perf([(80.0, 8)], started_at=day(0))]
    detail = stats.record_detail(80.0, 10, prior)
    assert detail['kind'] == 'e1rm'
    assert detail['previous'] == stats.judged_e1rm(80.0, 8)


def test_record_detail_is_none_when_nothing_was_beaten():
    prior = [perf([(80.0, 8)], started_at=day(0))]
    assert stats.record_detail(80.0, 8, prior) is None
    assert stats.record_detail(75.0, 5, prior) is None
    # Heavier, but a lower e1RM: weight is no kind of record (D3).
    assert stats.record_detail(90.0, 2, prior) is None


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


def test_session_report_keeps_the_records_of_a_deload_session():
    # G-078: marking the workout a deload took back records already
    # celebrated in it (D3 b-A).
    current = [perf([(200.0, 8)], started_at=day(7), is_deload=True)]
    history = [perf([(80.0, 8)], started_at=day(0))]
    report = stats.session_report(current, history)
    assert report['record_count'] == 1
    assert report['exercises'][0]['is_record'] is True
    assert report['exercises'][0]['verdict'] == 'rekord'


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


def test_session_record_counts_counts_deload_sessions_like_any_other():
    rows = [
        perf([(80.0, 8)], started_at=day(0), session_id=1),
        perf([(200.0, 8)], started_at=day(7), session_id=2, is_deload=True),
    ]
    assert stats.session_record_counts(rows) == {2: 1}


def test_exercise_progress_keeps_deload_rows_but_marks_them():
    rows = [perf([(80.0, 8)], started_at=day(0)),
            perf([(60.0, 8)], started_at=day(7), is_deload=True)]
    progress = stats.exercise_progress(rows)
    assert len(progress['table']) == 2
    # table is newest-first
    assert progress['table'][0]['is_deload'] is True
    assert progress['table'][1]['is_deload'] is False


def test_exercise_progress_of_deloads_only_still_has_its_best():
    # The best set is a fact, deload or not (D3).
    progress = stats.exercise_progress([perf([(60.0, 8)], started_at=day(0), is_deload=True)])
    assert progress['pr_e1rm']['weight'] == 60.0
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


# --- rest timing -----------------------------------------------------------


def _at(minute, second=0):
    import datetime as dt
    return dt.datetime(2026, 8, 3, 18, minute, second)


def test_rest_gaps_measures_the_interval_between_consecutive_sets():
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(0), 150), (_at(3), 150), (_at(5), 150)])
    assert [actual for actual, _ in gaps] == [180, 120]


def test_rest_gaps_sorts_by_when_the_set_landed():
    """Callers hand over whatever order the rows came back in."""
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(5), 150), (_at(0), 150), (_at(3), 150)])
    assert [actual for actual, _ in gaps] == [180, 120]


def test_rest_gaps_takes_the_planned_time_from_the_set_that_ended_the_gap():
    """You finish a set of Bankdrücken and rest Bankdrücken's time -- so the
    earlier set of each pair supplies the plan, not the one you are about to do."""
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(0), 150), (_at(3), 90)])
    assert gaps == [(180, 150)]


def test_rest_gaps_drops_an_interruption():
    """A phone call between sets is not rest. Over the cap it is not counted at
    all, rather than counted and averaged away."""
    from features.gym import stats
    gaps = stats.rest_gaps([(_at(0), 150), (_at(3), 150), (_at(30), 150)])
    assert [actual for actual, _ in gaps] == [180]


def test_rest_gaps_of_a_single_set_is_empty():
    """The first completed set of a session has nothing before it."""
    from features.gym import stats
    assert stats.rest_gaps([(_at(0), 150)]) == []
    assert stats.rest_gaps([]) == []


class TestE1rmTrend:
    """How fast the e1RM moves (D9 A), in kg per 30 days. It replaced the
    chart's date promise, and says a falling pace too."""

    NOW = dt.datetime(2026, 8, 11, 12, 0)

    def _rows(self, *values, spacing_days=7, end_days_ago=3, deloads=()):
        """One workout per value, `spacing_days` apart, the newest
        `end_days_ago` before NOW: a single, whose e1RM is its weight."""
        newest = self.NOW - dt.timedelta(days=end_days_ago)
        count = len(values)
        return [perf([(value, 1)], session_id=i + 1, is_deload=i in deloads,
                     started_at=newest - dt.timedelta(days=spacing_days * (count - 1 - i)))
                for i, value in enumerate(values)]

    def test_says_kg_a_month_off_the_least_squares_line(self):
        # +1 kg a week is 30/7 kg a month.
        assert stats.e1rm_trend(self._rows(80.0, 81.0, 82.0, 83.0), self.NOW) \
            == {'per_month': 4.3, 'workouts': 4}

    def test_one_hot_day_does_not_make_the_pace(self):
        # A line through all four, not the last step: 83 -> 90 alone is 30 kg a month.
        trend = stats.e1rm_trend(self._rows(80.0, 81.0, 82.0, 90.0), self.NOW)
        assert trend == {'per_month': 13.3, 'workouts': 4}

    def test_says_a_falling_pace_too(self):
        assert stats.e1rm_trend(self._rows(84.0, 83.0, 82.0, 81.0), self.NOW)['per_month'] == -4.3

    def test_reads_only_the_newest_six(self):
        # Six flat old workouts would flatten the line if they were read.
        rows = self._rows(*[60.0] * 6, 80.0, 81.0, 82.0, 83.0, 84.0, 85.0)
        assert stats.e1rm_trend(rows, self.NOW) == {'per_month': 4.3, 'workouts': 6}

    def test_silent_below_four_workouts(self):
        assert stats.e1rm_trend(self._rows(80.0, 82.0, 84.0), self.NOW) is None

    def test_silent_over_less_than_two_weeks(self):
        # Four workouts in six days said "+37,5 kg im Monat" (I2 review).
        rows = self._rows(100.0, 102.5, 105.0, 107.5, spacing_days=2)
        assert stats.e1rm_trend(rows, self.NOW) is None

    def test_reaches_back_past_six_until_two_weeks_are_read(self):
        # Six workouts two days apart span ten days; eight span fourteen.
        rows = self._rows(*[70.0 + i for i in range(10)], spacing_days=2)
        assert stats.e1rm_trend(rows, self.NOW) == {'per_month': 15.0, 'workouts': 8}

    def test_reaches_back_no_further_than_twelve(self):
        # Twelve daily workouts span eleven days: still no two weeks, no pace.
        rows = self._rows(*[70.0 + i for i in range(20)], spacing_days=1)
        assert stats.e1rm_trend(rows, self.NOW) is None

    def test_silent_once_the_newest_is_past_the_window(self):
        # The pace of a lifter who stopped is history, not a pace.
        assert stats.e1rm_trend(self._rows(80.0, 81.0, 82.0, 83.0, end_days_ago=28), self.NOW)
        assert stats.e1rm_trend(self._rows(80.0, 81.0, 82.0, 83.0, end_days_ago=29), self.NOW) is None

    def test_leaves_deloads_out(self):
        rows = self._rows(80.0, 81.0, 60.0, 82.0, 83.0, deloads=(2,))
        assert stats.e1rm_trend(rows, self.NOW)['workouts'] == 4

    def test_leaves_out_what_estimates_nothing(self):
        # Past 12 reps no set is judged, and a bodyweight set estimates 0 kg
        # (G-038): neither is a point on the line.
        rows = self._rows(80.0, 81.0, 82.0, 83.0) + [
            perf([(90.0, 15)], session_id=9, started_at=self.NOW - dt.timedelta(days=2)),
            perf([(0.0, 10)], session_id=10, started_at=self.NOW - dt.timedelta(days=1)),
        ]
        assert stats.e1rm_trend(rows, self.NOW) == {'per_month': 4.3, 'workouts': 4}

    def test_a_bodyweight_lift_has_no_pace(self):
        rows = [perf([(0.0, 8 + i)], session_id=i + 1,
                     started_at=self.NOW - dt.timedelta(days=7 * (4 - i))) for i in range(5)]
        assert stats.e1rm_trend(rows, self.NOW) is None

    def test_two_slots_of_one_workout_are_one_point(self):
        rows = self._rows(80.0, 81.0, 82.0, 83.0)
        rows.append(perf([(70.0, 1)], position=3, session_id=4, started_at=rows[-1].started_at))
        assert stats.e1rm_trend(rows, self.NOW) == {'per_month': 4.3, 'workouts': 4}

    def test_hands_over_the_points_it_fits(self):
        # Start draws them beside the pace (M3): the line and the number
        # are one reading, so they are the same workouts.
        rows = self._rows(*[60.0] * 2, 80.0, 81.0, 82.0, 83.0, 84.0, 85.0)
        assert stats.trend_points(rows, self.NOW) == [
            (row.started_at, value) for row, value in zip(rows[2:], (80.0, 81.0, 82.0, 83.0, 84.0, 85.0))]
        assert stats.trend_points(self._rows(80.0, 82.0, 84.0), self.NOW) is None


class TestProgressReport:
    """Start's "Fortschritt" (M3, D7-C): the lifts going up, ranked by the
    exercise page's pace, each with the workouts that pace was fitted through
    and its best."""

    NOW = dt.datetime(2026, 8, 11, 12, 0)

    def _rows(self, *values, exercise_id=1, name='Bankdruecken', end_days_ago=3):
        """One weekly single per value, the newest `end_days_ago` before NOW."""
        newest = self.NOW - dt.timedelta(days=end_days_ago)
        return [perf([(value, 1)], exercise_id=exercise_id, name=name,
                     session_id=exercise_id * 100 + i,
                     started_at=newest - dt.timedelta(days=7 * (len(values) - 1 - i)))
                for i, value in enumerate(values)]

    def test_lists_a_rising_lift_with_its_points_and_its_best(self):
        rows = self._rows(80.0, 81.0, 82.0, 83.0)
        assert stats.progress_report({1: rows}, set(), self.NOW) == {'with_trend': 1, 'up': [{
            'exercise_id': 1, 'name': 'Bankdruecken', 'per_month': 4.3, 'workouts': 4,
            'points': [{'started_at': row.started_at, 'e1rm': row.sets[0][0]} for row in rows],
            'best': {'e1rm': 83.0, 'started_at': rows[-1].started_at, 'is_record': True},
        }]}

    def test_ranks_the_fastest_first_and_breaks_a_tie_by_name(self):
        report = stats.progress_report({
            1: self._rows(80.0, 81.0, 82.0, 83.0, exercise_id=1, name='Zug'),
            2: self._rows(80.0, 82.0, 84.0, 86.0, exercise_id=2, name='Presse'),
            3: self._rows(80.0, 81.0, 82.0, 83.0, exercise_id=3, name='Dips'),
        }, set(), self.NOW)
        assert [(lift['name'], lift['per_month']) for lift in report['up']] == [
            ('Presse', 8.6), ('Dips', 4.3), ('Zug', 4.3)]

    def test_leaves_a_stalled_lift_to_steht_still_though_its_line_rises(self):
        # A lift sits in one half at most: the exercise page hides the pace
        # of a stalled lift too (D9). It still has a pace, though: counted,
        # the lede says nothing goes up rather than that no lift has data yet.
        rows = self._rows(80.0, 81.0, 82.0, 83.0)
        assert stats.progress_report({1: rows}, {1}, self.NOW) == {'up': [], 'with_trend': 1}

    def test_counts_a_flat_or_falling_pace_but_does_not_list_it(self):
        report = stats.progress_report({
            1: self._rows(84.0, 83.0, 82.0, 81.0, exercise_id=1),
            2: self._rows(80.0, 80.0, 80.0, 80.0, exercise_id=2),
        }, set(), self.NOW)
        assert report == {'up': [], 'with_trend': 2}

    def test_does_not_count_a_lift_without_a_pace(self):
        report = stats.progress_report({1: self._rows(80.0, 82.0, 84.0)}, set(), self.NOW)
        assert report == {'up': [], 'with_trend': 0}

    def test_calls_a_best_the_first_workout_still_holds_a_bestwert(self):
        # A comeback: the line rises, but the best is still the debut's,
        # and a debut beats nothing (D3).
        rows = self._rows(90.0, 70.0, 80.0, 89.0)
        [lift] = stats.progress_report({1: rows}, set(), self.NOW)['up']
        assert lift['per_month'] == 3.0
        assert lift['best'] == {'e1rm': 90.0, 'started_at': rows[0].started_at, 'is_record': False}


class TestBestRecord:
    """The best judged set, and whether it is a record (D3) -- "Rekord" or
    "Bestwert" on the exercise page and in Start's "Legen zu"."""

    def test_a_best_that_beat_an_earlier_workout_is_a_record(self):
        rows = [perf([(80.0, 5)], started_at=day(0), session_id=1),
                perf([(85.0, 5), (80.0, 5)], started_at=day(7), session_id=2)]
        best = stats.best_record(rows)
        assert (best['weight'], best['reps'], best['e1rm'], best['session_id'], best['is_record']) \
            == (85.0, 5, 99.2, 2, True)

    def test_the_debuts_best_is_no_record(self):
        rows = [perf([(85.0, 5)], started_at=day(0), session_id=1),
                perf([(80.0, 5)], started_at=day(7), session_id=2)]
        best = stats.best_record(rows)
        assert (best['session_id'], best['is_record']) == (1, False)

    def test_judges_by_the_marks_it_is_handed(self):
        # exercise_progress holds record_marks already and hands them over.
        rows = [perf([(80.0, 5)], started_at=day(0), session_id=1),
                perf([(82.5, 5)], started_at=day(7), session_id=2, position=1),
                perf([(90.0, 5)], started_at=day(7), session_id=2, position=3)]
        assert stats.best_record(rows, stats.record_marks(rows)) == stats.best_record(rows)
        assert stats.best_record(rows)['is_record'] is True
        assert stats.best_record(rows, {})['is_record'] is False

    def test_is_none_without_a_judged_set(self):
        assert stats.best_record([perf([(0.0, 10)])]) is None
        assert stats.best_record([]) is None


def test_record_set_is_the_set_that_made_the_value():
    # 80 × 5 and 70 × 10 both estimate 93,3: the heavier one is named.
    row = perf([(70.0, 10), (85.0, 3), (80.0, 5)])
    assert stats.record_set(row, 93.3) == (80.0, 5)
    assert stats.record_set(row, 93.5) == (85.0, 3)
    assert stats.record_set(row, 100.0) is None


class TestSessionRecords:
    """Verlauf's "Nur Rekorde" (M3): each workout's records, named."""

    def test_names_each_record_by_the_set_that_made_it_and_the_best_it_beat(self):
        rows = [perf([(80.0, 5)], started_at=day(0), session_id=1),
                perf([(85.0, 5), (80.0, 8)], started_at=day(7), session_id=2)]
        assert stats.session_records(rows) == {2: [{
            'exercise_id': 1, 'name': 'Bankdruecken', 'weight': 80.0, 'reps': 8,
            'e1rm': 101.3, 'previous': 93.3,
        }]}

    def test_names_an_exercise_once_a_workout_at_its_stronger_slot(self):
        rows = [perf([(80.0, 5)], started_at=day(0), session_id=1),
                perf([(85.0, 5)], started_at=day(7), session_id=2, position=1),
                perf([(90.0, 5)], started_at=day(7), session_id=2, position=3)]
        [record] = stats.session_records(rows)[2]
        assert (record['weight'], record['reps']) == (90.0, 5)

    def test_lists_the_records_in_the_order_the_workout_ran(self):
        rows = [
            perf([(80.0, 5)], started_at=day(0), session_id=1, exercise_id=1, name='Bank'),
            perf([(100.0, 5)], started_at=day(0), session_id=1, exercise_id=2, name='Kniebeuge',
                 position=2),
            perf([(110.0, 5)], started_at=day(7), session_id=2, exercise_id=2, name='Kniebeuge'),
            perf([(85.0, 5)], started_at=day(7), session_id=2, exercise_id=1, name='Bank',
                 position=2),
        ]
        assert [record['name'] for record in stats.session_records(rows)[2]] == ['Kniebeuge', 'Bank']

    def test_keeps_the_earlier_slot_of_an_exercise_on_a_tie(self):
        # Slot 3 arrives first: the rule, not the order rows come in, decides.
        rows = [
            perf([(80.0, 5)], started_at=day(0), session_id=1, exercise_id=1, name='Bank'),
            perf([(100.0, 5)], started_at=day(0), session_id=1, exercise_id=2, name='Kniebeuge',
                 position=2),
            perf([(85.0, 5)], started_at=day(7), session_id=2, exercise_id=1, name='Bank',
                 position=3),
            perf([(110.0, 5)], started_at=day(7), session_id=2, exercise_id=2, name='Kniebeuge',
                 position=2),
            perf([(85.0, 5)], started_at=day(7), session_id=2, exercise_id=1, name='Bank'),
        ]
        assert [record['name'] for record in stats.session_records(rows)[2]] == ['Bank', 'Kniebeuge']

    def test_counts_what_every_other_surface_counts(self):
        rows = [
            perf([(80.0, 5)], started_at=day(0), session_id=1, exercise_id=1),
            perf([(100.0, 5)], started_at=day(0), session_id=1, exercise_id=2, position=2),
            perf([(85.0, 5)], started_at=day(7), session_id=2, exercise_id=1),
            perf([(90.0, 5)], started_at=day(7), session_id=2, exercise_id=2, position=2),
            perf([(90.0, 5)], started_at=day(14), session_id=3, exercise_id=1, is_deload=True),
            perf([(105.0, 5)], started_at=day(14), session_id=3, exercise_id=2, position=2),
        ]
        records = stats.session_records(rows)
        assert {session_id: len(named) for session_id, named in records.items()} \
            == stats.session_record_counts(rows) == {2: 1, 3: 2}


class TestWeightLadder:
    """"Wiederholungen je Gewicht" (D9 A): how far each weight went."""

    def test_most_reps_per_weight_heaviest_first_with_workouts_and_first_day(self):
        rows = [
            perf([(80.0, 8), (80.0, 7)], started_at=day(0), session_id=1),
            perf([(82.5, 5), (80.0, 9)], started_at=day(7), session_id=2),
            perf([(82.5, 6)], started_at=day(14), session_id=3),
        ]
        assert stats.weight_ladder(rows) == [
            {'weight': 82.5, 'reps': 6, 'workouts': 2, 'first_at': day(7)},
            {'weight': 80.0, 'reps': 9, 'workouts': 2, 'first_at': day(0)},
        ]

    def test_shows_the_heaviest_four(self):
        rows = [perf([(float(weight), 8)], started_at=day(i), session_id=i + 1)
                for i, weight in enumerate([60, 70, 80, 90, 100])]
        assert [entry['weight'] for entry in stats.weight_ladder(rows)] == [100.0, 90.0, 80.0, 70.0]

    def test_leaves_deloads_out_and_reads_high_reps(self):
        # A deload's weight was lightened on purpose; 15 reps are what was done.
        rows = [perf([(60.0, 15)], started_at=day(0), session_id=1),
                perf([(90.0, 10)], started_at=day(7), session_id=2, is_deload=True)]
        assert stats.weight_ladder(rows) == [
            {'weight': 60.0, 'reps': 15, 'workouts': 1, 'first_at': day(0)}]

    def test_counts_a_workout_once_for_a_weight_it_used_in_two_slots(self):
        rows = [perf([(80.0, 8)], started_at=day(0), session_id=1, position=1),
                perf([(80.0, 6)], started_at=day(0), session_id=1, position=3)]
        assert stats.weight_ladder(rows) == [
            {'weight': 80.0, 'reps': 8, 'workouts': 1, 'first_at': day(0)}]

    def test_one_weight_is_one_line_however_the_float_came_out(self):
        rows = [perf([(62.5, 8)], started_at=day(0), session_id=1),
                perf([(62.500000001, 9)], started_at=day(7), session_id=2)]
        assert stats.weight_ladder(rows) == [
            {'weight': 62.5, 'reps': 9, 'workouts': 2, 'first_at': day(0)}]


class TestRecordStair:
    """The Rekordtreppe (D9, M2 chart 1): one col per workout, the best so
    far as its tread."""

    @staticmethod
    def _cols(stair, *keys):
        return [tuple(col[key] for key in keys) for col in stair['cols']]

    def test_a_tread_is_the_best_so_far_and_climbs_only_at_a_record(self):
        rows = [perf([(90.0, 1)], started_at=day(0), session_id=1),
                perf([(88.0, 1)], started_at=day(7), session_id=2),
                perf([(95.0, 1)], started_at=day(14), session_id=3),
                perf([(94.0, 1)], started_at=day(21), session_id=4)]
        stair = stats.record_stair(rows)
        # The debut is no record: nothing came before it (record_marks).
        assert self._cols(stair, 'session_id', 'e1rm', 'best', 'kind') == [
            (1, 90.0, 90.0, 'workout'), (2, 88.0, 90.0, 'workout'),
            (3, 95.0, 95.0, 'record'), (4, 94.0, 95.0, 'workout')]
        assert stair['cols'][2]['started_at'] == day(14)

    def test_a_lift_twice_in_one_workout_is_one_col_its_better_row(self):
        rows = [perf([(80.0, 1)], started_at=day(0), session_id=1, position=1),
                perf([(85.0, 1)], started_at=day(7), session_id=2, position=1),
                perf([(88.0, 1)], started_at=day(7), session_id=2, position=3)]
        assert self._cols(stats.record_stair(rows), 'session_id', 'position', 'e1rm', 'kind') == [
            (1, 1, 80.0, 'workout'), (2, 3, 88.0, 'record')]

    def test_a_deload_sits_in_the_lane_unless_it_set_a_record(self):
        # G-078: a deload can set a record; then it is one, on the stair.
        rows = [perf([(90.0, 1)], started_at=day(0), session_id=1),
                perf([(70.0, 1)], started_at=day(7), session_id=2, is_deload=True),
                perf([(95.0, 1)], started_at=day(14), session_id=3, is_deload=True)]
        assert self._cols(stats.record_stair(rows), 'kind', 'best') == [
            ('workout', 90.0), ('deload', 90.0), ('record', 95.0)]

    def test_a_deload_the_tread_climbs_at_is_drawn_on_it(self):
        # Under a pill a slot's best can rise at a deload that set no record
        # of the lift; in the lane, that step stood on nothing (I2 review).
        rows = [perf([(100.0, 1)], started_at=day(0), session_id=1, position=1),
                perf([(80.0, 1)], started_at=day(7), session_id=2, position=3),
                perf([(85.0, 1)], started_at=day(14), session_id=3, position=3, is_deload=True),
                perf([(70.0, 1)], started_at=day(21), session_id=4, position=3, is_deload=True)]
        assert self._cols(stats.record_stair(rows, position=3), 'session_id', 'best', 'kind') == [
            (2, 80.0, 'workout'), (3, 85.0, 'workout'), (4, 85.0, 'deload')]
        # So is a debut that was a deload: the first tread stands on it.
        debut = [perf([(80.0, 1)], started_at=day(0), session_id=1, is_deload=True),
                 perf([(78.0, 1)], started_at=day(7), session_id=2)]
        assert self._cols(stats.record_stair(debut), 'kind', 'best') == [
            ('workout', 80.0), ('workout', 80.0)]

    def test_draws_only_workouts_with_an_estimate(self):
        # Past 12 reps nothing is judged; 0 kg estimates 0 kg (G-038).
        rows = [perf([(90.0, 1)], started_at=day(0), session_id=1),
                perf([(60.0, 15)], started_at=day(7), session_id=2),
                perf([(0.0, 10)], started_at=day(14), session_id=3),
                perf([(92.0, 1)], started_at=day(21), session_id=4)]
        assert self._cols(stats.record_stair(rows), 'session_id') == [(1,), (4,)]

    def test_no_stair_with_fewer_than_two_workouts_to_draw(self):
        assert stats.record_stair([perf([(90.0, 1)])]) is None
        bodyweight = [perf([(0.0, 10)], started_at=day(0), session_id=1),
                      perf([(0.0, 12)], started_at=day(7), session_id=2)]
        assert stats.record_stair(bodyweight) is None

    def test_a_slot_draws_its_own_workouts_and_its_own_best(self):
        # 92 is slot 1's best, not the lift's: the tread rises, the dot stays plain.
        rows = [perf([(90.0, 1)], started_at=day(0), session_id=1, position=1),
                perf([(100.0, 1)], started_at=day(7), session_id=2, position=3),
                perf([(92.0, 1)], started_at=day(14), session_id=3, position=1)]
        assert self._cols(stats.record_stair(rows, position=1), 'session_id', 'best', 'kind') == [
            (1, 90.0, 'workout'), (3, 92.0, 'workout')]

    def test_a_record_is_gold_in_the_slot_that_set_it(self):
        # One workout ran the lift first and third; only the third set the record.
        rows = [perf([(90.0, 1)], started_at=day(0), session_id=1, position=1),
                perf([(88.0, 1)], started_at=day(7), session_id=2, position=1),
                perf([(95.0, 1)], started_at=day(7), session_id=2, position=3),
                perf([(89.0, 1)], started_at=day(14), session_id=3, position=3)]
        assert self._cols(stats.record_stair(rows, position=1), 'kind') == [
            ('workout',), ('workout',)]
        assert self._cols(stats.record_stair(rows, position=3), 'kind') == [
            ('record',), ('workout',)]

    def test_spans_the_dots_and_the_treads_but_not_the_lane(self):
        rows = [perf([(90.0, 1)], started_at=day(0), session_id=1),
                perf([(50.0, 1)], started_at=day(7), session_id=2, is_deload=True),
                perf([(100.0, 1)], started_at=day(14), session_id=3)]
        stair = stats.record_stair(rows)
        assert (stair['lo'], stair['hi'], stair['ticks']) == (90.0, 100.0, [90, 95, 100])

    def test_widens_a_flat_stair_to_five_kg_around_its_middle(self):
        # 0,5 kg over a year must draw flat, not as a cliff.
        rows = [perf([(100.0, 1)], started_at=day(0), session_id=1),
                perf([(100.5, 1)], started_at=day(7), session_id=2)]
        stair = stats.record_stair(rows)
        assert (stair['lo'], stair['hi'], stair['ticks']) == (97.75, 102.75, [98, 100, 102])

    def test_widens_a_light_lift_up_from_zero_never_below_it(self):
        # A 1 kg to 2 kg raise centred on 1,5 kg drew a "-1" gridline.
        rows = [perf([(1.0, 1)], started_at=day(0), session_id=1),
                perf([(2.0, 1)], started_at=day(7), session_id=2)]
        stair = stats.record_stair(rows)
        assert (stair['lo'], stair['hi']) == (0.0, 5.0)
        assert min(stair['ticks']) >= 0

    def test_ticks_are_the_widest_round_step_with_three_inside(self):
        assert stats._stair_ticks(60.0, 140.0) == [75, 100, 125]
        assert stats._stair_ticks(88.0, 95.0) == [88, 90, 92, 94]


# --------------------------------------------------------------------------
# The plan model (D2 P1): set count, rep range, "Nächstes Mal".
# --------------------------------------------------------------------------

def _targets(*pairs):
    return [{'weight': weight, 'reps': reps} for weight, reps in pairs]


class TestNextTarget:
    """Double progression, set by set (Michi 09-24, M2): each set one rep more
    at its own weight, up to the top of the range; once every planned set
    was done at the top, each set one loadable step up and back to the
    bottom (G-035)."""

    def test_each_set_gets_one_rep_more_at_its_own_weight(self):
        assert stats.next_target([(60.0, 9), (60.0, 8), (60.0, 8)], 6, 10, 3, 2.5) \
            == _targets((60.0, 10), (60.0, 9), (60.0, 9))

    def test_a_lighter_set_keeps_its_weight(self):
        # One weight for every set asked +5 kg of the back-off sets.
        assert stats.next_target([(40.0, 8), (35.0, 9), (35.0, 8)], 6, 10, 3, 2.5) \
            == _targets((40.0, 9), (35.0, 10), (35.0, 9))

    def test_a_set_left_out_last_time_is_aimed_at_like_the_one_before_it(self):
        # Rudern (M2): 85 x 11 and 85 x 9 of three planned sets, range 7-11.
        assert stats.next_target([(85.0, 11), (85.0, 9)], 7, 11, 3, 8.0) \
            == _targets((85.0, 11), (85.0, 10), (85.0, 10))

    def test_cuts_to_the_planned_sets(self):
        assert stats.next_target([(60.0, 8)] * 5, 6, 10, 3, 2.5) \
            == _targets(*[(60.0, 9)] * 3)

    def test_steps_up_once_every_planned_set_reached_the_top(self):
        assert stats.next_target([(40.0, 10), (35.0, 10), (35.0, 11)], 6, 10, 3, 2.5) \
            == _targets((42.5, 6), (37.5, 6), (37.5, 6))

    def test_waits_for_every_planned_set_before_stepping_up(self):
        # Two sets at the top of the range, three planned: the third was not
        # done, so it has not reached anything yet.
        assert stats.next_target([(60.0, 10), (60.0, 10)], 6, 10, 3, 2.5) \
            == _targets(*[(60.0, 10)] * 3)

    def test_a_set_past_the_top_is_not_asked_for_less(self):
        assert stats.next_target([(60.0, 12), (60.0, 8)], 6, 10, 2, 2.5) \
            == _targets((60.0, 12), (60.0, 9))

    def test_climbs_one_rep_at_a_time_below_the_range(self):
        assert stats.next_target([(80.0, 4), (80.0, 5)], 6, 10, 2, 2.5) \
            == _targets((80.0, 5), (80.0, 6))

    def test_snaps_the_step_onto_a_machines_real_stops(self):
        assert stats.next_target([(45.0, 12)] * 3, 8, 12, 3, 5.0, [40, 45, 52, 59]) \
            == _targets(*[(52, 8)] * 3)

    def test_topped_out_on_a_known_stack_asks_for_one_rep_more(self):
        # Snapping clamps back to the top stop; the same weight again at the
        # bottom of the range would be a step back.
        assert stats.next_target([(59.0, 12)] * 3, 8, 12, 3, 5.0, [40, 45, 52, 59]) \
            == _targets(*[(59.0, 13)] * 3)

    def test_bodyweight_progresses_by_reps(self):
        assert stats.next_target([(0.0, 10)] * 3, 6, 10, 3, 2.5) \
            == _targets(*[(0.0, 11)] * 3)

    def test_nothing_lifted_has_no_target(self):
        assert stats.next_target([], 6, 10, 3, 2.5) is None


class TestPlanShape:
    """Filled once from history, then only an explicit edit changes it
    (G-050: one test workout shrank a routine)."""

    def test_set_count_is_the_most_a_recent_workout_held(self):
        # Max, not mode: a cut-short workout must not shrink the plan.
        assert stats.plan_set_count([3, 2, 4]) == 4

    def test_set_count_defaults_without_history(self):
        assert stats.plan_set_count([]) == stats.DEFAULT_PLAN_SETS

    def test_set_count_stays_between_one_and_ten(self):
        assert stats.plan_set_count([14]) == 10
        assert stats.plan_set_count([0]) == 1

    def test_rep_range_centres_on_the_median_reps_at_the_top_weight(self):
        assert stats.derived_rep_range([8, 8, 7, 9, 8]) == (6, 10)

    def test_rep_range_rounds_a_half_up(self):
        assert stats.derived_rep_range([7, 8]) == (6, 10)

    def test_rep_range_never_starts_below_one(self):
        assert stats.derived_rep_range([2, 2, 1]) == (1, 4)

    def test_rep_range_defaults_to_six_to_ten(self):
        assert stats.derived_rep_range([]) == (6, 10)

    def test_history_range_reads_only_each_workouts_top_weight(self):
        # The back-off set's 12 reps say nothing about the working range.
        assert stats.rep_range_from([[(100, 8), (90, 12)]]) == (6, 10)

    def test_history_range_holds_a_lift_done_for_high_reps(self):
        # A calf raise done for 15 aims at 13-17: skipped as past
        # RECORD_MAX_REPS, it got 6-10 and a "42,5 × 6" (B5 review).
        assert stats.rep_range_from([[(40, 15)] * 3] * 3) == (13, 17)

    def test_rep_range_never_ends_above_what_a_routine_keeps(self):
        # The sheet posts the range back as it is, and the route refuses
        # anything past MAX_PLAN_REPS: the range moves down instead.
        assert stats.derived_rep_range([100, 100, 5]) == (96, stats.MAX_PLAN_REPS)

    def test_history_range_reads_the_newest_five_workouts(self):
        newest = [[(100, 8)]] * stats.RANGE_WORKOUTS
        assert stats.rep_range_from(newest + [[(100, 12)]] * 10) == (6, 10)

    def test_history_range_defaults_without_history(self):
        assert stats.rep_range_from([]) == stats.DEFAULT_REP_RANGE
