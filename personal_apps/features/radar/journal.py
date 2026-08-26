# personal_apps/features/radar/journal.py
"""Read and write radar_mention_events. The only module that knows it exists.

The journal answers one question for roll_up: what is EVERYTHING that landed in
this ticker's quarter-hour, regardless of which cycle carried it. Nothing else
in the pipeline reads it, and nothing reads it after retention drops the row --
the bucket is the durable artifact.
"""
import collections

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as mysql_insert

from extensions import db
from models import RadarMentionEvent

# Imported as a module, not `from .buckets import MentionRow, bucket_start_for`
# -- a name import needs those names bound in buckets' namespace by the time
# THIS line runs, which fails whenever buckets is the module still mid-import
# (it imports journal at its own top). Importing the module and reaching
# `buckets.MentionRow` / `buckets.bucket_start_for` only inside the functions
# below defers that lookup to call time, when both modules are always fully
# loaded, so it works regardless of which one a caller imports first.
from . import buckets

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

    rows = RadarMentionEvent.query.filter(sa.or_(*clauses)).all()
    return [buckets.MentionRow(ticker=row.ticker, external_id=row.external_id,
                               created_utc=row.created_utc, source=row.source,
                               channel=row.channel, author=row.author,
                               simhash=row.simhash, confidence=row.confidence,
                               sentiment=row.sentiment, engagement=row.engagement)
            for row in rows]
