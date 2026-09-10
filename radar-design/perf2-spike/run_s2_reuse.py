"""Task S2: two OS processes reuse one result, and the cold miss measured apart.

Processes, not threads. The thing PERF1 had to retract was a two-reader pair
that turned out to be two threads in one interpreter, so every concurrency
claim here is made with `subprocess.Popen` and nothing else.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s2_reuse.py
"""
import datetime as dt
import json
import os
import statistics
import subprocess
import sys
import time

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import accounts                                        # noqa: E402
import keys                                            # noqa: E402
import producer                                        # noqa: E402
import reader                                          # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import APP_DIR, SPIKE_DIR               # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402

WATCH_A = ['T00001', 'T00002', 'T00003']
WATCH_B = ['T02501', 'T02502']
SAMPLES = 20


def spawn(script, *args):
    return subprocess.Popen(
        [sys.executable, os.path.join(SPIKE_DIR, script)] + list(args),
        cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True)


def reader_args(now, *, window=24, segments='', market='us', user=None,
                sort=None, at=None, repeat=1):
    out = ['--now', now.isoformat(), '--window', str(window),
           '--segments', segments, '--market', market, '--fixture-sources',
           '--repeat', str(repeat)]
    if user is not None:
        out += ['--user', str(user)]
    if sort:
        out += ['--sort', sort]
    if at:
        out += ['--at', at.isoformat()]
    return out


def parse_result(proc):
    out, err = proc.communicate(timeout=600)
    for line in out.splitlines():
        if line.startswith('RESULT '):
            return json.loads(line[len('RESULT '):])
    raise AssertionError('no RESULT from reader\nSTDOUT:%s\nSTDERR:%s'
                         % (out, err))


def wait_ready(engine, key_hash, now, timeout=300):
    began = time.perf_counter()
    while time.perf_counter() - began < timeout:
        row = store.read(engine, key_hash, now)
        if row is not None and row.state == 'ready':
            return time.perf_counter() - began
        time.sleep(0.05)
    raise AssertionError('key never became ready')


def stats(values):
    ordered = sorted(values)
    return (statistics.median(ordered),
            ordered[max(0, round(0.95 * len(ordered)) - 1)],
            ordered[-1])


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        preflight(db, 'S2 -- cross-process reuse, and the cold miss')
        engine = db.engine
        sources = fixture_sources(db)
        now = selections.fixed_now()
        user_a, user_b = accounts.setup(db, (WATCH_A, WATCH_B))
        print('accounts: A=%d watching %s   B=%d watching %s'
              % (user_a, WATCH_A, user_b, WATCH_B))
        store.drop_table(engine)
        store.create_table(engine)

        # ---- Step 1: two independent processes, one build ----------------
        print('\n--- Step 1: two OS processes reuse one published result ---')
        query = Query(sources=list(sources), segments=[], window=24, limit=50,
                      min_venues=1, market='us', sort=None, direction='desc')
        key_hash, key_json = keys.canonical(query)
        assert store.enqueue(engine, key_hash, key_json, now) == 'pending'

        began = time.perf_counter()
        prod = spawn('producer.py', '--owner', 'p1', '--now', now.isoformat(),
                     '--loops', '1')
        prod_out, prod_err = prod.communicate(timeout=900)
        producer_wall = time.perf_counter() - began
        assert 'SERVED' in prod_out, (prod_out, prod_err)
        row = store.read(engine, key_hash, now)
        assert row.state == 'ready', row.state
        print('producer process: %.2fs wall (includes interpreter start),'
              ' build %d ms, fence %s'
              % (producer_wall, row.build_ms,
                 store.read(engine, key_hash, now).state))

        a = spawn('reader.py', *reader_args(now, user=user_a))
        b = spawn('reader.py', *reader_args(now, user=user_a))
        ra, rb = parse_result(a)[0], parse_result(b)[0]
        after = store.read(engine, key_hash, now)
        with engine.connect() as conn:
            fence = conn.execute(sa.text(
                'SELECT fence FROM radar_board_results WHERE key_hash = :k'),
                {'k': key_hash}).scalar()
        print('reader A: %.3fs  rows %s  digest %s'
              % (ra['seconds'], ra['rows'], ra['digest'][:16]))
        print('reader B: %.3fs  rows %s  digest %s'
              % (rb['seconds'], rb['rows'], rb['digest'][:16]))
        assert ra['digest'] == rb['digest'], 'READERS DISAGREE'
        assert not ra['pending'] and not rb['pending']
        assert fence == 1, 'more than one build: fence %s' % fence
        assert after.state == 'ready'
        print('IDENTICAL digests across two processes; fence = 1, so exactly'
              ' ONE build happened')

        # ---- Step 2: ready reads on their own ----------------------------
        print('\n--- Step 2: ready reads, the warm number ---')
        warm_rows = {}
        for window in (12, 24):
            q = Query(sources=list(sources), segments=[], window=window,
                      limit=50, min_venues=1, market='us', sort=None,
                      direction='desc')
            kh, kj = keys.canonical(q)
            store.enqueue(engine, kh, kj, now, warm=True)
            producer.serve_once(engine, 'setup', now, key_hash=kh,
                                query_cls=Query)
            assert store.read(engine, kh, now).state == 'ready'
            took = []
            payload = None
            for _ in range(SAMPLES):
                t0 = time.perf_counter()
                payload = reader.read_payload(
                    engine, {'window': str(window), 'segment': '',
                             'market': 'us', 'sources': ','.join(sources)},
                    now, user_a)
                took.append(time.perf_counter() - t0)
            median, p95, worst = stats(took)
            warm_rows[window] = (median, p95, worst)
            assert not payload['pending']
            assert payload['watching'] == WATCH_A, payload['watching']
            assert payload['watch_rows'], 'watch_rows never exercised'
            print('  %2dh  n=%d  median %6.1f ms  p95 %6.1f ms  max %6.1f ms'
                  '   (%d rows + %d watch rows, target 500 ms)'
                  % (window, SAMPLES, median * 1000, p95 * 1000, worst * 1000,
                     len(payload['rows']), len(payload['watch_rows'])))

        # Same again with NO watches, to say what the per-account half costs.
        for window in (24,):
            took = []
            for _ in range(SAMPLES):
                t0 = time.perf_counter()
                reader.read_payload(
                    engine, {'window': str(window), 'segment': '',
                             'market': 'us', 'sources': ','.join(sources)},
                    now, None)
                took.append(time.perf_counter() - t0)
            median, p95, worst = stats(took)
            print('  %2dh  no account (store read alone): median %6.1f ms '
                  ' p95 %6.1f ms  max %6.1f ms'
                  % (window, median * 1000, p95 * 1000, worst * 1000))

        # ---- Step 3: the first-ever miss, in three parts -----------------
        print('\n--- Step 3: the first-ever miss, three numbers ---')
        cold = Query(sources=list(sources), segments=[], window=24, limit=50,
                     min_venues=1, market='us', sort='lean', direction='desc')
        cold_hash, cold_json = keys.canonical(cold)
        with engine.begin() as conn:
            conn.execute(sa.text(
                'DELETE FROM radar_board_results WHERE key_hash = :k'),
                {'k': cold_hash})
        assert store.read(engine, cold_hash, now) is None

        # A producer daemon is already up and idle, so its interpreter start
        # is NOT counted -- the real producer is a long-running loop.
        daemon = spawn('producer.py', '--owner', 'daemon',
                       '--now', now.isoformat(), '--poll', '400',
                       '--poll-interval', '0.05')
        line = daemon.stdout.readline()
        assert line.strip() == 'READY', line

        t0 = time.perf_counter()
        answer = reader.read_payload(
            engine, {'window': '24', 'segment': '', 'market': 'us',
                     'sort': 'lean', 'sources': ','.join(sources)},
            now, user_a)
        a_seconds = time.perf_counter() - t0
        assert answer['pending'] and answer['rows'] is None
        b_seconds = wait_ready(engine, cold_hash, now)
        t2 = time.perf_counter()
        board = reader.read_payload(
            engine, {'window': '24', 'segment': '', 'market': 'us',
                     'sort': 'lean', 'sources': ','.join(sources)},
            now, user_a)
        second_read = time.perf_counter() - t2
        assert not board['pending'] and board['rows']
        built = store.read(engine, cold_hash, now)
        print('  (a) reader answers `pending`      %8.1f ms'
              '   <- THIS IS NOT A BOARD' % (a_seconds * 1000))
        print('  (b) enqueue -> state=ready        %8.1f ms'
              '   (producer build %d ms)'
              % (b_seconds * 1000, built.build_ms))
        print('  (c) until a reader SEES a board   %8.1f ms'
              '   <- THIS IS THE COLD NUMBER'
              % ((a_seconds + b_seconds + second_read) * 1000))
        print('      the follow-up ready read itself: %.1f ms'
              % (second_read * 1000))
        print('      cold target is 2000 ms; client aborts at 8000 ms')

        # ---- Step 4: two processes race a cold key -----------------------
        print('\n--- Step 4: two processes race one missing key ---')
        race = Query(sources=list(sources), segments=[], window=12, limit=50,
                     min_venues=1, market='de', sort=None, direction='desc')
        race_hash, _ = keys.canonical(race)
        daemon.kill()
        daemon.communicate()
        with engine.begin() as conn:
            conn.execute(sa.text(
                'DELETE FROM radar_board_results WHERE key_hash = :k'),
                {'k': race_hash})
        at = dt.datetime.now() + dt.timedelta(seconds=25)
        procs = [spawn('reader.py', *reader_args(
            now, window=12, market='de', user=user_a, at=at))
            for _ in range(2)]
        results = [parse_result(p)[0] for p in procs]
        for i, r in enumerate(results):
            print('  reader %d started %s -> pending=%s'
                  % (i, r['started_at'], r['pending']))
        raced_hash = results[0]['key_hash']
        assert raced_hash == race_hash, 'the readers keyed something else'
        assert results[0]['key_hash'] == results[1]['key_hash']
        with engine.connect() as conn:
            rows = conn.execute(sa.text(
                'SELECT COUNT(*), MAX(request_count), MAX(state)'
                ' FROM radar_board_results WHERE key_hash = :k'),
                {'k': raced_hash}).first()
        print('  rows for that key: %d   request_count: %d   state: %s'
              % (rows[0], rows[1], rows[2]))
        assert rows[0] == 1, 'two processes made %d rows' % rows[0]
        assert rows[1] == 2, 'both readers should have registered demand'
        prod2 = spawn('producer.py', '--owner', 'p2', '--now',
                      now.isoformat(), '--key', raced_hash, '--loops', '2')
        out2, err2 = prod2.communicate(timeout=900)
        served = [ln for ln in out2.splitlines() if ln.startswith('SERVED')]
        with engine.connect() as conn:
            fence2 = conn.execute(sa.text(
                'SELECT fence FROM radar_board_results WHERE key_hash = :k'),
                {'k': raced_hash}).scalar()
        print('  producer served %d time(s); fence = %d'
              % (len(served), fence2))
        assert fence2 == 1, 'the race queued more than one job'
        print('  EXACTLY ONE ROW AND ONE QUEUED JOB across two OS processes')

        accounts.teardown(db)
        print('\nS2 done. Spike accounts removed.')


if __name__ == '__main__':
    main()
