# personal_apps/features/radar/scheduling.py
"""Per-symbol poll scheduling.

Sources that return a fixed page size regardless of timespan cannot be polled
on a fixed interval: the page is hours of history for a quiet symbol and
minutes for a busy one. Polling the quiet one often refetches the same data;
polling the busy one rarely loses data permanently. So the interval comes from
each symbol's own measured rate, which makes the schedule self-correcting -- a
symbol that heats up is polled faster before anything is missed (spec 3.5).
"""
import datetime as dt

from extensions import db
from models import RadarPollState

# Messages a single call returns. Coverage is this divided by the rate.
PAGE_SIZE = 30

# Half the coverage window, so a rate estimate that is somewhat wrong still
# does not lose messages.
SAFETY_FACTOR = 0.5

MIN_INTERVAL = dt.timedelta(minutes=15)
MAX_INTERVAL = dt.timedelta(hours=4)


def interval_for_rate(rate, floor=None, ceiling=None, page_size=None):
    """How long until this symbol should be polled again.

    A rate of None means never measured -- poll soon and find out. A measured
    rate of zero means genuinely silent, so wait the maximum.

    The bounds are arguments because the defaults are StockTwits-shaped and a
    second source borrowed this scheduler. Reddit's feed holds 25 comments and
    r/wallstreetbets turns it over in under two minutes, so a fifteen-minute
    floor would mean never seeing most of it -- and unlike a symbol stream,
    what is missed is gone rather than merely late.
    """
    floor = floor or MIN_INTERVAL
    ceiling = ceiling or MAX_INTERVAL
    page = page_size or PAGE_SIZE

    if rate is None:
        return floor
    if rate <= 0:
        return ceiling

    coverage_hours = page / rate
    interval = dt.timedelta(hours=coverage_hours * SAFETY_FACTOR)
    return max(floor, min(ceiling, interval))


def ensure_tracked(source, symbols, now):
    """Add any symbols not yet tracked, due immediately. Returns how many."""
    existing = {
        row.symbol for row in
        RadarPollState.query.filter(RadarPollState.source == source,
                                    RadarPollState.symbol.in_(list(symbols))).all()
    } if symbols else set()

    added = 0
    for symbol in symbols:
        if symbol in existing:
            continue
        db.session.add(RadarPollState(source=source, symbol=symbol,
                                      next_due_at=now, observed_rate=None))
        added += 1
    db.session.commit()
    return added


def retire_untracked(source, symbols):
    """Drop poll state for symbols this source no longer tracks. Returns how many.

    ONLY for a source whose configured list is the complete set -- Reddit,
    where REDDIT_SUBS is exhaustive. StockTwits must never call this: its hot
    set is a rolling window, a ticker falling out of it is temporary, and
    deleting the row would throw away a real observed_rate that took hours to
    learn.

    Needed because due_symbols filters by SOURCE, not by the configured list.
    Without this, removing a subreddit leaves its row behind and the scheduler
    keeps handing it turns forever -- consuming exactly the request budget the
    removal was meant to free, and silently: the sub still appears in the
    logs, still costs feeds, and nothing looks wrong.
    """
    query = RadarPollState.query.filter(RadarPollState.source == source)
    if symbols:
        query = query.filter(RadarPollState.symbol.notin_(list(symbols)))
    retired = query.delete(synchronize_session=False)
    db.session.commit()
    return retired


def due_symbols(source, now, limit):
    """The most overdue symbols, up to the request budget.

    Ordered by how long they have been waiting, so a backlog larger than the
    budget rotates instead of starving the same symbols forever -- a symbol
    never polled is a permanent hole in its baseline.
    """
    rows = (RadarPollState.query
            .filter(RadarPollState.source == source,
                    RadarPollState.next_due_at <= now)
            .order_by(RadarPollState.next_due_at.asc())
            .limit(limit).all())
    return [row.symbol for row in rows]


def record_poll(source, symbol, now, rate, floor=None, ceiling=None,
                page_size=None):
    """Stamp a completed poll and schedule the next one from the new rate."""
    row = RadarPollState.query.filter_by(source=source, symbol=symbol).one_or_none()
    if row is None:
        row = RadarPollState(source=source, symbol=symbol)
        db.session.add(row)

    row.last_polled_at = now
    row.observed_rate = rate
    row.next_due_at = now + interval_for_rate(rate, floor, ceiling, page_size)
    db.session.commit()
