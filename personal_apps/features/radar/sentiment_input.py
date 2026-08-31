# personal_apps/features/radar/sentiment_input.py
"""Canonical sentiment input preparation (spec 2026-08-31 §4).

ONE path for local scoring, LLM judgment, training, backfill, and
evaluation, so they can never drift apart. Metadata stays structurally
separate from the author's untrusted text; nothing here appends source
labels, scores, or instructions to author_text.

The reddit comment rule: Reddit's own Atom feed titles comments as
"/u/<author> on <parent submission title>". That title is the PARENT
author's words. Production sent it to both scorers for months --
removing it raised Reddit exact agreement with blind labels from 57.5%
to 72.5% with an otherwise unchanged prompt (spec §2.2). It is dropped
even when the body is empty: an empty author_text is more honest than
borrowed parent tone. Only reddit sources get the shape test: bluesky
titles are hardcoded None and a fourchan subject is the author's own
text, where a coincidental match must stay.
"""
import dataclasses
import html
import re

from .config import source_root

PREPARATION_VERSION = 1

_WS_RE = re.compile(r'\s+')
# Uppercase token boundaries mirror extraction's bare-token shape: a
# ticker mention is $XXX or an uppercase word, never a lowercase one.
_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9])\$?([A-Z]{1,5})\b')


@dataclasses.dataclass(frozen=True)
class PreparedInput:
    author_text: str
    target_ticker: str
    source: str
    channel: str
    author: str | None
    is_comment: bool


def clean_text(text):
    """html.unescape + whitespace collapse + strip. THE cleaner.

    Both sentiment and extraction preparation call this one function, so
    a title like '/u/x\\non\\tparent' or '/u/x&nbsp;on&nbsp;parent' is a
    comment to BOTH or to NEITHER -- never a comment to one scope and
    authored text to the other (extractor-feedback plan, Codex finding 1).
    """
    return _WS_RE.sub(' ', html.unescape(text or '')).strip()


_clean = clean_text


def reddit_comment_split(source, cleaned_title):
    """(is_comment, thread_context) for an already-CLEANED title.

    The one structural fact about Reddit's Atom feed, decided in one
    place: comment titles arrive as '/u/<name> on <parent title>'.
    Splits ONCE at the first ' on ' -- usernames cannot contain spaces,
    so the first delimiter is always the structural one and a parent
    title containing ' on ' survives intact. Everything that is not a
    reddit comment returns (False, '').
    """
    is_comment = (source_root(source or '') == 'reddit'
                  and cleaned_title.startswith('/u/')
                  and ' on ' in cleaned_title)
    if not is_comment:
        return False, ''
    _username, thread_context = cleaned_title.split(' on ', 1)
    return True, thread_context


def prepare_sentiment_input(source, title, body, ticker,
                            author=None, channel=None):
    title_c, body_c = clean_text(title), clean_text(body)
    is_comment, _context = reddit_comment_split(source, title_c)
    if is_comment:
        # ALWAYS body-only, even when the body is empty: the synthetic
        # title is the PARENT author's words.
        text = body_c
    elif title_c and body_c:
        text = '%s %s' % (title_c, body_c)
    else:
        text = title_c or body_c
    return PreparedInput(author_text=text, target_ticker=ticker,
                         source=source or '', channel=channel or '',
                         author=author, is_comment=is_comment)


def mask_tickers(author_text, target_ticker, known_tickers):
    """Replace ticker tokens with stable sentinels for classifier features.

    The target becomes __TARGET__, every other recognized ticker becomes
    __OTHER_TICKER__. This is what makes a multi-ticker post ticker-aware
    instead of forcing one full-text label onto every mentioned ticker.
    """
    def swap(match):
        symbol = match.group(1)
        if symbol == target_ticker:
            return '__TARGET__'
        if symbol in known_tickers:
            return '__OTHER_TICKER__'
        return match.group(0)
    return _TOKEN_RE.sub(swap, author_text)
