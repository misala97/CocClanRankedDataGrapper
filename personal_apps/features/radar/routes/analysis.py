"""JSON for the hub's Analysis / Explore page (HA1 US daily).

Two authenticated reads, both delegating to features/radar/analysis.py:

  GET /radar/api/analysis/resolve?ticker=AAPL
  GET /radar/api/analysis/company/<company_id>?instrument_id=&from=&to=

Ordinary `login_required` access, as the search endpoint has: this is a
reader's own retrospective view, not an admin surface. Errors carry a stable
`code` and a sentence; never SQL, never a stack, never a 200 with an empty
series standing in for a failure.
"""
import datetime as dt

from flask import jsonify, request

from auth import login_required

from .. import analysis as analysis_mod
from ..analysis_contract import ContractError, parse_instrument_id, parse_range
from ._blueprint import radar_bp


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _refused(error: ContractError):
    return jsonify({'error': error.message, 'code': error.code}), error.status


@radar_bp.route('/api/analysis/resolve')
@login_required
def analysis_resolve():
    """The current company and its eligible US primary for one symbol."""
    args = list(request.args.items(multi=True))
    keys = [key for key, _ in args]
    if keys != ['ticker']:
        return jsonify({'error': 'exactly one ticker query parameter is required',
                        'code': 'unknown_query' if set(keys) - {'ticker'} else
                        ('duplicate_query' if keys.count('ticker') > 1 else 'missing_query')}), 400
    try:
        return jsonify(analysis_mod.resolve_company(args[0][1], _now()))
    except ContractError as error:
        return _refused(error)


@radar_bp.route('/api/analysis/company/<int:company_id>')
@login_required
def analysis_company(company_id):
    """Daily closes and retained daily counts for a pinned identity."""
    if company_id <= 0:
        return jsonify({'error': 'company_id must be a positive integer',
                        'code': 'invalid_id'}), 400
    args = list(request.args.items(multi=True))
    now = _now()
    try:
        start, end = parse_range(args, now)
        instrument_id = parse_instrument_id(args)
        payload = analysis_mod.read_company(company_id, instrument_id, start, end, now)
    except ContractError as error:
        return _refused(error)
    return jsonify(payload)
