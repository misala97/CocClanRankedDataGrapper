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
from models import (RadarBucket, RadarMention, RadarPost,
                    RadarSourceCursor, TickerUniverse)
from features.radar import ingest
from features.radar.sources import FetchResult, RawPost

NOW = dt.datetime(2026, 4, 15, 14, 20, 0)


def _wipe():
    from models import RadarBucketSource
    RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
        synchronize_session=False)
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
    RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
        synchronize_session=False)
    TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
        synchronize_session=False)
    RadarSourceCursor.query.delete(synchronize_session=False)


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
        _wipe()
        db.session.commit()
        yield
        _wipe()
        db.session.commit()


def post(ident='t3_1', body='$ZZG is ripping', score=5, author='u1',
         minute=10, title=None):
    return RawPost(source='stocktwits', external_id=ident, channel='testsub',
                   author=author,
                   created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
                   title=title, body=body, score=score, num_comments=0,
                   url='https://example.invalid/%s' % ident)


def fetcher_for(result, source='stocktwits'):
    def fetcher(since):
        return result
    return {source: fetcher}


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

    assert result['per_source'] == {'stocktwits': 'missing'}
    assert result['buckets_written'] == 0
    with flask_app.app_context():
        assert RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).count() == 0


def test_a_truncated_cycle_still_stores_its_mentions(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post()], status='truncated',
                                     catchup_depth=10)))

    assert result['per_source'] == {'stocktwits': 'truncated'}
    assert result['catchup_depth'] == {'stocktwits': 10}
    with flask_app.app_context():
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 1
        from models import RadarBucketSource
        assert RadarBucketSource.query.filter_by(
            ticker='ZZG', source='stocktwits').one().status == 'truncated'


def test_posts_with_no_recognizable_ticker_are_not_stored_at_all(seeded):
    """Bluesky is 144k posts/hour and almost none are about stocks. Storing
    everything and extracting later would be 100 million rows a month to find
    the quarter-million that matter, so extraction runs first and a post that
    mentions nothing is never written."""
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='market feels weird today')],
                                status='ok')))

    assert result['posts_seen'] == 1
    assert result['posts_new'] == 0
    assert result['mentions'] == 0
    with flask_app.app_context():
        assert RadarPost.query.filter_by(channel='testsub').count() == 0


def test_the_cursor_advances_even_when_nothing_was_stored(seeded):
    """The cursor tracks what was SEEN, not what was KEPT. Inferring it from
    stored rows would rewind every cycle and refetch the same window forever."""
    ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='no tickers here', minute=12)],
                                status='ok')))
    with flask_app.app_context():
        cursor = RadarSourceCursor.query.filter_by(source='stocktwits').one()
        assert cursor.cursor_utc == dt.datetime(2026, 4, 15, 14, 12, 0)


def test_since_advances_to_the_newest_post_seen(seeded):
    captured = {}

    def fetcher(since):
        captured['since'] = since
        return FetchResult(posts=[post(minute=10)], status='ok')

    ingest.run_cycle(NOW, {'stocktwits': fetcher})
    ingest.run_cycle(NOW, {'stocktwits': fetcher})
    assert captured['since'] == dt.datetime(2026, 4, 15, 14, 10, 0)


def test_two_sources_ingest_in_one_cycle(seeded):
    def st(since):
        return FetchResult(posts=[post(ident='st1', body='$ZZG up')], status='ok')

    def bs(since):
        p = post(ident='bs1', body='$ZZG up')
        p.source = 'bluesky'
        return FetchResult(posts=[p], status='ok')

    result = ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
    assert result['posts_new'] == 2
    assert result['per_source'] == {'stocktwits': 'ok', 'bluesky': 'ok'}
    with flask_app.app_context():
        from models import RadarBucketSource
        sources = {r.source for r in
                   RadarBucketSource.query.filter_by(ticker='ZZG').all()}
        assert sources == {'stocktwits', 'bluesky'}


def test_one_source_failing_does_not_stop_the_other(seeded):
    """The entire reason status is per source. A dead Bluesky must not cost a
    healthy StockTwits cycle, and must not write a zero for itself."""
    def st(since):
        return FetchResult(posts=[post(ident='st1', body='$ZZG up')], status='ok')

    def bs(since):
        return FetchResult(posts=[], status='missing')

    result = ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
    assert result['per_source'] == {'stocktwits': 'ok', 'bluesky': 'missing'}
    with flask_app.app_context():
        from models import RadarBucketSource
        rows = {r.source: r.status for r in
                RadarBucketSource.query.filter_by(ticker='ZZG').all()}
        assert rows == {'stocktwits': 'ok'}


def test_each_source_keeps_its_own_cursor(seeded):
    """One source catching up must not drag the others back over ground they
    already covered."""
    def st(since):
        return FetchResult(posts=[post(ident='st1', body='$ZZG', minute=10)],
                           status='ok')

    def bs(since):
        p = post(ident='bs1', body='$ZZG', minute=18)
        p.source = 'bluesky'
        return FetchResult(posts=[p], status='ok')

    ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
    with flask_app.app_context():
        cursors = {c.source: c.cursor_utc for c in RadarSourceCursor.query.all()}
    assert cursors['stocktwits'] == dt.datetime(2026, 4, 15, 14, 10, 0)
    assert cursors['bluesky'] == dt.datetime(2026, 4, 15, 14, 18, 0)


def test_the_same_post_twice_in_one_batch_is_stored_once(seeded):
    """A StockTwits message tagged $ZZG and $OTHER is returned by both symbol
    streams, so one cycle sees the same external_id twice. Found in live data,
    not in tests -- every fixture until now used distinct ids."""
    duplicate = [post(ident='dup1', body='$ZZG and more'),
                 post(ident='dup1', body='$ZZG and more')]
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=duplicate, status='ok')))

    assert result['posts_new'] == 1
    assert result['mentions'] == 1
    with flask_app.app_context():
        assert RadarPost.query.filter_by(external_id='dup1').count() == 1
        assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1


def test_a_low_only_post_is_counted_but_never_stored(seeded):
    """ROM in "dinosaur fossils at the ROM" is a real ticker and a real bare
    match, and about 12000 an hour of its kind cross the firehose. It is
    counted so the extractor's false-positive rate stays measurable, but the
    text is never kept -- seven million rows a month for posts the leaderboard
    can never surface."""
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(ident='low1', body='ZZG rumours')],
                                status='ok')))

    assert result['posts_new'] == 0
    assert result['mentions'] == 1
    with flask_app.app_context():
        assert RadarPost.query.filter_by(external_id='low1').count() == 0
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 0
        assert bucket.low_count == 1


def test_a_low_is_still_promoted_by_a_stored_high(seeded):
    """Promotion happens in memory before storage, so an unstored low can still
    be vouched for by a stored high from another author."""
    bare = post(ident='bare1', body='ZZG rumours', author='u1')
    tagged = post(ident='tag1', body='$ZZG confirmed', author='u2')
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[bare, tagged], status='ok')))

    assert result['posts_new'] == 1          # only the cashtagged one stored
    with flask_app.app_context():
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 2     # both scored
        assert bucket.low_count == 0
