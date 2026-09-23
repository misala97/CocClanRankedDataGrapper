# personal_apps/tests/test_radar_universe_directory.py
"""The Nasdaq Trader directory contract, pinned to the two documented files.

Every rule here is an official one. `nasdaqlisted.txt` publishes a `Market
Category` tier and `otherlisted.txt` publishes a listing `Exchange`, and the
two code namespaces are only disjoint by accident -- Nasdaq reuses `Q` and `G`
inside `nasdaqlisted.txt`'s own `Financial Status` column with unrelated
meanings. A parser that resolves a code without knowing which file and which
column it came from is therefore one column away from assigning the wrong
venue, which is why the contract is keyed by `(source_kind, code)` and refuses
a code that belongs to the other file.

The old seed parser accepted a `Listing Exchange` alias belonging to
`nasdaqtraded.txt`, a file Nasdaq publishes no field definitions for at all.
There is no authoritative meaning for the letters in that column, so it may
never supply a listing code again.
"""
import datetime as dt
import hashlib

import pytest

from features.radar.universe_directory import (
    DirectoryValidationError, NASDAQ_HEADER, OTHER_HEADER, SourceKindError,
    parse_directory, validate_pair, venue_rule,
)

CREATED = 'File Creation Time: 0915202618:01'
CREATED_AT = dt.datetime(2026, 9, 15, 18, 1)

NASDAQ_ROWS = (
    'AAAA|Alpha Fund ETF|G|N|N|100|Y|N',
    'BBBB|Beta Corp. - Common Stock|Q|N|N|100|N|N',
    'CCCC|Gamma Inc. - Common Stock|S|N|N|100|N|N',
)
OTHER_ROWS = (
    'DDDD|Delta Industries, Inc. Common Stock|N|DDDD|N|100|N|DDDD',
    'EEEE|Epsilon Trust|P|EEEE|Y|100|N|EEEE',
)


def _write(tmp_path, name, header, rows, *, footer=CREATED, bom=False,
           trailing_pipes=None):
    """One directory file, written exactly as Nasdaq publishes them: CRLF
    line endings, a pipe-padded creation-time footer and a final newline."""
    if trailing_pipes is None:
        trailing_pipes = len(header) - 1
    lines = ['|'.join(header), *rows]
    if footer is not None:
        lines.append(footer + '|' * trailing_pipes)
    raw = ('\r\n'.join(lines) + '\r\n').encode('utf-8')
    if bom:
        raw = b'\xef\xbb\xbf' + raw
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def _nasdaq(tmp_path, rows=NASDAQ_ROWS, **kwargs):
    return _write(tmp_path, 'nasdaqlisted.txt', NASDAQ_HEADER, rows, **kwargs)


def _other(tmp_path, rows=OTHER_ROWS, **kwargs):
    return _write(tmp_path, 'otherlisted.txt', OTHER_HEADER, rows,
                  trailing_pipes=kwargs.pop('trailing_pipes', 6), **kwargs)


def _problems(excinfo):
    return excinfo.value.problems


# --- the eight authority rules -------------------------------------------------

def test_the_eight_confirmed_codes_resolve_per_file():
    """ISO 10383, September 2026: all eight are ACTIVE US listing MICs."""
    assert venue_rule('nasdaqlisted', 'Q') == venue_rule('nasdaqlisted', 'Q')
    assert (venue_rule('nasdaqlisted', 'Q').code,
            venue_rule('nasdaqlisted', 'Q').mic,
            venue_rule('nasdaqlisted', 'Q').venue,
            venue_rule('nasdaqlisted', 'Q').mic_type,
            venue_rule('nasdaqlisted', 'Q').operating_mic) == (
        'Q', 'XNGS', 'Nasdaq Global Select', 'SGMT', 'XNAS')
    assert venue_rule('nasdaqlisted', 'G').mic == 'XNMS'
    assert venue_rule('nasdaqlisted', 'S').mic == 'XNCM'
    assert venue_rule('otherlisted', 'N').mic == 'XNYS'
    assert venue_rule('otherlisted', 'A').mic == 'XASE'
    assert venue_rule('otherlisted', 'P').mic == 'ARCX'
    assert venue_rule('otherlisted', 'Z').mic == 'BATS'
    assert venue_rule('otherlisted', 'V').mic == 'IEXG'


def test_a_code_from_the_wrong_file_resolves_to_nothing():
    """`Q` is a Nasdaq tier and never an other-listed exchange; `N` is NYSE
    and never a Nasdaq tier. One flat table would answer both."""
    assert venue_rule('otherlisted', 'Q') is None
    assert venue_rule('nasdaqlisted', 'N') is None
    assert venue_rule('nasdaqlisted', 'Z') is None
    assert venue_rule('otherlisted', 'G') is None
    assert venue_rule('otherlisted', 'S') is None


def test_segment_mics_record_their_operator_instead_of_becoming_it():
    """D1: the tier is the information the directory exists to carry, so the
    operating MIC is recorded beside it and never in place of it."""
    tiers = [venue_rule('nasdaqlisted', code) for code in ('Q', 'G', 'S')]
    assert [rule.mic for rule in tiers] == ['XNGS', 'XNMS', 'XNCM']
    assert {rule.operating_mic for rule in tiers} == {'XNAS'}
    assert {rule.mic_type for rule in tiers} == {'SGMT'}
    assert 'XNAS' not in {rule.mic for rule in tiers}

    assert (venue_rule('otherlisted', 'N').mic_type,
            venue_rule('otherlisted', 'N').operating_mic) == ('OPRT', 'XNYS')
    assert (venue_rule('otherlisted', 'V').mic_type,
            venue_rule('otherlisted', 'V').operating_mic) == ('OPRT', 'IEXG')
    assert venue_rule('otherlisted', 'Z').operating_mic == 'XCBO'
    assert venue_rule('otherlisted', 'A').operating_mic == 'XNYS'
    assert venue_rule('otherlisted', 'P').operating_mic == 'XNYS'


def test_a_venue_rule_is_immutable():
    rule = venue_rule('nasdaqlisted', 'Q')
    with pytest.raises(Exception):
        rule.mic = 'XNAS'


def test_an_unknown_source_kind_is_refused_rather_than_guessed(tmp_path):
    path = _nasdaq(tmp_path)
    assert venue_rule('nasdaqtraded', 'Q') is None
    with pytest.raises(SourceKindError):
        parse_directory(path, 'nasdaqtraded')


# --- parsing the documented shape ----------------------------------------------

def test_a_good_pair_parses_into_immutable_snapshots(tmp_path):
    nasdaq = parse_directory(_nasdaq(tmp_path), 'nasdaqlisted')
    other = parse_directory(_other(tmp_path), 'otherlisted')

    assert nasdaq.source_kind == 'nasdaqlisted'
    assert [row.symbol for row in nasdaq.rows] == ['AAAA', 'BBBB', 'CCCC']
    assert [row.exchange_code for row in nasdaq.rows] == ['G', 'Q', 'S']
    assert [row.is_etf for row in nasdaq.rows] == [True, False, False]
    assert nasdaq.rows[1].name == 'Beta Corp. - Common Stock'
    assert {row.source_kind for row in nasdaq.rows} == {'nasdaqlisted'}
    assert nasdaq.file_created_at == CREATED_AT
    assert other.file_created_at == CREATED_AT
    assert [row.symbol for row in other.rows] == ['DDDD', 'EEEE']
    assert [row.exchange_code for row in other.rows] == ['N', 'P']
    validate_pair(nasdaq, other)


def test_the_snapshot_hashes_the_exact_bytes_it_parsed(tmp_path):
    path = _nasdaq(tmp_path)
    snapshot = parse_directory(path, 'nasdaqlisted')
    assert snapshot.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert snapshot.bom_present is False


def test_a_utf8_bom_is_accepted_and_recorded(tmp_path):
    """The 2026-09-16 capture proved Nasdaq sent no BOM, but a decoded copy
    can carry one; it is a fact about the file, not a parse failure."""
    path = _nasdaq(tmp_path, bom=True)
    snapshot = parse_directory(path, 'nasdaqlisted')
    assert snapshot.bom_present is True
    assert [row.symbol for row in snapshot.rows] == ['AAAA', 'BBBB', 'CCCC']
    assert snapshot.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert not snapshot.rows[0].symbol.startswith('﻿')


def test_the_creation_time_footer_is_parsed_from_its_pinned_format(tmp_path):
    path = _nasdaq(tmp_path, footer='File Creation Time: 0102202603:04')
    assert parse_directory(path, 'nasdaqlisted').file_created_at == \
        dt.datetime(2026, 1, 2, 3, 4)


def test_the_other_listed_footer_carries_one_fewer_pipe(tmp_path):
    """Nasdaq pads the two footers differently; the contract matches the
    prefix and the timestamp, not the padding width."""
    path = _other(tmp_path, trailing_pipes=6)
    assert parse_directory(path, 'otherlisted').file_created_at == CREATED_AT


# --- fail-closed validation ----------------------------------------------------

def test_a_renamed_header_column_is_refused(tmp_path):
    header = list(NASDAQ_HEADER)
    header[2] = 'Listing Exchange'
    path = _write(tmp_path, 'nasdaqlisted.txt', header, NASDAQ_ROWS)
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('header' in problem for problem in _problems(excinfo))


def test_a_listing_exchange_file_can_never_supply_a_code(tmp_path):
    """`Listing Exchange` belongs to `nasdaqtraded.txt`, for which Nasdaq
    publishes no field definitions. It is not an alias for anything."""
    header = ('Symbol', 'Security Name', 'Listing Exchange', 'Test Issue',
              'Financial Status', 'Round Lot Size', 'ETF', 'NextShares')
    rows = ('AAAA|Alpha Fund ETF|G|N|N|100|Y|N',)
    path = _write(tmp_path, 'nasdaqtraded.txt', header, rows)
    for kind in ('nasdaqlisted', 'otherlisted'):
        with pytest.raises(DirectoryValidationError):
            parse_directory(path, kind)


def test_a_missing_header_column_is_refused(tmp_path):
    header = [name for name in NASDAQ_HEADER if name != 'NextShares']
    path = _write(tmp_path, 'nasdaqlisted.txt', header,
                  ('AAAA|Alpha Fund ETF|G|N|N|100|Y',),
                  trailing_pipes=6)
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('header' in problem for problem in _problems(excinfo))


def test_an_extra_header_column_is_refused(tmp_path):
    header = (*NASDAQ_HEADER, 'Extra')
    path = _write(tmp_path, 'nasdaqlisted.txt', header,
                  ('AAAA|Alpha Fund ETF|G|N|N|100|Y|N|x',))
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('header' in problem for problem in _problems(excinfo))


def test_the_other_listed_header_is_refused_for_the_nasdaq_kind(tmp_path):
    """Source kind is supplied, never inferred; the header then proves the
    caller bound the right file."""
    path = _write(tmp_path, 'otherlisted.txt', OTHER_HEADER, OTHER_ROWS,
                  trailing_pipes=6)
    with pytest.raises(DirectoryValidationError):
        parse_directory(path, 'nasdaqlisted')


def test_a_short_data_row_is_refused(tmp_path):
    path = _nasdaq(tmp_path, rows=(*NASDAQ_ROWS, 'DDDD|Short Corp|Q|N|N'))
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('width' in problem for problem in _problems(excinfo))


def test_a_long_data_row_is_refused(tmp_path):
    path = _nasdaq(tmp_path,
                   rows=(*NASDAQ_ROWS, 'DDDD|Long Corp|Q|N|N|100|N|N|extra'))
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('width' in problem for problem in _problems(excinfo))


def test_a_missing_footer_is_refused(tmp_path):
    path = _nasdaq(tmp_path, footer=None)
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('creation time' in problem for problem in _problems(excinfo))


def test_a_duplicate_footer_is_refused(tmp_path):
    path = _nasdaq(tmp_path, rows=(CREATED + '|||||||', *NASDAQ_ROWS))
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('creation time' in problem for problem in _problems(excinfo))


def test_a_malformed_creation_time_is_refused(tmp_path):
    path = _nasdaq(tmp_path, footer='File Creation Time: 2026-09-15 18:01')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('creation time' in problem for problem in _problems(excinfo))


def test_an_impossible_creation_time_is_refused(tmp_path):
    path = _nasdaq(tmp_path, footer='File Creation Time: 1332202699:99')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(path, 'nasdaqlisted')
    assert any('creation time' in problem for problem in _problems(excinfo))


def test_an_empty_file_is_refused(tmp_path):
    path = tmp_path / 'nasdaqlisted.txt'
    path.write_bytes(b'')
    with pytest.raises(DirectoryValidationError):
        parse_directory(path, 'nasdaqlisted')


# --- row-level rules -----------------------------------------------------------

def test_test_issues_are_excluded_without_failing_the_file(tmp_path):
    """Nasdaq's own dummy listings carry codes outside the eight -- the
    retained 2026-09-16 `otherlisted.txt` has `F` and `M` on test rows -- so
    they must be dropped before the code is ever resolved."""
    rows = (*NASDAQ_ROWS, 'ZZZT|Nasdaq Test Security|G|Y|N|100|N|N')
    snapshot = parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    assert [row.symbol for row in snapshot.rows] == ['AAAA', 'BBBB', 'CCCC']

    other_rows = (*OTHER_ROWS,
                  'ZZZTX|TXSE Test Stk 5 Common Stock|F|ZZZTX|N|40|Y|ZZZTX')
    other = parse_directory(_other(tmp_path, rows=other_rows), 'otherlisted')
    assert [row.symbol for row in other.rows] == ['DDDD', 'EEEE']


def test_symbols_outside_the_matchable_form_are_excluded(tmp_path):
    """541 of `otherlisted.txt`'s rows carry dots or spaces. They are not
    Radar identities and they are not an error in the file."""
    rows = (*OTHER_ROWS,
            'BRK.B|Berkshire Hathaway Inc. Class B|N|BRK B|N|100|N|',
            'FFFFFF|Six Letter Corp|N|FFFFFF|N|100|N|FFFFFF',
            'gggg|Lowercase Corp|N|gggg|N|100|N|gggg')
    snapshot = parse_directory(_other(tmp_path, rows=rows), 'otherlisted')
    assert [row.symbol for row in snapshot.rows] == ['DDDD', 'EEEE']


def test_an_unexpected_test_issue_value_is_refused(tmp_path):
    """Only `Y` rows are skipped, so any other non-`N` value would let one of
    Nasdaq's dummy listings through as a real one."""
    for value in ('', 'X', 'Yes'):
        rows = (*NASDAQ_ROWS,
                f'ZZZT|Nasdaq Test Security|G|{value}|N|100|N|N')
        with pytest.raises(DirectoryValidationError) as excinfo:
            parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
        assert any('Test Issue' in problem for problem in _problems(excinfo))


def test_a_blank_etf_flag_is_refused(tmp_path):
    """Both documented files carry the column on every row; a blank one means
    the file changed shape, not that the listing is a stock."""
    rows = (*NASDAQ_ROWS, 'DDDD|Delta Corp. - Common Stock|Q|N|N|100||N')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    assert any('ETF' in problem for problem in _problems(excinfo))


def test_an_unexpected_etf_value_is_refused(tmp_path):
    rows = (*NASDAQ_ROWS, 'DDDD|Delta Corp. - Common Stock|Q|N|N|100|X|N')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    assert any('ETF' in problem for problem in _problems(excinfo))


def test_a_duplicate_symbol_within_one_file_is_refused(tmp_path):
    rows = (*NASDAQ_ROWS, 'AAAA|Alpha Fund ETF Again|Q|N|N|100|Y|N')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    assert any('duplicate' in problem for problem in _problems(excinfo))


def test_an_unknown_code_quarantines_the_row_and_fails_the_file(tmp_path):
    """D8: an unrecognised listing code is never mapped to a fallback MIC.
    A new US listing venue would arrive exactly this way."""
    rows = (*NASDAQ_ROWS, 'DDDD|Delta Corp. - Common Stock|X|N|N|100|N|N')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    problems = _problems(excinfo)
    assert any('DDDD' in problem and 'X' in problem for problem in problems)
    assert not any('XNAS' in problem or 'XXXX' in problem
                   for problem in problems)


def test_a_code_belonging_to_the_other_file_fails_the_file(tmp_path):
    """The namespaces are disjoint today by accident, not by design."""
    rows = (*NASDAQ_ROWS, 'DDDD|Delta Corp. - Common Stock|N|N|N|100|N|N')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    assert any('DDDD' in problem for problem in _problems(excinfo))

    other_rows = (*OTHER_ROWS, 'FFFF|Foxtrot Corp|Q|FFFF|N|100|N|FFFF')
    with pytest.raises(DirectoryValidationError):
        parse_directory(_other(tmp_path, rows=other_rows), 'otherlisted')


# --- reporting and purity ------------------------------------------------------

def test_every_problem_is_reported_together_in_a_stable_order(tmp_path):
    rows = ('AAAA|Alpha Fund ETF|X|N|N|100|Y|N',
            'AAAA|Alpha Fund ETF Again|G|N|N|100||N',
            'CCCC|Gamma Inc.|S|N|N|100|N')
    with pytest.raises(DirectoryValidationError) as excinfo:
        parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    first = _problems(excinfo)
    assert len(first) >= 3
    with pytest.raises(DirectoryValidationError) as again:
        parse_directory(_nasdaq(tmp_path, rows=rows), 'nasdaqlisted')
    assert _problems(again) == first
    assert str(excinfo.value)


def test_a_refused_file_is_left_byte_identical(tmp_path):
    rows = (*NASDAQ_ROWS, 'DDDD|Delta Corp. - Common Stock|X|N|N|100|N|N')
    path = _nasdaq(tmp_path, rows=rows)
    before = path.read_bytes()
    with pytest.raises(DirectoryValidationError):
        parse_directory(path, 'nasdaqlisted')
    assert path.read_bytes() == before


def test_the_two_files_may_not_claim_the_same_symbol(tmp_path):
    nasdaq = parse_directory(_nasdaq(tmp_path), 'nasdaqlisted')
    overlap = (*OTHER_ROWS, 'BBBB|Beta Corp. Common Stock|N|BBBB|N|100|N|BBBB')
    other = parse_directory(_other(tmp_path, rows=overlap), 'otherlisted')
    with pytest.raises(DirectoryValidationError) as excinfo:
        validate_pair(nasdaq, other)
    assert any('BBBB' in problem for problem in _problems(excinfo))


def test_validate_pair_refuses_two_snapshots_of_the_same_kind(tmp_path):
    nasdaq = parse_directory(_nasdaq(tmp_path), 'nasdaqlisted')
    with pytest.raises(DirectoryValidationError):
        validate_pair(nasdaq, nasdaq)


def test_a_directory_row_is_immutable(tmp_path):
    row = parse_directory(_nasdaq(tmp_path), 'nasdaqlisted').rows[0]
    with pytest.raises(Exception):
        row.symbol = 'ZZZZ'


# --- the seed script now delegates ---------------------------------------------

def test_the_seed_script_binds_each_input_to_its_documented_file():
    from scripts import seed_radar_universe as seed

    assert seed.source_kind_for('nasdaqlisted.txt') == 'nasdaqlisted'
    assert seed.source_kind_for('/root/refresh/otherlisted.txt') == 'otherlisted'
    for name in ('nasdaqtraded.txt', 'listings.csv', 'nasdaqlisted.txt.bak',
                 'NASDAQLISTED.TXT'):
        with pytest.raises(SourceKindError):
            seed.source_kind_for(name)


def test_the_seed_script_yields_the_contract_rows(tmp_path):
    from scripts import seed_radar_universe as seed

    rows = list(seed.load_rows(_nasdaq(tmp_path), 'nasdaqlisted'))
    assert rows == [
        {'symbol': 'AAAA', 'name': 'Alpha Fund ETF', 'exchange': 'G',
         'is_etf': True},
        {'symbol': 'BBBB', 'name': 'Beta Corp. - Common Stock', 'exchange': 'Q',
         'is_etf': False},
        {'symbol': 'CCCC', 'name': 'Gamma Inc. - Common Stock', 'exchange': 'S',
         'is_etf': False},
    ]


def test_the_seed_script_no_longer_carries_generic_column_aliases():
    import inspect

    from scripts import seed_radar_universe as seed

    source = inspect.getsource(seed)
    assert 'Listing Exchange' not in source
    assert 'csv.DictReader' not in source


# --- the seed script validates the whole pair before the application ----------

class _Application:
    """Stands in for the Flask app and records being entered. Nothing here
    imports, configures or connects the real application or any database."""

    def __init__(self, events):
        self.events = events

    def app_context(self):
        import contextlib

        self.events.append('app_context')
        return contextlib.nullcontext()


@pytest.fixture()
def seed_run(monkeypatch):
    """Run the seed script's `main` as its command line would, with the
    application replaced by a recorder and the upsert by a stub. The real
    importer never runs here."""
    import sys
    import types

    from features.radar import universe
    from scripts import seed_radar_universe as seed

    events = []
    application = _Application(events)
    fake = types.ModuleType('app')

    def imported(name):
        # A module-level __getattr__: `from app import app` lands here, so
        # the import itself is recorded, not only entering the context.
        if name != 'app':
            raise AttributeError(name)
        events.append('import app')
        return application

    fake.__getattr__ = imported
    monkeypatch.setitem(sys.modules, 'app', fake)

    def upsert(rows, now):
        events.append(('upsert', [row['symbol'] for row in rows]))
        return {'added': len(rows), 'updated': 0, 'reassigned': 0,
                'flagged': 0}

    monkeypatch.setattr(universe, 'upsert_symbols', upsert)

    def run(*paths):
        monkeypatch.setattr(sys, 'argv', ['seed_radar_universe.py',
                                          *(str(path) for path in paths)])
        return seed.main()

    run.events = events
    return run


def test_the_seed_script_upserts_a_valid_pair_in_either_order(tmp_path,
                                                               seed_run):
    """The positive control for the refusals below: a valid pair reaches the
    application and the upsert, with rows in argument order as before."""
    nasdaq, other = _nasdaq(tmp_path), _other(tmp_path)

    assert seed_run(nasdaq, other) == 0
    assert seed_run(other, nasdaq) == 0
    assert seed_run.events == [
        'import app', 'app_context',
        ('upsert', ['AAAA', 'BBBB', 'CCCC', 'DDDD', 'EEEE']),
        'import app', 'app_context',
        ('upsert', ['DDDD', 'EEEE', 'AAAA', 'BBBB', 'CCCC'])]


@pytest.mark.parametrize('case, refusal', [
    ('only_nasdaq', DirectoryValidationError),
    ('only_other', DirectoryValidationError),
    ('nasdaq_twice', DirectoryValidationError),
    ('other_twice', DirectoryValidationError),
    ('unknown_file', SourceKindError),
])
def test_the_seed_script_refuses_anything_but_one_of_each_before_the_app(
        tmp_path, seed_run, case, refusal):
    nasdaq, other = _nasdaq(tmp_path), _other(tmp_path)
    again = tmp_path / 'again'
    again.mkdir()
    paths = {
        'only_nasdaq': (nasdaq,),
        'only_other': (other,),
        'nasdaq_twice': (nasdaq, other, _nasdaq(again)),
        'other_twice': (other, nasdaq, _other(again)),
        'unknown_file': (nasdaq, other,
                         _write(tmp_path, 'nasdaqtraded.txt', NASDAQ_HEADER,
                                NASDAQ_ROWS)),
    }[case]

    with pytest.raises(refusal):
        seed_run(*paths)
    assert seed_run.events == []


@pytest.mark.parametrize('reverse', [False, True],
                         ids=['nasdaq_first', 'other_first'])
def test_the_seed_script_refuses_a_cross_file_overlap_in_either_order(
        tmp_path, seed_run, reverse):
    """First-file-wins would silently pick a venue for BBBB, and which one
    would depend on argument order."""
    nasdaq = _nasdaq(tmp_path)
    other = _other(tmp_path, rows=(
        *OTHER_ROWS, 'BBBB|Beta Corp. Common Stock|N|BBBB|N|100|N|BBBB'))
    paths = (other, nasdaq) if reverse else (nasdaq, other)

    with pytest.raises(DirectoryValidationError) as excinfo:
        seed_run(*paths)
    assert any('BBBB' in problem for problem in _problems(excinfo))
    assert seed_run.events == []
