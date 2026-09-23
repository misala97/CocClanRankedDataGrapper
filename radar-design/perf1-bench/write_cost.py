"""What the new index costs the writers, measured on the write they perform.

The acceptance battery's probe INSERTed 20,000 rows at a bucket_start that
did not exist, so every key was new and every secondary-index entry was a
sequential append at the right edge of a bucket_start-leading B-tree -- the
cheapest pattern this index has. It claimed to collide "the way ingest's
ON DUPLICATE KEY UPDATE does" and did not: every fixture row sits on an exact
hour and the probe wrote at :30.

The real writers UPDATE columns this index carries. `scoring.py` bulk-updates
expected, variance, mention_z and baseline_days; `buckets.py` re-sets
mention_count, distinct_authors, distinct_text_ratio and status on the live
bucket every cycle. All eight are in ix_radar_bucket_sources_agg, so each one
delete-marks and re-inserts a secondary-index entry rather than appending.

So: update an indexed column on 20,000 rows that already exist, in the live
partition, and put it back afterwards. Read-modify-restore, no net change.
"""
import argparse
import time

import sqlalchemy as sa

from app import app
from extensions import db

DB = 'personal_apps_radar_perf1'
INDEX = 'ix_radar_bucket_sources_agg'
ROWS = 20_000


def has_index():
    return db.session.execute(sa.text(
        'SELECT COUNT(*) FROM information_schema.STATISTICS'
        ' WHERE TABLE_SCHEMA=:s AND TABLE_NAME=:t AND INDEX_NAME=:n'),
        {'s': DB, 't': 'radar_bucket_sources', 'n': INDEX}).scalar() > 0


def busiest_hour():
    """A bucket_start that really exists, with enough rows on it."""
    row = db.session.execute(sa.text(
        'SELECT bucket_start, COUNT(*) FROM radar_bucket_sources'
        ' GROUP BY bucket_start ORDER BY COUNT(*) DESC, bucket_start DESC'
        ' LIMIT 1')).first()
    return row[0], row[1]


def measure(at):
    keys = db.session.execute(sa.text(
        'SELECT ticker, source FROM radar_bucket_sources'
        ' WHERE bucket_start = :at ORDER BY ticker, source LIMIT :rows'),
        {'at': at, 'rows': ROWS}).fetchall()
    values = [{'t': t, 's': s, 'at': at} for t, s in keys]
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='')
    args = parser.parse_args()
    with app.app_context():
        assert db.engine.url.database == DB, db.engine.url.database
        pool = db.session.execute(
            sa.text('SELECT @@innodb_buffer_pool_size/1048576')).scalar()
        assert pool >= 2000, 'buffer pool is %s MB, the target runs 2500' % pool
        at, on_hour = busiest_hour()
        print('database: %s   pool: %.0f MB   index: %s'
              % (DB, pool, 'present' if has_index() else 'ABSENT'))
        print('updating an indexed column on rows that already exist,'
              ' bucket_start = %s (%s rows on that hour)'
              % (at, format(on_hour, ',')))
        for run in range(3):
            took, count = measure(at)
            print('  run %d: %s rows  %.2fs' % (run + 1, format(count, ','),
                                                took), flush=True)


if __name__ == '__main__':
    main()
