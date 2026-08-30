# personal_apps/features/radar/prices/__init__.py
"""What the rest of the radar sees of a market data provider.

One module knows a provider's JSON; everything else sees these two shapes.
That boundary is not decoration -- free market data terms change often, and
this project already lost Reddit mid-build to exactly that kind of change.
"""
import dataclasses
import datetime as dt
import decimal
from typing import Any


class PriceUnavailable(Exception):
    """This request did not arrive. Never becomes a zero price."""


class CurrencyMismatch(ValueError):
    """A provider returned a price in a currency other than its instrument."""


@dataclasses.dataclass(frozen=True, init=False)
class Quote:
    """Provider-neutral quote identity.

    ``prev_close`` remains a read-only compatibility alias while the existing
    US polling and persistence callers move to ``previous_close``.
    """
    ticker: str
    market: str
    venue: str
    mic: str
    provider_symbol: str
    currency: str
    price: decimal.Decimal
    previous_close: decimal.Decimal | None
    regular_close: decimal.Decimal | None
    quote_ts: dt.datetime | None
    volume: int | None
    provider_delay: str
    fetched_at: dt.datetime | None
    provider_mic: str | None

    def __init__(self, ticker: str, price: decimal.Decimal,
                 prev_close: decimal.Decimal | None = None,
                 quote_ts: dt.datetime | None = None,
                 volume: int | None = None, *, market: str = 'us',
                 venue: str = 'US', mic: str = 'XNAS',
                 provider_symbol: str | None = None, currency: str = 'USD',
                 previous_close: decimal.Decimal | None = None,
                 regular_close: decimal.Decimal | None = None,
                 provider_delay: str = 'delayed',
                 fetched_at: dt.datetime | None = None,
                 provider_mic: str | None = None):
        if provider_delay not in {'live', 'delayed', 'eod'}:
            raise ValueError(f'unknown provider delay: {provider_delay}')
        if previous_close is not None and prev_close is not None and \
                previous_close != prev_close:
            raise ValueError('previous_close and prev_close disagree')
        object.__setattr__(self, 'ticker', ticker)
        object.__setattr__(self, 'market', market)
        object.__setattr__(self, 'venue', venue)
        object.__setattr__(self, 'mic', mic)
        object.__setattr__(self, 'provider_symbol', provider_symbol or ticker)
        object.__setattr__(self, 'currency', currency)
        object.__setattr__(self, 'price', price)
        object.__setattr__(self, 'previous_close',
                           previous_close if previous_close is not None else prev_close)
        object.__setattr__(self, 'regular_close', regular_close)
        object.__setattr__(self, 'quote_ts', quote_ts)
        object.__setattr__(self, 'volume', volume)
        object.__setattr__(self, 'provider_delay', provider_delay)
        object.__setattr__(self, 'fetched_at', fetched_at)
        object.__setattr__(self, 'provider_mic', provider_mic)

    @property
    def prev_close(self):
        """Compatibility spelling used by the established US quote writers."""
        return self.previous_close


def _value(raw: Any, name: str, default=None):
    if isinstance(raw, dict):
        return raw.get(name, default)
    return getattr(raw, name, default)


def normalize_snapshot(instrument: Any, raw: Any) -> Quote:
    """Bind a provider result to a verified instrument without converting FX.

    The instrument owns ticker/venue/MIC/currency identity.  A provider price
    with a different currency is rejected rather than silently relabelled.
    """
    instrument_currency = _value(instrument, 'currency')
    raw_currency = _value(raw, 'currency')
    if instrument_currency != raw_currency:
        raise CurrencyMismatch(
            f'{_value(instrument, "ticker")} expects {instrument_currency}, '
            f'provider supplied {raw_currency}')

    expected_symbol = _value(instrument, 'provider_symbol')
    raw_symbol = _value(raw, 'provider_symbol') or _value(raw, 'ticker')
    if raw_symbol and raw_symbol != expected_symbol:
        raise ValueError(
            f'provider symbol {raw_symbol} does not match {expected_symbol}')
    provider_mic = _value(raw, 'provider_mic')
    if provider_mic and provider_mic != _value(instrument, 'mic'):
        raise ValueError(
            f'provider MIC {provider_mic} does not match '
            f'{_value(instrument, "mic")}')

    return Quote(
        ticker=_value(instrument, 'ticker'), market=_value(instrument, 'market'),
        venue=_value(instrument, 'venue'), mic=_value(instrument, 'mic'),
        provider_symbol=_value(instrument, 'provider_symbol'),
        currency=instrument_currency, price=_value(raw, 'price'),
        previous_close=_value(raw, 'previous_close', _value(raw, 'prev_close')),
        regular_close=_value(raw, 'regular_close'), quote_ts=_value(raw, 'quote_ts'),
        volume=_value(raw, 'volume'), provider_delay=_value(raw, 'provider_delay', 'delayed'),
        fetched_at=_value(raw, 'fetched_at'),
    )


@dataclasses.dataclass
class Profile:
    ticker: str
    market_cap: decimal.Decimal | None
    ipo_date: dt.date | None
    exchange: str | None
