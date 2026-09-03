"""The Arctic Shift reader: mapping, paging, cursors, statuses. Pure -- a
duck-typed fake client, no DB, the way test_radar_reddit.py works."""
import datetime as dt

import pytest

from features.radar.sources import arctic_shift
from features.radar.sources.reddit import _roll_up

NOW = dt.datetime(2027, 1, 4, 12, 45, 0)
EPOCH = dt.datetime(1970, 1, 1)


def epoch(when):
    return int((when - EPOCH).total_seconds())


def comment(ident, when, author='someone', body='ZZA to the moon', link='t3_parent1', score=1):
    return {'id': ident, 'name': f't1_{ident}', 'author': author, 'body': body,
            'created_utc': epoch(when), 'score': score, 'link_id': link,
            'permalink': f'/r/zzarc/comments/parent1/title/{ident}/', 'subreddit': 'zzarc'}


def submission(ident, when, title='ZZA thesis', selftext='long read', score=3, num_comments=2):
    return {'id': ident, 'name': f't3_{ident}', 'author': 'op', 'title': title,
            'selftext': selftext, 'created_utc': epoch(when), 'score': score,
            'num_comments': num_comments, 'permalink': f'/r/zzarc/comments/{ident}/title/',
            'url': 'https://example.invalid/off-site', 'subreddit': 'zzarc'}


class FakeClient:
    """Scripted per (path, subreddit): a list of responses consumed in
    order. An Exception instance is raised instead of returned."""

    def __init__(self, script, parents=None):
        self.script = {key: list(values) for key, values in script.items()}
        self.parents = parents or {}
        self.calls = []

    def get_json(self, path, params):
        self.calls.append((path, dict(params)))
        if path == '/posts/ids':
            ids = params['ids'].split(',')
            return [{'id': i[3:], 'name': i, 'title': self.parents[i]}
                    for i in ids if i in self.parents]
        queue = self.script.get((path, params['subreddit']), [])
        answer = queue.pop(0) if queue else []
        if isinstance(answer, Exception):
            raise answer
        return answer


def minute(n):
    return NOW - dt.timedelta(minutes=n)


# --- mapping -----------------------------------------------------------------

def test_a_comment_maps_to_the_rss_shape():
    posts = arctic_shift.to_raw_posts([comment('c1', minute(3))], 'zzarc', 'comments',
                                      {'t3_parent1': 'Why ZZA ripped'})
    [raw] = posts
    assert raw.source == 'reddit:zzarc' and raw.channel == 'zzarc'
    assert raw.external_id == 't1_c1'
    assert raw.author == '/u/someone'
    assert raw.title == '/u/someone on Why ZZA ripped'
    assert raw.body == 'ZZA to the moon'
    assert raw.score == 1 and raw.num_comments == 0
    assert raw.url == 'https://www.reddit.com/r/zzarc/comments/parent1/title/c1/'
    assert raw.created_utc == minute(3)


def test_a_comment_without_a_known_parent_keeps_a_non_empty_context():
    [raw] = arctic_shift.to_raw_posts([comment('c1', minute(3), link='t3_gone')],
                                      'zzarc', 'comments', {})
    assert raw.title == '/u/someone on [thread unavailable]'


def test_a_deleted_author_and_a_missing_score_are_safe():
    [raw] = arctic_shift.to_raw_posts(
        [{**comment('c1', minute(3)), 'author': '[deleted]', 'score': None}],
        'zzarc', 'comments', {'t3_parent1': 'x'})
    assert raw.author is None
    assert raw.title == '/u/[deleted] on x'
    assert raw.score == 0


def test_a_submission_maps_with_its_own_title_and_permalink():
    [raw] = arctic_shift.to_raw_posts([submission('p1', minute(9))], 'zzarc', 'posts', {})
    assert raw.external_id == 't3_p1'
    assert raw.title == 'ZZA thesis' and raw.body == 'long read'
    assert raw.score == 3 and raw.num_comments == 2
    assert raw.url == 'https://www.reddit.com/r/zzarc/comments/p1/title/'
    assert raw.author == '/u/op'


def test_a_long_synthetic_title_is_clipped_to_the_column():
    [raw] = arctic_shift.to_raw_posts([comment('c1', minute(3))], 'zzarc', 'comments',
                                      {'t3_parent1': 'x' * 600})
    assert len(raw.title) == 512
    assert raw.title.startswith('/u/someone on ')


# --- paging and cursors ------------------------------------------------------

def test_a_cycle_reads_each_sub_from_its_cursor_minus_one_second():
    client = FakeClient({
        ('/comments/search', 'zzarc'): [[comment('c1', minute(4)), comment('c2', minute(2))]],
        ('/posts/search', 'zzarc'): [[submission('p1', minute(5))]],
    }, parents={'t3_parent1': 'Why ZZA ripped'})
    cursors = {('zzarc', 'comments'): minute(30), ('zzarc', 'posts'): minute(40)}

    result, advanced = arctic_shift.fetch(cursors, client, subs=['zzarc'], now=NOW,
                                          page_size=100)

    comments_call = next(p for path, p in client.calls if path == '/comments/search')
    assert comments_call['after'] == epoch(minute(30)) - 1
    assert comments_call['sort'] == 'asc' and comments_call['limit'] == 100
    assert result.status == 'ok'
    assert result.per_source_status == {'reddit:zzarc': 'ok'}
    assert sorted(p.external_id for p in result.posts) == ['t1_c1', 't1_c2', 't3_p1']
    assert advanced == {('zzarc', 'comments'): minute(2), ('zzarc', 'posts'): minute(5)}


def test_a_cold_sub_starts_two_hours_back():
    client = FakeClient({('/comments/search', 'zzarc'): [[]], ('/posts/search', 'zzarc'): [[]]})

    result, advanced = arctic_shift.fetch({}, client, subs=['zzarc'], now=NOW,
                                          cold_start=dt.timedelta(hours=2))

    first = client.calls[0][1]
    assert first['after'] == epoch(NOW - dt.timedelta(hours=2)) - 1
    assert result.status == 'ok' and result.posts == []
    assert advanced == {}                       # nothing accepted, nothing moves


def test_a_full_page_pages_on_and_the_cap_reports_truncated():
    page1 = [comment(f'a{i}', minute(60) + dt.timedelta(seconds=i)) for i in range(3)]
    page2 = [comment(f'b{i}', minute(50) + dt.timedelta(seconds=i)) for i in range(3)]
    page3 = [comment(f'c{i}', minute(40) + dt.timedelta(seconds=i)) for i in range(3)]
    client = FakeClient({('/comments/search', 'zzarc'): [page1, page2, page3],
                         ('/posts/search', 'zzarc'): [[]]},
                        parents={'t3_parent1': 'x'})

    result, advanced = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                          subs=['zzarc'], now=NOW, page_size=3, max_pages=2)

    ids = sorted(p.external_id for p in result.posts)
    assert ids == sorted(f't1_{c["id"]}' for c in page1 + page2)
    assert result.per_source_status == {'reddit:zzarc': 'truncated'}
    assert result.status == 'truncated'
    # Cursor at the newest ACCEPTED comment; the archive is asked again from there.
    assert advanced[('zzarc', 'comments')] == minute(50) + dt.timedelta(seconds=2)
    second_call = [p for path, p in client.calls if path == '/comments/search'][1]
    assert second_call['after'] == page1[-1]['created_utc'] - 1


def test_a_short_last_page_is_complete_and_ok():
    page1 = [comment(f'a{i}', minute(60) + dt.timedelta(seconds=i)) for i in range(3)]
    page2 = [comment('b0', minute(50))]
    client = FakeClient({('/comments/search', 'zzarc'): [page1, page2],
                         ('/posts/search', 'zzarc'): [[]]}, parents={'t3_parent1': 'x'})

    result, _ = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                   subs=['zzarc'], now=NOW, page_size=3, max_pages=2)

    assert result.per_source_status == {'reddit:zzarc': 'ok'}
    assert len(result.posts) == 4


def test_ids_returned_twice_across_the_second_boundary_are_read_once():
    edge = minute(50)
    page1 = [comment('a0', edge - dt.timedelta(seconds=1)), comment('a1', edge)]
    page2 = [comment('a1', edge), comment('a2', edge + dt.timedelta(seconds=1))]  # a1 again
    client = FakeClient({('/comments/search', 'zzarc'): [page1, page2, []],
                         ('/posts/search', 'zzarc'): [[]]}, parents={'t3_parent1': 'x'})

    result, _ = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                   subs=['zzarc'], now=NOW, page_size=2, max_pages=5)

    assert sorted(p.external_id for p in result.posts) == ['t1_a0', 't1_a1', 't1_a2']


# --- statuses ----------------------------------------------------------------

def test_a_failing_sub_is_missing_and_keeps_its_cursor_while_the_others_read():
    client = FakeClient({
        ('/comments/search', 'zzbad'): [arctic_shift.ArcticShiftUnavailable('HTTP 500')],
        ('/posts/search', 'zzbad'): [[]],
        ('/comments/search', 'zzarc'): [[comment('c1', minute(2))]],
        ('/posts/search', 'zzarc'): [[]],
    }, parents={'t3_parent1': 'x'})
    cursors = {('zzbad', 'comments'): minute(30), ('zzarc', 'comments'): minute(30)}

    result, advanced = arctic_shift.fetch(cursors, client, subs=['zzbad', 'zzarc'], now=NOW)

    assert result.per_source_status == {'reddit:zzbad': 'missing', 'reddit:zzarc': 'ok'}
    assert result.status == _roll_up(['missing', 'ok'])       # 'truncated', the Reddit convention
    assert ('zzbad', 'comments') not in advanced
    assert advanced[('zzarc', 'comments')] == minute(2)


def test_a_sub_whose_posts_read_fails_publishes_nothing_and_moves_no_cursor():
    """Comments came back, posts did not: nothing of that sub is returned
    and neither cursor advances, so the comments are read again next cycle
    instead of being stored under a missing source and never counted."""
    client = FakeClient({
        ('/comments/search', 'zzarc'): [[comment('c1', minute(2))]],
        ('/posts/search', 'zzarc'): [arctic_shift.ArcticShiftUnavailable('HTTP 502')],
    }, parents={'t3_parent1': 'x'})

    result, advanced = arctic_shift.fetch({('zzarc', 'comments'): minute(30)}, client,
                                          subs=['zzarc'], now=NOW)

    assert result.per_source_status == {'reddit:zzarc': 'missing'}
    assert result.posts == []
    assert advanced == {}


def test_a_429_ends_the_cycle_and_the_rest_are_not_asked():
    client = FakeClient({
        ('/comments/search', 'zzarc'): [arctic_shift.ArcticShiftThrottled('HTTP 429')],
        ('/comments/search', 'zzbrc'): [[comment('c1', minute(2))]],
        ('/posts/search', 'zzbrc'): [[]],
    })

    result, advanced = arctic_shift.fetch({}, client, subs=['zzarc', 'zzbrc'], now=NOW)

    assert result.per_source_status == {'reddit:zzarc': 'missing'}   # zzbrc absent: never asked
    assert result.status == 'missing'
    assert advanced == {}
    assert all(p['subreddit'] == 'zzarc' for _, p in client.calls if 'subreddit' in p)


# --- parent titles -----------------------------------------------------------

def test_parent_titles_are_fetched_in_batches_and_cached_across_cycles():
    parents = {f't3_p{i}': f'title {i}' for i in range(150)}
    client = FakeClient({}, parents=parents)
    arctic_shift.reset_title_cache()

    first = arctic_shift.parent_titles(client, list(parents))
    calls = [p for path, p in client.calls if path == '/posts/ids']
    assert first == parents
    assert len(calls) == 2 and all(len(c['ids'].split(',')) <= 100 for c in calls)

    again = arctic_shift.parent_titles(client, ['t3_p1', 't3_p2'])
    assert again == {'t3_p1': 'title 1', 't3_p2': 'title 2'}
    assert len([p for path, p in client.calls if path == '/posts/ids']) == 2   # cache hit


# --- the backfill's reader and the probe ---------------------------------------

def test_page_range_reads_a_window_completely_and_stops_at_until():
    day = NOW.replace(hour=0, minute=0, second=0)
    inside = [comment(f'i{i}', day + dt.timedelta(hours=i)) for i in range(3)]
    beyond = [comment('z', day + dt.timedelta(days=1, seconds=5))]
    client = FakeClient({('/comments/search', 'zzarc'): [inside[:2], inside[2:] + beyond, []]})

    items = arctic_shift.page_range(client, 'zzarc', 'comments', day, day + dt.timedelta(days=1),
                                    page_size=2)

    assert [i['id'] for i in items] == ['i0', 'i1', 'i2']


def test_probe_names_the_subs_the_archive_has_nothing_for():
    client = FakeClient({('/posts/search', 'zzarc'): [[submission('p1', minute(5))]],
                         ('/posts/search', 'zzempty'): [[]]})
    assert arctic_shift.probe_subs(client, ['zzarc', 'zzempty']) == ['zzempty']


# --- 'auto' pages, whose size says nothing (probed 2026-09-02) ----------------

def test_an_auto_sized_read_pages_until_an_empty_page():
    """A numeric limit is refused above 100 and 'auto' answers with ~600,
    so 'the page was short' cannot mean 'that was the last of it'. Only an
    empty page ends the range."""
    page1 = [comment(f'a{i}', minute(60) + dt.timedelta(seconds=i)) for i in range(4)]
    page2 = [comment(f'b{i}', minute(50) + dt.timedelta(seconds=i)) for i in range(2)]
    client = FakeClient({('/comments/search', 'zzarc'): [page1, page2, []],
                         ('/posts/search', 'zzarc'): [[]]}, parents={'t3_parent1': 'x'})

    result, advanced = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                          subs=['zzarc'], now=NOW, page_size='auto',
                                          max_pages=5)

    assert len(result.posts) == 6                      # the short page was not the end
    assert result.per_source_status == {'reddit:zzarc': 'ok'}
    assert client.calls[0][1]['limit'] == 'auto'
    assert advanced[('zzarc', 'comments')] == minute(50) + dt.timedelta(seconds=1)


def test_an_auto_sized_read_that_hits_the_cap_is_truncated():
    pages = [[comment(f'p{n}i{i}', minute(60 - 10 * n) + dt.timedelta(seconds=i))
              for i in range(2)] for n in range(4)]
    client = FakeClient({('/comments/search', 'zzarc'): list(pages),
                         ('/posts/search', 'zzarc'): [[]]}, parents={'t3_parent1': 'x'})

    result, _ = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                   subs=['zzarc'], now=NOW, page_size='auto', max_pages=2)

    assert result.per_source_status == {'reddit:zzarc': 'truncated'}
    assert len(result.posts) == 4


def test_an_item_without_a_timestamp_does_not_take_the_whole_cycle_down():
    """The filter tolerates a missing created_utc; the paging key used to
    subscript it. One malformed item would have raised out of fetch() and
    run_cycle's blanket except would have marked every sub missing."""
    broken = [{'id': 'x1', 'name': 't1_x1', 'author': 'a', 'body': 'ZZA',
               'link_id': 't3_parent1', 'permalink': '/r/zzarc/x1/'}]
    client = FakeClient({('/comments/search', 'zzarc'): [broken],
                         ('/posts/search', 'zzarc'): [[]]}, parents={'t3_parent1': 'x'})

    result, advanced = arctic_shift.fetch({('zzarc', 'comments'): minute(30)}, client,
                                          subs=['zzarc'], now=NOW, page_size='auto')

    assert result.per_source_status == {'reddit:zzarc': 'ok'}
    assert result.posts == []
    assert advanced == {}


# --- the archive's own 'slow down' (measured 2026-09-03) ----------------------

class BusyOnceClient(FakeClient):
    """Raises ArcticShiftBusy for the first `busy` search calls, then
    behaves like FakeClient."""

    def __init__(self, script, busy=1, **kwargs):
        super().__init__(script, **kwargs)
        self.busy = busy

    def get_json(self, path, params):
        if path.endswith('/search') and self.busy:
            self.busy -= 1
            self.calls.append((path, dict(params)))
            raise arctic_shift.ArcticShiftBusy('HTTP 422 Timeout. Maybe slow down a bit')
        return super().get_json(path, params)


def test_a_422_is_the_archive_asking_us_to_slow_down_not_a_bad_request():
    """Deep pagination through a busy day answers 422 'Timeout. Maybe slow
    down a bit' around the fortieth page; the identical request then
    succeeds. It must be its own class, or the backfill cannot tell it
    from a 500 and gives the day up."""
    class Response:
        status_code = 422
        text = '{"data":null,"error":"Timeout. Maybe slow down a bit"}'
        ok = False

    class Session:
        headers = {}

        def get(self, url, params=None, timeout=None):
            return Response()

    client = arctic_shift.ArcticShiftClient()
    client._session = Session()
    with pytest.raises(arctic_shift.ArcticShiftBusy):
        client.get_json('/comments/search', {'subreddit': 'zzarc'})
    assert issubclass(arctic_shift.ArcticShiftBusy, arctic_shift.ArcticShiftUnavailable)


def test_page_range_waits_out_a_busy_archive(monkeypatch):
    slept = []
    monkeypatch.setattr(arctic_shift.time, 'sleep', slept.append)
    client = BusyOnceClient({('/comments/search', 'zzarc'): [[comment('c1', minute(30))], []]},
                            busy=1)

    items = arctic_shift.page_range(client, 'zzarc', 'comments', minute(60), NOW,
                                    page_size='auto')

    assert [i['id'] for i in items] == ['c1']
    assert slept and slept[0] >= 2.0


def test_page_range_gives_up_after_the_retry_budget(monkeypatch):
    monkeypatch.setattr(arctic_shift.time, 'sleep', lambda _s: None)
    client = BusyOnceClient({('/comments/search', 'zzarc'): [[]]}, busy=99)

    with pytest.raises(arctic_shift.ArcticShiftBusy):
        arctic_shift.page_range(client, 'zzarc', 'comments', minute(60), NOW, retries=2)
    assert len(client.calls) == 3          # the first try plus two retries


def test_a_live_cycle_does_not_wait_on_a_busy_archive(monkeypatch):
    """Five-minute windows are cheap queries. If one still times out, the
    sub is missing with its cursor unmoved and the next cycle asks again
    -- cheaper than holding the scheduler worker for 34 subreddits."""
    slept = []
    monkeypatch.setattr(arctic_shift.time, 'sleep', slept.append)
    client = BusyOnceClient({('/comments/search', 'zzarc'): [[comment('c1', minute(2))]],
                             ('/posts/search', 'zzarc'): [[]]}, busy=1)

    result, advanced = arctic_shift.fetch({('zzarc', 'comments'): minute(30)}, client,
                                          subs=['zzarc'], now=NOW)

    assert result.per_source_status == {'reddit:zzarc': 'missing'}
    assert advanced == {} and slept == []
