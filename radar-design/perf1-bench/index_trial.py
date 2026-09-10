"""Measure the candidate fixes for the pass-one aggregate, against each other.

Runs on the production-scale local copy only. Nothing here touches the target,
and the target's schema is not modified by this brief.

Each candidate is timed cold-ish (the buffer pool is warmed identically by a
discard run first) over N serial samples, and its EXPLAIN is captured, so the
return can say WHY as well as how fast.
"""
import datetime as dt
import statistics
import sys
import time

import sqlalchemy as sa

from app import app
from extensions import db

WINDOWS = (4, 12, 24)
SAMPLES = 5          # raised for the acceptance run; 5 is enough to compare

AGGREGATE = """
SELECT ticker, source, SUM(mention_count), SUM(COALESCE(expected, 0)),
       SUM(COALESCE(variance, 0)), MAX(distinct_authors),
       MIN(distinct_text_ratio), MIN(baseline_days),
       MAX(CASE WHEN status = 'truncated' THEN 1 ELSE 0 END)
FROM radar_bucket_sources
WHERE bucket_start >= :since AND bucket_start < :now
  AND mention_z IS NOT NULL
GROUP BY ticker, source
"""

# Every column the aggregate reads, in an order that serves the range filter
# first and then carries the rest as payload.
COVERING = """
CREATE INDEX ix_perf_cover ON radar_bucket_sources
    (bucket_start, source, ticker, mention_z, mention_count, expected,
     variance, distinct_authors, distinct_text_ratio, baseline_days, status)
"""

# The same idea with the GROUP BY's own columns leading, so the group needs
# no temporary table -- at the cost of the range no longer leading.
GROUPED = """
CREATE INDEX ix_perf_group ON radar_bucket_sources
    (ticker, source, bucket_start, mention_z, mention_count, expected,
     variance, distinct_authors, distinct_text_ratio, baseline_days, status)
"""


def time_it(now, hours, samples=SAMPLES):
    since = now - dt.timedelta(hours=hours)
    params = {'since': since, 'now': now}
    db.session.execute(sa.text(AGGREGATE), params).fetchall()   # warm
    took = []
    for _ in range(samples):
        began = time.perf_counter()
        rows = db.session.execute(sa.text(AGGREGATE), params).fetchall()
        took.append(time.perf_counter() - began)
    return took, len(rows)


def explain(now, hours):
    since = now - dt.timedelta(hours=hours)
    row = db.session.execute(
        sa.text('EXPLAIN ' + AGGREGATE),
        {'since': since, 'now': now}).first()
    return f'type={row[3]} key={row[5]} rows={row[8]} extra={row[10]}'


def report(label, now):
    print(f'\n=== {label} ===')
    for hours in WINDOWS:
        took, groups = time_it(now, hours)
        print(f'  {hours:>2}h  median {statistics.median(took):6.3f}s'
              f'  min {min(took):6.3f}s  max {max(took):6.3f}s'
              f'  groups {groups:,}')
        print(f'       {explain(now, hours)}')


def main():
    with app.app_context():
        name = db.engine.url.database
        assert name == 'personal_apps_radar_perf1', f'WRONG DATABASE: {name}'
        print('database:', name)
        total = db.session.execute(
            sa.text('SELECT COUNT(*) FROM radar_bucket_sources')).scalar()
        day = db.session.execute(sa.text(
            'SELECT COUNT(*) FROM radar_bucket_sources'
            ' WHERE bucket_start >= NOW() - INTERVAL 24 HOUR')).scalar()
        print(f'bucket_sources: {total:,} total, {day:,} in 24h')
        print('target:         9,333,403 total,  405,582 in 24h')

        now = dt.datetime.utcnow().replace(microsecond=0)

        # MySQL 8 has no DROP INDEX IF EXISTS.
        for name_ in ('ix_perf_cover', 'ix_perf_group'):
            try:
                db.session.execute(
                    sa.text(f'DROP INDEX {name_} ON radar_bucket_sources'))
                db.session.commit()
            except Exception:
                db.session.rollback()

        report('BASELINE - the indexes the target has', now)

        if '--baseline-only' in sys.argv:
            return

        print('\nbuilding covering index...')
        began = time.perf_counter()
        db.session.execute(sa.text(COVERING))
        db.session.commit()
        print(f'  built in {time.perf_counter() - began:.0f}s')
        report('CANDIDATE A - covering, range-leading', now)

        print('\nbuilding group-leading index...')
        began = time.perf_counter()
        db.session.execute(sa.text(GROUPED))
        db.session.commit()
        print(f'  built in {time.perf_counter() - began:.0f}s')
        report('CANDIDATE B - covering, group-leading (both present)', now)

        db.session.execute(sa.text('DROP INDEX ix_perf_cover'
                                   ' ON radar_bucket_sources'))
        db.session.commit()
        report('CANDIDATE B alone', now)


if __name__ == '__main__':
    main()
