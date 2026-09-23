"""P06 with REAL fetch children started by the PRODUCTION subprocess launcher:
fresh interpreters, minimal environment, real pipes, loopback/IPC only, no
provider, no network. Measures what the supervisor actually did; the numbers
are this machine's scheduling, not a guarantee.

Set SELECTED_PRICE_EVIDENCE_FILE to record the observed timings as JSON."""
import json
import os
import sys
import time

import pytest

from features.radar import price_chart_acquisition as acq
from features.radar import price_chart_contract as c

from .helpers import identity, utc

NOW = utc(2026, 9, 15, 14, 7)
WINDOW = c.window_for('1W', NOW)
TARGETS = 'tests.selected_price_unit.child_targets'
EVIDENCE = {'launcher': 'subprocess', 'platform': sys.platform, 'python': sys.version.split()[0]}


@pytest.fixture(scope='module', autouse=True)
def record():
    yield
    path = os.environ.get('SELECTED_PRICE_EVIDENCE_FILE')
    if path:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(EVIDENCE, handle, indent=2)


def recording(behaviour):
    children = []
    launch = acq.subprocess_launcher(module=TARGETS, args=(behaviour,))

    def launcher(spec):
        child = launch(spec)
        children.append(child)
        return child
    return launcher, children


def wait_idle(coordinator, limit=30.0):
    ends = time.monotonic() + limit
    while time.monotonic() < ends:
        if not coordinator.snapshot()['in_flight']:
            return
        time.sleep(0.02)
    raise AssertionError('supervisor did not finish')


def os_process_alive(pid):
    """Asks the OS, not the Popen object, whether a pid still runs."""
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)       # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259                            # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def assert_cleaned(child):
    process = child.process
    assert process.poll() is not None, 'child not reaped'
    assert not os_process_alive(process.pid), 'child survived'
    assert not child.reader_alive(), 'reader thread survived'
    assert process.stdin.closed and process.stdout.closed, 'pipe handle left open'


def test_a_real_child_returns_a_series_without_flask_the_database_or_the_parent_environment():
    launcher, children = recording('normal')
    coordinator = acq.Coordinator(launcher=launcher)
    started = time.monotonic()
    answer = coordinator.get_or_start(identity(), WINDOW, now=NOW)
    admission = time.monotonic() - started
    assert answer['state'] == 'pending' and admission < 0.5 and children == []
    wait_idle(coordinator)
    ready = coordinator.get_or_start(identity(), WINDOW, now=NOW)
    assert ready['state'] == 'ready'
    assert ready['series']['loaded'] == []
    assert set(ready['series']['env_keys']) <= set(acq.CHILD_ENV_ALLOWLIST.get(os.name, ()))
    child = children[0]
    assert child.process.returncode == 0 and ready['series']['child_pid'] == child.process.pid
    assert_cleaned(child)
    latency = coordinator.snapshot()['latency']
    EVIDENCE['normal'] = {'admission_seconds': round(admission, 4), 'supervisor_seconds': latency['max_seconds'],
                          'exitcode': child.process.returncode,
                          'heavy_modules_in_child': ready['series']['loaded'],
                          'child_env_keys': ready['series']['env_keys']}


def test_the_production_child_module_refuses_a_bad_spec_in_a_fresh_interpreter():
    launch = acq.subprocess_launcher()
    started = time.monotonic()
    child = launch({'version': 1, 'symbol': 'http://elsewhere/'})
    outcome, data = child.collect(time.monotonic, started + acq.DEADLINE_S)
    confirmed = child.reap(time.monotonic)
    assert outcome == 'done' and json.loads(data) == {'kind': 'invalid', 'reason': 'request_spec'}
    assert confirmed and child.process.returncode == 0
    assert_cleaned(child)
    EVIDENCE['production_child_bad_spec'] = {'seconds': round(time.monotonic() - started, 4),
                                             'exitcode': child.process.returncode}


def test_a_hanging_child_is_terminated_at_the_deadline_and_blocks_no_request():
    launcher, children = recording('hanging')
    coordinator = acq.Coordinator(launcher=launcher)
    started = time.monotonic()
    assert coordinator.get_or_start(identity(), WINDOW, now=NOW)['state'] == 'pending'
    admission = time.monotonic() - started
    time.sleep(0.5)
    other = coordinator.get_or_start(identity(instrument_id=8), WINDOW, now=NOW)
    assert other['state'] == 'busy' and admission < 0.5
    wait_idle(coordinator, limit=acq.DEADLINE_S + acq.CLEANUP_S + 10)
    total = time.monotonic() - started
    snapshot = coordinator.snapshot()
    assert snapshot['counters']['timeout'] == 1 and snapshot['quarantined'] is False
    assert len(children) == 1
    assert acq.DEADLINE_S <= snapshot['latency']['max_seconds'] < acq.DEADLINE_S + acq.CLEANUP_S + 2
    assert_cleaned(children[0])
    EVIDENCE['hanging'] = {'admission_seconds': round(admission, 4), 'deadline_seconds': acq.DEADLINE_S,
                           'cleanup_allowance_seconds': acq.CLEANUP_S,
                           'supervisor_seconds': snapshot['latency']['max_seconds'],
                           'wall_seconds_until_idle': round(total, 3),
                           'exitcode': children[0].process.returncode,
                           'other_key_state_meanwhile': other['state']}


def test_a_pipe_filling_oversized_child_is_cut_off_early_and_reaped():
    launcher, children = recording('oversized')
    coordinator = acq.Coordinator(launcher=launcher)
    started = time.monotonic()
    coordinator.get_or_start(identity(), WINDOW, now=NOW)
    wait_idle(coordinator)
    total = time.monotonic() - started
    snapshot = coordinator.snapshot()
    assert snapshot['counters']['invalid'] == 1 and not coordinator._cache
    assert snapshot['latency']['max_seconds'] < acq.DEADLINE_S
    assert_cleaned(children[0])
    EVIDENCE['oversized'] = {'supervisor_seconds': snapshot['latency']['max_seconds'],
                             'wall_seconds_until_idle': round(total, 3),
                             'exitcode': children[0].process.returncode,
                             'result_limit_bytes': acq.fetch.RESULT_LIMIT_BYTES}


def test_a_child_flooding_stderr_cannot_fill_a_pipe_or_memory():
    launcher, children = recording('stderr_flood')
    coordinator = acq.Coordinator(launcher=launcher)
    coordinator.get_or_start(identity(), WINDOW, now=NOW)
    wait_idle(coordinator)
    snapshot = coordinator.snapshot()
    assert snapshot['counters']['success'] == 1
    assert snapshot['latency']['max_seconds'] < acq.DEADLINE_S
    assert_cleaned(children[0])
    EVIDENCE['stderr_flood_8MiB'] = {'supervisor_seconds': snapshot['latency']['max_seconds'],
                                     'exitcode': children[0].process.returncode}


@pytest.mark.parametrize('behaviour', ['early_exit', 'garbage', 'nonzero'])
def test_early_exit_garbage_and_failed_exit_are_invalid_and_cached_never(behaviour):
    launcher, children = recording(behaviour)
    coordinator = acq.Coordinator(launcher=launcher)
    coordinator.get_or_start(identity(), WINDOW, now=NOW)
    wait_idle(coordinator)
    snapshot = coordinator.snapshot()
    assert snapshot['counters']['invalid'] == 1 and snapshot['counters']['success'] == 0
    assert not coordinator._cache and snapshot['quarantined'] is False
    assert_cleaned(children[0])
    EVIDENCE[behaviour] = {'supervisor_seconds': snapshot['latency']['max_seconds'],
                           'exitcode': children[0].process.returncode}
