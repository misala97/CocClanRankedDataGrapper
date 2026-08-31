# personal_apps/tests/test_radar_sentiment_v2.py
"""Sentiment v2: structured judgment, storage, routing (spec 2026-08-31)."""
import hashlib
import json

from features.radar import llm_sentiment, sentiment_input
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


def test_a_full_judgment_comes_back_typed():
    client = FakeClient([answer([full(1)])])
    got = judge([jitem(7)], client=client)
    j = got[7].judgment
    assert j.relevance == 'relevant' and j.attitude == 'positive'
    assert j.expected_move == 'up' and j.confidence == 'high'


def test_the_item_serialization_matches_the_spec_shape():
    client = FakeClient([answer([full(1)])])
    judge([jitem(1, text='body & text', ticker='ZZA',
                 source='reddit:options')], client=client)
    prompt = client.messages.requests[0]['messages'][0]['content']
    assert '<item n="1">' in prompt
    assert '<target_ticker>ZZA</target_ticker>' in prompt
    assert '<content_type>submission</content_type>' in prompt
    assert '<post>body &amp; text</post>' in prompt


def test_a_reddit_comment_serializes_as_comment_without_parent_title():
    client = FakeClient([answer([full(1)])])
    judge([jitem(1, text='my own words', ticker='ZZA',
                 source='reddit:options', title='/u/parent on Big Thread')],
          client=client)
    prompt = client.messages.requests[0]['messages'][0]['content']
    assert '<content_type>comment</content_type>' in prompt
    assert 'Big Thread' not in prompt


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


def test_the_review_preamble_is_present_only_on_review_calls():
    client = FakeClient([answer([full(1)])])
    judge([jitem(1)], client=client)
    assert llm_sentiment.REVIEW_PREAMBLE not in \
        client.messages.requests[0]['messages'][0]['content']
    client = FakeClient([answer([full(1)])])
    judge([jitem(1)], client=client, model=llm_sentiment.REVIEW_MODEL,
          effort='low', preamble=llm_sentiment.REVIEW_PREAMBLE)
    prompt = client.messages.requests[0]['messages'][0]['content']
    assert prompt.startswith(llm_sentiment.REVIEW_PREAMBLE)
    assert llm_sentiment._INSTRUCTIONS_V2 in prompt


def test_an_entry_with_a_value_outside_the_enums_is_discarded():
    bad = full(1)
    bad['attitude'] = 'bullish'
    client = FakeClient([answer([bad])])
    assert judge([jitem(1)], client=client) == {}


def test_a_partial_entry_is_discarded_not_defaulted():
    entry = full(1)
    del entry['content_origin']
    client = FakeClient([answer([entry])])
    assert judge([jitem(1)], client=client) == {}


def test_malformed_json_leaves_the_batch_unjudged():
    client = FakeClient([FakeResponse('this is not json')])
    assert judge([jitem(1)], client=client) == {}


def test_a_missing_item_number_is_discarded():
    entry = full(1)
    del entry['n']
    client = FakeClient([answer([entry])])
    assert judge([jitem(1)], client=client) == {}


def test_a_refusal_leaves_the_batch_unjudged():
    client = FakeClient([FakeResponse('no', stop_reason='refusal')])
    assert judge([jitem(1)], client=client) == {}


def test_batch_usage_is_split_across_its_answers():
    usage = type('U', (), {'input_tokens': 100, 'output_tokens': 21})()
    client = FakeClient([answer([full(1), full(2)], usage=usage)])
    got = judge([jitem(1), jitem(2)], client=client)
    assert got[1].input_tokens + got[2].input_tokens == 100
    assert got[1].output_tokens + got[2].output_tokens == 21


def test_no_effort_is_sent_by_default_and_effort_reaches_sonnet():
    client = FakeClient([answer([full(1)])])
    judge([jitem(1)], client=client)
    assert 'effort' not in client.messages.requests[0]['output_config']
    client = FakeClient([answer([full(1)])])
    judge([jitem(1)], client=client, model=llm_sentiment.REVIEW_MODEL,
          effort='low')
    assert client.messages.requests[0]['output_config']['effort'] == 'low'
    assert client.messages.requests[0]['model'] == 'claude-sonnet-5'


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
