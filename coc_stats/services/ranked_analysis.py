import datetime as dt
import json
from collections import Counter, defaultdict

from extensions import db
from models import AppUser, RankedBattleLog, RankedWeek, RankedWeekAnalysis
from services.api import api_fetch_league_group, api_fetch_player_data
from services.helpers import (
    JSON_PLAYER_DATA, JSON_RANKED_GROUP_DATA, json_get,
    get_league_thresholds, get_name_to_id, get_weekly_attacks,
    compute_hero_pct, trophies_at_rank,
)

MIN_BUCKET_SAMPLES = 3

THREAT_LEVELS = ('easy', 'manageable', 'even', 'tough', 'dangerous')
_THREAT_BADGE = {
    'easy': ('badge-wow', 'Easy'),
    'manageable': ('badge-good', 'Manageable'),
    'even': ('badge-even', 'Even'),
    'tough': ('badge-warning', 'Tough'),
    'dangerous': ('badge-suck', 'Dangerous'),
}


def _th_diff_bucket(diff):
    if diff > 0:
        return 'up'
    if diff < 0:
        return 'down'
    return 'even'


HERO_PCT_BUCKETS = ('0-25%', '25-50%', '50-75%', '75-100%')


def _hero_pct_bucket_idx(pct):
    if pct is None:
        return None
    if pct >= 100:
        return 3
    return min(3, int(pct // 25))


def _build_history_buckets(player_tag):
    """Bucket the linked player's own past ranked attacks/defenses by TH diff."""
    own_th_by_week = {
        (rw.league_group_tag, rw.league_season_id): rw.townhall
        for rw in RankedWeek.query.filter(RankedWeek.player_tag == player_tag).all()
    }
    logs = RankedBattleLog.query.filter(RankedBattleLog.player_tag == player_tag).all()

    att_buckets = {'up': [], 'even': [], 'down': []}
    def_buckets = {'up': [], 'even': [], 'down': []}

    for log in logs:
        own_th = own_th_by_week.get((log.league_group_tag, log.league_season_id))
        try:
            opp_th = int(log.opponent_th)
        except (TypeError, ValueError):
            opp_th = None
        if not own_th or opp_th is None:
            continue
        bucket = _th_diff_bucket(opp_th - own_th)
        stars = log.stars or 0
        if log.attack is True or log.attack == 1:
            att_buckets[bucket].append(stars)
        else:
            def_buckets[bucket].append(stars)

    def _avg(values):
        return round(sum(values) / len(values), 2) if values else None

    return {
        'attack': {b: {'avg': _avg(v), 'samples': len(v)} for b, v in att_buckets.items()},
        'defense': {b: {'avg': _avg(v), 'samples': len(v)} for b, v in def_buckets.items()},
    }


def _hero_power(player_api):
    return sum(h.get('level', 0) for h in player_api.get('heroes', []) if h.get('village') == 'home')


def _home_heroes(player_api):
    return [h for h in player_api.get('heroes', []) if h.get('village') == 'home']


def _threat_verdict(own_th, own_hero_pct, opp_th, opp_hero_pct):
    """Rule-based threat combining TH-diff (primary) and hero_pct-diff (secondary, capped).
    Returns (level, score); higher score = more dangerous opponent."""
    th_diff = (opp_th or 0) - (own_th or 0)
    hero_diff = (opp_hero_pct or 0) - (own_hero_pct or 0)
    score = th_diff * 2 + max(-2, min(2, round(hero_diff / 25)))
    if score <= -3: level = 'easy'
    elif score <= -1: level = 'manageable'
    elif score <= 1: level = 'even'
    elif score <= 3: level = 'tough'
    else: level = 'dangerous'
    return level, score


def _member_base(rank, member, max_attacks):
    attack_wins = member.get('attackWinCount', 0)
    attack_losses = member.get('attackLoseCount', 0)
    attacks_used = attack_wins + attack_losses
    return {
        'tag': member.get('playerTag'),
        'name': member.get('playerName', member.get('playerTag')),
        'clan_name': member.get('clanName'),
        'rank': rank,
        'trophies': member.get('leagueTrophies'),
        'attack_wins': attack_wins,
        'attack_losses': attack_losses,
        'defense_wins': member.get('defenseWinCount', 0),
        'defense_losses': member.get('defenseLoseCount', 0),
        'attacks_used': attacks_used,
        'attacks_remaining': max(0, max_attacks - attacks_used) if max_attacks else None,
        'max_attacks': max_attacks,
    }


def _extract_logs(group_api):
    attacks = group_api.get('attackLogs') or []
    defenses = group_api.get('defenseLogs') or []

    def _log(e):
        return {
            'opponent_tag': e.get('opponentPlayerTag'),
            'opponent_name': e.get('opponentName'),
            'stars': e.get('stars', 0),
            'destruction': round(float(e.get('destructionPercentage', 0)), 1),
            'trophies': e.get('trophies', 0),
        }

    attack_log = [_log(e) for e in attacks]
    defense_log = [_log(e) for e in defenses]
    a_stars = [e['stars'] for e in attack_log]
    d_stars = [e['stars'] for e in defense_log]
    return {
        'attack_log': attack_log,
        'defense_log': defense_log,
        'attack_avg_stars': round(sum(a_stars) / len(a_stars), 1) if a_stars else None,
        'defense_avg_stars': round(sum(d_stars) / len(d_stars), 1) if d_stars else None,
    }


def run_week_analysis(app_user_id):
    from app import app

    with app.app_context():
        row = db.session.get(RankedWeekAnalysis, app_user_id)
        try:
            app_user = db.session.get(AppUser, app_user_id)
            linked_tag = app_user.linked_player_tag if app_user else None
            if not linked_tag:
                raise ValueError("No linked player set.")

            player_api = api_fetch_player_data(linked_tag)
            season_id = json_get(player_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_SEASON_ID, default=0, raise_on_missing=False)
            if not season_id:
                raise ValueError("Linked player is not currently in a ranked week.")
            group_tag = json_get(player_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_GROUP_TAG)
            own_th = json_get(player_api, JSON_PLAYER_DATA.TOWN_HALL_LEVEL)
            league_tier = get_name_to_id(json_get(player_api, JSON_PLAYER_DATA.LEAGUE_TIER.ID))
            own_hero_pct = compute_hero_pct(_home_heroes(player_api), own_th)
            max_attacks = get_weekly_attacks(league_tier) or 0

            group_data_api = api_fetch_league_group(group_tag, season_id, linked_tag)
            members = json_get(group_data_api, JSON_RANKED_GROUP_DATA.MEMBERS)

            own_rank = None
            own_member = None
            opponents_raw = []
            for idx, member in enumerate(members, start=1):
                if member.get('playerTag') == linked_tag:
                    own_rank = idx
                    own_member = member
                else:
                    opponents_raw.append((idx, member))

            row.league_group_tag = group_tag
            row.league_season_id = str(season_id)
            row.player_tag = linked_tag
            row.progress_total = len(opponents_raw)
            row.progress_done = 0
            db.session.commit()

            thresholds = get_league_thresholds(league_tier) or {}
            promo_cutoff = thresholds.get('pro')
            dem_cutoff_rank = (len(members) - thresholds['dem'] + 1) if thresholds.get('dem') else None
            promo_cutoff_trophies = trophies_at_rank(members, promo_cutoff) if promo_cutoff else None
            dem_cutoff_trophies = trophies_at_rank(members, dem_cutoff_rank) if dem_cutoff_rank else None

            buckets = _build_history_buckets(linked_tag)

            own_logs = _extract_logs(group_data_api)
            own_attacks_by_tag = {a['opponent_tag']: a for a in own_logs['attack_log']}
            own_defenses_by_tag = {d['opponent_tag']: d for d in own_logs['defense_log']}

            results = []
            th_counter = Counter()
            hero_pct_values = []
            th_hero_buckets = defaultdict(lambda: [0, 0, 0, 0])
            if own_th:
                th_counter[own_th] += 1
            if own_hero_pct is not None:
                hero_pct_values.append(own_hero_pct)
                if own_th:
                    th_hero_buckets[own_th][_hero_pct_bucket_idx(own_hero_pct)] += 1

            for rank, member in opponents_raw:
                entry = _member_base(rank, member, max_attacks)
                entry['data_unavailable'] = False
                opp_tag = entry['tag']
                try:
                    opp_api = api_fetch_player_data(opp_tag)
                    opp_th = json_get(opp_api, JSON_PLAYER_DATA.TOWN_HALL_LEVEL)
                    entry['th'] = opp_th
                    entry['hero_power'] = _hero_power(opp_api)
                    entry['hero_pct'] = compute_hero_pct(_home_heroes(opp_api), opp_th)
                    th_counter[opp_th] += 1
                    hero_pct_values.append(entry['hero_pct'])
                    if opp_th:
                        th_hero_buckets[opp_th][_hero_pct_bucket_idx(entry['hero_pct'])] += 1

                    level, score = _threat_verdict(own_th, own_hero_pct, opp_th, entry['hero_pct'])
                    entry['threat_level'] = level
                    entry['threat_score'] = score
                    entry['threat_badge_class'], entry['threat_label'] = _THREAT_BADGE[level]

                    bucket = _th_diff_bucket(opp_th - own_th)
                    att_b = buckets['attack'][bucket]
                    def_b = buckets['defense'][bucket]
                    entry['predicted_my_stars'] = att_b['avg']
                    entry['predicted_their_stars'] = def_b['avg']
                    entry['low_confidence'] = (
                        att_b['samples'] < MIN_BUCKET_SAMPLES or def_b['samples'] < MIN_BUCKET_SAMPLES
                    )

                    opp_group_api = api_fetch_league_group(group_tag, season_id, opp_tag)
                    opp_logs = _extract_logs(opp_group_api)
                    entry['attack_avg_stars'] = opp_logs['attack_avg_stars']
                    entry['defense_avg_stars'] = opp_logs['defense_avg_stars']

                    entry['you_attacked'] = own_attacks_by_tag.get(opp_tag)
                    entry['they_attacked_you'] = own_defenses_by_tag.get(opp_tag)
                except Exception as e:
                    entry['data_unavailable'] = True
                    entry['error'] = str(e)

                results.append(entry)
                row.progress_done += 1
                db.session.commit()

            results.sort(key=lambda r: r['rank'])

            own_entry = _member_base(own_rank, own_member, max_attacks) if own_member else {
                'tag': linked_tag, 'name': linked_tag, 'rank': own_rank,
            }
            own_entry['th'] = own_th
            own_entry['hero_power'] = _hero_power(player_api)
            own_entry['hero_pct'] = own_hero_pct
            own_entry['attack_avg_stars'] = own_logs['attack_avg_stars']
            own_entry['defense_avg_stars'] = own_logs['defense_avg_stars']

            own_entry['promo_zone'] = bool(promo_cutoff and own_rank and own_rank <= promo_cutoff)
            own_entry['dem_zone'] = bool(dem_cutoff_rank and own_rank and own_rank >= dem_cutoff_rank)
            own_entry['spots_to_promo'] = (
                max(0, own_rank - promo_cutoff) if promo_cutoff and own_rank and not own_entry['promo_zone'] else 0
            )
            own_entry['spots_above_dem'] = (
                max(0, dem_cutoff_rank - own_rank) if dem_cutoff_rank and own_rank and not own_entry['dem_zone'] else 0
            )
            own_trophies = own_entry.get('trophies')
            own_entry['trophy_gap_to_promo'] = (
                max(0, promo_cutoff_trophies - own_trophies)
                if promo_cutoff_trophies is not None and own_trophies is not None and not own_entry['promo_zone']
                else 0
            )
            own_entry['trophy_cushion_above_dem'] = (
                max(0, own_trophies - dem_cutoff_trophies)
                if dem_cutoff_trophies is not None and own_trophies is not None and not own_entry['dem_zone']
                else 0
            )

            scored = [r for r in results if not r.get('data_unavailable')]
            best_targets = [r['tag'] for r in sorted(scored, key=lambda r: r['threat_score'])[:10]]
            danger_zone = [r['tag'] for r in sorted(scored, key=lambda r: -r['threat_score'])[:10]]

            avg_hero_pct = round(sum(hero_pct_values) / len(hero_pct_values)) if hero_pct_values else None

            row.results_json = json.dumps({
                'own': own_entry,
                'league_tier': league_tier,
                'group_size': len(members),
                'max_attacks': max_attacks,
                'promo_cutoff': promo_cutoff,
                'dem_cutoff_rank': dem_cutoff_rank,
                'promo_cutoff_trophies': promo_cutoff_trophies,
                'dem_cutoff_trophies': dem_cutoff_trophies,
                'th_distribution': dict(sorted(th_counter.items())),
                'avg_hero_pct': avg_hero_pct,
                'th_hero_buckets': dict(sorted(th_hero_buckets.items())),
                'opponents': results,
                'best_targets': best_targets,
                'danger_zone': danger_zone,
            }, default=str)
            row.status = 'done'
            row.finished_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            row.error_message = None
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            row = db.session.get(RankedWeekAnalysis, app_user_id)
            row.status = 'error'
            row.error_message = str(e)
            row.finished_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            db.session.commit()
