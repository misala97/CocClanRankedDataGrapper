# personal_apps/scratchpad/label_export/train_ner.py
"""Train the span tagger: a DeBERTa backbone and one linear layer over BIO.

THE SECOND MODEL, first attempt. The encoder answers "is this text about
ticker X" and cannot find X; this finds the words that name a company so
a lookup can map them and the encoder can judge the pair. Michi's call
2026-09-08: small backbone, four epochs, see where it lands -- against
zero-shot GLiNER on the same two benchmarks (the held-out spans, and the
3,000-post headroom probe through the same lookup and judge).

WHAT IS HELD OUT. Every example touching any of the three locked test
sets (natural / hard / recall) is held out whole, the encoder's protocol,
so the number is on posts nothing was trained on and nothing leaks.

Checkpointed after every epoch under the checkpointing contract, because
this machine crashes on its own. The save directory is stamped and never
overwritten -- the encoder work lost an A/B to `--save` once.

Runs in the encoder venv:

    C:/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe
        scratchpad/label_export/train_ner.py --epochs 4
"""
import argparse
import hashlib
import json
import os
import random
import sys
import time

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkpointing                                       # noqa: E402
import ner_tagging                                         # noqa: E402

BASE = 'microsoft/deberta-v3-small'
LABELS_DIR = 'C:/Users/michi/Desktop/radar_labels'
DEFAULT_SPANS = LABELS_DIR + '/spans-2026-09-07.jsonl'
TEST_SETS = ('test-natural.json', 'test-hard.json', 'test-recall.json')
OUT_ROOT = LABELS_DIR + '/ner'
N_LABELS = len(ner_tagging.LABELS)


def _sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()[:16]


# ---- data --------------------------------------------------------------------

def encode(tok, text, max_len):
    """Pieces and offsets for one text. Offsets are what align() and
    bio_decode() speak; nothing else about the tokenizer is trusted."""
    return tok(text, truncation=True, max_length=max_len,
               return_offsets_mapping=True)


class Pieces(Dataset):
    """Pre-tokenised once: 14k posts at 256 pieces is a few MB, and doing
    it per epoch would spend more time in the tokenizer than the GPU."""

    def __init__(self, examples, tok, max_len):
        self.items = []
        for example in examples:
            enc = encode(tok, example['text'], max_len)
            offsets = [tuple(o) for o in enc['offset_mapping']]
            item = {'input_ids': enc['input_ids'],
                    'attention_mask': enc['attention_mask'],
                    'labels': ner_tagging.label_ids_for(
                        offsets, example['spans'],
                        silver=example.get('silver', ()), ignore=example.get('ignore', ()))}
            if 'token_type_ids' in enc:
                item['token_type_ids'] = enc['token_type_ids']
            self.items.append(item)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


def make_collate(pad_id):
    def collate(items):
        width = max(len(item['input_ids']) for item in items)

        def pad(key, value):
            return torch.tensor([item[key] + [value] * (width - len(item[key]))
                                 for item in items])
        batch = {'input_ids': pad('input_ids', pad_id),
                 'attention_mask': pad('attention_mask', 0),
                 'labels': pad('labels', ner_tagging.IGNORE)}
        if 'token_type_ids' in items[0]:
            batch['token_type_ids'] = pad('token_type_ids', 0)
        return batch
    return collate


# ---- model -------------------------------------------------------------------

class Tagger(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base, dtype=torch.float32)
        self.drop = nn.Dropout(0.1)
        self.head = nn.Linear(self.encoder.config.hidden_size, N_LABELS)

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        kwargs = {'input_ids': input_ids, 'attention_mask': attention_mask}
        if token_type_ids is not None:
            kwargs['token_type_ids'] = token_type_ids
        hidden = self.encoder(**kwargs).last_hidden_state
        return self.head(self.drop(hidden))


def load_model(model_dir, device=None):
    """A saved tagger, ready to predict. What the probe calls."""
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    with open(os.path.join(model_dir, 'config.json'), encoding='utf-8') as handle:
        config = json.load(handle)
    tok = AutoTokenizer.from_pretrained(config['base'])
    model = Tagger(config['base'])
    model.load_state_dict(torch.load(os.path.join(model_dir, 'model.pt'),
                                     map_location=device, weights_only=True))
    model.to(device).eval()
    return tok, model, config, device


@torch.no_grad()
def predict_spans(model, tok, texts, device, max_len, batch_size=32, with_scores=False):
    """Character spans per text. With scores: (start, end, mean max-prob
    over the span's pieces), so a caller can see a 0.51 from a 0.99."""
    model.eval()
    out = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        encs = [encode(tok, text, max_len) for text in chunk]
        width = max(len(e['input_ids']) for e in encs)
        pad_id = tok.pad_token_id
        feed = {'input_ids': torch.tensor([e['input_ids'] + [pad_id] * (width - len(e['input_ids'])) for e in encs]),
                'attention_mask': torch.tensor([e['attention_mask'] + [0] * (width - len(e['attention_mask'])) for e in encs])}
        if 'token_type_ids' in encs[0]:
            feed['token_type_ids'] = torch.tensor([e['token_type_ids'] + [0] * (width - len(e['token_type_ids'])) for e in encs])
        feed = {k: v.to(device) for k, v in feed.items()}
        with torch.autocast('cuda', dtype=torch.bfloat16, enabled=device == 'cuda'):
            logits = model(**feed)
        probs = logits.float().softmax(-1)
        best_p, best = probs.max(-1)
        for row, enc in enumerate(encs):
            offsets = [tuple(o) for o in enc['offset_mapping']]
            ids = best[row, :len(offsets)].tolist()
            spans = ner_tagging.bio_decode(ids, offsets)
            if with_scores:
                conf = best_p[row, :len(offsets)].tolist()
                scored = []
                for s, e in spans:
                    inside = [conf[i] for i, (os_, oe) in enumerate(offsets)
                              if oe > os_ and os_ < e and oe > s]
                    scored.append((s, e, sum(inside) / max(1, len(inside))))
                out.append(scored)
            else:
                out.append(spans)
    return out


def evaluate(model, tok, examples, device, max_len, batch_size):
    preds = predict_spans(model, tok, [e['text'] for e in examples], device, max_len, batch_size)
    return ner_tagging.span_prf(examples, preds)


def report(table, title):
    print('  %s  P %.3f  R %.3f  F1 %.3f   (tp %d fp %d fn %d)'
          % (title, table['precision'], table['recall'], table['f1'],
             table['tp'], table['fp'], table['fn']))
    print('    recall by kind: %s' % '  '.join(
        '%s %d/%d=%.1f%%' % (kind, f, n, 100.0 * f / max(1, n))
        for kind, (f, n) in sorted(table['recall_by_kind'].items(), key=lambda kv: -kv[1][1])))


# ---- training ----------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--spans', default=DEFAULT_SPANS)
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--batch-size', type=int, default=16)
    ap.add_argument('--lr', type=float, default=3e-5)
    ap.add_argument('--max-len', type=int, default=256)
    ap.add_argument('--seed', type=int, default=20260908)
    ap.add_argument('--base', default=BASE)
    ap.add_argument('--out', default=OUT_ROOT)
    ap.add_argument('--no-resume', dest='resume', action='store_false')
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    with open(args.spans, encoding='utf-8') as handle:
        examples = [json.loads(line) for line in handle if line.strip()]
    test_ids = set()
    for name in TEST_SETS:
        with open(os.path.join(LABELS_DIR, name), encoding='utf-8') as handle:
            test_ids.update(json.load(handle))
    train_rows, held_rows = ner_tagging.split_holdout(examples, test_ids)
    held_rows, shared = ner_tagging.drop_shared_texts(train_rows, held_rows)
    print('examples %d -> train %d (%d with spans), held out %d (%d with spans, %d spans; '
          '%d dropped for sharing a text with training)'
          % (len(examples), len(train_rows), sum(1 for e in train_rows if e['spans']),
             len(held_rows), sum(1 for e in held_rows if e['spans']),
             sum(len(e['spans']) for e in held_rows), shared), flush=True)

    tok = AutoTokenizer.from_pretrained(args.base)
    t0 = time.time()
    train_set = Pieces(train_rows, tok, args.max_len)
    print('tokenised in %.0fs' % (time.time() - t0), flush=True)
    generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True,
                        collate_fn=make_collate(tok.pad_token_id), generator=generator)

    model = Tagger(args.base).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * len(loader)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps,
                                                pct_start=0.1, anneal_strategy='linear')

    # The checkpointing contract's field names, so is_compatible() reads
    # them unchanged. reversal_penalty is the encoder's; here it is 0 and
    # must stay 0 for a checkpoint to match.
    settings = {'base': args.base, 'lr': args.lr, 'batch_size': args.batch_size,
                'accumulate': 1, 'max_len': args.max_len, 'seed': args.seed,
                'reversal_penalty': 0.0, 'train_rows': len(train_rows),
                'labels_sha': _sha(args.spans), 'recall_labels_sha': None,
                'epochs': args.epochs}
    os.makedirs(os.path.join(args.out, 'checkpoints'), exist_ok=True)
    ckpt_path = os.path.join(args.out, 'checkpoints',
                             'ner-%s-%d.pt' % (args.base.split('/')[-1], args.max_len))
    start_epoch, history = 0, []
    if args.resume and os.path.exists(ckpt_path):
        saved = torch.load(ckpt_path, map_location=device, weights_only=False)
        if checkpointing.is_compatible(saved.get('settings'), settings):
            model.load_state_dict(saved['model'])
            opt.load_state_dict(saved['optimizer'])
            sched.load_state_dict(saved['scheduler'])
            start_epoch = saved['epochs_done']
            history = saved.get('history', [])
            print(' resuming at epoch %d/%d' % (start_epoch, args.epochs), flush=True)
        else:
            print(' checkpoint exists but its settings differ -- starting fresh', flush=True)

    t0 = time.time()
    for epoch in range(start_epoch, args.epochs):
        model.train()
        total = 0.0
        for batch in loader:
            labels = batch.pop('labels').to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.autocast('cuda', dtype=torch.bfloat16, enabled=device == 'cuda'):
                logits = model(**batch)
            loss = F.cross_entropy(logits.float().view(-1, N_LABELS), labels.view(-1),
                                   ignore_index=ner_tagging.IGNORE)
            if not torch.isfinite(loss):
                raise SystemExit('non-finite loss at epoch %d -- aborting, numbers '
                                 'from a diverged run are worthless' % (epoch + 1))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            total += float(loss)
        print(' epoch %d/%d loss %.4f (%.0fs)' % (epoch + 1, args.epochs,
                                                   total / len(loader), time.time() - t0), flush=True)
        table = evaluate(model, tok, held_rows, device, args.max_len, args.batch_size * 2)
        report(table, 'held-out epoch %d' % (epoch + 1))
        history.append({'epoch': epoch + 1, 'loss': round(total / len(loader), 4), **table})
        if args.resume:
            tmp = ckpt_path + '.tmp'
            torch.save({'model': model.state_dict(), 'optimizer': opt.state_dict(),
                        'scheduler': sched.state_dict(), 'epochs_done': epoch + 1,
                        'settings': settings, 'history': history}, tmp)
            os.replace(tmp, ckpt_path)

    stamp = time.strftime('%Y%m%d-%H%M%S')
    model_dir = os.path.join(args.out, 'model-ner-%s-%s' % (args.base.split('/')[-1], stamp))
    os.makedirs(model_dir, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(model_dir, 'model.pt'))
    with open(os.path.join(model_dir, 'config.json'), 'w', encoding='utf-8') as handle:
        json.dump({'base': args.base, 'max_len': args.max_len, 'labels': ner_tagging.LABELS,
                   'manifest': {**settings, 'held_out_rows': len(held_rows),
                                'train_seconds': round(time.time() - t0, 1),
                                'spans_file': os.path.basename(args.spans)}},
                  handle, indent=1)
    with open(os.path.join(model_dir, 'results.json'), 'w', encoding='utf-8') as handle:
        json.dump(history, handle, indent=1)
    with open(os.path.join(args.out, 'model-ner-latest.txt'), 'w', encoding='utf-8') as handle:
        handle.write(model_dir)
    print('saved %s' % model_dir)


if __name__ == '__main__':
    main()
