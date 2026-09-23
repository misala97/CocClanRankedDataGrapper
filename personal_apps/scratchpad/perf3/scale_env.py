"""Bind a process to the PERF3 scale database, whatever the worktree .env says.

`app.py` calls `load_dotenv(override=True)`, so the worktree `.env` (which
names the TEST database) silently replaces any `PERSONAL_DB_NAME` a script
sets in its environment. An environment variable therefore cannot select the
database, and every Task 8 process goes through this module instead:

1. the worktree `.env` is loaded by explicit path WITHOUT override, for the
   credentials only;
2. `dotenv.load_dotenv` is replaced with a no-op before `app` is imported, so
   nothing later can re-point the process;
3. `PERSONAL_DB_NAME` is set to the scale database, and `RADAR_BUILD_REVISION`
   to one fixed commit, because the cache namespace derives from the build
   revision and the git fallback reads HEAD -- a commit made while a
   measurement runs would move the namespace under the running processes and
   turn every board into a miss;
4. `features.radar.config.REDDIT_SUBS` is replaced by the fixture's OWN
   subreddit names, read with a direct pymysql query before the app exists.
   The fixture stores placeholders (`reddit:sub03`..`sub32` beside three real
   names); config holds real names, so the producer's derived warm set would
   expand the root `reddit` to names the fixture mostly lacks and aggregate a
   fraction of the rows -- the trap PERF1 had to retract. `expand_sources`
   reads the module global at call time, and the patch happens before `app`
   is imported, so `routes.api.MAX_SOURCES` (bound at import) agrees too;
5. before the first database connection, the exact host/port/database must
   pass `RADAR_DESTRUCTIVE_TEST_TARGET` and an independently provisioned
   registry; after import the engine is checked against the same registration;
6. after the import, `db.engine.url.database` is asserted, and so is the
   coverage of the warm set's expanded sources over the 24h window.

Two ways in:

    import scale_env; scale_env.bind()                       # a script
    <python 3.12> scratchpad/perf3/scale_env.py <script.py> [args...]

The second is how every subprocess is launched (producer, web-model workers,
`serve_perf3.py`): it binds, prints the block below, then runs the target with
`runpy.run_path` and the remaining argv. The interpreter is named directly
rather than through `py -3.12`: `py.exe` is a launcher that runs python.exe as
its CHILD, so killing it would orphan the real process and its working set
would be the launcher's few megabytes.

Never edit `.env` for this.
"""
import datetime as dt
import os
import pathlib
import runpy
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
APP_DIR = HERE.parents[1]
WORKTREE = APP_DIR.parent
ENV_FILE = WORKTREE / '.env'

SCALE_DB = 'personal_apps_radar_perf3_scale'
# The one revision every process of a run uses: HEAD when Task 8a was
# dispatched, unless the parent pins its own through PERF3_REVISION (Task 8b
# pins the HEAD it started from). Children inherit it with the rest of the
# parent's environment, so a run cannot straddle two namespaces.
REVISION = (os.environ.get('PERF3_REVISION')
            or '0b50952459fb009a710520f163bc92fcdfd968f6')
if len(REVISION) != 40 or any(c not in '0123456789abcdef' for c in REVISION):
    raise SystemExit(f'PERF3_REVISION {REVISION!r} is not a full commit hash')
# Databases a Task 8 process must never be bound to.
REFUSED = ('personal_apps', 'personal_apps_radar_perf1',
           'personal_apps_radar_perf3')

_STATE = {}


def _no_dotenv(*args, **kwargs):
    """What `dotenv.load_dotenv` becomes once this process is bound."""
    return False


def utcnow():
    """Naive UTC, the codebase's convention."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def credentials():
    """The connection settings `app.py` would use, with its own defaults."""
    return dict(host=os.environ.get('DB_HOST', 'localhost'),
                user=os.environ.get('DB_USER', 'root'),
                password=os.environ.get('DB_PASS', ''), port=3306)


def fixture_reddit_subs():
    """The fixture's DISTINCT `reddit:%` names, bare, read before `app`."""
    import pymysql
    connection = pymysql.connect(database=SCALE_DB, **credentials())
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT DISTINCT source FROM radar_bucket_sources'
                ' WHERE source LIKE %s ORDER BY source', ('reddit:%',))
            names = [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()
    subs = tuple(name[len('reddit:'):] for name in names)
    if not subs:
        raise SystemExit('the scale fixture holds no reddit:% rows')
    return subs


def _check_bound_names(config, subs):
    """Every loaded radar module that bound REDDIT_SUBS agrees with the patch."""
    from features.radar.routes import api
    if api.REDDIT_SUBS is not subs:
        raise SystemExit('routes.api bound REDDIT_SUBS before the patch')
    if api.MAX_SOURCES != len(config.SOURCES) + len(subs):
        raise SystemExit('routes.api.MAX_SOURCES disagrees with the patch')
    for name, module in list(sys.modules.items()):
        if not name.startswith('features.radar') or module is None:
            continue
        bound = getattr(module, 'REDDIT_SUBS', None)
        if bound is not None and tuple(bound) != subs:
            raise SystemExit(f'{name}.REDDIT_SUBS disagrees with the patch')


def coverage(app, db, config, now):
    """(sources, expanded names, covered, total) for the 24h window.

    `total` is every radar_bucket_sources row in [now - 24h, now); `covered`
    is the rows whose source is in `expand_sources` of the warm set's own
    sources. Equal and non-zero is the only acceptable answer.
    """
    import sqlalchemy as sa
    from features.radar import board_producer
    sources = sorted({source for query in board_producer.warm_queries(now)
                      for source in query.sources})
    expanded = config.expand_sources(sources)
    since = now - dt.timedelta(hours=24)
    with app.app_context():
        with db.engine.connect() as connection:
            total = connection.execute(sa.text(
                'SELECT COUNT(*) FROM radar_bucket_sources'
                ' WHERE bucket_start >= :since AND bucket_start < :now'),
                {'since': since, 'now': now}).scalar()
            covered = connection.execute(sa.text(
                'SELECT COUNT(*) FROM radar_bucket_sources'
                ' WHERE bucket_start >= :since AND bucket_start < :now'
                ' AND source IN :names').bindparams(
                    sa.bindparam('names', expanding=True)),
                {'since': since, 'now': now, 'names': expanded}).scalar()
    return sources, len(expanded), covered, total


def bind(label=None, *, require_window=True):
    """Bind this process to the scale database once; return the Flask app.

    `require_window=False` is for the fixture-alignment script alone, which
    runs precisely because the window may be empty.
    """
    if _STATE.get('app') is not None:
        return _STATE['app']
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    started = time.perf_counter()

    import dotenv
    if not ENV_FILE.is_file():
        raise SystemExit(f'no worktree .env at {ENV_FILE}')
    dotenv.load_dotenv(ENV_FILE, override=False)
    dotenv.load_dotenv = _no_dotenv

    os.environ['PERSONAL_DB_NAME'] = SCALE_DB
    os.environ['RADAR_BUILD_REVISION'] = REVISION
    os.environ.setdefault('RADAR_BOARD_SHARED_RESULTS', 'on')
    for path in (str(APP_DIR), str(HERE)):
        if path not in sys.path:
            sys.path.insert(0, path)

    # The connection settings say where this process points; they do not
    # authorize touching it. Require the separately supplied opt-in and
    # registry before fixture_reddit_subs opens the first connection.
    import sqlalchemy as sa
    import destructive_target
    settings = credentials()
    preflight_url = sa.engine.URL.create(
        'mysql+pymysql', username=settings['user'],
        password=settings['password'], host=settings['host'],
        port=settings['port'], database=SCALE_DB)
    try:
        destructive_target.require(preflight_url)
    except destructive_target.DestructiveTargetRefused as exc:
        raise SystemExit(str(exc)) from exc

    subs = fixture_reddit_subs()
    from features.radar import config
    config.REDDIT_SUBS = subs

    from app import app
    from extensions import db
    with app.app_context():
        # The Engine outlives the context it was looked up in; scripts use
        # it through `engine()` without holding a context for the store.
        bound_engine = db.engine
        bound = bound_engine.url.database
    _STATE['engine'] = bound_engine
    if bound != SCALE_DB or bound in REFUSED:
        raise SystemExit(f'bound to {bound!r}, refusing: only {SCALE_DB}')
    try:
        destructive_target.require(bound_engine.url)
    except destructive_target.DestructiveTargetRefused as exc:
        raise SystemExit(str(exc)) from exc
    _check_bound_names(config, subs)

    from features.radar import board_namespace
    described = board_namespace.describe()
    if described['revision'] != REVISION:
        raise SystemExit(f"namespace revision {described['revision']} is not"
                         f' the fixed {REVISION}')

    now = utcnow()
    sources, expanded, covered, total = coverage(app, db, config, now)
    if require_window and (total == 0 or covered != total):
        raise SystemExit(
            f'warm-set coverage of the 24h window is {covered} of {total}'
            ' rows: align the fixture (align_scale_fixture.py) first')

    _STATE.update(app=app, namespace=described['namespace'],
                  revision=described['revision'],
                  fingerprint=described['fingerprint'], subs=subs,
                  coverage=(covered, total), sources=sources)
    share = '100%' if total and covered == total else (
        f'{100.0 * covered / total:.1f}%' if total else 'EMPTY WINDOW')
    print('-' * 72)
    print(f'BIND {label or pathlib.Path(sys.argv[0]).name}  pid={os.getpid()}'
          f'  python={sys.executable} {sys.version.split()[0]}')
    print(f'  database   {bound}  (asserted after import; target runs '
          'MariaDB 10.11.14 -- seconds do not transfer)')
    print(f"  revision   {described['revision']}  (fixed for every process)")
    print(f"  namespace  {described['namespace']}  fingerprint "
          f"{described['fingerprint']}")
    print('  flag       RADAR_BOARD_SHARED_RESULTS='
          f"{os.environ.get('RADAR_BOARD_SHARED_RESULTS')}")
    print(f'  reddit     REDDIT_SUBS patched to the fixture\'s own {len(subs)}'
          f' names ({subs[0]} .. {subs[-1]}); warm sources {sources}'
          f' expand to {expanded} names')
    print(f'  coverage   {covered:,} of {total:,} radar_bucket_sources rows in'
          f' the 24h window at {now:%Y-%m-%d %H:%M:%S} UTC = {share}')
    print(f'  bound in   {time.perf_counter() - started:.2f} s')
    print('-' * 72, flush=True)
    return app


def namespace():
    """The namespace this process resolved (after `bind`)."""
    return _STATE['namespace']


def engine():
    """The scale database's Engine (after `bind`)."""
    return _STATE['engine']


def state():
    """What `bind` found, for the preflight block."""
    return dict(_STATE)


def main(argv):
    if len(argv) < 2:
        raise SystemExit('usage: scale_env.py <script.py> [args...]')
    target = pathlib.Path(argv[1])
    if not target.is_absolute():
        for base in (pathlib.Path.cwd(), APP_DIR, HERE):
            if (base / target).is_file():
                target = base / target
                break
    if not target.is_file():
        raise SystemExit(f'no such script: {argv[1]}')
    # `import scale_env` inside the target must find THIS module, bound.
    sys.modules['scale_env'] = sys.modules[__name__]
    # Subprocess logs carry a UTC time, so a producer's build lines can be
    # set beside the moments a measurement wrote something. The targets'
    # own `logging.basicConfig` calls become no-ops after this one; the
    # messages themselves are untouched.
    import logging
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        level=logging.INFO, datefmt='%H:%M:%S',
        format='%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s %(message)s')
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    bind(label=' '.join([target.name] + argv[2:]))
    sys.argv = [str(target)] + list(argv[2:])
    runpy.run_path(str(target), run_name='__main__')


if __name__ == '__main__':
    main(sys.argv)
