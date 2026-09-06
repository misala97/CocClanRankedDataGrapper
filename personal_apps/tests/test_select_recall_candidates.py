"""The recall wave's sample: rejected candidates, stratified by cause, capped
per symbol, written in the label harness's export shape with ids that can
never collide with a production mention."""
import collections
import json

from scripts import select_recall_candidates as sel


def _cand(i, symbol, cause, *, stored=False, text='some text', kind='comments'):
    return {'external_id': 't1_%d' % i, 'source': 'reddit:wallstreetbets', 'kind': kind,
            'created_utc': '2026-09-05T10:00:00', 'stored_today': stored,
            'accepted': [], 'symbol': symbol, 'cause': cause, 'evidence': symbol.lower(),
            'title': '/u/x on thread', 'author_text': text, 'truncated': False}


def test_quotas_per_cause_and_a_cap_per_symbol():
    pool = ([_cand(i, 'GPRO', 'name_only') for i in range(100)]
            + [_cand(200 + i, 'NKE', 'name_only') for i in range(100)]
            + [_cand(400 + i, 'NVDA', 'lowercase_symbol') for i in range(50)]
            + [_cand(500 + i, 'AI', 'stopword') for i in range(50)])
    picked = sel.pick(pool, n=100, quotas={'name_only': 0.6, 'lowercase_symbol': 0.2,
                                            'stopword': 0.2}, cap_share=0.3, seed=1)
    causes = {}
    symbols = {}
    for row in picked:
        causes[row['cause']] = causes.get(row['cause'], 0) + 1
        symbols[row['symbol']] = symbols.get(row['symbol'], 0) + 1
    assert len(picked) == 100
    assert causes == {'name_only': 60, 'lowercase_symbol': 20, 'stopword': 20}
    assert symbols['GPRO'] == 30 and symbols['NKE'] == 30   # cap 30% of 100 each


def test_a_short_stratum_gives_its_slack_to_the_others():
    pool = ([_cand(i, 'GPRO', 'name_only') for i in range(100)]
            + [_cand(300 + i, 'ZZZZ', 'cashtag_not_in_universe') for i in range(3)])
    picked = sel.pick(pool, n=50, quotas={'name_only': 0.5, 'cashtag_not_in_universe': 0.5},
                      cap_share=1.0, seed=1)
    assert len(picked) == 50
    assert sum(1 for r in picked if r['cause'] == 'cashtag_not_in_universe') == 3


def test_invisible_posts_come_before_stored_ones():
    pool = ([_cand(i, 'GPRO', 'name_only', stored=True) for i in range(20)]
            + [_cand(100 + i, 'GPRO', 'name_only', stored=False) for i in range(20)])
    picked = sel.pick(pool, n=20, quotas={'name_only': 1.0}, cap_share=1.0, seed=1)
    assert all(not r['stored_today'] for r in picked)


def test_the_same_seed_picks_the_same_rows():
    pool = [_cand(i, 'GPRO', 'name_only') for i in range(100)]
    a = sel.pick(pool, n=10, quotas={'name_only': 1.0}, cap_share=1.0, seed=7)
    b = sel.pick(pool, n=10, quotas={'name_only': 1.0}, cap_share=1.0, seed=7)
    assert [r['external_id'] for r in a] == [r['external_id'] for r in b]


def test_rows_are_written_in_the_harness_shape_with_synthetic_ids(tmp_path):
    picked = [_cand(1, 'GPRO', 'name_only', text='my GoPro broke'),
              _cand(2, 'NVDA', 'lowercase_symbol', kind='posts')]
    out = tmp_path / 'candidates.jsonl'
    sel.write_export(picked, out)
    with open(out, encoding='utf-8') as handle:
        rows = [json.loads(line) for line in handle]
    assert [r['mention_id'] for r in rows] == [-1, -2]      # never a production id
    assert rows[0]['ticker'] == 'GPRO'
    assert rows[0]['author_text'] == 'my GoPro broke'
    assert rows[0]['stratum'] == 'cand:name_only'
    assert rows[0]['is_comment'] is True and rows[1]['is_comment'] is False
    assert rows[0]['channel'] == 'wallstreetbets'
    assert rows[0]['sentiment_judged_at'] is None
    assert rows[0]['candidate'] == {'cause': 'name_only', 'evidence': 'gpro',
                                    'stored_today': False, 'external_id': 't1_1'}


def _c(i, symbol, cause, evidence):
    row = _cand(i, symbol, cause)
    row['evidence'] = evidence
    return row


def test_a_top_up_wave_skips_what_an_earlier_wave_already_drew():
    pool = [_c(1, 'GPRO', 'name_only', 'gopro'), _c(2, 'NKE', 'name_only', 'nike')]
    already = {('t1_1', 'GPRO', 'name_only')}
    fresh = sel.without(pool, already)
    assert [r['external_id'] for r in fresh] == ['t1_2']


def test_the_cap_can_count_evidence_tokens_rather_than_symbols():
    """`trump` produced 3,170 candidates across two listings, so capping
    per symbol would still let one word take a fifth of the wave."""
    pool = ([_c(i, 'DJT', 'name_only', 'trump') for i in range(50)]
            + [_c(100 + i, 'DJTWW', 'name_only', 'trump') for i in range(50)]
            + [_c(200 + i, 'GPRO', 'name_only', 'gopro') for i in range(50)])
    picked = sel.pick(pool, n=40, quotas={'name_only': 1.0}, cap_share=0.25, seed=1,
                      cap_key='evidence')
    tokens = collections.Counter(r['evidence'] for r in picked)
    assert tokens['trump'] == 10          # 25% of 40, across BOTH its symbols
    assert tokens['gopro'] == 10
    # Two tokens, ten each: the wave comes back SHORT rather than letting a
    # cap slip, which is the honest outcome when a pool is that narrow.
    assert len(picked) == 20


def test_capping_by_symbol_stays_the_default():
    pool = ([_c(i, 'DJT', 'name_only', 'trump') for i in range(50)]
            + [_c(100 + i, 'DJTWW', 'name_only', 'trump') for i in range(50)])
    picked = sel.pick(pool, n=20, quotas={'name_only': 1.0}, cap_share=0.25, seed=1)
    assert collections.Counter(r['symbol'] for r in picked) == {'DJT': 5, 'DJTWW': 5}


def test_a_wave_can_be_restricted_to_the_causes_worth_measuring():
    """A top-up exists to test what the loose pass newly finds; without a
    restriction the standing quotas spend a third of it on classes an
    earlier wave already measured."""
    quotas = sel.quotas_for(['name_only', 'metonym'])
    assert set(quotas) == {'name_only', 'metonym'}
    assert abs(sum(quotas.values()) - 1.0) < 1e-9
    # The shares keep their relative weight from the standing plan.
    assert quotas['name_only'] > quotas['metonym']


def test_restricting_to_an_unknown_cause_is_refused():
    try:
        sel.quotas_for(['name_only', 'not_a_cause'])
    except ValueError as exc:
        assert 'not_a_cause' in str(exc)
    else:
        raise AssertionError('an unknown cause must not silently select nothing')


def test_a_second_wave_gets_its_own_id_block():
    """Wave ids are negative so they cannot collide with a production
    mention -- but each wave counted from -1, so wave two's ids collided
    with wave one's and the harness skipped all 1,500 rows as already
    labelled."""
    picked = [_cand(1, 'GPRO', 'name_only'), _cand(2, 'NKE', 'name_only')]
    first = sel.export_rows(picked, wave=1)
    second = sel.export_rows(picked, wave=2)
    assert [r['mention_id'] for r in first] == [-1, -2]
    assert [r['mention_id'] for r in second] == [-1000001, -1000002]
    assert not ({r['mention_id'] for r in first} & {r['mention_id'] for r in second})


def test_a_wave_larger_than_its_block_is_refused():
    picked = [_cand(i, 'GPRO', 'name_only') for i in range(3)]
    try:
        sel.export_rows(picked, wave=1, block=2)
    except ValueError as exc:
        assert 'block' in str(exc)
    else:
        raise AssertionError('ids must never run into the next wave\'s block')
