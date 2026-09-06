# personal_apps/features/radar/judge_trial.py
"""The durable record of one encoder trial, and the evidence it pins.

Switching a removing judge off is not a rollback. By the time anyone wants
to stop it, its relevance verdicts have already left mentions out of bucket
counts and journal eligibility, and undoing that means clearing those
mentions and rebuilding their windows FROM THE JOURNAL. The journal keeps 48
hours. Posts keep 30 days. So the ability to undo the trial expires long
before anyone would finish arguing about whether to.

This module is what makes recovery possible at all:

- a singleton row, armed BEFORE the first encoder write, that says a trial
  is running and until when its evidence must be kept;
- a retention floor the pruners honour, so the journal stops forgetting the
  windows the trial touched;
- a stop switch that lives in the DATABASE rather than in an environment
  file, because an environment file loses to a stale service definition, a
  forgotten export, or a restart nobody expected.

The row is the enforcement boundary. Not the configuration, not the
service, not anybody's memory of what they set last week.
"""
import contextlib
import datetime as dt
import logging
import math
import threading

import sqlalchemy as sa

from extensions import db
from models import RadarJudgeTrial

logger = logging.getLogger('radar.judge_trial')

TRIAL_ID = 1

ARMED = 'armed'
RUNNING = 'running'
RECOVERING = 'recovering'
RECOVERED = 'recovered'

# While the trial is in one of these, its evidence is pinned.
PINNING = (ARMED, RUNNING, RECOVERING)

# How far back the pin reaches. The journal's own horizon is 48 hours, and
# the live judge gate reads a 24-hour window, so a floor 48 hours before
# arming covers every window the trial's first pass could possibly touch.
PIN_LOOKBACK = dt.timedelta(hours=48)

# The audit needs roughly 400 removal DECISIONS to bound removal precision
# at 95% confidence, so the sample is sized by the removal rate rather than
# by convenience.
REMOVAL_DECISIONS_WANTED = 400

RETENTION_LOCK = 'radar_encoder_trial_retention'

# Which advisory locks THIS thread already holds. MySQL's GET_LOCK is
# reentrant within one session, but advisory_lock deliberately takes a
# connection of its own, so without this a nested acquisition would block
# against its own outer holder until the timeout expired -- a self-deadlock
# that looks exactly like contention with another process. Found by the
# arm-during-prune test, which is precisely such a nesting.
_held = threading.local()


class TrialError(Exception):
    """The trial record refuses what was asked of it."""


class TrialLockUnavailable(TrialError):
    """Somebody else holds the lock this operation needs."""


@contextlib.contextmanager
def advisory_lock(name, timeout=10):
    """A lock the whole DATABASE honours, not just this process.

    `buckets.BUCKET_WRITE_LOCK` is a threading.Lock: it serializes the
    daemon's own jobs and knows nothing about the web process, a CLI run or
    the watchdog timer. Arming, pruning and recovery all have to exclude
    each other ACROSS processes, so they need a lock the server holds.

    Taken on its OWN connection. A session commit hands the session's
    connection back to the pool, and MySQL releases that connection's locks
    with it -- so a lock taken on the session would quietly vanish at the
    first commit inside the critical section.
    """
    engine = db.engine
    if engine.dialect.name != 'mysql':
        # sqlite, in the model unit tests: one connection, no cross-process
        # story to tell, and GET_LOCK does not exist.
        yield True
        return
    mine = getattr(_held, 'names', None)
    if mine is None:
        mine = _held.names = set()
    if name in mine:
        # Already ours. Re-entering is not contention.
        yield True
        return
    connection = engine.connect()
    try:
        got = connection.exec_driver_sql(
            'SELECT GET_LOCK(%s, %s)', (name, timeout)).scalar()
        if got != 1:
            raise TrialLockUnavailable(
                'could not take %r within %ss' % (name, timeout))
        mine.add(name)
        yield True
    finally:
        mine.discard(name)
        try:
            connection.exec_driver_sql('SELECT RELEASE_LOCK(%s)', (name,))
        finally:
            connection.close()


def _quarter_hour_after(when):
    """The next quarter-hour boundary strictly after `when`.

    Buckets are quarter-hours, and recovery rebuilds whole ones. A floor
    that landed mid-window would pin half a bucket, which is worse than
    useless: the rebuild would see a partial window and write a count that
    never happened.
    """
    floor = when.replace(minute=(when.minute // 15) * 15, second=0,
                         microsecond=0)
    return floor + dt.timedelta(minutes=15)


def current():
    """The trial row, or None. Read-only, constructs nothing."""
    return db.session.get(RadarJudgeTrial, TRIAL_ID)


def trial_status():
    """A plain dict for the CLI and the daemon's startup log."""
    row = current()
    if row is None:
        return None
    return {
        'status': row.status,
        'model_id': row.model_id,
        'prompt_version': row.prompt_version,
        'artifact_sha256': row.artifact_sha256,
        'armed_at': row.armed_at,
        'retain_from': row.retain_from,
        'first_judged_at': row.first_judged_at,
        'audit_evaluated_at': row.audit_evaluated_at,
        'audit_passed': row.audit_passed,
        'audit_report_sha256': row.audit_report_sha256,
        'stop_reason': row.stop_reason,
        'recipe': row.recipe,
    }


def retention_floor():
    """The timestamp retention must not prune past, or None.

    None means no trial is pinning anything and the ordinary horizons
    apply. A trial that has been fully RECOVERED stops pinning: its
    evidence has been used. A trial that merely PASSED its audit does not
    -- passing authorises continuing, and continuing still needs to be
    undoable.
    """
    row = current()
    if row is None or row.status not in PINNING:
        return None
    return row.retain_from


def arm_trial(now, *, artifact_sha256, baseline_report, baseline_removal_rate,
              seed):
    """Create the trial record. Once, before any encoder write.

    Everything the later evaluation is not allowed to choose for itself is
    frozen here: the artifact bundle hash, the baseline report it will be
    compared against, the removal rate that fixes the sample size, and the
    sampling seed. Fixing them AFTER seeing predictions is how a trial
    passes itself.

    Arming cannot overwrite an existing row or reset its clock. A second
    arm is an error, not an idempotent no-op: if a trial is already
    running, whoever is arming has lost track of which one is which.
    """
    from . import judge_backends, llm_sentiment

    if not isinstance(artifact_sha256, str) or len(artifact_sha256) != 64 \
            or any(c not in '0123456789abcdef' for c in artifact_sha256):
        raise TrialError('artifact_sha256 must be 64 lowercase hex characters')
    if not baseline_report or not str(baseline_report).strip():
        raise TrialError('a baseline report is required before arming')
    try:
        removal_rate = float(baseline_removal_rate)
    except (TypeError, ValueError):
        raise TrialError('baseline_removal_rate must be a number')
    if not 0 < removal_rate <= 1:
        raise TrialError('baseline_removal_rate must be in (0, 1], got %r'
                         % baseline_removal_rate)
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        raise TrialError('seed must be an integer')

    with advisory_lock(RETENTION_LOCK):
        if current() is not None:
            raise TrialError('a trial record already exists; this build runs '
                             'one trial and will not overwrite it')
        row = RadarJudgeTrial(
            id=TRIAL_ID,
            # Frozen from the code that is about to run, not from an
            # argument: these two say WHAT was tried, and a caller that
            # could pass them could describe a trial that never happened.
            model_id=judge_backends.ENCODER_MODEL_ID,
            prompt_version=llm_sentiment.PROMPT_VERSION,
            artifact_sha256=artifact_sha256,
            status=ARMED,
            armed_at=now,
            retain_from=_quarter_hour_after(now - PIN_LOOKBACK),
            recipe={
                'seed': seed,
                'baseline_report': str(baseline_report),
                'baseline_removal_rate': removal_rate,
                'sample_size': int(math.ceil(REMOVAL_DECISIONS_WANTED
                                             / removal_rate)),
                'removal_decisions_wanted': REMOVAL_DECISIONS_WANTED,
            })
        db.session.add(row)
        db.session.commit()
    logger.info('radar encoder trial armed: artifact %s, evidence pinned '
                'from %s, sample size %d',
                artifact_sha256[:12], row.retain_from,
                row.recipe['sample_size'])
    return row


def request_stop(reason):
    """Persist the stop BEFORE anything else changes.

    Durable, because the alternative is an environment file -- and an
    environment file loses to a stale unit definition, an un-exported
    variable, or a restart that reads the old one. Startup and every batch
    consult this row, so a stopped trial stays stopped even if
    RADAR_JUDGE_PRIMARY=encoder survives somewhere.
    """
    if not reason or not str(reason).strip():
        raise TrialError('a stop needs a reason; it is the record of why')
    with advisory_lock(RETENTION_LOCK):
        row = current()
        if row is None:
            raise TrialError('no trial to stop')
        if row.status == RECOVERED:
            return row
        row.status = RECOVERING
        row.stop_reason = str(reason).strip()
        db.session.commit()
    logger.warning('radar encoder trial stopping: %s', reason)
    return row
