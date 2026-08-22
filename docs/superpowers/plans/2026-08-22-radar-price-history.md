# Radar Price History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a switchable 1M/3M/1Y daily-close line for every ticker on the radar board, so a ticker seen for the first time can be judged against what the stock has been doing.

**Architecture:** Daily closes are fetched once per ticker per day by a new daemon job and stored in `radar_daily_closes`. The board payload carries a bare number array per row; the React island slices it client-side for the selected window. Volatility stops calling the provider and reads the same table.

**Tech Stack:** Flask + SQLAlchemy + Flask-Migrate (MySQL 8 dev / MariaDB prod), APScheduler daemon, React 19 + TypeScript + Vite island, pytest + vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-22-radar-price-history-design.md`. Read it before Task 1.
- **This changes nothing about divergence, the eligibility floor, or the ranking.** If a task appears to, stop and re-read the spec's Scope boundary.
- Every datetime stored is **naive UTC**. `close_date` is a `DATE`, not a datetime.
- Green and red mean **price direction** and nothing else on this surface. Chatter is violet.
- **An absence is never a zero.** `price_history` is `null` when nothing is stored; a null renders as a dashed rule, never as a flat line.
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

### Task 5: The payload

**Files:**
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Test: `personal_apps/tests/test_radar_board.py`, `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Consumes: `history.closes_for` (Task 2).
- Produces: `BoardRow.price_history: tuple[date, list[Decimal]] | None`; JSON `price_history: {"from": "YYYY-MM-DD", "closes": [...]} | null`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/tests/test_radar_board.py`:

```python
def test_a_row_carries_its_stored_price_history(clean):
    import decimal
    from models import RadarDailyClose

    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    for offset in range(3):
        db.session.add(RadarDailyClose(
            ticker=f'{PREFIX}A',
            close_date=NOW.date() - dt.timedelta(days=offset),
            close=decimal.Decimal('10') + decimal.Decimal(offset),
            fetched_at=NOW))
    db.session.commit()

    entry = only(board.build(['bluesky'], NOW), f'{PREFIX}A')

    start, closes = entry.price_history
    assert start == NOW.date() - dt.timedelta(days=2)
    assert [float(c) for c in closes] == [12.0, 11.0, 10.0]


def test_a_row_with_no_stored_history_carries_none_not_an_empty_list(clean):
    """Null and empty are different downstream: null draws a dashed
    "not known" rule, empty would draw a flat line and assert a steady price.
    """
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    db.session.commit()

    assert only(board.build(['bluesky'], NOW), f'{PREFIX}A').price_history is None
```

Append to `personal_apps/tests/test_radar_api.py`:

```python
def test_price_history_serializes_as_a_start_date_and_a_number_array(client):
    """A bare array keeps a full board near 100KB. Points are positioned by
    index, so the axis is trading days -- which is also what makes the 1M and
    3M slices exact."""
    payload = json.loads(client.get('/radar/api/board').data)

    for row in payload['rows']:
        entry = row['price_history']
        if entry is None:
            continue
        assert set(entry) == {'from', 'closes'}
        assert isinstance(entry['closes'], list)
        assert all(isinstance(value, float) for value in entry['closes'])
        assert entry['from'].count('-') == 2
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_radar_board.py -k price_history -v`
Expected: FAIL with `AttributeError: 'BoardRow' object has no attribute 'price_history'`

- [ ] **Step 3: Add it to the board**

In `personal_apps/features/radar/board.py`:

Add `history` to the imports: `from . import history, leaderboard, market_calendar`

Add the field to `BoardRow`, after `price_series`:

```python
    # (first trading date, closes oldest first), or None when nothing is
    # stored. None rather than an empty list: never fetched and no history are
    # different facts, and the surface draws them differently.
    price_history: object
```

In `build()`, after `prices = _price_series(...)`:

```python
    stored_history = history.closes_for(tickers, today=now.date())
```

And in the `BoardRow(...)` construction, after `price_series=...`:

```python
        price_history=_history_for(stored_history.get(row.ticker)),
```

Add the helper next to `_price_series`:

```python
def _history_for(series):
    """(first date, [closes]) or None. Splits the dates off the values because
    the payload sends the values alone and names only where they start."""
    if not series:
        return None
    return series[0][0], [close for _, close in series]
```

- [ ] **Step 4: Serialize it**

In `personal_apps/features/radar/routes/api.py`, inside `_row()`, after the
`price_series` entry:

```python
        'price_history': _history(entry.price_history),
```

And add the helper beside `_decimal_or_none`:

```python
def _history(entry):
    """{'from': ISO date, 'closes': [...]} or null.

    A bare number array rather than dated objects: 260 values per row across a
    full board is about 100KB this way and roughly triple that with a date on
    every point. Nothing reads a date off a 124px sparkline, and slicing by
    index gives exact trading-day windows.
    """
    if entry is None:
        return None
    start, closes = entry
    return {'from': start.isoformat(),
            'closes': [float(close) for close in closes]}
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_radar_board.py tests/test_radar_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/board.py personal_apps/features/radar/routes/api.py personal_apps/tests/test_radar_board.py personal_apps/tests/test_radar_api.py
git commit -m "feat(radar): carry a year of closes in the board payload"
```

---

### Task 6: Slicing and drawing the price line

**Files:**
- Modify: `personal_apps/static/radar/src/types.ts`
- Modify: `personal_apps/static/radar/src/board/geometry.ts`
- Create: `personal_apps/static/radar/src/board/PriceHistory.tsx`
- Test: `personal_apps/static/radar/src/board/geometry.test.ts`

**Interfaces:**
- Produces:
  - `types.ts`: `PriceHistory = { from: string; closes: number[] }`, `HistoryWindow = '1M' | '3M' | '1Y'`, `Row.price_history: PriceHistory | null`
  - `geometry.ts`: `HISTORY_SPANS: Record<HistoryWindow, number>`, `sliceHistory(closes, window) -> number[]`, `historyPath(closes, box) -> string`, `historyRose(closes) -> boolean`
  - `PriceHistory.tsx`: `<PriceHistory history={...} window={...} label={...} />`

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/static/radar/src/board/geometry.test.ts`:

```ts
describe('the price history window', () => {
  const year = Array.from({ length: 260 }, (_, i) => 100 + i)

  it('slices by trading days, which is what the index actually is', () => {
    expect(sliceHistory(year, '1M')).toHaveLength(21)
    expect(sliceHistory(year, '3M')).toHaveLength(63)
    expect(sliceHistory(year, '1Y')).toHaveLength(260)
  })

  it('takes the most recent end, not the oldest', () => {
    expect(sliceHistory(year, '1M').at(-1)).toBe(359)
  })

  it('returns everything it has when the series is shorter than the window', () => {
    // A stock that IPO'd last month has six weeks of history, not three
    // months of it, and padding would invent prices it never traded at.
    expect(sliceHistory([1, 2, 3], '1Y')).toEqual([1, 2, 3])
    expect(sliceHistory([1, 2, 3], '3M')).toEqual([1, 2, 3])
  })

  it('draws nothing from fewer than two points', () => {
    expect(historyPath([], BOX)).toBe('')
    expect(historyPath([42], BOX)).toBe('')
  })

  it('scales to its own range rather than to zero', () => {
    // Unlike the chatter line. A stock's floor is not zero, and the question
    // here is the shape of the year, not its magnitude.
    const path = historyPath([100, 150, 200], BOX)
    const values = [...path.matchAll(/[ML][\d.]+,([\d.]+)/g)].map((m) => Number(m[1]))

    expect(values[0]).toBe(BOX.height)
    expect(values[2]).toBe(0)
  })

  it('reads direction across the window, not across the whole year', () => {
    expect(historyRose([100, 50, 60])).toBe(false)
    expect(historyRose([100, 200])).toBe(true)
    expect(historyRose([])).toBe(true)
  })
})
```

Add `sliceHistory, historyPath, historyRose` to the import at the top of that
file.

- [ ] **Step 2: Run and watch them fail**

Run: `npx vitest run -c vite.radar.config.ts geometry`
Expected: FAIL with "sliceHistory is not exported"

- [ ] **Step 3: Add the types**

In `personal_apps/static/radar/src/types.ts`, before `interface Row`:

```ts
/** A year of daily closes, oldest first. Positioned by index: the axis is
 *  trading days, so holidays are not drawn as gaps. Nothing reads a date off
 *  a 124px sparkline, and index slicing gives exact trading-day windows. */
export interface PriceHistory {
  from: string
  closes: number[]
}

export type HistoryWindow = '1M' | '3M' | '1Y'
```

And inside `Row`, after `price_series`:

```ts
  /** null when nothing is stored yet -- which is not the same as flat. */
  price_history: PriceHistory | null
```

- [ ] **Step 4: Add the geometry**

Append to `personal_apps/static/radar/src/board/geometry.ts`:

```ts
/** Trading days per window. 1Y is the whole series, whatever length it is. */
export const HISTORY_SPANS: Record<HistoryWindow, number> = {
  '1M': 21,
  '3M': 63,
  '1Y': Number.MAX_SAFE_INTEGER,
}

/** The most recent N trading days. Short series come back whole rather than
 *  padded -- a stock that listed last month has six weeks of history, and
 *  inventing the rest would draw prices it never traded at. */
export function sliceHistory(closes: number[], window: HistoryWindow): number[] {
  const span = HISTORY_SPANS[window]
  return closes.length <= span ? closes : closes.slice(closes.length - span)
}

/** The price line, scaled to its own range across the selected window.
 *
 *  Not zero-anchored, unlike the chatter line above it: a stock's floor is not
 *  zero, and the question here is the shape of the move rather than its
 *  magnitude against nothing. */
export function historyPath(closes: number[], box: Box): string {
  if (closes.length < 2) return ''

  const low = Math.min(...closes)
  const high = Math.max(...closes)
  const span = high - low || 1
  const plotHeight = box.height - box.pad * 2

  return closes.map((value, index) => {
    const x = (index / (closes.length - 1)) * box.width
    const y = box.pad + plotHeight - ((value - low) / span) * plotHeight
    return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

/** Whether the window ended higher than it began. Decides the line's colour,
 *  which is why it reads the WINDOW rather than the full year -- a stock down
 *  on the year and up this month is green on the 1M view, correctly. */
export function historyRose(closes: number[]): boolean {
  const first = closes.at(0)
  const last = closes.at(-1)
  if (first === undefined || last === undefined) return true
  return last >= first
}
```

Add `HistoryWindow` to the type import at the top of `geometry.ts`:

```ts
import type { HistoryWindow, Point, PricePoint } from '../types'
```

- [ ] **Step 5: Run the geometry tests**

Run: `npx vitest run -c vite.radar.config.ts geometry`
Expected: PASS

- [ ] **Step 6: Write the component**

Create `personal_apps/static/radar/src/board/PriceHistory.tsx`:

```tsx
import type { HistoryWindow, PriceHistory as History } from '../types'
import { historyPath, historyRose, sliceHistory, type Box } from './geometry'

const BOX: Box = { width: 124, height: 26, pad: 3 }

/** A ticker's price over the selected window, as one line.
 *
 *  Sits beside the chatter sparkline deliberately: the pair answers the
 *  question divergence cannot, which is whether a stock exploding in mentions
 *  has been dead all year or has already run.
 *
 *  aria-hidden for the same reason the chatter sparkline is -- it draws no
 *  quantity the row does not already carry as text, and announcing "a line
 *  chart" adds an announcement without adding a fact.
 */
export function PriceHistory({ history, window, label }: {
  history: History | null
  window: HistoryWindow
  label: string
}) {
  const closes = history ? sliceHistory(history.closes, window) : []
  const path = historyPath(closes, BOX)
  const rose = historyRose(closes)

  return (
    <div className="hist">
      <svg viewBox={`0 0 ${BOX.width} ${BOX.height}`} preserveAspectRatio="none"
           role="img" aria-hidden="true" focusable="false">
        <title>{label}</title>
        {path ? (
          <path d={path} fill="none" strokeWidth="1.7" strokeLinejoin="round"
                strokeLinecap="round" vectorEffect="non-scaling-stroke"
                stroke={rose ? 'var(--up)' : 'var(--down)'} />
        ) : (
          // No history stored yet. A dashed rule says that; an empty box would
          // read as a price that held perfectly steady for a year.
          <line x1="0" y1={BOX.height / 2} x2={BOX.width} y2={BOX.height / 2}
                stroke="var(--rule)" strokeWidth="1" strokeDasharray="3 3"
                vectorEffect="non-scaling-stroke" />
        )}
      </svg>
    </div>
  )
}
```

- [ ] **Step 7: Typecheck and commit**

Run: `npx tsc --noEmit`
Expected: no output

```bash
git add personal_apps/static/radar/src/types.ts personal_apps/static/radar/src/board/geometry.ts personal_apps/static/radar/src/board/geometry.test.ts personal_apps/static/radar/src/board/PriceHistory.tsx
git commit -m "feat(radar): slice and draw a ticker's price history"
```

---

### Task 7: The scan row trades two columns for two

**Files:**
- Modify: `personal_apps/static/radar/src/board/ScanRow.tsx`
- Modify: `personal_apps/static/radar/radar.css`
- Test: `personal_apps/static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Consumes: `PriceHistory` component, `HistoryWindow` (Task 6).
- Produces: `<ScanRow ... historyWindow={HistoryWindow} />`.

**Track count stays at seven.** The price line adds one and merging Mentions
with Authors removes one; the grid is not getting wider. If you find yourself
writing an eighth track, something has gone wrong.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/static/radar/src/board/BoardPage.test.tsx`, and add
`price_history: { from: '2025-08-11', closes: [10, 11, 12] }` to the `row()`
fixture's defaults:

```tsx
describe('price history on a row', () => {
  it('shows mentions and people as one column', () => {
    // Merged to make room for the price line. They answer the same question --
    // how much talk, from how many mouths -- and the lead cards already say
    // them as one sentence.
    const { container } = render(<BoardPage initial={payload()} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(within(scan).getByText('20 / 9')).toBeInTheDocument()
  })

  it('draws a price line per row', () => {
    const { container } = render(<BoardPage initial={payload()} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(scan.querySelector('.hist path')).not.toBeNull()
  })

  it('draws a dashed rule, not a flat line, when there is no history', () => {
    const none = payload({
      rows: [row(), row(), row(), row({ ticker: 'DDD', price_history: null })],
    })
    const { container } = render(<BoardPage initial={none} />)
    const scan = container.querySelector('.row') as HTMLElement

    expect(scan.querySelector('.hist path')).toBeNull()
    expect(scan.querySelector('.hist line')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Run and watch them fail**

Run: `npx vitest run -c vite.radar.config.ts BoardPage`
Expected: FAIL — "Unable to find an element with the text: 20 / 9"

- [ ] **Step 3: Update ScanRow**

In `personal_apps/static/radar/src/board/ScanRow.tsx`:

Add to the imports:

```tsx
import type { HistoryWindow, Mark, Row } from '../types'
import { PriceHistory } from './PriceHistory'
```

Add `historyWindow` to the props (after `ranked`):

```tsx
  /** Which slice of the stored year the price line draws. */
  historyWindow: HistoryWindow
```

Replace the two separate count cells:

```tsx
      <div className="n">{row.mentions}</div>
      <div className="n">{row.authors}</div>
```

with the merged one plus the price line, placed directly after the `.trip`
block so the two sparklines sit side by side:

```tsx
      <div className="n">{row.mentions} / {row.authors}</div>
```

and immediately after the `<Sparkline .../>` element:

```tsx
      <PriceHistory history={row.price_history} window={historyWindow}
                    label={`${row.ticker} price, ${historyWindow}`} />
```

Update the mobile caption to match:

```tsx
      <div className="meta">
        <span><b>{row.mentions}</b> mentions</span>
        <span><b>{row.authors}</b> people</span>
        <span>{priceCell(row)}</span>
      </div>
```

- [ ] **Step 4: Update the grid**

In `personal_apps/static/radar/radar.css`, replace the `.cols, .row`
declaration's `grid-template-columns` with:

```css
  grid-template-columns:
    minmax(170px, 1.4fr)   /* ticker + name + marks */
    112px                  /* 24h chatter           */
    112px                  /* price history         */
    136px                  /* z triplet             */
    100px                  /* divergence            */
    92px                   /* mentions / people     */
    100px;                 /* price move            */
```

Add beside the `.spark` rule:

```css
.hist { position: relative; min-width: 0; }
.hist svg { display: block; width: 100%; height: 26px; }
```

In the `@media (max-width: 1080px)` block, replace the columns with:

```css
    grid-template-columns:
      minmax(140px, 1.3fr) 92px 92px 124px 88px 80px 88px;
```

In the `@media (max-width: 720px)` block, add `hist` to the grid areas so the
two lines share the second row:

```css
    grid-template-areas:
      'tick  dv'
      'spark trip'
      'hist  hist'
      'meta  meta';
```

and add `.hist { grid-area: hist; min-width: 0; }` beside the `.spark` rule in
that block.

- [ ] **Step 5: Run the tests**

Run: `npx vitest run -c vite.radar.config.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add personal_apps/static/radar/src/board/ScanRow.tsx personal_apps/static/radar/radar.css personal_apps/static/radar/src/board/BoardPage.test.tsx
git commit -m "feat(radar): put a price line on every row"
```

---

### Task 8: The control, the cards, and the header

**Files:**
- Modify: `personal_apps/static/radar/src/board/BoardPage.tsx`
- Modify: `personal_apps/static/radar/src/board/Controls.tsx`
- Modify: `personal_apps/static/radar/src/board/LeadCard.tsx`
- Test: `personal_apps/static/radar/src/board/BoardPage.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 6 and 7.
- Produces: board-level `historyWindow` state, default `'1Y'`.

- [ ] **Step 1: Write the failing tests**

Append to `personal_apps/static/radar/src/board/BoardPage.test.tsx`:

```tsx
describe('the history window control', () => {
  it('defaults to a year', () => {
    render(<BoardPage initial={payload()} />)

    expect(screen.getByRole('button', { name: '1Y' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('re-slices without refetching the board', async () => {
    // The whole year is already in the payload. Asking the server again for
    // data the client is holding would be a round trip for nothing.
    render(<BoardPage initial={payload()} />)

    await userEvent.click(screen.getByRole('button', { name: '3M' }))

    expect(fetch).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '3M' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('labels the column with the window in force', () => {
    render(<BoardPage initial={payload()} />)

    expect(screen.getByText('1Y price')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and watch them fail**

Run: `npx vitest run -c vite.radar.config.ts BoardPage`
Expected: FAIL — no button named "1Y"

- [ ] **Step 3: Add the control**

In `personal_apps/static/radar/src/board/Controls.tsx`, add to the imports:

```tsx
import type { BoardPayload, HistoryWindow, Segment, Selection } from '../types'
```

Add the constant beside `WINDOWS`:

```tsx
const HISTORY_WINDOWS: HistoryWindow[] = ['1M', '3M', '1Y']
```

Add two props to the component signature:

```tsx
  historyWindow: HistoryWindow
  onHistoryWindow: (next: HistoryWindow) => void
```

And add the group after the existing Window group:

```tsx
      <div className="group">
        <span className="lbl" id="hist-lbl">History</span>
        <div className="seg" role="group" aria-labelledby="hist-lbl">
          {HISTORY_WINDOWS.map((span) => (
            <button key={span} type="button"
                    aria-pressed={historyWindow === span}
                    onClick={() => onHistoryWindow(span)}>
              {span}
            </button>
          ))}
        </div>
      </div>
```

- [ ] **Step 4: Wire it into the page**

In `personal_apps/static/radar/src/board/BoardPage.tsx`:

Add to the type import: `import type { BoardPayload, HistoryWindow, Mark, Selection } from '../types'`

Add the state beside `busy`:

```tsx
  // Board-level, not per row, so every line on screen shares a window and the
  // rows stay comparable. Purely client-side: the payload already holds the
  // whole year, so switching costs no request.
  const [historyWindow, setHistoryWindow] = useState<HistoryWindow>('1Y')
```

Pass both to `Controls`:

```tsx
        <Controls payload={payload} selection={selection} busy={busy}
                  onChange={setSelection} historyWindow={historyWindow}
                  onHistoryWindow={setHistoryWindow} />
```

Pass the window to both children:

```tsx
                <LeadCard key={row.ticker} row={row} chatterMax={chatterMax}
                          windowHours={payload.window_hours} ranked={ranked}
                          hiddenMarks={universal} historyWindow={historyWindow} />
```

```tsx
                  <ScanRow key={row.ticker} row={row} ranked={ranked}
                           hiddenMarks={universal} historyWindow={historyWindow}
                           triplet={payload.triplet_hours} />
```

Update the column headings — the price-line heading names the window, and the
merged counts get one label:

```tsx
                <div className="cols" aria-hidden="true">
                  <div>Ticker</div>
                  <div>{payload.series_hours}h chatter</div>
                  <div>{historyWindow} price</div>
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

- [ ] **Step 5: Add the strip to the lead cards**

In `personal_apps/static/radar/src/board/LeadCard.tsx`, add the imports:

```tsx
import type { HistoryWindow, Mark, Row } from '../types'
import { PriceHistory } from './PriceHistory'
```

Add the prop after `hiddenMarks`:

```tsx
  historyWindow: HistoryWindow
```

And insert the strip between the `.chart` div and `.lead-foot`:

```tsx
      {/* A separate strip rather than a third series on the chart above. That
          chart exists to show 24h chatter against 24h price on one axis, and
          a year-long line sharing those axes would destroy the comparison. */}
      <div className="lead-hist">
        <PriceHistory history={row.price_history} window={historyWindow}
                      label={`${row.ticker} price, ${historyWindow}`} />
        <span className="lead-hist-k">{historyWindow} price</span>
      </div>
```

Add to `personal_apps/static/radar/radar.css`, after the `.legend` rule:

```css
.lead-hist {
  display: flex; align-items: center; gap: 10px;
  padding-top: 9px; border-top: 1px solid var(--rule-soft);
}
.lead-hist .hist { flex: 1 1 0; min-width: 0; }
.lead-hist-k { font-size: 11px; color: var(--muted); flex: none; }
```

- [ ] **Step 6: Run everything and build**

Run: `npx tsc --noEmit`
Expected: no output

Run: `npx vitest run -c vite.radar.config.ts`
Expected: PASS

Run: `npm run build`
Expected: two "built in" lines, no errors

- [ ] **Step 7: Verify in a browser at three widths**

Start the dev server (`.claude/launch.json` entry `personal_apps`, port 5001)
and screenshot `/radar/?window=24` at 1440, 1080 and 390 wide with
python-playwright. Assert programmatically, not by eye:

```python
info = page.evaluate("""() => ({
  rows: document.querySelectorAll('.row').length,
  histLines: document.querySelectorAll('.row .hist path').length,
  histDashed: document.querySelectorAll('.row .hist line').length,
  overflow: document.documentElement.scrollWidth > window.innerWidth,
})""")
```

`overflow` must be `false` at every width. Grid tracks that floor at
min-content have caused horizontal overflow twice on this page already — if it
returns true, the fix is `minmax(0, 1fr)` on the offending track, not a wider
page.

- [ ] **Step 8: Commit**

```bash
git add personal_apps/static/radar/src personal_apps/static/radar/radar.css
git commit -m "feat(radar): switch the price line between one month, three, and a year"
```

---

### Task 9: Deployment note

**Files:**
- Modify: `personal_apps/DEPLOY_FRONTEND.md`

- [ ] **Step 1: Record what the deploy needs**

The deploy script needs no change — `radar_history` runs inside the existing
`radar_ingest` service, and `npm run build` already chains both Vite configs.
But the migration does run, and the first hours after deploy look unusual.

Append to `personal_apps/DEPLOY_FRONTEND.md`:

```markdown
## Radar price history (2026-08-22)

`flask db upgrade` creates `radar_daily_closes`. No deploy-script change: the
fetch job runs inside the existing `radar_ingest` unit.

Expect the price column to be dashed rules for the first while. The job fetches
20 tickers per five-minute cycle against Twelve Data's eight-per-minute limit,
so a full board of ~50 takes roughly fifteen minutes to fill, and tickers that
join later fill on the cycle after they arrive. That is the rate limit, not a
failure.

Watch it with:

    journalctl -u radar_ingest -f | grep "history stored"
```

- [ ] **Step 2: Commit**

```bash
git add personal_apps/DEPLOY_FRONTEND.md
git commit -m "docs(radar): note what the price-history deploy looks like"
```
