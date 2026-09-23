"""One MODELLED web worker: the real WSGI app in one OS process. NOT gunicorn.

gunicorn does not run on Windows and there is no WSL on this machine. What
runs here is the unmodified application behind a fixed number of request
threads -- one by default, which models a sync worker; everything beyond that
number queues at the gate, as it would behind a busy sync worker. Nothing of
gunicorn's arbiter, worker lifecycle, graceful reload, signal handling or
request timeouts is modelled or measured.

The flag is whatever RADAR_BOARD_SHARED_RESULTS says in this process's
environment (scale_env defaults it to `on`); the parent sets `off` to model
the old synchronous path.

    cd personal_apps
    <python 3.12> scratchpad/perf3/scale_env.py scratchpad/perf3/serve_perf3.py --port 5081 [--threads 1]

`/perf3/stats` answers outside the gate with the pid, the working set and
the gate's counters.
"""
import argparse
import json
import os
import threading

import scale_env

app = scale_env.bind()

from perf3_common import working_set  # noqa: E402


class Gate:
    """At most `threads` requests execute the app at once; the rest queue."""

    def __init__(self, wsgi_app, threads):
        self.wsgi_app = wsgi_app
        self.threads = threads
        self.semaphore = threading.Semaphore(threads)
        self.lock = threading.Lock()
        self.in_flight = self.waiting = self.served = 0
        self.peak_in_flight = self.peak_queued = 0

    def __call__(self, environ, start_response):
        if environ.get('PATH_INFO') == '/perf3/stats':
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
            return self.wsgi_app(environ, start_response)
        finally:
            with self.lock:
                self.in_flight -= 1
                self.served += 1
            self.semaphore.release()

    def stats(self, start_response):
        body = json.dumps({
            'pid': os.getpid(), 'threads': self.threads,
            'served': self.served, 'peak_in_flight': self.peak_in_flight,
            'peak_queued': self.peak_queued,
            'namespace': scale_env.namespace(),
            'flag': os.environ.get('RADAR_BOARD_SHARED_RESULTS'),
            **working_set(os.getpid()),
        }).encode()
        start_response('200 OK', [('Content-Type', 'application/json'),
                                  ('Content-Length', str(len(body)))])
        return [body]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--threads', type=int, default=1)
    args = parser.parse_args()

    import logging
    from werkzeug.serving import make_server
    # One line per request to the log file is noise, and on a pipe it was a
    # deadlock (PERF2). The radar.board read lines stay.
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    app.wsgi_app = Gate(app.wsgi_app, args.threads)
    # threaded=True: one OS thread per connection; the GATE bounds how many
    # execute the application.
    server = make_server('127.0.0.1', args.port, app, threaded=True)
    print(f'SERVE ready pid={os.getpid()} port={args.port}'
          f' threads={args.threads}'
          f" flag={os.environ.get('RADAR_BOARD_SHARED_RESULTS')}"
          f' namespace={scale_env.namespace()}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
