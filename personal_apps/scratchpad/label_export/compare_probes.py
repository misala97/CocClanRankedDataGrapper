# personal_apps/scratchpad/label_export/compare_probes.py
"""Several probe runs side by side, on the same 3,000 posts.

    python scratchpad/label_export/compare_probes.py name=dir name=dir ...
        [--baseline name] [--sample sample-3000.jsonl]

Prints the funnel per run, the pairwise post overlaps, the union, and --
with a baseline -- every relevant pair a run found that the baseline did
not, with its text, so a change to the lookup or the finder is read as
posts rather than believed as a number. Pure; no models.
"""
import argparse
import json
import os
import sys


def jl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def relevant_pairs(run_dir):
    return {(v['external_id'], v['symbol']) for v in jl(os.path.join(run_dir, 'verdicts.jsonl'))
            if v['relevance'] == 'relevant' and v['content_origin'] != 'broadcast_or_automated'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('runs', nargs='+', help='name=dir')
    ap.add_argument('--baseline', default=None)
    ap.add_argument('--sample', default='C:/Users/michi/Desktop/radar_labels/ner/sample-3000.jsonl')
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    runs = dict(item.split('=', 1) for item in args.runs)
    summaries = {name: json.load(open(os.path.join(d, 'summary.json'), encoding='utf-8'))
                 for name, d in runs.items()}
    pairs = {name: relevant_pairs(d) for name, d in runs.items()}
    posts = {name: {p for p, _ in ps} for name, ps in pairs.items()}

    names = list(runs)
    print('%-32s' % '' + ''.join('%10s' % n for n in names))
    for key in ('posts_with_span', 'spans', 'pairs', 'relevant_pairs', 'relevant_posts',
                'extrapolated_relevant_posts_per_week'):
        print('%-32s' % key + ''.join('%10s' % summaries[n].get(key, '-') for n in names))
    print('%-32s' % 'unresolved spans' + ''.join(
        '%10s' % summaries[n]['spans_by_tier'].get('unresolved', 0) for n in names))
    print()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            print('  %s∩%s posts %d  %s-only %d  %s-only %d'
                  % (a, b, len(posts[a] & posts[b]), a, len(posts[a] - posts[b]), b, len(posts[b] - posts[a])))
    union = set().union(*posts.values())
    every = set.intersection(*posts.values())
    print('  union %d posts (%.2f%%), in every run %d' % (len(union), 100.0 * len(union) / 3000, len(every)))

    if args.baseline:
        sample = {r['external_id']: r['author_text'].replace('\n', ' ') for r in jl(args.sample)}
        base = pairs[args.baseline]
        for name in names:
            if name == args.baseline:
                continue
            new = sorted(pairs[name] - base, key=lambda x: x[1])
            lost = sorted(base - pairs[name], key=lambda x: x[1])
            print('\n## %s vs %s: +%d relevant pairs, -%d' % (name, args.baseline, len(new), len(lost)))
            for post, symbol in new:
                print('  + %-5s %s | %s' % (symbol, post, sample.get(post, '')[:140]))
            for post, symbol in lost:
                print('  - %-5s %s | %s' % (symbol, post, sample.get(post, '')[:140]))


if __name__ == '__main__':
    main()
