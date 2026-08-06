# -*- coding: utf-8 -*-
"""Study E - does ladder skill predict raid-weekend output?

Lifted out of features/admin/routes.py, where it lived inline behind an AJAX
endpoint. The arithmetic is unchanged; what is new is that the pure part is
separated from the loading part (load_correlation_inputs now lives in
loaders.py, the only DB-aware file) and now has tests.
"""

MIN_PERIODS            = 3   # weeks or weekends before a player's average means anything
MIN_CORRELATION_POINTS = 3   # players needed before r itself is meaningful


def pearson_r(xs, ys):
    """-> r rounded to 3 places, or None when it is undefined.

    Undefined covers two real states: too few players, and no variance on an
    axis. Neither is an error, and neither should raise.
    """
    n = len(xs)
    if n < MIN_CORRELATION_POINTS:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return round(num / den, 3) if den else None


def build_correlation(ranked_scores, raid_scores, players,
                      ranked_games=None, raid_attacks=None):
    """-> {'players', 'pearson_r', 'n_correlated'}

    ranked_scores / raid_scores are {tag: [score per period]}. A player below
    MIN_PERIODS on an axis scores None there and sits out the correlation, but
    still appears in the table - the roster should not silently shrink.

    Sorted by ranked_score, best first, unscored players last: `is None` sorts
    them after every real score including a genuine 0.0, which `0.0 or -1`
    used to conflate with "no score at all".
    """
    ranked_games = ranked_games or {}
    raid_attacks = raid_attacks or {}

    rows, xs, ys = [], [], []
    for p in players:
        tag = p['tag']
        rk, rd = ranked_scores.get(tag, []), raid_scores.get(tag, [])
        ranked = round(sum(rk) / len(rk), 1) if len(rk) >= MIN_PERIODS else None
        raid   = round(sum(rd) / len(rd), 1) if len(rd) >= MIN_PERIODS else None

        rows.append({
            'tag': tag, 'name': p['name'], 'th': p['th'],
            'ranked_score': ranked, 'ranked_weeks': len(rk),
            'ranked_games': ranked_games.get(tag, 0),
            'raid_score': raid, 'raid_weekends': len(rd),
            'raid_attacks': raid_attacks.get(tag, 0),
        })
        if ranked is not None and raid is not None:
            xs.append(ranked)
            ys.append(raid)

    rows.sort(key=lambda r: (r['ranked_score'] is None, -(r['ranked_score'] or 0)))
    return {'players': rows, 'pearson_r': pearson_r(xs, ys), 'n_correlated': len(xs)}
