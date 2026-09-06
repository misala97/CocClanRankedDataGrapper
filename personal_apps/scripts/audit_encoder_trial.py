#!/usr/bin/env python
"""Draw, label, evaluate and record the trial's fresh audit.

The existing 200-row audit cannot answer the question this one has to: half
of it was chosen BECAUSE the encoder wanted to delete those rows, so it
cannot estimate removal precision on production traffic, and more enriched
rows cannot fix that. This draws a fresh, uniformly sampled set instead.

    python -m scripts.audit_encoder_trial sample   --out DIR
    python -m scripts.audit_encoder_trial export-labels --out DIR
    python -m scripts.audit_encoder_trial evaluate --out DIR \
        --encoder-predictions FILE --haiku-predictions FILE --labels FILE
    python -m scripts.audit_encoder_trial accept   --report FILE

Two things this deliberately will NOT do.

It does not call a paid model. Producing the two prediction files is a
separate, explicitly authorised step documented in the deployment runbook,
because an evaluation command that quietly spends money is one somebody
runs twice.

It does not write judgments. Predictions are scored offline: nothing here
goes through apply_judgments, so an audit can never move a mention, a
bucket or the spend meter.
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
from features.radar import judge_trial, trial_audit  # noqa: E402
from models import RadarMention, RadarPost  # noqa: E402

FRAME = 'frame.json'
SAMPLE = 'sample.json'
BLIND = 'blind.jsonl'
REPORT_JSON = 'report.json'
REPORT_MD = 'report.md'


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path, payload):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=1, sort_keys=True, default=str)
    return path


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def cmd_sample(out_dir):
    """Freeze the frame, then draw from it with the seed fixed at arming.

    The frame is EVERY retained high-confidence mention in the first three
    days of the trial, across all sources and tickers, with no gate,
    removal or confidence enrichment. Enriching it is what made the last
    audit unable to answer the question.
    """
    os.makedirs(out_dir, exist_ok=True)
    with app.app_context():
        row = judge_trial.current()
        if row is None:
            raise SystemExit('no trial is armed')
        if row.first_judged_at is None:
            raise SystemExit('the trial has not judged anything yet; the '
                             'frame is defined from its first judgment')
        start = row.first_judged_at
        end = start + dt.timedelta(days=judge_trial.AUDIT_DRAW_DAY)
        ids = [int(i) for (i,) in db.session.query(RadarMention.id)
               .join(RadarPost, RadarPost.id == RadarMention.post_id)
               .filter(RadarMention.confidence == 'high',
                       RadarPost.created_utc >= start,
                       RadarPost.created_utc < end)
               .order_by(RadarMention.id).all()]
        recipe = row.recipe or {}
        wanted = int(recipe.get('sample_size') or 0)
        seed = recipe.get('seed')

    frame_path = _write(os.path.join(out_dir, FRAME),
                        {'first_judged_at': start, 'until': end,
                         'mention_ids': ids, 'size': len(ids)})
    if len(ids) < wanted:
        raise SystemExit(
            'the frame holds %d mentions and the recipe needs %d. Too little '
            'traffic is a FAILED audit, not permission to shrink the sample '
            'or widen the frame.' % (len(ids), wanted))

    drawn = sorted(random.Random(seed).sample(ids, wanted))
    _write(os.path.join(out_dir, SAMPLE),
           {'seed': seed, 'sample_size': wanted, 'mention_ids': drawn,
            'frame_sha256': sha256_of(frame_path),
            'drawn_at': dt.datetime.utcnow()})
    print('frame %d mentions -> sampled %d with seed %s'
          % (len(ids), wanted, seed))
    return 0


def cmd_export_labels(out_dir):
    """The blind file a human labels: text and ticker, no predictions.

    Neither backend's answer appears here. A labeller who can see what the
    model said is not producing an independent reference, and this audit
    exists precisely because the last reference was not independent enough.
    """
    sample = _read(os.path.join(out_dir, SAMPLE))
    with app.app_context():
        rows = (db.session.query(RadarMention, RadarPost)
                .join(RadarPost, RadarPost.id == RadarMention.post_id)
                .filter(RadarMention.id.in_(sample['mention_ids'])).all())
        written = 0
        with open(os.path.join(out_dir, BLIND), 'w', encoding='utf-8') as out:
            for mention, post in rows:
                out.write(json.dumps({
                    'mention_id': mention.id, 'ticker': mention.ticker,
                    'source': post.source, 'channel': post.channel,
                    'author': post.author, 'title': post.title,
                    'body': post.body}) + '\n')
                written += 1
    if written != len(sample['mention_ids']):
        raise SystemExit('%d of %d sampled mentions are no longer retained; '
                         'a shrunken denominator is a failed audit'
                         % (written, len(sample['mention_ids'])))
    print('wrote %d blind rows' % written)
    return 0


def _verdicts(path):
    """{mention_id: verdict} from a JSONL file of labels or predictions."""
    got = {}
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            got[int(row['mention_id'])] = row
    return got


def cmd_evaluate(out_dir, labels, encoder, haiku, shadow_days):
    """Score the two prediction sets against the reference. Pure and offline."""
    bundle = {'reference': _verdicts(labels),
              'encoder': _verdicts(encoder),
              'haiku': _verdicts(haiku),
              'shadow_days': shadow_days}
    with app.app_context():
        row = judge_trial.current()
        trial = {'artifact_sha256': row.artifact_sha256 if row else None,
                 'prompt_version': row.prompt_version if row else None,
                 'model_id': row.model_id if row else None}
    report = trial_audit.evaluate_trial_audit(bundle)
    report['trial'] = trial
    report['inputs'] = {'labels': sha256_of(labels),
                        'encoder': sha256_of(encoder),
                        'haiku': sha256_of(haiku)}
    report['evaluated_at'] = dt.datetime.utcnow()

    path = _write(os.path.join(out_dir, REPORT_JSON), report)
    with open(os.path.join(out_dir, REPORT_MD), 'w', encoding='utf-8') as out:
        out.write(_markdown(report))
    print('%s -- %s' % ('PASSED' if report['passed'] else 'FAILED', path))
    for criterion in report['criteria']:
        print('  %-26s %s' % (criterion['criterion'],
                              'pass' if criterion['passed'] else 'FAIL'))
    print('  tone qualification         %s (never gates the trial)'
          % ('qualified' if report['tone']['qualified'] else 'not qualified'))
    return 0


def _markdown(report):
    lines = ['# Encoder trial audit', '',
             '**Result: %s**' % ('PASSED' if report['passed'] else 'FAILED'),
             '', 'Sample size: %d' % report['sample_size'], '',
             '| criterion | encoder | incumbent | threshold | verdict |',
             '|---|---|---|---|---|']
    for criterion in report['criteria']:
        encoder = criterion.get('encoder') or {}
        incumbent = criterion.get('incumbent') or {}
        lines.append('| %s | %s | %s | %s | %s |' % (
            criterion['criterion'],
            _cell(encoder), _cell(incumbent),
            ('%.4f' % criterion['threshold']) if 'threshold' in criterion
            else '--',
            'pass' if criterion['passed'] else '**FAIL**'))
    lines += ['', '## Tone', '',
              'Reported, never gating: encoder tone is not written during '
              'the trial, so it cannot pass or fail it.', '',
              '| criterion | verdict |', '|---|---|']
    for criterion in report['tone']['criteria']:
        lines.append('| %s | %s |' % (criterion['criterion'],
                                      'pass' if criterion['passed'] else 'FAIL'))
    lines += ['', 'Tone qualification: **%s**'
              % ('qualified' if report['tone']['qualified']
                 else 'not qualified'),
              '', 'Qualifying authorises nothing on its own. Enabling '
              'encoder tone is a separate, separately reviewed change.', '']
    return '\n'.join(lines)


def _cell(interval):
    if not interval:
        return '--'
    return '%.4f (%d/%d, CI %.4f-%.4f)' % (
        interval['point'], interval['successes'], interval['total'],
        interval['lower'], interval['upper'])


def cmd_accept(report_path):
    """Record the result against the trial. The only command that writes."""
    report = _read(report_path)
    with app.app_context():
        judge_trial.accept_audit(report, sha256_of(report_path),
                                 dt.datetime.utcnow(),
                                 passed=bool(report.get('passed')))
    print('recorded: %s' % ('PASSED' if report.get('passed') else 'FAILED'))
    if not report.get('passed'):
        print('The trial is now recovering. Run '
              'scripts/rollback_encoder_judge.py --apply to drain it.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    for name in ('sample', 'export-labels'):
        step = sub.add_parser(name)
        step.add_argument('--out', required=True)

    evaluate = sub.add_parser('evaluate')
    evaluate.add_argument('--out', required=True)
    evaluate.add_argument('--labels', required=True)
    evaluate.add_argument('--encoder-predictions', required=True)
    evaluate.add_argument('--haiku-predictions', required=True)
    evaluate.add_argument('--shadow-days', type=float, default=0)

    accept = sub.add_parser('accept')
    accept.add_argument('--report', required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == 'sample':
            return cmd_sample(args.out)
        if args.command == 'export-labels':
            return cmd_export_labels(args.out)
        if args.command == 'evaluate':
            return cmd_evaluate(args.out, args.labels,
                                args.encoder_predictions,
                                args.haiku_predictions, args.shadow_days)
        return cmd_accept(args.report)
    except (judge_trial.TrialError, trial_audit.AuditError) as refused:
        print('refused: %s' % refused, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
