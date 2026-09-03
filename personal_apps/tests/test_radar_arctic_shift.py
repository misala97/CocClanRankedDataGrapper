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
