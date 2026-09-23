# personal_apps/features/radar/prices/alpaca.py
"""The one module that knows Alpaca's historical-bars JSON.

Its single role is the selected-instrument price chart: ONE pinned US/USD
symbol, ONE bounded request per acquisition child, consolidated SIP bars whose
`end` is already clamped at least fifteen minutes behind now by the caller.
It is not a quote source, not a poller and not a universe collector; nothing
here writes to the store or reaches the trading, account or asset endpoints.

The safety properties are `prices/yahoo.fetch_chart_bounded`'s, not its
response shape: a fixed HTTPS host, no ambient proxy or netrc (`trust_env`
off), no cookie jar, no redirect followed, no retry, no pagination, and a body
read in chunks and abandoned the moment it passes `max_body_bytes`. Status and
`Retry-After` come back for the caller to classify rather than being folded
into an exception, because request exceptions can carry the URL.

Credentials: `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` are read BY NAME from
the environment at the last responsible point -- inside the one request -- and
put only into the two documented headers. They are never held on the instance,
never formatted into a URL, an argument, a log line, an exception or a
returned value, and a missing or blank one refuses the request outright rather
than sending an anonymous one.

Binding: radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md.
"""
import collections
import http.cookiejar
import json
import os

import requests

#: The production data host. Tests replace DATA_HOST for their own process;
#: this constant is what production is asserted against.
PRODUCTION_DATA_HOST = 'https://data.alpaca.markets'
DATA_HOST = PRODUCTION_DATA_HOST
BARS_PATH = '/v2/stocks/bars'

KEY_ID_ENV = 'APCA_API_KEY_ID'
SECRET_ENV = 'APCA_API_SECRET_KEY'
KEY_ID_HEADER = 'APCA-API-KEY-ID'
SECRET_HEADER = 'APCA-API-SECRET-KEY'

#: Radar's two chart intervals, as Alpaca spells them.
TIMEFRAMES = {60: '1Min', 300: '5Min'}
FEED = 'sip'
ADJUSTMENT = 'raw'
SORT = 'asc'
LIMIT = 10_000
#: The documented Basic delay is 15 minutes; the extra minute is the ruling's
#: deliberate safety margin, applied by price_chart_contract when it builds the
#: request, never here.
DELAY_MARGIN_SECONDS = 16 * 60

#: A bar the provider returned: `t` the bar START (RFC-3339 UTC, nanosecond
#: precision reserved by the documentation), `c` its close.
TIMESTAMP_KEY = 't'
CLOSE_KEY = 'c'

#: What one bounded request answered. `problem` is None, 'credentials',
#: 'timeout', 'network', 'redirect', 'oversized' or 'invalid_body'; `payload`
#: is the parsed JSON body when there was one inside the bound -- for an error
#: status too, so the caller can read its numeric `code` -- else None.
BoundedBars = collections.namedtuple('BoundedBars', 'status retry_after payload problem')

#: The FAQ's documented refusal for a SIP window that is still too recent.
TOO_RECENT_CODE = 42210000


def credentials(source=None):
    """The two named variables as a pair, or None when either is missing.

    The values are returned to exactly one caller -- the request below -- and
    are never logged, stored on an instance or returned anywhere else.
    """
    source = os.environ if source is None else source
    key_id = (source.get(KEY_ID_ENV) or '').strip()
    secret = (source.get(SECRET_ENV) or '').strip()
    if not key_id or not secret:
        return None
    return key_id, secret


class AlpacaHttp:
    """Bounded transport for one short-lived acquisition child."""

    def __init__(self, timeout=(2.0, 3.0), *, max_body_bytes):
        self._session = requests.Session()
        self._timeout = timeout
        self._max_body_bytes = max_body_bytes
        # No environment proxy, no netrc, no cookie is ever stored or sent.
        self._session.trust_env = False
        self._session.cookies.set_policy(
            http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))

    def __repr__(self):
        # Explicit, so no default repr can ever grow a credential attribute.
        return f'<AlpacaHttp max_body_bytes={self._max_body_bytes}>'

    def fetch_bars_bounded(self, symbol, *, timeframe, start, end):
        """One historical-bars request for exactly one symbol.

        Never raises for a transport failure and never returns provider text:
        the caller owns the classification, and an exception message can carry
        the URL and its query.
        """
        secrets = credentials()
        if secrets is None:
            return BoundedBars(None, None, None, 'credentials')
        key_id, secret = secrets
        params = {
            'symbols': symbol, 'timeframe': timeframe, 'start': start, 'end': end,
            'feed': FEED, 'adjustment': ADJUSTMENT, 'sort': SORT, 'limit': LIMIT,
        }
        try:
            response = self._session.get(
                DATA_HOST + BARS_PATH, params=params, timeout=self._timeout,
                stream=True, allow_redirects=False,
                headers={'Accept': 'application/json',
                         KEY_ID_HEADER: key_id, SECRET_HEADER: secret})
        except requests.Timeout:
            return BoundedBars(None, None, None, 'timeout')
        except requests.RequestException:
            return BoundedBars(None, None, None, 'network')
        finally:
            del key_id, secret, secrets
        with response:
            status = response.status_code
            retry_after = response.headers.get('Retry-After')
            if response.is_redirect or 300 <= status < 400:
                return BoundedBars(status, retry_after, None, 'redirect')
            declared = response.headers.get('Content-Length', '')
            if declared.isdigit() and int(declared) > self._max_body_bytes:
                return BoundedBars(status, retry_after, None, 'oversized')
            chunks, size = [], 0
            try:
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > self._max_body_bytes:
                        return BoundedBars(status, retry_after, None, 'oversized')
                    chunks.append(chunk)
            except requests.Timeout:
                return BoundedBars(status, retry_after, None, 'timeout')
            except requests.RequestException:
                return BoundedBars(status, retry_after, None, 'network')
        try:
            payload = json.loads(b''.join(chunks))
        except ValueError:
            # Only a 200 has to be JSON; an error status with an empty or
            # unparsable body is still classified by its status alone.
            return BoundedBars(status, retry_after, None,
                               'invalid_body' if status == 200 else None)
        return BoundedBars(status, retry_after, payload, None)


def refusal_code(payload):
    """The numeric `code` of an error body, or None. Only the number is ever
    read: the accompanying `message` is provider text and stays unread."""
    if not isinstance(payload, dict):
        return None
    code = payload.get('code')
    if isinstance(code, bool) or not isinstance(code, int):
        return None
    return code
