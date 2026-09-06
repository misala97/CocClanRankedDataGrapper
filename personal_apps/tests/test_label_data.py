"""Assembling the training rows from several waves.

The recall waves live in their own files and have no production post id or
simhash, so the split's duplicate rules need something to group on.
"""
import json

from scratchpad.label_export import label_data


def _write(tmp_path, name, rows):
    path = tmp_path / name
    with open(path, 'w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row) + '\n')
    return str(path)


def _label(mention_id, ticker='GME', relevance='relevant'):
    return {'mention_id': mention_id, 'ticker': ticker, 'relevance': relevance,
            'content_origin': 'human_chatter', 'attitude': 'none',
            'expected_move': 'unknown', 'confidence': 'high',
            'stratum': 'reddit:a<200'}


def _export(mention_id, post_id=None, external_id=None, simhash=None):
    return {'mention_id': mention_id, 'post_id': post_id, 'external_id': external_id,
            'author_text': 'some text about GME', 'created_utc': '2026-09-05T10:00:00',
            'source': 'reddit:wallstreetbets', 'simhash': simhash}


def test_rows_from_several_waves_are_one_set(tmp_path):
    a_labels = _write(tmp_path, 'a-labels.jsonl', [_label(1)])
    a_export = _write(tmp_path, 'a-export.jsonl', [_export(1, post_id=10, simhash=7)])
    b_labels = _write(tmp_path, 'b-labels.jsonl', [_label(-1)])
    b_export = _write(tmp_path, 'b-export.jsonl', [_export(-1, external_id='t1_x')])
    rows = label_data.load_rows([(a_labels, a_export), (b_labels, b_export)])
    assert [r['mention_id'] for r in rows] == [1, -1]
    assert rows[0]['post_id'] == 10 and rows[0]['simhash'] == 7


def test_a_wave_row_is_grouped_by_its_post_not_left_without_one(tmp_path):
    """post_id is None for every wave row, and grouping on None would put
    all 4,500 of them in one group -- so the post's external id becomes the
    group, which is what it is."""
    labels = _write(tmp_path, 'labels.jsonl', [_label(-1, 'GME'), _label(-2, 'AMC'),
                                               _label(-3, 'TSLA')])
    export = _write(tmp_path, 'export.jsonl', [_export(-1, external_id='t1_x'),
                                               _export(-2, external_id='t1_x'),
                                               _export(-3, external_id='t1_y')])
    rows = label_data.load_rows([(labels, export)])
    groups = {r['post_id'] for r in rows}
    assert len(groups) == 2
    assert rows[0]['post_id'] == rows[1]['post_id'] != rows[2]['post_id']
    assert all(r['post_id'] is not None for r in rows)


def test_a_label_without_its_export_row_is_dropped(tmp_path):
    labels = _write(tmp_path, 'labels.jsonl', [_label(1), _label(2)])
    export = _write(tmp_path, 'export.jsonl', [_export(1, post_id=10)])
    assert [r['mention_id'] for r in label_data.load_rows([(labels, export)])] == [1]


def test_text_is_cut_where_the_teacher_stopped_reading(tmp_path):
    labels = _write(tmp_path, 'labels.jsonl', [_label(1)])
    row = _export(1, post_id=10)
    row['author_text'] = 'x' * 3000
    export = _write(tmp_path, 'export.jsonl', [row])
    [got] = label_data.load_rows([(labels, export)])
    assert len(got['text']) == label_data.TEXT_LIMIT == 2000


def test_ids_from_two_waves_must_not_collide(tmp_path):
    labels_a = _write(tmp_path, 'a.jsonl', [_label(-1)])
    export_a = _write(tmp_path, 'ae.jsonl', [_export(-1, external_id='t1_x')])
    labels_b = _write(tmp_path, 'b.jsonl', [_label(-1, 'AMC')])
    export_b = _write(tmp_path, 'be.jsonl', [_export(-1, external_id='t1_y')])
    try:
        label_data.load_rows([(labels_a, export_a), (labels_b, export_b)])
    except ValueError as exc:
        assert '-1' in str(exc)
    else:
        raise AssertionError('a collision would silently drop one of the two rows')
