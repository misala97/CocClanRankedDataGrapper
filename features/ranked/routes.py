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

    week_data = []
    all_players = Player.query.options(
        selectinload(Player.ranked_weeks).selectinload(RankedWeek.battle_logs)
    ).all()

    for player in all_players:
        ranked_week = None
        if selected_week_id:
            ranked_week = next(
                (rw for rw in player.ranked_weeks if rw.league_season_id == selected_week_id),
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
        })

    week_data.sort(key=lambda item: (item['rank'] or 9999, item['player_name'] or ''))

    last_10_seasons = [dw.league_season_id for dw in distinct_weeks[:10]]
    player_history = {}
    for player in all_players:
        history = []
        for season_id in reversed(last_10_seasons):
            dw = next((d for d in distinct_weeks if d.league_season_id == season_id), None)
            rw = next((r for r in player.ranked_weeks if r.league_season_id == season_id), None)
            if rw and dw:
                a_stars = [log.stars or 0 for log in rw.battle_logs if log.attack is True or log.attack == 1]
                d_stars = [log.stars or 0 for log in rw.battle_logs if not (log.attack is True or log.attack == 1)]
                att_c = len(a_stars)
                def_c = len(d_stars)
                history.append({
                    'label': dw.start_day.strftime('%d.%m.%y'),
                    'att_count': att_c,
                    'att_max': rw.max_attacks or 0,
                    'att_avg': round(sum(a_stars) / att_c, 2) if att_c else 0,
                    'def_count': def_c,
                    'def_avg': round(sum(d_stars) / def_c, 2) if def_c else 0,
                    'trophies': rw.trophies or 0,
                    'rank': rw.rank,
                    'league_tier': rw.league_tier or '',
                    'league_icon': rw.league_icon or '',
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
