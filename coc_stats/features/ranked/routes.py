import datetime as dt
import json

from flask import Blueprint, render_template, request
from sqlalchemy.orm import selectinload

from extensions import db
from models import Player, RankedWeek
from services.helpers import (
    get_league_thresholds, _get_league_rank,
    EXPECTED_LEAGUE_RANK, _calc_th_multiplier, to_local,
    _ranked_verdict, _ranked_score_from_adj, _calc_ranked_score, _is_attack,
)

ranked_bp = Blueprint('ranked', __name__)


@ranked_bp.route('/ranked')
def ranked_weeks_page():
    distinct_weeks = (
        db.session.query(
            RankedWeek.start_day,
            RankedWeek.end_day,
            db.func.max(RankedWeek.league_season_id).label('league_season_id'),
        )
        .group_by(RankedWeek.start_day, RankedWeek.end_day)
        .order_by(RankedWeek.start_day.desc())
        .all()
    )

    current_week_row = (
        db.session.query(RankedWeek.league_season_id)
        .filter(RankedWeek.is_done == False)
        .first()
    )
    current_week_id = current_week_row.league_season_id if current_week_row else None

    selected_week_id = request.args.get('week_id', default=None)
    if not selected_week_id:
        selected_week_id = current_week_id or (distinct_weeks[0].league_season_id if distinct_weeks else None)

    last_10_seasons = [dw.league_season_id for dw in distinct_weeks[:52]]
    season_filter   = set(last_10_seasons)
    if selected_week_id:
        season_filter.add(selected_week_id)

    selected_idx = next((i for i, dw in enumerate(distinct_weeks) if dw.league_season_id == selected_week_id), None)
    prev_week_id = distinct_weeks[selected_idx + 1].league_season_id if (selected_idx is not None and selected_idx + 1 < len(distinct_weeks)) else None
    if prev_week_id:
        season_filter.add(prev_week_id)

    all_weeks = (RankedWeek.query
                 .filter(RankedWeek.league_season_id.in_(season_filter))
                 .options(selectinload(RankedWeek.battle_logs))
                 .all()) if season_filter else []
    weeks_by_player = {}
    for w in all_weeks:
        weeks_by_player.setdefault(w.player_tag, []).append(w)

    distinct_week_map = {dw.league_season_id: dw for dw in distinct_weeks}

    week_data = []
    all_players = Player.query.all()

    for player in all_players:
        ranked_week = None
        if selected_week_id:
            ranked_week = next(
                (rw for rw in weeks_by_player.get(player.tag, []) if rw.league_season_id == selected_week_id),
                None
            )
        prev_ranked_week = next(
            (rw for rw in weeks_by_player.get(player.tag, []) if rw.league_season_id == prev_week_id),
            None
        ) if prev_week_id else None
        rank_prev = prev_ranked_week.rank if prev_ranked_week else None

        league_tier  = player.league_tier
        league_icon  = player.league_icon
        rank = trophies = None
        max_attacks = att_count = def_count = 0
        attack_logs = defense_logs = attack_details = defense_details = adj_attack_scores = []
        player_th = 0

        if ranked_week:
            league_tier  = ranked_week.league_tier or league_tier
            league_icon  = ranked_week.league_icon or league_icon
            rank         = ranked_week.rank
            trophies     = ranked_week.trophies
            max_attacks  = ranked_week.max_attacks or 0
            player_th    = ranked_week.townhall or player.current_th or 0

            attack_logs = defense_logs = []
            attack_details = defense_details = adj_attack_scores = []

            for log in ranked_week.battle_logs:
                local_time = to_local(log.time)
                detail_entry = {
                    'opponent_name': log.opponent_name or log.opponent_tag or 'Unbekannt',
                    'opponent_th': log.opponent_th or '',
                    'stars': log.stars or 0,
                    'percentage': log.percentage or 0,
                    'time': local_time.strftime('%d.%m.%y %H:%M') if local_time else '–',
                    'time_sort': local_time.isoformat() if local_time else '',
                }
                if _is_attack(log):
                    attack_logs = attack_logs + [log.stars or 0]
                    attack_details = attack_details + [detail_entry]
                    try:
                        opp_th = int(log.opponent_th)
                    except (TypeError, ValueError):
                        opp_th = player_th
                    diff = opp_th - player_th
                    adj = (log.stars or 0) * _calc_th_multiplier(diff, player_th)
                    adj_attack_scores = adj_attack_scores + [adj]
                else:
                    defense_logs = defense_logs + [log.stars or 0]
                    defense_details = defense_details + [detail_entry]

        att_count = len(attack_logs)
        def_count = len(defense_logs)
        att_avg = round(sum(attack_logs) / att_count, 2) if att_count else 0
        def_avg = round(sum(defense_logs) / def_count, 2) if def_count else 0

        att_0star = sum(1 for s in attack_logs if s == 0)
        att_1star = sum(1 for s in attack_logs if s == 1)
        att_2star = sum(1 for s in attack_logs if s == 2)
        att_3star = sum(1 for s in attack_logs if s == 3)
        def_0star = sum(1 for s in defense_logs if s == 0)
        def_1star = sum(1 for s in defense_logs if s == 1)
        def_2star = sum(1 for s in defense_logs if s == 2)
        def_3star = sum(1 for s in defense_logs if s == 3)

        is_active     = ranked_week is not None
        missing       = max(0, max_attacks - att_count)
        missing_text  = f" ({missing} missing)" if missing > 0 else ""

        score_100, th_adj_score, lm = _ranked_score_from_adj(adj_attack_scores, max_attacks, league_tier, player_th or player.current_th or 0)

        if not is_active:
            badge_class, judge_label, rank_status = 'badge-inactive', 'Inactive', 'inactive'
        else:
            badge_class, judge_label, _ = _ranked_verdict(score_100, att_count, max_attacks)
            rank_status = 'neutral'

        thresholds = get_league_thresholds(league_tier)
        if is_active and thresholds and rank and rank > 0:
            if rank <= thresholds['pro']:
                rank_status = 'up'
            elif rank > (100 - thresholds['dem']):
                rank_status = 'down'
            else:
                rank_status = 'neutral'

        week_data.append({
            'player_name': player.name or player.tag,
            'player_tag': player.tag,
            'rank': rank,
            'trophies': trophies or 0,
            'league_tier': league_tier,
            'league_icon': league_icon,
            'att_count': att_count,
            'att_max': max_attacks,
            'att_0star': att_0star, 'att_1star': att_1star, 'att_2star': att_2star, 'att_3star': att_3star,
            'att_avg': att_avg,
            'th_adj_score': th_adj_score,
            'league_mult': round(lm, 4),
            'league_rank': _get_league_rank(league_tier),
            'expected_league_rank': EXPECTED_LEAGUE_RANK.get(int(player_th or player.current_th or 0), 1),
            'score_100': score_100,
            'player_th': player_th or player.current_th or 0,
            'def_count': def_count,
            'def_max': max_attacks,
            'def_0star': def_0star, 'def_1star': def_1star, 'def_2star': def_2star, 'def_3star': def_3star,
            'def_avg': def_avg,
            'attack_details': attack_details,
            'defense_details': defense_details,
            'badge_class': badge_class,
            'judge_label': judge_label,
            'is_active': is_active,
            'rank_status': rank_status,
            'promo_spots': thresholds['pro'] if thresholds else None,
            'dem_spots': thresholds['dem'] if thresholds else None,
            'in_clan': player.in_clan,
            'in_group_chat': bool(player.in_group_chat),
            'group_total_attacks':  ranked_week.group_total_attacks  if ranked_week else None,
            'group_full_attackers': ranked_week.group_full_attackers if ranked_week else None,
            'league_tier_prev': prev_ranked_week.league_tier if prev_ranked_week else None,
        })

    week_data.sort(key=lambda item: (item['rank'] or 9999, item['player_name'] or ''))

    player_history = {}
    player_weeks_by_season = {}
    for tag, weeks in weeks_by_player.items():
        player_weeks_by_season[tag] = {w.league_season_id: w for w in weeks}

    for player in all_players:
        history = []
        for season_id in reversed(last_10_seasons):
            dw = distinct_week_map.get(season_id)
            rw = player_weeks_by_season.get(player.tag, {}).get(season_id)
            if not dw:
                continue
            if rw:
                atk_logs = [log for log in rw.battle_logs if _is_attack(log)]
                def_logs = [log for log in rw.battle_logs if not _is_attack(log)]
                a_stars = [log.stars or 0 for log in atk_logs]
                d_stars = [log.stars or 0 for log in def_logs]
                att_c = len(a_stars)
                def_c = len(d_stars)

                player_th_hist = rw.townhall or 0
                att_max_hist   = rw.max_attacks or 0
                score_100_hist, _, _ = _calc_ranked_score(rw.battle_logs, player_th_hist, att_max_hist, rw.league_tier or '')
                badge_hist, _, _ = _ranked_verdict(score_100_hist, att_c, att_max_hist)

                att_ths = [int(log.opponent_th) for log in atk_logs if log.opponent_th]
                def_ths = [int(log.opponent_th) for log in def_logs if log.opponent_th]

                history.append({
                    'label': dw.start_day.strftime('%d.%m.%y'),
                    'att_count': att_c,
                    'att_max': att_max_hist,
                    'att_avg': round(sum(a_stars) / att_c, 2) if att_c else 0,
                    'att_avg_th': round(sum(att_ths) / len(att_ths), 1) if att_ths else None,
                    'att_0star': sum(1 for s in a_stars if s == 0),
                    'att_1star': sum(1 for s in a_stars if s == 1),
                    'att_2star': sum(1 for s in a_stars if s == 2),
                    'att_3star': sum(1 for s in a_stars if s == 3),
                    'def_count': def_c,
                    'def_avg': round(sum(d_stars) / def_c, 2) if def_c else 0,
                    'def_avg_th': round(sum(def_ths) / len(def_ths), 1) if def_ths else None,
                    'def_0star': sum(1 for s in d_stars if s == 0),
                    'def_1star': sum(1 for s in d_stars if s == 1),
                    'def_2star': sum(1 for s in d_stars if s == 2),
                    'def_3star': sum(1 for s in d_stars if s == 3),
                    'player_th': player_th_hist,
                    'trophies': rw.trophies or 0,
                    'rank': rw.rank,
                    'league_tier': rw.league_tier or '',
                    'league_icon': rw.league_icon or '',
                    'score_100': score_100_hist,
                    'badge_class': badge_hist,
                    'is_inactive': False,
                    'group_full_attackers': rw.group_full_attackers,
                    'group_total_attacks': rw.group_total_attacks,
                })
            else:
                history.append({
                    'label': dw.start_day.strftime('%d.%m.%y'),
                    'att_count': 0, 'att_max': 0, 'att_avg': 0,
                    'att_avg_th': None, 'def_avg_th': None,
                    'att_0star': 0, 'att_1star': 0, 'att_2star': 0, 'att_3star': 0,
                    'def_0star': 0, 'def_1star': 0, 'def_2star': 0, 'def_3star': 0,
                    'player_th': 0,
                    'def_count': 0, 'def_avg': 0,
                    'trophies': 0, 'rank': None,
                    'league_tier': '', 'league_icon': '',
                    'score_100': 0, 'badge_class': 'badge-inactive',
                    'is_inactive': True,
                    'group_full_attackers': None,
                    'group_total_attacks': None,
                })
        if history:
            player_history[player.tag] = history

    selected_week_info = None
    if selected_week_id:
        selected_week_info = next((w for w in distinct_weeks if w.league_season_id == selected_week_id), None)

    return render_template(
        'ranked/ranked_weeks.html',
        distinct_weeks=distinct_weeks,
        selected_week_id=selected_week_id,
        selected_week_info=selected_week_info,
        current_week_id=current_week_id,
        week_data=week_data,
        player_history=player_history,
    )


@ranked_bp.route('/ranked/stats')
def ranked_stats_page():
    clan_players    = Player.query.filter_by(in_clan=True).all()
    in_clan_tags    = {p.tag for p in clan_players}
    player_name_map = {p.tag: (p.name or p.tag) for p in clan_players}

    all_weeks = (
        RankedWeek.query
        .filter(RankedWeek.player_tag.in_(in_clan_tags))
        .options(selectinload(RankedWeek.battle_logs))
        .all()
    )

    distinct_weeks_q = (
        db.session.query(RankedWeek.league_season_id, RankedWeek.start_day)
        .filter(RankedWeek.player_tag.in_(in_clan_tags))
        .distinct()
        .order_by(RankedWeek.start_day.asc())
        .all()
    )
    season_order  = [row.league_season_id for row in distinct_weeks_q]
    season_labels = {
        row.league_season_id: row.start_day.strftime('%d.%m.%y') if row.start_day else str(row.league_season_id)
        for row in distinct_weeks_q
    }

    # ── Per-player accumulators ───────────────────────────────────────────────
    acc              = {}
    clan_season_agg  = {}   # season_id -> {scores: [], participants: int}

    for week in all_weeks:
        tag = week.player_tag
        if tag not in in_clan_tags:
            continue
        if tag not in acc:
            acc[tag] = {
                'player_name':       player_name_map.get(tag, tag),
                'player_tag':        tag,
                'weeks_active':      0,
                'total_attacks':     0,
                'total_max_attacks': 0,
                'stars_3': 0, 'stars_2': 0, 'stars_1': 0, 'stars_0': 0,
                'total_stars':       0,
                'total_defenses':    0,
                'def_zero':          0,
                'def_stars':         0,
                'peak_trophies':     0,
                'best_rank':         None,
                'weekly_scores':     {},
                'th_matchups':       [],
                'th_eras':           {},   # th_level -> {attacks, stars_3, total_stars, scores, weeks}
                'verdict_dist':      {},   # badge_class -> count
            }
        p = acc[tag]
        p['weeks_active'] += 1

        player_th = week.townhall or 0
        att_max   = week.max_attacks or 0
        p['total_max_attacks'] += att_max

        adj_week         = []
        week_att_count   = 0
        week_stars_3     = 0
        week_total_stars = 0

        if (week.trophies or 0) > p['peak_trophies']:
            p['peak_trophies'] = week.trophies or 0
        if week.rank and (p['best_rank'] is None or week.rank < p['best_rank']):
            p['best_rank'] = week.rank

        for log in week.battle_logs:
            stars = log.stars or 0
            if _is_attack(log):
                p['total_attacks'] += 1
                week_att_count     += 1
                p['total_stars']   += stars
                week_total_stars   += stars
                if stars == 3:
                    p['stars_3'] += 1
                    week_stars_3 += 1
                elif stars == 2: p['stars_2'] += 1
                elif stars == 1: p['stars_1'] += 1
                else:            p['stars_0'] += 1
                try:    opp_th = int(log.opponent_th)
                except: opp_th = player_th
                diff = opp_th - player_th
                p['th_matchups'].append({'diff': diff, 'stars': stars})
                adj_week.append(stars * _calc_th_multiplier(diff, player_th))
            else:
                p['total_defenses'] += 1
                p['def_stars']      += stars
                if stars == 0:
                    p['def_zero'] += 1

        # TH era accumulation — uses ranked_week.townhall as the player's TH for this season
        if player_th > 0:
            era = p['th_eras'].setdefault(player_th, {
                'attacks': 0, 'stars_3': 0, 'total_stars': 0, 'scores': [], 'weeks': 0
            })
            era['weeks']       += 1
            era['attacks']     += week_att_count
            era['stars_3']     += week_stars_3
            era['total_stars'] += week_total_stars

        if att_max > 0:
            score, _, _ = _ranked_score_from_adj(adj_week, att_max, week.league_tier or '', player_th)
            p['weekly_scores'][week.league_season_id] = score

            if player_th > 0:
                p['th_eras'][player_th]['scores'].append(score)

            badge, _, _ = _ranked_verdict(score, week_att_count, att_max)
            p['verdict_dist'][badge] = p['verdict_dist'].get(badge, 0) + 1

            csa = clan_season_agg.setdefault(week.league_season_id, {'scores': [], 'participants': 0})
            csa['scores'].append(score)
            csa['participants'] += 1

    # ── Build result list ─────────────────────────────────────────────────────
    result = []
    for tag, p in acc.items():
        n      = p['total_attacks']
        scores = [p['weekly_scores'][s] for s in season_order if s in p['weekly_scores']]
        avg_score  = round(sum(scores) / len(scores), 1) if scores else 0
        best_score = max(scores) if scores else 0
        avg_stars  = round(p['total_stars'] / n, 2) if n else 0
        three_rate = round(p['stars_3'] / n * 100, 1) if n else 0
        two_rate   = round(p['stars_2'] / n * 100, 1) if n else 0
        one_rate   = round(p['stars_1'] / n * 100, 1) if n else 0
        zero_rate  = round(p['stars_0'] / n * 100, 1) if n else 0
        def_zero_r = round(p['def_zero'] / p['total_defenses'] * 100, 1) if p['total_defenses'] else 0
        attend_r   = round(p['total_attacks'] / p['total_max_attacks'] * 100, 1) if p['total_max_attacks'] else 0

        consistency = 0.0
        if len(scores) > 1:
            consistency = round((sum((s - avg_score) ** 2 for s in scores) / len(scores)) ** 0.5, 1)

        if len(scores) >= 6:
            trend = round(sum(scores[-3:]) / 3 - sum(scores[-6:-3]) / 3, 1)
        elif len(scores) >= 2:
            trend = round(scores[-1] - scores[-2], 1)
        else:
            trend = 0.0

        th_up   = [m for m in p['th_matchups'] if m['diff'] > 0]
        th_even = [m for m in p['th_matchups'] if m['diff'] == 0]
        th_down = [m for m in p['th_matchups'] if m['diff'] < 0]

        th_eras_list = [
            {
                'th':         th,
                'attacks':    era['attacks'],
                'three_rate': round(era['stars_3'] / era['attacks'] * 100, 1) if era['attacks'] else 0,
                'avg_score':  round(sum(era['scores']) / len(era['scores']), 1) if era['scores'] else 0,
                'weeks':      era['weeks'],
            }
            for th, era in sorted(p['th_eras'].items())
        ]

        vd = p['verdict_dist']
        result.append({
            'player_name':       p['player_name'],
            'player_tag':        p['player_tag'],
            'weeks_active':      p['weeks_active'],
            'total_attacks':     n,
            'total_max_attacks': p['total_max_attacks'],
            'attendance_rate':   attend_r,
            'avg_stars':         avg_stars,
            'three_rate':        three_rate,
            'two_rate':          two_rate,
            'one_rate':          one_rate,
            'zero_rate':         zero_rate,
            'avg_score':         avg_score,
            'best_score':        best_score,
            'best_rank':         p['best_rank'],
            'peak_trophies':     p['peak_trophies'],
            'consistency':       consistency,
            'trend':             trend,
            'def_zero_rate':     def_zero_r,
            'total_defenses':    p['total_defenses'],
            'th_up_avg':         round(sum(m['stars'] for m in th_up)   / len(th_up),   2) if th_up   else None,
            'th_even_avg':       round(sum(m['stars'] for m in th_even) / len(th_even), 2) if th_even else None,
            'th_down_avg':       round(sum(m['stars'] for m in th_down) / len(th_down), 2) if th_down else None,
            'th_up_count':       len(th_up),
            'th_even_count':     len(th_even),
            'th_down_count':     len(th_down),
            'weekly_scores':     p['weekly_scores'],
            'th_eras':           th_eras_list,
            'godlike_weeks':     vd.get('badge-godlike',  0),
            'dominant_weeks':    vd.get('badge-dominant', 0),
            'wow_weeks':         vd.get('badge-wow',      0),
            'good_weeks':        vd.get('badge-good',     0),
            'bad_weeks':         vd.get('badge-warning',  0),
            'disaster_weeks':    vd.get('badge-suck',     0),
            'useless_weeks':     vd.get('badge-useless',  0),
        })
    result.sort(key=lambda x: x['avg_score'], reverse=True)

    # ── Clan weekly trend ─────────────────────────────────────────────────────
    clan_trend = []
    for sid in season_order:
        csa = clan_season_agg.get(sid, {})
        ws  = csa.get('scores', [])
        if ws:
            clan_trend.append({
                'label':        season_labels[sid],
                'avg_score':    round(sum(ws) / len(ws), 1),
                'participants': csa['participants'],
                'max_score':    max(ws),
                'min_score':    min(ws),
            })

    # ── Performance heatmap (last 20 weeks) ───────────────────────────────────
    heatmap_weeks   = season_order[-20:]
    heatmap_players = [p['player_name'] for p in result]
    heatmap = {
        'weeks':   [season_labels[s] for s in reversed(heatmap_weeks)],
        'players': heatmap_players,
        'scores':  {
            p['player_name']: [p['weekly_scores'].get(s) for s in reversed(heatmap_weeks)]
            for p in result
        },
    }

    # ── Career lines for player chart (last 20 seasons) ──────────────────────
    career_seasons = season_order[-20:]
    career_labels  = [season_labels[s] for s in career_seasons]
    career_lines   = {
        p['player_name']: [p['weekly_scores'].get(s) for s in career_seasons]
        for p in result
    }

    # ── All TH levels seen across the data set ────────────────────────────────
    all_th_levels = sorted({th for p_data in acc.values() for th in p_data['th_eras']})

    # ── Summary ───────────────────────────────────────────────────────────────
    total_weeks          = len(distinct_weeks_q)
    all_attacks_total    = sum(p['total_attacks'] for p in result)
    all_3stars           = sum(p['stars_3'] for p in acc.values())
    clan_three_star_rate = round(all_3stars / all_attacks_total * 100, 1) if all_attacks_total else 0
    active               = [p for p in result if p['avg_score'] > 0]
    avg_clan_score       = round(sum(p['avg_score'] for p in active) / len(active), 1) if active else 0

    # ── Hall of Fame ──────────────────────────────────────────────────────────
    qualified = [p for p in result if p['avg_score'] > 0 and p['total_attacks'] >= 5]
    hof = {}
    if qualified:
        def _hof(p, label, val):
            return {'name': p['player_name'], 'tag': p['player_tag'], 'label': label, 'val': val}

        p = max(qualified, key=lambda x: x['avg_score'])
        hof['top_score'] = _hof(p, 'avg score', str(p['avg_score']))

        p = max(qualified, key=lambda x: x['best_score'])
        hof['best_week'] = _hof(p, 'best week score', str(p['best_score']))

        p = max(qualified, key=lambda x: x['three_rate'])
        hof['most_3star'] = _hof(p, '3★ rate', f"{p['three_rate']}%")

        defenders = [q for q in qualified if q['def_zero_rate'] > 0]
        if defenders:
            p = max(defenders, key=lambda x: x['def_zero_rate'])
            hof['best_def'] = _hof(p, 'def 0★ rate', f"{p['def_zero_rate']}%")

        godlikers = [q for q in qualified if q['godlike_weeks'] > 0]
        if godlikers:
            p = max(godlikers, key=lambda x: x['godlike_weeks'])
            hof['godlike'] = _hof(p, 'godlike weeks', str(p['godlike_weeks']))

        p = max(qualified, key=lambda x: x['weeks_active'])
        hof['most_active'] = _hof(p, 'seasons played', str(p['weeks_active']))

    # Strip weekly_scores before serialising
    result_json = [{k: v for k, v in p.items() if k != 'weekly_scores'} for p in result]

    return render_template(
        'ranked/ranked_stats.html',
        player_stats_json    = json.dumps(result_json,   default=str),
        clan_trend_json      = json.dumps(clan_trend,    default=str),
        heatmap_json         = json.dumps(heatmap,       default=str),
        career_lines_json    = json.dumps(career_lines,  default=str),
        career_labels_json   = json.dumps(career_labels, default=str),
        all_th_levels_json   = json.dumps(all_th_levels, default=str),
        hof_json             = json.dumps(hof,           default=str),
        total_weeks          = total_weeks,
        all_attacks_total    = all_attacks_total,
        clan_three_star_rate = clan_three_star_rate,
        avg_clan_score       = avg_clan_score,
    )
