# personal_apps/features/radar/sources/fourchan.py
"""4chan /biz/ ingest.

Public JSON API, no auth. Documented rate limit is 1 request/second, honoured
here -- which is why the catalog's last_modified matters: skipping idle threads
is the difference between a cycle finishing inside its budget and not.

Thin for equities and dominated by crypto, so its value is corroboration: a
ticker loud on both this and another source is a different object from one loud
on either alone (spec 3.6).
"""
import datetime as dt
import html
import re
import time

import requests

from . import FetchResult, RawPost

API_BASE = 'https://a.4cdn.org'
USER_AGENT_DEFAULT = 'personal_apps-radar/0.1 (personal research)'

# Documented courtesy limit.
REQUEST_INTERVAL_SECONDS = 1.0
THREAD_CAP = 30

_TAG_RE = re.compile(r'<[^>]+>')


class FourChanUnavailable(Exception):
    """This request did not arrive. Never becomes a zero count."""


class FourChanGone(FourChanUnavailable):
    """A thread that no longer exists.

    Distinct from unavailable, and the distinction decides whether a cycle is
    `truncated`. Threads are pruned off the board constantly, so one listed in
    the catalog can be gone a second later -- that is normal attrition, not
    coverage we failed to collect, and its posts are gone from the board too.

    Treating it as a failure marked every single cycle truncated, and
    truncated buckets are excluded from baselines, so the source would have
    collected data forever without ever becoming scoreable.
    """


class FourChanClient:
    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=25):
        self._headers = {'User-Agent': user_agent}
        self._timeout = timeout

    def get_json(self, path):
        try:
            response = requests.get(API_BASE + path, headers=self._headers,
                                    timeout=self._timeout)
            if response.status_code == 404:
                raise FourChanGone(path)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise FourChanUnavailable('%s: %s' % (path, exc)) from exc


def _clean(comment):
    """Comments are HTML: <br> line breaks, <a> quote links, &gt; greentext."""
    if not comment:
        return ''
    return html.unescape(_TAG_RE.sub(' ', comment)).strip()


def _to_raw_post(post, thread_no, board):
    when = dt.datetime.utcfromtimestamp(post['time'])
    body = '%s %s' % (_clean(post.get('sub')), _clean(post.get('com')))

    return RawPost(
        source='fourchan',
        external_id='fourchan:%s:%d' % (board, post['no']),
        channel=board,
        # Poster ids are per-thread and per-day, which is exactly the identity
        # the distinct-author gate wants. Without one, crediting the thread is
        # conservative -- it cannot inflate the author count.
        author=post.get('id') or ('thread:%d' % thread_no),
        created_utc=when,
        title=_clean(post.get('sub')) or None,
        body=body.strip(),
        score=0,
        num_comments=0,
        url='https://boards.4chan.org/%s/thread/%d#p%d' % (board, thread_no, post['no']),
    )


def fetch(since, client, board='biz', thread_cap=THREAD_CAP, pause=0.0):
    """Posts newer than `since` from threads active since then."""
    try:
        catalog = client.get_json('/%s/catalog.json' % board)
    except FourChanUnavailable:
        return FetchResult(posts=[], status='missing')

    entries = [t for page in catalog for t in (page.get('threads') or [])]
    cutoff = since.replace(tzinfo=dt.timezone.utc).timestamp()
    active = [t for t in entries if (t.get('last_modified') or 0) >= cutoff]
    active.sort(key=lambda t: t.get('last_modified', 0), reverse=True)

    capped = len(active) > thread_cap
    posts, failures, pruned = [], 0, 0

    for entry in active[:thread_cap]:
        try:
            thread = client.get_json('/%s/thread/%d.json' % (board, entry['no']))
        except FourChanGone:
            # Pruned between the catalog and now. Routine, and not an
            # undercount -- those posts are gone from the board as well.
            pruned += 1
            continue
        except FourChanUnavailable:
            # A real failure: the thread exists and we could not read it.
            failures += 1
            continue
        for post in thread.get('posts', []):
            raw = _to_raw_post(post, entry['no'], board)
            if raw.created_utc > since:
                posts.append(raw)
        if pause:
            time.sleep(pause)

    status = 'truncated' if (capped or failures) else 'ok'
    return FetchResult(posts=posts, status=status, catchup_depth=len(active[:thread_cap]))
