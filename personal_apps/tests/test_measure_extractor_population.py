"""The population pass over a raw capture: what the production extractor
accepts, what a loose pass finds that it rejected, and why."""
import datetime as dt
import json

from features.radar.universe import annotate_distinctive
from scripts import measure_extractor_population as pop

LOOKUP = annotate_distinctive({
    'NVDA': {'name': 'NVIDIA Corporation - Common Stock', 'exchange': 'NASDAQ'},
    'AI': {'name': 'C3.ai, Inc. Class A Common Stock', 'exchange': 'NYSE'},
    'GME': {'name': 'GameStop Corp', 'exchange': 'NYSE'},
    'F': {'name': 'Ford Motor Company', 'exchange': 'NYSE'},
    'APP': {'name': 'AppLovin Corporation', 'exchange': 'NASDAQ'},
    'GPRO': {'name': 'GoPro, Inc. - Class A Common Stock', 'exchange': 'NASDAQ'},
})


def _line(external_id, body, *, title='thread title', author='/u/someone',
          kind='comments', sub='wallstreetbets'):
    return {'source': 'reddit:%s' % sub, 'external_id': external_id, 'channel': sub,
            'author': author, 'created_utc': '2026-09-05T10:00:00',
            'title': ('/u/someone on %s' % title) if kind == 'comments' else title,
            'body': body, 'score': 1, 'num_comments': 0, 'url': 'https://example.invalid/',
            'native_tickers': [], 'native_sentiment': None, 'kind': kind}


def _raw_dir(tmp_path, lines):
    day = tmp_path / '2026-09-05'
    day.mkdir()
    with open(day / 'wallstreetbets.jsonl', 'w', encoding='utf-8') as handle:
        for line in lines:
            handle.write(json.dumps(line) + '\n')
    return tmp_path


NOT_COMMON = lambda word: False   # noqa: E731


def test_a_stored_post_and_an_invisible_post_are_told_apart():
    stored = pop.classify(_line('t1_a', 'loading up on $GME'), LOOKUP, NOT_COMMON)
    invisible = pop.classify(_line('t1_b', 'nvda is cooking'), LOOKUP, NOT_COMMON)
    assert stored['stored_today'] is True
    assert [m['ticker'] for m in stored['accepted']] == ['GME']
    assert invisible['stored_today'] is False
    assert invisible['accepted'] == []


def test_every_rejection_cause_is_named():
    row = pop.classify(_line(
        't1_c', 'nvda is cooking, AI names ripping, Nvidia and GoPro too, $ZZZZ and $F'),
        LOOKUP, NOT_COMMON)
    causes = {(c['symbol'], c['cause']) for c in row['rejected']}
    assert ('NVDA', 'lowercase_symbol') in causes
    assert ('AI', 'stopword') in causes
    assert ('GPRO', 'name_only') in causes            # 'GoPro' written, symbol absent
    assert ('ZZZZ', 'cashtag_not_in_universe') in causes
    assert ('F', 'single_letter_cashtag') in causes   # reddit does not allow $F
    # Nvidia is named AND its symbol appears (lowercase): the lowercase
    # candidate carries the name evidence, no second name_only row.
    assert ('NVDA', 'name_only') not in causes


def test_a_lowercase_word_that_is_common_is_not_a_candidate():
    common = lambda word: word in {'app'}   # noqa: E731
    row = pop.classify(_line('t1_d', 'the app is broken, gme fine'), LOOKUP, common)
    causes = {(c['symbol'], c['cause']) for c in row['rejected']}
    assert ('GME', 'lowercase_symbol') in causes
    assert ('APP', 'lowercase_symbol') not in causes


def test_a_name_written_lowercase_does_not_count_as_naming():
    row = pop.classify(_line('t1_e', 'my gopro broke'), LOOKUP, NOT_COMMON)
    assert row['rejected'] == []


def test_an_accepted_ticker_is_never_also_a_rejected_candidate():
    row = pop.classify(_line('t1_f', 'GME and gme and GameStop'), LOOKUP, NOT_COMMON)
    assert [m['ticker'] for m in row['accepted']] == ['GME']
    assert row['rejected'] == []


def test_a_post_dropped_whole_by_a_hygiene_gate_is_counted_as_such():
    row = pop.classify(_line('t1_g', 'GME weekly thread', author='/u/AutoModerator'),
                       LOOKUP, NOT_COMMON)
    assert row['stored_today'] is False
    assert row['gate'] == 'automated_author'
    assert row['rejected'] == []


def test_stopword_candidates_come_from_author_text_only():
    """A stopword in the parent title is context; the invisible-set
    question is what the AUTHOR wrote."""
    row = pop.classify(_line('t1_h', 'no tickers here', title='AI thread'), LOOKUP, NOT_COMMON)
    assert row['rejected'] == []


def test_the_report_counts_the_population(tmp_path):
    raw = _raw_dir(tmp_path, [
        _line('t1_a', 'loading up on $GME'),
        _line('t1_b', 'nvda is cooking'),
        _line('t3_c', 'AI names ripping', kind='posts'),
        _line('t1_g', 'GME weekly', author='/u/AutoModerator'),
    ])
    out = tmp_path / 'out'
    summary = pop.run(raw, LOOKUP, out, common_words=set())
    assert summary['posts'] == 4
    assert summary['stored_today'] == 1
    assert summary['invisible'] == 2
    assert summary['gated'] == 1
    assert summary['by_reason'] == {'explicit_cashtag': 1}
    assert summary['rejected_by_cause'] == {'lowercase_symbol': 1, 'stopword': 1}
    with open(out / 'rejected-candidates.jsonl', encoding='utf-8') as handle:
        rows = [json.loads(line) for line in handle]
    assert {r['external_id'] for r in rows} == {'t1_b', 't3_c'}
    assert all('author_text' in r and 'stored_today' in r for r in rows)


def test_common_words_are_the_tokens_the_corpus_writes_lowercase(tmp_path):
    raw = _raw_dir(tmp_path, [_line('t1_%d' % i, 'the app broke') for i in range(10)]
                   + [_line('t1_x', 'gme fine')]
                   + [_line('t1_y%d' % i, 'GME ripping') for i in range(5)])
    common = pop.common_words(raw, min_posts=1)
    assert 'app' in common and 'the' in common
    assert 'gme' not in common          # 1 of 6 posts lowercase: a symbol


def test_a_token_seen_too_rarely_is_not_called_ordinary(tmp_path):
    raw = _raw_dir(tmp_path, [_line('t1_x', 'gme fine')])
    assert pop.common_words(raw, min_posts=2) == set()


def test_labelled_rows_join_the_capture_by_external_id():
    labels = [{'mention_id': 1, 'ticker': 'GME', 'relevance': 'relevant'},
              {'mention_id': 2, 'ticker': 'AI', 'relevance': 'irrelevant'},
              {'mention_id': 3, 'ticker': 'F', 'relevance': 'relevant'}]
    export = [{'mention_id': 1, 'external_id': 't1_a'},
              {'mention_id': 2, 'external_id': 't3_c'},
              {'mention_id': 3, 'external_id': 't1_not_captured'}]
    joined, missing = pop.join_labels({'t1_a', 't3_c'}, labels, export)
    assert [(j['mention_id'], j['external_id']) for j in joined] == [(1, 't1_a'), (2, 't3_c')]
    assert missing == 1


def test_a_long_ordinary_word_written_capitalised_is_not_a_company_name():
    """`People` at a sentence start named PPLI 93 times in one day. The
    ordinary-word set has to cover name-length words, not just symbols."""
    lookup = annotate_distinctive({
        'PPLI': {'name': 'People Inc', 'exchange': 'NASDAQ'},
        'NVDA': {'name': 'NVIDIA Corporation - Common Stock', 'exchange': 'NASDAQ'},
    })
    common = lambda word: word in {'people'}   # noqa: E731
    row = pop.classify(_line('t1_p', 'People love Nvidia'), lookup, common)
    assert [(c['symbol'], c['cause']) for c in row['rejected']] == [('NVDA', 'name_only')]


def test_common_words_cover_name_length_words(tmp_path):
    raw = _raw_dir(tmp_path, [_line('t1_%d' % i, 'people love money') for i in range(10)]
                   + [_line('t1_c%d' % i, 'People love Money') for i in range(2)])
    common = pop.common_words(raw, min_posts=1)
    assert 'people' in common and 'money' in common
