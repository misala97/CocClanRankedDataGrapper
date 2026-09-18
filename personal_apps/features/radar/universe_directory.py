# personal_apps/features/radar/universe_directory.py
"""The Nasdaq Trader symbol-directory contract, pinned per file and column.

Two files, two column namespaces, one authority table. `nasdaqlisted.txt`
publishes a `Market Category` listing tier and `otherlisted.txt` publishes a
listing `Exchange`, and Nasdaq's own definitions page reuses `Q` and `G`
inside `nasdaqlisted.txt`'s `Financial Status` column with unrelated meanings
(`Q` is bankruptcy there, not Global Select). The two listing namespaces are
disjoint only by accident, so a code is resolved by `(source_kind, code)` and
a code belonging to the other file resolves to nothing.

Everything here is pure: bytes in, an immutable snapshot out, and on any
problem a single exception carrying every problem found. Nothing is fetched,
written, guessed or repaired. An unrecognised listing code is quarantined --
never turned into `XNAS`, `XXXX` or any other stand-in, because a fallback row
is indistinguishable from a legitimately-Nasdaq one and a new US listing venue
would arrive exactly as an unrecognised code.

Sources, confirmed 2026-09-17 and recorded in
`radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md`: Nasdaq Trader's *Symbol
Look-Up/Directory Data Fields & Definitions* for the code meanings, and the
ISO 10383 registry publication of 14 September 2026 for every MIC, its type
and its operating MIC. All eight MICs are ACTIVE, US and unexpired.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import pathlib
import re
from typing import Literal

SourceKind = Literal['nasdaqlisted', 'otherlisted']


class SourceKindError(ValueError):
    """A file was bound to something other than the two documented sources."""


class DirectoryValidationError(Exception):
    """Every problem one directory file has, reported together.

    A validator that stops at the first problem turns one bad publication into
    a sequence of re-runs. `problems` is ordered deterministically so two runs
    over the same bytes produce the same report.
    """

    def __init__(self, path, problems):
        self.path = str(path)
        self.problems = tuple(problems)
        super().__init__(f'{self.path}: ' + '; '.join(self.problems))


@dataclasses.dataclass(frozen=True)
class VenueRule:
    """One directory code and the listing venue it names.

    `mic` is the listing segment, which is the information the directory field
    exists to carry. `operating_mic` is recorded beside it, never in place of
    it: the segment-to-operator rollup is a lookup any consumer can do, while
    the reverse does not exist (D1).
    """
    code: str
    mic: str
    venue: str
    mic_type: str
    operating_mic: str


#: The complete authority table. `mic_type` is ISO 10383's OPRT/SGMT
#: enumeration; three of these are operating MICs or a segment of a
#: third-party operator, because the register holds no narrower code for NYSE
#: equities or IEX equities. That asymmetry is the register's, not a defect.
VENUE_RULES: dict[tuple[str, str], VenueRule] = {
    ('nasdaqlisted', 'Q'): VenueRule('Q', 'XNGS', 'Nasdaq Global Select',
                                     'SGMT', 'XNAS'),
    ('nasdaqlisted', 'G'): VenueRule('G', 'XNMS', 'Nasdaq Global Market',
                                     'SGMT', 'XNAS'),
    ('nasdaqlisted', 'S'): VenueRule('S', 'XNCM', 'Nasdaq Capital Market',
                                     'SGMT', 'XNAS'),
    ('otherlisted', 'N'): VenueRule('N', 'XNYS', 'NYSE', 'OPRT', 'XNYS'),
    ('otherlisted', 'A'): VenueRule('A', 'XASE', 'NYSE American', 'SGMT',
                                    'XNYS'),
    ('otherlisted', 'P'): VenueRule('P', 'ARCX', 'NYSE Arca', 'SGMT', 'XNYS'),
    ('otherlisted', 'Z'): VenueRule('Z', 'BATS', 'Cboe BZX', 'SGMT', 'XCBO'),
    ('otherlisted', 'V'): VenueRule('V', 'IEXG', 'IEX', 'OPRT', 'IEXG'),
}

#: Every listing MIC the directory can legitimately produce. `XNAS` is a
#: Nasdaq operating MIC and is deliberately absent: no listing resolves to it.
KNOWN_LISTING_MICS = frozenset(rule.mic for rule in VENUE_RULES.values())

NASDAQ_HEADER = ('Symbol', 'Security Name', 'Market Category', 'Test Issue',
                 'Financial Status', 'Round Lot Size', 'ETF', 'NextShares')
OTHER_HEADER = ('ACT Symbol', 'Security Name', 'Exchange', 'CQS Symbol', 'ETF',
                'Round Lot Size', 'Test Issue', 'NASDAQ Symbol')

HEADERS: dict[str, tuple[str, ...]] = {
    'nasdaqlisted': NASDAQ_HEADER,
    'otherlisted': OTHER_HEADER,
}
#: Which column carries the symbol and which carries the listing code, per
#: file. Neither is ever resolved by preference order across aliases.
SYMBOL_COLUMN = {'nasdaqlisted': 'Symbol', 'otherlisted': 'ACT Symbol'}
CODE_COLUMN = {'nasdaqlisted': 'Market Category', 'otherlisted': 'Exchange'}

#: One accepted basename per documented file. Every caller binds its inputs
#: through `source_kind_for`, so a file whose shape is unknown can never reach
#: a parser, an upsert or a reconciliation.
SOURCE_FILENAMES = {f'{kind}.txt': kind for kind in HEADERS}

#: The only symbol form that becomes a Radar identity. Every NYSE-family
#: class share, warrant and preferred carries a dot or a space and is dropped
#: here rather than mangled; 541 rows of the 2026-09-16 `otherlisted.txt`.
SYMBOL_FORM = re.compile(r'^[A-Z]{1,5}$')
FOOTER_PREFIX = 'File Creation Time:'
#: `MMDDYYYYHH:MM`, padded with pipes to a width the two files disagree about.
FOOTER = re.compile(r'^File Creation Time: (\d{10}:\d{2})\|*$')
BOM = b'\xef\xbb\xbf'


@dataclasses.dataclass(frozen=True)
class DirectoryRow:
    """One usable listing. `is_etf` is the directory's own Y/N answer."""
    symbol: str
    name: str
    exchange_code: str
    is_etf: bool
    source_kind: str

    @property
    def venue_rule(self) -> VenueRule | None:
        return venue_rule(self.source_kind, self.exchange_code)


@dataclasses.dataclass(frozen=True)
class DirectorySnapshot:
    """One validated file: its usable rows and the provenance of the bytes."""
    source_kind: str
    rows: tuple[DirectoryRow, ...]
    file_created_at: dt.datetime
    sha256: str
    bom_present: bool

    @property
    def mapping_source(self) -> str:
        """`radar_instruments.mapping_source` is 24 characters; this is 18."""
        return f'nasdaqdir-{self.file_created_at:%Y%m%d}'


def venue_rule(source_kind: str, code: str) -> VenueRule | None:
    """The listing venue for one code *in one file*, or None.

    None is the fail-closed answer for an unknown code, a code from the other
    file, and an unknown file. It never falls back to an operating MIC.
    """
    return VENUE_RULES.get((source_kind, code))


def source_kind_for(path) -> str:
    """The documented source kind a path is bound to, or refuse.

    Basename binding, not sniffing: which column carries the listing code
    depends on which file it came from, so a caller that cannot name the file
    cannot be allowed to guess it.
    """
    name = pathlib.PurePath(path).name
    kind = SOURCE_FILENAMES.get(name)
    if kind is None:
        raise SourceKindError(
            f'{path}: expected one of {", ".join(sorted(SOURCE_FILENAMES))}; '
            f'the listing code depends on which file it came from')
    return kind


def require_source_kind(source_kind: str) -> str:
    if source_kind not in HEADERS:
        raise SourceKindError(
            f'unknown directory source kind: {source_kind!r}; '
            f'expected one of {", ".join(sorted(HEADERS))}')
    return source_kind


def parse_directory(path, source_kind: SourceKind) -> DirectorySnapshot:
    """Parse and validate one directory file, or raise with every problem.

    The source kind is supplied by the caller and never inferred from the
    filename or the header; the pinned header then proves the caller bound the
    file it meant to. The bytes are read once, hashed exactly as read, and
    decoded from that same buffer, so the recorded hash is always the hash of
    what was parsed.
    """
    require_source_kind(source_kind)
    path = pathlib.Path(path)
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    bom_present = raw.startswith(BOM)

    problems: list[str] = []
    header = HEADERS[source_kind]
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise DirectoryValidationError(path, [f'not valid UTF-8: {exc}'])

    lines = text.splitlines()
    if not lines:
        raise DirectoryValidationError(path, ['the file is empty'])

    found_header = tuple(lines[0].split('|'))
    if found_header != header:
        problems.append(
            f'header does not match the documented {source_kind} columns: '
            f'expected {"|".join(header)}, found {"|".join(found_header)}')
        # Nothing below can be trusted once the columns are unknown.
        raise DirectoryValidationError(path, problems)

    created_at, body = _split_footer(lines[1:], problems)
    rows = _usable_rows(body, source_kind, header, problems)

    if problems:
        raise DirectoryValidationError(path, problems)
    return DirectorySnapshot(source_kind=source_kind, rows=tuple(rows),
                             file_created_at=created_at, sha256=sha256,
                             bom_present=bom_present)


def validate_pair(nasdaq: DirectorySnapshot,
                  other: DirectorySnapshot) -> None:
    """Refuse a pair that is not one of each file, or that overlaps.

    A symbol in both files is either a parse error or a directory change, and
    either way the pair may not be used: the seed's first-file-wins rule would
    silently pick a venue.
    """
    problems: list[str] = []
    if (nasdaq.source_kind, other.source_kind) != ('nasdaqlisted',
                                                   'otherlisted'):
        problems.append(
            f'expected one nasdaqlisted and one otherlisted snapshot, got '
            f'{nasdaq.source_kind} and {other.source_kind}')
        raise DirectoryValidationError('<pair>', problems)

    overlap = sorted({row.symbol for row in nasdaq.rows} &
                     {row.symbol for row in other.rows})
    if overlap:
        problems.append(
            f'{len(overlap)} symbol(s) appear in both files: '
            f'{", ".join(overlap[:20])}')
    if problems:
        raise DirectoryValidationError('<pair>', problems)


def _split_footer(lines, problems):
    """Return `(creation time, data lines)`, recording any footer problem."""
    marked = [index for index, line in enumerate(lines)
              if line.startswith(FOOTER_PREFIX)]
    if not marked:
        problems.append('no creation time footer')
        return None, lines
    if len(marked) > 1:
        problems.append(f'{len(marked)} creation time footers; expected one')
        return None, [line for index, line in enumerate(lines)
                      if index not in set(marked)]
    index = marked[0]
    if index != len(lines) - 1:
        problems.append('the creation time footer is not the last line')
    match = FOOTER.match(lines[index])
    created_at = None
    if match is None:
        problems.append(
            f'creation time is not File Creation Time: MMDDYYYYHH:MM '
            f'({lines[index]!r})')
    else:
        try:
            created_at = dt.datetime.strptime(match.group(1), '%m%d%Y%H:%M')
        except ValueError:
            problems.append(f'creation time is not a real timestamp '
                            f'({match.group(1)!r})')
    return created_at, [line for i, line in enumerate(lines) if i != index]


def _usable_rows(body, source_kind, header, problems):
    """The rows that become identities, with every row-level problem recorded.

    Two exclusions are ordinary and must not fail the file: Nasdaq's own test
    issues (which carry listing codes outside the eight -- the retained
    `otherlisted.txt` has `F` and `M` on test rows) and symbol forms the
    extractor cannot match. Everything after those two filters is a listing
    this contract claims to understand, so an unexpected ETF value, an
    unknown code or a duplicate symbol is a failure of the file.
    """
    symbol_at = header.index(SYMBOL_COLUMN[source_kind])
    code_at = header.index(CODE_COLUMN[source_kind])
    etf_at = header.index('ETF')
    test_at = header.index('Test Issue')
    name_at = header.index('Security Name')

    rows: list[DirectoryRow] = []
    seen: dict[str, int] = {}
    for offset, line in enumerate(body):
        # Line 1 is the header and the footer has been removed already.
        number = offset + 2
        cells = line.split('|')
        if len(cells) != len(header):
            problems.append(f'line {number}: row width {len(cells)}, '
                            f'expected {len(header)}')
            continue
        # Checked before anything is skipped: an unexpected value here could
        # otherwise let one of Nasdaq's own dummy listings through as real.
        test_issue = cells[test_at].strip().upper()
        if test_issue not in ('Y', 'N'):
            problems.append(f'line {number}: Test Issue '
                            f'{cells[test_at]!r}; the documented values are '
                            f'Y and N')
            continue
        if test_issue == 'Y':
            continue
        symbol = cells[symbol_at].strip()
        if not SYMBOL_FORM.match(symbol):
            continue

        if symbol in seen:
            problems.append(f'line {number}: duplicate symbol {symbol} '
                            f'(first seen on line {seen[symbol]})')
            continue
        seen[symbol] = number

        etf = cells[etf_at].strip().upper()
        if etf not in ('Y', 'N'):
            problems.append(f'line {number}: {symbol} has ETF {etf!r}; '
                            f'the documented values are Y and N')
            continue

        code = cells[code_at].strip()
        if venue_rule(source_kind, code) is None:
            problems.append(
                f'line {number}: {symbol} is quarantined -- listing code '
                f'{code!r} is not a documented {source_kind} value')
            continue

        rows.append(DirectoryRow(symbol=symbol, name=cells[name_at].strip(),
                                 exchange_code=code,
                                 is_etf=(etf == 'Y'), source_kind=source_kind))
    return rows
