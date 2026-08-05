# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.loaders — the fact-shaping functions.

Only the pure shaping functions are covered here. load_attack_facts() talks to
the database and is verified against live data in Task 8 instead.

The clan-identity tests are the point of this file. clan_war_member has no
clan_tag column, so the war side must take it from the war row via is_opponent;
cwl_member carries it directly. Getting this wrong is not a crash, it is a
plausible wrong number — see the spec's section 2.
"""

import datetime as dt
from types import SimpleNamespace as NS

from features.admin.insights.loaders import cwl_fact, war_fact

T0 = dt.datetime(2026, 7, 1, 12, 0)

FACT_KEYS = {'src', 'war_id', 'ended_at', 'attacker_tag', 'attacker_th',
             'defender_th', 'stars', 'destruction', 'clan_tag', 'attack_order'}


def war(clan='#US', opp='#THEM'):
    return NS(id=7, end_time=T0, clan_tag=clan, opponent_tag=opp)


def member(tag, th, is_opponent=0, clan_tag=None):
    return NS(player_tag=tag, town_hall_level=th,
              is_opponent=is_opponent, clan_tag=clan_tag)


def attack(stars=3, dest=100.0, order=4):
    return NS(attacker_tag='#A', defender_tag='#D',
              stars=stars, destruction_pct=dest, attack_order=order)


def test_war_fact_has_exactly_the_documented_keys():
    f = war_fact(attack(), member('#A', 14), member('#D', 15, 1), war())
    assert set(f) == FACT_KEYS


def test_war_attack_by_our_side_is_credited_to_our_clan():
    f = war_fact(attack(), member('#A', 14, is_opponent=0),
                 member('#D', 15, is_opponent=1), war(clan='#US', opp='#THEM'))
    assert f['clan_tag'] == '#US'


def test_war_attack_by_the_opponent_is_credited_to_the_opponent():
    """Both sides of every war feed the curve, so opponent attacks must be
    loaded — and attributed to the opponent, not silently to us."""
    f = war_fact(attack(), member('#A', 14, is_opponent=1),
                 member('#D', 15, is_opponent=0), war(clan='#US', opp='#THEM'))
    assert f['clan_tag'] == '#THEM'


def test_cwl_clan_tag_comes_from_the_member_not_from_is_opponent():
    """Our clan is 'the opponent' in rivals' CWL wars. A member flagged
    is_opponent=1 but carrying our clan_tag is us, and must be counted as us."""
    f = cwl_fact(attack(), member('#A', 14, is_opponent=1, clan_tag='#US'),
                 member('#D', 14, is_opponent=0, clan_tag='#THEM'),
                 NS(id=3, end_time=T0))
    assert f['clan_tag'] == '#US'


def test_th_differential_inputs_are_carried_through_unmodified():
    f = war_fact(attack(), member('#A', 13), member('#D', 16, 1), war())
    assert (f['attacker_th'], f['defender_th']) == (13, 16)


def test_null_stars_and_destruction_become_zero():
    """A recorded attack with no result is a zero, not a None that poisons a mean."""
    f = war_fact(NS(attacker_tag='#A', defender_tag='#D', stars=None,
                    destruction_pct=None, attack_order=None),
                 member('#A', 14), member('#D', 14, 1), war())
    assert f['stars'] == 0 and f['destruction'] == 0.0


def test_war_fact_uses_the_fallback_when_the_war_row_has_no_clan_tag():
    """The one war row predating the clan_tag column reads NULL from the DB;
    the fallback is the only thing standing between that row and a vanished fact."""
    f = war_fact(attack(), member('#A', 14, is_opponent=0),
                 member('#D', 15, is_opponent=1), war(clan=None, opp='#THEM'),
                 clan_tag_fallback='#US')
    assert f['clan_tag'] == '#US'


def test_opponent_side_of_a_null_clan_tag_war_ignores_the_fallback():
    """The opponent branch reads war.opponent_tag, never clan_tag_fallback —
    a NULL our-side tag must not leak into how the opponent is identified."""
    f = war_fact(attack(), member('#A', 14, is_opponent=1),
                 member('#D', 15, is_opponent=0), war(clan=None, opp='#THEM'),
                 clan_tag_fallback='#US')
    assert f['clan_tag'] == '#THEM'


def test_a_real_clan_tag_wins_over_the_fallback():
    """The fallback only fires when war.clan_tag is falsy; a populated row
    is trusted over the guess."""
    f = war_fact(attack(), member('#A', 14, is_opponent=0),
                 member('#D', 15, is_opponent=1), war(clan='#REAL', opp='#THEM'),
                 clan_tag_fallback='#US')
    assert f['clan_tag'] == '#REAL'


def test_null_clan_tag_with_no_fallback_stays_none():
    """war_fact stays total: no fallback supplied means the fact carries
    None rather than raising."""
    f = war_fact(attack(), member('#A', 14, is_opponent=0),
                 member('#D', 15, is_opponent=1), war(clan=None, opp='#THEM'))
    assert f['clan_tag'] is None
