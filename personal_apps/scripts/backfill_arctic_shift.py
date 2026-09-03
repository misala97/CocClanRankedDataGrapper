"""Backfill Reddit through Arctic Shift, day by day, through the live intake.

Why: the archive holds history and the baselines need 30 days of it, or
every Reddit-heavy ticker spikes for weeks after the switch. Each day of
each subreddit goes through the SAME functions the live cycle uses --
extraction, the journal, the bucket rollup -- so a backfilled bucket is
indistinguishable from a lived one, stamped with the current
source_config_version.

Run on the VPS after the deploy WITH THE DAEMON STOPPED: both sides
floor timestamps to 15-minute buckets, so no time cutoff keeps their
windows apart and two roll_ups on one window would race. The script
refuses --apply while radar_ingest is active.

    cd /root/coc-stats/personal_apps
    systemctl stop radar_ingest
    PYTHONPATH=. /root/coc-stats/venv/bin/python -m scripts.backfill_arctic_shift --apply
    systemctl start radar_ingest

Options: --days N (default POST_RETENTION_DAYS), --subs a,b (default
REDDIT_SUBS), --resume PATH (default scratchpad/arctic_backfill_resume.json),
--pause SECONDS between requests (default 0.2). Without --apply it fetches
and counts, storing nothing. Interrupted? Run it again: the resume file
skips finished days and the unique keys make a repeated day harmless.

One DAY is the unit, across every configured sub at once: the day's
posts are stored sub by sub, then ONE roll_up over the day's mention rows
with the full status map, so every sub gets its zero child rows exactly
as a live cycle writes them, and preserve_parent=True leaves the parent
buckets other sources built alone (the journal only holds 48 h).

Cost: the judge reads only mentions inside its 24 h window, so the last
day's reachable tickers are judged exactly as the live cycle would have
judged them; older days cost no model spend. The nightly prune removes
the journal rows of days older than 48 h the next morning; the buckets
they built stay.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, '.')  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import buckets, ingest, universe  # noqa: E402
from features.radar.config import BUCKET_MINUTES, POST_RETENTION_DAYS, REDDIT_SUBS  # noqa: E402
from features.radar.sources import arctic_shift  # noqa: E402

DEFAULT_RESUME = os.path.join('scratchpad', 'arctic_backfill_resume.json')


def daemon_is_active():
    """True when systemd says radar_ingest is running; False where there is
    no systemd (a dev machine) so the guard never blocks local runs."""
    try:
        done = subprocess.run(['systemctl', 'is-active', '--quiet', 'radar_ingest'],
                              check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def days(start, end):
    """Whole UTC days from `start`'s day to `end`, oldest first; the last
    chunk ends at `end` itself."""
    out = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        nxt = day + dt.timedelta(days=1)
        out.append((day, min(nxt, end)))
        day = nxt
    return out


def load_resume(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding='utf-8') as handle:
        return {tuple(item) for item in json.load(handle)}


def mark_done(path, day_key, sub):
    done = load_resume(path)
    done.add((day_key, sub))          # sub is '*' for a whole day
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(sorted(done), handle)


def _windows(day_start, day_end):
    step = dt.timedelta(minutes=BUCKET_MINUTES)
    start = buckets.bucket_start_for(day_start)
    out = set()
    while start < day_end:
        out.add(start)
        start += step
    return out


def run_day(client, subs, day_start, day_end, lookup, *, apply, pause=0.0):
    """One day across `subs` through the live intake. Returns counts."""
    counts = {'day': day_start.date().isoformat(), 'fetched': 0, 'new_posts': 0,
              'mentions': 0, 'buckets': 0}
    day_rows = []
    for sub in subs:
        raw = []
        for kind in arctic_shift.KINDS:
            items = arctic_shift.page_range(client, sub, kind, day_start, day_end, pause=pause)
            titles = {}
            if kind == 'comments':
                link_ids = [i.get('link_id') for i in items if i.get('link_id')]
                try:
                    titles = (arctic_shift.parent_titles(
                        client, link_ids, retries=arctic_shift.RANGE_RETRIES,
                        pause=pause) if link_ids else {})
                except arctic_shift.ArcticShiftUnavailable:
                    titles = {}
            raw.extend(arctic_shift.to_raw_posts(items, sub, kind, titles))
        counts['fetched'] += len(raw)
        if not apply or not raw:
            continue
        mention_rows, new_count, _intake = ingest._store_mentioning_posts(raw, lookup, day_end)
        db.session.commit()
        counts['new_posts'] += new_count
        day_rows.extend(mention_rows)
    if not apply:
        return counts
    counts['mentions'] = len(day_rows)
    # ONE rollup for the day with EVERY sub countable: the quiet subs get
    # their explicit zero rows, as a live cycle would write them. Parents
    # other sources built for these windows are left as they are.
    counts['buckets'] = buckets.roll_up(
        day_rows, {'reddit:%s' % sub: 'ok' for sub in subs},
        _windows(day_start, day_end), preserve_parent=True)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--apply', action='store_true', help='store; default is a dry run')
    parser.add_argument('--days', type=int, default=POST_RETENTION_DAYS)
    parser.add_argument('--subs', default=','.join(REDDIT_SUBS))
    parser.add_argument('--resume', default=DEFAULT_RESUME)
    parser.add_argument('--pause', type=float, default=0.2)
    args = parser.parse_args(argv)
    if args.apply and daemon_is_active():
        print('radar_ingest is running: stop it first (systemctl stop radar_ingest); '
              'two rollups on one window would race', file=sys.stderr)
        return 2
    subs = [s for s in args.subs.split(',') if s]
    now = dt.datetime.utcnow().replace(microsecond=0)
    start = now - dt.timedelta(days=args.days)
    client = arctic_shift.ArcticShiftClient(
        timeout=arctic_shift.RANGE_TIMEOUT_SECONDS)
    done = load_resume(args.resume) if args.apply else set()
    with app.app_context():
        lookup = universe.load_lookup()
        for day_start, day_end in days(start, now):
            key = day_start.date().isoformat()
            if (key, '*') in done:
                continue
            started = time.perf_counter()
            counts = run_day(client, subs, day_start, day_end, lookup,
                             apply=args.apply, pause=args.pause)
            print('%s  fetched %7d  new posts %6d  mentions %6d  buckets %5d  %.0fs'
                  % (key, counts['fetched'], counts['new_posts'], counts['mentions'],
                     counts['buckets'], time.perf_counter() - started), flush=True)
            if args.apply:
                mark_done(args.resume, key, '*')
    return 0


if __name__ == '__main__':
    sys.exit(main())
