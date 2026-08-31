# personal_apps/tests/test_radar_sentiment_input.py
"""Canonical sentiment input preparation (spec 2026-08-31 §4).

Pure functions, no DB.
"""
from features.radar import sentiment_input
from features.radar.sentiment_input import prepare_sentiment_input, mask_tickers


def test_reddit_comment_parent_title_is_stripped():
    p = prepare_sentiment_input(
        'reddit:wallstreetbets', '/u/someone on CRSR - The Best Opportunity',
        'I will short it at open', 'CRSR', author='/u/someone')
    assert p.author_text == 'I will short it at open'
    assert p.is_comment is True


def test_reddit_submission_keeps_title_and_body():
    p = prepare_sentiment_input(
        'reddit:wallstreetbets', 'CRSR to the moon', 'calls printed', 'CRSR')
    assert p.author_text == 'CRSR to the moon calls printed'
    assert p.is_comment is False


def test_comment_shape_on_a_non_reddit_source_is_not_stripped():
    p = prepare_sentiment_input(
        'fourchan', '/u/troll on something', 'body text', 'GME')
    assert '/u/troll on something' in p.author_text


def test_comment_shaped_title_is_discarded_even_with_an_empty_body():
    # The parent title is NEVER the comment author's words. An empty body
    # yields an honestly empty author_text, not borrowed parent tone
    # (Codex review correction 1).
    p = prepare_sentiment_input(
        'reddit:options', '/u/a on parent title', '   ', 'GME')
    assert p.author_text == ''
    assert p.is_comment is True


def test_html_entities_are_unescaped():
    p = prepare_sentiment_input('bluesky', None, 'they said &quot;sell&quot; &amp; ran', 'GME')
    assert p.author_text == 'they said "sell" & ran'


def test_whitespace_collapses_but_case_punctuation_emoji_survive():
    p = prepare_sentiment_input('bluesky', None, 'TO THE  MOON!!\n\n🚀', 'GME')
    assert p.author_text == 'TO THE MOON!! 🚀'


def test_null_title_and_body_become_empty_string():
    p = prepare_sentiment_input('bluesky', None, None, 'GME')
    assert p.author_text == ''


def test_metadata_stays_out_of_author_text():
    p = prepare_sentiment_input('reddit:options', 'title', 'body', 'GME',
                                author='/u/x', channel='options')
    assert '/u/x' not in p.author_text and 'options' not in p.author_text
    assert p.author == '/u/x' and p.channel == 'options'
    assert p.source == 'reddit:options' and p.target_ticker == 'GME'


def test_mask_tickers_marks_target_and_others():
    text = 'long $XLE short USO and SPY'
    out = mask_tickers(text, 'USO', {'XLE', 'USO', 'SPY'})
    assert '__TARGET__' in out
    assert out.count('__OTHER_TICKER__') == 2
    assert 'USO' not in out and 'XLE' not in out


def test_mask_tickers_does_not_touch_ordinary_words():
    out = mask_tickers('using a torch for fun', 'TORCH', {'TORCH'})
    assert out == 'using a torch for fun'   # lowercase word is not a ticker token


def test_preparation_version_exists():
    assert sentiment_input.PREPARATION_VERSION == 1
