"""Character spans -> per-token labels, the step that fails silently.

A tokenizer splits `GoPro` into pieces and reports where each piece came
from. The tagger learns per PIECE, so every span has to be projected onto
those pieces exactly. Get it off by one and the model trains on labels
that point at the wrong subword, which costs accuracy with no error and no
crash -- the reason this is a pure function with its own tests rather than
four lines inside a training loop.

BIO: B marks the first piece of a mention, I the rest, O everything else.
Two adjacent mentions stay separable because the second starts a new B.
"""
from scratchpad.label_export import span_tagging as st


def test_a_span_covering_one_token_is_a_single_b():
    # "GME to the moon"; offsets are (start, end) per token, CLS/SEP are (0,0)
    offsets = [(0, 0), (0, 3), (4, 6), (7, 10), (11, 15), (0, 0)]
    assert st.align(offsets, [(0, 3, 'GME')]) == ['O', 'B', 'O', 'O', 'O', 'O']


def test_a_span_split_into_subwords_is_b_then_i():
    # "GoPro" tokenized as "Go" + "Pro"
    offsets = [(0, 0), (0, 2), (2, 5), (6, 8), (0, 0)]
    assert st.align(offsets, [(0, 5, 'GPRO')]) == ['O', 'B', 'I', 'O', 'O']


def test_special_tokens_are_always_ignored():
    """CLS/SEP/PAD report (0, 0) and must never be labelled, even though
    0 sits inside a span that starts at 0."""
    offsets = [(0, 0), (0, 3), (0, 0), (0, 0)]
    assert st.align(offsets, [(0, 3, 'GME')]) == ['O', 'B', 'O', 'O']


def test_two_mentions_side_by_side_each_start_a_new_b():
    offsets = [(0, 0), (0, 4), (5, 9), (0, 0)]
    labels = st.align(offsets, [(0, 4, 'NVDA'), (5, 9, 'GPRO')])
    assert labels == ['O', 'B', 'B', 'O']


def test_a_span_beyond_the_truncation_point_is_simply_absent():
    """Long posts are cut at max_len. A span past the cut cannot be
    labelled and must not raise -- but the caller needs to know."""
    offsets = [(0, 0), (0, 3), (0, 0)]
    labels = st.align(offsets, [(0, 3, 'GME'), (900, 904, 'TSLA')])
    assert labels == ['O', 'B', 'O']
    assert st.lost_spans(offsets, [(0, 3, 'GME'), (900, 904, 'TSLA')]) == [(900, 904, 'TSLA')]


def test_a_token_only_partly_inside_a_span_still_counts():
    """Tokenizers do not respect our word boundaries; a piece that
    overlaps the span at all belongs to it."""
    offsets = [(0, 0), (0, 6), (0, 0)]          # one token covering "GoProX"
    assert st.align(offsets, [(0, 5, 'GPRO')]) == ['O', 'B', 'O']


def test_a_post_with_no_spans_is_all_o():
    offsets = [(0, 0), (0, 3), (4, 8), (0, 0)]
    assert st.align(offsets, []) == ['O', 'O', 'O', 'O']


def test_the_label_ids_are_stable_and_o_is_zero():
    """O must be 0 so padding and ignored positions read naturally."""
    assert st.LABELS == ['O', 'B', 'I']
    assert st.LABEL_ID['O'] == 0
    assert st.to_ids(['O', 'B', 'I']) == [0, 1, 2]
