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
