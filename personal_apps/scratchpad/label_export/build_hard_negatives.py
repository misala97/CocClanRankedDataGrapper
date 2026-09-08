# personal_apps/scratchpad/label_export/build_hard_negatives.py
"""Build the hard-negative wave for the encoder judge from the raw week.

Reads the captured Reddit week (scripts/capture_arctic_raw.py's layout),
constructs (symbol, text) pairs by the rules in hard_negatives.py, joins
the reader's verdicts on the NER probe (kind `read`), keeps every post the
locked sets and the audits hold OUT, and writes the wave in the label
harness's shapes so train_encoder.py reads it like any other wave:

    radar_labels/labels-hardneg.jsonl       the labels
    radar_labels/candidates-hardneg.jsonl   the texts (export shape)
    radar_labels/hardneg-report.md          counts by kind and symbol
    radar_labels/hardneg-spotread-50.md     50 constructed rows to read

No model is called and nothing is spent. Run from personal_apps/:

    PYTHONPATH=. python scratchpad/label_export/build_hard_negatives.py
"""
import argparse
import collections
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from features.radar import extraction  # noqa: E402
from features.radar.config import (NAME_SHAPES, ORDINARY_WORDS,  # noqa: E402
                                   is_automated_author, looks_like_bot_feed)
import hard_negatives as hn  # noqa: E402

ROOT = r'C:\Users\michi\Desktop\radar_labels'
RAW = os.path.join(ROOT, 'raw', 'reddit')
LOOKUP = os.path.join(ROOT, 'ner', 'lookup.json')
READ = os.path.join(ROOT, 'hardneg-read-2026-09-08.json')
PROBE_SAMPLE = os.path.join(ROOT, 'ner', 'sample-3000.jsonl')
EXPORT = os.path.join(ROOT, 'export-2026-09-05.jsonl')
RECALL_EXPORTS = [os.path.join(ROOT, 'candidates-2026-09-06.jsonl'),
                  os.path.join(ROOT, 'candidates-topup-2026-09-06.jsonl')]
LOCKED = [os.path.join(ROOT, n) for n in ('test-natural.json', 'test-hard.json',
                                          'test-recall.json')]
TRIAL_BLIND = os.path.join(ROOT, 'trial-audit', 'blind.jsonl')
AUDIT_200 = os.path.join(ROOT, 'audit-200.jsonl')
OUT_LABELS = os.path.join(ROOT, 'labels-hardneg.jsonl')
OUT_EXPORT = os.path.join(ROOT, 'candidates-hardneg.jsonl')
OUT_REPORT = os.path.join(ROOT, 'hardneg-report.md')
OUT_SPOT = os.path.join(ROOT, 'hardneg-spotread-50.md')

TEXT_LIMIT = 2000          # label_data.TEXT_LIMIT: what the judge reads
MIN_TEXT = 20              # shorter than this there is nothing to judge
RESERVOIR = 40             # candidates kept per (kind, symbol) before selection
SIZES = {'subword': 600, 'ordinary': 800, 'index': 100}
CAPS = {'subword': 6, 'ordinary': 8, 'index': 60}
WORDLIKE_SHARE = 0.7


def word_shaped(symbol, ordinary_words, name_shapes):
    """A symbol a finder would cut out of prose: an ordinary word (`corn`,
    `be`, `go`) or a token the corpus writes like a name (`dive`, `twin`)."""
    low = symbol.lower()
    return low in ordinary_words or low in name_shapes


def pairs_for(raw, lookup, ordinary_words, name_shapes):
    """Every constructed pair on one raw post's AUTHORED text."""
    if is_automated_author(raw['source'], raw.get('author')):
        return []
    prepared = extraction.prepare_extraction_input(
        raw['source'], raw.get('title'), raw.get('body') or '',
        author=raw.get('author'), channel=raw.get('channel'))
    if looks_like_bot_feed('%s %s' % (prepared.author_text, prepared.thread_context)):
        return []
    text = (prepared.author_text or '')[:TEXT_LIMIT]
    if len(text.strip()) < MIN_TEXT:
        return []
    found = []
    for kind, pairs in (
            ('subword', hn.subword_pairs(text, lookup)),
            ('ordinary', hn.ordinary_word_pairs(text, lookup, ordinary_words, name_shapes)),
            ('index', hn.index_name_pairs(text, lookup))):
        for symbol, evidence in pairs:
            if kind == 'subword' and len(symbol) < 3 and not word_shaped(
                    symbol, ordinary_words, name_shapes):
                continue          # `ne` ending `done`: noise, not a finder's cut
            found.append({'external_id': raw['external_id'], 'source': raw['source'],
                          'created_utc': raw.get('created_utc'), 'title': raw.get('title'),
                          'kind': kind, 'symbol': symbol, 'evidence': evidence,
                          'author_text': text})
    return found


def tiered_select(pairs, n, per_symbol_cap, seed, prefer, share):
    """`share` of `n` from the preferred pairs first, the rest from all."""
    first = hn.select([p for p in pairs if prefer(p)], int(round(share * n)),
                      per_symbol_cap, seed)
    taken = {(p['external_id'], p['symbol']) for p in first}
    rest = hn.select([p for p in pairs if (p['external_id'], p['symbol']) not in taken],
                     n - len(first), per_symbol_cap, seed + 1)
    # the second pass must respect the caps the first one already used
    per_symbol = collections.Counter(p['symbol'] for p in first)
    posts = {p['external_id'] for p in first}
    out = list(first)
    for pair in rest:
        if pair['external_id'] in posts or per_symbol[pair['symbol']] >= per_symbol_cap:
            continue
        per_symbol[pair['symbol']] += 1
        posts.add(pair['external_id'])
        out.append(pair)
    return out


def _jsonl(path):
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def iter_raw(raw_dir):
    for path in sorted(glob.glob(os.path.join(raw_dir, '*', '*.jsonl'))):
        yield from _jsonl(path)


def load_exclusions():
    """Posts no constructed row may come from: the three locked sets' posts
    (by id and by text), the trial audit's 746, the 200-row audit, and the
    probe's 3,000 (kind `read` draws from those deliberately)."""
    locked_ids = set()
    for path in LOCKED:
        if os.path.exists(path):
            locked_ids |= set(json.load(open(path, encoding='utf-8')))
    external_ids, texts = set(), set()
    for row in _jsonl(EXPORT):
        if row['mention_id'] in locked_ids:
            external_ids.add(row.get('external_id'))
            texts.add(row.get('author_text') or '')
    for path in RECALL_EXPORTS:
        for row in _jsonl(path):
            if row['mention_id'] in locked_ids:
                external_ids.add(row.get('external_id'))
                texts.add(row.get('author_text') or '')
    for row in _jsonl(TRIAL_BLIND):
        texts.add(row.get('body') or '')
        texts.add('%s %s' % (row.get('title') or '', row.get('body') or ''))
    for row in _jsonl(AUDIT_200):
        texts.add(row.get('text') or '')
    for row in _jsonl(PROBE_SAMPLE):
        external_ids.add(row['external_id'])
    texts.discard('')
    return hn.Exclusions(external_ids=external_ids, texts=texts)


def read_rows(read_path, probe_sample):
    verdicts = json.load(open(read_path, encoding='utf-8'))['verdicts']
    posts = {}
    for row in _jsonl(probe_sample):
        posts[row['external_id']] = {
            'external_id': row['external_id'], 'source': row['source'],
            'created_utc': row.get('created_utc'), 'title': row.get('title'),
            'author_text': (row.get('author_text') or '')[:TEXT_LIMIT]}
    return [hn.read_pair(v, posts) for v in verdicts]


def build(raw_dir, lookup, exclusions, seed, sizes=SIZES, caps=CAPS,
          ordinary_words=ORDINARY_WORDS, name_shapes=NAME_SHAPES, log=print):
    """Constructed pairs from the raw week, reservoir-sampled per (kind,
    symbol) so one symbol cannot flood a kind, then selected under caps."""
    rng = random.Random(seed)
    reservoirs = collections.defaultdict(list)
    seen = collections.Counter()
    posts = 0
    for raw in iter_raw(raw_dir):
        posts += 1
        if posts % 50000 == 0:
            log('  %d posts read' % posts)
        for pair in pairs_for(raw, lookup, ordinary_words, name_shapes):
            if exclusions.holds(pair):
                continue
            key = (pair['kind'], pair['symbol'])
            seen[key] += 1
            bucket = reservoirs[key]
            if len(bucket) < RESERVOIR:
                bucket.append(pair)
            else:
                slot = rng.randrange(seen[key])
                if slot < RESERVOIR:
                    bucket[slot] = pair
    log('read %d posts; %d (kind, symbol) keys, %d candidate pairs seen'
        % (posts, len(seen), sum(seen.values())))
    by_kind = collections.defaultdict(list)
    for (kind, _symbol), bucket in reservoirs.items():
        by_kind[kind].extend(bucket)
    chosen = []
    for kind, n in sizes.items():
        pool = by_kind.get(kind, [])
        if kind == 'subword':
            picked = tiered_select(
                pool, n, caps[kind], seed,
                prefer=lambda p: word_shaped(p['symbol'], ordinary_words, name_shapes),
                share=WORDLIKE_SHARE)
        else:
            picked = hn.select(pool, n, caps[kind], seed)
        log('  %-9s pool %6d -> %4d' % (kind, len(pool), len(picked)))
        chosen.extend(picked)
    return chosen, seen


def report(rows, seen, path, seed):
    lines = ['# Hard-negative wave -- built %s, seed %d' % (
        __import__('time').strftime('%Y-%m-%d %H:%M UTC', __import__('time').gmtime()), seed),
        '', 'Rows by kind and relevance:', '']
    kinds = collections.Counter((r['kind'], r.get('relevance', 'irrelevant')) for r in rows)
    for (kind, rel), n in sorted(kinds.items()):
        lines.append('    %-9s %-11s %5d' % (kind, rel, n))
    lines += ['', 'Symbols per kind (distinct), and the ten most frequent:', '']
    for kind in sorted({r['kind'] for r in rows}):
        symbols = collections.Counter(r['symbol'] for r in rows if r['kind'] == kind)
        lines.append('    %-9s %4d symbols: %s' % (
            kind, len(symbols), ', '.join('%s x%d' % s for s in symbols.most_common(10))))
    lines += ['', 'Candidate pairs seen in the raw week before selection (top 25 keys):', '']
    for (kind, symbol), n in seen.most_common(25):
        lines.append('    %-9s %-6s %7d' % (kind, symbol, n))
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')


def spot_read(rows, path, n, seed):
    constructed = [r for r in rows if r['kind'] != 'read']
    picked = random.Random(seed).sample(constructed, min(n, len(constructed)))
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('# Spot-read: %d constructed rows, seed %d. Mark each PURE '
                     '(irrelevant, as constructed) or NOT.\n\n' % (len(picked), seed))
        for i, r in enumerate(picked, start=1):
            handle.write('### %d. %s  %s  via %r  [%s]\n%s\n\n' % (
                i, r['kind'], r['symbol'], r['evidence'], r['external_id'],
                r['author_text'].replace('\n', ' ')[:600]))
    return picked


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--raw', default=RAW)
    ap.add_argument('--lookup', default=LOOKUP)
    ap.add_argument('--read', default=READ)
    ap.add_argument('--seed', type=int, default=20260908)
    for kind, n in SIZES.items():
        ap.add_argument('--n-%s' % kind, type=int, default=n)
    args = ap.parse_args(argv)
    sizes = {kind: getattr(args, 'n_%s' % kind) for kind in SIZES}

    lookup = json.load(open(args.lookup, encoding='utf-8'))['symbols']
    exclusions = load_exclusions()
    print('exclusions: %d post ids, %d texts' % (len(exclusions.external_ids),
                                                  len(exclusions.texts)))
    rows = read_rows(args.read, PROBE_SAMPLE)
    print('read verdicts: %d (%d relevant)' % (
        len(rows), sum(r['relevance'] == 'relevant' for r in rows)))
    constructed, seen = build(args.raw, lookup, exclusions, args.seed, sizes=sizes)
    rows += constructed
    labels, export = hn.wave_files(rows)
    for path, out in ((OUT_LABELS, labels), (OUT_EXPORT, export)):
        with open(path, 'w', encoding='utf-8') as handle:
            for row in out:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    report(rows, seen, OUT_REPORT, args.seed)
    spot_read(rows, OUT_SPOT, 50, args.seed)
    print('wrote %d rows -> %s, %s; report %s; spot-read %s'
          % (len(rows), OUT_LABELS, OUT_EXPORT, OUT_REPORT, OUT_SPOT))


if __name__ == '__main__':
    main()
