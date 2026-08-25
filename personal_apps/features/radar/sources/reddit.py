# personal_apps/features/radar/sources/reddit.py
"""Reddit ingest, over the published Atom feeds.

Reddit's JSON API returns 403 without OAuth and app registration at
reddit.com/prefs/apps no longer works, so the keyed route is genuinely closed.
The FEEDS are not: `/r/<sub>/comments/.rss` answers 200 with no auth at all.
Measured 2026-08-24.

WHY COMMENTS AND NOT SUBMISSIONS

Submissions are thin -- r/pennystocks runs about ten a day, because those subs
remove most of what is posted. The talk is in comments, and a large share of it
sits inside one or two pinned daily megathreads. The subreddit-level comments
feed returns those without walking post trees, which is what makes megathreads
free rather than a special case.

TWENTY-FIVE ENTRIES IS THE WHOLE FEED

There is no cursor and no paging. Whatever has happened since the last poll
beyond the newest 25 comments is simply gone. So the poll interval is not a
politeness setting, it is the coverage: r/wallstreetbets turns its feed over
every 1.8 minutes, and a fifteen-minute poll sees an eighth of it.

That is why a feed whose OLDEST entry is newer than the cursor reports
`truncated` -- there was a gap between the two that nobody read, and buckets
built from it must not claim to be complete.

RATE LIMITS ARE THE BINDING CONSTRAINT, NOT VOLUME

Sixteen requests in thirty seconds earned a sustained 429, and the penalty
outlasts the burst by many minutes. So the number of subreddits carried is
limited by the request budget rather than by how interesting they are, and
`fetch` takes the budget as an argument rather than deciding for itself.
"""
import datetime as dt
import re
import time
import xml.etree.ElementTree as ET

import requests

from . import FetchResult, RawPost

FEED = 'https://www.reddit.com/r/{sub}/comments/.rss'
ATOM = {'a': 'http://www.w3.org/2005/Atom'}

# Reddit asks for a descriptive agent naming the project and a contact. A
# browser-shaped one is what gets an IP blocked rather than throttled.
USER_AGENT_DEFAULT = ('personal_apps-radar/0.1 (personal research; '
                      'contact michi7788@googlemail.com)')

# Courtesy gap between feeds inside one cycle. Distinct from the per-subreddit
# poll interval, which decides how often a given sub comes round again.
REQUEST_INTERVAL_SECONDS = 2.0

# What a full feed looks like. Reddit serves the newest 25 comments and offers
# no paging, so a FULL feed is the only case where the window may have rolled
# past the cursor. A shorter one means the subreddit simply had less to say,
# and calling that `truncated` would mark every quiet sub incomplete forever --
# and truncated buckets are excluded from baselines, so those subs would
# collect data indefinitely without ever becoming scoreable.
FEED_LIMIT = 25

_TAG_RE = re.compile(r'<[^>]+>')


class RedditUnavailable(Exception):
    """This request did not arrive. Never becomes a zero count."""


class RedditThrottled(RedditUnavailable):
    """A 429.

    Its own type because it means something different from a network failure:
    the request was understood and refused for rate, so the right response is
    to stop asking this cycle rather than to retry the next subreddit
    immediately and deepen the penalty.
    """


class RedditClient:
    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=20):
        self._headers = {'User-Agent': user_agent}
        self._timeout = timeout

    def get_feed(self, sub):
        """Raw Atom for one subreddit's comments, or raise."""
        try:
            response = requests.get(FEED.format(sub=sub),
                                    headers=self._headers,
                                    timeout=self._timeout)
        except requests.RequestException as exc:
            raise RedditUnavailable(f'r/{sub}: {exc}') from exc

        if response.status_code == 429:
            raise RedditThrottled(f'r/{sub}: 429')
        if not response.ok:
            raise RedditUnavailable(f'r/{sub}: HTTP {response.status_code}')
        return response.text


def _text_of(entry):
    content = entry.findtext('a:content', '', ATOM)
    return ' '.join(_TAG_RE.sub(' ', content).split())


def _stamp(entry):
    raw = entry.findtext('a:updated', '', ATOM)
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(
            raw.replace('Z', '+00:00')).astimezone(dt.timezone.utc).replace(
                tzinfo=None)
    except ValueError:
        return None


def _to_raw_post(entry, sub):
    """One Atom entry as the shape every source produces.

    `score` and `num_comments` are zero because the feed does not carry them.
    Zero rather than None: they are engagement weights, and a comment with no
    reported score genuinely contributed no measured engagement -- unlike a
    mention count, where zero and unknown are different facts.
    """
    author = entry.find('a:author/a:name', ATOM)
    link = entry.find('a:link', ATOM)
    created = _stamp(entry)
    if created is None:
        return None
    return RawPost(
        source='reddit',
        external_id=entry.findtext('a:id', '', ATOM),
        # The subreddit, not 'reddit'. Per-subreddit baselines are not built
        # yet, but every stored comment records which sub it came from, so the
        # decision about which subs are worth keeping can be made from data.
        channel=sub,
        author=author.text if author is not None else None,
        created_utc=created,
        title=entry.findtext('a:title', '', ATOM) or None,
        body=_text_of(entry),
        score=0,
        num_comments=0,
        url=link.get('href') if link is not None else '',
    )


def fetch_one(sub, since, client):
    """(posts, status, observed_rate) for a single subreddit.

    `truncated` where the feed's oldest entry is newer than the cursor: the
    window rolled past between polls and the comments in the gap are gone, so
    the buckets this produces are real but incomplete.
    """
    body = client.get_feed(sub)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RedditUnavailable(f'r/{sub}: unparseable feed: {exc}') from exc

    entries = root.findall('a:entry', ATOM)
    posts = [p for p in (_to_raw_post(e, sub) for e in entries) if p]
    if not posts:
        return [], 'ok', 0.0

    stamps = sorted(p.created_utc for p in posts)
    oldest, newest = stamps[0], stamps[-1]

    # Messages an hour, for the poll scheduler. Measured from the feed itself
    # rather than assumed, which is what lets a quiet sub fall to a slow
    # cadence and hand its budget to a busy one.
    span_hours = max((newest - oldest).total_seconds() / 3600, 1 / 3600)
    rate = len(posts) / span_hours

    status = 'truncated' if len(posts) >= FEED_LIMIT and oldest > since else 'ok'
    return [p for p in posts if p.created_utc > since], status, rate


def fetch(since_by_sub, client, pause=REQUEST_INTERVAL_SECONDS):
    """Every subreddit in `since_by_sub`, each read from its OWN cursor.

    Per subreddit, not per source, and that is the whole point. One shared
    cursor is advanced to the newest comment seen across the batch, so polling
    r/wallstreetbets moves it to seconds ago and every quieter subreddit
    afterwards has its entire feed filtered out as "already seen". Measured
    2026-08-25: six of eight cycles returned nothing at all for that reason.

    `since_by_sub` is already the budgeted, rotated slice -- this module does
    not decide which subreddits are due, because that state belongs to the
    scheduler that the StockTwits path already uses.

    A 429 stops the cycle rather than moving to the next subreddit: the
    penalty is per-IP and asking again immediately deepens it. Whatever was
    collected before the refusal is still returned, because those comments
    were really read.

    `rates` carries ONLY the subreddits actually READ, and it is what the
    caller schedules from. The ones after a throttle were never requested, so
    stamping them as polled would push them down the queue for something that
    never happened to them -- and neither is the throttled one, for the same
    reason: it was refused, not read.

    Reversed 2026-08-25. A throttled sub used to be reported at rate zero, so
    the scheduler read it as silent and backed it off. The response headers
    disproved the reasoning behind that: `x-ratelimit-remaining` is 0.0 after
    a SINGLE request, so the budget is one feed per window and everything
    after the first is refused however long the pause. Whichever sub went
    second took the 429 -- two consecutive runs blamed a different one purely
    on ordering. A 429 is a fact about the budget, never about the subreddit.
    """
    posts, statuses, rates = [], [], {}

    for index, (sub, since) in enumerate(since_by_sub.items()):
        if index and pause:
            time.sleep(pause)
        try:
            found, status, rate = fetch_one(sub, since, client)
        except RedditThrottled:
            # Nothing recorded: it was refused, not read, so it stays due and
            # is retried rather than losing its turn.
            statuses.append('missing')
            break
        except RedditUnavailable:
            # Attempted and learned nothing. Recorded as unknown so it is
            # retried soon -- unlike a throttle, a 500 says nothing about
            # whether the next request will work.
            statuses.append('missing')
            rates[sub] = None
            continue
        posts.extend(found)
        statuses.append(status)
        rates[sub] = rate

    return FetchResult(posts=posts, status=_roll_up(statuses), rates=rates)


def _roll_up(statuses):
    """One status for the cycle, worst-case first.

    `missing` beats `truncated` beats `ok`, because a bucket may only claim
    the completeness of its least complete contributor. Nothing at all is
    `missing` rather than `ok`: a cycle that read no subreddit did not observe
    a quiet period, it observed nothing.
    """
    if not statuses or all(s == 'missing' for s in statuses):
        return 'missing'
    if 'truncated' in statuses or 'missing' in statuses:
        return 'truncated'
    return 'ok'
