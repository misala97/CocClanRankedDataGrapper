# personal_apps/tests/test_radar_market_data_report.py
"""The activation-gate report: enforced read-only, non-vacuous gates."""
import datetime as dt
import decimal

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from scripts.report_radar_market_data_shadow import (
    GERMAN_GATES, Gate, ReadOnlyViolation, ShadowReport, build_report,
    exit_code, install_statement_guard)

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


def test_a_truth_violation_blocks_regardless_of_percentages():
    gates = tuple(Gate(name, True, 1, 1, 1, {})
                  for name in GERMAN_GATES) + (
        Gate('grouped_agreement', True, 3, 3, 3, {}),)
    report = ShadowReport(
        start=START, end=NOW, gates=gates,
        truth_violations=('venue hop inside the window: [ZZX]',),
        incomplete=(), grouped_informational={},
        generation_sha256='a' * 64, instrument_map_sha256='b' * 64)
    assert exit_code(report, 'german') == 1
    assert exit_code(report, 'us-closes') == 1


def test_grouped_gate_requires_the_operator_audit(ctx):
    report = build_report(db.session, START, NOW, us_close_audit=None)
    assert any('operator audit' in item for item in report.incomplete)
    grouped = report.gate('grouped_agreement')
    assert grouped.passed is False
