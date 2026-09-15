"""P02: windows, bands and slots against independently written timestamps.

Every expected instant below was written by hand from the modeled calendar
(EDT = UTC-4 until 2026-11-01, EST = UTC-5 after; Labor Day 2026-09-07;
Thanksgiving 2026-11-26 with a 13:00 ET early close on 2026-11-27), not
computed with the code under test."""
import datetime as dt
import math

import pytest

from features.radar import price_chart_contract as c

from .helpers import identity, utc

D = dt.date


def test_1d_before_extended_open_is_the_previous_completed_session():
    w = c.window_for('1D', utc(2026, 9, 15, 7, 59))            # Tue 03:59 ET
    assert w.session_dates == (D(2026, 9, 14),)
    assert (w.start, w.end, w.partial) == (utc(2026, 9, 14, 8), utc(2026, 9, 15, 0), False)
    assert c.window_label(w) == 'last completed session'


def test_1d_at_extended_open_is_a_waiting_window_not_a_division_by_zero():
    now = utc(2026, 9, 15, 8)                                   # Tue 04:00 ET
    w = c.window_for('1D', now)
    assert w.start == w.end == now and w.waiting and w.partial
    assert c.slot_bounds(w) == [] and c.bands(w) == []
    assert c.request_spec(identity(), w) is None


def test_1d_during_the_session_runs_from_extended_open_to_now():
    w = c.window_for('1D', utc(2026, 9, 15, 13, 29))            # 09:29 ET
    assert (w.start, w.end, w.partial) == (utc(2026, 9, 15, 8), utc(2026, 9, 15, 13, 29), True)
    slots = c.slot_bounds(w)
    assert len(slots) == 22
    assert slots[0] == (utc(2026, 9, 15, 8), utc(2026, 9, 15, 8, 15))
    assert slots[-1] == (utc(2026, 9, 15, 13, 15), utc(2026, 9, 15, 13, 29))


def test_1d_at_extended_close_is_the_whole_completed_session():
    w = c.window_for('1D', utc(2026, 9, 16, 0))                 # Tue 20:00 ET
    assert w.session_dates == (D(2026, 9, 15),)
    assert (w.start, w.end, w.partial) == (utc(2026, 9, 15, 8), utc(2026, 9, 16, 0), False)


def test_1d_at_16_00_is_still_the_live_extended_session():
    w = c.window_for('1D', utc(2026, 9, 15, 20))                # 16:00 ET
    assert (w.start, w.end, w.partial) == (utc(2026, 9, 15, 8), utc(2026, 9, 15, 20), True)


def test_1w_before_regular_open_excludes_today_and_skips_labor_day():
    now = utc(2026, 9, 15, 13, 29)                              # Tue 09:29 ET
    w = c.window_for('1W', now)
    assert [d.isoformat() for d in w.session_dates] == [
        '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11', '2026-09-14']
    assert w.start == utc(2026, 9, 8, 13, 30)
    assert w.end == utc(2026, 9, 14, 20, 0)
    assert w.partial is False and c.window_label(w) == '5 sessions'


def test_1w_from_regular_open_includes_today_as_partial():
    now = utc(2026, 9, 15, 13, 30)                              # Tue 09:30 ET
    w = c.window_for('1W', now)
    assert w.session_dates[0] == D(2026, 9, 9) and w.session_dates[-1] == D(2026, 9, 15)
    assert (w.start, w.end, w.partial) == (utc(2026, 9, 9, 13, 30), now, True)
    assert c.window_label(w) == '5 sessions · today partial'


def test_1w_at_regular_close_is_complete():
    w = c.window_for('1W', utc(2026, 9, 15, 20))                # 16:00 ET
    assert (w.end, w.partial) == (utc(2026, 9, 15, 20), False)


def test_weekend():
    now = utc(2026, 9, 13, 12)                                  # Sunday
    day = c.window_for('1D', now)
    assert (day.start, day.end) == (utc(2026, 9, 11, 8), utc(2026, 9, 12, 0))
    week = c.window_for('1W', now)
    assert [d.day for d in week.session_dates] == [4, 8, 9, 10, 11]
    assert (week.start, week.end) == (utc(2026, 9, 4, 13, 30), utc(2026, 9, 11, 20))


def test_labor_day_is_not_a_session():
    now = utc(2026, 9, 7, 15)                                   # Labor Day 11:00 ET
    day = c.window_for('1D', now)
    assert day.session_dates == (D(2026, 9, 4),)
    assert (day.start, day.end) == (utc(2026, 9, 4, 8), utc(2026, 9, 5, 0))
    week = c.window_for('1W', now)
    assert week.session_dates == (D(2026, 8, 31), D(2026, 9, 1), D(2026, 9, 2),
                                  D(2026, 9, 3), D(2026, 9, 4))
    assert (week.start, week.end) == (utc(2026, 8, 31, 13, 30), utc(2026, 9, 4, 20))


def test_early_close_uses_the_modeled_13_00_close():
    now = utc(2026, 11, 27, 19)                                 # Fri 14:00 EST
    day = c.window_for('1D', now)
    assert (day.start, day.end, day.partial) == (utc(2026, 11, 27, 9), now, True)
    assert c.bands(day) == [
        {'from': '2026-11-27T09:00:00Z', 'to': '2026-11-27T14:30:00Z', 'state': 'premarket'},
        {'from': '2026-11-27T14:30:00Z', 'to': '2026-11-27T18:00:00Z', 'state': 'regular'},
        {'from': '2026-11-27T18:00:00Z', 'to': '2026-11-27T19:00:00Z', 'state': 'afterhours'},
    ]
    week = c.window_for('1W', now)
    assert [d.isoformat() for d in week.session_dates] == [
        '2026-11-20', '2026-11-23', '2026-11-24', '2026-11-25', '2026-11-27']
    assert (week.start, week.end, week.partial) == (utc(2026, 11, 20, 14, 30), utc(2026, 11, 27, 18), False)


def test_dst_end_keeps_slots_on_the_half_hour_and_bands_on_local_time():
    now = utc(2026, 11, 2, 15)                                  # Mon 10:00 EST
    w = c.window_for('1W', now)
    assert [d.isoformat() for d in w.session_dates] == [
        '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-11-02']
    assert (w.start, w.end, w.partial) == (utc(2026, 10, 27, 13, 30), now, True)
    slots = c.slot_bounds(w)
    assert len(slots) == 146
    assert all(start.minute == 30 for start, _ in slots)
    assert slots[-1] == (utc(2026, 11, 2, 14, 30), now)
    bands = c.bands(w)
    assert bands[-2:] == [
        {'from': '2026-11-02T09:00:00Z', 'to': '2026-11-02T14:30:00Z', 'state': 'premarket'},
        {'from': '2026-11-02T14:30:00Z', 'to': '2026-11-02T15:00:00Z', 'state': 'regular'}]
    assert {'from': '2026-10-30T13:30:00Z', 'to': '2026-10-30T20:00:00Z', 'state': 'regular'} in bands


@pytest.mark.parametrize('span,now', [('1W', utc(2026, 9, 15, 14, 7)), ('1D', utc(2026, 9, 15, 13, 29)),
                                      ('1W', utc(2026, 9, 13, 12))])
def test_bands_cover_the_window_contiguously(span, now):
    w = c.window_for(span, now)
    bands = c.bands(w)
    assert bands[0]['from'] == c.iso_z(w.start) and bands[-1]['to'] == c.iso_z(w.end)
    assert all(a['to'] == b['from'] and a['state'] != b['state'] for a, b in zip(bands, bands[1:]))
    assert {b['state'] for b in bands} <= {'regular', 'premarket', 'afterhours', 'closed'}


def test_1w_hourly_slots_anchor_at_09_30_and_only_the_last_is_short():
    w = c.window_for('1W', utc(2026, 9, 15, 14, 7))             # 10:07 ET
    slots = c.slot_bounds(w)
    assert len(slots) == math.ceil((w.end - w.start).total_seconds() / 3600) == 145
    assert slots[0] == (utc(2026, 9, 9, 13, 30), utc(2026, 9, 9, 14, 30))
    assert slots[-1] == (utc(2026, 9, 15, 13, 30), utc(2026, 9, 15, 14, 7))
    assert all(end - start == dt.timedelta(hours=1) for start, end in slots[:-1])


def test_the_lookup_bound_refuses_rather_than_inventing_sessions(monkeypatch):
    monkeypatch.setattr(c.us, 'is_trading_day', lambda day: False)
    for span in c.SPANS:
        with pytest.raises(c.ChartError) as error:
            c.window_for(span, utc(2026, 9, 15, 14))
        assert error.value.code == 'window_unavailable'


def test_only_1d_and_1w():
    with pytest.raises(c.ChartError) as error:
        c.window_for('1M', utc(2026, 9, 15, 14))
    assert (error.value.code, error.value.status) == ('invalid_span', 400)


def test_the_request_is_built_from_the_window_epochs_not_a_range():
    week = c.window_for('1W', utc(2026, 9, 15, 13, 29))
    spec = c.request_spec(identity(), week)
    assert 'range' not in spec
    assert spec['period1'] == int(utc(2026, 9, 8, 13, 30).timestamp())
    assert spec['period2'] == int(utc(2026, 9, 14, 20).timestamp())
    assert (spec['interval'], spec['interval_seconds'], spec['include_prepost']) == ('5m', 300, False)
    assert spec['intervals'][0] == [int(utc(2026, 9, 8, 13, 30).timestamp()),
                                    int(utc(2026, 9, 8, 20).timestamp())]
    assert len(spec['intervals']) == 5
    now = utc(2026, 9, 15, 13, 29, 30, 500000)
    day = c.window_for('1D', now)
    spec = c.request_spec(identity(), day)
    assert spec['period2'] == math.ceil(now.timestamp())
    assert (spec['interval'], spec['include_prepost']) == ('1m', True)
    assert spec['intervals'] == [[int(utc(2026, 9, 15, 8).timestamp()), int(now.timestamp())]]


def test_the_cache_key_does_not_move_with_now_but_does_with_the_sessions():
    a = c.cache_key(identity(), c.window_for('1W', utc(2026, 9, 15, 13, 31)))
    b = c.cache_key(identity(), c.window_for('1W', utc(2026, 9, 15, 19, 45)))
    assert a == b
    assert a != c.cache_key(identity(), c.window_for('1W', utc(2026, 9, 16, 13, 31)))
    assert a != c.cache_key(identity(provider_symbol='AAPX'), c.window_for('1W', utc(2026, 9, 15, 13, 31)))


def test_yahoo_symbol_forms():
    assert c.yahoo_symbol('AAPL') == 'AAPL'
    assert c.yahoo_symbol('BRK.B') == 'BRK-B'
    for refused in ('BRK/B', 'BRK-B', 'brk.b', 'A.B.C', '', None, 'TOOLONGSYMBOL1', 'AB CD'):
        assert c.yahoo_symbol(refused) is None


def test_fingerprint_changes_with_every_identity_field():
    base = identity()['fingerprint']
    for change in ({'company_id': 12}, {'instrument_id': 8}, {'provider_symbol': 'AAPX'},
                   {'currency': 'EUR'}, {'mic': 'XNYS'}, {'mapped_at_dt': dt.datetime(2026, 8, 2)}):
        assert identity(**change)['fingerprint'] != base
