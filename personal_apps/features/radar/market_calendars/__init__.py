"""Market-specific session calendars, expressed through UTC instants."""
import dataclasses
from datetime import datetime
from typing import Literal

Session = Literal['premarket', 'regular', 'afterhours', 'closed']


@dataclasses.dataclass(frozen=True)
class SessionBounds:
    opens_at: datetime
    regular_opens_at: datetime
    regular_closes_at: datetime
    closes_at: datetime


from . import de, us

_CALENDARS = {
    'us': us,
    'de': de,
}


def _calendar(market: str):
    try:
        return _CALENDARS[market]
    except KeyError:
        raise ValueError(f'unknown market: {market}') from None


def session_state(market: str, when_utc: datetime) -> Session:
    """Return the session state for ``market`` at an aware UTC instant."""
    return _calendar(market).session_state(when_utc)


def session_bounds(market: str, when_utc: datetime) -> SessionBounds:
    """Return that local calendar day's session boundaries in UTC."""
    return _calendar(market).session_bounds(when_utc)
