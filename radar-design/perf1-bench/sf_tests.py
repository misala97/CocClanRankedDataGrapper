def _single_flight_setup(api_mod, build):
    """Shared scaffolding: a patched build and clean single-flight globals."""
    import datetime as dt
    api_mod.board_cache.clear()
    api_mod._board_builds.clear()
    now = dt.datetime(2026, 9, 10, 12, 0, 0)
    return api_mod.parse_query({'market': 'us'}, now=now), now


def test_two_readers_of_one_board_build_it_once(monkeypatch):
    """The second reader waits for the first's board, it does not build a
    second copy of it.

    Measured 2026-09-10 on a production-scale copy: one reader built the 24h
    All-companies board in 5.91s and two concurrent readers took 8.02s and
    7.87s, past the point where the island gives up.

    NOTE this only engages under THREADED workers. The target runs
    `gunicorn --workers 2` with no `--threads`, which is two single-threaded
    sync processes -- two readers land in two processes and never share this
    dict. See the comment on `_board_builds`.
    """
    import threading
    from app import app as flask_app
    from features.radar.routes import api as api_mod

    builds = []
    first_inside = threading.Event()
    release = threading.Event()

    def slow_build(*args, **kwargs):
        builds.append(1)
        first_inside.set()
        release.wait(5)
        return 'THE BOARD'

    monkeypatch.setattr(api_mod.board_mod, 'build', slow_build)
    query, now = _single_flight_setup(api_mod, slow_build)
    got = {}

    def reader(name):
        with flask_app.app_context():
            got[name] = api_mod._build_board(query, now)

    first = threading.Thread(target=reader, args=('first',))
    first.start()
    assert first_inside.wait(5), 'the first reader never entered the build'

    second = threading.Thread(target=reader, args=('second',))
    second.start()
    # The second reader is parked on the first one's event. Let it finish.
    release.set()
    first.join(10)
    second.join(10)

    assert got == {'first': 'THE BOARD', 'second': 'THE BOARD'}
    assert len(builds) == 1, 'the board was built %d times' % len(builds)
    assert api_mod._board_builds == {}, 'a build entry outlived its build'


def test_the_board_is_cached_before_the_waiters_are_woken(monkeypatch):
    """The order of those two steps is the whole of the single-flight.

    A waiter wakes on the event and immediately reads the cache. If the event
    fires first, the waiter wakes to an empty cache and builds a duplicate --
    intermittently, only under load.

    This instruments `Event.set` itself, not the bookkeeping around it. An
    earlier version of this test watched `_board_builds.pop`, which happens
    after the cache write in BOTH the correct and the broken ordering: an
    independent review reintroduced the bug and this test passed twenty times
    out of twenty. Watch the thing whose order actually matters.
    """
    import threading
    from app import app as flask_app
    from features.radar.routes import api as api_mod

    seen = {}

    class WatchingEvent(threading.Event):
        def set(self):
            seen.setdefault('cached_when_woken',
                            bool(api_mod.board_cache))
            super().set()

    class Threading:
        Event = WatchingEvent

    monkeypatch.setattr(api_mod.board_mod, 'build',
                        lambda *a, **k: 'THE BOARD')
    # `_build_board` uses the module only for Event(); the lock already exists.
    monkeypatch.setattr(api_mod, 'threading', Threading)
    query, now = _single_flight_setup(api_mod, None)

    with flask_app.app_context():
        assert api_mod._build_board(query, now) == 'THE BOARD'

    assert seen.get('cached_when_woken') is True, (
        'the waiters were woken before the board reached the cache')


def test_a_failed_build_wakes_its_waiter_instead_of_parking_it(monkeypatch):
    """A raising build must not hold the next reader for BUILD_WAIT seconds,
    and must not leave its claim behind."""
    import threading
    import time
    from app import app as flask_app
    from features.radar.routes import api as api_mod

    calls = []
    first_inside = threading.Event()
    release = threading.Event()

    def build(*args, **kwargs):
        calls.append(len(calls))
        if len(calls) == 1:
            first_inside.set()
            release.wait(5)
            raise RuntimeError('the first build failed')
        return 'THE SECOND BOARD'

    monkeypatch.setattr(api_mod.board_mod, 'build', build)
    monkeypatch.setattr(api_mod, 'BUILD_WAIT', 30.0)   # must never be reached
    query, now = _single_flight_setup(api_mod, build)
    got, failed = {}, []

    def reader(name):
        with flask_app.app_context():
            try:
                got[name] = api_mod._build_board(query, now)
            except RuntimeError:
                failed.append(name)

    first = threading.Thread(target=reader, args=('first',))
    first.start()
    assert first_inside.wait(5)
    second = threading.Thread(target=reader, args=('second',))
    second.start()

    release.set()
    first.join(10)
    began = time.perf_counter()
    second.join(10)
    waited = time.perf_counter() - began

    assert failed == ['first'], 'the failure did not reach its own request'
    assert got == {'second': 'THE SECOND BOARD'}
    assert waited < 5, 'the waiter was parked for %.1fs' % waited
    assert api_mod._board_builds == {}, 'the failed build left its claim'


def test_a_failed_build_does_not_start_a_herd(monkeypatch):
    """One failure plus four waiters is two builds, not five.

    Falling through to an unclaimed build was a thundering herd: every waiter
    woke, found an empty cache, and built -- and because none of them claimed
    the key, each new arrival started another. An independent review measured
    five concurrent builds for one failing builder and four waiters, at the
    one moment the database was already unhealthy.
    """
    import threading
    from app import app as flask_app
    from features.radar.routes import api as api_mod

    running = []
    peak = []
    lock = threading.Lock()
    first_inside = threading.Event()
    release = threading.Event()
    calls = []

    def build(*args, **kwargs):
        with lock:
            calls.append(1)
            running.append(1)
            peak.append(len(running))
            mine = len(calls)
        try:
            if mine == 1:
                first_inside.set()
                release.wait(5)
                raise RuntimeError('the first build failed')
            return 'THE BOARD'
        finally:
            with lock:
                running.pop()

    monkeypatch.setattr(api_mod.board_mod, 'build', build)
    query, now = _single_flight_setup(api_mod, build)
    failures = []

    def reader():
        with flask_app.app_context():
            try:
                api_mod._build_board(query, now)
            except RuntimeError:
                failures.append(1)

    first = threading.Thread(target=reader)
    first.start()
    assert first_inside.wait(5)
    waiters = [threading.Thread(target=reader) for _ in range(4)]
    for thread in waiters:
        thread.start()
    release.set()
    first.join(15)
    for thread in waiters:
        thread.join(15)

    assert len(failures) == 1
    assert max(peak) == 1, 'builds overlapped: %d at once' % max(peak)
    assert len(calls) == 2, (
        'one failure and four waiters made %d builds' % len(calls))
    assert api_mod._board_builds == {}


def test_a_hung_build_does_not_poison_the_key_forever(monkeypatch):
    """A build that never returns and never raises must cost BUILD_WAIT once,
    not for every reader from then on.

    Its `finally` never runs, so its claim stands until a waiter's timeout
    clears it. Before that timeout cleared the claim, one hung build meant
    every later reader of that selection paid the full wait, indefinitely --
    strictly worse than the code it replaced, which cost only the hung request.
    """
    import threading
    import time
    from app import app as flask_app
    from features.radar.routes import api as api_mod

    hang = threading.Event()
    calls = []

    def build(*args, **kwargs):
        calls.append(len(calls))
        if len(calls) == 1:
            hang.wait(30)          # neither returns nor raises
            return 'TOO LATE'
        return 'THE BOARD'

    monkeypatch.setattr(api_mod.board_mod, 'build', build)
    monkeypatch.setattr(api_mod, 'BUILD_WAIT', 0.4)
    query, now = _single_flight_setup(api_mod, build)
    got = {}

    def reader(name):
        with flask_app.app_context():
            got[name] = api_mod._build_board(query, now)

    hung = threading.Thread(target=reader, args=('hung',), daemon=True)
    hung.start()
    time.sleep(0.15)               # let it take the claim

    second = threading.Thread(target=reader, args=('second',))
    second.start()
    second.join(10)

    began = time.perf_counter()
    third = threading.Thread(target=reader, args=('third',))
    third.start()
    third.join(10)
    third_waited = time.perf_counter() - began

    assert got.get('second') == 'THE BOARD'
    assert got.get('third') == 'THE BOARD'
    assert third_waited < 0.4, (
        'the third reader paid the timeout too: %.2fs' % third_waited)
    hang.set()
