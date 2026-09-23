"""request_timing: one line per request, by route template, and only when asked.

Every test but the two fresh-import ones builds its own `Flask(__name__)`:
the real app is only ever read here, never given a hook. And every test puts
the two process-wide loggers back afterwards, because `install` changes
loggers every other suite shares -- a `radar.board` left with
`propagate = False` would blind the caplog assertions in the board suites.
"""
import itertools
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from flask import Blueprint, Flask, Response

import request_timing
from features.radar import board_metrics

ENV_VAR = 'PERSONAL_REQUEST_TIMING_LOG'
ON = {ENV_VAR: '1'}
LOGGERS = ('app.request', 'radar.board')
PERSONAL_APPS = Path(__file__).resolve().parents[1]

BOARD_READ = ('radar.board board read demand=initial class=warm '
              'key=0123456789ab outcome=ready cache_age=1.0 queue_age=- '
              'read_ms=3 account_ms=4')
TICKER_LINE = ('app.request request method=GET '
               'route=/radar/api/ticker/<ticker> status=200 bytes=2 ms=500.0\n')


# --- fixtures and helpers ----------------------------------------------------

@pytest.fixture(autouse=True)
def loggers_put_back():
    saved = {name: _state(name) for name in LOGGERS}
    yield
    for name, (handlers, level, propagate) in saved.items():
        target = logging.getLogger(name)
        for handler in list(target.handlers):
            if handler not in handlers:
                target.removeHandler(handler)
        target.setLevel(level)
        target.propagate = propagate
    assert {name: _state(name) for name in LOGGERS} == saved


@pytest.fixture()
def steady_clock(monkeypatch):
    """Each reading half a second after the last, so every request's `ms` is
    exactly 500.0 and a test can compare a whole line."""
    readings = itertools.count(0, 0.5)
    monkeypatch.setattr(request_timing, '_clock', lambda: next(readings))


@pytest.fixture()
def listen():
    """Hang a `_Heard` on a logger for one test; it comes off afterwards."""
    attached = []

    def attach(name, level=None, events=None):
        target = logging.getLogger(name)
        heard = _Heard(events)
        attached.append((target, heard, target.level))
        target.addHandler(heard)
        if level is not None:
            target.setLevel(level)
        return heard

    yield attach
    for target, heard, level in reversed(attached):
        target.removeHandler(heard)
        target.setLevel(level)


class _Heard(logging.Handler):
    """Every record that reaches it, at any level."""

    def __init__(self, events=None):
        super().__init__(logging.DEBUG)
        self.records = []
        self._events = events

    def emit(self, record):
        self.records.append(record)
        if self._events is not None:
            self._events.append('line')


def _state(name):
    target = logging.getLogger(name)
    return list(target.handlers), target.level, target.propagate


def _app(**kwargs):
    app = Flask(__name__, **kwargs)

    @app.route('/radar/api/ticker/<ticker>')
    def ticker(ticker):
        return 'ok'

    return app


def _hooks(app):
    return [function
            for registry in (app.before_request_funcs, app.after_request_funcs,
                             app.teardown_request_funcs)
            for functions in registry.values()
            for function in functions]


def _log_a_read():
    board_metrics.log_read(demand='initial', cls='warm', key='0123456789abcdef',
                           outcome='ready', cache_age=1.0, queue_age=None,
                           read_ms=3, account_ms=4)


# --- the real app ------------------------------------------------------------

# What a gunicorn worker does: import app.py in a fresh interpreter and
# configure nothing. gunicorn's own logging setup (glogging.Logger.setup,
# 26.2.0) touches only `gunicorn.error` and `gunicorn.access`, so the state
# this prints is the state a worker serves requests in. Run in a child process
# because this one has pytest's handlers on the root logger.
_FRESH_IMPORT = '''
import json, logging
from app import app  # the import is what is under test
from features.radar import board_metrics

board = logging.getLogger('radar.board')
handlers, current = 0, board
while current is not None:
    handlers += sum(1 for handler in current.handlers
                    if handler.level <= logging.INFO)
    current = current.parent if current.propagate else None
print(json.dumps({'info_enabled': board.isEnabledFor(logging.INFO),
                  'handlers_at_info': handlers}), flush=True)
board_metrics.log_read(demand='initial', cls='warm', key='0123456789abcdef',
                       outcome='ready', cache_age=1.0, queue_age=None,
                       read_ms=3, account_ms=4)
'''


def _fresh_import(value):
    env = {name: text for name, text in os.environ.items() if name != ENV_VAR}
    if value is not None:
        env[ENV_VAR] = value
    done = subprocess.run([sys.executable, '-c', _FRESH_IMPORT],
                          cwd=PERSONAL_APPS, env=env, capture_output=True,
                          text=True, timeout=300, check=False)
    assert done.returncode == 0, done.stderr
    return done


def test_a_freshly_imported_app_drops_every_board_line_with_the_variable_unset():
    """The gap, as it stands in production today. board_metrics.py writes a
    `board read` line per read in the web process, and nothing there gives
    `radar.board` a handler: it inherits the root's WARNING, so every read
    line is dropped before it is formatted and never reaches journald. (The
    producer calls basicConfig itself, which is why its build lines do.)

    Unset, this stays true after this module exists -- off means the loggers
    are left exactly as they were."""
    done = _fresh_import(None)
    lines = done.stdout.splitlines()
    assert json.loads(lines[0]) == {'info_enabled': False,
                                    'handlers_at_info': 0}
    assert lines[1:] == []
    assert 'board read' not in done.stderr


def test_a_freshly_imported_app_prints_board_lines_with_the_variable_on():
    """The fix, through app.py itself: the same fresh import with the
    variable on prints the read line on stdout -- once, and nowhere else."""
    done = _fresh_import('1')
    lines = done.stdout.splitlines()
    assert json.loads(lines[0]) == {'info_enabled': True,
                                    'handlers_at_info': 1}
    assert lines[1:] == [BOARD_READ]
    assert 'board read' not in done.stderr


def test_the_real_app_has_no_timing_hook_with_the_variable_unset():
    """Merging this changes nothing by default: the app every other suite
    imports carries no hook from this module, and both loggers are bare."""
    from app import app as real_app

    assert not request_timing.enabled(os.environ), (
        f'{ENV_VAR} is set in this environment; this test is about the default')
    hooks = _hooks(real_app)
    assert hooks, ('the real app has hooks of its own -- finding none means '
                   'this test looked in the wrong place')
    assert [hook.__qualname__ for hook in hooks
            if hook.__module__ == request_timing.__name__] == []
    for name in LOGGERS:
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True


# --- on and off --------------------------------------------------------------

@pytest.mark.parametrize('value, on', [
    ('1', True), ('true', True), ('TRUE', True), (' yes ', True), ('On', True),
    (None, False), ('', False), ('0', False), ('false', False), ('no', False),
    ('off', False), ('enabled', False), ('y', False),
])
def test_the_variable_is_read_from_the_environment_strictly(value, on,
                                                            monkeypatch):
    if value is None:
        monkeypatch.delenv(ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_VAR, value)
    app = _app()
    assert request_timing.install(app) is on        # the default is os.environ
    assert bool(_hooks(app)) is on


@pytest.mark.parametrize('env', [{}, {ENV_VAR: ''}, {ENV_VAR: '0'},
                                 {ENV_VAR: 'off'}])
def test_off_registers_nothing_touches_no_logger_and_writes_nothing(
        env, capsys, listen):
    app = _app()
    before = {name: _state(name) for name in LOGGERS}

    assert request_timing.install(app, env=env) is False
    assert _hooks(app) == []
    assert app.extensions == {}
    assert {name: _state(name) for name in LOGGERS} == before

    # Listening as closely as a logger can be listened to.
    heard = listen('app.request', level=logging.DEBUG)
    response = app.test_client().get('/radar/api/ticker/NVDA?window=24')
    assert response.status_code == 200
    _log_a_read()
    assert heard.records == []
    assert capsys.readouterr().out == ''


# --- the line ----------------------------------------------------------------

def test_a_dynamic_route_is_logged_by_its_template_and_nothing_else(
        capsys, steady_clock):
    """The request is made as identifiable as a request can be -- a ticker in
    the path, a query string, a session cookie, a bearer token, a client
    address -- and the line is compared whole: a field nobody thought to
    forbid is how an identifier would actually arrive."""
    app = _app()
    assert request_timing.install(app, env=ON) is True
    client = app.test_client()
    client.set_cookie('session', 'cookie-4711')

    response = client.get('/radar/api/ticker/NVDA?window=24',
                          headers={'Authorization': 'Bearer token-0815'},
                          environ_base={'REMOTE_ADDR': '203.0.113.77'})

    assert response.status_code == 200
    out, err = capsys.readouterr()
    assert out == TICKER_LINE
    for value in ('NVDA', 'window', '24', 'cookie-4711', 'Bearer',
                  'token-0815', '203.0.113.77'):
        assert value not in out and value not in err


def test_an_unmatched_path_is_one_label_whatever_it_asked_for(
        capsys, steady_clock):
    app = _app()
    assert request_timing.install(app, env=ON)

    response = app.test_client().get(
        '/radar/api/tickers/NVDA/history?token=abc')

    assert response.status_code == 404
    out = capsys.readouterr().out
    assert out == ('app.request request method=GET route=<unmatched> '
                   f'status=404 bytes={len(response.data)} ms=500.0\n')
    assert 'NVDA' not in out and 'token' not in out


def test_every_static_file_is_one_label(tmp_path, capsys, steady_clock):
    """The app's and a blueprint's, found or not: a file name is as much a
    value as a ticker, and a page's worth of asset lines is one fact."""
    # Named `static`: Flask serves an app's folder at `/<its basename>`.
    (tmp_path / 'static').mkdir()
    (tmp_path / 'static' / 'site.css').write_bytes(b'body{}')
    (tmp_path / 'radar').mkdir()
    (tmp_path / 'radar' / 'radar.css').write_bytes(b'main{color:red}')
    app = _app(static_folder=str(tmp_path / 'static'))
    app.register_blueprint(Blueprint(
        'radar', __name__, static_folder=str(tmp_path / 'radar'),
        static_url_path='/radar/static'))
    assert request_timing.install(app, env=ON)
    client = app.test_client()

    sent = []
    for path in ('/static/site.css', '/radar/static/radar.css',
                 '/static/missing.css'):
        response = client.get(path)
        sent.append((response.status_code, len(response.data)))
        response.close()

    assert sent[:2] == [(200, 6), (200, 15)]
    assert sent[2][0] == 404
    assert capsys.readouterr().out.splitlines() == [
        'app.request request method=GET route=<static> '
        f'status={status} bytes={size} ms=500.0'
        for status, size in sent]


def test_a_view_that_raises_is_logged_with_the_500_it_sent(capsys,
                                                           steady_clock):
    """Debug off, as under gunicorn: Flask turns the exception into a 500 and
    still runs after_request, so the line has the page's size."""
    app = _app()

    @app.route('/boom')
    def boom():
        raise RuntimeError('boom')

    assert request_timing.install(app, env=ON)
    response = app.test_client().get('/boom')

    assert response.status_code == 500
    assert capsys.readouterr().out == (
        'app.request request method=GET route=/boom status=500 '
        f'bytes={len(response.data)} ms=500.0\n')


def test_a_request_that_escapes_flask_is_logged_from_teardown(capsys,
                                                             steady_clock):
    """With PROPAGATE_EXCEPTIONS on -- debug, testing -- the exception leaves
    Flask and after_request never runs. Teardown still does, and writes the
    line; there is no response to measure, so `bytes=-`."""
    app = _app()
    app.config['PROPAGATE_EXCEPTIONS'] = True

    @app.route('/boom')
    def boom():
        raise RuntimeError('boom')

    assert request_timing.install(app, env=ON)
    with pytest.raises(RuntimeError):
        app.test_client().get('/boom')

    assert capsys.readouterr().out == (
        'app.request request method=GET route=/boom status=500 bytes=- '
        'ms=500.0\n')


def test_a_hook_failing_after_this_one_gives_one_line_with_the_status_sent(
        capsys, steady_clock):
    """Flask answers a failing after_request hook by building a 500 and
    running every hook again. One line, carrying the 500 the client got --
    not a 200 line and then a 500 line. (`ms` is 1000.0 because the second
    pass read the clock again.)"""
    app = _app()

    @app.after_request              # registered first, so it runs after ours
    def fail(response):
        raise RuntimeError('a later hook failed')

    assert request_timing.install(app, env=ON)
    response = app.test_client().get('/radar/api/ticker/NVDA')

    assert response.status_code == 500
    assert capsys.readouterr().out == (
        'app.request request method=GET route=/radar/api/ticker/<ticker> '
        f'status=500 bytes={len(response.data)} ms=1000.0\n')


def test_a_streamed_body_is_neither_counted_nor_consumed(capsys, steady_clock,
                                                         listen):
    """No Content-Length, so `bytes=-` -- and the line is written before the
    first chunk exists: counting the body would have meant reading it."""
    events = []

    def body():
        for chunk in ('first,', 'second'):
            events.append(chunk)
            yield chunk

    app = _app()

    @app.route('/stream')
    def stream():
        return Response(body(), mimetype='text/plain')

    assert request_timing.install(app, env=ON)
    listen('app.request', events=events)
    response = app.test_client().get('/stream')

    assert response.get_data(as_text=True) == 'first,second'
    assert events == ['line', 'first,', 'second']
    assert capsys.readouterr().out == (
        'app.request request method=GET route=/stream status=200 bytes=- '
        'ms=500.0\n')


def test_a_method_outside_the_standard_seven_is_other(capsys, steady_clock):
    """The method is the one field a client spells freely, so it gets a
    vocabulary too -- the rule board_metrics.py keeps for the same reason."""
    app = _app()
    assert request_timing.install(app, env=ON)

    response = app.test_client().open('/radar/api/ticker/NVDA',
                                      method='PROPFIND')

    assert response.status_code == 405
    assert capsys.readouterr().out == (
        'app.request request method=<other> route=<unmatched> '
        f'status=405 bytes={len(response.data)} ms=500.0\n')


def test_ms_is_real_elapsed_time_to_one_decimal(capsys):
    app = _app()

    @app.route('/slow')
    def slow():
        time.sleep(0.02)
        return 'ok'

    assert request_timing.install(app, env=ON)
    app.test_client().get('/slow')

    line = capsys.readouterr().out
    match = re.fullmatch(r'app\.request request method=GET route=/slow '
                         r'status=200 bytes=2 ms=(\d+\.\d)\n', line)
    assert match, line
    assert float(match.group(1)) >= 20.0


# --- output ------------------------------------------------------------------

def test_board_lines_reach_stdout_when_on(capsys):
    assert request_timing.install(_app(), env=ON)

    _log_a_read()
    board_metrics.log_build(key='0123456789abcdef', cls='ondemand',
                            queue_wait=2.5, build_ms=5012,
                            payload_bytes=13000, result='published')

    assert capsys.readouterr().out == (
        BOARD_READ + '\n'
        'radar.board board build key=0123456789ab class=ondemand '
        'queue_wait=2.5 build_ms=5012 payload_bytes=13000 result=published\n')


def test_a_line_is_printed_once_and_reaches_no_other_handler(capsys,
                                                            steady_clock,
                                                            listen):
    """Propagation is cut on both loggers. Without that, the producer's
    basicConfig handler on the root would print every board line a second
    time, and `app.request` -- a child of Flask's own `app` logger, since the
    app's import name is `app` -- would reach that logger's handler too."""
    root = listen(None)
    flask_app_logger = listen('app')
    app = _app()
    assert request_timing.install(app, env=ON)

    app.test_client().get('/radar/api/ticker/NVDA')
    _log_a_read()

    assert [record.name for record in root.records
            if record.name in LOGGERS] == []
    assert flask_app_logger.records == []
    assert capsys.readouterr().out == TICKER_LINE + BOARD_READ + '\n'


def test_install_twice_adds_one_handler_and_one_set_of_hooks(capsys,
                                                            steady_clock):
    app, other = _app(), _app()
    before = {name: _state(name)[0] for name in LOGGERS}

    assert request_timing.install(app, env=ON)
    assert request_timing.install(app, env=ON)
    assert request_timing.install(other, env=ON)

    added = {name: [handler for handler in logging.getLogger(name).handlers
                    if handler not in before[name]]
             for name in LOGGERS}
    assert [len(handlers) for handlers in added.values()] == [1, 1]
    assert added['app.request'][0] is added['radar.board'][0]
    assert len(_hooks(app)) == 3
    assert len(_hooks(other)) == 3

    app.test_client().get('/radar/api/ticker/NVDA')
    assert capsys.readouterr().out == TICKER_LINE
