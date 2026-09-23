"""MD-SELECTED-PRICE-REVIEW-1, D17 probe (reviewer-owned evidence).

Question: does the production spawn launcher re-execute the launching
script's unguarded top level inside every fetch child, and does the child
inherit the parent's environment? No network (the production child refuses a
bad spec before any transport exists), no database, no application import.

    cd personal_apps
    py -3.12 ../radar-design/artifacts/md-selected-price-review-1/d17_spawn_main_probe.py

Mode `file` models `python app.py` / `py scratchpad/b1c/serve_b1c.py` (a
__main__ with a file path and unguarded top-level code). Mode `-c` models
`python -c "from app import app; app.run(...)"` (a __main__ with no file).
Writes d17_probe.json beside this file.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PERSONAL_APPS = HERE.parents[2] / 'personal_apps'
MARKER = HERE / 'd17_marker.tsv'
if str(PERSONAL_APPS) not in sys.path:
    sys.path.insert(0, str(PERSONAL_APPS))

# Unguarded top level, the shape app.py (lines 1-185) and serve_b1c.py (line 5)
# have. Every process that executes this file appends one line.
with open(MARKER, 'a', encoding='utf-8') as _fh:
    _fh.write(f"{os.getpid()}\t{__name__}\t{os.environ.get('SP_REVIEW_SENTINEL')}\n")


def spawn_bad_spec():
    from features.radar import price_chart_acquisition as acq
    started = time.monotonic()
    child = acq.spawn_launcher()({'version': 1, 'symbol': 'http://elsewhere/'})
    outcome, data = acq.collect(child, time.monotonic, started + acq.DEADLINE_S)
    confirmed = acq.reap(child, clock=time.monotonic)
    return {'outcome': outcome, 'result': json.loads(data) if data else None,
            'confirmed': confirmed, 'exitcode': child.process.exitcode,
            'child_pid': child.process.pid, 'seconds': round(time.monotonic() - started, 3)}


DASH_C = r'''
import json, os, sys, time
sys.path.insert(0, os.getcwd())
marker = sys.argv[1]
with open(marker, 'a', encoding='utf-8') as fh:
    fh.write(f"{os.getpid()}\t-c parent\t{os.environ.get('SP_REVIEW_SENTINEL')}\n")
from features.radar import price_chart_acquisition as acq
started = time.monotonic()
child = acq.spawn_launcher()({'version': 1, 'symbol': 'http://elsewhere/'})
outcome, data = acq.collect(child, time.monotonic, started + acq.DEADLINE_S)
confirmed = acq.reap(child, clock=time.monotonic)
print(json.dumps({'outcome': outcome, 'result': json.loads(data) if data else None,
                  'confirmed': confirmed, 'exitcode': child.process.exitcode,
                  'child_pid': child.process.pid}))
'''


def read_marker():
    if not MARKER.exists():
        return []
    return [dict(zip(('pid', 'name', 'sentinel'), line.split('\t')))
            for line in MARKER.read_text(encoding='utf-8').splitlines()]


if __name__ == '__main__':
    out = {'python': sys.version.split()[0], 'executable': sys.executable}
    # Mode file: this script is __main__ with a path.
    MARKER.write_text('', encoding='utf-8')
    with open(MARKER, 'a', encoding='utf-8') as fh:
        fh.write(f"{os.getpid()}\t__main__ (after reset)\t{os.environ.get('SP_REVIEW_SENTINEL')}\n")
    os.environ['SP_REVIEW_SENTINEL'] = 'set-in-parent-before-spawn'
    child = spawn_bad_spec()
    lines = read_marker()
    out['file_mode'] = {
        'child': child,
        'marker_lines': lines,
        'child_executed_script_top_level': any(l['pid'] == str(child['child_pid'])
                                               and l['name'] == '__mp_main__' for l in lines),
        'child_saw_parent_env_sentinel': any(l['pid'] == str(child['child_pid'])
                                             and l['sentinel'] == 'set-in-parent-before-spawn'
                                             for l in lines),
    }
    # Mode -c: a separate interpreter whose __main__ has no file.
    MARKER.write_text('', encoding='utf-8')
    proc = subprocess.run([sys.executable, '-c', DASH_C, str(MARKER)], cwd=str(PERSONAL_APPS),
                          capture_output=True, text=True, timeout=60, env=dict(os.environ))
    lines = read_marker()
    try:
        child = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        child = {'stdout': proc.stdout[-2000:], 'stderr': proc.stderr[-2000:]}
    out['dash_c_mode'] = {
        'returncode': proc.returncode, 'child': child, 'marker_lines': lines,
        'child_executed_any_top_level': any(l['pid'] == str(child.get('child_pid')) for l in lines),
    }
    MARKER.unlink(missing_ok=True)
    (HERE / 'd17_probe.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps(out, indent=1))
