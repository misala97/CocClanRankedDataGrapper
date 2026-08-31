# personal_apps/features/radar/journal.py
"""Read and write radar_mention_events. The only module that knows it exists.

The journal answers one question for roll_up: what is EVERYTHING that landed in
this ticker's quarter-hour, regardless of which cycle carried it. Nothing else
in the pipeline reads it, and nothing reads it after retention drops the row --
the bucket is the durable artifact.
"""
import collections
import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as mysql_insert

from extensions import db
from models import RadarMention, RadarMentionEvent, RadarPost

# Imported as a module, not `from .buckets import MentionRow, bucket_start_for`
# -- a name import needs those names bound in buckets' namespace by the time
# THIS line runs, which fails whenever buckets is the module still mid-import
# (it imports journal at its own top). Importing the module and reaching
# `buckets.MentionRow` / `buckets.bucket_start_for` only inside the functions
# below defers that lookup to call time, when both modules are always fully
# loaded, so it works regardless of which one a caller imports first.
from . import buckets
# Safe as a name import: config imports nothing from this package, so it is
# never the module mid-import. Only `buckets` is in the cycle.
from .config import MENTION_EVENT_RETENTION_HOURS, expand_sources_for_history

# Rows per INSERT. Large enough that a busy Bluesky cycle is a handful of
# statements, small enough to stay well inside max_allowed_packet.
_CHUNK = 500


def record(rows):
    """Store this cycle's mentions. Idempotent on (source, external_id, ticker).

    Only `engagement` is updated on a duplicate. Everything else was decided at
    first sight and must stay decided: re-deciding confidence on a later cycle
    would let a config change rewrite a bucket that was already counted, which
    is the hazard ingest's docstring has always warned about. Engagement takes
    the latest reported value instead -- last-write-wins, not a running
    maximum: verified this rewrites a stored 10.0 to 99.0, and the same UPDATE
    runs downward just as readily if a later cycle reports a smaller
    `score + num_comments` (a downvote, a deleted comment, moderation). That is
    the right direction to fail in, not a gap -- the bucket this feeds is
    itself rebuilt from scratch every pass to reflect what is true NOW rather
    than accumulate, and a GREATEST-style ratchet would freeze engagement at
    its historical peak instead, which is its own kind of stale count.
    """
    if not rows:
        return

    payload = [{
        'source': row.source,
        'external_id': row.external_id,
        'ticker': row.ticker,
        'channel': row.channel,
        'created_utc': row.created_utc,
        'bucket_start': buckets.bucket_start_for(row.created_utc),
        'author': row.author,
        'simhash': row.simhash,
        'confidence': row.confidence,
        'sentiment': row.sentiment,
        'engagement': row.engagement,
    } for row in rows]

    for start in range(0, len(payload), _CHUNK):
        statement = mysql_insert(RadarMentionEvent).values(payload[start:start + _CHUNK])
        db.session.execute(statement.on_duplicate_key_update(
            engagement=statement.inserted.engagement))
    db.session.commit()


def bootstrap_from_mentions(since):
    """Recover retained extractor decisions before the first journal rollup.

    The journal table is empty immediately after migration (Task 1), so an
    already-open quarter-hour rebuilt from the first post-deploy cursor slice
    alone would repeat the exact overwrite this whole generation exists to
    fix. radar_posts x radar_mentions is the only place the pre-migration
    decision still lives -- 30-day retention on posts outlasts the journal's
    48 hours -- so this replays it back through the same `record()` path a
    live cycle uses.

    Idempotent through record()'s unique key on (source, external_id,
    ticker): safe to call on every startup, not just the first one after a
    migration.

    `medium` is deliberately absent from the recovered confidence: the
    extractor only ever stored high/low, and promotion is recomputed from the
    full bucket at rollup, never invented here. A low-only post was never
    retained at all -- Bluesky alone would be 100 million rows a month of
    text nothing reads -- and stays honestly unrecoverable.
    """
    rows = (db.session.query(
                RadarMention.ticker, RadarMention.confidence,
                RadarMention.lexicon_sentiment,
                RadarPost.source, RadarPost.external_id, RadarPost.channel,
                RadarPost.author, RadarPost.created_utc, RadarPost.simhash,
                RadarPost.score, RadarPost.num_comments)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarPost.created_utc >= since,
                    RadarMention.confidence.in_(('high', 'low')))
            .all())
    recovered = [buckets.MentionRow(
        ticker=ticker, external_id=external_id, created_utc=created_utc,
        source=source, channel=channel, author=author, simhash=int(simhash),
        confidence=confidence, sentiment=sentiment,
        engagement=float((score or 0) + (num_comments or 0)))
        for (ticker, confidence, sentiment, source, external_id, channel,
             author, created_utc, simhash, score, num_comments) in rows]
    record(recovered)

    # Replayed events default to NULL eligibility; mentions already carrying
    # a final v2 judgment know better. Re-derive the flag from the
    # materialized verdict so a bootstrap never resurrects a confirmed
    # non-chatter mention into the counts. Lazy import: llm_sentiment
    # imports this module inside its pass functions, and this is the
    # matching half of that cycle-avoidance.
    from . import llm_sentiment
    judged = (db.session.query(RadarMention, RadarPost)
              .join(RadarPost, RadarPost.id == RadarMention.post_id)
              .filter(RadarPost.created_utc >= since,
                      RadarMention.sentiment_judged_at.isnot(None)).all())
    pairs = [((post.source, post.external_id, mention.ticker),
              llm_sentiment.final_eligibility(mention))
             for mention, post in judged]
    if pairs:
        sync_chatter_eligibility(pairs)
        db.session.commit()
    return len(recovered)


def events_for(keys):
    """Every stored event in these (ticker, bucket_start) windows.

    Queried per bucket_start rather than per pair, because one cycle touches a
    handful of quarter-hours and hundreds of tickers -- an IN over the tickers
    inside each window uses the (ticker, bucket_start) index and takes one
    round trip per window instead of one per pair.
    """
    keys = list(keys)
    if not keys:
        return []

    by_window = collections.defaultdict(set)
    for ticker, start in keys:
        by_window[start].add(ticker)

    clauses = [sa.and_(RadarMentionEvent.bucket_start == start,
                       RadarMentionEvent.ticker.in_(list(tickers)))
               for start, tickers in by_window.items()]

    # Chatter eligibility (spec §7.2): a FINAL irrelevant/broadcast verdict
    # (False) removes the event from every rebuild; NULL (undecided) and
    # True both count. isnot(False), not is_(True) -- provisional rows must
    # keep counting.
    rows = (RadarMentionEvent.query.filter(sa.or_(*clauses))
            .filter(RadarMentionEvent.counts_as_human_chatter.isnot(False))
            .all())
    return [buckets.MentionRow(ticker=row.ticker, external_id=row.external_id,
                               created_utc=row.created_utc, source=row.source,
                               channel=row.channel, author=row.author,
                               simhash=row.simhash, confidence=row.confidence,
                               sentiment=row.sentiment, engagement=row.engagement)
            for row in rows]


def mark_promoted(rows):
    """Replace the promotion verdict for every recomputed bare mention.

    Promotion is not monotonic: one voucher may carry four bare mentions,
    then a fifth makes the entire group incredible and revokes all four.
    Reset every low/medium row in the recomputed windows before marking the
    current mediums true.
    """
    decisions = [(row.source, row.external_id, row.ticker,
                  row.confidence == 'medium')
                 for row in rows if row.confidence in ('low', 'medium')]
    if not decisions:
        return
    for start in range(0, len(decisions), _CHUNK):
        chunk = decisions[start:start + _CHUNK]
        clauses = [sa.and_(RadarMentionEvent.source == source,
                           RadarMentionEvent.external_id == external_id,
                           RadarMentionEvent.ticker == ticker)
                   for source, external_id, ticker, _ in chunk]
        (RadarMentionEvent.query.filter(sa.or_(*clauses))
         .update({'promoted': False}, synchronize_session=False))

        promoted = [(source, external_id, ticker)
                    for source, external_id, ticker, value in chunk if value]
        if promoted:
            promoted_clauses = [sa.and_(RadarMentionEvent.source == source,
                                        RadarMentionEvent.external_id == external_id,
                                        RadarMentionEvent.ticker == ticker)
                                for source, external_id, ticker in promoted]
            (RadarMentionEvent.query.filter(sa.or_(*promoted_clauses))
             .update({'promoted': True}, synchronize_session=False))
    db.session.commit()


def sync_chatter_eligibility(pairs):
    """Set each event's chatter flag to the mention's FINAL eligibility.

    pairs: iterable of ((source, external_id, ticker), True | False | None).
    False excludes, True counts (an explicit decision -- a Sonnet reversal
    lands here and RESTORES counting), None returns a mention to
    provisional. Returns only windows whose stored value actually CHANGED,
    so unchanged re-syncs rebuild nothing.

    No commit of its own: runs inside the caller's judgment transaction,
    so the mention's materialized verdict and the journal's flag can never
    disagree across a crash.
    """
    pairs = list(pairs)
    changed = set()
    for start in range(0, len(pairs), _CHUNK):
        chunk = pairs[start:start + _CHUNK]
        by_identity = {identity: value for identity, value in chunk}
        clauses = [sa.and_(RadarMentionEvent.source == source,
                           RadarMentionEvent.external_id == external_id,
                           RadarMentionEvent.ticker == ticker)
                   for source, external_id, ticker in by_identity]
        for row in RadarMentionEvent.query.filter(sa.or_(*clauses)).all():
            value = by_identity[(row.source, row.external_id, row.ticker)]
            if row.counts_as_human_chatter is not value:
                row.counts_as_human_chatter = value
                changed.add((row.ticker, row.bucket_start))
    return changed


def recent_decided_windows(now, minutes=30):
    """Windows holding a recently DECIDED flag -- the durable retry net.

    A crash between the judgment commit and the bucket rebuild loses only
    that rebuild; the next pass re-collects these windows and rebuilds
    idempotently. Bounded by event recency so it stays one indexed read.
    """
    since = now - dt.timedelta(minutes=minutes)
    rows = (db.session.query(RadarMentionEvent.ticker,
                             RadarMentionEvent.bucket_start)
            .filter(RadarMentionEvent.counts_as_human_chatter.isnot(None),
                    RadarMentionEvent.created_utc >= since)
            .distinct().all())
    return {(ticker, start) for ticker, start in rows}


def rebuild_windows(windows, now=None):
    """Recompute the buckets behind these windows from the filtered journal.

    Refuses windows older than the journal horizon: their events are
    pruned, and bootstrap_from_mentions cannot restore low-confidence-only
    posts (never stored as mentions), so a rebuild there would silently
    collapse low_count -- corrupting forever-retained history to fix its
    tone eligibility. Documented deviation from a literal spec §9 step 7.
    """
    now = now or dt.datetime.utcnow()
    horizon = now - dt.timedelta(hours=MENTION_EVENT_RETENTION_HOURS)
    inside = [(ticker, start) for ticker, start in windows if start >= horizon]
    if not inside:
        return 0
    return buckets.rebuild_windows(inside)


def distinct_voices(tickers, sources, since, now, field):
    """Distinct authors or channels per ticker over the SCORED mentions.

    `field` is 'author' or 'channel'. Counted here rather than from
    radar_mentions because that table never holds `medium` -- promotion happens
    at rollup and is written back onto the journal, not onto the mention -- and
    because a post whose tickers were all `low` has no mention row at all.

    Buckets store distinct_authors as a COUNT, so aggregating them can only
    take a maximum, and a maximum systematically undercounts: two buckets
    holding {x, y} and {z, w} have four distinct voices and report two.
    Measured on live data, NVDA showed 26 real authors against a bucket
    maximum of 2.
    """
    if not tickers:
        return {}

    # A raw count of distinct people, with no baseline behind it, so the
    # pre-split root `reddit` events count towards it -- they are the same
    # readers on the same platform, and dropping them would undercount
    # breadth for every ticker discussed before the split.
    sources = expand_sources_for_history(sources)
    column = {'author': RadarMentionEvent.author,
              'channel': RadarMentionEvent.channel}[field]
    rows = (db.session.query(RadarMentionEvent.ticker,
                             sa.func.count(sa.distinct(column)))
            .filter(RadarMentionEvent.ticker.in_(list(tickers)),
                    RadarMentionEvent.source.in_(list(sources)),
                    RadarMentionEvent.created_utc >= since,
                    RadarMentionEvent.created_utc < now,
                    sa.or_(RadarMentionEvent.confidence == 'high',
                           RadarMentionEvent.promoted.is_(True)),
                    # A confirmed non-chatter voice is not a voice (spec
                    # §7.2); NULL/True keep counting.
                    RadarMentionEvent.counts_as_human_chatter.isnot(False))
            .group_by(RadarMentionEvent.ticker).all())
    # int() at the boundary: COUNT is Decimal on MySQL and MariaDB alike.
    return {ticker: int(count) for ticker, count in rows}
