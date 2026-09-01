# personal_apps/tests/test_radar_market_data_report.py
"""The activation-gate report: enforced read-only, non-vacuous gates."""
import datetime as dt
import decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from scripts.report_radar_market_data_shadow import (
    GERMAN_GATES, Gate, ReadOnlyViolation, ShadowReport, build_report,
    exit_code, install_statement_guard)
from scripts import report_radar_market_data_shadow as report_mod

NOW = dt.datetime(2027, 1, 4, 21, 30)
START = dt.datetime(2027, 1, 4, 6, 30)


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        yield


def test_report_rejects_every_mutating_statement(ctx):
    engine = sa.create_engine('sqlite://')
    install_statement_guard(engine)
    with engine.connect() as connection:
        connection.execute(sa.text('SELECT 1'))
        for statement in (
                'INSERT INTO radar_market_data_cycles (id) VALUES (1)',
                'UPDATE radar_quotes SET price=0',
                'DELETE FROM radar_quotes',
                'CREATE TABLE forbidden (id INT)',
                '  /* sneaky */ DROP TABLE radar_quotes'):
            with pytest.raises(ReadOnlyViolation):
                connection.execute(sa.text(statement))


def test_a_full_report_mutates_nothing(ctx):
    from models import RadarQuote
    before = db.session.query(sa.func.count(RadarQuote.id)).scalar()
    report = build_report(db.session, START, NOW)
    after = db.session.query(sa.func.count(RadarQuote.id)).scalar()
    assert before == after
    assert isinstance(report, ShadowReport)
    assert {gate.name for gate in report.gates} == set(GERMAN_GATES) | {
        'grouped_agreement'}


def test_an_empty_window_is_incomplete_never_vacuously_green(ctx):
    report = build_report(db.session, START, NOW)
    # Dev DB has no shadow session: multiple gates lack evidence and the
    # grouped backfill is absent. That is incomplete evidence, exit 2.
    assert report.incomplete
    assert exit_code(report, 'german') in (1, 2)
    assert exit_code(report, 'us-closes') == 2


def test_identity_audit_validation_is_strict(ctx, monkeypatch):
    from features.radar import instruments as inst
    decisions = [inst.MappingDecision(
        ticker='ZZRPT', status='mapped', reason=None, mic='XGAT',
        symbol='ZZR', isin='DE000ZZTST01', currency='EUR',
        mapping_source='openfigi')]
    generation = inst.persist_generation(decisions, NOW)
    try:
        audit = {
            'generation_sha256': 'f' * 64,  # wrong hash
            'reviewed_at': '2027-01-04T20:00:00Z', 'reviewer': 'Michi',
            'rows': [{'ticker': 'ZZRPT', 'mic': 'XGAT', 'symbol': 'ZZR',
                      'isin': 'DE000ZZTST01', 'currency': 'EUR',
                      'correct': True}],
        }
        report = build_report(db.session, START, NOW, identity_audit=audit)
        identity = report.gate('identity')
        assert identity.passed is False
        assert 'generation hash mismatch' in identity.detail['problems']

        # A row not confirmed correct is a truth violation, exit 1.
        audit['generation_sha256'] = generation.payload_sha256
        audit['rows'][0]['correct'] = False
        report = build_report(db.session, START, NOW, identity_audit=audit)
        assert any('wrong identities' in item
                   for item in report.truth_violations)
        assert exit_code(report, 'german') == 1
    finally:
        db.session.delete(generation)
        db.session.commit()


def test_each_german_gate_can_fail_alone():
    def gate(name, passed=True):
        return Gate(name, passed, 1, 1, 1, {})

    def report(**overrides):
        gates = [gate(name, overrides.get(name, True))
                 for name in GERMAN_GATES] + [gate('grouped_agreement',
                                                  False)]
        return ShadowReport(
            start=START, end=NOW, gates=tuple(gates),
            truth_violations=(), incomplete=(),
            grouped_informational={}, generation_sha256='a' * 64,
            instrument_map_sha256='b' * 64)

    # All German gates green: the grouped gate is informational for german.
    assert exit_code(report(), 'german') == 0
    for name in GERMAN_GATES:
        code = exit_code(report(**{name: False}), 'german')
        assert code in (1, 2), name
    # And the reverse independence: german failures never gate us-closes.
    grouped_green = ShadowReport(
        start=START, end=NOW,
        gates=tuple(gate(name, False) for name in GERMAN_GATES) + (
            gate('grouped_agreement', True),),
        truth_violations=(), incomplete=(), grouped_informational={},
        generation_sha256=None, instrument_map_sha256='b' * 64)
    assert exit_code(grouped_green, 'us-closes') == 0


def test_truth_violations_only_block_their_own_activation_track():
    gates = tuple(Gate(name, True, 1, 1, 1, {})
                  for name in GERMAN_GATES) + (
        Gate('grouped_agreement', True, 3, 3, 3, {}),)
    report = ShadowReport(
        start=START, end=NOW, gates=gates,
        truth_violations=('venue hop inside the window: [ZZX]',),
        incomplete=(), grouped_informational={},
        generation_sha256='a' * 64, instrument_map_sha256='b' * 64,
        german_truth_violations=('venue hop inside the window: [ZZX]',),
        grouped_truth_violations=())
    assert exit_code(report, 'german') == 1
    assert exit_code(report, 'us-closes') == 0

    grouped_report = ShadowReport(
        start=START, end=NOW, gates=gates,
        truth_violations=('conflicting grouped duplicate',),
        incomplete=(), grouped_informational={},
        generation_sha256='a' * 64, instrument_map_sha256='b' * 64,
        german_truth_violations=(),
        grouped_truth_violations=('conflicting grouped duplicate',))
    assert exit_code(grouped_report, 'german') == 0
    assert exit_code(grouped_report, 'us-closes') == 1


def test_grouped_gate_requires_the_operator_audit(ctx):
    report = build_report(db.session, START, NOW, us_close_audit=None)
    assert any('operator audit' in item for item in report.incomplete)
    grouped = report.gate('grouped_agreement')
    assert grouped.passed is False


@pytest.fixture()
def grouped_gate_evidence(ctx, monkeypatch):
    """Three compact expected days with two exact mapped identities."""
    from features.radar import market_data
    from features.radar import market_calendars
    from models import RadarDailyClose, RadarGroupedCloseDay

    dates = tuple(NOW.date() - dt.timedelta(days=offset)
                  for offset in (4, 3, 2, 1))
    identities = {
        'RPG1A': SimpleNamespace(ticker='RPG1A', mic='XNAS', currency='USD'),
        'RPG1B': SimpleNamespace(ticker='RPG1B', mic='XNYS', currency='USD'),
    }
    monkeypatch.setattr(report_mod, 'MIN_GROUPED_PROVIDER_ROWS', 2)
    monkeypatch.setattr(report_mod, 'MIN_GROUPED_OVERLAP_ROWS', 2)
    monkeypatch.setattr(report_mod, 'MIN_GROUPED_AGREEMENT_DAYS', 3)
    monkeypatch.setattr(
        market_calendars, 'session_state',
        lambda market, when, mic=None: (
            'regular' if market == 'us' and when.date() in dates else
            'closed'))
    monkeypatch.setattr(market_data, 'grouped_instrument_map',
                        lambda: (identities, []))
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: ['RPG1A', 'RPG1B'])

    for day in dates:
        db.session.add(RadarGroupedCloseDay(
            source='massive_grouped', close_date=day, is_shadow=True,
            status='accepted', fetched_at=NOW, completed_at=NOW,
            provider_rows=2, mapped_rows=2, written_rows=2,
            active_expected=2, active_matched=2))
        for index, identity in enumerate(identities.values()):
            price = decimal.Decimal(100 + index)
            db.session.add(RadarDailyClose(
                ticker=identity.ticker, market='us', mic=identity.mic,
                currency='USD', close_date=day, close=price,
                fetched_at=NOW, source='massive_grouped',
                price_basis='close', adjustment_basis='split',
                is_shadow=True))
            db.session.add(RadarDailyClose(
                ticker=identity.ticker, market='us', mic=identity.mic,
                currency='USD', close_date=day, close=price,
                fetched_at=NOW, source='twelvedata',
                price_basis='close', adjustment_basis='split',
                is_shadow=False))
    db.session.commit()

    def build(audit='correct'):
        unsigned = build_report(db.session, START, NOW)
        if audit is None:
            return unsigned
        supplied_hash = (unsigned.us_close_report_sha256 if audit == 'correct'
                         else '0' * 64)
        return build_report(db.session, START, NOW, us_close_audit={
            'report_sha256': supplied_hash,
            'instrument_map_sha256': unsigned.instrument_map_sha256,
            'reviewed_at': '2027-01-04T21:00:00Z',
            'reviewer': 'Michi',
            'accept_unmatched_symbols': True,
            'accept_storage_projection': True,
        })

    yield SimpleNamespace(dates=dates, identities=identities, build=build)

    db.session.rollback()
    RadarDailyClose.query.filter(
        RadarDailyClose.ticker.like('RPG1%')).delete(synchronize_session=False)
    RadarGroupedCloseDay.query.filter(
        RadarGroupedCloseDay.close_date.in_(dates),
        RadarGroupedCloseDay.source == 'massive_grouped',
        RadarGroupedCloseDay.is_shadow.is_(True)).delete(
            synchronize_session=False)
    db.session.commit()


def test_grouped_gate_binds_audit_and_reports_coverage_and_storage(
        grouped_gate_evidence):
    report = grouped_gate_evidence.build()
    assert len(report.us_close_report_sha256) == 64
    assert report.gate('grouped_agreement').passed is True
    assert exit_code(report, 'us-closes') == 0
    detail = report.grouped_informational
    assert detail['active_coverage_min'] == '1'
    assert detail['unmatched_universe_symbols'] == []
    assert detail['storage']['measured_shadow_rows'] == 8
    assert detail['storage']['projected_steady_state_rows'] == 8


def test_grouped_gate_rejects_an_audit_for_a_different_report(
        grouped_gate_evidence):
    report = grouped_gate_evidence.build(audit='wrong')
    assert report.gate('grouped_agreement').passed is False
    assert 'report hash mismatch' in \
        report.grouped_informational['audit_problems']


def test_grouped_gate_recomputes_active_coverage_from_shadow_rows(
        grouped_gate_evidence):
    from models import RadarDailyClose
    RadarDailyClose.query.filter_by(
        ticker='RPG1B', close_date=grouped_gate_evidence.dates[0],
        source='massive_grouped', is_shadow=True).delete()
    db.session.commit()
    report = grouped_gate_evidence.build(audit=None)
    assert report.gate('grouped_agreement').passed is False
    assert report.grouped_informational['active_coverage_gaps']


def test_grouped_gate_blocks_persisted_duplicate_conflicts(
        grouped_gate_evidence):
    from models import RadarGroupedCloseDay
    state = RadarGroupedCloseDay.query.filter_by(
        close_date=grouped_gate_evidence.dates[0], is_shadow=True).one()
    state.duplicate_conflicts = 1
    db.session.commit()
    report = grouped_gate_evidence.build(audit=None)
    assert any('duplicate' in item
               for item in report.grouped_truth_violations)
    assert exit_code(report, 'us-closes') == 1


def test_grouped_gate_blocks_adjustment_basis_conflicts(
        grouped_gate_evidence):
    from models import RadarDailyClose
    row = RadarDailyClose.query.filter_by(
        ticker='RPG1A', close_date=grouped_gate_evidence.dates[-1],
        is_shadow=False).one()
    row.source = 'yahoo_chart'
    row.adjustment_basis = None
    db.session.commit()
    report = grouped_gate_evidence.build(audit=None)
    assert any('adjustment-basis' in item
               for item in report.grouped_truth_violations)


def test_grouped_gate_requires_the_overlap_floor_independently(
        grouped_gate_evidence):
    from models import RadarDailyClose
    RadarDailyClose.query.filter_by(
        ticker='RPG1B', close_date=grouped_gate_evidence.dates[-1],
        is_shadow=False).delete()
    db.session.commit()
    report = grouped_gate_evidence.build(audit=None)
    assert report.grouped_informational['active_coverage_min'] == '1'
    assert any('overlapping' in item for item in report.grouped_incomplete)


def test_grouped_gate_refuses_a_zero_active_denominator(
        grouped_gate_evidence, monkeypatch):
    from features.radar import market_data
    monkeypatch.setattr(market_data, 'active_price_tickers', lambda now: [])
    report = grouped_gate_evidence.build(audit=None)
    assert any('zero active denominator' in item
               for item in report.grouped_incomplete)
