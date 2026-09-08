# personal_apps/tests/test_span_lookup.py
"""The static middle of the sandwich: a span of text -> one symbol, or nothing.

Every tier is exact. The failure mode this guards against is a FALSE
resolution -- "S&P" landing on SPGI, "Apple Bank" on AAPL -- because each
one becomes a pair the encoder judges, and enough of them inflate the very
number the probe exists to measure. Unresolved is a correct answer here.
"""
import pytest

from scratchpad.label_export import span_lookup as sl


def _lookup():
    """A miniature universe with the shapes that matter: a share-class pair,
    a Nasdaq '- Common Stock' suffix, an ADS, a leveraged fund carrying its
    underlying's symbol, a notes-due listing, and a short generic symbol."""
    return {
        'NVDA': {'name': 'NVIDIA Corporation - Common Stock',
                 'distinctive': ['nvidia']},
        'AAPL': {'name': 'Apple Inc. - Common Stock', 'distinctive': ['apple']},
        'INTC': {'name': 'Intel Corporation - Common Stock', 'distinctive': ['intel']},
        'BAC':  {'name': 'Bank of America Corporation', 'distinctive': ['america']},
        'BIDU': {'name': 'Baidu, Inc. - ADS', 'distinctive': ['baidu']},
        'GOOG': {'name': 'Alphabet Inc. - Class C Common Stock',
                 'distinctive': ['alphabet']},
        'GOOGL': {'name': 'Alphabet Inc. - Class A Common Stock',
                  'distinctive': ['alphabet']},
        'DIS':  {'name': 'The Walt Disney Company', 'distinctive': ['walt', 'disney']},
        'LYFT': {'name': 'Lyft, Inc. - Class A Common Stock', 'distinctive': ['lyft']},
        'AI':   {'name': 'C3.ai, Inc. - Class A Common Stock', 'distinctive': []},
        # The production bug the population script patches: is_pooled_vehicle
        # misses this name, so the universe hands it distinctive tokens.
        'NVDL': {'name': 'ProShares Ultra Long NVDA Daily ETF',
                 'distinctive': ['proshares', 'nvda', 'daily']},
        'TMUS-N': {'name': 'T-Mobile US, Inc. Senior Notes due June 2070',
                   'distinctive': ['mobile', 'senior', 'june']},
        'FRST': {'name': 'First Bank Holdings', 'distinctive': ['first']},
        'SCND': {'name': 'Second Bank Holdings', 'distinctive': ['second']},
    }


ALIASES = {'google': 'GOOGL', 'nvidea': 'NVDA', 'zuck': 'META', 'cook': None}


@pytest.fixture
def index():
    return sl.build_index(_lookup(), ALIASES)


# ---- normalisation ---------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    ('Bank of America Corporation', 'bank of america'),
    ('NVIDIA Corporation - Common Stock', 'nvidia'),
    ('Alphabet Inc. - Class A Common Stock', 'alphabet'),
    ('Baidu, Inc. - ADS', 'baidu'),
    ('The Walt Disney Company', 'walt disney'),
    ('S&P', ''),                       # single letters carry nothing
    ('  intel   corp ', 'intel'),
])
def test_normalise_name_strips_corporate_noise(raw, expected):
    assert sl.normalise_name(raw) == expected


def test_normalise_keeps_words_that_only_look_like_suffixes():
    # 'American' is not a suffix even though 'ADR' expands to it.
    assert sl.normalise_name('American Airlines Group Inc.') == 'american airlines'


# ---- the tiers, one at a time ------------------------------------------------

def test_symbol_tier_resolves_a_cashtag_and_a_lowercase_symbol(index):
    assert sl.resolve('$NVDA', index) == ('NVDA', 'symbol')
    assert sl.resolve('lyft', index) == ('LYFT', 'symbol')


def test_symbol_tier_needs_a_single_token(index):
    # 'The fux' is not a symbol lookup even if 'FUX' were listed.
    symbol, tier = sl.resolve('The fux', index)
    assert symbol is None and tier == 'unresolved'


def test_name_tier_matches_after_suffix_stripping(index):
    assert sl.resolve('Bank of America', index) == ('BAC', 'name')
    assert sl.resolve('bank of america corp', index) == ('BAC', 'name')
    assert sl.resolve('Baidu', index) == ('BIDU', 'name')


def test_name_tier_picks_one_share_class_rather_than_refusing(index):
    # Both Alphabet classes normalise to 'alphabet'. That is one issuer, not
    # an ambiguity; refusing would drop every mention of Alphabet.
    symbol, tier = sl.resolve('Alphabet', index)
    assert tier == 'name'
    assert symbol == 'GOOG'          # lexicographically first, documented


def test_tokens_tier_resolves_a_distinctive_word_inside_a_longer_span(index):
    assert sl.resolve('Nvidia GPUs', index) == ('NVDA', 'tokens')
    assert sl.resolve('Disney', index) == ('DIS', 'tokens')


def test_tokens_tier_refuses_when_the_words_disagree(index):
    # 'apple' says AAPL, 'america' says BAC; nothing agrees.
    assert sl.resolve('Apple America', index) == (None, 'unresolved')


def test_tokens_tier_has_nothing_to_go_on_for_generic_words(index):
    # 'bank' is in neither distinctive list; 'holdings' is a suffix. Nothing
    # to go on -> unresolved, never a guess between FRST and SCND.
    assert sl.resolve('Bank Holdings', index) == (None, 'unresolved')


def test_a_token_too_many_symbols_claim_leaves_the_index():
    crowded = {'S%d' % i: {'name': 'Omega Thing %d' % i, 'distinctive': ['omega']}
               for i in range(sl.MAX_NAME_CLAIMANTS + 1)}
    assert 'omega' not in sl.build_index(crowded, {}).by_token
    fewer = dict(list(crowded.items())[:sl.MAX_NAME_CLAIMANTS])
    assert len(sl.build_index(fewer, {}).by_token['omega']) == sl.MAX_NAME_CLAIMANTS


def test_alias_tier_is_last_and_only_for_known_words(index):
    assert sl.resolve('google', index) == ('GOOGL', 'alias')
    assert sl.resolve('Nvidea', index) == ('NVDA', 'alias')
    # META is not in this miniature universe: an alias to an unknown symbol
    # must not resolve.
    assert sl.resolve('zuck', index) == (None, 'unresolved')
    # A None alias is an explicit "this word is nobody".
    assert sl.resolve('cook', index) == (None, 'unresolved')


def test_an_exact_tier_beats_the_alias_table(index):
    # 'nvidia' IS a listing's normalised name; it resolves there, never
    # through a table someone typed.
    assert sl.resolve('nvidia', index) == ('NVDA', 'name')


# ---- the exclusions production applies ---------------------------------------

def test_a_leveraged_fund_does_not_own_its_underlyings_symbol(index):
    # NVDL carries 'nvda' as a distinctive token. A span 'nvda' must reach
    # NVDA through the symbol tier, and 'NVDA Daily' must not land on NVDL.
    assert sl.resolve('nvda', index) == ('NVDA', 'symbol')
    assert sl.resolve('NVDA Daily', index) == (None, 'unresolved')


def test_a_notes_due_listing_does_not_claim_its_month(index):
    assert sl.resolve('June', index) == (None, 'unresolved')


def test_a_distinctive_token_that_is_itself_a_symbol_names_nobody(index):
    # Same rule as production's _name_index: 'ai' would be a symbol lookup.
    assert 'nvda' not in index.by_token
    assert 'ai' not in index.by_token


# ---- the junk GLiNER produces ------------------------------------------------

@pytest.mark.parametrize('span', ['S&P', 'fed', 'FOMC', '420C', '10Y', 'Mag 7',
                                  'PUTS', 'kek', 'guccioli', ''])
def test_market_furniture_and_noise_stay_unresolved(index, span):
    assert sl.resolve(span, index) == (None, 'unresolved')


def test_a_short_generic_symbol_still_resolves_through_the_symbol_tier(index):
    # 'ai' IS a listed symbol. Resolving it is correct: whether the post is
    # about C3.ai is the encoder's question, and the tier is recorded so the
    # funnel can show that tier's precision separately.
    assert sl.resolve('ai', index) == ('AI', 'symbol')


# ---- after the audit: possessives, indices, ordinary words, whole words ------

def _audit_lookup():
    return {
        'WEN':  {'name': "Wendy's Company (The) - Common Stock", 'distinctive': ["wendy's"]},
        'NDAQ': {'name': 'Nasdaq, Inc. - Common Stock', 'distinctive': ['nasdaq']},
        'DOW':  {'name': 'Dow Inc. Common Stock', 'distinctive': []},
        'CORN': {'name': 'Teucrium Corn Fund', 'distinctive': ['teucrium', 'corn']},
        'GOLD': {'name': 'Barrick Gold Corporation', 'distinctive': ['barrick']},
        'DELL': {'name': 'Dell Technologies Inc. Class C', 'distinctive': ['dell']},
        'GPRO': {'name': 'GoPro, Inc. - Class A Common Stock', 'distinctive': ['gopro']},
        'DASH': {'name': 'DoorDash, Inc. - Common Stock', 'distinctive': ['doordash']},
        'GO':   {'name': 'Grocery Outlet Holding Corp. - Common Stock', 'distinctive': ['grocery', 'outlet']},
    }


ORDINARY = {'corn', 'gold', 'go', 'be', 'twin', 'target'}


@pytest.fixture
def audit_index():
    return sl.build_index(_audit_lookup(), {'go pro': 'GPRO', 'door dash': 'DASH'}, ordinary=ORDINARY)


def test_possessives_meet_in_the_middle(audit_index):
    assert sl.normalise_name("Wendy's Company (The) - Common Stock") == 'wendys'
    assert sl.resolve('Wendys', audit_index) == ('WEN', 'name')
    assert sl.resolve('Wendy’s', audit_index) == ('WEN', 'name')
    assert sl.resolve("wendy's", audit_index) == ('WEN', 'name')


def test_an_index_name_never_resolves_to_the_company_that_shares_it(audit_index):
    assert sl.resolve('Nasdaq', audit_index) == (None, 'unresolved')
    assert sl.resolve('Dow', audit_index) == (None, 'unresolved')
    assert sl.resolve('Russell', audit_index) == (None, 'unresolved')


def test_an_ordinary_word_resolves_only_when_written_as_a_symbol(audit_index):
    # 'corn' is a listed fund and a vegetable; the text decides which.
    assert sl.resolve('corn', audit_index) == (None, 'unresolved')
    assert sl.resolve('Corn', audit_index) == (None, 'unresolved')
    assert sl.resolve('CORN', audit_index) == ('CORN', 'symbol')
    assert sl.resolve('$corn', audit_index) == ('CORN', 'symbol')
    assert sl.resolve('gold', audit_index) == (None, 'unresolved')
    # A name that is not an ordinary word is unaffected.
    assert sl.resolve('Dell', audit_index) == ('DELL', 'symbol')


def test_two_word_brands_resolve_through_the_alias_table(audit_index):
    assert sl.resolve('go pro', audit_index) == ('GPRO', 'alias')
    assert sl.resolve('Door dash', audit_index) == ('DASH', 'alias')
    # ...and 'go' alone, an ordinary word, never lands on Grocery Outlet.
    assert sl.resolve('go', audit_index) == (None, 'unresolved')


@pytest.mark.parametrize('text, start, end, expected', [
    ('Avgo down', 2, 4, False),          # 'go' cut out of Avgo
    ('go pro calls', 0, 2, True),
    ('wsb is wild', 0, 2, False),        # 'ws' cut out of wsb
    ('$spy drops', 1, 4, True),          # '$' is not a word character
    ('LQMT diluted', 2, 4, False),       # 'MT' inside LQMT
    ('buy Dell.', 4, 8, True),
])
def test_whole_word_rejects_a_span_cut_inside_a_word(text, start, end, expected):
    assert sl.is_whole_word(text, start, end) is expected
