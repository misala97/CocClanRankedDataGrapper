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
                            board_shared, board_store)
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

    It does read through `db.session` once, and that one statement is not
    decoration. The real `board.build` is four ORM queries, so a real build
    leaves the session holding an open read transaction -- and closing that
    before the publish opens its own is the reason `serve_once` removes the
    session twice. A fake that touched no session would let that removal be
    deleted with every test still passing.

    Returns the call log.
    """
    calls = []

    def build(sources, now, **kwargs):
        calls.append((tuple(sources), now, tuple(sorted(kwargs.items()))))
        db.session.execute(sa.text('select 1')).scalar()
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


def test_the_eight_warm_hashes_do_not_move_with_the_clock():
    """The standing keys are the same eight at every hour of the day.

    They have to be. A key hash that carried the moment it was derived would
    mean the warm sweep adopting eight NEW rows on every tick, the previous
    eight aging out of the freshness window with nothing ever rebuilding them,
    and a readiness gate that could never open -- while `parse_query` takes a
    `now` and is entitled to use it, which is exactly why this is asserted
    rather than assumed.
    """
    assert board_producer.warm_keys(NOW) == board_producer.warm_keys(
        NOW + seconds(6 * 60 * 60))


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


@pytest.mark.parametrize('args, warm', [
    ({'market': 'us', 'segment': '', 'window': '12'}, True),
    # NOT warm, and here because the warm eight cannot pin the rooting: their
    # sources are the whole of SOURCES, every one of which is already its own
    # root, so `sorted({source_root(s) for s in sources})` is the identity on
    # them and a `build_blob` that dropped the rooting would still agree.
    # One subreddit is where the two paths could differ and must not.
    ({'market': 'us', 'sources': 'reddit:wallstreetbets'}, False),
], ids=['a standing board', 'a sub-source selection'])
def test_the_blob_is_the_payload_the_request_path_would_have_served(
        producer, monkeypatch, args, warm):
    """The two paths to a board, compared field for field.

    This is the whole premise of the shared cache: a reader handed a stored
    blob must be handed what the synchronous path would have built for it. The
    two are separate code -- `build_payload_direct` parses, builds, roots and
    serializes; `build_blob` does the same four things from a `Query` -- and
    nothing but this test forces them to stay the same. A rooting rule added
    to one, a field `serialize` grows that only one of them stamps, and the
    shared path serves a board subtly unlike the one it replaced, to everyone,
    silently.

    One kind of field is expected to differ, and it is named rather than
    skipped: the ENVELOPE -- how this particular copy of the board was
    delivered, how old it is and when to ask again -- is added by whichever
    path answered, on top of the board. The blob is the board itself, so it
    carries none of it. `ops_collected_at` is in the envelope for the request
    path and in the blob for the producer, and is compared: it is the one
    field that has to mean the same instant in both places, because a
    payload's frozen ops summaries are dated by it.

    `watching` and `watch_rows` are per ACCOUNT -- the reason the blob is
    viewer-invariant at all -- and are compared rather than subtracted. Both
    paths now add them out of the one helper `api.account_fields`, which is
    what a reader of a stored blob gets on top of it, so putting that helper's
    answer on the blob here compares what a viewer would actually be handed
    from either side. For `user_id=None` it is the empty marks of a board
    nobody has claimed.
    """
    fake_build(monkeypatch)
    # A cache of this test's own, so a board built by the fake cannot be
    # served to a later test asking the same selection for real.
    monkeypatch.setattr(api, 'board_cache', {})

    query = api.parse_query(args, now=NOW)
    assert (board_keys.canonical(query) in board_producer.warm_keys(NOW)) is warm

    served = api.build_payload_direct(args, now=NOW, user_id=None)
    blob, _, _, _, _ = board_producer.build_blob(query, now=Clock())
    stored = json.loads(zlib.decompress(blob))

    account = api.account_fields(query, NOW, None)
    assert account == {'watching': [], 'watch_rows': []}
    stored.update(account)
    assert stored.pop('ops_collected_at') == NOW.isoformat() + 'Z'
    envelope = {name: served.pop(name)
                for name in board_shared.ENVELOPE_KEYS if name in served}
    assert envelope['ops_collected_at'] == NOW.isoformat() + 'Z'
    assert envelope['shared'] is False and envelope['pending'] is False
    assert set(envelope) == set(board_shared.ENVELOPE_KEYS), (
        'the synchronous path stopped writing part of the envelope')

    # Both through the same encoder: the blob is JSON on the way into the
    # column and the request path is JSON on the way to the browser, so the
    # comparison is of content and not of which Python type carried it.
    assert json.loads(json.dumps(served, sort_keys=True, default=str)) == stored


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


SUSTAINED_TICKS = 80
SUSTAINED_REFRESH = 10
SUSTAINED_BUILD = 0.5


def test_a_sustained_mixed_run_starves_neither_class(producer, monkeypatch):
    """Eighty builds with a new viewer arriving on every one of them.

    Two bounds, and they pull against each other. The standing boards must not
    age past twice their refresh interval, which costs the queue a slot every
    time one comes due; and the queue must not be made to wait for more than
    two builds per place in line, which is what strict alternation buys it.

    The demand bound is per PLACE IN LINE rather than a flat number of ticks:
    arrivals here match the service rate exactly, so every slot warm work
    takes leaves the queue one deeper for the rest of the run, and no fixed
    wait can hold. What alternation actually promises is that the queue gets
    at least every other build, and that is the bound asserted.

    EIGHTY ticks and not forty, because the warm half of this test has to be
    able to fail. Forty ticks of a half-second build is twenty seconds of
    simulated time, and `age <= 2 * refresh` is twenty seconds -- so no
    arrangement of those forty ticks could have breached it, and the bound was
    decoration. Forty seconds is four refresh intervals, which is long enough
    for a standing board to age past the bound if the sweep ever stops
    re-enqueueing it. The count is asserted for the same reason: two warm
    builds is what a run gets from adopting the keys ONCE, and correct
    behaviour rebuilds each of the two around ticks 0, 2, ~20, ~22, ~40, ~42
    and ~60, ~62.
    """
    monkeypatch.setenv('RADAR_BOARD_REFRESH_SECONDS', str(SUSTAINED_REFRESH))
    clock = Clock()
    fake_build(monkeypatch, clock=clock, advance=SUSTAINED_BUILD)
    warm = warm_subset(monkeypatch, 2)
    warm_hashes = {board_keys.canonical(query)[0] for query in warm}

    loop = producer.loop(clock)
    served_classes = []
    warm_ages = []
    admitted_at = {}
    waits = []
    for index in range(SUSTAINED_TICKS):
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

    # Four, not two: two is what adopting the keys once and never coming back
    # for them would produce, and forty seconds is four refresh intervals.
    assert served_classes.count('warm') >= 4, (
        f'the warm sweep ran {served_classes.count("warm")} times in '
        f'{SUSTAINED_TICKS * SUSTAINED_BUILD}s of a '
        f'{SUSTAINED_REFRESH}s refresh')
    assert max(warm_ages) <= 2 * SUSTAINED_REFRESH, (
        f'a standing board aged to {max(warm_ages)}s past a '
        f'{SUSTAINED_REFRESH}s refresh')
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


def test_serve_once_claims_under_an_owner_the_column_can_hold(producer,
                                                              monkeypatch):
    """`lease_owner` is VARCHAR(64) and the fence compares stored to held.

    An owner longer than the column is shortened on the way in and matches
    nothing on the way out, so a builder would fence itself out of its own
    publish -- every board discarded as overtaken, by its own name. Under a
    strict `sql_mode` it does not even get that far. `Loop.__init__` truncates;
    `serve_once` is callable without a `Loop` and has to do the same.
    """
    clock = Clock()
    fake_build(monkeypatch)
    pair = demand_key(0)
    producer.admit(pair)
    long_owner = 'a-hostname-nobody-should-have-chosen:' * 4
    assert len(long_owner) > board_producer._OWNER_WIDTH

    assert board_producer.serve_once(
        producer.engine, producer.ns, long_owner, clock,
        prefer='demand', revision=REVISION) == pair[0]

    stored = producer.read(pair[0])
    assert stored.payload is not None, (
        'the publish was fenced out by the builder\'s own name')
    assert stored.queue_state == 'idle'
    health = board_store.health(producer.engine, producer.ns)
    assert health['producer_owner'] == long_owner[:board_producer._OWNER_WIDTH]


def test_a_database_that_blinked_after_the_build_is_not_the_keys_fault(
        producer, monkeypatch, caplog):
    """A `publish` that raises must not mark the key as having failed to build.

    The board was built, and built correctly. Counting an attempt against the
    key and backing it off for thirty seconds would punish the selection for
    the database's moment, and six of those moments would park a perfectly
    good standing board for fifteen minutes. What protects the row is the
    lease: it expires on its own and the key becomes claimable again, which is
    the same recovery a producer killed mid-build gets.
    """
    clock = Clock()
    fake_build(monkeypatch)
    pair = demand_key(0)
    producer.admit(pair)

    def explode(*args, **kwargs):
        raise RuntimeError('the connection went away')

    monkeypatch.setattr(board_store, 'publish', explode)

    with caplog.at_level(logging.INFO, logger='radar.board'):
        assert producer.serve(clock, prefer='demand') == pair[0]

    stored = producer.read(pair[0])
    assert stored.queue_state == 'building', (
        'a failing publish was written down as a failing build')
    assert stored.last_error is None, 'the database blinking became the key\'s error'
    assert stored.next_attempt_at is None, 'a built board was backed off'
    # One, and that one is `claim`'s own counter -- which the next successful
    # publish sets back to zero. `fail` was not called, which is the claim
    # being made: it is `fail` that turns a count into thirty seconds of
    # backoff and, at six, into fifteen minutes of parking.
    assert stored.attempts == 1
    assert stored.lease_expires_at is not None, (
        'nothing is left to make the key claimable again')
    assert any('board publish failed' in record.getMessage()
               for record in caplog.records), 'the failure went unlogged'
    assert board_store.health(producer.engine,
                              producer.ns)['producer_error'] is None


# --- two producers at once --------------------------------------------------

# The build the OTHER generation says it is. Different from REVISION on
# purpose: the column each row carries is what makes "whose board is this"
# something to assert rather than something to believe.
OTHER_REVISION = 'c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0'


def test_two_producers_on_one_database_publish_only_into_their_own(
        producer, monkeypatch):
    """A rollout and a rollback both run two producers side by side.

    That window is what the namespace was introduced for, and until now every
    test in this file built one namespace and one Loop, so nothing proved the
    ruling's "old and new producers must claim only their own namespace" for
    the producer at all. Two Loops, two generations, one database, one set of
    warm keys -- and a key only one of them was asked for.
    """
    clock = Clock()
    fake_build(monkeypatch)
    warm_hash, _ = board_keys.canonical(warm_subset(monkeypatch, 1)[0])
    theirs_ns = producer.namespace()
    mine = producer.loop(clock)
    theirs = board_producer.Loop(producer.engine, ns=theirs_ns,
                                 owner='owner-2', revision=OTHER_REVISION,
                                 now_fn=clock)
    # One viewer, asking the other generation for a board.
    theirs_only = demand_key(0)
    board_store.admit(producer.engine, theirs_ns, *theirs_only, NOW)

    # This producer's tick: its own warm board, and nothing of theirs.
    assert mine.tick(NOW) == warm_hash
    assert board_store.read(producer.engine, theirs_ns,
                            theirs_only[0]).queue_state == 'pending'
    assert board_store.read(producer.engine, theirs_ns, warm_hash) is None, (
        'a producer swept warm keys into a generation that is not its own')

    # Theirs: the same warm key, built and published under their own name.
    assert theirs.tick(NOW) == warm_hash
    for namespace, revision in ((producer.ns, REVISION),
                                (theirs_ns, OTHER_REVISION)):
        with producer.engine.connect() as connection:
            row = connection.execute(sa.text(
                'select * from radar_board_results'
                ' where namespace = :ns and key_hash = :k'),
                {'ns': namespace, 'k': warm_hash}).mappings().one()
        assert row['queue_state'] == 'idle'
        assert row['payload'] is not None
        assert row['producer_revision'] == revision, (
            'one generation published under the other one\'s revision')

    # Nothing is left for this producer: the only work outstanding is theirs.
    assert mine.tick(NOW) is None
    assert theirs.tick(NOW) == theirs_only[0]
    assert board_store.read(producer.engine, producer.ns,
                            theirs_only[0]) is None, (
        'a key admitted in one generation appeared in the other')


def test_a_producer_never_reclaims_a_lease_held_in_another_generation(
        producer, monkeypatch):
    """An expired lease is the one row any producer may take, and even that
    is namespace-scoped: a generation whose builder died is its own to
    recover, and a rollback must not hand its half-built keys to the other
    side."""
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 0)
    theirs_ns = producer.namespace()
    pair = demand_key(0)
    board_store.admit(producer.engine, theirs_ns, *pair, NOW)
    abandoned = board_store.claim(producer.engine, theirs_ns, 'owner-2', NOW,
                                  prefer='demand')
    assert abandoned is not None

    # Well past the lease, when any producer in that generation would reclaim.
    expired = NOW + seconds(board_store.limits().lease_seconds + 60)
    clock.now = expired

    assert producer.loop(clock).tick(expired) is None, (
        'a producer reclaimed a lease that belonged to another generation')
    row = board_store.read(producer.engine, theirs_ns, pair[0])
    assert row.queue_state == 'building'
    assert board_store.read(producer.engine, producer.ns, pair[0]) is None


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
    """Nothing open after a job, and nothing NESTED during one.

    `depth.peak == 1` is the load-bearing half. `serve_once` removes the
    session in a `finally` around the build itself and not only at the end, so
    that the build's own read transaction is closed before `publish` opens one
    of its own. Without that inner removal the two overlap: a peak of two,
    which is one pooled connection and one open read view held for the length
    of a build, on every job, on the one process that builds every board.
    """
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 1)
    producer.admit(demand_key(0))
    loop = producer.loop(clock)

    with _Depth(producer.engine) as depth:
        for _ in range(3):
            loop.tick(NOW)
            assert depth.open == 0
            assert depth.peak == 1, (
                f'a serving tick nested {depth.peak} transactions, so the '
                f'build held one open across the publish')
            assert session_transaction() is None

    broken_build(monkeypatch)
    producer.admit(demand_key(1))
    with _Depth(producer.engine) as depth:
        loop.tick(NOW)
        assert depth.open == 0, 'a failed job left a transaction open'
        assert depth.peak == 1, (
            f'a failing tick nested {depth.peak} transactions')
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


# --- a database that is down ------------------------------------------------

def scripted_loop(producer, monkeypatch, script, *, poll_interval=0.5):
    """A loop whose `tick` follows a script, and whose waits are recorded.

    `stop_event.wait` is replaced rather than shortened: the point is the
    sequence of durations the loop ASKS for, and waiting them out would make
    this test take the sum of them.
    """
    stop = threading.Event()
    waits = []
    steps = iter(script)

    def tick():
        step = next(steps)
        if step == 'fail':
            raise RuntimeError('the database is down')
        if step == 'stop':
            stop.set()
            return 'a' * 64
        return None if step == 'idle' else 'a' * 64

    def wait(timeout=None):
        waits.append(timeout)
        return stop.is_set()

    loop = producer.loop(Clock(), poll_interval=poll_interval)
    monkeypatch.setattr(loop, 'tick', tick)
    monkeypatch.setattr(stop, 'wait', wait)
    return loop, stop, waits


def test_a_failing_tick_backs_off_instead_of_retrying_twice_a_second(
        producer, monkeypatch, caplog):
    """A database that is down must not be polled at the idle rate forever.

    The failure mode this fixes is a whole service log: half a second apart,
    a full traceback each time, for as long as the outage lasts -- which is
    both the noisiest way to report one problem and the least kind thing to do
    to the database that is trying to come back. So consecutive failures
    double the wait up to a cap, and one completed tick puts it back.
    """
    loop, stop, waits = scripted_loop(
        producer, monkeypatch,
        # Three failures, one tick that completes with nothing to do, then one
        # more failure -- which must start the curve again, not continue it.
        ['fail', 'fail', 'fail', 'idle', 'fail', 'stop'])

    with caplog.at_level(logging.INFO, logger='radar.board'):
        loop.run(stop)

    assert waits == [1.0, 2.0, 4.0, 0.5, 1.0], (
        'the backoff is 2x the poll interval, doubling, and reset by a tick '
        f'that completed: {waits}')

    failed = [record for record in caplog.records
              if 'tick failed' in record.getMessage()]
    # One line per failed tick, no more: four failures, four lines. Half a
    # second apart with a traceback each, a minute of outage is a hundred and
    # twenty tracebacks that all say the same thing.
    lines = [record.getMessage() for record in failed]
    assert len(lines) == 4
    assert 'failures=1' in lines[0] and 'next_wait=1.0s' in lines[0]
    assert 'failures=3' in lines[2] and 'next_wait=4.0s' in lines[2]
    assert 'failures=1' in lines[3] and 'next_wait=1.0s' in lines[3], (
        'a tick that completed did not reset the count')

    # A traceback opens each RUN of failures and nothing after it. Two runs
    # here, because the successful tick in the middle ended the first one --
    # and a fresh outage is a fresh incident, worth a fresh traceback.
    with_traceback = [index for index, record in enumerate(failed)
                      if record.exc_info is not None]
    assert with_traceback == [0, 3], (
        'the traceback belongs to the first failure of an outage and to no '
        f'other: {with_traceback}')


def test_the_backoff_is_capped_so_a_long_outage_is_still_polled(
        producer, monkeypatch):
    """Doubling without a cap reaches an hour, and a producer that has stopped
    asking is indistinguishable from one that has died. Thirty seconds is a
    rate a recovering database can carry and a delay an operator will sit
    through."""
    loop, stop, waits = scripted_loop(
        producer, monkeypatch, ['fail', 'fail', 'stop'], poll_interval=20)

    loop.run(stop)

    assert waits == [board_producer.MAX_BACKOFF_SECONDS] * 2, (
        f'40s and 80s were asked for uncapped: {waits}')


def test_an_outage_of_hours_does_not_kill_the_producer_from_inside(
        producer, monkeypatch):
    """The cap is on the WAIT, and that is not where the arithmetic happens.

    `poll_interval * 2 ** failures` is computed before `min` ever sees it, and
    `2 ** 1024` is past the largest float there is: at the thousand and
    twenty-fourth consecutive failure the multiplication raises OverflowError
    -- inside the except handler that exists to keep this loop alive, so it
    propagates out of `run` and the only process that builds boards exits.

    Half a second apart, that is about eight and a half hours of a database
    being down: a long outage over an unattended weekend, which is precisely
    the situation the backoff was written for. So the EXPONENT is capped as
    well, and the five thousandth failure asks for the same thirty seconds the
    sixth did.
    """
    failures = 5000
    loop, stop, waits = scripted_loop(
        producer, monkeypatch, ['fail'] * failures + ['stop'])

    loop.run(stop)

    assert len(waits) == failures, f'the loop stopped waiting: {len(waits)}'
    # A half-second interval doubles into the cap at the sixth failure.
    assert waits[:6] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    assert set(waits[5:]) == {board_producer.MAX_BACKOFF_SECONDS}


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


def queue_lines(caplog):
    return len([record for record in caplog.records
                if record.getMessage().startswith('board queue ')])


def test_housekeeping_runs_on_a_minute_of_monotonic_time(
        producer, monkeypatch, caplog):
    """Sixty seconds by a clock that only goes forwards, not by the wall.

    The wall clock is what the three housekeeping calls are asked about --
    which rows have expired, which generations are stale -- but it is not what
    decides that a minute has passed. NTP steps a server's wall clock, and a
    step forward would run the housekeeping early while a step back would
    suspend it for the length of the step, on a process whose whole job is to
    keep going unattended for weeks.

    So the wall clock here jumps ten minutes forward and then back to where it
    started, and the housekeeping ignores both: it runs on the first tick and
    again when the MONOTONIC reading says sixty seconds, not before.
    """
    clock = Clock()
    fake_build(monkeypatch)
    warm_subset(monkeypatch, 1)
    elapsed = iter([1000.0, 1059.0, 1060.0])
    monkeypatch.setattr(board_producer, '_monotonic', lambda: next(elapsed))
    loop = producer.loop(clock)

    with caplog.at_level(logging.INFO, logger='radar.board'):
        loop.tick(NOW)
        assert queue_lines(caplog) == 1
        # Ten wall-clock minutes later, fifty-nine monotonic seconds later.
        loop.tick(NOW + seconds(600))
        assert queue_lines(caplog) == 1, (
            'a wall clock that jumped forward ran the housekeeping early')
        # The wall clock steps back to where it began; the interval is up.
        loop.tick(NOW)
        assert queue_lines(caplog) == 2, (
            'a wall clock that stepped back suspended the housekeeping')


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


def test_a_duration_never_renders_negative(caplog):
    """A board built half a second into the future is not a thing to report.

    Every duration on these lines is the difference of two WALL clocks read at
    different moments, and possibly on different machines: `cache_age` is now
    minus a stored `as_of`, `queue_age` now minus an `enqueued_at`. A step
    under NTP puts a minus sign in a field a dashboard parses as `\\d+\\.\\d`,
    and `cache_age=-0.5` is a number nobody can act on. Zero is the honest
    floor: the board is as new as it is possible to be.
    """
    with caplog.at_level(logging.INFO, logger='radar.board'):
        board_metrics.log_read(demand='poll', cls='warm', key='a' * 64,
                               outcome='ready', cache_age=-0.5,
                               queue_age=-12.25, read_ms=3, account_ms=1)
        board_metrics.log_build(key='a' * 64, cls='warm', queue_wait=-0.5,
                                build_ms=1, payload_bytes=1,
                                result='published')

    # This logger's own records, like the line-shape test above: another
    # library logging inside the block would otherwise become `lines[0]`.
    lines = [record.getMessage() for record in caplog.records
             if record.name == 'radar.board']
    assert 'cache_age=0.0' in lines[0] and 'queue_age=0.0' in lines[0], lines[0]
    assert 'queue_wait=0.0' in lines[1], lines[1]
    assert '-' not in lines[0].replace('board read ', ''), lines[0]
    assert READ_LINE.fullmatch(lines[0]), lines[0]
    assert BUILD_LINE.fullmatch(lines[1]), lines[1]


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
