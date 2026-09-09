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
        'catchup_depth': {name: 0 for name in roots},
        'intake_reasons': {name: _reasons() for name in roots},
    })


def reddit_envelope():
    """What `radar_reddit` writes: every configured sub in per_source, because
    arctic_shift.fetch iterates all of REDDIT_SUBS in one cycle -- but a single
    'reddit' key in aggregate_status and catchup_depth."""
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
    return [{'id': str(uuid.uuid4()), 'started_at': when,
             'finished_at': when + dt.timedelta(seconds=38), 'status': 'ok',
             'summary_json': body, 'error_code': None}
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


def timed(call, repeats=5):
    """Best and median of N, after one untimed warm-up. Both reported: the best
    is what the work costs on a warm buffer pool, which is a LOWER bound on a
    cold one."""
    call()
    runs = []
    for _ in range(repeats):
        began = time.perf_counter()
        call()
        runs.append((time.perf_counter() - began) * 1000)
    return min(runs), statistics.median(runs)


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
    """Python's own peak during one call. `summary()` ends in .all(), so every
    row AND every decoded dict is live at once -- on a small host that is the
    number that kills the process, not the seconds."""
    gc.collect()
    tracemalloc.start()
    call()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1048576


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
        print()

        clear()
        try:
            # Two days wider than the widest window: summary() queries Berlin
            # calendar days, whose start can precede ANCHOR - days.
            widest = max(WINDOWS)
            seed_from = ANCHOR - dt.timedelta(days=widest + 2)
            cycles = cycle_starts(seed_from, ANCHOR)
            reddits = reddit_starts(seed_from, ANCHOR)
            total = seed(rows_for(cycles, cycle_body)
                         + rows_for(reddits, reddit_body))
            print(f'seeded {total:,} runs over {widest + 2} days '
                  f'(cycle {len(cycles):,} + reddit {len(reddits):,})')
            # As the server stores it, not as Python would re-serialize it.
            # Exactly two distinct bodies are seeded, so the extremes name
            # them -- and both walks start at the same instant, so probing by
            # timestamp would read whichever row the server happened to return.
            length = sa.func.length(RadarIngestRun.summary_json)
            smallest, largest = db.session.execute(
                sa.select(sa.func.min(length), sa.func.max(length))
                .where(RadarIngestRun.started_at < dt.datetime(2020, 1, 1))
            ).one()
            print(f'  one radar_cycle envelope:  {smallest:,} bytes')
            print(f'  one radar_reddit envelope: {largest:,} bytes')
            print()

            import features.radar.routes.operations as operations
            operations._utcnow = lambda: ANCHOR              # noqa: SLF001
            app.config['TESTING'] = True
            admin = AppUser.query.filter_by(is_admin=True).order_by(
                AppUser.id).first()
            if admin is None:
                raise SystemExit('no admin user in the disposable database')

            print(f'{"window":>7} {"runs":>8} {"MiB":>6} {"summary ms":>13} '
                  f'{"endpoint ms":>13} {"no-JSON ms":>11} {"peak MiB":>9}')
            for days in WINDOWS:
                window_from, window_to = window_bounds(days)
                rows, byte_total = measured(window_from, window_to)

                best, median = timed(lambda d=days: activity.summary(ANCHOR, d))
                bare_best, _ = timed(
                    lambda f=window_from, t=window_to: control(f, t))
                peak = peak_mib(lambda d=days: activity.summary(ANCHOR, d))

                with app.test_client() as client:
                    with client.session_transaction() as session:
                        session['user_id'] = admin.id

                    def call(d=days):
                        response = client.get(f'/radar/api/activity?days={d}')
                        assert response.status_code == 200, response.status_code
                        return response.get_data()

                    endpoint_best, endpoint_median = timed(call)

                print(f'{days:>7} {rows:>8,} {byte_total / 1048576:>6.1f} '
                      f'{best:>9.0f}/{median:<3.0f} '
                      f'{endpoint_best:>9.0f}/{endpoint_median:<3.0f} '
                      f'{bare_best:>11.0f} {peak:>9.1f}')

            print('\nms columns are best/median of five on a warm buffer pool, '
                  'after a warm-up.')
            print('"runs" and "MiB" are asked of the database over the same '
                  'Berlin-day window summary() queries.')
            print('every seeded row is status=ok with a full envelope, and '
                  'every source reports all 8 intake reasons: an upper bound.')
            print(f'the newest day is partial -- seeding stops at the anchor '
                  f'({ANCHOR:%H:%M}), as a reader opening it mid-day would '
                  f'find it.')

            # A different question from the "runs" column above, and the two do
            # not have to agree. That column is what the endpoint READ: rows
            # inside a Berlin calendar window, from one walk seeded 32 days
            # back. This is what the schedulers would FIRE over a rolling
            # 24h * days, each window walked from its own start, so the
            # interval chain restarts at a different phase.
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
            print('\nseeded rows removed.')


if __name__ == '__main__':
    main()
