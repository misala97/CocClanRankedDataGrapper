# personal_apps/tests/test_radar_ingest.py
"""End-to-end through the pipeline with the network replaced by a callable.

The deleted-post case is the one worth reading twice: the text goes, the counts
stay. Removing the mention rows would rewrite history every time a user deleted
a post, and the aggregate fact that a ticker was discussed is not what needs
forgetting (spec 4.1).
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarMention, RadarPost, TickerUniverse
from features.radar import ingest
from features.radar.sources import FetchResult, RawPost

NOW = dt.datetime(2026, 4, 15, 14, 20, 0)


@pytest.fixture()
def seeded(clean_radar):
    with flask_app.app_context():
        db.session.add(TickerUniverse(symbol='ZZG', name='Zulu Games Corp',
                                      exchange='NYSE',
                                      first_seen=dt.datetime(2026, 1, 1)))
        db.session.commit()
        yield


@pytest.fixture()
def clean_radar():
    with flask_app.app_context():
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


def post(ident='t3_1', body='$ZZG is ripping', score=5, author='u1',
         minute=10, title=None):
    return RawPost(source='reddit', external_id=ident, channel='testsub',
                   author=author,
                   created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
                   title=title, body=body, score=score, num_comments=0,
                   url='https://example.invalid/%s' % ident)


def fetcher_for(result):
    def fetcher(since):
        return result
    return fetcher


def test_a_post_becomes_a_mention_and_a_bucket(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post()], status='ok')))

    assert result['posts_new'] == 1
    assert result['mentions'] == 1
    assert result['buckets_written'] == 1

    with flask_app.app_context():
        stored = RadarPost.query.filter_by(external_id='t3_1').one()
        assert stored.simhash != 0
        mention = RadarMention.query.filter_by(post_id=stored.id).one()
        assert mention.ticker == 'ZZG'
        assert mention.confidence == 'high'
        assert mention.lexicon_sentiment is not None
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 1


def test_reseeing_a_post_updates_its_score_without_duplicating(seeded):
    ingest.run_cycle(NOW, fetcher_for(FetchResult(posts=[post(score=5)], status='ok')))
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post(score=900)], status='ok')))

    assert result['posts_new'] == 0
    with flask_app.app_context():
        assert RadarPost.query.filter_by(external_id='t3_1').count() == 1
        assert RadarPost.query.filter_by(external_id='t3_1').one().score == 900


def test_a_deleted_post_loses_its_text_but_keeps_its_counts(seeded):
    ingest.run_cycle(NOW, fetcher_for(FetchResult(posts=[post()], status='ok')))
    ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='', author=None)], status='ok')))

    with flask_app.app_context():
        stored = RadarPost.query.filter_by(external_id='t3_1').one()
        assert stored.body == ''
        assert RadarMention.query.filter_by(post_id=stored.id).count() == 1
        assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1


def test_a_missing_source_writes_nothing_at_all(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[], status='missing')))

    assert result['status'] == 'missing'
    assert result['buckets_written'] == 0
    with flask_app.app_context():
        assert RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).count() == 0


def test_a_truncated_cycle_still_stores_its_mentions(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post()], status='truncated',
                                     catchup_depth=10)))

    assert result['status'] == 'truncated'
    assert result['catchup_depth'] == 10
    with flask_app.app_context():
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 1
        assert bucket.status_reddit == 'truncated'


def test_posts_with_no_recognizable_ticker_are_stored_but_bucket_nothing(seeded):
    """Storing them is what makes the next cycle's `since` correct."""
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='market feels weird today')],
                                status='ok')))

    assert result['posts_new'] == 1
    assert result['mentions'] == 0
    with flask_app.app_context():
        assert RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).count() == 0


def test_since_advances_to_the_newest_stored_post(seeded):
    captured = {}

    def fetcher(since):
        captured['since'] = since
        return FetchResult(posts=[post(minute=10)], status='ok')

    ingest.run_cycle(NOW, fetcher)
    ingest.run_cycle(NOW, fetcher)
    assert captured['since'] == dt.datetime(2026, 4, 15, 14, 10, 0)
