# personal_apps/features/radar/config.py
"""Radar tunables.

Everything here is configuration in the sense that changing it changes what
gets ingested -- which is exactly why the source list and the extraction rules
are hashed into a version stamped onto every bucket. Baselines are computed
only over buckets sharing the current version, so adding a source starts a
warm-up instead of reading straight through the discontinuity (spec 6.6). The
SUBREDDIT list is the one exception, since 2026-09-02: each `reddit:<sub>` is
its own population, so a new sub warms up alone and must not restart everyone
else's baseline. Which READER produced them (REDDIT_FETCHER) is hashed.
"""
import datetime as dt
import hashlib
import json
import os
import re

# Active sources. Adding one is a module in sources/ plus an entry here --
# nothing else in the pipeline names a source (spec 8.6).
SOURCES = ('bluesky', 'fourchan', 'reddit')

# Statuses a score may be written onto. This is deliberately not the same
# policy used to build baselines: `truncated` counts are real but incomplete,
# so they are worth ranking but not a description of normal. Keep this here,
# rather than in scoring, so rollup, scoring, and one-shot repair code cannot
# drift onto different definitions without introducing an import cycle.
SCOREABLE_STATUSES = frozenset({'ok', 'truncated'})

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
    # A finance subreddit is finance-native the way /biz/ is: `AAPL` without a
    # dollar sign is a ticker there in a way it is not on a general network.
    # Measured 2026-08-24, the junk this admits is the same
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
# company. Finance-native populations are the exception -- and since StockTwits
# was retired 2026-08-26 there are none, so every symbol in
# COIN_COLLISION_SYMBOLS is now dropped on every live source. That costs 49
# real tickers their mentions, which is the price of not putting Chainlink
# chatter under Interlink Electronics.
#
# Kept as a map rather than collapsed to a constant: Telegram is the next
# source and will need its own entry, and the extension point is the point.
COIN_SYMBOLS_MEAN_STOCKS = {
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
    'bluesky': 'forum',
    'fourchan': 'forum',
    # Comments carry real distinct authors, so the forum gate applies
    # unchanged -- unlike a broadcast channel, where one admin is every voice.
    'reddit': 'forum',
}


def source_root(source):
    """The policy-bearing part of a source name.

    Reddit carries its subreddit -- `reddit:wallstreetbets` -- so that one
    sub's feed rolling over between polls marks its own buckets truncated and
    not every other sub's. Before 2026-08-26 they shared one name and one
    status, and with REDDIT_SUBS_PER_CYCLE = 1 that meant whichever sub the
    cycle happened to read decided the status of all of them. In production
    that was 4372 truncated rows against 478 ok.

    The policy must NOT split with the name. An unlisted sub inherits Reddit's
    judgements rather than falling through to the strict default, which would
    silently disable bare tokens on a source that has nothing else.
    """
    return source.split(':', 1)[0]


def source_kind(source):
    """'forum' or 'broadcast'. Unknown sources are treated as forums.

    The strict direction: forum is the tighter gate, so a source nobody has
    characterised is judged by the harder standard rather than waved through.
    """
    return SOURCE_KIND.get(source_root(source), 'forum')


# Single-letter cashtags. `$M`, `$B`, `$T` and `$K` are money shorthand far
# more often than Macy's, Barnes Group, AT&T and Kellanova -- measured on live
# Bluesky, 119 of 3302 cashtag matches were single letters and essentially all
# of them were prose: "Tax @60% for over a $M", "make $B's", "is $B & can be
# $T if we all do it". A finance-native population is the exception, the same
# judgement bare tokens and coin collisions already get.
SINGLE_LETTER_CASHTAGS = {
    'fourchan': False,
    'bluesky': False,
}

# Automated feeds, not people. A machine restating a template every few
# seconds is ONE publisher however many tickers it names, so it is dropped
# whole rather than symbol by symbol -- and per-symbol rules would have to
# enumerate a list that changes weekly.
#
# Crypto exchange bots, prolific on general networks:
#   "$485.6K $PUMP LONG liquidated on Binance @ $0.0048"
#   "$H ARB 5.77% OKX -> BinanceF #arbitrage"
#
# Sports results, found 2026-08-25 as the top discarded symbol left after the
# junk-class stopwords shipped:
#   "FIP GOLD BELGRADE  Qualifying - Male - 1  B. Levchuk/Z. Meireles def ..."
# That is the International Padel Federation -- FIP the federation, GOLD a
# tournament tier -- at 3025 mentions a week from one account. A stopword was
# the wrong instrument: global, and it would have cost Barrick Gold and FTAI
# Infrastructure their bare mentions everywhere to silence one feed.
#
# Matched on the vocabulary of the FORMAT, which is what stays constant.
#
# DEFINED 2026-08-22 AND CALLED BY NOTHING until 2026-08-25, while being
# hashed into source_config_version the whole time -- so the stamp claimed it
# was policy while it had no effect. A defect shaped like an absence, which is
# why there is now an ingest test asserting the call actually happens.
_BOT_FEED_RE = re.compile(
    r'liquidated on\b|\bOKX\b|\bBinanceF\b|#arbitrage\b|vs\. Bitcoin\b'
    r'|\bFIP (?:GOLD|SILVER|BRONZE|PLATINUM|STAR)\b'
    r'|\bQualifying - (?:Male|Female)\b',
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


def looks_like_bot_feed(text):
    """True for machine-generated crypto exchange output.

    Applied on every source. A source these bots never touch pays nothing for
    the check, and scoping it per source would only invite the question of
    which sources are safe.
    """
    return bool(_BOT_FEED_RE.search(text or ''))


def single_letter_cashtags_allowed(source):
    return SINGLE_LETTER_CASHTAGS.get(source_root(source), False)


def coin_collision_dropped(source, symbol):
    """True when this symbol should be ignored on this source."""
    if COIN_SYMBOLS_MEAN_STOCKS.get(source_root(source), False):
        return False
    return symbol in COIN_COLLISION_SYMBOLS


def bare_tokens_allowed(source):
    return BARE_TOKENS_ALLOWED.get(source_root(source), False)


# What an UNCORROBORATED bare token is worth, per source. Measured 2026-08-25
# by sampling what the extractor actually threw away, live, on each source:
#
#   bluesky   0 of 25 discards were real tickers. CNH is a Brazilian driving
#             licence, HQ is comics, EU is the Portuguese word "I".
#   reddit   14 of 15 were real -- NVDA three times, plus AIXI, AMST, APRE,
#             CAST, CODX, DKS, GITS, GPUS, INHD, OLOX, SWVL. The one miss was
#             GPT, in a sentence about Claude and ChatGPT.
#
# Same rule, opposite populations. Reddit comments do not use cashtag
# notation, so a bare token is the only form they have and the corroboration
# path -- a DIFFERENT author cashtagging the same ticker inside 15 minutes --
# essentially never fires. The rule was discarding an entire source.
#
# `low` is the default on purpose: a new source has to opt in, or a general
# network quietly inherits a stock forum's rules.
BARE_TOKEN_CONFIDENCE = {
    'reddit': 'high',
}


def bare_token_confidence(source):
    return BARE_TOKEN_CONFIDENCE.get(source_root(source), 'low')


# Extractor hygiene (extractor-feedback spec §5.2): posts authored by
# Reddit's automation are not human chatter and are dropped BEFORE
# extraction. Exact normalized comparison only -- '/u/AutoModeratorFan'
# is a person. Reddit root only: an unrelated network's display name may
# legitimately be anything. Hashed into source_config_version because
# membership changes what gets counted.
AUTOMATED_AUTHORS = frozenset({'automoderator'})


def _extraction_input_version():
    """extraction.EXTRACTION_INPUT_VERSION, imported at call time.

    extraction imports this module at its top, so the dependency cannot
    run the other way at module level -- the same cycle-avoidance the
    journal/buckets pair documents.
    """
    from . import extraction
    return extraction.EXTRACTION_INPUT_VERSION


def is_automated_author(source, author):
    """True when this author is Reddit's automation, in any of the three
    upstream spellings (AutoModerator, u/AutoModerator, /u/AutoModerator),
    case-insensitively. Never substring matching."""
    if source_root(source) != 'reddit' or not author:
        return False
    normalized = author.strip().lower()
    for prefix in ('/u/', 'u/'):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized in AUTOMATED_AUTHORS

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
# Pruned from eighteen to eight on 2026-08-25, after seven hours of measured
# contribution -- see scripts/measure_subreddit_value.py, which produced every
# number below. The budget is ~30 feed requests an hour for ALL subreddits
# combined, so this list is a spending decision, not a taste one.
#
# KEPT, with mentions per feed actually RECEIVED (demand ran to 67/hour, so
# each sub got about 45% of what it asked for):
#
#   shortsqueeze     28.6  HTZ, RZLV, GOSS, GRRR -- micro-caps, the target
#   pennystocks      25.0  XELB, BMEA, APRE, AIXI -- likewise
#   thetagang        11.2  liquid large caps, exactly as the spec predicted,
#                          but real tickers at 1.85 feeds/hour
#   weedstocks        4.3  sector micro-caps
#   options           4.0
#   smallstreetbets   3.9
#   swingtrading      3.5
#   wallstreetbets    2.7  47% of ALL reddit volume on its own, and SNDK, AUR
#                          and CRSR are discovery names rather than megacaps
#
# CUT, and why:
#
#   Daytrading    7.84 feeds/hr for TP, RSI, ES, SMB -- take-profit, relative
#                 strength index, E-mini futures, a broker. Not companies. The
#                 remainder was QQQ, SPY and IWM. The most expensive junk here.
#   stocks        9.44 feeds/hr for NATO, GE, VOO, QQQ, VXUS, NKE. Index funds
#                 and megacaps: the source-list spec's own news-reposter test,
#                 failing exactly as written.
#   StockMarket   IQ, SSD, EWC, VTI, SCHD. Cheap, and still only ETFs.
#   SPACs         one mention in seven hours.
#   RobinHoodPennyStocks, wallstreetbetsOGs, Wallstreetbetsnew, Vitards,
#   Biotechplays, UraniumSqueeze -- zero mentions between them in seven hours.
#
# Frees 19.6 feeds/hour. Demand drops 67.3 to 47.7 and r/wallstreetbets moves
# from a 3.4-minute poll to 2.4, against a feed that turns over every 1.8.
#
# THAT CUT WAS A SPENDING DECISION AND THE BUDGET IS GONE (2026-09-02). Under
# REDDIT_FETCHER='arctic_shift' a subreddit costs a couple of requests per
# cycle out of ~120k an hour, so the subs cut for cost above are back and the
# list is a taste decision again: general trading communities only,
# single-ticker and regional subs still out. Re-measured through the archive
# with the real extractor (scripts/measure_arctic_shift_subreddits.py).
#
# Not hashed into source_config_version since 2026-09-02: each `reddit:<sub>`
# is its own population, a new sub warms up alone. And note run_radar_ingest
# retires the dropped subs' poll state -- due_symbols filters by source rather
# than by this list, so without that they would keep taking turns forever and
# the cut would be a silent no-op.
REDDIT_SUBS = (
    # The eight the RSS path read, spelled exactly as stored.
    'wallstreetbets', 'pennystocks', 'shortsqueeze', 'thetagang',
    'options', 'smallstreetbets', 'swingtrading', 'weedstocks',
    # Measured through Arctic Shift on 2026-09-02 with the real extractor
    # (scripts/measure_arctic_shift_subreddits.py); general trading
    # communities only, single-ticker subs stay out, regional ones except
    # the German WSB stay out (their symbols collide with the US universe).
    'daytrading', 'stocks', 'valueinvesting', 'trading', 'stockmarket',
    'pennystock', 'stocks_picks', 'wallstreetbetshuzzah', 'futurestrading',
    'schwab', 'optionswheel', 'biotech_stocks', 'technicalanalysis',
    'fidelity', 'webull', 'thinkorswim', 'realdaytrading', 'burryology',
    'shroomstocks', 'uraniumsqueeze', 'spacs', 'spacstocks', 'squeezeplays',
    'biotechplays', 'investing', 'mauerstrassenwetten',
)

# ---- which Reddit reader runs ----------------------------------------------
# 'arctic_shift': the open archive's public API, the full comment and post
# stream per subreddit, 5-10 minutes behind, ~120k requests/hour allowed.
# 'rss': the anonymous feed path this replaced on 2026-09-02 -- one feed per
# ~100 s for every subreddit together, a few percent of the stream. Kept in
# the tree in case the archive goes away; flipping back is this one line.
REDDIT_FETCHER = 'arctic_shift'
ARCTIC_SHIFT_INTERVAL_SECONDS = 300        # the archive lags 5-10 min; 5-min reads are enough
ARCTIC_SHIFT_MAX_PAGES = 3                 # per (sub, kind) per cycle; more = truncated
# 'auto', not a number. Probed 2026-09-02: a NUMERIC limit is rejected above
# 100 ("'limit' must be between 1 and 100"), while 'auto' answers with
# ~600 items a page -- a day of r/wallstreetbets is 12 pages instead of 71.
# The size is then unknown per page, so the reader treats an EMPTY page as
# the end of the range rather than a short one (sources/arctic_shift.py).
ARCTIC_SHIFT_PAGE_SIZE = 'auto'
ARCTIC_SHIFT_COLD_START = dt.timedelta(hours=2)   # same as the root cursor's


# TWO expansions exist, and merging them back into one is a data-loss bug in
# either direction. Read this before "simplifying" them.
#
# Before 2026-08-26 every Reddit observation was stored under the bare name
# `reddit`. Since the split it is stored under `reddit:<sub>`, and that older
# history is still sitting in radar_bucket_sources, radar_posts and
# radar_mention_events -- buckets are retained forever, which is what lets the
# detail chart's 1Y and 3Y spans fill in.
#
# Those old rows are readable for what they COUNTED and unreadable for what
# they SCORED:
#
#   - a mention_count is a raw observation. `reddit` counted 40 mentions in an
#     hour and `reddit:wallstreetbets` counted 12 in another; pooling them is
#     addition, and leaving the older half out draws Reddit's real, still
#     stored contribution as absent -- while Bluesky satisfies the same hour's
#     coverage test, so the gap renders as a measured number rather than as a
#     gap. That is an absence presented as a zero, which is the one thing this
#     surface may never do.
#
#   - an expected/variance/mention_z is relative to a BASELINE, and the old
#     rows carry the previous source_config_version. "All of Reddit" and
#     "r/pennystocks" are different populations; admitting the old stamp to a
#     scored read mixes two baselines into one z. That is what the stamp bump
#     exists to prevent.
#
# So: `expand_sources` for anything that reads a score, and
# `expand_sources_for_history` for anything that reads a count, a status or a
# timestamp. Neither is a superset that can stand in for the other.


def expand_sources(names):
    """Concrete stored source names for a root-level selection.

    STRICT -- this generation's names only. `reddit` means every configured
    subreddit, because that is what the UI chip and the daemon source list
    promise; a concrete subreddit stays concrete; and the pre-split root
    `reddit` is deliberately NOT included, because rows written under it were
    baselined against a different population.

    For scored reads and for scoring itself: leaderboard.build_rows,
    board._triplets, detail_panel.window_figures, scoring.pooled_z /
    window_z, run_radar_ingest.score_all.
    """
    out = []
    for name in names:
        if name == 'reddit':
            out.extend('reddit:%s' % sub for sub in REDDIT_SUBS)
        else:
            out.append(name)
    return out


def expand_sources_for_history(names):
    """`expand_sources` plus the pre-split root name it deliberately drops.

    For raw-count reads, which have no baseline dependency and so may see the
    whole of what was actually observed: board._covered_hours / _hourly_counts
    / _tones, detail.daily_counts / intraday_counts / first_watched_day /
    _watched_from_index, detail_panel.breakdown_for / _posts,
    journal.distinct_voices.

    Only for a ROOT selection. A reader who asked for one subreddit gets that
    subreddit, and the undifferentiated pre-split history is not it.
    """
    out = expand_sources(names)
    if 'reddit' in names:
        # Appended, not prepended: the order of an IN (...) list is
        # irrelevant to the query and this keeps the strict expansion's
        # ordering stable for anything that compares the two.
        out.append('reddit')
    return out

# Feeds read per cycle. The cycle is three minutes at the fastest cadence, so
# four is roughly one request every forty-five seconds -- deliberately below
# the rate that earned a sustained 429 during measurement. Eighteen subs
# therefore come round about every fourteen minutes, which is honest rather
# than complete: r/wallstreetbets turns its 25-entry feed over in under two
# minutes, so most of its comments will be missed and its buckets will say
# `truncated`. Raise this only after watching for 429s in the daemon log.
# One, because one is the entire budget. Measured against the live endpoint
# on the VPS 2026-08-25: `x-ratelimit-remaining` reads 0.0 after a single
# request, and successes landed at t=0, t=78 and t=198 seconds against
# refusals at t=19 and t=138 -- alternating, whichever subreddit was asked.
#
# Asking for three meant one answer and two 429s, and the 429 broke the cycle,
# so Reddit ran at roughly a third of even this budget from the day it
# shipped. Not hashed into source_config_version: cadence changes how much of
# a subreddit is seen, not which mentions count, and the per-source `truncated`
# status is what records the coverage honestly.
REDDIT_SUBS_PER_CYCLE = 1

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
REDDIT_INTERVAL_SECONDS = 120  # ~1 feed/window, matching the measured budget

# Bounds for this source's adaptive cadence. The scheduler's module defaults
# (15 min to 4 h) do not fit here, and the floor alone would lose most of
# r/wallstreetbets. The floor is what a busy sub gets; the ceiling is where a
# silent one -- or a throttled one -- ends up.
REDDIT_MIN_POLL = dt.timedelta(seconds=90)
# Six hours, raised from 45 minutes on 2026-08-25.
#
# The ceiling was starving the subreddits that matter. Measured live: two
# hours produced 179 mentions across 92 tickers and exactly ONE bucket cleared
# the eligibility floor. interval_for_rate already sizes each interval so the
# 25-entry feed cannot roll over, but clamping the result at 45 minutes meant
# a subreddit producing 0.07 comments an hour was polled 1.33 times an hour --
# nineteen polls per comment -- while r/wallstreetbets, which needs one every
# 1.8 minutes to keep up, fought seventeen near-dead subreddits for the same
# thirty feeds an hour.
#
# Safe because SAFETY_FACTOR is 0.5, so a sub is pinned here only when its
# rate is below 12.5/6 = 2.08 comments an hour -- and at that rate its feed
# takes twelve hours to fill, twice the interval. Nothing pinned can lose a
# comment. Subs above it are unaffected: r/stocks at 67/hour asks for eleven
# minutes and gets eleven minutes, ceiling or no ceiling.
REDDIT_MAX_POLL = dt.timedelta(hours=6)

# 15-minute grain. Fine enough for the 1h window in spec 6.9, coarse enough
# that a forever-retained table stays small.
BUCKET_MINUTES = 15

POST_RETENTION_DAYS = 30

# How long the mention journal is kept. Buckets are the durable artifact; the
# journal exists only so a bucket can be rebuilt while cycles are still
# arriving in it. Two days is generous against a catch-up after an outage --
# what it must outlast is the deepest cursor rewind, not the retention of
# anything the board reads.
MENTION_EVENT_RETENTION_HOURS = 48

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
    # --- Junk CLASSES, from seven days of live data measured 2026-08-25 -----
    #
    # The top thirty tickers by mention volume contained no company at all,
    # and roughly a sixth of the SCORED set was these. What is added below is
    # named classes rather than the individual collisions each of them
    # produced -- the distinction that keeps this from being another round of
    # the one-off patching the extraction rethink exists to stop.
    #
    # Each entry costs its ticker bare matches in posts that do not name the
    # company. It keeps every cashtag, and since 2026-08-25 it also keeps
    # every post carrying a distinctive word from the ticker's own name, so
    # Medtronic, Deere, Intercontinental Exchange, Permian Resources and Owens
    # Corning stay reachable in any post that is actually about them.

    # Timezones. Measured: CDT 3591, PDT 1966, MDT 1469, ET 1380, BST 1146
    # over seven days. Added as the whole family rather than the five that
    # happened to surface, because the class is closed and known.
    'CDT', 'PDT', 'MDT', 'EDT', 'EST', 'CST', 'MST', 'PST', 'ET', 'BST',
    'CET', 'GMT', 'UTC',

    # Countries, regions and cities. Measured: UK 4652, DC 2346, EU 2340,
    # DE 1885, NYC 1153.
    'UK', 'EU', 'DE', 'DC', 'NYC',

    # Government agencies, political movements and news organisations. These
    # are the ones that reached the SCORED set: MAGA 256, ICE 315, GOP 210,
    # IA 393. `NWS` is the National Weather Service, whose marine warnings
    # post continuously.
    'MAGA', 'GOP', 'ICE', 'IA', 'BBC', 'NWS',

    # Ordinary words and abbreviations, same class as the block above this
    # comment and found the same way. PR is public relations, OC a county or
    # a character, ST a street, PC a computer, FC a football club.
    'TV', 'LIVE', 'WTF', 'JUST', 'PR', 'OC', 'ST', 'PC', 'HE', 'FC', 'BOT',

    # AI model names in tech discussion. GPT is the Intelligent Alpha Atlas
    # ETF and also the only false positive in the Reddit sample that justified
    # BARE_TOKEN_CONFIDENCE -- "the only reason people use Claude and GPT".
    'GPT',

    # Maritime vessel-tracking identifiers, arriving together at 1676 and 1572
    # a week, which is the signature of a single position-reporting bot rather
    # than of people. A bot filter would be the better instrument; this is the
    # one that exists.
    'AIS', 'MMSI',

    # DELIBERATELY NOT ADDED, though both measured high:
    #
    #   FIP  3025/week, and the top discarded symbol after this list shipped
    #   GOLD arriving in the same posts
    #
    # They are one account: "FIP GOLD BELGRADE  Qualifying - Male - 1 ..." is
    # the International Padel Federation posting tournament results, where FIP
    # is the federation and GOLD is a tournament tier. A stopword is the wrong
    # instrument for one bot -- it is global, and it would cost Barrick Gold
    # and FTAI Infrastructure their bare mentions everywhere to silence a
    # padel feed. looks_like_bot_feed is the right instrument, and as of
    # 2026-08-25 it is wired into ingest and matches this format.
})

# How many bare mentions one cashtagging author may vouch for, inside one
# ticker's 15-minute bucket.
#
# Corroboration exists because a bare token is roughly 85% false positives on
# its own. But a cashtag is ONE person's act of notation, and the confidence
# it lends does not scale with how many strangers typed the same three
# letters. Uncapped, a single $ICE from someone discussing the exchange
# promoted an entire quarter-hour of immigration reporting into the scored
# set, which is how ICE, IA, MAGA and GOP got there.
#
# Four, and expressed as a ratio rather than a fixed number: ten people
# cashtagging in one quarter-hour is a real conversation and should carry more
# bare mentions than one person can, so a flat cap would throttle exactly the
# busy windows the board exists to surface. Over the ratio the promotion is
# refused outright rather than truncated to the first N, because choosing
# WHICH four to promote has no principled answer and the excess is itself the
# evidence that a common word has collided with a ticker.
MAX_BARE_PER_VOUCHER = 4

# Counts written by generation 1 were rebuilt from one cursor slice and lost
# up to 42.9% of the busiest buckets. Generation 2 rebuilds from the complete
# mention journal. Generation 3 (sentiment v2, spec §7.2) excludes events a
# FINAL irrelevant/broadcast judgment disqualified from every rollup and
# rebuild -- a smaller population than generation 2 counted, and tone
# judgments that REMOVE mentions from counts ride this generation, unlike
# judgments that merely rescore them. Hashed because two populations are not
# valid inputs to one baseline, even when the extractor admitted the same
# symbols.
ROLLUP_GENERATION = 3

# Extractor policy generation (extractor-feedback spec §5.3). Bumped when
# WHAT extraction counts changes: generation 1 = canonical input (the
# synthetic Reddit username discarded, parent title split into thread
# context) plus the automated-author drop. A ROLLBACK also increments
# this -- it must never restore an older stamp and mix post-rollback
# observations into the pre-release baseline.
EXTRACTION_POLICY_GENERATION = 1

# Generation 1 stored every subreddit under the aggregate name `reddit`.
# Generation 2 makes the subreddit part of the durable source name. The
# configured roots and subreddit membership stay unchanged across that split,
# so neither existing hash input can express this population discontinuity.
SOURCE_NAME_GENERATION = 2


def price_provider_config():
    """The three validated market-data v2 flags, read at startup.

    ``(us_quote_provider, de_price_mode, us_close_source)``. Defaults keep
    the live behavior exactly; an invalid value refuses startup rather than
    running a half-configured provider, and a close-source of shadow/massive
    without RADAR_MASSIVE_API_KEY refuses too -- a silently dormant close
    source must not look activated [A1][A2].
    """
    us_provider = os.getenv('RADAR_US_PRICE_PROVIDER', 'finnhub')
    de_mode = os.getenv('RADAR_DE_PRICE_MODE', 'legacy')
    close_source = os.getenv('RADAR_US_CLOSE_SOURCE', 'legacy')
    if us_provider not in ('finnhub', 'yahoo'):
        raise RuntimeError(
            f'RADAR_US_PRICE_PROVIDER must be finnhub|yahoo, '
            f'not {us_provider!r}')
    if de_mode not in ('legacy', 'shadow', 'active'):
        raise RuntimeError(
            f'RADAR_DE_PRICE_MODE must be legacy|shadow|active, '
            f'not {de_mode!r}')
    if close_source not in ('legacy', 'shadow', 'massive'):
        raise RuntimeError(
            f'RADAR_US_CLOSE_SOURCE must be legacy|shadow|massive, '
            f'not {close_source!r}')
    if close_source in ('shadow', 'massive') and \
            not os.getenv('RADAR_MASSIVE_API_KEY'):
        raise RuntimeError(
            'RADAR_US_CLOSE_SOURCE=%s requires RADAR_MASSIVE_API_KEY'
            % close_source)
    _validate_close_cleanup_evidence()
    return us_provider, de_mode, close_source


def _validate_close_cleanup_evidence():
    """All three cleanup-evidence settings or none (spec §9.2 [A1]).

    None means cleanup disabled, which is fine; a PARTIAL or malformed set
    refuses startup, because it means the operator believes evidence is
    recorded when retention will treat it as absent.
    """
    import re
    names = ('RADAR_US_CLOSE_ACTIVATED_AT',
             'RADAR_US_CLOSE_GATE_REPORT_SHA256',
             'RADAR_US_CLOSE_GATE_AUDIT_SHA256')
    values = [os.getenv(name) for name in names]
    present = [value for value in values if value]
    if not present:
        return
    if len(present) != len(names):
        raise RuntimeError(
            'US-close cleanup evidence must be all three settings or none: '
            + ', '.join(names))
    activated, report_sha, audit_sha = values
    sha_re = re.compile(r'^[0-9a-f]{64}$')
    if not sha_re.match(report_sha) or not sha_re.match(audit_sha):
        raise RuntimeError('cleanup gate digests must be exact lowercase '
                           'SHA-256 hex')
    try:
        dt.datetime.fromisoformat(activated.replace('Z', '+00:00'))
    except ValueError:
        raise RuntimeError(
            f'RADAR_US_CLOSE_ACTIVATED_AT is not an ISO UTC instant: '
            f'{activated!r}') from None


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
        'bare_confidence': dict(sorted(BARE_TOKEN_CONFIDENCE.items())),
        'single_letter': dict(sorted(SINGLE_LETTER_CASHTAGS.items())),
        'coin_symbols': sorted(COIN_COLLISION_SYMBOLS),
        'coin_means_stocks': dict(sorted(COIN_SYMBOLS_MEAN_STOCKS.items())),
        'stopwords': sorted(STOPWORDS),
        'cashtag_re': CASHTAG_PATTERN,
        'bare_re': BARE_PATTERN,
        'bot_re': _BOT_FEED_RE.pattern,
        'name_df': [MAX_NAME_TOKEN_DF, MAX_NAME_TOKEN_RATIO,
                    MIN_NAME_TOKEN_LEN],
        # Which Reddit reader produced the population: RSS saw a few percent
        # of the stream, Arctic Shift sees all of it. The subreddit LIST is
        # deliberately not hashed (2026-09-02): every reddit:<sub> is its own
        # population and a new sub warms up alone.
        'reddit_fetcher': REDDIT_FETCHER,
        # The same roots and subreddits can still produce a different stored
        # population when the source-name scheme changes.
        'source_name_generation': SOURCE_NAME_GENERATION,
        'pooled_re': POOLED_VEHICLE_PATTERN,
        # The PATTERN alone was not enough: this flag changes what the same
        # pattern is used FOR, so flipping it changed which mentions were
        # counted while leaving the stamp identical.
        'fund_tokens': FUNDS_PROMOTE_BARE_TOKENS,
        # Corroboration decides which bare mentions become scored, so retuning
        # the ceiling mixes populations judged under two different rules
        # inside one baseline unless the stamp moves with it.
        'bare_per_voucher': MAX_BARE_PER_VOUCHER,
        # Extractor policy: stable explicit data, never an incidental
        # function hash (extractor-feedback spec §5.3). The input version
        # is imported lazily because extraction imports this module.
        'extraction_policy_generation': EXTRACTION_POLICY_GENERATION,
        'extraction_input_version': _extraction_input_version(),
        'automated_authors': sorted(AUTOMATED_AUTHORS),
        # Not an extraction rule -- the extractor admits the same symbols
        # either way. What changed is how completely a bucket's count is
        # aggregated (audit 2026-08-26), and that is exactly as valid a
        # reason to start a new baseline as a membership change is.
        'rollup_generation': ROLLUP_GENERATION,
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

# ---- the judge gate ---------------------------------------------------------
# What the model pass reads. Sized on the VPS on 2026-09-02: 1715 tickers were
# judged that day, 96 ever cleared the floor in a 24h window; large + fund
# took 61.5% of the spend, tickers that never reach the board 31.3%, both
# gates together 80.9%. A watched ticker is always read (the reader's mark
# says so); everything else must be outside the skipped segments AND able
# to reach the board -- MIN_MENTIONS mentions from MIN_DISTINCT_AUTHORS
# voices inside JUDGE_FLOOR_HOURS. The text-ratio gate is left out so the
# gate over-admits, never under-admits. 24h because the board's widest
# window is 24h. Not part of source_config_version: the gate changes what is
# judged, not what a mention means.
JUDGE_GATE_ENABLED = True            # False = judge everything, as before
JUDGE_SKIP_SEGMENTS = ('large', 'fund')
JUDGE_FLOOR_HOURS = 24

# ---- the German delayed-data feed's host quota ------------------------------
# Deutsche Börse publishes one file per minute per channel. On 2026-09-01 the
# collector pulled ~520 minute-files in a few hours, the host answered HTTP
# 429 from then on, and the collector kept retrying two files every five
# minutes for 21 hours -- which kept the window full. The board needs one
# snapshot per cycle, not every minute-file, so: newest files first under a
# per-cycle cap, a rolling 24h download budget read from the cycle rows, and
# exponential backoff on 429 for the whole feed (the throttle is per IP).
# German trade history is sampled as a result, about one minute-file in
# five; decided by Michi on 2026-09-02.
DE_FILES_PER_CYCLE = 1                        # per channel, newest first
DE_DOWNLOAD_BUDGET_24H = 300                  # attempted downloads, all channels
DE_THROTTLE_BACKOFF_SECONDS = (1800, 21600)   # first wait, longest wait

# Distinct CHANNELS a broadcast source needs, against MIN_DISTINCT_AUTHORS for
# a forum. Two rather than three because there are orders of magnitude fewer
# channels than authors, and a symbol reaching two independent channels is
# already the rarer event.
MIN_DISTINCT_CHANNELS = 2

# Sentiment v2 review tier (spec 2026-08-31 §5.3). The share is of TODAY'S
# primary judgments, recomputed at each review pass and consumed by
# ATTEMPTED sends (a failed call still spent budget); hitting the ceiling
# is metered, never silent. The contradiction floor is how strong a local
# float must be before disagreeing with the model's attitude flags a
# mention for review.
REVIEW_DAILY_SHARE = 0.10
LOCAL_CONTRADICTION_FLOOR = 0.5


# Segment groups. `Discover` is what "stuff nobody has heard of" means in
# the segment vocabulary -- everything below the large-cap floor, plus the
# rows no provider has profiled.
#
# A GROUP, not a seventh segment: universe.segment_for still returns exactly
# one concrete segment and every row still reports its own, so the counts
# keep summing to the total. `unknown` is folded in on an assumption worth
# naming -- it means no market cap is known, not that the cap is small -- and
# it holds because a ticker no provider has profiled is overwhelmingly a tiny
# one. `recent_ipo` is deliberately NOT in the group: a fresh listing is not
# automatically obscure -- SPCX debuted at $1.9T and sat in the tab meant for
# penny stocks until Michi threw it out (2026-08-31). IPOs keep their own tab.
#
# `small` is the group's pre-2026-08-31 name, kept as an alias because
# bookmarked URLs carry `?segment=small`; resolving it to a literal segment
# nobody has would turn every saved link into an empty board.
_DISCOVER = ('mid', 'micro', 'unknown')
SEGMENT_GROUPS = {
    'discover': _DISCOVER,
    'small': _DISCOVER,
}

# What the board opens on, as the raw query-string value the parser splits.
# It is a discovery radar for the things nobody has heard of; opening on
# everything buries them under megacap chatter. Every member of the group is
# named beside Discover even though the GROUP already covers them: the
# selection drives which tabs read pressed, and a pressed Discover with an
# unpressed Mid would claim mid rows are not being shown while they are.
DEFAULT_SEGMENT = 'discover,mid,micro,unknown'


def segments_in(selection):
    """The concrete segments a selection covers, or () for everything.

    `selection` is one name or several. Several is a UNION, because picking a
    second chip is asking to see MORE -- an intersection of disjoint segments
    is always empty, which would make every multi-selection an empty board.

    Groups expand inside a multi-selection too, so `small` beside `large`
    means all four concrete segments rather than the literal string 'small'.
    Overlaps are collapsed: `small` already contains `micro`, and selecting
    both must not yield a duplicate a caller might count twice.

    Order is deterministic rather than set-iteration order, so a config
    version or a cache key built from this cannot change between runs.
    """
    if selection is None:
        return ()
    if isinstance(selection, str):
        selection = (selection,)

    seen, out = set(), []
    for name in selection:
        for concrete in SEGMENT_GROUPS.get(name, (name,)):
            if concrete not in seen:
                seen.add(concrete)
                out.append(concrete)
    return tuple(out)
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

# ---- scoring write tolerance ------------------------------------------------
# A scoring pass recomputes every row's expected/variance/mention_z, and every
# value moves a little every pass: the profile is normalised over the whole
# window and the prior is a global median, so one new mention anywhere nudges
# every ticker's expectation by ~0.1% (median relative drift 1.5e-3 per pass,
# measured 2026-09-03). Writing 4.5M rows to move each by 0.1% was 15 of a
# 28-minute pass. A row is rewritten only when it moved past these, or when it
# crosses ELEVATED_Z or PROVISIONAL_BASELINE_DAYS -- the two lines anything
# downstream compares against -- or was never scored. Staleness is bounded by
# the tolerance at all times (the comparison is against the STORED value, so
# drift cannot accumulate past it). Simulated on live data: 4.6% of
# r/wallstreetbets rows and 3.9% of r/schwab's write per pass instead of ~100%.
SCORE_WRITE_TOLERANCE_REL = 0.01      # expected and variance, relative
SCORE_WRITE_TOLERANCE_Z = 0.02        # mention_z, absolute
SCORE_WRITE_TOLERANCE_DAYS = 0.25     # baseline_days, absolute
