"""P01/P03: Yahoo bar normalization from the SAVED research arrays.

fixtures/yahoo_saved_arrays.json holds timestamp/close arrays copied verbatim
from radar-design/artifacts/md-selected-price/probe_raw_points.json (captured
2026-09-15 13:50-13:52 UTC by the Researcher). No meta was saved, so every
test supplies synthetic meta. None of this is live evidence."""
import datetime as dt
import json
from pathlib import Path

import pytest

from features.radar import price_chart_contract as c

from .helpers import identity, utc

FIX = json.loads((Path(__file__).parent / 'fixtures' / 'yahoo_saved_arrays.json').read_text(encoding='utf-8'))


def payload(key=None, symbol='AAPL', exchange='NMS', currency='USD', *, timestamps=None, closes=None):
    saved = FIX['series'][key] if key else {'timestamp': [], 'close': []}
    return {'chart': {'result': [{
        'meta': {'symbol': symbol, 'currency': currency, 'exchangeName': exchange},
        'timestamp': list(saved['timestamp'] if timestamps is None else timestamps),
        'indicators': {'quote': [{'close': list(saved['close'] if closes is None else closes)}]},
    }], 'error': None}}


def normalized(key, now, span, ident=None, **meta):
    ident = ident or identity()
    window = c.window_for(span, now)
    spec = c.request_spec(ident, window)
    return window, spec, c.normalize_yahoo(payload(key, **meta), spec, received_at=now.timestamp())


def test_saved_5d_5m_array_is_five_sessions_with_its_null_gap_and_off_grid_point_omitted():
    now = utc(2026, 9, 15, 13, 50, 19)
    window, _, result = normalized('yahoo_5d_5m_AAPL', now, '1W')
    assert result['kind'] == 'ok'
    assert (result['off_grid'], result['nulls'], len(result['bars'])) == (1, 1, 317)
    points = c.yahoo_points(result['bars'], window, now)
    days = {}
    for point in points:
        days[point['start'][:10]] = days.get(point['start'][:10], 0) + 1
    assert days == {'2026-09-09': 78, '2026-09-10': 78, '2026-09-11': 78, '2026-09-14': 78, '2026-09-15': 5}
    assert [i for i, p in enumerate(points) if p['break_before']] == [78, 156, 234, 312, 316]
    gap = points[316]
    assert gap['value'] is None and gap['start'] == '2026-09-15T13:50:00Z'
    assert gap['provisional'] is True and gap['at'] == '2026-09-15T13:50:19Z'
    price = c.provider_price(result, window, identity(), now=now)
    assert price['adjustment_basis'] == 'unknown' and price['kind'] == 'bar_close'
    assert price['price_basis'] == 'provider_bar_close' and price['interval_seconds'] == 300
    assert price['latest_observation_at'] == '2026-09-15T13:50:00Z'
    assert price['stale'] is False and price['fallback'] is False
    assert any('off the bar grid' in w for w in c.provider_warnings(result))


def test_a_bar_close_is_plotted_at_the_bar_end_never_at_its_start():
    now = utc(2026, 9, 15, 13, 50, 19)
    window, _, result = normalized('yahoo_5d_5m_AAPL', now, '1W')
    first = c.yahoo_points(result['bars'], window, now)[0]
    assert (first['start'], first['end'], first['at']) == (
        '2026-09-09T13:30:00Z', '2026-09-09T13:35:00Z', '2026-09-09T13:35:00Z')
    assert first['provisional'] is False


def test_saved_1d_1m_array_breaks_at_missing_minutes_nulls_and_the_regular_open():
    now = utc(2026, 9, 15, 13, 50, 21)
    window, _, result = normalized('yahoo_1d_1m_AAPL', now, '1D')
    assert (result['kind'], result['off_grid'], result['nulls'], len(result['bars'])) == ('ok', 1, 1, 351)
    points = c.yahoo_points(result['bars'], window, now)
    regular_open = utc(2026, 9, 15, 13, 30)
    for previous, point in zip(points, points[1:]):
        start = dt.datetime.fromisoformat(point['start'].replace('Z', '+00:00'))
        before = dt.datetime.fromisoformat(previous['start'].replace('Z', '+00:00'))
        expected = (point['value'] is None or previous['value'] is None
                    or start - before != dt.timedelta(minutes=1)
                    or (before < regular_open <= start))
        assert point['break_before'] is expected, point['start']
    assert next(p for p in points if p['start'] == '2026-09-15T13:30:00Z')['break_before'] is True


def test_sparse_ge_array_never_joins_across_a_missing_minute():
    now = utc(2026, 9, 15, 13, 50, 37)
    ident = identity(ticker='GE', provider_symbol='GE', mic='XNYS')
    window, _, result = normalized('yahoo_1d_1m_GE', now, '1D', ident, symbol='GE', exchange='NYQ')
    assert (result['kind'], len(result['bars']), result['nulls']) == ('ok', 47, 1)
    points = c.yahoo_points(result['bars'], window, now)
    joined = [(a, b) for a, b in zip(points, points[1:]) if not b['break_before']]
    assert joined, 'some adjacent minutes do exist in the sample'
    for a, b in joined:
        assert (dt.datetime.fromisoformat(b['start'][:-1]) - dt.datetime.fromisoformat(a['start'][:-1])
                == dt.timedelta(minutes=1))


def test_class_share_symbol_and_a_provisional_last_bar_from_receipt_time():
    now = utc(2026, 9, 15, 13, 51, 45)
    ident = identity(ticker='BRK.B', provider_symbol='BRK.B', mic='XNYS')
    window, spec, result = normalized('yahoo_5d_5m_BRK.B', now, '1W', ident, symbol='BRK-B', exchange='NYQ')
    assert spec['symbol'] == 'BRK-B'
    assert (result['kind'], result['nulls'], result['off_grid']) == ('ok', 0, 1)
    last = c.yahoo_points(result['bars'], window, now)[-1]
    assert (last['start'], last['provisional'], last['at']) == (
        '2026-09-15T13:50:00Z', True, '2026-09-15T13:51:45Z')


def test_a_cached_bar_stays_provisional_after_its_end_has_passed():
    received = utc(2026, 9, 15, 13, 51, 45)
    ident = identity(ticker='BRK.B', provider_symbol='BRK.B', mic='XNYS')
    _, _, result = normalized('yahoo_5d_5m_BRK.B', received, '1W', ident, symbol='BRK-B', exchange='NYQ')
    later = c.window_for('1W', utc(2026, 9, 15, 13, 58))
    last = c.yahoo_points(result['bars'], later, received)[-1]
    assert (last['provisional'], last['at']) == (True, '2026-09-15T13:51:45Z')


def test_one_valid_bar_is_a_point_not_an_unavailable_line():
    now = utc(2026, 9, 15, 9)
    window = c.window_for('1D', now)
    spec = c.request_spec(identity(), window)
    stamp = int(utc(2026, 9, 15, 8, 30).timestamp())
    result = c.normalize_yahoo(payload(timestamps=[stamp], closes=[100.25]), spec, received_at=now.timestamp())
    price = c.provider_price(result, window, identity(), now=now)
    assert len(price['points']) == 1 and price['points'][0]['value'] == 100.25


def test_a_missing_provider_session_does_not_shorten_the_window():
    now = utc(2026, 9, 15, 13, 50, 19)
    saved = FIX['series']['yahoo_5d_5m_AAPL']
    keep = [(t, v) for t, v in zip(saved['timestamp'], saved['close'])
            if dt.datetime.fromtimestamp(t, dt.timezone.utc).date() != dt.date(2026, 9, 11)]
    window = c.window_for('1W', now)
    spec = c.request_spec(identity(), window)
    result = c.normalize_yahoo(payload(timestamps=[t for t, _ in keep], closes=[v for _, v in keep]),
                               spec, received_at=now.timestamp())
    assert len(window.session_dates) == 5 and len(result['bars']) == 239
    points = c.yahoo_points(result['bars'], window, now)
    assert not any(p['start'].startswith('2026-09-11') for p in points)
    assert next(p for p in points if p['start'] == '2026-09-14T13:30:00Z')['break_before'] is True


@pytest.mark.parametrize('meta', [{'symbol': 'AAPL.X'}, {'currency': 'EUR'}, {'exchange': 'NYQ'}])
def test_identity_mismatch_is_refused(meta):
    now = utc(2026, 9, 15, 13, 50, 19)
    *_, result = normalized('yahoo_5d_5m_AAPL', now, '1W', **meta)
    assert result['kind'] == 'identity_mismatch'


def test_an_unknown_mic_is_refused():
    now = utc(2026, 9, 15, 13, 50, 19)
    *_, result = normalized('yahoo_5d_5m_AAPL', now, '1W', identity(mic='ZZZZ'))
    assert result['kind'] == 'identity_mismatch'


def test_zero_and_negative_closes_are_explicit_null_points_but_nan_is_invalid():
    now = utc(2026, 9, 15, 9)
    window = c.window_for('1D', now)
    spec = c.request_spec(identity(), window)
    stamps = [int(utc(2026, 9, 15, 8, m).timestamp()) for m in (0, 1, 2)]
    ok = c.normalize_yahoo(payload(timestamps=stamps, closes=[1.0, 0, -2.5]), spec, received_at=now.timestamp())
    assert [v for _, v in ok['bars']] == [1.0, None, None] and ok['nulls'] == 2
    for bad in (float('nan'), float('inf'), 'abc', True):
        result = c.normalize_yahoo(payload(timestamps=stamps, closes=[1.0, bad, 2.0]), spec,
                                   received_at=now.timestamp())
        assert result['kind'] == 'invalid', bad


def test_timestamps_must_increase_and_arrays_must_be_parallel():
    now = utc(2026, 9, 15, 9)
    window = c.window_for('1D', now)
    spec = c.request_spec(identity(), window)
    t = int(utc(2026, 9, 15, 8).timestamp())
    assert c.normalize_yahoo(payload(timestamps=[t, t], closes=[1.0, 2.0]), spec, received_at=0)['kind'] == 'invalid'
    assert c.normalize_yahoo(payload(timestamps=[t + 60, t], closes=[1.0, 2.0]), spec, received_at=0)['kind'] == 'invalid'
    assert c.normalize_yahoo(payload(timestamps=[t, t + 60], closes=[1.0]), spec, received_at=0)['kind'] == 'invalid'


def test_overflowing_responses_are_rejected_not_truncated():
    now = utc(2026, 9, 15, 9)
    spec = c.request_spec(identity(), c.window_for('1D', now))
    t = int(utc(2026, 9, 15, 8).timestamp())
    raw = c.normalize_yahoo(payload(timestamps=[t + i * 60 for i in range(c.MAX_RAW_BARS + 1)],
                                    closes=[1.0] * (c.MAX_RAW_BARS + 1)), spec, received_at=0)
    assert raw == {'kind': 'invalid', 'reason': 'too many bars'}
    wide = dict(spec, intervals=[[t, t + 10 ** 7]])
    points = c.normalize_yahoo(payload(timestamps=[t + i * 60 for i in range(c.MAX_PRICE_POINTS + 1)],
                                       closes=[1.0] * (c.MAX_PRICE_POINTS + 1)), wide, received_at=0)
    assert points == {'kind': 'invalid', 'reason': 'too many points'}


def test_empty_and_malformed_envelopes():
    now = utc(2026, 9, 15, 9)
    spec = c.request_spec(identity(), c.window_for('1D', now))
    t = int(utc(2026, 9, 15, 8).timestamp())
    assert c.normalize_yahoo(payload(timestamps=[t], closes=[None]), spec, received_at=0)['kind'] == 'empty'
    assert c.normalize_yahoo({'chart': {'result': []}}, spec, received_at=0)['kind'] == 'invalid'
    assert c.normalize_yahoo(None, spec, received_at=0)['kind'] == 'invalid'
    no_bars = {'chart': {'result': [{'meta': {'symbol': 'AAPL', 'currency': 'USD', 'exchangeName': 'NMS'},
                                     'indicators': {'quote': [{}]}}]}}
    assert c.normalize_yahoo(no_bars, spec, received_at=0)['kind'] == 'empty'
    assert c.normalize_yahoo(payload(timestamps=[t], closes=[1.0]), {'version': 1}, received_at=0) == {
        'kind': 'invalid', 'reason': 'request_spec'}


# --- Alpaca consolidated SIP bars (C1) --------------------------------------------
#
# Fixtures are hand-written in the exact shape the 2026-09-16 bounded validation
# recorded (radar-design/artifacts/md-selected-price-alpaca-validate-1/README.md):
# `{"bars": {"<SYMBOL>": [{c,h,l,n,o,t,v,vw}, ...]}, "next_page_token": null}`,
# with `t` the bar START in RFC-3339 UTC. No provider was contacted for any of
# them, and no credential is involved in normalization at all.

ALPACA_NOW = utc(2026, 9, 16, 0, 34)          # the validation's clock: market closed


def alpaca_bar(stamp, close, **over):
    row = {'t': stamp, 'o': close, 'h': close, 'l': close, 'c': close, 'v': 10, 'n': 2, 'vw': close}
    row.update(over)
    return row


def alpaca_payload(rows, symbol='AAPL', token=None):
    return {'bars': {symbol: list(rows)}, 'next_page_token': token}


def alpaca_spec(span, ident=None, now=ALPACA_NOW):
    window = c.window_for(span, now)
    spec, refusal = c.alpaca_request_spec(ident or identity(), window, now=now)
    assert refusal is None
    return window, spec


def test_a_1w_regular_session_excludes_the_exact_close_timestamp():
    window, spec = alpaca_spec('1W')
    result = c.normalize_alpaca(alpaca_payload([
        alpaca_bar('2026-09-15T19:55:00Z', 10.5), alpaca_bar('2026-09-15T20:00:00Z', 10.6)]),
        spec, received_at=ALPACA_NOW.timestamp())
    assert result['kind'] == 'ok' and result['outside'] == 1
    points = c.provider_points(result['bars'], window, ALPACA_NOW, regime=c.ALPACA_REGIME)
    assert [p['start'] for p in points] == ['2026-09-15T19:55:00Z']
    assert points[0]['segment'] == 'regular:2026-09-15|' + c.ALPACA_REGIME


def test_a_1d_extended_window_keeps_the_close_bar_as_a_separate_after_hours_segment():
    window, spec = alpaca_spec('1D')
    result = c.normalize_alpaca(alpaca_payload([
        alpaca_bar('2026-09-15T19:58:00Z', 10.4), alpaca_bar('2026-09-15T19:59:00Z', 10.5),
        alpaca_bar('2026-09-15T20:00:00Z', 10.6)]), spec, received_at=ALPACA_NOW.timestamp())
    assert (result['kind'], result['outside'], result['nulls']) == ('ok', 0, 0)
    points = c.provider_points(result['bars'], window, ALPACA_NOW, regime=c.ALPACA_REGIME)
    assert [p['segment'].split('|')[0] for p in points] == [
        'regular:2026-09-15', 'regular:2026-09-15', 'afterhours:2026-09-15']
    assert points[-1]['break_before'] is True


def test_missing_minutes_are_absent_and_do_not_end_the_hard_segment():
    window, spec = alpaca_spec('1D')
    result = c.normalize_alpaca(alpaca_payload([
        alpaca_bar('2026-09-15T13:30:00Z', 7.4), alpaca_bar('2026-09-15T14:20:00Z', 7.41),
        alpaca_bar('2026-09-15T14:21:00Z', 7.39)]), spec, received_at=ALPACA_NOW.timestamp())
    points = c.provider_points(result['bars'], window, ALPACA_NOW, regime=c.ALPACA_REGIME)
    assert len(points) == 3 and all(p['value'] is not None for p in points)
    assert len({p['segment'] for p in points}) == 1
    # break_before still records the grid gap; it no longer splits the drawing.
    assert [p['break_before'] for p in points] == [False, True, False]
    assert result['nulls'] == 0


def test_fractional_rfc3339_seconds_parse_and_stay_off_the_minute_grid():
    window, spec = alpaca_spec('1D')
    result = c.normalize_alpaca(alpaca_payload([
        alpaca_bar('2026-09-15T13:30:00.000000000Z', 7.4),
        alpaca_bar('2026-09-15T13:30:30.500Z', 7.5),
        alpaca_bar('2026-09-15T13:31:00Z', 7.6)]), spec, received_at=ALPACA_NOW.timestamp())
    assert (result['kind'], result['off_grid']) == ('ok', 1)
    points = c.provider_points(result['bars'], window, ALPACA_NOW, regime=c.ALPACA_REGIME)
    assert [p['start'] for p in points] == ['2026-09-15T13:30:00Z', '2026-09-15T13:31:00Z']


@pytest.mark.parametrize('rows,reason', [
    ([alpaca_bar('2026-09-15T13:31:00Z', 1.0), alpaca_bar('2026-09-15T13:30:00Z', 1.0)],
     'timestamps not increasing'),
    ([alpaca_bar('2026-09-15T13:30:00Z', 1.0), alpaca_bar('2026-09-15T13:30:00Z', 1.0)],
     'timestamps not increasing'),
    ([alpaca_bar('2026-09-15T13:30:00Z', 0)], 'close is not a finite positive number'),
    ([alpaca_bar('2026-09-15T13:30:00Z', -1.5)], 'close is not a finite positive number'),
    ([alpaca_bar('2026-09-15T13:30:00Z', None)], 'close is not a finite positive number'),
    ([alpaca_bar('2026-09-15T13:30:00Z', float('nan'))], 'close is not a finite positive number'),
    ([alpaca_bar('2026-09-15T13:30:00Z', True)], 'close is not a finite positive number'),
    ([alpaca_bar('not a timestamp', 1.0)], 'timestamp'),
    ([{'c': 1.0}], 'timestamp'),
])
def test_an_invalid_alpaca_bar_invalidates_the_whole_answer(rows, reason):
    _, spec = alpaca_spec('1D')
    result = c.normalize_alpaca(alpaca_payload(rows), spec, received_at=0)
    assert result == {'kind': 'invalid', 'reason': reason}


def test_the_symbol_key_must_match_exactly_and_a_page_token_is_truncation():
    _, spec = alpaca_spec('1D')
    rows = [alpaca_bar('2026-09-15T13:30:00Z', 7.4)]
    assert c.normalize_alpaca(alpaca_payload(rows, 'AAPL.X'), spec, received_at=0)['kind'] == 'identity_mismatch'
    assert c.normalize_alpaca({'bars': {'AAPL': rows, 'MSFT': rows}, 'next_page_token': None},
                              spec, received_at=0)['kind'] == 'identity_mismatch'
    assert c.normalize_alpaca(alpaca_payload(rows, token='abc'), spec, received_at=0) == {
        'kind': 'truncated', 'reason': 'the provider answer was paginated'}
    assert c.normalize_alpaca({'bars': {}, 'next_page_token': None}, spec, received_at=0)['kind'] == 'empty'
    assert c.normalize_alpaca(alpaca_payload([]), spec, received_at=0)['kind'] == 'empty'


def test_a_malformed_alpaca_envelope_is_invalid_never_a_zero_series():
    _, spec = alpaca_spec('1D')
    for body in (None, [], {'bars': []}, {'bars': {'AAPL': {}}, 'next_page_token': None},
                 {'next_page_token': None}):
        assert c.normalize_alpaca(body, spec, received_at=0)['kind'] == 'invalid'
    assert c.normalize_alpaca(alpaca_payload([alpaca_bar('2026-09-15T13:30:00Z', 1.0)]),
                              {'version': 1}, received_at=0) == {'kind': 'invalid', 'reason': 'request_spec'}


def test_the_alpaca_price_block_names_delayed_sip_and_raw_closes():
    window, spec = alpaca_spec('1D')
    result = c.normalize_alpaca(alpaca_payload([
        alpaca_bar('2026-09-15T13:30:00Z', 7.4), alpaca_bar('2026-09-15T13:31:00Z', 7.41)]),
        spec, received_at=ALPACA_NOW.timestamp())
    price = c.provider_price(result, window, identity(), now=ALPACA_NOW)
    assert (price['source'], price['kind']) == (c.ALPACA_SOURCE, 'bar_close')
    assert (price['price_basis'], price['adjustment_basis']) == ('provider_bar_close', 'raw')
    assert price['regimes'] == [{'id': c.ALPACA_REGIME, 'source': c.ALPACA_SOURCE,
                                 'price_basis': 'provider_bar_close', 'adjustment_basis': 'raw'}]
    assert price['fallback'] is False and price['interval_seconds'] == 60
    assert price['observations'] == 2 and price['expected_intervals'] == 960
    assert price['latest_observation_at'] == '2026-09-15T13:32:00Z'
    assert all(p['segment'] == 'regular:2026-09-15|' + c.ALPACA_REGIME for p in price['points'])


def test_too_many_alpaca_bars_are_rejected_not_truncated():
    _, spec = alpaca_spec('1D')
    rows = [alpaca_bar(c.iso_z(utc(2026, 9, 15, 8) + dt.timedelta(minutes=i)), 1.0)
            for i in range(c.MAX_RAW_BARS + 1)]
    assert c.normalize_alpaca(alpaca_payload(rows), spec, received_at=0) == {
        'kind': 'invalid', 'reason': 'too many bars'}
