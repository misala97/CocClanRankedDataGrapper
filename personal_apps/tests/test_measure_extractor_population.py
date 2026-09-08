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


# Since 2026-09-08 production itself reads the corpus word lists, so the
# loose pass has nothing to reject for a name alone, a lowercase symbol, an
# alias or a metonym: those are ACCEPTED, with a reason. These tests pin the
# division of labour as it is now. `_align` makes production's lists agree
# with the small corpus a test describes, so a regenerated data file cannot
# move a rule test.
from features.radar import extraction as _ext   # noqa: E402


def _align(monkeypatch, ordinary=(), shapes=('nvidia', 'gopro', 'moderna', 'apple')):
    monkeypatch.setattr(_ext, 'ORDINARY_WORDS', frozenset(ordinary))
    monkeypatch.setattr(_ext, 'NAME_SHAPES', frozenset(shapes))
    _ext._NAME_INDEX_CACHE[:] = []


def _accepted(row):
    return [(m['ticker'], m['reason']) for m in row['accepted']]


def test_a_stored_post_and_an_invisible_post_are_told_apart(monkeypatch):
    _align(monkeypatch)
    stored = pop.classify(_line('t1_a', 'loading up on $GME'), LOOKUP, NOT_COMMON)
    lowercase = pop.classify(_line('t1_b', 'nvda is cooking'), LOOKUP, NOT_COMMON)
    invisible = pop.classify(_line('t1_c', 'nothing about anything here'), LOOKUP, NOT_COMMON)
    assert stored['stored_today'] is True
    assert [m['ticker'] for m in stored['accepted']] == ['GME']
    # A lowercase symbol is stored since 2026-09-08 (high on a finance sub).
    assert lowercase['stored_today'] is True
    assert _accepted(lowercase) == [('NVDA', 'lowercase_symbol')]
    assert invisible['stored_today'] is False
    assert invisible['accepted'] == [] and invisible['rejected'] == []


def test_every_rejection_cause_is_named(monkeypatch):
    _align(monkeypatch)
    row = pop.classify(_line(
        't1_c', 'nvda is cooking, AI names ripping, Nvidia and GoPro too, $ZZZZ and $F'),
        LOOKUP, NOT_COMMON)
    causes = {(c['symbol'], c['cause']) for c in row['rejected']}
    assert ('AI', 'stopword') in causes
    assert ('ZZZZ', 'cashtag_not_in_universe') in causes
    assert ('F', 'single_letter_cashtag') in causes   # reddit does not allow $F
    # What production now counts is not a rejection: `nvda` corroborated by
    # `Nvidia` is bare_named, `GoPro` alone is name_only.
    accepted = dict(_accepted(row))
    assert accepted['NVDA'] == 'bare_named'
    assert accepted['GPRO'] == 'name_only'
    assert ('NVDA', 'lowercase_symbol') not in causes and ('GPRO', 'name_only') not in causes


def test_a_lowercase_word_that_is_common_is_not_a_candidate(monkeypatch):
    _align(monkeypatch, ordinary={'app'})
    common = lambda word: word in {'app'}   # noqa: E731
    row = pop.classify(_line('t1_d', 'the app is broken, gme fine'), LOOKUP, common)
    assert _accepted(row) == [('GME', 'lowercase_symbol')]
    assert row['rejected'] == []                      # `app` is a word, nowhere


def test_a_lowercase_name_nobody_writes_as_a_word_is_a_candidate(monkeypatch):
    _align(monkeypatch)
    """Reversed on purpose: requiring the capital cost `my gopro broke` and
    `do not buy moderna today`, and the capital was never the evidence --
    being a word rather than a name is, and the corpus's casing says which."""
    row = pop.classify(_line('t1_e', 'my gopro broke'), LOOKUP, NOT_COMMON)
    assert row['rejected'] == []
    assert _accepted(row) == [('GPRO', 'name_only')]


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


def test_the_report_counts_the_population(tmp_path, monkeypatch):
    _align(monkeypatch)
    raw = _raw_dir(tmp_path, [
        _line('t1_a', 'loading up on $GME'),
        _line('t1_b', 'nvda is cooking'),
        _line('t3_c', 'AI names ripping', kind='posts'),
        _line('t1_g', 'GME weekly', author='/u/AutoModerator'),
    ])
    out = tmp_path / 'out'
    summary = pop.run(raw, LOOKUP, out, common_words=set())
    assert summary['posts'] == 4
    assert summary['stored_today'] == 2               # $GME, and `nvda` since 2026-09-08
    assert summary['invisible'] == 1
    assert summary['gated'] == 1
    assert summary['by_reason'] == {'explicit_cashtag': 1, 'lowercase_symbol': 1}
    assert summary['rejected_by_cause'] == {'stopword': 1}
    with open(out / 'rejected-candidates.jsonl', encoding='utf-8') as handle:
        rows = [json.loads(line) for line in handle]
    assert {r['external_id'] for r in rows} == {'t3_c'}
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


def test_a_long_ordinary_word_written_capitalised_is_not_a_company_name(monkeypatch):
    """`People` at a sentence start named PPLI 93 times in one day."""
    lookup = annotate_distinctive({
        'PPLI': {'name': 'People Inc', 'exchange': 'NASDAQ'},
        'NVDA': {'name': 'NVIDIA Corporation - Common Stock', 'exchange': 'NASDAQ'},
    })
    _align(monkeypatch, ordinary={'people'}, shapes={'nvidia'})
    row = pop.classify(_line('t1_p', 'People love Nvidia'), lookup, NOT_COMMON,
                       name_shapes=pop.NameShapes({'nvidia'}))
    assert row['rejected'] == []
    assert _accepted(row) == [('NVDA', 'name_only')]


def test_common_words_cover_name_length_words(tmp_path):
    raw = _raw_dir(tmp_path, [_line('t1_%d' % i, 'people love money') for i in range(10)]
                   + [_line('t1_c%d' % i, 'People love Money') for i in range(2)])
    common = pop.common_words(raw, min_posts=1)
    assert 'people' in common and 'money' in common


def test_a_name_token_that_is_itself_a_symbol_names_nobody():
    """'ProShares Ultra NVDA' gives NVDB the token `nvda`; a post writing
    NVDA is a symbol mention, not a name for the leveraged fund."""
    lookup = annotate_distinctive({
        'NVDA': {'name': 'NVIDIA Corporation - Common Stock', 'exchange': 'NASDAQ'},
        'NVDB': {'name': 'ProShares Ultra NVDA', 'exchange': 'NASDAQ'},
        'SPCF': {'name': 'ProShares Ultra SpaceX', 'exchange': 'NASDAQ'},
    })
    row = pop.classify(_line('t1_q', 'NVDA and SpaceX both ripping'), lookup, NOT_COMMON)
    assert [m['ticker'] for m in row['accepted']] == ['NVDA']
    assert row['rejected'] == []


def test_a_debt_listing_does_not_name_its_issuer_by_its_due_month():
    lookup = annotate_distinctive({
        'TMUSI': {'name': 'T-Mobile US, Inc. - 5.500% Senior Notes due June 2070',
                  'exchange': 'NASDAQ'},
        'ENO': {'name': 'Entergy New Orleans, LLC First Mortgage Bonds, 5.50% Series due April 1, 2066',
                'exchange': 'NYSE'},
    })
    row = pop.classify(_line('t1_r', 'June and April were rough'), lookup, NOT_COMMON)
    assert row['rejected'] == []


def test_every_accepted_mention_is_written_with_its_provenance(tmp_path):
    raw = _raw_dir(tmp_path, [
        _line('t1_a', 'loading up on $GME'),
        _line('t1_b', 'GME and gme', title='GME thread'),
    ])
    out = tmp_path / 'out'
    pop.run(raw, LOOKUP, out, common_words=set())
    with open(out / 'accepted-mentions.jsonl', encoding='utf-8') as handle:
        rows = [json.loads(line) for line in handle]
    by_id = {r['external_id']: r for r in rows}
    assert by_id['t1_a']['ticker'] == 'GME'
    assert by_id['t1_a']['reason'] == 'explicit_cashtag'
    assert by_id['t1_b']['reason'] == 'bare_source_high'
    assert by_id['t1_b']['in_author_text'] is True
    assert by_id['t1_b']['in_thread_context'] is True
    assert set(by_id['t1_b']) >= {'source', 'kind', 'created_utc', 'confidence', 'title',
                                  'author_text'}


# --- the loose pass's own blind spots, found by scanning the posts where it
# --- produced nothing at all (2,161 of 141,440 held a company reference).

# Padded to a dozen listings on purpose: annotate_distinctive's ceiling is
# a RATIO of the universe, so in a six-symbol lookup only single-issuer
# tokens survive and `apple` would be gone before this module sees it.
APPLE_LOOKUP = annotate_distinctive({
    'PAD%d' % i: {'name': 'Padding %d Industries' % i, 'exchange': 'NYSE'}
    for i in range(12)} | {
    'AAPL': {'name': 'Apple Inc. - Common Stock', 'exchange': 'NASDAQ'},
    'APLE': {'name': 'Apple Hospitality REIT, Inc. Common Shares', 'exchange': 'NYSE'},
    'GOOGL': {'name': 'Alphabet Inc. Class A Common Stock', 'exchange': 'NASDAQ'},
    'GOOG': {'name': 'Alphabet Inc. Class C Capital Stock', 'exchange': 'NASDAQ'},
    'MRNA': {'name': 'Moderna, Inc. - Common Stock', 'exchange': 'NASDAQ'},
    'META': {'name': 'Meta Platforms, Inc. - Class A Common Stock', 'exchange': 'NASDAQ'},
})


def test_a_name_shared_by_a_few_symbols_still_names_them(monkeypatch):
    """`apple` is Apple Inc and Apple Hospitality REIT, so requiring exactly
    one symbol deleted the largest company on the board. A handful of
    claimants is an ambiguity for the judge to settle, not a reason to see
    nothing."""
    _align(monkeypatch)
    row = pop.classify(_line('t1_a', 'I think Apple had a good quarter'),
                       APPLE_LOOKUP, NOT_COMMON)
    assert row['rejected'] == []
    assert set(_accepted(row)) == {('AAPL', 'name_only'), ('APLE', 'name_only')}


def test_a_name_claimed_by_too_many_symbols_still_names_nobody():
    lookup = annotate_distinctive({
        'A%03d' % i: {'name': 'Zeta %d Corp' % i, 'exchange': 'NYSE'} for i in range(9)})
    row = pop.classify(_line('t1_b', 'Zeta again'), lookup, NOT_COMMON)
    assert row['rejected'] == []


def test_a_brand_the_legal_name_never_carries_is_still_a_candidate(monkeypatch):
    """Alphabet's listings never say Google; Meta's never say Facebook."""
    _align(monkeypatch)
    row = pop.classify(_line('t1_c', 'Google is cheap and Facebook is not'),
                       APPLE_LOOKUP, NOT_COMMON)
    assert row['rejected'] == []
    assert set(_accepted(row)) == {('GOOGL', 'alias'), ('META', 'alias')}


def test_a_person_who_stands_for_a_company_is_a_candidate(monkeypatch):
    _align(monkeypatch)
    row = pop.classify(_line('t1_d', 'I would buy if Zuck leaves for good'),
                       APPLE_LOOKUP, NOT_COMMON)
    assert row['rejected'] == []
    assert _accepted(row) == [('META', 'alias')]


def test_a_distinctive_name_written_lowercase_is_a_candidate(monkeypatch):
    """'do not buy moderna today' is unmistakably real; requiring the
    capital M was a rule about typing, not about meaning."""
    _align(monkeypatch)
    row = pop.classify(_line('t1_e', 'do not buy moderna today'), APPLE_LOOKUP, NOT_COMMON)
    assert row['rejected'] == []
    assert _accepted(row) == [('MRNA', 'name_only')]


def test_a_function_word_never_names_a_company_however_it_is_written(monkeypatch):
    _align(monkeypatch, shapes={'moderna'})
    """`That` named HAVAR 171 times and `Your` named GYGY 158 in one week,
    because a capital mid-sentence can be emphasis or a list. Measured over
    the corpus the two are not close: function words are capitalised
    mid-sentence in 0.3-3.6% of their occurrences, company names in
    23-81%. So name-shaped is a property of the token, measured once, and
    a token that fails it names nobody in any case."""
    lookup = annotate_distinctive({
        'HAVAR': {'name': 'That Company Inc', 'exchange': 'NYSE'},
        'MRNA': {'name': 'Moderna, Inc. - Common Stock', 'exchange': 'NASDAQ'},
    })
    names = pop.NameShapes({'moderna'})
    row = pop.classify(_line('t1_f', '100% That happened in 2000'), lookup, NOT_COMMON,
                       name_shapes=names)
    assert row['rejected'] == []
    row = pop.classify(_line('t1_g', 'do not buy moderna today'), lookup, NOT_COMMON,
                       name_shapes=names)
    # Since 2026-09-08 production itself counts a name alone, so the loose
    # pass has nothing left to reject: the mention is ACCEPTED, as name_only.
    assert row['rejected'] == []
    assert [(m['ticker'], m['reason']) for m in row['accepted']] == [('MRNA', 'name_only')]


def test_name_shapes_are_measured_from_the_corpus(tmp_path):
    raw = _raw_dir(tmp_path, (
        [_line('t1_a%d' % i, 'i think Apple is fine') for i in range(10)]
        + [_line('t1_b%d' % i, 'well that is that') for i in range(10)]
        + [_line('t1_c%d' % i, 'That is what I said') for i in range(10)]))
    shapes = pop.name_shapes(raw, min_occurrences=5, min_share=0.1)
    assert 'apple' in shapes          # capitalised mid-sentence every time
    assert 'that' not in shapes       # capitalised only where a sentence opens


def test_a_misspelled_name_is_a_candidate(monkeypatch):
    _align(monkeypatch)
    lookup = annotate_distinctive({'NVDA': {'name': 'NVIDIA Corporation', 'exchange': 'NASDAQ'}})
    row = pop.classify(_line('t1_h', 'nvdia to the moon'), lookup, NOT_COMMON)
    # Production reads the alias table since 2026-09-08: accepted, not rejected.
    assert row['rejected'] == []
    assert [(m['ticker'], m['reason']) for m in row['accepted']] == [('NVDA', 'alias')]
