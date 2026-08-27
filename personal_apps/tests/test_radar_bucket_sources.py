# personal_apps/tests/test_radar_bucket_sources.py
"""Per-source data in rows, not columns.

Two sources meant eight columns. Three makes twelve, and a UI that lets the
user pick a subset has to pool whichever ones they chose -- which columns named
after specific sources cannot express at all (spec 4.5, 8.6).
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarBucketSource
from features.radar import buckets
from test_radar_buckets import row, clean_buckets  # noqa: F401

START = dt.datetime(2026, 8, 21, 14, 0, 0)
_OWNED_TICKERS = ('ZZA',)


def _clear_owned_rows():
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker.in_(_OWNED_TICKERS)).delete(
        synchronize_session=False)
    RadarBucket.query.filter(RadarBucket.ticker.in_(_OWNED_TICKERS)).delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        _clear_owned_rows()
        yield
        _clear_owned_rows()


def _row(source='bluesky', ticker='ZZA', count=3, status='ok'):
    return RadarBucketSource(
        ticker=ticker, bucket_start=START, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), sentiment_mean=0.1,
        sentiment_stdev=None, status=status)


def test_one_row_per_source_for_the_same_bucket(ctx):
    for source in ('reddit', 'bluesky', 'fourchan'):
        db.session.add(_row(source=source))
    db.session.commit()
    assert RadarBucketSource.query.filter_by(ticker='ZZA').count() == 3


def test_the_same_source_twice_in_one_bucket_is_rejected(ctx):
    db.session.add(_row())
    db.session.commit()
    db.session.add(_row(count=99))
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_an_arbitrary_subset_pools_by_group_by(ctx):
    """The whole reason this table exists. The UI selector picks sources and
    the query sums over exactly those -- no schema knows their names."""
    db.session.add(_row(source='reddit', count=10))
    db.session.add(_row(source='bluesky', count=4))
    db.session.add(_row(source='fourchan', count=1))
    db.session.commit()

    chosen = ['reddit', 'bluesky']
    total = db.session.query(
        sa.func.sum(RadarBucketSource.mention_count)).filter(
        RadarBucketSource.ticker == 'ZZA',
        RadarBucketSource.bucket_start == START,
        RadarBucketSource.source.in_(chosen)).scalar()
    assert total == 14


def test_a_source_can_be_missing_while_another_is_ok(ctx):
    db.session.add(_row(source='reddit', status='ok'))
    db.session.add(_row(source='bluesky', status='truncated'))
    db.session.commit()
    statuses = {r.source: r.status for r in
                RadarBucketSource.query.filter_by(ticker='ZZA').all()}
    assert statuses == {'reddit': 'ok', 'bluesky': 'truncated'}


def test_low_confidence_is_counted_separately_from_scored(ctx):
    """low is stored but never scored (spec 4.2). Keeping the count is what
    lets the extractor's false-positive rate be measured against real data."""
    row = _row(count=5)
    row.low_count = 40
    db.session.add(row)
    db.session.commit()
    db.session.expire(row)
    assert row.mention_count == 5
    assert row.low_count == 40


def test_scoring_columns_start_null(ctx):
    db.session.add(_row())
    db.session.commit()
    row = RadarBucketSource.query.filter_by(ticker='ZZA').one()
    assert row.expected is None
    assert row.variance is None
    assert row.mention_z is None
    assert row.baseline_days is None


def test_the_parent_bucket_no_longer_has_per_source_columns(ctx):
    """A leftover count_reddit would be dead weight that some query eventually
    reads and quietly trusts."""
    for gone in ('count_reddit', 'count_stocktwits', 'status_reddit',
                 'status_stocktwits', 'mention_z_reddit', 'mention_z_stocktwits',
                 'baseline_days_reddit', 'baseline_days_stocktwits'):
        assert not hasattr(RadarBucket, gone), '%s should be gone' % gone


def test_the_parent_bucket_keeps_its_totals(ctx):
    for kept in ('mention_count', 'distinct_authors', 'sources_ok',
                 'source_config_version'):
        assert hasattr(RadarBucket, kept)


def test_a_downgrade_to_truncated_clears_the_stale_score(clean_buckets):
    """Scoring refuses a row that is not `ok`. Rewriting the status must not
    leave behind a z that the scorer would no longer produce.

    Found in production 2026-08-26: 399 rows marked truncated and still ranked
    on a mention_z from when they were ok.
    """
    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([row(external_id='zz-1')], {'bluesky': 'ok'}, start)

    scored = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    scored.mention_z = 4.2
    scored.expected = 1.0
    scored.variance = 2.0
    scored.baseline_days = 9
    db.session.commit()

    buckets.roll_up([row(external_id='zz-2', author='u2', simhash=2)],
                    {'bluesky': 'truncated'}, start)

    after = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    assert after.status == 'truncated'
    assert after.mention_z is None
    assert after.expected is None
    assert after.variance is None
    assert after.baseline_days is None
