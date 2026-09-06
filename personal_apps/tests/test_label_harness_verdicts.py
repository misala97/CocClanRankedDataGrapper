"""The labelling harness's acceptance rule.

The rendered prompt never names a JSON envelope -- production supplies one
through the API's response schema, and a subagent labeller has to choose.
Both shapes it chooses are the same content, so collect accepts either and
still applies prod's field validation exactly.
"""
import importlib.util
import json
import os
import sys

_PATH = os.path.join(os.path.dirname(__file__), '..', 'scratchpad', 'label_export',
                     'label_harness.py')
_SPEC = importlib.util.spec_from_file_location('label_harness', _PATH)
harness = importlib.util.module_from_spec(_SPEC)
sys.modules['label_harness'] = harness
_SPEC.loader.exec_module(harness)


def _verdict(n, relevance='relevant'):
    return {'n': n, 'relevance': relevance, 'content_origin': 'human_chatter',
            'attitude': 'none', 'expected_move': 'unknown', 'confidence': 'high'}


def test_the_production_envelope_is_accepted():
    text = json.dumps({'verdicts': [_verdict(1), _verdict(2, 'irrelevant')]})
    got, err = harness.validate(text, 2)
    assert err is None
    assert got[1]['relevance'] == 'relevant' and got[2]['relevance'] == 'irrelevant'


def test_a_dict_keyed_by_item_number_is_the_same_answer():
    entry = _verdict(1)
    entry.pop('n')
    text = json.dumps({'1': entry, '2': dict(entry, relevance='uncertain')})
    got, err = harness.validate(text, 2)
    assert err is None
    assert got[1]['relevance'] == 'relevant' and got[2]['relevance'] == 'uncertain'


def test_a_bad_enum_is_still_refused_in_either_shape():
    entry = _verdict(1)
    entry.pop('n')
    entry['relevance'] = 'maybe'
    got, err = harness.validate(json.dumps({'1': entry}), 1)
    assert err is None and got == {}
    bad = _verdict(1)
    bad['attitude'] = 'furious'
    got, err = harness.validate(json.dumps({'verdicts': [bad]}), 1)
    assert err is None and got == {}


def test_an_item_number_outside_the_batch_is_dropped():
    entry = _verdict(1)
    entry.pop('n')
    got, err = harness.validate(json.dumps({'0': entry, '41': entry, '1': entry}), 40)
    assert err is None and list(got) == [1]


def test_neither_shape_means_unparseable():
    got, err = harness.validate(json.dumps([_verdict(1)]), 1)
    assert got is None and 'verdicts' in err
