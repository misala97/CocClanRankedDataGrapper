"""MD-SELECTED-PRICE-CORRECTION-1, failing-first reproduction of F1/F2 on the
ORIGINAL multiprocessing spawn launcher, run BEFORE the correction.

    cd personal_apps
    py -3.12 ../radar-design/artifacts/md-selected-price-correction-1/failing_first_spawn_probe.py

This file is itself a FILE-PATH __main__ with unguarded top-level code (the
shape of app.py): it imports flask at top level and records, per process that
executes it, the pid, __name__, whether flask is loaded and the dummy sentinel.
The spawn child runs the production fetch_child with a bad spec, so there is
no network. Writes failing_first_spawn.json beside this file. After the
correction `spawn_launcher` no longer exists and this probe refuses to run.
"""
import json
import os
import sys
import time
from pathlib import Path

import flask  # noqa: F401 -- stands in for app.py's top-level application imports

HERE = Path(__file__).resolve().parent
PERSONAL_APPS = HERE.parents[2] / 'personal_apps'
MARKER = HERE / 'failing_first_marker.jsonl'
if str(PERSONAL_APPS) not in sys.path:
    sys.path.insert(0, str(PERSONAL_APPS))

with open(MARKER, 'a', encoding='utf-8') as _fh:
    _fh.write(json.dumps({'pid': os.getpid(), 'name': __name__, 'flask_loaded': 'flask' in sys.modules,
                          'sentinel': os.environ.get('RADAR_SP_DUMMY_SECRET')}) + '\n')


if __name__ == '__main__':
    from features.radar import price_chart_acquisition as acq
    if not hasattr(acq, 'spawn_launcher'):
        sys.exit('spawn_launcher is gone: this probe only reproduces the pre-correction launcher')
    MARKER.write_text('', encoding='utf-8')
    os.environ['RADAR_SP_DUMMY_SECRET'] = 'dummy-sentinel-not-a-real-secret'
    started = time.monotonic()
    child = acq.spawn_launcher()({'version': 1, 'symbol': 'http://elsewhere/'})
    outcome, data = acq.collect(child, time.monotonic, started + acq.DEADLINE_S)
    confirmed = acq.reap(child, clock=time.monotonic)
    lines = [json.loads(line) for line in MARKER.read_text(encoding='utf-8').splitlines() if line]
    child_lines = [line for line in lines if line['pid'] == child.process.pid]
    out = {
        'python': sys.version.split()[0],
        'parent_pid': os.getpid(),
        'child_pid': child.process.pid,
        'outcome': outcome, 'result': json.loads(data) if data else None, 'reaped': confirmed,
        'seconds': round(time.monotonic() - started, 3),
        'child_marker_lines': child_lines,
        'child_re_executed_parent_script': any(line['name'] == '__mp_main__' for line in child_lines),
        'child_imported_flask_via_parent_script': any(line['flask_loaded'] for line in child_lines),
        'child_saw_dummy_sentinel': any(line['sentinel'] for line in child_lines),
    }
    MARKER.unlink(missing_ok=True)
    (HERE / 'failing_first_spawn.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps(out, indent=1))
