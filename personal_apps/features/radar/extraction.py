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
_CASHTAG_RE = re.compile(r'\$([A-Za-z]{1,5})\b')
_BARE_RE = re.compile(r'\b([A-Z]{2,5})\b')

_NAME_NOISE = {'inc', 'inc.', 'corp', 'corp.', 'corporation', 'co', 'co.',
               'ltd', 'ltd.', 'limited', 'plc', 'holdings', 'group', 'the',
               'company', 'motor', 'de'}

_CONFIDENCE_RANK = {'medium': 0, 'high': 1}


def _company_tokens(name, symbol):
    """The words of a company name worth looking for in a post body.

    The symbol itself is excluded. Promotion exists to distinguish an
    ambiguous bare `AAPL` from an unambiguous `AAPL ... Apple`, and a symbol
    matching its own company name is circular -- it adds no evidence. Without
    this, every ticker whose symbol appears in its own name (AMC Entertainment,
    and a long tail like it) would promote itself to high on a bare mention and
    quietly hollow out the confidence tier.
    """
    if not name:
        return set()
    words = re.findall(r"[A-Za-z']+", name.lower())
    return {w for w in words
            if w not in _NAME_NOISE and len(w) > 2 and w != symbol.lower()}


def extract_tickers(title, body, lookup):
    """Return sorted (symbol, confidence) pairs for one post.

    lookup is universe.load_lookup()'s shape: uppercase symbol -> {'name',
    'exchange'}. Candidates are uppercased before lookup because the symbol
    column is utf8mb4_bin and will not fold case.
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

    # Bare uppercase tokens: rejected if blacklisted, promoted if the company
    # name is nearby in the same post.
    for raw in _BARE_RE.findall(text):
        symbol = raw.upper()
        if symbol in STOPWORDS or symbol not in lookup:
            continue
        name_tokens = _company_tokens(lookup[symbol].get('name'), symbol)
        confidence = 'high' if name_tokens & lowered_words else 'medium'
        record(symbol, confidence)

    return sorted(found.items())
