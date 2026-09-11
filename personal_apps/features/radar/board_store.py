"""Where a built board is kept, and how the work of building it is handed out.

Two tables and no ambition beyond them. `radar_board_results` holds one row per
(generation, exact selection): the compressed payload, when it was built, and
the queue state of the key -- all in one row, so publishing is a single UPDATE
and there is no instant in which a payload exists but the state does not yet say
so. `radar_board_namespaces` holds one control row per generation, and its row
lock is the only mutex in the design.

Three properties are load-bearing, and each one is a property of the database
rather than of this file:

*The bounds hold across processes.* Every gunicorn worker admits work, and two
workers that both count 31 admitted jobs will both admit a 32nd. So admission
and eviction happen inside one transaction that begins by taking `SELECT ...
FOR UPDATE` on the generation's control row. A refused admission writes nothing
at all -- not even the demand -- because a row costs a slot that eviction has
to pay for later, and a queue that long will not reach the key inside anyone's
patience anyway.

*A builder that lost its lease cannot publish.* The fence is a random token
minted per claim, checked together with the generation, the key, the owner and
`queue_state = 'building'`. A counter would be cheaper and would not work: a
row that is evicted and then recreated by a later reader starts counting again
from zero, and the abandoned builder's number matches the fresh row exactly.
Nothing brings a `secrets.token_hex(16)` back.

*Queue state and payload availability are independent.* Nothing here decides
what a viewer should be shown; that is read off the payload and its age by the
read path. This module moves keys between `idle`, `pending`, `building` and
`failed`, and stores blobs. A `failed` row keeps the board it published last
time, and goes on serving it while it backs off.

Everything takes the clock as an argument. The store never asks what time it is,
which is what makes a lease expiry or a backoff boundary something a test can
assert rather than wait for. Every function opens and closes its own
transactions; none accepts one and none leaves one open, because a claim held
inside a transaction would hold row locks for the length of a build.
"""
import dataclasses
import datetime as dt
import logging
import os
import secrets

import sqlalchemy as sa

from . import board_namespace

logger = logging.getLogger(__name__)

RESULTS = 'radar_board_results'
NAMESPACES = 'radar_board_namespaces'

# How many claimable rows one claim examines before giving up. The fenced
# UPDATE can lose to another producer, so a single candidate would make a
# claim fail whenever two producers overlapped; eight is enough that losing
# every one of them means there was genuinely no work.
_CANDIDATES = 8

# 16 bytes of randomness, written as the 32 hex characters `lease_token` holds.
_TOKEN_BYTES = 16

# `last_error` and `producer_error` are VARCHAR(255).
_ERROR_WIDTH = 255

# The retry curve: 30 s, doubling, never past 900 s. Past `max_attempts` the
# key is parked instead -- which is a slower rate, not a stop, because a key
# that starts working again should recover without anyone restarting anything.
_BACKOFF_BASE = 30
_BACKOFF_CEILING = 900

_RESULT_COLUMNS = (
    'key_hash, key_json, queue_state, warm, payload, payload_version, as_of, '
    'built_at, build_ms, enqueued_at, requested_at, request_count, attempts, '
    'next_attempt_at, last_error, lease_expires_at')

_NAMESPACE_COLUMNS = (
    'namespace, payload_version, producer_revision, created_at, last_seen_at, '
    'producer_owner, producer_seen_at, producer_success_at, producer_error')

# A row the producer may take. `pending` is the ordinary case; a `failed` row
# past its backoff is a retry; a `building` row whose lease has run out is a
# builder that died, and reclaiming it is the only thing that frees the key.
_CLAIMABLE = ("((queue_state = 'pending')"
              " OR (queue_state = 'failed' AND next_attempt_at <= :now)"
              " OR (queue_state = 'building' AND lease_expires_at < :now))")

# What the 32-job cap counts: work admitted and not yet finished. A parked key
# inside its backoff is deliberately absent -- it is waiting on a clock, not on
# the producer, and counting it would let six broken keys close the queue.
_ADMITTED = ("(queue_state IN ('pending', 'building')"
             " OR (queue_state = 'failed' AND next_attempt_at <= :now))")


@dataclasses.dataclass(frozen=True)
class Limits:
    """Every number this store obeys, in one place.

    `warm_limit` has no environment variable on purpose. The other nine are
    operational knobs -- how fresh is fresh, how long a lease lasts, how much
    queue is too much -- and an operator can move them without a deploy. The
    number of warm boards is not a knob: it is however many standing selections
    the producer derives, and typing a different number here would not create
    or remove one. It lives here so readiness has something to compare against.
    """
    fresh_seconds: float = 120.0
    hard_expiry_seconds: float = 600.0
    refresh_seconds: float = 120.0
    lease_seconds: float = 120.0
    max_queue: int = 32
    max_on_demand: int = 128
    max_attempts: int = 6
    park_seconds: float = 900.0
    retire_seconds: float = 86400.0
    warm_limit: int = 8


_ENVIRONMENT = (
    ('fresh_seconds', 'RADAR_BOARD_FRESH_SECONDS', float),
    ('hard_expiry_seconds', 'RADAR_BOARD_HARD_EXPIRY_SECONDS', float),
    ('refresh_seconds', 'RADAR_BOARD_REFRESH_SECONDS', float),
    ('lease_seconds', 'RADAR_BOARD_LEASE_SECONDS', float),
    ('max_queue', 'RADAR_BOARD_MAX_QUEUE', int),
    ('max_on_demand', 'RADAR_BOARD_MAX_ON_DEMAND', int),
    ('max_attempts', 'RADAR_BOARD_MAX_ATTEMPTS', int),
    ('park_seconds', 'RADAR_BOARD_PARK_SECONDS', float),
    ('retire_seconds', 'RADAR_BOARD_NAMESPACE_RETIRE_SECONDS', float),
)


@dataclasses.dataclass(frozen=True)
class Result:
    """One stored row, as everything outside this module sees it.

    Deliberately not the whole row. The lease owner and token are the store's
    business and nobody else's -- a caller that could read the live token could
    publish under someone else's fence -- and `payload_bytes` is derivable from
    the payload. `lease_expires_at` is here because an operator looking at a
    stuck key wants to know when it will free itself.
    """
    key_hash: str
    key_json: str
    queue_state: str
    warm: bool
    payload: bytes | None
    payload_version: int
    as_of: dt.datetime | None
    built_at: dt.datetime | None
    build_ms: int | None
    enqueued_at: dt.datetime | None
    requested_at: dt.datetime
    request_count: int
    attempts: int
    next_attempt_at: dt.datetime | None
    last_error: str | None
    lease_expires_at: dt.datetime | None


@dataclasses.dataclass(frozen=True)
class Claim:
    """The right to build one key, for as long as the lease lasts.

    Frozen, and carried by value: it is handed across a build that takes
    seconds with no transaction open, and the only thing that makes it
    authoritative when it comes back is `token` still matching the row.
    """
    key_hash: str
    key_json: str
    token: str
    owner: str
    warm: bool
    enqueued_at: dt.datetime | None
    attempts: int


def limits(env=os.environ):
    """The limits in force right now.

    Read on every call rather than resolved once. It is nine dictionary lookups
    against a process that is about to talk to a database, so the cost is
    nothing, and it means an operator who changes `RADAR_BOARD_MAX_QUEUE` gets
    the new bound on the next request instead of on the next restart.

    A value this cannot use is SAID and then ignored, and the default stands.
    This used to raise, on the argument that a silent fallback would quietly
    restore a bound the operator meant to move. That argument stopped holding
    once the reader path began calling it: `routes/api._direct_envelope` reads
    it on every synchronous build, so one mistyped tuning variable answered
    `/radar/`, `/radar/hub/` and `/radar/api/board` with a 500 WITH THE FLAG
    OFF -- taking down the path the whole rollout falls back to, over a knob
    only the shared path uses. The loud refusal is kept where an operator is
    watching for it: `validate_limits`, at the producer's startup.
    """
    overrides, refused = _read(env)
    for name, raw, reason in refused:
        if (name, raw) in _COMPLAINED:
            continue
        _COMPLAINED.add((name, raw))
        logger.error('radar board limit ignored, using the default: %s',
                     reason)
    return Limits(**overrides)


def validate_limits(env=os.environ):
    """Raise unless every tuning variable the environment sets is usable.

    For a process an operator starts and watches. A producer that came up on
    defaults because one variable was misspelled would run the wrong schedule
    for as long as nobody noticed, and there is nothing to lose by refusing to
    start: no reader is waiting on it, and the deploy that set the variable is
    the one being run. Readers take the opposite trade (`limits`).
    """
    _, refused = _read(env)
    if refused:
        raise board_namespace.ConfigError(
            '; '.join(reason for _, _, reason in refused))


# Limits that must be greater than zero. A bound of zero is not a tighter
# bound: `max_queue = 0` answers every on-demand admission `busy` for ever,
# `max_on_demand = 0` evicts every row as fast as it is written, and a lease
# of zero seconds has expired before the builder holding it reads it. Every
# other limit is a duration or a count where zero is coherent -- a refresh of
# zero is always due, a park of zero retries at once -- and only a negative
# value is not: -5 seconds of freshness marks every board stale the instant it
# is built.
_POSITIVE = frozenset({'max_queue', 'max_on_demand', 'lease_seconds'})

# Values already complained about, so a bad one is said once rather than on
# every request. Bounded by the number of distinct values the environment
# holds, which is at most one per variable per process.
_COMPLAINED = set()


def _refuse(field, name, cast, raw):
    """Why this value cannot be used, or None."""
    try:
        value = cast(raw)
    except ValueError:
        return f'{name} is not a number: {raw[:40]!r}'
    if field in _POSITIVE and value <= 0:
        return f'{name} must be greater than zero: {raw[:40]!r}'
    if field not in _POSITIVE and value < 0:
        return f'{name} cannot be negative: {raw[:40]!r}'
    return None


def _read(env):
    """Every override the environment asks for, and every one it got wrong."""
    overrides, refused = {}, []
    for field, name, cast in _ENVIRONMENT:
        raw = (env.get(name) or '').strip()
        if not raw:
            continue
        reason = _refuse(field, name, cast, raw)
        if reason is None:
            overrides[field] = cast(raw)
        else:
            refused.append((name, raw, reason))
    return overrides, refused


# --- the generation's control row -------------------------------------------

def ensure_namespace(engine, ns, now, *, revision, payload_version):
    """Introduce this generation, or say it is still here.

    Idempotent, and called on every producer tick and once per process by the
    read path. Either of them may be the caller that introduces a generation,
    and either may name its revision: a namespace *is* a revision --
    `board_namespace` derives the name from the payload version, the build
    revision and the configuration -- so a reader answering inside generation N
    shares that revision with the producer of N by construction, and cannot
    write a value the producer would disagree with. Two processes putting
    different revisions in one control row cannot happen: they would be two
    namespaces.

    The update arm rewrites the revision and the payload version rather than
    only stamping the clock. A row may have been created by `_adopt`, which
    leaves `producer_revision` NULL, and an update that only moved
    `last_seen_at` would leave that NULL standing for the whole life of the
    generation, with the admin surface reporting no revision at all.

    `created_at` is never touched. It is when this generation first appeared,
    which no later tick knows better than the first one did.

    `last_seen_at` moves by `GREATEST`, the same rule `_under_lock` uses and
    for the same reason: that column is the whole generation's clock and it is
    what retirement measures against, so a caller whose clock is behind the
    last one's -- a second producer overlapping a deploy, a host whose NTP
    stepped back -- must not be able to age a live generation towards deletion.
    """
    with engine.begin() as connection:
        connection.execute(sa.text(
            f'INSERT INTO {NAMESPACES}'
            ' (namespace, payload_version, producer_revision, created_at,'
            '  last_seen_at) VALUES (:ns, :version, :revision, :now, :now)'
            ' ON DUPLICATE KEY UPDATE'
            ' last_seen_at = GREATEST(last_seen_at, :now),'
            ' producer_revision = :revision, payload_version = :version'),
            {'ns': ns, 'version': payload_version, 'revision': revision,
             'now': now})


def heartbeat(engine, ns, owner, now, *, success_at=None, error=None):
    """Record that the producer is alive, and how its last job went.

    A success clears the last error as well as stamping the time, because an
    error left standing after the next successful build is a false alarm on the
    admin surface and someone will chase it. Passing neither leaves both alone:
    a plain tick says the producer is running, not that anything changed.

    `last_seen_at` moves by `GREATEST`, as it does everywhere: it is the
    generation's clock and retirement measures against it, so an argument from
    a producer whose clock is behind must not drag it backwards.
    `producer_seen_at` is assigned plainly, because that one IS this
    producer's claim about itself and the latest word on it is this call's.

    Returns whether there was a control row to update.
    """
    assignments = ['last_seen_at = GREATEST(last_seen_at, :now)',
                   'producer_owner = :owner', 'producer_seen_at = :now']
    params = {'ns': ns, 'now': now, 'owner': owner}
    if success_at is not None:
        assignments += ['producer_success_at = :success', 'producer_error = NULL']
        params['success'] = success_at
    if error is not None:
        assignments.append('producer_error = :error')
        params['error'] = str(error)[:_ERROR_WIDTH]

    with engine.begin() as connection:
        done = connection.execute(sa.text(
            f'UPDATE {NAMESPACES} SET {", ".join(assignments)}'
            ' WHERE namespace = :ns'), params)
        # Read inside the transaction. A CursorResult belongs to the connection
        # it came from, and `rowcount` after the block has closed it is a value
        # this code has no promise about.
        updated = done.rowcount
    return updated == 1


def health(engine, ns):
    """The generation's control row, or an empty mapping if there is none."""
    with engine.connect() as connection:
        row = connection.execute(sa.text(
            f'SELECT {_NAMESPACE_COLUMNS} FROM {NAMESPACES}'
            ' WHERE namespace = :ns'), {'ns': ns}).mappings().first()
    return dict(row) if row is not None else {}


def retire_namespaces(engine, keep_ns, now):
    """Delete generations nothing has touched for `retire_seconds`.

    Never the caller's own, whatever its `last_seen_at` says -- a reader whose
    producer has been down for a day is exactly the case where the rows are
    still the right rows, and a clock skew is not a reason to throw away the
    cache the caller is about to read.

    "Touched" means any admission, not merely a producer tick: `_under_lock`
    moves `last_seen_at` for every reader that admits, so a generation whose
    producer died yesterday but whose boards are still being read stays. That
    is the case where the stored boards matter most -- they are the only answer
    anybody has -- and deleting them under the readers still asking would empty
    the cache at precisely the wrong moment.

    A `building` row does not protect a generation here. Nothing has touched
    the control row for a day, so whatever was building it is long gone, and
    its lease expired within two minutes of that.

    One transaction per doomed generation, and the candidates are chosen
    WITHOUT `FOR UPDATE`. A single scanning `SELECT ... FOR UPDATE` would take
    exclusive locks along the way on the rows it examined and rejected -- the
    live generations' control rows, which are the mutex every web worker admits
    under -- and hold them for the length of the deletes. So the scan is a
    plain read, and each candidate is locked, re-checked under that lock, and
    deleted on its own. A generation that became live between the two steps
    fails the re-check and is left alone; the worst case is a retirement pass
    that skips it and finds it again tomorrow.

    Returns how many generations were retired.
    """
    cutoff = now - dt.timedelta(seconds=limits().retire_seconds)
    with engine.connect() as connection:
        candidates = connection.execute(sa.text(
            f'SELECT namespace FROM {NAMESPACES}'
            ' WHERE namespace <> :keep AND last_seen_at < :cutoff'),
            {'keep': keep_ns, 'cutoff': cutoff}).scalars().all()

    retired = []
    for candidate in candidates:
        deleted = False
        with engine.begin() as connection:
            last_seen = connection.execute(sa.text(
                f'SELECT last_seen_at FROM {NAMESPACES}'
                ' WHERE namespace = :ns FOR UPDATE'),
                {'ns': candidate}).scalar()
            if last_seen is not None and last_seen < cutoff:
                for statement in (
                        f'DELETE FROM {RESULTS} WHERE namespace = :ns',
                        f'DELETE FROM {NAMESPACES} WHERE namespace = :ns'):
                    connection.execute(sa.text(statement), {'ns': candidate})
                deleted = True
        # Counted after the commit, so a generation this pass DECLINED to
        # delete -- one that became live between the scan and the lock -- is
        # not reported as retired. A generation this pass failed to delete is
        # not a case the count has to describe: the commit raises and the
        # whole call goes out with it.
        if deleted:
            retired.append(candidate)
    return len(retired)


# --- reading ----------------------------------------------------------------

def read(engine, ns, key_hash):
    """The stored row for one key, or None. Never builds and never enqueues."""
    with engine.connect() as connection:
        row = connection.execute(sa.text(
            f'SELECT {_RESULT_COLUMNS} FROM {RESULTS}'
            ' WHERE namespace = :ns AND key_hash = :key'),
            {'ns': ns, 'key': key_hash}).mappings().first()
    if row is None:
        return None
    return Result(
        key_hash=row['key_hash'], key_json=row['key_json'],
        queue_state=row['queue_state'], warm=bool(row['warm']),
        payload=row['payload'], payload_version=row['payload_version'],
        as_of=row['as_of'], built_at=row['built_at'],
        build_ms=row['build_ms'], enqueued_at=row['enqueued_at'],
        requested_at=row['requested_at'], request_count=row['request_count'],
        attempts=row['attempts'], next_attempt_at=row['next_attempt_at'],
        last_error=row['last_error'],
        lease_expires_at=row['lease_expires_at'])


def queue_summary(engine, ns, now):
    """How much work this generation has, in one round trip.

    `warm_ready` counts warm keys with a payload no older than
    `fresh_seconds` -- readiness in the sense the producer's readiness probe
    means it, not merely "has been built at some point".
    """
    bounds = limits()
    with engine.connect() as connection:
        row = connection.execute(sa.text(f"""
            SELECT SUM(queue_state = 'pending')                  AS pending,
                   SUM(queue_state = 'building')                 AS building,
                   SUM(queue_state = 'failed'
                       AND next_attempt_at <= :now)              AS failed_due,
                   SUM(warm = 0)                                 AS on_demand_rows,
                   SUM(warm = 1 AND payload IS NOT NULL
                       AND as_of >= :fresh)                      AS warm_ready
              FROM {RESULTS} WHERE namespace = :ns
        """), {'now': now, 'ns': ns,
               'fresh': now - dt.timedelta(seconds=bounds.fresh_seconds)}
        ).mappings().one()
    # SUM over no rows is NULL, and MySQL hands these back as Decimal.
    return {name: int(row[name] or 0)
            for name in ('pending', 'building', 'failed_due', 'on_demand_rows',
                         'warm_ready')}


# --- admission and eviction, under the generation's lock --------------------

def admit(engine, ns, key_hash, key_json, now, *, warm=False, poll=False):
    """Ask for a key to be built, and say what happened.

    `'pending'` the key is queued, `'building'` someone is on it already,
    `'parked'` its last build failed and it is inside its backoff, `'busy'` the
    generation already has as much work as it will take -- and in that last
    case nothing at all was written.

    `poll=True` is a viewer asking again about a key it already asked for. It
    records the demand on `requested_at`, which is what eviction ranks by, but
    it does not count as a request and it does not move `enqueued_at`: a viewer
    that polls every second must not jump the queue past one that asked once
    and waited. It still inserts a missing row, because the result may simply
    have been evicted between the first ask and this one, and answering
    `pending` for a row that does not exist is a poll that never ends.
    """
    bounds = limits()
    return _under_lock(engine, ns, now, lambda connection: _admit(
        connection, ns, key_hash, key_json, now, warm=warm, poll=poll,
        bounds=bounds))


def evict(engine, ns, now):
    """Bring this generation back inside the on-demand row bound.

    Warm rows are never counted and never evicted; nor is a row being built.
    Returns how many rows were removed.
    """
    bounds = limits()
    return _under_lock(engine, ns, now,
                       lambda connection: _evict(connection, ns, bounds))


def refresh_warm(engine, ns, warm_keys, now):
    """Adopt the standing warm keys and enqueue the ones that have gone stale.

    `warm_keys` is an iterable of `(key_hash, key_json)` pairs, exactly as
    `board_keys.canonical` writes them -- the boards the producer keeps warm
    whether or not anyone is looking.

    A key is adopted as `idle` with no payload, so the one rule below decides
    both cases: never built (`as_of IS NULL`) and built too long ago are the
    same kind of due. Only `idle` rows are moved, which is what keeps a sweep
    from disturbing a build in flight or shortening a backoff.

    Nothing here demotes a key that has stopped being warm. It cannot happen
    inside one generation: the warm selections are derived from configuration,
    and configuration that moves gives every row a new namespace.

    Returns how many keys were enqueued.
    """
    bounds = limits()
    pairs = [(key_hash, key_json) for key_hash, key_json in warm_keys]

    def work(connection):
        if pairs:
            connection.execute(sa.text(f"""
                INSERT INTO {RESULTS}
                    (namespace, key_hash, key_json, payload_version,
                     queue_state, warm, requested_at, request_count, attempts)
                VALUES (:ns, :key, :json, :version, 'idle', 1, :now, 0, 0)
                ON DUPLICATE KEY UPDATE warm = 1
            """), [{'ns': ns, 'key': key_hash, 'json': key_json,
                    'version': board_namespace.PAYLOAD_VERSION, 'now': now}
                   for key_hash, key_json in pairs])
        moved = connection.execute(sa.text(f"""
            UPDATE {RESULTS} SET queue_state = 'pending', enqueued_at = :now
             WHERE namespace = :ns AND warm = 1 AND queue_state = 'idle'
               AND (as_of IS NULL OR as_of <= :cutoff)
        """), {'now': now, 'ns': ns,
               'cutoff': now - dt.timedelta(seconds=bounds.refresh_seconds)})
        return moved.rowcount

    return _under_lock(engine, ns, now, work)


def due_warm(engine, ns, now):
    """The warm keys whose board is missing or older than `refresh_seconds`.

    Oldest first, with the never-built ahead of everything: a board nobody has
    ever produced is infinitely stale, and any other order leaves the eight
    standing boards taking turns to be the one that is missing.
    """
    cutoff = now - dt.timedelta(seconds=limits().refresh_seconds)
    with engine.connect() as connection:
        return connection.execute(sa.text(
            f'SELECT key_hash FROM {RESULTS}'
            ' WHERE namespace = :ns AND warm = 1'
            ' AND (as_of IS NULL OR as_of <= :cutoff)'
            ' ORDER BY as_of IS NULL DESC, as_of ASC, key_hash ASC'),
            {'ns': ns, 'cutoff': cutoff}).scalars().all()


# --- the producer's side ----------------------------------------------------

def claim(engine, ns, owner, now, *, prefer='warm'):
    """Take a fenced lease on one claimable key of the named class, or None.

    One class only. `prefer='warm'` looks at warm rows oldest-board-first,
    `prefer='demand'` at on-demand rows oldest-request-first, and neither falls
    back to the other -- the caller alternates between them, and it can only do
    that if it is told which class was empty rather than quietly handed the
    other one.

    The transaction commits before this returns. A build takes seconds and must
    not hold a row lock for any of them; the lease, not a transaction, is what
    keeps a second producer off the key.
    """
    if prefer not in ('warm', 'demand'):
        raise ValueError(f"prefer must be 'warm' or 'demand', not {prefer!r}")
    bounds = limits()
    wants_warm = prefer == 'warm'
    # Warm work is ordered by the age of the board, with the never-built ahead
    # of everything -- a board nobody has ever produced is infinitely stale, and
    # `as_of IS NULL` is a real state a warm row sits in until its first build.
    # On-demand work is ordered by arrival, plainly: an admitted row always has
    # an `enqueued_at`, so there is no NULL case to rank.
    order = ('as_of IS NULL DESC, as_of ASC' if wants_warm
             else 'enqueued_at ASC')

    with engine.connect() as connection:
        candidates = connection.execute(sa.text(
            f'SELECT key_hash FROM {RESULTS}'
            ' WHERE namespace = :ns AND warm = :warm'
            f' AND {_CLAIMABLE}'
            f' ORDER BY {order}, key_hash ASC LIMIT :candidates'),
            {'ns': ns, 'warm': 1 if wants_warm else 0, 'now': now,
             'candidates': _CANDIDATES}).scalars().all()

    for candidate in candidates:
        token = secrets.token_hex(_TOKEN_BYTES)
        with engine.begin() as connection:
            taken = connection.execute(sa.text(f"""
                UPDATE {RESULTS}
                   SET queue_state = 'building', lease_owner = :owner,
                       lease_token = :token, lease_expires_at = :expires,
                       attempts = LEAST(attempts + 1, :max_attempts)
                 WHERE namespace = :ns AND key_hash = :key AND {_CLAIMABLE}
            """), {'owner': owner, 'token': token, 'ns': ns, 'key': candidate,
                   'now': now, 'max_attempts': bounds.max_attempts,
                   'expires': now + dt.timedelta(seconds=bounds.lease_seconds)})
            if taken.rowcount != 1:
                # Another producer got there between the two statements. The
                # candidate list is stale, not wrong -- try the next one.
                continue
            # Read back inside the claiming transaction, so what is carried
            # away is what the row says and not merely what was sent.
            row = connection.execute(sa.text(
                'SELECT key_json, lease_token, warm, enqueued_at, attempts'
                f' FROM {RESULTS} WHERE namespace = :ns AND key_hash = :key'),
                {'ns': ns, 'key': candidate}).mappings().one()
        if row['lease_token'] != token:
            continue
        return Claim(key_hash=candidate, key_json=row['key_json'],
                     token=row['lease_token'], owner=owner,
                     warm=bool(row['warm']), enqueued_at=row['enqueued_at'],
                     attempts=row['attempts'])
    return None


def publish(engine, ns, claim, blob, *, as_of, built_at, build_ms,
            producer_revision):
    """Store a finished board. False means the lease was lost: discard it.

    False is not an error. It means the key was reclaimed while this build was
    running, so someone else's result is newer than this one, and writing this
    one would replace a fresh board with a stale one.
    """
    with engine.begin() as connection:
        done = connection.execute(sa.text(f"""
            UPDATE {RESULTS}
               SET queue_state = 'idle', payload = :blob, payload_bytes = :size,
                   as_of = :as_of, built_at = :built_at, build_ms = :build_ms,
                   payload_version = :version, producer_revision = :revision,
                   lease_owner = NULL, lease_token = NULL,
                   lease_expires_at = NULL, attempts = 0, last_error = NULL,
                   next_attempt_at = NULL
             WHERE namespace = :ns AND key_hash = :key
               AND lease_owner = :owner AND lease_token = :token
               AND queue_state = 'building'
        """).bindparams(sa.bindparam('blob', type_=sa.LargeBinary)),
            {'blob': blob, 'size': len(blob), 'as_of': as_of,
             'built_at': built_at, 'build_ms': build_ms,
             'version': board_namespace.PAYLOAD_VERSION,
             'revision': producer_revision, 'ns': ns, 'key': claim.key_hash,
             'owner': claim.owner, 'token': claim.token})
        # Inside the block: the fence's whole answer is this number, and a
        # closed connection is not where to go looking for it.
        stored = done.rowcount
    return stored == 1


def fail(engine, ns, claim, error, now):
    """Record a failed build and set the retry clock. False means overtaken.

    `payload`, `as_of` and `built_at` are deliberately untouched. The last good
    board goes on being served, with its real age, while the key backs off --
    a broken rebuild is a reason to say the board is old, not a reason to have
    no board.

    Fenced on the same four columns as `publish`, so a builder that lost its
    lease can no more mark a key failed than it can publish to it. Otherwise a
    slow build could park a key that somebody else had just built successfully.

    The backoff is computed from the attempt count the claim carries rather
    than re-read here. Under the fence they are the same number -- only a claim
    changes `attempts`, and a claim would have changed the token too, in which
    case this UPDATE matches nothing and the delay is never used.
    """
    bounds = limits()
    with engine.begin() as connection:
        done = connection.execute(sa.text(f"""
            UPDATE {RESULTS}
               SET queue_state = 'failed', last_error = :error,
                   next_attempt_at = :next_attempt, lease_owner = NULL,
                   lease_token = NULL, lease_expires_at = NULL
             WHERE namespace = :ns AND key_hash = :key
               AND lease_owner = :owner AND lease_token = :token
               AND queue_state = 'building'
        """), {'error': str(error)[:_ERROR_WIDTH],
               'next_attempt': now + dt.timedelta(
                   seconds=_backoff(claim.attempts, bounds)),
               'ns': ns, 'key': claim.key_hash, 'owner': claim.owner,
               'token': claim.token})
        marked = done.rowcount
    return marked == 1


def _backoff(attempts, bounds):
    """How long a key waits before it may be tried again.

    Doubling from 30 s, and at `max_attempts` parked for `park_seconds`
    instead. Parked is a rate rather than a stop: a key broken by data that is
    itself being repaired has to be able to come back on its own, and a rule
    that stopped retrying until a reader asked again would be no backoff at all
    -- readers poll, so every poll would restart the build immediately.
    """
    attempts = min(max(int(attempts), 1), bounds.max_attempts)
    if attempts >= bounds.max_attempts:
        return bounds.park_seconds
    return min(_BACKOFF_BASE * 2 ** (attempts - 1), _BACKOFF_CEILING)


# --- the mechanics ----------------------------------------------------------

def _under_lock(engine, ns, now, work):
    """Run `work(connection)` holding the generation's control-row lock.

    The lock is a row that has to exist, and the first process to touch a
    generation may be a reader rather than the producer -- or the row may have
    been retired between two admissions. So a missing control row is created in
    a transaction of its own and the lock taken again, rather than pressing on
    without the mutex, which would silently drop the bounds this exists for.

    Holding the lock is also where `last_seen_at` is moved, which makes that
    column the clock of the whole generation and not of its producer: any
    admission -- a reader's, a poll's, the warm sweep's -- keeps the generation
    off the retirement list. One UPDATE on a row this transaction already holds
    exclusively, so it costs a statement and no additional lock.

    `GREATEST` rather than an assignment, because the caller's clock is an
    argument and two processes need not agree on it. A call passing an older
    moment (a test, a retry carrying the instant a request arrived) must not be
    able to age a generation backwards towards retirement.

    A refused admission rolls this back with everything else, because "a
    refusal writes nothing at all" is the rule that makes a `'busy'` answer
    cost a database round trip and not a row. Nothing is lost by it: a
    generation only answers `'busy'` when it already holds 32 admitted keys,
    and the viewers waiting on those poll them, which lands here and moves the
    clock.
    """
    for _ in range(2):
        with engine.begin() as connection:
            if connection.execute(sa.text(
                    f'SELECT namespace FROM {NAMESPACES}'
                    ' WHERE namespace = :ns FOR UPDATE'),
                    {'ns': ns}).first() is not None:
                connection.execute(sa.text(
                    f'UPDATE {NAMESPACES}'
                    ' SET last_seen_at = GREATEST(last_seen_at, :now)'
                    ' WHERE namespace = :ns'), {'ns': ns, 'now': now})
                return work(connection)
        _adopt(engine, ns, now)
    raise RuntimeError(
        f'no control row could be held for namespace {ns[:12]}...')


def _adopt(engine, ns, now):
    """A control row for a generation nobody has introduced yet.

    `producer_revision` is left NULL rather than guessed. The caller knows what
    revision it is, but this row describes the build that answers, and a reader
    creating the row is not that build; `ensure_namespace` fills it in when the
    producer arrives.
    """
    with engine.begin() as connection:
        connection.execute(sa.text(
            f'INSERT INTO {NAMESPACES}'
            ' (namespace, payload_version, created_at, last_seen_at)'
            ' VALUES (:ns, :version, :now, :now)'
            ' ON DUPLICATE KEY UPDATE last_seen_at = last_seen_at'),
            {'ns': ns, 'version': board_namespace.PAYLOAD_VERSION, 'now': now})


def _admit(connection, ns, key_hash, key_json, now, *, warm, poll, bounds):
    # A plain read, not `FOR UPDATE`. No other admission can be running -- they
    # all queue behind the control row -- so the only thing that can move this
    # row underneath us is the producer publishing or failing it, and both of
    # those take work OUT of the counted set. Reading a state that has since
    # been finished can therefore only make the cap check more permissive by
    # one job, against a queue that just got shorter.
    existing = connection.execute(sa.text(
        f'SELECT queue_state, next_attempt_at FROM {RESULTS}'
        ' WHERE namespace = :ns AND key_hash = :key'),
        {'ns': ns, 'key': key_hash}).mappings().first()
    state = existing['queue_state'] if existing else None
    retry_at = existing['next_attempt_at'] if existing else None

    parked = state == 'failed' and retry_at is not None and retry_at > now
    admitted = state in ('pending', 'building') or (
        state == 'failed' and retry_at is not None and retry_at <= now)

    # The cap is only in question when this admission would add a job to it.
    # A key already counted cannot be refused by the count it is part of, a
    # parked key is not entering the queue, and warm work is never refused --
    # the eight standing boards are the product, not a request.
    if not warm and not parked and not admitted:
        queued = connection.execute(sa.text(
            f'SELECT COUNT(*) FROM {RESULTS}'
            f' WHERE namespace = :ns AND {_ADMITTED}'),
            {'ns': ns, 'now': now}).scalar()
        if queued >= bounds.max_queue:
            connection.rollback()
            return 'busy'

    connection.execute(sa.text(f"""
        INSERT INTO {RESULTS}
            (namespace, key_hash, key_json, payload_version, queue_state, warm,
             enqueued_at, requested_at, request_count)
        VALUES (:ns, :key, :json, :version, 'pending', :warm, :now, :now,
                :initial)
        ON DUPLICATE KEY UPDATE
            requested_at = :now,
            request_count = request_count + :initial,
            warm = GREATEST(warm, :warm),
            enqueued_at = CASE
                WHEN queue_state IN ('pending', 'building') THEN enqueued_at
                WHEN queue_state = 'failed' AND next_attempt_at > :now
                    THEN enqueued_at
                ELSE :now END,
            queue_state = CASE
                WHEN queue_state = 'building' THEN 'building'
                WHEN queue_state = 'failed' AND next_attempt_at > :now
                    THEN 'failed'
                ELSE 'pending' END
    """), {'ns': ns, 'key': key_hash, 'json': key_json,
           'version': board_namespace.PAYLOAD_VERSION,
           'warm': 1 if warm else 0, 'now': now, 'initial': 0 if poll else 1})

    # Read back rather than inferred: `claim` moves a row from `pending` to
    # `building` without this lock, so what was true before the upsert is not
    # necessarily what the row says after it.
    stored = connection.execute(sa.text(
        f'SELECT queue_state FROM {RESULTS}'
        ' WHERE namespace = :ns AND key_hash = :key'),
        {'ns': ns, 'key': key_hash}).scalar()

    # In the same transaction as the admission that crossed the bound: an
    # eviction decided against a count somebody else is still changing is how
    # the bound stops being one.
    if not warm:
        _evict(connection, ns, bounds, protect=key_hash)
    return 'parked' if stored == 'failed' else stored


def _evict(connection, ns, bounds, *, protect=None):
    """Delete the least-wanted on-demand rows beyond the bound.

    Least wanted means oldest `requested_at`, which a poll refreshes -- a
    viewer still watching a board is a reason to keep it. A row being built is
    skipped even when it is the oldest: deleting it under its builder is
    precisely the shape that lets a finished build be published into a row that
    has since become somebody else's. `protect` is the key an admission just
    wrote, which must not be evicted by its own admission when everything
    older is busy being built.
    """
    extra = connection.execute(sa.text(
        f'SELECT COUNT(*) FROM {RESULTS} WHERE namespace = :ns AND warm = 0'),
        {'ns': ns}).scalar()
    if extra <= bounds.max_on_demand:
        return 0

    doomed = connection.execute(sa.text(
        f'SELECT key_hash FROM {RESULTS}'
        ' WHERE namespace = :ns AND warm = 0'
        " AND queue_state <> 'building' AND key_hash <> :protect"
        ' ORDER BY requested_at ASC, key_hash ASC LIMIT :count'),
        {'ns': ns, 'protect': protect or '',
         'count': extra - bounds.max_on_demand}).scalars().all()
    if not doomed:
        return 0
    connection.execute(
        sa.text(f'DELETE FROM {RESULTS}'
                ' WHERE namespace = :ns AND key_hash IN :doomed').bindparams(
                    sa.bindparam('doomed', expanding=True)),
        {'ns': ns, 'doomed': doomed})
    return len(doomed)
