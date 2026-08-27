# personal_apps/tests/test_radar_retention.py
"""Raw text ages out at 30 days; buckets are forever.

Chunking is not a nicety. A single unbounded delete of 30 days of Reddit posts
locks the table and writes one enormous transaction, on the same connection the
daemon needs for its next cycle.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarMention, RadarPost
from features.radar import retention

NOW = dt.datetime(2026, 4, 15, 12, 0, 0)


@pytest.fixture()
def aged_posts():
    with flask_app.app_context():
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        db.session.commit()

        for index, age_days in enumerate([1, 10, 29, 31, 60]):
            created = NOW - dt.timedelta(days=age_days)
            post = RadarPost(source='reddit', external_id='t3_age%d' % index,
                             channel='testsub', author='u1', created_utc=created,
                             title=None, body='x', score=1, num_comments=0,
                             url='https://example.invalid/', simhash=1,
                             first_seen=created, last_seen=created)
            db.session.add(post)
            db.session.flush()
            db.session.add(RadarMention(post_id=post.id, ticker='ZZR',
                                        confidence='high', lexicon_sentiment=0.0))
        db.session.commit()
        yield
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


def test_only_posts_past_the_window_are_deleted(aged_posts):
    deleted = retention.prune_posts(NOW)
    assert deleted == 2
    remaining = RadarPost.query.filter_by(channel='testsub').count()
    assert remaining == 3


def test_mentions_go_with_their_posts(aged_posts):
    retention.prune_posts(NOW)
    surviving_ids = {row.id for row in
                     RadarPost.query.filter_by(channel='testsub').all()}
    orphans = RadarMention.query.filter(
        RadarMention.ticker == 'ZZR',
        RadarMention.post_id.notin_(surviving_ids or {0})).count()
    assert orphans == 0


def test_buckets_survive_their_posts(aged_posts):
    """The whole storage design rests on this: buckets are the queryable
    layer and outlive the text they were computed from."""
    old = NOW - dt.timedelta(days=60)
    db.session.add(RadarBucket(
        ticker='ZZR', bucket_start=old, mention_count=3,
        high_confidence_count=3, distinct_authors=3, distinct_text_ratio=1.0,
        engagement_weighted_count=9.0,
        sources_ok=1, source_config_version='deadbeefdeadbeef'))
    db.session.commit()

    retention.prune_posts(NOW)
    assert RadarBucket.query.filter_by(ticker='ZZR', bucket_start=old).count() == 1


def test_chunking_deletes_everything_across_several_passes(aged_posts):
    deleted = retention.prune_posts(NOW, chunk_size=1)
    assert deleted == 2


def test_pruning_an_empty_window_is_a_no_op(aged_posts):
    retention.prune_posts(NOW)
    assert retention.prune_posts(NOW) == 0


# --- mention journal pruning -------------------------------------------------
#
# `clean_events` here cleans up by EXACT identity (ticker='ZZA', the two
# external_ids this suite creates) rather than a broad `ticker.like('ZZ%')`
# sweep. prune_mention_events's own delete query is unscoped by ticker -- it
# is a real production pruner, not a test helper -- so the `now` chosen below
# is deliberately a 2026-04-20 cutoff: the real dev database's
# radar_mention_events rows are all from 2026-08-22/23 (checked directly
# against the shared dev DB before writing this test), months after that
# cutoff, so no real row can ever be `< cutoff` here regardless of what this
# fixture does or does not clean up.

@pytest.fixture()
def clean_events():
    from models import RadarMentionEvent
    idents = ('zz-new', 'zz-old', 'zz-boundary')

    def clear():
        RadarMentionEvent.query.filter(
            RadarMentionEvent.ticker == 'ZZA',
            RadarMentionEvent.external_id.in_(idents)).delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        clear()
        yield
        clear()


def test_the_journal_is_pruned_by_when_the_post_was_written(clean_events):
    """By created_utc, not by when the row was inserted. A catch-up after an
    outage ingests posts hours old, and once their bucket is past the retention
    window nothing will rewrite it -- so that is what decides.

    The third row sits at EXACTLY the cutoff (now - MENTION_EVENT_RETENTION_HOURS),
    still safely inside this test's own April-2026 `now` -- nowhere near the real
    dev database's Aug-2026 rows. `created_utc < cutoff` is strict, so a row
    exactly at the cutoff has not yet aged out and must survive. This pins the
    boundary: flipping the implementation's `<` to `<=` must fail this test.
    """
    from models import RadarMentionEvent

    now = dt.datetime(2026, 4, 20, 12, 0, 0)
    rows = (
        (1, 'zz-new'),
        (72, 'zz-old'),
        (retention.MENTION_EVENT_RETENTION_HOURS, 'zz-boundary'),
    )
    for hours, ident in rows:
        created = now - dt.timedelta(hours=hours)
        db.session.add(RadarMentionEvent(
            source='bluesky', external_id=ident, ticker='ZZA', channel='c',
            created_utc=created,
            bucket_start=created.replace(minute=0, second=0, microsecond=0),
            author='u1', simhash=1, confidence='high',
            sentiment=None, engagement=0.0))
    db.session.commit()

    deleted = retention.prune_mention_events(now)
    assert deleted == 1
    assert isinstance(deleted, int)
    remaining = {e.external_id for e in
                 RadarMentionEvent.query.filter_by(ticker='ZZA').all()}
    assert remaining == {'zz-new', 'zz-boundary'}
