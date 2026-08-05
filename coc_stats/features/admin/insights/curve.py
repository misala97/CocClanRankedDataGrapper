# -*- coding: utf-8 -*-
"""Study A - what attacking up actually costs, and who beats that cost.

The curve is fitted over every attack in the table: both sides of every war,
and every clan in the CWL group. A baseline drawn only from our own attacks
cannot say whether our attacks are good.

War and CWL are fitted separately. They are not the same game - 76.6% against
44.8% same-town-hall triples on current data - and pooling them would flatter
CWL and libel war.
"""

from collections import defaultdict

DIFF_CLAMP         = 3      # differentials beyond this are single attacks, not a bucket
MIN_BUCKET_N       = 20     # below this a bucket merges toward zero
MIN_PLAYER_ATTACKS = 8      # below this a player is listed but not ranked


def clamp_diff(attacker_th, defender_th):
    """Town-hall differential, clamped to the range that carries enough attacks
    to mean anything. The war tail runs to +7 on single attacks.

    A missing town hall clamps rather than raising: one unparseable member row
    should cost one attack's precision, not the whole study.
    """
    return max(-DIFF_CLAMP, min(DIFF_CLAMP, (defender_th or 0) - (attacker_th or 0)))


def _bucket(group, merged):
    n = len(group)
    if not n:
        return {'n': 0, 'mean_stars': None, 'triple_rate': None, 'merged': merged}
    return {
        'n':           n,
        'mean_stars':  sum(f['stars'] for f in group) / n,
        'triple_rate': sum(1 for f in group if f['stars'] == 3) / n,
        'merged':      merged,
    }


def build_curve(facts):
    """-> {(src, diff): bucket} with every diff in [-DIFF_CLAMP, DIFF_CLAMP].

    Thin buckets merge toward zero, which is where the attacks are: a sparse
    +3 folds into +2, and if +2 is also sparse the pair folds into +1, and so
    on. Both keys then report the same merged stats with merged=True, so a
    caller can tell a measured expectation from a borrowed one.
    """
    raw = defaultdict(list)
    for f in facts:
        raw[(f['src'], clamp_diff(f['attacker_th'], f['defender_th']))].append(f)

    curve = {}
    for src in {s for s, _ in raw}:
        centre_extra, centre_keys = [], []
        for sign in (1, -1):
            carried, carried_keys = [], []
            for d in range(DIFF_CLAMP * sign, 0, -sign):
                group = raw.get((src, d), []) + carried
                keys  = carried_keys + [d]
                if len(group) < MIN_BUCKET_N:
                    carried, carried_keys = group, keys
                    continue
                stats = _bucket(group, merged=len(keys) > 1)
                for k in keys:
                    curve[(src, k)] = stats
                carried, carried_keys = [], []
            # Whatever is still too thin at +/-1 folds into the centre bucket.
            centre_extra += carried
            centre_keys  += carried_keys

        centre = raw.get((src, 0), []) + centre_extra
        stats  = _bucket(centre, merged=bool(centre_keys))
        for k in [0] + centre_keys:
            curve[(src, k)] = stats

        # A diff nobody ever attacked at reports no expectation, full stop -
        # even one that got carried into a distant, unrelated centre bucket
        # along the way. Merging borrows strength for thin-but-real evidence;
        # it must not manufacture evidence for a diff that has none of its own.
        for d in range(-DIFF_CLAMP, DIFF_CLAMP + 1):
            if not raw.get((src, d)):
                curve[(src, d)] = _bucket([], merged=False)

    return curve
