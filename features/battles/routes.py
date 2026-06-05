import datetime as dt
import json
from collections import defaultdict

from flask import Blueprint, render_template, request
from sqlalchemy import func as sa_func
from sqlalchemy.orm import selectinload

from extensions import db
from models import BattleLog, Player
from services.helpers import to_local, LOCAL_TZ

battles_bp = Blueprint('battles', __name__)


@battles_bp.route('/battles')
def battle_history_page():
    selected_type    = request.args.get('type', 'all')
    selected_week_str = request.args.get('week', None)

    now_local = dt.datetime.now(LOCAL_TZ)
    current_week_start = (now_local - dt.timedelta(days=now_local.weekday())).date()
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
        week_start_dt  = dt.datetime(week_start.year, week_start.month, week_start.day, tzinfo=LOCAL_TZ)\
            .astimezone(dt.timezone.utc).replace(tzinfo=None)
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


@battles_bp.route('/battles/stats')
def battle_stats_page():
    clan_players    = Player.query.filter_by(in_clan=True).all()
    in_clan_tags    = {p.tag for p in clan_players}
    player_name_map = {p.tag: (p.name or p.tag) for p in clan_players}

    # All attacks for clan players, sorted chronologically
    raw = (
        BattleLog.query
        .filter(BattleLog.attack == True, BattleLog.player_tag.in_(in_clan_tags))
        .order_by(BattleLog.time.asc())
        .all()
    )

    # Strip import-window artifacts (same logic as battle_history_page)
    first_log_time = {}
    for b in raw:
        if b.player_tag not in first_log_time or (b.time and b.time < first_log_time[b.player_tag]):
            first_log_time[b.player_tag] = b.time
    import_window = dt.timedelta(minutes=2)
    attacks = [
        b for b in raw
        if not (b.time and first_log_time.get(b.player_tag) and
                b.time <= first_log_time[b.player_tag] + import_window)
    ]

    # ── Per-player accumulation ───────────────────────────────────────────────
    acc = {}
    for b in attacks:
        tag = b.player_tag
        if tag not in acc:
            acc[tag] = {
                'player_name':   player_name_map.get(tag, tag),
                'player_tag':    tag,
                'total_attacks': 0,
                'total_gold':    0,
                'total_elixir':  0,
                'total_dark':    0,
                'stars_3': 0, 'stars_2': 0, 'stars_1': 0, 'stars_0': 0,
                'total_pct':     0,
                'best_loot':     0,
                'first_seen':    b.time,
                'last_seen':     b.time,
            }
        p = acc[tag]
        p['total_attacks'] += 1
        gold   = b.loot_gold or 0
        elixir = b.loot_elixir or 0
        dark   = b.loot_dark_elixir or 0
        p['total_gold']   += gold
        p['total_elixir'] += elixir
        p['total_dark']   += dark
        haul = gold + elixir
        if haul > p['best_loot']:
            p['best_loot'] = haul
        stars = min(b.stars or 0, 3)
        if stars == 3:   p['stars_3'] += 1
        elif stars == 2: p['stars_2'] += 1
        elif stars == 1: p['stars_1'] += 1
        else:            p['stars_0'] += 1
        p['total_pct'] += b.percentage or 0
        if b.time:
            if p['first_seen'] is None or b.time < p['first_seen']:
                p['first_seen'] = b.time
            if p['last_seen'] is None or b.time > p['last_seen']:
                p['last_seen'] = b.time

    result = []
    for tag, p in acc.items():
        n    = p['total_attacks']
        loot = p['total_gold'] + p['total_elixir']
        # weeks active (span from first to last attack in calendar weeks)
        weeks_span = 1
        if p['first_seen'] and p['last_seen']:
            span_days  = (p['last_seen'] - p['first_seen']).days
            weeks_span = max(1, round(span_days / 7))
        result.append({
            'player_name':   p['player_name'],
            'player_tag':    p['player_tag'],
            'total_attacks': n,
            'total_gold':    p['total_gold'],
            'total_elixir':  p['total_elixir'],
            'total_dark':    p['total_dark'],
            'total_loot':    loot,
            'avg_loot':      round(loot / n) if n else 0,
            'avg_per_week':  round(n / weeks_span, 1),
            'three_rate':    round(p['stars_3'] / n * 100, 1) if n else 0,
            'two_rate':      round(p['stars_2'] / n * 100, 1) if n else 0,
            'one_rate':      round(p['stars_1'] / n * 100, 1) if n else 0,
            'zero_rate':     round(p['stars_0'] / n * 100, 1) if n else 0,
            'avg_pct':       round(p['total_pct'] / n, 1) if n else 0,
            'best_loot':     p['best_loot'],
            'stars_3':       p['stars_3'],
        })
    result.sort(key=lambda x: x['total_attacks'], reverse=True)

    # ── Weekly activity (last 26 weeks) ───────────────────────────────────────
    weekly_map = defaultdict(lambda: {'attacks': 0, 'loot': 0, 'three': 0})
    for b in attacks:
        if b.time:
            local_t = to_local(b.time)
            if local_t:
                monday = (local_t.date() - dt.timedelta(days=local_t.weekday())).isoformat()
                weekly_map[monday]['attacks'] += 1
                weekly_map[monday]['loot']    += (b.loot_gold or 0) + (b.loot_elixir or 0)
                if (b.stars or 0) >= 3:
                    weekly_map[monday]['three'] += 1

    sorted_weeks = sorted(weekly_map.keys())[-26:]
    weekly_trend = [{
        'label':   dt.date.fromisoformat(w).strftime('%d.%m'),
        'attacks': weekly_map[w]['attacks'],
        'loot':    weekly_map[w]['loot'],
        'three_rate': round(weekly_map[w]['three'] / weekly_map[w]['attacks'] * 100, 1) if weekly_map[w]['attacks'] else 0,
    } for w in sorted_weeks]

    # ── Day × Hour activity heatmap ───────────────────────────────────────────
    dh_map = defaultdict(int)
    for b in attacks:
        if b.time:
            local_t = to_local(b.time)
            if local_t:
                dh_map[(local_t.weekday(), local_t.hour)] += 1
    # [day][hour] — day 0=Mon..6=Sun
    day_hour = [[dh_map.get((d, h), 0) for h in range(24)] for d in range(7)]

    # ── Battle type distribution ───────────────────────────────────────────────
    type_counts = defaultdict(int)
    for b in attacks:
        type_counts[b.type or 'Unknown'] += 1
    type_dist = [{'type': k, 'count': v}
                 for k, v in sorted(type_counts.items(), key=lambda x: -x[1])]

    # ── Summary ───────────────────────────────────────────────────────────────
    total_attacks_all    = len(attacks)
    total_gold_all       = sum(b.loot_gold or 0 for b in attacks)
    total_elixir_all     = sum(b.loot_elixir or 0 for b in attacks)
    total_dark_all       = sum(b.loot_dark_elixir or 0 for b in attacks)
    all_3stars           = sum(p['stars_3'] for p in acc.values())
    clan_3star_rate      = round(all_3stars / total_attacks_all * 100, 1) if total_attacks_all else 0

    return render_template(
        'battles/battle_stats.html',
        player_stats_json  = json.dumps(result,      default=str),
        weekly_trend_json  = json.dumps(weekly_trend, default=str),
        day_hour_json      = json.dumps(day_hour,     default=str),
        type_dist_json     = json.dumps(type_dist,    default=str),
        total_attacks_all  = total_attacks_all,
        total_gold_all     = total_gold_all,
        total_elixir_all   = total_elixir_all,
        total_dark_all     = total_dark_all,
        clan_3star_rate    = clan_3star_rate,
    )
