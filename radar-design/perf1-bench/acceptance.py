"""P2 acceptance: the whole board, before and after, on the same data.

What the brief asks for: at least twenty serial samples per critical 12h/24h
case with median, p95 and maximum; two simultaneous readers; rapid filter
changes; and cold told apart from warm.

Corrections carried in from the independent review, each of which invalidated
an earlier version of this evidence:

  * the source list comes from the FIXTURE, so `source IN (...)` matches every
    row -- the earlier run asked for config's real subreddit names against a
    fixture that stored placeholders, and so aggregated 41% of the rows;
  * the buffer pool is raised to the target's 2500 MB, because at the local
    default of 128 MB against a 1798 MB table every baseline run was
    disk-bound and the resulting ratio was an artifact;
  * the write test writes into the LIVE partition, with keys that collide the
    way ingest's ON DUPLICATE KEY UPDATE does -- the earlier one wrote 400
    days ahead into an empty partition, where a partition-local index has no
    rows to split;
  * index size is measured before AND after, after ANALYZE TABLE, because
    INDEX_LENGTH is otherwise served from stale persistent statistics;
  * payload parity is hashed here rather than asserted in prose.

Read-only against the synthetic fixture apart from the index build, the write
probe (which cleans up after itself) and ANALYZE. Nothing touches the target.
"""
import datetime as dt
import hashlib
import json
import statistics
import threading
import time

import sqlalchemy as sa

from app import app
from extensions import db
from features.radar import board as board_mod
from features.radar.routes import api as api_mod

DB = 'personal_apps_radar_perf1'
INDEX = 'ix_radar_bucket_sources_agg'
COLUMNS = ('bucket_start, source, ticker, mention_z, mention_count, expected, '
           'variance, distinct_authors, distinct_text_ratio, baseline_days, '
           'status')
SAMPLES = 20
CRITICAL = (12, 24)
ABORT = 8.0          # static/radar/src/api.ts, TIMEOUT_MS

SOURCES = []         # filled from the fixture in main()


def build(query, hours, now, **over):
    # segments=() is "All companies", the case the owner reports and the brief
    # names as critical -- NOT parse_query's default, which is a four-segment
    # filter. market is pinned rather than taken from the default, which is
    # 'de' or 'us' depending on the hour the run happens to start.
    kwargs = dict(window_hours=hours, segments=(),
                  limit=query.limit, min_venues=query.min_venues,
                  market='us', sort=query.sort, direction=query.direction)
    kwargs.update(over)
    return board_mod.build(SOURCES, now, **kwargs)


def digest(board):
    """The payload the island would receive, hashed."""
    return hashlib.sha256(json.dumps(
        api_mod.serialize(board), sort_keys=True, default=str
    ).encode()).hexdigest()[:16]


def index_mb():
    db.session.execute(sa.text('ANALYZE TABLE radar_bucket_sources'))
    db.session.commit()
    return db.session.execute(sa.text(
        'SELECT ROUND(SUM(stat_value * @@innodb_page_size) / 1048576)'
        ' FROM mysql.innodb_index_stats'
        " WHERE database_name=:db AND table_name LIKE 'radar_bucket_sources%'"
        " AND stat_name='size' AND index_name <> 'PRIMARY'"),
        {'db': DB}).scalar()


def has_index():
    return db.session.execute(sa.text(
        'SELECT COUNT(*) FROM information_schema.STATISTICS'
        ' WHERE TABLE_SCHEMA=:s AND TABLE_NAME=:t AND INDEX_NAME=:n'),
        {'s': DB, 't': 'radar_bucket_sources', 'n': INDEX}).scalar() > 0


def stats(took):
    ordered = sorted(took)
    return (statistics.median(ordered),
            ordered[max(0, round(0.95 * len(ordered)) - 1)],
            ordered[-1])


def serial(query, hours, now):
    """The first build is reported apart: it is the cache-miss reader, the one
    who was watching the eight-second abort fire."""
    t0 = time.perf_counter()
    board = build(query, hours, now)
    cold = time.perf_counter() - t0
    took = []
    for _ in range(SAMPLES):
        t0 = time.perf_counter()
        board = build(query, hours, now)
        took.append(time.perf_counter() - t0)
    median, p95, worst = stats(took)
    print('  %2dh  process-cold %5.2fs |  n=%d  median %5.2fs  p95 %5.2fs'
          '  max %5.2fs  rows %d'
          % (hours, cold, SAMPLES, median, p95, worst, len(board.rows)),
          flush=True)
    return max(worst, cold)


def concurrent(query, hours, now):
    took = {}
    ready = threading.Barrier(2)

    def reader(name):
        with app.app_context():
            ready.wait()
            t0 = time.perf_counter()
            build(query, hours, now)
            took[name] = time.perf_counter() - t0
            db.session.remove()

    threads = [threading.Thread(target=reader, args=(n,)) for n in 'AB']
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print('  %2dh  two readers at once:  A %5.2fs   B %5.2fs'
          % (hours, took['A'], took['B']), flush=True)
    return max(took.values())


def concurrent_via_endpoint(query, hours, now):
    """Two readers through the REAL cache path, not straight into the build.

    `board_mod.build` is what `concurrent` above times, and it is what the two
    readers were each doing twice over. This goes through `_build_board`,
    where the single-flight lives, so the pair is measured the way the
    endpoint actually serves it.
    """
    api_mod.board_cache.clear()
    api_mod._board_builds.clear()
    asked = api_mod.Query(sources=SOURCES, segments=(), window=hours,
                          limit=query.limit, min_venues=query.min_venues,
                          market='us', sort=query.sort,
                          direction=query.direction)
    took = {}
    ready = threading.Barrier(2)

    def reader(name):
        with app.app_context():
            ready.wait()
            t0 = time.perf_counter()
            api_mod._build_board(asked, now)
            took[name] = time.perf_counter() - t0
            db.session.remove()

    threads = [threading.Thread(target=reader, args=(n,)) for n in 'AB']
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    builds = 'coalesced' if abs(took['A'] - took['B']) < 0.35 else 'separate'
    print('  %2dh  two readers through the cache path:  A %5.2fs   B %5.2fs'
          '   (%s)' % (hours, took['A'], took['B'], builds), flush=True)
    return max(took.values())


def churn(query, now):
    steps = [('24h all', 24, {}),
             ('24h by mention_z', 24, {'sort': 'mention_z'}),
             ('12h all', 12, {}),
             ('12h discover', 12, {'segments': ['discover']}),
             ('24h all, German board', 24, {'market': 'de'}),
             ('4h all', 4, {}),
             ('24h venues>=2', 24, {'min_venues': 2})]
    began = time.perf_counter()
    worst = 0.0
    for label, hours, over in steps:
        t0 = time.perf_counter()
        build(query, hours, now, **over)
        took = time.perf_counter() - t0
        worst = max(worst, took)
        print('    %-18s %5.2fs' % (label, took), flush=True)
    print('  six filter changes back to back: %5.2fs   worst single %5.2fs'
          % (time.perf_counter() - began, worst), flush=True)
    return worst


def battery(label, query, now):
    print('\n=== %s ===' % label, flush=True)
    worst = 0.0
    for hours in CRITICAL:
        worst = max(worst, serial(query, hours, now))
    for hours in CRITICAL:
        worst = max(worst, concurrent(query, hours, now))
    for hours in CRITICAL:
        worst = max(worst, concurrent_via_endpoint(query, hours, now))
    worst = max(worst, churn(query, now))
    print('  WORST ANYTHING: %5.2fs   (client aborts at %.2fs)'
          % (worst, ABORT), flush=True)
    return worst


def write_cost(label, now):
    """One ingest-shaped batch into the LIVE partition, on keys that are
    already there -- which is what ingest actually does."""
    at = (now - dt.timedelta(minutes=30)).replace(second=0, microsecond=0)
    rows = db.session.execute(sa.text(
        'SELECT ticker, source FROM radar_bucket_sources'
        ' WHERE bucket_start >= :since ORDER BY ticker LIMIT 20000'),
        {'since': now - dt.timedelta(hours=6)}).fetchall()
    values = [{'t': ticker, 's': source, 'at': at} for ticker, source in rows]
    t0 = time.perf_counter()
    db.session.execute(sa.text("""
        INSERT INTO radar_bucket_sources
            (ticker, bucket_start, source, mention_count,
             high_confidence_count, low_count, distinct_authors,
             distinct_text_ratio, engagement_weighted_count, status, expected,
             variance, mention_z, baseline_days, source_config_version)
        VALUES (:t, :at, :s, 3, 2, 0, 2, 0.5, 3.0, 'ok', 1.0, 0.5, 1.5, 30,
                'v1')
        ON DUPLICATE KEY UPDATE mention_count = VALUES(mention_count)
    """), values)
    db.session.commit()
    took = time.perf_counter() - t0
    db.session.execute(sa.text(
        'DELETE FROM radar_bucket_sources WHERE bucket_start = :at'),
        {'at': at})
    db.session.commit()
    print('  write %s bucket rows into the live partition %s: %.2fs'
          % (format(len(values), ','), label, took), flush=True)
    return took


def main():
    global SOURCES
    with app.app_context():
        assert db.engine.url.database == DB, db.engine.url.database
        pool = db.session.execute(
            sa.text('SELECT @@innodb_buffer_pool_size/1048576')).scalar()
        print('database: %s - verified' % DB)
        print('buffer pool: %.0f MB   (target runs 2500 MB)' % pool)
        assert pool >= 2000, (
            'buffer pool is %s MB; the target runs 2500 and at the local '
            'default of 128 every baseline is disk-bound' % pool)

        SOURCES = [r[0] for r in db.session.execute(sa.text(
            'SELECT DISTINCT source FROM radar_bucket_sources')).fetchall()]
        total = db.session.execute(
            sa.text('SELECT COUNT(*) FROM radar_bucket_sources')).scalar()
        covered = db.session.execute(
            sa.text('SELECT COUNT(*) FROM radar_bucket_sources'
                    ' WHERE source IN :s').bindparams(
                        sa.bindparam('s', value=SOURCES,
                                     expanding=True))).scalar()
        assert covered == total, 'IN list covers %s of %s' % (covered, total)
        print('sources: %d names covering all %s rows'
              % (len(SOURCES), format(total, ',')))

        now = dt.datetime.utcnow().replace(microsecond=0)
        query = api_mod.parse_query({}, now=now)
        print('measuring: segments=() All companies, market=us, limit=%d'
              % query.limit)
        print('  (parse_query default for contrast: segments=%s market=%s'
              ' window=%dh)' % (query.segments, query.market, query.window),
              flush=True)

        if has_index():
            db.session.execute(sa.text(
                'ALTER TABLE radar_bucket_sources DROP INDEX %s,'
                ' ALGORITHM=INPLACE, LOCK=NONE' % INDEX))
            db.session.commit()
        size_before = index_mb()
        print('secondary index bytes, baseline: %s MB' % size_before,
              flush=True)

        before_digests = {h: digest(build(query, h, now)) for h in (4, 12, 24)}
        before = battery('BEFORE - the indexes the target has', query, now)
        before_write = write_cost('BEFORE', now)

        print('\nbuilding %s with the migration statement...' % INDEX,
              flush=True)
        t0 = time.perf_counter()
        db.session.execute(sa.text(
            'ALTER TABLE radar_bucket_sources ADD INDEX %s (%s),'
            ' ALGORITHM=INPLACE, LOCK=NONE' % (INDEX, COLUMNS)))
        db.session.commit()
        print('  built in %.0fs, online' % (time.perf_counter() - t0),
              flush=True)
        size_after = index_mb()
        print('secondary index bytes: %s MB -> %s MB   (adds %s MB)'
              % (size_before, size_after, size_after - size_before), flush=True)

        after_digests = {h: digest(build(query, h, now)) for h in (4, 12, 24)}
        after = battery('AFTER - one covering index', query, now)
        after_write = write_cost('AFTER', now)

        print('\npayload parity, the serialized board hashed:')
        for hours in (4, 12, 24):
            same = before_digests[hours] == after_digests[hours]
            print('  %2dh  %s -> %s   %s'
                  % (hours, before_digests[hours], after_digests[hours],
                     'IDENTICAL' if same else 'DIFFERS'))
        parity = before_digests == after_digests

        print('\nwrite cost: %.2fs -> %.2fs' % (before_write, after_write))
        print('worst case anywhere: %.2fs -> %.2fs' % (before, after))
        print('PARITY OK' if parity else 'PARITY BROKEN - the board changed')
        print('UNDER THE ABORT' if after < ABORT else 'STILL OVER THE ABORT')


if __name__ == '__main__':
    main()
