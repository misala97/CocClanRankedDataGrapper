#!/usr/bin/env python
"""Draw, label, predict, evaluate and record the trial's fresh audit.

The existing 200-row audit cannot answer the question this one has to: half
of it was chosen BECAUSE the encoder wanted to delete those rows, so it
cannot estimate removal precision on production traffic, and more enriched
rows cannot fix that. This draws a fresh, uniformly sampled set instead.

    python -m scripts.audit_encoder_trial sample        --out DIR
    python -m scripts.audit_encoder_trial export-labels --out DIR
    python -m scripts.audit_encoder_trial predict       --out DIR --backend encoder
    python -m scripts.audit_encoder_trial predict       --out DIR \
        --backend anthropic:claude-haiku-4-5 --confirm-spend
    python -m scripts.audit_encoder_trial evaluate      --out DIR --labels FILE \
        --encoder-predictions FILE --haiku-predictions FILE \
        --supplemental-audit FILE --supplemental-natural FILE
    python -m scripts.audit_encoder_trial accept        --report FILE \
        --acknowledgments FILE

It is a CHAIN, and every link reads what the one before it wrote and
refuses what it did not:

- `sample` freezes the frame and draws from it with the seed fixed at
  arming, on day three and not before, once. The frame and the sample both
  carry the trial's identity.
- `predict` scores exactly the sampled ids through the canonical prepared
  inputs -- the same function the live pass uses -- against the frozen
  artifact, offline: nothing goes through apply_judgments, so a prediction
  pass can never move a mention, a bucket or the history. Its file says
  which artifact and which sample it came from. A paid backend needs
  --confirm-spend; quota is never spent unasked.
- `evaluate` refuses labels that are not the sample and predictions that
  are not from this artifact and this sample, reads the tone shadow period
  from the judgment history rather than from a flag, and writes a report
  that records the hash of every input it used and whether it is complete.
- `accept` re-hashes those inputs, REPRODUCES the verdict from them,
  requires the inspections the spec asks for to be acknowledged against
  this exact report, checks the day-3/day-7 timing, and only then records
  the result. It is the only command that writes trial state.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import (judge_backends, judge_trial,  # noqa: E402
                            llm_sentiment, spend, trial_audit)
from features.radar.trial_audit import AuditError  # noqa: E402
from models import RadarMention, RadarPost, RadarSentimentJudgment  # noqa: E402

SCHEMA = 'radar-encoder-trial-audit-3'
FRAME = 'frame.json'
SAMPLE = 'sample.json'
BLIND = 'blind.jsonl'
REPORT_JSON = 'report.json'
REPORT_MD = 'report.md'
ACKNOWLEDGMENTS = 'acknowledgments.json'
# What a human must have looked at before a report can be accepted (spec
# 7.2c): the reversal disagreements and the truncated-post disagreements
# the supplemental sets list for inspection.
REQUIRED_INSPECTIONS = ('reversal_disagreements', 'truncated_disagreements')
LABEL_FIELDS = tuple(llm_sentiment._FIELD_ENUMS)


# ---- files -------------------------------------------------------------------

def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def _write(path, payload):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=1, sort_keys=True,
                  default=_json_default)
    return path


def _read(path):
    if not os.path.isfile(path):
        raise AuditError('no such file: %s' % path)
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def _rows(path):
    if not os.path.isfile(path):
        raise AuditError('no such file: %s' % path)
    with open(path, encoding='utf-8') as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if line:
                try:
                    yield number, json.loads(line)
                except ValueError as exc:
                    raise AuditError('%s line %d is not JSON: %s'
                                     % (path, number, exc))


def _when(value, what):
    """An ISO timestamp as naive UTC. Every clock in this chain is UTC."""
    if isinstance(value, dt.datetime):
        return value
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise AuditError('%s is not a timestamp: %r' % (what, value))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed


def _utcnow():
    return dt.datetime.utcnow()


# ---- the trial -----------------------------------------------------------------

def _identity(row):
    """What the trial IS. Written into every file this chain produces and
    checked at every link, so a file from another trial cannot be mistaken
    for one of this trial's."""
    return {'artifact_sha256': row.artifact_sha256,
            'prompt_version': row.prompt_version,
            'model_id': row.model_id}


def _current_trial():
    row = judge_trial.current()
    if row is None:
        raise AuditError('no trial is armed')
    return row


# ---- sample --------------------------------------------------------------------

def cmd_sample(out_dir, now=None):
    """Freeze the frame, then draw from it with the seed fixed at arming.

    The frame is EVERY retained high-confidence mention in the first three
    days of the trial, across all sources and tickers, with no gate,
    removal or confidence enrichment. Enriching it is what made the last
    audit unable to answer the question.

    On day three and not before: a frame drawn earlier is not complete.
    Not after day seven either -- a draw then could not be labelled in
    time and would never be accepted. Once: a rerun reuses the recorded
    draw, because the draw's timestamp is part of the record and a second
    draw is a second draw.
    """
    os.makedirs(out_dir, exist_ok=True)
    now = now or _utcnow()
    sample_path = os.path.join(out_dir, SAMPLE)
    with app.app_context():
        row = _current_trial()
        identity = _identity(row)
        if os.path.exists(sample_path):
            sample = _read(sample_path)
            if sample.get('trial') != identity:
                raise AuditError('%s holds a draw for a different trial'
                                 % sample_path)
            print('reusing the draw of %s: %d ids from a frame of %s'
                  % (sample.get('drawn_at'), len(sample['mention_ids']),
                     sample.get('frame_sha256', '')[:12]))
            return 0
        if row.first_judged_at is None:
            raise AuditError('the trial has not judged anything yet; the '
                             'frame is defined from its first judgment')
        start = row.first_judged_at
        end = start + dt.timedelta(days=judge_trial.AUDIT_DRAW_DAY)
        if now < end:
            raise AuditError('the frame closes at %s; a draw before then is '
                             'a draw from an incomplete frame' % end)
        latest = start + dt.timedelta(days=judge_trial.AUDIT_LABEL_DAY)
        if now > latest:
            raise AuditError('day %d passed at %s; a draw now could not be '
                             'labelled in time and would never be accepted'
                             % (judge_trial.AUDIT_LABEL_DAY, latest))
        ids = [int(i) for (i,) in db.session.query(RadarMention.id)
               .join(RadarPost, RadarPost.id == RadarMention.post_id)
               .filter(RadarMention.confidence == 'high',
                       RadarPost.created_utc >= start,
                       RadarPost.created_utc < end)
               .order_by(RadarMention.id).all()]
        recipe = row.recipe or {}
        wanted = int(recipe.get('sample_size') or 0)
        seed = recipe.get('seed')
        if not wanted or seed is None:
            raise AuditError('the armed recipe carries no sample size or seed')

    frame_path = _write(os.path.join(out_dir, FRAME),
                        {'first_judged_at': start, 'until': end,
                         'mention_ids': ids, 'size': len(ids),
                         'trial': identity, 'frozen_at': now})
    if len(ids) < wanted:
        raise AuditError(
            'the frame holds %d mentions and the recipe needs %d. Too little '
            'traffic is a FAILED audit, not permission to shrink the sample '
            'or widen the frame.' % (len(ids), wanted))

    drawn = sorted(random.Random(seed).sample(ids, wanted))
    _write(sample_path,
           {'seed': seed, 'sample_size': wanted, 'mention_ids': drawn,
            'frame_sha256': sha256_of(frame_path), 'drawn_at': now,
            'trial': identity})
    print('frame %d mentions -> sampled %d with seed %s'
          % (len(ids), wanted, seed))
    return 0


def _sampled_rows(ids):
    rows = (db.session.query(RadarMention, RadarPost)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.id.in_(list(ids))).all())
    if len(rows) != len(ids):
        raise AuditError('%d of %d sampled mentions are no longer retained; '
                         'a shrunken denominator is a failed audit'
                         % (len(rows), len(ids)))
    return rows


def cmd_export_labels(out_dir):
    """The blind file a human labels: text and ticker, no predictions.

    Neither backend's answer appears here. A labeller who can see what the
    model said is not producing an independent reference, and this audit
    exists precisely because the last reference was not independent enough.
    """
    sample = _read(os.path.join(out_dir, SAMPLE))
    with app.app_context():
        rows = _sampled_rows(sample['mention_ids'])
        written = 0
        with open(os.path.join(out_dir, BLIND), 'w', encoding='utf-8') as out:
            for mention, post in rows:
                out.write(json.dumps({
                    'mention_id': mention.id, 'ticker': mention.ticker,
                    'source': post.source, 'channel': post.channel,
                    'author': post.author, 'title': post.title,
                    'body': post.body}) + '\n')
                written += 1
    print('wrote %d blind rows' % written)
    return 0


# ---- predictions ---------------------------------------------------------------

def write_predictions(path, provenance, verdicts):
    """A JSONL file whose first line says where it came from."""
    with open(path, 'w', encoding='utf-8') as out:
        out.write(json.dumps({'provenance': provenance},
                             default=_json_default) + '\n')
        for key in sorted(verdicts):
            out.write(json.dumps(dict(verdicts[key], mention_id=key)) + '\n')
    return path


def read_predictions(path):
    """(provenance, {mention_id: verdict}). A file with no provenance
    header is refused: a prediction that cannot say which artifact and
    which sample it came from is not evidence about this trial."""
    provenance = None
    verdicts = {}
    for number, row in _rows(path):
        if 'provenance' in row:
            if provenance is not None:
                raise AuditError('%s carries two provenance headers' % path)
            provenance = row['provenance']
            continue
        if 'mention_id' not in row:
            raise AuditError('%s line %d names no mention_id' % (path, number))
        key = int(row.pop('mention_id'))
        if key in verdicts:
            raise AuditError('%s answers mention %d twice' % (path, key))
        verdicts[key] = row
    if provenance is None:
        raise AuditError('%s carries no provenance header; a prediction file '
                         'must say which backend, artifact and sample it '
                         'came from' % path)
    return provenance, verdicts


def cmd_predict(out_dir, backend_spec, *, artifact_dir=None,
                confirm_spend=False, now=None):
    """Score exactly the sampled ids, offline, from the frozen artifact.

    Through `llm_sentiment.items_for` and `llm_sentiment.judge` -- the
    canonical prepared inputs and the one validation boundary the live
    pass uses -- but never through apply_judgments: nothing here can move
    a mention, a bucket, the history or the trial. Only the spend meter is
    written, which is what the spec asks of a paid pass.
    """
    now = now or _utcnow()
    sample_path = os.path.join(out_dir, SAMPLE)
    if not os.path.exists(sample_path):
        raise AuditError('no sample in %s; run `sample` first' % out_dir)
    sample = _read(sample_path)
    ids = [int(i) for i in sample['mention_ids']]
    spec = (backend_spec or '').strip()
    with app.app_context():
        row = _current_trial()
        identity = _identity(row)
        if sample.get('trial') != identity:
            raise AuditError('%s holds a draw for a different trial'
                             % sample_path)
        if spec != 'encoder' and not confirm_spend:
            raise AuditError('%r is a paid backend and %d rows would be sent. '
                             'Quota is never spent unasked: pass '
                             '--confirm-spend to authorise this pass'
                             % (spec, len(ids)))
        backend = judge_backends.construct_backend(spec,
                                                   artifact_dir=artifact_dir)
        artifact = None
        if backend.id == judge_backends.ENCODER_MODEL_ID:
            artifact = backend.bundle_sha256()
            if artifact != row.artifact_sha256:
                raise AuditError('the artifact at hand (%s) is not the one the '
                                 'trial armed (%s); predictions from another '
                                 'artifact say nothing about this trial'
                                 % (artifact[:12], row.artifact_sha256[:12]))
        rows = _sampled_rows(ids)
        items = llm_sentiment.items_for(rows)
        meter = {'calls': 0, 'input': 0, 'output': 0}

        def count(usage):
            meter['calls'] += 1
            meter['input'] += getattr(usage, 'input_tokens', 0) or 0
            meter['output'] += getattr(usage, 'output_tokens', 0) or 0

        answers = llm_sentiment.judge(items, backend, on_usage=count)
        spend.record(backend.id, calls=meter['calls'],
                     input_tokens=meter['input'], output_tokens=meter['output'])
        verdicts = {key: {field: getattr(answer.judgment, field)
                          for field in LABEL_FIELDS}
                    for key, answer in answers.items()}
        backend_id = backend.id

    provenance = {'backend': backend_id, 'artifact_sha256': artifact,
                  'prompt_version': llm_sentiment.PROMPT_VERSION,
                  'sample_sha256': sha256_of(sample_path),
                  'predicted_at': now, 'asked': len(ids),
                  'answered': len(verdicts), 'calls': meter['calls'],
                  'input_tokens': meter['input'],
                  'output_tokens': meter['output']}
    path = write_predictions(os.path.join(out_dir, '%s.jsonl' % backend_id),
                             provenance, verdicts)
    print('%s answered %d of %d sampled rows in %d calls -> %s'
          % (backend_id, len(verdicts), len(ids), meter['calls'], path))
    if len(verdicts) < len(ids):
        print('  %d unanswered: they will fail coverage, which is the point'
              % (len(ids) - len(verdicts)))
    return 0


# ---- evaluate --------------------------------------------------------------------

def _labels(path, wanted):
    """The human labels, and the provenance the spec requires of them.

    Exactly the sample: a labelled row outside it is refused outright,
    because the denominator is the frozen draw and nothing else. A sampled
    row with no label is left to coverage, which fails the audit.

    Provenance: every row says when it was labelled, and a row whose
    final label differs from its `original` says why. A silent
    adjudication makes the report incomplete.
    """
    labels = {}
    problems = []
    adjudicated = 0
    completed_at = None
    for number, row in _rows(path):
        if 'mention_id' not in row:
            raise AuditError('%s line %d names no mention_id' % (path, number))
        key = int(row['mention_id'])
        if key not in wanted:
            raise AuditError('%s line %d labels mention %d, which is not in '
                             'the frozen sample; the labels must be exactly '
                             'the sample' % (path, number, key))
        if key in labels:
            raise AuditError('%s labels mention %d twice' % (path, key))
        final = {field: row.get(field) for field in LABEL_FIELDS}
        labels[key] = final
        when = row.get('labelled_at')
        if not when:
            problems.append('mention %d carries no labelled_at' % key)
        else:
            when = _when(when, 'labelled_at of mention %d' % key)
            completed_at = when if completed_at is None else max(completed_at,
                                                                 when)
        original = row.get('original')
        if original is not None:
            first = {field: original.get(field) for field in LABEL_FIELDS}
            if first != final:
                adjudicated += 1
                if not str(row.get('adjudication_reason') or '').strip():
                    problems.append('mention %d was adjudicated away from its '
                                    'original label with no reason recorded'
                                    % key)
    return labels, {'rows': len(labels), 'completed_at': completed_at,
                    'provenance_ok': not problems, 'adjudicated': adjudicated,
                    'problems': problems}


def _check_provenance(provenance, name, identity, sample_sha,
                      *, backend=None, backend_prefix=None, artifact=None):
    if provenance.get('sample_sha256') != sample_sha:
        raise AuditError('the %s predictions were made for a different sample '
                         '(%s, not %s)'
                         % (name, str(provenance.get('sample_sha256'))[:12],
                            sample_sha[:12]))
    if provenance.get('prompt_version') != identity['prompt_version']:
        raise AuditError('the %s predictions answer prompt version %r, the '
                         'trial froze %r'
                         % (name, provenance.get('prompt_version'),
                            identity['prompt_version']))
    if backend is not None and provenance.get('backend') != backend:
        raise AuditError('the %s predictions come from %r, not %r'
                         % (name, provenance.get('backend'), backend))
    if backend_prefix is not None and not str(
            provenance.get('backend') or '').startswith(backend_prefix):
        raise AuditError('the %s predictions come from %r, which is not an '
                         'incumbent %s* model'
                         % (name, provenance.get('backend'), backend_prefix))
    if artifact is not None and provenance.get('artifact_sha256') != artifact:
        raise AuditError('the %s predictions were made with artifact %s, the '
                         'trial armed %s'
                         % (name, str(provenance.get('artifact_sha256'))[:12],
                            artifact[:12]))


def _shadow(row):
    """The tone shadow period, read from the judgment history: how long
    the trial has been recording what it would have said beside what was
    displayed (spec 7.2c). Not a flag."""
    rows = (db.session.query(RadarSentimentJudgment.created_utc)
            .filter(RadarSentimentJudgment.model == row.model_id,
                    RadarSentimentJudgment.prompt_version == row.prompt_version,
                    RadarSentimentJudgment.stage == 'primary',
                    RadarSentimentJudgment.displayed_tone.isnot(None))
            .all())
    if not rows:
        return {'rows': 0, 'days': 0.0, 'from': None, 'until': None}
    stamps = [when for (when,) in rows]
    first, last = min(stamps), max(stamps)
    return {'rows': len(rows), 'from': first, 'until': last,
            'days': (last - first).total_seconds() / 86400.0}


def _supplemental(audit_path, natural_path):
    """The two supplementary sets (spec 7.3), or the reasons the report is
    incomplete without them."""
    section, reasons = {}, []
    for name, path in (('audit', audit_path), ('natural', natural_path)):
        if not path:
            reasons.append('no supplemental %s set was supplied' % name)
            continue
        if not os.path.isfile(path):
            reasons.append('supplemental %s set not found: %s' % (name, path))
            continue
        rows = [row for _n, row in _rows(path)]
        section[name] = trial_audit.supplemental_section(rows, name)
        if section[name]['invalid_rows']:
            reasons.append('supplemental %s set: %d rows carry no valid '
                           'reference or prediction'
                           % (name, section[name]['invalid_rows']))
    return section, reasons


def _assemble(out_dir, labels_path, encoder_path, haiku_path,
              supplemental_audit=None, supplemental_natural=None):
    """Everything `evaluate` computes from and `accept` reproduces with,
    verified the same way in both places."""
    sample_path = os.path.join(out_dir, SAMPLE)
    frame_path = os.path.join(out_dir, FRAME)
    sample = _read(sample_path)
    frame = _read(frame_path)
    if sha256_of(frame_path) != sample.get('frame_sha256'):
        raise AuditError('the frame has changed since the draw was made')
    with app.app_context():
        row = _current_trial()
        identity = _identity(row)
        if sample.get('trial') != identity or frame.get('trial') != identity:
            raise AuditError('the frame and sample in %s belong to a different '
                             'trial' % out_dir)
        recipe = row.recipe or {}
        if (sample.get('sample_size') != recipe.get('sample_size')
                or sample.get('seed') != recipe.get('seed')):
            raise AuditError('the sample was not drawn with the armed recipe '
                             '(size %r seed %r, armed %r %r)'
                             % (sample.get('sample_size'), sample.get('seed'),
                                recipe.get('sample_size'), recipe.get('seed')))
        drawn = sorted(random.Random(sample['seed']).sample(
            frame['mention_ids'], sample['sample_size']))
        if drawn != sample['mention_ids']:
            raise AuditError('the sample does not reproduce from the frame '
                             'and the armed seed')
        shadow = _shadow(row)
        first_judged_at = row.first_judged_at

    ids = [int(i) for i in sample['mention_ids']]
    wanted = set(ids)
    labels, label_meta = _labels(labels_path, wanted)
    sample_sha = sha256_of(sample_path)
    encoder_provenance, encoder = read_predictions(encoder_path)
    haiku_provenance, haiku = read_predictions(haiku_path)
    _check_provenance(encoder_provenance, 'encoder', identity, sample_sha,
                      backend=identity['model_id'],
                      artifact=identity['artifact_sha256'])
    _check_provenance(haiku_provenance, 'incumbent', identity, sample_sha,
                      backend_prefix='claude-')
    for name, verdicts in (('encoder', encoder), ('incumbent', haiku)):
        strays = set(verdicts) - wanted
        if strays:
            raise AuditError('the %s predictions answer %d mentions outside '
                             'the sample' % (name, len(strays)))

    supplemental, incomplete = _supplemental(supplemental_audit,
                                             supplemental_natural)
    incomplete = incomplete + list(label_meta['problems'])
    inputs = {'labels': labels_path, 'encoder': encoder_path,
              'haiku': haiku_path, 'sample': sample_path, 'frame': frame_path}
    if supplemental_audit:
        inputs['supplemental_audit'] = supplemental_audit
    if supplemental_natural:
        inputs['supplemental_natural'] = supplemental_natural
    return {
        'bundle': {'reference': labels, 'encoder': encoder, 'haiku': haiku,
                   'sample': ids, 'shadow_days': shadow['days']},
        'inputs': {name: {'path': os.path.abspath(path),
                          'sha256': sha256_of(path)}
                   for name, path in inputs.items()
                   if os.path.isfile(path)},
        'trial': identity,
        'first_judged_at': first_judged_at,
        'sample': {'seed': sample['seed'], 'size': sample['sample_size'],
                   'drawn_at': sample['drawn_at'],
                   'frame_sha256': sample['frame_sha256']},
        'labels': {'rows': label_meta['rows'],
                   'completed_at': label_meta['completed_at'],
                   'provenance_ok': label_meta['provenance_ok'],
                   'adjudicated': label_meta['adjudicated']},
        'predictions': {'encoder': encoder_provenance,
                        'incumbent': haiku_provenance},
        'shadow': shadow,
        'supplemental': supplemental,
        'incomplete': incomplete,
    }


def cmd_evaluate(out_dir, labels, encoder, haiku, supplemental_audit=None,
                 supplemental_natural=None, now=None):
    """Score the two prediction sets against the reference. Offline."""
    now = now or _utcnow()
    assembled = _assemble(out_dir, labels, encoder, haiku,
                          supplemental_audit, supplemental_natural)
    report = trial_audit.evaluate_trial_audit(assembled['bundle'])
    assert report['schema'] == SCHEMA
    for key in ('trial', 'inputs', 'sample', 'labels', 'predictions', 'shadow',
                'supplemental'):
        report[key] = assembled[key]
    report['complete'] = not assembled['incomplete']
    report['incomplete_reasons'] = assembled['incomplete']
    report['evaluated_at'] = now

    path = _write(os.path.join(out_dir, REPORT_JSON), report)
    with open(os.path.join(out_dir, REPORT_MD), 'w', encoding='utf-8') as out:
        out.write(_markdown(report))
    print('%s -- %s' % ('PASSED' if report['passed'] else 'FAILED', path))
    for criterion in report['criteria']:
        print('  %-26s %-5s %s' % (
            criterion['criterion'],
            'pass' if criterion['passed'] else 'FAIL',
            '' if criterion['gates'] else '(reported; does not stop the trial)'))
    print('  tone qualification         %-5s (reported; does not stop the trial)'
          % ('qual' if report['tone']['qualified'] else 'no'))
    print()
    print('  ready to expand later:     %s'
          % ('yes' if report.get('expansion_ready') else 'not yet'))
    print('  complete:                  %s'
          % ('yes' if report['complete'] else
             'NO -- ' + '; '.join(report['incomplete_reasons'])))
    return 0


def _cell(interval):
    if not interval or 'point' not in interval:
        return '--'
    return '%.4f (%d/%d, CI %.4f-%.4f)' % (
        interval['point'], interval['successes'], interval['total'],
        interval['lower'], interval['upper'])


def _markdown(report):
    lines = ['# Encoder trial audit', '',
             '**Result: %s**' % ('PASSED' if report['passed'] else 'FAILED'),
             '**Complete: %s**' % ('yes' if report['complete'] else 'NO'),
             '', 'Sample size: %d' % report['sample_size'], '',
             'One criterion stops the trial: whether it deletes real posts '
             'too often. The comparisons against the paid judge are measured '
             'and reported, and decide nothing here -- that judge stopped '
             'running on 2026-09-03 and is not an alternative. They are the '
             'evidence for a later decision to expand.', '',
             '| criterion | stops the trial | encoder | incumbent | threshold | verdict |',
             '|---|---|---|---|---|---|']
    for criterion in report['criteria']:
        lines.append('| %s | %s | %s | %s | %s | %s |' % (
            criterion['criterion'],
            'yes' if criterion['gates'] else 'no',
            _cell(criterion.get('encoder')), _cell(criterion.get('incumbent')),
            ('%.4f' % criterion['threshold']) if 'threshold' in criterion
            else '--',
            'pass' if criterion['passed'] else '**FAIL**'))
    if report['incomplete_reasons']:
        lines += ['', '## Incomplete', ''] + [
            '- %s' % reason for reason in report['incomplete_reasons']]
    lines += ['', 'Ready to expand later: **%s**'
              % ('yes' if report.get('expansion_ready') else 'not yet')]
    lines += ['', '## Tone', '',
              'Reported, never gating: encoder tone is not written during '
              'the trial, so it cannot pass or fail it. Shadow period: '
              '%.1f days over %d history rows.'
              % (report['shadow']['days'], report['shadow']['rows']), '',
              '| criterion | verdict |', '|---|---|']
    for criterion in report['tone']['criteria']:
        lines.append('| %s | %s |' % (criterion['criterion'],
                                      'pass' if criterion['passed'] else 'FAIL'))
    lines += ['', 'Tone qualification: **%s**'
              % ('qualified' if report['tone']['qualified']
                 else 'not qualified'),
              '', 'Qualifying authorises nothing on its own. Enabling '
              'encoder tone is a separate, separately reviewed change.']
    lines += ['', '## Supplementary sets (reported apart, never in the gate)',
              '']
    for name, section in sorted(report['supplemental'].items()):
        lines += ['### %s' % name, '',
                  '| half | rows | reversal rate | removal precision |',
                  '|---|---|---|---|']
        for half, stats in sorted(section['halves'].items()):
            lines.append('| %s | %d | %s | %s |' % (
                half, stats['rows'], _cell(stats.get('reversal_rate')),
                _cell(stats.get('removal_precision'))))
        lines += ['| all | %d | %s | %s |' % (
            section['rows'], _cell(section.get('reversal_rate')),
            _cell(section.get('removal_precision'))), '']
        lines.append('%d reversal disagreements and %d truncated-post '
                     'disagreements are listed in the JSON report for '
                     'inspection.' % (len(section['reversal_disagreements']),
                                      len(section['truncated_disagreements'])))
        lines.append('')
    return '\n'.join(lines) + '\n'


# ---- accept ------------------------------------------------------------------------

def cmd_accept(report_path, acknowledgments_path, now=None):
    """Record the result against the trial -- after reproducing it.

    A report is a claim about its inputs. This re-hashes every input the
    report names, computes the verdict again from them, and refuses a
    report that does not reproduce. Then the acknowledgments: a human has
    looked at the disagreement lists, and says so against THIS report's
    hash. Then the timing: drawn on or after day three, drawn and labelled
    by day seven. Only then is the result persisted, as the primitive's
    own checks -- identity, deadline, first judgment, idempotency -- allow.
    """
    now = now or _utcnow()
    report = _read(report_path)
    schema = report.get('schema') if isinstance(report, dict) else None
    if schema != SCHEMA:
        raise AuditError('%s is not an audit report this build can accept '
                         '(schema %r)' % (report_path, schema))
    inputs = report.get('inputs') or {}
    for name in ('labels', 'encoder', 'haiku', 'sample', 'frame'):
        if name not in inputs:
            raise AuditError('the report names no %s input' % name)
    for name, entry in inputs.items():
        path = entry.get('path')
        if not path or not os.path.isfile(path):
            raise AuditError('the %s input the report was computed from is '
                             'gone: %s' % (name, path))
        if sha256_of(path) != entry.get('sha256'):
            raise AuditError('the %s input has changed since the report was '
                             'computed: %s' % (name, path))
    if report.get('complete') is not True:
        raise AuditError('the report is incomplete: %s'
                         % '; '.join(report.get('incomplete_reasons')
                                     or ['no completeness recorded']))

    acknowledgments = _read(acknowledgments_path)
    report_sha = sha256_of(report_path)
    if acknowledgments.get('report_sha256') != report_sha:
        raise AuditError('the acknowledgments are for report %s, this is %s'
                         % (str(acknowledgments.get('report_sha256'))[:12],
                            report_sha[:12]))
    inspected = set(acknowledgments.get('inspected') or [])
    lacking = [name for name in REQUIRED_INSPECTIONS if name not in inspected]
    if lacking:
        raise AuditError('not acknowledged as inspected: %s'
                         % ', '.join(lacking))
    if not str(acknowledgments.get('by') or '').strip():
        raise AuditError('the acknowledgments name nobody')

    out_dir = os.path.dirname(inputs['sample']['path'])
    assembled = _assemble(out_dir, inputs['labels']['path'],
                          inputs['encoder']['path'], inputs['haiku']['path'],
                          (inputs.get('supplemental_audit') or {}).get('path'),
                          (inputs.get('supplemental_natural') or {}).get('path'))
    fresh = trial_audit.evaluate_trial_audit(assembled['bundle'])
    reproduced = (
        fresh['passed'] == report.get('passed')
        and fresh['expansion_ready'] == report.get('expansion_ready')
        and fresh['coverage']['complete']
        == (report.get('coverage') or {}).get('complete')
        and [c['passed'] for c in fresh['criteria']]
        == [c.get('passed') for c in (report.get('criteria') or [])])
    if not reproduced or assembled['incomplete']:
        raise AuditError('the report does not reproduce from its inputs; it '
                         'is not accepted')

    first = assembled['first_judged_at']
    if first is None:
        raise AuditError('the trial has not judged anything')
    day3 = first + dt.timedelta(days=judge_trial.AUDIT_DRAW_DAY)
    day7 = first + dt.timedelta(days=judge_trial.AUDIT_LABEL_DAY)
    drawn_at = _when(assembled['sample']['drawn_at'], 'drawn_at')
    if not day3 <= drawn_at <= day7:
        raise AuditError('the sample was drawn at %s; it had to be drawn '
                         'between day %d (%s) and day %d (%s)'
                         % (drawn_at, judge_trial.AUDIT_DRAW_DAY, day3,
                            judge_trial.AUDIT_LABEL_DAY, day7))
    completed = assembled['labels']['completed_at']
    if completed is None:
        raise AuditError('the labels carry no completion time')
    if completed > day7:
        raise AuditError('labelling finished at %s, after day %d (%s)'
                         % (completed, judge_trial.AUDIT_LABEL_DAY, day7))

    with app.app_context():
        judge_trial.accept_audit(report, report_sha, now, passed=fresh['passed'])
    print('recorded: %s (report %s, acknowledged by %s)'
          % ('PASSED' if fresh['passed'] else 'FAILED', report_sha[:12],
             acknowledgments['by']))
    if not fresh['passed']:
        print('The trial is now recovering. Run '
              'scripts/rollback_encoder_judge.py --apply to drain it.')
    return 0


# ---- entry point -----------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    for name in ('sample', 'export-labels'):
        step = sub.add_parser(name)
        step.add_argument('--out', required=True)

    predict = sub.add_parser('predict')
    predict.add_argument('--out', required=True)
    predict.add_argument('--backend', required=True,
                         help="'encoder' or 'anthropic:<model>'")
    predict.add_argument('--artifact-dir', default=None)
    predict.add_argument('--confirm-spend', action='store_true',
                         help='authorise a PAID backend to be called')

    evaluate = sub.add_parser('evaluate')
    evaluate.add_argument('--out', required=True)
    evaluate.add_argument('--labels', required=True)
    evaluate.add_argument('--encoder-predictions', required=True)
    evaluate.add_argument('--haiku-predictions', required=True)
    evaluate.add_argument('--supplemental-audit', default=None,
                          help='the original 200-row audit, both halves, '
                               'as {key, half, truncated, reference, '
                               'prediction} JSONL')
    evaluate.add_argument('--supplemental-natural', default=None,
                          help='the locked natural set, same format')

    accept = sub.add_parser('accept')
    accept.add_argument('--report', required=True)
    accept.add_argument('--acknowledgments', required=True,
                        help='{report_sha256, inspected: [...], by, at}')

    args = parser.parse_args(argv)
    try:
        if args.command == 'sample':
            return cmd_sample(args.out)
        if args.command == 'export-labels':
            return cmd_export_labels(args.out)
        if args.command == 'predict':
            return cmd_predict(args.out, args.backend,
                               artifact_dir=args.artifact_dir,
                               confirm_spend=args.confirm_spend)
        if args.command == 'evaluate':
            return cmd_evaluate(args.out, args.labels,
                                args.encoder_predictions,
                                args.haiku_predictions,
                                args.supplemental_audit,
                                args.supplemental_natural)
        return cmd_accept(args.report, args.acknowledgments)
    except (judge_trial.TrialError, AuditError) as refused:
        print('refused: %s' % refused, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
