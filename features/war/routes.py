import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import selectinload

from extensions import db
from models import ClanWar, ClanWarMember
from features.auth.routes import _can_edit_clan_war
from services.helpers import avg_league_name, league_rank, _calc_th_multiplier

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
            atk_th  = int(atk.town_hall_level or 0) if atk else 0
            atk_pos = int(atk.map_position or 0)    if atk else 0
            dfn_th  = int(dfn.town_hall_level or 0) if dfn else 0
            dfn_pos = int(dfn.map_position or 0)    if dfn else 0
            prior   = [x for x in attacks_on_defender.get(a.defender_tag, [])
                       if (x.attack_order or 0) < (a.attack_order or 0)]
            already_3star = any(x.stars >= 3 for x in prior)
            pos_diff  = dfn_pos - atk_pos
            th_favor  = atk_th  - dfn_th
            is_farm    = already_3star or (pos_diff >= 3 and th_favor >= 3)
            is_cleanup = not already_3star and pos_diff >= 5 and th_favor >= 2
            all_attacks_json.append({
                'order':         int(a.attack_order or 0),
                'attacker_name': str(atk.player_name or '?') if atk else '?',
                'attacker_pos':  atk_pos,
                'attacker_th':   atk_th,
                'attacker_side': 'opp' if (atk and atk.is_opponent) else 'our',
                'defender_name': str(dfn.player_name or '?') if dfn else '?',
                'defender_pos':  dfn_pos,
                'defender_th':   dfn_th,
                'stars':         int(a.stars or 0),
                'pct':           int(a.destruction_pct or 0),
                'already_3star': already_3star,
                'is_farm':       is_farm,
                'is_cleanup':    is_cleanup,
            })

    # ── War verdicts ──────────────────────────────────────────────────────────
    war_verdicts = []
    if members_our and selected_war and selected_war.state in ('inWar', 'warEnded'):
        for m in members_our:
            atk_th   = m.town_hall_level or 0
            atk_pos  = m.map_position or 0
            atk_list = attacks_by_attacker.get(m.player_tag, [])

            atk_details = []
            total_adj   = 0.0

            for atk in atk_list:
                dfn      = member_by_tag.get(atk.defender_tag)
                dfn_th   = (dfn.town_hall_level or 0) if dfn else atk_th
                dfn_pos  = (dfn.map_position or 0)   if dfn else 0
                stars    = atk.stars or 0

                prior = [a for a in attacks_on_defender.get(atk.defender_tag, [])
                         if (a.attack_order or 0) < (atk.attack_order or 0)]
                already_3star = any(a.stars >= 3 for a in prior)

                pos_diff    = dfn_pos - atk_pos          # positive → defender weaker
                th_favor    = atk_th  - dfn_th           # positive → attacker stronger TH
                is_farm     = already_3star or (pos_diff >= 5 and th_favor >= 2)
                is_cleanup  = not already_3star and pos_diff >= 5 and th_favor >= 2
                is_rushed   = bool(dfn.is_rushed) if dfn else False
                is_troll    = bool(dfn.is_troll)  if dfn else False

                adj = stars * _calc_th_multiplier(dfn_th - atk_th, atk_th)
                if is_rushed or is_troll:
                    adj *= 0.9
                if already_3star:
                    adj *= 0.3
                elif is_cleanup:
                    adj *= 0.8

                total_adj += adj
                atk_details.append({
                    'defender_name': (dfn.player_name or '?') if dfn else '?',
                    'defender_th':   dfn_th,
                    'defender_pos':  dfn_pos,
                    'stars':         stars,
                    'pct':           int(atk.destruction_pct or 0),
                    'th_diff':       dfn_th - atk_th,
                    'already_3star': already_3star,
                    'is_farm':       is_farm,
                    'is_cleanup':    is_cleanup,
                    'is_rushed':     is_rushed,
                    'is_troll':      is_troll,
                })

            score = min(round(total_adj / 2 / 3 * 100), 100)

            if not atk_list:
                badge, label = 'badge-inactive', 'No Show'
            elif score >= 80: badge, label = 'badge-godlike',  'War Hero'
            elif score >= 65: badge, label = 'badge-dominant', 'Excellent'
            elif score >= 50: badge, label = 'badge-wow',      'Solid'
            elif score >= 30: badge, label = 'badge-good',     'Average'
            elif score >= 10: badge, label = 'badge-warning',  'Weak'
            else:             badge, label = 'badge-suck',     'Disaster'

            war_verdicts.append({
                'player_name':  m.player_name or m.player_tag,
                'player_th':    atk_th,
                'map_pos':      atk_pos,
                'league':       m.ranked_league or '',
                'attacks_used': len(atk_list),
                'attack_details': atk_details,
                'score':        score,
                'badge':        badge,
                'label':        label,
            })

        war_verdicts.sort(key=lambda x: -x['score'])

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
        war_verdicts=war_verdicts,
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
