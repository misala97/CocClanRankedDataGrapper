"""Preflight every spike script runs first.

The prerequisites are the ones `perf1-bench/README.md` states: the fixture
database, its row count, and the buffer pool. A run that reports a smaller
pool is not evidence, so this refuses to continue rather than producing a
number nobody can trust.
"""
import os
import sys

import sqlalchemy as sa

DB = 'personal_apps_radar_perf1'
SPIKE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(SPIKE_DIR, '..', '..', 'personal_apps'))


def bootstrap():
    """Make `from app import app` work however the script was invoked.

    Python puts the SCRIPT's directory on sys.path, not the working directory,
    so running `python ../radar-design/perf2-spike/x.py` from `personal_apps/`
    cannot import the app without this.
    """
    for path in (SPIKE_DIR, APP_DIR):
        if path not in sys.path:
            sys.path.insert(0, path)
MIN_POOL_MB = 2000
TARGET_POOL_MB = 2560
# What models.py declares for radar_bucket_sources -- the deployed schema.
DEPLOYED_INDEXES = {'PRIMARY', 'ix_radar_bucket_sources_start',
                    'ix_radar_bucket_sources_coverage'}


def preflight(db, label=''):
    """Assert the database and pool, and return (db_name, pool_mb, rows)."""
    name = db.engine.url.database
    assert name == DB, 'wrong database: %s' % name
    pool = float(db.session.execute(
        sa.text('SELECT @@innodb_buffer_pool_size/1048576')).scalar())
    rows = db.session.execute(
        sa.text('SELECT COUNT(*) FROM radar_bucket_sources')).scalar()
    version = db.session.execute(sa.text('SELECT VERSION()')).scalar()
    # The fixture's STORAGE, not the branch's code. `codex/radar-perf2` does
    # not carry the held migration, but PERF1's `acceptance.py` builds
    # `ix_radar_bucket_sources_agg` physically and never drops it -- and it
    # was still there when this workstream started. Every build time taken
    # with it present is about 0.9 s optimistic. See `fixture_schema.py`.
    indexes = set(db.session.execute(sa.text(
        'SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS'
        ' WHERE TABLE_SCHEMA = :s AND TABLE_NAME = :t'),
        {'s': DB, 't': 'radar_bucket_sources'}).scalars().all())
    extra = sorted(indexes - DEPLOYED_INDEXES)
    print('=' * 72)
    if label:
        print('RUN: %s' % label)
    print('database:    %s' % name)
    print('engine:      %s   (the target runs MariaDB 10.11.14)' % version)
    print('buffer pool: %.0f MB   (target 2560 MB)' % pool)
    print('fixture:     %s radar_bucket_sources rows' % format(rows, ','))
    print('indexes:     %s%s'
          % ('deployed schema' if not extra else 'EXTRA: %s' % extra,
             '' if not extra else '  <-- NOT the deployed schema'))
    print('=' * 72, flush=True)
    assert not extra, (
        'radar_bucket_sources carries %s, which the target does not. Run '
        'perf2-spike/fixture_schema.py --fix. Every build time measured with '
        'the held index present is about 0.9 s optimistic.' % extra)
    assert pool >= MIN_POOL_MB, (
        'buffer pool is %.0f MB; at the local default of 128 every timing is '
        'disk-bound and every ratio is an artifact' % pool)
    return name, pool, rows


def fixture_sources(db):
    """The source names the FIXTURE holds, not config's.

    PERF1 retracted a whole round of evidence for asking config's real
    subreddit names of a fixture that stores placeholders: the `IN (...)`
    then matched 41% of the rows and every timing under it was wrong.
    """
    names = [r[0] for r in db.session.execute(sa.text(
        'SELECT DISTINCT source FROM radar_bucket_sources')).fetchall()]
    total = db.session.execute(
        sa.text('SELECT COUNT(*) FROM radar_bucket_sources')).scalar()
    covered = db.session.execute(
        sa.text('SELECT COUNT(*) FROM radar_bucket_sources'
                ' WHERE source IN :s').bindparams(
                    sa.bindparam('s', value=names, expanding=True))).scalar()
    assert covered == total, 'IN list covers %s of %s' % (covered, total)
    return sorted(names)
