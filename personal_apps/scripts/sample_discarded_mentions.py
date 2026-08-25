"""Capture the mentions the extractor throws away, so they can be graded.

This is a MEASUREMENT, not a pipeline. It answers one question before anyone
builds anything: of the bare-token mentions that never reach a score, how many
are real tickers? If a third of them are, a model re-read is a large recall
win and worth the engineering. If two percent are and the rest is ROM, IA and
CC, then the rules are roughly right, the board is thin because the internet
genuinely is not discussing micro-caps, and the answer is more sources rather
than a smarter classifier.

    cd personal_apps && PYTHONPATH=. python scripts/sample_discarded_mentions.py
    cd personal_apps && PYTHONPATH=. python scripts/sample_discarded_mentions.py --source reddit

WHY THIS READS LIVE SOURCES INSTEAD OF THE DATABASE
    It has to. ingest._store_mentioning_posts drops any post that produced no
    `high` mention before writing anything -- deliberately, since keeping them
    would be millions of rows a month of text the leaderboard can never
    surface. So the discarded population has no stored text ANYWHERE, and no
    SQL query can reach it. The `low` rows that do sit in radar_mentions rode
    in on posts that also carried a cashtag, which makes them a biased sample
    of exactly the wrong kind: they are the discards that happened to appear
    beside a confident match.

    Capturing live is the only way to see the real thing.

RUN BOTH SOURCES -- THE ANSWER IS NOT THE SAME ON EACH
    On Bluesky a bare uppercase token is usually an ordinary word, and the
    network is heavily Brazilian, so CNH, HQ and EU are Portuguese rather than
    CNH Industrial, Horizon Quantum and enCore Energy.

    On Reddit the same token is far more likely to be meant: r/wallstreetbets
    writes AAPL, not $AAPL. That is the whole recall complaint, and a Bluesky
    result says nothing about it.

TWO ARMS PER RUN
    discarded  posts the pipeline threw away (no `high`)  -> measures RECALL
    kept       posts the pipeline stored (>=1 `high`)     -> measures PRECISION

    The second arm costs nothing extra and answers the other half of the
    complaint: IA, ICE, MAGA and GOP are roughly 35% of the SCORED set, and
    that number needs a ground truth too.

GRADING
    This script deliberately calls no model. It writes files. Grade them in a
    separate, deliberate step, with a model at least as capable as the one
    that would run in production -- grading Haiku's candidates with Haiku
    measures agreement with itself and nothing else.
"""
import argparse
import datetime as dt
import json
import random

from app import app

from features.radar import ingest, universe
from features.radar.config import REDDIT_SUBS
from features.radar.sources import bluesky, reddit

DEFAULT_SECONDS = 180
DEFAULT_TARGET = 500

# How far back to start a firehose drain. Short: this wants a live slice, not
# a replay, and Jetstream clamps a too-old cursor silently anyway.
LOOKBACK = dt.timedelta(seconds=30)

# How far back to ask each Reddit feed for. The feed holds 25 entries whatever
# is asked, so a wide window simply means none of them are filtered out as
# already-seen -- which is what maximizes the sample per request, and requests
# are the scarce thing here.
REDDIT_LOOKBACK = dt.timedelta(days=1)


def full_text(row):
    """Title and body together -- which is what the extractor actually reads.

    Storing only the body loses the match on Reddit, where the title is the
    parent post's and carries the ticker far more often than the comment does.
    A grader shown a body with no ticker in it cannot judge anything, and the
    first four-row sample this script produced had exactly that defect.
    """
    return ' '.join(part for part in (row.get('title'), row.get('body')) if part)


def context(text, symbol, width=90):
    """The symbol with text either side, for reading at a glance.

    The full text goes in the JSONL; this is only for the human-readable file,
    where a wall of untrimmed posts is unreadable.
    """
    where = text.upper().find(symbol.upper())
    if where < 0:
        return text[:width * 2].replace('\n', ' ')
    start = max(0, where - width)
    end = min(len(text), where + len(symbol) + width)
    clip = text[start:end].replace('\n', ' ')
    return ('...' if start else '') + clip + ('...' if end < len(text) else '')


def classify(raw_posts, lookup):
    """Split extracted mentions into the discarded arm and the kept arm."""
    discarded, kept = [], []
    for raw in raw_posts:
        # The real production policy, imported rather than re-implemented: a
        # sampler measuring a slightly different policy than the daemon would
        # produce a number nobody could act on.
        tickers = ingest._extract_for(raw, lookup)
        if not tickers:
            continue

        stored = any(confidence == 'high' for _, confidence in tickers)
        arm = kept if stored else discarded
        for symbol, confidence in tickers:
            entry = lookup.get(symbol) or {}
            arm.append({
                'arm': 'kept' if stored else 'discarded',
                'ticker': symbol,
                'confidence': confidence,
                'company': entry.get('name'),
                'exchange': entry.get('exchange'),
                'source': raw.source,
                'channel': raw.channel,
                'created_utc': raw.created_utc.isoformat(),
                'url': raw.url,
                'title': raw.title,
                'body': raw.body,
            })

    return discarded, kept


def collect_bluesky(seconds, lookup):
    """One firehose drain, split into the two arms."""
    since = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - LOOKBACK
    result = bluesky.fetch(since, bluesky.live_drain, budget_seconds=seconds)

    if result.status == 'missing':
        raise SystemExit('the firehose delivered nothing -- check the network, '
                         'or set RADAR_FORCE_IPV4=1 if this host advertises '
                         'IPv6 without routing it')

    return classify(result.posts, lookup) + (len(result.posts),)


def collect_reddit(lookup, subs):
    """One pass over every configured subreddit, split into the two arms.

    Paced by the module's own REQUEST_INTERVAL_SECONDS. Sixteen requests in
    thirty seconds earned a sustained 429 on a residential IP, so this is not
    a knob to turn up for a bigger sample -- run it again later instead.
    """
    since = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - REDDIT_LOOKBACK
    client = reddit.RedditClient()
    result = reddit.fetch({sub: since for sub in subs}, client)

    if result.status == 'missing':
        raise SystemExit('every subreddit request failed -- likely throttled; '
                         'wait and run it again')

    return classify(result.posts, lookup) + (len(result.posts),)


def write_files(sample, stem):
    """One JSONL for machines, one text file for reading over coffee."""
    with open(stem + '.jsonl', 'w', encoding='utf-8') as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    with open(stem + '.txt', 'w', encoding='utf-8') as handle:
        for number, row in enumerate(sample, start=1):
            where = row['channel'] if row['source'] == 'reddit' else row['source']
            handle.write('%d. $%s  (%s)  [%s/%s, %s]\n'
                         % (number, row['ticker'], row['company'] or '?',
                            row['arm'], row['confidence'], where))
            handle.write('   %s\n\n'
                         % context(full_text(row), row['ticker']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='bluesky',
                        choices=('bluesky', 'reddit'))
    parser.add_argument('--seconds', type=int, default=DEFAULT_SECONDS,
                        help='bluesky only: how long to drain the firehose')
    parser.add_argument('--target', type=int, default=DEFAULT_TARGET,
                        help='samples to keep per arm')
    parser.add_argument('--out', default='radar_sample',
                        help='output file stem; two files per arm are written')
    args = parser.parse_args()

    with app.app_context():
        lookup = universe.load_lookup()
        if not lookup:
            raise SystemExit('the ticker universe is empty -- run '
                             'scripts/seed_radar_universe.py first')
        print('universe: %s symbols' % format(len(lookup), ','))

        if args.source == 'bluesky':
            print('draining bluesky for %ds...' % args.seconds)
            discarded, kept, posts_seen = collect_bluesky(args.seconds, lookup)
        else:
            print('reading %d subreddits, ~%.0fs at %gs between requests...'
                  % (len(REDDIT_SUBS),
                     len(REDDIT_SUBS) * reddit.REQUEST_INTERVAL_SECONDS,
                     reddit.REQUEST_INTERVAL_SECONDS))
            discarded, kept, posts_seen = collect_reddit(lookup, REDDIT_SUBS)

    print('\nposts seen            %s' % format(posts_seen, ','))
    print('discarded mentions    %s   <- the population in question'
          % format(len(discarded), ','))
    print('kept mentions         %s' % format(len(kept), ','))
    if discarded or kept:
        share = len(discarded) / (len(discarded) + len(kept))
        print('discard rate          %.1f%%' % (100.0 * share))

    for arm, rows in (('discarded', discarded), ('kept', kept)):
        if not rows:
            print('\n%s: nothing captured' % arm)
            continue
        # Sampled uniformly over what was captured, which is one continuous
        # slice rather than a whole day. Time of day changes who is posting,
        # so a slice at 03:00 UTC is not a slice at 15:00.
        sample = random.sample(rows, min(args.target, len(rows)))
        sample.sort(key=lambda row: row['ticker'])
        stem = '%s_%s_%s' % (args.out, args.source, arm)
        write_files(sample, stem)
        print('\n%s: wrote %s samples to %s.jsonl and %s.txt'
              % (arm, format(len(sample), ','), stem, stem))

        counts = {}
        for row in rows:
            counts[row['ticker']] = counts.get(row['ticker'], 0) + 1
        top = sorted(counts.items(), key=lambda pair: -pair[1])[:15]
        print('  top symbols: %s'
              % ', '.join('%s=%d' % (ticker, count) for ticker, count in top))


if __name__ == '__main__':
    main()
