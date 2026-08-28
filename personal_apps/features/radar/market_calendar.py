# personal_apps/features/radar/market_calendar.py
"""Legacy NYSE calendar compatibility wrapper.

New code should use :mod:`features.radar.market_calendars` and provide an
explicit market. This module deliberately continues to expose the original US
helpers until existing callers migrate.
"""
from .market_calendars import session_state as _registry_session_state
from .market_calendars.us import (
    AFTERHOURS_END,
    EARLY_CLOSE_END,
    NY,
    PREMARKET_START,
    REGULAR_END,
    REGULAR_START,
    early_close_days,
    holidays,
    is_trading_day,
)


def session_state(when_utc):
    """Return the NYSE session state for an aware UTC instant."""
    return _registry_session_state('us', when_utc)
