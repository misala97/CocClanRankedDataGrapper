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

API_BASE = 'https://finnhub.io/api/v1'

# Finnhub reports market capitalisation in MILLIONS of the listing currency.
# Storing the raw number would put every mega cap in the micro segment.
MARKET_CAP_UNIT = decimal.Decimal('1000000')


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
        """Company profile, or None when the provider has nothing at all."""
        try:
            payload = self._http.get('/stock/profile2', {'symbol': symbol})
        except PriceUnavailable:
            return None
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
