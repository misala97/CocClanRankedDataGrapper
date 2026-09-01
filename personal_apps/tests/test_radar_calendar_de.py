import datetime as dt

import pytest

from features.radar.market_calendars import session_state


def aware_utc(year, month, day, hour, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize(('instant', 'expected'), [
    ((2026, 8, 28, 5, 59), 'closed'),
    ((2026, 8, 28, 6, 0), 'premarket'),
    ((2026, 8, 28, 7, 0), 'regular'),
    ((2026, 8, 28, 15, 30), 'afterhours'),
    ((2026, 8, 28, 20, 0), 'closed'),
])
def test_xetra_summer_sessions_are_berlin_local(instant, expected):
    assert session_state('de', aware_utc(*instant)) == expected


def test_xetra_winter_open_moves_one_utc_hour():
    assert session_state('de', aware_utc(2026, 1, 7, 7, 0)) == 'premarket'
    assert session_state('de', aware_utc(2026, 1, 7, 8, 0)) == 'regular'


@pytest.mark.parametrize('instant', [
    (2026, 1, 1, 12, 0),
    (2026, 4, 3, 12, 0),
    (2026, 4, 6, 12, 0),
    (2026, 5, 1, 12, 0),
    (2026, 12, 24, 12, 0),
    (2026, 12, 25, 12, 0),
    (2026, 12, 31, 12, 0),
])
def test_xetra_2026_full_closures_are_closed(instant):
    assert session_state('de', aware_utc(*instant)) == 'closed'


@pytest.mark.parametrize(('instant', 'expected'), [
    ((2026, 8, 28, 6, 54), 'premarket'),
    ((2026, 8, 28, 6, 55), 'closed'),
    ((2026, 8, 28, 7, 0), 'regular'),
    ((2026, 8, 28, 15, 30), 'afterhours'),
    ((2026, 8, 28, 20, 0), 'closed'),
])
def test_xetra_session_edges_are_berlin_local(instant, expected):
    assert session_state('de', aware_utc(*instant)) == expected


def test_xetra_december_30_has_a_normal_close():
    assert session_state('de', aware_utc(2026, 12, 30, 16, 29)) == 'regular'
    assert session_state('de', aware_utc(2026, 12, 30, 16, 30)) == 'afterhours'


# --- Tradegate (XGAT) calendar, selected by MIC (plan Task 3) ----------------

def test_tradegate_opens_at_0730_berlin():
    before = dt.datetime(2026, 8, 31, 5, 29, tzinfo=dt.timezone.utc)
    opened = dt.datetime(2026, 8, 31, 5, 30, tzinfo=dt.timezone.utc)
    assert session_state('de', before, mic='XGAT') == 'closed'
    assert session_state('de', opened, mic='XGAT') == 'premarket'


def test_xetra_default_keeps_0800_berlin_behavior():
    at_0730 = dt.datetime(2026, 8, 31, 5, 30, tzinfo=dt.timezone.utc)
    assert session_state('de', at_0730, mic='XETR') == 'closed'
    assert session_state('de', at_0730) == 'closed'


@pytest.mark.parametrize(('instant', 'expected'), [
    # Summer (UTC+2): 07:30/09:00/17:30/22:00 Berlin.
    ((2026, 8, 31, 5, 29), 'closed'),
    ((2026, 8, 31, 5, 30), 'premarket'),
    ((2026, 8, 31, 7, 0), 'regular'),
    ((2026, 8, 31, 15, 29), 'regular'),
    ((2026, 8, 31, 15, 30), 'afterhours'),
    ((2026, 8, 31, 19, 59), 'afterhours'),
    ((2026, 8, 31, 20, 0), 'closed'),
])
def test_tradegate_summer_sessions_are_berlin_local(instant, expected):
    assert session_state('de', aware_utc(*instant), mic='XGAT') == expected


def test_tradegate_winter_open_moves_one_utc_hour():
    assert session_state('de', aware_utc(2026, 1, 7, 6, 30),
                         mic='XGAT') == 'premarket'
    assert session_state('de', aware_utc(2026, 1, 7, 8, 0),
                         mic='XGAT') == 'regular'


def test_tradegate_weekend_and_holiday_are_closed():
    assert session_state('de', aware_utc(2026, 8, 30, 10, 0),
                         mic='XGAT') == 'closed'
    assert session_state('de', aware_utc(2026, 1, 1, 10, 0),
                         mic='XGAT') == 'closed'


def test_unknown_market_mic_pair_is_rejected():
    with pytest.raises(ValueError):
        session_state('de', aware_utc(2026, 8, 31, 10, 0), mic='XNAS')
