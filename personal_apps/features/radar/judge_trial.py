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
import collections
import contextlib
import datetime as dt
import logging
import math
import threading

from extensions import db
from models import RadarJudgeTrial, RadarMention, RadarPost

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


# ---- recovery ---------------------------------------------------------------
#
# Undoing the trial means returning every mention it judged to the unjudged
# state that counts PROVISIONALLY, putting its journal eligibility back, and
# rebuilding the buckets that were computed without it. All three have to
# land together per window, or a crash leaves the counts disagreeing with
# the verdicts that produced them -- which is the exact failure the judging
# path already takes care to avoid.
#
# It is bounded and resumable because it may have to undo ten days of
# judgments on a 2 GB box, and because an incident is a bad time to
# discover that the recovery script is a single unbounded transaction.


def _recoverable(row):
    """Mentions this trial materialized, newest window first.

    Selected by the trial's OWN frozen model id and prompt version, not by
    whatever the code currently calls itself: a trial is recovered as the
    thing it was, even if the constants moved afterwards.

    Independent Anthropic review winners are excluded by exactly this
    filter and nothing more: if a review won, the mention's model IS the
    review's, so it does not match. A mention whose materialized verdict is
    the ENCODER'S is recovered even where a review history row also exists
    -- the review did not win there, the encoder's decision is the one in
    the counts, and skipping it would leave that decision in force forever
    while `remaining` never reached zero and the pin never released.
    """
    return (db.session.query(RadarMention, RadarPost)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.sentiment_model == row.model_id,
                    RadarMention.sentiment_prompt_version
                    == row.prompt_version))


def _window_of(post_created):
    return post_created.replace(minute=(post_created.minute // 15) * 15,
                                second=0, microsecond=0)


def recover_trial(*, apply=False, limit=2000, now=None):
    """Undo the trial's decisions, in bounded, whole-window transactions.

    Returns counts, and by default changes nothing at all: `apply=False` is
    a report, and it is the default because the alternative is a script
    that undoes ten days of production judgments if somebody forgets a
    flag.

    With `apply`, each window is one transaction: take the bucket guard,
    re-check the trial is still the one that was armed, clear the five
    non-tone fields, sync journal eligibility, rebuild the window from ALL
    its retained events, commit. A failure rolls that window back whole and
    leaves every earlier window recovered -- resumable, because a cleared
    mention no longer matches the selection.

    Tone and its provenance are NOT cleared. The trial never wrote them;
    what is there belongs to whoever did, and clearing it would delete a
    real verdict the board is showing.
    """
    if limit is not None and limit <= 0:
        raise TrialError('limit must be a positive number of mentions')
    now = now or dt.datetime.utcnow()
    row = current()
    if row is None:
        raise TrialError('no trial record: nothing to recover, and no pin '
                         'proving the evidence is still here')
    if row.retain_from is None:
        raise TrialError('the trial has no retention floor')

    rows = _recoverable(row).order_by(RadarPost.created_utc.desc(),
                                     RadarMention.id.desc()).all()
    total = len(rows)
    # Keyed by (ticker, quarter-hour) -- the identity of a BUCKET, which is
    # what gets rebuilt. Two tickers in the same quarter-hour are two
    # separate windows and must not be merged.
    by_window = collections.OrderedDict()
    for mention, post in rows:
        key = (mention.ticker, _window_of(post.created_utc))
        by_window.setdefault(key, []).append((mention, post))

    # Bounded by MENTIONS, and the bound is exact: the last window may be
    # recovered only in part. That is safe because the window is rebuilt
    # from ALL of its retained events either way -- the mentions still
    # judged stay excluded, the cleared ones count provisionally again, and
    # the next run finishes the job.
    selected, windows, taken = [], [], 0
    for key, members in by_window.items():
        if limit is not None and taken >= limit:
            break
        room = len(members) if limit is None else min(len(members),
                                                      limit - taken)
        selected.extend(members[:room])
        windows.append(key)
        taken += room

    outside = [start for _ticker, start in windows if start < row.retain_from]
    if outside:
        raise TrialError(
            '%d window(s) start before the retained interval (%s); their '
            'events are gone and rebuilding from what is left would write '
            'counts that never happened'
            % (len(outside), row.retain_from))

    report = {'total_mentions': total, 'total_windows': len(by_window),
              'selected_mentions': len(selected), 'selected_windows':
              len(windows), 'recovered': 0, 'remaining': total,
              'applied': bool(apply)}
    if not apply:
        return report
    if not selected:
        # Nothing matched. That is a successful, idempotent recovery -- a
        # second --apply after a complete one must not error, and must not
        # leave the pin held forever either.
        _mark_recovered()
        report.update(remaining=0, status=RECOVERED)
        return report

    recovered = 0
    taken_by_window = {}
    for key in windows:
        taken_by_window[key] = [entry for entry in selected
                                if (entry[0].ticker,
                                    _window_of(entry[1].created_utc)) == key]
    for key in windows:
        members = taken_by_window[key]
        # One window, one transaction. Bucket guard first, then the trial
        # row: every writer takes them in this order, which is what stops
        # two of them each holding one.
        with buckets_module().bucket_write_guard():
            state = (db.session.query(RadarJudgeTrial)
                     .filter_by(id=TRIAL_ID).with_for_update().one())
            if state.status == RECOVERED:
                break
            if (state.model_id != row.model_id
                    or state.prompt_version != row.prompt_version
                    or state.retain_from != row.retain_from):
                raise TrialError('the trial record changed while recovering')
            pairs = []
            for mention, post in members:
                mention.sentiment_relevance = None
                mention.sentiment_content_origin = None
                mention.sentiment_model = None
                mention.sentiment_prompt_version = None
                mention.sentiment_judged_at = None
                pairs.append(((post.source, post.external_id, mention.ticker),
                              None))
            journal_module().sync_chatter_eligibility(pairs)
            # NOT journal.rebuild_windows: that one refuses anything past
            # the 48-hour horizon, which is every window this is here for.
            # The pin is what makes the older ones safe, and it was checked
            # above.
            buckets_module().rebuild_windows([key], commit=False)
            db.session.commit()
        recovered += len(members)

    remaining = _recoverable(row).count()
    report.update(recovered=recovered, remaining=remaining)
    if remaining == 0:
        _mark_recovered()
        report['status'] = RECOVERED
    return report


def _mark_recovered():
    """Only after a FRESH count found nothing left.

    Marking recovered releases the retention pin, so claiming it early
    would let the pruner delete the evidence for whatever was still
    outstanding.
    """
    with advisory_lock(RETENTION_LOCK):
        row = current()
        if row is not None:
            row.status = RECOVERED
            db.session.commit()
    logger.info('radar encoder trial recovered; the retention pin is released')


def buckets_module():
    from . import buckets
    return buckets


def journal_module():
    from . import journal
    return journal


# ---- the audit's verdict, recorded ------------------------------------------

AUDIT_DRAW_DAY = 3
AUDIT_LABEL_DAY = 7
TRIAL_DEADLINE_DAYS = 10


def deadline(row):
    """When an unevaluated trial ends by itself, or None if it cannot.

    Measured from the FIRST JUDGED MENTION, not from arming or from a
    restart: the clock belongs to the live traffic the trial is changing,
    and a trial that was armed but never judged anything has nothing to
    expire.

    None once a PASSING audit is recorded. The deadline exists because a
    trial that changes live counts without ever testing its own acceptance
    rules is not a trial (spec §7.2b) -- and a trial that has tested them
    and passed has answered that. It keeps running suppressed, with its
    evidence still pinned; promoting it is a separate change.
    """
    if row is None or row.first_judged_at is None:
        return None
    if row.audit_evaluated_at is not None and row.audit_passed:
        return None
    return row.first_judged_at + dt.timedelta(days=TRIAL_DEADLINE_DAYS)


def accept_audit(report, report_sha256, now, *, passed):
    """Record the audit's result against the trial. The only writer of it.

    Refuses a report that does not belong to THIS trial, and refuses one
    that arrives after the deadline: a late report cannot postpone an
    expiry it already missed. A valid FAILING report is accepted and
    requests recovery -- failing is a result, not an error.

    Idempotent for the same report. A DIFFERENT report cannot replace a
    recorded result, because that is how a second opinion quietly becomes
    the first one.
    """
    if not report_sha256 or len(report_sha256) != 64:
        raise TrialError('an audit result needs its report hash')
    with advisory_lock(RETENTION_LOCK):
        row = current()
        if row is None:
            raise TrialError('no trial to accept an audit for')
        if row.audit_report_sha256 == report_sha256:
            return row                       # already recorded, same report
        if row.audit_evaluated_at is not None:
            raise TrialError(
                'this trial already has a recorded audit (%s); a different '
                'report cannot replace it'
                % row.audit_report_sha256[:12])
        if report.get('trial', {}).get('artifact_sha256') != row.artifact_sha256:
            raise TrialError('the report describes a different artifact')
        if report.get('trial', {}).get('prompt_version') != row.prompt_version:
            raise TrialError('the report describes a different prompt version')
        ends = deadline(row)
        if ends is not None and now > ends:
            raise TrialError(
                'the trial expired at %s; a report accepted afterwards would '
                'be postponing an expiry that already happened' % ends)

        row.audit_evaluated_at = now
        row.audit_passed = bool(passed)
        row.audit_report_sha256 = report_sha256
        if not passed:
            # A failing audit is the trial's own stop condition. It does
            # not wait for anyone to notice.
            row.status = RECOVERING
            row.stop_reason = 'audit failed (report %s)' % report_sha256[:12]
        db.session.commit()
    logger.info('radar encoder trial audit recorded: %s (report %s)',
                'PASSED' if passed else 'FAILED', report_sha256[:12])
    return row


def guard_encoder_trial(now):
    """May the encoder judge right now? Fails closed.

    Consulted at startup, before every batch, and again before a verdict is
    written -- the last one because an answer can come back after the trial
    it belongs to has ended, and a late answer must be discarded rather
    than stored.

    Returns the row when judging is allowed and raises otherwise, so a
    caller cannot mistake "no opinion" for permission.
    """
    row = current()
    if row is None:
        raise TrialError('the encoder is configured but no trial is armed; '
                         'without one there is no pin holding the evidence '
                         'its recovery would need')
    if row.status in (RECOVERING, RECOVERED):
        raise TrialError('the trial is %s and must not judge' % row.status)
    ends = deadline(row)
    if ends is not None and now >= ends:
        raise TrialError('the trial reached its %d-day deadline at %s'
                         % (TRIAL_DEADLINE_DAYS, ends))
    return row


def note_first_judgment(now):
    """Start the clock, in the transaction that writes the first verdict.

    Not at startup and not on a failed call: the deadline measures live
    traffic being changed, so it begins when a verdict is actually
    materialized and never before.
    """
    row = (db.session.query(RadarJudgeTrial).filter_by(id=TRIAL_ID)
           .with_for_update().one_or_none())
    if row is None:
        raise TrialError('no trial record')
    if row.first_judged_at is None:
        row.first_judged_at = now
        row.status = RUNNING
    return row


def tick(now, limit=2000):
    """Enforce the deadline. Reads the row; constructs no backend.

    Run by its own timer, independently of the ingest daemon, because the
    thing most likely to need stopping is the daemon. It cannot promise
    execution while the host is down -- so startup consults the same guard,
    and the first tick after a gap enforces the ORIGINAL deadline rather
    than a fresh one.

    Idempotent and safe to run every minute: with no trial, an armed trial
    that has not judged, a trial inside its deadline, or a recovered one,
    it does nothing at all.
    """
    row = current()
    if row is None or row.status == RECOVERED:
        return {'action': 'none'}
    if row.status == RECOVERING:
        # Already stopped, by an operator or a failed audit. Drain it.
        report = recover_trial(apply=True, limit=limit, now=now)
        report['action'] = 'recovering'
        return report

    ends = deadline(row)
    if ends is None or now < ends:
        return {'action': 'none'}

    logger.warning('radar encoder trial reached its %d-day deadline at %s '
                   'without a passing audit; stopping and recovering',
                   TRIAL_DEADLINE_DAYS, ends)
    request_stop('reached the %d-day deadline without a passing audit'
                 % TRIAL_DEADLINE_DAYS)
    report = recover_trial(apply=True, limit=limit, now=now)
    report['action'] = 'expired'
    return report
