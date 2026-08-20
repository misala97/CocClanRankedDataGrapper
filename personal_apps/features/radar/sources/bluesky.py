# personal_apps/features/radar/sources/bluesky.py
"""Bluesky ingest, over the public Jetstream firehose.

No credentials: Jetstream is open, and searchPosts -- the one endpoint that
needs auth -- is not wanted anyway, since search returns a ranked sample where
the firehose returns everything.

Drained in batches rather than held open. Jetstream accepts a cursor in
microseconds, so the daemon reconnects from its last processed timestamp,
catches up, and disconnects on the same schedule as the polling sources.

The cursor clamp is the thing to be careful about. Replay reaches back roughly
36 hours; ask for more and Jetstream returns events from as far back as it has
with no error and no warning. Trusting the connection would mean carrying a
hole while believing the range was covered, which is precisely how a gap turns
into a fake spike (spec 4.5).
"""
import datetime as dt

from . import FetchResult, RawPost

JETSTREAM_URL = ('wss://jetstream2.us-east.bsky.network/subscribe'
                 '?wantedCollections=app.bsky.feed.post')

# How far the first delivered event may sit after the requested cursor before
# it counts as a clamp rather than a quiet moment. The network does ~144k
# posts/hour, so minutes of genuine silence do not happen -- but a batch drain
# only samples the stream, so short gaps between what a cycle happens to catch
# are routine. Real clamps run for hours, not minutes, so this stays far below
# them.
CLAMP_TOLERANCE = dt.timedelta(minutes=5)


class JetstreamUnavailable(Exception):
    """The firehose did not deliver. Never becomes a zero count."""


def _to_raw_post(event):
    commit = event.get('commit') or {}
    record = commit.get('record') or {}
    text = record.get('text') or ''
    if not text:
        return None

    when = dt.datetime.utcfromtimestamp(event['time_us'] / 1_000_000)
    did = event.get('did') or ''
    rkey = commit.get('rkey') or ''

    return RawPost(
        source='bluesky',
        external_id='bluesky:%s:%s' % (did, rkey),
        channel='firehose',
        author=did,
        created_utc=when,
        title=None,
        body=text,
        score=0,
        num_comments=0,
        url='https://bsky.app/profile/%s/post/%s' % (did, rkey),
    )


def fetch(since, drain, budget_seconds=45):
    """Drain the firehose from `since` and normalize what comes back.

    `drain(cursor_us, budget)` is injected so the whole module is testable
    without a network, which spec 10 requires.
    """
    cursor_us = int(since.replace(tzinfo=dt.timezone.utc).timestamp() * 1_000_000)

    try:
        events = list(drain(cursor_us, budget_seconds))
    except JetstreamUnavailable:
        return FetchResult(posts=[], status='missing')

    if not events:
        # At ~144k posts/hour, an empty drain is a broken connection rather
        # than a calm network.
        return FetchResult(posts=[], status='missing')

    posts = []
    for event in events:
        if (event.get('commit') or {}).get('operation') != 'create':
            continue
        post = _to_raw_post(event)
        if post is not None:
            posts.append(post)

    earliest = min(dt.datetime.utcfromtimestamp(e['time_us'] / 1_000_000)
                   for e in events)

    if earliest - since > CLAMP_TOLERANCE:
        # Jetstream gave us less history than we asked for and said nothing.
        return FetchResult(posts=posts, status='truncated', covered_since=earliest)

    return FetchResult(posts=posts, status='ok')


def live_drain(cursor_us, budget_seconds):
    """Connect, replay from the cursor, stop at the budget. Real network."""
    import asyncio
    import json
    import time

    import websockets

    async def _run():
        collected = []
        url = '%s&cursor=%d' % (JETSTREAM_URL, cursor_us)
        started = time.time()
        try:
            async with websockets.connect(url, max_size=None) as socket:
                while time.time() - started < budget_seconds:
                    try:
                        raw = await asyncio.wait_for(socket.recv(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                    try:
                        collected.append(json.loads(raw))
                    except ValueError:
                        continue
        except Exception as exc:
            raise JetstreamUnavailable(str(exc)) from exc
        return collected

    return asyncio.run(_run())
