"""One meaning of "Rekord" (walkthrough 2026-09-23, D3; G-033, G-126, G-078,
G-130, G-038).

A set is a record when its e1RM beats every EARLIER workout's best for that
exercise: a tie is none, a first workout has nothing to beat, and the badge
stays as history when a later workout goes higher. The e1RM of a single is the
weight itself; above 12 reps a set is shown but judged by nothing. Deload makes
no difference either way. Weight and volume are no longer kinds of record.

Pure functions: no app, no database.
"""
import datetime as dt

from features.gym import analytics, stats


def row(sets, session_id, days, exercise_id=1, position=1, is_deload=False, name='Latzug'):
    return stats.PerformedExercise(
        exercise_id=exercise_id, name=name, muscle_group='Rücken', is_unilateral=False,
        position=position, session_id=session_id,
        started_at=dt.datetime(2026, 6, 1, 18, 0) + dt.timedelta(days=days),
        sets=tuple(sets), is_deload=is_deload,
    )


# -- the number ---------------------------------------------------------------

def test_a_single_is_worth_exactly_its_weight():
    assert stats.epley_1rm(100.0, 1) == 100.0
    assert stats.judged_e1rm(100.0, 1) == 100.0


def test_the_judged_e1rm_is_the_estimate_to_the_tenth_it_is_shown_at():
    assert stats.judged_e1rm(80.0, 8) == round(80.0 * (1 + 8 / 30), 1) == 101.3
    assert stats.judged_e1rm(60.0, 12) == 84.0


def test_above_twelve_reps_or_without_reps_a_set_is_judged_by_nothing():
    assert stats.judged_e1rm(40.0, 13) is None
    assert stats.judged_e1rm(40.0, 25) is None
    assert stats.judged_e1rm(40.0, 0) is None


def test_a_row_shows_its_best_judged_set_and_falls_back_only_when_it_has_none():
    mixed = row([(40.0, 25), (55.0, 8)], 1, 0)
    assert stats.best_e1rm(mixed) == stats.judged_e1rm(55.0, 8)
    only_high = row([(40.0, 25)], 2, 1)
    assert stats.judged_best(only_high) is None
    assert stats.best_e1rm(only_high) == stats.epley_1rm(40.0, 25)


# -- one set, live ------------------------------------------------------------

def test_a_set_that_beats_every_earlier_workout_is_a_record_and_says_what_it_beat():
    earlier = [row([(50.0, 10)], 1, 0), row([(52.5, 10)], 2, 7), row([(52.5, 8)], 3, 14)]
    detail = stats.record_detail(55.0, 10, earlier)
    assert detail == {'kind': 'e1rm', 'value': 73.3, 'previous': 70.0,
                      'previous_at': earlier[1].started_at}


def test_a_tie_is_no_record():
    earlier = [row([(52.5, 10)], 1, 0)]
    assert stats.record_detail(52.5, 10, earlier) is None
    # 90 × 10 and 100 × 6 both show as 120,0: a tie on screen is a tie.
    assert stats.record_detail(100.0, 6, [row([(90.0, 10)], 1, 0)]) is None


def test_a_heavier_set_with_a_lower_e1rm_is_no_record():
    """The 09-20 'weight outranks e1RM' rule is gone (D3)."""
    assert stats.record_detail(100.0, 5, [row([(90.0, 10)], 1, 0)]) is None


def test_the_first_workout_has_nothing_to_beat():
    assert stats.record_detail(80.0, 8, []) is None


def test_a_set_above_twelve_reps_is_never_a_record_nor_a_bar():
    """G-130: 40 × 25 estimates 73,3 and used to beat 55 × 8 (69,7)."""
    assert stats.record_detail(40.0, 25, [row([(55.0, 8)], 1, 0)]) is None
    high_only = [row([(40.0, 25)], 1, 0)]
    assert stats.record_detail(55.0, 8, high_only) is None       # nothing judged to beat
    earlier = [row([(40.0, 25)], 1, 0), row([(50.0, 8)], 2, 7)]
    assert stats.record_detail(55.0, 8, earlier)['previous'] == 63.3


def test_a_deload_workout_is_a_bar_like_any_other():
    """b-A: a record is a record, deload or not -- in both directions."""
    assert stats.record_detail(95.0, 8, [row([(100.0, 8)], 1, 0, is_deload=True)]) is None


# -- whole workouts -----------------------------------------------------------

def test_a_workout_keeps_its_record_when_a_later_one_goes_higher():
    """G-126: Verlauf counted only records still standing, so a badge vanished
    once a later workout beat it (a-A: it stays as history)."""
    rows = [row([(50.0, 10)], 1, 0), row([(52.5, 10)], 2, 7), row([(55.0, 10)], 3, 14),
            row([(52.5, 10)], 4, 21), row([(55.0, 10)], 5, 28)]
    assert stats.session_record_counts(rows) == {2: 1, 3: 1}


def test_a_workout_counts_one_record_per_exercise_however_many_slots_or_sets():
    rows = [row([(50.0, 10)], 1, 0),
            row([(55.0, 10), (56.0, 10)], 2, 7, position=1),
            row([(54.0, 10)], 2, 7, position=4),
            row([(60.0, 8)], 1, 0, exercise_id=2), row([(62.5, 8)], 2, 7, exercise_id=2)]
    assert stats.session_record_counts(rows) == {2: 2}


def test_a_workouts_own_rows_do_not_judge_each_other():
    """The same exercise twice in one workout: both tries face the same bar."""
    rows = [row([(50.0, 10)], 1, 0),
            row([(55.0, 10)], 2, 7, position=1), row([(53.0, 10)], 2, 7, position=4)]
    marks = stats.record_marks(rows)
    assert sorted(r.position for r in marks) == [1, 4]


def test_the_record_is_the_exercises_not_the_slots():
    """The chip judged within the slot, so a slot's best below the lift's own
    best still read "Rekord" (G-033)."""
    rows = [row([(55.0, 10)], 1, 0, position=1), row([(50.0, 10)], 2, 7, position=3),
            row([(52.5, 10)], 3, 14, position=3)]
    assert stats.session_record_counts(rows) == {}
    assert stats.exercise_state(rows, position=3) != 'rekord'


def test_a_deload_workout_can_set_a_record():
    rows = [row([(50.0, 10)], 1, 0), row([(52.5, 10)], 2, 7, is_deload=True)]
    assert stats.session_record_counts(rows) == {2: 1}


def test_workouts_are_ordered_by_when_they_started_not_by_id():
    """A workout entered later for an earlier day is judged on its day."""
    late_entry = row([(60.0, 10)], 9, 0)
    rows = [late_entry, row([(55.0, 10)], 2, 7)]
    assert stats.session_record_counts(rows) == {}


def test_two_workouts_that_started_together_are_ordered_by_id():
    """Same start (a pair, an import): the lower id went first, so the
    second is judged against it -- whatever order the rows arrive in."""
    first, second = row([(50.0, 10)], 3, 0), row([(52.5, 10)], 4, 0)
    assert stats.session_record_counts([second, first]) == {4: 1}
    first, second = row([(52.5, 10)], 3, 0), row([(50.0, 10)], 4, 0)
    assert stats.session_record_counts([second, first]) == {}


# -- the debrief --------------------------------------------------------------

def test_the_debrief_names_e1rm_records_only_and_judges_against_earlier_workouts():
    history = [row([(50.0, 10)], 1, 0), row([(80.0, 3)], 1, 0, exercise_id=2, name='Kniebeuge'),
               # Later than the workout being read: no bar for it.
               row([(70.0, 10)], 9, 30)]
    current = [row([(55.0, 10)], 5, 14), row([(85.0, 1)], 5, 14, exercise_id=2, name='Kniebeuge')]
    report = stats.session_report(current, history)
    assert [(r['kind'], r['name'], r['value'], r['previous']) for r in report['records']] == [
        ('e1rm', 'Latzug', 73.3, 66.7)]
    assert report['record_count'] == 1
    by_name = {e['name']: e for e in report['exercises']}
    assert by_name['Latzug']['verdict'] == 'rekord'
    assert by_name['Latzug']['is_record'] is True
    # 85 × 1 is 85,0 now, not 87,8: below 80 × 3 (88,0).
    assert by_name['Kniebeuge']['is_record'] is False
    assert by_name['Kniebeuge']['e1rm'] == 85.0


def test_a_deload_debrief_keeps_its_records():
    """G-078: marking the workout a deload took back records already
    celebrated in it."""
    history = [row([(50.0, 10)], 1, 0)]
    current = [row([(55.0, 10)], 2, 7, is_deload=True)]
    report = stats.session_report(current, history)
    assert report['record_count'] == 1
    assert report['exercises'][0]['verdict'] == 'rekord'


# -- the exercise page --------------------------------------------------------

def test_the_exercise_page_tags_every_workout_that_set_a_record():
    rows = [row([(50.0, 10)], 1, 0), row([(55.0, 10)], 2, 7), row([(55.0, 10)], 3, 14),
            row([(52.5, 10)], 4, 21)]
    progress = stats.exercise_progress(rows)
    assert {r['session_id']: r['is_record'] for r in progress['table']} == {
        1: False, 2: True, 3: False, 4: False}
    # The Rekordtreppe goes gold where the log says "Rekord", and nowhere else.
    assert [col['kind'] for col in stats.record_stair(rows)['cols']] == [
        'workout', 'record', 'workout', 'workout']


def test_rekord_on_the_exercise_means_its_newest_workout_set_one():
    """G-033: the header said "Rekord · Heute" for a tie."""
    tie = [row([(50.0, 10)], 1, 0), row([(55.0, 10)], 2, 7), row([(55.0, 10)], 3, 14)]
    assert stats.exercise_state(tie) != 'rekord'
    beat = tie + [row([(56.0, 10)], 4, 21, position=3)]
    assert stats.exercise_state(beat, position=1) == 'rekord'


def test_the_best_e1rm_is_the_earliest_set_that_reached_it_deloads_included():
    rows = [row([(50.0, 10)], 1, 0), row([(55.0, 10)], 2, 7, is_deload=True),
            row([(55.0, 10)], 3, 14), row([(40.0, 25)], 4, 21)]
    best = stats.exercise_progress(rows)['pr_e1rm']
    assert (best['session_id'], best['e1rm'], best['weight'], best['reps'], best['is_record']) \
        == (2, 73.3, 55.0, 10, True)


def test_the_best_set_is_a_record_only_once_it_beat_an_earlier_workout():
    # D3: the debut beats nothing. Its best, still standing, is the lift's
    # Bestwert -- the page said "Rekord" beside no gold anywhere (I2 review).
    rows = [row([(90.0, 1)], 1, 0), row([(85.0, 1)], 2, 7)]
    assert stats.exercise_progress(rows)['pr_e1rm']['is_record'] is False
    rows.append(row([(95.0, 1)], 3, 14))
    best = stats.exercise_progress(rows)['pr_e1rm']
    assert (best['session_id'], best['is_record']) == (3, True)


def test_a_bodyweight_exercise_has_no_best_e1rm_and_no_stair():
    """G-038: "Bestes e1RM 0,0 kg" and a 0-kg "Rekord"."""
    rows = [row([(0.0, 8)], 1, 0), row([(0.0, 10)], 2, 7)]
    progress = stats.exercise_progress(rows)
    assert progress['pr_e1rm'] is None
    assert not any(r['is_record'] for r in progress['table'])
    assert stats.record_stair(rows) is None


# -- stalls judge by the same number ------------------------------------------

def test_a_set_above_twelve_reps_neither_resets_nor_extends_a_stall():
    """40 × 25 estimated 73,3 and set a bar 56 × 8 (70,9) could not clear."""
    rows = [row([(55.0, 8)], 1, 0), row([(40.0, 25)], 2, 7), row([(55.0, 8)], 3, 14)]
    assert stats.sessions_since_pr(rows) == 1
    assert stats.sessions_since_pr(rows + [row([(56.0, 8)], 4, 21)]) == 0


# -- Verlauf ------------------------------------------------------------------

def test_the_timeline_lists_the_same_records_as_everywhere_else():
    rows = [row([(50.0, 10)], 1, 0), row([(52.5, 10)], 2, 7, is_deload=True),
            row([(60.0, 2)], 3, 14),             # heavier, lower e1RM (64,0): no record
            row([(55.0, 10)], 4, 21), row([(52.0, 10)], 5, 28)]
    timeline = analytics.record_timeline(rows)
    assert [(e['session_id'], e['e1rm']) for e in timeline] == [
        (4, {'value': 73.3, 'previous': 70.0}),
        (2, {'value': 70.0, 'previous': 66.7}),
    ]
    assert all('weight' not in e for e in timeline)
    assert stats.session_record_counts(rows) == {2: 1, 4: 1}
