# personal_apps/tests/test_radar_market_data_report.py
"""The US close activation-gate report: enforced read-only, non-vacuous."""
import datetime as dt
import decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from scripts.report_radar_market_data_shadow import (
    Gate, ReadOnlyViolation, ShadowReport, build_report, exit_code,
    install_statement_guard)
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
    assert {gate.name for gate in report.gates} == {'grouped_agreement'}


def test_an_empty_window_is_incomplete_never_vacuously_green(ctx):
    report = build_report(db.session, START, NOW)
    # Dev DB has no shadow session: multiple gates lack evidence and the
    # grouped backfill is absent. That is incomplete evidence, exit 2.
    assert report.incomplete
    assert exit_code(report, 'us-closes') == 2
    assert exit_code(report) == 2


def test_only_the_us_close_gate_exists(capsys):
    """The retired market's gates, audit and selector are gone; asking for
    them is an error, never a silent switch to the US gate."""
    for name in ('GERMAN_GATES', '_german_gates', '_active_generation',
                 'MIN_IDENTITY_AUDIT'):
        assert not hasattr(report_mod, name), name
    assert report_mod.GATES == ('us-closes',)
    report = ShadowReport(
        start=START, end=NOW,
        gates=(Gate('grouped_agreement', True, 3, 3, 3, {}),),
        truth_violations=(), incomplete=(), grouped_informational={},
        instrument_map_sha256='b' * 64)
    assert exit_code(report) == 0
    with pytest.raises(ValueError, match='unknown gate'):
        exit_code(report, 'german')
    for argv in (['--from', 'x', '--to', 'y', '--gate', 'german'],
                 ['--from', 'x', '--to', 'y', '--identity-audit', 'a.json']):
        with pytest.raises(SystemExit):
            report_mod.main(argv)
    assert 'german' in capsys.readouterr().err


def test_truth_violations_block_the_us_close_gate():
    gates = (Gate('grouped_agreement', True, 3, 3, 3, {}),)
    clean = ShadowReport(
        start=START, end=NOW, gates=gates, truth_violations=(),
        incomplete=(), grouped_informational={},
        instrument_map_sha256='b' * 64)
    assert exit_code(clean, 'us-closes') == 0

    grouped_report = ShadowReport(
        start=START, end=NOW, gates=gates,
        truth_violations=('conflicting grouped duplicate',),
        incomplete=(), grouped_informational={},
        instrument_map_sha256='b' * 64,
        grouped_truth_violations=('conflicting grouped duplicate',))
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
    from models import RadarDailyClose, RadarGroupedCloseDay, TickerUniverse

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
    TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(['RPG1A', 'RPG1B'])).delete(
            synchronize_session=False)
    db.session.add_all([
        TickerUniverse(symbol='RPG1A', name='RPG1A', first_seen=NOW),
        TickerUniverse(symbol='RPG1B', name='RPG1B', first_seen=NOW),
    ])

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
    TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(['RPG1A', 'RPG1B'])).delete(
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
    day = grouped_gate_evidence.dates[0]
    RadarDailyClose.query.filter_by(
        ticker='RPG1B', close_date=day,
        source='massive_grouped', is_shadow=True).delete()
    db.session.add(RadarDailyClose(
        ticker='RPG1B', market='us', mic='XNYS', currency='USD',
        close_date=day - dt.timedelta(days=1), close=decimal.Decimal('101'),
        fetched_at=NOW, source='massive_grouped', price_basis='close',
        adjustment_basis='split', is_shadow=True))
    db.session.commit()
    report = grouped_gate_evidence.build(audit=None)
    assert report.gate('grouped_agreement').passed is False
    assert report.grouped_informational['active_coverage_gaps']


def test_grouped_gate_excludes_pre_ipo_tickers_from_historical_coverage(
        grouped_gate_evidence):
    """The activation report must use the same date-aware denominator."""
    from models import RadarDailyClose, TickerUniverse
    day = grouped_gate_evidence.dates[0]
    TickerUniverse.query.filter_by(symbol='RPG1B').one().ipo_date = (
        day + dt.timedelta(days=1))
    RadarDailyClose.query.filter_by(
        ticker='RPG1B', close_date=day, source='massive_grouped',
        is_shadow=True).delete()
    db.session.commit()

    report = grouped_gate_evidence.build(audit=None)

    assert report.grouped_informational['active_coverage_gaps'] == []
    assert report.grouped_informational['active_coverage_min'] == '1'


def test_grouped_gate_excludes_a_symbol_before_massive_first_observed_day(
        grouped_gate_evidence):
    """The report shares ingestion's provider-availability denominator."""
    from models import RadarDailyClose
    day = grouped_gate_evidence.dates[0]
    RadarDailyClose.query.filter_by(
        ticker='RPG1B', close_date=day, source='massive_grouped',
        is_shadow=True).delete()
    db.session.commit()

    report = grouped_gate_evidence.build(audit=None)

    assert report.grouped_informational['active_coverage_gaps'] == []
    assert report.grouped_informational['active_coverage_min'] == '1'


def test_grouped_gate_does_not_count_a_pre_ipo_row_as_coverage(
        grouped_gate_evidence):
    """An old pre-IPO close cannot cover for a missing eligible ticker."""
    from models import RadarDailyClose, TickerUniverse
    day = grouped_gate_evidence.dates[0]
    TickerUniverse.query.filter_by(symbol='RPG1B').one().ipo_date = (
        day + dt.timedelta(days=1))
    RadarDailyClose.query.filter_by(
        ticker='RPG1A', close_date=day, source='massive_grouped',
        is_shadow=True).delete()
    db.session.add(RadarDailyClose(
        ticker='RPG1A', market='us', mic='XNAS', currency='USD',
        close_date=day - dt.timedelta(days=1), close=decimal.Decimal('100'),
        fetched_at=NOW, source='massive_grouped', price_basis='close',
        adjustment_basis='split', is_shadow=True))
    db.session.commit()

    report = grouped_gate_evidence.build(audit=None)

    assert report.grouped_informational['active_coverage_gaps'] == [{
        'date': day.isoformat(), 'matched': 0, 'expected': 1, 'ratio': '0',
    }]


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
