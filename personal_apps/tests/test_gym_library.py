"""The exercise library (L1) is static data. These tests hold its mechanical
rules and the search contract; the judgement calls are in
features/gym/library.py's docstring. No ORM and no database -- plain tuples,
like test_gym_matching."""
import re
from collections import Counter

import pytest

from features.gym import library
from models import EQUIPMENT_TYPES, MUSCLE_GROUPS

TRAINED_GROUPS = tuple(g for g in MUSCLE_GROUPS if g not in ('Cardio', 'Sonstiges'))


def _dupes(values):
    return sorted(v for v, n in Counter(values).items() if n > 1)


def _found(query):
    return {e.key for e in library.LIBRARY if library.matches(e, query)}


def test_keys_are_unique_slugs():
    keys = [e.key for e in library.LIBRARY]
    assert _dupes(keys) == []
    assert [k for k in keys if not re.fullmatch(r'[a-z][a-z0-9_]*', k)] == []


def test_names_read_bewegung_geraet_variante():
    for entry in library.LIBRARY:
        move, geraet, variants = library.parse_name(entry.name)
        assert geraet in library.GERAETE, entry.name
        assert move == move.strip() == entry.movement and all(variants), entry.name


def test_a_name_off_the_pattern_is_refused():
    for name in ('Bankdrücken', 'Bankdrücken (Langhantel', 'Rudern, eng (Kabel)', 'Latzug (Kabel) eng'):
        with pytest.raises(ValueError):
            library.parse_name(name)


def test_groups_come_from_the_app():
    for entry in library.LIBRARY:
        assert entry.group in TRAINED_GROUPS, entry.name
        assert set(entry.secondary) <= set(TRAINED_GROUPS), entry.name
        assert entry.group not in entry.secondary, entry.name
        assert _dupes(entry.secondary) == [], entry.name


def test_every_trained_group_has_a_real_choice():
    counts = Counter(e.group for e in library.LIBRARY)
    assert {g: counts[g] for g in TRAINED_GROUPS if counts[g] < 3} == {}


def test_the_geraet_decides_the_loading():
    for entry in library.LIBRARY:
        _, geraet, variants = library.parse_name(entry.name)
        assert entry.equipment in EQUIPMENT_TYPES, entry.name
        if geraet == 'Maschine':
            plates = 'Scheiben' in variants
            assert entry.equipment == ('plate_loaded' if plates else 'stack'), entry.name
        # Only a free bar's own weight sits inside the logged number.
        has_bar = geraet in ('Langhantel', 'SZ-Stange', 'Trap-Bar')
        assert (entry.bar is not None) == has_bar, entry.name


def test_one_arm_or_one_leg_logs_one_side():
    for entry in library.LIBRARY:
        _, _, variants = library.parse_name(entry.name)
        if any(v in library.ONE_SIDE_VARIANTS for v in variants):
            assert entry.unilateral, entry.name


def test_a_plate_loaded_machine_must_say_whether_it_logs_per_side():
    with pytest.raises(ValueError):
        library._e('x', 'Brustpresse (Maschine, Scheiben)', 'Brust')


def test_defaults_are_usable():
    for entry in library.LIBRARY:
        assert entry.increment > 0, entry.name
        assert entry.rest in library.REST_TIERS, entry.name


def test_a_name_or_alias_never_belongs_to_two_exercises():
    owner = {}
    for entry in library.LIBRARY:
        for text in (entry.name, *entry.aka):
            term = library.fold(text)
            assert owner.setdefault(term, entry.key) == entry.key, (
                f'{text!r} names both {owner[term]} and {entry.key}')


def test_english_and_german_names_both_find_an_exercise():
    """Owner, 2026-09-23: "chest fly and butterfly should both work"."""
    for query in ('butterfly', 'Chest Fly', 'chest fly machine', 'pec deck'):
        assert 'machine_fly' in _found(query), query


def test_spelling_without_umlauts_or_hyphens_still_finds():
    assert 'dumbbell_bench_press' in _found('bankdruecken kurzhantel')
    assert 'dumbbell_bench_press' in _found('Bankdrucken KH')
    assert 'dumbbell_pullover' in _found('ueberzuege')
    assert 'tbar_row' in _found('t bar row')
    assert 'cable_external_rotation' in _found('aussenrotation')


def test_a_query_narrows_instead_of_widening():
    assert _found('lat raise') >= {'dumbbell_lateral_raise', 'machine_lateral_raise'}
    assert {k for k in _found('lat raise') if 'pulldown' in k} == set()
    assert _found('zzz') == set()
