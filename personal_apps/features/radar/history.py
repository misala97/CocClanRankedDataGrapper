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


@dataclasses.dataclass(frozen=True)
class HistorySeries:
    """One identity's composed daily series plus its provenance seam."""
    closes: tuple
    history_proxy: bool
    proxy_mic: str | None
    proxy_venue: str | None
    native_mic: str | None
    native_venue: str | None
    native_from: dt.date | None


def series_for(ticker, market, mic, days, today):
    """The chartable series for one exact identity, with one honest seam.

    For a Tradegate-primary instrument, verified Xetra closes may fill the
    OLDER portion only -- exact same ISIN, EUR, and strictly before the
    first native Tradegate date. From that date on, missing Tradegate days
    stay missing rather than being silently patched (spec §8.2). Every
    other identity returns its native rows with no proxy.
    """
    native = tuple(closes_for([ticker], days=days, today=today,
                              market=market, mic=mic).get(ticker, []))
    if market != 'de' or mic != 'XGAT':
        return HistorySeries(closes=native, history_proxy=False,
                             proxy_mic=None, proxy_venue=None,
                             native_mic=mic, native_venue=None,
                             native_from=None)

    from models import RadarInstrument
    rows = {row.mic: row for row in RadarInstrument.query.filter_by(
        ticker=ticker, market='de').all()}
    xgat = rows.get('XGAT')
    xetr = rows.get('XETR')
    proxy_allowed = (
        xgat is not None and xetr is not None and
        xgat.isin is not None and xgat.isin == xetr.isin and
        xgat.currency == 'EUR' and xetr.currency == 'EUR')
    if not proxy_allowed:
        return HistorySeries(closes=native, history_proxy=False,
                             proxy_mic=None, proxy_venue=None,
                             native_mic='XGAT', native_venue='Tradegate BSX',
                             native_from=None)

    xetra = closes_for([ticker], days=days, today=today,
                       market='de', mic='XETR').get(ticker, [])
    native_by_day = dict(native)
    native_from = min(native_by_day) if native_by_day else None
    proxy = {day: close for day, close in xetra
             if native_from is None or day < native_from}
    combined = {**proxy, **native_by_day}
    return HistorySeries(
        closes=tuple(sorted(combined.items())),
        history_proxy=bool(proxy),
        proxy_mic='XETR' if proxy else None,
        proxy_venue='Xetra' if proxy else None,
        native_mic='XGAT', native_venue='Tradegate BSX',
        native_from=native_from)


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
