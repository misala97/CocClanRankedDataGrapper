# -*- coding: utf-8 -*-
"""Study B - the clan measured against the 21 others in its CWL group.

Every other study asks who among us is best. This one asks whether we are any
good, which only works because the CWL tables hold the whole group rather than
just our own wars.

Clans are ranked on stars above expectation rather than raw stars. A clan whose
roster sits above its opponents' draws easier matchups all season and would win
a raw-stars table without attacking any better.
"""

from collections import defaultdict

from .curve import clamp_diff, sae_of

MIN_CLAN_ATTACKS = 30   # below this a clan is shown but not ranked


def clan_ranking(facts, curve, our_tag, min_attacks=MIN_CLAN_ATTACKS):
    """-> one row per clan, best first, thin clans last.

    CWL only. Regular war has no rival population to compare against.

    n is every CWL attack the clan has, the figure a reader wants to see.
    n_scored is how many of those actually landed in a curve bucket with an
    expectation (mirrors curve.player_sae's n) - thin is gated on n_scored,
    not n, since a clan with plenty of raw attacks but few scorable ones is
    still a thin sample for this study's purpose.
    """
    by_clan = defaultdict(list)
    for f in facts:
        if f['src'] == 'cwl':
            by_clan[f['clan_tag']].append(f)

    rows = []
    for tag, clan_facts in by_clan.items():
        deltas = [d for d in (sae_of(f, curve) for f in clan_facts) if d is not None]
        if not deltas:
            continue
        same_th = [f for f in clan_facts
                   if clamp_diff(f['attacker_th'], f['defender_th']) == 0]
        rows.append({
            'clan_tag':            tag,
            'n':                   len(clan_facts),
            'n_scored':            len(deltas),
            'sae':                 sum(deltas) / len(deltas),
            'same_th_n':           len(same_th),
            'same_th_triple_rate': (sum(1 for f in same_th if f['stars'] == 3)
                                    / len(same_th)) if same_th else None,
            'is_ours':             tag == our_tag,
            'thin':                len(deltas) < min_attacks,
        })

    rows.sort(key=lambda r: (r['thin'], -r['sae']))
    ranked = sum(1 for r in rows if not r['thin'])
    for i, r in enumerate(rows, 1):
        r['rank'] = i
        # A percentile against a single clan says nothing, and thin clans are
        # not in the ranked population at all.
        r['percentile'] = (None if r['thin'] or ranked < 2 else
                           round(100.0 * (ranked - r['rank']) / (ranked - 1), 1))
    return rows
