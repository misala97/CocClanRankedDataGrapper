"""The side-by-side that decides whether a retrained judge ships.

The trial audit's 746 rows have a reference the encoder never trained on.
The question is not "is the new model good" but "is it better than the one
serving production, on the number that matters" -- removal precision, the
rate at which a verdict that DELETES a mention from the counts is right.
The chain's own `predict` refuses any artifact but the armed one, so this
compares two local checkpoints offline and reports the same statistics.
"""
from scratchpad.label_export import compare_judges as cj


def _v(relevance='relevant', origin='human_chatter', attitude='none',
       move='unknown', confidence='high'):
    return {'relevance': relevance, 'content_origin': origin,
            'attitude': attitude, 'expected_move': move, 'confidence': confidence}


def test_removal_precision_counts_only_what_a_model_chose_to_remove():
    """Its own predicted removals are the denominator -- not the sample,
    and not the reference's removals."""
    reference = {1: _v('irrelevant'), 2: _v('relevant'), 3: _v('relevant')}
    predictions = {1: _v('irrelevant'), 2: _v('irrelevant'), 3: _v('relevant')}
    got = cj.removal(predictions, reference)
    assert (got['successes'], got['total']) == (1, 2)
    assert got['point'] == 0.5


def test_broadcast_removes_a_mention_just_like_irrelevant_does():
    reference = {1: _v(origin='broadcast_or_automated')}
    predictions = {1: _v(origin='broadcast_or_automated')}
    assert cj.removal(predictions, reference)['point'] == 1.0


def test_a_model_that_removes_nothing_has_no_precision_to_report():
    """Not a perfect score: a denominator of zero is a failed criterion."""
    reference = {1: _v('irrelevant')}
    assert cj.removal({1: _v('relevant')}, reference) is None


def test_a_missing_prediction_is_a_disagreement_not_an_excuse():
    reference = {1: _v('relevant'), 2: _v('relevant')}
    assert cj.agreement({1: _v('relevant')}, reference, 'relevance')['successes'] == 1
    assert cj.agreement({1: _v('relevant')}, reference, 'relevance')['total'] == 2


def test_a_polarity_reversal_is_counted_over_directional_gold_only():
    reference = {1: _v(attitude='positive'), 2: _v(attitude='negative'),
                 3: _v(attitude='none')}
    predictions = {1: _v(attitude='negative'), 2: _v(attitude='negative'),
                   3: _v(attitude='positive')}
    got = cj.reversals(predictions, reference)
    assert (got['successes'], got['total']) == (1, 2)


def test_the_table_puts_the_challenger_beside_the_incumbent():
    reference = {1: _v('irrelevant'), 2: _v('relevant')}
    rows = cj.table({'live': {1: _v('irrelevant'), 2: _v('relevant')},
                     'new': {1: _v('irrelevant'), 2: _v('irrelevant')}},
                    reference)
    by_name = {r['metric']: r for r in rows}
    assert by_name['removal_precision']['live']['point'] == 1.0
    assert by_name['removal_precision']['new']['point'] == 0.5
    assert 'relevance' in by_name and 'content_origin' in by_name


def test_the_verdict_reads_the_lower_bound_not_the_point_estimate():
    """A point estimate that moved up on forty rows is noise; the ship
    rule is the Wilson lower bound against the incumbent's."""
    better = {'point': 0.9, 'lower': 0.85, 'upper': 0.94, 'successes': 90, 'total': 100}
    worse = {'point': 0.91, 'lower': 0.70, 'upper': 0.98, 'successes': 21, 'total': 23}
    assert cj.wins(better, worse) is True
    assert cj.wins(worse, better) is False
    assert cj.wins(None, better) is False
