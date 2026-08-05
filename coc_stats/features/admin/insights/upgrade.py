# -*- coding: utf-8 -*-
"""Study D - what a town hall upgrade costs, and for how long.

The weakest of the five, and it is presented as an observation rather than a
verdict. Only a handful of players clear the before/after thresholds, and an
upgrade coincides with new troops, new defences and whatever else was
happening that month; this measures the bundle, not the upgrade.

The window is a count of attacks rather than a span of days. Players attack at
very different rates, and a calendar window would compare one player's ten
attacks against another's two.
"""

import statistics
from collections import defaultdict

from .curve import sae_of

WINDOW          = 10   # attacks either side of the upgrade
MIN_SIDE        = 5    # fewer than this on either side and the player is skipped
RECOVERY_WINDOW = 5    # trailing attacks averaged when testing for recovery


def _mean(values):
    return sum(values) / len(values) if values else None


def _upgrade_index(facts):
    """Index of the first attack at a higher town hall than anything before it.

    Only the first upgrade is measured. A second upgrade inside the same window
    would contaminate the comparison it is part of.
    """
    ths = [f['attacker_th'] or 0 for f in facts]
    return next((i for i in range(1, len(ths)) if ths[i] > max(ths[:i])), None)


def _recovery_point(after_sae, baseline):
    """Attacks after the upgrade before a trailing mean regains the baseline."""
    for j in range(RECOVERY_WINDOW - 1, len(after_sae)):
        window = after_sae[j - RECOVERY_WINDOW + 1: j + 1]
        if _mean(window) >= baseline:
            return j + 1
    return None


def upgrade_effect(facts, curve):
    """-> {'players', 'n_players', 'mean_dip', 'n_recovered', 'median_recovery'}"""
    by_player = defaultdict(list)
    for f in facts:
        by_player[f['attacker_tag']].append(f)

    rows = []
    for tag, player_facts in by_player.items():
        # The loader returns table order; the whole study depends on time order.
        ordered = sorted(player_facts,
                         key=lambda f: (f['ended_at'], f['attack_order'] or 0))
        idx = _upgrade_index(ordered)
        if idx is None:
            continue

        before = ordered[max(0, idx - WINDOW):idx]
        after  = ordered[idx:idx + WINDOW]
        b_sae  = [d for d in (sae_of(f, curve) for f in before) if d is not None]
        a_sae  = [d for d in (sae_of(f, curve) for f in after) if d is not None]
        if len(b_sae) < MIN_SIDE or len(a_sae) < MIN_SIDE:
            continue

        baseline = _mean(b_sae)
        rows.append({
            'tag':             tag,
            'from_th':         ordered[idx - 1]['attacker_th'],
            'to_th':           ordered[idx]['attacker_th'],
            'before':          baseline,
            'after':           _mean(a_sae),
            'dip':             _mean(a_sae) - baseline,
            'n_before':        len(b_sae),
            'n_after':         len(a_sae),
            'recovered_after': _recovery_point(a_sae, baseline),
        })

    rows.sort(key=lambda r: r['dip'])
    recoveries = [r['recovered_after'] for r in rows if r['recovered_after']]
    return {
        'players':         rows,
        'n_players':       len(rows),
        'mean_dip':        _mean([r['dip'] for r in rows]),
        'n_recovered':     len(recoveries),
        'median_recovery': int(statistics.median(recoveries)) if recoveries else None,
    }
