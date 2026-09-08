# personal_apps/scratchpad/label_export/span_lookup.py
"""A span of text -> one symbol, or nothing. The static middle of the
sandwich: a model finds the words, this maps them, a model judges the pair.

EXACT TIERS ONLY, and unresolved is a correct answer. Every false
resolution becomes a pair the encoder judges, and enough of them inflate
the number the probe exists to measure. So there is no fuzzy matching
here, and each tier records itself in the answer: the funnel can then
show that `symbol` hits (short generic words like `ai`) have a different
precision from `name` hits, instead of one blended rate hiding both.

Torch-free and app-free on purpose. It reads the universe from a JSON dump
so it runs in the venv that has the models and not the app, and so the
tests need neither.

Rules copied from production rather than imported from it, because the
production module drags the Flask app in: the name-word pattern, the
minimum token length, the claimant cap, and the two exclusions the
population script patches on top (leveraged funds carrying their
underlying's symbol as a "name", and notes-due listings owning a month).
"""
import collections
import re

NAME_WORD_RE = re.compile(r"[a-z']+")        # config.NAME_WORD_PATTERN
MIN_NAME_TOKEN_LEN = 4                       # config.MIN_NAME_TOKEN_LEN
MAX_NAME_CLAIMANTS = 4                       # measure_extractor_population

_NOT_AN_ISSUER_RE = re.compile(
    r'\b(ultra|ultrashort|proshares|direxion)\b'
    r'|\b(notes?|bonds?|debentures?)\b.*\bdue\b', re.IGNORECASE)

# Corporate noise a name carries and a post never writes. Conservative on
# purpose: 'american' is NOT here, because American Airlines is a company,
# and 'trust' is not here because most REITs carry it.
SUFFIX_WORDS = frozenset((
    'inc', 'incorporated', 'corp', 'corporation', 'co', 'company', 'ltd',
    'limited', 'plc', 'llc', 'lp', 'holdings', 'holding', 'group', 'common',
    'stock', 'stocks', 'shares', 'share', 'class', 'ordinary', 'adr', 'ads',
    'depositary', 'depository', 'receipts', 'receipt', 'the',
))

_NON_ALNUM_RE = re.compile(r'[^a-z0-9]+')
_APOSTROPHE_RE = re.compile(r"['\u2019]")

# Index and market names that are ALSO a listed company's name token. A
# post writing 'Nasdaq' or 'Dow' means the index; the audit found both
# resolving to NDAQ and DOW and the judge waving them through. Written as
# a symbol (DOW, $DOW) they still resolve: that is how the ticker is written.
INDEX_STOPLIST = frozenset((
    'nasdaq', 'dow', 'russell', 'nyse', 'sp', 'spx', 'ndx', 'dax', 'nikkei',
    'kospi', 'ftse', 'vix',
))


class Index:
    """The three tables one lookup needs. Built once, read many."""

    def __init__(self, symbols, by_name, by_token, aliases, ordinary=frozenset()):
        self.symbols = symbols        # set of universe symbols, uppercase
        self.by_name = by_name        # normalised name -> sorted symbols
        self.by_token = by_token      # distinctive token -> sorted symbols
        self.aliases = aliases        # lowercase word -> symbol
        self.ordinary = ordinary      # words the corpus writes in lowercase


def normalise_name(text):
    """Lowercase, punctuation to spaces, corporate suffixes and single
    letters dropped. 'Bank of America Corporation' and a post's 'bank of
    america' meet in the middle; 'S&P' becomes nothing at all."""
    # Apostrophes vanish rather than split: "Wendy's" and "Wendys" and
    # "Wendy\u2019s" must all meet at 'wendys', not at 'wendy'.
    words = _NON_ALNUM_RE.sub(' ', _APOSTROPHE_RE.sub('', (text or '').lower())).split()
    kept = [w for w in words if w not in SUFFIX_WORDS and len(w) > 1]
    return ' '.join(kept)


def build_index(lookup, aliases, ordinary=()):
    """`lookup` is {symbol: {'name': ..., 'distinctive': [...]}} as stage 1
    dumps it; `aliases` is {word: symbol-or-None}; `ordinary` the words the
    corpus writes in lowercase most of the time (ordinary-words.json)."""
    symbols = set(lookup)
    by_name = collections.defaultdict(set)
    by_token = collections.defaultdict(set)
    for symbol, entry in lookup.items():
        name = entry.get('name') or ''
        if _NOT_AN_ISSUER_RE.search(name):
            continue
        normalised = normalise_name(name)
        if normalised:
            by_name[normalised].add(symbol)
        for token in entry.get('distinctive') or ():
            # A token that is itself a symbol names nobody: a post writing
            # it is a symbol mention, handled by the symbol tier.
            if token.upper() in symbols or len(token) < MIN_NAME_TOKEN_LEN:
                continue
            by_token[token].add(symbol)
    return Index(
        symbols=symbols,
        by_name={k: sorted(v) for k, v in by_name.items()},
        by_token={k: sorted(v) for k, v in by_token.items()
                  if len(v) <= MAX_NAME_CLAIMANTS},
        # An alias to a symbol this universe does not hold is not an alias.
        aliases={word: symbol for word, symbol in (aliases or {}).items()
                 if symbol and symbol in symbols},
        ordinary=frozenset(ordinary or ()),
    )


def is_whole_word(text, start, end):
    """Whether text[start:end] is bounded by non-word characters. A finder
    that cut 'go' out of 'Avgo' or 'MT' out of 'LQMT' produced a span the
    lookup must refuse, whatever it would resolve to."""
    before = text[start - 1] if start > 0 else ''
    after = text[end] if end < len(text) else ''
    return not before.isalnum() and not after.isalnum()


def resolve(span, index):
    """(symbol, tier) or (None, 'unresolved'). First tier to answer wins."""
    text = (span or '').strip()
    if not text:
        return None, 'unresolved'

    bare = text.lstrip('$').rstrip('.,;:!?')
    written_as_symbol = text.startswith('$') or (bare.isupper() and bare.isalpha())
    normalised = normalise_name(text)

    # A word the corpus writes in lowercase -- corn, gold, go, be, twin --
    # names a company only when written as its symbol. The audit's worst
    # false accepts were exactly these, waved through by the judge at 0.99.
    if not written_as_symbol and normalised in index.ordinary:
        return None, 'unresolved'
    # An index written as an index is never the company sharing its name.
    if not written_as_symbol and normalised in INDEX_STOPLIST:
        return None, 'unresolved'

    # symbol: '$nvda', 'lyft', 'ai'. One token only -- 'The fux' is a phrase.
    if bare and not any(ch.isspace() for ch in bare) and bare.upper() in index.symbols:
        return bare.upper(), 'symbol'

    # name: the whole span is a listing's name once both are normalised.
    # Several symbols under one normalised name are share classes of one
    # issuer, not an ambiguity; the first sorted symbol stands for it.
    if normalised and normalised in index.by_name:
        return index.by_name[normalised][0], 'name'

    # tokens: every distinctive word in the span must agree on one symbol.
    claims = [set(index.by_token[t]) for t in NAME_WORD_RE.findall(text.lower())
              if t in index.by_token]
    if claims:
        agreed = set.intersection(*claims)
        if len(agreed) == 1:
            return next(iter(agreed)), 'tokens'
        return None, 'unresolved'

    # alias: brands and misspellings no listing carries. Last, so an exact
    # tier is never overridden by a table someone typed.
    alias = index.aliases.get(text.lower())
    if alias:
        return alias, 'alias'
    return None, 'unresolved'
