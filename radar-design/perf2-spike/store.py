"""The bounded result store: one table carrying the payload AND the queue.

Part I.2 and I.3 of PERF2-PLAN, implemented against raw DDL on the disposable
fixture `personal_apps_radar_perf1`. NOTHING here goes into `models.py` and no
migration is added -- the table is created and dropped by the spike.

The whole point of one table is that publication is a single atomic `UPDATE`:
there is no window in which a payload exists but the state does not say so,
and no second table to keep consistent.

The lease is fenced. A builder that does not still hold the fence it claimed
under cannot publish, which is the first of the two defects Codex named in the
in-process single-flight; and a hung builder's lease expires and the reclaim
increments the fence past it, which is the second.
"""
import dataclasses
import datetime as dt
import zlib

import sqlalchemy as sa

TABLE = 'radar_board_results'

# The serialized shape's version. A stored payload at a different version is
# treated as missing -- that is deployment invalidation (Part I.4 step 2).
PAYLOAD_VERSION = 1

# Freshness, PROPOSED in Part I.5 and confirmed against S3's measured
# capacity. Every one of these is a knob the ledger reports a number for.
REFRESH_EVERY = 120         # seconds between warm sweeps
MAX_AGE = 300               # past this a served board is marked stale
HARD_MAX_AGE = 3600         # past this a stored board is treated as missing

# The producer's lease. Longer than the worst measured build by a wide
# margin, or a healthy builder gets fenced out by its own slowness.
LEASE_SECONDS = 120
MAX_ATTEMPTS = 6

# Bounds (Part I.2). Warm keys are never evicted.
MAX_ON_DEMAND_KEYS = 128
MAX_PENDING = 32

COMPRESS_LEVEL = 6

DDL = """
CREATE TABLE IF NOT EXISTS radar_board_results (
  key_hash          CHAR(64)      NOT NULL,
  key_json          VARCHAR(2048) NOT NULL,
  payload_version   SMALLINT      NOT NULL,
  producer_revision VARCHAR(64)   NULL,
  state             VARCHAR(16)   NOT NULL,
  warm              TINYINT       NOT NULL DEFAULT 0,
  as_of             DATETIME(6)   NULL,
  built_at          DATETIME(6)   NULL,
  build_ms          INT           NULL,
  payload           MEDIUMBLOB    NULL,
  payload_bytes     INT           NULL,
  requested_at      DATETIME(6)   NOT NULL,
  request_count     INT           NOT NULL DEFAULT 0,
  lease_owner       VARCHAR(64)   NULL,
  lease_expires_at  DATETIME(6)   NULL,
  fence             BIGINT        NOT NULL DEFAULT 0,
  attempts          SMALLINT      NOT NULL DEFAULT 0,
  next_attempt_at   DATETIME(6)   NULL,
  last_error        VARCHAR(255)  NULL,
  PRIMARY KEY (key_hash),
  KEY ix_radar_board_results_queue (state, next_attempt_at),
  KEY ix_radar_board_results_warm (warm, as_of),
  KEY ix_radar_board_results_requested (requested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


@dataclasses.dataclass
class Result:
    key_hash: str
    state: str
    payload: bytes
    as_of: dt.datetime
    built_at: dt.datetime
    age_seconds: float
    payload_version: int
    build_ms: int = None
    payload_bytes: int = None
    request_count: int = 0
    warm: bool = False
    attempts: int = 0
    last_error: str = None


@dataclasses.dataclass
class Claim:
    key_hash: str
    key_json: str
    fence: int
    owner: str


# ---- lifecycle -------------------------------------------------------------

def create_table(engine):
    with engine.begin() as conn:
        conn.execute(sa.text(DDL))


def drop_table(engine):
    with engine.begin() as conn:
        conn.execute(sa.text('DROP TABLE IF EXISTS %s' % TABLE))


def truncate(engine):
    with engine.begin() as conn:
        conn.execute(sa.text('TRUNCATE TABLE %s' % TABLE))


# ---- serialization ---------------------------------------------------------

def compress(payload_json_bytes):
    return zlib.compress(payload_json_bytes, COMPRESS_LEVEL)


def decompress(blob):
    return zlib.decompress(blob)


# ---- the read path (Part I.4) ---------------------------------------------

def read(engine, key_hash, now):
    """The stored row, with its real age. Never builds, never enqueues."""
    with engine.connect() as conn:
        row = conn.execute(sa.text(
            'SELECT key_hash, state, payload, as_of, built_at,'
            ' payload_version, build_ms, payload_bytes, request_count,'
            ' warm, attempts, last_error'
            ' FROM %s WHERE key_hash = :k' % TABLE),
            {'k': key_hash}).mappings().first()
    if row is None:
        return None
    age = None
    if row['as_of'] is not None:
        age = (now - row['as_of']).total_seconds()
    return Result(key_hash=row['key_hash'], state=row['state'],
                  payload=row['payload'], as_of=row['as_of'],
                  built_at=row['built_at'], age_seconds=age,
                  payload_version=row['payload_version'],
                  build_ms=row['build_ms'],
                  payload_bytes=row['payload_bytes'],
                  request_count=row['request_count'],
                  warm=bool(row['warm']), attempts=row['attempts'],
                  last_error=row['last_error'])


def queue_depth(engine, now=None):
    with engine.connect() as conn:
        return conn.execute(sa.text(
            "SELECT COUNT(*) FROM %s WHERE state IN ('pending','building')"
            % TABLE)).scalar()


def enqueue(engine, key_hash, key_json, now, warm=False):
    """Ask for a key to be built. Returns the resulting state.

    One short statement. Two web workers racing here produce ONE row and ONE
    queued job because the primary key says so -- the cross-process
    deduplication the in-process single-flight could not do.

    `busy` is returned truthfully when the queue is at `MAX_PENDING`: a cold
    key arriving past the cap is answered rather than lengthening a queue
    nobody will reach in time.
    """
    with engine.begin() as conn:
        existing = conn.execute(sa.text(
            'SELECT state FROM %s WHERE key_hash = :k' % TABLE),
            {'k': key_hash}).scalar()
        if existing is None:
            depth = conn.execute(sa.text(
                "SELECT COUNT(*) FROM %s WHERE state IN ('pending','building')"
                % TABLE)).scalar()
            if depth >= MAX_PENDING and not warm:
                return 'busy'
        # ON DUPLICATE KEY UPDATE, so two racing workers leave one row.
        #
        # STATE IS QUEUE STATE; THE PAYLOAD IS THE RESULT. They are orthogonal
        # columns of one row, which is a clarification of Part I.4 -- that
        # section's prose reads as though `state='ready'` were the condition
        # for serving, but a stale key has to become claimable again while it
        # is still being served. So enqueueing moves the queue state back to
        # `pending` WITHOUT clearing `payload`, and the read path decides from
        # the payload and its age, not from the state. A `building` key is
        # left alone: a reader must not interrupt a build in flight.
        #
        # `attempts` is reset because a reader asking again is fresh demand,
        # which is what un-parks a key that hit MAX_ATTEMPTS (Part I.3).
        conn.execute(sa.text("""
            INSERT INTO %s
              (key_hash, key_json, payload_version, state, warm,
               requested_at, request_count, attempts)
            VALUES (:k, :j, :v, 'pending', :w, :now, 1, 0)
            ON DUPLICATE KEY UPDATE
              requested_at = :now,
              request_count = request_count + 1,
              warm = GREATEST(warm, :w),
              attempts = 0,
              next_attempt_at = NULL,
              state = CASE WHEN state = 'building' THEN 'building'
                           ELSE 'pending' END
        """ % TABLE), {'k': key_hash, 'j': key_json, 'v': PAYLOAD_VERSION,
                       'w': 1 if warm else 0, 'now': now})
        state = conn.execute(sa.text(
            'SELECT state FROM %s WHERE key_hash = :k' % TABLE),
            {'k': key_hash}).scalar()
    if not warm:
        evict(engine, now)
    return state


def evict(engine, now):
    """Bound the on-demand key count. Warm keys are never evicted."""
    with engine.begin() as conn:
        extra = conn.execute(sa.text(
            'SELECT COUNT(*) FROM %s WHERE warm = 0' % TABLE)).scalar()
        if extra <= MAX_ON_DEMAND_KEYS:
            return 0
        doomed = conn.execute(sa.text(
            'SELECT key_hash FROM %s WHERE warm = 0'
            " AND state <> 'building'"
            ' ORDER BY requested_at ASC LIMIT :n' % TABLE),
            {'n': extra - MAX_ON_DEMAND_KEYS}).scalars().all()
        if not doomed:
            return 0
        conn.execute(sa.text(
            'DELETE FROM %s WHERE key_hash IN :ks' % TABLE).bindparams(
                sa.bindparam('ks', value=doomed, expanding=True)))
        return len(doomed)


# ---- the producer (Part I.3) ----------------------------------------------

def claim(engine, owner, now, key_hash=None):
    """Take a fenced lease on one claimable key, or None.

    Claimable: pending or failed and past its backoff, or building with an
    expired lease. The fence is read back INSIDE the claiming transaction, so
    it is our own increment and not a later producer's.
    """
    where = ("( (state IN ('pending','failed')"
             "   AND (next_attempt_at IS NULL OR next_attempt_at <= :now))"
             "  OR (state = 'building' AND lease_expires_at < :now) )")
    with engine.connect() as conn:
        params = {'now': now}
        sql = ('SELECT key_hash FROM %s WHERE %s' % (TABLE, where))
        if key_hash is not None:
            sql += ' AND key_hash = :k'
            params['k'] = key_hash
        # Warm keys first, then oldest request. A warm sweep must not be
        # starved by a burst of on-demand selections.
        sql += ' ORDER BY warm DESC, requested_at ASC LIMIT 8'
        candidates = conn.execute(sa.text(sql), params).scalars().all()

    for candidate in candidates:
        with engine.begin() as conn:
            result = conn.execute(sa.text("""
                UPDATE %s
                   SET state = 'building', lease_owner = :me,
                       lease_expires_at = :expires, fence = fence + 1,
                       attempts = attempts + 1
                 WHERE key_hash = :k AND %s
            """ % (TABLE, where)),
                {'me': owner, 'k': candidate, 'now': now,
                 'expires': now + dt.timedelta(seconds=LEASE_SECONDS)})
            if result.rowcount != 1:
                continue
            row = conn.execute(sa.text(
                'SELECT key_json, fence FROM %s WHERE key_hash = :k' % TABLE),
                {'k': candidate}).mappings().first()
        # COMMITTED before the build starts. Nothing holds a transaction
        # across `board.build`, which takes seconds.
        return Claim(key_hash=candidate, key_json=row['key_json'],
                     fence=row['fence'], owner=owner)
    return None


def publish(engine, claim_, blob, as_of, built_at, build_ms,
            producer_revision=None):
    """Atomically publish. False means we were overtaken; DISCARD the result.

    rowcount 0 here is not an error -- it means someone re-claimed the key
    while we were building, so their result is newer than ours.
    """
    with engine.begin() as conn:
        result = conn.execute(sa.text("""
            UPDATE %s
               SET state = 'ready', payload = :blob, payload_bytes = :n,
                   as_of = :as_of, built_at = :built, build_ms = :ms,
                   payload_version = :v, producer_revision = :rev,
                   lease_owner = NULL, lease_expires_at = NULL,
                   attempts = 0, last_error = NULL, next_attempt_at = NULL
             WHERE key_hash = :k AND fence = :fence
        """ % TABLE).bindparams(sa.bindparam('blob', type_=sa.LargeBinary)),
            {'blob': blob, 'n': len(blob), 'as_of': as_of, 'built': built_at,
             'ms': build_ms, 'v': PAYLOAD_VERSION, 'rev': producer_revision,
             'k': claim_.key_hash, 'fence': claim_.fence})
        return result.rowcount == 1


def backoff(attempts):
    return min(30 * 2 ** (max(attempts, 1) - 1), 900)


def fail(engine, claim_, message, now):
    """Record a failed build. Also fenced: an overtaken builder cannot mark a
    key failed after someone else published it.

    `payload` is deliberately untouched. The last good result keeps being
    served -- marked stale, with its real age -- while the key sits in
    `failed` with a growing backoff. At MAX_ATTEMPTS the backoff stops
    (`next_attempt_at` NULL) so the key is no longer retried until a reader
    asks again, which resets `attempts` in `enqueue`.
    """
    with engine.begin() as conn:
        attempts = conn.execute(sa.text(
            'SELECT attempts FROM %s WHERE key_hash = :k' % TABLE),
            {'k': claim_.key_hash}).scalar() or 1
        nxt = (None if attempts >= MAX_ATTEMPTS
               else now + dt.timedelta(seconds=backoff(attempts)))
        result = conn.execute(sa.text("""
            UPDATE %s
               SET state = 'failed',
                   last_error = :msg, next_attempt_at = :nxt,
                   lease_owner = NULL, lease_expires_at = NULL
             WHERE key_hash = :k AND fence = :fence
        """ % TABLE), {'msg': message[:255], 'nxt': nxt,
                       'k': claim_.key_hash, 'fence': claim_.fence})
        return result.rowcount == 1


def release_expired(engine, now):
    """Rows whose lease has expired are claimable again; this only reports
    them, because `claim` already re-claims them under a new fence."""
    with engine.connect() as conn:
        return conn.execute(sa.text(
            "SELECT key_hash FROM %s WHERE state = 'building'"
            ' AND lease_expires_at < :now' % TABLE),
            {'now': now}).scalars().all()
