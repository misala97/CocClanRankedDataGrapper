#!/usr/bin/env python
"""Build the four supplemental files the audit needs, from what is on disk.

Arming freezes WHICH rows the two supplementary sets are (spec 7.2c); the
audit's evaluate needs those same rows with a reference and a prediction
each (spec 7.3). This makes all four files in one go, so the membership
frozen at arming and the data evaluated later come from one place:

    supplemental-audit-keys.json      [{key, half}]            -> arm
    supplemental-natural-keys.json    [key, ...]               -> arm
    supplemental-audit.jsonl          {key, half, truncated,
                                       reference, prediction}  -> evaluate
    supplemental-natural.jsonl        same shape               -> evaluate

The audit set is the original 200-row audit: its human labels and the
shipping model's stored verdicts (`pc-verdicts-train13000.json`, keyed by
`n`). The locked natural set has NO stored per-row predictions -- the
training runs kept aggregates -- so its rows are scored here through the
packaged artifact, with the same adapter the trial runs. A row that cannot
be built stops the build: a set with a row silently dropped is a smaller
set, and the frozen membership would refuse it anyway.

    python -m scripts.build_supplemental_sets \
        --audit C:/Users/michi/Desktop/radar_labels/audit-200.jsonl \
        --audit-verdicts C:/Users/michi/Desktop/radar_labels/pc-verdicts-train13000.json \
        --natural C:/Users/michi/Desktop/radar_labels/test-natural.json \
        --labels C:/Users/michi/Desktop/radar_labels/labels-sonnet5.jsonl \
        --export C:/Users/michi/Desktop/radar_labels/export-2026-09-05.jsonl \
        --artifact-dir artifacts/judge --out C:/Users/michi/Desktop/radar_labels/supplemental

Runs on the PC (it needs the label files); ~4 minutes of CPU for the 900
natural rows.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.radar import judge_backends, llm_sentiment  # noqa: E402
from features.radar.sentiment_input import PreparedInput  # noqa: E402

FIVE = tuple(llm_sentiment._FIELD_ENUMS)
AUDIT_KEYS = 'supplemental-audit-keys.json'
NATURAL_KEYS = 'supplemental-natural-keys.json'
AUDIT_ROWS = 'supplemental-audit.jsonl'
NATURAL_ROWS = 'supplemental-natural.jsonl'


class BuildError(Exception):
    """A set cannot be built as frozen. Nothing is written."""


def _jsonl(path):
    if not os.path.isfile(path):
        raise BuildError('no such file: %s' % path)
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _json(path):
    if not os.path.isfile(path):
        raise BuildError('no such file: %s' % path)
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def _five(source):
    return {field: source.get(field) for field in FIVE}


def _audit_set(audit_path, verdicts_path):
    rows = _jsonl(audit_path)
    verdicts = _json(verdicts_path)
    keys, data = [], []
    for row in rows:
        number = row['n']
        key = 'audit-%d' % number
        stored = verdicts.get(str(number))
        if not stored:
            raise BuildError('audit row n=%d has no stored verdict in %s'
                             % (number, verdicts_path))
        human = row.get('human') or {}
        keys.append({'key': key, 'half': row['half']})
        data.append({'key': key, 'half': row['half'],
                     'ticker': row.get('ticker') or human.get('ticker'),
                     'truncated': bool(row.get('truncated')),
                     'reference': _five(human),
                     'prediction': dict(zip(FIVE, stored))})
    if not data:
        raise BuildError('the audit file holds no rows')
    return keys, data


def _natural_set(natural_path, labels_path, export_path, artifact_dir):
    ids = [int(i) for i in _json(natural_path)]
    labels = {}
    for row in _jsonl(labels_path):
        labels.setdefault(int(row['mention_id']), row)
    texts = {int(row['mention_id']): row for row in _jsonl(export_path)}
    unlabelled = [i for i in ids if i not in labels]
    if unlabelled:
        raise BuildError('%d natural rows have no label (first: %s)'
                         % (len(unlabelled), unlabelled[:5]))
    untexted = [i for i in ids
                if i not in texts or not texts[i].get('author_text')]
    if untexted:
        raise BuildError('%d natural rows have no text in the export (first: '
                         '%s)' % (len(untexted), untexted[:5]))

    backend = judge_backends.EncoderBackend(artifact_dir)
    items = []
    for mention_id in ids:
        label, source = labels[mention_id], texts[mention_id]
        item = llm_sentiment.JudgeItem()
        item.key = str(mention_id)
        item.prepared = PreparedInput(
            author_text=source['author_text'],
            target_ticker=label.get('ticker') or source.get('ticker'),
            source=source.get('source') or '', channel=source.get('channel') or '',
            author=source.get('author'), is_comment=bool(source.get('is_comment')))
        items.append(item)
    predictions = {}
    for start in range(0, len(items), backend.batch_size):
        answers, _usage = backend.judge_batch(items[start:start + backend.batch_size])
        for key, judgment in answers.items():
            predictions[key] = {field: getattr(judgment, field) for field in FIVE}
    unanswered = [item.key for item in items if item.key not in predictions]
    if unanswered:
        raise BuildError('the artifact answered nothing for %d rows'
                         % len(unanswered))

    keys = [str(i) for i in ids]
    data = [{'key': str(i), 'half': 'natural',
             'ticker': labels[i].get('ticker') or texts[i].get('ticker'),
             'truncated': bool(labels[i].get('truncated')),
             'reference': _five(labels[i]),
             'prediction': predictions[str(i)]} for i in ids]
    return keys, data


def build(*, audit, audit_verdicts, natural, labels, export, artifact_dir,
          out_dir):
    audit_keys, audit_rows = _audit_set(audit, audit_verdicts)
    natural_keys, natural_rows = _natural_set(natural, labels, export,
                                              artifact_dir)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, AUDIT_KEYS), 'w', encoding='utf-8') as out:
        json.dump(audit_keys, out)
    with open(os.path.join(out_dir, NATURAL_KEYS), 'w', encoding='utf-8') as out:
        json.dump(natural_keys, out)
    for name, rows in ((AUDIT_ROWS, audit_rows), (NATURAL_ROWS, natural_rows)):
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as out:
            for row in rows:
                out.write(json.dumps(row) + '\n')
    return {'audit': len(audit_rows), 'natural': len(natural_rows)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', required=True, help='audit-200.jsonl')
    parser.add_argument('--audit-verdicts', required=True,
                        help='pc-verdicts-train13000.json, keyed by n')
    parser.add_argument('--natural', required=True, help='test-natural.json')
    parser.add_argument('--labels', required=True, help='labels-sonnet5.jsonl')
    parser.add_argument('--export', required=True,
                        help='export-2026-09-05.jsonl (author_text per mention)')
    parser.add_argument('--artifact-dir', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        counts = build(audit=args.audit, audit_verdicts=args.audit_verdicts,
                       natural=args.natural, labels=args.labels,
                       export=args.export, artifact_dir=args.artifact_dir,
                       out_dir=args.out)
    except BuildError as why:
        print('refused: %s' % why, file=sys.stderr)
        return 1
    print('wrote the audit set (%d rows) and the natural set (%d rows) '
          'with their membership files -> %s'
          % (counts['audit'], counts['natural'], args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
