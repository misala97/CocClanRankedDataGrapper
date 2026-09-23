"""HA1 local runtime: gated tests and a loopback preview on an HA1 target.

    py -3.12 scratchpad/ha1/local_runtime.py test
    py -3.12 scratchpad/ha1/local_runtime.py serve [port]

REFUSES unless the operator has independently authorized a disposable HA1
target: `RADAR_HA1_TARGET` (host:port/database) and `RADAR_HA1_REGISTRY`
(absolute JSON registry naming that target, destructive_target format). The
gate runs BEFORE the application is imported, so a refusal executes no SQL
and binds nothing. Refused outright: protected names (`personal_apps`,
`coc_stats`), the B1C and old promotion databases, a non-loopback database
host, database ports 3306 (the default local server) and 3399 (the old
promotion server), and preview ports 5021/5033. This script never provisions,
registers or migrates anything.

`test` runs only suites whose fixtures were inspected (CORRECTION-1,
2026-09-15):
- tests/test_radar_analysis_api.py -- gated; owned exact identities.
- tests/test_radar_board_sort.py -- pure; imports only features.radar.board.
Dropped after inspection: tests/test_radar_search.py (ungated; deletes every
TickerUniverse and RadarWatch row LIKE 'ZQ%', which would destroy rows it
does not own, including preview fixtures) and tests/test_radar_hub_page.py
(ungated; deletes any pre-existing AppUser named 'pytest radar hub
nonadmin'). Non-admin Analysis access is covered in the API suite instead.

`serve` refuses a port already in use (its owner is never stopped), writes a
runtime identity record -- candidate root, branch, HEAD, target, registry,
port, pid and a nonce -- to radar-design/artifacts/ha1/runtime/, and stamps
every response of THIS process with `X-HA1-Runtime: <nonce>`, so
verify_preview.py can prove the listening server is this gated candidate
before it logs in. Application code is unchanged.

CORRECTION-1: not executed (no authorized HA1 target; execution held).

CORRECTION-2 (2026-09-15, harness only, NOT executed against a target):
- U1: every Git command runs as `git -c safe.directory=<resolved candidate>
  -C <resolved candidate> ...`, scoped to that one command and that one path;
  a failure is a clear SystemExit. No global Git configuration is read for
  trust or written.
- U8: `serve` refuses without built assets and stamps the runtime record with
  ha1_harness.source_fingerprint(candidate): a deterministic digest of the
  covered application/harness source, radar templates, radar frontend source
  and served build (untracked HA1 files included; runtime records, manifests,
  reports, logs and caches excluded). verify_preview.py recomputes it and
  refuses on drift; nothing stops a running server.
"""
import atexit
import datetime as dt
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT.parent
RUNTIME_DIR = CANDIDATE / 'radar-design' / 'artifacts' / 'ha1' / 'runtime'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha1_harness as harness  # noqa: E402 -- standard library only

REFUSED_DATABASES = {'personal_apps', 'coc_stats', 'personal_apps_radar_b1c',
                     'personal_apps_radar_human_chatter_release'}
REFUSED_PORTS = {5021, 5033}
REFUSED_DB_PORTS = {3306, 3399}
LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1', '[::1]'}
RUNTIME_HEADER = 'X-HA1-Runtime'
TEST_SUITES = ('tests/test_radar_analysis_api.py', 'tests/test_radar_board_sort.py')


def gate(env=None):
    values = os.environ if env is None else env
    target = (values.get('RADAR_HA1_TARGET') or '').strip()
    registry = (values.get('RADAR_HA1_REGISTRY') or '').strip()
    if not target or not registry:
        raise SystemExit('HA1 target not authorized: set RADAR_HA1_TARGET=host:port/database '
                         'and RADAR_HA1_REGISTRY=<absolute registry json>; nothing was bound')
    if '/' not in target or ':' not in target.split('/', 1)[0]:
        raise SystemExit(f'RADAR_HA1_TARGET must be host:port/database, got {target!r}')
    host_port, database = target.split('/', 1)
    host, raw_port = host_port.rsplit(':', 1)
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit(f'RADAR_HA1_TARGET port is not a number: {raw_port!r}') from None
    if host not in LOOPBACK_HOSTS:
        raise SystemExit(f'{host} is not a loopback database host; refused')
    if port in REFUSED_DB_PORTS:
        raise SystemExit(f'database port {port} belongs to a protected server; refused')
    if not database or database.lower() in REFUSED_DATABASES:
        raise SystemExit(f'{database!r} is protected or belongs to another assignment; refused')
    path = Path(registry)
    if not path.is_absolute():
        raise SystemExit('RADAR_HA1_REGISTRY must be an absolute path')
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f'cannot read the HA1 registry {path}: {type(exc).__name__}') from None
    if (not isinstance(document, dict) or document.get('version') != 1
            or target not in (document.get('targets') or [])):
        raise SystemExit(f'{target} is not registered in {path}')
    return host, port, database, target, str(path)


def bind(host, port, database, target, registry):
    os.environ['RADAR_DESTRUCTIVE_TEST_TARGET'] = target
    os.environ['RADAR_DESTRUCTIVE_TEST_REGISTRY'] = registry
    os.environ.setdefault('PERSONAL_SECRET_KEY', 'ha1-disposable-local-only')
    user = os.environ.get('RADAR_HA1_DB_USER', 'root')
    password = os.environ.get('RADAR_HA1_DB_PASS', '')
    from extensions import db
    original_init = db.init_app

    def local_init(app):
        app.config['SQLALCHEMY_DATABASE_URI'] = (
            f'mysql+pymysql://{quote(user)}:{quote(password)}@{host}:{port}/{database}')
        app.config['SESSION_COOKIE_SECURE'] = False
        return original_init(app)
    db.init_app = local_init
    from app import app
    with app.app_context():
        url = db.engine.url
        assert url.host == host and url.port == port and url.database == database, url
        import destructive_target
        destructive_target.require(url)
        print(f'HA1 bound target: {target} ({db.engine.dialect.name}); no SQL executed by the gate')
    return app


def runtime_path(port: int) -> Path:
    return RUNTIME_DIR / f'preview-runtime-{int(port)}.json'


def git(*args, candidate=None) -> str:
    """Git in the resolved candidate only.

    The shell that runs this harness may not own the worktree, and Git then
    refuses with "detected dubious ownership" (exit 128). Trust is granted per
    command, for exactly this resolved path, through `-c safe.directory=`;
    nothing is written to global or system configuration. Any failure is a
    SystemExit that names the command and Git's own message."""
    root = Path(CANDIDATE if candidate is None else candidate).resolve()
    command = ['git', '-c', f'safe.directory={root.as_posix()}', '-C', str(root), *args]
    try:
        completed = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        raise SystemExit(f'git could not be started for {root}: {exc}') from None
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or '').strip()
        raise SystemExit(f'git {" ".join(args)} failed in {root} (exit {completed.returncode}): '
                         f'{message}; no Git configuration was changed')
    return completed.stdout.strip()


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def serve(app, target, registry, preview):
    if preview in REFUSED_PORTS:
        raise SystemExit(f'port {preview} belongs to another preview; choose an unused one')
    if not port_free(preview):
        raise SystemExit(f'port {preview} is in use; choose an unused one (its owner is not stopped)')
    branch, head = git('rev-parse', '--abbrev-ref', 'HEAD'), git('rev-parse', 'HEAD')
    fingerprint = harness.source_fingerprint(CANDIDATE)
    problems = harness.fingerprint_failures(fingerprint, fingerprint)
    if problems:
        raise SystemExit('refusing to serve: ' + '; '.join(problems))
    nonce = secrets.token_hex(16)

    @app.after_request
    def _stamp(response):
        response.headers[RUNTIME_HEADER] = nonce
        return response

    record = {
        'version': harness.RUNTIME_VERSION, 'target': target, 'registry': registry,
        'candidate_root': str(CANDIDATE), 'branch': branch, 'head': head,
        'port': preview, 'pid': os.getpid(), 'nonce': nonce,
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'fingerprint': fingerprint,
    }
    print(f'HA1 runtime fingerprint {fingerprint["digest"]} over {len(fingerprint["files"])} '
          f'files ({fingerprint["build_files"]} served build files)')
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    path = runtime_path(preview)
    path.write_text(json.dumps(record, indent=2), encoding='utf-8')
    atexit.register(lambda: path.unlink(missing_ok=True))
    app.run(host='127.0.0.1', port=preview, use_reloader=False, threaded=True)


if __name__ == '__main__':
    host, port, database, target, registry = gate()
    app = bind(host, port, database, target, registry)
    os.chdir(ROOT)
    if sys.argv[1:2] == ['serve']:
        serve(app, target, registry, int(sys.argv[2]) if len(sys.argv) > 2 else 5041)
    else:
        import pytest
        fingerprint = harness.source_fingerprint(CANDIDATE)
        print(f'HA1 test run over source fingerprint {fingerprint["digest"]} '
              f'({len(fingerprint["files"])} files)')
        raise SystemExit(pytest.main([*TEST_SUITES, '-q']))
