# personal_apps/features/radar/config.py
"""Radar tunables.

Everything here is configuration in the sense that changing it changes what
gets ingested -- which is exactly why SUBREDDITS is hashed into a version
stamped onto every bucket. Baselines are computed only over buckets sharing the
current version, so adding a source starts a warm-up instead of reading
straight through the discontinuity (spec 6.6).
"""
import datetime as dt
import hashlib
import json
import re

# Active sources. Adding one is a module in sources/ plus an entry here --
# nothing else in the pipeline names a source (spec 8.6).
SOURCES = ('stocktwits', 'bluesky', 'fourchan', 'reddit')

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
    # Was False, set after the first live pass found IA (Iowa), GOP and AP
    # among the top bare tokens. Re-enabled 2026-08-23: an uncorroborated bare
    # token is stored `low` and never scored, so the junk that measurement
    # found now costs a row in a table and nothing on the board. What it buys
    # is the promotion path -- a distinctive company name in the same post, or
    # a different author cashtagging the same ticker in the same bucket --
    # which needs many independent authors and is therefore exactly this
    # source. Verified on Telegram, where channels whose bare tokens were RSI,
    # ROE, DMA and GROW produced zero high-confidence hits.
    #
    # See scripts/measure_bare_tokens.py. Revert if the top twenty scored
    # tickers stop looking like equities.
    'bluesky': True,
    # A finance subreddit is finance-native the way /biz/ and StockTwits are:
    # `AAPL` without a dollar sign is a ticker there in a way it is not on a
    # general network. Measured 2026-08-24, the junk this admits is the same
    # shape as elsewhere -- WTF and NATO topped r/StockMarket, OI and CC
    # topped r/options -- and lands as `low`, counted but never scored.
    'reddit': True,
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


# What kind of venue each source is, which decides how its independent voices
# get counted.
#
# The author gate is a proxy for one question -- how many independent voices
# are saying this. On a forum that is distinct authors. On a BROADCAST network
# one admin posts and thousands read, so every bucket has exactly one author
# and the author gate can never be cleared however loud the ticker is. There
# the independent unit is the CHANNEL: three channels carrying the same symbol
# is corroboration, one channel posting it forty times is not.
SOURCE_KIND = {
    'stocktwits': 'forum',
    'bluesky': 'forum',
    'fourchan': 'forum',
    # Comments carry real distinct authors, so the forum gate applies
    # unchanged -- unlike a broadcast channel, where one admin is every voice.
    'reddit': 'forum',
}


def source_kind(source):
    """'forum' or 'broadcast'. Unknown sources are treated as forums.

    The strict direction: forum is the tighter gate, so a source nobody has
    characterised is judged by the harder standard rather than waved through.
    """
    return SOURCE_KIND.get(source, 'forum')


# Single-letter cashtags. `$M`, `$B`, `$T` and `$K` are money shorthand far
# more often than Macy's, Barnes Group, AT&T and Kellanova -- measured on live
# Bluesky, 119 of 3302 cashtag matches were single letters and essentially all
# of them were prose: "Tax @60% for over a $M", "make $B's", "is $B & can be
# $T if we all do it". A finance-native population is the exception, the same
# judgement bare tokens and coin collisions already get.
SINGLE_LETTER_CASHTAGS = {
    'stocktwits': True,
    'fourchan': False,
    'bluesky': False,
}

# Exchange bots, not people. Crypto liquidation and arbitrage feeds post in a
# fixed format and are prolific on general networks:
#
#   "$485.6K $PUMP LONG liquidated on Binance @ $0.0048"
#   "$H ARB 5.77% OKX -> BinanceF #arbitrage"
#
# They are dropped whole rather than symbol by symbol, because the post is not
# a person discussing anything -- and the symbols they carry are coins, so
# per-symbol rules would have to enumerate a list that changes weekly. Matched
# on the exchange vocabulary itself, which is what stays constant.
_EXCHANGE_BOT_RE = re.compile(
    r'liquidated on\b|\bOKX\b|\bBinanceF\b|#arbitrage\b|vs\. Bitcoin\b',
    re.IGNORECASE)


# The two matching patterns. They sit here rather than in extraction.py
# because changing either changes WHICH mentions get counted, and
# source_config_version() below has to be able to see them -- extraction
# imports this module, so the dependency cannot run the other way.
#
# Cashtags: 1-5 UPPERCASE letters, with a left boundary so "A$AP Rocky" does
# not yield AP. Uppercase-only is what stops `$t` matching inside "s%$t".
CASHTAG_PATTERN = r'(?<![A-Za-z0-9])\$([A-Z]{1,5})\b'

# Bare tokens: 2-5 uppercase, guarded on the left so a token the cashtag
# pattern already rejected cannot slip back in as a bare match.
BARE_PATTERN = r'(?<![$A-Za-z0-9])([A-Z]{2,5})\b'


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
#
# These live here rather than in universe.py for the same reason the two match
# patterns above do: changing any of them changes WHICH mentions get counted,
# and source_config_version() has to see it. universe imports config, so the
# dependency cannot run the other way.
MAX_NAME_TOKEN_DF = 3
MAX_NAME_TOKEN_RATIO = 0.25
MIN_NAME_TOKEN_LEN = 4

NAME_WORD_PATTERN = r"[a-z']+"

# Names that are derivatives rather than issuers. A leveraged ETF, a warrant
# or a share class naming its underlying is not independent evidence that the
# name is common -- counting them is why `tesla` scored a document frequency
# of 4 against a ceiling of 3, and TSLA could never be promoted from a bare
# mention.
# A POOLED VEHICLE: something whose name describes a strategy rather than a
# business. One predicate, governing both halves of distinctiveness -- a name
# either contributes its tokens AND counts toward the issuer tally, or does
# neither.
#
# The two have to stay the same set. An earlier version used a broader pattern
# for the tally than for token suppression, and a word appearing only in
# excluded names then looked rare: an ADR kept `depositary` as a distinctive
# token because all 331 names carrying the word were skipped from the
# denominator.
#
# Deliberately narrow. Warrants, units, rights, preferred lines, notes and
# ADRs all stay IN -- an ADR is a real foreign company listing in the US,
# `ATA Creativity Global - American Depositary Shares`, and Chinese and
# Israeli small caps list that way constantly, so suppressing them would cut
# exactly the stocks this board exists to find. `trust` is out too: `Adamas
# Trust, Inc. - Common Stock` is an operating company, as are most REITs.
# Those listings collapse onto their issuer through _issuer_of instead, which
# is where that job belongs.
POOLED_VEHICLE_PATTERN = (
    r'\b(etf|etn|fund|index|portfolio|inverse|bull|bear|\d+x'
    r'|daily target|yield premium|covered call|leveraged)\b')

# Whether a pooled vehicle's own name may promote a bare mention of its
# ticker.
#
# False since 2026-08-23. It was True on the reasoning that an ETF's name
# should vouch for its own symbol, and the live board showed what that costs:
# the entire small-cap section was MAGA and GOP -- `Truth Social America First
# ETF` and `Subversive Congressional Republicans Trading ETF` -- promoted by
# ordinary political posts containing the words `truth social` and
# `republicans`.
#
# A thematic fund is named after a discourse, so its name tokens are the most
# common words in that discourse, and the corroboration runs backwards: for
# `tesla` the word is evidence the post concerns the company; for
# `republicans` it is evidence the post does not concern the fund.
#
# Funds remain reachable by cashtag, which scores directly. A person typing
# the dollar sign means the fund.
FUNDS_PROMOTE_BARE_TOKENS = False


def looks_like_exchange_bot(text):
    """True for machine-generated crypto exchange output.

    Applied on every source. These bots do not post to StockTwits, so the rule
    costs nothing there, and scoping it per source would only invite the
    question of which sources are safe.
    """
    return bool(_EXCHANGE_BOT_RE.search(text or ''))


def single_letter_cashtags_allowed(source):
    return SINGLE_LETTER_CASHTAGS.get(source, False)


def coin_collision_dropped(source, symbol):
    """True when this symbol should be ignored on this source."""
    if COIN_SYMBOLS_MEAN_STOCKS.get(source, False):
        return False
    return symbol in COIN_COLLISION_SYMBOLS


def bare_tokens_allowed(source):
    return BARE_TOKENS_ALLOWED.get(source, False)

# Subreddits to read, from
# docs/superpowers/specs/2026-08-24-radar-subreddit-source-list.md. Tier 1 and
# Tier 2 together, on Michi's call 2026-08-24: measure everything for a few
# days from real stored data, then prune. The alternative was 25-comment
# snapshots, which were too small a sample to decide on -- r/stocks measured
# zero ticker density across 93 comments an hour, which is sampling noise
# rather than truth.
#
# Regional subs are deliberately absent and must stay absent: TSX-V, NSE and
# ASX symbols collide with the US universe exactly the way crypto tickers do
# on /biz/. Single-ticker subs (Superstonk, GME, amcstock) likewise -- they
# discover nothing and would pin one symbol at a permanent maximum.
REDDIT_SUBS = (
    # Tier 1, core volume
    'wallstreetbets', 'stocks', 'Daytrading', 'StockMarket', 'pennystocks',
    'options', 'smallstreetbets', 'shortsqueeze', 'SPACs',
    # Tier 2, narrower
    'RobinHoodPennyStocks', 'wallstreetbetsOGs', 'Wallstreetbetsnew',
    'thetagang', 'swingtrading', 'Vitards', 'Biotechplays', 'weedstocks',
    'UraniumSqueeze',
)

# Feeds read per cycle. The cycle is three minutes at the fastest cadence, so
# four is roughly one request every forty-five seconds -- deliberately below
# the rate that earned a sustained 429 during measurement. Eighteen subs
# therefore come round about every fourteen minutes, which is honest rather
# than complete: r/wallstreetbets turns its 25-entry feed over in under two
# minutes, so most of its comments will be missed and its buckets will say
# `truncated`. Raise this only after watching for 429s in the daemon log.
REDDIT_SUBS_PER_CYCLE = 3

# Reddit runs on its OWN clock, not the market-session cycle.
#
# The ingest cycle stretches to 1800s overnight because chatter follows the
# session -- which is right for the sources it was built for and wrong here.
# Measured 2026-08-24: four subs per 30-minute cycle meant a full rotation of
# eighteen took over two hours, and r/wallstreetbets turns its 25-entry feed
# over in under two minutes. Six hours of that produced ONE scorable mention.
#
# Reddit does not stop at the closing bell, and what a slow poll misses is
# gone rather than late -- there is no cursor to catch up from.
REDDIT_INTERVAL_SECONDS = 120

# Bounds for this source's adaptive cadence. The scheduler's defaults are
# StockTwits-shaped (15 min to 4 h) and its floor alone would lose most of
# r/wallstreetbets. The floor is what a busy sub gets; the ceiling is where a
# silent one -- or a throttled one -- ends up.
REDDIT_MIN_POLL = dt.timedelta(seconds=90)
REDDIT_MAX_POLL = dt.timedelta(minutes=45)

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

# How long a price snapshot is worth keeping. The longest window the board or
# the panel ever measures a move across is 24h, so a week is generous; what
# the number cannot do is decide on its own which rows go, because
# `price_status` reads a ticker's most recent STALE_QUOTE_POLLS snapshots
# whenever they were taken. See retention.prune_quotes.
QUOTE_RETENTION_DAYS = 7

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
    """A stable 16-char stamp for everything that decides what gets counted.

    Sorted before hashing so reordering a list is not a config change -- only
    membership is. Stamped onto every bucket; baselines are computed only over
    buckets sharing the current stamp, so a change starts a warm-up instead of
    reading straight through a discontinuity (spec 6.6).

    THE EXTRACTION RULES ARE PART OF THIS, and were not until 2026-08-22. The
    stamp hashed the source list alone, so the bare-token rule, the coin
    collisions, the A$AP boundary and the uppercase-cashtag fix all shipped
    without invalidating baselines built under the previous rules -- silently
    mixing populations, which is the exact failure the stamp exists to
    prevent. It was giving false assurance rather than protection.

    What belongs here is anything that changes WHICH mentions get counted.
    Thresholds that change how a count is SCORED do not: rescoring re-reads
    the same buckets, so there is no discontinuity to warm up from.

    This versions what is INGESTED. The UI source selector is a read-time
    filter and must never touch it, or every toggle of a checkbox would look
    like a market-wide spike.
    """
    payload = json.dumps({
        'sources': sorted(SOURCES),
        'bare': dict(sorted(BARE_TOKENS_ALLOWED.items())),
        'single_letter': dict(sorted(SINGLE_LETTER_CASHTAGS.items())),
        'coin_symbols': sorted(COIN_COLLISION_SYMBOLS),
        'coin_means_stocks': dict(sorted(COIN_SYMBOLS_MEAN_STOCKS.items())),
        'stopwords': sorted(STOPWORDS),
        'cashtag_re': CASHTAG_PATTERN,
        'bare_re': BARE_PATTERN,
        'bot_re': _EXCHANGE_BOT_RE.pattern,
        'name_df': [MAX_NAME_TOKEN_DF, MAX_NAME_TOKEN_RATIO,
                    MIN_NAME_TOKEN_LEN],
        # Every subreddit shares the source name `reddit`, so adding or
        # dropping one changes which mentions are counted under it while the
        # source list stays identical. Exactly the false assurance the
        # extraction rules gave before 2026-08-22.
        'reddit_subs': sorted(REDDIT_SUBS),
        'pooled_re': POOLED_VEHICLE_PATTERN,
        # The PATTERN alone was not enough: this flag changes what the same
        # pattern is used FOR, so flipping it changed which mentions were
        # counted while leaving the stamp identical.
        'fund_tokens': FUNDS_PROMOTE_BARE_TOKENS,
    }, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


# Negative-binomial dispersion bounds. variance = mu + mu**2 / k, so a large k
# approaches Poisson and a small k allows heavy bursting.
#
# The UPPER bound is the one doing work. Dispersion is estimated over buckets
# that exclude known spikes, which makes the sample look calmer than the world
# is and biases k upward -- and a k that is too high shrinks the variance,
# inflates every z, produces more spikes, excludes more buckets, and biases k
# further. The clamp keeps that from running away.
K_MIN = 0.5
K_MAX = 50.0
K_DEFAULT = 5.0

# Below this many usable buckets, per-ticker dispersion is noise.
K_MIN_OBSERVATIONS = 20

# Floor under the variance, so a near-zero expectation cannot divide to
# infinity.
VARIANCE_FLOOR = 0.25


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


# Eligibility floor (spec 6.3). Three gates, each closing a hole the others
# cannot see: volume alone is meaningless at low counts, one account can supply
# any volume, and fifty accounts can paste one message.
MIN_MENTIONS = 5
MIN_DISTINCT_AUTHORS = 3

# Distinct CHANNELS a broadcast source needs, against MIN_DISTINCT_AUTHORS for
# a forum. Two rather than three because there are orders of magnitude fewer
# channels than authors, and a symbol reaching two independent channels is
# already the rarer event.
MIN_DISTINCT_CHANNELS = 2


# Segment groups. `Small` is what "penny stocks and unknown stuff" means in
# the segment vocabulary -- anything that is not large or mid.
#
# A GROUP, not a sixth segment: universe.segment_for still returns exactly one
# of the five and every row still reports its own, so the counts keep summing
# to the total. `unknown` is folded in on an assumption worth naming -- it
# means no market cap is known, not that the cap is small -- and it holds
# because a ticker no provider has profiled is overwhelmingly a tiny one. If
# `unknown` ever stops being dominated by small names, this is what to revisit.
SEGMENT_GROUPS = {
    'small': ('micro', 'unknown', 'recent_ipo'),
}

# What the board opens on. It is a discovery radar for the things nobody has
# heard of; opening on everything buries them under megacap chatter.
DEFAULT_SEGMENT = 'small'


def segments_in(selection):
    """The concrete segments a selection covers, or () for everything."""
    if selection is None:
        return ()
    return SEGMENT_GROUPS.get(selection, (selection,))
MIN_DISTINCT_TEXT_RATIO = 0.35

# A window counts as elevated at or above this z.
ELEVATED_Z = 2.0

# Sustained: this many of the last four non-overlapping hours elevated.
SUSTAINED_HOURS_REQUIRED = 3
SUSTAINED_HOURS_CONSIDERED = 4

# Bounded-transform scales for divergence (spec 6.4). K_M is larger because
# mention z-scores run far hotter than price ones -- the whole point of the
# transform is that neither term can swamp the other.
DIVERGENCE_K_MENTION = 4.0
DIVERGENCE_K_PRICE = 2.0

# Below this fractional move, a price counts as flat for the direction mark.
FLAT_MOVE = 0.005

# Floor under volatility, so a never-moving stock cannot divide to infinity.
MIN_SIGMA = 0.001


# Consecutive polls with an identical (quote_ts, volume) pair before a tape
# counts as frozen. Two could be one slow second; three is a pattern.
#
# On the current provider volume is always null, so in practice this compares
# quote_ts alone -- Finnhub's free quote carries no `v` field, measured.
STALE_QUOTE_POLLS = 3

# Daily closes needed before a volatility estimate means anything.
MIN_CLOSES_FOR_SIGMA = 10

# Trading hours in a session, for scaling a daily sigma to a shorter window.
SESSION_HOURS = 6.5

# Segment boundaries (spec 8.1), in dollars.
LARGE_CAP_FLOOR = 10_000_000_000
MID_CAP_FLOOR = 300_000_000

# A share price below this is treated as micro regardless of reported cap: a
# stale or wrong cap should not put a three-dollar stock in Large.
PENNY_PRICE = 5.00

# A listing younger than this has no baseline worth the name, which is a
# property of the data rather than of the company's size.
RECENT_IPO_DAYS = 365

# Below this many days of history a reading is marked provisional (spec 6.8).
PROVISIONAL_BASELINE_DAYS = 14
