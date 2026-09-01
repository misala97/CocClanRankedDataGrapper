# Radar Market Data v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Radar's unusable German-price path with delayed Deutsche Börse Tradegate/Xetra data, keep Finnhub as the US quote source while moving US daily closes to Massive's free grouped endpoint (Yahoo chart stays a flag-gated fallback and the German history backfill proxy), and backfill/accumulate truthful venue-aware history without interrupting the live board.

**Architecture:** Keep the existing social ticker, `RadarInstrument`, market-aware quote/history tables, board market switch, and `QuoteView` boundary. Add versioned German mappings, provider provenance, a correction-aware delayed-file collector, Yahoo and Massive grouped-close adapters `[A1]`, and shadow rows that existing readers cannot see; activate Germany, US quotes, and US closes independently only after their gates pass.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy/Alembic, MySQL 8 dev / MariaDB production, `requests`, APScheduler, gzip/JSON and stdlib HTML parsing, React 19, TypeScript 5.7, Vitest/Testing Library, Vite.

**Spec:** `docs/superpowers/specs/2026-08-31-radar-market-data-v2-design.md`

**Amendments:** the spec's Amendment log (2026-09-01) applies. Markers
`[A1]` (Massive grouped US closes), `[A2]` (Finnhub stays the US quote
source; Yahoo US = fallback), and `[A3]` (1D event-time slotting, session-
gated US polling) tag every amended passage in this plan; Task 4b is new.

**Codex amendment-review corrections (2026-09-01, binding):** implement the
three accepted provider amendments with the tightened contracts in the spec:
exact mapped-provider-symbol identity, dedicated grouped-day and post-close
session state, one split-only history basis, non-vacuous/full-backfill gating,
live Finnhub provenance, and exact event-identity deduplication. Later task
text cannot weaken these constraints.

## Global Constraints

- Branch is `dev_personal`; commit after every accepted task. Only `main` deploys, and Michi controls deployment.
- At execution time, create an isolated worktree with `superpowers:using-git-worktrees`; record its exact path/branch in the ledger rather than inventing one in advance.
- Current Alembic head before this plan is `f4b2d81c37a9`.
- Preserve the user's unrelated tracked changes in `personal_apps/scripts/discover_telegram_sources.py` and `personal_apps/telegram_candidates.json`, plus all unrelated untracked scratch work.
- Recurring market-data provider cost is exactly EUR 0.
- Germany uses delayed Deutsche Börse data: prefer `XGAT`, otherwise `XETR`. One ticker is pinned to one verified German venue between mapping generations.
- `[A2]` US quotes stay on Finnhub (`RADAR_US_PRICE_PROVIDER` default `finnhub`; the `yahoo` value is a fallback, not a planned activation) on the established five-minute cadence, session-gated plus one durably claimed post-close cycle. Finnhub writes `source='finnhub'`, `price_basis='trade'`, `provider_delay='live'`. Yahoo access uses the per-symbol chart endpoint only; never depend on Yahoo's `/v7/finance/quote` batch endpoint.
- `[A1]` US daily closes come from Massive's free grouped-daily endpoint (`source='massive_grouped'`, `adjustment_basis='split'`, whole-universe, one call per trading day) behind `RADAR_US_CLOSE_SOURCE=legacy|shadow|massive` (default `legacy`; `shadow` ingests grouped days as shadow rows for the agreement gate while Twelve Data keeps writing live rows). Exact mapped primary US `RadarInstrument.provider_symbol` drives identity; `universe.load_lookup()` must never drive grouped writes. Operator provisions the free key as `RADAR_MASSIVE_API_KEY`; base URL is config (`RADAR_MASSIVE_BASE_URL`, default `https://api.massive.com`; `https://api.polygon.io` is the legacy value, announced for phase-out during 2026).
- `[A1]` Shadow cleanup additionally requires valid `RADAR_US_CLOSE_ACTIVATED_AT`, `RADAR_US_CLOSE_GATE_REPORT_SHA256`, and `RADAR_US_CLOSE_GATE_AUDIT_SHA256`; absent/malformed evidence disables cleanup.
- `[A3]` Intraday chart spans slot prints by provider event time (quote_ts), never by fetch time. `[A1]` Daily closes older than the widest chart span (calendar days, not `HISTORY_DAYS` trading days) plus a buffer are pruned — native `deutsche_boerse_delayed` rows excepted — so universe-wide ingestion stays bounded.
- Never synthesize a German price with FX, fuzzy-map a company name, relabel Xetra history as Tradegate, or let a transient feed failure switch venue.
- UTC remains storage/wire time. German calendar/display time is `Europe/Berlin`.
- Provider event time, fetch time, venue, currency, source, and price basis remain distinct.
- `trade`, `midpoint`, and `close` are the only price bases. A midpoint is displayable as `indicative` but never divergence-eligible.
- Only a fresh executed trade (`age <= 1,800` seconds), a moving tape, and a non-fallback instrument may produce price divergence.
- German shadow mappings, quotes, and closes must be persisted for measurement but excluded from every live board/detail/history read.
- A structural file failure never advances its cursor. One invalid instrument does not discard the other valid instruments in a structurally valid file.
- Tasks 2 onward must not invent Deutsche Börse JSON fields. Task 1 produces the literal observed field/path contract and is a hard review checkpoint.
- Every stage deploys safely by itself. Provider flags default to the current live behavior until the corresponding activation gate passes.
- Create the execution ledger before Task 1 and update both it and `HANDOFF.md` after every accepted task/review, not only at the final gate.
- Tests use the established real dev MySQL database unless a migration/parser test explicitly creates an isolated SQLite schema.
- German activation requires: 50/50 audited identities correct, mapping coverage at least 90%, display coverage at least 95%, p95 provider-event age at most 1,800 seconds, deterministic transport success at least 99%, and history coverage at least 95%; any truth violation blocks activation regardless of percentages.
- Do not commit raw Deutsche Börse payloads, access cookies, acceptance artifacts, Yahoo payload dumps, or API keys.

---

## File map

### New files

| File | Responsibility |
|---|---|
| `personal_apps/scripts/capture_deutsche_boerse_contract.py` | Read four operator-downloaded `.json.gz` files, enforce archive limits, and emit a redacted structural report without database writes |
| `personal_apps/tests/test_capture_deutsche_boerse_contract.py` | Capture archive limits, structure redaction, and no-network/no-database tests |
| `docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md` | Literal, reviewed upstream paths/event semantics captured in Task 1; required input to Task 5 |
| `personal_apps/tests/fixtures/radar_market_data/*.json` | Tiny hand-authored payloads using observed keys and fake identifiers/prices |
| `personal_apps/features/radar/prices/yahoo.py` | Yahoo chart HTTP, identity validation, current quote and daily-close normalization |
| `personal_apps/features/radar/prices/massive.py` | `[A1]` Massive grouped-daily HTTP and provider-symbol-keyed payload validation; no database identity join or cursor ownership |
| `personal_apps/tests/test_radar_massive.py` | `[A1]` Grouped payload/date/duplicate validation, per-row containment, pacing, and quota/backoff tests |
| `personal_apps/features/radar/prices/openfigi.py` | OpenFIGI batching and exact share-class-to-MIC candidate lookup |
| `personal_apps/features/radar/prices/deutsche_boerse.py` | Terms-cookie transport, file listing/download limits, observed JSON parsing, corrections, reference rows, and venue quote selection |
| `personal_apps/features/radar/market_calendars/tradegate.py` | `XGAT` 07:30–22:00 Berlin session boundaries |
| `personal_apps/features/radar/market_data.py` | Active-candidate selection, cursor/cycle transactions, German collection, native close materialization, exact grouped-instrument join/state, post-close claims, and provider-independent orchestration |
| `personal_apps/features/radar/data/german_instrument_overrides.json` | Small audited ADR/issuer exception set; exact identifiers and evidence only |
| `personal_apps/migrations/versions/6a21d4e8c9f0_add_radar_market_data_v2.py` | Expand-only provenance, adjustment, shadow, cursor, cycle, trade-event, grouped-day, provider-session, and mapping-generation schema |
| `personal_apps/scripts/backfill_radar_market_history.py` | Resumable Yahoo US/Xetra history backfill with dry-run/apply modes |
| `personal_apps/scripts/report_radar_market_data_shadow.py` | READ ONLY activation-gate report and 50-instrument identity-audit export |
| `personal_apps/tests/test_radar_yahoo.py` | Yahoo identity, backoff, quote, and history tests |
| `personal_apps/tests/test_radar_openfigi.py` | Share-class/MIC batching and refusal tests |
| `personal_apps/tests/test_radar_deutsche_boerse.py` | Delayed-file transport/parser/correction/selection safety tests |
| `personal_apps/tests/test_radar_market_data.py` | Shadow visibility, cursor transactions, mapping generations, collection, and native-close tests |
| `personal_apps/tests/test_radar_market_data_report.py` | Read-only shadow-report thresholds and no-mutation guard |
| `personal_apps/migrations/versions/b742e9d13c60_contract_radar_market_data_v2.py` | Post-rollback-window NOT NULL contraction; Task 12 only |
| `docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md` | Per-task commit, review, test, deployment-carry, and gate state during execution |

### Existing files with changed responsibility

| File | Change |
|---|---|
| `personal_apps/models.py` | Add provenance/shadow/adjustment fields and six operational models |
| `personal_apps/features/radar/prices/__init__.py` | Extend provider-neutral `Quote`; centralize positive-price/book/source/basis validation |
| `personal_apps/features/radar/instruments.py` | Replace Twelve/Finnhub catalog mapping with complete-generation build/activate/rollback logic |
| `personal_apps/features/radar/markets.py` | Remove Xetra hard-code; carry basis/source/book; forbid midpoint/fallback scoring |
| `personal_apps/features/radar/market_calendars/__init__.py`, `de.py` | Select German calendar by MIC while retaining Xetra behavior |
| `personal_apps/features/radar/quotes.py` | Persist provenance, exclude shadow rows, and preserve the pinned venue through stale states |
| `personal_apps/features/radar/history.py` | Source-priority writes, shadow exclusion, Xetra→Tradegate proxy seam, and history metadata |
| `personal_apps/features/radar/leaderboard.py` | Reuse chatter-only candidate discovery and calculate sigma from selected native/proxy series |
| `personal_apps/features/radar/detail.py`, `detail_panel.py` | Carry chart proxy metadata and select history for the quote's exact identity |
| `personal_apps/features/radar/board.py` | Tradegate Germany header/calendar boundary |
| `personal_apps/features/radar/routes/api.py` | Serialize source, basis, bid/ask, eligibility, and chart proxy fields |
| `personal_apps/features/radar/config.py` | Independent `legacy|shadow|active` German, `finnhub|yahoo` US-quote, and `legacy|shadow|massive` US-close flags `[A1]` plus bounded provider settings |
| `personal_apps/run_radar_ingest.py` | Independent session-gated Finnhub US quote, Deutsche Börse collection, daily Massive grouped-close, and Yahoo-fallback jobs `[A1]``[A2]``[A3]`; legacy defaults remain |
| `personal_apps/features/radar/retention.py` | Prune operational cycles/trade events plus bounded daily-close retention `[A1]` while preserving cursor and mapping generations |
| `personal_apps/static/radar/src/types.ts` | Quote basis/source/book and chart proxy types |
| `personal_apps/static/radar/src/QuoteBadges.tsx` | Tradegate/Xetra source, `indicative`, age, and fallback copy |
| `personal_apps/static/radar/src/detail/PriceChart.tsx` | Visible Xetra-proxy/Tradegate seam label |
| `personal_apps/static/radar/radar.css` | Indicative/proxy styles that do not reuse direction colors |
| Existing Radar tests | Compatibility, migration, scheduling, board/detail, history, retention, and UI regressions |

---

### Task 1: Capture and freeze the Deutsche Börse provider contract

This task is an empirical/legal gate, not a parser implementation. The operator
accepts the terms and downloads the latest `DGAT-pretrade`, `DGAT-posttrade`,
`DETR-pretrade`, and `DETR-posttrade` files. No later task starts until the
contract supplement and sanitized fixtures receive a read-only review.

**Files:**
- Create: `personal_apps/scripts/capture_deutsche_boerse_contract.py`
- Create: `personal_apps/tests/test_capture_deutsche_boerse_contract.py`
- Create: `docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md`
- Create after measurement: `docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md`
- Create after measurement: `personal_apps/tests/fixtures/radar_market_data/xgat_pretrade.json`
- Create after measurement: `personal_apps/tests/fixtures/radar_market_data/xgat_posttrade.json`
- Create after measurement: `personal_apps/tests/fixtures/radar_market_data/xetr_pretrade.json`
- Create after measurement: `personal_apps/tests/fixtures/radar_market_data/xetr_posttrade.json`

**Interfaces:**
- Produces: `inspect_archive(path: pathlib.Path, *, max_compressed=52_428_800, max_uncompressed=262_144_000, max_ratio=100) -> ArchiveReport`.
- Produces: CLI JSON containing file SHA-256, byte counts, top-level type, every JSON path/type/count, timestamp-shaped paths, identifier-shaped paths, and no raw prices/identifiers.
- Produces: the reviewed contract supplement with exact JSON pointers for records, MIC, ISIN/stable ID, local mnemonic, currency, security type, event ID, original-event ID, event action, event timestamp, price, volume, bid, ask, and official-close marker or an explicit `absent` ruling.

- [ ] **Step 0: Create the execution ledger before provider work**

Record worktree path, branch, starting HEAD, protected dirty files, spec/plan
commit IDs, Task 1 as in progress, and empty columns for implementation commit,
focused tests, independent review, findings, and next action. Update
`HANDOFF.md` with the same exact workspace evidence.

- [ ] **Step 1: Write archive-safety and redaction tests**

```python
def test_capture_rejects_a_decompression_bomb(tmp_path):
    archive = tmp_path / 'large.json.gz'
    with gzip.open(archive, 'wb') as handle:
        handle.write(b'[' + b' ' * 10_000 + b']')
    with pytest.raises(CaptureError, match='decompression ratio'):
        inspect_archive(archive, max_uncompressed=20_000, max_ratio=2)


def test_capture_reports_structure_without_market_values(tmp_path):
    archive = tmp_path / 'sample.json.gz'
    payload = {'rows': [{'ISIN': 'DE000FAKE001', 'price': 123.45,
                         'timestamp': '2026-08-31T12:43:00Z'}]}
    with gzip.open(archive, 'wt', encoding='utf-8') as handle:
        json.dump(payload, handle)
    report = inspect_archive(archive)
    encoded = json.dumps(dataclasses.asdict(report), sort_keys=True)
    assert '/rows/*/ISIN' in encoded
    assert 'DE000FAKE001' not in encoded
    assert '123.45' not in encoded
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_capture_deutsche_boerse_contract.py -q`

Expected: FAIL because the script and `CaptureError` do not exist.

- [ ] **Step 3: Implement bounded gzip/JSON inspection**

Implement streaming compressed-byte accounting, bounded decompression, one
JSON decode, recursive structural traversal, and value redaction. The core
result types are fixed:

```python
@dataclasses.dataclass(frozen=True)
class PathShape:
    path: str
    types: tuple[str, ...]
    occurrences: int


@dataclasses.dataclass(frozen=True)
class ArchiveReport:
    filename: str
    sha256: str
    compressed_bytes: int
    uncompressed_bytes: int
    top_level_type: str
    paths: tuple[PathShape, ...]
    timestamp_paths: tuple[str, ...]
    identifier_paths: tuple[str, ...]
```

The CLI takes exactly four named inputs plus `--output`; stdout is also the
same JSON. It must never perform an HTTP request or database import.

- [ ] **Step 4: Prove the script is read-only and passes its tests**

Run: `cd personal_apps && python -m pytest tests/test_capture_deutsche_boerse_contract.py -q`

Expected: PASS. Run `rg -n "requests|extensions|models|db\." scripts/capture_deutsche_boerse_contract.py` and expect no matches.

- [ ] **Step 5: Operator accepts terms and downloads four current files**

Michi opens the official `DGAT` and `DETR` pre/post file-service pages, reads
and accepts the displayed terms, and downloads one current `.json.gz` from
each. The worker does not click acceptance, copy browser cookies, or commit the
downloads. Record the four absolute local paths only in the terminal command,
not a repository file.

- [ ] **Step 6: Produce and inspect the structural report**

Run:

```powershell
cd personal_apps
$xgatPre = Read-Host 'Absolute path to the downloaded DGAT pre-trade file'
$xgatPost = Read-Host 'Absolute path to the downloaded DGAT post-trade file'
$xetrPre = Read-Host 'Absolute path to the downloaded DETR pre-trade file'
$xetrPost = Read-Host 'Absolute path to the downloaded DETR post-trade file'
python -m scripts.capture_deutsche_boerse_contract `
  --xgat-pre $xgatPre `
  --xgat-post $xgatPost `
  --xetr-pre $xetrPre `
  --xetr-post $xetrPost `
  --output $env:TEMP\radar-dbag-contract-report.json
```

Expected: four SHA-256s and structural path inventories; no actual ISIN,
mnemonic, price, bid, ask, cookie, or trade ID appears in the report.

- [ ] **Step 7: Write the literal provider-contract supplement**

The supplement records one table per `(MIC, channel)` with the exact observed
JSON pointer and observed type for every semantic field listed under
Interfaces. It also records the exact index URL, file-link form, filename time
format, UTC behavior, whether each file is a full snapshot or delta, ordering,
correction/cancellation behavior, completeness of the reference universe,
compressed/uncompressed size, and parse time. Write `absent` where the source
does not carry a semantic field; do not infer it.

The final section contains one of two binding outcomes:

```text
PASS — stable identity, provider event time, and sufficient trade/book data
were observed for both XGAT and XETR; Tasks 2–12 may proceed.
```

or:

```text
STOP — the report names every absent or ambiguous truth-rule input; no
production parser may be implemented and the parent design must be revised.
```

- [ ] **Step 8: Hand-author minimal sanitized fixtures and add parity checks**

Each fixture uses the literal observed keys/nesting but fake identifiers such
as `DE000ZZTEST01`, prices `100.00/100.10`, and fixed UTC timestamps. Include
one normal event and each observed correction/cancellation representation.
Add a test that every JSON pointer named by the supplement resolves in the
matching fixture, so a prose/key mismatch fails before Task 5.

- [ ] **Step 9: Commit the reviewed capture artifacts**

```bash
git add personal_apps/scripts/capture_deutsche_boerse_contract.py \
  personal_apps/tests/test_capture_deutsche_boerse_contract.py \
  personal_apps/tests/fixtures/radar_market_data \
  docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md \
  docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md HANDOFF.md
git commit -m "docs(radar): freeze Deutsche Boerse feed contract"
```

**Hard checkpoint:** obtain an independent read-only review of the supplement,
fixtures, and PASS/STOP ruling. A STOP ends this plan. A PASS unlocks Task 2.

---

### Task 2: Add compatible provenance, shadow, cursor, and generation persistence

**Files:**
- Modify: `personal_apps/models.py:545-583, 844-930`
- Create: `personal_apps/migrations/versions/6a21d4e8c9f0_add_radar_market_data_v2.py`
- Modify: `personal_apps/tests/test_radar_models.py`
- Modify: `personal_apps/tests/test_radar_migration.py`

**Interfaces:**
- Produces nullable legacy-compatible quote fields: `source`, `price_basis`, `bid`, `ask`; plus non-null `is_shadow=False`.
- Produces nullable legacy-compatible daily-close fields: `source`, `price_basis`, `adjustment_basis`; plus non-null `is_shadow=False`.
- Produces `RadarMappingGeneration`, `RadarMarketDataCursor`, `RadarMarketDataCycle`, `RadarMarketTradeEvent`, `RadarGroupedCloseDay`, and `RadarProviderSessionState`.
- Produces nullable `RadarInstrument.mapping_generation_id` for current German rows.
- Replaces daily-close uniqueness with `(ticker, market, mic, close_date, is_shadow)` so a measured shadow close cannot overwrite or block the live/backfill row for the same day.

- [ ] **Step 1: Write failing model and CHECK-constraint tests**

```python
def test_market_data_v2_model_shapes():
    quote = RadarQuote(
        ticker='MDV2ZZ', market='de', mic='XGAT', currency='EUR',
        provider_symbol='ZZ1', fetched_at=NOW, quote_ts=NOW, price=100,
        source='deutsche_boerse_delayed', price_basis='trade',
        bid=decimal.Decimal('99.90'), ask=decimal.Decimal('100.10'),
        is_shadow=True)
    assert (quote.source, quote.price_basis, quote.is_shadow) == (
        'deutsche_boerse_delayed', 'trade', True)
    assert {'source', 'mic', 'channel'} <= {
        column.name for column in RadarMarketDataCursor.__table__.columns}
    checks = {constraint.name for constraint in RadarQuote.__table__.constraints}
    assert 'ck_radar_quote_price_basis' in checks
```

Also assert the trade-event unique key is `(mic, event_id)`, cursor primary key
is `(source, mic, channel)`, and cycle unique key is
`(source, mic, channel, scheduled_at)`. Assert grouped-day uniqueness is
`(source, close_date, is_shadow)` and provider-session-state uniqueness is
`(source, market)`.

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_models.py -q`

Expected: FAIL on missing columns/models.

- [ ] **Step 3: Add the SQLAlchemy fields and operational models**

Use these exact model meanings:

```python
class RadarMappingGeneration(db.Model):
    __tablename__ = 'radar_mapping_generations'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    market = db.Column(db.String(2), nullable=False)
    status = db.Column(db.String(12), nullable=False)  # shadow/active/retired/failed
    source = db.Column(db.String(32), nullable=False)
    payload_sha256 = db.Column(db.String(64), nullable=False, unique=True)
    payload_json = db.Column(MEDIUMTEXT, nullable=False)
    summary_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    activated_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)


class RadarMarketDataCursor(db.Model):
    __tablename__ = 'radar_market_data_cursors'
    source = db.Column(db.String(32), primary_key=True)
    mic = db.Column(db.String(4), primary_key=True)
    channel = db.Column(db.String(12), primary_key=True)
    remote_id = db.Column(db.String(160), nullable=False)
    source_ts = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    checksum = db.Column(db.String(64), nullable=False)
    fetched_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
```

`RadarMarketDataCycle` stores scheduled/completed time, mode
`shadow|active`, status `accepted|duplicate|no_newer|rejected|transport_error`, newest
remote ID/source time, file counts, record/selected counts, compressed and
uncompressed bytes, parse milliseconds, provider/fetch lag, and a bounded
`error_code`. `RadarMarketTradeEvent` stores MIC, ISIN, event ID, original
event ID, action `new|correct|cancel`, event time, nullable positive price,
nullable volume, official-close boolean, source remote ID, and received time.

`RadarGroupedCloseDay` has an autoincrement key plus a unique
`(source, close_date, is_shadow)` tuple. It stores status
`accepted|no_data|rejected|transport_error`, nullable payload SHA-256, fetched/completed
times, provider/mapped/written/unmatched-provider/unmatched-universe/
active-expected/active-matched/malformed/duplicate-conflict counts, bounded `error_code`, nullable HTTP
status, and nullable `backoff_until`. This is the only resumable progress
ledger for Massive grouped days; do not fabricate a MIC/channel cursor.

`RadarProviderSessionState` has primary key `(source, market)` and stores
nullable `last_post_close_session_date` plus `claimed_at`. Task 9 updates it
under a row lock and commits before calling the quote provider.

- [ ] **Step 4: Write the expand-only migration from `f4b2d81c37a9`**

The migration must:

1. create the six operational tables and indexes;
2. add nullable `mapping_generation_id` with a named foreign key to
   `radar_instruments`;
3. add nullable provenance/book columns to quotes and nullable source,
   price-basis, and adjustment-basis provenance to closes;
4. add `is_shadow BOOLEAN NOT NULL DEFAULT 0` to quotes/closes;
5. replace `uq_radar_daily_close_market` with a named unique constraint that
   includes `is_shadow`;
6. add CHECKs for quote basis, daily-close price and adjustment bases,
   generation status, cycle mode/status, grouped-day status, channel, and
   trade action;
7. leave every old writer valid.

Downgrade drops only the new tables/columns/constraints and preserves all
legacy quote/close rows. Before dropping `is_shadow`, it deletes only shadow
daily-close rows (never live rows), removes the five-column unique constraint,
and restores the original four-column `uq_radar_daily_close_market`; otherwise
two shadow/live rows for one date would collide during downgrade.

- [ ] **Step 5: Write migration overlap and downgrade tests**

Create the pre-migration schema, insert an old quote and daily close, upgrade,
then insert another row using the old column list. Assert both have
`is_shadow=0` and nullable provenance. Downgrade and assert both legacy rows
remain. Before downgrading, insert live and shadow daily closes for the same
`(ticker, market, mic, close_date)` and assert both coexist; prove the original
four-column unique constraint rejects that pair in the isolated broken variant.
Add a second broken-variant assertion by temporarily omitting the server
default in the isolated schema and proving the old insert fails.
Also insert and round-trip grouped-day/session-state rows, prove their unique
keys reject duplicates, and prove invalid grouped status and non-`split`
modern adjustment basis fail their named CHECKs. Migration-era NULL remains
accepted by the expand migration.

- [ ] **Step 6: Run model/migration tests and inspect the head**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_models.py tests/test_radar_migration.py -q
python -m flask --app app db heads
```

Expected: PASS; head is `6a21d4e8c9f0`.

- [ ] **Step 7: Commit the additive schema**

```bash
git add personal_apps/models.py \
  personal_apps/migrations/versions/6a21d4e8c9f0_add_radar_market_data_v2.py \
  personal_apps/tests/test_radar_models.py personal_apps/tests/test_radar_migration.py
git commit -m "feat(radar): add market data provenance storage"
```

---

### Task 3: Extend normalized quotes and select calendars by MIC

**Files:**
- Modify: `personal_apps/features/radar/prices/__init__.py`
- Modify: `personal_apps/features/radar/prices/finnhub.py`
- Modify: `personal_apps/features/radar/prices/twelvedata.py`
- Modify: `personal_apps/features/radar/markets.py`
- Modify: `personal_apps/features/radar/quotes.py`
- Modify: `personal_apps/features/radar/market_calendars/__init__.py`
- Modify: `personal_apps/features/radar/market_calendars/de.py`
- Create: `personal_apps/features/radar/market_calendars/tradegate.py`
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/detail.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/tests/test_radar_prices.py`
- Modify: `personal_apps/tests/test_radar_markets.py`
- Modify: `personal_apps/tests/test_radar_quotes.py`
- Modify: `personal_apps/tests/test_radar_quotes_batch.py`
- Modify: `personal_apps/tests/test_radar_calendar_de.py`
- Modify: `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Produces `Quote.source`, `.price_basis`, `.bid`, `.ask` with legacy defaults `legacy`, `trade`, `None`, `None`.
- Produces `QuoteView.source`, `.price_basis`, `.bid`, `.ask`.
- Produces `session_state(market, when_utc, mic=None)` and `session_bounds(market, when_utc, mic=None)`; `de/None` remains Xetra-compatible.
- Produces `select_quote(ticker, requested_market, snapshots, now, tape_status='ok', allow_us_fallback=True)`; callers pass `False` when a verified German primary exists but its feed is unavailable.
- Makes every current quote read exclude `RadarQuote.is_shadow IS TRUE`.

- [ ] **Step 1: Write failing provenance, book, and eligibility tests**

```python
def test_midpoint_is_visible_but_never_score_eligible():
    quote = snapshot(
        market='de', mic='XGAT', venue='Tradegate BSX', currency='EUR',
        source='deutsche_boerse_delayed', price_basis='midpoint',
        bid='99.90', ask='100.10')
    view = QuoteView.from_snapshot(quote, NOW)
    assert view.price == decimal.Decimal('100.00')
    assert view.price_basis == 'midpoint'
    assert view.score_eligible is False


def test_verified_german_mapping_does_not_fallback_during_feed_failure():
    selected = select_quote('AAPL', 'de', {'us': snapshot()}, NOW,
                            allow_us_fallback=False)
    assert selected.quality == 'unavailable'
    assert selected.is_fallback is False
```

Add validation cases for non-positive price, crossed book, one-sided midpoint,
unknown source/basis, and quote timestamp absent. Add a test inserting a newer
`is_shadow=True` XGAT row and an older live XGAT row; `quote_views_for` must
return the older live row. Add a window containing trade→midpoint→trade and
assert `move_since`/`moves_for` use only the two trade snapshots.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_prices.py tests/test_radar_markets.py tests/test_radar_quotes.py tests/test_radar_quotes_batch.py -q`

Expected: FAIL on missing normalized fields and shadow filtering.

- [ ] **Step 3: Extend `Quote` and central validation**

Add exact allowed sets and constructor fields:

```python
PRICE_BASES = frozenset({'trade', 'midpoint', 'close'})
QUOTE_SOURCES = frozenset({
    'legacy', 'finnhub', 'twelvedata',
    'deutsche_boerse_delayed', 'yahoo_chart',
})
CLOSE_SOURCES = QUOTE_SOURCES | frozenset({'massive_grouped'})  # [A1]
```

`[A1]` Quote validation rejects `source='massive_grouped'` even when
`price_basis='close'`; Massive is a daily-close source, never a `Quote` source.
Daily-close validation accepts it only with `price_basis='close'` and
`adjustment_basis='split'`. Keep quote-source and close-source validation as
separate functions/sets so a future call site cannot accidentally broaden
the intraday contract.

`Quote.__init__` rejects price `<= 0`; midpoint requires positive `bid <= ask`
and sets price to the exact decimal midpoint; trade/close may carry a valid
book but never derive their price from it. `normalize_snapshot` preserves the
instrument-owned ticker/market/venue/MIC/symbol/currency and copies only the
validated source/basis/book/event values.

Change freshness classification so `quote_ts is None` is `unavailable` and
never falls back to `fetched_at`. Fetch time remains diagnostic metadata only.
Session calculation may use the current market clock for an unavailable row,
but no price, move, or eligibility may result from that missing provider time.

- [ ] **Step 4: Extend persistence and presentation selection**

`record_quotes(quotes, now, *, is_shadow=False, commit=True)` writes source,
basis, bid, ask, and shadow state. With `commit=False` it only stages rows so
Task 7 can commit quote, cursor, trade events, and cycle together.

Every `RadarQuote` read used by board/detail/move/status adds
`RadarQuote.is_shadow.is_(False)`. `_stored_quote` restores the four new fields
and uses `legacy/trade` for migration-era NULL values. Remove the
`quote.mic == 'XETR'` hard-code from `_primary_quote`; the current primary
instrument supplies the MIC.

In `quote_views_for`, `allow_us_fallback` is true only when no mapped German
primary row exists. A mapped row with no live snapshot returns unavailable or
its retained stale quote, never US.

`move_since` and `moves_for` include only `price_basis='trade'` rows plus
migration-era NULL basis as legacy trades. A midpoint may appear on the chart,
but cannot become either endpoint of the divergence move. Update Finnhub to
declare `source='finnhub'`, emit quote basis `trade`, and override the legacy
constructor default with `provider_delay='live'`; while in that file,
correct the module comment claiming ~20-minute delayed free quotes — Finnhub's
current documentation states real-time US quotes on the free tier `[A2]`.
Update Twelve Data to
declare `source='twelvedata'` and emit quote basis `trade`. Task 8's generic
history writer reads `provider.source` and persists daily price basis `close`
plus adjustment basis `split`, so the
tuple-returning `daily_closes` interface does not grow a second result shape.
Pin both negative contracts in tests: constructing a Massive `Quote` raises,
and a normalized Finnhub quote carries exactly `('finnhub', 'trade', 'live')`.

- [ ] **Step 5: Add the Tradegate calendar and MIC routing tests**

```python
def test_tradegate_opens_at_0730_berlin():
    before = dt.datetime(2026, 8, 31, 5, 29, tzinfo=dt.timezone.utc)
    opened = dt.datetime(2026, 8, 31, 5, 30, tzinfo=dt.timezone.utc)
    assert session_state('de', before, mic='XGAT') == 'closed'
    assert session_state('de', opened, mic='XGAT') == 'premarket'


def test_xetra_default_keeps_0800_berlin_behavior():
    at_0730 = dt.datetime(2026, 8, 31, 5, 30, tzinfo=dt.timezone.utc)
    assert session_state('de', at_0730, mic='XETR') == 'closed'
    assert session_state('de', at_0730) == 'closed'
```

Cover winter/summer UTC offsets, weekend/holiday closure, 09:00 and 17:30
boundaries, and 22:00 close. The existing Xetra tests must remain unchanged.

- [ ] **Step 6: Implement MIC-aware calendar dispatch**

```python
def _calendar(market: str, mic: str | None = None):
    if market == 'us':
        return us
    if market == 'de' and mic == 'XGAT':
        return tradegate
    if market == 'de' and mic in (None, 'XETR'):
        return de
    raise ValueError(f'unknown market/MIC: {market}/{mic}')
```

Pass quote MIC through `QuoteView.from_snapshot`, chart session helpers, and
detail intraday anchoring. The board-wide Germany header uses `XGAT`; a row or
fallback chart uses its actual selected quote MIC.

- [ ] **Step 7: Pin 17:30 baseline behavior**

Add a test where an XGAT late quote has no official/last-trade
`regular_close`; its `extended_move` must be `None`, not a midpoint-derived or
Xetra-derived number. Existing premarket/afterhours tests continue to prove
the correct prior-close/current-day-close baseline when present.

- [ ] **Step 8: Run focused backend tests**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_prices.py tests/test_radar_markets.py \
  tests/test_radar_quotes.py tests/test_radar_quotes_batch.py \
  tests/test_radar_calendar_de.py tests/test_radar_api.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit the normalized contract and calendars**

```bash
git add personal_apps/features/radar/prices/__init__.py \
  personal_apps/features/radar/prices/finnhub.py \
  personal_apps/features/radar/prices/twelvedata.py \
  personal_apps/features/radar/markets.py personal_apps/features/radar/quotes.py \
  personal_apps/features/radar/market_calendars \
  personal_apps/features/radar/board.py personal_apps/features/radar/detail.py \
  personal_apps/features/radar/routes/api.py personal_apps/tests/test_radar_prices.py \
  personal_apps/tests/test_radar_markets.py personal_apps/tests/test_radar_quotes.py \
  personal_apps/tests/test_radar_quotes_batch.py \
  personal_apps/tests/test_radar_calendar_de.py personal_apps/tests/test_radar_api.py
git commit -m "feat(radar): carry truthful quote provenance"
```

---

### Task 4: Implement the Yahoo chart provider without activating it

**Files:**
- Create: `personal_apps/features/radar/prices/yahoo.py`
- Create: `personal_apps/tests/test_radar_yahoo.py`
- Modify: `personal_apps/tests/test_radar_prices.py`

**Interfaces:**
- Produces `YahooHttp.get_chart(symbol, *, interval, period1, period2, include_prepost) -> dict`.
- Produces `YahooProvider.quotes_for_instruments(instruments) -> dict[str, Quote]`.
- Produces `YahooProvider.daily_closes(symbol, days, mic_code=None) -> list[tuple[date, Decimal]]`.
- Never raises a provider/network/shape error out of a per-instrument call; an invalid instrument is absent.

- [ ] **Step 1: Write failing response-shape and identity tests**

Use fixed fake payloads, not recorded Yahoo bodies:

```python
def chart_payload(symbol='AAPL', currency='USD', exchange='NMS'):
    return {'chart': {'result': [{
        'meta': {'symbol': symbol, 'currency': currency,
                 'exchangeName': exchange, 'chartPreviousClose': 99.0},
        'timestamp': [1788170400, 1788171300],
        'indicators': {'quote': [{'close': [100.0, 101.0],
                                  'volume': [10, 20]}],
                       'adjclose': [{'adjclose': [100.0, 101.0]}]},
    }], 'error': None}}


def test_quote_uses_last_non_null_chart_print():
    provider = YahooProvider(FakeHttp(chart_payload()))
    found = provider.quotes_for_instruments([instrument('AAPL', 'XNAS', 'USD')])
    quote = found['AAPL']
    assert quote.price == decimal.Decimal('101.0')
    assert quote.quote_ts == dt.datetime.fromtimestamp(1788171300, dt.timezone.utc).replace(tzinfo=None)
    assert (quote.source, quote.price_basis, quote.provider_delay) == (
        'yahoo_chart', 'trade', 'delayed')
```

Add cases for HTTP 401/403/429, timeout, `chart.error`, no result, wrong symbol,
wrong currency, incompatible exchange, missing timestamp, null final bar with
an earlier valid bar, zero/negative close, and malformed parallel arrays.

- [ ] **Step 2: Run the Yahoo tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_yahoo.py -q`

Expected: FAIL because `prices.yahoo` does not exist.

- [ ] **Step 3: Implement bounded HTTP, cache, and backoff**

Use `/v8/finance/chart/{url-quoted-symbol}` only. `YahooHttp` owns one
`requests.Session`, timeout `(3.05, 15)`, `max_workers=4`, cache TTL 60 seconds,
and process-local exponential backoff `60, 120, 240, 480, 960, 1800` seconds after
401/403/429. A successful request resets the backoff. During backoff it returns
no payload without touching the network.

Current quote requests use a one-day range, five-minute interval, and
`includePrePost=true`. Daily history uses explicit `period1/period2`,
`interval=1d`, and `includePrePost=false`. Do not add yfinance or another
dependency.

- [ ] **Step 4: Implement exact metadata and parallel-array validation**

Create explicit MIC allowlists for Yahoo exchange metadata. `XNAS`, `XNGS`,
`XNMS`, and `XNCM` accept Nasdaq metadata; `XNYS` accepts NYSE metadata;
`ARCX` accepts NYSE Arca; `XASE` accepts NYSE American; `BATS` accepts Cboe;
`IEXG` accepts IEX; `XETR` accepts German/Xetra metadata. These cover every
MIC already seeded by the current universe migration. Unknown MIC or missing/
mismatched returned exchange metadata rejects the response rather than
weakening identity validation.

For current quotes, select the latest index where timestamp and close are both
valid. `previous_close` comes from positive `chartPreviousClose`, falling back
only to positive `previousClose`. `regular_close`
uses positive `regularMarketPrice` only when `regularMarketTime` identifies the
same market day; otherwise it remains absent. Volume comes from the selected
parallel index. For daily history, pair date with the `quote.close` value at
the same index, deduplicate by date, sort oldest-first, and bound to the
requested calendar window. Do **not** read Yahoo `adjclose`: Yahoo's adjusted
close includes dividends as well as splits, while Massive `adjusted=true` and
the incumbent Twelve Data default are split-only. Every Yahoo history write
therefore records `adjustment_basis='split'` `[A1]`.

Add a binding fixture in which `quote.close` and `adjclose` differ because of
a dividend and another in which the provider series reflects a split. Assert
the adapter selects `quote.close`, persists the split basis through Task 8,
and a broken implementation selecting `adjclose` fails. This prevents a
manufactured dividend seam between the Yahoo deep tail and Massive history.

- [ ] **Step 5: Prove per-instrument containment and concurrency bounds**

Add a three-instrument test: one succeeds, one times out, one has the wrong
currency. Assert only the valid symbol is returned and active fake requests
never exceed four. Add a broken variant with the semaphore removed and assert
the concurrency test fails.

- [ ] **Step 6: Run focused provider tests**

Run: `cd personal_apps && python -m pytest tests/test_radar_yahoo.py tests/test_radar_prices.py -q`

Expected: PASS without network access.

- [ ] **Step 7: Commit the dormant Yahoo adapter**

```bash
git add personal_apps/features/radar/prices/yahoo.py \
  personal_apps/tests/test_radar_yahoo.py personal_apps/tests/test_radar_prices.py
git commit -m "feat(radar): add Yahoo chart price adapter"
```

---

### Task 4b: Implement the Massive grouped-daily close provider without activating it `[A1]`

**Files:**
- Create: `personal_apps/features/radar/prices/massive.py`
- Create: `personal_apps/tests/test_radar_massive.py`
- Modify: `personal_apps/tests/test_radar_prices.py`

**Interfaces:**
- Produces `MassiveHttp.get_grouped_daily(day) -> dict` using `GET {base}/v2/aggs/grouped/locale/us/market/stocks/{YYYY-MM-DD}?adjusted=true&apiKey=...`.
- Produces `MassiveProvider.grouped_closes(day) -> GroupedFetch`; an accepted
  `GroupedFetch` owns a `ProviderGroupedDay` whose `closes` are
  `dict[str, Decimal]` keyed by exact uppercase provider symbol, plus payload
  checksum and provider/malformed/duplicate-conflict counts. It does not
  import models or map symbols to Radar identities.
- Produces class attribute `source = 'massive_grouped'` consumed by Task 8's generic close writer.
- Never raises a provider/network/shape error out of `grouped_closes`.
  `GroupedFetch.status` is `accepted|no_data|rejected|transport_error` and
  carries bounded `error_code`, HTTP status, and optional `backoff_until` so
  Task 8 can persist every attempt without confusing failure with progress.

- [ ] **Step 1: Write failing grouped-payload tests**

Use fixed fake payloads with the endpoint's documented envelope, not recorded
bodies:

```python
def grouped_payload(rows=None):
    return {'status': 'OK', 'queryCount': 3, 'resultsCount': 3,
            'adjusted': True,
            'results': rows if rows is not None else [
                {'T': 'ZZAA', 'c': 100.5, 'o': 99.0, 'h': 101.0,
                 'l': 98.5, 'v': 1000, 't': event_ms(DAY)},
                {'T': 'ZZBB', 'c': 55.25, 'o': 54.0, 'h': 56.0,
                 'l': 53.5, 'v': 2000, 't': event_ms(DAY)},
                {'T': 'ZZUNKNOWN', 'c': 1.0, 'o': 1.0, 'h': 1.0,
                 'l': 1.0, 'v': 5, 't': event_ms(DAY)},
            ]}


def test_grouped_closes_returns_exact_provider_symbols():
    provider = MassiveProvider(FakeHttp(grouped_payload()))
    fetch = provider.grouped_closes(DAY)
    assert fetch.status == 'accepted'
    assert fetch.day.closes == {
        'ZZAA': decimal.Decimal('100.5'),
        'ZZBB': decimal.Decimal('55.25'),
        'ZZUNKNOWN': decimal.Decimal('1.0'),
    }


def test_one_malformed_row_does_not_discard_the_day():
    rows = grouped_payload()['results']
    rows[0]['c'] = 0  # zero close is rejected per spec truth rule 7
    provider = MassiveProvider(FakeHttp(grouped_payload(rows)))
    fetch = provider.grouped_closes(DAY)
    assert 'ZZAA' not in fetch.day.closes
    assert fetch.day.closes['ZZBB'] == decimal.Decimal('55.25')
    assert fetch.day.malformed_rows == 1


def test_transport_or_envelope_failure_is_typed():
    assert MassiveProvider(RaisingHttp(requests.Timeout)).grouped_closes(
        DAY).status == 'transport_error'
    assert MassiveProvider(FakeHttp({'status': 'ERROR'})).grouped_closes(
        DAY).status == 'rejected'
    assert MassiveProvider(FakeHttp({'status': 'OK'})).grouped_closes(
        DAY).status == 'rejected'
    assert MassiveProvider(FakeHttp(None, status_code=429)).grouped_closes(
        DAY).status == 'transport_error'
```

Add cases for: missing `results` key, non-list `results`, a row missing `T`
or `c` or `t`, negative close, a row whose `t` does not resolve to the exact
requested US exchange-local date (reject that row), HTTP 401/403 (fail the
day, log once), and duplicates. Identical duplicate `(T, c, event date)` rows
deduplicate and count once; conflicting duplicates omit that symbol and
increment `duplicate_conflicts` — last-row-wins is forbidden. An empty
`results` list on an expected trading day returns `no_data`, never
`accepted`. `event_ms(DAY)` derives the fixture timestamp from `DAY`; no
hard-coded timestamp may silently describe a different date.

- [ ] **Step 2: Run the Massive tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_massive.py -q`

Expected: FAIL because `prices.massive` does not exist.

- [ ] **Step 3: Implement bounded HTTP and pacing**

`MassiveHttp` owns one `requests.Session`, timeout `(3.05, 30)`, reads
`RADAR_MASSIVE_API_KEY` and `RADAR_MASSIVE_BASE_URL` (default
`https://api.massive.com`; `https://api.polygon.io` is the documented
legacy-compatibility value — the rebrand announcement keeps old endpoints
alive only "for an extended period" with a phase-out planned during 2026)
at call time, and enforces the free tier's five-calls-per-
minute limit with a process-local monotonic pacer (sleep-free in tests via an
injectable clock). A 429 sets exponential backoff `60, 120, 240` seconds;
success resets it. A missing key makes every call return no payload and log
once — the adapter is dormant until the operator provisions the key.

`adjusted=true` (split-adjusted) matches the series the store actually
holds: the incumbent Twelve Data fetch sends no adjustment parameter, and
Twelve Data's documented default is split adjustment. Pinning the opposite
basis would rewrite every post-split history the moment the higher-priority
grouped backfill runs. Add a split-ticker fixture: a grouped row whose
adjusted close is far from a seeded unadjusted value proves the parameter is
actually sent. The normalized day exposes `adjustment_basis='split'`.

- [ ] **Step 4: Implement per-row validation without database identity**

Validate the envelope (`status == 'OK'`, list `results`), then per row:
uppercase `T`, positive finite `c` parsed via `str()` into `Decimal`, `t`
resolving to the exact requested date in the US exchange timezone. Reject
rows individually and return only exact provider-symbol keys. Compute the
payload SHA-256 from a deterministic canonical representation. Identity join,
active coverage, unmatched-universe counts, storage, and progress belong to
Task 8, where `RadarInstrument` is available. No normalization map exists
yet: punctuation variants are added only from observed mismatch logs during
shadow days, never guessed here.

- [ ] **Step 5: Run focused provider tests**

Run: `cd personal_apps && python -m pytest tests/test_radar_massive.py tests/test_radar_prices.py -q`

Expected: PASS without network access.

- [ ] **Step 6: Commit the dormant Massive adapter**

```bash
git add personal_apps/features/radar/prices/massive.py \
  personal_apps/tests/test_radar_massive.py personal_apps/tests/test_radar_prices.py
git commit -m "feat(radar): add Massive grouped-daily close adapter"
```

---

### Task 5: Implement the captured Deutsche Börse delayed-file adapter

**Prerequisite:** Task 1's contract supplement ends in PASS. The implementer
reads it completely before writing a parser. Literal upstream JSON pointers in
this task mean the exact reviewed strings from that supplement; no heuristic
key search or alternate spelling is permitted.

**Files:**
- Create: `personal_apps/features/radar/prices/deutsche_boerse.py`
- Create: `personal_apps/tests/test_radar_deutsche_boerse.py`
- Use: `personal_apps/tests/fixtures/radar_market_data/*.json`
- Use: `docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md`

**Interfaces:**
- Produces immutable `VenueReference`, `TradeEvent`, `BookEvent`, `FeedFile`, and `FeedBatch` dataclasses.
- Produces `DeutscheBoerseHttp.list_files(mic, channel) -> list[FeedFile]` and `.download(file) -> bytes`.
- Produces `DeutscheBoerseProvider.files_after(mic, channel, cursor) -> list[FeedFile]` and `.parse(file, compressed) -> FeedBatch`.
- A complete reference snapshot is explicitly `FeedBatch.reference_complete=True`; absence of this proof can never mark a mapping unavailable.

- [ ] **Step 1: Write failing fixture parser tests**

```python
def test_posttrade_fixture_preserves_identity_and_correction():
    batch = parse_fixture('xgat_posttrade.json', mic='XGAT', channel='posttrade')
    assert batch.mic == 'XGAT'
    assert batch.channel == 'posttrade'
    assert batch.source_ts == dt.datetime(2026, 8, 31, 12, 43)
    assert batch.trades == (
        TradeEvent(mic='XGAT', isin='DE000ZZTEST01', event_id='trade-1',
                   original_event_id=None, action='new',
                   event_ts=dt.datetime(2026, 8, 31, 12, 42),
                   price=decimal.Decimal('100.00'), volume=20,
                   is_official_close=False),
        TradeEvent(mic='XGAT', isin='DE000ZZTEST01', event_id='cancel-1',
                   original_event_id='trade-1', action='cancel',
                   event_ts=dt.datetime(2026, 8, 31, 12, 43),
                   price=None, volume=None, is_official_close=False),
    )
```

Add pre-trade book/reference assertions and Xetra equivalents. Add malformed
record, wrong MIC, invalid ISIN, naive/non-UTC time, non-positive price,
negative volume, crossed book, duplicate event ID with conflicting content,
and an unknown action test.

- [ ] **Step 2: Run parser tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_deutsche_boerse.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Define the provider dataclasses and literal path tables**

```python
@dataclasses.dataclass(frozen=True)
class VenueReference:
    mic: str
    isin: str
    symbol: str
    name: str | None
    currency: str
    security_type: str


@dataclasses.dataclass(frozen=True)
class TradeEvent:
    mic: str
    isin: str
    event_id: str
    original_event_id: str | None
    action: str
    event_ts: dt.datetime
    price: decimal.Decimal | None
    volume: int | None
    is_official_close: bool


@dataclasses.dataclass(frozen=True)
class BookEvent:
    mic: str
    isin: str
    event_ts: dt.datetime
    bid: decimal.Decimal
    ask: decimal.Decimal


@dataclasses.dataclass(frozen=True)
class FeedBatch:
    mic: str
    channel: str
    remote_id: str
    source_ts: dt.datetime
    references: tuple[VenueReference, ...]
    trades: tuple[TradeEvent, ...]
    books: tuple[BookEvent, ...]
    reference_complete: bool
    record_count: int


@dataclasses.dataclass(frozen=True)
class FeedFile:
    mic: str
    channel: str
    remote_id: str
    source_ts: dt.datetime
    url: str


@dataclasses.dataclass(frozen=True)
class ReferenceCatalog:
    mic: str
    rows: tuple[VenueReference, ...]
    complete: bool
    content_sha256: str
```

Encode one constant path map per captured `(MIC, channel)` using the literal
JSON pointers from the approved supplement. `_at_pointer(payload, pointer)` is
the only field reader. A missing required pointer rejects the file; an invalid
individual record is counted/rejected while other structurally valid records
remain.

- [ ] **Step 4: Implement archive and index transport limits**

`DeutscheBoerseHttp` uses the exact reviewed index URLs from the supplement,
one `requests.Session`, timeout `(3.05, 20)`, and the operator-supplied
`RADAR_DBAG_DELAYED_COOKIE`. It never logs the cookie. A missing cookie returns
`PriceUnavailable('delayed-data terms access not configured')` before a
network call.

Use `html.parser.HTMLParser` to collect file links. Accept only same-origin
HTTPS links whose filename matches the exact captured `DGAT/DETR` channel/time
grammar. Sort by filename source time, never by HTML order. Downloads enforce
50 MiB compressed, 250 MiB uncompressed, and decompression ratio 100 before
JSON decode. Reject redirects to another origin.

- [ ] **Step 5: Write transport adversarial tests**

Cover unordered/duplicate links, a lookalike hostname, path traversal, wrong
venue/channel filename, redirect, timeout, non-gzip response, gzip bomb,
oversized JSON, invalid UTF-8, invalid JSON, and a source timestamp that
disagrees with the filename. Assert every failure is `PriceUnavailable` or
`FeedRejected` with a bounded reason code and no payload excerpt.

- [ ] **Step 6: Implement correction semantics as pure functions**

```python
def apply_trade_events(
        current: dict[str, TradeEvent],
        incoming: collections.abc.Iterable[TradeEvent],
) -> dict[str, TradeEvent]:
    updated = dict(current)
    for event in sorted(incoming, key=lambda item: (item.event_ts, item.event_id)):
        if event.action == 'new':
            updated[event.event_id] = event
        elif event.action == 'correct':
            updated.pop(event.original_event_id, None)
            updated[event.event_id] = event
        elif event.action == 'cancel':
            updated.pop(event.original_event_id, None)
    return updated
```

Reject a correction/cancellation whose original ID is absent from both the
retained journal and the same batch; it cannot silently revoke a guessed
trade. A duplicate event ID with byte-equivalent normalized content is
idempotent; conflicting content rejects the file.

- [ ] **Step 7: Run all adapter tests**

Run: `cd personal_apps && python -m pytest tests/test_radar_deutsche_boerse.py tests/test_capture_deutsche_boerse_contract.py -q`

Expected: PASS without network access.

- [ ] **Step 8: Commit the dormant delayed-file adapter**

```bash
git add personal_apps/features/radar/prices/deutsche_boerse.py \
  personal_apps/tests/test_radar_deutsche_boerse.py
git commit -m "feat(radar): parse Deutsche Boerse delayed files"
```

---

### Task 6: Build versioned XGAT-first German mappings

**Files:**
- Create: `personal_apps/features/radar/prices/openfigi.py`
- Create: `personal_apps/features/radar/data/german_instrument_overrides.json`
- Modify: `personal_apps/features/radar/instruments.py`
- Create: `personal_apps/tests/test_radar_openfigi.py`
- Modify: `personal_apps/tests/test_radar_instruments.py`
- Modify: `personal_apps/tests/test_radar_market_data.py`

**Interfaces:**
- Produces `OpenFigiProvider.us_share_classes(instruments) -> dict[str, ShareClass]`.
- Produces `OpenFigiProvider.venue_candidates(share_classes, mic) -> dict[str, tuple[VenueCandidate, ...]]`.
- Produces `build_generation(openfigi, references_by_mic: dict[str, ReferenceCatalog], overrides, now) -> RadarMappingGeneration` with status `shadow` and no current-instrument mutation.
- Produces `activate_generation(generation_id, now) -> int` and `rollback_generation(generation_id, now) -> int`, each one transaction.

The normalized mapping types are fixed:

```python
@dataclasses.dataclass(frozen=True)
class ShareClass:
    ticker: str
    share_class_figi: str
    security_type: str


@dataclasses.dataclass(frozen=True)
class VenueCandidate:
    share_class_figi: str
    mic: str
    symbol: str
    name: str | None
    security_type: str


@dataclasses.dataclass(frozen=True)
class MappingDecision:
    ticker: str
    status: str
    reason: str | None
    mic: str | None
    symbol: str | None
    isin: str | None
    currency: str | None
    mapping_source: str
```

- [ ] **Step 1: Write failing OpenFIGI batching and refusal tests**

```python
def test_share_class_maps_to_xgat_before_xetr():
    provider = OpenFigiProvider(FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XGAT'): [de_result('APC', 'XGAT')],
        ('SHARE', 'BBG001S5N8V8', 'XETR'): [de_result('APC', 'XETR')],
    }))
    decision = decide_mapping(
        instrument('AAPL'), provider,
        {'XGAT': reference_catalog(
             'XGAT', [reference('APC', 'XGAT', 'US0378331005')]),
         'XETR': reference_catalog(
             'XETR', [reference('APC', 'XETR', 'US0378331005')])}, {})
    assert (decision.status, decision.mic, decision.symbol) == (
        'mapped', 'XGAT', 'APC')
```

Cover ten-job unauthenticated batching, 429 containment, multiple US classes,
unsupported type, multiple venue candidates, wrong currency, exact mnemonic
missing from official reference, and incomplete reference catalogs. The SAP
ADR case must refuse automatic mapping.

- [ ] **Step 2: Run focused mapping tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_openfigi.py tests/test_radar_instruments.py tests/test_radar_market_data.py -q`

Expected: FAIL on missing OpenFIGI/generation interfaces.

- [ ] **Step 3: Implement the public OpenFIGI adapter**

Use `/v3/mapping` with at most ten jobs/request without a key and at most 25
requests/minute. An optional `OPENFIGI_API_KEY` raises batch size to 100 but is
not required. US jobs use exact ticker plus known exchange; venue jobs use
`idType=ID_BB_GLOBAL_SHARE_CLASS_LEVEL`, exact share-class FIGI, `micCode`,
and `currency=EUR`.

Return only normalized common-stock/ETF candidates. A response warning is an
empty candidate set; transport/429/malformed response is `PriceUnavailable`
and aborts the whole generation rather than turning every ticker unavailable.

- [ ] **Step 4: Define and validate reviewed overrides**

The committed JSON root is `{"version": 1, "overrides": []}` initially.
Each future entry must include exactly `social_ticker`,
`us_instrument_identifier`, `german_mic`, `local_mnemonic`, `german_isin`,
`currency`, `evidence_url`, `reference_date`, `reviewer`, and `reviewed_at`.
Load with strict key equality, valid ISIN/MIC/currency/time checks, unique
social ticker, and a reviewed timestamp no older than 366 days. An override is
accepted only when the exact MIC/mnemonic/ISIN exists in the complete official
reference map.

- [ ] **Step 5: Replace catalog joins with deterministic decisions**

Define refusal reasons exactly:

```python
REFUSAL_REASONS = frozenset({
    'no_us_share_class', 'ambiguous_us_share_class',
    'no_german_candidate', 'ambiguous_german_candidate',
    'official_reference_missing', 'currency_mismatch',
    'security_type_mismatch', 'override_invalid',
})
```

`decide_mapping` tries `XGAT`, then `XETR`, then an exact override. It never
compares company names. `unavailable` is allowed only when both official
reference inputs say `complete=True`; otherwise the generation build raises
and writes nothing.

- [ ] **Step 6: Persist a canonical shadow generation**

Serialize sorted decisions using compact JSON with sorted keys. The payload
contains every active US ticker, its mapped identity or refusal reason, and
the complete-reference hashes. Hash the exact UTF-8 bytes with SHA-256. If an
identical hash already exists, return that generation instead of duplicating
it. New evidence writes `status='shadow'`; it does not alter
`RadarInstrument.is_primary`.

- [ ] **Step 7: Implement atomic activation and rollback**

Before first activation, snapshot current German `RadarInstrument` rows into
a generation with source `legacy` so rollback has a real target.

Activation verifies the payload hash, all override/reference identities, and
one primary per mapped ticker; then in one transaction it:

1. marks the previous active generation `retired`;
2. upserts exact current `RadarInstrument` rows for the selected XGAT/XETR
   decisions and stamps `mapping_generation_id`;
3. makes selected rows primary and all other German rows non-primary;
4. records unavailable/refusal outcomes without inventing venue rows;
5. marks the selected generation active with `activated_at`.

Rollback takes a previously active generation ID and applies the same payload
algorithm in reverse status order. Add a forced exception after half the row
updates and assert the transaction leaves the previous primaries/generation
unchanged.

- [ ] **Step 8: Run mapping and transaction tests**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_openfigi.py tests/test_radar_instruments.py \
  tests/test_radar_market_data.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit the shadow mapping pipeline**

```bash
git add personal_apps/features/radar/prices/openfigi.py \
  personal_apps/features/radar/data/german_instrument_overrides.json \
  personal_apps/features/radar/instruments.py \
  personal_apps/tests/test_radar_openfigi.py \
  personal_apps/tests/test_radar_instruments.py \
  personal_apps/tests/test_radar_market_data.py
git commit -m "feat(radar): build versioned German mappings"
```

---

### Task 7: Collect Deutsche Börse files transactionally in shadow mode

**Files:**
- Create: `personal_apps/features/radar/market_data.py`
- Modify: `personal_apps/features/radar/quotes.py`
- Modify: `personal_apps/features/radar/retention.py`
- Modify: `personal_apps/tests/test_radar_market_data.py`
- Modify: `personal_apps/tests/test_radar_quote_retention.py`

**Interfaces:**
- Produces `collect_german_cycle(provider, generation_id, active_tickers, now, *, mode='shadow') -> CycleSummary`.
- Produces `select_german_quotes(instruments, trades, books, now) -> dict[(ticker, market, mic), Quote]`.
- Produces durable cursor/trade/cycle writes committed with quote snapshots per accepted channel/file.
- Retains trade events and cycle rows for 48 hours and 14 days respectively; never prunes cursors or mapping generations.

`CycleSummary` is immutable and exact:

```python
@dataclasses.dataclass(frozen=True)
class CycleSummary:
    mode: str
    status: str
    files_seen: int
    files_accepted: int
    selected_quotes: int
    rejected_records: int
    error_code: str | None

    @classmethod
    def accepted(cls, selected_quotes: int) -> 'CycleSummary':
        return cls('shadow', 'accepted', 1, 1, selected_quotes, 0, None)
```

- [ ] **Step 1: Write failing trade/midpoint selection tests**

```python
def test_latest_valid_trade_beats_midpoint():
    picked = select_price(
        now=NOW,
        trades=[trade('old', NOW - dt.timedelta(minutes=31), '99.00'),
                trade('new', NOW - dt.timedelta(minutes=20), '100.00')],
        book=book(NOW - dt.timedelta(minutes=18), '99.90', '100.10'))
    assert (picked.price, picked.price_basis) == (
        decimal.Decimal('100.00'), 'trade')


def test_fresh_book_is_indicative_when_no_fresh_trade():
    picked = select_price(
        now=NOW,
        trades=[trade('old', NOW - dt.timedelta(minutes=31), '99.00')],
        book=book(NOW - dt.timedelta(minutes=18), '99.90', '100.10'))
    assert (picked.price, picked.price_basis) == (
        decimal.Decimal('100.00'), 'midpoint')
```

Cover exact 1,800-second boundary, canceled newest trade revealing the prior
valid trade, corrected price, no/crossed/one-sided book, mismatched ISIN/MIC,
and provider timestamp absent.

- [ ] **Step 2: Write failing transaction/cursor tests**

Create two fake files. Force quote persistence to raise after trade events are
staged. Assert cursor, events, quote, and accepted cycle are all absent after
rollback. Then run normally and assert all four appear together. Re-run the
same remote file and assert no duplicate event/quote is written; a cycle may
record `no_newer`.

- [ ] **Step 3: Run collection tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_market_data.py -q`

Expected: FAIL because collection/selection does not exist.

- [ ] **Step 4: Implement active mapping payload reads**

Collection reads the named generation payload, validates its SHA-256, and
selects only mapped decisions whose ticker is in `active_tickers`. It does not
query `RadarInstrument.is_primary`, because a shadow generation is deliberately
not active for the board. Build exact `(mic, isin) -> decision` indexes and
reject duplicate identities assigned to different social tickers.

- [ ] **Step 5: Apply trade files into the retained journal**

For every accepted post-trade file, lock the cursor row, parse the complete
batch, load original events required by corrections/cancellations, apply
events in deterministic order, and upsert by `(mic, event_id)`. A cancellation
marks its original event revoked through the normalized event set; it never
deletes audit evidence. Only after quote selection and cycle metrics are
staged does one commit advance the cursor.

Pre-trade files use the same cursor/cycle transaction. They need no long-lived
book journal: select the newest valid book in the accepted batch/current
snapshot and persist its bid/ask in the resulting `RadarQuote`. When processing
a post-trade file, the selector may reuse only the latest stored quote's book
whose provider event timestamp is still within 1,800 seconds; fetch time never
refreshes that book.

A later remote ID with the same verified checksum is recorded as `duplicate`:
it writes no event or quote, but advances the cursor to that later remote ID in
the same transaction so the collector cannot become stuck re-reading it.

- [ ] **Step 6: Persist one shadow snapshot per selected instrument and poll**

Build `Quote(source='deutsche_boerse_delayed', provider_delay='delayed')` from
the selected trade/midpoint and call
`quotes.record_quotes(normalized, now, is_shadow=(mode == 'shadow'), commit=False)`.
Repeated scheduled polls may write the same event timestamp because
frozen-tape detection needs consecutive evidence. The unique fetched time is
the cycle's scheduled UTC instant; processing duplicate files within that
cycle remains idempotent.

- [ ] **Step 7: Contain per-instrument and structural failures correctly**

An invalid record increments rejected-record count and excludes only that
instrument when the file envelope/identity map is still structurally valid.
Invalid gzip/JSON, missing batch-level source time/MIC, conflicting event IDs,
or reference completeness contradictions reject the entire file, write a
`rejected` cycle in a separate failure transaction, and leave the cursor
unchanged.

- [ ] **Step 8: Add bounded retention**

`retention.prune_market_data(now)` deletes trade-event rows received before
`now - 48h` and cycle rows scheduled before `now - 14d` in 5,000-row chunks.
It never deletes an event still referenced by a correction inside the 48-hour
window. Cursor and mapping-generation tables are excluded from this function.

- [ ] **Step 9: Run collection/retention tests**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_market_data.py \
  tests/test_radar_quotes.py tests/test_radar_quote_retention.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit the shadow collector**

```bash
git add personal_apps/features/radar/market_data.py \
  personal_apps/features/radar/quotes.py personal_apps/features/radar/retention.py \
  personal_apps/tests/test_radar_market_data.py \
  personal_apps/tests/test_radar_quote_retention.py
git commit -m "feat(radar): collect German market data in shadow"
```

---

### Task 8: Backfill history and compose the truthful Xetra proxy seam

**Files:**
- Modify: `personal_apps/features/radar/history.py`
- Modify: `personal_apps/features/radar/market_data.py`
- Modify: `personal_apps/features/radar/leaderboard.py`
- Modify: `personal_apps/features/radar/detail.py`
- Modify: `personal_apps/features/radar/detail_panel.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/features/radar/retention.py` `[A1]`
- Create: `personal_apps/scripts/backfill_radar_market_history.py`
- Modify: `personal_apps/tests/test_radar_history.py`
- Modify: `personal_apps/tests/test_radar_leaderboard.py`
- Modify: `personal_apps/tests/test_radar_detail.py`
- Modify: `personal_apps/tests/test_radar_api.py`
- Modify: `personal_apps/tests/test_radar_market_data.py`
- Modify: `personal_apps/tests/test_radar_quote_retention.py` `[A1]`

**Interfaces:**
- Produces `HistorySeries(closes, history_proxy, proxy_mic, proxy_venue, native_mic, native_venue, native_from)`.
- Produces `history.series_for(ticker, market, mic, days, today) -> HistorySeries`.
- Extends `record_closes(ticker, closes, now, *, market='us', mic=None, currency='USD', source='legacy', price_basis='close', adjustment_basis=None, is_shadow=False)` with source-priority overwrite rules. Every selected v2 provider passes `adjustment_basis='split'`; only migration-era compatibility may leave it NULL.
- Produces `materialize_native_closes(now, *, mode) -> int` from valid executed events only.
- Produces `GroupedInstrument(ticker, mic, currency)` and
  `market_data.grouped_instrument_map() -> dict[str, GroupedInstrument]`, keyed
  by exact provider symbol from one unambiguous primary US mapping.
- Produces `market_data.ingest_grouped_day(provider, day, now) -> GroupedDayResult` `[A1]`, the shared transactional writer both the daily job (Task 9) and the universe backfill mode use; shadow/live state comes only from validated config.
- Produces `leaderboard.chatter_candidates(...)` and
  `market_data.active_price_tickers(now)` here as prerequisites for grouped
  active-union coverage; Task 9 reuses rather than reimplements them.
- Produces a resumable CLI with `--market us|de|us-universe|all` `[A1]`, `--limit`, `--resume-after`, `--dry-run`, and explicit `--apply`.

- [ ] **Step 1: Write failing source-priority and shadow tests**

```python
def test_native_close_cannot_be_overwritten_by_yahoo():
    record_closes('AAPL', [(DAY, D('100.00'))], NOW, market='de', mic='XETR',
                  currency='EUR', source='deutsche_boerse_delayed')
    record_closes('AAPL', [(DAY, D('99.00'))], LATER, market='de', mic='XETR',
                  currency='EUR', source='yahoo_chart')
    row = RadarDailyClose.query.filter_by(
        ticker='AAPL', market='de', mic='XETR', close_date=DAY).one()
    assert (row.close, row.source) == (D('100.00'), 'deutsche_boerse_delayed')


def test_live_history_reader_excludes_newer_shadow_close():
    add_close('AAPL', DAY, '100', is_shadow=False)
    add_close('AAPL', DAY + dt.timedelta(days=1), '101', is_shadow=True)
    assert closes_for(['AAPL'], market='de', mic='XGAT')['AAPL'] == [(DAY, D('100'))]
```

- [ ] **Step 2: Write failing proxy-seam tests**

Create XETR closes on days 1–5 and XGAT native closes on days 4–6 with the same
instrument ISIN. Assert the series is XETR on days 1–3 and XGAT on days 4–6,
with `native_from=day4`. Delete XGAT day5 and assert day5 is missing, not
patched by XETR. Change the XETR ISIN or currency and assert no proxy is used.

- [ ] **Step 3: Run history/detail tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_history.py tests/test_radar_detail.py tests/test_radar_leaderboard.py tests/test_radar_api.py -q`

Expected: FAIL on missing provenance/series metadata.

- [ ] **Step 4: Implement deterministic source priority**

```python
CLOSE_SOURCE_PRIORITY = {
    'legacy': 0,
    'twelvedata': 10,  # [A1] the incumbent US writer during overlap
    'yahoo_chart': 10,
    'massive_grouped': 12,  # [A1] official beats unofficial for the same US day
    'deutsche_boerse_delayed': 20,
}
```

`record_closes` updates an existing row only when the incoming source priority
is greater or equal; equal priority permits provider restatement. Live reads
always add `is_shadow IS FALSE`. Existing NULL source rows normalize to
`legacy`; no old data disappears during overlap. Upsert lookup includes the
incoming `is_shadow` value, matching Task 2's five-column unique identity.
`fetch_into_store` passes the adapter's exact `provider.source`; an adapter
without that attribute is `legacy` during compatibility. Selected v2 writes
from Twelve Data, Yahoo, Massive, and Deutsche Börse store
`adjustment_basis='split'`; migration-era NULL is interpreted as split only
for known incumbent Twelve Data rows. A source/basis conflict is refused
rather than overwritten.

- [ ] **Step 5: Implement one-seam history composition**

For non-XGAT identities, `series_for` returns native rows and no proxy. For
XGAT, load its current instrument ISIN, find the XETR row with the exact same
ISIN and EUR currency, then:

```python
native_from = min(native_by_day) if native_by_day else None
proxy = {day: close for day, close in xetra_by_day.items()
         if native_from is None or day < native_from}
combined = {**proxy, **native_by_day}
```

Return sorted combined closes plus explicit proxy/native metadata. Never read
US rows. `leaderboard._quote_sigmas` uses these combined closes, while current
move/divergence continues to use only quote snapshots from the selected MIC.

- [ ] **Step 6: Add chart metadata without changing the chart arrays**

Extend `detail.Chart` with `history_proxy`, `proxy_mic`, `proxy_venue`,
`native_mic`, `native_venue`, and `native_from`, all defaulting to false/None
for compatibility. `detail_panel.build` obtains `HistorySeries`, passes only
its close pairs to existing calendar alignment, and carries metadata to
`routes.api`. Intraday spans report no history proxy because they read actual
quote snapshots.

- [ ] **Step 7: Implement native close materialization**

For each mapped MIC/ISIN and Berlin trading day, prefer the newest valid event
marked official close. If none exists, choose the final non-revoked executed
trade at or before venue close. Never use a book/midpoint. Write
Write `source='deutsche_boerse_delayed'`, `price_basis='close'`,
`adjustment_basis='split'`, and shadow state matching collection mode.
Re-running the same day is idempotent and may
replace Yahoo at higher source priority.

Also derive XGAT `regular_close` at 17:30 from an official close or the final
valid executed trade at/before 17:30. If absent, leave it NULL.

When selecting a current German quote, attach `previous_close` from the prior
trading day's `HistorySeries`. An XGAT quote may therefore use its exact-ISIN
Xetra proxy before native history accumulates; an absent/mismatched proxy
leaves the baseline NULL. This baseline may calculate displayed regular move
and sigma, but it never substitutes the current venue quote.

- [ ] **Step 7b: Extract the exact chatter-active union used by grouped validation**

Move the existing pass-one SQL aggregation, voice/channel counts, and
`scoring.is_eligible` decision from `leaderboard.build_rows` into
`_chatter_survivors(sources, now, window_hours)`. Preserve its stored tuple
shape so pass two remains equivalent. `chatter_candidates` returns its sorted
keys without market, quote, history, profile, or segment reads;
`active_price_tickers` is the union over 1h/4h/24h. Before/after leaderboard
tests must preserve every row, exclusion count, and query bound. Task 9 uses
these functions unchanged for polling.

- [ ] **Step 8: Write the resumable Yahoo backfill CLI**

The command orders missing/stale instruments deterministically by ticker/MIC,
requires exact current `RadarInstrument.provider_symbol`, appends `.DE` only
for XETR, and verifies Yahoo metadata through `YahooProvider` before writing.
It requests the existing `history.HISTORY_DAYS == 780` trading-day depth so
the shipped 3Y chart does not regress; the spec's 400-calendar-day minimum is
a floor, not a reason to discard the established longer span.
`--dry-run` is the default and prints counts/next resume key only. `--apply`
performs bounded commits per instrument. `--resume-after AAPL:XNAS` resumes
strictly after that key. The two flags are mutually exclusive.

Add tests that `--limit` bounds attempted instruments (not successful ones),
a failed ticker advances the resumable attempt cursor, and a second run writes
no duplicate dates.

The Yahoo US arm of the backfill covers only the active board union — its
role after this amendment is the deep tail beyond Massive's two-year window,
preserving the shipped 3Y span for tickers the board shows `[A1]`. In addition
to this explicit bootstrap, persist enough completion state for Task 9 to
admit at most two newly active, 3Y-incomplete tickers per 15-minute history
cycle and remove them once complete.

- [ ] **Step 8b: Add the grouped universe backfill mode `[A1]`**

`--market us-universe` iterates US trading days newest-first from yesterday
back to the free tier's two-year depth, calling
`market_data.ingest_grouped_day(provider, day, now)` per day. The shadow state
is never a caller choice: `ingest_grouped_day` derives
it from `RADAR_US_CLOSE_SOURCE` (`shadow` → `is_shadow=True`; `massive` →
`is_shadow=False`), and the `us-universe` mode REFUSES to run under `legacy`
with a message naming the flag — an ungated run would overwrite the
incumbent live US closes at higher priority and turn the Task 11 agreement
gate into massive-vs-massive self-agreement.

`grouped_instrument_map` queries `RadarInstrument.market == 'us'` and
`is_primary IS TRUE`, joined by ticker to `TickerUniverse.delisted_at IS
NULL`. It keys the result by exact uppercase `provider_symbol` and preserves
the row-owned ticker, MIC, and currency. If one provider symbol maps to more
than one identity, omit it and report an ambiguity. Never use
`universe.load_lookup()` or ticker/name text as grouped storage identity.

`ingest_grouped_day` calls `MassiveProvider.grouped_closes`, joins its exact
provider-symbol keys through that map, and computes provider, mapped, written,
unmatched-provider, unmatched-universe, malformed, duplicate-conflict, and
current board-active coverage counts. It accepts a day only when the envelope
and exact exchange-local date are valid, provider rows are at least 5,000,
and at least 95% of the current board-active mapped US union is present.
An accepted attempt writes closes with `source='massive_grouped'`,
`price_basis='close'`, and `adjustment_basis='split'` and its
`RadarGroupedCloseDay` row in one transaction. A non-accepted attempt writes
no grouped closes, persists `no_data|rejected|transport_error` plus bounded
error/backoff evidence, and remains retryable. No path uses or advances a
`RadarMarketDataCursor`. `--resume-after 2026-06-30` resumes strictly before that date
(the date is the cursor in this mode); `--limit` bounds attempted days. At 5
calls/minute the full two-year backfill is ~500 requests ≈ 100 minutes,
stated in `--dry-run` output.

Tests: a failed middle day leaves earlier and later days written and is
retried on rerun; a rerun writes no duplicate dates; under
`RADAR_US_CLOSE_SOURCE=legacy` the mode refuses before any provider call;
a live grouped close overwrites a `twelvedata` or `yahoo_chart` row for the
same US identity/date (priority 12 > 10); and identity isolation — a
grouped write addresses only US-market identities and can never match a
German-market row, proven by seeding a same-ticker `de`/`XGAT` close and
asserting it is untouched. Also prove exact provider-symbol identity preserves
MIC/currency, duplicate mappings are refused, empty and below-threshold days
do not advance, a failed write rolls back both closes and accepted state, and
the `universe.load_lookup()` symbol/name path is unreachable.

- [ ] **Step 8c: Slot the 1D chart by provider event time `[A3]`**

In `detail.py`, `intraday_prices` currently keys each 15-minute slot by
`fetched_at`; the 1W path (`_daily_anchors`) already selects by `quote_ts`
and drops NULLs — it is the reference behavior and needs no change. Scope
this step to `intraday_prices` (the 1D span) only: place each print by
`quote_ts`, drop rows with
`quote_ts IS NULL`, order by `(quote_ts, fetched_at)`, and deduplicate only the
exact `(quote_ts, price)` observation: a print re-fetched across many polls
occupies the single slot of its event time and the line honestly ends at the
last real print. Equal prices at distinct event times remain separate prints;
price equality alone is never a dedupe key.

Teeth first, two fixtures. (1) Out-of-span: seed one quote row whose
`quote_ts` is 46 hours old and five
poll rows re-storing it with fresh `fetched_at` values across the current
1D window; assert against the CURRENT implementation that multiple 1D slots
carry the price (the stale flat line) and watch that assertion fail once the
fix lands — the fixed chart draws zero populated slots because the event
time predates the span. (2) In-span: seed one print whose `quote_ts` lies
inside the 1D window, re-stored by three later polls with fresh
`fetched_at`; the fixed chart populates exactly one slot, at the event
time. Add a third fixture with equal prices at two distinct `quote_ts` values
and assert both survive. Keep the
existing no-carry-forward rule: absent slots stay `None`.

- [ ] **Step 8d: Bound daily-close retention `[A1]`**

Universe-wide grouped ingestion makes `radar_daily_closes` grow by one row
per US ticker per trading day (~12.6k/day; roughly 10M rows ≈ order 1 GB at
steady state) — bounded only if pruned. Extend `retention.prune_market_data`
to delete daily-close rows with `close_date` older than
`max(detail.SPAN_DAYS.values()) + 90` CALENDAR days (1095 + 90 = 1185 today
— `HISTORY_DAYS` counts TRADING days and must not be used as a calendar
horizon), shadow rows included, but never rows with
`source='deutsche_boerse_delayed'`: native German closes are observed, not
refetchable, and their universe is small enough to keep. Tests: a close
still displayable on the widest (3Y) chart span survives the prune; a
non-native row just outside the horizon is deleted; a native
`deutsche_boerse_delayed` row outside the horizon survives; the prune leaves
quote snapshots and cursors alone.

Massive shadow cleanup is narrower and separately guarded: retain the complete
shadow lane through the gate and for seven complete days after activation.
Only after the report- and instrument-map-bound gate/audit hashes are
recorded in the three validated cleanup settings may retention prune
`massive_grouped` shadow rows older than 30 calendar days. It never prunes
live rows or native Deutsche Börse rows. Tests
prove the seven-day and recorded-hash guards independently and first prove a
broken missing guard would delete rollback evidence prematurely.

- [ ] **Step 9: Run history, ranking, detail, API, and script tests**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_history.py tests/test_radar_leaderboard.py \
  tests/test_radar_detail.py tests/test_radar_api.py \
  tests/test_radar_market_data.py tests/test_radar_massive.py \
  tests/test_radar_quote_retention.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit backfill and proxy history**

```bash
git add personal_apps/features/radar/history.py \
  personal_apps/features/radar/market_data.py \
  personal_apps/features/radar/leaderboard.py personal_apps/features/radar/detail.py \
  personal_apps/features/radar/detail_panel.py \
  personal_apps/features/radar/routes/api.py \
  personal_apps/features/radar/retention.py \
  personal_apps/scripts/backfill_radar_market_history.py \
  personal_apps/tests/test_radar_history.py \
  personal_apps/tests/test_radar_leaderboard.py \
  personal_apps/tests/test_radar_detail.py personal_apps/tests/test_radar_api.py \
  personal_apps/tests/test_radar_market_data.py \
  personal_apps/tests/test_radar_quote_retention.py
git commit -m "feat(radar): backfill venue-aware price history"
```

---

### Task 9: Schedule independent providers behind safe activation flags

**Files:**
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/features/radar/leaderboard.py`
- Modify: `personal_apps/features/radar/scheduling.py`
- Modify: `personal_apps/features/radar/market_data.py`
- Modify: `personal_apps/run_radar_ingest.py`
- Modify: `personal_apps/tests/test_radar_config.py`
- Modify: `personal_apps/tests/test_radar_leaderboard.py`
- Modify: `personal_apps/tests/test_radar_scheduling.py`
- Modify: `personal_apps/tests/test_radar_daemon.py`
- Modify: `personal_apps/tests/test_radar_market_data.py`

**Interfaces:**
- Reuses Task 8's `leaderboard.chatter_candidates(sources, now, window_hours) -> list[str]` and `market_data.active_price_tickers(now) -> list[str]` without a second eligibility implementation.
- Produces `scheduling.due_symbols_from(source, symbols, now, limit) -> list[str]` and fixed-interval rescheduling (five-minute Finnhub default, 15-minute Yahoo fallback `[A2]`) without deleting rolling-window state.
- Produces `market_data.claim_post_close(source, market, now) -> date | None`, backed by `RadarProviderSessionState` and committed before any remote quote call.
- Produces config `RADAR_US_PRICE_PROVIDER=finnhub|yahoo` (default `finnhub`), `RADAR_DE_PRICE_MODE=legacy|shadow|active` (default `legacy`), and `RADAR_US_CLOSE_SOURCE=legacy|shadow|massive` (default `legacy`) `[A1]`.
- Validates optional cleanup evidence `RADAR_US_CLOSE_ACTIVATED_AT`,
  `RADAR_US_CLOSE_GATE_REPORT_SHA256`, and
  `RADAR_US_CLOSE_GATE_AUDIT_SHA256`; all three or none, with none meaning
  cleanup disabled.
- Produces independent scheduler jobs `radar_us_quotes`, `radar_de_market_data`, `radar_market_history`, `radar_us_grouped_closes` `[A1]`, and weekly `radar_mappings`.
- Produces `market_data.ops_summary(now) -> dict`, a 60-second memoized database-only health summary with no provider calls.

- [ ] **Step 1: Re-run and extend the Task 8 chatter-candidate parity tests**

Seed eligible/ineligible tickers across the 1h, 4h, and 24h windows, including
a ticker whose older low-text-ratio evidence excludes it at 24h but whose new
evidence passes at 1h. Assert:

```python
expected = set()
for hours in (1, 4, 24):
    expected.update(leaderboard.chatter_candidates(SOURCES, NOW, hours))
assert set(market_data.active_price_tickers(NOW)) == expected
```

For each window, compare `chatter_candidates` to the survivor keys produced by
the extracted pass-one helper used inside `build_rows`; one judgement must not
be copied into two implementations. These tests are already green from Task
8; add only scheduling assertions here and do not re-extract the helper.

- [ ] **Step 2: Verify the scheduler consumes the shared eligibility pass**

Import Task 8's public functions directly. A monkeypatched
`leaderboard.chatter_candidates` must change both the active grouped-coverage
denominator and scheduler union, proving there is one owner. No market,
quote, history, profile, or segment lookup may be introduced into that helper.

- [ ] **Step 3: Add a rolling-set due query**

```python
def due_symbols_from(source, symbols, now, limit):
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        return []
    rows = (RadarPollState.query
            .filter(RadarPollState.source == source,
                    RadarPollState.symbol.in_(symbols),
                    RadarPollState.next_due_at <= now)
            .order_by(RadarPollState.next_due_at.asc(),
                      RadarPollState.symbol.asc())
            .limit(limit).all())
    return [row.symbol for row in rows]
```

Add `record_fixed_poll(source, symbol, now, interval)` that stamps the attempt
and exact next due time. Do not call `retire_untracked`: price candidates are a
rolling set, and deleting their state would make arrivals monopolize every
cycle.

- [ ] **Step 4: Write failing configuration and independence tests**

```python
def test_price_provider_defaults_preserve_live_behavior(monkeypatch):
    monkeypatch.delenv('RADAR_US_PRICE_PROVIDER', raising=False)
    monkeypatch.delenv('RADAR_DE_PRICE_MODE', raising=False)
    monkeypatch.delenv('RADAR_US_CLOSE_SOURCE', raising=False)
    assert price_provider_config() == ('finnhub', 'legacy', 'legacy')


def test_yahoo_failure_does_not_skip_german_cycle(monkeypatch):
    monkeypatch.setattr(daemon, '_run_us_price_cycle', raising_provider_error)
    german = Mock(return_value=CycleSummary.accepted(3))
    monkeypatch.setattr(daemon, '_run_de_price_cycle', german)
    assert daemon._scheduled_us_quotes()['error'] is True
    result = daemon._scheduled_de_market_data()
    assert result.selected_quotes == 3
    german.assert_called_once()
```

Add the reverse failure test, missing Deutsche Börse cookie in shadow/active,
invalid flag value startup refusal, and no provider factory construction for a
disabled path. Add all-or-none cleanup-evidence validation, exact lowercase
SHA-256, UTC activation timestamp, and absent-evidence-means-no-cleanup tests.

- [ ] **Step 5: Implement exact flags and factories**

`price_provider_config()` validates the three enums at startup `[A1]`.
`legacy` runs
the current Finnhub/Twelve behavior; `shadow` runs the Deutsche Börse
collector with `is_shadow=True` while live German reads remain legacy;
`active` runs it with `is_shadow=False` and never constructs/calls Twelve Data
for German prices. Yahoo activation never constructs/calls Finnhub for US
quotes, but the Finnhub profile job remains untouched. `[A2]` The `yahoo` US
value is a fallback path, not a planned activation — the default stays
`finnhub` through every rollout stage. `[A1]` `RADAR_US_CLOSE_SOURCE`:
`legacy` retains the Twelve Data US history writer and never constructs the
Massive provider; `shadow` runs the grouped job with `is_shadow=True` while
Twelve Data keeps writing live rows, feeding the Task 11 agreement gate;
`massive` runs it with `is_shadow=False` and stops the Twelve Data US
history writer. A missing `RADAR_MASSIVE_API_KEY` under `shadow` or
`massive` refuses startup the same way an invalid enum does — a silently
dormant close source must not look activated.

Do not place access-cookie content in config summaries. Log only
`dbag_access_configured=true|false`.

- [ ] **Step 6: Implement fair active-set polling**

`active_price_tickers` unions the exact 1h/4h/24h chatter candidates. The
German file cycle materializes every mapped active ticker because one file
download already contains the venue data. `[A2]` Finnhub polls the active
union under poll source `price:finnhub` on the five-minute cadence; Yahoo
fallback mode tracks the same union under poll source `price:yahoo`, asks at
most 100 due symbols per 15-minute cycle,
and calls `record_fixed_poll` for every attempted symbol whether it succeeds
or fails; provider backoff prevents an outage from retrying immediately.
`[A3]` Either US quote wrapper first consults the US market calendar: while
the calendar answers closed (weekend, holiday, overnight outside the
recognized pre/post phases) it performs no provider request, except one
post-close cycle per trading day to capture the closing print. That exception
is eligible only in the 60 minutes after the calendar's extended-session
close. `claim_post_close` locks `(source, 'us')`, verifies the resolved session
date is newer than `last_post_close_session_date`, writes the date and
`claimed_at`, and commits before the provider request. Once claimed, failure
does not reopen the date. The ordinary open-session path does not claim it.
Create the key with an idempotent insert before `SELECT ... FOR UPDATE` so two
first-ever callers cannot both win; a duplicate-key race retries the locked
read. Resolve the active candidate set before claiming, and do not claim an
empty cycle.
The skip is logged as a structured no-op, not an error.

- [ ] **Step 7: Register independent jobs without double polling**

Replace `radar_quotes` with:

```python
us_quote_minutes = 5 if us_provider == 'finnhub' else 15  # [A2]
scheduler.add_job(_scheduled_us_quotes, 'interval', minutes=us_quote_minutes,
                  id='radar_us_quotes', max_instances=1, coalesce=True)
scheduler.add_job(_scheduled_de_market_data, 'interval', minutes=5,
                  id='radar_de_market_data', max_instances=1, coalesce=True,
                  next_run_time=dt.datetime.now(dt.timezone.utc))
scheduler.add_job(_scheduled_history, 'interval', minutes=15,
                  id='radar_market_history', max_instances=1, coalesce=True)
scheduler.add_job(_scheduled_us_grouped_closes, 'cron', hour=23, minute=30,
                  id='radar_us_grouped_closes', max_instances=1,
                  coalesce=True)  # [A1] 23:30 UTC is after the US close in both DST states
```

`[A1]` `_scheduled_us_grouped_closes` is a no-op under
`RADAR_US_CLOSE_SOURCE=legacy`. Under `shadow` and `massive` it ingests
every unfetched US
trading day among the most recent seven via
`market_data.ingest_grouped_day` (bounded catch-up after daemon downtime;
five calls fit inside one pacer minute) with the mode's shadow state,
selecting missing/non-accepted dates from `RadarGroupedCloseDay` and logging
its stored matched/unmatched/error counts. Accepted state, not a maximum date,
is progress, so a failed middle day remains retryable.

The German wrapper downloads every five minutes while either venue is open
and through the 30-minute source-delay buffer after close. Its immediate
startup call consumes any retained cursor gap even when the service restarts
while closed; after that, closed/no-gap invocations perform no HTTP request.
The history job materializes the post-close daily value and repeats the same
idempotent reconciliation on its first run after 06:30 Berlin the next morning
from the retained trade journal.

Weekly mapping behavior is mode-aware: `legacy` retains the current job;
`shadow` builds/updates a shadow generation but never activates it; `active`
builds a complete candidate generation. An identical payload keeps the active
generation. A payload that adds/removes an identity or changes ticker, MIC,
symbol, ISIN, or currency stays `shadow` for identity review and explicit
activation; it never changes a live primary automatically. A failed
generation preserves the current active one.

`_scheduled_history` handles US closes by `RADAR_US_CLOSE_SOURCE` `[A1]`:
`legacy` and `shadow` retain the current Twelve Data live writer so shadow has
an independent incumbent; `massive` stops that writer and lets the grouped
live lane own recent US closes. Under `shadow` or `massive`, the 15-minute history cycle
may select at most two newly board-active tickers whose stored live history
does not yet reach the 3Y floor, using poll source `history:yahoo-tail` for
fair deterministic retries. Once a ticker is complete it is not called again.
This is the only recurring per-symbol Yahoo history path. The
German active path materializes native closes from Deutsche Börse and never
makes recurring Yahoo `.DE` calls; German Yahoo use remains the explicit
backfill command from Task 8.

The scheduled prune calls `retention.prune_market_data`. Every scheduler
wrapper catches/logs its own provider error and returns a structured result;
none may terminate the daemon.

`ops_summary` reads the latest cycle per MIC/channel, current mapping
generation counts/refusals, quote-basis/quality counts, cursor lag, Yahoo
backoff/status, Massive grouped-day state (latest accepted date; retryable
gaps; provider/matched/written/unmatched/malformed/conflict counts; HTTP,
error, and backoff state), the last claimed US post-close session date
`[A1]``[A3]`, and
native/proxy history counts. Cache for 60 seconds in
process and expose a `clear_ops_memo()` test seam. It must not import or call a
provider module.

- [ ] **Step 8: Pin the scheduler and no-double-call tests**

Assert all five job IDs appear exactly once, their intervals/cron are exact
(`radar_us_quotes` at five minutes under the default `finnhub` flag and 15
under `yahoo` `[A2]`; `radar_us_grouped_closes` at 23:30 UTC `[A1]`), and
the old `radar_quotes` ID is absent. Under Yahoo/active flags, monkeypatch the
legacy provider constructors to raise and prove no call reaches them; under
`RADAR_US_CLOSE_SOURCE=massive`, prove the Twelve Data history writer is
never constructed and the grouped job runs; under `legacy`, prove the grouped
job returns its no-op result without constructing the Massive provider `[A1]`.
Assert a closed-calendar US cycle performs no provider call and the single
post-close cycle does `[A3]`. Restart, concurrent-claim, DST, early-close,
weekend, overnight-before-open, outside-the-60-minute-window, and provider-
failure tests must not duplicate or misassign the claimed session date. Under
default flags, prove the current provider paths still run. Call `ops_summary`
twice inside 60 seconds and assert the SQL counter does not increase on the
second call; monkeypatch every provider constructor to raise and prove the
summary still succeeds from stored state; assert the summary carries the
Massive grouped-close fields (accepted date, gaps, all counts, error/backoff)
and the post-close claim `[A1]``[A3]`. Prove the future deep-tail queue tries
at most two incomplete newly active tickers per history cycle, advances failed
attempts fairly, and never calls an already-complete ticker.
Assert startup performs one retained-gap check, a closed/no-gap interval makes
no HTTP call, the 22:00–22:30 Berlin buffer still collects, and the first
post-06:30 history run repeats native-close reconciliation exactly once per
local trading date.

- [ ] **Step 9: Run daemon/config/candidate tests**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_config.py tests/test_radar_leaderboard.py \
  tests/test_radar_scheduling.py tests/test_radar_daemon.py \
  tests/test_radar_market_data.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit dormant orchestration**

```bash
git add personal_apps/features/radar/config.py \
  personal_apps/features/radar/leaderboard.py \
  personal_apps/features/radar/scheduling.py \
  personal_apps/features/radar/market_data.py personal_apps/run_radar_ingest.py \
  personal_apps/tests/test_radar_config.py \
  personal_apps/tests/test_radar_leaderboard.py \
  personal_apps/tests/test_radar_scheduling.py \
  personal_apps/tests/test_radar_daemon.py \
  personal_apps/tests/test_radar_market_data.py
git commit -m "feat(radar): schedule independent market data jobs"
```

---

### Task 10: Surface actual venue, basis, age, and history proxy

**Files:**
- Modify: `personal_apps/features/radar/board.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/tests/test_radar_board.py`
- Modify: `personal_apps/tests/test_radar_api.py`
- Modify: `personal_apps/static/radar/src/types.ts`
- Modify: `personal_apps/static/radar/src/QuoteBadges.tsx`
- Modify: `personal_apps/static/radar/src/detail/PriceChart.tsx`
- Modify: `personal_apps/static/radar/src/detail/PriceChart.test.tsx`
- Modify: `personal_apps/static/radar/src/list/TickerRow.test.tsx`
- Modify: `personal_apps/static/radar/src/board/BoardPage.test.tsx`
- Modify: `personal_apps/static/radar/src/hardening.test.tsx`
- Modify: `personal_apps/static/radar/radar.css`

**Interfaces:**
- Extends `MarketQuote` with nullable `source`, `price_basis`, `bid`, and `ask`.
- Extends `DetailChart` with `history_proxy`, nullable proxy/native venue+MIC, and nullable `native_from`.
- Extends `BoardPayload` with optional `market_data_ops` from the cached database-only summary.
- Germany board header says `Tradegate-first Germany`; each row still names its actual Tradegate, Xetra, or US fallback venue.
- Indicative and proxy states use text plus neutral/amber styling, never green/red alone.

- [ ] **Step 1: Write failing backend serialization tests**

```python
def test_quote_serializes_tradegate_provenance():
    payload = api._quote(quote_view(
        venue='Tradegate BSX', mic='XGAT', source='deutsche_boerse_delayed',
        price_basis='midpoint', bid=D('99.90'), ask=D('100.10'),
        price=D('100.00'), regular_move=D('0.01'), extended_move=None,
        session='regular', quality='delayed', age_seconds=600,
        quote_ts=dt.datetime(2026, 8, 31, 12, 43), tape_status='ok',
        score_eligible=False, is_fallback=False))
    assert payload == {
        'market': 'de',
        'venue': 'Tradegate BSX',
        'mic': 'XGAT',
        'currency': 'EUR',
        'price': 100.0,
        'regular_move': 0.01,
        'extended_move': None,
        'session': 'regular',
        'quality': 'delayed',
        'age_seconds': 600,
        'quoted_at': '2026-08-31T12:43:00Z',
        'source': 'deutsche_boerse_delayed',
        'price_basis': 'midpoint',
        'bid': 99.9,
        'ask': 100.1,
        'tape_status': 'ok',
        'score_eligible': False,
        'score_term': 'chatter',
        'is_fallback': False,
    }
```

Use exact-key assertions on the full quote object rather than substring tests.
Assert board/detail legacy flat price fields equal the nested selected quote.
Add chart assertions for proxy metadata and an intraday chart with all proxy
fields false/None. Request the board twice inside the memo window and assert
the second request performs no additional market-data health query and no
provider call.

- [ ] **Step 2: Run backend API tests and verify they fail**

Run: `cd personal_apps && python -m pytest tests/test_radar_api.py tests/test_radar_board.py tests/test_radar_detail.py -q`

Expected: FAIL on missing fields/header metadata.

- [ ] **Step 3: Serialize one canonical quote/history decision**

Add source/basis/bid/ask to `_quote` from `QuoteView`; do not re-derive basis or
eligibility in the serializer. Add all `HistorySeries` metadata under the
existing detail `chart` object. Set `Board.market_venue` to
`Tradegate-first Germany` for `market=de` and keep `US markets` for US. The
board serializer adds `market_data_ops=market_data.ops_summary(generated_at)`;
the detail endpoint does not repeat it.

- [ ] **Step 4: Extend frontend types and fixtures**

```typescript
export type PriceBasis = 'trade' | 'midpoint' | 'close'
export type QuoteSource =
  | 'legacy' | 'finnhub' | 'twelvedata'
  | 'deutsche_boerse_delayed' | 'yahoo_chart'

export interface MarketQuote {
  source: QuoteSource | null
  price_basis: PriceBasis | null
  bid: number | null
  ask: number | null
}
```

Merge these fields into the existing interface rather than creating a second
quote shape. Extend every typed test fixture explicitly; do not use broad
`as MarketQuote` casts that could hide a missing production field.
Add the exact optional health-summary shape under `BoardPayload`; it is
operational status only and never controls client-side quote eligibility.

- [ ] **Step 5: Write failing quote-badge tests**

```tsx
it('labels an XGAT midpoint as indicative and not as a trade', () => {
  render(<QuoteBadges quote={quote({
    venue: 'Tradegate BSX', mic: 'XGAT', currency: 'EUR',
    price_basis: 'midpoint', bid: 99.9, ask: 100.1,
    score_eligible: false,
  })} />)
  expect(screen.getByText('Tradegate BSX · EUR')).toBeVisible()
  expect(screen.getByText('indicative')).toBeVisible()
  expect(screen.queryByText(/executed/i)).not.toBeInTheDocument()
})
```

Cover Tradegate trade, Xetra trade, US fallback, delayed age, stale age,
unavailable, and midpoint with no score. Assert fallback still says USD and
never receives the German venue label.

- [ ] **Step 6: Implement shared provenance copy**

`QuoteBadges` adds an `indicative` badge when `price_basis==='midpoint'` and
keeps the existing source/fallback/quality/session/tape/move badges. Bid/ask
are not crammed into board rows; detail accessible text includes both values
and the spread. `qualityText` still derives only freshness copy, not basis.

- [ ] **Step 7: Write and implement the visible history-seam label**

When `chart.history_proxy` is true, `PriceChart` renders:

```tsx
<p className="history-proxy-note">
  {`${chart.proxy_venue} history${chart.native_from
    ? ` through ${formatMarketDate(chart.native_from)}`
    : ''} · ${chart.native_venue} now`}
</p>
```

When false, no note or empty element renders. Add tests for proxy with a
seam, all-proxy before native accumulation, no proxy, and correct Berlin date
formatting.

- [ ] **Step 8: Add non-directional styling and responsive tests**

`.quote-basis.indicative` and `.history-proxy-note` use the existing warning/
muted palette, not `--up` or `--down`. Ensure badge wrapping and chart note do
not overflow at 390px. Add accessible text assertions so color removal does
not remove meaning.

- [ ] **Step 9: Run backend and frontend tests/build**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_api.py tests/test_radar_board.py \
  tests/test_radar_detail.py -q
npm test
npm run build
```

Expected: backend PASS, frontend PASS, TypeScript/Vite build succeeds.

- [ ] **Step 10: Commit truthful market-data presentation**

```bash
git add personal_apps/features/radar/board.py \
  personal_apps/features/radar/routes/api.py \
  personal_apps/tests/test_radar_board.py personal_apps/tests/test_radar_api.py \
  personal_apps/static/radar/src/types.ts \
  personal_apps/static/radar/src/QuoteBadges.tsx \
  personal_apps/static/radar/src/detail/PriceChart.tsx \
  personal_apps/static/radar/src/detail/PriceChart.test.tsx \
  personal_apps/static/radar/src/list/TickerRow.test.tsx \
  personal_apps/static/radar/src/board/BoardPage.test.tsx \
  personal_apps/static/radar/src/hardening.test.tsx \
  personal_apps/static/radar/radar.css
git commit -m "feat(radar): show market data provenance"
```

---

### Task 11: Build the READ ONLY shadow report and activation/rollback gates

**Files:**
- Create: `personal_apps/scripts/report_radar_market_data_shadow.py`
- Create: `personal_apps/tests/test_radar_market_data_report.py`
- Modify: `personal_apps/tests/test_radar_market_data.py`
- Modify during execution: `docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md`
- Modify during execution: `HANDOFF.md`

**Interfaces:**
- Produces `build_report(session, start, end, identity_audit=None, us_close_audit=None) -> ShadowReport` without remote calls or writes.
- CLI: `python -m scripts.report_radar_market_data_shadow --from ISO --to ISO [--gate german|us-closes] [--identity-audit FILE] [--us-close-audit FILE] [--json]` `[A1]` (default `--gate german`).
- Exit 0 only when every automatic gate GOVERNING THE SELECTED SWITCH passes — for `german`, the German gates plus a supplied/passing 50-row identity audit, with the grouped agreement gate reported informationally; for `us-closes`, the grouped agreement gate alone `[A1]`. Exit 2 for incomplete evidence; exit 1 for a failed truth/identity gate.
- Activation remains an operator action; the script reports readiness and never changes flags/mappings/rows.

- [ ] **Step 1: Write failing read-only guard tests**

```python
def test_report_rejects_every_mutating_statement(app):
    with app.app_context():
        install_statement_guard(db.engine)
        for sql in ('INSERT INTO radar_market_data_cycles (id) VALUES (1)',
                    'UPDATE radar_quotes SET price=0',
                    'DELETE FROM radar_quotes',
                    'CREATE TABLE forbidden (id INT)'):
            with pytest.raises(ReadOnlyViolation):
                db.session.execute(sa.text(sql))
```

The production entry starts `SET TRANSACTION READ ONLY` before its first
query. The SQLAlchemy `before_cursor_execute` guard rejects leading comments/
whitespace followed by INSERT, UPDATE, DELETE, REPLACE, CREATE, ALTER, DROP,
TRUNCATE, GRANT, or CALL. A test snapshots row counts/hashes before and after a
full report and asserts equality.

- [ ] **Step 2: Write failing threshold and denominator tests**

Seed cycles/mappings/quotes/history so each gate can fail alone. In particular:

- mapping denominator includes only top-100 30-day tickers for which a
  complete official reference shows a German listing;
- display coverage denominator includes mapped active instruments sampled in
  open-session cycles;
- `no_newer` counts as deterministic transport success but `rejected` and
  `transport_error` do not;
- p95 uses provider event age, never fetch age;
- a provider-closed/suspended date is excluded from expected history only when
  the stored reference/calendar evidence explicitly says so;
- history coverage uses a deterministic 20-instrument stratified sample and
  each instrument's one-year expected-session denominator;
- one wrong identity, midpoint-as-trade, venue hop, US-as-German, or
  proxy-as-native makes the truth gate fail regardless of percentages.

- [ ] **Step 3: Implement exact report fields and gate constants**

```python
MIN_IDENTITY_AUDIT = 50
MIN_MAPPING_COVERAGE = 0.90
MIN_DISPLAY_COVERAGE = 0.95
MAX_P95_EVENT_AGE_SECONDS = 1800
MIN_TRANSPORT_SUCCESS = 0.99
MIN_HISTORY_COVERAGE = 0.95
MIN_GROUPED_AGREEMENT_DAYS = 3             # [A1]
MIN_GROUPED_PROVIDER_ROWS = 5000           # [A1]
MIN_GROUPED_ACTIVE_COVERAGE = Decimal('0.95')  # [A1]
MIN_GROUPED_OVERLAP_ROWS = 100             # [A1]
MAX_GROUPED_CLOSE_DELTA = Decimal('0.005')  # [A1] 0.5% vs incumbent close
```

`ShadowReport` carries raw numerator/denominator, ratio, threshold, pass state,
and refusal/absence buckets for every gate. It also reports p50/p95 age,
trade/midpoint/stale/unavailable shares, file bytes, decompression ratio,
parse p50/p95, memory high-water input if recorded, source/channel gaps,
German mapping-generation hash, grouped-instrument-map hash, and Yahoo status
separately.

`[A1]` The report additionally computes the **US grouped-close agreement
gate**, independent of the German gates. It loads the expected US trading
dates from the calendar for the complete provider two-year entitlement and
requires an accepted `RadarGroupedCloseDay` shadow state for every date; each
accepted state must record at least `MIN_GROUPED_PROVIDER_ROWS` structurally
valid rows. The report recomputes `MIN_GROUPED_ACTIVE_COVERAGE` for every day
from the current board-active mapped US union, the exact current grouped map,
and persisted shadow closes; it does not trust a stale ingestion-time ratio.
Among the most recent expected dates, at least
`MIN_GROUPED_AGREEMENT_DAYS` are consecutive and each has at least
`MIN_GROUPED_OVERLAP_ROWS` ticker/date overlaps with incumbent live US
closes. Every overlap's relative delta must be at most
`MAX_GROUPED_CLOSE_DELTA`.

Split-like near-integer deltas, any other adjustment-basis mismatch, and
conflicting duplicate symbols are blockers, not observations to exclude from
the denominator. The report lists unmatched symbols, measured table rows/
daily growth, and projected steady-state storage. Zero overlap, zero active
denominator, too few rows, missing expected dates, missing state, or a missing
operator audit is `incomplete` and can never pass vacuously. This gate governs only the
`RADAR_US_CLOSE_SOURCE=massive` switch and is enforced only under
`--gate us-closes`; under `--gate german` it is informational. German
activation neither requires nor waits for it.

- [ ] **Step 4: Export and validate the identity audit**

Without `--identity-audit`, output a deterministic 50-row stratified sample:
ordinary shares, ETFs, XGAT, XETR fallback, dual listing, and every override.
The audit JSON schema is:

```json
{
  "generation_sha256": "64 lowercase hex characters",
  "reviewed_at": "2026-09-01T20:00:00Z",
  "reviewer": "Michi",
  "rows": [
    {
      "ticker": "AAPL",
      "mic": "XGAT",
      "symbol": "APC",
      "isin": "US0378331005",
      "currency": "EUR",
      "correct": true
    }
  ]
}
```

Validation requires exact generation hash, at least 50 unique tickers, all
required strata represented, and every `correct` true. The script cannot set
or infer `correct`.

For `--gate us-closes`, the script first emits deterministic close-gate JSON
and its SHA-256. The separate operator audit schema is:

```json
{
  "report_sha256": "64 lowercase hex characters",
  "instrument_map_sha256": "64 lowercase hex characters",
  "reviewed_at": "2026-09-04T20:00:00Z",
  "reviewer": "Michi",
  "accept_unmatched_symbols": true,
  "accept_storage_projection": true
}
```

`instrument_map_sha256` hashes sorted
`provider_symbol|ticker|mic|currency` rows from the exact unambiguous grouped
instrument map; it is the US mapping generation identity even though the
legacy US mappings do not use `RadarMappingGeneration`. Validation requires
exact current report and instrument-map hashes and
both explicit acceptances. The tool never fills them itself. Changing the
report, instrument map, mismatch list, or storage numbers invalidates the
audit. Keep the German identity audit and US-close audit independent.

- [ ] **Step 5: Run report tests and broken-variant checks**

Run: `cd personal_apps && python -m pytest tests/test_radar_market_data_report.py tests/test_radar_market_data.py -q`

Then temporarily invert each gate comparator in the test-local function and
prove its dedicated test fails. Also run broken variants that remove the
provider-row, active-coverage, overlap, complete-backfill, split-conflict, and
operator-audit requirements; each must make a red fixture falsely green and
therefore fail its teeth assertion. Restore the implementation and rerun
green.

- [ ] **Step 6: Create the execution ledger and refresh handoff evidence**

The ledger records for every task: commit, files, focused tests, independent
review verdict, open findings, and whether it is safe to continue. It also
records Task 1 contract hash, migration heads, mapping generation hash,
grouped-instrument-map hash, backfill state/counts, shadow interval, activation
report/audit hashes, activation timestamp, and report output.

Update `HANDOFF.md` with exact branch/worktree/HEAD, dirty-file ownership,
completed/open task, next action, test results, environment-only failures,
protected Telegram files, provider flags, and rollback generation ID. Git and
test evidence override stale prose.

- [ ] **Step 7: Commit report tooling and bookkeeping templates**

```bash
git add personal_apps/scripts/report_radar_market_data_shadow.py \
  personal_apps/tests/test_radar_market_data_report.py \
  personal_apps/tests/test_radar_market_data.py \
  docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md HANDOFF.md
git commit -m "feat(radar): gate market data activation"
```

- [ ] **Step 8: Execute the production shadow gate without activating**

After Michi deploys code/migration with `RADAR_DE_PRICE_MODE=shadow`, let one
complete 07:30–22:00 Berlin Tradegate session finish. Run the report for that
exact UTC interval, export the audit, have Michi review its 50 identities, then
rerun with the audit. Record all evidence in the ledger. Do not change a
provider mode when any truth/identity gate fails or any gate governing THAT
mode's switch is below threshold `[A1]` (the `--gate` scoping from Step 3
defines which gates govern which switch).

- [ ] **Step 9: Activation sequence after a green report for the switch**

Michi performs these operator-controlled state changes in order. German
activation (items 1–4) and the US close switch (items 5–6) are independent
tracks; neither waits for the other `[A1]`:

1. run the backfill CLI (`--market us`, `--market de`) in bounded `--apply`
   batches until the active-union US deep tail and verified Xetra histories
   are complete;
2. activate the audited mapping generation atomically and record the previous
   generation ID;
3. set `RADAR_DE_PRICE_MODE=active`, restart through the normal deploy path,
   and wait for the first accepted active German cycle;
4. verify Germany board/detail on XGAT, XETR fallback, midpoint, unavailable,
   and US fallback examples;
5. `[A1]` set `RADAR_US_CLOSE_SOURCE=shadow`, run the complete two-year
   universe backfill (`--market us-universe --apply`) in resumable bounded
   batches, and let at least three consecutive expected US trading days be
   accepted. Run `--gate us-closes` once without an audit, have Michi review
   agreement deltas, every unmatched symbol, and measured/projected storage,
   create the report- and instrument-map-bound audit, then rerun against that exact audit.
   Missing/failed expected dates must be retried before this can go green;
6. `[A1]` only on a green us-closes gate set
   `RADAR_US_CLOSE_SOURCE=massive` together with
   `RADAR_US_CLOSE_ACTIVATED_AT` and the exact report/audit SHA-256 settings,
   then rerun the complete universe backfill
   in the live lane. Preserve the shadow lane for the seven-day rollback
   window; afterward Task 8's guarded retention may prune shadow rows older
   than 30 days once both evidence hashes are recorded.

`[A2]` There is no Yahoo US activation step: `RADAR_US_PRICE_PROVIDER`
stays `finnhub`; the `yahoo` value exists for emergencies only.

Rollback sets German mode to `legacy`, applies the recorded prior mapping
generation, and leaves new rows/cursors/history intact. US-close rollback
returns `RADAR_US_CLOSE_SOURCE` to `legacy` `[A1]`; an emergency US quote
fallback sets `RADAR_US_PRICE_PROVIDER=yahoo` and is reverted to `finnhub`
when the emergency ends `[A2]`. No rollback track changes another track's
flag.

---

### Task 12: Contract the overlap only after the rollback window, then verify everything

This task is deliberately delayed. It begins only after at least seven full
production days on the new writers, a green shadow/active report, and Michi's
explicit decision that old-writer rollback is no longer required. Completing
Tasks 1–11 does not authorize it automatically.

**Files:**
- Create: `personal_apps/migrations/versions/b742e9d13c60_contract_radar_market_data_v2.py`
- Modify: `personal_apps/models.py`
- Modify: `personal_apps/features/radar/quotes.py`
- Modify: `personal_apps/features/radar/history.py`
- Modify: `personal_apps/tests/test_radar_migration.py`
- Modify: `personal_apps/tests/test_radar_quotes.py`
- Modify: `personal_apps/tests/test_radar_history.py`
- Modify: `docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md`
- Modify: `HANDOFF.md`

**Interfaces:**
- Makes quote `market`, `mic`, `currency`, `provider_symbol`, `source`, and `price_basis` non-null.
- Makes daily-close `market`, `mic`, `currency`, `source`, `price_basis`, and `adjustment_basis` non-null after the explicit migration-era classification.
- Removes the `(market IS NULL, mic IS NULL)` legacy-US compatibility branches only after migration proof.
- Downgrade restores nullability but does not erase normalized values.

- [ ] **Step 1: Write failing contraction migration tests**

Start from Task 2 schema with legacy NULL rows plus modern rows. Upgrade and
assert:

```python
quote = connection.execute(sa.text(
    "SELECT market, mic, currency, provider_symbol, source, price_basis "
    "FROM radar_quotes WHERE id=1")).one()
assert tuple(quote) == ('us', 'XNAS', 'USD', 'AAPL', 'legacy', 'trade')

close = connection.execute(sa.text(
    "SELECT market, mic, currency, source, price_basis, adjustment_basis "
    "FROM radar_daily_closes WHERE id=1")).one()
assert tuple(close) == ('us', 'XNAS', 'USD', 'legacy', 'close', 'split')
```

Assert every target column is non-nullable and an old-column-list insert now
fails. Downgrade restores nullable columns and preserves row values.

- [ ] **Step 2: Write the guarded contraction migration**

Backfill legacy quote identity from the ticker's current primary US
`RadarInstrument`; use `XNAS` only for a legacy row whose instrument is absent,
matching the current compatibility fallback. Backfill sources/bases exactly as
in Step 1. Classify adjustment basis as `split` only for rows whose source is
known to be the incumbent Twelve Data/legacy split-adjusted writer or whose
v2 writer already supplied it; abort rather than guessing for any unexplained
row. Abort with a raised SQL error if any target NULL remains before
the NOT NULL `ALTER COLUMN` operations.

Use `batch_alter_table` and name every CHECK/index explicitly. `down_revision`
is `6a21d4e8c9f0`. Downgrade changes nullability only; it does not drop v2
columns/tables, because Task 2 owns their destructive downgrade.

- [ ] **Step 3: Remove legacy NULL read branches**

Delete NULL-as-US OR legs from `quotes._quote_matches`, `statuses_for`,
`moves_for`, `history._market_filter`, and related tests. Keep
`source or 'legacy'` and `price_basis or 'trade/close'` defensive adapters for
one release so a manually restored older database fails safe rather than
raising in presentation.

- [ ] **Step 4: Run migration and focused regressions**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_migration.py tests/test_radar_quotes.py \
  tests/test_radar_quotes_batch.py tests/test_radar_history.py -q
python -m flask --app app db heads
```

Expected: PASS; head is `b742e9d13c60`.

- [ ] **Step 5: Commit the contraction separately**

```bash
git add personal_apps/migrations/versions/b742e9d13c60_contract_radar_market_data_v2.py \
  personal_apps/models.py personal_apps/features/radar/quotes.py \
  personal_apps/features/radar/history.py \
  personal_apps/tests/test_radar_migration.py \
  personal_apps/tests/test_radar_quotes.py \
  personal_apps/tests/test_radar_quotes_batch.py \
  personal_apps/tests/test_radar_history.py \
  docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md HANDOFF.md
git commit -m "refactor(radar): contract market data identity fields"
```

- [ ] **Step 6: Run complete backend/frontend verification**

Run:

```powershell
cd personal_apps
python -m pytest tests/ -q
npm test
npm run build
$shadowStart = Read-Host 'Shadow start UTC recorded in the execution ledger'
$shadowEnd = Read-Host 'Shadow end UTC recorded in the execution ledger'
$identityAudit = Read-Host 'Absolute path to the reviewed identity-audit JSON'
$usCloseAudit = Read-Host 'Absolute path to the reviewed US-close audit JSON'
python -m scripts.report_radar_market_data_shadow --from $shadowStart --to $shadowEnd --gate german --identity-audit $identityAudit --json
python -m scripts.report_radar_market_data_shadow --from $shadowStart --to $shadowEnd --gate us-closes --us-close-audit $usCloseAudit --json
```

The final report command uses the exact recorded values from the execution
ledger. Expected: all Python tests pass; all Vitest suites pass; TypeScript and
both Vite builds pass; both reports exit 0 with every governing gate true.

- [ ] **Step 7: Perform visual and operational verification**

Using headless Playwright against the local app, capture desktop 1440×1000 and
mobile 390×844 in light/dark for: XGAT trade, XGAT indicative, XETR fallback,
US fallback, stale, unavailable, and proxy-history detail. Verify no console
errors, horizontal overflow, hidden provenance, or direction-colored
freshness/basis state.

Read daemon logs/ops summary and confirm separate German/Yahoo/Massive
health, no
secret values, correct cadences (five-minute Finnhub US and German cycles,
daily grouped-close cron `[A1]``[A2]`), session-gated US polling with the
single post-close cycle `[A3]`, no legacy German calls in
active mode, no Twelve Data US history calls under
`RADAR_US_CLOSE_SOURCE=massive` `[A1]`, and no Finnhub quote calls under
Yahoo mode.

After seven complete active Massive days, verify the exact gate-report and
operator-audit hashes are stored before enabling the bounded shadow cleanup.
Run retention once and prove only `massive_grouped` shadow rows older than 30
calendar days were removed; live Massive history, native Deutsche Börse
history, grouped-day progress, and the hashed evidence remain.

- [ ] **Step 8: Final independent review and handoff**

Request a read-only review against every spec section and this plan. Resolve
all BLOCKER/SHOULD-FIX findings with focused tests and separate fix commits.
Update the ledger/HANDOFF with final HEAD, dirty-file ownership, migration
head, all test outputs, mapping/rollback generation IDs, active flags,
backfill counts, gate report, and the next safe operator action.

Do not remove the Twelve Data adapter in this plan; its code removal is a
later cleanup after the rollback period and is explicitly outside the spec's
activation work. The Finnhub adapter is not removal-eligible at all `[A2]`:
it remains the live US quote and profile source.

---

## Deployment compatibility matrix

| Through task | Live behavior | Safe rollback |
|---|---|---|
| 1 | no runtime change | remove capture-only commit |
| 2 | old writers/readers; additive columns/tables unused | Task 2 downgrade preserves legacy quote/close rows |
| 3 | current providers, now with legacy provenance defaults and shadow exclusion | revert code; additive schema remains harmless |
| 4–6 | dormant provider/mapping code (Yahoo, Massive `[A1]`); shadow generation does not affect primaries | disable job/revert code; prior mapping untouched |
| 7–8 | shadow rows/history may accumulate but live readers exclude them | stop collector; no user-visible change |
| 9 | defaults still Finnhub quotes + Twelve Data closes + legacy German path `[A1]``[A2]` | restore default flags |
| 10 | clients understand new fields; legacy values still serialize | old UI can ignore additive JSON fields |
| 11 active | German, US-quote, and US-close paths independently switchable; grouped closes need their own agreement gate `[A1]` | restore each flag independently; apply prior mapping generation |
| 12 | new writers required; old writer rollback intentionally closed | code rollback only to a v2-aware revision; migration downgrade restores nullability |

## Plan self-review record

- Spec §§1–4: Tasks 3, 5, 7, 9, and 10 implement source choice, venue pinning,
  last-trade/midpoint precedence, session behavior, US isolation, and honest
  fallback behavior.
- Spec §5: Tasks 1, 5, and 6 implement exact OpenFIGI→official-reference
  mapping, audited overrides, complete-generation semantics, and rollback.
- Spec §6: Task 1 is the binding provider-contract gate; Task 5 is forbidden
  from inventing upstream fields.
- Spec §7: Tasks 2, 3, 5, and 7 implement normalized provenance, shadow rows,
  split-adjustment provenance, quote/close source separation, correction
  journal, per-file atomicity, grouped-day state, and cursor safety.
- Spec §8: Task 8 implements the backfill (Massive grouped universe depth,
  Yahoo deep tail and `.DE` proxy `[A1]`), exact-ISIN Xetra proxy, one seam,
  native closes, priority, and sigma use without US contamination.
- Spec §9: Tasks 3 and 9 implement exact freshness/eligibility, fair active
  coverage, five-minute German and five-minute session-gated Finnhub US
  cadence (15-minute under the Yahoo fallback flag), and the daily
  grouped-close job; bounded daily-close retention is implemented in Task 8
  Step 8d and scheduled through Task 9; the post-close exception is durably
  claimed and the future deep-tail queue is bounded `[A1]``[A2]``[A3]`.
- Spec §10: Task 10 implements all API/interface provenance and compatibility.
- Spec §11: Tasks 2, 7, 9, and 11 implement bounded resource use, cached DB
  diagnostics, separate workers, and no secret logging.
- Spec §12: Tasks 2–12 implement expand/shadow/activate/rollback/contract stages
  and every numeric activation threshold.
- Spec §13: Every required mapping, parser, Yahoo, history, board, isolation,
  and absence-shaped test has a named task; Tasks 3, 4, 6, 7, 8, and 11
  require
  broken-variant proof where a false green is plausible (Task 8 carries the
  `[A3]` 1D stale-repeat teeth test).
- Spec §14 non-goals remain out: no paid API, FX, broker path, fuzzy mapping,
  Yahoo circumvention, dynamic venue hopping, midpoint scoring, or chatter/
  sentiment changes.
- Type/signature pass: `Quote` fields introduced in Task 3 match storage,
  collector, API, and TypeScript names; `HistorySeries` fields introduced in
  Task 8 match Task 10; generation/cursor/cycle/grouped-day/session-state
  model names match Tasks 6, 7, 8, 9, and 11.
- Empirical-field ruling: the only values not knowable while writing this plan
  are upstream paths legally hidden behind the terms gate. They are not left
  as implementation guesses: Task 1 creates an exact reviewed supplement and
  Task 5 consumes those literal values or stops.
- Amendment pass (2026-09-01, `[A1]``[A2]``[A3]`): Task 4b adds the dormant
  Massive grouped-close adapter; Task 8 gains the universe backfill mode,
  1D event-time slotting with a teeth test, and bounded daily-close
  retention; Task 9 gains the third close-source flag, the daily grouped
  job, five-minute session-gated Finnhub cadence, and matching scheduler
  assertions; Task 11 gains the non-vacuous full-backfill grouped agreement
  gate; Task 3 forbids `massive_grouped` from quotes and corrects Finnhub to
  live provenance. Yahoo history selects split-only `quote.close`, Task 8
  joins grouped rows through exact mapped provider identity, and the 1D chart
  deduplicates exact event observations rather than equal prices.
  Grouped symbol-mismatch normalization follows the capture-gate philosophy:
  added only from observed shadow-day logs, never guessed.
