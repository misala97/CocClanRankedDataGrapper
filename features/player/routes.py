import datetime as dt

from flask import Blueprint, render_template, request
from sqlalchemy import func, tuple_
from sqlalchemy.orm import selectinload

from extensions import db
from models import Player, RankedWeek, RankedBattleLog, BattleLog, RaidWeekend, RaidWeekendLog, ClanWar, ClanWarMember, ClanWarAttack
from services.db import db_player_get
from services.helpers import (
    _ranked_verdict, _calc_ranked_score,
    _district_stats, _raid_verdict, LOCAL_TZ,
    _is_attack, week_cutoff, filter_import_window,
)



from features.war.war_combos import classify_attack, get_war_verdict, get_attack_context

player_bp = Blueprint('player', __name__)


def _war_player_verdict(player_tag, player_th, player_attacks, all_attacks_in_war, opp_th_lookup):
    """Return (score, verdict_label, badge, labels) for one player in one war."""
    atk_on_def = {}
    for a in sorted(all_attacks_in_war, key=lambda a: a.attack_order or 0):
        atk_on_def.setdefault(a.defender_tag, []).append(a)

    labels = []
    for atk in sorted(player_attacks, key=lambda a: a.attack_order or 0):
        opp_th = opp_th_lookup.get(atk.defender_tag, player_th)
        already_3star, partially = get_attack_context(atk, atk_on_def)
        labels.append(classify_attack(atk.stars or 0, player_th, opp_th, already_3star, partially))

    while len(labels) < 2:
        labels.append('no_attack')

    score, verdict_label, badge = get_war_verdict(labels[0], labels[1])
    return score, verdict_label, badge, labels


def _fmt_loot(n):
    n = int(n or 0)
    if n >= 1_000_000: return f'{n / 1_000_000:.1f}M'
    if n >= 1_000:     return f'{n / 1_000:.0f}K'
    return str(n)


def _period_limits(period):
    if period == 'week':  return 1,  1,   7,  2
    if period == 'month': return 4,  4,  30,  8
    return                       16, 20, 180, 30


def calculate_activity_score(player_tag, period='week'):
    now = dt.datetime.now(dt.timezone.utc)
    season_limit, raid_limit, battle_days, war_limit = _period_limits(period)

    player_obj = Player.query.filter_by(tag=player_tag).first()
    join_date  = player_obj.join_date if player_obj else None

    # Get last N seasons with start dates, then filter to those after join_date
    season_rows = (db.session.query(RankedWeek.league_season_id, func.min(RankedWeek.start_day))
                   .group_by(RankedWeek.league_season_id)
                   .order_by(RankedWeek.league_season_id.desc())
                   .limit(season_limit)
                   .all())
    eligible_season_rows = [(sid, start) for sid, start in season_rows
                            if join_date is None or start is None or start >= join_date]
    season_ids             = [sid for sid, _ in eligible_season_rows]
    total_eligible_seasons = len(eligible_season_rows)

    # Player's participated weeks within eligible seasons
    player_weeks = (RankedWeek.query
                    .filter(RankedWeek.player_tag == player_tag,
                            RankedWeek.league_season_id.in_(season_ids))
                    .with_entities(RankedWeek.league_group_tag, RankedWeek.league_season_id, RankedWeek.max_attacks)
                    .all()) if season_ids else []
    week_pks = [(w.league_group_tag, w.league_season_id) for w in player_weeks]
    total_done = (RankedBattleLog.query
                  .filter(RankedBattleLog.player_tag == player_tag,
                          RankedBattleLog.attack == True,
                          tuple_(RankedBattleLog.league_group_tag, RankedBattleLog.league_season_id).in_(week_pks))
                  .count()) if week_pks else 0

    participated_season_ids = {w.league_season_id for w in player_weeks}
    player_total_max        = sum(w.max_attacks or 0 for w in player_weeks)

    # Seasons the player was eligible for but didn't participate in count as 0/avg_max
    missed_season_ids = [sid for sid in season_ids if sid not in participated_season_ids]
    if missed_season_ids:
        avg_max_rows = dict(
            db.session.query(RankedWeek.league_season_id, func.avg(RankedWeek.max_attacks))
            .filter(RankedWeek.league_season_id.in_(missed_season_ids))
            .group_by(RankedWeek.league_season_id)
            .all()
        )
        for sid in missed_season_ids:
            player_total_max += round(avg_max_rows.get(sid) or 8)

    ranked_score = min(100, round(100 * total_done / player_total_max)) if player_total_max else 0

    cutoff = week_cutoff(now, battle_days)
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

    last_raids = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).limit(raid_limit).all()
    if join_date:
        eligible_raids = [r for r in last_raids if r.start_time and r.start_time.date() >= join_date]
    else:
        eligible_raids = last_raids
    eligible_raid_ids = [r.id for r in eligible_raids]
    eligible_raid_count = len(eligible_raids)
    raid_attacks = (RaidWeekendLog.query
                    .filter(RaidWeekendLog.player_tag == player_tag,
                            RaidWeekendLog.raid_weekend_id.in_(eligible_raid_ids))
                    .count()) if eligible_raid_ids else 0
    raid_max_possible = eligible_raid_count * 6
    raid_score = min(100, round(100 * raid_attacks / raid_max_possible)) if raid_max_possible else 0

    # ── War component (regular wars only, wars player was selected for) ───────
    last_wars = (ClanWar.query
                 .order_by(ClanWar.start_time.desc())
                 .limit(war_limit).all())
    war_ids = [w.id for w in last_wars]
    player_war_members = (ClanWarMember.query
                          .filter(ClanWarMember.clan_war_id.in_(war_ids),
                                  ClanWarMember.player_tag == player_tag,
                                  ClanWarMember.is_opponent == False)
                          .all()) if war_ids else []
    participated_war_ids = {m.clan_war_id for m in player_war_members}
    total_war_max = len(participated_war_ids) * 2
    war_attacks_done = (ClanWarAttack.query
                        .filter(ClanWarAttack.clan_war_id.in_(list(participated_war_ids)),
                                ClanWarAttack.attacker_tag == player_tag)
                        .count()) if participated_war_ids else 0
    war_score = min(100, round(100 * war_attacks_done / total_war_max)) if total_war_max else 0

    act_components = [ranked_score, battle_score, raid_score]
    if participated_war_ids:
        act_components.append(war_score)
    total = round(sum(act_components) / len(act_components))

    if total >= 80:   label, color = 'Active',   'green'
    elif total >= 50: label, color = 'Regular',  'blue'
    elif total >= 20: label, color = 'Casual',   'accent'
    else:             label, color = 'Inactive', 'red'

    has_data     = total_eligible_seasons > 0 or battles_in_window > 0 or eligible_raid_count > 0
    battle_detail = (f'{battles_in_window} attacks · {player_weekly_avg:.1f}/week'
                     f' · Clan avg: {clan_weekly_avg:.1f}/week')

    return {
        'score': total, 'label': label, 'label_color': color,
        'ranked_score': ranked_score, 'ranked_max': 100,
        'ranked_detail': f'{total_done}/{player_total_max} attacks · {len(player_weeks)}/{total_eligible_seasons} seasons played',
        'battle_score': battle_score, 'battle_max': 100,
        'battle_detail': battle_detail,
        'raid_score': raid_score, 'raid_max': 100,
        'raid_detail': f'{raid_attacks}/{raid_max_possible} attacks across last {eligible_raid_count} raid weekends',
        'war_score': war_score, 'war_max': 100,
        'war_score_has_data': bool(participated_war_ids),
        'war_detail': f'{war_attacks_done}/{total_war_max} attacks across {len(participated_war_ids)} wars',
        'has_data': has_data,
    }


def calculate_skill_score(player_tag, period='month'):
    now = dt.datetime.now(dt.timezone.utc)
    season_limit, raid_limit, battle_days, war_limit = _period_limits(period)

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
        a_logs      = [l for l in rw.battle_logs if _is_attack(l)]
        player_th   = rw.townhall or 0
        max_attacks = rw.max_attacks or 0
        if not max_attacks:
            continue
        score_100, _, _ = _calc_ranked_score(a_logs, player_th, max_attacks, rw.league_tier)
        ranked_scores.append(score_100)
    avg_ranked   = sum(ranked_scores) / len(ranked_scores) if ranked_scores else 0
    ranked_skill = round(avg_ranked)

    last_raids = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).limit(raid_limit).all()
    raid_ids   = [r.id for r in last_raids]
    total_raids = len(raid_ids)
    player_raid_logs = (RaidWeekendLog.query
                        .filter(RaidWeekendLog.player_tag == player_tag,
                                RaidWeekendLog.raid_weekend_id.in_(raid_ids))
                        .all()) if raid_ids else []
    logs_by_raid = {}
    for l in player_raid_logs:
        logs_by_raid.setdefault(l.raid_weekend_id, []).append(l)
    attended_raid_ids = [rid for rid in raid_ids if rid in logs_by_raid]
    raid_scores = [_raid_verdict(logs_by_raid[rid])[2] for rid in attended_raid_ids]
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

    # ── War skill (regular wars only, wars player was selected for and attacked in) ──
    last_wars = (ClanWar.query
                 .order_by(ClanWar.start_time.desc())
                 .limit(war_limit).all())
    war_ids = [w.id for w in last_wars]
    player_war_members = (ClanWarMember.query
                          .filter(ClanWarMember.clan_war_id.in_(war_ids),
                                  ClanWarMember.player_tag == player_tag,
                                  ClanWarMember.is_opponent == False)
                          .all()) if war_ids else []
    war_member_map       = {m.clan_war_id: m for m in player_war_members}
    participated_war_ids = set(war_member_map.keys())

    # Fetch ALL attacks in player's wars (needed for context in classify_attack)
    all_attacks_in_wars = (ClanWarAttack.query
                           .filter(ClanWarAttack.clan_war_id.in_(list(participated_war_ids)))
                           .all()) if participated_war_ids else []

    opp_members = (ClanWarMember.query
                   .filter(ClanWarMember.clan_war_id.in_(list(participated_war_ids)),
                           ClanWarMember.is_opponent == True)
                   .all()) if participated_war_ids else []
    opp_th_by_war = {}
    for m in opp_members:
        opp_th_by_war.setdefault(m.clan_war_id, {})[m.player_tag] = m.town_hall_level

    all_by_war      = {}
    player_by_war   = {}
    for a in all_attacks_in_wars:
        all_by_war.setdefault(a.clan_war_id, []).append(a)
        if a.attacker_tag == player_tag:
            player_by_war.setdefault(a.clan_war_id, []).append(a)

    war_skill_scores = []
    for war_id in participated_war_ids:
        p_attacks = player_by_war.get(war_id, [])
        if not p_attacks:
            war_skill_scores.append(0)
            continue
        my_member = war_member_map.get(war_id)
        player_th = my_member.town_hall_level if my_member else 0
        score, _, _, _ = _war_player_verdict(
            player_tag, player_th, p_attacks,
            all_by_war.get(war_id, []),
            opp_th_by_war.get(war_id, {}),
        )
        war_skill_scores.append(score)
    war_skill = round(sum(war_skill_scores) / len(war_skill_scores)) if war_skill_scores else 0

    skill_components = []
    if ranked_scores:       skill_components.append(ranked_skill)
    if attended_raid_ids:   skill_components.append(raid_skill)
    if player_loot > 0:     skill_components.append(battle_skill)
    if war_skill_scores:    skill_components.append(war_skill)
    total = round(sum(skill_components) / len(skill_components)) if skill_components else 0

    if total >= 80:   label, color = 'Elite',   'purple'
    elif total >= 60: label, color = 'Strong',  'green'
    elif total >= 40: label, color = 'Average', 'blue'
    elif total >= 20: label, color = 'Weak',    'accent'
    else:             label, color = 'Novice',  'muted'

    has_data = bool(skill_components)

    return {
        'score': total, 'label': label, 'label_color': color,
        'ranked_skill': ranked_skill, 'ranked_max': 100,
        'ranked_skill_has_data': bool(ranked_scores),
        'ranked_detail': f'Avg verdict {avg_ranked:.0f}/100 · {len(player_weeks)} seasons played',
        'raid_skill': raid_skill, 'raid_max': 100,
        'raid_skill_has_data': bool(attended_raid_ids),
        'raid_detail': f'Avg verdict {avg_raid:.0f}/100 · {len(attended_raid_ids)} raids attended',
        'battle_skill': battle_skill, 'battle_max': 100,
        'battle_skill_has_data': player_loot > 0,
        'battle_detail': f'{_fmt_loot(player_loot)} loot · Clan avg: {_fmt_loot(clan_avg_loot)}',
        'war_skill': war_skill, 'war_max': 100,
        'war_skill_has_data': bool(war_skill_scores),
        'war_detail': f'Avg verdict {war_skill:.0f}/100 · {len(participated_war_ids)} wars selected',
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
        a_logs    = [l for l in rw.battle_logs if _is_attack(l)]
        d_logs    = [l for l in rw.battle_logs if not (_is_attack(l))]
        a_stars   = [l.stars or 0 for l in a_logs]
        d_stars   = [l.stars or 0 for l in d_logs]
        player_th = rw.townhall or player.current_th or 0
        max_attacks = rw.max_attacks or 0
        score_100, _, _ = _calc_ranked_score(a_logs, player_th, max_attacks, rw.league_tier)
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
        battle_history.append({
            'time':         b.time,
            'opponent_tag': b.opponent_tag or '—',
            'stars':        min(b.stars or 0, 3),
            'percentage':   b.percentage or 0,
            'gold':         b.loot_gold or 0,
            'elixir':       b.loot_elixir or 0,
            'dark':         b.loot_dark_elixir or 0,
            'type':         b.type or '—',
            'attack':       bool(b.attack),
        })

    player_raid_logs = RaidWeekendLog.query.filter(RaidWeekendLog.player_tag == actual_tag).all()
    raid_logs_by_id  = {}
    for l in player_raid_logs:
        raid_logs_by_id.setdefault(l.raid_weekend_id, []).append(l)

    all_raids   = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).all()
    raid_history = []
    for r in all_raids:
        logs = raid_logs_by_id.get(r.id, [])
        cleanup_ids, solo_wipe_count = _district_stats(logs)
        non_cleanup = [l.percentage for l in logs if l.id not in cleanup_ids and l.percentage is not None]
        badge_class, judge_label, score_100 = _raid_verdict(logs)
        raid_history.append({
            'raid_id':    r.id,
            'start':      r.start_time.strftime('%d.%m.%Y') if r.start_time else '—',
            'end':        r.end_time.strftime('%d.%m.%Y')   if r.end_time   else '—',
            'participated': len(logs) > 0,
            'att_count':  len(logs),
            'avg_pct':    round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0,
            'solo_wipes': solo_wipe_count,
            'cleanups':   len(cleanup_ids),
            'badge_class': badge_class,
            'judge_label': judge_label,
            'score_100':   score_100,
        })

    all_wars_q = (ClanWar.query.order_by(ClanWar.start_time.desc()).limit(20).all())
    war_ids_for_history = [w.id for w in all_wars_q]
    player_war_members_h = {m.clan_war_id: m for m in ClanWarMember.query
                             .filter(ClanWarMember.clan_war_id.in_(war_ids_for_history),
                                     ClanWarMember.player_tag == actual_tag,
                                     ClanWarMember.is_opponent == False).all()}

    # All attacks in wars the player was selected for (for context)
    all_attacks_h = {}
    player_attacks_h = {}
    for a in (ClanWarAttack.query
              .filter(ClanWarAttack.clan_war_id.in_(list(player_war_members_h.keys()))).all()):
        all_attacks_h.setdefault(a.clan_war_id, []).append(a)
        if a.attacker_tag == actual_tag:
            player_attacks_h.setdefault(a.clan_war_id, []).append(a)

    opp_th_h = {}
    for m in (ClanWarMember.query
              .filter(ClanWarMember.clan_war_id.in_(list(player_war_members_h.keys())),
                      ClanWarMember.is_opponent == True).all()):
        opp_th_h.setdefault(m.clan_war_id, {})[m.player_tag] = m.town_hall_level

    war_history = []
    for w in all_wars_q:
        member = player_war_members_h.get(w.id)
        if not member:
            continue
        p_attacks = player_attacks_h.get(w.id, [])
        player_th = member.town_hall_level or player.current_th or 0
        score_100, judge_label, badge_class, _ = _war_player_verdict(
            actual_tag, player_th, p_attacks,
            all_attacks_h.get(w.id, []),
            opp_th_h.get(w.id, {}),
        )
        avg_stars = round(sum(a.stars or 0 for a in p_attacks) / len(p_attacks), 2) if p_attacks else 0
        war_history.append({
            'war_id':      w.id,
            'start':       w.start_time.strftime('%d.%m.%Y') if w.start_time else '—',
            'end':         w.end_time.strftime('%d.%m.%Y')   if w.end_time   else '—',
            'opponent':    w.opponent_name or '—',
            'att_count':   len(p_attacks),
            'att_max':     2,
            'avg_stars':   avg_stars,
            'score_100':   score_100,
            'badge_class': badge_class,
            'judge_label': judge_label,
        })

    return render_template('player/player_profile.html',
                           player=player,
                           activity=activity,
                           activity_periods=activity_periods,
                           skill_periods=skill_periods,
                           ranked_history=ranked_history,
                           battle_history=battle_history,
                           raid_history=raid_history,
                           war_history=war_history)


def _calculate_scores_bulk(player_tags, period='month'):
    if not player_tags:
        return {}

    now = dt.datetime.now(dt.timezone.utc)
    season_limit, raid_limit, battle_days, war_limit = _period_limits(period)

    weeks_float = battle_days / 7

    # ── seasons (shared) ─────────────────────────────────────────────────────
    season_rows = (db.session.query(RankedWeek.league_season_id, func.min(RankedWeek.start_day))
                   .group_by(RankedWeek.league_season_id)
                   .order_by(RankedWeek.league_season_id.desc())
                   .limit(season_limit)
                   .all())
    season_ids       = [sid for sid, _ in season_rows]
    season_start_map = {sid: start for sid, start in season_rows}

    all_weeks = (RankedWeek.query
                 .filter(RankedWeek.league_season_id.in_(season_ids))
                 .options(selectinload(RankedWeek.battle_logs))
                 .all()) if season_ids else []
    weeks_by_player = {}
    for w in all_weeks:
        weeks_by_player.setdefault(w.player_tag, []).append(w)

    # Avg max_attacks per season (used for missed-season penalty)
    season_avg_max = dict(
        db.session.query(RankedWeek.league_season_id, func.avg(RankedWeek.max_attacks))
        .filter(RankedWeek.league_season_id.in_(season_ids))
        .group_by(RankedWeek.league_season_id)
        .all()
    ) if season_ids else {}

    # ── ranked attack counts (bulk) ───────────────────────────────────────────
    all_week_pks = [(w.league_group_tag, w.league_season_id) for w in all_weeks]
    if all_week_pks:
        ranked_attack_map = dict(
            db.session.query(RankedBattleLog.player_tag, func.count())
            .filter(RankedBattleLog.player_tag.in_(player_tags),
                    RankedBattleLog.attack == True,
                    tuple_(RankedBattleLog.league_group_tag, RankedBattleLog.league_season_id).in_(all_week_pks))
            .group_by(RankedBattleLog.player_tag)
            .all()
        )
    else:
        ranked_attack_map = {}

    # ── battle stats (bulk) ───────────────────────────────────────────────────
    cutoff = week_cutoff(now, battle_days)
    loot_expr = (func.coalesce(BattleLog.loot_gold, 0) +
                 func.coalesce(BattleLog.loot_elixir, 0) +
                 func.coalesce(BattleLog.loot_dark_elixir, 0))

    battle_rows = (db.session.query(BattleLog.player_tag, func.count(), func.sum(loot_expr))
                   .filter(BattleLog.player_tag.in_(player_tags),
                           BattleLog.attack == True,
                           BattleLog.time >= cutoff)
                   .group_by(BattleLog.player_tag)
                   .all())
    battle_count_map = {tag: cnt  for tag, cnt, _   in battle_rows}
    loot_map         = {tag: loot for tag, _,   loot in battle_rows}

    clan_member_count = len(player_tags)
    clan_total_battles = sum(battle_count_map.values())
    clan_total_loot    = sum((v or 0) for v in loot_map.values())
    clan_weekly_avg    = clan_total_battles / clan_member_count / weeks_float if clan_member_count else 0
    clan_avg_loot      = clan_total_loot / clan_member_count if clan_member_count else 0

    # ── raid logs (bulk) ─────────────────────────────────────────────────────
    last_raids = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).limit(raid_limit).all()
    raid_ids   = [r.id for r in last_raids]

    all_raid_logs = (RaidWeekendLog.query
                     .filter(RaidWeekendLog.player_tag.in_(player_tags),
                             RaidWeekendLog.raid_weekend_id.in_(raid_ids))
                     .all()) if raid_ids else []
    raid_logs_by_player = {}
    for l in all_raid_logs:
        raid_logs_by_player.setdefault(l.player_tag, {}).setdefault(l.raid_weekend_id, []).append(l)

    # ── join dates (bulk) ────────────────────────────────────────────────────
    join_dates = dict(
        db.session.query(Player.tag, Player.join_date)
        .filter(Player.tag.in_(player_tags))
        .all()
    )

    # ── war data (bulk, regular wars only) ───────────────────────────────────
    last_wars = (ClanWar.query
                 .order_by(ClanWar.start_time.desc())
                 .limit(war_limit).all())
    war_ids = [w.id for w in last_wars]

    all_war_members = (ClanWarMember.query
                       .filter(ClanWarMember.clan_war_id.in_(war_ids),
                               ClanWarMember.player_tag.in_(player_tags),
                               ClanWarMember.is_opponent == False)
                       .all()) if war_ids else []
    war_members_by_player = {}
    for m in all_war_members:
        war_members_by_player.setdefault(m.player_tag, {})[m.clan_war_id] = m

    # All attacks in the war window (needed for classify_attack context)
    all_war_attacks_bulk = (ClanWarAttack.query
                            .filter(ClanWarAttack.clan_war_id.in_(war_ids))
                            .all()) if war_ids else []
    all_attacks_by_war = {}
    war_attacks_by_player = {}
    for a in all_war_attacks_bulk:
        all_attacks_by_war.setdefault(a.clan_war_id, []).append(a)
        if a.attacker_tag in set(player_tags):
            war_attacks_by_player.setdefault(a.attacker_tag, {}).setdefault(a.clan_war_id, []).append(a)

    participated_war_ids_all = {m.clan_war_id for m in all_war_members}
    all_opp_members = (ClanWarMember.query
                       .filter(ClanWarMember.clan_war_id.in_(list(participated_war_ids_all)),
                               ClanWarMember.is_opponent == True)
                       .all()) if participated_war_ids_all else []
    opp_th_by_war_bulk = {}
    for m in all_opp_members:
        opp_th_by_war_bulk.setdefault(m.clan_war_id, {})[m.player_tag] = m.town_hall_level

    # ── compute per-player ────────────────────────────────────────────────────
    results = {}
    for tag in player_tags:
        join_date = join_dates.get(tag)
        eligible_season_ids = [sid for sid in season_ids
                               if join_date is None or season_start_map.get(sid) is None
                               or season_start_map[sid] >= join_date]

        player_weeks             = weeks_by_player.get(tag, [])
        participated_season_ids  = {w.league_season_id for w in player_weeks}
        player_max               = sum(w.max_attacks or 0 for w in player_weeks
                                       if w.league_season_id in set(eligible_season_ids))
        for sid in eligible_season_ids:
            if sid not in participated_season_ids:
                player_max += round(season_avg_max.get(sid) or 8)

        # --- activity ---
        total_done         = ranked_attack_map.get(tag, 0)
        ranked_score       = min(100, round(100 * total_done / player_max)) if player_max else 0
        battles_in_window  = battle_count_map.get(tag, 0)
        player_weekly_avg  = battles_in_window / weeks_float
        battle_score       = min(100, round(100 * player_weekly_avg / clan_weekly_avg)) if clan_weekly_avg > 0 else 0
        join_date          = join_dates.get(tag)
        eligible_raids     = [r for r in last_raids if not join_date or (r.start_time and r.start_time.date() >= join_date)]
        eligible_raid_ids  = {r.id for r in eligible_raids}
        raid_attacks       = sum(len(v) for rid, v in raid_logs_by_player.get(tag, {}).items() if rid in eligible_raid_ids)
        raid_max_possible  = len(eligible_raids) * 6
        raid_score         = min(100, round(100 * raid_attacks / raid_max_possible)) if raid_max_possible else 0
        # --- war activity ---
        player_war_member_map  = war_members_by_player.get(tag, {})
        player_participated_wars = set(player_war_member_map.keys())
        total_war_max          = len(player_participated_wars) * 2
        player_war_attacks     = sum(len(v) for wid, v in war_attacks_by_player.get(tag, {}).items()
                                     if wid in player_participated_wars)
        war_score              = min(100, round(100 * player_war_attacks / total_war_max)) if total_war_max else 0

        act_components = [ranked_score, battle_score, raid_score]
        if player_participated_wars:
            act_components.append(war_score)
        act_total = round(sum(act_components) / len(act_components))
        if act_total >= 80:   act_label, act_color = 'Active',   'green'
        elif act_total >= 50: act_label, act_color = 'Regular',  'blue'
        elif act_total >= 20: act_label, act_color = 'Casual',   'accent'
        else:                 act_label, act_color = 'Inactive', 'red'

        # --- skill ---
        ranked_skill_scores = []
        for rw in player_weeks:
            a_logs      = [l for l in rw.battle_logs if _is_attack(l)]
            player_th   = rw.townhall or 0
            max_attacks = rw.max_attacks or 0
            if not max_attacks:
                continue
            score_100, _, _ = _calc_ranked_score(a_logs, player_th, max_attacks, rw.league_tier)
            ranked_skill_scores.append(score_100)
        ranked_skill = round(sum(ranked_skill_scores) / len(ranked_skill_scores)) if ranked_skill_scores else 0

        raid_logs_by_id       = raid_logs_by_player.get(tag, {})
        attended_rids         = [rid for rid in raid_ids if rid in raid_logs_by_id]
        raid_skill_scores     = [_raid_verdict(raid_logs_by_id[rid])[2] for rid in attended_rids]
        raid_skill            = round(sum(raid_skill_scores) / len(raid_skill_scores)) if raid_skill_scores else 0

        player_loot  = loot_map.get(tag) or 0
        battle_skill = min(100, round(100 * player_loot / clan_avg_loot)) if clan_avg_loot > 0 else 0

        # --- war skill ---
        war_skill_scores = []
        for war_id, p_attacks in war_attacks_by_player.get(tag, {}).items():
            if war_id not in player_participated_wars:
                continue
            my_member = player_war_member_map.get(war_id)
            player_th = my_member.town_hall_level if my_member else 0
            score, _, _, _ = _war_player_verdict(
                tag, player_th, p_attacks,
                all_attacks_by_war.get(war_id, []),
                opp_th_by_war_bulk.get(war_id, {}),
            )
            war_skill_scores.append(score)
        war_skill = round(sum(war_skill_scores) / len(war_skill_scores)) if war_skill_scores else 0

        sk_components = []
        if ranked_skill_scores:  sk_components.append(ranked_skill)
        if attended_rids:        sk_components.append(raid_skill)
        if player_loot > 0:      sk_components.append(battle_skill)
        if war_skill_scores:     sk_components.append(war_skill)
        sk_total = round(sum(sk_components) / len(sk_components)) if sk_components else 0
        if sk_total >= 80:   sk_label, sk_color = 'Elite',   'purple'
        elif sk_total >= 60: sk_label, sk_color = 'Strong',  'green'
        elif sk_total >= 40: sk_label, sk_color = 'Average', 'blue'
        elif sk_total >= 20: sk_label, sk_color = 'Weak',    'accent'
        else:                sk_label, sk_color = 'Novice',  'muted'

        results[tag] = {
            'activity': {
                'score': act_total, 'label': act_label, 'label_color': act_color,
                'ranked_score': ranked_score, 'battle_score': battle_score,
                'raid_score': raid_score, 'war_score': war_score,
                'war_score_has_data': bool(player_participated_wars),
                'has_data': len(eligible_season_ids) > 0 or battles_in_window > 0 or len(eligible_raids) > 0,
            },
            'skill': {
                'score': sk_total, 'label': sk_label, 'label_color': sk_color,
                'ranked_skill': ranked_skill, 'raid_skill': raid_skill,
                'battle_skill': battle_skill, 'war_skill': war_skill,
                'ranked_skill_has_data': bool(ranked_skill_scores),
                'raid_skill_has_data':   bool(attended_rids),
                'battle_skill_has_data': player_loot > 0,
                'war_skill_has_data':    bool(war_skill_scores),
                'has_data': bool(sk_components),
            },
        }

    return results


@player_bp.route('/clan')
def clan_overview():
    period = request.args.get('period', 'month')
    if period not in ('week', 'month', '6months'):
        period = 'month'

    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
    scores  = _calculate_scores_bulk([p.tag for p in players], period)

    player_cards = []
    for player in players:
        s        = scores.get(player.tag, {})
        activity = s.get('activity', {'score': 0, 'label': 'Inactive', 'label_color': 'red',
                                      'ranked_score': 0, 'battle_score': 0, 'raid_score': 0, 'has_data': False})
        skill    = s.get('skill',    {'score': 0, 'label': 'Novice',   'label_color': 'muted',
                                      'ranked_skill': 0, 'battle_skill': 0, 'raid_skill': 0, 'has_data': False})
        player_cards.append({
            'name':        player.name or player.tag,
            'tag':         player.tag,
            'tag_url':     player.tag.replace('#', ''),
            'th':          player.current_th,
            'league_icon': player.league_icon,
            'activity':    activity,
            'skill':       skill,
            'combined':    activity['score'] + skill['score'],
        })
    player_cards.sort(key=lambda x: (-x['combined'], x['name']))

    return render_template('player/clan_overview.html', player_cards=player_cards, period=period)
