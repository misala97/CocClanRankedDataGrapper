"""The set of symbols extraction is allowed to match.

Seeded from a symbol listing and refreshed weekly. The interesting logic is
reassignment: a symbol that was delisted and later reappears under a different
company name is a different instrument, and continuing its baseline would make
every subsequent spike wrong with nothing to show for it in the logs.
"""
import collections
import re

from extensions import db
from models import TickerUniverse

# A name token is only evidence for its ticker if it is rare across the whole
# universe. Nasdaq security names all end in boilerplate -- "Common Stock",
# "Class A Ordinary Share", "ETF" -- so `stock` appears in 4219 of 12596 names
# and `etf` in 5196. Treating those as corroboration meant any post containing
# the word "stock" promoted every bare token in it, which on a stock message
# board is every post.
#
# Rather than maintain a boilerplate blacklist that each new listing convention
# defeats, distinctiveness is measured from the universe itself.
# The threshold is both absolute and proportional. Absolute alone does not
# scale down: in a four-symbol universe where every name ends "Common Stock",
# `stock` has a document frequency of four and would qualify as distinctive.
# Proportional alone does not scale up: a quarter of 12596 names is 3149, which
# would admit plenty of boilerplate. Whichever is stricter wins.
MAX_NAME_TOKEN_DF = 3
MAX_NAME_TOKEN_RATIO = 0.25
MIN_NAME_TOKEN_LEN = 4

_NAME_WORD_RE = re.compile(r"[a-z']+")

# Crypto is excluded entirely (spec 3.7), and the exclusion has to work on
# every source rather than only on StockTwits, where an instrument_class field
# makes it easy. Elsewhere the giveaway is the fund's own name: BTC is
# Grayscale Bitcoin Mini Trust, ETH is Grayscale Ethereum, XRP is the Bitwise
# XRP ETF.
#
# Matched on the NAME, never on the symbol. BCH is Banco de Chile and LINK is
# Interlink Electronics -- real companies whose tickers happen to spell coins,
# and deleting them would cost genuine coverage to fix an ambiguity that only
# exists on crypto-heavy sources.
_CRYPTO_NAME_RE = re.compile(
    r'\b(bitcoin|ethereum|ether|crypto|blockchain|solana|litecoin|dogecoin'
    r'|ripple|xrp|digital\s+asset|coinbase\s+premium)\b', re.I)


def is_crypto_name(name):
    """True when a security's name marks it as crypto exposure."""
    return bool(_CRYPTO_NAME_RE.search(name or ''))


def _significant(name):
    """A comparable form of a company name.

    Legal-form suffixes are dropped so 'Acme Inc' and 'Acme Holdings Inc' can
    be recognized as the same company renaming itself rather than a new one.
    """
    if not name:
        return ''
    noise = {'inc', 'inc.', 'corp', 'corp.', 'corporation', 'co', 'co.',
             'ltd', 'ltd.', 'limited', 'plc', 'holdings', 'group', 'the',
             'company', 'sa', 'ag', 'nv'}
    words = [w for w in name.lower().replace(',', ' ').split() if w not in noise]
    return ' '.join(words)


def _is_reassignment(row, incoming_name):
    """A different company on a symbol that had been delisted.

    Both halves are required. A name change while listed is a rename; a
    delisting followed by the same name returning is a relisting.
    """
    if row.delisted_at is None:
        return False
    old = _significant(row.name)
    new = _significant(incoming_name)
    if not old or not new:
        return False
    return old.split()[:1] != new.split()[:1]


def upsert_symbols(rows, now):
    """Add or refresh universe rows. Returns counts of what happened."""
    counts = {'added': 0, 'updated': 0, 'reassigned': 0}

    for row in rows:
        symbol = (row.get('symbol') or '').strip().upper()
        if not symbol:
            continue
        name = row.get('name')
        exchange = row.get('exchange')

        existing = TickerUniverse.query.filter_by(symbol=symbol).one_or_none()
        if existing is None:
            db.session.add(TickerUniverse(symbol=symbol, name=name,
                                          exchange=exchange, first_seen=now))
            counts['added'] += 1
            continue

        if _is_reassignment(existing, name):
            existing.first_seen = now
            existing.delisted_at = None
            counts['reassigned'] += 1
        elif existing.delisted_at is not None:
            existing.delisted_at = None

        if existing.name != name or existing.exchange != exchange:
            counts['updated'] += 1
        existing.name = name
        existing.exchange = exchange

    db.session.commit()
    return counts


def mark_delisted(symbols, now):
    """Stamp delisted_at. The rows stay -- a delisted ticker still gets
    talked about, and dropping it would turn those mentions into silent
    misses rather than into recorded ones."""
    marked = 0
    for symbol in symbols:
        row = TickerUniverse.query.filter_by(
            symbol=symbol.strip().upper()).one_or_none()
        if row is not None and row.delisted_at is None:
            row.delisted_at = now
            marked += 1
    db.session.commit()
    return marked


def annotate_distinctive(lookup):
    """Add a `distinctive` token set to every entry, in place.

    A token qualifies when it appears in at most MAX_NAME_TOKEN_DF names across
    the whole lookup, is long enough to be a real word, and is not the symbol
    echoing itself. Measured against the passed lookup rather than a constant,
    so it calibrates to whatever universe it is given -- including the small
    ones in tests.

    Symbols left with an empty set can never be promoted from a bare mention.
    That is the intended outcome for tickers like HR or DYOR, whose names carry
    nothing but boilerplate.
    """
    frequency = collections.Counter()
    tokens_by_symbol = {}
    for symbol, entry in lookup.items():
        tokens = set(_NAME_WORD_RE.findall((entry.get('name') or '').lower()))
        tokens_by_symbol[symbol] = tokens
        for token in tokens:
            frequency[token] += 1

    ceiling = min(MAX_NAME_TOKEN_DF,
                  max(1, int(MAX_NAME_TOKEN_RATIO * len(lookup))))

    for symbol, tokens in tokens_by_symbol.items():
        lookup[symbol]['distinctive'] = {
            token for token in tokens
            if frequency[token] <= ceiling
            and len(token) >= MIN_NAME_TOKEN_LEN
            and token != symbol.lower()
        }
    return lookup


def load_lookup():
    """Every symbol, keyed uppercase, with its distinctive name tokens.

    Extraction uppercases candidates before it gets here -- the column is
    utf8mb4_bin and will not fold case for us.
    """
    lookup = {
        row.symbol: {'name': row.name, 'exchange': row.exchange}
        for row in TickerUniverse.query.all()
        if not is_crypto_name(row.name)
    }
    return annotate_distinctive(lookup)
