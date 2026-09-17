"""The US market session calendar, expressed through UTC instants."""
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


from . import us


def _calendar(market: str, mic: str | None = None):
    """Radar keeps one calendar: the US one.

    Every US caller passes its quote's MIC (XNAS, XNYS, ...); the US calendar
    serves them all, so the MIC is accepted and not consulted. Any other
    market -- including the retired one -- is refused whatever MIC it names.
    """
    del mic
    if market == 'us':
        return us
    raise ValueError(f'unknown market: {market}')


def session_state(market: str, when_utc: datetime,
                  mic: str | None = None) -> Session:
    """Return the session state for ``market`` at an aware UTC instant."""
    return _calendar(market, mic).session_state(when_utc)


def session_bounds(market: str, when_utc: datetime,
                   mic: str | None = None) -> SessionBounds:
    """Return that local calendar day's session boundaries in UTC."""
    return _calendar(market, mic).session_bounds(when_utc)
