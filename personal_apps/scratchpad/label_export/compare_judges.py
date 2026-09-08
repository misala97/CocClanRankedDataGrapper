# personal_apps/scratchpad/label_export/compare_judges.py
"""Score two encoder checkpoints on the trial audit's 746 rows, side by side.

Deliverable 4 of the hard-negative retrain. The question is never "is the
new model good" in the abstract -- it is whether it beats the artifact
serving production on the number that decides the board's counts:
REMOVAL PRECISION, the rate at which a verdict that deletes a mention is
right. False rejects are rare (2 of 78 on the NER probe); false accepts
are the measured defect.

Two properties are borrowed from `features.radar.trial_audit` rather than
re-derived, because the trial's own report used them and the numbers have
to be comparable: a model's removal denominator is ITS OWN predicted
removals, and a missing prediction is a disagreement rather than an
excused absence.

The audit chain's `predict` refuses any artifact but the one the trial
armed, which is correct for the chain and useless here, so this scores
local checkpoints offline and writes its own report. Nothing it does can
touch a mention, a bucket or the trial.

    cd personal_apps && PYTHONPATH=. <torch venv python> \\
        scratchpad/label_export/compare_judges.py \\
        --live  C:/Users/michi/Desktop/radar_labels/encoder/model-train17090-20260907-192428 \\
        --new   C:/Users/michi/Desktop/radar_labels/encoder/model-<the retrain> \\
        --out   C:/Users/michi/Desktop/radar_labels/compare-746.md
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from features.radar import trial_audit  # noqa: E402

FIELDS = ('relevance', 'content_origin', 'attitude', 'expected_move')
ROOT = r'C:\Users\michi\Desktop\radar_labels'
BLIND = os.path.join(ROOT, 'trial-audit', 'blind.jsonl')
REFERENCE = os.path.join(ROOT, 'trial-audit', 'reference.jsonl')


def removal(predictions, reference):
    """Precision of the verdicts that would DELETE a mention, or None when
    a model removed nothing -- a failed criterion, never a perfect score."""
    try:
        return trial_audit.removal_precision(predictions, reference)
    except trial_audit.AuditError:
        return None


def agreement(predictions, reference, field):
    return trial_audit.field_agreement(predictions, reference, field)


def reversals(predictions, reference):
    """Polarity flips over the rows whose gold attitude has a direction, or
    None when the reference holds no directional row to flip."""
    try:
        return trial_audit.reversal_rate(predictions, reference)
    except trial_audit.AuditError:
        return None


def wins(challenger, incumbent):
    """Whether `challenger` beats `incumbent` on the Wilson LOWER bound.

    The point estimate moves on noise; the bound is what a decision may
    rest on. A model with nothing to report never wins.
    """
    if not challenger or 'lower' not in challenger:
        return False
    if not incumbent or 'lower' not in incumbent:
        return True
    return challenger['lower'] > incumbent['lower']


def table(predictions_by_name, reference):
    """One row per metric, one column per model."""
    rows = [{'metric': 'removal_precision', 'higher_is_better': True}]
    rows += [{'metric': field, 'higher_is_better': True} for field in FIELDS]
    rows.append({'metric': 'polarity_reversals', 'higher_is_better': False})
    for row in rows:
        for name, predictions in predictions_by_name.items():
            if row['metric'] == 'removal_precision':
                row[name] = removal(predictions, reference)
            elif row['metric'] == 'polarity_reversals':
                row[name] = reversals(predictions, reference)
            else:
                row[name] = agreement(predictions, reference, row['metric'])
    return rows


def _cell(interval):
    if not interval or 'point' not in interval:
        return '--'
    return '%.3f (%d/%d, %.3f-%.3f)' % (
        interval['point'], interval['successes'], interval['total'],
        interval['lower'], interval['upper'])


def markdown(rows, names, extra=()):
    out = ['| metric | %s |' % ' | '.join(names),
           '|---|%s' % ('---|' * len(names))]
    for row in rows:
        out.append('| %s | %s |' % (row['metric'],
                                    ' | '.join(_cell(row.get(n)) for n in names)))
    return '\n'.join(list(extra) + out)


# ---- scoring, torch ------------------------------------------------------------

def load_rows(blind_path=BLIND, reference_path=REFERENCE):
    """The 746 blind rows and their reference verdicts."""
    blind = [json.loads(l) for l in open(blind_path, encoding='utf-8') if l.strip()]
    reference = {}
    for line in open(reference_path, encoding='utf-8'):
        if line.strip():
            row = json.loads(line)
            reference[row['mention_id']] = {f: row[f] for f in
                                            ('relevance', 'content_origin',
                                             'attitude', 'expected_move',
                                             'confidence')}
    return blind, reference


def prepared_text(row):
    """The canonical text the judge reads, built the way production builds
    it -- never the raw body, or the comparison measures a different input
    than the one the live judge sees."""
    from features.radar import sentiment_input
    prepared = sentiment_input.prepare_sentiment_input(
        row['source'], row.get('title'), row.get('body') or '', row['ticker'],
        author=row.get('author'), channel=row.get('channel') or '')
    return prepared.author_text


def predict(model_dir, rows):
    """Every row's five fields from one checkpoint."""
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoTokenizer
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import train_encoder as T

    config = json.load(open(os.path.join(model_dir, 'config.json'), encoding='utf-8'))
    T.MAX_LEN = config.get('max_len', T.MAX_LEN)
    base = config.get('base', T.BASE)
    T.BASE = base
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tokenizer = AutoTokenizer.from_pretrained(base)
    model = T.MultiHead(base).to(device)
    model.load_state_dict(torch.load(os.path.join(model_dir, 'weights.pt'),
                                     map_location=device))
    model.eval()
    items = [{'mention_id': r['mention_id'], 'ticker': r['ticker'],
              'text': prepared_text(r), 'y': {h: 0 for h in T.HEADS}}
             for r in rows]
    for item in items:
        T.RAW_Y[item['mention_id']] = {h: T.HEADS[h][0] for h in T.HEADS}
        T.RAW_STRATUM[item['mention_id']] = 'compare'
    out = {}
    index = 0
    with torch.no_grad():
        for batch in DataLoader(T.Rows(items, tokenizer), batch_size=16, shuffle=False):
            for head in T.HEADS:
                batch.pop('y_' + head, None)
                batch.pop('m_' + head, None)
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch)
            size = next(iter(batch.values())).shape[0]
            for j in range(size):
                out[items[index + j]['mention_id']] = {
                    head: T.HEADS[head][int(logits[head][j].argmax())]
                    for head in T.HEADS}
            index += size
    del model
    torch.cuda.empty_cache()
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--live', required=True, help='the serving checkpoint')
    parser.add_argument('--new', required=True, help='the challenger')
    parser.add_argument('--blind', default=BLIND)
    parser.add_argument('--reference', default=REFERENCE)
    parser.add_argument('--out', default=os.path.join(ROOT, 'compare-746.md'))
    args = parser.parse_args(argv)

    rows, reference = load_rows(args.blind, args.reference)
    print('rows %d, reference %d' % (len(rows), len(reference)))
    predictions = {}
    for name, model_dir in (('live', args.live), ('new', args.new)):
        predictions[name] = predict(model_dir, rows)
        print('%s: %d predictions from %s' % (name, len(predictions[name]),
                                              os.path.basename(model_dir)))
    rows_out = table(predictions, reference)
    header = ['# Trial audit, 746 rows: the serving judge against the retrain',
              '',
              '- live: `%s`' % args.live,
              '- new:  `%s`' % args.new,
              '- reference: `%s` (external, neither model trained on it)' % args.reference,
              '',
              'Each cell is the point estimate with (successes/total, Wilson 95%).',
              'The ship rule is the LOWER bound on removal precision, because a',
              'wrong deletion is the costliest error the judge makes.',
              '']
    verdict = next(r for r in rows_out if r['metric'] == 'removal_precision')
    footer = ['',
              '**Removal precision: %s** the serving judge.'
              % ('the retrain BEATS' if wins(verdict.get('new'), verdict.get('live'))
                 else 'the retrain DOES NOT beat')]
    text = markdown(rows_out, ('live', 'new'), extra=header) + '\n'.join(footer)
    with open(args.out, 'w', encoding='utf-8') as handle:
        handle.write(text + '\n')
    print(text)
    # the shapes the retrain was for: how each model does on the rows whose
    # gold says the mention is real, split by nothing but its own verdict
    for name, preds in predictions.items():
        counts = collections.Counter(v['relevance'] for v in preds.values())
        print('%-5s relevance mix %s' % (name, dict(counts)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
