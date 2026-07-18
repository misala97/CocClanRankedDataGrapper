import datetime as dt

from flask import Blueprint, render_template, request
from sqlalchemy import func, tuple_
from sqlalchemy.orm import selectinload

from extensions import db
from models import Player, RankedWeek, RankedBattleLog, BattleLog, RaidWeekend, RaidWeekendLog, ClanWar, ClanWarMember, ClanWarAttack, CWLSeason, CWLWar, CWLMember, CWLAttack
from services.db import db_player_get
from services.helpers import (
    _ranked_verdict, _calc_ranked_score,
    _district_stats, _raid_verdict, LOCAL_TZ,
    _is_attack, week_cutoff, filter_import_window,
)



from features.war.war_combos import classify_attack, get_war_verdict, get_attack_context, get_cwl_verdict
from features.cwl.routes import _build_cwl_matchup_rates, cwl_attack_verdict
from features.auth.routes import _is_super_admin

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
    from app import CLAN_TAG
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

    # ── CWL activity component ────────────────────────────────────────────────
    cwl_limit = {'week': 1, 'month': 2, '6months': 6}.get(period, 2)
    cwl_season_ids = [s.id for s in CWLSeason.query.order_by(CWLSeason.id.desc()).limit(cwl_limit).all()]
    if cwl_season_ids:
        # Anchor on member records — avoids pulling in wars between other CWL clans
        _cwl_selected_wars = [m.war_id for m in CWLMember.query
                               .join(CWLWar, CWLMember.war_id == CWLWar.id)
                               .filter(CWLMember.player_tag == player_tag,
                                       CWLMember.clan_tag == CLAN_TAG,
                                       CWLWar.season_id.in_(cwl_season_ids))
                               .all()]
        cwl_rounds_selected = len(_cwl_selected_wars)
        cwl_attacks_done = (CWLAttack.query
                            .filter(CWLAttack.war_id.in_(_cwl_selected_wars),
                                    CWLAttack.attacker_tag == player_tag)
                            .count()) if _cwl_selected_wars else 0
    else:
        cwl_rounds_selected = cwl_attacks_done = 0
        _cwl_selected_wars = []
    cwl_score = min(100, round(100 * cwl_attacks_done / cwl_rounds_selected)) if cwl_rounds_selected else 0
    cwl_score_has_data = cwl_rounds_selected > 0
    cwl_act_detail = f'{cwl_attacks_done}/{cwl_rounds_selected} attacks across last {len(cwl_season_ids)} CWL seasons'

    act_components = [ranked_score, battle_score, raid_score]
    if participated_war_ids:
        act_components.append(war_score)
    if cwl_score_has_data:
        act_components.append(cwl_score)
    total = round(sum(act_components) / len(act_components))

    if total >= 80:   label, color = 'Active',   'green'
    elif total >= 50: label, color = 'Regular',  'blue'
    elif total >= 20: label, color = 'Casual',   'yellow'
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
        'cwl_score': cwl_score, 'cwl_max': 100,
        'cwl_score_has_data': cwl_score_has_data,
        'cwl_detail': cwl_act_detail,
        'has_data': has_data,
    }


def calculate_skill_score(player_tag, period='month'):
    from app import CLAN_TAG
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

    # ── CWL skill component ───────────────────────────────────────────────────
    cwl_limit = {'week': 1, 'month': 2, '6months': 6}.get(period, 2)
    cwl_season_ids_sk = [s.id for s in CWLSeason.query.order_by(CWLSeason.id.desc()).limit(cwl_limit).all()]
    if cwl_season_ids_sk:
        cwl_player_wars = [m.war_id for m in CWLMember.query
                           .join(CWLWar, CWLMember.war_id == CWLWar.id)
                           .filter(CWLMember.player_tag == player_tag,
                                   CWLMember.clan_tag == CLAN_TAG,
                                   CWLWar.season_id.in_(cwl_season_ids_sk))
                           .all()]
        cwl_atk_by_war = {}
        for a in (CWLAttack.query
                  .filter(CWLAttack.war_id.in_(cwl_player_wars),
                          CWLAttack.attacker_tag == player_tag)
                  .all()) if cwl_player_wars else []:
            cwl_atk_by_war.setdefault(a.war_id, []).append(a)
    else:
        cwl_player_wars = []
        cwl_atk_by_war = {}

    cwl_matchup_rates, _, _ = _build_cwl_matchup_rates()
    cwl_member_by_key = {
        (m.war_id, m.player_tag): m
        for m in CWLMember.query.filter(CWLMember.war_id.in_(cwl_player_wars)).all()
    } if cwl_player_wars else {}

    cwl_skill_scores = []
    for wid in cwl_player_wars:
        atks = cwl_atk_by_war.get(wid, [])
        if atks:
            sc, _, _ = cwl_attack_verdict(atks[0], cwl_member_by_key, cwl_matchup_rates)
            cwl_skill_scores.append(sc)
        else:
            cwl_skill_scores.append(0)
    cwl_skill = round(sum(cwl_skill_scores) / len(cwl_skill_scores)) if cwl_skill_scores else 0
    cwl_skill_has_data = bool(cwl_player_wars)
    avg_cwl = sum(cwl_skill_scores) / len(cwl_skill_scores) if cwl_skill_scores else 0

    skill_components = []
    if ranked_scores:       skill_components.append(ranked_skill)
    if attended_raid_ids:   skill_components.append(raid_skill)
    if player_loot > 0:     skill_components.append(battle_skill)
    if war_skill_scores:    skill_components.append(war_skill)
    if cwl_skill_has_data:  skill_components.append(cwl_skill)
    total = round(sum(skill_components) / len(skill_components)) if skill_components else 0

    if total >= 80:   label, color = 'Elite',   'purple'
    elif total >= 60: label, color = 'Strong',  'green'
    elif total >= 40: label, color = 'Average', 'blue'
    elif total >= 20: label, color = 'Weak',    'yellow'
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
        'cwl_skill': cwl_skill, 'cwl_max': 100,
        'cwl_skill_has_data': cwl_skill_has_data,
        'cwl_detail': f'Avg verdict {avg_cwl:.0f}/100 · {len(cwl_player_wars)} CWL rounds selected',
        'has_data': has_data,
    }


def calculate_scores_all_periods(player_tag, cwl_matchup_rates):
    """Compute activity + skill scores for all three periods in a single DB pass.
    Returns (activity_periods_dict, skill_periods_dict) keyed by 'week'/'month'/'6months'.
    """
    from app import CLAN_TAG
    now = dt.datetime.now(dt.timezone.utc)

    _season_limit = {'week': 1,  'month': 4,  '6months': 16}
    _raid_limit   = {'week': 1,  'month': 4,  '6months': 20}
    _battle_days  = {'week': 7,  'month': 30, '6months': 180}
    _war_limit    = {'week': 2,  'month': 8,  '6months': 30}
    _cwl_limit    = {'week': 1,  'month': 2,  '6months': 6}

    # ── 1. Player join date ─────────────────────────────────────────────────
    player_obj = Player.query.filter_by(tag=player_tag).first()
    join_date  = player_obj.join_date if player_obj else None

    # ── 2. Ranked seasons (max 16 + avg max pre-fetched) ───────────────────
    all_season_rows = (db.session.query(RankedWeek.league_season_id, func.min(RankedWeek.start_day))
                       .group_by(RankedWeek.league_season_id)
                       .order_by(RankedWeek.league_season_id.desc())
                       .limit(16).all())
    all_season_ids  = [sid for sid, _ in all_season_rows]

    all_player_weeks = (RankedWeek.query
                        .filter(RankedWeek.player_tag == player_tag,
                                RankedWeek.league_season_id.in_(all_season_ids))
                        .options(selectinload(RankedWeek.battle_logs))
                        .all()) if all_season_ids else []

    all_avg_max = dict(
        db.session.query(RankedWeek.league_season_id, func.avg(RankedWeek.max_attacks))
        .filter(RankedWeek.league_season_id.in_(all_season_ids))
        .group_by(RankedWeek.league_season_id)
        .all()
    ) if all_season_ids else {}

    # ── 3. Clan tags + battle logs (180-day window covers all periods) ──────
    in_clan_tags      = [r.tag for r in Player.query.filter(Player.in_clan == True).with_entities(Player.tag).all()]
    clan_member_count = len(in_clan_tags)
    cutoff_max        = now - dt.timedelta(days=180)

    player_battles_raw = (db.session.query(
            BattleLog.time,
            func.coalesce(BattleLog.loot_gold, 0),
            func.coalesce(BattleLog.loot_elixir, 0),
            func.coalesce(BattleLog.loot_dark_elixir, 0))
        .filter(BattleLog.player_tag == player_tag,
                BattleLog.attack == True,
                BattleLog.time >= cutoff_max)
        .all())

    clan_battles_raw = (db.session.query(
            BattleLog.time,
            func.coalesce(BattleLog.loot_gold, 0),
            func.coalesce(BattleLog.loot_elixir, 0),
            func.coalesce(BattleLog.loot_dark_elixir, 0))
        .filter(BattleLog.player_tag.in_(in_clan_tags),
                BattleLog.attack == True,
                BattleLog.time >= cutoff_max)
        .all()) if in_clan_tags else []

    # ── 4. Raids (max 20) ───────────────────────────────────────────────────
    all_raids   = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).limit(20).all()
    all_raid_ids = [r.id for r in all_raids]
    all_raid_logs = (RaidWeekendLog.query
                     .filter(RaidWeekendLog.player_tag == player_tag,
                             RaidWeekendLog.raid_weekend_id.in_(all_raid_ids))
                     .all()) if all_raid_ids else []
    raid_logs_by_id = {}
    for l in all_raid_logs:
        raid_logs_by_id.setdefault(l.raid_weekend_id, []).append(l)

    # ── 5. Regular wars (max 30) ────────────────────────────────────────────
    all_wars    = ClanWar.query.order_by(ClanWar.start_time.desc()).limit(30).all()
    all_war_ids = [w.id for w in all_wars]

    all_war_members = (ClanWarMember.query
                       .filter(ClanWarMember.clan_war_id.in_(all_war_ids),
                               ClanWarMember.player_tag == player_tag,
                               ClanWarMember.is_opponent == False)
                       .all()) if all_war_ids else []
    all_participated = {m.clan_war_id for m in all_war_members}
    war_member_map   = {m.clan_war_id: m for m in all_war_members}

    all_war_attacks = (ClanWarAttack.query
                       .filter(ClanWarAttack.clan_war_id.in_(list(all_participated)))
                       .all()) if all_participated else []
    opp_war_members = (ClanWarMember.query
                       .filter(ClanWarMember.clan_war_id.in_(list(all_participated)),
                               ClanWarMember.is_opponent == True)
                       .all()) if all_participated else []
    opp_th_by_war = {}
    for m in opp_war_members:
        opp_th_by_war.setdefault(m.clan_war_id, {})[m.player_tag] = m.town_hall_level

    all_attacks_by_war    = {}
    player_attacks_by_war = {}
    for a in all_war_attacks:
        all_attacks_by_war.setdefault(a.clan_war_id, []).append(a)
        if a.attacker_tag == player_tag:
            player_attacks_by_war.setdefault(a.clan_war_id, []).append(a)

    # ── 6. CWL (max 6 seasons) ──────────────────────────────────────────────
    all_cwl_seasons    = CWLSeason.query.order_by(CWLSeason.id.desc()).limit(6).all()
    all_cwl_season_ids = [s.id for s in all_cwl_seasons]

    cwl_player_members = (CWLMember.query
                          .join(CWLWar, CWLMember.war_id == CWLWar.id)
                          .filter(CWLMember.player_tag == player_tag,
                                  CWLMember.clan_tag == CLAN_TAG,
                                  CWLWar.season_id.in_(all_cwl_season_ids))
                          .all()) if all_cwl_season_ids else []
    cwl_war_ids = [m.war_id for m in cwl_player_members]

    cwl_war_season_map = {w.id: w.season_id
                          for w in CWLWar.query.filter(CWLWar.id.in_(cwl_war_ids)).all()
                          } if cwl_war_ids else {}

    cwl_attacks = (CWLAttack.query
                   .filter(CWLAttack.war_id.in_(cwl_war_ids),
                           CWLAttack.attacker_tag == player_tag)
                   .all()) if cwl_war_ids else []
    cwl_atk_by_war = {}
    for a in cwl_attacks:
        cwl_atk_by_war.setdefault(a.war_id, []).append(a)

    cwl_member_by_key = {
        (m.war_id, m.player_tag): m
        for m in CWLMember.query.filter(CWLMember.war_id.in_(cwl_war_ids)).all()
    } if cwl_war_ids else {}

    # ── Per-period computation (no further DB queries) ──────────────────────
    activity_periods = {}
    skill_periods    = {}

    for period in ('week', 'month', '6months'):
        sl = _season_limit[period]
        rl = _raid_limit[period]
        bd = _battle_days[period]
        wl = _war_limit[period]
        cl = _cwl_limit[period]

        cutoff  = week_cutoff(now, bd)
        # Normalise to naive UTC so Python datetime comparisons work
        if getattr(cutoff, 'tzinfo', None) is not None:
            cutoff = cutoff.astimezone(dt.timezone.utc).replace(tzinfo=None)
        weeks_f = bd / 7

        # ── Ranked ──────────────────────────────────────────────────────────
        period_season_rows   = all_season_rows[:sl]
        eligible_season_rows = [(sid, start) for sid, start in period_season_rows
                                if join_date is None or start is None or start >= join_date]
        eligible_season_ids  = {sid for sid, _ in eligible_season_rows}
        total_eligible       = len(eligible_season_rows)

        period_weeks            = [w for w in all_player_weeks if w.league_season_id in eligible_season_ids]
        participated_season_ids = {w.league_season_id for w in period_weeks}
        player_total_max        = sum(w.max_attacks or 0 for w in period_weeks)

        for sid in (sid for sid in eligible_season_ids if sid not in participated_season_ids):
            player_total_max += round(all_avg_max.get(sid) or 8)

        total_done   = sum(sum(1 for l in w.battle_logs if _is_attack(l)) for w in period_weeks)
        ranked_score = min(100, round(100 * total_done / player_total_max)) if player_total_max else 0

        ranked_scores = []
        for rw in period_weeks:
            a_logs = [l for l in rw.battle_logs if _is_attack(l)]
            if not (rw.max_attacks or 0):
                continue
            sc, _, _ = _calc_ranked_score(a_logs, rw.townhall or 0, rw.max_attacks, rw.league_tier)
            ranked_scores.append(sc)
        avg_ranked   = sum(ranked_scores) / len(ranked_scores) if ranked_scores else 0
        ranked_skill = round(avg_ranked)

        # ── Battles ─────────────────────────────────────────────────────────
        p_in = [(t, g, e, d) for t, g, e, d in player_battles_raw if t and t >= cutoff]
        c_in = [(t, g, e, d) for t, g, e, d in clan_battles_raw   if t and t >= cutoff]

        battles_in_window = len(p_in)
        clan_weekly_avg   = len(c_in) / clan_member_count / weeks_f if clan_member_count else 0
        player_weekly_avg = battles_in_window / weeks_f
        battle_score      = min(100, round(100 * player_weekly_avg / clan_weekly_avg)) if clan_weekly_avg > 0 else 0

        player_loot   = sum(g + e + d for _, g, e, d in p_in)
        clan_loot_sum = sum(g + e + d for _, g, e, d in c_in)
        clan_avg_loot = clan_loot_sum / clan_member_count if clan_member_count else 0
        battle_skill  = min(100, round(100 * player_loot / clan_avg_loot)) if clan_avg_loot > 0 else 0

        # ── Raids ────────────────────────────────────────────────────────────
        period_raids   = all_raids[:rl]
        eligible_raids = [r for r in period_raids
                          if not join_date or (r.start_time and r.start_time.date() >= join_date)]
        eligible_raid_ids   = [r.id for r in eligible_raids]
        eligible_raid_count = len(eligible_raids)

        raid_attacks      = sum(len(raid_logs_by_id.get(rid, [])) for rid in eligible_raid_ids)
        raid_max_possible = eligible_raid_count * 6
        raid_score        = min(100, round(100 * raid_attacks / raid_max_possible)) if raid_max_possible else 0

        attended_raid_ids = [rid for rid in eligible_raid_ids if rid in raid_logs_by_id]
        raid_scores       = [_raid_verdict(raid_logs_by_id[rid])[2] for rid in attended_raid_ids]
        avg_raid          = sum(raid_scores) / len(raid_scores) if raid_scores else 0
        raid_skill        = round(avg_raid)

        # ── Regular wars ─────────────────────────────────────────────────────
        period_war_set       = {w.id for w in all_wars[:wl]}
        participated_war_ids = all_participated & period_war_set

        total_war_max    = len(participated_war_ids) * 2
        war_attacks_done = sum(len(player_attacks_by_war.get(wid, [])) for wid in participated_war_ids)
        war_score        = min(100, round(100 * war_attacks_done / total_war_max)) if total_war_max else 0

        war_skill_scores = []
        for war_id in participated_war_ids:
            p_atks = player_attacks_by_war.get(war_id, [])
            if not p_atks:
                war_skill_scores.append(0)
                continue
            m = war_member_map.get(war_id)
            score, _, _, _ = _war_player_verdict(
                player_tag, m.town_hall_level if m else 0, p_atks,
                all_attacks_by_war.get(war_id, []),
                opp_th_by_war.get(war_id, {}),
            )
            war_skill_scores.append(score)
        war_skill = round(sum(war_skill_scores) / len(war_skill_scores)) if war_skill_scores else 0

        # ── CWL ──────────────────────────────────────────────────────────────
        period_cwl_season_set = {s.id for s in all_cwl_seasons[:cl]}
        period_cwl_war_ids    = [wid for wid in cwl_war_ids
                                 if cwl_war_season_map.get(wid) in period_cwl_season_set]

        cwl_rounds_selected = len(period_cwl_war_ids)
        cwl_attacks_done    = sum(len(cwl_atk_by_war.get(wid, [])) for wid in period_cwl_war_ids)
        cwl_score           = min(100, round(100 * cwl_attacks_done / cwl_rounds_selected)) if cwl_rounds_selected else 0
        cwl_score_has_data  = cwl_rounds_selected > 0

        cwl_skill_scores = []
        for wid in period_cwl_war_ids:
            atks = cwl_atk_by_war.get(wid, [])
            if atks:
                sc, _, _ = cwl_attack_verdict(atks[0], cwl_member_by_key, cwl_matchup_rates)
                cwl_skill_scores.append(sc)
            else:
                cwl_skill_scores.append(0)
        cwl_skill          = round(sum(cwl_skill_scores) / len(cwl_skill_scores)) if cwl_skill_scores else 0
        cwl_skill_has_data = bool(period_cwl_war_ids)
        avg_cwl            = sum(cwl_skill_scores) / len(cwl_skill_scores) if cwl_skill_scores else 0

        # ── Activity dict ────────────────────────────────────────────────────
        act_comps = [ranked_score, battle_score, raid_score]
        if participated_war_ids: act_comps.append(war_score)
        if cwl_score_has_data:   act_comps.append(cwl_score)
        act_total = round(sum(act_comps) / len(act_comps))

        if   act_total >= 80: act_label, act_color = 'Active',   'green'
        elif act_total >= 50: act_label, act_color = 'Regular',  'blue'
        elif act_total >= 20: act_label, act_color = 'Casual',   'yellow'
        else:                 act_label, act_color = 'Inactive', 'red'

        activity_periods[period] = {
            'score': act_total, 'label': act_label, 'label_color': act_color,
            'ranked_score': ranked_score, 'ranked_max': 100,
            'ranked_detail': f'{total_done}/{player_total_max} attacks · {len(period_weeks)}/{total_eligible} seasons played',
            'battle_score': battle_score, 'battle_max': 100,
            'battle_detail': f'{battles_in_window} attacks · {player_weekly_avg:.1f}/week · Clan avg: {clan_weekly_avg:.1f}/week',
            'raid_score': raid_score, 'raid_max': 100,
            'raid_detail': f'{raid_attacks}/{raid_max_possible} attacks across last {eligible_raid_count} raid weekends',
            'war_score': war_score, 'war_max': 100,
            'war_score_has_data': bool(participated_war_ids),
            'war_detail': f'{war_attacks_done}/{total_war_max} attacks across {len(participated_war_ids)} wars',
            'cwl_score': cwl_score, 'cwl_max': 100,
            'cwl_score_has_data': cwl_score_has_data,
            'cwl_detail': f'{cwl_attacks_done}/{cwl_rounds_selected} attacks across last {len(period_cwl_season_set)} CWL seasons',
            'has_data': total_eligible > 0 or battles_in_window > 0 or eligible_raid_count > 0,
        }

        # ── Skill dict ───────────────────────────────────────────────────────
        sk_comps = []
        if ranked_scores:       sk_comps.append(ranked_skill)
        if attended_raid_ids:   sk_comps.append(raid_skill)
        if player_loot > 0:     sk_comps.append(battle_skill)
        if war_skill_scores:    sk_comps.append(war_skill)
        if cwl_skill_has_data:  sk_comps.append(cwl_skill)
        sk_total = round(sum(sk_comps) / len(sk_comps)) if sk_comps else 0

        if   sk_total >= 80: sk_label, sk_color = 'Elite',   'purple'
        elif sk_total >= 60: sk_label, sk_color = 'Strong',  'green'
        elif sk_total >= 40: sk_label, sk_color = 'Average', 'blue'
        elif sk_total >= 20: sk_label, sk_color = 'Weak',    'yellow'
        else:                sk_label, sk_color = 'Novice',  'muted'

        skill_periods[period] = {
            'score': sk_total, 'label': sk_label, 'label_color': sk_color,
            'ranked_skill': ranked_skill, 'ranked_max': 100,
            'ranked_skill_has_data': bool(ranked_scores),
            'ranked_detail': f'Avg verdict {avg_ranked:.0f}/100 · {len(period_weeks)} seasons played',
            'raid_skill': raid_skill, 'raid_max': 100,
            'raid_skill_has_data': bool(attended_raid_ids),
            'raid_detail': f'Avg verdict {avg_raid:.0f}/100 · {len(attended_raid_ids)} raids attended',
            'battle_skill': battle_skill, 'battle_max': 100,
            'battle_skill_has_data': player_loot > 0,
            'battle_detail': f'{_fmt_loot(player_loot)} loot · Clan avg: {_fmt_loot(clan_avg_loot)}',
            'war_skill': war_skill, 'war_max': 100,
            'war_skill_has_data': bool(war_skill_scores),
            'war_detail': f'Avg verdict {war_skill:.0f}/100 · {len(participated_war_ids)} wars selected',
            'cwl_skill': cwl_skill, 'cwl_max': 100,
            'cwl_skill_has_data': cwl_skill_has_data,
            'cwl_detail': f'Avg verdict {avg_cwl:.0f}/100 · {len(period_cwl_war_ids)} CWL rounds selected',
            'has_data': bool(sk_comps),
        }

    return activity_periods, skill_periods


@player_bp.route('/player/<tag>')
def player_profile(tag):
    from app import CLAN_TAG
    actual_tag = '#' + tag
    player = db_player_get(actual_tag)
    if not player:
        return render_template('player/player_profile.html', player=None, player_tag=actual_tag), 404

    cwl_matchup_rates, _, _ = _build_cwl_matchup_rates()
    _all_act, _all_sk = calculate_scores_all_periods(actual_tag, cwl_matchup_rates)
    activity_periods = {p: d for p, d in _all_act.items() if d['has_data']}
    skill_periods    = {p: d for p, d in _all_sk.items()  if d['has_data']}
    activity = _all_act.get('week', next(iter(_all_act.values()), {}))

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

    all_raids = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).all()
    if player.join_date:
        all_raids = [r for r in all_raids if r.start_time and r.start_time.date() >= player.join_date]
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

    # CWL History
    player_cwl_members = (CWLMember.query
                          .filter(CWLMember.player_tag == actual_tag,
                                  CWLMember.clan_tag == CLAN_TAG)
                          .all())
    cwl_war_ids = [m.war_id for m in player_cwl_members]
    cwl_history = []
    if cwl_war_ids:
        cwl_wars_map = {w.id: w for w in CWLWar.query.filter(CWLWar.id.in_(cwl_war_ids)).all()}
        cwl_attacks_by_war = {}
        for a in CWLAttack.query.filter(CWLAttack.attacker_tag == actual_tag,
                                        CWLAttack.war_id.in_(cwl_war_ids)).all():
            cwl_attacks_by_war.setdefault(a.war_id, []).append(a)

        _cwl_mbr = {
            (m.war_id, m.player_tag): m
            for m in CWLMember.query.filter(CWLMember.war_id.in_(cwl_war_ids)).all()
        }

        members_by_season = {}
        for m in player_cwl_members:
            war = cwl_wars_map.get(m.war_id)
            if war:
                members_by_season.setdefault(war.season_id, []).append((war, m))

        season_info = {s.id: s for s in CWLSeason.query.filter(
            CWLSeason.id.in_(members_by_season.keys())).all()}

        for season_id in sorted(members_by_season.keys(), reverse=True):
            s = season_info.get(season_id)
            if player.join_date and s:
                try:
                    szn_date = dt.date(int(s.season[:4]), int(s.season[5:7]), 1)
                    if szn_date < player.join_date.replace(day=1):
                        continue
                except Exception:
                    pass

            wars_and_members = members_by_season[season_id]
            att_used = 0
            scores = []
            total_stars = 0
            for war, member in wars_and_members:
                attacks = cwl_attacks_by_war.get(war.id, [])
                if attacks:
                    att_used += len(attacks)
                    for a in attacks:
                        sc, _, _ = cwl_attack_verdict(a, _cwl_mbr, cwl_matchup_rates)
                        scores.append(sc)
                        total_stars += (a.stars or 0)
                else:
                    scores.append(0)

            avg_score = round(sum(scores) / len(scores)) if scores else 0
            avg_stars = round(total_stars / att_used, 2) if att_used else 0

            if   avg_score >= 88: badge_c, judge_l = 'badge-godlike',  'Godlike'
            elif avg_score >= 70: badge_c, judge_l = 'badge-dominant', 'Dominant'
            elif avg_score >= 60: badge_c, judge_l = 'badge-wow',      'Very Good'
            elif avg_score >= 50: badge_c, judge_l = 'badge-good',     'Good'
            elif avg_score >= 32: badge_c, judge_l = 'badge-warning',  'Okay'
            elif avg_score >= 18: badge_c, judge_l = 'badge-suck',     'Poor'
            elif att_used > 0:    badge_c, judge_l = 'badge-useless',  'Disaster'
            else:                  badge_c, judge_l = 'badge-useless',  'Skipped'

            cwl_history.append({
                'season_id':        season_id,
                'season':           s.season if s else f'Season {season_id}',
                'rounds_selected':  len(wars_and_members),
                'att_used':         att_used,
                'att_possible':     len(wars_and_members),
                'avg_stars':        avg_stars,
                'participated':     att_used > 0,
                'score_100':        avg_score,
                'badge_class':      badge_c,
                'judge_label':      judge_l,
            })

    return render_template('player/player_profile.html',
                           player=player,
                           activity=activity,
                           activity_periods=activity_periods,
                           skill_periods=skill_periods,
                           ranked_history=ranked_history,
                           battle_history=battle_history,
                           raid_history=raid_history,
                           war_history=war_history,
                           cwl_history=cwl_history)


def _calculate_scores_bulk(player_tags, period='month'):
    from app import CLAN_TAG
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

    # ── CWL data (bulk) ──────────────────────────────────────────────────────
    cwl_limit = {'week': 1, 'month': 2, '6months': 6}.get(period, 2)
    cwl_season_ids_bulk = [s.id for s in CWLSeason.query.order_by(CWLSeason.id.desc()).limit(cwl_limit).all()]
    if cwl_season_ids_bulk:
        # Anchor on member records to avoid wars between other CWL clans in the group
        all_cwl_members_bulk = (CWLMember.query
                                .join(CWLWar, CWLMember.war_id == CWLWar.id)
                                .filter(CWLMember.player_tag.in_(player_tags),
                                        CWLMember.clan_tag == CLAN_TAG,
                                        CWLWar.season_id.in_(cwl_season_ids_bulk))
                                .all())
        cwl_war_ids_bulk = list({m.war_id for m in all_cwl_members_bulk})
        all_cwl_attacks_bulk = (CWLAttack.query
                                .filter(CWLAttack.war_id.in_(cwl_war_ids_bulk),
                                        CWLAttack.attacker_tag.in_(player_tags))
                                .all()) if cwl_war_ids_bulk else []
    else:
        cwl_war_ids_bulk = []
        all_cwl_members_bulk = []
        all_cwl_attacks_bulk = []

    # per-player: war_id → member; attacker_tag → {war_id → [attacks]}
    cwl_members_by_player = {}   # tag → [war_id, ...]
    for m in all_cwl_members_bulk:
        cwl_members_by_player.setdefault(m.player_tag, []).append(m.war_id)
    cwl_attacks_by_player_bulk = {}  # tag → {war_id → [CWLAttack]}
    for a in all_cwl_attacks_bulk:
        cwl_attacks_by_player_bulk.setdefault(a.attacker_tag, {}).setdefault(a.war_id, []).append(a)

    cwl_matchup_rates_bulk, _, _ = _build_cwl_matchup_rates()
    cwl_member_by_key_bulk = {
        (m.war_id, m.player_tag): m
        for m in CWLMember.query.filter(CWLMember.war_id.in_(cwl_war_ids_bulk)).all()
    } if cwl_war_ids_bulk else {}

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

        # --- cwl activity ---
        cwl_wars_for_player  = cwl_members_by_player.get(tag, [])
        cwl_rounds_selected  = len(cwl_wars_for_player)
        cwl_attacks_used     = sum(len(v) for v in cwl_attacks_by_player_bulk.get(tag, {}).values())
        cwl_score            = min(100, round(100 * cwl_attacks_used / cwl_rounds_selected)) if cwl_rounds_selected else 0
        cwl_score_has_data   = cwl_rounds_selected > 0

        act_components = [ranked_score, battle_score, raid_score]
        if player_participated_wars:
            act_components.append(war_score)
        if cwl_score_has_data:
            act_components.append(cwl_score)
        act_total = round(sum(act_components) / len(act_components))
        if act_total >= 80:   act_label, act_color = 'Active',   'green'
        elif act_total >= 50: act_label, act_color = 'Regular',  'blue'
        elif act_total >= 20: act_label, act_color = 'Casual',   'yellow'
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
        tag_war_attacks = war_attacks_by_player.get(tag, {})
        for war_id in player_participated_wars:
            p_attacks = tag_war_attacks.get(war_id, [])
            if not p_attacks:
                war_skill_scores.append(0)
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

        # --- cwl skill ---
        cwl_skill_scores = []
        tag_cwl_attacks  = cwl_attacks_by_player_bulk.get(tag, {})
        for wid in cwl_wars_for_player:
            atks = tag_cwl_attacks.get(wid, [])
            if atks:
                sc, _, _ = cwl_attack_verdict(atks[0], cwl_member_by_key_bulk, cwl_matchup_rates_bulk)
                cwl_skill_scores.append(sc)
            else:
                cwl_skill_scores.append(0)
        cwl_skill          = round(sum(cwl_skill_scores) / len(cwl_skill_scores)) if cwl_skill_scores else 0
        cwl_skill_has_data = bool(cwl_wars_for_player)

        sk_components = []
        if ranked_skill_scores:  sk_components.append(ranked_skill)
        if attended_rids:        sk_components.append(raid_skill)
        if player_loot > 0:      sk_components.append(battle_skill)
        if war_skill_scores:     sk_components.append(war_skill)
        if cwl_skill_has_data:   sk_components.append(cwl_skill)
        sk_total = round(sum(sk_components) / len(sk_components)) if sk_components else 0
        if sk_total >= 80:   sk_label, sk_color = 'Elite',   'purple'
        elif sk_total >= 60: sk_label, sk_color = 'Strong',  'green'
        elif sk_total >= 40: sk_label, sk_color = 'Average', 'blue'
        elif sk_total >= 20: sk_label, sk_color = 'Weak',    'yellow'
        else:                sk_label, sk_color = 'Novice',  'muted'

        results[tag] = {
            'activity': {
                'score': act_total, 'label': act_label, 'label_color': act_color,
                'ranked_score': ranked_score, 'battle_score': battle_score,
                'raid_score': raid_score, 'war_score': war_score,
                'war_score_has_data': bool(player_participated_wars),
                'cwl_score': cwl_score, 'cwl_score_has_data': cwl_score_has_data,
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
                'cwl_skill': cwl_skill, 'cwl_skill_has_data': cwl_skill_has_data,
                'has_data': bool(sk_components),
            },
        }

    return results


@player_bp.route('/clan')
def clan_overview():
    period = request.args.get('period', 'month')
    if period not in ('week', 'month', '6months'):
        period = 'month'

    players    = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
    scores     = _calculate_scores_bulk([p.tag for p in players], period)
    show_wpref = _is_super_admin()

    player_cards = []
    for player in players:
        s        = scores.get(player.tag, {})
        activity = s.get('activity', {'score': 0, 'label': 'Inactive', 'label_color': 'red',
                                      'ranked_score': 0, 'battle_score': 0, 'raid_score': 0, 'has_data': False})
        skill    = s.get('skill',    {'score': 0, 'label': 'Novice',   'label_color': 'muted',
                                      'ranked_skill': 0, 'battle_skill': 0, 'raid_skill': 0, 'has_data': False})
        card = {
            'name':        player.name or player.tag,
            'tag':         player.tag,
            'tag_url':     player.tag.replace('#', ''),
            'th':          player.current_th,
            'league_icon': player.league_icon,
            'activity':    activity,
            'skill':       skill,
            'combined':    activity['score'] + skill['score'],
        }
        if show_wpref:
            war_pref = player.war_preference_custom or player.war_preference_in_game or None
            if war_pref:
                card['war_pref'] = war_pref
        player_cards.append(card)
    player_cards.sort(key=lambda x: (-x['combined'], x['name']))

    return render_template('player/clan_overview.html', player_cards=player_cards, period=period)
