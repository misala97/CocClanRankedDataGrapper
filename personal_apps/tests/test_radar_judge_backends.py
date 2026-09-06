# personal_apps/tests/test_radar_judge_backends.py
"""The vendor adapter: request shape, parsing, and what it refuses to answer.

Everything here is about talking to Anthropic specifically. What radar DOES
with an answer -- validation, token attribution, storage, review precedence
-- is tested against a FakeBackend in test_radar_sentiment_v2, because none
of it should care who answered.

The fake client is deliberately the same shape it has always been: these
assertions moved out of the judge() tests unchanged, so the request bytes
they pin are the request bytes that were already going out.
"""
import json

import anthropic
import pytest

from features.radar import judge_backends, llm_sentiment, sentiment_input
from features.radar.judge_backends import AnthropicBackend, Usage
from features.radar.llm_sentiment import (CONFIDENCE, JudgeItem,
                                          SentimentUnavailable)


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


def full(n, relevance='relevant', origin='human_chatter', attitude='positive',
         move='up', confidence='high'):
    return {'n': n, 'relevance': relevance, 'content_origin': origin,
            'attitude': attitude, 'expected_move': move,
            'confidence': confidence}


def answer(entries, usage=None):
    return FakeResponse(json.dumps({'verdicts': entries}), usage=usage)


def backend_over(answers, model=None, effort=None):
    client = FakeClient(answers)
    return AnthropicBackend(model or llm_sentiment.PRIMARY_MODEL,
                            effort=effort, client=client), client


# ---- the request ------------------------------------------------------------

def test_the_item_serialization_matches_the_spec_shape():
    backend, client = backend_over([answer([full(1)])])
    backend.judge_batch([jitem(1, text='body & text', ticker='ZZA',
                               source='reddit:options')])
    prompt = client.messages.requests[0]['messages'][0]['content']
    assert '<item n="1">' in prompt
    assert '<target_ticker>ZZA</target_ticker>' in prompt
    assert '<content_type>submission</content_type>' in prompt
    assert '<post>body &amp; text</post>' in prompt


def test_a_reddit_comment_serializes_as_comment_without_parent_title():
    backend, client = backend_over([answer([full(1)])])
    backend.judge_batch([jitem(1, text='my own words', ticker='ZZA',
                               source='reddit:options',
                               title='/u/parent on Big Thread')])
    prompt = client.messages.requests[0]['messages'][0]['content']
    assert '<content_type>comment</content_type>' in prompt
    assert 'Big Thread' not in prompt


def test_the_review_preamble_is_present_only_when_asked_for():
    backend, client = backend_over([answer([full(1)])])
    backend.judge_batch([jitem(1)])
    assert llm_sentiment.REVIEW_PREAMBLE not in \
        client.messages.requests[0]['messages'][0]['content']

    backend, client = backend_over([answer([full(1)])],
                                   model=llm_sentiment.REVIEW_MODEL)
    backend.judge_batch([jitem(1)], preamble=llm_sentiment.REVIEW_PREAMBLE)
    prompt = client.messages.requests[0]['messages'][0]['content']
    assert prompt.startswith(llm_sentiment.REVIEW_PREAMBLE)
    assert llm_sentiment._INSTRUCTIONS_V2 in prompt


def test_the_binding_schema_travels_on_every_call():
    backend, client = backend_over([answer([full(1)])])
    backend.judge_batch([jitem(1)])
    request = client.messages.requests[0]
    assert request['output_config']['format'] == {
        'type': 'json_schema', 'schema': llm_sentiment.V2_SCHEMA}
    assert request['max_tokens'] == 2048
    assert request['model'] == llm_sentiment.PRIMARY_MODEL


def test_effort_is_a_property_of_the_backend_not_of_the_call():
    """Haiku 4.5 rejects `effort` with a 400, the review tier requires it.
    It used to be threaded through two layers of generic code."""
    backend, client = backend_over([answer([full(1)])])
    backend.judge_batch([jitem(1)])
    assert 'effort' not in client.messages.requests[0]['output_config']

    backend, client = backend_over([answer([full(1)])],
                                   model=llm_sentiment.REVIEW_MODEL,
                                   effort='low')
    backend.judge_batch([jitem(1)])
    assert client.messages.requests[0]['output_config']['effort'] == 'low'
    assert client.messages.requests[0]['model'] == 'claude-sonnet-5'


# ---- the response -----------------------------------------------------------

def test_a_full_judgment_comes_back_typed_and_keyed():
    backend, _client = backend_over([answer([full(1)])])
    got, usage = backend.judge_batch([jitem(7)])
    assert set(got) == {7}
    assert got[7].relevance == 'relevant' and got[7].attitude == 'positive'
    assert got[7].expected_move == 'up' and got[7].confidence == 'high'
    assert usage == Usage(0, 0)


def test_usage_is_reported_as_integers():
    reported = type('U', (), {'input_tokens': 100, 'output_tokens': 21})()
    backend, _client = backend_over([answer([full(1)], usage=reported)])
    _got, usage = backend.judge_batch([jitem(1)])
    assert usage == Usage(100, 21)


def test_the_adapter_reports_what_the_model_said_without_judging_it():
    """Validation is llm_sentiment's boundary, not the adapter's. The
    adapter must not quietly drop a bad value -- and must not repair it
    either, which is how a defaulted verdict would get stored."""
    bad = full(1)
    bad['attitude'] = 'bullish'          # not in the enum
    backend, _client = backend_over([answer([bad])])
    got, _usage = backend.judge_batch([jitem(1)])
    assert got[1].attitude == 'bullish'

    missing = full(2)
    del missing['content_origin']
    backend, _client = backend_over([answer([missing])])
    got, _usage = backend.judge_batch([jitem(1), jitem(2)])
    assert got[2].content_origin is None      # absent, not invented


def test_a_duplicated_item_number_keeps_only_one_answer():
    backend, _client = backend_over([answer([full(1, attitude='positive'),
                                             full(1, attitude='negative')])])
    got, _usage = backend.judge_batch([jitem(1)])
    assert set(got) == {1}


def test_an_entry_without_a_usable_item_number_is_dropped():
    no_n = full(1)
    del no_n['n']
    backend, _client = backend_over([answer([no_n, full(99), 'not a dict'])])
    got, _usage = backend.judge_batch([jitem(1)])
    assert got == {}


# ---- what is not a verdict --------------------------------------------------

def test_a_refusal_is_not_a_verdict():
    backend, _client = backend_over([FakeResponse('no', stop_reason='refusal')])
    with pytest.raises(SentimentUnavailable):
        backend.judge_batch([jitem(1)])


def test_malformed_json_is_not_a_verdict():
    backend, _client = backend_over([FakeResponse('this is not json')])
    with pytest.raises(SentimentUnavailable):
        backend.judge_batch([jitem(1)])


@pytest.mark.parametrize('body', [
    json.dumps({'verdicts': {'n': 1}}),      # well-formed, wrong shape
    json.dumps({'verdicts': 'what'}),
    json.dumps({'nothing': 'here'}),
])
def test_a_wrong_shaped_answer_costs_only_its_batch(body):
    """Iterating a dict here once yielded strings and let an AttributeError
    escape the whole pass (Codex review, finding 8)."""
    backend, _client = backend_over([FakeResponse(body)])
    with pytest.raises(SentimentUnavailable):
        backend.judge_batch([jitem(1)])


def test_a_transport_failure_is_translated_at_the_vendor_boundary():
    """Nothing upstream of the adapter should have to know this backend
    speaks HTTP, so anthropic.APIError never leaves it."""
    backend, _client = backend_over([anthropic.APIConnectionError(request=None)])
    with pytest.raises(SentimentUnavailable):
        backend.judge_batch([jitem(1)])


# ---- construction -----------------------------------------------------------

def test_the_client_is_not_built_until_a_batch_is_judged(monkeypatch):
    """Importing or constructing must not require an API key: the daemon
    resolves its configuration at startup, before it judges anything."""
    def boom(*args, **kwargs):
        raise AssertionError('a client was constructed at construction time')

    monkeypatch.setattr(anthropic, 'Anthropic', boom)
    backend = judge_backends.construct_backend('anthropic:claude-haiku-4-5')
    assert backend.id == 'claude-haiku-4-5'


def test_construct_backend_builds_the_named_anthropic_model():
    backend = judge_backends.construct_backend('anthropic:claude-sonnet-5',
                                               effort='low')
    assert isinstance(backend, AnthropicBackend)
    assert backend.id == 'claude-sonnet-5' and backend.effort == 'low'
    assert backend.supports_review is True
    assert backend.batch_size == llm_sentiment.BATCH_SIZE
    assert backend.pass_limit == llm_sentiment.PASS_LIMIT


@pytest.mark.parametrize('spec', ['', '   ', 'anthropic:', 'haiku',
                                  'openai:gpt-5', None, 'encoder'])
def test_an_unknown_spec_is_an_error_not_a_silent_default(spec):
    """Judging with the wrong backend is worse than not judging: the wrong
    answers get stored and counted under the wrong provenance."""
    with pytest.raises(ValueError):
        judge_backends.construct_backend(spec)


def test_every_field_of_the_protocol_is_present_on_the_adapter():
    backend = judge_backends.construct_backend('anthropic:claude-haiku-4-5')
    for attribute in ('id', 'batch_size', 'pass_limit', 'supports_review',
                      'judge_batch'):
        assert hasattr(backend, attribute), attribute


def test_the_backend_id_fits_the_provenance_column():
    from models import RadarMention, RadarSentimentJudgment
    width = RadarMention.__table__.c.sentiment_model.type.length
    assert RadarSentimentJudgment.__table__.c.model.type.length == width
    for model_id in (llm_sentiment.PRIMARY_MODEL, llm_sentiment.REVIEW_MODEL):
        assert len(model_id) <= width, model_id


# ---- display metadata -------------------------------------------------------

def test_backend_label_names_the_source_without_opening_anything(monkeypatch):
    """It runs inside a web request, so it must stay pure."""
    def boom(*args, **kwargs):
        raise AssertionError('backend_label constructed a client')

    monkeypatch.setattr(anthropic, 'Anthropic', boom)
    assert judge_backends.backend_label('claude-haiku-4-5') == 'Claude'
    assert judge_backends.backend_label('claude-sonnet-5') == 'Claude'
    assert judge_backends.backend_label('claude-haiku-4-4-retired') == 'Claude'
    assert judge_backends.backend_label('something-else') == 'model'
    assert judge_backends.backend_label(None) == 'model'


def test_the_enum_names_are_shared_not_copied():
    """The adapter reads llm_sentiment's field list; a new field must not
    need two edits to reach the wire."""
    from features.radar.llm_sentiment import _FIELD_ENUMS
    assert set(_FIELD_ENUMS) == {'relevance', 'content_origin', 'attitude',
                                 'expected_move', 'confidence'}
    assert _FIELD_ENUMS['confidence'] == CONFIDENCE
