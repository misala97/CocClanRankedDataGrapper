"""The builder: one raw post in, its constructed pairs out; a tiered pick
that spends most of the subword budget on the word-shaped symbols the
finders actually cut (`corn`, `be`, `go`), not on `ing` inside every gerund."""
from scratchpad.label_export import build_hard_negatives as build


def _lookup(**symbols):
    return {sym: {'name': name, 'distinctive': list(distinctive)}
            for sym, (name, distinctive) in symbols.items()}


def _raw(external_id='t1_x', body='ahhh I saw buttcorn take a hit', author='/u/someone',
         title='/u/someone on Daily thread', source='reddit:wallstreetbets'):
    return {'source': source, 'external_id': external_id, 'channel': 'wallstreetbets',
            'author': author, 'created_utc': '2026-09-01T00:00:01', 'title': title,
            'body': body, 'kind': 'comments'}


def test_a_raw_comment_yields_its_pairs_on_the_authored_text_only():
    """The parent title is thread context; a symbol cut out of IT is not a
    pair the judge will ever see, because the judge reads author text."""
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']),
                     NAT=('Nordic American Tankers', ['nordic', 'tankers']))
    pairs = build.pairs_for(_raw(title='/u/x on natgas thread'), lookup,
                            ordinary_words={'nat'}, name_shapes=set())
    assert [(p['symbol'], p['kind'], p['evidence']) for p in pairs] == [
        ('CORN', 'subword', 'buttcorn')]
    assert pairs[0]['author_text'] == 'ahhh I saw buttcorn take a hit'
    assert pairs[0]['external_id'] == 't1_x'


def test_a_two_letter_symbol_at_the_edge_of_an_english_word_is_noise():
    """`ne` ends `done` in every third post; a finder never proposes it and
    the judge learns nothing from it. `ws` ending... `wsb` is a cut."""
    lookup = _lookup(NE=('NextEra Energy', ['nextera']),
                     WS=('Worthington Steel', ['worthington']))
    assert build.pairs_for(_raw(body='once the world is done building'), lookup,
                           ordinary_words={'done'}, name_shapes=set()) == []
    pairs = build.pairs_for(_raw(body='warsh just fucked wsb and investors'), lookup,
                            ordinary_words={'ws'}, name_shapes=set())
    assert [(p['symbol'], p['evidence']) for p in pairs] == [('WS', 'wsb')]


def test_automation_and_bot_feeds_yield_nothing():
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']))
    assert build.pairs_for(_raw(author='AutoModerator'), lookup, set(), set()) == []


def test_a_post_too_short_to_judge_yields_nothing():
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']))
    assert build.pairs_for(_raw(body='buttcorn'), lookup, set(), set()) == []


def test_evidence_past_what_the_judge_reads_does_not_count():
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']))
    body = 'x ' * 1100 + 'buttcorn'           # the word sits past 2,000 chars
    assert build.pairs_for(_raw(body=body), lookup, set(), set()) == []


def test_the_subword_budget_prefers_word_shaped_symbols():
    wordlike = [{'external_id': 'w%d' % i, 'symbol': 'CORN', 'kind': 'subword',
                 'evidence': 'buttcorn', 'author_text': 'x'} for i in range(20)]
    other = [{'external_id': 'o%d' % i, 'symbol': 'ING', 'kind': 'subword',
              'evidence': 'buying', 'author_text': 'x'} for i in range(20)]
    picked = build.tiered_select(wordlike + other, n=10, per_symbol_cap=20, seed=1,
                                 prefer=lambda p: p['symbol'] == 'CORN', share=0.7)
    assert len(picked) == 10
    assert sum(p['symbol'] == 'CORN' for p in picked) == 7
    assert sum(p['symbol'] == 'ING' for p in picked) == 3


def test_a_word_shaped_symbol_is_a_word_the_corpus_writes():
    """An ordinary word (`corn`, `be`) or a name shape (`dive`, `twin`);
    two letters buy nothing on their own -- `ne`, `ry` are not words."""
    assert build.word_shaped('CORN', {'corn'}, set()) is True
    assert build.word_shaped('BE', {'be'}, set()) is True
    assert build.word_shaped('DIVE', set(), {'dive'}) is True
    assert build.word_shaped('NE', set(), set()) is False
    assert build.word_shaped('ING', set(), set()) is False
