# personal_apps/scratchpad/label_export/freeze_recall.py
"""Freeze the recall wave's evaluation set ONCE, by mention id.

The existing locked sets (test-natural, test-hard) are drawn from the
production export, which holds only mentions the extractor ACCEPTED. They
therefore say nothing about how the model handles a company named without
its symbol, a symbol typed in lowercase, or a person standing for a
company -- the classes the recall waves exist to teach it. Without a
locked slice of the waves, every number about those classes would be
in-sample.

    cd personal_apps && PYTHONPATH=. python -m scratchpad.label_export.freeze_recall

Grouped by POST, so a post's several ticker rows never straddle the
boundary, and stratified by rejection cause, so the small classes
(metonym, cashtags outside the universe) are not rounded away. Refuses to
overwrite: a locked set that can be regenerated is not locked.
"""
import collections
import json
import os
import random
import sys

ROOT = r'C:\Users\michi\Desktop\radar_labels'
CANDIDATES = [os.path.join(ROOT, 'candidates-2026-09-06.jsonl'),
              os.path.join(ROOT, 'candidates-topup-2026-09-06.jsonl')]
LABELS = os.path.join(ROOT, 'labels-recall.jsonl')
OUT = os.path.join(ROOT, 'test-recall.json')
TARGET = 900
SEED = 20260907


def _cause(row):
    return row.get('candidate', {}).get('cause', 'unknown')


def choose(rows, target=TARGET, seed=SEED):
    """Mention ids for the locked set: whole posts, every cause in
    proportion to the pool it came from."""
    rng = random.Random(seed)
    by_post = collections.defaultdict(list)
    for row in rows:
        by_post[row['external_id']].append(row)

    posts_by_cause = collections.defaultdict(list)
    for post, group in by_post.items():
        # A post's cause is its first row's: posts are single-cause in
        # practice, and a tie has to land somewhere.
        posts_by_cause[_cause(group[0])].append(post)

    total_rows = len(rows)
    picked = []
    for cause, posts in sorted(posts_by_cause.items()):
        rng.shuffle(posts)
        rows_in_cause = sum(len(by_post[p]) for p in posts)
        want = max(1, round(target * rows_in_cause / total_rows))
        taken = 0
        for post in posts:
            if taken >= want:
                break
            picked.extend(row['mention_id'] for row in by_post[post])
            taken += len(by_post[post])
    return sorted(picked)


def write(path, ids):
    if os.path.exists(str(path)):
        sys.exit('%s already exists -- a locked set is never regenerated' % path)
    with open(str(path), 'w', encoding='utf-8') as handle:
        json.dump(sorted(ids), handle)


def main():
    labelled = set()
    with open(LABELS, encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                labelled.add(json.loads(line)['mention_id'])
    rows = []
    for path in CANDIDATES:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row['mention_id'] in labelled:
                    rows.append(row)
    ids = choose(rows)
    write(OUT, ids)
    by_cause = collections.Counter(
        _cause(r) for r in rows if r['mention_id'] in set(ids))
    print('locked %d of %d labelled wave rows -> %s' % (len(ids), len(rows), OUT))
    print('by cause:', dict(by_cause))


if __name__ == '__main__':
    main()
