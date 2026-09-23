"""The one exercise list and each lifter's settings on top of it
(features/gym/exercises.py). The first half is pure -- plain dicts, no
database -- like test_gym_library."""
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
