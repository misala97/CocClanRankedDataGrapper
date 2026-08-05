# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.upgrade - Study D.

The window is a count of attacks, not a span of days: players attack at very
different rates, and a calendar window would compare one player's ten attacks
against another's two.
"""

import datetime as dt

from features.admin.insights.upgrade import (
    MIN_SIDE,
    RECOVERY_WINDOW,
    WINDOW,
    upgrade_effect,
)

T0 = dt.datetime(2026, 6, 1, 12, 0)
CURVE = {(s, d): {'n': 99, 'mean_stars': 2.0, 'triple_rate': .5, 'merged': False}
         for s in ('war', 'cwl') for d in range(-3, 4)}


def run(tag, th, stars_seq, start=0):
    """Consecutive attacks at one town hall level, ordered in time."""
    return [{'src': 'war', 'attacker_tag': tag, 'attacker_th': th,
             'defender_th': th, 'stars': s, 'destruction': 100.0,
             'clan_tag': '#US', 'war_id': start + i,
             'ended_at': T0 + dt.timedelta(days=start + i), 'attack_order': 1}
            for i, s in enumerate(stars_seq)]


def test_a_player_who_dips_after_upgrading_is_measured():
    facts = run('#A', 14, [3] * WINDOW) + run('#A', 15, [1] * WINDOW, start=WINDOW)
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert (row['from_th'], row['to_th']) == (14, 15)
    assert row['before'] == 1.0 and row['after'] == -1.0
    assert row['dip'] == -2.0


def test_a_player_who_improves_after_upgrading_reports_a_positive_dip():
    """The study must be able to find no slump at all."""
    facts = run('#A', 14, [1] * WINDOW) + run('#A', 15, [3] * WINDOW, start=WINDOW)
    assert upgrade_effect(facts, CURVE)['players'][0]['dip'] == 2.0


def test_a_player_who_never_upgraded_is_absent():
    assert upgrade_effect(run('#A', 14, [3] * 40), CURVE)['players'] == []


def test_a_player_one_attack_short_on_either_side_is_absent():
    short_after = (run('#A', 14, [3] * WINDOW) +
                   run('#A', 15, [1] * (MIN_SIDE - 1), start=WINDOW))
    short_before = (run('#B', 14, [3] * (MIN_SIDE - 1)) +
                    run('#B', 15, [1] * WINDOW, start=MIN_SIDE))
    assert upgrade_effect(short_after, CURVE)['players'] == []
    assert upgrade_effect(short_before, CURVE)['players'] == []


def test_exactly_the_minimum_on_each_side_qualifies():
    facts = (run('#A', 14, [3] * MIN_SIDE) +
             run('#A', 15, [1] * MIN_SIDE, start=MIN_SIDE))
    assert len(upgrade_effect(facts, CURVE)['players']) == 1


def test_the_window_is_capped_at_ten_attacks_a_side():
    """A player with fifty attacks before the upgrade is judged on the last ten,
    not on a career average that would drown the effect."""
    facts = (run('#A', 14, [0] * 40 + [3] * WINDOW) +
             run('#A', 15, [1] * WINDOW, start=50))
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert row['n_before'] == WINDOW
    assert row['before'] == 1.0          # the last ten, all 3-star


def test_only_the_first_upgrade_in_the_record_is_measured():
    """Two upgrades in one window would contaminate each other's comparison."""
    facts = (run('#A', 14, [3] * WINDOW) +
             run('#A', 15, [1] * WINDOW, start=WINDOW) +
             run('#A', 16, [0] * WINDOW, start=WINDOW * 2))
    rows = upgrade_effect(facts, CURVE)['players']
    assert len(rows) == 1
    assert (rows[0]['from_th'], rows[0]['to_th']) == (14, 15)


def test_attacks_are_ordered_in_time_not_by_arrival():
    """Facts come out of the loader in table order, not chronological order."""
    late = run('#A', 15, [1] * WINDOW, start=WINDOW)
    early = run('#A', 14, [3] * WINDOW)
    row = upgrade_effect(late + early, CURVE)['players'][0]
    assert row['before'] == 1.0 and row['after'] == -1.0


def test_recovery_is_the_first_point_the_trailing_mean_regains_the_baseline():
    before = run('#A', 14, [2] * WINDOW)                       # sae 0.0
    after  = run('#A', 15, [0] * RECOVERY_WINDOW + [2] * RECOVERY_WINDOW,
                 start=WINDOW)
    row = upgrade_effect(before + after, CURVE)['players'][0]
    assert row['recovered_after'] == WINDOW


def test_a_player_who_never_recovers_reports_none():
    facts = run('#A', 14, [3] * WINDOW) + run('#A', 15, [0] * WINDOW, start=WINDOW)
    assert upgrade_effect(facts, CURVE)['players'][0]['recovered_after'] is None


def test_the_aggregate_averages_the_players_it_found():
    facts = (run('#A', 14, [3] * WINDOW) + run('#A', 15, [1] * WINDOW, start=WINDOW) +
             run('#B', 14, [3] * WINDOW) + run('#B', 15, [2] * WINDOW, start=WINDOW))
    out = upgrade_effect(facts, CURVE)
    assert out['n_players'] == 2
    assert out['mean_dip'] == -1.5       # -2.0 and -1.0


def test_no_facts_yields_an_empty_aggregate_not_a_crash():
    out = upgrade_effect([], CURVE)
    assert out['players'] == [] and out['n_players'] == 0
    assert out['mean_dip'] is None and out['median_recovery'] is None
