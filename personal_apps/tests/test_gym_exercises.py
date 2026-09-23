"""The one exercise list and each lifter's settings on top of it
(features/gym/exercises.py). The first half is pure -- plain dicts, no
database -- like test_gym_library; the second runs against a real database
and deletes what it creates."""
import datetime as dt

import pytest

from features.gym import exercises, library
from features.gym.exercises import Setup, entry_values, resolve, sync_plan, to_store

BENCH = library.BY_KEY['barbell_bench_press']
LIST = {'weight_increment': 5.0, 'default_rest_seconds': 90, 'stack_kg': None, 'bar_weight': None}


def test_an_entry_becomes_the_columns_of_its_row():
    values = entry_values(BENCH)
    assert values['library_key'] == 'barbell_bench_press'
    assert values['name'] == 'Bankdrücken (Langhantel)'
    assert values['muscle_group'] == 'Brust'
    assert values['secondary_muscle_groups'] == ['Trizeps', 'Schultern']
    assert values['equipment'] == 'plate_loaded'
    assert values['is_unilateral'] is False
    assert (values['weight_increment'], values['bar_weight'], values['default_rest_seconds']) == (2.5, 20.0, 180)
    assert values['stack_kg'] is None


def test_an_empty_table_gets_every_entry_and_a_synced_one_nothing():
    inserts, updates = sync_plan({})
    assert len(inserts) == len(library.LIBRARY) == 158 and updates == []
    stored = {row['library_key']: dict(row) for row in inserts}
    assert sync_plan(stored) == ([], [])


def test_a_changed_entry_updates_only_what_changed():
    stored = {e.key: entry_values(e) for e in library.LIBRARY}
    stored['barbell_bench_press'] = {**stored['barbell_bench_press'],
                                     'name': 'Bankdrücken (alt)', 'default_rest_seconds': 150}
    assert sync_plan(stored) == ([], [('barbell_bench_press',
                                       {'name': 'Bankdrücken (Langhantel)', 'default_rest_seconds': 180})])


def test_database_shapes_of_the_same_values_are_not_changes():
    # MySQL hands back tinyint 1/0 for booleans and single-precision floats;
    # a sync that read those as changes would rewrite 158 rows on every boot.
    stored = {e.key: entry_values(e) for e in library.LIBRARY}
    row = stored['dumbbell_curl']
    stored['dumbbell_curl'] = {**row, 'is_unilateral': int(row['is_unilateral']),
                               'weight_increment': row['weight_increment'] + 1e-9}
    assert sync_plan(stored) == ([], [])


def test_a_row_whose_key_left_the_list_is_left_alone():
    stored = {e.key: entry_values(e) for e in library.LIBRARY}
    stored['retired_machine'] = {'library_key': 'retired_machine', 'name': 'Alt (Maschine)'}
    assert sync_plan(stored) == ([], [])


def test_without_settings_every_value_is_the_lists():
    assert resolve(LIST, None) == Setup(5.0, 90, None, None, frozenset())
    assert resolve(LIST, {'weight_increment': None, 'default_rest_seconds': None,
                          'stack_kg': None, 'bar_weight': None}).changed == frozenset()


def test_a_stored_value_wins_and_says_so():
    setup = resolve(LIST, {'weight_increment': 8.0})
    assert setup.weight_increment == 8.0 and setup.default_rest_seconds == 90
    assert setup.changed == {'weight_increment'}


def test_a_stored_zero_bar_switches_the_lists_bar_off():
    setup = resolve({**LIST, 'bar_weight': 20.0}, {'bar_weight': 0.0})
    assert setup.bar_weight == 0.0 and setup.changed == {'bar_weight'}


def test_an_empty_stack_list_counts_as_no_setting():
    assert resolve(LIST, {'stack_kg': []}).stack_kg is None


def test_only_what_differs_from_the_list_is_stored():
    assert to_store(LIST, {'weight_increment': 5.0}, 'stack') == {'weight_increment': None}
    assert to_store(LIST, {'weight_increment': None}, 'stack') == {'weight_increment': None}
    assert to_store(LIST, {'weight_increment': 8.0}, 'stack') == {'weight_increment': 8.0}
    assert to_store(LIST, {'default_rest_seconds': 90}, 'stack') == {'default_rest_seconds': None}
    assert to_store(LIST, {'default_rest_seconds': 150}, 'stack') == {'default_rest_seconds': 150}


def test_a_zero_bar_is_stored_only_to_switch_a_bar_off():
    assert to_store(LIST, {'bar_weight': 0.0}, 'plate_loaded') == {'bar_weight': None}
    with_bar = {**LIST, 'bar_weight': 20.0}
    assert to_store(with_bar, {'bar_weight': 0.0}, 'plate_loaded') == {'bar_weight': 0.0}
    assert to_store(with_bar, {'bar_weight': 20.0}, 'plate_loaded') == {'bar_weight': None}
    assert to_store(with_bar, {'bar_weight': None}, 'plate_loaded') == {'bar_weight': None}
    assert to_store(with_bar, {'bar_weight': 15.0}, 'plate_loaded') == {'bar_weight': 15.0}


def test_stack_stops_belong_to_a_stack_only():
    assert to_store(LIST, {'stack_kg': [19.0, 5.0, 12.0]}, 'stack') == {'stack_kg': [5.0, 12.0, 19.0]}
    assert to_store(LIST, {'stack_kg': [5.0, 12.0]}, 'dumbbell') == {'stack_kg': None}
    assert to_store(LIST, {'stack_kg': None}, 'stack') == {'stack_kg': None}


def test_the_list_values_of_a_row_come_from_its_list_columns():
    class Row:
        list_increment, list_rest_seconds, list_stack_kg, list_bar_weight = 2.5, 180, None, 20.0
    assert exercises.list_values(Row()) == {'weight_increment': 2.5, 'default_rest_seconds': 180,
                                            'stack_kg': None, 'bar_weight': 20.0}


def test_the_old_names_on_an_exercise_fail_loudly():
    """A write to exercise.weight_increment once landed in a plain attribute
    and read back fine -- the list's value silently standing in for the
    lifter's. It raises now, whichever way round."""
    from models import Exercise
    exercise = Exercise(name='pytest guard')
    for field in exercises.PERSONAL_FIELDS:
        with pytest.raises(AttributeError, match='is gone'):
            getattr(exercise, field)
        with pytest.raises(AttributeError, match='is gone'):
            setattr(exercise, field, 5.0)
    with pytest.raises(AttributeError, match='is gone'):
        Exercise(name='pytest guard', weight_increment=5.0)


# -- against the database ------------------------------------------------------

@pytest.fixture()
def two_on_one_row():
    """Two fresh lifters and a key-less row (step 2.5, rest 90, a stack).
    Yields {'a', 'b', 'exercise'} ids."""
    from app import app as flask_app
    from extensions import db
    from models import AppUser, Exercise, ExerciseSettings, WorkoutSession
    from werkzeug.security import generate_password_hash

    with flask_app.app_context():
        users = [AppUser(username=f'pytest setup {x}', password_hash=generate_password_hash('x'),
                         is_admin=False) for x in 'ab']
        exercise = Exercise(name='pytest setup lift', list_increment=2.5, list_rest_seconds=90)
        db.session.add_all(users + [exercise])
        db.session.commit()
        ids = {'a': users[0].id, 'b': users[1].id, 'exercise': exercise.id}
    yield ids
    with flask_app.app_context():
        user_ids = [ids['a'], ids['b']]
        for session_ in WorkoutSession.query.filter(WorkoutSession.user_id.in_(user_ids)):
            db.session.delete(session_)
        ExerciseSettings.query.filter(ExerciseSettings.user_id.in_(user_ids)).delete()
        db.session.delete(db.session.get(Exercise, ids['exercise']))
        for user_id in user_ids:
            db.session.delete(db.session.get(AppUser, user_id))
        db.session.commit()


def test_syncing_twice_changes_nothing_the_second_time():
    from app import app as flask_app
    from extensions import db
    with flask_app.app_context():
        with db.engine.begin() as connection:
            exercises.sync_library(connection)
        with db.engine.begin() as connection:
            assert exercises.sync_library(connection) == (0, 0)


def test_two_lifters_read_their_own_values_off_one_row(two_on_one_row):
    from app import app as flask_app
    from extensions import db
    from models import Exercise, ExerciseSettings
    with flask_app.app_context():
        exercise = db.session.get(Exercise, two_on_one_row['exercise'])
        db.session.add(ExerciseSettings(user_id=two_on_one_row['a'], exercise_id=exercise.id,
                                        weight_increment=8.0))
        db.session.commit()
        mine = exercises.setups(two_on_one_row['a'], [exercise])[exercise.id]
        theirs = exercises.setups(two_on_one_row['b'], [exercise])[exercise.id]
        assert (mine.weight_increment, mine.changed) == (8.0, {'weight_increment'})
        assert (theirs.weight_increment, theirs.changed) == (2.5, frozenset())


def test_saving_stores_the_difference_and_drops_a_row_left_empty(two_on_one_row):
    from app import app as flask_app
    from extensions import db
    from models import Exercise, ExerciseSettings
    a = two_on_one_row['a']
    with flask_app.app_context():
        exercise = db.session.get(Exercise, two_on_one_row['exercise'])
        rows = ExerciseSettings.query.filter_by(user_id=a, exercise_id=exercise.id)
        exercises.save_setup(a, exercise, {'weight_increment': 8.0, 'default_rest_seconds': 90})
        db.session.commit()
        assert [(r.weight_increment, r.default_rest_seconds) for r in rows] == [(8.0, None)]
        exercises.save_setup(a, exercise, {'weight_increment': None})
        db.session.commit()
        assert rows.count() == 0


def test_a_lifters_exercises_are_the_ones_they_touched(two_on_one_row):
    """Logged, in a routine, or set up -- a row nobody touched is on the list
    for everyone, but in nobody's catalogue."""
    from app import app as flask_app
    from conftest import list_exercise
    from extensions import db
    from models import ExerciseSettings, SessionExercise, WorkoutSession
    a, b = two_on_one_row['a'], two_on_one_row['b']
    with flask_app.app_context():
        now = dt.datetime.utcnow()
        logged = WorkoutSession(name='pytest setup session', user_id=a, started_at=now,
                                finished_at=now)
        logged.exercises.append(SessionExercise(exercise_id=two_on_one_row['exercise'], position=1))
        fly = list_exercise('machine_fly')
        db.session.add_all([logged, ExerciseSettings(user_id=b, exercise_id=fly.id,
                                                     default_rest_seconds=45)])
        db.session.commit()
        assert [e.id for e in exercises.touched_exercises(a)] == [two_on_one_row['exercise']]
        assert [e.id for e in exercises.touched_exercises(b)] == [fly.id]


def test_the_picker_offers_the_list_and_nothing_retired():
    """Retired is a NULL key or one today's list no longer has."""
    from app import app as flask_app
    from conftest import list_exercise
    from extensions import db
    from models import Exercise
    with flask_app.app_context():
        list_exercise()                                   # syncs the list
        retired = [Exercise(name='pytest retired lift'),
                   Exercise(name='pytest dropped lift', library_key='pytest_dropped_key')]
        db.session.add_all(retired)
        db.session.commit()
        try:
            offered = exercises.library_exercises()
            assert sorted(e.library_key for e in offered) == sorted(library.BY_KEY)
            assert not {e.id for e in retired} & {e.id for e in offered}
        finally:
            for row in retired:
                db.session.delete(row)
            db.session.commit()
