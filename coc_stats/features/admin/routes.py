import datetime as dt

import requests as req_lib

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort

from extensions import db
from models import AppUser, Player, UptimeTracker, ClanWar, ClanWarMember, ClanWarAttack, CWLBonus
from features.auth.routes import require_super_admin, _current_user
from features.admin import monitor_stats

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin')
@require_super_admin
def admin_hub():
    # Overview / command deck. Sync-health (nav_health / nav_task_status), newbie_check_count,
    # and pending_approvals arrive via the sitewide context processor — the Overview assembles
    # only the two figures the processor doesn't carry.
    return render_template(
        'admin/admin_overview.html',
        active_members=Player.query.filter_by(in_clan=True).count(),
        app_users=AppUser.query.count(),
        cwl_bonus=_cwl_bonus_available(),
    )


@admin_bp.route('/admin/monitor')
@require_super_admin
def admin_monitor():
    # Thin route: fetch the window, hand it to the pure aggregator. The
    # per-task maths, the cross-task incident correlation and the cause rollup
    # all live in features/admin/monitor_stats.py, where they are unit-tested.
    days = request.args.get('days', monitor_stats.DEFAULT_DAYS, type=int)
    if days not in monitor_stats.VALID_DAYS:
        days = monitor_stats.DEFAULT_DAYS

    now_naive = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    trackers = UptimeTracker.query.filter(
        UptimeTracker.time >= now_naive - dt.timedelta(days=days)
    ).order_by(UptimeTracker.time.asc()).all()

    return render_template(
        'admin/admin_monitor.html',
        page=monitor_stats.build_monitor_page(trackers, now_naive, days),
        selected_days=days,
        period_options=monitor_stats.VALID_DAYS,
    )


@admin_bp.route('/admin/roster')
@require_super_admin
def admin_roster():
    # Shell page — the war-roster / CWL-bonus decision tools each fetch their own
    # data via existing AJAX endpoints (/admin/war-roster, /admin/cwl-bonus[/*]).
    return render_template(
        'admin/admin_roster.html',
        current_month=dt.date.today().strftime('%Y-%m'),
    )


@admin_bp.route('/admin/insights')
@require_super_admin
def admin_insights():
    # Clan-analytics home. Five studies over the war, CWL, ranked and raid
    # tables, computed on load behind a data-version cache — they are
    # viewer-invariant, so there is nothing to gain from making the admin ask.
    from features.admin.insights import build_briefing
    return render_template('admin/admin_insights.html', **build_briefing())


@admin_bp.route('/admin/users')
@require_super_admin
def admin_users():
    users   = AppUser.query.order_by(AppUser.is_approved, AppUser.created_at.desc()).all()
    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()

    # Accounts may be linked to a player who has since left the clan. Those tags match
    # no in-clan option, so without this the select renders "None" and the next save
    # silently wipes a link nobody meant to touch. Passed separately (not merged into
    # `players`) so the template can present them as their own category.
    in_clan_tags = {p.tag for p in players}
    orphan_tags  = {u.linked_player_tag for u in users if u.linked_player_tag} - in_clan_tags
    departed_linked = (
        Player.query.filter(Player.tag.in_(orphan_tags)).order_by(Player.name).all()
        if orphan_tags else []
    )

    return render_template(
        'admin/admin_users.html',
        users=users, players=players, departed_linked=departed_linked,
    )


@admin_bp.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@require_super_admin
def admin_user_approve(user_id):
    u = db.get_or_404(AppUser, user_id)
    u.is_approved = True
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


def _is_self(user_id):
    """Locking yourself out is the one mistake this page can't undo for you.
    The template disables these controls on your own row; this is the same rule
    enforced server-side, so a stale page or a direct POST can't get around it."""
    me = _current_user()
    return bool(me and me.id == user_id)


@admin_bp.route('/admin/users/<int:user_id>/reject', methods=['POST'])
@require_super_admin
def admin_user_reject(user_id):
    if _is_self(user_id):
        abort(400, 'You cannot revoke your own access.')
    u = db.get_or_404(AppUser, user_id)
    u.is_approved = False
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@require_super_admin
def admin_user_delete(user_id):
    if _is_self(user_id):
        abort(400, 'You cannot delete your own account.')
    u = db.get_or_404(AppUser, user_id)
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/<int:user_id>/toggle-super', methods=['POST'])
@require_super_admin
def admin_user_toggle_super(user_id):
    u = db.get_or_404(AppUser, user_id)
    if u.is_super_admin and _is_self(user_id):
        abort(400, 'You cannot remove your own super admin.')
    u.is_super_admin = not u.is_super_admin
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/<int:user_id>/perms', methods=['POST'])
@require_super_admin
def admin_user_perms(user_id):
    u = db.get_or_404(AppUser, user_id)
    u.perm_create_reminder_ranked = 'perm_create_reminder_ranked' in request.form
    u.perm_clan_war_edits         = 'perm_clan_war_edits'         in request.form
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/<int:user_id>/link-player', methods=['POST'])
@require_super_admin
def admin_user_link_player(user_id):
    u = db.get_or_404(AppUser, user_id)
    tag = request.form.get('linked_player_tag', '').strip() or None
    if tag is not None:
        exists = Player.query.filter_by(tag=tag).first()
        if not exists:
            tag = None
    u.linked_player_tag = tag
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/members')
@require_super_admin
def admin_members():
    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
    return render_template('admin/admin_members.html', players=players)


from tasks import TaskBusyError

_TRIGGERABLE_TASKS = {
    'task_update_battle_logs':  ('tasks.battle_logs',  'task_update_battle_logs'),
    'task_update_ranked_weeks': ('tasks.ranked_weeks', 'task_update_ranked_weeks'),
    'task_update_clan_members': ('tasks.clan_members', 'task_update_clan_members'),
    'task_update_raid_weekend': ('tasks.raid_weekend', 'task_update_raid_weekend'),
    'task_update_clan_war':     ('tasks.clan_war',     'task_update_clan_war'),
    'task_update_cwl':          ('tasks.cwl',          'task_update_cwl'),
}


@admin_bp.route('/admin/trigger-task', methods=['POST'])
@require_super_admin
def admin_trigger_task():
    import importlib
    task_name = (request.get_json() or {}).get('task')
    if task_name not in _TRIGGERABLE_TASKS:
        return jsonify(ok=False, error='Unknown task'), 400
    try:
        module_path, fn_name = _TRIGGERABLE_TASKS[task_name]
        mod = importlib.import_module(module_path)
        getattr(mod, fn_name)()
        return jsonify(ok=True)
    except TaskBusyError:
        return jsonify(ok=False, busy=True, error='Task is already running — try again in a moment.'), 409
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


# ── CWL Bonus ─────────────────────────────────────────────────────────────────

def _shift_month(m, delta):
    y, mo = map(int, m.split('-'))
    mo += delta
    while mo > 12: mo -= 12; y += 1
    while mo < 1:  mo += 12; y -= 1
    return f'{y}-{mo:02d}'


@admin_bp.route('/admin/cwl-bonus', methods=['GET'])
@require_super_admin
def admin_cwl_bonus_list():
    from sqlalchemy import func
    from models import CWLSeason, CWLWar, CWLMember, CWLAttack
    from app import CLAN_TAG

    current_month = dt.date.today().strftime('%Y-%m')
    candidate_months = [_shift_month(current_month, i) for i in range(-3, 2)]  # -3,-2,-1,0,+1

    # A calendar month can have 2 CWL seasons (Supercell schedule shifts), and CoC's API may key
    # a season with a longer string (e.g. '2026-06-02') instead of reusing plain 'YYYY-MM'. Resolve
    # each candidate month to whichever season key(s) actually exist, falling back to the bare
    # 'YYYY-MM' placeholder only when nothing was ever recorded for that month — otherwise months
    # whose real key is the long form end up with a second, always-empty 'YYYY-MM' column too.
    matching_seasons = (CWLSeason.query
                        .filter(db.or_(*[db.or_(CWLSeason.season == m, CWLSeason.season.like(f'{m}-%'))
                                          for m in candidate_months]))
                        .all())
    seasons_by_cal_month = {}
    for s in matching_seasons:
        seasons_by_cal_month.setdefault(s.season[:7], []).append(s.season)

    months = []
    for m in candidate_months:
        months.extend(sorted(seasons_by_cal_month.get(m, [m])))
    months.sort()   # 'YYYY-MM' sorts right before its same-month 'YYYY-MM-DD...' extra keys

    members = Player.query.filter_by(in_clan=True).order_by(Player.name).all()

    # All bonuses for all months in one query
    all_bonuses = CWLBonus.query.filter(CWLBonus.month.in_(months)).all()
    bonus_set = {(b.player_tag, b.month) for b in all_bonuses}

    # CWL stats per month
    month_stats = {}     # month -> { player_tag -> {stars, attacks, max_attacks} }
    season_states = {}   # month -> CWLSeason.state
    month_war_ids = {}   # month -> [war_id, ...]
    month_total_wars = {}   # month -> total wars in the season (for "flawless" = full participation)
    for month in months:
        season = CWLSeason.query.filter_by(season=month).first()
        if not season:
            continue
        season_states[month] = season.state
        season_wars = [w for w in CWLWar.query.filter_by(season_id=season.id).all()
                       if w.clan_tag == CLAN_TAG or w.opp_tag == CLAN_TAG]
        if not season_wars:
            continue
        war_ids = [w.id for w in season_wars]
        month_war_ids[month] = war_ids
        # "Flawless" requires attacking every war that's actually happened so far — a future war
        # still in 'preparation' hasn't given anyone a chance to attack yet, so it must not count.
        month_total_wars[month] = sum(1 for w in season_wars if w.state in ('inWar', 'warEnded'))

        max_rows = (db.session.query(CWLMember.player_tag, func.count(CWLMember.id))
                    .filter(CWLMember.war_id.in_(war_ids),
                            CWLMember.clan_tag == CLAN_TAG)
                    .group_by(CWLMember.player_tag).all())
        max_atk_map = {tag: cnt for tag, cnt in max_rows}
        if not max_atk_map:
            continue

        atk_rows = (db.session.query(CWLAttack.attacker_tag, func.count(CWLAttack.id))
                    .filter(CWLAttack.war_id.in_(war_ids),
                            CWLAttack.attacker_tag.in_(list(max_atk_map)))
                    .group_by(CWLAttack.attacker_tag).all())
        atk_map = {tag: cnt for tag, cnt in atk_rows}

        star_rows = (db.session.query(CWLAttack.attacker_tag, func.sum(CWLAttack.stars))
                     .filter(CWLAttack.war_id.in_(war_ids),
                             CWLAttack.attacker_tag.in_(list(max_atk_map)))
                     .group_by(CWLAttack.attacker_tag).all())
        stars_map = {tag: int(s or 0) for tag, s in star_rows}

        month_stats[month] = {
            tag: {
                'stars':       stars_map.get(tag, 0),
                'attacks':     atk_map.get(tag, 0),
                'max_attacks': max_atk_map[tag],
            } for tag in max_atk_map
        }

    # Active CWL period = most recent season that isn't finished yet; falls back to the
    # literal calendar month (even with no data) so the UI behaves as before in normal months.
    active_month = current_month
    for m in reversed(months):
        if season_states.get(m) and season_states[m] != 'ended':
            active_month = m
            break

    # Map positions from the active month's CWL (min across war days = consistent position)
    cwl_pos_map = {}
    if month_war_ids.get(active_month):
        pos_rows = (db.session.query(CWLMember.player_tag, func.min(CWLMember.map_position))
                    .filter(CWLMember.war_id.in_(month_war_ids[active_month]),
                            CWLMember.clan_tag == CLAN_TAG)
                    .group_by(CWLMember.player_tag).all())
        cwl_pos_map = {tag: pos for tag, pos in pos_rows if pos is not None}
        

    return jsonify(
        months=months,
        current_month=active_month,
        members=[{
            'tag':  p.tag,
            'name': p.name or p.tag,
            'ranked_league': p.league_tier,
            'league': p.league_tier,
            'cwl_pos': cwl_pos_map.get(p.tag),
            'by_month': {
                m: {
                    'has_bonus':   (p.tag, m) in bonus_set,
                    'in_cwl':      p.tag in month_stats.get(m, {}),
                    'stars':       month_stats.get(m, {}).get(p.tag, {}).get('stars', 0),
                    'attacks':     month_stats.get(m, {}).get(p.tag, {}).get('attacks', 0),
                    'max_attacks': month_stats.get(m, {}).get(p.tag, {}).get('max_attacks', 0),
                    'total_wars':  month_total_wars.get(m, 0),
                } for m in months
            },
        } for p in members],
    )


# Guaranteed bonuses by (league_group, war_size) — None = N/A
_GUARANTEED_BONUSES = {
    'bronze_silver': {5: 0, 15: 1, 30: 2},
    'gold_crystal':  {5: 0, 15: 2, 30: 4},
    'master':        {5: 1, 15: 3, 30: 6},
    'champion':      {5: None, 15: 4, 30: None},
}

def _cwl_league_group(league_name):
    if not league_name:
        return 'bronze_silver'
    n = league_name.lower()
    if 'champion' in n:
        return 'champion'
    if 'master' in n:
        return 'master'
    if 'crystal' in n or 'gold' in n:
        return 'gold_crystal'
    return 'bronze_silver'

def _normalize_war_size(team_size):
    if not team_size or team_size <= 7:  return 5
    if team_size <= 20:                   return 15
    return 30


def _cwl_bonus_available():
    """Overview alert tile: how many bonus slots remain unassigned in the active CWL season.
    available = (guaranteed-by-league/size + wins) − already-assigned. Needs no per-player
    data. Returns {'count', 'season_label'} or None when there is no active season / N/A league."""
    try:
        from models import CWLSeason, CWLWar
        from app import CLAN_TAG

        # Active season = most recent season that hasn't ended yet (matches admin_cwl_bonus_list).
        recent = CWLSeason.query.order_by(CWLSeason.season.desc()).limit(8).all()
        season = next((s for s in recent if s.state and s.state != 'ended'), None)
        if not season:
            return None

        wars = [w for w in CWLWar.query.filter_by(season_id=season.id).all()
                if w.clan_tag == CLAN_TAG or w.opp_tag == CLAN_TAG]
        if not wars:
            return None

        war_size = _normalize_war_size(wars[0].team_size)
        league_name = season.league_name
        if not league_name:
            our_war = next((w for w in wars if w.clan_tag == CLAN_TAG), None) or wars[0]
            league_name = (our_war.clan_cwl_league if our_war.clan_tag == CLAN_TAG
                           else our_war.opp_cwl_league) or ''

        guaranteed = _GUARANTEED_BONUSES.get(_cwl_league_group(league_name), {}).get(war_size)
        if guaranteed is None:
            return None

        wins = 0
        for w in wars:
            if w.state != 'warEnded':
                continue
            if w.clan_tag == CLAN_TAG:
                our_s, opp_s = w.clan_stars or 0, w.opp_stars or 0
                our_p, opp_p = float(w.clan_destruction_pct or 0), float(w.opp_destruction_pct or 0)
            else:
                our_s, opp_s = w.opp_stars or 0, w.clan_stars or 0
                our_p, opp_p = float(w.opp_destruction_pct or 0), float(w.clan_destruction_pct or 0)
            if our_s > opp_s or (our_s == opp_s and our_p > opp_p):
                wins += 1

        already   = CWLBonus.query.filter_by(month=season.season).count()
        available = max(0, (guaranteed + wins) - already)
        return {'count': available, 'season_label': season.season}
    except Exception:
        return None


@admin_bp.route('/admin/cwl-bonus/suggest', methods=['POST'])
@require_super_admin
def admin_cwl_bonus_suggest():
    from sqlalchemy import func
    from models import CWLSeason, CWLWar, CWLMember, CWLAttack
    from app import CLAN_TAG
    import traceback

    try:
        return _cwl_bonus_suggest_inner(func, CWLSeason, CWLWar, CWLMember, CWLAttack, CLAN_TAG)
    except Exception as e:
        return jsonify(ok=False, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()), 500


def _cwl_bonus_suggest_inner(func, CWLSeason, CWLWar, CWLMember, CWLAttack, CLAN_TAG):
    data  = request.get_json() or {}
    month = data.get('month', dt.date.today().strftime('%Y-%m'))

    season = CWLSeason.query.filter_by(season=month).first()
    if not season:
        return jsonify(ok=False, error='No CWL season found for this month.'), 404

    wars = [w for w in CWLWar.query.filter_by(season_id=season.id).all()
            if w.clan_tag == CLAN_TAG or w.opp_tag == CLAN_TAG]
    if not wars:
        return jsonify(ok=False, error='No CWL wars found for this clan this month.'), 404

    war_ids  = [w.id for w in wars]
    war_size = _normalize_war_size(wars[0].team_size)

    # League name: prefer season record, fall back to our clan's war record
    league_name = season.league_name
    if not league_name:
        our_war = next((w for w in wars if w.clan_tag == CLAN_TAG), None) or wars[0]
        league_name = (our_war.clan_cwl_league if our_war.clan_tag == CLAN_TAG
                       else our_war.opp_cwl_league) or ''

    league_grp = _cwl_league_group(league_name)
    guaranteed = _GUARANTEED_BONUSES.get(league_grp, {}).get(war_size)
    if guaranteed is None:
        return jsonify(ok=False, error=f'Guaranteed bonus is N/A for {league_name or "unknown league"} {war_size}v{war_size}.'), 400

    # Count wins
    wins = 0
    for w in wars:
        if w.state != 'warEnded':
            continue
        if w.clan_tag == CLAN_TAG:
            our_s, opp_s = w.clan_stars or 0, w.opp_stars or 0
            our_p, opp_p = float(w.clan_destruction_pct or 0), float(w.opp_destruction_pct or 0)
        else:
            our_s, opp_s = w.opp_stars or 0, w.clan_stars or 0
            our_p, opp_p = float(w.opp_destruction_pct or 0), float(w.clan_destruction_pct or 0)
        if our_s > opp_s or (our_s == opp_s and our_p > opp_p):
            wins += 1

    total_bonuses = guaranteed + wins

    # Participants
    max_rows = (db.session.query(CWLMember.player_tag, func.count(CWLMember.id))
                .filter(CWLMember.war_id.in_(war_ids),
                        CWLMember.clan_tag == CLAN_TAG)
                .group_by(CWLMember.player_tag).all())
    max_atk_map  = {tag: cnt for tag, cnt in max_rows}
    participants = list(max_atk_map.keys())

    # Stars + attacks
    perf_rows = (db.session.query(
                     CWLAttack.attacker_tag,
                     func.sum(CWLAttack.stars),
                     func.sum(CWLAttack.destruction_pct),
                     func.count(CWLAttack.id),
                 )
                 .filter(CWLAttack.war_id.in_(war_ids), CWLAttack.attacker_tag.in_(participants))
                 .group_by(CWLAttack.attacker_tag).all())
    stars_map, destruction_map, atk_map = {}, {}, {}
    for tag, s, d, c in perf_rows:
        stars_map[tag]       = int(s or 0)
        destruction_map[tag] = float(d or 0)
        atk_map[tag]         = c

    current_bonuses = {b.player_tag for b in CWLBonus.query.filter_by(month=month).all()}
    player_map      = {p.tag: p.name or p.tag
                       for p in Player.query.filter(Player.tag.in_(participants)).all()}

    # Last bonus month per participant (across all time)
    last_bonus_rows = (db.session.query(CWLBonus.player_tag, func.max(CWLBonus.month))
                       .filter(CWLBonus.player_tag.in_(participants),
                               CWLBonus.month != month)   # exclude current month
                       .group_by(CWLBonus.player_tag).all())
    last_bonus_map = {tag: m for tag, m in last_bonus_rows}

    # Count actual elapsed CWL seasons, not calendar months — some months run two CWL groups
    # (e.g. '2026-06' and '2026-06-16'), so a plain month-number diff would undercount how many
    # seasons separate a player's last bonus from the current one. A gap of 1 means their last
    # bonus was the immediately preceding season ("last CWL"); it can never be 0, since the
    # current season's own bonuses are excluded from the "last bonus" lookup above.
    #
    # CWLSeason only retains recent rotations (old ones get cleaned up), so it alone can't place
    # older bonus months in order. CWLBonus.month covers full history but only at coarse monthly
    # granularity. Union both — the keys sort correctly together either way ('2026-06' < '2026-06-16'),
    # so this gives a complete, correctly-ordered season list even past CWLSeason's retention window.
    season_rows  = {s.season for s in CWLSeason.query.all()}
    bonus_months = {m for (m,) in db.session.query(CWLBonus.month).distinct().all()}
    all_seasons  = sorted(season_rows | bonus_months | {month})
    season_index = {s: i for i, s in enumerate(all_seasons)}
    current_idx  = season_index.get(month)

    def _months_ago(last_month):
        if not last_month:
            return None
        if current_idx is not None and last_month in season_index:
            return current_idx - season_index[last_month]
        y, mo = last_month.split('-')[:2]
        cy, cmo = month.split('-')[:2]
        return (int(cy) - int(y)) * 12 + (int(cmo) - int(mo))

    # "Flawless" requires attacking every war that's actually happened so far this season — a
    # future war still in 'preparation' hasn't given anyone a chance to attack yet, so it must
    # not count toward the denominator (otherwise nobody could ever be flawless mid-season).
    total_wars = sum(1 for w in wars if w.state in ('inWar', 'warEnded'))
    participant_list = [{
        'tag':         tag,
        'name':        player_map.get(tag, tag),
        'stars':       stars_map.get(tag, 0),
        'destruction': round(destruction_map.get(tag, 0), 1),
        'attacks':     atk_map.get(tag, 0),
        'max_attacks': max_atk_map.get(tag, 0),
        'total_wars':  total_wars,
        'has_bonus':   tag in current_bonuses,
        'last_bonus':  last_bonus_map.get(tag),
        'months_ago':  _months_ago(last_bonus_map.get(tag)),
    } for tag in participants]

    # Sort: eligible first, then by longest without bonus (None = never → oldest date → newest)
    # Tiebreak: more stars first
    eligible = [p for p in participant_list if not p['has_bonus'] and p['attacks'] >= p['max_attacks']]
    eligible.sort(key=lambda p: (
        p['last_bonus'] or '',   # '' sorts before any YYYY-MM → never bonused first
        -p['stars'],
        -p['destruction'],
    ))

    already   = len(current_bonuses)
    available = max(0, total_bonuses - already)
    selected  = eligible[:available]

    def _reason(p):
        if p['last_bonus'] is None:
            return 'No bonus on record'
        ma = p['months_ago']
        if ma == 1:
            return f"Last bonus last CWL ({p['last_bonus']})"
        return f"Last bonus {ma} CWLs ago ({p['last_bonus']})"

    suggested_tags    = [p['tag'] for p in selected]
    suggested_details = [{'tag': p['tag'], 'name': p['name'], 'stars': p['stars'],
                          'attacks': p['attacks'], 'max_attacks': p['max_attacks'],
                          'total_wars': p['total_wars'], 'reason': _reason(p)}
                         for p in selected]

    return jsonify(
        ok=True,
        wins=wins,
        guaranteed=guaranteed,
        total_bonuses=total_bonuses,
        already_given=already,
        available=available,
        league=league_name or '?',
        war_size=war_size,
        suggested_tags=suggested_tags,
        suggested_details=suggested_details,
        participants=participant_list,
    )


@admin_bp.route('/admin/cwl-bonus/apply', methods=['POST'])
@require_super_admin
def admin_cwl_bonus_apply():
    data  = request.get_json() or {}
    month = data.get('month', '')
    tags  = data.get('tags', [])
    if not month or not tags:
        return jsonify(ok=False, error='Missing month or tags'), 400
    added = 0
    for tag in tags:
        if not CWLBonus.query.filter_by(player_tag=tag, month=month).first():
            db.session.add(CWLBonus(player_tag=tag, month=month))
            added += 1
    db.session.commit()
    return jsonify(ok=True, added=added)


@admin_bp.route('/admin/cwl-bonus/toggle', methods=['POST'])
@require_super_admin
def admin_cwl_bonus_toggle():
    data = request.get_json() or {}
    tag   = data.get('player_tag', '').strip()
    month = data.get('month', '').strip()
    if not tag or not month:
        return jsonify(ok=False, error='Missing player_tag or month'), 400
    existing = CWLBonus.query.filter_by(player_tag=tag, month=month).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify(ok=True, added=False)
    db.session.add(CWLBonus(player_tag=tag, month=month))
    db.session.commit()
    return jsonify(ok=True, added=True)


@admin_bp.route('/admin/members/<path:tag>/update', methods=['POST'])
@require_super_admin
def admin_member_update(tag):
    player = db.get_or_404(Player, tag)
    data = request.get_json()
    if 'admin_comment' in data:
        player.admin_comment = data['admin_comment'].strip() or None
    if 'in_group_chat' in data:
        player.in_group_chat = bool(data['in_group_chat'])
    if 'war_preference_custom' in data:
        v = data['war_preference_custom']
        player.war_preference_custom = v if v in ('in', 'out') else None
    if 'newbie_check' in data:
        player.newbie_check = bool(data['newbie_check'])
    db.session.commit()
    return jsonify(ok=True)


# ── New Member Evaluation ─────────────────────────────────────────────────────

# (min_th, pass_threshold, warn_threshold) — evaluated top-down, first match wins
_WAR_STARS_BRACKETS   = [(18, 300, 200), (17, 250, 150), (16, 150, 75), (15, 100, 50), (13, 50, 10) , (0, 50, 10)]
_DONATIONS_BRACKETS   = [(14, 2000, 500), (13, 1000, 200), (0, 0, 0)]
_ATTACK_WINS_BRACKETS = [(18, 3000, 2000), (17, 2000, 1000), (15, 1000, 400), (13, 500, 200), (0, 500, 200)]

def _th_threshold(th, brackets):
    for min_th, good, warn in brackets:
        if th >= min_th:
            return good, warn
    return brackets[-1][1], brackets[-1][2]


def _evaluate_player_data(data):
    """Given raw CoC API player dict, return evaluation dict (checks + verdict + heroes)."""
    from services.helpers import EXPECTED_LEAGUE_RANK, _get_league_rank, get_name_to_id, hero_th_max, compute_hero_pct

    th_level    = data.get('townHallLevel', 0)
    league_icon = ((data.get('league') or {}).get('iconUrls') or {}).get('small', '')

    # Heroes — percentage of TH-appropriate max levels
    heroes_raw = [h for h in (data.get('heroes') or []) if h.get('village') == 'home']
    heroes = [
        {'name': h.get('name', ''), 'level': h.get('level', 0),
         'max_level': hero_th_max(h.get('name', ''), th_level) or h.get('maxLevel', 1)}
        for h in heroes_raw
    ]
    hero_pct = compute_hero_pct(heroes_raw, th_level)

    # Lifetime stats from achievements
    ach_map         = {a['name']: a.get('value', 0) for a in (data.get('achievements') or [])}
    war_stars_val   = ach_map.get('War Hero',      data.get('warStars', 0))
    donations_val   = ach_map.get('Friend in Need', data.get('donations', 0))
    attack_wins_val = ach_map.get('Conqueror',      data.get('attackWins', 0))

    # Ranked league — compare against TH-expected rank
    league_tier_raw = data.get('leagueTier') or {}
    league_tier_id  = league_tier_raw.get('id')
    ranked_name     = get_name_to_id(league_tier_id) if league_tier_id else None
    player_rank     = _get_league_rank(ranked_name) if ranked_name else 0
    expected_rank   = EXPECTED_LEAGUE_RANK.get(th_level, 1)
    expected_name   = get_name_to_id(105000000 + expected_rank)

    def chk(value, good, warn, label, fmt):
        status = 'pass' if value >= good else ('warn' if value >= warn else 'fail')
        return {'status': status, 'label': label, 'detail': fmt(value)}

    war_good, war_warn = _th_threshold(th_level, _WAR_STARS_BRACKETS)
    don_good, don_warn = _th_threshold(th_level, _DONATIONS_BRACKETS)
    atk_good, atk_warn = _th_threshold(th_level, _ATTACK_WINS_BRACKETS)

    rank_diff   = player_rank - expected_rank
    rank_status = 'pass' if rank_diff >= 3 else ('warn' if rank_diff >= 0 else 'fail')

    checks = [
        chk(hero_pct,        75,       50,       'Heroes',       lambda v: f'{v}% of TH max'),
        chk(war_stars_val,   war_good, war_warn,  'War Stars',   lambda v: f'{v:,} (need {war_good})'),
        chk(donations_val,   don_good, don_warn,  'Donations',   lambda v: f'{v:,} (need {don_good})'),
        chk(attack_wins_val, atk_good, atk_warn,  'Attack Wins', lambda v: f'{v:,} (need {atk_good})'),
        {
            'status': rank_status,
            'label':  'Ranked League',
            'detail': f'{ranked_name or "Unranked"} (expected ≥ {expected_name})',
        },
    ]

    passes = sum(1 for c in checks if c['status'] == 'pass')
    fails  = sum(1 for c in checks if c['status'] == 'fail')
    if fails == 0:
        verdict = 'accept'
    elif fails >= 2:
        verdict = 'decline'
    elif passes <= 1:
        verdict = 'decline'
    else:
        verdict = 'consider'

    return dict(
        th=th_level,
        ranked_league=ranked_name,
        league_icon=league_icon,
        heroes=heroes, hero_pct=hero_pct,
        checks=checks, verdict=verdict,
    )


@admin_bp.route('/admin/evaluate-new-members', methods=['POST'])
@require_super_admin
def admin_evaluate_new_members():
    from services.api import api_fetch_player_data

    new_members = Player.query.filter(
        Player.in_clan == True,
        Player.newbie_check == False,
    ).order_by(Player.join_date.desc()).all()

    results = []
    for player in new_members:
        try:
            data = api_fetch_player_data(player.tag)
            ev   = _evaluate_player_data(data)
            results.append({
                'name':      data.get('name', player.name or player.tag),
                'tag':       player.tag,
                'join_date': player.join_date.strftime('%d.%m.%Y') if player.join_date else '?',
                'days_ago':  (dt.date.today() - player.join_date).days if player.join_date else '?',
                **ev,
            })
        except RuntimeError as e:
            results.append({
                'name': player.name or player.tag,
                'tag':  player.tag,
                'join_date': player.join_date.strftime('%d.%m.%Y') if player.join_date else '?',
                'days_ago': (dt.date.today() - player.join_date).days if player.join_date else '?',
                'error': str(e),
            })

    _verdict_order = {'decline': 0, 'consider': 1, 'accept': 2}
    results.sort(key=lambda r: (
        _verdict_order.get(r.get('verdict'), 1),
        -sum(1 for c in r.get('checks', []) if c.get('status') == 'fail'),
    ))

    return jsonify(results=results, count=len(results))


# ── CWL Roster Recommendation ─────────────────────────────────────────────────

def _player_war_stats(player_tag):
    """Return (war_score 0-100, war_skill 0-100, wars_participated) using the last month's data."""
    import datetime as dt
    from features.player.routes import calculate_activity_score, calculate_skill_score
    from models import ClanWar, ClanWarMember
    act   = calculate_activity_score(player_tag, period='month')
    skill = calculate_skill_score(player_tag, period='month')
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).replace(tzinfo=None)
    wars_participated = (ClanWarMember.query
                         .join(ClanWar, ClanWarMember.clan_war_id == ClanWar.id)
                         .filter(ClanWarMember.player_tag == player_tag,
                                 ClanWarMember.is_opponent == False,
                                 ClanWar.state == 'warEnded',
                                 ClanWar.start_time >= cutoff)
                         .count())
    return act.get('war_score', 0), skill.get('war_skill', 0), wars_participated


@admin_bp.route('/admin/war-roster', methods=['POST'])
@require_super_admin
def admin_war_roster():
    import math
    auto_mode = request.form.get('war_size', '') == 'auto'
    war_size_raw = request.form.get('war_size', 15)
    fill_ups_raw = request.form.get('fill_ups', 5)
    war_size = None if auto_mode else max(5, min(50, round(int(war_size_raw) / 5) * 5))
    fill_ups = None  # computed below for both modes

    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()

    enriched = []
    for p in players:
        war_score, war_skill, war_count = _player_war_stats(p.tag)
        enriched.append({
            'tag':        p.tag,
            'name':       p.name,
            'th':         p.current_th or 0,
            'war_pref':   p.war_preference_custom,
            'war_score':  war_score,
            'verdict':    war_skill,
            'war_count':  war_count,
            'league':     p.league_tier or '',
        })

    def _composite(p):
        return (p['war_score'] ** 1.5 * p['verdict'] ** 0.6) / (100 ** 1.1)

    def _opted_out(p):
        return p['war_pref'] == 'out'

    def _is_eligible(p):
        if _opted_out(p):
            return False
        return _composite(p) >= 50 or (p['war_pref'] == 'in' and p['war_count'] < 5)

    eligible = [p for p in enriched if _is_eligible(p)]

    if auto_mode:
        eligible_count = len(eligible)
        non_eligible   = [p for p in enriched if not _is_eligible(p)]
        ceil_size      = min(50, math.ceil(eligible_count / 5) * 5)
        fill_needed    = ceil_size - eligible_count
        if fill_needed <= len(non_eligible):
            war_size = ceil_size
            fill_ups = fill_needed
        else:
            war_size = min(50, math.floor(eligible_count / 5) * 5)
            fill_ups = 0
    else:
        fill_ups = max(0, min(war_size, int(fill_ups_raw)))

    selected_tags = set()
    main_spots = war_size - fill_ups

    # Step 1a — pref='in' AND < 5 wars: sparse override, sorted by composite DESC then TH
    main_roster = []
    for p in sorted([p for p in eligible if p['war_pref'] == 'in' and p['war_count'] < 5],
                    key=lambda p: (-_composite(p), -p['th'])):
        if len(main_roster) >= main_spots:
            break
        main_roster.append({**p, 'reason': 'Sparse data (<5 wars)'})
        selected_tags.add(p['tag'])

    # Step 1b — pref='in' AND eligible: picked by composite DESC, capped at main_spots
    for p in sorted([p for p in eligible if p['war_pref'] == 'in' and p['tag'] not in selected_tags],
                    key=lambda p: (-_composite(p), -p['th'])):
        if len(main_roster) >= main_spots:
            break
        main_roster.append({**p, 'reason': 'War pref: In'})
        selected_tags.add(p['tag'])

    # Step 2 — remaining eligible spots by composite DESC, TH DESC
    main_spots_left = main_spots - len(main_roster)
    for p in sorted([p for p in eligible if p['tag'] not in selected_tags],
                    key=lambda p: (-_composite(p), -p['th'])):
        if main_spots_left <= 0:
            break
        main_roster.append({**p, 'reason': f'Score: {round(_composite(p))}'})
        selected_tags.add(p['tag'])
        main_spots_left -= 1

    # Step 3 — fill-ups: lowest THs from whoever is not yet selected
    fill_up_list = sorted(
        [p for p in enriched if p['tag'] not in selected_tags],
        key=lambda p: (p['th'], p['name'])
    )[:fill_ups]
    for p in fill_up_list:
        selected_tags.add(p['tag'])

    roster = (
        [{**p, 'role': p['reason']} for p in main_roster] +
        [{**p, 'role': 'Fill-up'}   for p in fill_up_list]
    )

    bench = sorted(
        [p for p in enriched if p['tag'] not in selected_tags],
        key=lambda p: (-p['verdict'], -p['th'])
    )

    pref_in_count  = sum(1 for p in main_roster if p['reason'] == 'War pref: In')
    score_count    = len(main_roster) - pref_in_count
    eligible_count = len(eligible)

    return jsonify(
        roster=roster, bench=bench,
        war_size=war_size, fill_ups=len(fill_up_list),
        main_picks=len(main_roster),
        pref_in_count=pref_in_count,
        score_count=score_count,
        eligible_count=eligible_count,
        auto=auto_mode,
    )



