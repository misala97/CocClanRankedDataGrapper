# personal_apps/tests/test_sample_zero_candidate_posts.py
"""Stage 1 of the NER probe: a fixed, uniform sample of the posts the
extractor sees nothing in.

Two things can go quietly wrong here and both would poison every number
downstream: the predicate admitting posts that DID have a candidate (then
the probe measures the extractor's rejects, already measured elsewhere),
and a sample that is the first N of whatever sub sorts first (then the
number is about r/biotech_stocks, not about the week).
"""
import json

from scripts import sample_zero_candidate_posts as szc


def _row(gate=None, accepted=(), rejected=()):
    return {'external_id': 'x', 'gate': gate, 'accepted': list(accepted),
            'rejected': list(rejected), 'author_text': 'body', 'source': 'reddit:t',
            'kind': 'comments', 'created_utc': '2026-08-30T00:00:00', 'title': None}


BODY = 'x' * szc.MIN_BODY_CHARS


def test_predicate_admits_only_the_post_nothing_found_anything_in():
    assert szc.is_zero_candidate(_row(), BODY)
    assert not szc.is_zero_candidate(_row(gate='bot_feed'), BODY)
    assert not szc.is_zero_candidate(_row(accepted=[{'symbol': 'NVDA'}]), BODY)
    # The loose pass finding something makes it a REJECT, a different population.
    assert not szc.is_zero_candidate(_row(rejected=[{'symbol': 'BE'}]), BODY)


def test_predicate_applies_the_probes_body_floor():
    assert not szc.is_zero_candidate(_row(), 'x' * (szc.MIN_BODY_CHARS - 1))
    assert szc.is_zero_candidate(_row(), BODY)


def _lines(n):
    return [{'external_id': 't1_%03d' % i, 'source': 'reddit:t', 'channel': 't',
             'author': 'a', 'created_utc': '2026-08-30T00:00:00', 'title': None,
             'body': BODY + str(i), 'kind': 'comments'} for i in range(n)]


def _classify_all_empty(line, **_):
    return {'external_id': line['external_id'], 'gate': None, 'accepted': [],
            'rejected': [], 'author_text': line['body'], 'source': line['source'],
            'kind': line['kind'], 'created_utc': line['created_utc'],
            'title': line['title']}


def test_sample_is_seeded_and_stops_at_n():
    lines = _lines(50)
    first = szc.sample(lines, n=5, seed=7, classify_fn=_classify_all_empty)
    again = szc.sample(lines, n=5, seed=7, classify_fn=_classify_all_empty)
    other = szc.sample(lines, n=5, seed=8, classify_fn=_classify_all_empty)
    assert len(first) == 5
    assert [r['external_id'] for r in first] == [r['external_id'] for r in again]
    assert [r['external_id'] for r in first] != [r['external_id'] for r in other]
    # Not the first five of the file.
    assert [r['external_id'] for r in first] != ['t1_000', 't1_001', 't1_002',
                                                  't1_003', 't1_004']


def test_sample_skips_posts_with_candidates_without_counting_them():
    lines = _lines(20)

    def classify(line, **_):
        row = _classify_all_empty(line)
        if int(line['external_id'][-3:]) % 2:
            row['accepted'] = [{'symbol': 'NVDA'}]
        return row

    got = szc.sample(lines, n=6, seed=1, classify_fn=classify)
    assert len(got) == 6
    assert all(int(r['external_id'][-3:]) % 2 == 0 for r in got)


def test_sample_row_carries_what_stage_two_needs_and_nothing_secret():
    line = _lines(1)[0]
    row = szc.sample_row(line, _classify_all_empty(line))
    assert set(row) == {'external_id', 'source', 'kind', 'created_utc', 'title',
                        'body', 'author_text'}
    assert 'author' not in row
    json.dumps(row)                     # must be a plain JSON line


def test_lookup_dump_is_plain_json_with_sorted_tokens():
    lookup = {'NVDA': {'name': 'NVIDIA Corporation', 'exchange': 'Q',
                       'distinctive': {'nvidia', 'corporation'}}}
    dumped = szc.dump_lookup(lookup, aliases={'google': 'GOOGL', 'cook': None})
    assert dumped['symbols']['NVDA'] == {'name': 'NVIDIA Corporation',
                                         'distinctive': ['corporation', 'nvidia']}
    assert dumped['aliases'] == {'google': 'GOOGL', 'cook': None}
    json.dumps(dumped)


def test_exclusions_leave_the_lookup_dump_and_are_reported():
    lookup = {'QQQ': {'name': 'Invesco QQQ Trust', 'distinctive': set()},
              'NVDA': {'name': 'NVIDIA Corporation', 'distinctive': {'nvidia'}}}
    kept = szc.without_symbols(lookup, {'QQQ'})
    assert set(kept) == {'NVDA'}
    assert set(lookup) == {'QQQ', 'NVDA'}          # the caller's dict is untouched
