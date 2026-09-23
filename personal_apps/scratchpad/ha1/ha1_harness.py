"""HA1 harness rules that need no application, database or browser.

Everything the DB/preview harness decides -- which identities it owns and may
delete, what counts as a passed budget, how a statement-timeout probe is
classified, whether a listening preview is the gated candidate, which C15/C16
states must be covered, what contrast ratio a colour pair has -- lives here,
so it is unit-tested DB-free (tests/ha1_unit/test_ha1_harness.py). The scripts
that touch a database or a browser (probe_analysis.py, preview_fixtures.py,
verify_preview.py, tests/test_radar_analysis_api.py) import these rules
rather than restating them.

CORRECTION-1 (2026-09-15): written and unit-tested only. No database, preview
or browser harness was executed.

CORRECTION-2 (2026-09-15, harness only; still NOT executed against a database,
preview or browser): case recording that attributes a raised check to every
enclosing case and fails a case that evaluated nothing (U6/U9); contrast that
fails unsupported colours, composites alpha against the real ancestor
background and requires evaluated text (4.5:1) and graphics (3:1) pairs
(U6); a deterministic source/build fingerprint for runtime identity (U8);
structured cleanup-failure reports (U7); sub-second timeout and deadline
measurement rules under the REVIEW-2 deadline ruling (U5); the dialect label
only after a connection initialized it (U10); and the full-access-host session
helper the API suite uses (U4).
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import math
import re
import secrets
import sys
from contextlib import contextmanager
from pathlib import Path

# --- SPEC section 7 budgets -----------------------------------------------------

MAX_DATA_SELECTS = 4
BUCKET_ROW_CAP = 7 * 96 * 64
BUCKET_ROW_SENTINEL = BUCKET_ROW_CAP + 1
MAX_SOURCES = 64
RESPONSE_BYTES = 1024 * 1024
READER_ALLOC_BYTES = 32 * 1024 * 1024
WARM_REQUESTS = 20
WARM_P95_MS = 1000.0
STATEMENT_LIMIT_S = 2.0
READER_BUDGET_S = 5.0
MIN_STATEMENT_S = 0.001
BROWSER_TIMEOUT_MS = 8000
#: How far past its limit an interrupted statement may return and still be
#: attributed to that limit (driver round trip, scheduling). CORRECTION-1
#: value, unchanged; every overshoot is recorded as a number regardless.
TIMEOUT_GRACE_S = 1.0
TIMEOUT_ERRNOS = frozenset({1969, 3024})
INDEXED_PLAN_TYPES = frozenset({'const', 'eq_ref', 'ref', 'range'})
#: U5: the sub-second limit sent through ReaderBudget + SqlStore._timed.
SUBSECOND_REQUEST_S = 0.250
#: LOCAL-QA (2026-09-15): the CPU-bound probe statement. A row scan over the
#: sequence engine (~1e9 rows, ~58 s unlimited on the local MariaDB 10.11.14)
#: raises 1969 when max_statement_time interrupts it -- the way the reader's
#: own table reads fail. BENCHMARK() is NOT used: on that engine it is cut off
#: at the limit but returns 0 with no error (runtime evidence in
#: radar-design/artifacts/ha1/local-qa/diag_timeout.out.json), which the
#: classification rightly refuses to count as an interrupt.
CPU_PROBE_SQL = 'SELECT COUNT(*) AS value FROM seq_1_to_1000000000 WHERE MOD(seq, 7) = 3'
#: LOCAL-QA: the statement limit sent ONLY while tracemalloc measures reader
#: allocation. Tracing slowed the 43,008-row bucket fetch from ~0.6 s to
#: ~2.6-2.9 s, straddling the reader's 2 s limit (one traced run refused, two
#: passed: local-qa/diag_max_read.out.json), so the memory instrument itself
#: tripped the time limit. Time limits are asserted on UNTRACED reads only;
#: the limit each statement was handed by the reader is still recorded.
TRACED_STATEMENT_LIMIT_S = 30.0
#: LOCAL-QA: the longest single wait inside a long observation window, so the
#: operator sees progress at least this often.
PROGRESS_SEGMENT_MS = 30_000


def quiet_segments(total_ms: int, segment_ms: int = PROGRESS_SEGMENT_MS) -> list[int]:
    """Split one observation window into consecutive waits of at most
    `segment_ms` that add up to exactly `total_ms` (the window is not shortened)."""
    if total_ms <= 0 or segment_ms <= 0:
        raise ValueError('an observation window and its segments must be positive')
    whole, rest = divmod(int(total_ms), int(segment_ms))
    return [int(segment_ms)] * whole + ([rest] if rest else [])


def nearest_rank_p95(values) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError('no samples')
    return ordered[max(1, math.ceil(0.95 * len(ordered))) - 1]


def off_grid_sentinel(day: dt.date) -> dt.datetime:
    """A bucket_start seven minutes into `day`. No aligned quarter-hour row
    can occupy that key, so it can be the 43,009th retained row of a fixture
    whose 7 x 96 x 64 aligned rows already fill the cap -- without adding a
    65th source."""
    return dt.datetime.combine(day, dt.time(0, 7))


def budget_failures(label: str, measured: dict) -> list[str]:
    """Every SPEC section 7 budget this fixture's measurement misses. A value
    that was not measured is a failure, never a pass."""
    failures = []

    def at_most(name, limit):
        value = measured.get(name)
        if value is None:
            failures.append(f'{label}: {name} was not measured')
        elif value > limit:
            failures.append(f'{label}: {name}={value} exceeds {limit}')

    statuses = measured.get('statuses') or []
    if not statuses or any(status != 200 for status in statuses):
        failures.append(f'{label}: not every measured request answered 200 ({statuses})')
    at_most('max_data_statements', MAX_DATA_SELECTS)
    at_most('bucket_rows', BUCKET_ROW_CAP)
    at_most('distinct_sources', MAX_SOURCES)
    at_most('response_bytes', RESPONSE_BYTES)
    at_most('reader_alloc_bytes', READER_ALLOC_BYTES)
    warm = measured.get('warm_ms') or []
    if len(warm) != WARM_REQUESTS:
        failures.append(f'{label}: {len(warm)} warm requests measured, {WARM_REQUESTS} required')
    else:
        p95 = nearest_rank_p95(warm)
        if p95 > WARM_P95_MS:
            failures.append(f'{label}: warm p95 {p95:.1f} ms exceeds {WARM_P95_MS:.0f} ms')
    return failures


def plan_failures(name: str, plan_rows) -> list[str]:
    # U11 (deferred by ruling): kept strict until actual EXPLAIN evidence
    # shows a false fail; never relaxed speculatively.
    if not plan_rows:
        return [f'EXPLAIN {name}: no plan rows']
    return [f'EXPLAIN {name}: access type {row.get("type")!r} is not index-constrained'
            for row in plan_rows if row.get('type') not in INDEXED_PLAN_TYPES]


# --- statement timeout ----------------------------------------------------------

def classify_timeout(kind: str, errno, returned, elapsed_s: float, requested_s) -> str:
    """What happened to a probe statement run under a statement limit.

    - `interrupted_error`: the engine raised its timeout errno.
    - `other_error`: the engine raised something else.
    - `interrupted_silently`: MySQL-family SLEEP() returns 1 when it is
      interrupted rather than raising. The statement WAS cut short, but the
      reader's error mapping was not exercised; this is recorded, not passed.
    - `not_interrupted`: the statement ran to completion. Never a pass.
    """
    if errno in TIMEOUT_ERRNOS:
        return 'interrupted_error'
    if errno is not None:
        return 'other_error'
    if (kind == 'sleep' and requested_s is not None and returned is not None
            and int(returned) == 1 and elapsed_s < 0.9 * requested_s):
        return 'interrupted_silently'
    return 'not_interrupted'


def subsecond_failures(probe) -> list[str]:
    """U5: a CPU-bound statement sent under a sub-second limit that the
    PRODUCTION logic computed (ReaderBudget.statement_timeout ->
    seconds_literal -> SqlStore._timed). Requested and effective limits,
    elapsed time and overshoot must all be recorded; only an interrupt with
    the mapped timeout error counts."""
    if not probe:
        return ['timeout: the sub-second CPU probe did not run']
    failures = []
    requested, effective = probe.get('requested_s'), probe.get('effective_s')
    if requested != SUBSECOND_REQUEST_S:
        failures.append(f'timeout: sub-second probe requested {requested!r}, not {SUBSECOND_REQUEST_S}')
    if not isinstance(effective, (int, float)) or not (MIN_STATEMENT_S <= effective <= SUBSECOND_REQUEST_S):
        failures.append(f'timeout: sub-second effective limit {effective!r} is not within '
                        f'[{MIN_STATEMENT_S}, {SUBSECOND_REQUEST_S}]')
    literal = str(probe.get('rendered') or '')
    if not re.search(r'max_statement_time=0\.\d{3} FOR', literal):
        failures.append(f'timeout: sub-second statement was not rendered as a fractional '
                        f'SET STATEMENT limit ({literal!r})')
    if probe.get('classification') != 'interrupted_error':
        failures.append(f'timeout: the sub-second CPU statement was {probe.get("classification")!r}, '
                        'not interrupted with the timeout error the reader maps')
    elapsed = probe.get('elapsed_s')
    if not isinstance(elapsed, (int, float)):
        failures.append('timeout: sub-second elapsed time was not measured')
    elif isinstance(effective, (int, float)):
        if probe.get('overshoot_s') is None:
            failures.append('timeout: sub-second overshoot was not recorded')
        if elapsed > effective + TIMEOUT_GRACE_S:
            failures.append(f'timeout: sub-second statement stopped only after {elapsed}s '
                            f'against {effective}s')
    return failures


def timeout_failures(result: dict, limit_s: float) -> list[str]:
    if not str(result.get('dialect') or '').startswith('mariadb'):
        return [f'timeout: a MariaDB target is required; bound dialect is '
                f'{result.get("dialect")!r}, so nothing is proven']
    failures = []
    probes = result.get('probes') or {}
    cpu = probes.get('cpu')
    if not cpu:
        failures.append('timeout: the CPU-bound probe did not run')
    elif cpu['classification'] != 'interrupted_error':
        failures.append(f'timeout: the CPU-bound statement was {cpu["classification"]}, '
                        'not interrupted with the timeout error the reader maps')
    elif cpu['elapsed_s'] > limit_s + TIMEOUT_GRACE_S:
        failures.append(f'timeout: interrupted only after {cpu["elapsed_s"]}s '
                        f'against a {limit_s}s limit')
    sleep = probes.get('sleep')
    if not sleep:
        failures.append('timeout: the SLEEP probe did not run')
    elif sleep['classification'] in ('not_interrupted', 'other_error'):
        failures.append(f'timeout: SLEEP was {sleep["classification"]}; an '
                        'uncancelled statement is not a pass')
    elif sleep['elapsed_s'] > limit_s + TIMEOUT_GRACE_S:
        failures.append(f'timeout: SLEEP stopped only after {sleep["elapsed_s"]}s')
    failures += subsecond_failures(probes.get('cpu_subsecond'))
    if result.get('recovery_ok') is not True:
        failures.append('timeout: a normal statement on the same connection after the '
                        'timeouts did not succeed (recovery unproven)')
    before, after = result.get('connection_id_before'), result.get('connection_id_after')
    if before is None or before != after:
        failures.append('timeout: hygiene was not observed on one physical connection '
                        f'({before} -> {after})')
    if result.get('session_max_statement_time_before') != result.get('session_max_statement_time_after'):
        failures.append('timeout: the connection session max_statement_time changed')
    return failures


# --- the five-second reader budget (REVIEW-2 deadline ruling) ----------------------

DEADLINE_ACCEPTANCE = 'mastermind_ruling_required'


def deadline_failures(result) -> list[str]:
    """The ruling's semantics, measured: five seconds is the reader/resolver
    budget, each statement gets min(2 s, remaining), never under 1 ms, and a
    read whose budget expired never succeeds. It is NOT a hard full-HTTP
    cancellation guarantee, so overshoot is RECORDED for Mastermind and never
    passed or failed against a tolerance chosen here."""
    if not result:
        return ['deadline: the budget-exhaustion probe did not run']
    failures = []
    for scope in ('reader', 'http'):
        part = result.get(scope)
        if not part:
            failures.append(f'deadline: the {scope} budget-exhaustion case did not run')
            continue
        if part.get('status') == 200 or part.get('code') != 'analysis_limit':
            failures.append(f'deadline: {scope} read whose budget was exhausted answered '
                            f'{part.get("status")!r}/{part.get("code")!r}, not 503 analysis_limit')
        handed = part.get('handed_timeouts_s')
        if not handed:
            failures.append(f'deadline: {scope} reader statement limits were not recorded')
        else:
            if len(handed) > MAX_DATA_SELECTS:
                failures.append(f'deadline: {scope} reader issued {len(handed)} data statements')
            bad = [value for value in handed
                   if not isinstance(value, (int, float))
                   or value < MIN_STATEMENT_S or value > STATEMENT_LIMIT_S]
            if bad:
                failures.append(f'deadline: {scope} statement limits outside '
                                f'[{MIN_STATEMENT_S}, {STATEMENT_LIMIT_S}] s: {bad}')
        for measure in ('elapsed_s', 'overshoot_s'):
            if not isinstance(part.get(measure), (int, float)):
                failures.append(f'deadline: {scope} {measure} was not measured')
    if not isinstance((result.get('http') or {}).get('full_request_ms'), (int, float)):
        failures.append('deadline: full-request duration was not measured separately')
    if result.get('acceptance') != DEADLINE_ACCEPTANCE:
        failures.append('deadline: overshoot must be returned for a Mastermind ruling, not self-approved')
    return failures


# --- dialect ---------------------------------------------------------------------

def dialect_record(dialect, timeout_dialect) -> dict:
    """U10: the timeout dialect only once a real connection initialized the
    engine. Before the first connect SQLAlchemy reports is_mariadb=False on a
    MariaDB server, so a label read earlier would be wrong; it is refused."""
    version = getattr(dialect, 'server_version_info', None)
    if version is None:
        return {'initialized': False, 'timeout_dialect': None,
                'failure': 'timeout dialect not recorded: no connection has initialized the '
                           'engine dialect yet'}
    return {'initialized': True, 'server_version_info': list(version),
            'timeout_dialect': timeout_dialect(), 'failure': None}


# --- owned fixtures ---------------------------------------------------------------

SYMBOL = re.compile(r'^ZQ[A-Z0-9]{2,10}$')
USERNAME = re.compile(r'^zq-ha1-[a-z0-9]{1,12}-[a-z0-9]{1,24}$')
MANIFEST_VERSION = 1
#: Delete order: children before the rows they reference.
KINDS = ('bucket', 'close', 'instrument', 'company', 'user')


class FixtureCollision(RuntimeError):
    """A planned identity already exists. Nothing was written."""


class CleanupIncomplete(RuntimeError):
    """Owned rows could not all be removed; the message lists what remains
    and `.remaining` carries the exact keys (no secrets)."""

    def __init__(self, message, remaining=None):
        super().__init__(message)
        self.remaining = remaining or {}


def run_token() -> str:
    return secrets.token_hex(3).upper()


def owned_symbol(role: str, token: str) -> str:
    symbol = f'ZQ{role}{token}'.upper()
    if not SYMBOL.match(symbol):
        raise ValueError(f'{symbol!r} is not an owned HA1 fixture symbol')
    return symbol


def owned_username(role: str, token: str) -> str:
    name = f'zq-ha1-{token}-{role}'.lower()
    if not USERNAME.match(name):
        raise ValueError(f'{name!r} is not an owned HA1 fixture username')
    return name


class OwnedFixtures:
    """Exactly the rows one run created, and nothing else.

    Use as a context manager. Entering asks the store whether any planned
    symbol or username already exists in any touched table and refuses
    (`FixtureCollision`) BEFORE any mutation. Every created row is recorded by
    its exact key; `cleanup()` deletes only those keys and then verifies none
    remain. Leaving the block always cleans up, unless `persist()` was called
    and the block ended without an exception (the preview's seeded fixtures,
    removed later from their manifest).

    CORRECTION-2 (U7): a cleanup failure is kept, not only printed.
    `cleanup_report()` states whether cleanup completed and lists the owned
    identities still present, so a structured report can carry BOTH the
    original failure and the cleanup failure.

    The store interface: `existing(symbols, usernames) -> {table: [values]}`,
    `delete(kind, keys)`, `count_owned(kind, keys) -> int`, and optionally
    `prepare_cleanup()` (discard a failed transaction first).
    """

    def __init__(self, store, symbols, usernames=()):
        self.store = store
        self.symbols = tuple(symbols)
        self.usernames = tuple(usernames)
        for symbol in self.symbols:
            if not SYMBOL.match(symbol):
                raise ValueError(f'{symbol!r} is not an owned HA1 fixture symbol')
        for name in self.usernames:
            if not USERNAME.match(name):
                raise ValueError(f'{name!r} is not an owned HA1 fixture username')
        self.keys: dict[str, list] = {kind: [] for kind in KINDS}
        self._checked = False
        self._kept = False
        self.cleanup_status = 'not_run'
        self.cleanup_error = None
        self.remaining: dict[str, list] = {}

    def __enter__(self):
        found = self.store.existing(self.symbols, self.usernames)
        collisions = {table: values for table, values in found.items() if values}
        if collisions:
            raise FixtureCollision(
                'planned HA1 fixture identities already exist; nothing was written: '
                + '; '.join(f'{table}: {sorted(map(str, values))}'
                            for table, values in sorted(collisions.items())))
        self._checked = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._kept and exc_type is None:
            self.cleanup_status = 'kept'
            return False
        try:
            self.cleanup()
        except CleanupIncomplete as cleanup_error:
            if exc_type is None:
                raise
            print(f'HA1 fixture cleanup incomplete after {exc_type.__name__}: {cleanup_error}',
                  file=sys.stderr)
            if exc is not None and hasattr(exc, 'add_note'):
                exc.add_note(f'HA1 fixture cleanup incomplete: {cleanup_error}')
        return False

    def _check(self, kind, key):
        if not self._checked:
            raise RuntimeError('record() before the collision check')
        if kind not in KINDS:
            raise ValueError(f'unknown fixture kind {kind!r}')
        if kind == 'user':
            if key.get('username') not in self.usernames:
                raise ValueError(f'user {key.get("username")!r} was not planned')
            int(key['id'])
        elif kind == 'bucket':
            if key.get('ticker') not in self.symbols:
                raise ValueError(f'bucket ticker {key.get("ticker")!r} was not planned')
            if not isinstance(key.get('bucket_start'), dt.datetime) or not key.get('source'):
                raise ValueError('a bucket key needs bucket_start and source')
        else:
            owner = key.get('symbol') if kind == 'company' else key.get('ticker')
            if owner not in self.symbols:
                raise ValueError(f'{kind} owner {owner!r} was not planned')
            int(key['id'])

    def record(self, kind: str, key: dict):
        self._check(kind, key)
        self.keys[kind].append(dict(key))

    def delete_now(self, kind: str, key: dict):
        """Remove one owned row before cleanup (the overflow sentinel)."""
        if key not in self.keys[kind]:
            raise ValueError('only a recorded key can be deleted')
        self.store.delete(kind, [key])
        self.keys[kind].remove(key)

    def cleanup(self):
        errors = []
        remaining = {}
        if hasattr(self.store, 'prepare_cleanup'):
            try:
                self.store.prepare_cleanup()
            except Exception as exc:  # noqa: BLE001 -- recorded, cleanup continues
                errors.append(f'prepare: {type(exc).__name__}')
        for kind in KINDS:
            if self.keys[kind]:
                try:
                    self.store.delete(kind, self.keys[kind])
                except Exception as exc:  # noqa: BLE001
                    errors.append(f'{kind}: delete raised {type(exc).__name__}')
        for kind in KINDS:
            if self.keys[kind]:
                try:
                    left = self.store.count_owned(kind, self.keys[kind])
                except Exception as exc:  # noqa: BLE001
                    errors.append(f'{kind}: count raised {type(exc).__name__}')
                    remaining[kind] = [_encode(kind, key) for key in self.keys[kind]]
                else:
                    if left:
                        errors.append(f'{kind}: {left} owned row(s) still present')
                        remaining[kind] = [_encode(kind, key) for key in self.keys[kind]]
        if errors:
            self.cleanup_status = 'incomplete'
            self.remaining = remaining
            owners = sorted({str(key.get('username') or key.get('symbol') or key.get('ticker'))
                             for keys in remaining.values() for key in keys})
            self.cleanup_error = '; '.join(errors) + (
                f' (owned identities possibly remaining: {owners})' if owners else '')
            raise CleanupIncomplete(self.cleanup_error, remaining)
        self.cleanup_status = 'complete'
        self.cleanup_error = None
        self.remaining = {}
        self.keys = {kind: [] for kind in KINDS}

    def cleanup_report(self) -> dict:
        return {'status': self.cleanup_status, 'error': self.cleanup_error,
                'remaining': self.remaining,
                'planned_symbols': list(self.symbols), 'planned_usernames': list(self.usernames)}

    def persist(self, target: str) -> dict:
        self._kept = True
        return self.manifest(target)

    def manifest(self, target: str) -> dict:
        return {
            'version': MANIFEST_VERSION,
            'target': target,
            'symbols': list(self.symbols),
            'usernames': list(self.usernames),
            'keys': {kind: [_encode(kind, key) for key in self.keys[kind]] for kind in KINDS},
        }

    @classmethod
    def from_manifest(cls, store, document: dict, target: str) -> 'OwnedFixtures':
        if not isinstance(document, dict) or document.get('version') != MANIFEST_VERSION:
            raise ValueError('not a version 1 HA1 fixture manifest')
        if document.get('target') != target:
            raise ValueError(f'the manifest belongs to {document.get("target")!r}, '
                             f'not the gated target {target!r}; nothing was deleted')
        owned = cls(store, document.get('symbols') or (), document.get('usernames') or ())
        owned._checked = True
        for kind in KINDS:
            for key in (document.get('keys') or {}).get(kind, []):
                owned.record(kind, _decode(kind, key))
        return owned


def _encode(kind, key):
    if kind == 'bucket':
        return {**key, 'bucket_start': key['bucket_start'].isoformat()}
    return dict(key)


def _decode(kind, key):
    if kind == 'bucket':
        return {**key, 'bucket_start': dt.datetime.fromisoformat(key['bucket_start'])}
    return dict(key)


_SECRET_PATTERNS = (
    (re.compile(r'(://[^:/@\s]+:)[^@\s]+@'), r'\1***@'),
    (re.compile(r'(?i)(password|passwd|pwd|secret|token)(\s*[=:]\s*)[^\s,;&)]+'), r'\1\2***'),
)


def redact(text) -> str:
    """No credential in a structured report: URL passwords and key=value
    secrets are masked."""
    value = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def run_failure_report(original, owned) -> dict:
    """U7: one structured record that keeps the ORIGINAL failure and the
    CLEANUP outcome side by side, with the owned identities still present,
    and the exit code that follows from either."""
    cleanup = owned.cleanup_report() if owned is not None else {'status': 'not_started',
                                                                 'error': None, 'remaining': {}}
    failures = []
    if original is not None:
        failures.append(redact(f'original failure: {type(original).__name__}: {original}'))
    if cleanup['status'] == 'incomplete':
        failures.append(redact(f'cleanup failure: {cleanup["error"]}'))
    return {'original_failure': (redact(f'{type(original).__name__}: {original}')
                                 if original is not None else None),
            'cleanup': {**cleanup, 'error': redact(cleanup['error']) if cleanup['error'] else None},
            'failures': failures,
            'exit_code': 1 if failures else 0}


# --- source/build fingerprint (U8) -------------------------------------------------

FINGERPRINT_VERSION = 1
#: Relative to the candidate root: the application and harness source a gated
#: runtime executes, the templates it renders, the radar frontend source and
#: the built assets it serves. Untracked HA1 files are included by path, not
#: by Git status.
FINGERPRINT_INCLUDE = (
    'personal_apps/app.py', 'personal_apps/auth.py', 'personal_apps/extensions.py',
    'personal_apps/models.py', 'personal_apps/destructive_target.py',
    'personal_apps/vite_assets.py', 'personal_apps/request_timing.py',
    'personal_apps/features/radar/**/*.py',
    'personal_apps/templates/radar/**/*',
    'personal_apps/scratchpad/ha1/*.py',
    'personal_apps/static/radar/src/**/*',
    'personal_apps/static/radar/dist/**/*',
)
#: Mutable or irrelevant inputs that would make the fingerprint invalidate
#: itself: runtime identity records, fixture manifests, reports, logs, caches
#: and frontend test files that the build never serves.
#: (The harness writes all of its runtime records, manifests and reports
#: under radar-design/artifacts/, which no include reaches and this list
#: excludes again. No bare `runtime` directory pattern: it would silently
#: drop a legitimately named source folder.)
FINGERPRINT_EXCLUDE = (
    '*/__pycache__/*', '*.pyc', '*/.pytest_cache/*', '*/node_modules/*', '*.log', '*.tmp',
    'radar-design/artifacts/*', '*.test.ts', '*.test.tsx',
)
BUILD_PREFIX = 'personal_apps/static/radar/dist/'


def fingerprint_excluded(relative: str) -> bool:
    return any(fnmatch.fnmatchcase(relative, excluded) for excluded in FINGERPRINT_EXCLUDE)


def fingerprint_inputs(root) -> list[str]:
    root = Path(root)
    found = set()
    for pattern in FINGERPRINT_INCLUDE:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if fingerprint_excluded(relative):
                continue
            found.add(relative)
    return sorted(found)


def source_fingerprint(root) -> dict:
    """A deterministic digest of every covered input: sorted relative path,
    byte length and SHA-256 of the bytes. No mtimes, no Git state."""
    root = Path(root)
    files = {}
    digest = hashlib.sha256()
    for relative in fingerprint_inputs(root):
        data = (root / relative).read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        files[relative] = file_hash
        digest.update(f'{relative}\0{len(data)}\0{file_hash}\n'.encode('utf-8'))
    return {'version': FINGERPRINT_VERSION, 'digest': digest.hexdigest(), 'files': files,
            'build_files': sum(1 for relative in files if relative.startswith(BUILD_PREFIX))}


def fingerprint_failures(started, current) -> list[str]:
    """Why a runtime started from `started` cannot vouch for `current`, or []."""
    failures = []
    if not current.get('build_files'):
        failures.append('no served build assets under personal_apps/static/radar/dist: run '
                        '`npm run build`, then restart local_runtime.py serve deliberately')
    if not isinstance(started, dict) or not started.get('digest'):
        failures.append('the runtime record carries no source/build fingerprint: restart '
                        'local_runtime.py serve deliberately (no process was stopped)')
    elif started.get('digest') != current.get('digest'):
        before, after = started.get('files') or {}, current.get('files') or {}
        changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
        shown = ', '.join(changed[:12]) + (f' (+{len(changed) - 12} more)' if len(changed) > 12 else '')
        failures.append(f'source/build drift since the runtime started ({shown or "digest differs"}): '
                        'rebuild if frontend source changed, then restart local_runtime.py serve '
                        'deliberately; the running server was NOT stopped')
    return failures


# --- preview identity -------------------------------------------------------------

RUNTIME_VERSION = 2


def preview_identity_failures(document, *, target, registry, root, branch, head, port,
                              header_nonce, pid_alive, fingerprint=None) -> list[str]:
    """Why the listening preview cannot be trusted as THIS gated candidate
    bound to THIS registered HA1 database and THIS source/build, or []."""
    if not isinstance(document, dict):
        return ['no runtime identity record for this port: start '
                'scratchpad/ha1/local_runtime.py serve <port> in this candidate first']
    expected = {'version': RUNTIME_VERSION, 'target': target, 'registry': registry,
                'candidate_root': str(root), 'branch': branch, 'head': head, 'port': port}
    failures = [f'runtime {name} is {document.get(name)!r}, expected {value!r}'
                for name, value in expected.items() if document.get(name) != value]
    if not document.get('nonce') or header_nonce != document.get('nonce'):
        failures.append("the listening server did not answer with this runtime's nonce")
    if not pid_alive:
        failures.append('the recorded runtime process is not alive')
    if fingerprint is None:
        failures.append('the current source/build fingerprint was not computed')
    else:
        failures += fingerprint_failures(document.get('fingerprint'), fingerprint)
    return failures


# --- case recording (C15/C16) --------------------------------------------------------

class Case:
    """One acceptance case's checks inside one block.

    `check` counts every evaluated assertion. `unsupported` records a check
    that could not be evaluated in this environment; it is reported as a
    failure, never mistaken for success."""

    def __init__(self, name, label=''):
        self.name = name
        self.label = label
        self.checks = 0
        self.failures = []
        self.unsupported_checks = []
        self.facts = {}

    def check(self, condition, message):
        self.checks += 1
        if not condition:
            self.failures.append(message)
        return bool(condition)

    def unsupported(self, message):
        self.unsupported_checks.append(message)


def record_case(results, case, raised=None):
    entry = results.setdefault(case.name, {'failures': [], 'facts': {}, 'checks': 0})
    entry.setdefault('checks', 0)
    entry.setdefault('facts', {})
    prefix = f'[{case.label}] ' if case.label else ''
    problems = list(case.failures)
    problems += [f'UNSUPPORTED, not a pass: {message}' for message in case.unsupported_checks]
    if raised is not None:
        problems.append(f'raised {type(raised).__name__}: {raised}')
    elif case.checks == 0 and not case.unsupported_checks:
        problems.append('no check was evaluated; a case with zero checks is not a pass')
    entry['failures'] += [prefix + problem for problem in problems]
    entry['checks'] += case.checks
    if case.facts:
        entry['facts'][case.label or 'all'] = case.facts


@contextmanager
def cases(results, names, label=''):
    """Several cases sharing one block. An exception raised in the block is
    recorded against EVERY case in it (nested `with case(A), case(B)` used to
    attribute it only to B, leaving A looking passed)."""
    current = tuple(Case(name, label) for name in names)
    raised = None
    try:
        yield current
    except Exception as exc:  # noqa: BLE001 -- a raised check is a recorded failure
        raised = exc
    finally:
        for one in current:
            record_case(results, one, raised)


@contextmanager
def case(results, name, label=''):
    with cases(results, (name,), label) as (one,):
        yield one


C16_CASES = (
    'gate_identity', 'empty_analysis', 'resolve_pin_replace', 'de_entry_us_label',
    'back_restores_board', 'viewport_1440', 'viewport_1920', 'viewport_768',
    'viewport_390', 'viewport_320', 'zoom_200', 'reduced_motion', 'keyboard_days',
    'keyboard_table', 'focus_visible', 'touch_targets_44', 'no_document_overflow',
    'contrast_text', 'us_primary_usd_visible_mobile', 'loading_state',
    'network_error_retry', 'timeout_error', 'session_expiry', 'invalid_range_pinned',
    'invalid_range_ticker_only', 'explicit_range_push_back_refresh', 'one_close',
    'no_close_no_chatter', 'partial_truncated_zero', 'config_transition', 'overlap',
    'identity_boundary', 'regime_change', 'invalid_row_closed_day_close', 'excluded_rows',
    'stale_link_409', 'ineligible_422', 'ambiguous_resolve_409', 'limit_503',
    'non_admin_access',
    # CORRECTION-2 (U6/U9)
    'contrast_graphics', 'touch_select_and_scroll_reach', 'chart_control_alignment',
    'price_line_runs', 'skip_link_and_tab_order', 'menu_escape', 'source_build_identity',
)

#: CORRECTION-2 (U3): C15 in the actual app, with owned identities only.
C15_CASES = (
    'c15_root_overview_mount', 'c15_hub_alias_mount', 'c15_legacy_mount_and_return',
    'c15_signed_out_redirects', 'c15_valid_t_bookmark', 'c15_valid_hash_overrides_t',
    'c15_invalid_hash_fallback', 'c15_filter_only_bookmark', 'c15_canonical_analysis_link',
    'c15_back_to_pre_selection_analysis', 'c15_no_board_poll_on_analysis',
)

ACCEPTANCE_CASES = C16_CASES + C15_CASES


def case_failures(results: dict, required=ACCEPTANCE_CASES) -> list[str]:
    failures = [f'case {name} was not recorded' for name in required if name not in results]
    for name, outcome in sorted(results.items()):
        problems = outcome.get('failures', [])
        failures += [f'{name}: {problem}' for problem in problems]
        if not problems and not outcome.get('checks'):
            failures.append(f'{name}: no check was evaluated; a case with zero checks is not a pass')
    return failures


def c16_failures(results: dict) -> list[str]:
    return case_failures(results, ACCEPTANCE_CASES)


# --- contrast (U6) --------------------------------------------------------------------

TEXT_CONTRAST_MIN = 4.5
GRAPHIC_CONTRAST_MIN = 3.0


class UnsupportedColour(ValueError):
    """A computed colour this harness cannot evaluate. A failure, never a skip."""


class UnverifiedBackground(ValueError):
    """The painted background cannot be established (no opaque ancestor, or a
    background image in the way). A failure, never a skip."""


_RGB = re.compile(r'^rgba?\(\s*([\d.]+)(?:\s*,\s*|\s+)([\d.]+)(?:\s*,\s*|\s+)([\d.]+)'
                  r'(?:\s*[,/]\s*([\d.]+%?))?\s*\)$')


def parse_color(text):
    """Computed `rgb()`/`rgba()` (comma or space syntax) and `transparent`.
    Anything else -- `oklch()`, `color(...)`, `none`, `url(#...)` -- raises."""
    value = (text or '').strip().lower()
    if value == 'transparent':
        return (0.0, 0.0, 0.0), 0.0
    match = _RGB.match(value)
    if not match:
        raise UnsupportedColour(f'unsupported colour {text!r}')
    channels = tuple(float(match.group(index)) for index in (1, 2, 3))
    raw = match.group(4)
    if raw is None:
        alpha = 1.0
    elif raw.endswith('%'):
        alpha = float(raw[:-1]) / 100
    else:
        alpha = float(raw)
    if any(channel > 255 for channel in channels) or not 0 <= alpha <= 1:
        raise UnsupportedColour(f'out-of-range colour {text!r}')
    return channels, alpha


def composite(foreground, alpha, background):
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(foreground, background))


def effective_background(layers):
    """`layers` run from the element outwards to the root: each
    {'node', 'color', 'image'}. Composite translucent layers over the nearest
    opaque one; refuse when none is opaque or an image paints in between."""
    stack = []
    for layer in layers or ():
        if layer.get('image'):
            raise UnverifiedBackground(f'background image on {layer.get("node")!r} '
                                       'cannot be composited')
        rgb, alpha = parse_color(layer.get('color'))
        stack.append((rgb, alpha))
        if alpha >= 1:
            break
    else:
        raise UnverifiedBackground('no opaque background up to the document root')
    rgb = stack[-1][0]
    for over, alpha in reversed(stack[:-1]):
        rgb = composite(over, alpha, rgb)
    return rgb


def contrast_ratio(foreground, background) -> float:
    def luminance(rgb):
        channels = []
        for value in rgb:
            c = value / 255
            channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def contrast_failures(samples, *, minimum, kind):
    """`samples`: one entry per REQUIRED (selector, property):
    {'selector', 'property', 'matched', 'pairs': [{'value', 'layers'}]}.
    Every required selector must match a rendered element AND yield at least
    one evaluated pair at `minimum`. Returns (failures, evaluated)."""
    failures, evaluated = [], []
    if not samples:
        return [f'{kind}: no required selectors were sampled'], evaluated
    for sample in samples:
        where = f'{kind} {sample.get("selector")} {sample.get("property")}'
        if not sample.get('matched'):
            failures.append(f'{where}: required selector matched no rendered element')
            continue
        good = 0
        for pair in sample.get('pairs') or ():
            try:
                foreground, alpha = parse_color(pair.get('value'))
                background = effective_background(pair.get('layers'))
            except (UnsupportedColour, UnverifiedBackground) as exc:
                failures.append(f'{where}: {exc}; unverified, not skipped')
                continue
            if alpha <= 0:
                failures.append(f'{where}: fully transparent {pair.get("value")!r}; unverified')
                continue
            ratio = contrast_ratio(composite(foreground, alpha, background), background)
            good += 1
            evaluated.append({'selector': sample.get('selector'), 'property': sample.get('property'),
                              'ratio': round(ratio, 2)})
            if ratio < minimum:
                failures.append(f'{where}: contrast {ratio:.2f}:1 is below {minimum}:1')
        if good == 0 and sample.get('pairs'):
            failures.append(f'{where}: no pair could be evaluated')
        elif not sample.get('pairs'):
            failures.append(f'{where}: matched but no pair was sampled')
    if not evaluated:
        failures.append(f'{kind}: no contrast pair was evaluated')
    return failures, evaluated


# --- actual-app chart expectations (U9) -------------------------------------------------

def adjacent_runs(flags) -> list[list[int]]:
    """Index-adjacent runs of True: the price line joins neighbouring
    observed dates only (same regime assumed by the fixture), so any date
    without a close -- a weekend included -- breaks it."""
    runs, current = [], []
    for index, flag in enumerate(flags):
        if flag:
            current.append(index)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def interior_break_window(last_day: dt.date, is_trading_day, days=7, search=21):
    """The latest `days`-long window ending on or before `last_day` whose
    first and last dates are modeled trading days and which contains a
    modeled closed date strictly inside -- so the fixture proves both a
    connected run and a break. None if no such window exists in `search`."""
    for back in range(search):
        end = last_day - dt.timedelta(days=back)
        start = end - dt.timedelta(days=days - 1)
        window = [start + dt.timedelta(days=n) for n in range(days)]
        flags = [bool(is_trading_day(day)) for day in window]
        runs = adjacent_runs(flags)
        if flags[0] and flags[-1] and not all(flags) and any(len(run) > 1 for run in runs):
            return start, end
    return None


# --- the full-access host (U4) ----------------------------------------------------------

def host_session_get(client, host, user_id, path, *, scheme='http'):
    """Put `user_id` in the Flask test client's session ON `host`, then
    request `path` on that same host. A session set on the default test host
    never reaches another host (REVIEW-2 toy: 302 /login), so a request made
    that way proves nothing about the member gate."""
    base_url = f'{scheme}://{host}'
    with client.session_transaction(base_url=base_url) as flask_session:
        flask_session['user_id'] = user_id
    return client.get(path, base_url=base_url)
