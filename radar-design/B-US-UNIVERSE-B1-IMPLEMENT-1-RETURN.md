# B-US-UNIVERSE-B1-IMPLEMENT-1 — Implementer return

Date: 2026-09-18 · Role: Implementer (Claude Opus 5, no subagents) · Status:
**COMPLETE LOCAL CANDIDATE — UNCOMMITTED; ONE OWNER-AUTHORIZED LOCAL-DATABASE
INCIDENT RECORDED**

## 0. Result

All five plan tasks are implemented test-first and reconciled. The candidate
is one uncommitted, unstaged change set. Three things stand out:

- **Accepted numbers reproduced independently.** The strict parser, run over
  the retained 2026-09-16 files, gives exactly 5,600 + 7,058 = 12,658
  listings, with both hashes matching the recorded ones. The pure reconciler,
  run over Evidence‑2's captured state, gives exactly the accepted **114
  safe / 26 non-common / 6 corporate-action / 7 drift / 87 absent**, symbol
  for symbol. The drift rows split T1/T2/T3 exactly as the Authority ruling
  did. The unmodified CLI's dry-run over that evidence issues two `SELECT`s
  and nothing else. Two runs give byte-identical reports.
- **Apply capability built but not run for real.** The guarded insert-only
  apply is approval-manifest-bound, hash-bound, rechecked inside the
  transaction, serialized, all-or-nothing and idempotent. It was exercised
  only on per-test in-memory SQLite. **No 114-row apply ran anywhere.**
- **Incident — the Mastermind must know.** The plan's wider-gate command bound
  the protected *local development* database `personal_apps` on `localhost`.
  It collected release A's known unguarded migration test (F1), which
  downgraded that database and dropped four tables. I stopped the run and
  reported it. With the owner's explicit authorization I restored the schema
  to head with one `flask db upgrade`. The four tables are back but empty;
  their local rows are lost. Production and the VPS were never contacted.
  Every later gate ran through a harness that makes the application database
  unreachable (§9).

## 1. Start gate (fresh, per-command `safe.directory`)

| Check | Observed |
|---|---|
| Workspace | `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts` |
| Branch | `codex/radar-selected-price-charts` |
| `HEAD` / `origin/main` / `origin/codex/radar-selected-price-charts` | `0fdad7327292cd3cd0b62dbe3f6b460873263053` (all three) |
| Index | empty |
| Pre-existing dirt | 9 modified tracked planning docs + 36 untracked entries (45 status lines), all preserved |
| Recent log | `0fdad73 docs(radar): record US USD-only removal` at the tip |

All required reads were done in order: root `HANDOFF.md`, `WORKFLOW.md`,
the B brief and ledger, the three rulings, the three returns, the B1 plan,
the release-A closure, and the newest notices in `radar-design/HANDOFF.md`,
`ASSIGNMENTS.md` and `MASTERMIND-STATE.md`.

## 2. Completed work, task by task

Per-task detail with the failing-first output of each gate is in
`radar-design/artifacts/b-us-universe-b1-implement-1/checkpoints.md`.

| Task | Files | Failing gate first | Focused gate |
|---|---|---|---|
| 1 strict directory contract | `features/radar/universe_directory.py` (new), `tests/test_radar_universe_directory.py` (new), `scripts/seed_radar_universe.py` | `ModuleNotFoundError` | 80 passed (with `test_radar_universe.py`) |
| 2 pure reconciler + approval contract + dry-run CLI | `features/radar/universe_reconcile.py` (new), `tests/test_radar_universe_reconcile.py` (new), `scripts/reconcile_radar_universe.py` (new), `tests/fixtures/radar_universe/approved_safe_sample.csv` (new) | `ModuleNotFoundError` | 55 passed; offline Evidence‑2 reconciliation ALL OK |
| 3 guarded insert-only apply | `universe_reconcile.py`, `reconcile_radar_universe.py`, `tests/test_radar_universe_mapping_apply.py` (new) | `ImportError: LockUnavailable` | 117 passed (Tasks 1–3 together) |
| 4 fallbacks removed + IEXG | `quotes.py`, `prices/__init__.py`, `analysis_contract.py`, their three test files, **plus one argument each in `prices/finnhub.py` and `prices/twelvedata.py`** (§11 F1) | 8 expected failures | 156 passed |
| 5 verification, evidence, return | this return, the evidence directory, ledger and handoff status | — | §8 |

Self-review (Task 5 Step 4) found three defects in my own candidate. All
three are fixed, each with a test that fails without the fix: a MySQL lock
that could leak, a false whole-batch refusal on DE-archive symbols, and
unvalidated `Test Issue` values (§5, §11).

## 3. Directory contract

**Headers**, exact, pinned per file (`universe_directory.py:94-99`):

- `nasdaqlisted.txt`: `Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares`
- `otherlisted.txt`: `ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol`

**The eight rules** (`VENUE_RULES`, `:75-90`), keyed by `(source_kind, code)`:

| File · column | Code | MIC | Venue label (Radar's, kept) | `mic_type` | `operating_mic` |
|---|---|---|---|---|---|
| nasdaqlisted · Market Category | Q | XNGS | Nasdaq Global Select | SGMT | XNAS |
| nasdaqlisted · Market Category | G | XNMS | Nasdaq Global Market | SGMT | XNAS |
| nasdaqlisted · Market Category | S | XNCM | Nasdaq Capital Market | SGMT | XNAS |
| otherlisted · Exchange | N | XNYS | NYSE | OPRT | XNYS |
| otherlisted · Exchange | A | XASE | NYSE American | SGMT | XNYS |
| otherlisted · Exchange | P | ARCX | NYSE Arca | SGMT | XNYS |
| otherlisted · Exchange | Z | BATS | Cboe BZX | SGMT | XCBO |
| otherlisted · Exchange | V | IEXG | IEX | OPRT | IEXG |

A code from the wrong file, an unknown code, or an unknown source kind
resolves to `None`. Nothing ever falls back to an operating MIC.
`KNOWN_LISTING_MICS` holds the eight and deliberately excludes `XNAS`.

**Validation** (`parse_directory`, `:185`; `_usable_rows`, `:284`):

- It reads the bytes once, hashes exactly those bytes, and decodes them with
  `utf-8-sig`, recording whether a BOM was present.
- The source kind is supplied by the caller and never inferred. The exact
  header then proves which file was bound.
- Every row must have exactly the header's width.
- There must be exactly one `File Creation Time: MMDDYYYYHH:MM` footer, it
  must be the last line, and it must be a real timestamp. The two files pad
  it to different widths, which the parser accepts.
- `Test Issue` and `ETF` must be `Y`/`N`; a blank `ETF` is refused.
- `Test Issue = Y` rows and symbols outside `^[A-Z]{1,5}$` are *excluded*,
  not errors. The retained `otherlisted.txt` has 541 such symbols and `F`/`M`
  codes on its test rows.
- Duplicate symbols fail. Unknown or wrong-file codes are quarantined and
  fail the file.
- All problems come back together in one stably ordered
  `DirectoryValidationError`.
- `validate_pair` refuses anything other than one snapshot of each kind, and
  refuses cross-file overlap.
- Not implemented, as the plan requires: fetching, freshness windows,
  row-count breakers, run persistence.

**The retired alias is gone.** `seed_radar_universe.py` binds each argument
by basename through `source_kind_for` (`:161`), delegates to
`parse_directory`, and imports the application only after every file has
parsed. It no longer contains `csv.DictReader` or the retired column name.
`test_a_listing_exchange_file_can_never_supply_a_code` refuses a
`nasdaqtraded.txt`-shaped file for both source kinds. Upsert semantics are
unchanged; the script was not run.

## 4. Reconciliation — fresh offline counts vs accepted evidence

`verify_against_evidence_2.py` ran 31 checks, all OK. It parses the retained
sources and adapts Evidence‑2's accepted `current-state.json` (12,745
identities, 12,599 US rows) into the pure records. It then runs the real
`reconcile()`.

| Accepted fact | Evidence‑2 | Fresh B1 result |
|---|---|---|
| usable rows / unique incoming | 5,600 + 7,058 / 12,658 | identical; both SHA-256 match (`bd5524e0…`, `86102373…`) |
| safe insert-only candidates | 114 | **114, identical symbol set** |
| non-common (D3) | 26 | **26, identical** (11 warrants, 5 units, 4 rights, 4 note-class, 2 preferred) |
| corporate-action review | 6 | **6, identical** (ATLQ/ATLQR/ATLQU/ATLQW, AELV, MATR) |
| MIC drift | EPRX, FSHP, FSHPR, FSHPU, KHC, MVPA, OPAD | **identical**: T1 EPRX/FSHP/FSHPR/FSHPU, T2 MVPA, T3 KHC/OPAD |
| absent | 87 | **87, identical** |
| candidate MICs | ARCX 36, BATS 28, XNMS 26, XNCM 15, XNYS 5, XASE 4 | identical; no `XNAS`/`XXXX` |
| quarantined / conflicts | — | 0 / 0 |

This is a cross-check of two independent derivations, not a restatement.
Evidence‑2 classified historically (symbols absent from the pre-import
export). B1 classifies from current state (active identity, no mapped US
primary).

The real CLI, over the same evidence loaded into isolated SQLite
(`produce_dry_run_report.py`), gives:

- mode `dry-run`;
- 2 statements recorded, both `SELECT`;
- no row changed;
- two runs with byte-identical `dry-run-report.json`, SHA-256
  `c3cfb922be0875ab1fe045a68aca8a82c564f78ffc0f0b6861a3e2a3485e5ed8`.

## 5. Mapping safety

- **Reachability.** Apply exists only with both `--apply-mappings` and
  `--approved-mappings PATH`. Either one alone is an argparse error. There is
  no `--force`, `--yes`, rollback, delete, identity write, fetch or scheduler
  hook, and a test asserts their absence.
- **Approval binding** (`load_approved_mappings`, `:482`). The header must be
  exactly `symbol,mic,source_kind,exchange_code,directory_sha256`. It refuses:
  - duplicate symbols;
  - symbols outside `^[A-Z]{1,5}$`;
  - a MIC outside the confirmed eight, including `XNAS`/`XXXX`;
  - a MIC that disagrees with its file's code;
  - a code from the wrong file or an unknown source kind;
  - a SHA-256 that is not 64 lowercase hex characters;
  - extra, missing or reordered columns;
  - an empty manifest.
- **Hash binding.** Each reconciliation carries the SHA-256 of the exact
  bytes it parsed. An approval whose `directory_sha256` differs refuses the
  whole batch.
- **Apply-time rechecks, inside the transaction** (`_apply_time_problem`,
  `:698`). For each approved symbol:
  - it is still a safe candidate, with the same source kind, code and MIC;
  - the identity exists and is active;
  - no US instrument row exists;
  - no other mapped US primary owns the provider symbol;
  - market/currency are exactly `us`/`USD`;
  - `mapping_source` is at most 24 characters.
  `now_utc` must be timezone-aware and is stored as naive UTC. The legacy
  backfill's Europe/Berlin `mapped_at` inconsistency is documented, not
  repeated.
- **All or nothing.** Any refused symbol rolls back the whole batch. After
  the flush and before the single commit, `_assert_invariants` (`:749`)
  requires:
  - every inserted row is US/USD;
  - exactly one mapped US primary per touched ticker;
  - no shared provider symbol among mapped US primaries.
  It reads US rows only. Any exception rolls back and re-raises.
- **Serialization.** `named_lock` (`:571`) runs
  `GET_LOCK('radar_universe_maintenance', 0)` and `RELEASE_LOCK` in a
  `finally`, both on **one dedicated connection**. It refuses any non-MySQL
  bind. SQLite tests inject an adapter, as the plan permits. The MySQL
  execution path is **unexercised**; fake-engine tests pin its connection and
  release behaviour.
- **Idempotency.** A symbol already carrying exactly the approved identity is
  *skipped*, never re-inserted or refused. Its `mapped_at` is unchanged,
  whether the plan is reused or freshly reconciled.
- **Never rewrites.** The writer only inserts. No existing `RadarInstrument`
  is updated, disabled or deleted; a source test asserts no such call exists.
  The DE lane is never read by the writer. A US ticker sharing its symbol with
  an archived DE row is inserted, and the DE row stays byte-identical.
- **Reporting.** `ApplyResult` holds sorted `inserted`/`skipped`/`refused`
  plus problems, with no connection detail. The CLI writes its report
  atomically, only after the transaction outcome is known, and exits 1 on any
  refusal.

## 6. D1 / D2 / D3 / D8 proof

| Ruling | Code | Tests |
|---|---|---|
| **D1** segment MIC kept; `mic_type` + `operating_mic` recorded; never normalized; never rewritten | `VENUE_RULES`/`KNOWN_LISTING_MICS` (`universe_directory.py:75-92`); `_classify_mapped` → `mic_drift` `preserve_existing_mic` (`universe_reconcile.py:315`); `_drift` T1/T2/T3 from the ISO operating MIC (`:395`) | `test_segment_mics_record_their_operator_instead_of_becoming_it`; `test_a_mic_difference_preserves_the_stored_mic_and_is_classed` ×5; `test_drift_rows_never_propose_a_new_mapping`; the real 7 |
| **D2** name changes report-only | `_classify_mapped` → `name_review` `review_no_mutation` with the importer's own kinds (`_name_change`, `:421`); corporate-action pairs likewise; B1 has no identity write at all | `test_a_first_token_change_is_reviewed_and_mutates_nothing` (PMA); `test_a_same_issuer_rename_is_reported_without_action`; `test_a_ticker_change_pair_is_reviewed_as_a_corporate_action`; the real 6 |
| **D3** 26 non-common stay identities | `_classify_unmapped` → `non_common` `identity_only` (`:341`); ambiguous derivative wording goes to `quarantined`, never to safe | `test_each_non_common_class_is_identity_only` ×5; `test_an_uncorroborated_derivative_word_is_quarantined_not_mapped`; `test_an_approval_for_something_that_is_not_a_safe_candidate_is_refused`; the real 26 |
| **D8** no fabricated `XNAS`/`XXXX` | parser quarantine; reconciler `unknown_listing_code`/`identity_missing`; `Quote.mic` has no default (`prices/__init__.py:90`); `_stored_quote` requires an instrument (`quotes.py:90-100`); `quote_views_for` reads only mapped primaries (`:150`); `record_quotes` refuses a MIC-less snapshot (`:49`) | `test_an_unknown_code_quarantines_the_row_and_fails_the_file`; `test_an_unknown_listing_code_is_quarantined_and_never_defaulted`; `test_a_quote_cannot_be_built_without_an_explicit_mic`; `test_a_ticker_with_no_mapped_primary_stays_unavailable` ×2; `test_record_quotes_refuses_a_snapshot_with_no_venue` |

## 7. Fallback and IEXG proof

- `Quote(...)` without `mic` raises `TypeError`. Every product construction
  passes one explicitly:
  - `finnhub.py:81` passes `mic=None`, because `/quote` names no listing;
  - `twelvedata.py:110` passes `mic=mic_code` (was `mic_code or 'XNAS'`);
  - `yahoo.py` and `normalize_snapshot` already used the instrument's MIC.
- An unmapped ticker, with either stored US rows or legacy `(NULL, NULL)`
  rows, stays unavailable (`mic=None`, no price). Its stored rows are not
  adapted.
- A mapped ticker still reads its legacy `(NULL, NULL)` snapshot, under its
  real segment MIC (`XNMS` in the test). An explicit unknown stored MIC
  (`XXXX`) is read as itself, never normalized.
- A mixed batch keeps the mapped view and leaves the unmapped one unavailable.
- `KNOWN_US_MICS` is now the eight confirmed listing MICs, adding `IEXG`.
  `calendar_for('IEXG')` gives modeled US hints identical to `XNGS`.
  `XXXX`, `XNAS`, `XETR`, `''` and `None` stay `unknown`.
- The plan's sweep finds no `mic: str = 'XNAS'` and no `row.mic or 'XNAS'`.
  `Listing Exchange` appears only in rejection tests. `ELSE 'XXXX'` appears
  only in the immutable historical migration
  `a4c8e2f19b70_add_radar_market_instruments.py:32` — archival, not edited.
  The remaining `'XNAS'` literals in product code are legitimate:
  - operating-MIC metadata;
  - the T1 test;
  - the dormant Yahoo allowlist key, which accepts a stored MIC and never
    produces one.

## 8. Evidence

All under `radar-design/artifacts/b-us-universe-b1-implement-1/`. Final
transcript: `gate-transcript.txt`, run 2026-09-18T00:14:51Z by
`final_gates.sh`. Every pytest run went through `run_db_free_gate.py`. The
baseline is a read-only `git archive HEAD personal_apps` export of `0fdad73`.

| Gate | Candidate | HEAD baseline |
|---|---|---|
| Focused B1 suite (plan Task 5 Step 1 files) | **266 passed**, 2 failed, 57 errors | existing files: 126 passed, 2 failed, 57 errors |
| selected-price unit | **261 passed** | 261 passed |
| HA1 (`chatter_tone` + `yahoo` + `ha1_unit`, `--noconftest`) | **276 passed**, 3 failed, 1 skipped | 269 passed, 3 failed, 1 skipped |
| Massive | **18 passed** | 18 passed |
| Evidence‑2 reconciliation | 31/31 ALL OK | — |
| CLI dry-run ×2 | 2 `SELECT`s, 0 rows changed, identical `c3cfb922…` | — |
| Pre-fix bug replay | REPRODUCED AND FIXED | — |
| `git diff --check` | exit 0 | — |
| models/migrations diff | 0 lines | — |
| trailing whitespace / `py_compile` | none / exit 0 | — |

**The focused suite's 2 failed + 57 errors** are one set of 59 pre-existing
tests that need the bound database. There are 16 in `test_radar_universe.py`,
30 in `test_radar_quotes.py` and 13 in `test_radar_quotes_batch.py`. They
cannot reach `b1-gate.invalid`. The candidate and baseline sets are
**identical test IDs**. The +140 passes are exactly the new tests:

| New tests | Count |
|---|---|
| directory | 38 |
| reconcile | 55 |
| apply | 32 |
| isolated D8 readers | 6 |
| prices | 2 |
| calendar | 7 |

**The 3 HA1 failures** are `test_radar_yahoo.py::test_daily_closes_*`. They
are identical at baseline. They are clock-dependent: `daily_closes` filters
with `dt.datetime.now() - (days+3)`, and the fixtures are dated 2026-08-31.

Evidence file hashes (SHA-256):

| File | SHA-256 |
|---|---|
| `dry-run-report.json` | `c3cfb922be0875ab1fe045a68aca8a82c564f78ffc0f0b6861a3e2a3485e5ed8` |
| `dry-run-summary.json` | `f69eb4813871718ff6d874c46119c2019dca6a39675a5798b85abbda47cc81a5` |
| `evidence-2-reconciliation.json` | `830b464cba0078307b0edb85eb5620072bfba0a79b6c483395b1855ecb48bd39` |
| `gate-transcript.txt` | `e646a349b581bd576a134c0b4766f2f8d37c590e6718f98883ee700b3af32a51` |
| `candidate-manifest.txt` | `20698bc28d661764dd552f8e21f6c5cc7154442a085f6257de071f2ecb7aaa13` (per-file product hashes + numstat) |
| `verify_against_evidence_2.py` | `0f838ece194f13660129462523ec1ae6400338197aa7505b9c3f2bb35097ea68` |
| `produce_dry_run_report.py` | `4a3b2905e9fba5773c3922301df110a835c3012150b7d195f46e001e30d7d7f9` |
| `run_db_free_gate.py` | `4003b0700410f464f23eaef17fbb14df860266c1027ec109a5703d9c08274fe3` |
| `replay_pre_fix_invariant_bug.py` | `b08103d6cc2c287a3c9adf514765cd5c9bd3149b60ca87312657d0e00411eae6` |
| `final_gates.sh` | `087b3a518c1e60ff03e4cdca723fa159f774810e7cc4ff0b25cf2b4fef70d69b` |

The `checkpoints.md` hash changes with this final edit and is not listed.
No evidence file contains a path to the user profile, a host, a credential or
an environment value (scanned).

## 9. Evidence attribution

- **Fresh worker execution (this session):**
  - every test count, gate and hash above;
  - the offline reconciliation and the CLI dry-run;
  - the HEAD-export baselines;
  - the Evidence‑2 manifest re-hash;
  - the read-only local-schema checks;
  - the owner-authorized restoring upgrade.
- **Fresh, but on a non-authorized target:** before the incident, the
  focused gates that include DB-backed suites ran against local
  `personal_apps`: Task 1's 80-pass, Task 4's 156-pass and my first
  baseline. After that, product code changed only in the self-review fixes.
  Those fixes touch `universe_reconcile.py` and `universe_directory.py`,
  which none of the 59 DB-backed tests exercise.
- **Accepted prior evidence, not re-measured:**
  - the 12,745/12,599 captured state and the cohort CSVs (Evidence‑2);
  - the code and MIC authority (Authority‑1);
  - the release-A archive facts.
- **Inference:**
  - that no real candidate collides with an archived DE ticker is unknown,
    because the DE archive was never captured offline;
  - the MySQL named-lock path is correct by construction and by fake-engine
    test, not by execution.

## 10. Database safety — including the incident

- **Authorized targets used.** Every apply, reconciliation and CLI test ran
  on in-memory SQLite created inside the test. The fixture asserts the
  `sqlite` backend and an empty database name. Only `radar_ticker_universe`
  and `radar_instruments` exist there. `personal_apps_radar_wt` is not
  registered on this machine, so no MySQL gate ran and that gate is
  **unavailable**.
- **The incident, stated plainly.** Task 5 Step 2's wider command
  (`pytest tests/ -k "radar and not destructive"`) was run without first
  proving the selector excludes destructive suites, which the plan requires.
  It bound local `personal_apps`. The unguarded
  `test_radar_activity.py::test_the_migration_adds_and_removes_only_its_own_two_tables`
  (release-A finding F1) downgraded it to `b3d9e1f5a274`, and its `finally`
  upgrade did not restore it. That dropped:
  - `radar_ingest_runs`;
  - `radar_board_observations`;
  - `radar_board_results`;
  - `radar_board_namespaces`.
  I stopped the run, verified the damage with read-only queries, and asked
  the owner. On explicit authorization I ran exactly
  `PYTHONPATH=. FLASK_APP=app.py py -3.12 -m flask db upgrade`, against local
  `personal_apps` only. It is back at head `b7e3f9c1a2d4` with 47 tables. The
  four tables are **empty**; their earlier local rows are **lost**.
- **Never contacted:** production, the VPS, any provider or network
  endpoint, and the DE/EUR archive.
- **No real 114-row apply** ran on any target.

## 11. Findings and limitations

- **F1 — plan/code discrepancy (resolved narrowly).** Task 4 requires
  removing `Quote`'s `mic='XNAS'` default but names neither provider file.
  `prices/finnhub.py:74` built `Quote` without a MIC, and its
  `except (TypeError, …)` would have silently dropped **every** Finnhub quote,
  including mapped tickers, since `_poll_instruments` fetches through
  `provider.quotes()`. Step 5 requires listing "every call site changed to
  pass an explicit MIC", so each provider got a one-argument change:
  - Finnhub `mic=None`;
  - Twelve Data `mic=mic_code`.
  **Ruling requested:** accept these two call-site changes as within Task 4.
- **F2 — behaviour change needing a Mastermind ruling.**
  `run_radar_ingest.py:461-465` still sends an all-unmapped due batch's raw
  Finnhub snapshots to `record_quotes`. That now raises. The cycle's existing
  handler logs `radar US quote cycle failed` with a traceback and reports
  `error: True`, storing nothing. Before B1 this case silently stored
  fabricated `XNAS` rows; measured production extent was zero.
  - It is reachable: `active_price_tickers` is not filtered to mapped
    tickers.
  - The new behaviour is fail-closed but noisy.
  - A quiet skip needs a `run_radar_ingest.py` change, which B1 does not
    authorize.
  **Recommend:** a one-line follow-up, or accept the noise until B2.
- **F3 — self-review fixes (done).** Each is proven by a test that fails
  without its fix:
  - the dedicated-connection lock;
  - the US-only post-flush check, which previously refused a batch on any
    DE-archive symbol collision; the replay shows it;
  - `Test Issue` Y/N validation.
- **F4 — process gap (done here, systemic elsewhere).** The plan's wider
  gate cannot be run safely while `test_radar_activity.py`'s migration test
  stays unguarded. **Recommend** a small bounded fix: wrap it in
  `radar_disposable.require`.
- **F5 — the provider-owner recheck is stricter than C6.** It considers
  every mapped US primary, not only active identities. That is fail-closed;
  with 0 delisted identities today it changes nothing.
- **F6 — rechecks run against a report made before the lock.** Directory-
  and approval-derived facts cannot change, and every database-derived fact
  is re-read inside the transaction. Corporate-action pairing is not
  recomputed at apply time; it could only shift if an identity import ran
  between report and apply.
- **Unavailable gates:**
  - the MySQL apply/lock path and the 59 DB-backed regression tests, for
    lack of a registered `personal_apps_radar_wt`;
  - the plan's wider selector, which is unsafe as written.
- **B2 exclusions kept:**
  - no fetch, freshness, breakers or run table;
  - no identity write, absence aging or delisting;
  - no reassignment, MIC transition or provider presence;
  - no rollback command, scheduler or migration.

## 12. Actions taken

- **Created:**
  - `features/radar/universe_directory.py`;
  - `features/radar/universe_reconcile.py`;
  - `scripts/reconcile_radar_universe.py`;
  - `tests/test_radar_universe_directory.py`;
  - `tests/test_radar_universe_reconcile.py`;
  - `tests/test_radar_universe_mapping_apply.py`;
  - `tests/fixtures/radar_universe/approved_safe_sample.csv`;
  - this return;
  - the evidence directory.
- **Modified:**
  - `features/radar/quotes.py`;
  - `features/radar/prices/__init__.py`;
  - `features/radar/prices/finnhub.py`;
  - `features/radar/prices/twelvedata.py`;
  - `features/radar/analysis_contract.py`;
  - `scripts/seed_radar_universe.py`;
  - `tests/test_radar_quotes.py`;
  - `tests/test_radar_prices.py`;
  - `tests/ha1_unit/test_analysis_contract.py`;
  - the current B1 status in `radar-design/B-US-UNIVERSE-LEDGER.md` and root
    `HANDOFF.md`.
- **Database:**
  - one owner-authorized `flask db upgrade` on local `personal_apps`, to
    restore it;
  - read-only `SELECT`s on it for forensics;
  - no other writes by me. The test-caused downgrade is described in §10.
- **Explicitly not done:**
  - no stage, commit, push or deploy;
  - no network fetch or provider call;
  - no config, env, schema or migration file change;
  - no historical-row mutation;
  - no importer run and no real apply;
  - no subagents.

## 13. Protected state

- Release A is untouched. The eight warm boards and the Charts/Alpaca/Yahoo
  flags are production facts and were not accessed.
- All 12,599 existing mapped US primaries and their history are untouched:
  no production write, and the local writer is insert-only.
- The seven drift rows keep their MICs (`preserve_existing_mic`).
- The 26 non-common and 6 corporate-action identities stay unmapped: never
  safe candidates, and refused by the apply.
- `models.py` and `migrations/` have zero diff.
- The Evidence‑2 manifest re-hashes 19/19. The Evidence‑1 and Authority‑1
  artifacts and all returns predate this work.
- Unrelated dirty files are preserved.

---

## Mastermind return prompt

```text
You are Radar's Mastermind / Overview. Assess this Implementer return for assignment B-US-UNIVERSE-B1-IMPLEMENT-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts; base = HEAD = origin/main = origin/codex/radar-selected-price-charts = 0fdad7327292cd3cd0b62dbe3f6b460873263053 (verified fresh at start and in the final gate transcript); index empty.
Working tree: PRE-EXISTING (preserved): 9 modified tracked Mastermind planning docs (HANDOFF.md; radar-design/A-US-USD-ONLY-LEDGER, ASSIGNMENTS, HANDOFF, MARKET-DATA-ROADMAP, MASTERMIND-STATE, MD-SELECTED-PRICE-LEDGER, ROADMAP, WORKFLOW .md) and 36 untracked entries (B/A/MD returns, rulings, prompts, plan, artifact directories, one docs spec). IMPLEMENTER-OWNED, uncommitted/unstaged: modified personal_apps/features/radar/{quotes.py, prices/__init__.py, prices/finnhub.py, prices/twelvedata.py, analysis_contract.py}, personal_apps/scripts/seed_radar_universe.py, personal_apps/tests/{test_radar_quotes.py, test_radar_prices.py, ha1_unit/test_analysis_contract.py}; created personal_apps/features/radar/{universe_directory.py, universe_reconcile.py}, personal_apps/scripts/reconcile_radar_universe.py, personal_apps/tests/{test_radar_universe_directory.py, test_radar_universe_reconcile.py, test_radar_universe_mapping_apply.py, fixtures/radar_universe/approved_safe_sample.csv}, radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md, radar-design/artifacts/b-us-universe-b1-implement-1/ (11 files). Current-B1-status edits only: root HANDOFF.md (new top notice) and radar-design/B-US-UNIVERSE-LEDGER.md (B1 row + next action). Nothing staged, committed or pushed.
Binding artifacts: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/{B-US-UNIVERSE-BRIEF.md, B-US-UNIVERSE-EVIDENCE-1-RULING.md, B-US-UNIVERSE-EVIDENCE-2-RULING.md, B-US-UNIVERSE-AUTHORITY-1-RULING.md, B-US-UNIVERSE-B1-PLAN.md, B-US-UNIVERSE-LEDGER.md, B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md}; evidence C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/b-us-universe-b1-implement-1/ (checkpoints.md, gate-transcript.txt, final_gates.sh, run_db_free_gate.py, verify_against_evidence_2.py, evidence-2-reconciliation.json, produce_dry_run_report.py, dry-run-report.json, dry-run-summary.json, replay_pre_fix_invariant_bug.py, candidate-manifest.txt).

Objective and authorized scope: Build and locally verify B1 only; no real 114-row apply, production access, commit or deployment.
Completed work:
- Task 1: strict per-file directory contract, universe_directory.py. The seed script now binds inputs by basename and delegates to it.
- Task 2: pure reconciler with 7 cohorts, strict approval-manifest loader, SELECT-only current-state loader, and dry-run-by-default CLI. Evidence-2 reproduced offline, 31/31 checks.
- Task 3: approval- and hash-bound, in-transaction-rechecked, locked, all-or-nothing, idempotent insert-only apply, plus the CLI apply branch.
- Task 4: Quote.mic has no default; the reader admits only mapped primaries; record_quotes refuses a MIC-less snapshot; IEXG added to KNOWN_US_MICS.
- Task 5: gates, evidence, self-review, return.
- Self-review fixed three of my own defects, each proven by a failing-without-fix test:
  (1) the MySQL named lock is now taken and released on one dedicated connection, not the ORM session, whose pooled connection can change at commit;
  (2) the post-flush check now reads US rows only; the first version refused a whole batch when a US symbol matched an archived DE instrument, and a replay reproduces this;
  (3) Test Issue values are validated as Y/N.
Directory contract:
- Headers:
  - nasdaqlisted: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
  - otherlisted: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
- Eight (source_kind, code) rules, each with MIC / mic_type / operating_mic; Radar venue labels kept:
  - Q XNGS SGMT/XNAS
  - G XNMS SGMT/XNAS
  - S XNCM SGMT/XNAS
  - N XNYS OPRT/XNYS
  - A XASE SGMT/XNYS
  - P ARCX SGMT/XNYS
  - Z BATS SGMT/XCBO
  - V IEXG OPRT/IEXG
- Resolving to nothing, never to XNAS/XXXX: wrong-file codes, unknown codes, unknown source kinds.
- Validation:
  - exact-bytes SHA-256 and a recorded BOM;
  - exact header and exact row width;
  - exactly one last-line File Creation Time: MMDDYYYYHH:MM footer, padding-tolerant;
  - Test Issue and ETF must be Y/N; blank ETF refused;
  - Test Issue=Y rows and non-^[A-Z]{1,5}$ symbols are excluded, not errors;
  - duplicates fail; unknown or wrong-file codes are quarantined and fail the file;
  - all problems reported together in a stable order;
  - validate_pair refuses same-kind pairs and cross-file overlap.
- The undocumented Listing Exchange alias is gone; a test refuses such a file for both kinds.
Reconciliation (fresh offline):
- Parser output: 5,600 + 7,058 = 12,658; both SHA-256 match the recorded bd5524e0…/86102373….
- Against Evidence-2's 12,745/12,599 state, as identical symbol sets:
  - safe 114;
  - non-common 26;
  - corporate-action review 6;
  - MIC drift 7 (EPRX, FSHP, FSHPR, FSHPU = T1; MVPA = T2; KHC, OPAD = T3);
  - absent 87;
  - quarantined 0 and conflicts 0.
- Candidate MICs: ARCX 36, BATS 28, XNMS 26, XNCM 15, XNYS 5, XASE 4.
- The unmodified CLI dry-run over that evidence, loaded into isolated SQLite:
  - exactly 2 SELECT statements and 0 rows changed;
  - two runs give byte-identical reports, sha256 c3cfb922be0875ab1fe045a68aca8a82c564f78ffc0f0b6861a3e2a3485e5ed8.
Mapping safety:
- Apply is reachable only with --apply-mappings plus --approved-mappings. There is no force, yes, rollback, delete, fetch or identity write.
- The manifest header must be exactly symbol,mic,source_kind,exchange_code,directory_sha256. The loader refuses:
  - duplicates and non-^[A-Z]{1,5}$ symbols;
  - unknown MICs, including XNAS/XXXX;
  - a MIC that disagrees with its code, and wrong-file codes;
  - malformed SHA-256;
  - extra or reordered columns, and an empty manifest.
- Each reconciliation carries the SHA-256 of the exact directory bytes; the manifest digest must match it.
- Inside the transaction, every approved symbol is re-read:
  - still a safe candidate with the same kind, code and MIC;
  - identity exists and is active;
  - no US row exists;
  - provider symbol not owned by another mapped US primary;
  - us/USD;
  - source at most 24 characters;
  - aware now_utc, stored as naive UTC.
- Any refusal refuses the whole batch.
- After the flush, before the single commit: inserted rows are US/USD; one mapped US primary per touched ticker; no shared provider symbol. US rows only are read.
- Any exception rolls back and re-raises.
- Lock: GET_LOCK('radar_universe_maintenance', 0) and RELEASE_LOCK in finally, on one dedicated connection; non-MySQL binds are refused; SQLite tests inject an adapter.
- An already-applied identical row is skipped with mapped_at unchanged, whether the plan is reused or freshly reconciled.
- No existing row is updated or deleted. A DE row sharing the symbol stays byte-identical.
- 32 apply tests, all on in-memory SQLite.
D1/D2/D3/D8 proof:
- D1: universe_directory.py VENUE_RULES/KNOWN_LISTING_MICS lines 75-92; universe_reconcile.py _classify_mapped line 315 and _drift line 395. Tests: segment/operator test; 5 T1/T2/T3 drift parametrisations; the real 7.
- D2: _classify_mapped → name_review/review_no_mutation, using the importer's own name-change kinds; B1 has no identity write. Tests: PMA first-token test; rename test; JAB/ATLQ pair test; the real 6.
- D3: _classify_unmapped line 341 → non_common/identity_only; ambiguous wording is quarantined. Tests: 5 class parametrisations; uncorroborated-unit test; the apply refuses a warrant approval; the real 26.
- D8:
  - parser quarantine;
  - reconciler unknown_listing_code/identity_missing;
  - prices/__init__.py:90 mic keyword-only with no default;
  - quotes.py:90-100 _stored_quote requires an instrument;
  - quotes.py:150 candidates are mapped primaries only;
  - quotes.py:49 record_quotes refuses mic None.
  - Tests: unknown-code, no-default, unmapped-unavailable ×2 and record-refusal tests.
Fallback/IEXG proof:
- Quote() without mic raises TypeError.
- Provider call sites: finnhub.py:81 mic=None; twelvedata.py:110 mic=mic_code (was mic_code or 'XNAS').
- An unmapped ticker with stored US or legacy-null rows is unavailable with mic None. A mapped ticker reads its legacy-null row under XNMS. An explicit XXXX is read as itself. A mixed batch is correct.
- KNOWN_US_MICS = the 8 confirmed MICs. calendar_for('IEXG') gives modeled hints equal to XNGS; XXXX, XNAS, XETR, '' and None stay unknown.
- Plan sweep: no mic: str = 'XNAS' and no row.mic or 'XNAS'. Listing Exchange appears only in rejection tests. ELSE 'XXXX' appears only in the immutable migration a4c8e2f19b70:32, which is archival and not edited.
Evidence:
- final_gates.sh → gate-transcript.txt (sha e646a349…), 2026-09-18T00:14:51Z. All pytest runs via run_db_free_gate.py: no .env read, DB host b1-gate.invalid. Baseline = read-only git archive of HEAD.
- Focused B1 suite: candidate 266 passed / 2 failed / 57 errors; baseline 126 / 2 / 57. The 59 failed/errored IDs are identical: pre-existing DB-backed tests that cannot connect (universe 16, quotes 30, quotes_batch 13). The +140 passes are exactly the new tests: directory 38, reconcile 55, apply 32, isolated D8 readers 6, prices 2, calendar 7.
- selected-price: 261 = baseline 261.
- HA1 (chatter_tone+yahoo+ha1_unit --noconftest): 276 passed / 3 failed / 1 skipped vs baseline 269 / 3 / 1. The 3 identical pre-existing failures are test_radar_yahoo daily_closes; they are clock-dependent (datetime.now() floor vs 2026-08-31 fixtures).
- Massive: 18 = 18.
- Evidence-2 reconciliation: 31/31.
- CLI dry-run twice: identical, as above.
- Bug replay: REPRODUCED AND FIXED.
- git diff --check exit 0; models/migrations diff 0 lines; no trailing whitespace; py_compile ok.
- Artifact hashes are listed in return §8.
Evidence attribution:
- Fresh worker execution: all of the above gates and hashes, the HEAD-export baselines, the Evidence-2 manifest re-hash (19/19), read-only local-schema forensics, and the owner-authorized restore.
- Fresh but on a NON-authorized target: before the incident, the plan's focused gates that include DB-backed suites ran against local personal_apps (Task 1 80-pass, Task 4 156-pass, first baseline). Later product changes touch none of the 59 DB-backed tests.
- Accepted prior evidence (not re-measured): Evidence-2 cohorts and captured state, Authority-1 codes and MICs, release-A facts.
- Inference: the MySQL lock path is correct by construction and by fake-engine test, not by execution. Whether any of the 114 collides with an archived DE ticker is unknown, because the DE archive was never captured offline; the fix makes it moot.
Database safety:
- All B1 DB tests ran on per-test in-memory SQLite, with a fixture asserting the sqlite backend and an empty database name. personal_apps_radar_wt is not registered here, so the MySQL gates are unavailable.
- INCIDENT: I ran the plan's wider selector `pytest tests/ -k "radar and not destructive"` without first proving it excludes destructive suites. It bound the protected LOCAL development database personal_apps@localhost. The unguarded release-A F1 test test_radar_activity.py::test_the_migration_adds_and_removes_only_its_own_two_tables downgraded it to b3d9e1f5a274 and dropped radar_ingest_runs, radar_board_observations, radar_board_results and radar_board_namespaces; its finally-upgrade did not restore.
- I stopped the run and verified the damage read-only. With the owner's explicit authorization I ran only `PYTHONPATH=. FLASK_APP=app.py py -3.12 -m flask db upgrade` on local personal_apps. It is back at head b7e3f9c1a2d4 with 47 tables; the four tables are recreated EMPTY and their local rows are lost.
- No production, VPS, provider, network or DE/EUR-archive access. No real 114-row apply on any target.
Findings and limitations:
- F1: Task 4 names neither provider file, but removing the Quote default would have silently dropped every Finnhub quote. Finnhub's TypeError is swallowed at finnhub.py:92, and mapped polls also use provider.quotes(). Step 5's "every call site" is applied as one argument each in finnhub.py/twelvedata.py. Ruling requested.
- F2: the unmapped branch run_radar_ingest.py:461-465 remains. When a whole due batch is unmapped (reachable, because active_price_tickers is not filtered to mapped tickers), record_quotes now raises. The existing handler logs "radar US quote cycle failed" with error=True and stores nothing. This is fail-closed but noisy, where it used to write fabricated XNAS rows with measured extent 0. A quiet skip needs a run_radar_ingest.py change outside B1. Ruling requested.
- F3: the three self-review defects are fixed, as above.
- F4: test_radar_activity.py's migration test is still unguarded. The plan's wider selector is unsafe until it is wrapped in radar_disposable.require. Recommend a bounded fix.
- F5: the provider-owner recheck considers all mapped US primaries, not only active identities. Stricter and fail-closed; no effect with 0 delisted today.
- F6: rechecks run against a report made before the lock. DB-derived facts are re-read in the transaction; corporate-action pairing is not recomputed at apply time.
- Unavailable gates: the MySQL lock/apply path, the 59 DB-backed regression tests on an authorized target, and the plan's wider selector.
- B2 exclusions kept: no fetch, freshness, breakers or run table; no identity write, absence aging or delisting; no reassignment, MIC transition or provider presence; no rollback, scheduler or migration.
Actions taken:
- Files created and modified exactly as listed under Working tree.
- One owner-authorized restoring `flask db upgrade` on local personal_apps, plus read-only SELECTs for forensics.
- Explicitly NO stage, commit, push or deploy; no network fetch or provider call; no config, env, schema or migration-file change; no historical-row mutation; no importer run; no real 114-row apply; no production access.
Protected state:
- Release A was not accessed or changed.
- The existing 12,599 mapped US primaries and their history are untouched.
- The seven drift rows keep their MICs (preserve_existing_mic).
- The 26 non-common and 6 corporate-action identities are never safe candidates and are refused by apply.
- models.py and migrations have 0 diff.
- The Evidence-2 manifest re-hashes 19/19. Evidence-1 and Authority-1 artifacts and returns predate this work.
- Unrelated dirty files are preserved.
- Local personal_apps is at head, minus the lost rows of the 4 restored tables.
Subagents: none
Updated artifacts (local, uncommitted):
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/b-us-universe-b1-implement-1/
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/B-US-UNIVERSE-LEDGER.md (B1 status)
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/HANDOFF.md (B1 notice)
Requested Mastermind decision: Assess B1 and, if accepted for review, prepare one fresh independent Reviewer/QA prompt; do not implement fixes, commit, deploy or run the real apply. Also rule on F1 (provider call sites), F2 (noisy unmapped-branch refusal) and F4 (guard for the unguarded migration test), and record the local-database incident.
Next bounded action recommendation: One fresh independent Reviewer/QA inspects the complete candidate and evidence against the binding plan.

Read the current handoff, B ledger, all three rulings, plan, implementation return and evidence. Verify Git/artifact evidence, make the product ruling, and update repository continuity. Do not implement, commit, deploy or apply mappings yourself.
```
