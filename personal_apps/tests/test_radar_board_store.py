"""The board result store, against the real database it is written for.

Everything here that matters is a race, a bound or a fence, and none of the
three can be proved against a mock. `ON DUPLICATE KEY UPDATE` deduplicating two
simultaneous admissions, `SELECT ... FOR UPDATE` on the control row keeping two
processes from both deciding there is room for one more job, `UPDATE ... WHERE
lease_token = ...` refusing a builder that no longer holds its lease -- each of
those is a property of MySQL, not of this module, and a fake that agreed with
the code would only prove the code agrees with itself. So the tests run on the
disposable database, the concurrent ones use real threads on real pooled
connections, and each one works inside a namespace of its own so they neither
see nor evict each other's rows.

Time is passed in, never read: every timestamp below is derived from one fixed
moment, which is what makes a lease expiry or a backoff boundary something to
assert rather than something to wait for.
"""
import dataclasses
import datetime as dt
import json
import hashlib
import secrets
import threading
import zlib

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import board_keys, board_namespace, board_store

DISPOSABLE = 'personal_apps_radar_perf3'

# One fixed instant. Naive UTC, the way every timestamp in these tables is.
NOW = dt.datetime(2026, 9, 10, 12, 0, 0)

REVISION = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0'


def seconds(count):
    return dt.timedelta(seconds=count)


def key(name):
    """A (key_hash, key_json) pair.

    The store never decodes `key_json` -- checking that it still means what its
    hash says is the producer's job -- so most tests need only a pair that is
    distinct and self-consistent. `test_a_real_key_and_a_real_payload_survive`
    puts a genuine canonical key through the same path.
    """
    key_json = json.dumps({'v': 2, 'name': name}, sort_keys=True,
                          separators=(',', ':'))
    return hashlib.sha256(key_json.encode('utf-8')).hexdigest(), key_json


class _Store:
    """The engine plus the namespaces one test is allowed to touch."""

    def __init__(self, engine):
        self.engine = engine
        self.namespaces = []
        self.ns = self.namespace()

    def namespace(self, now=NOW, *, revision=REVISION, introduce=True):
        """A namespace this test owns, cleaned up whatever happens to it.

        `introduce=False` skips `ensure_namespace`, which is how a generation
        looks before any producer has spoken: whichever reader touches it first
        adopts the control row, revision unknown.
        """
        name = 'perf3test-' + secrets.token_hex(20)
        self.namespaces.append(name)
        if introduce:
            board_store.ensure_namespace(self.engine, name, now,
                                         revision=revision, payload_version=1)
        return name

    def rows(self, ns=None):
        with self.engine.connect() as connection:
            return connection.execute(sa.text(
                'select * from radar_board_results where namespace = :ns'
                ' order by requested_at, key_hash'),
                {'ns': ns or self.ns}).mappings().all()

    def row(self, key_hash, ns=None):
        """The raw row, for the columns `Result` deliberately does not carry."""
        with self.engine.connect() as connection:
            return connection.execute(sa.text(
                'select * from radar_board_results'
                ' where namespace = :ns and key_hash = :k'),
                {'ns': ns or self.ns, 'k': key_hash}).mappings().first()

    def read(self, key_hash, ns=None):
        return board_store.read(self.engine, ns or self.ns, key_hash)

    def admit(self, pair, now=NOW, **kwargs):
        return board_store.admit(self.engine, self.ns, pair[0], pair[1], now,
                                 **kwargs)

    def seed(self, count, *, prefix, base=NOW, state='idle', warm=0,
             step=seconds(1), ns=None):
        """Rows in the shape a producer leaves behind, inserted directly.

        Eviction needs 128 rows in one namespace and admission refuses the
        33rd job, so 128 rows cannot be admitted as pending -- which is not a
        limitation of the test but the very interaction it is set among. A
        published row is `idle`, and 128 of those are what a busy generation
        actually looks like.
        """
        pairs = [key(f'{prefix}{index}') for index in range(count)]
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                'insert into radar_board_results'
                ' (namespace, key_hash, key_json, payload_version,'
                '  queue_state, warm, requested_at, request_count, attempts)'
                ' values (:ns, :k, :j, 1, :state, :warm, :at, 1, 0)'),
                [{'ns': ns or self.ns, 'k': pair[0], 'j': pair[1],
                  'state': state, 'warm': warm, 'at': base + step * index}
                 for index, pair in enumerate(pairs)])
        return pairs


@pytest.fixture
def store():
    """A namespace of this test's own, on the disposable database only."""
    with flask_app.app_context():
        if db.engine.url.database != DISPOSABLE:
            pytest.skip(f'not the disposable database: {db.engine.url.database}')
        engine = db.engine
        with engine.connect() as connection:
            if not connection.execute(sa.text(
                    "show tables like 'radar_board_results'")).first():
                pytest.fail('radar_board_results is missing: run '
                            'PYTHONPATH=. FLASK_APP=app.py py -3.12 -m flask '
                            'db upgrade first')
        owned = _Store(engine)
        try:
            yield owned
        finally:
            with engine.begin() as connection:
                for name in owned.namespaces:
                    connection.execute(sa.text(
                        'delete from radar_board_results where namespace = :ns'),
                        {'ns': name})
                    connection.execute(sa.text(
                        'delete from radar_board_namespaces'
                        ' where namespace = :ns'), {'ns': name})


# --- limits ----------------------------------------------------------------

def test_the_limits_are_the_documented_defaults_and_move_with_the_environment(
        monkeypatch):
    """Read on every call, so a test can change one without a restart -- and so
    an operator can, which is the only reason they are environment variables."""
    base = board_store.limits()
    assert (base.fresh_seconds, base.hard_expiry_seconds, base.refresh_seconds,
            base.lease_seconds, base.max_queue, base.max_on_demand,
            base.max_attempts, base.park_seconds, base.retire_seconds,
            base.warm_limit) == (120, 600, 120, 120, 32, 128, 6, 900, 86400, 8)

    monkeypatch.setenv('RADAR_BOARD_MAX_QUEUE', '3')
    monkeypatch.setenv('RADAR_BOARD_FRESH_SECONDS', '15')
    monkeypatch.setenv('RADAR_BOARD_NAMESPACE_RETIRE_SECONDS', '60')
    changed = board_store.limits()
    assert changed.max_queue == 3
    assert changed.fresh_seconds == 15
    assert changed.retire_seconds == 60
    assert changed.max_on_demand == 128, 'an untouched limit moved'


def test_a_limit_the_environment_got_wrong_is_refused_by_name(monkeypatch):
    """Loudly, and naming the variable -- in the process an operator starts.

    This used to be `limits()` itself raising, on the argument that falling
    back to a default would let a typo silently restore a bound the operator
    meant to move. That argument still holds for the producer, and it is where
    the check now lives. It stopped holding for `limits()` once the reader
    path began calling it: `_direct_envelope` reads it on every synchronous
    build, so a typo took down `/radar/` and `/radar/api/board` WITH THE FLAG
    OFF -- the rollback path, and the one path that must not depend on a knob
    only the shared path uses. See the read-path test below.
    """
    monkeypatch.setenv('RADAR_BOARD_MAX_QUEUE', 'thirty-two')
    with pytest.raises(board_namespace.ConfigError) as refused:
        board_store.validate_limits()
    assert 'RADAR_BOARD_MAX_QUEUE' in str(refused.value)
    assert 'thirty-two' in str(refused.value)

    monkeypatch.setenv('RADAR_BOARD_MAX_QUEUE', '32')
    monkeypatch.setenv('RADAR_BOARD_LEASE_SECONDS', 'two minutes')
    with pytest.raises(board_namespace.ConfigError) as refused:
        board_store.validate_limits()
    assert 'RADAR_BOARD_LEASE_SECONDS' in str(refused.value)


@pytest.mark.parametrize('name, raw', [
    # Not a number at all.
    ('RADAR_BOARD_FRESH_SECONDS', 'abc'),
    ('RADAR_BOARD_MAX_QUEUE', 'thirty-two'),
    # A number, and not a bound. Zero admitted jobs is not a tighter queue, it
    # is a queue that answers `busy` for ever; a lease of zero seconds has
    # expired before the builder reads it.
    ('RADAR_BOARD_MAX_QUEUE', '0'),
    ('RADAR_BOARD_MAX_ON_DEMAND', '-1'),
    ('RADAR_BOARD_LEASE_SECONDS', '0'),
    # A negative duration is not a shorter one: -5 marks every board stale the
    # instant it is built.
    ('RADAR_BOARD_FRESH_SECONDS', '-5'),
    ('RADAR_BOARD_HARD_EXPIRY_SECONDS', '-1'),
    ('RADAR_BOARD_REFRESH_SECONDS', '-0.5'),
    ('RADAR_BOARD_PARK_SECONDS', '-900'),
    ('RADAR_BOARD_NAMESPACE_RETIRE_SECONDS', '-1'),
    ('RADAR_BOARD_MAX_ATTEMPTS', '-6'),
])
def test_a_limit_the_environment_got_wrong_is_ignored_by_readers(
        monkeypatch, name, raw):
    """Every reader answers, on the default, whatever the variable says.

    Both of these used to get through. A non-numeric value raised out of
    `limits()` uncaught; a nonsense-but-numeric one was obeyed, so
    `RADAR_BOARD_MAX_QUEUE=0` answered every on-demand admission `busy` for
    ever and `RADAR_BOARD_FRESH_SECONDS=-5` marked every board stale.
    """
    monkeypatch.setenv(name, raw)
    assert board_store.limits() == board_store.Limits()


def test_the_flag_off_envelope_survives_any_value_of_the_tuning_variables(
        monkeypatch):
    """The rollback path, which must not depend on a knob it does not use.

    `_direct_envelope` reads `limits()` for the two bounds it reports, so the
    new parsing runs on every synchronous build. A 500 here is `/radar/`,
    `/radar/hub/` and `/radar/api/board` down with the flag off.
    """
    from features.radar.routes import api

    monkeypatch.setenv('RADAR_BOARD_FRESH_SECONDS', 'abc')
    monkeypatch.setenv('RADAR_BOARD_MAX_QUEUE', '0')
    envelope = api._direct_envelope(NOW, NOW + seconds(30))
    assert envelope['shared'] is False
    assert envelope['fresh_seconds'] == board_store.Limits().fresh_seconds
    assert envelope['hard_expiry_seconds'] == (
        board_store.Limits().hard_expiry_seconds)
    assert envelope['age_seconds'] == 30


def test_a_limit_the_environment_got_wrong_is_said_once_in_the_log(
        monkeypatch, caplog):
    """Said, because a reader silently running on defaults is its own trap --
    and said once per value, because `limits()` runs on every request."""
    monkeypatch.setattr(board_store, '_COMPLAINED', set())
    monkeypatch.setenv('RADAR_BOARD_MAX_QUEUE', '0')
    with caplog.at_level('ERROR', logger='features.radar.board_store'):
        for _ in range(3):
            board_store.limits()
    said = [record for record in caplog.records
            if 'RADAR_BOARD_MAX_QUEUE' in record.getMessage()]
    assert len(said) == 1
    assert '0' in said[0].getMessage()


# --- admission -------------------------------------------------------------

def test_admit_of_a_missing_key_creates_one_pending_row(store):
    pair = key('cold')
    assert store.admit(pair) == 'pending'

    result = store.read(pair[0])
    assert result.queue_state == 'pending'
    assert result.enqueued_at == NOW
    assert result.requested_at == NOW
    assert result.request_count == 1
    assert result.key_json == pair[1]
    assert result.warm is False
    assert result.payload is None and result.as_of is None
    assert result.attempts == 0 and result.next_attempt_at is None
    assert len(store.rows()) == 1


def test_read_of_a_key_nobody_asked_for_is_none(store):
    assert store.read(key('never')[0]) is None


def test_two_racing_admits_leave_one_row_and_two_recorded_requests(store):
    """The cross-process deduplication an in-process single-flight cannot do.
    Two threads, two pooled connections, one primary key."""
    pair = key('race')
    gate = threading.Barrier(3, timeout=15)
    connection_ids = []
    trouble = []

    def racer():
        try:
            with store.engine.connect() as connection:
                connection_ids.append(connection.execute(
                    sa.text('select connection_id()')).scalar())
                # Both connections are open here, so the two admissions below
                # really are running against two sessions of the database.
                gate.wait()
                store.admit(pair)
        except BaseException as problem:                     # noqa: BLE001
            trouble.append(problem)

    threads = [threading.Thread(target=racer) for _ in range(2)]
    for thread in threads:
        thread.start()
    gate.wait()
    for thread in threads:
        thread.join(timeout=15)

    assert not trouble, trouble
    assert len(set(connection_ids)) == 2, connection_ids
    assert len(store.rows()) == 1, 'the race created a second row'
    result = store.read(pair[0])
    assert result.request_count == 2
    assert result.enqueued_at == NOW

    # And a later admission of the same pending key records the demand without
    # moving the row's place in the queue.
    assert store.admit(pair, NOW + seconds(300)) == 'pending'
    result = store.read(pair[0])
    assert result.enqueued_at == NOW, 'a repeat admission jumped the queue'
    assert result.requested_at == NOW + seconds(300)
    assert result.request_count == 3


def test_a_poll_moves_neither_the_request_count_nor_the_queue(store):
    pair = key('poll')
    store.admit(pair)

    assert store.admit(pair, NOW + seconds(60), poll=True) == 'pending'

    result = store.read(pair[0])
    assert result.request_count == 1, 'a poll counted as a new request'
    assert result.enqueued_at == NOW
    # Demand is still recorded: a viewer still watching is a reason to keep
    # the row alive when eviction comes looking for the least wanted one.
    assert result.requested_at == NOW + seconds(60)


def test_a_poll_still_creates_a_row_that_is_no_longer_there(store):
    """The result may have been evicted between the first ask and the poll.
    Answering `pending` without a row would poll forever against nothing."""
    pair = key('poll-cold')
    assert store.admit(pair, poll=True) == 'pending'

    result = store.read(pair[0])
    assert result.queue_state == 'pending'
    assert result.request_count == 0
    assert result.enqueued_at == NOW


def test_admit_of_a_building_key_does_not_disturb_the_build(store):
    pair = key('mid-build')
    store.admit(pair)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')

    assert store.admit(pair, NOW + seconds(5)) == 'building'

    result = store.read(pair[0])
    assert result.queue_state == 'building'
    assert result.enqueued_at == NOW
    assert store.row(pair[0])['lease_token'] == claim.token


def test_the_thirty_third_on_demand_key_is_refused_and_nothing_is_written(
        store):
    limits = board_store.limits()
    for index in range(limits.max_queue):
        assert store.admit(key(f'queued{index}')) == 'pending'
    before = len(store.rows())

    overflow = key('overflow')
    assert store.admit(overflow) == 'busy'

    assert len(store.rows()) == before == limits.max_queue
    assert store.read(overflow[0]) is None, 'a refused admission wrote a row'


def test_a_warm_admission_is_never_refused(store):
    limits = board_store.limits()
    for index in range(limits.max_queue):
        store.admit(key(f'queued{index}'))

    warm = key('warm-past-the-cap')
    assert store.admit(warm, warm=True) == 'pending'

    result = store.read(warm[0])
    assert result.warm is True
    assert result.queue_state == 'pending'


def test_a_failed_row_inside_its_backoff_is_parked_and_left_alone(store):
    pair = key('sad')
    store.admit(pair)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')
    assert board_store.fail(store.engine, store.ns, claim, 'RuntimeError',
                            NOW) is True
    backoff_until = store.read(pair[0]).next_attempt_at
    assert backoff_until == NOW + seconds(30)

    assert store.admit(pair, NOW + seconds(10)) == 'parked'

    result = store.read(pair[0])
    assert result.queue_state == 'failed'
    assert result.next_attempt_at == backoff_until, 'a reader shortened a backoff'
    assert result.enqueued_at == NOW
    assert result.attempts == 1
    # The demand itself is still recorded; only the retry clock is untouchable.
    assert result.request_count == 2
    assert result.requested_at == NOW + seconds(10)


def test_a_failed_row_past_its_backoff_counts_toward_the_cap(store):
    """A key waiting to be retried is a job, and a job is what the 32 counts."""
    limits = board_store.limits()
    failed = key('failed-due')
    store.admit(failed)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')
    board_store.fail(store.engine, store.ns, claim, 'RuntimeError', NOW)

    later = NOW + seconds(60)                       # past the 30 s backoff
    for index in range(limits.max_queue - 1):
        assert store.admit(key(f'queued{index}'), later) == 'pending'

    assert store.admit(key('one-too-many'), later) == 'busy'

    # A key already inside the count is never refused by the count it is in.
    assert store.admit(failed, later) == 'pending'
    assert store.admit(key('still-too-many'), later) == 'busy'
    assert len(store.rows()) == limits.max_queue


# --- eviction --------------------------------------------------------------

def test_the_hundred_and_twenty_ninth_row_evicts_the_least_wanted(store):
    limits = board_store.limits()
    seeded = store.seed(limits.max_on_demand, prefix='held')

    newcomer = key('newcomer')
    assert store.admit(newcomer, NOW + seconds(9999)) == 'pending'

    assert len(store.rows()) == limits.max_on_demand
    assert store.read(seeded[0][0]) is None, 'the oldest row survived'
    assert store.read(seeded[1][0]) is not None
    assert store.read(newcomer[0]) is not None, 'the new row evicted itself'


def test_eviction_steps_over_a_build_in_flight(store):
    """An active claim is never evicted. Deleting the row under a builder is
    exactly the shape that lets a stale result be published later."""
    limits = board_store.limits()
    seeded = store.seed(limits.max_on_demand, prefix='held')
    oldest = seeded[0]
    with store.engine.begin() as connection:
        connection.execute(sa.text(
            "update radar_board_results set queue_state = 'building',"
            " lease_owner = 'owner-1', lease_token = :token,"
            " lease_expires_at = :expires"
            ' where namespace = :ns and key_hash = :k'),
            {'token': 'f' * 32, 'expires': NOW + seconds(9999),
             'ns': store.ns, 'k': oldest[0]})

    store.admit(key('newcomer'), NOW + seconds(9999))

    assert store.read(oldest[0]) is not None, 'a build in flight was evicted'
    assert store.read(seeded[1][0]) is None, 'the next oldest was not evicted'
    assert len(store.rows()) == limits.max_on_demand


def test_the_generation_lock_admits_exactly_one_job_when_only_one_fits(
        store, monkeypatch):
    """The bound the control row exists for.

    Eight threads arrive at the same instant with eight different keys and room
    for one. Without a lock every one of them counts an empty queue and every
    one of them is admitted -- which is the whole reason this is a row lock in
    the database rather than a lock in a Python process, since in production
    the eight are separate gunicorn workers that share no memory at all.
    """
    monkeypatch.setenv('RADAR_BOARD_MAX_QUEUE', '1')
    gate = threading.Barrier(9, timeout=20)
    answers = []
    trouble = []

    def racer(index):
        try:
            gate.wait()
            answers.append(store.admit(key(f'contender{index}')))
        except BaseException as problem:                     # noqa: BLE001
            trouble.append(problem)

    threads = [threading.Thread(target=racer, args=(index,))
               for index in range(8)]
    for thread in threads:
        thread.start()
    gate.wait()
    for thread in threads:
        thread.join(timeout=20)

    assert not trouble, trouble
    assert sorted(answers) == ['busy'] * 7 + ['pending'], answers
    assert len(store.rows()) == 1, 'the cap of one admitted more than one job'


def test_eviction_never_removes_the_row_the_admission_just_created(
        store, monkeypatch):
    """Every older row is being built, so the only row eviction may take is the
    one that just arrived -- and taking it would answer `pending` for a key
    with no row behind it, which polls forever."""
    monkeypatch.setenv('RADAR_BOARD_MAX_QUEUE', '500')
    limits = board_store.limits()
    store.seed(limits.max_on_demand, prefix='busy', state='building')

    newcomer = key('newcomer')
    assert store.admit(newcomer, NOW + seconds(9999)) == 'pending'

    assert store.read(newcomer[0]) is not None
    # Nothing could be evicted, so the bound is briefly exceeded -- which is
    # the honest outcome: a bound cannot be enforced against active builds.
    assert len(store.rows()) == limits.max_on_demand + 1


def test_evict_leaves_the_warm_rows_alone(store):
    limits = board_store.limits()
    warm = store.seed(4, prefix='warm', warm=1)
    store.seed(limits.max_on_demand + 5, prefix='held', base=NOW + seconds(10))

    removed = board_store.evict(store.engine, store.ns, NOW + seconds(9999))

    assert removed == 5
    for pair in warm:
        assert store.read(pair[0]) is not None, 'a warm row was evicted'
    assert len(store.rows()) == limits.max_on_demand + len(warm)


# --- claiming --------------------------------------------------------------

def test_claim_returns_nothing_when_there_is_nothing_to_do(store):
    assert board_store.claim(store.engine, store.ns, 'owner-1', NOW) is None
    store.seed(3, prefix='published')            # idle rows are not work
    assert board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                             prefer='demand') is None


def test_claim_takes_a_fenced_lease_on_a_pending_row(store):
    limits = board_store.limits()
    pair = key('claimable')
    store.admit(pair)

    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')

    assert claim.key_hash == pair[0]
    assert claim.key_json == pair[1]
    assert claim.owner == 'owner-1'
    assert claim.warm is False
    assert claim.enqueued_at == NOW
    assert claim.attempts == 1
    assert len(claim.token) == 32 and int(claim.token, 16) >= 0

    row = store.row(pair[0])
    assert row['queue_state'] == 'building'
    assert row['lease_owner'] == 'owner-1'
    assert row['lease_token'] == claim.token
    assert row['lease_expires_at'] == NOW + seconds(limits.lease_seconds)
    assert row['attempts'] == 1


def test_a_live_lease_holds_and_an_expired_one_is_reclaimed_under_a_new_token(
        store):
    limits = board_store.limits()
    pair = key('leased')
    store.admit(pair)
    first = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')

    still_leased = NOW + seconds(limits.lease_seconds)
    assert board_store.claim(store.engine, store.ns, 'owner-2', still_leased,
                             prefer='demand') is None

    expired = still_leased + seconds(1)
    second = board_store.claim(store.engine, store.ns, 'owner-2', expired,
                               prefer='demand')
    assert second is not None
    assert second.owner == 'owner-2'
    assert second.token != first.token, 'the lease was handed on, not reissued'
    assert second.attempts == 2
    assert store.row(pair[0])['lease_expires_at'] == expired + seconds(
        limits.lease_seconds)


def test_claim_serves_only_the_class_it_was_asked_for(store):
    warm = key('warm-work')
    demand = key('demand-work')
    store.admit(warm, warm=True)
    store.admit(demand)

    warm_claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                                   prefer='warm')
    demand_claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                                     prefer='demand')
    assert warm_claim.key_hash == warm[0] and warm_claim.warm is True
    assert demand_claim.key_hash == demand[0] and demand_claim.warm is False

    # With nothing of the preferred class left, `claim` says so rather than
    # quietly serving the other -- the caller alternates, and it can only do
    # that if it is told which class was empty.
    board_store.publish(store.engine, store.ns, warm_claim, b'x',
                        as_of=NOW, built_at=NOW, build_ms=1,
                        producer_revision=REVISION)
    assert board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                             prefer='warm') is None


def _publish_warm(store, pair, as_of):
    """Introduce one warm key and build it, so its `as_of` is known.

    One at a time on purpose: with several due at once the claim order is the
    very thing under test, and a fixture that assumed it would prove nothing.
    """
    board_store.refresh_warm(store.engine, store.ns, [pair], NOW)
    claim = board_store.claim(store.engine, store.ns, 'setup', NOW,
                              prefer='warm')
    assert claim.key_hash == pair[0], 'a never-built warm key is claimed first'
    board_store.publish(store.engine, store.ns, claim, b'x', as_of=as_of,
                        built_at=as_of, build_ms=1,
                        producer_revision=REVISION)


def test_warm_claims_come_oldest_first_with_the_never_built_ahead_of_them(
        store):
    """A board nobody has ever built is infinitely stale, and the sweep has to
    treat it that way or the eight standing boards never all become ready."""
    older, newer, never = key('older'), key('newer'), key('never')
    _publish_warm(store, older, NOW - seconds(900))
    _publish_warm(store, newer, NOW - seconds(400))

    board_store.refresh_warm(store.engine, store.ns, [older, newer, never],
                             NOW)
    for pair in (older, newer, never):
        assert store.read(pair[0]).queue_state == 'pending'

    order = []
    for _ in range(3):
        claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                                  prefer='warm')
        assert claim is not None
        order.append(claim.key_hash)
        board_store.publish(store.engine, store.ns, claim, b'x', as_of=NOW,
                            built_at=NOW, build_ms=1,
                            producer_revision=REVISION)
    assert order == [never[0], older[0], newer[0]]


# --- publishing and failing ------------------------------------------------

def test_publish_stores_the_board_and_lets_the_lease_go(store):
    pair = key('publishable')
    store.admit(pair)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')
    blob = zlib.compress(json.dumps({'rows': list(range(400))}).encode('utf-8'))
    as_of = NOW + seconds(1)
    built_at = NOW + seconds(4)

    assert board_store.publish(store.engine, store.ns, claim, blob,
                               as_of=as_of, built_at=built_at, build_ms=3210,
                               producer_revision=REVISION) is True

    result = store.read(pair[0])
    assert result.queue_state == 'idle'
    assert result.payload == blob
    assert result.as_of == as_of
    assert result.built_at == built_at
    assert result.build_ms == 3210
    assert result.payload_version == board_namespace.PAYLOAD_VERSION
    assert result.attempts == 0
    assert result.last_error is None
    assert result.next_attempt_at is None
    assert result.lease_expires_at is None

    row = store.row(pair[0])
    assert row['payload_bytes'] == len(blob)
    assert row['producer_revision'] == REVISION
    assert row['lease_owner'] is None and row['lease_token'] is None


def test_publish_under_a_token_that_is_no_longer_held_changes_nothing(store):
    pair = key('overtaken')
    store.admit(pair)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')
    stale = dataclasses.replace(claim, token='0' * 32)

    assert board_store.publish(store.engine, store.ns, stale, b'nonsense',
                               as_of=NOW, built_at=NOW, build_ms=1,
                               producer_revision=REVISION) is False
    assert board_store.fail(store.engine, store.ns, stale, 'RuntimeError',
                            NOW) is False

    result = store.read(pair[0])
    assert result.queue_state == 'building'
    assert result.payload is None
    assert store.row(pair[0])['lease_token'] == claim.token


def test_a_builder_whose_row_was_evicted_and_recreated_cannot_publish(store):
    """The defect a counting fence cannot close. The recreated row's counter
    starts again at zero, so the abandoned builder's number matches it; an
    unguessable token does not come back."""
    limits = board_store.limits()
    pair = key('evicted')
    store.admit(pair)
    first = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')

    expired = NOW + seconds(limits.lease_seconds + 1)
    second = board_store.claim(store.engine, store.ns, 'owner-2', expired,
                               prefer='demand')
    assert second.token != first.token
    assert board_store.publish(store.engine, store.ns, second, b'the-board',
                               as_of=expired, built_at=expired, build_ms=5,
                               producer_revision=REVISION) is True

    store.seed(limits.max_on_demand, prefix='newer', base=NOW + seconds(10))
    assert board_store.evict(store.engine, store.ns, expired) == 1
    assert store.read(pair[0]) is None, 'the row under test was not evicted'

    recreated = NOW + seconds(5000)
    assert store.admit(pair, recreated) == 'pending'

    assert board_store.publish(store.engine, store.ns, first, b'stale-board',
                               as_of=NOW, built_at=NOW, build_ms=5,
                               producer_revision=REVISION) is False
    assert board_store.fail(store.engine, store.ns, first, 'RuntimeError',
                            recreated) is False
    assert board_store.publish(store.engine, store.ns, second, b'older-board',
                               as_of=expired, built_at=expired, build_ms=5,
                               producer_revision=REVISION) is False

    result = store.read(pair[0])
    assert result.queue_state == 'pending'
    assert result.payload is None
    assert result.attempts == 0


def test_fail_backs_off_and_keeps_the_board_it_already_had(store):
    """A failed rebuild is not a reason to stop serving last night's answer."""
    pair = key('was-good')
    store.admit(pair)
    good = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                             prefer='demand')
    blob = zlib.compress(b'the good board')
    board_store.publish(store.engine, store.ns, good, blob, as_of=NOW,
                        built_at=NOW, build_ms=7, producer_revision=REVISION)

    later = NOW + seconds(600)
    store.admit(pair, later)
    doomed = board_store.claim(store.engine, store.ns, 'owner-1', later,
                               prefer='demand')
    assert board_store.fail(store.engine, store.ns, doomed, 'RuntimeError',
                            later) is True

    result = store.read(pair[0])
    assert result.queue_state == 'failed'
    assert result.next_attempt_at == later + seconds(30)
    assert result.last_error == 'RuntimeError'
    assert result.attempts == 1
    assert result.payload == blob, 'the previous board was thrown away'
    assert result.as_of == NOW
    assert result.build_ms == 7
    row = store.row(pair[0])
    assert row['lease_owner'] is None and row['lease_token'] is None


def test_the_backoff_doubles_and_then_the_row_is_parked(store):
    limits = board_store.limits()
    pair = key('hopeless')
    store.admit(pair)

    delays = []
    moment = NOW
    for _ in range(limits.max_attempts + 1):
        claim = board_store.claim(store.engine, store.ns, 'owner-1', moment,
                                  prefer='demand')
        assert claim is not None, f'not claimable at {moment}'
        assert board_store.fail(store.engine, store.ns, claim, 'RuntimeError',
                                moment) is True
        result = store.read(pair[0])
        delays.append((result.next_attempt_at - moment).total_seconds())
        moment = result.next_attempt_at

    assert delays == [30, 60, 120, 240, 480, 900, 900]
    assert store.read(pair[0]).attempts == limits.max_attempts, (
        'attempts kept climbing past the cap')


def test_a_parked_row_waits_the_park_interval_and_not_the_doubled_backoff(
        store, monkeypatch):
    """Two different rules that happen to meet at 900 s under the defaults --
    `min(30 * 2 ** 5, 900)` is also 900 -- so a park that had quietly become
    the ceiling would look identical. Moving `park_seconds` tells them apart.
    """
    monkeypatch.setenv('RADAR_BOARD_PARK_SECONDS', '1800')
    limits = board_store.limits()
    assert limits.park_seconds == 1800
    pair = key('parked')
    store.admit(pair)

    delays = []
    moment = NOW
    for _ in range(limits.max_attempts):
        claim = board_store.claim(store.engine, store.ns, 'owner-1', moment,
                                  prefer='demand')
        board_store.fail(store.engine, store.ns, claim, 'RuntimeError', moment)
        result = store.read(pair[0])
        delays.append((result.next_attempt_at - moment).total_seconds())
        moment = result.next_attempt_at

    assert delays == [30, 60, 120, 240, 480, 1800]


def test_a_long_error_is_stored_at_the_width_the_column_has(store):
    pair = key('shouty')
    store.admit(pair)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')

    board_store.fail(store.engine, store.ns, claim, 'E' * 400, NOW)

    assert store.read(pair[0]).last_error == 'E' * 255


# --- the warm sweep --------------------------------------------------------

def test_refresh_warm_adopts_the_warm_keys_and_enqueues_the_due_ones(store):
    limits = board_store.limits()
    warm = [key(f'warm{index}') for index in range(limits.warm_limit)]

    assert board_store.refresh_warm(store.engine, store.ns, warm, NOW) == 8

    for pair in warm:
        result = store.read(pair[0])
        assert result.warm is True
        assert result.queue_state == 'pending'
        assert result.enqueued_at == NOW
        assert result.request_count == 0, 'a sweep counted as viewer demand'

    # A row already pending is not re-enqueued, and its place is not moved.
    assert board_store.refresh_warm(store.engine, store.ns, warm,
                                    NOW + seconds(300)) == 0
    assert store.read(warm[0][0]).enqueued_at == NOW


def test_refresh_warm_waits_exactly_the_refresh_interval(store):
    limits = board_store.limits()
    pair = key('warm-fresh')
    board_store.refresh_warm(store.engine, store.ns, [pair], NOW)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='warm')
    as_of = NOW + seconds(1)
    board_store.publish(store.engine, store.ns, claim, b'board', as_of=as_of,
                        built_at=as_of, build_ms=1, producer_revision=REVISION)

    just_short = as_of + seconds(limits.refresh_seconds) - seconds(1)
    assert board_store.refresh_warm(store.engine, store.ns, [pair],
                                    just_short) == 0
    assert store.read(pair[0]).queue_state == 'idle'

    due = as_of + seconds(limits.refresh_seconds)
    assert board_store.refresh_warm(store.engine, store.ns, [pair], due) == 1
    result = store.read(pair[0])
    assert result.queue_state == 'pending'
    assert result.enqueued_at == due
    assert result.payload == b'board', 'the refresh discarded the live board'


def test_refresh_warm_never_disturbs_a_build_in_flight(store):
    pair = key('warm-building')
    board_store.refresh_warm(store.engine, store.ns, [pair], NOW)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='warm')

    assert board_store.refresh_warm(store.engine, store.ns, [pair],
                                    NOW + seconds(9999)) == 0

    row = store.row(pair[0])
    assert row['queue_state'] == 'building'
    assert row['lease_token'] == claim.token


def test_a_warm_key_whose_build_failed_backs_off_before_it_is_swept_again(
        store):
    """The one row that is warm and broken at the same time.

    The sweep moves `idle` rows only, so a warm key inside its backoff has to
    be left to its clock exactly like an on-demand one -- otherwise the eight
    standing boards would each retry every tick, which is the fastest possible
    loop against whatever is failing. Once the clock runs out the ordinary
    warm claim picks it up again, with no sweep in between.
    """
    pair = key('warm-broken')
    board_store.refresh_warm(store.engine, store.ns, [pair], NOW)
    first = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='warm')
    assert board_store.fail(store.engine, store.ns, first, 'RuntimeError',
                            NOW) is True
    retry_at = store.read(pair[0]).next_attempt_at
    assert retry_at == NOW + seconds(30)

    inside = NOW + seconds(10)
    assert board_store.refresh_warm(store.engine, store.ns, [pair],
                                    inside) == 0, 'the sweep restarted a backoff'
    result = store.read(pair[0])
    assert result.queue_state == 'failed'
    assert result.next_attempt_at == retry_at
    assert board_store.claim(store.engine, store.ns, 'owner-2', inside,
                             prefer='warm') is None
    assert board_store.due_warm(store.engine, store.ns, inside) == [pair[0]], (
        'a failed warm key is still a warm key that owes a board')

    second = board_store.claim(store.engine, store.ns, 'owner-2', retry_at,
                               prefer='warm')
    assert second is not None, 'the backoff never ended'
    assert second.key_hash == pair[0]
    assert second.warm is True
    assert second.attempts == 2
    assert second.token != first.token


def test_refresh_warm_promotes_a_key_a_viewer_asked_for_first(store):
    pair = key('promoted')
    store.admit(pair)

    board_store.refresh_warm(store.engine, store.ns, [pair], NOW)

    result = store.read(pair[0])
    assert result.warm is True
    assert result.request_count == 1, 'the promotion erased the recorded demand'


def test_due_warm_names_the_stale_warm_keys_oldest_first(store):
    fresh, stale, never = key('fresh'), key('stale'), key('never')
    _publish_warm(store, stale, NOW - seconds(600))
    _publish_warm(store, fresh, NOW - seconds(10))
    board_store.refresh_warm(store.engine, store.ns, [never], NOW)
    store.admit(key('on-demand'))

    due = board_store.due_warm(store.engine, store.ns, NOW)

    assert due == [never[0], stale[0]], (
        'a warm key inside the refresh interval, or an on-demand key, is due')


# --- two generations at once ------------------------------------------------

def test_a_generation_is_blind_to_another_generations_queue(store):
    """The producer's side of the namespace rule, which nothing pinned.

    Rollout and rollback are the two moments when two generations are live at
    once, and that window is the whole reason the namespace exists. The reader
    side is covered (test_radar_board_shared_api: a board another generation
    stored is invisible); this is the other half the ruling asks for in as many
    words -- "test simultaneous v1/v2 readers and producers, not only a reader
    rejecting an old blob".

    Every statement in the store carries `WHERE namespace = :ns`, so this is a
    proof rather than a suspicion. It is worth having as a test because the
    failure it would catch is silent: one generation quietly serving the other
    one's boards, during a deploy, to readers who cannot tell.
    """
    bounds = board_store.limits()
    theirs = store.namespace()

    # One of everything a producer looks for, all of it in the other
    # generation: a claimable on-demand row, a warm row that has never been
    # built, and enough idle on-demand rows to be over the eviction bound on
    # their own.
    demand = key('theirs-demand')
    board_store.admit(store.engine, theirs, *demand, NOW)
    warm = key('theirs-warm')
    board_store.refresh_warm(store.engine, theirs, [warm], NOW)
    store.seed(bounds.max_on_demand + 5, prefix='theirs-idle-', ns=theirs)
    before = len(store.rows(theirs))

    # This generation has an empty queue, whatever the other one is holding.
    assert board_store.claim(store.engine, store.ns, 'mine', NOW,
                             prefer='demand') is None
    assert board_store.claim(store.engine, store.ns, 'mine', NOW,
                             prefer='warm') is None
    assert board_store.due_warm(store.engine, store.ns, NOW) == []
    assert board_store.queue_summary(store.engine, store.ns, NOW) == {
        'pending': 0, 'building': 0, 'failed_due': 0, 'on_demand_rows': 0,
        'warm_ready': 0}
    assert board_store.evict(store.engine, store.ns, NOW) == 0
    assert board_store.refresh_warm(store.engine, store.ns, [], NOW) == 0

    # And the other generation kept every row it had.
    assert len(store.rows(theirs)) == before
    assert board_store.due_warm(store.engine, theirs, NOW) == [warm[0]]
    assert board_store.queue_summary(store.engine, theirs, NOW) == {
        'pending': 2, 'building': 0, 'failed_due': 0,
        'on_demand_rows': bounds.max_on_demand + 6, 'warm_ready': 0}
    # The eviction this generation refused to do is the other one's to do, so
    # the zero above is a namespace scope and not an eviction that cannot run.
    assert board_store.evict(store.engine, theirs, NOW) == 6


def test_a_claim_from_one_generation_cannot_publish_or_fail_in_another(store):
    """The fence is namespace, key, owner and token together.

    A producer holding a live lease in one generation is the nearest thing
    there is to an authorised writer, and it must still be refused everywhere
    but its own: through a rollback the two producers run side by side on the
    same keys, and a publish that crossed would put one build's board under the
    other generation's name.
    """
    theirs = store.namespace()
    pair = key('same-key-both-sides')
    board_store.admit(store.engine, theirs, *pair, NOW)
    store.admit(pair)
    held = board_store.claim(store.engine, theirs, 'theirs', NOW,
                             prefer='demand')
    assert held is not None

    assert board_store.publish(store.engine, store.ns, held, b'board',
                               as_of=NOW, built_at=NOW, build_ms=1,
                               producer_revision=REVISION) is False
    assert board_store.fail(store.engine, store.ns, held, 'RuntimeError',
                            NOW) is False

    mine = store.read(pair[0])
    assert mine.queue_state == 'pending', "another generation's claim wrote here"
    assert mine.payload is None and mine.attempts == 0
    # And the claim still works where it belongs.
    assert board_store.publish(store.engine, theirs, held, b'board',
                               as_of=NOW, built_at=NOW, build_ms=1,
                               producer_revision=REVISION) is True


# --- retirement, health and the summary ------------------------------------

def test_retire_namespaces_removes_only_the_generation_nothing_has_touched(
        store):
    limits = board_store.limits()
    long_ago = NOW - seconds(limits.retire_seconds + 60)
    stale = store.namespace(long_ago)
    live = store.namespace(NOW - seconds(60))
    # Each generation's traffic at its own moment: an admission moves
    # `last_seen_at`, so admitting into the stale one at NOW would keep it
    # alive and this test would be about nothing.
    board_store.admit(store.engine, stale, *key('anything'), long_ago)
    board_store.admit(store.engine, live, *key('anything'), NOW)
    board_store.admit(store.engine, store.ns, *key('mine'), NOW)

    retired = board_store.retire_namespaces(store.engine, store.ns, NOW)

    assert retired >= 1
    assert not store.rows(stale)
    assert board_store.health(store.engine, stale) == {}
    assert len(store.rows(live)) == 1, 'a live generation was retired'
    assert board_store.health(store.engine, live)
    assert len(store.rows()) == 1, "the caller's own generation was retired"


def test_retire_namespaces_never_retires_the_caller_however_old_it_looks(
        store):
    limits = board_store.limits()
    long_ago = NOW - seconds(limits.retire_seconds + 60)
    ancient = store.namespace(long_ago)
    # Admitted at its own old moment, so nothing but the keep rule is sparing
    # it: its `last_seen_at` really is past the cutoff when retirement looks.
    board_store.admit(store.engine, ancient, *key('mine'), long_ago)

    board_store.retire_namespaces(store.engine, ancient, NOW)

    assert len(store.rows(ancient)) == 1
    assert board_store.health(store.engine, ancient)


def test_reader_traffic_alone_keeps_a_generation_off_the_retirement_list(
        store):
    """`last_seen_at` is the whole generation's clock, not the producer's.

    A producer that has been down since yesterday is exactly when the stored
    boards matter most -- they are the only answer anyone has -- and retiring
    them under the readers still asking for them would empty the cache at the
    worst possible moment. So any admission keeps a generation alive, and only
    a generation nobody is reading either goes.
    """
    limits = board_store.limits()
    long_ago = NOW - seconds(limits.retire_seconds + 60)
    watched = store.namespace(long_ago)
    abandoned = store.namespace(long_ago)
    board_store.admit(store.engine, watched, *key('still-wanted'), long_ago)
    board_store.admit(store.engine, abandoned, *key('forgotten'), long_ago)

    # A day of readers and no producer at all: no heartbeat, no
    # `ensure_namespace`, nothing but admissions.
    for minute in range(3):
        board_store.admit(store.engine, watched, *key('still-wanted'),
                          NOW - seconds(60 * minute), poll=True)

    board_store.retire_namespaces(store.engine, store.ns, NOW)

    assert board_store.health(store.engine, watched), (
        'a generation with live readers was retired'
    )
    assert len(store.rows(watched)) == 1
    assert board_store.health(store.engine, abandoned) == {}
    assert not store.rows(abandoned)


def test_a_producer_stamps_its_revision_onto_a_row_a_reader_adopted(store):
    """Whoever adopts the control row first, the producer owns what it says.

    A reader can be the first process to touch a generation, and it has no
    business guessing which build answers there -- so the adopted row carries
    no revision. When the producer arrives it is authoritative for its own
    namespace, and an update that only moved `last_seen_at` would leave the
    admin surface reporting no revision for the whole life of the generation.
    """
    fresh = store.namespace(introduce=False)
    board_store.admit(store.engine, fresh, *key('first-in'), NOW)
    adopted = board_store.health(store.engine, fresh)
    assert adopted['producer_revision'] is None, (
        'a reader guessed at the revision')

    producer_revision = 'deadbeef' * 5
    board_store.ensure_namespace(store.engine, fresh, NOW + seconds(30),
                                 revision=producer_revision, payload_version=1)

    reported = board_store.health(store.engine, fresh)
    assert reported['producer_revision'] == producer_revision
    assert reported['payload_version'] == 1
    assert reported['last_seen_at'] == NOW + seconds(30)
    assert reported['created_at'] == NOW, 'the introduction rewrote the birth'


def test_heartbeat_and_health_round_trip_the_producer_fields(store):
    assert board_store.heartbeat(store.engine, store.ns, 'host:42',
                                 NOW) is True

    reported = board_store.health(store.engine, store.ns)
    assert reported['namespace'] == store.ns
    assert reported['payload_version'] == 1
    assert reported['producer_revision'] == REVISION
    assert reported['producer_owner'] == 'host:42'
    assert reported['producer_seen_at'] == NOW
    assert reported['last_seen_at'] == NOW
    assert reported['producer_success_at'] is None
    assert reported['producer_error'] is None

    board_store.heartbeat(store.engine, store.ns, 'host:42', NOW + seconds(60),
                          error='RuntimeError')
    assert board_store.health(store.engine,
                              store.ns)['producer_error'] == 'RuntimeError'

    board_store.heartbeat(store.engine, store.ns, 'host:42',
                          NOW + seconds(120), success_at=NOW + seconds(119))
    reported = board_store.health(store.engine, store.ns)
    assert reported['producer_success_at'] == NOW + seconds(119)
    assert reported['producer_error'] is None, (
        'a success left the previous failure standing')
    assert reported['producer_seen_at'] == NOW + seconds(120)

    assert board_store.heartbeat(store.engine, 'no-such-generation', 'host:42',
                                 NOW) is False
    assert board_store.health(store.engine, 'no-such-generation') == {}


def test_ensure_namespace_is_idempotent_and_keeps_the_first_creation(store):
    board_store.ensure_namespace(store.engine, store.ns, NOW + seconds(600),
                                 revision=REVISION, payload_version=1)

    reported = board_store.health(store.engine, store.ns)
    assert reported['created_at'] == NOW
    assert reported['last_seen_at'] == NOW + seconds(600)


def test_no_clock_on_the_control_row_can_age_a_generation_backwards(store):
    """`last_seen_at` only ever moves forward, whichever call moves it.

    Three public calls write that column -- `ensure_namespace`, `heartbeat`
    and every admission through `_under_lock` -- and each takes the clock as
    an argument, from a process that need not agree with the last one. Two
    producers overlapping across a deploy, a retry carrying the instant its
    request arrived, a host whose NTP stepped back: any of those could drag a
    live generation towards the retirement cutoff, and the cache would be
    deleted under the readers still asking for it. `_under_lock` already
    argued this; the other two simply assigned.

    `producer_seen_at` is a different question and is deliberately left alone:
    it is one producer's claim about itself, not the generation's clock.
    """
    ahead = NOW + seconds(600)
    behind = NOW - seconds(600)
    board_store.ensure_namespace(store.engine, store.ns, ahead,
                                 revision=REVISION, payload_version=1)

    board_store.ensure_namespace(store.engine, store.ns, behind,
                                 revision=REVISION, payload_version=1)
    assert board_store.health(store.engine, store.ns)['last_seen_at'] == ahead, (
        'ensure_namespace aged the generation backwards')

    assert board_store.heartbeat(store.engine, store.ns, 'host:42', behind)
    reported = board_store.health(store.engine, store.ns)
    assert reported['last_seen_at'] == ahead, (
        'a heartbeat aged the generation backwards')
    assert reported['producer_seen_at'] == behind, (
        "the producer's own stamp is its own to move")

    # The call that already had the rule, so all three are asserted together.
    board_store.admit(store.engine, store.ns, *key('late-arrival'), behind)
    assert board_store.health(store.engine, store.ns)['last_seen_at'] == ahead, (
        'an admission aged the generation backwards')


def test_queue_summary_counts_each_class_of_work(store):
    limits = board_store.limits()
    for index in range(3):
        store.admit(key(f'pending{index}'))
    building = key('building')
    store.admit(building)
    board_store.claim(store.engine, store.ns, 'owner-1', NOW, prefer='demand')
    failed = key('failed')
    store.admit(failed)
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')
    board_store.fail(store.engine, store.ns, claim, 'RuntimeError', NOW)
    warm = key('warm-ready')
    board_store.refresh_warm(store.engine, store.ns, [warm], NOW)
    warm_claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                                   prefer='warm')
    board_store.publish(store.engine, store.ns, warm_claim, b'board',
                        as_of=NOW, built_at=NOW, build_ms=1,
                        producer_revision=REVISION)

    inside_backoff = board_store.queue_summary(store.engine, store.ns, NOW)
    past_backoff = board_store.queue_summary(store.engine, store.ns,
                                             NOW + seconds(60))
    gone_stale = board_store.queue_summary(
        store.engine, store.ns, NOW + seconds(limits.fresh_seconds + 1))

    assert inside_backoff == {'pending': 3, 'building': 1, 'failed_due': 0,
                              'on_demand_rows': 5, 'warm_ready': 1}
    assert past_backoff['failed_due'] == 1
    assert gone_stale['warm_ready'] == 0


def test_a_real_key_and_a_real_payload_survive_the_whole_path(store):
    """The widths, once, with a genuine 4,000-character key and a 12 KB blob --
    the two shapes the columns were chosen for."""
    from features.radar.routes.api import Query

    names = ['reddit:' + ('x' * 100) + str(index) for index in range(37)]
    key_hash, key_json = board_keys.canonical(Query(
        sources=names, segments=['mid', 'micro', 'mid'], window=24, limit=100,
        min_venues=2, market='de', sort='lean', direction='asc'))
    assert len(key_json) > 3500
    blob = zlib.compress(bytes(range(256)) * 96, 6)

    assert board_store.admit(store.engine, store.ns, key_hash, key_json,
                             NOW) == 'pending'
    claim = board_store.claim(store.engine, store.ns, 'owner-1', NOW,
                              prefer='demand')
    assert claim.key_json == key_json
    assert board_keys.round_trips(claim.key_hash, claim.key_json)
    assert board_store.publish(store.engine, store.ns, claim, blob, as_of=NOW,
                               built_at=NOW, build_ms=1,
                               producer_revision=REVISION) is True

    result = store.read(key_hash)
    assert result.key_json == key_json
    assert board_keys.round_trips(result.key_hash, result.key_json)
    assert result.payload == blob
    assert zlib.decompress(result.payload) == bytes(range(256)) * 96


# --- transactions ----------------------------------------------------------

class _Depth:
    """How many transactions this engine currently has open.

    `begin`, `commit` and `rollback` are the only three events involved --
    SAVEPOINTs have their own names -- so the count is exactly the depth, and
    zero after a call means that call left nothing behind for the next one to
    inherit.
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


def test_no_public_call_leaves_a_transaction_open(store):
    """Nothing here may hold a transaction across a call boundary. A producer
    that returns from `claim` still inside one holds row locks for the whole
    length of a build, which is seconds, and a web worker that returns from
    `admit` still inside one holds the namespace lock every other worker
    admits under."""
    limits = board_store.limits()
    engine, ns = store.engine, store.ns
    pair, warm, busy = key('tx'), key('tx-warm'), key('tx-busy')
    store.seed(limits.max_queue, prefix='tx-queued', state='pending')
    # One generation actually due for retirement, with a result row of its
    # own. `retire_namespaces` opens a transaction PER CANDIDATE, so with an
    # empty candidate list the only part of it the listener would see is the
    # unlocked scan -- and the loop that takes the lock and deletes would go
    # unwatched, which is the half of that function this test is about.
    doomed = store.namespace(NOW - seconds(limits.retire_seconds + 60))
    board_store.admit(engine, doomed, *key('tx-doomed'),
                      NOW - seconds(limits.retire_seconds + 60))

    with _Depth(engine) as depth:
        def closed(label):
            assert depth.open == 0, f'{label} left {depth.open} open'

        board_store.ensure_namespace(engine, ns, NOW, revision=REVISION,
                                     payload_version=1)
        closed('ensure_namespace')
        assert board_store.admit(engine, ns, *busy, NOW) == 'busy'
        closed('admit (refused)')
        board_store.admit(engine, ns, *pair, NOW, warm=True)
        closed('admit')
        board_store.admit(engine, ns, *pair, NOW, poll=True)
        closed('admit (poll)')
        board_store.read(engine, ns, pair[0])
        closed('read')
        board_store.refresh_warm(engine, ns, [warm], NOW)
        closed('refresh_warm')
        board_store.due_warm(engine, ns, NOW)
        closed('due_warm')
        claim = board_store.claim(engine, ns, 'owner-1', NOW, prefer='warm')
        closed('claim')
        board_store.publish(engine, ns, claim, b'board', as_of=NOW,
                            built_at=NOW, build_ms=1,
                            producer_revision=REVISION)
        closed('publish')
        again = board_store.claim(engine, ns, 'owner-1', NOW, prefer='demand')
        closed('claim (demand)')
        board_store.fail(engine, ns, again, 'RuntimeError', NOW)
        closed('fail')
        board_store.evict(engine, ns, NOW)
        closed('evict')
        board_store.heartbeat(engine, ns, 'owner-1', NOW, success_at=NOW)
        closed('heartbeat')
        board_store.health(engine, ns)
        closed('health')
        board_store.queue_summary(engine, ns, NOW)
        closed('queue_summary')
        assert board_store.retire_namespaces(engine, ns, NOW) >= 1, (
            'the per-candidate loop never ran, so nothing here watched it')
        closed('retire_namespaces')
        assert not store.rows(doomed)

        assert depth.peak == 1, (
            f'a call nested {depth.peak} transactions, so one of them was '
            f'held open across another')
