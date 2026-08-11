# -*- coding: utf-8 -*-
"""Unit tests for _resolve_active_month — the pure helper behind /admin/cwl-bonus
that picks which season column the ledger treats as "current".

The invariant under test: the returned month must ALWAYS be a key of `months`,
because the client sorts the ledger by `by_month[current_month]` and crashes on
a key that has no column (the "Could not load CWL data." panel after a season
keyed long-form, e.g. '2026-08-03', had ended).
"""

from features.admin.routes import _resolve_active_month


def test_active_season_wins_regardless_of_key_form():
    months = ['2026-07', '2026-08-03', '2026-09']
    states = {'2026-07': 'ended', '2026-08-03': 'inWar'}
    assert _resolve_active_month(months, states, '2026-08',
                                 {'2026-08': ['2026-08-03']}) == '2026-08-03'


def test_all_ended_long_key_falls_back_to_real_season_key():
    # The bug: calendar month '2026-08' is not in months (its season is keyed
    # '2026-08-03'), so the old fallback returned a month with no ledger column.
    months = ['2026-07', '2026-08-03', '2026-09']
    states = {'2026-07': 'ended', '2026-08-03': 'ended'}
    resolved = _resolve_active_month(months, states, '2026-08',
                                     {'2026-08': ['2026-08-03']})
    assert resolved == '2026-08-03'
    assert resolved in months


def test_all_ended_two_seasons_in_month_picks_latest():
    months = ['2026-08-03', '2026-08-17']
    states = {'2026-08-03': 'ended', '2026-08-17': 'ended'}
    assert _resolve_active_month(months, states, '2026-08',
                                 {'2026-08': ['2026-08-03', '2026-08-17']}) == '2026-08-17'


def test_no_season_this_month_keeps_bare_calendar_month():
    # Nothing recorded for '2026-09' — the bare placeholder is itself in months,
    # so the fallback stays as-is (empty column, no crash).
    months = ['2026-08-03', '2026-09']
    states = {'2026-08-03': 'ended'}
    assert _resolve_active_month(months, states, '2026-09',
                                 {'2026-08': ['2026-08-03']}) == '2026-09'


def test_plain_key_ended_season_unchanged():
    # Season keyed exactly 'YYYY-MM' and ended: old behavior was already fine.
    months = ['2026-07', '2026-08']
    states = {'2026-07': 'ended', '2026-08': 'ended'}
    assert _resolve_active_month(months, states, '2026-08',
                                 {'2026-08': ['2026-08']}) == '2026-08'
