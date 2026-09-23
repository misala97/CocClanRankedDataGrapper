"""C1 Task 1: the bounded Alpaca transport against a LOOPBACK HTTP server, and
the child's classification of its answers.

The data host is replaced for the test process only; no provider is contacted
and no real credential is read. The two credential variables are set to
SENTINELS here, and every assertion that matters is that those sentinels leave
the process only inside the two documented request headers.

Binding: radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md and
radar-design/MD-SELECTED-PRICE-ALPACA-C1-SPEC.md."""
import http.server
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from features.radar import price_chart_contract as c
from features.radar import price_chart_fetch as fetch
from features.radar.prices import alpaca

from .helpers import identity, utc

NOW = utc(2026, 9, 16, 0, 34)                      # market closed, the validation's clock
WINDOW = c.window_for('1D', NOW)                   # the completed 2026-09-15 extended session
SPEC, _REFUSAL = c.alpaca_request_spec(identity(), WINDOW, now=NOW)

KEY_SENTINEL = 'PKSENTINELKEYID0000'
SECRET_SENTINEL = 'sentinel-secret-not-a-real-credential'
SEEN = []


def bars_body(symbol='AAPL', *, token=None, bars=None):
    series = [{'t': '2026-09-15T13:30:00Z', 'o': 1.0, 'h': 1.0, 'l': 1.0, 'c': 100.0, 'v': 10, 'n': 2, 'vw': 1.0},
              {'t': '2026-09-15T13:31:00Z', 'o': 1.0, 'h': 1.0, 'l': 1.0, 'c': 100.5, 'v': 10, 'n': 2, 'vw': 1.0}]
    payload = {'bars': {symbol: series if bars is None else bars}, 'next_page_token': token}
    return json.dumps(payload).encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body=b'', headers=()):
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        SEEN.append((parts.path, query, dict(self.headers)))
        symbol = (query.get('symbols') or [''])[0]
        if symbol == 'AAPL':
            self._send(200, bars_body(), [('Content-Type', 'application/json'),
                                          ('Set-Cookie', 'tracking=1'),
                                          ('X-RateLimit-Limit', '200')])
        elif symbol == 'PAGED':
            self._send(200, bars_body('PAGED', token='abc'), [('Content-Type', 'application/json')])
        elif symbol == 'GONE':
            self._send(200, json.dumps({'bars': {}, 'next_page_token': None}).encode())
        elif symbol == 'OTHER':
            self._send(200, bars_body('MSFT'))
        elif symbol == 'BIG':
            self.send_response(200)
            self.end_headers()
            for _ in range(10):
                self.wfile.write(b' ' * (64 * 1024))
        elif symbol == 'DECLARED':
            self.send_response(200)
            self.send_header('Content-Length', str(10 * 1024 * 1024))
            self.end_headers()
            self.wfile.write(b'{}')
        elif symbol == 'REDIRECT':
            self._send(302, b'', [('Location', 'http://elsewhere.invalid/v2/stocks/bars')])
        elif symbol == 'THROTTLE':
            self._send(429, b'{"message":"too many requests"}', [('Retry-After', '120')])
        elif symbol == 'FORBIDDEN':
            self._send(403, b'{"code":40110000,"message":"access key verification failed"}')
        elif symbol == 'UNAUTH':
            self._send(401, b'{"message":"unauthorized"}')
        elif symbol == 'TOORECENT':
            self._send(422, json.dumps({'code': 42210000,
                                        'message': 'subscription does not permit querying recent SIP data'}).encode())
        elif symbol == 'MISSING':
            self._send(404, b'{"code":40410000,"message":"not found"}')
        elif symbol == 'DOWN':
            self._send(503, b'')
        elif symbol == 'JUNK':
            self._send(200, b'not json')
        elif symbol == 'SLOW':
            time.sleep(1.5)
            try:
                self._send(200, bars_body())
            except OSError:
                pass
        else:
            self._send(400, b'{"message":"bad request"}')


@pytest.fixture(scope='module')
def server():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{httpd.server_address[1]}'
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture()
def local_host(server, monkeypatch):
    monkeypatch.setattr(alpaca, 'DATA_HOST', server)
    monkeypatch.setenv(alpaca.KEY_ID_ENV, KEY_SENTINEL)
    monkeypatch.setenv(alpaca.SECRET_ENV, SECRET_SENTINEL)
    SEEN.clear()
    return server


def bounded(timeout=(2.0, 3.0)):
    return alpaca.AlpacaHttp(timeout=timeout, max_body_bytes=fetch.BODY_LIMIT_BYTES)


def get(http, symbol, *, timeframe='1Min'):
    return http.fetch_bars_bounded(symbol, timeframe=timeframe, start=SPEC['start'], end=SPEC['end'])


# --- the request ------------------------------------------------------------------

def test_one_symbol_one_call_with_exactly_the_ruled_parameters(local_host):
    result = fetch.run(SPEC, clock=lambda: NOW.timestamp())
    assert result['kind'] == 'ok' and result['source'] == c.ALPACA_SOURCE
    assert len(SEEN) == 1
    path, query, headers = SEEN[0]
    assert path == alpaca.BARS_PATH
    assert query == {'symbols': ['AAPL'], 'timeframe': ['1Min'], 'start': [SPEC['start']],
                     'end': [SPEC['end']], 'feed': ['sip'], 'adjustment': ['raw'],
                     'sort': ['asc'], 'limit': ['10000']}
    assert 'Cookie' not in headers and 'Proxy-Authorization' not in headers
    assert headers['APCA-API-KEY-ID'] == KEY_SENTINEL
    assert headers['APCA-API-SECRET-KEY'] == SECRET_SENTINEL


def test_the_class_share_symbol_keeps_its_dot_and_asks_for_it_exactly(local_host):
    ident = identity(ticker='BRK.B', provider_symbol='BRK.B', mic='XNYS')
    spec, refusal = c.alpaca_request_spec(ident, WINDOW, now=NOW)
    assert refusal is None and spec['symbol'] == 'BRK.B'
    get(bounded(), spec['symbol'])
    assert SEEN[0][1]['symbols'] == ['BRK.B']


def test_the_fixed_host_ignores_ambient_proxies_cookies_and_redirects(local_host, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://user:pass@127.0.0.1:9')
    monkeypatch.setenv('HTTP_PROXY', 'http://user:pass@127.0.0.1:9')
    transport = bounded()
    assert transport._session.trust_env is False
    assert alpaca.DATA_HOST.startswith('http')
    assert alpaca.PRODUCTION_DATA_HOST == 'https://data.alpaca.markets'
    get(transport, 'AAPL')
    get(transport, 'AAPL')
    assert len(transport._session.cookies) == 0 and 'Cookie' not in SEEN[-1][2]
    assert get(transport, 'REDIRECT').problem == 'redirect'


@pytest.mark.parametrize('symbol,problem', [('BIG', 'oversized'), ('DECLARED', 'oversized'),
                                            ('JUNK', 'invalid_body')])
def test_bounded_body_refusals(local_host, symbol, problem):
    answer = get(bounded(), symbol)
    assert answer.problem == problem and answer.payload is None
    assert len(SEEN) == 1                                  # nothing retried, nothing followed


def test_a_slow_answer_is_a_timeout_not_a_hang(local_host):
    started = time.monotonic()
    answer = get(bounded(timeout=(0.5, 0.5)), 'SLOW')
    assert answer.problem == 'timeout' and time.monotonic() - started < 1.4


def test_an_unreachable_host_is_a_network_problem_without_its_url(monkeypatch):
    monkeypatch.setattr(alpaca, 'DATA_HOST', 'http://127.0.0.1:9')
    monkeypatch.setenv(alpaca.KEY_ID_ENV, KEY_SENTINEL)
    monkeypatch.setenv(alpaca.SECRET_ENV, SECRET_SENTINEL)
    result = fetch.run(SPEC, transport_factory=lambda: alpaca.AlpacaHttp(timeout=(0.5, 0.5),
                                                                        max_body_bytes=1024))
    assert result['kind'] in ('upstream_error', 'timeout')
    assert '127.0.0.1' not in json.dumps(result)


# --- credentials ------------------------------------------------------------------

def test_no_credential_value_leaves_the_process_outside_the_two_headers(local_host):
    result = fetch.run(SPEC, clock=lambda: NOW.timestamp())
    encoded = fetch.encode_result(result).decode()
    for secret in (KEY_SENTINEL, SECRET_SENTINEL):
        assert secret not in encoded
        assert secret not in json.dumps(SPEC)
        assert secret not in repr(bounded())
    header_names = set(SEEN[0][2])
    assert {'APCA-API-KEY-ID', 'APCA-API-SECRET-KEY'} <= header_names
    for name, value in SEEN[0][2].items():
        if name not in ('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY'):
            assert KEY_SENTINEL not in value and SECRET_SENTINEL not in value


def test_a_provider_failure_never_carries_credentials_or_provider_text(local_host):
    for symbol in ('FORBIDDEN', 'THROTTLE', 'TOORECENT'):
        answer = get(bounded(), symbol)
        classified = fetch.classify_alpaca(answer, dict(SPEC, symbol=symbol), received_at=0)
        text = json.dumps(classified)
        assert KEY_SENTINEL not in text and SECRET_SENTINEL not in text
        assert 'access key verification failed' not in text
        assert 'subscription does not permit' not in text


@pytest.mark.parametrize('missing', [alpaca.KEY_ID_ENV, alpaca.SECRET_ENV, 'both'])
def test_missing_credentials_refuse_before_any_request(local_host, monkeypatch, missing):
    for name in ((alpaca.KEY_ID_ENV, alpaca.SECRET_ENV) if missing == 'both' else (missing,)):
        monkeypatch.setenv(name, '   ')
    assert alpaca.credentials() is None
    answer = get(bounded(), 'AAPL')
    assert answer.problem == 'credentials' and SEEN == []
    assert fetch.run(SPEC)['kind'] == 'credentials_missing'


# --- classification ---------------------------------------------------------------

def test_statuses_come_back_for_the_child_to_classify(local_host):
    throttle = get(bounded(), 'THROTTLE')
    assert (throttle.status, throttle.retry_after) == (429, '120')
    assert fetch.classify_alpaca(throttle, SPEC, received_at=0) == {
        'kind': 'throttle', 'status': 429, 'retry_after': 120}
    for symbol, kind in (('FORBIDDEN', 'permission'), ('UNAUTH', 'permission'),
                         ('MISSING', 'unsupported'), ('DOWN', 'upstream_error'),
                         ('TOORECENT', 'waiting')):
        answer = get(bounded(), symbol)
        assert fetch.classify_alpaca(answer, SPEC, received_at=0)['kind'] == kind, symbol


def test_an_empty_bars_map_is_empty_and_a_page_token_is_truncated(local_host):
    empty = fetch.classify_alpaca(get(bounded(), 'GONE'), dict(SPEC, symbol='GONE'), received_at=0)
    assert empty['kind'] == 'empty'
    paged = fetch.classify_alpaca(get(bounded(), 'PAGED'), dict(SPEC, symbol='PAGED'), received_at=0)
    assert paged['kind'] == 'truncated'


def test_another_symbols_series_is_an_identity_mismatch(local_host):
    answer = get(bounded(), 'OTHER')
    assert fetch.classify_alpaca(answer, dict(SPEC, symbol='OTHER'), received_at=0)['kind'] == 'identity_mismatch'


def test_an_empty_clamped_window_is_waiting_and_makes_no_request(local_host):
    empty = dict(SPEC, end=SPEC['start'])
    assert fetch.run(empty, clock=lambda: NOW.timestamp())['kind'] == 'waiting'
    assert SEEN == []


def test_the_child_writes_one_bounded_alpaca_result(local_host):
    import io
    out = io.BytesIO()
    assert fetch.main(io.BytesIO(json.dumps(SPEC).encode()), out) == 0
    answer = json.loads(out.getvalue())
    assert answer['kind'] == 'ok' and answer['source'] == c.ALPACA_SOURCE
    assert len(answer['bars']) == 2
    assert len(SEEN) == 1
