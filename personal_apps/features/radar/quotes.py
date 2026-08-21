# personal_apps/features/radar/quotes.py
"""Price snapshots, frozen-tape detection, and volatility.

The frozen-tape check is the reason quotes are stored as snapshots rather than
as one current price. A halted stock keeps its last print while mentions
explode BECAUSE it halted -- which is maximum divergence produced entirely by
an artifact, and halts cluster on exactly the micro caps that dominate this
board.

The same signature comes from a stock too illiquid for anyone to have traded
it. The data cannot separate the two, so the mark is NO PRINT rather than HALT
(a deliberate wording change from spec 6.5): both are untradeable, and calling
an empty tape a halt claims more than the data supports.
"""
import datetime as dt
import decimal
import statistics

from extensions import db
from models import RadarQuote

from .config import MIN_CLOSES_FOR_SIGMA, SESSION_HOURS, STALE_QUOTE_POLLS


def record_quotes(quotes, now):
    """Store a snapshot per quote. Returns how many were written."""
    written = 0
    for quote in quotes.values():
        db.session.add(RadarQuote(
            ticker=quote.ticker, fetched_at=now, quote_ts=quote.quote_ts,
            price=quote.price, prev_close=quote.prev_close,
            volume=quote.volume))
        written += 1
    db.session.commit()
    return written


def price_status(ticker, now, polls=STALE_QUOTE_POLLS):
    """'ok', 'stale', or 'unknown'.

    'unknown' is deliberately distinct from 'stale'. Never quoted is a
    different fact from quoted-and-frozen, and only the second is evidence
    about the stock.
    """
    recent = (RadarQuote.query
              .filter(RadarQuote.ticker == ticker,
                      RadarQuote.fetched_at <= now)
              .order_by(RadarQuote.fetched_at.desc())
              .limit(polls).all())

    if not recent:
        return 'unknown'
    if len(recent) < polls:
        return 'ok'

    signatures = {(row.quote_ts, row.volume) for row in recent}
    # Both frozen, not just one: a stale timestamp with rising volume is a
    # provider quirk rather than a stopped tape.
    return 'stale' if len(signatures) == 1 else 'ok'


def daily_sigma(closes):
    """Standard deviation of daily returns, or None if history is too thin."""
    if len(closes) < MIN_CLOSES_FOR_SIGMA:
        return None

    returns = []
    for (_, earlier), (_, later) in zip(closes, closes[1:]):
        if earlier and earlier != 0:
            returns.append(float(later / earlier) - 1.0)

    if len(returns) < 2:
        return None
    return statistics.pstdev(returns)


def move_since(ticker, hours, now):
    """Fractional price change across the window, or None.

    Measured between the oldest and newest snapshots inside the window, so it
    answers the question divergence asks -- has the price moved while this was
    being discussed -- rather than comparing against a stale reference point
    outside it.
    """
    since = now - dt.timedelta(hours=hours)
    rows = (RadarQuote.query
            .filter(RadarQuote.ticker == ticker,
                    RadarQuote.fetched_at >= since,
                    RadarQuote.fetched_at <= now)
            .order_by(RadarQuote.fetched_at.asc()).all())

    if len(rows) < 2:
        return None

    first, last = rows[0].price, rows[-1].price
    if not first:
        return None
    return (last - first) / first


def scale_sigma(sigma, hours):
    """A daily sigma scaled to a shorter window, by the square root of time."""
    if sigma is None:
        return None
    return sigma * ((hours / SESSION_HOURS) ** 0.5)


def refresh_sigma(provider, tickers, now):
    """Recompute and store daily volatility. Returns how many were updated.

    A ticker whose provider returns no history keeps whatever it had. No
    history is not a volatility of zero, and a zero sigma downstream turns
    every price move into an infinite z.
    """
    from models import TickerUniverse

    updated = 0
    for ticker in tickers:
        closes = provider.daily_closes(ticker, days=35)
        sigma = daily_sigma(closes)
        if sigma is None:
            continue

        row = TickerUniverse.query.filter_by(symbol=ticker).one_or_none()
        if row is None:
            continue
        row.daily_sigma = sigma
        row.sigma_refreshed_at = now
        updated += 1

    db.session.commit()
    return updated
