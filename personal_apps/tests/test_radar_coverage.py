"""Which slots ingest was alive for, cached as a set that grows.

The memo used to be keyed by (start, now) at minute grain, so every minute
re-ran the DISTINCT over radar_bucket_sources -- 1.8s for a week by
2026-09-01, the whole of the 1W panel's wait. The set only ever gains slots,
so it is kept whole per source selection and topped up from the newest
slots on each call; a full rescan every few minutes catches a backfill into
an older slot.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource
from features.radar import coverage
from features.radar.config import source_config_version

# Far from any window the dev database holds data for, and a fixed clock:
# the cache's own TTLs are driven by `coverage._clock`, patched below.
NOW = dt.datetime(2025, 3, 5, 12, 0, 0)
START = NOW - dt.timedelta(days=7)
SOURCE = 'bluesky'


def slot(minutes_ago, ticker='CVA', status='ok'):
    when = NOW - dt.timedelta(minutes=minutes_ago)
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=when, source=SOURCE, mention_count=1,
        high_confidence_count=1, low_count=0, distinct_authors=1,
        distinct_text_ratio=1.0, engagement_weighted_count=1.0, status=status,
        source_config_version=source_config_version(), expected=1.0,
        variance=1.0, mention_z=0.0, baseline_days=30))
    db.session.commit()
    return when


@pytest.fixture()
def clean():
    def wipe():
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('CV%')).delete(synchronize_session=False)
        db.session.commit()
    with flask_app.app_context():
        wipe()
        coverage.clear_memo()
        yield
        wipe()
        coverage.clear_memo()


def covered():
    return coverage.covered_bucket_starts([SOURCE], START, NOW)


def test_a_slot_written_after_the_first_call_shows_on_the_next(clean, monkeypatch):
    monkeypatch.setattr(coverage, '_clock', lambda: NOW)
    first = slot(minutes_ago=60)
    assert first in covered()

    second = slot(minutes_ago=15)

    assert covered() >= {first, second}


def test_a_backfill_into_an_old_slot_shows_after_the_full_rescan(clean, monkeypatch):
    clock = {'at': NOW}
    monkeypatch.setattr(coverage, '_clock', lambda: clock['at'])
    slot(minutes_ago=60)
    covered()

    old = slot(minutes_ago=3 * 60)
    # Not yet: the top-up only re-reads the newest slots.
    assert old not in covered()

    clock['at'] = NOW + coverage.FULL_RESCAN + dt.timedelta(seconds=1)
    assert old in covered()


def test_the_answer_is_bounded_by_the_range_asked(clean, monkeypatch):
    monkeypatch.setattr(coverage, '_clock', lambda: NOW)
    inside = slot(minutes_ago=60)
    slot(minutes_ago=8 * 24 * 60)          # before START
    slot(minutes_ago=-30)                  # after NOW

    assert covered() == {inside}


def test_a_missing_slot_is_not_coverage(clean, monkeypatch):
    monkeypatch.setattr(coverage, '_clock', lambda: NOW)
    ok = slot(minutes_ago=60)
    slot(minutes_ago=45, status='missing')

    assert covered() == {ok}


def test_clear_memo_forgets_the_set(clean, monkeypatch):
    monkeypatch.setattr(coverage, '_clock', lambda: NOW)
    slot(minutes_ago=60)
    covered()
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker.like('CV%')).delete(synchronize_session=False)
    db.session.commit()

    coverage.clear_memo()

    assert covered() == set()
