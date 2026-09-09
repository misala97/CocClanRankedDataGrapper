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
    """
    status = 'error' if error_code else 'ok'
    envelope = (None if summary is None
                else {'schema_version': SCHEMA_VERSION, 'summary': summary})
    try:
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
    except Exception:
        logger.exception('radar run recorder could not close run %s', run_id)


# --- reading it back -------------------------------------------------------

def iso_z(value: dt.datetime | None) -> str | None:
    """Naive UTC out as ISO 8601 with an explicit Z.

    Every datetime in this codebase is naive UTC by convention, and a naive
    timestamp on the wire is one the browser renders in local time without
    being asked to.
    """
    return None if value is None else value.isoformat() + 'Z'


def _berlin_date(now: dt.datetime) -> dt.date:
    return now.replace(tzinfo=dt.timezone.utc).astimezone(BERLIN).date()


def _day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """This Berlin calendar day, as naive UTC instants.

    Built from two Berlin midnights, never by adding 86,400 seconds: the day
    Germany starts summer time is 23 hours long and the day it ends is 25, and
    a fixed-width day would put the boundary inside the wrong day and move
    runs between them.
    """
    start = dt.datetime.combine(day, dt.time(0), tzinfo=BERLIN)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0),
                              tzinfo=BERLIN)
    return (start.astimezone(dt.timezone.utc).replace(tzinfo=None),
            end.astimezone(dt.timezone.utc).replace(tzinfo=None))


def _counters(runs: list[RadarIngestRun]) -> dict[str, int | None]:
    """Sum what the completed runs of one day reported.

    Only runs carrying a summary in the schema version this code understands
    are added. A day with no such run reports null for every counter -- it is
    a day nobody measured, and a zero would say the sources were quiet.

    These keep the meanings ingest gave them: posts_seen counts fetch
    deliveries and repeats a post two overlapping cycles returned, and
    buckets_written counts work performed rather than distinct quarter-hours.
    Neither is a claim about how much of the internet was covered.
    """
    envelopes = [run.summary_json for run in runs
                 if run.status == 'ok' and isinstance(run.summary_json, dict)
                 and run.summary_json.get('schema_version') == SCHEMA_VERSION]
    if not envelopes:
        return {name: None for name in COUNTERS}
    return {name: sum((envelope.get('summary') or {}).get(name) or 0
                      for envelope in envelopes)
            for name in COUNTERS}


def summary(now: dt.datetime, days: int) -> dict:
    """Recorded fetch activity over the last `days` Berlin calendar days.

    What this is: the runs that were recorded, grouped by the Berlin day they
    STARTED in, with the counters the completed ones reported. What it is not
    is a measure of coverage. A day of successful runs proves those cycles
    happened, never that every post on every source was seen -- which is why
    `completeness` says 'partial' at its most confident and never 'complete'.

    `recording_started_at` is when the first run was ever recorded. Before it
    there is no gap to explain: nothing was recording.
    """
    if days not in ALLOWED_DAYS:
        raise ValueError(f'unsupported window: {days!r}')

    today = _berlin_date(now)
    dates = [today - dt.timedelta(days=offset)
             for offset in range(days - 1, -1, -1)]
    window_from = _day_bounds(dates[0])[0]
    window_to = _day_bounds(dates[-1])[1]

    runs = RadarIngestRun.query.filter(
        RadarIngestRun.started_at >= window_from,
        RadarIngestRun.started_at < window_to).all()
    by_day: dict[dt.date, list[RadarIngestRun]] = {day: [] for day in dates}
    for run in runs:
        by_day.setdefault(_berlin_date(run.started_at), []).append(run)

    recording_started_at = db.session.query(
        db.func.min(RadarIngestRun.started_at)).scalar()

    return {
        'generated_at': iso_z(now),
        'from': iso_z(window_from),
        'to': iso_z(window_to),
        'recording_started_at': iso_z(recording_started_at),
        'days': [_day(day, by_day.get(day, [])) for day in dates],
    }


def _day(day: dt.date, runs: list[RadarIngestRun]) -> dict:
    completed = [run for run in runs if run.status == 'ok']
    return {
        'date': day.isoformat(),
        **_counters(completed),
        'completed_runs': len(completed),
        # Still open: either running now, or left behind by a process that
        # died. Both are cycles whose totals were never reported, which is not
        # the same as cycles that reported nothing.
        'incomplete_runs': sum(1 for run in runs if run.status == 'running'),
        'error_runs': sum(1 for run in runs if run.status == 'error'),
        'completeness': 'partial' if completed else 'unknown',
    }
