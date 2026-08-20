# personal_apps/tests/test_radar_calendar.py
"""Session state drives ingest cadence now and forward-return offsets in Plan 3.

The DST cases are the point of this suite: the EU and US switch on different
dates, so for about three weeks each spring the US open lands an hour earlier
in Berlin than usual. Anything that reasoned in German local time would
mis-tier ingest for exactly those weeks (spec 4.4).
"""
import datetime as dt
from zoneinfo import ZoneInfo

from features.radar import market_calendar as cal

BERLIN = ZoneInfo('Europe/Berlin')


def _utc(year, month, day, hour, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


def test_regular_session_on_an_ordinary_wednesday():
    # 2026-04-15 is a Wednesday. 14:00 UTC = 10:00 ET, mid-session.
    assert cal.session_state(_utc(2026, 4, 15, 14)) == 'regular'


def test_premarket_before_the_open():
    # 12:00 UTC = 08:00 ET.
    assert cal.session_state(_utc(2026, 4, 15, 12)) == 'premarket'


def test_afterhours_after_the_close():
    # 21:00 UTC = 17:00 ET.
    assert cal.session_state(_utc(2026, 4, 15, 21)) == 'afterhours'


def test_closed_overnight():
    # 03:00 UTC = 23:00 ET the previous day, past the 20:00 after-hours end.
    assert cal.session_state(_utc(2026, 4, 15, 3)) == 'closed'


def test_closed_on_a_weekend():
    # 2026-04-18 is a Saturday.
    assert cal.session_state(_utc(2026, 4, 18, 14)) == 'closed'


def test_closed_on_a_fixed_holiday():
    # Independence Day 2026 falls on a Saturday, so it is observed Friday 3rd.
    assert cal.session_state(_utc(2026, 7, 3, 14)) == 'closed'


def test_closed_on_good_friday():
    # Easter 2026 is April 5, so Good Friday is April 3.
    assert dt.date(2026, 4, 3) in cal.holidays(2026)
    assert cal.session_state(_utc(2026, 4, 3, 14)) == 'closed'


def test_thanksgiving_is_the_fourth_thursday():
    assert dt.date(2026, 11, 26) in cal.holidays(2026)


def test_day_after_thanksgiving_is_an_early_close():
    assert dt.date(2026, 11, 27) in cal.early_close_days(2026)
    # 18:30 UTC = 13:30 ET, past the 13:00 early close.
    assert cal.session_state(_utc(2026, 11, 27, 18, 30)) == 'afterhours'
    # 17:00 UTC = 12:00 ET, still open.
    assert cal.session_state(_utc(2026, 11, 27, 17)) == 'regular'


def test_dst_desync_window_us_already_switched_eu_has_not():
    """2026: US DST starts Mar 8, EU starts Mar 29. Between those dates the
    US open is 13:30 UTC and lands at 14:30 in Berlin rather than 15:30."""
    instant = _utc(2026, 3, 16, 13, 45)          # Monday, 09:45 ET
    assert cal.session_state(instant) == 'regular'
    assert instant.astimezone(BERLIN).hour == 14


def test_outside_the_desync_window_the_open_is_1530_berlin():
    instant = _utc(2026, 4, 15, 13, 45)          # 09:45 ET
    assert cal.session_state(instant) == 'regular'
    assert instant.astimezone(BERLIN).hour == 15


def test_naive_datetimes_are_rejected():
    """A naive datetime here would be silently interpreted as local time on
    whatever machine runs the daemon."""
    import pytest
    with pytest.raises(ValueError):
        cal.session_state(dt.datetime(2026, 4, 15, 14))
