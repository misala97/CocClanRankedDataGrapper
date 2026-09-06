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
from features.radar import judge_backends, llm_sentiment, sentiment, sentiment_input  # noqa: E402
from models import RadarMention, RadarPost  # noqa: E402
from scripts.train_radar_sentiment import (  # noqa: E402
    BURNED_MANIFEST, HAMMING_LIMIT, hamming)

REFERENCE_DIR = os.path.join(sentiment.ARTIFACT_DIR, '..', 'reference')
MIN_TOTAL, MIN_PER_SOURCE = 300, 100
# Every §10.1 hard-slice category must be represented, separately
# guaranteed rather than hoped for (Codex review, blocker 4).
HARD_SLICE_FLOOR = 10
HARD_SLICE_TAGS = ('multi_ticker', 'question', 'likely_false_ticker',
                   'neutral_info', 'attitude_move_conflict')
LABEL_FIELDS = ('relevance', 'content_origin', 'attitude', 'expected_move',
                'confidence')


def _path(name):
    return os.path.join(REFERENCE_DIR, name)


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def sampling_ok(rows, check_hard_slice=False):
    """(ok, reasons) against the §10.1 floors. rows carry 'source_root'
    and (when check_hard_slice) 'tags'."""
    reasons = []
    if len(rows) < MIN_TOTAL:
        reasons.append('%d rows < %d' % (len(rows), MIN_TOTAL))
    for root in ('reddit', 'bluesky'):
        got = sum(1 for row in rows if row['source_root'] == root)
        if got < MIN_PER_SOURCE:
            reasons.append('%s %d < %d' % (root, got, MIN_PER_SOURCE))
    if check_hard_slice:
        for tag in HARD_SLICE_TAGS:
            got = sum(1 for row in rows if tag in row.get('tags', ()))
            if got < HARD_SLICE_FLOOR:
                reasons.append('hard slice %s: %d < %d'
                               % (tag, got, HARD_SLICE_FLOOR))
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
    """The committed burn list. REQUIRED -- no bypass flag exists: a
    reference set sampled without it can test on design-process data
    (Codex review, blocker 3)."""
    if not os.path.exists(BURNED_MANIFEST):
        return None
    data = json.load(open(BURNED_MANIFEST, encoding='utf-8'))
    return [int(h) for h in data.get('simhashes', [])]


def cmd_sample(cutoff, thin_slice_reason=None):
    burned = load_burned()
    if burned is None:
        print('missing %s -- the burned post list is committed to the repo '
              'and required; there is no bypass.' % BURNED_MANIFEST)
        return 1

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
                # The exact classifier feature text, frozen at sample time
                # with the live universe -- scoring must mask identically
                # to training, not with an empty ticker set (blocker 5).
                'masked_text': sentiment.classifier_text(prepared),
                'is_comment': prepared.is_comment,
                'author': prepared.author, 'channel': prepared.channel,
            })
            if len(sample) >= MIN_TOTAL + 60:
                ok, _ = sampling_ok(sample, check_hard_slice=True)
                if ok:
                    break

    ok, reasons = sampling_ok(sample, check_hard_slice=True)
    if not ok:
        hard_only = all(reason.startswith('hard slice') for reason in reasons)
        if hard_only and thin_slice_reason:
            print('hard-slice floors unmet (%s) -- ACCEPTED with recorded '
                  'ruling: %s' % ('; '.join(reasons), thin_slice_reason))
        else:
            print('sampling floor not met: %s -- widen the cutoff window, '
                  'wait for more data, or (hard-slice floors only) rule it '
                  'through --accept-thin-slice "reason"'
                  % '; '.join(reasons))
            return 1

    os.makedirs(REFERENCE_DIR, exist_ok=True)
    with open(_path('reference-blind.jsonl'), 'w', encoding='utf-8') as out:
        for row in sample:
            blind = {key: row[key] for key in
                     ('n', 'source_root', 'ticker', 'author_text',
                      'masked_text', 'is_comment', 'author', 'channel',
                      'source', 'tags')}
            out.write(json.dumps(blind, ensure_ascii=False) + '\n')
    with open(_path('reference-key-skeleton.json'), 'w',
              encoding='utf-8') as out:
        json.dump([{key: row[key] for key in
                    ('n', 'mention_id', 'post_external_id', 'simhash')}
                   for row in sample], out)
    with open(_path('sampling-meta.json'), 'w', encoding='utf-8') as out:
        json.dump({'sample_cutoff': cutoff.isoformat(),
                   'thin_slice_reason': thin_slice_reason,
                   'sampled_at': dt.datetime.utcnow().isoformat()}, out)
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
    # The heuristic is preserved verbatim in this commit -- it is wrong (it
    # infers a call parameter from a model id, the same shape of mistake as
    # the stage proxy) but replacing it is a configuration change and
    # belongs with the rest of them, not in a refactor that must not move
    # any behaviour.
    effort = 'low' if model != llm_sentiment.PRIMARY_MODEL else None
    backend = judge_backends.construct_backend('anthropic:' + model,
                                               effort=effort)
    answers = llm_sentiment.judge(items, backend)
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

    # The FINAL keyed set must still clear the §10.1 floors: missing label
    # answers can silently shrink it below 300 between sampling and freeze
    # (Codex review, blocker 4).
    blind = {row['n']: row for row in
             map(json.loads,
                 open(_path('reference-blind.jsonl'), encoding='utf-8'))}
    keyed_blind = [blind[entry['n']] for entry in key if entry['n'] in blind]
    meta = json.load(open(_path('sampling-meta.json'), encoding='utf-8'))
    ok, reasons = sampling_ok(keyed_blind, check_hard_slice=True)
    if not ok:
        hard_only = all(reason.startswith('hard slice') for reason in reasons)
        if not (hard_only and meta.get('thin_slice_reason')):
            print('the keyed set no longer clears the floors: %s -- relabel '
                  'the missing items or resample' % '; '.join(reasons))
            return 1

    files = ['reference-blind.jsonl', 'reference-key-skeleton.json',
             'reference-labels-one.jsonl', 'reference-labels-two.jsonl',
             'reference-key.json', 'sampling-meta.json']
    if os.path.exists(adjudication_path):
        files.append('reference-adjudication.jsonl')
    manifest = {
        'frozen_at': dt.datetime.utcnow().isoformat(),
        'sample_cutoff': meta['sample_cutoff'],
        'thin_slice_reason': meta.get('thin_slice_reason'),
        'prompt_version': llm_sentiment.PROMPT_VERSION,
        'labeling_models': sorted({row['model'] for row in one.values()}
                                  | {row['model'] for row in two.values()}),
        'adjudication_provenance':
            'two blind model passes; disagreements human-resolved without '
            'production predictions in view',
        'burned_manifest_sha256':
            sha256_of(BURNED_MANIFEST) if os.path.exists(BURNED_MANIFEST)
            else None,
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
    sample.add_argument('--accept-thin-slice', default=None,
                        help='recorded ruling accepting unmet HARD-SLICE '
                             'floors (total/source floors are never '
                             'waivable)')
    label = sub.add_parser('label')
    label.add_argument('--label-pass', required=True, choices=('one', 'two'))
    label.add_argument('--model', required=True)
    sub.add_parser('export-disagreements')
    sub.add_parser('freeze')
    args = parser.parse_args()

    if args.command == 'sample':
        cutoff = dt.datetime.strptime(args.cutoff, '%Y-%m-%d')
        return cmd_sample(cutoff, thin_slice_reason=args.accept_thin_slice)
    if args.command == 'label':
        return cmd_label(args.label_pass, args.model)
    if args.command == 'export-disagreements':
        return cmd_export_disagreements()
    return cmd_freeze()


if __name__ == '__main__':
    sys.exit(main())
