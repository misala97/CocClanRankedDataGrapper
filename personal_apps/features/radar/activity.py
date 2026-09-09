"""Recording what the ingest daemon actually did.

Two rules shape this module.

The first is that instrumentation may never become a reason a cycle fails.
Every write here is wrapped, logs a stable message and returns; `start_run`
mints its id before it touches the database, so ingest has something to report
against even when nothing can be stored.

The second is that the recorder owns its transaction. It opens a session bound
to `db.engine` rather than joining `db.session`, because the caller is the
ingest cycle and that session holds partially built buckets. Committing the
caller's pending work as a side effect of writing a marker row would be a
data-corruption bug wearing an instrumentation costume.

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

from sqlalchemy.orm import Session

from extensions import db
from models import RadarIngestRun

logger = logging.getLogger(__name__)

# The vocabulary `summary_json` is written in. Bump it when a counter changes
# meaning, never when one is added.
SCHEMA_VERSION = 1

TERMINAL = {'ok', 'error'}


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
            updated = session.query(RadarIngestRun).filter(
                RadarIngestRun.id == run_id,
                RadarIngestRun.status == 'running',
            ).update({'finished_at': now, 'status': status,
                      'summary_json': envelope, 'error_code': error_code},
                     synchronize_session=False)
        if not updated:
            logger.warning('radar run recorder found no open run %s to close',
                           run_id)
    except Exception:
        logger.exception('radar run recorder could not close run %s', run_id)
