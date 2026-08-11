# -*- coding: utf-8 -*-
"""Unit tests for the pure helpers behind the admin CWL Bonus console.

Three of them decide whether a finished season's unassigned bonuses stay
reachable:

  _resolve_active_month  — which season key the ledger calls "current"
  _match_season_key      — turning a bare 'YYYY-MM' into the real season key
  _rank_bonus_candidates — who fills the remaining slots
  _cwl_slot_math         — how many slots the season is worth

A calendar month's season is often keyed long-form ('2026-08-02'), so a bare
'2026-08' matches no season row and no ledger column — the failure behind both
the crashed panel and the "No CWL season found for this month." message.
"""

from types import SimpleNamespace as NS

from features.admin.routes import (
    _cwl_slot_math,
    _match_season_key,
    _rank_bonus_candidates,
    _resolve_active_month,
)

CLAN = '#CLAN'


# ── _resolve_active_month ────────────────────────────────────────────────────

def test_active_season_wins_regardless_of_key_form():
    months = ['2026-07', '2026-08-03', '2026-09']
    states = {'2026-07': 'ended', '2026-08-03': 'inWar'}
    assert _resolve_active_month(months, states, '2026-08',
                                 {'2026-08': ['2026-08-03']}) == '2026-08-03'


def test_all_ended_long_key_falls_back_to_real_season_key():
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
    months = ['2026-08-03', '2026-09']
    states = {'2026-08-03': 'ended'}
    assert _resolve_active_month(months, states, '2026-09',
                                 {'2026-08': ['2026-08-03']}) == '2026-09'


def test_plain_key_ended_season_unchanged():
    months = ['2026-07', '2026-08']
    states = {'2026-07': 'ended', '2026-08': 'ended'}
    assert _resolve_active_month(months, states, '2026-08',
                                 {'2026-08': ['2026-08']}) == '2026-08'


def test_finished_season_with_open_slots_beats_empty_current_month():
    # September has no CWL yet, August ended with bonuses still unassigned —
    # the console must land on August rather than an empty September.
    months = ['2026-07-02', '2026-08-02', '2026-09']
    states = {'2026-07-02': 'ended', '2026-08-02': 'ended'}
    assert _resolve_active_month(months, states, '2026-09',
                                 {'2026-08': ['2026-08-02']},
                                 open_slots={'2026-08-02': True}) == '2026-08-02'


def test_fully_assigned_seasons_leave_current_month_alone():
    months = ['2026-07-02', '2026-08-02', '2026-09']
    states = {'2026-07-02': 'ended', '2026-08-02': 'ended'}
    assert _resolve_active_month(months, states, '2026-09',
                                 {'2026-08': ['2026-08-02']},
                                 open_slots={'2026-08-02': False}) == '2026-09'


def test_open_slots_picks_most_recent_of_several():
    months = ['2026-07-02', '2026-08-02']
    states = {'2026-07-02': 'ended', '2026-08-02': 'ended'}
    assert _resolve_active_month(months, states, '2026-09', {},
                                 open_slots={'2026-07-02': True,
                                             '2026-08-02': True}) == '2026-08-02'


def test_running_season_outranks_an_older_one_with_open_slots():
    months = ['2026-07-02', '2026-08-02']
    states = {'2026-07-02': 'ended', '2026-08-02': 'inWar'}
    assert _resolve_active_month(months, states, '2026-08', {},
                                 open_slots={'2026-07-02': True}) == '2026-08-02'


# ── _match_season_key ────────────────────────────────────────────────────────

def test_match_season_key_prefers_exact():
    assert _match_season_key('2026-08-02', ['2026-08', '2026-08-02']) == '2026-08-02'


def test_match_season_key_upgrades_bare_month_to_real_key():
    # A stale client sending '2026-08' must still reach the August season.
    assert _match_season_key('2026-08', ['2026-07-02', '2026-08-02']) == '2026-08-02'


def test_match_season_key_takes_latest_when_month_has_two():
    assert _match_season_key('2026-06', ['2026-06-02', '2026-06-16']) == '2026-06-16'


def test_match_season_key_leaves_unknown_month_untouched():
    assert _match_season_key('2026-05', ['2026-08-02']) == '2026-05'


def test_match_season_key_handles_empty_month():
    assert _match_season_key('', ['2026-08-02']) == ''


# ── _cwl_slot_math ───────────────────────────────────────────────────────────

def war(state='warEnded', ours=True, our_stars=30, opp_stars=20,
        our_pct=90.0, opp_pct=80.0, size=15, league='Master League III'):
    """One CWLWar row; `ours` flips which side of the row our clan sits on."""
    if ours:
        return NS(state=state, team_size=size, clan_tag=CLAN, opp_tag='#OPP',
                  clan_stars=our_stars, opp_stars=opp_stars,
                  clan_destruction_pct=our_pct, opp_destruction_pct=opp_pct,
                  clan_cwl_league=league, opp_cwl_league=None)
    return NS(state=state, team_size=size, clan_tag='#OPP', opp_tag=CLAN,
              clan_stars=opp_stars, opp_stars=our_stars,
              clan_destruction_pct=opp_pct, opp_destruction_pct=our_pct,
              clan_cwl_league=None, opp_cwl_league=league)


def test_slot_math_counts_guaranteed_plus_wins():
    wars = [war(), war(), war(our_stars=10, opp_stars=25)]
    m = _cwl_slot_math('Master League III', wars, CLAN)
    assert (m['guaranteed'], m['wins'], m['total']) == (3, 2, 5)
    assert m['war_size'] == 15


def test_slot_math_wins_read_our_side_when_listed_as_opponent():
    m = _cwl_slot_math('Master League III', [war(ours=False)], CLAN)
    assert m['wins'] == 1


def test_slot_math_unfinished_wars_dont_count():
    m = _cwl_slot_math('Master League III', [war(state='inWar'), war(state='preparation')], CLAN)
    assert m['wins'] == 0 and m['total'] == 3


def test_slot_math_destruction_breaks_a_star_tie():
    tie_win  = war(our_stars=20, opp_stars=20, our_pct=61.0, opp_pct=60.0)
    tie_loss = war(our_stars=20, opp_stars=20, our_pct=59.0, opp_pct=60.0)
    assert _cwl_slot_math('Master League III', [tie_win, tie_loss], CLAN)['wins'] == 1


def test_slot_math_falls_back_to_the_war_row_for_the_league():
    m = _cwl_slot_math(None, [war(league='Champion League I')], CLAN)
    assert m['league_name'] == 'Champion League I' and m['guaranteed'] == 4


def test_slot_math_na_league_size_reports_no_total():
    m = _cwl_slot_math('Champion League I', [war(size=30)], CLAN)
    assert m['guaranteed'] is None and m['total'] is None


def test_slot_math_without_wars_is_empty_not_a_crash():
    m = _cwl_slot_math('Master League III', [], CLAN)
    assert m['total'] is None and m['wins'] == 0


# ── _rank_bonus_candidates ───────────────────────────────────────────────────

def part(tag, *, attacks=7, max_attacks=7, stars=18, destruction=90.0,
         has_bonus=False, last_bonus=None):
    return {'tag': tag, 'attacks': attacks, 'max_attacks': max_attacks,
            'stars': stars, 'destruction': destruction,
            'has_bonus': has_bonus, 'last_bonus': last_bonus}


def test_full_attendance_ranked_by_longest_wait():
    picked = _rank_bonus_candidates(
        [part('#A', last_bonus='2026-07-02'), part('#B'), part('#C', last_bonus='2026-05')], 3)
    assert [p['tag'] for p in picked] == ['#B', '#C', '#A']


def test_bonus_holders_are_never_suggested():
    picked = _rank_bonus_candidates([part('#A', has_bonus=True), part('#B')], 5)
    assert [p['tag'] for p in picked] == ['#B']


def test_slots_beyond_the_full_attendance_pool_fall_back_to_best_of_the_rest():
    # The season is over: only #A went 7/7, but three slots remain. The next
    # best attendance fills them instead of the console offering nothing.
    picked = _rank_bonus_candidates([
        part('#A'),
        part('#B', attacks=5),
        part('#C', attacks=6),
    ], 3)
    assert [p['tag'] for p in picked] == ['#A', '#C', '#B']


def test_fallback_picks_carry_their_missed_attacks():
    picked = _rank_bonus_candidates([part('#A'), part('#B', attacks=5)], 2)
    assert picked[0]['missed'] == 0
    assert picked[1]['missed'] == 2


def test_fallback_breaks_an_attack_tie_by_longest_wait_then_stars():
    picked = _rank_bonus_candidates([
        part('#A', attacks=5, last_bonus='2026-07-02', stars=20),
        part('#B', attacks=5, last_bonus='2026-05',    stars=10),
        part('#C', attacks=5, last_bonus='2026-05',    stars=15),
    ], 3)
    assert [p['tag'] for p in picked] == ['#C', '#B', '#A']


def test_no_shows_are_never_suggested():
    picked = _rank_bonus_candidates([part('#A', attacks=0), part('#B', attacks=0)], 4)
    assert picked == []


def test_more_candidates_than_slots_is_truncated():
    assert len(_rank_bonus_candidates([part('#A'), part('#B'), part('#C')], 2)) == 2


def test_no_remaining_slots_suggests_nobody():
    assert _rank_bonus_candidates([part('#A')], 0) == []
