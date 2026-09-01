# personal_apps/tests/test_capture_deutsche_boerse_contract.py
"""The capture tool is the plan's legal/empirical gate: it may describe the
SHAPE of a licensed Deutsche Börse file but must never leak a value from it,
touch the network, or import the app. These tests pin all three properties
before any real download exists."""
import dataclasses
import gzip
import json
import pathlib
import re
import subprocess
import sys

import pytest

from scripts.capture_deutsche_boerse_contract import (
    ArchiveReport, CaptureError, inspect_archive, main)


def _write_gz(path, payload):
    with gzip.open(path, 'wt', encoding='utf-8') as handle:
        json.dump(payload, handle)


def test_capture_rejects_a_decompression_bomb(tmp_path):
    archive = tmp_path / 'large.json.gz'
    with gzip.open(archive, 'wb') as handle:
        handle.write(b'[' + b' ' * 10_000 + b']')
    with pytest.raises(CaptureError, match='decompression ratio'):
        inspect_archive(archive, max_uncompressed=20_000, max_ratio=2)


def test_capture_reports_structure_without_market_values(tmp_path):
    archive = tmp_path / 'sample.json.gz'
    payload = {'rows': [{'ISIN': 'DE000FAKE001', 'price': 123.45,
                         'timestamp': '2026-08-31T12:43:00Z'}]}
    _write_gz(archive, payload)
    report = inspect_archive(archive)
    encoded = json.dumps(dataclasses.asdict(report), sort_keys=True)
    assert '/rows/*/ISIN' in encoded
    assert 'DE000FAKE001' not in encoded
    assert '123.45' not in encoded


def test_capture_rejects_an_oversized_compressed_file(tmp_path):
    archive = tmp_path / 'big.json.gz'
    _write_gz(archive, {'rows': list(range(100))})
    with pytest.raises(CaptureError, match='compressed'):
        inspect_archive(archive, max_compressed=10)


def test_capture_rejects_an_oversized_uncompressed_payload(tmp_path):
    archive = tmp_path / 'wide.json.gz'
    _write_gz(archive, {'rows': ['x' * 500]})
    # A generous ratio keeps the ratio guard quiet so the absolute
    # uncompressed cap is what trips.
    with pytest.raises(CaptureError, match='uncompressed'):
        inspect_archive(archive, max_uncompressed=100, max_ratio=1_000_000)


def test_capture_rejects_invalid_gzip(tmp_path):
    archive = tmp_path / 'notgzip.json.gz'
    archive.write_bytes(b'this is not a gzip stream')
    with pytest.raises(CaptureError, match='gzip'):
        inspect_archive(archive)


def test_capture_rejects_invalid_json(tmp_path):
    archive = tmp_path / 'notjson.json.gz'
    with gzip.open(archive, 'wb') as handle:
        handle.write(b'{"rows": [')
    with pytest.raises(CaptureError, match='JSON'):
        inspect_archive(archive)


def test_capture_rejects_invalid_utf8(tmp_path):
    archive = tmp_path / 'notutf8.json.gz'
    with gzip.open(archive, 'wb') as handle:
        handle.write(b'\xff\xfe\x00broken')
    with pytest.raises(CaptureError, match='UTF-8|JSON'):
        inspect_archive(archive)


def test_newline_delimited_json_reports_line_objects_as_star_paths(tmp_path):
    # The real Deutsche Börse delayed files are JSON Lines, not one document:
    # the very first capture run failed with "Extra data" until this branch
    # existed. Each line is a root object collapsed under /*.
    archive = tmp_path / 'lines.json.gz'
    lines = '\n'.join(json.dumps(obj) for obj in (
        {'isin': 'DE000FAKE001', 'price': 1.5},
        {'isin': 'DE000FAKE002', 'price': 2.5},
        {'other': True},
    ))
    with gzip.open(archive, 'wt', encoding='utf-8') as handle:
        handle.write(lines + '\n')
    report = inspect_archive(archive)
    assert report.top_level_type == 'ndjson'
    by_path = {shape.path: shape for shape in report.paths}
    assert by_path['/*/isin'].occurrences == 2
    assert by_path['/*/price'].types == ('number',)
    assert by_path['/*/other'].types == ('boolean',)
    encoded = json.dumps(dataclasses.asdict(report))
    assert 'DE000FAKE001' not in encoded


def test_a_top_level_list_reports_star_paths(tmp_path):
    archive = tmp_path / 'list.json.gz'
    _write_gz(archive, [{'a': 1}, {'a': 2}, {'b': 'x'}])
    report = inspect_archive(archive)
    assert report.top_level_type == 'list'
    by_path = {shape.path: shape for shape in report.paths}
    assert by_path['/*/a'].occurrences == 2
    assert by_path['/*/a'].types == ('number',)
    assert by_path['/*/b'].types == ('string',)


def test_timestamp_and_identifier_shaped_paths_are_classified(tmp_path):
    archive = tmp_path / 'shapes.json.gz'
    _write_gz(archive, {'rows': [{
        'isin': 'DE000FAKE001',
        'ts': '2026-08-31T12:43:00Z',
        'epoch': 1756644180000,
        'note': 'hello world sentence',
    }]})
    report = inspect_archive(archive)
    assert '/rows/*/ts' in report.timestamp_paths
    assert '/rows/*/epoch' in report.timestamp_paths
    assert '/rows/*/isin' in report.identifier_paths
    assert '/rows/*/note' not in report.identifier_paths
    assert '/rows/*/note' not in report.timestamp_paths


def test_report_carries_hashes_and_sizes(tmp_path):
    archive = tmp_path / 'sized.json.gz'
    _write_gz(archive, {'k': 'v'})
    report = inspect_archive(archive)
    assert report.filename == 'sized.json.gz'
    assert len(report.sha256) == 64
    assert report.compressed_bytes == archive.stat().st_size
    assert report.uncompressed_bytes > 0
    assert report.top_level_type == 'dict'


def test_cli_end_to_end_writes_redacted_report_for_all_four_inputs(tmp_path):
    inputs = {}
    for name in ('xgat-pre', 'xgat-post', 'xetr-pre', 'xetr-post'):
        path = tmp_path / f'{name}.json.gz'
        _write_gz(path, {'rows': [{'ISIN': 'DE000FAKE001',
                                   'price': 55.5,
                                   'ts': '2026-08-31T12:00:00Z'}]})
        inputs[name] = path
    output = tmp_path / 'report.json'
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.capture_deutsche_boerse_contract',
         '--xgat-pre', str(inputs['xgat-pre']),
         '--xgat-post', str(inputs['xgat-post']),
         '--xetr-pre', str(inputs['xetr-pre']),
         '--xetr-post', str(inputs['xetr-post']),
         '--output', str(output)],
        capture_output=True, text=True, check=True)
    written = json.loads(output.read_text(encoding='utf-8'))
    assert set(written) == {'xgat_pre', 'xgat_post', 'xetr_pre', 'xetr_post'}
    for key in written:
        assert '/rows/*/ISIN' in json.dumps(written[key])
    # stdout carries the same JSON; neither channel leaks a payload value.
    assert json.loads(result.stdout) == written
    for text in (result.stdout, output.read_text(encoding='utf-8')):
        assert 'DE000FAKE001' not in text
        assert '55.5' not in text
        assert '2026-08-31T12:00:00Z' not in text


def test_aggregate_statistics_are_auditable_without_leaking_values(tmp_path):
    # The supplement's quantitative claims (duplicate counts, ordering,
    # enum time-clustering) must be re-derivable from the committed tool,
    # not rest on a discarded local analysis (review finding 4).
    archive = tmp_path / 'stats.json.gz'
    rows = [
        {'txid': 'zz-1', 'flag': 'R', 'price': 10.0,
         'publicationDateAndTime': '2026-08-31T09:00:00.000Z'},
        {'txid': 'zz-2', 'flag': 'R', 'price': 11.0,
         'publicationDateAndTime': '2026-08-31T09:01:00.000Z'},
        {'txid': 'zz-2', 'flag': 'C', 'price': 12.0,
         'publicationDateAndTime': '2026-08-31T15:35:00.000Z'},
        {'txid': 'zz-3', 'flag': 'C', 'price': 13.0,
         'publicationDateAndTime': '2026-08-31T15:39:00.000Z'},
        {'txid': 'zz-4', 'flag': 'R', 'price': 14.0,
         'publicationDateAndTime': '2026-08-31T15:20:00.000Z'},
    ]
    with gzip.open(archive, 'wt', encoding='utf-8') as handle:
        handle.write('\n'.join(json.dumps(row) for row in rows) + '\n')
    report = inspect_archive(archive)

    cardinality = {c.path: c for c in report.value_cardinality}
    # txid: 4 distinct across 5 rows -> exactly one duplicate is derivable.
    assert (cardinality['/*/txid'].distinct, cardinality['/*/txid'].total) == (4, 5)
    assert (cardinality['/*/flag'].distinct, cardinality['/*/flag'].total) == (2, 5)

    order = {o.path: o.violations for o in report.order_violations}
    # 15:35 -> 15:20 is the single descending step.
    assert order['/*/publicationDateAndTime'] == 1

    profiles = {p.path: p for p in report.enum_time_profiles}
    flag = {v.value: v for v in profiles['/*/flag'].values}
    assert flag['C'].count == 2
    assert (flag['C'].first_hhmm, flag['C'].last_hhmm) == ('15:35', '15:39')
    assert flag['R'].count == 3
    # High-cardinality paths must never surface values.
    assert '/*/txid' not in profiles
    encoded = json.dumps(dataclasses.asdict(report))
    assert 'zz-1' not in encoded
    assert '10.0' not in encoded


_SUPPLEMENT = (pathlib.Path(__file__).parent.parent.parent / 'docs'
               / 'superpowers' / 'specs'
               / '2026-08-31-radar-deutsche-boerse-feed-contract.md')
_FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'radar_market_data'

_SECTION_TO_FIXTURE = {
    '### 3.1': 'xgat_posttrade.json',
    '### 3.2': 'xetr_posttrade.json',
    '### 3.3': 'xgat_pretrade.json',
    '### 3.4': 'xetr_pretrade.json',
}


def _pointers_by_fixture():
    """Every backticked /*-pointer in each supplement field section."""
    text = _SUPPLEMENT.read_text(encoding='utf-8')
    marks = sorted(
        ((text.index(heading), fixture)
         for heading, fixture in _SECTION_TO_FIXTURE.items()),
        key=lambda item: item[0])
    end_of_tables = text.index('## 4.')
    found = {}
    for index, (start, fixture) in enumerate(marks):
        stop = marks[index + 1][0] if index + 1 < len(marks) else end_of_tables
        found[fixture] = re.findall(r'`(/\*/[^`]+)`', text[start:stop])
    # Section 3.2 inherits 3.1's pointers, minus the exceptions its
    # inheritance sentence names in backticks.
    inheritance = re.search(
        r'Same pointers as 3\.1(?: \(except ([^)]*)\))?', text)
    assert inheritance is not None
    excepted = set(re.findall(r'`(/\*/[^`]+)`', inheritance.group(1) or ''))
    found['xetr_posttrade.json'] += found['xgat_posttrade.json']
    # The exception sentence itself is inside section 3.2, so its backticked
    # pointer is scraped like any other -- drop the excepted set entirely.
    found['xetr_posttrade.json'] = [
        pointer for pointer in found['xetr_posttrade.json']
        if pointer not in excepted]
    return found


def _resolves(rows, pointer):
    """True when some fixture row carries the pointer's path."""
    def walk(node, segments):
        if not segments:
            return True
        head, *rest = segments
        if head == '*':
            return isinstance(node, list) and any(
                walk(child, rest) for child in node)
        return isinstance(node, dict) and head in node and walk(
            node[head], rest)
    return walk(rows, ['*'] + pointer.strip('/').split('/')[1:])


def test_every_supplement_pointer_resolves_in_its_fixture():
    by_fixture = _pointers_by_fixture()
    # A silently empty extraction would make this test vacuous.
    assert all(len(pointers) >= 5 for pointers in by_fixture.values()), \
        by_fixture
    for fixture, pointers in by_fixture.items():
        rows = json.loads((_FIXTURES / fixture).read_text(encoding='utf-8'))
        missing = [p for p in set(pointers) if not _resolves(rows, p)]
        assert not missing, f'{fixture}: unresolved pointers {sorted(missing)}'


def _fixture_pointers(node, prefix=''):
    if isinstance(node, list):
        for child in node:
            yield from _fixture_pointers(child, prefix + '/*')
    elif isinstance(node, dict):
        for key, child in node.items():
            yield from _fixture_pointers(child, '%s/%s' % (prefix, key))
    else:
        yield prefix


def test_every_fixture_key_is_named_by_the_supplement():
    # The reverse direction: a fixture must not carry a field the contract
    # tables never documented (review finding 2 — two fixtures did).
    by_fixture = _pointers_by_fixture()
    for fixture, pointers in by_fixture.items():
        rows = json.loads((_FIXTURES / fixture).read_text(encoding='utf-8'))
        documented = set(pointers)
        undocumented = {
            pointer for pointer in _fixture_pointers(rows)
            if pointer not in documented}
        assert not undocumented, f'{fixture}: {sorted(undocumented)}'


def test_the_parity_check_has_teeth():
    rows = json.loads(
        (_FIXTURES / 'xgat_posttrade.json').read_text(encoding='utf-8'))
    assert not _resolves(rows, '/*/definitelyNotAField')


def test_the_script_never_imports_network_or_database_modules():
    import scripts.capture_deutsche_boerse_contract as module
    source = open(module.__file__, encoding='utf-8').read()
    for forbidden in ('requests', 'urllib', 'extensions', 'models',
                      'sqlalchemy'):
        assert forbidden not in source
