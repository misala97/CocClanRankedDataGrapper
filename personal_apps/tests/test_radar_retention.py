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
        engagement_weighted_count=9.0, count_reddit=3, count_stocktwits=0,
        status_reddit='ok', status_stocktwits='missing', sources_ok=1,
        source_config_version='deadbeefdeadbeef'))
    db.session.commit()

    retention.prune_posts(NOW)
    assert RadarBucket.query.filter_by(ticker='ZZR', bucket_start=old).count() == 1


def test_chunking_deletes_everything_across_several_passes(aged_posts):
    deleted = retention.prune_posts(NOW, chunk_size=1)
    assert deleted == 2


def test_pruning_an_empty_window_is_a_no_op(aged_posts):
    retention.prune_posts(NOW)
    assert retention.prune_posts(NOW) == 0
