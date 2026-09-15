"""MD-SELECTED-PRICE-CORRECTION-2: R2-1 check, adapted from the immutable
../md-selected-price-review-2/post_popen_cleanup_repro.py (left unchanged).

    py -3.12 radar-design/artifacts/md-selected-price-correction-2/post_popen_cleanup_check.py [label]

Safe fakes only: subprocess.Popen is replaced by in-memory processes; no real
child, network, database or provider. Every scenario goes through the REAL
Coordinator and the REAL subprocess_launcher(), then asks for a second,
different chart. Each scenario states what the ruling requires and whether the
code under test met it. Writes post_popen_cleanup_check-<label>.json here.

- post_popen_unconfirmed: reader thread cannot start AFTER Popen; the process
  ignores kill and wait() always times out. Required: quarantined,
  cleanup_failed 1, second chart unavailable, exactly one Popen.
- post_popen_confirmed: reader thread cannot start; kill ends the process and
  wait() returns. Required: NOT quarantined, invalid 1, second chart pending.
- post_popen_kill_raises_but_exited: reader cannot start; kill() raises
  OSError (already gone) but wait() returns an exit code -- process evidence
  confirms exit. Required: NOT quarantined.
- pre_popen_failure: Popen itself raises FileNotFoundError (no process).
  Required: NOT quarantined, invalid 1, second chart pending.
- control_reap_unconfirmed: reader starts, child never answers, Child.reap
  cannot confirm. Required (unchanged behaviour): quarantined, second unavailable.
"""
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'personal_apps'))

from features.radar import price_chart_acquisition as acq  # noqa: E402
from features.radar import price_chart_contract as c  # noqa: E402
from tests.selected_price_unit.helpers import identity, utc  # noqa: E402

NOW = utc(2026, 9, 15, 14, 7)
WINDOW = c.window_for('1W', NOW)
REAL_POPEN = subprocess.Popen
REAL_THREAD = threading.Thread
CALLS = []


class FakeProcess:
    def __init__(self, args, *, dies_on_kill=True, kill_raises=False, **kwargs):
        self.args = args
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(b'')
        self.pid = 90000 + len(CALLS)
        self.returncode = None
        self.dies_on_kill = dies_on_kill
        self.kill_raises = kill_raises
        self.kill_calls = self.terminate_calls = 0

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1
        if self.kill_raises:
            self.returncode = 1                 # it had already exited
            raise ProcessLookupError(3, 'No such process')
        if self.dies_on_kill:
            self.returncode = -9


def popen_factory(**behaviour):
    def make(args, **kwargs):
        process = FakeProcess(args, **behaviour)
        CALLS.append(process)
        return process
    return make


def refusing_popen(args, **kwargs):
    CALLS.append(None)
    raise FileNotFoundError(2, 'interpreter not found')


class ReaderCannotStart(REAL_THREAD):
    def start(self):
        if self.name == 'radar-price-chart-reader':
            raise RuntimeError("can't start new thread")
        super().start()


def wait_idle(coordinator, limit=10.0):
    ends = time.monotonic() + limit
    while coordinator.snapshot()['in_flight'] and time.monotonic() < ends:
        time.sleep(0.02)


def run(name, popen, reader_fails, required):
    CALLS.clear()
    acq.subprocess.Popen = popen
    acq.threading.Thread = ReaderCannotStart if reader_fails else REAL_THREAD
    try:
        coordinator = acq.Coordinator(deadline_s=0.3, cleanup_s=0.2)
        first = coordinator.get_or_start(identity(), WINDOW, now=NOW)
        wait_idle(coordinator)
        snap = coordinator.snapshot()
        second = coordinator.get_or_start(identity(instrument_id=8), WINDOW, now=NOW)
        wait_idle(coordinator)
        observed = {
            'first_state': first['state'],
            'quarantined': snap['quarantined'],
            'counters': {k: v for k, v in snap['counters'].items() if v},
            'second_state': second['state'],
            'second_reason': second['reason'],
            'popen_calls': len(CALLS),
            'first_process': (None if not CALLS or CALLS[0] is None else
                              {'kill_calls': CALLS[0].kill_calls, 'terminate_calls': CALLS[0].terminate_calls,
                               'exit_confirmed_by_process': CALLS[0].returncode is not None}),
        }
    finally:
        acq.subprocess.Popen = REAL_POPEN
        acq.threading.Thread = REAL_THREAD
    unmet = {k: {'required': v, 'observed': observed.get(k) if k != 'cleanup_failed'
                 else observed['counters'].get('cleanup_failed', 0)}
             for k, v in required.items()
             if (observed['counters'].get('cleanup_failed', 0) if k == 'cleanup_failed' else observed.get(k)) != v}
    return {'scenario': name, 'required': required, 'observed': observed, 'met': not unmet, 'unmet': unmet}


SCENARIOS = [
    ('post_popen_unconfirmed', dict(dies_on_kill=False), True,
     {'quarantined': True, 'cleanup_failed': 1, 'second_state': 'unavailable', 'popen_calls': 1}),
    ('post_popen_confirmed', dict(dies_on_kill=True), True,
     {'quarantined': False, 'cleanup_failed': 0, 'second_state': 'pending', 'popen_calls': 2}),
    ('post_popen_kill_raises_but_exited', dict(kill_raises=True), True,
     {'quarantined': False, 'cleanup_failed': 0, 'second_state': 'pending', 'popen_calls': 2}),
    ('pre_popen_failure', None, False,
     {'quarantined': False, 'cleanup_failed': 0, 'second_state': 'pending', 'popen_calls': 2}),
    ('control_reap_unconfirmed', dict(dies_on_kill=False), False,
     {'quarantined': True, 'cleanup_failed': 1, 'second_state': 'unavailable', 'popen_calls': 1}),
]


if __name__ == '__main__':
    label = sys.argv[1] if len(sys.argv) > 1 else 'run'
    results = [run(name, refusing_popen if behaviour is None else popen_factory(**behaviour), reader_fails, required)
               for name, behaviour, reader_fails, required in SCENARIOS]
    out = {'label': label, 'all_met': all(r['met'] for r in results), 'scenarios': results}
    (HERE / f'post_popen_cleanup_check-{label}.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps({'label': label, 'all_met': out['all_met'],
                      'scenarios': {r['scenario']: (r['met'], r['unmet']) for r in results}}, indent=1))
