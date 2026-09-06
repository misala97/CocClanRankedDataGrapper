#!/usr/bin/env python
"""Undo the encoder trial's decisions. Reports by default; applies on demand.

Switching the backend off stops NEW judgments and changes nothing about the
ones already made: every mention the encoder removed is still missing from
its bucket counts and from distinct-voice reads. This is the other half --
it returns those mentions to the unjudged state that counts provisionally,
puts their journal eligibility back, and rebuilds the affected windows from
the complete retained journal.

    python -m scripts.rollback_encoder_judge                  # report only
    python -m scripts.rollback_encoder_judge --apply          # up to 2000
    python -m scripts.rollback_encoder_judge --apply --limit 500

A dry run is the DEFAULT, and it writes nothing at all -- not the mentions,
not the buckets, not the trial's own status. `--apply` durably requests the
stop first, then drains a bounded number of mentions in whole-window
transactions; run it again to continue. The trial is marked recovered only
after a fresh count finds nothing left, because that is what releases the
retention pin holding the evidence.

Tone is never cleared. The trial did not write it, and what is there
belongs to whoever did.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from features.radar import judge_trial  # noqa: E402


def run(apply=False, limit=2000):
    try:
        return _run(apply=apply, limit=limit)
    except judge_trial.TrialError as refused:
        # An operator reading this is usually mid-incident. A traceback is
        # the wrong thing to hand them.
        print('cannot recover: %s' % refused, file=sys.stderr)
        return 1


def _run(apply=False, limit=2000):
    with app.app_context():
        if apply:
            # Durable first. If this run dies halfway, the trial must
            # already be stopped -- otherwise the daemon keeps judging
            # while recovery is undoing, and the two race forever.
            state = judge_trial.current()
            if state is not None and state.status not in (
                    judge_trial.RECOVERING, judge_trial.RECOVERED):
                judge_trial.request_stop('recovery run')

        report = judge_trial.recover_trial(apply=apply, limit=limit)

    print('encoder-judged mentions outstanding: %d in %d window(s)'
          % (report['total_mentions'], report['total_windows']))
    print('this run covers:                     %d in %d window(s)%s'
          % (report['selected_mentions'], report['selected_windows'],
             '' if report['selected_mentions'] == report['total_mentions']
             else ' (capped by --limit)'))
    if not apply:
        print('\ndry run -- nothing was written. Pass --apply to recover.')
        return 0
    print('recovered this run:                  %d' % report['recovered'])
    print('still outstanding:                   %d' % report['remaining'])
    if report['remaining']:
        print('\nRun again to continue. The retention pin stays until the '
              'last one is recovered.')
    else:
        print('\nAll recovered. The retention pin is released.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='actually recover (default: report only)')
    parser.add_argument('--dry-run', action='store_true',
                        help='the default; refuses to be combined with '
                             '--apply so an ambiguous command cannot write')
    parser.add_argument('--limit', type=int, default=2000,
                        help='maximum mentions to recover in this run')
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error('--apply and --dry-run contradict each other; say which')
    if args.limit <= 0:
        parser.error('--limit must be a positive number of mentions')
    return run(apply=args.apply, limit=args.limit)


if __name__ == '__main__':
    raise SystemExit(main())
