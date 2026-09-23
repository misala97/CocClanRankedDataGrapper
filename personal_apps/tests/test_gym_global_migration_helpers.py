"""The pure half of migration e2c7a9f41b86 (one global exercise list, G2).

Only its helpers are tested here, loaded by path: running the migration
itself from this suite would run it against whatever database the suite
binds -- the shared dev DB. The migration runs on a scratch copy instead
(see the G1 plan)."""
import importlib.util
from pathlib import Path

import pytest

from features.gym import library

_PATH = (Path(__file__).resolve().parent.parent / 'migrations' / 'versions'
         / 'e2c7a9f41b86_gym_global_exercise_list.py')


@pytest.fixture(scope='module')
def rev():
    spec = importlib.util.spec_from_file_location('rev_e2c7a9f41b86', _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _target(key, **overrides):
    entry = library.BY_KEY[key]
    return {'id': 1, 'library_key': key, 'equipment': entry.equipment,
            'is_unilateral': entry.unilateral, 'weight_increment': entry.increment,
            'default_rest_seconds': entry.rest, 'bar_weight': entry.bar, 'stack_kg': None,
            **overrides}


def _row(**values):
    return {'id': 7, 'user_id': 1, 'n_se': 0, 'weight_increment': None,
            'default_rest_seconds': None, 'bar_weight': None, 'stack_kg': None, **values}


def test_every_production_name_lands_on_a_real_entry(rev):
    assert len(rev.PRODUCTION_2026_09) == 21
    assert sorted(set(rev.PRODUCTION_2026_09.values()) - set(library.BY_KEY)) == []


def test_every_production_exercise_has_its_own_entry(rev):
    # One entry per kind of machine: two old names never share a target, so
    # no lifter's two histories are merged into one.
    targets = list(rev.PRODUCTION_2026_09.values())
    assert len(targets) == len(set(targets))


def test_every_old_name_still_finds_its_exercise(rev):
    """The history moves to the German names; the lifters keep searching
    with the English ones they typed for months. The words that only marked
    one gym's machine are dropped with the machines' own entries."""
    markers = {library.fold(word) for word in ('Good', 'Hauptbahnhof')}
    for old, key in rev.PRODUCTION_2026_09.items():
        query = ' '.join(w for w in library.fold(old).split() if w not in markers)
        found = {e.key for e in library.LIBRARY if library.matches(e, query)}
        assert key in found, old


def test_the_mapping_decides_then_an_exact_name_or_alias(rev):
    index = rev.alias_index(library.LIBRARY)
    assert rev.resolve_key('Chest Fly (Machine)', index) == 'machine_fly'
    assert rev.resolve_key('  Chest Fly  (Machine) ', index) == 'machine_fly'
    assert rev.resolve_key('Bankdrücken (Langhantel)', index) == 'barbell_bench_press'
    assert rev.resolve_key('bankdruecken langhantel', index) == 'barbell_bench_press'
    assert rev.resolve_key('Barbell Bench Press', index) == 'barbell_bench_press'
    assert rev.resolve_key('Probe Neu', index) is None


def test_an_alias_two_entries_share_decides_nothing(rev):
    index = {'bench': {'a', 'b'}}
    assert rev.resolve_key('Bench', index) is None


def test_an_even_grid_is_what_the_step_already_says(rev):
    assert rev.is_even_grid([5, 10, 15, 20, 25, 30, 35, 40, 45, 50], 5)
    assert not rev.is_even_grid([5, 12, 19, 26], 5)
    assert not rev.is_even_grid([5, 10, 15], 2.5)
    assert not rev.is_even_grid([], 5)
    assert not rev.is_even_grid([20], 5)


def test_an_old_null_is_no_setting(rev):
    # u3's Preacher Curl had no increment and stepped 1.25; the list's 2.5
    # takes over instead of the old default being frozen in as a setting.
    assert rev.carried(_row(), _target('plate_preacher_curl')) == {}


def test_what_differed_from_the_list_is_carried(rev):
    target = _target('machine_fly')        # stack, step 5, rest 90
    assert rev.carried(_row(weight_increment=8.0, default_rest_seconds=150), target) == \
        {'weight_increment': 8.0, 'default_rest_seconds': 150}
    assert rev.carried(_row(weight_increment=5.0, default_rest_seconds=90), target) == {}


def test_stack_stops_are_carried_only_when_they_say_something(rev):
    target = _target('cable_front_raise_one_arm')        # a cable stack, step 5
    grid = [float(k) for k in range(5, 55, 5)]
    assert rev.carried(_row(weight_increment=5.0, stack_kg=grid), target) == {}
    assert rev.carried(_row(stack_kg=[5.0, 12.0, 19.0]), target) == {'stack_kg': [5.0, 12.0, 19.0]}
    assert rev.carried(_row(stack_kg='[19, 5, 12]'), target) == {'stack_kg': [5.0, 12.0, 19.0]}
    plate = _target('plate_preacher_curl')
    assert rev.carried(_row(stack_kg=[5.0, 12.0, 19.0]), plate) == {}


def test_a_bar_is_carried_only_when_it_differs(rev):
    assert rev.carried(_row(bar_weight=20.0), _target('barbell_overhead_press')) == {}
    assert rev.carried(_row(bar_weight=0.0), _target('machine_fly')) == {}
    assert rev.carried(_row(bar_weight=15.0), _target('barbell_overhead_press')) == {'bar_weight': 15.0}
    # An old NULL on a barbell entry: no setting, the list's bar applies.
    assert rev.carried(_row(bar_weight=None), _target('barbell_overhead_press')) == {}


def test_the_row_with_the_most_history_wins_then_the_oldest(rev):
    rows = [{'id': 5, 'n_se': 3}, {'id': 2, 'n_se': 9}, {'id': 1, 'n_se': 9}]
    assert rev.winner(rows)['id'] == 1
    assert rev.winner([{'id': 4, 'n_se': 0}])['id'] == 4


def test_a_changed_side_or_loading_is_reported(rev):
    """One side or both decides every volume figure of the history, so the
    deploy log names each row whose list entry reads it differently."""
    target = _target('plate_lateral_raise')             # plate-loaded, one side
    assert rev.fact_changes(_row(is_unilateral=True, equipment='plate_loaded'), target) == []
    assert rev.fact_changes(_row(is_unilateral=0, equipment='stack'), target) == [
        'is_unilateral False -> True', 'equipment stack -> plate_loaded']


def test_a_downgrade_is_refused(rev):
    with pytest.raises(RuntimeError, match='backup'):
        rev.downgrade()
