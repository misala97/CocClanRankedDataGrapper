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


def _clean(text):
    return _WS_RE.sub(' ', html.unescape(text or '')).strip()


def prepare_sentiment_input(source, title, body, ticker,
                            author=None, channel=None):
    title_c, body_c = _clean(title), _clean(body)
    is_comment = (source_root(source or '') == 'reddit'
                  and title_c.startswith('/u/') and ' on ' in title_c)
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
