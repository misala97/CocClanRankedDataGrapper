"""What every Task 8 script shares: statistics, processes, HTTP, memory,
accounts and the store's rows.

Processes, not threads, wherever a claim is about concurrency: PERF1 had to
retract a two-reader pair that turned out to be two threads in one
interpreter. Children are started with the interpreter itself (never the
`py.exe` launcher, which would be the PID killed and measured) through
`scale_env.py`, and they write to a log FILE: a child writing into a pipe
nobody drains deadlocks once Windows' pipe buffer fills, which is what
PERF2's first worker run did.
"""
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import os
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import sqlalchemy as sa

HERE = pathlib.Path(__file__).resolve().parent
APP_DIR = HERE.parents[1]
SCALE_ENV = HERE / 'scale_env.py'
DEFAULT_OUT = pathlib.Path(tempfile.gettempdir()) / 'radar-perf3-task8'
USER_PREFIX = 'perf3_'


# --- statistics ---------------------------------------------------------------

def summary(values):
    """(n, median, p95, max). p95 is nearest-rank, as PERF2 reported it."""
    ordered = sorted(values)
    if not ordered:
        return 0, None, None, None
    return (len(ordered), statistics.median(ordered),
            ordered[max(0, round(0.95 * len(ordered)) - 1)], ordered[-1])


def fmt(values, *, scale=1000.0, unit='ms', digits=1):
    """'n=20  median 12.3 ms  p95 15.0 ms  max 18.2 ms'."""
    n, median, p95, worst = summary(values)
    if not n:
        return 'n=0'
    f = f'{{:.{digits}f}}'
    return (f'n={n}  median {f.format(median * scale)} {unit}  p95 '
            f'{f.format(p95 * scale)} {unit}  max {f.format(worst * scale)} '
            f'{unit}')


def triple(values, *, scale=1000.0):
    """[median, p95, max] scaled, for the JSON record."""
    n, median, p95, worst = summary(values)
    if not n:
        return None
    return [round(median * scale, 1), round(p95 * scale, 1),
            round(worst * scale, 1)]


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def out_dir(path=None):
    target = pathlib.Path(path) if path else DEFAULT_OUT
    target.mkdir(parents=True, exist_ok=True)
    return target


def save(out, name, record):
    path = out / name
    path.write_text(json.dumps(record, indent=2, default=str),
                    encoding='utf-8')
    print(f'  [saved {path}]', flush=True)
    return path


# --- memory -------------------------------------------------------------------

class _Counters(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS_EX."""
    _fields_ = [('cb', wt.DWORD), ('PageFaultCount', wt.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t),
                ('PrivateUsage', ctypes.c_size_t)]


# argtypes and restype are NOT optional: without them ctypes passes a 64-bit
# HANDLE as a 32-bit int and every reading silently comes back 0 -- which is
# what PERF2's first worker reported.
_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_kernel32.OpenProcess.restype = wt.HANDLE
_kernel32.CloseHandle.argtypes = [wt.HANDLE]
_kernel32.CloseHandle.restype = wt.BOOL
_psapi = ctypes.WinDLL('psapi', use_last_error=True)
_psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_Counters),
                                        wt.DWORD]
_psapi.GetProcessMemoryInfo.restype = wt.BOOL
_QUERY = 0x1000 | 0x0010      # PROCESS_QUERY_LIMITED_INFORMATION | VM_READ


def working_set(pid):
    """Windows' working set (the local analogue of RSS), its peak and the
    private bytes of one process, in MB."""
    handle = _kernel32.OpenProcess(_QUERY, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        if not _psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters),
                                           counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'ws_mb': round(counters.WorkingSetSize / 1048576, 1),
                'peak_ws_mb': round(counters.PeakWorkingSetSize / 1048576, 1),
                'private_mb': round(counters.PrivateUsage / 1048576, 1)}
    finally:
        _kernel32.CloseHandle(handle)


# --- child processes ------------------------------------------------------------

class Child:
    """One subprocess launched through scale_env, logging to a file."""

    def __init__(self, name, script, args, log_path, env):
        self.name = name
        self.log_path = pathlib.Path(log_path)
        self._log = open(self.log_path, 'w', encoding='utf-8')
        self.started = time.perf_counter()
        self.proc = subprocess.Popen(
            [sys.executable, str(SCALE_ENV), str(script)] + [str(a) for a in args],
            cwd=str(APP_DIR), stdout=self._log, stderr=subprocess.STDOUT,
            env=env)
        self.pid = self.proc.pid

    def text(self):
        return self.log_path.read_text(encoding='utf-8', errors='replace')

    def wait_line(self, pattern, timeout=180):
        """The first match of `pattern` in the log, waiting for it."""
        regex = re.compile(pattern)
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            match = regex.search(self.text())
            if match:
                return match
            if self.proc.poll() is not None:
                raise RuntimeError(f'{self.name} exited {self.proc.returncode}'
                                   f' before {pattern!r}:\n{self.text()[-3000:]}')
            time.sleep(0.05)
        raise TimeoutError(f'{self.name}: no {pattern!r} in {timeout}s')

    def alive(self):
        return self.proc.poll() is None

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
        try:
            self.proc.wait(timeout=30)
        finally:
            self._log.close()


def child_env(flag='on', **extra):
    env = dict(os.environ)
    env['PYTHONUNBUFFERED'] = '1'
    env['RADAR_BOARD_SHARED_RESULTS'] = flag
    env.update({key: str(value) for key, value in extra.items()})
    return env


def start_producer(out, name='producer', poll_interval=None, flag='on'):
    """The real `run_radar_board_producer.py`, as a subprocess."""
    args = [] if poll_interval is None else ['--poll-interval', poll_interval]
    child = Child(name, 'run_radar_board_producer.py', args,
                  out / f'{name}.log', child_env(flag))
    match = child.wait_line(r'radar board producer namespace=([0-9a-f]{64})')
    child.namespace = match.group(1)
    return child


def start_web(out, port, name=None, flag='on', threads=1):
    """One web-model worker (`serve_perf3.py`): real WSGI app, one process."""
    name = name or f'web{port}'
    child = Child(name, HERE / 'serve_perf3.py',
                  ['--port', port, '--threads', threads],
                  out / f'{name}.log', child_env(flag))
    match = child.wait_line(r'SERVE ready .*namespace=([0-9a-f]{64})')
    child.namespace = match.group(1)
    child.port = port
    child.ready_s = time.perf_counter() - child.started
    return child


def stop_all(children):
    for child in children:
        try:
            child.kill()
        except Exception as problem:                     # noqa: BLE001
            print(f'  (stopping {child.name}: {problem})')


# --- HTTP -------------------------------------------------------------------------

# No proxies for loopback, whatever the environment says.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def mint_cookie(app, user_id):
    """A session cookie signed with the app's own serializer."""
    from flask.sessions import SecureCookieSessionInterface
    serializer = SecureCookieSessionInterface().get_signing_serializer(app)
    return serializer.dumps({'user_id': user_id})


def http_get(port, path, *, cookie=None, params=None, timeout=120):
    """(seconds, status, body) -- seconds until the body was fully read."""
    url = f'http://127.0.0.1:{port}{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    headers = {'Cookie': f'session={cookie}'} if cookie else {}
    request = urllib.request.Request(url, headers=headers)
    began = time.perf_counter()
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as problem:
        body = problem.read()
        status = problem.code
    return time.perf_counter() - began, status, body


def board(port, params, cookie, *, poll=False, timeout=120):
    """(seconds, status, payload) for one /radar/api/board request."""
    query = dict(params)
    if poll:
        query['poll'] = '1'
    took, status, body = http_get(port, '/radar/api/board', cookie=cookie,
                                  params=query, timeout=timeout)
    payload = json.loads(body) if status == 200 else None
    return took, status, payload


def is_board(payload):
    """A real board: rows present (possibly empty), not a pending shell."""
    return (payload is not None and not payload.get('pending')
            and not payload.get('busy') and payload.get('rows') is not None)


# --- accounts --------------------------------------------------------------------

def create_accounts(engine, spec, now=None):
    """{username: id} for accounts holding the given watch lists.

    Disposable: the password hash is not a hash, so none of these can log in.
    Every name carries the `perf3_` prefix, and `delete_accounts` removes
    exactly these rows and their watches.
    """
    now = now or utcnow().replace(microsecond=0)
    ids = {}
    with engine.begin() as c:
        for username, tickers in spec.items():
            if not username.startswith(USER_PREFIX):
                raise ValueError(f'{username!r} lacks the {USER_PREFIX} prefix')
            user_id = c.execute(sa.text(
                'SELECT id FROM app_user WHERE username = :u'),
                {'u': username}).scalar()
            if user_id is None:
                c.execute(sa.text(
                    'INSERT INTO app_user (username, password_hash, created_at,'
                    ' is_admin) VALUES (:u, :p, :c, 0)'),
                    {'u': username, 'p': 'perf3-not-a-login', 'c': now})
                user_id = c.execute(sa.text(
                    'SELECT id FROM app_user WHERE username = :u'),
                    {'u': username}).scalar()
            c.execute(sa.text('DELETE FROM radar_watch WHERE user_id = :u'),
                      {'u': user_id})
            for index, ticker in enumerate(tickers):
                c.execute(sa.text(
                    'INSERT INTO radar_watch (user_id, ticker, created_at)'
                    ' VALUES (:u, :t, :c)'),
                    {'u': user_id, 't': ticker,
                     'c': now + dt.timedelta(seconds=index)})
            ids[username] = user_id
    return ids


def delete_accounts(engine, usernames=None):
    """Remove the named perf3_ accounts (all of them when None) and watches."""
    with engine.begin() as c:
        if usernames is None:
            usernames = c.execute(sa.text(
                'SELECT username FROM app_user WHERE username LIKE :p'),
                {'p': USER_PREFIX + '%'}).scalars().all()
        removed = 0
        for username in usernames:
            if not username.startswith(USER_PREFIX):
                continue
            user_id = c.execute(sa.text(
                'SELECT id FROM app_user WHERE username = :u'),
                {'u': username}).scalar()
            if user_id is None:
                continue
            c.execute(sa.text('DELETE FROM radar_watch WHERE user_id = :u'),
                      {'u': user_id})
            c.execute(sa.text('DELETE FROM app_user WHERE id = :u'),
                      {'u': user_id})
            removed += 1
    return removed


# --- the store -------------------------------------------------------------------

def warm_args():
    """The eight warm selections as request arguments, derived from the
    producer's own constants rather than copied."""
    from features.radar import board_producer
    return [{'market': market, 'segment': segment, 'window': str(window)}
            for market in board_producer.WARM_MARKETS
            for segment in board_producer.WARM_SEGMENTS
            for window in board_producer.WARM_WINDOWS]


def key_of(args, now=None):
    """(key_hash, key_json) exactly as a web worker would compute it."""
    from features.radar import board_keys
    from features.radar.routes import api
    return board_keys.canonical(api.parse_query(args, now=now or utcnow()))


def label(args):
    segment = args.get('segment', '')
    segment = 'all' if segment == '' else (
        'default' if segment.startswith('discover') else segment)
    extra = ' '.join(f'{k}={v}' for k, v in sorted(args.items())
                     if k not in ('market', 'segment', 'window'))
    return (f"{args.get('market', '?')}/{segment}/{args.get('window', '12')}h"
            + (f' {extra}' if extra else ''))


def key_row(engine, ns, key_hash):
    with engine.connect() as c:
        row = c.execute(sa.text(
            'SELECT key_hash, warm, queue_state, as_of, built_at, build_ms,'
            ' enqueued_at, requested_at, request_count, attempts,'
            ' payload IS NOT NULL AS has_payload, payload_bytes'
            ' FROM radar_board_results WHERE namespace = :ns AND key_hash = :k'),
            {'ns': ns, 'k': key_hash}).mappings().first()
    return dict(row) if row is not None else None


def ns_rows(engine, ns):
    with engine.connect() as c:
        return [dict(row) for row in c.execute(sa.text(
            'SELECT key_hash, warm, queue_state, as_of, built_at, build_ms,'
            ' enqueued_at FROM radar_board_results WHERE namespace = :ns'),
            {'ns': ns}).mappings().all()]


def delete_key(engine, ns, key_hash):
    """Make one key cold again. Never under a builder."""
    with engine.begin() as c:
        return c.execute(sa.text(
            'DELETE FROM radar_board_results WHERE namespace = :ns'
            " AND key_hash = :k AND queue_state <> 'building'"),
            {'ns': ns, 'k': key_hash}).rowcount


SCALE_DB = 'personal_apps_radar_perf3_scale'


def _only_the_scale_database(engine):
    """Refuse an engine bound anywhere but the measurement database.

    Inside the destructive helpers rather than at their call sites. Every
    caller in this directory passes `scale_env.engine()`, which has already
    refused anything else -- but these two TRUNCATE and DELETE whole tables,
    and a helper that can empty a database should not be taking anyone's word
    for which database it is pointed at.
    """
    bound = engine.url.database
    if bound != SCALE_DB:
        raise SystemExit(f'refusing to empty {bound!r}: only {SCALE_DB}')


def truncate_store(engine):
    _only_the_scale_database(engine)
    with engine.begin() as c:
        c.execute(sa.text('TRUNCATE TABLE radar_board_results'))
        c.execute(sa.text('TRUNCATE TABLE radar_board_namespaces'))


def delete_on_demand(engine, ns):
    """Every on-demand board of the namespace, and every other namespace."""
    _only_the_scale_database(engine)
    with engine.begin() as c:
        rows = c.execute(sa.text(
            'DELETE FROM radar_board_results WHERE namespace = :ns'
            ' AND warm = 0'), {'ns': ns}).rowcount
        others = c.execute(sa.text(
            'DELETE FROM radar_board_results WHERE namespace <> :ns'),
            {'ns': ns}).rowcount
        c.execute(sa.text(
            'DELETE FROM radar_board_namespaces WHERE namespace <> :ns'),
            {'ns': ns})
    return rows, others


def queue_counts(engine, ns):
    with engine.connect() as c:
        row = c.execute(sa.text(
            "SELECT SUM(queue_state = 'pending'), SUM(queue_state ="
            " 'building'), COUNT(*) FROM radar_board_results"
            ' WHERE namespace = :ns'), {'ns': ns}).one()
    return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)


def wait_ready_idle(engine, ns, timeout=600, settle=0.0):
    """Seconds until every warm board is fresh and nothing is queued."""
    from features.radar import board_producer
    began = time.perf_counter()
    while time.perf_counter() - began < timeout:
        state = board_producer.readiness(engine, ns, utcnow())
        pending, building, _ = queue_counts(engine, ns)
        if state['ready'] and pending == 0 and building == 0:
            if settle:
                time.sleep(settle)
            return time.perf_counter() - began
        time.sleep(0.25)
    raise TimeoutError(f'store not ready and idle within {timeout}s')


def lock_status(engine):
    with engine.connect() as c:
        rows = c.execute(sa.text(
            "SHOW GLOBAL STATUS LIKE 'Innodb_row_lock%'")).all()
    return {name: int(value) for name, value in rows}


def lock_delta(before, after):
    return {'waits': after['Innodb_row_lock_waits']
            - before['Innodb_row_lock_waits'],
            'time_ms': after['Innodb_row_lock_time']
            - before['Innodb_row_lock_time'],
            'time_max_ms_since_start': after['Innodb_row_lock_time_max']}


def parse_builds(text):
    """The producer's `board build` lines, as dicts."""
    pattern = re.compile(
        r'(?P<t>\d\d:\d\d:\d\d\.\d{3})Z INFO radar\.board board build '
        r'key=(?P<key>[0-9a-f]+) class=(?P<cls>\w+) queue_wait=(?P<qw>[-\d.]+)'
        r' build_ms=(?P<ms>\d+) payload_bytes=(?P<bytes>\d+)'
        r' result=(?P<result>\w+)')
    out = []
    for match in pattern.finditer(text):
        out.append({'t': match['t'], 'key': match['key'], 'cls': match['cls'],
                    'queue_wait': (None if match['qw'] == '-'
                                   else float(match['qw'])),
                    'build_ms': int(match['ms']),
                    'payload_bytes': int(match['bytes']),
                    'result': match['result']})
    return out
