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


def price_status(ticker, now, polls=STALE_QUOTE_POLLS, session=None):
    """'ok', 'closed', 'stale', or 'unknown'.

    Each is a different fact and they must not collapse into each other:

    - 'unknown' -- never quoted. Says nothing about the stock.
    - 'closed'  -- the exchange is shut. Says nothing about the stock either;
                   it is a property of the clock.
    - 'stale'   -- the market is open and this tape still is not printing.
                   THAT is evidence about the stock, and the only one of the
                   three that earns the no-print mark.
    - 'ok'      -- a live, moving tape.

    'closed' exists because without it a Saturday marked all 52 tickers
    no-print, which reads as "every one of these is untradeable" when the real
    statement is "it is the weekend". Nights and weekends are around 60% of
    the clock, so this is the common case, not an edge case.

    `session` comes from market_calendar; it is a parameter rather than a
    lookup so a caller scoring many tickers computes it once.
    """
    recent = (RadarQuote.query
              .filter(RadarQuote.ticker == ticker,
                      RadarQuote.fetched_at <= now)
              .order_by(RadarQuote.fetched_at.desc())
              .limit(polls).all())

    if not recent:
        return 'unknown'
    if session == 'closed':
        # A frozen tape outside trading hours is the exchange being shut, not
        # this stock failing to trade. Premarket and afterhours are NOT closed:
        # those tapes are thin but real, and a stock not printing in them is
        # exactly the illiquidity the mark is for.
        return 'closed'
    if len(recent) < polls:
        return 'ok'

    signatures = {(row.quote_ts, row.volume) for row in recent}
    # Two signals rather than one: a stale timestamp with rising volume is a
    # provider quirk rather than a stopped tape.
    #
    # HONESTLY, TODAY THERE IS ONE. Finnhub's /quote returns c, d, dp, h, l, o,
    # pc and t -- no volume field, verified against the live API -- so
    # RadarQuote.volume is always NULL and this reduces to comparing quote_ts.
    # The pair is kept because it is the correct rule and a provider that does
    # send volume restores the second signal for free; what was wrong was the
    # comment claiming a safeguard that has never been active.
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
