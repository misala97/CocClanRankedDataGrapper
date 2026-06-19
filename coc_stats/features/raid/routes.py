import json

from flask import Blueprint, render_template, request
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from extensions import db
from models import RaidWeekend, RaidWeekendLog, Player
from services.helpers import CLEANUP_THRESHOLD, raid_district_medal_value, raid_score_verdict, _raid_level_mult

raid_bp = Blueprint('raid', __name__)


@raid_bp.route('/raid')
def raid_weekend_page():
    all_raids = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).all()

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
            .order_by(RaidWeekendLog.id.asc())
            .all()
        )

        # ── Per-attack medal-rate impact (id order ≈ chronological order) ──────
        # Tracks medals_so_far / attacks_so_far before vs after each attack, so we
        # can tell whether a given attack pulled the clan's per-attack rate up
        # (it finished a district) or down (it used an attack without finishing one).
        rate_delta_by_log_id = {}
        medals_so_far = 0
        attacks_so_far = 0
        completed_districts = set()
        for log in logs:
            before_rate = (medals_so_far / attacks_so_far) if attacks_so_far else 0.0
            attacks_so_far += 1
            district_key = (log.defender_tag, log.district_name)
            if (log.percentage_total or 0) >= 100 and district_key not in completed_districts:
                completed_districts.add(district_key)
                medals_so_far += raid_district_medal_value(log.district_name, log.district_level)
            after_rate = medals_so_far / attacks_so_far
            rate_delta_by_log_id[log.id] = round(after_rate - before_rate, 2)

        player_map = {}
        for log in logs:
            tag = log.player_tag
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
            if log.total_loot_all_attacks:
                p['capital_loot'] = log.total_loot_all_attacks
            level = log.district_level or 5
            try:
                level = int(level)
            except (TypeError, ValueError):
                level = 5
            level_mult = round(_raid_level_mult(level), 2)
            pct = log.percentage or 0
            p['attack_logs'].append({
                'log_id':           log.id,
                'district_name':    log.district_name or '—',
                'district_level':   level,
                'level_mult':       level_mult,
                'stars':            log.stars or 0,
                'percentage':       pct,
                'adj_score':        0.0,
                'percentage_total': log.percentage_total or 0,
                'rate_delta':       rate_delta_by_log_id.get(log.id, 0.0),
                'is_clean_up':      False,
                'defender_name':         log.defender_name or '—',
                'defender_tag':          log.defender_tag or '—',
                'defender_badge':        log.defender_badge or None,
                'defender_league':       log.defender_league or None,
                'defender_league_badge': log.defender_league_badge or None,
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

            p['cleanup_count']   = len(cleanup_log_ids)
            p['solo_wipes']      = solo_wipe_count
            p['net_rate_impact'] = round(sum(l['rate_delta'] for l in p['attack_logs']), 2)

            non_cleanup = [l['percentage'] for l in p['attack_logs'] if not l['is_clean_up']]
            p['avg_pct'] = round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0

            effective_max  = max(1, p['att_count'] - p['cleanup_count'])
            total_adj      = sum(l['adj_score'] for l in p['attack_logs'])
            adj_per_attack = total_adj / effective_max
            missing = max(0, MAX_ATTACKS - p['att_count'])
            missing_text = f" ({missing} missing)" if missing else ""
            score_100, adj_boosted, p['badge_class'], p['judge_label'] = raid_score_verdict(
                adj_per_attack, p['solo_wipes'], p['att_count'], missing_text
            )
            p['score_100']      = score_100
            p['adj_per_attack'] = adj_boosted
            p['effective_max']  = effective_max

        player_data = sorted(player_map.values(), key=lambda x: x['att_count'], reverse=True)
        total_log_attacks = sum(p['att_count'] for p in player_data)
        cleanup_count = sum(p['cleanup_count'] for p in player_data)

        # ── Estimated raid medals ─────────────────────────────────────────────
        destroyed = (
            RaidWeekendLog.query
            .filter(
                RaidWeekendLog.raid_weekend_id == selected_raid.id,
                RaidWeekendLog.percentage_total >= 100,
            )
            .with_entities(RaidWeekendLog.defender_tag, RaidWeekendLog.district_name, RaidWeekendLog.district_level)
            .distinct()
            .all()
        )
        total_medals  = sum(raid_district_medal_value(r.district_name, r.district_level) for r in destroyed)
        total_attacks = max(total_log_attacks, 1)

        # Average defensive reward from last 10 finished raids
        past_def = (
            RaidWeekend.query
            .filter(RaidWeekend.defensive_reward > 0)
            .order_by(RaidWeekend.start_time.desc())
            .limit(10)
            .with_entities(RaidWeekend.defensive_reward)
            .all()
        )
        avg_defensive = round(sum(r.defensive_reward for r in past_def) / len(past_def)) if past_def else 0

        if total_medals > 0:
            baseline = total_medals / total_attacks
            off_6atk = max(0, min(round(baseline * 6), 1620))
            est_medals_6atk = off_6atk + avg_defensive
            for p in player_data:
                p['est_medals'] = max(0, min(round(min(p['att_count'], 6) * baseline), 1620)) + avg_defensive
        elif selected_raid.offensive_reward and selected_raid.offensive_reward > 0:
            baseline = selected_raid.offensive_reward
            off_6atk = min(round(baseline * 6), 1620)
            est_medals_6atk = off_6atk + avg_defensive
            for p in player_data:
                p['est_medals'] = min(round(min(p['att_count'], 6) * baseline), 1620) + avg_defensive
        else:
            est_medals_6atk = None
            for p in player_data:
                p['est_medals'] = None

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
            start = r.start_time.strftime('%d.%m.%Y') if r.start_time else '?'
            end   = r.end_time.strftime('%d.%m.%Y') if r.end_time else '?'
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
        est_medals_6atk=est_medals_6atk,
    )


@raid_bp.route('/raid/stats')
def raid_stats_page():
    clan_players    = Player.query.filter_by(in_clan=True).all()
    player_name_map = {p.tag: (p.name or p.tag) for p in clan_players}
    in_clan_tags    = {p.tag for p in clan_players}

    # Attack + participation totals per player
    atk_rows = (
        db.session.query(
            RaidWeekendLog.player_tag,
            func.count(RaidWeekendLog.id).label('total_attacks'),
            func.avg(RaidWeekendLog.percentage).label('avg_pct'),
            func.count(func.distinct(RaidWeekendLog.raid_weekend_id)).label('raids_participated'),
        )
        .group_by(RaidWeekendLog.player_tag)
        .all()
    )

    # Total loot per player (max per-raid loot, summed across raids)
    loot_subq = (
        db.session.query(
            RaidWeekendLog.player_tag,
            RaidWeekendLog.raid_weekend_id,
            func.max(RaidWeekendLog.total_loot_all_attacks).label('raid_loot'),
        )
        .group_by(RaidWeekendLog.player_tag, RaidWeekendLog.raid_weekend_id)
        .subquery()
    )
    loot_rows = (
        db.session.query(
            loot_subq.c.player_tag,
            func.sum(loot_subq.c.raid_loot).label('total_loot'),
        )
        .group_by(loot_subq.c.player_tag)
        .all()
    )

    # Solo wipe encounters (player got 100% total on a district)
    enc_subq = (
        db.session.query(
            RaidWeekendLog.player_tag,
            RaidWeekendLog.district_name,
            RaidWeekendLog.district_level,
            RaidWeekendLog.defender_tag,
            RaidWeekendLog.raid_weekend_id,
            func.count(RaidWeekendLog.id).label('att_count'),
        )
        .filter(RaidWeekendLog.defender_tag.isnot(None))
        .group_by(
            RaidWeekendLog.player_tag,
            RaidWeekendLog.district_name,
            RaidWeekendLog.district_level,
            RaidWeekendLog.defender_tag,
            RaidWeekendLog.raid_weekend_id,
        )
        .having(func.sum(RaidWeekendLog.percentage) == 100)
        .subquery()
    )

    solo_rows = (
        db.session.query(
            enc_subq.c.player_tag,
            func.count().label('total_solo_wipes'),
            func.avg(enc_subq.c.att_count).label('avg_attacks_per_wipe'),
        )
        .group_by(enc_subq.c.player_tag)
        .all()
    )

    # Per-player per-district breakdown (powers the champions strip + heatmap)
    hist_raw = (
        db.session.query(
            enc_subq.c.player_tag,
            enc_subq.c.district_name,
            func.count(enc_subq.c.att_count).label('n'),
            func.avg(enc_subq.c.att_count).label('avg_attacks'),
        )
        .group_by(enc_subq.c.player_tag, enc_subq.c.district_name)
        .all()
    )
    hist_stats = [{
        'player_name': str(player_name_map.get(r.player_tag, r.player_tag)),
        'district':    str(r.district_name),
        'clears':      int(r.n),
        'avg_attacks': round(float(r.avg_attacks), 2) if r.avg_attacks is not None else 0,
    } for r in hist_raw if r.player_tag in in_clan_tags and r.district_name]

    district_rows = (
        db.session.query(
            enc_subq.c.district_name,
            enc_subq.c.district_level,
            func.count().label('total_clears'),
            func.avg(enc_subq.c.att_count).label('avg_attacks'),
            func.min(enc_subq.c.att_count).label('best_attacks'),
        )
        .group_by(enc_subq.c.district_name, enc_subq.c.district_level)
        .all()
    )

    # All district encounters (denominator for solo wipe rate)
    all_enc_subq = (
        db.session.query(
            RaidWeekendLog.player_tag,
            RaidWeekendLog.district_name,
            RaidWeekendLog.defender_tag,
            RaidWeekendLog.raid_weekend_id,
        )
        .filter(RaidWeekendLog.defender_tag.isnot(None))
        .group_by(
            RaidWeekendLog.player_tag,
            RaidWeekendLog.district_name,
            RaidWeekendLog.defender_tag,
            RaidWeekendLog.raid_weekend_id,
        )
        .subquery()
    )
    total_encounters = db.session.query(func.count()).select_from(all_enc_subq).scalar() or 0

    # Attacks per finished raid (for participation rate)
    part_rows = (
        db.session.query(
            RaidWeekendLog.raid_weekend_id,
            func.count(RaidWeekendLog.id).label('total_attacks'),
        )
        .join(RaidWeekend, RaidWeekendLog.raid_weekend_id == RaidWeekend.id)
        .filter(RaidWeekend.state == 'ended')
        .group_by(RaidWeekendLog.raid_weekend_id)
        .all()
    )

    finished_raids = (
        RaidWeekend.query
        .filter(RaidWeekend.state == 'ended', RaidWeekend.capital_total_loot.isnot(None))
        .order_by(RaidWeekend.start_time.asc())
        .all()
    )

    loot_map = {r.player_tag: int(r.total_loot or 0) for r in loot_rows}
    solo_map = {
        r.player_tag: {
            'wipes':   int(r.total_solo_wipes),
            'avg_atk': round(float(r.avg_attacks_per_wipe or 0), 2),
        }
        for r in solo_rows
    }

    player_stats = []
    for r in atk_rows:
        tag = r.player_tag
        if tag not in in_clan_tags:
            continue
        total_loot = loot_map.get(tag, 0)
        raids      = int(r.raids_participated)
        solo       = solo_map.get(tag, {'wipes': 0, 'avg_atk': 0.0})
        player_stats.append({
            'player_name':        player_name_map.get(tag, tag),
            'player_tag':         tag,
            'raids_participated': raids,
            'total_attacks':      int(r.total_attacks),
            'total_loot':         total_loot,
            'avg_loot_per_raid':  round(total_loot / raids) if raids > 0 else 0,
            'total_solo_wipes':   solo['wipes'],
            'avg_attacks_per_wipe': solo['avg_atk'],
            'avg_pct':            round(float(r.avg_pct or 0), 1),
        })
    player_stats.sort(key=lambda x: x['total_solo_wipes'], reverse=True)

    district_data = sorted([{
        'name':         r.district_name or '?',
        'level':        int(r.district_level or 0),
        'total_clears': int(r.total_clears),
        'avg_attacks':  round(float(r.avg_attacks or 0), 2),
        'best_attacks': int(r.best_attacks or 0),
    } for r in district_rows if r.district_name], key=lambda x: x['avg_attacks'])

    raid_history = [{
        'label':     r.start_time.strftime('%d.%m.%y') if r.start_time else '?',
        'loot':      r.capital_total_loot or 0,
        'districts': r.enemy_districts_destroyed or 0,
    } for r in finished_raids]

    total_raids           = len(finished_raids)
    total_loot_all        = sum(r['loot'] for r in raid_history)
    total_solo_wipes_all  = sum(p['total_solo_wipes'] for p in player_stats)
    avg_loot_per_raid     = round(total_loot_all / total_raids) if total_raids else 0

    # Solo wipe rate
    solo_wipe_rate = round(total_solo_wipes_all / total_encounters * 100, 1) if total_encounters > 0 else 0

    # Avg participation rate (attacks used out of max 6 per member per raid)
    clan_size = len(clan_players)
    if part_rows and clan_size > 0:
        avg_atk_per_raid = sum(r.total_attacks for r in part_rows) / len(part_rows)
        participation_pct = round(avg_atk_per_raid / (clan_size * 6) * 100, 1)
        avg_atk_per_member = round(avg_atk_per_raid / clan_size, 1)
    else:
        participation_pct  = 0.0
        avg_atk_per_member = 0.0

    # Loot trend: last 3 raids vs the 3 before that
    if len(raid_history) >= 4:
        recent_loots = [r['loot'] for r in raid_history[-3:]]
        prior_loots  = [r['loot'] for r in raid_history[-6:-3]] or [r['loot'] for r in raid_history[:-3]]
        recent_avg   = sum(recent_loots) / len(recent_loots)
        prior_avg    = sum(prior_loots)  / len(prior_loots)
        loot_trend_pct = round((recent_avg - prior_avg) / prior_avg * 100, 1) if prior_avg else 0
        loot_trend_dir = 'up' if loot_trend_pct > 1 else ('down' if loot_trend_pct < -1 else 'flat')
    else:
        loot_trend_pct = None
        loot_trend_dir = 'none'

    return render_template(
        'raid/raid_stats.html',
        player_stats_json  = json.dumps(player_stats,  default=str),
        district_data_json = json.dumps(district_data, default=str),
        raid_history_json  = json.dumps(raid_history,  default=str),
        hist_stats_json    = json.dumps(hist_stats,    default=str),
        total_raids          = total_raids,
        total_loot_all       = total_loot_all,
        total_solo_wipes_all = total_solo_wipes_all,
        avg_loot_per_raid    = avg_loot_per_raid,
        solo_wipe_rate       = solo_wipe_rate,
        participation_pct    = participation_pct,
        avg_atk_per_member   = avg_atk_per_member,
        loot_trend_pct       = loot_trend_pct,
        loot_trend_dir       = loot_trend_dir,
    )
