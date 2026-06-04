import datetime as dt
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from extensions import db
from models import AppUser, Player, BattleLog, RankedWeek, UptimeTracker
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
