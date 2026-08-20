# personal_apps/tests/test_radar_extraction.py
"""Extraction is the highest-risk component in the pipeline: every false
positive becomes a fake spike, and the fake spike looks exactly like a real
one downstream.

The corpus below is deliberately adversarial in both directions -- posts that
must yield tickers, and posts full of symbol-shaped tokens that must yield
none.
"""
from features.radar.extraction import extract_tickers
from features.radar.universe import annotate_distinctive

# Run through the same annotation production uses, so these tests exercise the
# real corroboration path rather than a hand-built approximation of it.
LOOKUP = annotate_distinctive({
    'GME': {'name': 'GameStop Corp', 'exchange': 'NYSE'},
    'AAPL': {'name': 'Apple Inc', 'exchange': 'NASDAQ'},
    'IT': {'name': 'Gartner Inc', 'exchange': 'NYSE'},
    'ALL': {'name': 'Allstate Corp', 'exchange': 'NYSE'},
    'DD': {'name': 'DuPont de Nemours Inc', 'exchange': 'NYSE'},
    'F': {'name': 'Ford Motor Company', 'exchange': 'NYSE'},
    'TSLA': {'name': 'Tesla Inc', 'exchange': 'NASDAQ'},
})


def symbols(title, body):
    return [symbol for symbol, _ in extract_tickers(title, body, LOOKUP)]


def test_cashtag_is_high_confidence():
    assert extract_tickers(None, 'loading up on $GME', LOOKUP) == [('GME', 'high')]


def test_cashtag_is_matched_case_insensitively_but_stored_upper():
    assert extract_tickers(None, 'buying $gme today', LOOKUP) == [('GME', 'high')]


def test_an_uncorroborated_bare_symbol_is_low_confidence():
    """Low is stored but never scored. Against the real 12596-symbol universe
    these were roughly 85% false positives, so a bare token has to earn its
    way up -- either a distinctive company word in the same post, or another
    author cashtagging it in the same window (promotion happens at rollup)."""
    assert extract_tickers(None, 'AAPL looks strong here', LOOKUP) == [('AAPL', 'low')]


def test_bare_symbol_with_company_name_is_promoted():
    result = extract_tickers('Apple earnings', 'AAPL reports tonight', LOOKUP)
    assert result == [('AAPL', 'high')]


def test_stopwords_are_rejected_as_bare_tokens():
    """The whole reason the blacklist exists. Every token here is a real
    ticker and none of them is being talked about."""
    text = 'DD on my ATH puts, IT is ALL priced in IMO, EOD PM CEO'
    assert symbols(None, text) == []


def test_a_stopword_as_a_cashtag_is_still_accepted():
    """An explicit $DD is unambiguous in a way bare DD is not."""
    assert extract_tickers(None, 'my $DD thesis', LOOKUP) == [('DD', 'high')]


def test_unknown_symbols_are_not_invented():
    assert symbols(None, 'ZZZZ and QQQQ are ripping') == []


def test_single_letter_bare_tokens_are_rejected():
    """F is a real ticker and also the most common one-letter token in
    English. Bare single letters are never worth the false positives."""
    assert symbols(None, 'F this market') == []


def test_single_letter_cashtag_is_accepted():
    assert extract_tickers(None, 'long $F into earnings', LOOKUP) == [('F', 'high')]


def test_title_and_body_are_both_scanned():
    assert symbols('GME thread', 'nothing here') == ['GME']


def test_duplicate_mentions_collapse_to_one():
    assert extract_tickers(None, 'GME GME GME', LOOKUP) == [('GME', 'low')]


def test_highest_confidence_wins_for_one_symbol():
    result = extract_tickers(None, 'GME is moving, $GME calls', LOOKUP)
    assert result == [('GME', 'high')]


def test_multiple_symbols_are_sorted():
    result = symbols(None, '$TSLA and $AAPL and $GME')
    assert result == ['AAPL', 'GME', 'TSLA']


def test_possessives_and_punctuation_do_not_break_matching():
    assert symbols(None, "GME's move, (AAPL) too.") == ['AAPL', 'GME']


def test_lowercase_prose_is_not_a_ticker():
    """Bare matching is uppercase-only. 'it is all gme' must yield nothing --
    lowercase is prose, and treating it as symbols would match constantly."""
    assert symbols(None, 'it is all gme to me') == []


def test_empty_input_is_safe():
    assert extract_tickers(None, None, LOOKUP) == []
    assert extract_tickers('', '', LOOKUP) == []


def test_a_symbol_does_not_promote_itself_via_its_own_company_name():
    """AMC bare, in a universe where the company is 'AMC Entertainment'.

    Promotion means "the company name appears nearby, so this is unambiguous".
    A symbol matching its own name is circular and is evidence of nothing --
    without this guard every ticker whose symbol sits inside its own company
    name promotes itself on a bare mention, and the confidence tier stops
    separating anything.
    """
    lookup = annotate_distinctive(
        {'AMC': {'name': 'AMC Entertainment Holdings', 'exchange': 'NYSE'}})
    assert extract_tickers(None, 'AMC ripping today', lookup) == [('AMC', 'low')]


def test_a_real_company_name_still_promotes():
    """The guard must not break the case promotion exists for."""
    lookup = annotate_distinctive(
        {'AMC': {'name': 'AMC Entertainment Holdings', 'exchange': 'NYSE'}})
    result = extract_tickers(None, 'AMC entertainment earnings tonight', lookup)
    assert result == [('AMC', 'high')]


def test_common_english_words_that_are_tickers_are_rejected():
    """WSB writes titles in caps, so these appear as prose constantly."""
    lookup = annotate_distinctive({
        'BE': {'name': 'Bloom Energy Corp', 'exchange': 'NYSE'},
        'OR': {'name': 'Osisko Gold Royalties', 'exchange': 'NYSE'},
        'AI': {'name': 'C3.ai Inc', 'exchange': 'NYSE'},
        'OPEN': {'name': 'Opendoor Technologies', 'exchange': 'NASDAQ'},
    })
    assert extract_tickers(None, 'I AM GOING TO BE RICH OR LOSE IT ALL', lookup) == []
    assert extract_tickers(None, 'OPEN interest is insane', lookup) == []
    assert extract_tickers(None, 'AI will change everything', lookup) == []


def test_those_words_still_match_as_cashtags():
    """Rejecting the bare token must not cost the ticker its explicit form."""
    lookup = annotate_distinctive(
        {'BE': {'name': 'Bloom Energy Corp', 'exchange': 'NYSE'}})
    assert extract_tickers(None, 'long $BE into earnings', lookup) == [('BE', 'high')]


def test_boilerplate_in_a_security_name_is_not_corroboration():
    """The bug this whole tier exists because of.

    Nasdaq security names all end in "Common Stock", so `stock` appears in 4219
    of 12596 names. Treating it as corroboration meant any post containing the
    word "stock" promoted every bare token in it to high -- which, on a stock
    message board, is every post.
    """
    lookup = annotate_distinctive({
        'DRS': {'name': 'Leonardo DRS, Inc. - Common Stock', 'exchange': 'NASDAQ'},
        'RC': {'name': 'Ready Capital Corporation Common Stock', 'exchange': 'NYSE'},
        'GME': {'name': 'GameStop Corporation Common Stock', 'exchange': 'NYSE'},
    })
    result = dict(extract_tickers(None, 'my favourite stock is DRS and RC', lookup))
    assert result.get('DRS') == 'low'
    assert result.get('RC') == 'low'

    # The distinctive word still works.
    promoted = dict(extract_tickers(None, 'GME is gamestop', lookup))
    assert promoted['GME'] == 'high'


def test_a_word_common_across_the_universe_is_not_corroboration():
    """`healthcare` appears in every name here, so it carries no information
    about which ticker is meant. A genuinely rare word in the same names still
    does -- the rule is about how much a word narrows things down, not about
    any hand-picked list."""
    lookup = annotate_distinctive({
        'HR': {'name': 'Healthcare Realty Trust Common Stock', 'exchange': 'NYSE'},
        'HCA': {'name': 'HCA Healthcare Inc Common Stock', 'exchange': 'NYSE'},
        'CTRE': {'name': 'CareTrust Healthcare Common Stock', 'exchange': 'NYSE'},
        'DOC': {'name': 'Healthpeak Healthcare Common Stock', 'exchange': 'NYSE'},
    })
    assert 'healthcare' not in lookup['HR']['distinctive']
    assert 'stock' not in lookup['HR']['distinctive']
    assert extract_tickers(None, 'healthcare stocks like HR', lookup) == [('HR', 'low')]
    # `realty` is unique to HR in this universe, so it does corroborate.
    assert extract_tickers(None, 'realty play: HR', lookup) == [('HR', 'high')]
