"""Labelling harness for the local-judge roadmap (steps 2-3).

render  : pick rows from the export, write one prompt file per batch of 20 using
          the EXACT production prompt bytes (llm_sentiment._prompt_v2), plus an
          items file with the mention ids in order.
collect : read the verdict files subagents wrote, validate exactly like prod
          (enum check, one verdict per item, never defaulted), append to the
          labels JSONL, mark batches done or failed in status.json.
status  : print progress.

Run from personal_apps/:  python scratchpad/label_export/label_harness.py render --n 200 --run pilot-200
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from features.radar import llm_sentiment as L  # noqa: E402
from features.radar import sentiment_input as S  # noqa: E402

EXPORT = r'C:\Users\michi\Desktop\radar_labels\export-2026-09-05.jsonl'
ROOT = r'C:\Users\michi\Desktop\radar_labels'
MAX_CHARS = 2000            # the student's window; longer text is cut, flagged
BATCH = L.BATCH_SIZE        # 20 in prod; the main run uses 40 (--batch)
MODEL_TAG = 'claude-sonnet-5@claude-code-subagent'

# Pilot stratification: rows per export stratum for a run of N (scaled).
PILOT_MIX = {
    'haiku_mixed': 8, 'haiku_uncertain': 15, 'haiku_irrelevant': 12,
    'haiku_broadcast': 15, 'haiku_rest': 10, 'fourchan': 5, 'thin_tickers': 20,
    'reddit:a<200': 40, 'reddit:b200-500': 20, 'reddit:c500-1k': 10,
    'reddit:d1k-2k': 6, 'reddit:e>2k': 4, 'bluesky:a<200': 22, 'bluesky:b200-500': 13,
}


def load_export(path=None):
    # --export points render at a candidate file in the export's shape (the
    # recall wave, scripts/select_recall_candidates.py); default is prod's.
    return [json.loads(l) for l in open(path or EXPORT, encoding='utf-8') if l.strip()]


def prepared_of(row):
    text = row['author_text']
    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS]
    prep = S.PreparedInput(author_text=text, target_ticker=row['ticker'],
                           source=row['source'], channel=row['channel'] or '',
                           author=row['author'], is_comment=bool(row['is_comment']))
    return prep, truncated


# The 25k plan: rare strata in full, the rest proportional to the export.
MAIN_MIX = {
    'haiku_mixed': 439, 'haiku_uncertain': 1758, 'haiku_irrelevant': 1443,
    'haiku_broadcast': 2220, 'haiku_rest': 1893, 'fourchan': 93, 'thin_tickers': 5692,
    'reddit:a<200': 4246, 'reddit:b200-500': 2521, 'reddit:c500-1k': 1094,
    'reddit:d1k-2k': 716, 'reddit:e>2k': 476, 'bluesky:a<200': 1391, 'bluesky:b200-500': 1018,
}


def pick(rows, n, seed, exclude_ids, mix):
    """Deterministic plan: per-stratum quotas, seeded shuffle, then the first
    n rows not yet labelled. Re-running with the same seed continues the same
    ordered plan, so chunks are stratified on average and never overlap."""
    rng = random.Random(seed)
    by_stratum = collections.defaultdict(list)
    for r in sorted(rows, key=lambda r: r['mention_id']):
        by_stratum[r['stratum']].append(r)
    if mix == 'pilot':
        scale = n / float(sum(PILOT_MIX.values()))
        quotas = {k: max(1, int(round(v * scale))) for k, v in PILOT_MIX.items()}
    else:
        quotas = MAIN_MIX
    plan = []
    for stratum, quota in quotas.items():
        pool = by_stratum.get(stratum, [])
        rng.shuffle(pool)
        plan.extend(pool[:quota])
    rng.shuffle(plan)
    fresh = [r for r in plan if r['mention_id'] not in exclude_ids]
    return fresh[:n], len(plan), len(fresh)


def cmd_render(a):
    run = os.path.join(ROOT, a.run)
    os.makedirs(run, exist_ok=True)
    done_ids = set()
    labels_path = os.path.join(ROOT, a.labels or 'labels-sonnet5.jsonl')
    if os.path.exists(labels_path):
        done_ids = {json.loads(l)['mention_id'] for l in open(labels_path, encoding='utf-8') if l.strip()}
    if a.export:
        # A pre-selected file: render it in file order, skipping nothing but
        # ids already in the labels file this run collects into.
        rows = [r for r in load_export(a.export) if r['mention_id'] not in done_ids][:a.n]
        plan_size, remaining = len(rows), len(rows)
    elif a.ids_file:
        order = json.load(open(a.ids_file, encoding='utf-8'))
        by_id = {r['mention_id']: r for r in load_export()}
        rows = [by_id[i] for i in order if i in by_id and i not in done_ids][:a.n]
        plan_size, remaining = len(order), len(rows)
    else:
        rows, plan_size, remaining = pick(load_export(), a.n, a.seed, done_ids, a.mix)
    batch = a.batch
    status = {'run': a.run, 'rendered_at': dt.datetime.utcnow().isoformat(), 'batches': {}}
    for b, start in enumerate(range(0, len(rows), batch), start=1):
        batch_rows = rows[start:start + batch]
        items, meta = [], []
        for r in batch_rows:
            prep, truncated = prepared_of(r)
            it = L.JudgeItem()
            it.key = r['mention_id']
            it.prepared = prep
            items.append(it)
            meta.append({'mention_id': r['mention_id'], 'ticker': r['ticker'],
                         'stratum': r['stratum'], 'truncated': truncated,
                         'haiku': {f: r['sentiment_' + f] for f in
                                   ('relevance', 'content_origin', 'attitude',
                                    'expected_move', 'confidence')}
                         if r['sentiment_judged_at'] else None})
        prompt = L._prompt_v2(items)
        name = 'batch-%04d' % b
        with open(os.path.join(run, name + '.prompt.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(prompt)
        with open(os.path.join(run, name + '.items.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=0)
        status['batches'][name] = {'n': len(meta), 'state': 'rendered',
                                   'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]}
    with open(os.path.join(run, 'status.json'), 'w', encoding='utf-8') as f:
        json.dump(status, f, indent=1)
    strata = collections.Counter(r['stratum'] for r in rows)
    print('rendered %d rows in %d batches of %d to %s' % (len(rows), len(status['batches']), batch, run))
    print('plan %s: %d offered, %d selected' % (a.export or a.ids_file or a.mix, plan_size, remaining))
    print('strata:', dict(strata))
    print('truncated rows:', sum(prepared_of(r)[1] for r in rows))
    print('haiku-labelled rows:', sum(1 for r in rows if r['sentiment_judged_at']))


def _entries(payload):
    """The verdict entries, in either envelope, each carrying its own `n`.

    The rendered prompt never names a JSON envelope: production supplies
    one through the API's response schema, which a subagent labeller does
    not have, so it chooses. Both choices observed carry the same content
    -- {'verdicts': [{'n': 1, ...}]} and {'1': {...}} -- and the field
    validation below is applied to either, unchanged. Anything else is
    unparseable, exactly as before.
    """
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get('verdicts'), list):
        return payload['verdicts']
    entries = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            return None
        try:
            number = int(key)
        except (TypeError, ValueError):
            return None
        entries.append(dict(value, n=number))
    return entries or None


def validate(text, n_items):
    """Exactly prod's acceptance rule (llm_sentiment._judge_batch_v2)."""
    try:
        payload = json.loads(text)
    except Exception as exc:
        return None, 'unparseable: %s' % exc
    verdicts = _entries(payload)
    if verdicts is None:
        return None, 'no verdicts: not a verdicts list and not keyed by item number'
    got = {}
    for e in verdicts:
        if not isinstance(e, dict):
            continue
        n = e.get('n')
        if not isinstance(n, int) or not 1 <= n <= n_items:
            continue
        vals = {}
        for f, allowed in L._FIELD_ENUMS.items():
            v = e.get(f)
            if v not in allowed:
                vals = None
                break
            vals[f] = v
        if vals is None:
            continue
        got[n] = vals
    return got, None


def cmd_collect(a):
    run = os.path.join(ROOT, a.run)
    status_path = os.path.join(run, 'status.json')
    status = json.load(open(status_path, encoding='utf-8'))
    # --labels lets an evaluation run (the audit rows) land in its own file,
    # so the trainer never sees those rows as training data.
    labels_path = os.path.join(ROOT, a.labels or 'labels-sonnet5.jsonl')
    booked = 0
    with open(labels_path, 'a', encoding='utf-8') as out:
        for name, st in sorted(status['batches'].items()):
            if st['state'] == 'done':
                continue
            vpath = os.path.join(run, name + '.verdict.json')
            if not os.path.exists(vpath):
                st['state'] = 'rendered'
                continue
            meta = json.load(open(os.path.join(run, name + '.items.json'), encoding='utf-8'))
            got, err = validate(open(vpath, encoding='utf-8').read(), len(meta))
            if err:
                st.update(state='failed', error=err)
                continue
            missing = [i + 1 for i in range(len(meta)) if i + 1 not in got]
            now = dt.datetime.utcnow().isoformat()
            for i, m in enumerate(meta, start=1):
                if i not in got:
                    continue
                rec = {'mention_id': m['mention_id'], 'ticker': m['ticker'],
                       'stratum': m['stratum'], 'truncated': m['truncated'],
                       'model': MODEL_TAG, 'prompt_version': L.PROMPT_VERSION,
                       'run': a.run, 'batch': name, 'labelled_at': now,
                       'haiku': m['haiku']}
                rec.update(got[i])
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                booked += 1
            st.update(state='done' if not missing else 'partial',
                      judged=len(got), missing=missing)
    json.dump(status, open(status_path, 'w', encoding='utf-8'), indent=1)
    states = collections.Counter(s['state'] for s in status['batches'].values())
    print('booked %d labels; batch states: %s' % (booked, dict(states)))
    for name, st in sorted(status['batches'].items()):
        if st['state'] not in ('done',):
            print(' ', name, st)


def cmd_status(a):
    run = os.path.join(ROOT, a.run)
    status = json.load(open(os.path.join(run, 'status.json'), encoding='utf-8'))
    states = collections.Counter(s['state'] for s in status['batches'].values())
    print(dict(states))


def cmd_compare(a):
    """Sonnet vs Haiku on the rows that carry both."""
    labels = [json.loads(l) for l in open(os.path.join(ROOT, 'labels-sonnet5.jsonl'), encoding='utf-8') if l.strip()]
    both = [r for r in labels if r.get('haiku')]
    if not both:
        print('no rows with both labels yet')
        return
    fields = ('relevance', 'content_origin', 'attitude', 'expected_move', 'confidence')
    print('rows with Haiku label:', len(both))
    for f in fields:
        agree = sum(r[f] == r['haiku'][f] for r in both)
        print('  %-15s agree %.1f%%' % (f, 100.0 * agree / len(both)))
    flips = sum({r['attitude'], r['haiku']['attitude']} == {'positive', 'negative'} for r in both)
    print('  polarity flips: %d' % flips)
    print('  Sonnet attitude mix:', dict(collections.Counter(r['attitude'] for r in labels)))
    print('  Sonnet relevance mix:', dict(collections.Counter(r['relevance'] for r in labels)))
    print('  Sonnet origin mix:', dict(collections.Counter(r['content_origin'] for r in labels)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('render'); r.add_argument('--n', type=int, required=True)
    r.add_argument('--run', required=True); r.add_argument('--seed', type=int, default=1)
    r.add_argument('--mix', choices=['pilot', 'main'], default='main')
    r.add_argument('--batch', type=int, default=40)
    r.add_argument('--ids-file', default=None,
                   help='JSON list of mention ids, in priority order')
    r.add_argument('--export', default=None,
                   help='render this export-shaped file in order instead of picking from prod')
    r.add_argument('--labels', default=None,
                   help='labels JSONL whose ids are skipped (default labels-sonnet5.jsonl)')
    c = sub.add_parser('collect'); c.add_argument('--run', required=True)
    c.add_argument('--labels', default=None, help='output JSONL name (default labels-sonnet5.jsonl)')
    s = sub.add_parser('status'); s.add_argument('--run', required=True)
    sub.add_parser('compare')
    a = ap.parse_args()
    {'render': cmd_render, 'collect': cmd_collect, 'status': cmd_status, 'compare': cmd_compare}[a.cmd](a)
