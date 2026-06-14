import json

from flask import Blueprint, render_template, redirect, url_for, request, jsonify

from extensions import db
from features.auth.routes import _current_user, _any_access
from models import EquipmentGoal
from services.api import api_fetch_player_data

tools_bp = Blueprint('tools', __name__)


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
    if not player:
        return render_template('tools/equipment.html', player=None, equipment=None, error=None,
                               saved_goals_json='{}', saved_ores_json='{"shiny":0,"glowy":0,"starry":0}')

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
                               saved_goals_json='{}', saved_ores_json='{"shiny":0,"glowy":0,"starry":0}')

    goals = {g.equipment_name: {'target': g.target_level, 'priority': g.priority}
             for g in EquipmentGoal.query.filter_by(user_id=user.id).all()}
    ores = {'shiny': user.ore_shiny or 0, 'glowy': user.ore_glowy or 0, 'starry': user.ore_starry or 0}

    return render_template(
        'tools/equipment.html',
        player=player,
        equipment=equipment,
        error=None,
        saved_goals_json=json.dumps(goals),
        saved_ores_json=json.dumps(ores),
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
