# personal_apps/tests/test_ner_probe.py
"""Stage 2 of the NER probe, the parts that are arithmetic.

The two model calls are glue and untested. Everything between them --
which pairs get judged, what counts as a hit, how a sample becomes a
weekly number -- is where a wrong answer would look exactly like a right
one, so it is pinned here.
"""
from scratchpad.label_export import ner_probe as np_


def _finding(post, span, symbol, tier, label='company', score=0.9):
    return {'external_id': post, 'span': span, 'label': label, 'score': score,
            'symbol': symbol, 'tier': tier}


def _verdict(relevance='relevant', origin='human_chatter', p=0.9):
    return {'relevance': relevance, 'relevance_p': p, 'content_origin': origin,
            'attitude': 'none', 'expected_move': 'unknown', 'confidence': 'medium'}


def test_pairs_are_one_per_post_and_symbol_in_first_seen_order():
    findings = [
        _finding('p1', 'Nvidia', 'NVDA', 'tokens'),
        _finding('p1', '$NVDA', 'NVDA', 'symbol'),          # same pair, once
        _finding('p1', 'Intel', 'INTC', 'name'),
        _finding('p2', 'S&P', None, 'unresolved'),          # no symbol, no pair
        _finding('p2', 'lyft', 'LYFT', 'symbol'),
    ]
    assert np_.pairs_from(findings) == [('p1', 'NVDA'), ('p1', 'INTC'), ('p2', 'LYFT')]


def test_hit_rules_match_the_board():
    assert np_.is_kept(_verdict('relevant'))
    assert np_.is_kept(_verdict('uncertain'))
    assert not np_.is_kept(_verdict('irrelevant'))
    assert not np_.is_kept(_verdict('relevant', origin='broadcast_or_automated'))
    assert np_.is_relevant(_verdict('relevant'))
    assert not np_.is_relevant(_verdict('uncertain'))
    assert not np_.is_relevant(_verdict('relevant', origin='broadcast_or_automated'))


def test_funnel_counts_posts_spans_pairs_and_hits():
    findings = [
        _finding('p1', 'Nvidia', 'NVDA', 'tokens'),
        _finding('p1', 'Intel', 'INTC', 'name'),
        _finding('p2', 'S&P', None, 'unresolved'),
        _finding('p2', 'fed', None, 'unresolved'),
        _finding('p3', 'lyft', 'LYFT', 'symbol'),
        _finding('p4', 'S&P', None, 'unresolved'),
    ]
    verdicts = {
        ('p1', 'NVDA'): _verdict('relevant'),
        ('p1', 'INTC'): _verdict('irrelevant'),
        ('p3', 'LYFT'): _verdict('uncertain'),
    }
    f = np_.funnel(findings, verdicts, n_posts=10)
    assert f['posts_sampled'] == 10
    assert f['posts_with_span'] == 4
    assert f['spans'] == 6
    assert f['spans_by_tier'] == {'tokens': 1, 'name': 1, 'symbol': 1, 'unresolved': 3}
    assert f['unresolved_top'][0] == ['S&P', 2]
    assert f['pairs'] == 3
    assert f['relevant_pairs'] == 1
    assert f['kept_pairs'] == 2
    assert f['relevant_posts'] == 1
    assert f['kept_posts'] == 2
    # Per tier: tokens 1/1 relevant, name 0/1, symbol 0/1 (uncertain is kept, not relevant).
    assert f['relevant_rate_by_tier'] == {'tokens': [1, 1], 'name': [0, 1], 'symbol': [0, 1]}


def test_extrapolation_scales_the_relevant_post_rate_to_the_week():
    # 30 of 3000 sampled posts relevant, over 132,164 zero-candidate posts a week.
    assert np_.extrapolate(30, 3000, weekly_posts=132_164) == 1321.64
    assert np_.extrapolate(0, 3000, weekly_posts=132_164) == 0.0


def test_funnel_survives_an_empty_run():
    f = np_.funnel([], {}, n_posts=3)
    assert f['posts_with_span'] == 0 and f['pairs'] == 0 and f['relevant_posts'] == 0
    assert f['extrapolated_relevant_posts_per_week'] == 0.0
