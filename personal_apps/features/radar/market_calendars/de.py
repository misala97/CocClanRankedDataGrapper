"""Xetra 2026 session calendar."""
import datetime as dt
from zoneinfo import ZoneInfo

from . import SessionBounds

BERLIN = ZoneInfo('Europe/Berlin')

EARLY_START = dt.time(8, 0)
EARLY_END = dt.time(8, 55)
REGULAR_START = dt.time(9, 0)
REGULAR_END = dt.time(17, 30)
LATE_END = dt.time(22, 0)

_FULL_CLOSURES = {
    2026: {
        dt.date(2026, 1, 1),
        dt.date(2026, 4, 3),
        dt.date(2026, 4, 6),
        dt.date(2026, 5, 1),
        dt.date(2026, 12, 24),
        dt.date(2026, 12, 25),
        dt.date(2026, 12, 31),
    },
}


def full_closures(year):
    """Xetra full-day closures, kept in an isolated annual mapping."""
    return _FULL_CLOSURES.get(year, set())


def is_trading_day(day):
    return day.weekday() < 5 and day not in full_closures(day.year)


def _aware_local_day(when_utc):
    if when_utc.tzinfo is None:
        raise ValueError('session_state requires a timezone-aware UTC datetime')
    return when_utc.astimezone(BERLIN).date()


def session_bounds(when_utc):
    """Return the Xetra calendar day's session boundaries in UTC."""
    day = _aware_local_day(when_utc)

    def at(time):
        return dt.datetime.combine(day, time, tzinfo=BERLIN).astimezone(dt.timezone.utc)

    return SessionBounds(
        opens_at=at(EARLY_START),
        premarket_closes_at=at(EARLY_END),
        regular_opens_at=at(REGULAR_START),
        regular_closes_at=at(REGULAR_END),
        closes_at=at(LATE_END),
    )


def session_state(when_utc):
    """One of 'premarket', 'regular', 'afterhours', 'closed'."""
    day = _aware_local_day(when_utc)
    if not is_trading_day(day):
        return 'closed'

    now = when_utc.astimezone(BERLIN).time()
    if EARLY_START <= now <= EARLY_END:
        return 'premarket'
    if REGULAR_START <= now < REGULAR_END:
        return 'regular'
    if REGULAR_END <= now < LATE_END:
        return 'afterhours'
    return 'closed'
