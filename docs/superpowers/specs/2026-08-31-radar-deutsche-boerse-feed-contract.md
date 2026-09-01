# Deutsche Börse delayed-data feed contract (captured)

**Captured:** 2026-09-01, 08:34–10:55 UTC, live Xetra/Tradegate session, by
the Task 1 capture gate of
`docs/superpowers/plans/2026-08-31-radar-market-data-v2.md`. Operator (Michi)
accepted the service's disclaimer in his own browser before any download.

**Method:** four current minute-files (one per MIC/channel, 08:34 UTC slice)
were downloaded and inspected with
`personal_apps/scripts/capture_deutsche_boerse_contract.py` (redacted
structural report; SHA-256s below). The tool itself emits the aggregate,
value-free statistics behind this document's quantitative claims —
per-path value cardinality (duplicates = total − distinct), timestamp
ordering-violation counts, and short-enum time profiles (flag vocabularies
with ≤12 distinct short uppercase values, each with count and first/last
HH:MM) — so every such claim is re-derivable by re-running the tool on a
fresh download; nothing rests on a discarded local analysis. No licensed
payload, price, ISIN, or ID enters Git or the report. Supporting
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
| trading system | `/*/tradingSystem` | string | `7` observed on every XGAT row |
| other observed | `/*/mmtAlgoInd` (`H`/`-`), `/*/mmtTradingMode` (`U`), `/*/priceNotation` (1, rarely 2), `/*/venueOfPublication` (`XCEF`), `/*/notionalAmount` (rare, number) | | recorded, unused |

### 3.2 XETR post-trade (`DETR-posttrade`)

Same pointers as 3.1 (except `/*/notionalAmount`, not observed on XETR),
plus:

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
| trading system | `/*/tradingSystem` | string | `7` on every row |
| price notation | `/*/priceNotation` | number | `1` observed |
| batch ID | `/*/messageId` | string | one per file |

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

### 3.5 Official DBAG venue instrument files (reference capture, 2026-09-01)

**Captured:** 2026-09-01 ~14:05 UTC, by the R6 reference gate. Both files are
public downloads with no auth, no cookie, and no click-through terms; the
Xetra downloads page carries only DBAG's standard accuracy/liability
disclaimer.

| Source | Exact URL | Rows | SHA-256 at capture |
|---|---|---|---|
| Xetra (XETR) all tradable instruments | `https://www.cashmarket.deutsche-boerse.com/resource/blob/1528/025198b8d1f317b79e6724dd6b5f87b6/data/t7-xetr-allTradableInstruments.csv` | 5,106 | `969b4b931a35004d603cd489a9998f3c0d4eb9672b4b2c0e55cdb1d5049639e1` |
| Börse Frankfurt (XFRA "BF") all tradable instruments | `https://www.cashmarket.deutsche-boerse.com/resource/blob/2289108/926cf6a36dbbd65465d592c48ef30d19/data/t7-xfra-BF-allTradableInstruments.csv` | 56,275 | `63472e318e9ecd3e725b976ce05c6cf91fdc43d550077573d5f095132c07f36b` |

**File grammar (identical in both files, verified byte-equal headers):**

- Line 1: `Market:;XETR` (resp. `XFRA`) — MUST match the expected venue.
- Line 2: `Date Last Update:;DD.MM.YYYY` — file generation date (both files
  dated 01.09.2026 at capture; the download pages state daily updates).
- Line 3: semicolon-separated header, **153 columns**. Columns are addressed
  BY NAME (never by index) — the consumed set is exactly the eight columns
  below; a rename of ANY of them is a structural violation. Rows are
  filtered on read: a row whose `MIC Code` differs from the file's venue,
  or whose `Product Status`/`Instrument Status` is not `Active`, never
  enters a catalog (a dying trading line must not validate a mapping).

| Semantic field | Column name | Observed values / notes |
|---|---|---|
| instrument name | `Instrument` | free text |
| ISIN | `ISIN` | 12-char ISIN, never empty (0 empties in both files) |
| local mnemonic | `Mnemonic` | unique among CS+ETF rows within each file (0 duplicates); 1 empty row (an XETR `SR`) |
| venue MIC | `MIC Code` | constant `XETR` / `XFRA` per file |
| security type | `Instrument Type` | XETR: `CS` 1420, `ETF` 3093, `ETN` 387, `ETC` 205, `SR` 1. XFRA: `BOND` 35879, `CS` 14605, `ETF` 2921, `FUN` 2270, `ETN` 364, `ETC` 200, `WAR` 31, `OTHER` 4, `SR` 1 |
| trading currency | `Currency` | ALL `CS` rows are `EUR` in both files; ETFs also trade USD/GBP/CHF/JPY/SEK/AUD lines |
| product status | `Product Status` | `Active` only observed |
| instrument status | `Instrument Status` | XETR: `Active` 5100, `Inactive` 5, `PendingDeletion` 1 |

- Type normalization to the OpenFIGI vocabulary (`is_supported_type`):
  `CS` → `common stock`, `ETF` → `etf`; every other value is carried as
  `dbag:<lowercased value>` — the namespace prefix guarantees BY
  CONSTRUCTION that no future DBAG type value (e.g. a hypothetical `ETP`)
  can collide with a supported OpenFIGI type and silently widen the
  mapping.
- US coverage evidence: XFRA-BF carries **4,077 US-ISIN `CS` rows** (e.g.
  `US0378331005` → `APC`, `US69608A1088` → `PTX`, `US88160R1014` → `TL0`);
  XETR alone carries almost none of the smaller US names, which is why the
  Frankfurt file is REQUIRED (ruling R12).
- Cross-file consistency: 4,290 shared CS/ETF ISINs; the only (mnemonic,
  type) disagreements are 118 ETF ISINs with **multiple Xetra trading
  lines** (multi-currency lines of one share class; XFRA has zero
  multi-row ISINs). Ruling R13 excludes ISIN-ambiguous rows from the
  ISIN-keyed enrichment join; the per-venue symbol-keyed catalogs are
  unaffected (mnemonics stay unique).

### 3.6 Tradegate BSX instrument universe (reference capture, 2026-09-01)

**Source authority:** `www.tradegatebsx.com` is the official site of the
Tradegate Berlin Stock Exchange ("Tradegate BSX"), an institution of public
law operated by Tradegate Exchange GmbH, Kronprinzendamm 21, 10711 Berlin,
supervised by the Berlin Senate exchange oversight (site imprint, read
2026-09-01). This is the venue the delayed feed labels `DGAT`/`XGAT`.

**No bulk instrument file exists.** The official universe is the site's A–Z
price list ("indizes.php"), crawled as 27 pages:

- URL grammar: `https://www.tradegatebsx.com/indizes.php?lang=en&buchstabe={L}`
  with `L ∈ {0-9, A..Z}` (27 pages).
- Row grammar (exact, observed): inside `<tbody id="kursliste_abc">`, one
  anchor per instrument:
  `<a id="name_N" href="orderbuch.php?lang=en&amp;isin={ISIN}" class="hyphens">{Name}</a>`.
  The ISIN in the `href` is the instrument identity; the anchor text is the
  display name.
- Captured universe: **6,485 unique ISINs** across all 27 pages (page counts
  7–682, no empty page); concatenated raw pages SHA-256
  `d3cfa341399a1b90f728b3c60a2d82866fc3a089c857a1f6242c824355ac121e`,
  parsed `(ISIN, name)` list SHA-256
  `594879b1141333d794dec9fbf834d7f31b8b560a13cad12235aefd04773e7c09`.
- The index pages publish **no mnemonic, no security type, no currency** per
  row. Per-instrument detail pages (`orderbuch.php?isin=…`) do show a
  mnemonic (verified: `US0378331005` → `APC`, currency EUR), but crawling
  6.5k detail pages per refresh is not acceptable; ruling R13 derives those
  fields via the §3.5 files instead.
- Asset-class observation: joining all 6,485 ISINs against §3.5 resolves
  6,419 (**6,418 `CS` + 1 `SR`, zero ETFs, zero conflicts**) — the A–Z list
  is an **equities universe** (ruling R14). 66 ISINs (~1%) resolve to no
  §3.5 row (foreign small-caps and a few ex-Frankfurt listings, e.g.
  `BMG667211046` Norwegian Cruise Line) and are conservatively unmappable
  (ruling R13).
- Currency: the site states "Prices in Euro; foreign currency bonds in the
  respective currency"; the equity detail page observed shows EUR. XGAT
  catalog rows therefore carry `EUR` (ruling R15), which the R10 EUR filter
  and the mapping's `currency_mismatch` refusal both re-check downstream.

## 4. Reference universe

The delayed service carries **no reference/instrument-master channel**: no
mnemonic, security name, or type anywhere in any inspected file. ISIN and
per-row sub-venue MIC are the only identity. See ruling R6. The R6
precondition is now satisfied by §3.5/§3.6 and rulings R12–R15.

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
  rule is amended to: follow EXACTLY ONE redirect, only when issued by
  `mfs.deutsche-boerse.com`, only to
  `https://storage.googleapis.com/mv-cef-prod-europe-west3-private-min-by-min-files/`
  (the exact bucket observed for BOTH minute files and, under its `daily/`
  subpath, the daily consolidated files); any second redirect, other host, or
  other bucket prefix is rejected.
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
  Evidence base is one trading day; the German shadow phase (Tasks 7/11)
  must reconfirm the `C` clustering across its full-session days before
  activation makes this fully load-bearing, and the enum-time-profile
  statistics the capture tool now emits make that reconfirmation a rerun,
  not a new analysis.
- **R6 — Reference data absent:** mnemonic/type/completeness cannot come from
  the delayed files. `FeedBatch.reference_complete` is always `False` for this
  source, and absence of references in the delayed feed can never mark a
  mapping unavailable. The mapping's official reference universes (Task 6)
  must come from separate official instrument sources (candidates: the Xetra
  "Tradable Instruments" download; a Tradegate BSX instrument list) — but
  NEITHER candidate was captured by this gate: URL, shape, terms, and
  completeness semantics are all unobserved. **Binding precondition:** before
  Task 6 consumes any `ReferenceCatalog`, each reference source passes its own
  capture-and-freeze (same discipline as this supplement: exact URL, field
  pointers, completeness proof, sanitized fixture) appended here as §3.5/§3.6
  and reviewed. Until then, reference-source names in the plan are candidates,
  not contracts.
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
- **R12 — Frankfurt file joins the reference set:** the plan named only the
  Xetra Tradable Instruments file, but Xetra lists just 1,420 common stocks
  and misses most US names the board tracks. The Börse Frankfurt "BF" file
  (same grammar, §3.5) carries 14,605 CS rows incl. 4,077 US ISINs and is
  the mnemonic authority for non-Xetra names. Both §3.5 files together form
  the German symbol→ISIN reference; German mnemonics ("Börsenkürzel") are
  market-wide, not per-venue, so a Frankfurt mnemonic is valid for the same
  ISIN on Tradegate — this market convention is the join's premise and its
  correctness is re-verified empirically by the shadow report's mapping
  and identity gates before anything activates.
- **R13 — XGAT rows are derived, conservatively:** Tradegate publishes no
  bulk mnemonic/type/currency. An XGAT `VenueReferenceRow` exists ONLY for
  a crawled Tradegate ISIN that resolves via §3.5 to exactly one
  (mnemonic, normalized type) pair; ISINs resolving to zero rows or to
  conflicting pairs are EXCLUDED, so the mapping can only refuse them
  (`official_reference_missing`), never mis-map them. At capture this
  excludes 66 of 6,485 (~1%). The same refusal-over-guessing rule governs
  SYMBOL collisions in every built catalog (spec §5.2 step 5): the
  mapping's reference lookup is keyed by symbol, so when two rows hold
  the same symbol — e.g. two different Tradegate ISINs enriched to one
  mnemonic across the two §3.5 files — ALL rows of that symbol are
  dropped and those instruments can only refuse.
- **R14 — Tradegate A–Z is equities-only:** zero ETFs resolved. ETF tickers
  therefore can never map to XGAT under this reference; they fall through
  to XETR (whose catalog does carry ETFs) or refuse. Consistent with EU
  retail reality (US ETFs are not PRIIPs-tradable) and accepted.
- **R15 — XGAT currency:** `EUR`, from the venue's own pricing statement
  plus the observed detail page. The real downstream re-check is the R10
  EUR row filter on feed data (the mapping's `currency_mismatch` refusal
  compares this constant to itself for XGAT and only bites for XETR).
- **R16 — Reference completeness semantics:** a DBAG file is complete iff
  its `Market:` line matches the expected venue, its `Date Last Update:`
  parses and is at most 7 days old, every consumed column resolves by
  name, and the USABLE catalog row count — after status/MIC filtering,
  empty-mnemonic and collision exclusions — is at least roughly half the
  captured baseline (floors: 2,500 XETR catalog rows of 5,100 observed;
  25,000 XFRA enrichment rows of 56,275 observed — pinned as constants
  in code). The Tradegate
  crawl is complete iff all 27 pages fetch with at least one parsed row on
  every lettered page and the RESOLVED post-join row total (after R13's
  exclusions, of 6,419 observed) is at least 3,000 — deliberately stricter
  than a raw-ISIN floor: an enrichment collapse also refuses.
  Anything less makes the affected `ReferenceCatalog.complete = False`,
  which `decide_mapping` turns into `IncompleteReference` — the build
  writes nothing rather than marking tickers unavailable (spec §5.4).

## 7. Sanitized fixtures

`personal_apps/tests/fixtures/radar_market_data/{xgat,xetr}_{pretrade,posttrade}.json`
reproduce the exact observed keys and nesting with fake identifiers
(`DE000ZZTST01/02`), fake prices, and fixed UTC timestamps; the XETR
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
