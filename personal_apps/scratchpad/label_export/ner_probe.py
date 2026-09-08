# personal_apps/scratchpad/label_export/ner_probe.py
"""Stage 2 of the NER headroom probe: find, resolve, judge, count.

THE IDEA (Michi's). The target architecture is trained-static-trained: a
span model finds the words that name a company, a lookup maps them to a
symbol, the encoder judges the pair. The span model does not exist yet.
GLiNER, zero-shot, stands in for it, over the posts the extractor sees
nothing in -- and what comes out the end is the prize for building the
real one, counted rather than eyeballed, plus a silver span set from that
exact population.

Runs in the encoder venv (torch, gliner, onnxruntime). Reads the two files
stage 1 wrote and imports no app.

    C:/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe scratchpad/label_export/ner_probe.py
        --sample C:/Users/michi/Desktop/radar_labels/ner/sample-3000.jsonl
        --lookup C:/Users/michi/Desktop/radar_labels/ner/lookup.json
        --out    C:/Users/michi/Desktop/radar_labels/ner/probe-3000
        --artifact-dir C:/Users/michi/Desktop/radar_labels/artifact-base   # what prod runs

The arithmetic between the two model calls -- which pairs are judged,
what counts as a hit, how a sample becomes a weekly number -- is pure and
tested. The model calls are glue.
"""
import argparse
import collections
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import span_lookup                                          # noqa: E402

GLINER_MODEL = 'urchade/gliner_small-v2.1'
LABELS = ['publicly traded company', 'company', 'stock ticker']   # the probe's
THRESHOLD = 0.5
# Zero-candidate posts in the measured week that ALSO clear the 40-char
# body floor stage 1 applies: 70,381 (HANDOFF.md). Not the 132,164 of all
# zero-candidate posts -- the sample never sees a short comment, so a rate
# measured on it must not be scaled to them. Stage 1 agrees from the other
# direction: 3,000 of 8,688 shuffled posts qualified, 34.5% x 198,586 = 68,512.
ZERO_CANDIDATE_POSTS_PER_WEEK = 70_381
UNRESOLVED_TOP_N = 40
SPOTCHECK_N = 50


# ---- the arithmetic ----------------------------------------------------------

def is_kept(verdict):
    """The board's rule: an irrelevant or automated mention leaves every
    surface; unjudged and uncertain stay."""
    return (verdict['relevance'] != 'irrelevant'
            and verdict['content_origin'] != 'broadcast_or_automated')


def is_relevant(verdict):
    """Strict: the encoder said relevant, and a person wrote it."""
    return (verdict['relevance'] == 'relevant'
            and verdict['content_origin'] != 'broadcast_or_automated')


def pairs_from(findings):
    """One (post, symbol) per resolved span, in first-seen order. A post
    naming NVIDIA twice is one pair; the encoder reads the whole text."""
    seen, pairs = set(), []
    for finding in findings:
        if not finding.get('symbol'):
            continue
        key = (finding['external_id'], finding['symbol'])
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    return pairs


def extrapolate(relevant_posts, n_posts, weekly_posts=ZERO_CANDIDATE_POSTS_PER_WEEK):
    if not n_posts:
        return 0.0
    return round(weekly_posts * relevant_posts / n_posts, 2)


def funnel(findings, verdicts, n_posts):
    """Everything the printed funnel shows, from the span rows and the
    pair verdicts. A pair's tier is that of the first span that produced
    it, so per-tier precision is attributable."""
    pairs = pairs_from(findings)
    tier_of = {}
    for finding in findings:
        if finding.get('symbol'):
            tier_of.setdefault((finding['external_id'], finding['symbol']),
                               finding['tier'])

    unresolved = collections.Counter(f['span'] for f in findings
                                     if not f.get('symbol'))
    by_tier = collections.defaultdict(lambda: [0, 0])
    relevant_posts, kept_posts = set(), set()
    relevant_pairs = kept_pairs = 0
    for pair in pairs:
        verdict = verdicts.get(pair)
        if verdict is None:
            continue
        counts = by_tier[tier_of[pair]]
        counts[1] += 1
        if is_relevant(verdict):
            counts[0] += 1
            relevant_pairs += 1
            relevant_posts.add(pair[0])
        if is_kept(verdict):
            kept_pairs += 1
            kept_posts.add(pair[0])

    return {
        'posts_sampled': n_posts,
        'posts_with_span': len({f['external_id'] for f in findings}),
        'spans': len(findings),
        'spans_by_tier': dict(collections.Counter(f['tier'] for f in findings)),
        'unresolved_top': [[text, count]
                           for text, count in unresolved.most_common(UNRESOLVED_TOP_N)],
        'pairs': len(pairs),
        'relevant_pairs': relevant_pairs,
        'kept_pairs': kept_pairs,
        'relevant_posts': len(relevant_posts),
        'kept_posts': len(kept_posts),
        'relevant_rate_by_tier': dict(by_tier),
        'extrapolated_relevant_posts_per_week':
            extrapolate(len(relevant_posts), n_posts),
    }


# ---- the glue ----------------------------------------------------------------

def find_spans(rows, batch_size, threshold=THRESHOLD):
    """GLiNER over `author_text`, the same prepared text the judge reads."""
    import torch
    from gliner import GLiNER

    model = GLiNER.from_pretrained(GLINER_MODEL)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = model.to(device)
    model.eval()
    findings = []
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        with torch.no_grad():
            batches = model.batch_predict_entities(
                [row['author_text'] for row in chunk], LABELS, threshold=threshold)
        for row, entities in zip(chunk, batches):
            for entity in entities:
                findings.append({
                    'external_id': row['external_id'],
                    'span': entity['text'],
                    'label': entity['label'],
                    'score': round(float(entity['score']), 3),
                    'start': entity.get('start'),
                    'end': entity.get('end'),
                })
        if (start // batch_size) % 10 == 0:
            print('  gliner %d/%d' % (min(start + batch_size, len(rows)), len(rows)),
                  file=sys.stderr, flush=True)
    return findings, device


def judge_pairs(pairs, text_by_id, artifact_dir, batch_size):
    """The deployed artifact, through the toy's loader -- same (ticker,
    text) sentence pair production feeds it."""
    import ask_encoder

    numpy, session, tokenizer, config = ask_encoder.load(artifact_dir)
    verdicts = {}
    for start in range(0, len(pairs), batch_size):
        chunk = pairs[start:start + batch_size]
        out = ask_encoder.judge(numpy, session, tokenizer, config,
                                [(symbol, text_by_id[post]) for post, symbol in chunk])
        for pair, heads in zip(chunk, out):
            verdicts[pair] = {
                'relevance': heads['relevance'][0],
                'relevance_p': round(heads['relevance'][1], 3),
                'content_origin': heads['content_origin'][0],
                'origin_p': round(heads['content_origin'][1], 3),
                'attitude': heads['attitude'][0],
                'expected_move': heads['expected_move'][0],
                'confidence': heads['confidence'][0],
            }
        if (start // batch_size) % 20 == 0:
            print('  encoder %d/%d' % (min(start + batch_size, len(pairs)), len(pairs)),
                  file=sys.stderr, flush=True)
    return verdicts, config


def spotcheck(findings, verdicts, rows_by_id, n, seed):
    """Random relevant pairs with their text, for a human (or Claude) to
    read before the number is believed. The encoder has only ever judged
    posts a rule found a candidate in; this is the check that it still
    makes sense on posts a model found one in."""
    tier_span = {}
    for finding in findings:
        if finding.get('symbol'):
            tier_span.setdefault((finding['external_id'], finding['symbol']),
                                 (finding['tier'], finding['span']))
    relevant = [pair for pair, verdict in verdicts.items() if is_relevant(verdict)]
    picked = random.Random(seed).sample(relevant, min(n, len(relevant)))
    lines = ['# Spot-check: %d of %d encoder-relevant pairs\n' % (len(picked), len(relevant))]
    for post, symbol in picked:
        verdict = verdicts[(post, symbol)]
        tier, span = tier_span[(post, symbol)]
        text = rows_by_id[post]['author_text'].replace('\n', ' ')
        lines.append('### %s  via %s "%s"  relevant %.2f  %s / %s\n'
                     % (symbol, tier, span, verdict['relevance_p'],
                        verdict['attitude'], verdict['expected_move']))
        lines.append('`%s`  \n%s\n' % (post, text[:600] + ('...' if len(text) > 600 else '')))
    return '\n'.join(lines)


def render(f, timings, device, config):
    tiers = f['spans_by_tier']
    resolved = {t: n for t, n in tiers.items() if t != 'unresolved'}
    print()
    print('posts sampled                    %6d' % f['posts_sampled'])
    print('  with >=1 span                  %6d  (%.1f%%)'
          % (f['posts_with_span'], 100.0 * f['posts_with_span'] / max(1, f['posts_sampled'])))
    print('spans                            %6d   resolved %s / unresolved %d'
          % (f['spans'], ' '.join('%s=%d' % kv for kv in sorted(resolved.items())),
             tiers.get('unresolved', 0)))
    print('(post, symbol) pairs             %6d' % f['pairs'])
    print('  encoder relevant               %6d   <- headline' % f['relevant_pairs'])
    print('  encoder kept (incl. uncertain) %6d' % f['kept_pairs'])
    print('posts with a relevant pair       %6d  (%.2f%% of sample)'
          % (f['relevant_posts'], 100.0 * f['relevant_posts'] / max(1, f['posts_sampled'])))
    print('relevant rate per tier           %s'
          % '  '.join('%s %d/%d' % (t, r, n) for t, (r, n)
                      in sorted(f['relevant_rate_by_tier'].items())))
    print('extrapolated relevant posts/week %8.0f   (of %d zero-candidate posts)'
          % (f['extrapolated_relevant_posts_per_week'], ZERO_CANDIDATE_POSTS_PER_WEEK))
    print('top unresolved                   %s'
          % ', '.join('%s x%d' % (t, c) for t, c in f['unresolved_top'][:15]))
    print('timings                          %s'
          % '  '.join('%s %.0fs' % kv for kv in timings.items()))
    print('finder %s on %s; judge %s max_len %d'
          % (GLINER_MODEL, device, config['base'], config['max_len']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--sample', required=True)
    parser.add_argument('--lookup', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--artifact-dir', default=None,
                        help='defaults to the toy loader\'s artifact')
    parser.add_argument('--gliner-batch', type=int, default=32)
    parser.add_argument('--encoder-batch', type=int, default=16)
    parser.add_argument('--threshold', type=float, default=THRESHOLD)
    parser.add_argument('--seed', type=int, default=20260908)
    args = parser.parse_args(argv)
    # The unresolved list is whatever GLiNER found, and on 2026-09-08 that
    # included a peace sign; a cp1252 console must not lose the run on it.
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    with open(args.sample, encoding='utf-8') as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    with open(args.lookup, encoding='utf-8') as handle:
        dumped = json.load(handle)
    index = span_lookup.build_index(dumped['symbols'], dumped['aliases'])
    rows_by_id = {row['external_id']: row for row in rows}
    print('%d posts, %d symbols, %d name tokens, %d aliases'
          % (len(rows), len(index.symbols), len(index.by_token), len(index.aliases)),
          file=sys.stderr, flush=True)

    timings = {}
    started = time.perf_counter()
    findings, device = find_spans(rows, args.gliner_batch, args.threshold)
    timings['gliner'] = time.perf_counter() - started

    started = time.perf_counter()
    for finding in findings:
        finding['symbol'], finding['tier'] = span_lookup.resolve(finding['span'], index)
    timings['lookup'] = time.perf_counter() - started

    pairs = pairs_from(findings)
    started = time.perf_counter()
    import ask_encoder
    artifact_dir = args.artifact_dir or ask_encoder.DEFAULT_ARTIFACT_DIR
    verdicts, config = judge_pairs(pairs, {k: r['author_text'] for k, r in rows_by_id.items()},
                                   artifact_dir, args.encoder_batch)
    timings['encoder'] = time.perf_counter() - started

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'findings.jsonl'), 'w', encoding='utf-8') as handle:
        for finding in findings:
            handle.write(json.dumps(finding, ensure_ascii=False) + '\n')
    with open(os.path.join(args.out, 'verdicts.jsonl'), 'w', encoding='utf-8') as handle:
        for (post, symbol), verdict in verdicts.items():
            handle.write(json.dumps(dict(external_id=post, symbol=symbol, **verdict),
                                    ensure_ascii=False) + '\n')
    result = funnel(findings, verdicts, len(rows))
    result['timings'] = {k: round(v, 1) for k, v in timings.items()}
    result['finder'] = {'model': GLINER_MODEL, 'labels': LABELS,
                        'threshold': args.threshold, 'device': device}
    result['judge'] = {'artifact_dir': os.path.abspath(artifact_dir),
                       'base': config['base'], 'max_len': config['max_len'],
                       'source_model': config.get('manifest', {}).get('source_model')}
    with open(os.path.join(args.out, 'summary.json'), 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=1)
    with open(os.path.join(args.out, 'spotcheck.md'), 'w', encoding='utf-8') as handle:
        handle.write(spotcheck(findings, verdicts, rows_by_id, SPOTCHECK_N, args.seed))
    render(result, timings, device, config)


if __name__ == '__main__':
    main()
