"""P06/P09: the bounded transport against a LOOPBACK HTTP server, and the
child's classification. The Yahoo host is replaced for the test process only;
no provider is contacted. The emitted query string is the request FORM this
code sends -- whether Yahoo answers that form identically to range=1d/5d was
not checked and is not claimed."""
import http.server
import io
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from features.radar import price_chart_contract as c
from features.radar import price_chart_fetch as fetch
from features.radar.prices import yahoo

from .helpers import identity, utc

NOW = utc(2026, 9, 15, 13, 50, 19)
WINDOW = c.window_for('1W', NOW)
SPEC = c.request_spec(identity(), WINDOW)
SEEN = []


def chart_body(symbol='AAPL'):
    return json.dumps({'chart': {'result': [{
        'meta': {'symbol': symbol, 'currency': 'USD', 'exchangeName': 'NMS'},
        'timestamp': [SPEC['anchor'], SPEC['anchor'] + 300],
        'indicators': {'quote': [{'close': [100.0, 100.5]}]}}], 'error': None}}).encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parts = urlsplit(self.path)
        symbol = parts.path.rsplit('/', 1)[-1]
        SEEN.append((symbol, parse_qs(parts.query), dict(self.headers)))
        if symbol == 'AAPL':
            body = chart_body()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Set-Cookie', 'B=tracking')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
            self.send_response(302)
            self.send_header('Location', 'http://elsewhere.invalid/v8/finance/chart/AAPL')
            self.end_headers()
        elif symbol == 'THROTTLE':
            self.send_response(429)
            self.send_header('Retry-After', '120')
            self.end_headers()
        elif symbol == 'MISSING':
            self.send_response(404)
            self.end_headers()
        elif symbol == 'DOWN':
            self.send_response(503)
            self.end_headers()
        elif symbol == 'JUNK':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'not json')
        elif symbol == 'SLOW':
            time.sleep(1.5)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(chart_body())
            except OSError:
                pass                      # the client already gave up, which is the point


@pytest.fixture(scope='module')
def server():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{httpd.server_address[1]}/v8/finance/chart/'
    httpd.shutdown()


@pytest.fixture()
def local_base(server, monkeypatch):
    monkeypatch.setattr(yahoo, 'API_BASE', server)
    SEEN.clear()
    return server


def bounded(timeout=(2.0, 3.0)):
    return yahoo.YahooHttp(timeout=timeout, cache=False, max_body_bytes=fetch.BODY_LIMIT_BYTES)


def get(http, symbol):
    return http.fetch_chart_bounded(symbol, interval=SPEC['interval'], period1=SPEC['period1'],
                                    period2=SPEC['period2'], include_prepost=SPEC['include_prepost'])


def test_the_child_sends_exactly_the_window_epochs_and_normalizes_the_answer(local_base):
    result = fetch.run(SPEC, transport_factory=bounded, clock=lambda: NOW.timestamp())
    assert result['kind'] == 'ok' and result['status'] == 200
    assert result['bars'] == [[SPEC['anchor'], 100.0], [SPEC['anchor'] + 300, 100.5]]
    symbol, query, headers = SEEN[-1]
    assert symbol == 'AAPL'
    assert query == {'interval': ['5m'], 'period1': [str(SPEC['period1'])],
                     'period2': [str(SPEC['period2'])], 'includePrePost': ['false']}
    assert 'range' not in query and 'Cookie' not in headers


def test_a_second_bounded_request_carries_no_cookie_and_hits_the_server_again(local_base):
    http = bounded()
    get(http, 'AAPL')
    get(http, 'AAPL')
    assert len(SEEN) == 2
    assert 'Cookie' not in SEEN[-1][2] and len(http._session.cookies) == 0


@pytest.mark.parametrize('symbol,problem', [('BIG', 'oversized'), ('DECLARED', 'oversized'),
                                            ('REDIRECT', 'redirect'), ('JUNK', 'invalid_body')])
def test_bounded_refusals(local_base, symbol, problem):
    answer = get(bounded(), symbol)
    assert answer.problem == problem and answer.payload is None
    assert len(SEEN) == 1                                   # nothing followed, nothing retried


def test_statuses_come_back_for_the_caller_to_classify(local_base):
    throttle = get(bounded(), 'THROTTLE')
    assert (throttle.status, throttle.retry_after, throttle.problem) == (429, '120', None)
    assert fetch.classify(throttle, SPEC, received_at=0) == {'kind': 'throttle', 'status': 429, 'retry_after': 120}
    assert fetch.classify(get(bounded(), 'MISSING'), SPEC, received_at=0)['kind'] == 'unsupported'
    assert fetch.classify(get(bounded(), 'DOWN'), SPEC, received_at=0)['kind'] == 'upstream_error'


def test_a_slow_answer_is_a_timeout_not_a_hang(local_base):
    started = time.monotonic()
    answer = get(bounded(timeout=(0.5, 0.5)), 'SLOW')
    assert answer.problem == 'timeout' and time.monotonic() - started < 1.4


def test_an_unreachable_host_is_a_network_problem_without_its_url(monkeypatch):
    monkeypatch.setattr(yahoo, 'API_BASE', 'http://127.0.0.1:9/v8/finance/chart/')
    result = fetch.run(SPEC, transport_factory=lambda: yahoo.YahooHttp(timeout=(0.5, 0.5), cache=False,
                                                                       max_body_bytes=1024))
    assert result['kind'] in ('upstream_error', 'timeout')
    assert '127.0.0.1' not in json.dumps(result)


def test_the_default_transport_is_unchanged_for_existing_callers(local_base):
    http = yahoo.YahooHttp()
    first = http.get_chart('AAPL', interval='5m', period1=1, period2=2, include_prepost=True)
    second = http.get_chart('AAPL', interval='5m', period1=1, period2=2, include_prepost=True)
    assert first == second and len(SEEN) == 1              # still cached for 60 s
    assert http._session.trust_env is True
    with pytest.raises(RuntimeError):
        http.fetch_chart_bounded('AAPL', interval='5m', period1=1, period2=2, include_prepost=True)
    uncached = yahoo.YahooHttp(cache=False)
    uncached.get_chart('AAPL', interval='5m', period1=1, period2=2, include_prepost=True)
    uncached.get_chart('AAPL', interval='5m', period1=1, period2=2, include_prepost=True)
    assert len(SEEN) == 3 and bounded()._session.trust_env is False


def test_retry_after_parsing():
    assert fetch.parse_retry_after('120', 0) == 120
    assert fetch.parse_retry_after('Wed, 16 Sep 2026 13:50:19 GMT', NOW.timestamp()) == 86_400
    for bad in (None, '', 'soon', '-5'):
        assert fetch.parse_retry_after(bad, 0) is None


def test_the_child_main_reads_one_bounded_request_and_writes_one_result(local_base):
    out = io.BytesIO()
    assert fetch.main(io.BytesIO(json.dumps(SPEC).encode()), out) == 0
    answer = json.loads(out.getvalue())
    assert answer['kind'] == 'ok' and answer['bars'] == [[SPEC['anchor'], 100.0], [SPEC['anchor'] + 300, 100.5]]
    padded = json.dumps(dict(SPEC, pad='x' * fetch.SPEC_LIMIT_BYTES)).encode()
    for raw in (b'', b'not json', b'\xff\xfe', b'[1, 2]', json.dumps({'version': 1}).encode(), padded):
        out = io.BytesIO()
        assert fetch.main(io.BytesIO(raw), out) == 0
        assert json.loads(out.getvalue()) == {'kind': 'invalid', 'reason': 'request_spec'}
    assert len(SEEN) == 1                                   # only the valid request reached the server


def test_the_result_bound():
    huge = fetch.encode_result({'kind': 'ok', 'pad': 'x' * fetch.RESULT_LIMIT_BYTES})
    assert json.loads(huge) == {'kind': 'invalid', 'reason': 'result exceeds bound'}
