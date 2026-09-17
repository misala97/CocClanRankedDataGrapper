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
# writers [A1].
CLOSE_SOURCE_PRIORITY = {
    'legacy': 0,
    'twelvedata': 10,
    'yahoo_chart': 10,
    'massive_grouped': 12,
}

# Radar stores and reads US dollar closes only. Archived non-US rows stay in
# the table untouched; no reader here selects them and no writer adds one.
MARKET = 'us'
CURRENCY = 'USD'

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


def _require_us(market):
    if market != MARKET:
        raise ValueError(f'unknown market: {market}')


def _market_filter(market, mic):
    """Match a US instrument while treating `(NULL, NULL)` as legacy US."""
    _require_us(market)
    legacy = sa.and_(RadarDailyClose.market.is_(None),
                     RadarDailyClose.mic.is_(None))
    if mic is not None:
        return sa.or_(
            sa.and_(RadarDailyClose.market == MARKET,
                    RadarDailyClose.mic == mic),
            legacy)
    return sa.or_(RadarDailyClose.market == MARKET, legacy)


def record_closes(ticker, closes, now, *, market='us', mic=None,
                  currency='USD', source='legacy', price_basis='close',
                  adjustment_basis=None, is_shadow=False, commit=True):
    """Upsert (date, close) pairs for one ticker. Returns rows written.

    Upsert rather than append: providers restate recent bars. Overwrites
    obey CLOSE_SOURCE_PRIORITY -- an existing row survives a lower-priority
    write, equal priority is provider restatement, and a migration-era NULL
    source reads as ``legacy``. The upsert identity includes ``is_shadow``:
    the shadow lane can never overwrite or block the live row for one date.

    Only US dollar closes are written; the archived non-US lane has no writer.
    """
    from .prices import validate_close_source
    if market != MARKET or currency != CURRENCY:
        raise ValueError(
            f'only US USD closes are stored, not {market}/{currency}')
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
            values = dict(
                ticker=ticker, market=market, mic=mic, currency=currency,
                close_date=day, close=close, fetched_at=now,
                source=source, price_basis=price_basis,
                adjustment_basis=adjustment_basis, is_shadow=is_shadow)
            if db.session.get_bind().dialect.name == 'mysql':
                # The daemon and a one-time backfill may both observe an
                # absent row before either writes it. Make that final write
                # atomic so the loser reconciles instead of raising 1062.
                from sqlalchemy.dialects.mysql import insert as mysql_insert
                table = RadarDailyClose.__table__
                insert = mysql_insert(table).values(**values)
                eligible_sources = [
                    candidate for candidate, priority
                    in CLOSE_SOURCE_PRIORITY.items()
                    if priority <= incoming_priority]
                replace = sa.or_(table.c.source.is_(None),
                                 table.c.source.in_(eligible_sources))
                assignments = {
                    name: sa.case(
                        (replace, getattr(insert.inserted, name)),
                        else_=getattr(table.c, name))
                    for name in ('close', 'fetched_at', 'currency', 'source',
                                 'price_basis', 'adjustment_basis')
                }
                db.session.execute(
                    insert.on_duplicate_key_update(**assignments))
            else:
                db.session.add(RadarDailyClose(**values))
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
    different questions: a listing's exact-ISIN sibling on another US venue
    may hold the deeper series.

    `currency` is the currency `closes` is expressed in, which the axis and
    the hover read. It is always the US dollar: nothing is ever converted.
    """
    closes: tuple
    market: str | None
    mic: str | None
    venue: str | None
    currency: str | None


EMPTY_BASIS = HistoryBasis(closes=(), market=None, mic=None, venue=None,
                           currency=None)


def _native_basis(ticker, quote, days, today):
    rows = closes_for([ticker], days=days, today=today,
                      market=quote.market, mic=quote.mic).get(ticker, [])
    return HistoryBasis(closes=tuple(rows), market=quote.market,
                        mic=quote.mic, venue=quote.venue,
                        currency=quote.currency)


def _sibling_basis(ticker, quote, days, today):
    """Another US venue, when it is provably the same paper.

    Same ISIN, both non-null, same currency: a question about which series may
    stand in for which, and never about how to stitch them.
    """
    from models import RadarInstrument
    rows = RadarInstrument.query.filter_by(
        ticker=ticker, market=MARKET).all()
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
                        currency=sibling.currency)


def resolve_basis(ticker, quote, days, today):
    """The chartable US series for one ticker over `days`, and its venue.

    Candidates in precedence order -- the quote's own venue, then the
    ISIN-matched US sibling -- and the one with the MOST closes in the span
    wins. `max` keeps the first of equal counts, so precedence breaks ties.
    Evaluated per span on purpose: each span should draw the most price it
    can while saying which venue that was. A quote from any other market is a
    caller bug; archived non-US closes are never a candidate.

    Fewer than MIN_BASIS_CLOSES is not a candidate at all. When nothing
    qualifies the caller gets EMPTY_BASIS and the panel says so, which is the
    honest answer and the one the renderer already draws.
    """
    _require_us(quote.market)
    first_visible = today - dt.timedelta(days=max(days - 1, 0))
    candidates = [_native_basis(ticker, quote, days, today),
                  _sibling_basis(ticker, quote, days, today)]
    # closes_for intentionally includes `today-days` for other callers. A
    # chart of N calendar days starts at today-(N-1), so choose the basis from
    # the points the reader can actually see rather than an extra boundary row.
    candidates = [
        (dataclasses.replace(
            candidate,
            closes=tuple((day, close) for day, close in candidate.closes
                         if first_visible <= day <= today))
         if candidate is not None else None)
        for candidate in candidates]
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

    Returns ``(stored, empty)``. A provider answering nothing leaves the
    stored rows alone: blanking a year of history because one call failed
    would empty the column for that ticker until the next cycle, which is
    worse than showing yesterday's.
    """
    stored = 0
    empty = 0
    provider_symbols = provider_symbols or {}
    for ticker in tickers:
        symbol = provider_symbols.get(ticker, ticker)
        if mic is None:
            closes = provider.daily_closes(symbol, HISTORY_DAYS)
        else:
            closes = provider.daily_closes(symbol, HISTORY_DAYS, mic_code=mic)
        if not closes:
            # Counted, not swallowed. A provider that refuses an identity --
            # Yahoo rejects any MIC outside its allowlist before it looks at
            # a single bar -- otherwise reports a successful cycle that
            # stored nothing.
            empty += 1
            continue
        record_closes(ticker, closes, now, market=market, mic=mic,
                      currency=currency,
                      source=getattr(provider, 'source', 'legacy'),
                      adjustment_basis=(
                          'split' if getattr(provider, 'source', None)
                          in ('yahoo_chart', 'massive_grouped',
                              'twelvedata') else None))
        stored += 1
    return stored, empty
