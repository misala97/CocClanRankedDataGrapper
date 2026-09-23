"""The ingest-shaped write beside the producer: perf1's statement, this fixture.

The timed statement is `perf1-bench/write_cost.py`'s own, copied rather than
imported -- that helper binds `personal_apps_radar_perf1` and must never be
pointed at this database:

    UPDATE radar_bucket_sources SET mention_z = mention_z + :delta
     WHERE ticker = :t AND bucket_start = :at AND source = :s

executed for up to 20,000 rows that already exist and committed, which is the
write ingest performs (PERF1 retracted an earlier probe that INSERTed into an
empty partition and measured the cheapest pattern the index has).

Two deviations, both stated beside the numbers:

* Which hour. `write_cost.py` took the busiest hour. Every hour of this
  fixture holds exactly 16,792 rows, so "busiest" degenerates to "latest",
  and after alignment the latest hour is a future one that no board reads.
  The LIVE hour is used instead -- the newest bucket at or before the clock,
  the one ingest re-writes every cycle and every board window includes.
* The restore. `mention_z` is a FLOAT, and `+1.0` then `-1.0` is not an
  identity in single precision, so each run is restored by writing the
  original values back exactly (`SET mention_z = :orig`, same executemany
  shape). The restore is timed and reported apart; the write_cost number is
  the `+ :delta` UPDATE alone.

A separate OS process on purpose: executemany of an UPDATE is one round trip
per row driven from Python, and inside the measuring process it would share
the GIL with the samplers it is being compared against.

    <python 3.12> scratchpad/perf3/scale_env.py scratchpad/perf3/write_contention_perf3.py --offsets 0,0,0 [--out FILE]

`--offsets` are seconds after start at which each run begins (a run whose
offset has passed starts as soon as the previous one is done).
"""
import argparse
import json
import pathlib
import time

import sqlalchemy as sa

import scale_env

app = scale_env.bind()

from extensions import db  # noqa: E402

ROWS = 20_000
WRITE = sa.text(
    'UPDATE radar_bucket_sources SET mention_z = mention_z + :delta'
    ' WHERE ticker = :t AND bucket_start = :at AND source = :s')
RESTORE = sa.text(
    'UPDATE radar_bucket_sources SET mention_z = :orig'
    ' WHERE ticker = :t AND bucket_start = :at AND source = :s')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offsets', default='0,0,0')
    parser.add_argument('--out')
    args = parser.parse_args()
    offsets = [float(value) for value in args.offsets.split(',')]

    with app.app_context():
        now = scale_env.utcnow()
        at = db.session.execute(sa.text(
            'SELECT MAX(bucket_start) FROM radar_bucket_sources'
            ' WHERE bucket_start <= :now'), {'now': now}).scalar()
        rows = db.session.execute(sa.text(
            'SELECT ticker, source, mention_z FROM radar_bucket_sources'
            ' WHERE bucket_start = :at ORDER BY ticker, source LIMIT :rows'),
            {'at': at, 'rows': ROWS}).fetchall()
        db.session.commit()
        values = [{'t': t, 's': s, 'at': at} for t, s, _ in rows]
        originals = [{'t': t, 's': s, 'at': at, 'orig': z}
                     for t, s, z in rows]
        print('WRITE-PLAN ' + json.dumps({
            'live_hour': str(at), 'rows': len(values),
            'null_mention_z': sum(1 for *_, z in rows if z is None),
            'offsets': offsets}), flush=True)

        began = time.perf_counter()
        results = []
        for run, offset in enumerate(offsets, start=1):
            delay = began + offset - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            started_utc = scale_env.utcnow()
            t0 = time.perf_counter()
            db.session.execute(WRITE, [dict(v, delta=1.0) for v in values])
            db.session.commit()
            update_s = time.perf_counter() - t0
            t1 = time.perf_counter()
            db.session.execute(RESTORE, originals)
            db.session.commit()
            restore_s = time.perf_counter() - t1
            record = {'run': run, 'rows': len(values),
                      'started_utc': started_utc.isoformat(),
                      'ended_utc': scale_env.utcnow().isoformat(),
                      'update_s': round(update_s, 3),
                      'restore_s': round(restore_s, 3)}
            results.append(record)
            print('WRITE ' + json.dumps(record), flush=True)
        db.session.remove()
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(
            {'live_hour': str(at), 'runs': results}, indent=2),
            encoding='utf-8')
    print('WRITE-DONE', flush=True)


if __name__ == '__main__':
    main()
