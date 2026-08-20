"""One ingest cycle: fetch, store, extract, roll up.

The fetcher is injected rather than imported so the whole pipeline is testable
without a network, which spec 10 requires. run_radar_ingest.py supplies the
real one.
"""
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarMention, RadarPost, RadarSourceCursor

from . import buckets, extraction, fingerprint, sentiment, universe
from .config import BUCKET_MINUTES

# How far back a cycle rolls up when there is no stored history yet.
_COLD_START_WINDOW = dt.timedelta(hours=2)


def _since_for(source):
    """How far this source has been read.

    Explicit cursor state, not max(radar_posts.created_utc). Posts mentioning
    no ticker are never stored -- Bluesky alone would otherwise be 100 million
    rows a month of text nothing reads -- so inferring the cursor from stored
    rows would rewind it to the last post that happened to mention something
    and refetch everything since, every cycle, forever.
    """
    row = RadarSourceCursor.query.filter_by(source=source).one_or_none()
    if row is not None:
        return row.cursor_utc
    return dt.datetime.utcnow() - _COLD_START_WINDOW


def _advance_cursor(source, newest_seen):
    """Move a source's cursor to the newest post it returned.

    Advanced from what was SEEN, not what was KEPT. A cycle full of posts that
    mention nothing still made progress.
    """
    if newest_seen is None:
        return
    row = RadarSourceCursor.query.filter_by(source=source).one_or_none()
    if row is None:
        row = RadarSourceCursor(source=source, cursor_utc=newest_seen)
        db.session.add(row)
    elif newest_seen > row.cursor_utc:
        row.cursor_utc = newest_seen


def _store_mentioning_posts(raw_posts, lookup, now):
    """Store only posts that mention a ticker, and their mentions.

    Extraction runs before storage rather than after, which is what keeps the
    firehose affordable: at 144k posts/hour, storing everything and extracting
    later would be 100 million rows a month to find roughly 250 thousand that
    matter.

    Extraction still runs once per post -- an already-stored post is refreshed
    for engagement but never re-extracted, so a stopword or universe change
    cannot silently rewrite history under a bucket that was already counted.
    """
    if not raw_posts:
        return [], 0

    # Whether to STORE a new post depends on extraction. Whether to REFRESH an
    # already-stored one does not: a post deleted upstream comes back with an
    # empty body, extracts nothing, and would never have its stored text
    # blanked if the two decisions were the same decision.
    existing = {}
    ids = [raw.external_id for raw in raw_posts]
    for start in range(0, len(ids), 1000):
        chunk = ids[start:start + 1000]
        for row in RadarPost.query.filter(RadarPost.external_id.in_(chunk)).all():
            existing[row.external_id] = row

    fresh, new_count = [], 0
    for raw in raw_posts:
        row = existing.get(raw.external_id)
        tickers = extraction.extract_tickers(raw.title, raw.body, lookup)

        if row is None:
            # New, and only worth keeping if it mentions something. At 144k
            # posts/hour, storing the rest would be 100 million rows a month
            # of text nothing reads.
            if not tickers:
                continue
            row = RadarPost(source=raw.source, external_id=raw.external_id,
                            channel=raw.channel, created_utc=raw.created_utc,
                            first_seen=now)
            db.session.add(row)
            new_count += 1
            fresh.append((raw, row, tickers))

        # Engagement grows after first sight, so these always refresh.
        row.score = raw.score
        row.num_comments = raw.num_comments
        row.last_seen = now
        row.url = raw.url
        # Text and author are overwritten unconditionally, which is what makes
        # an upstream deletion propagate: the blanked body replaces the stored
        # one while the mention rows and bucket counts stay.
        row.title = raw.title
        row.body = raw.body
        row.author = raw.author
        row.simhash = fingerprint.simhash64('%s %s' % (raw.title or '', raw.body))

    db.session.flush()

    mention_rows = []
    for raw, row, tickers in fresh:
        score = sentiment.lexicon_score('%s %s' % (raw.title or '', raw.body))
        for symbol, confidence in tickers:
            db.session.add(RadarMention(post_id=row.id, ticker=symbol,
                                        confidence=confidence,
                                        lexicon_sentiment=score))
            mention_rows.append(buckets.MentionRow(
                ticker=symbol, created_utc=raw.created_utc, source=raw.source,
                author=raw.author, simhash=row.simhash, confidence=confidence,
                sentiment=score,
                engagement=float(raw.score + raw.num_comments)))

    return mention_rows, new_count


def _touched_buckets(mention_rows, since, now):
    """Every bucket this cycle covered, including ones with no mentions.

    Derived from the cycle's time span rather than from the rows, so a healthy
    source that simply saw nothing records a genuine zero -- which is a
    different fact from `missing` and must stay distinguishable.
    """
    windows = set()
    cursor = buckets.bucket_start_for(since)
    end = buckets.bucket_start_for(now)
    while cursor <= end:
        windows.add(cursor)
        cursor += dt.timedelta(minutes=BUCKET_MINUTES)
    for row in mention_rows:
        windows.add(buckets.bucket_start_for(row.created_utc))
    return windows


def run_cycle(now, fetchers):
    """Fetch every source, store what mentions something, roll up once.

    `fetchers` maps source name to a callable taking `since`. The set is open;
    nothing here knows which sources exist.
    """
    lookup = universe.load_lookup()
    statuses, depths = {}, {}
    all_mentions = []
    touched = set()
    posts_seen = posts_new = 0

    for source, fetcher in fetchers.items():
        since = _since_for(source)
        result = fetcher(since)
        statuses[source] = result.status
        depths[source] = result.catchup_depth

        if result.status == 'missing':
            continue

        posts_seen += len(result.posts)

        # A source that could not reach as far back as it was asked did not
        # cover the earlier part of the window, and must not have buckets
        # written as though it had.
        effective_since = result.covered_since or since
        touched |= _touched_buckets([], effective_since, now)

        mention_rows, new_count = _store_mentioning_posts(result.posts, lookup, now)
        posts_new += new_count
        all_mentions.extend(mention_rows)

        if result.posts:
            _advance_cursor(source, max(p.created_utc for p in result.posts))

    db.session.commit()

    for row in all_mentions:
        touched.add(buckets.bucket_start_for(row.created_utc))

    written = buckets.roll_up(all_mentions, statuses, touched)

    return {'posts_seen': posts_seen, 'posts_new': posts_new,
            'mentions': len(all_mentions), 'buckets_written': written,
            'per_source': statuses, 'catchup_depth': depths}
