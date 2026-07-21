"""Pure aggregation for the long-term Ranked record page (/ranked/stats).

Every function here takes ORM rows (or plain objects shaped like them) and
returns plain dicts. No Flask, no DB session, no template concerns — so the
whole module is verifiable from a standalone script with synthetic fixtures.

Scoring is never reimplemented; it comes from services.helpers.
"""

import datetime as dt
import statistics

from services.helpers import (
    _calc_ranked_score,
    _get_league_rank,
    _is_attack,
    _ranked_verdict,
)

# ── Tunable thresholds ────────────────────────────────────────────────────────
WINDOWS               = {'all': None, '12': 12, '4': 4}
DEFAULT_WINDOW        = 'all'

TREND_BAND            = 8.0     # points of score that qualify as surging / sliding
UNRELIABLE_SIGMA      = 15.0    # sigma at or above this is "erratic" / Unreliable
ABSENT_ATTENDANCE     = 0.50    # attendance below this is "not participating"
FORM_BAND             = 2.0     # clan-mean delta that separates holding from moving
GOOD_BAND_CUTOFF      = 58      # _ranked_verdict's "Good" floor, for roster depth

MIN_WEEKS_FOR_TREND   = 4       # trend and sigma are meaningless below this
TREND_LONG_WINDOW     = 3       # weeks per side once there is enough history
TREND_SHORT_WINDOW    = 2       # weeks per side when history is still short
MIN_WEEKS_FOR_RANKING = 3       # fewer than this drops to the "not enough data" tail

DEFENSE_BAND_MIN_N    = 250     # defenses needed before a league band is trusted
MATCHUP_MIN_N         = 10      # attacks needed before a TH bucket is rendered
NEAR_MISS_PCT         = 90      # 2-star at or above this destruction is a near-miss

LEGEND_RANK_FLOOR     = 34      # _get_league_rank returns 34/35/36 for Legend III/II/I

RELIABILITY_BANDS = ((5.0, 'metronome'), (10.0, 'steady'), (15.0, 'swingy'),
                     (None, 'erratic'))


def select_seasons(weeks, window):
    """Completed season ids, oldest first, trimmed to the requested window."""
    first_day = {}
    for w in weeks:
        if not w.is_done:
            continue
        sid = w.league_season_id
        day = w.start_day or dt.date.min
        if sid not in first_day or day < first_day[sid]:
            first_day[sid] = day
    ordered = sorted(first_day, key=lambda s: (first_day[s], s))
    limit = WINDOWS.get(window)
    return ordered[-limit:] if limit else ordered


def build_week_records(weeks, season_ids):
    """{player_tag: [week record, ...]} ordered to match season_ids.

    attacks_used comes from ranked_week (attack_wins + attack_losses), not from
    counting battle logs: the logs are a rolling API sample and can be short,
    while the week row is authoritative.
    """
    wanted = set(season_ids)
    out = {}
    for w in weeks:
        if not w.is_done or w.league_season_id not in wanted:
            continue
        max_attacks = w.max_attacks or 0
        used = (w.attack_wins or 0) + (w.attack_losses or 0)
        tier = w.league_tier or ''
        score, _, _ = _calc_ranked_score(w.battle_logs, w.townhall or 0, max_attacks, tier)
        badge, label, _ = _ranked_verdict(score, used, max_attacks)
        out.setdefault(w.player_tag, []).append({
            'season_id':    w.league_season_id,
            'start_day':    w.start_day,
            'score':        score,
            'badge':        badge,
            'label':        label.split(' (')[0],
            'attacks_used': used,
            'max_attacks':  max_attacks,
            'townhall':     w.townhall or 0,
            'league_tier':  tier,
            'league_rank':  _get_league_rank(tier),
            'trophies':     w.trophies or 0,
            'rank':         w.rank,
        })
    order = {sid: i for i, sid in enumerate(season_ids)}
    for records in out.values():
        records.sort(key=lambda r: order[r['season_id']])
    return out


def reliability_word(sigma):
    """Sigma rendered as a word. Bands are exclusive at the top."""
    for cutoff, word in RELIABILITY_BANDS:
        if cutoff is None or sigma < cutoff:
            return word
    return 'erratic'


def score_trend(scores):
    """Points of score gained or lost, comparing recent weeks to earlier ones.

    Returns None below MIN_WEEKS_FOR_TREND — a two-week 'trend' is noise.
    """
    n = len(scores)
    long_span = TREND_LONG_WINDOW * 2
    if n >= long_span:
        return round(sum(scores[-TREND_LONG_WINDOW:]) / TREND_LONG_WINDOW
                     - sum(scores[long_span * -1:-TREND_LONG_WINDOW]) / TREND_LONG_WINDOW, 1)
    if n >= MIN_WEEKS_FOR_TREND:
        return round(sum(scores[-TREND_SHORT_WINDOW:]) / TREND_SHORT_WINDOW
                     - sum(scores[:TREND_SHORT_WINDOW]) / TREND_SHORT_WINDOW, 1)
    return None


def player_aggregate(records):
    """Window-level summary for one player, from their ordered week records."""
    scores = [r['score'] for r in records]
    n = len(scores)
    mean = round(sum(scores) / n, 1) if n else 0.0
    sigma = round(statistics.pstdev(scores), 1) if n > 1 else 0.0

    attacks_max = sum(r['max_attacks'] for r in records)
    attacks_used = sum(r['attacks_used'] for r in records)

    ranked_weeks = [r for r in records if r['league_rank']]

    verdict_record = {}
    for r in records:
        verdict_record[r['badge']] = verdict_record.get(r['badge'], 0) + 1

    # The badge for the WINDOW MEAN, so the roster's mean cell is colored by the
    # band that mean actually falls into. att_count=1, max_attacks=1 keeps
    # _ranked_verdict from appending a missing-attacks suffix — attendance is
    # reported separately and must not leak into this badge.
    mean_badge, _, _ = _ranked_verdict(int(round(mean)), 1, 1) if n else ('badge-useless', '', 0)

    return {
        'weeks_played':    n,
        'mean':            mean,
        'mean_badge':      mean_badge,
        'sigma':           sigma,
        'reliability':     reliability_word(sigma),
        'trend':           score_trend(scores),
        'attendance':      round(attacks_used / attacks_max, 4) if attacks_max else 0.0,
        'attacks_used':    attacks_used,
        'attacks_max':     attacks_max,
        'attacks_wasted':  attacks_max - attacks_used,
        'league_move':     (ranked_weeks[-1]['league_rank'] - ranked_weeks[0]['league_rank'])
                           if ranked_weeks else 0,
        'league_now':      ranked_weeks[-1]['league_tier'] if ranked_weeks else '',
        'league_rank_now': ranked_weeks[-1]['league_rank'] if ranked_weeks else 0,
        'best':            max(scores) if scores else 0,
        'worst':           min(scores) if scores else 0,
        'verdict_record':  verdict_record,
    }
