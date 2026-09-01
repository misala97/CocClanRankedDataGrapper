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
