# -*- coding: utf-8 -*-
"""Study E - does ladder skill predict raid-weekend output?

Lifted out of features/admin/routes.py, where it lived inline behind an AJAX
endpoint. The arithmetic is unchanged; what is new is that the pure part is
separated from the loading part and now has tests.
"""

from collections import defaultdict

MIN_PERIODS = 3   # weeks or weekends before a player's average means anything


def pearson_r(xs, ys):
    """-> r rounded to 3 places, or None when it is undefined.

    Undefined covers two real states: too few players, and no variance on an
    axis. Neither is an error, and neither should raise.
    """
    n = len(xs)
    if n < MIN_PERIODS:
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

    rows.sort(key=lambda r: -(r['ranked_score'] or -1))
    return {'players': rows, 'pearson_r': pearson_r(xs, ys), 'n_correlated': len(xs)}


def load_correlation_inputs():
    """Per-player ranked-week and raid-weekend score series. Needs an app context."""
    from extensions import db
    from models import Player, RankedWeek, RaidWeekendLog
    from services.helpers import _calc_ranked_score, _raid_verdict

    players = Player.query.filter_by(in_clan=True).all()
    tags    = [p.tag for p in players]

    ranked_scores, ranked_games = defaultdict(list), defaultdict(int)
    weeks = (RankedWeek.query
             .filter(RankedWeek.player_tag.in_(tags), RankedWeek.is_done == True)
             .options(db.joinedload(RankedWeek.battle_logs))
             .all())
    for week in weeks:
        attacks = sum(1 for l in week.battle_logs if l.attack)
        if not attacks:
            continue
        score, _, _ = _calc_ranked_score(week.battle_logs, week.townhall or 0,
                                         week.max_attacks or attacks,
                                         week.league_tier or '')
        ranked_scores[week.player_tag].append(score)
        ranked_games[week.player_tag] += attacks

    per_weekend = defaultdict(list)
    for log in RaidWeekendLog.query.filter(RaidWeekendLog.player_tag.in_(tags)).all():
        per_weekend[(log.player_tag, log.raid_weekend_id)].append(log)

    raid_scores, raid_attacks = defaultdict(list), defaultdict(int)
    for (tag, _), logs in per_weekend.items():
        if not logs:
            continue
        _, _, score = _raid_verdict(logs)
        raid_scores[tag].append(score)
        raid_attacks[tag] += len(logs)

    roster = [{'tag': p.tag, 'name': p.name or p.tag, 'th': p.current_th or 0}
              for p in players]
    return ranked_scores, raid_scores, roster, ranked_games, raid_attacks
