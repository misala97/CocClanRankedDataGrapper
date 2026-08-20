# personal_apps/tests/test_radar_reddit_source.py
"""Reddit's 100-item listing is comfortable at rest and far too small during a
squeeze, which is precisely when the data matters. Catch-up pagination is what
stops ingest silently truncating at the worst possible moment, and `truncated`
is what stops the undercount reaching a baseline (spec 4.3, 4.5).

Pagination walks *backwards* through /new using `after`. `before` returns items
NEWER than the given fullname and would loop on an empty page instead of
catching up -- test_pagination_uses_after pins that.
"""
import datetime as dt

from features.radar.sources import FetchResult, RawPost
from features.radar.sources import reddit


class FakeClient:
    """Serves canned listing pages and records the params it was called with."""

    def __init__(self, pages_by_path):
        self.pages_by_path = pages_by_path
        self.calls = []

    def get_listing(self, path, params):
        self.calls.append((path, dict(params)))
        pages = self.pages_by_path.get(path, [])
        after = params.get('after')
        index = 0
        if after is not None:
            index = next(i + 1 for i, page in enumerate(pages)
                         if page['data']['after'] == after)
        if index >= len(pages):
            return {'data': {'children': [], 'after': None}}
        return pages[index]


def _child(kind, ident, created, body='body', author='u1', score=1):
    return {
        'kind': kind,
        'data': {
            'id': ident,
            'name': '%s_%s' % (kind, ident),
            'author': author,
            'created_utc': created.replace(tzinfo=dt.timezone.utc).timestamp(),
            'title': 'a title' if kind == 't3' else None,
            'selftext': body if kind == 't3' else '',
            'body': body if kind == 't1' else '',
            'score': score,
            'num_comments': 0,
            'permalink': '/r/x/comments/%s/' % ident,
            'subreddit': 'wallstreetbets',
        },
    }


def _page(children, after):
    return {'data': {'children': children, 'after': after}}


BASE = dt.datetime(2026, 4, 15, 14, 0, 0)


def test_a_single_page_is_ok():
    client = FakeClient({
        '/r/wallstreetbets/new': [_page([_child('t3', 'a', BASE)], None)],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('new',))
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    assert [p.external_id for p in result.posts] == ['t3_a']


def test_posts_are_normalized_into_rawpost():
    client = FakeClient({
        '/r/wallstreetbets/new': [_page([_child('t3', 'a', BASE, body='GME')], None)],
    })
    post = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                        subreddits=('wallstreetbets',), kinds=('new',)).posts[0]
    assert isinstance(post, RawPost)
    assert post.source == 'reddit'
    assert post.channel == 'wallstreetbets'
    assert post.body == 'GME'
    assert post.created_utc == BASE
    assert post.native_tickers == []
    assert post.native_sentiment is None


def test_pagination_uses_after_and_stops_at_since():
    """Two pages; `since` sits between them, so page 2 is fetched and its
    older items are dropped."""
    newer = _child('t3', 'a', BASE)
    older = _child('t3', 'b', BASE - dt.timedelta(hours=3))
    client = FakeClient({
        '/r/wallstreetbets/new': [
            _page([newer], 't3_a'),
            _page([older], None),
        ],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('new',))
    assert [p.external_id for p in result.posts] == ['t3_a']
    assert result.status == 'ok'
    assert client.calls[1][1]['after'] == 't3_a'
    assert 'before' not in client.calls[1][1]


def test_hitting_the_page_cap_marks_truncated():
    """Every page is full of items newer than `since`, so catch-up never
    completes. The data returned is real but incomplete, and only the status
    records that."""
    pages = [_page([_child('t3', str(i), BASE)], 't3_%d' % i) for i in range(20)]
    client = FakeClient({'/r/wallstreetbets/new': pages})
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('new',),
                          page_cap=3)
    assert result.status == 'truncated'
    assert result.catchup_depth == 3
    assert len(result.posts) == 3


def test_a_client_error_marks_missing_and_returns_no_posts():
    """`missing` must never be expressed as a zero count -- that is the
    baseline poisoning the status column exists to prevent."""
    class Failing:
        def get_listing(self, path, params):
            raise reddit.RedditUnavailable('503')

    result = reddit.fetch(BASE - dt.timedelta(hours=1), Failing(),
                          subreddits=('wallstreetbets',), kinds=('new',))
    assert result.status == 'missing'
    assert result.posts == []


def test_one_subreddit_failing_does_not_lose_the_others():
    class PartlyFailing(FakeClient):
        def get_listing(self, path, params):
            if path.startswith('/r/stocks'):
                raise reddit.RedditUnavailable('503')
            return super().get_listing(path, params)

    client = PartlyFailing({
        '/r/wallstreetbets/new': [_page([_child('t3', 'a', BASE)], None)],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets', 'stocks'), kinds=('new',))
    assert [p.external_id for p in result.posts] == ['t3_a']
    assert result.status == 'truncated'


def test_comments_are_ingested_too():
    """A large share of ticker mentions live in comment threads."""
    client = FakeClient({
        '/r/wallstreetbets/comments': [
            _page([_child('t1', 'c', BASE, body='GME squeeze')], None)],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('comments',))
    assert result.posts[0].external_id == 't1_c'
    assert result.posts[0].title is None
    assert result.posts[0].body == 'GME squeeze'


def test_deleted_bodies_are_normalized_to_empty():
    client = FakeClient({
        '/r/wallstreetbets/new': [
            _page([_child('t3', 'a', BASE, body='[deleted]', author='[deleted]')],
                  None)],
    })
    post = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                        subreddits=('wallstreetbets',), kinds=('new',)).posts[0]
    assert post.body == ''
    assert post.author is None
