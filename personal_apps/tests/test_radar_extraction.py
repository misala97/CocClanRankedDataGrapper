# personal_apps/tests/test_radar_extraction.py
"""Extraction is the highest-risk component in the pipeline: every false
positive becomes a fake spike, and the fake spike looks exactly like a real
one downstream.

The corpus below is deliberately adversarial in both directions -- posts that
must yield tickers, and posts full of symbol-shaped tokens that must yield
none.
"""
import pytest

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


def test_a_lowercase_cashtag_is_not_a_cashtag():
    """Reversed on 2026-08-22, after measuring it on live data.

    Case-insensitive matching read `$t` out of "full of s%$t", `$m` out of
    "{ArC@$m}", `$hit` out of "ain't buying your $hit" and `$t` out of
    "Slayyyter $t." -- 118 of 3304 Bluesky cashtag matches, essentially all
    noise. Cashtag notation is uppercase by convention and every client that
    renders it uppercases, so a lowercase one is far likelier to be
    punctuation than a deliberate act of notation.
    """
    assert extract_tickers(None, 'buying $gme today', LOOKUP) == []
    assert extract_tickers(None, 'buying $GME today', LOOKUP) == [('GME', 'high')]


# A lookup containing the symbols the noise actually collides with, so these
# assertions fail for the right reason. Against the shared LOOKUP above they
# would pass whatever the rule did, because it holds no F-shaped collisions --
# an absence proves nothing unless the symbol could have been found.
NOISE_LOOKUP = annotate_distinctive({
    'T': {'name': 'AT&T Inc', 'exchange': 'NYSE'},
    'M': {'name': 'Macys Inc', 'exchange': 'NYSE'},
    'HIT': {'name': 'Health In Tech Inc', 'exchange': 'NASDAQ'},
})


def test_punctuation_before_a_lowercase_letter_is_not_a_ticker():
    """The A$AP left-boundary guard does not help here: '%', '@' and ':' all
    satisfy it, so case is what does the work."""
    for text in ('full of s%$t', "ain't buying your $hit", 'Slayyyter $t.'):
        assert extract_tickers(None, text, NOISE_LOOKUP) == [], text

    # Teeth: the same strings uppercased DO resolve, so the empty results
    # above are the case rule and not a missing lookup entry.
    assert extract_tickers(None, 'holding $T', NOISE_LOOKUP) == [('T', 'high')]
    assert extract_tickers(None, 'holding $HIT', NOISE_LOOKUP) == [('HIT', 'high')]


def test_a_single_letter_cashtag_is_money_shorthand_off_a_finance_network():
    """$M and $T are million/trillion far more often than Macy's and AT&T.
    Allowed where the population is finance-native, rejected where it is not --
    the same per-source judgement bare tokens already get.
    """
    text = 'Tax at 60% for over a $M and it can be $T if we all do it'
    assert extract_tickers(None, text, NOISE_LOOKUP,
                           allow_single_letter=False) == []
    # Teeth: the identical text with the gate open finds both, so the empty
    # result above is the gate rather than the pattern.
    assert extract_tickers(None, text, NOISE_LOOKUP,
                           allow_single_letter=True) == [('M', 'high'), ('T', 'high')]
    # Multi-letter cashtags are untouched by the gate.
    assert extract_tickers(None, 'watching $HIT', NOISE_LOOKUP,
                           allow_single_letter=False) == [('HIT', 'high')]


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


def test_a_dollar_sign_inside_a_word_is_not_a_cashtag():
    """Found in live data: "A$AP Rocky" scored a high-confidence mention of
    Ampco-Pittsburgh. Stylised names put dollar signs mid-word and the pattern
    has to require a boundary on the left as well as the right."""
    lookup = annotate_distinctive({'AP': {'name': 'Ampco-Pittsburgh Corporation',
                                          'exchange': 'NYSE'}})
    assert extract_tickers(None, 'now playing A$AP Rocky', lookup) == []
    assert extract_tickers(None, 'ke$ha and A$AP', lookup) == []
    # A real cashtag still works.
    assert extract_tickers(None, 'bought $AP today', lookup) == [('AP', 'high')]
    assert extract_tickers(None, '($AP)', lookup) == [('AP', 'high')]


def test_bare_tokens_can_be_switched_off_per_source():
    """On a general-population network a bare token is overwhelmingly an
    ordinary word that happens to be listed. Live data: Bluesky's top mentions
    were IA (Iowa), GOP (the party) and AP (the news agency), while the same
    extractor on StockTwits returned MRNA, DJT and AVGO. Same code, different
    populations."""
    assert extract_tickers(None, 'GME to the moon', LOOKUP, allow_bare=False) == []
    # Cashtags still count -- a dollar sign is a deliberate act of notation
    # wherever it appears.
    assert extract_tickers(None, 'buying $GME', LOOKUP, allow_bare=False) == \
        [('GME', 'high')]


def test_bare_matching_is_on_by_default():
    """Finance-native sources keep it; the parameter exists to turn it off."""
    assert extract_tickers(None, 'GME to the moon', LOOKUP) == [('GME', 'low')]


# --- The junk classes, measured on seven days of live data 2026-08-25 -------
#
# The top thirty tickers by mention volume contained no company at all. They
# were timezones, country and region codes, government agencies, news
# organisations and ordinary capitalised words. Between them they accounted
# for a large share of every mention the pipeline handled, and a sixth of the
# SCORED set.
#
# These are named classes rather than a list of one-off collisions, which is
# the distinction that keeps this from being another round of the patching the
# extraction rethink complains about.

JUNK_LOOKUP = annotate_distinctive({
    'CDT': {'name': 'CDT Equity Inc. - Common Stock', 'exchange': 'NASDAQ'},
    'PDT': {'name': 'John Hancock Premium Dividend Fund', 'exchange': 'NYSE'},
    'ET': {'name': 'Energy Transfer LP Common Units', 'exchange': 'NYSE'},
    'MDT': {'name': 'Medtronic plc. Ordinary Shares', 'exchange': 'NYSE'},
    'UK': {'name': 'Ucommune International Ltd', 'exchange': 'NASDAQ'},
    'DE': {'name': 'Deere & Company Common Stock', 'exchange': 'NYSE'},
    'ICE': {'name': 'Intercontinental Exchange Inc. Common Stock', 'exchange': 'NYSE'},
    'NWS': {'name': 'News Corporation - Class B Common Stock', 'exchange': 'NASDAQ'},
    'TV': {'name': 'Grupo Televisa S.A.B. Common Stock', 'exchange': 'NYSE'},
    'HE': {'name': 'Hawaiian Electric Industries, Inc. Common Stock', 'exchange': 'NYSE'},
    'MMSI': {'name': 'Merit Medical Systems, Inc. - Common Stock', 'exchange': 'NASDAQ'},
    'AAPL': {'name': 'Apple Inc', 'exchange': 'NASDAQ'},
})


def junk_symbols(text):
    return [symbol for symbol, _ in extract_tickers(None, text, JUNK_LOOKUP)]


@pytest.mark.parametrize('text,symbol', [
    # Timezones. CDT alone was 3591 mentions in seven days.
    ('the panel runs 9:30-11am CDT', 'CDT'),
    ('AI and Faith will host a panel 9:30-11am PDT', 'PDT'),
    ('Filed Aug 20, 2026 - 8:00pm ET', 'ET'),
    # Country and region codes.
    ('it is just turned tummy tuesday here in the UK', 'UK'),
    ('DE hat auch nichts gemacht', 'DE'),
    # Agencies and news organisations.
    ("ICE's tactics look increasingly like torture", 'ICE'),
    ('NWS has issued a marine warning for Cape Hatteras', 'NWS'),
    # Ordinary capitalised words. WSB and Bluesky both shout constantly.
    ('local TV and talk radio and the podcasts', 'TV'),
    ('You mean HE said that?', 'HE'),
])
def test_the_measured_junk_classes_are_not_bare_tickers(text, symbol):
    assert symbol not in junk_symbols(text)


def test_the_junk_classes_keep_their_cashtags():
    """Teeth. A stopword removes bare matching only.

    `$ICE` is a deliberate act of notation and means the exchange whoever is
    in the room -- which is the same asymmetry the whole confidence design
    rests on. If the stopword killed cashtags too, Intercontinental Exchange
    would become untrackable to fix a problem about immigration reporting.
    """
    assert extract_tickers(None, 'long $ICE into earnings', JUNK_LOOKUP) == \
        [('ICE', 'high')]
    assert extract_tickers(None, 'adding $MDT and $DE', JUNK_LOOKUP) == \
        [('DE', 'high'), ('MDT', 'high')]


def test_a_stopworded_ticker_still_matches_when_its_own_company_is_named():
    """What makes the junk classes safe to add at all.

    Medtronic, Deere, Intercontinental Exchange, Permian Resources and Owens
    Corning are real companies whose tickers spell a timezone, a country, an
    agency, a profession and a county. Blocking the bare token outright would
    cost them every mention that is genuinely about them.

    A distinctive word from the ticker's OWN name is a far stronger signal
    than the stopword is, and annotate_distinctive already excludes a symbol
    echoing itself -- so `Medtronic` in the post cannot be `MDT` in the post.
    Where the two disagree, the name wins.
    """
    assert ('MDT', 'high') in extract_tickers(
        None, 'Medtronic guided up, MDT popping premarket', JUNK_LOOKUP)
    # And the reverse, which is the whole point: no company word, no match.
    assert 'MDT' not in junk_symbols('call at 4pm MDT')


def test_the_stopword_reprieve_needs_the_right_company_name():
    """Teeth for the test above.

    If any distinctive word lifted any stopword, one company's name in a post
    would unblock every stopworded ticker in it -- and posts naming a company
    are exactly the posts most likely to shout other words in capitals.
    """
    got = junk_symbols('Medtronic guided up, MDT popping, call is 4pm CDT')
    assert 'MDT' in got
    assert 'CDT' not in got


# --- Per-source bare-token confidence, measured 2026-08-25 ------------------
#
# The 85%-false-positive figure the `low` tier was built on came from a
# GENERAL network. Sampled on r/wallstreetbets, r/stocks and r/pennystocks,
# the same rule's discard pile was 14 of 15 REAL tickers -- NVDA three times,
# plus AIXI, AMST, APRE, CAST, CODX, DKS, GITS, GPUS, INHD, OLOX and SWVL.
# One junk: GPT, in a sentence about Claude and ChatGPT.
#
# Reddit comments do not use cashtags, so a bare token is the only form they
# have and corroboration -- which needs a DIFFERENT author cashtagging the
# same ticker in the same 15 minutes -- essentially never fires. The rule was
# discarding the entire source.

REDDIT_LOOKUP = annotate_distinctive({
    'NVDA': {'name': 'NVIDIA Corporation - Common Stock', 'exchange': 'NASDAQ'},
    'OLOX': {'name': 'Olenox Industries Inc. - Common Stock', 'exchange': 'OTC'},
    'DKS': {'name': "Dick's Sporting Goods Inc Common Stock", 'exchange': 'NYSE'},
    'ICE': {'name': 'Intercontinental Exchange Inc. Common Stock', 'exchange': 'NYSE'},
})


def test_a_bare_token_on_a_stock_subreddit_is_high_confidence():
    """The whole finding. "NVDA TO THE MOON" in a daily discussion thread is
    not an ambiguous token that needs a stranger to vouch for it."""
    assert extract_tickers(None, 'NVDA TO THE MOON', REDDIT_LOOKUP,
                           bare_confidence='high') == [('NVDA', 'high')]


def test_the_same_token_stays_low_on_a_general_network():
    """Teeth, and the reason this is per-source rather than a global loosening.

    Bluesky's discard pile sampled 0 of 25 real -- CNH is a Brazilian driving
    licence, HQ is comics, EU is the word "I". Promoting bare tokens there
    would put all of it on the board.
    """
    assert extract_tickers(None, 'NVDA TO THE MOON', REDDIT_LOOKUP,
                           bare_confidence='low') == [('NVDA', 'low')]


def test_low_is_still_the_default():
    """A new source must opt in deliberately. Inheriting the permissive
    setting is how a general network would quietly get Reddit's rules."""
    assert extract_tickers(None, 'NVDA TO THE MOON', REDDIT_LOOKUP) == \
        [('NVDA', 'low')]


def test_stopwords_still_win_on_a_permissive_source():
    """Promotion is about which population is being read, not a licence to
    count every capitalised word. ICE is stopworded and stays out even here --
    and the name reprieve still applies, so a post naming the exchange counts.
    """
    assert extract_tickers(None, 'ICE raids again', REDDIT_LOOKUP,
                           bare_confidence='high') == []
    assert extract_tickers(None, 'Intercontinental Exchange ICE beat',
                           REDDIT_LOOKUP, bare_confidence='high') == \
        [('ICE', 'high')]


def test_the_bare_confidence_policy_is_hashed_into_the_config_version():
    """It changes which mentions are counted, so baselines built under the old
    rule must not be read straight through the change."""
    from unittest import mock
    from features.radar import config

    before = config.source_config_version()
    with mock.patch.dict(config.BARE_TOKEN_CONFIDENCE, {'reddit': 'low'}):
        assert config.source_config_version() != before
