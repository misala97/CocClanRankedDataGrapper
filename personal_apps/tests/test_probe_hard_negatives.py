"""A held-out probe for the defect the hard negatives were built to fix.

The 746-row trial audit predates the extractor change and holds no
out-of-distribution finder pair, so it cannot answer whether the judge
still rubber-stamps `corn` in "buttcorn". The training wave cannot answer
it either: all 1,553 of its rows went into training. This draws FRESH
constructed pairs from the raw week -- same rules, different posts, every
post any wave or locked set already used excluded -- so both models can be
scored on pairs neither has seen.

Every pair here is irrelevant by construction, so a model's score is
simply how often it wrongly says `relevant`: the false-accept rate that
was 1.00 for `corn`, 0.99 for `Abt`, 0.97 for `nat`.
"""
from scratchpad.label_export import probe_hard_negatives as probe


class _Excl:
    def __init__(self, ids):
        self.external_ids = set(ids)
        self.texts = set()

    def holds(self, row):
        return row.get('external_id') in self.external_ids


def test_a_post_an_earlier_wave_used_is_not_in_the_probe():
    """Otherwise the probe measures training data and says the fix worked."""
    excl = probe.widen(_Excl({'t1_locked'}), used_posts={'t1_trained'})
    assert excl.holds({'external_id': 't1_locked', 'author_text': 'x'})
    assert excl.holds({'external_id': 't1_trained', 'author_text': 'x'})
    assert not excl.holds({'external_id': 't1_fresh', 'author_text': 'x'})


def test_the_posts_every_wave_used_are_read_from_its_export():
    rows = [{'external_id': 't1_a'}, {'external_id': 't1_b'}, {'external_id': 't1_a'}]
    assert probe.posts_of(rows) == {'t1_a', 't1_b'}


def test_a_false_accept_is_a_constructed_pair_called_relevant():
    pairs = [{'symbol': 'CORN', 'external_id': 'p1', 'kind': 'subword'},
             {'symbol': 'NAT', 'external_id': 'p2', 'kind': 'ordinary'},
             {'symbol': 'DOW', 'external_id': 'p3', 'kind': 'index'}]
    verdicts = {'p1': {'relevance': 'relevant'}, 'p2': {'relevance': 'irrelevant'},
                'p3': {'relevance': 'uncertain'}}
    got = probe.score(pairs, verdicts)
    assert got['false_accepts'] == 1
    assert got['total'] == 3
    assert got['rate']['successes'] == 1


def test_uncertain_is_not_a_false_accept():
    """`uncertain` does not put a mention on the board; only `relevant`
    does, and only `relevant` is the defect being measured."""
    pairs = [{'symbol': 'X', 'external_id': 'p1', 'kind': 'subword'}]
    assert probe.score(pairs, {'p1': {'relevance': 'uncertain'}})['false_accepts'] == 0


def test_a_pair_the_model_never_answered_is_not_counted_either_way():
    pairs = [{'symbol': 'X', 'external_id': 'p1', 'kind': 'subword'},
             {'symbol': 'Y', 'external_id': 'p2', 'kind': 'subword'}]
    got = probe.score(pairs, {'p1': {'relevance': 'relevant'}})
    assert got['total'] == 1 and got['false_accepts'] == 1


def test_the_breakdown_names_the_kind_each_false_accept_came_from():
    pairs = [{'symbol': 'CORN', 'external_id': 'p1', 'kind': 'subword'},
             {'symbol': 'NAT', 'external_id': 'p2', 'kind': 'ordinary'}]
    verdicts = {'p1': {'relevance': 'relevant'}, 'p2': {'relevance': 'relevant'}}
    got = probe.score(pairs, verdicts)
    assert got['by_kind'] == {'subword': 1, 'ordinary': 1}
