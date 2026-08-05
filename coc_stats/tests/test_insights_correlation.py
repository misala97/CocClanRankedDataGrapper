# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.correlation - Study E.

This study shipped inline in routes.py with no tests. The zero-variance guard
below is the one that mattered: a clan where everyone scores the same makes the
denominator zero, and the page would have 500'd rather than saying "no signal".
"""

from features.admin.insights.correlation import (
    MIN_PERIODS,
    build_correlation,
    pearson_r,
)

PLAYERS = [{'tag': '#A', 'name': 'Ann', 'th': 15},
           {'tag': '#B', 'name': 'Bo',  'th': 14},
           {'tag': '#C', 'name': 'Cy',  'th': 13}]


def test_a_perfect_positive_relationship_is_one():
    assert pearson_r([1, 2, 3], [10, 20, 30]) == 1.0


def test_a_perfect_inverse_relationship_is_minus_one():
    assert pearson_r([1, 2, 3], [30, 20, 10]) == -1.0


def test_too_few_points_yield_no_coefficient():
    assert pearson_r([1, 2], [3, 4]) is None


def test_zero_variance_yields_no_coefficient_rather_than_a_crash():
    """Everyone scoring identically is a real state, not an error."""
    assert pearson_r([5, 5, 5], [1, 2, 3]) is None
    assert pearson_r([1, 2, 3], [5, 5, 5]) is None


def test_a_player_averages_across_their_periods():
    out = build_correlation({'#A': [60, 80, 70]}, {'#A': [50, 50, 50]}, PLAYERS[:1])
    row = out['players'][0]
    assert row['ranked_score'] == 70.0
    assert row['raid_score'] == 50.0
    assert row['ranked_weeks'] == 3 and row['raid_weekends'] == 3


def test_a_player_short_of_the_minimum_scores_none_but_still_appears():
    short = [70] * (MIN_PERIODS - 1)
    out = build_correlation({'#A': short}, {'#A': [50] * MIN_PERIODS}, PLAYERS[:1])
    row = out['players'][0]
    assert row['ranked_score'] is None
    assert row['raid_score'] == 50.0
    assert row['ranked_weeks'] == MIN_PERIODS - 1


def test_only_players_scored_on_both_axes_enter_the_correlation():
    out = build_correlation(
        {'#A': [60] * 3, '#B': [70] * 3, '#C': [80] * 3},
        {'#A': [10] * 3, '#B': [20] * 3, '#C': [30] * 1},   # C short on raids
        PLAYERS)
    assert out['n_correlated'] == 2


def test_a_player_with_no_data_at_all_still_appears_with_their_name():
    out = build_correlation({}, {}, PLAYERS[:1])
    row = out['players'][0]
    assert row['name'] == 'Ann' and row['th'] == 15
    assert row['ranked_score'] is None and row['raid_score'] is None


def test_players_sort_by_ranked_score_best_first():
    out = build_correlation(
        {'#A': [60] * 3, '#B': [90] * 3, '#C': [75] * 3},
        {'#A': [10] * 3, '#B': [10] * 3, '#C': [10] * 3}, PLAYERS)
    assert [p['tag'] for p in out['players']] == ['#B', '#C', '#A']


def test_no_players_yields_an_empty_result_not_a_crash():
    out = build_correlation({}, {}, [])
    assert out['players'] == [] and out['pearson_r'] is None
    assert out['n_correlated'] == 0


def test_a_zero_score_sorts_before_an_unscored_player_not_beside_them():
    """The old key treated ranked_score=0.0 and ranked_score=None as the same
    "no score" via `or -1`; a genuine zero must outrank no data at all. Player
    order here (#C, #A, #B) is chosen so a stable sort on the old, buggy key
    would place unscored #C ahead of zero-scored #A - proving the fix matters,
    not just that it changed something."""
    players = [PLAYERS[2], PLAYERS[0], PLAYERS[1]]   # #C, #A, #B
    out = build_correlation(
        {'#A': [0] * 3, '#B': [50] * 3},              # #C has no ranked scores
        {'#A': [10] * 3, '#B': [10] * 3, '#C': [10] * 3},
        players)
    assert [p['tag'] for p in out['players']] == ['#B', '#A', '#C']
