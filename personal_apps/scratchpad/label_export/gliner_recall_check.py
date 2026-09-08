# personal_apps/scratchpad/label_export/gliner_recall_check.py
"""How much of what we KNOW is a company mention does zero-shot GLiNER find?

The headroom probe used GLiNER as the finder, so its number is a floor
that sits GLiNER's miss rate below the ceiling. Reading 200 of its blanks
bounded that directly (>= 79-85% post recall). This is the cross-check
from the other side: the span dataset holds 13,933 spans a teacher
confirmed name a company, with their exact character offsets. Run GLiNER
over those posts and count the spans it covers -- overall, and by surface
form, because the zero-candidate pool never contains an ALLCAPS symbol
and what matters there is the Title-case and lowercase recall.

Runs in the encoder venv. Reads `spans-<date>.jsonl` from span_dataset.

    C:/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe
        scratchpad/label_export/gliner_recall_check.py
        --spans C:/Users/michi/Desktop/radar_labels/spans-2026-09-07.jsonl
        --out   C:/Users/michi/Desktop/radar_labels/ner/gliner-recall
"""
import argparse
import collections
import json
import os
import re
import sys
import time

GLINER_MODEL = 'urchade/gliner_small-v2.1'
LABELS = ['publicly traded company', 'company', 'stock ticker']
THRESHOLD = 0.5


def covered(span, entities):
    """Any shared character. GLiNER widens ('Nvidia GPUs') and narrows;
    either still found the mention. Touching is not overlap."""
    start, end = span
    return any(e['start'] < end and e['end'] > start for e in entities)


def kind_of(surface):
    if surface.startswith('$'):
        return 'cashtag'
    if re.fullmatch(r'[A-Z0-9.\-/]{1,6}', surface):
        return 'ALLCAPS'
    if re.fullmatch(r'[A-Z][a-z]+', surface):
        return 'Titlecase'
    if re.fullmatch(r'[a-z]+', surface):
        return 'lowercase'
    return 'other'


def recall_table(examples, entities_per_example):
    by_kind = collections.defaultdict(lambda: [0, 0])
    spans = found = 0
    posts_with_spans = posts_hit = 0
    entities = off_span = 0
    for example, entities_here in zip(examples, entities_per_example):
        entities += len(entities_here)
        for entity in entities_here:
            if not any(entity['start'] < e and entity['end'] > s
                       for s, e, _ in example['spans']):
                off_span += 1
        if not example['spans']:
            continue
        posts_with_spans += 1
        hit_here = False
        for start, end, _ticker in example['spans']:
            spans += 1
            kind = kind_of(example['text'][start:end])
            by_kind[kind][1] += 1
            if covered((start, end), entities_here):
                found += 1
                by_kind[kind][0] += 1
                hit_here = True
        posts_hit += hit_here
    return {'spans': spans, 'found': found, 'by_kind': dict(by_kind),
            'posts_with_spans': posts_with_spans, 'posts_hit': posts_hit,
            'entities': entities, 'entities_off_span': off_span}


def find(examples, batch_size, threshold):
    import torch
    from gliner import GLiNER

    model = GLiNER.from_pretrained(GLINER_MODEL)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = model.to(device).eval()
    out = []
    for start in range(0, len(examples), batch_size):
        chunk = examples[start:start + batch_size]
        with torch.no_grad():
            batches = model.batch_predict_entities(
                [e['text'] for e in chunk], LABELS, threshold=threshold)
        out.extend(batches)
        if (start // batch_size) % 25 == 0:
            print('  gliner %d/%d' % (min(start + batch_size, len(examples)), len(examples)),
                  file=sys.stderr, flush=True)
    return out, device


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--spans', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--threshold', type=float, default=THRESHOLD)
    parser.add_argument('--only-with-spans', action='store_true',
                        help='skip the 4,486 negative-only posts (faster; loses the off-span count on them)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    with open(args.spans, encoding='utf-8') as handle:
        examples = [json.loads(line) for line in handle if line.strip()]
    if args.only_with_spans:
        examples = [e for e in examples if e['spans']]
    started = time.perf_counter()
    entities, device = find(examples, args.batch, args.threshold)
    elapsed = time.perf_counter() - started

    table = recall_table(examples, entities)
    table['elapsed_s'] = round(elapsed, 1)
    table['device'] = device
    table['examples'] = len(examples)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'summary.json'), 'w', encoding='utf-8') as handle:
        json.dump(table, handle, indent=1)
    # The misses themselves, so the kinds can be read rather than guessed at.
    with open(os.path.join(args.out, 'misses.jsonl'), 'w', encoding='utf-8') as handle:
        for example, entities_here in zip(examples, entities):
            for start, end, ticker in example['spans']:
                if not covered((start, end), entities_here):
                    handle.write(json.dumps({'ticker': ticker, 'surface': example['text'][start:end],
                                             'kind': kind_of(example['text'][start:end]),
                                             'text': example['text'][:300]}, ensure_ascii=False) + '\n')

    print('examples %d (%d with spans)   %s   %.0fs' % (len(examples), table['posts_with_spans'], device, elapsed))
    print('span recall      %d / %d = %.1f%%' % (table['found'], table['spans'], 100.0 * table['found'] / max(1, table['spans'])))
    print('post recall      %d / %d = %.1f%%' % (table['posts_hit'], table['posts_with_spans'], 100.0 * table['posts_hit'] / max(1, table['posts_with_spans'])))
    for kind, (f, n) in sorted(table['by_kind'].items(), key=lambda kv: -kv[1][1]):
        print('  %-10s %5d / %5d = %5.1f%%' % (kind, f, n, 100.0 * f / max(1, n)))
    print('entities %d, off any known span %d (%.0f%%; negatives are not exhaustive, read misses.jsonl)'
          % (table['entities'], table['entities_off_span'], 100.0 * table['entities_off_span'] / max(1, table['entities'])))


if __name__ == '__main__':
    main()
