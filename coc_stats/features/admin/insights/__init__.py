# -*- coding: utf-8 -*-
"""Assembles the five Insights studies into one briefing.

Every study is viewer-invariant - the same answer for every admin - so the
result is cached rather than recomputed per view. The key is a census of the
source tables, so new wars, weeks or raids invalidate it on arrival; the TTL is
only a backstop for edits that do not change a row count.

Row counts, not the spec's proposed max(last_updated): three of the four
source tables (ClanWarAttack, CWLAttack, RaidWeekendLog) carry no such column,
so a row-count census is the cheap check that actually exists on all four.

build_briefing() returns the cached dict itself, not a copy. Callers must
treat it as immutable - re-sorting one of its lists in place, for instance,
would corrupt what every other request sees for the rest of the TTL.
"""

import datetime as dt

from . import benchmark, consistency, correlation, curve, upgrade
from .loaders import load_attack_facts, load_correlation_inputs, resolve_clan_tag

_CACHE = {}
_TTL   = 600          # seconds


def _data_version():
    """Row counts across the source tables. Cheap, and it changes on any sync."""
    from models import ClanWarAttack, CWLAttack, RaidWeekendLog, RankedWeek
    return (ClanWarAttack.query.count(), CWLAttack.query.count(),
            RankedWeek.query.count(), RaidWeekendLog.query.count())


def curve_rows(fitted):
    """The curve reshaped for display: {src: [row, ...]} ordered -3 -> +3.

    The curve itself is keyed by a (src, diff) tuple, which a template cannot
    index cleanly. Shaping it here keeps the studies' own contract untouched
    and keeps the reshaping out of Jinja, where it could not be tested.
    """
    out = {}
    for src, _ in fitted:
        if src in out:
            continue
        out[src] = [dict(fitted[(src, d)], diff=d)
                    for d in range(-curve.DIFF_CLAMP, curve.DIFF_CLAMP + 1)]
    return out


def group_same_th_rate(rows):
    """The rivals' combined same-town-hall triple rate, for the us-vs-them line.

    Weighted by each clan's attack count rather than averaging the per-clan
    rates: a clan with six same-TH attacks should not swing the group figure
    as hard as one with two hundred.
    """
    rivals = [r for r in rows
              if not r['is_ours'] and r['same_th_triple_rate'] is not None]
    n = sum(r['same_th_n'] for r in rivals)
    if not n:
        return None, 0
    return sum(r['same_th_triple_rate'] * r['same_th_n'] for r in rivals) / n, n


def build_briefing():
    """-> the whole page's data. Requires an app context."""
    key = _data_version()
    now = dt.datetime.now().timestamp()
    hit = _CACHE.get(key)
    if hit and hit[0] > now:
        return hit[1]

    from models import Player

    players      = Player.query.all()
    names        = {p.tag: p.name or p.tag for p in players}
    in_clan_tags = {p.tag for p in players if p.in_clan}

    facts = load_attack_facts()
    fitted = curve.build_curve(facts)
    our_tag = resolve_clan_tag()

    ranked_scores, raid_scores, corr_roster, games, attacks = \
        load_correlation_inputs()

    ranked_rows = consistency.consistency(ranked_scores,
                                          consistency.MIN_RANKED_WEEKS)
    raid_rows   = consistency.consistency(raid_scores,
                                          consistency.MIN_RAID_WEEKENDS)

    bench      = benchmark.clan_ranking(facts, fitted, our_tag)
    group_rate, group_n = group_same_th_rate(bench)

    data = {
        'curve':              fitted,
        'curve_rows':         curve_rows(fitted),
        # The one row the page leads with, resolved here so the template does
        # not have to search a 22-row list for it.
        'us':                 next((r for r in bench if r['is_ours']), None),
        'group_same_th':      group_rate,
        'group_same_th_n':    group_n,
        # Scope is in_clan=True: this study ranks who on OUR roster beats
        # the curve, a roster decision. upgrade.py below deliberately stays
        # unscoped (it studies a phenomenon, not a roster) - the two differ
        # on purpose, do not "fix" them to match.
        'players_sae':        curve.player_sae(facts, fitted, roster=in_clan_tags),
        'benchmark':          bench,
        'consistency_ranked': ranked_rows,
        'consistency_raid':   raid_rows,
        'contrast_ranked':    consistency.contrast_pair(ranked_rows),
        'upgrade':            upgrade.upgrade_effect(facts, fitted),
        'correlation':        correlation.build_correlation(
                                  ranked_scores, raid_scores, corr_roster,
                                  games, attacks),
        'names':              names,
        'our_clan_tag':       our_tag,
        # Surfaced so the page can state its own cut-offs instead of hardcoding
        # numbers that would drift the moment a threshold is retuned.
        'thresholds': {
            'player_attacks': curve.MIN_PLAYER_ATTACKS,
            'ranked_weeks':   consistency.MIN_RANKED_WEEKS,
            'raid_weekends':  consistency.MIN_RAID_WEEKENDS,
            'clan_attacks':   benchmark.MIN_CLAN_ATTACKS,
        },
    }

    _CACHE.clear()          # only the newest version is worth holding
    _CACHE[key] = (now + _TTL, data)
    return data
