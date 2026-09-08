"""Freezing the fourth locked set: the new mention shapes.

The three locked sets predate the 2026-09-08 extractor change. natural and
hard come from the production export, which holds only what the OLD rules
accepted; recall comes from the loose pass's candidates. None of them
contains a Title-case symbol (`Nvda`) or an alias (`google`), so nothing
measures those shapes out of sample. This freezes a slice of the new-shape
wave before any of it is trained on.

Whole posts, like freeze_test_sets.py: a post's several ticker rows never
straddle the train/test boundary, so the set overshoots `target` by at
most the last post it took.
"""
from scratchpad.label_export import freeze_newshape as fz


def _row(mention_id, stratum='new:titlecase_symbol', post='t1_a'):
    return {'mention_id': mention_id, 'stratum': stratum, 'post_id': post}


def _by_stratum(rows):
    out = {}
    for row in rows:
        out[row['stratum']] = out.get(row['stratum'], 0) + 1
    return out


def test_the_slice_keeps_each_shape_in_proportion():
    rows = ([_row(i, 'new:name_only', 'p%d' % i) for i in range(500)]
            + [_row(1000 + i, 'new:lowercase_symbol', 'q%d' % i) for i in range(300)]
            + [_row(2000 + i, 'new:alias', 'r%d' % i) for i in range(200)])
    picked = fz.pick(rows, target=100, seed=1)
    assert len(picked) == 100                    # one row per post here, no overshoot
    assert _by_stratum(picked) == {'new:name_only': 50, 'new:lowercase_symbol': 30,
                                    'new:alias': 20}


def test_a_post_never_straddles_the_boundary():
    """Two rows from one post are one group: if the post is in the locked
    set, both its rows are, or the trainer would train on a locked post."""
    rows = [_row(1, post='shared'), _row(2, post='shared')] + [
        _row(10 + i, post='p%d' % i) for i in range(50)]
    picked = fz.pick(rows, target=6, seed=1)
    ids = {r['mention_id'] for r in picked}
    assert (1 in ids) == (2 in ids)


def test_the_same_seed_picks_the_same_set():
    rows = [_row(i, post='p%d' % i) for i in range(100)]
    a = fz.pick(rows, target=20, seed=7)
    b = fz.pick(rows, target=20, seed=7)
    assert [r['mention_id'] for r in a] == [r['mention_id'] for r in b]


def test_a_different_seed_picks_a_different_set():
    rows = [_row(i, post='p%d' % i) for i in range(100)]
    a = {r['mention_id'] for r in fz.pick(rows, target=20, seed=7)}
    b = {r['mention_id'] for r in fz.pick(rows, target=20, seed=8)}
    assert a != b


def test_a_shape_short_of_its_quota_gives_all_it_has_and_the_rest_make_up_the_total():
    """Explicit quotas, because a proportional quota can never exceed the
    rows a shape has. The shortfall is real when a wave underfills one
    shape and the set still has to reach its size."""
    rows = ([_row(i, 'new:name_only', 'p%d' % i) for i in range(90)]
            + [_row(500 + i, 'new:alias', 'r%d' % i) for i in range(2)])
    picked = fz.pick(rows, target=20, seed=1,
                     quotas={'new:name_only': 0.5, 'new:alias': 0.5})
    assert _by_stratum(picked)['new:alias'] == 2
    assert len(picked) == 20


def test_the_set_overshoots_only_by_the_last_post_it_took():
    """Whole posts of five rows each against a target of 12: 15, not 12."""
    rows = [_row(i * 10 + j, post='p%d' % i) for i in range(10) for j in range(5)]
    picked = fz.pick(rows, target=12, seed=1)
    assert len(picked) == 15
    assert len({r['post_id'] for r in picked}) == 3
