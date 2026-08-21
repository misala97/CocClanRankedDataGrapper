# personal_apps/tests/test_radar_scoring.py
"""Turning counts into surprise.

Everything here reads radar_bucket_sources and writes back onto the same rows.
No prices and no divergence -- those need a market feed and are Plan 3.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource
from features.radar import scoring
from features.radar.config import source_config_version

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)
NOW = MONDAY + dt.timedelta(days=35)


@pytest.fixture()
def rows():
    with flask_app.app_context():
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('SS%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('SS%')).delete(synchronize_session=False)
        db.session.commit()


def add(when, count, ticker='SSA', source='stocktwits', status='ok',
        version=None):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=when, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), status=status,
        source_config_version=version or source_config_version()))


def steady_history(ticker='SSA', per_bucket=2, days=30, source='stocktwits'):
    """A boringly consistent ticker, so anything unusual is the test's doing.

    2880 rows at 15-minute grain. Added to the session and committed once by
    the caller -- committing per row makes this suite take minutes.
    """
    for step in range(days * 96):
        add(MONDAY + dt.timedelta(minutes=15 * step), per_bucket,
            ticker=ticker, source=source)


def test_a_normal_bucket_scores_near_zero(rows):
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.mention_z is not None
    assert abs(row.mention_z) < 2


def test_a_spike_scores_high(rows):
    steady_history()
    loud = MONDAY + dt.timedelta(days=20)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
        {'mention_count': 60})
    db.session.commit()

    scoring.score_source('stocktwits', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=loud).one().mention_z > 5


def test_expected_and_variance_are_stored_too(rows):
    """Pooling a user-selected subset means summing components, so the parts
    have to survive, not just the z (spec 6.2)."""
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.expected > 0
    assert row.variance >= row.expected


def test_missing_buckets_are_never_scored(rows):
    """A source that was down has nothing to be surprised about."""
    steady_history()
    gap = MONDAY + dt.timedelta(days=12)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=gap).update(
        {'status': 'missing', 'mention_count': 0})
    db.session.commit()

    scoring.score_source('stocktwits', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=gap).one().mention_z is None


def test_a_gap_does_not_depress_the_baseline(rows):
    """The observed-mass property, end to end. A week of outage must not make
    the ticker look like it went quiet, or everything after would spike."""
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    reference = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z

    outage_start = MONDAY + dt.timedelta(days=5)
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker == 'SSA',
        RadarBucketSource.bucket_start >= outage_start,
        RadarBucketSource.bucket_start < outage_start + dt.timedelta(days=7)
    ).update({'status': 'missing', 'mention_count': 0}, synchronize_session=False)
    db.session.commit()

    scoring.score_source('stocktwits', NOW)
    after = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z
    assert after == pytest.approx(reference, abs=0.5)


def test_baseline_days_is_recorded(rows):
    steady_history(days=30)
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.baseline_days >= 14


def test_a_brand_new_ticker_is_provisional(rows):
    """Two days of history cannot support a z-score anyone should act on."""
    for step in range(2 * 96):
        add(NOW - dt.timedelta(days=2) + dt.timedelta(minutes=15 * step), 3,
            ticker='SSNEW')
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    row = (RadarBucketSource.query.filter_by(ticker='SSNEW')
           .order_by(RadarBucketSource.bucket_start.desc()).first())
    assert row.baseline_days < 14


def test_scoring_only_touches_its_own_source(rows):
    steady_history(source='stocktwits')
    steady_history(ticker='SSB', source='bluesky')
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    assert RadarBucketSource.query.filter_by(
        ticker='SSB', source='bluesky').first().mention_z is None
