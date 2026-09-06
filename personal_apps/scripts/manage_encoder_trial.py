#!/usr/bin/env python
"""Arm, inspect and stop the encoder trial.

Three commands in this task; `tick` (automatic expiry enforcement) arrives
with the watchdog. None of them constructs a judge or opens an artifact --
this talks to the trial record and nothing else, so it works when the model
does not.

    python -m scripts.manage_encoder_trial status
    python -m scripts.manage_encoder_trial arm --artifact-sha256 <64 hex> \
        --baseline-report <path> --baseline-removal-rate 0.31 --seed 20260906
    python -m scripts.manage_encoder_trial stop --reason "removal share -60%"

`arm` is the preflight gate. Everything the later evaluation is not allowed
to choose for itself is fixed here -- the artifact bundle hash, the baseline
it will be compared against, the removal rate that fixes the sample size,
and the sampling seed -- because choosing them after seeing predictions is
how a trial passes itself. If those inputs cannot be supplied, that is a
reason not to arm, not a reason to invent them.
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from features.radar import judge_trial  # noqa: E402


def cmd_status():
    with app.app_context():
        state = judge_trial.trial_status()
    if state is None:
        print('no trial record: nothing armed, nothing pinned')
        return 0
    print('status            %s' % state['status'])
    print('model / prompt    %s / %s' % (state['model_id'],
                                         state['prompt_version']))
    print('artifact sha256   %s' % state['artifact_sha256'])
    print('armed at          %s' % state['armed_at'])
    print('evidence pinned   from %s' % state['retain_from'])
    print('first judged at   %s' % (state['first_judged_at'] or '-- not yet'))
    print('audit             %s' % _audit_line(state))
    if state['stop_reason']:
        print('stop reason       %s' % state['stop_reason'])
    recipe = state['recipe'] or {}
    print('sample size       %s (removal rate %s, seed %s)'
          % (recipe.get('sample_size'), recipe.get('baseline_removal_rate'),
             recipe.get('seed')))
    print('baseline report   %s' % recipe.get('baseline_report'))
    return 0


def _audit_line(state):
    if state['audit_evaluated_at'] is None:
        return 'not evaluated'
    return '%s at %s (report %s)' % (
        'PASSED' if state['audit_passed'] else 'FAILED',
        state['audit_evaluated_at'],
        (state['audit_report_sha256'] or '')[:12])


def cmd_arm(args):
    baseline = args.baseline_report
    if not os.path.isfile(baseline):
        print('no baseline report at %s -- arming needs the actual report '
              'it will be compared against' % baseline, file=sys.stderr)
        return 2
    with app.app_context():
        row = judge_trial.arm_trial(
            dt.datetime.utcnow(),
            artifact_sha256=args.artifact_sha256.strip().lower(),
            baseline_report=os.path.abspath(baseline),
            baseline_removal_rate=args.baseline_removal_rate,
            seed=args.seed)
        print('armed. evidence pinned from %s; sample size %d'
              % (row.retain_from, row.recipe['sample_size']))
    return 0


def cmd_stop(args):
    with app.app_context():
        row = judge_trial.request_stop(args.reason)
    print('trial status is now %s. This stops NEW judgments; the decisions '
          'already made are still in the counts until recovery runs.'
          % row.status)
    return 0


def cmd_tick(args):
    """Enforce the deadline. Reads the row; constructs no judge.

    Run by its own timer every minute, deliberately not by the ingest
    daemon: the thing most likely to need stopping IS the daemon.
    """
    with app.app_context():
        report = judge_trial.tick(dt.datetime.utcnow(), limit=args.limit)
    action = report.get('action', 'none')
    if action == 'none':
        return 0
    print('%s: recovered %d, %d remaining'
          % (action, report.get('recovered', 0), report.get('remaining', 0)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('status', help='read the trial record (writes nothing)')

    arm = sub.add_parser('arm', help='create the trial record, once')
    arm.add_argument('--artifact-sha256', required=True,
                     help='SHA256 of the three-file artifact bundle')
    arm.add_argument('--baseline-report', required=True,
                     help='path to the incumbent baseline report')
    arm.add_argument('--baseline-removal-rate', required=True, type=float,
                     help='measured removal share, in (0, 1]; fixes the '
                          'audit sample size')
    arm.add_argument('--seed', required=True, type=int,
                     help='sampling seed, fixed before any prediction')

    stop = sub.add_parser('stop', help='durably request recovery')
    stop.add_argument('--reason', required=True,
                      help='why; it becomes the record')

    tick = sub.add_parser('tick', help='enforce the deadline (the watchdog)')
    tick.add_argument('--limit', type=int, default=2000,
                      help='maximum mentions to recover in one tick')

    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except judge_trial.TrialError as refused:
        print('refused: %s' % refused, file=sys.stderr)
        return 1


def _dispatch(args):
    if args.command == 'status':
        return cmd_status()
    if args.command == 'arm':
        return cmd_arm(args)
    if args.command == 'tick':
        return cmd_tick(args)
    return cmd_stop(args)


if __name__ == '__main__':
    raise SystemExit(main())
