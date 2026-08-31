# personal_apps/scripts/capture_unmatched_reddit.py
"""THROWAWAY SPIKE: capture Reddit comments the extractor matches nothing
in, for the §8.2 alias measurement. Raw text at capture time, because
unmatched posts are never stored anywhere else.

Operator-run, budget-aware (one subreddit per pass, the live feed's own
pause), append-only JSONL under scratchpad/. Run it for at least one
full day before grading anything; build the blind reference sample
BEFORE evaluating aliases (spec §8.2).

    python -m scripts.capture_unmatched_reddit --minutes 60
    python -m scripts.capture_unmatched_reddit --summarize

--summarize counts word-boundary candidate-alias hits (Tesla, Google,
lowercase spy, ...) over the capture. Counting is not grading: relevance
and human-origin precision come from the blind protocol, by a human, on
a frozen sample. No alias ships from this script.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

sys.path.insert(0, '.')  # noqa: E402

from app import app  # noqa: E402
from features.radar import extraction, universe  # noqa: E402
from features.radar.config import (  # noqa: E402
    REDDIT_INTERVAL_SECONDS, REDDIT_SUBS, bare_token_confidence,
    bare_tokens_allowed, single_letter_cashtags_allowed)
from features.radar.sources import reddit as reddit_source  # noqa: E402

CAPTURE_DIR = os.path.join('scratchpad', 'unmatched_reddit')
CAPTURE_PATH = os.path.join(CAPTURE_DIR, 'capture.jsonl')

# Explicit per-ticker candidates only -- never every "distinctive"
# universe token (spec §8.2 and the 434-of-1,255 Bluesky collision
# measurement behind it).
ALIAS_CANDIDATES = {
    'TSLA': ('tesla',),
    'GOOGL': ('google',),
    'SPY': ('spy',),
    'HOOD': ('robinhood',),
    'META': ('facebook',),
}


def is_unmatched(raw, lookup):
    """True when the PRODUCTION extractor finds nothing -- the same pure
    functions, never a second implementation."""
    prepared = extraction.prepare_extraction_input(
        raw.source, raw.title, raw.body, author=raw.author,
        channel=raw.channel)
    matches = extraction.extract(
        prepared, lookup,
        allow_bare=bare_tokens_allowed(raw.source),
        allow_single_letter=single_letter_cashtags_allowed(raw.source),
        bare_confidence=bare_token_confidence(raw.source))
    return not matches, prepared


def capture(minutes):
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    with app.app_context():
        lookup = universe.load_lookup()
    client = reddit_source.RedditClient()
    deadline = time.time() + minutes * 60
    since = dt.datetime.utcnow() - dt.timedelta(hours=2)
    captured = 0
    with open(CAPTURE_PATH, 'a', encoding='utf-8') as out:
        while time.time() < deadline:
            for sub in REDDIT_SUBS:
                posts, status, _rate = reddit_source.fetch_one(
                    sub, since, client)
                for raw in posts:
                    unmatched, prepared = is_unmatched(raw, lookup)
                    if not unmatched:
                        continue
                    out.write(json.dumps({
                        'captured_at': dt.datetime.utcnow().isoformat(),
                        'sub': sub, 'source': raw.source,
                        'external_id': raw.external_id,
                        'author_text': prepared.author_text,
                        'thread_context': prepared.thread_context,
                        'is_comment': prepared.is_comment,
                        'created_utc': raw.created_utc.isoformat(),
                    }, ensure_ascii=False) + '\n')
                    captured += 1
                out.flush()
                time.sleep(REDDIT_INTERVAL_SECONDS)
                if time.time() >= deadline:
                    break
    print('captured %d unmatched comments -> %s' % (captured, CAPTURE_PATH))
    return 0


def summarize():
    if not os.path.exists(CAPTURE_PATH):
        print('nothing captured yet')
        return 1
    rows = [json.loads(line)
            for line in open(CAPTURE_PATH, encoding='utf-8')]
    print('%d unmatched comments captured' % len(rows))
    for ticker, aliases in sorted(ALIAS_CANDIDATES.items()):
        for alias in aliases:
            pattern = re.compile(r'\b%s\b' % re.escape(alias), re.IGNORECASE)
            hits = sum(1 for row in rows
                       if pattern.search(row['author_text']))
            print('  %-6s %-10r %d hits in authored text' % (ticker, alias,
                                                             hits))
    print('Counting is not grading: no alias ships without the blind '
          '>=95%% relevance / >=90%% human-chatter measurement on fresh '
          'data (spec §8.2).')
    return 0


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--minutes', type=int)
    group.add_argument('--summarize', action='store_true')
    args = parser.parse_args()
    if args.summarize:
        return summarize()
    return capture(args.minutes)


if __name__ == '__main__':
    sys.exit(main())
