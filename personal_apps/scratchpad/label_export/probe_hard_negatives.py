# personal_apps/scratchpad/label_export/probe_hard_negatives.py
"""Did the hard negatives actually fix the judge? A held-out probe.

The 2026-09-08 audit found the judge rubber-stamps (symbol, text) pairs a
finder proposes: `corn` 1.00 in "buttcorn", `Abt` 0.99 in "about", `nat`
0.97 in "nat gas", `MT` 0.92 inside "LQMT". The retrain put 1,553
constructed pairs in front of it. Neither existing measurement can say
whether that worked:

- the three older locked sets and the 746-row trial audit all predate the
  extractor change and hold no such pair;
- the hard-negative wave itself went entirely into training, with nothing
  held out (a gap in how it was built, named here rather than hidden).

So this draws FRESH pairs by the same construction rules from the same raw
week, excluding every post any wave, locked set or audit has used, and
scores both checkpoints on them. Every pair is irrelevant by
construction, so the score is simply the false-accept rate: how often a
model says `relevant` about a symbol nobody mentioned. Lower is better,
and the difference between the two models is the answer.

    cd personal_apps && PYTHONPATH=. <torch venv python> \\
        scratchpad/label_export/probe_hard_negatives.py \\
        --live C:/Users/michi/Desktop/radar_labels/encoder/model-train17090-20260907-192428 \\
        --new  C:/Users/michi/Desktop/radar_labels/encoder/model-train19877-20260908-221023
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from features.radar import trial_audit  # noqa: E402
import build_hard_negatives as builder  # noqa: E402
import hard_negatives as hn  # noqa: E402

ROOT = builder.ROOT
WAVE_EXPORTS = ('candidates-hardneg.jsonl', 'candidates-newshape-2026-09-08.jsonl')


def posts_of(rows):
    """Every external id a wave's export mentions."""
    return {row['external_id'] for row in rows if row.get('external_id')}


def widen(exclusions, used_posts):
    """The builder's exclusions plus the posts earlier waves already spent."""
    exclusions.external_ids |= set(used_posts)
    return exclusions


def used_posts(root=ROOT, exports=WAVE_EXPORTS):
    out = set()
    for name in exports:
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as handle:
            out |= posts_of(json.loads(line) for line in handle if line.strip())
    return out


def score(pairs, verdicts):
    """False accepts over the pairs a model answered.

    Every pair is irrelevant by construction, so `relevant` is wrong and
    nothing else is: `uncertain` keeps the mention off the board, which is
    the behaviour the board needs even if it is not a confident rejection.
    """
    answered = [p for p in pairs if p['external_id'] in verdicts]
    wrong = [p for p in answered
             if verdicts[p['external_id']].get('relevance') == 'relevant']
    by_kind = collections.Counter(p['kind'] for p in wrong)
    return {'total': len(answered), 'false_accepts': len(wrong),
            'by_kind': dict(by_kind),
            'rate': trial_audit.wilson_interval(len(wrong), len(answered))
                    if answered else None,
            'wrong': wrong}


def build(n, seed, log=print):
    """Fresh constructed pairs, one per post, none of them ever trained on."""
    lookup = json.load(open(builder.LOOKUP, encoding='utf-8'))['symbols']
    exclusions = widen(builder.load_exclusions(), used_posts())
    log('excluding %d posts (locked sets, audits, probe, and the waves already spent)'
        % len(exclusions.external_ids))
    sizes = {'subword': n // 2, 'ordinary': n // 2, 'index': max(1, n // 10)}
    caps = {'subword': max(2, n // 40), 'ordinary': max(2, n // 40), 'index': n // 5}
    pairs, _seen = builder.build(builder.RAW, lookup, exclusions, seed,
                                 sizes=sizes, caps=caps, log=log)
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--live', required=True)
    parser.add_argument('--new', required=True)
    parser.add_argument('--n', type=int, default=400)
    parser.add_argument('--seed', type=int, default=20260909)
    parser.add_argument('--out', default=os.path.join(ROOT, 'probe-hardneg-heldout.md'))
    args = parser.parse_args(argv)

    pairs = build(args.n, args.seed)
    print('probe pairs: %d  %s' % (len(pairs), dict(collections.Counter(
        p['kind'] for p in pairs))))
    rows = [{'mention_id': p['external_id'], 'ticker': p['symbol'],
             'text': p['author_text'], 'source': p.get('source', ''),
             'title': p.get('title'), 'body': p['author_text'],
             'channel': '', 'author': None}
            for p in pairs]

    import compare_judges as cj

    results = {}
    for name, model_dir in (('live', args.live), ('new', args.new)):
        verdicts = cj.predict(model_dir, [dict(r, mention_id=r['mention_id']) for r in rows])
        results[name] = score(pairs, verdicts)
        got = results[name]
        print('%-5s false accepts %d of %d (%.3f, %.3f-%.3f)  %s'
              % (name, got['false_accepts'], got['total'], got['rate']['point'],
                 got['rate']['lower'], got['rate']['upper'], got['by_kind']))

    lines = ['# Held-out hard negatives: does the retrain still rubber-stamp?', '',
             'Pairs built by the same rules as the training wave, from the same raw',
             'week, on posts NO wave, locked set or audit has used. Every pair is',
             'irrelevant by construction, so the score is the false-accept rate.', '',
             '| model | false accepts | of | rate (Wilson 95%) | by kind |',
             '|---|---|---|---|---|']
    for name in ('live', 'new'):
        got = results[name]
        lines.append('| %s | %d | %d | %.3f (%.3f-%.3f) | %s |'
                     % (name, got['false_accepts'], got['total'], got['rate']['point'],
                        got['rate']['lower'], got['rate']['upper'], got['by_kind']))
    better = results['new']['rate']['point'] < results['live']['rate']['point']
    lines += ['', '**The retrain %s the serving judge on constructed pairs.**'
              % ('IMPROVES on' if better else 'does NOT improve on')]
    lines += ['', '## What the retrain still accepts (up to 40)', '']
    for pair in results['new']['wrong'][:40]:
        lines.append('- `%s` via %r [%s] -- %s' % (
            pair['symbol'], pair['evidence'], pair['kind'],
            pair['author_text'].replace('\n', ' ')[:200]))
    with open(args.out, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    print('wrote', args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
