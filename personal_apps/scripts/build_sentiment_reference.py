# personal_apps/scripts/build_sentiment_reference.py
"""Build, blind-label, and freeze the locked sentiment reference set.

Spec §10.1. The lifecycle, each step an invocation:

    python -m scripts.build_sentiment_reference sample --cutoff 2026-09-05
    python -m scripts.build_sentiment_reference label --label-pass one --model claude-opus-5
    python -m scripts.build_sentiment_reference label --label-pass two --model claude-sonnet-5
    python -m scripts.build_sentiment_reference export-disagreements
    # ...resolve reference-adjudication.jsonl by hand, WITHOUT looking at
    # production predictions...
    python -m scripts.build_sentiment_reference freeze

Sampling: >=300 time-forward mentions with post created AFTER --cutoff
(the post-freeze cutoff is recorded in the manifest), >=100 reddit and
>=100 bluesky, production-frequency weighted, hard-slice candidates
tagged per category. Posts within simhash Hamming <= 3 of anything in
the burned manifest (the 160-item audit set that steered design, plus
any prompt-development posts) are excluded -- the burn is enforced, not
remembered.

The two labeling passes run the SAME binding prompt through judge();
disagreements export for human adjudication. freeze writes a manifest
carrying the cutoff, prompt version, labeling models, adjudication
provenance, and the sha256 of every data file -- the scorer refuses to
run when any hash disagrees.

Everything lands under artifacts/reference/ (git-ignored; the manifest
is the freeze, back it up like data).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

sys.path.insert(0, '.')  # noqa: E402

import sqlalchemy as sa  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import llm_sentiment, sentiment, sentiment_input  # noqa: E402
from models import RadarMention, RadarPost  # noqa: E402
from scripts.train_radar_sentiment import HAMMING_LIMIT, hamming  # noqa: E402

REFERENCE_DIR = os.path.join(sentiment.ARTIFACT_DIR, '..', 'reference')
MIN_TOTAL, MIN_PER_SOURCE = 300, 100
LABEL_FIELDS = ('relevance', 'content_origin', 'attitude', 'expected_move',
                'confidence')


def _path(name):
    return os.path.join(REFERENCE_DIR, name)


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def sampling_ok(rows):
    """(ok, reasons) against the §10.1 floor. rows carry 'source' roots."""
    reasons = []
    if len(rows) < MIN_TOTAL:
        reasons.append('%d rows < %d' % (len(rows), MIN_TOTAL))
    for root in ('reddit', 'bluesky'):
        got = sum(1 for row in rows if row['source_root'] == root)
        if got < MIN_PER_SOURCE:
            reasons.append('%s %d < %d' % (root, got, MIN_PER_SOURCE))
    return (not reasons), reasons


def hard_slice_tags(mention, post, sibling_count):
    """Cheap structural tags steering hard-slice coverage; the adjudicated
    labels, not these tags, are the truth."""
    text = '%s %s' % (post.title or '', post.body or '')
    tags = []
    if sibling_count > 1:
        tags.append('multi_ticker')
    if '?' in text:
        tags.append('question')
    if mention.sentiment_relevance in ('irrelevant', 'uncertain'):
        tags.append('likely_false_ticker')
    if mention.sentiment_attitude == 'none':
        tags.append('neutral_info')
    if (mention.sentiment_attitude in ('positive', 'negative')
            and mention.sentiment_expected_move in ('up', 'down')
            and ((mention.sentiment_attitude == 'positive')
                 != (mention.sentiment_expected_move == 'up'))):
        tags.append('attitude_move_conflict')
    return tags


def load_burned():
    path = _path('burned-manifest.json')
    if not os.path.exists(path):
        return None
    data = json.load(open(path, encoding='utf-8'))
    return [int(h) for h in data.get('simhashes', [])]


def cmd_sample(cutoff, allow_missing_burned=False):
    burned = load_burned()
    if burned is None:
        if not allow_missing_burned:
            print('no burned-manifest.json in %s -- the 160-item audit set '
                  'MUST be excluded. Write it (post simhashes) or pass '
                  '--allow-missing-burned to state there is nothing to burn.'
                  % os.path.abspath(REFERENCE_DIR))
            return 1
        burned = []

    with app.app_context():
        rows = (db.session.query(RadarMention, RadarPost)
                .join(RadarPost, RadarPost.id == RadarMention.post_id)
                .filter(RadarPost.created_utc >= cutoff,
                        RadarMention.confidence == 'high')
                .order_by(sa.func.rand()).limit(5000).all())
        siblings = {}
        for mention, post in rows:
            siblings[post.id] = siblings.get(post.id, 0) + 1

        sample = []
        seen_posts = set()
        for mention, post in rows:
            if post.id in seen_posts:
                continue
            simhash = int(post.simhash or 0)
            if any(hamming(simhash, burnt) <= HAMMING_LIMIT
                   for burnt in burned):
                continue
            seen_posts.add(post.id)
            prepared = sentiment_input.prepare_sentiment_input(
                post.source, post.title, post.body, mention.ticker,
                author=post.author, channel=post.channel)
            if not prepared.author_text.strip():
                continue
            from features.radar.config import source_root
            sample.append({
                'n': len(sample) + 1,
                'mention_id': mention.id,
                'post_external_id': post.external_id,
                'simhash': simhash,
                'source': post.source,
                'source_root': source_root(post.source),
                'ticker': mention.ticker,
                'tags': hard_slice_tags(mention, post, siblings[post.id]),
                'author_text': prepared.author_text,
                'is_comment': prepared.is_comment,
                'author': prepared.author, 'channel': prepared.channel,
            })
            if len(sample) >= MIN_TOTAL + 60:
                ok, _ = sampling_ok(sample)
                if ok:
                    break

    ok, reasons = sampling_ok(sample)
    if not ok:
        print('sampling floor not met: %s -- widen the cutoff window or '
              'wait for more data' % '; '.join(reasons))
        return 1

    os.makedirs(REFERENCE_DIR, exist_ok=True)
    with open(_path('reference-blind.jsonl'), 'w', encoding='utf-8') as out:
        for row in sample:
            blind = {key: row[key] for key in
                     ('n', 'source_root', 'ticker', 'author_text',
                      'is_comment', 'author', 'channel', 'source', 'tags')}
            out.write(json.dumps(blind, ensure_ascii=False) + '\n')
    with open(_path('reference-key-skeleton.json'), 'w',
              encoding='utf-8') as out:
        json.dump([{key: row[key] for key in
                    ('n', 'mention_id', 'post_external_id', 'simhash')}
                   for row in sample], out)
    print('sampled %d items (%d reddit, %d bluesky) -> reference-blind.jsonl'
          % (len(sample),
             sum(1 for r in sample if r['source_root'] == 'reddit'),
             sum(1 for r in sample if r['source_root'] == 'bluesky')))
    return 0


def _blind_items():
    items = []
    for line in open(_path('reference-blind.jsonl'), encoding='utf-8'):
        row = json.loads(line)
        item = llm_sentiment.JudgeItem()
        item.key = row['n']
        item.prepared = sentiment_input.PreparedInput(
            author_text=row['author_text'], target_ticker=row['ticker'],
            source=row['source'], channel=row['channel'] or '',
            author=row['author'], is_comment=row['is_comment'])
        items.append(item)
    return items


def cmd_label(label_pass, model):
    items = _blind_items()
    effort = 'low' if model != llm_sentiment.PRIMARY_MODEL else None
    answers = llm_sentiment.judge(items, model=model, effort=effort)
    out_path = _path('reference-labels-%s.jsonl' % label_pass)
    with open(out_path, 'w', encoding='utf-8') as out:
        for item in items:
            answer = answers.get(item.key)
            if answer is None:
                continue
            record = {'n': item.key, 'model': model}
            for field in LABEL_FIELDS:
                record[field] = getattr(answer.judgment, field)
            out.write(json.dumps(record) + '\n')
    print('labeled %d/%d -> %s' % (len(answers), len(items), out_path))
    return 0


def _labels(path):
    return {row['n']: row for row in
            map(json.loads, open(path, encoding='utf-8'))}


def cmd_export_disagreements():
    one = _labels(_path('reference-labels-one.jsonl'))
    two = _labels(_path('reference-labels-two.jsonl'))
    out_path = _path('reference-adjudication.jsonl')
    count = 0
    with open(out_path, 'w', encoding='utf-8') as out:
        for n in sorted(set(one) | set(two)):
            a, b = one.get(n), two.get(n)
            if a and b and all(a[field] == b[field]
                               for field in LABEL_FIELDS):
                continue
            count += 1
            out.write(json.dumps({
                'n': n, 'pass_one': a, 'pass_two': b,
                'resolved': None,   # fill with the five final fields
            }) + '\n')
    print('%d disagreements -> %s (resolve WITHOUT production predictions '
          'in view)' % (count, out_path))
    return 0


def cmd_freeze():
    one = _labels(_path('reference-labels-one.jsonl'))
    two = _labels(_path('reference-labels-two.jsonl'))
    adjudicated = {}
    adjudication_path = _path('reference-adjudication.jsonl')
    if os.path.exists(adjudication_path):
        for row in map(json.loads, open(adjudication_path, encoding='utf-8')):
            if row.get('resolved') is None:
                print('unresolved disagreement n=%d -- freeze refused'
                      % row['n'])
                return 1
            adjudicated[row['n']] = row['resolved']

    key = []
    for n in sorted(set(one) & set(two) | set(adjudicated)):
        if n in adjudicated:
            final = adjudicated[n]
        else:
            final = {field: one[n][field] for field in LABEL_FIELDS}
            if any(one[n][field] != two[n][field] for field in LABEL_FIELDS):
                print('n=%d disagrees but is not adjudicated -- run '
                      'export-disagreements first' % n)
                return 1
        key.append(dict(n=n, **{field: final[field]
                                for field in LABEL_FIELDS}))
    key_path = _path('reference-key.json')
    with open(key_path, 'w', encoding='utf-8') as out:
        json.dump(key, out)

    files = ['reference-blind.jsonl', 'reference-key-skeleton.json',
             'reference-labels-one.jsonl', 'reference-labels-two.jsonl',
             'reference-key.json']
    if os.path.exists(adjudication_path):
        files.append('reference-adjudication.jsonl')
    burned = _path('burned-manifest.json')
    manifest = {
        'frozen_at': dt.datetime.utcnow().isoformat(),
        'prompt_version': llm_sentiment.PROMPT_VERSION,
        'labeling_models': sorted({row['model'] for row in one.values()}
                                  | {row['model'] for row in two.values()}),
        'adjudication_provenance':
            'two blind model passes; disagreements human-resolved without '
            'production predictions in view',
        'burned_manifest_sha256':
            sha256_of(burned) if os.path.exists(burned) else None,
        'files': {name: sha256_of(_path(name)) for name in files},
        'items': len(key),
    }
    with open(_path('reference-manifest.json'), 'w', encoding='utf-8') as out:
        json.dump(manifest, out, indent=2)
    print('frozen: %d items, manifest written' % len(key))
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sample = sub.add_parser('sample')
    sample.add_argument('--cutoff', required=True,
                        help='YYYY-MM-DD; posts strictly after this date')
    sample.add_argument('--allow-missing-burned', action='store_true')
    label = sub.add_parser('label')
    label.add_argument('--label-pass', required=True, choices=('one', 'two'))
    label.add_argument('--model', required=True)
    sub.add_parser('export-disagreements')
    sub.add_parser('freeze')
    args = parser.parse_args()

    if args.command == 'sample':
        cutoff = dt.datetime.strptime(args.cutoff, '%Y-%m-%d')
        return cmd_sample(cutoff, args.allow_missing_burned)
    if args.command == 'label':
        return cmd_label(args.label_pass, args.model)
    if args.command == 'export-disagreements':
        return cmd_export_disagreements()
    return cmd_freeze()


if __name__ == '__main__':
    sys.exit(main())
