"""The read path: a board somebody else built, and an honest answer when
there is not one yet.

A web worker only ever READS. There is no fallback branch that builds -- not
on a miss, not on a board that has gone stale, not when the queue is full and
not on a key whose builds keep failing. That is the whole property the shared
result exists for, and it is a property of this file: the moment one branch
here calls `board.build`, every worker is back to spending six hundred
milliseconds of its own on a board the producer already has.

*Disposition is read off the payload, never off the queue state.* A key that
is queued for refresh (`pending`), being rebuilt (`building`) or backing off
after a failure (`failed`) keeps serving the board it last published, with its
true age. The two questions -- "is there a board" and "is anyone working on
one" -- are independent, and answering the first from the second is how a
`failed` key ends up showing nothing to a viewer who could have been shown a
board thirty seconds old.

*The envelope is the same on both paths.* Every response, from here or from
the legacy synchronous path, carries the same fields describing how it was
delivered: whether it is shared, pending, busy, stale or failing, when it was
built, how old it is, and when to ask again. The client renders one shape. The
fields are named once, in `ENVELOPE_KEYS`, because two modules write them and
a third subtracts them.

*A pending answer is not a board.* Its `rows` are null rather than empty --
empty means "nothing was loud enough", which is a real and different thing to
say -- and it carries no `spend`, `sentiment_ops` or `market_data_ops` at all,
because those are frozen INTO a payload at build time and a shell was never
built. What it does carry is the selection echoed back, computed from the
parsed query, so the surface can draw its chips and its clock while it waits
instead of blanking the controls the reader just used.

*The per-account half is added on top, and timed apart.* A stored board is
viewer-invariant -- that is what lets one of them answer everybody -- so a
reader's own marks are fetched per request and never compressed into the blob.
The metrics line reports that half separately, because it is the part no cache
can ever remove and the part an operator would otherwise mistake for the read
getting slower.
"""
import datetime as dt
import json
import zlib
from time import perf_counter

import sqlalchemy as sa

from . import board as board_mod
from . import board_keys, board_metrics, board_namespace, board_store
from .config import SOURCES, source_root
from .market_calendars import session_state

# Everything either path adds ON TOP of a serialized board. Named here because
# three places have to agree about it: this module writes it for a stored
# board, `routes.api.build_payload_direct` writes it for a synchronous one, and
# the producer's equivalence test subtracts it before comparing a blob with a
# payload. `generated_at` is deliberately absent -- it is the board's own stamp
# and `serialize` has always written it.
ENVELOPE_KEYS = frozenset({
    'shared', 'pending', 'busy', 'stale', 'failed',
    'as_of', 'built_at', 'age_seconds',
    'fresh_seconds', 'hard_expiry_seconds',
    'retry_after_ms', 'queue_age_seconds', 'ops_collected_at',
})

# How soon a waiting client should ask again. The queue-position curve starts
# at a second and adds half a second per place ahead, so a viewer twelfth in
# line is not making twelve pointless round trips a second at exactly the
# moment the queue is longest. It stops growing at eight places: past that the
# wait is dominated by the queue and a longer poll interval only delays the
# answer once it arrives.
PENDING_BASE_MS = 1000
PENDING_STEP_MS = 500
PENDING_MAX_POSITION = 8

# Busy and parked both mean "not queued behind anything countable": the
# generation is refusing work, or this key is waiting on a clock. Neither has a
# position, and both are asking the client to slow down rather than to queue.
BACKED_OFF_MS = 5000

# `ensure_namespace` is idempotent and cheap, but it is still a write, and a
# read path that made one per request would put a row lock in front of every
# board view. Once per process is enough: what it establishes -- that the
# generation's control row exists and is not aging towards retirement -- does
# not stop being true, and every admission moves `last_seen_at` again anyway.
_ENSURED = {}


def reset_namespace_memo():
    """Forget which namespaces this process has introduced. For tests."""
    _ENSURED.clear()


def _api():
    """`routes.api`, imported at call time.

    That module imports this one to dispatch on the flag, so importing it back
    at load time would close the circle. The same reason `board_producer._api`
    and `board_keys.query_from_json` defer their own import of it.
    """
    from .routes import api
    return api


# --- what a stored row is worth ---------------------------------------------

def disposition(result, now, limits):
    """(kind, age_seconds) for one stored row. Pure; no I/O.

    `kind` is `'missing'`, `'ready'` or `'stale'`. Missing covers four
    different absences that all have the same answer -- no row, no payload, a
    payload this build can no longer decode, and a board so old it misdescribes
    its own rolling window -- because a reader has exactly one thing to do
    about any of them.

    The boundaries are closed at the bottom and open at the top, and they are
    written as `>` for that reason: a board exactly `fresh_seconds` old is
    still fresh, and one exactly `hard_expiry_seconds` old is still worth
    serving under a stale mark.

    The age has a floor of zero, the same one `queue_age` and every duration on
    the metrics line have. A board stamped later than this reader's clock is
    two hosts disagreeing about the time, not a board that has not happened
    yet, and a negative age would reach the head of the page as "-0.4s ago"
    and a dashboard as a number it parses as positive.
    """
    if (result is None or result.payload is None or result.as_of is None
            or result.payload_version != board_namespace.PAYLOAD_VERSION):
        return 'missing', None
    age = max(0.0, (now - result.as_of).total_seconds())
    if age > limits.hard_expiry_seconds:
        return 'missing', age
    if age > limits.fresh_seconds:
        return 'stale', age
    return 'ready', age


# --- the read ---------------------------------------------------------------

def read_payload(engine, args, now, user_id, *, poll=False):
    """The store's answer for one request. NEVER builds.

    `now` is naive UTC, the convention every datetime in this codebase carries
    and the one `board.build` is given.

    `poll` is a viewer asking again about a board it is already waiting for. It
    records the demand without counting as a request and without moving the key
    up the queue, and it says so on the metrics line -- the ratio of polls to
    initial reads is how long viewers are actually waiting.
    """
    started = perf_counter()
    api = _api()
    query = api.parse_query(args, now=now)
    key_hash, key_json = board_keys.canonical(query)
    ns = board_namespace.namespace()
    _ensure_namespace_once(engine, ns, now)
    bounds = board_store.limits()

    stored = board_store.read(engine, ns, key_hash)
    kind, age = disposition(stored, now, bounds)
    # Read off the row as it was FOUND. After an admission every key has a row,
    # so asking afterwards would call every first-time reader's board on-demand
    # even when it was one of the eight standing ones.
    cls = 'warm' if stored is not None and stored.warm else 'ondemand'

    if kind == 'missing':
        payload, outcome, queue_age = _wait_for_a_build(
            engine, ns, key_hash, key_json, query, now, bounds, stored=stored,
            poll=poll)
        _log(demand=poll, cls=cls, key=key_hash, outcome=outcome,
             cache_age=None, queue_age=queue_age, started=started,
             account_ms=0)
        return payload

    if kind == 'stale':
        # Asked for, not waited on. Nothing else would ask: the producer sweeps
        # the eight standing boards on its own, and this key need not be one.
        # A `'busy'` answer here is fine -- the board is served either way.
        board_store.admit(engine, ns, key_hash, key_json, now, poll=poll)

    payload = _serve(stored, kind, age, bounds)
    account_started = perf_counter()
    _add_account(payload, query, now, user_id)
    account_ms = _elapsed(account_started)
    _log(demand=poll, cls=cls, key=key_hash, outcome=kind, cache_age=age,
         queue_age=None, started=started, account_ms=account_ms)
    return payload


def _serve(stored, kind, age, bounds):
    """A stored blob, decoded, with the envelope of a real board on it.

    `generated_at` is left exactly as the producer wrote it: it is when the
    board was BUILT, and rewriting it here would make the head's freshness
    stamp a lie for every reader after the first. `as_of` and `built_at` come
    off the row, which is where the producer's two clock readings live.
    """
    payload = json.loads(zlib.decompress(stored.payload))
    payload.update({
        'shared': True,
        'pending': False,
        'busy': False,
        'stale': kind == 'stale',
        # A queue state, not a verdict on this payload. The board below is
        # still a board; what failed is the attempt to build a newer one.
        'failed': stored.queue_state == 'failed',
        'as_of': _iso(stored.as_of),
        'built_at': _iso(stored.built_at),
        'age_seconds': age,
        'fresh_seconds': bounds.fresh_seconds,
        'hard_expiry_seconds': bounds.hard_expiry_seconds,
        # A stale board has a refresh queued, so there is a reason to come
        # back; a fresh one has nothing to wait for and says so with null.
        'retry_after_ms': BACKED_OFF_MS if kind == 'stale' else None,
        'queue_age_seconds': None,
        # The row's own instant, overriding whatever the blob carries. The
        # producer writes the same value into both -- the ops summaries frozen
        # inside a payload are read at the start of the build `as_of` names --
        # and the row is the copy this response's age is already measured
        # against. Deferring to the blob would let a payload from some other
        # build put an age on those figures that the board around them does
        # not have.
        'ops_collected_at': _iso(stored.as_of),
    })
    return payload


def _add_account(payload, query, now, user_id):
    """The caller's own marks, on top of the viewer-invariant board.

    The same function the synchronous path calls rather than a copy of it.
    This is the half of a board response no cache can ever answer, and it is
    the half a reader of a stored board most needs to be identical: two
    implementations would be two chances for one account to see a different
    mark depending on which path happened to serve it.
    """
    payload.update(_api().account_fields(query, now, user_id))


# --- when there is nothing to serve -----------------------------------------

def _wait_for_a_build(engine, ns, key_hash, key_json, query, now, bounds, *,
                      stored, poll):
    """Ask for the board, and describe the wait. Returns (payload, outcome,
    queue_age).

    Three answers, and they are not the same wait. `busy` is the generation
    refusing work -- nothing was written, and the client should slow down
    rather than queue. `parked` is this key backing off after repeated build
    failures, which is a wait on a clock and not on a queue, so it gets the
    same slower rate and says `failed` so the surface can tell the reader why.
    Anything else is an ordinary place in line.

    `stored` is the row as it was FOUND, before the admission below moved it,
    and `failed` on the shell is that row's queue state. It is the answer to
    "why am I being shown nothing", and the honest answer for a key whose
    backoff has just elapsed -- re-queued here, at the ordinary rate -- is
    still that its last build failed. A viewer six attempts into a broken key
    deserves to be told that rather than "loading" for the seventh time.

    It says what the ROW says, and no more than that: once this admission has
    re-queued a failed key it is `pending`, nothing has failed since, and the
    next read reports `failed: false`. The field is the state of the key, not a
    memory of its history -- a memory is what `attempts` and `last_error` are
    for, and they are the operator's to read, not the viewer's.
    """
    failed = stored is not None and stored.queue_state == 'failed'
    state = board_store.admit(engine, ns, key_hash, key_json, now, poll=poll)
    if state == 'busy':
        return (_waiting(query, now, bounds, pending=False, failed=False,
                         retry_after_ms=BACKED_OFF_MS, queue_age=None),
                'busy', None)

    # Read back rather than inferred: `admit` has just written the row and only
    # the row knows when this key ENTERED the queue -- which a poll deliberately
    # does not move, and which is what both the wait and the position rank by.
    queued = board_store.read(engine, ns, key_hash)
    enqueued_at = queued.enqueued_at if queued is not None else None
    queue_age = (None if enqueued_at is None
                 else max(0.0, (now - enqueued_at).total_seconds()))

    if state == 'parked':
        return (_waiting(query, now, bounds, pending=True, failed=True,
                         retry_after_ms=BACKED_OFF_MS, queue_age=queue_age),
                'failed', queue_age)

    position = _queue_position(engine, ns, enqueued_at)
    retry = PENDING_BASE_MS + PENDING_STEP_MS * min(position,
                                                    PENDING_MAX_POSITION)
    return (_waiting(query, now, bounds, pending=True, failed=failed,
                     retry_after_ms=retry, queue_age=queue_age),
            'pending', queue_age)


def _queue_position(engine, ns, enqueued_at):
    """How many keys entered this generation's queue before this one.

    Zero when the row has no `enqueued_at` to compare against, which is a row
    that was evicted between the admission and this read: an unknown position
    is answered as the front of the queue rather than as a long wait, because
    the next poll will find out and a pessimistic guess only makes it later.

    The table name comes from `board_store` rather than being spelled again
    here. This is the one read of these tables that does not live in that
    module -- it is part of describing the WAIT rather than of moving keys
    between states -- and a second literal for the table would be a second
    thing to change when one moved.
    """
    if enqueued_at is None:
        return 0
    with engine.connect() as connection:
        return connection.execute(sa.text(
            f'SELECT COUNT(*) FROM {board_store.RESULTS}'
            " WHERE namespace = :ns AND queue_state = 'pending'"
            ' AND enqueued_at < :enqueued'),
            {'ns': ns, 'enqueued': enqueued_at}).scalar() or 0


def _waiting(query, now, bounds, *, pending, failed, retry_after_ms,
             queue_age):
    """The shell a viewer gets while the board is being built.

    Explicitly not a board. `rows` is null rather than empty because empty is a
    real answer -- nothing was loud enough in this window -- and a client that
    could not tell the two apart would draw "no movement" over a cache miss.
    """
    payload = _selection_echo(query, now)
    payload.update({
        'shared': True,
        'pending': pending,
        'busy': not pending,
        'stale': False,
        'failed': failed,
        # Nothing was built, so there is no instant to name. Null and not the
        # current clock: "calculated just now" about a board that does not
        # exist is the one thing a freshness stamp must never say.
        'generated_at': None,
        'as_of': None,
        'built_at': None,
        'age_seconds': None,
        'fresh_seconds': bounds.fresh_seconds,
        'hard_expiry_seconds': bounds.hard_expiry_seconds,
        'retry_after_ms': retry_after_ms,
        'queue_age_seconds': queue_age,
        'ops_collected_at': None,
        'rows': None,
        'watching': [],
        'watch_rows': [],
    })
    return payload


def _selection_echo(query, now):
    """The part of a board that is the QUESTION rather than the answer.

    Every one of these is derivable from the parsed query and the clock, which
    is why a shell can carry them: the surface draws its chips, its window
    buttons and its market clock from this echo, and blanking them while the
    board is built would take the controls away from the reader at the exact
    moment they are waiting for the result of using them.

    The session and the boundary go through the same two functions
    `board.build` calls, with the same Tradegate-first MIC for Germany, so a
    pending page and the board that replaces it cannot disagree about what time
    it is on the market.
    """
    api = _api()
    mic = 'XGAT' if query.market == 'de' else None
    session = session_state(query.market, now.replace(tzinfo=dt.timezone.utc),
                            mic=mic)
    label, boundary_at = board_mod._next_boundary(query.market, now, session,
                                                  mic=mic)
    return {
        'market': query.market,
        'display_timezone': 'Europe/Berlin',
        'market_venue': ('Tradegate-first Germany' if query.market == 'de'
                         else 'US markets'),
        'session': session,
        'next_boundary_label': label,
        'next_boundary_at': api._iso_z(boundary_at),
        # ROOTED and sorted, exactly as `build_payload` roots them: this list
        # is what lights the chips, and there is one chip per root.
        'sources': sorted({source_root(source) for source in query.sources}),
        'all_sources': list(SOURCES),
        # Verbatim, order and duplicates included -- the key keeps them and the
        # surface reads them back to draw its segment chips.
        'segments': list(query.segments),
        'min_venues': query.min_venues,
        'window_hours': query.window,
        'sort': query.sort,
        'dir': query.direction,
        'triplet_hours': list(board_mod.TRIPLET_HOURS),
        'series_hours': board_mod.SERIES_HOURS,
        'lead_count': board_mod.LEAD_COUNT,
        # Counts label the controls, and there is nothing counted yet. Zeroes
        # where the shape needs numbers, empty where it needs a mapping.
        'segment_counts': {},
        'venue_counts': {'any': 0, 'multi': 0},
        'excluded': {},
    }


# --- the mechanics ----------------------------------------------------------

def _ensure_namespace_once(engine, ns, now):
    """Introduce this generation, at most once per process.

    The revision written here is this process's own, and that is not a guess:
    the namespace IS derived from the revision, so a reader answering inside
    generation N is running exactly the build that produces N. What a reader
    cannot claim is that a producer is alive -- `producer_owner` and
    `producer_seen_at` are only ever written by `heartbeat`, so an operator
    reading the admin surface still sees a generation with no producer.
    """
    if _ENSURED.get(ns):
        return
    board_store.ensure_namespace(
        engine, ns, now, revision=board_namespace.describe()['revision'],
        payload_version=board_namespace.PAYLOAD_VERSION)
    _ENSURED[ns] = True


def _log(*, demand, cls, key, outcome, cache_age, queue_age, started,
         account_ms):
    """One line per read, with nobody's name in it.

    `outcome=failed` is a reader that got NOTHING because this key's builds are
    failing. A board served from a key that is failing is still `ready` or
    `stale` -- the viewer got a board -- and that the key is broken is
    `log_build`'s line to write, once per attempt, rather than this one's to
    repeat on every poll.
    """
    board_metrics.log_read(
        demand='poll' if demand else 'initial', cls=cls, key=key,
        outcome=outcome, cache_age=cache_age, queue_age=queue_age,
        read_ms=_elapsed(started), account_ms=account_ms)


def _elapsed(started):
    """Milliseconds since a `perf_counter` reading, as a whole number."""
    return int(round((perf_counter() - started) * 1000))


def _iso(value):
    """A stored instant on the wire, with its UTC made explicit."""
    return _api()._iso_z(value)
