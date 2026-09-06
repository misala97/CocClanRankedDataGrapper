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

# EVERY timestamp in this suite lives in 2020, and that is a safety
# property, not a style choice. These tests call the REAL pruners against
# the WHOLE table -- that is the point of them, since a cutoff computed
# correctly and applied to nothing proves nothing -- and the development
# database is shared with every other suite and with real ingested data.
#
# A cutoff in 2020 cannot reach a row from 2026. An earlier version of this
# file used 2027, which put every cutoff in the future: it deleted the
# development database's posts, mentions, judgment history and journal.
# `prune_within_2020` below refuses to run a pruner whose cutoff escapes
# the decade, so the mistake cannot be repeated by changing one constant.
NOW = dt.datetime(2020, 3, 1, 12, 0, 0)
SAFETY_CEILING = dt.datetime(2021, 1, 1)
SHA = 'a' * 64
PREFIX = 'zztrial-pin'


def prune_events(now):
    """The real journal pruner, refused if its cutoff leaves 2020."""
    cutoff = now - dt.timedelta(hours=48)
    assert cutoff < SAFETY_CEILING, (
        'this cutoff (%s) would delete real development data' % cutoff)
    return retention.prune_mention_events(now)


def prune_posts(now):
    """The real post pruner, refused if its cutoff leaves 2020."""
    cutoff = now - dt.timedelta(days=30)
    assert cutoff < SAFETY_CEILING, (
        'this cutoff (%s) would delete real development data' % cutoff)
    return retention.prune_posts(now)


@pytest.fixture()
def no_trial():
    """This suite owns the singleton, and the dev database is shared."""
    with flask_app.app_context():
        _wipe()
        yield
        _wipe()


def _wipe():
    from models import RadarBucket, RadarBucketSource
    RadarJudgeTrial.query.delete(synchronize_session=False)
    # roll_up leaves buckets, and buckets are never pruned by anything.
    for model in (RadarBucketSource, RadarBucket):
        # Every ZZT bucket, not only the ones inside this suite's decade:
        # buckets are never pruned by anything, so a stray one from an
        # earlier version of these fixtures outlives the run that made it
        # and trips the daemon's rollup-bootstrap guard at startup.
        model.query.filter(model.ticker == 'ZZT').delete(
            synchronize_session=False)
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
        prune_events(NOW)
        assert surviving_events() == set()


def test_an_armed_trial_keeps_the_journal_it_would_rebuild_from(no_trial):
    with flask_app.app_context():
        arm(now=NOW)
        # Inside the pin (armed_at - 48h) and far outside the ordinary
        # 48-hour horizon by the time the pruner runs ten days later.
        evidence(PREFIX + '-inside', NOW - dt.timedelta(hours=40))
        evidence(PREFIX + '-older', NOW - dt.timedelta(hours=60))

        prune_events(NOW + dt.timedelta(days=10))

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

        prune_events(NOW + dt.timedelta(days=10))

        assert PREFIX + '-low' in surviving_events()


def test_the_pin_keeps_the_posts_and_their_judgment_history(no_trial):
    """Posts cascade to mentions and mentions to history, so losing a post
    loses the evidence of what the trial decided about it."""
    with flask_app.app_context():
        arm(now=NOW)
        evidence(PREFIX + '-post', NOW - dt.timedelta(hours=30))

        # Thirty-one days on, the ordinary post horizon has passed it.
        prune_posts(NOW + dt.timedelta(days=31))

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

        prune_posts(NOW + dt.timedelta(days=31))

        assert PREFIX + '-ancient' not in surviving_posts()


def test_a_recovered_trial_stops_holding_evidence(no_trial):
    with flask_app.app_context():
        row = arm(now=NOW)
        evidence(PREFIX + '-done', NOW - dt.timedelta(hours=30))
        row.status = judge_trial.RECOVERED
        db.session.commit()

        prune_events(NOW + dt.timedelta(days=10))

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
            now = NOW + dt.timedelta(days=10)
            assert now - dt.timedelta(hours=48) < SAFETY_CEILING
            retention.prune_mention_events(now, chunk_size=1, pause=0)
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


# ---- recovery ---------------------------------------------------------------
#
# The property under test is that the counts end up as though the encoder
# had never judged. So these build a real bucket from real journal events,
# let the encoder remove some of them, recover, and compare the bucket to
# what it was -- rather than checking that some columns became NULL.

def bucket_of(ticker, window):
    from models import RadarBucket
    return RadarBucket.query.filter_by(ticker=ticker,
                                       bucket_start=window).one_or_none()


def counted(ticker, window):
    row = bucket_of(ticker, window)
    return None if row is None else (row.mention_count,
                                     row.high_confidence_count,
                                     row.distinct_authors, row.low_count)


def judged_by_encoder(mention, when, relevance='irrelevant'):
    """Materialize an encoder verdict the way apply_judgments would."""
    from features.radar import llm_sentiment
    mention.sentiment_relevance = relevance
    mention.sentiment_content_origin = 'human_chatter'
    mention.sentiment_model = 'radar-encoder-v1'
    mention.sentiment_prompt_version = llm_sentiment.PROMPT_VERSION
    mention.sentiment_judged_at = when


@pytest.fixture()
def counted_window(no_trial):
    """One quarter-hour with three high-confidence mentions, rolled up."""
    from features.radar import buckets, journal, llm_sentiment
    with flask_app.app_context():
        when = NOW - dt.timedelta(hours=30)
        window = when.replace(minute=(when.minute // 15) * 15, second=0,
                              microsecond=0)
        for n in range(3):
            evidence('%s-w%d' % (PREFIX, n), when + dt.timedelta(minutes=n))
        # A low-confidence event with no mention at all: it belongs to the
        # same window and only the journal remembers it.
        evidence('%s-wlow' % PREFIX, when + dt.timedelta(minutes=3),
                 confidence='low', with_mention=False)
        # roll_up, not rebuild_windows: a rebuild only CORRECTS windows that
        # already have child rows, so nothing would exist to recover into.
        rows = [buckets.MentionRow(
            ticker='ZZT', external_id='%s-w%d' % (PREFIX, n),
            created_utc=when + dt.timedelta(minutes=n), source='bluesky',
            channel='firehose', author='someone%d' % n, simhash=n + 1,
            confidence='high', sentiment=0.2, engagement=0.0)
            for n in range(3)]
        buckets.roll_up(rows, {'bluesky': 'ok'}, {window})
        db.session.commit()
        yield window


def encoder_mentions():
    return (db.session.query(RadarMention)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarPost.external_id.like(PREFIX + '%'),
                    RadarMention.sentiment_model == 'radar-encoder-v1').all())


def test_a_dry_run_reports_and_writes_nothing(counted_window):
    with flask_app.app_context():
        arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()
        before = counted('ZZT', counted_window)

        report = judge_trial.recover_trial(apply=False, now=NOW)

        assert report['applied'] is False
        assert report['total_mentions'] == 3
        assert report['recovered'] == 0
        assert len(encoder_mentions()) == 3          # untouched
        assert counted('ZZT', counted_window) == before
        assert judge_trial.current().status == judge_trial.ARMED


def _our_mentions():
    return (db.session.query(RadarMention)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarPost.external_id.like(PREFIX + '%')).all())


def test_recovery_puts_the_counts_back(counted_window):
    """The whole point: after recovery the bucket reads as it did before
    the encoder ever judged, rebuilt from the complete journal."""
    from features.radar import buckets, llm_sentiment
    with flask_app.app_context():
        before = counted('ZZT', counted_window)
        assert before is not None

        arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()
        from features.radar import journal
        journal.sync_chatter_eligibility(
            [((post.source, post.external_id, mention.ticker),
              llm_sentiment.final_eligibility(mention))
             for mention, post in _pairs()])
        db.session.commit()
        buckets.rebuild_windows([('ZZT', counted_window)])
        removed = counted('ZZT', counted_window)
        assert removed != before, 'the fixture must actually lose counts'

        report = judge_trial.recover_trial(apply=True, now=NOW)

        assert report['recovered'] == 3 and report['remaining'] == 0
        assert counted('ZZT', counted_window) == before


def _pairs():
    return (db.session.query(RadarMention, RadarPost)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarPost.external_id.like(PREFIX + '%')).all())


def test_recovery_returns_mentions_to_the_unjudged_state(counted_window):
    with flask_app.app_context():
        arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()

        judge_trial.recover_trial(apply=True, now=NOW)

        for mention in _our_mentions():
            assert mention.sentiment_relevance is None
            assert mention.sentiment_content_origin is None
            assert mention.sentiment_model is None
            assert mention.sentiment_prompt_version is None
            assert mention.sentiment_judged_at is None
            assert llm_sentiment_module().final_eligibility(mention) is None


def llm_sentiment_module():
    from features.radar import llm_sentiment
    return llm_sentiment


def test_history_survives_recovery(counted_window):
    """It is the evidence of what the trial did. Recovery undoes the
    DECISIONS, not the record of having made them."""
    with flask_app.app_context():
        arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()
        before = RadarSentimentJudgment.query.count()

        judge_trial.recover_trial(apply=True, now=NOW)

        assert RadarSentimentJudgment.query.count() == before


def test_tone_and_its_owner_are_never_cleared(counted_window):
    """The trial did not write them. What is there belongs to whoever did,
    and the board is showing it."""
    with flask_app.app_context():
        arm(now=NOW)
        for mention in _our_mentions():
            mention.sentiment_attitude = 'positive'
            mention.sentiment_expected_move = 'up'
            mention.sentiment_confidence = 'high'
            mention.llm_sentiment = 'bullish'
            mention.sentiment_tone_model = 'claude-haiku-4-5'
            judged_by_encoder(mention, NOW)
        db.session.commit()

        judge_trial.recover_trial(apply=True, now=NOW)

        for mention in _our_mentions():
            assert mention.sentiment_attitude == 'positive'
            assert mention.llm_sentiment == 'bullish'
            assert mention.sentiment_tone_model == 'claude-haiku-4-5'


def test_an_independent_review_winner_is_left_alone(counted_window):
    """A review judged the prepared text itself. Its verdict is not the
    encoder's to withdraw -- it merely sits on a mention the encoder also
    judged."""
    from features.radar import llm_sentiment
    with flask_app.app_context():
        arm(now=NOW)
        mentions = _our_mentions()
        for mention in mentions:
            judged_by_encoder(mention, NOW)
        reviewed = mentions[0]
        reviewed.sentiment_model = 'claude-sonnet-5'
        db.session.add(RadarSentimentJudgment(
            mention_id=reviewed.id, stage='review', model='claude-sonnet-5',
            prompt_version=llm_sentiment.PROMPT_VERSION, relevance='relevant',
            content_origin='human_chatter', attitude='positive',
            expected_move='up', confidence='high', input_tokens=1,
            output_tokens=1, created_utc=NOW))
        db.session.commit()

        report = judge_trial.recover_trial(apply=True, now=NOW)

        assert report['recovered'] == 2
        assert db.session.get(RadarMention, reviewed.id).sentiment_model \
            == 'claude-sonnet-5'


def test_recovery_selects_by_the_trials_frozen_prompt(counted_window):
    """Recovered as the thing it WAS, even if the constants moved after."""
    with flask_app.app_context():
        row = arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()
        row.prompt_version = 'zz-some-other-generation'
        db.session.commit()

        report = judge_trial.recover_trial(apply=True, now=NOW)

        assert report['total_mentions'] == 0
        assert len(encoder_mentions()) == 3          # none matched, none lost


def test_recovery_is_bounded_and_resumable(counted_window):
    with flask_app.app_context():
        arm(now=NOW)
        # Three mentions across three separate windows, so the mention
        # limit can cut between them.
        for index, (mention, post) in enumerate(_pairs()):
            post.created_utc = NOW - dt.timedelta(hours=30, minutes=20 * index)
            judged_by_encoder(mention, NOW)
        db.session.commit()

        first = judge_trial.recover_trial(apply=True, limit=1, now=NOW)
        assert first['recovered'] == 1 and first['remaining'] == 2
        assert judge_trial.current().status != judge_trial.RECOVERED

        second = judge_trial.recover_trial(apply=True, limit=99, now=NOW)
        assert second['recovered'] == 2 and second['remaining'] == 0


def test_the_pin_is_released_only_when_nothing_is_left(counted_window):
    with flask_app.app_context():
        arm(now=NOW)
        for index, (mention, post) in enumerate(_pairs()):
            post.created_utc = NOW - dt.timedelta(hours=30, minutes=20 * index)
            judged_by_encoder(mention, NOW)
        db.session.commit()

        judge_trial.recover_trial(apply=True, limit=1, now=NOW)
        assert judge_trial.retention_floor() is not None

        judge_trial.recover_trial(apply=True, limit=99, now=NOW)
        assert judge_trial.current().status == judge_trial.RECOVERED
        assert judge_trial.retention_floor() is None


def test_recovering_nothing_is_a_success_not_an_error(counted_window):
    with flask_app.app_context():
        arm(now=NOW)
        report = judge_trial.recover_trial(apply=True, now=NOW)
        assert report['recovered'] == 0 and report['remaining'] == 0
        assert judge_trial.current().status == judge_trial.RECOVERED


def test_recovery_without_a_trial_refuses(no_trial):
    with flask_app.app_context():
        with pytest.raises(judge_trial.TrialError):
            judge_trial.recover_trial(apply=True)


def test_a_window_older_than_the_pin_refuses_rather_than_guesses(
        counted_window):
    """Its events are pruned. Rebuilding from what is left would write a
    smaller count than really happened -- into forever-retained history."""
    with flask_app.app_context():
        row = arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()
        row.retain_from = NOW - dt.timedelta(hours=1)   # after the fixture
        db.session.commit()

        with pytest.raises(judge_trial.TrialError):
            judge_trial.recover_trial(apply=True, now=NOW)
        assert len(encoder_mentions()) == 3


@pytest.mark.parametrize('limit', [0, -1])
def test_a_non_positive_limit_is_refused(counted_window, limit):
    with flask_app.app_context():
        arm(now=NOW)
        with pytest.raises(judge_trial.TrialError):
            judge_trial.recover_trial(apply=True, limit=limit)


def test_a_failed_window_leaves_all_of_its_state_untouched(counted_window,
                                                           monkeypatch):
    """The atomicity claim, forced. Everything in the window rolls back
    together -- mention fields, journal flags and bucket totals."""
    from features.radar import buckets
    with flask_app.app_context():
        before = counted('ZZT', counted_window)
        arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()

        real = buckets.rebuild_windows

        def fail_after_promotion(windows, commit=True):
            real(windows, commit=commit)
            raise RuntimeError('crash after promotion, before totals')

        monkeypatch.setattr(buckets, 'rebuild_windows', fail_after_promotion)
        with pytest.raises(RuntimeError):
            judge_trial.recover_trial(apply=True, now=NOW)
        db.session.rollback()

        # Nothing moved: the mentions are still judged and the counts are
        # still what the encoder left them.
        assert len(encoder_mentions()) == 3
        assert counted('ZZT', counted_window) == before


def test_a_dry_run_cannot_write_even_if_it_tried(counted_window):
    """Server-side enforcement, the same shape the extractor diagnostic
    uses: every statement the dry run issues is inspected, and anything
    that is not a read raises. A default that quietly undid ten days of
    production judgments would be the worst possible default, so this asks
    the database rather than trusting the code path.
    """
    import sqlalchemy as sa
    from sqlalchemy import event

    with flask_app.app_context():
        arm(now=NOW)
        for mention in _our_mentions():
            judged_by_encoder(mention, NOW)
        db.session.commit()

        attempted = []

        def read_only(conn, cursor, statement, parameters, context,
                      executemany):
            head = statement.lstrip().split(None, 1)[0].upper()
            if head not in ('SELECT', 'SHOW', 'SET'):
                attempted.append(head)
                raise RuntimeError('dry run attempted %s' % head)

        event.listen(db.engine, 'before_cursor_execute', read_only)
        try:
            with db.session.no_autoflush:
                report = judge_trial.recover_trial(apply=False, now=NOW)
        finally:
            event.remove(db.engine, 'before_cursor_execute', read_only)

        assert attempted == []
        assert report['total_mentions'] == 3
        assert report['recovered'] == 0
        assert judge_trial.current().status == judge_trial.ARMED


def test_an_encoder_verdict_is_recovered_even_beside_a_review_row(
        counted_window):
    """A review HISTORY row is not a review WIN. If the encoder's verdict
    is the one materialized, it is the one in the counts, and leaving it
    there would strand the trial: remaining never reaches zero, so the
    retention pin is never released.
    """
    from features.radar import llm_sentiment
    with flask_app.app_context():
        arm(now=NOW)
        mentions = _our_mentions()
        for mention in mentions:
            judged_by_encoder(mention, NOW)
        # A review answered this mention at some point, but the encoder's
        # verdict is what the mention currently says.
        db.session.add(RadarSentimentJudgment(
            mention_id=mentions[0].id, stage='review', model='claude-sonnet-5',
            prompt_version=llm_sentiment.PROMPT_VERSION, relevance='relevant',
            content_origin='human_chatter', attitude='positive',
            expected_move='up', confidence='high', input_tokens=1,
            output_tokens=1, created_utc=NOW))
        db.session.commit()

        report = judge_trial.recover_trial(apply=True, now=NOW)

        assert report['recovered'] == 3 and report['remaining'] == 0
        assert judge_trial.current().status == judge_trial.RECOVERED


# ---- recording the audit's verdict ------------------------------------------

REPORT_SHA = 'd' * 64


def report_for(row, passed=True):
    return {'passed': passed,
            'trial': {'artifact_sha256': row.artifact_sha256,
                      'prompt_version': row.prompt_version}}


def started(row, when=None):
    """A trial that has actually judged something, so its clock is running."""
    row.first_judged_at = when or NOW
    row.status = judge_trial.RUNNING
    db.session.commit()
    return row


def test_a_passing_audit_is_recorded_and_changes_nothing_else(no_trial):
    """Passing authorises CONTINUING. It does not release the pin, promote
    the backend, or enable tone."""
    with flask_app.app_context():
        row = started(arm())
        judge_trial.accept_audit(report_for(row), REPORT_SHA,
                                 NOW + dt.timedelta(days=8), passed=True)
        row = judge_trial.current()
        assert row.audit_passed is True
        assert row.audit_report_sha256 == REPORT_SHA
        assert row.status == judge_trial.RUNNING
        assert judge_trial.retention_floor() is not None


def test_a_failing_audit_stops_the_trial_without_waiting_to_be_noticed(
        no_trial):
    with flask_app.app_context():
        row = started(arm())
        judge_trial.accept_audit(report_for(row, passed=False), REPORT_SHA,
                                 NOW + dt.timedelta(days=8), passed=False)
        row = judge_trial.current()
        assert row.audit_passed is False
        assert row.status == judge_trial.RECOVERING
        assert 'audit failed' in row.stop_reason


def test_the_same_report_may_be_accepted_twice(no_trial):
    with flask_app.app_context():
        row = started(arm())
        when = NOW + dt.timedelta(days=8)
        judge_trial.accept_audit(report_for(row), REPORT_SHA, when, passed=True)
        judge_trial.accept_audit(report_for(row), REPORT_SHA, when, passed=True)
        assert judge_trial.current().audit_report_sha256 == REPORT_SHA


def test_a_different_report_cannot_replace_a_recorded_result(no_trial):
    """That is how a second opinion quietly becomes the first one."""
    with flask_app.app_context():
        row = started(arm())
        when = NOW + dt.timedelta(days=8)
        judge_trial.accept_audit(report_for(row, passed=False), REPORT_SHA,
                                 when, passed=False)
        with pytest.raises(judge_trial.TrialError):
            judge_trial.accept_audit(report_for(row), 'e' * 64, when,
                                     passed=True)
        assert judge_trial.current().audit_passed is False


@pytest.mark.parametrize('wrong', ['artifact_sha256', 'prompt_version'])
def test_a_report_about_another_trial_is_refused(no_trial, wrong):
    with flask_app.app_context():
        row = started(arm())
        report = report_for(row)
        report['trial'][wrong] = 'something-else'
        with pytest.raises(judge_trial.TrialError):
            judge_trial.accept_audit(report, REPORT_SHA,
                                     NOW + dt.timedelta(days=8), passed=True)
        assert judge_trial.current().audit_evaluated_at is None


def test_a_late_report_cannot_postpone_an_expiry_it_already_missed(no_trial):
    with flask_app.app_context():
        row = started(arm())
        with pytest.raises(judge_trial.TrialError):
            judge_trial.accept_audit(report_for(row), REPORT_SHA,
                                     NOW + dt.timedelta(days=11), passed=True)
        assert judge_trial.current().audit_evaluated_at is None


def test_an_audit_result_needs_its_report_hash(no_trial):
    with flask_app.app_context():
        row = started(arm())
        with pytest.raises(judge_trial.TrialError):
            judge_trial.accept_audit(report_for(row), '', NOW, passed=True)


# ---- the guard --------------------------------------------------------------

def test_the_guard_refuses_when_no_trial_is_armed(no_trial):
    """Without a trial there is no pin holding the evidence recovery would
    need, so judging would be unrecoverable from its first row."""
    with flask_app.app_context():
        with pytest.raises(judge_trial.TrialError):
            judge_trial.guard_encoder_trial(NOW)


def test_the_guard_allows_an_armed_trial_before_its_first_judgment(no_trial):
    with flask_app.app_context():
        arm()
        assert judge_trial.guard_encoder_trial(NOW).status == judge_trial.ARMED


@pytest.mark.parametrize('status', [judge_trial.RECOVERING,
                                    judge_trial.RECOVERED])
def test_a_stopped_trial_may_not_judge(no_trial, status):
    with flask_app.app_context():
        row = arm()
        row.status = status
        db.session.commit()
        with pytest.raises(judge_trial.TrialError):
            judge_trial.guard_encoder_trial(NOW)


def test_the_deadline_runs_from_the_first_judgment_not_from_arming(no_trial):
    """A trial armed and left idle has changed nothing, so it has nothing
    to expire."""
    with flask_app.app_context():
        row = arm()
        assert judge_trial.deadline(row) is None
        judge_trial.guard_encoder_trial(NOW + dt.timedelta(days=30))

        started(row, when=NOW)
        assert judge_trial.deadline(judge_trial.current()) == \
            NOW + dt.timedelta(days=10)


def test_the_guard_refuses_on_the_deadline_itself(no_trial):
    with flask_app.app_context():
        started(arm())
        judge_trial.guard_encoder_trial(NOW + dt.timedelta(days=9, hours=23))
        with pytest.raises(judge_trial.TrialError):
            judge_trial.guard_encoder_trial(NOW + dt.timedelta(days=10))


def test_a_passing_audit_lifts_the_deadline_but_nothing_else(no_trial):
    """The deadline exists because a trial that never tests its own
    acceptance rules is not a trial. One that has tested them and passed
    has answered that, so it keeps running -- still suppressed, still
    pinned, still needing a separate change to be promoted."""
    with flask_app.app_context():
        row = started(arm())
        judge_trial.accept_audit(report_for(row), REPORT_SHA,
                                 NOW + dt.timedelta(days=5), passed=True)

        judge_trial.guard_encoder_trial(NOW + dt.timedelta(days=11))
        assert judge_trial.deadline(judge_trial.current()) is None
        assert judge_trial.retention_floor() is not None
        assert judge_trial.current().status == judge_trial.RUNNING


def test_a_failing_audit_does_not_lift_the_deadline(no_trial):
    with flask_app.app_context():
        row = started(arm())
        judge_trial.accept_audit(report_for(row, passed=False), REPORT_SHA,
                                 NOW + dt.timedelta(days=5), passed=False)
        # ...and it is already recovering, so it may not judge at all.
        with pytest.raises(judge_trial.TrialError):
            judge_trial.guard_encoder_trial(NOW + dt.timedelta(days=6))


def test_an_unevaluated_trial_still_expires_on_day_ten(no_trial):
    with flask_app.app_context():
        started(arm())
        judge_trial.guard_encoder_trial(NOW + dt.timedelta(days=9, hours=23))
        with pytest.raises(judge_trial.TrialError):
            judge_trial.guard_encoder_trial(NOW + dt.timedelta(days=10))




# ---- the write boundary: what the pass locks, and what it may not undo -----

def as_another_process(sql, *params):
    """One committed statement on a connection of its own -- the CLI or the
    timer, whose commits this session's open snapshot cannot see."""
    with db.engine.connect() as other:
        other.exec_driver_sql(sql, params)
        other.commit()


@pytest.mark.parametrize('moved', ['prompt', 'model'])
def test_the_guard_refuses_when_the_code_no_longer_matches_the_armed_trial(
        no_trial, monkeypatch, moved):
    """The row froze WHAT was tried. If the prompt version or model id in
    the code has moved since, writes would be stamped with the new one and
    recovery -- which selects by the frozen one -- would never find them.
    That is a different trial, and it needs its own arming."""
    from features.radar import judge_backends, llm_sentiment
    with flask_app.app_context():
        arm()
        if moved == 'prompt':
            monkeypatch.setattr(llm_sentiment, 'PROMPT_VERSION', 'zz-moved')
        else:
            monkeypatch.setattr(judge_backends, 'ENCODER_MODEL_ID',
                                'radar-encoder-v2')
        with pytest.raises(judge_trial.TrialError) as caught:
            judge_trial.guard_encoder_trial(NOW)
        assert 'armed' in str(caught.value)


@pytest.mark.parametrize('status', [judge_trial.RECOVERING,
                                    judge_trial.RECOVERED])
def test_a_first_judgment_cannot_resurrect_a_stopped_trial(no_trial, status):
    """`recovered` -> `running` would re-pin evidence that may already be
    pruned and restart a trial nobody armed."""
    with flask_app.app_context():
        row = arm()
        row.status = status
        db.session.commit()
        with pytest.raises(judge_trial.TrialError):
            judge_trial.lock_for_write(NOW)
        db.session.rollback()
        assert judge_trial.current().status == status
        assert judge_trial.current().first_judged_at is None


@pytest.mark.parametrize('status', [judge_trial.RECOVERING,
                                    judge_trial.RECOVERED])
def test_the_clock_itself_refuses_to_start_a_stopped_trial(no_trial, status):
    """The boundary refuses first; this is the second line, tested on its
    own so that a caller who reached the clock some other way cannot turn
    `recovered` back into `running`."""
    with flask_app.app_context():
        row = arm()
        row.status = status
        db.session.commit()
        with pytest.raises(judge_trial.TrialError):
            judge_trial.note_first_judgment(row, NOW)
        assert row.status == status
        assert row.first_judged_at is None


def test_the_write_lock_reads_the_row_as_it_is_now_not_as_it_was(no_trial):
    """The session has the row in memory as `armed`. Another process stops
    the trial. A re-read that answers from the identity map -- or from the
    transaction's repeatable-read snapshot -- still says `armed`; only a
    locking read says what is true."""
    with flask_app.app_context():
        arm()
        assert judge_trial.current().status == judge_trial.ARMED   # cached
        as_another_process('UPDATE radar_judge_trial SET status = %s '
                           'WHERE id = 1', judge_trial.RECOVERING)
        with pytest.raises(judge_trial.TrialError):
            judge_trial.lock_for_write(NOW)
        db.session.rollback()


def test_the_write_lock_starts_the_clock_once_and_only_from_armed(no_trial):
    with flask_app.app_context():
        arm()
        row = judge_trial.lock_for_write(NOW)
        judge_trial.note_first_judgment(row, NOW)
        db.session.commit()
        assert judge_trial.current().status == judge_trial.RUNNING
        first = judge_trial.current().first_judged_at
        assert first == NOW

        row = judge_trial.lock_for_write(NOW + dt.timedelta(days=3))
        judge_trial.note_first_judgment(row, NOW + dt.timedelta(days=3))
        db.session.commit()
        assert judge_trial.current().first_judged_at == first


def test_the_write_side_refuses_a_post_outside_the_retained_interval(
        no_trial):
    """Selection keeps such posts out; this is the check that holds even if
    selection did not (spec §7.2a: batches outside the retained interval
    are refused)."""
    from types import SimpleNamespace
    with flask_app.app_context():
        row = arm()
        inside = SimpleNamespace(created_utc=row.retain_from)
        outside = SimpleNamespace(
            created_utc=row.retain_from - dt.timedelta(minutes=1))
        judge_trial.refuse_outside_retention(row, [inside])
        with pytest.raises(judge_trial.TrialError):
            judge_trial.refuse_outside_retention(row, [inside, outside])
