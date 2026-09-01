"""Market-specific session calendars, expressed through UTC instants."""
import dataclasses
from datetime import datetime
from typing import Literal

Session = Literal['premarket', 'regular', 'afterhours', 'closed']


@dataclasses.dataclass(frozen=True)
class SessionBounds:
    opens_at: datetime
    premarket_closes_at: datetime
    regular_opens_at: datetime
    regular_closes_at: datetime
    closes_at: datetime


from . import de, tradegate, us


def _calendar(market: str, mic: str | None = None):
    """Calendars are selected by MIC, not one process-global German clock.

    ``de`` with no MIC stays Xetra-compatible for every pre-v2 caller.
    """
    if market == 'us':
        return us
    if market == 'de' and mic == 'XGAT':
        return tradegate
    if market == 'de' and mic in (None, 'XETR'):
        return de
    raise ValueError(f'unknown market/MIC: {market}/{mic}')


def session_state(market: str, when_utc: datetime,
                  mic: str | None = None) -> Session:
    """Return the session state for ``market`` at an aware UTC instant."""
    return _calendar(market, mic).session_state(when_utc)


def session_bounds(market: str, when_utc: datetime,
                   mic: str | None = None) -> SessionBounds:
    """Return that local calendar day's session boundaries in UTC."""
    return _calendar(market, mic).session_bounds(when_utc)
