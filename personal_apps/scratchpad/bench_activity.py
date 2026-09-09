"""How much the activity endpoint actually has to read, and how long it takes.

Repeatable. Run it from personal_apps with PYTHONPATH=. against the disposable
database; it refuses to run against anything else, seeds its own rows in a
window no real data occupies, measures, and removes them again -- in a
`finally`, so a failure inside the timed region does not leave them behind.

    PYTHONPATH=. py -3.12 scratchpad/bench_activity.py

Why it exists: the first capacity note guessed 2,880 runs over 30 days from the
board archive's 15-minute cadence. That is the wrong writer. Runs are written by
`tick`, and `tick` is called by TWO scheduler jobs on their own cadences --
`radar_cycle`, whose interval follows the NYSE session, and `radar_reddit`,
which is fixed. The count below is derived by walking the real calendar through
the real interval table rather than by dividing an hour by a guess.

The two jobs write DIFFERENT envelopes, and that is the correction a first
version of this script got wrong. `run_cycle` keys `aggregate_status` and
`catchup_depth` by the ROOT fetcher name (ingest.py:288,306) and only
`per_source` by concrete names, and the schedulers pass disjoint fetcher sets --
`session_fetchers` is everything but reddit (run_radar_ingest.py:1348) and the
reddit job gets `{'reddit': fetcher}` alone (:1128). No real run has ever
produced the 36-key maps a single uniform envelope models, and modelling one
overstated the volume roughly twofold. Both shapes are built here and each
firing is seeded with its own.
"""
import datetime as dt
import gc
import statistics
import sys
import time
import tracemalloc
import uuid

sys.path.insert(0, '.')

import sqlalchemy as sa                                     # noqa: E402

from app import app                                        # noqa: E402
from extensions import db                                  # noqa: E402
from features.radar import activity, market_calendar       # noqa: E402
from features.radar.config import REDDIT_SUBS              # noqa: E402
from features.radar.extraction import REASONS              # noqa: E402
from models import AppUser, RadarIngestRun                 # noqa: E402
from run_radar_ingest import (                             # noqa: E402
    CYCLE_SECONDS, FALLBACK_INTERVAL, INTERVALS, _reddit_job_seconds)

EXPECTED_DB = 'personal_apps_radar_wt'

# 2019: before Radar existed, so nothing real can be in the window and the
# cleanup can be scoped by date rather than by collecting ids. The backend
# suite also anchors fixtures in 2019 and test_radar_observations.py runs the
# same blanket `started_at < 2020-01-01` delete; no test anchor falls inside
# 05-27..06-26, so the two do not collide today. Do not run this concurrently
# with that suite.
#
# A WEDNESDAY, deliberately. The session cycle runs at 180s while the market is
# open and 1800s overnight and at weekends, so a one-day window anchored on a
# Sunday reports far fewer cycle runs than a weekday one. Anchoring on a weekend
# would have made the smallest window look like the cheapest case by a factor
# the endpoint does not enjoy in practice. Both are printed at the end.
ANCHOR = dt.datetime(2019, 6, 26, 12, 0)           # Wednesday
WEEKEND_ANCHOR = dt.datetime(2019, 6, 30, 12, 0)   # Sunday, for contrast
WINDOWS = (1, 7, 30)

# Acceptance targets set by Codex's R3 ruling, against the 30-day upper-bound
# fixture on this local environment. Targets, not predictions, and not a
# production guarantee.
PEAK_TARGET_MIB = 16
ENDPOINT_TARGET_MS = 500

# What a cycle costs before the scheduler counts the next interval. APScheduler
# builds a fresh interval trigger on reschedule and its start_date is
# `now + interval` at construction (apscheduler/triggers/interval.py), so the
# next firing is FINISH + interval, not START + interval. Real runs are
# therefore slightly rarer than a drift-free walk suggests. The drift-free walk
# is kept as the upper bound and both are printed.
CYCLE_DURATION = 38
REDDIT_DURATION = 38


def cycle_starts(start, end, duration=0):
    """When `radar_cycle` would have fired, by the rule it actually uses.

    _scheduled_cycle reschedules itself after every run with
    interval_for(current_state(now)), so the cadence is a function of the NYSE
    session at each firing -- 180s while the market is open or in pre-market,
    600s after hours, 1800s overnight and at weekends.

    `duration` models the reschedule happening when the run FINISHES. Zero is
    the drift-free upper bound.
    """
    out, when = [], start
    while when < end:
        out.append(when)
        state = market_calendar.session_state(
            when.replace(tzinfo=dt.timezone.utc))
        when += dt.timedelta(
            seconds=INTERVALS.get(state, FALLBACK_INTERVAL) + duration)
    return out


def reddit_starts(start, end, duration=0):
    """`radar_reddit` runs on a fixed interval and calls the same tick.

    An upper bound in one more way than cycle_starts: the job carries
    coalesce=True and max_instances=1, so an Arctic Shift pass that overran its
    interval collapses the firings it missed into a single run.
    """
    step = dt.timedelta(seconds=_reddit_job_seconds() + duration)
    out, when = [], start
    while when < end:
        out.append(when)
        when += step
    return out


def _envelope(summary):
    return {'schema_version': activity.SCHEMA_VERSION, 'summary': summary}


def _reasons():
    """One intake counter, in the extractor's real vocabulary."""
    return dict(zip(REASONS, (312, 178, 96, 61, 24, 17, 9, 4)))


def cycle_envelope():
    """What `radar_cycle` writes: bluesky and fourchan, no reddit.

    Neither fetcher reports per_source_status, so run_cycle files each under
    its own root name; aggregate_status and catchup_depth are keyed by the
    fetcher roots either way.
    """
    roots = ['bluesky', 'fourchan']
    return _envelope({
        'posts_seen': 214, 'posts_new': 37, 'mentions': 19,
        'buckets_written': 6,
        'per_source': {name: 'ok' for name in roots},
        'aggregate_status': {name: 'ok' for name in roots},
        # fourchan reports len(active[:thread_cap]), not 0 (fourchan.py:137).
        'catchup_depth': {'bluesky': 0, 'fourchan': 40},
        'intake_reasons': {name: _reasons() for name in roots},
    })


def reddit_envelope():
    """What `radar_reddit` writes: every configured sub in per_source, because
    arctic_shift.fetch iterates all of REDDIT_SUBS in one cycle -- but a single
    'reddit' key in aggregate_status and catchup_depth.

    34 is a ceiling, not a constant: a 429 ends the cycle and the subs never
    asked stay absent from per_source_status rather than appearing as failures.
    """
    subs = ['reddit:%s' % sub for sub in REDDIT_SUBS]
    return _envelope({
        'posts_seen': 1287, 'posts_new': 143, 'mentions': 96,
        'buckets_written': 41,
        'per_source': {name: 'ok' for name in subs},
        'aggregate_status': {'reddit': 'ok'},
        'catchup_depth': {'reddit': 0},
        'intake_reasons': {name: _reasons() for name in subs},
    })


def rows_for(starts, body):
    """Seeded rows carry the typed projection beside the envelope, because
    that is what `finish_run` writes. Seeding envelopes alone would leave every
    row uncountable and the read would be measured returning nulls -- fast, and
    measuring nothing."""
    version, countable, counters = activity.project(body)
    return [{'id': str(uuid.uuid4()), 'started_at': when,
             'finished_at': when + dt.timedelta(seconds=38), 'status': 'ok',
             'summary_json': body, 'error_code': None,
             'summary_schema_version': version,
             'summary_countable': countable, **counters}
            for when in starts]


def seed(rows):
    for chunk in range(0, len(rows), 500):
        db.session.bulk_insert_mappings(RadarIngestRun, rows[chunk:chunk + 500])
        db.session.commit()
    return len(rows)


def clear():
    db.session.rollback()
    RadarIngestRun.query.filter(
        RadarIngestRun.started_at < dt.datetime(2020, 1, 1)).delete(
            synchronize_session=False)
    db.session.commit()


def timed(call, repeats=5, warm_up=True):
    """Median and maximum of N. The maximum is the honest number for a route a
    reader can hit repeatedly; the median says what it usually costs.

    `warm_up=False` leaves the first call inside the measurement, which is what
    a COLD read looks like -- no application object caches, no warmed pool.
    """
    if warm_up:
        call()
    runs = []
    for _ in range(repeats):
        began = time.perf_counter()
        call()
        runs.append((time.perf_counter() - began) * 1000)
    return statistics.median(runs), max(runs)


def rss_mib():
    """What the operating system thinks the process is using.

    tracemalloc sees Python allocations and misses allocator overhead and
    fragmentation, so it is a floor. This is the number a host actually runs
    out of. psutil first; on Windows without it, ask the API directly rather
    than report nothing.
    """
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1048576
    except ImportError:
        pass
    if sys.platform != 'win32':
        try:
            import resource
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Linux reports KiB, macOS bytes.
            return peak / 1024 if sys.platform.startswith('linux') \
                else peak / 1048576
        except ImportError:
            return None
    import ctypes
    import ctypes.wintypes as wintypes

    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD),
                    ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t)]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    # restype matters. ctypes defaults a return to c_int, which truncates the
    # 64-bit pseudo-handle GetCurrentProcess returns, and the call then fails
    # silently with a zero return and a zero working set.
    current_process = ctypes.windll.kernel32.GetCurrentProcess
    current_process.restype = wintypes.HANDLE
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters),
                         wintypes.DWORD]
    if not get_info(current_process(), ctypes.byref(counters), counters.cb):
        return None
    return counters.WorkingSetSize / 1048576


def concurrent_reads(client_factory, days, workers=4):
    """Several readers at once. One request says nothing about what happens
    when four arrive together -- and the endpoint is reachable by any signed-in
    reader, repeatedly."""
    import threading

    errors, timings = [], []
    lock = threading.Lock()

    def one():
        try:
            began = time.perf_counter()
            with client_factory() as client:
                response = client.get(f'/radar/api/activity?days={days}')
                body = response.get_data()
            elapsed = (time.perf_counter() - began) * 1000
            with lock:
                if response.status_code != 200:
                    errors.append(f'status {response.status_code}')
                timings.append(elapsed)
            del body
        except Exception as problem:                     # noqa: BLE001
            with lock:
                errors.append(f'{type(problem).__name__}: {problem}')

    threads = [threading.Thread(target=one) for _ in range(workers)]
    before = rss_mib()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    after = rss_mib()
    return errors, timings, before, after


def window_bounds(days):
    """The instants `activity.summary` will actually query -- Berlin calendar
    days, not a rolling 24h * days. Counting bytes over a different window than
    the one being timed is how a table ends up carrying three numbers drawn
    from two different row sets.
    """
    today = activity._berlin_date(ANCHOR)                    # noqa: SLF001
    first = today - dt.timedelta(days=days - 1)
    return (activity._day_bounds(first)[0],                  # noqa: SLF001
            activity._day_bounds(today)[1])                  # noqa: SLF001


def measured(window_from, window_to):
    """Rows and JSON bytes the endpoint reads, asked of the database.

    LENGTH() over the JSON column, not a Python re-serialization: what the
    server sends is its own canonical text for the value, and json.dumps under
    some separator choice is a third number matching neither.
    """
    return db.session.execute(sa.select(
        sa.func.count(),
        sa.func.coalesce(
            sa.func.sum(sa.func.length(RadarIngestRun.summary_json)), 0),
    ).where(RadarIngestRun.started_at >= window_from,
            RadarIngestRun.started_at < window_to)).one()


def control(window_from, window_to):
    """The same rows without summary_json. The difference is the envelopes,
    which is the claim the whole exercise rests on."""
    return db.session.execute(sa.select(
        RadarIngestRun.started_at, RadarIngestRun.status,
    ).where(RadarIngestRun.started_at >= window_from,
            RadarIngestRun.started_at < window_to)).all()


def peak_mib(call):
    """Python's own peak during one call.

    This used to be the headline cost: `summary()` ended in `.all()` over rows
    carrying `summary_json`, so every row and every decoded envelope was live
    at once. It now selects scalars and streams them, and this is the number
    that proves it."""
    gc.collect()
    tracemalloc.start()
    call()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1048576


def pass_over(label, duration, admin, cycle_body, reddit_body):
    """Seed one scheduling model and measure it. Clears first, so the two
    passes cannot see each other's rows.

    Two kinds of read are timed. COLD includes the first call, before any
    application-level object cache or warmed connection exists. WARM is the
    median of five after a warm-up. The database buffer pool is warm in both
    after the seed, and that is stated rather than claimed away: what separates
    the two columns here is APPLICATION state, not disk.
    """
    clear()
    # Two days wider than the widest window: summary() queries Berlin calendar
    # days, whose start can precede ANCHOR - days.
    widest = max(WINDOWS)
    seed_from = ANCHOR - dt.timedelta(days=widest + 2)
    cycles = cycle_starts(seed_from, ANCHOR, duration)
    reddits = reddit_starts(seed_from, ANCHOR, duration)
    total = seed(rows_for(cycles, cycle_body) + rows_for(reddits, reddit_body))
    print(f'\n=== {label} ===')
    print(f'seeded {total:,} runs over {widest + 2} days '
          f'(cycle {len(cycles):,} + reddit {len(reddits):,})')

    def client_factory():
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = admin.id
        return client

    print(f'{"window":>7} {"rows":>7} {"JSON MiB":>9} {"summary ms":>16} '
          f'{"endpoint ms":>16} {"cold ms":>9} {"peak MiB":>9}')
    results = {}
    for days in WINDOWS:
        window_from, window_to = window_bounds(days)
        rows, byte_total = measured(window_from, window_to)

        median, worst = timed(lambda d=days: activity.summary(ANCHOR, d))
        peak = peak_mib(lambda d=days: activity.summary(ANCHOR, d))

        with client_factory() as client:
            def call(d=days):
                response = client.get(f'/radar/api/activity?days={d}')
                assert response.status_code == 200, response.status_code
                return response.get_data()

            endpoint_median, endpoint_worst = timed(call)

        # A fresh client and a fresh session, first call measured.
        with client_factory() as cold_client:
            def cold(d=days):
                response = cold_client.get(f'/radar/api/activity?days={d}')
                assert response.status_code == 200, response.status_code
                return response.get_data()

            cold_median, _ = timed(cold, repeats=1, warm_up=False)

        print(f'{days:>7} {rows:>7,} {byte_total / 1048576:>9.1f} '
              f'{median:>10.0f}/{worst:<5.0f} '
              f'{endpoint_median:>10.0f}/{endpoint_worst:<5.0f} '
              f'{cold_median:>9.0f} {peak:>9.1f}')
        results[days] = {'rows': rows, 'endpoint_median': endpoint_median,
                         'endpoint_max': endpoint_worst, 'peak': peak}

    print('  ms columns are median/maximum of five measured requests after a '
          'warm-up; "cold" is a single first request on a fresh client.')

    # Four at once, at the widest window.
    errors, timings, rss_before, rss_after = concurrent_reads(
        client_factory, max(WINDOWS), workers=4)
    shown = '/'.join(f'{value:.0f}' for value in sorted(timings))
    print(f'  four concurrent {max(WINDOWS)}-day reads: {len(errors)} errors, '
          f'{shown} ms')
    if errors:
        print(f'    errors: {errors}')
    if rss_before is not None:
        print(f'    process RSS {rss_before:.0f} -> {rss_after:.0f} MiB')
    else:
        print('    process RSS unavailable on this platform')
    return results


def main():
    with app.app_context():
        resolved = db.engine.url.database
        # Not an assert: -O would compile the one guard that matters away.
        if resolved != EXPECTED_DB:
            raise SystemExit(f'refusing to run against {resolved!r}')
        # A connection first: server_version_info is populated on connect.
        with db.engine.connect() as connection:
            connection.exec_driver_sql('select 1')
        version = '.'.join(
            str(part) for part in db.engine.dialect.server_version_info or ())
        print(f'database: {resolved} ({db.engine.dialect.name} {version})')
        print("production is MariaDB; these numbers are MySQL's.\n")

        cycle_body, reddit_body = cycle_envelope(), reddit_envelope()
        print(f'reddit reader @ {_reddit_job_seconds()}s; session cycle floor '
              f'{CYCLE_SECONDS}s; {len(REDDIT_SUBS)} subs configured')
        for name, body in (('radar_cycle', cycle_body),
                           ('radar_reddit', reddit_body)):
            keys = body['summary']
            print(f'  {name:<13} per_source={len(keys["per_source"]):<3}'
                  f' aggregate_status={len(keys["aggregate_status"]):<3}'
                  f' catchup_depth={len(keys["catchup_depth"]):<3}'
                  f' intake_reasons={len(keys["intake_reasons"])}')

        import features.radar.routes.operations as operations
        original_utcnow = operations._utcnow                  # noqa: SLF001
        operations._utcnow = lambda: ANCHOR                   # noqa: SLF001
        app.config['TESTING'] = True

        clear()
        try:
            admin = AppUser.query.filter_by(is_admin=True).order_by(
                AppUser.id).first()
            if admin is None:
                raise SystemExit('no admin user in the disposable database')

            # As the server stores it, not as Python would re-serialize it.
            seed(rows_for([ANCHOR - dt.timedelta(days=200)], cycle_body)
                 + rows_for([ANCHOR - dt.timedelta(days=199)], reddit_body))
            length = sa.func.length(RadarIngestRun.summary_json)
            smallest, largest = db.session.execute(
                sa.select(sa.func.min(length), sa.func.max(length))
                .where(RadarIngestRun.started_at < dt.datetime(2020, 1, 1))
            ).one()
            print(f'  one radar_cycle envelope:  {smallest:,} bytes')
            print(f'  one radar_reddit envelope: {largest:,} bytes')

            # BOTH scheduling models are seeded and measured, not one measured
            # and the other asserted. The drift-free walk is the upper bound
            # this file argues APScheduler does not actually produce, so
            # publishing only it would be the same overstatement in a
            # different place.
            upper = pass_over('start + interval (drift-free upper bound)', 0,
                              admin, cycle_body, reddit_body)
            pass_over(f'finish + interval ({CYCLE_DURATION}s runs, what '
                      f'APScheduler does)', CYCLE_DURATION,
                      admin, cycle_body, reddit_body)

            # Codex's acceptance targets, checked against the 30-day
            # UPPER-BOUND fixture -- the larger of the two models, which is the
            # one the ruling names.
            widest = upper[max(WINDOWS)]
            print(f'\nacceptance, 30-day upper-bound fixture '
                  f'({widest["rows"]:,} rows):')
            for name, value, limit, unit in (
                    ('peak incremental Python heap', widest['peak'],
                     PEAK_TARGET_MIB, 'MiB'),
                    ('median endpoint', widest['endpoint_median'],
                     ENDPOINT_TARGET_MS, 'ms')):
                verdict = 'PASS' if value <= limit else 'FAIL'
                print(f'  {verdict}  {name}: {value:.1f} {unit} '
                      f'(target <= {limit} {unit})')

            print('\n"JSON MiB" is what the envelopes WOULD have cost: the '
                  'bytes are still stored, and the read no longer fetches '
                  'them. It is the size of the problem, not of the request.')
            print('"rows" and "JSON MiB" are asked of the database over the '
                  'same Berlin-day window summary() queries.')
            print('peak MiB is tracemalloc, so Python allocations only. The '
                  'driver is pymysql -- pure Python, so its buffers ARE '
                  'counted -- but allocator overhead is not: a floor on RSS.')
            print('the database buffer pool is warm in every column here, '
                  'having just been seeded. What "cold" varies is APPLICATION '
                  'state: a fresh client and session, first call measured.')
            print('every seeded row is status=ok, countable, at the current '
                  'schema version and reporting all four counters: the '
                  'maximum-work case for the read, since every row is folded '
                  'into a day rather than skipped.')
            print(f'the newest day is partial -- seeding stops at the anchor '
                  f'({ANCHOR:%H:%M}), as a reader opening it mid-day would '
                  f'find it.')

            # A different question from the "runs" column above, and the two do
            # not have to agree. That column is what the endpoint READ: rows
            # inside a Berlin calendar window, from one walk seeded 32 days
            # back. This is what the schedulers would FIRE over a rolling
            # 24h * days, each window walked from its own start. Two things
            # separate them -- the run duration above all, and then phase,
            # because each window restarts the interval chain.
            print('\nfirings per rolling window, by scheduling model:')
            print(f'{"window":>7} {"start+interval":>15} {"finish+interval":>16}')
            for days in WINDOWS:
                start = ANCHOR - dt.timedelta(days=days)
                drift_free = (len(cycle_starts(start, ANCHOR))
                              + len(reddit_starts(start, ANCHOR)))
                realistic = (len(cycle_starts(start, ANCHOR, CYCLE_DURATION))
                             + len(reddit_starts(start, ANCHOR,
                                                 REDDIT_DURATION)))
                print(f'{days:>7} {drift_free:>15,} {realistic:>16,}')
            weekend_from = WEEKEND_ANCHOR - dt.timedelta(days=1)
            weekend = (len(cycle_starts(weekend_from, WEEKEND_ANCHOR))
                       + len(reddit_starts(weekend_from, WEEKEND_ANCHOR)))
            print(f'one Sunday, drift-free: {weekend:,}')
        finally:
            clear()
            operations._utcnow = original_utcnow              # noqa: SLF001
            print('\nseeded rows removed.')


if __name__ == '__main__':
    main()
