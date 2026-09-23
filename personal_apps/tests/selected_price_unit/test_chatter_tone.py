"""P04: aligned chatter slots and retained tone, unknown versus zero."""
import datetime as dt
from decimal import Decimal

import pytest

from features.radar import chatter_tone
from features.radar import price_chart_contract as c

from .helpers import bucket, naive, tone_row, utc

DAY = c.window_for('1D', utc(2026, 9, 15, 9, 37))       # 08:00Z .. 09:37Z, seven 15-minute slots
QUARTERS = [naive(2026, 9, 15, 8) + dt.timedelta(minutes=15 * i) for i in range(7)]
FLOOR = naive(2026, 1, 1)


def slots(rows, window=DAY, floor=FLOOR):
    return c.chatter_slots(rows, window, identity_floor=floor)


def test_observed_partial_and_the_clipped_final_bucket():
    rows = [bucket(q, 'bluesky', 2) for q in QUARTERS]
    rows += [bucket(q, 'fourchan', 1) for q in QUARTERS if q != QUARTERS[2]]
    out = slots(rows)['slots']
    assert [s['count'] for s in out] == [3, 3, 2, 3, 3, 3, 3]
    assert [s['coverage'] for s in out] == ['observed', 'observed', 'partial', 'observed',
                                            'observed', 'observed', 'partial']
    assert (out[-1]['start'], out[-1]['end']) == ('2026-09-15T09:30:00Z', '2026-09-15T09:37:00Z')


def test_only_recorded_zero_is_zero_and_nothing_recorded_is_unknown():
    zero = slots([bucket(q, 'bluesky', 0) for q in QUARTERS])['slots']
    assert [s['count'] for s in zero] == [0] * 7 and zero[0]['coverage'] == 'observed'
    none = slots([])
    assert [s['count'] for s in none['slots']] == [None] * 7
    assert {s['coverage'] for s in none['slots']} == {'unknown'}
    assert c.tone_slots(none, {}, retained_from=naive(2026, 9, 14)) == [None] * 7


def test_identical_duplicates_count_once_and_conflicting_ones_make_the_source_unknown():
    same = slots([bucket(QUARTERS[0], 'bluesky', 2), bucket(QUARTERS[0], 'bluesky', 2)])['slots']
    assert same[0]['count'] == 2
    conflict = slots([bucket(QUARTERS[0], 'bluesky', 2), bucket(QUARTERS[0], 'bluesky', 5),
                      bucket(QUARTERS[0], 'fourchan', 1)])
    assert (conflict['slots'][0]['count'], conflict['slots'][0]['coverage']) == (1, 'partial')
    assert any('conflicting duplicate' in w for w in conflict['warnings'])
    alone = slots([bucket(QUARTERS[0], 'bluesky', 2), bucket(QUARTERS[0], 'bluesky', 5)])['slots']
    assert (alone[0]['count'], alone[0]['coverage']) == (None, 'unknown')


@pytest.mark.parametrize('row', [bucket(QUARTERS[0], 'bluesky', -1), bucket(QUARTERS[0], 'bluesky', '3'),
                                 bucket(QUARTERS[0], 'bluesky', True), bucket(QUARTERS[0], 'bluesky', 3, 'weird')])
def test_malformed_counts_are_unknown_not_zero(row):
    assert slots([row])['slots'][0]['count'] is None


def test_missing_status_is_not_zero_and_truncated_is_partial():
    out = slots([bucket(QUARTERS[0], 'bluesky', 0, 'missing'), bucket(QUARTERS[1], 'bluesky', 4, 'truncated'),
                 bucket(QUARTERS[1], 'fourchan', 1)])['slots']
    assert out[0]['count'] is None
    assert (out[1]['count'], out[1]['truncated'], out[1]['coverage']) == (5, True, 'partial')


def test_bare_reddit_and_a_subreddit_in_one_bucket_withhold_the_total():
    out = slots([bucket(QUARTERS[0], 'reddit', 2), bucket(QUARTERS[0], 'reddit:wallstreetbets', 3),
                 bucket(QUARTERS[1], 'reddit:wallstreetbets', 3)])
    assert (out['slots'][0]['count'], out['slots'][0]['overlap_ambiguous']) == (None, True)
    assert (out['slots'][1]['count'], out['slots'][1]['overlap_ambiguous']) == (3, False)
    assert c.tone_slots(out, {}, retained_from=naive(2026, 9, 14))[0] is None


def test_1w_slots_anchor_at_09_30_and_config_changes_are_flagged_where_they_happen():
    week = c.window_for('1W', utc(2026, 9, 15, 14, 7))
    rows = [bucket(naive(2026, 9, 15, 13, 30), config='v1'), bucket(naive(2026, 9, 15, 13, 45), config='v2'),
            bucket(naive(2026, 9, 15, 14, 0), config='v2')]
    out = slots(rows, week)
    assert len(out['slots']) == 145
    assert (out['slots'][0]['start'], out['slots'][0]['end']) == ('2026-09-09T13:30:00Z', '2026-09-09T14:30:00Z')
    last = out['slots'][-1]
    assert (last['start'], last['end'], last['count']) == ('2026-09-15T13:30:00Z', '2026-09-15T14:07:00Z', 3)
    assert last['config_transition'] is True and last['coverage'] == 'partial'
    assert not any(s['config_transition'] for s in out['slots'][:-1])


def test_before_the_company_record_is_unknown():
    out = slots([bucket(q) for q in QUARTERS], floor=naive(2026, 9, 15, 8, 20))
    assert [s['count'] for s in out['slots'][:3]] == [None, None, 1]
    assert out['slots'][0]['coverage'] == 'unknown'
    assert any('precede the company record' in w for w in out['warnings'])


def test_row_and_source_bounds_refuse():
    with pytest.raises(c.ChartError) as error:
        slots([bucket(QUARTERS[0])] * (c.SOURCE_ROW_LIMIT + 1))
    assert (error.value.code, error.value.status) == ('read_limit', 503)
    with pytest.raises(c.ChartError):
        slots([bucket(QUARTERS[0], f'src{i}') for i in range(c.MAX_SOURCES + 1)])


def test_tone_reconciles_to_the_new_slot_totals():
    chatter = slots([bucket(QUARTERS[0], 'bluesky', 3), bucket(QUARTERS[0], 'fourchan', 2)])
    aggregates = {('bluesky', QUARTERS[0]): tone_row(QUARTERS[0], 'bluesky', bullish=Decimal(2), bearish=1),
                  ('fourchan', QUARTERS[0]): tone_row(QUARTERS[0], 'fourchan', neutral=1, unjudged=1)}
    tone = c.tone_slots(chatter, aggregates, retained_from=naive(2026, 9, 14))
    assert tone[0] == {'bullish': 2, 'bearish': 1, 'neutral': 1, 'unjudged': 1, 'unavailable': 0,
                       'status': 'complete'}
    for slot, part in zip(chatter['slots'], tone):
        if slot['count'] is not None:
            assert sum(part[k] for k in c.TONE_CATEGORIES) == slot['count']


def test_expired_missing_conflicting_or_mismatched_evidence_is_unavailable_never_neutral():
    chatter = slots([bucket(QUARTERS[0], 'bluesky', 3), bucket(QUARTERS[0], 'fourchan', 2)])
    good = tone_row(QUARTERS[0], 'bluesky', bullish=3)
    expired = c.tone_slots(chatter, {('bluesky', QUARTERS[0]): good}, retained_from=QUARTERS[1])
    assert (expired[0]['unavailable'], expired[0]['neutral'], expired[0]['status']) == (5, 0, 'unavailable')
    missing = c.tone_slots(chatter, {('bluesky', QUARTERS[0]): good}, retained_from=naive(2026, 9, 14))
    assert (missing[0]['bullish'], missing[0]['unavailable'], missing[0]['status']) == (3, 2, 'partial')
    conflicted = dict(good, eligibility_conflicts=1)
    assert c.tone_slots(chatter, {('bluesky', QUARTERS[0]): conflicted},
                        retained_from=naive(2026, 9, 14))[0]['unavailable'] == 5
    short = tone_row(QUARTERS[0], 'bluesky', bullish=2)          # 2 judged events for a count of 3
    assert c.tone_slots(chatter, {('bluesky', QUARTERS[0]): short},
                        retained_from=naive(2026, 9, 14))[0]['unavailable'] == 5


def test_a_tone_failure_colours_counts_unavailable_and_leaves_them_standing():
    chatter = slots([bucket(QUARTERS[0], 'bluesky', 3)])
    tone = c.tone_slots(chatter, {}, retained_from=naive(2026, 9, 14), failure='read_limit')
    assert tone[0] == {'bullish': 0, 'bearish': 0, 'neutral': 0, 'unjudged': 0, 'unavailable': 3,
                       'status': 'unavailable'}
    assert tone[1] is None and chatter['slots'][0]['count'] == 3


def test_reuses_the_existing_reconciliation_and_classification():
    assert c.tone_slots.__code__.co_names.count('reconcile_slot') >= 1
    assert chatter_tone.classify_recorded_tone(attitude=None, llm_sentiment=None, lexicon_sentiment=0.9) == 'unjudged'
