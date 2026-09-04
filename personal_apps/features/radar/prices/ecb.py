# personal_apps/features/radar/prices/ecb.py
"""The one module that knows the ECB's eurofxref XML.

Two files, one shape: `eurofxref-daily.xml` is today's rates and
`eurofxref-hist.xml` is every business day since 1999-01-04 in the same
envelope, 8 MB of it. So there is one parser and the only decision is which
URL to fetch.

No key, no account, no quota, and a publisher who will still be here next
year -- which is the whole reason this is the FX source. It publishes once
per TARGET business day at about 16:00 CET, so a rate for today does not
exist before then and asking again earlier will not conjure one.
"""
import datetime as dt
import decimal
import xml.etree.ElementTree as ET

import requests

from . import PriceUnavailable

DAILY_URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
HISTORY_URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml'

_NS = {'e': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}


class EcbHttp:
    """Thin transport, separated so the provider is testable without a network."""

    def __init__(self, timeout=(3.05, 30)):
        self._timeout = timeout

    def get_daily(self):
        return self._get(DAILY_URL)

    def get_history(self):
        return self._get(HISTORY_URL)

    def _get(self, url):
        try:
            response = requests.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            raise PriceUnavailable('ecb %s: %s' % (url, exc)) from exc


def parse_rates(raw, quote='USD'):
    """[(date, rate)] newest first, for the days that carry `quote`.

    A day whose envelope omits the currency is ABSENT from the result. The
    ECB does drop currencies (it stopped publishing several in 2024), and a
    day mapped to zero would convert a real close into a real lie.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise PriceUnavailable('ecb: malformed xml: %s' % exc) from exc

    rates = []
    for cube in root.findall('.//e:Cube[@time]', _NS):
        try:
            day = dt.date.fromisoformat(cube.get('time'))
        except (TypeError, ValueError):
            continue
        for entry in cube:
            if entry.get('currency') != quote:
                continue
            try:
                rates.append((day, decimal.Decimal(entry.get('rate'))))
            except (TypeError, decimal.InvalidOperation):
                pass
            break
    return rates


class EcbProvider:
    source = 'ecb'

    def __init__(self, http):
        self._http = http

    def rates(self, historical=False, quote='USD'):
        raw = (self._http.get_history() if historical
               else self._http.get_daily())
        return parse_rates(raw, quote=quote)
