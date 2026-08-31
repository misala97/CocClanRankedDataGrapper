# personal_apps/tests/test_diagnose_extractor_feedback.py
"""The read-only extractor diagnostic (extractor-feedback spec §7/§11.3).

Pure pieces tested directly; the full run tested against the live dev
database for the two properties that matter most: it mutates nothing,
and with zero actionable cohorts it recommends nothing.
"""
import datetime as dt

import pytest

from features.radar import universe
from scripts import diagnose_extractor_feedback as diag


def test_wilson_lower_bound_is_reproducible():
    # Hand-checked: 8/10 -> ~0.490; 1/1 -> ~0.207; 40/80 -> ~0.393.
    assert diag.wilson_low(8, 10) == pytest.approx(0.4901, abs=0.005)
    assert diag.wilson_low(1, 1) == pytest.approx(0.2065, abs=0.005)
    assert diag.wilson_low(40, 80) == pytest.approx(0.3935, abs=0.005)
    assert diag.wilson_low(0, 0) == 0.0
    # The ranking property the interval exists for: one bad answer on a
    # tiny slice ranks below a measured failure.
    assert diag.wilson_low(1, 1) < diag.wilson_low(40, 80)


def test_readiness_needs_consecutive_days_and_a_real_slice():
    day = dt.date(2027, 3, 1)
    six = [day + dt.timedelta(days=index) for index in range(6)]
    seven = [day + dt.timedelta(days=index) for index in range(7)]
    gapped = seven[:3] + [day + dt.timedelta(days=index)
                          for index in range(5, 9)]
    assert diag.readiness(six, 100) == (False,
                                        ['6 consecutive judged days < 7'])
    ok, reasons = diag.readiness(seven, 100)
    assert ok and not reasons
    assert not diag.readiness(gapped, 100)[0]
    assert not diag.readiness(seven, 49)[0]
    # Two failures report both reasons.
    assert len(diag.readiness(six, 10)[1]) == 2


def test_template_fingerprint_survives_ticker_and_number_swaps():
    a = diag.template_fingerprint('$GME +4.2% Market Alert vol 120,000')
    b = diag.template_fingerprint('$TSLA -1.7% Market Alert vol 98,500')
    c = diag.template_fingerprint('completely different words entirely')
    assert a == b
    assert a != c


def test_label_rates_never_merge_uncertain_into_exclusions():
    rows = [{'relevance': 'irrelevant'}, {'relevance': 'uncertain'},
            {'relevance': None}]
    rates = diag.label_rates(rows, 'relevance', diag.RELEVANCE_KEYS)
    assert rates['irrelevant'] == 1
    assert rates['uncertain'] == 1
    assert rates['missing_unjudged'] == 1
    # TEETH: the merged variant the spec forbids would read 2 -- if
    # someone "simplifies" uncertain into irrelevant, this line bites.
    assert rates['irrelevant'] + rates['uncertain'] == 2
    assert rates['irrelevant'] != 2


def test_provenance_uses_the_production_extractor():
    from types import SimpleNamespace
    lookup = universe.annotate_distinctive(
        {'ZZDG': {'name': 'Diag Corp', 'exchange': 'NYSE'}})
    post = SimpleNamespace(source='bluesky', title=None,
                           body='loading $ZZDG today', author='a',
                           channel='c')
    mention = SimpleNamespace(ticker='ZZDG')
    reason, in_author, in_context = diag.provenance_for(mention, post, lookup)
    assert (reason, in_author, in_context) == ('explicit_cashtag', True,
                                               False)
    # Text refreshed away: the reserved marker, never a fake reason.
    post.body = 'the ticker is gone now'
    reason, _a, _c = diag.provenance_for(mention, post, lookup)
    assert reason == diag.TEXT_CHANGED
    assert reason not in diag.__dict__.get('REASONS', ())


def test_ranked_slices_respect_wilson_and_the_appendix_floor():
    def rows(ticker, n, bad):
        return [{'ticker': ticker, 'source': 'bluesky',
                 'source_root': 'bluesky',
                 'reason': 'bare_low', 'judged': True,
                 'relevance': 'irrelevant' if index < bad else 'relevant'}
                for index in range(n)]
    ranked, appendix = diag.ranked_slices(
        rows('AAA', 80, 40) + rows('BBB', 1, 1), 'relevance', 'irrelevant')
    assert [key[0] for _low, _k, _n, key in ranked] == ['AAA']
    assert [key[0] for _low, _k, _n, key in appendix] == ['BBB']


def test_the_full_run_is_read_only_and_recommends_nothing_yet(capsys):
    """Acceptance §12.7 against the live restore: zero current-policy
    coverage, no recommendation, exit 0 -- and the statement guard saw
    only reads. The guard's teeth live in the next test."""
    diag._read_statements.clear()
    assert diag.main([]) == 0
    out = capsys.readouterr().out
    assert 'NO RECOMMENDATIONS' in out
    assert 'LEGACY-POLICY cohort' in out
    assert 'unclear' not in out          # v1 vocabulary never appears
    assert diag._read_statements, 'the guard never saw the queries'
    assert set(diag._read_statements) <= {'SELECT', 'SHOW', 'SET'}


def test_the_read_guard_has_teeth():
    """A non-read statement through the guarded path must abort."""
    with pytest.raises(RuntimeError):
        diag._read_guard(None, None,
                         "UPDATE radar_mentions SET ticker='X'",
                         None, None, False)
    # And reads pass.
    diag._read_guard(None, None, 'SELECT 1', None, None, False)


def test_no_model_call_is_possible(monkeypatch, capsys):
    """Spec §11.3: the diagnostic never talks to a model. Poison the
    client factory and run the whole thing."""
    from features.radar import llm_sentiment

    def boom():
        raise AssertionError('the diagnostic constructed a model client')

    monkeypatch.setattr(llm_sentiment, '_get_client', boom)
    assert diag.main([]) == 0


def test_combine_flag_is_loud(capsys):
    assert diag.main(['--combine-prompt-versions']) == 0
    assert 'VERSIONS COMBINED' in capsys.readouterr().out


def test_a_planted_mutation_dies_inside_the_real_transaction(monkeypatch):
    """Full-path teeth (Codex final review, finding 9): a mutation smuggled
    into the diagnostic's own run must be killed by the guard, in the
    actual guarded transaction, not in a unit-test simulation."""
    import sqlalchemy as sa
    from extensions import db
    real = diag.build_population

    def sabotaged(combine_prompt_versions=False):
        db.session.execute(sa.text(
            "UPDATE radar_review_meter SET demanded = demanded WHERE 1=0"))
        return real(combine_prompt_versions)

    monkeypatch.setattr(diag, 'build_population', sabotaged)
    with pytest.raises(Exception):
        diag.main([])


def test_the_session_stays_clean_after_a_full_run():
    """Flask-SQLAlchemy scopes sessions per app context, so the
    inspection must share the context the population build runs in."""
    import sqlalchemy as sa
    from app import app as flask_app
    from extensions import db
    with flask_app.app_context():
        with db.session.no_autoflush:
            db.session.execute(sa.text('SET TRANSACTION READ ONLY'))
            diag.build_population()
        assert not db.session.new
        assert not db.session.dirty
        assert not db.session.deleted
        db.session.rollback()


def test_broken_reconciliation_fails_loudly():
    with pytest.raises(AssertionError):
        diag.reconciled('scope', {'author': 1}, total=2)
    diag.reconciled('scope', {'author': 2}, total=2)   # and a true one passes
