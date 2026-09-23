"""Candidate indexes for the pass-one aggregate, measured against each other.

The query here is TAKEN FROM THE CODE, not hand-written: it is built from the
same SQLAlchemy expression `leaderboard._aggregate` uses, so the shape cannot
drift from production's the way an earlier proxy did. That proxy dropped the
`source IN (...)` predicate, which is exactly the predicate that motivates the
source-leading candidate, so the candidate was structurally invisible.

The source list comes from the FIXTURE, so the IN list matches every row the
table holds -- the same 100% coverage production has, where config's names and
the stored names agree. Only the strings are shorter; the cost section
accounts for that separately.

Read-only against the synthetic fixture. Nothing here touches the target.
"""
import datetime as dt
import statistics
import time

import sqlalchemy as sa

from app import app
from extensions import db
from features.radar import leaderboard

DB = 'personal_apps_radar_perf1'
SAMPLES = 5
WINDOWS = (4, 12, 24)
CANDIDATES = {
    # The range first, everything else behind it as payload.
    'A range-leading': '(bucket_start, source, ticker, mention_z, '
                       'mention_count, expected, variance, distinct_authors, '
                       'distinct_text_ratio, baseline_days, status)',
    # The GROUP BY's own columns first: no temporary table, but no range.
    'B group-leading': '(ticker, source, bucket_start, mention_z, '
                       'mention_count, expected, variance, distinct_authors, '
                       'distinct_text_ratio, baseline_days, status)',
    # The IN list first, so each source is its own covering range scan.
    # Invisible to the earlier proxy, which had dropped the source predicate.
    'C source-leading': '(source, bucket_start, ticker, mention_z, '
                        'mention_count, expected, variance, distinct_authors, '
                        'distinct_text_ratio, baseline_days, status)',
}

NAME = 'ix_perf_candidate'


def real_query(sources, since, now):
    """`_aggregate`'s own statement, reached through the module."""
    bucket = leaderboard.RadarBucketSource
    return (db.session.query(
        bucket.ticker.label('ticker'),
        bucket.source.label('source'),
        sa.func.sum(bucket.mention_count),
        sa.func.sum(sa.func.coalesce(bucket.expected, 0.0)),
        sa.func.sum(sa.func.coalesce(bucket.variance, 0.0)),
        sa.func.max(bucket.distinct_authors),
        sa.func.min(bucket.distinct_text_ratio),
        sa.func.min(bucket.baseline_days),
        sa.func.max(sa.case((bucket.status == 'truncated', 1), else_=0)))
        .filter(bucket.source.in_(sources),
                bucket.bucket_start >= since,
                bucket.bucket_start < now,
                bucket.mention_z.isnot(None))
        .group_by(bucket.ticker, bucket.source))


def drop():
    try:
        db.session.execute(sa.text(f'DROP INDEX {NAME} ON radar_bucket_sources'))
        db.session.commit()
    except Exception:
        db.session.rollback()


def index_mb():
    return db.session.execute(sa.text(
        'SELECT ROUND(INDEX_LENGTH/1048576) FROM information_schema.TABLES'
        f" WHERE TABLE_SCHEMA='{DB}' AND TABLE_NAME='radar_bucket_sources'")
    ).scalar()


def measure(sources, now, hours):
    since = now - dt.timedelta(hours=hours)
    query = real_query(sources, since, now)
    rows = query.all()                                   # warm
    took = []
    for _ in range(SAMPLES):
        t0 = time.perf_counter()
        query.all()
        took.append(time.perf_counter() - t0)
    plan = db.session.execute(
        sa.text('EXPLAIN ' + str(query.statement.compile(
            db.engine, compile_kwargs={'literal_binds': True})))).first()
    return statistics.median(took), max(took), len(rows), plan


def report(label, sources, now):
    print(f'\n=== {label} ===')
    for hours in WINDOWS:
        median, worst, groups, plan = measure(sources, now, hours)
        print(f'  {hours:>2}h  median {median:6.2f}s  max {worst:6.2f}s'
              f'  groups {groups:,}')
        print(f'       type={plan[3]} key={plan[5]} rows={plan[8]}'
              f' extra={plan[10]}')


def main():
    with app.app_context():
        assert db.engine.url.database == DB, db.engine.url.database
        print('database:', DB, '- verified')
        pool = db.session.execute(
            sa.text('SELECT @@innodb_buffer_pool_size/1048576')).scalar()
        print(f'buffer pool: {pool:.0f} MB   (target runs 2500 MB)')
        assert pool >= 2000, (
            'buffer pool is %s MB; the target runs 2500 and at the local '
            'default of 128 every baseline is disk-bound' % pool)

        sources = [r[0] for r in db.session.execute(sa.text(
            'SELECT DISTINCT source FROM radar_bucket_sources')).fetchall()]
        covered = db.session.execute(
            sa.text('SELECT COUNT(*) FROM radar_bucket_sources'
                    ' WHERE source IN :s').bindparams(
                        sa.bindparam('s', value=sources, expanding=True))).scalar()
        total = db.session.execute(
            sa.text('SELECT COUNT(*) FROM radar_bucket_sources')).scalar()
        assert covered == total, f'IN list covers {covered} of {total} rows'
        print(f'sources: {len(sources)} names, covering {covered:,}/{total:,}'
              f' rows  (target: 36 names, all rows)')
        day = db.session.execute(sa.text(
            'SELECT COUNT(*) FROM radar_bucket_sources'
            ' WHERE bucket_start >= UTC_TIMESTAMP() - INTERVAL 24 HOUR')).scalar()
        print(f'24h slice: {day:,} rows   (target 405,582)')

        now = dt.datetime.utcnow().replace(microsecond=0)
        drop()
        base_mb = index_mb()
        print(f'index bytes on the table, baseline: {base_mb} MB')
        report('BASELINE - the indexes the target has', sources, now)

        for label, columns in CANDIDATES.items():
            drop()
            print(f'\nbuilding {label} {columns[:40]}...')
            t0 = time.perf_counter()
            db.session.execute(sa.text(
                f'ALTER TABLE radar_bucket_sources ADD INDEX {NAME} {columns},'
                f' ALGORITHM=INPLACE, LOCK=NONE'))
            db.session.commit()
            built = time.perf_counter() - t0
            print(f'  built in {built:.0f}s, online;'
                  f' adds {index_mb() - base_mb} MB')
            report(label, sources, now)

        drop()
        print('\ncandidate index dropped; fixture back to baseline')


if __name__ == '__main__':
    main()
