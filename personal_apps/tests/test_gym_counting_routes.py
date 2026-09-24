"""B3 at the routes: one rule for what counts (Q1, G-038), a record is an
e1RM against the workouts BEFORE (D3), the stall line steps up from the top
set (G-123), and un-skip plans the sets still owed (G-125).

The pure rules are pinned in test_gym_records.py; these pin that every
screen asks them. Each case is one the old rules answered differently.
Runs against the local development database, on rows it builds and deletes.
"""
import datetime as dt

import pytest

from app import app as flask_app
from conftest import _admin_id, embedded_payload
from extensions import db
from models import Exercise, SessionExercise, SessionSet, WorkoutSession


class Rows:
    """Workouts and exercises for one test, built inside an app context and
    deleted afterwards whatever the test does."""

    def __init__(self):
        self.now = dt.datetime.utcnow()
        self.session_ids = []
        self.exercise_ids = []

    def exercise(self, name):
        exercise = Exercise(name=f'pytest b3 {name}', muscle_group='Brust')
        db.session.add(exercise)
        db.session.flush()
        self.exercise_ids.append(exercise.id)
        return exercise

    def workout(self, days_ago=0.0, finished=True, is_deload=False):
        started = self.now - dt.timedelta(days=days_ago)
        workout = WorkoutSession(
            name='pytest b3', user_id=_admin_id(), started_at=started,
            finished_at=started + dt.timedelta(minutes=50) if finished else None,
            is_deload=is_deload, deload_pct=70 if is_deload else None)
        db.session.add(workout)
        db.session.flush()
        self.session_ids.append(workout.id)
        return workout

    def row(self, workout, exercise, done=(), planned=(), position=1,
            skipped=False, replaces=None):
        """`done` and `planned` are (weight, reps) pairs, logged in order."""
        row = SessionExercise(session_id=workout.id, exercise_id=exercise.id,
                              position=position, skipped=skipped,
                              replaces_id=replaces.id if replaces is not None else None)
        db.session.add(row)
        db.session.flush()
        for number, (weight, reps) in enumerate(list(done) + list(planned), start=1):
            is_done = number <= len(done)
            db.session.add(SessionSet(
                session_exercise_id=row.id, position=number, weight=weight, reps=reps,
                completed=is_done,
                completed_at=workout.started_at + dt.timedelta(minutes=number) if is_done else None))
        db.session.flush()
        return row

    def delete(self):
        with flask_app.app_context():
            for session_id in self.session_ids:
                workout = db.session.get(WorkoutSession, session_id)
                if workout is not None:
                    workout.resting_set_id = None
                    db.session.commit()
                    db.session.delete(workout)
                    db.session.commit()
            for exercise_id in self.exercise_ids:
                exercise = db.session.get(Exercise, exercise_id)
                if exercise is not None:
                    db.session.delete(exercise)
                    db.session.commit()


@pytest.fixture()
def rows():
    built = Rows()
    try:
        yield built
    finally:
        built.delete()


def _sets(row_id):
    """A row's sets as (weight, reps, completed), in order."""
    with flask_app.app_context():
        row = db.session.get(SessionExercise, row_id)
        return [(s.weight, s.reps, s.completed)
                for s in sorted(row.sets, key=lambda s: s.position)]


def test_the_live_count_holds_every_done_set(client, rows):
    """Q1: a set done before its exercise was skipped, or before it was
    replaced, was done. The count left both out while the volume kept the
    skipped one (G-064), so the finish sheet offered "verwerfen" for a
    workout the server refused to discard (G-131)."""
    with flask_app.app_context():
        skipped_lift, original, substitute = (
            rows.exercise('skipped'), rows.exercise('original'), rows.exercise('substitute'))
        today = rows.workout(days_ago=0.04, finished=False)
        rows.row(today, skipped_lift, done=[(40.0, 10), (40.0, 10)], skipped=True)
        before = rows.row(today, original, done=[(30.0, 10)], position=2)
        after = rows.row(today, substitute, done=[(20.0, 10)],
                         planned=[(20.0, 10), (20.0, 10)], position=2, replaces=before)
        db.session.commit()
        ids = (today.id, after.id)

    payload = embedded_payload(client.get(f'/gym/session/{ids[0]}').get_data(as_text=True))
    assert payload['sets_done'] == 4
    assert payload['sets_total'] == 6
    # The skipped lift's two, then the original's one riding on the
    # substitute, ahead of the substitute's own.
    assert payload['tick_states'] == ['done', 'done', 'done', 'done', 'now', 'open']
    assert payload['session_volume'] == 800.0 + 300.0 + 200.0
    assert payload['has_completed_set'] is True
    carried = {se['id']: (se['replaced_sets_done'], se['replaced_volume'])
               for se in payload['visible_exercises']}
    assert carried[ids[1]] == (1, 300.0)
    assert sorted(carried.values()) == [(0, 0.0), (1, 300.0)]

    # The same count refuses the discard.
    client.post(f'/gym/session/{ids[0]}/discard')
    with flask_app.app_context():
        assert db.session.get(WorkoutSession, ids[0]) is not None


def test_the_live_flare_judges_against_earlier_workouts_only(client, rows):
    """A workout finished after this one started -- a partner's, or one
    entered for an earlier day -- is no bar for it (D3)."""
    with flask_app.app_context():
        lift = rows.exercise('flare earlier')
        earlier = rows.workout(days_ago=8)
        rows.row(earlier, lift, done=[(100.0, 5)])                    # e1RM 116.7
        today = rows.workout(days_ago=0.125, finished=False)
        mine = rows.row(today, lift, done=[(105.0, 5)])               # 122.5
        later = rows.workout(days_ago=0.04)
        rows.row(later, lift, done=[(120.0, 5)])                      # 140.0
        db.session.commit()
        ids = (today.id, mine.sets[0].id, earlier.started_at)

    payload = embedded_payload(client.get(f'/gym/session/{ids[0]}').get_data(as_text=True))
    assert ids[1] in payload['record_set_ids']
    detail = payload['record_details'][str(ids[1])]
    assert (detail['kind'], detail['value'], detail['previous']) == ('e1rm', 122.5, 116.7)
    assert detail['previous_at'].startswith(ids[2].isoformat()[:16])


def test_a_deload_workout_sets_records_and_holds_the_bar(client, rows):
    """b-A: a record is a record, deload or not -- as the set that sets one
    and as the best it has to beat. A deload workout used to set none, and
    a deload's best was no bar, so beating the last full workout counted."""
    with flask_app.app_context():
        lift = rows.exercise('deload bar')
        full = rows.workout(days_ago=10)
        rows.row(full, lift, done=[(100.0, 5)])                       # 116.7
        light = rows.workout(days_ago=5, is_deload=True)
        rows.row(light, lift, done=[(110.0, 5)])                      # 128.3
        today = rows.workout(days_ago=0.04, finished=False, is_deload=True)
        mine = rows.row(today, lift, done=[(105.0, 5), (112.5, 5)])  # 122.5, 131.3
        db.session.commit()
        ids = (today.id, mine.sets[0].id, mine.sets[1].id)

    payload = embedded_payload(client.get(f'/gym/session/{ids[0]}').get_data(as_text=True))
    assert ids[1] not in payload['record_set_ids'], 'the deload best is the bar'
    assert ids[2] in payload['record_set_ids'], 'a deload workout sets records'
    assert payload['record_details'][str(ids[2])]['previous'] == 128.3


def test_a_set_over_twelve_reps_is_no_record(client, rows):
    """c-A: past 12 reps the estimate is not judged (G-130)."""
    with flask_app.app_context():
        lift = rows.exercise('high reps')
        earlier = rows.workout(days_ago=7)
        rows.row(earlier, lift, done=[(20.0, 10)])                    # 26.7
        today = rows.workout(days_ago=0.04, finished=False)
        mine = rows.row(today, lift, done=[(20.0, 20)])               # 33.3, unjudged
        db.session.commit()
        ids = (today.id, mine.sets[0].id)

    payload = embedded_payload(client.get(f'/gym/session/{ids[0]}').get_data(as_text=True))
    assert ids[1] not in payload['record_set_ids']


def test_a_stalled_lift_is_aimed_set_by_set_from_its_own_weights(client, rows):
    """G-123 stepped up from the workout's last set, a back-off set as often
    as not. The target reads every set at its own weight (D2 P1): the top
    set one rep on, the back-off set -- already at the top of the 6-10 range
    its history gives -- held there."""
    with flask_app.app_context():
        lift = rows.exercise('stall top set')
        for days_ago in (25, 20, 15, 10, 5):
            past = rows.workout(days_ago=days_ago)
            rows.row(past, lift, done=[(60.0, 8), (50.0, 10)])        # ties: no PR
        today = rows.workout(days_ago=0.04, finished=False)
        mine = rows.row(today, lift, planned=[(60.0, 8), (50.0, 10)])
        db.session.commit()
        ids = (today.id, mine.id)

    payload = embedded_payload(client.get(f'/gym/session/{ids[0]}').get_data(as_text=True))
    assert payload['stagnation_counts'][str(ids[1])] >= 4
    assert payload['next_targets'][str(ids[1])] == [
        {'weight': 60.0, 'reps': 9}, {'weight': 50.0, 'reps': 10}]


def test_un_skip_plans_the_sets_still_owed(client, rows):
    """G-125: skipped at 1 of 3, the row came back "fully done" and its
    plan was lost -- un-skip only seeded a row with NO set left."""
    with flask_app.app_context():
        lift = rows.exercise('unskip history')
        past = rows.workout(days_ago=7)
        rows.row(past, lift, done=[(50.0, 10), (50.0, 10), (50.0, 8)])
        today = rows.workout(days_ago=0.04, finished=False)
        mine = rows.row(today, lift, done=[(50.0, 10)], planned=[(50.0, 10), (50.0, 8)])
        db.session.commit()
        row_id = mine.id

    client.post(f'/gym/session-exercise/{row_id}/skip')
    assert _sets(row_id) == [(50.0, 10, True)]
    client.post(f'/gym/session-exercise/{row_id}/skip')
    assert _sets(row_id) == [(50.0, 10, True), (50.0, 10, False), (50.0, 8, False)]
    with flask_app.app_context():
        positions = [s.position for s in db.session.get(SessionExercise, row_id).sets]
        assert sorted(positions) == [1, 2, 3]


def test_un_skip_of_a_blank_plan_carries_the_done_set(client, rows):
    """No history: the plan is blank, and the numbers typed into the first
    set are what the rest would have carried had nothing been skipped."""
    with flask_app.app_context():
        lift = rows.exercise('unskip blank')
        today = rows.workout(days_ago=0.04, finished=False)
        mine = rows.row(today, lift, done=[(30.0, 10)], skipped=True)
        db.session.commit()
        row_id = mine.id

    client.post(f'/gym/session-exercise/{row_id}/skip')
    assert _sets(row_id) == [(30.0, 10, True), (30.0, 10, False), (30.0, 10, False)]
    with flask_app.app_context():
        planned = [s for s in db.session.get(SessionExercise, row_id).sets if not s.completed]
        assert [s.is_default_seeded for s in planned] == [False, False]


def test_the_debrief_gilds_the_record_sets(client, rows):
    """Gold is the set whose own e1RM beat every earlier workout (D3), the
    set the live flare fired on. It used to be the first set matching a
    WEIGHT record's number, found by exercise name: here the heavier second
    set, which is no record."""
    with flask_app.app_context():
        lift = rows.exercise('debrief gold')
        earlier = rows.workout(days_ago=9)
        rows.row(earlier, lift, done=[(80.0, 5)])                     # 93.3
        today = rows.workout(days_ago=0.1)
        rows.row(today, lift, done=[(80.0, 8), (82.5, 3)])            # 101.3, 90.8
        db.session.commit()
        workout_id = today.id

    payload = embedded_payload(client.get(f'/gym/session/{workout_id}').get_data(as_text=True))
    assert payload['tick_states'] == ['record', 'done']
    assert [(r['kind'], r['value'], r['previous']) for r in payload['records']] == [
        ('e1rm', 101.3, 93.3)]
    assert payload['exercises'][0]['is_record'] is True


def test_the_debrief_counts_the_sets_of_a_replaced_original(client, rows):
    """Q1: the sets done before a swap were done. The debrief dropped them
    while Heute and Statistik counted them."""
    with flask_app.app_context():
        original, substitute = rows.exercise('debrief original'), rows.exercise('debrief sub')
        today = rows.workout(days_ago=0.1)
        before = rows.row(today, original, done=[(70.0, 8)])
        rows.row(today, substitute, done=[(60.0, 10), (60.0, 10)], replaces=before)
        db.session.commit()
        workout_id = today.id

    payload = embedded_payload(client.get(f'/gym/session/{workout_id}').get_data(as_text=True))
    assert payload['total_sets'] == 3
    assert payload['total_volume'] == 560.0 + 1200.0
    assert sorted(e['name'] for e in payload['exercises']) == [
        'pytest b3 debrief original', 'pytest b3 debrief sub']
    assert len(payload['tick_states']) == 3
    # Nothing unlogged: the original is on the page with its set.
    assert payload['unlogged'] == []


def test_the_catalogue_chip_counts_a_deload_record(client, rows):
    """'Rekord' when the newest workout set one, deload or not (D3). The
    catalogue judged the non-deload rows only, so the chip missed it."""
    with flask_app.app_context():
        lift = rows.exercise('catalogue deload')
        rows.row(rows.workout(days_ago=10), lift, done=[(100.0, 5)])
        rows.row(rows.workout(days_ago=3, is_deload=True), lift, done=[(110.0, 5)])
        db.session.commit()
        exercise_id = lift.id

    payload = embedded_payload(client.get('/gym/uebungen').get_data(as_text=True))
    entry = next(entry for group in payload['groups'] for entry in group['entries']
                 if entry['exercise']['id'] == exercise_id)
    assert entry['chip_label'] == 'Rekord'


def test_the_catalogue_counts_from_a_deload_record(client, rows):
    """B3 review: three ties then a deload record read "Rekord" beside
    "2 Einheiten ohne PR" (the count ran per slot, blind to deloads), and
    "best 100,0" beside the exercise page's "Schwerster Satz 110,0"."""
    with flask_app.app_context():
        lift = rows.exercise('catalogue drought')
        for days_ago in (20, 15, 10):
            rows.row(rows.workout(days_ago=days_ago), lift, done=[(100.0, 5)])
        rows.row(rows.workout(days_ago=3, is_deload=True), lift, done=[(110.0, 5)])
        db.session.commit()
        exercise_id = lift.id

    payload = embedded_payload(client.get('/gym/uebungen').get_data(as_text=True))
    entry = next(entry for group in payload['groups'] for entry in group['entries']
                 if entry['exercise']['id'] == exercise_id)
    assert entry['chip_label'] == 'Rekord'
    assert entry['sessions_since_pr'] == 0
    assert entry['best_weight'] == 110.0
    # What you would load today stays the working weight, not the deload's.
    assert entry['last_weight'] == 100.0


def test_un_skip_after_a_deload_marked_mid_workout_keeps_the_weights(client, rows):
    """B3 review: a deload marked after a set only labels the workout ("Nur
    markiert"), yet un-skip planned the owed sets at 70 % -- 70 x 10 behind
    100 x 5 -- and the sheet then said the percentage was applied."""
    with flask_app.app_context():
        lift = rows.exercise('unskip marked deload')
        rows.row(rows.workout(days_ago=7), lift, done=[(100.0, 5), (100.0, 5), (100.0, 5)])
        today = rows.workout(days_ago=0.04, finished=False)
        mine = rows.row(today, lift, done=[(100.0, 5)], planned=[(100.0, 5), (100.0, 5)])
        db.session.commit()
        ids = (today.id, mine.id)

    client.post(f'/gym/session/{ids[0]}/deload', data={'on': '1', 'pct': '70'})
    client.post(f'/gym/session-exercise/{ids[1]}/skip')
    client.post(f'/gym/session-exercise/{ids[1]}/skip')
    assert _sets(ids[1]) == [(100.0, 5, True), (100.0, 5, False), (100.0, 5, False)]
    payload = embedded_payload(client.get(f'/gym/session/{ids[0]}').get_data(as_text=True))
    assert payload['deload_applied'] is False


def test_the_deload_toggle_leaves_a_ticked_set_with_no_reps_alone(client, rows):
    """B3 review: a ticked 0-rep set counts for nothing (Q1), so the toggle
    still rescaled the plan -- and gave that set DELOAD_REPS, turning a
    leftover into a counted 70 x 10."""
    with flask_app.app_context():
        lift = rows.exercise('deload ticked zero')
        rows.row(rows.workout(days_ago=7), lift, done=[(100.0, 5)])
        today = rows.workout(days_ago=0.04, finished=False)
        mine = rows.row(today, lift, done=[(100.0, 0)], planned=[(100.0, 5)])
        db.session.commit()
        ids = (today.id, mine.id)

    client.post(f'/gym/session/{ids[0]}/deload', data={'on': '1', 'pct': '70'})
    [ticked, planned] = _sets(ids[1])
    assert ticked == (100.0, 0, True)
    assert planned[0] < 100.0 and planned[2] is False
