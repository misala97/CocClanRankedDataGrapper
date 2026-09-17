"""Rolling deletion of raw text and of stale US price snapshots and closes.

Buckets are never touched here. They are the queryable layer and are retained
forever; raw posts exist only long enough to be extracted from and read on a
detail page (spec 5).

Archived rows of the retired non-US market -- quotes, closes, trade events,
collection cycles, cursors, mapping generations and reference rates -- are
historical evidence. No query here selects, ranks or deletes one: every price
retention query is scoped to US and legacy-US (NULL market) rows before it
decides anything.
"""
import datetime as dt
import time

import sqlalchemy as sa

from extensions import db
from models import RadarMentionEvent, RadarPost, RadarQuote

from .config import (MENTION_EVENT_RETENTION_HOURS, POST_RETENTION_DAYS,
                     QUOTE_RETENTION_DAYS, STALE_QUOTE_POLLS)

# Breathing room between chunks so the daemon's next cycle is not queued behind
# a long delete on the same connection.
_CHUNK_PAUSE_SECONDS = 0.05


def _pinned(cutoff):
    """The cutoff an armed trial allows, which is never later than its own.

    A trial pins the evidence its recovery would need: the journal keeps 48
    hours and posts 30 days, and both of those forget faster than anyone
    decides to stop a trial. While one is armed, running or recovering,
    pruning stops at the EARLIER of the ordinary horizon and the trial's
    floor -- so the ordinary rules still apply to everything the trial does
    not need.

    A trial that merely PASSED its audit still pins: passing authorises
    continuing, and continuing still has to be undoable. Only a completed
    recovery releases the floor, because only then has the evidence been
    used.

    A failure to READ the state aborts the prune rather than bypassing the
    pin. Deleting evidence because a query failed is the one outcome this
    cannot risk.
    """
    from . import judge_trial
    floor = judge_trial.retention_floor()
    if floor is None:
        return cutoff
    return min(cutoff, floor)


def prune_closes(now, chunk_size=5000):
    """Bound the US daily-close store: the calendar horizon, then the
    evidence-armed Massive shadow cleanup. Returns rows deleted."""
    deleted = _prune_daily_closes(now, chunk_size)
    deleted += _prune_massive_shadow(now, chunk_size)
    return deleted


def _close_horizon_days():
    # CALENDAR days at least as deep as the widest chart span, plus buffer.
    # HISTORY_DAYS counts TRADING days and must never be a calendar horizon:
    # using it would repeatedly delete the deepest ~nine months of every 3Y
    # chart [A1].
    from .detail import SPAN_DAYS
    return max(SPAN_DAYS.values()) + 90


def _prune_daily_closes(now, chunk_size):
    """[A1] Universe-wide grouped ingestion is bounded only if pruned.

    US and legacy-US (NULL market) rows only; archived non-US closes are
    never candidates.
    """
    from models import RadarDailyClose

    horizon = (now.date() if isinstance(now, dt.datetime) else now) \
        - dt.timedelta(days=_close_horizon_days())
    deleted = 0
    while True:
        batch = [row_id for (row_id,) in
                 db.session.query(RadarDailyClose.id)
                 .filter(RadarDailyClose.close_date < horizon,
                         sa.or_(RadarDailyClose.market == 'us',
                                RadarDailyClose.market.is_(None)))
                 .limit(chunk_size).all()]
        if not batch:
            break
        RadarDailyClose.query.filter(
            RadarDailyClose.id.in_(batch)).delete(synchronize_session=False)
        db.session.commit()
        deleted += len(batch)
        if len(batch) < chunk_size:
            break
    return deleted


def _massive_cleanup_evidence(now):
    """The three validated settings that arm shadow cleanup, or None.

    Enforceable configuration, not a log-reading convention: absent or
    malformed evidence DISABLES cleanup (spec §9.2). All three must
    validate -- a UTC activation instant at least seven days old and two
    exact lowercase SHA-256 digests.
    """
    import os
    import re
    activated_raw = os.getenv('RADAR_US_CLOSE_ACTIVATED_AT')
    report_sha = os.getenv('RADAR_US_CLOSE_GATE_REPORT_SHA256')
    audit_sha = os.getenv('RADAR_US_CLOSE_GATE_AUDIT_SHA256')
    if not (activated_raw and report_sha and audit_sha):
        return None
    sha_re = re.compile(r'^[0-9a-f]{64}$')
    if not sha_re.match(report_sha) or not sha_re.match(audit_sha):
        return None
    try:
        activated = dt.datetime.fromisoformat(
            activated_raw.replace('Z', '+00:00'))
    except ValueError:
        return None
    if activated.tzinfo is not None:
        activated = activated.astimezone(dt.timezone.utc).replace(tzinfo=None)
    reference = now if isinstance(now, dt.datetime) else dt.datetime.combine(
        now, dt.time())
    if reference - activated < dt.timedelta(days=7):
        return None
    return activated


def _prune_massive_shadow(now, chunk_size):
    """[A1] Bounded shadow cleanup, armed only by recorded gate evidence.

    Retains the complete shadow lane through the gate and seven days past
    activation; then prunes only ``massive_grouped`` SHADOW closes older
    than 30 calendar days. Live rows and archived non-US closes are never
    touched here.
    """
    from models import RadarDailyClose

    if _massive_cleanup_evidence(now) is None:
        return 0
    horizon = (now.date() if isinstance(now, dt.datetime) else now) \
        - dt.timedelta(days=30)
    deleted = 0
    while True:
        batch = [row_id for (row_id,) in
                 db.session.query(RadarDailyClose.id)
                 .filter(RadarDailyClose.is_shadow.is_(True),
                         RadarDailyClose.source == 'massive_grouped',
                         RadarDailyClose.close_date < horizon)
                 .limit(chunk_size).all()]
        if not batch:
            break
        RadarDailyClose.query.filter(
            RadarDailyClose.id.in_(batch)).delete(synchronize_session=False)
        db.session.commit()
        deleted += len(batch)
        if len(batch) < chunk_size:
            break
    return deleted


def prune_posts(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS):
    """Delete posts older than the retention window, in chunks.

    Mentions follow via ON DELETE CASCADE. Returns the number deleted.
    """
    from . import judge_trial
    horizon = now - dt.timedelta(days=POST_RETENTION_DAYS)
    total = 0

    while True:
        # The floor is re-read inside the lock on EVERY chunk. Arming takes
        # the same lock, so a trial that begins halfway through a long prune
        # cannot have its evidence deleted by a cutoff computed before it
        # existed.
        with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK):
            cutoff = _pinned(horizon)
            ids = [
                row_id for (row_id,) in
                db.session.query(RadarPost.id)
                .filter(RadarPost.created_utc < cutoff)
                .order_by(RadarPost.created_utc)
                .limit(chunk_size).all()
            ]
            if not ids:
                break

            db.session.query(RadarPost).filter(RadarPost.id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()
        total += len(ids)

        if len(ids) < chunk_size:
            break
        if pause:
            time.sleep(pause)

    return total


def prune_quotes(now, keep=STALE_QUOTE_POLLS, chunk_size=5000,
                 pause=_CHUNK_PAUSE_SECONDS):
    """Delete price snapshots past the window, in chunks. Returns the count.

    Not a plain age filter, and that is the whole difficulty. `price_status`
    decides from a ticker's most recent `keep` snapshots WHENEVER THEY WERE
    TAKEN -- quotes are only fetched for tickers the board is watching, so a
    name that went quiet weeks ago still has three real snapshots and still
    answers 'ok' or 'stale'. Deleting them by age alone would turn it
    'unknown', which asserts the board never quoted it: a statement about the
    stock rather than about our polling, and exactly the collapse those four
    statuses exist to prevent.

    So the rank is computed over ALL of a ticker's rows and the age filter is
    applied after it. Ranking only the old rows would protect the newest three
    OF THE OLD ONES, which is a different set and the wrong one -- a busy
    ticker would keep three ancient snapshots it has no use for while the rule
    that needed them was already satisfied by newer rows.

    Deletable ids are collected in one pass rather than re-ranked per chunk:
    the window function would otherwise sort the whole table once per chunk,
    and this runs nightly against a table nothing else is reading at 04:30.

    Only US and legacy-US rows are ranked at all: the market filter sits
    inside the ranked subquery, so an archived non-US row is never a
    candidate rather than a candidate filtered out afterwards.
    """
    cutoff = now - dt.timedelta(days=QUOTE_RETENTION_DAYS)

    ranked = _ranked_quotes()

    doomed = [row_id for (row_id,) in db.session.execute(
        sa.select(ranked.c.id)
        .where(ranked.c.rn > keep, ranked.c.fetched_at < cutoff))]

    total = 0
    for start in range(0, len(doomed), chunk_size):
        batch = doomed[start:start + chunk_size]
        db.session.query(RadarQuote).filter(RadarQuote.id.in_(batch)).delete(
            synchronize_session=False)
        db.session.commit()
        total += len(batch)
        if pause and start + chunk_size < len(doomed):
            time.sleep(pause)

    return total


def _ranked_quotes():
    """Every US and legacy-US snapshot with its newest-first rank per
    (ticker, market, mic)."""
    return sa.select(
        RadarQuote.id.label('id'),
        RadarQuote.fetched_at.label('fetched_at'),
        sa.func.row_number().over(
            partition_by=(RadarQuote.ticker, RadarQuote.market, RadarQuote.mic),
            order_by=RadarQuote.fetched_at.desc()).label('rn'),
    ).where(sa.or_(RadarQuote.market == 'us',
                   RadarQuote.market.is_(None))).subquery()


def prune_mention_events(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS):
    """Delete journal rows whose bucket can no longer be rewritten.

    By created_utc rather than by insertion time. A catch-up after an outage
    ingests posts hours old, and what decides is when the POST was written --
    once its quarter-hour is past the window, no cycle will touch that bucket
    again and the events behind it have nothing left to answer.

    Returns the number deleted.
    """
    from . import judge_trial
    horizon = now - dt.timedelta(hours=MENTION_EVENT_RETENTION_HOURS)
    total = 0

    while True:
        # Same discipline as prune_posts, and this is where the pin bites
        # first: the journal horizon is 48 hours, so without it the windows
        # a trial would have to rebuild are gone within two days.
        with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK):
            cutoff = _pinned(horizon)
            ids = [
                row_id for (row_id,) in
                db.session.query(RadarMentionEvent.id)
                .filter(RadarMentionEvent.created_utc < cutoff)
                .order_by(RadarMentionEvent.created_utc)
                .limit(chunk_size).all()
            ]
            if not ids:
                break

            db.session.query(RadarMentionEvent).filter(
                RadarMentionEvent.id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()
        total += len(ids)

        if len(ids) < chunk_size:
            break
        if pause:
            time.sleep(pause)

    return total
