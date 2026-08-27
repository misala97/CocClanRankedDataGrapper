# personal_apps/tests/test_radar_discovery.py
"""The discovery script and the daemon share one IP's Reddit budget.

Reddit's anonymous feed budget is one request per window --
`x-ratelimit-remaining` reads 0.0 after a single call, measured on the VPS
2026-08-25. This script polls the same `/comments/.rss` feeds at SLEEP=45s
while the daemon polls one feed per 120s against that same budget. Run
together, they 429 each other and the daemon's cycle then reports `missing`
and writes no buckets at all.

These tests exercise the guard at the script boundary -- never by actually
running a discovery pass. Running discovery for real would hit the network
and overwrite personal_apps/reddit_candidates.json, which is the user's own
unrelated work in progress and must not be touched by this suite.
"""
from types import SimpleNamespace
from unittest.mock import Mock, mock_open

import pytest

import scripts.discover_reddit_sources as discovery


class _FakeAppContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeApp:
    """Stands in for the real Flask app so entering it is observable and
    costs no real database connection."""

    def __init__(self):
        self.entered = 0

    def app_context(self):
        self.entered += 1
        return _FakeAppContext()


def test_absent_systemctl_means_not_running_and_never_shells_out(monkeypatch):
    monkeypatch.setattr('shutil.which', lambda name: None)
    run = Mock()
    monkeypatch.setattr('subprocess.run', run)

    assert discovery._daemon_is_running() is False
    assert run.call_count == 0


def test_an_active_daemon_is_detected_via_the_exact_argv(monkeypatch):
    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/systemctl')
    run = Mock(return_value=SimpleNamespace(stdout='active\n'))
    monkeypatch.setattr('subprocess.run', run)

    assert discovery._daemon_is_running() is True
    run.assert_called_once_with(
        ['systemctl', 'is-active', 'radar_ingest'],
        capture_output=True, text=True)


def test_main_refuses_before_entering_the_app_context_when_daemon_runs(monkeypatch):
    fake_app = _FakeApp()
    monkeypatch.setattr(discovery, 'app', fake_app)
    monkeypatch.setattr(discovery, '_daemon_is_running', lambda: True)

    errors = []
    monkeypatch.setattr('sys.stderr', SimpleNamespace(write=errors.append))

    result = discovery.main([])

    assert result == 1
    assert fake_app.entered == 0
    joined = ''.join(errors)
    assert 'systemctl stop radar_ingest' in joined
    assert '--anyway' in joined


def test_anyway_proceeds_past_the_guard_when_daemon_runs(monkeypatch):
    fake_app = _FakeApp()
    monkeypatch.setattr(discovery, 'app', fake_app)
    monkeypatch.setattr(discovery, '_daemon_is_running', lambda: True)
    monkeypatch.setattr(discovery, 'CANDIDATES', [])
    monkeypatch.setattr(discovery.universe, 'load_lookup', lambda: {})
    fake_open = mock_open()
    monkeypatch.setattr(discovery, 'open', fake_open, raising=False)

    result = discovery.main(['--anyway'])

    assert result in (None, 0)
    assert fake_app.entered >= 1
    fake_open.assert_called_once_with(
        'reddit_candidates.json', 'w', encoding='utf-8')
