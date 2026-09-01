# personal_apps/tests/test_radar_massive.py
"""The Massive grouped-daily adapter: payload truth without database identity.

[A1] This module validates envelope, rows, dates, and duplicates and returns
exact provider symbols; joining to Radar identities, coverage counting, and
progress persistence belong to market_data, where RadarInstrument exists.
"""
import datetime as dt
import decimal

import pytest
import requests

from features.radar.prices import massive

DAY = dt.date(2026, 8, 28)


def event_ms(day, hour=20):
    """Provider timestamps resolve to the requested US exchange-local date."""
    stamp = dt.datetime(day.year, day.month, day.day, hour,
                        tzinfo=dt.timezone.utc)
    return int(stamp.timestamp() * 1000)


def grouped_payload(rows=None):
    if rows is None:
        rows = [
            {'T': 'ZZAA', 'c': 100.5, 'o': 99.0, 'h': 101.0,
             'l': 98.5, 'v': 1000, 't': event_ms(DAY)},
            {'T': 'ZZBB', 'c': 55.25, 'o': 54.0, 'h': 56.0,
             'l': 53.5, 'v': 2000, 't': event_ms(DAY)},
            {'T': 'ZZUNKNOWN', 'c': 1.0, 'o': 1.0, 'h': 1.0,
             'l': 1.0, 'v': 5, 't': event_ms(DAY)},
        ]
    return {'status': 'OK', 'queryCount': len(rows),
            'resultsCount': len(rows), 'adjusted': True, 'results': rows}


class FakeHttp:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.calls = 0

    def get_grouped_daily(self, day):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        if self.status_code != 200:
            raise massive.MassiveTransportError(
                'HTTP %d' % self.status_code, http_status=self.status_code)
        return self.payload


class RaisingHttp:
    def __init__(self, exception_type):
        self.exception_type = exception_type

    def get_grouped_daily(self, day):
        raise massive.MassiveTransportError('boom')


def test_grouped_closes_returns_exact_provider_symbols():
    provider = massive.MassiveProvider(FakeHttp(grouped_payload()))
    fetch = provider.grouped_closes(DAY)
    assert fetch.status == 'accepted'
    assert fetch.day.closes == {
        'ZZAA': decimal.Decimal('100.5'),
        'ZZBB': decimal.Decimal('55.25'),
        'ZZUNKNOWN': decimal.Decimal('1.0'),
    }
    assert fetch.day.adjustment_basis == 'split'
    assert len(fetch.day.payload_sha256) == 64


def test_one_malformed_row_does_not_discard_the_day():
    rows = grouped_payload()['results']
    rows[0]['c'] = 0  # zero close is rejected per spec truth rule 7
    provider = massive.MassiveProvider(FakeHttp(grouped_payload(rows)))
    fetch = provider.grouped_closes(DAY)
    assert 'ZZAA' not in fetch.day.closes
    assert fetch.day.closes['ZZBB'] == decimal.Decimal('55.25')
    assert fetch.day.malformed_rows == 1


def test_transport_or_envelope_failure_is_typed():
    assert massive.MassiveProvider(RaisingHttp(requests.Timeout)).grouped_closes(
        DAY).status == 'transport_error'
    assert massive.MassiveProvider(FakeHttp({'status': 'ERROR'})).grouped_closes(
        DAY).status == 'rejected'
    assert massive.MassiveProvider(FakeHttp({'status': 'OK'})).grouped_closes(
        DAY).status == 'rejected'
    assert massive.MassiveProvider(FakeHttp(None, status_code=429)).grouped_closes(
        DAY).status == 'transport_error'


def test_transport_failure_preserves_the_persistable_backoff_deadline():
    deadline = dt.datetime(2026, 8, 28, 21, 1)
    error = massive.MassiveTransportError(
        'rate limited', http_status=429, backoff_until=deadline)
    fetch = massive.MassiveProvider(FakeHttp(error)).grouped_closes(DAY)
    assert fetch.status == 'transport_error'
    assert fetch.http_status == 429
    assert fetch.backoff_until == deadline


@pytest.mark.parametrize('mutate', [
    lambda payload: payload.pop('results'),
    lambda payload: payload.update(results='not a list'),
])
def test_broken_envelopes_are_rejected(mutate):
    payload = grouped_payload()
    mutate(payload)
    assert massive.MassiveProvider(
        FakeHttp(payload)).grouped_closes(DAY).status == 'rejected'


@pytest.mark.parametrize('row', [
    {'c': 1.0, 't': event_ms(DAY)},                        # missing T
    {'T': 'ZZAA', 't': event_ms(DAY)},                     # missing c
    {'T': 'ZZAA', 'c': 1.0},                               # missing t
    {'T': 'ZZAA', 'c': -5.0, 't': event_ms(DAY)},          # negative close
    {'T': 'ZZAA', 'c': 1.0,
     't': event_ms(DAY + dt.timedelta(days=3))},           # wrong date
])
def test_invalid_rows_are_counted_not_fatal(row):
    payload = grouped_payload([row, {'T': 'ZZOK', 'c': 2.5, 'o': 2.0,
                                     'h': 2.6, 'l': 1.9, 'v': 10,
                                     't': event_ms(DAY)}])
    fetch = massive.MassiveProvider(FakeHttp(payload)).grouped_closes(DAY)
    assert fetch.day.closes == {'ZZOK': decimal.Decimal('2.5')}
    assert fetch.day.malformed_rows == 1


def test_identical_duplicates_deduplicate_and_conflicts_refuse_the_symbol():
    rows = [
        {'T': 'ZZAA', 'c': 100.5, 't': event_ms(DAY)},
        {'T': 'ZZAA', 'c': 100.5, 't': event_ms(DAY)},   # identical: once
        {'T': 'ZZBB', 'c': 55.25, 't': event_ms(DAY)},
        {'T': 'ZZBB', 'c': 60.00, 't': event_ms(DAY)},   # conflict: refused
    ]
    fetch = massive.MassiveProvider(FakeHttp(grouped_payload(rows))).grouped_closes(DAY)
    assert fetch.day.closes == {'ZZAA': decimal.Decimal('100.5')}
    assert fetch.day.duplicate_conflicts == 1
    # Last-row-wins is forbidden: the conflicting symbol is simply absent.
    assert 'ZZBB' not in fetch.day.closes


def test_an_empty_expected_trading_day_is_no_data_never_accepted():
    fetch = massive.MassiveProvider(
        FakeHttp(grouped_payload([]))).grouped_closes(DAY)
    assert fetch.status == 'no_data'
    assert fetch.day is None


def test_missing_api_key_makes_the_adapter_dormant(monkeypatch):
    monkeypatch.delenv('RADAR_MASSIVE_API_KEY', raising=False)
    http = massive.MassiveHttp()
    with pytest.raises(massive.MassiveTransportError, match='key'):
        http.get_grouped_daily(DAY)


def test_the_pacer_spaces_five_calls_per_minute(monkeypatch):
    clock = {'now': 1000.0}
    sleeps = []
    monkeypatch.setenv('RADAR_MASSIVE_API_KEY', 'zz-test-key')
    http = massive.MassiveHttp(
        clock=lambda: clock['now'], sleep=lambda s: sleeps.append(s))

    captured = []

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            captured.append((url, dict(params or {})))
            response = type('R', (), {})()
            response.status_code = 200
            response.raise_for_status = lambda: None
            response.json = lambda: grouped_payload()
            return response

    http._session = FakeSession()
    for _ in range(6):
        http.get_grouped_daily(DAY)
    # Six calls against a five-per-minute budget: exactly one waits.
    assert len(sleeps) == 1 and sleeps[0] > 0
    url, params = captured[0]
    assert url.endswith('/v2/aggs/grouped/locale/us/market/stocks/2026-08-28')
    assert params['adjusted'] == 'true'
    assert params['apiKey'] == 'zz-test-key'


def test_a_429_sets_backoff_that_blocks_without_network(monkeypatch):
    clock = {'now': 1000.0}
    monkeypatch.setenv('RADAR_MASSIVE_API_KEY', 'zz-test-key')
    http = massive.MassiveHttp(clock=lambda: clock['now'], sleep=lambda s: None)

    class Fake429Session:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, timeout=None):
            self.calls += 1
            response = type('R', (), {})()
            response.status_code = 429

            def raise_for_status():
                error = requests.HTTPError('429')
                error.response = response
                raise error
            response.raise_for_status = raise_for_status
            response.json = lambda: {}
            return response

    session = Fake429Session()
    http._session = session
    with pytest.raises(massive.MassiveTransportError) as first:
        http.get_grouped_daily(DAY)
    assert first.value.backoff_until is not None
    with pytest.raises(massive.MassiveTransportError, match='backoff') as held:
        http.get_grouped_daily(DAY)
    assert held.value.backoff_until == first.value.backoff_until
    assert session.calls == 1
    clock['now'] += 61
    with pytest.raises(massive.MassiveTransportError):
        http.get_grouped_daily(DAY)
    assert session.calls == 2


def test_the_split_adjustment_parameter_is_actually_sent(monkeypatch):
    """A grouped row far from a seeded unadjusted value proves adjusted=true
    reached the wire; the assertion pins the request parameter itself."""
    monkeypatch.setenv('RADAR_MASSIVE_API_KEY', 'zz-test-key')
    captured = {}
    http = massive.MassiveHttp(clock=lambda: 0.0, sleep=lambda s: None)

    class CapturingSession:
        def get(self, url, params=None, timeout=None):
            captured.update(params or {})
            response = type('R', (), {})()
            response.status_code = 200
            response.raise_for_status = lambda: None
            # Post-split adjusted close, far from the pre-split 500.0.
            response.json = lambda: grouped_payload(
                [{'T': 'ZZSPLIT', 'c': 50.0, 't': event_ms(DAY)}])
            return response

    http._session = CapturingSession()
    fetch = massive.MassiveProvider(http).grouped_closes(DAY)
    assert captured['adjusted'] == 'true'
    assert fetch.day.closes['ZZSPLIT'] == decimal.Decimal('50.0')
    assert fetch.day.adjustment_basis == 'split'


def test_provider_source_attribute_feeds_the_generic_close_writer():
    assert massive.MassiveProvider(FakeHttp(grouped_payload())).source == \
        'massive_grouped'
