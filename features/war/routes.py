import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import selectinload

from extensions import db
from models import ClanWar, ClanWarMember, Player
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
    ALL_LABELS  = ['clear', 'failed_clear', 'high_clear', 'farm', 'failed_farm',
                   'low_clear', 'low_clear_fail', 'clean_up', 'failed_clean_up', 'wasted']
    FARM_LABELS = {'farm', 'failed_farm'}

    wars = (ClanWar.query
            .options(selectinload(ClanWar.members), selectinload(ClanWar.attacks))
            .filter(ClanWar.state == 'warEnded')
            .order_by(ClanWar.start_time.asc())
            .all())

    wins = losses = draws = 0
    total_stars_for = total_stars_against = 0

    def _war_result(w):
        our = w.clan_stars or 0; opp = w.opponent_stars or 0
        op = float(w.clan_destruction_pct or 0); pp = float(w.opponent_destruction_pct or 0)
        if our > opp or (our == opp and op > pp): return 'win'
        if opp > our or (our == opp and pp > op): return 'loss'
        return 'draw'

    for w in wars:
        our = w.clan_stars or 0; opp = w.opponent_stars or 0
        total_stars_for += our; total_stars_against += opp
        r = _war_result(w)
        if r == 'win': wins += 1
        elif r == 'loss': losses += 1
        else: draws += 1

    # Build league icon map from Player table
    player_icons = {p.tag: (p.league_icon or '') for p in Player.query.all()}

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
                    'league': m.ranked_league or '', 'league_icon': player_icons.get(tag, ''),
                    'wars': 0, 'attacks_used': 0, 'attacks_possible': 0,
                    'stars': 0, 'three_stars': 0, 'two_stars': 0, 'one_stars': 0, 'zero_stars': 0,
                    'destruction_sum': 0.0, 'labels': {l: 0 for l in ALL_LABELS},
                    'verdict_scores': [],
                    'dfn_th_sum': 0.0, 'dfn_th_sum_nf': 0.0,
                    'attacks_used_nf': 0,
                    'stars_nf': 0, 'three_stars_nf': 0, 'two_stars_nf': 0, 'one_stars_nf': 0, 'zero_stars_nf': 0,
                    'destruction_sum_nf': 0.0, 'labels_nf': {l: 0 for l in ALL_LABELS},
                    'th_breakdown': {},
                }
            ps = player_stats[tag]
            ps['name']        = m.player_name or tag
            ps['th']          = m.town_hall_level or ps['th']
            ps['league']      = m.ranked_league or ps['league']
            ps['league_icon'] = player_icons.get(tag, '') or ps['league_icon']
            ps['wars'] += 1
            ps['attacks_possible'] += 2
            atk_th   = m.town_hall_level or 0
            atk_list = attacks_by_attacker.get(tag, [])
            ps['attacks_used'] += len(atk_list)

            war_labels = []
            for atk in atk_list:
                dfn = member_by_tag.get(atk.defender_tag)
                dfn_th = (dfn.town_hall_level or 0) if dfn else atk_th
                stars  = atk.stars or 0
                prior  = [a for a in attacks_on_defender.get(atk.defender_tag, [])
                          if (a.attack_order or 0) < (atk.attack_order or 0)]
                already_3star      = any(a.stars >= 3 for a in prior)
                partially_attacked = len(prior) > 0 and not already_3star
                lbl = classify_attack(stars, atk_th, dfn_th, already_3star, partially_attacked)
                war_labels.append(lbl)
                ps['stars'] += stars
                ps['destruction_sum'] += float(atk.destruction_pct or 0)
                ps['dfn_th_sum'] += dfn_th
                if stars == 3:   ps['three_stars'] += 1
                elif stars == 2: ps['two_stars']   += 1
                elif stars == 1: ps['one_stars']   += 1
                else:            ps['zero_stars']  += 1
                if lbl in ps['labels']: ps['labels'][lbl] += 1
                if dfn_th > 0:
                    thb = ps['th_breakdown'].setdefault(dfn_th, {
                        'th': dfn_th,
                        'attacks': 0, 'stars': 0,
                        'three_stars': 0, 'two_stars': 0, 'one_stars': 0, 'zero_stars': 0,
                        'attacks_nf': 0, 'stars_nf': 0,
                        'three_stars_nf': 0, 'two_stars_nf': 0, 'one_stars_nf': 0, 'zero_stars_nf': 0,
                    })
                    thb['attacks'] += 1
                    thb['stars'] += stars
                    if stars == 3:   thb['three_stars'] += 1
                    elif stars == 2: thb['two_stars']   += 1
                    elif stars == 1: thb['one_stars']   += 1
                    else:            thb['zero_stars']  += 1
                    if lbl not in FARM_LABELS:
                        thb['attacks_nf'] += 1
                        thb['stars_nf'] += stars
                        if stars == 3:   thb['three_stars_nf'] += 1
                        elif stars == 2: thb['two_stars_nf']   += 1
                        elif stars == 1: thb['one_stars_nf']   += 1
                        else:            thb['zero_stars_nf']  += 1
                if lbl not in FARM_LABELS:
                    ps['stars_nf'] += stars
                    ps['destruction_sum_nf'] += float(atk.destruction_pct or 0)
                    ps['dfn_th_sum_nf'] += dfn_th
                    ps['attacks_used_nf'] += 1
                    if stars == 3:   ps['three_stars_nf'] += 1
                    elif stars == 2: ps['two_stars_nf']   += 1
                    elif stars == 1: ps['one_stars_nf']   += 1
                    else:            ps['zero_stars_nf']  += 1
                    if lbl in ps['labels_nf']: ps['labels_nf'][lbl] += 1

            while len(war_labels) < 2:
                war_labels.append('no_attack')
            war_score, _, _ = get_war_verdict(war_labels[0], war_labels[1])
            ps['verdict_scores'].append(war_score)

    # ── Derived per-player stats ──────────────────────────────────────────────
    player_list = []
    total_clan_stars    = sum(ps['stars']    for ps in player_stats.values())
    total_clan_stars_nf = sum(ps['stars_nf'] for ps in player_stats.values())
    for tag, ps in player_stats.items():
        used    = ps['attacks_used']
        used_nf = ps['attacks_used_nf']
        ps['tag']              = tag
        ps['attacks_missed']   = ps['attacks_possible'] - used
        ps['avg_stars']           = round(ps['stars']    / used,    2) if used    else 0.0
        ps['avg_stars_nf']        = round(ps['stars_nf'] / used_nf, 2) if used_nf else 0.0
        ps['three_star_rate']     = round(ps['three_stars']    / used    * 100) if used    else 0
        ps['three_star_rate_nf']  = round(ps['three_stars_nf'] / used_nf * 100) if used_nf else 0
        ps['two_star_rate']       = round(ps['two_stars']      / used    * 100) if used    else 0
        ps['two_star_rate_nf']    = round(ps['two_stars_nf']   / used_nf * 100) if used_nf else 0
        ps['one_star_rate']       = round(ps['one_stars']      / used    * 100) if used    else 0
        ps['one_star_rate_nf']    = round(ps['one_stars_nf']   / used_nf * 100) if used_nf else 0
        ps['zero_star_rate']      = round(ps['zero_stars']     / used    * 100) if used    else 0
        ps['zero_star_rate_nf']   = round(ps['zero_stars_nf']  / used_nf * 100) if used_nf else 0
        ps['avg_destruction']     = round(ps['destruction_sum']    / used,    1) if used    else 0.0
        ps['avg_destruction_nf']  = round(ps['destruction_sum_nf'] / used_nf, 1) if used_nf else 0.0
        ps['participation']       = round(used / ps['attacks_possible'] * 100) if ps['attacks_possible'] else 0
        ps['star_pct']            = round(ps['stars']    / total_clan_stars    * 100, 1) if total_clan_stars    else 0
        ps['star_pct_nf']         = round(ps['stars_nf'] / total_clan_stars_nf * 100, 1) if total_clan_stars_nf else 0
        vs = ps['verdict_scores']
        ps['avg_verdict']    = round(sum(vs) / len(vs), 1) if vs else 0.0
        ps['avg_dfn_th']     = round(ps['dfn_th_sum']    / used,    1) if used    else 0.0
        ps['avg_dfn_th_nf']  = round(ps['dfn_th_sum_nf'] / used_nf, 1) if used_nf else 0.0
        thb_list = sorted(ps['th_breakdown'].values(), key=lambda x: x['th'])
        for t in thb_list:
            a, a_nf = t['attacks'], t['attacks_nf']
            t['avg_stars']          = round(t['stars']    / a,    2) if a    else 0.0
            t['three_star_rate']    = round(t['three_stars']    / a    * 100) if a    else 0
            t['avg_stars_nf']       = round(t['stars_nf'] / a_nf, 2) if a_nf else 0.0
            t['three_star_rate_nf'] = round(t['three_stars_nf'] / a_nf * 100) if a_nf else 0
        ps['th_breakdown'] = thb_list
        player_list.append(ps)

    player_list.sort(key=lambda x: (-x['wars'], -x['avg_stars']))

    # ── Clan-wide totals ──────────────────────────────────────────────────────
    total_attacks_used_clan     = sum(p['attacks_used']     for p in player_list)
    total_attacks_possible_clan = sum(p['attacks_possible'] for p in player_list)
    total_3stars_clan           = sum(p['three_stars']       for p in player_list)
    clan_participation_rate     = round(total_attacks_used_clan / total_attacks_possible_clan * 100) if total_attacks_possible_clan else 0
    clan_3star_rate             = round(total_3stars_clan / total_attacks_used_clan * 100) if total_attacks_used_clan else 0
    total_3stars_clan_nf        = sum(p['three_stars_nf']  for p in player_list)
    total_attacks_used_clan_nf  = sum(p['attacks_used_nf'] for p in player_list)
    clan_3star_rate_nf          = round(total_3stars_clan_nf / total_attacks_used_clan_nf * 100) if total_attacks_used_clan_nf else 0
    star_diff                   = total_stars_for - total_stars_against

    # ── Label totals (both variants) ──────────────────────────────────────────
    label_totals    = {l: sum(p['labels'].get(l, 0)    for p in player_list) for l in ALL_LABELS}
    label_totals_nf = {l: sum(p['labels_nf'].get(l, 0) for p in player_list) for l in ALL_LABELS}

    # ── Per-TH breakdown (both variants) ─────────────────────────────────────
    def _build_per_th(key_stars, key_used, key_3stars):
        per = {}
        for ps in player_list:
            th = ps['th']
            if th not in per:
                per[th] = {'th': th, 'player_count': 0, 'stars': 0, 'attacks': 0, 'three_stars': 0}
            per[th]['player_count'] += 1
            per[th]['stars']        += ps[key_stars]
            per[th]['attacks']      += ps[key_used]
            per[th]['three_stars']  += ps[key_3stars]
        for v in per.values():
            v['avg_stars']       = round(v['stars'] / v['attacks'], 2) if v['attacks'] else 0.0
            v['three_star_rate'] = round(v['three_stars'] / v['attacks'] * 100) if v['attacks'] else 0
        return sorted(per.values(), key=lambda x: -x['th'])

    per_th_list    = _build_per_th('stars', 'attacks_used',    'three_stars')
    per_th_list_nf = _build_per_th('stars_nf', 'attacks_used_nf', 'three_stars_nf')

    # ── Hall of Fame (top 10, both variants) ─────────────────────────────────
    eligible    = [p for p in player_list if p['wars'] >= 1 and p['attacks_used']    >= 2]
    eligible_nf = [p for p in player_list if p['wars'] >= 1 and p['attacks_used_nf'] >= 2]
    hof_avg_stars      = sorted(eligible,    key=lambda x: -x['avg_stars'])[:10]
    hof_avg_stars_nf   = sorted(eligible_nf, key=lambda x: -x['avg_stars_nf'])[:10]
    hof_3star_rate     = sorted(eligible,    key=lambda x: -x['three_star_rate'])[:10]
    hof_3star_rate_nf  = sorted(eligible_nf, key=lambda x: -x['three_star_rate_nf'])[:10]
    hof_most_wars      = sorted(player_list, key=lambda x: -x['wars'])[:10]
    hof_shame          = sorted(player_list, key=lambda x: x['participation'])[:5]

    # ── War timeline ──────────────────────────────────────────────────────────
    war_timeline = []
    for w in wars:
        our = w.clan_stars or 0; opp = w.opponent_stars or 0
        our_pct = float(w.clan_destruction_pct or 0); opp_pct = float(w.opponent_destruction_pct or 0)
        war_timeline.append({
            'id': w.id,
            'date': w.start_time.strftime('%d.%m') if w.start_time else '?',
            'date_full': w.start_time.strftime('%d.%m.%Y') if w.start_time else '?',
            'opponent': w.opponent_name or '?',
            'result': _war_result(w),
            'our_stars': our, 'opp_stars': opp,
            'our_pct': round(our_pct, 1), 'opp_pct': round(opp_pct, 1),
            'size': w.team_size or 0,
        })

    recent_wars = war_timeline[-10:][::-1]
    first_war_date = wars[0].start_time.strftime('%d.%m.%Y') if wars and wars[0].start_time else None

    win_streak = 0
    for w in reversed(war_timeline):
        if w['result'] == 'win':
            win_streak += 1
        else:
            break

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
        clan_3star_rate_nf=clan_3star_rate_nf,
        label_totals=label_totals,
        label_totals_nf=label_totals_nf,
        per_th_list=per_th_list,
        per_th_list_nf=per_th_list_nf,
        hof_avg_stars=hof_avg_stars,         hof_avg_stars_nf=hof_avg_stars_nf,
        hof_3star_rate=hof_3star_rate,       hof_3star_rate_nf=hof_3star_rate_nf,
        hof_most_wars=hof_most_wars,
        hof_shame=hof_shame,
        player_list=player_list,
        recent_wars=recent_wars,
        first_war_date=first_war_date,
        win_streak=win_streak,
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
