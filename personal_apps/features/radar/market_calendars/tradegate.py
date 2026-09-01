"""Tradegate BSX (XGAT) 2026 session calendar.

07:30–22:00 Berlin per the exchange's published trading hours. The movement
vocabulary maps 07:30–09:00 to premarket, the 09:00–17:30 reference window
to regular, and 17:30–22:00 to afterhours (spec §4.4). Full-day closures
reuse the Xetra set: both are German venues and no divergent Tradegate
closure has been observed; the shadow phase would surface one as a string
of empty market-open cycles.
"""
import datetime as dt

from . import SessionBounds
from .de import BERLIN, full_closures

EARLY_START = dt.time(7, 30)
EARLY_END = dt.time(9, 0)
REGULAR_START = dt.time(9, 0)
REGULAR_END = dt.time(17, 30)
LATE_END = dt.time(22, 0)


def is_trading_day(day):
    return day.weekday() < 5 and day not in full_closures(day.year)


def _aware_local_day(when_utc):
    if when_utc.tzinfo is None:
        raise ValueError('session_state requires a timezone-aware UTC datetime')
    return when_utc.astimezone(BERLIN).date()


def session_bounds(when_utc):
    """Return the Tradegate calendar day's session boundaries in UTC."""
    day = _aware_local_day(when_utc)

    def at(time):
        return dt.datetime.combine(day, time, tzinfo=BERLIN).astimezone(
            dt.timezone.utc)

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
    if EARLY_START <= now < EARLY_END:
        return 'premarket'
    if REGULAR_START <= now < REGULAR_END:
        return 'regular'
    if REGULAR_END <= now < LATE_END:
        return 'afterhours'
    return 'closed'
