# personal_apps/features/radar/sources/reddit.py
"""Reddit ingest.

Catch-up pagination walks backwards through /new with `after` until it reaches
items older than `since`. `before` would be wrong here: it returns items NEWER
than the given fullname, so a catch-up loop built on it fetches an empty page
and concludes it is up to date while a squeeze is still being written.

Uses `requests` directly rather than a Reddit client library -- the surface used
is two endpoints and one token grant, and the dependency is not worth it.
"""
import datetime as dt

import requests

from . import FetchResult, RawPost
from ..config import PAGE_CAP, SUBREDDITS

USER_AGENT_DEFAULT = 'personal_apps-radar/0.1'
TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
API_BASE = 'https://oauth.reddit.com'

_DELETED = {'[deleted]', '[removed]'}


class RedditUnavailable(Exception):
    """Any failure that means this cycle did not get the data. Callers turn
    this into a `missing` or `truncated` status -- never into a zero count."""


class RedditClient:
    """OAuth token handling and one listing call.

    Credentials come from the environment: REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD, REDDIT_USER_AGENT.
    """

    def __init__(self, client_id, client_secret, username, password,
                 user_agent=USER_AGENT_DEFAULT, timeout=15):
        self._auth = (client_id, client_secret)
        self._credentials = {'grant_type': 'password',
                             'username': username, 'password': password}
        self._headers = {'User-Agent': user_agent}
        self._timeout = timeout
        self._token = None
        self._token_expires = dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    def _ensure_token(self):
        now = dt.datetime.now(dt.timezone.utc)
        if self._token and now < self._token_expires:
            return
        try:
            response = requests.post(TOKEN_URL, auth=self._auth,
                                     data=self._credentials,
                                     headers=self._headers,
                                     timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RedditUnavailable('token request failed: %s' % exc) from exc

        self._token = payload['access_token']
        # Renew a minute early rather than discovering expiry mid-catch-up.
        lifetime = int(payload.get('expires_in', 3600)) - 60
        self._token_expires = now + dt.timedelta(seconds=max(lifetime, 60))

    def get_listing(self, path, params):
        self._ensure_token()
        headers = dict(self._headers)
        headers['Authorization'] = 'Bearer %s' % self._token
        try:
            response = requests.get(API_BASE + path, params=params,
                                    headers=headers, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RedditUnavailable('listing %s failed: %s' % (path, exc)) from exc


def _clean(value):
    """Reddit writes '[deleted]' into the field rather than clearing it."""
    if value is None:
        return None
    return None if value in _DELETED else value


def _to_raw_post(child):
    kind = child['kind']
    data = child['data']
    body = data.get('selftext') if kind == 't3' else data.get('body')
    body = _clean(body) or ''

    return RawPost(
        source='reddit',
        external_id=data.get('name') or '%s_%s' % (kind, data['id']),
        channel=data.get('subreddit') or '',
        author=_clean(data.get('author')),
        created_utc=dt.datetime.utcfromtimestamp(float(data['created_utc'])),
        title=_clean(data.get('title')) if kind == 't3' else None,
        body=body,
        score=int(data.get('score') or 0),
        num_comments=int(data.get('num_comments') or 0),
        url='https://www.reddit.com%s' % (data.get('permalink') or ''),
    )


def _fetch_one(client, path, since, page_cap):
    """Walk one listing backwards until items predate `since`.

    Returns (posts, hit_cap). Raises RedditUnavailable if the listing could
    not be read at all.
    """
    posts = []
    after = None
    for depth in range(page_cap):
        params = {'limit': 100, 'raw_json': 1}
        if after is not None:
            params['after'] = after

        payload = client.get_listing(path, params)
        data = payload.get('data') or {}
        children = data.get('children') or []
        if not children:
            return posts, False, depth + 1

        caught_up = False
        for child in children:
            post = _to_raw_post(child)
            if post.created_utc <= since:
                caught_up = True
                continue
            posts.append(post)

        after = data.get('after')
        if caught_up or after is None:
            return posts, False, depth + 1

    return posts, True, page_cap


def fetch(since, client, subreddits=SUBREDDITS, kinds=('new', 'comments'),
          page_cap=PAGE_CAP):
    """Everything posted after `since` across the configured subreddits.

    status is the worst outcome across all listings walked:
      - every listing complete            -> 'ok'
      - any listing capped, or any single listing unreadable while others
        succeeded                          -> 'truncated'
      - nothing readable at all            -> 'missing'
    """
    posts = []
    deepest = 0
    capped = False
    failures = 0
    attempts = 0

    for subreddit in subreddits:
        for kind in kinds:
            attempts += 1
            path = '/r/%s/%s' % (subreddit, kind)
            try:
                found, hit_cap, depth = _fetch_one(client, path, since, page_cap)
            except RedditUnavailable:
                failures += 1
                continue
            posts.extend(found)
            deepest = max(deepest, depth)
            capped = capped or hit_cap

    if failures == attempts:
        return FetchResult(posts=[], status='missing', catchup_depth=0)

    status = 'truncated' if (capped or failures) else 'ok'
    return FetchResult(posts=posts, status=status, catchup_depth=deepest)
