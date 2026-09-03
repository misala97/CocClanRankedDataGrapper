"""The one-off backfill: day chunks, resume, and one real day through the
same intake the live cycle uses."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from features.radar import buckets
from features.radar.config import source_config_version
from models import RadarBucket, RadarBucketSource, RadarPost
from scripts import backfill_arctic_shift as backfill
from test_radar_arctic_shift import FakeClient, comment, submission   # tests/ is on sys.path

PREFIX = 'zzarcbf'
QUIET = 'zzarcquiet'
DAY = dt.datetime(2027, 1, 4)


@pytest.fixture()
def clean():
    def wipe():
        for name in (PREFIX, QUIET):
            RadarPost.query.filter(RadarPost.source == f'reddit:{name}').delete(
                synchronize_session=False)
            RadarBucketSource.query.filter(RadarBucketSource.source == f'reddit:{name}').delete(
                synchronize_session=False)
        db.session.commit()
    with flask_app.app_context():
        wipe()
        yield
        wipe()


def test_days_are_whole_utc_days_oldest_first():
    chunks = backfill.days(dt.datetime(2027, 1, 1, 15, 0), dt.datetime(2027, 1, 4, 10, 0))
    assert chunks[0] == (dt.datetime(2027, 1, 1), dt.datetime(2027, 1, 2))
    assert chunks[-1] == (dt.datetime(2027, 1, 4), dt.datetime(2027, 1, 4, 10, 0))
    assert len(chunks) == 4


def test_resume_skips_what_was_done(tmp_path):
    path = tmp_path / 'resume.json'
    done = backfill.load_resume(path)
    assert done == set()
    backfill.mark_done(path, '2027-01-01', 'zzarc')
    assert backfill.load_resume(path) == {('2027-01-01', 'zzarc')}


def _lookup():
    from features.radar import universe
    return universe.annotate_distinctive({'ZZTQ': {'name': 'Zztq Corp', 'exchange': 'Q'}})


def _day_client(when):
    return FakeClient({
        ('/comments/search', PREFIX): [[comment('c1', when, body='ZZTQ to the moon'),
                                        comment('c2', when + dt.timedelta(minutes=1),
                                                author='other', body='$ZZTQ again')], []],
        ('/posts/search', PREFIX): [[submission('p1', when, title='ZZTQ thesis')], []],
        ('/comments/search', QUIET): [[], []],
        ('/posts/search', QUIET): [[], []],
    }, parents={'t3_parent1': 'ZZTQ thread'})


def test_a_day_lands_as_posts_and_ok_children_for_every_sub_under_the_current_version(clean):
    """The whole day, all subs at once, one rollup with the full status
    map: the sub that spoke gets its counts, the sub that did not gets an
    explicit zero row -- the same rows a live cycle would have written."""
    when = DAY + dt.timedelta(hours=10, minutes=5)
    with flask_app.app_context():
        counts = backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                                  DAY + dt.timedelta(days=1), _lookup(), apply=True)

        assert counts['fetched'] == 3
        stored = RadarPost.query.filter_by(source=f'reddit:{PREFIX}').all()
        assert {p.external_id for p in stored} >= {'t1_c1', 't1_c2'}
        window = buckets.bucket_start_for(when)
        loud = RadarBucketSource.query.filter_by(
            source=f'reddit:{PREFIX}', ticker='ZZTQ', bucket_start=window).one()
        quiet = RadarBucketSource.query.filter_by(
            source=f'reddit:{QUIET}', ticker='ZZTQ', bucket_start=window).one()
        assert loud.status == 'ok' and loud.mention_count >= 2
        assert quiet.status == 'ok' and quiet.mention_count == 0
        assert loud.source_config_version == source_config_version()
        assert quiet.source_config_version == source_config_version()

        # Idempotent: the same day again stores nothing new.
        again = backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                                 DAY + dt.timedelta(days=1), _lookup(), apply=True)
        assert again['new_posts'] == 0
        assert RadarPost.query.filter_by(source=f'reddit:{PREFIX}').count() == len(stored)


def test_an_existing_parent_bucket_is_left_alone(clean):
    """The journal keeps 48 h. Rebuilding an old window's parent from it
    would erase Bluesky's and 4chan's totals; the backfill writes children
    and leaves an existing parent exactly as it was."""
    when = DAY + dt.timedelta(hours=10, minutes=5)
    window = buckets.bucket_start_for(when)
    with flask_app.app_context():
        RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
        # source_config_version is NOT NULL: a parent another source built
        # carries the stamp of the run that built it.
        db.session.add(RadarBucket(ticker='ZZTQ', bucket_start=window, mention_count=7,
                                   high_confidence_count=7, low_count=0, distinct_authors=5,
                                   sources_ok=2,
                                   source_config_version=source_config_version()))
        db.session.commit()
        try:
            backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                             DAY + dt.timedelta(days=1), _lookup(), apply=True)

            parent = RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).one()
            assert parent.mention_count == 7 and parent.distinct_authors == 5
            assert RadarBucketSource.query.filter_by(
                source=f'reddit:{PREFIX}', ticker='ZZTQ', bucket_start=window).one().mention_count >= 2
        finally:
            RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
            db.session.commit()


def test_a_parent_that_did_not_exist_is_created_from_the_day(clean):
    when = DAY + dt.timedelta(hours=10, minutes=5)
    window = buckets.bucket_start_for(when)
    with flask_app.app_context():
        RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
        db.session.commit()
        try:
            backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                             DAY + dt.timedelta(days=1), _lookup(), apply=True)
            parent = RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).one()
            assert parent.mention_count >= 2
        finally:
            RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
            db.session.commit()


def test_a_dry_run_counts_and_stores_nothing(clean):
    when = DAY + dt.timedelta(hours=10)
    with flask_app.app_context():
        counts = backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                                  DAY + dt.timedelta(days=1), _lookup(), apply=False)
        assert counts['fetched'] == 3
        assert RadarPost.query.filter_by(source=f'reddit:{PREFIX}').count() == 0


def test_apply_refuses_while_the_daemon_runs(monkeypatch, capsys):
    monkeypatch.setattr(backfill, 'daemon_is_active', lambda: True)
    assert backfill.main(['--apply', '--days', '1', '--subs', PREFIX]) == 2
    assert 'radar_ingest is running' in capsys.readouterr().err
