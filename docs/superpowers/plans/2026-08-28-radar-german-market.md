# Radar German Market and Berlin Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a switchable US/German price context to Radar, render all user-facing time in Europe/Berlin, and expose honest regular and extended-session movement with explicit quote quality and US fallback states.

**Architecture:** Keep the current US ticker as the stable social/company identity and add market instruments beneath it. Price persistence, calendars, ranking, API payloads, and frontend caches become market-aware; Germany mode prefers verified Xetra EUR instruments and falls back explicitly to the US/USD instrument. Provider adapters normalize quote metadata and quality, while UTC remains the storage/wire convention.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy/Alembic, MySQL/SQLite tests, requests, React 19, TypeScript, Vitest/Testing Library, Vite, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-28-radar-german-market-design.md`

## Global Constraints

- Every user-facing date and clock uses the fixed IANA timezone `Europe/Berlin`; storage and ISO wire values remain UTC.
- `market` is exactly `us` or `de`; omitted API/query state defaults to `us`.
- A German price must be an actual German-venue EUR price. Never synthesize it with FX conversion.
- Missing German instruments use an explicit US/USD fallback; no fuzzy company-name mapping.
- Quote qualities are exactly `live`, `delayed`, `eod`, `stale`, or `unavailable`.
- Delayed quotes are divergence-eligible only when their quote age is at most 1,800 seconds and existing frozen-tape checks pass.
- EOD, stale, unavailable, and currency-mismatched data never produce live price divergence.
- Green/red mean price direction only. Pre-/after-hours states also require visible text or an accessible label.
- Preserve the existing API’s flat US price fields for one compatibility phase.
- No EIX scraping or private Scalable endpoint; EIX remains out of scope until a permitted feed exists.
- Work task-by-task. One implementation worker at a time, then an independent read-only review. Update the ledger and `HANDOFF.md` after every accepted task.
- Preserve unrelated changes in the primary checkout; all feature work stays in `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-german-market` on `codex/radar-german-market`.

---

## File map

### New files

- `personal_apps/features/radar/markets.py` — market constants, instrument/quote selection, normalized `QuoteView`, freshness and fallback rules.
- `personal_apps/features/radar/instruments.py` — catalog normalization, ISIN joins, Xetra preference, mapping persistence and refresh scheduling.
- `personal_apps/features/radar/market_calendars/us.py` — existing NYSE rules moved without behaviour change.
- `personal_apps/features/radar/market_calendars/de.py` — Xetra calendar and session boundaries.
- `personal_apps/features/radar/market_calendars/__init__.py` — `session_state(market, when_utc)` and session-boundary registry.
- `personal_apps/migrations/versions/a4c8e2f19b70_add_radar_market_instruments.py` — compatibility migration and downgrade.
- `personal_apps/tests/test_radar_markets.py` — normalized quality, selection and fallback tests.
- `personal_apps/tests/test_radar_instruments.py` — provider catalog mapping tests.
- `personal_apps/tests/test_radar_calendar_de.py` — Xetra calendar/DST tests.
- `personal_apps/static/radar/src/board/MarketSwitch.tsx` — accessible market selector.
- `personal_apps/static/radar/src/detail/SessionBands.tsx` — chart session intervals and labels.

### Existing files with changed responsibility

- `personal_apps/models.py` — add `RadarInstrument`; add market/venue/currency/provider context to quote and daily-close rows.
- `personal_apps/features/radar/prices/__init__.py` — normalize provider quote identity, currency, regular close, and quality inputs.
- `personal_apps/features/radar/prices/finnhub.py` — request provider symbols but return canonical ticker/market context.
- `personal_apps/features/radar/prices/twelvedata.py` — catalog reads and MIC-qualified history requests.
- `personal_apps/features/radar/quotes.py`, `history.py`, `retention.py` — isolate all reads, writes, windows and partitions by market/MIC.
- `personal_apps/run_radar_ingest.py` — poll US and mapped German instruments independently; refresh mappings weekly.
- `personal_apps/features/radar/market_calendar.py` — compatibility re-export only, then remove internal NY-only assumptions.
- `personal_apps/features/radar/leaderboard.py`, `board.py`, `detail.py`, `detail_panel.py`, `phrasing.py` — accept market, use per-row quote/session, and preserve social metrics.
- `personal_apps/features/radar/routes/api.py` and `routes/views.py` — parse/serialize market and default invalid human-page queries to US.
- `personal_apps/static/radar/src/types.ts`, `api.ts`, `board/BoardPage.tsx` — typed market state, URLs and cache boundaries.
- `personal_apps/static/radar/src/format.ts` — fixed Berlin time and currency-aware formatting.
- `personal_apps/static/radar/src/list/ListPane.tsx`, `list/TickerRow.tsx`, `detail/Identity.tsx`, `detail/PriceChart.tsx` — quote source/quality/session presentation.
- `personal_apps/static/radar/src/board/BoardPage.test.tsx`, `format.test.ts`, `detail/PriceChart.test.tsx`, `hardening.test.tsx` — UI and compatibility regression coverage.

---

### Task 1: Add compatible market-aware persistence

**Files:**
- Modify: `personal_apps/models.py`
- Create: `personal_apps/migrations/versions/a4c8e2f19b70_add_radar_market_instruments.py`
- Modify: `personal_apps/tests/test_radar_models.py`
- Modify: `personal_apps/tests/test_radar_migration.py`

**Interfaces:**
- Produces: `RadarInstrument(ticker, market, venue, mic, provider_symbol, currency, isin, is_primary, mapping_status, mapping_source, mapped_at)`.
- Produces: transitional nullable `RadarQuote.market`, `.mic`, `.currency`,
  `.provider_symbol`; new rows can carry market context while legacy writers
  continue during the overlap.
- Produces: transitional nullable `RadarDailyClose.market`, `.mic`, `.currency`;
  a later contraction changes keys only after every writer is market-aware.

- [x] **Step 1: Write failing model-shape tests**

```python
def test_radar_instrument_identity_and_market_quote_context():
    instrument = RadarInstrument(
        ticker='AAPL', market='de', venue='Xetra', mic='XETR',
        provider_symbol='APC', currency='EUR', isin='US0378331005',
        is_primary=True, mapping_status='mapped', mapping_source='twelvedata')
    quote = RadarQuote(
        ticker='AAPL', market='de', mic='XETR', currency='EUR',
        provider_symbol='APC', fetched_at=NOW, quote_ts=NOW,
        price=decimal.Decimal('194.20'))
    assert instrument.market == quote.market == 'de'
    assert instrument.currency == quote.currency == 'EUR'
```

- [x] **Step 2: Run the focused tests and confirm they fail because the model/columns do not exist**

Run: `cd personal_apps && python -m pytest tests/test_radar_models.py tests/test_radar_migration.py -q`

Expected: failure naming `RadarInstrument` or missing market columns.

- [x] **Step 3: Add the SQLAlchemy model and context columns**

Use database enums/checks already established by this repository where portable; keep Python-level string values:

```python
class RadarInstrument(db.Model):
    __tablename__ = 'radar_instruments'
    __table_args__ = (
        db.UniqueConstraint('ticker', 'market', 'mic',
                            name='uq_radar_instrument'),
        db.Index('ix_radar_instrument_primary',
                 'ticker', 'market', 'is_primary'),
        {'mysql_charset': 'utf8mb4'},
    )
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ticker = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    market = db.Column(db.String(2), nullable=False)
    venue = db.Column(db.String(48), nullable=False)
    mic = db.Column(db.String(4), nullable=False)
    provider_symbol = db.Column(db.String(32), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    isin = db.Column(db.String(12), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    mapping_status = db.Column(db.String(12), nullable=False)
    mapping_source = db.Column(db.String(24), nullable=True)
    mapped_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
```

- [x] **Step 4: Generate and edit the compatibility migration**

Create revision `a4c8e2f19b70` with `down_revision` set to the repository's
current Alembic head at execution time; confirm it with `flask db heads` before
writing the file.

Migration order must be: create table; add nullable context columns; seed US
instruments from active `radar_ticker_universe`; backfill quote/daily-close rows
with `market='us'`, a deterministic MIC from the existing exchange code,
`currency='USD'`, and provider symbol equal to ticker. Preserve the old
unique/primary/index keys in this expand migration so the legacy daemon can
continue to write. Task 5 adds market-aware keys and a later contraction makes
the columns non-null only after a null-row verification. Downgrade removes
context columns and drops `radar_instruments`; Task 1 creates no German price
rows, so this stage requires no destructive data deletion.

- [x] **Step 5: Add migration assertions for preservation, overlap and downgrade**

```python
def test_market_migration_preserves_existing_us_price_rows(migrated_connection):
    quote = migrated_connection.execute(sa.text(
        "SELECT market, currency, provider_symbol FROM radar_quotes "
        "WHERE ticker='AAPL'")) .one()
    assert tuple(quote) == ('us', 'USD', 'AAPL')

def test_market_migration_downgrade_keeps_us_and_drops_de_context(
        migration_connection):
    migration_connection.insert_legacy_quote('AAPL')
    migration_connection.upgrade()
    migration_connection.downgrade()
    assert migration_connection.quote_columns() == {
        'id', 'ticker', 'fetched_at', 'quote_ts', 'price', 'prev_close',
        'volume'}
    assert migration_connection.quote_count('AAPL') == 1
```

- [x] **Step 6: Run model and migration tests**

Run: `cd personal_apps && python -m pytest tests/test_radar_models.py tests/test_radar_migration.py -q`

Expected: all pass.

- [ ] **Step 7: Commit Task 1**

```powershell
git add personal_apps/models.py personal_apps/migrations/versions personal_apps/tests/test_radar_models.py personal_apps/tests/test_radar_migration.py
git commit -m "feat(radar): add market-aware price storage"
```

---

### Task 2: Introduce market calendars without changing US behaviour

**Files:**
- Create: `personal_apps/features/radar/market_calendars/__init__.py`
- Create: `personal_apps/features/radar/market_calendars/us.py`
- Create: `personal_apps/features/radar/market_calendars/de.py`
- Modify: `personal_apps/features/radar/market_calendar.py`
- Modify: `personal_apps/tests/test_radar_calendar.py`
- Create: `personal_apps/tests/test_radar_calendar_de.py`

**Interfaces:**
- Produces: `session_state(market: str, when_utc: datetime) -> Session`.
- Produces: `session_bounds(market: str, when_utc: datetime) -> SessionBounds` with UTC `opens_at`, `regular_opens_at`, `regular_closes_at`, `closes_at`.
- Preserves: `market_calendar.session_state(when_utc)` as a US compatibility wrapper until all callers migrate.

- [ ] **Step 1: Pin the current US calendar through the new registry**

```python
def test_registry_preserves_us_dst_and_early_close():
    assert session_state('us', aware_utc(2026, 3, 9, 13, 45)) == 'regular'
    assert session_state('us', aware_utc(2026, 11, 27, 18, 15)) == 'afterhours'
```

- [ ] **Step 2: Add failing Xetra session and DST tests**

```python
@pytest.mark.parametrize(('instant', 'expected'), [
    ((2026, 8, 28, 5, 59), 'closed'),
    ((2026, 8, 28, 6, 0), 'premarket'),
    ((2026, 8, 28, 7, 0), 'regular'),
    ((2026, 8, 28, 15, 30), 'afterhours'),
    ((2026, 8, 28, 20, 0), 'closed'),
])
def test_xetra_summer_sessions_are_berlin_local(instant, expected):
    assert session_state('de', aware_utc(*instant)) == expected

def test_xetra_winter_open_moves_one_utc_hour():
    assert session_state('de', aware_utc(2026, 1, 7, 7, 0)) == 'premarket'
    assert session_state('de', aware_utc(2026, 1, 7, 8, 0)) == 'regular'
```

- [ ] **Step 3: Run calendar tests and confirm the registry/DE module is absent**

Run: `cd personal_apps && python -m pytest tests/test_radar_calendar.py tests/test_radar_calendar_de.py -q`

- [ ] **Step 4: Move the existing NYSE implementation unchanged into `market_calendars/us.py` and add the registry**

```python
@dataclasses.dataclass(frozen=True)
class SessionBounds:
    opens_at: dt.datetime
    regular_opens_at: dt.datetime
    regular_closes_at: dt.datetime
    closes_at: dt.datetime

def session_state(market, when_utc):
    try:
        calendar = {'us': us, 'de': de}[market]
    except KeyError as exc:
        raise ValueError(f'unknown market: {market}') from exc
    return calendar.session_state(when_utc)
```

- [ ] **Step 5: Implement the 2026 Xetra rules with `ZoneInfo('Europe/Berlin')`**

Use 08:00–08:55 early, 09:00–17:30 regular, and closing-auction end–22:00 late. Encode the official 2026 full closures: Jan 1, Apr 3, Apr 6, May 1, Dec 24, Dec 25, Dec 31; encode Dec 30’s published shortened close only when the official circular defines it. In the absence of a circular, keep the regular boundary and isolate the annual override in one mapping.

- [ ] **Step 6: Run both calendar suites**

Run: `cd personal_apps && python -m pytest tests/test_radar_calendar.py tests/test_radar_calendar_de.py -q`

Expected: all pass, including every pre-existing US assertion.

- [ ] **Step 7: Commit Task 2**

```powershell
git add personal_apps/features/radar/market_calendar.py personal_apps/features/radar/market_calendars personal_apps/tests/test_radar_calendar.py personal_apps/tests/test_radar_calendar_de.py
git commit -m "feat(radar): add Xetra market calendar"
```

---

### Task 3: Normalize quote quality, movement and fallback selection

**Files:**
- Create: `personal_apps/features/radar/markets.py`
- Modify: `personal_apps/features/radar/prices/__init__.py`
- Create: `personal_apps/tests/test_radar_markets.py`
- Modify: `personal_apps/tests/test_radar_prices.py`

**Interfaces:**
- Produces: `Market = Literal['us', 'de']` by documented string contract.
- Produces: `QuoteView` dataclass consumed by leaderboard, board and detail.
- Produces: `classify_quality(quote_ts, fetched_at, provider_delay, now) -> str`.
- Produces: `select_quote(ticker, requested_market, snapshots, now) -> QuoteView`.

- [ ] **Step 1: Add failing quality and movement tests**

```python
def test_delayed_quote_is_eligible_at_exactly_thirty_minutes():
    view = quote_view(quote_ts=NOW - dt.timedelta(minutes=30), quality='delayed')
    assert view.score_eligible is True

def test_delayed_quote_becomes_stale_after_thirty_minutes():
    view = quote_view(quote_ts=NOW - dt.timedelta(minutes=30, seconds=1),
                      quality='delayed')
    assert view.quality == 'stale'
    assert view.score_eligible is False

def test_afterhours_move_uses_same_day_regular_close():
    view = quote_view(price='102', previous_close='98', regular_close='100',
                      session='afterhours')
    assert view.regular_move == decimal.Decimal('0.0204081632653061224489795918')
    assert view.extended_move == decimal.Decimal('0.02')
```

- [ ] **Step 2: Add failing fallback and currency-integrity tests**

```python
def test_missing_de_quote_selects_marked_us_fallback():
    selected = select_quote('AAPL', 'de', {'us': us_snapshot()}, NOW)
    assert (selected.market, selected.currency, selected.is_fallback) == (
        'us', 'USD', True)

def test_currency_mismatch_rejects_provider_snapshot():
    with pytest.raises(CurrencyMismatch):
        normalize_snapshot(de_instrument(currency='EUR'), raw(currency='USD'))
```

- [ ] **Step 3: Run the focused suites and confirm missing interfaces**

Run: `cd personal_apps && python -m pytest tests/test_radar_markets.py tests/test_radar_prices.py -q`

- [ ] **Step 4: Extend the provider-neutral dataclasses**

```python
@dataclasses.dataclass(frozen=True)
class Quote:
    ticker: str
    market: str
    venue: str
    mic: str
    provider_symbol: str
    currency: str
    price: decimal.Decimal
    previous_close: decimal.Decimal | None
    regular_close: decimal.Decimal | None
    quote_ts: dt.datetime | None
    volume: int | None
    provider_delay: str  # 'live', 'delayed', or 'eod'
```

Implement immutable `QuoteView` with `price`, `regular_move`, `extended_move`,
`session`, `quality`, `age_seconds`, `score_eligible`, venue identity, and
`is_fallback`. Centralize every movement calculation here; serializers and
components must not rederive it.

- [ ] **Step 5: Implement fallback selection and exact freshness rules**

Selection order for `de` is fresh primary Xetra, retained Xetra snapshot,
fresh US primary marked fallback, retained US snapshot marked fallback, then
unavailable. Selection order for `us` never falls to Germany.

- [ ] **Step 6: Run focused tests**

Run: `cd personal_apps && python -m pytest tests/test_radar_markets.py tests/test_radar_prices.py -q`

Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add personal_apps/features/radar/markets.py personal_apps/features/radar/prices/__init__.py personal_apps/tests/test_radar_markets.py personal_apps/tests/test_radar_prices.py
git commit -m "feat(radar): normalize market quote states"
```

---

### Task 4: Map verified Xetra instruments from provider catalogs

**Files:**
- Create: `personal_apps/features/radar/instruments.py`
- Modify: `personal_apps/features/radar/prices/finnhub.py`
- Modify: `personal_apps/features/radar/prices/twelvedata.py`
- Create: `personal_apps/tests/test_radar_instruments.py`
- Modify: `personal_apps/tests/test_radar_prices.py`

**Interfaces:**
- Produces: `CatalogInstrument(symbol, name, mic, currency, isin, figi)`.
- Produces: `TwelveDataProvider.stock_catalog(mic_code: str) -> list[CatalogInstrument]`.
- Produces: `map_xetra(us_rows, de_rows) -> dict[str, CatalogInstrument]`, keyed by existing Radar ticker.
- Produces: `refresh_mappings(provider, now) -> MappingResult`.

- [ ] **Step 1: Write catalog normalization tests using provider-shaped fixtures**

```python
def test_twelve_data_catalog_keeps_stable_identity_fields():
    rows = provider.stock_catalog('XETR')
    assert rows == [CatalogInstrument(
        symbol='APC', name='Apple Inc', mic='XETR', currency='EUR',
        isin='US0378331005', figi='BBG000B9XRY4')]
```

- [ ] **Step 2: Write mapping tests for Xetra preference and ambiguity rejection**

```python
def test_mapping_joins_same_isin_and_prefers_xetra():
    result = map_xetra([catalog('AAPL', 'XNAS', 'USD', APPLE_ISIN)], [
        catalog('APC', 'XFRA', 'EUR', APPLE_ISIN),
        catalog('APC', 'XETR', 'EUR', APPLE_ISIN),
    ])
    assert result['AAPL'].mic == 'XETR'

def test_mapping_does_not_guess_from_company_name():
    assert map_xetra([catalog('AAA', 'XNAS', 'USD', None)], [
        catalog('AAA', 'XETR', 'EUR', None)]) == {}
```

- [ ] **Step 3: Run tests and confirm the catalog interfaces are absent**

Run: `cd personal_apps && python -m pytest tests/test_radar_instruments.py tests/test_radar_prices.py -q`

- [ ] **Step 4: Add Twelve Data `/stocks` catalog support and Finnhub symbol-directory fallback**

`/stocks` requests use `mic_code=XETR`, `show_plan=true`; catalog parsing keeps
only Common Stock/ETF-like types with `currency='EUR'`. The US catalog is read
for the active universe’s MICs. Finnhub parsing is isolated behind the same
`CatalogInstrument` shape and may supply ISIN when the Twelve Data entitlement
does not. Never log response tokens or API keys.

- [ ] **Step 5: Implement persistence with preserved verified mappings**

In one transaction, upsert verified rows; mark a ticker unavailable only when
the reference request completed successfully and no stable join existed;
leave all old rows untouched on transport/provider failure. Set exactly one
primary Xetra row per company/market.

- [ ] **Step 6: Add a read-only entitlement probe command**

Expose `python run_radar_ingest.py --probe-german-data` returning counts only:
catalog reachable, Xetra rows, rows carrying ISIN, mapped active tickers, quote
sample age/quality. Output must redact keys and omit full catalog payloads.

- [ ] **Step 7: Run catalog/mapping tests**

Run: `cd personal_apps && python -m pytest tests/test_radar_instruments.py tests/test_radar_prices.py -q`

Expected: all pass without network calls.

- [ ] **Step 8: Commit Task 4**

```powershell
git add personal_apps/features/radar/instruments.py personal_apps/features/radar/prices/finnhub.py personal_apps/features/radar/prices/twelvedata.py personal_apps/tests/test_radar_instruments.py personal_apps/tests/test_radar_prices.py personal_apps/run_radar_ingest.py
git commit -m "feat(radar): map verified Xetra instruments"
```

---

### Task 5: Isolate polling, history and retention by market

**Files:**
- Modify: `personal_apps/features/radar/quotes.py`
- Modify: `personal_apps/features/radar/history.py`
- Modify: `personal_apps/features/radar/retention.py`
- Modify: `personal_apps/run_radar_ingest.py`
- Modify: `personal_apps/tests/test_radar_quotes.py`
- Modify: `personal_apps/tests/test_radar_quotes_batch.py`
- Modify: `personal_apps/tests/test_radar_quote_retention.py`
- Modify: `personal_apps/tests/test_radar_history.py`
- Modify: `personal_apps/tests/test_radar_daemon.py`

**Interfaces:**
- Produces: `record_quotes(quotes, now)` persisting normalized market identity.
- Produces: `statuses_for(instruments, now)` and `moves_for(instruments, hours, now)` keyed by `(ticker, market)`.
- Produces: history reads/writes keyed by `(ticker, market, mic)`.
- Preserves: US polling cadence and provider rate limits.

- [ ] **Step 1: Add failing cross-market isolation tests**

```python
def test_latest_quote_does_not_cross_market(clean_quotes):
    store_quote('AAPL', 'us', 'XNAS', 'USD', price='220', at=NOW)
    store_quote('AAPL', 'de', 'XETR', 'EUR', price='194', at=NOW)
    assert latest('AAPL', 'de', NOW).price == decimal.Decimal('194')

def test_retention_keeps_required_snapshots_per_market(clean_quotes):
    seed_many_quotes('AAPL', markets=('us', 'de'))
    prune_quotes(NOW, keep=3)
    assert count_quotes('AAPL', 'us') == 3
    assert count_quotes('AAPL', 'de') == 3
```

- [ ] **Step 2: Add failing daemon tests for independent partial failure**

```python
def test_german_quote_failure_does_not_block_us_quotes(monkeypatch):
    providers = fake_market_providers(de_error=PriceUnavailable('denied'))
    result = daemon.quote_cycle(providers, NOW)
    assert result.us_stored == 2
    assert result.de_stored == 0
```

- [ ] **Step 3: Run focused tests and confirm current ticker-only reads leak markets**

Run: `cd personal_apps && python -m pytest tests/test_radar_quotes.py tests/test_radar_quotes_batch.py tests/test_radar_quote_retention.py tests/test_radar_history.py tests/test_radar_daemon.py -q`

- [ ] **Step 4: Thread instrument identity through quote/history SQL**

Every filter, window partition, uniqueness key and retention partition that
currently uses `ticker` must use `ticker + market + mic`. Keep social buckets
ticker-only. Daily sigma remains based on the US primary series until Task 6
requests the market-specific series explicitly.

- [ ] **Step 5: Poll primary US and mapped DE instruments in bounded batches**

Keep the existing US cap/cadence. German polling receives its own cap and does
not steal US calls. The mapping refresh runs weekly before German polling; an
empty/failed catalog does not delete mappings. Quote results are recorded per
instrument and partial results commit normally.

- [ ] **Step 6: Request MIC-qualified German daily history**

Extend `daily_closes(symbol, days, mic_code=None)` so German calls pass
`mic_code='XETR'`. Store EUR history separately. A provider status other than
`ok` leaves existing history unchanged and records no zero rows.

- [ ] **Step 7: Run focused suites**

Run the command from Step 3.

Expected: all pass.

- [ ] **Step 8: Commit Task 5**

```powershell
git add personal_apps/features/radar/quotes.py personal_apps/features/radar/history.py personal_apps/features/radar/retention.py personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_quotes.py personal_apps/tests/test_radar_quotes_batch.py personal_apps/tests/test_radar_quote_retention.py personal_apps/tests/test_radar_history.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): ingest prices per market"
```

---

### Task 6: Make ranking, board, detail and API market-aware

**Files:**
- Modify: `personal_apps/features/radar/leaderboard.py`
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/detail.py`
- Modify: `personal_apps/features/radar/detail_panel.py`
- Modify: `personal_apps/features/radar/phrasing.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/features/radar/routes/views.py`
- Modify: `personal_apps/tests/test_radar_leaderboard.py`
- Modify: `personal_apps/tests/test_radar_board.py`
- Modify: `personal_apps/tests/test_radar_detail.py`
- Modify: `personal_apps/tests/test_radar_api.py`
- Modify: `personal_apps/tests/test_radar_phrasing.py`

**Interfaces:**
- Adds: `Query.market: str` defaulting to `us`.
- Adds: `Board.market`, `.display_timezone`; each `Row` owns `quote: QuoteView`.
- Adds: `board.build(sources, now, window_hours=4, segments=(), limit=50,
  leads=3, min_venues=1, market='us')` and
  `detail_panel.build(ticker, sources, now, window_hours=4, span='1M',
  market='us')`.
- Serializes: nested `quote` object while retaining legacy US flat fields.

- [ ] **Step 1: Pin query compatibility and invalid market behaviour**

```python
def test_market_defaults_to_us():
    assert parse_query(MultiDict()).market == 'us'

def test_api_rejects_unknown_market(client):
    assert client.get('/radar/api/board?market=moon').status_code == 400

def test_human_page_bad_market_falls_back_to_us(client):
    response = client.get('/radar/?market=moon')
    assert response.status_code == 200
    assert b'"market": "us"' in response.data
```

- [ ] **Step 2: Add board/detail fallback and stale-score tests**

```python
def test_germany_board_serializes_us_fallback(client, seeded_us_only_quote):
    row = client.get('/radar/api/board?market=de').get_json()['rows'][0]
    assert row['quote']['is_fallback'] is True
    assert row['quote']['currency'] == 'USD'

def test_eod_german_quote_cannot_produce_divergence(seeded_de_eod_quote):
    row = build_rows(['bluesky'], NOW, window_hours=4,
                     segments=(), limit=50, market='de').rows[0]
    assert row.divergence is None
    assert row.quote.quality == 'eod'
```

- [ ] **Step 3: Run focused suites and confirm market is not yet accepted**

Run: `cd personal_apps && python -m pytest tests/test_radar_leaderboard.py tests/test_radar_board.py tests/test_radar_detail.py tests/test_radar_api.py tests/test_radar_phrasing.py -q`

- [ ] **Step 4: Thread `market` through query/build calls and select per-row quotes**

Remove the global-session assumption from ranking. The board may expose an
aggregate header session for its requested market, but ranking and row copy use
`row.quote.session` and `row.quote.score_eligible`. A fallback row therefore
uses US calendar semantics inside Germany mode.

- [ ] **Step 5: Serialize the nested quote contract**

```python
def _quote(view):
    return {
        'market': view.market, 'venue': view.venue, 'mic': view.mic,
        'currency': view.currency, 'price': _decimal_or_none(view.price),
        'regular_move': _decimal_or_none(view.regular_move),
        'extended_move': _decimal_or_none(view.extended_move),
        'session': view.session, 'quality': view.quality,
        'age_seconds': view.age_seconds,
        'quoted_at': _iso_z(view.quoted_at),
        'is_fallback': view.is_fallback,
    }
```

Set board-level `market` and `display_timezone='Europe/Berlin'`. Keep
`generated_at` and every quote/post/chart instant as explicit-Z ISO.

- [ ] **Step 6: Keep chart history within the selected market**

Intraday chart reads market/MIC quotes. Daily chart reads market/MIC closes.
If DE history is absent, return null/not-measured German history; never splice
US USD history into a German EUR chart. A US-fallback detail intentionally
requests and labels US history.

- [ ] **Step 7: Run focused backend suites**

Run the command from Step 3.

Expected: all pass.

- [ ] **Step 8: Commit Task 6**

```powershell
git add personal_apps/features/radar/leaderboard.py personal_apps/features/radar/board.py personal_apps/features/radar/detail.py personal_apps/features/radar/detail_panel.py personal_apps/features/radar/phrasing.py personal_apps/features/radar/routes personal_apps/tests/test_radar_leaderboard.py personal_apps/tests/test_radar_board.py personal_apps/tests/test_radar_detail.py personal_apps/tests/test_radar_api.py personal_apps/tests/test_radar_phrasing.py
git commit -m "feat(radar): serve market-specific boards"
```

---

### Task 7: Add typed market selection and Berlin formatting

**Files:**
- Modify: `personal_apps/static/radar/src/types.ts`
- Modify: `personal_apps/static/radar/src/api.ts`
- Modify: `personal_apps/static/radar/src/board/BoardPage.tsx`
- Create: `personal_apps/static/radar/src/board/MarketSwitch.tsx`
- Modify: `personal_apps/static/radar/src/board/Controls.tsx`
- Modify: `personal_apps/static/radar/src/format.ts`
- Modify: `personal_apps/static/radar/src/format.test.ts`
- Modify: `personal_apps/static/radar/src/board/BoardPage.test.tsx`
- Modify: `personal_apps/static/radar/src/hardening.test.tsx`

**Interfaces:**
- Adds: `Market = 'us' | 'de'`, `Quote`, and `QuoteQuality` TypeScript types.
- Adds: `Selection.market` and `BoardPayload.market`.
- Produces: `formatMarketTime`, `formatPostStamp`, `formatPrice`, `formatQuoteAge` with explicit timezone/currency arguments.

- [ ] **Step 1: Write Berlin/DST and currency formatting tests**

```typescript
it('formats the same UTC instant in Berlin summer time', () => {
  expect(stampTime('2026-08-28T19:04:11Z')).toBe('21:04 CEST')
})

it('formats Berlin winter time without using the machine timezone', () => {
  expect(stampTime('2026-01-28T19:04:11Z')).toBe('20:04 CET')
})

it('formats venue currency explicitly', () => {
  expect(money(194.2, 'EUR')).toBe('194,20 €')
  expect(money(220.5, 'USD', { explicitCode: true }))
    .toBe('220,50 $ · USD')
})
```

- [ ] **Step 2: Write market-switch URL and retention tests**

```typescript
it('switches market while retaining ticker and filters', async () => {
  await user.click(screen.getByRole('radio', { name: 'Germany' }))
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining('market=de'), expect.anything())
  expect(window.location.search).toContain('t=AAPL')
  expect(window.location.search).toContain('window=4')
})
```

- [ ] **Step 3: Run Radar frontend tests and confirm current UTC/fixed-USD expectations fail**

Run: `cd personal_apps && npm test -- --runInBand`

If Vitest rejects the Jest-only flag, run the repository command `npm test`; do not change test concurrency to make assertions pass.

- [ ] **Step 4: Add market/quote types and include market in every request/query key**

```typescript
export type Market = 'us' | 'de'
export type QuoteQuality = 'live' | 'delayed' | 'eod' | 'stale' | 'unavailable'

export interface MarketQuote {
  market: Market; venue: string | null; mic: string | null; currency: string
  price: number | null; regular_move: number | null; extended_move: number | null
  session: Session; quality: QuoteQuality; age_seconds: number | null
  quoted_at: string | null; is_fallback: boolean
}
```

`queryFor`, `fetchBoard`, `fetchDetail`, selection state and URL replacement all
carry market. The embedded payload initializes it, defaulting legacy embedded
payloads to US at the boundary.

- [ ] **Step 5: Implement the accessible segmented market control**

Use a fieldset/radiogroup with `US` and `Germany`, visible in the board header.
It must keep selected ticker and panel span; market changes refetch board and
detail but source/segment/window/venue controls remain unchanged.

- [ ] **Step 6: Replace UTC/date and USD-only helpers with fixed Berlin/currency helpers**

Use `Intl.DateTimeFormat('de-DE', { timeZone: 'Europe/Berlin', hour: '2-digit',
minute: '2-digit', hour12: false, timeZoneName: 'short' })`. Do not
use browser-local getters. Include `CET`/`CEST` through `timeZoneName: 'short'`.
Post stamps include German-local date and time; invalid inputs still return the
existing unknown marker.

- [ ] **Step 7: Run frontend tests**

Run: `cd personal_apps && npm test`

Expected: existing 539 tests plus new tests pass.

- [ ] **Step 8: Commit Task 7**

```powershell
git add personal_apps/static/radar/src/types.ts personal_apps/static/radar/src/api.ts personal_apps/static/radar/src/board personal_apps/static/radar/src/format.ts personal_apps/static/radar/src/format.test.ts personal_apps/static/radar/src/hardening.test.tsx
git commit -m "feat(radar): add market switch and Berlin time"
```

---

### Task 8: Present quote source, quality and extended movement

**Files:**
- Modify: `personal_apps/static/radar/src/list/ListPane.tsx`
- Modify: `personal_apps/static/radar/src/list/TickerRow.tsx`
- Modify: `personal_apps/static/radar/src/list/TickerRow.test.tsx`
- Modify: `personal_apps/static/radar/src/detail/Identity.tsx`
- Modify: `personal_apps/static/radar/src/detail/DetailPane.tsx`
- Modify: `personal_apps/static/radar/src/hardening.test.tsx`
- Modify: `personal_apps/static/radar/src/entries/board.tsx` or the Radar stylesheet imported there.

**Interfaces:**
- Consumes: `MarketQuote` from Task 7.
- Produces: accessible `QuoteBadges` treatment reused by list and identity.

- [ ] **Step 1: Add failing visible-state tests**

```typescript
it('marks a US fallback without hiding its currency', () => {
  renderRow({ quote: quote({ market: 'us', currency: 'USD', is_fallback: true }) })
  expect(screen.getByText('US fallback · Nasdaq · USD')).toBeVisible()
})

it('separates regular and after-hours movement', () => {
  renderIdentity({ quote: quote({ regular_move: .012, extended_move: -.004,
                                  session: 'afterhours' }) })
  expect(screen.getByText('+1,20 % regular')).toBeVisible()
  expect(screen.getByText('−0,40 % after hours')).toBeVisible()
})

it('names delayed and EOD prices', () => {
  renderRow({ quote: quote({ quality: 'delayed', age_seconds: 720 }) })
  expect(screen.getByText('12 min delayed')).toBeVisible()
})
```

- [ ] **Step 2: Run the focused component tests and confirm missing quote UI**

Run: `cd personal_apps && npx vitest run -c vite.radar.config.ts static/radar/src/list/TickerRow.test.tsx static/radar/src/hardening.test.tsx`

- [ ] **Step 3: Implement shared semantic badge rendering**

Fallback uses a neutral outlined warning. Delayed/EOD/stale states always show
text. Premarket uses an amber clock plus `Pre-market`; after-hours uses a
violet moon plus `After hours`; regular uses a neutral venue label. Icons are
`aria-hidden` only when adjacent text names the state.

- [ ] **Step 4: Update list ranking explanations for per-row sessions**

`TickerRow` reads `row.quote.score` fields serialized by the server and does
not infer eligibility from board-level session. Board-level copy describes the
selected market; fallback rows explain their own US session locally.

- [ ] **Step 5: Add CSS using existing Radar tokens**

Do not introduce a second green/red meaning. Define neutral fallback outline,
amber premarket and violet after-hours custom properties for light/dark themes;
preserve reduced motion and print hiding rules.

- [ ] **Step 6: Run Radar frontend tests**

Run: `cd personal_apps && npm test`

Expected: all pass.

- [ ] **Step 7: Commit Task 8**

```powershell
git add personal_apps/static/radar/src/list personal_apps/static/radar/src/detail/Identity.tsx personal_apps/static/radar/src/detail/DetailPane.tsx personal_apps/static/radar/src/hardening.test.tsx personal_apps/static/radar/src/entries/board.tsx personal_apps/static/radar/src/**/*.css
git commit -m "feat(radar): show quote venue and session moves"
```

---

### Task 9: Shade chart sessions and format chart time in Berlin

**Files:**
- Create: `personal_apps/static/radar/src/detail/SessionBands.tsx`
- Modify: `personal_apps/static/radar/src/detail/PriceChart.tsx`
- Modify: `personal_apps/static/radar/src/detail/PriceChart.test.tsx`
- Modify: `personal_apps/static/radar/src/types.ts`
- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Adds: chart `sessions: Array<{start: string; end: string; kind: Session}>` for intraday spans.
- Produces: `SessionBands` SVG background/labels clipped to the chart plot.

- [ ] **Step 1: Add failing API session-interval test**

```python
def test_intraday_chart_serializes_market_session_intervals(de_detail):
    chart = serialize_detail(de_detail)['chart']
    assert chart['sessions'][0] == {
        'start': '2026-08-28T06:00:00Z',
        'end': '2026-08-28T06:55:00Z',
        'kind': 'premarket',
    }
```

- [ ] **Step 2: Add failing chart rendering/time tests**

```typescript
it('labels chart ticks in Berlin rather than UTC', () => {
  render(<PriceChart chart={intradayAt('2026-08-28T19:00:00Z')} />)
  expect(screen.getByText(/21:00/)).toBeInTheDocument()
})

it('renders named extended-session bands', () => {
  const { container } = render(<PriceChart chart={chartWithSessions()} />)
  expect(container.querySelector('[data-session="afterhours"]')).not.toBeNull()
  expect(screen.getByText('After hours')).toBeInTheDocument()
})
```

- [ ] **Step 3: Run focused API/chart tests and confirm they fail**

Run backend: `cd personal_apps && python -m pytest tests/test_radar_api.py -q`

Run frontend: `cd personal_apps && npx vitest run -c vite.radar.config.ts static/radar/src/detail/PriceChart.test.tsx`

- [ ] **Step 4: Serialize exact session intervals for intraday spans**

Use the selected quote market/MIC calendar. Clip intervals to chart start/end.
Daily spans send an empty session list because shading hundreds of daily
regular windows is noise rather than context.

- [ ] **Step 5: Render clipped bands and Berlin tick labels**

Draw bands behind price/chatter paths. Premarket and after-hours use the same
amber/violet tokens as badges, at low opacity. Add one label per contiguous
band when width permits; expose full names to screen readers even when narrow
visual labels are omitted.

- [ ] **Step 6: Run backend and frontend focused tests**

Run both commands from Step 3.

Expected: all pass.

- [ ] **Step 7: Commit Task 9**

```powershell
git add personal_apps/features/radar/routes/api.py personal_apps/tests/test_radar_api.py personal_apps/static/radar/src/detail/SessionBands.tsx personal_apps/static/radar/src/detail/PriceChart.tsx personal_apps/static/radar/src/detail/PriceChart.test.tsx personal_apps/static/radar/src/types.ts
git commit -m "feat(radar): mark extended chart sessions"
```

---

### Task 10: Full verification, provider probe and deployment handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-08-28-radar-german-market-ledger.md`
- Modify: `HANDOFF.md`
- Create: `.artifacts/radar-german-market/` screenshots and probe output locally only; do not commit secrets or generated assets.

**Interfaces:**
- Consumes all previous tasks.
- Produces an evidence-complete branch ready for independent review and merge.

- [ ] **Step 1: Run backend tests under an isolated test database**

Use the repository’s test DB override rather than the shared development DB.
Run all Radar tests from `personal_apps` using an explicit file list so
PowerShell does not pass an unexpanded glob:

```powershell
$radarTests = Get-ChildItem tests/test_radar_*.py | ForEach-Object FullName
python -m pytest $radarTests -q
```

Expected: all pass. If the known profile tests still see production rows, fix
the test DB configuration/fixture isolation before accepting the result; do not
change profile assertions as part of this feature.

- [ ] **Step 2: Run frontend tests and production build**

```powershell
cd personal_apps
npm test
npm run build
```

Expected: all existing and new tests pass; both Vite manifests build.

- [ ] **Step 3: Run the redacted provider probe**

Run: `cd personal_apps && python run_radar_ingest.py --probe-german-data`.

Record only provider names, entitlement status, catalog/mapping counts, sample
venue/currency, quote age and quality in the ledger. If German intraday access
is unavailable, verify Germany mode uses marked US fallbacks and EOD Xetra data
is never labelled live.

- [ ] **Step 4: Run one batched Playwright visual audit**

Start the local app using its documented test/development command, then use one
Python Playwright script to capture desktop 1440×1000 and mobile 390×844 in
light/dark themes plus print. Check:

```python
assert await page.locator('body').evaluate(
    '(el) => el.scrollWidth <= el.clientWidth')
assert await page.locator('[role="radiogroup"]').is_visible()
assert len(console_errors) == 0
```

Capture US regular, US after-hours fixture, Germany Xetra quote, and Germany US
fallback. Inspect the PNGs with the local image viewer.

- [ ] **Step 5: Run diff hygiene and secret checks**

```powershell
git diff --check main...HEAD
git status --short
git diff --stat main...HEAD
rg -n "FINNHUB_API_KEY=|TWELVEDATA_API_KEY=|token=[A-Za-z0-9]" docs HANDOFF.md personal_apps
```

Expected: clean diff, only intentional tracked changes, no secret values.

- [ ] **Step 6: Perform independent read-only review**

Reviewer reads spec, ledger, handoff, every commit/diff and verification output.
They report findings by priority with exact file/line evidence. The implementer
resolves accepted findings with focused tests and separate commits; record
rulings and evidence in the ledger.

- [ ] **Step 7: Update durable handoff artifacts**

Set exact worktree, branch, HEAD, dirty files/ownership, accepted tasks,
remaining findings, tests/results, provider entitlement result, deploy carries,
and immediate next action. Evidence must match Git at the time of writing.

- [ ] **Step 8: Final integration decision**

Only after the independent review is clean and all required gates pass, use
`superpowers:finishing-a-development-branch` to offer merge/push choices. Do
not merge or deploy merely because implementation tasks are complete.

---

## Plan self-review record

- Spec coverage: storage, calendars, mapping, provider normalization, polling,
  ranking/API, market switch, Berlin formatting, quote quality, extended UI,
  chart shading, compatibility, error handling, migration and deployment gates
  each map to at least one task.
- Scope: EIX scraping, FX synthesis, broker integration, German-issuer universe,
  full localization and paid-feed purchase remain excluded.
- Type consistency: backend uses `market`, `mic`, `currency`, `provider_symbol`,
  nested `quote`; frontend uses `Market`, `MarketQuote`, `QuoteQuality`; session
  vocabulary remains `premarket | regular | afterhours | closed`.
- Placeholder scan: implementation decisions and failure behaviour are explicit;
  the migration revision filename is intentionally generated by Alembic and is
  the only runtime-generated path.
- Cross-agent safety: every task is independently testable/committable and the
  ledger/handoff rule prevents completed tasks from being re-dispatched.
