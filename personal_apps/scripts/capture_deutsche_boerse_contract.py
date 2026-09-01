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
class ValueCardinality:
    path: str
    distinct: int
    total: int


@dataclasses.dataclass(frozen=True)
class OrderCheck:
    path: str
    violations: int


@dataclasses.dataclass(frozen=True)
class EnumValueProfile:
    value: str
    count: int
    first_hhmm: str
    last_hhmm: str


@dataclasses.dataclass(frozen=True)
class EnumTimeProfile:
    path: str
    values: tuple[EnumValueProfile, ...]


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
    # Aggregate, value-free statistics so the supplement's quantitative
    # claims (duplicate counts, ordering, enum clustering) are re-derivable
    # from the committed tool instead of a discarded local analysis.
    # enum_time_profiles is the ONE place literal payload strings appear,
    # and only for paths with at most _ENUM_MAX_DISTINCT distinct values --
    # schema vocabulary (flags, MICs, currencies), never market data.
    value_cardinality: tuple[ValueCardinality, ...] = ()
    order_violations: tuple[OrderCheck, ...] = ()
    enum_time_profiles: tuple[EnumTimeProfile, ...] = ()


# A string path qualifies as enum vocabulary only while its distinct-value
# count stays at or below this. Prices, ISINs, and ids blow past it within a
# handful of rows and are therefore never surfaced.
_ENUM_MAX_DISTINCT = 12

# Only values of this shape may ever be surfaced in an enum profile: short
# uppercase flag/venue/currency vocabulary. ISINs (12 chars), transaction
# ids, and anything lowercase or long can never appear regardless of
# cardinality -- a second guard on top of _ENUM_MAX_DISTINCT, because a
# SMALL file could otherwise sneak identifiers under the distinct cap.
_ENUM_VALUE_RE = re.compile(r'^[A-Z0-9-]{1,6}$')


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
        # split('\n') rather than splitlines(): the latter also splits on
        # exotic Unicode terminators that could legally appear INSIDE a
        # string field and would misfire the parser.
        for number, line in enumerate(text.split('\n'), start=1):
            line = line.strip('\r').strip()
            if not line:
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

    # Aggregate statistics run over NDJSON rows (the only shape the real
    # feed uses); a single JSON document has no row sequence to profile.
    cardinality = {}
    order_checks = {}
    profiles = {}
    if ndjson:
        counters = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            row_ts = max((value for value in row.values()
                          if isinstance(value, str)
                          and _TIMESTAMP_RE.match(value.strip())),
                         default=None)
            hhmm = row_ts[11:16] if row_ts and len(row_ts) >= 16 else None
            for key, value in row.items():
                if not isinstance(value, str):
                    continue
                pointer = '/*/%s' % key
                entry = counters.setdefault(
                    pointer, {'distinct': set(), 'total': 0,
                              'profile': {}, 'overflow': False})
                # Exact distinct counts: "0 duplicate transaction ids in
                # 376k rows" is only auditable with the real number. Memory
                # is bounded by the decompression caps upstream.
                entry['total'] += 1
                entry['distinct'].add(value)
                if _TIMESTAMP_RE.match(value.strip()):
                    check = order_checks.setdefault(
                        pointer, {'previous': None, 'violations': 0})
                    if check['previous'] is not None and value < check['previous']:
                        check['violations'] += 1
                    check['previous'] = value
                    continue
                if not entry['overflow'] and _ENUM_VALUE_RE.match(value) \
                        and not _ISIN_RE.match(value):
                    stats = entry['profile'].setdefault(
                        value, {'count': 0, 'first': None, 'last': None})
                    stats['count'] += 1
                    if hhmm is not None:
                        stats['first'] = min(stats['first'] or hhmm, hhmm)
                        stats['last'] = max(stats['last'] or hhmm, hhmm)
                    if len(entry['profile']) > _ENUM_MAX_DISTINCT:
                        entry['overflow'] = True
                        entry['profile'] = {}
        for pointer, entry in counters.items():
            cardinality[pointer] = ValueCardinality(
                path=pointer, distinct=len(entry['distinct']),
                total=entry['total'])
            if entry['profile'] and not entry['overflow']:
                profiles[pointer] = EnumTimeProfile(
                    path=pointer,
                    values=tuple(
                        EnumValueProfile(value=value, count=stats['count'],
                                         first_hhmm=stats['first'] or '',
                                         last_hhmm=stats['last'] or '')
                        for value, stats in sorted(entry['profile'].items())))

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
        identifier_paths=tuple(sorted(identifier_paths)),
        value_cardinality=tuple(
            cardinality[key] for key in sorted(cardinality)),
        order_violations=tuple(
            OrderCheck(path=key, violations=check['violations'])
            for key, check in sorted(order_checks.items())),
        enum_time_profiles=tuple(
            profiles[key] for key in sorted(profiles)))


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
