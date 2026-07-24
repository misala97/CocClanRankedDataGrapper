import json
from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, request, jsonify

from extensions import db
from features.auth.routes import _current_user, _any_access
from models import EquipmentGoal, ClanWar, CWLSeason, CWLWar
from services.api import api_fetch_player_data

tools_bp = Blueprint('tools', __name__)

# Canonical hero-equipment names — mirrors the EQUIP_HERO / EQUIP_IMAGES maps in
# templates/tools/equipment.html (the only other place this full name list is kept).
# equipment_save() uses this to reject any equipment_name the client sends that
# isn't a real piece of equipment, since EquipmentGoal.equipment_name is otherwise
# stored (and later rendered) verbatim from client-supplied JSON keys.
_VALID_EQUIPMENT_NAMES = frozenset({
    'Barbarian Puppet', 'Earthquake Boots', 'Rage Vial', 'Snake Bracelet', 'Vampstache',
    'Giant Gauntlet', 'Spiky Ball',
    'Archer Puppet', 'Frozen Arrow', 'Giant Arrow', 'Healer Puppet', 'Invisibility Vial',
    'Magic Mirror', 'Monolith Arrow', 'WWE Action Figure', 'Action Figure',
    'Eternal Tome', 'Fireball', 'Healing Tome', 'Life Gem', 'Rage Gem', 'Lavaloon Puppet',
    'Electro Boots', 'Haste Vial', 'Hog Rider Puppet', 'Royal Gem', 'Seeking Shield',
    'Frost Flake', 'Rocket Spear',
    'Dark Crown', 'Dark Orb', 'Henchmen Puppet', 'Power Pump', 'Noble Iron', 'Meteor Staff',
    'Iron Pants', 'Metal Pants',
    'Electro Fangs', 'Fire Heart', 'Flame Blower', 'Rocket Backpack', 'Stun Blast',
})

_WAR_ORE = {
    8:  (380, 15, 0), 9:  (410, 18, 0), 10: (460, 21, 3), 11: (560, 24, 3),
    12: (610, 27, 4), 13: (710, 30, 4), 14: (810, 33, 5), 15: (960, 36, 5),
    16: (1110, 39, 6), 17: (1110, 39, 6), 18: (1110, 39, 6),
}

def _compute_war_stats(player_tag: str, cutoff=None) -> dict:
    if cutoff is None:
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


def _ore_mult(clan_stars, opp_stars, clan_pct, opp_pct) -> float:
    cs, os_, cd, od = clan_stars or 0, opp_stars or 0, clan_pct or 0, opp_pct or 0
    if cs > os_: return 1.0
    if cs < os_: return 0.5
    if cd > od:  return 1.0
    if cd < od:  return 0.5
    return 4 / 7


def _tally_ore_from_wars(wars, player_tag: str):
    """(shiny, glowy, starry, attacks, wars_participated) this player earned across `wars`,
    using the same per-attack ore model as the source stats (defender TH → _WAR_ORE × result mult)."""
    shiny = glowy = starry = attacks = participated_wars = 0
    for war in wars:
        mult = _ore_mult(war.clan_stars, getattr(war, 'opponent_stars', None) or getattr(war, 'opp_stars', None),
                         war.clan_destruction_pct,
                         getattr(war, 'opponent_destruction_pct', None) or getattr(war, 'opp_destruction_pct', None))
        defender_th = {m.player_tag: m.town_hall_level for m in war.members if m.is_opponent}
        took = False
        for attack in war.attacks:
            if attack.attacker_tag != player_tag:
                continue
            th  = max(8, min(18, defender_th.get(attack.defender_tag, 14) or 14))
            ore = _WAR_ORE.get(th, (0, 0, 0))
            shiny  += round(ore[0] * mult)
            glowy  += round(ore[1] * mult)
            starry += round(ore[2] * mult)
            attacks += 1
            took = True
        if took:
            participated_wars += 1
    return shiny, glowy, starry, attacks, participated_wars


def _compute_ore_since(player_tag: str, since_dt) -> dict:
    """Ore this player earned from regular-war + CWL attacks that ended at/after `since_dt`.
    Powers the Armory since-last-visit pulse."""
    reg_wars = ClanWar.query.filter(ClanWar.end_time >= since_dt).all()
    cwl_wars = CWLWar.query.filter(CWLWar.end_time >= since_dt).all()
    ws, wg, wst, wa, wc = _tally_ore_from_wars(reg_wars, player_tag)
    cs, cg, cst, ca, cr = _tally_ore_from_wars(cwl_wars, player_tag)
    return {
        'shiny': ws + cs, 'glowy': wg + cg, 'starry': wst + cst,
        'war_attacks': wa, 'war_count': wc,
        'cwl_attacks': ca, 'cwl_rounds': cr,
    }


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
                               saved_goals={}, saved_ores={'shiny': 0, 'glowy': 0, 'starry': 0},
                               war_stats_json=_empty, cwl_stats_json=_empty, gain_settings=None)

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
                               saved_goals={}, saved_ores={'shiny': 0, 'glowy': 0, 'starry': 0},
                               war_stats_json=_empty, cwl_stats_json=_empty, gain_settings=None)

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

    # ── Since-last-visit pulse ────────────────────────────────────────────────
    # Ore earned from this player's own war + CWL attacks since they last opened the
    # Armory. The stamp only advances on a "fresh" visit (≥8h elapsed or a new calendar
    # day) so refreshing within a session keeps showing the same pulse instead of zero.
    now       = datetime.utcnow()
    prev_seen = user.equip_last_seen_at
    pulse     = None
    if prev_seen is not None:
        try:
            pulse = _compute_ore_since(player.tag, prev_seen)
        except Exception:
            pulse = None
    if prev_seen is None or (now - prev_seen) >= timedelta(hours=8) or now.date() != prev_seen.date():
        user.equip_last_seen_at = now
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    try:
        gain_settings = json.loads(user.gain_settings) if user.gain_settings else None
    except (TypeError, ValueError):
        gain_settings = None

    return render_template(
        'tools/equipment.html',
        player=player,
        equipment=equipment,
        error=None,
        saved_goals=goals,
        saved_ores=ores,
        war_stats_json=json.dumps(war_stats),
        cwl_stats_json=json.dumps(cwl_stats),
        gain_settings=gain_settings,
        equip_pulse_json=json.dumps(pulse) if pulse else 'null',
        equip_pulse_since=json.dumps(prev_seen.isoformat()) if prev_seen else 'null',
    )


@tools_bp.route('/tools/equipment/save', methods=['POST'])
def equipment_save():
    user = _current_user()
    if not user or not _any_access():
        return jsonify({'error': 'not logged in'}), 401

    data = request.get_json(silent=True) or {}

    user.ore_shiny  = max(0, int(data.get('shiny',  0) or 0))
    user.ore_glowy  = max(0, int(data.get('glowy',  0) or 0))
    user.ore_starry = max(0, int(data.get('starry', 0) or 0))

    gain_settings = data.get('gainSettings')
    if gain_settings is not None:
        user.gain_settings = json.dumps(gain_settings)

    incoming = data.get('goals', {})  # {name: {target, priority} | null}
    if not isinstance(incoming, dict):
        incoming = {}

    existing = {g.equipment_name: g for g in EquipmentGoal.query.filter_by(user_id=user.id).all()}

    for name, goal in incoming.items():
        if name not in _VALID_EQUIPMENT_NAMES:
            continue
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
