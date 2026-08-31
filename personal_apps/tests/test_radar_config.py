# personal_apps/tests/test_radar_config.py
"""The source config version is what stops a source being added from
manufacturing a market-wide spike the next morning (spec 6.6). It has to be
stable across runs and sensitive to the list it hashes."""
from features.radar import config


def test_version_is_stable_across_calls():
    assert config.source_config_version() == config.source_config_version()


def test_the_superseded_page_cap_is_gone():
    from features.radar import config

    assert not hasattr(config, 'PAGE_CAP')


def test_version_changes_when_the_source_list_changes(monkeypatch):
    before = config.source_config_version()
    monkeypatch.setattr(config, 'SOURCES', config.SOURCES + ('newsource',))
    assert config.source_config_version() != before


def test_version_changes_when_the_rollup_generation_changes(monkeypatch):
    """A corrected aggregate population cannot share the old baseline."""
    before = config.source_config_version()
    monkeypatch.setattr(config, 'ROLLUP_GENERATION',
                        config.ROLLUP_GENERATION + 1, raising=False)
    assert config.source_config_version() != before


def test_version_changes_when_the_source_name_generation_changes(monkeypatch):
    """Aggregate Reddit and per-subreddit Reddit are different populations."""
    before = config.source_config_version()
    monkeypatch.setattr(config, 'SOURCE_NAME_GENERATION',
                        config.SOURCE_NAME_GENERATION + 1)
    assert config.source_config_version() != before


def test_version_ignores_source_order():
    forward = config.source_config_version()
    reversed_list = tuple(reversed(config.SOURCES))
    import unittest.mock as mock
    with mock.patch.object(config, 'SOURCES', reversed_list):
        assert config.source_config_version() == forward


def test_version_is_short_hex():
    version = config.source_config_version()
    assert len(version) == 16
    assert all(c in '0123456789abcdef' for c in version)


def test_stopwords_are_uppercase():
    """Extraction uppercases candidates before checking membership; a
    lowercase entry here would never match and would silently let a false
    positive through."""
    assert all(word == word.upper() for word in config.STOPWORDS)


def test_ipv4_preference_is_off_unless_asked_for(monkeypatch):
    """A host with working IPv6 should use it. This exists for one broken
    machine, not as a default."""
    monkeypatch.delenv('RADAR_FORCE_IPV4', raising=False)
    assert config.prefer_ipv4_if_configured() is False


def test_ipv4_preference_applies_when_set(monkeypatch):
    import socket
    import urllib3.util.connection as urllib3_connection
    original = urllib3_connection.allowed_gai_family
    monkeypatch.setenv('RADAR_FORCE_IPV4', '1')
    try:
        assert config.prefer_ipv4_if_configured() is True
        assert urllib3_connection.allowed_gai_family() == socket.AF_INET
    finally:
        urllib3_connection.allowed_gai_family = original


def test_finance_native_sources_allow_bare_tokens():
    assert config.bare_tokens_allowed('fourchan') is True


def test_bluesky_reads_bare_tokens_since_the_tiering_changed():
    """Reversed 2026-08-23. This asserted False, set after the first live pass
    found IA (Iowa), GOP and AP among Bluesky's top bare tokens.

    What changed is not the noise but what it costs: an uncorroborated bare
    token is stored `low` and never scored, so those three now occupy table
    rows and nothing else. Meanwhile the promotion path -- a distinctive
    company name in the post, or a different author cashtagging the same
    ticker in the same bucket -- needs many independent authors, which is
    exactly what this source has.
    """
    assert config.bare_tokens_allowed('bluesky') is True


def test_an_uncharacterised_source_defaults_to_cashtags_only():
    """Safe direction for a source nobody has measured yet: a missed mention
    costs a row, a false one costs a fake spike."""
    assert config.bare_tokens_allowed('some_new_network') is False


def test_coin_shaped_symbols_are_dropped_on_general_sources():
    """BCH is Banco de Chile and LINK is Interlink Electronics, so the
    name-based crypto filter cannot see them. On the first live hour four of
    the ten loudest tickers were coins read as companies, BCH the largest."""
    assert config.coin_collision_dropped('bluesky', 'BCH') is True
    assert config.coin_collision_dropped('fourchan', 'LINK') is True


def test_a_finance_native_source_can_opt_into_coin_symbols(monkeypatch):
    """The extension point, kept alive with no live source using it.

    StockTwits was the only population where $LINK meant Interlink rather
    than Chainlink. It is retired; this pins that a future finance-native
    source can still opt in, rather than the map quietly becoming a constant
    nobody can override.
    """
    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'bluesky', True)
    assert config.coin_collision_dropped('bluesky', 'LINK') is False
    assert config.coin_collision_dropped('bluesky', 'BCH') is False


def test_ordinary_tickers_are_untouched_everywhere():
    for source in ('bluesky', 'fourchan', 'reddit'):
        assert config.coin_collision_dropped(source, 'MRNA') is False
        assert config.coin_collision_dropped(source, 'AAPL') is False


def test_an_unknown_source_drops_them():
    """Same safe default as bare tokens: unmeasured sources get the strict
    reading."""
    assert config.coin_collision_dropped('some_new_network', 'BCH') is True


# Exchange bots and the version stamp, both added 2026-08-22 after live data
# showed the board's top rows were crypto liquidation feeds and money
# shorthand rather than equities.

def test_exchange_bot_output_is_recognised():
    from features.radar.config import looks_like_bot_feed

    assert looks_like_bot_feed(
        '$485.6K $PUMP LONG liquidated on Binance @ $0.0048')
    assert looks_like_bot_feed('$H ARB 5.77% OKX -> BinanceF #arbitrage')


def test_a_person_talking_about_selling_is_not_a_bot():
    """The rule matches exchange vocabulary, not trading vocabulary. Dropping
    posts because someone wrote 'liquidated' would cost real mentions."""
    from features.radar.config import looks_like_bot_feed

    assert not looks_like_bot_feed('I liquidated my position yesterday')
    assert not looks_like_bot_feed('NVDA earnings beat, calls printing')


def test_the_version_stamp_covers_the_extraction_rules():
    """It hashed the source list alone until 2026-08-22, so every extraction
    change -- bare tokens, coin collisions, the A$AP boundary -- shipped
    without invalidating the baselines built under the previous rules. That is
    the exact discontinuity the stamp exists to prevent, so it was giving
    false assurance rather than protection.
    """
    from features.radar import config

    before = config.source_config_version()
    original = config.STOPWORDS
    try:
        config.STOPWORDS = frozenset(original | {'ZZZZ'})
        assert config.source_config_version() != before
    finally:
        config.STOPWORDS = original
    assert config.source_config_version() == before


def test_changing_a_scoring_threshold_does_not_reset_baselines():
    """Only rules that change WHICH mentions get counted belong in the stamp.
    Rescoring re-reads the same buckets, so a threshold change has no
    discontinuity to warm up from -- and resetting thirty days of history for
    one would be a self-inflicted outage."""
    from features.radar import config

    before = config.source_config_version()
    original = config.MIN_MENTIONS
    try:
        config.MIN_MENTIONS = original + 1
        assert config.source_config_version() == before
    finally:
        config.MIN_MENTIONS = original


# Source kinds. The author gate is a proxy for "how many independent voices",
# and on a broadcast network that unit is the channel, not the author.

def test_every_configured_source_has_a_kind():
    """A source with no kind still works -- it gets the forum gate -- but the
    map going stale silently is how a broadcast venue would end up judged by
    an author count it can never reach."""
    from features.radar import config

    for source in config.SOURCES:
        assert source in config.SOURCE_KIND, source


def test_an_unknown_source_gets_the_stricter_gate():
    """Forum is the tighter of the two. A source nobody has characterised
    should be judged strictly, not leniently."""
    from features.radar.config import source_kind

    assert source_kind('something-new') == 'forum'


def test_a_prefixed_source_inherits_its_roots_policy():
    """`reddit:wallstreetbets` is Reddit for every per-source judgement.

    Splitting the source name is what stops one sub's permanent feed rollover
    from marking every other sub's buckets truncated. It must not also split
    the policy: an unlisted sub inherits Reddit's rules rather than falling
    through to the strict default, which would silently disable bare tokens on
    a source that depends on them.
    """
    from features.radar import config

    assert config.source_root('reddit:wallstreetbets') == 'reddit'
    assert config.source_root('bluesky') == 'bluesky'
    assert config.bare_tokens_allowed('reddit:wallstreetbets') is True
    assert config.bare_token_confidence('reddit:pennystocks') == 'high'
    assert config.source_kind('reddit:thetagang') == 'forum'
    assert config.coin_collision_dropped('reddit:weedstocks', 'LINK') is True


def test_every_policy_lookup_uses_the_prefixed_sources_root(monkeypatch):
    """The less visible policy extension points must inherit the root too."""
    monkeypatch.setitem(config.SOURCE_KIND, 'reddit', 'broadcast')
    monkeypatch.setitem(config.SINGLE_LETTER_CASHTAGS, 'reddit', True)
    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'reddit', True)

    assert config.source_kind('reddit:wallstreetbets') == 'broadcast'
    assert config.single_letter_cashtags_allowed(
        'reddit:wallstreetbets') is True
    assert config.coin_collision_dropped(
        'reddit:wallstreetbets', 'LINK') is False


def test_root_reddit_expands_to_every_configured_concrete_source():
    expected = ['reddit:%s' % sub for sub in config.REDDIT_SUBS]

    assert config.expand_sources(['bluesky', 'reddit']) == [
        'bluesky', *expected]
    assert config.expand_sources(['reddit:wallstreetbets']) == [
        'reddit:wallstreetbets']


def test_the_version_stamp_covers_the_distinctiveness_rule():
    """Distinctiveness decides whether a bare mention is promoted to `high`,
    so changing it changes WHICH mentions get counted -- the exact
    discontinuity the stamp warms up from. It hashed the source list and the
    extraction patterns but not this, which is the same omission that shipped
    three extraction fixes over stale baselines on 2026-08-22.
    """
    from features.radar import config

    before = config.source_config_version()
    original = config.MAX_NAME_TOKEN_DF
    try:
        config.MAX_NAME_TOKEN_DF = original + 5
        assert config.source_config_version() != before
    finally:
        config.MAX_NAME_TOKEN_DF = original
    assert config.source_config_version() == before


# --- Multi-segment selection, 2026-08-25 ------------------------------------

def test_a_selection_of_several_segments_is_their_union():
    """Michi's ask: "small and micro at once".

    A union rather than an intersection -- picking two filters is asking to
    see more, not less, and an intersection of disjoint segments is always
    empty.
    """
    from features.radar.config import segments_in

    assert set(segments_in(['large', 'mid'])) == {'large', 'mid'}


def test_a_group_expands_inside_a_multi_selection():
    """`discover` is a group of three. Picking it beside `large` has to
    expand it, not filter on the literal string, or the group stops meaning
    anything the moment a second chip is on."""
    from features.radar.config import segments_in

    assert set(segments_in(['discover', 'large'])) == {
        'mid', 'micro', 'unknown', 'large'}


def test_overlapping_selections_do_not_double_up():
    """`discover` already contains `micro`. Selecting both is not an error
    and must not produce a duplicate that a caller might count."""
    from features.radar.config import segments_in

    got = segments_in(['discover', 'micro'])

    assert sorted(got) == sorted(set(got))
    assert set(got) == {'mid', 'micro', 'unknown'}


def test_an_empty_selection_still_means_everything():
    """The existing contract, which the surface reaches by deselecting every
    chip. () is 'no filter', not 'nothing matches'."""
    from features.radar.config import segments_in

    assert segments_in([]) == ()
    assert segments_in(None) == ()


def test_a_single_string_selection_still_works():
    """The default is a bare string. Widening the parameter must not
    break it."""
    from features.radar.config import segments_in

    assert set(segments_in('discover')) == {'mid', 'micro', 'unknown'}
    assert set(segments_in('large')) == {'large'}


def test_small_stays_an_alias_for_the_discover_group():
    """Bookmarked URLs carry `?segment=small` from before the rename
    (2026-08-31). They must keep resolving to the group rather than to a
    literal segment nobody has, which would be an empty board."""
    from features.radar.config import segments_in

    assert set(segments_in('small')) == {'mid', 'micro', 'unknown'}


def test_recent_ipo_is_not_in_the_discover_group():
    """A fresh listing is not automatically obscure -- SPCX debuted at $1.9T
    and sat in the tab meant for penny stocks. IPOs get their own tab and
    stay out of the bundle (Michi, 2026-08-31)."""
    from features.radar.config import segments_in

    assert 'recent_ipo' not in segments_in('discover')


def test_stocktwits_is_retired():
    """Cloudflare bot management, diagnosed 2026-08-26.

    403 on every endpoint with every user agent, from two networks. It reported
    `missing` honestly for five days and produced nothing, while remaining a
    selectable venue in the UI -- an invitation to filter on a source that has
    never returned a row.
    """
    from features.radar import config

    assert 'stocktwits' not in config.SOURCES
    assert 'stocktwits' not in config.BARE_TOKENS_ALLOWED
    assert 'stocktwits' not in config.SINGLE_LETTER_CASHTAGS
    assert 'stocktwits' not in config.COIN_SYMBOLS_MEAN_STOCKS
    assert 'stocktwits' not in config.SOURCE_KIND
    assert not hasattr(config, 'STOCKTWITS_REQUESTS_PER_HOUR')


def test_no_source_reads_a_coin_symbol_as_a_company():
    """A consequence of the retirement, named so it is not rediscovered.

    StockTwits was the only population where $LINK meant Interlink rather than
    Chainlink. With it gone, COIN_COLLISION_SYMBOLS are dropped everywhere --
    49 real tickers lose their mentions on every live source. The map stays a
    map rather than collapsing to a constant, because Telegram will need its
    own entry and the extension point is the point.
    """
    from features.radar import config

    assert not any(config.COIN_SYMBOLS_MEAN_STOCKS.values())
    assert config.coin_collision_dropped('bluesky', 'LINK') is True
