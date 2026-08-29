# personal_apps/features/radar/history.py
"""Daily closes: what a ticker's price has been doing, over months.

Divergence measures hours, which is the right question about a stock you
already know and the wrong one the first time you see a ticker. Flat over four
hours while down 80% on the year and flat over four hours having tripled since
June are opposite situations behind an identical score. This is the context
that separates them -- read beside the score, never folded into it.

The provider allows eight requests a minute, so the interesting decision here
is not how to fetch but WHOM to ask about. A ticker with no history at all is
the one the board cannot describe, so it goes first.
"""
import collections
import datetime as dt

from extensions import db
from models import RadarDailyClose

# Three years of trading days. Was 260 -- a single year -- until 2026-08-23,
# when the detail panel gained a 3Y span.
#
# The long span is the one that answers "has this stock done this before",
# which is the whole reason a reader opens the panel on a ticker they have
# never heard of. ~780 rows x 247 tickers is about 190k rows, which is
# nothing, and one full backfill takes about an hour against the provider's
# eight-per-minute limit.
HISTORY_DAYS = 780

# A stored ticker counts as deep enough at this fraction of HISTORY_DAYS.
#
# Not 1.0. A listing younger than the window has less history than we ask for
# and always will, so an exact comparison would put every recent IPO back in
# the queue on every cycle -- spending the whole rate limit on precisely the
# tickers that can never satisfy it.
MIN_STORED_RATIO = 0.9

# How old the newest stored close may be before it is worth re-asking.
#
# Two days, not one. Over a weekend the provider has nothing newer than
# Friday, so a one-day rule would mark every ticker stale all weekend and
# spend the entire per-cycle budget re-fetching rows that cannot change --
# starving the tickers with no history at all, which are the only ones the
# board actually cannot draw.
STALE_AFTER_DAYS = 2


def _market_filters(ticker, market, mic):
    filters = [RadarDailyClose.ticker == ticker,
               RadarDailyClose.market == market]
    if market == 'us':
        filters[-1] = (RadarDailyClose.market == 'us') | \
                      RadarDailyClose.market.is_(None)
    if mic is not None:
        filters.append(RadarDailyClose.mic == mic)
    return filters


def record_closes(ticker, closes, now, *, market='us', mic=None, currency='USD'):
    """Upsert (date, close) pairs for one ticker. Returns rows written.

    Upsert rather than append: providers restate recent bars, and a second
    write for the same day must replace it or every overlapping point would be
    drawn twice.
    """
    if not closes:
        return 0

    existing = {row.close_date: row for row in RadarDailyClose.query.filter(
        *_market_filters(ticker, market, mic),
        RadarDailyClose.close_date.in_([day for day, _ in closes])).all()}

    for day, close in closes:
        row = existing.get(day)
        if row is None:
            db.session.add(RadarDailyClose(
                ticker=ticker, market=market, mic=mic, currency=currency,
                close_date=day, close=close, fetched_at=now))
        else:
            row.close = close
            row.fetched_at = now
            row.market = market
            row.mic = mic
            row.currency = currency

    db.session.commit()
    return len(closes)


def closes_for(tickers, days=HISTORY_DAYS, today=None, *, market='us', mic=None):
    """{ticker: [(date, close)]} oldest first, for tickers that have any.

    A ticker with nothing stored is ABSENT from the result rather than mapped
    to an empty list. The two mean different things downstream -- absent
    becomes a null payload and draws a dashed "not known" rule, while an empty
    series would draw a flat line and assert a price that held steady.
    """
    if not tickers:
        return {}

    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)

    market_filter = RadarDailyClose.market == market
    if market == 'us':
        market_filter = (RadarDailyClose.market == 'us') | \
                        RadarDailyClose.market.is_(None)
    rows = (db.session.query(RadarDailyClose.ticker,
                             RadarDailyClose.close_date,
                             RadarDailyClose.close)
            .filter(RadarDailyClose.ticker.in_(list(tickers)),
                    market_filter,
                    *([RadarDailyClose.mic == mic] if mic is not None else []),
                    RadarDailyClose.close_date >= since,
                    RadarDailyClose.close_date <= today)
            .order_by(RadarDailyClose.close_date.asc()).all())

    series = collections.defaultdict(list)
    for ticker, day, close in rows:
        series[ticker].append((day, close))
    return dict(series)


def tickers_needing_history(candidates, today, stale_after_days=STALE_AFTER_DAYS,
                            *, market='us', mic=None):
    """Which of `candidates` to spend requests on, most urgent first.

    Missing before stale before shallow, each keeping the caller's order --
    the caller passes them loudest first, and among tickers we cannot draw at
    all the loudest is the one most likely to be looked at next.

    Shallow comes last and exists because raising HISTORY_DAYS does nothing on
    its own: every already-stored ticker has a current newest close, so the
    staleness rule never fires for it and the store would sit at its old depth
    forever. A ticker we can already draw is the least urgent of the three.
    """
    if not candidates:
        return []

    market_filter = RadarDailyClose.market == market
    if market == 'us':
        market_filter = (RadarDailyClose.market == 'us') | \
                        RadarDailyClose.market.is_(None)
    rows = (db.session.query(
        RadarDailyClose.ticker,
        db.func.max(RadarDailyClose.close_date),
        db.func.count())
        .filter(RadarDailyClose.ticker.in_(list(candidates)),
                market_filter,
                *([RadarDailyClose.mic == mic] if mic is not None else []))
        .group_by(RadarDailyClose.ticker).all())
    newest = {ticker: day for ticker, day, _ in rows}
    stored = {ticker: count for ticker, _, count in rows}

    cutoff = today - dt.timedelta(days=stale_after_days)
    floor = int(HISTORY_DAYS * MIN_STORED_RATIO)

    missing = [t for t in candidates if t not in newest]
    stale = [t for t in candidates if t in newest and newest[t] < cutoff]
    seen = set(missing) | set(stale)
    shallow = [t for t in candidates
               if t not in seen and stored.get(t, 0) < floor]
    return missing + stale + shallow


def fetch_into_store(provider, tickers, now, *, market='us', mic=None,
                     currency='USD', provider_symbols=None):
    """Fetch a year of closes for each ticker and store it.

    Returns how many tickers came back with anything. A provider answering
    nothing leaves the stored rows alone: blanking a year of history because
    one call failed would empty the column for that ticker until the next
    cycle, which is worse than showing yesterday's.
    """
    stored = 0
    provider_symbols = provider_symbols or {}
    for ticker in tickers:
        symbol = provider_symbols.get(ticker, ticker)
        if mic is None:
            closes = provider.daily_closes(symbol, HISTORY_DAYS)
        else:
            closes = provider.daily_closes(symbol, HISTORY_DAYS, mic_code=mic)
        if not closes:
            continue
        record_closes(ticker, closes, now, market=market, mic=mic,
                      currency=currency)
        stored += 1
    return stored
