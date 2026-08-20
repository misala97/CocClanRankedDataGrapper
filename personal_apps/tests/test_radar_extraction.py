# personal_apps/tests/test_radar_extraction.py
"""Extraction is the highest-risk component in the pipeline: every false
positive becomes a fake spike, and the fake spike looks exactly like a real
one downstream.

The corpus below is deliberately adversarial in both directions -- posts that
must yield tickers, and posts full of symbol-shaped tokens that must yield
none.
"""
from features.radar.extraction import extract_tickers

LOOKUP = {
    'GME': {'name': 'GameStop Corp', 'exchange': 'NYSE'},
    'AAPL': {'name': 'Apple Inc', 'exchange': 'NASDAQ'},
    'IT': {'name': 'Gartner Inc', 'exchange': 'NYSE'},
    'ALL': {'name': 'Allstate Corp', 'exchange': 'NYSE'},
    'DD': {'name': 'DuPont de Nemours Inc', 'exchange': 'NYSE'},
    'F': {'name': 'Ford Motor Company', 'exchange': 'NYSE'},
    'TSLA': {'name': 'Tesla Inc', 'exchange': 'NASDAQ'},
}


def symbols(title, body):
    return [symbol for symbol, _ in extract_tickers(title, body, LOOKUP)]


def test_cashtag_is_high_confidence():
    assert extract_tickers(None, 'loading up on $GME', LOOKUP) == [('GME', 'high')]


def test_cashtag_is_matched_case_insensitively_but_stored_upper():
    assert extract_tickers(None, 'buying $gme today', LOOKUP) == [('GME', 'high')]


def test_bare_symbol_is_medium_confidence():
    assert extract_tickers(None, 'AAPL looks strong here', LOOKUP) == [('AAPL', 'medium')]


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
    assert extract_tickers(None, 'GME GME GME', LOOKUP) == [('GME', 'medium')]


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
