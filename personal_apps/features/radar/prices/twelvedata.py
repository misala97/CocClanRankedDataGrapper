# personal_apps/features/radar/prices/twelvedata.py
"""Daily closes, for the volatility estimate behind price_move_z.

Here because Finnhub's free tier returns 403 for /stock/candle, measured. That
matters more than it sounds: no daily closes means no sigma, no sigma means
price_move_z is always None, and divergence stops ranking anything at all.

Twelve Data's free quotes are four hours delayed, which is why it is not the
quote provider. A four-hour-old daily bar is the same daily bar.
"""
import datetime as dt
import decimal
import os

import requests

from . import PriceUnavailable
from ..instruments import CatalogInstrument

API_BASE = 'https://api.twelvedata.com'


class TwelveDataHttp:
    """Thin transport, separated so the provider is testable without a network."""

    def __init__(self, api_key=None, timeout=20):
        self._key = api_key or os.getenv('TWELVEDATA_API_KEY')
        self._timeout = timeout

    def get(self, path, params):
        query = dict(params)
        query['apikey'] = self._key
        try:
            response = requests.get(API_BASE + path, params=query,
                                    timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable('%s: %s' % (path, exc)) from exc


class TwelveDataProvider:
    def __init__(self, http):
        self._http = http

    def daily_closes(self, symbol, days):
        """(date, close) oldest first. Empty when there is no usable history.

        Empty rather than raising: an unknown symbol and a tripped rate limit
        both arrive as status='error' with HTTP 200, and neither is a reason to
        take down the job that asked.
        """
        try:
            payload = self._http.get('/time_series', {
                'symbol': symbol, 'interval': '1day', 'outputsize': days})
        except PriceUnavailable:
            return []

        if payload.get('status') != 'ok':
            return []

        closes = []
        for row in payload.get('values') or []:
            try:
                when = dt.date.fromisoformat(row['datetime'][:10])
                closes.append((when, decimal.Decimal(str(row['close']))))
            except (KeyError, ValueError, decimal.InvalidOperation):
                continue

        # Newest first on the wire; volatility wants chronological order.
        return sorted(closes)

    def stock_catalog(self, mic_code):
        """Normalized stock/ETF reference data for a permitted MIC catalog."""
        payload = self._http.get('/stocks', {
            'mic_code': mic_code, 'show_plan': 'true'})
        if not isinstance(payload, dict) or payload.get('status') == 'error':
            raise PriceUnavailable('/stocks: provider returned no catalog')

        rows = payload.get('data') or []
        catalog = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            kind = str(row.get('type') or row.get('instrument_type') or '').lower()
            if not ('stock' in kind or 'etf' in kind or
                    'exchange traded fund' in kind):
                continue
            symbol = row.get('symbol')
            currency = row.get('currency')
            if not symbol or not currency:
                continue
            row_mic = row.get('mic_code') or row.get('mic')
            # A German catalog must explicitly identify an EUR Xetra listing;
            # do not infer either field from the request parameter.
            if mic_code == 'XETR' and (row_mic != 'XETR' or currency != 'EUR'):
                continue
            catalog.append(CatalogInstrument(
                symbol=str(symbol), name=row.get('name') or row.get('description'),
                mic=row_mic, currency=currency, isin=row.get('isin'),
                figi=row.get('figi')))
        return catalog
