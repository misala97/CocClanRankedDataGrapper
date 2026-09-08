# personal_apps/scratchpad/label_export/build_spans_v2.py
"""spans-v1 -> spans-v2: fill the names a mention-sampled wave never
labelled, mask the symbols nothing decided. See span_dataset.augment.

Which words count as NAMES: a distinctive listing token (the universe's
own rule, at most four claimants, not itself a symbol) that the corpus
ALSO writes like a name (name_shapes: capitalised mid-sentence often
enough). Either alone is too loose -- distinctive tokens include
`daily` and `senior`, name shapes include `Monday` and `Hello` -- and
the intersection is the part both instruments agree on.

Torch-free, app-free: reads the lookup dump and the instruments file.

    python scratchpad/label_export/build_spans_v2.py \
        --spans C:/Users/michi/Desktop/radar_labels/spans-2026-09-07.jsonl \
        --out   C:/Users/michi/Desktop/radar_labels/spans-v2-2026-09-08.jsonl
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import span_dataset                                        # noqa: E402
import span_lookup                                         # noqa: E402

LABELS_DIR = 'C:/Users/michi/Desktop/radar_labels'

# Proper nouns that are listing tokens (Trump Media, Reddit Inc, Monday.com,
# Daily Journal) and are never that listing when a finance sub writes them.
# The symbol side has config.STOPWORDS for the same reason; this is the
# name side, kept just as short and just as explicit.
VOUCHED_MIN = 3

NAME_STOPLIST = frozenset((
    'trump', 'reddit',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december',
))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--spans', default=LABELS_DIR + '/spans-2026-09-07.jsonl')
    ap.add_argument('--lookup', default=LABELS_DIR + '/ner/lookup.json')
    ap.add_argument('--instruments', default=LABELS_DIR + '/promotion-instruments.json')
    ap.add_argument('--ordinary', default=LABELS_DIR + '/ordinary-words.json')
    ap.add_argument('--out', default=LABELS_DIR + '/spans-v2-2026-09-08.jsonl')
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    with open(args.lookup, encoding='utf-8') as handle:
        dumped = json.load(handle)
    with open(args.instruments, encoding='utf-8') as handle:
        instruments = json.load(handle)
    with open(args.ordinary, encoding='utf-8') as handle:
        ordinary = set(json.load(handle)['words'])
    index = span_lookup.build_index(dumped['symbols'], dumped['aliases'])
    # Distinctive AND name-shaped, and NOT a word the corpus writes in
    # lowercase most of the time ('total', 'daily', 'delta', 'exchange'),
    # and not a proper noun that is never the listing.
    candidates = ((set(index.by_token) & set(instruments['name_shapes']))
                  - ordinary - NAME_STOPLIST)
    symbols = set(dumped['symbols'])

    with open(args.spans, encoding='utf-8') as handle:
        examples = [json.loads(line) for line in handle if line.strip()]

    # Vouched: the teacher has already confirmed this surface form as a
    # company mention at least VOUCHED_MIN times. 'korea', 'south' and
    # 'johnson' are listing tokens the corpus capitalises and nobody has
    # ever judged to name a company; 'nvidia' has 82 gold spans. Silver
    # only extends what gold vouches for into the posts that went
    # unlabelled. Aliases (google, facebook) are added whole: they are not
    # listing tokens and would never pass the distinctive test.
    vouched = collections.Counter(example['text'][s:e].lower()
                                  for example in examples for s, e, _ in example['spans'])
    name_tokens = ({token for token in candidates if vouched[token] >= VOUCHED_MIN}
                   | set(index.aliases))
    filled = collections.Counter()
    masked = collections.Counter()
    out = []
    for example in examples:
        got = span_dataset.augment(example, name_tokens, symbols)
        for s, e in got['silver']:
            filled[example['text'][s:e].lower()] += 1
        for s, e in got['ignore']:
            masked[example['text'][s:e].lstrip('$').upper()] += 1
        out.append(got)
    with open(args.out, 'w', encoding='utf-8') as handle:
        for example in out:
            handle.write(json.dumps(example, ensure_ascii=False) + '\n')

    print('name tokens: %d = (distinctive ∩ name-shaped − ordinary − stoplist = %d) '
          'vouched >= %d by gold, + %d aliases'
          % (len(name_tokens), len(candidates), VOUCHED_MIN, len(index.aliases)))
    print('name tokens: ' + ', '.join(sorted(name_tokens)))
    print('examples %d; gold spans %d; silver added %d in %d posts; masked %d in %d posts'
          % (len(out), sum(len(e['spans']) for e in out), sum(filled.values()),
             sum(1 for e in out if e['silver']), sum(masked.values()),
             sum(1 for e in out if e['ignore'])))
    print('silver top: ' + ', '.join('%s x%d' % kv for kv in filled.most_common(30)))
    print('masked top: ' + ', '.join('%s x%d' % kv for kv in masked.most_common(30)))
    print('-> %s' % args.out)


if __name__ == '__main__':
    main()
