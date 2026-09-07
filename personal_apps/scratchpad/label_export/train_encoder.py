"""Step 4 of the local-judge roadmap: train the distilled encoder.

One shared DeBERTa-v3-small encoder, five classification heads (relevance,
content_origin, attitude, expected_move, confidence). Input is
"<ticker> [SEP] <author_text>", the same canonical text the judge reads.

THREE LOCKED SETS since 2026-09-07. natural and hard are drawn from the
production export, which holds only mentions the extractor ACCEPTED, so
neither says anything about a company named without its symbol, a symbol
typed lowercase, or a person standing for a company. `test-recall.json`
locks a slice of the recall waves for exactly those, and without it every
number about the new classes would be in-sample.

Split discipline (spec §8): the evaluation sets are FROZEN on disk by
mention id (freeze_test_sets.py) and never trained on. Training drops any
row that shares a post with a locked row AND any row whose post simhash is
within Hamming distance 3 of a locked row's -- Codex's review of 2026-09-05
found 10 exact and 26 near-duplicate collisions with post-id exclusion
alone, which is a leak. The locked sets are scored once per run.

Every run is seeded and writes a manifest (seed, sizes, exclusions, input
file hashes, git HEAD) next to its results so a number can be reproduced.

Usage (from personal_apps/, venv python):
    python scratchpad/label_export/train_encoder.py --curve 3000,5000,8600 --save
"""
import argparse
import collections
import hashlib
import json
import os
import random
import subprocess
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer, logging as hf_logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import label_data  # noqa: E402
import tone_training  # noqa: E402
import checkpointing  # noqa: E402

ROOT = r'C:\Users\michi\Desktop\radar_labels'
LABELS = os.path.join(ROOT, 'labels-sonnet5.jsonl')
EXPORT = os.path.join(ROOT, 'export-2026-09-05.jsonl')
# The recall waves: rejected candidates, labelled by the same teacher with
# the same prompt, carrying the classes the production export cannot hold.
RECALL_LABELS = os.path.join(ROOT, 'labels-recall.jsonl')
RECALL_EXPORTS = [os.path.join(ROOT, 'candidates-2026-09-06.jsonl'),
                  os.path.join(ROOT, 'candidates-topup-2026-09-06.jsonl')]
PAIRS = ([(LABELS, EXPORT)]
         + [(RECALL_LABELS, export) for export in RECALL_EXPORTS])
OUT_DIR = os.path.join(ROOT, 'encoder')
TEST_NATURAL = os.path.join(ROOT, 'test-natural.json')
TEST_HARD = os.path.join(ROOT, 'test-hard.json')
TEST_RECALL = os.path.join(ROOT, 'test-recall.json')
hf_logging.set_verbosity_error()
BASE = 'microsoft/deberta-v3-small'
# Tokens the model reads. Labels were made on the first 2,000 chars of a
# post (label_harness.MAX_CHARS); 512 tokens covers that, 256 did not --
# the first runs silently read half of what the teacher judged.
MAX_LEN = 512
HAMMING_LIMIT = 3          # near-duplicate rule, same as train_radar_sentiment.py

# Ship gates on the natural set (roadmap step 4 / spec §10.2), as macro-F1
# where the spec says F1. Printed as PASS/FAIL so accuracy cannot hide them.
GATES = {
    'relevance_macro_f1': 0.90,
    'content_origin_macro_f1': 0.90,
    'removal_precision': 0.95,
    'attitude_accuracy': 0.80,
    'reversal_rate_max': 0.02,
}

HEADS = {
    'relevance': ['relevant', 'irrelevant', 'uncertain'],
    'content_origin': ['human_chatter', 'broadcast_or_automated', 'uncertain'],
    'attitude': ['positive', 'negative', 'mixed', 'none'],
    'expected_move': ['up', 'down', 'flat', 'unknown'],
    'confidence': ['high', 'medium', 'low'],
}
IDX = {h: {v: i for i, v in enumerate(vs)} for h, vs in HEADS.items()}
# mention_id -> the label VALUES, so the mask can ask about relevance
# by name rather than by an index the head order could change.
RAW_Y = {}


def load_rows():
    """Every wave's rows, label values mapped to head indices.

    A wave's labels file is read once per export it is paired with; a row
    whose mention id is missing from that export is skipped there and
    picked up by the pair that does hold it.
    """
    rows = []
    seen = set()
    for labels_path, export_path in PAIRS:
        for row in label_data.load_rows([(labels_path, export_path)]):
            if row['mention_id'] in seen:
                continue
            seen.add(row['mention_id'])
            RAW_Y[row['mention_id']] = dict(row['y'])
            row['y'] = {h: IDX[h][row['y'][h]] for h in HEADS}
            rows.append(row)
    return rows


def _near(hash_a, hash_b):
    return bin(hash_a ^ hash_b).count('1') <= HAMMING_LIMIT


def split(rows):
    """FROZEN evaluation sets (by mention id, on disk) + everything else.

    The two locked sets never change and are never trained on, so numbers
    from different runs are comparable -- the whole point of a locked set.
    Training drops rows sharing a POST with a locked row, and rows whose
    post simhash is within HAMMING_LIMIT of any locked row's: a repost of a
    test post is the test post as far as the model is concerned. Returns
    the exclusion counts too, for the manifest.
    """
    natural_ids = set(json.load(open(TEST_NATURAL, encoding='utf-8')))
    hard_ids = set(json.load(open(TEST_HARD, encoding='utf-8')))
    recall_ids = (set(json.load(open(TEST_RECALL, encoding='utf-8')))
                  if os.path.exists(TEST_RECALL) else set())
    locked = natural_ids | hard_ids | recall_ids
    locked_rows = [r for r in rows if r['mention_id'] in locked]
    locked_posts = {r['post_id'] for r in locked_rows}
    locked_hashes = {r['simhash'] for r in locked_rows if r['simhash'] is not None}
    natural = [r for r in rows if r['mention_id'] in natural_ids]
    hard = [r for r in rows if r['mention_id'] in hard_ids]
    recall = [r for r in rows if r['mention_id'] in recall_ids]

    candidates = [r for r in rows if r['post_id'] not in locked_posts]
    dropped_post = len(rows) - len(locked_rows) - len(candidates)
    # Pairwise over DISTINCT hashes: a few thousand x ~1,300 popcounts.
    near_hashes = set()
    for h in {r['simhash'] for r in candidates if r['simhash'] is not None}:
        if h in locked_hashes or any(_near(h, lh) for lh in locked_hashes):
            near_hashes.add(h)
    train = [r for r in candidates if r['simhash'] not in near_hashes]
    dropped_near = len(candidates) - len(train)
    train.sort(key=lambda r: r['created'])
    exclusions = {'shared_post': dropped_post, 'near_duplicate': dropped_near,
                  'near_duplicate_hashes': len(near_hashes)}
    return train, natural, hard, recall, exclusions


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()[:16]


def _git_head():
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'],
                                       text=True).strip()
    except Exception:
        return 'unknown'


class Rows(Dataset):
    def __init__(self, rows, tok):
        self.rows, self.tok = rows, tok

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        enc = self.tok(r['ticker'], r['text'], truncation=True,
                       max_length=MAX_LEN, padding='max_length',
                       return_tensors='pt')
        item = {k: v.squeeze(0) for k, v in enc.items()}
        for h in HEADS:
            item['y_' + h] = torch.tensor(r['y'][h])
            # 1.0 where this row may teach this head. See tone_training:
            # a non-relevant row's attitude/expected_move is a label the
            # PROMPT forced, not a judgement, and training on it taught the
            # tone heads to answer `none`.
            item['m_' + h] = torch.tensor(
                1.0 if tone_training.is_trainable({'y': RAW_Y[r['mention_id']]}, h)
                else 0.0)
        return item


class MultiHead(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base, dtype=torch.float32)
        h = self.encoder.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.heads = nn.ModuleDict(
            {k: nn.Linear(h, len(v)) for k, v in HEADS.items()})

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        kw = {'input_ids': input_ids, 'attention_mask': attention_mask}
        if token_type_ids is not None:
            kw['token_type_ids'] = token_type_ids
        out = self.encoder(**kw).last_hidden_state[:, 0]
        out = self.drop(out)
        return {k: head(out) for k, head in self.heads.items()}


def evaluate(model, loader, device):
    model.eval()
    preds = {h: [] for h in HEADS}
    gold = {h: [] for h in HEADS}
    with torch.no_grad():
        for batch in loader:
            ys = {h: batch.pop('y_' + h) for h in HEADS}
            # The dataset also carries a per-head trainability mask. It is
            # for the LOSS only; the model has never seen it as an input,
            # and leaving it in the batch made forward() raise after a
            # full six-epoch run had already finished.
            for h in HEADS:
                batch.pop('m_' + h, None)
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch)
            for h in HEADS:
                preds[h] += logits[h].float().argmax(-1).cpu().tolist()
                gold[h] += ys[h].tolist()
    return preds, gold


def report(preds, gold, rows, title):
    print('\n===', title, '(n=%d)' % len(rows))
    out = {}
    for h, classes in HEADS.items():
        p, g = np.array(preds[h]), np.array(gold[h])
        acc = float((p == g).mean())
        f1s = []
        per = {}
        for i, c in enumerate(classes):
            tp = int(((p == i) & (g == i)).sum())
            fp = int(((p == i) & (g != i)).sum())
            fn = int(((p != i) & (g == i)).sum())
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
            f1s.append(f1)
            per[c] = {'precision': round(prec, 3), 'recall': round(rec, 3),
                      'f1': round(f1, 3), 'support': int((g == i).sum())}
        out[h] = {'accuracy': round(acc, 3), 'macro_f1': round(float(np.mean(f1s)), 3),
                  'per_class': per}
        print(' %-15s acc %.3f  macroF1 %.3f  %s' % (
            h, acc, np.mean(f1s),
            ' '.join('%s:%.2f/%d' % (c[:4], per[c]['f1'], per[c]['support'])
                     for c in classes)))
    # the gate that matters: precision when a mention would be REMOVED
    p_rel, g_rel = np.array(preds['relevance']), np.array(gold['relevance'])
    p_org, g_org = np.array(preds['content_origin']), np.array(gold['content_origin'])
    remove_p = (p_rel == IDX['relevance']['irrelevant']) | (
        p_org == IDX['content_origin']['broadcast_or_automated'])
    remove_g = (g_rel == IDX['relevance']['irrelevant']) | (
        g_org == IDX['content_origin']['broadcast_or_automated'])
    tp = int((remove_p & remove_g).sum())
    fp = int((remove_p & ~remove_g).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    out['removal_precision'] = round(prec, 3)
    out['removal_predicted'] = int(remove_p.sum())
    print(' removal (irrelevant|broadcast) precision %.3f over %d predicted removals'
          % (prec, remove_p.sum()))
    # attitude polarity reversals
    pa, ga = np.array(preds['attitude']), np.array(gold['attitude'])
    pos, neg = IDX['attitude']['positive'], IDX['attitude']['negative']
    flips = int((((pa == pos) & (ga == neg)) | ((pa == neg) & (ga == pos))).sum())
    directional = int(((ga == pos) | (ga == neg)).sum())
    out['polarity_reversals'] = flips
    out['directional_gold'] = directional
    out['reversal_rate'] = round(flips / directional, 4) if directional else None
    print(' polarity reversals %d of %d directional gold rows (%.1f%%)'
          % (flips, directional, 100.0 * flips / directional if directional else 0))
    return out


def gate_report(res, title):
    """The ship gates, as PASS/FAIL, on one evaluation set."""
    checks = [
        ('relevance macro-F1', res['relevance']['macro_f1'], GATES['relevance_macro_f1'], True),
        ('origin macro-F1', res['content_origin']['macro_f1'], GATES['content_origin_macro_f1'], True),
        ('removal precision', res['removal_precision'], GATES['removal_precision'], True),
        ('attitude accuracy', res['attitude']['accuracy'], GATES['attitude_accuracy'], True),
        ('reversal rate', res['reversal_rate'] or 0.0, GATES['reversal_rate_max'], False),
    ]
    print(' gates on %s:' % title)
    passed = 0
    for name, value, line, at_least in checks:
        ok = value >= line if at_least else value <= line
        passed += ok
        print('   %-18s %.3f  %s %.2f  %s' % (name, value, '>=' if at_least else '<=',
                                             line, 'PASS' if ok else 'FAIL'))
    print('   %d of %d gates pass' % (passed, len(checks)))
    return passed


def train_one(train_rows, tune_rows, test_rows, recall_rows, args, device, tag):
    tok = AutoTokenizer.from_pretrained(BASE)
    model = MultiHead(BASE).to(device)
    gen = torch.Generator()
    gen.manual_seed(args.seed)
    dl = lambda rows, shuffle: DataLoader(Rows(rows, tok), batch_size=args.batch_size,
                                          shuffle=shuffle, num_workers=0,
                                          generator=gen if shuffle else None)
    train_loader, tune_loader, test_loader = (dl(train_rows, True), dl(tune_rows, False),
                                              dl(test_rows, False))  # tune=natural, test=hard
    recall_loader = dl(recall_rows, False) if recall_rows else None
    # class weights: rare classes (mixed, uncertain, 4chan-ish) must not vanish
    weights = {}
    for h, classes in HEADS.items():
        # Counted over the rows that will actually reach this head's loss,
        # or the tone heads would be balanced against a distribution the
        # mask removes.
        counted = [r for r in train_rows
                   if tone_training.is_trainable({'y': RAW_Y[r['mention_id']]}, h)]
        counts = collections.Counter(r['y'][h] for r in counted)
        w = torch.tensor([1.0 / max(1, counts.get(i, 0)) ** 0.5
                          for i in range(len(classes))], dtype=torch.float, device=device)
        w = w / w.mean()
        weights[h] = w.clamp(max=4.0)
    losses = {h: nn.CrossEntropyLoss(weight=weights[h], reduction='none')
              for h in HEADS}
    # gold index -> the index it must not be confused with (positive/negative,
    # up/down). A reversal puts a mention on the WRONG side of the board;
    # cross-entropy alone charges it like any other miss.
    opposite = {}
    for h, classes in HEADS.items():
        mapping = tone_training.opposite_index_map(h, classes)
        if not mapping:
            continue
        table = torch.full((len(classes),), -1, dtype=torch.long)
        for gold, other in mapping.items():
            table[gold] = other
        opposite[h] = table.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    accum = max(1, args.accumulate)
    steps = (len(train_loader) + accum - 1) // accum * args.epochs
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps,
                                                pct_start=0.1)
    t0 = time.time()
    # A crash costs one epoch, not the run: this machine throws 0x116 about
    # every five days regardless of workload (see checkpointing.py).
    ckpt_path = os.path.join(OUT_DIR, 'checkpoint-%s.pt' % tag)
    settings = dict(vars(args))
    settings.update({'base': BASE, 'max_len': MAX_LEN, 'train_rows': len(train_rows),
                     'labels_sha': _sha(LABELS),
                     'recall_labels_sha': (_sha(RECALL_LABELS)
                                           if os.path.exists(RECALL_LABELS) else None)})
    start_epoch = 0
    if args.resume and os.path.exists(ckpt_path):
        saved = torch.load(ckpt_path, map_location=device, weights_only=False)
        if checkpointing.is_compatible(saved.get('settings'), settings):
            model.load_state_dict(saved['model'])
            opt.load_state_dict(saved['optimizer'])
            sched.load_state_dict(saved['scheduler'])
            start_epoch = saved['epochs_done']
            print(' resuming from %s at epoch %d/%d'
                  % (os.path.basename(ckpt_path), start_epoch, args.epochs))
        else:
            print(' checkpoint %s exists but its settings differ -- starting fresh'
                  % os.path.basename(ckpt_path))
    for epoch in range(start_epoch, args.epochs):
        model.train()
        total = 0.0
        opt.zero_grad()
        for i, batch in enumerate(train_loader, start=1):
            ys = {h: batch.pop('y_' + h).to(device) for h in HEADS}
            ms = {h: batch.pop('m_' + h).to(device) for h in HEADS}
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch)
            loss = 0.0
            for h in HEADS:
                per_row = losses[h](logits[h].float(), ys[h])
                mask = ms[h]
                # Mean over the rows that count, not over the batch: a batch
                # that happens to hold few relevant rows must not quietly
                # shrink the tone heads' gradient.
                loss = loss + (per_row * mask).sum() / mask.sum().clamp(min=1.0)
                if h in opposite and args.reversal_penalty > 0:
                    other = opposite[h][ys[h]]
                    charge = (other >= 0) & (mask > 0)
                    if bool(charge.any()):
                        probs = logits[h].float().softmax(-1)
                        p_opp = probs.gather(
                            1, other.clamp(min=0).unsqueeze(1)).squeeze(1)
                        loss = loss + args.reversal_penalty * (
                            (p_opp * charge.float()).sum()
                            / charge.float().sum().clamp(min=1.0))
            if not torch.isfinite(loss):
                raise SystemExit('non-finite loss at epoch %d -- aborting, '
                                 'numbers from a diverged run are worthless' % (epoch + 1))
            (loss / accum).backward()
            if i % accum == 0 or i == len(train_loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
            total += float(loss)
        print(' epoch %d/%d loss %.3f (%.0fs)' % (epoch + 1, args.epochs,
                                                  total / len(train_loader), time.time() - t0))
        if args.resume:
            tmp = ckpt_path + '.tmp'
            torch.save({'model': model.state_dict(), 'optimizer': opt.state_dict(),
                        'scheduler': sched.state_dict(), 'epochs_done': epoch + 1,
                        'settings': settings}, tmp)
            os.replace(tmp, ckpt_path)   # atomic: a crash mid-write keeps the old one
    res = {'tag': tag, 'train_rows': len(train_rows), 'natural_rows': len(tune_rows),
           'hard_rows': len(test_rows), 'epochs': args.epochs,
           'train_seconds': round(time.time() - t0, 1)}
    p, g = evaluate(model, tune_loader, device)
    res['natural'] = report(p, g, tune_rows, '%s LOCKED NATURAL (board traffic)' % tag)
    p, g = evaluate(model, test_loader, device)
    res['hard'] = report(p, g, test_rows, '%s LOCKED HARD (rare classes)' % tag)
    if recall_loader is not None:
        p, g = evaluate(model, recall_loader, device)
        res['recall_rows'] = len(recall_rows)
        res['recall'] = report(p, g, recall_rows,
                               '%s LOCKED RECALL (what the rules never accepted)' % tag)
    return model, tok, res


def main():
    global MAX_LEN
    ap = argparse.ArgumentParser()
    ap.add_argument('--subset', type=int, default=0, help='cap on labelled rows')
    ap.add_argument('--curve', default='', help='comma list of train sizes')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--batch-size', type=int, default=8)
    ap.add_argument('--lr', type=float, default=3e-5)
    ap.add_argument('--save', action='store_true')
    ap.add_argument('--seed', type=int, default=20260905)
    ap.add_argument('--max-len', type=int, default=MAX_LEN)
    # 512 tokens at batch 16 overflows the 3080's 10 GB and spills into
    # system RAM (froze the PC, 2026-09-05). Batch 8 x accumulate 2 is the
    # same effective batch at roughly half the VRAM.
    ap.add_argument('--no-resume', dest='resume', action='store_false',
                    help='ignore any checkpoint and do not write one')
    ap.set_defaults(resume=True)
    ap.add_argument('--reversal-penalty', type=float, default=1.0,
                    help='extra loss on the probability given to the polarity '
                         'opposite of the gold class (0 disables)')
    ap.add_argument('--accumulate', type=int, default=2,
                    help='gradient accumulation steps; effective batch = batch * this')
    args = ap.parse_args()
    MAX_LEN = args.max_len
    seed_everything(args.seed)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    rows = load_rows()
    if args.subset:
        rows = rows[:args.subset]
    train_rows, natural_rows, hard_rows, recall_rows, exclusions = split(rows)
    print('rows %d -> train %d / locked natural %d / hard %d / recall %d on %s'
          % (len(rows), len(train_rows), len(natural_rows), len(hard_rows),
             len(recall_rows), device))
    print('excluded from training: %d share a locked post, %d near-duplicates '
          '(%d distinct hashes within Hamming %d of a locked row)'
          % (exclusions['shared_post'], exclusions['near_duplicate'],
             exclusions['near_duplicate_hashes'], HAMMING_LIMIT))
    manifest = {
        'seed': args.seed, 'max_len': MAX_LEN, 'epochs': args.epochs,
        'lr': args.lr, 'batch_size': args.batch_size, 'base': BASE,
        'tone_mask': 'relevance==relevant for %s' % (tone_training.TONE_HEADS,),
        'reversal_penalty': args.reversal_penalty,
        'labels_sha': _sha(LABELS), 'export_sha': _sha(EXPORT),
        'test_natural_sha': _sha(TEST_NATURAL), 'test_hard_sha': _sha(TEST_HARD),
        'git_head': _git_head(), 'labelled_rows': len(rows),
        'train_rows': len(train_rows), 'natural_rows': len(natural_rows),
        'hard_rows': len(hard_rows), 'recall_rows': len(recall_rows),
        'recall_labels_sha': _sha(RECALL_LABELS) if os.path.exists(RECALL_LABELS) else None,
        'test_recall_sha': _sha(TEST_RECALL) if os.path.exists(TEST_RECALL) else None,
        'exclusions': exclusions,
        'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    for h in HEADS:
        # The mix the head actually SEES: printing all 17,090 rows here
        # while the tone heads train on 11,057 of them misleads whoever
        # reads the log later.
        seen = [r for r in train_rows
                if tone_training.is_trainable({'y': RAW_Y[r['mention_id']]}, h)]
        print(' %-15s trains on %5d rows, mix %s'
              % (h, len(seen), dict(collections.Counter(
                  HEADS[h][r['y'][h]] for r in seen))))
    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    sizes = ([int(s) for s in args.curve.split(',')] if args.curve
             else [len(train_rows)])
    for size in sizes:
        subset = train_rows[:size]
        tag = 'train%d' % len(subset)
        print('\n' + '=' * 70 + '\n' + tag)
        model, tok, res = train_one(subset, natural_rows, hard_rows, recall_rows,
                                    args, device, tag)
        results.append(res)
        res['manifest'] = manifest
        if args.save and size == sizes[-1]:
            # Stamped, because a bare tag made every run overwrite the last
            # one -- and once the previous weights are gone, no A/B against
            # them is possible. `model-latest` is a convenience pointer.
            stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
            path = os.path.join(OUT_DIR, 'model-%s-%s' % (tag, stamp))
            os.makedirs(path, exist_ok=True)
            torch.save(model.state_dict(), os.path.join(path, 'weights.pt'))
            tok.save_pretrained(path)
            json.dump({'base': BASE, 'heads': HEADS, 'max_len': MAX_LEN,
                       'manifest': manifest},
                      open(os.path.join(path, 'config.json'), 'w'), indent=1)
            pointer = os.path.join(OUT_DIR, 'model-latest.txt')
            with open(pointer, 'w', encoding='utf-8') as handle:
                handle.write(path)
            print('saved to', path)
        done_ckpt = os.path.join(OUT_DIR, 'checkpoint-%s.pt' % tag)
        if os.path.exists(done_ckpt):
            os.remove(done_ckpt)         # the run finished; its results are written
        del model
        torch.cuda.empty_cache()
    out = os.path.join(OUT_DIR, 'results.json')
    prev = json.load(open(out)) if os.path.exists(out) else []
    json.dump(prev + results, open(out, 'w'), indent=1)
    run_id = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    json.dump({'manifest': manifest, 'results': results},
              open(os.path.join(OUT_DIR, 'run-%s.json' % run_id), 'w'), indent=1)
    print('\ncurve on the LOCKED sets (macro-F1 where the gate says F1):')
    for which in ('natural', 'hard', 'recall'):
        if not all(which in r for r in results):
            continue
        print(' -- %s' % which)
        for r in results:
            t = r[which]
            print('   train %5d | rel F1 %.3f | orig F1 %.3f | att acc %.3f | '
                  'removal P %.3f | reversals %.1f%%'
                  % (r['train_rows'], t['relevance']['macro_f1'],
                     t['content_origin']['macro_f1'], t['attitude']['accuracy'],
                     t['removal_precision'], 100.0 * (t['reversal_rate'] or 0)))
    print()
    gate_report(results[-1]['natural'], 'natural (largest run)')


if __name__ == '__main__':
    main()
