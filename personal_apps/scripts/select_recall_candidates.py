# personal_apps/scripts/select_recall_candidates.py
"""Pick the recall wave: rejected candidates for Sonnet to label.

Reads rejected-candidates.jsonl from scripts/measure_extractor_population.py
and writes N rows in the label harness's export shape, so `label_harness.py
render --export <file>` renders them with the production prompt, unchanged.

    cd personal_apps && PYTHONPATH=. python -m scripts.select_recall_candidates \\
        --candidates C:/Users/michi/Desktop/radar_labels/raw/population/rejected-candidates.jsonl \\
        --out C:/Users/michi/Desktop/radar_labels/candidates-2026-09-06.jsonl --n 3000

A TOP-UP WAVE draws only what an earlier wave could not see: pass
--exclude with the earlier wave's candidate file and every (post, symbol,
cause) it already holds is skipped, so a second wave spends entirely on
what the loose pass learned to find.

STRATIFIED BY CAUSE, CAPPED PER SYMBOL (or per evidence token, --cap-by
evidence: `trump` produced 3,170 candidates across Trump Media and its
warrant, so capping the symbol still lets one word take a fifth of a
wave). Half of all name-only candidates
are fourteen symbols (GoPro alone is a tenth), and AI is a third of the
stopword class; an uncapped sample would measure those and nothing else.
Each symbol may take at most `cap_share` of the wave. A cause whose pool
runs short hands its slack to the others, so the wave is always full.

INVISIBLE FIRST. A candidate in a post the pipeline never stored is the
recall question; one beside an accepted ticker is the same question with a
bias, and is taken only when the invisible pool runs dry.

IDS ARE NEGATIVE. -1, -2, ... can never collide with a production
mention_id, so the wave's labels can sit in the same JSONL shape as the
15,200 without any row being mistaken for a stored mention; `stratum`
carries `cand:<cause>` and `candidate` carries the provenance.

No model is called here. The wave itself runs only when its size has been
named and the go given.
"""
import argparse
import collections
import json
import random

DEFAULT_QUOTAS = {
    'metonym': 0.05,
    'name_only': 0.40,
    'lowercase_symbol': 0.30,
    'stopword': 0.20,
    'cashtag_not_in_universe': 0.05,
    'bare_other': 0.03,
    'single_letter_cashtag': 0.02,
}
DEFAULT_CAP_SHARE = 0.03        # 90 rows per symbol in a wave of 3,000


def without(candidates, already):
    """Candidates an earlier wave did not hold, by (post, symbol, cause)."""
    return [c for c in candidates
            if (c['external_id'], c['symbol'], c['cause']) not in already]


def keys_of(candidates):
    return {(c['external_id'], c['symbol'], c['cause']) for c in candidates}


def pick(candidates, n, quotas, cap_share, seed, cap_key='symbol'):
    """Deterministic: per-cause quotas, invisible posts first, seeded
    order, a per-symbol cap over the whole wave, slack redistributed."""
    rng = random.Random(seed)
    cap = max(1, int(cap_share * n))
    pools = {}
    for cause in quotas:
        rows = [c for c in candidates if c['cause'] == cause]
        rows.sort(key=lambda c: c['external_id'])
        rng.shuffle(rows)
        # Stable: keeps the shuffled order inside each half.
        rows.sort(key=lambda c: bool(c['stored_today']))
        pools[cause] = collections.deque(rows)

    per_key = collections.Counter()
    picked = []

    def take(cause, want):
        taken = 0
        pool = pools[cause]
        skipped = []
        while pool and taken < want:
            row = pool.popleft()
            if per_key[row[cap_key]] >= cap:
                skipped.append(row)
                continue
            per_key[row[cap_key]] += 1
            picked.append(row)
            taken += 1
        pool.extend(skipped)
        return taken

    for cause, share in quotas.items():
        take(cause, int(round(share * n)))
    # Slack: round-robin over the causes that still have eligible rows.
    while len(picked) < n:
        progressed = False
        for cause in quotas:
            if len(picked) >= n:
                break
            if take(cause, 1):
                progressed = True
        if not progressed:
            break
    rng.shuffle(picked)
    return picked[:n]


def to_export_row(candidate, mention_id):
    source = candidate['source']
    return {
        'mention_id': mention_id,
        'ticker': candidate['symbol'],
        'confidence': None,
        'lexicon_sentiment': None,
        'sentiment_relevance': None, 'sentiment_content_origin': None,
        'sentiment_attitude': None, 'sentiment_expected_move': None,
        'sentiment_confidence': None, 'sentiment_model': None,
        'sentiment_prompt_version': None, 'sentiment_judged_at': None,
        'post_id': None,
        'source': source,
        'external_id': candidate['external_id'],
        'channel': source.split(':', 1)[1] if ':' in source else '',
        'author': None,
        'created_utc': candidate['created_utc'],
        'title': candidate.get('title'),
        'body': None,
        'score': None, 'num_comments': None, 'simhash': None,
        'author_text': candidate['author_text'],
        'is_comment': candidate.get('kind') == 'comments',
        'preparation_version': 1,
        'stratum': 'cand:%s' % candidate['cause'],
        'text_len': len(candidate['author_text']),
        'candidate': {'cause': candidate['cause'], 'evidence': candidate['evidence'],
                      'stored_today': bool(candidate['stored_today']),
                      'external_id': candidate['external_id']},
    }


def write_export(picked, path):
    with open(str(path), 'w', encoding='utf-8') as handle:
        for index, candidate in enumerate(picked, start=1):
            handle.write(json.dumps(to_export_row(candidate, -index), ensure_ascii=False) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--n', type=int, required=True)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--cap-share', type=float, default=DEFAULT_CAP_SHARE)
    parser.add_argument('--cap-by', choices=['symbol', 'evidence'], default='symbol')
    parser.add_argument('--exclude', default=None,
                        help="an earlier wave's candidate file; its rows are skipped")
    args = parser.parse_args(argv)

    with open(args.candidates, encoding='utf-8') as handle:
        candidates = [json.loads(line) for line in handle if line.strip()]
    if args.exclude:
        with open(args.exclude, encoding='utf-8') as handle:
            already = {(r['candidate']['external_id'], r['ticker'],
                        r['candidate']['cause'])
                       for r in (json.loads(line) for line in handle if line.strip())}
        before = len(candidates)
        candidates = without(candidates, already)
        print('excluded %d candidates an earlier wave already drew'
              % (before - len(candidates)))
    picked = pick(candidates, args.n, DEFAULT_QUOTAS, args.cap_share, args.seed,
                  cap_key=args.cap_by)
    write_export(picked, args.out)

    by_cause = collections.Counter(c['cause'] for c in picked)
    invisible = sum(1 for c in picked if not c['stored_today'])
    print('picked %d of %d candidates -> %s' % (len(picked), len(candidates), args.out))
    print('by cause:', dict(by_cause))
    print('invisible posts: %d (%.0f%%)' % (invisible, 100.0 * invisible / max(len(picked), 1)))
    for cause in by_cause:
        rows = [c for c in picked if c['cause'] == cause]
        top = collections.Counter(c['symbol'] for c in rows)
        tokens = collections.Counter(c['evidence'].lower() for c in rows)
        print('  %-24s distinct symbols %3d, top: %s' % (cause, len(top), top.most_common(6)))
        print('  %-24s distinct tokens  %3d, top: %s' % ('', len(tokens), tokens.most_common(6)))


if __name__ == '__main__':
    main()
