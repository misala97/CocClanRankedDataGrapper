# personal_apps/tests/test_radar_journal.py
"""The journal is what makes a bucket rebuildable.

roll_up used to recompute a bucket from one cycle's in-memory mentions and
overwrite the result. Every source advances a cursor, so each cycle carries
only a slice, and a bucket touched by several cycles kept the last slice.
Measured in production 2026-08-26: 43% of the 10+ mention buckets lost.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarMentionEvent


@pytest.fixture()
def clean_events():
    with flask_app.app_context():
        RadarMentionEvent.query.filter(
            RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarMentionEvent.query.filter(
            RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture()
def clean_buckets():
    from models import RadarBucket, RadarBucketSource
    with flask_app.app_context():
        for model in (RadarBucketSource, RadarBucket):
            model.query.filter(model.ticker.like('ZZ%')).delete(
                synchronize_session=False)
        db.session.commit()
        yield
        for model in (RadarBucketSource, RadarBucket):
            model.query.filter(model.ticker.like('ZZ%')).delete(
                synchronize_session=False)
        db.session.commit()


_ALL_OK = {'bluesky': 'ok'}


def _row(external_id, ticker='ZZA', minute=3, source='bluesky', author='u1',
         simhash=111, confidence='high', sentiment=0.5, engagement=10.0,
         channel='c'):
    from features.radar import buckets
    return buckets.MentionRow(
        ticker=ticker, external_id=external_id,
        created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
        source=source, channel=channel, author=author, simhash=simhash,
        confidence=confidence, sentiment=sentiment, engagement=engagement)


def test_a_second_poll_inside_one_bucket_does_not_erase_the_first(clean_buckets,
                                                                  clean_events):
    """The production shape, which the old regression test never modelled.

    tests/test_radar_buckets.py fed its second roll_up call a SUPERSET of the
    first, modelling a full re-read of the window. No source does that: every
    one advances a cursor, so cycle N+1 carries a DISJOINT tail. The assertion
    encoded the assumption instead of testing it, and passed for months while
    production lost 43% of its busiest buckets.
    """
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1, minute=1)],
                    _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-b', author='u2', simhash=2, minute=4)],
                    _ALL_OK, start)

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
    assert bucket.distinct_authors == 2


def test_the_same_post_arriving_twice_is_counted_once(clean_buckets, clean_events):
    """Cycles overlap by design; the unique key is what absorbs that."""
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1)],
                    _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1)],
                    _ALL_OK, start)

    assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 1


def test_a_cashtag_vouches_across_cycle_boundaries(clean_buckets, clean_events):
    """Promotion is a property of the QUARTER-HOUR, not of one cycle's slice.

    _promote's own docstring says the window is the bucket. It could not be,
    while the only rows it saw were the ones this cycle happened to fetch.
    """
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-low', author='u1', simhash=1,
                          confidence='low', minute=1)], _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-high', author='u2', simhash=2,
                          confidence='high', minute=9)], _ALL_OK, start)

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    # The low was promoted to medium by the later cycle's cashtag.
    assert bucket.mention_count == 2
    assert bucket.high_confidence_count == 1
    assert bucket.low_count == 0


def test_the_table_accepts_one_event(clean_events):
    db.session.add(RadarMentionEvent(
        source='bluesky', external_id='zz-1', ticker='ZZA', channel='c',
        created_utc=dt.datetime(2026, 4, 15, 14, 3, 0),
        bucket_start=dt.datetime(2026, 4, 15, 14, 0, 0),
        author='u1', simhash=111, confidence='high',
        sentiment=0.5, engagement=10.0))
    db.session.commit()

    row = RadarMentionEvent.query.filter_by(ticker='ZZA').one()
    assert row.confidence == 'high'
    assert row.bucket_start == dt.datetime(2026, 4, 15, 14, 0, 0)


def test_the_same_mention_cannot_be_stored_twice(clean_events):
    """(source, external_id, ticker) is the identity of a mention.

    A post returned by two overlapping cycles is one mention, not two, and the
    unique key is what stops a rebuild from double-counting it.
    """
    import sqlalchemy as sa

    for _ in range(2):
        db.session.add(RadarMentionEvent(
            source='bluesky', external_id='zz-dup', ticker='ZZB', channel='c',
            created_utc=dt.datetime(2026, 4, 15, 14, 3, 0),
            bucket_start=dt.datetime(2026, 4, 15, 14, 0, 0),
            author='u1', simhash=222, confidence='high',
            sentiment=None, engagement=0.0))
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()
