"""The producer: one job at a time, fairly chosen, fenced, and idle with
nothing open.

Against the real disposable database, for the same reason the store's tests
are: the fence is an UPDATE that matches no rows, the backoff is a comparison
between two DATETIMEs, and the claim order is an ORDER BY. A fake store would
only prove this file agrees with itself.

The BOARD, on the other hand, is faked throughout. `board.build` is thirty
seconds of SQL against nine million bucket rows and none of it is what this
task got wrong; what this task can get wrong is which clock `as_of` is read
from, whether a lost lease can still publish, and whether the eight standing
boards can starve the queue or the queue the eight boards. So `board_mod.build`
becomes a deterministic stand-in (the shape `test_radar_board_cache.py`
established) and the three ops summaries become constants, which makes a
payload something a test can compare byte for byte.

Time is a `Clock` the test moves by hand -- including from inside the fake
build, which is the only way to assert that `as_of` is the instant the build
STARTED and `built_at` the instant it finished.
"""
import datetime as dt
import json
import logging
import re
import secrets
import threading
import time
import zlib

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import board as board_mod
from features.radar import (board_keys, board_metrics, board_producer,
                            board_store)
from features.radar.config import DEFAULT_SEGMENT, SOURCES
from features.radar.routes import api

DISPOSABLE = 'personal_apps_radar_perf3'

# One fixed instant. Naive UTC, the way every timestamp in these tables is.
NOW = dt.datetime(2026, 9, 10, 12, 0, 0)

REVISION = 'b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0'


def seconds(count):
    return dt.timedelta(seconds=count)


class Clock:
    """A wall clock the test moves by hand.

    Passed where the producer wants `now_fn`, so every timestamp it writes --
    `as_of`, `built_at`, a lease expiry, a backoff boundary -- is something
    this file decided rather than something it has to wait for.
    """

    def __init__(self, start=NOW):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, count):
        self.now += seconds(count)
        return self.now


def demand_query(index):
    """A legal on-demand selection nobody keeps warm.

    `segment=large` is outside DEFAULT_SEGMENT and the limit varies, so these
    can never collide with a warm key -- and they are REAL keys, which matters
    because the producer refuses to publish one that does not round-trip.
    """
    return api.parse_query({'market': 'us', 'segment': 'large', 'window': '1',
                            'limit': str(10 + index)}, now=NOW)


def demand_key(index):
    return board_keys.canonical(demand_query(index))


def warm_subset(monkeypatch, count):
    """The producer's own warm selections, narrowed to `count` of them.

    Narrowed rather than invented: these are the real eight, so
    `refresh_warm`, `claim` and `round_trips` all see exactly what production
    hands them. Eight warm rows adopted on every tick would swamp the
    scheduling tests, whose whole subject is the ratio between the two
    classes.
    """
    chosen = board_producer.warm_queries(NOW)[:count]
    monkeypatch.setattr(board_producer, 'warm_queries', lambda now: list(chosen))
    return chosen


def fake_build(monkeypatch, *, clock=None, advance=0, raises=None, before=None):
    """`board.build` as a deterministic stand-in, plus frozen ops summaries.

    `advance` moves the clock INSIDE the build, which is what separates
    `as_of` from `built_at`. `before` runs at the top of the build, which is
    how the overtaken test gets a second producer in edgeways.

    Returns the call log.
    """
    calls = []

    def build(sources, now, **kwargs):
        calls.append((tuple(sources), now, tuple(sorted(kwargs.items()))))
        if before is not None:
            before()
        if clock is not None and advance:
            clock.advance(advance)
        if raises is not None:
            raise raises
        return board_mod.Board(
            generated_at=now, market=kwargs.get('market', 'us'),
            display_timezone='Europe/Berlin', market_venue='US markets',
            next_boundary_label='closes', next_boundary_at=now,
            sources=list(sources), segments=list(kwargs.get('segments', ())),
            session='regular', min_venues=kwargs.get('min_venues', 1),
            venue_counts={'any': 0, 'multi': 0},
            window_hours=kwargs.get('window_hours', 12),
            segment_counts={}, excluded={}, rows=[],
            sort=kwargs.get('sort'), direction=kwargs.get('direction', 'desc'))

    monkeypatch.setattr(board_mod, 'build', build)
    monkeypatch.setattr(api.spend, 'summary', lambda: {'usd': 0})
    monkeypatch.setattr(api.llm_sentiment, 'ops_summary', lambda: {'backlog': 0})
    monkeypatch.setattr(api.market_data, 'ops_summary', lambda now: {'rows': 0})
    return calls


def broken_build(monkeypatch, exception=None):
    """A build that raises, leaving everything else about the fake alone."""
    problem = exception or RuntimeError('boom')

    def build(sources, now, **kwargs):
        raise problem

    monkeypatch.setattr(board_mod, 'build', build)
    return problem


class _Producer:
    """The engine plus the one namespace a test is allowed to touch."""

    def __init__(self, engine):
        self.engine = engine
        self.namespaces = []
        self.ns = self.namespace()

    def namespace(self, now=NOW):
        name = 'perf3prod-' + secrets.token_hex(20)
        self.namespaces.append(name)
        board_store.ensure_namespace(self.engine, name, now,
                                     revision=REVISION, payload_version=1)
        return name

    def loop(self, clock, **kwargs):
        return board_producer.Loop(self.engine, ns=self.ns, owner='owner-1',
                                   revision=REVISION, now_fn=clock, **kwargs)

    def serve(self, clock, *, prefer='warm', owner='owner-1'):
        return board_producer.serve_once(self.engine, self.ns, owner, clock,
                                         prefer=prefer, revision=REVISION)

    def admit(self, pair, now=NOW, **kwargs):
        return board_store.admit(self.engine, self.ns, pair[0], pair[1], now,
                                 **kwargs)

    def read(self, key_hash):
        return board_store.read(self.engine, self.ns, key_hash)

    def payload(self, key_hash):
        return json.loads(zlib.decompress(self.read(key_hash).payload))

    def row(self, key_hash):
        """The raw row, for the columns `Result` deliberately does not carry."""
        with self.engine.connect() as connection:
            return connection.execute(sa.text(
                'select * from radar_board_results'
                ' where namespace = :ns and key_hash = :k'),
                {'ns': self.ns, 'k': key_hash}).mappings().first()

    def rewrite_key_json(self, key_hash, key_json):
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                'update radar_board_results set key_json = :j'
                ' where namespace = :ns and key_hash = :k'),
                {'j': key_json, 'ns': self.ns, 'k': key_hash})


@pytest.fixture
def producer():
    """A namespace of this test's own, on the disposable database only."""
    with flask_app.app_context():
        if db.engine.url.database != DISPOSABLE:
            pytest.skip(f'not the disposable database: {db.engine.url.database}')
        engine = db.engine
        owned = _Producer(engine)
        try:
            yield owned
        finally:
            db.session.remove()
            with engine.begin() as connection:
                for name in owned.namespaces:
                    connection.execute(sa.text(
                        'delete from radar_board_results where namespace = :ns'),
                        {'ns': name})
                    connection.execute(sa.text(
                        'delete from radar_board_namespaces where namespace = :ns'),
                        {'ns': name})


# --- the warm set -----------------------------------------------------------

def test_the_warm_set_is_eight_selections_nobody_typed():
    """Two markets x (All | the default segments) x two windows, and every
    other field from the parser's own defaults.

    Typing `limit=50` here would be a second place for it to be wrong: the
    warm boards have to be the boards a bare URL asks for, and the only thing
    that knows what those are is the parser the URL goes through.
    """
    queries = board_producer.warm_queries(NOW)
    assert len(queries) == 8
    assert len({board_keys.canonical(q)[0] for q in queries}) == 8

    for query in queries:
        assert query.limit == 50
        assert query.min_venues == 1
        assert query.sort is None
        assert query.direction == 'desc'
        assert query.sources == list(SOURCES)

    default_segments = [name for name in DEFAULT_SEGMENT.split(',') if name]
    segments = [query.segments for query in queries]
    assert segments.count([]) == 4
    assert segments.count(default_segments) == 4
    assert sorted(query.market for query in queries) == ['de'] * 4 + ['us'] * 4
    assert sorted(query.window for query in queries) == [12] * 4 + [24] * 4


def test_the_warm_set_matches_the_number_readiness_compares_against():
    assert len(board_producer.warm_queries(NOW)) == board_store.limits().warm_limit


# --- one job ----------------------------------------------------------------

def test_serve_once_claims_builds_publishes_and_the_board_reads_back(
        producer, monkeypatch):
    clock = Clock()
    calls = fake_build(monkeypatch)
    query = warm_subset(monkeypatch, 1)[0]
    key_hash, key_json = board_keys.canonical(query)

    served = producer.loop(clock).tick(NOW)

    assert served == key_hash
    assert len(calls) == 1
    stored = producer.read(key_hash)
    assert stored.queue_state == 'idle'
    assert stored.as_of == NOW and stored.built_at == NOW
    assert stored.attempts == 0 and stored.last_error is None
    assert stored.lease_expires_at is None

    expected, as_of, built_at, build_ms, payload_bytes = \
        board_producer.build_blob(query, now=Clock())
    assert zlib.decompress(stored.payload) == zlib.decompress(expected)
    assert (as_of, built_at) == (NOW, NOW)
    assert payload_bytes == len(expected)
    assert producer.row(key_hash)['payload_bytes'] == len(expected)
    assert producer.row(key_hash)['producer_revision'] == REVISION


def test_the_stored_payload_carries_the_rooted_sources_and_the_ops_stamp(
        producer, monkeypatch):
    """`build_blob` reproduces `build_payload`'s rooting, and stamps the one
    field the frozen ops summaries need to be honest about their age."""
    clock = Clock()
    fake_build(monkeypatch)
    query = api.parse_query({'market': 'us', 'sources': 'reddit:wallstreetbets'},
                            now=NOW)
    blob, as_of, _, _, _ = board_producer.build_blob(query, now=clock)

    payload = json.loads(zlib.decompress(blob))
    assert payload['sources'] == ['reddit']
    assert payload['ops_collected_at'] == NOW.isoformat() + 'Z'
    assert payload['generated_at'] == NOW.isoformat() + 'Z'
    # Viewer-invariant: nothing per account is ever compressed into the blob.
    assert 'watching' not in payload and 'watch_rows' not in payload


def test_as_of_is_the_clock_at_the_start_of_the_build(producer, monkeypatch):
    """A board says what the world looked like when it was READ, not when it
    was finished being written down. Seven seconds of build sit between the
    two, and the stamps have to show them."""
    clock = Clock()
    fake_build(monkeypatch, clock=clock, advance=7)
    query = warm_subset(monkeypatch, 1)[0]
    key_hash, _ = board_keys.canonical(query)

    producer.loop(clock).tick()

    stored = producer.read(key_hash)
    assert stored.as_of == NOW
    assert stored.built_at == NOW + seconds(7)
    assert json.loads(zlib.decompress(stored.payload))['ops_collected_at'] == \
        NOW.isoformat() + 'Z'


def test_build_ms_is_elapsed_time_not_wall_clock(producer, monkeypatch):
    """`perf_counter`, because the wall clock can step sideways under NTP and
    a board that took -3 ms to build is a metric nobody can act on."""
    clock = Clock()
    fake_build(monkeypatch, clock=clock, advance=7)
    # The job's own reading first, then the build's two. Every one is far
    # away from the seven WALL-CLOCK seconds the fake build burns, which is
    # the point: they are different questions and different clocks.
    ticks = iter([50.0, 100.0, 100.25])
    monkeypatch.setattr(board_producer, 'perf_counter', lambda: next(ticks))
    query = warm_subset(monkeypatch, 1)[0]
    key_hash, _ = board_keys.canonical(query)

    producer.loop(clock).tick()

    assert producer.read(key_hash).build_ms == 250


# --- the round-trip guard ---------------------------------------------------

def test_a_key_that_no_longer_means_what_it_says_is_failed_not_published(
        producer, monkeypatch):
    """The stored json is re-canonicalised before anything is written under
    its hash. A row whose two halves disagree is a row that would serve one
    viewer another viewer's board, so it is failed and nothing is built."""
    clock = Clock()
    calls = fake_build(monkeypatch)
    pair = demand_key(0)
    producer.admit(pair)
    # A different LEGAL key -- the corruption a widened normalization or a
    # half-written column would produce, not a syntax error.
    producer.rewrite_key_json(pair[0], demand_key(1)[1])

    served = producer.serve(clock, prefer='demand')

    assert served == pair[0]
    assert calls == [], 'a key that does not round-trip must not be built'
    stored = producer.read(pair[0])
    assert stored.queue_state == 'failed'
    assert stored.last_error.startswith('KeyMismatch')
    assert stored.payload is None


# --- fair scheduling --------------------------------------------------------

def classes_of(served, warm_hashes):
    return [None if key is None else ('warm' if key in warm_hashes else 'demand')
            for key in served]


def test_the_two_classes_alternate_while_both_have_work(producer, monkeypatch):
    """Four standing boards due and six viewers waiting: one each, turn about,
    and the leftovers of whichever class outlasts the other follow."""
    clock = Clock()
    fake_build(monkeypatch)
    warm_hashes = {board_keys.canonical(query)[0]
                   for query in warm_subset(monkeypatch, 4)}
    for index in range(6):
        producer.admit(demand_key(index))

    loop = producer.loop(clock)
    served = [loop.tick(NOW) for _ in range(11)]

    assert classes_of(served, warm_hashes) == (
        ['warm', 'demand'] * 4 + ['demand', 'demand', None])


def test_the_mirror_case_alternates_too(producer, monkeypatch):
    clock = Clock()
    fake_build(monkeypatch)
    warm_hashes = {board_keys.canonical(query)[0]
                   for query in warm_subset(monkeypatch, 4)}
    for index in range(6):
        producer.admit(demand_key(index))

    loop = producer.loop(clock)
    loop.next_class = 'demand'
    served = [loop.tick(NOW) for _ in range(11)]

    assert classes_of(served, warm_hashes) == (
        ['demand', 'warm'] * 4 + ['demand', 'demand', None])


def test_the_preference_survives_a_class_that_had_nothing(producer, monkeypatch):
    """A tick that had to serve the other class does not spend its turn. The
    starved class is tried FIRST next time -- otherwise a busy queue and an
    alternating preference between them would let warm work slip a turn every
    time it happened to be a moment early."""
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 0)
    for index in range(3):
        producer.admit(demand_key(index))

    loop = producer.loop(clock)
    assert loop.next_class == 'warm'
    loop.tick(NOW)
    assert loop.next_class == 'warm', 'a starved preference must not rotate'


def test_a_sustained_mixed_run_starves_neither_class(producer, monkeypatch):
    """Forty builds with a new viewer arriving on every one of them.

    Two bounds, and they pull against each other. The standing boards must not
    age past twice their refresh interval, which costs the queue a slot every
    time one comes due; and the queue must not be made to wait for more than
    two builds per place in line, which is what strict alternation buys it.

    The demand bound is per PLACE IN LINE rather than a flat number of ticks:
    arrivals here match the service rate exactly, so every slot warm work
    takes leaves the queue one deeper for the rest of the run, and no fixed
    wait can hold. What alternation actually promises is that the queue gets
    at least every other build, and that is the bound asserted.
    """
    monkeypatch.setenv('RADAR_BOARD_REFRESH_SECONDS', '10')
    clock = Clock()
    fake_build(monkeypatch, clock=clock, advance=0.5)
    warm = warm_subset(monkeypatch, 2)
    warm_hashes = {board_keys.canonical(query)[0] for query in warm}

    loop = producer.loop(clock)
    served_classes = []
    warm_ages = []
    admitted_at = {}
    waits = []
    for index in range(40):
        pair = demand_key(index)
        producer.admit(pair, now=clock.now)
        admitted_at[pair[0]] = (index, _pending_demand(producer))

        served = loop.tick()
        assert served is not None, 'there was work and the producer took none'
        served_classes.append('warm' if served in warm_hashes else 'demand')
        if served not in warm_hashes:
            entered, position = admitted_at[served]
            waits.append((index - entered, position))
        for key_hash in warm_hashes:
            stored = producer.read(key_hash)
            if stored is not None and stored.as_of is not None:
                warm_ages.append((clock.now - stored.as_of).total_seconds())

    assert served_classes.count('warm') >= 2, 'the warm sweep never ran'
    assert max(warm_ages) <= 2 * 10, (
        f'a standing board aged to {max(warm_ages)}s past a 10s refresh')
    assert all(wait <= 2 * position for wait, position in waits), (
        f'a viewer waited more than two builds per place in line: {waits}')
    # The mechanism behind that bound, asserted directly.
    assert 'warm, warm' not in ', '.join(served_classes), (
        'two warm builds in a row while the queue had work')


def _pending_demand(producer):
    """How many on-demand rows are queued, the newest one included."""
    with producer.engine.connect() as connection:
        return connection.execute(sa.text(
            "select count(*) from radar_board_results"
            " where namespace = :ns and warm = 0 and queue_state = 'pending'"),
            {'ns': producer.ns}).scalar()


# --- failure ----------------------------------------------------------------

def test_a_failed_build_backs_off_and_the_last_board_goes_on_being_served(
        producer, monkeypatch):
    clock = Clock()
    fake_build(monkeypatch)
    pair = demand_key(0)
    producer.admit(pair)
    assert producer.serve(clock, prefer='demand') == pair[0]
    published = producer.read(pair[0]).payload
    assert published is not None

    clock.advance(60)
    producer.admit(pair, now=clock.now)
    broken_build(monkeypatch)
    assert producer.serve(clock, prefer='demand') == pair[0]

    stored = producer.read(pair[0])
    assert stored.queue_state == 'failed'
    assert stored.last_error == 'RuntimeError', 'the message text is not a column'
    assert stored.next_attempt_at == clock.now + seconds(30)
    assert stored.attempts == 1
    assert stored.payload == published, 'a broken rebuild threw away the board'
    assert stored.as_of == NOW


def test_six_failures_park_the_key_and_the_next_success_resets_the_count(
        producer, monkeypatch):
    clock = Clock()
    fake_build(monkeypatch)
    broken_build(monkeypatch)
    pair = demand_key(0)
    producer.admit(pair)

    backoffs = []
    for attempt in range(1, 7):
        failed_at = clock.now
        assert producer.serve(clock, prefer='demand') == pair[0]
        stored = producer.read(pair[0])
        assert stored.attempts == attempt
        backoffs.append((stored.next_attempt_at - failed_at).total_seconds())
        # Straight to the retry boundary, which is the point of taking the
        # clock as an argument: none of this is waited for.
        clock.now = stored.next_attempt_at

    assert backoffs == [30, 60, 120, 240, 480, 900], (
        'the retry curve is 30s doubling, and parked at the sixth attempt')

    fake_build(monkeypatch)
    assert producer.serve(clock, prefer='demand') == pair[0]
    recovered = producer.read(pair[0])
    assert recovered.attempts == 0
    assert recovered.last_error is None
    assert recovered.next_attempt_at is None
    assert recovered.payload is not None


# --- the fence --------------------------------------------------------------

def test_a_builder_that_lost_its_lease_publishes_nothing(producer, monkeypatch,
                                                          caplog):
    """The first builder's lease runs out mid-build, a second producer takes
    the key and publishes, and then the first one finishes. Its publish has to
    lose: its board is the older one, and writing it would replace a fresh
    board with a stale one."""
    clock = Clock()
    lease = board_store.limits().lease_seconds
    pair = demand_key(0)
    producer.admit(pair)
    overtaker = {'done': False}

    def hand_over():
        if overtaker['done']:
            return
        overtaker['done'] = True
        # Past the first claim's lease, so the row is claimable again.
        clock.advance(lease + 1)
        assert producer.serve(clock, prefer='demand', owner='owner-2') == pair[0]

    fake_build(monkeypatch, before=hand_over)

    with caplog.at_level(logging.INFO, logger='radar.board'):
        assert producer.serve(clock, prefer='demand') == pair[0]

    stored = producer.read(pair[0])
    assert stored.as_of == NOW + seconds(lease + 1), "the overtaker's board"
    assert stored.queue_state == 'idle'
    lines = [record.getMessage() for record in caplog.records
             if record.getMessage().startswith('board build ')]
    assert any('result=overtaken' in line for line in lines)
    assert any('result=published' in line for line in lines)


# --- transactions -----------------------------------------------------------

class _Depth:
    """How many transactions this engine currently has open.

    The same listener the store's tests use: `begin`, `commit` and `rollback`
    are the only three events involved, so the count is exactly the depth.
    """

    def __init__(self, engine):
        self.engine = engine
        self.open = 0
        self.peak = 0

    def __enter__(self):
        sa.event.listen(self.engine, 'begin', self._begin)
        sa.event.listen(self.engine, 'commit', self._end)
        sa.event.listen(self.engine, 'rollback', self._end)
        return self

    def __exit__(self, *problem):
        sa.event.remove(self.engine, 'begin', self._begin)
        sa.event.remove(self.engine, 'commit', self._end)
        sa.event.remove(self.engine, 'rollback', self._end)

    def _begin(self, connection):
        self.open += 1
        self.peak = max(self.peak, self.open)

    def _end(self, connection):
        self.open -= 1


def session_transaction():
    """The ORM session's open transaction, or None.

    `db.session` is a `scoped_session`, which does not proxy
    `get_transaction()` -- and asking the proxy for the session would CREATE
    one, which is precisely the thing a removed session should not have. So a
    registry with no session at all answers None, which is the stronger of the
    two ways of having nothing open.
    """
    if not db.session.registry.has():
        return None
    return db.session().get_transaction()


def test_an_idle_tick_leaves_nothing_open(producer, monkeypatch):
    """A producer with no work waits, and it must wait holding nothing. An ORM
    session left open across a poll interval is a connection out of the pool
    and a read view held against every table the last build touched."""
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 0)
    loop = producer.loop(clock)

    with _Depth(producer.engine) as depth:
        assert loop.tick(NOW) is None
        assert depth.open == 0, f'an idle tick left {depth.open} open'
        assert depth.peak == 1, 'a tick nested transactions'

    assert session_transaction() is None


def test_no_job_leaves_a_transaction_open_behind_it(producer, monkeypatch):
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 1)
    producer.admit(demand_key(0))
    loop = producer.loop(clock)

    with _Depth(producer.engine) as depth:
        for _ in range(3):
            loop.tick(NOW)
            assert depth.open == 0
            assert session_transaction() is None

    broken_build(monkeypatch)
    producer.admit(demand_key(1))
    with _Depth(producer.engine) as depth:
        loop.tick(NOW)
        assert depth.open == 0, 'a failed job left a transaction open'
    assert session_transaction() is None


# --- shutdown ---------------------------------------------------------------

def test_shutdown_waits_for_the_build_in_flight_and_no_longer(producer,
                                                              monkeypatch):
    """SIGTERM during a build finishes the build. The alternative is a lease
    left held for two minutes on a key nobody is building any more."""
    started = threading.Event()

    def sleep_a_little():
        started.set()
        time.sleep(0.3)

    fake_build(monkeypatch, before=sleep_a_little)
    query = warm_subset(monkeypatch, 1)[0]
    key_hash, _ = board_keys.canonical(query)
    stop = threading.Event()
    loop = producer.loop(board_producer.utcnow)

    def run():
        with flask_app.app_context():
            loop.run(stop)

    thread = threading.Thread(target=run, name='producer-under-test')
    thread.start()
    assert started.wait(5), 'the build never began'
    stop.set()
    thread.join(1.0)

    assert not thread.is_alive(), 'the loop outlived its stop event'
    stored = producer.read(key_hash)
    assert stored is not None and stored.payload is not None, (
        'the build in flight was abandoned rather than finished')


# --- readiness --------------------------------------------------------------

def test_readiness_names_the_standing_boards_that_are_missing(producer,
                                                              monkeypatch):
    clock = Clock()
    fake_build(monkeypatch)

    cold = board_producer.readiness(producer.engine, producer.ns, NOW)
    assert cold['ready'] is False
    assert cold['warm_total'] == 8 and cold['warm_ready'] == 0
    assert len(cold['missing']) == 8
    assert all(re.fullmatch(r'[0-9a-f]{12}', key) for key in cold['missing'])

    loop = producer.loop(clock)
    for _ in range(8):
        assert loop.tick(NOW) is not None

    warm = board_producer.readiness(producer.engine, producer.ns, NOW)
    assert warm['ready'] is True
    assert warm['missing'] == [] and warm['warm_ready'] == 8

    fresh_seconds = board_store.limits().fresh_seconds
    assert board_producer.readiness(
        producer.engine, producer.ns, NOW + seconds(fresh_seconds))['ready'] is True
    stale = board_producer.readiness(
        producer.engine, producer.ns, NOW + seconds(fresh_seconds + 0.001))
    assert stale['ready'] is False and len(stale['missing']) == 8


def test_readiness_refuses_to_be_ready_about_the_wrong_number_of_boards(
        producer, monkeypatch):
    """`warm_limit` is what readiness compares against. A ninth standing
    selection added without moving it would otherwise report a warm cache
    that is one board short of what the code now builds."""
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 4)
    loop = producer.loop(clock)
    for _ in range(4):
        loop.tick(NOW)

    state = board_producer.readiness(producer.engine, producer.ns, NOW)
    assert state['missing'] == []
    assert state['warm_total'] == 4 and state['warm_limit'] == 8
    assert state['ready'] is False


# --- health -----------------------------------------------------------------

def test_the_namespace_row_carries_the_producers_health(producer, monkeypatch):
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 1)

    producer.loop(clock).tick(NOW)

    health = board_store.health(producer.engine, producer.ns)
    assert health['producer_owner'] == 'owner-1'
    assert health['producer_seen_at'] == NOW
    assert health['producer_success_at'] == NOW
    assert health['producer_error'] is None
    assert health['producer_revision'] == REVISION

    broken_build(monkeypatch)
    producer.admit(demand_key(0))
    producer.serve(clock, prefer='demand')

    failed = board_store.health(producer.engine, producer.ns)
    assert failed['producer_error'] == 'RuntimeError'
    assert failed['producer_success_at'] == NOW, 'the last success still stands'


def test_housekeeping_runs_on_a_minute_and_says_what_the_queue_holds(
        producer, monkeypatch, caplog):
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 1)
    loop = producer.loop(clock)

    with caplog.at_level(logging.INFO, logger='radar.board'):
        loop.tick(NOW)
        queue_lines = [record.getMessage() for record in caplog.records
                       if record.getMessage().startswith('board queue ')]
        assert len(queue_lines) == 1
        loop.tick(NOW + seconds(59))
        assert len([record for record in caplog.records
                    if record.getMessage().startswith('board queue ')]) == 1
        loop.tick(NOW + seconds(60))
        assert len([record for record in caplog.records
                    if record.getMessage().startswith('board queue ')]) == 2


# --- metrics ----------------------------------------------------------------

BUILD_LINE = re.compile(
    r'board build key=[0-9a-f]{12} class=(warm|ondemand) '
    r'queue_wait=(\d+\.\d|-) build_ms=\d+ payload_bytes=\d+ '
    r'result=(published|overtaken|failed)')

READ_LINE = re.compile(
    r'board read demand=(initial|poll) class=(warm|ondemand) key=[0-9a-f]{12} '
    r'outcome=(ready|stale|pending|busy|failed) cache_age=(\d+\.\d|-) '
    r'queue_age=(\d+\.\d|-) read_ms=\d+ account_ms=\d+')


def test_the_metrics_lines_are_the_documented_shape_and_name_nobody(
        producer, monkeypatch, caplog):
    """A test greps these lines, which is the point: every field is drawn from
    a closed vocabulary, a twelve-hex prefix or a number, so there is nowhere
    for a user id, a query string or a URL to appear."""
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 1)
    producer.admit(demand_key(0))
    loop = producer.loop(clock)

    with caplog.at_level(logging.INFO, logger='radar.board'):
        loop.tick(NOW)
        loop.tick(NOW)
        board_metrics.log_read(demand='poll', cls='ondemand',
                               key=demand_key(0)[0], outcome='stale',
                               cache_age=12.5, queue_age=None, read_ms=3,
                               account_ms=1)
        board_metrics.log_read(demand='initial', cls='warm',
                               key=demand_key(1)[0], outcome='pending',
                               cache_age=None, queue_age=0.25, read_ms=2,
                               account_ms=0)

    lines = [record.getMessage() for record in caplog.records
             if record.name == 'radar.board']
    builds = [line for line in lines if line.startswith('board build ')]
    reads = [line for line in lines if line.startswith('board read ')]
    assert len(builds) == 2 and len(reads) == 2
    for line in builds:
        assert BUILD_LINE.fullmatch(line), line
    for line in reads:
        assert READ_LINE.fullmatch(line), line
    assert 'class=warm' in builds[0] and 'class=ondemand' in builds[1]
    assert 'cache_age=-' in reads[0] or 'queue_age=-' in reads[0]

    for line in lines:
        for forbidden in ('user', '?', '/radar', 'http', '@', '&'):
            assert forbidden not in line, line


def test_a_metrics_field_outside_its_vocabulary_is_refused():
    """Refused rather than printed. These values are constants in code, so an
    unknown one is a bug on its way into a log line a dashboard parses --
    and the closed vocabulary is the whole of the no-identifiers guarantee."""
    with pytest.raises(ValueError):
        board_metrics.log_read(demand='initial', cls='warm', key='a' * 64,
                               outcome='whatever', cache_age=None,
                               queue_age=None, read_ms=1, account_ms=1)
    with pytest.raises(ValueError):
        board_metrics.log_build(key='not hex at all', cls='warm', queue_wait=0,
                                build_ms=1, payload_bytes=1,
                                result='published')
    with pytest.raises(ValueError):
        board_metrics.log_build(key='a' * 64, cls='demand', queue_wait=0,
                                build_ms=1, payload_bytes=1, result='published')
