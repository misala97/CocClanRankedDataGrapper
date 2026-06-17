import json
from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, request, jsonify

from extensions import db
from features.auth.routes import _current_user, _any_access
from models import EquipmentGoal, ClanWar, CWLSeason, CWLWar
from services.api import api_fetch_player_data

tools_bp = Blueprint('tools', __name__)

_WAR_ORE = {
    8:  (380, 15, 0), 9:  (410, 18, 0), 10: (460, 21, 3), 11: (560, 24, 3),
    12: (610, 27, 4), 13: (710, 30, 4), 14: (810, 33, 5), 15: (960, 36, 5),
    16: (1110, 39, 6), 17: (1110, 39, 6), 18: (1110, 39, 6),
}

def _compute_war_stats(player_tag: str) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=30)
    wars   = ClanWar.query.filter(ClanWar.end_time >= cutoff).all()
    total_shiny = total_glowy = total_starry = total_attacks = total_wars = 0
    for war in wars:
        if war.clan_stars > war.opponent_stars:
            mult = 1.0
        elif war.clan_stars < war.opponent_stars:
            mult = 0.5
        elif (war.clan_destruction_pct or 0) > (war.opponent_destruction_pct or 0):
            mult = 1.0
        elif (war.clan_destruction_pct or 0) < (war.opponent_destruction_pct or 0):
            mult = 0.5
        else:
            mult = 4 / 7
        defender_th = {m.player_tag: m.town_hall_level for m in war.members if m.is_opponent}
        participated = False
        for attack in war.attacks:
            if attack.attacker_tag != player_tag:
                continue
            th = max(8, min(18, defender_th.get(attack.defender_tag, 14) or 14))
            ore = _WAR_ORE.get(th, (0, 0, 0))
            total_shiny  += round(ore[0] * mult)
            total_glowy  += round(ore[1] * mult)
            total_starry += round(ore[2] * mult)
            total_attacks += 1
            participated  = True
        if participated:
            total_wars += 1
    return {'shiny': total_shiny, 'glowy': total_glowy, 'starry': total_starry,
            'attacks': total_attacks, 'wars': total_wars}


def _compute_cwl_stats(player_tag: str) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=31)

    # Find the most recent ended CWL season that has wars within the last 31 days
    season = (
        CWLSeason.query
        .join(CWLWar, CWLWar.season_id == CWLSeason.id)
        .filter(CWLSeason.state == 'ended', CWLWar.end_time >= cutoff)
        .order_by(CWLWar.end_time.desc())
        .first()
    )
    if not season:
        return {'shiny': 0, 'glowy': 0, 'starry': 0, 'attacks': 0, 'wars': 0}

    total_shiny = total_glowy = total_starry = total_attacks = total_wars = 0

    for war in season.wars:
        if (war.clan_stars or 0) > (war.opp_stars or 0):
            mult = 1.0
        elif (war.clan_stars or 0) < (war.opp_stars or 0):
            mult = 0.5
        elif (war.clan_destruction_pct or 0) > (war.opp_destruction_pct or 0):
            mult = 1.0
        elif (war.clan_destruction_pct or 0) < (war.opp_destruction_pct or 0):
            mult = 0.5
        else:
            mult = 4 / 7

        defender_th = {m.player_tag: m.town_hall_level for m in war.members if m.is_opponent}

        participated = False
        for attack in war.attacks:
            if attack.attacker_tag != player_tag:
                continue
            th  = max(8, min(18, defender_th.get(attack.defender_tag, 14) or 14))
            ore = _WAR_ORE.get(th, (0, 0, 0))
            total_shiny  += round(ore[0] * mult)
            total_glowy  += round(ore[1] * mult)
            total_starry += round(ore[2] * mult)
            total_attacks += 1
            participated  = True

        if participated:
            total_wars += 1

    return {'shiny': total_shiny, 'glowy': total_glowy, 'starry': total_starry,
            'attacks': total_attacks, 'wars': total_wars}


def _require_login():
    if not _any_access():
        return redirect(url_for('auth.login'))
    return None


@tools_bp.route('/tools/equipment')
def equipment_calculator():
    guard = _require_login()
    if guard:
        return guard

    user = _current_user()
    if not user:
        return redirect(url_for('auth.login'))

    player = user.linked_player
    _empty = '{"shiny":0,"glowy":0,"starry":0,"attacks":0,"wars":0}'
    if not player:
        return render_template('tools/equipment.html', player=None, equipment=None, error=None,
                               saved_goals_json='{}', saved_ores_json='{"shiny":0,"glowy":0,"starry":0}',
                               war_stats_json=_empty, cwl_stats_json=_empty, gain_settings_json='null')

    try:
        data = api_fetch_player_data(player.tag)

        equipped_on = {}
        for hero in data.get('heroes', []):
            for e in hero.get('equipment', []):
                equipped_on[e.get('name')] = hero.get('name', '?')

        seen = set()
        equipment = []
        for e in data.get('heroEquipment', []):
            name = e.get('name')
            if name not in seen:
                seen.add(name)
                entry = dict(e)
                entry['equipped_on'] = equipped_on.get(name)
                equipment.append(entry)

        if not equipment:
            for hero in data.get('heroes', []):
                for e in hero.get('equipment', []):
                    name = e.get('name')
                    if name not in seen:
                        seen.add(name)
                        entry = dict(e)
                        entry['equipped_on'] = hero.get('name', '?')
                        equipment.append(entry)

        _hero_order = ['Barbarian King', 'Archer Queen', 'Grand Warden', 'Royal Champion', 'Minion Prince']
        def _sort_key(e):
            hero = e.get('equipped_on') or ''
            hero_rank = _hero_order.index(hero) if hero in _hero_order else len(_hero_order)
            return (e.get('village', ''), hero_rank, hero, -(e.get('level') or 0))
        equipment.sort(key=_sort_key)

    except RuntimeError as e:
        return render_template('tools/equipment.html', player=player, equipment=None, error=str(e),
                               saved_goals_json='{}', saved_ores_json='{"shiny":0,"glowy":0,"starry":0}',
                               war_stats_json=_empty, cwl_stats_json=_empty, gain_settings_json='null')

    goals = {g.equipment_name: {'target': g.target_level, 'priority': g.priority}
             for g in EquipmentGoal.query.filter_by(user_id=user.id).all()}
    ores = {'shiny': user.ore_shiny or 0, 'glowy': user.ore_glowy or 0, 'starry': user.ore_starry or 0}

    _zero = {'shiny': 0, 'glowy': 0, 'starry': 0, 'attacks': 0, 'wars': 0}
    try:
        war_stats = _compute_war_stats(player.tag)
    except Exception:
        war_stats = _zero.copy()

    try:
        cwl_stats = _compute_cwl_stats(player.tag)
    except Exception:
        cwl_stats = _zero.copy()

    return render_template(
        'tools/equipment.html',
        player=player,
        equipment=equipment,
        error=None,
        saved_goals_json=json.dumps(goals),
        saved_ores_json=json.dumps(ores),
        war_stats_json=json.dumps(war_stats),
        cwl_stats_json=json.dumps(cwl_stats),
        gain_settings_json=user.gain_settings or 'null',
    )


@tools_bp.route('/tools/equipment/save', methods=['POST'])
def equipment_save():
    user = _current_user()
    if not user:
        return jsonify({'error': 'not logged in'}), 401

    data = request.get_json(silent=True) or {}

    user.ore_shiny  = max(0, int(data.get('shiny',  0) or 0))
    user.ore_glowy  = max(0, int(data.get('glowy',  0) or 0))
    user.ore_starry = max(0, int(data.get('starry', 0) or 0))

    gain_settings = data.get('gainSettings')
    if gain_settings is not None:
        user.gain_settings = json.dumps(gain_settings)

    incoming = data.get('goals', {})  # {name: {target, priority} | null}

    existing = {g.equipment_name: g for g in EquipmentGoal.query.filter_by(user_id=user.id).all()}

    for name, goal in incoming.items():
        if goal is None:
            if name in existing:
                db.session.delete(existing[name])
        else:
            target   = goal.get('target')
            priority = goal.get('priority')
            if target is None:
                if name in existing:
                    db.session.delete(existing[name])
            elif name in existing:
                existing[name].target_level = target
                existing[name].priority     = priority
            else:
                db.session.add(EquipmentGoal(
                    user_id=user.id,
                    equipment_name=name,
                    target_level=target,
                    priority=priority,
                ))

    db.session.commit()
    return jsonify({'ok': True})
