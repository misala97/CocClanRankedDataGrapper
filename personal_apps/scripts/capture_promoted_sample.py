# personal_apps/scripts/capture_promoted_sample.py
"""THROWAWAY SPIKE: raw-text capture for the §8.3 medium-promotion audit.

Low-only posts are never stored, so the retained mention table cannot
produce a complete promoted sample -- the text must be captured LIVE, at
fetch time, before storage decides anything (Codex plan-review finding
9). This spike polls the live sources, records EVERY low-confidence
candidate mention it sees with its raw text, and a later --grade-sheet
pass joins those captures against the journal's promoted flags by
(source, external_id, ticker).

    python -m scripts.capture_promoted_sample --minutes 60
    python -m scripts.capture_promoted_sample --grade-sheet

The grade sheet holds >=100 promoted events plus a same-size
unpromoted-low control from the SAME capture, full raw text, with the
promotion flag hidden from the grading columns -- grade relevance and
human origin blind, then compare. Thresholds change only through a
separately approved design.
"""
import argparse
import csv
import datetime as dt
import json
import os
import random
import sys
import time

sys.path.insert(0, '.')  # noqa: E402

import sqlalchemy as sa  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import extraction, universe  # noqa: E402
from features.radar.config import (  # noqa: E402
    REDDIT_INTERVAL_SECONDS, REDDIT_SUBS, bare_token_confidence,
    bare_tokens_allowed, single_letter_cashtags_allowed)
from features.radar.sources import bluesky as bluesky_source  # noqa: E402
from features.radar.sources import reddit as reddit_source  # noqa: E402
from models import RadarMentionEvent  # noqa: E402

CAPTURE_DIR = os.path.join('scratchpad', 'promoted_sample')
CAPTURE_PATH = os.path.join(CAPTURE_DIR, 'low_candidates.jsonl')
SHEET_PATH = os.path.join(CAPTURE_DIR, 'grade_sheet.csv')
KEY_PATH = os.path.join(CAPTURE_DIR, 'grade_sheet_key.json')
MIN_PROMOTED = 100


def low_candidates(raw, lookup):
    prepared = extraction.prepare_extraction_input(
        raw.source, raw.title, raw.body, author=raw.author,
        channel=raw.channel)
    matches = extraction.extract(
        prepared, lookup,
        allow_bare=bare_tokens_allowed(raw.source),
        allow_single_letter=single_letter_cashtags_allowed(raw.source),
        bare_confidence=bare_token_confidence(raw.source))
    return [(m, prepared) for m in matches if m.confidence == 'low']


def _record(out, raw, match, prepared):
    out.write(json.dumps({
        'captured_at': dt.datetime.utcnow().isoformat(),
        'source': raw.source, 'external_id': raw.external_id,
        'ticker': match.ticker,
        'author_text': prepared.author_text,
        'thread_context': prepared.thread_context,
        'author': raw.author,
    }, ensure_ascii=False) + '\n')


def capture(minutes):
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    with app.app_context():
        lookup = universe.load_lookup()
    deadline = time.time() + minutes * 60
    since = dt.datetime.utcnow() - dt.timedelta(minutes=30)
    reddit_client = reddit_source.RedditClient()
    captured = 0
    with open(CAPTURE_PATH, 'a', encoding='utf-8') as out:
        while time.time() < deadline:
            result = bluesky_source.fetch(since, drain=False)
            for raw in result.posts:
                for match, prepared in low_candidates(raw, lookup):
                    _record(out, raw, match, prepared)
                    captured += 1
            for sub in REDDIT_SUBS[:2]:
                posts, _status, _rate = reddit_source.fetch_one(
                    sub, since, reddit_client)
                for raw in posts:
                    for match, prepared in low_candidates(raw, lookup):
                        _record(out, raw, match, prepared)
                        captured += 1
                time.sleep(REDDIT_INTERVAL_SECONDS)
            out.flush()
            since = dt.datetime.utcnow() - dt.timedelta(minutes=5)
    print('captured %d low candidates -> %s' % (captured, CAPTURE_PATH))
    return 0


def grade_sheet():
    if not os.path.exists(CAPTURE_PATH):
        print('nothing captured yet -- run --minutes first, while '
              'promotion is warm')
        return 1
    rows = {}
    for line in open(CAPTURE_PATH, encoding='utf-8'):
        row = json.loads(line)
        rows[(row['source'], row['external_id'], row['ticker'])] = row

    with app.app_context():
        clauses = [sa.and_(RadarMentionEvent.source == s,
                           RadarMentionEvent.external_id == e,
                           RadarMentionEvent.ticker == t)
                   for s, e, t in list(rows)[:5000]]
        promoted_ids = set()
        if clauses:
            for event in RadarMentionEvent.query.filter(
                    sa.or_(*clauses),
                    RadarMentionEvent.promoted.is_(True)).all():
                promoted_ids.add((event.source, event.external_id,
                                  event.ticker))

    promoted = [rows[key] for key in promoted_ids if key in rows]
    control_pool = [row for key, row in rows.items()
                    if key not in promoted_ids]
    if len(promoted) < MIN_PROMOTED:
        print('only %d promoted captures (< %d) -- keep capturing while '
              'promotion is warm; the 48h journal is the join window'
              % (len(promoted), MIN_PROMOTED))
    random.seed(11)
    control = random.sample(control_pool,
                            min(len(promoted) or 1, len(control_pool)))

    sample = ([dict(row, _kind='promoted') for row in promoted]
              + [dict(row, _kind='control') for row in control])
    random.shuffle(sample)
    with open(SHEET_PATH, 'w', encoding='utf-8', newline='') as out:
        writer = csv.writer(out)
        # BLIND: the promotion flag is NOT a grading column.
        writer.writerow(['n', 'source', 'ticker', 'author_text',
                         'thread_context', 'relevance_grade',
                         'origin_grade'])
        key = []
        for index, row in enumerate(sample, start=1):
            writer.writerow([index, row['source'], row['ticker'],
                             row['author_text'], row['thread_context'],
                             '', ''])
            key.append({'n': index, '_kind': row['_kind'],
                        'external_id': row['external_id']})
    with open(KEY_PATH, 'w', encoding='utf-8') as out:
        json.dump(key, out)
    print('grade sheet: %d rows (%d promoted, %d control) -> %s; the '
          'promoted/control key is SEPARATE in %s -- grade blind first'
          % (len(sample), len(promoted), len(control), SHEET_PATH,
             KEY_PATH))
    return 0


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--minutes', type=int)
    group.add_argument('--grade-sheet', action='store_true')
    args = parser.parse_args()
    if args.grade_sheet:
        return grade_sheet()
    return capture(args.minutes)


if __name__ == '__main__':
    sys.exit(main())
