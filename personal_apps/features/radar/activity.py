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


def _counted(runs) -> list[dict]:
    """The summaries of one day that this code can honestly add up.

    Only the schema version it understands. The version exists because a
    counter's MEANING changed, and adding a v1 `posts_seen` to a v2 one
    produces a number that means neither.
    """
    return [run.summary_json['summary'] for run in runs
            if isinstance(run.summary_json, dict)
            and run.summary_json.get('schema_version') == SCHEMA_VERSION
            and isinstance(run.summary_json.get('summary'), dict)]


def _counters(summaries: list[dict]) -> dict[str, int | None]:
    """Sum one day's countable summaries, counter by counter.

    A counter absent from any summary being added makes THAT counter null for
    the day rather than a zero. Counters are allowed to be added without a
    version bump, so an older run genuinely never measured a newer one -- and
    reporting 0 for it would be the exact lie this module exists to avoid:
    a cycle that measured nothing turned into a cycle that measured nothing
    happening.

    The counters keep the meanings ingest gave them. posts_seen counts fetch
    deliveries and repeats a post two overlapping cycles returned;
    buckets_written counts work performed rather than distinct quarter-hours.
    Neither is a claim about how much of the internet was covered.
    """
    if not summaries:
        return {name: None for name in COUNTERS}
    counters: dict[str, int | None] = {}
    for name in COUNTERS:
        values = [summary.get(name) for summary in summaries]
        counters[name] = (None if any(value is None for value in values)
                          else sum(values))
    return counters


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

    # Three columns rather than whole ORM rows, and it is not enough at the
    # widest window.
    #
    # MEASURED, 2026-09-09, against the disposable clone by
    # scratchpad/bench_activity.py, which derives the run count from the two
    # schedulers that actually call tick -- `radar_cycle` on the NYSE session
    # (180s open, 600s after hours, 1800s overnight and weekends) and
    # `radar_reddit` fixed at ARCTIC_SHIFT_INTERVAL_SECONDS:
    #
    #     days=1   568 runs    3.3 MiB   36 ms    (weekday; a weekend day is 336)
    #     days=7   3,352 runs 19.2 MiB  406 ms
    #     days=30  14,792 runs 84.7 MiB 2,706 ms
    #
    # An earlier note here guessed ~2,880 runs over 30 days by dividing the
    # window by the board archive's 15-minute cadence. That is the wrong
    # writer and it was five times low: one envelope is 6 KB because every
    # per-source map is keyed by all 36 concrete sources, and two jobs write
    # one row each per firing.
    #
    # So days=30 reads ~85 MiB to return four integers a day. Extracting the
    # counters in SQL would remove the transfer and is NOT taken here: it needs
    # JSON path functions whose behaviour on the production MariaDB cannot be
    # verified from this environment. The portable fix -- typed counter columns
    # written at finish_run, or a daily rollup -- is a schema change, and that
    # decision belongs to the plan owner. The evidence is in HUB-LEDGER.md.
    runs = db.session.query(
        RadarIngestRun.started_at, RadarIngestRun.status,
        RadarIngestRun.summary_json,
    ).filter(RadarIngestRun.started_at >= window_from,
             RadarIngestRun.started_at < window_to).all()
    by_day: dict[dt.date, list] = {day: [] for day in dates}
    for run in runs:
        day = _berlin_date(run.started_at)
        # The window is the union of exactly these Berlin days, so a run
        # inside it belongs to one of them. Dropping it silently instead of
        # saying so would be a missing run nobody could find.
        assert day in by_day, f'run at {run.started_at} fell outside {dates}'
        by_day[day].append(run)

    recording_started_at = db.session.query(
        db.func.min(RadarIngestRun.started_at)).scalar()

    return {
        'generated_at': iso_z(now),
        'from': iso_z(window_from),
        'to': iso_z(window_to),
        'recording_started_at': iso_z(recording_started_at),
        'days': [_day(day, by_day.get(day, [])) for day in dates],
    }


def _day(day: dt.date, runs: list) -> dict:
    completed = [run for run in runs if run.status == 'ok']
    summaries = _counted(completed)
    return {
        'date': day.isoformat(),
        **_counters(summaries),
        'completed_runs': len(completed),
        # How many of those the counters were actually drawn from. Lower than
        # completed_runs when a run stored no summary or stored one in a
        # schema version this code will not add to the current one. Without
        # it, a day of runs whose totals were all skipped is indistinguishable
        # from a day of runs that reported nothing, and a per-run rate
        # computed from completed_runs would be silently wrong.
        'counted_runs': len(summaries),
        # Still open: either running now, or left behind by a process that
        # died. Both are cycles whose totals were never reported, which is not
        # the same as cycles that reported nothing.
        'incomplete_runs': sum(1 for run in runs if run.status == 'running'),
        'error_runs': sum(1 for run in runs if run.status == 'error'),
        'completeness': 'partial' if completed else 'unknown',
    }
