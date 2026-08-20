# personal_apps/tests/test_radar_config.py
"""The source config version is what stops a subreddit being added from
manufacturing a market-wide spike the next morning (spec 6.6). It has to be
stable across runs and sensitive to the list it hashes."""
from features.radar import config


def test_version_is_stable_across_calls():
    assert config.source_config_version() == config.source_config_version()


def test_version_changes_when_the_subreddit_list_changes(monkeypatch):
    before = config.source_config_version()
    monkeypatch.setattr(config, 'SUBREDDITS', config.SUBREDDITS + ('newsub',))
    assert config.source_config_version() != before


def test_version_ignores_subreddit_order():
    forward = config.source_config_version()
    reversed_list = tuple(reversed(config.SUBREDDITS))
    import unittest.mock as mock
    with mock.patch.object(config, 'SUBREDDITS', reversed_list):
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
