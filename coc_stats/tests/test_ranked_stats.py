# -*- coding: utf-8 -*-
"""Unit tests for features.ranked.stats — the pure Ranked-record aggregation module.

Every function under test takes ORM rows (or plain objects shaped like them)
and returns plain dicts. No Flask, no DB session, no app context — so these
tests build synthetic fixtures with plain dicts and SimpleNamespace, and need
no database, no app_context(), and no environment variables to run.

Ported from nine scratchpad verification scripts (verify_stats_1..6, 9) that
accumulated while stats.py was built across Tasks 1-9 of the ranked-record
plan (verify_stats_7/8 covered the route + DB and are not pure — they do not
belong here). Grouped below by the function under test, in the order those
functions appear in stats.py, with the per-script rec()/week()/log() helpers
consolidated into the factories in the first section.
"""

import datetime as dt
from types import SimpleNamespace as NS

import pytest

from features.ranked.stats import (
    DEFENSE_BAND_MIN_N,
    FORM_BAND,
    MATCHUP_MIN_N,
    MIN_WEEKS_FOR_RANKING,
    VERDICT_BANDS,
    WINDOWS,
    build_defense_expectations,
    build_record_page,
    build_week_records,
    career_markers,
    clan_form,
    defense_band,
    matchup_buckets,
    movers,
    near_misses,
    player_aggregate,
    player_defense,
    reliability_word,
    score_trend,
    select_seasons,
)


# ── Fixture factories ────────────────────────────────────────────────────────
# Plain builder functions rather than @pytest.fixture, because most tests need
# several differently-parameterized instances in one body rather than one
# fixed value per test. Shared here once instead of duplicated per test file
# the way the nine source scripts each carried their own copy.

def battle_log(attack=True, stars=3, pct=0, opp_th=17, sid='s', tag='#A', troph=0):
    """One battle_logs row, shaped like the ORM's log objects."""
    return NS(attack=attack, stars=stars, percentage=pct, opponent_th=opp_th,
              trophies=troph, league_season_id=sid, player_tag=tag)


def ranked_week(sid, day, *, done=True, tag='#A', th=15, maxa=12, used=12,
                 tier='Witch League 17', logs=None, trophies=500, rank=10):
    """One ranked_week row: a whole week's participation for one player."""
    return NS(league_season_id=sid, start_day=dt.date(2026, 5, day), is_done=done,
              player_tag=tag, townhall=th, max_attacks=maxa, attack_wins=used,
              attack_losses=0, league_tier=tier, trophies=trophies, rank=rank,
              battle_logs=logs or [])


def attack_log(stars, pct, opp_th, sid='s1'):
    """One attack-direction battle log, for matchup_buckets / near_misses."""
    return NS(stars=stars, percentage=pct, opponent_th=opp_th,
              league_season_id=sid, attack=True)


def defense_log(trophies, stars=0):
    """One defense-direction battle log, for player_defense."""
    return NS(trophies=trophies, stars=stars)


def week_record(score=70, *, badge='badge-wow', label='Very Good', used=12, maxa=12,
                 th=15, tier='Titan League 25', rank=25, sid='s', start_day=None,
                 trophies=500, player_rank=10):
    """One already-scored week record — the dict shape build_week_records emits.

    player_aggregate, player_defense, clan_form and career_markers all consume
    this shape directly, so most tests below start here instead of
    round-tripping through build_week_records.
    """
    return {'season_id': sid, 'start_day': start_day, 'score': score, 'badge': badge,
            'label': label, 'attacks_used': used, 'max_attacks': maxa,
            'townhall': th, 'league_tier': tier, 'league_rank': rank,
            'trophies': trophies, 'rank': player_rank}


def player_row(tag, *, mean=70.0, sigma=3.0, trend=0.0, attendance=1.0, weeks=9):
    """One row shaped like a player_aggregate() output, for movers()/clan_form()."""
    return {'player_tag': tag, 'player_name': tag.strip('#'), 'mean': mean,
            'sigma': sigma, 'trend': trend, 'attendance': attendance,
            'weeks_played': weeks}


# ── select_seasons ───────────────────────────────────────────────────────────

def test_select_seasons_excludes_incomplete_and_orders_oldest_first():
    weeks = [ranked_week('s3', 20), ranked_week('s1', 4), ranked_week('s2', 11),
              ranked_week('s4', 25, done=False)]
    assert select_seasons(weeks, 'all') == ['s1', 's2', 's3']


def test_select_seasons_window_larger_than_data_returns_all():
    weeks = [ranked_week('s3', 20), ranked_week('s1', 4), ranked_week('s2', 11),
              ranked_week('s4', 25, done=False)]
    assert select_seasons(weeks, '4') == ['s1', 's2', 's3']
    assert WINDOWS['all'] is None


def test_select_seasons_window_keeps_most_recent_n():
    weeks10 = [ranked_week('s%d' % i, i + 1) for i in range(1, 9)]
    assert select_seasons(weeks10, '4') == ['s5', 's6', 's7', 's8']


# ── build_week_records ───────────────────────────────────────────────────────
#
# TH-ceiling calibration (deliberate fixture values, do not "simplify" them —
# an earlier fixture picked a same-TH opponent by mistake and silently proved
# the wrong thing):
#
# The 0-100 score divides by a per-town-hall ceiling of 3 * _max_th_multiplier(th).
# For TH<=16 that ceiling is 3 * 1.15 = 3.45, which assumes attacking TH+2 bases.
# An even-TH attack only earns _calc_th_multiplier(0, 15) = 0.95, so a TH15 player
# who only ever hits even matchups tops out below 100, no matter how well they
# attack. That is the intended behaviour of the TH-ceiling normalization, not a
# defect — it is why an even-TH week below caps at 83 rather than 100.
#
# The fixtures below use TH17 opponents (diff +2 -> multiplier 1.15, hitting the
# ceiling exactly) and league "Witch League 17", whose rank 17 equals
# EXPECTED_LEAGUE_RANK[15], making _league_mult exactly 1.0. That makes the
# arithmetic exact: a full week of triples scores exactly 100, half scores
# exactly 50, and the even-TH counterpart caps at exactly 83.

def test_build_week_records_full_ceiling_week_scores_100():
    perfect = [battle_log(True, 3, 100) for _ in range(12)]
    recs = build_week_records([ranked_week('s1', 4, logs=perfect)], ['s1'])
    assert list(recs) == ['#A']
    r = recs['#A'][0]
    assert r['score'] == 100, 'twelve ceiling-rate triples on 12 max attacks is a perfect score'
    assert r['badge'] == 'badge-godlike'
    assert r['label'] == 'Godlike', 'label must be stripped of the missing-attacks suffix'
    assert r['attacks_used'] == 12
    assert r['league_rank'] == 17
    assert r['townhall'] == 15


def test_build_week_records_even_th_week_caps_at_83():
    even_logs = [battle_log(True, 3, 100, opp_th=15) for _ in range(12)]
    even = build_week_records([ranked_week('s1', 4, logs=even_logs)], ['s1'])
    assert even['#A'][0]['score'] == 83, 'even-TH tops out below 100 by design'


def test_build_week_records_half_attacks_halves_score():
    half = [battle_log(True, 3, 100) for _ in range(6)]
    r = build_week_records([ranked_week('s1', 4, used=6, logs=half)], ['s1'])['#A'][0]
    assert r['attacks_used'] == 6, 'attacks_used comes from ranked_week, not the log count'
    assert r['score'] == 50, 'six of twelve triples halves the score'
    assert 'missing' in r['label'].lower() or r['label'] == 'Bad'


def test_build_week_records_orders_by_season_ids_not_input_order():
    perfect = [battle_log(True, 3, 100) for _ in range(12)]
    multi = [ranked_week('s2', 11, logs=perfect), ranked_week('s1', 4, logs=perfect)]
    ordered = build_week_records(multi, ['s1', 's2'])['#A']
    assert [x['season_id'] for x in ordered] == ['s1', 's2']


def test_build_week_records_drops_seasons_outside_window():
    perfect = [battle_log(True, 3, 100) for _ in range(12)]
    multi = [ranked_week('s2', 11, logs=perfect), ranked_week('s1', 4, logs=perfect)]
    assert build_week_records(multi, ['s2'])['#A'][0]['season_id'] == 's2'


# ── reliability_word ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('sigma, expected', [
    (0.0, 'metronome'), (4.9, 'metronome'),
    (5.0, 'steady'), (9.9, 'steady'),
    (10.0, 'swingy'), (14.9, 'swingy'),
    (15.0, 'erratic'), (99.0, 'erratic'),
], ids=['0.0', '4.9', '5.0', '9.9', '10.0', '14.9', '15.0', '99.0'])
def test_reliability_word_band_edges(sigma, expected):
    """Bands are exclusive at the top: 4.9 is metronome, 5.0 is already steady."""
    assert reliability_word(sigma) == expected


# ── score_trend ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('scores, expected', [
    ([50, 50, 50], None),                                  # n=3, below MIN_WEEKS_FOR_TREND
    ([], None),                                             # n=0
    ([40, 40, 60, 60], 20.0),                                # n=4, last two minus first two
    ([40, 40, 0, 60, 60], 20.0),                             # n=5, middle week ignored
    ([10, 10, 10, 20, 20, 20], 10.0),                        # n=6, last three minus prior three
    ([20, 20, 20, 10, 10, 10], -10.0),                       # n=6, falling
    ([0, 0, 0, 10, 10, 10, 20, 20, 20], 10.0),               # n=9, only the last six matter
], ids=['n=3', 'n=0', 'n=4', 'n=5', 'n=6-rising', 'n=6-falling', 'n=9'])
def test_score_trend_at_n(scores, expected):
    assert score_trend(scores) == expected


# ── player_aggregate ─────────────────────────────────────────────────────────

def test_player_aggregate_flat_series():
    a = player_aggregate([week_record(80)] * 4)
    assert a['weeks_played'] == 4
    assert a['mean'] == 80.0
    assert a['sigma'] == 0.0, 'a flat series has zero spread'
    assert a['reliability'] == 'metronome'
    assert a['trend'] == 0.0
    assert a['attendance'] == 1.0
    assert a['attacks_wasted'] == 0
    assert a['best'] == 80 and a['worst'] == 80
    assert a['verdict_record'] == {'Very Good': 4}
    assert sum(a['verdict_record'].values()) == a['weeks_played']


def test_player_aggregate_mean_badge_decoupled_from_week_badges():
    """mean_badge bands the WINDOW MEAN, not whichever badge a week happened to carry."""
    assert player_aggregate([week_record(80)])['mean_badge'] == 'badge-dominant'
    assert player_aggregate([week_record(95), week_record(95)])['mean_badge'] == 'badge-godlike'
    assert player_aggregate([week_record(60), week_record(60)])['mean_badge'] == 'badge-good'
    assert player_aggregate([week_record(10), week_record(10)])['mean_badge'] == 'badge-useless'

    # A player whose two weeks are 'Godlike' and 'Disaster' badges must NOT
    # inherit either week's badge — the mean (60) falls in the 'Good' band,
    # and mean_badge must report that band regardless of the per-week badges.
    mixed = player_aggregate([week_record(90, badge='badge-godlike'),
                              week_record(30, badge='badge-suck')])
    assert mixed['mean'] == 60.0
    assert mixed['mean_badge'] == 'badge-good', mixed['mean_badge']


def test_player_aggregate_single_week_no_division_by_zero():
    one = player_aggregate([week_record(70)])
    assert one['sigma'] == 0.0
    assert one['trend'] is None
    assert one['weeks_played'] == 1


def test_player_aggregate_attendance_sums_across_weeks():
    part = player_aggregate([week_record(50, used=6, maxa=12), week_record(50, used=12, maxa=12)])
    assert part['attendance'] == 0.75
    assert part['attacks_used'] == 18
    assert part['attacks_max'] == 24
    assert part['attacks_wasted'] == 6


def test_player_aggregate_zero_max_attacks_no_division_by_zero():
    zero = player_aggregate([week_record(0, used=0, maxa=0)])
    assert zero['attendance'] == 0.0


def test_player_aggregate_league_move_spans_first_to_last_played():
    climb = player_aggregate([week_record(70, rank=20, tier='Golem League 20'),
                              week_record(70, rank=28, tier='Dragon League 28')])
    assert climb['league_move'] == 8
    assert climb['league_now'] == 'Dragon League 28'
    assert climb['league_rank_now'] == 28


def test_player_aggregate_unranked_week_skipped_for_league_move():
    gap = player_aggregate([week_record(70, rank=0, tier=''),
                            week_record(70, rank=20, tier='Golem League 20'),
                            week_record(70, rank=25, tier='Titan League 25')])
    assert gap['league_move'] == 5


def test_player_aggregate_verdict_record_keys_on_label_not_badge():
    """Task 9: badge-useless legitimately serves both 'Useless' and 'No Attacks',
    but verdict_record must key on the label so a week the player never attacked
    is never silently counted as a week they attacked badly."""
    a = player_aggregate([
        week_record(0, badge='badge-useless', label='No Attacks'),
        week_record(10, badge='badge-useless', label='Useless'),
        week_record(90, badge='badge-godlike', label='Godlike'),
    ])
    assert a['verdict_record'] == {'No Attacks': 1, 'Useless': 1, 'Godlike': 1}
    assert sum(a['verdict_record'].values()) == 3


def test_player_aggregate_townhall_now_is_most_recent_week():
    assert player_aggregate([week_record(70, th=14), week_record(70, th=15)])['townhall_now'] == 15
    assert player_aggregate([])['townhall_now'] == 0


# ── VERDICT_BANDS ─────────────────────────────────────────────────────────────

def test_verdict_bands_eight_labels_best_to_worst_no_attacks_last():
    labels = [b[0] for b in VERDICT_BANDS]
    assert labels == ['Godlike', 'Dominant', 'Very Good', 'Good', 'Bad',
                      'Disaster', 'Useless', 'No Attacks']
    assert len(set(labels)) == 8, 'labels must be unique'
    # badge-useless legitimately serves two different labels — 'Useless' and
    # 'No Attacks' are different situations, which is exactly why
    # verdict_record (tested above) keys on label rather than badge.
    assert [b[1] for b in VERDICT_BANDS].count('badge-useless') == 2


# ── defense_band ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('league_rank, expected', [
    (0, 'unranked'), (1, '1-5'), (5, '1-5'), (6, '6-10'),
    (16, '16-20'), (20, '16-20'), (31, '31-35'),
    (33, '31-35'),  # the highest numbered non-legend league is 33
    (34, 'legend'), (36, 'legend'),
])
def test_defense_band_boundaries(league_rank, expected):
    assert defense_band(league_rank) == expected


# ── build_defense_expectations / player_defense ────────────────────────────────

@pytest.fixture
def populated_expectations():
    """A well-populated 21-25 band (player #A, rank 25) plus a thin 1-5 band
    (player #B, rank 2), shared by every build_defense_expectations /
    player_defense test that needs a realistic band table to check against."""
    fat = DEFENSE_BAND_MIN_N + 10
    records = {'#A': [week_record(sid='s1', rank=25)], '#B': [week_record(sid='s2', rank=2)]}
    logs = {('#A', 's1'): [defense_log(20)] * fat, ('#B', 's2'): [defense_log(40)] * 5}
    exp = build_defense_expectations(records, logs)
    return records, logs, exp, fat


def test_build_defense_expectations_well_populated_band_keeps_own_mean(populated_expectations):
    records, logs, exp, fat = populated_expectations
    assert exp['21-25']['n'] == fat
    assert exp['21-25']['mean'] == 20.0, 'a well-populated band keeps its own mean regardless of other bands'
    assert exp['21-25']['thin'] is False


def test_build_defense_expectations_single_band_mean_equals_global_mean():
    """When a well-populated band is the ONLY band, its mean and the clan-wide
    global mean must be identical — there is nothing else to average in."""
    fat = DEFENSE_BAND_MIN_N + 10
    records = {'#A': [week_record(sid='s1', rank=25)]}
    logs = {('#A', 's1'): [defense_log(20)] * fat}
    exp = build_defense_expectations(records, logs)
    assert exp['21-25']['n'] == fat
    assert exp['21-25']['mean'] == 20.0
    assert exp['_global']['mean'] == 20.0


def test_build_defense_expectations_thin_band_falls_back_to_global_mean(populated_expectations):
    records, logs, exp, fat = populated_expectations
    assert exp['1-5']['n'] == 5
    assert exp['1-5']['thin'] is True
    assert exp['1-5']['mean'] == exp['_global']['mean'], 'thin bands must use the global mean'
    assert exp['21-25']['thin'] is False
    assert exp['21-25']['mean'] == 20.0


def test_player_defense_index_measured_against_band_not_global_mean(populated_expectations):
    records, logs, exp, fat = populated_expectations
    pd = player_defense('#A', records['#A'], logs, exp)
    assert pd['n'] == fat
    assert pd['tpd'] == 20.0
    assert pd['index'] == 0.0, 'a player exactly at band expectation indexes to zero'
    assert pd['thin'] is False


def test_player_defense_above_band_indexes_positive(populated_expectations):
    records, logs, exp, fat = populated_expectations
    logs2 = dict(logs)
    logs2[('#C', 's1')] = [defense_log(30)] * 10
    pd2 = player_defense('#C', [week_record(sid='s1', rank=25)], logs2, exp)
    assert pd2['index'] == 10.0


def test_player_defense_no_logged_defenses_returns_nulls(populated_expectations):
    records, logs, exp, fat = populated_expectations
    pd3 = player_defense('#Z', [week_record(sid='s1', rank=25)], {}, exp)
    assert pd3 == {'n': 0, 'tpd': None, 'index': None, 'thin': True, 'star_mix': {}}


def test_player_defense_thin_band_membership_inherited(populated_expectations):
    records, logs, exp, fat = populated_expectations
    pd4 = player_defense('#B', records['#B'], logs, exp)
    assert pd4['thin'] is True


def test_player_defense_star_mix_tallies_by_star_count():
    """Task 9: star_mix is a {stars: count} tally over the player's own defenses."""
    records = {'#A': [week_record(sid='s1', rank=25)]}
    logs = {('#A', 's1'): [defense_log(40, 0), defense_log(27, 1), defense_log(14, 2),
                            defense_log(0, 3), defense_log(0, 3)]}
    exp = build_defense_expectations(records, logs)
    pd = player_defense('#A', records['#A'], logs, exp)
    assert pd['star_mix'] == {0: 1, 1: 1, 2: 1, 3: 2}
    assert sum(pd['star_mix'].values()) == pd['n']
    assert player_defense('#Z', records['#A'], {}, exp)['star_mix'] == {}


# ── clan_form ─────────────────────────────────────────────────────────────────

SEASON_IDS_6 = ['s1', 's2', 's3', 's4', 's5', 's6']
SEASON_LABELS_6 = {s: s.upper() for s in SEASON_IDS_6}


def season_scores(scores, sids=SEASON_IDS_6):
    """{'#A': [week_record per season]} for a given per-season score list."""
    return {'#A': [week_record(v, sid=s) for s, v in zip(sids, scores)]}


def test_clan_form_rising_clan():
    form = clan_form(season_scores([50, 50, 50, 70, 70, 70]), SEASON_IDS_6, SEASON_LABELS_6,
                      depth_source=[player_row('#A', mean=70.0)])
    assert [p['mean'] for p in form['points']] == [50.0, 50.0, 50.0, 70.0, 70.0, 70.0]
    assert form['points'][0]['label'] == 'S1'
    assert form['points'][0]['participants'] == 1
    assert form['delta'] == 20.0
    assert form['direction'] == 'climbing'
    assert form['current'] == 70.0
    assert form['peak_mean'] == 70.0
    assert form['vs_peak'] == 0.0


def test_clan_form_falling_clan_below_peak():
    f2 = clan_form(season_scores([70, 70, 70, 50, 50, 50]), SEASON_IDS_6, SEASON_LABELS_6,
                    depth_source=[])
    assert f2['delta'] == -20.0
    assert f2['direction'] == 'slipping'
    assert f2['peak_mean'] == 70.0
    assert f2['peak_label'] == 'S1'
    assert f2['vs_peak'] == -20.0


def test_clan_form_flat_clan_holds():
    flat = season_scores([60] * 6)
    assert clan_form(flat, SEASON_IDS_6, SEASON_LABELS_6, depth_source=[])['direction'] == 'holding'


@pytest.mark.parametrize('scores, expected_delta, expected_direction', [
    ([50, 50, 50, 52, 52, 52], FORM_BAND, 'climbing'),      # exactly +FORM_BAND must move, not hold
    ([52, 52, 52, 50, 50, 50], -FORM_BAND, 'slipping'),     # exactly -FORM_BAND must move, not hold
    ([50, 50, 50, 51, 51, 51], 1.0, 'holding'),              # just inside the band, on either side
    ([51, 51, 51, 50, 50, 50], -1.0, 'holding'),
], ids=['at+FORM_BAND', 'at-FORM_BAND', 'inside+', 'inside-'])
def test_clan_form_form_band_boundary(scores, expected_delta, expected_direction):
    # 6 seasons so the n>=6 (three-vs-three) delta formula is the one under test.
    form = clan_form(season_scores(scores), SEASON_IDS_6, SEASON_LABELS_6, depth_source=[])
    assert form['delta'] == expected_delta
    assert form['direction'] == expected_direction


def test_clan_form_season_with_no_data_is_skipped_not_zeroed():
    sparse = {'#A': [week_record(60, sid='s1'), week_record(60, sid='s3')]}
    pts = clan_form(sparse, ['s1', 's2', 's3'], {'s1': 'A', 's2': 'B', 's3': 'C'},
                    depth_source=[])['points']
    assert [p['season_id'] for p in pts] == ['s1', 's3']


def test_clan_form_empty_input_does_not_raise():
    empty = clan_form({}, [], {}, depth_source=[])
    assert empty['points'] == []
    assert empty['direction'] == 'holding'


def test_clan_form_depth_counts_players_at_or_above_good_cutoff():
    flat = season_scores([60] * 6)
    depth = clan_form(flat, SEASON_IDS_6, SEASON_LABELS_6,
                      depth_source=[player_row('#A', mean=90.0), player_row('#B', mean=58.0),
                                    player_row('#C', mean=57.9)])
    assert depth['depth'] == 2, 'the GOOD_BAND_CUTOFF (58) is inclusive at the low end'


def test_clan_form_basis_reports_which_delta_formula_was_used():
    """Task 9: basis names the branch (three-vs-three vs first-vs-last)."""
    long_form = clan_form(season_scores([50, 50, 50, 70, 70, 70]), SEASON_IDS_6, SEASON_LABELS_6,
                          depth_source=[])
    assert long_form['basis'] == 'last three seasons'
    assert long_form['delta'] == 20.0

    sids3 = ['s1', 's2', 's3']
    short_form = clan_form({'#A': [week_record(v, sid=s) for s, v in zip(sids3, [50, 60, 70])]},
                           sids3, {s: s for s in sids3}, depth_source=[])
    assert short_form['basis'] == 'first to last season'
    assert short_form['delta'] == 20.0

    assert clan_form({}, [], {}, depth_source=[])['basis'] == 'first to last season'


# ── movers ────────────────────────────────────────────────────────────────────

def test_movers_bands_sorted_and_threshold_inclusive():
    rows = [
        player_row('#surge',  trend=12.0),
        player_row('#slide',  trend=-12.0),
        player_row('#steady', trend=1.0),
        player_row('#wild',   trend=0.0, sigma=20.0),
        player_row('#gone',   trend=-30.0, sigma=25.0, attendance=0.10),
        player_row('#new',    trend=None, weeks=2),
        player_row('#edge',   trend=8.0),
    ]
    m = movers(rows)
    assert [r['player_tag'] for r in m['surging']] == ['#surge', '#edge'], \
        'TREND_BAND is inclusive, sorted by trend desc'
    assert [r['player_tag'] for r in m['sliding']] == ['#slide']
    assert [r['player_tag'] for r in m['unreliable']] == ['#wild']
    assert [r['player_tag'] for r in m['absent']] == ['#gone']


def test_movers_absent_exclusion_invariant():
    """The Absent-exclusion invariant: '#gone' has trend -30 (past TREND_BAND)
    and sigma 25 (past UNRELIABLE_SIGMA) — it would qualify for sliding AND
    unreliable — but low attendance routes it to absent FIRST and excludes it
    from every other band. A player who isn't playing is not "sliding"."""
    rows = [player_row('#gone', trend=-30.0, sigma=25.0, attendance=0.10)]
    m = movers(rows)
    assert [r['player_tag'] for r in m['absent']] == ['#gone']
    for band in ('surging', 'sliding', 'unreliable'):
        assert '#gone' not in [r['player_tag'] for r in m[band]], band


def test_movers_below_trend_minimum_appears_in_no_band():
    rows = [player_row('#new', trend=None, weeks=2)]
    m = movers(rows)
    for band in ('surging', 'sliding', 'unreliable', 'absent'):
        assert '#new' not in [r['player_tag'] for r in m[band]], band


def test_movers_empty_bands_are_lists_not_none():
    assert movers([])['surging'] == []


# ── matchup_buckets ───────────────────────────────────────────────────────────

def test_matchup_buckets_fold_arithmetic_and_enough_gate():
    th = {'s1': 15}
    logs = ([attack_log(3, 100, 12)] * 2 +               # diff -3 -> folds to -2
            [attack_log(3, 100, 13)] * 3 +                # diff -2 -> bucket -2
            [attack_log(2, 90, 14)] * 4 +                 # diff -1
            [attack_log(3, 100, 15)] * MATCHUP_MIN_N +    # diff 0, exactly at the enough gate
            [attack_log(1, 50, 18)] * 2)                  # diff +3 -> folds to +2
    b = matchup_buckets(logs, th)
    assert set(b) == {-2, -1, 0, 2}
    assert b[-2]['attacks'] == 5, 'diff -3 and diff -2 both fold into bucket -2'
    assert b[2]['attacks'] == 2, 'diff +3 folds into bucket +2'
    assert b[0]['attacks'] == MATCHUP_MIN_N
    assert b[0]['avg_stars'] == 3.0
    assert b[0]['avg_pct'] == 100.0
    assert b[0]['enough'] is True, 'a bucket at exactly MATCHUP_MIN_N is enough'
    assert b[-1]['enough'] is False, 'four attacks is not enough to render a confident bucket'


def test_matchup_buckets_skips_logs_with_unknown_season():
    th = {'s1': 15}
    assert matchup_buckets([attack_log(3, 100, 15, sid='unknown')], th) == {}


def test_matchup_buckets_unparseable_opponent_th_treated_as_even():
    th = {'s1': 15}
    weird = matchup_buckets([attack_log(3, 100, None)], th)
    assert weird[0]['attacks'] == 1


# ── near_misses ───────────────────────────────────────────────────────────────

def test_near_misses_counts_and_percentages():
    nm = near_misses([attack_log(3, 100, 15)] * 6 + [attack_log(2, 95, 15)] * 3 +
                      [attack_log(2, 70, 15)])
    assert nm['attacks'] == 10
    assert nm['three'] == 6 and nm['three_pct'] == 60.0
    assert nm['near'] == 3, 'only 2-star at or above NEAR_MISS_PCT counts'
    assert nm['near_pct'] == 30.0


def test_near_misses_empty_does_not_divide_by_zero():
    assert near_misses([])['near_pct'] == 0.0


@pytest.mark.parametrize('pct, expected_near', [(90, 1), (89, 0)],
                         ids=['at-90-counts', 'at-89-does-not'])
def test_near_misses_inclusive_at_exactly_90(pct, expected_near):
    assert near_misses([attack_log(2, pct, 15)])['near'] == expected_near


# ── career_markers ────────────────────────────────────────────────────────────

def test_career_markers_first_week_never_emits_and_transitions_are_flagged():
    records = [
        week_record(sid='s1', th=15, rank=20, tier='Golem League 20'),
        week_record(sid='s2', th=15, rank=22, tier='P.E.K.K.A League 22'),
        week_record(sid='s3', th=16, rank=22, tier='P.E.K.K.A League 22'),
        week_record(sid='s4', th=16, rank=20, tier='Golem League 20'),
    ]
    marks = career_markers(records)
    kinds = [(m['season_id'], m['kind']) for m in marks]
    assert ('s2', 'promotion') in kinds
    assert ('s3', 'townhall') in kinds
    assert ('s4', 'demotion') in kinds
    assert not [m for m in marks if m['season_id'] == 's1'], \
        'the first week is the baseline, never a change'

    th_mark = [m for m in marks if m['kind'] == 'townhall'][0]
    assert th_mark['detail'] == 'TH15 -> TH16'


def test_career_markers_empty_and_single_week():
    assert career_markers([]) == []
    assert career_markers([week_record(sid='s1', th=15, rank=20, tier='Golem League 20')]) == []


# ── build_record_page ─────────────────────────────────────────────────────────

def strong_logs(sid):
    return [battle_log(True, 3, 100, sid=sid, opp_th=15) for _ in range(12)] + \
           [battle_log(False, 1, 70, sid=sid, opp_th=15, troph=27)]


def weak_logs(sid):
    return [battle_log(True, 1, 40, sid=sid, opp_th=15) for _ in range(12)] + \
           [battle_log(False, 3, 100, sid=sid, opp_th=15, troph=0)]


def clan_week(tag, sid, day, logs, *, used=12, maxa=12, done=True, th=15,
              tier='Titan League 25'):
    return NS(league_season_id=sid, start_day=dt.date(2026, 5, day), is_done=done,
              player_tag=tag, townhall=th, max_attacks=maxa, attack_wins=used,
              attack_losses=0, league_tier=tier, trophies=500, rank=10,
              battle_logs=logs)


@pytest.fixture
def clan_page_fixture():
    """Three players across four completed seasons plus one live season:
    #A strong and full-history, #B weak and full-history, #C strong but only
    one week played (falls into the thin tail, not the ranked roster)."""
    players = [NS(tag='#A', name='Ace'), NS(tag='#B', name='Bit'), NS(tag='#C', name='Cy')]
    weeks = []
    for i, day in enumerate([4, 11, 18, 25], start=1):
        sid = 's%d' % i
        weeks.append(clan_week('#A', sid, day, strong_logs(sid)))
        weeks.append(clan_week('#B', sid, day, weak_logs(sid)))
    weeks.append(clan_week('#C', 's1', 4, strong_logs('s1')))                # too few weeks
    weeks.append(clan_week('#A', 's9', 30, strong_logs('s9'), done=False))   # live season
    return players, weeks


def test_build_record_page_seasons_and_labels_exclude_live(clan_page_fixture):
    players, weeks = clan_page_fixture
    page = build_record_page(players, weeks, 'all')
    assert page['window'] == 'all'
    assert page['seasons'] == ['s1', 's2', 's3', 's4'], 'the live season must be excluded'
    assert 's9' not in page['labels']
    assert page['labels']['s1'] == '04.05.26'


def test_build_record_page_roster_sorted_and_excludes_thin_tail(clan_page_fixture):
    players, weeks = clan_page_fixture
    page = build_record_page(players, weeks, 'all')
    tags = [r['player_tag'] for r in page['roster']]
    assert tags == ['#A', '#B']
    assert page['roster'][0]['player_name'] == 'Ace'
    assert page['roster'][0]['mean'] > page['roster'][1]['mean']

    assert [r['player_tag'] for r in page['tail_thin']] == ['#C']
    assert page['tail_thin'][0]['weeks_played'] < MIN_WEEKS_FOR_RANKING
    assert page['tail_absent'] == []


def test_build_record_page_roster_rows_carry_defense_axis(clan_page_fixture):
    players, weeks = clan_page_fixture
    page = build_record_page(players, weeks, 'all')
    assert page['roster'][0]['defense']['n'] == 4
    assert page['roster'][0]['defense']['index'] is not None


def test_build_record_page_form_covers_every_season_with_data(clan_page_fixture):
    players, weeks = clan_page_fixture
    page = build_record_page(players, weeks, 'all')
    assert len(page['form']['points']) == 4
    assert page['form']['direction'] in ('climbing', 'holding', 'slipping')


def test_build_record_page_drill_down_present_for_every_player(clan_page_fixture):
    players, weeks = clan_page_fixture
    page = build_record_page(players, weeks, 'all')
    assert set(page['players']) == {'#A', '#B', '#C'}
    detail = page['players']['#A']
    assert len(detail['records']) == 4
    assert detail['near']['three_pct'] == 100.0
    assert detail['matchups'][0]['attacks'] == 48
    assert detail['markers'] == [], 'a static career has no markers'
    assert detail['attendance_weeks'] == [], 'full attendance lists no short weeks'


def test_build_record_page_short_week_listed_in_attendance():
    short = [clan_week('#D', 's1', 4, strong_logs('s1'), used=6)]
    page = build_record_page([NS(tag='#D', name='Dee')], short, 'all')
    assert page['players']['#D']['attendance_weeks'][0]['missing'] == 6


def test_build_record_page_absent_players_held_out_of_roster():
    absent_weeks = [
        clan_week('#E', 's%d' % i, d,
                  [battle_log(False, 3, 100, sid='s%d' % i, opp_th=15, troph=0)], used=0)
        for i, d in enumerate([4, 11, 18, 25], start=1)
    ]
    page = build_record_page([NS(tag='#E', name='Eve')], absent_weeks, 'all')
    assert page['roster'] == []
    assert [r['player_tag'] for r in page['tail_absent']] == ['#E']
    assert [r['player_tag'] for r in page['movers']['absent']] == ['#E']


def test_build_record_page_empty_clan_does_not_raise():
    blank = build_record_page([], [], 'all')
    assert blank['roster'] == []
    assert blank['seasons'] == []
    assert blank['players'] == {}


def test_build_record_page_ignores_non_clan_players(clan_page_fixture):
    players, weeks = clan_page_fixture
    outsider = weeks + [clan_week('#ZZ', 's1', 4, strong_logs('s1'))]
    assert '#ZZ' not in build_record_page(players, outsider, 'all')['players']


# ── build_record_page: live_season (Task 9) ────────────────────────────────────

def test_build_record_page_live_season_surfaced_not_hidden():
    players = [NS(tag='#A', name='Ace')]
    weeks = [clan_week('#A', 's%d' % i, i + 3, []) for i in range(1, 5)]
    weeks.append(clan_week('#A', 'live', 30, [], done=False))
    page = build_record_page(players, weeks, 'all')
    assert 'live' not in page['seasons'], 'the live season must stay out of the math'
    assert page['live_season'] is not None
    assert page['live_season']['label'] == '30.05.26'
    assert page['live_season']['participants'] == 1


def test_build_record_page_no_live_season_is_none():
    players = [NS(tag='#A', name='Ace')]
    weeks = [clan_week('#A', 's%d' % i, i + 3, []) for i in range(1, 5)]
    page = build_record_page(players, weeks, 'all')
    assert page['live_season'] is None
