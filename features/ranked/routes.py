import datetime as dt

from flask import Blueprint, render_template, request
from sqlalchemy.orm import selectinload

from extensions import db
from models import Player, RankedWeek
from services.helpers import (
    get_league_thresholds, _get_league_rank, _league_mult,
    EXPECTED_LEAGUE_RANK, _calc_th_multiplier, to_local,
)

ranked_bp = Blueprint('ranked', __name__)


@ranked_bp.route('/ranked')
def ranked_weeks_page():
    distinct_weeks = db.session.query(
        RankedWeek.start_day,
        RankedWeek.end_day,
        RankedWeek.league_season_id
    ).distinct().order_by(RankedWeek.start_day.desc()).all()

    selected_week_id = request.args.get('week_id', default=None)
    if not selected_week_id and distinct_weeks:
        selected_week_id = distinct_weeks[0].league_season_id

    last_10_seasons = [dw.league_season_id for dw in distinct_weeks[:52]]
    season_filter   = set(last_10_seasons)
    if selected_week_id:
        season_filter.add(selected_week_id)

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
                if log.attack is True or log.attack == 1:
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

        th_adj_score = round(sum(adj_attack_scores) / max_attacks, 3) if max_attacks > 0 else 0.0
        lm = _league_mult(league_tier, player_th or player.current_th or 0)
        score_100 = min(round(th_adj_score * lm * 100 / 3.45), 100)

        if not is_active:
            badge_class, judge_label, rank_status = 'badge-inactive', 'Inactive', 'inactive'
        elif score_100 >= 87:
            badge_class, judge_label, rank_status = 'badge-godlike',  'Godlike'  + missing_text, 'neutral'
        elif score_100 >= 80:
            badge_class, judge_label, rank_status = 'badge-dominant', 'Dominant' + missing_text, 'neutral'
        elif score_100 >= 65:
            badge_class, judge_label, rank_status = 'badge-wow',      'Very Good'+ missing_text, 'neutral'
        elif score_100 >= 58:
            badge_class, judge_label, rank_status = 'badge-good',     'Good'     + missing_text, 'neutral'
        elif score_100 >= 43:
            badge_class, judge_label, rank_status = 'badge-warning',  'Bad'      + missing_text, 'neutral'
        elif score_100 >= 29:
            badge_class, judge_label, rank_status = 'badge-suck',     'Disaster' + missing_text, 'neutral'
        else:
            badge_class, judge_label, rank_status = 'badge-useless',  'Useless'  + missing_text, 'neutral'

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
                a_stars = [log.stars or 0 for log in rw.battle_logs if log.attack is True or log.attack == 1]
                d_stars = [log.stars or 0 for log in rw.battle_logs if not (log.attack is True or log.attack == 1)]
                att_c = len(a_stars)
                def_c = len(d_stars)

                player_th_hist = rw.townhall or 0
                att_max_hist   = rw.max_attacks or 0
                adj_hist = []
                for log in rw.battle_logs:
                    if log.attack is True or log.attack == 1:
                        try:    opp_th = int(log.opponent_th)
                        except: opp_th = player_th_hist
                        adj_hist.append((log.stars or 0) * _calc_th_multiplier(opp_th - player_th_hist, player_th_hist))
                th_adj_hist   = round(sum(adj_hist) / att_max_hist, 3) if att_max_hist > 0 else 0.0
                lm_hist       = _league_mult(rw.league_tier or '', player_th_hist)
                score_100_hist = min(round(th_adj_hist * lm_hist * 100 / 3.45), 100) if att_max_hist > 0 else 0
                if   score_100_hist >= 87: badge_hist = 'badge-godlike'
                elif score_100_hist >= 80: badge_hist = 'badge-dominant'
                elif score_100_hist >= 65: badge_hist = 'badge-wow'
                elif score_100_hist >= 58: badge_hist = 'badge-good'
                elif score_100_hist >= 43: badge_hist = 'badge-warning'
                elif score_100_hist >= 29: badge_hist = 'badge-suck'
                elif att_c > 0:            badge_hist = 'badge-useless'
                else:                      badge_hist = 'badge-inactive'

                history.append({
                    'label': dw.start_day.strftime('%d.%m.%y'),
                    'att_count': att_c,
                    'att_max': att_max_hist,
                    'att_avg': round(sum(a_stars) / att_c, 2) if att_c else 0,
                    'def_count': def_c,
                    'def_avg': round(sum(d_stars) / def_c, 2) if def_c else 0,
                    'trophies': rw.trophies or 0,
                    'rank': rw.rank,
                    'league_tier': rw.league_tier or '',
                    'league_icon': rw.league_icon or '',
                    'score_100': score_100_hist,
                    'badge_class': badge_hist,
                    'is_inactive': False,
                })
            else:
                history.append({
                    'label': dw.start_day.strftime('%d.%m.%y'),
                    'att_count': 0, 'att_max': 0, 'att_avg': 0,
                    'def_count': 0, 'def_avg': 0,
                    'trophies': 0, 'rank': None,
                    'league_tier': '', 'league_icon': '',
                    'score_100': 0, 'badge_class': 'badge-inactive',
                    'is_inactive': True,
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
        week_data=week_data,
        player_history=player_history,
    )
