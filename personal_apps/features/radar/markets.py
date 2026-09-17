"""Normalized US quote quality and movement.

Radar prices US listings in US dollars only. A snapshot from any other market
or in any other currency is never selected, converted or relabelled.
"""
import dataclasses
import datetime as dt
import decimal
from collections.abc import Iterable, Mapping
from typing import Literal

from .market_calendars import session_state
from .prices import Quote


Market = Literal['us']
MARKET = 'us'
CURRENCY = 'USD'
TapeStatus = Literal['ok', 'closed', 'stale', 'unknown']
QUALITY_STATES = frozenset({'live', 'delayed', 'eod', 'stale', 'unavailable'})
TAPE_STATUSES = frozenset({'ok', 'closed', 'stale', 'unknown'})
DELAYED_ELIGIBILITY_SECONDS = 30 * 60


def _utc_naive(when: dt.datetime | None) -> dt.datetime | None:
    if when is None:
        return None
    if when.tzinfo is not None:
        return when.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return when


def _utc_aware(when: dt.datetime) -> dt.datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(dt.timezone.utc)


def _age_seconds(quote_ts: dt.datetime | None, fetched_at: dt.datetime | None,
                 now: dt.datetime) -> int | None:
    # Age is a fact about the PROVIDER EVENT TIME. A fetch receipt proves a
    # request completed, not that the market said anything; it never makes
    # old data fresh (spec §3 rule 5 / §9.3). fetched_at stays a parameter
    # only so callers keep one signature while it remains diagnostic-only.
    del fetched_at
    observed_at = _utc_naive(quote_ts)
    if observed_at is None:
        return None
    return max(0, int((_utc_naive(now) - observed_at).total_seconds()))


def classify_quality(quote_ts: dt.datetime | None, fetched_at: dt.datetime | None,
                     provider_delay: str, now: dt.datetime) -> str:
    """Return the user-facing quality state for a provider snapshot.

    Missing provider time is ``unavailable`` -- never inferred from fetch
    time.
    """
    if provider_delay not in {'live', 'delayed', 'eod'}:
        raise ValueError(f'unknown provider delay: {provider_delay}')
    if provider_delay == 'eod':
        return 'eod'
    age = _age_seconds(quote_ts, fetched_at, now)
    if age is None:
        return 'unavailable'
    if age > DELAYED_ELIGIBILITY_SECONDS:
        return 'stale'
    return provider_delay


def _movement(price: decimal.Decimal | None,
              baseline: decimal.Decimal | None) -> decimal.Decimal | None:
    if price is None or baseline is None or baseline == 0:
        return None
    return price / baseline - decimal.Decimal(1)


@dataclasses.dataclass(frozen=True)
class QuoteView:
    """The only quote representation consumed by Radar presentation code."""
    ticker: str
    market: str
    venue: str | None
    mic: str | None
    provider_symbol: str | None
    currency: str | None
    price: decimal.Decimal | None
    previous_close: decimal.Decimal | None
    regular_close: decimal.Decimal | None
    quote_ts: dt.datetime | None
    volume: int | None
    session: str
    quality: str
    age_seconds: int | None
    tape_status: str
    score_eligible: bool
    regular_move: decimal.Decimal | None
    extended_move: decimal.Decimal | None
    source: str | None = None
    price_basis: str | None = None
    bid: decimal.Decimal | None = None
    ask: decimal.Decimal | None = None

    @property
    def score_term(self) -> str:
        """The term this quote permits the board to use for its row score."""
        return 'divergence' if self.score_eligible else 'chatter'

    @classmethod
    def unavailable(cls, ticker: str, market: str) -> 'QuoteView':
        return cls(ticker=ticker, market=market, venue=None, mic=None,
                   provider_symbol=None, currency=None, price=None,
                   previous_close=None, regular_close=None, quote_ts=None,
                    volume=None, session='closed', quality='unavailable',
                   age_seconds=None, tape_status='unknown',
                   score_eligible=False, regular_move=None,
                   extended_move=None)

    @classmethod
    def from_snapshot(cls, quote: Quote, now: dt.datetime,
                      tape_status: TapeStatus = 'ok') -> 'QuoteView':
        """Build a view from a US dollar snapshot and its tape verdict.

        ``tape_status`` is supplied by quote-history code. Only ``'ok'``
        permits scoring; every other verdict is not a verified open tape,
        even when this provider snapshot is otherwise fresh.
        """
        if tape_status not in TAPE_STATUSES:
            raise ValueError(f'unknown tape status: {tape_status}')
        if quote.market != MARKET:
            raise ValueError(f'not a US snapshot: {quote.market}')
        if quote.currency != CURRENCY:
            raise ValueError(f'not a USD snapshot: {quote.currency}')
        # Session may use the current clock for a row without provider time,
        # but no price/move/eligibility can come from that missing time.
        observed_at = quote.quote_ts or now
        session = session_state(quote.market, _utc_aware(observed_at),
                                mic=quote.mic)
        age_seconds = _age_seconds(quote.quote_ts, quote.fetched_at, now)
        quality = classify_quality(quote.quote_ts, quote.fetched_at,
                                   quote.provider_delay, now)
        return cls(
            ticker=quote.ticker, market=quote.market, venue=quote.venue,
            mic=quote.mic, provider_symbol=quote.provider_symbol,
            currency=quote.currency, price=quote.price,
            previous_close=quote.previous_close, regular_close=quote.regular_close,
            quote_ts=quote.quote_ts, volume=quote.volume, session=session,
            quality=quality, age_seconds=age_seconds,
            tape_status=tape_status,
            # Only a fresh executed trade on a moving tape may produce
            # divergence: midpoints are visible-not-eligible.
            score_eligible=(quality in {'live', 'delayed'} and
                            tape_status == 'ok' and
                            quote.price_basis == 'trade'),
            regular_move=_movement(quote.price, quote.previous_close),
            extended_move=(
                _movement(quote.price, quote.previous_close)
                if session == 'premarket' else
                _movement(quote.price, quote.regular_close)
                if session == 'afterhours' else None),
            source=quote.source, price_basis=quote.price_basis,
            bid=quote.bid, ask=quote.ask,
        )


def _quotes_for(snapshots: Mapping[str, object], market: str) -> list[Quote]:
    value = snapshots.get(market)
    if value is None:
        return []
    if isinstance(value, Quote):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [quote for quote in value if isinstance(quote, Quote)]
    return []


def _primary_quote(ticker: str,
                   snapshots: Mapping[str, object]) -> Quote | None:
    # A snapshot filed under the US key is still checked: only a US dollar
    # print of this ticker is a candidate. The current primary instrument
    # supplies the MIC, and the caller hands this function only its rows.
    quotes = [quote for quote in _quotes_for(snapshots, MARKET)
              if quote.ticker == ticker and quote.market == MARKET
              and quote.currency == CURRENCY]
    if not quotes:
        return None
    return max(quotes, key=lambda quote: _utc_naive(quote.fetched_at) or
               _utc_naive(quote.quote_ts) or dt.datetime.min)


def select_quote(ticker: str, requested_market: Market,
                 snapshots: Mapping[str, object], now: dt.datetime,
                 tape_status: TapeStatus = 'ok') -> QuoteView:
    """Select the honest US quote, retaining a stale snapshot as stale.

    Missing US data stays unavailable: there is no other market to fall back
    to, and no other currency to convert from.
    """
    if requested_market != MARKET:
        raise ValueError(f'unknown market: {requested_market}')

    requested = _primary_quote(ticker, snapshots)
    if requested is not None:
        view = QuoteView.from_snapshot(requested, now, tape_status=tape_status)
        if view.quality != 'unavailable':
            return view

    return QuoteView.unavailable(ticker, requested_market)
