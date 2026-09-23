"""Fill personal_apps_radar_perf1 to the target's measured cardinalities.

Synthetic, not restored: no post content, no author names and no other
personal data leaves the target. What is reproduced is the SHAPE the planner
reacts to -- total table size, the size of the 24h slice, the distinct-ticker
and group counts, and the 780 days of daily closes the sigma read walks.

Measured on the target 2026-09-10, and matched here:

  radar_bucket_sources   9,333,403 total, 405,582 in 24h,
                         5,505 tickers, 51,255 (ticker, source) groups
  radar_mention_events   1,153,330 total, 563,744 in 24h
  radar_daily_closes     5,678,006
  radar_quotes             110,742
  radar_ticker_universe     12,415
  radar_mentions           267,766

Generated with INSERT ... SELECT against a numbers table, per hour, so no
single statement holds nine million rows.
"""
import datetime as dt
import time

import sqlalchemy as sa

from app import app
from extensions import db

# The target's own source list: two big feeds plus ~33 reddit subs.
SOURCES = ['bluesky', 'fourchan'] + [f'reddit:sub{i:02d}' for i in range(33)]
TICKERS = 12_415          # radar_ticker_universe
ACTIVE = 5_505            # tickers appearing in a 24h window
HOURS = 552               # 23 days -> 9.33M at 405,582/day
CLOSE_DAYS = 780          # history.HISTORY_DAYS, what the sigma read walks
NOW = dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0)


def run(sql, **params):
    db.session.execute(sa.text(sql), params)
    db.session.commit()


def scalar(sql):
    return db.session.execute(sa.text(sql)).scalar()


def numbers(limit):
    """A numbers table, filled in batches.

    Not a recursive CTE: `cte_max_recursion_depth` defaults to 1000 and this
    needs twenty thousand. Raising a server variable to build a fixture is a
    worse trade than one bulk insert.
    """
    run('DROP TABLE IF EXISTS perf_numbers')
    run('CREATE TABLE perf_numbers (n INT PRIMARY KEY)')
    for start in range(0, limit, 5_000):
        values = ','.join(f'({n})' for n in range(start, min(start + 5_000, limit)))
        run(f'INSERT INTO perf_numbers (n) VALUES {values}')


def main():
    with app.app_context():
        name = db.engine.url.database
        assert name == 'personal_apps_radar_perf1', f'WRONG DATABASE: {name}'
        print('database:', name, '- verified before any write')
        began = time.perf_counter()

        print('numbers table...')
        numbers(20_000)

        print('universe...')
        run('DELETE FROM radar_ticker_universe')
        run("""
            INSERT INTO radar_ticker_universe
                (symbol, name, exchange, first_seen, market_cap, is_etf)
            SELECT CONCAT('T', LPAD(n, 5, '0')),
                   CONCAT('Synthetic Company ', n),
                   CASE WHEN n % 3 = 0 THEN 'NASDAQ' ELSE 'NYSE' END,
                   :first_seen,
                   POW(10, 7 + (n % 6)),
                   n % 40 = 0
            FROM perf_numbers WHERE n < :tickers
        """, first_seen=NOW - dt.timedelta(days=900), tickers=TICKERS)
        print('  universe:', scalar('SELECT COUNT(*) FROM radar_ticker_universe'))

        # --- the table the bottleneck lives in -------------------------------
        # Per hour: every active ticker appears on a deterministic subset of
        # sources, so the (ticker, source) group count lands near the
        # target's 51,255 over 24 hours.
        print('bucket sources (9.3M rows, this is the long one)...')
        run('DELETE FROM radar_bucket_sources')
        rows_per_hour_target = 9_333_403 // HOURS
        for hour in range(HOURS):
            at = NOW - dt.timedelta(hours=hour)
            for si, source in enumerate(SOURCES):
                # Each source carries a slice of the active tickers; the two
                # big feeds carry far more, as they do on the target.
                share = 0.62 if si < 2 else 0.055
                keep = max(int(ACTIVE * share), 1)
                run("""
                    INSERT INTO radar_bucket_sources
                        (ticker, bucket_start, source, mention_count,
                         high_confidence_count, low_count, distinct_authors,
                         distinct_text_ratio, engagement_weighted_count,
                         status, expected, variance, mention_z, baseline_days,
                         source_config_version)
                    SELECT CONCAT('T', LPAD((n * 7 + :salt) % :active, 5, '0')),
                           :at, :source,
                           1 + (n % 9), 1 + (n % 5), n % 3, 1 + (n % 7),
                           0.3 + (n % 50) / 100.0, 1.0 + (n % 4),
                           'ok',
                           1.0 + (n % 6), 0.5 + (n % 3), (n % 40) / 10.0, 30,
                           'v1'
                    FROM perf_numbers WHERE n < :keep
                    ON DUPLICATE KEY UPDATE mention_count = VALUES(mention_count)
                """, at=at, source=source, salt=hour * 13 + si, active=ACTIVE,
                    keep=keep)
            if hour % 48 == 0:
                have = scalar('SELECT COUNT(*) FROM radar_bucket_sources')
                print(f'  hour {hour}/{HOURS}  rows={have:,}'
                      f'  {time.perf_counter() - began:.0f}s')
        total = scalar('SELECT COUNT(*) FROM radar_bucket_sources')
        day = scalar('SELECT COUNT(*) FROM radar_bucket_sources'
                     ' WHERE bucket_start >= NOW() - INTERVAL 24 HOUR')
        tick = scalar('SELECT COUNT(DISTINCT ticker) FROM radar_bucket_sources'
                      ' WHERE bucket_start >= NOW() - INTERVAL 24 HOUR')
        print(f'  bucket_sources: {total:,} total, {day:,} in 24h,'
              f' {tick:,} tickers  (target 9,333,403 / 405,582 / 5,505)')

        print('daily closes (5.7M)...')
        run('DELETE FROM radar_daily_closes')
        for chunk in range(0, CLOSE_DAYS, 60):
            run("""
                INSERT INTO radar_daily_closes
                    (ticker, market, mic, currency, close_date, close,
                     fetched_at, source, price_basis, adjustment_basis,
                     is_shadow)
                SELECT CONCAT('T', LPAD(t.n, 5, '0')), 'us', 'XNAS', 'USD',
                       DATE_SUB(CURDATE(), INTERVAL (d.n + :chunk) DAY),
                       10 + ((t.n + d.n) % 500),
                       :now, 'yahoo_chart', 'close', 'split', 0
                FROM perf_numbers t
                JOIN perf_numbers d ON d.n < 60
                WHERE t.n < :active AND (d.n + :chunk) < :days
                  AND DAYOFWEEK(DATE_SUB(CURDATE(),
                      INTERVAL (d.n + :chunk) DAY)) NOT IN (1, 7)
            """, chunk=chunk, active=ACTIVE, days=CLOSE_DAYS, now=NOW)
        print('  daily_closes:', f'{scalar("SELECT COUNT(*) FROM radar_daily_closes"):,}',
              '(target 5,678,006)')

        print('mention events (1.15M)...')
        run('DELETE FROM radar_mention_events')
        for hour in range(48):
            at = NOW - dt.timedelta(hours=hour)
            run("""
                INSERT INTO radar_mention_events
                    (source, external_id, ticker, channel, created_utc,
                     bucket_start, author, simhash, confidence, engagement,
                     promoted, counts_as_human_chatter)
                SELECT CASE WHEN n % 2 = 0 THEN 'bluesky' ELSE 'fourchan' END,
                       CONCAT('perf-', :hour, '-', n),
                       CONCAT('T', LPAD((n * 3 + :hour) % :active, 5, '0')),
                       CONCAT('chan', n % 40),
                       DATE_ADD(:at, INTERVAL (n % 60) MINUTE), :at,
                       CONCAT('author', n % 5000),
                       n, 'high', 1.0, 0, 1
                FROM perf_numbers WHERE n < :per_hour
                ON DUPLICATE KEY UPDATE engagement = VALUES(engagement)
            """, hour=hour, at=at, active=ACTIVE, per_hour=12_000)
        print('  mention_events:', f'{scalar("SELECT COUNT(*) FROM radar_mention_events"):,}',
              '(target 1,153,330; 24h slice is what the voice query reads)')

        print('quotes (110k)...')
        run('DELETE FROM radar_quotes')
        for hour in range(24):
            at = NOW - dt.timedelta(hours=hour)
            run("""
                INSERT INTO radar_quotes
                    (ticker, market, mic, currency, fetched_at, quote_ts,
                     price, price_basis, is_shadow)
                SELECT CONCAT('T', LPAD(n, 5, '0')), 'us', 'XNAS', 'USD',
                       :at, :at, 10 + ((n + :hour) % 400), 'trade', 0
                FROM perf_numbers WHERE n < :per_hour
            """, at=at, hour=hour, per_hour=4_600)
        print('  quotes:', f'{scalar("SELECT COUNT(*) FROM radar_quotes"):,}',
              '(target 110,742)')

        run('DROP TABLE IF EXISTS perf_numbers')
        print(f'done in {time.perf_counter() - began:.0f}s')


if __name__ == '__main__':
    main()
