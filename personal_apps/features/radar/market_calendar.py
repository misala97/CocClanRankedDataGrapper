# personal_apps/features/radar/market_calendar.py
"""NYSE session state, computed locally.

Local rather than from a data provider for two reasons: spec 10 forbids live
API calls in tests, and Plan 3's forward returns need historical session
boundaries, which a "is the market open right now" endpoint cannot give.

Everything crossing this module's boundary is timezone-aware UTC. Conversion to
America/New_York happens inside, and nothing here ever reasons in Berlin time --
that conversion belongs to the display layer (spec 4.4).
"""
import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')

PREMARKET_START = dt.time(4, 0)
REGULAR_START = dt.time(9, 30)
REGULAR_END = dt.time(16, 0)
EARLY_CLOSE_END = dt.time(13, 0)
AFTERHOURS_END = dt.time(20, 0)


def _easter(year):
    """Anonymous Gregorian algorithm. Good Friday is Easter minus two days,
    and it is the only NYSE holiday that is not a fixed or nth-weekday rule."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month, day = divmod(h + lam - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def _nth_weekday(year, month, weekday, n):
    """The nth weekday of a month. weekday follows date.weekday(): Mon=0."""
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    if month == 12:
        following = dt.date(year + 1, 1, 1)
    else:
        following = dt.date(year, month + 1, 1)
    last = following - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day):
    """NYSE shifts a weekend holiday to the adjacent weekday."""
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def holidays(year):
    """Full-day NYSE closures for a calendar year, already observed-shifted."""
    fixed = [
        dt.date(year, 1, 1),
        dt.date(year, 6, 19),
        dt.date(year, 7, 4),
        dt.date(year, 12, 25),
    ]
    days = {_observed(day) for day in fixed}
    days.add(_nth_weekday(year, 1, 0, 3))        # MLK Day
    days.add(_nth_weekday(year, 2, 0, 3))        # Washington's Birthday
    days.add(_easter(year) - dt.timedelta(days=2))   # Good Friday
    days.add(_last_weekday(year, 5, 0))          # Memorial Day
    days.add(_nth_weekday(year, 9, 0, 1))        # Labor Day
    days.add(_nth_weekday(year, 11, 3, 4))       # Thanksgiving
    return days


def early_close_days(year):
    """1pm ET closes. Each is only an early close when it lands on a day the
    market is otherwise open."""
    candidates = {
        _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1),   # day after Thanksgiving
        dt.date(year, 7, 3),
        dt.date(year, 12, 24),
    }
    closed = holidays(year)
    return {
        day for day in candidates
        if day.weekday() < 5 and day not in closed
    }


def is_trading_day(day):
    return day.weekday() < 5 and day not in holidays(day.year)


def session_state(when_utc):
    """One of 'premarket', 'regular', 'afterhours', 'closed'."""
    if when_utc.tzinfo is None:
        raise ValueError('session_state requires a timezone-aware UTC datetime')

    local = when_utc.astimezone(NY)
    day = local.date()
    if not is_trading_day(day):
        return 'closed'

    close = EARLY_CLOSE_END if day in early_close_days(day.year) else REGULAR_END
    now = local.time()

    if PREMARKET_START <= now < REGULAR_START:
        return 'premarket'
    if REGULAR_START <= now < close:
        return 'regular'
    if close <= now < AFTERHOURS_END:
        return 'afterhours'
    return 'closed'
