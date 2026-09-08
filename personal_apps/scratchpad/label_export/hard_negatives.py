# personal_apps/scratchpad/label_export/hard_negatives.py
"""Hard negatives for the encoder judge, built by construction.

The judge was trained only on (symbol, text) pairs the production rules had
proposed. The 2026-09-08 NER audit put finder-proposed pairs in front of it
and it rubber-stamped them: `corn` 1.00 for "buttcorn", `Abt` 0.99 for
"about", `nat` 0.97 for "nat gas", `MT` 0.92 inside "LQMT", `ws` 0.98 inside
"wsb". It had never seen a pair of those shapes labelled irrelevant, so it
read bearish text as a bearish mention.

Four kinds, each pure for a stated reason:

  read      pairs a reader judged (the audit's 44 disagreements and the 33
            pairs every finder agreed on). Relevant ones are kept: the set
            must also anchor `Nvda`, `Avgo`, `Dell` as relevant, or the
            negatives teach "a symbol written as a word is junk".
  subword   the symbol occurs only INSIDE a longer word (`buttcorn`,
            `LQMT`, `wsb`) and nowhere as a word, a cashtag or a name.
            Irrelevant by construction: nobody mentioned it.
  ordinary  an ordinary word (the corpus writes it lowercase most of the
            time) that happens to be a symbol, written lowercase or at a
            sentence start, with no cashtag, no caps and no name token of
            the company in the text. Words the listing name itself echoes
            (`gold` / Barrick Gold, `corn` / the Corn Fund, `target`) are
            arguable and left out.
  index     `Dow` and `Nasdaq` as the index, resolved to Dow Inc. / Nasdaq
            Inc. by a name lookup. The company sense (`Nasdaq Inc`, `$NDAQ`)
            is left alone.

Torch-free on purpose: what counts as a negative is a rule about the data
and belongs in the ordinary test suite. build_hard_negatives.py reads the
raw week and writes the wave files; train_encoder.py reads those like any
other wave.
"""
import random
import re

ID_BLOCK = 3_000_000                     # waves 1 and 2 took -1.. and -1000001..
MODEL_TAG = 'constructed@hard-negatives-1'
READ_TAG = 'claude-fable-5-1@ner-audit-read-2026-09-08'
PROMPT_VERSION = 'hard-negatives-1'
MIN_LEN, MAX_LEN = 2, 5
INDEX_NAMES = {'dow': 'DOW', 'nasdaq': 'NDAQ'}

_URL_RE = re.compile(r'https?://\S+|www\.\S+')
_WORD_RE = re.compile(r"[A-Za-z]+")
_CASHTAG_RE = re.compile(r'\$([A-Za-z]{1,5})\b')
_SENTENCE_START_RE = re.compile(r'(?:^\s*[-*>"\'(\[]?\s*|[.!?\n]["\')\]]?\s*)$')


def _strip_urls(text):
    return _URL_RE.sub(' ', text or '')


def _words(text):
    return _WORD_RE.findall(text)


def _whole_word(token, text):
    return re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(token), text,
                     re.IGNORECASE) is not None


def _cashtags(text):
    return {m.upper() for m in _CASHTAG_RE.findall(text)}


def _named(symbol, lookup, lowered_words):
    distinctive = set(lookup[symbol].get('distinctive') or ())
    return bool(distinctive & lowered_words)


def _lowered_words(text):
    return {w.lower() for w in _words(text)}


def _name_tokens(entry):
    return set(re.findall(r"[a-z]+", (entry.get('name') or '').lower()))


def subword_pairs(text, lookup):
    """(symbol, word) for every symbol that occurs only inside a longer word."""
    text = _strip_urls(text)
    words = _words(text)
    lowered = {w.lower() for w in words}
    cashtags = _cashtags(text)
    found = {}
    for word in words:
        if len(word) <= MIN_LEN:
            continue
        if word.upper() in lookup:
            continue                      # the word IS a symbol; what is inside it is that issuer
        low = word.lower()
        # A span finder cuts at a word's edge (`butt|corn`, `LQ|MT`, `ws|b`,
        # `Av|go`); a piece out of the middle is a substring nobody proposes.
        pieces = set()
        for length in range(MIN_LEN, min(MAX_LEN, len(low) - 1) + 1):
            pieces.add(low[:length])
            pieces.add(low[-length:])
        for piece in sorted(pieces):
            symbol = piece.upper()
            if symbol not in lookup or symbol in found:
                continue
            if piece in lowered or symbol in cashtags:
                continue
            if _named(symbol, lookup, lowered):
                continue
            found[symbol] = word
    return sorted(found.items())


def ordinary_word_pairs(text, lookup, ordinary_words, name_shapes):
    """(symbol, word) for ordinary words that are symbols, used as words."""
    text = _strip_urls(text)
    lowered = _lowered_words(text)
    cashtags = _cashtags(text)
    found = {}
    for match in _WORD_RE.finditer(text):
        word = match.group(0)
        low = word.lower()
        if not (MIN_LEN <= len(low) <= MAX_LEN) or low not in ordinary_words:
            continue
        symbol = low.upper()
        if symbol not in lookup or symbol in found:
            continue
        if word == symbol:
            continue                      # written in caps: a bare mention, not a negative
        if word != low and not _SENTENCE_START_RE.search(text[:match.start()]):
            continue                      # capitalised mid-sentence: may be a name
        if low in name_shapes or low in _name_tokens(lookup[symbol]):
            continue
        if symbol in cashtags or _whole_word_caps(symbol, text):
            continue
        if _named(symbol, lookup, lowered):
            continue
        found[symbol] = word
    return sorted(found.items())


def _whole_word_caps(symbol, text):
    return re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(symbol), text) is not None


def index_name_pairs(text, lookup):
    """(symbol, word) for an index name used as the index."""
    text = _strip_urls(text)
    lowered = _lowered_words(text)
    cashtags = _cashtags(text)
    found = {}
    for name, symbol in INDEX_NAMES.items():
        if symbol not in lookup or symbol in found:
            continue
        match = re.search(r"(?<![A-Za-z])(%s)(?![A-Za-z])(?!\s*,?\s*inc\b)" % name,
                          text, re.IGNORECASE)
        if match is None:
            continue
        if symbol in cashtags or _whole_word_caps(symbol, text):
            continue
        if re.search(r"(?<![A-Za-z])%s\s*,?\s*inc\b" % name, text, re.IGNORECASE):
            continue
        found[symbol] = match.group(1)
    return sorted(found.items())


def select(pairs, n, per_symbol_cap, seed):
    """At most `n` pairs, at most `per_symbol_cap` per symbol, one per post,
    in a shuffled order that a seed reproduces."""
    order = list(pairs)
    random.Random(seed).shuffle(order)
    per_symbol = {}
    posts = set()
    chosen = []
    for pair in order:
        if len(chosen) >= n:
            break
        if pair['external_id'] in posts:
            continue
        if per_symbol.get(pair['symbol'], 0) >= per_symbol_cap:
            continue
        per_symbol[pair['symbol']] = per_symbol.get(pair['symbol'], 0) + 1
        posts.add(pair['external_id'])
        chosen.append(pair)
    return chosen


def _norm(text):
    return ' '.join((text or '').split()).lower()


class Exclusions:
    """Posts that must not become training rows: the locked sets' posts,
    the audits' posts, anything a later measurement will read."""

    def __init__(self, external_ids=(), texts=()):
        self.external_ids = set(external_ids)
        self.texts = {_norm(t) for t in texts}

    def holds(self, row):
        return (row.get('external_id') in self.external_ids
                or _norm(row.get('author_text')) in self.texts)


def read_pair(verdict, posts):
    """A reader's verdict on (post, symbol), joined to the post's text."""
    post = posts[verdict['external_id']]
    pair = dict(post)
    pair.update({'symbol': verdict['symbol'], 'evidence': verdict.get('evidence', ''),
                 'kind': 'read', 'relevance': verdict['relevance'],
                 'content_origin': verdict.get('content_origin', 'human_chatter'),
                 'attitude': verdict.get('attitude', 'none'),
                 'expected_move': verdict.get('expected_move', 'unknown'),
                 'confidence': verdict.get('confidence', 'high')})
    return pair


def wave_files(pairs, block=ID_BLOCK):
    """(labels rows, export rows) in the recall waves' shapes, ids in their
    own block so no wave's ids can collide with another's."""
    labels, export = [], []
    for offset, pair in enumerate(pairs, start=1):
        mention_id = -(block + offset)
        kind = pair['kind']
        read = kind == 'read'
        labels.append({
            'mention_id': mention_id, 'ticker': pair['symbol'],
            'stratum': 'hardneg:%s' % kind, 'truncated': False,
            'model': READ_TAG if read else MODEL_TAG,
            'prompt_version': PROMPT_VERSION, 'run': 'hardneg-01',
            'batch': None, 'labelled_at': pair.get('labelled_at'), 'haiku': None,
            'relevance': pair.get('relevance', 'irrelevant'),
            'content_origin': pair.get('content_origin', 'human_chatter'),
            'attitude': pair.get('attitude', 'none'),
            'expected_move': pair.get('expected_move', 'unknown'),
            'confidence': pair.get('confidence', 'high'),
        })
        export.append({
            'mention_id': mention_id, 'ticker': pair['symbol'], 'post_id': None,
            'source': pair.get('source'), 'external_id': pair['external_id'],
            'channel': (pair.get('source') or '').split(':')[-1],
            'created_utc': pair.get('created_utc'), 'title': pair.get('title'),
            'author_text': pair.get('author_text') or '', 'simhash': None,
            'stratum': 'hardneg:%s' % kind,
            'candidate': {'cause': kind, 'evidence': pair.get('evidence', ''),
                          'external_id': pair['external_id']},
        })
    return labels, export
