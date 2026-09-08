# personal_apps/tests/test_gliner_recall_check.py
"""The arithmetic of the GLiNER recall cross-check: whether a found entity
covers a known span, what kind of surface form a span is, and the table."""
from scratchpad.label_export import gliner_recall_check as grc


def test_overlap_is_any_shared_character_not_exact_bounds():
    # GLiNER tends to widen ('Nvidia GPUs') or narrow a span; either counts.
    assert grc.covered((10, 16), [{'start': 10, 'end': 21}])
    assert grc.covered((10, 16), [{'start': 12, 'end': 14}])
    assert not grc.covered((10, 16), [{'start': 16, 'end': 20}])   # touching is not overlap
    assert not grc.covered((10, 16), [])


def test_surface_kinds():
    assert grc.kind_of('$NVDA') == 'cashtag'
    assert grc.kind_of('NVDA') == 'ALLCAPS'
    assert grc.kind_of('BRK.B') == 'ALLCAPS'
    assert grc.kind_of('Nvda') == 'Titlecase'
    assert grc.kind_of('nvda') == 'lowercase'
    assert grc.kind_of('Bank of America') == 'other'


def test_table_counts_found_over_known_by_kind_and_per_post():
    examples = [
        {'text': 'NVDA and Nvda and nvda', 'spans': [[0, 4, 'NVDA'], [9, 13, 'NVDA'], [18, 22, 'NVDA']]},
        {'text': 'Apple rocks', 'spans': [[0, 5, 'AAPL']]},
        {'text': 'nothing here', 'spans': []},
    ]
    entities = [
        [{'start': 0, 'end': 4}, {'start': 9, 'end': 13}],   # found NVDA and Nvda, missed nvda
        [],                                                  # missed Apple
        [{'start': 0, 'end': 7}],                            # a false find on a span-less post
    ]
    table = grc.recall_table(examples, entities)
    assert table['spans'] == 4
    assert table['found'] == 2
    assert table['by_kind'] == {'ALLCAPS': [1, 1], 'Titlecase': [1, 2], 'lowercase': [0, 1]}
    assert table['posts_with_spans'] == 2
    assert table['posts_hit'] == 1
    assert table['entities'] == 3
    assert table['entities_off_span'] == 1
