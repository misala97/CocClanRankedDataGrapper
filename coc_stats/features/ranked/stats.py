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


def defense_band(league_rank):
    """League-rank band used to normalize defense.

    Holding a base gets much harder as you climb (clan data: mean trophies per
    defense falls from 17.3 in band 16-20 to 6.7 in band 31-35), so raw
    cross-league comparison is invalid.
    """
    if not league_rank:
        return 'unranked'
    if league_rank >= LEGEND_RANK_FLOOR:
        return 'legend'
    low = ((league_rank - 1) // 5) * 5 + 1
    return '%d-%d' % (low, low + 4)


def build_defense_expectations(week_records_by_tag, defense_logs_by_key):
    """Expected trophies-per-defense per league band, across the whole clan.

    Bands with fewer than DEFENSE_BAND_MIN_N defenses fall back to the global
    mean and are flagged thin, rather than presenting a noisy band mean as if
    it were precise.
    """
    buckets = {}
    for tag, records in week_records_by_tag.items():
        for r in records:
            band = defense_band(r['league_rank'])
            for log in defense_logs_by_key.get((tag, r['season_id']), ()):
                buckets.setdefault(band, []).append(log.trophies or 0)

    every = [v for values in buckets.values() for v in values]
    global_mean = round(sum(every) / len(every), 2) if every else 0.0

    expectations = {}
    for band, values in buckets.items():
        thin = len(values) < DEFENSE_BAND_MIN_N
        expectations[band] = {
            'n':    len(values),
            'mean': global_mean if thin else round(sum(values) / len(values), 2),
            'thin': thin,
        }
    expectations['_global'] = {'n': len(every), 'mean': global_mean, 'thin': False}
    return expectations


def player_defense(tag, records, defense_logs_by_key, expectations):
    """One player's defense quality against what their leagues expected."""
    fallback = expectations['_global']
    values, expected, thin = [], [], False
    for r in records:
        band = expectations.get(defense_band(r['league_rank']), fallback)
        logs = defense_logs_by_key.get((tag, r['season_id']), ())
        if logs and band.get('thin'):
            thin = True
        for log in logs:
            values.append(log.trophies or 0)
            expected.append(band['mean'])

    if not values:
        return {'n': 0, 'tpd': None, 'index': None, 'thin': True}

    tpd = round(sum(values) / len(values), 1)
    return {
        'n':     len(values),
        'tpd':   tpd,
        'index': round(tpd - sum(expected) / len(expected), 1),
        'thin':  thin,
    }


def clan_form(week_records_by_tag, season_ids, labels, depth_source):
    """Clan mean score per season, plus a verdict on direction.

    depth_source is the list of player aggregate rows; depth counts how many
    clear the Good verdict band on their window mean.
    """
    by_season = {}
    for records in week_records_by_tag.values():
        for r in records:
            by_season.setdefault(r['season_id'], []).append(r['score'])

    points = []
    for sid in season_ids:
        scores = by_season.get(sid)
        if not scores:
            continue
        points.append({
            'season_id':    sid,
            'label':        labels.get(sid, sid),
            'mean':         round(sum(scores) / len(scores), 1),
            'participants': len(scores),
        })

    means = [p['mean'] for p in points]
    if len(means) >= 6:
        delta = round(sum(means[-3:]) / 3 - sum(means[-6:-3]) / 3, 1)
    elif len(means) >= 2:
        delta = round(means[-1] - means[0], 1)
    else:
        delta = 0.0

    if delta >= FORM_BAND:
        direction = 'climbing'
    elif delta <= -FORM_BAND:
        direction = 'slipping'
    else:
        direction = 'holding'

    peak = max(points, key=lambda p: p['mean']) if points else None
    return {
        'points':     points,
        'delta':      delta,
        'direction':  direction,
        'current':    points[-1]['mean'] if points else 0.0,
        'peak_mean':  peak['mean'] if peak else 0.0,
        'peak_label': peak['label'] if peak else '',
        'vs_peak':    round(points[-1]['mean'] - peak['mean'], 1) if points else 0.0,
        'depth':      sum(1 for r in depth_source if r['mean'] >= GOOD_BAND_CUTOFF),
    }


def movers(rows):
    """The four exception bands.

    Absent is computed first and its members are excluded from the other three:
    a player who did not attack is not "sliding", they are not playing, and
    that is the fact leadership needs.
    """
    absent = [r for r in rows if r['attendance'] < ABSENT_ATTENDANCE]
    absent_tags = {r['player_tag'] for r in absent}

    eligible = [r for r in rows
                if r['player_tag'] not in absent_tags
                and r['weeks_played'] >= MIN_WEEKS_FOR_TREND]

    return {
        'surging':    sorted([r for r in eligible
                              if r['trend'] is not None and r['trend'] >= TREND_BAND],
                             key=lambda r: -r['trend']),
        'sliding':    sorted([r for r in eligible
                              if r['trend'] is not None and r['trend'] <= -TREND_BAND],
                             key=lambda r: r['trend']),
        'unreliable': sorted([r for r in eligible if r['sigma'] >= UNRELIABLE_SIGMA],
                             key=lambda r: -r['sigma']),
        'absent':     sorted(absent, key=lambda r: r['attendance']),
    }


def matchup_buckets(attack_logs, th_by_season):
    """Attack performance per town-hall matchup, bucketed -2..+2 with open ends.

    A bucket below MATCHUP_MIN_N is still returned but flagged not-enough, so
    the page can say "you have only faced even matchups" rather than render a
    confident number over three attacks.
    """
    buckets = {}
    for log in attack_logs:
        own = th_by_season.get(log.league_season_id)
        if not own:
            continue
        try:
            opponent = int(log.opponent_th)
        except (TypeError, ValueError):
            opponent = own
        diff = opponent - own
        key = -2 if diff <= -2 else (2 if diff >= 2 else diff)
        bucket = buckets.setdefault(key, {'attacks': 0, '_stars': 0, '_pct': 0})
        bucket['attacks'] += 1
        bucket['_stars'] += log.stars or 0
        bucket['_pct'] += log.percentage or 0

    for bucket in buckets.values():
        n = bucket['attacks']
        bucket['avg_stars'] = round(bucket.pop('_stars') / n, 2)
        bucket['avg_pct'] = round(bucket.pop('_pct') / n, 1)
        bucket['enough'] = n >= MATCHUP_MIN_N
    return buckets


def near_misses(attack_logs):
    """Attacks that were one building short of a three-star."""
    total = len(attack_logs)
    near = sum(1 for l in attack_logs
               if (l.stars or 0) == 2 and (l.percentage or 0) >= NEAR_MISS_PCT)
    three = sum(1 for l in attack_logs if (l.stars or 0) == 3)
    return {
        'attacks':   total,
        'near':      near,
        'three':     three,
        'near_pct':  round(near / total * 100, 1) if total else 0.0,
        'three_pct': round(three / total * 100, 1) if total else 0.0,
    }


def career_markers(records):
    """Town-hall upgrades and league promotions/demotions along a career line.

    The first week is the baseline and never produces a marker.
    """
    markers = []
    for previous, current in zip(records, records[1:]):
        if current['townhall'] and previous['townhall'] and current['townhall'] != previous['townhall']:
            markers.append({
                'season_id': current['season_id'],
                'kind':      'townhall',
                'detail':    'TH%d -> TH%d' % (previous['townhall'], current['townhall']),
            })
        if current['league_rank'] and previous['league_rank'] and current['league_rank'] != previous['league_rank']:
            markers.append({
                'season_id': current['season_id'],
                'kind':      'promotion' if current['league_rank'] > previous['league_rank'] else 'demotion',
                'detail':    '%s -> %s' % (previous['league_tier'], current['league_tier']),
            })
    return markers


def _split_logs(weeks, in_clan_tags, wanted_seasons):
    """Battle logs split by direction, keyed (player_tag, season_id)."""
    attacks, defenses = {}, {}
    for w in weeks:
        if w.player_tag not in in_clan_tags or w.league_season_id not in wanted_seasons:
            continue
        key = (w.player_tag, w.league_season_id)
        for log in w.battle_logs:
            (attacks if _is_attack(log) else defenses).setdefault(key, []).append(log)
    return attacks, defenses


def build_record_page(clan_players, weeks, window):
    """Everything /ranked/stats renders, from ORM rows to plain dicts."""
    names = {p.tag: (p.name or p.tag) for p in clan_players}
    in_clan = set(names)

    season_ids = select_seasons([w for w in weeks if w.player_tag in in_clan], window)
    wanted = set(season_ids)

    labels = {}
    for w in weeks:
        sid = w.league_season_id
        if sid in wanted and sid not in labels and w.start_day:
            labels[sid] = w.start_day.strftime('%d.%m.%y')
    for sid in season_ids:
        labels.setdefault(sid, sid)

    clan_weeks = [w for w in weeks if w.player_tag in in_clan]
    records_by_tag = build_week_records(clan_weeks, season_ids)
    attack_logs, defense_logs = _split_logs(clan_weeks, in_clan, wanted)
    expectations = build_defense_expectations(records_by_tag, defense_logs)

    rows, details = [], {}
    for tag, records in records_by_tag.items():
        row = player_aggregate(records)
        row['player_tag'] = tag
        row['player_name'] = names[tag]
        row['defense'] = player_defense(tag, records, defense_logs, expectations)
        row['scores'] = [r['score'] for r in records]
        row['seasons'] = [r['season_id'] for r in records]
        rows.append(row)

        player_attacks = [l for key, logs in attack_logs.items() if key[0] == tag
                          for l in logs]
        details[tag] = {
            'records':   records,
            'markers':   career_markers(records),
            'matchups':  matchup_buckets(player_attacks,
                                         {r['season_id']: r['townhall'] for r in records}),
            'near':      near_misses(player_attacks),
            'defense':   row['defense'],
            'attendance_weeks': [
                {'season_id': r['season_id'], 'label': labels.get(r['season_id'], r['season_id']),
                 'used': r['attacks_used'], 'max': r['max_attacks'],
                 'missing': r['max_attacks'] - r['attacks_used']}
                for r in records if r['max_attacks'] > r['attacks_used']
            ],
        }

    bands = movers(rows)
    absent_tags = {r['player_tag'] for r in bands['absent']}

    roster = sorted(
        [r for r in rows
         if r['player_tag'] not in absent_tags and r['weeks_played'] >= MIN_WEEKS_FOR_RANKING],
        key=lambda r: -r['mean'])
    tail_thin = sorted(
        [r for r in rows
         if r['player_tag'] not in absent_tags and r['weeks_played'] < MIN_WEEKS_FOR_RANKING],
        key=lambda r: -r['mean'])

    return {
        'window':      window,
        'seasons':     season_ids,
        'labels':      labels,
        'form':        clan_form(records_by_tag, season_ids, labels, depth_source=roster),
        'movers':      bands,
        'roster':      roster,
        'tail_thin':   tail_thin,
        'tail_absent': bands['absent'],
        'players':     details,
    }
