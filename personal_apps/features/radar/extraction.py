# personal_apps/features/radar/extraction.py
"""Ticker matching, in confidence tiers.

The asymmetry between cashtags and bare tokens is the whole design. `$DD` is a
deliberate act of notation and is taken at face value even for blacklisted
symbols; bare `DD` in a WSB post is almost always the phrase, not DuPont, and
is rejected. Bare matching is uppercase-only for the same reason -- lowercase
`it` is prose and would match on nearly every post ever written.
"""
import dataclasses
import re

from .config import BARE_PATTERN, CASHTAG_PATTERN, STOPWORDS
# One cleaner, one comment predicate -- sentiment_input owns both, and
# extraction consuming them is what keeps the two preparations agreeing
# about what a Reddit comment even is. sentiment_input imports only
# config, so there is no cycle.
from . import sentiment_input

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

EXTRACTION_INPUT_VERSION = 1


@dataclasses.dataclass(frozen=True)
class ExtractionInput:
    """What extraction is allowed to read, with the scopes kept apart.

    thread_context can ASSOCIATE a comment with a ticker; author_text is
    the only text that speaks for the author; the synthetic username is
    neither and is discarded structurally here -- never by a global
    regex, because an authored post mentioning a Reddit user is content
    (extractor-feedback spec §4).
    """
    author_text: str
    thread_context: str
    source: str
    author: str | None
    channel: str
    is_comment: bool


def prepare_extraction_input(source, title, body, author=None, channel=None):
    title_c = sentiment_input.clean_text(title)
    body_c = sentiment_input.clean_text(body)
    is_comment, thread_context = sentiment_input.reddit_comment_split(
        source, title_c)
    if is_comment:
        author_text = body_c
    else:
        thread_context = ''
        author_text = ' '.join(part for part in (title_c, body_c) if part)
    return ExtractionInput(author_text=author_text,
                           thread_context=thread_context,
                           source=source or '', author=author,
                           channel=channel or '', is_comment=is_comment)


# Provenance reasons, strongest-first (extractor-feedback spec §6). One
# per code path below: explicit notation, name-corroborated bare token, a
# source whose population makes an uncorroborated bare token high
# (reddit), and the stored-but-never-scored low tier.
REASONS = ('explicit_cashtag', 'bare_named', 'bare_source_high', 'bare_low')

_REASON_RANK = {reason: index for index, reason in enumerate(REASONS)}


@dataclasses.dataclass(frozen=True)
class Match:
    """One extracted ticker with its provenance.

    `reason` follows the occurrence that carried the strongest
    confidence; the scope flags OR together across occurrences, so a body
    mention is not hidden merely because the parent also cashtags it.
    """
    ticker: str
    confidence: str
    reason: str
    in_author_text: bool
    in_thread_context: bool


def _scan(text, lookup, allow_bare, allow_single_letter, bare_confidence,
          lowered_words):
    """(symbol -> (confidence, reason)) for ONE scope's text.

    The rules are the pre-provenance extractor's, unchanged. See the long
    history in the comments below -- the asymmetry between cashtags and
    bare tokens is the whole design.
    """
    found = {}

    def record(symbol, confidence, reason):
        previous = found.get(symbol)
        if (previous is None
                or _CONFIDENCE_RANK[confidence]
                > _CONFIDENCE_RANK[previous[0]]):
            found[symbol] = (confidence, reason)

    # Cashtags: explicit notation, accepted even for blacklisted symbols.
    for raw in _CASHTAG_RE.findall(text):
        if len(raw) == 1 and not allow_single_letter:
            continue
        if raw in lookup:
            record(raw, 'high', 'explicit_cashtag')

    # Bare uppercase tokens, where the source's population makes them
    # meaningful at all (config.bare_tokens_allowed). Measured against the
    # real 12596-symbol universe, counting these on their own produced
    # roughly 85% false positives, so a bare token stays `low` unless a
    # distinctive word from its company name is in the same post. `low` is
    # stored but never scored; promotion to `medium` happens at rollup.
    for raw in (_BARE_RE.findall(text) if allow_bare else ()):
        symbol = raw.upper()
        if symbol not in lookup:
            continue
        distinctive = lookup[symbol].get('distinctive') or set()
        named = bool(distinctive & lowered_words)

        # A stopword blocks the bare token -- UNLESS a distinctive word
        # from that ticker's OWN name is present. MDT, DE, ICE, PR and OC
        # spell a timezone, a country, an agency, a profession and a
        # county; blocking them outright would cost Medtronic, Deere,
        # Intercontinental Exchange, Permian Resources and Owens Corning
        # every mention genuinely about them. annotate_distinctive already
        # excludes a symbol echoing itself, so only `Medtronic` can be
        # MDT's reprieve, never `MDT`.
        if symbol in STOPWORDS and not named:
            continue
        # `bare_confidence` is what an UNCORROBORATED bare token is worth
        # on this source: 85% false positives on a general network, 14 of
        # 15 real on finance-native Reddit. Defaults to `low`; a new
        # source opts in deliberately.
        if named:
            record(symbol, 'high', 'bare_named')
        else:
            record(symbol, bare_confidence,
                   'bare_source_high' if bare_confidence == 'high'
                   else 'bare_low')

    return found


def extract(prepared, lookup, allow_bare=True, allow_single_letter=True,
            bare_confidence='low'):
    """Provenance-bearing extraction over a canonical ExtractionInput.

    Scans author_text and thread_context SEPARATELY with the same rules,
    then merges per ticker: strongest confidence wins, scope flags OR
    together. Name corroboration reads BOTH scopes combined -- a parent
    title naming the company legitimately vouches for a bare token in the
    body; they are one conversation (plan-level decision, accepted in the
    Codex plan review). The discarded username never reaches either
    scope, which IS the §5.1 username exclusion.
    """
    combined = ' '.join(part for part in (prepared.author_text,
                                          prepared.thread_context) if part)
    if not combined.strip():
        return []
    lowered_words = set(re.findall(r"[a-z']+", combined.lower()))

    merged = {}
    scopes = (('in_author_text', prepared.author_text),
              ('in_thread_context', prepared.thread_context))
    for flag_name, text in scopes:
        if not text:
            continue
        for symbol, (confidence, reason) in _scan(
                text, lookup, allow_bare, allow_single_letter,
                bare_confidence, lowered_words).items():
            entry = merged.setdefault(symbol, {
                'confidence': confidence, 'reason': reason,
                'in_author_text': False, 'in_thread_context': False})
            entry[flag_name] = True
            better = (_CONFIDENCE_RANK[confidence]
                      > _CONFIDENCE_RANK[entry['confidence']]
                      or (_CONFIDENCE_RANK[confidence]
                          == _CONFIDENCE_RANK[entry['confidence']]
                          and _REASON_RANK[reason]
                          < _REASON_RANK[entry['reason']]))
            if better:
                entry['confidence'] = confidence
                entry['reason'] = reason

    return [Match(ticker=symbol, confidence=entry['confidence'],
                  reason=entry['reason'],
                  in_author_text=entry['in_author_text'],
                  in_thread_context=entry['in_thread_context'])
            for symbol, entry in sorted(merged.items())]


def extract_tickers(title, body, lookup, allow_bare=True,
                    allow_single_letter=True, bare_confidence='low'):
    """Return sorted (symbol, confidence) pairs for one post.

    COMPATIBILITY WRAPPER over extract(): treats title+body as authored
    text with no thread context and no username discard -- the pre-
    canonical behavior, byte-for-byte, which is exactly what its callers
    and the regression suite pin. The reddit comment path goes through
    prepare_extraction_input + extract(); this shape exists for
    measurement scripts and the tests that predate provenance.

    lookup is universe.load_lookup()'s shape: uppercase symbol -> {'name',
    'exchange', 'distinctive'}. Returns `high` and `low` only; `medium`
    is awarded at rollup. `allow_single_letter` gates one-letter cashtags
    (money shorthand on a general network -- $M, $B, $T).
    """
    prepared = ExtractionInput(
        author_text=' '.join(part for part in (title, body) if part),
        thread_context='', source='', author=None, channel='',
        is_comment=False)
    matches = extract(prepared, lookup, allow_bare=allow_bare,
                      allow_single_letter=allow_single_letter,
                      bare_confidence=bare_confidence)
    return [(m.ticker, m.confidence) for m in matches]
