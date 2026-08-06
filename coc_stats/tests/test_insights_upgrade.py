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


def test_a_second_upgrade_inside_the_after_window_clips_it():
    """The after-window for the first upgrade must not bleed into the second
    upgrade's era. Six TH15 attacks then a TH16 upgrade means the after side
    is those six attacks only, not ten."""
    facts = (run('#A', 14, [3] * WINDOW) +
             run('#A', 15, [1] * 6, start=WINDOW) +
             run('#A', 16, [0] * WINDOW, start=WINDOW + 6))
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert (row['from_th'], row['to_th']) == (14, 15)
    assert row['n_after'] == 6
    assert row['after'] == -1.0
    assert row['dip'] == -2.0


def test_clipping_below_min_side_drops_the_player():
    """If the second upgrade lands before MIN_SIDE clean attacks accumulate,
    there is nothing left to judge the first upgrade on."""
    facts = (run('#A', 14, [3] * WINDOW) +
             run('#A', 15, [1] * (MIN_SIDE - 1), start=WINDOW) +
             run('#A', 16, [0] * WINDOW, start=WINDOW + MIN_SIDE - 1))
    assert upgrade_effect(facts, CURVE)['players'] == []


def test_from_th_skips_a_none_reading_immediately_before_the_upgrade():
    """A row with no parsed town hall must not overwrite the real prior
    level - the row that happens to sit right before the upgrade attack is
    not necessarily the one that carries a usable attacker_th."""
    none_row = {'src': 'war', 'attacker_tag': '#A', 'attacker_th': None,
                'defender_th': 14, 'stars': 2, 'destruction': 100.0,
                'clan_tag': '#US', 'war_id': 9,
                'ended_at': T0 + dt.timedelta(days=9), 'attack_order': 1}
    facts = (run('#A', 14, [3] * 9, start=0) + [none_row] +
             run('#A', 16, [1] * WINDOW, start=10))
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert row['from_th'] == 14
    assert row['from_th'] is not None


def test_from_th_ignores_a_downward_glitch():
    """A stray low reading just before the upgrade (15, 14, 16) must not be
    mistaken for the pre-upgrade level - the real prior level is the running
    maximum, 15, not the glitch."""
    glitch_row = {'src': 'war', 'attacker_tag': '#A', 'attacker_th': 14,
                  'defender_th': 15, 'stars': 2, 'destruction': 100.0,
                  'clan_tag': '#US', 'war_id': 9,
                  'ended_at': T0 + dt.timedelta(days=9), 'attack_order': 1}
    facts = (run('#A', 15, [3] * 9, start=0) + [glitch_row] +
             run('#A', 16, [1] * WINDOW, start=10))
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert row['from_th'] == 15


def test_from_th_is_none_when_every_pre_upgrade_reading_is_none():
    """A player whose pre-upgrade town halls never parsed still gets an
    upgrade detected: _upgrade_index treats a missing reading as 0 via
    `or 0`, so the first real reading still looks like a rise from 0. But
    from_th must report None rather than fabricate 0 - no real pre-upgrade
    level was ever actually seen."""
    none_facts = [{'src': 'war', 'attacker_tag': '#A', 'attacker_th': None,
                   'defender_th': 14, 'stars': 2, 'destruction': 100.0,
                   'clan_tag': '#US', 'war_id': i,
                   'ended_at': T0 + dt.timedelta(days=i), 'attack_order': 1}
                  for i in range(WINDOW)]
    facts = none_facts + run('#A', 15, [1] * WINDOW, start=WINDOW)
    row = upgrade_effect(facts, CURVE)['players'][0]
    assert row['from_th'] is None
    assert row['to_th'] == 15


def test_median_recovery_is_the_median_not_the_mean():
    """With more than two recovered players, median and mean diverge - this
    must exercise that split, and the int() cast on a genuinely fractional
    median."""
    def player(tag, after_stars):
        return (run(tag, 14, [2] * WINDOW) +
                run(tag, 15, after_stars, start=WINDOW))

    facts = (player('#A', [2] * WINDOW) +                 # recovers at 5
             player('#B', [2] * WINDOW) +                 # recovers at 5
             player('#C', [0] + [2] * (WINDOW - 1)) +      # recovers at 6
             player('#D', [0] * 5 + [2] * 5))              # recovers at 10

    out = upgrade_effect(facts, CURVE)
    recovered = sorted(r['recovered_after'] for r in out['players'])
    assert recovered == [5, 5, 6, 10]
    assert out['median_recovery'] == 5          # median([5,5,6,10]) = 5.5 -> 5
    assert isinstance(out['median_recovery'], int)
