"""The new-shape wave drawn OFFLINE from the raw week replayed through the
shipped extractor (scripts/measure_extractor_population.py's
accepted-mentions.jsonl), because production has had the new rules for
ninety minutes and a wave needs a week. Same shapes, same subs, one week
older; ids in their own negative block so nothing collides with a stored
mention or an earlier wave."""
from scripts import sample_new_shape_mentions as wave


def _accepted(external_id='t1_a', ticker='NVDA', reason='titlecase_symbol',
              text='Nvda ripping', in_author_text=True):
    return {'external_id': external_id, 'source': 'reddit:wallstreetbets',
            'kind': 'comments', 'created_utc': '2026-09-01T00:00:01',
            'ticker': ticker, 'confidence': 'high', 'reason': reason,
            'in_author_text': in_author_text, 'in_thread_context': False,
            'title': '/u/x on thread', 'author_text': text}


def test_a_replayed_new_shape_mention_becomes_a_candidate():
    [cand] = wave.candidates_from_raw([_accepted()])
    assert cand['symbol'] == 'NVDA' and cand['cause'] == 'titlecase_symbol'
    assert cand['external_id'] == 't1_a' and cand['author_text'] == 'Nvda ripping'
    assert cand['stored_today'] is False and cand['is_comment'] is True


def test_old_shapes_and_low_confidence_are_not_candidates():
    rows = [_accepted(reason='bare_source_high'), _accepted(reason='explicit_cashtag')]
    rows.append(dict(_accepted(external_id='t1_low'), confidence='low'))
    assert wave.candidates_from_raw(rows) == []


def test_a_symbol_seen_only_in_the_parent_title_is_not_the_authors_mention():
    """Title-case symbols in a thread title still count for the extractor
    (like bare tokens always have), but the judge reads the author's text;
    a wave row whose symbol is not in that text would be a label on the
    wrong thing."""
    assert wave.candidates_from_raw([_accepted(in_author_text=False)]) == []


def test_excluded_posts_are_skipped():
    class Excl:
        def holds(self, row):
            return row['external_id'] == 't1_locked'
    rows = [_accepted(external_id='t1_locked'), _accepted(external_id='t1_free')]
    picked = wave.candidates_from_raw(rows, exclusions=Excl())
    assert [c['external_id'] for c in picked] == ['t1_free']


def test_raw_wave_rows_take_their_own_id_block():
    [cand] = wave.candidates_from_raw([_accepted()])
    [row] = wave.raw_export_rows([cand])
    assert row['mention_id'] == -4000001
    assert row['post_id'] is None and row['simhash'] is None
    assert row['stratum'] == 'new:titlecase_symbol'
    assert row['candidate']['stored_today'] is False


def test_proportional_quotas_follow_the_pool():
    pool = ([_accepted('a%d' % i, reason='name_only') for i in range(60)]
            + [_accepted('b%d' % i, reason='alias') for i in range(20)]
            + [_accepted('c%d' % i, reason='lowercase_symbol') for i in range(10)]
            + [_accepted('d%d' % i, reason='titlecase_symbol') for i in range(10)])
    quotas = wave.proportional_quotas(wave.candidates_from_raw(pool))
    assert quotas == {'name_only': 0.6, 'alias': 0.2,
                      'lowercase_symbol': 0.1, 'titlecase_symbol': 0.1}
