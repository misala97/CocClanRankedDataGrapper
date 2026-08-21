# Radar Plan 3 — Prices and Divergence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every scored ticker a price context, and turn mention z-scores into the divergence metric the product exists for — chatter far above normal while the price has not moved.

**Architecture:** A provider adapter behind which Finnhub sits, a quote table that keeps enough history to detect a frozen tape, a volatility estimate from daily closes, and a bounded transform that combines mention surprise with price movement without letting either term swamp the other.

**Tech Stack:** Python 3.12, SQLAlchemy, MySQL 8 (dev) / MariaDB (prod), `requests`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-20-radar-social-sentiment-design.md` §3.4, §6.4, §6.5, §8.1

**Measured before planning, not assumed.** Finnhub free returns 200 for
`/quote` and `/stock/profile2` but **403 for `/stock/candle`**, and its quote
carries no volume field. No daily closes means no volatility, which means
`price_move_z` is always None and divergence cannot rank at all — so daily
bars come from Twelve Data, whose four-hour delay disqualified it for quotes
and is meaningless for a daily bar.
**Predecessors:** Plans 1, 1b and 2 complete. 228 radar tests green; `mention_z` is being written per source.

## Global Constraints

- **The provider is swappable.** Everything outside `sources/`-style provider modules talks to an adapter. Nothing may import Finnhub-specific names or assume its JSON shape.
- **No live network calls in tests.** Every provider test drives a fake.
- **Prices are `DECIMAL(18,6)`, never float** (spec §5.5.5). Return arithmetic accumulates drift and the history log is the last place that belongs.
- **A missing quote is missing, not zero.** Same rule as every other gap in this project: a ticker with no usable quote gets no divergence, not a divergence of zero.
- **No spike log yet.** The `radar_spike` table, forward returns and the did-it-work aggregates are Plan 4.
- All datetimes UTC, `DATETIME(6)`.
- The radar suite must keep passing under `-W error::DeprecationWarning`.
- Working directory for every command: `C:\Users\michi\Desktop\CodingStuff\personal_apps`.

## Deviations from the spec, and why

**§6.5 calls the frozen-tape mark HALT. This plan calls it NO PRINT.** The data cannot distinguish a trading halt from a stock so illiquid nobody traded it that interval. Both are untradeable and both fake the divergence, so one mark is right — but calling an empty tape a halt is a claim the data does not support.

**§8.1's segments need market cap, which Finnhub's profile provides.** No deviation, but noting the dependency: the segment tabs cannot exist before this plan.

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `features/radar/prices/__init__.py` | `Quote`, `Profile` dataclasses and the adapter contract |
| `features/radar/prices/finnhub.py` | Quotes and profiles |
| `features/radar/prices/twelvedata.py` | Daily closes, for volatility |
| `features/radar/quotes.py` | Quote storage, no-print detection, volatility |
| `features/radar/divergence.py` | Price-move normalization and the divergence metric |
| `tests/test_radar_prices.py`, `tests/test_radar_quotes.py`, `tests/test_radar_divergence.py` | |

**Modify:** `models.py`, `features/radar/config.py`, `features/radar/universe.py`, `run_radar_ingest.py`

---

## Task 1: Quote and profile storage

**Files:**
- Modify: `personal_apps/models.py`
- Create: migration
- Test: `personal_apps/tests/test_radar_quotes.py`

**Interfaces:**
- Produces: `RadarQuote`; `TickerUniverse` gains `market_cap`, `ipo_date`, `next_earnings_date`, `profile_refreshed_at`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_quotes.py
"""Quote storage.

Snapshots rather than a single current price: no-print detection compares
consecutive polls, so the previous one has to still be there to compare
against.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from models import RadarQuote, TickerUniverse

NOW = dt.datetime(2026, 8, 21, 14, 0, 0)


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        RadarQuote.query.filter(RadarQuote.ticker.like('QQ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarQuote.query.filter(RadarQuote.ticker.like('QQ%')).delete(
            synchronize_session=False)
        db.session.commit()


def add(when, price, volume=1000, ticker='QQA', quote_ts=None):
    db.session.add(RadarQuote(
        ticker=ticker, fetched_at=when,
        quote_ts=quote_ts or when, price=decimal.Decimal(str(price)),
        prev_close=decimal.Decimal('100.000000'), volume=volume))


def test_a_quote_round_trips_exactly(ctx):
    """DECIMAL, not float. Return arithmetic compounds, and the history log is
    the last place drift belongs."""
    add(NOW, '123.456789')
    db.session.commit()
    stored = RadarQuote.query.filter_by(ticker='QQA').one()
    assert stored.price == decimal.Decimal('123.456789')


def test_consecutive_snapshots_are_both_kept(ctx):
    """No-print detection compares one poll against the last, so the last one
    has to still exist."""
    add(NOW, '100.0')
    add(NOW + dt.timedelta(minutes=2), '101.0')
    db.session.commit()
    assert RadarQuote.query.filter_by(ticker='QQA').count() == 2


def test_the_same_instant_twice_is_rejected(ctx):
    add(NOW, '100.0')
    db.session.commit()
    add(NOW, '999.0')
    import sqlalchemy as sa
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_universe_carries_the_profile_fields(ctx):
    """Segments need market cap; the earnings slice needs the date. Both come
    from the same profile call, refreshed weekly."""
    for field in ('market_cap', 'ipo_date', 'next_earnings_date',
                  'profile_refreshed_at'):
        assert hasattr(TickerUniverse, field)


def test_market_cap_holds_a_large_number(ctx):
    """Mega caps are into the trillions; an INTEGER column would overflow."""
    row = TickerUniverse(symbol='QQBIG', name='Huge Corp', exchange='NASDAQ',
                         first_seen=NOW,
                         market_cap=decimal.Decimal('3500000000000'))
    db.session.add(row)
    db.session.commit()
    db.session.expire(row)
    assert row.market_cap == decimal.Decimal('3500000000000')
    db.session.delete(row)
    db.session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_quotes.py -v`
Expected: FAIL with `ImportError: cannot import name 'RadarQuote' from 'models'`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/models.py`:

```python
class RadarQuote(db.Model):
    """One price snapshot for one ticker.

    Snapshots rather than a single current price, because no-print detection
    compares consecutive polls: a frozen tape is one where quote_ts and volume
    are both unchanged since last time, and that comparison needs last time to
    still be here.

    DECIMAL rather than float throughout (spec 5.5.5). Forward returns compound
    these, and drift in a history log is the one place it cannot be tolerated.
    """
    __tablename__ = 'radar_quotes'
    __table_args__ = (
        db.UniqueConstraint('ticker', 'fetched_at', name='uq_radar_quote'),
        db.Index('ix_radar_quotes_ticker_fetched', 'ticker', 'fetched_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    id          = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ticker      = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    fetched_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)

    # The exchange's timestamp for the print, not ours. A tape that has not
    # moved reuses the same one, which is what makes it detectable.
    quote_ts    = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    price       = db.Column(db.Numeric(18, 6), nullable=False)
    prev_close  = db.Column(db.Numeric(18, 6), nullable=True)
    volume      = db.Column(db.BigInteger, nullable=True)
```

Add to `TickerUniverse`:

```python
    # From the provider's profile call, refreshed weekly. Market cap drives the
    # segment tabs; the earnings date drives the proximity slice, since a large
    # share of mention spikes are simply scheduled.
    market_cap           = db.Column(db.Numeric(20, 2), nullable=True)
    ipo_date             = db.Column(db.Date, nullable=True)
    next_earnings_date   = db.Column(db.Date, nullable=True)
    profile_refreshed_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
```

Generate the migration, review it, delete anything emitted against unrelated tables, then apply:

```bash
python -m flask --app app db migrate -m "add radar quotes and profile fields"
python -m flask --app app db upgrade
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_quotes.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/ personal_apps/tests/test_radar_quotes.py
git commit -m "feat(radar): store price snapshots, not just the latest price"
```

---

## Task 2: The provider adapter and its Finnhub implementation

**Files:**
- Create: `personal_apps/features/radar/prices/__init__.py`, `personal_apps/features/radar/prices/finnhub.py`
- Test: `personal_apps/tests/test_radar_prices.py`

**Interfaces:**
- Produces:
  - `Quote` — `ticker`, `price`, `prev_close`, `quote_ts`, `volume`
  - `Profile` — `ticker`, `market_cap`, `ipo_date`, `exchange`
  - `PriceUnavailable`
  - `finnhub.FinnhubProvider` — `.quotes(symbols) -> dict[str, Quote]`, `.profile(symbol) -> Profile | None`
  - `twelvedata.TwelveDataProvider` — `.daily_closes(symbol, days) -> list[tuple[date, Decimal]]`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_prices.py
"""The provider adapter.

One module knows Finnhub's JSON. Everything else sees Quote and Profile, so
swapping providers is one file -- which matters, because free market data
tiers change terms often and this project has already lost one data source
mid-build.
"""
import datetime as dt
import decimal

import pytest

from features.radar.prices import Profile, PriceUnavailable, Quote
from features.radar.prices import finnhub, twelvedata


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, dict(params)))
        if path not in self.payloads:
            raise PriceUnavailable('404 %s' % path)
        return self.payloads[path]


def test_a_quote_is_normalized():
    http = FakeHttp({'/quote': {'c': 123.45, 'pc': 120.0, 'v': 900000,
                                't': 1786000000}})
    quotes = finnhub.FinnhubProvider(http).quotes(['AAA'])
    quote = quotes['AAA']
    assert isinstance(quote, Quote)
    assert quote.price == decimal.Decimal('123.45')
    assert quote.prev_close == decimal.Decimal('120.0')
    assert quote.volume == 900000
    assert quote.quote_ts == dt.datetime.utcfromtimestamp(1786000000).replace(
        microsecond=0)


def test_prices_arrive_as_decimal_not_float():
    """Float here would quietly poison every forward return downstream."""
    http = FakeHttp({'/quote': {'c': 0.1, 'pc': 0.2, 'v': 1, 't': 1786000000}})
    quote = finnhub.FinnhubProvider(http).quotes(['AAA'])['AAA']
    assert isinstance(quote.price, decimal.Decimal)


def test_a_zero_price_is_not_a_quote():
    """Finnhub returns c=0 for an unknown symbol rather than an error. Storing
    that as a price would read as a 100% crash."""
    http = FakeHttp({'/quote': {'c': 0, 'pc': 0, 'v': 0, 't': 0}})
    assert finnhub.FinnhubProvider(http).quotes(['AAA']) == {}


def test_one_bad_symbol_does_not_lose_the_others():
    class Partial(FakeHttp):
        def get(self, path, params):
            if params.get('symbol') == 'BAD':
                raise PriceUnavailable('500')
            return {'c': 10.0, 'pc': 9.0, 'v': 5, 't': 1786000000}

    quotes = finnhub.FinnhubProvider(Partial({})).quotes(['AAA', 'BAD', 'BBB'])
    assert set(quotes) == {'AAA', 'BBB'}


def test_a_profile_is_normalized():
    http = FakeHttp({'/stock/profile2': {
        'marketCapitalization': 3500.5, 'ipo': '2004-08-19', 'exchange': 'NASDAQ'}})
    profile = finnhub.FinnhubProvider(http).profile('AAA')
    assert isinstance(profile, Profile)
    # Finnhub reports market cap in MILLIONS. Storing it raw would put every
    # mega cap in the micro segment.
    assert profile.market_cap == decimal.Decimal('3500500000')
    assert profile.ipo_date == dt.date(2004, 8, 19)


def test_a_profile_without_a_market_cap_is_still_returned():
    """Newly listed and OTC names often have no cap. They belong in the Unknown
    segment, which is a first-class tab, not a discard pile."""
    http = FakeHttp({'/stock/profile2': {'exchange': 'OTC'}})
    profile = finnhub.FinnhubProvider(http).profile('AAA')
    assert profile is not None
    assert profile.market_cap is None


def test_an_empty_profile_is_none():
    http = FakeHttp({'/stock/profile2': {}})
    assert finnhub.FinnhubProvider(http).profile('AAA') is None


def test_daily_closes_come_back_oldest_first():
    """From Twelve Data, not Finnhub: /stock/candle is 403 on Finnhub free,
    measured. Volatility is the whole reason daily closes exist here, and
    without it divergence cannot rank anything."""
    http = FakeHttp({'/time_series': {
        'status': 'ok',
        'values': [
            {'datetime': '2026-08-20', 'close': '12.0'},
            {'datetime': '2026-08-19', 'close': '11.0'},
            {'datetime': '2026-08-18', 'close': '10.0'},
        ]}})
    closes = twelvedata.TwelveDataProvider(http).daily_closes('AAA', days=3)
    # Twelve Data returns newest first; volatility wants chronological order.
    assert [c for _, c in closes] == [decimal.Decimal('10.0'),
                                      decimal.Decimal('11.0'),
                                      decimal.Decimal('12.0')]
    assert closes[0][0] < closes[-1][0]


def test_an_error_status_is_empty_not_an_exception():
    """Twelve Data reports an unknown symbol as status='error' with a 200."""
    http = FakeHttp({'/time_series': {'status': 'error',
                                      'message': 'symbol not found'}})
    assert twelvedata.TwelveDataProvider(http).daily_closes('AAA', days=30) == []


def test_a_rate_limited_response_is_empty_not_a_crash():
    """800 requests a day is ample for weekly volatility, but a burst can
    still trip it, and one tripped call must not take down the job."""
    http = FakeHttp({'/time_series': {'status': 'error', 'code': 429}})
    assert twelvedata.TwelveDataProvider(http).daily_closes('AAA', days=30) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_prices.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'features.radar.prices'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/prices/__init__.py
"""What the rest of the radar sees of a market data provider.

One module knows a provider's JSON; everything else sees these two shapes.
That boundary is not decoration -- free market data terms change often, and
this project already lost Reddit mid-build to exactly that kind of change.
"""
import dataclasses
import datetime as dt
import decimal


class PriceUnavailable(Exception):
    """This request did not arrive. Never becomes a zero price."""


@dataclasses.dataclass
class Quote:
    ticker: str
    price: decimal.Decimal
    prev_close: decimal.Decimal | None
    quote_ts: dt.datetime | None
    volume: int | None


@dataclasses.dataclass
class Profile:
    ticker: str
    market_cap: decimal.Decimal | None
    ipo_date: dt.date | None
    exchange: str | None
```

```python
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

```

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_prices.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/prices/ personal_apps/tests/test_radar_prices.py
git commit -m "feat(radar): put a swappable adapter in front of the price provider"
```

---

## Task 3: No-print detection and volatility

**Files:**
- Create: `personal_apps/features/radar/quotes.py`
- Modify: `personal_apps/features/radar/config.py`, `personal_apps/tests/test_radar_quotes.py`

**Interfaces:**
- Produces:
  - `record_quotes(quotes, now) -> int`
  - `price_status(ticker, now) -> str` — `'ok'` | `'stale'` | `'unknown'`
  - `daily_sigma(closes) -> float | None`
  - `move_since(ticker, hours, now) -> Decimal | None`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_quotes.py`:

```python
from features.radar import quotes as quotes_mod


def test_a_moving_tape_is_ok(ctx):
    add(NOW, '100.0', volume=1000, quote_ts=NOW)
    add(NOW + dt.timedelta(minutes=2), '101.0', volume=1200,
        quote_ts=NOW + dt.timedelta(minutes=2))
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=3)) == 'ok'


def test_an_unchanged_tape_is_stale(ctx):
    """A halted stock keeps its last price while mentions explode BECAUSE it
    halted -- maximum divergence produced entirely by an artifact. The same
    signature comes from a stock too illiquid to trade, which is why the mark
    says NO PRINT rather than HALT: the data cannot tell them apart, and both
    are untradeable."""
    frozen = NOW - dt.timedelta(minutes=5)
    for step in range(3):
        add(NOW + dt.timedelta(minutes=2 * step), '100.0', volume=5000,
            quote_ts=frozen)
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=5)) == 'stale'


def test_one_unchanged_poll_is_not_yet_stale(ctx):
    """Two identical polls could be one slow second. Three is a pattern."""
    frozen = NOW - dt.timedelta(minutes=5)
    add(NOW, '100.0', volume=5000, quote_ts=frozen)
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=1)) != 'stale'


def test_volume_moving_while_the_stamp_sticks_is_still_ok(ctx):
    """Both have to be frozen. A stale timestamp with rising volume is a
    provider quirk, not a stopped tape."""
    frozen = NOW - dt.timedelta(minutes=5)
    for step in range(3):
        add(NOW + dt.timedelta(minutes=2 * step), '100.0',
            volume=5000 + step, quote_ts=frozen)
    db.session.commit()
    assert quotes_mod.price_status('QQA', NOW + dt.timedelta(minutes=5)) == 'ok'


def test_no_quotes_at_all_is_unknown_not_stale(ctx):
    """Never quoted is a different fact from quoted and frozen, and only one
    of them is evidence about the stock."""
    assert quotes_mod.price_status('QQNONE', NOW) == 'unknown'


def test_daily_sigma_of_a_flat_series_is_zero(ctx):
    closes = [(dt.date(2026, 7, day), decimal.Decimal('100')) for day in range(1, 20)]
    assert quotes_mod.daily_sigma(closes) == pytest.approx(0.0)


def test_daily_sigma_grows_with_volatility(ctx):
    calm = [(dt.date(2026, 7, d), decimal.Decimal(100 + (d % 2)))
            for d in range(1, 25)]
    wild = [(dt.date(2026, 7, d), decimal.Decimal(100 + 20 * (d % 2)))
            for d in range(1, 25)]
    assert quotes_mod.daily_sigma(wild) > quotes_mod.daily_sigma(calm) * 5


def test_daily_sigma_needs_enough_history(ctx):
    assert quotes_mod.daily_sigma([]) is None
    assert quotes_mod.daily_sigma(
        [(dt.date(2026, 7, 1), decimal.Decimal('100'))]) is None


def test_move_since_measures_against_the_oldest_quote_in_the_window(ctx):
    add(NOW - dt.timedelta(hours=2), '100.0')
    add(NOW - dt.timedelta(minutes=30), '104.0')
    add(NOW, '110.0')
    db.session.commit()
    move = quotes_mod.move_since('QQA', hours=1, now=NOW + dt.timedelta(minutes=1))
    # From 104 to 110 is roughly +5.8%; the two-hour-old quote is out of window.
    assert 0.05 < float(move) < 0.065


def test_move_since_is_none_without_two_quotes(ctx):
    add(NOW, '100.0')
    db.session.commit()
    assert quotes_mod.move_since('QQA', hours=1, now=NOW) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_quotes.py -v`
Expected: FAIL with `ImportError: cannot import name 'quotes'`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/features/radar/config.py`:

```python
# Consecutive polls with an identical (quote_ts, volume) pair before a tape
# counts as frozen. Two could be one slow second; three is a pattern.
STALE_QUOTE_POLLS = 3

# Daily closes needed before a volatility estimate means anything.
MIN_CLOSES_FOR_SIGMA = 10

# Trading hours in a session, for scaling a daily sigma to a shorter window.
SESSION_HOURS = 6.5
```

```python
# personal_apps/features/radar/quotes.py
"""Price snapshots, frozen-tape detection, and volatility.

The frozen-tape check is the reason quotes are stored as snapshots rather than
as one current price. A halted stock keeps its last print while mentions
explode BECAUSE it halted -- which is maximum divergence produced entirely by
an artifact, and halts cluster on exactly the micro caps that dominate this
board.

The same signature comes from a stock too illiquid for anyone to have traded
it. The data cannot separate the two, so the mark is NO PRINT rather than HALT
(a deliberate wording change from spec 6.5): both are untradeable, and calling
an empty tape a halt claims more than the data supports.
"""
import datetime as dt
import decimal
import statistics

from extensions import db
from models import RadarQuote

from .config import MIN_CLOSES_FOR_SIGMA, SESSION_HOURS, STALE_QUOTE_POLLS


def record_quotes(quotes, now):
    """Store a snapshot per quote. Returns how many were written."""
    written = 0
    for quote in quotes.values():
        db.session.add(RadarQuote(
            ticker=quote.ticker, fetched_at=now, quote_ts=quote.quote_ts,
            price=quote.price, prev_close=quote.prev_close,
            volume=quote.volume))
        written += 1
    db.session.commit()
    return written


def price_status(ticker, now, polls=STALE_QUOTE_POLLS):
    """'ok', 'stale', or 'unknown'.

    'unknown' is deliberately distinct from 'stale'. Never quoted is a
    different fact from quoted-and-frozen, and only the second is evidence
    about the stock.
    """
    recent = (RadarQuote.query
              .filter(RadarQuote.ticker == ticker,
                      RadarQuote.fetched_at <= now)
              .order_by(RadarQuote.fetched_at.desc())
              .limit(polls).all())

    if not recent:
        return 'unknown'
    if len(recent) < polls:
        return 'ok'

    signatures = {(row.quote_ts, row.volume) for row in recent}
    # Both frozen, not just one: a stale timestamp with rising volume is a
    # provider quirk rather than a stopped tape.
    return 'stale' if len(signatures) == 1 else 'ok'


def daily_sigma(closes):
    """Standard deviation of daily returns, or None if history is too thin."""
    if len(closes) < MIN_CLOSES_FOR_SIGMA:
        return None

    returns = []
    for (_, earlier), (_, later) in zip(closes, closes[1:]):
        if earlier and earlier != 0:
            returns.append(float(later / earlier) - 1.0)

    if len(returns) < 2:
        return None
    return statistics.pstdev(returns)


def move_since(ticker, hours, now):
    """Fractional price change across the window, or None.

    Measured between the oldest and newest snapshots inside the window, so it
    answers the question divergence asks -- has the price moved while this was
    being discussed -- rather than comparing against a stale reference point
    outside it.
    """
    since = now - dt.timedelta(hours=hours)
    rows = (RadarQuote.query
            .filter(RadarQuote.ticker == ticker,
                    RadarQuote.fetched_at >= since,
                    RadarQuote.fetched_at <= now)
            .order_by(RadarQuote.fetched_at.asc()).all())

    if len(rows) < 2:
        return None

    first, last = rows[0].price, rows[-1].price
    if not first:
        return None
    return (last - first) / first


def scale_sigma(sigma, hours):
    """A daily sigma scaled to a shorter window, by the square root of time."""
    if sigma is None:
        return None
    return sigma * ((hours / SESSION_HOURS) ** 0.5)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_quotes.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/quotes.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_quotes.py
git commit -m "feat(radar): notice when a tape has stopped printing"
```

---

## Task 4: Divergence

**Files:**
- Create: `personal_apps/features/radar/divergence.py`
- Modify: `personal_apps/features/radar/config.py`
- Test: `personal_apps/tests/test_radar_divergence.py`

**Interfaces:**
- Produces:
  - `price_move_z(move, sigma) -> float | None`
  - `divergence(mention_z, price_move_z) -> float`
  - `direction(move) -> str` — `'up'` | `'flat'` | `'down'`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_divergence.py
"""The metric the product exists for.

Chatter far above normal while the price has not moved. Two corrections to the
naive mention_z minus price_move_z are what make it work at all -- see the
docstrings on each test.
"""
import pytest

from features.radar import divergence as div


def test_loud_and_unmoved_beats_loud_and_already_up():
    """The whole product in one assertion."""
    unmoved = div.divergence(mention_z=8.0, price_move_z=0.1)
    already_ran = div.divergence(mention_z=8.0, price_move_z=4.0)
    assert unmoved > already_ran


def test_the_mention_term_cannot_swamp_the_price_term():
    """Mention counts are heavy-tailed and reach z in the teens; volatility-
    normalized price moves rarely pass 4 sigma. Subtracting them raw makes
    divergence a slightly-adjusted mention_z, and the price side stops
    mattering."""
    huge = div.divergence(mention_z=40.0, price_move_z=4.0)
    modest = div.divergence(mention_z=6.0, price_move_z=0.0)
    assert modest > huge


def test_a_falling_price_does_not_score_as_unmoved():
    """With a signed term, a stock down four sigma scores HIGHER than a flat
    one, and the top of the board fills with things already dumping. "The
    price has not reflected it yet" is a claim about magnitude."""
    dumping = div.divergence(mention_z=8.0, price_move_z=-4.0)
    flat = div.divergence(mention_z=8.0, price_move_z=0.0)
    assert dumping < flat


def test_a_rising_and_falling_move_are_penalised_equally():
    assert div.divergence(8.0, 3.0) == pytest.approx(div.divergence(8.0, -3.0))


def test_divergence_is_bounded():
    assert -1.0 <= div.divergence(1000.0, 0.0) <= 1.0
    assert -1.0 <= div.divergence(0.0, 1000.0) <= 1.0


def test_quiet_and_moving_scores_low():
    """A price move nobody is discussing is not this tool's job."""
    assert div.divergence(mention_z=0.0, price_move_z=4.0) < 0


def test_price_move_z_normalizes_by_volatility():
    """Five percent on a penny stock is noise; five percent on a mega cap is an
    event. Ranking on raw percent would mark every small cap as already moved
    and hide real large-cap divergence."""
    calm = div.price_move_z(move=0.05, sigma=0.01)
    wild = div.price_move_z(move=0.05, sigma=0.20)
    assert calm > wild
    assert calm > 4


def test_price_move_z_is_none_without_a_sigma():
    """No volatility estimate means no opinion, which is different from an
    opinion of zero."""
    assert div.price_move_z(move=0.05, sigma=None) is None


def test_a_zero_sigma_does_not_divide_by_zero():
    assert div.price_move_z(move=0.05, sigma=0.0) is not None


def test_direction_reports_the_sign_separately():
    """Kept as its own column so loud-and-dumping is visible at a glance
    instead of inferred from a magnitude."""
    assert div.direction(0.05) == 'up'
    assert div.direction(-0.05) == 'down'
    assert div.direction(0.0001) == 'flat'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_divergence.py -v`
Expected: FAIL with `ImportError: cannot import name 'divergence'`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/features/radar/config.py`:

```python
# Bounded-transform scales for divergence (spec 6.4). K_M is larger because
# mention z-scores run far hotter than price ones -- the whole point of the
# transform is that neither term can swamp the other.
DIVERGENCE_K_MENTION = 4.0
DIVERGENCE_K_PRICE = 2.0

# Below this fractional move, a price counts as flat for the direction mark.
FLAT_MOVE = 0.005

# Floor under volatility, so a never-moving stock cannot divide to infinity.
MIN_SIGMA = 0.001
```

```python
# personal_apps/features/radar/divergence.py
"""Chatter far above normal, against a price that has not moved.

Two corrections to the naive `mention_z - price_move_z`, both of which the
first draft got wrong:

Mention counts are heavy-tailed and reach z-scores in the teens, while
volatility-normalized price moves rarely pass 4 sigma. Subtracting them raw
leaves divergence as a slightly-adjusted mention_z, with the price side barely
able to influence the ranking at all. Both terms go through a bounded
transform first.

And price enters as MAGNITUDE. With a signed term a stock down four sigma
scores higher than a flat one, so the top of the board fills with things
already collapsing -- while "the price has not reflected it yet" is plainly a
claim about magnitude. The sign is kept, as its own column, so loud-and-dumping
is visible rather than inferred.
"""
import math

from .config import (DIVERGENCE_K_MENTION, DIVERGENCE_K_PRICE, FLAT_MOVE,
                     MIN_SIGMA)


def price_move_z(move, sigma):
    """How many sigma this move is, or None when volatility is unknown.

    None rather than zero: no volatility estimate means no opinion about
    whether the move was large, which is a different thing from an opinion
    that it was not.
    """
    if move is None or sigma is None:
        return None
    return float(move) / max(sigma, MIN_SIGMA)


def divergence(mention_z, price_move_z):
    """Bounded in (-1, 1). Higher means louder relative to how far it moved."""
    mention = math.tanh(mention_z / DIVERGENCE_K_MENTION)
    price = math.tanh(abs(price_move_z) / DIVERGENCE_K_PRICE)
    return mention - price


def direction(move):
    """'up', 'down' or 'flat' -- the sign divergence deliberately discards."""
    if move is None:
        return 'flat'
    if float(move) > FLAT_MOVE:
        return 'up'
    if float(move) < -FLAT_MOVE:
        return 'down'
    return 'flat'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_divergence.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/divergence.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_divergence.py
git commit -m "feat(radar): rank on chatter the price has not caught up with"
```

---

## Task 5: Segments from market cap

**Files:**
- Modify: `personal_apps/features/radar/universe.py`, `personal_apps/features/radar/config.py`
- Modify: `personal_apps/tests/test_radar_universe.py`

**Interfaces:**
- Produces: `segment_for(market_cap, ipo_date, last_price, today) -> str`; `refresh_profiles(provider, symbols, now) -> int`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_universe.py`:

```python
import decimal


def test_segments_split_on_market_cap():
    big = decimal.Decimal('50000000000')
    mid = decimal.Decimal('2000000000')
    small = decimal.Decimal('100000000')
    today = dt.date(2026, 8, 21)
    assert universe.segment_for(big, None, None, today) == 'large'
    assert universe.segment_for(mid, None, None, today) == 'mid'
    assert universe.segment_for(small, None, None, today) == 'micro'


def test_a_cheap_share_price_is_micro_whatever_the_cap():
    """Penny stocks behave like micro caps regardless of what the cap says,
    and a stale or wrong cap should not put one in Large."""
    assert universe.segment_for(decimal.Decimal('20000000000'), None,
                                decimal.Decimal('3.00'),
                                dt.date(2026, 8, 21)) == 'micro'


def test_a_recent_listing_is_its_own_segment():
    """Recent IPOs have no baseline worth the name, which is a property of the
    data rather than of the company's size."""
    assert universe.segment_for(decimal.Decimal('5000000000'),
                                dt.date(2026, 3, 1), None,
                                dt.date(2026, 8, 21)) == 'recent_ipo'


def test_an_old_listing_is_not_recent():
    assert universe.segment_for(decimal.Decimal('5000000000'),
                                dt.date(2010, 3, 1), None,
                                dt.date(2026, 8, 21)) == 'mid'


def test_no_market_cap_is_unknown_not_micro():
    """Unknown is a first-class tab, and the most interesting one. Defaulting
    it to micro would bury exactly the names worth surfacing among genuinely
    tiny companies."""
    assert universe.segment_for(None, None, None, dt.date(2026, 8, 21)) == 'unknown'


def test_refresh_profiles_stores_what_the_provider_returns(clean_universe):
    from features.radar.prices import Profile

    class FakeProvider:
        def profile(self, symbol):
            return Profile(ticker=symbol,
                           market_cap=decimal.Decimal('7500000000'),
                           ipo_date=dt.date(2015, 5, 5), exchange='NASDAQ')

    universe.upsert_symbols(
        [{'symbol': 'ZZP', 'name': 'Profile Corp', 'exchange': 'NASDAQ'}], NOW)
    assert universe.refresh_profiles(FakeProvider(), ['ZZP'], NOW) == 1

    row = TickerUniverse.query.filter_by(symbol='ZZP').one()
    assert row.market_cap == decimal.Decimal('7500000000')
    assert row.ipo_date == dt.date(2015, 5, 5)
    assert row.profile_refreshed_at == NOW


def test_a_provider_returning_nothing_leaves_the_row_alone(clean_universe):
    """A failed lookup must not erase a cap we already had -- that would move
    the ticker into Unknown until the next refresh."""
    class Empty:
        def profile(self, symbol):
            return None

    universe.upsert_symbols(
        [{'symbol': 'ZZQ', 'name': 'Quiet Corp', 'exchange': 'NYSE'}], NOW)
    TickerUniverse.query.filter_by(symbol='ZZQ').update(
        {'market_cap': decimal.Decimal('1000000000')})
    db.session.commit()

    universe.refresh_profiles(Empty(), ['ZZQ'], NOW)
    assert TickerUniverse.query.filter_by(symbol='ZZQ').one().market_cap == \
        decimal.Decimal('1000000000')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_universe.py -v`
Expected: FAIL — `universe` has no attribute `segment_for`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/features/radar/config.py`:

```python
# Segment boundaries (spec 8.1), in dollars.
LARGE_CAP_FLOOR = 10_000_000_000
MID_CAP_FLOOR = 300_000_000

# A share price below this is treated as micro regardless of reported cap.
PENNY_PRICE = 5.00

# A listing younger than this has no baseline worth the name.
RECENT_IPO_DAYS = 365
```

Add to `personal_apps/features/radar/universe.py`:

```python
import datetime as dt

from .config import (LARGE_CAP_FLOOR, MID_CAP_FLOOR, PENNY_PRICE,
                     RECENT_IPO_DAYS)


def segment_for(market_cap, ipo_date, last_price, today):
    """Which segment tab a ticker belongs to.

    Order matters. A recent listing is its own segment whatever its size,
    because the distinguishing fact is that it has no history rather than that
    it is small. And a penny price overrides the reported cap, since a stale or
    wrong cap should not put a three-dollar stock in Large.
    """
    if ipo_date is not None and (today - ipo_date).days <= RECENT_IPO_DAYS:
        return 'recent_ipo'

    if last_price is not None and float(last_price) < PENNY_PRICE:
        return 'micro'

    # Unknown rather than micro. It is a first-class tab and frequently the
    # most interesting one; defaulting to micro would bury the names worth
    # surfacing among genuinely tiny companies.
    if market_cap is None:
        return 'unknown'

    if market_cap >= LARGE_CAP_FLOOR:
        return 'large'
    if market_cap >= MID_CAP_FLOOR:
        return 'mid'
    return 'micro'


def refresh_profiles(provider, symbols, now):
    """Pull profiles and store what came back. Returns how many were updated.

    A provider returning nothing leaves the existing row untouched: erasing a
    cap we already had would move the ticker into Unknown until the next
    refresh, which is worse than a slightly stale number.
    """
    updated = 0
    for symbol in symbols:
        profile = provider.profile(symbol)
        if profile is None:
            continue

        row = TickerUniverse.query.filter_by(symbol=symbol).one_or_none()
        if row is None:
            continue

        if profile.market_cap is not None:
            row.market_cap = profile.market_cap
        if profile.ipo_date is not None:
            row.ipo_date = profile.ipo_date
        row.profile_refreshed_at = now
        updated += 1

    db.session.commit()
    return updated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_universe.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/universe.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_universe.py
git commit -m "feat(radar): sort tickers into segments, and keep Unknown first-class"
```

---

## Task 6: The quote-polling job

**Files:**
- Modify: `personal_apps/run_radar_ingest.py`, `personal_apps/tests/test_radar_daemon.py`

**Interfaces:**
- Produces: `poll_quotes(now, provider, limit=50) -> dict`; `refresh_profiles_job(now, provider) -> int`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_daemon.py`:

```python
def test_quote_polling_targets_the_loudest_tickers(monkeypatch):
    """The free tier is 60 calls a minute, so quotes go to the tickers actually
    on the board rather than to all 12,000 in the universe."""
    asked = {}

    class FakeProvider:
        def quotes(self, symbols):
            asked['symbols'] = list(symbols)
            return {}

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon.quotes, 'record_quotes', lambda q, now: 0)
    daemon.poll_quotes(_utc(2026, 8, 21, 14), FakeProvider(), limit=50)
    assert asked['symbols'] == ['AAA', 'BBB']


def test_a_dead_provider_does_not_kill_the_job(monkeypatch):
    class Dead:
        def quotes(self, symbols):
            raise RuntimeError('provider down')

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    result = daemon.poll_quotes(_utc(2026, 8, 21, 14), Dead())
    assert result['stored'] == 0
    assert result['error'] is True


def test_nothing_loud_means_no_provider_call(monkeypatch):
    """An empty board must not burn rate limit on a call with no symbols."""
    called = {'n': 0}

    class Counting:
        def quotes(self, symbols):
            called['n'] += 1
            return {}

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: [])
    daemon.poll_quotes(_utc(2026, 8, 21, 14), Counting())
    assert called['n'] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_daemon.py -v`
Expected: FAIL — `run_radar_ingest` has no attribute `poll_quotes`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/run_radar_ingest.py`:

```python
import sqlalchemy as sa

from features.radar import divergence, quotes
from features.radar.prices import finnhub as finnhub_provider

# Free tier is 60 calls/minute. Quotes go to the tickers actually on the board,
# not to all 12,000 in the universe.
QUOTE_LIMIT = 50
QUOTE_INTERVAL_MINUTES = 5


def _loud_tickers(now, limit):
    """Tickers worth spending a quote on: the loudest recently scored."""
    from models import RadarBucketSource
    since = now.replace(tzinfo=None) - dt.timedelta(hours=4)
    rows = (db.session.query(RadarBucketSource.ticker,
                             sa.func.max(RadarBucketSource.mention_z))
            .filter(RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.mention_z.isnot(None))
            .group_by(RadarBucketSource.ticker)
            .order_by(sa.func.max(RadarBucketSource.mention_z).desc())
            .limit(limit).all())
    return [ticker for ticker, _ in rows]


def poll_quotes(now_utc, provider, limit=QUOTE_LIMIT):
    """Fetch and store quotes for the loudest tickers."""
    now = now_utc.replace(tzinfo=None)
    symbols = _loud_tickers(now_utc, limit)
    if not symbols:
        # No board, no reason to spend rate limit on an empty request.
        return {'requested': 0, 'stored': 0, 'error': False}

    try:
        found = provider.quotes(symbols)
        stored = quotes.record_quotes(found, now)
    except Exception:
        logger.exception('radar quote poll failed')
        return {'requested': len(symbols), 'stored': 0, 'error': True}

    return {'requested': len(symbols), 'stored': stored, 'error': False}


def _scheduled_quotes():
    now = dt.datetime.now(dt.timezone.utc)
    provider = finnhub_provider.FinnhubProvider(finnhub_provider.FinnhubHttp())
    with app.app_context():
        result = poll_quotes(now, provider)
    logger.info('radar quotes requested=%d stored=%d error=%s',
                result['requested'], result['stored'], result['error'])
```

Register it in `main()`:

```python
    scheduler.add_job(_scheduled_quotes, 'interval',
                      minutes=QUOTE_INTERVAL_MINUTES, id='radar_quotes',
                      max_instances=1, coalesce=True)
```

Add `from extensions import db` to the imports if it is not already there.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_daemon.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): spend quotes on the tickers actually on the board"
```

---

## Task 7: Verify against the live provider

**Files:**
- Modify: `.env` (locally, not committed)

This is the only task that needs the network and a key.

- [ ] **Step 1: Add the key**

Create a free account at https://finnhub.io and add to `personal_apps/.env`:

```
FINNHUB_API_KEY=...
TWELVEDATA_API_KEY=...
```

Both are free email signups, no card. The repo-root `.env` is the one
`find_dotenv()` resolves to from `personal_apps/`, so that is where they go.

- [ ] **Step 2: Check what the free tier actually returns**

```bash
cd personal_apps && python -W ignore -c "
import sys; sys.path.insert(0,'.')
from dotenv import load_dotenv; load_dotenv()
from features.radar.prices import finnhub, twelvedata
p = finnhub.FinnhubProvider(finnhub.FinnhubHttp())
q = p.quotes(['AAPL','SPY','GME'])
for s, quote in q.items():
    print('%-5s price=%s prev=%s vol=%s ts=%s' % (s, quote.price, quote.prev_close, quote.volume, quote.quote_ts))
prof = p.profile('AAPL')
print('profile:', prof)
closes = p.daily_closes('AAPL', days=40)
print('daily closes returned:', len(closes))
"
```

**What to check, and what each answer means:**

- **Quotes return prices** — the adapter works.
- **`vol=None`** — Finnhub's `/quote` may omit volume on the free tier. No-print detection needs it: without volume it degrades to comparing `quote_ts` alone, which is weaker but still catches a frozen tape. Report this rather than working around it.
- **`daily closes returned: 0`** — `/stock/candle` has been restricted for US equities on Finnhub's free tier before. Without daily closes there is no volatility estimate, so `price_move_z` is always None and divergence cannot rank. **This is the finding that would matter most**, and the fallback is a different source for daily bars, not a workaround here.
- **`profile:` with a market cap** — segments work.

- [ ] **Step 3: Record what was found**

Whatever the answers are, write them into the spec's §3.4 as measured facts rather than assumptions — the same treatment the social sources got.

---

## Done when

- `python -m pytest tests/test_radar_*.py -q -W error::DeprecationWarning` passes
- A live quote poll stores rows in `radar_quotes`
- Three consecutive identical polls make `price_status` return `stale`
- A ticker with no quote gets no divergence rather than a divergence of zero

## What Plan 4 picks up

The spike state machine, session-relative forward returns, excess over SPY and segment medians, and the did-it-work aggregates (spec §7). Then Plan 5 is the three surfaces.

The `excluded` hook in `scoring.score_source` is still unused — Plan 4 wires open-spike buckets into it so a ticker that squeezed last week stops carrying the squeeze in its own baseline.
