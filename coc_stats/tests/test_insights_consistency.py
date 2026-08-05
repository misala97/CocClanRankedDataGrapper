# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.consistency - Study C.

The mean is already elsewhere in the app. What is new here is the spread, and
the finding is the contrast: two players with near-identical averages and very
different sigma are different roster decisions.
"""

from features.admin.insights.consistency import (
    MEAN_BAND,
    consistency,
    contrast_pair,
    series_stats,
)


def test_series_stats_reports_spread_and_extremes():
    s = series_stats([50, 60, 70])
    assert s['n'] == 3
    assert s['mean'] == 60
    assert s['floor'] == 50 and s['ceiling'] == 70
    assert round(s['sd'], 3) == 8.165


def test_a_flat_series_has_no_spread():
    assert series_stats([70, 70, 70])['sd'] == 0.0


def test_a_single_value_has_no_spread_rather_than_crashing():
    s = series_stats([70])
    assert s['n'] == 1 and s['sd'] == 0.0


def test_an_empty_series_is_none():
    assert series_stats([]) is None


def test_players_sort_steadiest_first():
    rows = consistency({'#SWINGY': [40, 100, 40, 100, 40, 100],
                        '#STEADY': [70, 71, 69, 70, 71, 69]}, min_n=6)
    assert [r['tag'] for r in rows] == ['#STEADY', '#SWINGY']


def test_a_player_one_week_short_is_thin_and_sorted_last():
    rows = consistency({'#THIN':  [70, 70, 70, 70, 70],
                        '#SOLID': [40, 100, 40, 100, 40, 100]}, min_n=6)
    assert rows[0]['tag'] == '#SOLID'
    assert rows[1]['tag'] == '#THIN' and rows[1]['thin'] is True


def test_a_player_exactly_at_the_threshold_is_not_thin():
    rows = consistency({'#EDGE': [70] * 6}, min_n=6)
    assert rows[0]['thin'] is False


def test_the_contrast_pair_matches_means_and_maximises_the_sigma_gap():
    """The finding: same average, different reliability."""
    rows = consistency({'#STEADY':  [70, 70, 70, 70, 70, 70],
                        '#STREAKY': [40, 100, 40, 100, 40, 100],   # mean 70
                        '#OTHER':   [20, 22, 21, 20, 22, 21]}, min_n=6)
    pair = contrast_pair(rows)
    assert pair['steady']['tag'] == '#STEADY'
    assert pair['streaky']['tag'] == '#STREAKY'


def test_no_pair_when_no_two_players_share_a_mean():
    rows = consistency({'#A': [90] * 6, '#B': [20] * 6}, min_n=6)
    assert contrast_pair(rows, mean_band=MEAN_BAND) is None


def test_thin_players_are_never_named_in_the_contrast():
    """Bluntness is a tone decision; sample size is not."""
    rows = consistency({'#STEADY': [70] * 6,
                        '#THIN':   [40, 100, 40, 100]}, min_n=6)
    assert contrast_pair(rows) is None


def test_no_players_yields_no_rows_and_no_pair():
    assert consistency({}, min_n=6) == []
    assert contrast_pair([]) is None
