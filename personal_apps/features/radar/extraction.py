# personal_apps/features/radar/extraction.py
"""Ticker matching, in confidence tiers.

The asymmetry between cashtags and bare tokens is the whole design. `$DD` is a
deliberate act of notation and is taken at face value even for blacklisted
symbols; bare `DD` in a WSB post is almost always the phrase, not DuPont, and
is rejected. Bare matching is uppercase-only for the same reason -- lowercase
`it` is prose and would match on nearly every post ever written.
"""
import re

from .config import STOPWORDS

# Cashtags accept 1-5 letters. Bare tokens require 2-5: single uppercase
# letters are far more often sentence fragments, initials or profanity than
# they are Ford.
# The left boundary is not decoration: without it, "A$AP Rocky" yields a
# cashtag for AP (Ampco-Pittsburgh), which is how a Selena Gomez track
# became a high-confidence stock mention in live data.
_CASHTAG_RE = re.compile(r'(?<![A-Za-z0-9])\$([A-Za-z]{1,5})\b')
# Guarded on the left too. A token sitting after a '$' that the cashtag
# pattern already rejected -- the AP in "A$AP" -- must not slip back in as
# a bare match.
_BARE_RE = re.compile(r'(?<![$A-Za-z0-9])([A-Z]{2,5})\b')

_CONFIDENCE_RANK = {'low': 0, 'medium': 1, 'high': 2}


def extract_tickers(title, body, lookup, allow_bare=True):
    """Return sorted (symbol, confidence) pairs for one post.

    lookup is universe.load_lookup()'s shape: uppercase symbol -> {'name',
    'exchange', 'distinctive'}. Candidates are uppercased before lookup because
    the symbol column is utf8mb4_bin and will not fold case.

    Returns `high` and `low` only. `medium` is awarded at rollup and appears in
    the ranking order here so the two stages compose.
    """
    text = ' '.join(part for part in (title, body) if part)
    if not text.strip():
        return []

    lowered_words = set(re.findall(r"[a-z']+", text.lower()))
    found = {}

    def record(symbol, confidence):
        previous = found.get(symbol)
        if previous is None or _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[previous]:
            found[symbol] = confidence

    # Cashtags: explicit notation, accepted even for blacklisted symbols.
    for raw in _CASHTAG_RE.findall(text):
        symbol = raw.upper()
        if symbol in lookup:
            record(symbol, 'high')

    # Bare uppercase tokens, where the source's population makes them
    # meaningful at all (config.bare_tokens_allowed). On a general network
    # they are overwhelmingly ordinary words that happen to be listed.
    #
    # Measured against the real 12596-symbol universe,
    # counting these on their own produced roughly 85% false positives, so a
    # bare token stays `low` unless a distinctive word from its company name is
    # in the same post. `low` is stored but never scored; promotion to `medium`
    # happens at rollup, when a different author cashtags the same ticker in
    # the same window.
    for raw in (_BARE_RE.findall(text) if allow_bare else ()):
        symbol = raw.upper()
        if symbol in STOPWORDS or symbol not in lookup:
            continue
        distinctive = lookup[symbol].get('distinctive') or set()
        confidence = 'high' if distinctive & lowered_words else 'low'
        record(symbol, confidence)

    return sorted(found.items())
