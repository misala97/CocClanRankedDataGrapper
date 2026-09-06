"""The recall wave's sample: rejected candidates, stratified by cause, capped
per symbol, written in the label harness's export shape with ids that can
never collide with a production mention."""
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
