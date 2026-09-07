"""The recall wave's own held-out set.

The encoder has never seen a name-only or lowercase-symbol row, so the
existing frozen sets say nothing about how it handles them. A slice of the
wave is locked the same way: by post, once, never regenerated.
"""
import json

from scratchpad.label_export import freeze_recall as freeze


def _row(mention_id, external_id, cause='name_only'):
    return {'mention_id': mention_id, 'external_id': external_id,
            'stratum': 'cand:%s' % cause,
            'candidate': {'cause': cause, 'evidence': 'x',
                          'stored_today': False, 'external_id': external_id}}


def test_a_posts_rows_never_straddle_the_boundary():
    rows = [_row(-1, 't1_a'), _row(-2, 't1_a'), _row(-3, 't1_b'), _row(-4, 't1_c')]
    picked = freeze.choose(rows, target=2, seed=1)
    posts = {r['external_id'] for r in rows if r['mention_id'] in picked}
    for row in rows:
        if row['external_id'] in posts:
            assert row['mention_id'] in picked


def test_every_cause_is_represented_in_proportion():
    rows = ([_row(-i, 't1_n%d' % i, 'name_only') for i in range(80)]
            + [_row(-100 - i, 't1_m%d' % i, 'metonym') for i in range(20)])
    picked = set(freeze.choose(rows, target=50, seed=1))
    by_cause = {}
    for row in rows:
        if row['mention_id'] in picked:
            cause = row['candidate']['cause']
            by_cause[cause] = by_cause.get(cause, 0) + 1
    assert by_cause['metonym'] >= 5           # a fifth of the pool, not zero
    assert by_cause['name_only'] >= 30


def test_the_same_seed_locks_the_same_rows():
    rows = [_row(-i, 't1_%d' % i) for i in range(40)]
    assert freeze.choose(rows, target=10, seed=3) == freeze.choose(rows, target=10, seed=3)


def test_an_existing_locked_set_is_never_overwritten(tmp_path):
    path = tmp_path / 'test-recall.json'
    path.write_text('[-1]', encoding='utf-8')
    try:
        freeze.write(path, [-2, -3])
    except SystemExit as exc:
        assert 'never regenerated' in str(exc)
    else:
        raise AssertionError('a locked set that can be regenerated is not locked')
    assert json.loads(path.read_text(encoding='utf-8')) == [-1]
