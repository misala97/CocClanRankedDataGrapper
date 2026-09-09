"""Recording what the ingest daemon actually did.

Two rules shape this module.

The first is that instrumentation may never become a reason a cycle fails.
Every write here is wrapped, logs a stable message and returns; `start_run`
mints its id before it touches the database, so ingest has something to report
against even when nothing can be stored.

The second is that the recorder owns its transaction. It opens a session bound
to `db.engine` rather than joining `db.session`. On the success path the cycle
has already committed by the time the run is closed, so the danger is on the
FAILURE path: `finish_run` runs there while `db.session` may still hold a
half-written roll-up that nobody rolled back. Committing that pending work as a
side effect of writing a marker row would be a data-corruption bug wearing an
instrumentation costume, and joining the caller's session would also make a
recorder rollback discard whatever the caller had staged.

What is recorded is deliberately narrow. A completed run carries the summary
`ingest.run_cycle` returned, exactly, inside an envelope naming its schema
version. A failed run carries a code and no counters -- the zeros in tick's
error return exist to keep the caller's shape stable and would read, if
stored, as a cycle that measured nothing happening. A process that dies leaves
its `running` row behind; that is incomplete, and readers must say so.
"""
import datetime as dt
import logging
import uuid
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.orm import Session

from extensions import db
from models import RadarIngestRun

logger = logging.getLogger(__name__)

# The vocabulary `summary_json` is written in. Bump it when a counter changes
# meaning, never when one is added.
SCHEMA_VERSION = 1

TERMINAL = {'ok', 'error'}

# The reader's own timezone. A "day" on the activity page is a day the reader
# lived through, not a 24-hour slice of UTC.
BERLIN = ZoneInfo('Europe/Berlin')

ALLOWED_DAYS = (1, 7, 30)

COUNTERS = ('posts_seen', 'posts_new', 'mentions', 'buckets_written')

# The accepted domain of a stored counter: a non-negative integer that fits a
# signed BIGINT. Anything else is not coerced, clamped or turned into a zero --
# it is refused, and the refusal is visible as a null.
COUNTER_MAX = 2 ** 63 - 1

# How many rows the read holds at once. Bounded on purpose: the cost this
# module was rewritten to remove was holding a month of them.
READ_BATCH = 1000


def project(envelope) -> tuple[int | None, bool, dict[str, int | None]]:
    """The typed view of one `summary_json`, as (version, countable, counters).

    This is the ONLY definition of the projection. `finish_run` writes it, the
    migration's backfill re-implements it against a frozen copy, and the tests
    compare both against the envelope reducer they replace. A second definition
    anywhere would be a second answer to the same question.

    `countable` means the envelope is structurally what this module writes: a
    mapping, declaring an integer schema version, carrying a mapping summary.
    It deliberately does NOT mean the version is one any reader understands --
    only a reader can decide that, against its own SCHEMA_VERSION, and a marker
    that folded the two together would have to be rewritten every time the
    version moved.

    A counter missing from an otherwise valid summary is null and leaves the
    row countable. That is the distinction the marker exists for: null alone
    cannot separate "this run stored nothing countable" from "this run's
    summary omitted this counter", and those two have opposite consequences --
    the first is skipped, the second nulls the day.

    THREE DELIBERATE DIVERGENCES from the envelope reducer this replaced. It
    compared `schema_version == SCHEMA_VERSION` and summed whatever the summary
    held, so in Python it accepted `True` and `1.0` as version 1 and would have
    added a negative or a bool to a total. This is stricter on purpose, and
    each case is pinned by a test that asserts the DIFFERENCE rather than
    parity:

      * `schema_version` of `1.0` or `True` is not countable. An Integer column
        recording `1` for either would claim the envelope declared something it
        did not, and a projection that misreports its own provenance is worse
        than one that declines to answer.
      * A counter outside the accepted domain is null rather than summed;
        see `_counter`.
      * A counter stored as a string nulls that counter instead of raising
        TypeError out of the endpoint, which is what the old reducer did.

    Parity is exact everywhere else, which is every shape production writes.
    """
    empty = {name: None for name in COUNTERS}
    if not isinstance(envelope, dict):
        return None, False, dict(empty)
    version = envelope.get('schema_version')
    # `isinstance(True, int)` is True in Python, and 1.0 == 1 -- both would
    # have passed the old equality check. Neither is an integer version.
    if isinstance(version, bool) or not isinstance(version, int):
        return None, False, dict(empty)
    summary = envelope.get('summary')
    if not isinstance(summary, dict):
        return version, False, dict(empty)
    return version, True, {name: _counter(summary.get(name))
                           for name in COUNTERS}


def _counter(value) -> int | None:
    """One counter, or null when it is not one.

    Null covers absent, explicitly null, and out of domain. Out of domain is
    logged rather than silently dropped, because a counter arriving as a string
    or a negative means the writer changed and this projection is the place
    that noticed.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        logger.warning('radar run counter is %s, not an integer; recorded as '
                       'absent', type(value).__name__)
        return None
    if not 0 <= value <= COUNTER_MAX:
        logger.warning('radar run counter %d is outside the accepted domain; '
                       'recorded as absent', value)
        return None
    return value


def _session():
    """A transaction of the recorder's own, bound to the shared engine."""
    return Session(bind=db.engine)


def start_run(now: dt.datetime) -> str:
    """Mark a cycle as started. Returns its id whether or not it stored."""
    run_id = str(uuid.uuid4())
    try:
        with _session() as session, session.begin():
            session.add(RadarIngestRun(id=run_id, started_at=now,
                                       status='running'))
    except Exception:
        logger.exception('radar run recorder could not store a start marker')
    return run_id


def finish_run(run_id: str, now: dt.datetime, *, summary: dict | None,
               error_code: str | None) -> None:
    """Close a run once.

    Only a row still `running` is updated, which is what makes this idempotent:
    a retry, a duplicated job or a late callback cannot restate totals that
    were already recorded, in either direction.

    The envelope and its projection are written by the same UPDATE, inside this
    transaction and under this guard. Not a second writer and not a later pass:
    a row whose typed counters disagreed with its own JSON would be a row with
    two answers, and there would be no way to tell which one was the record.
    """
    status = 'error' if error_code else 'ok'
    envelope = (None if summary is None
                else {'schema_version': SCHEMA_VERSION, 'summary': summary})
    try:
        # Inside the try, with everything else. `project` only inspects types
        # and logs, so it is not expected to raise -- but this module's first
        # rule is that instrumentation never takes a cycle down, and `tick`
        # does not wrap this call. A guarantee with an exception in it is not
        # one.
        version, countable, counters = project(envelope)
        with _session() as session, session.begin():
            # FOR UPDATE, so a second closer waits and then re-reads the status
            # this one committed rather than deciding against a stale snapshot.
            run = session.get(RadarIngestRun, run_id, with_for_update=True)
            if run is None:
                # Not the benign case. The start marker was never stored, so
                # this cycle's outcome is not recorded anywhere.
                logger.warning(
                    'radar run recorder has no row for run %s -- its start '
                    'marker never stored and this cycle is unrecorded', run_id)
                return
            if run.status in TERMINAL:
                # The designed no-op: a retry or a late callback arriving after
                # the run was closed. Distinct from the case above, because an
                # operator reading the log has to be able to tell a healthy
                # repeat from a lost run.
                logger.info('radar run %s was already closed as %s; leaving '
                            'its totals alone', run_id, run.status)
                return
            run.finished_at = now
            run.status = status
            run.summary_json = envelope
            run.error_code = error_code
            run.summary_schema_version = version
            run.summary_countable = countable
            for name, value in counters.items():
                setattr(run, name, value)
    except Exception:
        logger.exception('radar run recorder could not close run %s', run_id)


# --- reading it back -------------------------------------------------------

def iso_z(value: dt.datetime | None) -> str | None:
    """Naive UTC out as ISO 8601 with an explicit Z.

    Every datetime in this codebase is naive UTC by convention, and a naive
    timestamp on the wire is one the browser renders in local time without
    being asked to. An aware value would come out as `...+00:00Z`, which is
    not a timestamp at all -- hence the assertion rather than a coercion.
    """
    if value is None:
        return None
    assert value.tzinfo is None, 'naive UTC expected'
    return value.isoformat() + 'Z'


def _berlin_date(now: dt.datetime) -> dt.date:
    # replace(), not astimezone(): the input is naive UTC by convention, and
    # an aware value handed in here would be relabelled rather than converted.
    assert now.tzinfo is None, 'naive UTC expected'
    return now.replace(tzinfo=dt.timezone.utc).astimezone(BERLIN).date()


def _day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """This Berlin calendar day, as naive UTC instants.

    Built from two Berlin midnights, never by adding 86,400 seconds: the day
    Germany starts summer time is 23 hours long and the day it ends is 25, and
    a fixed-width day would put the boundary inside the wrong day and move
    runs between them.

    Midnight itself is never ambiguous or absent in this zone -- Berlin
    transitions at 02:00 and 03:00 -- so `fold` never has to be chosen. A zone
    that changed at midnight would need more than this.
    """
    start = dt.datetime.combine(day, dt.time(0), tzinfo=BERLIN)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0),
                              tzinfo=BERLIN)
    return (start.astimezone(dt.timezone.utc).replace(tzinfo=None),
            end.astimezone(dt.timezone.utc).replace(tzinfo=None))


class _Day:
    """One Berlin day's totals, folded a row at a time.

    An accumulator rather than a list of rows, because the list was the whole
    problem: a month of runs held every row and every decoded envelope at once.
    Nothing here grows with the number of runs.
    """

    __slots__ = ('completed', 'counted', 'running', 'errored', 'sums',
                 'missing')

    def __init__(self):
        self.completed = self.counted = self.running = self.errored = 0
        self.sums = {name: 0 for name in COUNTERS}
        # Counters that at least one PARTICIPATING row did not report. Kept as
        # a set of names rather than a null running total, so a later row
        # cannot quietly resurrect a counter an earlier one already made
        # unanswerable.
        self.missing = set()

    def add(self, row) -> None:
        if row.status == 'running':
            self.running += 1
            return
        if row.status == 'error':
            self.errored += 1
            return
        # Explicitly 'ok', not "whatever is left". The CHECK constraint allows
        # only three statuses today, but the reducer this replaced required
        # `status == 'ok'`, and a fourth status added later must not silently
        # become a completed run here.
        if row.status != 'ok':
            return
        self.completed += 1
        # The reader decides compatibility, not the writer's marker: the marker
        # says the envelope was well formed, this says its vocabulary is the
        # one these sums are in. Adding a v1 counter to a v2 one produces a
        # number that means neither.
        if not (row.summary_countable
                and row.summary_schema_version == SCHEMA_VERSION):
            return
        self.counted += 1
        for name in COUNTERS:
            value = getattr(row, name)
            if value is None:
                self.missing.add(name)
            else:
                self.sums[name] += value

    def counters(self) -> dict[str, int | None]:
        """A counter is null when nothing countable contributed to it, or when
        anything that did failed to report it. Never a zero standing in for an
        absent measurement -- a genuine measured zero and a missing one are
        different facts, and this module exists to keep them apart."""
        if not self.counted:
            return {name: None for name in COUNTERS}
        return {name: (None if name in self.missing else self.sums[name])
                for name in COUNTERS}

    def as_json(self, day: dt.date) -> dict:
        return {
            'date': day.isoformat(),
            **self.counters(),
            'completed_runs': self.completed,
            # How many of those the counters were actually drawn from. Lower
            # than completed_runs when a run stored no summary or stored one in
            # a schema version this code will not add to the current one.
            # Without it, a day of runs whose totals were all skipped is
            # indistinguishable from a day of runs that reported nothing, and a
            # per-run rate computed from completed_runs would be silently wrong.
            'counted_runs': self.counted,
            # Still open: either running now, or left behind by a process that
            # died. Both are cycles whose totals were never reported, which is
            # not the same as cycles that reported nothing.
            'incomplete_runs': self.running,
            'error_runs': self.errored,
            'completeness': 'partial' if self.completed else 'unknown',
        }


def summary(now: dt.datetime, days: int) -> dict:
    """Recorded fetch activity over the last `days` Berlin calendar days.

    What this is: the runs that were recorded, grouped by the Berlin day they
    STARTED in, with the counters the completed ones reported. What it is not
    is a measure of coverage. A day of successful runs proves those cycles
    happened, never that every post on every source was seen -- which is why
    `completeness` says 'partial' at its most confident and never 'complete'.

    `recording_started_at` is when the first run was ever recorded. Before it
    there is no gap to explain: nothing was recording.

    Nothing here is memoised and no day is ever frozen by its date. A run is
    filed under the Berlin day it STARTED in, but `finish_run` closes it later,
    so a cycle spanning midnight changes the previous day's totals after that
    day has ended -- roughly one day in five at the measured cadence. Every
    read re-reads.
    """
    if days not in ALLOWED_DAYS:
        raise ValueError(f'unsupported window: {days!r}')

    today = _berlin_date(now)
    dates = [today - dt.timedelta(days=offset)
             for offset in range(days - 1, -1, -1)]
    window_from = _day_bounds(dates[0])[0]
    window_to = _day_bounds(dates[-1])[1]

    # The typed projection, never `summary_json`.
    #
    # MEASURED 2026-09-09 against the disposable clone (MySQL 8.0.46;
    # production is MariaDB) by scratchpad/bench_activity.py. Reading a month
    # of activity used to transfer and decode every envelope: 12,728 rows,
    # 56.8 MiB and ~201 MiB of peak Python heap to return 120 integers, on a
    # `login_required`, uncached route. The projection columns are written
    # beside the envelope by `finish_run`; the envelope stays as provenance and
    # is never selected here.
    #
    # Two things keep the memory bounded, and they are not equal. The query
    # names eight scalar columns, so no envelope is fetched and no ORM entity
    # is constructed that could lazily load one -- that is what removed the
    # 201 MiB, because the heap was the decoded envelopes. Streaming then buys
    # the margin: `yield_per` folds each batch into the accumulators below and
    # lets it go, so nothing proportional to the run count is ever live.
    # Without it, `.all()` over the same eight scalars would hold single-digit
    # MiB of row tuples -- far short of the original cost, and far short of the
    # 0.8 MiB measured.
    #
    # Verified rather than assumed: on pymysql this executes on an SSCursor, so
    # the streaming is genuine server-side streaming and not a buffered result
    # handed out in slices.
    #
    # One statement, so one snapshot. Paging with separate LIMIT/OFFSET
    # queries would assemble a window out of several transactions, and a cycle
    # closing between two of them could be counted twice or not at all.
    rows = db.session.execute(
        sa.select(
            RadarIngestRun.started_at, RadarIngestRun.status,
            RadarIngestRun.summary_countable,
            RadarIngestRun.summary_schema_version,
            RadarIngestRun.posts_seen, RadarIngestRun.posts_new,
            RadarIngestRun.mentions, RadarIngestRun.buckets_written,
        ).where(RadarIngestRun.started_at >= window_from,
                RadarIngestRun.started_at < window_to)
        .execution_options(yield_per=READ_BATCH)
    )

    by_day: dict[dt.date, _Day] = {day: _Day() for day in dates}
    for row in rows:
        day = _berlin_date(row.started_at)
        # The window is the union of exactly these Berlin days, so a run
        # inside it belongs to one of them. Dropping it silently instead of
        # saying so would be a missing run nobody could find.
        accumulator = by_day.get(day)
        if accumulator is None:
            raise AssertionError(
                f'run at {row.started_at} fell outside {dates}')
        accumulator.add(row)

    recording_started_at = db.session.query(
        db.func.min(RadarIngestRun.started_at)).scalar()

    return {
        'generated_at': iso_z(now),
        'from': iso_z(window_from),
        'to': iso_z(window_to),
        'recording_started_at': iso_z(recording_started_at),
        'days': [by_day[day].as_json(day) for day in dates],
    }
