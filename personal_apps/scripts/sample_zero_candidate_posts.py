# personal_apps/scripts/sample_zero_candidate_posts.py
"""Stage 1 of the NER headroom probe: a fixed, uniform sample of the posts
the extractor sees nothing in, plus a dump of the universe, as plain files.

WHY FILES. The finder (GLiNER now, a trained span model later) lives in a
venv with torch and no Flask app; the extractor and the universe live in
the app with no torch. So this stage runs in the app, writes the sample
and the lookup, and stage 2 never imports either. The sample is thereby a
fixed artifact: any future finder is run against the same 3,000 posts and
the numbers compare.

WHAT "ZERO-CANDIDATE" MEANS. `classify()` runs production extraction AND
the loose pass. A post is in this pool only when both found nothing and no
gate fired -- the loose pass finding something makes it a REJECT, which is
a different population, already measured (~11,450 real mentions a week).
This pool is the 66.6% neither pass can see, the one a span model would
search.

    python scripts/sample_zero_candidate_posts.py \
        --raw C:/Users/michi/Desktop/radar_labels/raw/reddit \
        --out C:/Users/michi/Desktop/radar_labels/ner \
        --n 3000
"""
import argparse
import functools
import json
import os
import random
import time

MIN_BODY_CHARS = 40        # the GLiNER probe's floor; shorter posts are noise
DEFAULT_SEED = 20260908


def is_zero_candidate(row, body):
    """Nothing gated it, production found nothing, the loose pass found
    nothing, and there is enough text for a finder to read."""
    return (row.get('gate') is None
            and not row.get('accepted')
            and not row.get('rejected')
            and len(body or '') >= MIN_BODY_CHARS)


def sample_row(line, row):
    """What stage 2 needs and nothing more. `author_text` is the prepared
    text production feeds the judge; `body` is the raw text, kept so the
    spot-check reads what the person wrote."""
    return {
        'external_id': row['external_id'],
        'source': row['source'],
        'kind': row.get('kind'),
        'created_utc': row['created_utc'],
        'title': row.get('title'),
        'body': line.get('body') or '',
        'author_text': row['author_text'],
    }


def sample(lines, n, seed, classify_fn, stats=None):
    """The first `n` zero-candidate posts of a seeded shuffle.

    Shuffled BEFORE classifying rather than classified-then-sampled: the
    latter would classify the whole week to pick 3,000, and the former
    reads roughly n / 0.666 posts and stops. Same distribution, since the
    shuffle is uniform over the week.
    """
    order = list(lines)
    random.Random(seed).shuffle(order)
    out, classified = [], 0
    for line in order:
        classified += 1
        row = classify_fn(line)
        if is_zero_candidate(row, line.get('body')):
            out.append(sample_row(line, row))
            if len(out) >= n:
                break
    if stats is not None:
        stats['classified'] = classified
    return out


def without_symbols(lookup, excluded):
    """The lookup minus `excluded`, as a new dict. Reproduces a sample drawn
    under an older universe: the dev universe was 88 symbols short of
    production until 2026-09-08 and the benchmark sample was drawn then."""
    excluded = set(excluded)
    return {symbol: entry for symbol, entry in lookup.items() if symbol not in excluded}


def dump_lookup(lookup, aliases):
    """The universe as stage 2 reads it: names and distinctive tokens only,
    tokens sorted so the file is stable across runs."""
    return {
        'symbols': {symbol: {'name': entry.get('name'),
                             'distinctive': sorted(entry.get('distinctive') or ())}
                    for symbol, entry in lookup.items()},
        'aliases': dict(aliases),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--raw', required=True, help='DIR/<day>/<sub>.jsonl')
    parser.add_argument('--out', required=True)
    parser.add_argument('--n', type=int, default=3000)
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--exclude-symbols', default=None,
                        help='JSON list of symbols to remove from the universe before classifying')
    parser.add_argument('--exclude-aliases', default=None,
                        help='JSON list of alias keys to remove for this run (reproduces an older table)')
    parser.add_argument('--lookup-only', action='store_true',
                        help='write lookup.json and nothing else')
    args = parser.parse_args(argv)

    from scripts import measure_extractor_population as pop
    from app import app
    from features.radar import universe

    started = time.perf_counter()
    with app.app_context():
        lookup = universe.load_lookup()
    if args.exclude_aliases:
        with open(args.exclude_aliases, encoding='utf-8') as handle:
            for key in json.load(handle):
                # The loose pass reads the module table; the sample must be
                # drawn under the table that existed when the benchmark was.
                pop.NAME_ALIASES.pop(key, None)
        pop._NAME_INDEX_CACHE[:] = []
    aliases = dict(pop.NAME_ALIASES)
    aliases.update(pop.METONYMS)
    os.makedirs(args.out, exist_ok=True)
    if args.lookup_only:
        with open(os.path.join(args.out, 'lookup.json'), 'w', encoding='utf-8') as handle:
            json.dump(dump_lookup(lookup, aliases), handle, ensure_ascii=False)
        print('lookup.json: %d symbols, %d aliases' % (len(lookup), len(aliases)))
        return
    if args.exclude_symbols:
        with open(args.exclude_symbols, encoding='utf-8') as handle:
            excluded = json.load(handle)
        lookup = without_symbols(lookup, excluded)
        print('universe minus %d excluded symbols: %d' % (len(excluded), len(lookup)), flush=True)
    words = pop.common_words(args.raw)
    shapes = pop.name_shapes(args.raw)
    lines = list(pop.iter_raw(args.raw))
    print('raw posts: %d; ordinary words: %d; name-shaped tokens: %d  (%.0fs)'
          % (len(lines), len(words), len(shapes), time.perf_counter() - started),
          flush=True)

    classify_fn = functools.partial(pop.classify, lookup=lookup,
                                    is_common=words.__contains__, name_shapes=shapes)
    stats = {}
    started = time.perf_counter()
    rows = sample(lines, args.n, args.seed, classify_fn, stats)
    elapsed = time.perf_counter() - started

    sample_path = os.path.join(args.out, 'sample-%d.jsonl' % args.n)
    with open(sample_path, 'w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    if not args.exclude_symbols:
        with open(os.path.join(args.out, 'lookup.json'), 'w', encoding='utf-8') as handle:
            json.dump(dump_lookup(lookup, aliases), handle, ensure_ascii=False)

    print('sampled %d zero-candidate posts from %d classified (%.1f%% of the '
          'shuffled prefix), seed %d, %.0fs -> %s'
          % (len(rows), stats['classified'],
             100.0 * len(rows) / max(1, stats['classified']),
             args.seed, elapsed, sample_path))


if __name__ == '__main__':
    main()
