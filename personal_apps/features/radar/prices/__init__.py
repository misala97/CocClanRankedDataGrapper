# personal_apps/features/radar/prices/__init__.py
"""What the rest of the radar sees of a market data provider.

One module knows a provider's JSON; everything else sees these two shapes.
That boundary is not decoration -- free market data terms change often, and
this project already lost Reddit mid-build to exactly that kind of change.
"""
import dataclasses
import datetime as dt
import decimal


class PriceUnavailable(Exception):
    """This request did not arrive. Never becomes a zero price."""


@dataclasses.dataclass
class Quote:
    ticker: str
    price: decimal.Decimal
    prev_close: decimal.Decimal | None
    quote_ts: dt.datetime | None
    volume: int | None


@dataclasses.dataclass
class Profile:
    ticker: str
    market_cap: decimal.Decimal | None
    ipo_date: dt.date | None
    exchange: str | None
