"""Before/after on the WHOLE build, plus what the index costs to write.

Same dataset, same fixed input time, same process. The board is built through
board.build, not through a hand-written query, so the number is the one the
endpoint would produce.
"""
import datetime as dt
import statistics
import time

import sqlalchemy as sa

from app import app
from extensions import db
from features.radar import board as board_mod

COVER = ('CREATE INDEX ix_perf_cover ON radar_bucket_sources'
         ' (bucket_start, source, ticker, mention_z, mention_count, expected,'
         '  variance, distinct_authors, distinct_text_ratio, baseline_days,'
         '  status)')
SOURCES = ['bluesky', 'fourchan', 'reddit']
SAMPLES = 3


def drop(name):
    try:
        db.session.execute(sa.text(f'DROP INDEX {name} ON radar_bucket_sources'))
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def has_index(name):
    return db.session.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS"
        " WHERE TABLE_SCHEMA='personal_apps_radar_perf1'"
        " AND TABLE_NAME='radar_bucket_sources' AND INDEX_NAME=:n"),
        {'n': name}).scalar() > 0


def build_times(now, hours):
    board_mod.build(SOURCES, now, window_hours=hours, segments=(), limit=50,
                    market='us')                      # warm
    took = []
    for _ in range(SAMPLES):
        began = time.perf_counter()
        built = board_mod.build(SOURCES, now, window_hours=hours, segments=(),
                                limit=50, market='us')
        took.append(time.perf_counter() - began)
    return took, len(built.rows)


def write_cost(label):
    """What one ingest-shaped batch of 20,000 bucket rows costs to insert."""
    at = dt.datetime.utcnow().replace(microsecond=0) + dt.timedelta(days=400)
    began = time.perf_counter()
    db.session.execute(sa.text("""
        INSERT INTO radar_bucket_sources
            (ticker, bucket_start, source, mention_count, high_confidence_count,
             low_count, distinct_authors, distinct_text_ratio,
             engagement_weighted_count, status, expected, variance, mention_z,
             baseline_days, source_config_version)
        SELECT CONCAT('W', LPAD(n, 5, '0')), :at, 'bluesky',
               1, 1, 0, 1, 0.5, 1.0, 'ok', 1.0, 0.5, 1.0, 30, 'v1'
        FROM perf_write_numbers
        ON DUPLICATE KEY UPDATE mention_count = VALUES(mention_count)
    """), {'at': at})
    db.session.commit()
    took = time.perf_counter() - began
    db.session.execute(sa.text(
        'DELETE FROM radar_bucket_sources WHERE bucket_start = :at'), {'at': at})
    db.session.commit()
    print(f'  write 20,000 rows {label}: {took:.2f}s')
    return took


def report(label, now):
    print(f'\n=== {label} ===')
    for hours in (4, 12, 24):
        took, rows = build_times(now, hours)
        print(f'  {hours:>2}h board.build  median {statistics.median(took):6.2f}s'
              f'  min {min(took):6.2f}s  max {max(took):6.2f}s  rows {rows}')


def main():
    with app.app_context():
        name = db.engine.url.database
        assert name == 'personal_apps_radar_perf1', f'WRONG DATABASE: {name}'
        print('database:', name)

        db.session.execute(sa.text(
            'CREATE TABLE IF NOT EXISTS perf_write_numbers (n INT PRIMARY KEY)'))
        db.session.commit()
        if db.session.execute(sa.text(
                'SELECT COUNT(*) FROM perf_write_numbers')).scalar() < 20_000:
            for start in range(0, 20_000, 5_000):
                values = ','.join(f'({n})' for n in range(start, start + 5_000))
                db.session.execute(sa.text(
                    f'INSERT IGNORE INTO perf_write_numbers (n) VALUES {values}'))
            db.session.commit()

        now = dt.datetime.utcnow().replace(microsecond=0)

        drop('ix_perf_group')
        drop('ix_perf_cover')
        print('indexes: as deployed')
        report('BEFORE - the indexes the target has', now)
        before_write = write_cost('BEFORE')

        print('\nbuilding the covering index...')
        began = time.perf_counter()
        db.session.execute(sa.text(COVER))
        db.session.commit()
        print(f'  built in {time.perf_counter() - began:.0f}s')

        size = db.session.execute(sa.text(
            "SELECT ROUND(INDEX_LENGTH/1048576) FROM information_schema.TABLES"
            " WHERE TABLE_SCHEMA='personal_apps_radar_perf1'"
            " AND TABLE_NAME='radar_bucket_sources'")).scalar()
        print(f'  all indexes on the table now: {size} MB')

        report('AFTER - one covering index added', now)
        after_write = write_cost('AFTER')
        print(f'\nwrite cost: {before_write:.2f}s -> {after_write:.2f}s'
              f'  ({after_write / before_write:.2f}x)')


if __name__ == '__main__':
    main()
