"""Find and score public Telegram channels worth ingesting.

Adapted from michi's discovery pass. The design is his: search Telegram's own
index rather than trusting published lists, which are affiliate spam that dies
within months, and score candidates on data we need anyway.

TWO DELIBERATE CHANGES FROM THE ORIGINAL

It scores with the REAL extractor -- features.radar.extraction -- rather than a
local copy. The original carried `\\$([A-Za-z]{1,5})` and a bare-token pass, the
pattern this codebase replaced on 2026-08-22 after it matched `$t` inside
"s%$t" and read `$M` as Macy's rather than millions. Scoring a channel with a
looser extractor than the one that will read it selects channels for noise.
The same applies to simhash: fingerprint.simhash64 is what ingest uses.

And its data comes from where this project actually keeps it -- the universe
from MySQL, the stopwords and coin collisions from config -- rather than from
three JSON files under data/, which does not exist here.

RATE
Conservative on purpose. A session created an hour ago making hundreds of
channel lookups is what Telegram's spam heuristics are built to notice, and
this is running on a personal account. Sleeps are long, the candidate cap is
low, and the pass is not urgent.

    cd personal_apps && PYTHONPATH=. python scripts/discover_telegram_sources.py
"""
import asyncio
import collections
import datetime as dt
import json
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel

sys.path.insert(0, os.getcwd())

from app import app                                       # noqa: E402
from features.radar import extraction, fingerprint, universe   # noqa: E402
from features.radar.config import COIN_COLLISION_SYMBOLS       # noqa: E402

SESSION_NAME = 'radar_telegram'
SEEDS = [
    'penny stock', 'small cap stocks', 'OTC stocks', 'stock alerts',
    'premarket movers', 'low float stocks', 'swing trade stocks',
    'day trading stocks',
]
SAMPLE = 200            # messages read per candidate
WINDOW_DAYS = 30
MAX_CANDIDATES = 40     # first-pass cap; raise once the account is warm
SLEEP = 3.0


async def flood_safe(fn, *args, **kwargs):
    while True:
        try:
            return await fn(*args, **kwargs)
        except FloodWaitError as wait:
            print(f'  flood wait {wait.seconds}s')
            await asyncio.sleep(wait.seconds + 5)


def score_text(text, lookup):
    """(equity hits, crypto hits) under the policy Telegram would ingest with.

    bare tokens allowed (a finance-native channel, like /biz/), single-letter
    cashtags rejected ($M is millions here too). Coin-shaped symbols are
    counted rather than dropped, because their SHARE is the thing being
    measured -- a channel that is 80% crypto is the one to reject.
    """
    found = extraction.extract_tickers(None, text, lookup, allow_bare=True,
                                       allow_single_letter=False)
    equity, crypto = [], []
    for symbol, _confidence in found:
        (crypto if symbol in COIN_COLLISION_SYMBOLS else equity).append(symbol)
    return equity, crypto


async def discover(client):
    """Public broadcast channels matching any seed. Search is capped
    server-side and skews large, so coverage comes from more seeds rather than
    a bigger limit."""
    seen = {}
    for seed in SEEDS:
        result = await flood_safe(client, SearchRequest(q=seed, limit=50))
        new = 0
        for chat in result.chats:
            if isinstance(chat, Channel) and chat.broadcast and chat.username:
                if chat.username not in seen:
                    new += 1
                seen[chat.username] = chat
        print(f'  {seed!r}: +{new} (total {len(seen)})')
        await asyncio.sleep(SLEEP)
    return seen


async def profile(client, username, lookup):
    try:
        entity = await flood_safe(client.get_entity, username)
        full = await flood_safe(client, GetFullChannelRequest(entity))
        messages = await flood_safe(client.get_messages, entity, limit=SAMPLE)
    except (ChannelPrivateError, ValueError, TypeError) as exc:
        return {'username': username, 'skipped': type(exc).__name__}
    if not messages:
        return {'username': username, 'skipped': 'no messages'}

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=WINDOW_DAYS)
    recent = [m for m in messages if m.date >= cutoff]
    if not recent:
        return {'username': username, 'skipped': 'nothing in 30d'}

    texts = [m.message or '' for m in recent]
    equity = crypto = with_ticker = 0
    tickers = collections.Counter()
    for text in texts:
        hits, coins = score_text(text, lookup)
        equity += len(hits)
        crypto += len(coins)
        tickers.update(hits)
        if hits or coins:
            with_ticker += 1

    count = len(recent)
    span = max((recent[0].date - recent[-1].date).days, 1)
    return {
        'username': username,
        'title': entity.title,
        'subscribers': full.full_chat.participants_count,
        'msgs_per_day': round(count / span, 2),
        'text_share': round(sum(1 for t in texts if t.strip()) / count, 2),
        'ticker_share': round(with_ticker / count, 2),
        'crypto_share': round(crypto / max(equity + crypto, 1), 2),
        'top_tickers': tickers.most_common(10),
        'hashes': [h for h in (fingerprint.simhash64(t) for t in texts) if h],
    }


def passes(entry):
    return (
        'skipped' not in entry
        and entry['msgs_per_day'] >= 3
        and entry['text_share'] >= 0.5
        and entry['ticker_share'] >= 0.3
        and entry['crypto_share'] <= 0.3
    )


def overlap(left, right):
    """Near-duplicate rate between two channels. High means one operator, or
    straight reposting -- which makes them one voice, not two."""
    if not left:
        return 0.0
    hits = sum(1 for a in left
               if any(bin(a ^ b).count('1') <= 3 for b in right))
    return round(hits / len(left), 2)


async def main():
    load_dotenv(override=True)
    api_id, api_hash = os.getenv('TELEGRAM_API_ID'), os.getenv('TELEGRAM_API_HASH')
    if not api_id or not api_hash:
        raise SystemExit('TELEGRAM_API_ID / TELEGRAM_API_HASH missing from .env')

    with app.app_context():
        lookup = universe.load_lookup()
    print(f'universe: {len(lookup)} symbols')

    async with TelegramClient(SESSION_NAME, int(api_id), api_hash) as client:
        print('searching...')
        candidates = await discover(client)
        shortlist = list(candidates)[:MAX_CANDIDATES]
        print(f'{len(candidates)} public channels found, profiling {len(shortlist)}')

        profiles = []
        for n, username in enumerate(shortlist, 1):
            entry = await profile(client, username, lookup)
            profiles.append(entry)
            flag = entry.get('skipped') or (
                f"{entry['msgs_per_day']}/day tick={entry['ticker_share']} "
                f"crypto={entry['crypto_share']}")
            print(f'  [{n}/{len(shortlist)}] @{username}: {flag}')
            await asyncio.sleep(SLEEP)

        kept = [p for p in profiles if passes(p)]
        for i, a in enumerate(kept):
            for b in kept[i + 1:]:
                rate = overlap(a['hashes'], b['hashes'])
                if rate > 0.4:
                    print(f'OVERLAP @{a["username"]} <-> @{b["username"]}: {rate}')

        for entry in profiles:
            entry.pop('hashes', None)
        with open('telegram_candidates.json', 'w', encoding='utf-8') as handle:
            json.dump({'kept': [p['username'] for p in kept],
                       'profiles': profiles}, handle, indent=2)
        print(f'\n{len(kept)} kept -> telegram_candidates.json')
        for entry in kept:
            print(f'  @{entry["username"]:24s} {entry["subscribers"]:>8} subs  '
                  f'{entry["msgs_per_day"]:>5}/day  {entry["top_tickers"][:5]}')


if __name__ == '__main__':
    asyncio.run(main())
