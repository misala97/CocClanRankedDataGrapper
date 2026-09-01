# personal_apps/scripts/capture_deutsche_boerse_contract.py
"""Describe the SHAPE of four Deutsche Börse delayed-data files, nothing else.

This is the plan's provider-contract capture gate (spec §6): the exact field
names, nesting, and identifier/timestamp representations of the licensed
files must be OBSERVED before any parser is written, but the licensed VALUES
must never enter Git, a report, or a terminal scrollback that gets pasted
into a document. So the tool emits JSON paths, JSON types, and occurrence
counts — and classifies which paths LOOK timestamp- or identifier-shaped by
inspecting values it then throws away.

Deliberately stdlib-only and offline: no HTTP, no app import, no database.
The operator downloads the files in a browser after accepting the terms;
this script only reads the four local paths it is handed.

    cd personal_apps && python -m scripts.capture_deutsche_boerse_contract \
        --xgat-pre ... --xgat-post ... --xetr-pre ... --xetr-post ... \
        --output %TEMP%\radar-dbag-contract-report.json
"""
import argparse
import dataclasses
import gzip
import hashlib
import json
import pathlib
import re
import sys


class CaptureError(Exception):
    """A file that cannot be safely or completely inspected."""


@dataclasses.dataclass(frozen=True)
class PathShape:
    path: str
    types: tuple[str, ...]
    occurrences: int


@dataclasses.dataclass(frozen=True)
class ArchiveReport:
    filename: str
    sha256: str
    compressed_bytes: int
    uncompressed_bytes: int
    top_level_type: str
    paths: tuple[PathShape, ...]
    timestamp_paths: tuple[str, ...]
    identifier_paths: tuple[str, ...]


# Chunked reads so a hostile archive cannot balloon memory before the
# accounting notices; 1 MiB keeps the loop tight without large buffers.
_CHUNK = 1 << 20

_JSON_TYPES = {
    dict: 'dict', list: 'list', str: 'string', bool: 'boolean',
    int: 'number', float: 'number', type(None): 'null',
}

# Shape detectors run on leaf STRINGS/NUMBERS to classify the PATH; the
# matched values are never emitted. ISO-8601-ish covers date, datetime with
# offset/Z, and time-only forms; epoch-ish covers seconds/millis/micros
# since 2000 as integers.
_TIMESTAMP_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}([.,]\d+)?)?'
    r'(Z|[+-]\d{2}:?\d{2})?)?$|^\d{2}:\d{2}:\d{2}([.,]\d+)?$')
_EPOCH_RANGE = (946_684_800, 4_102_444_800)  # 2000..2100 in seconds
_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}\d$')
_MNEMONIC_RE = re.compile(r'^[A-Z0-9]{1,6}$')


def _looks_like_timestamp(value):
    if isinstance(value, str):
        return bool(_TIMESTAMP_RE.match(value.strip()))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        for scale in (1, 1e3, 1e6, 1e9):
            scaled = seconds / scale
            if _EPOCH_RANGE[0] <= scaled <= _EPOCH_RANGE[1]:
                return True
    return False


def _looks_like_identifier(value):
    return isinstance(value, str) and bool(
        _ISIN_RE.match(value.strip()) or _MNEMONIC_RE.match(value.strip()))


def inspect_archive(path, *, max_compressed=52_428_800,
                    max_uncompressed=262_144_000, max_ratio=100):
    """One bounded, redacted structural report for one ``.json.gz`` file."""
    path = pathlib.Path(path)
    compressed_bytes = path.stat().st_size
    if compressed_bytes > max_compressed:
        raise CaptureError(
            'compressed size %d exceeds limit %d'
            % (compressed_bytes, max_compressed))

    sha = hashlib.sha256()
    with open(path, 'rb') as raw:
        while chunk := raw.read(_CHUNK):
            sha.update(chunk)

    pieces = []
    uncompressed_bytes = 0
    try:
        with gzip.open(path, 'rb') as handle:
            while chunk := handle.read(_CHUNK):
                uncompressed_bytes += len(chunk)
                if uncompressed_bytes > max_uncompressed:
                    raise CaptureError(
                        'uncompressed size exceeds limit %d' % max_uncompressed)
                if (compressed_bytes and
                        uncompressed_bytes / compressed_bytes > max_ratio):
                    raise CaptureError(
                        'decompression ratio exceeds limit %d' % max_ratio)
                pieces.append(chunk)
    except (OSError, EOFError) as exc:
        raise CaptureError('invalid gzip stream: %s' % exc) from exc

    try:
        text = b''.join(pieces).decode('utf-8')
    except UnicodeDecodeError as exc:
        raise CaptureError('payload is not UTF-8: %s' % exc) from exc

    # The real delayed files turned out to be JSON Lines, not one document:
    # a single-document parse dies with "Extra data". Fall back to
    # line-delimited parsing and report the roots as ndjson.
    ndjson = False
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        rows = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CaptureError(
                    'payload is not valid JSON (single or line-delimited): '
                    'line %d: %s' % (number, exc)) from exc
        if not rows:
            raise CaptureError('payload is not valid JSON: empty document')
        payload = rows
        ndjson = True

    shapes = {}
    timestamp_paths = set()
    identifier_paths = set()

    def visit(node, pointer):
        kind = _JSON_TYPES[type(node)]
        entry = shapes.setdefault(pointer, {'types': set(), 'count': 0})
        entry['types'].add(kind)
        entry['count'] += 1
        if isinstance(node, dict):
            for key, child in node.items():
                visit(child, '%s/%s' % (pointer, key))
        elif isinstance(node, list):
            for child in node:
                visit(child, pointer + '/*')
        else:
            if _looks_like_timestamp(node):
                timestamp_paths.add(pointer)
            elif _looks_like_identifier(node):
                identifier_paths.add(pointer)

    if isinstance(payload, dict):
        for key, child in payload.items():
            visit(child, '/%s' % key)
    elif isinstance(payload, list):
        for child in payload:
            visit(child, '/*')

    paths = tuple(
        PathShape(path=pointer, types=tuple(sorted(entry['types'])),
                  occurrences=entry['count'])
        for pointer, entry in sorted(shapes.items()))
    return ArchiveReport(
        filename=path.name, sha256=sha.hexdigest(),
        compressed_bytes=compressed_bytes,
        uncompressed_bytes=uncompressed_bytes,
        top_level_type='ndjson' if ndjson else _JSON_TYPES[type(payload)],
        paths=paths,
        timestamp_paths=tuple(sorted(timestamp_paths)),
        identifier_paths=tuple(sorted(identifier_paths)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Redacted structural capture of four Deutsche Börse '
                    'delayed-data files.')
    parser.add_argument('--xgat-pre', required=True, type=pathlib.Path)
    parser.add_argument('--xgat-post', required=True, type=pathlib.Path)
    parser.add_argument('--xetr-pre', required=True, type=pathlib.Path)
    parser.add_argument('--xetr-post', required=True, type=pathlib.Path)
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args(argv)

    report = {
        name: dataclasses.asdict(inspect_archive(getattr(args, name)))
        for name in ('xgat_pre', 'xgat_post', 'xetr_pre', 'xetr_post')
    }
    encoded = json.dumps(report, indent=2, sort_keys=True)
    args.output.write_text(encoded, encoding='utf-8')
    print(encoded)
    return 0


if __name__ == '__main__':
    sys.exit(main())
