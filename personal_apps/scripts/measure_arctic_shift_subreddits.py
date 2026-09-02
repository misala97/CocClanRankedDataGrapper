"""Measure candidate subreddits through Arctic Shift, with the real extractor.

Aggregates only: comments and posts per hour, lag, the share of comments
carrying a ticker, the crypto share, equity mentions per hour, distinct
authors, and the top symbols. Never stores text or author names.

Run from personal_apps/ (needs the universe lookup from the dev DB):
    PYTHONPATH=. python scripts/measure_arctic_shift_subreddits.py [sub ...]
Writes scratchpad/arctic_shift_probe/measurements.jsonl and prints a table.
"""
import collections
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from app import app  # noqa: E402
from features.radar import extraction, universe  # noqa: E402
from features.radar.config import COIN_COLLISION_SYMBOLS  # noqa: E402

BASE = 'https://arctic-shift.photon-reddit.com/api'
USER_AGENT = 'radar-probe/0.1 (personal, measuring subreddit value)'
OUT = pathlib.Path('scratchpad/arctic_shift_probe')

# General stock/trading communities. Regional and thematic ones are measured
# too and flagged; single-ticker subs (Superstonk, GME, amcstock, bbby) are
# out by policy and not listed.
CANDIDATES = [
    # broad US trading / investing
    'wallstreetbets', 'stocks', 'StockMarket', 'investing', 'options',
    'Daytrading', 'smallstreetbets', 'pennystocks', 'Shortsqueeze', 'thetagang',
    'ValueInvesting', 'swingtrading', 'Wallstreetbetsnew', 'WallStreetbetsELITE',
    'wallstreetbets2', 'stonks', 'traders', 'Trading', 'technicalanalysis',
    'StockMarketChat', 'stocktobuytoday', 'StocksAndTrading', 'stockpicks',
    'Stock_Picks', 'UndervaluedStonks', 'Undervalued', 'UnderValuedStocks',
    'DueDiligence', 'DueDiligenceArchive', 'SecurityAnalysis', 'dividends',
    'DividendsPlusGrowth', 'investing_discussion', 'EducatedInvesting',
    'RichTogether', 'InvestmentClub', 'squeezeplays', 'Vitards',
    'RobinHood', 'Webull', 'Fidelity', 'Schwab', 'thinkorswim',
    'FluentInFinance', 'Bogleheads', 'ETFs', 'REITs', 'SPACs', 'IPO',
    # thematic sectors (multi-ticker)
    'biotech_stocks', 'Biotechplays', 'weedstocks', 'EnergyStocks',
    'UraniumSqueeze', 'greeninvestor', 'semiconductor', 'shroomstocks',
    'EVstocks', 'SpaceStocks', 'Gold', 'Silverbugs', 'Wallstreetsilver',
    'pennystock', 'PennyStocksDD', 'pennystocksDD', 'Pennystock_Talk',
    # regional (flagged: other exchanges collide with the US universe)
    'CanadianInvestor', 'Baystreetbets', 'Canadapennystocks', 'ASX_Bets',
    'UKInvesting', 'mauerstrassenwetten', 'Finanzen', 'Aktien',
]

REGIONAL = {'CanadianInvestor', 'Baystreetbets', 'Canadapennystocks', 'ASX_Bets',
            'UKInvesting', 'mauerstrassenwetten', 'Finanzen', 'Aktien'}


def fetch(kind, sub, limit=100):
    url = f'{BASE}/{kind}/search?' + urllib.parse.urlencode(
        {'subreddit': sub, 'limit': limit, 'sort': 'desc'})
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get('data', [])


def rate(items):
    """Items per hour from the newest 100, and the newest item's lag in minutes."""
    if len(items) < 2:
        return 0.0, None
    stamps = [item['created_utc'] for item in items]
    span_h = max((max(stamps) - min(stamps)) / 3600, 1 / 60)
    return len(items) / span_h, (time.time() - max(stamps)) / 60


def score(text, lookup):
    found = extraction.extract_tickers(None, text, lookup, allow_bare=True,
                                       allow_single_letter=False)
    equity, crypto = [], []
    for symbol, _confidence in found:
        (crypto if symbol in COIN_COLLISION_SYMBOLS else equity).append(symbol)
    return equity, crypto


def profile(sub, lookup):
    try:
        comments = fetch('comments', sub)
        time.sleep(0.3)
        posts = fetch('posts', sub)
        time.sleep(0.3)
    except Exception as exc:
        return {'sub': sub, 'skipped': f'{type(exc).__name__}: {str(exc)[:60]}'}
    if len(comments) < 2 and len(posts) < 2:
        return {'sub': sub, 'skipped': 'nothing recent'}
    per_hour, lag = rate(comments)
    posts_per_hour, _ = rate(posts)
    equity = crypto = with_ticker = 0
    symbols = []
    authors = set()
    for comment in comments:
        hits, coins = score(comment.get('body') or '', lookup)
        equity += len(hits)
        crypto += len(coins)
        symbols.extend(hits)
        if hits or coins:
            with_ticker += 1
        if comment.get('author'):
            authors.add(comment['author'])
    n = max(len(comments), 1)
    return {
        'sub': sub,
        'regional': sub in REGIONAL,
        'comments_per_hour': round(per_hour, 1),
        'posts_per_hour': round(posts_per_hour, 1),
        'lag_minutes': round(lag) if lag is not None else None,
        'ticker_share': round(with_ticker / n, 2),
        'crypto_share': round(crypto / max(equity + crypto, 1), 2),
        'equity_per_hour': round(per_hour * (equity / n), 1),
        'distinct_authors': len(authors),
        'top': collections.Counter(symbols).most_common(6),
        'measured_at': dt.datetime.utcnow().isoformat(),
    }


def main(argv):
    subs = argv or CANDIDATES
    OUT.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        lookup = universe.load_lookup()
    rows = []
    with open(OUT / 'measurements.jsonl', 'a', encoding='utf-8') as handle:
        for sub in subs:
            row = profile(sub, lookup)
            rows.append(row)
            handle.write(json.dumps(row) + '\n')
    kept = [r for r in rows if 'skipped' not in r]
    print(f"{'subreddit':22s} {'cmt/h':>6s} {'post/h':>6s} {'lag':>4s} {'tick':>5s} {'crypto':>6s} {'eq/h':>6s} {'auth':>4s}  top")
    for r in sorted(kept, key=lambda r: -r['equity_per_hour']):
        flag = ' R' if r['regional'] else '  '
        top = ' '.join(f'{s}:{c}' for s, c in r['top'][:4])
        print(f"{r['sub']:22s} {r['comments_per_hour']:>6} {r['posts_per_hour']:>6} "
              f"{str(r['lag_minutes']):>4} {r['ticker_share']:>5} {r['crypto_share']:>6} "
              f"{r['equity_per_hour']:>6} {r['distinct_authors']:>4}{flag} {top}")
    for r in rows:
        if 'skipped' in r:
            print(f"{r['sub']:22s} skipped: {r['skipped']}")


if __name__ == '__main__':
    main(sys.argv[1:])
