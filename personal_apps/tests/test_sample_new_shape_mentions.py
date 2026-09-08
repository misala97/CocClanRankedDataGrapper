"""The labelling wave on the NEW mention population (2026-09-08 15:35 UTC
onward): mentions the extractor now counts as a Title-case symbol, a
lowercase symbol, a name alone or an alias. The reason is not a column, so
it is re-derived by running the production extractor over the stored post;
the wave is stratified by that reason and written in the export shape with
the mention's REAL id, so a label lands on the row it was made for."""
import types

from scripts import sample_new_shape_mentions as wave


def _lookup(**symbols):
    return {sym: {'name': name, 'distinctive': set(distinctive)}
            for sym, (name, distinctive) in symbols.items()}


def _post(body, title='/u/x on Daily Discussion Thread', source='reddit:wallstreetbets',
          author='/u/x', post_id=7, external_id='t1_abc'):
    return types.SimpleNamespace(id=post_id, source=source, external_id=external_id,
                                 channel='wallstreetbets', author=author,
                                 created_utc='2026-09-08T16:00:00', title=title,
                                 body=body, simhash=12345, first_seen='2026-09-08T16:01:00')


def _mention(mention_id, ticker, post_id=7):
    return types.SimpleNamespace(id=mention_id, ticker=ticker, post_id=post_id,
                                 confidence='high', sentiment_judged_at=None)


def test_a_stored_mentions_reason_is_re_derived_from_its_post():
    lookup = _lookup(NVDA=('NVIDIA Corporation', ['nvidia']),
                     AVGO=('Broadcom Inc.', ['broadcom']))
    reasons = wave.reasons_for(_post('Nvda ripping, avgo too'), lookup)
    assert reasons == {'NVDA': 'titlecase_symbol', 'AVGO': 'lowercase_symbol'}
    # the company's own name beside the symbol corroborates it: an OLD shape
    assert wave.reasons_for(_post('Nvda and nvidia both ripping'), lookup) == {
        'NVDA': 'bare_named'}


def test_a_mention_whose_reason_is_an_old_shape_is_not_in_the_wave():
    lookup = _lookup(NVDA=('NVIDIA Corporation', ['nvidia']))
    candidates = wave.candidates_for(_post('NVDA calls'), [_mention(1, 'NVDA')], lookup)
    assert candidates == []


def test_a_new_shape_mention_becomes_a_candidate_with_its_real_id():
    lookup = _lookup(NVDA=('NVIDIA Corporation', ['nvidia']))
    [cand] = wave.candidates_for(_post('Nvda calls'), [_mention(4242, 'NVDA')], lookup)
    assert cand['mention_id'] == 4242
    assert cand['cause'] == 'titlecase_symbol'
    assert cand['symbol'] == 'NVDA'
    assert cand['author_text'] == 'Nvda calls'
    assert cand['post_id'] == 7 and cand['simhash'] == 12345


def test_the_export_row_carries_the_mention_id_and_the_new_stratum():
    lookup = _lookup(NVDA=('NVIDIA Corporation', ['nvidia']))
    [cand] = wave.candidates_for(_post('Nvda calls'), [_mention(4242, 'NVDA')], lookup)
    row = wave.export_row(cand)
    assert row['mention_id'] == 4242
    assert row['ticker'] == 'NVDA'
    assert row['stratum'] == 'new:titlecase_symbol'
    assert row['post_id'] == 7 and row['simhash'] == 12345
    assert row['author_text'] == 'Nvda calls'
    assert row['is_comment'] is True
    assert row['sentiment_judged_at'] is None
    assert row['candidate'] == {'cause': 'titlecase_symbol', 'evidence': None,
                                'stored_today': True, 'external_id': 't1_abc'}


def test_the_wave_is_stratified_by_reason_with_a_cap_per_symbol():
    def cand(i, symbol, cause):
        return {'mention_id': i, 'symbol': symbol, 'cause': cause,
                'external_id': 't1_%d' % i, 'stored_today': True}
    pool = ([cand(i, 'NVDA', 'titlecase_symbol') for i in range(100)]
            + [cand(200 + i, 'LULU', 'lowercase_symbol') for i in range(100)]
            + [cand(400 + i, 'MRNA', 'name_only') for i in range(100)]
            + [cand(600 + i, 'TSLA', 'alias') for i in range(100)])
    picked = wave.pick(pool, n=40, seed=1, cap_share=0.3)
    causes = {}
    for row in picked:
        causes[row['cause']] = causes.get(row['cause'], 0) + 1
    assert len(picked) == 40
    assert causes == {'titlecase_symbol': 10, 'lowercase_symbol': 10,
                      'name_only': 10, 'alias': 10}
