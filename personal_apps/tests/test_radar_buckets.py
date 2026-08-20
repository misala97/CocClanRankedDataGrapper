# personal_apps/tests/test_radar_buckets.py
"""The rollup is where per-source status becomes durable.

`truncated` is the subtle case: those counts are real but incomplete, so they
must be visible on the live leaderboard while being barred from any baseline.
Plan 2 enforces the second half; this suite pins that the status reaches the
row at all, because a bucket written `ok` when it was truncated is
indistinguishable from a genuine quiet period forever after.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucket
from features.radar import buckets
from features.radar.config import source_config_version


@pytest.fixture()
def clean_buckets():
    with flask_app.app_context():
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


def row(ticker='ZZA', minute=3, source='reddit', author='u1', simhash=111,
        confidence='high', sentiment=0.5, engagement=10.0):
    return buckets.MentionRow(
        ticker=ticker,
        created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
        source=source, author=author, simhash=simhash,
        confidence=confidence, sentiment=sentiment, engagement=engagement)


ALL_OK = {'reddit': 'ok', 'stocktwits': 'missing'}


def test_bucket_start_floors_to_fifteen_minutes():
    assert buckets.bucket_start_for(dt.datetime(2026, 4, 15, 14, 3, 59)) == \
        dt.datetime(2026, 4, 15, 14, 0, 0)
    assert buckets.bucket_start_for(dt.datetime(2026, 4, 15, 14, 44, 0)) == \
        dt.datetime(2026, 4, 15, 14, 30, 0)


def test_counts_are_written(clean_buckets):
    buckets.roll_up([row(author='u1', simhash=1), row(author='u2', simhash=2)],
                    ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
    assert bucket.distinct_authors == 2
    assert bucket.count_reddit == 2
    assert bucket.high_confidence_count == 2


def test_distinct_text_ratio_catches_a_copy_paste_brigade(clean_buckets):
    """Fifty accounts posting one thing. distinct_authors sees nothing wrong;
    this is the column that does."""
    rows = [row(author='u%d' % i, simhash=999) for i in range(4)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.distinct_authors == 4
    assert bucket.distinct_text_ratio == pytest.approx(0.25)


def test_per_source_status_is_stored_separately(clean_buckets):
    buckets.roll_up([row()], {'reddit': 'ok', 'stocktwits': 'missing'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.status_reddit == 'ok'
    assert bucket.status_stocktwits == 'missing'
    assert bucket.sources_ok == 1


def test_truncated_counts_are_kept_and_marked(clean_buckets):
    buckets.roll_up([row()], {'reddit': 'truncated', 'stocktwits': 'missing'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 1
    assert bucket.status_reddit == 'truncated'
    assert bucket.sources_ok == 0


def test_a_missing_source_writes_no_bucket_rather_than_a_zero(clean_buckets):
    """The single most important rule in the ingest layer. A zero here would
    poison the baseline and manufacture a spike when ingest resumes."""
    written = buckets.roll_up([], {'reddit': 'missing', 'stocktwits': 'missing'},
                              {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert written == 0
    assert RadarBucket.query.filter_by(ticker='ZZA').count() == 0


def test_rerunning_a_cycle_replaces_rather_than_doubles(clean_buckets):
    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([row(author='u1', simhash=1)], ALL_OK, start)
    buckets.roll_up([row(author='u1', simhash=1), row(author='u2', simhash=2)],
                    ALL_OK, start)
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2


def test_mentions_split_across_bucket_boundaries(clean_buckets):
    touched = {dt.datetime(2026, 4, 15, 14, 0, 0),
               dt.datetime(2026, 4, 15, 14, 15, 0)}
    buckets.roll_up([row(minute=3), row(minute=20)], ALL_OK, touched)
    assert RadarBucket.query.filter_by(ticker='ZZA').count() == 2


def test_config_version_is_stamped(clean_buckets):
    buckets.roll_up([row()], ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.source_config_version == source_config_version()


def test_sentiment_mean_is_averaged(clean_buckets):
    buckets.roll_up([row(sentiment=1.0, author='u1', simhash=1),
                     row(sentiment=0.0, author='u2', simhash=2)],
                    ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.sentiment_mean == pytest.approx(0.5)


def test_scoring_columns_are_left_untouched(clean_buckets):
    """Plan 1 writes no scores. A rollup that reset these would silently
    invalidate Plan 2's work on every cycle."""
    buckets.roll_up([row()], ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    bucket.mention_z_reddit = 4.2
    db.session.commit()

    buckets.roll_up([row(), row(author='u2', simhash=2)], ALL_OK,
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    db.session.expire(bucket)
    assert bucket.mention_z_reddit == 4.2
