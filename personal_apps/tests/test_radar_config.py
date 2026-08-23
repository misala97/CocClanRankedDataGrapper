# personal_apps/tests/test_radar_config.py
"""The source config version is what stops a source being added from
manufacturing a market-wide spike the next morning (spec 6.6). It has to be
stable across runs and sensitive to the list it hashes."""
from features.radar import config


def test_version_is_stable_across_calls():
    assert config.source_config_version() == config.source_config_version()


def test_version_changes_when_the_source_list_changes(monkeypatch):
    before = config.source_config_version()
    monkeypatch.setattr(config, 'SOURCES', config.SOURCES + ('newsource',))
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
    assert config.bare_tokens_allowed('stocktwits') is True
    assert config.bare_tokens_allowed('fourchan') is True


def test_general_sources_require_cashtags():
    assert config.bare_tokens_allowed('bluesky') is False


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


def test_finance_native_sources_keep_them():
    """On StockTwits, $LINK means Interlink -- the population is discussing
    equities, so the company reading is the right one."""
    assert config.coin_collision_dropped('stocktwits', 'LINK') is False
    assert config.coin_collision_dropped('stocktwits', 'BCH') is False


def test_ordinary_tickers_are_untouched_everywhere():
    for source in ('bluesky', 'fourchan', 'stocktwits'):
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
    from features.radar.config import looks_like_exchange_bot

    assert looks_like_exchange_bot(
        '$485.6K $PUMP LONG liquidated on Binance @ $0.0048')
    assert looks_like_exchange_bot('$H ARB 5.77% OKX -> BinanceF #arbitrage')


def test_a_person_talking_about_selling_is_not_a_bot():
    """The rule matches exchange vocabulary, not trading vocabulary. Dropping
    posts because someone wrote 'liquidated' would cost real mentions."""
    from features.radar.config import looks_like_exchange_bot

    assert not looks_like_exchange_bot('I liquidated my position yesterday')
    assert not looks_like_exchange_bot('NVDA earnings beat, calls printing')


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
