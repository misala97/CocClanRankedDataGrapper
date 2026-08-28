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
