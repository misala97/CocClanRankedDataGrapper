"""P06: the coordinator with an injected monotonic clock, wall clock, child
launcher and thread factory. No process, no network, no waiting."""
import json

import pytest

from features.radar import price_chart_acquisition as acq
from features.radar import price_chart_contract as c
from features.radar import price_chart_fetch as fetch

from .helpers import identity, series, utc

NOW = utc(2026, 9, 15, 14, 7)
WINDOW = c.window_for('1W', NOW)
ANCHOR = int(WINDOW.start.timestamp())


class Clocks:
    def __init__(self):
        self.mono = 100.0
        self.wall = 2_000_000_000.0

    def monotonic(self):
        return self.mono

    def time(self):
        return self.wall


class FakeProcess:
    def __init__(self, stubborn=False):
        self.alive = True
        self.stubborn = stubborn
        self.terminated = self.killed = False

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        pass

    def terminate(self):
        self.terminated = True
        if not self.stubborn:
            self.alive = False

    def kill(self):
        self.killed = True
        if not self.stubborn:
            self.alive = False


class FakeChild:
    """The launcher's child contract -- collect() then reap() -- on the fake
    clocks. The real subprocess Child is exercised in test_child_lifecycle.py."""

    def __init__(self, data, clocks, process):
        self.data = data
        self.clocks = clocks
        self.process = process
        self.closed = False

    def collect(self, clock, deadline):
        if self.data is None:                      # a child that never answers
            self.clocks.mono = max(self.clocks.mono, deadline)
            return 'timeout', None
        if len(self.data) > fetch.RESULT_LIMIT_BYTES:
            return 'oversized', None
        self.process.alive = False
        return 'done', self.data

    def reap(self, clock, cleanup_s=acq.CLEANUP_S):
        if self.process.alive:
            self.process.terminate()
        if self.process.alive:
            self.process.kill()
        self.closed = True
        return not self.process.alive


class Harness:
    def __init__(self, *results, stubborn=False, hang=False):
        self.clocks = Clocks()
        self.results = list(results)
        self.specs, self.pending, self.children = [], [], []
        self.stubborn, self.hang = stubborn, hang
        self.coordinator = acq.Coordinator(clock=self.clocks.monotonic, wall=self.clocks.time,
                                           launcher=self.launch, thread_factory=self.thread)

    def launch(self, spec):
        self.specs.append(spec)
        process = FakeProcess(self.stubborn)
        result = self.results.pop(0) if self.results else series(ANCHOR, received_at=self.clocks.wall)
        child = FakeChild(None if self.hang else json.dumps(result).encode(), self.clocks, process)
        self.children.append(child)
        return child

    def thread(self, target, args, name=None, daemon=None):
        harness = self

        class Deferred:
            def start(self):
                harness.pending.append((target, args))
        return Deferred()

    def run(self):
        while self.pending:
            target, args = self.pending.pop(0)
            target(*args)

    def ask(self, ident=None, window=WINDOW, source=c.YAHOO_SOURCE):
        return self.coordinator.get_or_start(ident or identity(), window, now=NOW, source=source)


def ok(h, **over):
    return series(ANCHOR, received_at=h.clocks.wall, **over)


def test_a_miss_admits_one_acquisition_and_returns_at_once():
    h = Harness()
    answer = h.ask()
    assert (answer['state'], answer['series']) == ('pending', None)
    assert h.specs == [] and len(h.pending) == 1          # the child starts on the supervisor thread
    h.run()
    assert len(h.specs) == 1 and h.coordinator.counters['success'] == 1


def test_the_stable_key_is_reused_while_now_moves():
    h = Harness()
    h.ask()
    h.run()
    h.clocks.wall += 30
    later = c.window_for('1W', utc(2026, 9, 15, 14, 30))
    answer = h.ask(window=later)
    assert answer['state'] == 'ready' and answer['series']['bars'][0][0] == ANCHOR
    assert len(h.specs) == 1


def test_same_key_callers_share_the_one_in_flight_and_other_keys_are_busy_without_a_queue():
    h = Harness()
    assert h.ask()['state'] == 'pending'
    assert h.ask()['state'] == 'pending'
    busy = h.ask(identity(provider_symbol='MSFT', ticker='MSFT'))
    assert (busy['state'], busy['retry_after_seconds']) == ('busy', acq.BUSY_RETRY_S)
    assert len(h.pending) == 1
    h.run()
    assert len(h.specs) == 1 and h.coordinator.counters['busy'] == 1
    assert h.pending == []                                  # nothing queued behind it


def test_exactly_ten_starts_in_any_rolling_sixty_seconds():
    h = Harness()
    for index in range(10):
        assert h.ask(identity(instrument_id=100 + index))['state'] == 'pending'
        h.run()
        h.clocks.mono += 1
    refused = h.ask(identity(instrument_id=200))
    assert refused['state'] == 'busy' and refused['retry_after_seconds'] == 50
    h.clocks.mono = 100.0 + 59.999
    assert h.ask(identity(instrument_id=200))['state'] == 'busy'
    h.clocks.mono = 100.0 + 60
    assert h.ask(identity(instrument_id=200))['state'] == 'pending'


def test_at_least_sixty_seconds_between_starts_for_one_chart():
    h = Harness({'kind': 'upstream_error', 'status': 503})
    h.ask()
    h.run()
    h.clocks.mono += 59
    assert h.ask()['state'] == 'backoff'
    h.clocks.mono += 1
    assert h.ask()['state'] == 'pending'


@pytest.mark.parametrize('result,counter,state,seconds', [
    ({'kind': 'empty'}, 'empty', 'backoff', 60),
    ({'kind': 'invalid', 'reason': 'arrays'}, 'invalid', 'backoff', 60),
    ({'kind': 'timeout'}, 'timeout', 'backoff', 60),
    ({'kind': 'upstream_error', 'status': 502}, 'upstream_error', 'backoff', 60),
    ({'kind': 'unsupported', 'status': 404}, 'unsupported', 'unavailable', 900),
    ({'kind': 'identity_mismatch'}, 'identity_mismatch', 'unavailable', 900),
])
def test_failures_cool_the_chart_without_a_retry(result, counter, state, seconds):
    h = Harness(result)
    h.ask()
    h.run()
    assert h.coordinator.counters[counter] == 1
    answer = h.ask()
    assert (answer['state'], answer['retry_after_seconds']) == (state, seconds)
    h.clocks.mono += seconds
    assert h.ask()['state'] == 'pending'
    assert len(h.specs) == 1


def test_a_throttle_opens_the_provider_wide_ladder_and_honours_a_longer_retry_after():
    h = Harness({'kind': 'throttle', 'status': 429, 'retry_after': None},
                {'kind': 'throttle', 'status': 429, 'retry_after': None},
                {'kind': 'throttle', 'status': 429, 'retry_after': 300},
                {'kind': 'throttle', 'status': 403, 'retry_after': 100_000})
    other = identity(instrument_id=99)
    h.ask()
    h.run()
    assert h.ask(other)['retry_after_seconds'] == 60 and h.ask(other)['state'] == 'backoff'
    h.clocks.mono += 60
    h.ask(other)
    h.run()
    assert h.ask()['retry_after_seconds'] == 120
    h.clocks.mono += 120
    h.ask(identity(instrument_id=98))
    h.run()
    assert h.ask()['retry_after_seconds'] == 300              # longer valid Retry-After wins over 240
    h.clocks.mono += 300
    h.ask(identity(instrument_id=97))
    h.run()
    capped = h.ask()
    assert (capped['state'], capped['retry_after_seconds']) == ('unavailable', acq.RETRY_AFTER_CAP_S)
    h.clocks.mono += 86_400
    assert h.ask()['state'] == 'unavailable'                   # never sooner than the supplied time
    h.clocks.mono += 13_600
    assert h.ask(identity(instrument_id=96))['state'] == 'pending'
    assert h.coordinator.counters['throttle'] == 4


def test_stale_series_are_served_with_a_refresh_then_dropped_at_fifteen_minutes():
    h = Harness()
    h.ask()
    h.run()
    h.clocks.wall += 61
    h.clocks.mono += 61
    stale = h.ask()
    assert stale['state'] == 'pending' and stale['series'] is not None
    assert h.coordinator.counters['served_stale'] == 1
    h.clocks.wall += 900
    h.clocks.mono += 900
    h.pending.clear()
    h.coordinator._inflight = None
    assert h.ask()['series'] is None


def test_an_identity_mismatch_drops_the_cached_series():
    h = Harness(series(ANCHOR, received_at=2_000_000_000.0), {'kind': 'identity_mismatch'})
    h.ask()
    h.run()
    h.clocks.wall += 61
    h.clocks.mono += 61
    assert h.ask()['series'] is not None
    h.run()
    answer = h.ask()
    assert answer['series'] is None and answer['state'] == 'unavailable'


def test_the_cache_is_lru_and_bounded_by_keys_and_bytes(monkeypatch):
    monkeypatch.setattr(acq, 'CACHE_KEYS', 3)
    h = Harness()
    for index in range(4):
        h.ask(identity(instrument_id=index + 1))
        h.run()
        h.clocks.mono += 61
    assert len(h.coordinator._cache) == 3
    assert h.ask(identity(instrument_id=1))['series'] is None
    monkeypatch.setattr(acq, 'CACHE_BYTES', 1)
    h2 = Harness()
    h2.ask()
    h2.run()
    assert len(h2.coordinator._cache) == 0 and h2.coordinator._cache_bytes == 0


def test_an_oversized_series_is_rejected_not_truncated():
    big = [[ANCHOR + 300 * i, 123456.123456] for i in range(12_000)]
    h = Harness({'kind': 'ok', 'bars': big, 'received_at': 2_000_000_000.0})
    h.ask()
    h.run()
    assert h.coordinator.counters['invalid'] == 1 and not h.coordinator._cache


def test_a_result_over_the_channel_bound_is_invalid():
    h = Harness()
    h.results = [{'kind': 'ok', 'bars': [], 'pad': 'x' * (fetch.RESULT_LIMIT_BYTES + 10), 'received_at': 1.0}]
    h.ask()
    h.run()
    assert h.coordinator.counters['invalid'] == 1


def test_a_hanging_child_times_out_and_is_reaped_on_the_supervisor_clock():
    h = Harness(hang=True)
    h.ask()
    h.run()
    child = h.children[0]
    assert child.process.terminated and not child.process.alive and child.closed
    assert h.coordinator.counters['timeout'] == 1
    assert h.coordinator.snapshot()['latency']['max_seconds'] >= acq.DEADLINE_S
    assert h.ask()['state'] == 'backoff'


def test_cleanup_that_cannot_be_confirmed_quarantines_acquisition():
    h = Harness(hang=True, stubborn=True)
    h.ask()
    h.run()
    assert h.children[0].process.killed
    assert h.coordinator.counters['cleanup_failed'] == 1
    answer = h.ask(identity(instrument_id=55))
    assert answer['state'] == 'unavailable' and answer['reason'].startswith('cleanup_failed')
    assert len(h.specs) == 1 and h.coordinator.snapshot()['quarantined'] is True


def test_unsupported_symbols_and_waiting_windows_start_nothing():
    h = Harness()
    assert h.ask(identity(provider_symbol='BRK/B'))['state'] == 'unavailable'
    waiting = c.window_for('1D', utc(2026, 9, 15, 8))
    assert h.ask(window=waiting)['state'] == 'unavailable'
    assert h.pending == [] and h.specs == []


# --- the Alpaca source (C1) -------------------------------------------------------

@pytest.fixture()
def alpaca_keys(monkeypatch):
    monkeypatch.setenv('APCA_API_KEY_ID', 'PKSENTINELKEYID0000')
    monkeypatch.setenv('APCA_API_SECRET_KEY', 'sentinel-secret-not-a-real-credential')


def test_an_alpaca_acquisition_builds_the_alpaca_request_and_keeps_its_own_cache_key():
    h = Harness({'kind': 'ok', 'source': c.ALPACA_SOURCE, 'bars': [[ANCHOR, 101.0]],
                 'off_grid': 0, 'outside': 0, 'nulls': 0, 'received_at': 2_000_000_000.0})
    assert h.ask(source=c.ALPACA_SOURCE)['state'] == 'pending'
    h.run()
    assert h.specs[0]['source'] == c.ALPACA_SOURCE and h.specs[0]['feed'] == 'sip'
    assert h.specs[0]['timeframe'] == '5Min' and h.specs[0]['limit'] == 10_000
    assert h.coordinator.counters['success'] == 1
    # The same chart on the other source is a different key, so it is admitted
    # in its own right rather than reading Alpaca's cached series.
    h.clocks.mono += 1
    assert h.ask()['state'] in ('pending', 'busy')
    assert h.ask(source=c.ALPACA_SOURCE)['state'] == 'ready'


@pytest.mark.parametrize('result,counter,state,seconds', [
    ({'kind': 'truncated', 'reason': 'the provider answer was paginated'}, 'truncated', 'backoff', 60),
    ({'kind': 'waiting', 'reason': 'clamp'}, 'waiting', 'unavailable', 60),
    ({'kind': 'credentials_missing'}, 'credentials_missing', 'unavailable', 900),
])
def test_the_new_alpaca_outcomes_cool_the_chart_without_a_retry(result, counter, state, seconds):
    h = Harness(result)
    h.ask(source=c.ALPACA_SOURCE)
    h.run()
    assert h.coordinator.counters[counter] == 1
    answer = h.ask(source=c.ALPACA_SOURCE)
    assert (answer['state'], answer['retry_after_seconds']) == (state, seconds)
    assert len(h.specs) == 1


def ok_result(source=c.ALPACA_SOURCE, **over):
    row = {'kind': 'ok', 'bars': [[ANCHOR, 101.0]], 'off_grid': 0, 'outside': 0,
           'nulls': 0, 'received_at': 2_000_000_000.0}
    if source is not None:
        row['source'] = source
    row.update(over)
    return row


def forged_source(value):
    """An otherwise valid `ok` result whose `source` is exactly `value` --
    including an explicit JSON null, which ok_result() would omit."""
    row = ok_result()
    row['source'] = value
    return row


def assert_refused_source(h, admitted):
    """Invalid, never cached, the normal 60-second cooldown with a reason that
    names the source rather than a byte bound, and nothing for the reader to
    resolve: it goes on to its own coherent stored fallback."""
    assert h.coordinator.counters['invalid'] == 1
    assert h.coordinator.counters['success'] == 0
    assert not h.coordinator._cache and h.coordinator._cache_bytes == 0
    answer = h.ask(source=admitted)
    assert (answer['state'], answer['retry_after_seconds']) == ('backoff', 60)
    assert answer['series'] is None
    assert 'source' in answer['reason'] and 'bound' not in answer['reason']
    h.clocks.mono += 60
    assert h.ask(source=admitted)['state'] == 'pending'
    assert len(h.specs) == 1


# C2-1: `_settle` is the supervisor's boundary for the child's result envelope.
# It bounds the bytes and checks `bars` and `received_at`; a `source` that is
# not the one this child was admitted for has to be refused HERE, because the
# reader resolves it on the Flask request thread, where an unknown one would
# raise instead of falling back.
@pytest.mark.parametrize('value', ['not_a_source', None, 7, ''])
def test_a_child_result_whose_source_cannot_be_profiled_is_invalid_and_never_cached(value):
    h = Harness(forged_source(value))
    h.ask(source=c.ALPACA_SOURCE)
    h.run()
    assert_refused_source(h, c.ALPACA_SOURCE)


# M1: the source is untrusted JSON. An array or object cannot be looked up in a
# table without raising, and it must not escape the supervisor thread: it is an
# invalid result like any other.
@pytest.mark.parametrize('value', [[c.ALPACA_SOURCE], {'source': c.ALPACA_SOURCE}])
def test_an_unhashable_source_is_an_invalid_result_not_a_supervisor_exception(value):
    h = Harness(forged_source(value))
    h.ask(source=c.ALPACA_SOURCE)
    h.run()                                   # would raise TypeError out of _supervise
    assert_refused_source(h, c.ALPACA_SOURCE)


# M1: a KNOWN source is still wrong when it is not the one admitted. A Yahoo
# series must never be cached under an Alpaca key, nor the other way round; and
# a result with no source is the historical Yahoo shape, so it cannot answer an
# Alpaca request either.
@pytest.mark.parametrize('returned,admitted', [
    (c.YAHOO_SOURCE, c.ALPACA_SOURCE),
    (c.ALPACA_SOURCE, c.YAHOO_SOURCE),
    (None, c.ALPACA_SOURCE),
])
def test_a_known_source_other_than_the_admitted_one_is_invalid_and_never_cached(returned, admitted):
    h = Harness(ok_result(source=returned))
    h.ask(source=admitted)
    h.run()
    assert h.specs[0]['source'] == admitted
    assert_refused_source(h, admitted)


# A request spec without a source is the historical Yahoo request, so only a
# Yahoo result -- named, or the historical unnamed shape -- may answer it.
@pytest.mark.parametrize('returned,counter', [
    (None, 'success'), (c.YAHOO_SOURCE, 'success'), (c.ALPACA_SOURCE, 'invalid'),
])
def test_a_spec_without_a_source_admits_only_the_historical_yahoo_result(returned, counter):
    h = Harness(ok_result(source=returned))
    spec = c.request_spec(identity(), WINDOW)
    del spec['source']
    h.coordinator._supervise(c.cache_key(identity(), WINDOW), spec)
    assert h.specs == [spec]
    assert h.coordinator.counters[counter] == 1
    assert len(h.coordinator._cache) == (1 if counter == 'success' else 0)


@pytest.mark.parametrize('source', [c.ALPACA_SOURCE, c.YAHOO_SOURCE, None])
def test_a_profiled_source_and_the_historical_missing_one_still_succeed(source):
    h = Harness(ok_result(source=source))
    h.ask(source=source or c.YAHOO_SOURCE)
    h.run()
    assert h.coordinator.counters['success'] == 1 and h.coordinator.counters['invalid'] == 0
    assert len(h.coordinator._cache) == 1
    # And whatever was cached is resolvable: this is the call that used to raise.
    series = h.ask(source=source or c.YAHOO_SOURCE)['series']
    assert c.provider_price(series, WINDOW, identity(), now=NOW)['source'] == (
        source or c.YAHOO_SOURCE)


def test_a_permission_refusal_pauses_the_whole_process_and_says_so():
    h = Harness({'kind': 'permission', 'status': 403})
    h.ask(source=c.ALPACA_SOURCE)
    h.run()
    assert h.coordinator.counters['permission'] == 1
    other = h.ask(identity(instrument_id=99), source=c.ALPACA_SOURCE)
    assert (other['state'], other['retry_after_seconds']) == ('backoff', 60)
    assert 'credential' in other['reason']
    assert 'throttled' not in other['reason']


def test_a_too_recent_window_is_refused_before_a_child_starts():
    h = Harness()
    early = utc(2026, 9, 15, 8, 10)                    # ten minutes into the extended session
    answer = h.coordinator.get_or_start(identity(), c.window_for('1D', early), now=early,
                                        source=c.ALPACA_SOURCE)
    assert answer['state'] == 'unavailable' and 'delayed' in answer['reason']
    assert h.pending == [] and h.specs == []


def test_admission_needs_both_the_chart_and_alpaca_flags(monkeypatch, alpaca_keys):
    monkeypatch.setattr(acq, '_instance', None)
    monkeypatch.delenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', raising=False)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_ALPACA_ENABLED', '1')
    assert acq.Admission().get_or_start(identity(), WINDOW, now=NOW)['state'] == 'disabled'
    assert acq._instance is None
    monkeypatch.setenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', 'on')
    assert acq.selected_source() == (c.ALPACA_SOURCE, None)
    monkeypatch.delenv('RADAR_SELECTED_PRICE_ALPACA_ENABLED')
    assert acq.selected_source() == (None, 'disabled')


def test_missing_credentials_refuse_without_starting_a_child(monkeypatch):
    monkeypatch.setattr(acq, '_instance', None)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', 'on')
    monkeypatch.setenv('RADAR_SELECTED_PRICE_ALPACA_ENABLED', '1')
    monkeypatch.delenv('APCA_API_KEY_ID', raising=False)
    monkeypatch.delenv('APCA_API_SECRET_KEY', raising=False)
    assert acq.selected_source() == (None, 'credentials_missing')
    answer = acq.Admission().get_or_start(identity(), WINDOW, now=NOW)
    assert answer['state'] == 'unavailable' and 'credential' in answer['reason']
    assert acq._instance is None


# C2-4: operations must name the source that is actually selected, not always
# claim Alpaca. When a source is intended but cannot run -- the credentials are
# not configured -- naming it is still the truth; when nothing is selected, no
# source is claimed at all.
def test_ops_names_the_source_that_is_actually_selected(monkeypatch, alpaca_keys):
    monkeypatch.setattr(acq, '_instance', None)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', 'on')
    monkeypatch.delenv('RADAR_SELECTED_PRICE_ALPACA_ENABLED', raising=False)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_YAHOO_ENABLED', 'on')
    yahoo = acq.ops_snapshot()
    assert (yahoo['source'], yahoo['source_state']) == (c.YAHOO_SOURCE, 'yahoo')
    monkeypatch.setenv('RADAR_SELECTED_PRICE_ALPACA_ENABLED', '1')
    active = acq.ops_snapshot()
    assert (active['source'], active['source_state']) == (c.ALPACA_SOURCE, 'active')
    monkeypatch.delenv('APCA_API_SECRET_KEY')
    blind = acq.ops_snapshot()
    assert (blind['source'], blind['source_state']) == (c.ALPACA_SOURCE, 'credentials_missing')
    for name in ('RADAR_SELECTED_PRICE_ALPACA_ENABLED', 'RADAR_SELECTED_PRICE_YAHOO_ENABLED'):
        monkeypatch.delenv(name)
    nothing = acq.ops_snapshot()
    assert (nothing['source'], nothing['source_state']) == (None, 'disabled')


def test_ops_names_the_source_truthfully_and_never_reports_a_credential(monkeypatch, alpaca_keys):
    monkeypatch.setattr(acq, '_instance', None)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', 'on')
    monkeypatch.delenv('RADAR_SELECTED_PRICE_ALPACA_ENABLED', raising=False)
    monkeypatch.delenv('RADAR_SELECTED_PRICE_YAHOO_ENABLED', raising=False)
    off = acq.ops_snapshot()
    assert (off['charts_enabled'], off['alpaca_enabled'], off['source_state']) == (True, False, 'disabled')
    assert off['source'] is None and off['credentials_present'] is True
    monkeypatch.setenv('RADAR_SELECTED_PRICE_ALPACA_ENABLED', '1')
    assert acq.ops_snapshot()['source_state'] == 'active'
    monkeypatch.delenv('APCA_API_KEY_ID')
    blind = acq.ops_snapshot()
    assert (blind['credentials_present'], blind['source_state']) == (False, 'credentials_missing')
    assert 'PKSENTINELKEYID0000' not in json.dumps(blind)
    assert 'sentinel-secret-not-a-real-credential' not in json.dumps(blind)
    monkeypatch.delenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED')
    assert acq.ops_snapshot()['source_state'] == 'charts_off'


def test_flag_off_creates_no_coordinator_and_ops_never_creates_one(monkeypatch):
    monkeypatch.delenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', raising=False)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_YAHOO_ENABLED', '1')
    monkeypatch.setattr(acq, '_instance', None)
    answer = acq.Admission().get_or_start(identity(), WINDOW, now=NOW)
    assert answer['state'] == 'disabled' and acq._instance is None
    snapshot = acq.ops_snapshot()
    assert acq._instance is None and snapshot['scope'] == 'process' and snapshot['yahoo_enabled'] is False
    acq.note_fallback()
    assert acq._instance is None


def test_the_snapshot_is_process_scoped_and_complete():
    h = Harness()
    h.ask()
    snapshot = h.coordinator.snapshot()
    assert snapshot['scope'] == 'process' and snapshot['in_flight'] is True
    assert set(snapshot['counters']) == set(acq.COUNTERS)
    assert {'pid', 'coordinator_started_at', 'charts_enabled', 'yahoo_enabled', 'configured_web_workers',
            'configured_web_workers_source', 'cache_keys', 'cache_bytes', 'rolling_starts_60s',
            'backoff_until', 'latency', 'note'} <= set(snapshot)
    assert 'process_started_at' not in snapshot
    assert snapshot['rolling_starts_60s'] == 1
    # The coordinator's own creation, on its wall clock -- not the OS process start.
    assert snapshot['coordinator_started_at'] == '2033-05-18T03:33:20Z'


def test_before_any_acquisition_the_coordinator_has_not_started(monkeypatch):
    monkeypatch.setattr(acq, '_instance', None)
    snapshot = acq.ops_snapshot()
    assert snapshot['coordinator_started_at'] is None and 'process_started_at' not in snapshot
    assert snapshot['pid'] > 0 and snapshot['scope'] == 'process'
    assert 'reset when it restarts' in snapshot['note']


@pytest.mark.parametrize('raw,expected', [
    (None, None), ('', None), ('   ', None), ('0', None), ('00', None), ('-2', None), ('+2', None),
    ('two', None), ('2.5', None), ('²', None), ('٣', None), ('2 workers', None),
    ('1', 1), (' 3 ', 3), ('12', 12),
])
def test_configured_workers_come_only_from_a_positive_web_concurrency(monkeypatch, raw, expected):
    monkeypatch.setattr(acq, '_instance', None)
    if raw is None:
        monkeypatch.delenv('WEB_CONCURRENCY', raising=False)
    else:
        monkeypatch.setenv('WEB_CONCURRENCY', raw)
    snapshot = acq.ops_snapshot()
    assert snapshot['configured_web_workers'] == expected
    assert snapshot['configured_web_workers_source'] == 'WEB_CONCURRENCY'
