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
