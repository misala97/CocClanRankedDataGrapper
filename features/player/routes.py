import datetime as dt

from flask import Blueprint, render_template, request
from sqlalchemy import func, tuple_
from sqlalchemy.orm import selectinload

from extensions import db
from models import Player, RankedWeek, RankedBattleLog, BattleLog, RaidWeekend, RaidWeekendLog
from services.db import db_player_get
from services.helpers import (
    to_local, _calc_th_multiplier, _league_mult, _ranked_verdict,
    _district_stats, _raid_verdict,
)

player_bp = Blueprint('player', __name__)


def _fmt_loot(n):
    n = int(n or 0)
    if n >= 1_000_000: return f'{n / 1_000_000:.1f}M'
    if n >= 1_000:     return f'{n / 1_000:.0f}K'
    return str(n)


def calculate_activity_score(player_tag, period='week'):
    now = dt.datetime.now(dt.timezone.utc)
    if period == 'week':
        season_limit, raid_limit, battle_days = 1, 1, 7
    elif period == 'month':
        season_limit, raid_limit, battle_days = 4, 4, 30
    else:
        season_limit, raid_limit, battle_days = 16, 20, 180

    last_seasons = (db.session.query(RankedWeek.league_season_id)
                    .distinct().order_by(RankedWeek.league_season_id.desc())
                    .limit(season_limit).all())
    season_ids   = [r.league_season_id for r in last_seasons]
    player_weeks = (RankedWeek.query
                    .filter(RankedWeek.league_season_id.in_(season_ids))
                    .with_entities(RankedWeek.league_group_tag, RankedWeek.league_season_id,
                                   RankedWeek.player_tag, RankedWeek.max_attacks)
                    .all()) if season_ids else []
    week_pks = [(w.league_group_tag, w.league_season_id) for w in player_weeks if w.player_tag == player_tag]
    total_done = (RankedBattleLog.query
                  .filter(RankedBattleLog.player_tag == player_tag,
                          RankedBattleLog.attack == True,
                          tuple_(RankedBattleLog.league_group_tag, RankedBattleLog.league_season_id).in_(week_pks))
                  .count()) if week_pks else 0
    player_total_max = sum(w.max_attacks or 0 for w in player_weeks if w.player_tag == player_tag)
    total_seasons    = len(season_ids)
    ranked_score     = min(100, round(100 * total_done / player_total_max)) if player_total_max else 0

    cutoff = now - dt.timedelta(days=battle_days)
    weeks  = battle_days / 7
    battles_in_window = (BattleLog.query
                         .filter(BattleLog.player_tag == player_tag,
                                 BattleLog.attack == True,
                                 BattleLog.time >= cutoff)
                         .count())
    in_clan_tags = [r.tag for r in Player.query.filter(Player.in_clan == True).with_entities(Player.tag).all()]
    clan_total   = (BattleLog.query
                    .filter(BattleLog.player_tag.in_(in_clan_tags),
                            BattleLog.attack == True,
                            BattleLog.time >= cutoff)
                    .count()) if in_clan_tags else 0
    clan_member_count = len(in_clan_tags)
    clan_weekly_avg   = clan_total / clan_member_count / weeks if clan_member_count else 0
    player_weekly_avg = battles_in_window / weeks
    battle_score      = min(100, round(100 * player_weekly_avg / clan_weekly_avg)) if clan_weekly_avg > 0 else 0

    last_raids   = RaidWeekend.query.order_by(RaidWeekend.startTime.desc()).limit(raid_limit).all()
    raid_ids     = [r.id for r in last_raids]
    total_raids  = len(raid_ids)
    raid_attacks = (RaidWeekendLog.query
                    .filter(RaidWeekendLog.playerTag == player_tag,
                            RaidWeekendLog.raid_weekend_id.in_(raid_ids))
                    .count()) if raid_ids else 0
    raid_max_possible = total_raids * 6
    raid_score = min(100, round(100 * raid_attacks / raid_max_possible)) if raid_max_possible else 0

    total = round((ranked_score + battle_score + raid_score) / 3)
    if total >= 80:   label, color = 'Active',   'green'
    elif total >= 50: label, color = 'Regular',  'blue'
    elif total >= 20: label, color = 'Casual',   'accent'
    else:             label, color = 'Inactive', 'red'

    has_data     = total_seasons > 0 or battles_in_window > 0 or total_raids > 0
    battle_detail = (f'{battles_in_window} attacks · {player_weekly_avg:.1f}/week'
                     f' · Clan avg: {clan_weekly_avg:.1f}/week')

    return {
        'score': total, 'label': label, 'label_color': color,
        'ranked_score': ranked_score, 'ranked_max': 100,
        'ranked_detail': f'{total_done}/{player_total_max} attacks across last {total_seasons} seasons',
        'battle_score': battle_score, 'battle_max': 100,
        'battle_detail': battle_detail,
        'raid_score': raid_score, 'raid_max': 100,
        'raid_detail': f'{raid_attacks}/{raid_max_possible} attacks across last {total_raids} raid weekends',
        'has_data': has_data,
    }


def calculate_skill_score(player_tag, period='month'):
    now = dt.datetime.now(dt.timezone.utc)
    if period == 'week':
        season_limit, raid_limit, battle_days = 1, 1, 7
    elif period == 'month':
        season_limit, raid_limit, battle_days = 4, 4, 30
    else:
        season_limit, raid_limit, battle_days = 16, 20, 180

    last_seasons = (db.session.query(RankedWeek.league_season_id)
                    .distinct().order_by(RankedWeek.league_season_id.desc())
                    .limit(season_limit).all())
    season_ids   = [r.league_season_id for r in last_seasons]
    total_seasons = len(season_ids)
    player_weeks = (RankedWeek.query
                    .filter(RankedWeek.player_tag == player_tag,
                            RankedWeek.league_season_id.in_(season_ids))
                    .options(selectinload(RankedWeek.battle_logs))
                    .all()) if season_ids else []

    ranked_scores = []
    for rw in player_weeks:
        a_logs      = [l for l in rw.battle_logs if l.attack is True or l.attack == 1]
        player_th   = rw.townhall or 0
        max_attacks = rw.max_attacks or 0
        if not max_attacks:
            continue
        adj = []
        for l in a_logs:
            try: opp_th = int(l.opponent_th)
            except: opp_th = player_th
            adj.append((l.stars or 0) * _calc_th_multiplier(opp_th - player_th, player_th))
        lm = _league_mult(rw.league_tier, player_th)
        score_100 = min(round(sum(adj) / max_attacks * lm * 100 / 3.45), 100)
        ranked_scores.append(score_100)
    ranked_scores.extend([0] * (total_seasons - len(ranked_scores)))
    avg_ranked   = sum(ranked_scores) / len(ranked_scores) if ranked_scores else 0
    ranked_skill = round(avg_ranked)

    last_raids = RaidWeekend.query.order_by(RaidWeekend.startTime.desc()).limit(raid_limit).all()
    raid_ids   = [r.id for r in last_raids]
    total_raids = len(raid_ids)
    player_raid_logs = (RaidWeekendLog.query
                        .filter(RaidWeekendLog.playerTag == player_tag,
                                RaidWeekendLog.raid_weekend_id.in_(raid_ids))
                        .all()) if raid_ids else []
    logs_by_raid  = {}
    for l in player_raid_logs:
        logs_by_raid.setdefault(l.raid_weekend_id, []).append(l)
    raid_scores = [_raid_verdict(logs_by_raid.get(rid, []))[2] for rid in raid_ids]
    avg_raid    = sum(raid_scores) / len(raid_scores) if raid_scores else 0
    raid_skill  = round(avg_raid)

    cutoff    = now - dt.timedelta(days=battle_days)
    loot_expr = (func.coalesce(BattleLog.loot_gold, 0) +
                 func.coalesce(BattleLog.loot_elixir, 0) +
                 func.coalesce(BattleLog.loot_dark_elixir, 0))
    player_loot = (db.session.query(func.sum(loot_expr))
                   .filter(BattleLog.player_tag == player_tag,
                           BattleLog.attack == True,
                           BattleLog.time >= cutoff)
                   .scalar()) or 0
    in_clan_tags = [r.tag for r in Player.query.filter(Player.in_clan == True).with_entities(Player.tag).all()]
    clan_loot_total = (db.session.query(func.sum(loot_expr))
                       .filter(BattleLog.player_tag.in_(in_clan_tags),
                               BattleLog.attack == True,
                               BattleLog.time >= cutoff)
                       .scalar() or 0) if in_clan_tags else 0
    clan_avg_loot = clan_loot_total / len(in_clan_tags) if in_clan_tags else 0
    battle_skill  = min(100, round(100 * player_loot / clan_avg_loot)) if clan_avg_loot > 0 else 0

    total = round((ranked_skill + raid_skill + battle_skill) / 3)
    if total >= 80:   label, color = 'Elite',   'purple'
    elif total >= 60: label, color = 'Strong',  'green'
    elif total >= 40: label, color = 'Average', 'blue'
    elif total >= 20: label, color = 'Weak',    'accent'
    else:             label, color = 'Novice',  'muted'

    has_data = total_seasons > 0 or total_raids > 0 or player_loot > 0

    return {
        'score': total, 'label': label, 'label_color': color,
        'ranked_skill': ranked_skill, 'ranked_max': 100,
        'ranked_detail': f'Avg verdict {avg_ranked:.0f}/100 · {len(player_weeks)}/{total_seasons} seasons played',
        'raid_skill': raid_skill, 'raid_max': 100,
        'raid_detail': f'Avg verdict {avg_raid:.0f}/100 · {total_raids} raids',
        'battle_skill': battle_skill, 'battle_max': 100,
        'battle_detail': f'{_fmt_loot(player_loot)} loot · Clan avg: {_fmt_loot(clan_avg_loot)}',
        'has_data': has_data,
    }


@player_bp.route('/player/<tag>')
def player_profile(tag):
    actual_tag = '#' + tag
    player = db_player_get(actual_tag)
    if not player:
        return render_template('player/player_profile.html', player=None, player_tag=actual_tag), 404

    _act_week  = calculate_activity_score(actual_tag, 'week')
    _act_month = calculate_activity_score(actual_tag, 'month')
    _act_6m    = calculate_activity_score(actual_tag, '6months')
    activity_periods = {}
    if _act_week['has_data']:  activity_periods['week']    = _act_week
    if _act_month['has_data']: activity_periods['month']   = _act_month
    if _act_6m['has_data']:    activity_periods['6months'] = _act_6m
    activity = _act_week

    _sk_week  = calculate_skill_score(actual_tag, 'week')
    _sk_month = calculate_skill_score(actual_tag, 'month')
    _sk_6m    = calculate_skill_score(actual_tag, '6months')
    skill_periods = {}
    if _sk_week['has_data']:  skill_periods['week']    = _sk_week
    if _sk_month['has_data']: skill_periods['month']   = _sk_month
    if _sk_6m['has_data']:    skill_periods['6months'] = _sk_6m

    ranked_weeks_q = (RankedWeek.query
                      .filter(RankedWeek.player_tag == actual_tag)
                      .order_by(RankedWeek.start_day.desc())
                      .limit(10)
                      .options(selectinload(RankedWeek.battle_logs))
                      .all())
    ranked_history = []
    for rw in ranked_weeks_q:
        a_logs    = [l for l in rw.battle_logs if l.attack is True or l.attack == 1]
        d_logs    = [l for l in rw.battle_logs if not (l.attack is True or l.attack == 1)]
        a_stars   = [l.stars or 0 for l in a_logs]
        d_stars   = [l.stars or 0 for l in d_logs]
        player_th = rw.townhall or player.current_th or 0
        max_attacks = rw.max_attacks or 0
        adj_scores = []
        for l in a_logs:
            try: opp_th = int(l.opponent_th)
            except: opp_th = player_th
            adj_scores.append((l.stars or 0) * _calc_th_multiplier(opp_th - player_th, player_th))
        th_adj    = sum(adj_scores) / max_attacks if max_attacks else 0.0
        lm        = _league_mult(rw.league_tier, player_th)
        score_100 = min(round(th_adj * lm * 100 / 3.45), 100)
        badge_class, judge_label, _ = _ranked_verdict(score_100, len(a_logs), max_attacks)
        ranked_history.append({
            'league_season_id': rw.league_season_id,
            'start_day': rw.start_day.strftime('%d.%m.%y') if rw.start_day else '—',
            'end_day':   rw.end_day.strftime('%d.%m.%y')   if rw.end_day   else '—',
            'league_tier': rw.league_tier or '—',
            'league_icon': rw.league_icon or '',
            'rank': rw.rank,
            'trophies': rw.trophies or 0,
            'att_count': len(a_logs), 'att_max': max_attacks,
            'att_avg': round(sum(a_stars) / len(a_stars), 2) if a_stars else 0,
            'def_count': len(d_logs),
            'def_avg': round(sum(d_stars) / len(d_stars), 2) if d_stars else 0,
            'is_done': bool(rw.is_done),
            'badge_class': badge_class,
            'judge_label': judge_label,
            'score_100': score_100,
        })

    recent_battles_q = (BattleLog.query
                        .filter(BattleLog.player_tag == actual_tag)
                        .order_by(BattleLog.time.desc())
                        .limit(20)
                        .all())
    battle_history = []
    for b in recent_battles_q:
        local_time = to_local(b.time)
        battle_history.append({
            'time':         local_time.strftime('%d.%m.%y %H:%M') if local_time else '—',
            'opponent_tag': b.opponent_tag or '—',
            'stars':        min(b.stars or 0, 3),
            'percentage':   b.percentage or 0,
            'gold':         b.loot_gold or 0,
            'elixir':       b.loot_elixir or 0,
            'dark':         b.loot_dark_elixir or 0,
            'type':         b.type or '—',
            'attack':       bool(b.attack),
        })

    player_raid_logs = RaidWeekendLog.query.filter(RaidWeekendLog.playerTag == actual_tag).all()
    raid_logs_by_id  = {}
    for l in player_raid_logs:
        raid_logs_by_id.setdefault(l.raid_weekend_id, []).append(l)

    all_raids   = RaidWeekend.query.order_by(RaidWeekend.startTime.desc()).all()
    raid_history = []
    for r in all_raids:
        logs = raid_logs_by_id.get(r.id, [])
        cleanup_ids, solo_wipe_count = _district_stats(logs)
        non_cleanup = [l.percentage for l in logs if l.id not in cleanup_ids and l.percentage is not None]
        badge_class, judge_label, score_100 = _raid_verdict(logs)
        raid_history.append({
            'raid_id':    r.id,
            'start':      r.startTime.strftime('%d.%m.%Y') if r.startTime else '—',
            'end':        r.endTime.strftime('%d.%m.%Y')   if r.endTime   else '—',
            'participated': len(logs) > 0,
            'att_count':  len(logs),
            'avg_pct':    round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0,
            'solo_wipes': solo_wipe_count,
            'cleanups':   len(cleanup_ids),
            'badge_class': badge_class,
            'judge_label': judge_label,
            'score_100':   score_100,
        })

    return render_template('player/player_profile.html',
                           player=player,
                           activity=activity,
                           activity_periods=activity_periods,
                           skill_periods=skill_periods,
                           ranked_history=ranked_history,
                           battle_history=battle_history,
                           raid_history=raid_history)


@player_bp.route('/clan')
def clan_overview():
    period = request.args.get('period', 'month')
    if period not in ('week', 'month', '6months'):
        period = 'month'

    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
    player_cards = []
    for player in players:
        activity = calculate_activity_score(player.tag, period)
        skill    = calculate_skill_score(player.tag, period)
        player_cards.append({
            'name':         player.name or player.tag,
            'tag':          player.tag,
            'tag_url':      player.tag.replace('#', ''),
            'th':           player.current_th,
            'league_icon':  player.league_icon,
            'activity':     activity,
            'skill':        skill,
            'combined':     activity['score'] + skill['score'],
        })
    player_cards.sort(key=lambda x: (-x['combined'], x['name']))

    return render_template('player/clan_overview.html', player_cards=player_cards, period=period)
