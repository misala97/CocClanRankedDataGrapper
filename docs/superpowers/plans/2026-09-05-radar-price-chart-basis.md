# Radar Price Chart Basis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the radar ticker panel draw a price line on every span, by resolving the chart's price history from the ticker's own listings instead of from whichever venue happened to supply the quote.

**Architecture:** A new `HistoryBasis` value type replaces the Xetra→Tradegate `HistorySeries` seam. `history.resolve_basis()` builds up to three candidate series for a ticker — the quote's own venue, the ISIN-matched sibling venue in the same market, and the primary US listing converted to EUR through a stored ECB daily-rate table — and returns whichever holds the most closes in the requested span. Around that: `_daily_anchors` stops discarding extended-hours and bell-stamped prints, 1D falls back to daily anchors when the quote store is too thin, the Massive grouped-daily source fills the close store market-wide, and the German delayed feed is paced to survive its own download budget.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, Alembic (Flask-Migrate), MySQL 8 locally / MariaDB in production, pytest. Frontend: React 19 + TypeScript + Vite, tested with vitest + @testing-library/react.

## Global Constraints

- **Working directory is `personal_apps/`** for every command in this plan unless stated otherwise. The repo root is `C:\Users\michi\Desktop\CodingStuff`; the Flask project root is `C:\Users\michi\Desktop\CodingStuff\personal_apps`.
- **Branch: `dev_personal`.** Do not commit to `main`. The final task merges.
- **The working tree has unrelated dirty work** (`scripts/discover_telegram_sources.py`, `telegram_candidates.json`, `reddit_candidates.json`, several `scratchpad/` probes, `scripts/measure_*.py`, `tests/test_measure_*.py`). **Never `git add -A`, never `git add .`, never `git commit -a`.** Every commit step in this plan lists explicit paths. Preserve that dirty work untouched.
- **Tests run against the real local development database** (`tests/conftest.py`), not sqlite and not a fixture DB. Tests must create rows under a unique ticker prefix and delete them in a fixture teardown, following `tests/test_radar_history.py`.
- **Python tests:** run from `personal_apps/` with `python -m pytest tests/<file> -v`. There is no `pytest.ini`, `setup.cfg` or `pyproject.toml` — no custom options, no markers.
- **JS tests:** run from `personal_apps/` with `npm test` (which is `vitest run && vitest run -c vite.radar.config.ts`). The radar island's tests only run under the second config.
- **Production DB is MariaDB.** `CAST(... AS JSON)` is a parse error there. Keep migration DDL plain. DDL commits even when a later step of the same migration fails, so each migration does one thing.
- **Current Alembic head is `c8d2e5f7a1b4`** (`migrations/versions/c8d2e5f7a1b4_add_radar_reddit_cursors.py`). The one new migration in this plan sets `down_revision = 'c8d2e5f7a1b4'`.
- **Absence is never zero.** A ticker with no stored closes is absent from a result, never mapped to an empty list or a zero. A converted price that has no FX rate for its date is dropped, never carried at a neighbouring rate beyond the documented carry-forward rule.
- **Commit message style:** `feat(radar): ...` / `fix(radar): ...` / `test(radar): ...`, lowercase subject, no trailing period, and every commit ends with the trailer:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```
- **Spec:** `docs/superpowers/specs/2026-09-04-radar-price-chart-basis-design.md` (repo root, not `personal_apps/`). Read it before Task 1.

---

### Task 1: The FX rate store

**Files:**
- Modify: `models.py` (add `RadarFxRate` after `RadarDailyClose`, which ends around line 985)
- Create: `migrations/versions/d4e7a1b93c25_add_radar_fx_rates.py`
- Create: `features/radar/fx.py`
- Test: `tests/test_radar_fx.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `models.RadarFxRate` with columns `id, rate_date, base, quote, rate, source, fetched_at`
  - `fx.record_rates(rates, now, *, base='EUR', quote='USD', source='ecb', commit=True) -> int` where `rates` is an iterable of `(datetime.date, decimal.Decimal)`
  - `fx.rate_series(start, end, *, base='EUR', quote='USD') -> dict[datetime.date, decimal.Decimal]`
  - `fx.rate_on(series, day) -> decimal.Decimal | None` — carry-forward from the most recent published day at or before `day`; `None` when `day` precedes every published day
  - `fx.convert_usd_to_eur(closes, series) -> tuple[tuple[datetime.date, decimal.Decimal], ...]` — drops any pair whose date has no usable rate

- [ ] **Step 1: Write the failing test**

Create `tests/test_radar_fx.py`:

```python
"""The euro reference rates a converted price line is drawn through.

The ECB publishes on TARGET business days only, so the interesting rules
here are all about the days it does NOT publish: a close on a Saturday is
converted at Friday's rate, and a close older than the whole stored series
is dropped rather than converted at the oldest rate we happen to hold.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import fx
from models import RadarFxRate

NOW = dt.datetime(2026, 9, 5, 18, 0, 0)


@pytest.fixture()
def clean():
    def wipe():
        RadarFxRate.query.filter(RadarFxRate.source == 'test-fx').delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def seed(pairs):
    fx.record_rates(pairs, NOW, source='test-fx')


def test_record_rates_writes_one_row_per_day(clean):
    written = fx.record_rates(
        [(dt.date(2026, 9, 1), decimal.Decimal('1.1600')),
         (dt.date(2026, 9, 2), decimal.Decimal('1.1615'))],
        NOW, source='test-fx')

    assert written == 2
    assert RadarFxRate.query.filter_by(source='test-fx').count() == 2


def test_record_rates_restates_an_existing_day(clean):
    seed([(dt.date(2026, 9, 1), decimal.Decimal('1.1600'))])

    fx.record_rates([(dt.date(2026, 9, 1), decimal.Decimal('1.1700'))],
                    NOW, source='test-fx')

    rows = RadarFxRate.query.filter_by(source='test-fx').all()
    assert len(rows) == 1
    assert rows[0].rate == decimal.Decimal('1.17000000')


def test_rate_series_returns_published_days_only(clean):
    seed([(dt.date(2026, 9, 1), decimal.Decimal('1.1600')),
          (dt.date(2026, 9, 4), decimal.Decimal('1.1615'))])

    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 4))

    assert sorted(series) == [dt.date(2026, 9, 1), dt.date(2026, 9, 4)]


def test_rate_on_carries_the_last_published_rate_forward(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('1.1615'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    # 5 Sept is a Saturday: the ECB published nothing, so Friday stands.
    assert fx.rate_on(series, dt.date(2026, 9, 5)) == decimal.Decimal('1.1615')


def test_rate_on_refuses_a_day_before_the_series(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('1.1615'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    assert fx.rate_on(series, dt.date(2026, 9, 3)) is None


def test_convert_usd_to_eur_divides_by_the_days_rate(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('2.0000'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    converted = fx.convert_usd_to_eur(
        [(dt.date(2026, 9, 4), decimal.Decimal('10.00'))], series)

    assert converted == ((dt.date(2026, 9, 4), decimal.Decimal('5.00')),)


def test_convert_usd_to_eur_drops_a_close_with_no_usable_rate(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('2.0000'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    converted = fx.convert_usd_to_eur(
        [(dt.date(2026, 9, 3), decimal.Decimal('10.00')),
         (dt.date(2026, 9, 4), decimal.Decimal('10.00'))], series)

    assert [day for day, _ in converted] == [dt.date(2026, 9, 4)]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_radar_fx.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'features.radar.fx'` (collection error).

- [ ] **Step 3: Add the model**

In `models.py`, immediately after the `RadarDailyClose` class body ends and before the next class, add:

```python
class RadarFxRate(db.Model):
    """One published FX reference rate per day, per currency pair.

    Here so a US listing's closes can be drawn on a EUR axis without the
    close store ever holding a derived number. Conversion happens at read
    time against these rows; what is stored is only ever what a venue
    printed and what a central bank published.

    The ECB publishes on TARGET business days, so this table has holes by
    construction. A reader carries the last published rate forward across
    them (features/radar/fx.py) rather than interpolating -- a weekend has
    no rate because no rate was set, not because one was missed.
    """
    __tablename__ = 'radar_fx_rates'
    __table_args__ = (
        db.UniqueConstraint('rate_date', 'base', 'quote',
                            name='uq_radar_fx_rate_day'),
        db.Index('ix_radar_fx_rates_pair_day', 'base', 'quote', 'rate_date'),
        {'mysql_charset': 'utf8mb4'},
    )

    id         = db.Column(
        db.BigInteger().with_variant(db.Integer(), 'sqlite'),
        primary_key=True, autoincrement=True)
    rate_date  = db.Column(db.Date, nullable=False)
    base       = db.Column(db.String(3), nullable=False)
    quote      = db.Column(db.String(3), nullable=False)
    # Units of `quote` per one `base`. EUR/USD 1.1615 means one euro buys
    # 1.1615 dollars, which is the direction the ECB publishes in.
    rate       = db.Column(db.Numeric(18, 8), nullable=False)
    source     = db.Column(db.String(16), nullable=False)
    fetched_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
```

- [ ] **Step 4: Write the migration**

Create `migrations/versions/d4e7a1b93c25_add_radar_fx_rates.py`:

```python
"""add radar_fx_rates

One published reference rate per day and currency pair, so a US listing's
closes can be drawn on a euro axis. Plain DDL -- MariaDB in production.

Revision ID: d4e7a1b93c25
Revises: c8d2e5f7a1b4
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'd4e7a1b93c25'
down_revision = 'c8d2e5f7a1b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'radar_fx_rates',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('base', sa.String(length=3), nullable=False),
        sa.Column('quote', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(18, 8), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('fetched_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rate_date', 'base', 'quote',
                            name='uq_radar_fx_rate_day'),
        mysql_charset='utf8mb4')
    op.create_index('ix_radar_fx_rates_pair_day', 'radar_fx_rates',
                    ['base', 'quote', 'rate_date'])


def downgrade():
    op.drop_index('ix_radar_fx_rates_pair_day', table_name='radar_fx_rates')
    op.drop_table('radar_fx_rates')
```

- [ ] **Step 5: Apply the migration**

Run: `python -m flask db upgrade`
Expected: output ending `Running upgrade c8d2e5f7a1b4 -> d4e7a1b93c25, add radar_fx_rates`.

- [ ] **Step 6: Write the module**

Create `features/radar/fx.py`:

```python
# personal_apps/features/radar/fx.py
"""Euro reference rates, and the one conversion the chart is allowed to do.

A ticker listed on Nasdaq and quoted at Tradegate has three years of closes
in dollars and a headline price in euros. Drawing the dollars on a euro axis
would be a lie by omission, and drawing nothing -- which is what the panel
did until 2026-09-05 -- is a lie by silence. So: convert, at read time,
against a rate somebody published on that date, and say so next to the line.

Read time, not write time, on purpose. The close store holds what a venue
printed. A converted number is a derived number and derived numbers do not
belong in it; today's rate would also silently restate every historical row
the next time anything touched them.
"""
import datetime as dt
import decimal

from extensions import db
from models import RadarFxRate

# The only pair the panel needs. Named rather than parameterised everywhere:
# a second pair is a schema question (which venue, which axis) and not a
# matter of passing another string.
BASE = 'EUR'
QUOTE = 'USD'


def record_rates(rates, now, *, base=BASE, quote=QUOTE, source='ecb',
                 commit=True):
    """Upsert (date, rate) pairs. Returns rows written.

    Upsert because the ECB restates: the daily file is provisional for a few
    hours after publication, and the history file is the corrected record.
    """
    rates = list(rates)
    if not rates:
        return 0

    existing = {row.rate_date: row for row in RadarFxRate.query.filter(
        RadarFxRate.base == base, RadarFxRate.quote == quote,
        RadarFxRate.rate_date.in_([day for day, _ in rates])).all()}

    written = 0
    for day, rate in rates:
        row = existing.get(day)
        if row is None:
            db.session.add(RadarFxRate(
                rate_date=day, base=base, quote=quote,
                rate=decimal.Decimal(rate), source=source, fetched_at=now))
        else:
            row.rate = decimal.Decimal(rate)
            row.source = source
            row.fetched_at = now
        written += 1

    if commit:
        db.session.commit()
    return written


def rate_series(start, end, *, base=BASE, quote=QUOTE):
    """{date: rate} for every PUBLISHED day in the window.

    Holes are kept as holes. `rate_on` is what decides what a hole means;
    a series that pre-filled its weekends would have already decided.
    """
    rows = (db.session.query(RadarFxRate.rate_date, RadarFxRate.rate)
            .filter(RadarFxRate.base == base, RadarFxRate.quote == quote,
                    RadarFxRate.rate_date >= start,
                    RadarFxRate.rate_date <= end).all())
    return {day: rate for day, rate in rows}


def rate_on(series, day):
    """The rate in force on `day`: the last one published at or before it.

    None before the series begins. Not the earliest known rate -- a 2019
    close converted at 2024's rate is a fabricated price, and the honest
    answer to "what was this worth in euros" is that we do not know.

    Bounded at seven days of carry-forward. TARGET closes for at most four
    consecutive days (Easter); a longer gap is a broken feed, and drawing
    through it would hide exactly the outage the reader needs to see.
    """
    if not series:
        return None
    for back in range(0, 8):
        rate = series.get(day - dt.timedelta(days=back))
        if rate is not None:
            return rate
    return None


def convert_usd_to_eur(closes, series):
    """(date, usd) pairs -> (date, eur) pairs, dropping what we cannot price.

    The ECB quotes EUR/USD as dollars per euro, so euros are dollars DIVIDED
    by the rate. Quantised to four places, which is what RadarDailyClose.close
    stores and therefore the most precision the input ever carried.
    """
    converted = []
    for day, close in closes:
        rate = rate_on(series, day)
        if rate is None or rate == 0:
            continue
        converted.append(
            (day, (decimal.Decimal(close) / rate).quantize(
                decimal.Decimal('0.0001'), rounding=decimal.ROUND_HALF_UP)))
    return tuple(converted)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_fx.py -v`
Expected: PASS, 7 passed.

- [ ] **Step 8: Commit**

```bash
git add models.py features/radar/fx.py migrations/versions/d4e7a1b93c25_add_radar_fx_rates.py tests/test_radar_fx.py
git commit -m "feat(radar): store published euro reference rates

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The ECB provider and its backfill

**Files:**
- Create: `features/radar/prices/ecb.py`
- Create: `scripts/backfill_radar_fx.py`
- Test: `tests/test_radar_ecb.py`

**Interfaces:**
- Consumes: `fx.record_rates` from Task 1.
- Produces:
  - `ecb.EcbHttp(timeout=(3.05, 30))` with `.get_daily() -> bytes` and `.get_history() -> bytes`
  - `ecb.EcbProvider(http)` with `.source = 'ecb'` and `.rates(historical=False) -> list[tuple[datetime.date, decimal.Decimal]]`, newest first
  - `ecb.parse_rates(raw, quote='USD') -> list[tuple[datetime.date, decimal.Decimal]]`
  - `scripts/backfill_radar_fx.py` runnable as `python scripts/backfill_radar_fx.py`

The transport/provider split follows `features/radar/prices/twelvedata.py`: a thin `*Http` class that can be replaced in tests, and a provider that never touches the network itself.

- [ ] **Step 1: Write the failing test**

Create `tests/test_radar_ecb.py`:

```python
"""The ECB adapter: one parser, and a refusal for everything it cannot read.

The daily file is 1.5 KB and the history file is 8 MB of the same shape, so
there is exactly one parser and the only difference is which URL fetched it.
"""
import datetime as dt
import decimal

import pytest

from features.radar.prices import PriceUnavailable
from features.radar.prices import ecb

DAILY = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time='2026-09-03'>
      <Cube currency='USD' rate='1.1615'/>
      <Cube currency='JPY' rate='171.02'/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""

HIST = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time='2026-09-03'><Cube currency='USD' rate='1.1615'/></Cube>
    <Cube time='2026-09-02'><Cube currency='USD' rate='1.1600'/></Cube>
    <Cube time='2026-09-01'><Cube currency='JPY' rate='171.02'/></Cube>
  </Cube>
</gesmes:Envelope>"""


class FakeHttp:
    def __init__(self, daily=DAILY, history=HIST):
        self._daily = daily
        self._history = history
        self.asked = []

    def get_daily(self):
        self.asked.append('daily')
        return self._daily

    def get_history(self):
        self.asked.append('history')
        return self._history


def test_parses_the_daily_file():
    assert ecb.parse_rates(DAILY) == [
        (dt.date(2026, 9, 3), decimal.Decimal('1.1615'))]


def test_parses_every_day_of_the_history_file():
    assert ecb.parse_rates(HIST) == [
        (dt.date(2026, 9, 3), decimal.Decimal('1.1615')),
        (dt.date(2026, 9, 2), decimal.Decimal('1.1600'))]


def test_a_day_without_the_pair_is_absent_not_zero():
    days = [day for day, _ in ecb.parse_rates(HIST)]
    assert dt.date(2026, 9, 1) not in days


def test_malformed_xml_is_unavailable_not_empty():
    with pytest.raises(PriceUnavailable):
        ecb.parse_rates(b'<not-xml')


def test_provider_reads_the_daily_file_by_default():
    http = FakeHttp()
    rates = ecb.EcbProvider(http).rates()
    assert http.asked == ['daily']
    assert rates == [(dt.date(2026, 9, 3), decimal.Decimal('1.1615'))]


def test_provider_reads_the_history_file_when_asked():
    http = FakeHttp()
    rates = ecb.EcbProvider(http).rates(historical=True)
    assert http.asked == ['history']
    assert len(rates) == 2


def test_provider_source_is_ecb():
    assert ecb.EcbProvider(FakeHttp()).source == 'ecb'
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_radar_ecb.py -v`
Expected: FAIL — `ImportError: cannot import name 'ecb' from 'features.radar.prices'`.

- [ ] **Step 3: Write the provider**

Create `features/radar/prices/ecb.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_ecb.py -v`
Expected: PASS, 7 passed.

- [ ] **Step 5: Write the backfill script**

Create `scripts/backfill_radar_fx.py`:

```python
# personal_apps/scripts/backfill_radar_fx.py
"""Load the ECB's full euro reference-rate history into radar_fx_rates.

One request, about 8 MB, roughly 7000 business days back to 1999. Run once
after the migration; the daily job keeps it current from then on.

    python scripts/backfill_radar_fx.py
"""
import datetime as dt
import sys

sys.path.insert(0, '.')

from app import app                      # noqa: E402
from features.radar import fx            # noqa: E402
from features.radar.prices import ecb    # noqa: E402


def main():
    provider = ecb.EcbProvider(ecb.EcbHttp())
    rates = provider.rates(historical=True)
    if not rates:
        print('ecb returned no rates -- nothing written')
        return 1
    with app.app_context():
        written = fx.record_rates(rates, dt.datetime.utcnow())
    oldest = min(day for day, _ in rates)
    newest = max(day for day, _ in rates)
    print(f'radar fx backfill: {written} rates, {oldest} .. {newest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 6: Run the backfill against the local dev database**

Run: `python scripts/backfill_radar_fx.py`
Expected: a line like `radar fx backfill: 7085 rates, 1999-01-04 .. 2026-09-04`. This is a real network call and a real write to the dev DB, which is disposable.

- [ ] **Step 7: Verify the store answers a real question**

Run:
```bash
python -c "import datetime as dt; from app import app; from features.radar import fx; app.app_context().push(); s=fx.rate_series(dt.date(2026,8,1), dt.date(2026,9,5)); print(len(s), fx.rate_on(s, dt.date(2026,9,5)))"
```
Expected: a count in the mid-twenties and a non-`None` `Decimal` — the Saturday carrying Friday's rate forward.

- [ ] **Step 8: Commit**

```bash
git add features/radar/prices/ecb.py scripts/backfill_radar_fx.py tests/test_radar_ecb.py
git commit -m "feat(radar): read euro reference rates from the ECB

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `HistoryBasis` and `resolve_basis`

**Files:**
- Modify: `features/radar/history.py:171-228` (replace `HistorySeries` and `series_for`)
- Test: `tests/test_radar_history_basis.py`

**Interfaces:**
- Consumes: `fx.rate_series`, `fx.convert_usd_to_eur` (Task 1); `history.closes_for` (existing, unchanged).
- Produces:
  - `history.HistoryBasis` — frozen dataclass with fields `closes: tuple`, `market: str | None`, `mic: str | None`, `venue: str | None`, `currency: str | None`, `converted_from: str | None`
  - `history.EMPTY_BASIS` — the all-`None` basis with `closes=()`
  - `history.MIN_BASIS_CLOSES = 2`
  - `history.resolve_basis(ticker, quote, days, today) -> HistoryBasis` where `quote` is the quote view returned by `quotes.quote_views_for` (it supplies `.market`, `.mic`, `.venue`, `.currency`)

`series_for` and `HistorySeries` are DELETED in this task. Task 4 updates the only caller.

- [ ] **Step 1: Write the failing test**

Create `tests/test_radar_history_basis.py`:

```python
"""Which venue's closes a panel chart is actually drawn from.

The rule being pinned: the venue that QUOTES a ticker and the venue that has
its HISTORY are different questions. A Nasdaq listing quoted at Tradegate has
three years of dollars and two days of euros, and the chart that reads the
quote's venue draws the two days.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import fx, history
from models import RadarDailyClose, RadarFxRate, RadarInstrument

TODAY = dt.date(2026, 9, 4)
NOW = dt.datetime(2026, 9, 4, 20, 0, 0)
PREFIX = 'HB'


class FakeQuote:
    """Only the four fields resolve_basis reads off a quote view."""

    def __init__(self, market, mic, venue, currency):
        self.market = market
        self.mic = mic
        self.venue = venue
        self.currency = currency


DE_QUOTE = FakeQuote('de', 'XGAT', 'Tradegate BSX', 'EUR')
US_QUOTE = FakeQuote('us', 'XNMS', 'Nasdaq Global Market', 'USD')


@pytest.fixture()
def clean():
    def wipe():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        RadarInstrument.query.filter(
            RadarInstrument.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        RadarFxRate.query.filter_by(source='test-basis').delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def close(ticker, days_back, price, *, market, mic, currency):
    db.session.add(RadarDailyClose(
        ticker=ticker, market=market, mic=mic, currency=currency,
        close_date=TODAY - dt.timedelta(days=days_back),
        close=decimal.Decimal(price), fetched_at=NOW))


def instrument(ticker, market, mic, venue, currency, isin, primary=True):
    db.session.add(RadarInstrument(
        ticker=ticker, market=market, mic=mic, venue=venue,
        provider_symbol=ticker, currency=currency, isin=isin,
        is_primary=primary, mapping_status='mapped', mapped_at=NOW))


def parity_rates():
    fx.record_rates(
        [(TODAY - dt.timedelta(days=n), decimal.Decimal('2.0000'))
         for n in range(0, 40)], NOW, source='test-basis')


def test_native_venue_wins_when_it_has_the_depth(clean):
    ticker = f'{PREFIX}NAT'
    for n in range(1, 11):
        close(ticker, n, '10.00', market='de', mic='XGAT', currency='EUR')
    for n in range(1, 4):
        close(ticker, n, '20.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()
    parity_rates()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.mic == 'XGAT'
    assert basis.converted_from is None
    assert len(basis.closes) == 10


def test_isin_matched_sibling_wins_over_a_two_day_native_stub(clean):
    ticker = f'{PREFIX}SIB'
    for n in range(1, 3):
        close(ticker, n, '10.00', market='de', mic='XGAT', currency='EUR')
    for n in range(1, 21):
        close(ticker, n, '11.00', market='de', mic='XETR', currency='EUR')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'DE000TEST001')
    instrument(ticker, 'de', 'XETR', 'Xetra', 'EUR', 'DE000TEST001',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.mic == 'XETR'
    assert basis.venue == 'Xetra'
    assert basis.currency == 'EUR'
    assert basis.converted_from is None


def test_a_sibling_with_a_different_isin_is_not_a_sibling(clean):
    ticker = f'{PREFIX}ISIN'
    for n in range(1, 21):
        close(ticker, n, '11.00', market='de', mic='XETR', currency='EUR')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'DE000TEST002')
    instrument(ticker, 'de', 'XETR', 'Xetra', 'EUR', 'DE000OTHER99',
               primary=False)
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.mic != 'XETR'


def test_converted_us_history_wins_when_germany_has_nothing(clean):
    """RZLV's exact shape: a German quote, no Xetra listing, deep US closes."""
    ticker = f'{PREFIX}RZLV'
    for n in range(1, 21):
        close(ticker, n, '10.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'GB00TEST0001')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()
    parity_rates()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.market == 'us'
    assert basis.mic == 'XNMS'
    assert basis.currency == 'EUR'
    assert basis.converted_from == 'USD'
    # Parity rate of 2.0 -- ten dollars is five euros.
    assert basis.closes[0][1] == decimal.Decimal('5.0000')


def test_conversion_is_skipped_without_stored_rates(clean):
    ticker = f'{PREFIX}NOFX'
    for n in range(1, 21):
        close(ticker, n, '10.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'de', 'XGAT', 'Tradegate BSX', 'EUR', 'GB00TEST0002')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis.closes == ()


def test_a_us_quote_never_converts(clean):
    ticker = f'{PREFIX}USQ'
    for n in range(1, 21):
        close(ticker, n, '10.00', market='us', mic='XNMS', currency='USD')
    instrument(ticker, 'us', 'XNMS', 'Nasdaq Global Market', 'USD', None)
    db.session.commit()
    parity_rates()

    basis = history.resolve_basis(ticker, US_QUOTE, 30, TODAY)

    assert basis.currency == 'USD'
    assert basis.converted_from is None
    assert basis.closes[0][1] == decimal.Decimal('10.0000')


def test_a_single_close_is_not_a_line(clean):
    ticker = f'{PREFIX}ONE'
    close(ticker, 1, '10.00', market='de', mic='XGAT', currency='EUR')
    db.session.commit()

    basis = history.resolve_basis(ticker, DE_QUOTE, 30, TODAY)

    assert basis == history.EMPTY_BASIS


def test_nothing_stored_yields_the_empty_basis(clean):
    basis = history.resolve_basis(f'{PREFIX}VOID', DE_QUOTE, 30, TODAY)
    assert basis == history.EMPTY_BASIS
    assert basis.closes == ()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_radar_history_basis.py -v`
Expected: FAIL — `AttributeError: module 'features.radar.history' has no attribute 'resolve_basis'`.

- [ ] **Step 3: Replace `HistorySeries` and `series_for`**

In `features/radar/history.py`, delete lines 171-228 — the `@dataclasses.dataclass(frozen=True) class HistorySeries` block and the whole of `def series_for(...)` — and put this in their place:

```python
# A line needs two points. One stored close is a dot, and a dot drawn as a
# price line is a claim about a trend that one number cannot support.
MIN_BASIS_CLOSES = 2


@dataclasses.dataclass(frozen=True)
class HistoryBasis:
    """Where one chart's price line actually came from.

    The venue that QUOTES a ticker and the venue that has its HISTORY are
    different questions, and the panel used to answer both with the quote.
    On the German board that made a Nasdaq listing read its two stored
    Tradegate closes instead of its 780 stored Nasdaq ones.

    `currency` is the currency `closes` is expressed in, which the axis and
    the hover read. `converted_from` is set only when these closes were
    priced in another currency and converted here -- the renderer states it
    beside the chart, because a converted line must never read as native.
    """
    closes: tuple
    market: str | None
    mic: str | None
    venue: str | None
    currency: str | None
    converted_from: str | None


EMPTY_BASIS = HistoryBasis(closes=(), market=None, mic=None, venue=None,
                           currency=None, converted_from=None)


def _native_basis(ticker, quote, days, today):
    rows = closes_for([ticker], days=days, today=today,
                      market=quote.market, mic=quote.mic).get(ticker, [])
    return HistoryBasis(closes=tuple(rows), market=quote.market,
                        mic=quote.mic, venue=quote.venue,
                        currency=quote.currency, converted_from=None)


def _sibling_basis(ticker, quote, days, today):
    """The other venue in the same market, when it is provably the same paper.

    Same ISIN, both non-null, same currency. That is the §8.2 test the old
    Xetra proxy used, moved here: it was always a question about which
    series may stand in for which, and never about how to stitch them.
    """
    from models import RadarInstrument
    rows = RadarInstrument.query.filter_by(
        ticker=ticker, market=quote.market).all()
    here = next((r for r in rows if r.mic == quote.mic), None)
    if here is None or here.isin is None:
        return None
    sibling = next((r for r in rows
                    if r.mic != quote.mic and r.isin == here.isin
                    and r.currency == here.currency), None)
    if sibling is None:
        return None
    closes = closes_for([ticker], days=days, today=today,
                        market=sibling.market, mic=sibling.mic).get(ticker, [])
    return HistoryBasis(closes=tuple(closes), market=sibling.market,
                        mic=sibling.mic, venue=sibling.venue,
                        currency=sibling.currency, converted_from=None)


def _converted_basis(ticker, quote, days, today):
    """The primary US listing, in the quote's currency.

    Only EUR is served, because only the German board asks. A pair we cannot
    price returns None rather than an unconverted dollar series: a USD line
    under a EUR axis label is the exact lie this whole basis exists to stop.
    """
    if quote.currency != 'EUR':
        return None

    from models import RadarInstrument
    us = (RadarInstrument.query
          .filter_by(ticker=ticker, market='us', is_primary=True)
          .first())
    if us is None:
        return None

    closes = closes_for([ticker], days=days, today=today,
                        market='us', mic=us.mic).get(ticker, [])
    if not closes:
        return None

    from . import fx
    series = fx.rate_series(min(day for day, _ in closes), today)
    converted = fx.convert_usd_to_eur(closes, series)
    if not converted:
        return None
    return HistoryBasis(closes=converted, market='us', mic=us.mic,
                        venue=us.venue, currency='EUR', converted_from='USD')


def resolve_basis(ticker, quote, days, today):
    """The chartable series for one ticker over `days`, and where it is from.

    Candidates in precedence order -- the quote's own venue, the ISIN-matched
    sibling, the converted US primary -- and the one with the MOST closes in
    the span wins. `max` keeps the first of equal counts, so precedence breaks
    ties. Evaluated per span on purpose: a ticker may have a deep Xetra month
    and a deeper converted three years, and each span should draw the most
    price it can while saying which venue that was.

    Fewer than MIN_BASIS_CLOSES is not a candidate at all. When nothing
    qualifies the caller gets EMPTY_BASIS and the panel says so, which is the
    honest answer and the one the renderer already draws.
    """
    candidates = [_native_basis(ticker, quote, days, today),
                  _sibling_basis(ticker, quote, days, today),
                  _converted_basis(ticker, quote, days, today)]
    usable = [c for c in candidates
              if c is not None and len(c.closes) >= MIN_BASIS_CLOSES]
    if not usable:
        return EMPTY_BASIS
    return max(usable, key=lambda c: len(c.closes))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_history_basis.py -v`
Expected: PASS, 8 passed.

- [ ] **Step 5: Confirm the old suite sees the deletion**

Run: `python -m pytest tests/test_radar_history.py -v`
Expected: FAIL — the seam tests that call `history.series_for` now error with `AttributeError`. Note which test names fail; they are rewritten in Task 4 Step 6. Do not fix them here.

- [ ] **Step 6: Commit**

```bash
git add features/radar/history.py tests/test_radar_history_basis.py
git commit -m "feat(radar): resolve a chart's price history from the listing, not the quote

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Wire the panel to the basis

**Files:**
- Modify: `features/radar/detail.py` — the `Chart` dataclass (fields `history_proxy` through `native_from`, around lines 84-91) and `intraday_chart_for` (around lines 314-365)
- Modify: `features/radar/detail_panel.py:336-357`
- Modify: `tests/test_radar_history.py` — rewrite the seam tests that Task 3 broke
- Test: `tests/test_radar_detail.py` (extend)

**Interfaces:**
- Consumes: `history.resolve_basis`, `history.EMPTY_BASIS` (Task 3).
- Produces: `Chart.currency`, `Chart.basis_venue`, `Chart.converted_from`, `Chart.priced_from` — read by Task 5's serializer.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_radar_detail.py`:

```python
def test_chart_carries_its_basis_not_the_quotes_venue():
    """A chart drawn from a converted US series says so on the chart itself.

    The header keeps saying Tradegate: that is where the headline price is
    from. The chart is a different statement and carries its own.
    """
    from features.radar import detail as detail_mod

    chart = detail_mod.Chart(start=dt.date(2026, 9, 1), closes=[1.0, 2.0],
                             chatter=[None, None], watched_from=None)

    assert chart.currency is None
    assert chart.basis_venue is None
    assert chart.converted_from is None
    assert chart.priced_from == 'daily'
    assert not hasattr(chart, 'history_proxy')
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_radar_detail.py::test_chart_carries_its_basis_not_the_quotes_venue -v`
Expected: FAIL — `AttributeError: 'Chart' object has no attribute 'currency'`.

- [ ] **Step 3: Replace the Chart's provenance fields**

In `features/radar/detail.py`, in the `Chart` dataclass, delete these seven lines:

```python
    # Xetra->Tradegate history-seam provenance (spec §8.2). Defaults keep
    # every non-proxy chart, including all intraday spans, byte-compatible.
    history_proxy: bool = False
    proxy_mic: str | None = None
    proxy_venue: str | None = None
    native_mic: str | None = None
    native_venue: str | None = None
    native_from: dt.date | None = None
```

and put this in their place:

```python
    # Where this chart's price line came from (features/radar/history.py).
    # Not the quote's venue: a Nasdaq listing quoted at Tradegate draws its
    # Nasdaq closes, converted, and the panel states that beside the chart.
    currency: str | None = None
    basis_venue: str | None = None
    converted_from: str | None = None
    # 'intraday' when the line came from quote snapshots, 'daily' when it
    # came from stored closes. The 1D span may be either (see Task 7's
    # fallback), and the panel's subtitle must not claim the wrong one.
    priced_from: str = 'daily'
```

- [ ] **Step 4: Point `intraday_chart_for` at the basis**

In `features/radar/detail.py`, inside `intraday_chart_for`, replace this block:

```python
    price_series = None
    if span == '1D':
        closes = intraday_prices(ticker, start, now, step_minutes, slots,
                                 market=market, mic=mic)
    else:
        from . import history
        days = int(slots * step_minutes / 1440) + 2
        price_series = history.series_for(
            ticker, market, mic, days, now.date())
        closes = _daily_anchors(
            ticker, start, now, step_minutes, slots,
            dict(price_series.closes), market=market, mic=mic)
```

with:

```python
    basis = None
    priced_from = 'daily'
    if span == '1D':
        closes = intraday_prices(ticker, start, now, step_minutes, slots,
                                 market=market, mic=mic)
        priced_from = 'intraday'
    else:
        from . import history
        days = int(slots * step_minutes / 1440) + 2
        basis = history.resolve_basis(ticker, quote, days, now.date())
        closes = _daily_anchors(
            ticker, start, now, step_minutes, slots,
            dict(basis.closes), market=market, mic=mic)
```

and replace the whole `return Chart(...)` at the end of `intraday_chart_for` with:

```python
    return Chart(
        start=start, closes=closes, chatter=chatter,
        watched_from=(start + dt.timedelta(
            minutes=first_watched * step_minutes)
                      if first_watched is not None else None),
        step_minutes=step_minutes,
        priced_from=priced_from,
        currency=(basis.currency if basis is not None else quote.currency),
        basis_venue=(basis.venue if basis is not None else quote.venue),
        converted_from=(basis.converted_from if basis is not None else None))
```

- [ ] **Step 5: Give `intraday_chart_for` the quote it now needs**

In `features/radar/detail.py`, change the signature:

```python
def intraday_chart_for(ticker, sources, now, span, *, quote):
```

and inside it, immediately after the docstring, add:

```python
    market, mic = quote.market, quote.mic
```

Then in `features/radar/detail_panel.py`, replace lines 336-357 — the whole `if chart_mod.is_intraday(span): ... chart.native_from = series.native_from` block — with:

```python
    if chart_mod.is_intraday(span):
        chart = chart_mod.intraday_chart_for(
            ticker, sources, now, span, quote=quote)
    else:
        days = chart_mod.SPAN_DAYS[span]
        start = now.date() - dt.timedelta(days=days - 1)
        from_dt = dt.datetime.combine(start, dt.time.min)
        # The basis owns which venue's closes these are and what currency
        # they are in; the chart only aligns them to calendar days.
        basis = history.resolve_basis(ticker, quote, days, now.date())
        chart = chart_mod.chart_for(
            ticker, start, days, dict(basis.closes),
            chart_mod.daily_counts([ticker], sources, from_dt, now),
            chart_mod.first_watched_day(sources, from_dt, now))
        chart.currency = basis.currency or quote.currency
        chart.basis_venue = basis.venue or quote.venue
        chart.converted_from = basis.converted_from
```

- [ ] **Step 6: Rewrite the seam tests Task 3 broke**

In `tests/test_radar_history.py`, delete every test that calls `history.series_for` (the ones the Task 3 Step 5 run named) and add in their place:

```python
def test_basis_prefers_the_deepest_venue(clean):
    """The old seam test, restated as the rule that replaced it.

    It used to assert that Xetra closes fill only the days BEFORE the first
    Tradegate one. There is no stitch any more: the deeper series wins whole,
    and the panel says which venue it was.
    """
    from models import RadarInstrument

    class Q:
        market, mic, venue, currency = 'de', 'XGAT', 'Tradegate BSX', 'EUR'

    ticker = f'{PREFIX}SEAM'
    for n in range(1, 3):
        db.session.add(RadarDailyClose(
            ticker=ticker, market='de', mic='XGAT', currency='EUR',
            close_date=TODAY - dt.timedelta(days=n),
            close=decimal.Decimal('9.00'), fetched_at=NOW))
    for n in range(1, 15):
        db.session.add(RadarDailyClose(
            ticker=ticker, market='de', mic='XETR', currency='EUR',
            close_date=TODAY - dt.timedelta(days=n),
            close=decimal.Decimal('8.00'), fetched_at=NOW))
    for mic, venue in (('XGAT', 'Tradegate BSX'), ('XETR', 'Xetra')):
        db.session.add(RadarInstrument(
            ticker=ticker, market='de', mic=mic, venue=venue,
            provider_symbol=ticker, currency='EUR', isin='DE000SEAM001',
            is_primary=(mic == 'XGAT'), mapping_status='mapped',
            mapped_at=NOW))
    db.session.commit()

    basis = history.resolve_basis(ticker, Q(), 30, TODAY)

    assert basis.mic == 'XETR'
    assert len(basis.closes) == 14
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/test_radar_detail.py tests/test_radar_history.py tests/test_radar_history_basis.py -v`
Expected: PASS. If `tests/test_radar_api.py` or `tests/test_radar_board.py` now error on the removed `Chart` fields, that is Task 5's job — do not touch them here.

- [ ] **Step 8: Commit**

```bash
git add features/radar/detail.py features/radar/detail_panel.py tests/test_radar_detail.py tests/test_radar_history.py
git commit -m "feat(radar): the panel chart draws its basis, not the quote's venue

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The payload and the renderer

**Files:**
- Modify: `features/radar/routes/api.py:583-612` (the `'chart'` block)
- Modify: `static/radar/src/types.ts:110-140` (`DetailChart`)
- Modify: `static/radar/src/detail/PriceChart.tsx` (the `currency` prop, `proxyNote`)
- Modify: `static/radar/src/detail/DetailPane.tsx:42-58` (subtitle map) and line 297 (the `currency` prop it passes)
- Test: `tests/test_radar_api.py` (extend), `static/radar/src/detail/PriceChart.test.tsx` (extend)

**Interfaces:**
- Consumes: `Chart.currency`, `Chart.basis_venue`, `Chart.converted_from`, `Chart.priced_from` (Task 4).
- Produces: payload keys `chart.currency`, `chart.basis_venue`, `chart.converted_from`, `chart.priced_from`; the removal of `history_proxy`, `proxy_mic`, `proxy_venue`, `native_mic`, `native_venue`, `native_from`.

- [ ] **Step 1: Find every frontend reader of the removed keys**

Run:
```bash
grep -rn "history_proxy\|proxy_mic\|proxy_venue\|native_mic\|native_venue\|native_from" static/radar/src/
```
Expected: hits in `types.ts`, `PriceChart.tsx`, and possibly `PriceChart.test.tsx`. Every hit must be gone by the end of this task — a payload key removed on the server while a component still reads it is exactly the dead-contract failure this codebase has shipped before.

- [ ] **Step 2: Write the failing server test**

Append to `tests/test_radar_api.py`:

```python
def test_panel_chart_states_its_basis(client):
    """The chart's own provenance travels with the chart, not the quote."""
    response = client.get('/radar/api/panel/AAPL?span=1M&market=de')
    assert response.status_code == 200
    chart = response.get_json()['chart']

    assert 'currency' in chart
    assert 'basis_venue' in chart
    assert 'converted_from' in chart
    assert chart['priced_from'] in ('daily', 'intraday')
    for gone in ('history_proxy', 'proxy_mic', 'proxy_venue',
                 'native_mic', 'native_venue', 'native_from'):
        assert gone not in chart
```

If the panel route is not `/radar/api/panel/<ticker>`, read the blueprint in `features/radar/routes/api.py` and use the real path; the assertions are unchanged.

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/test_radar_api.py::test_panel_chart_states_its_basis -v`
Expected: FAIL — `assert 'currency' in chart`.

- [ ] **Step 4: Update the serializer**

In `features/radar/routes/api.py`, replace this block inside `'chart': {`:

```python
            # Xetra->Tradegate seam provenance: visible near the chart,
            # never silently native (spec §8.2/§10).
            'history_proxy': d.chart.history_proxy,
            'proxy_mic': d.chart.proxy_mic,
            'proxy_venue': d.chart.proxy_venue,
            'native_mic': d.chart.native_mic,
            'native_venue': d.chart.native_venue,
            'native_from': (d.chart.native_from.isoformat()
                            if d.chart.native_from else None),
```

with:

```python
            # Where this line came from. The axis reads `currency` from
            # here, never from the quote: they differ exactly when the
            # basis is a converted foreign listing, which is the case the
            # reader most needs told (spec §1/§3).
            'currency': d.chart.currency,
            'basis_venue': d.chart.basis_venue,
            'converted_from': d.chart.converted_from,
            'priced_from': d.chart.priced_from,
```

- [ ] **Step 5: Run the server test to verify it passes**

Run: `python -m pytest tests/test_radar_api.py -v`
Expected: PASS.

- [ ] **Step 6: Update the frontend type**

In `static/radar/src/types.ts`, replace the `history_proxy` … `native_from` fields of `DetailChart` (lines 130-139) with:

```ts
  /** The currency `closes` is expressed in, and the venue those closes came
   *  from. Not necessarily the quote's: a Nasdaq listing quoted at Tradegate
   *  draws its Nasdaq closes converted to EUR. */
  currency: string | null
  basis_venue: string | null
  /** Set only when `closes` was converted out of another currency. The panel
   *  states it beside the chart -- a converted line must never read native. */
  converted_from: string | null
  /** 'intraday' when the line is quote snapshots, 'daily' when it is stored
   *  closes. 1D may be either. */
  priced_from: 'intraday' | 'daily'
```

- [ ] **Step 7: Write the failing component test**

Append to `static/radar/src/detail/PriceChart.test.tsx`, following the imports and helpers already in that file:

```tsx
it('states a converted basis beside the chart', () => {
  const { getByText } = render(
    <PriceChart chart={{
      ...baseChart,
      closes: [1, 2, 3],
      currency: 'EUR',
      basis_venue: 'Nasdaq Global Market',
      converted_from: 'USD',
    }} />)

  expect(getByText(
    'Nasdaq Global Market closes, converted to EUR at the ECB daily rate',
  )).toBeTruthy()
})

it('says nothing when the basis is the quote’s own venue', () => {
  const { queryByText } = render(
    <PriceChart chart={{
      ...baseChart,
      closes: [1, 2, 3],
      currency: 'EUR',
      basis_venue: 'Tradegate BSX',
      converted_from: null,
    }} quoteVenue="Tradegate BSX" />)

  expect(queryByText(/converted/)).toBeNull()
})
```

If `baseChart` does not already exist in that file, define it at the top of the file from the existing test's inline chart object, adding `currency: null, basis_venue: null, converted_from: null, priced_from: 'daily'`.

- [ ] **Step 8: Run it to verify it fails**

Run: `npm test`
Expected: FAIL on the radar config run — the note text is not rendered.

- [ ] **Step 9: Update `PriceChart`**

In `static/radar/src/detail/PriceChart.tsx`, change the component signature from:

```tsx
export function PriceChart({ chart, currency = 'USD' }: {
  chart: DetailChart
  /** The quote's currency, for the axis and the hover readout. */
  currency?: string
}) {
```

to:

```tsx
export function PriceChart({ chart, quoteVenue }: {
  chart: DetailChart
  /** The venue in the header. The basis note appears when the line came
   *  from somewhere else. */
  quoteVenue?: string | null
}) {
  // The axis belongs to the LINE, not the headline price. They differ
  // exactly when the basis is a converted foreign listing.
  const currency = chart.currency ?? 'USD'
```

and replace the `proxyNote` block:

```tsx
  const proxyNote = chart.history_proxy && chart.proxy_venue &&
      chart.native_venue
    ? `${chart.proxy_venue} history${chart.native_from
        ? ` through ${formatMarketDate(chart.native_from)}`
        : ''} · ${chart.native_venue} now`
    : null
```

with:

```tsx
  /* The basis is stated in text NEXT TO the chart, never in a tooltip: a
   * converted or foreign-venue line must not read as native (spec §1/§3). */
  const basisNote = !chart.basis_venue || chart.basis_venue === quoteVenue
    ? null
    : chart.converted_from
      ? `${chart.basis_venue} closes, converted to ${currency} at the ECB daily rate`
      : `${chart.basis_venue} closes${quoteVenue ? ` · quoted at ${quoteVenue}` : ''}`
```

and in the JSX, change `{proxyNote ? <p className="history-proxy-note">{proxyNote}</p> : null}` to `{basisNote ? <p className="history-proxy-note">{basisNote}</p> : null}`.

If `formatMarketDate` is now unused in the file, remove it from the import on line 1 — `tsc --noEmit` runs as part of `npm run build` and an unused import is a build error.

- [ ] **Step 10: Update `DetailPane`**

In `static/radar/src/detail/DetailPane.tsx`, change line 297 from:

```tsx
                      currency={detail.identity.quote.currency ?? undefined} />
```

to:

```tsx
                      quoteVenue={detail.identity.quote.venue} />
```

and make the 1D subtitle follow the chart. Replace the constant lookup at the `SUBTITLE`/`AXIS` use site with a call that reads `priced_from`; add above the map:

```tsx
/** 1D prices from quote snapshots when there are enough of them and from
 *  stored daily closes when there are not, so its subtitle cannot be a
 *  constant -- it would claim intraday resolution the line does not have. */
function subtitleFor(chart: DetailChart): string {
  if (chart.span === '1D' && chart.priced_from === 'daily') {
    return 'daily closes · mentions per 15 min'
  }
  return SUBTITLE[chart.span]
}
```

and use `subtitleFor(detail.chart)` wherever `SUBTITLE[span]` was read.

- [ ] **Step 11: Run all the tests**

Run: `npm test`
Expected: PASS on both configs.

Run: `npm run build`
Expected: no TypeScript errors.

Run: `python -m pytest tests/test_radar_api.py tests/test_radar_detail.py -v`
Expected: PASS.

- [ ] **Step 12: Confirm no dead readers remain**

Run:
```bash
grep -rn "history_proxy\|proxy_mic\|proxy_venue\|native_mic\|native_venue\|native_from" static/radar/src/ features/radar/
```
Expected: no output.

- [ ] **Step 13: Commit**

```bash
git add features/radar/routes/api.py static/radar/src/types.ts static/radar/src/detail/PriceChart.tsx static/radar/src/detail/PriceChart.test.tsx static/radar/src/detail/DetailPane.tsx tests/test_radar_api.py
git commit -m "feat(radar): the chart states the venue and currency it was drawn from

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: `_daily_anchors` stops discarding real prints

**Files:**
- Modify: `features/radar/detail.py` — `_daily_anchors`, the `in_session` comparison around line 296
- Test: `tests/test_radar_detail.py` (extend)

**Interfaces:**
- Consumes: `market_calendars.session_bounds`, which returns `SessionBounds(opens_at, premarket_closes_at, regular_opens_at, regular_closes_at, closes_at)` — `opens_at`/`closes_at` are the EXTENDED session edges.
- Produces: no new names; `_daily_anchors` keeps its signature.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_radar_detail.py`:

```python
def test_a_print_stamped_at_the_bell_is_an_anchor():
    """`opens <= ts < closes` dropped every print stamped exactly at 20:00Z.

    Measured on production 2026-09-04: all 54 of RZLV's prints for 2026-08-28
    carried exactly that timestamp, so its week line had nothing to draw.
    """
    from features.radar import detail as detail_mod
    from features.radar.market_calendars import session_bounds

    day = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)
    bounds = session_bounds('us', day)
    bell = bounds.regular_closes_at.astimezone(
        dt.timezone.utc).replace(tzinfo=None)

    kept = detail_mod._session_prints(
        [(bell, 10.0)], bounds)

    assert kept == [(bell, 10.0)]


def test_extended_hours_prints_anchor_when_the_session_had_none():
    """Tradegate's whole poll window is its late session.

    Its regular window is 09:00-17:30 Berlin and every stored XGAT quote_ts
    on production falls after it, so a regular-only filter kept zero of them.
    """
    from features.radar import detail as detail_mod
    from features.radar.market_calendars import session_bounds

    day = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)
    bounds = session_bounds('de', day, mic='XGAT')
    late = bounds.regular_closes_at.astimezone(
        dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=30)

    kept = detail_mod._session_prints([(late, 10.0)], bounds)

    assert kept == [(late, 10.0)]


def test_a_print_outside_the_extended_session_is_not_an_anchor():
    from features.radar import detail as detail_mod
    from features.radar.market_calendars import session_bounds

    day = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)
    bounds = session_bounds('us', day)
    stray = bounds.opens_at.astimezone(
        dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=2)

    assert detail_mod._session_prints([(stray, 10.0)], bounds) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_radar_detail.py -k session_prints -v`
Expected: FAIL — `AttributeError: module 'features.radar.detail' has no attribute '_session_prints'`.

- [ ] **Step 3: Extract and fix the filter**

In `features/radar/detail.py`, add above `_daily_anchors`:

```python
def _session_prints(prints, bounds):
    """The day's prints worth anchoring, best band first.

    Regular-session prints where there are any, extended-hours ones where
    there are not. Both edges INCLUSIVE: a print stamped exactly at the
    closing bell is the closing print, and the half-open comparison this
    replaced discarded it -- all 54 of one ticker's prints for one day,
    measured on production 2026-09-04.

    Extended hours are a fallback rather than a peer because a regular
    print is a better answer to "what did this trade at today". They are
    admitted at all because Tradegate's entire poll window lies outside its
    own regular session, so a regular-only rule kept nothing for the whole
    German board.
    """
    def naive(when):
        return when.astimezone(dt.timezone.utc).replace(tzinfo=None)

    regular = [(ts, price) for ts, price in prints
               if naive(bounds.regular_opens_at) <= ts
               <= naive(bounds.regular_closes_at)]
    if regular:
        return regular
    return [(ts, price) for ts, price in prints
            if naive(bounds.opens_at) <= ts <= naive(bounds.closes_at)]
```

Then inside `_daily_anchors`, replace:

```python
        in_session = [(ts, float(price)) for ts, price in prints
                      if opens <= ts < closes]
```

with:

```python
        in_session = _session_prints(
            [(ts, float(price)) for ts, price in prints], bounds)
```

The local `opens`/`closes` variables above it stay — `closes` is still used for the stored-close slot index below.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_detail.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add features/radar/detail.py tests/test_radar_detail.py
git commit -m "fix(radar): a print at the bell, and one after hours, still anchor the week

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: 1D falls back to daily anchors

**Files:**
- Modify: `features/radar/detail.py` — `intraday_chart_for`
- Test: `tests/test_radar_detail.py` (extend)

**Interfaces:**
- Consumes: `history.resolve_basis` (Task 3), `_daily_anchors` (Task 6), `Chart.priced_from` (Task 4).
- Produces: `detail.MIN_INTRADAY_POINTS = 2`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_radar_detail.py`:

```python
def test_one_quote_in_the_day_falls_back_to_daily_closes():
    """76% of US-quoted tickers had fewer than two prints in 24h on prod.

    A one-point 1D chart renders the same "no stored price" text as an empty
    one, so the span was blank for most of the board. Coarse beats empty, and
    the subtitle says which it got.
    """
    from features.radar import detail as detail_mod
    assert detail_mod.MIN_INTRADAY_POINTS == 2
```

Then add an integration assertion, which is what actually pins the behaviour:

```python
def test_the_1d_chart_reports_where_its_line_came_from(client):
    """priced_from is the only thing that separates a coarse 1D from a dense
    one, so it must be present and honest on a real panel."""
    response = client.get('/radar/api/panel/AAPL?span=1D&market=de')
    assert response.status_code == 200
    chart = response.get_json()['chart']
    real = [c for c in chart['closes'] if c is not None]

    if chart['priced_from'] == 'intraday':
        assert len(real) >= 2
    else:
        assert chart['basis_venue'] is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_radar_detail.py -k 1d -v`
Expected: FAIL — `AttributeError: module 'features.radar.detail' has no attribute 'MIN_INTRADAY_POINTS'`.

- [ ] **Step 3: Implement the fallback**

In `features/radar/detail.py`, add beside the other constants, under `INTRADAY_SPANS`:

```python
# Below this many priced slots, the 1D span stops being an intraday chart.
#
# Two, because the renderer needs two points for a line and one stored quote
# draws the same "no stored price" text as none at all. The poller only
# covers chatter-selected tickers at 55 a cycle, so on 2026-09-04 that was
# 76% of every US-quoted ticker on production: a whole span that said
# "nothing known" about tickers with three years of stored closes.
MIN_INTRADAY_POINTS = 2
```

Then in `intraday_chart_for`, replace the `if span == '1D':` arm written in Task 4:

```python
    if span == '1D':
        closes = intraday_prices(ticker, start, now, step_minutes, slots,
                                 market=market, mic=mic)
        priced_from = 'intraday'
```

with:

```python
    if span == '1D':
        closes = intraday_prices(ticker, start, now, step_minutes, slots,
                                 market=market, mic=mic)
        priced_from = 'intraday'
        if sum(1 for c in closes if c is not None) < MIN_INTRADAY_POINTS:
            from . import history
            basis = history.resolve_basis(ticker, quote, 3, now.date())
            anchored = _daily_anchors(
                ticker, start, now, step_minutes, slots,
                dict(basis.closes), market=market, mic=mic)
            if sum(1 for c in anchored if c is not None) >= MIN_INTRADAY_POINTS:
                closes = anchored
                priced_from = 'daily'
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_detail.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add features/radar/detail.py tests/test_radar_detail.py
git commit -m "feat(radar): a thin day falls back to daily closes rather than drawing nothing

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Whole-market closes from Massive

**Files:**
- Modify: `run_radar_ingest.py` — add `_scheduled_us_closes` and register it in the scheduler block
- Create: `scripts/backfill_radar_us_closes.py`
- Test: `tests/test_radar_massive.py` (extend)

**Interfaces:**
- Consumes: `features/radar/prices/massive.py` — `MassiveHttp` (reads `RADAR_MASSIVE_API_KEY`, `RADAR_MASSIVE_BASE_URL`, paces at `CALLS_PER_MINUTE = 5`), `MassiveProvider(http).grouped_closes(day)` with `source = 'massive_grouped'`, and `MassiveTransportError`; `market_data.py`'s existing identity mapping; `history.record_closes` (which must be called with `adjustment_basis='split'` for this source or it raises).
- Produces: `run_radar_ingest.store_grouped_day(provider, day, now) -> int` (tickers written), and `scripts/backfill_radar_us_closes.py` runnable as `python scripts/backfill_radar_us_closes.py --days 500`.

Read `features/radar/prices/massive.py` and `features/radar/market_data.py` in full before writing this task's code — the symbol-to-identity mapping already exists there and must be reused, not reimplemented.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_radar_massive.py`:

```python
def test_a_grouped_day_writes_every_mapped_ticker(clean):
    """One request covers the whole US market, which is the entire point.

    Per-ticker fetching realised ~250 tickers a day against a 12,599-ticker
    universe on production; 10,676 of them had no stored close at all.
    """
    import datetime as dt
    import decimal
    import run_radar_ingest

    day = dt.date(2026, 9, 3)
    now = dt.datetime(2026, 9, 4, 6, 0, 0)

    class FakeProvider:
        source = 'massive_grouped'

        def grouped_closes(self, when):
            assert when == day
            return {f'{PREFIX}A': decimal.Decimal('10.00'),
                    f'{PREFIX}B': decimal.Decimal('20.00'),
                    'NOT-MAPPED-XYZ': decimal.Decimal('30.00')}

    written = run_radar_ingest.store_grouped_day(FakeProvider(), day, now)

    assert written == 2


def test_an_unmapped_symbol_is_reported_not_stored(clean, caplog):
    import datetime as dt
    import decimal
    import run_radar_ingest

    class FakeProvider:
        source = 'massive_grouped'

        def grouped_closes(self, when):
            return {'NOT-MAPPED-XYZ': decimal.Decimal('30.00')}

    written = run_radar_ingest.store_grouped_day(
        FakeProvider(), dt.date(2026, 9, 3), dt.datetime(2026, 9, 4, 6, 0, 0))

    assert written == 0
    assert 'unmapped' in caplog.text.lower()
```

The `clean` fixture and `PREFIX` already exist in `tests/test_radar_massive.py`; if `clean` does not seed `RadarInstrument` rows for `{PREFIX}A` and `{PREFIX}B` as mapped US primaries, extend it to do so and to delete them on teardown.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_radar_massive.py -v`
Expected: FAIL — `AttributeError: module 'run_radar_ingest' has no attribute 'store_grouped_day'`.

- [ ] **Step 3: Implement the writer**

In `run_radar_ingest.py`, beside the other history helpers, add:

```python
def store_grouped_day(provider, day, now):
    """One grouped-daily payload -> radar_daily_closes. Returns tickers written.

    The provider returns exact provider symbols and knows nothing about radar
    identities; the mapping is RadarInstrument's, exactly as market_data does
    it for quotes. A symbol with no mapped instrument is COUNTED AND LOGGED
    rather than dropped -- a wholesale source surfaces mapping gaps that
    per-ticker fetching never exercised, and that report is the point.
    """
    from models import RadarInstrument

    closes = provider.grouped_closes(day)
    if not closes:
        logger.info('radar us closes %s: provider returned nothing', day)
        return 0

    rows = RadarInstrument.query.filter_by(
        market='us', is_primary=True).all()
    by_symbol = {row.provider_symbol.upper(): row for row in rows}

    written = 0
    unmapped = 0
    for symbol, close in closes.items():
        instrument = by_symbol.get(symbol.upper())
        if instrument is None:
            unmapped += 1
            continue
        history.record_closes(
            instrument.ticker, [(day, close)], now,
            market='us', mic=instrument.mic, currency=instrument.currency,
            source='massive_grouped', adjustment_basis='split', commit=False)
        written += 1
    db.session.commit()
    logger.info('radar us closes %s: stored=%d unmapped=%d', day, written,
                unmapped)
    return written
```

Import `history` and `db` at the top of `run_radar_ingest.py` if they are not already imported there; check first.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_massive.py -v`
Expected: PASS.

- [ ] **Step 5: Register the daily job**

In `run_radar_ingest.py`, add beside the other scheduled functions:

```python
def _scheduled_us_closes():
    """Yesterday's whole-market closes, once an hour until they land.

    Grouped daily is one request for every US ticker, so this is cheap enough
    to retry rather than schedule precisely: the file appears some hours after
    the bell and record_closes is an upsert, so a repeat is a restatement.
    """
    from features.radar.prices import massive

    with app.app_context():
        now = dt.datetime.utcnow()
        day = (now - dt.timedelta(days=1)).date()
        provider = massive.MassiveProvider(massive.MassiveHttp())
        try:
            store_grouped_day(provider, day, now)
        except massive.MassiveTransportError as exc:
            logger.warning('radar us closes %s: %s', day, exc)
```

and register it in the scheduler block next to `_scheduled_history`, with `scheduler.add_job(_scheduled_us_closes, 'interval', hours=1)`. Match the exact call style of the neighbouring `add_job` lines.

- [ ] **Step 6: Write the backfill script**

Create `scripts/backfill_radar_us_closes.py`:

```python
# personal_apps/scripts/backfill_radar_us_closes.py
"""Backfill radar_daily_closes from Massive's grouped-daily endpoint.

One request per US trading day, paced by the adapter at five a minute. The
free tier reaches back about two years, so --days 500 is roughly the whole
of it and takes about an hour and forty minutes.

    python scripts/backfill_radar_us_closes.py --days 500
"""
import argparse
import datetime as dt
import sys

sys.path.insert(0, '.')

from app import app                                # noqa: E402
from features.radar.prices import massive          # noqa: E402
from run_radar_ingest import store_grouped_day     # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=500,
                        help='calendar days back from yesterday')
    args = parser.parse_args()

    provider = massive.MassiveProvider(massive.MassiveHttp())
    now = dt.datetime.utcnow()
    total = 0
    with app.app_context():
        for back in range(1, args.days + 1):
            day = (now - dt.timedelta(days=back)).date()
            if day.weekday() >= 5:
                continue
            try:
                written = store_grouped_day(provider, day, now)
            except massive.MassiveTransportError as exc:
                print(f'{day}: {exc}')
                continue
            total += written
            print(f'{day}: {written}')
    print(f'radar us close backfill: {total} rows')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 7: Verify the script runs and refuses cleanly without a key**

Run: `python scripts/backfill_radar_us_closes.py --days 2`
Expected: with no `RADAR_MASSIVE_API_KEY` set, a warning line per day and `radar us close backfill: 0 rows` — a clean refusal, not a traceback.

- [ ] **Step 8: Commit**

```bash
git add run_radar_ingest.py scripts/backfill_radar_us_closes.py tests/test_radar_massive.py
git commit -m "feat(radar): fill the close store from one grouped-daily request

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: A fair German history queue

**Files:**
- Modify: `models.py` — add `history_due_at` to `RadarInstrument`
- Modify: `migrations/versions/d4e7a1b93c25_add_radar_fx_rates.py` — NO. Create: `migrations/versions/e5f8b2ca4d36_add_instrument_history_due.py`
- Modify: `features/radar/history.py` — `fetch_into_store`, the silent `continue`
- Modify: `run_radar_ingest.py` — `refresh_de_history` selection
- Test: `tests/test_radar_history.py` (extend)

**Interfaces:**
- Consumes: `history.HISTORY_DAYS`.
- Produces:
  - `RadarInstrument.history_due_at: datetime | None`
  - `history.fetch_into_store(...) -> tuple[int, int]` — **CHANGED RETURN**: `(stored, empty)` instead of `stored`. Every existing caller must be updated in this task; find them with `grep -rn "fetch_into_store" .`
  - `history.due_instruments(instruments, now, limit) -> list` — oldest `history_due_at` first, `None` first

- [ ] **Step 1: Write the failing test**

Append to `tests/test_radar_history.py`:

```python
def test_an_empty_fetch_is_counted_not_swallowed(clean):
    """`if not closes: continue` reported success while storing nothing.

    Yahoo refuses any MIC outside its allowlist, which has no XGAT, so the
    German per-ticker fetcher has silently stored zero rows since it was
    written -- and the log line said it had run.
    """
    provider = FakeProvider({})

    stored, empty = history.fetch_into_store(
        provider, [f'{PREFIX}EMPTY'], NOW)

    assert stored == 0
    assert empty == 1


def test_due_instruments_serves_the_never_fetched_first(clean):
    from models import RadarInstrument

    never = RadarInstrument(
        ticker=f'{PREFIX}NEW', market='de', mic='XETR', venue='Xetra',
        provider_symbol='NEW', currency='EUR', is_primary=True,
        mapping_status='mapped', mapped_at=NOW, history_due_at=None)
    recent = RadarInstrument(
        ticker=f'{PREFIX}OLD', market='de', mic='XETR', venue='Xetra',
        provider_symbol='OLD', currency='EUR', is_primary=True,
        mapping_status='mapped', mapped_at=NOW,
        history_due_at=NOW - dt.timedelta(hours=1))
    db.session.add_all([recent, never])
    db.session.commit()

    due = history.due_instruments([recent, never], NOW, limit=2)

    assert [row.ticker for row in due] == [f'{PREFIX}NEW', f'{PREFIX}OLD']
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_radar_history.py -k "empty_fetch or due_instruments" -v`
Expected: FAIL — `TypeError: cannot unpack non-sequence int`.

- [ ] **Step 3: Add the column and its migration**

In `models.py`, in `RadarInstrument`, after `mapping_generation_id`, add:

```python
    # When this instrument's daily history is next worth fetching. NULL means
    # never fetched, which sorts first: a ticker the panel cannot draw at all
    # outranks one whose last close is a day stale.
    #
    # A durable schedule rather than a per-cycle ranking. The history job used
    # to select from the loudest hundred tickers by chatter, so a ticker that
    # had never been loud was unreachable however long it sat on the board --
    # 10,676 of 12,599 active tickers had no stored close on 2026-09-04.
    history_due_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
```

Create `migrations/versions/e5f8b2ca4d36_add_instrument_history_due.py`:

```python
"""add radar_instruments.history_due_at

A durable per-instrument history schedule, so the fetch queue drains instead
of re-competing with today's chatter ranking. Plain DDL -- MariaDB in prod.

Revision ID: e5f8b2ca4d36
Revises: d4e7a1b93c25
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'e5f8b2ca4d36'
down_revision = 'd4e7a1b93c25'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('radar_instruments',
                  sa.Column('history_due_at', mysql.DATETIME(fsp=6),
                            nullable=True))
    op.create_index('ix_radar_instruments_history_due', 'radar_instruments',
                    ['market', 'history_due_at'])


def downgrade():
    op.drop_index('ix_radar_instruments_history_due',
                  table_name='radar_instruments')
    op.drop_column('radar_instruments', 'history_due_at')
```

Run: `python -m flask db upgrade`
Expected: `Running upgrade d4e7a1b93c25 -> e5f8b2ca4d36`.

- [ ] **Step 4: Change `fetch_into_store` and add `due_instruments`**

In `features/radar/history.py`, replace the body of `fetch_into_store` from `stored = 0` to the end with:

```python
    stored = 0
    empty = 0
    provider_symbols = provider_symbols or {}
    for ticker in tickers:
        symbol = provider_symbols.get(ticker, ticker)
        if mic is None:
            closes = provider.daily_closes(symbol, HISTORY_DAYS)
        else:
            closes = provider.daily_closes(symbol, HISTORY_DAYS, mic_code=mic)
        if not closes:
            # Counted, not swallowed. A provider that refuses an identity --
            # Yahoo rejects any MIC outside its allowlist before it looks at
            # a single bar -- otherwise reports a successful cycle that
            # stored nothing, which is how the German history fetcher ran
            # for weeks writing zero rows.
            empty += 1
            continue
        record_closes(ticker, closes, now, market=market, mic=mic,
                      currency=currency,
                      source=getattr(provider, 'source', 'legacy'),
                      adjustment_basis=(
                          'split' if getattr(provider, 'source', None)
                          in ('yahoo_chart', 'massive_grouped',
                              'twelvedata') else None))
        stored += 1
    return stored, empty
```

and add at the end of the module:

```python
def due_instruments(instruments, now, limit):
    """The next `limit` instruments to spend history requests on.

    Never fetched first, then longest overdue. A plain ordering over a stored
    timestamp, so the queue DRAINS: a budget that runs out delays an
    instrument rather than dropping it, which is the difference between a
    backlog and a ticker that is never reachable at all.
    """
    ordered = sorted(
        instruments,
        key=lambda row: (row.history_due_at is not None, row.history_due_at
                         or now))
    return ordered[:limit]
```

- [ ] **Step 5: Update every caller of `fetch_into_store`**

Run: `grep -rn "fetch_into_store" . --include=*.py`

For each call site outside `history.py` and the tests, change `stored = history.fetch_into_store(...)` to `stored, empty = history.fetch_into_store(...)` and include `empty` in that site's existing log line. In `run_radar_ingest.py`'s `refresh_de_history`, also stamp the schedule after each pass:

```python
        for instrument in batch:
            instrument.history_due_at = now + dt.timedelta(days=1)
        db.session.commit()
```

and select `batch` with `history.due_instruments(candidates, now, HISTORY_LIMIT)` in place of the loudest-first slice.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_radar_history.py tests/test_radar_ingest.py tests/test_radar_daemon.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add models.py features/radar/history.py run_radar_ingest.py migrations/versions/e5f8b2ca4d36_add_instrument_history_due.py tests/test_radar_history.py
git commit -m "fix(radar): the history queue drains instead of chasing today's loudest

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Pace the German feed to its budget

**Files:**
- Modify: `features/radar/config.py:933-935`
- Modify: `features/radar/market_data.py` — `collect_german_cycle`
- Test: `tests/test_radar_market_data.py` (extend)

**Interfaces:**
- Consumes: `market_calendars.session_state`.
- Produces: `market_data.DE_COLLECT_MICS`, and `collect_german_cycle` returning a `CycleSummary` with `status='closed'` outside the session.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_radar_market_data.py`:

```python
def test_the_collector_sleeps_outside_the_tradegate_session():
    """The budget was spent overnight on files nobody would read.

    Four channel-passes every five minutes is 48 downloads an hour, so a
    300/24h budget was gone before noon and every production cycle from
    then on recorded 'download budget spent 300/300' -- the German board
    was dark for the whole trading day, every day.
    """
    import datetime as dt
    from features.radar import market_data

    # 03:00 UTC on a weekday: Tradegate is shut.
    night = dt.datetime(2026, 9, 3, 3, 0, 0)
    summary = market_data.collect_german_cycle(
        provider=None, generation_id=None, active_tickers=[], now=night,
        mode='active')

    assert summary.status == 'closed'
    assert summary.files_seen == 0


def test_only_quote_supplying_mics_are_collected():
    from features.radar import market_data
    assert market_data.DE_COLLECT_MICS == ('XGAT',)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_radar_market_data.py -k "sleeps or quote_supplying" -v`
Expected: FAIL — `AttributeError: module 'features.radar.market_data' has no attribute 'DE_COLLECT_MICS'`.

- [ ] **Step 3: Raise the budget**

In `features/radar/config.py`, replace lines 933-935 with:

```python
DE_FILES_PER_CYCLE = 1                        # per channel, newest first
# Session-gated collection over the quote-supplying MIC costs two downloads
# a cycle, twelve cycles an hour, across Tradegate's ~14.5-hour day: about
# 348. At 300 the budget was spent by mid-morning and every later cycle
# recorded 'download budget spent 300/300' -- the safety net had become the
# binding constraint. 400 leaves headroom above a full session and still
# sits far under the ~170 files/hour that drew the original HTTP 429.
DE_DOWNLOAD_BUDGET_24H = 400                  # attempted downloads, all channels
DE_THROTTLE_BACKOFF_SECONDS = (1800, 21600)   # first wait, longest wait
```

- [ ] **Step 4: Gate the cycle**

In `features/radar/market_data.py`, beside the other constants, add:

```python
# MICs the collector actually spends downloads on.
#
# XGAT only: Tradegate is the venue that supplies German QUOTES, and Xetra's
# daily closes come from the history path (features/radar/history.py), not
# from this feed. Collecting both doubled the download cost for a series
# nothing reads.
DE_COLLECT_MICS = ('XGAT',)
```

and at the top of `collect_german_cycle`, immediately after the docstring:

```python
    from .market_calendars import session_state

    aware = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    if session_state('de', aware, mic='XGAT') == 'closed':
        # A file published while the venue is shut is a file the board will
        # never draw, and the budget it costs is the one the session needs.
        return CycleSummary(mode=mode, status='closed', files_seen=0,
                            files_accepted=0, selected_quotes=0,
                            rejected_records=0, error_code=None)
```

Then change the MIC selection line from:

```python
    mics = sorted({mic for mic, _ in by_identity}) or ['XGAT']
```

to:

```python
    mics = [mic for mic in sorted({mic for mic, _ in by_identity})
            if mic in DE_COLLECT_MICS] or list(DE_COLLECT_MICS)
```

If `session_state` returns a value other than `'closed'` for a shut venue, read `features/radar/market_calendars/tradegate.py` and use whatever it actually returns; the test asserts on `summary.status`, not on the calendar's vocabulary.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_radar_market_data.py tests/test_radar_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add features/radar/config.py features/radar/market_data.py tests/test_radar_market_data.py
git commit -m "fix(radar): the German feed spends its budget on the session, not the night

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: End-to-end verification and merge

**Files:**
- Create: `scratchpad/probe_panel_matrix.py` (untracked, never committed)
- Test: full suite

**Interfaces:** none — this task ships.

- [ ] **Step 1: Run the whole Python suite**

Run: `python -m pytest tests/ -q`
Expected: PASS. Any failure here is a real regression in this plan's work — fix it before continuing, and do not adjust an assertion to match new behaviour without checking the spec first.

- [ ] **Step 2: Run the whole JS suite and the build**

Run: `npm test`
Run: `npm run build`
Expected: both clean.

- [ ] **Step 3: Measure the matrix that started this**

Create `scratchpad/probe_panel_matrix.py`:

```python
import datetime as dt
import sys

sys.path.insert(0, '.')

from app import app
from features.radar import detail_panel
from features.radar.config import SOURCES

with app.app_context():
    now = dt.datetime.utcnow()
    for market in ('de', 'us'):
        print('=== board market =', market)
        for ticker in ('RZLV', 'AAPL', 'NVDA', 'TSLA'):
            row = []
            for span in ('1D', '1W', '1M', '6M', '1Y', '3Y'):
                d = detail_panel.build(ticker, tuple(SOURCES), now,
                                       span=span, market=market)
                n = sum(1 for v in d.chart.closes if v is not None)
                row.append(f'{span}={n}/{len(d.chart.closes)}')
            print(' ', ticker, d.chart.currency, d.chart.basis_venue,
                  d.chart.converted_from, ' '.join(row))
```

Run: `python scratchpad/probe_panel_matrix.py`

Expected: on `board=de`, RZLV's daily spans are no longer `2/30`, `2/182`, `2/365`, `2/1095`; they carry hundreds of points with `currency='EUR'` and `converted_from='USD'`. Record the numbers — they are the evidence this plan worked, and they go in the completion report.

- [ ] **Step 4: See it**

Start the app on port 5001 and screenshot the panel with python-playwright at 390×844 and at desktop width, minting a session cookie rather than logging in (see `reference_personal_apps_local_run`). Batch both viewports into one script and one Bash call, then `Read` the PNGs.

Confirm by eye: a price line exists on 1M/1Y/3Y for a German-quoted ticker, the axis reads `€`, and the basis note sits above the chart reading `Nasdaq Global Market closes, converted to EUR at the ECB daily rate`.

- [ ] **Step 5: Commit any fixes, then merge**

```bash
git checkout dev_personal
git add <only files this plan touched>
git commit -m "fix(radar): <what the visual pass found>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git checkout main
git merge dev_personal
git push origin main
git checkout dev_personal
git push origin dev_personal
```

The `git checkout dev_personal` at the end is not optional: merging leaves HEAD on `main`, and the next commit made without it lands on the wrong branch.

- [ ] **Step 6: Report the deploy carries**

The deploy is Michi's. Tell him, in this order:

1. `flask db upgrade` in `personal_apps/` — two new migrations (`d4e7a1b93c25`, `e5f8b2ca4d36`)
2. add `RADAR_MASSIVE_API_KEY=<his free key>` to `/root/coc-stats/.env`
3. `python scripts/backfill_radar_fx.py` — one request, seconds
4. `python scripts/backfill_radar_us_closes.py --days 500` — ~100 minutes at 5 calls/min
5. the Xetra depth backfill at `HISTORY_DAYS`

---

## Self-Review

**Spec coverage.** §1 basis → Task 3, wired in Task 4. §2 FX → Tasks 1-2. §3 payload/renderer → Task 5. §4 anchors → Task 6. §5 1D fallback → Task 7. §6 Massive → Task 8. §7 German depth and fair queue → Task 9 (the Xetra depth backfill itself is a deploy carry, Task 11 Step 6, since it is a data operation against production and not a code change). §8 feed pacing → Task 10. Testing section → distributed per task plus Task 11. Rollout → Task 11.

**One gap accepted deliberately:** the spec's "budget state joins the ops summary" (§8) is not a task. It is an observability nicety with no user-visible effect on the chart, and adding it would mean touching the ops summary's shape for one line. If Michi wants it, it is a five-minute follow-up.

**Type consistency.** `HistoryBasis` fields are named identically in Task 3 (definition), Task 4 (`basis.currency`, `basis.venue`, `basis.converted_from`), Task 5 (`chart.currency`, `chart.basis_venue`, `chart.converted_from`) and the TS type. Note the deliberate rename across the boundary: the basis calls it `venue`, the chart calls it `basis_venue`, because `Chart` already carries other venue-free fields and an unqualified `venue` on the payload would read as the quote's. `fetch_into_store`'s return type changes in Task 9 and every caller is updated in the same task.
