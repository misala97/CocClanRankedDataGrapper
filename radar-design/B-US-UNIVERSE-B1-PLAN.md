# Radar B1 US Universe Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not use subagents; Radar requires one owner-selected Implementer followed by one independent Reviewer.

**Goal:** Build a strict, fail-closed Nasdaq-directory reconciliation path and a guarded insert-only mapper for the accepted 114 safe US identities, while eliminating fabricated MIC fallbacks and preserving every existing mapping and historical row.

**Architecture:** A new pure directory-contract module owns file-specific headers, code-to-MIC metadata, parsing, validation, and reconciliation shapes. A separate CLI remains dry-run by default and requires an explicit reviewed approval manifest before its transactional mapping mode is even reachable. Existing quote readers stop admitting unmapped identities through the legacy `XNAS` fallback, while HA1 learns the already-confirmed `IEXG` MIC.

**Tech Stack:** Python 3.12, Flask, SQLAlchemy, pytest, existing Radar models and database helpers. No new package, migration, scheduler, network client, provider call, frontend change, or production action.

**Spec:** `radar-design/B-US-UNIVERSE-BRIEF.md`; binding decisions and corrections are in `radar-design/B-US-UNIVERSE-AUTHORITY-1-RULING.md`.

## Global Constraints

- Start only from workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, expected `HEAD` `0fdad7327292cd3cd0b62dbe3f6b460873263053`.
- Preserve all pre-existing tracked and untracked work. Leave the B1 candidate uncommitted and unstaged for independent review.
- Release A is closed. Do not rerun, test, review, deploy, clean up, or otherwise reopen A.
- The completed 2026-09-16 manual import is historical evidence. Do not rerun it and do not fetch fresh directory data.
- Do not access production, any VPS, any provider/account endpoint, or any non-disposable database.
- Do not alter `models.py`, any migration, schema, environment, job, timer, service, frontend, or historical DE/EUR row.
- Do not change identity upsert, absence, delisting, reassignment, MIC-transition, provider-presence, or scheduler behavior. Those remain B2 or manual-review work.
- Preserve the existing MIC of every mapped row. Never rewrite, replace, deactivate, or delete an existing `RadarInstrument`.
- D1: retain segment MICs and expose `mic_type` plus `operating_mic` in the directory contract; never normalize Nasdaq tiers to `XNAS`.
- D2: name changes are report-only in B1. No identity text, baseline, `first_seen`, or mapping is changed.
- D3: the 26 non-common listings remain identities only and receive no price mapping.
- D8: unknown or unmapped identities are skipped/quarantined; never fabricate `XNAS` or `XXXX`.
- The real 114-row apply is not part of local implementation. Implement and test the guarded capability, produce an offline/dry-run reconciliation, and stop before any real apply.
- Every task begins with a failing focused test, implements the smallest responsible change, reruns its focused gate, and records a checkpoint in the return.

---

### Task 1: Add the strict, source-aware directory contract

**Files:**

- Create: `personal_apps/features/radar/universe_directory.py`
- Create: `personal_apps/tests/test_radar_universe_directory.py`
- Modify: `personal_apps/scripts/seed_radar_universe.py`

**Interfaces:**

- Produces `SourceKind = Literal['nasdaqlisted', 'otherlisted']`.
- Produces immutable `VenueRule(code, mic, venue, mic_type, operating_mic)` values keyed by `(source_kind, code)`.
- Produces `DirectoryRow(symbol, name, exchange_code, is_etf, source_kind)`.
- Produces `DirectorySnapshot(source_kind, rows, file_created_at, sha256, bom_present)`.
- Produces `parse_directory(path: Path, source_kind: SourceKind) -> DirectorySnapshot` and `validate_pair(nasdaq, other) -> None`.
- `seed_radar_universe.load_rows` delegates to this contract with an explicit source kind; it no longer accepts `Listing Exchange` or generic CSV aliases.

- [ ] **Step 1: Write failing contract tests.**

Cover all eight rules and the wrong-file quarantine:

```python
assert venue_rule('nasdaqlisted', 'Q') == VenueRule(
    'Q', 'XNGS', 'Nasdaq Global Select', 'SGMT', 'XNAS')
assert venue_rule('nasdaqlisted', 'G').mic == 'XNMS'
assert venue_rule('nasdaqlisted', 'S').mic == 'XNCM'
assert venue_rule('otherlisted', 'N').mic == 'XNYS'
assert venue_rule('otherlisted', 'A').mic == 'XASE'
assert venue_rule('otherlisted', 'P').mic == 'ARCX'
assert venue_rule('otherlisted', 'Z').mic == 'BATS'
assert venue_rule('otherlisted', 'V').mic == 'IEXG'
assert venue_rule('otherlisted', 'Q') is None
assert venue_rule('nasdaqlisted', 'N') is None
```

Use exact pinned headers:

```python
NASDAQ_HEADER = ('Symbol', 'Security Name', 'Market Category', 'Test Issue',
                  'Financial Status', 'Round Lot Size', 'ETF', 'NextShares')
OTHER_HEADER = ('ACT Symbol', 'Security Name', 'Exchange', 'CQS Symbol', 'ETF',
                'Round Lot Size', 'Test Issue', 'NASDAQ Symbol')
```

Tests must prove: UTF-8 BOM accepted and recorded; renamed/missing/extra header rejected; every row has exact width; footer matches `File Creation Time: MMDDYYYYHH:MM`; missing/duplicate footer rejected; Test Issue Y excluded; ETF accepts only Y/N; blank ETF rejected because both official files carry it; symbols must match `^[A-Z]{1,5}$`; duplicate symbols fail; unknown/wrong-file codes are quarantined and make validation fail; the two files may not overlap. A fixture containing only `Listing Exchange` must fail.

- [ ] **Step 2: Run the new tests and confirm they fail because the module does not exist.**

```powershell
py -3.12 -m pytest tests/test_radar_universe_directory.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement the immutable mapping and strict parser.**

Use this complete authority table:

```python
VENUE_RULES = {
    ('nasdaqlisted', 'Q'): VenueRule('Q', 'XNGS', 'Nasdaq Global Select', 'SGMT', 'XNAS'),
    ('nasdaqlisted', 'G'): VenueRule('G', 'XNMS', 'Nasdaq Global Market', 'SGMT', 'XNAS'),
    ('nasdaqlisted', 'S'): VenueRule('S', 'XNCM', 'Nasdaq Capital Market', 'SGMT', 'XNAS'),
    ('otherlisted', 'N'): VenueRule('N', 'XNYS', 'NYSE', 'OPRT', 'XNYS'),
    ('otherlisted', 'A'): VenueRule('A', 'XASE', 'NYSE American', 'SGMT', 'XNYS'),
    ('otherlisted', 'P'): VenueRule('P', 'ARCX', 'NYSE Arca', 'SGMT', 'XNYS'),
    ('otherlisted', 'Z'): VenueRule('Z', 'BATS', 'Cboe BZX', 'SGMT', 'XCBO'),
    ('otherlisted', 'V'): VenueRule('V', 'IEXG', 'IEX', 'OPRT', 'IEXG'),
}
```

Read bytes once, hash those exact bytes, decode with `utf-8-sig`, and never infer a source kind from a filename or header. Return all validation problems together in a stable `DirectoryValidationError` without mutating anything. `validate_pair` rejects cross-file symbol overlap. Do not implement network fetching, freshness windows, row-count circuit breakers, or accepted-run persistence in B1.

Modify `seed_radar_universe.py` so each input is explicitly bound by basename to only `nasdaqlisted.txt` or `otherlisted.txt`, and parsing uses `parse_directory`. Unknown filenames fail before `app.app_context()` is entered. Keep its existing identity-upsert semantics otherwise unchanged; do not run it during this assignment.

- [ ] **Step 4: Run focused parser tests.**

```powershell
py -3.12 -m pytest tests/test_radar_universe_directory.py tests/test_radar_universe.py -q -p no:cacheprovider
```

- [ ] **Step 5: Record the Task 1 checkpoint without staging or committing.**

Record files, command output, and the explicit proof that `Listing Exchange` no longer supplies a code.

---

### Task 2: Add a pure dry-run reconciler and reviewed-approval contract

**Files:**

- Create: `personal_apps/features/radar/universe_reconcile.py`
- Create: `personal_apps/tests/test_radar_universe_reconcile.py`
- Create: `personal_apps/scripts/reconcile_radar_universe.py`
- Test fixture only: `personal_apps/tests/fixtures/radar_universe/approved_safe_sample.csv`

**Interfaces:**

- Produces `CurrentIdentity` and `CurrentMapping` plain immutable records, with no ORM dependency in the pure reconciler.
- Produces `Reconciliation` containing `safe_mapping_candidates`, `non_common`, `name_review`, `mic_drift`, `absent`, `conflicts`, and `quarantined` lists.
- Produces `reconcile(snapshot_rows, current_identities, current_mappings) -> Reconciliation`.
- Produces `load_approved_mappings(path) -> tuple[ApprovedMapping, ...]` for a CSV whose exact header is `symbol,mic,source_kind,exchange_code,directory_sha256`.
- Produces `load_current_state(session) -> tuple[tuple[CurrentIdentity, ...], tuple[CurrentMapping, ...]]` using bounded read queries only.
- The CLI accepts two local directory paths and a required `--report PATH`, opens the configured database only to load current identities/mappings, and defaults to a read-only JSON/text report. It performs no download and no database mutation unless both `--apply-mappings` and `--approved-mappings PATH` are present.

- [ ] **Step 1: Write failing pure reconciliation tests.**

Tests must prove:

```python
assert result.safe_mapping_candidates[0].symbol == 'SAFE'
assert result.safe_mapping_candidates[0].market == 'us'
assert result.safe_mapping_candidates[0].currency == 'USD'
assert result.safe_mapping_candidates[0].provider_symbol == 'SAFE'
assert result.non_common[0].action == 'identity_only'
assert result.name_review[0].action == 'review_no_mutation'
assert result.mic_drift[0].action == 'preserve_existing_mic'
assert result.absent[0].action == 'observe_only'
```

Include cases for: an active plain common/fund identity with no US row; each non-common name class (warrant, right, unit, preferred, note); an existing primary; a provider-symbol collision; a first-token change; a T1/T2/T3 MIC difference; an unknown code; an inactive identity; and a directory-absent identity. The pure reconciler must never emit an update/delete action.

Approval parsing must reject duplicate symbols, unknown MICs, a MIC that disagrees with the source/code rule, malformed SHA-256, unexpected columns, and symbols outside `^[A-Z]{1,5}$`.

- [ ] **Step 2: Run the new tests and confirm the missing-module failures.**

```powershell
py -3.12 -m pytest tests/test_radar_universe_reconcile.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement the pure reconciliation and CLI dry-run.**

The report must be deterministic: sort every cohort by symbol and serialize only non-secret fields. The mapping plan for a safe row is exactly:

```python
PlannedMapping(
    ticker=row.symbol,
    market='us',
    venue=rule.venue,
    mic=rule.mic,
    provider_symbol=row.symbol,
    currency='USD',
    isin=None,
    is_primary=True,
    mapping_status='mapped',
    mapping_source=f'nasdaqdir-{snapshot.file_created_at:%Y%m%d}',
)
```

The non-common classifier is conservative and name-backed: `warrant`, `right`, `unit`, `preferred`, or `note` descriptions are identity-only. The ETF flag does not make a row non-common. Any ambiguity goes to `quarantined`, never to the safe set.

The CLI must print its mode (`dry-run`), both source hashes, creation times, cohort counts, and output path. Without `--apply-mappings`, it may execute only the bounded current-state `SELECT`s and write the requested report; it must not call `upsert_symbols`, flush/commit, acquire the write lock, or mutate any ORM object. The tests must attach a SQL statement recorder and prove every dry-run database statement begins with `SELECT`.

- [ ] **Step 4: Prove dry-run purity and deterministic output.**

```powershell
py -3.12 -m pytest tests/test_radar_universe_reconcile.py -q -p no:cacheprovider
```

Run the CLI twice against copied test fixtures and the same isolated SQLite state, then compare report hashes. Expected: identical hashes, only `SELECT` statements, and zero changed database rows.

- [ ] **Step 5: Reconcile the retained 2026-09-16 evidence offline.**

Use only the retained files under `radar-design/artifacts/b-us-universe-evidence-2/`; do not fetch or touch production. In a sanitized evidence-only verification script, adapt the accepted current-state JSON and cohort CSV fields into the pure `CurrentIdentity`/`CurrentMapping` inputs, then compare the implementation's classifications with the accepted Evidence-2 CSVs. The required acceptance facts are 114 safe candidates, 26 non-common rows, 6 corporate-action review rows, and the accepted seven drift symbols. Keep this adapter under `radar-design/artifacts/b-us-universe-b1-implement-1/`, not in product runtime. If the implementation cannot reproduce those facts without broadening B1, stop and report the exact discrepancy rather than embedding an exception list.

---

### Task 3: Add the guarded insert-only mapping transaction

**Files:**

- Modify: `personal_apps/features/radar/universe_reconcile.py`
- Modify: `personal_apps/scripts/reconcile_radar_universe.py`
- Create: `personal_apps/tests/test_radar_universe_mapping_apply.py`

**Interfaces:**

- Produces `apply_approved_mappings(session, reconciliation, approvals, now_utc) -> ApplyResult`.
- `ApplyResult` contains sorted `inserted`, `skipped`, and `refused` symbols and never includes a secret or connection string.
- The writer uses `GET_LOCK('radar_universe_maintenance', 0)` on MySQL and always releases it in `finally`; the unit boundary permits an injected lock adapter for SQLite tests.
- A single transaction inserts only new `RadarInstrument` rows. It never calls `upsert_symbols` and never updates/deletes an existing row.

- [ ] **Step 1: Write failing disposable-database tests.**

Test one successful insert with exact fields, an idempotent rerun, missing approval, directory-hash mismatch, changed MIC, inactive/missing identity, any existing US instrument, mapped-provider collision, multiple-primary precondition, injected failure, lock contention, and a pre-existing DE/EUR row. Required assertions include:

```python
assert inserted.market == 'us'
assert inserted.currency == 'USD'
assert inserted.mic == 'XNMS'
assert inserted.provider_symbol == inserted.ticker
assert inserted.is_primary is True
assert inserted.mapping_status == 'mapped'
assert inserted.mapping_source == 'nasdaqdir-20260915'
assert inserted.mapped_at == NOW_UTC.replace(tzinfo=None)
assert de_row_after == de_row_before
```

For every refusal and injected exception, assert zero new `RadarInstrument` rows after rollback.

- [ ] **Step 2: Run the apply tests only after proving the target is disposable.**

Prefer isolated SQLite table tests. If a MySQL-specific gate is necessary, use the repository's disposable-target guard and require exact database name `personal_apps_radar_wt`. Otherwise mark that gate unavailable; never redirect it to `personal_apps` or production.

```powershell
py -3.12 -m pytest tests/test_radar_universe_mapping_apply.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement fail-closed apply behavior.**

Before inserting anything, re-query every approved symbol inside the transaction and require all of these to hold: identity exists and is active; current directory row and source hash equal the approval; row remains in `safe_mapping_candidates`; no US instrument exists for the ticker; no mapped active primary owns the provider symbol; proposed market/currency are exactly `us`/`USD`; mapping source length is at most 24; `now_utc` is timezone-aware and is stored as naive UTC. Refuse the entire batch if any symbol fails—no partial success.

After `flush()` and before commit, assert one mapped primary per touched ticker, no provider-symbol collision, and no touched non-US instrument. Commit once. The CLI writes a sanitized report atomically only after the transaction result is known.

The CLI apply branch is reachable only with both flags:

```text
--apply-mappings --approved-mappings <reviewed.csv>
```

There is no `--force`, `--yes`, implicit approval, identity update, MIC rewrite, delete, rollback command, network fetch, or scheduler hook in B1.

- [ ] **Step 4: Run apply and parser/reconciler gates.**

```powershell
py -3.12 -m pytest tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py -q -p no:cacheprovider
```

- [ ] **Step 5: Record the Task 3 checkpoint and stop short of the real apply.**

State explicitly that no 114-row database apply was executed. Preserve the accepted cohort files unchanged.

---

### Task 4: Remove fabricated MIC fallbacks and recognize IEXG

**Files:**

- Modify: `personal_apps/features/radar/quotes.py`
- Modify: `personal_apps/features/radar/prices/__init__.py`
- Modify: `personal_apps/features/radar/analysis_contract.py`
- Modify: `personal_apps/tests/test_radar_quotes.py`
- Modify: `personal_apps/tests/test_radar_prices.py`
- Modify: `personal_apps/tests/ha1_unit/test_analysis_contract.py`

**Interfaces:**

- `Quote(..., mic=...)` requires an explicit MIC; it has no default `XNAS` value.
- `quote_views_for` does not query or adapt stored quote rows for a ticker lacking a mapped US primary.
- Legacy `(market NULL, mic NULL)` rows remain readable only when a mapped US instrument supplies the explicit identity.
- `KNOWN_US_MICS` contains all eight confirmed listing MICs, including `IEXG`.

- [ ] **Step 1: Write failing fallback tests.**

Add tests proving: constructing `Quote` without `mic` raises `TypeError`; an unmapped ticker with stored US or legacy-null rows remains unavailable and writes/returns no fabricated `XNAS`; a mapped ticker may still read its legacy-null snapshot under its actual segment MIC; explicit unknown MICs are not normalized; `calendar_for('IEXG')` returns modeled US hints while `calendar_for('XXXX')` remains unknown.

- [ ] **Step 2: Run focused tests and capture the expected failures.**

```powershell
py -3.12 -m pytest tests/test_radar_quotes.py tests/test_radar_prices.py tests/ha1_unit/test_analysis_contract.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement the narrow D8 and IEXG corrections.**

Remove the constructor default `mic='XNAS'`. In `quote_views_for`, build status candidates only from verified mapped US primaries; for a missing primary, return the existing unavailable `QuoteView` without adapting any stored row. Make `_stored_quote` require a non-null instrument and use `instrument.mic` directly. Do not edit the historical migration containing `XXXX`, and do not rewrite any stored row.

Add `IEXG` to `KNOWN_US_MICS`. No other calendar behavior changes.

- [ ] **Step 4: Run the focused and adjacent reader gates.**

```powershell
py -3.12 -m pytest tests/test_radar_quotes.py tests/test_radar_quotes_batch.py tests/test_radar_prices.py tests/ha1_unit/test_analysis_contract.py -q -p no:cacheprovider
```

- [ ] **Step 5: Record the Task 4 checkpoint without staging or committing.**

List every call site changed to pass an explicit MIC and prove no live fallback remains.

---

### Task 5: Integrated verification, evidence, and Implementer return

**Files:**

- Create: `radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md`
- Create sanitized evidence under: `radar-design/artifacts/b-us-universe-b1-implement-1/`
- Update only current status: `radar-design/B-US-UNIVERSE-LEDGER.md` and root `HANDOFF.md`

- [ ] **Step 1: Run the B1 focused suite and static guards.**

```powershell
py -3.12 -m pytest tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py tests/test_radar_universe.py tests/test_radar_quotes.py tests/test_radar_quotes_batch.py tests/test_radar_prices.py tests/ha1_unit/test_analysis_contract.py -q -p no:cacheprovider
git diff --check
git diff -- personal_apps/models.py personal_apps/migrations
rg -n "Listing Exchange|mic: str = 'XNAS'|row\.mic or 'XNAS'|ELSE 'XXXX'" personal_apps/features personal_apps/scripts personal_apps/tests personal_apps/migrations
```

Expected: tests pass; diff check is clean; models/migrations have no diff; `Listing Exchange` and active `XNAS` defaults have no product hit (their focused rejection tests may contain those literal strings); the immutable historical migration may remain the sole product `ELSE 'XXXX'` hit and must be reported as archival code, not edited.

- [ ] **Step 2: Run wider protected Radar tests in proportion to the change.**

```powershell
py -3.12 -m pytest tests/ -k "radar and not destructive" -q -p no:cacheprovider
```

If repository markers do not safely exclude destructive suites, do not improvise the selector. Run the focused suite plus established selected-price and HA1 unit suites separately, and record the wider gate as unavailable with the exact reason.

- [ ] **Step 3: Produce reproducible offline evidence.**

Retain: command transcript; test summary; source hashes; deterministic dry-run report; comparison against accepted 114/26/6 and seven-drift facts; candidate diff manifest; and a statement that no real apply, production access, network fetch, provider call, migration, commit, or deployment occurred. Do not copy credentials or private environment values.

- [ ] **Step 4: Self-review against the binding ruling.**

Confirm every approved decision is visible in code/tests: D1 segment MIC plus operating metadata; D2 name changes report-only; D3 non-common unmapped; D8 no fabricated fallback; IEXG recognized; undocumented alias gone. Confirm B2 features were not added.

- [ ] **Step 5: Write the return and stop.**

Leave one complete local, uncommitted, unstaged candidate. The next gate is one fresh independent Reviewer/QA. Do not prepare a correction, commit, deploy, or run the real 114-row apply.

## Independent review after implementation

The Reviewer receives this plan, all three B rulings, the implementation return, complete diff, and evidence. Review only: source-aware parsing, fail-closed validation, exact cohort reconciliation, approval binding, transaction atomicity, D1/D2/D3/D8 behavior, IEXG, fallback removal, protected historical state, and test provenance. Findings precede any correction task. Commit, deployment, and the real 114-row apply each require later explicit owner authorization.
