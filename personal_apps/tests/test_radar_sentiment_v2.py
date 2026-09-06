# personal_apps/tests/test_radar_sentiment_v2.py
"""Sentiment v2: structured judgment, storage, routing (spec 2026-08-31)."""
import hashlib
import json

from features.radar import judge_backends, llm_sentiment, sentiment_input
from features.radar.llm_sentiment import (
    ATTITUDE, CONFIDENCE, CONTENT_ORIGIN, EXPECTED_MOVE, RELEVANCE,
    JudgeItem, Judgment, legacy_projection)
# judge_v2 takes the plain name when Task 6 retires the v1 pass; these
# tests already exercise the final calling convention.
from features.radar.llm_sentiment import judge_v2 as judge


class FakeResponse:
    def __init__(self, text, stop_reason='end_turn', usage=None):
        self.content = [type('Block', (), {'type': 'text', 'text': text})()]
        self.stop_reason = stop_reason
        self.usage = usage


class FakeMessages:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeClient:
    def __init__(self, answers):
        self.messages = FakeMessages(answers)


def prepared(text='great company, buying more', ticker='ZZA',
             source='bluesky', title=None):
    return sentiment_input.prepare_sentiment_input(
        source, title, text, ticker, author='a1', channel='c1')


def jitem(key, **kwargs):
    item = JudgeItem()
    item.key, item.prepared = key, prepared(**kwargs)
    return item


def answer(entries, usage=None):
    return FakeResponse(json.dumps({'verdicts': entries}), usage=usage)


def full(n, relevance='relevant', origin='human_chatter', attitude='positive',
         move='up', confidence='high'):
    return {'n': n, 'relevance': relevance, 'content_origin': origin,
            'attitude': attitude, 'expected_move': move,
            'confidence': confidence}


class FakeBackend:
    """A backend with no vendor inside it.

    What the pipeline does with an answer -- validate it, split the batch's
    tokens over it, store it, let review outrank primary -- is the same
    whoever answered. These tests answer directly, so a change to the
    Anthropic request shape can never make them pass or fail.

    `answers` is one entry per batch: {item.key: Judgment} for what came
    back, or an exception to raise instead.
    """

    supports_review = True

    def __init__(self, answers, id='zz-fake-backend', batch_size=20,
                 pass_limit=400, usage=None):
        self.id = id
        self.batch_size = batch_size
        self.pass_limit = pass_limit
        self.answers = list(answers)
        self.usage = usage if usage is not None else judge_backends.Usage(0, 0)
        self.batches = []

    def judge_batch(self, batch, *, preamble=None):
        self.batches.append((list(batch), preamble))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return dict(answer), self.usage


def jm(relevance='relevant', origin='human_chatter', attitude='positive',
       move='up', confidence='high'):
    return Judgment(relevance, origin, attitude, move, confidence)


def test_judge_returns_what_the_backend_answered():
    backend = FakeBackend([{7: jm()}])
    got = judge([jitem(7)], backend)
    assert set(got) == {7}
    assert got[7].judgment.attitude == 'positive'


def test_a_value_outside_the_enums_is_discarded_whoever_said_it():
    """Validation is the pipeline's boundary, not the adapter's -- so it
    holds for a backend that never saw the schema at all."""
    backend = FakeBackend([{1: jm(attitude='bullish')}])
    assert judge([jitem(1)], backend) == {}


def test_a_partial_answer_is_discarded_not_defaulted():
    backend = FakeBackend([{1: Judgment('relevant', None, 'positive',
                                        'up', 'high')}])
    assert judge([jitem(1)], backend) == {}


def test_an_unavailable_batch_leaves_its_items_unjudged():
    backend = FakeBackend([llm_sentiment.SentimentUnavailable('nope')])
    assert judge([jitem(1), jitem(2)], backend) == {}


def test_one_failed_batch_does_not_cost_the_others():
    backend = FakeBackend([llm_sentiment.SentimentUnavailable('nope'),
                           {2: jm()}], batch_size=1)
    got = judge([jitem(1), jitem(2)], backend)
    assert set(got) == {2}


def test_items_are_batched_at_the_backends_size():
    backend = FakeBackend([{1: jm()}, {2: jm()}, {3: jm()}], batch_size=1)
    judge([jitem(1), jitem(2), jitem(3)], backend)
    assert [len(batch) for batch, _preamble in backend.batches] == [1, 1, 1]

    backend = FakeBackend([{1: jm(), 2: jm(), 3: jm()}], batch_size=20)
    judge([jitem(1), jitem(2), jitem(3)], backend)
    assert [len(batch) for batch, _preamble in backend.batches] == [3]


def test_batch_usage_is_split_across_its_answers():
    backend = FakeBackend([{1: jm(), 2: jm()}],
                          usage=judge_backends.Usage(100, 21))
    got = judge([jitem(1), jitem(2)], backend)
    assert got[1].input_tokens + got[2].input_tokens == 100
    assert got[1].output_tokens + got[2].output_tokens == 21


def test_usage_is_split_over_what_survived_validation():
    """A batch where the model answered one item and botched another must
    attribute all of its tokens to the item that was stored."""
    backend = FakeBackend([{1: jm(), 2: jm(confidence='very')}],
                          usage=judge_backends.Usage(100, 20))
    got = judge([jitem(1), jitem(2)], backend)
    assert set(got) == {1}
    assert (got[1].input_tokens, got[1].output_tokens) == (100, 20)


def test_a_tokenless_backend_costs_nothing_and_still_answers():
    backend = FakeBackend([{1: jm()}], id='radar-encoder-v1')
    got = judge([jitem(1)], backend)
    assert (got[1].input_tokens, got[1].output_tokens) == (0, 0)


def test_the_preamble_reaches_the_backend_only_when_given():
    backend = FakeBackend([{1: jm()}, {1: jm()}], batch_size=20)
    judge([jitem(1)], backend)
    judge([jitem(1)], backend, preamble=llm_sentiment.REVIEW_PREAMBLE)
    assert [preamble for _batch, preamble in backend.batches] ==         [None, llm_sentiment.REVIEW_PREAMBLE]


def test_no_items_asks_the_backend_nothing():
    backend = FakeBackend([])
    assert judge([], backend) == {}
    assert backend.batches == []





def test_the_binding_prompt_is_byte_exact():
    # Exact hash of the spec §5.2.1 fenced block (trailing newline
    # stripped). ANY drift -- a reflowed line, a "harmless" word -- fails
    # here and forces a new prompt version instead.
    digest = hashlib.sha256(
        llm_sentiment._INSTRUCTIONS_V2.encode('utf-8')).hexdigest()
    assert digest == \
        'c762061d47848abe454a8545e91ab55de80bf175bee7ccba6bca2853e3b5f4f1'
    assert llm_sentiment.PROMPT_VERSION == \
        'radar-sentiment-v2-attitude-origin-candidate-1'


def test_the_binding_schema_is_canonically_exact():
    canon = json.dumps(llm_sentiment.V2_SCHEMA, sort_keys=True,
                       separators=(',', ':'))
    assert hashlib.sha256(canon.encode('utf-8')).hexdigest() == \
        '6c0fb71b60b903995f9045985e27aa3545aa94b2108ee52f1355dafe502b12c0'


def test_the_schema_is_the_binding_enum_set():
    schema = llm_sentiment.V2_SCHEMA
    props = schema['properties']['verdicts']['items']['properties']
    assert tuple(props['relevance']['enum']) == RELEVANCE
    assert tuple(props['content_origin']['enum']) == CONTENT_ORIGIN
    assert tuple(props['attitude']['enum']) == ATTITUDE
    assert tuple(props['expected_move']['enum']) == EXPECTED_MOVE
    assert tuple(props['confidence']['enum']) == CONFIDENCE
    assert props.keys() >= {'n'}










def test_legacy_projection_matches_the_spec_table():
    def j(relevance='relevant', origin='human_chatter', attitude='none'):
        return Judgment(relevance=relevance, content_origin=origin,
                        attitude=attitude, expected_move='unknown',
                        confidence='high')
    assert legacy_projection(j(relevance='irrelevant')) == 'unclear'
    assert legacy_projection(j(relevance='uncertain')) == 'unclear'
    assert legacy_projection(j(origin='broadcast_or_automated')) == 'unclear'
    assert legacy_projection(j(origin='uncertain')) == 'unclear'
    assert legacy_projection(j(attitude='positive')) == 'bullish'
    assert legacy_projection(j(attitude='negative')) == 'bearish'
    assert legacy_projection(j(attitude='mixed')) == 'neutral'
    assert legacy_projection(j(attitude='none')) == 'unclear'


# --- Storage: history, materialization, projection (Task 4) -----------------

import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarMention, RadarPost, RadarSentimentJudgment

# Future-dated: these suites run against the real local development
# database with no transactional isolation, and pending_v2 returns
# newest-first.
NOW = dt.datetime(2027, 1, 1, 12, 0, 0)


@pytest.fixture()
def clean_posts():
    with flask_app.app_context():
        RadarPost.query.filter(RadarPost.external_id.like('zztest%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarPost.query.filter(RadarPost.external_id.like('zztest%')).delete(
            synchronize_session=False)
        db.session.commit()


def make_post(external_id, ticker='ZZA', confidence='high',
              llm=None, body='ZZA ripping'):
    post = RadarPost(source='bluesky', external_id=external_id,
                     channel='firehose', author='someone', created_utc=NOW,
                     title=None, body=body, first_seen=NOW, last_seen=NOW)
    db.session.add(post)
    db.session.flush()
    mention = RadarMention(post_id=post.id, ticker=ticker,
                           confidence=confidence, lexicon_sentiment=0.25,
                           llm_sentiment=llm)
    db.session.add(mention)
    db.session.commit()
    return mention.id


def rows_for(mention_ids):
    return (db.session.query(RadarMention, RadarPost)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.id.in_(list(mention_ids))).all())


def ja(relevance='relevant', origin='human_chatter', attitude='positive',
       move='up', confidence='high', input_tokens=40, output_tokens=7):
    return llm_sentiment.JudgedAnswer(
        judgment=Judgment(relevance, origin, attitude, move, confidence),
        input_tokens=input_tokens, output_tokens=output_tokens)


def test_apply_writes_history_final_fields_and_projection(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-v2-a', body='love it, calls')
        written = llm_sentiment.apply_judgments(
            rows_for([mention_id]), {mention_id: ja()},
            stage='primary', model='claude-haiku-4-5')
        db.session.commit()      # apply never commits; the caller owns it
        assert written == 1
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'positive'
        assert m.sentiment_relevance == 'relevant'
        assert m.llm_sentiment == 'bullish'          # projection
        assert m.sentiment_model == 'claude-haiku-4-5'
        assert m.sentiment_prompt_version == llm_sentiment.PROMPT_VERSION
        assert m.sentiment_judged_at is not None
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).all()
        assert len(history) == 1 and history[0].stage == 'primary'
        assert history[0].input_tokens == 40


def test_review_overwrites_primary_but_not_vice_versa(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-v2-b')
        rows = rows_for([mention_id])
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='positive')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='negative', move='down')},
            stage='review', model=llm_sentiment.REVIEW_MODEL)
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='positive')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'negative'    # review still stands
        assert m.sentiment_model == llm_sentiment.REVIEW_MODEL
        assert m.llm_sentiment == 'bearish'
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).order_by(RadarSentimentJudgment.id).all()
        assert [h.stage for h in history] == ['primary', 'review', 'primary']


# --- Stage is a fact in the history, not an inference from the model id ----
#
# apply_judgments and review_candidates both used to read STAGE off the
# mention's model column: `sentiment_model == REVIEW_MODEL` meant "a review
# stands here", `== PRIMARY_MODEL` meant "this was judged by the primary".
# That is only right while the two backends happen to carry different ids,
# which is a fact about today's configuration and not about the pipeline.
# It fails silently in both directions -- a standing review overwritten by a
# later primary pass, or rows judged by a previous primary id dropping out of
# the review pool -- and the suite stayed green because every existing test
# uses two different fake ids. radar_sentiment_judgments.stage already holds
# the truth; these tests ask it.

import contextlib

import sqlalchemy as sa

# Deliberately neither PRIMARY_MODEL nor REVIEW_MODEL: one backend serving
# both roles is exactly the configuration the model-id proxy cannot express.
SAME_BACKEND = 'zz-same-backend'


@contextlib.contextmanager
def history_selects():
    """Collect SELECTs issued against radar_sentiment_judgments in the block.

    The stage lookup must be ONE query for the whole batch. A per-row
    version would pass every correctness test here and quietly turn a
    400-mention pass into 400 extra round trips.
    """
    seen = []

    def before(conn, cursor, statement, parameters, context, executemany):
        text = ' '.join(statement.split()).lower()
        if text.startswith('select') and 'radar_sentiment_judgments' in text:
            seen.append(text)

    sa.event.listen(db.engine, 'before_cursor_execute', before)
    try:
        yield seen
    finally:
        sa.event.remove(db.engine, 'before_cursor_execute', before)


def test_a_standing_review_survives_a_later_primary_from_the_same_id(
        clean_posts):
    """The identical-id case the old predicate could not express."""
    with flask_app.app_context():
        mention_id = make_post('zztest-stage-same')
        rows = rows_for([mention_id])
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='positive')},
            stage='primary', model=SAME_BACKEND)
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='negative', move='down')},
            stage='review', model=SAME_BACKEND)
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='positive')},
            stage='primary', model=SAME_BACKEND)
        db.session.commit()

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'negative'    # the review still stands
        assert m.sentiment_expected_move == 'down'
        assert m.llm_sentiment == 'bearish'
        # History is append-only and records the blocked pass too: the
        # guard governs materialization, never the evidence.
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).order_by(RadarSentimentJudgment.id).all()
        assert [h.stage for h in history] == ['primary', 'review', 'primary']
        assert [h.model for h in history] == [SAME_BACKEND] * 3


def test_two_primaries_under_the_review_id_do_not_protect_each_other(
        clean_posts):
    """The opposite false positive: a primary must never protect itself
    just because it was written by the model that usually reviews."""
    with flask_app.app_context():
        mention_id = make_post('zztest-stage-selfprot')
        rows = rows_for([mention_id])
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='positive')},
            stage='primary', model=llm_sentiment.REVIEW_MODEL)
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='negative', move='down')},
            stage='primary', model=llm_sentiment.REVIEW_MODEL)
        db.session.commit()

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'negative'    # the second one won
        assert m.llm_sentiment == 'bearish'


def test_another_mentions_review_cannot_protect_this_one(clean_posts):
    """Scoped to the mention. A batch lookup that answered 'some row in
    this batch has been reviewed' would pass every single-row test."""
    with flask_app.app_context():
        reviewed_id = make_post('zztest-stage-neighbour-r')
        plain_id = make_post('zztest-stage-neighbour-p')
        llm_sentiment.apply_judgments(
            rows_for([reviewed_id]), {reviewed_id: ja(attitude='negative',
                                                      move='down')},
            stage='review', model=llm_sentiment.REVIEW_MODEL)
        db.session.commit()

        both = rows_for([reviewed_id, plain_id])
        llm_sentiment.apply_judgments(
            both, {reviewed_id: ja(attitude='positive'),
                   plain_id: ja(attitude='positive')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()

        assert db.session.get(
            RadarMention, reviewed_id).sentiment_attitude == 'negative'
        assert db.session.get(
            RadarMention, plain_id).sentiment_attitude == 'positive'


def test_an_older_prompt_generations_review_does_not_protect(clean_posts):
    """Scoped to the CURRENT prompt version, not to 'the latest history
    row', which answers a different question."""
    with flask_app.app_context():
        mention_id = make_post('zztest-stage-oldprompt')
        db.session.add(RadarSentimentJudgment(
            mention_id=mention_id, stage='review',
            model=llm_sentiment.REVIEW_MODEL,
            prompt_version='radar-sentiment-v2-retired-generation',
            relevance='relevant', content_origin='human_chatter',
            attitude='negative', expected_move='down', confidence='high',
            input_tokens=0, output_tokens=0, created_utc=NOW))
        db.session.commit()

        llm_sentiment.apply_judgments(
            rows_for([mention_id]), {mention_id: ja(attitude='positive')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'positive'
        assert m.sentiment_prompt_version == llm_sentiment.PROMPT_VERSION


def test_the_review_lookup_sees_an_uncommitted_review(clean_posts):
    """Both passes run inside one open transaction in production. A review
    written but not yet committed must already protect its mention."""
    with flask_app.app_context():
        mention_id = make_post('zztest-stage-uncommitted')
        rows = rows_for([mention_id])
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='negative', move='down')},
            stage='review', model=llm_sentiment.REVIEW_MODEL)
        # No commit here, deliberately.
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(attitude='positive')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'negative'


def test_the_stage_lookup_is_one_query_for_the_whole_batch(clean_posts):
    with flask_app.app_context():
        ids = [make_post('zztest-stage-bulk-%d' % n) for n in range(3)]
        rows = rows_for(ids)
        answers = {mention_id: ja() for mention_id in ids}
        with history_selects() as seen:
            llm_sentiment.apply_judgments(
                rows, answers, stage='primary',
                model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        assert len(seen) == 1, seen

        # A review pass has no standing review to respect -- review always
        # wins -- so it asks nothing at all.
        with history_selects() as seen:
            llm_sentiment.apply_judgments(
                rows, answers, stage='review',
                model=llm_sentiment.REVIEW_MODEL)
        db.session.commit()
        assert seen == []


def test_a_previous_primary_id_stays_eligible_for_review(clean_posts,
                                                         own_candidates):
    """The review pool is 'judged, not yet reviewed at this prompt
    version'. Which backend produced the primary answer is irrelevant to
    that question, and filtering on it silently emptied the pool after a
    backend change."""
    with flask_app.app_context():
        old_id = make_post('zztest-stage-oldbackend')
        llm_sentiment.apply_judgments(
            rows_for([old_id]), {old_id: ja(confidence='low')},
            stage='primary', model='claude-haiku-4-4-retired')
        db.session.commit()

        got = [mention.id for mention, _post
               in llm_sentiment.review_candidates(NOW)]
        assert old_id in got


def test_a_standing_review_leaves_the_pool_whatever_id_wrote_it(
        clean_posts, own_candidates):
    with flask_app.app_context():
        mention_id = make_post('zztest-stage-reviewed-same')
        rows = rows_for([mention_id])
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(confidence='low')},
            stage='primary', model=SAME_BACKEND)
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(confidence='low')},
            stage='review', model=SAME_BACKEND)
        db.session.commit()

        got = [mention.id for mention, _post
               in llm_sentiment.review_candidates(NOW)]
        assert mention_id not in got


def test_an_unjudged_mention_stays_null(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-v2-c')
        written = llm_sentiment.apply_judgments(
            rows_for([mention_id]), {}, stage='primary',
            model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        assert written == 0
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude is None
        assert m.sentiment_judged_at is None
        assert RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).count() == 0


def test_final_eligibility_maps_the_materialized_fields(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-v2-d')
        rows = rows_for([mention_id])
        m = rows[0][0]
        assert llm_sentiment.final_eligibility(m) is None   # unjudged

        cases = [
            (ja(relevance='irrelevant', attitude='none', move='unknown'), False),
            (ja(origin='broadcast_or_automated'), False),
            (ja(), True),
            (ja(relevance='uncertain'), None),
            (ja(origin='uncertain'), None),
        ]
        for answer_, expected in cases:
            llm_sentiment.apply_judgments(rows, {mention_id: answer_},
                                          stage='review',
                                          model=llm_sentiment.REVIEW_MODEL)
            db.session.commit()
            assert llm_sentiment.final_eligibility(m) is expected, answer_


def test_a_sonnet_reversal_restores_eligibility(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-v2-e')
        rows = rows_for([mention_id])
        m = rows[0][0]
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja(relevance='irrelevant', attitude='none',
                                  move='unknown')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        assert llm_sentiment.final_eligibility(m) is False
        llm_sentiment.apply_judgments(
            rows, {mention_id: ja()}, stage='review',
            model=llm_sentiment.REVIEW_MODEL)
        db.session.commit()
        assert llm_sentiment.final_eligibility(m) is True


def test_pending_v2_targets_unjudged_v2_not_legacy(clean_posts):
    with flask_app.app_context():
        legacy_only = make_post('zztest-v2-f', llm='bullish')
        judged = make_post('zztest-v2-g')
        llm_sentiment.apply_judgments(
            rows_for([judged]), {judged: ja()}, stage='primary',
            model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        # pending() is the activated v2 selection (pending_v2 aliases it):
        # keyed on sentiment_judged_at, so a legacy verdict does not hide
        # an unjudged row, and a judged row never comes back.
        waiting = {mention.id for mention, _post
                   in llm_sentiment.pending(50)}
        assert legacy_only in waiting
        assert judged not in waiting


# --- Review routing, priorities, ceiling meter (Task 7) ---------------------

from models import RadarReviewMeter


def _j(relevance='relevant', origin='human_chatter', attitude='positive',
       move='up', confidence='high'):
    return Judgment(relevance, origin, attitude, move, confidence)


def test_the_five_triggers_and_only_those():
    assert llm_sentiment.needs_review(_j(confidence='low'), 0.0)
    assert llm_sentiment.needs_review(_j(relevance='uncertain'), 0.0)
    assert llm_sentiment.needs_review(_j(origin='uncertain'), 0.0)
    assert llm_sentiment.needs_review(_j(attitude='positive', move='down'), 0.0)
    # polarity-only cases pin move='down' so the attitude/move rule stays out
    assert llm_sentiment.needs_review(_j(attitude='negative', move='down'), 0.6)
    assert not llm_sentiment.needs_review(_j(), 0.0)
    assert not llm_sentiment.needs_review(_j(), 0.6)      # agreeing local
    assert not llm_sentiment.needs_review(
        _j(attitude='negative', move='down'), 0.3)        # weak local


def test_priority_order_matches_the_spec():
    uncertain = llm_sentiment.review_priority(_j(relevance='uncertain'), 0.0)
    polarity = llm_sentiment.review_priority(
        _j(attitude='negative', move='down'), 0.6)
    low = llm_sentiment.review_priority(_j(confidence='low'), 0.0)
    conflict = llm_sentiment.review_priority(
        _j(attitude='positive', move='down'), 0.0)
    assert uncertain < polarity < low < conflict


@pytest.fixture()
def clean_meter():
    with flask_app.app_context():
        RadarReviewMeter.query.filter(
            RadarReviewMeter.day >= dt.date(2027, 1, 1)).delete(
                synchronize_session=False)
        db.session.commit()
        yield
        RadarReviewMeter.query.filter(
            RadarReviewMeter.day >= dt.date(2027, 1, 1)).delete(
                synchronize_session=False)
        db.session.commit()


def test_meter_upserts_per_day(clean_meter):
    with flask_app.app_context():
        llm_sentiment._meter_add(dt.date(2027, 1, 1), demanded=3)
        llm_sentiment._meter_add(dt.date(2027, 1, 1), attempted=2, served=2,
                                 capped=1)
        row = db.session.get(RadarReviewMeter, dt.date(2027, 1, 1))
        assert (row.demanded, row.attempted, row.served, row.capped) \
            == (3, 2, 2, 1)


def test_review_candidates_orders_by_priority_and_skips_reviewed(clean_posts):
    with flask_app.app_context():
        # Three judged mentions with different trigger shapes, one already
        # reviewed at this prompt version.
        low_conf = make_post('zztest-rc-low')
        uncertain = make_post('zztest-rc-unc')
        reviewed = make_post('zztest-rc-done')
        untriggered = make_post('zztest-rc-none')
        llm_sentiment.apply_judgments(
            rows_for([low_conf]), {low_conf: ja(confidence='low')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        llm_sentiment.apply_judgments(
            rows_for([uncertain]), {uncertain: ja(relevance='uncertain')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        llm_sentiment.apply_judgments(
            rows_for([reviewed]), {reviewed: ja(confidence='low')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        llm_sentiment.apply_judgments(
            rows_for([reviewed]), {reviewed: ja()},
            stage='review', model=llm_sentiment.REVIEW_MODEL)
        llm_sentiment.apply_judgments(
            rows_for([untriggered]), {untriggered: ja()},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()

        got = [mention.id for mention, _post
               in llm_sentiment.review_candidates(NOW)]
        ours = [i for i in got
                if i in {low_conf, uncertain, reviewed, untriggered}]
        assert ours == [uncertain, low_conf]


# --- The Sonnet review pass (Task 8) ----------------------------------------

def sentinel_backend():
    """A backend whose every use fails the test: proves no call was made."""
    class Boom(FakeBackend):
        def judge_batch(self, batch, *, preamble=None):
            raise AssertionError('the review pass must not judge here')
    return Boom([], id=llm_sentiment.REVIEW_MODEL)


def review_backend_over(answers):
    """The real Sonnet adapter over a fake transport.

    The review tests that survive here assert on stored fields, meters and
    -- in one case -- the exact prompt bytes that prove the review is an
    INDEPENDENT judgment. That last one needs the real request, so these
    keep the adapter and fake only the HTTP client.
    """
    client = FakeClient(answers)
    backend = judge_backends.AnthropicBackend(
        llm_sentiment.REVIEW_MODEL, effort='low', client=client)
    return backend, client


@pytest.fixture()
def clean_meter_all():
    """Empty meter for exact-count assertions, WITHOUT destroying real
    operational history on the shared dev database: existing rows are
    snapshotted and restored (Codex final review, finding 10)."""
    with flask_app.app_context():
        snapshot = [{'day': row.day, 'demanded': row.demanded,
                     'attempted': row.attempted, 'served': row.served,
                     'capped': row.capped}
                    for row in RadarReviewMeter.query.all()]
        RadarReviewMeter.query.delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarReviewMeter.query.delete(synchronize_session=False)
        for row in snapshot:
            db.session.add(RadarReviewMeter(**row))
        db.session.commit()


@pytest.fixture()
def own_candidates(monkeypatch):
    """Scope the review scan to this suite's fixtures.

    The dev database is shared and now carries REAL v2 judgments (a live
    daemon ran locally on 2026-08-31); the recency scan would otherwise
    pull those into demand counts and ceiling math. The wrapper keeps the
    production query, ordering, and triggers under test and drops only
    foreign rows -- the same own-your-rows discipline every suite here
    uses.
    """
    real = llm_sentiment.review_candidates

    def scoped(now, limit=llm_sentiment.PASS_LIMIT):
        return [(mention, post) for mention, post in real(now, limit)
                if post.external_id.startswith('zztest')]

    monkeypatch.setattr(llm_sentiment, 'review_candidates', scoped)


def primary_judged(external_id, confidence='low'):
    """A mention with a primary judgment whose confidence triggers review."""
    mention_id = make_post(external_id)
    llm_sentiment.apply_judgments(
        rows_for([mention_id]), {mention_id: ja(confidence=confidence)},
        stage='primary', model=llm_sentiment.PRIMARY_MODEL)
    db.session.commit()
    return mention_id


def test_review_pass_is_off_without_the_flag(clean_posts, clean_meter_all,
                                             own_candidates, monkeypatch):
    monkeypatch.delenv('RADAR_SONNET_REVIEW', raising=False)
    with flask_app.app_context():
        primary_judged('zztest-rv-off')
        assert llm_sentiment.run_review_pass(backend=sentinel_backend()) == 0
        assert RadarReviewMeter.query.count() == 0


def test_shadow_mode_meters_but_never_calls(clean_posts, clean_meter_all,
                                            own_candidates, monkeypatch):
    monkeypatch.setenv('RADAR_SONNET_REVIEW', 'shadow')
    with flask_app.app_context():
        mention_id = primary_judged('zztest-rv-shadow')
        assert llm_sentiment.run_review_pass(backend=sentinel_backend()) == 0
        row = RadarReviewMeter.query.one()
        assert row.demanded == 1 and row.attempted == 0 and row.served == 0
        m = db.session.get(RadarMention, mention_id)
        assert m.review_requested_at is not None


def test_demand_is_counted_once_across_passes(clean_posts, clean_meter_all,
                                              own_candidates, monkeypatch):
    monkeypatch.setenv('RADAR_SONNET_REVIEW', 'shadow')
    with flask_app.app_context():
        primary_judged('zztest-rv-once')
        llm_sentiment.run_review_pass(backend=sentinel_backend())
        llm_sentiment.run_review_pass(backend=sentinel_backend())
        row = RadarReviewMeter.query.one()
        assert row.demanded == 1


def test_the_ceiling_caps_on_attempted_and_priority_wins(
        clean_posts, clean_meter_all, own_candidates, monkeypatch):
    monkeypatch.setenv('RADAR_SONNET_REVIEW', 'true')
    with flask_app.app_context():
        # Two candidates, ceiling budget for one: the higher-priority
        # (uncertain relevance) is served, the low-confidence one is capped.
        low_conf = primary_judged('zztest-rv-cap-a', confidence='low')
        uncertain = make_post('zztest-rv-cap-b')
        llm_sentiment.apply_judgments(
            rows_for([uncertain]), {uncertain: ja(relevance='uncertain')},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        # Pin the fixture arithmetic: 2 primary judgments, share 0.5 ->
        # budget for exactly one. _primary_count is the seam so the real
        # daemon's history cannot move `allowed`.
        monkeypatch.setattr(llm_sentiment, '_primary_count', lambda day: 2)
        monkeypatch.setattr(llm_sentiment.config, 'REVIEW_DAILY_SHARE', 0.5)
        backend, client = review_backend_over([answer([full(1)])])
        served = llm_sentiment.run_review_pass(backend=backend)
        assert served == 1
        row = RadarReviewMeter.query.one()
        assert row.demanded == 2 and row.attempted == 1
        assert row.served == 1 and row.capped == 1
        assert db.session.get(RadarMention,
                              uncertain).sentiment_model \
            == llm_sentiment.REVIEW_MODEL
        assert db.session.get(RadarMention,
                              low_conf).sentiment_model \
            == llm_sentiment.PRIMARY_MODEL


def test_a_failed_sonnet_call_meters_attempted_but_not_served(
        clean_posts, clean_meter_all, own_candidates, monkeypatch):
    monkeypatch.setenv('RADAR_SONNET_REVIEW', '1')
    monkeypatch.setattr(llm_sentiment, '_primary_count', lambda day: 10)
    monkeypatch.setattr(llm_sentiment.config, 'REVIEW_DAILY_SHARE', 1.0)
    with flask_app.app_context():
        mention_id = primary_judged('zztest-rv-fail')
        backend, client = review_backend_over(
            [FakeResponse('not json at all')])
        assert llm_sentiment.run_review_pass(backend=backend) == 0
        row = RadarReviewMeter.query.one()
        assert row.attempted == 1 and row.served == 0
        # The invalid answer preserved the Haiku final result untouched.
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_model == llm_sentiment.PRIMARY_MODEL
        assert RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id, stage='review').count() == 0


def test_sonnet_result_overwrites_and_carries_the_preamble(
        clean_posts, clean_meter_all, own_candidates, monkeypatch):
    monkeypatch.setenv('RADAR_SONNET_REVIEW', 'true')
    monkeypatch.setattr(llm_sentiment, '_primary_count', lambda day: 10)
    monkeypatch.setattr(llm_sentiment.config, 'REVIEW_DAILY_SHARE', 1.0)
    with flask_app.app_context():
        mention_id = primary_judged('zztest-rv-serve')
        backend, client = review_backend_over(
            [answer([full(1, attitude='negative', move='down')])])
        assert llm_sentiment.run_review_pass(backend=backend) == 1
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'negative'
        assert m.sentiment_model == llm_sentiment.REVIEW_MODEL
        assert m.llm_sentiment == 'bearish'
        prompt = client.messages.requests[0]['messages'][0]['content']
        # INDEPENDENCE, proven against HAND-BUILT bytes: preamble +
        # binding instructions + one literally-spelled item, assembled
        # here without calling the production serializer -- a regression
        # in _prompt_v2 cannot rewrite both sides of this assertion
        # (Codex final review, finding 8).
        item_literal = (
            '<item n="1">\n'
            '<target_ticker>ZZA</target_ticker>\n'
            '<source>bluesky</source>\n'
            '<author>someone</author>\n'
            '<channel>firehose</channel>\n'
            '<content_type>submission</content_type>\n'
            '<post>ZZA ripping</post>\n'
            '</item>')
        expected = (llm_sentiment.REVIEW_PREAMBLE
                    + llm_sentiment._INSTRUCTIONS_V2
                    + '\n\n' + item_literal)
        assert prompt == expected
        assert client.messages.requests[0]['model'] \
            == llm_sentiment.REVIEW_MODEL
        assert client.messages.requests[0]['output_config']['effort'] == 'low'
        row = RadarReviewMeter.query.one()
        assert row.served == 1


# --- Rejudge backlog selection (Task 11) ------------------------------------

from scripts import rejudge_radar_sentiment as rejudge


def test_rejudge_selects_exactly_the_non_current_versions(clean_posts):
    with flask_app.app_context():
        legacy_v1 = make_post('zztest-rj-v1', llm='bullish')   # v1-era row
        never = make_post('zztest-rj-never')
        current = make_post('zztest-rj-cur')
        llm_sentiment.apply_judgments(
            rows_for([current]), {current: ja()}, stage='primary',
            model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        # A row judged under an older prompt version.
        stale = make_post('zztest-rj-stale')
        llm_sentiment.apply_judgments(
            rows_for([stale]), {stale: ja()}, stage='primary',
            model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        m = db.session.get(RadarMention, stale)
        m.sentiment_prompt_version = 'radar-sentiment-v1-retired'
        db.session.commit()

        got = {mention.id for mention, _post
               in rejudge.rejudge_backlog(100000)}
        ours = got & {legacy_v1, never, current, stale}
        assert ours == {legacy_v1, never, stale}


def test_rejudge_keeps_history_and_overwrites_the_projection(clean_posts):
    with flask_app.app_context():
        stale = make_post('zztest-rj-hist', llm='bearish')
        m = db.session.get(RadarMention, stale)
        m.sentiment_prompt_version = 'radar-sentiment-v1-retired'
        m.sentiment_judged_at = NOW
        m.sentiment_attitude = 'negative'
        m.sentiment_relevance = 'relevant'
        m.sentiment_content_origin = 'human_chatter'
        db.session.add(RadarSentimentJudgment(
            mention_id=stale, stage='primary', model='claude-haiku-4-5',
            prompt_version='radar-sentiment-v1-retired',
            relevance='relevant', content_origin='human_chatter',
            attitude='negative', expected_move='down', confidence='high',
            input_tokens=1, output_tokens=1, created_utc=NOW))
        db.session.commit()

        rows = rejudge.rejudge_backlog(100000)
        ours = [(mention, post) for mention, post in rows
                if mention.id == stale]
        written = llm_sentiment.apply_judgments(
            ours, {stale: ja(attitude='positive')}, stage='primary',
            model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        assert written == 1
        m = db.session.get(RadarMention, stale)
        assert m.sentiment_attitude == 'positive'
        assert m.llm_sentiment == 'bullish'
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=stale).order_by(RadarSentimentJudgment.id).all()
        assert [h.prompt_version for h in history] == \
            ['radar-sentiment-v1-retired', llm_sentiment.PROMPT_VERSION]


def test_cost_projection_uses_measured_history_when_present(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-rj-cost')
        llm_sentiment.apply_judgments(
            rows_for([mention_id]),
            {mention_id: ja(input_tokens=1000, output_tokens=100)},
            stage='primary', model=llm_sentiment.PRIMARY_MODEL)
        db.session.commit()
        per = rejudge.measured_tokens_per_mention()
        assert per is not None
        usd = rejudge.projected_cost_usd(1000, per)
        assert usd > 0.0


# --- Locked reference tooling, pure pieces (Task 13) ------------------------

def test_rejudge_judges_through_an_explicitly_constructed_haiku(
        clean_posts, monkeypatch):
    """The bounded history rewrite builds its own judge.

    It must not inherit whatever the daemon is configured with: this script
    rewrites the past, and the past must not quietly acquire a different
    judge because a trial is running. What it constructs is what it books
    and what it stores.
    """
    with flask_app.app_context():
        stale = make_post('zztest-rj-backend')
        m = db.session.get(RadarMention, stale)
        m.sentiment_prompt_version = 'radar-sentiment-v1-retired'
        m.sentiment_judged_at = NOW
        db.session.commit()

        built = []
        backend = FakeBackend([{stale: jm(attitude='negative', move='down')}],
                              id=llm_sentiment.PRIMARY_MODEL,
                              usage=judge_backends.Usage(11, 3))

        def fake_construct(spec, **kwargs):
            built.append(spec)
            return backend

        monkeypatch.setattr(judge_backends, 'construct_backend', fake_construct)
        monkeypatch.setattr(rejudge, 'rejudge_backlog',
                            lambda limit: rows_for([stale]))

        assert rejudge.run(apply=True, limit=1) == 1
        assert built == ['anthropic:' + llm_sentiment.PRIMARY_MODEL]
        m = db.session.get(RadarMention, stale)
        assert m.sentiment_model == llm_sentiment.PRIMARY_MODEL
        assert m.sentiment_attitude == 'negative'
        assert m.sentiment_prompt_version == llm_sentiment.PROMPT_VERSION


def test_a_dry_run_constructs_no_judge_at_all(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError('a dry run built a judge')

    monkeypatch.setattr(judge_backends, 'construct_backend', boom)
    with flask_app.app_context():
        assert rejudge.run(apply=False) == 0


from scripts import build_sentiment_reference as reference
from scripts import score_sentiment_reference as scorer


def test_sampling_floor_names_each_shortfall():
    rows = [{'source_root': 'reddit'}] * 50 + [{'source_root': 'bluesky'}] * 40
    ok, reasons = reference.sampling_ok(rows)
    assert not ok
    assert len(reasons) == 3          # total, reddit, bluesky
    ok, reasons = reference.sampling_ok(
        [{'source_root': 'reddit'}] * 150 + [{'source_root': 'bluesky'}] * 150)
    assert ok and not reasons


def test_macro_f1_and_removal_precision_arithmetic():
    pairs = [({'relevance': 'irrelevant', 'content_origin': 'human_chatter'},
              {'relevance': 'irrelevant', 'content_origin': 'human_chatter'}),
             ({'relevance': 'irrelevant', 'content_origin': 'human_chatter'},
              {'relevance': 'relevant', 'content_origin': 'human_chatter'}),
             ({'relevance': 'relevant', 'content_origin': 'human_chatter'},
              {'relevance': 'relevant', 'content_origin': 'human_chatter'})]
    assert scorer.removal_precision(pairs) == pytest.approx(0.5)
    f1 = scorer.macro_f1([(p['relevance'], t['relevance'])
                          for p, t in pairs],
                         ('relevant', 'irrelevant', 'uncertain'))
    assert 0.0 < f1 < 1.0


def test_llm_gates_flag_a_broken_source_even_when_the_aggregate_passes():
    tables = {
        'schema_invalid': 0,
        'attitude_exact': 0.9, 'directional_agreement': 0.9,
        'reversal_rate': 0.0, 'relevance_f1': 0.95, 'origin_f1': 0.95,
        'removal_precision': 1.0,
        'per_source_attitude': {'reddit': 0.9, 'bluesky': 0.5},
    }
    ok, reasons = scorer.llm_gates_pass(tables)
    assert not ok
    assert any('bluesky' in reason for reason in reasons)


def test_unjudged_reference_items_count_as_misses():
    """Blocker 4: coverage is part of the grade -- a pipeline that judged
    half the set cannot score like one that judged all of it."""
    def row(predicted, truth='positive'):
        return {'truth': {'relevance': 'relevant',
                          'content_origin': 'human_chatter',
                          'attitude': truth, 'expected_move': 'up',
                          'confidence': 'high'},
                'predicted': predicted, 'source_root': 'reddit', 'tags': []}
    good = {'relevance': 'relevant', 'content_origin': 'human_chatter',
            'attitude': 'positive', 'expected_move': 'up',
            'confidence': 'high'}
    tables = scorer.attitude_tables([row(good), row(None)])
    assert tables['coverage'] == pytest.approx(0.5)
    assert tables['attitude_exact'] == pytest.approx(0.5)


def test_a_hard_slice_regression_beyond_two_points_is_flagged():
    tables = {'per_tag_attitude': {'question': 0.70, 'multi_ticker': 0.90}}
    previous = {'per_tag_attitude': {'question': 0.75, 'multi_ticker': 0.91}}
    drops = scorer.hard_slice_regressions(tables, previous)
    assert len(drops) == 1 and 'question' in drops[0]


def test_the_ledger_dedups_on_identity_not_bare_candidate(tmp_path,
                                                          monkeypatch):
    from features.radar import sentiment
    monkeypatch.setattr(sentiment, 'ARTIFACT_DIR', str(tmp_path))
    scorer.ledger_append({'candidate': 'clf-v2-x', 'identity': 'clf-v2-x#aaa',
                          'kind': 'local', 'passes_10_3': True})
    assert scorer.ledger_lookup_identity('clf-v2-x#aaa') is not None
    # Same artifact, different predictions (retrained scorer state): a new
    # identity is NOT refused...
    assert scorer.ledger_lookup_identity('clf-v2-x#bbb') is None
    # ...while the trainer's promotion gate finds the candidate by version.
    from scripts import train_radar_sentiment as trainer_mod
    assert trainer_mod.reference_verdict('clf-v2-x') is True


def test_the_frozen_manifest_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, 'REFERENCE_DIR', str(tmp_path))
    blind = tmp_path / 'reference-blind.jsonl'
    blind.write_text('{"n": 1}\n', encoding='utf-8')
    manifest = {'files': {'reference-blind.jsonl':
                          reference.sha256_of(str(blind))}}
    (tmp_path / 'reference-manifest.json').write_text(
        json.dumps(manifest), encoding='utf-8')
    assert scorer.verify_manifest() == manifest
    blind.write_text('{"n": 1, "tampered": true}\n', encoding='utf-8')
    with pytest.raises(SystemExit):
        scorer.verify_manifest()


# --- Codex deploy-review fixes (2026-08-31 round 2) -------------------------

def test_the_activation_cutoff_fences_the_legacy_backlog(clean_posts):
    """Blocker 1: without the cutoff, the ten-minute scheduler would bill
    through the entire pre-v2 backlog on deploy day, bypassing the rejudge
    script's dry-run and --limit controls."""
    with flask_app.app_context():
        legacy = make_post('zztest-cut-legacy')
        m = db.session.get(RadarMention, legacy)
        m.post.created_utc = llm_sentiment.V2_ACTIVATION_CUTOFF \
            - dt.timedelta(days=1)
        db.session.commit()

        live = {mention.id for mention, _post in llm_sentiment.pending(50)}
        assert legacy not in live

        # The rejudge script, and only it, still reaches behind the fence.
        backlog = {mention.id for mention, _post
                   in rejudge.rejudge_backlog(100000)}
        assert legacy in backlog




def test_the_meter_lands_on_the_utc_day_of_the_pass(clean_posts,
                                                    clean_meter_all,
                                                    own_candidates,
                                                    monkeypatch):
    """Finding 7: date.today() is the machine's local calendar; around
    midnight it disagrees with the UTC clock every other figure uses."""
    monkeypatch.setenv('RADAR_SONNET_REVIEW', 'shadow')
    with flask_app.app_context():
        mention_id = primary_judged('zztest-utc-day')
        # Move the judgment history onto the future UTC day so the pass's
        # ceiling math and the meter share that day.
        target_day = dt.datetime(2027, 6, 1, 23, 59, 0)
        RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).update(
                {'created_utc': target_day},
                synchronize_session=False)
        db.session.commit()

        llm_sentiment.run_review_pass(backend=sentinel_backend(),
                                      now=target_day)
        row = RadarReviewMeter.query.one()
        assert row.day == target_day.date()
