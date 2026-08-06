# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.benchmark - Study B.

The only study that answers "are we actually good" rather than "who among us
is best", because the CWL tables hold all 22 clans in the group.

Clans are ranked on stars above expectation, not raw stars: a clan whose roster
happens to sit above its opponents' would otherwise win on matchup luck.
"""

from features.admin.insights.benchmark import MIN_CLAN_ATTACKS, clan_ranking

CURVE = {('cwl', d): {'n': 99, 'mean_stars': 2.0, 'triple_rate': .5, 'merged': False}
         for d in range(-3, 4)}
CURVE.update({('war', d): {'n': 99, 'mean_stars': 2.0, 'triple_rate': .5,
                           'merged': False} for d in range(-3, 4)})


def att(clan, stars, diff=0, src='cwl'):
    return {'src': src, 'clan_tag': clan, 'attacker_tag': '#P', 'attacker_th': 14,
            'defender_th': 14 + diff, 'stars': stars, 'destruction': 100.0,
            'war_id': 1, 'ended_at': None, 'attack_order': 1}


def clan(tag, stars, n=MIN_CLAN_ATTACKS, diff=0):
    return [att(tag, stars, diff) for _ in range(n)]


def test_clans_rank_by_stars_above_expectation():
    rows = clan_ranking(clan('#GOOD', 3) + clan('#BAD', 1), CURVE, '#GOOD')
    assert [r['clan_tag'] for r in rows] == ['#GOOD', '#BAD']
    assert rows[0]['sae'] == 1.0 and rows[1]['sae'] == -1.0


def test_regular_war_attacks_are_excluded():
    """War has no rival population - only CWL supports a benchmark."""
    facts = clan('#US', 3) + [att('#US', 0, src='war') for _ in range(50)]
    assert clan_ranking(facts, CURVE, '#US')[0]['n'] == MIN_CLAN_ATTACKS


def test_our_clan_is_flagged_and_the_others_are_not():
    rows = {r['clan_tag']: r for r in
            clan_ranking(clan('#US', 3) + clan('#THEM', 1), CURVE, '#US')}
    assert rows['#US']['is_ours'] is True
    assert rows['#THEM']['is_ours'] is False


def test_same_th_triple_rate_counts_only_equal_town_halls():
    facts = (clan('#US', 3, n=10, diff=0) + clan('#US', 0, n=10, diff=0) +
             clan('#US', 3, n=10, diff=2))
    row = clan_ranking(facts, CURVE, '#US')[0]
    assert row['same_th_n'] == 20
    assert row['same_th_triple_rate'] == 0.5


def test_a_clan_that_never_faced_an_equal_town_hall_reports_no_rate():
    row = clan_ranking(clan('#US', 3, diff=2), CURVE, '#US')[0]
    assert row['same_th_n'] == 0
    assert row['same_th_triple_rate'] is None


def test_a_thin_clan_is_marked_and_sorted_last_despite_a_better_figure():
    facts = clan('#THIN', 3, n=MIN_CLAN_ATTACKS - 1) + clan('#SOLID', 2)
    rows = clan_ranking(facts, CURVE, '#SOLID')
    assert rows[0]['clan_tag'] == '#SOLID'
    assert rows[1]['thin'] is True


def test_rank_is_dense_and_one_based():
    rows = clan_ranking(clan('#A', 3) + clan('#B', 2) + clan('#C', 1), CURVE, '#A')
    assert [r['rank'] for r in rows] == [1, 2, 3]


def test_percentile_spans_the_ranked_clans_only():
    facts = (clan('#A', 3) + clan('#B', 2) + clan('#C', 1) +
             clan('#THIN', 3, n=2))
    rows = {r['clan_tag']: r for r in clan_ranking(facts, CURVE, '#A')}
    assert rows['#A']['percentile'] == 100.0
    assert rows['#C']['percentile'] == 0.0
    assert rows['#B']['percentile'] == 50.0
    assert rows['#THIN']['percentile'] is None


def test_a_lone_clan_has_no_percentile():
    """One clan is not a benchmark - a percentile here would be meaningless."""
    assert clan_ranking(clan('#US', 3), CURVE, '#US')[0]['percentile'] is None


def test_no_facts_yields_no_rows():
    assert clan_ranking([], CURVE, '#US') == []
