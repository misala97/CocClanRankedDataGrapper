"""Fill the LOCAL dev database with a realistic radar board.

Not deployment tooling and not a fixture the suite uses -- this exists so the
board can be looked at while it is being built. The VPS has real data; this
machine has thirty-one leftover test posts, which is not enough to tell whether
a layout works.

Deliberately writes only the tables the surface reads, and then runs the REAL
scoring pass over them, so expected / variance / mention_z come out of
features/radar/scoring.py rather than being invented here. A seed that hand-
wrote its own z-scores would validate the CSS and nothing else.

    cd personal_apps && PYTHONPATH=. python scratchpad/seed_radar_dev.py
"""
import datetime as dt
import math
import random

import sqlalchemy as sa

from app import app
from extensions import db
from features.radar import scoring
from features.radar.config import source_config_version
from models import (RadarBucketSource, RadarMention, RadarPost, RadarQuote,
                    TickerUniverse)

random.seed(11)

NOW = dt.datetime.now(dt.timezone.utc).replace(
    tzinfo=None, minute=0, second=0, microsecond=0)
HISTORY_DAYS = 32
SOURCES = ('bluesky', 'fourchan')

# (symbol, name, market cap, base rate per bucket, 24h shape, price path)
# The shapes are the four situations the board has to tell apart: a spike that
# just started, one that peaked hours ago, a steady hum, and a ticker whose
# price ran while the talk died down.
PLAN = [
    ('SPY',  'SPDR S&P 500 ETF Trust',     520e9, 0.9, 'spike_late', 'flat'),
    ('TSLA', 'Tesla Inc',                  780e9, 0.7, 'spike_late', 'flat'),
    ('QQQ',  'Invesco QQQ Trust',          290e9, 0.6, 'spike_mid',  'down'),
    ('NVDA', 'NVIDIA Corp',               2900e9, 0.8, 'spike_mid',  'up'),
    ('DIA',  'SPDR Dow Jones Industrial',   38e9, 0.4, 'fade',       'flat'),
    ('NET',  'Cloudflare Inc',              34e9, 0.3, 'spike_late', 'up'),
    ('AAPL', 'Apple Inc',                 3300e9, 0.6, 'steady',     'down'),
    ('WMT',  'Walmart Inc',                760e9, 0.4, 'steady',     'flat'),
    ('MU',   'Micron Technology Inc',        9e9, 0.3, 'fade',       'late_up'),
    ('MSTR', 'Strategy Inc',                 6e9, 0.3, 'fade',       'up'),
    ('AMD',  'Advanced Micro Devices',     240e9, 0.3, 'fade',       'up'),
    ('HOWL', 'Werewolf Therapeutics Inc',  0.11e9, 0.2, 'spike_late', 'frozen'),
    ('SOUN', 'SoundHound AI Inc',          2.1e9, 0.2, 'spike_mid',  'up'),
    ('RIVN', 'Rivian Automotive Inc',        8e9, 0.25, 'steady',    'down'),
]

BULL = ['calls printing', 'bullish setup here', 'loading more, undervalued',
        'breakout confirmed', 'this rips tomorrow']
BEAR = ['puts are free money', 'bearish, overvalued', 'this dumps',
        'bagholders in shambles', 'weak guidance incoming']
FLAT = ['anyone watching this', 'volume looks odd today', 'earnings when',
        'chart looks like a chart', 'holding for now']


def shape_factor(shape, hours_ago):
    """Multiplier on the base rate, as a function of how long ago it was."""
    if shape == 'spike_late':
        return 1 + 11 * math.exp(-(hours_ago ** 2) / 6)
    if shape == 'spike_mid':
        return 1 + 9 * math.exp(-((hours_ago - 7) ** 2) / 10)
    if shape == 'fade':
        return 1 + 7 * math.exp(-((hours_ago - 15) ** 2) / 12)
    return 1.25


def wipe():
    for table in ('radar_mentions', 'radar_posts', 'radar_bucket_sources',
                  'radar_buckets', 'radar_quotes'):
        db.session.execute(sa.text(f'DELETE FROM {table}'))
    db.session.commit()


def seed_universe():
    today = NOW.date()
    for symbol, name, cap, _rate, _shape, _price in PLAN:
        row = TickerUniverse.query.filter_by(symbol=symbol).one_or_none()
        if row is None:
            row = TickerUniverse(symbol=symbol, first_seen=NOW)
            db.session.add(row)
        row.name = name
        row.market_cap = cap
        # Without a sigma there is no price z, and therefore no divergence on
        # any row -- the whole board would read "not scored".
        row.daily_sigma = 0.021
        row.sigma_refreshed_at = NOW
        row.ipo_date = today - dt.timedelta(days=200 if symbol == 'SOUN' else 4000)
    db.session.commit()


def seed_buckets():
    """History first, then the last 24 hours with each ticker's own shape."""
    version = source_config_version()
    start = NOW - dt.timedelta(days=HISTORY_DAYS)
    rows = []

    for symbol, _name, _cap, base, shape, _price in PLAN:
        bucket = start
        while bucket < NOW:
            hours_ago = (NOW - bucket).total_seconds() / 3600
            # A weak time-of-day rhythm, so the hour-of-week profile has
            # something real to learn rather than flat noise.
            local_hour = bucket.hour
            daylight = 0.45 + 0.85 * math.exp(-((local_hour - 16) ** 2) / 40)
            rate = base * daylight
            if hours_ago < 24:
                rate *= shape_factor(shape, hours_ago)

            for source in SOURCES:
                share = 0.72 if source == 'bluesky' else 0.28
                count = poisson(rate * share)
                if count == 0 and random.random() < 0.75:
                    continue
                rows.append({
                    'ticker': symbol, 'bucket_start': bucket, 'source': source,
                    'mention_count': count,
                    'high_confidence_count': max(0, count - (count // 4)),
                    'low_count': 0,
                    'distinct_authors': max(1, min(count, int(count * 0.8) + 1)),
                    'distinct_text_ratio': 0.9,
                    'engagement_weighted_count': float(count),
                    'sentiment_mean': None, 'sentiment_stdev': None,
                    'status': 'ok', 'source_config_version': version,
                    'expected': None, 'variance': None, 'mention_z': None,
                    'baseline_days': None,
                })
            bucket += dt.timedelta(minutes=15)

    db.session.execute(sa.insert(RadarBucketSource), rows)
    db.session.commit()
    return len(rows)


def poisson(mean):
    """Small-mean Poisson draw. Knuth's method is fine at these rates."""
    if mean <= 0:
        return 0
    limit, k, product = math.exp(-mean), 0, 1.0
    while product > limit:
        k += 1
        product *= random.random()
    return k - 1


def seed_posts():
    """Real posts and mentions for the last 24h.

    The board counts distinct authors and splits tone from the mention rows
    themselves, so bucket counts alone would leave both columns empty.
    """
    authors = [f'user{n:03d}' for n in range(90)]
    posts, mentions, external = [], [], 0

    for symbol, _name, _cap, base, shape, _price in PLAN:
        for hours_ago in range(24):
            at = NOW - dt.timedelta(hours=hours_ago, minutes=random.randint(0, 59))
            count = poisson(base * 4 * shape_factor(shape, hours_ago))
            for _ in range(count):
                external += 1
                lean = random.random()
                body, score = ((random.choice(BULL), round(random.uniform(0.2, 0.9), 2))
                               if lean < 0.32 else
                               (random.choice(BEAR), round(-random.uniform(0.2, 0.9), 2))
                               if lean < 0.52 else
                               (random.choice(FLAT), 0.0))
                posts.append({
                    'source': random.choice(SOURCES),
                    'external_id': f'seed-{external}',
                    'channel': 'seed', 'author': random.choice(authors),
                    'created_utc': at, 'title': None,
                    'body': f'${symbol} {body}', 'score': 0, 'num_comments': 0,
                    'url': None, 'simhash': random.getrandbits(63),
                    'first_seen': at, 'last_seen': at,
                })
                mentions.append((external, symbol, score))

    db.session.execute(sa.insert(RadarPost), posts)
    db.session.commit()

    ids = dict(db.session.query(RadarPost.external_id, RadarPost.id).all())
    db.session.execute(sa.insert(RadarMention), [{
        'post_id': ids[f'seed-{ext}'], 'ticker': symbol,
        'confidence': 'high', 'lexicon_sentiment': score, 'llm_sentiment': None,
    } for ext, symbol, score in mentions])
    db.session.commit()
    return len(posts)


def seed_quotes():
    """A quote every five minutes for 24h, per ticker.

    'frozen' repeats one snapshot verbatim, which is what a halted or untraded
    tape looks like -- that is how the no-print mark gets exercised.
    """
    rows = []
    for symbol, _name, _cap, _base, _shape, path in PLAN:
        price = round(random.uniform(18, 240), 2)
        volume = 1_000_000
        for step in range(288):
            at = NOW - dt.timedelta(minutes=5 * (287 - step))
            if path == 'frozen':
                rows.append({'ticker': symbol, 'fetched_at': at,
                             'quote_ts': NOW - dt.timedelta(hours=9),
                             'price': price, 'prev_close': price,
                             'volume': volume})
                continue
            drift = {'flat': 0.00002, 'up': 0.00035, 'down': -0.00030,
                     'late_up': 0.00002}[path]
            if path == 'late_up' and step > 240:
                drift = 0.0013
            price = round(price * (1 + drift + random.uniform(-0.0004, 0.0004)), 2)
            volume += random.randint(500, 5000)
            rows.append({'ticker': symbol, 'fetched_at': at, 'quote_ts': at,
                         'price': price, 'prev_close': price, 'volume': volume})

    db.session.execute(sa.insert(RadarQuote), rows)
    db.session.commit()
    return len(rows)


def main():
    with app.app_context():
        wipe()
        seed_universe()
        buckets = seed_buckets()
        posts = seed_posts()
        quotes = seed_quotes()
        written = {s: scoring.score_source(s, NOW) for s in SOURCES}
        print(f'buckets={buckets} posts={posts} quotes={quotes} scored={written}')


if __name__ == '__main__':
    main()
