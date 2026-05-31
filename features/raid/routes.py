import json

from flask import Blueprint, render_template, request
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from extensions import db
from models import RaidWeekend, RaidWeekendLog, Player
from services.helpers import CLEANUP_THRESHOLD, raid_district_medal_value

raid_bp = Blueprint('raid', __name__)


@raid_bp.route('/raid')
def raid_weekend_page():
    all_raids = RaidWeekend.query.order_by(RaidWeekend.startTime.desc()).all()

    selected_id = request.args.get('raid_id', type=int)
    if not selected_id and all_raids:
        selected_id = all_raids[0].id

    selected_raid = next((r for r in all_raids if r.id == selected_id), None) if selected_id else None

    player_data = []
    total_log_attacks = 0
    cleanup_count = 0
    est_medals_6atk = None

    if selected_raid:
        logs = (
            RaidWeekendLog.query
            .filter(RaidWeekendLog.raid_weekend_id == selected_raid.id)
            .options(selectinload(RaidWeekendLog.player))
            .all()
        )

        player_map = {}
        for log in logs:
            tag = log.playerTag
            if tag not in player_map:
                player_map[tag] = {
                    'player_name': log.player.name if log.player else tag,
                    'player_tag': tag,
                    'in_clan': log.player.in_clan if log.player else None,
                    'att_count': 0,
                    'cleanup_count': 0,
                    'capital_loot': 0,
                    'solo_wipes': 0,
                    'attack_logs': [],
                }
            p = player_map[tag]
            p['att_count'] += 1
            if log.totalLootAllAttacks:
                p['capital_loot'] = log.totalLootAllAttacks
            level = log.districLevel or 5
            try:
                level = int(level)
            except (TypeError, ValueError):
                level = 5
            level_mult = round(1.0 + (level - 5) * (0.07 if level >= 5 else 0.05), 2)
            pct = log.percentage or 0
            p['attack_logs'].append({
                'log_id':           log.id,
                'district_name':    log.districtName or '—',
                'district_level':   level,
                'level_mult':       level_mult,
                'stars':            log.stars or 0,
                'percentage':       pct,
                'adj_score':        0.0,
                'percentage_total': log.percentageTotal or 0,
                'is_clean_up':      False,
                'defender_name':    log.defenderName or '—',
                'defender_tag':     log.defenderTag or '—',
            })

        MAX_ATTACKS = 6
        for p in player_map.values():
            district_hits = {}
            for l in p['attack_logs']:
                key = (l['district_name'], l['defender_tag'])
                district_hits.setdefault(key, []).append(l)
            cleanup_log_ids = set()
            solo_wipe_count = 0
            for hits in district_hits.values():
                district_done = any(l['percentage_total'] == 100 for l in hits)
                player_total  = sum(l['percentage'] for l in hits)
                if len(hits) == 1 and district_done and hits[0]['percentage'] < CLEANUP_THRESHOLD:
                    cleanup_log_ids.add(hits[0]['log_id'])
                if district_done and player_total == 100:
                    solo_wipe_count += 1
            for l in p['attack_logs']:
                l['is_clean_up'] = l['log_id'] in cleanup_log_ids
                l['adj_score']   = round(0.0 if l['is_clean_up'] else l['percentage'] * l['level_mult'], 2)

            p['cleanup_count'] = len(cleanup_log_ids)
            p['solo_wipes']    = solo_wipe_count

            non_cleanup = [l['percentage'] for l in p['attack_logs'] if not l['is_clean_up']]
            p['avg_pct'] = round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0

            effective_max  = max(1, p['att_count'] - p['cleanup_count'])
            total_adj      = sum(l['adj_score'] for l in p['attack_logs'])
            adj_per_attack = total_adj / effective_max
            adj_per_attack = adj_per_attack * (1.10 ** p['solo_wipes'])
            score_100      = min(round(adj_per_attack * 100 / 73.94), 100)
            p['score_100']      = score_100
            p['adj_per_attack'] = round(adj_per_attack, 2)
            p['effective_max']  = effective_max

            missing = max(0, MAX_ATTACKS - p['att_count'])
            missing_text = f" ({missing} missing)" if missing else ""

            if p['att_count'] == 0:
                p['badge_class'], p['judge_label'] = 'badge-inactive', 'Inactive'
            elif score_100 >= 87:
                p['badge_class'], p['judge_label'] = 'badge-godlike',  'Godlike'  + missing_text
            elif score_100 >= 80:
                p['badge_class'], p['judge_label'] = 'badge-dominant', 'Dominant' + missing_text
            elif score_100 >= 65:
                p['badge_class'], p['judge_label'] = 'badge-wow',      'Very Good'+ missing_text
            elif score_100 >= 58:
                p['badge_class'], p['judge_label'] = 'badge-good',     'Good'     + missing_text
            elif score_100 >= 43:
                p['badge_class'], p['judge_label'] = 'badge-warning',  'Bad'      + missing_text
            elif score_100 >= 29:
                p['badge_class'], p['judge_label'] = 'badge-suck',     'Disaster' + missing_text
            else:
                p['badge_class'], p['judge_label'] = 'badge-useless',  'Useless'  + missing_text

        player_data = sorted(player_map.values(), key=lambda x: x['att_count'], reverse=True)
        total_log_attacks = sum(p['att_count'] for p in player_data)
        cleanup_count = sum(p['cleanup_count'] for p in player_data)

        # ── Estimated raid medals ─────────────────────────────────────────────
        destroyed = (
            RaidWeekendLog.query
            .filter(
                RaidWeekendLog.raid_weekend_id == selected_raid.id,
                RaidWeekendLog.percentageTotal >= 100,
            )
            .with_entities(RaidWeekendLog.defenderTag, RaidWeekendLog.districtName, RaidWeekendLog.districLevel)
            .distinct()
            .all()
        )
        total_medals  = sum(raid_district_medal_value(r.districtName, r.districLevel) for r in destroyed)
        total_attacks = max(total_log_attacks, 1)

        # Average defensive reward from last 10 finished raids
        past_def = (
            RaidWeekend.query
            .filter(RaidWeekend.defensiveReward > 0)
            .order_by(RaidWeekend.startTime.desc())
            .limit(10)
            .with_entities(RaidWeekend.defensiveReward)
            .all()
        )
        avg_defensive = round(sum(r.defensiveReward for r in past_def) / len(past_def)) if past_def else 0

        if total_medals > 0:
            baseline = total_medals / total_attacks
            off_6atk = max(0, min(round(baseline * 6), 1620))
            est_medals_6atk = off_6atk + avg_defensive
            for p in player_data:
                p['est_medals'] = max(0, min(round(min(p['att_count'], 6) * baseline), 1620)) + avg_defensive
        elif selected_raid.offensiveReward and selected_raid.offensiveReward > 0:
            baseline = selected_raid.offensiveReward
            off_6atk = min(round(baseline * 6), 1620)
            est_medals_6atk = off_6atk + avg_defensive
            for p in player_data:
                p['est_medals'] = min(round(min(p['att_count'], 6) * baseline), 1620) + avg_defensive
        else:
            est_medals_6atk = None
            for p in player_data:
                p['est_medals'] = None

    # Long-term solo wipe stats
    enc_subq = (
        db.session.query(
            RaidWeekendLog.playerTag,
            RaidWeekendLog.districtName,
            RaidWeekendLog.districLevel,
            RaidWeekendLog.defenderTag,
            RaidWeekendLog.raid_weekend_id,
            func.count(RaidWeekendLog.id).label('att_count'),
        )
        .filter(RaidWeekendLog.defenderTag.isnot(None))
        .group_by(
            RaidWeekendLog.playerTag,
            RaidWeekendLog.districtName,
            RaidWeekendLog.districLevel,
            RaidWeekendLog.defenderTag,
            RaidWeekendLog.raid_weekend_id,
        )
        .having(func.sum(RaidWeekendLog.percentage) == 100)
        .subquery()
    )
    hist_raw = (
        db.session.query(
            enc_subq.c.playerTag,
            enc_subq.c.districtName,
            enc_subq.c.districLevel,
            func.count(enc_subq.c.att_count).label('n'),
            func.avg(enc_subq.c.att_count).label('avg_attacks'),
        )
        .group_by(enc_subq.c.playerTag, enc_subq.c.districtName, enc_subq.c.districLevel)
        .all()
    )
    clan_players    = Player.query.filter_by(in_clan=True).all()
    player_name_map = {p.tag: (p.name or p.tag) for p in clan_players}
    in_clan_tags    = {p.tag for p in clan_players}
    hist_stats = [{
        'player_tag':  str(r.playerTag),
        'player_name': str(player_name_map.get(r.playerTag, r.playerTag)),
        'district':    str(r.districtName) if r.districtName else None,
        'level':       int(r.districLevel) if r.districLevel is not None else 0,
        'clears':      int(r.n),
        'avg_attacks': round(float(r.avg_attacks), 1) if r.avg_attacks is not None else 0,
    } for r in hist_raw if r.playerTag in in_clan_tags]
    hist_stats_json = json.dumps(hist_stats, default=str)

    has_ongoing = any(r.state == 'ongoing' for r in all_raids)
    last_weekend_assigned = False
    raid_options = []
    for r in all_raids:
        if r.state == 'ongoing':
            label = 'Current Weekend'
        elif has_ongoing and not last_weekend_assigned:
            label = 'Last Weekend'
            last_weekend_assigned = True
        else:
            start = r.startTime.strftime('%d.%m.%Y') if r.startTime else '?'
            end   = r.endTime.strftime('%d.%m.%Y') if r.endTime else '?'
            label = f"{start} – {end}"
        raid_options.append({'id': r.id, 'label': label})

    return render_template(
        'raid/raid_weekend.html',
        raid_options=raid_options,
        selected_raid=selected_raid,
        selected_id=selected_id,
        player_data=player_data,
        total_log_attacks=total_log_attacks,
        cleanup_count=cleanup_count,
        hist_stats_json=hist_stats_json,
        est_medals_6atk=est_medals_6atk,
    )
