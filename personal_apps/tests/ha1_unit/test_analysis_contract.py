"""HA1 pure contract tests (PLAN C01-C10). DB-free: run with
`py -3.12 -m pytest --confcutdir=tests/ha1_unit tests/ha1_unit -q` from
personal_apps so tests/conftest.py (which imports the app and its DB) is not
collected."""
import datetime as dt
import json
from decimal import Decimal

import pytest

from features.radar import analysis_contract as ac

NOW = dt.datetime(2026, 9, 14, 12, 30, tzinfo=dt.timezone.utc)
FIRST_SEEN = dt.datetime(2026, 1, 1)
INSTRUMENT = {'id': 7, 'ticker': 'AAA', 'market': 'us', 'mic': 'XNYS',
              'venue': 'NYSE', 'currency': 'USD', 'provider_symbol': 'AAA',
              'mapped_at': dt.datetime(2026, 8, 1)}


def d(day):
    return dt.date(2026, 9, day)


def us_calendar(day):
    from features.radar.market_calendars import us
    return 'modeled_open' if us.is_trading_day(day) else 'modeled_closed'


def unknown_calendar(day):
    return 'unknown'


def close_row(day, close='10.5', **over):
    row = {'close_date': d(day),
           'close': Decimal(close) if close is not None else None, 'currency': 'USD',
           'source': 'massive_grouped', 'price_basis': 'close',
           'adjustment_basis': 'split', 'market': 'us', 'mic': 'XNYS',
           'is_shadow': False,
           'fetched_at': dt.datetime(2026, 9, day, 23, 0)}
    row.update(over)
    return row


def bucket(day, slot, source='bluesky', count=1, status='ok',
           config='cfgA', **over):
    row = {'bucket_start': dt.datetime(2026, 9, day) + dt.timedelta(minutes=15 * slot),
           'source': source, 'mention_count': count, 'status': status,
           'source_config_version': config}
    row.update(over)
    return row


def full_day(day, source='bluesky', count=0, status='ok', config='cfgA'):
    return [bucket(day, s, source, count, status, config) for s in range(96)]


# --- C01 range -------------------------------------------------------------

class TestParseRange:
    def test_default_is_the_last_seven_completed_utc_days(self):
        assert ac.default_range(NOW) == (d(7), d(13))

    def test_default_uses_utc_not_local_date(self):
        late = dt.datetime(2026, 9, 14, 23, 59, tzinfo=dt.timezone.utc)
        assert ac.default_range(late) == (d(7), d(13))
        early = dt.datetime(2026, 9, 15, 0, 0, tzinfo=dt.timezone.utc)
        assert ac.default_range(early) == (d(8), d(14))

    def test_explicit_seven_and_one_day_ranges_are_accepted(self):
        args = [('instrument_id', '7'), ('from', '2026-09-07'), ('to', '2026-09-13')]
        assert ac.parse_range(args, NOW) == (d(7), d(13))
        one = [('instrument_id', '7'), ('from', '2026-09-13'), ('to', '2026-09-13')]
        assert ac.parse_range(one, NOW) == (d(13), d(13))

    def test_a_historical_window_is_accepted_without_shifting(self):
        args = [('instrument_id', '7'), ('from', '2026-03-02'), ('to', '2026-03-04')]
        assert ac.parse_range(args, NOW) == (dt.date(2026, 3, 2), dt.date(2026, 3, 4))

    @pytest.mark.parametrize('pairs, code', [
        ([('instrument_id', '7'), ('from', '2026-09-13'), ('to', '2026-09-07')], 'reversed_range'),
        ([('instrument_id', '7'), ('from', '2026-09-06'), ('to', '2026-09-13')], 'range_too_long'),
        ([('instrument_id', '7'), ('from', '2026-09-08'), ('to', '2026-09-14')], 'range_not_completed'),
        ([('instrument_id', '7'), ('from', '2026-09-20'), ('to', '2026-09-21')], 'range_not_completed'),
        ([('instrument_id', '7'), ('from', '2026-02-29'), ('to', '2026-03-01')], 'invalid_date'),
        ([('instrument_id', '7'), ('from', '2026-9-7'), ('to', '2026-09-13')], 'invalid_date'),
        ([('instrument_id', '7'), ('from', '2026-09-07T00:00'), ('to', '2026-09-13')], 'invalid_date'),
        ([('instrument_id', '7'), ('from', '2026-09-07'), ('to', '2026-09-13'), ('to', '2026-09-12')], 'duplicate_query'),
        ([('instrument_id', '7'), ('from', '2026-09-07'), ('to', '2026-09-13'), ('span', '1D')], 'unknown_query'),
        ([('instrument_id', '7'), ('from', '2026-09-07')], 'missing_query'),
        ([('from', '2026-09-07'), ('to', '2026-09-13')], 'missing_query'),
        ([('instrument_id', '0'), ('from', '2026-09-07'), ('to', '2026-09-13')], 'invalid_id'),
        ([('instrument_id', '-3'), ('from', '2026-09-07'), ('to', '2026-09-13')], 'invalid_id'),
        ([('instrument_id', '7x'), ('from', '2026-09-07'), ('to', '2026-09-13')], 'invalid_id'),
    ])
    def test_invalid_input_is_rejected_with_a_stable_code(self, pairs, code):
        with pytest.raises(ac.ContractError) as info:
            ac.parse_range(pairs, NOW)
        assert info.value.code == code
        assert info.value.status == 400

    def test_a_multidict_is_read_with_every_repeated_value(self):
        class MD:
            def __init__(self, pairs):
                self.pairs = pairs

            def items(self, multi=False):
                return list(self.pairs)
        with pytest.raises(ac.ContractError) as info:
            ac.parse_range(MD([('instrument_id', '7'), ('from', '2026-09-07'),
                               ('from', '2026-09-08'), ('to', '2026-09-13')]), NOW)
        assert info.value.code == 'duplicate_query'

    def test_instrument_id_is_parsed_alongside(self):
        assert ac.parse_instrument_id([('instrument_id', '42')]) == 42


# --- C03 interior missing ----------------------------------------------------

class TestInteriorMissing:
    def test_planner_oracle_examples(self):
        assert ac.interior_missing({d(8), d(9)}, {d(8), d(9)}) == []
        assert ac.interior_missing({d(8), d(10)}, {d(8), d(9), d(10)}) == [d(9)]
        assert ac.interior_missing({d(8)}, {d(8), d(9)}) is None
        assert ac.interior_missing({d(8), d(11)}, None) is None

    def test_edges_are_not_interior_and_none_dates_are_ignored(self):
        assert ac.interior_missing({d(9), d(10)}, {d(7), d(8), d(9), d(10), d(11), None}) == []
        assert ac.interior_missing({d(8), d(11)}, {d(8), d(9), d(10), d(11)}) == [d(9), d(10)]


# --- C03/C04/C05/C10 price ---------------------------------------------------

class TestPriceDays:
    def test_every_requested_date_is_present_independently(self):
        out = ac.price_days([], INSTRUMENT, FIRST_SEEN, d(7), d(13), us_calendar)
        assert [p['date'] for p in out['days']] == [f'2026-09-{n:02d}' for n in range(7, 14)]
        assert all(p['state'] == 'missing' and p['close'] is None for p in out['days'])
        assert out['usable_count'] == 0
        assert out['first_usable'] is None and out['last_usable'] is None
        assert out['interior_modeled_missing'] is None
        assert out['official_completeness'] == 'unknown'
        assert out['regime_changed'] is False
        assert out['resolution'] == 'daily_close'

    def test_calendar_hints_are_modeled_and_labor_day_is_closed(self):
        out = ac.price_days([], INSTRUMENT, FIRST_SEEN, d(5), d(8), us_calendar)
        hints = {p['date']: p['calendar_hint'] for p in out['days']}
        assert hints == {'2026-09-05': 'modeled_closed', '2026-09-06': 'modeled_closed',
                         '2026-09-07': 'modeled_closed', '2026-09-08': 'modeled_open'}

    def test_one_close_is_a_dot_and_two_adjacent_closes_have_no_interior_gap(self):
        one = ac.price_days([close_row(9)], INSTRUMENT, FIRST_SEEN, d(7), d(13), us_calendar)
        assert one['usable_count'] == 1
        assert one['first_usable'] == one['last_usable'] == '2026-09-09'
        assert one['interior_modeled_missing'] is None
        two = ac.price_days([close_row(8), close_row(9)], INSTRUMENT, FIRST_SEEN,
                            d(7), d(13), us_calendar)
        assert two['interior_modeled_missing'] == []
        assert two['days'][1]['close'] == 10.5 and two['days'][1]['state'] == 'observed'
        assert two['days'][1]['regime'] == two['days'][2]['regime']

    def test_an_interior_modeled_open_date_without_a_close_is_a_gap(self):
        out = ac.price_days([close_row(8), close_row(10)], INSTRUMENT, FIRST_SEEN,
                            d(7), d(13), us_calendar)
        assert out['interior_modeled_missing'] == ['2026-09-09']
        # 11 (Fri) has no close but is an EDGE, not interior; weekend is not a gap.
        assert '2026-09-11' not in out['interior_modeled_missing']

    def test_weekend_between_closes_is_not_a_gap_but_unknown_calendar_gives_null(self):
        rows = [close_row(11), close_row(14)]
        known = ac.price_days(rows, INSTRUMENT, FIRST_SEEN, d(10), d(14), us_calendar)
        assert known['interior_modeled_missing'] == []
        other = dict(INSTRUMENT, mic='XXXX')
        unknown = ac.price_days([close_row(11, mic='XXXX'), close_row(14, mic='XXXX')],
                                other, FIRST_SEEN, d(10), d(14), unknown_calendar)
        assert unknown['interior_modeled_missing'] is None
        assert {p['calendar_hint'] for p in unknown['days']} == {'unknown'}

    def test_a_close_on_a_modeled_closed_day_stays_observed_with_a_warning(self):
        out = ac.price_days([close_row(7)], INSTRUMENT, FIRST_SEEN, d(7), d(8), us_calendar)
        assert out['days'][0]['state'] == 'observed'
        assert out['days'][0]['calendar_hint'] == 'modeled_closed'
        assert any('modeled_closed' in w for w in out['warnings'])

    @pytest.mark.parametrize('over, reason', [
        ({'source': None}, 'source'),
        ({'source': '  '}, 'source'),
        ({'price_basis': None}, 'price_basis'),
        ({'adjustment_basis': None}, 'adjustment_basis'),
        ({'currency': 'EUR'}, 'currency'),
        ({'close': Decimal('0')}, 'close'),
        ({'close': Decimal('-1')}, 'close'),
        ({'close': None}, 'close'),
    ])
    def test_unusable_selected_rows_are_invalid_not_zero(self, over, reason):
        out = ac.price_days([close_row(9, **over)], INSTRUMENT, FIRST_SEEN, d(9), d(9), us_calendar)
        day = out['days'][0]
        assert day['state'] == 'invalid'
        assert day['close'] is None
        assert reason in day['reason']
        assert out['usable_count'] == 0

    def test_invalid_row_keeps_safe_provenance(self):
        out = ac.price_days([close_row(9, currency='EUR')], INSTRUMENT, FIRST_SEEN,
                            d(9), d(9), us_calendar)
        day = out['days'][0]
        assert day['source'] == 'massive_grouped' and day['fetched_at'] == '2026-09-09T23:00:00Z'

    @pytest.mark.parametrize('over', [
        {'mic': None}, {'mic': 'XNAS'}, {'market': 'de'}, {'is_shadow': True},
        {'fetched_at': dt.datetime(2026, 9, 14, 12, 31)}, {'close_date': d(20)},
    ])
    def test_other_identity_shadow_future_and_out_of_range_rows_are_excluded(self, over):
        out = ac.price_days([close_row(9, **over)], INSTRUMENT, FIRST_SEEN, d(9), d(9),
                            us_calendar, read_started_at=NOW)
        assert out['days'][0]['state'] == 'missing'
        assert out['days'][0]['source'] is None

    def test_an_excluded_row_does_not_replace_a_valid_selected_one(self):
        rows = [close_row(9, mic='XNAS', close='99'), close_row(9)]
        out = ac.price_days(rows, INSTRUMENT, FIRST_SEEN, d(9), d(9), us_calendar)
        assert out['days'][0]['close'] == 10.5

    def test_an_invalid_gap_is_a_missing_usable_observation_with_its_reason(self):
        rows = [close_row(8), close_row(9, currency='EUR'), close_row(10)]
        out = ac.price_days(rows, INSTRUMENT, FIRST_SEEN, d(8), d(10), us_calendar)
        assert out['interior_modeled_missing'] == ['2026-09-09']
        assert out['days'][1]['state'] == 'invalid'

    def test_regime_runs_break_on_source_or_basis_change(self):
        rows = [close_row(8, source='finnhub'), close_row(9, source='massive_grouped'),
                close_row(10, source='finnhub'), close_row(11, source='finnhub', close='250')]
        out = ac.price_days(rows, INSTRUMENT, FIRST_SEEN, d(8), d(11), us_calendar)
        regimes = [p['regime'] for p in out['days']]
        assert regimes[0] == regimes[2] == regimes[3] and regimes[1] != regimes[0]
        assert out['regime_changed'] is True
        assert ac.regime_runs(out['days']) == [['2026-09-08'], ['2026-09-09'],
                                                ['2026-09-10', '2026-09-11']]
        # A split-like jump inside one stamp is NOT an event: nothing is
        # inferred from the 10.5 -> 250 move and no return is calculated.
        assert not any('jump' in w or 'corporate' in w for w in out['warnings'])
        assert all('return' not in p for p in out['days'])

    def test_rows_before_first_seen_are_identity_unverified(self):
        rows = [close_row(8), close_row(9)]
        out = ac.price_days(rows, INSTRUMENT, dt.datetime(2026, 9, 9, 15, 0), d(8), d(9), us_calendar)
        assert out['days'][0]['state'] == 'identity_unverified'
        assert out['days'][0]['close'] is None
        assert out['days'][0]['source'] == 'massive_grouped'
        # Same-day precision: the day of first_seen itself counts as verified
        # only conservatively -- the date is >= first_seen's UTC date.
        assert out['days'][1]['state'] == 'observed'
        assert out['usable_count'] == 1
        assert any('identity' in w for w in out['warnings'])

    def test_close_dates_are_dates_not_fabricated_timestamps(self):
        out = ac.price_days([close_row(9)], INSTRUMENT, FIRST_SEEN, d(9), d(9), us_calendar)
        assert out['days'][0]['date'] == '2026-09-09'
        assert 'T' not in out['days'][0]['date']


# --- C06-C10 chatter ---------------------------------------------------------

class TestChatterDays:
    def test_no_rows_is_unavailable_not_zero(self):
        out = ac.chatter_days([], d(7), d(13), FIRST_SEEN)
        assert len(out['days']) == 7
        for day in out['days']:
            assert day['mentions'] is None and day['coverage'] == 'unavailable'
            assert day['sources'] == [] and day['configured_source_coverage'] == 'unknown'
        assert out['first_observed'] is None and out['last_observed'] is None
        assert out['resolution'] == 'daily_counts' and out['input_minutes'] == 15

    def test_ninety_six_ok_zero_slots_is_observed_zero(self):
        out = ac.chatter_days(full_day(9), d(9), d(9), FIRST_SEEN)
        day = out['days'][0]
        assert day['mentions'] == 0 and day['coverage'] == 'observed'
        src = day['sources'][0]
        assert src['source'] == 'bluesky' and src['mentions'] == 0
        assert src['ok_slots'] == 96 and src['coverage'] == 'observed_full_day'
        assert src['expected_slots'] == 96 and src['absent_slots'] == 0
        assert src['config_versions'] == ['cfgA'] and src['transition'] is False
        assert out['first_observed'] == '2026-09-09T00:00:00Z'
        assert out['last_observed'] == '2026-09-09T23:45:00Z'

    def test_ninety_five_ok_plus_one_absent_is_partial_zero(self):
        out = ac.chatter_days(full_day(9)[:95], d(9), d(9), FIRST_SEEN)
        day = out['days'][0]
        assert day['mentions'] == 0 and day['coverage'] == 'partial'
        assert day['sources'][0]['absent_slots'] == 1
        assert day['sources'][0]['coverage'] == 'partial'

    def test_one_ok_zero_and_one_missing_is_partial_zero_and_missing_gives_nothing(self):
        rows = [bucket(9, 0, count=0, status='ok'), bucket(9, 1, count=5, status='missing')]
        out = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        src = out['days'][0]['sources'][0]
        assert src['mentions'] == 0 and src['ok_slots'] == 1 and src['missing_slots'] == 1
        assert src['absent_slots'] == 94 and src['coverage'] == 'partial'

    def test_a_source_absent_all_window_is_never_borrowed(self):
        rows = full_day(9, source='bluesky', count=3)
        out = ac.chatter_days(rows, d(8), d(9), FIRST_SEEN)
        assert [s['source'] for s in out['days'][0]['sources']] == ['bluesky']
        assert out['days'][0]['sources'][0]['coverage'] == 'unavailable'
        assert out['days'][0]['sources'][0]['mentions'] is None
        assert out['days'][0]['mentions'] is None and out['days'][0]['coverage'] == 'unavailable'
        assert out['days'][1]['mentions'] == 288

    def test_truncated_counts_and_missing_are_partial_never_extrapolated(self):
        rows = ([bucket(9, s, count=1, status='ok') for s in range(3)]
                + [bucket(9, s, count=1, status='truncated') for s in range(3, 5)]
                + [bucket(9, s, count=99, status='missing') for s in range(5, 96)])
        out = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        src = out['days'][0]['sources'][0]
        assert src['mentions'] == 5 and src['coverage'] == 'partial'
        assert (src['ok_slots'], src['truncated_slots'], src['missing_slots']) == (3, 2, 91)
        assert out['days'][0]['mentions'] == 5 and out['days'][0]['coverage'] == 'partial'

    def test_negative_count_and_unknown_status_are_invalid_slots_and_a_misaligned_row_is_excluded(self):
        rows = [bucket(9, 0, count=-1), bucket(9, 1, count=2, status='weird'),
                bucket(9, 2, count=2, bucket_start=dt.datetime(2026, 9, 9, 0, 37)),
                bucket(9, 3, count='4'), bucket(9, 4, count=4)]
        out = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        src = out['days'][0]['sources'][0]
        assert src['invalid_slots'] == 3 and src['ok_slots'] == 1 and src['mentions'] == 4
        # The 00:37 row is not a slot: it is an excluded source-bucket row.
        assert src['excluded_rows'] == 1 and out['days'][0]['excluded_rows'] == 1
        assert src['coverage'] == 'partial'
        assert _partition(src) == 96

    def test_unaligned_rows_stay_outside_the_96_slot_partition(self):
        # REVIEW-1 repro #2: a full ok day plus two off-grid rows used to sum
        # to 98 slots and still read as partial for an unstated reason.
        rows = full_day(9, count=1) + [
            bucket(9, 0, bucket_start=dt.datetime(2026, 9, 9, 0, 7)),
            bucket(9, 0, bucket_start=dt.datetime(2026, 9, 9, 0, 22))]
        out = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        day = out['days'][0]
        src = day['sources'][0]
        assert (src['ok_slots'], src['invalid_slots'], src['absent_slots']) == (96, 0, 0)
        assert _partition(src) == 96 and src['expected_slots'] == 96
        assert src['excluded_rows'] == 2 and day['excluded_rows'] == 2
        assert src['mentions'] == 96
        # Excluded evidence is uncertainty: never a full-day claim.
        assert src['coverage'] == 'partial' and day['coverage'] == 'partial'
        assert any('off the 15-minute grid' in w for w in out['warnings'])

    def test_the_slot_fields_always_partition_the_day(self):
        rows = ([bucket(9, s, count=1) for s in range(10)]
                + [bucket(9, s, count=1, status='truncated') for s in range(10, 20)]
                + [bucket(9, s, count=1, status='missing') for s in range(20, 30)]
                + [bucket(9, s, count=-2) for s in range(30, 35)]
                + [bucket(9, 40, count=1), bucket(9, 40, count=1)]
                + [bucket(9, 0, bucket_start=dt.datetime(2026, 9, 9, 5, 1))])
        src = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)['days'][0]['sources'][0]
        assert _partition(src) == 96
        assert src['excluded_rows'] == 2

    def test_two_configs_in_one_day_is_a_transition_and_never_a_full_claim(self):
        rows = ([bucket(9, s, config='cfgA') for s in range(48)]
                + [bucket(9, s, config='cfgB') for s in range(48, 96)])
        out = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        src = out['days'][0]['sources'][0]
        assert src['mentions'] == 96 and src['config_versions'] == ['cfgA', 'cfgB']
        assert src['transition'] is True and src['coverage'] == 'partial'
        assert out['days'][0]['config_transition'] is True
        assert out['days'][0]['coverage'] == 'partial'

    def test_config_change_across_the_day_boundary_is_flagged_on_the_later_day(self):
        rows = full_day(8, config='cfgA') + full_day(9, config='cfgB')
        out = ac.chatter_days(rows, d(8), d(9), FIRST_SEEN)
        assert out['days'][0]['config_transition'] is False
        assert out['days'][1]['config_transition'] is True
        assert out['days'][0]['coverage'] == 'observed' and out['days'][1]['coverage'] == 'observed'
        assert any('config' in w for w in out['warnings'])

    def test_a_null_stamp_keeps_counts_but_prevents_a_full_day(self):
        out = ac.chatter_days(full_day(9, count=2, config=None), d(9), d(9), FIRST_SEEN)
        src = out['days'][0]['sources'][0]
        assert src['mentions'] == 192 and src['config_versions'] == [None]
        assert src['coverage'] == 'partial' and src['ok_slots'] == 96

    def test_bare_reddit_and_child_in_one_slot_makes_the_pooled_day_ambiguous(self):
        rows = (full_day(9, source='reddit', count=1)
                + full_day(9, source='reddit:wallstreetbets', count=2)
                + full_day(9, source='bluesky', count=3))
        out = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        day = out['days'][0]
        assert day['mentions'] is None and day['overlap_ambiguous'] is True
        assert day['coverage'] == 'partial'
        by = {s['source']: s['mentions'] for s in day['sources']}
        assert by == {'bluesky': 288, 'reddit': 96, 'reddit:wallstreetbets': 192}

    def test_root_only_older_reddit_and_retired_sources_are_included(self):
        rows = full_day(8, source='reddit', count=1) + full_day(9, source='stocktwits', count=1)
        out = ac.chatter_days(rows, d(8), d(9), FIRST_SEEN)
        assert out['days'][0]['mentions'] == 96 and out['days'][0]['overlap_ambiguous'] is False
        assert {s['source'] for s in out['days'][1]['sources']} == {'reddit', 'stocktwits'}
        assert out['days'][1]['mentions'] == 96

    def test_buckets_before_first_seen_are_excluded_individually(self):
        first_seen = dt.datetime(2026, 9, 9, 12, 0)
        out = ac.chatter_days(full_day(9, count=1), d(9), d(9), first_seen)
        src = out['days'][0]['sources'][0]
        assert src['mentions'] == 48 and src['ok_slots'] == 48 and src['absent_slots'] == 48
        assert out['days'][0]['identity_excluded_slots'] == 48
        assert out['days'][0]['coverage'] == 'partial'
        assert any('identity' in w for w in out['warnings'])

    def test_identity_exclusions_count_source_bucket_rows_not_time_slots(self):
        # REVIEW-1 repro #1: 48 quarter-hours before first_seen on 3 sources.
        rows = [bucket(9, s, source=src) for src in ('bluesky', 'fourchan', 'reddit:wsb')
                for s in range(96)]
        out = ac.chatter_days(rows, d(9), d(9), dt.datetime(2026, 9, 9, 12))
        assert out['days'][0]['identity_excluded_slots'] == 144
        assert any('144 retained source-bucket row(s) precede' in w for w in out['warnings'])

    def test_a_source_seen_only_before_first_seen_is_not_represented_but_is_disclosed(self):
        # REVIEW-1 repro #4: stocktwits has rows only before first_seen.
        rows = ([bucket(9, s, source='stocktwits') for s in range(10)]
                + [bucket(9, s) for s in range(60, 96)])
        out = ac.chatter_days(rows, d(9), d(9), dt.datetime(2026, 9, 9, 6))
        day = out['days'][0]
        assert [s['source'] for s in day['sources']] == ['bluesky']
        assert day['identity_excluded_slots'] == 10
        assert any('only before the company record' in w and 'stocktwits' in w
                   for w in out['warnings'])
        # Nothing claims the historical source set is known.
        assert day['configured_source_coverage'] == 'unknown'

    def test_the_source_limit_still_counts_what_was_fetched_before_exclusion(self):
        rows = [bucket(9, 0, source=f's{i}') for i in range(65)]
        with pytest.raises(ac.ContractError):
            ac.chatter_days(rows, d(9), d(9), dt.datetime(2026, 9, 10))

    def test_half_open_utc_bounds_and_ninety_six_slots_on_dst_days(self):
        # 2026-03-08 is a US DST change day; UTC days always have 96 slots.
        rows = [dict(bucket(9, 0), bucket_start=dt.datetime(2026, 3, 8) + dt.timedelta(minutes=15 * s))
                for s in range(96)]
        rows.append(dict(bucket(9, 0), bucket_start=dt.datetime(2026, 3, 9, 0, 0), mention_count=50))
        out = ac.chatter_days(rows, dt.date(2026, 3, 8), dt.date(2026, 3, 8), FIRST_SEEN)
        assert len(out['days']) == 1
        assert out['days'][0]['sources'][0]['ok_slots'] == 96
        assert out['days'][0]['mentions'] == 96  # the row AT the end bound is excluded

    def test_too_many_sources_or_rows_is_a_limit_not_a_truncated_success(self):
        rows = [bucket(9, 0, source=f's{i}') for i in range(65)]
        with pytest.raises(ac.ContractError) as info:
            ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        assert info.value.code == 'analysis_limit' and info.value.status == 503
        big = [bucket(9, 0, source=f's{i % 64}') for i in range(ac.BUCKET_ROW_LIMIT + 1)]
        with pytest.raises(ac.ContractError) as info2:
            ac.chatter_days(big, d(9), d(9), FIRST_SEEN)
        assert info2.value.code == 'analysis_limit'

    def test_a_duplicate_key_row_counts_once_and_is_flagged(self):
        rows = [bucket(9, 0, count=5), bucket(9, 0, count=5)]
        out = ac.chatter_days(rows, d(9), d(9), FIRST_SEEN)
        src = out['days'][0]['sources'][0]
        assert src['mentions'] == 5 and src['ok_slots'] == 1
        assert src['invalid_slots'] == 0 and src['excluded_rows'] == 1
        assert _partition(src) == 96
        full = ac.chatter_days(full_day(9) + [bucket(9, 3, count=0)], d(9), d(9), FIRST_SEEN)
        assert full['days'][0]['sources'][0]['coverage'] == 'partial'


def _partition(src):
    return sum(src[k] for k in ('ok_slots', 'truncated_slots', 'missing_slots',
                                'invalid_slots', 'absent_slots'))


# --- modeled US calendars ------------------------------------------------------

class TestKnownUsMics:
    """The calendar's MIC set must be the confirmed listing vocabulary.

    All eight codes in the Nasdaq directory contract resolve to an ACTIVE US
    listing MIC (ISO 10383, September 2026 publication). `IEXG` was missing
    here, so the first `V` listing Radar ever mapped would silently have lost
    its trading-day hints -- fail-soft, but wrong, and there is no reason for
    IEX to model differently from the other seven.
    """

    def test_all_eight_confirmed_listing_mics_are_known(self):
        from features.radar.universe_directory import KNOWN_LISTING_MICS

        assert ac.KNOWN_US_MICS == frozenset(
            {'XNGS', 'XNMS', 'XNCM', 'XNYS', 'XASE', 'ARCX', 'BATS', 'IEXG'})
        assert KNOWN_LISTING_MICS <= ac.KNOWN_US_MICS

    def test_iexg_gets_the_modeled_us_calendar(self):
        saturday, monday = dt.date(2026, 9, 12), dt.date(2026, 9, 14)
        hints = ac.calendar_for('IEXG')
        assert hints(saturday) == 'modeled_closed'
        assert hints(monday) == 'modeled_open'
        assert [hints(day) for day in (saturday, monday)] == [
            ac.calendar_for('XNGS')(saturday), ac.calendar_for('XNGS')(monday)]

    @pytest.mark.parametrize('mic', ['XXXX', 'XNAS', 'XETR', '', None])
    def test_everything_outside_the_confirmed_set_stays_unknown(self, mic):
        """`XNAS` is Nasdaq's operating MIC and this codebase's former
        fallback sentinel; no listing resolves to it, so it is not modeled."""
        assert ac.calendar_for(mic)(dt.date(2026, 9, 14)) == 'unknown'


# --- payload assembly ---------------------------------------------------------

class TestPayloadShape:
    def test_price_and_chatter_serialize_to_json_finite_values(self):
        price = ac.price_days([close_row(9)], INSTRUMENT, FIRST_SEEN, d(8), d(9), us_calendar)
        chatter = ac.chatter_days(full_day(9, count=1), d(8), d(9), FIRST_SEEN)
        text = json.dumps({'price': price, 'chatter': chatter}, allow_nan=False)
        assert 'NaN' not in text
