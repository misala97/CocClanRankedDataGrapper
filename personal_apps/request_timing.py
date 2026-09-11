"""One line per request, named by the route it matched and never by its URL.

Off unless `PERSONAL_REQUEST_TIMING_LOG` is truthy (`1`, `true`, `yes`, `on`),
and off means absent: `install` registers no hook and touches no logger, so a
process that does not set the variable runs exactly what it ran before.

On, every request writes one INFO line on `app.request`:

    request method=GET route=/radar/api/ticker/<ticker> status=200 bytes=2048 ms=41.3

`route` is the matched rule's TEMPLATE, not the path. A path without its query
string still carries what a person chose -- `/radar/api/ticker/NVDA` is
somebody's ticker -- and gunicorn's access-log atoms can print only the path;
the template is the one label the application has and the server does not. A
request no rule matched is `<unmatched>`, whatever it asked for, and every
static file, the app's and each blueprint's, is `<static>`: a file name is as
much a value as a ticker.

Every field is a closed vocabulary or a number, the rule board_metrics.py
keeps and for the same reason. The method is one of the standard seven or
`<other>` -- it is the one field a client spells freely -- the status and the
size are integers, and `ms` is elapsed time by `perf_counter` from
before_request. The query string, cookies, headers, the client address, the
session and the account are not merely left off the line: nothing here reads
them.

`bytes` is the response's Content-Length when the response already knows it,
and `-` when it does not. A streamed body is not read to be counted.

The line is written at teardown, from what after_request noted. Teardown runs
once for every request, including one that raised past Flask's own handling
(PROPAGATE_EXCEPTIONS, as in debug and testing): that request never reaches
after_request and is logged as `status=500 bytes=-`. And when a later
after_request hook fails, Flask builds a 500 and runs the hooks again; the
second note replaces the first, so the line carries what the client was sent.

Output is stdout, so journald keeps it. `install` hangs one plain handler on
`app.request` AND on `radar.board`, and the second is half the point.
board_metrics.py writes a line per board read in the web process, where
nothing configures a handler -- gunicorn sets up only its own `gunicorn.*`
loggers -- so `radar.board` inherited the root's WARNING and every read line
was dropped unformatted. (The producer calls basicConfig itself; its build
lines always reached the journal.) Propagation is cut on both, so each line is
printed once: otherwise the producer's basicConfig handler would repeat every
board line, and `app.request` would also reach Flask's own logger `app`, whose
child it is because the app's import name is `app`.

Rollback is unsetting the variable and restarting. Nothing here writes a file,
so there is nothing to delete.
"""
import logging
import os
import sys
import time

from flask import request

ENV_VAR = 'PERSONAL_REQUEST_TIMING_LOG'

# Both loggers the handler goes on: this module's, and the board's.
LOGGER_NAMES = ('app.request', 'radar.board')

logger = logging.getLogger('app.request')

_TRUTHY = ('1', 'true', 'yes', 'on')
_METHODS = ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS')

# Per-request state goes in the WSGI environ, which belongs to this request
# alone. Not `g`: a caller holding an app context open shares one `g` across
# every request it makes.
_STARTED = 'personal_apps.request_timing.started'
_NOTED = 'personal_apps.request_timing.noted'

# Names the one handler `install` makes, so a second call finds it, and marks
# an app that already has the hooks.
_MARK = 'personal_apps_request_timing'

# The clock, by name, so a test can make every request take the same time.
_clock = time.perf_counter


def enabled(env=os.environ):
    """Whether `env` turns the line on. Anything but the four words is off."""
    return (env.get(ENV_VAR) or '').strip().lower() in _TRUTHY


def install(app, env=os.environ):
    """The hooks and the stdout handler, or nothing at all; returns which.

    Safe to call twice: the handler is found rather than made again, and an
    app that already has the hooks does not get a second set, which would
    write every line twice.
    """
    if not enabled(env):
        return False
    _attach_stdout_handler()
    if _MARK not in app.extensions:
        app.before_request(_start)
        app.after_request(_note)
        app.teardown_request(_write)
        app.extensions[_MARK] = True
    return True


def _start():
    request.environ[_STARTED] = _clock()


def _note(response):
    request.environ[_NOTED] = (response.status_code, response.content_length,
                               _elapsed_ms())
    return response


def _write(exc):
    noted = request.environ.pop(_NOTED, None)
    if noted is None:                  # after_request never ran: it raised
        noted = (500, None, _elapsed_ms())
    status, size, ms = noted
    logger.info('request method=%s route=%s status=%s bytes=%s ms=%s',
                _method(), _route(), status,
                '-' if size is None else size,
                '-' if ms is None else f'{ms:.1f}')


def _elapsed_ms():
    """Milliseconds since `_start`, or None for a request it never saw."""
    started = request.environ.get(_STARTED)
    return None if started is None else (_clock() - started) * 1000


def _method():
    method = request.method
    return method if method in _METHODS else '<other>'


def _route():
    rule = request.url_rule
    if rule is None:
        return '<unmatched>'
    if rule.endpoint == 'static' or rule.endpoint.endswith('.static'):
        return '<static>'
    return rule.rule


def _attach_stdout_handler():
    handler = _installed_handler()
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter('%(name)s %(message)s'))
        setattr(handler, _MARK, True)
    for name in LOGGER_NAMES:
        target = logging.getLogger(name)
        target.addHandler(handler)          # a no-op when it is already there
        # A handler at INFO is not enough on its own: the logger's level
        # decides first, and unset it is the root's WARNING.
        if target.getEffectiveLevel() > logging.INFO:
            target.setLevel(logging.INFO)
        target.propagate = False


def _installed_handler():
    for name in LOGGER_NAMES:
        for handler in logging.getLogger(name).handlers:
            if getattr(handler, _MARK, False):
                return handler
    return None
