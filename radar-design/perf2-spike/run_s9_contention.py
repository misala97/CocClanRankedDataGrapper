"""Task S9: what a producer sweep does to the write path.

The write is `perf1-bench/write_cost.py`'s, unchanged in shape: one bulk
UPDATE of an indexed column across rows that already exist in the live
partition, restored afterwards. That is the write ingest actually performs --
PERF1 retracted an earlier probe that INSERTed into an empty partition and
measured the cheapest pattern the index has.

The producer runs as a SEPARATE OS PROCESS, because a thread in this
interpreter would contend for the GIL rather than for the database, and the
question is about the database.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s9_contention.py
"""
import datetime as dt
import os
import statistics
import subprocess
import sys
import time

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import producer                                        # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import APP_DIR, SPIKE_DIR               # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402

ROWS = 20_000
RUNS = 3


def busiest_hour(db):
    row = db.session.execute(sa.text(
        'SELECT bucket_start, COUNT(*) FROM radar_bucket_sources'
        ' GROUP BY bucket_start ORDER BY COUNT(*) DESC, bucket_start DESC'
        ' LIMIT 1')).first()
    return row[0], row[1]


def write_once(db, at):
    """One ingest-shaped bulk UPDATE, restored. Returns (seconds, rows)."""
    rows = db.session.execute(sa.text(
        'SELECT ticker, source FROM radar_bucket_sources'
        ' WHERE bucket_start = :at ORDER BY ticker, source LIMIT :rows'),
        {'at': at, 'rows': ROWS}).fetchall()
    values = [{'t': t, 's': s, 'at': at} for t, s in rows]
    statement = sa.text(
        'UPDATE radar_bucket_sources SET mention_z = mention_z + :delta'
        ' WHERE ticker = :t AND bucket_start = :at AND source = :s')
    began = time.perf_counter()
    db.session.execute(statement, [dict(v, delta=1.0) for v in values])
    db.session.commit()
    took = time.perf_counter() - began
    db.session.execute(statement, [dict(v, delta=-1.0) for v in values])
    db.session.commit()
    return took, len(values)


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        preflight(db, 'S9 -- what the producer does to the write path')
        engine = db.engine
        sources = fixture_sources(db)
        now = selections.fixed_now()
        at, on_hour = busiest_hour(db)
        index_present = db.session.execute(sa.text(
            'SELECT COUNT(*) FROM information_schema.STATISTICS'
            ' WHERE TABLE_SCHEMA=:s AND TABLE_NAME=:t AND INDEX_NAME=:n'),
            {'s': 'personal_apps_radar_perf1',
             't': 'radar_bucket_sources',
             'n': 'ix_radar_bucket_sources_agg'}).scalar() > 0
        print('held index ix_radar_bucket_sources_agg: %s   (it must be'
              ' ABSENT -- this branch does not carry it)'
              % ('PRESENT' if index_present else 'absent'))
        assert not index_present, 'the held index is on this database'
        print('write: bulk UPDATE of mention_z on up to %s existing rows at'
              ' bucket_start=%s (%s rows on that hour), restored afterwards'
              % (format(ROWS, ','), at, format(on_hour, ',')))

        # ---- Step 1: baseline --------------------------------------------
        print('\n--- Step 1: the write with no producer running ---')
        baseline = []
        for run in range(RUNS):
            took, count = write_once(db, at)
            baseline.append(took)
            print('  run %d: %s rows  %.2f s' % (run + 1, format(count, ','),
                                                 took), flush=True)
        base_median = statistics.median(baseline)
        print('  BASELINE median: %.2f s' % base_median)

        # ---- Step 2: the same write under a producer sweep ---------------
        print('\n--- Step 2: the same write under a producer sweep ---')
        store.drop_table(engine)
        store.create_table(engine)
        warm = selections.warm_set(Query, sources)
        for query in warm:
            key_hash, key_json = keys.canonical(query)
            store.enqueue(engine, key_hash, key_json, now, warm=True)
        # Warm the pages first: a cold first sweep would be measuring page
        # faults, not contention (S3 measured 93 s cold against 59 s warm).
        print('  warming the producer\'s pages first (one full sweep)...',
              flush=True)
        pre = time.perf_counter()
        while producer.serve_once(engine, 'prewarm', now,
                                  query_cls=Query) is not None:
            pass
        print('  prewarm sweep: %.1f s' % (time.perf_counter() - pre))

        for query in warm:
            key_hash, key_json = keys.canonical(query)
            store.enqueue(engine, key_hash, key_json, now, warm=True)
        sweeper = subprocess.Popen(
            [sys.executable, os.path.join(SPIKE_DIR, 'producer.py'),
             '--owner', 'sweeper', '--now', now.isoformat(),
             '--poll', '400', '--poll-interval', '0.05'],
            cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        assert sweeper.stdout.readline().strip() == 'READY'
        sweep_began = time.perf_counter()
        under = []
        try:
            for run in range(RUNS):
                took, count = write_once(db, at)
                under.append(took)
                print('  run %d: %s rows  %.2f s' % (run + 1,
                                                     format(count, ','), took),
                      flush=True)
        finally:
            # How far the sweep got while the writes were running.
            with engine.connect() as conn:
                still_queued = conn.execute(sa.text(
                    "SELECT COUNT(*) FROM radar_board_results"
                    " WHERE state IN ('pending','building')")).scalar()
            sweeper.kill()
            out, err = sweeper.communicate()
        served = len([x for x in out.splitlines() if x.startswith('SERVED')])
        elapsed = time.perf_counter() - sweep_began
        under_median = statistics.median(under)
        print('  UNDER-SWEEP median: %.2f s' % under_median)
        print('  the sweep meanwhile: %d of %d keys built in %.1f s'
              ' (%d still queued when the writes finished)'
              % (served, len(warm), elapsed, still_queued))

        # ---- Step 3: the ruling ------------------------------------------
        print('\n--- Step 3: the ruling on the host ---')
        delta = (under_median / base_median - 1) * 100
        print('  write, alone      : %.2f s' % base_median)
        print('  write, under sweep: %.2f s   (%+.0f%%)'
              % (under_median, delta))
        sweep_alone_per_key = 65.8 / 16   # S3's median warm sweep on
        #                                  the DEPLOYED schema
        per_key_under = elapsed / served if served else float('nan')
        print('  producer, alone   : %.1f s per key (S3 median sweep 58.9 s'
              ' / 16 keys)' % sweep_alone_per_key)
        print('  producer, under writes: %.1f s per key   (%+.0f%%)'
              % (per_key_under,
                 (per_key_under / sweep_alone_per_key - 1) * 100))
        print()
        if delta > 15:
            print('  RULING: the producer measurably delays the write path'
                  ' (%+.0f%%). The ingest daemon is the WRONG host and the'
                  ' producer needs its own unit.' % delta)
        else:
            print('  RULING: the producer does not measurably delay the write'
                  ' path (%+.0f%%, inside run-to-run variance for this'
                  ' write). The ingest daemon is not ruled OUT by this'
                  ' measurement.' % delta)
        print('  The engine is MySQL 8.0.46. The target is MariaDB 10.11.14,'
              ' and this box is not running the real ingest cycle beside it.')
        print('  What is NOT measured here: APScheduler overlap behaviour in'
              ' run_radar_ingest.py, the scoring pass, retention/partition'
              ' maintenance, or the Reddit fetch loop. Codex\'s ruling asks'
              ' for the daemon\'s EXECUTION and OVERLAP behaviour to be'
              ' checked before multi-second work goes into its scheduler;'
              ' that is a code question about the daemon, answered below.')

        # ---- What the daemon's scheduler actually does -------------------
        print('\n--- the ingest daemon\'s scheduler, read rather than'
              ' guessed ---')
        import re
        source = open(os.path.join(APP_DIR, 'run_radar_ingest.py'),
                      encoding='utf-8').read()
        adds = re.findall(r'add_job\((.{0,220})', source, re.S)
        print('  %d add_job calls in run_radar_ingest.py' % len(adds))
        for kw in ('max_instances', 'coalesce', 'misfire_grace_time',
                   'BackgroundScheduler', 'BlockingScheduler',
                   'ThreadPoolExecutor', 'ProcessPoolExecutor',
                   'executors='):
            hits = len(re.findall(re.escape(kw), source))
            print('    %-22s %d occurrence(s)' % (kw, hits))
        values = set(re.findall(r'max_instances\s*=\s*(\d+)', source))
        print('    every max_instances value in the file: %s'
              % ', '.join(sorted(values)))
        print('    scheduler: %s'
              % (re.search(r'BackgroundScheduler\([^)]*\)', source).group(0)))
        print("    no `executors=` argument, so APScheduler's DEFAULT"
              ' thread pool runs every job. A multi-second producer job'
              ' would sit in that pool beside the other %d.' % len(adds))


if __name__ == '__main__':
    main()
