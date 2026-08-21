# personal_apps/features/radar/config.py
"""Radar tunables.

Everything here is configuration in the sense that changing it changes what
gets ingested -- which is exactly why SUBREDDITS is hashed into a version
stamped onto every bucket. Baselines are computed only over buckets sharing the
current version, so adding a source starts a warm-up instead of reading
straight through the discontinuity (spec 6.6).
"""
import hashlib
import json

# Active sources. Adding one is a module in sources/ plus an entry here --
# nothing else in the pipeline names a source (spec 8.6).
SOURCES = ('stocktwits', 'bluesky', 'fourchan')

# Whether a bare uppercase token may be read as a ticker on a given source.
#
# Measured on live data with the same extractor: StockTwits' top mentions were
# MRNA, DJT, AVGO, IOVA -- all real. Bluesky's were IA (Iowa), GOP (the party),
# AP (the news agency) and BTC (the coin) -- all real tickers, none of them
# about stocks. The difference is the population, not the code. Where everyone
# is discussing markets, MRNA means Moderna; on a general network almost nobody
# is, and three-letter words mean what they usually mean.
#
# Corroboration cannot rescue this. GOP's ETF is named "Subversive
# Congressional Republicans Trading", so a political post corroborates it
# perfectly, and thirty different people said "IA", so the distinct-author gate
# passes too.
#
# Sources absent from this mapping default to cashtag-only, which is the safe
# direction for a source nobody has characterised yet.
BARE_TOKENS_ALLOWED = {
    'stocktwits': True,    # finance-only by construction
    'fourchan': True,      # /biz/ is a finance board
    'bluesky': False,      # general population; cashtags only
}


# Ticker symbols that are also well-known crypto coins. The listed company is
# genuinely not crypto -- BCH is Banco de Chile, LINK is Interlink Electronics,
# ATOM is Atomera -- so the name-based crypto filter cannot see them, and
# deleting them from the universe would cost real coverage.
#
# On StockTwits, $LINK means Interlink: the population is discussing equities.
# On a general network or a crypto board it means Chainlink. Measured on the
# first live hour, four of the ten loudest tickers were these -- BCH, LINK,
# ATOM and LTC -- with BCH the single largest.
#
# So they are dropped only where the coin reading dominates, which is the same
# per-source judgement bare tokens already get.
COIN_COLLISION_SYMBOLS = frozenset({
    'BCH', 'LTC', 'LINK', 'ATOM', 'DOT', 'ADA', 'SOL', 'XMR', 'TRX', 'ALGO',
    'ICP', 'FIL', 'APT', 'ARB', 'OP', 'INJ', 'SUI', 'SEI', 'TIA', 'NEAR',
    'HBAR', 'VET', 'EOS', 'XLM', 'ETC', 'XTZ', 'AAVE', 'MKR', 'SNX', 'CRV',
    'RUNE', 'FTM', 'GRT', 'IMX', 'LDO', 'STX', 'KAS', 'TON', 'PEPE', 'SHIB',
    'DOGE', 'BNB', 'AVAX', 'MATIC', 'UNI', 'CAKE', 'RNDR', 'JUP', 'WIF',
})

# Sources where a coin-shaped symbol should be read as the coin, not the
# company. Finance-native populations are the exception.
COIN_SYMBOLS_MEAN_STOCKS = {
    'stocktwits': True,
    'fourchan': False,     # /biz/ is crypto culture first
    'bluesky': False,
}


def coin_collision_dropped(source, symbol):
    """True when this symbol should be ignored on this source."""
    if COIN_SYMBOLS_MEAN_STOCKS.get(source, False):
        return False
    return symbol in COIN_COLLISION_SYMBOLS


def bare_tokens_allowed(source):
    return BARE_TOKENS_ALLOWED.get(source, False)

# StockTwits publishes no rate-limit headers and twenty consecutive requests
# drew no 429, so this is a conservative budget rather than a documented
# ceiling. The daemon backs off on 429 regardless.
STOCKTWITS_REQUESTS_PER_HOUR = 150

# 15-minute grain. Fine enough for the 1h window in spec 6.9, coarse enough
# that a forever-retained table stays small.
BUCKET_MINUTES = 15

# Pages to walk per channel per cycle before giving up and
# marking the affected buckets `truncated` (spec 4.3).
PAGE_CAP = 10

POST_RETENTION_DAYS = 30

# English words and trading slang that collide with real ticker symbols. Every
# entry costs a real ticker its bare-token matches, so entries are only added
# when the collision is common enough to outweigh that.
STOPWORDS = frozenset({
    'IT', 'ON', 'ALL', 'FOR', 'ARE', 'CAN', 'NOW', 'ONE', 'OUT', 'NEW',
    'ANY', 'BIG', 'GET', 'GOT', 'HAS', 'HIS', 'HER', 'HOW', 'ITS', 'LET',
    'MAN', 'MAY', 'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'YOU', 'AND', 'THE',
    'DD', 'CEO', 'CFO', 'CTO', 'EPS', 'ATH', 'IMO', 'IPO', 'ETF', 'IRA',
    'USA', 'GDP', 'CPI', 'FED', 'SEC', 'IRS', 'NYSE', 'PM', 'AM', 'EOD',
    'EOW', 'OTM', 'ITM', 'ATM', 'FD', 'FDS', 'YOLO', 'PUMP', 'HOLD',
    'BUY', 'SELL', 'PUT', 'PUTS', 'CALL', 'CALLS', 'LONG', 'SHORT',
    'BULL', 'BEAR', 'MOON', 'HODL', 'LMAO', 'IMHO', 'TLDR', 'EDIT',
    # Common English words that are also live tickers. WSB writes titles in
    # caps constantly, so these fire far more often as prose than as symbols.
    # Each entry costs that ticker its bare-token matches and keeps its
    # cashtag matches, which is the right trade when the word is this common.
    'BE', 'OR', 'SO', 'AT', 'BY', 'GO', 'UP', 'US', 'WE', 'AN', 'AS',
    'IF', 'IN', 'IS', 'OF', 'TO', 'DO', 'NO', 'OK', 'VS', 'AI', 'OPEN',
    'NEXT', 'REAL', 'GOOD', 'BEST', 'CASH', 'FREE', 'LIFE', 'PLAN',
    'PLAY', 'SAFE', 'TEAM', 'TRUE', 'WELL', 'WORK', 'LOVE', 'HOPE',
})


def source_config_version():
    """A stable 16-char stamp for the active source configuration.

    Sorted before hashing so reordering the list is not a config change --
    only membership is. Stamped onto every bucket; see spec 6.6.

    This versions what is INGESTED. The UI source selector is a read-time
    filter and must never touch it, or every toggle of a checkbox would look
    like a market-wide spike.
    """
    payload = json.dumps(sorted(SOURCES), separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def prefer_ipv4_if_configured():
    """Opt-in workaround for a host that advertises IPv6 but cannot route it.

    Set RADAR_FORCE_IPV4=1 to make outbound HTTP skip AAAA records.

    Measured on one such machine: DNS returned both records, IPv4 connected in
    10 milliseconds, and IPv6 hung until the OS gave up around 43 seconds --
    which every request paid before falling back. Forcing IPv4 took a
    StockTwits call from 42.6s to 0.53s.

    Off by default and deliberately not automatic. A host with working IPv6
    should use it, and silently disabling half the internet's addressing to
    paper over one broken machine is the wrong default for the VPS.
    """
    import os
    if os.getenv('RADAR_FORCE_IPV4', '').strip() not in ('1', 'true', 'True'):
        return False

    import socket
    import urllib3.util.connection as urllib3_connection
    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
    return True
