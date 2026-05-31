import datetime as dt

from flask import Blueprint, render_template, request
from sqlalchemy.orm import selectinload

from models import ClanWar
from services.helpers import avg_league_name

war_bp = Blueprint('war', __name__)


@war_bp.route('/war')
def clan_war_page():
    wars = ClanWar.query.order_by(ClanWar.start_time.desc()).all()
    selected_id = request.args.get('war_id', type=int)
    if not selected_id and wars:
        selected_id = wars[0].id

    selected_war = (
        ClanWar.query
        .options(selectinload(ClanWar.members), selectinload(ClanWar.attacks))
        .filter_by(id=selected_id)
        .first()
    ) if selected_id else None

    members_our, members_opp = [], []
    attacks_by_attacker, attacks_on_defender, member_by_tag = {}, {}, {}
    avg_th_our = avg_th_opp = 0
    avg_league_our = avg_league_opp = None

    if selected_war:
        members_our = sorted([m for m in selected_war.members if not m.is_opponent], key=lambda m: m.map_position or 999)
        members_opp = sorted([m for m in selected_war.members if m.is_opponent],     key=lambda m: m.map_position or 999)
        member_by_tag = {m.player_tag: m for m in selected_war.members}

        avg_th_our = round(sum(m.town_hall_level or 0 for m in members_our) / len(members_our), 1) if members_our else 0
        avg_th_opp = round(sum(m.town_hall_level or 0 for m in members_opp) / len(members_opp), 1) if members_opp else 0
        avg_league_our = avg_league_name(members_our)
        avg_league_opp = avg_league_name(members_opp)

        for a in selected_war.attacks:
            attacks_by_attacker.setdefault(a.attacker_tag, []).append(a)
            attacks_on_defender.setdefault(a.defender_tag, []).append(a)
        for lst in attacks_by_attacker.values():
            lst.sort(key=lambda a: a.attack_order or 0)
        for lst in attacks_on_defender.values():
            lst.sort(key=lambda a: a.attack_order or 0)

    war_options = []
    for w in wars:
        if w.state == 'preparation':
            label = f"Preparation — vs {w.opponent_name or '?'}"
        elif w.state == 'inWar':
            label = f"Ongoing — vs {w.opponent_name or '?'}"
        else:
            start = w.start_time.strftime('%d.%m.%Y') if w.start_time else '?'
            label = f"{start} — vs {w.opponent_name or '?'}"
        war_options.append({'id': w.id, 'label': label})

    return render_template(
        'war/clanwar.html',
        war=selected_war,
        war_options=war_options,
        selected_id=selected_id,
        members_our=members_our,
        members_opp=members_opp,
        attacks_by_attacker=attacks_by_attacker,
        attacks_on_defender=attacks_on_defender,
        member_by_tag=member_by_tag,
        avg_th_our=avg_th_our,
        avg_th_opp=avg_th_opp,
        avg_league_our=avg_league_our,
        avg_league_opp=avg_league_opp,
        now=dt.datetime.now(dt.timezone.utc),
    )
