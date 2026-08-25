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
