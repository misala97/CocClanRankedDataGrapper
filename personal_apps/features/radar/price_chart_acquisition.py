"""Selected price charts: bounded background acquisition, per web process.

The web request never waits for Yahoo. It asks `Admission.get_or_start`,
which under a short lock either hands back a series this process already
holds, or admits at most ONE acquisition and returns at once. The admitted
acquisition runs on a supervisor thread that starts one fetch child, drains
its output concurrently on a reader thread -- so a full pipe cannot deadlock
completion -- and enforces a monotonic deadline measured from before the
child is started, covering startup, request, read and parse. On expiry the
child is terminated, then killed, then reaped; if its exit (or its reader's
end) cannot be confirmed within the cleanup allowance the process stops
acquiring (`cleanup_failed`) rather than start another child.

The child is an explicit fresh interpreter running one module,
`python -E -s -B -m features.radar.price_chart_fetch`, started from an
argument array (no shell) in the application directory with a minimal
environment built from an allowlist (`CHILD_ENV_ALLOWLIST`) -- never a copy
of os.environ, and os.environ is never modified. It therefore never executes
the parent's main script (python app.py, serve_b1c.py, gunicorn, pytest:
the launcher's shape does not matter), never imports Flask, the models or the
database, never loads dotenv, and does not inherit PYTHONPATH/PYTHONSTARTUP,
user site-packages, proxy settings, provider keys, database or application
secrets. Its one validated public request goes in on stdin (bounded), its one
JSON result comes back on stdout (bounded), stderr goes to the null device.

Limits, all per web PROCESS -- nothing here is shared across workers, and a
restart resets every counter. With N web workers up to N children can run at
once, and the ingest daemon's own Yahoo traffic is separate and not counted:

- one supervisor and one child in flight; no queue -- a different chart asks
  again later (`busy`), the same chart shares the one in flight (`pending`);
- at most 10 child starts in any rolling 60 seconds, and at least 60 seconds
  between starts for the same chart; no retry inside an acquisition;
- 401/403/429 open a provider-wide backoff on the existing 60 -> 1800 s
  ladder, or a longer valid Retry-After (saturating at one day; a longer one
  makes acquisition unavailable until its full time);
- 5xx, timeouts, invalid or empty bodies: 60 s cooldown for that chart; 404:
  unsupported for 15 minutes; an identity mismatch drops the cached series;
- cache: 128 keys, 8 MiB, 256 KiB per series, LRU; fresh for 60 s after
  receipt, served with its age until 15 minutes, then not at all.

These are supervisor deadlines and application limits. They are not an
end-to-end HTTP guarantee, an OS scheduling promise or a provider-wide rate
limit.

Binding: radar-design/MD-SELECTED-PRICE-SPEC.md sections 6 and 7.
"""
from __future__ import annotations

import atexit
import collections
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config
from . import price_chart_contract as contract
from . import price_chart_fetch as fetch
from .prices import yahoo

DEADLINE_S = 6.0
CLEANUP_S = 1.0
POLL_S = 0.05
ROLLING_WINDOW_S = 60.0
ROLLING_STARTS = 10
KEY_MIN_INTERVAL_S = 60.0
CACHE_KEYS = 128
CACHE_BYTES = 8 * 1024 * 1024
ENTRY_BYTES = 256 * 1024
BACKOFF_STEPS = yahoo._BACKOFF_STEPS
RETRY_AFTER_CAP_S = 86_400
COOLDOWN_S = 60.0
UNSUPPORTED_S = 900.0
PENDING_RETRY_S = 2
BUSY_RETRY_S = 5

COUNTERS = ('success', 'empty', 'invalid', 'identity_mismatch', 'timeout', 'throttle',
            'unsupported', 'upstream_error', 'served_stale', 'fallback', 'busy',
            'cleanup_failed')


#: The production child program, run with `python -m`.
FETCH_MODULE = 'features.radar.price_chart_fetch'
#: personal_apps: the child's working directory, so `-m` finds `features`.
APP_ROOT = Path(__file__).resolve().parents[2]
#: -E ignore every PYTHON* variable (PYTHONPATH, PYTHONSTARTUP, PYTHONHOME...);
#: -s no user site-packages; -B write no bytecode into the application tree.
INTERPRETER_FLAGS = ('-E', '-s', '-B')
#: The ONLY environment entries a child receives, per os.name. Windows cannot
#: initialise sockets (WinError 10106) without SYSTEMROOT; a POSIX interpreter
#: started by absolute path needs nothing. No PATH, HOME, locale, proxy, TLS
#: bundle override, provider key, database URL or application secret.
CHILD_ENV_ALLOWLIST = {'nt': ('SYSTEMROOT',), 'posix': ()}
_MODULE_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*')
_NO_WINDOW = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def child_environment(source=None, platform=None) -> dict:
    """A new dict holding only the allowlisted, non-empty entries of `source`
    (os.environ by default), which is read and never modified."""
    source = os.environ if source is None else source
    platform = os.name if platform is None else platform
    environment = {}
    for name in CHILD_ENV_ALLOWLIST.get(platform, ()):
        value = source.get(name)
        if isinstance(value, str) and value:
            environment[name] = value
    return environment


class Child:
    """One started fetch child: its process and the thread draining its stdout.

    The reader keeps at most RESULT_LIMIT_BYTES and stops reading the moment a
    chunk would pass it, so neither a full pipe nor a flood of output can
    block the supervisor or grow memory; stderr is never piped at all."""

    def __init__(self, process, *, result_limit: int = fetch.RESULT_LIMIT_BYTES):
        self.process = process
        self._limit = result_limit
        self._buffer = bytearray()
        self._overflow = False
        self._broken = False
        self._finished = threading.Event()
        self._reader = threading.Thread(target=self._drain, name='radar-price-chart-reader', daemon=True)
        self._reader.start()

    def _drain(self):
        try:
            while True:
                chunk = self.process.stdout.read(fetch.CHUNK_BYTES)
                if not chunk:
                    return
                if len(self._buffer) + len(chunk) > self._limit:
                    self._overflow = True
                    return
                self._buffer += chunk
        except (OSError, ValueError):
            self._broken = True
        finally:
            self._finished.set()

    def reader_alive(self) -> bool:
        return self._reader.is_alive()

    def collect(self, clock, deadline: float) -> tuple[str, bytes | None]:
        """The result once the child closed its output and exited 0; or
        over bound, broken, a failed exit, or late."""
        while not self._finished.is_set():
            remaining = deadline - clock()
            if remaining <= 0:
                return 'timeout', None
            self._finished.wait(min(remaining, POLL_S))
        if self._overflow:
            return 'oversized', None
        if self._broken:
            return 'invalid', None
        remaining = deadline - clock()
        if remaining <= 0:
            return 'timeout', None
        try:
            code = self.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return 'timeout', None
        if code != 0:
            return 'invalid', None
        return 'done', bytes(self._buffer)

    def reap(self, clock, cleanup_s: float = CLEANUP_S) -> bool:
        """Stop and reap the child, end its reader and close its pipes.
        True only when both the exit and the reader's end are confirmed."""
        process = self.process
        ends = clock() + cleanup_s
        exited = False
        try:
            exited = _wait(process, min(0.2, ends - clock()))
            if not exited:
                process.terminate()
                exited = _wait(process, (ends - clock()) / 2)
            if not exited:
                process.kill()
                exited = _wait(process, ends - clock())
        except OSError:
            exited = False
        self._reader.join(max(0.0, ends - clock()))
        drained = not self._reader.is_alive()
        _close(process.stdin)
        if drained:
            # Never close a handle a live reader is blocked on.
            _close(process.stdout)
        return exited and drained


def subprocess_launcher(module: str = FETCH_MODULE, args=()):
    """A launcher that starts `module` as a fresh interpreter child.

    `module`/`args` exist so tests can run real synthetic child programs
    through this same launcher; production code only ever calls it with no
    arguments, and nothing reachable from a request selects either."""
    if not isinstance(module, str) or not _MODULE_NAME.fullmatch(module):
        raise ValueError('the child must be a dotted module name')
    args = tuple(args)
    if not all(isinstance(arg, str) for arg in args):
        raise ValueError('child arguments must be strings')

    def launch(spec):
        data = json.dumps(spec, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(data) > fetch.SPEC_LIMIT_BYTES:
            raise ValueError('the request spec exceeds its bound')
        if not sys.executable:
            raise RuntimeError('no interpreter path to start a child with')
        process = subprocess.Popen(
            [sys.executable, *INTERPRETER_FLAGS, '-m', module, *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=str(APP_ROOT), env=child_environment(), bufsize=0, close_fds=True, **_NO_WINDOW)
        try:
            try:
                # At most SPEC_LIMIT_BYTES, well inside the smallest default
                # pipe buffer (4 KiB on Windows), so this never waits on the
                # child reading it -- even a child that never reads.
                view = memoryview(data)
                while view:
                    written = process.stdin.write(view)
                    view = view[written if written else len(view):]
            except OSError:
                pass            # the child is already gone; its outcome says so
            finally:
                _close(process.stdin)
            return Child(process)
        except BaseException as exc:
            if not _kill_now(process):
                # No Child reaches the supervisor, so it must learn here that a
                # process may still be running: it quarantines on this.
                raise UnconfirmedCleanup(exc) from exc
            raise
    return launch


class UnconfirmedCleanup(RuntimeError):
    """A child was started, its launch then failed, and its exit could not be
    confirmed. The supervisor quarantines on it; `__cause__` keeps the
    original launch failure."""

    def __init__(self, cause: BaseException):
        super().__init__(f'fetch child exit unconfirmed after a failed launch ({type(cause).__name__})')


def _wait(process, seconds: float) -> bool:
    try:
        process.wait(timeout=max(0.0, seconds))
        return True
    except subprocess.TimeoutExpired:
        return False


def _close(stream) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def _kill_now(process) -> bool:
    """Emergency cleanup for a child whose launch failed after Popen: kill,
    wait at most CLEANUP_S, close its pipes. True only when the process itself
    reports an exit within that time -- a kill call, or a kill that raised
    because the process looked gone, confirms nothing on its own."""
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=CLEANUP_S)
        exited = True
    except (OSError, subprocess.TimeoutExpired):
        exited = False
    _close(process.stdin)
    _close(process.stdout)
    return exited


class Coordinator:
    def __init__(self, *, clock=time.monotonic, wall=time.time,
                 launcher=None, thread_factory=threading.Thread,
                 deadline_s: float = DEADLINE_S, cleanup_s: float = CLEANUP_S):
        self._clock = clock
        self._wall = wall
        self._launch = launcher or subprocess_launcher()
        self._thread_factory = thread_factory
        self._deadline_s = deadline_s
        self._cleanup_s = cleanup_s
        self._lock = threading.Lock()
        self._cache: 'collections.OrderedDict[tuple, dict]' = collections.OrderedDict()
        self._cache_bytes = 0
        self._cooldowns: dict[tuple, tuple[float, str, str]] = {}
        self._key_starts: dict[tuple, float] = {}
        self._starts: collections.deque = collections.deque()
        self._inflight: tuple | None = None
        self._child: Child | None = None
        self._backoff_index = -1
        self._backoff_until = 0.0
        self._backoff_capped = False
        self._unavailable_until = 0.0
        self._quarantined = False
        self.counters = {name: 0 for name in COUNTERS}
        self._latency = {'count': 0, 'sum_seconds': 0.0, 'max_seconds': 0.0}
        self._created = wall()
        self._pid = os.getpid()

    # --- admission (request thread, short lock, no I/O) ----------------------

    def get_or_start(self, identity: dict, window: contract.Window, *, now) -> dict:
        spec = contract.request_spec(identity, window)
        if spec is None:
            reason = ('the session has only just begun' if window.waiting
                      else 'the mapped symbol has no supported provider form')
            return _answer('unavailable', None, reason)
        key = contract.cache_key(identity, window)
        mono, wall = self._clock(), self._wall()
        start = False
        with self._lock:
            series, age = self._cached(key, wall)
            if series is not None and age < contract.FRESH_SECONDS:
                return _answer('ready', None, None, series)
            refused = self._refusal(key, mono)
            if refused is None:
                self._record_start(key, mono)
                start = True
                refused = ('pending', PENDING_RETRY_S,
                           'refreshing an aged series' if series is not None else 'acquiring')
            if series is not None:
                self.counters['served_stale'] += 1
        if start:
            try:
                self._thread_factory(target=self._supervise, args=(key, spec),
                                     name='radar-price-chart-supervisor', daemon=True).start()
            except RuntimeError:
                with self._lock:
                    self._inflight = None
                return _answer('unavailable', None, 'the acquisition could not be started', series)
        state, retry_after, reason = refused
        return _answer(state, retry_after, reason, series)

    def _cached(self, key, wall):
        entry = self._cache.get(key)
        if entry is None:
            return None, None
        age = max(0.0, wall - entry['series']['received_at'])
        if age >= contract.STALE_LIMIT_SECONDS:
            self._drop(key)
            return None, None
        self._cache.move_to_end(key)
        return entry['series'], age

    def _refusal(self, key, mono):
        if self._quarantined:
            return ('unavailable', None, 'cleanup_failed: a fetch child could not be confirmed stopped')
        if self._inflight is not None:
            if self._inflight[0] == key:
                return ('pending', PENDING_RETRY_S, 'acquisition in progress')
            self.counters['busy'] += 1
            return ('busy', BUSY_RETRY_S, 'another chart is being acquired in this process')
        if mono < self._unavailable_until:
            return ('unavailable', min(_ceil(self._unavailable_until - mono), RETRY_AFTER_CAP_S),
                    'the provider asked this process to wait longer than one day')
        if mono < self._backoff_until:
            reason = 'the provider throttled this process'
            if self._backoff_capped:
                reason += ' (its Retry-After was capped at one day for display)'
            return ('backoff', _ceil(self._backoff_until - mono), reason)
        cooldown = self._cooldowns.get(key)
        if cooldown is not None and mono < cooldown[0]:
            return (cooldown[1], _ceil(cooldown[0] - mono), cooldown[2])
        last = self._key_starts.get(key)
        if last is not None and mono - last < KEY_MIN_INTERVAL_S:
            return ('backoff', _ceil(KEY_MIN_INTERVAL_S - (mono - last)),
                    'this chart was acquired less than a minute ago')
        while self._starts and mono - self._starts[0] >= ROLLING_WINDOW_S:
            self._starts.popleft()
        if len(self._starts) >= ROLLING_STARTS:
            self.counters['busy'] += 1
            return ('busy', _ceil(ROLLING_WINDOW_S - (mono - self._starts[0])),
                    'this process reached its acquisition start limit')
        return None

    def _record_start(self, key, mono):
        self._starts.append(mono)
        self._key_starts[key] = mono
        if len(self._key_starts) > CACHE_KEYS:
            for old in [k for k, at in self._key_starts.items() if mono - at >= KEY_MIN_INTERVAL_S]:
                del self._key_starts[old]
        self._cooldowns = {k: v for k, v in self._cooldowns.items() if v[0] > mono}
        self._inflight = (key, mono)

    # --- supervision (background thread) -------------------------------------

    def _supervise(self, key, spec):
        started = self._clock()
        child = None
        outcome, data = 'invalid', None
        confirmed = True
        try:
            child = self._launch(spec)
            with self._lock:
                self._child = child
            outcome, data = child.collect(self._clock, started + self._deadline_s)
        except UnconfirmedCleanup:
            # Started, failed, and possibly still running: quarantine below,
            # in the same locked step that releases admission.
            outcome, data = 'invalid', None
            confirmed = False
        except Exception:  # noqa: BLE001 -- a failed start is an invalid acquisition
            outcome, data = 'invalid', None
        finally:
            if child is not None:
                try:
                    confirmed = child.reap(self._clock, self._cleanup_s)
                except Exception:  # noqa: BLE001 -- unconfirmed cleanup quarantines
                    confirmed = False
            elapsed = max(0.0, self._clock() - started)
            with self._lock:
                self._child = None
                self._inflight = None
                self._latency['count'] += 1
                self._latency['sum_seconds'] += elapsed
                self._latency['max_seconds'] = max(self._latency['max_seconds'], elapsed)
                if not confirmed:
                    self._quarantined = True
                    self.counters['cleanup_failed'] += 1
                self._settle(key, outcome, data)

    def _settle(self, key, outcome, data):
        mono = self._clock()
        if outcome == 'timeout':
            self.counters['timeout'] += 1
            self._cool(key, mono, COOLDOWN_S, 'backoff', 'the last acquisition timed out')
            return
        if outcome != 'done':
            self.counters['invalid'] += 1
            self._cool(key, mono, COOLDOWN_S, 'backoff', 'the last acquisition was invalid')
            return
        try:
            result = json.loads(data)
            kind = result['kind']
        except (ValueError, TypeError, KeyError):
            self.counters['invalid'] += 1
            self._cool(key, mono, COOLDOWN_S, 'backoff', 'the last acquisition was invalid')
            return
        if kind == 'ok':
            if (len(data) > ENTRY_BYTES or not isinstance(result.get('bars'), list)
                    or not isinstance(result.get('received_at'), (int, float))):
                self.counters['invalid'] += 1
                self._cool(key, mono, COOLDOWN_S, 'backoff', 'the series exceeded its bound')
                return
            self.counters['success'] += 1
            self._backoff_index = -1
            self._backoff_until = 0.0
            self._backoff_capped = False
            self._store(key, result, len(data))
        elif kind == 'throttle':
            self.counters['throttle'] += 1
            self._throttle(mono, result.get('retry_after'))
        elif kind == 'unsupported':
            self.counters['unsupported'] += 1
            self._cool(key, mono, UNSUPPORTED_S, 'unavailable', 'the provider does not know this symbol')
        elif kind == 'identity_mismatch':
            self.counters['identity_mismatch'] += 1
            self._drop(key)
            self._cool(key, mono, UNSUPPORTED_S, 'unavailable',
                       'the provider answered for a different listing')
        elif kind == 'empty':
            self.counters['empty'] += 1
            self._cool(key, mono, COOLDOWN_S, 'backoff', 'the provider returned no bars')
        elif kind == 'timeout':
            self.counters['timeout'] += 1
            self._cool(key, mono, COOLDOWN_S, 'backoff', 'the provider did not answer in time')
        elif kind == 'upstream_error':
            self.counters['upstream_error'] += 1
            self._cool(key, mono, COOLDOWN_S, 'backoff', 'the provider answered with an error')
        else:
            self.counters['invalid'] += 1
            self._cool(key, mono, COOLDOWN_S, 'backoff', 'the provider answer was invalid')

    def _cool(self, key, mono, seconds, state, reason):
        self._cooldowns[key] = (mono + seconds, state, reason)

    def _throttle(self, mono, retry_after):
        self._backoff_index = min(self._backoff_index + 1, len(BACKOFF_STEPS) - 1)
        ladder = BACKOFF_STEPS[self._backoff_index]
        self._backoff_capped = False
        if isinstance(retry_after, int) and not isinstance(retry_after, bool) and retry_after > ladder:
            if retry_after > RETRY_AFTER_CAP_S:
                self._unavailable_until = mono + retry_after
                self._backoff_until = mono + RETRY_AFTER_CAP_S
                self._backoff_capped = True
            else:
                self._backoff_until = mono + retry_after
        else:
            self._backoff_until = mono + ladder

    def _store(self, key, series, size):
        self._drop(key)
        self._cache[key] = {'series': series, 'size': size}
        self._cache_bytes += size
        while len(self._cache) > CACHE_KEYS or self._cache_bytes > CACHE_BYTES:
            _, evicted = self._cache.popitem(last=False)
            self._cache_bytes -= evicted['size']

    def _drop(self, key):
        entry = self._cache.pop(key, None)
        if entry is not None:
            self._cache_bytes -= entry['size']

    # --- health and shutdown ---------------------------------------------------

    def note_fallback(self):
        with self._lock:
            self.counters['fallback'] += 1

    def snapshot(self) -> dict:
        mono, wall = self._clock(), self._wall()
        with self._lock:
            while self._starts and mono - self._starts[0] >= ROLLING_WINDOW_S:
                self._starts.popleft()
            backoff = max(self._backoff_until, self._unavailable_until)
            return _snapshot_shape(
                pid=self._pid, started=self._created,
                in_flight=self._inflight is not None,
                in_flight_seconds=(round(mono - self._inflight[1], 3)
                                   if self._inflight is not None else None),
                cache_keys=len(self._cache), cache_bytes=self._cache_bytes,
                rolling_starts=len(self._starts),
                backoff_until=(_iso_wall(wall + backoff - mono) if backoff > mono else None),
                quarantined=self._quarantined, counters=dict(self.counters),
                latency={**self._latency, 'sum_seconds': round(self._latency['sum_seconds'], 3),
                         'max_seconds': round(self._latency['max_seconds'], 3)})

    def shutdown(self):
        with self._lock:
            child = self._child
        if child is not None:
            try:
                child.reap(self._clock, self._cleanup_s)
            except Exception:  # noqa: BLE001 -- interpreter exit: nothing left to report to
                pass


def _ceil(seconds: float) -> int:
    return max(1, int(math.ceil(seconds)))


def _answer(state, retry_after, reason, series=None) -> dict:
    return {'state': state, 'retry_after_seconds': retry_after, 'reason': reason, 'series': series}


def _iso_wall(epoch: float) -> str:
    return contract.iso_z(dt.datetime.fromtimestamp(epoch, dt.timezone.utc))


WORKERS_SOURCE = 'WEB_CONCURRENCY'
_POSITIVE_COUNT = re.compile(r'[0-9]+')


def _configured_workers():
    """A positive explicit WEB_CONCURRENCY, else None: unknown. A gunicorn
    `--workers` flag or any other launcher setting is not visible from here
    and is never guessed."""
    raw = os.environ.get(WORKERS_SOURCE, '').strip()
    if not _POSITIVE_COUNT.fullmatch(raw):
        return None
    count = int(raw)
    return count if count > 0 else None


def _snapshot_shape(*, pid, started, in_flight, in_flight_seconds, cache_keys, cache_bytes,
                    rolling_starts, backoff_until, quarantined, counters, latency) -> dict:
    return {
        'scope': 'process',
        'pid': pid,
        # When this process's acquisition coordinator was created: lazily, on
        # the first provider-enabled chart request that reaches acquisition,
        # whether or not that request is then admitted -- not the OS process
        # start. None: not yet.
        'coordinator_started_at': _iso_wall(started) if started is not None else None,
        'charts_enabled': config.selected_price_charts_enabled(),
        'yahoo_enabled': config.selected_price_yahoo_enabled(),
        'configured_web_workers': _configured_workers(),
        'configured_web_workers_source': WORKERS_SOURCE,
        'limits': {'max_children': 1, 'starts_per_60s': ROLLING_STARTS,
                   'deadline_seconds': DEADLINE_S, 'cache_keys': CACHE_KEYS,
                   'cache_bytes': CACHE_BYTES},
        'note': ('Counts for this web process only, reset when it restarts. Each web worker '
                 'has its own limits; the ingest daemon\'s Yahoo traffic is separate.'),
        'in_flight': in_flight,
        'in_flight_seconds': in_flight_seconds,
        'cache_keys': cache_keys,
        'cache_bytes': cache_bytes,
        'rolling_starts_60s': rolling_starts,
        'backoff_until': backoff_until,
        'quarantined': quarantined,
        'counters': counters,
        'latency': latency,
    }


# --- the process's one coordinator ------------------------------------------------

_instance_lock = threading.Lock()
_instance: Coordinator | None = None


def coordinator() -> Coordinator:
    """Created lazily in the process that uses it -- after any fork -- and
    replaced if this is a different process than the one that made it."""
    global _instance
    with _instance_lock:
        if _instance is None or _instance._pid != os.getpid():
            _instance = Coordinator()
            atexit.register(_instance.shutdown)
        return _instance


class Admission:
    """What the route hands the reader: provider acquisition when both flags
    allow it, and a `disabled` answer that creates nothing otherwise."""

    def get_or_start(self, identity, window, *, now):
        if not config.selected_price_yahoo_enabled():
            return _answer('disabled', None, 'provider acquisition is switched off')
        return coordinator().get_or_start(identity, window, now=now)


def note_fallback() -> None:
    with _instance_lock:
        instance = _instance if _instance is not None and _instance._pid == os.getpid() else None
    if instance is not None:
        instance.note_fallback()


def ops_snapshot() -> dict:
    """Health for /api/ops. Never creates a coordinator or starts anything."""
    with _instance_lock:
        instance = _instance if _instance is not None and _instance._pid == os.getpid() else None
    if instance is not None:
        return instance.snapshot()
    return _snapshot_shape(pid=os.getpid(), started=None, in_flight=False, in_flight_seconds=None,
                           cache_keys=0, cache_bytes=0, rolling_starts=0, backoff_until=None,
                           quarantined=False, counters={name: 0 for name in COUNTERS},
                           latency={'count': 0, 'sum_seconds': 0.0, 'max_seconds': 0.0})
