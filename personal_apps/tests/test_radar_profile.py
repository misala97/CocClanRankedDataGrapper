# personal_apps/tests/test_radar_profile.py
"""What a normal bucket looks like, per source.

Chatter has a strong weekly shape, and comparing 03:00 Sunday against 15:00
Tuesday as one population makes every weekday afternoon a spike. The profile is
what removes that shape before anything is called unusual.

Per source, not market-wide: StockTwits follows US market hours, Bluesky is
global and diurnal, /biz/ runs around the clock. One shared profile would tell
Bluesky to expect silence when half its users are awake.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource
from features.radar import profile

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)      # a Monday, 00:00 UTC


@pytest.fixture()
def buckets():
    with flask_app.app_context():
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('PP%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('PP%')).delete(synchronize_session=False)
        db.session.commit()


def add(source, when, count, ticker='PPA', status='ok'):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=when, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), status=status))


def test_bucket_of_week_is_zero_at_monday_midnight():
    assert profile.bucket_of_week(MONDAY) == 0


def test_bucket_of_week_advances_every_fifteen_minutes():
    assert profile.bucket_of_week(MONDAY + dt.timedelta(minutes=15)) == 1
    assert profile.bucket_of_week(MONDAY + dt.timedelta(hours=1)) == 4


def test_bucket_of_week_wraps_after_a_week():
    assert profile.bucket_of_week(MONDAY + dt.timedelta(days=7)) == 0
    assert profile.bucket_of_week(
        MONDAY + dt.timedelta(days=6, hours=23, minutes=45)) == 671


def test_a_profile_sums_to_one(buckets):
    for hour in (2, 14, 20):
        add('stocktwits', MONDAY + dt.timedelta(hours=hour), count=hour)
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    assert sum(built.values()) == pytest.approx(1.0)


def test_busy_buckets_get_a_larger_share(buckets):
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
    add('stocktwits', MONDAY + dt.timedelta(hours=3), count=1)
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    busy = profile.hour_share(built, MONDAY + dt.timedelta(hours=14))
    quiet = profile.hour_share(built, MONDAY + dt.timedelta(hours=3))
    assert busy > quiet * 10


def test_every_bucket_has_a_nonzero_share(buckets):
    """Smoothing is load-bearing. A share of zero makes expected zero, and any
    observation against it is an infinite z -- so one quiet hour in the sample
    window would manufacture a spike there forever after."""
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=50)
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    assert len(built) == 672
    assert all(share > 0 for share in built.values())


def test_profiles_are_per_source(buckets):
    """StockTwits peaks in the US session; a 24/7 source does not. Sharing one
    profile would read half of Bluesky's normal traffic as unusual."""
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
    add('bluesky', MONDAY + dt.timedelta(hours=3), count=100)
    db.session.commit()
    st = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    bs = profile.build_profile('bluesky', MONDAY + dt.timedelta(days=1))
    assert profile.hour_share(st, MONDAY + dt.timedelta(hours=14)) > \
        profile.hour_share(bs, MONDAY + dt.timedelta(hours=14))


def test_missing_and_truncated_buckets_are_ignored(buckets):
    """A source that was down did not observe a quiet hour. Counting the gap
    would bend the profile towards silence at exactly the wrong times."""
    add('stocktwits', MONDAY + dt.timedelta(hours=14), count=100)
    add('stocktwits', MONDAY + dt.timedelta(hours=15), count=0, status='missing')
    add('stocktwits', MONDAY + dt.timedelta(hours=16), count=5, status='truncated')
    db.session.commit()
    built = profile.build_profile('stocktwits', MONDAY + dt.timedelta(days=1))
    fifteen = profile.hour_share(built, MONDAY + dt.timedelta(hours=15))
    sixteen = profile.hour_share(built, MONDAY + dt.timedelta(hours=16))
    # Both fall back to the smoothing floor, and are equal because neither
    # contributed an observation.
    assert fifteen == pytest.approx(sixteen)


def test_an_empty_history_gives_a_flat_profile(buckets):
    """Day one. Flat means "no idea yet", which is the honest prior and cannot
    on its own make anything look unusual."""
    built = profile.build_profile('stocktwits', MONDAY)
    assert len(built) == 672
    assert len(set(round(v, 12) for v in built.values())) == 1
