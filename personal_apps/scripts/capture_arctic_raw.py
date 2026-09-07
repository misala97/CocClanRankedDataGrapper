# personal_apps/scripts/capture_arctic_raw.py
"""Capture the raw Reddit stream, unfiltered, so the extractor's rejects exist.

Why: ingest._store_mentioning_posts drops any post without a `high` mention
before writing, so the population the extractor REJECTS has no text anywhere
-- not in radar_posts, not in any export. Every number the project has about
extraction is conditioned on acceptance. This script writes the whole stream
of each configured subreddit for whole UTC days, through the same archive
reader the live cycle uses, mapped to the same RawPost shapes, and filters
nothing. A later pass runs the extractor over it and gets both populations
with their text.

    cd personal_apps && PYTHONPATH=. python -m scripts.capture_arctic_raw --out DIR
    cd personal_apps && PYTHONPATH=. python -m scripts.capture_arctic_raw --out DIR --days 7 --end 2026-09-06

Layout: DIR/<YYYY-MM-DD>/<sub>.jsonl, one RawPost per line plus `kind`
('comments' | 'posts'). Each (day, sub) file is written whole, via a .tmp
rename, and its existence is the resume marker: interrupted? run it again.
Newest day first, so the days that join the labelled rows land first.

MEASUREMENT, not pipeline: nothing here touches the database.
"""
import argparse
import dataclasses
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, '.')  # noqa: E402

from features.radar.config import REDDIT_SUBS  # noqa: E402
from features.radar.sources import arctic_shift  # noqa: E402

DEFAULT_DAYS = 7
DEFAULT_PAUSE = 0.2


def day_chunks(end, days):
    """`days` whole UTC days ending at `end` (a midnight), NEWEST FIRST."""
    end = end.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for offset in range(days):
        stop = end - dt.timedelta(days=offset)
        out.append((stop - dt.timedelta(days=1), stop))
    return out


def _row(raw, kind):
    data = dataclasses.asdict(raw)
    data['created_utc'] = raw.created_utc.isoformat()
    data['kind'] = kind
    return data


def capture_day(client, subs, day_start, day_end, out_dir, *, pause=0.0):
    """One day across `subs`, one file per sub. Returns {sub: count}, with
    None for a sub whose file already existed and was left alone."""
    day_dir = os.path.join(str(out_dir), day_start.date().isoformat())
    os.makedirs(day_dir, exist_ok=True)
    counts = {}
    for sub in subs:
        final = os.path.join(day_dir, '%s.jsonl' % sub)
        tmp = final + '.tmp'
        if os.path.exists(final):
            counts[sub] = None
            continue
        written = 0
        with open(tmp, 'w', encoding='utf-8') as handle:
            for kind in arctic_shift.KINDS:
                items = arctic_shift.page_range(client, sub, kind, day_start, day_end,
                                                pause=pause)
                titles = {}
                if kind == 'comments':
                    link_ids = [i.get('link_id') for i in items if i.get('link_id')]
                    if link_ids:
                        try:
                            titles = arctic_shift.parent_titles(
                                client, link_ids, retries=arctic_shift.RANGE_RETRIES,
                                pause=pause)
                        except arctic_shift.ArcticShiftUnavailable:
                            titles = {}
                for raw in arctic_shift.to_raw_posts(items, sub, kind, titles):
                    handle.write(json.dumps(_row(raw, kind), ensure_ascii=False) + '\n')
                    written += 1
        os.replace(tmp, final)
        counts[sub] = written
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True, help='directory for DIR/<day>/<sub>.jsonl')
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS)
    parser.add_argument('--end', default=None,
                        help='YYYY-MM-DD midnight UTC the window ends at (default: today)')
    parser.add_argument('--subs', default=','.join(REDDIT_SUBS))
    parser.add_argument('--pause', type=float, default=DEFAULT_PAUSE)
    args = parser.parse_args(argv)

    if args.end:
        end = dt.datetime.strptime(args.end, '%Y-%m-%d')
    else:
        end = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    subs = [s for s in args.subs.split(',') if s]
    client = arctic_shift.ArcticShiftClient(timeout=arctic_shift.RANGE_TIMEOUT_SECONDS)

    total = 0
    for day_start, day_end in day_chunks(end, args.days):
        started = time.perf_counter()
        counts = capture_day(client, subs, day_start, day_end, args.out, pause=args.pause)
        fetched = sum(c for c in counts.values() if c)
        skipped = sum(1 for c in counts.values() if c is None)
        total += fetched
        print('%s  items=%d  subs_skipped=%d  %.0fs' % (
            day_start.date().isoformat(), fetched, skipped,
            time.perf_counter() - started), flush=True)
    print('done: %d items written' % total, flush=True)


if __name__ == '__main__':
    main()
