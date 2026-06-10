from flask import Blueprint, render_template, redirect, url_for

from features.auth.routes import _current_user, _any_access
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
        return render_template('tools/equipment.html', player=None, equipment=None, error=None)

    try:
        data = api_fetch_player_data(player.tag)

        # Build a map of equipped items: name -> hero name
        equipped_on = {}
        for hero in data.get('heroes', []):
            for e in hero.get('equipment', []):
                equipped_on[e.get('name')] = hero.get('name', '?')

        # Merge all owned equipment — top-level has everything, heroes[] has equipped subset
        seen = set()
        equipment = []
        for e in data.get('heroEquipment', []):
            name = e.get('name')
            if name not in seen:
                seen.add(name)
                entry = dict(e)
                entry['equipped_on'] = equipped_on.get(name)
                equipment.append(entry)

        # Fall back to heroes[] if top-level was empty (API quirk)
        if not equipment:
            for hero in data.get('heroes', []):
                for e in hero.get('equipment', []):
                    name = e.get('name')
                    if name not in seen:
                        seen.add(name)
                        entry = dict(e)
                        entry['equipped_on'] = hero.get('name', '?')
                        equipment.append(entry)

        _hero_order = [
            'Barbarian King', 'Archer Queen', 'Grand Warden',
            'Royal Champion', 'Minion Prince',
        ]
        def _sort_key(e):
            hero = e.get('equipped_on') or ''
            hero_rank = _hero_order.index(hero) if hero in _hero_order else len(_hero_order)
            return (e.get('village', ''), hero_rank, hero, -(e.get('level') or 0))

        equipment.sort(key=_sort_key)
    except RuntimeError as e:
        return render_template('tools/equipment.html', player=player, equipment=None, error=str(e))

    return render_template('tools/equipment.html', player=player, equipment=equipment, error=None)
