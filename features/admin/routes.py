import datetime as dt
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from extensions import db
from models import AppUser, Player, BattleLog, RankedWeek, UptimeTracker, ClanWar, ClanWarMember, ClanWarAttack
from features.auth.routes import require_admin_login, require_super_admin

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin')
@require_admin_login
def admin_hub():
    days = request.args.get('days', 7, type=int)
    if days not in [1, 7, 14, 30]:
        days = 7

    now_naive = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    cutoff = now_naive - dt.timedelta(days=days)
    trackers = UptimeTracker.query.filter(
        UptimeTracker.time >= cutoff
    ).order_by(UptimeTracker.time.asc()).all()

    by_function = defaultdict(list)
    for t in trackers:
        try:
            dur = float(t.duration) if t.duration else 0.0
        except (ValueError, TypeError):
            dur = 0.0
        by_function[t.function].append({
            'time':          t.time.strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
            'duration':      dur,
            'status':        t.status or 'success',
            'summary':       t.summary or '',
            'error_message': t.error_message or '',
        })

    function_stats = {}

    for fn, runs in by_function.items():
        success_runs = [r for r in runs if r['status'] != 'skipped']
        durations    = [r['duration'] for r in success_runs]
        avg_dur = round(sum(durations) / len(durations), 2) if durations else 0
        max_dur = round(max(durations), 2) if durations else 0

        # Use only the most recent 20 successful runs for median gap so tasks
        # with dynamic scheduling (clan_war switches between 3 min and 60 min)
        # adapt quickly to their current mode instead of averaging across both.
        recent_success = success_runs[-20:] if len(success_runs) > 20 else success_runs

        gaps_minutes = []
        for i in range(1, len(recent_success)):
            t1 = dt.datetime.strptime(recent_success[i - 1]['time'], '%Y-%m-%dT%H:%M:%SZ')
            t2 = dt.datetime.strptime(recent_success[i]['time'],     '%Y-%m-%dT%H:%M:%SZ')
            gaps_minutes.append((t2 - t1).total_seconds() / 60)

        sorted_gaps = sorted(gaps_minutes)
        median_gap  = sorted_gaps[len(sorted_gaps) // 2] if sorted_gaps else None
        max_gap     = max(gaps_minutes) if gaps_minutes else None

        gap_events = []
        if median_gap and len(success_runs) > 1:
            for i in range(1, len(success_runs)):
                t1 = dt.datetime.strptime(success_runs[i - 1]['time'], '%Y-%m-%dT%H:%M:%SZ')
                t2 = dt.datetime.strptime(success_runs[i]['time'],     '%Y-%m-%dT%H:%M:%SZ')
                gap_min = (t2 - t1).total_seconds() / 60
                if gap_min > median_gap * 2.5:
                    gap_events.append({
                        'start':        success_runs[i - 1]['time'],
                        'end':          success_runs[i]['time'],
                        'duration_min': round(gap_min, 1),
                    })

        last_run  = runs[-1] if runs else None
        health    = 'unknown'
        minutes_since = None
        # Use last run of ANY status for the recency check — a recent skip still
        # proves the task is alive (e.g. raid_weekend skips on weekdays).
        if last_run:
            last_dt = dt.datetime.strptime(last_run['time'], '%Y-%m-%dT%H:%M:%SZ')
            minutes_since = round((now_naive - last_dt).total_seconds() / 60, 1)
            if median_gap:
                if minutes_since > median_gap * 2.5:
                    health = 'down'
                elif minutes_since > median_gap * 1.5:
                    health = 'warning'
                else:
                    health = 'up'
            else:
                health = 'up' if minutes_since < 120 else 'warning'

        error_count   = sum(1 for r in runs if r['status'] == 'error')
        skipped_count = sum(1 for r in runs if r['status'] == 'skipped')

        function_stats[fn] = {
            'count':          len(runs),
            'error_count':    error_count,
            'skipped_count':  skipped_count,
            'avg_duration':   avg_dur,
            'max_duration':   max_dur,
            'median_gap':     round(median_gap, 1) if median_gap else None,
            'max_gap':        round(max_gap, 1) if max_gap else None,
            'last_run':       last_run['time'] if last_run else None,
            'last_status':    last_run['status'] if last_run else None,
            'last_summary':   last_run['summary'] if last_run else None,
            'last_error':     last_run['error_message'] if last_run else None,
            'minutes_since':  minutes_since,
            'status':         health,
            'gap_events':     gap_events,
        }

    members = Player.query.filter_by(in_clan=True).order_by(Player.name).all()

    return render_template(
        'admin/admin_hub.html',
        by_function=dict(by_function),
        function_stats=function_stats,
        selected_days=days,
        members=members,
    )


@admin_bp.route('/admin/users')
@require_super_admin
def admin_users():
    users   = AppUser.query.order_by(AppUser.is_approved, AppUser.created_at.desc()).all()
    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
    return render_template('admin/admin_users.html', users=users, players=players)


@admin_bp.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@require_super_admin
def admin_user_approve(user_id):
    u = db.get_or_404(AppUser, user_id)
    u.is_approved = True
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/<int:user_id>/reject', methods=['POST'])
@require_super_admin
def admin_user_reject(user_id):
    u = db.get_or_404(AppUser, user_id)
    u.is_approved = False
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@require_super_admin
def admin_user_delete(user_id):
    u = db.get_or_404(AppUser, user_id)
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/admin/users/<int:user_id>/toggle-super', methods=['POST'])
@require_super_admin
def admin_user_toggle_super(user_id):
    u = db.get_or_404(AppUser, user_id)
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
@require_admin_login
def admin_members():
    players = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
    return render_template('admin/admin_members.html', players=players)


@admin_bp.route('/admin/members/<path:tag>/update', methods=['POST'])
@require_admin_login
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
    db.session.commit()
    return jsonify(ok=True)


@admin_bp.route('/debug')
def debug_dashboard():
    filter_tag = request.args.get('player_tag', default='').strip()
    sort_by = request.args.get('sort', default='tag')

    players_query = Player.query
    if filter_tag:
        search_term = f"%{filter_tag}%"
        players_query = players_query.filter(
            or_(Player.tag.ilike(search_term), Player.name.ilike(search_term))
        )

    if sort_by == 'name':
        players_query = players_query.order_by(Player.name.asc())
    elif sort_by == 'last_updated':
        players_query = players_query.order_by(Player.last_updated.desc())
    else:
        players_query = players_query.order_by(Player.tag.asc())

    players = players_query.options(
        selectinload(Player.ranked_weeks).selectinload(RankedWeek.battle_logs),
        selectinload(Player.battle_logs)
    ).all()

    selected_player = None
    battle_logs = []
    ranked_weeks = []
    if filter_tag:
        selected_player = db.session.get(Player, filter_tag)
        if not selected_player:
            selected_player = Player.query.filter(Player.tag.ilike(filter_tag)).first()
        if selected_player:
            battle_logs = (
                BattleLog.query
                .filter(BattleLog.player_tag == selected_player.tag)
                .order_by(BattleLog.time.desc())
                .limit(100)
                .all()
            )
            ranked_weeks = (
                RankedWeek.query
                .filter(RankedWeek.player_tag == selected_player.tag)
                .order_by(RankedWeek.start_day.desc())
                .all()
            )

    uptime_tracker_objs = UptimeTracker.query.order_by(UptimeTracker.time.desc()).limit(100).all()
    uptime_trackers = [
        {
            'id': t.id,
            'function': t.function,
            'time': t.time.isoformat() if t.time else None,
        }
        for t in uptime_tracker_objs
    ]

    return render_template(
        'admin/debug_dashboard.html',
        players=players,
        selected_player=selected_player,
        battle_logs=battle_logs,
        ranked_weeks=ranked_weeks,
        uptime_trackers=uptime_tracker_objs,
        uptime_trackers_json=uptime_trackers,
        current_tag=filter_tag,
        current_sort=sort_by,
    )


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
        war_size = math.ceil(eligible_count / 5) * 5 + 5
        fill_ups = war_size - eligible_count
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
