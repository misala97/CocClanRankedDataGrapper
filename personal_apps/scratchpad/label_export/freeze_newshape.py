# personal_apps/scratchpad/label_export/freeze_newshape.py
"""Freeze the FOURTH locked set: the mention shapes the extractor gained
on 2026-09-08 (Title-case symbol, lowercase symbol, name alone, alias).

The other three locked sets cannot measure these. `test-natural` and
`test-hard` are drawn from the production export, which holds only what
the OLD rules accepted; `test-recall` is the loose pass's candidates,
which had no Title-case or alias tier at all. Without this set every
number about the new shapes would be in-sample.

Whole posts, stratified by shape in the proportion the wave has them,
seeded. Refuses to overwrite: a locked set that can be regenerated is not
locked.

    cd personal_apps && PYTHONPATH=. python scratchpad/label_export/freeze_newshape.py \\
        --labels C:/Users/michi/Desktop/radar_labels/labels-newshape.jsonl \\
        --export C:/Users/michi/Desktop/radar_labels/candidates-newshape-2026-09-08.jsonl \\
        --out C:/Users/michi/Desktop/radar_labels/test-newshape.json --target 320
"""
import argparse
import collections
import json
import os
import random
import sys

SEED = 20260908


def _read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_rows(labels_path, export_path):
    """Labelled wave rows carrying the post they came from."""
    export = {row['mention_id']: row for row in _read_jsonl(export_path)}
    rows = []
    for label in _read_jsonl(labels_path):
        source = export.get(label['mention_id'])
        if source is None:
            continue
        rows.append({'mention_id': label['mention_id'],
                     'stratum': label['stratum'],
                     'post_id': source.get('external_id') or source.get('post_id'),
                     'ticker': label['ticker'],
                     'relevance': label['relevance']})
    return rows


def proportional_quotas(rows):
    counts = collections.Counter(row['stratum'] for row in rows)
    total = sum(counts.values())
    return {stratum: n / total for stratum, n in counts.items()} if total else {}


def pick(rows, target, seed=SEED, quotas=None):
    """Whole posts, per-shape quotas, slack redistributed.

    Overshoots `target` by at most the last post taken -- the same
    convention freeze_test_sets.py uses, because splitting a post is the
    one thing a locked set may not do.
    """
    quotas = quotas or proportional_quotas(rows)
    by_post = collections.OrderedDict()
    for row in sorted(rows, key=lambda r: r['mention_id']):
        by_post.setdefault(row['post_id'], []).append(row)
    # A post's shape is its first row's: rows of one post travel together,
    # so the post is counted once, under one shape.
    posts_by_stratum = collections.defaultdict(list)
    for post, post_rows in by_post.items():
        posts_by_stratum[post_rows[0]['stratum']].append(post)
    rng = random.Random(seed)
    for stratum in sorted(posts_by_stratum):
        rng.shuffle(posts_by_stratum[stratum])

    picked = []
    taken = set()

    def take(stratum, want):
        got = 0
        for post in posts_by_stratum.get(stratum, ()):
            if post in taken or got >= want:
                continue
            taken.add(post)
            picked.extend(by_post[post])
            got += len(by_post[post])
        return got

    for stratum in sorted(quotas):
        take(stratum, int(round(quotas[stratum] * target)))
    # Slack: a shape that ran out hands its rows to the others, round-robin,
    # so the set still reaches its size.
    while len(picked) < target:
        progressed = False
        for stratum in sorted(posts_by_stratum):
            if len(picked) >= target:
                break
            if take(stratum, 1):
                progressed = True
        if not progressed:
            break
    picked.sort(key=lambda r: r['mention_id'])
    return picked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--labels', required=True)
    parser.add_argument('--export', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--target', type=int, default=320)
    parser.add_argument('--seed', type=int, default=SEED)
    args = parser.parse_args(argv)

    if os.path.exists(args.out):
        sys.exit('%s already exists -- a locked set is never regenerated' % args.out)
    rows = load_rows(args.labels, args.export)
    print('labelled wave rows: %d over %d posts'
          % (len(rows), len({r['post_id'] for r in rows})))
    picked = pick(rows, args.target, args.seed)
    json.dump(sorted(r['mention_id'] for r in picked), open(args.out, 'w'))
    print('locked %d rows over %d posts -> %s'
          % (len(picked), len({r['post_id'] for r in picked}), args.out))
    for field in ('stratum', 'relevance'):
        print('  %-10s %s' % (field, dict(collections.Counter(
            r[field] for r in picked))))
    left = [r for r in rows if r['mention_id'] not in {p['mention_id'] for p in picked}]
    print('  trainable remainder %d  %s' % (len(left), dict(collections.Counter(
        r['stratum'] for r in left))))


if __name__ == '__main__':
    main()
