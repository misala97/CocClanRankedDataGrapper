# personal_apps/tests/test_radar_universe_reconcile.py
"""The dry-run reconciler: what the directory and the database disagree about.

Every cohort here is a *report*. The pure reconciler proposes exactly one
action -- inserting a US primary for an identity that has none -- and every
other disagreement resolves to observing, holding or reviewing. It may never
emit an update or a delete, because the MIC participates in
`uq_radar_quote_market` and `uq_radar_daily_close_market` and rewriting one
orphans stored history that cannot be recovered from a US row (no ISIN).
"""
import csv
import datetime as dt
import hashlib
import json

import pytest
import sqlalchemy as sa

from features.radar.universe_directory import DirectoryRow
from features.radar.universe_reconcile import (
    ApprovalError, CurrentIdentity, CurrentMapping, load_approved_mappings,
    reconcile,
)

SOURCE = 'nasdaqdir-20260915'
SHA = 'bd5524e05ab8530c482882df7f9eb109b9a9f96cf73dd67872ee911251262ddd'
OTHER_SHA = ('861023735ffebda2ede5059070f622d8ba2fb541'
             '75e78e5d73275b2701bd9b96')


def row(symbol, name=None, code='G', *, kind='nasdaqlisted', is_etf=False):
    return DirectoryRow(symbol=symbol, name=name or f'{symbol} Corp. - Common '
                        'Stock', exchange_code=code, is_etf=is_etf,
                        source_kind=kind)


def identity(symbol, name=None, code='G', *, is_etf=False, active=True):
    """Distinct issuer names by default: two rows sharing one issuer key are
    a corporate-action pair, which is a different cohort entirely."""
    return CurrentIdentity(symbol=symbol,
                           name=name or f'{symbol} Corp. - Common Stock',
                           exchange=code, is_etf=is_etf, active=active)


def mapping(ticker, mic='XNMS', *, venue='Nasdaq Global Market',
            provider_symbol=None, currency='USD', is_primary=True,
            status='mapped', market='us'):
    return CurrentMapping(ticker=ticker, market=market, mic=mic, venue=venue,
                          provider_symbol=provider_symbol or ticker,
                          currency=currency, is_primary=is_primary,
                          mapping_status=status)


def run(rows, identities, mappings=()):
    return reconcile(rows, identities, mappings, mapping_source=SOURCE)


def symbols(cohort):
    return [entry.symbol for entry in cohort]


# --- the one proposed action ---------------------------------------------------

def test_an_unmapped_active_common_listing_is_a_safe_candidate():
    result = run([row('SAFE')], [identity('SAFE')])

    assert symbols(result.safe_mapping_candidates) == ['SAFE']
    assert result.safe_mapping_candidates[0].symbol == 'SAFE'
    assert result.safe_mapping_candidates[0].market == 'us'
    assert result.safe_mapping_candidates[0].currency == 'USD'
    assert result.safe_mapping_candidates[0].provider_symbol == 'SAFE'
    assert result.safe_mapping_candidates[0].action == 'insert_us_primary'
    assert not result.non_common
    assert not result.conflicts
    assert not result.quarantined


def test_the_planned_mapping_is_exactly_the_contract_row():
    planned = run([row('SAFE', code='S')],
                  [identity('SAFE', code='S')]).safe_mapping_candidates[0].mapping

    assert planned.ticker == 'SAFE'
    assert planned.market == 'us'
    assert planned.venue == 'Nasdaq Capital Market'
    assert planned.mic == 'XNCM'
    assert planned.provider_symbol == 'SAFE'
    assert planned.currency == 'USD'
    assert planned.isin is None
    assert planned.is_primary is True
    assert planned.mapping_status == 'mapped'
    assert planned.mapping_source == SOURCE
    assert len(planned.mapping_source) <= 24


def test_a_fund_is_safe_and_the_etf_flag_alone_never_disqualifies_it():
    result = run([row('ETFX', 'Alpha Broad Market ETF', 'P',
                      kind='otherlisted', is_etf=True)],
                 [identity('ETFX', 'Alpha Broad Market ETF', 'P',
                           is_etf=True)])
    assert symbols(result.safe_mapping_candidates) == ['ETFX']
    assert result.safe_mapping_candidates[0].mic == 'ARCX'


def test_every_confirmed_code_produces_its_own_mic():
    rows, identities = [], []
    for symbol, code, kind in (('AAA', 'Q', 'nasdaqlisted'),
                               ('BBB', 'G', 'nasdaqlisted'),
                               ('CCC', 'S', 'nasdaqlisted'),
                               ('DDD', 'N', 'otherlisted'),
                               ('EEE', 'A', 'otherlisted'),
                               ('FFF', 'P', 'otherlisted'),
                               ('GGG', 'Z', 'otherlisted'),
                               ('HHH', 'V', 'otherlisted')):
        rows.append(row(symbol, f'{symbol} Corp. - Common Stock', code,
                        kind=kind))
        identities.append(identity(symbol, f'{symbol} Corp. - Common Stock',
                                   code))
    result = run(rows, identities)
    assert [c.mic for c in result.safe_mapping_candidates] == [
        'XNGS', 'XNMS', 'XNCM', 'XNYS', 'XASE', 'ARCX', 'BATS', 'IEXG']
    assert 'XNAS' not in {c.mic for c in result.safe_mapping_candidates}


# --- D3: non-common listings stay identities -----------------------------------

@pytest.mark.parametrize('symbol, name, hint', [
    ('AAAAW', 'Alpha Acquisition Corp - Warrants', 'warrant'),
    ('AAAAR', 'Alpha Acquisition Corp - Rights', 'right'),
    ('AAAAU', 'Alpha Acquisition Corp - Units', 'unit'),
    ('AAAAP', 'Alpha Corp. - Series A Preferred Stock', 'preferred'),
    ('AAAAN', 'Alpha Capital Corp 8.00% Notes due 2031', 'note'),
])
def test_each_non_common_class_is_identity_only(symbol, name, hint):
    result = run([row(symbol, name)], [identity(symbol, name)])

    assert symbols(result.non_common) == [symbol]
    assert result.non_common[0].action == 'identity_only'
    assert result.non_common[0].reason == hint
    assert not result.safe_mapping_candidates


def test_an_uncorroborated_derivative_word_is_quarantined_not_mapped():
    """'Limited Partnership Units' is ordinary equity. Ambiguity may never
    reach the safe set, and it may not be silently called a unit either."""
    name = 'Alpha Energy Partners LP - Limited Partnership Units'
    result = run([row('ALPH', name)], [identity('ALPH', name)])

    assert symbols(result.quarantined) == ['ALPH']
    assert result.quarantined[0].action == 'quarantine_no_mapping'
    assert not result.safe_mapping_candidates
    assert not result.non_common


# --- already mapped: nothing to do, or drift to preserve -----------------------

def test_an_existing_primary_produces_no_cohort_row_at_all():
    result = run([row('HELD')], [identity('HELD')], [mapping('HELD')])
    assert result.counts == {name: 0 for name in result.counts}


@pytest.mark.parametrize('symbol, stored, code, kind, drift', [
    ('EPRX', 'XNCM', 'Q', 'nasdaqlisted', 'T1'),
    ('FSHP', 'XNMS', 'S', 'nasdaqlisted', 'T1'),
    ('MVPA', 'ARCX', 'N', 'otherlisted', 'T2'),
    ('KHC', 'XNGS', 'N', 'otherlisted', 'T3'),
    ('OPAD', 'XNYS', 'S', 'nasdaqlisted', 'T3'),
])
def test_a_mic_difference_preserves_the_stored_mic_and_is_classed(
        symbol, stored, code, kind, drift):
    """D1: both sides of every drift row are ACTIVE ISO MICs, so this is a
    history-continuity question, not a repair. T1 keeps its operating MIC,
    T2 changes segment inside one operator, T3 changes the operator."""
    result = run([row(symbol, f'{symbol} Corp. - Common Stock', code,
                      kind=kind)],
                 [identity(symbol, f'{symbol} Corp. - Common Stock', code)],
                 [mapping(symbol, stored)])

    assert symbols(result.mic_drift) == [symbol]
    entry = result.mic_drift[0]
    assert entry.action == 'preserve_existing_mic'
    assert entry.reason == drift
    assert entry.stored_mic == stored
    assert entry.directory_mic != stored
    assert not result.safe_mapping_candidates
    assert not result.conflicts


def test_drift_rows_never_propose_a_new_mapping():
    result = run([row('KHC', 'Kraft Heinz Co. - Common Stock', 'N',
                      kind='otherlisted')],
                 [identity('KHC', 'Kraft Heinz Co. - Common Stock', 'N')],
                 [mapping('KHC', 'XNGS')])
    assert all(getattr(entry, 'mapping', None) is None
               for cohort in result.cohorts.values() for entry in cohort)


# --- D2: name changes are report-only ------------------------------------------

def test_a_first_token_change_is_reviewed_and_mutates_nothing():
    result = run([row('PMA', 'PMA Graphene Technology Group Inc. - Class A')],
                 [identity('PMA', 'Ming Shing Group Holdings Limited')],
                 [mapping('PMA')])

    assert symbols(result.name_review) == ['PMA']
    assert result.name_review[0].action == 'review_no_mutation'
    assert result.name_review[0].reason == 'first_token_changed'
    assert not result.safe_mapping_candidates
    assert not result.mic_drift


def test_a_same_issuer_rename_is_reported_without_action():
    result = run([row('ZONE', 'Zone Frontier Inc. - Common Stock')],
                 [identity('ZONE', 'Zone Frontier Corp. - Common Stock')],
                 [mapping('ZONE')])
    assert result.name_review[0].reason in {'cosmetic', 'security_description',
                                            'rename_same_first_token'}
    assert result.name_review[0].action == 'review_no_mutation'


@pytest.mark.parametrize('stored, listed, kind', [
    ('Alpha Corp. - Common Stock', 'Beta Holdings Inc. - Common Stock',
     'first_token_changed'),
    ('Zeta Frontier Corp. - Common Stock', 'Zeta Pioneer Inc. - Common Stock',
     'rename_same_first_token'),
    ('Alpha Corp. - Common Stock', 'Alpha Corp. - Class A Common Stock',
     'security_description'),
    ('Alpha Corp. - Common Stock', 'Alpha Corp - Common Stock', 'cosmetic'),
], ids=['first_token_changed', 'rename_same_first_token',
        'security_description', 'cosmetic'])
def test_an_unmapped_identity_whose_name_changed_is_reviewed_not_mapped(
        stored, listed, kind):
    """D2 applies before the safe set, not only to mapped rows. An unmapped
    identity is a candidate only while its stored name is the name the
    directory lists; a new company on a reused symbol, or the same company
    renamed, is held for review and never mapped automatically."""
    result = run([row('RENM', listed)], [identity('RENM', stored)])

    assert symbols(result.name_review) == ['RENM']
    assert result.name_review[0].action == 'review_no_mutation'
    assert result.name_review[0].reason == kind
    assert not result.safe_mapping_candidates


def test_a_ticker_change_pair_is_reviewed_as_a_corporate_action():
    """An absence and an addition sharing an issuer are one event. The four
    JAB/ATLQ rows are the measured case: the old mappings collect nothing
    while the new symbols have none."""
    result = run(
        [row('ATLQ', 'JAB Acquisition Corp I - Class A Ordinary Shares'),
         row('ATLQW', 'JAB Acquisition Corp I - Warrants')],
        [identity('ATLQ', 'JAB Acquisition Corp I - Class A Ordinary Shares'),
         identity('ATLQW', 'JAB Acquisition Corp I - Warrants'),
         identity('JAB', 'JAB Acquisition Corp I - Class A Ordinary Shares')],
        [mapping('JAB')])

    assert symbols(result.name_review) == ['ATLQ', 'ATLQW']
    assert {entry.reason for entry in result.name_review} == {
        'corporate_action_pair'}
    assert symbols(result.absent) == ['JAB']
    assert not result.safe_mapping_candidates
    assert not result.non_common


# --- absence, conflicts, quarantine --------------------------------------------

def test_an_identity_absent_from_the_directory_is_observed_only():
    result = run([row('HERE')], [identity('HERE'), identity('GONE')],
                 [mapping('HERE'), mapping('GONE')])

    assert symbols(result.absent) == ['GONE']
    assert result.absent[0].action == 'observe_only'
    assert result.absent[0].reason == 'directory_absent'


def test_absence_never_proposes_a_delisting_or_an_unmapping():
    result = run([], [identity('GONE')], [mapping('GONE')])
    actions = {entry.action for cohort in result.cohorts.values()
               for entry in cohort}
    assert actions == {'observe_only'}
    assert not any('delete' in action or 'update' in action
                   or 'delist' in action or 'unmap' in action
                   for action in actions)


def test_an_inactive_identity_is_a_conflict_not_a_candidate():
    result = run([row('DEAD')], [identity('DEAD', active=False)])

    assert symbols(result.conflicts) == ['DEAD']
    assert result.conflicts[0].reason == 'identity_inactive'
    assert not result.safe_mapping_candidates


def test_an_existing_us_row_that_is_not_a_mapped_primary_is_a_conflict():
    result = run([row('HELD')], [identity('HELD')],
                 [mapping('HELD', status='held', is_primary=False)])

    assert symbols(result.conflicts) == ['HELD']
    assert result.conflicts[0].reason == 'us_instrument_row_exists'
    assert not result.safe_mapping_candidates


def test_a_provider_symbol_already_owned_is_a_conflict():
    """The grouped identity map drops both sides of a shared provider symbol
    silently, so the reconciler refuses before one is created."""
    result = run([row('NEWX')], [identity('NEWX'), identity('OLDX')],
                 [mapping('OLDX', provider_symbol='NEWX')])

    assert symbols(result.conflicts) == ['NEWX']
    assert result.conflicts[0].reason == 'provider_symbol_taken'
    assert not result.safe_mapping_candidates


def test_more_than_one_mapped_primary_is_a_conflict():
    result = run([row('DUPE')], [identity('DUPE')],
                 [mapping('DUPE', 'XNMS'), mapping('DUPE', 'XNCM')])

    assert symbols(result.conflicts) == ['DUPE']
    assert result.conflicts[0].reason == 'multiple_mapped_primaries'


def test_an_unknown_listing_code_is_quarantined_and_never_defaulted():
    result = run([DirectoryRow('WHAT', 'What Corp.', 'X', False,
                               'nasdaqlisted')],
                 [identity('WHAT', 'What Corp.', 'X')])

    assert symbols(result.quarantined) == ['WHAT']
    assert result.quarantined[0].reason == 'unknown_listing_code'
    assert not result.safe_mapping_candidates
    assert 'XNAS' not in result.quarantined[0].detail
    assert 'XXXX' not in result.quarantined[0].detail


def test_a_directory_row_with_no_identity_is_quarantined():
    """B1 writes no identity. A listing Radar has never seen cannot be
    mapped, and inventing the identity is B2's problem, not this one's."""
    result = run([row('GHOST')], [])
    assert symbols(result.quarantined) == ['GHOST']
    assert result.quarantined[0].reason == 'identity_missing'


def test_non_us_instrument_rows_are_never_read_or_reported():
    result = run([row('SAFE')], [identity('SAFE')],
                 [mapping('SAFE', 'XETR', currency='EUR', market='de')])
    assert symbols(result.safe_mapping_candidates) == ['SAFE']
    assert not result.conflicts


# --- shape, purity, determinism ------------------------------------------------

def test_the_reconciler_never_proposes_an_update_or_a_delete():
    result = run(
        [row('SAFE'), row('AAAAW', 'Alpha Acquisition Corp - Warrants'),
         row('DRIFT', 'Drift Corp. - Common Stock', 'S'),
         row('PMA', 'PMA Graphene Technology Group Inc. - Class A'),
         DirectoryRow('WHAT', 'What Corp.', 'X', False, 'nasdaqlisted')],
        [identity('SAFE'), identity('AAAAW', 'Alpha Acquisition Corp - Warrants'),
         identity('DRIFT', 'Drift Corp. - Common Stock', 'S'),
         identity('PMA', 'Ming Shing Group Holdings Limited'),
         identity('WHAT', 'What Corp.', 'X'), identity('GONE')],
        [mapping('DRIFT', 'XNMS'), mapping('PMA'), mapping('GONE')])

    actions = {entry.action for cohort in result.cohorts.values()
               for entry in cohort}
    assert actions <= {'insert_us_primary', 'identity_only',
                       'review_no_mutation', 'preserve_existing_mic',
                       'observe_only', 'review_conflict',
                       'quarantine_no_mapping'}


def test_every_cohort_is_sorted_by_symbol():
    rows = [row(s) for s in ('ZZZ', 'AAA', 'MMM')]
    ids = [identity(s) for s in ('ZZZ', 'AAA', 'MMM', 'ZGON', 'AGON')]
    result = run(rows, ids, [mapping('ZGON'), mapping('AGON')])
    assert symbols(result.safe_mapping_candidates) == ['AAA', 'MMM', 'ZZZ']
    assert symbols(result.absent) == ['AGON', 'ZGON']


def test_reconciling_twice_produces_identical_results():
    rows = [row('SAFE'), row('AAAAW', 'Alpha Acquisition Corp - Warrants')]
    ids = [identity('SAFE'), identity('AAAAW',
                                     'Alpha Acquisition Corp - Warrants')]
    assert run(rows, ids).as_dict() == run(rows, ids).as_dict()


def test_the_inputs_are_not_mutated():
    rows = [row('SAFE')]
    ids = [identity('SAFE')]
    maps = [mapping('OTHER')]
    before = (list(rows), list(ids), list(maps))
    run(rows, ids, maps)
    assert (rows, ids, maps) == before


def test_the_report_dict_is_json_serialisable_and_carries_no_secret():
    result = run([row('SAFE')], [identity('SAFE')])
    text = json.dumps(result.as_dict(), sort_keys=True)
    assert 'SAFE' in text
    for forbidden in ('password', 'mysql+pymysql', 'DB_PASS', '@localhost'):
        assert forbidden not in text


# --- the reviewed approval manifest --------------------------------------------

APPROVAL_HEADER = 'symbol,mic,source_kind,exchange_code,directory_sha256'


def _approval_file(tmp_path, body, header=APPROVAL_HEADER, name='approved.csv'):
    path = tmp_path / name
    path.write_text(header + '\n' + body, encoding='utf-8')
    return path


def test_a_reviewed_manifest_loads(tmp_path):
    path = _approval_file(
        tmp_path,
        f'SAFE,XNMS,nasdaqlisted,G,{SHA}\n'
        f'ARCA,ARCX,otherlisted,P,{OTHER_SHA}\n')
    approvals = load_approved_mappings(path)

    assert [a.symbol for a in approvals] == ['ARCA', 'SAFE']
    assert approvals[1].mic == 'XNMS'
    assert approvals[1].source_kind == 'nasdaqlisted'
    assert approvals[1].exchange_code == 'G'
    assert approvals[1].directory_sha256 == SHA


def test_the_committed_sample_manifest_is_valid():
    import pathlib
    sample = (pathlib.Path(__file__).parent / 'fixtures' / 'radar_universe'
              / 'approved_safe_sample.csv')
    approvals = load_approved_mappings(sample)
    assert [a.symbol for a in approvals] == ['AAAA', 'BBBB', 'CCCC']
    assert {a.directory_sha256 for a in approvals} == {SHA}


def test_a_duplicate_symbol_is_refused(tmp_path):
    path = _approval_file(tmp_path, f'SAFE,XNMS,nasdaqlisted,G,{SHA}\n'
                                    f'SAFE,XNCM,nasdaqlisted,S,{SHA}\n')
    with pytest.raises(ApprovalError, match='duplicate'):
        load_approved_mappings(path)


def test_an_unknown_mic_is_refused(tmp_path):
    for mic in ('XNAS', 'XXXX', 'XETR', ''):
        path = _approval_file(tmp_path,
                              f'SAFE,{mic},nasdaqlisted,G,{SHA}\n')
        with pytest.raises(ApprovalError):
            load_approved_mappings(path)


def test_a_mic_that_disagrees_with_its_code_is_refused(tmp_path):
    path = _approval_file(tmp_path, f'SAFE,XNCM,nasdaqlisted,G,{SHA}\n')
    with pytest.raises(ApprovalError, match='does not match'):
        load_approved_mappings(path)


def test_a_code_from_the_wrong_file_is_refused(tmp_path):
    path = _approval_file(tmp_path, f'SAFE,XNYS,nasdaqlisted,N,{SHA}\n')
    with pytest.raises(ApprovalError):
        load_approved_mappings(path)


def test_a_malformed_hash_is_refused(tmp_path):
    for bad in ('', 'deadbeef', SHA.upper(), SHA + 'ff', SHA[:-1] + 'z'):
        path = _approval_file(tmp_path, f'SAFE,XNMS,nasdaqlisted,G,{bad}\n')
        with pytest.raises(ApprovalError, match='sha256|SHA-256'):
            load_approved_mappings(path)


def test_an_unexpected_column_is_refused(tmp_path):
    path = _approval_file(tmp_path, f'SAFE,XNMS,nasdaqlisted,G,{SHA},yes\n',
                          header=APPROVAL_HEADER + ',force')
    with pytest.raises(ApprovalError, match='column'):
        load_approved_mappings(path)


def test_a_reordered_header_is_refused(tmp_path):
    path = _approval_file(tmp_path, f'XNMS,SAFE,nasdaqlisted,G,{SHA}\n',
                          header='mic,symbol,source_kind,exchange_code,'
                                 'directory_sha256')
    with pytest.raises(ApprovalError, match='column'):
        load_approved_mappings(path)


def test_a_symbol_outside_the_matchable_form_is_refused(tmp_path):
    for bad in ('brk', 'BRK.B', 'TOOLONG', '', 'AB1'):
        path = _approval_file(tmp_path, f'{bad},XNMS,nasdaqlisted,G,{SHA}\n')
        with pytest.raises(ApprovalError):
            load_approved_mappings(path)


def test_an_unknown_source_kind_is_refused(tmp_path):
    path = _approval_file(tmp_path, f'SAFE,XNMS,nasdaqtraded,G,{SHA}\n')
    with pytest.raises(ApprovalError):
        load_approved_mappings(path)


def test_an_empty_manifest_is_refused(tmp_path):
    path = _approval_file(tmp_path, '')
    with pytest.raises(ApprovalError, match='no approved'):
        load_approved_mappings(path)


# --- the CLI: dry-run by default, SELECT-only ----------------------------------

def _sqlite_session(identities=(), mappings=()):
    """An isolated SQLite database holding only the two tables read here."""
    from models import RadarInstrument, TickerUniverse

    engine = sa.create_engine('sqlite://')
    sa.event.listen(
        engine, 'connect',
        lambda connection, _: connection.create_collation(
            'utf8mb4_bin', lambda left, right: (left > right) - (left < right)))
    for model in (TickerUniverse, RadarInstrument):
        model.__table__.create(engine, checkfirst=True)
    session = sa.orm.Session(engine)
    for index, item in enumerate(identities, start=1):
        session.add(TickerUniverse(
            id=index, symbol=item.symbol, name=item.name,
            exchange=item.exchange, is_etf=item.is_etf,
            first_seen=dt.datetime(2026, 8, 21, 8, 15),
            delisted_at=None if item.active else dt.datetime(2026, 9, 1)))
    for index, item in enumerate(mappings, start=1):
        session.add(RadarInstrument(
            id=index, ticker=item.ticker, market=item.market, venue=item.venue,
            mic=item.mic, provider_symbol=item.provider_symbol,
            currency=item.currency, is_primary=item.is_primary,
            mapping_status=item.mapping_status,
            mapping_source='nasdaq-directory',
            mapped_at=dt.datetime(2026, 8, 30, 14, 28)))
    session.commit()
    return engine, session


def _recorder(engine):
    seen = []

    @sa.event.listens_for(engine, 'before_cursor_execute')
    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement.strip())

    return seen


def _fixture_pair(tmp_path):
    from tests.test_radar_universe_directory import (
        NASDAQ_HEADER, OTHER_HEADER, _write,
    )
    nasdaq = _write(tmp_path, 'nasdaqlisted.txt', NASDAQ_HEADER, (
        'SAFE|Safe Corp. - Common Stock|G|N|N|100|N|N',
        'WRNTW|Warrant Corp - Warrants|S|N|N|100|N|N',
    ))
    other = _write(tmp_path, 'otherlisted.txt', OTHER_HEADER, (
        'ARCA|Arca Fund ETF|P|ARCA|Y|100|N|ARCA',
    ), trailing_pipes=6)
    return nasdaq, other


def test_the_cli_dry_run_writes_a_report_and_issues_only_selects(tmp_path):
    from scripts import reconcile_radar_universe as cli

    nasdaq, other = _fixture_pair(tmp_path)
    engine, session = _sqlite_session(
        [identity('SAFE', 'Safe Corp. - Common Stock'),
         identity('WRNTW', 'Warrant Corp - Warrants', 'S'),
         identity('ARCA', 'Arca Fund ETF', 'P', is_etf=True),
         identity('GONE', 'Gone Corp. - Common Stock')],
        [mapping('GONE')])
    statements = _recorder(engine)
    report = tmp_path / 'report.json'

    code = cli.main([str(nasdaq), str(other), '--report', str(report)],
                    session_factory=lambda: session)

    assert code == 0
    payload = json.loads(report.read_text(encoding='utf-8'))
    assert payload['mode'] == 'dry-run'
    assert payload['counts']['safe_mapping_candidates'] == 2
    assert payload['counts']['non_common'] == 1
    assert payload['counts']['absent'] == 1
    assert [e['symbol'] for e in payload['cohorts']['safe_mapping_candidates']] \
        == ['ARCA', 'SAFE']
    assert payload['sources']['nasdaqlisted']['sha256'] == \
        hashlib.sha256(nasdaq.read_bytes()).hexdigest()
    assert payload['mapping_source'] == 'nasdaqdir-20260915'

    assert statements, 'the dry run never touched the database'
    assert all(s.upper().startswith('SELECT') for s in statements), statements


def test_the_cli_dry_run_changes_no_row(tmp_path):
    from models import RadarInstrument, TickerUniverse
    from scripts import reconcile_radar_universe as cli

    nasdaq, other = _fixture_pair(tmp_path)
    engine, session = _sqlite_session(
        [identity('SAFE', 'Safe Corp. - Common Stock'),
         identity('WRNTW', 'Warrant Corp - Warrants', 'S'),
         identity('ARCA', 'Arca Fund ETF', 'P', is_etf=True)])

    cli.main([str(nasdaq), str(other), '--report', str(tmp_path / 'r.json')],
             session_factory=lambda: session)

    assert session.query(RadarInstrument).count() == 0
    assert session.query(TickerUniverse).count() == 3
    assert not session.new and not session.dirty and not session.deleted


def test_two_dry_runs_produce_byte_identical_reports(tmp_path):
    from scripts import reconcile_radar_universe as cli

    nasdaq, other = _fixture_pair(tmp_path)
    digests = []
    for name in ('first.json', 'second.json'):
        engine, session = _sqlite_session(
            [identity('SAFE', 'Safe Corp. - Common Stock'),
             identity('WRNTW', 'Warrant Corp - Warrants', 'S'),
             identity('ARCA', 'Arca Fund ETF', 'P', is_etf=True)])
        report = tmp_path / name
        cli.main([str(nasdaq), str(other), '--report', str(report)],
                 session_factory=lambda: session)
        digests.append(hashlib.sha256(report.read_bytes()).hexdigest())
    assert digests[0] == digests[1]


def test_the_cli_refuses_an_input_it_cannot_bind_to_a_documented_file(tmp_path):
    from features.radar.universe_directory import SourceKindError
    from scripts import reconcile_radar_universe as cli

    nasdaq, _ = _fixture_pair(tmp_path)
    stray = tmp_path / 'nasdaqtraded.txt'
    stray.write_bytes(nasdaq.read_bytes())
    with pytest.raises(SourceKindError):
        cli.main([str(nasdaq), str(stray), '--report', str(tmp_path / 'r.json')],
                 session_factory=lambda: None)


def test_the_cli_requires_a_report_path(tmp_path):
    from scripts import reconcile_radar_universe as cli

    nasdaq, other = _fixture_pair(tmp_path)
    with pytest.raises(SystemExit):
        cli.main([str(nasdaq), str(other)], session_factory=lambda: None)


def test_applying_without_an_approved_manifest_is_refused(tmp_path):
    from scripts import reconcile_radar_universe as cli

    nasdaq, other = _fixture_pair(tmp_path)
    with pytest.raises(SystemExit):
        cli.main([str(nasdaq), str(other), '--report',
                  str(tmp_path / 'r.json'), '--apply-mappings'],
                 session_factory=lambda: None)


def test_the_cli_offers_no_force_or_implicit_approval_flag():
    import inspect

    from scripts import reconcile_radar_universe as cli

    source = inspect.getsource(cli)
    for forbidden in ('--force', '--yes', '--rollback', '--delete',
                      'upsert_symbols', 'requests', 'urlopen'):
        assert forbidden not in source


def test_load_current_state_reads_only_us_rows(tmp_path):
    from features.radar.universe_reconcile import load_current_state

    engine, session = _sqlite_session(
        [identity('SAFE'), identity('DEAD', active=False)],
        [mapping('SAFE'), mapping('XETRA', 'XETR', currency='EUR',
                                  market='de')])
    statements = _recorder(engine)
    identities, mappings = load_current_state(session)

    assert [i.symbol for i in identities] == ['DEAD', 'SAFE']
    assert [i.active for i in identities] == [False, True]
    assert [m.ticker for m in mappings] == ['SAFE']
    assert all(s.upper().startswith('SELECT') for s in statements), statements


def test_the_approval_sample_fixture_matches_the_documented_header():
    import pathlib
    sample = (pathlib.Path(__file__).parent / 'fixtures' / 'radar_universe'
              / 'approved_safe_sample.csv')
    with sample.open(newline='', encoding='utf-8') as handle:
        assert next(csv.reader(handle)) == APPROVAL_HEADER.split(',')
