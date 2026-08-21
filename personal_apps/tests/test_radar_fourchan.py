# personal_apps/tests/test_radar_fourchan.py
"""4chan /biz/: narrow, crypto-heavy, useful as corroboration.

Measured at 22.7 posts/hour with 171 ticker mentions across 1450 posts. Thin
for equities once crypto is filtered, but every post carries a poster id, so
the distinct-author gate works -- anonymous is not identity-free (spec 3.6).
"""
import datetime as dt

from features.radar.sources import FetchResult
from features.radar.sources import fourchan


class FakeClient:
    def __init__(self, catalog, threads):
        self.catalog = catalog
        self.threads = threads
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        if path.endswith('catalog.json'):
            return self.catalog
        for number, payload in self.threads.items():
            if path.endswith('/%d.json' % number):
                return payload
        raise fourchan.FourChanGone(path)


BASE = dt.datetime(2026, 8, 21, 14, 0, 0)


def _epoch(when):
    return int(when.replace(tzinfo=dt.timezone.utc).timestamp())


def _post(number, when, com='$ZZA is the play', poster='AbCdEf12'):
    return {'no': number, 'time': _epoch(when), 'com': com, 'id': poster}


def _catalog(entries):
    return [{'page': 1, 'threads': entries}]


def test_thread_posts_become_rawposts():
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE), _post(101, BASE)]}})
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    assert len(result.posts) == 2
    post = result.posts[0]
    assert post.source == 'fourchan'
    assert post.channel == 'biz'
    assert post.external_id == 'fourchan:biz:100'
    assert post.author == 'AbCdEf12'


def test_html_is_stripped_and_entities_decoded():
    """Comments arrive as HTML with <br> and &gt; quoting."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE, com='&gt;buy <b>$ZZA</b><br>now')]}})
    body = fourchan.fetch(BASE - dt.timedelta(hours=1), client).posts[0].body
    assert '<b>' not in body
    assert '&gt;' not in body
    assert '$ZZA' in body


def test_posts_older_than_since_are_dropped():
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE - dt.timedelta(days=2)),
                         _post(101, BASE)]}})
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert [p.external_id for p in result.posts] == ['fourchan:biz:101']


def test_threads_untouched_since_the_cursor_are_not_fetched():
    """The catalog carries last_modified, so an idle thread costs no request.
    At 1 request/second that is the difference between a cycle finishing and
    not."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)},
                  {'no': 200, 'last_modified': _epoch(BASE - dt.timedelta(days=3))}]),
        {100: {'posts': [_post(100, BASE)]},
         200: {'posts': [_post(200, BASE)]}})
    fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert not any('200.json' in call for call in client.calls)


def test_hitting_the_thread_cap_marks_truncated():
    entries = [{'no': n, 'last_modified': _epoch(BASE)} for n in range(60)]
    threads = {n: {'posts': [_post(n, BASE)]} for n in range(60)}
    result = fourchan.fetch(BASE - dt.timedelta(hours=1),
                            FakeClient(_catalog(entries), threads), thread_cap=5)
    assert result.status == 'truncated'
    assert len(result.posts) == 5


def test_an_unreachable_catalog_is_missing():
    class Failing:
        def get_json(self, path):
            raise fourchan.FourChanUnavailable('503')
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), Failing())
    assert result.status == 'missing'
    assert result.posts == []


def test_a_pruned_thread_is_routine_and_not_truncation():
    """Threads are pruned constantly, so one listed in the catalog can be gone
    a second later. That is attrition, not coverage we failed to collect --
    and marking it truncated made every single live cycle truncated, which
    excludes the source from baselines permanently."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)},
                  {'no': 999, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE)]}})
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert len(result.posts) == 1
    assert result.status == 'ok'


def test_a_post_without_a_poster_id_falls_back_to_its_thread():
    """Some boards omit ids. Falling back to the thread keeps distinct-author
    counting conservative rather than crediting every post to one 'anon'."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [{'no': 101, 'time': _epoch(BASE), 'com': '$ZZA'}]}})
    assert fourchan.fetch(BASE - dt.timedelta(hours=1), client).posts[0].author == \
        'thread:100'


def test_a_thread_that_errors_for_real_is_truncation():
    """A 500 is different from a 404: the thread exists and we could not read
    it, so this cycle genuinely undercounted."""
    class Flaky(FakeClient):
        def get_json(self, path):
            if '/999.json' in path:
                raise fourchan.FourChanUnavailable('500 server error')
            return super().get_json(path)

    client = Flaky(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)},
                  {'no': 999, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE)]}})
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert result.status == 'truncated'
    assert len(result.posts) == 1


def test_gone_is_a_kind_of_unavailable():
    """Callers that only care that a request failed still catch one type."""
    assert issubclass(fourchan.FourChanGone, fourchan.FourChanUnavailable)
