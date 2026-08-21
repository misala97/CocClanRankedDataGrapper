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
