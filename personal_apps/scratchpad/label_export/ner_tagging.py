# personal_apps/scratchpad/label_export/ner_tagging.py
"""The torch-free half of training a span tagger: which tokens carry a
label, how a run of predictions becomes character spans again, which
posts are held out, and how a prediction is scored.

Everything here is a rule that can be wrong silently, which is why it is
a pure function with a test rather than four lines inside the training
loop. `span_tagging.align` already projects spans onto pieces; this adds
the three things around it.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import span_tagging                                        # noqa: E402
from gliner_recall_check import covered, kind_of            # noqa: E402

IGNORE = -100          # what torch's cross-entropy skips
LABELS = span_tagging.LABELS


def label_ids_for(offsets, spans, silver=(), ignore=()):
    """One label id per piece, IGNORE on specials and padding.

    align() gives specials 'O', which is a label the loss would learn
    from; CLS and SEP must teach nothing. `silver` regions are labelled
    like spans; `ignore` regions (an unlabelled symbol-shaped token) are
    masked so a piece the labels never decided teaches nothing either --
    unless a gold span covers it, gold wins.
    """
    names = span_tagging.align(offsets, list(spans) + [(s, e, None) for s, e in silver])
    gold = [(s, e) for s, e, _ in spans]
    ids = []
    for (start, end), name in zip(offsets, names):
        if end <= start:
            ids.append(IGNORE)
        elif (any(start < e and end > s for s, e in ignore)
              and not any(start < e and end > s for s, e in gold)):
            ids.append(IGNORE)
        else:
            ids.append(span_tagging.LABEL_ID[name])
    return ids


def bio_decode(label_ids, offsets):
    """Character spans from per-piece predictions.

    B opens a span, I extends it, O closes it. An I with nothing open ALSO
    opens one: the model will sometimes mark a mention's first piece I,
    and refusing that would drop the whole mention over one label. A
    special piece closes whatever is open, so a span can never run across
    SEP. Spans carry the pieces' offsets as they are -- a piece that owns
    its leading space hands it on, and the caller strips.
    """
    spans, current = [], None
    for label_id, (start, end) in zip(label_ids, offsets):
        if end <= start:
            if current:
                spans.append(tuple(current))
                current = None
            continue
        name = LABELS[label_id] if 0 <= label_id < len(LABELS) else 'O'
        if name == 'B' or (name == 'I' and current is None):
            if current:
                spans.append(tuple(current))
            current = [start, end]
        elif name == 'I':
            current[1] = end
        elif current:
            spans.append(tuple(current))
            current = None
    if current:
        spans.append(tuple(current))
    return spans


def split_holdout(examples, test_mention_ids):
    """(train, held_out). An example touching ANY locked test mention is
    held out whole: a post half in training and half in test would leak
    its text."""
    held = set(test_mention_ids)
    train, out = [], []
    for example in examples:
        (out if held.intersection(example['mention_ids']) else train).append(example)
    return train, out


def span_prf(examples, predicted):
    """Span-level precision / recall / F1 by overlap, plus recall by the
    gold span's surface kind. `predicted` is one list of (start, end) per
    example, in the same order.

    A gold span covered by any prediction is one hit however many pieces
    predicted it; a prediction covering no gold is one false positive,
    including every prediction on a post with no spans at all -- those
    posts are where a finder's precision is actually decided.
    """
    tp = fp = fn = 0
    by_kind = collections.defaultdict(lambda: [0, 0])
    for example, preds in zip(examples, predicted):
        gold = [(s, e) for s, e, _ in example['spans']]
        # A prediction on a region the labels never decided -- a filled
        # name or a masked symbol -- is neither a hit nor a false positive.
        undecided = ([tuple(r) for r in example.get('silver', ())]
                     + [tuple(r) for r in example.get('ignore', ())])
        pred_dicts = [{'start': s, 'end': e} for s, e in preds]
        for start, end in gold:
            kind = kind_of(example['text'][start:end])
            by_kind[kind][1] += 1
            if covered((start, end), pred_dicts):
                tp += 1
                by_kind[kind][0] += 1
            else:
                fn += 1
        for start, end in preds:
            if any(start < ge and end > gs for gs, ge in gold):
                continue
            if any(start < ue and end > us for us, ue in undecided):
                continue
            fp += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': round(precision, 4), 'recall': round(recall, 4),
            'f1': round(f1, 4), 'recall_by_kind': dict(by_kind)}
