"""The one process that builds boards.

Every web worker reads; this builds. That is the whole of the design, and
everything below is a consequence of it.

*What it keeps warm is derived, not typed.* The eight standing boards are
whatever `parse_query` makes of the two markets, the two segment selections a
bare URL can carry, and the two windows the surface offers. Writing `limit=50`
here would be a second place for the default limit to live, and the day the
parser's default moved, the eight warm boards would quietly stop being the
boards anybody actually asks for.

*A board is stamped with when it was READ, not when it was written down.*
`as_of` is the clock immediately before `board.build`; `built_at` is the clock
after the payload is serialized. Between them sit seconds of SQL, and a
viewer told "calculated just now" about a board whose numbers are eight
seconds old has been told something false. Elapsed time is `perf_counter`,
which is a different question from either -- the wall clock can step sideways
under NTP and a build that took -3 ms is a metric nobody can act on.

*Fairness is between two classes, and it alternates.* Warm work and on-demand
work are separate queues and `claim` takes one class per call, deliberately.
The producer alternates -- but only spends its turn when the preferred class
actually had something. A tick that found no warm work and served a viewer
instead leaves the preference where it was, so the warm sweep is tried first
again next time rather than losing its place to a moment's bad timing.

*Nothing is held while it waits.* The claim commits before the build begins;
the build's own read transaction is closed before the publish opens its own;
and an idle loop sleeps on the stop event, outside every transaction, holding
no connection. A producer that polls every half second while holding an ORM
session would keep one connection and one read view out of circulation for the
whole life of the process.

*A build that fails leaves the last board standing.* The row goes to `failed`
with the exception's TYPE (never its message -- that is where a ticker, a
query or an account id would arrive in a column), backs off, and goes on
serving the board it published last time. Six failures park it for fifteen
minutes, which is a rate rather than a stop. What fails AFTER a successful
build -- the publish, the log line, the heartbeat -- is the database's failure
and not the key's, so it is logged and nothing is written down against the
key; the lease expires on its own and the key comes back.

*A database that is down is one incident, not two a second.* The loop does not
exit when a tick raises, but it does back off: consecutive failures double the
wait from twice the poll interval up to thirty seconds, and a tick that
completes puts the count back to zero. The first failure of a run carries the
traceback and every one after it is a single line saying how many there have
been and when the next attempt is -- because at the idle rate a minute of
outage is a hundred and twenty tracebacks, and the hundred and twentieth says
nothing the first did not.
"""
import datetime as dt
import json
import logging
import os
import socket
import time
import zlib
from time import perf_counter

from extensions import db

from . import board as board_mod
from . import board_keys, board_metrics, board_namespace, board_store
from .config import DEFAULT_SEGMENT, source_root

logger = logging.getLogger('radar.board')

# The standing selections, as arguments to the parser rather than as a Query.
# `''` is how a URL asks for All; DEFAULT_SEGMENT is what a bare URL asks for.
WARM_MARKETS = ('us', 'de')
WARM_SEGMENTS = ('', DEFAULT_SEGMENT)
WARM_WINDOWS = (12, 24)

# zlib level 6 is its own default: the board payload compresses ~10x at 6 and
# ~10.5x at 9 for three times the CPU, and this runs once per key per two
# minutes on a machine that also serves the site.
COMPRESSION = 6

# How long an idle loop waits before asking for work again.
DEFAULT_POLL_INTERVAL = 0.5

# The longest a failing loop waits between attempts. Consecutive failures
# double the wait from twice the poll interval up to this; without a cap the
# doubling reaches an hour inside a dozen failures, and a producer that has
# stopped asking is indistinguishable from one that has died. Thirty seconds
# is a rate a recovering database can carry and a delay an operator will sit
# through.
MAX_BACKOFF_SECONDS = 30.0

# How often the loop evicts, retires and reports. Not per tick: at a half
# second that would be four housekeeping transactions a second against the
# control row every web worker admits under.
HOUSEKEEPING_SECONDS = 60

# `last_error` says a key's build did not round-trip. Not an exception type,
# because nothing raised -- the stored key simply no longer means what its
# hash says, and building it would publish one viewer's board under another
# viewer's key.
KEY_MISMATCH = 'KeyMismatch'

_OTHER = {'warm': 'demand', 'demand': 'warm'}

# `lease_owner` and `producer_owner` are VARCHAR(64).
_OWNER_WIDTH = 64


def utcnow():
    """Naive UTC, the convention every datetime in this codebase is stored in.

    `datetime.utcnow()` is deprecated and slated for removal, and it printed a
    warning into the service log on every cycle.
    """
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def default_owner():
    """Who this producer is, for the lease and the health row.

    Host and pid, which is what distinguishes two producers during a deploy's
    overlap. Not a name anybody chose: an owner is a fence, and a fence that
    two processes could both spell the same way is not one.
    """
    return f'{socket.gethostname()}:{os.getpid()}'[:_OWNER_WIDTH]


def _api():
    """`routes.api`, imported at call time.

    Importing it binds the whole radar blueprint -- `features.radar.routes`
    registers every route module on the way in -- which a process whose job is
    to build boards has no business doing at import time. Deferred for the
    same reason `board_keys.query_from_json` imports `Query` at call time.
    """
    from .routes import api
    return api


# --- what is kept warm ------------------------------------------------------

def warm_queries(now):
    """The eight boards this producer keeps warm whether or not anyone looks.

    Built by putting arguments through the same parser a request goes through,
    so limit, venues, sources, sort and direction are the parser's defaults and
    not a copy of them. Two markets, All versus the default segments, twelve
    hours versus twenty-four: sixteen selections would be the full cross with
    the other two windows, and measurement said the short windows are asked for
    rarely enough to be on-demand work.
    """
    parse_query = _api().parse_query
    return [parse_query({'market': market, 'segment': segment,
                         'window': str(window)}, now=now)
            for market in WARM_MARKETS
            for segment in WARM_SEGMENTS
            for window in WARM_WINDOWS]


def warm_keys(now):
    """The warm selections as the (key_hash, key_json) pairs the store wants."""
    return [board_keys.canonical(query) for query in warm_queries(now)]


# --- one board --------------------------------------------------------------

def build_blob(query, *, now):
    """Build one board and return it compressed, with its three stamps.

    `now` is the CLOCK, not an instant: this reads it twice, once before the
    build and once after the payload is written out, and the gap between them
    is the honest answer to "how old is this board" for as long as it is
    stored. A caller that passed a single instant could not produce that gap.

    The sources are rooted exactly as `build_payload` roots them, because the
    payload's `sources` is what lights the chips on the surface and there is
    one chip per root. `ops_collected_at` is added because the three ops
    summaries inside `serialize` are read at build time and then frozen into a
    payload that may be served for ten minutes; without it the surface would
    present a spend figure with no way to say how old it is.

    Returns (blob, as_of, built_at, build_ms, payload_bytes). `payload_bytes`
    is the STORED size -- the same number the row's column of that name holds
    and the same one the metrics line reports, so the three cannot drift into
    meaning different things.
    """
    api = _api()
    as_of = now()
    started = perf_counter()
    board = board_mod.build(query.sources, as_of, window_hours=query.window,
                            segments=query.segments, limit=query.limit,
                            min_venues=query.min_venues, market=query.market,
                            sort=query.sort, direction=query.direction)
    board.sources = sorted({source_root(source) for source in query.sources})
    payload = api.serialize(board)
    payload['ops_collected_at'] = as_of.isoformat() + 'Z'
    # `default=str` is the backstop for a Decimal that escaped `_decimal_or_none`
    # rather than a licence to store objects: sort_keys is what matters, because
    # a payload whose key order moved would be a different blob for the same board.
    text = json.dumps(payload, sort_keys=True, default=str)
    built_at = now()
    blob = zlib.compress(text.encode('utf-8'), COMPRESSION)
    return blob, as_of, built_at, _elapsed(started), len(blob)


def serve_once(engine, ns, owner, now_fn, *, prefer, revision=None):
    """Claim one key of the named class, build it, publish it. Returns the key.

    None means that class had nothing claimable -- which is information the
    caller needs, and is why `claim` refuses to quietly hand back the other
    class instead.

    The key's stored json is re-canonicalised before anything is written under
    its hash. A row whose two halves disagree would serve one viewer another
    viewer's board, so it is failed and never built; `python -O` strips
    `assert`, which is why this is an `if`.

    Every exit removes the ORM session. The build's own read transaction is
    closed before `publish` opens one of its own, so a build and a write never
    hold two connections at once, and a failure never leaves a transaction
    open across the backoff.

    Three separate spans of risk, each with its own answer, because they are
    not the same event:

    * the round-trip guard, whose failure is not an exception at all,
    * the build, whose failure is the key's own and is recorded on the key,
    * everything after the build, whose failure is the DATABASE's and must not
      be written down as this key having failed to build.
    """
    revision = revision or board_namespace.describe()['revision']
    # The same truncation `Loop.__init__` applies. `lease_owner` is
    # VARCHAR(64) and the fence compares the stored value to this one, so an
    # owner the column silently shortened would fence itself out of its own
    # publish -- and this function is callable without a `Loop`.
    owner = owner[:_OWNER_WIDTH]
    claimed_at = now_fn()
    claim = board_store.claim(engine, ns, owner, claimed_at, prefer=prefer)
    if claim is None:
        return None

    cls = 'warm' if claim.warm else 'ondemand'
    queue_wait = (None if claim.enqueued_at is None else
                  max(0.0, (claimed_at - claim.enqueued_at).total_seconds()))
    started = perf_counter()
    try:
        # Outside every `except` below, so the guard's failure is recorded
        # exactly once. Inside one, a `_record_failure` that itself raised
        # would be caught and recorded a SECOND time under a different error
        # name, and the row would end up saying the key failed for whatever
        # went wrong while writing down that it failed.
        if not board_keys.round_trips(claim.key_hash, claim.key_json):
            logger.error('board key does not reproduce its own hash key=%s',
                         claim.key_hash[:board_metrics.KEY_WIDTH])
            _record_failure(engine, ns, claim, owner, KEY_MISMATCH, now_fn,
                            cls=cls, queue_wait=queue_wait,
                            build_ms=_elapsed(started))
            return claim.key_hash

        try:
            query = board_keys.query_from_json(claim.key_json)
            blob, as_of, built_at, build_ms, payload_bytes = build_blob(
                query, now=now_fn)
        except Exception as exc:
            # Broad on purpose, and narrow in SCOPE. One key's data being
            # wrong is not a reason for the other seven to stop being built,
            # and the traceback goes to the log while only the exception's
            # type goes into the row.
            logger.exception('board build failed key=%s class=%s',
                             claim.key_hash[:board_metrics.KEY_WIDTH], cls)
            _record_failure(engine, ns, claim, owner, type(exc).__name__,
                            now_fn, cls=cls, queue_wait=queue_wait,
                            build_ms=_elapsed(started))
            return claim.key_hash
        finally:
            db.session.remove()

        try:
            published = board_store.publish(
                engine, ns, claim, blob, as_of=as_of, built_at=built_at,
                build_ms=build_ms, producer_revision=revision)
            board_metrics.log_build(
                key=claim.key_hash, cls=cls, queue_wait=queue_wait,
                build_ms=build_ms, payload_bytes=payload_bytes,
                result='published' if published else 'overtaken')
            if published:
                stamped = now_fn()
                board_store.heartbeat(engine, ns, owner, stamped,
                                      success_at=stamped)
        except Exception:
            # The board was BUILT. Whatever failed here -- the publish, the
            # log line, the success heartbeat -- is not the key's fault, and
            # calling `fail` would count an attempt against a key that built
            # perfectly well and back it off for thirty seconds because the
            # database blinked. The lease is what protects the row: it expires
            # on its own and the key becomes claimable again, which is the
            # same recovery an interrupted producer gets.
            logger.exception('board publish failed key=%s class=%s',
                             claim.key_hash[:board_metrics.KEY_WIDTH], cls)
    finally:
        db.session.remove()
    return claim.key_hash


def _record_failure(engine, ns, claim, owner, error, now_fn, *, cls,
                    queue_wait, build_ms):
    """Back the key off, say so on the health row, and count the attempt.

    `fail` is fenced on the same four columns as `publish`, so a builder that
    lost its lease can no more park a key than it can publish to it -- this may
    write nothing at all, and that is correct.
    """
    now = now_fn()
    board_store.fail(engine, ns, claim, error, now)
    board_store.heartbeat(engine, ns, owner, now, error=error)
    board_metrics.log_build(key=claim.key_hash, cls=cls, queue_wait=queue_wait,
                            build_ms=build_ms, payload_bytes=0, result='failed')


def _elapsed(started):
    """Milliseconds since a `perf_counter` reading, as a whole number."""
    return int(round((perf_counter() - started) * 1000))


def _monotonic():
    """`time.perf_counter`, for measuring an INTERVAL rather than a duration.

    Named apart from the `perf_counter` `_elapsed` reads so that a test which
    pins one of the two does not silently move the other: a build's duration
    and the housekeeping interval are unrelated questions that happen to want
    the same clock.
    """
    return time.perf_counter()


# --- readiness --------------------------------------------------------------

def readiness(engine, ns, now):
    """Whether every standing board is built and fresh, and which are not.

    The prewarm gate: a deploy turns the shared path on only once this says
    ready, because the alternative is every viewer meeting `pending` at once.

    It counts the keys this build DERIVES, not the warm rows the table happens
    to hold, and compares that count against `warm_limit` -- which is the only
    reason that limit exists. A ninth standing selection added without moving
    it would otherwise report a warm cache one board short of what the
    producer now builds, and report it as ready.
    """
    bounds = board_store.limits()
    pairs = warm_keys(now)
    missing = []
    for key_hash, _ in pairs:
        stored = board_store.read(engine, ns, key_hash)
        if (stored is None or stored.payload is None or stored.as_of is None
                or (now - stored.as_of).total_seconds() > bounds.fresh_seconds):
            # The same twelve characters the log lines carry, so a missing key
            # here and a build line there are one grep apart.
            missing.append(key_hash[:board_metrics.KEY_WIDTH])
    return {
        'ready': not missing and len(pairs) == bounds.warm_limit,
        'namespace': ns,
        'warm_total': len(pairs),
        'warm_ready': len(pairs) - len(missing),
        'warm_limit': bounds.warm_limit,
        'fresh_seconds': bounds.fresh_seconds,
        'missing': missing,
    }


# --- the loop ---------------------------------------------------------------

# The most times the backoff doubles. The cap on the WAIT is not where this
# arithmetic happens: `poll_interval * 2 ** failures` is evaluated before `min`
# can see it, and `2 ** 1024` is past the largest float there is, so the
# thousand and twenty-fourth consecutive failure raises OverflowError -- inside
# the except handler whose entire job is to keep this loop alive. At a half
# second between attempts that is under nine hours of a database being down: a
# long outage over an unattended weekend, which is precisely what the backoff
# was written for. Sixteen doublings pass `MAX_BACKOFF_SECONDS` from any
# interval an operator would set, so nothing below the cap changes.
BACKOFF_MAX_DOUBLINGS = 16


def _backoff(poll_interval, failures):
    """How long to wait after `failures` consecutive failed ticks."""
    return min(poll_interval * 2 ** min(failures, BACKOFF_MAX_DOUBLINGS),
               MAX_BACKOFF_SECONDS)

class Loop:
    """The producer's tick, its fairness, and its shutdown.

    Holds no connection and no session between ticks. The only state it
    carries is which class it owes a turn to and when it last did the
    housekeeping -- everything else about what to build next is in the table,
    where a second producer during a deploy's overlap can see it too.
    """

    def __init__(self, engine, *, ns=None, owner=None, revision=None,
                 now_fn=utcnow, poll_interval=DEFAULT_POLL_INTERVAL):
        self.engine = engine
        self.ns = ns or board_namespace.namespace()
        self.owner = (owner or default_owner())[:_OWNER_WIDTH]
        self.revision = revision or board_namespace.describe()['revision']
        self.now_fn = now_fn
        self.poll_interval = poll_interval
        # Warm first on a cold start: the eight standing boards are what a
        # viewer arriving at a bare URL is about to ask for.
        self.next_class = 'warm'
        self._housekept_at = None

    def tick(self, now=None):
        """One pass: say we are here, sweep the warm set, serve one key.

        Returns the key served, or None when neither class had work. The
        caller decides what to do with None -- `run` waits, `--once` exits --
        because the wait must happen outside this method, with nothing open.
        """
        now = self.now_fn() if now is None else now
        board_store.ensure_namespace(
            self.engine, self.ns, now, revision=self.revision,
            payload_version=board_namespace.PAYLOAD_VERSION)
        board_store.heartbeat(self.engine, self.ns, self.owner, now)
        board_store.refresh_warm(self.engine, self.ns, warm_keys(now), now)

        preferred = self.next_class
        served = serve_once(self.engine, self.ns, self.owner, self.now_fn,
                            prefer=preferred, revision=self.revision)
        if served is not None:
            self.next_class = _OTHER[preferred]
        else:
            # The preference is deliberately NOT rotated here. This tick did
            # not spend its turn on the preferred class, it found nothing
            # there; rotating would let a class that was a moment early lose
            # its place every time that happened.
            served = serve_once(self.engine, self.ns, self.owner, self.now_fn,
                                prefer=_OTHER[preferred],
                                revision=self.revision)

        self._housekeeping(now)
        # Before the caller's wait, whatever happened above.
        db.session.remove()
        return served

    def readiness(self, now=None):
        """This loop's own namespace, asked the readiness question."""
        return readiness(self.engine, self.ns,
                         self.now_fn() if now is None else now)

    def run(self, stop_event):
        """Serve keys until asked to stop, finishing the build in flight.

        The idle wait is `stop_event.wait`, not `sleep`: a SIGTERM must not
        have to wait out a poll interval, and the wait happens after `tick`
        has removed the session, so nothing is held across it.

        A tick that raises is logged and retried. A database that blinked is
        not a reason for the only process that builds boards to exit.

        But consecutive failures BACK OFF, doubling from twice the poll
        interval up to `MAX_BACKOFF_SECONDS`, and one tick that completes puts
        the count back to zero. Retrying a down database twice a second is
        both the least kind thing to do to a server that is trying to come
        back and the noisiest way to report one problem: at the idle rate, an
        outage of a minute is a hundred and twenty tracebacks in the service
        log, and the hundred and twentieth says nothing the first did not. So
        the first failure carries the traceback and every failure after it is
        one line saying how many there have been and when the next attempt is.
        """
        logger.info('board producer running owner=%s poll_interval=%.2fs',
                    self.owner, self.poll_interval)
        failures = 0
        while not stop_event.is_set():
            try:
                served = self.tick()
            except Exception:
                failures += 1
                wait = _backoff(self.poll_interval, failures)
                message = ('board producer tick failed failures=%d '
                           'next_wait=%.1fs')
                if failures == 1:
                    logger.exception(message, failures, wait)
                else:
                    logger.info(message, failures, wait)
                # The tick's own `remove()` may be what did not happen.
                db.session.remove()
                stop_event.wait(wait)
                continue
            failures = 0
            if served is None:
                stop_event.wait(self.poll_interval)
        logger.info('board producer stopped owner=%s', self.owner)

    def _housekeeping(self, now):
        """Eviction, retirement and one line about the queue, once a minute.

        The MINUTE is monotonic; `now` is the wall clock and is only what the
        three calls below are asked about. A wall clock that stepped forward
        under NTP would otherwise run the housekeeping early, and one that
        stepped back would suspend it for as long as the step -- on a producer
        whose whole job is to keep running unattended.
        """
        elapsed = _monotonic()
        if (self._housekept_at is not None and
                elapsed - self._housekept_at < HOUSEKEEPING_SECONDS):
            return
        self._housekept_at = elapsed
        evicted = board_store.evict(self.engine, self.ns, now)
        retired = board_store.retire_namespaces(self.engine, self.ns, now)
        queue = board_store.queue_summary(self.engine, self.ns, now)
        logger.info(
            'board queue pending=%d building=%d failed_due=%d on_demand=%d '
            'warm_ready=%d evicted=%d retired=%d',
            queue['pending'], queue['building'], queue['failed_due'],
            queue['on_demand_rows'], queue['warm_ready'], evicted, retired)
