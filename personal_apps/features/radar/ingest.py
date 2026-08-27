"""One ingest cycle: fetch, store, extract, roll up.

The fetcher is injected rather than imported so the whole pipeline is testable
without a network, which spec 10 requires. run_radar_ingest.py supplies the
real one.
"""
import datetime as dt
import logging

import sqlalchemy as sa

from extensions import db
from models import RadarMention, RadarPost, RadarSourceCursor

from . import buckets, extraction, fingerprint, sentiment, universe
from .config import (
    BUCKET_MINUTES, bare_token_confidence, bare_tokens_allowed,
    coin_collision_dropped, looks_like_bot_feed,
    single_letter_cashtags_allowed)

logger = logging.getLogger('radar.ingest')

def _utcnow():
    """Naive UTC, the convention every datetime in this codebase is stored in.

    datetime.utcnow() is deprecated and slated for removal, and it printed a
    warning into the service log on every cycle.
    """
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

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
    return _utcnow() - _COLD_START_WINDOW


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


def _extract_for(raw, lookup):
    """Extract under the policy that applies to this post's source.

    Four per-source judgements, all about population rather than code:
    whether a bare token can be read as a ticker at all, what an
    uncorroborated one is WORTH, and whether a coin-shaped symbol means the
    company or the coin.
    """
    # An automated feed is one publisher however many tickers it names, and
    # it is not a person discussing anything. Dropped before extraction so the
    # whole post goes -- config.looks_like_bot_feed carries what counts and
    # why it matches the format's vocabulary rather than the symbols.
    if looks_like_bot_feed('%s %s' % (raw.title or '', raw.body or '')):
        return []

    tickers = extraction.extract_tickers(
        raw.title, raw.body, lookup,
        allow_bare=bare_tokens_allowed(raw.source),
        allow_single_letter=single_letter_cashtags_allowed(raw.source),
        bare_confidence=bare_token_confidence(raw.source))
    return [(symbol, confidence) for symbol, confidence in tickers
            if not coin_collision_dropped(raw.source, symbol)]


def _store_mentioning_posts(raw_posts, lookup, now):
    """Store only posts that mention a ticker, and their mentions.

    Extraction runs before storage rather than after, which is what keeps the
    firehose affordable: at 144k posts/hour, storing everything and extracting
    later would be 100 million rows a month to find roughly 250 thousand that
    matter.

    Extraction runs once per post per cycle, and the journal keeps the result:
    a post arriving again in a later cycle upserts its existing event rather
    than re-deciding it, so a stopword or universe change cannot rewrite
    history under a bucket that was already counted.
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
    extracted = {}
    for raw in raw_posts:
        row = existing.get(raw.external_id)
        # An external identity can appear twice in a source batch. The second
        # loop below needs the same decision, so cache it explicitly: a
        # setdefault default would call _extract_for eagerly for duplicates.
        if raw.external_id not in extracted:
            extracted[raw.external_id] = _extract_for(raw, lookup)
        tickers = extracted[raw.external_id]

        if row is None:
            # New, and only worth keeping if something scorable was found.
            #
            # `low` is an uncorroborated bare token -- ROM in "dinosaur fossils
            # at the ROM", and about 12000 an hour of its kind on the firehose.
            # Those are counted in the bucket but never scored, and there is no
            # reason to keep the text: it would be seven million rows a month
            # to store posts the leaderboard can never surface. Their mentions
            # still reach the rollup in memory, so counts and promotion are
            # unaffected.
            if not any(conf == 'high' for _, conf in tickers):
                continue
            row = RadarPost(source=raw.source, external_id=raw.external_id,
                            channel=raw.channel, created_utc=raw.created_utc,
                            first_seen=now)
            db.session.add(row)
            new_count += 1
            fresh.append((raw, row, tickers))
            # A message tagged with two tickers is returned by both symbol
            # streams, so the same external_id can arrive twice in one batch.
            # Without recording it here the second copy also looks new, and
            # both inserts hit the unique key.
            existing[raw.external_id] = row

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

    # Every extraction reaches the rollup, stored or not -- bucket counts and
    # corroboration are computed in memory from these rows.
    mention_rows = []
    fresh_ids = {raw.external_id for raw, _, _ in fresh}
    for raw in raw_posts:
        if raw.external_id in fresh_ids:
            continue
        tickers = extracted[raw.external_id]
        if not tickers:
            continue
        score = sentiment.lexicon_score('%s %s' % (raw.title or '', raw.body))
        for symbol, confidence in tickers:
            mention_rows.append(buckets.MentionRow(
                ticker=symbol, external_id=raw.external_id,
                created_utc=raw.created_utc, source=raw.source,
                channel=raw.channel,
                author=raw.author, simhash=fingerprint.simhash64(
                    '%s %s' % (raw.title or '', raw.body)),
                confidence=confidence, sentiment=score,
                engagement=float(raw.score + raw.num_comments)))

    for raw, row, tickers in fresh:
        score = sentiment.lexicon_score('%s %s' % (raw.title or '', raw.body))
        for symbol, confidence in tickers:
            db.session.add(RadarMention(post_id=row.id, ticker=symbol,
                                        confidence=confidence,
                                        lexicon_sentiment=score))
            mention_rows.append(buckets.MentionRow(
                ticker=symbol, external_id=raw.external_id,
                created_utc=raw.created_utc, source=raw.source,
                channel=raw.channel,
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
        try:
            result = fetcher(since)
        except Exception:
            # Isolated deliberately, and broadly. Each source declares an
            # exception type for "this fetch did not arrive", but a source can
            # also fail in ways it never anticipated -- a missing dependency
            # took down a whole cycle, StockTwits and 4chan included, because
            # ModuleNotFoundError is not JetstreamUnavailable. One source
            # failing must never cost the others their data (spec 4.5), and
            # `missing` is the honest record of it: no row, never a zero.
            logger.exception('radar source %s failed this cycle', source)
            statuses[source] = 'missing'
            # Not zero: no fetch arrived to measure a catch-up depth.
            depths[source] = None
            continue
        # A fetcher covering several source names reports each. Reddit does:
        # one cycle reads a slice of subreddits and each is its own source.
        # When those concrete statuses exist, the aggregate fetch verdict must
        # not become a zero-valued root child in the rollup population.
        #
        # `is not None`, NOT truthiness. An empty map is an explicit "no
        # source was observed" -- Reddit with nothing due did not read Reddit
        # -- and falling back to the aggregate verdict there would stamp
        # `{'reddit': 'ok'}` onto the rollup, which writes a zero-count child
        # row under a name no fetch produced. Only a MISSING map (None) means
        # "this fetcher does not report per-source status", where the
        # aggregate genuinely applies to the one name it fetched under.
        if result.per_source_status is None:
            result_statuses = {source: result.status}
        else:
            result_statuses = dict(result.per_source_status)
        statuses.update(result_statuses)
        depths[source] = result.catchup_depth

        # Nothing observed at all, or everything observed failed. Either way
        # there is no coverage this cycle: no buckets are touched on this
        # source's behalf and no cursor moves. Aggregate status remains useful
        # for cycle reporting, but it cannot discard an earlier successful sub
        # when a later request was refused.
        if not result_statuses or all(
                status == 'missing' for status in result_statuses.values()):
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
