"""Hard negatives for the encoder judge: (symbol, text) pairs a finder would
propose and no reader would accept.

The 2026-09-08 audit found the judge rubber-stamps out-of-distribution
pairs -- `corn` 1.00 for "buttcorn", `Abt` 0.99 for "about", `gold` 1.00
for the metal, `MT` inside "LQMT", `ws` inside "wsb". Its training set only
ever held pairs the production rules had proposed, so a symbol cut out of
a longer word or an ordinary word that happens to be a symbol was never
seen labelled irrelevant. These rules build such pairs from the raw week,
label-free, by construction; each kind is pure for a stated reason and a
spot-read measures the residue.
"""
from scratchpad.label_export import hard_negatives as hn


def _lookup(**symbols):
    """{SYM: {'name', 'distinctive'}} in ner/lookup.json's shape."""
    return {sym: {'name': name, 'distinctive': list(distinctive)}
            for sym, (name, distinctive) in symbols.items()}


# ---- kind B: a symbol cut out of a longer word --------------------------------

def test_a_symbol_inside_a_longer_word_is_a_subword_pair():
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']))
    pairs = hn.subword_pairs('ahhh I saw buttcorn take a big hit', lookup)
    assert pairs == [('CORN', 'buttcorn')]


def test_subword_is_case_insensitive_on_both_sides():
    lookup = _lookup(MT=('ArcelorMittal', ['arcelormittal']),
                     WS=('Worthington Steel', ['worthington']))
    assert hn.subword_pairs('LQMT was delisted', lookup) == [('MT', 'LQMT')]
    assert hn.subword_pairs('warsh just fucked wsb', lookup) == [('WS', 'wsb')]


def test_a_symbol_also_written_as_a_whole_word_is_not_a_subword_pair():
    """Then it may be a real mention; the pair is not a negative by construction."""
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']))
    assert hn.subword_pairs('corn is up, buttcorn too', lookup) == []
    assert hn.subword_pairs('CORN calls, buttcorn', lookup) == []
    assert hn.subword_pairs('$CORN buttcorn', lookup) == []


def test_a_subword_pair_needs_no_name_corroboration_in_the_text():
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']))
    assert hn.subword_pairs('Teucrium buttcorn', lookup) == []


def test_a_word_that_is_itself_a_symbol_hides_the_symbols_inside_it():
    """`Googl` is GOOGL, and GOOG inside it is the same issuer, not junk."""
    lookup = _lookup(GOOG=('Alphabet Inc. Class C', ['alphabet']),
                     GOOGL=('Alphabet Inc. Class A', ['alphabet']))
    assert hn.subword_pairs('Googl down again', lookup) == []


def test_subword_symbols_are_two_to_five_letters():
    lookup = _lookup(A=('Agilent', ['agilent']),
                     ABCDEF=('Nope', ['nope']),
                     GO=('Grocery Outlet', ['grocery', 'outlet']))
    assert hn.subword_pairs('buying gopro calls', lookup) == [('GO', 'gopro')]


def test_a_subword_pair_is_cut_at_a_word_edge_like_a_finder_cuts():
    """`butt|corn`, `LQ|MT`, `ws|b`, `Av|go`: a span finder cuts at an
    edge. `lime` in the middle of `slimed` is a substring nobody proposes."""
    lookup = _lookup(LIME=('Lime Fund', ['lime']),
                     GO=('Grocery Outlet', ['grocery', 'outlet']))
    assert hn.subword_pairs('I thought they slimed you', lookup) == []
    assert hn.subword_pairs('Avgo is down', lookup) == [('GO', 'Avgo')]


def test_urls_are_not_words():
    lookup = _lookup(CORN=('Teucrium Corn Fund', ['teucrium']))
    assert hn.subword_pairs('see https://x.com/buttcorn now', lookup) == []


# ---- kind C: an ordinary word that happens to be a symbol -----------------------

def test_an_ordinary_word_written_lowercase_is_an_ordinary_word_pair():
    lookup = _lookup(NAT=('Nordic American Tankers', ['nordic', 'tankers']))
    pairs = hn.ordinary_word_pairs('and like nat gas as well', lookup,
                                   ordinary_words={'nat', 'gas'}, name_shapes=set())
    assert pairs == [('NAT', 'nat')]


def test_an_ordinary_word_at_a_sentence_start_is_still_ordinary():
    """`Abt to full port` -- a capital where grammar puts one."""
    lookup = _lookup(ABT=('Abbott Laboratories', ['abbott']))
    pairs = hn.ordinary_word_pairs('Abt to full port first thing.', lookup,
                                   ordinary_words={'abt'}, name_shapes=set())
    assert pairs == [('ABT', 'Abt')]


def test_an_ordinary_word_capitalised_mid_sentence_may_be_a_name():
    lookup = _lookup(ABT=('Abbott Laboratories', ['abbott']))
    pairs = hn.ordinary_word_pairs('I hold Abt since May', lookup,
                                   ordinary_words={'abt'}, name_shapes=set())
    assert pairs == []


def test_the_symbol_in_caps_or_as_a_cashtag_is_a_mention_not_a_negative():
    lookup = _lookup(NAT=('Nordic American Tankers', ['nordic', 'tankers']))
    words = {'nat'}
    assert hn.ordinary_word_pairs('nat gas and NAT calls', lookup, words, set()) == []
    assert hn.ordinary_word_pairs('nat gas and $NAT', lookup, words, set()) == []


def test_a_word_the_listing_name_echoes_is_ambiguous_and_skipped():
    """`gold` for Barrick Gold, `corn` for the Corn Fund, `target` for
    Target: the metal is not the miner, but a reader could argue either
    way, and a set that is pure by construction takes no arguable pairs."""
    lookup = _lookup(GOLD=('Barrick Gold Corporation', ['barrick']))
    assert hn.ordinary_word_pairs('gold just had a run', lookup, {'gold'}, set()) == []


def test_a_word_the_corpus_writes_like_a_name_is_skipped():
    lookup = _lookup(APLE=('Apple Hospitality REIT', ['hospitality']))
    assert hn.ordinary_word_pairs('an apple a day', lookup, {'apple'},
                                  name_shapes={'apple'}) == []


def test_a_name_corroborated_word_is_not_a_negative():
    lookup = _lookup(NAT=('Nordic American Tankers', ['nordic', 'tankers']))
    assert hn.ordinary_word_pairs('nordic tankers, nat is cheap', lookup,
                                  {'nat'}, set()) == []


# ---- kind D: an index name that resolves to a company ----------------------------

def test_an_index_name_is_an_index_pair():
    lookup = _lookup(DOW=('Dow Inc.', ['dow']), NDAQ=('Nasdaq, Inc.', ['nasdaq']))
    assert hn.index_name_pairs('rotation from tech to Dow and Russell', lookup) == [('DOW', 'Dow')]
    assert hn.index_name_pairs('Nasdaq being held up by chips', lookup) == [('NDAQ', 'Nasdaq')]


def test_the_company_sense_of_an_index_name_is_left_alone():
    lookup = _lookup(NDAQ=('Nasdaq, Inc.', ['nasdaq']), DOW=('Dow Inc.', ['dow']))
    assert hn.index_name_pairs('Nasdaq Inc reported earnings', lookup) == []
    assert hn.index_name_pairs('$NDAQ and the Nasdaq', lookup) == []
    assert hn.index_name_pairs('DOW chemical, the Dow', lookup) == []


# ---- selection, exclusion, ids, the wave shape ----------------------------------

def _pair(post, symbol, kind='subword'):
    return {'external_id': post, 'symbol': symbol, 'evidence': symbol.lower(),
            'kind': kind, 'source': 'reddit:wallstreetbets',
            'created_utc': '2026-09-01T00:00:00', 'author_text': 'text ' + post}


def test_selection_caps_each_symbol_and_takes_one_pair_per_post():
    pairs = ([_pair('p%d' % i, 'GO') for i in range(10)]
             + [_pair('q%d' % i, 'MT') for i in range(3)]
             + [_pair('q0', 'WS')])
    chosen = hn.select(pairs, n=8, per_symbol_cap=4, seed=1)
    # 4 GO by the cap, then q0..q2 carry MT and WS but each post gives one pair
    assert len(chosen) == 7
    assert sum(p['symbol'] == 'GO' for p in chosen) == 4
    assert len({p['external_id'] for p in chosen}) == 7


def test_selection_is_deterministic_for_a_seed():
    pairs = [_pair('p%d' % i, 'GO') for i in range(20)]
    a = hn.select(pairs, n=5, per_symbol_cap=5, seed=7)
    b = hn.select(pairs, n=5, per_symbol_cap=5, seed=7)
    assert [p['external_id'] for p in a] == [p['external_id'] for p in b]


def test_a_post_the_locked_sets_or_audits_hold_is_excluded():
    ex = hn.Exclusions(external_ids={'t1_locked'}, texts={'a locked post'})
    assert ex.holds({'external_id': 't1_locked', 'author_text': 'anything'})
    assert ex.holds({'external_id': 't1_new', 'author_text': ' A locked  post '})
    assert not ex.holds({'external_id': 't1_new', 'author_text': 'fresh'})


def test_ids_take_their_own_block_below_the_recall_waves():
    rows = [_pair('p1', 'GO'), _pair('p2', 'MT')]
    labels, export = hn.wave_files(rows)
    assert [r['mention_id'] for r in labels] == [-3000001, -3000002]
    assert [r['mention_id'] for r in export] == [-3000001, -3000002]


def test_a_constructed_pair_is_an_irrelevant_row_in_the_wave_shape():
    [label], [export] = hn.wave_files([_pair('p1', 'GO', kind='subword')])
    assert label['ticker'] == 'GO'
    assert label['relevance'] == 'irrelevant'
    assert label['content_origin'] == 'human_chatter'
    assert (label['attitude'], label['expected_move'], label['confidence']) == (
        'none', 'unknown', 'high')
    assert label['stratum'] == 'hardneg:subword'
    assert label['model'] == hn.MODEL_TAG
    assert export['external_id'] == 'p1'
    assert export['post_id'] is None and export['simhash'] is None
    assert export['author_text'] == 'text p1'
    assert export['candidate'] == {'cause': 'subword', 'evidence': 'go',
                                   'external_id': 'p1'}


def test_a_read_verdict_keeps_the_readers_labels():
    """Kind A: pairs a reader judged, relevant ones included, so the set
    also anchors the shapes it must NOT learn to reject."""
    verdict = {'external_id': 'p9', 'symbol': 'NVDA', 'relevance': 'relevant',
               'attitude': 'positive', 'expected_move': 'up', 'evidence': 'Nvda'}
    [label], [export] = hn.wave_files(
        [hn.read_pair(verdict, {'p9': _pair('p9', 'NVDA')})])
    assert label['relevance'] == 'relevant'
    assert label['attitude'] == 'positive' and label['expected_move'] == 'up'
    assert label['stratum'] == 'hardneg:read'
    assert label['model'] == hn.READ_TAG
    assert export['candidate']['evidence'] == 'Nvda'
