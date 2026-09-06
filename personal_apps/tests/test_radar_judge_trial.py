# personal_apps/tests/test_radar_judge_trial.py
"""The trial record, and the evidence it stops retention from deleting.

The thing under test is an ability to UNDO. Switching a removing judge off
leaves every mention it removed still missing from the counts; putting them
back means rebuilding their windows from the journal, and the journal keeps
48 hours. So the pin is not a nicety on top of the trial -- without it the
trial becomes irreversible about two days in, quietly, while everything
still looks fine.

Every retention assertion here therefore runs the REAL pruners against real
rows and checks what survived, rather than checking that a cutoff was
computed.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from features.radar import judge_trial, retention
from models import (RadarJudgeTrial, RadarMention, RadarMentionEvent,
                    RadarPost, RadarSentimentJudgment)

NOW = dt.datetime(2027, 3, 1, 12, 0, 0)
SHA = 'a' * 64
PREFIX = 'zztrial-pin'


@pytest.fixture()
def no_trial():
    """This suite owns the singleton, and the dev database is shared."""
    with flask_app.app_context():
        _wipe()
        yield
        _wipe()


def _wipe():
    RadarJudgeTrial.query.delete(synchronize_session=False)
    RadarMentionEvent.query.filter(
        RadarMentionEvent.external_id.like(PREFIX + '%')).delete(
        synchronize_session=False)
    ids = [row.id for row in RadarPost.query.filter(
        RadarPost.external_id.like(PREFIX + '%')).all()]
    if ids:
        RadarPost.query.filter(RadarPost.id.in_(ids)).delete(
            synchronize_session=False)
    db.session.commit()


def arm(now=NOW, rate=0.31, seed=20260906, sha=SHA):
    return judge_trial.arm_trial(now, artifact_sha256=sha,
                                 baseline_report='reports/baseline.json',
                                 baseline_removal_rate=rate, seed=seed)


def evidence(external_id, when, *, confidence='high', with_mention=True,
             chatter=None):
    """A post, its journal event, and optionally its mention and history.

    The journal row exists even for a post whose tickers were all `low` --
    those never become mentions at all, and they are exactly the rows a
    rebuild needs and cannot reconstruct from anywhere else.
    """
    post = RadarPost(source='bluesky', external_id=external_id,
                     channel='firehose', author='someone', created_utc=when,
                     title=None, body='ZZT ripping', first_seen=when,
                     last_seen=when)
    db.session.add(post)
    db.session.flush()
    db.session.add(RadarMentionEvent(
        source='bluesky', external_id=external_id, ticker='ZZT',
        confidence=confidence, created_utc=when,
        bucket_start=when.replace(minute=(when.minute // 15) * 15, second=0,
                                  microsecond=0),
        promoted=False, counts_as_human_chatter=chatter))
    if with_mention:
        mention = RadarMention(post_id=post.id, ticker='ZZT',
                               confidence=confidence, lexicon_sentiment=0.2)
        db.session.add(mention)
        db.session.flush()
        db.session.add(RadarSentimentJudgment(
            mention_id=mention.id, stage='primary', model='radar-encoder-v1',
            prompt_version='zz-prompt', relevance='irrelevant',
            content_origin='human_chatter', attitude='none',
            expected_move='unknown', confidence='high',
            input_tokens=0, output_tokens=0, created_utc=when))
    db.session.commit()
    return post.id


def surviving_events():
    return {row.external_id for row in RadarMentionEvent.query.filter(
        RadarMentionEvent.external_id.like(PREFIX + '%')).all()}


def surviving_posts():
    return {row.external_id for row in RadarPost.query.filter(
        RadarPost.external_id.like(PREFIX + '%')).all()}


# ---- arming -----------------------------------------------------------------

def test_arming_freezes_what_the_evaluation_may_not_choose(no_trial):
    with flask_app.app_context():
        row = arm(rate=0.4)
        assert row.status == judge_trial.ARMED
        assert row.artifact_sha256 == SHA
        assert row.first_judged_at is None
        # 400 removal decisions at a 0.4 removal rate needs 1000 rows.
        assert row.recipe['sample_size'] == 1000
        assert row.recipe['seed'] == 20260906
        assert row.recipe['baseline_removal_rate'] == 0.4


def test_the_model_and_prompt_are_taken_from_the_code_not_the_caller(no_trial):
    """They say WHAT was tried. A caller able to pass them could describe a
    trial that never happened."""
    from features.radar import judge_backends, llm_sentiment
    with flask_app.app_context():
        row = arm()
        assert row.model_id == judge_backends.ENCODER_MODEL_ID
        assert row.prompt_version == llm_sentiment.PROMPT_VERSION


def test_the_pin_starts_on_a_quarter_hour_before_the_journal_horizon(no_trial):
    """Buckets are quarter-hours and recovery rebuilds whole ones. A floor
    landing mid-window would pin half a bucket, and rebuilding from half a
    window writes a count that never happened."""
    with flask_app.app_context():
        row = arm(now=dt.datetime(2027, 3, 1, 12, 7, 33))
        assert row.retain_from == dt.datetime(2027, 2, 27, 12, 15)
        assert row.retain_from < row.armed_at - dt.timedelta(hours=47)


def test_a_second_arming_is_refused(no_trial):
    """Two trials sharing one record could not both be recovered."""
    with flask_app.app_context():
        first = arm()
        with pytest.raises(judge_trial.TrialError):
            arm(now=NOW + dt.timedelta(days=1), sha='b' * 64)
        again = judge_trial.current()
        assert again.armed_at == first.armed_at
        assert again.artifact_sha256 == SHA


@pytest.mark.parametrize('kwargs', [
    {'sha': 'not-a-sha'},
    {'sha': 'A' * 64},                      # uppercase is not the format
    {'sha': 'a' * 63},
    {'rate': 0},
    {'rate': 1.5},
    {'rate': -0.2},
    {'rate': 'many'},
    {'seed': 'later'},
])
def test_arming_refuses_an_input_it_cannot_trust(no_trial, kwargs):
    with flask_app.app_context():
        with pytest.raises(judge_trial.TrialError):
            arm(**kwargs)
        assert judge_trial.current() is None


def test_arming_refuses_without_a_baseline(no_trial):
    """The trial's gates are RELATIVE to the incumbent. With no baseline
    there is nothing to be relative to, and 'we will find one later' is how
    a threshold ends up chosen after the numbers are in."""
    with flask_app.app_context():
        with pytest.raises(judge_trial.TrialError):
            judge_trial.arm_trial(NOW, artifact_sha256=SHA,
                                  baseline_report='  ',
                                  baseline_removal_rate=0.3, seed=1)
        assert judge_trial.current() is None


# ---- the floor --------------------------------------------------------------

def test_nothing_is_pinned_without_a_trial(no_trial):
    with flask_app.app_context():
        assert judge_trial.retention_floor() is None


@pytest.mark.parametrize('status,pins', [
    (judge_trial.ARMED, True),
    (judge_trial.RUNNING, True),
    (judge_trial.RECOVERING, True),
    (judge_trial.RECOVERED, False),
])
def test_only_a_completed_recovery_releases_the_pin(no_trial, status, pins):
    with flask_app.app_context():
        row = arm()
        row.status = status
        db.session.commit()
        assert (judge_trial.retention_floor() is not None) is pins


def test_a_passing_audit_does_not_release_the_pin(no_trial):
    """Passing authorises CONTINUING, and continuing still has to be
    undoable. Only recovery has used the evidence up."""
    with flask_app.app_context():
        row = arm()
        row.status = judge_trial.RUNNING
        row.audit_evaluated_at = NOW
        row.audit_passed = True
        row.audit_report_sha256 = 'c' * 64
        db.session.commit()
        assert judge_trial.retention_floor() == row.retain_from


# ---- what the pruners actually delete ---------------------------------------

def test_the_journal_forgets_the_trials_windows_without_a_pin(no_trial):
    """The state this exists to prevent, proved by running the real pruner
    with no trial armed: 48 hours on, the evidence is gone."""
    with flask_app.app_context():
        evidence(PREFIX + '-a', NOW - dt.timedelta(hours=60))
        retention.prune_mention_events(NOW)
        assert surviving_events() == set()


def test_an_armed_trial_keeps_the_journal_it_would_rebuild_from(no_trial):
    with flask_app.app_context():
        arm(now=NOW)
        # Inside the pin (armed_at - 48h) and far outside the ordinary
        # 48-hour horizon by the time the pruner runs ten days later.
        evidence(PREFIX + '-inside', NOW - dt.timedelta(hours=40))
        evidence(PREFIX + '-older', NOW - dt.timedelta(hours=60))

        retention.prune_mention_events(NOW + dt.timedelta(days=10))

        assert PREFIX + '-inside' in surviving_events()
        # ...and the ordinary rules still apply to everything else.
        assert PREFIX + '-older' not in surviving_events()


def test_the_pin_keeps_low_confidence_events_with_no_mention_at_all(no_trial):
    """A post whose tickers were all `low` never becomes a mention, so the
    journal row is the ONLY record of it -- and a rebuild that cannot see
    it silently writes a smaller low_count than really happened."""
    with flask_app.app_context():
        arm(now=NOW)
        evidence(PREFIX + '-low', NOW - dt.timedelta(hours=30),
                 confidence='low', with_mention=False)

        retention.prune_mention_events(NOW + dt.timedelta(days=10))

        assert PREFIX + '-low' in surviving_events()


def test_the_pin_keeps_the_posts_and_their_judgment_history(no_trial):
    """Posts cascade to mentions and mentions to history, so losing a post
    loses the evidence of what the trial decided about it."""
    with flask_app.app_context():
        arm(now=NOW)
        evidence(PREFIX + '-post', NOW - dt.timedelta(hours=30))

        # Thirty-one days on, the ordinary post horizon has passed it.
        retention.prune_posts(NOW + dt.timedelta(days=31))

        assert PREFIX + '-post' in surviving_posts()
        kept = RadarPost.query.filter_by(
            external_id=PREFIX + '-post').one()
        mention = RadarMention.query.filter_by(post_id=kept.id).one()
        assert RadarSentimentJudgment.query.filter_by(
            mention_id=mention.id).count() == 1


def test_posts_outside_the_pin_still_age_out(no_trial):
    with flask_app.app_context():
        arm(now=NOW)
        evidence(PREFIX + '-ancient', NOW - dt.timedelta(days=5))

        retention.prune_posts(NOW + dt.timedelta(days=31))

        assert PREFIX + '-ancient' not in surviving_posts()


def test_a_recovered_trial_stops_holding_evidence(no_trial):
    with flask_app.app_context():
        row = arm(now=NOW)
        evidence(PREFIX + '-done', NOW - dt.timedelta(hours=30))
        row.status = judge_trial.RECOVERED
        db.session.commit()

        retention.prune_mention_events(NOW + dt.timedelta(days=10))

        assert surviving_events() == set()


# ---- stopping ---------------------------------------------------------------

def test_a_stop_is_durable_and_carries_its_reason(no_trial):
    """In the database, not in an environment file -- an environment file
    loses to a stale unit definition or a restart that reads the old one."""
    with flask_app.app_context():
        arm()
        judge_trial.request_stop('removal share moved -60% against baseline')
        row = judge_trial.current()
        assert row.status == judge_trial.RECOVERING
        assert 'removal share' in row.stop_reason
        # And it still pins: a stopped trial has MORE to recover, not less.
        assert judge_trial.retention_floor() is not None


def test_a_stop_needs_a_reason(no_trial):
    with flask_app.app_context():
        arm()
        with pytest.raises(judge_trial.TrialError):
            judge_trial.request_stop('   ')
        assert judge_trial.current().status == judge_trial.ARMED


def test_stopping_a_recovered_trial_changes_nothing(no_trial):
    with flask_app.app_context():
        row = arm()
        row.status = judge_trial.RECOVERED
        db.session.commit()
        judge_trial.request_stop('too late')
        assert judge_trial.current().status == judge_trial.RECOVERED


def test_stopping_without_a_trial_is_an_error_not_a_shrug(no_trial):
    with flask_app.app_context():
        with pytest.raises(judge_trial.TrialError):
            judge_trial.request_stop('nothing to stop')


# ---- the lock ---------------------------------------------------------------

def test_the_retention_lock_is_held_across_processes(no_trial):
    """A threading.Lock would not do: the pruner runs in the daemon and
    arming runs from a CLI, which are different processes entirely."""
    import sqlalchemy as sa
    with flask_app.app_context():
        if db.engine.dialect.name != 'mysql':
            pytest.skip('advisory locks are a server feature')
        other = db.engine.connect()
        try:
            taken = other.exec_driver_sql(
                "SELECT GET_LOCK(%s, 0)", (judge_trial.RETENTION_LOCK,)
            ).scalar()
            assert taken == 1
            with pytest.raises(judge_trial.TrialLockUnavailable):
                with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK,
                                               timeout=0):
                    pass
        finally:
            other.exec_driver_sql("SELECT RELEASE_LOCK(%s)",
                                  (judge_trial.RETENTION_LOCK,))
            other.close()


def test_the_lock_is_released_even_when_the_body_raises(no_trial):
    with flask_app.app_context():
        if db.engine.dialect.name != 'mysql':
            pytest.skip('advisory locks are a server feature')
        with pytest.raises(ValueError):
            with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK):
                raise ValueError('boom')
        # Free again, or this test would be the last one that ever passed.
        with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK, timeout=0):
            pass


def test_pruning_cannot_cross_a_pin_installed_while_it_runs(no_trial):
    """The race the lock exists for: a long prune computes a cutoff, a
    trial is armed, and the next chunk must see the new floor."""
    with flask_app.app_context():
        evidence(PREFIX + '-race-1', NOW - dt.timedelta(hours=30))
        evidence(PREFIX + '-race-2', NOW - dt.timedelta(hours=29))
        calls = {'n': 0}
        real = retention._pinned

        def arm_before_the_second_chunk(cutoff):
            # Armed only once the first chunk has already been decided, so
            # a cutoff computed once at the top of the loop would never see
            # this trial at all -- which is the bug being tested for.
            calls['n'] += 1
            if calls['n'] == 2:
                arm(now=NOW)
            return real(cutoff)

        retention._pinned = arm_before_the_second_chunk
        try:
            # chunk_size 1 so the floor is re-read between the two rows.
            retention.prune_mention_events(NOW + dt.timedelta(days=10),
                                           chunk_size=1, pause=0)
        finally:
            retention._pinned = real

        # The first chunk ran before the trial existed and legitimately
        # deleted its row; the second re-read the floor, saw the new pin,
        # and kept its own.
        assert calls['n'] >= 2, 'the floor must be re-read per chunk'
        assert PREFIX + '-race-1' not in surviving_events()
        assert PREFIX + '-race-2' in surviving_events()


def test_taking_the_same_lock_twice_in_one_thread_is_not_contention(no_trial):
    """Re-entering is not contention. advisory_lock takes a connection of
    its own, so without this a nested acquisition would block against its
    own outer holder for the full timeout -- a self-deadlock that reads
    exactly like another process holding the lock. Recovery nests these.
    """
    with flask_app.app_context():
        with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK):
            with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK,
                                           timeout=0):
                pass
        # ...and the outermost exit really did release it.
        with judge_trial.advisory_lock(judge_trial.RETENTION_LOCK, timeout=0):
            pass
