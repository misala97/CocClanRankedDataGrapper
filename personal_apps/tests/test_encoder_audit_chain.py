# personal_apps/tests/test_encoder_audit_chain.py
"""The audit as an enforced chain: frozen frame, validated inputs and
predictions and labels, a report computed from them, and an acceptance
that reproduces it.

Every step reads what the step before it wrote and refuses what it did
not. The sample must reproduce from the frame and the armed recipe; a
prediction file must say which artifact and which sample it came from;
the labels must be exactly the sample, every value a real verdict; the
report must reproduce from its recorded inputs; and acceptance needs the
inspections the spec requires, acknowledged against THIS report. Merely
hashing whatever files were handed in establishes none of that -- sixty
arbitrary perfect rows passed a 400-row audit that way.

Fixtures are small: the audit needs REMOVAL_DECISIONS_WANTED removal
decisions, and that constant is pinned to sixty here, the least that can
clear the 0.93 Wilson lower bound with no wrong deletions (60/60 bounds
at 0.9404; 50/50 at 0.9296 does not).
"""
import datetime as dt
import hashlib
import json
import os
import random

import pytest

from app import app as flask_app
from extensions import db
from features.radar import judge_backends, judge_trial, llm_sentiment
from features.radar.judge_backends import Judgment, Usage
from models import (RadarJudgeTrial, RadarLlmSpend, RadarMention, RadarPost,
                    RadarSentimentJudgment)
from scripts import audit_encoder_trial as cli

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'fixtures', 'radar_encoder')
SIZE = 60
TICKER = 'ZZAU'
ENCODER = judge_backends.ENCODER_MODEL_ID
HAIKU = 'claude-haiku-4-5'
FIELDS = ('relevance', 'content_origin', 'attitude', 'expected_move',
          'confidence')

REMOVED = dict(relevance='irrelevant', content_origin='human_chatter',
               attitude='none', expected_move='unknown', confidence='high')
KEPT = dict(relevance='relevant', content_origin='human_chatter',
            attitude='positive', expected_move='up', confidence='high')

# What the fixture's supplemental files hold, frozen at arming: twenty
# rows per half of the audit set, twenty in the natural set.
SUPPLEMENTAL = {
    'audit': {'keys': ['removal-%d' % i for i in range(20)]
              + ['natural-%d' % i for i in range(20)],
              'halves': dict([('removal-%d' % i, 'removal') for i in range(20)]
                             + [('natural-%d' % i, 'natural')
                                for i in range(20)])},
    'natural': {'keys': ['natural-%d' % i for i in range(20)]},
}


def fixture_sha():
    return judge_backends.EncoderBackend(FIXTURE).bundle_sha256()


def _wipe():
    db.session.rollback()
    RadarJudgeTrial.query.delete(synchronize_session=False)
    ids = [row.id for row in RadarPost.query.filter(
        RadarPost.external_id.like('zzaudit%')).all()]
    if ids:
        RadarPost.query.filter(RadarPost.id.in_(ids)).delete(
            synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def trial(monkeypatch):
    """A running trial on its fourth day, with SIZE sampled-able mentions
    inside its frame and the audit sized to exactly SIZE rows."""
    monkeypatch.setattr(judge_trial, 'REMOVAL_DECISIONS_WANTED', SIZE)
    with flask_app.app_context():
        _wipe()
        started = dt.datetime.utcnow() - dt.timedelta(days=4)
        row = judge_trial.arm_trial(started - dt.timedelta(hours=1),
                                    artifact_sha256=fixture_sha(),
                                    baseline_report='reports/baseline.json',
                                    baseline_removal_rate=1.0, seed=7,
                                    supplemental=SUPPLEMENTAL)
        row.first_judged_at = started
        row.status = judge_trial.RUNNING
        db.session.commit()
        for n in range(SIZE):
            when = started + dt.timedelta(minutes=n)
            post = RadarPost(source='bluesky', external_id='zzaudit-%03d' % n,
                             channel='firehose', author='someone%d' % n,
                             created_utc=when, title=None,
                             body='ZZAU ripping w%d' % (n % 32),
                             first_seen=when, last_seen=when)
            db.session.add(post)
            db.session.flush()
            db.session.add(RadarMention(post_id=post.id, ticker=TICKER,
                                        confidence='high',
                                        lexicon_sentiment=0.2))
        db.session.commit()
        yield row
        _wipe()


def started_at():
    return judge_trial.current().first_judged_at


class FakeJudge:
    """Answers every item the same way. `sha` makes it look like a
    deployed encoder artifact to the predict command's identity check."""
    supports_review = False
    writes_tone = False
    batch_size = 20
    pass_limit = 400

    def __init__(self, backend_id, answer, sha=None):
        self.id = backend_id
        self.answer = answer
        self.sha = sha
        self.batches = 0

    def bundle_sha256(self):
        return self.sha

    def judge_batch(self, batch, *, preamble=None):
        self.batches += 1
        return ({item.key: Judgment(**self.answer) for item in batch},
                Usage(10, 2))


def fake_backends(monkeypatch, encoder_answer=REMOVED, haiku_answer=REMOVED,
                  encoder_sha=None):
    made = {}

    def construct(spec, *, effort=None, artifact_dir=None):
        if spec == 'encoder':
            made['encoder'] = FakeJudge(ENCODER, encoder_answer,
                                        encoder_sha or fixture_sha())
            return made['encoder']
        made['haiku'] = FakeJudge(spec.split(':', 1)[1], haiku_answer)
        return made['haiku']

    monkeypatch.setattr(judge_backends, 'construct_backend', construct)
    return made


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def write_labels(path, verdicts, *, labelled_at=None, adjudicate=None):
    """`adjudicate` maps key -> (original verdict, reason or None)."""
    labelled_at = labelled_at or (started_at() + dt.timedelta(days=5))
    with open(path, 'w', encoding='utf-8') as out:
        for key, verdict in verdicts.items():
            row = dict(verdict, mention_id=key,
                       labelled_at=labelled_at.isoformat())
            if adjudicate and key in adjudicate:
                original, reason = adjudicate[key]
                row['original'] = original
                if reason is not None:
                    row['adjudication_reason'] = reason
            out.write(json.dumps(row) + '\n')
    return str(path)


def write_supplemental(path, rows):
    with open(path, 'w', encoding='utf-8') as out:
        for row in rows:
            out.write(json.dumps(row) + '\n')
    return str(path)


def supplemental_rows(n=20, half='removal', truncated=False, reversed_=0):
    rows = []
    for i in range(n):
        reference = dict(KEPT)
        prediction = dict(KEPT)
        if i < reversed_:
            prediction['attitude'] = 'negative'
        rows.append({'key': '%s-%d' % (half, i), 'half': half,
                     'truncated': truncated and i % 2 == 0,
                     'reference': reference, 'prediction': prediction})
    return rows


def write_ack(out_dir, report_path, inspected=cli.REQUIRED_INSPECTIONS,
              by='michi'):
    path = os.path.join(out_dir, cli.ACKNOWLEDGMENTS)
    with open(path, 'w', encoding='utf-8') as out:
        json.dump({'report_sha256': sha256_of(report_path),
                   'inspected': list(inspected), 'by': by,
                   'at': dt.datetime.utcnow().isoformat()}, out)
    return path


def sampled_ids(out_dir):
    return read_json(os.path.join(out_dir, cli.SAMPLE))['mention_ids']


def predictions_path(out_dir, backend_id):
    return os.path.join(out_dir, '%s.jsonl' % backend_id)


def evaluate_args(out_dir, labels, encoder=None, haiku=None,
                  supplemental=True):
    args = ['evaluate', '--out', out_dir, '--labels', labels,
            '--encoder-predictions', encoder or predictions_path(out_dir, ENCODER),
            '--haiku-predictions', haiku or predictions_path(out_dir, HAIKU)]
    if supplemental:
        args += ['--supplemental-audit',
                 os.path.join(out_dir, 'supplemental-audit.jsonl'),
                 '--supplemental-natural',
                 os.path.join(out_dir, 'supplemental-natural.jsonl')]
    return args


def chain(tmp_path, monkeypatch, *, encoder_answer=REMOVED,
          haiku_answer=REMOVED, labels=None, supplemental=True):
    """sample, export-labels, predict twice, labels, supplemental files,
    evaluate. Returns the directory and the report."""
    out = str(tmp_path)
    fake_backends(monkeypatch, encoder_answer, haiku_answer)
    assert cli.main(['sample', '--out', out]) == 0
    assert cli.main(['export-labels', '--out', out]) == 0
    assert cli.main(['predict', '--out', out, '--backend', 'encoder']) == 0
    assert cli.main(['predict', '--out', out, '--backend',
                     'anthropic:' + HAIKU, '--confirm-spend']) == 0
    ids = sampled_ids(out)
    labels = labels or {key: dict(encoder_answer) for key in ids}
    labels_path = write_labels(tmp_path / 'labels.jsonl', labels)
    write_supplemental(tmp_path / 'supplemental-audit.jsonl',
                       supplemental_rows(half='removal', reversed_=2)
                       + supplemental_rows(half='natural', truncated=True))
    write_supplemental(tmp_path / 'supplemental-natural.jsonl',
                       supplemental_rows(half='natural', reversed_=3))
    assert cli.main(evaluate_args(out, labels_path,
                                  supplemental=supplemental)) == 0
    report_path = os.path.join(out, cli.REPORT_JSON)
    return out, labels_path, report_path, read_json(report_path)


# ---- 1. the frozen frame and the reproducible draw --------------------------

def test_sampling_refuses_before_day_three(trial):
    """The frame is the first three days of the trial. Drawing on day
    one draws from a frame that is not closed yet."""
    with flask_app.app_context():
        # A nested context is a separate session; the fixture's object
        # would not be flushed by this commit.
        judge_trial.current().first_judged_at =             dt.datetime.utcnow() - dt.timedelta(days=1)
        db.session.commit()
    out = str(pytest_tmp())
    assert cli.main(['sample', '--out', out]) == 1
    assert not os.path.exists(os.path.join(out, cli.SAMPLE))
    assert not os.path.exists(os.path.join(out, cli.FRAME))


def pytest_tmp():
    import tempfile
    return tempfile.mkdtemp(prefix='zzaudit-')


def test_sampling_reuses_the_frozen_draw_on_rerun(trial, tmp_path):
    out = str(tmp_path)
    assert cli.main(['sample', '--out', out]) == 0
    first = read_json(os.path.join(out, cli.SAMPLE))
    frame_sha = sha256_of(os.path.join(out, cli.FRAME))
    # A rerun must not redraw, not even with the same seed: the draw's
    # timestamp is part of the record and a second draw is a second draw.
    assert cli.main(['sample', '--out', out]) == 0
    second = read_json(os.path.join(out, cli.SAMPLE))
    assert second == first
    assert sha256_of(os.path.join(out, cli.FRAME)) == frame_sha


def test_the_sample_reproduces_from_the_frame_and_the_recipe(trial, tmp_path):
    """What makes the draw independent of the predictions: anyone with the
    frame and the armed seed gets the same ids."""
    out = str(tmp_path)
    assert cli.main(['sample', '--out', out]) == 0
    frame = read_json(os.path.join(out, cli.FRAME))
    sample = read_json(os.path.join(out, cli.SAMPLE))
    with flask_app.app_context():
        recipe = judge_trial.current().recipe
        identity = {'artifact_sha256': fixture_sha(),
                    'prompt_version': llm_sentiment.PROMPT_VERSION,
                    'model_id': ENCODER}
    assert sample['sample_size'] == recipe['sample_size'] == SIZE
    assert sample['seed'] == recipe['seed']
    assert sample['mention_ids'] == sorted(
        random.Random(recipe['seed']).sample(frame['mention_ids'], SIZE))
    assert sample['frame_sha256'] == sha256_of(os.path.join(out, cli.FRAME))
    assert sample['trial'] == frame['trial'] == identity
    assert sample['drawn_at']


# ---- 2. predictions: exactly the sample, offline, from the frozen artifact --

def test_predict_scores_exactly_the_sample_offline_and_meters_the_calls(
        trial, tmp_path):
    """The real fixture artifact, through the real adapter. No mention or
    history is written; the spend meter books the calls; the file says
    which artifact and which sample it came from."""
    out = str(tmp_path)
    assert cli.main(['sample', '--out', out]) == 0
    ids = sampled_ids(out)
    with flask_app.app_context():
        history_before = RadarSentimentJudgment.query.count()
        spent = db.session.get(RadarLlmSpend, (dt.date.today(), ENCODER))
        calls_before = spent.calls if spent else 0

    assert cli.main(['predict', '--out', out, '--backend', 'encoder',
                     '--artifact-dir', FIXTURE]) == 0

    provenance, verdicts = cli.read_predictions(predictions_path(out, ENCODER))
    assert sorted(verdicts) == ids
    assert provenance['backend'] == ENCODER
    assert provenance['artifact_sha256'] == fixture_sha()
    assert provenance['prompt_version'] == llm_sentiment.PROMPT_VERSION
    assert provenance['sample_sha256'] == sha256_of(os.path.join(out, cli.SAMPLE))
    for verdict in verdicts.values():
        for field in FIELDS:
            assert verdict[field] in llm_sentiment._FIELD_ENUMS[field]
    with flask_app.app_context():
        db.session.expire_all()
        assert RadarSentimentJudgment.query.count() == history_before
        judged = (db.session.query(RadarMention)
                  .filter(RadarMention.id.in_(ids),
                          RadarMention.sentiment_judged_at.isnot(None)).count())
        assert judged == 0
        spent = db.session.get(RadarLlmSpend, (dt.date.today(), ENCODER))
        expected_calls = -(-SIZE // judge_backends.ENCODER_BATCH_SIZE)
        assert spent.calls == calls_before + expected_calls


def test_predict_refuses_an_artifact_other_than_the_armed_one(trial, tmp_path,
                                                              monkeypatch):
    out = str(tmp_path)
    assert cli.main(['sample', '--out', out]) == 0
    fake_backends(monkeypatch, encoder_sha='e' * 64)
    assert cli.main(['predict', '--out', out, '--backend', 'encoder']) == 1
    assert not os.path.exists(predictions_path(out, ENCODER))


def test_a_paid_prediction_pass_needs_explicit_confirmation(trial, tmp_path,
                                                            monkeypatch):
    """Quota is never spent unasked. Without the flag the backend is not
    even constructed."""
    out = str(tmp_path)
    assert cli.main(['sample', '--out', out]) == 0
    made = fake_backends(monkeypatch)
    assert cli.main(['predict', '--out', out, '--backend',
                     'anthropic:' + HAIKU]) == 1
    assert 'haiku' not in made
    assert not os.path.exists(predictions_path(out, HAIKU))


# ---- 3. evaluate: the labels are the sample, every value a verdict ----------

def test_evaluate_refuses_labels_that_are_not_the_sample(trial, tmp_path,
                                                         monkeypatch):
    """Sixty arbitrary rows with a perfect removal record are not an
    audit of this trial. The denominator is the frozen sample, and a label
    file that is not it is refused outright."""
    out, _labels, _report, _ = chain(tmp_path, monkeypatch)
    os.remove(os.path.join(out, cli.REPORT_JSON))
    # Every sampled row correctly labelled AND five strays: the only thing
    # wrong with this file is that it is not exactly the sample, so the
    # only way to refuse it is the membership check itself.
    rows = {key: dict(REMOVED) for key in sampled_ids(out)}
    rows.update({1000000 + i: dict(REMOVED) for i in range(5)})
    superset = write_labels(tmp_path / 'superset.jsonl', rows)
    assert cli.main(evaluate_args(out, superset)) == 1
    assert not os.path.exists(os.path.join(out, cli.REPORT_JSON))


def test_a_missing_or_invalid_label_fails_coverage(trial, tmp_path,
                                                   monkeypatch):
    out, _labels, _report, _ = chain(tmp_path, monkeypatch)
    ids = sampled_ids(out)

    short = {key: dict(REMOVED) for key in ids[:-1]}
    short_path = write_labels(tmp_path / 'short.jsonl', short)
    assert cli.main(evaluate_args(out, short_path)) == 0
    report = read_json(os.path.join(out, cli.REPORT_JSON))
    assert report['passed'] is False
    assert report['coverage']['complete'] is False
    assert report['coverage']['missing_count'] == 1

    invalid = {key: dict(REMOVED) for key in ids}
    invalid[ids[0]]['relevance'] = 'yes'
    invalid_path = write_labels(tmp_path / 'invalid.jsonl', invalid)
    assert cli.main(evaluate_args(out, invalid_path)) == 0
    report = read_json(os.path.join(out, cli.REPORT_JSON))
    assert report['passed'] is False
    assert report['coverage']['complete'] is False


def test_an_empty_verdict_is_not_a_prediction(trial, tmp_path, monkeypatch):
    """An empty label and an empty prediction agree on nothing, and used
    to count as agreement on every field."""
    out, labels_path, _report, _ = chain(tmp_path, monkeypatch)
    ids = sampled_ids(out)
    provenance, verdicts = cli.read_predictions(predictions_path(out, ENCODER))
    verdicts[ids[0]] = {}
    hollow = str(tmp_path / 'hollow.jsonl')
    cli.write_predictions(hollow, provenance, verdicts)
    assert cli.main(evaluate_args(out, labels_path, encoder=hollow)) == 0
    report = read_json(os.path.join(out, cli.REPORT_JSON))
    assert report['coverage']['complete'] is False
    assert report['passed'] is False


def test_evaluate_refuses_predictions_from_another_artifact_or_sample(
        trial, tmp_path, monkeypatch):
    out, labels_path, _report, _ = chain(tmp_path, monkeypatch)
    provenance, verdicts = cli.read_predictions(predictions_path(out, ENCODER))

    other_artifact = str(tmp_path / 'other-artifact.jsonl')
    cli.write_predictions(other_artifact,
                          dict(provenance, artifact_sha256='e' * 64), verdicts)
    assert cli.main(evaluate_args(out, labels_path,
                                  encoder=other_artifact)) == 1

    other_sample = str(tmp_path / 'other-sample.jsonl')
    cli.write_predictions(other_sample,
                          dict(provenance, sample_sha256='5' * 64), verdicts)
    assert cli.main(evaluate_args(out, labels_path, encoder=other_sample)) == 1


def test_shadow_days_come_from_the_history_not_from_a_flag(trial, tmp_path,
                                                           monkeypatch):
    """Seven days of trial-mode history with the tone that was displayed
    must ACCOMPANY the tone report (spec 7.2c). It is read from the
    judgment history, not asserted on the command line."""
    with pytest.raises(SystemExit):
        cli.main(['evaluate', '--out', str(tmp_path), '--labels', 'x',
                  '--encoder-predictions', 'x', '--haiku-predictions', 'x',
                  '--shadow-days', '7'])

    out, labels_path, _report, report = chain(tmp_path, monkeypatch)
    shadow = [c for c in report['tone']['criteria']
              if c['criterion'] == 'shadow_period'][0]
    assert shadow['passed'] is False
    assert report['shadow']['rows'] == 0

    with flask_app.app_context():
        first = started_at()
        ids = sampled_ids(out)
        for day, key in enumerate(ids[:9]):
            db.session.add(RadarSentimentJudgment(
                mention_id=key, stage='primary', model=ENCODER,
                prompt_version=llm_sentiment.PROMPT_VERSION,
                relevance='relevant', content_origin='human_chatter',
                attitude='positive', expected_move='up', confidence='high',
                input_tokens=0, output_tokens=0,
                created_utc=first + dt.timedelta(days=day),
                displayed_tone='neutral', displayed_judged_by='lexicon'))
        db.session.commit()
    assert cli.main(evaluate_args(out, labels_path)) == 0
    report = read_json(os.path.join(out, cli.REPORT_JSON))
    shadow = [c for c in report['tone']['criteria']
              if c['criterion'] == 'shadow_period'][0]
    assert shadow['passed'] is True
    assert report['shadow']['rows'] == 9
    assert report['shadow']['days'] == pytest.approx(8.0)


# ---- 4. completeness: supplemental evidence and label provenance -----------

def test_a_report_without_supplemental_evidence_is_incomplete(trial, tmp_path,
                                                              monkeypatch):
    out, labels_path, report_path, report = chain(tmp_path, monkeypatch,
                                                  supplemental=False)
    assert report['passed'] is True
    assert report['complete'] is False
    assert any('supplemental' in reason for reason in report['incomplete_reasons'])
    ack = write_ack(out, report_path)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 1
    with flask_app.app_context():
        assert judge_trial.current().audit_evaluated_at is None


def test_supplemental_sets_are_reported_apart_and_never_enter_the_gate(
        trial, tmp_path, monkeypatch):
    _out, _labels, _report, report = chain(tmp_path, monkeypatch)
    supplemental = report['supplemental']
    audit = supplemental['audit']
    assert set(audit['halves']) == {'removal', 'natural'}
    assert audit['halves']['removal']['reversal_rate']['successes'] == 2
    assert audit['halves']['natural']['reversal_rate']['successes'] == 0
    assert supplemental['natural']['reversal_rate']['successes'] == 3
    # Listed for inspection: every reversal, and every disagreement on a
    # truncated post.
    assert len(audit['reversal_disagreements']) == 2
    assert all(row['truncated'] is False
               for row in audit['reversal_disagreements'])
    assert supplemental['natural']['reversal_rate']['total'] == 20
    # None of it touches the gate.
    assert report['passed'] is True
    assert report['complete'] is True


def test_label_provenance_requires_a_reason_for_every_adjudicated_change(
        trial, tmp_path, monkeypatch):
    out, _labels, _report, _ = chain(tmp_path, monkeypatch)
    ids = sampled_ids(out)
    final = {key: dict(REMOVED) for key in ids}
    with_reason = write_labels(
        tmp_path / 'adjudicated.jsonl', final,
        adjudicate={ids[0]: (dict(KEPT), 'the post is a bot relay')})
    assert cli.main(evaluate_args(out, with_reason)) == 0
    report = read_json(os.path.join(out, cli.REPORT_JSON))
    assert report['labels']['provenance_ok'] is True
    assert report['labels']['adjudicated'] == 1
    assert report['complete'] is True

    without = write_labels(tmp_path / 'silent.jsonl', final,
                           adjudicate={ids[0]: (dict(KEPT), None)})
    assert cli.main(evaluate_args(out, without)) == 0
    report = read_json(os.path.join(out, cli.REPORT_JSON))
    assert report['labels']['provenance_ok'] is False
    assert report['complete'] is False


# ---- 5. accept: reproduce, acknowledge, and only then record ----------------

def test_the_full_chain_records_a_passing_audit(trial, tmp_path, monkeypatch):
    out, _labels, report_path, report = chain(tmp_path, monkeypatch)
    assert report['passed'] is True and report['complete'] is True
    ack = write_ack(out, report_path)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 0
    with flask_app.app_context():
        row = judge_trial.current()
        assert row.audit_passed is True
        assert row.audit_report_sha256 == sha256_of(report_path)
        assert judge_trial.deadline(row) is None
        assert row.status == judge_trial.RUNNING


def test_a_failing_chain_starts_recovery(trial, tmp_path, monkeypatch):
    """The encoder deleted everything; the humans say it was all real."""
    out, _labels, report_path, report = chain(
        tmp_path, monkeypatch, encoder_answer=REMOVED, haiku_answer=KEPT,
        labels=None)
    ids = sampled_ids(out)
    honest = write_labels(tmp_path / 'honest.jsonl',
                          {key: dict(KEPT) for key in ids})
    assert cli.main(evaluate_args(out, honest)) == 0
    report = read_json(report_path)
    assert report['passed'] is False
    ack = write_ack(out, report_path)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 0
    with flask_app.app_context():
        row = judge_trial.current()
        assert row.audit_passed is False
        assert row.status == judge_trial.RECOVERING


def test_accept_recomputes_the_verdict_from_the_inputs(trial, tmp_path,
                                                       monkeypatch):
    """A report is a claim about its inputs. Acceptance re-derives the
    claim; a flipped flag with a matching acknowledgment is still refused."""
    out, _labels, report_path, report = chain(
        tmp_path, monkeypatch, encoder_answer=REMOVED, haiku_answer=KEPT)
    ids = sampled_ids(out)
    honest = write_labels(tmp_path / 'honest.jsonl',
                          {key: dict(KEPT) for key in ids})
    assert cli.main(evaluate_args(out, honest)) == 0
    report = read_json(report_path)
    assert report['passed'] is False

    report['passed'] = True
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=1, sort_keys=True, default=str)
    ack = write_ack(out, report_path)             # acknowledges the forgery
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 1
    with flask_app.app_context():
        assert judge_trial.current().audit_evaluated_at is None


def test_accept_refuses_an_input_that_changed_since_the_report(
        trial, tmp_path, monkeypatch):
    out, labels_path, report_path, _ = chain(tmp_path, monkeypatch)
    with open(labels_path, 'a', encoding='utf-8') as handle:
        handle.write('\n')
    ack = write_ack(out, report_path)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 1


def test_accept_refuses_without_the_required_inspections(trial, tmp_path,
                                                         monkeypatch):
    out, _labels, report_path, _ = chain(tmp_path, monkeypatch)
    partial = write_ack(out, report_path, inspected=('reversal_disagreements',))
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', partial]) == 1

    other = write_ack(out, report_path)
    with open(other, encoding='utf-8') as handle:
        payload = json.load(handle)
    payload['report_sha256'] = '0' * 64
    with open(other, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', other]) == 1

    with flask_app.app_context():
        assert judge_trial.current().audit_evaluated_at is None


def test_accept_refuses_labels_finished_after_day_seven(trial, tmp_path,
                                                        monkeypatch):
    out, _labels, report_path, _ = chain(tmp_path, monkeypatch)
    ids = sampled_ids(out)
    late = write_labels(tmp_path / 'late.jsonl',
                        {key: dict(REMOVED) for key in ids},
                        labelled_at=started_at() + dt.timedelta(days=7, hours=1))
    assert cli.main(evaluate_args(out, late)) == 0
    ack = write_ack(out, report_path)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 1


def test_a_minimal_report_is_refused_even_with_matching_identity(trial,
                                                                 tmp_path):
    """The reproduction from the review: matching artifact and prompt plus
    a passing flag, and nothing else."""
    with flask_app.app_context():
        row = judge_trial.current()
        minimal = {'passed': True,
                   'trial': {'artifact_sha256': row.artifact_sha256,
                             'prompt_version': row.prompt_version}}
        with pytest.raises(judge_trial.TrialError):
            judge_trial.accept_audit(minimal, 'c' * 64,
                                     dt.datetime.utcnow(), passed=True)
    report_path = str(tmp_path / 'minimal.json')
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(minimal, handle)
    ack = write_ack(str(tmp_path), report_path)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 1
    with flask_app.app_context():
        assert judge_trial.current().audit_evaluated_at is None


def test_acceptance_needs_a_first_judgment(trial):
    """A trial that has judged nothing has nothing to have been audited."""
    with flask_app.app_context():
        row = judge_trial.current()
        row.first_judged_at = None
        row.status = judge_trial.ARMED
        db.session.commit()
        report = {'schema': cli.SCHEMA, 'passed': True, 'complete': True,
                  'trial': {'artifact_sha256': row.artifact_sha256,
                            'prompt_version': row.prompt_version}}
        with pytest.raises(judge_trial.TrialError):
            judge_trial.accept_audit(report, 'c' * 64, dt.datetime.utcnow(),
                                     passed=True)


# ---- 6. the supplemental sets are the frozen sets, not any file -------------

def test_an_empty_supplemental_file_is_not_evidence(trial, tmp_path,
                                                    monkeypatch):
    """Two existing files with zero rows produced a complete report and
    reached acceptance. A set is the rows frozen at arming, and a file
    that holds none of them holds no evidence."""
    out, labels_path, report_path, _ = chain(tmp_path, monkeypatch)
    for name in ('supplemental-audit.jsonl', 'supplemental-natural.jsonl'):
        open(os.path.join(out, name), 'w', encoding='utf-8').close()
    assert cli.main(evaluate_args(out, labels_path)) == 0
    report = read_json(report_path)
    assert report['passed'] is True
    assert report['complete'] is False
    assert any('missing' in reason for reason in report['incomplete_reasons'])
    ack = write_ack(out, report_path)
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 1
    with flask_app.app_context():
        assert judge_trial.current().audit_evaluated_at is None


@pytest.mark.parametrize('damage', ['missing', 'extra', 'duplicate',
                                    'wrong_half'])
def test_supplemental_membership_must_match_what_was_frozen(
        trial, tmp_path, monkeypatch, damage):
    out, labels_path, report_path, report = chain(tmp_path, monkeypatch)
    assert report['complete'] is True
    audit_path = os.path.join(out, 'supplemental-audit.jsonl')
    rows = [json.loads(line) for line in open(audit_path, encoding='utf-8')]
    if damage == 'missing':
        rows = rows[1:]
    elif damage == 'extra':
        rows.append(dict(rows[0], key='removal-999'))
    elif damage == 'duplicate':
        rows.append(dict(rows[0]))
    else:
        rows[0] = dict(rows[0], half='natural')
    write_supplemental(audit_path, rows)

    assert cli.main(evaluate_args(out, labels_path)) == 0
    report = read_json(report_path)
    assert report['complete'] is False
    assert report['incomplete_reasons']
    assert report['passed'] is True            # completeness, not the gate


# ---- 7. accept reproduces the whole report, not its flags ------------------

@pytest.mark.parametrize('edit', ['numbers', 'supplemental'])
def test_accept_refuses_a_report_whose_content_was_edited(trial, tmp_path,
                                                          monkeypatch, edit):
    """The flags reproduced while the numbers behind them did not: a
    numerator and denominator set to 99999, a natural-set count set to
    900, and an acknowledgment of that report's hash still reached
    persistence. What is acknowledged must be what the inputs say."""
    out, _labels, report_path, report = chain(tmp_path, monkeypatch)
    if edit == 'numbers':
        removal = [c for c in report['criteria']
                   if c['criterion'] == 'removal_precision'][0]
        removal['encoder']['successes'] = 99999
        removal['encoder']['total'] = 99999
    else:
        report['supplemental']['natural']['rows'] = 900
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=1, sort_keys=True, default=str)
    ack = write_ack(out, report_path)             # acknowledges the edit
    assert cli.main(['accept', '--report', report_path,
                     '--acknowledgments', ack]) == 1
    with flask_app.app_context():
        assert judge_trial.current().audit_evaluated_at is None
