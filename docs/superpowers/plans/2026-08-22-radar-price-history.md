# Radar Price History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the radar's existing chatter-vs-price chart a span control (24h / 1M / 3M / 1Y) so a ticker seen for the first time can be judged against what the stock has been doing for a year.

**Architecture:** Daily closes are fetched once per ticker per day by a new daemon job and stored in `radar_daily_closes`. Daily chatter is aggregated from buckets already stored. The payload carries both as calendar-day-aligned arrays under one start date; the island slices them client-side. Volatility stops calling the provider and reads the same table.

**Tech Stack:** Flask + SQLAlchemy + Flask-Migrate (MySQL 8 dev / MariaDB prod), APScheduler daemon, React 19 + TypeScript + Vite island, pytest + vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-22-radar-price-history-design.md`. Read it before Task 1.
- **This changes nothing about divergence, the eligibility floor, or the ranking.** If a task appears to, stop and re-read the spec's Scope boundary.
- Every datetime stored is **naive UTC**. `close_date` is a `DATE`, not a datetime.
- Green and red mean **price direction** and nothing else on this surface. Chatter is violet.
- **An absence is never a zero**, and the two series mean different things by it. `closes[i] = null` is a weekend or holiday — the price line is drawn ACROSS it. `chatter[i] = null` is before ingest began — no bar is drawn at all.
- **Both series are indexed by calendar day** from one shared `from` date. Never by array index: price has ~252 trading days a year against chatter's 365, and index positioning drifts them over a hundred days apart.
- Prod is **MariaDB**, dev is MySQL 8. Keep DDL plain — no `CAST(... AS JSON)`, no partitioning on this table.
- TypeScript runs with `strict` and `noUncheckedIndexedAccess`. Indexed reads are `T | undefined`; use `.at()` or an explicit guard, and never add `any`.
- `npm run build` runs `tsc --noEmit` over `static/gym/src` **and** `static/radar/src`. It must stay green.
- Run pytest from `personal_apps/`. Run vitest for radar with `-c vite.radar.config.ts`.
- Existing pytest failures in `tests/test_gym_ownership.py`, `tests/test_gym_exercise_ownership.py` and `tests/test_gym_routes_smoke.py` are pre-existing dev-database state. Ignore them; do not "fix" them.

---

### Task 1: The table

**Files:**
- Modify: `personal_apps/models.py` (add the model beside the other `Radar*` models)
- Create: `personal_apps/migrations/versions/<generated>_add_radar_daily_closes.py`
- Test: `personal_apps/tests/test_radar_models.py`

**Interfaces:**
- Produces: `models.RadarDailyClose` with columns `ticker`, `close_date`, `close`, `fetched_at`.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_models.py`:

```python
def test_a_daily_close_is_unique_per_ticker_and_date():
    """One close per ticker per trading day. A second write for the same day
    replaces it rather than accumulating -- the provider restates recent bars,
    and duplicates would silently double the history a sparkline draws."""
    import datetime as dt
    import decimal
    from app import app as flask_app
    from extensions import db
    from models import RadarDailyClose

    with flask_app.app_context():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker == 'MDLZZ').delete(synchronize_session=False)
        db.session.commit()

        db.session.add(RadarDailyClose(
            ticker='MDLZZ', close_date=dt.date(2026, 8, 21),
            close=decimal.Decimal('12.3400'), fetched_at=dt.datetime(2026, 8, 22)))
        db.session.commit()

        stored = RadarDailyClose.query.filter_by(ticker='MDLZZ').one()
        assert stored.close_date == dt.date(2026, 8, 21)
        assert float(stored.close) == 12.34

        RadarDailyClose.query.filter(
            RadarDailyClose.ticker == 'MDLZZ').delete(synchronize_session=False)
        db.session.commit()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_radar_models.py::test_a_daily_close_is_unique_per_ticker_and_date -v`
Expected: FAIL with `ImportError: cannot import name 'RadarDailyClose' from 'models'`

- [ ] **Step 3: Add the model**

In `personal_apps/models.py`, directly after the `RadarQuote` class:

```python
class RadarDailyClose(db.Model):
    """One daily close per ticker. What the board's price history draws.

    Separate from RadarQuote, which is an intraday snapshot taken every five
    minutes and pruned. This is one row per trading day, kept for a year, and
    it answers a different question: not "did the price move while people were
    talking" but "what state is this stock in".

    Not partitioned, unlike radar_buckets. A year of closes for a few thousand
    tickers is small, and rows are replaced by date rather than accumulated.
    """
    __tablename__ = 'radar_daily_closes'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    ticker     = db.Column(db.String(12, collation='utf8mb4_bin'),
                           primary_key=True)
    close_date = db.Column(db.Date, primary_key=True)
    close      = db.Column(db.Numeric(18, 4), nullable=False)
    fetched_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
```

- [ ] **Step 4: Generate and trim the migration**

Run: `set FLASK_APP=app.py && flask db migrate -m "add radar daily closes"`

Open the generated file in `migrations/versions/`. Delete every operation that
is not `create_table('radar_daily_closes', ...)` / `drop_table`. Autogenerate
compares the whole metadata against a dev database that may drift, and an
unrelated `alter_column` shipping to MariaDB is how a deploy breaks halfway.
Note from prior experience: **DDL commits even when a later statement in the
same migration fails**, so a migration must contain only what it intends.

- [ ] **Step 5: Apply it and confirm the schema**

Run: `flask db upgrade`
Run: `python -m pytest tests/test_radar_models.py::test_a_daily_close_is_unique_per_ticker_and_date -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions personal_apps/tests/test_radar_models.py
git commit -m "feat(radar): store daily closes"
```

---

### Task 2: Reading and writing history

**Files:**
- Create: `personal_apps/features/radar/history.py`
- Test: `personal_apps/tests/test_radar_history.py`

**Interfaces:**
- Consumes: `models.RadarDailyClose` (Task 1); `prices.twelvedata.TwelveDataProvider.daily_closes(symbol, days) -> list[tuple[date, Decimal]]` oldest first.
- Produces:
  - `HISTORY_DAYS = 260`
  - `record_closes(ticker, closes, now) -> int` — upsert, returns rows written
  - `closes_for(tickers, days=HISTORY_DAYS, today=None) -> dict[str, list[tuple[date, Decimal]]]` oldest first
  - `tickers_needing_history(candidates, today, stale_after_days=2) -> list[str]` — missing first, then stale, preserving the order of `candidates`
  - `fetch_into_store(provider, tickers, now) -> int` — tickers stored

- [ ] **Step 1: Write the failing tests**

Create `personal_apps/tests/test_radar_history.py`:

```python
"""Daily closes: the price context a first-time ticker is judged against.

The rules being pinned are about spending a scarce budget well. The provider
allows eight requests a minute, so which tickers get asked about, and how
often, is the whole design -- a job that re-asks for Friday's close all
weekend never gets to the ticker that appeared an hour ago.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import history
from models import RadarDailyClose

TODAY = dt.date(2026, 8, 21)
NOW = dt.datetime(2026, 8, 21, 20, 0, 0)
PREFIX = 'HS'


@pytest.fixture()
def clean():
    def wipe():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def store(ticker, days_back, price='10.00'):
    db.session.add(RadarDailyClose(
        ticker=ticker, close_date=TODAY - dt.timedelta(days=days_back),
        close=decimal.Decimal(price), fetched_at=NOW))


class FakeProvider:
    """Records what it was asked for; answers from a fixed script."""

    def __init__(self, script):
        self.script = script
        self.asked = []

    def daily_closes(self, symbol, days):
        self.asked.append((symbol, days))
        return self.script.get(symbol, [])


def test_closes_are_returned_oldest_first(clean):
    store(f'{PREFIX}A', 2, '11.00')
    store(f'{PREFIX}A', 1, '12.00')
    store(f'{PREFIX}A', 0, '13.00')
    db.session.commit()

    series = history.closes_for([f'{PREFIX}A'], today=TODAY)[f'{PREFIX}A']

    assert [float(close) for _, close in series] == [11.0, 12.0, 13.0]


def test_only_the_requested_span_comes_back(clean):
    store(f'{PREFIX}A', 400, '1.00')
    store(f'{PREFIX}A', 5, '2.00')
    db.session.commit()

    series = history.closes_for([f'{PREFIX}A'], days=30, today=TODAY)[f'{PREFIX}A']

    assert [float(close) for _, close in series] == [2.0]


def test_a_ticker_with_nothing_stored_is_absent_not_empty(clean):
    """Absent and empty are different facts downstream: one becomes a null
    payload that draws a dashed rule, the other would draw a flat line."""
    assert history.closes_for([f'{PREFIX}A'], today=TODAY) == {}


def test_a_ticker_with_no_history_is_asked_about_first(clean):
    store(f'{PREFIX}B', 0)
    db.session.commit()

    due = history.tickers_needing_history(
        [f'{PREFIX}B', f'{PREFIX}A'], today=TODAY)

    assert due[0] == f'{PREFIX}A'


def test_fridays_close_is_not_stale_on_monday(clean):
    """Two days, not one. The provider has nothing newer to give over a
    weekend, so a one-day rule would spend every Monday-morning cycle
    re-fetching rows that cannot have changed."""
    store(f'{PREFIX}A', 2)
    db.session.commit()

    assert history.tickers_needing_history([f'{PREFIX}A'], today=TODAY) == []


def test_a_genuinely_old_series_is_refreshed(clean):
    store(f'{PREFIX}A', 9)
    db.session.commit()

    assert history.tickers_needing_history([f'{PREFIX}A'], today=TODAY) == [f'{PREFIX}A']


def test_fetching_replaces_a_day_rather_than_duplicating_it(clean):
    """Providers restate recent bars. Appending would double every point the
    sparkline draws for the overlapping days."""
    store(f'{PREFIX}A', 0, '10.00')
    db.session.commit()

    provider = FakeProvider({f'{PREFIX}A': [(TODAY, decimal.Decimal('99.00'))]})
    history.fetch_into_store(provider, [f'{PREFIX}A'], NOW)

    rows = RadarDailyClose.query.filter_by(ticker=f'{PREFIX}A').all()
    assert len(rows) == 1
    assert float(rows[0].close) == 99.0


def test_a_provider_returning_nothing_leaves_what_we_had(clean):
    """Erasing a year of history because one call failed would blank the
    column for a ticker until the next cycle."""
    store(f'{PREFIX}A', 1, '10.00')
    db.session.commit()

    history.fetch_into_store(FakeProvider({}), [f'{PREFIX}A'], NOW)

    assert RadarDailyClose.query.filter_by(ticker=f'{PREFIX}A').count() == 1


def test_a_full_year_is_requested(clean):
    provider = FakeProvider({})
    history.fetch_into_store(provider, [f'{PREFIX}A'], NOW)

    assert provider.asked == [(f'{PREFIX}A', history.HISTORY_DAYS)]
    assert history.HISTORY_DAYS >= 252
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_radar_history.py -v`
Expected: FAIL with `ImportError: cannot import name 'history' from 'features.radar'`

- [ ] **Step 3: Write the module**

Create `personal_apps/features/radar/history.py`:

```python
# personal_apps/features/radar/history.py
"""Daily closes: what a ticker's price has been doing, over months.

Divergence measures hours, which is the right question about a stock you
already know and the wrong one the first time you see a ticker. Flat over four
hours while down 80% on the year and flat over four hours having tripled since
June are opposite situations behind an identical score. This is the context
that separates them -- read beside the score, never folded into it.

The provider allows eight requests a minute, so the interesting decision here
is not how to fetch but WHOM to ask about. A ticker with no history at all is
the one the board cannot describe, so it goes first.
"""
import collections
import datetime as dt

from extensions import db
from models import RadarDailyClose

# A full trading year. 252 is the usual count; 260 covers a leap of holidays
# without a second request.
HISTORY_DAYS = 260

# How old the newest stored close may be before it is worth re-asking.
#
# Two days, not one. Over a weekend the provider has nothing newer than
# Friday, so a one-day rule would mark every ticker stale all weekend and
# spend the entire per-cycle budget re-fetching rows that cannot change --
# starving the tickers with no history at all, which are the only ones the
# board actually cannot draw.
STALE_AFTER_DAYS = 2


def record_closes(ticker, closes, now):
    """Upsert (date, close) pairs for one ticker. Returns rows written.

    Upsert rather than append: providers restate recent bars, and a second
    write for the same day must replace it or every overlapping point would be
    drawn twice.
    """
    if not closes:
        return 0

    existing = {row.close_date: row for row in RadarDailyClose.query.filter(
        RadarDailyClose.ticker == ticker,
        RadarDailyClose.close_date.in_([day for day, _ in closes])).all()}

    for day, close in closes:
        row = existing.get(day)
        if row is None:
            db.session.add(RadarDailyClose(
                ticker=ticker, close_date=day, close=close, fetched_at=now))
        else:
            row.close = close
            row.fetched_at = now

    db.session.commit()
    return len(closes)


def closes_for(tickers, days=HISTORY_DAYS, today=None):
    """{ticker: [(date, close)]} oldest first, for tickers that have any.

    A ticker with nothing stored is ABSENT from the result rather than mapped
    to an empty list. The two mean different things downstream -- absent
    becomes a null payload and draws a dashed "not known" rule, while an empty
    series would draw a flat line and assert a price that held steady.
    """
    if not tickers:
        return {}

    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)

    rows = (db.session.query(RadarDailyClose.ticker,
                             RadarDailyClose.close_date,
                             RadarDailyClose.close)
            .filter(RadarDailyClose.ticker.in_(list(tickers)),
                    RadarDailyClose.close_date >= since,
                    RadarDailyClose.close_date <= today)
            .order_by(RadarDailyClose.close_date.asc()).all())

    series = collections.defaultdict(list)
    for ticker, day, close in rows:
        series[ticker].append((day, close))
    return dict(series)


def tickers_needing_history(candidates, today, stale_after_days=STALE_AFTER_DAYS):
    """Which of `candidates` to spend requests on, most urgent first.

    Missing before stale, each keeping the caller's order -- the caller passes
    them loudest first, and among tickers we cannot draw at all the loudest is
    the one most likely to be looked at next.
    """
    if not candidates:
        return []

    newest = dict(db.session.query(
        RadarDailyClose.ticker, db.func.max(RadarDailyClose.close_date))
        .filter(RadarDailyClose.ticker.in_(list(candidates)))
        .group_by(RadarDailyClose.ticker).all())

    cutoff = today - dt.timedelta(days=stale_after_days)
    missing = [t for t in candidates if t not in newest]
    stale = [t for t in candidates if t in newest and newest[t] < cutoff]
    return missing + stale


def fetch_into_store(provider, tickers, now):
    """Fetch a year of closes for each ticker and store it. Returns how many
    tickers came back with anything.

    A provider answering nothing leaves the stored rows alone. Blanking a
    year of history because one call failed would empty the column for that
    ticker until the next cycle, which is worse than showing yesterday's.
    """
    stored = 0
    for ticker in tickers:
        closes = provider.daily_closes(ticker, HISTORY_DAYS)
        if not closes:
            continue
        record_closes(ticker, closes, now)
        stored += 1
    return stored
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_radar_history.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/history.py personal_apps/tests/test_radar_history.py
git commit -m "feat(radar): keep a year of daily closes, and spend requests on the tickers we cannot draw"
```

---

### Task 3: Volatility reads the table

**Files:**
- Modify: `personal_apps/features/radar/quotes.py:135-159` (`refresh_sigma`)
- Modify: `personal_apps/run_radar_ingest.py` (`refresh_volatility` drops its provider argument)
- Test: `personal_apps/tests/test_radar_quotes.py`, `personal_apps/tests/test_radar_daemon.py`

**Interfaces:**
- Consumes: `history.closes_for` (Task 2).
- Produces: `quotes.refresh_sigma(tickers, now) -> int` — **the `provider` parameter is gone**; `run_radar_ingest.refresh_volatility(now_utc, limit=SIGMA_LIMIT)` — **its `provider` parameter is gone too**.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_quotes.py`:

```python
def test_sigma_is_computed_from_stored_closes_without_a_provider():
    """refresh_sigma used to fetch 35 closes per ticker every twelve hours and
    throw them away. The history job already stores a year of them, so the
    second fetch was pure waste -- and on an eight-request-a-minute budget,
    waste that competed with the tickers the board cannot draw at all."""
    import datetime as dt
    import decimal
    from app import app as flask_app
    from extensions import db
    from features.radar import quotes
    from models import RadarDailyClose, TickerUniverse

    today = dt.date(2026, 8, 21)
    now = dt.datetime(2026, 8, 21, 20, 0, 0)

    with flask_app.app_context():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker == 'QSIGZ').delete(synchronize_session=False)
        TickerUniverse.query.filter_by(symbol='QSIGZ').delete(
            synchronize_session=False)
        db.session.add(TickerUniverse(symbol='QSIGZ', name='Sigma Test',
                                      first_seen=dt.datetime(2020, 1, 1)))
        for offset in range(20):
            db.session.add(RadarDailyClose(
                ticker='QSIGZ', close_date=today - dt.timedelta(days=offset),
                close=decimal.Decimal('100') + decimal.Decimal(offset % 3),
                fetched_at=now))
        db.session.commit()

        updated = quotes.refresh_sigma(['QSIGZ'], now)

        assert updated == 1
        row = TickerUniverse.query.filter_by(symbol='QSIGZ').one()
        assert row.daily_sigma is not None and row.daily_sigma > 0
        assert row.sigma_refreshed_at == now

        RadarDailyClose.query.filter(
            RadarDailyClose.ticker == 'QSIGZ').delete(synchronize_session=False)
        TickerUniverse.query.filter_by(symbol='QSIGZ').delete(
            synchronize_session=False)
        db.session.commit()


def test_a_ticker_with_too_little_history_keeps_its_old_sigma():
    """No history is not a volatility of zero, and a zero sigma downstream
    turns every price move into an infinite z."""
    import datetime as dt
    from app import app as flask_app
    from extensions import db
    from features.radar import quotes
    from models import RadarDailyClose, TickerUniverse

    now = dt.datetime(2026, 8, 21, 20, 0, 0)
    with flask_app.app_context():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker == 'QTHINZ').delete(synchronize_session=False)
        TickerUniverse.query.filter_by(symbol='QTHINZ').delete(
            synchronize_session=False)
        db.session.add(TickerUniverse(symbol='QTHINZ', name='Thin',
                                      first_seen=dt.datetime(2020, 1, 1),
                                      daily_sigma=0.05))
        db.session.commit()

        assert quotes.refresh_sigma(['QTHINZ'], now) == 0
        assert TickerUniverse.query.filter_by(symbol='QTHINZ').one().daily_sigma == 0.05

        TickerUniverse.query.filter_by(symbol='QTHINZ').delete(
            synchronize_session=False)
        db.session.commit()
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_radar_quotes.py::test_sigma_is_computed_from_stored_closes_without_a_provider -v`
Expected: FAIL with `TypeError: refresh_sigma() missing 1 required positional argument`

- [ ] **Step 3: Rewrite refresh_sigma**

Replace `refresh_sigma` in `personal_apps/features/radar/quotes.py` entirely:

```python
def refresh_sigma(tickers, now):
    """Recompute and store daily volatility from stored closes. Returns how
    many were updated.

    Reads radar_daily_closes rather than calling the provider. It used to
    fetch thirty-five closes per ticker every twelve hours and discard them;
    the history job now keeps a year of the same data, and on an
    eight-request-a-minute budget the duplicate fetch competed directly with
    the tickers that have no history at all.

    A ticker without enough stored history keeps whatever sigma it had. No
    history is not a volatility of zero, and a zero sigma downstream turns
    every price move into an infinite z.
    """
    from models import TickerUniverse

    from . import history

    stored = history.closes_for(tickers, days=history.HISTORY_DAYS)

    updated = 0
    for ticker in tickers:
        sigma = daily_sigma(stored.get(ticker, []))
        if sigma is None:
            continue

        row = TickerUniverse.query.filter_by(symbol=ticker).one_or_none()
        if row is None:
            continue
        row.daily_sigma = sigma
        row.sigma_refreshed_at = now
        updated += 1

    db.session.commit()
    return updated
```

- [ ] **Step 4: Update the daemon's wrapper**

In `personal_apps/run_radar_ingest.py`, replace `refresh_volatility` and `_scheduled_volatility`:

```python
def refresh_volatility(now_utc, limit=SIGMA_LIMIT):
    """Recompute daily sigma for the tickers on the board.

    No provider argument any more: sigma is computed from the closes the
    history job already stored (features/radar/history.py).
    """
    tickers = _loud_tickers(now_utc, limit)
    if not tickers:
        return 0
    try:
        return quotes.refresh_sigma(tickers, now_utc.replace(tzinfo=None))
    except Exception:
        logger.exception('radar volatility refresh failed')
        return 0


def _scheduled_volatility():
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        updated = refresh_volatility(now)
    logger.info('radar volatility refreshed %d tickers', updated)
```

Leave `from features.radar.prices import twelvedata as twelvedata_provider`
in place. It has no caller between this task and the next, which looks like
dead code for exactly one commit -- but Task 4's history job is its new owner,
and removing it here only to restore it there churns the file across a review
boundary for no gain.

- [ ] **Step 5: Fix the daemon tests that pass a provider**

In `personal_apps/tests/test_radar_daemon.py`, every call of the form
`daemon.refresh_volatility(_utc(2026, 8, 21, 14), object())` loses its second
argument and becomes `daemon.refresh_volatility(_utc(2026, 8, 21, 14))`. The
tests that monkeypatch `daemon.quotes.refresh_sigma` must patch a two-argument
function: `lambda tickers, now: len(tickers)`.

- [ ] **Step 6: Run the affected suites**

Run: `python -m pytest tests/test_radar_quotes.py tests/test_radar_daemon.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/radar/quotes.py personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_quotes.py personal_apps/tests/test_radar_daemon.py
git commit -m "refactor(radar): compute sigma from stored closes instead of refetching them"
```

---

### Task 4: The history job

**Files:**
- Modify: `personal_apps/run_radar_ingest.py`
- Test: `personal_apps/tests/test_radar_daemon.py`

**Interfaces:**
- Consumes: `history.tickers_needing_history`, `history.fetch_into_store` (Task 2); `_loud_tickers(now, limit)` (existing).
- Produces: `run_radar_ingest.refresh_history(now_utc, provider, limit=HISTORY_LIMIT) -> int`, job id `radar_history`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_daemon.py`:

```python
def test_history_is_fetched_for_tickers_that_have_none(monkeypatch):
    seen = {}

    def fake_fetch(provider, tickers, now):
        seen['tickers'] = list(tickers)
        return len(tickers)

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: ['BBB'])
    monkeypatch.setattr(daemon.history, 'fetch_into_store', fake_fetch)

    assert daemon.refresh_history(_utc(2026, 8, 21, 14), object()) == 1
    assert seen['tickers'] == ['BBB']


def test_the_history_job_respects_its_per_cycle_cap(monkeypatch):
    """Eight requests a minute is the real ceiling, not the daily quota. A
    cycle that asked for everything would trip it and lose the whole batch."""
    asked = {}

    def fake_fetch(provider, tickers, now):
        asked['n'] = len(tickers)
        return len(tickers)

    many = [f'T{n}' for n in range(100)]
    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: many)
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: list(candidates))
    monkeypatch.setattr(daemon.history, 'fetch_into_store', fake_fetch)

    daemon.refresh_history(_utc(2026, 8, 21, 14), object(), limit=20)
    assert asked['n'] == 20


def test_a_failing_history_provider_does_not_kill_the_cycle(monkeypatch):
    def boom(provider, tickers, now):
        raise RuntimeError('provider down')

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: ['AAA'])
    monkeypatch.setattr(daemon.history, 'fetch_into_store', boom)

    assert daemon.refresh_history(_utc(2026, 8, 21, 14), object()) == 0


def test_nothing_due_spends_no_requests(monkeypatch):
    called = {'n': 0}

    def counting(provider, tickers, now):
        called['n'] += 1
        return 0

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: [])
    monkeypatch.setattr(daemon.history, 'fetch_into_store', counting)

    daemon.refresh_history(_utc(2026, 8, 21, 14), object())
    assert called['n'] == 0


def test_the_daemon_schedules_a_history_job():
    """The profile job shipped unscheduled and nothing caught it, because the
    defect was an absence. Assert the registration itself."""
    import inspect
    source = inspect.getsource(daemon.main)

    assert "id='radar_history'" in source
    assert '_scheduled_history' in source
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_daemon.py -k history -v`
Expected: FAIL with `AttributeError: module 'run_radar_ingest' has no attribute 'history'`

- [ ] **Step 3: Add the job**

In `personal_apps/run_radar_ingest.py`, add `history` to the radar import:

```python
from features.radar import (
    history, ingest, market_calendar, quotes, retention, scheduling, scoring,
    universe)
```

Re-add the Twelve Data import removed in Task 3 — the history job is now its
only caller:

```python
from features.radar.prices import twelvedata as twelvedata_provider
```

Add the constants next to `PROFILE_LIMIT`:

```python
# Daily closes for the price-history column. The binding constraint is Twelve
# Data's EIGHT REQUESTS PER MINUTE, not its 800/day quota: 20 per five-minute
# cycle is four a minute, leaving room for the quote job alongside.
HISTORY_LIMIT = 20
HISTORY_INTERVAL_MINUTES = 5
```

Add the functions before `_scheduled_volatility`:

```python
def refresh_history(now_utc, provider, limit=HISTORY_LIMIT):
    """Fetch a year of daily closes for board tickers that need them.

    Returns how many tickers came back with data. Ordering is the history
    module's decision -- missing before stale -- because a ticker the board
    cannot draw at all is worth more than a fresher copy of one it can.
    """
    candidates = _loud_tickers(now_utc, limit * 5)
    if not candidates:
        return 0

    naive = now_utc.replace(tzinfo=None)
    try:
        due = history.tickers_needing_history(candidates, naive.date())[:limit]
        if not due:
            return 0
        return history.fetch_into_store(provider, due, naive)
    except Exception:
        logger.exception('radar history refresh failed')
        return 0


def _scheduled_history():
    now = dt.datetime.now(dt.timezone.utc)
    provider = twelvedata_provider.TwelveDataProvider(
        twelvedata_provider.TwelveDataHttp())
    with app.app_context():
        stored = refresh_history(now, provider)
    logger.info('radar history stored %d tickers', stored)
```

Register it in `main()`, after the profiles job:

```python
    # One minute in, ahead of everything else that costs requests: a ticker
    # with no stored history is the only one the board literally cannot draw.
    scheduler.add_job(_scheduled_history, 'interval',
                      minutes=HISTORY_INTERVAL_MINUTES, id='radar_history',
                      max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=1))
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_radar_daemon.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): fetch daily closes, tickers we cannot draw first"
```

---


### Task 5: One aligned series per row

**Files:**
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Test: `personal_apps/tests/test_radar_board.py`, `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Consumes: `history.closes_for` (Task 2).
- Produces: `board.CHART_DAYS = 365`; `board.Chart(start: date, closes: list, chatter: list)`; `BoardRow.chart: Chart | None`; JSON `chart: {"from", "closes", "chatter"} | null`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_board.py`:

```python
def test_the_chart_aligns_price_and_chatter_on_calendar_days(clean):
    """Price has ~252 trading days a year, chatter has 365. Positioning both
    by array index would drift them over a hundred days apart by December."""
    import decimal
    from models import RadarDailyClose

    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    for offset in (0, 1, 2):
        db.session.add(RadarDailyClose(
            ticker=f'{PREFIX}A', close_date=NOW.date() - dt.timedelta(days=offset),
            close=decimal.Decimal('10') + decimal.Decimal(offset), fetched_at=NOW))
    db.session.commit()

    chart = only(board.build(['bluesky'], NOW), f'{PREFIX}A').chart

    assert len(chart.closes) == len(chart.chatter) == board.CHART_DAYS
    assert (NOW.date() - chart.start).days == board.CHART_DAYS - 1
    # Today is the last index of both arrays, so the two line up by date.
    assert float(chart.closes[-1]) == 10.0
    assert chart.chatter[-1] == 10


def test_a_day_the_market_did_not_trade_is_null_not_carried_forward(clean):
    """Null means no trade happened. The client draws the line across it;
    repeating the previous close here would invent a print."""
    import decimal
    from models import RadarDailyClose

    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    db.session.add(RadarDailyClose(
        ticker=f'{PREFIX}A', close_date=NOW.date() - dt.timedelta(days=3),
        close=decimal.Decimal('10'), fetched_at=NOW))
    db.session.commit()

    chart = only(board.build(['bluesky'], NOW), f'{PREFIX}A').chart

    assert chart.closes[-1] is None
    assert float(chart.closes[-4]) == 10.0


def test_days_before_ingest_began_have_no_chatter_at_all(clean):
    """Not zero. We were not watching, and a zero bar would claim a silence we
    never observed -- the same rule the hourly series already follows."""
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    db.session.commit()

    chart = only(board.build(['bluesky'], NOW), f'{PREFIX}A').chart

    assert chart.chatter[0] is None
    assert chart.chatter[-1] == 10


def test_a_ticker_with_no_stored_closes_has_no_chart(clean):
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    db.session.commit()

    assert only(board.build(['bluesky'], NOW), f'{PREFIX}A').chart is None
```

Append to `personal_apps/tests/test_radar_api.py`:

```python
def test_the_chart_serializes_as_two_aligned_arrays(client):
    payload = json.loads(client.get('/radar/api/board').data)

    for row in payload['rows']:
        chart = row['chart']
        if chart is None:
            continue
        assert set(chart) == {'from', 'closes', 'chatter'}
        assert len(chart['closes']) == len(chart['chatter'])
        assert chart['from'].count('-') == 2
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_board.py -k chart -v`
Expected: FAIL with `AttributeError: 'BoardRow' object has no attribute 'chart'`

- [ ] **Step 3: Build the aligned series**

In `personal_apps/features/radar/board.py`, add `history` to the imports
(`from . import history, leaderboard, market_calendar`) and add near the top:

```python
# One calendar year -- the chart's widest span.
CHART_DAYS = 365


@dataclasses.dataclass
class Chart:
    """Price and chatter over the same calendar days.

    Both arrays are CHART_DAYS long and share `start`, so index i is the same
    date in each. That alignment is why this is one structure rather than two:
    a year holds ~252 trading days and 365 calendar days, and positioning each
    by its own index would drift them apart by over a hundred days.

    `closes[i]` is None where the market did not trade -- weekends, holidays.
    `chatter[i]` is None where we were not yet watching. Different absences,
    drawn differently: the price line spans its gaps, the chatter bars do not.
    """
    start: dt.date
    closes: list
    chatter: list
```

Add beside `_hourly_counts`:

```python
def _daily_counts(tickers, sources, start, now):
    """Pooled mention count per (ticker, calendar day).

    From buckets, which are retained forever -- unlike posts, which prune at
    30 days. That is what lets the chart's long spans fill in over time with
    no new collection.
    """
    if not tickers:
        return {}

    rows = (db.session.query(RadarBucketSource.ticker,
                             sa.func.date(RadarBucketSource.bucket_start),
                             sa.func.sum(RadarBucketSource.mention_count))
            .filter(RadarBucketSource.ticker.in_(list(tickers)),
                    RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now)
            .group_by(RadarBucketSource.ticker,
                      sa.func.date(RadarBucketSource.bucket_start)).all())

    totals = {}
    for ticker, day, count in rows:
        # MySQL returns DATE() as a date object; MariaDB has been seen to
        # return a string. Normalise rather than trusting the driver.
        if isinstance(day, str):
            day = dt.date.fromisoformat(day)
        totals[(ticker, day)] = int(count or 0)
    return totals


def _first_watched_day(sources, start, now):
    """Earliest calendar day any bucket exists for. Before it, chatter is
    unknown rather than zero."""
    earliest = (db.session.query(sa.func.min(RadarBucketSource.bucket_start))
                .filter(RadarBucketSource.source.in_(list(sources)),
                        RadarBucketSource.bucket_start >= start).scalar())
    return earliest.date() if earliest else None


def _chart_for(ticker, start, days, closes_by_day, counts, watched_from):
    """One Chart, both arrays indexed by calendar day from `start`."""
    closes, chatter = [], []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        closes.append(closes_by_day.get(day))
        if watched_from is None or day < watched_from:
            chatter.append(None)
        else:
            chatter.append(counts.get((ticker, day), 0))
    return Chart(start=start, closes=closes, chatter=chatter)
```

Add the field to `BoardRow`, after `price_series`:

```python
    # Price and chatter over one calendar year, aligned. None when the ticker
    # has no stored closes at all.
    chart: object
```

In `build()`, after `prices = _price_series(...)`:

```python
    chart_start = now.date() - dt.timedelta(days=CHART_DAYS - 1)
    chart_from = dt.datetime.combine(chart_start, dt.time.min)
    stored_closes = history.closes_for(tickers, days=CHART_DAYS,
                                       today=now.date())
    daily_counts = _daily_counts(tickers, sources, chart_from, now)
    watched_from = _first_watched_day(sources, chart_from, now)
```

And in the `BoardRow(...)` construction, after `price_series=...`:

```python
        chart=(_chart_for(row.ticker, chart_start, CHART_DAYS,
                          dict(stored_closes[row.ticker]), daily_counts,
                          watched_from)
               if row.ticker in stored_closes else None),
```

- [ ] **Step 4: Serialize it**

In `personal_apps/features/radar/routes/api.py`, add to `_row()` after the
`price_series` entry:

```python
        'chart': _chart(entry.chart),
```

And beside `_decimal_or_none`:

```python
def _chart(chart):
    """{'from', 'closes', 'chatter'} or null, both arrays calendar-aligned.

    365 entries each, mostly literal nulls -- about 250KB across a full board
    and roughly 30KB once nginx gzips it (7.8x measured on coc_stats). Sending
    the year whole is what makes the span switch instant: the client already
    holds every span it can show.
    """
    if chart is None:
        return None
    return {
        'from': chart.start.isoformat(),
        'closes': [float(c) if c is not None else None for c in chart.closes],
        'chatter': chart.chatter,
    }
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_radar_board.py tests/test_radar_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/board.py personal_apps/features/radar/routes/api.py personal_apps/tests/test_radar_board.py personal_apps/tests/test_radar_api.py
git commit -m "feat(radar): align a year of price and chatter on one calendar axis"
```

---

### Task 6: Drawing two series over any span

**Files:**
- Modify: `personal_apps/static/radar/src/types.ts`
- Modify: `personal_apps/static/radar/src/board/geometry.ts`
- Test: `personal_apps/static/radar/src/board/geometry.test.ts`

**Interfaces:**
- Produces, in `types.ts`: `Chart = { from: string; closes: (number|null)[]; chatter: (number|null)[] }`, `ChartSpan = '24h' | '1M' | '3M' | '1Y'`, `Row.chart: Chart | null`.
- Produces, in `geometry.ts`: `SPAN_DAYS`, `sliceChart(chart, span) -> Chart`, `pricePath(closes, box) -> string`, `dailyBars(chatter, box, yMax) -> Bar[]`, `chartRose(closes) -> boolean`, `peakOf(values) -> number`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/static/radar/src/board/geometry.test.ts` (add the new
names to the existing `./geometry` import):

```ts
describe('the chart span', () => {
  const chart = {
    from: '2025-08-23',
    closes: Array.from({ length: 365 }, (_, i) => (i % 7 < 5 ? 100 + i : null)),
    chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
  }

  it('slices both series to the same days', () => {
    const month = sliceChart(chart, '1M')

    expect(month.closes).toHaveLength(30)
    expect(month.chatter).toHaveLength(30)
  })

  it('moves the start date with the slice', () => {
    // Otherwise every span would claim to begin a year ago.
    expect(sliceChart(chart, '1Y').from).toBe('2025-08-23')
    expect(sliceChart(chart, '1M').from).not.toBe('2025-08-23')
  })

  it('returns everything it has when the series is shorter than the span', () => {
    const young = { from: '2026-08-01', closes: [1, 2, 3], chatter: [1, 2, 3] }

    expect(sliceChart(young, '1Y').closes).toEqual([1, 2, 3])
  })
})

describe('the price line across a closed market', () => {
  it('draws through a gap rather than breaking at it', () => {
    // A weekend is not missing data about the price, it is a weekend. The
    // chatter line breaks at its gaps; this one must not, or a year renders
    // as 52 fragments.
    const path = pricePath([10, null, null, 13], BOX)

    expect(path.split('M')).toHaveLength(2)
    expect(path.match(/L/g) ?? []).toHaveLength(1)
  })

  it('keeps calendar position, not the order of surviving points', () => {
    const path = pricePath([10, null, null, 13], BOX)
    const xs = [...path.matchAll(/[ML]([\d.]+),/g)].map((m) => Number(m[1]))

    expect(xs[0]).toBe(0)
    expect(xs[1]).toBeCloseTo(BOX.width)
  })

  it('draws nothing from fewer than two real closes', () => {
    expect(pricePath([null, null], BOX)).toBe('')
    expect(pricePath([10, null], BOX)).toBe('')
  })

  it('stays in its band when one is set, leaving the floor to the bars', () => {
    const banded = pricePath([100, 110], { ...BOX, priceBand: 0.5 })
    const ys = [...banded.matchAll(/[ML][\d.]+,([\d.]+)/g)].map((m) => Number(m[1]))

    expect(Math.max(...ys)).toBeLessThanOrEqual(BOX.height * 0.5)
  })

  it('reads direction across the span, ignoring untraded days', () => {
    expect(chartRose([100, null, 50])).toBe(false)
    expect(chartRose([50, null, 100])).toBe(true)
    expect(chartRose([null, null])).toBe(true)
  })
})

describe('daily chatter bars', () => {
  it('emits nothing for a day nobody was watching', () => {
    expect(dailyBars([null, null, 4], BOX, 4)).toHaveLength(1)
  })

  it('emits nothing for a measured zero, and something for a one', () => {
    const bars = dailyBars([0, 1], BOX, 4)

    expect(bars).toHaveLength(1)
    expect(bars[0]!.ratio).toBeCloseTo(0.25)
  })

  it('ignores nulls when finding the peak', () => {
    expect(peakOf([null, 7, null, 3])).toBe(7)
    expect(peakOf([null, null])).toBe(0)
  })
})
```

- [ ] **Step 2: Run and watch them fail**

Run: `npx vitest run -c vite.radar.config.ts geometry`
Expected: FAIL with "sliceChart is not exported"

- [ ] **Step 3: Add the types**

In `personal_apps/static/radar/src/types.ts`, before `interface Row`:

```ts
/** Price and chatter over the same calendar days, sharing `from`.
 *
 *  `closes[i]` null means the market did not trade that day -- the line is
 *  drawn across it. `chatter[i]` null means we were not watching yet -- no bar
 *  is drawn at all. Two different absences, deliberately not collapsed. */
export interface Chart {
  from: string
  closes: (number | null)[]
  chatter: (number | null)[]
}

export type ChartSpan = '24h' | '1M' | '3M' | '1Y'
```

Inside `Row`, after `price_series`:

```ts
  /** null when the ticker has no stored closes at all. */
  chart: Chart | null
```

- [ ] **Step 4: Add the geometry**

Append to `personal_apps/static/radar/src/board/geometry.ts`, adding `Chart`
and `ChartSpan` to the type import at the top:

```ts
/** Calendar days per span. '24h' is absent on purpose: that span reads the
 *  hourly `series` the payload already carried, at a resolution the daily
 *  arrays cannot express. */
export const SPAN_DAYS: Record<Exclude<ChartSpan, '24h'>, number> = {
  '1M': 30,
  '3M': 90,
  '1Y': 365,
}

/** The most recent N calendar days of both series, with `from` moved to match.
 *
 *  Slicing both by the same count is what keeps them aligned; moving `from`
 *  is what stops every span claiming to start a year ago. */
export function sliceChart(chart: Chart, span: ChartSpan): Chart {
  const days = span === '24h' ? SPAN_DAYS['1M'] : SPAN_DAYS[span]
  if (chart.closes.length <= days) return chart

  const cut = chart.closes.length - days
  const start = new Date(`${chart.from}T00:00:00Z`)
  start.setUTCDate(start.getUTCDate() + cut)
  return {
    from: start.toISOString().slice(0, 10),
    closes: chart.closes.slice(cut),
    chatter: chart.chatter.slice(cut),
  }
}

/** The price line, drawn ACROSS days the market was shut.
 *
 *  The chatter line breaks at its gaps because a gap there is an hour nobody
 *  measured. A gap here is a weekend: the price did not stop existing, and
 *  breaking at every Saturday would render a year as 52 fragments. Points
 *  keep their calendar index, so a Monday sits three days after the Friday
 *  before it whether or not anything traded between. */
export function pricePath(closes: (number | null)[], box: Box): string {
  const real = closes
    .map((value, index) => ({ value, index }))
    .filter((p): p is { value: number; index: number } => p.value !== null)
  if (real.length < 2) return ''

  const values = real.map((p) => p.value)
  const low = Math.min(...values)
  const span = Math.max(...values) - low || 1
  // priceBand keeps the line in the upper part of the box so the chatter bars
  // growing from the floor can cross it rather than hide under it. The scan
  // cell leaves it unset and uses the full height; the lead card sets 0.5.
  const plotHeight = (box.height - box.pad * 2) * (box.priceBand ?? 1)
  const lastIndex = Math.max(closes.length - 1, 1)

  return real.map((point, n) => {
    const x = (point.index / lastIndex) * box.width
    const y = box.pad + plotHeight - ((point.value - low) / span) * plotHeight
    return `${n ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

/** Highest measured value, ignoring nulls. */
export function peakOf(values: (number | null)[]): number {
  return values.reduce<number>(
    (best, v) => (v !== null && v > best ? v : best), 0)
}

/** One bar per day of chatter, zero-anchored, nothing for a null day. */
export function dailyBars(chatter: (number | null)[], box: Box,
                          yMax: number): Bar[] {
  const top = Math.max(yMax, 1)
  const slot = box.width / Math.max(chatter.length, 1)
  const full = (box.height - box.pad * 2) * (box.barBand ?? 1)
  const bars: Bar[] = []

  chatter.forEach((count, index) => {
    if (count === null || count === 0) return
    const ratio = count / top
    const height = Math.max(ratio * full, 1.2)
    bars.push({
      x: index * slot + slot * 0.15,
      y: box.height - box.pad - height,
      width: Math.max(slot * 0.7, 0.6),
      height,
      ratio,
    })
  })
  return bars
}

/** Whether the span ended higher than it began, ignoring untraded days. */
export function chartRose(closes: (number | null)[]): boolean {
  const real = closes.filter((v): v is number => v !== null)
  const first = real.at(0)
  const last = real.at(-1)
  if (first === undefined || last === undefined) return true
  return last >= first
}
```

- [ ] **Step 5: Run and commit**

Run: `npx vitest run -c vite.radar.config.ts geometry` — PASS
Run: `npx tsc --noEmit` — no output

```bash
git add personal_apps/static/radar/src/types.ts personal_apps/static/radar/src/board/geometry.ts personal_apps/static/radar/src/board/geometry.test.ts
git commit -m "feat(radar): draw price across closed days, chatter only where measured"
```

---

### Task 7: One component, both sizes

**Files:**
- Create: `personal_apps/static/radar/src/board/SpanChart.tsx`
- Modify: `personal_apps/static/radar/src/board/ScanRow.tsx`
- Modify: `personal_apps/static/radar/radar.css`
- Test: `personal_apps/static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Consumes: Task 6's geometry; the existing `chatterRuns`/`peak` for the 24h span.
- Produces: `<SpanChart chart={Chart|null} series={Point[]} span={ChartSpan} box={Box} label={string} />`.

**The track count goes from seven to six.** The chart replaces the existing
chatter column rather than adding beside it, and Mentions merges with Authors.
Nothing gets wider; if you find yourself adding a track, re-read this.

- [ ] **Step 1: Write the failing tests**

Add to the `row()` fixture defaults in
`personal_apps/static/radar/src/board/BoardPage.test.tsx`:

```tsx
    chart: {
      from: '2025-08-23',
      closes: Array.from({ length: 365 }, (_, i) => (i % 7 < 5 ? 100 + i : null)),
      chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
    },
```

Then append:

```tsx
describe('the chart on a row', () => {
  it('shows mentions and people as one column', () => {
    // Merged to pay for the chart column. They answer the same question --
    // how much talk, from how many mouths -- and the lead cards already say
    // them as one sentence.
    const { container } = render(<BoardPage initial={payload()} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(within(scan).getByText('20 / 9')).toBeInTheDocument()
  })

  it('draws chatter only at the 24h span', () => {
    // 24h reads the hourly series. There is no price line at that resolution:
    // daily closes cannot express a day.
    const { container } = render(<BoardPage initial={payload()} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(scan.querySelector('.spark path.chat')).not.toBeNull()
    expect(scan.querySelector('.spark path.px')).toBeNull()
  })

  it('draws both series once a longer span is chosen', async () => {
    const { container } = render(<BoardPage initial={payload()} />)

    await userEvent.click(within(screen.getByRole('group', { name: 'Chart' }))
      .getByRole('button', { name: '1Y' }))

    const scan = container.querySelector('.row') as HTMLElement
    expect(scan.querySelector('.spark path.px')).not.toBeNull()
  })

  it('draws a dashed rule, not a flat line, for a ticker with no closes', async () => {
    const none = payload({
      rows: [row(), row(), row(), row({ ticker: 'DDD', chart: null })],
    })
    const { container } = render(<BoardPage initial={none} />)

    await userEvent.click(within(screen.getByRole('group', { name: 'Chart' }))
      .getByRole('button', { name: '1Y' }))

    const scan = container.querySelector('.row') as HTMLElement
    expect(scan.querySelector('.spark path.px')).toBeNull()
    expect(scan.querySelector('.spark line')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Run and watch them fail**

Run: `npx vitest run -c vite.radar.config.ts BoardPage`
Expected: FAIL — "Unable to find an element with the text: 20 / 9"

- [ ] **Step 3: Write the component**

Create `personal_apps/static/radar/src/board/SpanChart.tsx`:

```tsx
import type { Chart, ChartSpan, Point } from '../types'
import {
  chartRose, chatterRuns, dailyBars, peak, peakOf, pricePath, sliceChart,
  type Box,
} from './geometry'

/** Chatter against price over the selected span, on one axis.
 *
 *  Used at both sizes -- the 124x26 scan cell and the 300x92 lead card --
 *  because they draw the same thing, and a second implementation is a second
 *  place for the two to disagree.
 *
 *  At 24h the source is the hourly `series`, which the daily arrays cannot
 *  express; at every longer span it is the calendar-aligned `chart`. Two code
 *  paths for one component, and an honest split: they are genuinely different
 *  resolutions of different data.
 */
export function SpanChart({ chart, series, span, box, label }: {
  chart: Chart | null
  series: Point[]
  span: ChartSpan
  box: Box
  label: string
}) {
  const hourly = span === '24h'
  const sliced = chart && !hourly ? sliceChart(chart, span) : null

  const runs = hourly ? chatterRuns(series, box, peak(series)) : []
  const bars = sliced ? dailyBars(sliced.chatter, box, peakOf(sliced.chatter)) : []
  const path = sliced ? pricePath(sliced.closes, box) : ''
  const rose = sliced ? chartRose(sliced.closes) : true
  const blank = hourly ? runs.length === 0 : !path && bars.length === 0

  return (
    <div className="spark">
      <svg viewBox={`0 0 ${box.width} ${box.height}`} preserveAspectRatio="none"
           role="img" aria-hidden="true" focusable="false">
        <title>{label}</title>
        {runs.map((d, index) => (
          <path key={index} className="chat" d={d} fill="none"
                stroke="var(--mark)" strokeWidth="1.7" strokeLinejoin="round"
                strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        ))}
        {bars.map((bar, index) => (
          <rect key={index} x={bar.x} y={bar.y} width={bar.width}
                height={bar.height} fill="var(--mark)"
                opacity={(0.34 + 0.66 * bar.ratio).toFixed(2)} />
        ))}
        {path && (
          <path className="px" d={path} fill="none" strokeWidth="1.7"
                strokeLinejoin="round" strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                stroke={rose ? 'var(--up)' : 'var(--down)'} />
        )}
        {blank && (
          // Nothing measured across the whole span. A dashed rule says so; an
          // empty box would read as a price and a silence that held steady.
          <line x1="0" y1={box.height / 2} x2={box.width} y2={box.height / 2}
                stroke="var(--rule)" strokeWidth="1" strokeDasharray="3 3"
                vectorEffect="non-scaling-stroke" />
        )}
      </svg>
    </div>
  )
}
```

- [ ] **Step 4: Use it in the scan row**

In `personal_apps/static/radar/src/board/ScanRow.tsx`: import `SpanChart` and
the `ChartSpan` type, drop the `Sparkline` import, add a `span: ChartSpan`
prop, and replace the `<Sparkline .../>` element with:

```tsx
      <SpanChart chart={row.chart} series={row.series} span={span}
                 box={{ width: 124, height: 26, pad: 3 }}
                 label={`${row.ticker}, ${span}`} />
```

Replace the two count cells with one:

```tsx
      <div className="n">{row.mentions} / {row.authors}</div>
```

and change the mobile caption's second span to read `people`:

```tsx
        <span><b>{row.authors}</b> people</span>
```

`Sparkline.tsx` now has no consumer. Delete the file — a component nobody
renders is one the next person has to work out is dead.

- [ ] **Step 5: Update the grid**

In `personal_apps/static/radar/radar.css`, replace `.cols, .row`'s
`grid-template-columns` with six tracks:

```css
  grid-template-columns:
    minmax(190px, 1.5fr)   /* ticker + name + marks */
    150px                  /* chatter + price chart */
    146px                  /* z triplet             */
    104px                  /* divergence            */
    104px                  /* mentions / people     */
    104px;                 /* price move            */
```

In `@media (max-width: 1080px)`:

```css
    grid-template-columns:
      minmax(150px, 1.4fr) 120px 132px 92px 92px 92px;
```

The 720px block needs no change: it already places `.spark` by grid area, and
the chart reuses that class.

- [ ] **Step 6: Run and commit**

Run: `npx vitest run -c vite.radar.config.ts` — PASS
Run: `npx tsc --noEmit` — no output

```bash
git add personal_apps/static/radar/src personal_apps/static/radar/radar.css
git commit -m "feat(radar): one chart component, chatter and price on one axis"
```

---

### Task 8: The span control, and the cards

**Files:**
- Modify: `personal_apps/static/radar/src/board/BoardPage.tsx`
- Modify: `personal_apps/static/radar/src/board/Controls.tsx`
- Modify: `personal_apps/static/radar/src/board/LeadCard.tsx`
- Modify: `personal_apps/features/radar/board.py`, `personal_apps/features/radar/routes/api.py` (drop `price_series`)
- Test: `personal_apps/static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Produces: board-level `span` state, default `'24h'`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/static/radar/src/board/BoardPage.test.tsx`:

```tsx
describe('the two time controls', () => {
  it('labels them Score and Chart, because they are different questions', () => {
    // One decides what gets ranked, the other what gets drawn. Both called
    // "Window" they would read as one setting that had been split in half.
    render(<BoardPage initial={payload()} />)

    expect(screen.getByText('Score')).toBeInTheDocument()
    expect(screen.getByText('Chart')).toBeInTheDocument()
  })

  it('defaults the chart to 24h, the operational view', () => {
    // Both groups render a 24h button -- Score's longest window and Chart's
    // shortest span -- so this must be scoped or it matches two and throws.
    render(<BoardPage initial={payload()} />)
    const chart = screen.getByRole('group', { name: 'Chart' })

    expect(within(chart).getByRole('button', { name: '24h' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('re-slices the chart without refetching the board', async () => {
    // The whole year is already in the payload; asking the server again for
    // data the client is holding would be a round trip for nothing.
    render(<BoardPage initial={payload()} />)

    await userEvent.click(within(screen.getByRole('group', { name: 'Chart' }))
      .getByRole('button', { name: '3M' }))

    expect(fetch).not.toHaveBeenCalled()
  })

  it('still refetches when the SCORE window changes', async () => {
    // The opposite case, and the reason the two controls stay separate: the
    // score window changes what the server ranks.
    render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('button', { name: '1h' }))

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
  })
})
```

- [ ] **Step 2: Run and watch them fail**

Run: `npx vitest run -c vite.radar.config.ts BoardPage`
Expected: FAIL — no text "Score"

- [ ] **Step 3: Add the control**

In `Controls.tsx`: import the `ChartSpan` type, add
`const SPANS: ChartSpan[] = ['24h', '1M', '3M', '1Y']`, add props
`span: ChartSpan` and `onSpan: (next: ChartSpan) => void`, rename the existing
Window group's label text to `Score` (and its id to `score-lbl`), and add
after that group:

```tsx
      <div className="group">
        <span className="lbl" id="span-lbl">Chart</span>
        <div className="seg" role="group" aria-labelledby="span-lbl">
          {SPANS.map((option) => (
            <button key={option} type="button"
                    aria-pressed={span === option}
                    onClick={() => onSpan(option)}>
              {option}
            </button>
          ))}
        </div>
      </div>
```

Note the `Score` group already renders a `24h` button. Both groups now contain
one, which is why the tests above address them via `aria-pressed` and the
`Score` group's own buttons are asserted by their distinct labels (`1h`).

- [ ] **Step 4: Wire the page**

In `BoardPage.tsx`, add beside `busy`:

```tsx
  // Client-side only: the payload holds the whole year, so switching span
  // costs no request. Defaults to 24h -- the operational "is this spiking
  // now" view, and the only span with a meaningful amount of chatter today.
  const [span, setSpan] = useState<ChartSpan>('24h')
```

Pass `span={span} onSpan={setSpan}` to `Controls`, and `span={span}` to both
`ScanRow` and `LeadCard`.

The heading row must now have **six** cells to match the six grid tracks --
the chatter heading becomes the chart heading, and the two count headings
become one. A seventh would silently shift every column right of it:

```tsx
                <div className="cols" aria-hidden="true">
                  <div>Ticker</div>
                  <div>{span} chart</div>
                  <div className="n">
                    {payload.triplet_hours.map((h) => `${h}h`).join(' · ')}
                  </div>
                  <div className="n">
                    {ranked === 'chatter' ? 'Chatter z' : 'Divergence'}
                  </div>
                  <div className="n">Mentions / people</div>
                  <div className="n">Price {payload.window_hours}h</div>
                </div>
```

- [ ] **Step 5: Use the same component on the cards, and delete what it replaces**

In `LeadCard.tsx`, replace the hand-rolled `<svg>` block inside `.chart` with:

```tsx
        <SpanChart chart={row.chart} series={row.series} span={span}
                   box={{ width: 300, height: 92, pad: 11, barBand: 0.94,
                          priceBand: 0.5 }}
                   label={`${row.ticker}, ${span}`} />
```

and change the legend's trailing span from `peak {peakHour}/h · 24h` to
`{span}`.

The card's intraday price line came from `price_series`, which the shared
component does not read. That payload field, `board._price_series`, and
`geometry.priceLine`/`priceRose` now have no consumer. **Delete all four.** An
unused payload field is one the next person has to prove is dead; deleting it
also drops a per-row quote query from every board build.

- [ ] **Step 6: Run everything**

Run: `npx tsc --noEmit` — no output
Run: `npx vitest run -c vite.radar.config.ts` — PASS
Run: `npm run build` — two "built in" lines
Run: `python -m pytest tests/ -q -k "radar or vite or auth"` — PASS

- [ ] **Step 7: Verify in a browser**

Screenshot `/radar/?window=24` at 1440, 1080 and 390 with python-playwright, at
spans `24h` and `1Y`. Assert programmatically rather than by eye:

```python
info = page.evaluate("""() => ({
  rows: document.querySelectorAll('.row').length,
  chatter: document.querySelectorAll('.row .spark path.chat, .row .spark rect').length,
  price: document.querySelectorAll('.row .spark path.px').length,
  overflow: document.documentElement.scrollWidth > window.innerWidth,
})""")
```

`overflow` must be false at every width and span. Grid tracks that floor at
min-content have caused horizontal overflow twice on this page already; the fix
is `minmax(0, 1fr)` on the offending track, never a wider page.

Read the PNGs back and look at them. At `1Y` expect a price line spanning the
width with chatter bars only in the last few days — that is correct today and
fills in as buckets accumulate.

- [ ] **Step 8: Commit**

```bash
git add personal_apps
git commit -m "feat(radar): switch the chart between a day, a month, a quarter and a year"
```

---

### Task 9: Deployment note

**Files:**
- Modify: `personal_apps/DEPLOY_FRONTEND.md`

- [ ] **Step 1: Record what the deploy needs**

The deploy script needs no change — `radar_history` runs inside the existing
`radar_ingest` unit, and `npm run build` already chains both Vite configs. But
the migration runs, and the first hour looks unusual.

Append to `personal_apps/DEPLOY_FRONTEND.md`:

```markdown
## Radar price history (2026-08-22)

`flask db upgrade` creates `radar_daily_closes`. No deploy-script change: the
fetch job runs inside the existing `radar_ingest` unit.

Expect the chart's longer spans to be dashed rules at first. The job fetches 20
tickers per five-minute cycle against Twelve Data's eight-per-minute limit, so
a full board of ~50 takes roughly fifteen minutes to fill, and tickers that
join later fill on the cycle after they arrive. That is the rate limit, not a
failure.

Expect the 1Y span to be price-only for months. Chatter history starts at
2026-08-21 and grows one day per day; `radar_buckets` is never pruned, so it
fills in on its own.

Watch it with:

    journalctl -u radar_ingest -f | grep "history stored"
```

- [ ] **Step 2: Commit**

```bash
git add personal_apps/DEPLOY_FRONTEND.md
git commit -m "docs(radar): note what the price-history deploy looks like"
```
