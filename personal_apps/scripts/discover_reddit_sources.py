"""Measure which subreddits are worth ingesting, and how often to poll them.

The Telegram counterpart to this (discover_telegram_sources.py) exists because
guessing at sources wastes a build. The same applies here: raw comment volume
says nothing on its own -- r/wallstreetbets carries 818 comments an hour and
most of them are memes, while r/pennystocks carries 27 and they are about
small caps. What matters is volume TIMES ticker share, minus crypto.

Scored with the real extractor, features.radar.extraction, for the reason the
Telegram script gives: measuring a source with a looser extractor than the one
that will read it selects sources for noise.

WHAT THE FEED IS

Reddit's JSON API returns 403 without OAuth and app registration is closed, but
the published Atom feeds are open and need no auth. `/r/<sub>/comments/.rss`
is the last 25 comments across the whole subreddit.

Twenty-five is the whole feed, so the SPAN of those 25 is what decides poll
cadence: if a sub produces 25 comments in two minutes, polling every ten
minutes misses four fifths of them. That is what `suggested_poll` reports.

RATE LIMITS ARE THE REAL CONSTRAINT

Anonymous feeds throttle hard -- 16 requests in 30 seconds earned a sustained
429 during the first pass. SLEEP is deliberately generous; this runs once.
"""
import argparse
import datetime as dt
import re
import sys
import time
import xml.etree.ElementTree as ET

import requests

sys.path.insert(0, '.')

from app import app                                            # noqa: E402
from features.radar import extraction, universe                # noqa: E402
from features.radar.config import COIN_COLLISION_SYMBOLS       # noqa: E402

# Reddit asks for a descriptive User-Agent naming the project and a contact.
# Anonymous browser-shaped agents are what gets IPs blocked.
USER_AGENT = ('radar/0.1 (personal stock-chatter research; '
              'contact michi7788@googlemail.com)')
NS = {'a': 'http://www.w3.org/2005/Atom'}
SLEEP = 45.0

# Candidates, grouped by why they are here. Being on this list is a question,
# not an answer -- the point of the script is to reject most of them.
CANDIDATES = [
    # small and micro cap, the population the board exists for
    'pennystocks', 'RobinHoodPennyStocks', 'smallstreetbets', 'Shortsqueeze',
    'CanadianPennyStocks', 'UndervaluedStonks', 'microcaps', 'biotech_stocks',
    # general retail trading, high volume and low precision
    'wallstreetbets', 'wallstreetbetsOGs', 'stocks', 'StockMarket',
    'Daytrading', 'swingtrading', 'options', 'thetagang',
    'stockstobuytoday', 'TradingEdge',
    # research and catalysts
    'SPACs', 'Vitards', 'DueDiligenceArchive', 'weedstocks', 'Biotechplays',
    'Wallstreetbetsnew', 'UraniumSqueeze',
    # NOTE: regional subs (CanadianInvestor, ASX_Bets, UKInvesting,
    # IndianStockMarket) were in this list and are deliberately NOT. See
    # docs/superpowers/specs/2026-08-24-radar-subreddit-source-list.md -- they
    # discuss the wrong exchange, and TSX-V / NSE / ASX symbols collide with
    # the US universe exactly the way crypto tickers do on /biz/. A sub can
    # score well here and still be a corruption vector, which is why the list
    # is a judgement and not only a measurement.
    #
    # `investing` is out for a different reason: long horizon, mega-cap and
    # ETFs, so no signal at a day-trading cadence.
]

# Subs devoted to ONE ticker are excluded on purpose and must stay excluded.
# They do not discover anything -- every comment is about the same symbol, so
# they would manufacture a permanent, enormous spike for it and drown the
# board. r/Superstonk, r/GME and r/amcstock are the obvious cases.
SINGLE_TICKER_SUBS = frozenset({'superstonk', 'gme', 'amcstock', 'bbby'})


def fetch(sub, kind='comments'):
    url = f'https://www.reddit.com/r/{sub}/{kind}/.rss'
    return requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=20)


def score_text(text, lookup):
    """(equity hits, crypto hits) under the policy Reddit would ingest with.

    Bare tokens allowed: a finance subreddit is finance-native the way /biz/
    and StockTwits are, so `AAPL` without a dollar sign is a ticker there in a
    way it is not on a general network. Single-letter cashtags rejected -- $M
    is millions here too. Coin-shaped symbols are counted rather than dropped,
    because their SHARE is the thing being measured.
    """
    found = extraction.extract_tickers(None, text, lookup, allow_bare=True,
                                       allow_single_letter=False)
    equity, crypto = [], []
    for symbol, _confidence in found:
        (crypto if symbol in COIN_COLLISION_SYMBOLS else equity).append(symbol)
    return equity, crypto


def profile(sub, lookup):
    response = fetch(sub)
    if response.status_code != 200:
        return {'sub': sub, 'skipped': f'HTTP {response.status_code}'}

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        return {'sub': sub, 'skipped': f'unparseable: {exc}'}

    entries = root.findall('a:entry', NS)
    if len(entries) < 2:
        return {'sub': sub, 'skipped': f'only {len(entries)} entries'}

    stamps = sorted(e.findtext('a:updated', '', NS) for e in entries
                    if e.findtext('a:updated', '', NS))
    first = dt.datetime.fromisoformat(stamps[0].replace('Z', '+00:00'))
    last = dt.datetime.fromisoformat(stamps[-1].replace('Z', '+00:00'))
    minutes = max((last - first).total_seconds() / 60, 0.1)

    equity = crypto = with_ticker = 0
    symbols = []
    authors = set()
    for entry in entries:
        body = ' '.join(re.sub(r'<[^>]+>', ' ',
                               entry.findtext('a:content', '', NS)).split())
        hits, coins = score_text(body, lookup)
        equity += len(hits)
        crypto += len(coins)
        symbols.extend(hits)
        if hits or coins:
            with_ticker += 1
        name = entry.find('a:author/a:name', NS)
        if name is not None and name.text:
            authors.add(name.text)

    per_hour = len(entries) / (minutes / 60)
    counted = collections_count(symbols)
    return {
        'sub': sub,
        'per_hour': round(per_hour, 1),
        'ticker_share': round(with_ticker / len(entries), 2),
        'crypto_share': round(crypto / max(equity + crypto, 1), 2),
        # The figure that actually matters: mentions an hour this sub would
        # contribute, not comments an hour it produces.
        'equity_per_hour': round(per_hour * (equity / len(entries)), 1),
        'distinct_authors': len(authors),
        # 25 entries is the whole feed, so this is how often it must be read
        # to avoid missing comments between polls. Two thirds of the turnover
        # window, floored at 60s to stay inside the rate limit.
        'suggested_poll': max(60, int(minutes * 60 * 0.66)),
        'top': counted[:6],
    }


def collections_count(symbols):
    import collections
    return collections.Counter(symbols).most_common()


def passes(entry):
    """Worth ingesting at all.

    The bar is equity mentions per hour, not comments per hour: a sub that
    talks constantly about nothing tradeable costs requests and contributes
    noise. Crypto-dominated subs are rejected outright -- coin tickers collide
    with live equity symbols and would manufacture fake spikes.
    """
    return ('skipped' not in entry
            and entry['equity_per_hour'] >= 1.0
            and entry['crypto_share'] <= 0.4
            and entry['distinct_authors'] >= 5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sleep', type=float, default=SLEEP,
                        help='seconds between requests; lower risks a 429')
    args = parser.parse_args()

    with app.app_context():
        lookup = universe.load_lookup()
    print(f'universe: {len(lookup)} symbols\n')

    profiles = []
    for n, sub in enumerate(CANDIDATES, 1):
        if sub.lower() in SINGLE_TICKER_SUBS:
            continue
        if n > 1:
            time.sleep(args.sleep)
        entry = profile(sub, lookup)
        profiles.append(entry)
        if 'skipped' in entry:
            print(f'  [{n}/{len(CANDIDATES)}] r/{sub:24} {entry["skipped"]}')
        else:
            print(f'  [{n}/{len(CANDIDATES)}] r/{sub:24} '
                  f'{entry["per_hour"]:>7}/h comments  '
                  f'tick={entry["ticker_share"]:<5} '
                  f'equity={entry["equity_per_hour"]:>6}/h  '
                  f'crypto={entry["crypto_share"]}')

    kept = sorted((p for p in profiles if passes(p)),
                  key=lambda p: -p['equity_per_hour'])
    total = sum(p['equity_per_hour'] for p in kept)

    print(f'\n{len(kept)} subreddits worth ingesting, '
          f'~{total:.0f} equity mentions/hour combined\n')
    print(f'  {"subreddit":26} {"equity/h":>9} {"poll":>7}  top tickers')
    for p in kept:
        print(f'  r/{p["sub"]:24} {p["equity_per_hour"]:>9} '
              f'{p["suggested_poll"]:>6}s  {[t for t, _ in p["top"][:5]]}')

    import json
    with open('reddit_candidates.json', 'w', encoding='utf-8') as handle:
        json.dump({'kept': [p['sub'] for p in kept], 'profiles': profiles},
                  handle, indent=2)
    print('\n-> reddit_candidates.json')


if __name__ == '__main__':
    main()
