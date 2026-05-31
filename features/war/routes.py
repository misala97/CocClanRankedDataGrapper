import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import selectinload

from extensions import db
from models import ClanWar, ClanWarMember
from features.auth.routes import _can_edit_clan_war
from services.helpers import avg_league_name, league_rank

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
    members_our_json = members_opp_json = []
    all_attacks_json = []

    if selected_war:
        members_our = sorted([m for m in selected_war.members if not m.is_opponent], key=lambda m: m.map_position or 999)
        members_opp = sorted([m for m in selected_war.members if m.is_opponent],     key=lambda m: m.map_position or 999)
        member_by_tag = {m.player_tag: m for m in selected_war.members}

        avg_th_our = round(sum(m.town_hall_level or 0 for m in members_our) / len(members_our), 1) if members_our else 0
        avg_th_opp = round(sum(m.town_hall_level or 0 for m in members_opp) / len(members_opp), 1) if members_opp else 0
        avg_league_our = avg_league_name(members_our)
        avg_league_opp = avg_league_name(members_opp)

        SKIP_LEAGUES = {'Unranked', 'Unknown League', None, ''}

        members_our_json = [{'th': m.town_hall_level or 0, 'name': m.player_name or '', 'pos': m.map_position or 0, 'league': m.ranked_league or '', 'lr': league_rank(m.ranked_league) if m.ranked_league not in SKIP_LEAGUES else 0} for m in members_our]
        members_opp_json = [{'th': m.town_hall_level or 0, 'name': m.player_name or '', 'pos': m.map_position or 0, 'league': m.ranked_league or '', 'lr': league_rank(m.ranked_league) if m.ranked_league not in SKIP_LEAGUES else 0} for m in members_opp]

        for a in selected_war.attacks:
            attacks_by_attacker.setdefault(a.attacker_tag, []).append(a)
            attacks_on_defender.setdefault(a.defender_tag, []).append(a)
        for lst in attacks_by_attacker.values():
            lst.sort(key=lambda a: a.attack_order or 0)
        for lst in attacks_on_defender.values():
            lst.sort(key=lambda a: a.attack_order or 0)

        for a in sorted(selected_war.attacks, key=lambda a: a.attack_order or 0):
            atk = member_by_tag.get(a.attacker_tag)
            dfn = member_by_tag.get(a.defender_tag)
            all_attacks_json.append({
                'order':         int(a.attack_order or 0),
                'attacker_name': str(atk.player_name or '?') if atk else '?',
                'attacker_pos':  int(atk.map_position or 0)   if atk else 0,
                'attacker_th':   int(atk.town_hall_level or 0) if atk else 0,
                'attacker_side': 'opp' if (atk and atk.is_opponent) else 'our',
                'defender_name': str(dfn.player_name or '?') if dfn else '?',
                'defender_pos':  int(dfn.map_position or 0)   if dfn else 0,
                'defender_th':   int(dfn.town_hall_level or 0) if dfn else 0,
                'stars':         int(a.stars or 0),
                'pct':           int(a.destruction_pct or 0),
            })

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
        members_our_json=members_our_json,
        members_opp_json=members_opp_json,
        all_attacks_json=all_attacks_json,
        now=dt.datetime.now(dt.timezone.utc),
    )


@war_bp.route('/war/api/<int:war_id>/castle-empty', methods=['POST'])
def war_toggle_castle_empty(war_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    war = db.get_or_404(ClanWar, war_id)
    war.castle_empty = not war.castle_empty
    db.session.commit()
    return jsonify(ok=True, value=war.castle_empty)


@war_bp.route('/war/api/member/<int:member_id>/is-rushed', methods=['POST'])
def war_toggle_member_rushed(member_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    m = db.get_or_404(ClanWarMember, member_id)
    if not m.is_opponent:
        return jsonify(error='Only opponent members can be flagged'), 400
    m.is_rushed = not m.is_rushed
    db.session.commit()
    return jsonify(ok=True, value=m.is_rushed)


@war_bp.route('/war/api/member/<int:member_id>/is-troll', methods=['POST'])
def war_toggle_member_troll(member_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    m = db.get_or_404(ClanWarMember, member_id)
    if not m.is_opponent:
        return jsonify(error='Only opponent members can be flagged'), 400
    m.is_troll = not m.is_troll
    db.session.commit()
    return jsonify(ok=True, value=m.is_troll)
