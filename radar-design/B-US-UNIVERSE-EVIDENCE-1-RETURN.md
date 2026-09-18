# B-US-UNIVERSE-EVIDENCE-1 — Researcher return

Date: 2026-09-17 · Role: Researcher (Claude Opus 5, no subagents) · Status: **REPOSITORY PORTION COMPLETE; EXACT COHORT ROWS BLOCKED ON AUTHORIZATION**

## 0. Result in one paragraph

The recorded totals reconcile exactly: 12,599 − 87 + 146 = 12,658 incoming rows, and 12,599 + 146 = 12,745 active identities, of which 12,599 are mapped. The exact 146/51/87 symbol rows could **not** be rebuilt, though. They exist only in retained files on the production host and in the production database, and this dispatch authorized neither. No file in this worktree names a single cohort symbol. Everything that could be done from the repository is done:

- a full trace of how identities and mappings are written and read;
- twelve findings, three of them high severity;
- a proposed mapping contract, with a table of how each finding changes it;
- a failure-safe daily-maintenance design;
- a schema assessment and a test matrix;
- a tested offline tool (`reconstruct_cohorts.py`) that produces and classifies the exact cohort tables once the owner authorizes a read-only copy of the retained files;
- the exact query text for current-state capture (`current_state_select.sql`), which was **not executed**.

The most important finding: **after release A, nothing in the codebase writes a US `RadarInstrument` row.** The only US rows ever written came from the one-time backfill in migration `a4c8e2f19b70`. So every identity added after that migration stays unmapped until a writer exists.

## 1. Git continuity (verified at start)

| Item | Observed |
|---|---|
| Workspace | `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts` (`git rev-parse --show-toplevel`) |
| Branch | `codex/radar-selected-price-charts` |
| HEAD / origin/main / feature ref | `0fdad7327292cd3cd0b62dbe3f6b460873263053` (all three) |
| Index | empty |
| Tracked dirt (pre-existing, Mastermind-owned) | 9 modified: `HANDOFF.md`, `radar-design/{A-US-USD-ONLY-LEDGER,ASSIGNMENTS,HANDOFF,MARKET-DATA-ROADMAP,MASTERMIND-STATE,MD-SELECTED-PRICE-LEDGER,ROADMAP,WORKFLOW}.md` |
| Untracked (pre-existing) | 370 paths: 12 radar-design documents (incl. the B brief/ledger/prompt and the refresh record), 1 docs spec review, 357 files under `radar-design/artifacts/` (a-us-usd-only-*, encoder audit, md-selected-price-*) |
| Added by this assignment (untracked) | this return and `radar-design/artifacts/b-us-universe-evidence-1/` (5 files) |

None of the pre-existing dirt was modified. Nothing was staged or committed. I did not update the B ledger, the handoffs or the other state files, because the Mastermind owns them.

## 2. Authorization check

The dispatch is the assignment prompt itself. It **does not explicitly authorize** any conditional category, so none was used.

| Category | Authorized? | Used? |
|---|---|---|
| Repository/Git reads, worktree artifacts, local offline analysis | yes | yes |
| Retained production-host evidence (`/root/radar-universe-refresh-20260916/*`) | **no** | no |
| Bounded `SELECT`-only queries | **no** | no — query text prepared, not run |
| Fresh official Nasdaq Trader directory reads | **no** | no |
| Retained evidence outside this worktree (brief §4), e.g. untracked `personal_apps/nasdaqlisted.txt` / `otherlisted.txt` in the main checkout (vintage unknown, not read) | **no** | no |
| Subagents | not authorized | none |

I did no external web research either. The exchange-code meanings and ISO MIC facts below come from repository code (migration `a4c8e2f19b70`, `prices/yahoo.py`). Background knowledge is labeled as such and listed as a verification carry.

## 3. Source inventory

**Required reads, read completely:**
- root `HANDOFF.md`;
- `radar-design/` documents: `B-US-UNIVERSE-BRIEF.md`, `B-US-UNIVERSE-LEDGER.md`, `US-UNIVERSE-REFRESH-2026-09-16.md`, `A-US-USD-ONLY-RELEASE-CLOSURE.md`, `A-US-USD-ONLY-LEDGER.md`, `WORKFLOW.md`, `HANDOFF.md`, `ASSIGNMENTS.md`, `MASTERMIND-STATE.md`, and `B-US-UNIVERSE-EVIDENCE-1-PROMPT.md`.

**Supporting documents:** `US-USD-ONLY-DECISION.md` (the pre-import count of 12,599 active / 12,599 mapped), the A research/review/deploy returns (confirming no US writer remains), and the fingerprint summaries in `artifacts/a-us-usd-only-release/host/archive-fp/`.

**Retained refresh tooling, the only B-specific evidence in the worktree:**
- `artifacts/md-selected-price-personal-preview/universe_refresh_preflight.py`. It defines the host evidence: `universe-before.json` holds all universe rows; `preflight.json` holds counts, a 30-symbol `add_sample`, the `revived` list and file hashes. It computed "added", "changed" and "absent" over **all** rows. It hashed the **network body**, then wrote a BOM-stripped decoded copy (lines 8–13).
- `artifacts/md-selected-price-personal-preview/count_market_coverage.py` — the active/mapped coverage query, which filters on `delisted_at IS NULL`.

**Code and schema traced:**

| Concern | Path:line |
|---|---|
| Directory parser | `personal_apps/scripts/seed_radar_universe.py:30-35` (column aliases), `:46-82` (`load_rows`: footer skip, Test Issue skip, `isalpha() and len<=5`, ETF Y/N), `:90-104` (first file wins, single `upsert_symbols`) |
| Identity upsert | `personal_apps/features/radar/universe.py:78-121` (added/updated/reassigned/flagged; `updated` = name or exchange differs), `:63-75` (`_is_reassignment` requires `delisted_at`), `:124-136` (`mark_delisted`, with no production caller — only `tests/test_radar_universe.py:69,112`) |
| Identity model | `personal_apps/models.py:497-543` (`radar_ticker_universe`) |
| Mapping model | `personal_apps/models.py:546-597` (`radar_instruments`: `uq_radar_instrument (ticker, market, mic)` at `:556-557`; **non-unique** `ix_radar_instrument_primary` at `:560-561`; free-text `mapping_status` at `:579`; `mapping_generation_id`, documented as DE-only, at `:582-588`; `history_due_at` at `:597`) |
| Only US mapping writer ever | `personal_apps/migrations/versions/a4c8e2f19b70_add_radar_market_instruments.py:23-51` (MIC/VENUE/MAPPED tables), `:140-148` (one-time `INSERT … FROM radar_ticker_universe WHERE delisted_at IS NULL`, `mapping_source='nasdaq-directory'`, `mapped_at=CURRENT_TIMESTAMP`) |
| Later schema | `6a21d4e8c9f0_add_radar_market_data_v2.py:188-192` (generation FK), `e5f8b2ca4d36_add_instrument_history_due.py:20-25`; head `b7e3f9c1a2d4` |
| Removed mapping writers | Release A app commit `c851220` deleted `features/radar/instruments.py` (738 lines) and `reference_universe.py` (330). Both wrote only DE rows or generations. `git show 38591e0:…instruments.py` shows US rows being read only (`_active_us_instruments`) |
| Price storage keys include MIC | `models.py:887-888` (`uq_radar_quote_market`), `:960-961` (`uq_radar_daily_close_market`) |
| Mapping readers (all require `market='us'`, `is_primary`, `mapping_status='mapped'`) | `features/radar/quotes.py:127-134`; `run_radar_ingest.py:356-363` (`_market_instruments`, used by the US quote cycle at `:458`, by history at `:633` and by the Yahoo tail at `:695`); `features/radar/market_data.py:48-80` (grouped-close identity map; ambiguous provider symbols dropped silently); `features/radar/analysis.py:75-81,300-318` (HA1 eligibility: ≤2 candidates, USD, MIC/venue/provider present, `mapped_at ≤ read_start`); `features/radar/price_chart_reader.py:214-255` (selected-price identity → 422 `unsupported_instrument`); `scripts/backfill_radar_market_history.py:30-40` |
| Stored-row readers keyed by MIC | `features/radar/quotes.py:153-176`; `price_chart_reader.py:68-82`; `analysis.py:91-100`; `history.py:230-296` (sibling basis needs non-null ISIN, which US rows lack) |
| Legacy fallback for unmapped tickers | `run_radar_ingest.py:458-465` → `features/radar/prices/__init__.py:81-86` (`Quote` defaults `mic='XNAS'`, `venue='US'`) → `quotes.py:31-56` |
| Provider symbol forms | `features/radar/price_chart_contract.py:102-103` (`_PLAIN_SYMBOL`, `_CLASS_SHARE`), `:328-364` (`yahoo_symbol`, `alpaca_symbol`, `provider_symbol_supported`); `analysis_contract.py:48` (`TICKER`) |
| MIC-based identity validation | `features/radar/prices/yahoo.py:40-53` (`_EXCHANGE_ALLOWLIST`, keyed to exactly the migration's MICs plus XNAS); `prices/__init__.py:151-173` (provider MIC must equal instrument MIC) |
| Grouped-close acceptance | `market_data.py:157-158` (floors of 5,000 rows and 95% coverage), `:83-139`, `:237-280` |
| Scheduler | `run_radar_ingest.py:987-1066` (job set; no universe/directory job); `:612-617` (profiles job updates market data only) |
| Archival fingerprint scope | `artifacts/a-us-usd-only-release/host/archive-fp-0fdad73.py:15-22` (`radar_instruments`/quotes/closes only where `market='de' OR currency='EUR'`; generations only where `market='de'`) |
| Tests | `tests/test_radar_universe.py` (upsert, reassignment, lookup, segments; **no parser/`load_rows` test anywhere**); `tests/test_radar_migration.py:290-315` (backfill → AAPL XNGS, unknown → XXXX/unverified); `tests/ha1_unit/test_analysis_reader.py:127,183` (ineligible status/primary cases); `tests/selected_price_unit/helpers.py:23-31`; `tests/radar_disposable.py` (destructive-target registry guard) |

**Unavailable:**
- the four host files;
- any production row;
- current directory contents;
- the Nasdaq Trader definitions page and the ISO 10383 registry (not fetched).

## 4. Counts reconciliation

**Historical (2026-09-16 import, as recorded in `US-UNIVERSE-REFRESH-2026-09-16.md`, not re-measured):** files created `0915202618:01`; 5,600 + 7,058 usable rows = 12,658 unique incoming; importer output 146 added, 51 updated, 0 reassigned, 0 flags set; 87 existing rows absent; 12,745 active after; 12,599 mapped.

**Arithmetic, every step consistent:**

| Quantity | Value | Basis |
|---|---|---|
| Matched existing | 12,658 − 146 = **12,512** | recorded |
| Rows before the import | 12,512 + 87 = **12,599** | derived |
| Pre-import active (same day, `US-USD-ONLY-DECISION.md`) | 12,599, all mapped | measured by Mastermind |
| ⇒ Delisted rows before | **0**, so revived = 0 | derived |
| Active after | 12,599 + 146 = **12,745** | matches the recorded figure |
| Unmapped after | 12,745 − 12,599 = **146** = added | matches the recorded figure |
| Changed | 51 of the 12,512 matched | recorded |
| Mapped after | 12,599 = 12,512 matched (incl. the 51) + 87 absent | derived |

**Discrepancies:** none in the totals. **Qualifications:**
- `before_rows` and "0 delisted" are derived, not recorded.
- The recorded SHA-256 values are of the network body. The retained files are decoded copies (preflight lines 10–11), so they match byte-for-byte only if Nasdaq sent no BOM. The tool reports `exact`, `matches_after_restoring_stripped_bom` or `mismatch`.
- `preflight.json` keeps only 30 added symbols. The full lists must be recomputed.

**Current state (2026-09-17): NOT MEASURED (not authorized).** Repository evidence predicts no identity or mapping drift since the import:
- no importer run is recorded;
- no US writer exists at `0fdad73`;
- release A's fingerprints cover only DE/EUR rows, and A wrote no US instrument row;
- the profiles job changes only `market_cap` and `ipo_date` (`universe.py:300-337`).

One kind of drift is plausible: legacy quote rows under MIC `XNAS` for unmapped cohort symbols (F2). Query Q5 measures this.

## 5. Cohort tables

**Status: BLOCKED — no rows** (`artifacts/b-us-universe-evidence-1/cohort-status.json`, `"rows": null`). No classification of a real symbol is claimed.

**Tables ready to produce once authorized.** `reconstruct_cohorts.py` writes three files, plus `cohorts.json` and `reconciliation.json`:
- `cohort-146-added-unmapped.csv`
- `cohort-51-changed.csv`
- `cohort-87-absent.csv`

Its column contract and vocabularies are in `cohort-schema.json`:
- stable identity key;
- directory name, exchange field and code, ETF flag, financial status, CQS and NASDAQ symbols;
- the before row;
- proposed market, MIC, venue, provider symbol and currency;
- security-type hint;
- name and exchange change kinds;
- cross-cohort pairs;
- current mapping state and MIC drift;
- conflicts, classification, disposition, and the evidence source with a file-hash prefix.

**How the tool guarantees parity:**
- It **executes the importer's own `load_rows`/`_first`**, `universe._significant`/`_issuer_of`, and the migration's MIC/VENUE tables, reading them from repository source via AST without importing the app.
- It checks every recorded count and every derived identity. It exits 3, still writing the tables, if any check fails to reproduce.
- It refuses to overwrite existing output and never touches its inputs.

**Classification rules (deterministic and conservative):**

- **146 added (unmapped):**
  - known code, ETF flag present, common or fund, no pair, no conflict → `SAFE_AUTO_MAP_CANDIDATE`;
  - Nasdaq five-letter W/R/U corroborated by the name, or preferred/note by name → `NON_COMMON_LISTING` (owner decision D3);
  - derivative word without corroboration (e.g. "Limited Partnership Units") → `SECURITY_TYPE_UNCLEAR`;
  - shares an issuer key with an absent row → `POSSIBLE_TICKER_CHANGE`. Funds pair only on the full key, so new iShares/ProShares funds don't pair with every closed fund from the same sponsor;
  - code outside the eight → `VENUE_UNKNOWN`;
  - current state shows a US row, an inactive symbol or a taken provider symbol → `EXISTING_MAPPING_CONFLICT`.
- **51 changed:**
  - first significant token changed (the importer's own reassignment test, minus its unreachable `delisted_at` precondition) → `POSSIBLE_REASSIGNMENT`;
  - cross-exchange move → `VENUE_TRANSFER`;
  - Q/G/S move → `NASDAQ_TIER_DRIFT` (stored MIC now names the wrong Nasdaq segment);
  - cosmetic or security-description-only name change → `IDENTITY_METADATA_ONLY`;
  - same first token → `RENAME_LIKELY`.
- **87 absent:** a pair with an added row → `POSSIBLE_TICKER_CHANGE`; corroborated warrant/right/unit → `ABSENT_DERIVATIVE_LIKELY_EXPIRED`; everything else → `ABSENT_UNEXPLAINED`. **Every absent row gets a no-delist, no-mapping-change disposition.**

**Safe automation versus review:**
- Only `SAFE_AUTO_MAP_CANDIDATE` is eligible for automation (the insert-only mapper), and only after an apply-time recheck.
- Everything else goes to hold, manual review or an owner decision.
- No existing row is rewritten automatically.

**Expected families.** These are hypotheses from how the parser works, not facts; the real mix is unknown until the rows exist.
- The 146 probably include new fund launches and IPOs (candidates for `SAFE`) and Nasdaq SPAC components with W/R/U suffixes (`NON_COMMON`). NYSE-family components cannot appear, because their symbols are not plain letters.
- The 51 probably include Nasdaq tier moves and wording changes in security descriptions.
- The 87 probably include closed funds, completed mergers or ticker changes, and expired SPAC warrants or rights.

**Verification.** The synthetic self-test (`selftest_reconstruct.py`, clearly synthetic data) passed. Command: `py -3.12 radar-design/artifacts/b-us-universe-evidence-1/selftest_reconstruct.py . <scratch>` → `SELFTEST PASS`, exit 0. It covers:
- all 18 fixture rows classified as expected, including a Nasdaq tier drift with `mic_drift=true`, `mapped_while_absent`, legacy-fallback surfacing, adoption of the current id, and no false ETF-sponsor pairing;
- a run with the real recorded expectations against synthetic files exits 3, and no row claims current state;
- an existing output directory exits 2;
- inputs are byte-identical afterwards.

The self-test passing does **not** show the real cohorts are correct.

## 6. Repository findings

Ranked by severity. Each cites the code it rests on.

- **F1 (High) — No US mapping writer exists.** US rows came only from migration `a4c8e2f19b70:140-148`. The importer writes identities only (`seed_radar_universe.py:103-104`, `universe.py:78-121`). Release A removed the DE-only writers (`c851220`).
  - **Consequence for every identity added after 2026-08-28:** no quote poll in mixed batches (`run_radar_ingest.py:356-363,458`), no grouped close (`market_data.py:48-80`), no history (`:620-640`), HA1 returns 422 (`analysis.py:300-318`), and the selected-price chart returns 422 `unsupported_instrument` (`price_chart_reader.py:229-234`).
  - Extraction still matches these identities (`universe.load_lookup`, `:227-238`), so they are discussed and ranked without prices.
- **F2 (High) — Unmapped tickers can get quote rows under a made-up MIC.**
  - **Mechanism:** when a due batch contains no mapped ticker, the US quote cycle calls `provider.quotes(due)` and stores the result (`run_radar_ingest.py:458-465`). The provider's `Quote` defaults to `mic='XNAS'`, `venue='US'` (`prices/__init__.py:81-86`). For an NYSE listing that is a wrong venue. After a real mapping (e.g. XNYS or XNCM) is written, readers filter on the mapped MIC or on legacy `(NULL, NULL)` only (`quotes.py:153-176`), so those rows become invisible orphans.
  - **Extent:** unknown (Q5).
  - **Mixed batches:** unmapped tickers are skipped silently.
- **F3 (High) — MIC is part of every price key, yet the directory can move it.**
  - Quote and close uniqueness include `mic` (`models.py:887-888,960-961`), and every reader filters `mic = :mic`.
  - The directory's Nasdaq `Market Category` (Q/G/S) is stored as `exchange` and was mapped to segment MICs XNGS/XNMS/XNCM. A tier move counts as "updated" but leaves the instrument's MIC unchanged.
  - Rewriting the MIC in place would orphan stored quotes and closes. A new primary row would hide history (the sibling basis needs an ISIN, and US rows have none: `history.py:244-259`).
  - The Yahoo allowlist (`prices/yahoo.py:43-53`) and provider-MIC equality (`prices/__init__.py:169-173`) make stale MICs a functional rejection risk as well as a labeling one.
- **F4 (Medium-High) — Reassignment detection never runs in production.** `_is_reassignment` requires `delisted_at` (`universe.py:69-70`), and nothing outside tests calls `mark_delisted`. A symbol reused by a different issuer between refreshes is recorded as an ordinary rename: baseline and `first_seen` are kept and the mapping is not reviewed. Some of the 51 may be this; the tool flags them.
- **F5 (Medium) — The parser is permissive and `exchange` means two things.**
  - `_EXCHANGE_KEYS` precedence (`seed_radar_universe.py:32`) stores Nasdaq tier letters and other-listed exchange letters in one undocumented column (`models.py:514`).
  - There is no header, footer, minimum-count, duplicate or BOM validation (`:48`, `encoding='utf-8'`). A renamed column silently yields `''` and would rewrite `exchange` on every row as an "update" (`universe.py:115-118`). The preflight worked around the BOM question by re-encoding.
  - There is no parser test.
- **F6 (Medium) — "One primary" is enforced by readers, not the schema, and they disagree.** The index is non-unique. HA1 and the chart refuse two candidates, `quotes.py:134` keeps the last one silently, and the grouped map drops a shared provider symbol silently (`market_data.py:74-79`).
- **F7 (Medium, a useful property) — Every reader treats any status other than `mapped` as ineligible.** `mapping_status` is free text with no CHECK constraint (`models.py:579`), so a new `held` status fails closed everywhere without a migration.
- **F8 (Low-Medium) — `mapped_at` time basis.** The backfill used `CURRENT_TIMESTAMP` (`migration:145`), while HA1 and the chart reject `mapped_at > read_start`, which is naive UTC (`analysis.py:315-317`). A new writer must stamp naive UTC from Python (`run_radar_ingest.py:94-101`). The host DB session time zone is unverified (Q0).
- **F9 (Low-Medium) — Absent-but-mapped symbols stay in the grouped identity map** (`market_data.py:57-64` filters only on `delisted_at`). If they are on the active board and were observed before, they stay in the 95% acceptance denominator (`:128-139,263-280`).
- **F10 (Low) — Only plain alphabetic symbols of up to five letters become identities** (`seed_radar_universe.py:66-70`). Class shares such as BRK.B have no Radar identity, although Alpaca accepts that form (`price_chart_contract.py:344-358`). Nasdaq five-letter warrants, rights, units and preferreds *are* admitted.
- **F11 (Low) — `upsert_symbols` is atomic (one commit) but has no lock, dry-run or audit**, and it makes one SELECT per row. It also uses the deprecated `utcnow()` (`seed:104`).
- **F12 (Info) — Future US writes cannot disturb the A archival proof** as long as they never write `market='de'` or `currency='EUR'` (fingerprint predicates at `archive-fp-0fdad73.py:15-19`).

## 7. Schema assessment

| Need | Current support | Gap |
|---|---|---|
| Provenance | `radar_instruments.mapping_source` (String 24), `mapped_at`; identity has `first_seen` only | No run id, file hash or creation time; no `updated_at`; names and exchanges overwritten in place |
| Status | `mapping_status` (free text, fail-closed); `delisted_at` (never set) | No absence state, review state or reason |
| Effective time | `mapped_at` (creation only) | No valid-from/valid-to, no last-seen-in-directory |
| Rename/reassignment history | none | Overwrite in place; `first_seen` reset only on the unreachable path |
| Manual review | none | No queue or decision record |
| Generation/audit | `radar_mapping_generations` (market column unconstrained; DE-only by docstring; archival and fingerprinted where `market='de'`) | Reusable in principle, but it mixes archival and live meaning. DE generations average ~2.3 MB each (50 MB / 22 rows), so a daily US generation would need its own retention |
| Uniqueness | `(ticker, market, mic)` unique | "one mapped US primary per ticker" and "provider symbol unique" are not enforced |

**Assessment:**
- **B1 (insert-only mapping for safe new identities) needs no migration.** Minimal provenance fits existing columns: `mapping_source='nasdaqdir-YYYYMMDD'` (18 characters) plus a naive-UTC `mapped_at`, with a file-based run report retained on the host.
- **B2 (daily maintenance with absence aging, review queue and audit) needs an additive migration.** Proposal:
  - a `radar_universe_runs` table (file hashes, creation times, counts, breaker and exit state, staged-diff hash, inverse operations);
  - a `radar_universe_events` table (per symbol: added / changed / absent_observed / returned / mapped / held, with before/after JSON and a review decision);
  - three columns on `radar_ticker_universe`: `last_seen_in_directory_at`, `absent_since`, `absent_snapshots`.
- A database-enforced one-primary rule (e.g. a unique index over a generated column) is optional and needs a separate rehearsal on MariaDB 10.11.
- DE/EUR schema and rows stay untouched.

## 8. Proposed mapping contract (US primary)

- **C1 — Exchange code to MIC, interpreted per source file.**
  - `nasdaqlisted` Market Category: Q→XNGS "Nasdaq Global Select", G→XNMS "Nasdaq Global Market", S→XNCM "Nasdaq Capital Market".
  - `otherlisted` Exchange: N→XNYS "NYSE", A→XASE "NYSE American", P→ARCX "NYSE Arca", Z→BATS "Cboe BZX", V→IEXG "IEX".
  - These are the migration's table (`a4c8e2f19b70:23-45`), which is also the Yahoo allowlist key set.
  - Any other code, or a code in the wrong file, gets **no row**; it is quarantined rather than inserted as `XXXX/unverified`.
  - *Verification carry:* confirm the letter meanings against Nasdaq Trader's symbol-directory definitions and ISO 10383 before implementation, and watch for new listing venues (inference: new U.S. listing exchanges would arrive as new codes).
- **C2 — MIC stability.** An existing primary's MIC is never rewritten in place.
  - A Nasdaq tier move is recorded as drift (D1).
  - A cross-exchange transfer goes to review. Switching primaries requires an explicit history-continuity ruling first (F3).
- **C3 — Provider symbol = directory symbol** (plain `^[A-Z]{1,5}$`). It must pass `alpaca_symbol()` and `yahoo_symbol()`. B1 creates no other form, and no rewriting or guessing is allowed.
- **C4 — Currency and market.** `market='us'`, `currency='USD'`, `isin=NULL` unless verified. Never EUR or DE.
- **C5 — One primary.** Exactly one `is_primary=1 AND mapping_status='mapped'` row per active ticker. The writer checks this inside its transaction; a post-apply check must return nothing.
- **C6 — No provider-symbol collisions.** A provider symbol must be unique among mapped US primaries of active tickers. The writer refuses a collision; otherwise the grouped map would silently drop both.
- **C7 — Time basis.** `mapped_at` = naive UTC from the application clock, at or before commit.
- **C8 — Provenance.** `mapping_source='nasdaqdir-<YYYYMMDD of file creation>'`. The run report (hashes, creation times, counts, inserted ids) is retained, in a table from B2 onward.
- **C9 — Statuses.**
  - `mapped` — eligible.
  - `held` — writer-owned, ineligible, pending review. Used only on rows the writer is creating; never applied automatically to an existing `mapped` row, because that would silently remove prices.
  - Existing `unverified` rows are left alone.
- **C10 — Missing provider data.** Mapping does not depend on provider presence. Readers already degrade honestly (stored-data fallback, unmatched counts). Provider presence can be recorded passively later from accepted Massive grouped days; an Alpaca asset lookup is D7.
- **C11 — Rename versus reassignment.** A same-issuer rename updates identity text only. A first-token change, or a return with a different issuer, updates identity text but queues review. Any baseline reset or mapping change waits for that review (D2).
- **C12 — Non-common listings** (warrants, rights, units, preferreds, notes). The identity is kept for extraction; there is **no mapping** until D3.
- **C13 — Absence** never deletes or unmaps anything. See §9.5.

## 9. Proposed failure-safe daily maintenance (B2)

1. **Serialize.** Take a dedicated connection and `GET_LOCK('radar_universe_maintenance', 0)`. If busy → exit 40. The CLI and any scheduled run share this lock.
2. **Acquire both files.**
   - HTTPS from `https://www.nasdaqtrader.com/dynamic/symdir/{nasdaqlisted,otherlisted}.txt`.
   - Use `trust_env=False`, a (5, 20) s timeout, a 5 MB body cap and at most one retry.
   - Write the exact bytes atomically to a 0700 run directory and hash them.
   - Parse only the exact bytes that were stored and hashed.
3. **Validate each file.** Any failure → exit 20 with **no mutation**, and the evidence is kept.
   - Decode as utf-8-sig and record whether a BOM was present.
   - The header must equal the pinned column list. Every row must have the header's width.
   - The footer must match `File Creation Time: MMDDYYYYHH:MM` with pipe padding. The creation time must be no more than 36 h old and not in the future, and the two files' times must be within 6 h of each other.
   - Usable rows: at least 4,800 for Nasdaq and 6,000 for other listings (about 85% of 2026-09-16), and within ±3% of the last accepted run.
   - No duplicate symbol within a file, and no overlap between the files.
   - ETF and Test Issue values must be Y or N.
   - The code must be in that file's allowed set. More than 5 quarantined rows fails the run.
4. **Idempotency.** If the hash pair equals the last accepted run → exit 10 (`no_newer`). Files older than the last accepted run → exit 20.
5. **Stage and diff.** Normalize rows into a staged JSON with a hash. Compute added / changed / newly absent / returned against the database under the lock, and classify them exactly as in §5.
6. **Circuit breakers.** A tripped breaker → exit 30, no mutation, and a report. A later `--approve-run <run_id>` applies only that exact staged hash. Proposed defaults, all owner-tunable:
   - added > 250 or > 2%;
   - newly absent > 60 or > 0.5%;
   - changed > 200;
   - first-token changes > 10;
   - venue transfers > 25.
7. **Dry run by default.** Write the diff report and exit 0.
8. **Apply** (explicit flag, or scheduled apply mode after D5), in **one transaction**:
   - identity inserts and text updates (D2 governs reassignment holds);
   - C1–C9 mapping inserts for safe candidates;
   - absence counters;
   - the run row plus pre-images and inserted ids.
   Before committing, run the invariant checks: one primary, provider uniqueness, no non-USD US row, and the DE/EUR row count and max id unchanged. Any failure → rollback, exit 60. Otherwise commit, run a read-only post-check, and exit 0. A database error → rollback, exit 50.
9. **Absence lifecycle.**
   - `present` → `absent(n)`, counting only **accepted** snapshots. Failed, stale or partial runs neither count nor reset.
   - At n ≥ 5 accepted snapshots spanning ≥ 7 days → `absence_confirmed`, which only enqueues review.
   - `delisted_at` is set only by a reviewed action (D4). The mapping stays; it may become `held` only after review.
   - Reappearance resets n. A different issuer triggers reassignment review.
   - The 87 are at n = 1 as of 2026-09-16: no action.
10. **Rollback.** `--rollback <run_id>` reapplies the stored pre-images in one transaction, and refuses (exit 50) if a later accepted run touched the same rows. Rows the run inserted are removed only if still unchanged (D4 covers whether that delete is acceptable; the alternative is `held`). The nightly database backup remains the last resort.
11. **Scheduling and observability.**
    - Network fetches never run on a web request path.
    - The first runs are manual CLI runs. Later, one run per day (proposed 10:30 UTC) either as a `radar_ingest` APScheduler job (`max_instances=1` plus the named lock) or as a systemd timer (D5). Weekend `no_newer` is normal.
    - The ops panel shows the last accepted run, its age, counts and breaker state from the run table. Raise a flag if the last accepted run is more than 72 h old or a breaker tripped.
    - Log one structured line per run.
12. **Exit codes:** 0 ok/dry, 10 no_newer, 20 invalid/stale input, 30 breaker, 40 lock busy, 50 DB error or refused rollback, 60 invariant failure.

## 10. Test matrix and future live verification

| Layer | Cases |
|---|---|
| Parser (pure) | exact headers; renamed/missing column refused; BOM accepted and recorded; footer parse and missing footer; Test Issue skip; `isalpha`/length filter; ETF Y/N/blank; row-width mismatch; duplicates within a file; cross-file overlap |
| Validator (pure) | row-count floors and deltas; freshness and future times; creation-time skew; unknown code in the right versus wrong file; quarantine limit; `no_newer` idempotency |
| Diff/classifier (pure) | added/changed/absent/returned; cosmetic, description, rename and first-token change; tier versus cross-venue; issuer pairing and the fund exception; derivative corroboration |
| Breakers (pure) | each threshold at, below and above its limit; `--approve-run` bound to the staged hash |
| Mapping planner (pure) | C1 table, including wrong-file codes; C3 forms; C4 USD/US only; C5 one primary; C6 collision refused; C7 naive UTC; C8 source length ≤ 24 |
| Apply (disposable DB) | single transaction rolls back on injected failure; rerun is idempotent; lock contention returns 40; invariant violation returns 60; rollback via pre-images and refusal after a later run; DE/EUR rows unchanged |
| Readers (disposable DB) | a newly mapped ticker becomes eligible in quotes, the US cycle, the grouped map, HA1 and the chart; a `held` row is ineligible everywhere; the F2 fix: an all-unmapped batch writes no XNAS rows |
| Environment carry | DB-backed suites need a registered disposable target (`tests/radar_disposable.py`); that registry is still unavailable (A carry) |

**Future live verification** (separately authorized):
- a dry run on the host with fresh files, compared against the reconstructed cohorts;
- one apply for the reviewed safe set;
- checks afterwards:
  - mapped active count rises by exactly that set;
  - multiple primaries = 0 and provider collisions = 0 (Q2/Q8);
  - the A archive fingerprint reports `all_match`;
  - three new symbols resolve on HA1 and the chart;
  - the next accepted grouped day shows `unmatched_provider` down, with coverage still above the floor;
  - no new errors.

## 11. Ranked risks and owner decisions

**Risks, ranked by severity × irreversibility:**
1. F3: a wrong MIC rewrite orphans or hides price history. Recovery is hard.
2. F4/C11: a missed reassignment corrupts the baseline without any signal.
3. F2: orphan XNAS rows accumulate.
4. F1: the product gap — undiscoverable prices for new listings.
5. F5: a silent parser degradation rewrites identity text.
6. F6: silent last-wins or dropped primaries.
7. F8: a future `mapped_at` makes rows transiently ineligible.
8. F9: absent rows depress grouped coverage.

**Decisions:**
- **D1** — MIC policy.
  - (a) Keep the MIC fixed and record tier drift. **Recommended.**
  - (b) Normalize Nasdaq to XNAS, which needs a keyed data migration.
  - (c) Add a new primary row plus a history-continuity rule. Cross-venue transfers stay manual under any option.
- **D2** — First-token changes: apply the text update automatically but hold baseline and mapping for review (**recommended**), or hold the whole row.
- **D3** — Map non-common listings (warrants, rights, units, preferreds, notes)? **Recommended: no, for now.**
- **D4** — Absence thresholds, and whether delisting or deletion of inserted rows is ever automatic. **Recommended: manual only in B2.**
- **D5** — Scheduler home (radar_ingest job versus systemd timer) and whether scheduled runs may apply or only dry-run.
- **D6** — Authorize evidence completion (§12). **Required to close this assignment's cohort deliverable.**
- **D7** — Provider presence: an Alpaca asset lookup (extra provider calls) versus passive Massive observation. **Recommended: passive.**
- **D8** — F2: include the one-line "skip unmapped instead of defaulting to XNAS" fix in B1 (**recommended**), and leave existing XNAS rows inert.

## 12. Smallest safe next steps

**Next assignment (recommended): `B-US-UNIVERSE-EVIDENCE-2`** — a Researcher, read-only, with owner authorization D6 limited to three steps:
1. Copy `/root/radar-universe-refresh-20260916/{nasdaqlisted.txt,otherlisted.txt,universe-before.json,preflight.json}` read-only to a local evidence directory. Record the hashes on the host and locally. These files hold public listing metadata only; the `.env` is never read.
2. Run `current_state_select.sql` once (READ ONLY transaction, `max_statement_time=10`, rollback). Credentials are read by name only.
3. Run `reconstruct_cohorts.py` locally with `--current`, and return the three tables, reconciliation and drift.

No fresh directory fetch is needed for the historical cohorts. It can be authorized separately if the owner wants today's directory drift.

**Smallest safe implementation slice, after the evidence is accepted and D1/D3/D8 are decided:** **B1**, with no migration and no scheduler:
- a strict directory parser/validator module;
- a dry-run reconciler CLI (the default);
- an explicit `--apply-mappings` step that **only inserts** C1–C8 US primary rows for reviewed `SAFE_AUTO_MAP_CANDIDATE` identities, in one transaction under the named lock, with apply-time rechecks and a retained run report;
- the D8 fallback fix.

B1 excludes identity-upsert changes, absence handling, MIC rewrites, delisting and scheduling; those belong to B2. The sequence is one Implementer, then an independent Reviewer, then an owner-authorized deployment and one manual apply.

## 13. Actions and protected state

**Actions:**
- Read repository and Git state.
- Created untracked files:
  - `radar-design/B-US-UNIVERSE-EVIDENCE-1-RETURN.md`;
  - `radar-design/artifacts/b-us-universe-evidence-1/{reconstruct_cohorts.py, selftest_reconstruct.py, current_state_select.sql, cohort-schema.json, cohort-status.json}`.
- Ran the synthetic self-test in the session scratchpad, plus `py_compile` (I removed the `__pycache__` it created).

**No actions of any other kind:**
- no importer run or database connection;
- no production, host or network access;
- no product/test/config/migration edits;
- no ledger or handoff edits;
- no staging, commits or deployment;
- no subagents.

Release A remains closed. Pre-existing dirt, other worktrees, local databases and ports are untouched.

## 14. Mastermind return prompt

```text
You are Radar's Mastermind / Overview. Resume from repository evidence, not chat memory.

Assignment completed: B-US-UNIVERSE-EVIDENCE-1 (repository portion complete; exact cohort rows BLOCKED on authorization)
Workspace: C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Observed HEAD / origin/main / feature ref: 0fdad7327292cd3cd0b62dbe3f6b460873263053 / 0fdad7327292cd3cd0b62dbe3f6b460873263053 / 0fdad7327292cd3cd0b62dbe3f6b460873263053
Observed index and worktree dirt: index empty. 9 tracked Mastermind-owned continuity files modified (HANDOFF.md; radar-design/A-US-USD-ONLY-LEDGER, ASSIGNMENTS, HANDOFF, MARKET-DATA-ROADMAP, MASTERMIND-STATE, MD-SELECTED-PRICE-LEDGER, ROADMAP, WORKFLOW .md) plus 370 pre-existing untracked paths, all untouched. Researcher added only untracked radar-design/B-US-UNIVERSE-EVIDENCE-1-RETURN.md and radar-design/artifacts/b-us-universe-evidence-1/ (5 files). No stage/commit; B ledger and handoffs NOT edited (Mastermind-owned).

Read completely:
1. HANDOFF.md
2. radar-design/B-US-UNIVERSE-BRIEF.md
3. radar-design/B-US-UNIVERSE-LEDGER.md
4. radar-design/US-UNIVERSE-REFRESH-2026-09-16.md
5. radar-design/B-US-UNIVERSE-EVIDENCE-1-RETURN.md, then radar-design/artifacts/b-us-universe-evidence-1/{cohort-status.json, cohort-schema.json, reconstruct_cohorts.py, selftest_reconstruct.py, current_state_select.sql}

Research result:
- Historical 146 cohort: totals reconcile exactly (12,658 incoming - 12,512 matched = 146 = 12,745 active - 12,599 mapped); rows NOT reconstructed. They exist only in host files /root/radar-universe-refresh-20260916/ and the production DB, which the dispatch did not authorize (no worktree artifact names any cohort symbol). Classification rules and a tested offline tool are ready; the tool runs the importer's own parser from source.
- Historical 51 cohort: 51 of the 12,512 matched rows (name or exchange differs); rows NOT reconstructed; rules separate cosmetic/description, rename, Nasdaq tier drift, venue transfer and possible reassignment.
- Historical 87 cohort: before = 12,512 + 87 = 12,599 = pre-import active, so 0 delisted and 0 revived (derived). Rows NOT reconstructed; every disposition is observe/no-delist; ticker-change pairing with the 146 is built in.
- Current-state drift: NOT MEASURED (SELECTs not authorized). Repository evidence predicts no identity/mapping drift since the import, but possible orphan quote rows under a fabricated MIC XNAS for unmapped symbols (F2). Query text prepared, not executed.
- Mapping-contract recommendation: C1-C13 in the return: per-file eight-code MIC table from migration a4c8e2f19b70; never rewrite an existing MIC in place; provider_symbol = plain symbol; USD/US only; one mapped primary; no provider-symbol collision; naive-UTC mapped_at; mapping_source nasdaqdir-YYYYMMDD; 'held' as a fail-closed status only for writer-created rows; non-common listings unmapped pending D3; absence never deletes or unmaps.
- Daily-maintenance recommendation: B2 design in return section 9: named DB lock; exact-bytes acquisition of both files; strict header/footer/freshness/floor/delta/duplicate/overlap/code validation with no mutation on failure; hash idempotency; staged diff; circuit breakers with hash-bound approval; dry-run default; single-transaction apply with invariant checks and pre-image rollback; conservative absence aging (5 accepted snapshots over 7 days, then review only; delisting manual); deterministic exit codes 0/10/20/30/40/50/60; ops visibility; scheduler home is D5.
- Schema/migration assessment: B1 (insert-only safe mappings) needs NO migration. B2 needs additive tables radar_universe_runs and radar_universe_events plus three absence columns on radar_ticker_universe. One-primary and provider uniqueness are not DB-enforced today (F6). Archival fingerprints cover only DE/EUR predicates, so US writes cannot disturb A (F12).
- Open decisions/risks: findings F1 (no US mapping writer exists), F2 (legacy fallback writes XNAS rows for unmapped tickers), F3 (MIC is part of every price key while tier/venue moves change the directory code), F4 (reassignment detection never runs; mark_delisted has no production caller), F5 (permissive parser, no parser tests, mixed-meaning exchange column), F6-F11. Decisions D1 (MIC policy), D2 (first-token changes), D3 (non-common listings), D4 (absence/delisting automation), D5 (scheduler home/apply mode), D6 (authorize evidence completion), D7 (provider presence check), D8 (F2 fix in B1). Verification carry: confirm the exchange-letter meanings and ISO MICs against official definitions before implementation.
- Smallest safe next assignment: B-US-UNIVERSE-EVIDENCE-2 (Researcher, read-only) once the owner authorizes D6: read-only copy of the four retained host files, one run of current_state_select.sql in a READ ONLY transaction, local run of reconstruct_cohorts.py --current, then return exact tables and drift. After acceptance and D1/D3/D8: implementation slice B1 (strict parser/validator + dry-run reconciler + insert-only US primary mapper for reviewed safe identities + the F2 fix; no migration or scheduler).

Release A remains CLOSED. Do not rerun the completed manual import. Do not implement, deploy, mutate production, or dispatch another worker until this return is reconciled into the B ledger and the owner approves the next step.
```
