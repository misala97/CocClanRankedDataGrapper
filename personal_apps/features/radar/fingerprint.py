# personal_apps/features/radar/fingerprint.py
"""Near-duplicate detection for bucket-level distinct_text_ratio.

Exact simhash equality, not Hamming-distance clustering: the ratio only needs
to separate "fifty people said fifty things" from "fifty accounts pasted one
thing", and equality does that at a fraction of the cost. Paraphrase is out of
scope and stays out of scope (spec 6.7).
"""
import hashlib
import re

_URL_RE = re.compile(r'https?://\S+')
_NON_WORD_RE = re.compile(r'[^a-z0-9\s]+')
_WHITESPACE_RE = re.compile(r'\s+')

_BITS = 64


def normalize(text):
    """Lowercase, strip URLs and punctuation, collapse whitespace.

    URLs go first and entirely: referral spam is the same pitch with a
    different tracking code, and keeping the URL would make each copy unique.
    """
    lowered = (text or '').lower()
    without_urls = _URL_RE.sub(' ', lowered)
    without_punct = _NON_WORD_RE.sub(' ', without_urls)
    return _WHITESPACE_RE.sub(' ', without_punct).strip()


def _token_hash(token):
    digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
    return int.from_bytes(digest, 'big')


def simhash64(text):
    """A 64-bit simhash of the normalized text. Stable across processes --
    blake2b rather than hash(), whose seed is randomized per interpreter."""
    tokens = normalize(text).split()
    if not tokens:
        return 0

    weights = [0] * _BITS
    for token in tokens:
        value = _token_hash(token)
        for bit in range(_BITS):
            if value >> bit & 1:
                weights[bit] += 1
            else:
                weights[bit] -= 1

    result = 0
    for bit in range(_BITS):
        if weights[bit] > 0:
            result |= 1 << bit
    return result
