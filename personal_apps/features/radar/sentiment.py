# personal_apps/features/radar/sentiment.py
"""Lexicon sentiment, applied to every mention at ingest.

Cheap and adequate for the long tail. It is knowingly weak on the sarcasm and
inverted positions WSB runs on -- that is what the Claude Haiku re-read on
radar top-N is for (spec 6.11), and the two scores disagreeing is itself the
signal that a post was one of those.
"""
import re

_WORD_RE = re.compile(r"[a-z']+")

_POSITIVE = {
    'bullish': 2.0, 'buy': 1.0, 'long': 0.5, 'calls': 1.0, 'moon': 1.5,
    'squeeze': 1.0, 'rip': 1.0, 'ripping': 1.5, 'great': 1.0, 'huge': 1.0,
    'upside': 1.5, 'undervalued': 1.5, 'beat': 1.0, 'strong': 1.0,
    'rally': 1.0, 'breakout': 1.5, 'green': 0.5, 'gains': 1.0, 'win': 1.0,
}

_NEGATIVE = {
    'bearish': 2.0, 'sell': 1.0, 'short': 0.5, 'puts': 1.0, 'crash': 1.5,
    'dump': 1.5, 'dumps': 1.5, 'dumping': 1.5, 'terrible': 1.5, 'bad': 1.0,
    'overvalued': 1.5, 'miss': 1.0, 'missed': 1.0, 'weak': 1.0, 'bag': 1.0,
    'bagholder': 1.5, 'red': 0.5, 'losses': 1.0, 'rug': 1.5, 'scam': 2.0,
}

_NEGATIONS = {'not', 'no', 'never', "isn't", "aint", "ain't", "doesn't", "don't"}

# How many tokens after a negation stay flipped.
_NEGATION_SCOPE = 3

# Divisor turning a raw sum into roughly [-1, 1] before clamping. Four strong
# words in one direction is already a maximally one-sided post.
_SCALE = 8.0


def lexicon_score(text):
    """A sentiment score in [-1.0, 1.0]. 0.0 means no lexicon words matched."""
    tokens = _WORD_RE.findall((text or '').lower())
    total = 0.0
    negated_until = -1

    for index, token in enumerate(tokens):
        if token in _NEGATIONS:
            negated_until = index + _NEGATION_SCOPE
            continue

        weight = _POSITIVE.get(token, 0.0) - _NEGATIVE.get(token, 0.0)
        if weight == 0.0:
            continue
        if index <= negated_until:
            weight = -weight
        total += weight

    return max(-1.0, min(1.0, total / _SCALE))
