"""Step 0 of Task 8: bring the scale fixture's data up to the wall clock.

The perf1-derived fixture ends at 2026-09-10 12:00 UTC, and every process on
the shared path reads the real clock, so a board built later sees a partial
or empty window. Every board query is bounded above by `now`
(leaderboard.py:183-184; board.py:200-201, 259-260, 315-316, 383-384;
coverage.py:60-61), so rows dated after the measuring clock are invisible to
any window, and extending the fixture forward is safe.

What this does, idempotently:

1. For each of radar_bucket_sources, radar_mention_events and radar_quotes,
   find the end of its data (ignoring rows dated more than seven days past
   the clock: three `reddit:zzarcbf` mention events dated 2027-01-04 are a
   test's residue, and would otherwise make that table look aligned already),
   and copy its most recent 24-hour slice forward by whole days (+1 d, +2 d,
   ...) until the data reaches at least 24 h beyond now. Whole-day shifts keep
   the grid and the weekday pattern. Every datetime column of a copied row
   moves by the same whole number of days.
2. Delete the same number of the OLDEST whole days (24-hour spans from the
   first bucket) from radar_bucket_sources only, so it keeps its 23 days and
   9,269,184 rows. The other two tables hold a day or two and lose nothing.
3. Keep every primary and unique key unique. The keys are read from
   information_schema before anything is written, and each one must be
   satisfied by an auto-increment column (left for the server to assign), a
   shifted datetime column, or the declared re-key column (mention events'
   `external_id`, which gets an `@YYYYMMDD` suffix naming the target day).
   A key none of those covers stops the script.
4. Print counts before and after, the spans, and the rows inside the 24h and
   12h windows at the current clock; ANALYZE the three tables; re-run the
   preflight.

Nothing else is touched. Each hour of each copy, and each hour of the trim, is
its own transaction; a target hour that already holds rows is skipped, so a
re-run after an interruption finishes the job instead of duplicating it.

    cd personal_apps
    <python 3.12> scratchpad/perf3/align_scale_fixture.py [--dry-run]
"""
import argparse
import datetime as dt
import time

import sqlalchemy as sa

import scale_env

HOUR = dt.timedelta(hours=1)
DAY = dt.timedelta(days=1)
RESIDUE = dt.timedelta(days=7)
SLICE_HOURS = 24
SUFFIX_WIDTH = len('@YYYYMMDD')

# (table, grid column, datetime columns that move, re-key column, trim?)
PLAN = (
    ('radar_bucket_sources', 'bucket_start', ('bucket_start',), None, True),
    ('radar_mention_events', 'bucket_start',
     ('created_utc', 'bucket_start', 'chatter_decided_at'), 'external_id',
     False),
    ('radar_quotes', 'fetched_at', ('fetched_at', 'quote_ts'), None, False),
)
# The column each table's window count is taken on.
WINDOW_COLUMN = {'radar_bucket_sources': 'bucket_start',
                 'radar_mention_events': 'created_utc',
                 'radar_quotes': 'fetched_at'}


def shape(c, table, grid, shifted, rekey):
    """Columns to insert, and why every unique key stays unique."""
    columns = c.execute(sa.text(
        'SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, EXTRA'
        ' FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()'
        ' AND TABLE_NAME = :t ORDER BY ORDINAL_POSITION'), {'t': table}).all()
    keys = {name: tuple(cols.split(',')) for name, cols in c.execute(sa.text(
        'SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)'
        ' FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE()'
        ' AND TABLE_NAME = :t AND NON_UNIQUE = 0 GROUP BY INDEX_NAME'),
        {'t': table}).all()}
    names = [row[0] for row in columns]
    for needed in (grid,) + tuple(shifted) + ((rekey,) if rekey else ()):
        if needed not in names:
            raise SystemExit(f'{table} has no column {needed}')
    for column in shifted:
        kind = next(row[1] for row in columns if row[0] == column)
        if kind not in ('datetime', 'timestamp'):
            raise SystemExit(f'{table}.{column} is {kind}, not a datetime')
    auto = {row[0] for row in columns if 'auto_increment' in (row[3] or '')}
    reasons = {}
    for name, key in keys.items():
        if auto & set(key):
            reasons[name] = f'{key}: auto-increment, assigned by the server'
        elif set(shifted) & set(key):
            reasons[name] = f'{key}: carries a shifted datetime'
        elif rekey and rekey in key:
            reasons[name] = f'{key}: {rekey} re-keyed with @YYYYMMDD'
        else:
            raise SystemExit(f'{table}.{name} {key} would collide on a copy')
    if rekey:
        width = next(row[2] for row in columns if row[0] == rekey)
        longest = c.execute(sa.text(
            f'SELECT MAX(CHAR_LENGTH(`{rekey}`)) FROM `{table}`')).scalar() or 0
        if longest + SUFFIX_WIDTH > width:
            raise SystemExit(f'{table}.{rekey}: {longest} + {SUFFIX_WIDTH}'
                             f' characters exceed {width}')
    return {'insert': [n for n in names if n not in auto], 'keys': reasons,
            'auto': sorted(auto)}


def end_of_data(c, table, grid, now):
    return c.execute(sa.text(
        f'SELECT MAX(`{grid}`) FROM `{table}` WHERE `{grid}` < :h'),
        {'h': now + RESIDUE}).scalar()


def days_needed(anchor, now):
    """The smallest whole number of days that takes `anchor` to now + 24 h."""
    days = 0
    while anchor + days * DAY < now + DAY:
        days += 1
    return days


def copy_chunk(engine, table, grid, shifted, rekey, insert, low, high, days):
    """Copy (low, high] of `grid` forward by `days`. None if already there."""
    target_low, target_high = low + days * DAY, high + days * DAY
    with engine.begin() as c:
        if c.execute(sa.text(
                f'SELECT 1 FROM `{table}` WHERE `{grid}` > :lo'
                f' AND `{grid}` <= :hi LIMIT 1'),
                {'lo': target_low, 'hi': target_high}).first() is not None:
            return None
        expressions = []
        for column in insert:
            if column in shifted:
                expressions.append(f'`{column}` + INTERVAL {int(days)} DAY')
            elif column == rekey:
                expressions.append(f'CONCAT(`{column}`, :suffix)')
            else:
                expressions.append(f'`{column}`')
        params = {'lo': low, 'hi': high}
        if rekey:
            params['suffix'] = '@' + target_high.strftime('%Y%m%d')
        return c.execute(sa.text(
            f'INSERT INTO `{table}` ({", ".join(f"`{n}`" for n in insert)})'
            f' SELECT {", ".join(expressions)} FROM `{table}`'
            f' WHERE `{grid}` > :lo AND `{grid}` <= :hi'), params).rowcount


def census(engine, now):
    """Counts, spans and window rows of the three tables at `now`."""
    out = {}
    with engine.connect() as c:
        for table, grid, _, _, _ in PLAN:
            column = WINDOW_COLUMN[table]
            count, low, high = c.execute(sa.text(
                f'SELECT COUNT(*), MIN(`{grid}`), MAX(`{grid}`) FROM `{table}`'
                f' WHERE `{grid}` < :h'), {'h': now + RESIDUE}).one()
            windows = {hours: c.execute(sa.text(
                f'SELECT COUNT(*) FROM `{table}` WHERE `{column}` >= :since'
                f' AND `{column}` < :now'),
                {'since': now - dt.timedelta(hours=hours), 'now': now}).scalar()
                for hours in (24, 12)}
            residue = c.execute(sa.text(
                f'SELECT COUNT(*) FROM `{table}` WHERE `{grid}` >= :h'),
                {'h': now + RESIDUE}).scalar()
            out[table] = {'rows': count, 'span': (low, high),
                          'window_24h': windows[24], 'window_12h': windows[12],
                          'residue': residue}
    return out


def show(title, facts):
    print(f'\n{title}')
    print(f"  {'table':22s} {'rows':>11s} {'first':>19s} {'last':>19s}"
          f" {'24h rows':>9s} {'12h rows':>9s}")
    for table, fact in facts.items():
        low, high = fact['span']
        print(f"  {table:22s} {fact['rows']:>11,} {str(low):>19s}"
              f" {str(high):>19s} {fact['window_24h']:>9,}"
              f" {fact['window_12h']:>9,}"
              + (f"   (+{fact['residue']} residue rows past now+7d)"
                 if fact['residue'] else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dry-run', action='store_true',
                        help='print the plan and write nothing')
    args = parser.parse_args()

    import env_check
    env_check.preflight('align_scale_fixture: before', require_window=False)
    app = scale_env.bind()
    engine = scale_env.engine()

    now = scale_env.utcnow()
    print(f'\nclock: {now:%Y-%m-%d %H:%M:%S} UTC; the data must reach'
          f' {now + DAY:%Y-%m-%d %H:%M:%S}')
    with app.app_context():
        before = census(engine, now)
    show('BEFORE', before)

    plans = []
    with engine.connect() as c:
        for table, grid, shifted, rekey, trim in PLAN:
            anchor = end_of_data(c, table, grid, now)
            days = days_needed(anchor, now)
            info = shape(c, table, grid, shifted, rekey)
            plans.append((table, grid, shifted, rekey, trim, anchor, days,
                          info))
            print(f'\n{table}: data ends {anchor}; copy the slice'
                  f' ({anchor - SLICE_HOURS * HOUR}, {anchor}] forward by'
                  f' {days} day(s)' + (f', then trim {days} oldest day(s)'
                                       if trim and days else ''))
            print(f"  inserted columns: {len(info['insert'])} (server assigns"
                  f" {info['auto'] or 'nothing'})")
            for name, reason in info['keys'].items():
                print(f'  unique {name}: {reason}')

    if args.dry_run:
        print('\nDRY RUN: nothing written.')
        return
    if not any(days for *_, days, _ in plans):
        print('\nALREADY ALIGNED: every table reaches now + 24 h; nothing'
              ' written.')
    touched = []
    for table, grid, shifted, rekey, trim, anchor, days, info in plans:
        if not days:
            continue
        touched.append(table)
        began = time.perf_counter()
        copied = skipped = 0
        for shift in range(1, days + 1):
            for hour in range(SLICE_HOURS):
                low = anchor - SLICE_HOURS * HOUR + hour * HOUR
                done = copy_chunk(engine, table, grid, shifted, rekey,
                                  info['insert'], low, low + HOUR, shift)
                if done is None:
                    skipped += 1
                else:
                    copied += done
            print(f'  {table}: +{shift} d copied, {copied:,} rows so far'
                  f' ({time.perf_counter() - began:.1f} s)', flush=True)
        print(f'  {table}: {copied:,} rows copied, {skipped} target hours'
              f' already present, {time.perf_counter() - began:.1f} s')
        if trim:
            began = time.perf_counter()
            with engine.connect() as c:
                first = c.execute(sa.text(
                    f'SELECT MIN(`{grid}`) FROM `{table}`')).scalar()
            cutoff = first + days * DAY
            removed = 0
            low = first
            while low < cutoff:
                with engine.begin() as c:
                    removed += c.execute(sa.text(
                        f'DELETE FROM `{table}` WHERE `{grid}` >= :lo'
                        f' AND `{grid}` < :hi'),
                        {'lo': low, 'hi': min(low + HOUR, cutoff)}).rowcount
                low += HOUR
            print(f'  {table}: trimmed {removed:,} rows before {cutoff}'
                  f' ({time.perf_counter() - began:.1f} s)', flush=True)
    if touched:
        with engine.connect() as c:
            for table in touched:
                result = c.execute(sa.text(f'ANALYZE TABLE `{table}`')).all()
                print(f'  ANALYZE {table}: {result[-1][-1]}')

    now = scale_env.utcnow()
    with app.app_context():
        after = census(engine, now)
    show(f'AFTER (clock {now:%Y-%m-%d %H:%M:%S} UTC)', after)
    env_check.preflight('align_scale_fixture: after', require_window=True)


if __name__ == '__main__':
    main()
