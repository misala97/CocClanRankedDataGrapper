# personal_apps/scratchpad/label_export/span_tagging.py
"""Project character spans onto tokenizer pieces. BIO labels.

This is the step that fails silently. A tokenizer splits `GoPro` into
pieces and reports the character range each piece came from; the tagger
learns per PIECE, so every span has to land on exactly the right ones. Off
by one and the model trains on labels pointing at the wrong subword, with
no error and no crash -- which is why this is a pure function with its own
tests rather than four lines inside a training loop.

BIO: `B` on the first piece of a mention, `I` on the rest, `O` elsewhere.
The distinction is not decoration: two companies named side by side would
merge into one mention under a single label, and `B` is what keeps them
apart when the spans are read back out.

Torch-free; it takes the offset list a tokenizer already produces.
"""

LABELS = ['O', 'B', 'I']
LABEL_ID = {name: index for index, name in enumerate(LABELS)}


def _is_special(offset):
    """Tokenizers report (0, 0) for CLS/SEP/PAD.

    Checking the width rather than the position matters: a real first token
    also starts at 0, and treating it as special would silently drop every
    mention that opens a post.
    """
    return offset[1] <= offset[0]


def align(offsets, spans):
    """One label per token, given `offsets` from the tokenizer and
    character `spans` of (start, end, ticker)."""
    labels = ['O'] * len(offsets)
    for start, end, _ticker in spans:
        first = True
        for index, (token_start, token_end) in enumerate(offsets):
            if _is_special((token_start, token_end)):
                continue
            # Any overlap counts: a tokenizer does not respect our word
            # boundaries, so a piece straddling the edge belongs to the span.
            if token_start < end and token_end > start:
                labels[index] = 'B' if first else 'I'
                first = False
    return labels


def lost_spans(offsets, spans):
    """Spans that landed on no token, because the text was truncated.

    Returned rather than ignored: a training set quietly missing its later
    mentions looks exactly like a model that fails to find them.
    """
    lost = []
    for span in spans:
        start, end, _ticker = span
        if not any(not _is_special(o) and o[0] < end and o[1] > start for o in offsets):
            lost.append(span)
    return lost


def to_ids(labels):
    return [LABEL_ID[name] for name in labels]
