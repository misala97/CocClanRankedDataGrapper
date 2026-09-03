"""Reddit through Arctic Shift, the open archive with a public API.

WHY NOT REDDIT ITSELF. The anonymous feed path (reddit.py) gets one feed per
~100 s for every subreddit together, the 25 newest comments of whichever sub
is due -- a few percent of r/wallstreetbets alone. Reddit's own API needs a
manual approval that takes weeks and may not come. The archive returns the
whole comment and post stream per subreddit, paged by time, 5-10 minutes
behind, ~120k requests an hour allowed. Measured 2026-09-02: ~1,700
comments/hour over the configured subs against ~140 mentions/hour from all
three sources before.

WHAT STAYS THE SAME. Posts come out under the existing `reddit:<sub>` names
with the RSS path's shapes -- `/u/<name>` authors, `t1_`/`t3_` fullnames as
external ids, comment titles `'/u/<author> on <parent title>'` -- so the
forum gate, the finance-native bare tokens, the author rules, the comment
splitting and the phrasing all apply unchanged, and the switch dedupes
against what RSS stored.

CURSORS. One per (sub, kind), the newest created_utc accepted; the archive's
`after` is exclusive at whole-second granularity, so every request asks from
`cursor - 1` and ids dedupe the overlap. One shared watermark would starve
the quiet subs behind the busy one (reddit.py:185-191).
"""
import collections
import datetime as dt
import time

import requests

from . import FetchResult, RawPost
from .reddit import _roll_up
from ..config import (ARCTIC_SHIFT_COLD_START, ARCTIC_SHIFT_MAX_PAGES,
                      ARCTIC_SHIFT_PAGE_SIZE)

API_BASE = 'https://arctic-shift.photon-reddit.com/api'
USER_AGENT_DEFAULT = 'personal_apps-radar/0.1 (personal research)'
REDDIT_BASE = 'https://www.reddit.com'
TITLE_MAX = 512                      # RadarPost.title is String(512)
UNKNOWN_PARENT = '[thread unavailable]'
IDS_PER_CALL = 100
KINDS = ('comments', 'posts')
_EPOCH = dt.datetime(1970, 1, 1)


class ArcticShiftUnavailable(Exception):
    """The archive did not answer usefully for one request."""


class ArcticShiftThrottled(ArcticShiftUnavailable):
    """HTTP 429: the host is throttling us; nothing more this cycle."""


class ArcticShiftClient:
    """Index-free, key-free: GET a search path with query params."""

    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=30):
        self._session = requests.Session()
        self._session.headers['User-Agent'] = user_agent
        self._timeout = timeout

    def get_json(self, path, params):
        try:
            response = self._session.get(API_BASE + path, params=params,
                                         timeout=self._timeout)
        except requests.RequestException as exc:
            raise ArcticShiftUnavailable(f'{path}: {exc}') from exc
        if response.status_code == 429:
            raise ArcticShiftThrottled(f'{path}: HTTP 429')
        if not response.ok:
            raise ArcticShiftUnavailable(f'{path}: HTTP {response.status_code}')
        try:
            payload = response.json()
        except ValueError as exc:
            raise ArcticShiftUnavailable(f'{path}: not JSON') from exc
        data = payload.get('data') if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []


# ---- time --------------------------------------------------------------------

def _epoch(when):
    return int((when - _EPOCH).total_seconds())


def _naive_utc(epoch):
    return dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc).replace(tzinfo=None)


# ---- mapping -----------------------------------------------------------------

def _author(item):
    name = item.get('author')
    if not name or name == '[deleted]':
        return None
    return '/u/%s' % name


def _clip(title):
    return title if len(title) <= TITLE_MAX else title[:TITLE_MAX]


def to_raw_posts(items, sub, kind, titles):
    """RawPosts in the RSS path's shapes. `titles` maps t3_ fullnames to
    parent titles (comments need them for their synthetic title)."""
    out = []
    for item in items:
        created = item.get('created_utc')
        if created is None:
            continue
        ident = item.get('id')
        author = _author(item)
        permalink = item.get('permalink') or ''
        if kind == 'comments':
            handle = author or '/u/[deleted]'
            parent = titles.get(item.get('link_id') or '', '') or UNKNOWN_PARENT
            out.append(RawPost(
                source='reddit:%s' % sub,
                external_id=item.get('name') or 't1_%s' % ident,
                channel=sub,
                author=author,
                created_utc=_naive_utc(created),
                title=_clip('%s on %s' % (handle, parent)),
                body=item.get('body') or '',
                score=int(item.get('score') or 0),
                num_comments=0,
                url=REDDIT_BASE + permalink,
            ))
        else:
            out.append(RawPost(
                source='reddit:%s' % sub,
                external_id=item.get('name') or 't3_%s' % ident,
                channel=sub,
                author=author,
                created_utc=_naive_utc(created),
                title=_clip(item.get('title') or '') or None,
                body=item.get('selftext') or '',
                score=int(item.get('score') or 0),
                num_comments=int(item.get('num_comments') or 0),
                url=REDDIT_BASE + permalink,
            ))
    return out


# ---- parent titles -----------------------------------------------------------

# t3 fullname -> title, for the life of the process. Bounded: a day of
# r/wallstreetbets is a few thousand threads; the cache is cleared when it
# passes the cap rather than evicted, which is fine for a lookup this cheap.
_TITLES = {}
_TITLE_CACHE_MAX = 50_000


def reset_title_cache():
    _TITLES.clear()


def parent_titles(client, link_ids):
    """Titles for the given t3_ fullnames, batched, cached. Ids the archive
    does not hold are simply absent from the answer."""
    wanted = [i for i in dict.fromkeys(link_ids) if i and i not in _TITLES]
    for start in range(0, len(wanted), IDS_PER_CALL):
        chunk = wanted[start:start + IDS_PER_CALL]
        for post in client.get_json('/posts/ids', {'ids': ','.join(chunk)}):
            name = post.get('name') or 't3_%s' % post.get('id')
            _TITLES[name] = post.get('title') or ''
    if len(_TITLES) > _TITLE_CACHE_MAX:
        keep = {i: _TITLES[i] for i in link_ids if i in _TITLES}
        _TITLES.clear()
        _TITLES.update(keep)
    return {i: _TITLES[i] for i in link_ids if i in _TITLES}


# ---- paging ------------------------------------------------------------------

def _pages(client, sub, kind, since, *, until=None, max_pages=None,
           page_size=ARCTIC_SHIFT_PAGE_SIZE, pause=0.0):
    """Items with created_utc >= since (and < until when given), ascending,
    deduplicated by fullname across the overlap at each second boundary.
    Returns (items, complete): complete is False when max_pages was hit
    with a page still coming back.

    THE END OF THE RANGE IS AN EMPTY PAGE, not a short one. The API caps a
    numeric `limit` at 100 and answers 'auto' with whatever it feels like
    (~600, probed 2026-09-02), so page length says nothing about whether
    more is waiting. A numeric page_size keeps the short-page shortcut,
    which saves the confirming request the tests script."""
    items, seen = [], set()
    after = _epoch(since) - 1
    pages = 0
    while True:
        params = {'subreddit': sub, 'after': after, 'sort': 'asc', 'limit': page_size}
        if until is not None:
            params['before'] = _epoch(until)
        page = client.get_json('/%s/search' % kind, params)
        pages += 1
        fresh = 0
        for item in page:
            created = item.get('created_utc')
            if created is None or created < _epoch(since):
                continue
            if until is not None and created >= _epoch(until):
                continue
            name = item.get('name') or '%s_%s' % ('t1' if kind == 'comments' else 't3',
                                                  item.get('id'))
            if name in seen:
                continue
            seen.add(name)
            items.append(item)
            fresh += 1
        if not page:
            return items, True
        if isinstance(page_size, int) and len(page) < page_size:
            return items, True
        if max_pages is not None and pages >= max_pages:
            return items, False
        newest = max(int(item['created_utc']) for item in page)
        if newest - 1 <= after and fresh == 0:
            # A whole page inside one second and nothing new: the archive
            # cannot be paged past it with a one-second key. Take what we
            # have rather than loop.
            return items, True
        after = newest - 1
        if pause:
            time.sleep(pause)


def page_range(client, sub, kind, since, until, *, page_size=ARCTIC_SHIFT_PAGE_SIZE,
               pause=0.0):
    """Every item in [since, until), fully paged. The backfill's reader."""
    items, _complete = _pages(client, sub, kind, since, until=until,
                              page_size=page_size, pause=pause)
    return items


# ---- the cycle ---------------------------------------------------------------

def fetch(cursors, client, *, subs, now, max_pages=ARCTIC_SHIFT_MAX_PAGES,
          page_size=ARCTIC_SHIFT_PAGE_SIZE, cold_start=ARCTIC_SHIFT_COLD_START,
          pause=0.0):
    """One cycle over `subs`. Returns (FetchResult, advanced) where
    `advanced` maps (sub, kind) to the newest created_utc accepted -- the
    caller persists it.

    A SUBREDDIT IS ATOMIC. Its posts and both cursor advances are published
    only when both reads (comments, posts) completed as ok or truncated. If
    either fails the sub is `missing`, none of its posts are returned and
    neither cursor moves: run_cycle stores what a fetch returns whatever
    the status says, but journals only countable sources -- so comments
    returned under a missing sub would be stored and never counted while
    an advanced cursor made sure they were never read again.

    A 429 ends the cycle: the archive is one host, so asking the next sub
    would only deepen the throttle, and sleeping cannot recover the work
    -- the radar_reddit job simply asks again in ARCTIC_SHIFT_INTERVAL
    seconds. Subs never asked stay ABSENT from per_source_status (no
    observation, no row), the RSS convention.
    """
    raw_by_sub = collections.defaultdict(list)
    statuses = {}
    advanced = {}
    throttled = False
    for sub in subs:
        if throttled:
            break
        source = 'reddit:%s' % sub
        sub_status = 'ok'
        reads = []
        sub_advanced = {}
        for kind in KINDS:
            since = cursors.get((sub, kind)) or (now - cold_start)
            try:
                items, complete = _pages(client, sub, kind, since, max_pages=max_pages,
                                         page_size=page_size, pause=pause)
            except ArcticShiftThrottled:
                sub_status = 'missing'
                throttled = True
                break
            except ArcticShiftUnavailable:
                sub_status = 'missing'
                break
            if not complete:
                sub_status = 'truncated'
            if items:
                sub_advanced[(sub, kind)] = _naive_utc(
                    max(int(item['created_utc']) for item in items))
            reads.append((kind, items))
        statuses[source] = sub_status
        if sub_status != 'missing':
            raw_by_sub[sub] = reads
            advanced.update(sub_advanced)

    link_ids = [item.get('link_id') for sub_reads in raw_by_sub.values()
                for kind, items in sub_reads if kind == 'comments'
                for item in items if item.get('link_id')]
    try:
        titles = parent_titles(client, link_ids) if link_ids else {}
    except ArcticShiftUnavailable:
        titles = {}          # comments keep the unavailable-thread context

    posts = []
    for sub, sub_reads in raw_by_sub.items():
        for kind, items in sub_reads:
            posts.extend(to_raw_posts(items, sub, kind, titles))

    return (FetchResult(posts=posts, status=_roll_up(list(statuses.values())),
                        per_source_status=statuses),
            advanced)


def probe_subs(client, subs):
    """Subs the archive has nothing for -- a misspelled name answers 200
    and an empty list forever, and an all-zero 'ok' history would build a
    baseline out of nothing. Logged at daemon start, never fatal."""
    silent = []
    for sub in subs:
        try:
            page = client.get_json('/posts/search',
                                   {'subreddit': sub, 'limit': 1, 'sort': 'desc'})
        except ArcticShiftUnavailable:
            continue
        if not page:
            silent.append(sub)
    return silent
