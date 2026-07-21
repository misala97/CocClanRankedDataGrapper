import copy
import datetime as dt
import json
import threading

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from sqlalchemy.orm import selectinload

from extensions import db
from features.auth.routes import _current_user
from features.ranked.stats import (
    DEFAULT_WINDOW, WINDOWS, build_record_page,
)
from models import Player, RankedWeek, RankedWeekAnalysis
from services.helpers import (
    get_league_thresholds, _get_league_rank,
    EXPECTED_LEAGUE_RANK, _calc_th_multiplier, to_local,
    _ranked_verdict, _ranked_score_from_adj, _calc_ranked_score, _is_attack,
)

ranked_bp = Blueprint('ranked', __name__)

ANALYSIS_COOLDOWN = dt.timedelta(minutes=10)
# A 'running' row whose process died (crash/restart) mid-run would otherwise stay stuck
# forever and lock the user out — treat it as abandoned past this age, same idea as
# tasks/__init__.py's STALE_LOCK_SECONDS for the scheduler's file locks.
STALE_RUNNING_TIMEOUT = dt.timedelta(minutes=15)


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
        .order_by(RankedWeek.start_day.desc())
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
            # Week-over-week movement on the standing spine. prev_ranked_week is already
            # loaded (its season is in season_filter), so this is a free passthrough — the
            # roster row shows rank/trophy delta vs last week. rank_prev is only meaningful
            # when the league is unchanged (a new league group = a different 1–100 ladder);
            # the template suppresses the rank delta when league_tier_prev != league_tier.
            'rank_prev': rank_prev,
            'trophies_prev': prev_ranked_week.trophies if prev_ranked_week else None,
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


_RECORD_CACHE = {}          # (window, roster_hash) -> (expires_at, payload)
_RECORD_TTL   = 300         # seconds


def _script_safe_json(payload):
    """JSON for embedding directly in a <script> block.

    json.dumps leaves '</script>' intact, and the HTML tokenizer ends the
    script element at that sequence even inside a JS string literal — so a
    player name coming from the game API could break out into HTML. These
    five escapes are what Flask's own tojson filter applies; the parsed
    value is identical.
    """
    dumped = json.dumps(payload, default=str)
    return (dumped.replace('<', '\\u003c')
                  .replace('>', '\\u003e')
                  .replace('&', '\\u0026')
                  .replace(' ', '\\u2028')
                  .replace(' ', '\\u2029'))


def _record_page_cached(clan_players, window):
    """Clan-wide aggregates are viewer-invariant, so cache per (window, roster).

    Callers get a deep copy: the payload goes straight into a Jinja context,
    and Jinja can call mutating methods on it. Handing out the cached objects
    themselves would let one render corrupt every later viewer's page until
    the TTL lapsed.
    """
    tags = frozenset(p.tag for p in clan_players)
    key = (window, tags)
    now = dt.datetime.now().timestamp()
    hit = _RECORD_CACHE.get(key)
    if hit and hit[0] > now:
        return copy.deepcopy(hit[1])

    weeks = (
        RankedWeek.query
        .filter(RankedWeek.player_tag.in_(tags))
        .options(selectinload(RankedWeek.battle_logs))
        .all()
    ) if tags else []

    payload = build_record_page(clan_players, weeks, window)
    _RECORD_CACHE[key] = (now + _RECORD_TTL, payload)
    return copy.deepcopy(payload)


@ranked_bp.route('/ranked/stats')
def ranked_stats_page():
    window = request.args.get('window', DEFAULT_WINDOW)
    if window not in WINDOWS:
        window = DEFAULT_WINDOW

    clan_players = Player.query.filter_by(in_clan=True).all()
    page = _record_page_cached(clan_players, window)

    return render_template(
        'ranked/ranked_stats.html',
        window       = window,
        windows      = list(WINDOWS),
        form         = page['form'],
        movers       = page['movers'],
        roster       = page['roster'],
        tail_thin    = page['tail_thin'],
        tail_absent  = page['tail_absent'],
        seasons      = page['seasons'],
        page_json    = _script_safe_json(page),
    )


@ranked_bp.route('/ranked/analysis')
def ranked_analysis_page():
    user = _current_user()
    if not user or not user.linked_player_tag:
        return redirect(url_for('ranked.ranked_weeks_page'))

    row = db.session.get(RankedWeekAnalysis, user.id)
    results = json.loads(row.results_json) if row and row.results_json else None
    retry_after = None
    if row and row.finished_at:
        elapsed = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - row.finished_at
        if elapsed < ANALYSIS_COOLDOWN:
            retry_after = int((ANALYSIS_COOLDOWN - elapsed).total_seconds())

    return render_template(
        'ranked/ranked_analysis.html',
        analysis=row,
        results=results,
        retry_after=retry_after,
    )


@ranked_bp.route('/ranked/analysis/run', methods=['POST'])
def ranked_analysis_run():
    from services.ranked_analysis import run_week_analysis

    user = _current_user()
    if not user or not user.linked_player_tag:
        return jsonify(ok=False, error='Link a player to your account first.'), 403

    row = db.session.get(RankedWeekAnalysis, user.id)
    if not row:
        row = RankedWeekAnalysis(app_user_id=user.id, status='idle')
        db.session.add(row)
        db.session.commit()

    if row.status == 'running':
        started = row.started_at
        is_stale = started is None or (
            dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - started > STALE_RUNNING_TIMEOUT
        )
        if not is_stale:
            return jsonify(ok=False, busy=True, error='Analysis is already running — try again in a moment.'), 409

    if row.finished_at:
        elapsed = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - row.finished_at
        if elapsed < ANALYSIS_COOLDOWN:
            retry_after = int((ANALYSIS_COOLDOWN - elapsed).total_seconds())
            return jsonify(ok=False, cooldown=True, retry_after=retry_after,
                            error='Please wait before running another analysis.'), 429

    row.status = 'running'
    row.progress_done = 0
    row.progress_total = 0
    row.error_message = None
    row.started_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    db.session.commit()

    threading.Thread(target=run_week_analysis, args=(user.id,), daemon=True).start()
    return jsonify(ok=True)


@ranked_bp.route('/ranked/analysis/status')
def ranked_analysis_status():
    user = _current_user()
    if not user or not user.linked_player_tag:
        return jsonify(ok=False, error='Link a player to your account first.'), 403

    row = db.session.get(RankedWeekAnalysis, user.id)
    if not row:
        return jsonify(ok=True, status='idle', progress_done=0, progress_total=0)

    return jsonify(
        ok=True,
        status=row.status,
        progress_done=row.progress_done or 0,
        progress_total=row.progress_total or 0,
        error=row.error_message,
    )
