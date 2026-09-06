"""The raw capture: every item of a day, per sub, written whole to disk with
its parent title, and never fetched twice."""
import datetime as dt
import json

from scripts import capture_arctic_raw as capture
from test_radar_arctic_shift import FakeClient, comment, submission   # tests/ is on sys.path

DAY = dt.datetime(2027, 1, 4)
END = dt.datetime(2027, 1, 5)


def _client():
    return FakeClient({
        ('/comments/search', 'zzarc'): [[comment('c1', DAY, body='ZZTQ to the moon'),
                                        comment('c2', DAY + dt.timedelta(minutes=1),
                                                author='other', body='nothing here')], []],
        ('/posts/search', 'zzarc'): [[submission('p1', DAY, title='ZZTQ thesis')], []],
        ('/comments/search', 'zzquiet'): [[]],
        ('/posts/search', 'zzquiet'): [[]],
    }, parents={'t3_parent1': 'Why ZZA ripped'})


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle]


def test_a_day_is_written_per_sub_with_parent_titles_and_nothing_filtered(tmp_path):
    counts = capture.capture_day(_client(), ['zzarc', 'zzquiet'], DAY, END, tmp_path)

    rows = _read(tmp_path / '2027-01-04' / 'zzarc.jsonl')
    assert counts == {'zzarc': 3, 'zzquiet': 0}
    # Every item, including the one with no ticker in it: the point of the
    # capture is the population the extractor never stored.
    assert sorted(r['external_id'] for r in rows) == ['t1_c1', 't1_c2', 't3_p1']
    by_id = {r['external_id']: r for r in rows}
    assert by_id['t1_c1']['title'] == '/u/someone on Why ZZA ripped'
    assert by_id['t1_c1']['body'] == 'ZZTQ to the moon'
    assert by_id['t1_c1']['kind'] == 'comments'
    assert by_id['t3_p1']['kind'] == 'posts'
    assert by_id['t3_p1']['created_utc'] == '2027-01-04T00:00:00'
    assert by_id['t1_c1']['source'] == 'reddit:zzarc'
    # A quiet sub still leaves its (empty) file, so the resume marker exists.
    assert _read(tmp_path / '2027-01-04' / 'zzquiet.jsonl') == []


def test_a_sub_already_on_disk_is_not_fetched_again(tmp_path):
    capture.capture_day(_client(), ['zzarc'], DAY, END, tmp_path)
    again = _client()
    counts = capture.capture_day(again, ['zzarc'], DAY, END, tmp_path)
    assert again.calls == []
    assert counts == {'zzarc': None}


def test_a_partial_file_from_an_interrupted_run_is_redone(tmp_path):
    day_dir = tmp_path / '2027-01-04'
    day_dir.mkdir()
    (day_dir / 'zzarc.jsonl.tmp').write_text('{"half": true', encoding='utf-8')
    capture.capture_day(_client(), ['zzarc'], DAY, END, tmp_path)
    assert not (day_dir / 'zzarc.jsonl.tmp').exists()
    assert len(_read(day_dir / 'zzarc.jsonl')) == 3


def test_days_run_newest_first():
    chunks = capture.day_chunks(dt.datetime(2027, 1, 4), days=3)
    assert chunks == [
        (dt.datetime(2027, 1, 3), dt.datetime(2027, 1, 4)),
        (dt.datetime(2027, 1, 2), dt.datetime(2027, 1, 3)),
        (dt.datetime(2027, 1, 1), dt.datetime(2027, 1, 2)),
    ]
