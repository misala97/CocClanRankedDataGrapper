# -*- coding: utf-8 -*-
"""Study C - who is reliable, as distinct from who is good.

The mean already appears elsewhere in the app. The spread does not, and it is
a different roster question: a 70-average player who never drops below 65 and
a 70-average player who alternates 40 and 100 are not interchangeable.

Sigma is the population standard deviation over the weeks a player actually
played. Those weeks are the whole record, not a sample drawn from a larger one,
and pstdev is defined at n=1 where stdev raises.
"""

import statistics

MIN_RANKED_WEEKS  = 6      # below this a player is listed but not ranked
MIN_RAID_WEEKENDS = 4
MEAN_BAND         = 3.0    # how close two means must be to count as "the same"


def series_stats(values):
    """-> {'n', 'mean', 'sd', 'floor', 'ceiling'}, or None for an empty series."""
    if not values:
        return None
    return {
        'n':       len(values),
        'mean':    sum(values) / len(values),
        'sd':      statistics.pstdev(values),
        'floor':   min(values),
        'ceiling': max(values),
    }


def consistency(scores_by_player, min_n):
    """-> one row per player, steadiest first, thin players last."""
    rows = []
    for tag, values in scores_by_player.items():
        stats = series_stats(values)
        if not stats:
            continue
        stats['tag']  = tag
        stats['thin'] = stats['n'] < min_n
        rows.append(stats)

    rows.sort(key=lambda r: (r['thin'], r['sd']))
    return rows


def contrast_pair(rows, mean_band=MEAN_BAND):
    """The two ranked players with the closest means and the widest sigma gap.

    This is the finding the study exists to state. Thin players are excluded:
    a wide sigma over four weeks is noise, and naming someone for it would be
    the study accusing its own sample.
    """
    solid = [r for r in rows if not r['thin']]
    best  = None
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if abs(a['mean'] - b['mean']) > mean_band:
                continue
            gap = abs(a['sd'] - b['sd'])
            if best is None or gap > best[0]:
                best = (gap, a, b)

    if best is None or best[0] == 0:
        return None
    _, a, b = best
    steady, streaky = (a, b) if a['sd'] < b['sd'] else (b, a)
    return {'steady': steady, 'streaky': streaky}
