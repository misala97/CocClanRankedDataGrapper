"""The read path behind the flag: what a viewer is handed, and what it costs.

Against the disposable database, because everything here that matters is a
property of a stored row: whether a board that is 120.001 seconds old counts
as stale, whether a key in another generation is visible, whether a refused
admission wrote anything. A fake store would only prove this file agrees with
itself.

The tripwire is the first test and the reason for the rest. `board.build` and
`leaderboard.build_rows` are monkeypatched to raise for the whole module, so
ANY test here that accidentally reached the synchronous path would error
rather than pass slowly. That is the one property the shared path exists for:
a web worker never builds -- not on a miss, not on stale, not on busy, not on
a key that has been failing.

Each test owns a namespace of its own -- `board_namespace.namespace` is
monkeypatched to a random name and its rows are deleted afterwards -- so two
tests cannot see, evict or queue behind each other's work. Time is passed in
rather than read, which is what makes an exact freshness boundary something to
assert instead of something to wait for.
"""
import datetime as dt
import hashlib
import json
import logging
import re
import secrets
import zlib

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import (board as board_mod, board_keys, board_namespace,
                            board_producer, board_shared, board_store,
                            leaderboard, observations, watch)
from features.radar.market_calendars import session_state
import radar_disposable
from features.radar.routes import api

# One fixed instant, naive UTC -- the convention every timestamp in these
# tables is written in. A Thursday, inside the US regular session.
NOW = dt.datetime(2026, 9, 10, 15, 0, 0)

REVISION = 'b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0'


def seconds(count):
    return dt.timedelta(seconds=count)


# --- the fixtures -----------------------------------------------------------

class _Shared:
    """One namespace, the engine, and the shortest way to put a board in it."""

    def __init__(self, engine, ns):
        self.engine = engine
        self.ns = ns
        self.namespaces = [ns]

    def another_namespace(self):
        """A second generation, for the isolation test."""
        name = 'perf3read-' + secrets.token_hex(20)
        self.namespaces.append(name)
        return name

    def rows(self, ns=None):
        with self.engine.connect() as connection:
            return connection.execute(sa.text(
                'select * from radar_board_results where namespace = :ns'),
                {'ns': ns or self.ns}).mappings().all()

    def row(self, key_hash, ns=None):
        with self.engine.connect() as connection:
            return connection.execute(sa.text(
                'select * from radar_board_results'
                ' where namespace = :ns and key_hash = :k'),
                {'ns': ns or self.ns, 'k': key_hash}).mappings().first()

    def publish(self, args, *, as_of, ns=None, built_at=None, rows=None):
        """The row a finished build leaves behind, written directly.

        Not through `claim`/`publish`. Those pick whichever key is oldest in
        the namespace, so a fixture that used them could not put a payload on
        a NAMED key while other rows are queued -- which is the situation
        half of these tests are set in. The columns below are exactly the ones
        `board_store.publish` writes, and the store's own suite is where that
        statement is tested; here the point is the state, not the road to it.
        """
        ns = ns or self.ns
        query = api.parse_query(args, now=NOW)
        key_hash, key_json = board_keys.canonical(query)
        blob = blob_for(query, as_of=as_of, rows=rows)
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                'insert into radar_board_results'
                ' (namespace, key_hash, key_json, payload_version, queue_state,'
                '  warm, payload, payload_bytes, as_of, built_at, build_ms,'
                '  producer_revision, requested_at, request_count, attempts)'
                " values (:ns, :k, :j, 1, 'idle', 0, :blob, :size, :as_of,"
                '         :built_at, 7, :rev, :as_of, 1, 0)'
                ' on duplicate key update payload = :blob, payload_bytes = :size,'
                " as_of = :as_of, built_at = :built_at, queue_state = 'idle',"
                ' payload_version = 1, attempts = 0, last_error = null,'
                ' next_attempt_at = null'
            ).bindparams(sa.bindparam('blob', type_=sa.LargeBinary)),
                {'ns': ns, 'k': key_hash, 'j': key_json, 'blob': blob,
                 'size': len(blob), 'as_of': as_of,
                 'built_at': built_at or as_of, 'rev': REVISION})
        return key_hash

    def fail(self, args, *, now, error='RuntimeError', ns=None, retry_in=30):
        """The row a failed build leaves: backed off, payload untouched.

        `retry_in` is how far the backoff reaches past `now`. Negative is a
        backoff that has ELAPSED -- the key is still in the `failed` state its
        last build left it in, and the next admission will re-queue it. That is
        a different situation from a parked key and the two answer differently,
        so the fixture has to be able to produce both.
        """
        ns = ns or self.ns
        query = api.parse_query(args, now=NOW)
        key_hash, key_json = board_keys.canonical(query)
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                'insert into radar_board_results'
                ' (namespace, key_hash, key_json, payload_version, queue_state,'
                '  warm, enqueued_at, requested_at, request_count, attempts,'
                '  next_attempt_at, last_error)'
                " values (:ns, :k, :j, 1, 'failed', 0, :now, :now, 1, 1,"
                '         :retry, :error)'
                " on duplicate key update queue_state = 'failed', attempts = 1,"
                ' next_attempt_at = :retry, last_error = :error,'
                ' enqueued_at = :now'),
                {'ns': ns, 'k': key_hash, 'j': key_json, 'now': now,
                 'retry': now + seconds(retry_in), 'error': error})
        return key_hash

    def building(self, args, *, now, as_of=None, ns=None):
        """The row a claim leaves behind: `building`, leased, maybe payloadless.

        `as_of=None` is a key nobody has ever published -- the first build of a
        selection, in flight. With an `as_of` it is a rebuild of a board that
        already exists, which is the state the store spends most of its life
        in and the one where a reader must go on serving what it has.
        """
        ns = ns or self.ns
        query = api.parse_query(args, now=NOW)
        key_hash, key_json = board_keys.canonical(query)
        blob = None if as_of is None else blob_for(query, as_of=as_of)
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                'insert into radar_board_results'
                ' (namespace, key_hash, key_json, payload_version, queue_state,'
                '  warm, payload, payload_bytes, as_of, built_at, enqueued_at,'
                '  requested_at, request_count, attempts, lease_owner,'
                '  lease_token, lease_expires_at)'
                " values (:ns, :k, :j, 1, 'building', 0, :blob, :size, :as_of,"
                "         :as_of, :now, :now, 1, 0, 'somehost:42', 'tok',"
                '         :lease)'
            ).bindparams(sa.bindparam('blob', type_=sa.LargeBinary)),
                {'ns': ns, 'k': key_hash, 'j': key_json, 'blob': blob,
                 'size': None if blob is None else len(blob), 'as_of': as_of,
                 'now': now, 'lease': now + seconds(120)})
        return key_hash

    def seed_pending(self, count, *, base=NOW):
        """`count` on-demand rows already queued, inserted directly.

        The queue cap refuses the 33rd job, so 32 pending rows cannot be
        admitted one at a time through `admit` -- which is not a limitation of
        the test but the interaction it is set among.
        """
        pairs = []
        for index in range(count):
            key_json = json.dumps({'v': 2, 'seed': index}, sort_keys=True,
                                  separators=(',', ':'))
            pairs.append((hashlib.sha256(key_json.encode()).hexdigest(),
                          key_json))
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                'insert into radar_board_results'
                ' (namespace, key_hash, key_json, payload_version,'
                '  queue_state, warm, enqueued_at, requested_at,'
                '  request_count, attempts)'
                " values (:ns, :k, :j, 1, 'pending', 0, :at, :at, 1, 0)"),
                [{'ns': self.ns, 'k': pair[0], 'j': pair[1],
                  'at': base + seconds(index)}
                 for index, pair in enumerate(pairs)])
        return pairs


def blob_for(query, *, as_of, rows=None):
    """A stored payload in the shape `serialize` produces, compressed.

    Deliberately not a real board: this file is about what the read path does
    with a stored blob, and `test_radar_board_producer.py` is where the blob's
    own fidelity to `build_payload` is pinned. Every key the client reads is
    here, with `ops_collected_at` stamped as `build_blob` stamps it.

    The session and the boundary are the three fields a serialized board
    DERIVES rather than echoes, and they are derived here the way `board.build`
    derives them -- from the same two functions, with the same Tradegate-first
    MIC. A fake that named a session out of the air would make the shell-versus-
    board comparison below assert a difference the producer never produces.
    """
    mic = 'XGAT' if query.market == 'de' else None
    session = session_state(query.market, as_of.replace(tzinfo=dt.timezone.utc),
                            mic=mic)
    label, boundary_at = board_mod._next_boundary(query.market, as_of, session,
                                                  mic=mic)
    payload = {
        'generated_at': as_of.isoformat() + 'Z',
        'ops_collected_at': as_of.isoformat() + 'Z',
        'market': query.market,
        'display_timezone': 'Europe/Berlin',
        'market_venue': ('Tradegate-first Germany' if query.market == 'de'
                         else 'US markets'),
        'next_boundary_label': label,
        'next_boundary_at': api._iso_z(boundary_at),
        'sources': sorted({api.source_root(s) for s in query.sources}),
        'all_sources': list(api.SOURCES),
        'segments': list(query.segments),
        'session': session,
        'min_venues': query.min_venues,
        'sort': query.sort,
        'dir': query.direction,
        'venue_counts': {'any': 3, 'multi': 1},
        'window_hours': query.window,
        'segment_counts': {'all': 3, 'large': 2},
        'excluded': {},
        'spend': {'today_usd': 0.0},
        'sentiment_ops': {'backlog': 0},
        'market_data_ops': {'quotes': 0},
        'triplet_hours': list(board_mod.TRIPLET_HOURS),
        'series_hours': board_mod.SERIES_HOURS,
        'lead_count': board_mod.LEAD_COUNT,
        'rows': rows if rows is not None else [{'ticker': 'AAA'},
                                               {'ticker': 'BBB'}],
    }
    return zlib.compress(json.dumps(payload, sort_keys=True).encode('utf-8'), 6)


@pytest.fixture(autouse=True)
def no_building(monkeypatch):
    """The tripwire, for every test in this file.

    A reader that built a board would be the one failure this whole design
    exists to prevent, and it would be invisible: the response would look
    right and merely take six hundred milliseconds. So both entry points to a
    build raise, module-wide, and only a test that deliberately wants the
    legacy path puts them back.
    """
    def forbidden(*args, **kwargs):
        raise AssertionError('the read path built a board')

    monkeypatch.setattr(board_mod, 'build', forbidden)
    monkeypatch.setattr(leaderboard, 'build_rows', forbidden)
    # Not part of the tripwire the plan names, but the same accident wearing a
    # different hat: an account with marks would otherwise reach the database
    # for real in every served test here.
    monkeypatch.setattr(board_mod, 'build_pinned_rows',
                        lambda *a, **k: pytest.fail('unexpected pinned build'))


@pytest.fixture
def disposable():
    """The database guard, without the flag or a namespace.

    For the flag-OFF test below, which wants neither -- and which, before
    this, was the one test in this file that ran against whatever database
    happened to be bound.
    """
    with flask_app.app_context():
        radar_disposable.require()
        yield


@pytest.fixture
def shared(monkeypatch):
    """The flag on, a namespace of this test's own, and a clean memo."""
    with flask_app.app_context():
        radar_disposable.require('radar_board_results',
                                 'radar_board_namespaces')
        engine = db.engine
        name = 'perf3read-' + secrets.token_hex(20)
        monkeypatch.setenv('RADAR_BOARD_SHARED_RESULTS', 'on')
        monkeypatch.setattr(board_namespace, 'namespace', lambda: name)
        monkeypatch.setattr(board_namespace, 'describe', lambda: {
            'payload_version': board_namespace.PAYLOAD_VERSION,
            'revision': REVISION, 'fingerprint': 'f' * 16, 'namespace': name})
        board_shared.reset_namespace_memo()

        owned = _Shared(engine, name)
        try:
            yield owned
        finally:
            board_shared.reset_namespace_memo()
            with engine.begin() as connection:
                for namespace in owned.namespaces:
                    connection.execute(sa.text(
                        'delete from radar_board_results'
                        ' where namespace = :ns'), {'ns': namespace})
                    connection.execute(sa.text(
                        'delete from radar_board_namespaces'
                        ' where namespace = :ns'), {'ns': namespace})


def read(shared, args=None, *, now=NOW, user_id=None, poll=False):
    """`read_payload` inside an application context, the way a route calls it."""
    with flask_app.app_context():
        return board_shared.read_payload(shared.engine, args or {'market': 'us'},
                                         now, user_id, poll=poll)


def _embedded(html, element_id):
    """The payload a server-rendered page put in the document."""
    return json.loads(re.search(
        rf'<script type="application/json" id="{element_id}">(.*?)</script>',
        html, re.S).group(1))


# --- the tripwire -----------------------------------------------------------

def test_a_miss_is_a_pending_answer_and_never_a_build(shared, client):
    """The whole premise, through the real endpoint: with nothing stored and
    both build entry points raising, a viewer gets 200 and a shell."""
    response = client.get('/radar/api/board?market=us&window=12')
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['pending'] is True
    assert payload['busy'] is False
    assert payload['shared'] is True
    assert payload['rows'] is None
    assert payload['generated_at'] is None
    assert payload['as_of'] is None and payload['built_at'] is None
    assert payload['age_seconds'] is None
    # The selection echo is computed from the query, not from a board.
    assert payload['market'] == 'us'
    assert payload['window_hours'] == 12
    assert payload['segments'] == list(api.parse_query(
        {'market': 'us', 'window': '12'}, now=NOW).segments)
    assert payload['sources'] == sorted(api.SOURCES)
    assert payload['session'] in ('premarket', 'regular', 'afterhours', 'closed')
    assert payload['next_boundary_label'] in ('opens', 'closes')
    assert payload['venue_counts'] == {'any': 0, 'multi': 0}
    assert payload['segment_counts'] == {} and payload['excluded'] == {}
    assert payload['watching'] == [] and payload['watch_rows'] == []
    # Frozen operational figures belong to a board. A shell has none.
    for absent in ('spend', 'sentiment_ops', 'market_data_ops'):
        assert absent not in payload
    assert payload['ops_collected_at'] is None
    # The whole envelope, on the state that has the least to say.
    assert board_shared.ENVELOPE_KEYS <= set(payload)


def test_a_poll_asks_again_without_counting_as_a_new_request(shared, client):
    """`poll=1` records the demand and does not move the viewer up the queue.
    A client that polls every second must not outrank one that asked once."""
    assert client.get('/radar/api/board?market=us').status_code == 200
    key_hash, _ = board_keys.canonical(api.parse_query({'market': 'us'},
                                                       now=NOW))
    first = shared.row(key_hash)
    assert first['request_count'] == 1

    assert client.get('/radar/api/board?market=us&poll=1').status_code == 200
    again = shared.row(key_hash)
    assert again['request_count'] == 1
    assert again['enqueued_at'] == first['enqueued_at']


def test_only_the_literal_poll_1_is_read_as_a_poll(shared, client):
    """`poll=true` is a request, and is counted as one.

    The route compares against `'1'` exactly. Widening that to the flag
    vocabulary the environment uses would be a kindness to nobody -- this
    parameter is written by our own client, not by an operator -- and the cost
    of guessing wrong in the other direction is a viewer's repeat polls
    silently inflating `request_count`, which is what eviction ranks by.
    """
    assert client.get('/radar/api/board?market=us').status_code == 200
    key_hash, _ = board_keys.canonical(api.parse_query({'market': 'us'},
                                                       now=NOW))
    assert shared.row(key_hash)['request_count'] == 1

    assert client.get('/radar/api/board?market=us&poll=true').status_code == 200
    assert shared.row(key_hash)['request_count'] == 2


def test_the_server_rendered_pages_embed_the_pending_envelope(shared, client):
    """Both surfaces are the same payload, so both learn `pending` at once --
    including the one whose first paint is the document itself."""
    board_html = client.get('/radar/').get_data(as_text=True)
    embedded = _embedded(board_html, 'radar-data')
    assert embedded['pending'] is True and embedded['rows'] is None

    hub_html = client.get('/radar/hub/').get_data(as_text=True)
    shell = _embedded(hub_html, 'radar-hub-data')
    assert shell['board']['pending'] is True
    assert shell['board']['rows'] is None
    assert shell['board']['shared'] is True


@pytest.mark.parametrize('path, element_id, unwrap', [
    ('/radar/', 'radar-data', lambda embedded: embedded),
    ('/radar/hub/', 'radar-hub-data', lambda embedded: embedded['board']),
], ids=['board', 'hub'])
def test_a_query_the_parser_refuses_still_never_builds(
        shared, client, path, element_id, unwrap):
    """`?window=nonsense` raises BadQuery, and both pages answer it by asking
    for the DEFAULT board instead of erroring.

    That second ask goes through the dispatcher like the first, which is the
    part worth a test: a fallback wired to the synchronous function would build
    a board on a web worker -- the one thing the flag exists to stop -- and
    would do it on exactly the request a person makes by mistyping in the
    address bar, where nobody would think to look for it.
    """
    response = client.get(path + '?window=nonsense')
    assert response.status_code == 200

    payload = unwrap(_embedded(response.get_data(as_text=True), element_id))
    assert payload['pending'] is True and payload['rows'] is None
    assert payload['shared'] is True
    # The default board: the fallback asked with no arguments at all.
    assert payload['window_hours'] == 12


# --- disposition, at the exact boundaries -----------------------------------

def test_a_board_just_inside_the_freshness_bound_is_ready(shared):
    as_of = NOW - seconds(119.999)
    shared.publish({'market': 'us'}, as_of=as_of, built_at=as_of + seconds(7))
    payload = read(shared)

    assert payload['pending'] is False and payload['busy'] is False
    assert payload['stale'] is False and payload['failed'] is False
    assert payload['shared'] is True
    assert payload['age_seconds'] == pytest.approx(119.999, abs=0.001)
    assert payload['rows'] == [{'ticker': 'AAA'}, {'ticker': 'BBB'}]
    assert payload['generated_at'] == payload['as_of']
    # The row's own two clock readings, both on the wire. `built_at` is the
    # later one -- seven seconds of build sit between them -- so a payload that
    # reported one for the other would say a board took no time to make.
    assert payload['as_of'] == as_of.isoformat() + 'Z'
    assert payload['built_at'] == (as_of + seconds(7)).isoformat() + 'Z'
    assert payload['fresh_seconds'] == 120.0
    assert payload['hard_expiry_seconds'] == 600.0
    assert payload['retry_after_ms'] is None
    assert payload['queue_age_seconds'] is None
    assert payload['ops_collected_at'] == payload['as_of']
    assert board_shared.ENVELOPE_KEYS <= set(payload)
    # Served, not enqueued: a fresh board is not work.
    assert shared.row(board_keys.canonical(
        api.parse_query({'market': 'us'}, now=NOW))[0])['queue_state'] == 'idle'


def test_a_board_stamped_in_the_future_is_no_younger_than_new(shared):
    """Two hosts' clocks, one of them ahead. A board whose `as_of` is later
    than this reader's `now` is not evidence of anything except NTP, and the
    honest floor is zero: a negative age renders as `-0.4s ago` on the head and
    lands in a metrics field a dashboard parses as a positive number.
    """
    shared.publish({'market': 'us'}, as_of=NOW + seconds(3))
    payload = read(shared)

    assert payload['age_seconds'] == 0.0
    assert payload['stale'] is False and payload['pending'] is False


@pytest.mark.parametrize('age, stale, pending, why', [
    (120.0, False, False, 'exactly fresh_seconds is still fresh'),
    (120.001, True, False, 'one millisecond past it is stale'),
    (600.0, True, False, 'exactly hard_expiry_seconds still serves'),
    (600.001, False, True, 'one millisecond past it is missing'),
], ids=['120', '120.001', '600', '600.001'])
def test_the_freshness_boundaries_are_where_they_are_documented(
        shared, age, stale, pending, why):
    """Asserted at the millisecond, because a `>=` written as a `>` moves the
    contract by an amount no eye reading the code would catch."""
    shared.publish({'market': 'us'}, as_of=NOW - seconds(age))
    payload = read(shared)

    assert payload['stale'] is stale, why
    assert payload['pending'] is pending, why
    assert (payload['rows'] is None) is pending, why
    if not pending:
        assert payload['age_seconds'] == pytest.approx(age, abs=0.001)


@pytest.mark.parametrize('age, expected_state', [
    (120.001, 'pending'),
    (600.001, 'pending'),
], ids=['stale enqueues a refresh', 'hard-expired enqueues a build'])
def test_an_old_board_is_queued_for_rebuilding_by_the_reader_that_met_it(
        shared, age, expected_state):
    """The reader does not build, but it does ask. Nothing else would: the
    producer sweeps the warm eight, and this key may not be one of them."""
    key_hash = shared.publish({'market': 'us'}, as_of=NOW - seconds(age))
    read(shared)
    assert shared.row(key_hash)['queue_state'] == expected_state


def test_a_stale_board_is_served_with_its_true_age_and_a_retry(shared):
    shared.publish({'market': 'us'}, as_of=NOW - seconds(300))
    payload = read(shared)

    assert payload['stale'] is True and payload['pending'] is False
    assert payload['rows'] is not None
    assert payload['age_seconds'] == pytest.approx(300.0, abs=0.001)
    assert payload['retry_after_ms'] == 5000
    assert payload['queue_age_seconds'] is None
    assert board_shared.ENVELOPE_KEYS <= set(payload)


def test_the_ops_stamp_is_the_rows_own_as_of(shared):
    """`ops_collected_at` dates the frozen spend and ingest figures inside a
    payload, and the row is what knows when this board was read: the summaries
    were collected at the start of the build that wrote it.

    Taken from the row rather than from the blob, even though the producer
    writes the same instant into both. A payload that arrived with some other
    stamp -- a blob written by a build that has since been corrected, a hand
    edit -- would otherwise put an age on the operational figures that the
    board they belong to does not have.
    """
    as_of = NOW - seconds(10)
    query = api.parse_query({'market': 'us'}, now=NOW)
    key_hash, _ = board_keys.canonical(query)
    blob = zlib.compress(json.dumps(
        {**json.loads(zlib.decompress(blob_for(query, as_of=as_of))),
         'ops_collected_at': '1999-01-01T00:00:00Z'}).encode(), 6)
    shared.publish({'market': 'us'}, as_of=as_of)
    with shared.engine.begin() as connection:
        connection.execute(sa.text(
            'update radar_board_results set payload = :blob'
            ' where namespace = :ns and key_hash = :k'
        ).bindparams(sa.bindparam('blob', type_=sa.LargeBinary)),
            {'blob': blob, 'ns': shared.ns, 'k': key_hash})

    payload = read(shared)
    assert payload['ops_collected_at'] == as_of.isoformat() + 'Z'
    assert payload['ops_collected_at'] == payload['as_of']


def test_the_shell_and_the_board_describe_the_same_selection(shared):
    """One question, two answers, and the client draws the same controls from
    either. The shell computes the echo from the parsed query; the board
    carries whatever the producer serialized into the blob. Every field that
    is the QUESTION rather than the answer has to agree, or a board arriving
    after a pending shell would silently redraw the chips, the window buttons
    or the market clock the reader was already looking at.

    The key sets differ by exactly the three frozen operational summaries,
    which are built INTO a payload and which a shell was never built to have.

    Published at the instant the shell was computed for, so that a difference
    in the echo is a difference in how the two paths DERIVE it rather than
    however many seconds of clock separate a build from a read.
    """
    args = {'market': 'de', 'window': '24', 'segment': 'large',
            'sources': 'reddit:wallstreetbets'}
    shell = read(shared, args)
    assert shell['pending'] is True

    shared.publish(args, as_of=NOW)
    board = read(shared, args)
    assert board['pending'] is False

    assert set(board) - set(shell) == {'spend', 'sentiment_ops',
                                       'market_data_ops'}
    assert set(shell) - set(board) == set()
    for field in ('market', 'window_hours', 'segments', 'sources',
                  'all_sources', 'min_venues', 'sort', 'dir',
                  'display_timezone', 'market_venue', 'session',
                  'next_boundary_label', 'next_boundary_at', 'triplet_hours',
                  'series_hours', 'lead_count'):
        assert shell[field] == board[field], field


def test_a_payload_from_another_shape_is_not_read_at_all(shared):
    """The version is what makes a deploy safe: a row the running code can no
    longer decode is missing, not something to try."""
    key_hash = shared.publish({'market': 'us'}, as_of=NOW - seconds(5))
    with shared.engine.begin() as connection:
        connection.execute(sa.text(
            'update radar_board_results set payload_version = 999'
            ' where namespace = :ns and key_hash = :k'),
            {'ns': shared.ns, 'k': key_hash})

    payload = read(shared)
    assert payload['pending'] is True and payload['rows'] is None


# --- a key whose build is failing -------------------------------------------

def test_a_failing_key_goes_on_serving_the_board_it_last_published(shared):
    """`failed` is a queue state, not a verdict on the payload. A board that
    is thirty seconds old is a board, whatever the next build did."""
    shared.publish({'market': 'us'}, as_of=NOW - seconds(30))
    key_hash = shared.fail({'market': 'us'}, now=NOW)
    assert shared.row(key_hash)['last_error'] == 'RuntimeError'

    payload = read(shared)
    assert payload['rows'] is not None
    assert payload['failed'] is True
    assert payload['stale'] is False and payload['pending'] is False
    assert payload['age_seconds'] == pytest.approx(30.0, abs=0.001)


def test_a_failing_key_with_no_board_waits_at_the_slower_rate(shared):
    """Parked: nothing to serve and nothing to hurry. The answer is a pending
    shell that says the build is failing, and asks again in five seconds
    rather than one -- the key is waiting on a clock, not on a queue."""
    key_hash = shared.fail({'market': 'us'}, now=NOW)
    payload = read(shared)

    assert payload['pending'] is True and payload['rows'] is None
    assert payload['failed'] is True
    assert payload['retry_after_ms'] == 5000
    assert payload['queue_age_seconds'] == pytest.approx(0.0, abs=0.001)
    assert shared.row(key_hash)['queue_state'] == 'failed'
    assert board_shared.ENVELOPE_KEYS <= set(payload)


def test_a_pending_shell_says_the_last_build_of_this_key_failed(shared):
    """`failed` on a pending envelope is the row's queue state, not the
    backoff's.

    A key whose backoff has ELAPSED is re-queued by the admission this read
    performs -- an ordinary place in line, at the ordinary retry rate -- but
    the reason it is empty is still that its last build failed, and that is
    what the surface needs in order to say something truer than "loading" to
    somebody who has been waiting through six attempts.

    The second read is the other half of the contract. By then the row is
    `pending`: the failure is over, nothing has failed since, and `failed`
    goes back to false. It says what the row says, which is the only rule that
    cannot drift.
    """
    key_hash = shared.fail({'market': 'us'}, now=NOW, retry_in=-5)
    first = read(shared)

    assert first['pending'] is True and first['rows'] is None
    assert first['failed'] is True, 'the shell forgot why it is empty'
    # Queued, not parked: the ordinary pending curve and not the 5 s backoff.
    assert first['retry_after_ms'] == 1000
    assert shared.row(key_hash)['queue_state'] == 'pending'

    second = read(shared)
    assert second['pending'] is True
    assert second['failed'] is False, (
        'a re-queued key is no longer a failed one')


# --- a key being built ------------------------------------------------------

def test_a_board_being_rebuilt_is_served_while_the_rebuild_runs(shared):
    """`building` is somebody working, not a reason to show nobody anything.
    The board underneath is whatever was last published, with its true age."""
    shared.building({'market': 'us'}, now=NOW, as_of=NOW - seconds(300))
    payload = read(shared)

    assert payload['rows'] is not None
    assert payload['pending'] is False and payload['failed'] is False
    assert payload['stale'] is True, 'a five-minute-old board is stale'
    assert payload['age_seconds'] == pytest.approx(300.0, abs=0.001)


def test_a_first_build_in_flight_is_a_pending_answer_that_waits_for_it(shared):
    """Nothing published yet and a builder already on it: the answer is the
    pending shell, and the admission must leave the claim alone. Re-queueing a
    key that is being built would make a second producer eligible for work
    that is already in flight, and counting a poll as a request would let a
    viewer who waits by asking outrank one who waits by waiting."""
    key_hash = shared.building({'market': 'us'}, now=NOW)
    before = shared.row(key_hash)

    payload = read(shared, poll=True)

    assert payload['pending'] is True and payload['rows'] is None
    assert payload['failed'] is False
    after = shared.row(key_hash)
    assert after['queue_state'] == 'building'
    assert after['request_count'] == before['request_count']
    assert after['lease_expires_at'] == before['lease_expires_at']


# --- the queue --------------------------------------------------------------

def test_the_pending_retry_grows_with_the_queue_ahead_of_this_key(shared):
    """A viewer twelfth in line polling every second is twelve pointless
    round trips a second at the exact moment the queue is longest."""
    shared.seed_pending(5, base=NOW - seconds(100))
    payload = read(shared)

    assert payload['pending'] is True
    assert payload['retry_after_ms'] == 1000 + 500 * 5
    assert payload['queue_age_seconds'] == pytest.approx(0.0, abs=0.001)


def test_the_pending_retry_stops_growing_at_eight_places(shared):
    shared.seed_pending(20, base=NOW - seconds(100))
    assert read(shared)['retry_after_ms'] == 1000 + 500 * 8


def test_a_full_queue_answers_busy_and_writes_nothing(shared):
    """A refused admission costs a round trip and not a row: the row would
    cost a slot that eviction has to pay for later, and a queue that long
    will not reach the key inside anyone's patience anyway."""
    shared.seed_pending(32)
    before = len(shared.rows())

    payload = read(shared)
    assert payload['busy'] is True
    assert payload['pending'] is False
    assert payload['stale'] is False and payload['failed'] is False
    assert payload['rows'] is None
    assert payload['retry_after_ms'] == 5000
    assert payload['queue_age_seconds'] is None
    assert board_shared.ENVELOPE_KEYS <= set(payload)
    assert len(shared.rows()) == before


# --- generations ------------------------------------------------------------

def test_a_board_stored_by_another_generation_is_invisible(
        shared, monkeypatch):
    """A namespace IS a build. The same question answered by a different
    revision or a different configuration is a different answer, and serving
    it would be worse than a cold cache."""
    other = shared.another_namespace()
    board_store.ensure_namespace(shared.engine, other, NOW, revision=REVISION,
                                 payload_version=1)
    shared.publish({'market': 'us'}, as_of=NOW - seconds(10), ns=other)

    assert read(shared)['pending'] is True, 'namespace A saw B\'s board'

    monkeypatch.setattr(board_namespace, 'namespace', lambda: other)
    board_shared.reset_namespace_memo()
    from_other = read(shared)
    assert from_other['pending'] is False
    assert from_other['rows'] is not None


# --- per account ------------------------------------------------------------

@pytest.fixture()
def two_accounts():
    """Two signed-in accounts with different marks, removed afterwards."""
    from werkzeug.security import generate_password_hash
    from models import AppUser

    names = ('pytest radar shared one', 'pytest radar shared two')
    ids = []
    with flask_app.app_context():
        for name in names:
            AppUser.query.filter_by(username=name).delete(
                synchronize_session=False)
        db.session.commit()
        for name in names:
            user = AppUser(username=name,
                           password_hash=generate_password_hash('x'),
                           is_admin=False)
            db.session.add(user)
            db.session.commit()
            ids.append(user.id)
        watch.add(ids[0], 'AAPL')
        watch.add(ids[1], 'TSLA')
    try:
        yield ids
    finally:
        with flask_app.app_context():
            from models import RadarWatch
            RadarWatch.query.filter(RadarWatch.user_id.in_(ids)).delete(
                synchronize_session=False)
            AppUser.query.filter(AppUser.id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()


def test_two_accounts_read_one_board_and_keep_their_own_marks(
        shared, two_accounts, monkeypatch):
    """The blob is viewer-invariant and the marks are added on top of it --
    which is the only reason one stored board can answer everybody."""
    class Entry:
        def __init__(self, ticker):
            self.ticker = ticker

    asked = []

    def pinned(tickers, sources, now, **kwargs):
        asked.append(list(tickers))
        return [Entry(ticker) for ticker in tickers]

    monkeypatch.setattr(board_mod, 'build_pinned_rows', pinned)
    monkeypatch.setattr(api, '_row', lambda entry: {'ticker': entry.ticker})

    key_hash = shared.publish({'market': 'us'}, as_of=NOW - seconds(10))
    first = read(shared, user_id=two_accounts[0])
    second = read(shared, user_id=two_accounts[1])

    assert first['watching'] == ['AAPL'] and second['watching'] == ['TSLA']
    assert first['watch_rows'] == [{'ticker': 'AAPL'}]
    assert second['watch_rows'] == [{'ticker': 'TSLA'}]
    assert asked == [['AAPL'], ['TSLA']]
    assert first['rows'] == second['rows']

    stored = zlib.decompress(shared.row(key_hash)['payload'])
    assert b'AAPL' not in stored and b'TSLA' not in stored
    assert 'watching' not in json.loads(stored)


# --- the capture archive ----------------------------------------------------

def test_capture_reads_nothing_from_the_store_even_with_the_flag_on(
        shared, monkeypatch):
    """The observation archive records what a board SHOWED, so it has to build
    one. Routing it through the cache would file a `pending` shell as an
    observation, or file the same board under two different quarter-hours."""
    calls = []

    def direct(args, now=None, user_id=None):
        calls.append(args)
        return {'rows': [], 'generated_at': 'x', 'watching': [],
                'watch_rows': [], 'spend': {}, 'sentiment_ops': {},
                'market_data_ops': {}}

    def forbidden(*args, **kwargs):
        raise AssertionError('capture read the shared store')

    monkeypatch.setattr(observations, 'build_payload_direct', direct)
    monkeypatch.setattr(board_shared, 'read_payload', forbidden)

    with flask_app.app_context():
        try:
            observations.capture(dt.datetime(2019, 6, 2, 11, 8))
        finally:
            db.session.rollback()
            from models import RadarBoardObservation
            RadarBoardObservation.query.filter(
                RadarBoardObservation.slot_start
                < dt.datetime(2020, 1, 1)).delete(synchronize_session=False)
            db.session.commit()

    assert [args['market'] for args in calls] == ['us', 'de']


# --- the flag off -----------------------------------------------------------

def test_the_flag_off_is_todays_payload_with_the_envelope_on_top(
        disposable, monkeypatch):
    """Byte for byte the board the synchronous path has always built, plus
    the fields that describe how it was delivered -- so the client has one
    shape to render whichever path answered."""
    monkeypatch.delenv('RADAR_BOARD_SHARED_RESULTS', raising=False)
    # A cache of this test's own. `board_cache` is process-global, so a fake
    # board left in the real one would be served to a later test asking the
    # same selection for real -- and the memo assertion below would pass or
    # fail on what some other test had already built.
    monkeypatch.setattr(api, 'board_cache', {})
    builds = _counting_build(monkeypatch)

    with flask_app.app_context():
        payload = api.build_payload({'market': 'us'}, now=NOW)
        again = api.build_payload({'market': 'us'}, now=NOW + seconds(30))

    assert len(builds) == 1, 'the legacy memo was not used'
    assert payload['shared'] is False
    assert payload['pending'] is False and payload['busy'] is False
    assert payload['stale'] is False and payload['failed'] is False
    assert payload['as_of'] == payload['built_at'] == payload['generated_at']
    assert payload['ops_collected_at'] == payload['generated_at']
    assert payload['age_seconds'] == 0.0
    assert payload['retry_after_ms'] is None
    assert payload['queue_age_seconds'] is None
    assert payload['fresh_seconds'] == 120.0
    assert payload['hard_expiry_seconds'] == 600.0
    assert isinstance(payload['rows'], list)
    # A memoised board keeps its own build time, and the age grows with it.
    assert again['generated_at'] == payload['generated_at']
    assert again['age_seconds'] == pytest.approx(30.0, abs=0.001)

    assert set(payload) - board_shared.ENVELOPE_KEYS == {
        'generated_at', 'market', 'display_timezone', 'market_venue',
        'next_boundary_label', 'next_boundary_at', 'sources', 'all_sources',
        'segments', 'session', 'min_venues', 'sort', 'dir', 'venue_counts',
        'window_hours', 'segment_counts', 'excluded', 'spend', 'sentiment_ops',
        'market_data_ops', 'triplet_hours', 'series_hours', 'lead_count',
        'rows', 'watching', 'watch_rows'}


@pytest.mark.parametrize('value, enabled', [
    ('1', True), ('true', True), ('YES', True), (' on ', True),
    ('0', False), ('off', False), ('', False), ('maybe', False),
])
def test_the_flag_is_read_from_the_environment_on_every_call(
        monkeypatch, value, enabled):
    monkeypatch.setenv('RADAR_BOARD_SHARED_RESULTS', value)
    assert api.shared_results_enabled() is enabled


def _counting_build(monkeypatch):
    """`board.build` replaced by a fast fake, as test_radar_board_cache does."""
    calls = []

    def build(sources, now, **kwargs):
        calls.append((tuple(sources), now))
        return board_mod.Board(
            generated_at=now, market=kwargs.get('market', 'us'),
            display_timezone='Europe/Berlin', market_venue='US markets',
            next_boundary_label='closes', next_boundary_at=now,
            sources=list(sources), segments=list(kwargs.get('segments', ())),
            session='regular', min_venues=kwargs.get('min_venues', 1),
            venue_counts={}, window_hours=kwargs.get('window_hours', 4),
            segment_counts={}, excluded={}, rows=[])

    monkeypatch.setattr(board_mod, 'build', build)
    monkeypatch.setattr(api.spend, 'summary', lambda: {})
    monkeypatch.setattr(api.llm_sentiment, 'ops_summary', lambda: {})
    monkeypatch.setattr(api.market_data, 'ops_summary', lambda now: {})
    return calls


# --- the operations surface -------------------------------------------------

def test_ops_reports_the_producer_and_its_queue(shared, client):
    board_store.ensure_namespace(shared.engine, shared.ns, NOW,
                                 revision=REVISION, payload_version=1)
    board_store.heartbeat(shared.engine, shared.ns, 'somehost:42', NOW,
                          success_at=NOW)
    shared.seed_pending(3)

    payload = client.get('/radar/api/ops').get_json()
    results = payload['board_results']

    assert results['namespace'] == shared.ns
    assert results['enabled'] is True
    assert results['producer']['owner'] == 'somehost:42'
    assert results['producer']['seen_at'].endswith('Z')
    assert results['producer']['success_at'].endswith('Z')
    assert results['producer']['error'] is None
    assert results['warm_total'] == 8
    assert results['warm_ready'] == 0
    assert results['queue'] == {'pending': 3, 'building': 0, 'failed_due': 0}
    assert results['on_demand_rows'] == 3


def test_ops_counts_the_standing_boards_this_build_derives(shared, client,
                                                           monkeypatch):
    """`warm_total` is how many standing selections the producer HAS, which is
    the number `warm_ready` is short of.

    Derived rather than read off a limit: the eight come from a cross product
    of markets, segments and windows, and a ninth added to that cross product
    must make the operations page read "8 of 12" rather than a full house it
    is two thirds of. A constant that agreed with the derivation today is a
    constant that would go on agreeing after the derivation moved.
    """
    monkeypatch.setattr(board_producer, 'WARM_WINDOWS', (4, 12, 24))

    results = client.get('/radar/api/ops').get_json()['board_results']
    assert results['warm_total'] == 12
    assert results['warm_ready'] == 0


def test_ops_still_answers_when_the_shared_tables_are_not_there(
        shared, client, monkeypatch):
    """The flag can be on before the migration only by operator error -- and
    that is exactly the moment the operations page has to render."""
    def missing(*args, **kwargs):
        raise sa.exc.ProgrammingError(
            "select ...", {}, Exception("1146, \"Table doesn't exist\""))

    monkeypatch.setattr(board_store, 'health', missing)

    payload = client.get('/radar/api/ops').get_json()
    assert payload['board_results']['error'] == 'table missing'
    assert payload['board_results']['enabled'] is True


def test_ops_is_still_refused_to_a_signed_in_stranger(shared, plain_reader):
    assert plain_reader.get('/radar/api/ops').status_code == 403


@pytest.fixture()
def plain_reader():
    """A signed-in account that is not an admin."""
    from werkzeug.security import generate_password_hash
    from models import AppUser

    name = 'pytest radar shared nonadmin'
    with flask_app.app_context():
        AppUser.query.filter_by(username=name).delete(synchronize_session=False)
        db.session.commit()
        user = AppUser(username=name, password_hash=generate_password_hash('x'),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    flask_app.config['TESTING'] = True
    try:
        with flask_app.test_client() as test_client:
            with test_client.session_transaction() as flask_session:
                flask_session['user_id'] = user_id
            yield test_client
    finally:
        with flask_app.app_context():
            AppUser.query.filter_by(id=user_id).delete(synchronize_session=False)
            db.session.commit()


# --- the metrics line -------------------------------------------------------

def _lines(caplog):
    return [record.getMessage() for record in caplog.records
            if record.name == 'radar.board'
            and record.getMessage().startswith('board read ')]


def _field(line, name):
    return re.search(rf'\b{name}=(\S+)', line).group(1)


def test_every_outcome_writes_one_read_line(shared, caplog):
    """One line per read, and the outcome is the answer the viewer got."""
    with caplog.at_level(logging.INFO, logger='radar.board'):
        read(shared)                                             # pending
        shared.publish({'market': 'de'}, as_of=NOW - seconds(300))
        read(shared, {'market': 'de'})                           # stale
        shared.publish({'market': 'de'}, as_of=NOW - seconds(10))
        read(shared, {'market': 'de'})                           # ready
        shared.seed_pending(32, base=NOW - seconds(500))
        read(shared, {'market': 'us', 'window': '4'})             # busy

    lines = _lines(caplog)
    assert [_field(line, 'outcome') for line in lines] == [
        'pending', 'stale', 'ready', 'busy']
    for line in lines:
        assert _field(line, 'demand') == 'initial'
        assert _field(line, 'class') == 'ondemand'
        assert re.fullmatch(r'[0-9a-f]{12}', _field(line, 'key'))
        assert re.fullmatch(r'\d+', _field(line, 'read_ms'))
        assert re.fullmatch(r'\d+', _field(line, 'account_ms'))
    assert _field(lines[0], 'cache_age') == '-'
    assert _field(lines[0], 'queue_age') == '0.0'
    assert _field(lines[1], 'cache_age') == '300.0'
    assert _field(lines[2], 'cache_age') == '10.0'
    assert _field(lines[3], 'queue_age') == '-'


def test_a_parked_key_is_logged_as_a_failed_read(shared, caplog):
    """`outcome=failed` is a reader that got NOTHING because the key's builds
    are failing. A served board from a failing key is still ready or stale --
    that the key is broken is `log_build`'s line to write, not this one's."""
    shared.fail({'market': 'us'}, now=NOW)
    with caplog.at_level(logging.INFO, logger='radar.board'):
        read(shared)
    assert _field(_lines(caplog)[0], 'outcome') == 'failed'


def test_a_poll_says_so_and_a_warm_row_says_which_class_it_is(shared, caplog):
    key_hash = shared.publish({'market': 'us'}, as_of=NOW - seconds(10))
    with shared.engine.begin() as connection:
        connection.execute(sa.text(
            'update radar_board_results set warm = 1'
            ' where namespace = :ns and key_hash = :k'),
            {'ns': shared.ns, 'k': key_hash})

    with caplog.at_level(logging.INFO, logger='radar.board'):
        read(shared, poll=True)

    line = _lines(caplog)[0]
    assert _field(line, 'demand') == 'poll'
    assert _field(line, 'class') == 'warm'


def test_the_read_line_carries_no_identifier(shared, caplog, two_accounts,
                                             monkeypatch):
    """The vocabulary is closed and the key is twelve hex characters. Nothing
    on this line can be a ticker, an account, a URL or a query string -- so the
    read below is made as loudly identifiable as a read can be: a named
    account, its own mark, and one subreddit in the selection."""
    monkeypatch.setattr(board_mod, 'build_pinned_rows', lambda *a, **k: [])
    shared.publish({'market': 'us', 'sources': 'reddit:wallstreetbets'},
                   as_of=NOW - seconds(10))
    with caplog.at_level(logging.INFO, logger='radar.board'):
        read(shared, {'market': 'us', 'sources': 'reddit:wallstreetbets'},
             user_id=two_accounts[0])

    line = _lines(caplog)[0]
    assert 'wallstreetbets' not in line and 'reddit' not in line
    assert 'AAPL' not in line
    # The whole line, not a list of things it must not contain: a field this
    # test never thought of is the way an identifier would actually arrive.
    assert re.fullmatch(
        r'board read demand=\w+ class=\w+ key=[0-9a-f]{12} outcome=\w+ '
        r'cache_age=[\d.-]+ queue_age=[\d.-]+ read_ms=\d+ account_ms=\d+',
        line)
