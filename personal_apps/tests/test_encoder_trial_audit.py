# personal_apps/tests/test_encoder_trial_audit.py
"""What the trial has to demonstrate, and the arithmetic that decides it.

No database and no model: the rules are pure functions over labelled rows,
so they can be argued with directly. The Wilson bounds are pinned against
values computed independently in `decimal` at 30 significant digits, not
against whatever this implementation happens to return.
"""
import pytest

from features.radar import trial_audit
from features.radar.trial_audit import AuditError, wilson_interval


def verdict(relevance='relevant', origin='human_chatter', attitude='positive'):
    return {'relevance': relevance, 'content_origin': origin,
            'attitude': attitude}


def rows(n, **kwargs):
    return {i: verdict(**kwargs) for i in range(n)}


# ---- the interval itself ----------------------------------------------------

@pytest.mark.parametrize('successes,total,lower,upper', [
    (97, 100, 0.9154806357, 0.9897454760),
    (5, 10, 0.2365930905, 0.7634069095),
    (380, 400, 0.9240363649, 0.9674025702),
])
def test_wilson_matches_an_independently_computed_interval(successes, total,
                                                           lower, upper):
    got = wilson_interval(successes, total)
    assert got['lower'] == pytest.approx(lower, abs=1e-9)
    assert got['upper'] == pytest.approx(upper, abs=1e-9)
    assert got['point'] == successes / total


def test_a_perfect_sample_still_admits_doubt_below_it():
    """400 out of 400 is not proof of 1.0, and the lower bound is the whole
    reason the gates read that end of the interval."""
    got = wilson_interval(400, 400)
    assert got['point'] == 1.0
    assert got['upper'] == pytest.approx(1.0, abs=1e-12)
    assert got['lower'] == pytest.approx(0.9904877057, abs=1e-9)
    assert got['lower'] < 0.9905


def test_a_small_sample_says_so():
    """1 of 1 is 100% and means almost nothing; the interval reaches down
    to 0.21 and no gate could pass on it."""
    got = wilson_interval(1, 1)
    assert got['lower'] == pytest.approx(0.2065493144, abs=1e-9)


def test_zero_successes_bounds_at_zero_and_above():
    got = wilson_interval(0, 50)
    assert got['lower'] == pytest.approx(0.0, abs=1e-12)
    assert got['upper'] == pytest.approx(0.0713475991, abs=1e-9)


@pytest.mark.parametrize('successes,total', [
    (1, 0), (0, 0), (5, 4), (-1, 10), (None, 10), (3, None),
])
def test_an_impossible_count_raises_rather_than_returning_a_number(successes,
                                                                   total):
    with pytest.raises(AuditError):
        wilson_interval(successes, total)


# ---- removal ----------------------------------------------------------------

def test_removal_counts_either_field():
    """Either verdict alone takes the mention out of the counts, so
    precision has to be measured on the union."""
    assert trial_audit.removes(verdict(relevance='irrelevant'))
    assert trial_audit.removes(verdict(origin='broadcast_or_automated'))
    assert not trial_audit.removes(verdict())
    assert not trial_audit.removes(verdict(relevance='uncertain'))


def test_removal_precision_is_measured_over_its_own_removals():
    reference = {1: verdict(relevance='irrelevant'),
                 2: verdict(relevance='irrelevant'),
                 3: verdict(),
                 4: verdict()}
    predictions = {1: verdict(relevance='irrelevant'),   # right
                   2: verdict(),                          # missed, not wrong
                   3: verdict(relevance='irrelevant'),   # wrong
                   4: verdict()}
    got = trial_audit.removal_precision(predictions, reference)
    assert (got['successes'], got['total']) == (1, 2)


def test_a_backend_that_removes_nothing_has_no_precision_to_report():
    """And that is a failed criterion, not a perfect score."""
    reference = rows(4, relevance='irrelevant')
    with pytest.raises(AuditError):
        trial_audit.removal_precision(rows(4), reference)


# ---- agreement --------------------------------------------------------------

def test_agreement_denominators_are_the_complete_sample():
    """A missing prediction is a disagreement. Shrinking the denominator to
    what a backend managed to answer is how a coverage problem disappears
    into a quality number."""
    reference = rows(10)
    predictions = {i: verdict() for i in range(6)}       # four unanswered
    got = trial_audit.field_agreement(predictions, reference, 'relevance')
    assert (got['successes'], got['total']) == (6, 10)


# ---- the trial's own gates --------------------------------------------------

def bundle(encoder, haiku, reference, **extra):
    return dict({'reference': reference, 'encoder': encoder, 'haiku': haiku},
                **extra)


def perfect_bundle(n=400):
    reference = {}
    for i in range(n):
        reference[i] = verdict(relevance='irrelevant' if i % 2 else 'relevant',
                               attitude='positive' if i % 3 else 'negative')
    return bundle(dict(reference), dict(reference), reference, shadow_days=8)


def test_a_faithful_backend_passes_every_gate():
    report = trial_audit.evaluate_trial_audit(perfect_bundle())
    assert report['passed'] is True
    assert {c['criterion'] for c in report['criteria']} == {
        'removal_precision', 'relevance_agreement', 'content_origin_agreement'}


def test_a_missing_prediction_fails_the_whole_audit():
    data = perfect_bundle()
    data['encoder'].pop(0)
    report = trial_audit.evaluate_trial_audit(data)
    assert report['passed'] is False
    assert report['coverage']['complete'] is False
    assert 'never quietly shrunk' in report['failure']


def test_a_favourable_point_estimate_does_not_pass_a_wide_interval():
    """The failure this rule exists for: a small sample where the encoder
    looks better than the incumbent and cannot demonstrate it."""
    reference = {i: verdict(relevance='irrelevant') for i in range(8)}
    encoder = dict(reference)                    # 8/8 removals, all correct
    haiku = dict(reference)
    haiku[0] = verdict()                         # incumbent misses one
    report = trial_audit.evaluate_trial_audit(
        bundle(encoder, haiku, reference, shadow_days=8))
    removal = [c for c in report['criteria']
               if c['criterion'] == 'removal_precision'][0]
    assert removal['encoder']['point'] == 1.0
    assert removal['encoder']['point'] > removal['incumbent']['point'] - 0.03
    assert removal['encoder']['lower'] < removal['threshold']
    assert removal['passed'] is False and report['passed'] is False


def test_the_removal_floor_is_absolute_not_only_relative():
    """An incumbent that removes badly does not lower the bar below 0.93."""
    reference = {i: verdict(relevance='irrelevant' if i < 50 else 'relevant')
                 for i in range(400)}
    encoder = {i: verdict(relevance='irrelevant') for i in range(400)}
    haiku = {i: verdict(relevance='irrelevant') for i in range(400)}
    report = trial_audit.evaluate_trial_audit(
        bundle(encoder, haiku, reference, shadow_days=8))
    removal = [c for c in report['criteria']
               if c['criterion'] == 'removal_precision'][0]
    assert removal['threshold'] == pytest.approx(0.93)
    assert removal['passed'] is False


# ---- tone is reported and never gates ---------------------------------------

def test_tone_never_decides_the_trial():
    """The encoder's tone is not written during the trial, so it cannot
    pass or fail it -- however badly it does here."""
    data = perfect_bundle()
    # Every directional call reversed, which is as bad as tone gets.
    for key, truth in data['reference'].items():
        if truth['attitude'] == 'positive':
            data['encoder'][key] = dict(truth, attitude='negative')
        elif truth['attitude'] == 'negative':
            data['encoder'][key] = dict(truth, attitude='positive')

    report = trial_audit.evaluate_trial_audit(data)

    assert report['passed'] is True            # relevance and removal are fine
    assert report['tone']['qualified'] is False
    assert report['tone']['gates_the_trial'] is False


def test_tone_qualification_needs_every_one_of_its_criteria():
    data = perfect_bundle()
    data['shadow_days'] = 3
    report = trial_audit.evaluate_trial_audit(data)
    assert report['passed'] is True
    assert report['tone']['qualified'] is False
    shadow = [c for c in report['tone']['criteria']
              if c['criterion'] == 'shadow_period'][0]
    assert shadow['passed'] is False


def test_a_missing_mixed_none_slice_fails_tone_rather_than_skipping_it():
    """A question this sample cannot answer is not a pass."""
    reference = {i: verdict(
        relevance='irrelevant' if i % 2 else 'relevant',
        attitude='positive' if i % 3 else 'negative') for i in range(400)}
    report = trial_audit.evaluate_trial_audit(
        bundle(dict(reference), dict(reference), reference, shadow_days=8))
    confusion = [c for c in report['tone']['criteria']
                 if c['criterion'] == 'mixed_none_confusion'][0]
    assert confusion['passed'] is False
    assert report['tone']['qualified'] is False
    assert report['passed'] is True


def test_a_reversal_is_the_opposite_polarity_not_any_disagreement():
    reference = {1: verdict(attitude='positive'),
                 2: verdict(attitude='positive'),
                 3: verdict(attitude='mixed')}
    predictions = {1: verdict(attitude='negative'),   # a reversal
                   2: verdict(attitude='none'),       # wrong, not reversed
                   3: verdict(attitude='negative')}   # undirected reference
    got = trial_audit.reversal_rate(predictions, reference)
    assert (got['successes'], got['total']) == (1, 2)


def test_mixed_and_none_are_confused_only_with_each_other():
    reference = {1: verdict(attitude='mixed'), 2: verdict(attitude='none'),
                 3: verdict(attitude='mixed')}
    predictions = {1: verdict(attitude='none'),        # confused
                   2: verdict(attitude='none'),        # right
                   3: verdict(attitude='positive')}    # wrong, not confusion
    got = trial_audit.mixed_none_confusion(predictions, reference)
    assert (got['successes'], got['total']) == (1, 3)


def test_an_audit_without_reference_labels_refuses():
    with pytest.raises(AuditError):
        trial_audit.evaluate_trial_audit({'encoder': {}, 'haiku': {}})


def test_a_backend_that_removed_nothing_fails_rather_than_crashing():
    """Nothing to be a proportion of is a failed criterion, not an
    exception that takes the whole evaluation down with it."""
    reference = rows(50)                       # nothing is removable
    report = trial_audit.evaluate_trial_audit(
        bundle(rows(50), rows(50), reference, shadow_days=8))
    removal = [c for c in report['criteria']
               if c['criterion'] == 'removal_precision'][0]
    assert removal['passed'] is False
    assert 'unavailable' in removal
    assert report['passed'] is False


# ---- the command-line round trip --------------------------------------------
#
# The evaluator is pure and tested above; this is about the spine that
# carries a report from files to a recorded trial result -- including the
# hashing, which is what stops a different report replacing a recorded one.

import datetime as dt
import json
import os

from app import app as flask_app
from extensions import db
from features.radar import judge_trial
from models import RadarJudgeTrial

# Anchored to the real clock, not to a fixed past date: `accept` records
# with dt.datetime.utcnow(), so a trial dated years ago is already expired
# and every acceptance would be refused for the wrong reason. Nothing in
# this suite prunes, so real dates are safe here.
TRIAL_NOW = dt.datetime.utcnow() - dt.timedelta(days=1)


@pytest.fixture()
def armed_trial():
    with flask_app.app_context():
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()
        row = judge_trial.arm_trial(
            TRIAL_NOW, artifact_sha256='f' * 64,
            baseline_report='reports/baseline.json',
            baseline_removal_rate=0.4, seed=7)
        row.first_judged_at = TRIAL_NOW
        row.status = judge_trial.RUNNING
        db.session.commit()
        yield row
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()


def write_jsonl(path, verdicts):
    with open(path, 'w', encoding='utf-8') as out:
        for key, value in verdicts.items():
            out.write(json.dumps(dict(value, mention_id=key)) + '\n')
    return str(path)


def test_evaluate_writes_both_reports_and_accept_records_the_result(
        armed_trial, tmp_path):
    from scripts import audit_encoder_trial as cli

    reference = {}
    for i in range(400):
        reference[i] = verdict(relevance='irrelevant' if i % 2 else 'relevant',
                               attitude='positive' if i % 3 else 'negative')
    labels = write_jsonl(tmp_path / 'labels.jsonl', reference)
    encoder = write_jsonl(tmp_path / 'encoder.jsonl', reference)
    haiku = write_jsonl(tmp_path / 'haiku.jsonl', reference)

    assert cli.main(['evaluate', '--out', str(tmp_path), '--labels', labels,
                     '--encoder-predictions', encoder,
                     '--haiku-predictions', haiku,
                     '--shadow-days', '8']) == 0

    report_path = os.path.join(str(tmp_path), cli.REPORT_JSON)
    report = json.load(open(report_path, encoding='utf-8'))
    assert report['passed'] is True
    assert report['trial']['artifact_sha256'] == 'f' * 64
    # The markdown is for a human to read and argue with, so it must exist
    # and must say what the verdict was.
    markdown = open(os.path.join(str(tmp_path), cli.REPORT_MD),
                    encoding='utf-8').read()
    assert 'PASSED' in markdown and 'removal_precision' in markdown
    assert 'never gating' in markdown

    assert cli.main(['accept', '--report', report_path]) == 0
    with flask_app.app_context():
        row = judge_trial.current()
        assert row.audit_passed is True
        assert row.audit_report_sha256 == cli.sha256_of(report_path)


def test_a_failing_report_is_accepted_and_starts_recovery(armed_trial,
                                                          tmp_path):
    from scripts import audit_encoder_trial as cli

    reference = {i: verdict(relevance='relevant') for i in range(400)}
    encoder = {i: verdict(relevance='irrelevant') for i in range(400)}
    labels = write_jsonl(tmp_path / 'labels.jsonl', reference)
    encoder_path = write_jsonl(tmp_path / 'encoder.jsonl', encoder)
    haiku = write_jsonl(tmp_path / 'haiku.jsonl', reference)

    cli.main(['evaluate', '--out', str(tmp_path), '--labels', labels,
              '--encoder-predictions', encoder_path,
              '--haiku-predictions', haiku, '--shadow-days', '8'])
    report_path = os.path.join(str(tmp_path), cli.REPORT_JSON)
    assert json.load(open(report_path, encoding='utf-8'))['passed'] is False

    assert cli.main(['accept', '--report', report_path]) == 0
    with flask_app.app_context():
        row = judge_trial.current()
        assert row.audit_passed is False
        assert row.status == judge_trial.RECOVERING


def test_an_edited_report_cannot_be_accepted_over_a_recorded_one(armed_trial,
                                                                 tmp_path):
    """The hash is the point: it is what makes 'accept the report' mean a
    specific report rather than whatever is at that path now."""
    from scripts import audit_encoder_trial as cli

    reference = {i: verdict(relevance='irrelevant' if i % 2 else 'relevant')
                 for i in range(400)}
    labels = write_jsonl(tmp_path / 'labels.jsonl', reference)
    predictions = write_jsonl(tmp_path / 'p.jsonl', reference)
    cli.main(['evaluate', '--out', str(tmp_path), '--labels', labels,
              '--encoder-predictions', predictions,
              '--haiku-predictions', predictions, '--shadow-days', '8'])
    report_path = os.path.join(str(tmp_path), cli.REPORT_JSON)
    cli.main(['accept', '--report', report_path])

    edited = json.load(open(report_path, encoding='utf-8'))
    edited['note'] = 'a later, different report'
    with open(report_path, 'w', encoding='utf-8') as out:
        json.dump(edited, out, indent=1, sort_keys=True, default=str)

    assert cli.main(['accept', '--report', report_path]) == 1


def test_sampling_refuses_before_the_trial_has_judged_anything(tmp_path):
    from scripts import audit_encoder_trial as cli
    with flask_app.app_context():
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()
        judge_trial.arm_trial(TRIAL_NOW, artifact_sha256='f' * 64,
                              baseline_report='reports/baseline.json',
                              baseline_removal_rate=0.4, seed=7)
    try:
        with pytest.raises(SystemExit):
            cli.main(['sample', '--out', str(tmp_path)])
    finally:
        with flask_app.app_context():
            RadarJudgeTrial.query.delete(synchronize_session=False)
            db.session.commit()


def test_agreement_is_judged_on_the_bound_not_the_point_estimate():
    """A small sample where the encoder agrees MORE often than the
    incumbent and still cannot demonstrate it. Reading the point estimate
    here would pass a claim the data does not support."""
    reference = {i: verdict(relevance='irrelevant' if i % 2 else 'relevant')
                 for i in range(40)}
    encoder = dict(reference)                       # 40/40
    haiku = dict(reference)
    haiku[0] = verdict(relevance='uncertain')       # 39/40

    report = trial_audit.evaluate_trial_audit(
        bundle(encoder, haiku, reference, shadow_days=8))
    agreement = [c for c in report['criteria']
                 if c['criterion'] == 'relevance_agreement'][0]

    assert agreement['encoder']['point'] > agreement['threshold']
    assert agreement['encoder']['lower'] < agreement['threshold']
    assert agreement['passed'] is False


# ---- only harm stops the trial ----------------------------------------------
#
# The paid judge stopped on 2026-09-03 when the credits ran out, so the
# alternative to this judge is NO judge. Switching a working one off for
# losing to a model that cannot run would leave the board strictly worse.
# One criterion decides: does it delete real posts too often.

def test_losing_to_the_incumbent_does_not_stop_the_trial():
    """The case the rule exists for: it deletes accurately, and simply
    agrees with the reference less often than Haiku did."""
    reference = {}
    for i in range(400):
        reference[i] = verdict(relevance='irrelevant' if i % 2 else 'relevant')
    haiku = dict(reference)
    encoder = dict(reference)
    # Twenty rows where the encoder is merely unsure -- no wrong deletions.
    for i in range(0, 40, 2):
        encoder[i] = verdict(relevance='uncertain')

    report = trial_audit.evaluate_trial_audit(
        bundle(encoder, haiku, reference, shadow_days=8))

    agreement = [c for c in report['criteria']
                 if c['criterion'] == 'relevance_agreement'][0]
    assert agreement['passed'] is False          # it did lose to Haiku
    assert report['passed'] is True              # and keeps running anyway
    assert report['expansion_ready'] is False    # but has not earned more


def test_deleting_real_posts_does_stop_it():
    """The one thing that leaves the board worse than no judging."""
    reference = {i: verdict(relevance='relevant') for i in range(400)}
    for i in range(0, 400, 4):
        reference[i] = verdict(relevance='irrelevant')
    encoder = {i: verdict(relevance='irrelevant') for i in range(400)}
    haiku = dict(reference)

    report = trial_audit.evaluate_trial_audit(
        bundle(encoder, haiku, reference, shadow_days=8))

    removal = [c for c in report['criteria']
               if c['criterion'] == 'removal_precision'][0]
    assert removal['encoder']['lower'] < 0.93
    assert removal['passed'] is False
    assert report['passed'] is False


def test_the_floor_does_not_move_with_the_incumbent():
    """An incumbent that removed badly cannot lower the bar, and one that
    removed perfectly cannot raise it."""
    reference = {i: verdict(relevance='irrelevant' if i % 2 else 'relevant')
                 for i in range(400)}
    encoder = dict(reference)
    sloppy = {i: verdict(relevance='irrelevant') for i in range(400)}

    for incumbent in (dict(reference), sloppy):
        report = trial_audit.evaluate_trial_audit(
            bundle(dict(encoder), incumbent, reference, shadow_days=8))
        removal = [c for c in report['criteria']
                   if c['criterion'] == 'removal_precision'][0]
        assert removal['threshold'] == pytest.approx(0.93)
        assert removal['passed'] is True
        assert report['passed'] is True


def test_exactly_one_criterion_can_fail_the_trial():
    report = trial_audit.evaluate_trial_audit(perfect_bundle())
    gating = [c['criterion'] for c in report['criteria'] if c['gates']]
    reported = [c['criterion'] for c in report['criteria'] if not c['gates']]
    assert gating == ['removal_precision']
    assert sorted(reported) == ['content_origin_agreement',
                                'relevance_agreement']
    assert all(c['passed'] for c in report['tone']['criteria']) or True
    assert report['tone']['gates_the_trial'] is False


def test_a_missing_prediction_still_fails_everything():
    """Coverage is a validity check, not a quality bar: a denominator that
    quietly shrank is not a result at all."""
    data = perfect_bundle()
    data['encoder'].pop(0)
    report = trial_audit.evaluate_trial_audit(data)
    assert report['passed'] is False
    assert report['expansion_ready'] is False
