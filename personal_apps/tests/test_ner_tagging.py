# personal_apps/tests/test_ner_tagging.py
"""The rules around the span tagger's training loop. Each one fails
silently when wrong: a label on CLS, a span that runs through SEP, a test
post leaking into training, a false positive counted as nothing."""
from scratchpad.label_export import ner_tagging as nt

B, I, O = nt.LABELS.index('B'), nt.LABELS.index('I'), nt.LABELS.index('O')
IGN = nt.IGNORE


def test_specials_carry_no_label_even_when_a_span_opens_the_text():
    # CLS, 'Apple', 'rocks', SEP, PAD
    offsets = [(0, 0), (0, 5), (6, 11), (0, 0), (0, 0)]
    assert nt.label_ids_for(offsets, [(0, 5, 'AAPL')]) == [IGN, B, O, IGN, IGN]


def test_decode_merges_runs_and_returns_offsets():
    offsets = [(0, 0), (0, 3), (3, 6), (7, 12), (13, 16), (0, 0)]
    #          CLS     Nvi     dia     rocks    AMD     SEP
    assert nt.bio_decode([IGN, B, I, O, B, IGN], offsets) == [(0, 6), (13, 16)]


def test_decode_opens_on_a_stray_i_and_splits_on_a_new_b():
    offsets = [(0, 0), (0, 3), (3, 6), (7, 10), (0, 0)]
    # I with nothing open still starts a span; a B right after closes it.
    assert nt.bio_decode([IGN, I, I, B, IGN], offsets) == [(0, 6), (7, 10)]


def test_decode_never_runs_a_span_across_a_special_or_off_the_end():
    offsets = [(0, 0), (0, 4), (0, 0), (5, 9)]
    # B, SEP, I: the SEP closes the first span; the trailing I is its own.
    assert nt.bio_decode([IGN, B, IGN, I], offsets) == [(0, 4), (5, 9)]
    assert nt.bio_decode([IGN, B, I], offsets[:3] + []) == [(0, 4)]


def test_decode_treats_ignore_as_outside():
    offsets = [(0, 0), (0, 4), (5, 9)]
    assert nt.bio_decode([IGN, IGN, B], offsets) == [(5, 9)]


def test_holdout_takes_a_post_whole_when_any_of_its_mentions_is_locked():
    examples = [
        {'mention_ids': [1, 2], 'text': 'a', 'spans': []},
        {'mention_ids': [3], 'text': 'b', 'spans': []},
        {'mention_ids': [4, 5], 'text': 'c', 'spans': []},
    ]
    train, out = nt.split_holdout(examples, {2, 99})
    assert [e['text'] for e in train] == ['b', 'c']
    assert [e['text'] for e in out] == ['a']


def test_prf_counts_hits_misses_and_false_positives_including_on_empty_posts():
    examples = [
        {'text': 'NVDA and Nvda', 'spans': [[0, 4, 'NVDA'], [9, 13, 'NVDA']]},
        {'text': 'nothing here', 'spans': []},
        {'text': 'apple', 'spans': [[0, 5, 'AAPL']]},
    ]
    predicted = [
        [(0, 4), (8, 13)],        # hit, hit (overlap counts)
        [(0, 7)],                 # false positive on a span-less post
        [],                       # miss
    ]
    got = nt.span_prf(examples, predicted)
    assert (got['tp'], got['fp'], got['fn']) == (2, 1, 1)
    assert got['precision'] == round(2 / 3, 4)
    assert got['recall'] == round(2 / 3, 4)
    assert got['recall_by_kind'] == {'ALLCAPS': [1, 1], 'Titlecase': [1, 1], 'lowercase': [0, 1]}


def test_prf_is_zero_not_an_error_when_nothing_is_predicted():
    got = nt.span_prf([{'text': 'NVDA', 'spans': [[0, 4, 'NVDA']]}], [[]])
    assert (got['precision'], got['recall'], got['f1']) == (0.0, 0.0, 0.0)


# ---- v2: silver and ignore regions ------------------------------------------

def test_silver_is_labelled_like_gold_and_ignore_is_masked_unless_gold_covers_it():
    #          CLS     Goo     gle     AI      NVDA    SEP
    offsets = [(0, 0), (0, 3), (3, 6), (7, 9), (10, 14), (0, 0)]
    got = nt.label_ids_for(offsets, [(10, 14, 'NVDA')], silver=[(0, 6)], ignore=[(7, 9), (10, 14)])
    assert got == [IGN, B, I, IGN, B, IGN]


def test_prf_does_not_charge_predictions_on_undecided_regions():
    examples = [{'text': 'Google AI NVDA', 'spans': [[10, 14, 'NVDA']],
                 'silver': [[0, 6]], 'ignore': [[7, 9]]}]
    got = nt.span_prf(examples, [[(0, 6), (7, 9), (10, 14)]])
    assert (got['tp'], got['fp'], got['fn']) == (1, 0, 0)
    got = nt.span_prf(examples, [[(0, 6), (7, 9)]])
    assert (got['tp'], got['fp'], got['fn']) == (0, 0, 1)
