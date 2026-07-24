import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from extensions import db
from models import ClanWar, ClanWarMember, WarCombo
from features.auth.routes import _can_edit_clan_war
from services.helpers import avg_league_name, league_rank, SKIP_LEAGUES, get_combos
from features.war.war_combos import classify_attack, get_war_verdict, get_attack_context
from features.player.routes import clear_bulk_standing_cache

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

        members_our_json = [{'tag': m.player_tag or '', 'th': m.town_hall_level or 0, 'name': m.player_name or '', 'pos': m.map_position or 0, 'league': m.ranked_league or '', 'lr': league_rank(m.ranked_league) if m.ranked_league not in SKIP_LEAGUES else 0} for m in members_our]
        members_opp_json = [{'tag': m.player_tag or '', 'th': m.town_hall_level or 0, 'name': m.player_name or '', 'pos': m.map_position or 0, 'league': m.ranked_league or '', 'lr': league_rank(m.ranked_league) if m.ranked_league not in SKIP_LEAGUES else 0} for m in members_opp]

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
            already_3star, partially_attacked = get_attack_context(a, attacks_on_defender)
            atk_label = classify_attack(
                int(a.stars or 0), atk_th, dfn_th, already_3star, partially_attacked
            ) if atk_th and dfn_th else 'unknown'
            all_attacks_json.append({
                'order':         int(a.attack_order or 0),
                'attacker_tag':  str(atk.player_tag or '') if atk else '',
                'attacker_name': str(atk.player_name or '?') if atk else '?',
                'attacker_pos':  atk_pos,
                'attacker_th':   atk_th,
                'attacker_side': 'opp' if (atk and atk.is_opponent) else 'our',
                'defender_name': str(dfn.player_name or '?') if dfn else '?',
                'defender_pos':  dfn_pos,
                'defender_th':   dfn_th,
                'stars':         int(a.stars or 0),
                'pct':           int(a.destruction_pct or 0),
                'duration':      int(a.duration or 0),
                'label':         atk_label,
            })

    # ── War verdicts ──────────────────────────────────────────────────────────
    war_verdicts = []
    if members_our and selected_war and selected_war.state in ('inWar', 'warEnded'):
        for m in members_our:
            atk_th   = m.town_hall_level or 0
            atk_pos  = m.map_position or 0
            atk_list = attacks_by_attacker.get(m.player_tag, [])

            atk_details = []
            labels      = []

            for atk in atk_list:
                dfn      = member_by_tag.get(atk.defender_tag)
                dfn_th   = (dfn.town_hall_level or 0) if dfn else atk_th
                dfn_pos  = (dfn.map_position or 0)    if dfn else 0
                stars    = atk.stars or 0

                already_3star, partially_attacked = get_attack_context(atk, attacks_on_defender)
                label = classify_attack(stars, atk_th, dfn_th, already_3star, partially_attacked)
                labels.append(label)

                prior        = [a for a in attacks_on_defender.get(atk.defender_tag, [])
                                if (a.attack_order or 0) < (atk.attack_order or 0)]
                stars_before = max((a.stars for a in prior), default=0)

                if already_3star:
                    target_state = 'cleared'
                elif partially_attacked:
                    target_state = 'partial'
                else:
                    target_state = 'fresh'

                atk_details.append({
                    'defender_name': (dfn.player_name or '?') if dfn else '?',
                    'defender_th':   dfn_th,
                    'defender_pos':  dfn_pos,
                    'stars':         stars,
                    'pct':           int(atk.destruction_pct or 0),
                    'th_diff':       dfn_th - atk_th,
                    'pos_diff':      dfn_pos - atk_pos,
                    'label':         label,
                    'stars_before':  stars_before,
                    'target_state':  target_state,
                })

            while len(labels) < 2:
                labels.append('no_attack')

            score, verdict_label, badge = get_war_verdict(labels[0], labels[1], get_combos())

            war_verdicts.append({
                'player_name':    m.player_name or m.player_tag,
                'player_tag':     m.player_tag or '',
                'player_th':      atk_th,
                'map_pos':        atk_pos,
                'league':         m.ranked_league or '',
                'attacks_used':   len(atk_list),
                'attack_details': atk_details,
                'score':          score,
                'badge':          badge,
                'label':          verdict_label,
                'atk_labels':     labels,
            })

        war_verdicts.sort(key=lambda x: -x['score'])

    # ── War matchup rates from all completed wars ─────────────────────────────
    _hist = (ClanWar.query
             .options(selectinload(ClanWar.members), selectinload(ClanWar.attacks))
             .filter(ClanWar.state.in_(['inWar', 'warEnded']))
             .all())
    # War-wide attack-usage rate, for the win-probability engine's remaining attacks — a
    # historical star distribution only describes attacks that landed, not the real chance a
    # remaining slot never gets used at all (forgot, ran out of time). Only warEnded wars count,
    # since an ongoing war's unused slots aren't "missed" yet — they may still get used before it
    # ends. One flat rate is used for every player on both sides (see warMissRate in
    # clanwar.html) — regular war is every other day with 2 attacks each, so per-player/per-side
    # blending only added noise and a structural bias (our roster always has personal history, a
    # regular-war opponent almost never does).
    _raw_war, _player_war = {}, {}
    _our_possible, _our_used = 0, 0
    for hw in _hist:
        _mb = {m.player_tag: m for m in hw.members}
        for atk in hw.attacks:
            am = _mb.get(atk.attacker_tag)
            dm = _mb.get(atk.defender_tag)
            if not am or not dm:
                continue
            ath = am.town_hall_level or 0
            dth = dm.town_hall_level or 0
            if ath < 5 or dth < 5:
                continue
            s = min(atk.stars or 0, 3)
            k = (ath, dth)
            _raw_war.setdefault(k, [0, 0, 0, 0])[s] += 1
            _player_war.setdefault(am.player_tag, {}).setdefault(k, [0, 0, 0, 0])[s] += 1

        if hw.state != 'warEnded':
            continue
        for m in hw.members:
            if m.player_tag and not m.is_opponent:
                _our_possible += 2
        if hw.clan_attacks:
            _our_used += hw.clan_attacks

    war_matchup_rates, war_matchup_counts = {}, {}
    war_total_atk_count = sum(sum(v) for v in _raw_war.values())
    for (ath, dth), counts in _raw_war.items():
        total = sum(counts)
        k = f'{ath}_{dth}'
        war_matchup_counts[k] = total
        if total >= 5:
            war_matchup_rates[k] = [round(c / total, 4) for c in counts]

    war_player_history = {}
    for tag, matchups in _player_war.items():
        ph = {}
        for (ath, dth), counts in matchups.items():
            if sum(counts) >= 1:
                ph[f'{ath}_{dth}'] = {'counts': counts, 'total': sum(counts)}
        if ph:
            war_player_history[tag] = ph

    war_global_attack_rate_our = {'used': _our_used, 'possible': _our_possible}

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
        war_matchup_rates=war_matchup_rates,
        war_matchup_counts=war_matchup_counts,
        war_total_atk_count=war_total_atk_count,
        war_player_history=war_player_history,
        war_global_attack_rate_our=war_global_attack_rate_our,
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


@war_bp.route('/war/api/combo/add', methods=['POST'])
def war_add_combo():
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403

    data = request.get_json(silent=True) or {}
    label_a = str(data.get('label_a') or '').strip()
    label_b = str(data.get('label_b') or '').strip()
    verdict_label = str(data.get('verdict_label') or '').strip()

    if not label_a or not label_b:
        return jsonify(error='Missing attack labels'), 400
    try:
        score = int(data.get('score'))
    except (TypeError, ValueError):
        return jsonify(error='Score must be a number'), 400
    if not (0 <= score <= 100):
        return jsonify(error='Score must be between 0 and 100'), 400
    if not verdict_label or len(verdict_label) > 60:
        return jsonify(error='Verdict label must be 1-60 characters'), 400

    a, b = sorted([label_a, label_b])
    db.session.add(WarCombo(label_a=a, label_b=b, score=score, verdict_label=verdict_label))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='Combo already named'), 409

    clear_bulk_standing_cache()
    return jsonify(ok=True)
