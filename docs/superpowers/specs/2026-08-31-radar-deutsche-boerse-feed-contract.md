# Deutsche Börse delayed-data feed contract (captured)

**Captured:** 2026-09-01, 08:34–10:55 UTC, live Xetra/Tradegate session, by
the Task 1 capture gate of
`docs/superpowers/plans/2026-08-31-radar-market-data-v2.md`. Operator (Michi)
accepted the service's disclaimer in his own browser before any download.

**Method:** four current minute-files (one per MIC/channel, 08:34 UTC slice)
were downloaded and inspected with
`personal_apps/scripts/capture_deutsche_boerse_contract.py` (redacted
structural report; SHA-256s below). Value-level enumeration of enum-shaped
fields, timestamp formats, ordering, and ID cardinality ran locally and was
discarded; no licensed payload, price, ISIN, or ID enters Git. Supporting
observations used the two daily consolidated post-trade files and two
market-closed minute files.

Captured file SHA-256s (files themselves NOT committed):

| Input | File | SHA-256 |
|---|---|---|
| XGAT pre-trade | `DGAT-pretrade-2026-09-01T08_34.json.gz` | see `contract-report.json` in the session capture directory; recorded in ledger |
| XGAT post-trade | `DGAT-posttrade-2026-09-01T08_34.json.gz` | idem |
| XETR pre-trade | `DETR-pretrade-2026-09-01T08_34.json.gz` | idem |
| XETR post-trade | `DETR-posttrade-2026-09-01T08_34.json.gz` | idem |

## 1. Transport contract (observed)

- Entry pages (HTML shells, jQuery app): `https://mfs.deutsche-boerse.com/{DGAT|DETR}-{pretrade|posttrade}`.
- **File index API:** `GET https://mfs.deutsche-boerse.com/api/{DGAT|DETR}-{pretrade|posttrade}` returns JSON:
  `SrcText` (string, human venue/channel name), `DaysToKeepOnWebpage` (number, observed `1`),
  `GenerationDatetime` (string, `YYYY-MM-DD HH:MM:SS.mmm UTC`), `SourcePrefix`,
  `FileCount` (number, observed ~1,897), `CurrentFiles` (array of filename strings,
  newest first).
- **Download:** `GET https://mfs.deutsche-boerse.com/api/download/{filename}`
  responds `301 Moved Permanently` with a plain-text body and `Location` to a
  **signed Google Cloud Storage URL** on `https://storage.googleapis.com/`
  (bucket observed: `mv-cef-prod-europe-west3-private-min-by-min-files/{SRC}/...`)
  with **`X-Goog-Expires=2` (two seconds)**. The client MUST follow that one
  cross-origin redirect immediately; a stored redirect URL is dead on reuse.
- **Auth: none.** No login, cookie, or token is required for the index or the
  download. The site's terms disclaimer is a client-side jQuery dialog with no
  server-side acceptance state. The planned `RADAR_DBAG_DELAYED_COOKIE` is
  therefore unnecessary (ruling R3 below).
- **Filename grammar (exact):**
  - minute files: `{SRC}-{channel}-YYYY-MM-DDTHH_MM.json.gz` where
    `SRC ∈ {DGAT, DETR}`, `channel ∈ {pretrade, posttrade}`, time is the UTC
    minute the file covers (verified: the `T08_34` post-trade file's event
    times span exactly `08:34:00.0…–08:34:59.9 Z`).
  - daily files: `{SRC}-{channel}-daily-YYYY-MM-DD.json.gz` — one consolidated
    full-day file per channel, present for the previous trading day.
- **Cadence/retention:** one file per minute per channel; `DaysToKeepOnWebpage=1`
  ("available until midnight of the following business day" per the MDS page);
  ~1,897 files listed per channel at capture time.
- Minute files are **per-minute event deltas**, not snapshots. A 5-minute
  Radar cycle must fetch every unseen minute file since its cursor, in
  filename-time order.
- **Market-closed representation:** minute files outside trading hours exist
  and are valid gzip streams whose uncompressed payload is **0 bytes**
  (observed `02:00` UTC files, both channels).

## 2. Payload encoding

- gzip; decompressed content is **NDJSON** (one JSON object per line), NOT a
  single JSON document. UTF-8.
- One `messageId` per FILE (cardinality 1 across all rows of every inspected
  file, including a 376k-row daily) — it is a batch identity, not an event ID.
- Rows are ordered ascending by `publicationDateAndTime` (0 violations in
  376,164 rows).
- All timestamps: ISO-8601 UTC with `Z`, nanosecond precision, e.g.
  `2026-09-01T08:34:00.461254580Z`.

## 3. Field tables (exact observed JSON pointers, NDJSON row = `/*`)

### 3.1 XGAT post-trade (`DGAT-posttrade`)

| Semantic field | Pointer | Observed type | Notes |
|---|---|---|---|
| record | `/*` | dict | one executed trade |
| MIC | `/*/venueOfExecution` | string | values observed: `XGAT`, `XGRM` (sub-venue) |
| ISIN / stable ID | `/*/instrumentIdentificationCode` | string | ISIN format |
| local mnemonic | — | — | **absent** (ruling R6) |
| currency | `/*/priceCurrency` | string | `EUR` observed |
| security type | — | — | **absent** (ruling R6) |
| event ID | `/*/transactionIdentificationCode` | string | unique per file; 0 duplicates in 319,010-row daily |
| original-event ID | — | — | **absent** (ruling R4) |
| event action | `/*/mmtModificationInd` | string | only `-` observed, full day, both venues (ruling R4) |
| event timestamp | `/*/tradingDateAndTime` | string | execution time, UTC `Z` |
| publication timestamp | `/*/publicationDateAndTime` | string | ordering key |
| price | `/*/price` | number | |
| volume | `/*/quantity` | number | |
| official-close marker | — | — | **absent** on XGAT (ruling R5) |
| batch ID | `/*/messageId` | string | one per file |
| other observed | `/*/mmtAlgoInd` (`H`/`-`), `/*/mmtTradingMode` (`U`), `/*/priceNotation` (1, rarely 2), `/*/venueOfPublication` (`XCEF`), `/*/notionalAmount` (rare, number) | | recorded, unused |

### 3.2 XETR post-trade (`DETR-posttrade`)

Same pointers as 3.1, plus:

| Semantic field | Pointer | Observed type | Notes |
|---|---|---|---|
| official-close marker | `/*/lastTradeIndicator` | string, OPTIONAL | values observed: `R` (majority), `P`, `C`, `k`. **`C` rows cluster exclusively at 15:35–15:39 UTC (= 17:35–17:39 Berlin, the Xetra closing auction) across a full-day file — `C` is the observationally established closing-auction trade marker.** Other values' semantics are NOT guessed; only `C` is used, only as close evidence. |
| sub-venues | `/*/venueOfExecution` | string | observed: `XETA`, `XETB`, `XEMA`, `XETS`, `XEMI`, `XEMB`, `XETU` |
| extra MMT flags | `/*/mmtBenchmarkRefprcInd` (`-`/`S`), `/*/mmtPubModeDefReason` (`-`) | string | recorded, unused |
| trading system | `/*/tradingSystem` | string | `1` continuous, `3` observed with `P` rows |

### 3.3 XGAT pre-trade (`DGAT-pretrade`)

Flat top-of-book rows (~119,738/minute observed):

| Semantic field | Pointer | Observed type | Notes |
|---|---|---|---|
| MIC | `/*/venueOfExecution` | string | `XGAT`, `XGRM` |
| ISIN | `/*/instrumentIdentificationCode` | string | |
| currency | `/*/priceCurrency` | string | `EUR` dominant; `USD`, `GBP`, `AUD`, `CHF` observed — **non-EUR rows exist and must be filtered** |
| bid / ask | `/*/bid`, `/*/ask` | number | |
| bid/ask size | `/*/bidQty`, `/*/askQty` | number | |
| book event time | `/*/updateDateAndTime` | string | UTC `Z` |
| publication time | `/*/publicationDateAndTime` | string | |
| event ID | — | — | **absent** for book rows; book identity = `(ISIN, updateDateAndTime)` |
| phase | `/*/tradingSystemPhase` | string/number | numeric codes observed (`203` dominant); semantics not guessed |

### 3.4 XETR pre-trade (`DETR-pretrade`)

Mixed row shapes in one file (400,512 rows/minute observed; 20.3 MB
compressed, **200.6 MB uncompressed** — see R8):

- Depth rows (majority): `/*/mdBidMktDepthGroup1/*/price`,
  `/*/mdBidMktDepthGroup1/*/quantity`, `/*/mdAskMktDepthGroup1/*/price`,
  `/*/mdAskMktDepthGroup1/*/quantity`,
  `/*/aggregatedNumberOfOrdersAndQuotesBid/*/noOfOrders`,
  `/*/aggregatedNumberOfOrdersAndQuotesAsk/*/noOfOrders`,
  `/*/mdupdateDateAndTime`, `/*/retailFlag`.
- Top-of-book rows: `/*/bestBid`, `/*/bestBidQty`, `/*/bestAsk`,
  `/*/bestAskQty`, `/*/updateDateAndTime`.
- Shared: `/*/instrumentIdentificationCode`, `/*/priceCurrency`,
  `/*/messageId`; a subset carries `/*/publicationDateAndTime`,
  `/*/tradingSystem`, `/*/tradingSystemPhase`, `/*/venueOfExecution`,
  `/*/priceNotation`.
- Radar's midpoint selection needs only `bestBid`/`bestAsk` (+Qty) or the
  XGAT-style flat book; depth arrays are ignored.

## 4. Reference universe

The delayed service carries **no reference/instrument-master channel**: no
mnemonic, security name, or type anywhere in any inspected file. ISIN and
per-row sub-venue MIC are the only identity. See ruling R6.

## 5. Sizes and parse cost (measured)

| File | Compressed | Uncompressed | Parse time (Python json, streaming lines) |
|---|---|---|---|
| XGAT post minute | 12.6 KB | ~0.2 MB | negligible |
| XETR post minute | 24.8 KB | ~0.4 MB | negligible |
| XGAT pre minute | 3.2 MB | 42.2 MB | ~1 s |
| XETR pre minute | 20.3 MB | 200.6 MB | ~10 s scale (3.4 s for the 13.7 MB daily post file) |
| XGAT post daily | 10.7 MB | 319,010 rows | 2.9 s |
| XETR post daily | 13.7 MB | 376,164 rows | 3.4 s |

## 6. Binding rulings (deviations from plan assumptions; reviewer input)

- **R1 — NDJSON:** payloads are JSON Lines. Parser reads line-delimited
  objects; the capture tool already gained this branch with a pinned test.
- **R2 — Redirect transport:** `api/download` 301s to a ~2-second signed
  `storage.googleapis.com` URL. Task 5's "reject redirects to another origin"
  rule is amended to: follow EXACTLY ONE redirect, only to
  `https://storage.googleapis.com/`, and only when issued by
  `mfs.deutsche-boerse.com`; any second redirect or other host is rejected.
- **R3 — No cookie:** access is public; terms acceptance is a client-side
  dialog the operator accepted. `RADAR_DBAG_DELAYED_COOKIE` is dropped;
  the configured switch for German collection remains the mode flag alone.
  (Operator re-confirms terms if DBAG ever adds server-side acceptance.)
- **R4 — Corrections not observed:** `mmtModificationInd` exists but only
  `-` was observed across two full-day files (695k rows) and all minute
  files. No correction/cancellation representation can be implemented from
  observation. The parser treats any non-`-` value as a rejected row with a
  counted reason (`unobserved_modification`), never as a guessed amend/cancel.
  The plan's correction-journal machinery (original-event links, revocation)
  reduces to this rejection rule; `RadarMarketTradeEvent.action` stores `new`
  only, and the 48-hour journal retention serves close reconciliation, not
  corrections.
- **R5 — Official close:** XETR: `lastTradeIndicator == 'C'` is the
  closing-auction marker (observational evidence above); use it for
  `is_official_close`. XGAT: no marker exists; the native close is the final
  valid executed trade of the session (the spec's designed fallback).
- **R6 — Reference data absent:** mnemonic/type/completeness cannot come from
  the delayed files. `FeedBatch.reference_complete` is always `False` for this
  source, and the mapping's official reference universes (Task 6) must come
  from the separate official instrument files (Xetra "Tradable Instruments"
  download; Tradegate BSX instrument list), which are fetched and hashed as
  their own `ReferenceCatalog` inputs. Absence of references in the delayed
  feed can never mark a mapping unavailable.
- **R7 — Sub-venue MICs:** rows carry execution MICs finer than the channel
  (`XGRM` under DGAT; `XETA/XETB/XEMA/XETS/XEMI/XEMB/XETU` under DETR). The
  channel's file determines the Radar market identity (`XGAT`/`XETR`); the
  row-level MIC is stored as provenance and any row whose sub-venue is not in
  the observed per-channel set is rejected and counted.
- **R8 — XETR pre-trade cost:** 20 MB compressed / 200 MB uncompressed per
  minute is far above the plan's default caps if fetched per minute. Radar
  needs XETR books only for XETR-fallback instruments without fresh trades.
  Ruling: the collector fetches XGAT pre+post and XETR post every cycle, and
  XETR pre-trade AT MOST once per cycle only when at least one mapped
  XETR-primary active instrument lacks a fresh trade — and parses it
  streaming with the existing decompression caps raised for this single
  channel to 30 MiB compressed / 300 MiB uncompressed. This stays inside the
  resource gate and is measured by the shadow report.
- **R9 — Empty files:** a 0-byte uncompressed gzip is a VALID market-closed
  file: the cycle records `no_data` for it and advances the cursor; it is not
  a parse error.
- **R10 — Multi-currency book rows:** non-EUR pre-trade rows exist on XGAT;
  currency filtering (EUR only) is mandatory before midpoint selection.
- **R11 — Daily consolidated files:** `{SRC}-{channel}-daily-YYYY-MM-DD`
  files exist for the prior trading day and are the natural input for the
  post-close native-close reconciliation (§8.3 of the design) and for
  catch-up after daemon downtime within retention.

## 7. Sanitized fixtures

`personal_apps/tests/fixtures/radar_market_data/{xgat,xetr}_{pretrade,posttrade}.json`
reproduce the exact observed keys and nesting with fake identifiers
(`DE000ZZTEST01/02`), fake prices, and fixed UTC timestamps; the XETR
post-trade fixture includes one `lastTradeIndicator: "C"` closing-auction row
and the XETR pre-trade fixture includes one depth row and one top-of-book
row. A parity test asserts every pointer this supplement names resolves in
the matching fixture. Fixtures are stored as JSON arrays of row objects (the
parser consumes rows; NDJSON framing is covered by transport tests).

## 8. Ruling

```text
PASS — stable identity, provider event time, and sufficient trade/book data
were observed for both XGAT and XETR; Tasks 2–12 may proceed.
```

Grounds: stable per-instrument identity (ISIN) and per-trade identity
(`transactionIdentificationCode`) exist; provider event time
(`tradingDateAndTime` / `updateDateAndTime`, UTC, ns) exists; executed
trades with price/volume and two-sided books with sizes exist for both MICs;
an official-close marker exists for XETR and a deterministic fallback exists
for XGAT; ordering, retention, market-closed, and empty-file behavior are
all observed. The truth rules of design §3 are implementable. Rulings R1–R11
adapt the plan where its assumptions differed from observation and are part
of this gate's review scope.
