# personal_apps/tests/test_radar_chatter_eligibility.py
"""Chatter eligibility on the journal and the bucket rebuild (spec §7.2).

A FINAL irrelevant/broadcast judgment removes an event from counts;
`uncertain` and unjudged stay provisional; a review reversal restores.
Runs against the real dev database: ZZE-prefixed rows, future dates
inside the 48h rebuild horizon.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from features.radar import buckets, config, journal
from features.radar.config import source_config_version
from models import RadarBucket, RadarBucketSource, RadarMentionEvent

TICKER = 'ZZE'
SOURCE = 'bluesky'
# Future, so it sits inside the utcnow-48h rebuild horizon and clear of
# real dev-database data.
WINDOW = dt.datetime.utcnow().replace(minute=0, second=0,
                                      microsecond=0) + dt.timedelta(days=200)


def _wipe():
    RadarMentionEvent.query.filter_by(ticker=TICKER).delete(
        synchronize_session=False)
    RadarBucketSource.query.filter_by(ticker=TICKER).delete(
        synchronize_session=False)
    RadarBucket.query.filter_by(ticker=TICKER).delete(
        synchronize_session=False)


@pytest.fixture()
def clean():
    with flask_app.app_context():
        _wipe()
        db.session.commit()
        yield
        _wipe()
        db.session.commit()


def event(external_id, author='u1', confidence='high', sentiment=0.5,
          engagement=10.0, minute=3, flag=None):
    row = RadarMentionEvent(
        source=SOURCE, external_id=external_id, ticker=TICKER,
        channel='c', created_utc=WINDOW + dt.timedelta(minutes=minute),
        bucket_start=WINDOW, author=author,
        simhash=abs(hash(external_id)) % (2 ** 63), confidence=confidence,
        sentiment=sentiment, engagement=engagement,
        counts_as_human_chatter=flag)
    db.session.add(row)
    return row


def child(expected=None, variance=None, mention_z=None, baseline_days=None,
          status='ok', version=None):
    row = RadarBucketSource(
        ticker=TICKER, bucket_start=WINDOW, source=SOURCE,
        mention_count=3, high_confidence_count=3, low_count=0,
        distinct_authors=3, distinct_text_ratio=1.0,
        engagement_weighted_count=30.0, status=status,
        source_config_version=version or source_config_version(),
        expected=expected, variance=variance, mention_z=mention_z,
        baseline_days=baseline_days)
    db.session.add(row)
    db.session.add(RadarBucket(
        ticker=TICKER, bucket_start=WINDOW, mention_count=3,
        high_confidence_count=3, low_count=0, distinct_authors=3,
        distinct_text_ratio=1.0, engagement_weighted_count=30.0,
        sources_ok=1, source_config_version=version or
        source_config_version()))
    return row


def identity(external_id):
    return (SOURCE, external_id, TICKER)


def test_the_generation_carries_the_population_change():
    assert config.ROLLUP_GENERATION == 3


def test_sync_sets_values_and_returns_only_changed_windows(clean):
    with flask_app.app_context():
        event('zze-a')
        event('zze-b')
        db.session.commit()

        changed = journal.sync_chatter_eligibility(
            [(identity('zze-a'), False), (identity('zze-b'), True)])
        db.session.commit()
        assert changed == {(TICKER, WINDOW)}

        rows = {r.external_id: r.counts_as_human_chatter
                for r in RadarMentionEvent.query.filter_by(
                    ticker=TICKER).all()}
        assert rows == {'zze-a': False, 'zze-b': True}

        # Re-syncing the same values changes nothing and rebuilds nothing.
        again = journal.sync_chatter_eligibility(
            [(identity('zze-a'), False), (identity('zze-b'), True)])
        assert again == set()

        # A reversal (review overturning the primary) is a change again.
        back = journal.sync_chatter_eligibility([(identity('zze-a'), True)])
        db.session.commit()
        assert back == {(TICKER, WINDOW)}


def test_events_for_excludes_only_the_confirmed_ineligible(clean):
    with flask_app.app_context():
        event('zze-a', flag=False)
        event('zze-b', flag=True)
        event('zze-c', flag=None)
        db.session.commit()

        got = {row.external_id
               for row in journal.events_for([(TICKER, WINDOW)])}
        assert got == {'zze-b', 'zze-c'}


def test_rebuild_drops_the_excluded_and_preserves_baseline_inputs(clean):
    with flask_app.app_context():
        event('zze-a', author='u1', engagement=10.0)
        event('zze-b', author='u2', engagement=10.0)
        event('zze-c', author='u3', engagement=10.0)
        child(expected=1.0, variance=2.0, mention_z=9.9, baseline_days=30.0)
        db.session.commit()

        journal.sync_chatter_eligibility([(identity('zze-c'), False)])
        db.session.commit()
        written = journal.rebuild_windows({(TICKER, WINDOW)})
        assert written == 1

        row = RadarBucketSource.query.filter_by(
            ticker=TICKER, bucket_start=WINDOW, source=SOURCE).one()
        assert row.mention_count == 2
        assert row.distinct_authors == 2
        assert row.engagement_weighted_count == 20.0
        # Source health and the baseline inputs are preserved...
        assert row.status == 'ok'
        assert row.expected == 1.0 and row.variance == 2.0
        assert row.baseline_days == 30.0
        # ...and the z is recomputed IMMEDIATELY from the corrected count.
        assert row.mention_z == pytest.approx((2 - 1.0) / 2.0 ** 0.5)
        parent = RadarBucket.query.filter_by(
            ticker=TICKER, bucket_start=WINDOW).one()
        assert parent.mention_count == 2
        assert parent.sources_ok == 1        # preserved, not recomputed

        # Idempotent: a second rebuild writes the same numbers.
        journal.rebuild_windows({(TICKER, WINDOW)})
        row = RadarBucketSource.query.filter_by(
            ticker=TICKER, bucket_start=WINDOW, source=SOURCE).one()
        assert row.mention_count == 2
        assert row.mention_z == pytest.approx((2 - 1.0) / 2.0 ** 0.5)


def test_removing_the_last_eligible_event_leaves_explicit_zeros(clean):
    with flask_app.app_context():
        event('zze-only')
        child()
        db.session.commit()

        journal.sync_chatter_eligibility([(identity('zze-only'), False)])
        db.session.commit()
        journal.rebuild_windows({(TICKER, WINDOW)})

        row = RadarBucketSource.query.filter_by(
            ticker=TICKER, bucket_start=WINDOW, source=SOURCE).one()
        assert row.mention_count == 0
        assert row.engagement_weighted_count == 0.0
        assert row.status == 'ok'            # a zero, not an absence
        parent = RadarBucket.query.filter_by(
            ticker=TICKER, bucket_start=WINDOW).one()
        assert parent.mention_count == 0


def test_a_generation_mismatch_clears_scores_instead_of_recomputing(clean):
    with flask_app.app_context():
        event('zze-a')
        child(expected=1.0, variance=2.0, mention_z=9.9, baseline_days=30.0,
              version='oldgen0000000000')
        db.session.commit()

        journal.rebuild_windows({(TICKER, WINDOW)})

        row = RadarBucketSource.query.filter_by(
            ticker=TICKER, bucket_start=WINDOW, source=SOURCE).one()
        assert row.expected is None and row.variance is None
        assert row.mention_z is None and row.baseline_days is None
        assert row.source_config_version == source_config_version()


def test_a_window_older_than_the_journal_horizon_is_refused(clean):
    with flask_app.app_context():
        stale = dt.datetime(2020, 1, 1, 12, 0, 0)
        assert journal.rebuild_windows({(TICKER, stale)}) == 0


def test_a_window_nothing_ever_counted_is_skipped(clean):
    with flask_app.app_context():
        event('zze-a')
        db.session.commit()
        # No child rows exist for the window.
        assert buckets.rebuild_windows({(TICKER, WINDOW)}) == 0


def test_recent_decided_windows_keys_on_decision_time_not_event_age(clean):
    """The Codex blocker-2 case: a backfill decides an event HOURS after it
    was created. A crash between the flag commit and the rebuild must be
    rediscovered by the next pass -- so the net keys on when the flag was
    DECIDED, never on created_utc."""
    with flask_app.app_context():
        now = dt.datetime.utcnow()
        row = event('zze-old')
        row.created_utc = now - dt.timedelta(hours=6)     # old event...
        row.bucket_start = buckets.bucket_start_for(row.created_utc)
        db.session.commit()

        journal.sync_chatter_eligibility([(identity('zze-old'), False)])
        db.session.commit()                                # ...decided NOW

        got = journal.recent_decided_windows(now + dt.timedelta(seconds=1))
        assert (TICKER, row.bucket_start) in got

        # An event whose flag was never decided is not in the net...
        undecided = event('zze-undecided')
        undecided.created_utc = now
        undecided.bucket_start = buckets.bucket_start_for(now)
        db.session.commit()
        got = journal.recent_decided_windows(now + dt.timedelta(seconds=1))
        assert (TICKER, undecided.bucket_start) not in got or \
            undecided.bucket_start == row.bucket_start

        # ...and outside the recency bound the net lets go: it is a retry
        # net, not a standing rescan.
        later = now + dt.timedelta(hours=2)
        assert (TICKER, row.bucket_start) not in \
            journal.recent_decided_windows(later, minutes=1)


def test_distinct_voices_stops_counting_an_excluded_author(clean):
    with flask_app.app_context():
        event('zze-a', author='u1')
        event('zze-b', author='u2', flag=False)
        db.session.commit()

        since = WINDOW - dt.timedelta(hours=1)
        until = WINDOW + dt.timedelta(hours=1)
        voices = journal.distinct_voices([TICKER], ['bluesky'], since, until,
                                         'author')
        assert voices.get(TICKER, 0) == 1
