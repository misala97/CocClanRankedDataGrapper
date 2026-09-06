# personal_apps/scratchpad/label_export/label_data.py
"""Assemble the encoder's training rows from every labelling wave.

Deliberately free of torch, so the rules that decide WHAT the model trains
on can be tested in the ordinary suite rather than only inside the
training venv. train_encoder.py imports this.

A wave is a (labels, export) pair: the production set is
labels-sonnet5.jsonl against export-2026-09-05.jsonl, and each recall wave
is labels-recall.jsonl against its own candidates file. Both shapes carry
the same fields; a wave row simply has no production post id or simhash,
because its post was never stored.

GROUPING. The split's duplicate rules group by post, so a post's several
ticker rows never straddle the train/test boundary. A wave row's post_id
is None, and grouping on None would make all 4,500 of them one group, so
the post's external id stands in -- which is what it is.
"""
import json

TEXT_LIMIT = 2000       # label_harness.MAX_CHARS: what the teacher read


def _read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_rows(pairs, heads=None, index=None):
    """Rows from every (labels_path, export_path) pair, in order.

    `heads` and `index` are the trainer's label vocabulary; without them
    the raw label values are carried through, which is what the tests and
    any analysis want.
    """
    rows = []
    seen = {}
    for labels_path, export_path in pairs:
        export = {row['mention_id']: row for row in _read_jsonl(export_path)}
        for label in _read_jsonl(labels_path):
            source = export.get(label['mention_id'])
            if source is None:
                continue
            mention_id = label['mention_id']
            if mention_id in seen:
                raise ValueError(
                    'mention_id %s appears in both %s and %s: one of the two '
                    'rows would be silently dropped'
                    % (mention_id, seen[mention_id], labels_path))
            seen[mention_id] = labels_path
            group = source.get('post_id')
            if group is None:
                group = source.get('external_id') or 'mention:%s' % mention_id
            rows.append({
                'mention_id': mention_id,
                'post_id': group,
                'ticker': label['ticker'],
                'text': (source['author_text'] or '')[:TEXT_LIMIT],
                'created': source['created_utc'],
                'stratum': label['stratum'],
                'source': (source['source'] or '').split(':')[0],
                'simhash': source.get('simhash'),
                'wave': labels_path,
                'y': ({head: index[head][label[head]] for head in heads}
                      if heads and index else {h: label[h] for h in
                                               ('relevance', 'content_origin',
                                                'attitude', 'expected_move',
                                                'confidence')}),
            })
    return rows
