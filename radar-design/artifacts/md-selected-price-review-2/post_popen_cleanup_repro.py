"""MD-SELECTED-PRICE-REVIEW-2 (reviewer-owned): does an UNCONFIRMED cleanup after
a post-Popen launcher exception quarantine acquisition?

    py -3.12 radar-design/artifacts/md-selected-price-review-2/post_popen_cleanup_repro.py

Safe fakes only: subprocess.Popen is replaced by an in-memory process that
ignores kill/terminate and whose wait() always times out; no real process,
network, database or provider. Two runs through the REAL Coordinator and the
REAL subprocess_launcher():
- post_popen: the reader thread cannot start (Child.__init__ raises), so the
  launcher's own except -> _kill_now path runs.
- control: the reader starts, the child never answers, and cleanup happens in
  Child.reap via the supervisor.
Also re-hashes the 50 manifest files with independent code.
Writes post_popen_cleanup_repro.json beside this file.
"""
import hashlib
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


class Unkillable:
    instances = []

    def __init__(self, args, **kwargs):
        self.args = args
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(b'')      # control run: reader sees EOF at once
        self.pid = 90000 + len(Unkillable.instances)
        self.kill_calls = self.terminate_calls = 0
        Unkillable.instances.append(self)

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(self.args, timeout)

    def poll(self):
        return None                       # never exits

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1


class ReaderCannotStart(REAL_THREAD):
    def start(self):
        if self.name == 'radar-price-chart-reader':
            raise RuntimeError("can't start new thread")
        super().start()


def wait_idle(coordinator, limit=10.0):
    ends = time.monotonic() + limit
    while coordinator.snapshot()['in_flight'] and time.monotonic() < ends:
        time.sleep(0.02)


def scenario(name, reader_fails):
    Unkillable.instances.clear()
    acq.subprocess.Popen = Unkillable
    acq.threading.Thread = ReaderCannotStart if reader_fails else REAL_THREAD
    try:
        coordinator = acq.Coordinator(deadline_s=0.3, cleanup_s=0.2)
        first = coordinator.get_or_start(identity(), WINDOW, now=NOW)
        wait_idle(coordinator)
        after_first = coordinator.snapshot()
        second = coordinator.get_or_start(identity(instrument_id=8), WINDOW, now=NOW)
        wait_idle(coordinator)
        return {
            'scenario': name,
            'first_state': first['state'],
            'snapshot_after_first': {k: after_first[k] for k in ('quarantined', 'in_flight')}
            | {'counters': {k: v for k, v in after_first['counters'].items() if v}},
            'first_process': {'kill_calls': Unkillable.instances[0].kill_calls,
                              'terminate_calls': Unkillable.instances[0].terminate_calls,
                              'still_running_per_poll': Unkillable.instances[0].poll() is None},
            'second_chart_state': second['state'],
            'second_chart_reason': second['reason'],
            'processes_started': len(Unkillable.instances),
        }
    finally:
        acq.subprocess.Popen = REAL_POPEN
        acq.threading.Thread = REAL_THREAD


def rehash():
    manifest = json.loads((ROOT / 'radar-design/artifacts/md-selected-price-correction-1/fingerprint-final.json')
                          .read_text(encoding='utf-8'))
    mismatches = []
    lines = []
    for path, info in sorted(manifest['files'].items()):
        data = (ROOT / path).read_bytes()
        if 'sha256_lf' in info:
            digest = hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()
            expected = info['sha256_lf']
        else:
            digest = hashlib.sha256(data).hexdigest()
            expected = info['sha256']
        lines.append(f'{path}\t{digest}\n')
        if digest != expected:
            mismatches.append(path)
    return {'files': len(manifest['files']), 'mismatches': mismatches,
            'digest': hashlib.sha256(''.join(lines).encode()).hexdigest(),
            'recorded_digest': manifest['digest']}


if __name__ == '__main__':
    out = {'post_popen': scenario('post_popen_reader_start_failure', True),
           'control': scenario('control_reap_unconfirmed', False),
           'independent_rehash': rehash()}
    (HERE / 'post_popen_cleanup_repro.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps(out, indent=1))
