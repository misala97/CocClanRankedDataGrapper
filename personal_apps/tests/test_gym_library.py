"""The exercise library (L1) is data under review. These tests hold its
mechanical rules; the judgement calls are in features/gym/library.py's
docstring. No ORM and no database -- plain tuples, like test_gym_matching."""
import re
from collections import Counter

import pytest

from features.gym import library
from features.gym.library_mapping import OPEN, PRODUCTION_2026_09
from features.gym.matching import normalise
from models import EQUIPMENT_TYPES, MUSCLE_GROUPS

TRAINED_GROUPS = tuple(g for g in MUSCLE_GROUPS if g not in ('Cardio', 'Sonstiges'))


def _dupes(values):
    return sorted(v for v, n in Counter(values).items() if n > 1)


def test_keys_are_unique_slugs():
    keys = [e.key for e in library.LIBRARY]
    assert _dupes(keys) == []
    assert [k for k in keys if not re.fullmatch(r'[a-z][a-z0-9_]*', k)] == []


def test_names_are_unique_and_read_bewegung_geraet_variante():
    assert _dupes(normalise(e.name) for e in library.LIBRARY) == []
    for entry in library.LIBRARY:
        move, geraet, variants = library.parse_name(entry.name)
        assert geraet in library.GERAETE, entry.name
        assert move == move.strip() and all(variants), entry.name


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
    counts = Counter(e.group for e in library.SEEDABLE)
    assert {g: counts[g] for g in TRAINED_GROUPS if counts[g] < 3} == {}


def test_the_geraet_decides_the_loading():
    for entry in library.LIBRARY:
        _, geraet, variants = library.parse_name(entry.name)
        if geraet == 'Körpergewicht':
            assert entry.equipment == 'bodyweight', entry.name
            continue
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


def test_a_search_term_never_points_at_two_exercises():
    owner = {}
    for entry in library.LIBRARY:
        for text in (entry.name, *entry.aka):
            term = normalise(text)
            assert owner.setdefault(term, entry.key) == entry.key, (
                f'{text!r} names both {owner[term]} and {entry.key}')


def test_only_bodyweight_waits_for_the_owners_call():
    left_out = {e.key for e in library.LIBRARY} - {e.key for e in library.SEEDABLE}
    assert left_out == {e.key for e in library.LIBRARY if e.equipment == 'bodyweight'}
    assert all(e.equipment in EQUIPMENT_TYPES for e in library.SEEDABLE)


def test_every_production_exercise_has_its_own_entry():
    targets = list(PRODUCTION_2026_09.values())
    assert [k for k in targets if k not in library.BY_KEY] == []
    # Two production exercises on one entry would merge two histories.
    assert _dupes(targets) == []
    assert set(OPEN) <= set(PRODUCTION_2026_09)
