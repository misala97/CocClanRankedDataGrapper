"""How much the activity endpoint actually has to read, and how long it takes.

Repeatable. Run it from personal_apps with PYTHONPATH=. against the disposable
database; it refuses to run against anything else, seeds its own rows in a
window no real data occupies, measures, and removes them again.

    PYTHONPATH=. py -3.12 scratchpad/bench_activity.py

Why it exists: the first capacity note guessed 2,880 runs over 30 days from the
board archive's 15-minute cadence. That is the wrong writer. Runs are written by
`tick`, and `tick` is called by TWO scheduler jobs on their own cadences --
`radar_cycle`, whose interval follows the NYSE session, and `radar_reddit`,
which is fixed. The count below is derived by walking the real calendar through
the real interval table rather than by dividing an hour by a guess.
"""
import datetime as dt
import json
import statistics
import sys
import time
import uuid

sys.path.insert(0, '.')

from app import app                                        # noqa: E402
from extensions import db                                  # noqa: E402
from features.radar import activity, market_calendar       # noqa: E402
from features.radar.config import SOURCES, expand_sources  # noqa: E402
from models import RadarIngestRun                          # noqa: E402
from run_radar_ingest import INTERVALS, FALLBACK_INTERVAL  # noqa: E402
from features.radar.config import (                        # noqa: E402
    ARCTIC_SHIFT_INTERVAL_SECONDS, CYCLE_SECONDS, REDDIT_FETCHER,
    REDDIT_INTERVAL_SECONDS)

EXPECTED_DB = 'personal_apps_radar_wt'

# 2019: before Radar existed, so nothing real can be in the window and the
# cleanup can be scoped by date rather than by collecting ids.
#
# A WEDNESDAY, deliberately. The session cycle runs at 180s while the market is
# open and 1800s overnight and at weekends, so a one-day window anchored on a
# Sunday reports 48 cycle runs and a weekday one reports 280 -- nearly six
# times as many. Anchoring on a weekend would have made the smallest window
# look like the cheapest case by a factor the endpoint does not enjoy in
# practice.
ANCHOR = dt.datetime(2019, 6, 26, 12, 0)      # Wednesday
WEEKEND_ANCHOR = dt.datetime(2019, 6, 30, 12, 0)   # Sunday, for contrast
WINDOWS = (1, 7, 30)


def reddit_interval() -> int:
    return (ARCTIC_SHIFT_INTERVAL_SECONDS if REDDIT_FETCHER == 'arctic_shift'
            else REDDIT_INTERVAL_SECONDS)


def cycle_starts(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    """When `radar_cycle` would have fired, by the rule it actually uses.

    _scheduled_cycle reschedules itself after every run with
    interval_for(current_state(now)), so the cadence is a function of the NYSE
    session at each firing -- 180s while the market is open or in pre-market,
    600s after hours, 1800s overnight and at weekends.
    """
    out, when = [], start
    while when < end:
        out.append(when)
        state = market_calendar.session_state(when.replace(tzinfo=dt.timezone.utc))
        when += dt.timedelta(seconds=INTERVALS.get(state, FALLBACK_INTERVAL))
    return out


def reddit_starts(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    """`radar_reddit` runs on a fixed interval and calls the same tick."""
    step = dt.timedelta(seconds=reddit_interval())
    out, when = [], start
    while when < end:
        out.append(when)
        when += step
    return out


def envelope(sources: list[str]) -> dict:
    """A summary of the shape `ingest.run_cycle` returns, at the real width.

    Constructed, not captured -- this machine has no production run to copy --
    but every key is run_cycle's own and every per-source map is keyed by the
    ACTUAL expanded source list, which is what makes it representative in the
    only dimension that matters here: size.
    """
    return {
        'schema_version': activity.SCHEMA_VERSION,
        'summary': {
            'posts_seen': 1287, 'posts_new': 143, 'mentions': 96,
            'buckets_written': 41,
            'per_source': {name: 'ok' for name in sources},
            'aggregate_status': {name: 'ok' for name in sources},
            'catchup_depth': {name: 0 for name in sources},
            'intake_reasons': {
                name: {'no_ticker': 812, 'low_confidence': 61,
                       'duplicate': 24, 'too_short': 9}
                for name in sources
            },
        },
    }


def seed(starts: list[dt.datetime], body: dict) -> int:
    rows = [{'id': str(uuid.uuid4()), 'started_at': when,
             'finished_at': when + dt.timedelta(seconds=38), 'status': 'ok',
             'summary_json': body, 'error_code': None}
            for when in starts]
    for chunk in range(0, len(rows), 500):
        db.session.bulk_insert_mappings(RadarIngestRun, rows[chunk:chunk + 500])
        db.session.commit()
    return len(rows)


def clear() -> None:
    db.session.rollback()
    RadarIngestRun.query.filter(
        RadarIngestRun.started_at < dt.datetime(2020, 1, 1)).delete(
            synchronize_session=False)
    db.session.commit()


def timed(call, repeats=5):
    """Best of N, after one untimed warm-up. Best rather than mean: the
    interesting number is what the work costs, not what the machine was also
    doing."""
    call()
    runs = []
    for _ in range(repeats):
        began = time.perf_counter()
        call()
        runs.append((time.perf_counter() - began) * 1000)
    return min(runs), statistics.median(runs)


def main() -> None:
    with app.app_context():
        resolved = db.engine.url.database
        assert resolved == EXPECTED_DB, f'refusing to run against {resolved!r}'
        print(f'database: {resolved}\n')

        expanded = sorted(expand_sources(SOURCES))
        body = envelope(expanded)
        one = len(json.dumps(body, separators=(',', ':')).encode())
        print(f'configured feeds: {len(SOURCES)} roots -> {len(expanded)} '
              f'concrete sources')
        print(f'reddit reader: {REDDIT_FETCHER} @ {reddit_interval()}s; '
              f'session cycle floor {CYCLE_SECONDS}s')
        print(f'one envelope: {one:,} bytes of JSON\n')

        clear()
        rows_seeded = 0
        report = []
        for days in WINDOWS:
            start = ANCHOR - dt.timedelta(days=days)
            cycles = cycle_starts(start, ANCHOR)
            reddits = reddit_starts(start, ANCHOR)
            # Only the rows this window needs that are not already there: the
            # windows nest, so seed the widest once and slice by date.
            report.append((days, len(cycles), len(reddits)))

        widest = max(WINDOWS)
        start = ANCHOR - dt.timedelta(days=widest)
        all_starts = sorted(cycle_starts(start, ANCHOR)
                            + reddit_starts(start, ANCHOR))
        rows_seeded = seed(all_starts, body)
        print(f'seeded {rows_seeded:,} runs over {widest} days\n')

        print(f'{"window":>7} {"runs":>9} {"JSON MiB":>9} {"summary ms":>12} '
              f'{"endpoint ms":>12}')
        for days, cycles, reddits in report:
            window_start = ANCHOR - dt.timedelta(days=days)
            in_window = [when for when in all_starts if when >= window_start]
            bytes_total = len(in_window) * one

            best, median = timed(lambda d=days: activity.summary(ANCHOR, d))

            import features.radar.routes.operations as operations
            operations._utcnow = lambda: ANCHOR          # noqa: SLF001
            app.config['TESTING'] = True
            from models import AppUser
            admin = AppUser.query.filter_by(is_admin=True).order_by(
                AppUser.id).first()
            with app.test_client() as client:
                with client.session_transaction() as session:
                    session['user_id'] = admin.id

                def call(d=days):
                    response = client.get(f'/radar/api/activity?days={d}')
                    assert response.status_code == 200, response.status_code
                    return response.get_data()

                endpoint_best, endpoint_median = timed(call)

            print(f'{days:>7} {len(in_window):>9,} '
                  f'{bytes_total / 1048576:>9.1f} '
                  f'{best:>8.0f}/{median:<3.0f} '
                  f'{endpoint_best:>8.0f}/{endpoint_median:<3.0f}')
            print(f'         (cycle {cycles:,} + reddit {reddits:,})')

        print('\nms columns are best/median of five, after a warm-up.')
        clear()
        print('seeded rows removed.')


if __name__ == '__main__':
    main()
