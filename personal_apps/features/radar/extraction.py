# personal_apps/features/radar/extraction.py
"""Ticker matching, in confidence tiers.

The asymmetry between cashtags and bare tokens is the whole design. `$DD` is a
deliberate act of notation and is taken at face value even for blacklisted
symbols; bare `DD` in a WSB post is almost always the phrase, not DuPont, and
is rejected. Bare matching is uppercase-only for the same reason -- lowercase
`it` is prose and would match on nearly every post ever written.
"""
import re

from .config import BARE_PATTERN, CASHTAG_PATTERN, STOPWORDS

# Cashtags accept 1-5 UPPERCASE letters. Bare tokens require 2-5: single
# uppercase letters are far more often sentence fragments, initials or
# profanity than they are Ford.
#
# Uppercase-only is a correction, not the original design. Mixed case matched
# `$t` inside "full of s%$t", `$m` inside "{ArC@$m}", `$hit` in "ain't buying
# your $hit", and `$t` in "Slayyyter $t." -- 118 of 3304 live cashtag matches,
# essentially all of it noise. Cashtag notation is uppercase by convention and
# every client that renders it uppercases, so a lowercase one is far more
# likely to be punctuation than a deliberate act of notation.
#
# The left boundary is not decoration: without it, "A$AP Rocky" yields a
# cashtag for AP (Ampco-Pittsburgh), which is how a Selena Gomez track became
# a high-confidence stock mention in live data. It does not help with the
# case above, though -- `%`, `@` and `:` all satisfy it, which is why the
# case rule is what does the work.
#
# Both patterns live in config.py, not here: changing either changes which
# mentions get counted, and source_config_version() has to hash them so a
# change invalidates the baselines built under the old rules.
_CASHTAG_RE = re.compile(CASHTAG_PATTERN)
# Guarded on the left too. A token sitting after a '$' that the cashtag
# pattern already rejected -- the AP in "A$AP" -- must not slip back in as
# a bare match.
_BARE_RE = re.compile(BARE_PATTERN)

_CONFIDENCE_RANK = {'low': 0, 'medium': 1, 'high': 2}


def extract_tickers(title, body, lookup, allow_bare=True,
                    allow_single_letter=True, bare_confidence='low'):
    """Return sorted (symbol, confidence) pairs for one post.

    lookup is universe.load_lookup()'s shape: uppercase symbol -> {'name',
    'exchange', 'distinctive'}. Candidates are uppercased before lookup because
    the symbol column is utf8mb4_bin and will not fold case.

    Returns `high` and `low` only. `medium` is awarded at rollup and appears in
    the ranking order here so the two stages compose.

    `allow_single_letter` gates one-letter cashtags, which on a general network
    are money shorthand -- $M, $B, $T -- rather than Macy's, Barnes and AT&T.
    See config.SINGLE_LETTER_CASHTAGS for the measurement.
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
        if len(raw) == 1 and not allow_single_letter:
            continue
        if raw in lookup:
            record(raw, 'high')

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
        if symbol not in lookup:
            continue
        distinctive = lookup[symbol].get('distinctive') or set()
        named = bool(distinctive & lowered_words)

        # A stopword blocks the bare token -- UNLESS a distinctive word from
        # that ticker's OWN name is in the same post. Added 2026-08-25 with
        # the junk classes, and it is what makes those safe: MDT, DE, ICE, PR
        # and OC spell a timezone, a country, an agency, a profession and a
        # county, and blocking them outright would cost Medtronic, Deere,
        # Intercontinental Exchange, Permian Resources and Owens Corning every
        # mention that is genuinely about them.
        #
        # Safe because annotate_distinctive already excludes a symbol echoing
        # itself, so `MDT` in the post cannot be its own reprieve -- only
        # `Medtronic` can. The name is a far stronger signal than the stopword
        # it overrides, and where they disagree the name is right.
        if symbol in STOPWORDS and not named:
            continue
        # `bare_confidence` is what an UNCORROBORATED bare token is worth on
        # this source, and it is per-source because the populations are not
        # comparable. The 85%-false-positive figure this tier was built on was
        # measured on a general network; sampled on r/wallstreetbets,
        # r/stocks and r/pennystocks the same discard pile was 14 of 15 real
        # tickers. Reddit comments do not write cashtags, so corroboration --
        # a different author cashtagging the same ticker in the same 15
        # minutes -- essentially never fires and the rule discarded the source
        # whole. Defaults to `low`: a new source opts in deliberately.
        record(symbol, 'high' if named else bare_confidence)

    return sorted(found.items())
