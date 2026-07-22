"""Tests for features.gym.stats -- pure functions, so no app context, no
database, and no fixtures beyond plain data."""
import datetime as dt

from features.gym import stats


def perf(sets, position=1, started_at=None, is_unilateral=False,
         exercise_id=1, name='Bankdruecken', muscle_group='Brust', session_id=1):
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
    )


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
