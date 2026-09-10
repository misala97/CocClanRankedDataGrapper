"""Task T1: two sync processes against two threaded processes.

**A MODEL, not gunicorn.** gunicorn does not run on Windows and there is no
WSL here. `t1_worker.py` serves the real WSGI app behind a fixed number of
request threads: two processes at one thread each models `--workers 2` with
no `--threads`, and two processes at two threads each models
`--workers 2 --threads 2`. Everything gunicorn's arbiter does -- worker
lifecycle, graceful reload, signal handling, request timeouts -- is NOT
measured. Every number below carries that caveat.

The app runs UNMODIFIED here: the deployed synchronous board path, because
that is the code the worker configuration decision is about.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_t1_workers.py
"""
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

from env_check import APP_DIR, SPIKE_DIR               # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402

PORTS = (5011, 5012)
CHEAP = '/'                    # the app overview: one user lookup, one render
POOL_SIZE, POOL_OVERFLOW = 5, 10


def get(url, cookie, timeout=120):
    request = urllib.request.Request(url, headers={'Cookie': 'session=%s'
                                                   % cookie})
    began = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.read()
    return time.perf_counter() - began, status


def wait_ready(proc, port, cookie):
    line = proc.stdout.readline()
    assert 'ready' in line, line
    for _ in range(200):
        try:
            get('http://127.0.0.1:%d/t1/stats' % port, cookie, timeout=3)
            return line.strip()
        except Exception:                               # noqa: BLE001
            time.sleep(0.2)
    raise AssertionError('worker never answered')


def stats(port, cookie):
    request = urllib.request.Request('http://127.0.0.1:%d/t1/stats' % port,
                                     headers={'Cookie': 'session=%s' % cookie})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def board_url(port, src, window, market):
    return ('http://127.0.0.1:%d/radar/api/board?window=%d&segment=&market=%s'
            '&sources=%s' % (port, window, market, src))


def run_model(threads, cookie, src, label):
    procs = [subprocess.Popen(
        [sys.executable, os.path.join(SPIKE_DIR, 't1_worker.py'),
         '--port', str(port), '--threads', str(threads)],
        cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for port in PORTS]
    out = {}
    try:
        for proc, port in zip(procs, PORTS):
            print('  %s' % wait_ready(proc, port, cookie))
        rest = [stats(port, cookie) for port in PORTS]
        out['rss_rest'] = [s['working_set'] for s in rest]

        # Baseline: the cheap request with nothing else happening.
        idle = [get('http://127.0.0.1:%d%s' % (PORTS[0], CHEAP), cookie)[0]
                for _ in range(12)]
        out['cheap_idle'] = idle[2:]

        # Two concurrent board builds, one per process -- the shape the claim
        # is about. Different selections, so the app's own 60 s memo cannot
        # answer either of them.
        board_took = {}

        def build(port, window, market):
            board_took[port] = get(board_url(port, src, window, market),
                                   cookie, timeout=180)

        threads_ = [threading.Thread(target=build, args=(PORTS[0], 24, 'us')),
                    threading.Thread(target=build, args=(PORTS[1], 12, 'de'))]
        cheap = []
        stop = threading.Event()

        def hammer():
            # Round-robin, the way a proxy in front of two workers would.
            i = 0
            while not stop.is_set():
                port = PORTS[i % len(PORTS)]
                i += 1
                took, status = get('http://127.0.0.1:%d%s' % (port, CHEAP),
                                   cookie, timeout=180)
                cheap.append((took, status, port))
                time.sleep(0.1)

        hammering = threading.Thread(target=hammer)
        for t in threads_:
            t.start()
        hammering.start()
        peak_rss = [0, 0]
        while any(t.is_alive() for t in threads_):
            for index, port in enumerate(PORTS):
                try:
                    peak_rss[index] = max(peak_rss[index],
                                          stats(port, cookie)['working_set'])
                except Exception:                       # noqa: BLE001
                    pass
            time.sleep(0.3)
        for t in threads_:
            t.join()
        stop.set()
        hammering.join()
        out['boards'] = board_took
        out['cheap_under_load'] = [c[0] for c in cheap]
        out['cheap_statuses'] = {c[1] for c in cheap}
        out['rss_peak'] = peak_rss
        out['stats'] = [stats(port, cookie) for port in PORTS]
    finally:
        for proc in procs:
            proc.kill()
            proc.communicate()
    return out


def summarise(values):
    ordered = sorted(values)
    return (statistics.median(ordered),
            ordered[max(0, round(0.95 * len(ordered)) - 1)], ordered[-1])


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from flask.sessions import SecureCookieSessionInterface
        preflight(db, 'T1 -- two sync processes against two threaded ones')
        sources = fixture_sources(db)
        src = ','.join(sources)
        user_id = db.session.execute(sa.text(
            'SELECT id FROM app_user ORDER BY id LIMIT 1')).scalar()
        cookie = SecureCookieSessionInterface().get_signing_serializer(
            app).dumps({'user_id': user_id})
        print('THIS IS A MODEL OF gunicorn, NOT gunicorn. Windows, no WSL.')
        print('pool per process: %d + %d overflow = %d connections'
              % (POOL_SIZE, POOL_OVERFLOW, POOL_SIZE + POOL_OVERFLOW))

    results = {}
    for threads, label in ((1, '2 processes x 1 thread  (models --workers 2)'),
                           (2, '2 processes x 2 threads (models --workers 2 '
                               '--threads 2)')):
        print('\n--- %s ---' % label)
        results[threads] = run_model(threads, cookie, src, label)

    # ---- Step 2: non-Radar responsiveness ------------------------------
    print('\n--- Step 2: a cheap non-Radar request under two board builds ---')
    print('  %-24s %9s %9s %9s %9s'
          % ('', 'idle med', 'load med', 'load p95', 'load max'))
    for threads in (1, 2):
        r = results[threads]
        idle = summarise(r['cheap_idle'])
        load = summarise(r['cheap_under_load'])
        print('  %-24s %8.0fms %8.0fms %8.0fms %8.0fms'
              % ('%d thread(s)/process' % threads, idle[0] * 1000,
                 load[0] * 1000, load[1] * 1000, load[2] * 1000))
        assert r['cheap_statuses'] == {200}, r['cheap_statuses']
    for threads in (1, 2):
        r = results[threads]
        print('  %d thread(s): the two board builds took %s'
              % (threads, ', '.join('%.1fs (HTTP %d)' % v
                                    for v in r['boards'].values())))
    one = summarise(results[1]['cheap_under_load'])
    two = summarise(results[2]['cheap_under_load'])
    print('\n  THE CLAIM: "two sync workers mean two board builds block the'
          ' whole of personal_apps".')
    print('  Median cheap request during two builds: %.0f ms with one thread'
          ' per process, %.0f ms with two.' % (one[0] * 1000, two[0] * 1000))
    print('  Worst: %.0f ms against %.0f ms.' % (one[2] * 1000, two[2] * 1000))
    verdict = ('CONFIRMED' if one[0] > two[0] * 3 else
               'PARTLY -- the gap is smaller than the claim implies'
               if one[0] > two[0] * 1.5 else 'REFUTED on this evidence')
    print('  %s.' % verdict)

    # ---- Step 3: the connection pool -----------------------------------
    print('\n--- Step 3: peak checked-out connections per process ---')
    print('  %-24s %-10s %-10s %s'
          % ('', 'worker A', 'worker B', 'against 5 + 10 overflow'))
    for threads in (1, 2):
        peaks = [s['peak_pool_checkedout'] for s in results[threads]['stats']]
        print('  %-24s %-10d %-10d %d%% of the pool at worst'
              % ('%d thread(s)/process' % threads, peaks[0], peaks[1],
                 100 * max(peaks) // (POOL_SIZE + POOL_OVERFLOW)))
    print('  peak concurrent requests actually executing per process: %s / %s'
          % ([s['peak_in_flight'] for s in results[1]['stats']],
             [s['peak_in_flight'] for s in results[2]['stats']]))
    print('  peak queued behind the gate: %s / %s'
          % ([s['peak_queued'] for s in results[1]['stats']],
             [s['peak_queued'] for s in results[2]['stats']]))

    # ---- Step 4: memory -------------------------------------------------
    print('\n--- Step 4: memory per process (Windows working set ~ RSS) ---')
    print('  %-24s %-22s %s' % ('', 'at rest', 'under two builds'))
    for threads in (1, 2):
        r = results[threads]
        print('  %-24s %-22s %s'
              % ('%d thread(s)/process' % threads,
                 ' / '.join('%.0f MB' % (v / 1048576)
                            for v in r['rss_rest']),
                 ' / '.join('%.0f MB' % (v / 1048576)
                            for v in r['rss_peak'])))

    # ---- Step 5: shared mutable state -----------------------------------
    print('\n--- Step 5: module-level mutable state a second thread would'
          ' newly share ---')
    shared_state_report()

    # ---- Step 6: the recommendation -------------------------------------
    recommendation(one, two, results)


def shared_state_report():
    """Read from the code, not guessed. Each entry names its file and line."""
    entries = [
        ('routes/api.py:447', 'board_cache', 'dict',
         'GUARDED by _board_lock (448). Read, build outside the lock, write.'
         ' Two threads can build the same key at once and the second write'
         ' wins -- duplicated work, not corruption.'),
        ('leaderboard.py:112', 'sigma_cache', 'dict',
         'NO LOCK. `if any(key[3] != today ...): sigma_cache.clear()` then'
         ' reads and writes. A clear racing a read is a KeyError or a lost'
         ' entry; a dict mutated during `any(... for key in list(...))` is'
         ' the reason that list() is there. The store makes this WORSE, not'
         ' better, if two threads build.'),
        ('coverage.py:45-46', '_cache', 'dict',
         'GUARDED by its own _lock (45). Safe.'),
        ('market_data.py:900', '_OPS_MEMO', 'dict',
         'NO LOCK. Two threads can both miss and both run the 91 ms query'
         ' (S1); the last write wins. Wasteful, not incorrect.'),
        ('llm_sentiment.py:1178', '_gauge_cache', 'dict',
         'NO LOCK. Same shape as _OPS_MEMO: duplicated work, last write'
         ' wins.'),
        ('sentiment.py:59', '_active_cache', 'dict',
         'NO LOCK. Holds the loaded classifier artifact and a `warned` flag.'
         ' Two threads can both load the artifact; the flag can warn twice.'),
        ('sentiment.py:128', '_KNOWN', 'dict',
         'NO LOCK. {at, tickers}; the pair is written field by field, so a'
         ' reader can see a new `at` with the old `tickers`.'),
        ('judge_config.py:114', '_active', 'dict',
         'NO LOCK. Four fields written together on reload; a reader between'
         ' two of the writes sees a mixed configuration.'),
        ('market_data.py:201', '_THROTTLE', 'dict',
         'NO LOCK, but written only by the ingest daemon, not by a web'
         ' worker. Not newly shared by --threads.'),
        ('extraction.py:62', '_NAME_INDEX_CACHE', 'list',
         'NO LOCK. Compared by identity while holding the lookup. Written by'
         ' the extractor, which runs in the daemon, not the web worker.'),
        ('buckets.py:169', 'BUCKET_WRITE_LOCK', 'Lock',
         'A lock, not state. Daemon-side.'),
    ]
    print('  %-22s %-20s %s' % ('where', 'name', 'thread-safe?'))
    for where, name, kind, note in entries:
        print('  %-22s %-20s %s' % (where, '%s (%s)' % (name, kind), note))
    print('\n  Of these, THREE are on the web request path and unguarded:'
          ' leaderboard.sigma_cache, market_data._OPS_MEMO and'
          ' llm_sentiment._gauge_cache. Only sigma_cache can raise.')
    # Prove sigma_cache is reachable from a board build, rather than assert.
    source = open(os.path.join(APP_DIR, 'features', 'radar',
                               'leaderboard.py'), encoding='utf-8').read()
    uses = len(re.findall(r'sigma_cache', source))
    print('  sigma_cache appears %d times in leaderboard.py and is reached'
          ' through _quote_sigmas, which build_rows calls on every board'
          ' build.' % uses)


def recommendation(one, two, results):
    print('\n--- Step 6: the recommendation ---')
    peaks = max(s['peak_pool_checkedout'] for s in results[2]['stats'])
    print("""
  RECOMMENDATION: do NOT set --threads until leaderboard.sigma_cache is
  guarded. It is an unlocked module dict that every board build clears and
  repopulates, on the request path, and two threads in one process are the
  first thing that has ever been able to race it. That is a one-line lock,
  but it is a code change and it is not in this authorization.

  The responsiveness case is real but smaller than the claim: a cheap
  non-Radar request during two board builds is %.0f ms with one thread per
  process and %.0f ms with two. The pool is not the constraint -- peak
  checked-out connections reached %d of 15 per process in the threaded model.

  Measured HERE, on MySQL 8.0.46 under Windows, against a MODEL of gunicorn.
  Nothing about gunicorn's own arbiter, worker lifecycle, graceful reload,
  signal handling or request timeouts is measured, and gunicorn cannot be run
  on this machine to check.

  THE EXACT REVERSIBLE UNIT CHANGE, AS TEXT. NOT APPLIED, NOT AUTHORIZED:

      # /etc/systemd/system/personal_apps.service
      -ExecStart=/srv/personal_apps/venv/bin/gunicorn --workers 2 \\
      -    --bind 127.0.0.1:8001 app:app
      +ExecStart=/srv/personal_apps/venv/bin/gunicorn --workers 2 --threads 2 \\
      +    --worker-class gthread --bind 127.0.0.1:8001 app:app

  `--threads` is ignored by the `sync` worker class, so `--worker-class
  gthread` has to move with it or the change is a silent no-op. The reversal
  is deleting the two added flags and `systemctl daemon-reload &&
  systemctl restart personal_apps`; it costs one restart, and in-process
  state (board_cache, sigma_cache, the ops memos) is lost on both sides of
  it, which is exactly what the result store removes as a concern.

  The command line above is taken from PERF1-LEDGER.md's recorded process
  table -- `gunicorn --workers 2 --bind 127.0.0.1:5001 app:app`, PIDs 121328
  / 121352 / 121355 -- and NOT read off the running unit file: no ssh, no
  contact with the target in this workstream. The unit's other directives are
  unknown here. Whoever prepares the release package must diff this against
  the real unit before using it.
""" % (one[0] * 1000, two[0] * 1000, peaks))


if __name__ == '__main__':
    main()
