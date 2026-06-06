import calendar as _cal
import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.orm import selectinload

from extensions import db
from models import CWLSeason, CWLClan, CWLClanMember, CWLWar, CWLMember, CWLAttack
from features.war.war_combos import classify_attack, get_war_verdict
from features.auth.routes import _can_edit_clan_war
from services.helpers import league_rank, avg_league_name, SKIP_LEAGUES

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

    # ── Win reachability for live wars ────────────────────────────────────────
    win_status = None
    if war.state == 'inWar':
        our_stars_now = (war.clan_stars  if our_side else war.opp_stars)  or 0
        opp_stars_now = (war.opp_stars   if our_side else war.clan_stars) or 0
        our_done      = (war.clan_attacks if our_side else war.opp_attacks) or 0
        opp_done      = (war.opp_attacks  if our_side else war.clan_attacks) or 0
        size          = war.team_size or 15
        our_max = our_stars_now + max(0, size - our_done) * 3
        opp_max = opp_stars_now + max(0, size - opp_done) * 3
        if our_stars_now > opp_max:
            win_status = 'safe_win'
        elif opp_stars_now > our_max:
            win_status = 'cant_win'
        else:
            win_status = 'contested'

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
        'win_status':       win_status,
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


# ── Long-term CWL stats ───────────────────────────────────────────────────────

def _league_class(name):
    for key in ('Crystal', 'Master', 'Champion', 'Titan', 'Legend', 'Gold', 'Silver', 'Bronze'):
        if key in (name or ''):
            return f'lc-{key.lower()}'
    return 'lc-unknown'


@cwl_bp.route('/cwl/stats')
def cwl_stats_page():
    our_tag = _our_clan_tag()

    LEAGUE_ORDER = {
        'Bronze League III': 1, 'Bronze League II': 2, 'Bronze League I': 3,
        'Silver League III': 4, 'Silver League II': 5, 'Silver League I': 6,
        'Gold League III':   7, 'Gold League II':   8, 'Gold League I':   9,
        'Crystal League III':10, 'Crystal League II':11, 'Crystal League I':12,
        'Master League III': 13, 'Master League II': 14, 'Master League I': 15,
        'Champion League III':16,'Champion League II':17,'Champion League I':18,
        'Titan League III':  19, 'Titan League II':  20, 'Titan League I':  21,
        'Legend League':     22,
    }

    seasons = CWLSeason.query.order_by(CWLSeason.id.asc()).all()
    if not seasons:
        return render_template('cwl/cwl_stats.html', no_data=True, our_tag=our_tag)

    all_wars = (CWLWar.query
                .options(selectinload(CWLWar.members), selectinload(CWLWar.attacks))
                .all())

    wars_by_season = {}
    for w in all_wars:
        wars_by_season.setdefault(w.season_id, []).append(w)

    our_ended_wars = [w for w in all_wars
                      if (w.clan_tag == our_tag or w.opp_tag == our_tag)
                      and w.state == 'warEnded']

    # ── Per-season summary ────────────────────────────────────────────────────
    seasons_data = []
    for season in seasons:
        s_wars = [w for w in our_ended_wars if w.season_id == season.id]
        if not s_wars:
            continue

        wins = losses = draws = 0
        stars_for = stars_against = 0
        for war in s_wars:
            result = _war_result(war, our_tag)
            if result == 'win':    wins   += 1
            elif result == 'loss': losses += 1
            else:                  draws  += 1
            if war.clan_tag == our_tag:
                stars_for     += war.clan_stars or 0
                stars_against += war.opp_stars  or 0
            else:
                stars_for     += war.opp_stars  or 0
                stars_against += war.clan_stars or 0

        # Group rank
        group_wars = [w for w in wars_by_season.get(season.id, []) if w.state == 'warEnded']
        clan_pts = {}
        for w in group_wars:
            for tag, s, p, opp_s, opp_p in [
                (w.clan_tag, w.clan_stars or 0, float(w.clan_destruction_pct or 0),
                 w.opp_stars or 0,  float(w.opp_destruction_pct  or 0)),
                (w.opp_tag,  w.opp_stars  or 0, float(w.opp_destruction_pct  or 0),
                 w.clan_stars or 0, float(w.clan_destruction_pct or 0)),
            ]:
                if not tag: continue
                cs = clan_pts.setdefault(tag, {'wins': 0, 'stars': 0, 'dest': 0.0})
                cs['stars'] += s; cs['dest'] += p
                if s > opp_s or (s == opp_s and p > opp_p): cs['wins'] += 1
        sorted_tags = sorted(clan_pts, key=lambda t: (-clan_pts[t]['wins']*10 - clan_pts[t]['stars'], -clan_pts[t]['dest']))
        rank       = next((i+1 for i, t in enumerate(sorted_tags) if t == our_tag), None)
        group_size = len(sorted_tags)

        try:
            yr, mo    = season.season.split('-')
            szn_label = f"{_cal.month_abbr[int(mo)]} {yr}"
        except Exception:
            szn_label = season.season

        league = season.league_name or '—'
        seasons_data.append({
            'season_id':     season.id,
            'season':        season.season,
            'season_label':  szn_label,
            'league':        league,
            'league_rank':   LEAGUE_ORDER.get(league, 0),
            'league_class':  _league_class(league),
            'wars':          len(s_wars),
            'wins':          wins,
            'losses':        losses,
            'draws':         draws,
            'stars_for':     stars_for,
            'stars_against': stars_against,
            'star_diff':     stars_for - stars_against,
            'win_rate':      round(wins / len(s_wars) * 100) if s_wars else 0,
            'rank':          rank,
            'group_size':    group_size,
        })

    if not seasons_data:
        return render_template('cwl/cwl_stats.html', no_data=True, our_tag=our_tag)

    # ── League movement & group finish per season ─────────────────────────────
    for i, s in enumerate(seasons_data):
        if i > 0 and seasons_data[i-1]['league_rank'] and s['league_rank']:
            prev_lr, curr_lr = seasons_data[i-1]['league_rank'], s['league_rank']
            s['league_movement'] = 'up' if curr_lr > prev_lr else ('down' if curr_lr < prev_lr else 'same')
        else:
            s['league_movement'] = 'start'

        if s['rank']:
            if s['rank'] <= 2:
                s['finish'] = 'promotion'
            elif s['group_size'] and s['rank'] >= s['group_size'] - 1:
                s['finish'] = 'relegation'
            else:
                s['finish'] = 'mid'
        else:
            s['finish'] = None

    # ── Aggregate season stats ────────────────────────────────────────────────
    total_seasons       = len(seasons_data)
    total_wars          = sum(s['wars']          for s in seasons_data)
    total_wins          = sum(s['wins']          for s in seasons_data)
    total_losses        = sum(s['losses']        for s in seasons_data)
    total_draws         = sum(s['draws']         for s in seasons_data)
    total_stars_for     = sum(s['stars_for']     for s in seasons_data)
    total_stars_against = sum(s['stars_against'] for s in seasons_data)
    win_rate            = round(total_wins / total_wars * 100) if total_wars else 0

    ranked_szns  = [s for s in seasons_data if s['rank']]
    avg_rank     = round(sum(s['rank'] for s in ranked_szns) / len(ranked_szns), 1) if ranked_szns else None
    promotions   = sum(1 for s in seasons_data if s.get('finish') == 'promotion')
    relegations  = sum(1 for s in seasons_data if s.get('finish') == 'relegation')

    rank_dist = {}
    for s in seasons_data:
        if s['rank']:
            rank_dist[s['rank']] = rank_dist.get(s['rank'], 0) + 1

    # ── Player stats + per-season tracking ───────────────────────────────────
    player_stats  = {}
    player_szn    = {}   # tag -> {season_id -> {'stars','attacks','wars'}}

    for war in our_ended_wars:
        members_our   = [m for m in war.members if m.clan_tag == our_tag]
        member_by_tag = {m.player_tag: m for m in war.members}
        atks_by_att, atks_on_dfn = {}, {}
        for a in sorted(war.attacks, key=lambda x: x.attack_order or 0):
            atks_by_att.setdefault(a.attacker_tag, []).append(a)
            atks_on_dfn.setdefault(a.defender_tag, []).append(a)

        for member in members_our:
            tag    = member.player_tag
            atk_th = member.town_hall_level or 0
            if tag not in player_stats:
                player_stats[tag] = {
                    'name': member.player_name or tag, 'th': atk_th,
                    'wars': 0, 'attacks_used': 0, 'attacks_possible': 0,
                    'stars': 0, 'three_stars': 0, 'two_stars': 0, 'one_stars': 0, 'zero_stars': 0,
                    'destruction_sum': 0.0, 'verdict_scores': [], 'seasons_set': set(),
                }
            ps = player_stats[tag]
            ps['name'] = member.player_name or tag
            ps['th']   = atk_th or ps['th']
            ps['wars'] += 1
            ps['attacks_possible'] += 1
            ps['seasons_set'].add(war.season_id)

            atk_list = atks_by_att.get(tag, [])
            ps['attacks_used'] += len(atk_list)

            sw = player_szn.setdefault(tag, {}).setdefault(war.season_id, {'stars': 0, 'attacks': 0, 'wars': 0})
            sw['wars']    += 1
            sw['attacks'] += len(atk_list)
            sw['stars']   += sum(a.stars or 0 for a in atk_list)

            for atk in atk_list:
                dfn    = member_by_tag.get(atk.defender_tag)
                dfn_th = (dfn.town_hall_level or 0) if dfn else atk_th
                stars  = atk.stars or 0
                prior  = [a for a in atks_on_dfn.get(atk.defender_tag, [])
                          if (a.attack_order or 0) < (atk.attack_order or 0)]
                already_3star      = any(a.stars >= 3 for a in prior)
                partially_attacked = len(prior) > 0 and not already_3star
                label = classify_attack(stars, atk_th, dfn_th, already_3star, partially_attacked)
                ps['stars'] += stars
                ps['destruction_sum'] += float(atk.destruction_pct or 0)
                if stars == 3:   ps['three_stars'] += 1
                elif stars == 2: ps['two_stars']   += 1
                elif stars == 1: ps['one_stars']   += 1
                else:            ps['zero_stars']  += 1

            lbl1 = classify_attack(atk_list[0].stars or 0, atk_th,
                                   (member_by_tag.get(atk_list[0].defender_tag) or member).town_hall_level or atk_th,
                                   False, False) if atk_list else 'no_attack'
            score, _, _ = get_war_verdict(lbl1, 'no_attack')
            ps['verdict_scores'].append(score)

    all_szn_ids = [s['season_id'] for s in seasons_data]

    player_list = []
    for tag, ps in player_stats.items():
        used     = ps['attacks_used']
        possible = ps['attacks_possible']
        ps['tag']             = tag
        ps['seasons']         = len(ps['seasons_set'])
        ps['avg_stars']       = round(ps['stars']       / used,    2) if used else 0.0
        ps['three_star_rate'] = round(ps['three_stars'] / used * 100) if used else 0
        ps['two_star_rate']   = round(ps['two_stars']   / used * 100) if used else 0
        ps['one_star_rate']   = round(ps['one_stars']   / used * 100) if used else 0
        ps['zero_star_rate']  = round(ps['zero_stars']  / used * 100) if used else 0
        ps['avg_destruction'] = round(ps['destruction_sum'] / used, 1) if used else 0.0
        ps['participation']   = round(used / possible * 100) if possible else 0
        vs = ps['verdict_scores']
        ps['avg_verdict']     = round(sum(vs) / len(vs), 1) if vs else 0.0
        ps['attacks_missed']  = possible - used

        # Longest consecutive season streak
        curr_str = max_str = 0
        for sid in all_szn_ids:
            if sid in ps['seasons_set']:
                curr_str += 1; max_str = max(max_str, curr_str)
            else:
                curr_str = 0
        ps['max_consecutive_seasons'] = max_str

        # Best single season
        best_avg, best_szn = 0.0, '—'
        for sid, sw in player_szn.get(tag, {}).items():
            if sw['attacks'] >= 3:
                avg = round(sw['stars'] / sw['attacks'], 2)
                if avg > best_avg:
                    best_avg = avg
                    best_szn = next((s['season_label'] for s in seasons_data if s['season_id'] == sid), '?')
        ps['best_season_label'] = best_szn
        ps['best_season_avg']   = best_avg

        del ps['seasons_set']
        player_list.append(ps)

    player_list.sort(key=lambda x: (-x['wars'], -x['avg_stars']))

    # Star contribution %
    total_cwl_stars = sum(p['stars'] for p in player_list)
    for p in player_list:
        p['star_contribution'] = round(p['stars'] / total_cwl_stars * 100, 1) if total_cwl_stars else 0.0

    # ── Season MVPs ───────────────────────────────────────────────────────────
    season_mvps = []
    for s in seasons_data:
        szn_map = {tag: player_szn[tag][s['season_id']]
                   for tag in player_szn if s['season_id'] in player_szn.get(tag, {})}
        if not szn_map:
            continue
        mvp_tag = max(szn_map, key=lambda t: (szn_map[t]['stars'], szn_map[t]['attacks']))
        p = next((x for x in player_list if x['tag'] == mvp_tag), None)
        if not p:
            continue
        sw = szn_map[mvp_tag]
        season_mvps.append({
            'season':    s['season_label'],
            'league':    s['league'],
            'lc':        s['league_class'],
            'finish':    s['finish'],
            'rank':      s['rank'],
            'name':      p['name'],
            'th':        p['th'],
            'stars':     sw['stars'],
            'attacks':   sw['attacks'],
            'wars':      sw['wars'],
            'avg_stars': round(sw['stars'] / sw['attacks'], 2) if sw['attacks'] else 0,
        })
    season_mvps.reverse()   # most recent first

    # ── Head-to-head records ──────────────────────────────────────────────────
    h2h = {}
    for war in our_ended_wars:
        our_side  = war.clan_tag == our_tag
        opp_tag   = war.opp_tag   if our_side else war.clan_tag
        opp_name  = war.opp_name  if our_side else war.clan_name
        if not opp_tag: continue
        rec = h2h.setdefault(opp_tag, {'name': opp_name or '?', 'wins': 0, 'losses': 0, 'draws': 0, 'wars': 0})
        rec['wars'] += 1
        result = _war_result(war, our_tag)
        if result == 'win':    rec['wins']   += 1
        elif result == 'loss': rec['losses'] += 1
        else:                  rec['draws']  += 1
    h2h_list = sorted(h2h.values(), key=lambda x: (-x['wars'], x['name']))[:12]

    # ── Hall of Fame ──────────────────────────────────────────────────────────
    min_wars = max(3, total_wars // 8)
    eligible = [p for p in player_list if p['wars'] >= min_wars] or player_list[:10]

    hof_veterans = sorted(player_list, key=lambda p: (-p['seasons'], -p['max_consecutive_seasons']))[:10]
    hof_ironman  = sorted(player_list, key=lambda p: (-p['participation'], -p['wars']))[:10]
    hof_stars    = sorted(player_list, key=lambda p: (-p['stars'],         -p['avg_stars']))[:10]
    hof_elite    = sorted(eligible,    key=lambda p: (-p['avg_stars'],     -p['wars']))[:10]

    # ── Chart data ────────────────────────────────────────────────────────────
    rank_dist_data    = [rank_dist.get(i, 0) for i in range(1, 9)]
    league_rank_js    = [s['league_rank']  for s in seasons_data]
    league_labels_js  = [s['season_label'] for s in seasons_data]
    league_names_js   = [s['league']       for s in seasons_data]
    season_winrate_js = [s['win_rate']     for s in seasons_data]
    season_stars_js   = [s['stars_for']    for s in seasons_data]
    season_stars_a_js = [s['stars_against'] for s in seasons_data]

    return render_template('cwl/cwl_stats.html',
        no_data             = False,
        our_tag             = our_tag,
        total_seasons       = total_seasons,
        total_wars          = total_wars,
        total_wins          = total_wins,
        total_losses        = total_losses,
        total_draws         = total_draws,
        total_stars_for     = total_stars_for,
        total_stars_against = total_stars_against,
        win_rate            = win_rate,
        avg_rank            = avg_rank,
        promotions          = promotions,
        relegations         = relegations,
        first_season        = seasons_data[0]['season_label'],
        latest_league       = seasons_data[-1]['league'],
        latest_lc           = seasons_data[-1]['league_class'],
        seasons_data        = seasons_data,
        season_mvps         = season_mvps,
        player_list         = player_list,
        h2h_list            = h2h_list,
        hof_veterans        = hof_veterans,
        hof_ironman         = hof_ironman,
        hof_stars           = hof_stars,
        hof_elite           = hof_elite,
        rank_dist_data      = rank_dist_data,
        league_rank_js      = league_rank_js,
        league_labels_js    = league_labels_js,
        league_names_js     = league_names_js,
        season_winrate_js   = season_winrate_js,
        season_stars_js     = season_stars_js,
        season_stars_a_js   = season_stars_a_js,
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
