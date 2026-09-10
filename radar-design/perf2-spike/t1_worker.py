"""One MODELLED worker process: the real WSGI app behind N request threads.

THIS IS NOT GUNICORN. gunicorn does not run on Windows and there is no WSL on
this machine. What runs here is N operating-system threads allowed to execute
the WSGI application concurrently inside one process, with everything beyond N
queued -- which is what `--threads N` on the gthread worker gives a client,
and `--threads 1` models a sync worker. Nothing about gunicorn's arbiter,
worker lifecycle, graceful reload or signal handling is modelled or measured.

The app itself is UNMODIFIED: this is the deployed synchronous board path, on
purpose, because the worker configuration question is about the code that runs
today.

    python t1_worker.py --port 5011 --threads 2
"""
import argparse
import ctypes
import ctypes.wintypes
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()


class _Counters(ctypes.Structure):
    _fields_ = [('cb', ctypes.wintypes.DWORD),
                ('PageFaultCount', ctypes.wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t)]


def working_set():
    """Windows' working set, the local analogue of RSS. (current, peak)."""
    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters),
        counters.cb)
    return counters.WorkingSetSize, counters.PeakWorkingSetSize


class Gate:
    """At most `threads` requests execute the app at once; the rest queue."""

    def __init__(self, app, threads):
        self.app = app
        self.threads = threads
        self.semaphore = threading.Semaphore(threads)
        self.in_flight = 0
        self.peak_in_flight = 0
        self.peak_queued = 0
        self.waiting = 0
        self.peak_pool = 0
        self.served = 0
        self.lock = threading.Lock()

    def __call__(self, environ, start_response):
        if environ.get('PATH_INFO') == '/t1/stats':
            return self.stats(start_response)
        with self.lock:
            self.waiting += 1
            self.peak_queued = max(self.peak_queued, self.waiting)
        self.semaphore.acquire()
        with self.lock:
            self.waiting -= 1
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            return self.app(environ, start_response)
        finally:
            with self.lock:
                self.in_flight -= 1
                self.served += 1
            self.semaphore.release()

    def stats(self, start_response):
        current, peak = working_set()
        body = json.dumps({
            'threads': self.threads,
            'pid': os.getpid(),
            'peak_in_flight': self.peak_in_flight,
            'peak_queued': self.peak_queued,
            'peak_pool_checkedout': self.peak_pool,
            'served': self.served,
            'working_set': current,
            'peak_working_set': peak,
        }).encode()
        start_response('200 OK', [('Content-Type', 'application/json'),
                                  ('Content-Length', str(len(body)))])
        return [body]


def sample_pool(gate, app):
    """Peak checked-out connections, sampled. SQLAlchemy exposes the count
    but not a high-water mark, so one has to be kept."""
    from extensions import db
    while True:
        try:
            with app.app_context():
                out = db.engine.pool.checkedout()
            gate.peak_pool = max(gate.peak_pool, out)
        except Exception:                               # noqa: BLE001
            pass
        time.sleep(0.005)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, required=True)
    ap.add_argument('--threads', type=int, required=True)
    args = ap.parse_args()

    from werkzeug.serving import make_server

    from app import app
    gate = Gate(app.wsgi_app, args.threads)
    app.wsgi_app = gate
    sampler = threading.Thread(target=sample_pool, args=(gate, app),
                               daemon=True)
    sampler.start()
    # threaded=True gives one OS thread per connection; the GATE, not the
    # server, is what bounds concurrency to `threads`.
    server = make_server('127.0.0.1', args.port, app, threaded=True)
    print('WORKER %d ready on %d with %d request thread(s)'
          % (os.getpid(), args.port, args.threads), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
