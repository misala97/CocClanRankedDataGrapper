"""JSON for the selected-instrument price chart (MD-SELECTED-PRICE).

  GET /radar/api/ticker/<ticker>/price-chart?span=1D|1W&market=us&sources=...

Ordinary `login_required` access, as the ticker detail it sits beside. Only
three query keys exist: no from/to, no provider, no symbol override. The
request is validated and the identity resolved before any acquisition is
admitted, and the answer is assembled from local data only -- provider I/O
happens in price_chart_acquisition's background child, never here. An
upstream failure alone is a 200 that explains itself; a bounded store
failure is a 503 with a stable code, never an empty success.

Switched off (the default), the route is a 404 with code `feature_disabled`
and the hub draws the chart it always drew.
"""
import datetime as dt

from flask import jsonify, request

from auth import login_required

from .. import config
from .. import price_chart_acquisition as acquisition
from .. import price_chart_reader as reader
from ..price_chart_contract import MAX_SOURCES, SPANS, ChartError
from ._blueprint import radar_bp
from .api import BadQuery, parse_query

ALLOWED_QUERY_KEYS = ('span', 'market', 'sources')


def _refused(code: str, status: int, message: str):
    return jsonify({'error': message, 'code': code}), status


def parse_chart_query(pairs):
    """(span, concrete sources) or raise ChartError. Repeats and unknown keys
    are refused rather than collapsed or ignored."""
    seen = {}
    for key, value in pairs:
        if key not in ALLOWED_QUERY_KEYS:
            raise ChartError('unknown_query', 400, f'unsupported query parameter {key!r}')
        if key in seen:
            raise ChartError('duplicate_query', 400, f'query parameter {key!r} was given more than once')
        seen[key] = value
    if 'span' not in seen or 'market' not in seen:
        raise ChartError('missing_query', 400, 'span and market are required')
    if seen['span'] not in SPANS:
        raise ChartError('invalid_span', 400, 'span must be 1D or 1W')
    if seen['market'] not in ('us', 'de'):
        raise ChartError('invalid_market', 400, 'unknown market')
    if seen['market'] != 'us':
        raise ChartError('unsupported_instrument', 422,
                         'selected price charts cover US primary listings only')
    raw = seen.get('sources')
    if raw is not None and not raw.strip():
        raise ChartError('invalid_sources', 400, 'sources must name at least one source')
    try:
        query = parse_query({'market': 'us', **({'sources': raw} if raw is not None else {})})
    except BadQuery as exc:
        raise ChartError('invalid_sources', 400, str(exc)) from exc
    concrete = list(dict.fromkeys(config.expand_sources_for_history(query.sources)))
    if len(concrete) > MAX_SOURCES:
        raise ChartError('too_many_sources', 400, f'at most {MAX_SOURCES} concrete sources')
    return seen['span'], concrete


@radar_bp.route('/api/ticker/<ticker>/price-chart')
@login_required
def ticker_price_chart(ticker):
    if not config.selected_price_charts_enabled():
        return _refused('feature_disabled', 404, 'selected price charts are switched off')
    try:
        span, sources = parse_chart_query(request.args.items(multi=True))
        payload = reader.build_response(ticker, sources, span, dt.datetime.now(dt.timezone.utc),
                                        coordinator=acquisition.Admission())
    except ChartError as error:
        return _refused(error.code, error.status, error.message)
    if payload['price'] is not None and payload['price']['fallback']:
        acquisition.note_fallback()
    return jsonify(payload)
