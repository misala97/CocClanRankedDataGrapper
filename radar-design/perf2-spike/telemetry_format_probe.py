"""What the proposed gunicorn access-log format does and does not emit.

Runs gunicorn's OWN Logger.atoms and its SafeAtoms formatting. `gunicorn.util`
imports fcntl, pwd and grp at module scope and Windows has none of them, so
three stub modules go into sys.modules first; atoms() is pure string work and
calls into none of the stubbed functions. The line this prints is gunicorn's
output, not a reimplementation of it.

Touches no database and opens no connection. Run it from anywhere:

    python radar-design/perf2-spike/telemetry_format_probe.py

Backs radar-design/PERF2-TELEMETRY.md.
"""
import datetime
import sys
import types

_STUBS = {
    'fcntl': {'fcntl': lambda *a, **k: 0, 'F_GETFD': 1, 'F_SETFD': 2,
              'FD_CLOEXEC': 1},
    'pwd': {'getpwnam': lambda n: types.SimpleNamespace(pw_uid=0, pw_gid=0),
            'getpwuid': lambda u: types.SimpleNamespace(pw_name='root',
                                                        pw_uid=0, pw_gid=0)},
    'grp': {'getgrnam': lambda n: types.SimpleNamespace(gr_gid=0),
            'getgrgid': lambda g: types.SimpleNamespace(gr_name='root',
                                                        gr_gid=0)},
}
for _name, _attrs in _STUBS.items():
    _module = types.ModuleType(_name)
    for _key, _value in _attrs.items():
        setattr(_module, _key, _value)
    sys.modules.setdefault(_name, _module)

import gunicorn                       # noqa: E402
import gunicorn.glogging as glogging  # noqa: E402

# The proposal. `%(U)s` is the path WITHOUT the query string; `%(r)s` is the
# request line WITH it, and is the obvious-looking wrong choice.
FORMAT = '%(t)s %(m)s %(U)s %(s)s %(B)s %(L)s'

QUERY = 'sources=bluesky,fourchan,reddit&window=24&segment=&market=us&t=GME'


def _atoms(path, query, headers, environ_extra, seconds=4.512):
    class Req:
        method = 'GET'
        remote_addr = '203.0.113.44'

    Req.path = path
    Req.query = query
    Req.headers = headers

    class Resp:
        status = '200 OK'
        status_code = 200
        response_length = 148213
        sent = 148213
        headers = [('CONTENT-TYPE', 'application/json')]

    environ = {
        'REQUEST_METHOD': 'GET', 'PATH_INFO': path, 'QUERY_STRING': query,
        'RAW_URI': path + ('?' + query if query else ''),
        'SERVER_PROTOCOL': 'HTTP/1.1', 'REMOTE_ADDR': '203.0.113.44',
    }
    environ.update(environ_extra)
    logger = glogging.Logger.__new__(glogging.Logger)
    return glogging.Logger.atoms(
        logger, Resp, Req, environ,
        datetime.timedelta(seconds=int(seconds),
                           microseconds=round(seconds % 1 * 1_000_000)))


def main():
    print('gunicorn', gunicorn.__version__)
    print()

    atoms = _atoms(
        '/radar/api/board', QUERY,
        [('COOKIE', 'session=eyJfZnJlc2giOnRydWV9.aBcDeF.SECRETSESSIONVALUE'),
         ('AUTHORIZATION', 'Bearer supersecrettoken'),
         ('USER-AGENT', 'Mozilla/5.0 (Windows NT 10.0)'),
         ('REFERER', 'https://mgemmel.viewdns.net/radar/?t=GME')],
        {'HTTP_COOKIE': 'session=SECRETSESSIONVALUE',
         'HTTP_AUTHORIZATION': 'Bearer supersecrettoken',
         'HTTP_X_FORWARDED_FOR': '198.51.100.7'})

    print('FORMAT :', FORMAT)
    print('LINE   :', FORMAT % glogging.SafeAtoms(atoms))
    print()
    print('--- present in the request, NOT referenced by the format ---')
    for key in sorted(atoms):
        if ('%(' + key + ')s') in FORMAT:
            continue
        if key in ('h', 'r', 'q', 'f', 'a') or key.startswith('{'):
            print(f'  {key!r:26} = {str(atoms[key])[:72]!r}')

    print()
    print('--- line size, same formatter, representative paths ---')
    paths = ['/radar/', '/radar/api/board', '/radar/api/ticker/WOLF',
             '/radar/hub/', '/radar/api/activity', '/radar/api/ops',
             '/static/radar/assets/board-DxK3nQ12.js', '/gym/']
    total = 0
    for path in paths:
        line = FORMAT % glogging.SafeAtoms(_atoms(path, 'x=1', [], {}))
        size = len(line.encode()) + 1          # the newline is stored too
        total += size
        print(f'  {size:4d} bytes  {line}')
    mean = total / len(paths)
    print(f'\n  mean over {len(paths)} paths: {mean:.1f} bytes/line')
    for rate in (1_000, 5_000, 20_000, 100_000):
        print(f'  {rate:>7,} req/day -> {rate * mean / 1048576:6.2f} MB/day, '
              f'{rate * mean * 14 / 1048576:7.2f} MB over 14 days')


if __name__ == '__main__':
    main()
