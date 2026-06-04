import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import selectinload

from extensions import db
from models import CWLSeason, CWLClan, CWLClanMember, CWLWar, CWLMember, CWLAttack
from features.war.war_combos import classify_attack, get_war_verdict
from features.auth.routes import _can_edit_clan_war
from services.helpers import league_rank, avg_league_name

cwl_bp = Blueprint('cwl', __name__)

CLAN_TAG = None  # resolved at request time from app context


def _our_clan_tag():
    from app import CLAN_TAG as tag
    return tag


def _war_result(war, our_tag):
    """Return 'win', 'loss', or 'draw' from our clan's perspective."""
    if war.clan_tag == our_tag:
        our_stars, opp_stars = war.clan_stars or 0, war.opp_stars or 0
        our_pct,   opp_pct   = float(war.clan_destruction_pct or 0), float(war.opp_destruction_pct or 0)
    else:
        our_stars, opp_stars = war.opp_stars or 0, war.clan_stars or 0
        our_pct,   opp_pct   = float(war.opp_destruction_pct or 0), float(war.clan_destruction_pct or 0)
    if our_stars > opp_stars or (our_stars == opp_stars and our_pct > opp_pct):
        return 'win'
    if opp_stars > our_stars or (our_stars == opp_stars and opp_pct > our_pct):
        return 'loss'
    return 'draw'


def _build_war_detail(war, our_tag):
    """Build the member/attack/verdict data for one CWL war, mirroring clan war page logic."""
    members_our = sorted([m for m in war.members if m.clan_tag == our_tag],  key=lambda m: m.map_position or 999)
    members_opp = sorted([m for m in war.members if m.clan_tag != our_tag],  key=lambda m: m.map_position or 999)
    member_by_tag = {m.player_tag: m for m in war.members}

    attacks_by_attacker = {}
    attacks_on_defender = {}
    for a in sorted(war.attacks, key=lambda a: a.attack_order or 0):
        attacks_by_attacker.setdefault(a.attacker_tag, []).append(a)
        attacks_on_defender.setdefault(a.defender_tag, []).append(a)

    all_attacks_json = []
    for a in sorted(war.attacks, key=lambda a: a.attack_order or 0):
        atk = member_by_tag.get(a.attacker_tag)
        dfn = member_by_tag.get(a.defender_tag)
        atk_th  = int(atk.town_hall_level or 0) if atk else 0
        dfn_th  = int(dfn.town_hall_level or 0) if dfn else 0
        atk_pos = int(atk.map_position    or 0) if atk else 0
        dfn_pos = int(dfn.map_position    or 0) if dfn else 0
        prior   = [x for x in attacks_on_defender.get(a.defender_tag, [])
                   if (x.attack_order or 0) < (a.attack_order or 0)]
        already_3star      = any(x.stars >= 3 for x in prior)
        partially_attacked = len(prior) > 0 and not already_3star
        label = classify_attack(int(a.stars or 0), atk_th, dfn_th, already_3star, partially_attacked) if atk_th and dfn_th else 'unknown'
        all_attacks_json.append({
            'order':         int(a.attack_order or 0),
            'attacker_name': atk.player_name or '?' if atk else '?',
            'attacker_pos':  atk_pos,
            'attacker_th':   atk_th,
            'attacker_side': 'opp' if (atk and atk.clan_tag != our_tag) else 'our',
            'defender_name': dfn.player_name or '?' if dfn else '?',
            'defender_pos':  dfn_pos,
            'defender_th':   dfn_th,
            'stars':         int(a.stars or 0),
            'pct':           int(a.destruction_pct or 0),
            'label':         label,
        })

    SKIP_LEAGUES = {'Unranked', 'Unknown League', None, ''}
    members_our_json = [{'th': m.town_hall_level or 0, 'name': m.player_name or '',
                         'pos': m.map_position or 0, 'league': m.ranked_league or '',
                         'lr': league_rank(m.ranked_league) if m.ranked_league not in SKIP_LEAGUES else 0}
                        for m in members_our]
    members_opp_json = [{'th': m.town_hall_level or 0, 'name': m.player_name or '',
                         'pos': m.map_position or 0, 'league': m.ranked_league or '',
                         'lr': league_rank(m.ranked_league) if m.ranked_league not in SKIP_LEAGUES else 0}
                        for m in members_opp]

    war_verdicts = []
    if war.state in ('inWar', 'warEnded'):
        for m in members_our:
            atk_th   = m.town_hall_level or 0
            atk_list = attacks_by_attacker.get(m.player_tag, [])
            labels   = []
            atk_details = []

            for atk in atk_list:
                dfn     = member_by_tag.get(atk.defender_tag)
                dfn_th  = (dfn.town_hall_level or 0) if dfn else atk_th
                dfn_pos = (dfn.map_position    or 0) if dfn else 0
                stars   = atk.stars or 0
                prior   = [a for a in attacks_on_defender.get(atk.defender_tag, [])
                           if (a.attack_order or 0) < (atk.attack_order or 0)]
                already_3star      = any(a.stars >= 3 for a in prior)
                partially_attacked = len(prior) > 0 and not already_3star
                label  = classify_attack(stars, atk_th, dfn_th, already_3star, partially_attacked)
                labels.append(label)
                stars_before  = max((a.stars for a in prior), default=0)
                target_state  = 'cleared' if already_3star else ('partial' if partially_attacked else 'fresh')
                atk_details.append({
                    'defender_name': (dfn.player_name or '?') if dfn else '?',
                    'defender_th':   dfn_th,
                    'defender_pos':  dfn_pos,
                    'stars':         stars,
                    'pct':           int(atk.destruction_pct or 0),
                    'th_diff':       dfn_th - atk_th,
                    'pos_diff':      dfn_pos - (m.map_position or 0),
                    'label':         label,
                    'stars_before':  stars_before,
                    'target_state':  target_state,
                })

            while len(labels) < 1:
                labels.append('no_attack')

            score, verdict_label, badge = get_war_verdict(labels[0], labels[1] if len(labels) > 1 else 'no_attack')
            war_verdicts.append({
                'player_name':    m.player_name or m.player_tag,
                'player_tag':     m.player_tag,
                'player_th':      atk_th,
                'map_pos':        m.map_position or 0,
                'league':         m.ranked_league or '',
                'attacks_used':   len(atk_list),
                'attack_details': atk_details,
                'score':          score,
                'badge':          badge,
                'label':          verdict_label,
                'atk_labels':     labels,
            })
        war_verdicts.sort(key=lambda x: -x['score'])

    our_side = war.clan_tag == our_tag

    def _avg_th(members):
        return round(sum(m.town_hall_level or 0 for m in members) / len(members), 1) if members else '—'

    return {
        'war':              war,
        'our_tag':          our_tag,
        'our_clan_tag':     war.clan_tag    if our_side else war.opp_tag,
        'our_clan_name':    war.clan_name   if our_side else war.opp_name,
        'our_clan_badge':   war.clan_badge  if our_side else war.opp_badge,
        'our_stars':        war.clan_stars  if our_side else war.opp_stars,
        'our_attacks':      war.clan_attacks if our_side else war.opp_attacks,
        'our_pct':          war.clan_destruction_pct if our_side else war.opp_destruction_pct,
        'our_avg_th':       _avg_th(members_our),
        'our_avg_league':   avg_league_name(members_our),
        'our_cwl_league':   war.clan_cwl_league    if our_side else war.opp_cwl_league,
        'our_location':     war.clan_location      if our_side else war.opp_location,
        'our_wars_won':     war.clan_wars_won      if our_side else war.opp_wars_won,
        'our_war_frequency':war.clan_war_frequency if our_side else war.opp_war_frequency,
        'our_win_streak':   war.clan_win_streak    if our_side else war.opp_win_streak,
        'opp_clan_tag':     war.opp_tag     if our_side else war.clan_tag,
        'opp_clan_name':    war.opp_name    if our_side else war.clan_name,
        'opp_clan_badge':   war.opp_badge   if our_side else war.clan_badge,
        'opp_stars':        war.opp_stars   if our_side else war.clan_stars,
        'opp_attacks':      war.opp_attacks if our_side else war.clan_attacks,
        'opp_pct':          war.opp_destruction_pct if our_side else war.clan_destruction_pct,
        'opp_avg_th':       _avg_th(members_opp),
        'opp_avg_league':   avg_league_name(members_opp),
        'opp_cwl_league':   war.opp_cwl_league     if our_side else war.clan_cwl_league,
        'opp_location':     war.opp_location       if our_side else war.clan_location,
        'opp_wars_won':     war.opp_wars_won       if our_side else war.clan_wars_won,
        'opp_war_frequency':war.opp_war_frequency  if our_side else war.clan_war_frequency,
        'opp_win_streak':   war.opp_win_streak     if our_side else war.clan_win_streak,
        'members_our':      members_our,
        'members_opp':      members_opp,
        'members_our_json': members_our_json,
        'members_opp_json': members_opp_json,
        'attacks_by_attacker': attacks_by_attacker,
        'attacks_on_defender': attacks_on_defender,
        'member_by_tag':    member_by_tag,
        'all_attacks_json': all_attacks_json,
        'war_verdicts':     war_verdicts,
        'result':           _war_result(war, our_tag) if war.state == 'warEnded' else None,
    }


@cwl_bp.route('/cwl')
def cwl_page():
    our_tag = _our_clan_tag()

    seasons = CWLSeason.query.order_by(CWLSeason.id.desc()).all()
    if not seasons:
        return render_template('cwl/cwl.html', season=None, our_tag=our_tag)

    selected_season_id = request.args.get('season_id', type=int)
    if selected_season_id:
        season = CWLSeason.query.get(selected_season_id)
    else:
        season = seasons[0]

    if not season:
        return render_template('cwl/cwl.html', season=None, our_tag=our_tag, seasons=seasons)

    clans = (CWLClan.query
             .filter_by(season_id=season.id)
             .options(selectinload(CWLClan.members))
             .all())

    wars = (CWLWar.query
            .filter_by(season_id=season.id)
            .options(selectinload(CWLWar.members), selectinload(CWLWar.attacks))
            .order_by(CWLWar.round_number, CWLWar.id)
            .all())

    # ── Per-clan day-1 roster stats ───────────────────────────────────────────
    SKIP_LEAGUES = {'Unranked', 'Unknown League', None, ''}
    clan_rosters = {}
    for clan in clans:
        members = sorted(clan.members, key=lambda m: m.town_hall_level or 0, reverse=True)
        avg_th  = (sum(m.town_hall_level or 0 for m in members) / len(members)) if members else 0
        al      = avg_league_name(members)
        top15   = members[:15]
        top15_th = round(sum(m.town_hall_level or 0 for m in top15) / len(top15), 1) if top15 else 0
        top15_al = avg_league_name(top15)
        clan_rosters[clan.tag] = {
            'members':            members,
            'avg_th':             round(avg_th, 1),
            'avg_league':         al,
            'avg_lr':             league_rank(al) if al else 0,
            'avg_unranked':       sum(1 for m in members if m.ranked_league in SKIP_LEAGUES),
            'count':              len(members),
            'top15_avg_th':       top15_th,
            'top15_league':       top15_al,
            'top15_league_lr':    league_rank(top15_al) if top15_al else 0,
            'top15_unranked':     sum(1 for m in top15 if m.ranked_league in SKIP_LEAGUES),
            'active_members':     {},  # filled below after wars are processed
        }

    # ── Standings ─────────────────────────────────────────────────────────────
    standings = {c.tag: {
        'name': c.name, 'badge_url': c.badge_url, 'tag': c.tag,
        'wars': 0, 'wins': 0, 'losses': 0, 'draws': 0,
        'stars': 0, 'destruction': 0.0, 'attacks': 0, 'attacks_possible': 0,
        'rounds': [],
    } for c in clans}

    for war in wars:
        if war.state == 'preparation':
            continue
        ended = war.state == 'warEnded'
        for tag, stars, pct, atk, opp_tag, opp_stars, opp_pct, opp_name, opp_badge in (
            (war.clan_tag, war.clan_stars or 0, float(war.clan_destruction_pct or 0), war.clan_attacks or 0,
             war.opp_tag,  war.opp_stars  or 0, float(war.opp_destruction_pct  or 0), war.opp_name, war.opp_badge),
            (war.opp_tag,  war.opp_stars  or 0, float(war.opp_destruction_pct  or 0), war.opp_attacks or 0,
             war.clan_tag, war.clan_stars or 0, float(war.clan_destruction_pct or 0), war.clan_name, war.clan_badge),
        ):
            if tag not in standings:
                continue
            s = standings[tag]
            s['stars']             += stars
            s['destruction']       += pct
            s['attacks']           += atk
            s['attacks_possible']  += war.team_size or 0
            result = None
            if ended:
                s['wars'] += 1
                if stars > opp_stars or (stars == opp_stars and pct > opp_pct):
                    s['wins'] += 1
                    result = 'win'
                elif opp_stars > stars or (stars == opp_stars and opp_pct > pct):
                    s['losses'] += 1
                    result = 'loss'
                else:
                    s['draws'] += 1
                    result = 'draw'
            s['rounds'].append({
                'round':     war.round_number,
                'opp_name':  opp_name or '?',
                'opp_badge': opp_badge,
                'our_stars': stars,
                'opp_stars': opp_stars,
                'our_pct':   round(pct, 1),
                'opp_pct':   round(opp_pct, 1),
                'state':     war.state,
                'result':    result,
                'atk_done':  atk,
                'atk_total': war.team_size or 0,
            })

    for s_data in standings.values():
        s_data['rounds'].sort(key=lambda r: r['round'])

    # ── CWL score: stars + 10 per win + 10 live bonus if currently winning ────
    for war in wars:
        if war.state != 'inWar':
            continue
        for tag, our_stars, opp_stars, our_pct, opp_pct in (
            (war.clan_tag, war.clan_stars or 0, war.opp_stars or 0,
             float(war.clan_destruction_pct or 0), float(war.opp_destruction_pct or 0)),
            (war.opp_tag,  war.opp_stars  or 0, war.clan_stars or 0,
             float(war.opp_destruction_pct or 0), float(war.clan_destruction_pct or 0)),
        ):
            if tag not in standings:
                continue
            standings[tag]['live_winning'] = (
                our_stars > opp_stars or
                (our_stars == opp_stars and our_pct > opp_pct)
            )

    for s_data in standings.values():
        s_data.setdefault('live_winning', False)
        s_data['score'] = s_data['stars'] + s_data['wins'] * 10 + (10 if s_data['live_winning'] else 0)

    # ── Active member stats per clan (selected for any war day) ─────────────
    class _MP:
        def __init__(self, ranked_league): self.ranked_league = ranked_league

    for war in wars:
        if war.state not in ('inWar', 'warEnded'):
            continue
        attack_counts = {}
        for a in war.attacks:
            attack_counts[a.attacker_tag] = attack_counts.get(a.attacker_tag, 0) + 1
        for member in war.members:
            r = clan_rosters.get(member.clan_tag)
            if r is None:
                continue
            tag = member.player_tag
            if tag not in r['active_members']:
                r['active_members'][tag] = {
                    'th': member.town_hall_level or 0,
                    'league': member.ranked_league,
                    'wars_selected': 0,
                    'attacks_done': 0,
                }
            r['active_members'][tag]['wars_selected'] += 1
            r['active_members'][tag]['attacks_done'] += attack_counts.get(tag, 0)

    for r in clan_rosters.values():
        active = r['active_members']
        if active:
            ths = [v['th'] for v in active.values()]
            r['active_avg_th']    = round(sum(ths) / len(ths), 1)
            al = avg_league_name([_MP(v['league']) for v in active.values()])
            r['active_league']    = al
            r['active_league_lr'] = league_rank(al) if al else 0
            r['active_count']     = len(active)
            r['active_unranked']  = sum(1 for v in active.values() if v['league'] in SKIP_LEAGUES)
        else:
            r['active_avg_th']    = 0
            r['active_league']    = None
            r['active_league_lr'] = 0
            r['active_count']     = 0
            r['active_unranked']  = 0

    # ── Sort day-1 roster by current-day map position ────────────────────────
    # Find the most recent inWar/warEnded war per clan (prefer inWar over warEnded)
    clan_current_war = {}
    for war in sorted(wars, key=lambda w: w.round_number or 0):
        if war.state not in ('inWar', 'warEnded'):
            continue
        for tag in (war.clan_tag, war.opp_tag):
            if tag not in clan_current_war or war.state == 'inWar':
                clan_current_war[tag] = war

    for clan_tag, war in clan_current_war.items():
        r = clan_rosters.get(clan_tag)
        if r is None:
            continue
        pos_lookup = {
            m.player_tag: m.map_position or 999
            for m in war.members
            if m.clan_tag == clan_tag
        }
        r['members'] = sorted(r['members'], key=lambda m: pos_lookup.get(m.player_tag, 999))

    sorted_standings = sorted(
        standings.values(),
        key=lambda s: (-s['score'], -s['stars'], -s['destruction']),
    )

    current_enemy_tag  = None
    tomorrow_enemy_tag = None
    for war in wars:
        involves_us = (war.clan_tag == our_tag or war.opp_tag == our_tag)
        if not involves_us:
            continue
        opp = war.opp_tag if war.clan_tag == our_tag else war.clan_tag
        if war.state == 'inWar' and not current_enemy_tag:
            current_enemy_tag = opp
        elif war.state == 'preparation' and not tomorrow_enemy_tag:
            tomorrow_enemy_tag = opp

    # ── Per-round war details (our clan only) ─────────────────────────────────
    rounds = {}
    for war in wars:
        if war.clan_tag != our_tag and war.opp_tag != our_tag:
            continue
        detail = _build_war_detail(war, our_tag)
        rounds[war.round_number] = detail

    sorted_rounds = sorted(rounds.items())

    # ── Extended clan info from first available war per clan ──────────────────
    clan_war_info = {}
    for war in wars:
        for tag, cwl_l, loc, won, freq, streak in [
            (war.clan_tag, war.clan_cwl_league, war.clan_location, war.clan_wars_won, war.clan_war_frequency, war.clan_win_streak),
            (war.opp_tag,  war.opp_cwl_league,  war.opp_location,  war.opp_wars_won,  war.opp_war_frequency,  war.opp_win_streak),
        ]:
            if tag and tag not in clan_war_info:
                clan_war_info[tag] = {
                    'cwl_league': cwl_l, 'location': loc,
                    'wars_won': won, 'war_frequency': freq, 'win_streak': streak,
                }

    # ── Current day attack progress ───────────────────────────────────────────
    current_day_attacks = {}
    for war in wars:
        if war.state != 'inWar':
            continue
        size = war.team_size or 0
        for tag, atk in (
            (war.clan_tag, war.clan_attacks or 0),
            (war.opp_tag,  war.opp_attacks  or 0),
        ):
            if tag:
                current_day_attacks[tag] = {'done': atk, 'total': size}

    our_clan = next((c for c in clans if c.tag == our_tag), None)

    return render_template(
        'cwl/cwl.html',
        season=season,
        seasons=seasons,
        our_tag=our_tag,
        our_clan=our_clan,
        current_enemy_tag=current_enemy_tag,
        tomorrow_enemy_tag=tomorrow_enemy_tag,
        clans=clans,
        clan_rosters=clan_rosters,
        clan_war_info=clan_war_info,
        current_day_attacks=current_day_attacks,
        standings=sorted_standings,
        sorted_rounds=sorted_rounds,
        now=dt.datetime.now(dt.timezone.utc),
        league_rank=league_rank,
    )


# ── Flag toggle API ───────────────────────────────────────────────────────────

@cwl_bp.route('/cwl/api/war/<int:war_id>/castle-empty', methods=['POST'])
def cwl_toggle_castle_empty(war_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    war = db.get_or_404(CWLWar, war_id)
    war.castle_empty = not war.castle_empty
    db.session.commit()
    return jsonify(ok=True, value=war.castle_empty)


@cwl_bp.route('/cwl/api/member/<int:member_id>/is-rushed', methods=['POST'])
def cwl_toggle_member_rushed(member_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    m = db.get_or_404(CWLMember, member_id)
    m.is_rushed = not m.is_rushed
    db.session.commit()
    return jsonify(ok=True, value=m.is_rushed)


@cwl_bp.route('/cwl/api/member/<int:member_id>/is-troll', methods=['POST'])
def cwl_toggle_member_troll(member_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    m = db.get_or_404(CWLMember, member_id)
    m.is_troll = not m.is_troll
    db.session.commit()
    return jsonify(ok=True, value=m.is_troll)


@cwl_bp.route('/cwl/api/clan-member/<int:member_id>/is-rushed', methods=['POST'])
def cwl_toggle_clan_member_rushed(member_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    m = db.get_or_404(CWLClanMember, member_id)
    m.is_rushed = not m.is_rushed
    db.session.commit()
    return jsonify(ok=True, value=m.is_rushed)


@cwl_bp.route('/cwl/api/clan-member/<int:member_id>/is-troll', methods=['POST'])
def cwl_toggle_clan_member_troll(member_id):
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403
    m = db.get_or_404(CWLClanMember, member_id)
    m.is_troll = not m.is_troll
    db.session.commit()
    return jsonify(ok=True, value=m.is_troll)
