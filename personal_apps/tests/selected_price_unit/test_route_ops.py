"""P07: the route, the shell flag and the ops field on a minimal Flask app
with the real radar blueprint. Authentication is patched at auth.py's own
helpers; the reader gets a fake store. No database, no provider."""
import flask
import pytest

import auth
from features.radar import config
from features.radar import price_chart_acquisition as acq
from features.radar import price_chart_contract as c
from features.radar import price_chart_reader as reader
from features.radar.routes import operations, radar_bp, views

from .helpers import FakeAdmission, FakeStore, bucket, naive, series

URL = '/radar/api/ticker/AAPL/price-chart'


@pytest.fixture()
def app(monkeypatch):
    app = flask.Flask('selected-price-test')
    app.config.update(TESTING=True, SECRET_KEY='test')
    stub = flask.Blueprint('auth', __name__)
    stub.add_url_rule('/login', 'login', lambda: 'login')
    app.register_blueprint(stub)
    app.register_blueprint(radar_bp)
    monkeypatch.setattr(auth, '_is_logged_in', lambda: True)
    monkeypatch.setattr(auth, 'is_admin', lambda: True)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', '1')
    monkeypatch.delenv('RADAR_SELECTED_PRICE_YAHOO_ENABLED', raising=False)
    monkeypatch.setattr(acq, '_instance', None)
    reader.clear_local_cache()
    yield app
    reader.clear_local_cache()


@pytest.fixture()
def store(monkeypatch):
    fake = FakeStore(buckets=[bucket(naive(2026, 9, 15, 13, 0))])
    monkeypatch.setattr(reader, 'ChartSqlStore', lambda: fake)
    return fake


def test_flag_off_is_feature_disabled_and_reads_nothing(app, store, monkeypatch):
    monkeypatch.delenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED')
    response = app.test_client().get(URL + '?span=1D&market=us')
    assert response.status_code == 404 and response.get_json()['code'] == 'feature_disabled'
    assert store.calls == []


def test_signed_out_is_sent_to_sign_in_before_anything_runs(app, store, monkeypatch):
    monkeypatch.setattr(auth, '_is_logged_in', lambda: False)
    response = app.test_client().get(URL + '?span=1D&market=us')
    assert response.status_code == 302 and store.calls == [] and acq._instance is None


@pytest.mark.parametrize('query,code,status', [
    ('span=1D&market=us&from=2026-09-01', 'unknown_query', 400),
    ('span=1D&span=1W&market=us', 'duplicate_query', 400),
    ('span=1D', 'missing_query', 400),
    ('span=1M&market=us', 'invalid_span', 400),
    ('span=1D&market=xx', 'invalid_market', 400),
    ('span=1D&market=de', 'unsupported_instrument', 422),
    ('span=1D&market=us&sources=myspace', 'invalid_sources', 400),
    ('span=1D&market=us&sources=', 'invalid_sources', 400),
    ('span=1D&market=us&symbol=MSFT', 'unknown_query', 400),
])
def test_only_three_validated_query_keys(app, store, query, code, status):
    response = app.test_client().get(f'{URL}?{query}')
    assert (response.status_code, response.get_json()['code']) == (status, code)
    assert store.calls == []


def test_identity_errors_map_to_their_statuses(app, monkeypatch):
    for fake, status, code in ((FakeStore(companies=[]), 404, 'unknown_ticker'),
                               (FakeStore(instruments=[]), 422, 'unsupported_instrument')):
        monkeypatch.setattr(reader, 'ChartSqlStore', lambda fake=fake: fake)
        response = app.test_client().get(URL + '?span=1D&market=us')
        assert (response.status_code, response.get_json()['code']) == (status, code)
    response = app.test_client().get('/radar/api/ticker/%3F%3F/price-chart?span=1D&market=us')
    assert (response.status_code, response.get_json()['code']) == (400, 'invalid_ticker')


def test_a_store_failure_is_a_503_with_a_code_and_no_sql(app, monkeypatch):
    fake = FakeStore(fail={'bucket_rows': c.ChartError('store_unavailable', 503, 'the store could not be read')})
    monkeypatch.setattr(reader, 'ChartSqlStore', lambda: fake)
    response = app.test_client().get(URL + '?span=1D&market=us')
    body = response.get_json()
    assert response.status_code == 503 and body == {'code': 'store_unavailable',
                                                     'error': 'the store could not be read'}


def test_disabled_provider_answers_200_with_local_data_and_the_full_contract(app, store):
    response = app.test_client().get(URL + '?span=1W&market=us&sources=bluesky,reddit')
    assert response.status_code == 200
    body = response.get_json()
    assert body['version'] == 1 and body['acquisition']['state'] == 'disabled'
    assert set(body['window']) == {'from', 'to', 'timezone', 'session_dates', 'partial', 'calendar_basis', 'bands'}
    assert set(body['chatter']) == {'step_minutes', 'from', 'to', 'slots', 'tone', 'normal_per_slot'}
    assert set(body['identity']) == {'ticker', 'company_id', 'instrument_id', 'mic', 'venue', 'currency',
                                     'provider_symbol', 'mapped_at', 'fingerprint'}
    sources = store.params['bucket_rows']['sources']
    assert 'bluesky' in sources and 'reddit' in sources and any(s.startswith('reddit:') for s in sources)
    assert 'fourchan' not in sources


def test_pending_then_ready_through_the_route(app, store, monkeypatch):
    window = c.window_for('1W', c.aware_utc(__import__('datetime').datetime.now(c.UTC)))
    pending = {'state': 'pending', 'retry_after_seconds': 2, 'reason': 'acquiring', 'series': None}
    ready = {'state': 'ready', 'retry_after_seconds': None, 'reason': None,
             'series': series(int(window.price_intervals()[0][0].timestamp()),
                              received_at=window.end.timestamp())}
    admission = FakeAdmission(pending, ready)
    monkeypatch.setattr(acq, 'Admission', lambda: admission)
    client = app.test_client()
    first = client.get(URL + '?span=1W&market=us').get_json()
    second = client.get(URL + '?span=1W&market=us').get_json()
    assert first['acquisition']['state'] == 'pending'
    assert second['acquisition']['state'] == 'ready' and second['price']['kind'] == 'bar_close'
    point = second['price']['points'][0]
    assert set(point) == {'at', 'start', 'end', 'value', 'provisional', 'break_before', 'regime'}
    assert set(second['price']) == {'source', 'kind', 'currency', 'mic', 'price_basis', 'adjustment_basis',
                                    'regimes', 'received_at', 'cache_age_seconds', 'latest_observation_at',
                                    'stale', 'fallback', 'interval_seconds', 'points'}


def test_the_fallback_counter_only_moves_for_an_existing_coordinator(app, monkeypatch):
    fake = FakeStore(daily=[])
    monkeypatch.setattr(reader, 'ChartSqlStore', lambda: fake)
    app.test_client().get(URL + '?span=1D&market=us')
    assert acq._instance is None


def test_the_shell_carries_only_the_chart_flag(app, monkeypatch):
    captured = {}

    class User:
        id = 1

    monkeypatch.setattr(views, 'build_payload', lambda args, user_id=None: {'rows': []})
    monkeypatch.setattr(views, 'current_user', lambda: User())
    monkeypatch.setattr(views, 'is_admin', lambda: False)
    monkeypatch.setattr(views, 'render_template', lambda name, **kw: captured.update(kw) or 'ok')
    monkeypatch.setenv('RADAR_SELECTED_PRICE_YAHOO_ENABLED', '1')
    app.test_client().get('/radar/')
    assert captured['shell']['selected_price_charts_enabled'] is True
    assert 'selected_price_yahoo_enabled' not in captured['shell']
    monkeypatch.delenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED')
    app.test_client().get('/radar/hub/')
    assert captured['shell']['selected_price_charts_enabled'] is False


def test_both_flags_default_off_and_the_provider_flag_needs_the_chart_flag(monkeypatch):
    monkeypatch.delenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', raising=False)
    monkeypatch.delenv('RADAR_SELECTED_PRICE_YAHOO_ENABLED', raising=False)
    assert (config.selected_price_charts_enabled(), config.selected_price_yahoo_enabled()) == (False, False)
    monkeypatch.setenv('RADAR_SELECTED_PRICE_YAHOO_ENABLED', 'true')
    assert config.selected_price_yahoo_enabled() is False
    monkeypatch.setenv('RADAR_SELECTED_PRICE_CHARTS_ENABLED', 'on')
    assert config.selected_price_yahoo_enabled() is True


@pytest.fixture()
def ops_fakes(monkeypatch):
    monkeypatch.setattr(operations.spend, 'summary', lambda: {})
    monkeypatch.setattr(operations.llm_sentiment, 'ops_summary', lambda: {})
    monkeypatch.setattr(operations.market_data, 'ops_summary', lambda now: {})
    monkeypatch.setattr(operations.observations, 'latest_observed_at', lambda: None)
    monkeypatch.setattr(operations, '_board_results', lambda now: {})


def test_ops_reports_process_health_without_creating_or_starting_anything(app, ops_fakes, monkeypatch):
    launched = []
    monkeypatch.setattr(acq, 'subprocess_launcher', lambda *a, **k: launched.append(1))
    monkeypatch.setattr(acq.subprocess, 'Popen', lambda *a, **k: launched.append(2))
    monkeypatch.setenv('WEB_CONCURRENCY', '2')
    body = app.test_client().get('/radar/api/ops').get_json()
    ops = body['selected_price_ops']
    assert ops['scope'] == 'process' and ops['charts_enabled'] is True and ops['yahoo_enabled'] is False
    assert ops['in_flight'] is False and set(ops['counters']) == set(acq.COUNTERS)
    assert ops['coordinator_started_at'] is None and 'process_started_at' not in ops
    assert (ops['configured_web_workers'], ops['configured_web_workers_source']) == (2, 'WEB_CONCURRENCY')
    assert acq._instance is None and launched == []


def test_ops_stays_admin_only(app, ops_fakes, monkeypatch):
    monkeypatch.setattr(auth, 'is_admin', lambda: False)
    assert app.test_client().get('/radar/api/ops').status_code == 403
