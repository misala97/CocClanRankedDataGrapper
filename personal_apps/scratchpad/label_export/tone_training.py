# personal_apps/scratchpad/label_export/tone_training.py
"""What the tone heads learn from, and what a polarity flip costs.

Deliberately free of torch: these are decisions about the DATA, and they
belong in the ordinary test suite rather than only inside the training
venv. train_encoder.py turns what is here into tensors.

TWO FINDINGS DRIVE THIS, both from the 2026-09-06/07 runs.

The direction heads are fed mostly non-answers. Of 10,323 relevant rows,
6,019 say `unknown` for expected_move -- and on top of those, every
IRRELEVANT or UNCERTAIN row carries `none`/`unknown` because the labelling
prompt FORCES it ("if relevance is not relevant, attitude must be none and
expected_move must be unknown"). Those 4,890 forced rows are not
judgements; they are a restatement of the relevance label. Training on
them teaches the tone heads to answer `none` and rewards them for it, so
`attitude` sat at 0.71-0.75 accuracy while predicting `none` covered most
of the set. Masking them out costs nothing real: a `relevant` row that
genuinely carries no attitude is KEPT, because "the author mentioned it
without taking a side" is a real observation.

A polarity reversal is not an ordinary error. Calling `up` when the truth
is `down` puts a mention on the wrong side of the board; calling `up` when
the truth is `unknown` merely adds noise. Cross-entropy charges both the
same, and the measured reversal rate stayed at 13-17% against a 2% gate.
`opposite_index_map` names the pairs a loss should charge extra for.
"""

# The heads whose labels are forced to a constant on non-relevant rows.
TONE_HEADS = ('attitude', 'expected_move')

# Per head, the two classes that are each other's opposite. Anything not
# named here has no opposite: `mixed` is not the reverse of `none`, and
# `flat` is a genuine third answer rather than the negation of `up`.
OPPOSITES = {
    'attitude': {'positive': 'negative', 'negative': 'positive'},
    'expected_move': {'up': 'down', 'down': 'up'},
}

# A row may teach the tone heads only when its relevance is this.
TONE_REQUIRES_RELEVANCE = 'relevant'


def is_trainable(row, head):
    """Whether `row` may contribute to `head`'s loss.

    Every row teaches relevance, content_origin and confidence -- those are
    judged on their own terms. The tone heads see only rows whose relevance
    is `relevant`, because the others carry a label the prompt wrote rather
    than the teacher.
    """
    if head not in TONE_HEADS:
        return True
    return row['y']['relevance'] == TONE_REQUIRES_RELEVANCE


def trainable_mask(rows, head):
    """`is_trainable` over a batch, in order."""
    return [is_trainable(row, head) for row in rows]


def opposite_class(head, name):
    """The class a prediction must not be confused with, or None."""
    return OPPOSITES.get(head, {}).get(name)


def opposite_index_map(head, classes):
    """{gold index -> opposite index} for one head's class list.

    Indices, because a loss works in them. Empty for any head with no
    directional pair, which is how a caller knows to skip the term.
    """
    order = {name: index for index, name in enumerate(classes)}
    mapping = {}
    for name, other in OPPOSITES.get(head, {}).items():
        if name in order and other in order:
            mapping[order[name]] = order[other]
    return mapping
