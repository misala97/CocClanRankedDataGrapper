"""Two readers through the endpoint's own cache path, five pairs per window.

The acceptance battery imported `api.py` before the cache-write/event-order
fix landed, so its endpoint-path numbers came from the racy version. This
re-measures the same thing against the fixed code, and repeats it five times
per window because the race was a scheduling race: one coalesced pair proves
nothing, five do.
"""
import datetime as dt
import statistics
import threading
import time

import sqlalchemy as sa

from app import app
from extensions import db
from features.radar.routes import api as api_mod

DB = 'personal_apps_radar_perf1'
PAIRS = 5


def pair(sources, hours, now):
    api_mod.board_cache.clear()
    api_mod._board_builds.clear()
    builds = []
    real_build = api_mod.board_mod.build

    def counted(*args, **kwargs):
        builds.append(1)
        return real_build(*args, **kwargs)

    api_mod.board_mod.build = counted
    try:
        asked = api_mod.Query(sources=sources, segments=(), window=hours,
                              limit=50, min_venues=1, market='us',
                              sort=None, direction='desc')
        took = {}
        ready = threading.Barrier(2)

        def reader(name):
            with app.app_context():
                ready.wait()
                t0 = time.perf_counter()
                api_mod._build_board(asked, now)
                took[name] = time.perf_counter() - t0
                db.session.remove()

        threads = [threading.Thread(target=reader, args=(n,)) for n in 'AB']
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return max(took.values()), len(builds)
    finally:
        api_mod.board_mod.build = real_build


def main():
    with app.app_context():
        assert db.engine.url.database == DB, db.engine.url.database
        index = db.session.execute(sa.text(
            'SELECT COUNT(*) FROM information_schema.STATISTICS'
            " WHERE TABLE_SCHEMA=:s AND TABLE_NAME='radar_bucket_sources'"
            " AND INDEX_NAME='ix_radar_bucket_sources_agg'"),
            {'s': DB}).scalar() > 0
        print('database: %s   covering index: %s'
              % (DB, 'present' if index else 'ABSENT'))
        sources = [r[0] for r in db.session.execute(sa.text(
            'SELECT DISTINCT source FROM radar_bucket_sources')).fetchall()]
        now = dt.datetime.utcnow().replace(microsecond=0)

        for hours in (12, 24):
            slowest = []
            duplicated = 0
            for _ in range(PAIRS):
                worst, builds = pair(sources, hours, now)
                slowest.append(worst)
                if builds != 1:
                    duplicated += 1
            print('  %2dh  %d pairs  slower reader: median %5.2fs  max %5.2fs'
                  '   duplicate builds: %d/%d'
                  % (hours, PAIRS, statistics.median(slowest), max(slowest),
                     duplicated, PAIRS), flush=True)


if __name__ == '__main__':
    main()
