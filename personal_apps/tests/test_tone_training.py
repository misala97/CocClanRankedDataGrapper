"""What the tone heads are allowed to learn from, and what a flip costs.

Two findings drive this. Two thirds of what the direction heads see is a
non-answer: 6,019 of 10,323 relevant rows say `unknown`, and on top of that
every irrelevant row is FORCED to none/unknown by the prompt's own rule, so
those 4,890 rows teach the model nothing except "say none". And a polarity
reversal -- calling up when the truth is down -- is the one error that
actively misleads the board, yet plain cross-entropy charges it exactly like
calling up when the truth is unknown.
"""
from scratchpad.label_export import tone_training as tt


def _row(relevance='relevant', attitude='positive', move='up'):
    return {'y': {'relevance': relevance, 'attitude': attitude,
                  'expected_move': move, 'content_origin': 'human_chatter',
                  'confidence': 'high'}}


def test_only_relevance_and_origin_are_learned_from_every_row():
    assert tt.TONE_HEADS == ('attitude', 'expected_move')
    row = _row(relevance='irrelevant', attitude='none', move='unknown')
    assert tt.is_trainable(row, 'relevance') is True
    assert tt.is_trainable(row, 'content_origin') is True
    assert tt.is_trainable(row, 'confidence') is True


def test_a_forced_label_on_an_irrelevant_row_teaches_the_tone_heads_nothing():
    row = _row(relevance='irrelevant', attitude='none', move='unknown')
    assert tt.is_trainable(row, 'attitude') is False
    assert tt.is_trainable(row, 'expected_move') is False


def test_an_uncertain_row_is_excluded_too():
    row = _row(relevance='uncertain', attitude='none', move='unknown')
    assert tt.is_trainable(row, 'attitude') is False


def test_a_relevant_row_trains_the_tone_heads_even_when_it_has_no_direction():
    """`relevant` + `none`/`unknown` is a real judgement -- the author said
    something about the company without taking a side. Only the FORCED
    labels are noise."""
    row = _row(relevance='relevant', attitude='none', move='unknown')
    assert tt.is_trainable(row, 'attitude') is True
    assert tt.is_trainable(row, 'expected_move') is True


def test_the_mask_over_a_batch_counts_what_is_left():
    rows = [_row(), _row(relevance='irrelevant', attitude='none', move='unknown'),
            _row(relevance='uncertain', attitude='none', move='unknown')]
    mask = tt.trainable_mask(rows, 'attitude')
    assert mask == [True, False, False]
    assert tt.trainable_mask(rows, 'relevance') == [True, True, True]


def test_the_opposite_of_each_directional_class_is_named():
    assert tt.opposite_class('attitude', 'positive') == 'negative'
    assert tt.opposite_class('attitude', 'negative') == 'positive'
    assert tt.opposite_class('expected_move', 'up') == 'down'
    assert tt.opposite_class('expected_move', 'down') == 'up'


def test_a_non_directional_class_has_no_opposite_to_penalise():
    assert tt.opposite_class('attitude', 'mixed') is None
    assert tt.opposite_class('attitude', 'none') is None
    assert tt.opposite_class('expected_move', 'flat') is None
    assert tt.opposite_class('expected_move', 'unknown') is None
    assert tt.opposite_class('relevance', 'relevant') is None


def test_the_penalty_targets_are_indices_into_the_head_s_own_class_list():
    classes = ['positive', 'negative', 'mixed', 'none']
    targets = tt.opposite_index_map('attitude', classes)
    assert targets == {0: 1, 1: 0}          # positive->negative, negative->positive
    assert tt.opposite_index_map('expected_move', ['up', 'down', 'flat', 'unknown']) == {0: 1, 1: 0}
    assert tt.opposite_index_map('confidence', ['high', 'medium', 'low']) == {}
