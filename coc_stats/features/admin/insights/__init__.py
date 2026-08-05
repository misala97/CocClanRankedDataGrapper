# -*- coding: utf-8 -*-
"""Assembles the five Insights studies into one briefing.

Every study is viewer-invariant - the same answer for every admin - so the
result is cached rather than recomputed per view. The key is a census of the
source tables, so new wars, weeks or raids invalidate it on arrival; the TTL is
only a backstop for edits that do not change a row count.
"""

import datetime as dt

from . import benchmark, consistency, correlation, curve, upgrade
from .loaders import load_attack_facts, resolve_clan_tag

_CACHE = {}
_TTL   = 600          # seconds


def _data_version():
    """Row counts across the source tables. Cheap, and it changes on any sync."""
    from models import ClanWarAttack, CWLAttack, RaidWeekendLog, RankedWeek
    return (ClanWarAttack.query.count(), CWLAttack.query.count(),
            RankedWeek.query.count(), RaidWeekendLog.query.count())


def build_briefing():
    """-> the whole page's data. Requires an app context."""
    key = _data_version()
    now = dt.datetime.now().timestamp()
    hit = _CACHE.get(key)
    if hit and hit[0] > now:
        return hit[1]

    from models import Player

    facts = load_attack_facts()
    fitted = curve.build_curve(facts)
    our_tag = resolve_clan_tag()

    ranked_scores, raid_scores, roster, games, attacks = \
        correlation.load_correlation_inputs()

    ranked_rows = consistency.consistency(ranked_scores,
                                          consistency.MIN_RANKED_WEEKS)
    raid_rows   = consistency.consistency(raid_scores,
                                          consistency.MIN_RAID_WEEKENDS)

    data = {
        'curve':              fitted,
        'players_sae':        curve.player_sae(facts, fitted),
        'benchmark':          benchmark.clan_ranking(facts, fitted, our_tag),
        'consistency_ranked': ranked_rows,
        'consistency_raid':   raid_rows,
        'contrast_ranked':    consistency.contrast_pair(ranked_rows),
        'upgrade':            upgrade.upgrade_effect(facts, fitted),
        'correlation':        correlation.build_correlation(
                                  ranked_scores, raid_scores, roster,
                                  games, attacks),
        'names':              {p.tag: p.name or p.tag for p in Player.query.all()},
        'our_clan_tag':       our_tag,
    }

    _CACHE.clear()          # only the newest version is worth holding
    _CACHE[key] = (now + _TTL, data)
    return data
