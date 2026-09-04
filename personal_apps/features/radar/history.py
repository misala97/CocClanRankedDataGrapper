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
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarDailyClose

# Higher priority wins a live row; equal priority permits provider
# restatement. massive_grouped outranks the unofficial and incumbent US
# writers; native Deutsche Börse closes outrank everything [A1].
CLOSE_SOURCE_PRIORITY = {
    'legacy': 0,
    'twelvedata': 10,
    'yahoo_chart': 10,
    'massive_grouped': 12,
    'deutsche_boerse_delayed': 20,
}

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
    return [RadarDailyClose.ticker == ticker, _market_filter(market, mic)]


def _market_filter(market, mic):
    """Match an instrument while treating `(NULL, NULL)` as legacy US."""
    if market == 'us' and mic is not None:
        return sa.or_(
            sa.and_(RadarDailyClose.market == 'us', RadarDailyClose.mic == mic),
            sa.and_(RadarDailyClose.market.is_(None),
                    RadarDailyClose.mic.is_(None)))

    market_filter = RadarDailyClose.market == market
    if market == 'us':
        market_filter = sa.or_(
            market_filter,
            sa.and_(RadarDailyClose.market.is_(None),
                    RadarDailyClose.mic.is_(None)))
    if mic is None:
        return market_filter
    return sa.and_(market_filter, RadarDailyClose.mic == mic)


def record_closes(ticker, closes, now, *, market='us', mic=None,
                  currency='USD', source='legacy', price_basis='close',
                  adjustment_basis=None, is_shadow=False, commit=True):
    """Upsert (date, close) pairs for one ticker. Returns rows written.

    Upsert rather than append: providers restate recent bars. Overwrites
    obey CLOSE_SOURCE_PRIORITY -- an existing row survives a lower-priority
    write, equal priority is provider restatement, and a migration-era NULL
    source reads as ``legacy``. The upsert identity includes ``is_shadow``:
    the shadow lane can never overwrite or block the live row for one date.
    """
    from .prices import validate_close_source
    validate_close_source(source, price_basis, adjustment_basis)
    if source in ('massive_grouped',) and adjustment_basis != 'split':
        # Every selected v2 provider writes split-only provenance; a
        # source/basis conflict is refused rather than overwritten.
        raise ValueError(f'{source} closes must declare adjustment split')
    if not closes:
        return 0

    incoming_priority = CLOSE_SOURCE_PRIORITY[source]
    existing = {row.close_date: row for row in RadarDailyClose.query.filter(
        *_market_filters(ticker, market, mic),
        RadarDailyClose.is_shadow.is_(bool(is_shadow)),
        RadarDailyClose.close_date.in_([day for day, _ in closes])).all()}

    written = 0
    for day, close in closes:
        row = existing.get(day)
        if row is None:
            db.session.add(RadarDailyClose(
                ticker=ticker, market=market, mic=mic, currency=currency,
                close_date=day, close=close, fetched_at=now,
                source=source, price_basis=price_basis,
                adjustment_basis=adjustment_basis, is_shadow=is_shadow))
            written += 1
            continue
        stored_priority = CLOSE_SOURCE_PRIORITY.get(
            row.source or 'legacy', 0)
        if incoming_priority < stored_priority:
            continue
        row.close = close
        row.fetched_at = now
        row.market = market
        row.mic = mic
        row.currency = currency
        row.source = source
        row.price_basis = price_basis
        row.adjustment_basis = adjustment_basis
        written += 1

    if commit:
        db.session.commit()
    return written


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

    rows = (db.session.query(RadarDailyClose.ticker,
                             RadarDailyClose.close_date,
                             RadarDailyClose.close)
            .filter(RadarDailyClose.ticker.in_(list(tickers)),
                    _market_filter(market, mic),
                    RadarDailyClose.is_shadow.is_(False),
                    RadarDailyClose.close_date >= since,
                    RadarDailyClose.close_date <= today)
            .order_by(RadarDailyClose.close_date.asc()).all())

    series = collections.defaultdict(list)
    for ticker, day, close in rows:
        series[ticker].append((day, close))
    return dict(series)


# A line needs two points. One stored close is a dot, and a dot drawn as a
# price line is a claim about a trend that one number cannot support.
MIN_BASIS_CLOSES = 2


@dataclasses.dataclass(frozen=True)
class HistoryBasis:
    """Where one chart's price line actually came from.

    The venue that QUOTES a ticker and the venue that has its HISTORY are
    different questions, and the panel used to answer both with the quote.
    On the German board that made a Nasdaq listing read its two stored
    Tradegate closes instead of its 780 stored Nasdaq ones.

    `currency` is the currency `closes` is expressed in, which the axis and
    the hover read. `converted_from` is set only when these closes were
    priced in another currency and converted here -- the renderer states it
    beside the chart, because a converted line must never read as native.
    """
    closes: tuple
    market: str | None
    mic: str | None
    venue: str | None
    currency: str | None
    converted_from: str | None


EMPTY_BASIS = HistoryBasis(closes=(), market=None, mic=None, venue=None,
                           currency=None, converted_from=None)


def _native_basis(ticker, quote, days, today):
    rows = closes_for([ticker], days=days, today=today,
                      market=quote.market, mic=quote.mic).get(ticker, [])
    return HistoryBasis(closes=tuple(rows), market=quote.market,
                        mic=quote.mic, venue=quote.venue,
                        currency=quote.currency, converted_from=None)


def _sibling_basis(ticker, quote, days, today):
    """The other venue in the same market, when it is provably the same paper.

    Same ISIN, both non-null, same currency. That is the §8.2 test the old
    Xetra proxy used, moved here: it was always a question about which
    series may stand in for which, and never about how to stitch them.
    """
    from models import RadarInstrument
    rows = RadarInstrument.query.filter_by(
        ticker=ticker, market=quote.market).all()
    here = next((r for r in rows if r.mic == quote.mic), None)
    if here is None or here.isin is None:
        return None
    sibling = next((r for r in rows
                    if r.mic != quote.mic and r.isin == here.isin
                    and r.currency == here.currency), None)
    if sibling is None:
        return None
    closes = closes_for([ticker], days=days, today=today,
                        market=sibling.market, mic=sibling.mic).get(ticker, [])
    return HistoryBasis(closes=tuple(closes), market=sibling.market,
                        mic=sibling.mic, venue=sibling.venue,
                        currency=sibling.currency, converted_from=None)


def _converted_basis(ticker, quote, days, today):
    """The primary US listing, in the quote's currency.

    Only EUR is served, because only the German board asks. A pair we cannot
    price returns None rather than an unconverted dollar series: a USD line
    under a EUR axis label is the exact lie this whole basis exists to stop.
    """
    if quote.currency != 'EUR':
        return None

    from models import RadarInstrument
    us = (RadarInstrument.query
          .filter_by(ticker=ticker, market='us', is_primary=True)
          .first())
    if us is None:
        return None

    closes = closes_for([ticker], days=days, today=today,
                        market='us', mic=us.mic).get(ticker, [])
    if not closes:
        return None

    from . import fx
    first_close = min(day for day, _ in closes)
    series = fx.rate_series(
        first_close - dt.timedelta(days=fx.MAX_CARRY_DAYS), today)
    converted = fx.convert_usd_to_eur(closes, series)
    if not converted:
        return None
    return HistoryBasis(closes=converted, market='us', mic=us.mic,
                        venue=us.venue, currency='EUR', converted_from='USD')


def resolve_basis(ticker, quote, days, today):
    """The chartable series for one ticker over `days`, and where it is from.

    Candidates in precedence order -- the quote's own venue, the ISIN-matched
    sibling, the converted US primary -- and the one with the MOST closes in
    the span wins. `max` keeps the first of equal counts, so precedence breaks
    ties. Evaluated per span on purpose: a ticker may have a deep Xetra month
    and a deeper converted three years, and each span should draw the most
    price it can while saying which venue that was.

    Fewer than MIN_BASIS_CLOSES is not a candidate at all. When nothing
    qualifies the caller gets EMPTY_BASIS and the panel says so, which is the
    honest answer and the one the renderer already draws.
    """
    candidates = [_native_basis(ticker, quote, days, today),
                  _sibling_basis(ticker, quote, days, today),
                  _converted_basis(ticker, quote, days, today)]
    usable = [c for c in candidates
              if c is not None and len(c.closes) >= MIN_BASIS_CLOSES]
    if not usable:
        return EMPTY_BASIS
    return max(usable, key=lambda c: len(c.closes))


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

    rows = (db.session.query(
        RadarDailyClose.ticker,
        db.func.max(RadarDailyClose.close_date),
        db.func.count())
        .filter(RadarDailyClose.ticker.in_(list(candidates)),
                _market_filter(market, mic))
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
                      currency=currency,
                      source=getattr(provider, 'source', 'legacy'),
                      adjustment_basis=(
                          'split' if getattr(provider, 'source', None)
                          in ('yahoo_chart', 'massive_grouped',
                              'twelvedata') else None))
        stored += 1
    return stored
