"""F1/F2 (MD-SELECTED-PRICE-CORRECTION-1): the fetch child is an explicit
fresh-interpreter module subprocess with a minimal environment.

The end-to-end case starts a PARENT whose __main__ is a FILE PATH with
unguarded top-level code (the shape of app.py / serve_b1c.py), a dummy secret
sentinel, and Python start-up/path/proxy overrides in its environment; that
parent runs the real Coordinator with the production launcher against a
loopback HTTP server. No provider, no database, no real secret."""
import hashlib
import http.server
import io
import json
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from features.radar import price_chart_acquisition as acq
from features.radar import price_chart_contract as c
from features.radar import price_chart_fetch as fetch

from .helpers import identity, utc

PERSONAL = Path(__file__).resolve().parents[2]
NOW = utc(2026, 9, 15, 13, 50, 19)
SPEC = c.request_spec(identity(), c.window_for('1W', NOW))
SENTINEL_KEY = 'RADAR_SP_DUMMY_SECRET'
SENTINEL = 'dummy-sentinel-not-a-real-secret'
#: Made-up values in the two real credential variable NAMES. Nothing here is a
#: credential; no provider is contacted with them.
KEY_ID_SENTINEL = 'PKSENTINELKEYID0000'
SECRET_SENTINEL = 'sentinel-secret-not-a-real-credential'
SEEN = []


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

PARENT = textwrap.dedent('''\
    import json, os, sys, time
    MARKER, PERSONAL, BASE = sys.argv[1], sys.argv[2], sys.argv[3]
    # Unguarded top level: every interpreter that executes this FILE says so.
    with open(MARKER, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps({'role': 'parent-script-top-level', 'pid': os.getpid(),
                             'name': __name__}) + '\\n')
    sys.path.insert(0, PERSONAL)
    os.environ[%(key)r] = %(value)r
    os.environ['APCA_API_KEY_ID'] = %(key_id)r
    os.environ['APCA_API_SECRET_KEY'] = %(secret)r

    if __name__ == '__main__':
        from features.radar import price_chart_acquisition as acq
        from features.radar import price_chart_contract as c
        from tests.selected_price_unit.helpers import identity, utc
        now = utc(2026, 9, 15, 13, 50, 19)
        window = c.window_for('1W', now)
        before = dict(os.environ)
        coordinator = acq.Coordinator(launcher=acq.subprocess_launcher(
            module='tests.selected_price_unit.probe_child', args=(MARKER, BASE)))
        started = time.monotonic()
        first = coordinator.get_or_start(identity(), window, now=now)
        admission = time.monotonic() - started
        while coordinator.snapshot()['in_flight'] and time.monotonic() - started < 30:
            time.sleep(0.02)
        ready = coordinator.get_or_start(identity(), window, now=now)
        print(json.dumps({
            'parent_pid': os.getpid(), 'first': first['state'], 'admission_seconds': admission,
            'ready': ready['state'], 'bars': (ready['series'] or {}).get('bars'),
            'counters': coordinator.snapshot()['counters'],
            'supervisor_seconds': coordinator.snapshot()['latency']['max_seconds'],
            'sentinel_in_parent': os.environ.get(%(key)r) == %(value)r,
            'parent_environment_unchanged': dict(os.environ) == before,
            'modules_flask_in_parent': 'flask' in sys.modules}))
''') % {'key': SENTINEL_KEY, 'value': SENTINEL,
        'key_id': 'PKSENTINELKEYID0000', 'secret': 'sentinel-secret-not-a-real-credential'}

HOOK = textwrap.dedent('''\
    """RADAR_SP_HOOK: a start-up hook reachable only through PYTHONPATH."""
    import json, os
    with open(os.environ['RADAR_SP_HOOK_MARKER'], 'a', encoding='utf-8') as fh:
        fh.write(json.dumps({'role': 'sitecustomize', 'pid': os.getpid()}) + '\\n')
''')


def chart_body():
    return json.dumps({'chart': {'result': [{
        'meta': {'symbol': 'AAPL', 'currency': 'USD', 'exchangeName': 'NMS'},
        'timestamp': [SPEC['anchor'], SPEC['anchor'] + 300],
        'indicators': {'quote': [{'close': [100.0, 100.5]}]}}], 'error': None}}).encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        SEEN.append((urlsplit(self.path).path, dict(self.headers)))
        body = chart_body()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Set-Cookie', 'B=tracking')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def loopback():
    SEEN.clear()
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{httpd.server_address[1]}/v8/finance/chart/'
    httpd.shutdown()
    httpd.server_close()


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def test_a_file_path_parent_is_not_re_executed_and_its_secrets_and_overrides_stay_behind(tmp_path, loopback):
    marker = tmp_path / 'marker.jsonl'
    marker.write_text('', encoding='utf-8')
    parent = tmp_path / 'parent_launcher.py'
    parent.write_text(PARENT, encoding='utf-8')
    hook = tmp_path / 'hook'
    hook.mkdir()
    (hook / 'sitecustomize.py').write_text(HOOK, encoding='utf-8')
    environment = dict(os.environ)
    environment.update({
        'PYTHONPATH': str(hook), 'PYTHONSTARTUP': str(hook / 'sitecustomize.py'),
        'RADAR_SP_HOOK_MARKER': str(marker),
        'HTTP_PROXY': 'http://proxyuser:proxypass@127.0.0.1:9', 'HTTPS_PROXY': 'http://proxyuser:proxypass@127.0.0.1:9',
        'NO_PROXY': '', 'SECRET_KEY': 'dummy-flask-secret', 'DATABASE_URL': 'mysql://dummy:dummy@127.0.0.1:1/none',
    })
    run = subprocess.run([sys.executable, str(parent), str(marker), str(PERSONAL), loopback],
                         cwd=str(tmp_path), env=environment, capture_output=True, timeout=60)
    assert run.returncode == 0, run.stderr.decode(errors='replace')[-2000:]
    out = json.loads(run.stdout.decode().strip().splitlines()[-1])
    parent_pid = out['parent_pid']
    records = lines(marker)

    # The parent really had the sentinel and the start-up hook ...
    assert out['sentinel_in_parent'] and out['parent_environment_unchanged']
    assert [r['pid'] for r in records if r['role'] == 'sitecustomize'] == [parent_pid]
    # ... its file's top level ran exactly once, in the parent only ...
    assert [(r['pid'], r['name']) for r in records if r['role'] == 'parent-script-top-level'] == [
        (parent_pid, '__main__')]
    # ... and the child was the explicit module, with nothing inherited.
    children = [r for r in records if r['role'] == 'child']
    assert len(children) == 1
    child = children[0]
    assert child['pid'] != parent_pid
    assert child['main_spec'] == 'tests.selected_price_unit.probe_child'
    assert child['heavy_modules'] == []
    assert child['dummy_sentinel_present'] is False and child['sitecustomize_hook_loaded'] is False
    assert set(child['env_keys']) <= set(acq.CHILD_ENV_ALLOWLIST.get(os.name, ())) | set(acq.CREDENTIAL_ENV)
    # The two credential NAMES crossed, with their values intact and nowhere
    # near the argument array; nothing else the parent held crossed with them.
    assert set(child['env_keys']) >= set(acq.CREDENTIAL_ENV)
    assert child['credential_digests'] == {'APCA_API_KEY_ID': digest(KEY_ID_SENTINEL),
                                           'APCA_API_SECRET_KEY': digest(SECRET_SENTINEL)}
    assert child['argv_carries_a_credential'] is False
    assert child['flags'] == {'ignore_environment': 1, 'no_user_site': 1, 'dont_write_bytecode': 1}
    # The production child's own transport did the request: direct, no proxy, no cookie.
    assert (out['first'], out['ready']) == ('pending', 'ready')
    assert out['bars'] == [[SPEC['anchor'], 100.0], [SPEC['anchor'] + 300, 100.5]]
    assert len(SEEN) == 1 and SEEN[0][0].endswith('/AAPL')
    assert not {'Proxy-Authorization', 'Cookie'} & set(SEEN[0][1])
    evidence = os.environ.get('SELECTED_PRICE_ISOLATION_EVIDENCE_FILE')
    if evidence:
        Path(evidence).write_text(json.dumps({'parent': out, 'marker_records': records,
                                              'loopback_requests': len(SEEN),
                                              'loopback_request_header_names': sorted(SEEN[0][1])},
                                             indent=2), encoding='utf-8')


def test_the_child_environment_is_an_explicit_allowlist():
    hostile = {'SYSTEMROOT': r'C:\Windows', 'PATH': '/usr/bin', 'HOME': '/root', 'PYTHONPATH': '/tmp/hook',
               'PYTHONSTARTUP': '/tmp/hook.py', 'PYTHONHOME': '/elsewhere', 'HTTP_PROXY': 'http://u:p@proxy',
               'HTTPS_PROXY': 'http://u:p@proxy', 'ALL_PROXY': 'socks://proxy', 'REQUESTS_CA_BUNDLE': '/tmp/ca',
               'SECRET_KEY': 'x', 'DATABASE_URL': 'mysql://u:p@db', 'FINNHUB_API_KEY': 'x',
               'VAPID_PRIVATE_KEY': 'x', 'LD_PRELOAD': '/tmp/evil.so', SENTINEL_KEY: SENTINEL}
    assert acq.child_environment(hostile, platform='nt') == {'SYSTEMROOT': r'C:\Windows'}
    assert acq.child_environment(hostile, platform='posix') == {}
    assert acq.child_environment({'PATH': 'x'}, platform='nt') == {}
    produced = acq.child_environment(hostile, platform='nt')
    produced['EXTRA'] = '1'
    assert 'EXTRA' not in hostile


def test_only_the_two_named_alpaca_variables_join_the_platform_minimum():
    assert acq.CREDENTIAL_ENV == ('APCA_API_KEY_ID', 'APCA_API_SECRET_KEY')
    hostile = {'SYSTEMROOT': r'C:\Windows', 'APCA_API_KEY_ID': KEY_ID_SENTINEL,
               'APCA_API_SECRET_KEY': SECRET_SENTINEL, 'APCA_API_BASE_URL': 'https://paper-api.alpaca.markets',
               'ALPACA_API_KEY': 'x', 'SECRET_KEY': 'x', 'FINNHUB_API_KEY': 'x'}
    assert acq.child_environment(hostile, platform='nt') == {
        'SYSTEMROOT': r'C:\Windows', 'APCA_API_KEY_ID': KEY_ID_SENTINEL,
        'APCA_API_SECRET_KEY': SECRET_SENTINEL}
    assert acq.child_environment(hostile, platform='posix') == {
        'APCA_API_KEY_ID': KEY_ID_SENTINEL, 'APCA_API_SECRET_KEY': SECRET_SENTINEL}
    # Blank is absent, not an empty credential.
    assert acq.child_environment({'APCA_API_KEY_ID': '', 'APCA_API_SECRET_KEY': '  '},
                                 platform='posix') == {}


def test_an_alpaca_child_is_started_with_no_credential_in_its_arguments(monkeypatch):
    FakePopen.instances.clear()
    monkeypatch.setattr(acq.subprocess, 'Popen', FakePopen)
    monkeypatch.setenv('APCA_API_KEY_ID', KEY_ID_SENTINEL)
    monkeypatch.setenv('APCA_API_SECRET_KEY', SECRET_SENTINEL)
    now = utc(2026, 9, 16, 0, 34)
    spec, refusal = c.alpaca_request_spec(identity(), c.window_for('1D', now), now=now)
    assert refusal is None
    acq.subprocess_launcher()(spec)
    popen = FakePopen.instances[0]
    written = popen.stdin.written.decode()
    for secret in (KEY_ID_SENTINEL, SECRET_SENTINEL):
        assert secret not in ' '.join(popen.args)
        assert secret not in written                       # not in the request spec either
    assert json.loads(written) == spec
    assert popen.kwargs['env'] == acq.child_environment()
    assert popen.kwargs['env']['APCA_API_KEY_ID'] == KEY_ID_SENTINEL
    assert popen.kwargs['stderr'] is subprocess.DEVNULL


class FakeStdin(io.BytesIO):
    def close(self):
        self.written = self.getvalue()
        super().close()


class FakePopen:
    instances = []

    def __init__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.stdin = FakeStdin()
        self.stdout = io.BytesIO(json.dumps({'kind': 'empty'}).encode())
        self.pid = 4242
        self.returncode = None
        self.killed = False
        FakePopen.instances.append(self)

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_the_launcher_uses_an_argument_array_no_shell_and_never_touches_the_parent_environment(monkeypatch):
    FakePopen.instances.clear()
    monkeypatch.setattr(acq.subprocess, 'Popen', FakePopen)
    monkeypatch.setenv(SENTINEL_KEY, SENTINEL)
    touched = []
    monkeypatch.setattr(os, 'putenv', lambda *a: touched.append(('putenv', a)))
    monkeypatch.setattr(os, 'unsetenv', lambda *a: touched.append(('unsetenv', a)))
    before = dict(os.environ)
    child = acq.subprocess_launcher()(SPEC)
    popen = FakePopen.instances[0]
    assert popen.args == [sys.executable, '-E', '-s', '-B', '-m', 'features.radar.price_chart_fetch']
    assert popen.kwargs.get('shell', False) is False
    assert popen.kwargs['env'] == acq.child_environment() and SENTINEL_KEY not in popen.kwargs['env']
    assert popen.kwargs['env'] is not os.environ
    assert popen.kwargs['stdin'] is subprocess.PIPE and popen.kwargs['stdout'] is subprocess.PIPE
    assert popen.kwargs['stderr'] is subprocess.DEVNULL
    assert Path(popen.kwargs['cwd']) == PERSONAL and popen.kwargs['bufsize'] == 0
    assert json.loads(popen.stdin.written) == SPEC and popen.stdin.closed
    assert child.collect(lambda: 0.0, 5.0) == ('done', json.dumps({'kind': 'empty'}).encode())
    assert child.reap(__import__('time').monotonic) is True
    assert dict(os.environ) == before and touched == []


def test_an_oversized_spec_or_a_malformed_module_starts_nothing(monkeypatch):
    FakePopen.instances.clear()
    monkeypatch.setattr(acq.subprocess, 'Popen', FakePopen)
    with pytest.raises(ValueError):
        acq.subprocess_launcher()(dict(SPEC, symbol='A' * (fetch.SPEC_LIMIT_BYTES + 1)))
    for module in ('features.radar.price_chart_fetch; echo', '-c', 'x y', ''):
        with pytest.raises(ValueError):
            acq.subprocess_launcher(module=module)
    with pytest.raises(ValueError):
        acq.subprocess_launcher(args=(1,))
    assert FakePopen.instances == []


def test_a_child_gone_before_its_request_is_written_is_not_an_exception(monkeypatch):
    class Broken(FakePopen):
        def __init__(self, args, **kwargs):
            super().__init__(args, **kwargs)

            def refuse(data):
                raise BrokenPipeError(32, 'The pipe is being closed')
            self.stdin.write = refuse

    monkeypatch.setattr(acq.subprocess, 'Popen', Broken)
    child = acq.subprocess_launcher()(SPEC)
    assert child.process.stdin.closed
    child.reap(__import__('time').monotonic)


def test_a_reader_that_cannot_start_kills_the_child_and_closes_its_pipes(monkeypatch):
    FakePopen.instances.clear()
    monkeypatch.setattr(acq.subprocess, 'Popen', FakePopen)

    class NoThread:
        def __init__(self, *a, **k):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(acq.threading, 'Thread', NoThread)
    with pytest.raises(RuntimeError):
        acq.subprocess_launcher()(SPEC)
    popen = FakePopen.instances[0]
    assert popen.killed and popen.stdin.closed and popen.stdout.closed


def test_unconfirmed_subprocess_cleanup_quarantines_acquisition():
    class Stubborn(FakePopen):
        def __init__(self):
            super().__init__(['child'])
            self.stdout = io.BytesIO(b'')

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired('child', timeout)

        def terminate(self):
            pass

        def kill(self):
            self.killed = True

    made = []

    def launcher(spec):
        child = acq.Child(Stubborn())
        made.append(child)
        return child

    coordinator = acq.Coordinator(launcher=launcher, deadline_s=0.2, cleanup_s=0.1)
    coordinator.get_or_start(identity(), c.window_for('1W', NOW), now=NOW)
    ends = __import__('time').monotonic() + 10
    while coordinator.snapshot()['in_flight'] and __import__('time').monotonic() < ends:
        __import__('time').sleep(0.02)
    snapshot = coordinator.snapshot()
    assert made[0].process.killed
    assert snapshot['quarantined'] is True and snapshot['counters']['cleanup_failed'] == 1
    again = coordinator.get_or_start(identity(instrument_id=9), c.window_for('1W', NOW), now=NOW)
    assert again['state'] == 'unavailable' and again['reason'].startswith('cleanup_failed')
    assert len(made) == 1


# --- R2-1 (MD-SELECTED-PRICE-CORRECTION-2): a launch that fails AFTER Popen ----------

class IgnoresKill(FakePopen):
    """Started, then will not die: kill() does nothing and wait() times out."""

    def kill(self):
        self.killed = True

    def terminate(self):
        pass

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired('child', timeout)


class GoneBeforeKill(FakePopen):
    """kill() raises because the process already exited; wait() proves it."""

    def kill(self):
        self.killed = True
        self.returncode = 1
        raise ProcessLookupError(3, 'No such process')

    def wait(self, timeout=None):
        return self.returncode


def reader_cannot_start(monkeypatch):
    real = acq.threading.Thread

    class Refusing(real):
        def start(self):
            if self.name == 'radar-price-chart-reader':
                raise RuntimeError("can't start new thread")
            super().start()

    monkeypatch.setattr(acq.threading, 'Thread', Refusing)


def two_charts(monkeypatch, popen):
    """The real Coordinator and real launcher: one chart, then a different one."""
    FakePopen.instances.clear()
    monkeypatch.setattr(acq.subprocess, 'Popen', popen)
    coordinator = acq.Coordinator(deadline_s=0.3, cleanup_s=0.2)
    window = c.window_for('1W', NOW)
    coordinator.get_or_start(identity(), window, now=NOW)
    ends = __import__('time').monotonic() + 10
    while coordinator.snapshot()['in_flight'] and __import__('time').monotonic() < ends:
        __import__('time').sleep(0.02)
    snapshot = coordinator.snapshot()
    second = coordinator.get_or_start(identity(instrument_id=9), window, now=NOW)
    return snapshot, second


def test_an_unconfirmed_cleanup_after_a_post_popen_failure_quarantines_before_another_start(monkeypatch):
    reader_cannot_start(monkeypatch)
    snapshot, second = two_charts(monkeypatch, IgnoresKill)
    assert FakePopen.instances[0].killed
    assert snapshot['quarantined'] is True
    assert snapshot['counters']['cleanup_failed'] == 1 and snapshot['counters']['invalid'] == 1
    assert second['state'] == 'unavailable' and second['reason'].startswith('cleanup_failed')
    assert len(FakePopen.instances) == 1


@pytest.mark.parametrize('popen', [FakePopen, GoneBeforeKill], ids=['killed-and-reaped', 'already-exited'])
def test_a_confirmed_cleanup_after_a_post_popen_failure_is_an_ordinary_invalid_start(monkeypatch, popen):
    reader_cannot_start(monkeypatch)
    snapshot, second = two_charts(monkeypatch, popen)
    assert snapshot['quarantined'] is False and snapshot['counters']['cleanup_failed'] == 0
    assert snapshot['counters']['invalid'] == 1
    assert second['state'] == 'pending' and len(FakePopen.instances) == 2


def test_a_failure_before_any_process_exists_never_quarantines(monkeypatch):
    attempts = []

    def refuse(args, **kwargs):
        attempts.append(args)
        raise FileNotFoundError(2, 'interpreter not found')

    snapshot, second = two_charts(monkeypatch, refuse)
    assert snapshot['quarantined'] is False and snapshot['counters']['cleanup_failed'] == 0
    assert snapshot['counters']['invalid'] == 1
    assert second['state'] == 'pending'
    __import__('time').sleep(0.2)
    assert len(attempts) == 2


def test_emergency_cleanup_reports_exit_only_from_process_evidence():
    stubborn = IgnoresKill(['child'])
    assert acq._kill_now(stubborn) is False and stubborn.killed       # a kill call is not an exit
    assert stubborn.stdin.closed and stubborn.stdout.closed
    reaped = FakePopen(['child'])
    assert acq._kill_now(reaped) is True and reaped.killed
    gone = GoneBeforeKill(['child'])
    assert acq._kill_now(gone) is True                                # kill raised, wait proved exit


def test_the_launcher_names_an_unconfirmed_cleanup_and_keeps_the_original_error(monkeypatch):
    reader_cannot_start(monkeypatch)
    monkeypatch.setattr(acq.subprocess, 'Popen', IgnoresKill)
    with pytest.raises(acq.UnconfirmedCleanup) as raised:
        acq.subprocess_launcher()(SPEC)
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert "can't start new thread" in str(raised.value.__cause__)
