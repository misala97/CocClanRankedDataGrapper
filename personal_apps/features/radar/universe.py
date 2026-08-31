"""The set of symbols extraction is allowed to match.

Seeded from a symbol listing and refreshed weekly. The interesting logic is
reassignment: a symbol that was delisted and later reappears under a different
company name is a different instrument, and continuing its baseline would make
every subsequent spike wrong with nothing to show for it in the logs.
"""
import collections
import datetime as dt
import re

from extensions import db
from models import TickerUniverse

from .prices import PriceUnavailable

from .config import (FUNDS_PROMOTE_BARE_TOKENS, LARGE_CAP_FLOOR,
                     MAX_NAME_TOKEN_DF, MAX_NAME_TOKEN_RATIO, MID_CAP_FLOOR,
                     MIN_NAME_TOKEN_LEN, NAME_WORD_PATTERN, PENNY_PRICE,
                     POOLED_VEHICLE_PATTERN, RECENT_IPO_DAYS)

# The distinctiveness tunables now live in config, so source_config_version
# can hash them -- changing any of them changes which mentions get promoted,
# and therefore which get counted.
_NAME_WORD_RE = re.compile(NAME_WORD_PATTERN)
_POOLED_RE = re.compile(POOLED_VEHICLE_PATTERN, re.IGNORECASE)

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
    counts = {'added': 0, 'updated': 0, 'reassigned': 0, 'flagged': 0}

    for row in rows:
        symbol = (row.get('symbol') or '').strip().upper()
        if not symbol:
            continue
        name = row.get('name')
        exchange = row.get('exchange')
        is_etf = row.get('is_etf')

        existing = TickerUniverse.query.filter_by(symbol=symbol).one_or_none()
        if existing is None:
            db.session.add(TickerUniverse(symbol=symbol, name=name,
                                          exchange=exchange, is_etf=is_etf,
                                          first_seen=now))
            counts['added'] += 1
            continue

        # Only when the directory actually said something. A re-seed from a
        # file without the column must not overwrite a Y we already have.
        if is_etf is not None and existing.is_etf != is_etf:
            existing.is_etf = is_etf
            # Counted separately from `updated`, which tracks name and
            # exchange. The first re-seed after the column was added rewrote
            # thousands of rows and reported "0 updated", which reads as
            # nothing having happened.
            counts['flagged'] += 1

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


def _issuer_of(name):
    """The issuer a listing belongs to.

    Everything before the first comma, ' - ', or coupon rate, so every share
    class, unit, warrant, right and note of one company collapses to a single
    key. Crude, and it only has to be good enough to stop one company counting
    as four.

    The coupon rate is there because not every issuer uses a separator:
    Sachem's four note listings read `Sachem Capital Corp. 6.00% Notes due
    2026` with nothing to split on, which made one small-cap lender look like
    five issuers and cost `sachem` its distinctiveness.
    """
    return re.split(r',| - |\s\d+(?:\.\d+)?%',
                    name or '', maxsplit=1)[0].strip().lower()


def annotate_distinctive(lookup):
    """Add a `distinctive` token set to every entry, in place.

    A token qualifies when at most MAX_NAME_TOKEN_DF distinct ISSUERS use it,
    it is long enough to be a real word, and it is not the symbol echoing
    itself. Measured against the passed lookup rather than a constant, so it
    calibrates to whatever universe it is given -- including the small ones in
    tests.

    ISSUERS, not listings, and funds excluded from the count. Counting
    listings made a company compete with its own derivatives: `tesla` appeared
    in four names -- Tesla plus three leveraged ETFs -- against a ceiling of
    three, so TSLA could never be promoted from a bare mention. The same shape
    hits small caps harder, because a recent IPO lists as Common Stock plus
    Units plus Warrants plus Rights. Both exclusions are needed: dropping
    funds alone leaves Alphabet's five share classes, and issuer-deduping
    alone leaves Tesla's three ETFs.

    POOLED VEHICLES also get no distinctive tokens of their own, under
    FUNDS_PROMOTE_BARE_TOKENS. Until 2026-08-23 they did, on the reasoning
    that an ETF's name should vouch for its own symbol -- and the live board's
    entire small-cap section came back as MAGA and GOP, thematic funds whose
    names are made of the commonest words in the discourse they are named
    after. The config constants carry the full account.

    Note the two patterns are not the same set. Token suppression uses the
    narrower POOLED_VEHICLE_PATTERN, so an ADR or a SPAC warrant stays
    promotable while a 2X leveraged ETF does not.

    The cost is that some ordinary words qualify: `peace` drops from four
    listings to one issuer because three of the four are Peace Acquisition's
    unit, warrant and right. Accepted, because promotion still requires the
    bare ticker in the same post.

    Symbols left with an empty set can never be promoted from a bare mention.
    That remains the intended outcome for tickers like HR or DYOR, whose names
    carry nothing but boilerplate.
    """
    issuers = collections.defaultdict(set)
    tokens_by_symbol = {}
    for symbol, entry in lookup.items():
        name = entry.get('name') or ''
        tokens = set(_NAME_WORD_RE.findall(name.lower()))

        # One predicate governs both halves, and it has to: a name that
        # contributes tokens must also contribute to the count, or a word
        # appearing ONLY in excluded names looks rare. That leaked -- an ADR
        # kept `depositary` as a distinctive token because all 331 names
        # carrying the word were skipped from the denominator.
        if is_pooled_vehicle(name):
            tokens_by_symbol[symbol] = (
                tokens if FUNDS_PROMOTE_BARE_TOKENS else set())
            continue

        tokens_by_symbol[symbol] = tokens
        for token in tokens:
            issuers[token].add(_issuer_of(name))

    ceiling = min(MAX_NAME_TOKEN_DF,
                  max(1, int(MAX_NAME_TOKEN_RATIO * len(lookup))))

    for symbol, tokens in tokens_by_symbol.items():
        lookup[symbol]['distinctive'] = {
            token for token in tokens
            if len(issuers.get(token, ())) <= ceiling
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


def is_pooled_vehicle(name):
    """Whether a listing is a fund rather than a company.

    One predicate, two callers: which names may promote a bare ticker, and
    which segment a row lands in. They are the same judgement -- "is this an
    operating business" -- and POOLED_VEHICLE_PATTERN carries the full account
    of what is deliberately excluded from it. ADRs stay in, because an ADR is
    a real foreign company; `trust` is not matched, because most REITs and
    plenty of operating companies carry it.
    """
    return bool(name) and bool(_POOLED_RE.search(name))


def segment_for(market_cap, ipo_date, last_price, today, name=None,
                is_etf=None):
    """Which segment tab a ticker belongs to.

    Order matters. A recent listing is its own segment whatever its size,
    because the distinguishing fact is that it has no history rather than that
    it is small. And a penny price overrides the reported cap, since a stale or
    wrong cap should not put a three-dollar stock in Large.
    """
    # `is_etf` is the Nasdaq directory's own Y/N and beats everything. The
    # name pattern is only the fallback for a row the directory has not been
    # read for -- it misses `Invesco QQQ Trust`, `SPDR Dow Jones Industrial`
    # and `SPDR Gold Shares`, which carry no fund word between them, and
    # `trust` cannot be added to it because Adamas Trust is a real company.
    # Where the directory HAS spoken and said N, the name is not consulted:
    # an operating company is not reclassified by a word in its title.
    #
    # Before everything else, including recency. A fund has no market cap to
    # look up anywhere -- Finnhub's /stock/profile2 returns an empty payload
    # for SPY and QQQ, verified against the live API 2026-08-24 -- so without
    # this it falls through to Unknown, and Unknown sits inside the Discover
    # group. That put SPY in the tab meant for the stuff nobody has heard
    # of. Ahead of recent_ipo too: a fund launched last month is still a
    # fund, not a listing to track.
    if is_etf or (is_etf is None and is_pooled_vehicle(name)):
        return 'fund'

    if ipo_date is not None and (today - ipo_date).days <= RECENT_IPO_DAYS:
        return 'recent_ipo'

    if last_price is not None and float(last_price) < PENNY_PRICE:
        return 'micro'

    # Unknown rather than micro. It is a first-class tab and frequently the
    # most interesting one; defaulting to micro would bury the names worth
    # surfacing among genuinely tiny companies.
    if market_cap is None:
        return 'unknown'

    if market_cap >= LARGE_CAP_FLOOR:
        return 'large'
    if market_cap >= MID_CAP_FLOOR:
        return 'mid'
    return 'micro'


def refresh_profiles(provider, symbols, now):
    """Pull profiles and store what came back. Returns how many were updated.

    A provider returning nothing leaves the existing row untouched: erasing a
    cap we already had would move the ticker into Unknown until the next
    refresh, which is worse than a slightly stale number.
    """
    updated = 0
    for symbol in symbols:
        try:
            profile = provider.profile(symbol)
        except PriceUnavailable:
            # We learned nothing. A timeout or a rate limit says nothing about
            # whether this symbol has a profile, so the row is left untouched
            # and asked again next run rather than stamped and left for a week.
            continue

        row = TickerUniverse.query.filter_by(symbol=symbol).one_or_none()
        if row is None:
            continue

        if profile is None:
            # The provider answered and has nothing. Stamped, so the job stops
            # asking every six hours forever -- ETFs are the common case and
            # they will never answer. The existing cap, if any, is left alone:
            # erasing it would move the ticker into Unknown.
            row.profile_refreshed_at = now
            continue

        if profile.market_cap is not None:
            row.market_cap = profile.market_cap
        if profile.ipo_date is not None:
            row.ipo_date = profile.ipo_date
        row.profile_refreshed_at = now
        updated += 1

    db.session.commit()
    return updated
