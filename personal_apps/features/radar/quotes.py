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
import collections
import datetime as dt
import decimal
import statistics

import sqlalchemy as sa

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
            volume=quote.volume, market=quote.market, mic=quote.mic,
            currency=quote.currency, provider_symbol=quote.provider_symbol))
        written += 1
    db.session.commit()
    return written


def _instrument_identity(instrument):
    """Return ``(ticker, market, mic, result_key)`` for old and new callers."""
    if isinstance(instrument, str):
        return instrument, 'us', None, instrument
    if isinstance(instrument, tuple):
        ticker, market, *rest = instrument
        return ticker, market, rest[0] if rest else None, (ticker, market)
    return (instrument.ticker, instrument.market, instrument.mic,
            (instrument.ticker, instrument.market))


def _quote_matches(ticker, market, mic):
    clauses = [RadarQuote.ticker == ticker]
    # During the expand/write overlap, `(NULL, NULL)` is the legacy US
    # identity.  A requested primary MIC must include that pair; filtering
    # only `market IS NULL` and then requiring the MIC loses old snapshots.
    if market == 'us' and mic is not None:
        clauses.append(sa.or_(
            sa.and_(RadarQuote.market == 'us', RadarQuote.mic == mic),
            sa.and_(RadarQuote.market.is_(None), RadarQuote.mic.is_(None))))
    else:
        market_clause = RadarQuote.market == market
        if market == 'us':
            market_clause = sa.or_(
                market_clause,
                sa.and_(RadarQuote.market.is_(None), RadarQuote.mic.is_(None)))
        clauses.append(market_clause)
        if mic is not None:
            clauses.append(RadarQuote.mic == mic)
    return clauses


def _stored_identity_matches(stored_market, stored_mic, market, mic):
    """Whether an already-selected row belongs to the requested instrument."""
    if stored_market != market:
        if not (market == 'us' and stored_market is None and stored_mic is None):
            return False
    return mic is None or stored_mic == mic or (
        market == 'us' and stored_market is None and stored_mic is None)


def price_status(ticker, now, polls=STALE_QUOTE_POLLS, session=None,
                 market='us', mic=None):
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
              .filter(*_quote_matches(ticker, market, mic),
                      RadarQuote.fetched_at <= now)
              .order_by(RadarQuote.fetched_at.desc())
              .limit(polls).all())
    return _status_from(recent, polls, session)


def _status_from(recent, polls, session):
    """The rule itself, given a ticker's most recent `polls` snapshots.

    Split out so the batched lookup below decides with THIS function rather
    than a copy of it. Whether a tape counts as frozen is a judgement, and two
    implementations of one judgement is how a no-print mark ends up on a
    different set of rows depending on which code path asked.
    """
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


def statuses_for(instruments, now, polls=STALE_QUOTE_POLLS, session=None):
    """`price_status` for many tickers at once, with each latest snapshot.

    Returns {ticker: (status, latest_row_or_None)} covering every ticker asked
    about, including ones with no quote at all -- absent from the mapping and
    'unknown' are not the same answer, and a caller that used `.get()` on a
    partial mapping would silently turn the second into the first.

    One query instead of two per ticker. `leaderboard.build_rows` ranks every
    eligible ticker before the segment filter, so the per-ticker version there
    cost roughly 1200 round trips on the live board and 1.5 seconds of the
    page's time to first byte.

    ROW_NUMBER is the only way to take the newest `polls` rows PER ticker in
    one statement. A time window cannot substitute: quotes are only fetched
    for tickers the board is watching, so a name that went quiet weeks ago has
    three real snapshots that any recent window would miss, and it would drop
    from 'ok' to 'unknown' -- which says something about the stock rather than
    about our polling. Needs MariaDB 10.2+ / MySQL 8+, both long past.
    """
    instruments = list(instruments)
    if not instruments:
        return {}

    identities = [_instrument_identity(instrument) for instrument in instruments]
    tickers = {ticker for ticker, _, _, _ in identities}
    markets = {market for _, market, _, _ in identities}

    market_clause = RadarQuote.market.in_(markets)
    if 'us' in markets:
        market_clause = sa.or_(market_clause, RadarQuote.market.is_(None))
    numbered = sa.select(
        RadarQuote,
        sa.func.row_number().over(
            partition_by=(RadarQuote.ticker, RadarQuote.market, RadarQuote.mic),
            order_by=RadarQuote.fetched_at.desc()).label('rn'),
    ).where(RadarQuote.ticker.in_(tickers), market_clause,
            RadarQuote.fetched_at <= now).subquery()

    entity = sa.orm.aliased(RadarQuote, numbered)
    rows = db.session.execute(
        sa.select(entity, numbered.c.rn)
        .where(numbered.c.rn <= polls)
        .order_by(numbered.c.ticker, numbered.c.rn)).all()

    recent = collections.defaultdict(list)
    for quote, _ in rows:
        recent[(quote.ticker, quote.market, quote.mic)].append(quote)

    result = {}
    for ticker, market, mic, key in identities:
        matching = []
        for (stored_ticker, stored_market, stored_mic), rows_for_identity in recent.items():
            if (stored_ticker != ticker or
                    not _stored_identity_matches(
                        stored_market, stored_mic, market, mic)):
                continue
            matching.extend(rows_for_identity)
        matching.sort(key=lambda row: row.fetched_at, reverse=True)
        matching = matching[:polls]
        result[key] = (_status_from(matching, polls, session),
                       matching[0] if matching else None)
    return result


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


def move_since(ticker, hours, now, market='us', mic=None):
    """Fractional price change across the window, or None.

    Measured between the oldest and newest snapshots inside the window, so it
    answers the question divergence asks -- has the price moved while this was
    being discussed -- rather than comparing against a stale reference point
    outside it.
    """
    since = now - dt.timedelta(hours=hours)
    rows = (RadarQuote.query
            .filter(*_quote_matches(ticker, market, mic),
                    RadarQuote.fetched_at >= since,
                    RadarQuote.fetched_at <= now)
            .order_by(RadarQuote.fetched_at.asc()).all())

    return _move_from([row.price for row in rows])


def _move_from(prices):
    """The rule, given a ticker's prices across the window in time order."""
    if len(prices) < 2:
        return None
    first, last = prices[0], prices[-1]
    if not first:
        return None
    return (last - first) / first


def moves_for(instruments, hours, now):
    """`move_since` for many tickers in one query.

    Returns {ticker: fraction_or_None} for every ticker asked about. None means
    the window holds fewer than two snapshots, which is not a flat price -- see
    `_move_from`, which both this and the single-ticker version decide with.
    """
    instruments = list(instruments)
    if not instruments:
        return {}

    identities = [_instrument_identity(instrument) for instrument in instruments]
    tickers = {ticker for ticker, _, _, _ in identities}
    markets = {market for _, market, _, _ in identities}

    since = now - dt.timedelta(hours=hours)
    market_clause = RadarQuote.market.in_(markets)
    if 'us' in markets:
        market_clause = sa.or_(market_clause, RadarQuote.market.is_(None))
    rows = (db.session.query(RadarQuote.ticker, RadarQuote.market,
                             RadarQuote.mic, RadarQuote.price)
            .filter(RadarQuote.ticker.in_(tickers),
                    market_clause,
                    RadarQuote.fetched_at >= since,
                    RadarQuote.fetched_at <= now)
            .order_by(RadarQuote.ticker, RadarQuote.market, RadarQuote.mic,
                      RadarQuote.fetched_at.asc()).all())

    prices = collections.defaultdict(list)
    for ticker, market, mic, price in rows:
        prices[(ticker, market, mic)].append(price)

    result = {}
    for ticker, market, mic, key in identities:
        matching = []
        for (stored_ticker, stored_market, stored_mic), values in prices.items():
            if (stored_ticker != ticker or
                    not _stored_identity_matches(
                        stored_market, stored_mic, market, mic)):
                continue
            matching.extend(values)
        result[key] = _move_from(matching)
    return result


def scale_sigma(sigma, hours):
    """A daily sigma scaled to a shorter window, by the square root of time."""
    if sigma is None:
        return None
    return sigma * ((hours / SESSION_HOURS) ** 0.5)


def refresh_sigma(tickers, now):
    """Recompute and store daily volatility from stored closes. Returns how
    many were updated.

    Reads radar_daily_closes rather than calling the provider. It used to
    fetch thirty-five closes per ticker every twelve hours and discard them;
    the history job now keeps a year of the same data, and on an
    eight-request-a-minute budget the duplicate fetch competed directly with
    the tickers that have no history at all.

    A ticker without enough stored history keeps whatever sigma it had. No
    history is not a volatility of zero, and a zero sigma downstream turns
    every price move into an infinite z.
    """
    from models import TickerUniverse

    from . import history

    stored = history.closes_for(tickers, days=history.HISTORY_DAYS)

    updated = 0
    for ticker in tickers:
        sigma = daily_sigma(stored.get(ticker, []))
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
