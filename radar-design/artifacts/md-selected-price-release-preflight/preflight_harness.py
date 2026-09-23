"""MD-SELECTED-PRICE-RELEASE-PREFLIGHT: Linux/venv subprocess harness.
Runs in a NON-SERVED scratch copy of the accepted package files, with the
production venv interpreter. Synthetic children only; no provider, no DB."""
import datetime as dt, hashlib, http.server, json, os, subprocess, sys, threading, time
from pathlib import Path
HERE = Path(__file__).resolve().parent            # scratch/personal_apps
os.chdir(HERE); sys.path.insert(0, str(HERE))
from features.radar import price_chart_acquisition as acq, price_chart_contract as c
OUT = {'recorded_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'host': os.uname().nodename,
       'parent': {'python': sys.version, 'sys_executable': sys.executable, 'sys_prefix': sys.prefix,
                  'base_prefix': sys.base_prefix, 'platform': sys.platform, 'pid': os.getpid(),
                  'app_root': str(acq.APP_ROOT), 'child_env_allowlist_posix': list(acq.CHILD_ENV_ALLOWLIST['posix']),
                  'child_environment': acq.child_environment(), 'interpreter_flags': list(acq.INTERPRETER_FLAGS)}}
# 0. copied-file hashes (LF normalized) vs accepted manifest
manifest = json.loads((HERE / 'fingerprint-final.json').read_text())['files']
hashes = {}
for rel in sorted(manifest):
    local = HERE.parent / rel
    if local.is_file() and 'sha256_lf' in manifest[rel]:
        h = hashlib.sha256(local.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        hashes[rel] = {'sha256_lf': h, 'matches_accepted': h == manifest[rel]['sha256_lf']}
OUT['copied_file_hashes'] = hashes
OUT['copied_all_match'] = all(v['matches_accepted'] for v in hashes.values())
# 1. minimal-environment import of the real child module under -E -s -B, env={}
probe = ('import json,sys,os\nimport features.radar.price_chart_fetch as f\nimport requests,certifi\n'
         'H=("flask","flask_sqlalchemy","sqlalchemy","extensions","models","app","auth","dotenv","pymysql")\n'
         'print(json.dumps({"sys_executable":sys.executable,"sys_prefix":sys.prefix,"env_keys":sorted(os.environ),'
         '"flags":{"E":sys.flags.ignore_environment,"s":sys.flags.no_user_site,"B":sys.flags.dont_write_bytecode},'
         '"heavy_loaded":[h for h in H if h in sys.modules],"requests":requests.__version__,'
         '"certifi_exists":os.path.exists(certifi.where()),"cwd":os.getcwd()}))')
r = subprocess.run([sys.executable, *acq.INTERPRETER_FLAGS, '-c', probe], cwd=str(acq.APP_ROOT), env={},
                   capture_output=True, text=True, timeout=30)
OUT['minimal_env_import'] = {'returncode': r.returncode, 'stdout': json.loads(r.stdout) if r.returncode == 0 else r.stdout, 'stderr_tail': r.stderr[-400:]}
# 2. the REAL fetch child (price_chart_fetch.main via probe_child) against a loopback fixture server
NOW = dt.datetime.now(dt.timezone.utc)
WIN = c.window_for('1W', NOW)
ANCHOR = int(WIN.start.timestamp())
SEEN = []
def body():
    return json.dumps({'chart': {'result': [{'meta': {'symbol': 'AAPL', 'currency': 'USD', 'exchangeName': 'NMS'},
        'timestamp': [ANCHOR, ANCHOR + 300, ANCHOR + 600], 'indicators': {'quote': [{'close': [100.0, 100.5, None]}]}}], 'error': None}}).encode()
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        SEEN.append({'path': self.path, 'header_names': sorted(self.headers.keys())})
        b = body(); self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Set-Cookie', 'B=tracking'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{httpd.server_address[1]}/v8/finance/chart/'
def identity(sym='AAPL', mic='XNMS'):
    m = dt.datetime(2026, 8, 1)
    return {'ticker': sym, 'company_id': 11, 'instrument_id': 7, 'mic': mic, 'venue': 'NASDAQ', 'currency': 'USD',
            'provider_symbol': sym, 'mapped_at': c.iso_z(m), 'mapped_at_dt': m, 'first_seen_dt': dt.datetime(2026, 1, 1),
            'fingerprint': c.fingerprint(11, 7, sym, 'USD', mic, m)}
def wait_idle(co, limit=30.0):
    e = time.monotonic() + limit
    while time.monotonic() < e:
        if not co.snapshot()['in_flight']: return True
        time.sleep(0.02)
    return False
def alive(pid):
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    return True
marker = HERE / 'probe_marker.jsonl'
if marker.exists(): marker.unlink()
co = acq.Coordinator(launcher=acq.subprocess_launcher('tests.selected_price_unit.probe_child', (str(marker), BASE)))
t0 = time.monotonic(); first = co.get_or_start(identity(), WIN, now=NOW); adm = time.monotonic() - t0
idle = wait_idle(co); second = co.get_or_start(identity(), WIN, now=NOW)
rec = [json.loads(l) for l in marker.read_text().splitlines() if l] if marker.exists() else []
OUT['real_fetch_child_loopback'] = {'first_state': first['state'], 'admission_seconds': round(adm, 4), 'idle': idle,
    'second_state': second['state'], 'bars': (second.get('series') or {}).get('bars'),
    'counters': co.snapshot()['counters'], 'latency': co.snapshot()['latency'], 'loopback_requests': SEEN, 'child_record': rec}
httpd.shutdown(); httpd.server_close()
# 3. lifecycle behaviours, one child at a time, real launcher, real deadline/reap
life = []
for beh in ('normal', 'hanging', 'oversized', 'early_exit', 'garbage', 'nonzero', 'stderr_flood'):
    kids = []
    launch = acq.subprocess_launcher('tests.selected_price_unit.child_targets', (beh,))
    def L(spec, launch=launch, kids=kids):
        k = launch(spec); kids.append(k); return k
    co = acq.Coordinator(launcher=L)
    t0 = time.monotonic(); st = co.get_or_start(identity(), WIN, now=NOW)['state']
    idle = wait_idle(co); el = time.monotonic() - t0
    snap = co.snapshot(); k = kids[0] if kids else None
    entry = {'behaviour': beh, 'admitted_state': st, 'idle_within_30s': idle, 'elapsed_seconds': round(el, 3),
             'latency_max_seconds': snap['latency']['max_seconds'], 'counters': {a: b for a, b in snap['counters'].items() if b},
             'quarantined': snap.get('quarantined'), 'cache_keys': snap['cache_keys']}
    if k is not None:
        p = k.process
        entry.update({'child_pid': p.pid, 'returncode': p.poll(), 'os_alive_after': alive(p.pid), 'reader_alive_after': k.reader_alive(),
                      'stdin_closed': p.stdin.closed if p.stdin else None, 'stdout_closed': p.stdout.closed if p.stdout else None})
        entry['cleaned'] = (p.poll() is not None and not alive(p.pid) and not k.reader_alive() and p.stdin.closed and p.stdout.closed)
    life.append(entry)
OUT['lifecycle'] = life
# 4. leftovers by exact module name (only our own scratch children)
r = subprocess.run(['pgrep', '-af', 'tests.selected_price_unit'], capture_output=True, text=True)
OUT['leftover_processes'] = [l for l in r.stdout.splitlines() if 'pgrep' not in l]
OUT['scratch_dir'] = str(HERE.parent)
print(json.dumps(OUT, indent=1, default=str))
