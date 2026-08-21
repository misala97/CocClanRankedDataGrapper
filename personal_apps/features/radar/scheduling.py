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


def interval_for_rate(rate):
    """How long until this symbol should be polled again.

    A rate of None means never measured -- poll soon and find out. A measured
    rate of zero means genuinely silent, so wait the maximum.
    """
    if rate is None:
        return MIN_INTERVAL
    if rate <= 0:
        return MAX_INTERVAL

    coverage_hours = PAGE_SIZE / rate
    interval = dt.timedelta(hours=coverage_hours * SAFETY_FACTOR)
    return max(MIN_INTERVAL, min(MAX_INTERVAL, interval))


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


def record_poll(source, symbol, now, rate):
    """Stamp a completed poll and schedule the next one from the new rate."""
    row = RadarPollState.query.filter_by(source=source, symbol=symbol).one_or_none()
    if row is None:
        row = RadarPollState(source=source, symbol=symbol)
        db.session.add(row)

    row.last_polled_at = now
    row.observed_rate = rate
    row.next_due_at = now + interval_for_rate(rate)
    db.session.commit()
