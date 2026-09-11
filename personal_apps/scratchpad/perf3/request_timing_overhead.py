"""Request-timing overhead: the enabled hooks against no hooks, per request.

Task 9a. Run from personal_apps/:

    PYTHONPATH=. py -3.12 scratchpad/perf3/request_timing_overhead.py

Two minimal Flask apps with the same cheap route, `/ping/<name>` -- a dynamic
rule, so the label is a template, as on every Radar API route. One is given
the hooks by `request_timing.install` with the variable on; the other is
handed an empty environment, which registers nothing, which is what "off" is.
Each round sends --requests requests to each through the Flask test client,
alternating one and one with the order swapped every pair, so both halves see
the same machine; --warmup pairs go first and are not counted.

The enabled handler writes to os.devnull: a real write and flush per line,
which is what the handler does, and no terminal, which production does not
have either. journald's side of the line -- a socket write on Linux, and its
rate limit -- is not modelled. No database and no network: the hooks cost the
same on any route, and a cheap route keeps the difference visible.

Prints per-request median and p95 in microseconds for each app and the
difference, per round, then the rounds as JSON.
"""
import argparse
import io
import json
import logging
import math
import os
import platform
import re
import statistics
import sys
import time
from importlib.metadata import version

from flask import Flask

import request_timing

URL = '/ping/NVDA?window=24'
LINE = re.compile(r'app\.request request method=GET route=/ping/<name> '
                  r'status=200 bytes=2 ms=\d+\.\d\n')


def _client(on):
    app = Flask(f'overhead_{"on" if on else "off"}')

    @app.route('/ping/<name>')
    def ping(name):
        return 'ok'

    env = {request_timing.ENV_VAR: '1'} if on else {}
    assert request_timing.install(app, env=env) is on
    return app.test_client()


def _p95(samples):
    """Nearest rank."""
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _check(on, off, handler, sink):
    """One request to each on a side stream: the enabled app writes exactly
    one line, the other none. Outside the timed loop, so it costs it nothing."""
    probe = io.StringIO()
    handler.setStream(probe)
    try:
        on.get(URL)
        written_on = probe.getvalue()
        off.get(URL)
        written_off = probe.getvalue()[len(written_on):]
    finally:
        handler.setStream(sink)
    assert LINE.fullmatch(written_on), written_on
    assert written_off == '', written_off


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--requests', type=int, default=1000)
    parser.add_argument('--warmup', type=int, default=200)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args(argv)

    sink = open(os.devnull, 'w', encoding='utf-8')
    real_stdout, sys.stdout = sys.stdout, sink   # the handler binds sys.stdout
    try:
        on = _client(True)
    finally:
        sys.stdout = real_stdout
    off = _client(False)
    handler = next(handler for handler in logging.getLogger('app.request').handlers
                   if getattr(handler, 'stream', None) is sink)

    print(f'python {platform.python_version()}, flask {version("flask")}, '
          f'werkzeug {version("werkzeug")}, {platform.platform()}, '
          f'{os.cpu_count()} logical CPUs; enabled handler -> os.devnull')
    _check(on, off, handler, sink)
    for _ in range(args.warmup):
        on.get(URL)
        off.get(URL)

    pairs = ((('off', off), ('on', on)), (('on', on), ('off', off)))
    rounds = []
    for number in range(1, args.rounds + 1):
        samples = {'off': [], 'on': []}
        for index in range(args.requests):
            for name, client in pairs[index % 2]:
                started = time.perf_counter_ns()
                response = client.get(URL)
                elapsed = time.perf_counter_ns() - started
                if response.status_code != 200:
                    raise SystemExit(f'{name}: status {response.status_code}')
                samples[name].append(elapsed / 1000)
        row = {'round': number, 'requests_each': args.requests}
        for name in ('off', 'on'):
            row[f'{name}_median_us'] = round(statistics.median(samples[name]), 1)
            row[f'{name}_p95_us'] = round(_p95(samples[name]), 1)
        row['median_delta_us'] = round(row['on_median_us'] - row['off_median_us'], 1)
        row['p95_delta_us'] = round(row['on_p95_us'] - row['off_p95_us'], 1)
        rounds.append(row)
        print(f"round {number}: off median {row['off_median_us']} us, "
              f"p95 {row['off_p95_us']} us | on median {row['on_median_us']} us, "
              f"p95 {row['on_p95_us']} us | on - off: median "
              f"{row['median_delta_us']} us, p95 {row['p95_delta_us']} us")
    _check(on, off, handler, sink)                 # and still so afterwards
    print(json.dumps(rounds))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
