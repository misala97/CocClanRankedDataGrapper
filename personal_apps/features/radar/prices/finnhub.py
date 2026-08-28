# personal_apps/features/radar/prices/finnhub.py
"""The one module that knows Finnhub's JSON.

Free tier: 60 calls/minute, quotes roughly 20 minutes delayed. The delay is
survivable because divergence asks whether the price has moved at all, not
what it is to the cent -- but it is the reason this provider is behind an
adapter rather than called directly.
"""
import datetime as dt
import decimal
import os

import requests

from . import PriceUnavailable, Profile, Quote
from ..instruments import CatalogInstrument

API_BASE = 'https://finnhub.io/api/v1'

# Finnhub reports market capitalisation in MILLIONS of the listing currency.
# Storing the raw number would put every mega cap in the micro segment.
MARKET_CAP_UNIT = decimal.Decimal('1000000')

FINNHUB_EXCHANGE_BY_MIC = {
    'XETR': 'DE',
    'XNAS': 'US', 'XNGS': 'US', 'XNMS': 'US', 'XNCM': 'US',
    'XNYS': 'US', 'ARCX': 'US', 'XASE': 'US', 'BATS': 'US', 'IEXG': 'US',
}


class FinnhubHttp:
    """Thin transport, separated so the provider is testable without a network."""

    def __init__(self, api_key=None, timeout=20):
        self._key = api_key or os.getenv('FINNHUB_API_KEY')
        self._timeout = timeout

    def get(self, path, params):
        query = dict(params)
        query['token'] = self._key
        try:
            response = requests.get(API_BASE + path, params=query,
                                    timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable('%s: %s' % (path, exc)) from exc


def _decimal(value):
    if value is None:
        return None
    return decimal.Decimal(str(value))


class FinnhubProvider:
    def __init__(self, http):
        self._http = http

    def quotes(self, symbols):
        """Current quotes, keyed by symbol. Symbols that fail are absent.

        Absent rather than zero: a missing quote must not read as a price of
        nothing, which downstream would be a total collapse.
        """
        found = {}
        for symbol in symbols:
            try:
                payload = self._http.get('/quote', {'symbol': symbol})
            except PriceUnavailable:
                continue

            price = _decimal(payload.get('c'))
            # Finnhub answers c=0 for an unknown symbol rather than erroring.
            if not price:
                continue

            stamp = payload.get('t')
            found[symbol] = Quote(
                ticker=symbol,
                price=price,
                prev_close=_decimal(payload.get('pc')),
                quote_ts=(dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
                          .replace(tzinfo=None, microsecond=0) if stamp else None),
                # Always None in practice: /quote returns c, d, dp, h, l, o,
                # pc and t, with no volume field. Verified against the live
                # API rather than inferred. The read is left in place because
                # it costs nothing and a future provider behind this adapter
                # may supply it -- see quotes.price_status for what depends on
                # it, and what currently does not.
                volume=int(payload['v']) if payload.get('v') is not None else None,
            )
        return found

    def profile(self, symbol):
        """The company profile, or None when the provider covers no such thing.

        Two different facts, and they used to collapse into one None:

        - the request failed -- a timeout, a 429, a bad gateway. That says
          nothing about the symbol, so it RAISES and the caller asks again.
        - the request succeeded and came back empty. The provider genuinely
          has no profile for this symbol, and asking again in six hours will
          get the same nothing. `/stock/profile2` does not cover ETFs, so
          SPY, QQQ and DIA answer this way every time -- and because a caller
          could not tell the two apart, they were retried forever, spending
          slots that companies with a real profile were queueing for.
        """
        payload = self._http.get('/stock/profile2', {'symbol': symbol})
        if not payload:
            return None

        cap = payload.get('marketCapitalization')
        ipo = payload.get('ipo')
        return Profile(
            ticker=symbol,
            # None, not zero: an unknown cap belongs in the Unknown segment,
            # which is a first-class tab rather than a discard pile.
            market_cap=(_decimal(cap) * MARKET_CAP_UNIT) if cap else None,
            ipo_date=dt.date.fromisoformat(ipo) if ipo else None,
            exchange=payload.get('exchange'),
        )

    def stock_catalog(self, mic_code):
        """Finnhub symbol directory normalized to the catalog identity shape.

        A country directory is not proof that every row is Xetra. Rows without
        a provider-supplied MIC therefore remain unqualified and cannot map.
        """
        exchange = FINNHUB_EXCHANGE_BY_MIC.get(mic_code)
        if exchange is None:
            raise PriceUnavailable(f'/stock/symbol: unsupported MIC {mic_code}')
        payload = self._http.get('/stock/symbol', {'exchange': exchange})
        if not isinstance(payload, list):
            raise PriceUnavailable('/stock/symbol: provider returned no catalog')

        catalog = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            kind = str(row.get('type') or '').lower()
            if kind and not ('stock' in kind or 'etf' in kind or
                             'exchange traded fund' in kind):
                continue
            symbol = row.get('symbol') or row.get('displaySymbol')
            currency = row.get('currency')
            if not symbol or not currency:
                continue
            catalog.append(CatalogInstrument(
                symbol=str(symbol), name=row.get('description') or row.get('name'),
                mic=row.get('mic'), currency=currency, isin=row.get('isin'),
                figi=row.get('figi')))
        return catalog
