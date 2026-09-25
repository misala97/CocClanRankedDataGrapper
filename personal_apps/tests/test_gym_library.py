"""The exercise library (L1) is static data. These tests hold its mechanical
rules and the search contract; the judgement calls are in
features/gym/library.py's docstring. No ORM and no database -- plain tuples."""
import re
from collections import Counter

import pytest

from features.gym import library
from models import EQUIPMENT_TYPES, MUSCLE_GROUPS

TRAINED_GROUPS = tuple(g for g in MUSCLE_GROUPS if g not in ('Cardio', 'Sonstiges'))


def _dupes(values):
    return sorted(v for v, n in Counter(values).items() if n > 1)


def _found(query):
    hits, _ = library.find([e.search_text for e in library.LIBRARY], query)
    return {library.LIBRARY[i].key for i in hits}


def test_keys_are_unique_slugs():
    keys = [e.key for e in library.LIBRARY]
    assert _dupes(keys) == []
    assert [k for k in keys if not re.fullmatch(r'[a-z][a-z0-9_]*', k)] == []


def test_names_are_unique():
    # The add sheet shows nothing but the name, and analytics buckets a
    # lifter's volume by it: two entries of one name would read as one.
    assert _dupes([e.name for e in library.LIBRARY]) == []


def test_names_read_bewegung_geraet_variante():
    for entry in library.LIBRARY:
        move, geraet, variants = library.parse_name(entry.name)
        assert geraet in library.GERAETE, entry.name
        assert move == move.strip() == entry.movement and all(variants), entry.name


def test_movement_and_label_put_the_name_back_together():
    """The add sheet shows one movement once and each variant by its label, so
    the two halves must be the whole name -- no word lost, none doubled."""
    for entry in library.LIBRARY:
        assert f'{entry.movement} ({entry.label})' == entry.name


def test_a_movement_is_listed_in_one_section_in_the_lists_order():
    assert set(library.MOVEMENT_GROUP) == {e.movement for e in library.LIBRARY}
    firsts = {}
    for entry in library.LIBRARY:
        firsts.setdefault(entry.movement, entry.group)
    assert library.MOVEMENT_GROUP == firsts
    assert library.LIST_GROUPS[0] == library.LIBRARY[0].group
    assert set(library.LIST_GROUPS) == set(library.MOVEMENT_GROUP.values())


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


def _movement(*names):
    return {e.key for e in library.LIBRARY if e.movement in names}


def test_a_movement_name_finds_every_variant():
    """G-006: "bench" found Negativbankdrücken (Langhantel) and not its
    Kurzhantel, Maschine or Multipresse variants."""
    presses = _movement('Bankdrücken', 'Schrägbankdrücken', 'Negativbankdrücken')
    assert len(presses) == 13
    assert _found('bench') == presses
    assert _found('decline bench') == _movement('Negativbankdrücken')
    assert _found('rowing') == _movement('Rudern')
    assert _found('romanian') == _movement('Rumänisches Kreuzheben')
    assert _found('kniebeuge') >= _movement('Goblet Squat')


def test_movement_aliases_are_for_movements_with_variants():
    counts = Counter(e.movement for e in library.LIBRARY)
    assert {m: counts[m] for m in library.MOVEMENT_AKA if counts[m] < 2} == {}


def test_a_long_word_may_be_one_typo_off():
    """G-006: "Bankdrüken", one letter short, found nothing."""
    assert 'barbell_bench_press' in _found('Bankdrüken')        # a letter dropped
    assert 'barbell_bench_press' in _found('Bankdrückken')      # one added
    assert 'barbell_squat' in _found('kniebeigen')              # one changed
    assert 'cable_lat_pulldown' in _found('lat pulldwon')       # two swapped
    assert 'plate_leg_press' in _found('legpress')              # a space dropped
    assert 'barbell_bench_press' not in _found('Bankdüken')     # two off
    # What the right spelling finds, flat, incline and decline alike.
    assert _found('bankdruken kurzhantel') == _found('bankdrucken kurzhantel') == {
        'dumbbell_bench_press', 'dumbbell_incline_bench_press', 'dumbbell_decline_bench_press'}


def test_a_typo_is_only_the_fallback():
    """One edit from "bench" is "rench": with typos always on, French Press
    was a bench press."""
    texts = [e.search_text for e in library.LIBRARY]
    assert library.find(texts, 'bench')[1] == 'phrase'
    assert library.find(texts, 'Bankdrüken')[1] == 'typos'
    assert library.matches('french press', 'bench', typos=True)
    assert not library.matches('french press', 'bench')


def test_the_whole_query_as_one_run_comes_first():
    """"Push 2" is the workout Push 2, not every Push of 2026 -- and joined by
    a space, the run went on from Push's name into a date on the 23rd."""
    push2 = library.fold_apart(('Push 2', '31.07.2026 Juli 2026'))
    push = library.fold_apart(('Push', '23.09.2026 September 2026'))
    assert library.find([push2, push], 'push 2') == ([0], 'phrase')
    assert library.find([push2, push], 'Push 23.09') == ([1], 'words')
    assert library.find([push2, push], 'juli push') == ([0], 'words')


def test_a_date_is_never_a_typo():
    """One edit off "31.07" are 01.07., 03.07., 13.07. and 31.08.: a day
    with no workout showed four others."""
    days = [library.fold_apart(('Push', f'{day}.2026 Juli 2026')) for day in ('01.07', '13.07')]
    assert library.find(days, '31.07') == ([], 'words')
    assert not library.matches(days[0], '31.07', typos=True)


def test_a_short_word_stays_exact():
    """One edit is most of a four-letter word."""
    assert library.FUZZY_FROM == 5
    assert _found('bnak') == set()
    assert library.matches('fliegende kabel', 'fliegnede', typos=True)
    assert not library.matches('kabel', 'kbael', typos=True)


def test_a_query_that_folds_to_nothing_is_no_query():
    assert library.matches('bankdrucken langhantel', '-')
    assert library.matches('bankdrucken langhantel', '  ')
