# personal_apps/features/radar/config.py
"""Radar tunables.

Everything here is configuration in the sense that changing it changes what
gets ingested -- which is exactly why SUBREDDITS is hashed into a version
stamped onto every bucket. Baselines are computed only over buckets sharing the
current version, so adding a subreddit starts a warm-up instead of reading
straight through the discontinuity (spec 6.6).
"""
import hashlib
import json

SUBREDDITS = (
    'wallstreetbets',
    'stocks',
    'options',
    'pennystocks',
    'shortsqueeze',
    'Daytrading',
    'smallstreetbets',
    'SPACs',
)

# 15-minute grain. Fine enough for the 1h window in spec 6.9, coarse enough
# that a forever-retained table stays small.
BUCKET_MINUTES = 15

# Pages of 100 items to walk per subreddit per cycle before giving up and
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
    """
    payload = json.dumps(sorted(SUBREDDITS), separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
