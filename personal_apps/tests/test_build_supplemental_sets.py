# personal_apps/tests/test_build_supplemental_sets.py
"""The four supplemental files, from what is on disk and the artifact.

Arming freezes which rows the two supplementary sets are; the audit's
evaluate needs those rows with a reference and a prediction each. The
builder makes all four files from the label files on the PC and the
packaged artifact, so the membership frozen at arming and the data
evaluated later come from one place and cannot drift apart.

The natural set has no stored predictions -- the training runs kept
aggregates -- so the builder scores its rows through the artifact, the
same adapter the trial runs.
"""
import json
import os

import pytest

from features.radar import judge_backends, llm_sentiment
from scripts import build_supplemental_sets as builder

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'fixtures', 'radar_encoder')
FIVE = ('relevance', 'content_origin', 'attitude', 'expected_move',
        'confidence')


def label(mention_id, ticker, **fields):
    row = {'mention_id': mention_id, 'ticker': ticker, 'truncated': False,
           'relevance': 'relevant', 'content_origin': 'human_chatter',
           'attitude': 'positive', 'expected_move': 'up',
           'confidence': 'high'}
    row.update(fields)
    return row


def write_jsonl(path, rows):
    with open(path, 'w', encoding='utf-8') as out:
        for row in rows:
            out.write(json.dumps(row) + '\n')
    return str(path)


def write_json(path, payload):
    with open(path, 'w', encoding='utf-8') as out:
        json.dump(payload, out)
    return str(path)


@pytest.fixture()
def sources(tmp_path):
    """Three natural rows and a four-row audit with two halves, plus the
    audit's verdicts keyed by `n` the way pc-verdicts-train13000.json is."""
    audit = [
        {'n': 1, 'half': 'removal', 'truncated': False,
         'human': label(11, 'ZZA', relevance='irrelevant')},
        {'n': 2, 'half': 'removal', 'truncated': True,
         'human': label(12, 'ZZA')},
        {'n': 3, 'half': 'natural', 'truncated': False,
         'human': label(13, 'ZZB')},
        {'n': 4, 'half': 'natural', 'truncated': False,
         'human': label(14, 'ZZB', attitude='negative')},
    ]
    verdicts = {str(n): ['irrelevant', 'human_chatter', 'none', 'unknown',
                         'high'] for n in range(1, 5)}
    labels = [label(101, 'ZZC'), label(102, 'ZZC', attitude='mixed'),
              label(103, 'ZZD', truncated=True), label(999, 'ZZE')]
    export = [{'mention_id': m, 'ticker': t, 'source': 'bluesky',
               'channel': 'firehose', 'author': 'someone',
               'author_text': 'w%d ZZ ripping' % m}
              for m, t in ((101, 'ZZC'), (102, 'ZZC'), (103, 'ZZD'),
                           (999, 'ZZE'))]
    return {
        'audit': write_jsonl(tmp_path / 'audit-200.jsonl', audit),
        'audit_verdicts': write_json(tmp_path / 'pc-verdicts.json', verdicts),
        'natural': write_json(tmp_path / 'test-natural.json', [101, 102, 103]),
        'labels': write_jsonl(tmp_path / 'labels.jsonl', labels),
        'export': write_jsonl(tmp_path / 'export.jsonl', export),
        'out': str(tmp_path / 'out'),
    }


def run(sources, **overrides):
    args = dict(sources)
    args.update(overrides)
    return builder.build(audit=args['audit'],
                         audit_verdicts=args['audit_verdicts'],
                         natural=args['natural'], labels=args['labels'],
                         export=args['export'], artifact_dir=FIXTURE,
                         out_dir=args['out'])


def read_jsonl(path):
    return [json.loads(line) for line in open(path, encoding='utf-8') if line.strip()]


def test_the_membership_files_are_exactly_the_sets(sources):
    run(sources)
    audit_keys = json.load(open(os.path.join(sources['out'],
                                             'supplemental-audit-keys.json')))
    assert audit_keys == [{'key': 'audit-1', 'half': 'removal'},
                          {'key': 'audit-2', 'half': 'removal'},
                          {'key': 'audit-3', 'half': 'natural'},
                          {'key': 'audit-4', 'half': 'natural'}]
    natural_keys = json.load(open(os.path.join(sources['out'],
                                               'supplemental-natural-keys.json')))
    assert natural_keys == ['101', '102', '103']


def test_the_audit_set_carries_the_human_reference_and_the_stored_verdicts(
        sources):
    run(sources)
    rows = read_jsonl(os.path.join(sources['out'], 'supplemental-audit.jsonl'))
    assert [row['key'] for row in rows] == ['audit-1', 'audit-2', 'audit-3',
                                            'audit-4']
    assert rows[0]['half'] == 'removal' and rows[2]['half'] == 'natural'
    assert rows[1]['truncated'] is True
    assert rows[0]['reference']['relevance'] == 'irrelevant'
    assert rows[3]['reference']['attitude'] == 'negative'
    assert rows[0]['prediction'] == dict(zip(FIVE, ['irrelevant',
                                                    'human_chatter', 'none',
                                                    'unknown', 'high']))
    for row in rows:
        assert set(row['reference']) == set(FIVE)


def test_the_natural_set_is_scored_through_the_artifact(sources):
    """The prediction is the artifact's answer to the canonical input --
    the same adapter, the same tokenizer pair -- not a stored number."""
    run(sources)
    rows = read_jsonl(os.path.join(sources['out'], 'supplemental-natural.jsonl'))
    assert [row['key'] for row in rows] == ['101', '102', '103']
    assert all(row['half'] == 'natural' for row in rows)
    assert rows[2]['truncated'] is True
    assert rows[1]['reference']['attitude'] == 'mixed'
    backend = judge_backends.EncoderBackend(FIXTURE)
    from features.radar.sentiment_input import PreparedInput
    for row in rows:
        item = llm_sentiment.JudgeItem()
        item.key = row['key']
        item.prepared = PreparedInput(
            author_text='w%s ZZ ripping' % row['key'], target_ticker=row['ticker'],
            source='bluesky', channel='firehose', author='someone',
            is_comment=False)
        (answers, _usage) = backend.judge_batch([item])
        expected = answers[row['key']]
        assert row['prediction'] == {field: getattr(expected, field)
                                     for field in FIVE}


def test_a_natural_row_without_a_label_or_text_stops_the_build(sources,
                                                                tmp_path):
    """The set is the frozen rows. One that cannot be built is not
    silently dropped -- that would be a smaller set."""
    with pytest.raises(builder.BuildError):
        run(sources, natural=write_json(tmp_path / 'n2.json', [101, 102, 555]))
    with pytest.raises(builder.BuildError):
        run(sources, export=write_jsonl(tmp_path / 'e2.jsonl', [
            {'mention_id': 101, 'ticker': 'ZZC', 'author_text': 'x'}]))


def test_an_audit_row_without_a_stored_verdict_stops_the_build(sources,
                                                               tmp_path):
    with pytest.raises(builder.BuildError):
        run(sources, audit_verdicts=write_json(tmp_path / 'v2.json',
                                               {'1': ['irrelevant', 'human_chatter',
                                                      'none', 'unknown', 'high']}))
