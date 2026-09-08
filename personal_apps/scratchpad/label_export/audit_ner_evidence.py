# personal_apps/scratchpad/label_export/audit_ner_evidence.py
"""Independent re-check of the NER evidence, 2026-09-08, after Codex's audit.

Four problems, each answered with numbers from the artifacts rather than
from the documents that described them:

  1. Leakage into the held-out set: gold surfaces counted over ALL examples
     when choosing which names to fill, and identical texts on both sides.
  2. Permissive scoring: any-overlap credit, and predictions escaping FP by
     touching a silver/ignore region. Re-scored strict, and end-to-end
     (does the predicted surface still resolve to the gold ticker).
  3. The recall-ceiling inference: pipeline yield split into detection,
     resolution and relevance, with the unresolved spans and the rejected
     pairs dumped for reading.
  4. Disagreement between the three finders on the probe.

Runs in the encoder venv (needs the taggers for 1 and 2). Writes
`radar_labels/ner/audit-2026-09-08/` with a report and the reading dumps.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ner_tagging                                         # noqa: E402
import span_lookup                                         # noqa: E402
import train_ner                                           # noqa: E402
from gliner_recall_check import kind_of                    # noqa: E402

L = 'C:/Users/michi/Desktop/radar_labels'
NER = L + '/ner'
OUT = NER + '/audit-2026-09-08'
V1 = NER + '/model-ner-deberta-v3-small-20260908-133610'
V2 = NER + '/model-ner-deberta-v3-small-20260908-135556'
PROBES = {'gliner': NER + '/probe-3000', 'v1': NER + '/probe-3000-trained',
          'v2': NER + '/probe-3000-trained-v2'}


def jl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def overlap(a, b):
    return a[0] < b[1] and a[1] > b[0]


def iou(a, b):
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def score(examples, preds, mode, undecided_rule):
    """mode: 'any' | 'iou50' | 'exact'. undecided_rule: 'touch' (current:
    any overlap with a silver/ignore region excuses the prediction) or
    'covered' (the region must cover >= 50% of the prediction)."""
    tp = fp = fn = 0
    for example, spans in zip(examples, preds):
        gold = [(s, e) for s, e, _ in example['spans']]
        und = [tuple(r) for r in example.get('silver', ())] + [tuple(r) for r in example.get('ignore', ())]
        for g in gold:
            hit = any((overlap(g, p) if mode == 'any' else iou(g, p) >= 0.5 if mode == 'iou50' else g == p)
                      for p in spans)
            tp += hit
            fn += not hit
        for p in spans:
            if any((overlap(g, p) if mode == 'any' else iou(g, p) >= 0.5 if mode == 'iou50' else g == p)
                   for g in gold):
                continue
            if undecided_rule == 'touch' and any(overlap(u, p) for u in und):
                continue
            if undecided_rule == 'covered' and any(
                    max(0, min(u[1], p[1]) - max(u[0], p[0])) >= 0.5 * (p[1] - p[0]) for u in und):
                continue
            fp += 1
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return pr, rc, f1, tp, fp, fn


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    os.makedirs(OUT, exist_ok=True)
    report = []

    def say(line=''):
        print(line)
        report.append(line)

    v1_examples = jl(L + '/spans-2026-09-07.jsonl')
    v2_examples = jl(L + '/spans-v2-2026-09-08.jsonl')
    test_ids = set()
    for name in train_ner.TEST_SETS:
        with open(os.path.join(L, name), encoding='utf-8') as handle:
            test_ids.update(json.load(handle))
    train2, held2 = ner_tagging.split_holdout(v2_examples, test_ids)
    train1, held1 = ner_tagging.split_holdout(v1_examples, test_ids)
    assert [e['key'] for e in held1] == [e['key'] for e in held2]

    # ---- 1. leakage ---------------------------------------------------------
    say('## 1. Leakage')
    with open(NER + '/lookup.json', encoding='utf-8') as handle:
        dumped = json.load(handle)
    with open(L + '/promotion-instruments.json', encoding='utf-8') as handle:
        instruments = json.load(handle)
    with open(L + '/ordinary-words.json', encoding='utf-8') as handle:
        ordinary = set(json.load(handle)['words'])
    import build_spans_v2 as b2
    index = span_lookup.build_index(dumped['symbols'], dumped['aliases'])
    candidates = ((set(index.by_token) & set(instruments['name_shapes'])) - ordinary - b2.NAME_STOPLIST)
    vouched_all = collections.Counter(e['text'][s:t].lower() for e in v1_examples for s, t, _ in e['spans'])
    vouched_train = collections.Counter(e['text'][s:t].lower() for e in train1 for s, t, _ in e['spans'])
    names_all = {c for c in candidates if vouched_all[c] >= b2.VOUCHED_MIN} | set(index.aliases)
    names_train = {c for c in candidates if vouched_train[c] >= b2.VOUCHED_MIN} | set(index.aliases)
    leaked = sorted(names_all - names_train)
    say('names vouched with ALL gold: %d; with TRAIN gold only: %d; leaked (only vouched via held-out gold): %s'
        % (len(names_all), len(names_train), leaked))
    silver_train_leaked = collections.Counter()
    for e in train2:
        for s, t in e['silver']:
            w = e['text'][s:t].lower()
            if w in leaked:
                silver_train_leaked[w] += 1
    say('silver spans in TRAINING from leaked names: %d  %s'
        % (sum(silver_train_leaked.values()), dict(silver_train_leaked)))
    held_gold_leaked = collections.Counter(e['text'][s:t].lower() for e in held1 for s, t, _ in e['spans']
                                           if e['text'][s:t].lower() in leaked)
    say('HELD-OUT gold spans with those surfaces (the most recall the leak could buy): %d of %d  %s'
        % (sum(held_gold_leaked.values()), sum(len(e['spans']) for e in held1), dict(held_gold_leaked)))
    train_texts = {e['text'] for e in train1}
    dup_held = [e for e in held1 if e['text'] in train_texts]
    say('identical texts train<->held-out: %d held-out rows, %d gold spans'
        % (len(dup_held), sum(len(e['spans']) for e in dup_held)))
    dup_keys = {e['key'] for e in dup_held}

    # ---- 2. scoring -----------------------------------------------------------
    say('\n## 2. Scoring')
    texts = [e['text'] for e in held2]
    preds = {}
    for tag, mdir in (('v1', V1), ('v2', V2)):
        tok, model, cfg, device = train_ner.load_model(mdir)
        preds[tag] = train_ner.predict_spans(model, tok, texts, device, cfg['max_len'], 64)
    say('held-out (1,856 rows, 1,629 gold spans), v1 vs v2 under each rule:')
    say('  %-34s %8s %8s %8s %8s' % ('rule', 'v1 P', 'v1 R', 'v2 P', 'v2 R'))
    for mode in ('any', 'iou50', 'exact'):
        for und in ('touch', 'covered'):
            r1 = score(held2, preds['v1'], mode, und)
            r2 = score(held2, preds['v2'], mode, und)
            say('  %-34s %8.3f %8.3f %8.3f %8.3f   (v1 tp/fp/fn %d/%d/%d; v2 %d/%d/%d)'
                % ('%s overlap, undecided=%s' % (mode, und), r1[0], r1[1], r2[0], r2[1],
                   r1[3], r1[4], r1[5], r2[3], r2[4], r2[5]))
    held_nodup = [e for e in held2 if e['key'] not in dup_keys]
    idx = [i for i, e in enumerate(held2) if e['key'] not in dup_keys]
    for tag in ('v1', 'v2'):
        r = score(held_nodup, [preds[tag][i] for i in idx], 'any', 'touch')
        say('  %s without the %d duplicated rows (any/touch): P %.3f R %.3f' % (tag, len(dup_held), r[0], r[1]))
    # over-long predictions and escapes
    for tag in ('v1', 'v2'):
        multi = sum(1 for e, spans in zip(held2, preds[tag]) for p in spans
                    if sum(overlap((s, t), p) for s, t, _ in e['spans']) >= 2)
        long_ = sum(1 for e, spans in zip(held2, preds[tag]) for p in spans
                    for s, t, _ in e['spans'] if overlap((s, t), p) and (p[1] - p[0]) > (t - s) + 3)
        escapes = 0
        for e, spans in zip(held2, preds[tag]):
            gold = [(s, t) for s, t, _ in e['spans']]
            und = [tuple(r) for r in e.get('silver', ())] + [tuple(r) for r in e.get('ignore', ())]
            for p in spans:
                if any(overlap(g, p) for g in gold):
                    continue
                touching = [u for u in und if overlap(u, p)]
                if touching and not any(max(0, min(u[1], p[1]) - max(u[0], p[0])) >= 0.5 * (p[1] - p[0]) for u in touching):
                    escapes += 1
        say('  %s: predictions covering >=2 gold spans %d; overlapping a gold span but >3 chars longer %d; '
            'FP escapes by merely touching an undecided region %d' % (tag, multi, long_, escapes))
    # end-to-end: predicted surface resolves to the gold ticker
    for tag in ('v1', 'v2'):
        ok = wrong = none = 0
        for e, spans in zip(held2, preds[tag]):
            for s, t, ticker in e['spans']:
                hits = [p for p in spans if overlap((s, t), p)]
                if not hits:
                    continue
                symbol, _tier = span_lookup.resolve(e['text'][hits[0][0]:hits[0][1]].strip(), index)
                if symbol is None:
                    none += 1
                elif symbol == ticker or (symbol in ('GOOG', 'GOOGL') and ticker in ('GOOG', 'GOOGL')):
                    ok += 1
                else:
                    wrong += 1
        say('  %s: of gold spans it overlaps, predicted surface resolves to the gold ticker %d, to a different symbol %d, to nothing %d'
            % (tag, ok, wrong, none))

    # ---- 4. disagreement on the probe ----------------------------------------
    say('\n## 4. Disagreement on the probe')
    rel = {}
    pairs_rel = {}
    for tag, d in PROBES.items():
        vs = jl(d + '/verdicts.jsonl')
        pairs_rel[tag] = {(v['external_id'], v['symbol']) for v in vs
                          if v['relevance'] == 'relevant' and v['content_origin'] != 'broadcast_or_automated'}
        rel[tag] = {p for p, _ in pairs_rel[tag]}
    for a, b in (('gliner', 'v1'), ('v1', 'v2'), ('gliner', 'v2')):
        say('  posts: %s∩%s %d, %s-only %d, %s-only %d | pairs: shared %d, %s-only %d, %s-only %d'
            % (a, b, len(rel[a] & rel[b]), a, len(rel[a] - rel[b]), b, len(rel[b] - rel[a]),
               len(pairs_rel[a] & pairs_rel[b]), a, len(pairs_rel[a] - pairs_rel[b]), b, len(pairs_rel[b] - pairs_rel[a])))
    union_posts = rel['gliner'] | rel['v1'] | rel['v2']
    all3 = rel['gliner'] & rel['v1'] & rel['v2']
    say('  union of relevant posts %d (%.2f%%), in all three %d' % (len(union_posts), 100.0 * len(union_posts) / 3000, len(all3)))
    sample = {r['external_id']: r for r in jl(NER + '/sample-3000.jsonl')}
    findings = {tag: jl(d + '/findings.jsonl') for tag, d in PROBES.items()}
    verdicts = {tag: {(v['external_id'], v['symbol']): v for v in jl(d + '/verdicts.jsonl')} for tag, d in PROBES.items()}
    with open(OUT + '/disagreements.md', 'w', encoding='utf-8') as handle:
        for post in sorted(union_posts):
            who = ' '.join('%s=%s' % (t, ','.join(sorted(sym for p, sym in pairs_rel[t] if p == post)) or '-') for t in PROBES)
            if post in all3:
                continue
            handle.write('### %s   %s\n' % (post, who))
            for tag in PROBES:
                spans = ['%s->%s(%s)' % (f['span'], f['symbol'], f['tier']) for f in findings[tag] if f['external_id'] == post]
                vs = ['%s:%s/%.2f' % (sym, v['relevance'], v['relevance_p']) for (p, sym), v in verdicts[tag].items() if p == post]
                handle.write('- %s found %s; judged %s\n' % (tag, spans or '-', vs or '-'))
            handle.write('\n%s\n\n' % sample[post]['author_text'].replace('\n', ' ')[:500])
    say('  disagreement dump: %s (%d posts not in all three)' % (OUT + '/disagreements.md', len(union_posts - all3)))

    # ---- 3. the pipeline stages, for reading ---------------------------------
    say('\n## 3. Pipeline stages (GLiNER probe)')
    g = findings['gliner']
    unresolved = collections.Counter(f['span'] for f in g if not f['symbol'])
    with open(OUT + '/unresolved-gliner.txt', 'w', encoding='utf-8') as handle:
        for text, n in unresolved.most_common():
            handle.write('%3d  %s\n' % (n, text))
    rejected = [(p, sym, v) for (p, sym), v in verdicts['gliner'].items()
                if not (v['relevance'] == 'relevant' and v['content_origin'] != 'broadcast_or_automated')]
    with open(OUT + '/rejected-pairs-gliner.md', 'w', encoding='utf-8') as handle:
        for p, sym, v in rejected:
            spans = [f['span'] for f in g if f['external_id'] == p and f['symbol'] == sym]
            handle.write('### %s %s  via %s  -> %s %.2f / %s\n%s\n\n'
                         % (p, sym, spans, v['relevance'], v['relevance_p'], v['content_origin'],
                            sample[p]['author_text'].replace('\n', ' ')[:400]))
    say('  flagged posts 419; spans 527; unresolved 440 (%d distinct) -> %s' % (len(unresolved), OUT + '/unresolved-gliner.txt'))
    say('  pairs 78; encoder rejected %d -> %s' % (len(rejected), OUT + '/rejected-pairs-gliner.md'))

    with open(OUT + '/report.md', 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(report) + '\n')
    print('\n-> %s' % OUT)


if __name__ == '__main__':
    main()
