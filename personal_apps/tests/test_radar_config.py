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
