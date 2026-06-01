import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import selectinload

from extensions import db
from models import ClanWar, ClanWarMember
from features.auth.routes import _can_edit_clan_war
from services.helpers import avg_league_name, league_rank
from features.war.war_combos import classify_attack, get_war_verdict

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
            already_3star      = any(x.stars >= 3 for x in prior)
            partially_attacked = len(prior) > 0 and not already_3star
            atk_label = classify_attack(
                int(a.stars or 0), atk_th, dfn_th, already_3star, partially_attacked
            ) if atk_th and dfn_th else 'unknown'
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

                prior = [a for a in attacks_on_defender.get(atk.defender_tag, [])
                         if (a.attack_order or 0) < (atk.attack_order or 0)]
                already_3star      = any(a.stars >= 3 for a in prior)
                partially_attacked = len(prior) > 0 and not already_3star

                label = classify_attack(stars, atk_th, dfn_th, already_3star, partially_attacked)
                labels.append(label)

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

            score, verdict_label, badge = get_war_verdict(labels[0], labels[1])

            war_verdicts.append({
                'player_name':    m.player_name or m.player_tag,
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


@war_bp.route('/war/stats')
def war_stats_page():
    ALL_LABELS = ['clear', 'failed_clear', 'high_clear', 'farm', 'failed_farm',
                  'low_clear', 'low_clear_fail', 'clean_up', 'failed_clean_up', 'wasted']

    wars = (ClanWar.query
            .options(selectinload(ClanWar.members), selectinload(ClanWar.attacks))
            .filter(ClanWar.state == 'warEnded')
            .order_by(ClanWar.start_time.asc())
            .all())

    wins = losses = draws = 0
    total_stars_for = total_stars_against = 0

    for w in wars:
        our = w.clan_stars or 0
        opp = w.opponent_stars or 0
        our_pct = float(w.clan_destruction_pct or 0)
        opp_pct = float(w.opponent_destruction_pct or 0)
        total_stars_for += our
        total_stars_against += opp
        if our > opp or (our == opp and our_pct > opp_pct):
            wins += 1
        elif opp > our or (our == opp and opp_pct > our_pct):
            losses += 1
        else:
            draws += 1

    player_stats = {}

    for war in wars:
        members_our = [m for m in war.members if not m.is_opponent]
        member_by_tag = {m.player_tag: m for m in war.members}
        attacks_by_attacker, attacks_on_defender = {}, {}
        for a in war.attacks:
            attacks_by_attacker.setdefault(a.attacker_tag, []).append(a)
            attacks_on_defender.setdefault(a.defender_tag, []).append(a)
        for lst in attacks_by_attacker.values():
            lst.sort(key=lambda x: x.attack_order or 0)
        for lst in attacks_on_defender.values():
            lst.sort(key=lambda x: x.attack_order or 0)

        for m in members_our:
            tag = m.player_tag
            if tag not in player_stats:
                player_stats[tag] = {
                    'name': m.player_name or tag, 'th': m.town_hall_level or 0,
                    'league': m.ranked_league or '', 'wars': 0,
                    'attacks_used': 0, 'attacks_possible': 0,
                    'stars': 0, 'three_stars': 0, 'destruction_sum': 0.0,
                    'labels': {l: 0 for l in ALL_LABELS},
                }
            ps = player_stats[tag]
            ps['name']   = m.player_name or tag
            ps['th']     = m.town_hall_level or ps['th']
            ps['league'] = m.ranked_league or ps['league']
            ps['wars'] += 1
            ps['attacks_possible'] += 2
            atk_th   = m.town_hall_level or 0
            atk_list = attacks_by_attacker.get(tag, [])
            ps['attacks_used'] += len(atk_list)

            for atk in atk_list:
                dfn = member_by_tag.get(atk.defender_tag)
                dfn_th = (dfn.town_hall_level or 0) if dfn else atk_th
                stars  = atk.stars or 0
                prior  = [a for a in attacks_on_defender.get(atk.defender_tag, [])
                          if (a.attack_order or 0) < (atk.attack_order or 0)]
                already_3star      = any(a.stars >= 3 for a in prior)
                partially_attacked = len(prior) > 0 and not already_3star
                lbl = classify_attack(stars, atk_th, dfn_th, already_3star, partially_attacked)
                ps['stars'] += stars
                ps['destruction_sum'] += float(atk.destruction_pct or 0)
                if stars == 3:
                    ps['three_stars'] += 1
                if lbl in ps['labels']:
                    ps['labels'][lbl] += 1

    # ── Per-player derived stats ──────────────────────────────────────────────
    player_list = []
    total_clan_stars = sum(ps['stars'] for ps in player_stats.values())
    for tag, ps in player_stats.items():
        used = ps['attacks_used']
        ps['tag']             = tag
        ps['attacks_missed']  = ps['attacks_possible'] - used
        ps['avg_stars']       = round(ps['stars'] / used, 2) if used else 0.0
        ps['three_star_rate'] = round(ps['three_stars'] / used * 100) if used else 0
        ps['avg_destruction'] = round(ps['destruction_sum'] / used, 1) if used else 0.0
        ps['participation']   = round(used / ps['attacks_possible'] * 100) if ps['attacks_possible'] else 0
        ps['star_pct']        = round(ps['stars'] / total_clan_stars * 100, 1) if total_clan_stars else 0
        player_list.append(ps)

    player_list.sort(key=lambda x: (-x['wars'], -x['avg_stars']))

    # ── Clan-wide totals ──────────────────────────────────────────────────────
    total_attacks_used_clan      = sum(p['attacks_used']      for p in player_list)
    total_attacks_possible_clan  = sum(p['attacks_possible']  for p in player_list)
    total_3stars_clan            = sum(p['three_stars']        for p in player_list)
    clan_participation_rate      = round(total_attacks_used_clan / total_attacks_possible_clan * 100) if total_attacks_possible_clan else 0
    clan_3star_rate              = round(total_3stars_clan / total_attacks_used_clan * 100) if total_attacks_used_clan else 0
    star_diff                    = total_stars_for - total_stars_against

    # ── Label totals clan-wide ────────────────────────────────────────────────
    label_totals = {l: 0 for l in ALL_LABELS}
    for ps in player_list:
        for lbl, cnt in ps['labels'].items():
            label_totals[lbl] = label_totals.get(lbl, 0) + cnt

    # ── Notable wars ──────────────────────────────────────────────────────────
    def _war_result(w):
        our = w.clan_stars or 0; opp = w.opponent_stars or 0
        our_pct = float(w.clan_destruction_pct or 0); opp_pct = float(w.opponent_destruction_pct or 0)
        if our > opp or (our == opp and our_pct > opp_pct): return 'win'
        if opp > our or (our == opp and opp_pct > our_pct): return 'loss'
        return 'draw'

    best_star_war = max(wars, key=lambda w: w.clan_stars or 0, default=None)
    wins_list = [w for w in wars if _war_result(w) == 'win']
    losses_list = [w for w in wars if _war_result(w) == 'loss']
    biggest_win  = max(wins_list,   key=lambda w: (w.clan_stars or 0) - (w.opponent_stars or 0), default=None)
    biggest_loss = max(losses_list, key=lambda w: (w.opponent_stars or 0) - (w.clan_stars or 0), default=None)

    def _war_card(w):
        if not w: return None
        return {
            'opponent': w.opponent_name or '?',
            'our_stars': w.clan_stars or 0,
            'opp_stars': w.opponent_stars or 0,
            'our_pct': round(float(w.clan_destruction_pct or 0), 1),
            'opp_pct': round(float(w.opponent_destruction_pct or 0), 1),
            'date': w.start_time.strftime('%d.%m.%Y') if w.start_time else '?',
            'size': w.team_size or 0,
        }

    # ── Per-TH breakdown ──────────────────────────────────────────────────────
    per_th = {}
    for ps in player_list:
        th = ps['th']
        if th not in per_th:
            per_th[th] = {'th': th, 'player_count': 0, 'stars': 0, 'attacks': 0, 'three_stars': 0}
        per_th[th]['player_count'] += 1
        per_th[th]['stars']        += ps['stars']
        per_th[th]['attacks']      += ps['attacks_used']
        per_th[th]['three_stars']  += ps['three_stars']
    for v in per_th.values():
        v['avg_stars']      = round(v['stars'] / v['attacks'], 2) if v['attacks'] else 0.0
        v['three_star_rate']= round(v['three_stars'] / v['attacks'] * 100) if v['attacks'] else 0
    per_th_list = sorted(per_th.values(), key=lambda x: -x['th'])

    # ── Hall of Fame ──────────────────────────────────────────────────────────
    eligible = [p for p in player_list if p['wars'] >= 2 and p['attacks_used'] >= 4]
    hof_avg_stars   = sorted(eligible, key=lambda x: -x['avg_stars'])[:3]
    hof_3star_rate  = sorted(eligible, key=lambda x: -x['three_star_rate'])[:3]
    hof_most_wars   = sorted(player_list, key=lambda x: -x['wars'])[:3]
    hof_shame       = sorted(player_list, key=lambda x: x['participation'])[:5]

    # ── War timeline ──────────────────────────────────────────────────────────
    war_timeline = []
    for w in wars:
        our = w.clan_stars or 0; opp = w.opponent_stars or 0
        our_pct = float(w.clan_destruction_pct or 0); opp_pct = float(w.opponent_destruction_pct or 0)
        result = _war_result(w)
        war_timeline.append({
            'date': w.start_time.strftime('%d.%m') if w.start_time else '?',
            'opponent': w.opponent_name or '?',
            'result': result,
            'our_stars': our, 'opp_stars': opp,
            'our_pct': round(our_pct, 1), 'opp_pct': round(opp_pct, 1),
            'size': w.team_size or 0,
        })

    # ── Recent war log (last 10 detailed) ────────────────────────────────────
    recent_wars = war_timeline[-10:][::-1]

    first_war_date = wars[0].start_time.strftime('%d.%m.%Y') if wars and wars[0].start_time else None

    return render_template(
        'war/war_stats.html',
        total_wars=len(wars),
        wins=wins, losses=losses, draws=draws,
        win_rate=round(wins / len(wars) * 100, 1) if wars else 0,
        total_stars_for=total_stars_for,
        total_stars_against=total_stars_against,
        star_diff=star_diff,
        total_attacks_used_clan=total_attacks_used_clan,
        total_attacks_possible_clan=total_attacks_possible_clan,
        clan_participation_rate=clan_participation_rate,
        clan_3star_rate=clan_3star_rate,
        label_totals=label_totals,
        best_star_war=_war_card(best_star_war),
        biggest_win=_war_card(biggest_win),
        biggest_loss=_war_card(biggest_loss),
        per_th_list=per_th_list,
        hof_avg_stars=hof_avg_stars,
        hof_3star_rate=hof_3star_rate,
        hof_most_wars=hof_most_wars,
        hof_shame=hof_shame,
        player_list=player_list,
        war_timeline=war_timeline,
        recent_wars=recent_wars,
        first_war_date=first_war_date,
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
