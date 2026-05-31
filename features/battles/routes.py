import datetime as dt

from flask import Blueprint, render_template, request
from sqlalchemy import func as sa_func
from sqlalchemy.orm import selectinload

from extensions import db
from models import BattleLog
from services.helpers import to_local

battles_bp = Blueprint('battles', __name__)


@battles_bp.route('/battles')
def battle_history_page():
    selected_type    = request.args.get('type', 'all')
    selected_week_str = request.args.get('week', None)

    now = dt.datetime.now(dt.timezone.utc)
    current_week_start = (now - dt.timedelta(days=now.weekday())).date()
    is_all_time = (selected_week_str == 'all')

    if not is_all_time:
        if selected_week_str:
            try:
                week_start = dt.date.fromisoformat(selected_week_str)
                week_start = week_start - dt.timedelta(days=week_start.weekday())
            except ValueError:
                week_start = current_week_start
        else:
            week_start = current_week_start
        week_end       = week_start + dt.timedelta(days=6)
        week_start_dt  = dt.datetime(week_start.year, week_start.month, week_start.day, tzinfo=dt.timezone.utc)
        next_monday_dt = week_start_dt + dt.timedelta(days=7)

    oldest = (
        BattleLog.query
        .filter(BattleLog.attack == True)
        .order_by(BattleLog.time.asc())
        .first()
    )
    available_weeks = []
    all_time_label  = 'All Time'
    if oldest and oldest.time:
        min_date   = oldest.time.date()
        min_monday = min_date - dt.timedelta(days=min_date.weekday())
        all_time_label = f"All Time – since {min_monday.strftime('%d.%m.%Y')}"
        w = min_monday
        while w <= current_week_start:
            wend = w + dt.timedelta(days=6)
            available_weeks.append({
                'start': w.isoformat(),
                'label': f"{w.strftime('%d.%m.%Y')} – {wend.strftime('%d.%m.%Y')}"
            })
            w += dt.timedelta(days=7)
        available_weeks.reverse()
        available_weeks.insert(0, {'start': 'all', 'label': all_time_label})

    if is_all_time:
        base_q = BattleLog.query.filter(BattleLog.attack == True)
    else:
        base_q = BattleLog.query.filter(
            BattleLog.attack == True,
            BattleLog.time >= week_start_dt,
            BattleLog.time < next_monday_dt,
        )
    if selected_type != 'all':
        base_q = base_q.filter(BattleLog.type == selected_type)

    attacks = base_q.options(selectinload(BattleLog.player)).all()

    first_log_time = dict(
        db.session.query(BattleLog.player_tag, sa_func.min(BattleLog.time))
        .group_by(BattleLog.player_tag)
        .all()
    )
    import_window = dt.timedelta(minutes=2)
    attacks = [
        b for b in attacks
        if not (b.time and first_log_time.get(b.player_tag) and
                b.time <= first_log_time[b.player_tag] + import_window)
    ]

    total_attacks = len(attacks)
    total_gold    = sum(b.loot_gold or 0 for b in attacks)
    total_elixir  = sum(b.loot_elixir or 0 for b in attacks)
    total_dark    = sum(b.loot_dark_elixir or 0 for b in attacks)

    player_map = {}
    for b in attacks:
        tag = b.player_tag
        if tag not in player_map:
            player_map[tag] = {
                'player_name': b.player.name if b.player else b.player_tag,
                'player_tag': tag,
                'in_clan': b.player.in_clan if b.player else True,
                'att_count': 0,
                'total_gold': 0, 'total_elixir': 0, 'total_dark': 0,
                'attack_logs': [],
            }
        s = player_map[tag]
        if b.player:
            s['player_name'] = b.player.name
            s['in_clan']     = b.player.in_clan
        stars = min(b.stars or 0, 3)
        s['att_count']    += 1
        s['total_gold']   += b.loot_gold or 0
        s['total_elixir'] += b.loot_elixir or 0
        s['total_dark']   += b.loot_dark_elixir or 0
        local_time = to_local(b.time)
        s['attack_logs'].append({
            'time':         local_time.strftime('%d.%m.%y %H:%M') if local_time else '–',
            'time_sort':    local_time.isoformat() if local_time else '',
            'opponent_tag': b.opponent_tag or '–',
            'type':         b.type or '–',
            'stars':        stars,
            'percentage':   b.percentage or 0,
            'gold':         b.loot_gold or 0,
            'elixir':       b.loot_elixir or 0,
            'dark':         b.loot_dark_elixir or 0,
        })

    player_data = sorted(player_map.values(), key=lambda x: x['att_count'], reverse=True)
    top_by_attacks = sorted(player_data, key=lambda x: x['att_count'], reverse=True)[:10]

    return render_template(
        'battles/battle_history.html',
        available_weeks=available_weeks,
        selected_week_start='all' if is_all_time else week_start.isoformat(),
        current_week_start=current_week_start.isoformat(),
        selected_type=selected_type,
        week_label=all_time_label if is_all_time else f"{week_start.strftime('%d.%m.%Y')} – {week_end.strftime('%d.%m.%Y')}",
        total_attacks=total_attacks,
        total_gold=total_gold,
        total_elixir=total_elixir,
        total_dark=total_dark,
        top_by_attacks=top_by_attacks,
        player_data=player_data,
    )
