"""One ingest cycle: fetch, store, extract, roll up.

The fetcher is injected rather than imported so the whole pipeline is testable
without a network, which spec 10 requires. run_radar_ingest.py supplies the
real one.
"""
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarMention, RadarPost

from . import buckets, extraction, fingerprint, sentiment, universe
from .config import BUCKET_MINUTES

# How far back a cycle rolls up when there is no stored history yet.
_COLD_START_WINDOW = dt.timedelta(hours=2)


def _since_for(source):
    """The newest stored post for a source, or a cold-start window.

    Driven by stored data rather than by a clock, so a daemon restart or a
    missed cycle catches up instead of leaving a hole.
    """
    newest = db.session.query(sa.func.max(RadarPost.created_utc)).filter(
        RadarPost.source == source).scalar()
    return newest if newest is not None else dt.datetime.utcnow() - _COLD_START_WINDOW


def _store_posts(raw_posts, now):
    """Upsert posts. Returns {external_id: RadarPost} and a new-post count."""
    if not raw_posts:
        return {}, 0

    ids = [p.external_id for p in raw_posts]
    existing = {
        row.external_id: row
        for row in RadarPost.query.filter(RadarPost.external_id.in_(ids)).all()
    }

    stored = {}
    new_count = 0
    for raw in raw_posts:
        row = existing.get(raw.external_id)
        if row is None:
            row = RadarPost(source=raw.source, external_id=raw.external_id,
                            channel=raw.channel, created_utc=raw.created_utc,
                            first_seen=now)
            db.session.add(row)
            new_count += 1

        # Engagement grows after first sight, so these always refresh.
        row.score = raw.score
        row.num_comments = raw.num_comments
        row.last_seen = now
        row.url = raw.url

        # Text and author are only overwritten while they still exist
        # upstream; a deletion blanks them, and the mention rows stay.
        row.title = raw.title
        row.body = raw.body
        row.author = raw.author
        row.simhash = fingerprint.simhash64('%s %s' % (raw.title or '', raw.body))

        stored[raw.external_id] = row

    db.session.flush()
    return stored, new_count


def _extract_mentions(raw_posts, stored, lookup):
    """Create mention rows for posts that do not have them yet.

    Extraction runs once per post. Re-running it on every refetch would let a
    stopword or universe change silently rewrite history, and a bucket whose
    counts move under it is worse than one computed from a stale rule.
    """
    post_ids = [row.id for row in stored.values() if row.id is not None]
    already = set()
    if post_ids:
        already = {
            post_id for (post_id,) in
            db.session.query(RadarMention.post_id).filter(
                RadarMention.post_id.in_(post_ids)).distinct().all()
        }

    mention_rows = []
    for raw in raw_posts:
        row = stored.get(raw.external_id)
        if row is None or row.id in already:
            continue

        score = sentiment.lexicon_score('%s %s' % (raw.title or '', raw.body))
        for symbol, confidence in extraction.extract_tickers(
                raw.title, raw.body, lookup):
            db.session.add(RadarMention(post_id=row.id, ticker=symbol,
                                        confidence=confidence,
                                        lexicon_sentiment=score))
            mention_rows.append(buckets.MentionRow(
                ticker=symbol, created_utc=raw.created_utc, source=raw.source,
                author=raw.author, simhash=row.simhash, confidence=confidence,
                sentiment=score,
                engagement=float(raw.score + raw.num_comments)))

    return mention_rows


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


def run_cycle(now, fetcher, source='reddit'):
    """Fetch, store, extract and roll up once. Returns a summary dict."""
    since = _since_for(source)
    result = fetcher(since)

    statuses = {'reddit': 'missing', 'stocktwits': 'missing'}
    statuses[source] = result.status

    if result.status == 'missing':
        return {'posts_seen': 0, 'posts_new': 0, 'mentions': 0,
                'buckets_written': 0, 'status': 'missing',
                'catchup_depth': result.catchup_depth}

    lookup = universe.load_lookup()
    stored, new_count = _store_posts(result.posts, now)
    mention_rows = _extract_mentions(result.posts, stored, lookup)
    db.session.commit()

    written = buckets.roll_up(mention_rows, statuses,
                              _touched_buckets(mention_rows, since, now))

    return {'posts_seen': len(result.posts), 'posts_new': new_count,
            'mentions': len(mention_rows), 'buckets_written': written,
            'status': result.status, 'catchup_depth': result.catchup_depth}
