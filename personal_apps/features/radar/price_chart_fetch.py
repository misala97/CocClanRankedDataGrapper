"""Selected price charts: the fetch child program.

price_chart_acquisition starts this module as its own fresh interpreter,

    python -E -s -B -m features.radar.price_chart_fetch

with an allowlisted minimal environment. It reads ONE validated public
request spec (JSON, at most SPEC_LIMIT_BYTES) from stdin, makes at most one
Yahoo chart request for it, normalizes the answer with the pure contract,
writes ONE JSON result (at most RESULT_LIMIT_BYTES) to stdout and exits 0.

What it deliberately does not have: the parent's main script, a Flask app or
request context, a database handle or engine, dotenv, the web process's
requests session or environment -- so no proxy settings, provider keys,
database or application secrets are even present -- an arbitrary URL, a
retry, an alternate symbol or a cache. Its imports are the pure contract and
the Yahoo module -- nothing that reaches `extensions`, `models` or `app`
(tests/selected_price_unit checks a real child's own sys.modules and
environment).

Binding: radar-design/MD-SELECTED-PRICE-SPEC.md section 6, as amended by
radar-design/MD-SELECTED-PRICE-REVIEW-1-RULING.md (F1/F2).
"""
from __future__ import annotations

import email.utils
import json
import sys
import time

from . import price_chart_contract as contract
from .prices.yahoo import YahooHttp

BODY_LIMIT_BYTES = 512 * 1024
RESULT_LIMIT_BYTES = 512 * 1024
SPEC_LIMIT_BYTES = 2048
CHUNK_BYTES = 64 * 1024
CONNECT_TIMEOUT_S = 2.0
READ_TIMEOUT_S = 3.0


def parse_retry_after(value, now_epoch: float) -> int | None:
    """Seconds from a Retry-After header, or None when it is not valid."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.isdigit():
        return int(text)
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None or when.tzinfo is None:
        return None
    return max(0, int(when.timestamp() - now_epoch))


def classify(fetch, spec: dict, *, received_at: float) -> dict:
    """One bounded response, as the result the supervisor acts on."""
    if fetch.problem == 'timeout':
        return {'kind': 'timeout', 'status': fetch.status}
    if fetch.problem == 'network':
        return {'kind': 'upstream_error', 'reason': 'network', 'status': fetch.status}
    if fetch.problem in ('redirect', 'oversized', 'invalid_body'):
        return {'kind': 'invalid', 'reason': fetch.problem, 'status': fetch.status}
    if fetch.status in (401, 403, 429):
        return {'kind': 'throttle', 'status': fetch.status,
                'retry_after': parse_retry_after(fetch.retry_after, received_at)}
    if fetch.status == 404:
        return {'kind': 'unsupported', 'status': 404}
    if fetch.status is not None and fetch.status >= 500:
        return {'kind': 'upstream_error', 'reason': 'server', 'status': fetch.status}
    if fetch.status != 200:
        return {'kind': 'invalid', 'reason': 'status', 'status': fetch.status}
    result = contract.normalize_yahoo(fetch.payload, spec, received_at=received_at)
    result['status'] = 200
    return result


def encode_result(result: dict) -> bytes:
    data = json.dumps(result, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(data) > RESULT_LIMIT_BYTES:
        data = json.dumps({'kind': 'invalid', 'reason': 'result exceeds bound'}).encode('utf-8')
    return data


def _transport():
    return YahooHttp(timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S), cache=False,
                     max_body_bytes=BODY_LIMIT_BYTES)


def run(request_spec, transport_factory=_transport, clock=time.time) -> dict:
    """The child's work without the pipes, so tests can run it in-process."""
    if not contract._spec_ok(request_spec):
        return {'kind': 'invalid', 'reason': 'request_spec'}
    try:
        fetch = transport_factory().fetch_chart_bounded(
            request_spec['symbol'], interval=request_spec['interval'],
            period1=request_spec['period1'], period2=request_spec['period2'],
            include_prepost=request_spec['include_prepost'])
        return classify(fetch, request_spec, received_at=clock())
    except Exception as exc:  # noqa: BLE001 -- a result, never a traceback over the pipe
        return {'kind': 'invalid', 'reason': type(exc).__name__}


def read_spec(stream):
    """The request spec from a binary stream, or None when it is over its
    bound or not JSON (run() then refuses it as an invalid request)."""
    data = stream.read(SPEC_LIMIT_BYTES + 1)
    if not data or len(data) > SPEC_LIMIT_BYTES:
        return None
    try:
        return json.loads(data)
    except ValueError:
        return None


def main(stdin=None, stdout=None) -> int:
    """One request in, one result out."""
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout.buffer if stdout is None else stdout
    stdout.write(encode_result(run(read_spec(stdin))))
    stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
