# B-US-UNIVERSE-B1-REVIEW-1 — Independent Reviewer / QA return

Date: 2026-09-18 · Role: Reviewer / QA (fresh; not the Implementer of
B1-IMPLEMENT-1 or B1-CORRECTION-1; Claude Opus 5; no subagents) · Scope:
read-only review of the complete uncommitted B1 candidate including C1–C5.

## 0. Verdict

**ACCEPTED WITH NON-BLOCKING CARRIES.**

The complete candidate meets the B1 contract and all four owner decisions
(D1/D2/D3/D8). C1–C5 are each correct. No Critical, High or Medium defect
was found. Two Low findings are carried, neither blocking code acceptance:

| ID | Severity | Summary |
|---|---|---|
| F6 | Low | Corporate-action pairing/absence context is not recomputed under the lock, and the identity importer does not take the lock. The window is narrow, and it cannot produce a state that a legal serial order could not. |
| R1 | Low | The CLI writes `--report` only after the apply has committed. If that write fails, the inserts stay committed with no report file and no printed summary. |

Live MySQL/MariaDB execution of the lock and writer path, and the 59 DB-backed
regression tests, remain **unavailable**. Both returns honestly mark them
unavailable and do not overclaim.

## 1. Start gate (fresh, per-command `safe.directory`)

| Check | Observed |
|---|---|
| Workspace | `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts` |
| Branch | `codex/radar-selected-price-charts` |
| `HEAD` / `origin/main` / `origin/codex/radar-selected-price-charts` | `0fdad7327292cd3cd0b62dbe3f6b460873263053` (all three) |
| Index | empty (0 staged paths) |
| Status at start | 467 lines = 19 tracked modifications + 448 untracked. The ruling recorded 465; the difference is the Mastermind's own `B-US-UNIVERSE-B1-CORRECTION-1-RULING.md` and `B-US-UNIVERSE-B1-REVIEW-1-PROMPT.md`, written after that count. |
| Recent log | `0fdad73 docs(radar): record US USD-only removal` at the tip |
| Status after all verification runs | byte-identical to the start snapshot (467 lines). My runs changed nothing. |

Required reads were completed in the prompt's order: root `HANDOFF.md`
(newest notice), `WORKFLOW.md`, the B brief and ledger, Evidence-2 and
Authority-1 rulings, the B1 plan, the B1-IMPLEMENT-1 ruling and return, the
correction prompt, return and ruling, the release-A closure, and the newest
notices in `radar-design/HANDOFF.md`, `ASSIGNMENTS.md` and
`MASTERMIND-STATE.md`.

## 2. What was inspected

- **Every file in `b-us-universe-b1-correction-1/candidate-manifest.txt`,
  read in full.** 18 files:
  - `universe_directory.py`, `universe_reconcile.py`,
    `reconcile_radar_universe.py`, `seed_radar_universe.py`;
  - the `run_radar_ingest.py` change;
  - the `quotes.py`, `prices/__init__.py`, `finnhub.py`, `twelvedata.py` and
    `analysis_contract.py` diffs;
  - all four new test modules, the three modified test modules and the
    fixture.
- **The complete tracked diff and `correction-delta.patch`.** The delta's
  pre-images match the original B1 manifest (for example `44faf0d0…` and
  `6c9b34a2…`) and the HEAD blob of `run_radar_ingest.py` (`d03ed599…`). The
  ten files the correction did not touch still hash to the B1 manifest.
- **Supporting code outside the candidate.** It fixes the semantics the
  candidate depends on:
  - `models.py`: the `radar_instruments` unique constraint `(ticker, market,
    mic)` and the column collations;
  - `features/radar/universe.py` (`upsert_symbols`, `mark_delisted`);
  - `scheduling.record_fixed_poll`/`due_symbols_from`,
    `market_data.active_price_tickers`/`claim_post_close`;
  - `normalize_snapshot`;
  - `app.py` engine options: QueuePool and the MariaDB default isolation
    level;
  - every product `Quote(...)` and `record_quotes(...)` call site.
- **Evidence scripts and transcripts.**
  - Both `gate-transcript.txt` files and the correction `checkpoints.md`.
  - `run_db_free_gate.py` and `verify_against_evidence_2.py`, read in full
    before running them.
  - `reproduce_dry_run_report.py`. I read it and did **not** run it, because
    it writes into the correction evidence directory.

## 3. Findings (severity-ranked)

### F6 — Low (non-blocking): pairing/absence context is not rechecked under the lock; the importer bypasses the lock

**Evidence.**

- `universe_reconcile.py:391-396` pairs an unmapped listing with active,
  directory-absent identities. The reconciliation is computed before the
  lock (`reconcile_radar_universe.py:131-132`).
- Under the lock, `_recheck` binds each approval to that pre-lock
  reconciliation (`universe_reconcile.py:772-775`). It re-reads only these
  facts from the database:
  - identity existence, `delisted_at` and name (`:797-809`);
  - provider-symbol ownership (`:811-820`);
  - existing US rows (`:822-837`).
- The absent set, and the identity names and ETF flags that feed
  `_pair_key`, are not re-derived.
- The B1 plan requires the row to "remain in `safe_mapping_candidates`"
  inside the transaction (`B-US-UNIVERSE-B1-PLAN.md:240`). That is met for
  every database-derived component except pairing.
- The identity writer `universe.upsert_symbols` (`features/radar/universe.py:78-121`)
  and its only caller, the manual seed script
  (`scripts/seed_radar_universe.py:105-106`), take no named lock. So the
  comment "One named MySQL lock serializes every universe-maintenance
  write" (`universe_reconcile.py:51`) overstates: the lock serializes apply
  against apply only.

**Can the race make an approved candidate unsafe?** Only in a narrow sense.
For a pairing to emerge that the apply would miss, three things must hold:

1. an importer run must **commit** new or renamed or reactivated identities;
2. those identities must be absent from the reviewed directory `D0`, which in
   practice means a run with a newer directory;
3. that commit must land inside the apply command's own window. The window
   runs from its `load_current_state` read to its writer's first read, or
   falls during the writer's transaction, because every recheck is a
   consistent snapshot read and not a locking read.

An import that finishes before the apply command starts is **caught**: the
CLI re-reconciles fresh in every invocation. The newly paired symbol then
lands in `name_review`, its approval is refused, and the whole batch is
refused.

If the race does occur, the outcome is the same as a legal serial order,
"apply against `D0`, then import":

- only the lock-holding apply writes `radar_instruments`, so no
  `RadarInstrument` invariant can break (one mapped primary per ticker, no
  shared provider symbol);
- the new row is factually correct for the reviewed `D0` bytes;
- on the next reconciliation, the new counterpart symbol (unmapped, present
  in `D1`, sharing an issuer with the now-absent mapped symbol) routes to
  `name_review`/`corporate_action_pair`. D2's review opportunity survives on
  the counterpart.

**Does existing serialization prevent the race?** No. The named lock does not
cover the importer. What bounds the race today:

- `upsert_symbols` is reachable only from the manual seed script. No
  scheduler or job calls it, and no other product code writes
  `radar_ticker_universe` name, ETF or `delisted_at` (grep-verified).
- Each apply invocation reconciles afresh.
- The candidate's own identity, name and active state are re-read under the
  lock.

**Severity: Low; not blocking B1 code acceptance.**

**Smallest correction** (B2, or before any second apply, not now):

- inside the writer transaction, call `load_current_state(writer)` plus
  `reconcile(...)` over the same parsed rows, and bind approvals to that
  fresh reconciliation;
- make the seed/importer take `radar_universe_maintenance`;
- until then, narrow the `:51` comment to what it guarantees.

**Operational carry for the real 114-row apply:**

- no seed or import run concurrently with the apply;
- run a fresh dry-run immediately before the apply.

### R1 — Low (non-blocking): report is written only after commit, with no guard on its path

**Evidence.** `scripts/reconcile_radar_universe.py:134-137` runs these steps
in order:

1. `_apply(...)`, which commits inside `apply_approved_mappings`;
2. `write_report(args.report, payload)` (`:102-108`: open `PATH.partial`,
   then `os.replace`);
3. only then, `print(summarise(...))`.

**Reproduction by reasoning.** Pass `--report` into a directory that does not
exist, or whose disk is full. The transaction commits the approved inserts.
Then `open(f'{path}.partial', 'w')` raises `FileNotFoundError` or `OSError`.
The process exits with that traceback, having written no report file and
printed no inserted/skipped/refused summary. The operator cannot tell from
the command's output whether anything was committed.

**Impact.** This is audit-trail loss on the one production write B1 exists to
perform. It is recoverable:

- a rerun with the same manifest reconciles the rows as `in_sync` and reports
  them `skipped`;
- the rows carry `mapping_source` and `mapped_at`.

Hence Low.

**Smallest correction.** Either of:

- before `_apply`, prove the report destination (create the `.partial` file,
  or check the parent directory exists and is writable);
- print the apply summary to stdout before attempting the file write.

**Operational mitigation if carried:** use an existing, writable report
directory and tee stdout/stderr to a log.

No other actionable defect was found.

## 4. Mandatory adversarial questions

1. **Does the lock span a newly begun writer transaction?** Yes.
   - `named_lock` (`universe_reconcile.py:608-638`) holds one dedicated
     `engine.connect()` connection for the whole block, and runs
     `GET_LOCK(...,0)` and `RELEASE_LOCK` (in `finally`) on it.
   - The writer is a new `sa.orm.Session(bind=engine, autobegin=False)`,
     created **inside** the lock block (`:682-687`). Every recheck, the insert
     and flush, `_assert_invariants`, and the commit or rollback happen inside
     it (`:688-725`). The session closes before the lock's `finally` releases
     the lock.
   - With `autobegin=False`, a stray read outside the begun transaction
     raises.
   - There is no pre-lock snapshot reuse:
     - the writer's first consistent read, which fixes its REPEATABLE READ
       view, happens after `GET_LOCK` returns 1;
     - the CLI also ends its report transaction (`reconcile_radar_universe.py:154`);
     - under QueuePool, the lock connection stays checked out, so the writer
       necessarily gets a different pooled connection. This is inference; it
       was not executed on MySQL.
   - There is no connection-lifetime gap: commit is durable before release.
   - One residual, accepted for a seconds-long supervised run: lock liveness
     is not re-verified before commit. If the server killed the lock
     connection mid-apply, MySQL would free the lock.
2. **Can an approval be inserted or skipped without every recheck?** No.
   - Both non-refusing returns of `_recheck` — insert `(None, planned)` at
     `:829` and skip `(None, None)` at `:837` — are reachable only after all
     of these, in order:
     - the source/code/MIC rule (`:760-764`);
     - the per-source directory digest (`:766-770`);
     - binding to this run's safe candidate or `in_sync` listing, with equal
       source kind and code (`:772-781`);
     - for an insert, the planned row against the full contract row plus
       `isin is None` and the `mapping_source` length (`:783-795`);
     - identity exists, not delisted, name unchanged (`:797-809`);
     - no other mapped US primary owns the provider symbol (`:811-820`);
     - existing US rows: none for an insert, or exactly one row equal on
       ticker, market, venue, MIC, provider symbol, currency, primary flag and
       status for a skip (`:822-837`).
   - The single exception is the pairing context. See F6.
3. **Is refusal all-or-nothing for every ordering?** Yes.
   - The loop evaluates every approval without writing (`:690-712`).
   - Nothing is added to the session until after the loop.
   - `if refused or not pending: rollback` (`:714-715`).
   - Any exception rolls back and re-raises (`:723-725`).
   - `inserted` is assigned only after `commit()` (`:721-722`).
   - Duplicate approvals from a non-loader caller would fail the unique
     constraint or `_assert_invariants` and roll back.
   - The C2 tests pair every refusal with a valid companion (NEWC), so any
     partial insert would show.
4. **Can a name change, non-common listing, corporate action, unknown code or
   drift row reach the safe set or the apply?**
   - Not through the reconciler:
     - unknown code or missing identity: quarantined (`:304-316`);
     - mapped rows: conflict, drift, name review or `in_sync` only
       (`:338-364`);
     - unmapped rows: inactive, existing US row or taken provider symbol are
       conflicts; a pair is `name_review`; an uncorroborated derivative word
       is quarantined; D3 classes are `non_common`; D2 name drift is
       `name_review` (`:411-420`); only the remainder is safe.
   - Not through the apply: an approval for any of these is neither a
     candidate nor `in_sync`, so it is refused and the batch refused. An
     `in_sync` approval can only ever be skipped (`:826-828`).
   - Sole residual: a pairing that emerges inside the apply's own window
     (F6).
5. **Does the seed reject bad inputs before app or database access?** Yes.
   - `read_pair` (`seed_radar_universe.py:60-83`) runs at `:94`, before
     `from app import app` at `:102`.
   - Unknown basenames raise `SourceKindError` immediately.
   - Duplicate and missing kinds are reported together.
   - Both files are parsed, then `validate_pair` refuses overlap in either
     argument order.
   - The only module imported before validation is the pure
     `universe_directory`.
   - The tests' fake `app` module records the import itself, and `events == []`
     for every refusal.
6. **Does an all-unmapped batch make no provider call or quote write?** Yes.
   - `run_radar_ingest.py:452-463` resolves mapped primaries before any
     provider is constructed. With none due, it stamps
     `record_fixed_poll` for each due symbol and returns
     `{'skipped': 'no_mapped_instruments', 'stored': 0, 'error': False}`.
   - No provider is constructed, `record_quotes` is not called, no MIC is
     invented, and nothing is logged as an error.
   - The only `record_quotes` caller in product code binds every quote
     through `normalize_snapshot`, using the instrument's non-null MIC.
   - The scheduler wrapper reads the result with `.get()`, so the missing
     `attempted` key is harmless.
   - The stamp is fairness bookkeeping, as accepted in B-R15.
   - Pre-existing (not introduced here): in the post-close window,
     `claim_post_close` (`:436`) runs before mapped resolution. An
     all-unmapped due batch therefore consumes the session's single post-close
     shot. HEAD consumed it the same way, while storing fabricated `XNAS` rows
     instead.
7. **F6.** See §3. Judgment: Low, non-blocking, carried.
8. **Are the private `in_sync`/`name` fields sufficient and non-leaking, with
   the report unchanged?** Yes.
   - `SafeCandidate.as_dict()` omits `name`.
   - `Reconciliation.as_dict()`/`counts` iterate `COHORTS` only, so neither
     `in_sync` nor `source_digests` is serialized.
   - `build_report` serializes only `counts` and `as_dict()`.
   - The stored reports from both runs hash `c3cfb922…`. I verified the
     hashes; I did not regenerate the report.
   - `in_sync` is sufficient for a skip because it requires one mapped
     primary, the directory's MIC, an active identity and an unchanged name.
     The apply then demands the full 8-field contract row.
   - The name field is public directory text.
9. **Are the offline SQLite tests a faithful, bounded proof?** Yes, within
   stated limits, and not overstated.
   - The in-memory SQLite target shares one connection per thread, so those
     tests prove logic and atomicity, not isolation. The fixture docstring
     says so.
   - The C1 tests use a separate file database in WAL mode with explicit
     `BEGIN`, whose first read fixes the snapshot. That matches InnoDB
     consistent-read timing. The one engine difference is that SQLite
     refuses a stale snapshot's write upgrade where InnoDB would accept it.
     The tests assert the correct outcome, so either stale behaviour fails
     them.
   - The recorded RED replay shows both C1 tests failing on the rebuilt
     pre-correction code.
   - `named_lock` is proven only for statement order and connection
     identity, against a fake engine.
   - Both returns label live MySQL as unavailable or inference.
10. **Did the candidate preserve protected state?** Yes.
    - `models.py` and `migrations/`: 0 diff lines and 0 status lines.
    - The writer and every recheck filter `market == 'us'`. The DE/EUR lane
      is never read or written, and the tests prove an archived DE row
      stays byte-identical.
    - Existing US mappings: the writer only inserts. No update or delete
      exists in `apply_approved_mappings`, `_recheck` or
      `_assert_invariants`; the flush writes only the pending new rows.
    - The accepted cohorts reproduce exactly (§6).
    - Release A artifacts are untouched, and unrelated dirt is preserved
      (status identical before and after my runs).

## 5. C1–C5 assessment

- **C1 — PASS.**
  - The fresh writer session and transaction begin under the lock and end
    before release (`universe_reconcile.py:682-725`).
  - The CLI ends its report read first (`reconcile_radar_universe.py:154`).
  - The regression tests `test_a_snapshot_read_before_the_lock_cannot_satisfy_the_rechecks`
    and `test_the_cli_ends_its_report_read_before_it_asks_for_the_lock` pass
    now and failed in the recorded RED replay.
  - The lock-span guard test passes.
  - Live MySQL: unavailable.
- **C2 — PASS.**
  - One `_recheck` path serves insert and skip (`:745-837`).
  - A skip needs an exact 8-field row.
  - The six refusal tests plus the valid-rerun control pass.
- **C3 — PASS.**
  - Unmapped D2 routing comes before admission (`:411-420`), and there is an
    apply-time name recheck (`:804-809`).
  - The retained cohorts are unchanged: 31/31, verifier output
    byte-identical.
- **C4 — PASS.**
  - `read_pair` validates the complete pair before the app import
    (`seed_radar_universe.py:60-102`).
  - Upsert rows, their order and the timestamp are unchanged versus HEAD;
    first-file-wins is gone.
  - No caller of the old `load_rows` signature exists.
- **C5 — PASS.**
  - No provider call, no quote write, non-error `no_mapped_instruments`, and
    the poll stamp is kept (`run_radar_ingest.py:452-463`).
  - The mixed path is unchanged.

## 6. Original B1 contract assessment

- **Parser — conforms.**
  - Exact pinned headers (`universe_directory.py:94-97`).
  - Eight rules keyed by `(source_kind, code)`, with MIC, `mic_type` and
    `operating_mic` (`:75-88`); wrong-file and unknown codes resolve to
    `None`.
  - Per-file symbol and code columns.
  - Exact-bytes SHA-256, BOM recorded, exact row width.
  - Exactly one last-line `MMDDYYYYHH:MM` footer.
  - `Test Issue`/`ETF` restricted to Y/N; blank `ETF` refused; duplicates
    refused.
  - `validate_pair` refuses same-kind pairs and overlap.
  - The `Listing Exchange` alias is gone (sweep: rejection tests only).
  - Two documented, benign tolerances:
    - symbols outside `^[A-Z]{1,5}$` are *excluded* rather than failing the
      file, matching HEAD's importer and the accepted counts;
    - `.strip().upper()` accepts `y`/`n`.
- **Reconcile and dry-run — conforms.**
  - Pure and deterministic: every cohort is sorted, and no update, delete or
    delist action exists.
  - Evidence-2's 114/26/6/7/87 reproduce symbol-for-symbol, with the T1/T2/T3
    split and the MIC distribution exact.
- **Approval manifest — conforms.** It has an exact header and refuses
  duplicates, unknown MICs, MIC/code disagreement, wrong-file codes,
  malformed digests, bad symbols, and an empty manifest.
- **Hash binding — conforms.** The digest is checked per source kind at apply
  time.
- **Apply — conforms, with the F6 carry.**
  - Insert-only, serialized apply-versus-apply, one transaction,
    all-or-nothing, safe idempotent skip.
  - Naive-UTC `mapped_at`, the timezone-aware `now_utc` requirement, and
    `mapping_source` of at most 24 characters.
  - The CLI apply is reachable only with both flags, and has no force, yes,
    delete, rollback, fetch or scheduler path.
- **Fallback removal — conforms.**
  - `Quote.mic` is keyword-only with no default (`prices/__init__.py:70,90`).
  - `finnhub.py:81` passes `mic=None`; `twelvedata.py:110` passes
    `mic=mic_code`, which is used only for history in production.
  - `record_quotes` refuses a MIC-less snapshot (`quotes.py:43-50`).
  - `_stored_quote` requires an instrument (`:99-101`).
  - `quote_views_for` reads mapped primaries only (`:141-167`).
  - Every product `Quote(...)` passes an explicit MIC.
  - The only product `ELSE 'XXXX'` is the immutable migration
    `a4c8e2f19b70:32`.
- **IEXG — conforms.**
  - `KNOWN_US_MICS` now holds the eight confirmed listing MICs
    (`analysis_contract.py:45-46`).
  - `XNAS` stays `unknown`.
  - The Yahoo allowlist already carried `IEXG`.
- **Scope — conforms.**
  - No models, migration, schema, scheduler, B2 or A change.
  - `run_radar_ingest.py` changed only as C5 authorized.
  - No real apply, import, network, provider or production action.

## 7. Evidence (fresh reviewer execution)

Transcript: `radar-design/artifacts/b-us-universe-b1-review-1/review-transcript.txt`,
produced by `review_gates.sh` (run 2026-09-18T11:25:15Z). I also ran the same
gates once, individually, earlier in the session, with identical results.

| Command | Result |
|---|---|
| `py -3.12 ../radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py tests/test_radar_ingest_unmapped_batch.py -q -p no:cacheprovider --tb=short` (from `personal_apps`, `PYTHONDONTWRITEBYTECODE=1`) | **153 passed**, 0 failed, 0 skipped, 2 warnings (the seed's pre-existing `utcnow` deprecation); `db-free gate: application bound to b1-gate.invalid/b1_gate_no_database (unresolvable); no .env read` |
| Same, one module at a time | directory 46, reconcile 59, apply 44, ingest 4 |
| `py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/verify_against_evidence_2.py .` | **31/31 ok, `ALL OK`**. A second run wrote its JSON outside the repo; sha256 `830b464c…` = both accepted copies. |
| Candidate manifest re-hash (`check_manifest.py`) | **18 files, 0 mismatched** |
| Retained evidence hashes | both `dry-run-report.json` = `c3cfb922…`; both `evidence-2-reconciliation.json` = `830b464c…`; harness `4003b070…`; verifier `0f838ece…` |
| `git diff --check` | exit 0. The untracked new files have 0 trailing-whitespace lines, checked separately. |
| `git diff -- personal_apps/models.py personal_apps/migrations` | 0 lines; 0 status lines |
| Plan fallback sweep (`git grep --untracked`) | only the rejection tests and the archival migration `ELSE 'XXXX'` |

The harness was read before use. It replaces `dotenv.load_dotenv` before
anything imports `app.py`. `app.py` reads `DB_HOST`/`PERSONAL_DB_NAME` after
that call, so the bind is `b1-gate.invalid`. The verifier imports no `app`,
opens no database, and writes a file only when given a second argument.

## 8. Evidence attribution

- **Fresh reviewer execution (this session):**
  - every Git and status check;
  - the 153-test gate and the per-module counts;
  - the verifier: 31/31, output byte-identical;
  - the manifest and evidence re-hashes;
  - the diff check, models/migrations check and fallback sweep;
  - the delta pre-image hash comparison;
  - all code reading and static analysis.
- **Implementer / Mastermind evidence, reviewed but not re-executed:**
  - the real-CLI dry-run reproduction (2 `SELECT`s, byte-identical
    `c3cfb922…`); I verified only the stored hashes;
  - the RED replay (22 failed / 131 passed); I reviewed the transcript;
  - the B1 gates for `test_radar_quotes.py`, `test_radar_prices.py`,
    `ha1_unit/test_analysis_contract.py`, selected-price, HA1 and Massive.
    These modules are outside my permitted run list, so their new isolated
    tests were reviewed statically only;
  - the Evidence-2 capture and the Authority-1 facts (accepted prior
    evidence).
- **Inference:**
  - MySQL REPEATABLE READ read-view timing;
  - that QueuePool hands the writer a connection distinct from the lock's;
  - `GET_LOCK` server semantics;
  - F6's serialization-equivalence argument;
  - R1's failure path, which I derived by reasoning and did not execute.

## 9. Unavailable gates

- **Live MySQL/MariaDB.** No verified disposable `personal_apps_radar_wt`
  exists, so the named lock and fresh writer path have never run on the
  engine they target.
- **The 59 DB-backed regression tests** (universe 16, quotes 30,
  quotes_batch 13). Not run: they cannot reach the poisoned bind, and no safe
  target exists.
- **The wider selector.** Prohibited (B-R13); F4's migration test is still
  unguarded.
- **`test_radar_quotes.py`, `test_radar_prices.py`,
  `ha1_unit/test_analysis_contract.py`, `test_radar_quotes_batch.py`.** Not
  run by this reviewer; outside the prompt's four-module list.

None of these was substituted with an unsafe database.

## 10. Pre-existing debt and observations (not candidate findings)

- **`mapping_source` date.** It comes from `nasdaqlisted`'s creation time for
  every row (`reconcile_radar_universe.py:83`). The retained pair both read
  `2026-09-15T18:01`, so the stamp is exact for B1. B2 should either require
  equal creation times in `validate_pair` or stamp per source.
- **Unmapped symbols in the US quote rotation.** `active_price_tickers` is
  not filtered to mapped tickers, so unmapped symbols keep consuming cap
  slots (accepted in B-R15). The post-close claim precedes mapped
  resolution (§4 Q6). B2 could filter candidates to mapped primaries before
  scheduling and claiming.
- **Narrow source-inspection test.** `test_the_writer_never_updates_or_deletes_an_existing_row`
  inspects only `apply_approved_mappings`' own source. Manual review of
  `_recheck` and `_assert_invariants` found no update or delete.
- **Sample fixture.** `approved_safe_sample.csv` carries the real retained
  `nasdaqlisted` digest, but it is inert against the retained pair:
  - `BBBB` is absent;
  - `AAAA` is otherlisted/BATS;
  - `CCCC` is code Q/XNGS.
  Any accidental apply of it refuses the whole batch.
- **Other readers.** `price_status`, `move_since`, `moves_for` and
  string-identity `statuses_for` still read any US or legacy row by ticker.
  By plan scope only `quote_views_for` changed. None fabricates a MIC, and
  the measured fabricated-`XNAS` extent is zero.
- **Carried debt:** F4 (unguarded migration test), B-R13, and the seed's
  `datetime.utcnow()` deprecation.

## 11. Actions taken

- **Created:**
  - this return;
  - `radar-design/artifacts/b-us-universe-b1-review-1/review-transcript.txt`
    (sha256 `3b773327…`);
  - `radar-design/artifacts/b-us-universe-b1-review-1/review_gates.sh`
    (`249648b9…`);
  - `radar-design/artifacts/b-us-universe-b1-review-1/check_manifest.py`
    (`4631c7de…`).

  These evidence files hold no absolute path, host, credential or environment
  value (scanned).
- **Explicitly none of:**
  - a product or test edit, or any formatting change;
  - an edit to candidate evidence, ledgers, handoffs, roadmaps or existing
    returns/rulings;
  - the real mapping apply or an importer run;
  - access to the local `personal_apps` DB, production, the VPS, the network,
    a provider or an account;
  - credential or environment inspection;
  - a stage, commit, push, merge or deploy;
  - a clean, reset, checkout or discard;
  - subagents.
- **Bytecode.** Every Python run used `PYTHONDONTWRITEBYTECODE=1` and
  `-p no:cacheprovider`.

## 12. Protected state

- Release A: LIVE / VERIFIED / CLOSED at `0fdad73`, untouched.
- DE/EUR history and schema: untouched. The writer and rechecks are US-only,
  and models/migrations have 0 diff.
- Existing US mappings: the writer is insert-only. The seven drift rows are
  `preserve_existing_mic`; the 26 non-common and 6 corporate-action rows are
  never safe.
- Evidence-1, Evidence-2, Authority-1, the B1 and correction returns, and
  their evidence: hashes re-verified where pinned; unchanged.
- Unrelated dirt: preserved. Status is byte-identical to the start snapshot
  until my four review files; the final count is 471 lines = 467 + these 4.

---

## Mastermind return prompt

```text
You are Radar's Mastermind / Overview. Assess this independent Reviewer/QA return for assignment B-US-UNIVERSE-B1-REVIEW-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts; HEAD = origin/main = origin/codex/radar-selected-price-charts = 0fdad7327292cd3cd0b62dbe3f6b460873263053 (verified fresh at start and in the review transcript, 2026-09-18T11:25:15Z); index empty.
Working tree: the complete B1 candidate (18 manifest files) is uncommitted and unstaged; nothing is staged, committed or pushed. Status was 467 lines (19 tracked M + 448 untracked) at start and byte-identical after every verification run. Reviewer-owned additions, all untracked: radar-design/B-US-UNIVERSE-B1-REVIEW-1-RETURN.md and radar-design/artifacts/b-us-universe-b1-review-1/{review-transcript.txt, review_gates.sh, check_manifest.py}. Final count 471 lines.
Binding artifacts: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/{B-US-UNIVERSE-B1-PLAN.md, B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md, B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md, B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md, B-US-UNIVERSE-B1-CORRECTION-1-RULING.md, B-US-UNIVERSE-B1-REVIEW-1-RETURN.md, B-US-UNIVERSE-LEDGER.md, B-US-UNIVERSE-AUTHORITY-1-RULING.md, B-US-UNIVERSE-EVIDENCE-2-RULING.md}. Evidence: .../radar-design/artifacts/{b-us-universe-b1-implement-1/, b-us-universe-b1-correction-1/, b-us-universe-b1-review-1/}.

Objective and scope reviewed: read-only independent review of the complete uncommitted B1 candidate plus C1–C5, against the B1 plan, D1/D2/D3/D8 and the correction ruling. DB-free gates only. No fixes, no real apply, no database/network/provider/production access, no commit or deployment.
Verdict: ACCEPTED WITH NON-BLOCKING CARRIES.
Findings:
- F6 (Low, non-blocking).
  - What: pairing/absence context is not recomputed under the lock. universe_reconcile.py:391-396 pairs pre-lock; _recheck binds approvals to the pre-lock reconciliation at :772-775 and re-reads only identity, name, owner and US rows at :797-837. The importer (universe.upsert_symbols, universe.py:78-121, called only by seed_radar_universe.py:105-106) takes no named lock, so the ":51" comment "serializes every universe-maintenance write" overstates. The plan's "row remains in safe_mapping_candidates" inside the transaction (B1-PLAN.md:240) holds for every DB-derived component except pairing.
  - Impact: only an importer commit inside one apply command's own report-to-commit window escapes. An import finished before the apply command is caught, because each invocation re-reconciles. The outcome equals the legal serial order "apply against D0, then import": no RadarInstrument invariant can break (only the lock-holding apply writes it), and the counterpart surfaces in name_review on the next reconcile.
  - Smallest correction (B2 / later): re-run load_current_state(writer) plus reconcile inside the writer transaction, and make the seed take radar_universe_maintenance.
  - Operational carry for the real apply: no concurrent seed/import, and a fresh dry-run immediately before.
- R1 (Low, non-blocking).
  - What: reconcile_radar_universe.py:134-137 commits the apply, then writes --report (write_report :102-108), then prints the summary. A report-write failure (bad directory, full disk) leaves committed inserts with no report file and no printed outcome.
  - Impact: recoverable. A rerun reports the rows as skipped, and the rows carry mapping_source/mapped_at.
  - Smallest correction: prove the report destination (create PATH.partial or check the parent directory) before _apply, or print the apply summary before the file write.
  - Operational mitigation: an existing writable report directory plus a stdout/stderr log.
- No Critical, High or Medium findings.
C1–C5 assessment:
- C1 PASS. The writer Session(autobegin=False) is created and begun under the lock and ends before release (universe_reconcile.py:682-725); the CLI rolls back its report read at :154. The snapshot and CLI regression tests pass, and failed in the recorded RED replay. Live MySQL unavailable.
- C2 PASS. One _recheck path (:745-837) serves insert and skip; a skip needs an exact 8-field row; any refusal rolls back.
- C3 PASS. Unmapped D2 routing before admission (:411-420) and an apply-time name recheck (:804-809); cohorts unchanged.
- C4 PASS. read_pair (seed :60-83) runs at :94, before the app import at :102; missing, duplicate, unknown and overlap are refused in either order; upsert rows, order and timestamp are unchanged versus HEAD.
- C5 PASS. run_radar_ingest.py:452-463 constructs no provider and writes no quote, returns non-error no_mapped_instruments, and keeps the B-R15 poll stamp; the mixed path is unchanged.
F6 judgment: Low, non-blocking for B1 code acceptance, per the finding above. The existing named lock serializes apply against apply only, not import against apply. The race is bounded by three facts: the importer is manual-only, every apply invocation re-reconciles, and the candidate's own identity is re-read under the lock.
Original B1 contract assessment:
- Parser conforms: exact headers; eight (source_kind, code) rules with mic_type/operating_mic; footer, width, Y/N, duplicate and wrong-file checks; exact-bytes hash; BOM; validate_pair. The Listing Exchange alias is gone. Two benign tolerances: non-^[A-Z]{1,5}$ symbols are excluded as at HEAD, and y/n is uppercased.
- Reconcile conforms: pure, deterministic, never proposes an update or delete; 114/26/6/7/87 exact.
- Approval manifest and hash binding conform.
- Apply conforms, with the F6 carry: insert-only, all-or-nothing, idempotent, naive UTC.
- Fallback removal conforms: Quote.mic has no default; finnhub passes mic=None; twelvedata passes mic=mic_code; record_quotes refuses a MIC-less snapshot; _stored_quote requires an instrument; quote_views_for reads mapped primaries only.
- IEXG is in KNOWN_US_MICS.
- Scope: no models, migrations, B2 or A change.
Evidence:
- `py -3.12 ../radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py tests/test_radar_ingest_unmapped_batch.py -q -p no:cacheprovider --tb=short` → 153 passed (46/59/44/4), 0 failed, 0 skipped, 2 pre-existing utcnow warnings; poisoned bind confirmed.
- `py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/verify_against_evidence_2.py .` → 31/31 ALL OK; JSON output (written outside the repo) sha256 830b464c… = both accepted copies.
- Candidate manifest: 18/18 hashes match.
- Retained dry-run reports c3cfb922… ×2; harness 4003b070…; verifier 0f838ece….
- git diff --check exit 0; untracked new files have 0 trailing whitespace; models/migrations 0 diff lines; the fallback sweep finds only the rejection tests and the archival ELSE 'XXXX'.
- Delta pre-images match the B1 manifest and the HEAD blob.
- Status identical before and after verification.
Evidence attribution:
- Fresh reviewer execution: all of the above, plus full code reading and static analysis.
- Implementer/Mastermind evidence reviewed, not re-executed: the dry-run CLI reproduction (stored hashes verified only), the RED replay 22/131, and the B1 quotes/prices/HA1/selected-price/Massive gates (outside my permitted run list).
- Accepted prior evidence: Evidence-2 and Authority-1.
- Inference: MySQL REPEATABLE READ timing, distinct pooled lock/writer connections, GET_LOCK semantics, the F6 serialization equivalence, and R1's failure path (reasoned, not executed).
Unavailable gates: live MySQL/MariaDB lock and writer path (no verified disposable personal_apps_radar_wt); the 59 DB-backed regressions; the wider selector (B-R13, F4 unguarded); test_radar_quotes/prices/quotes_batch/ha1_unit not run by this reviewer. No unsafe substitute was used.
Actions taken: created the review return and three sanitized evidence files only. No product or test edit, no evidence/ledger/handoff edit, no apply or import, no DB/network/provider/production access, no credential or environment inspection, no stage/commit/push/deploy, no clean/reset/discard, no subagents.
Protected state: release A untouched (CLOSED at 0fdad73); DE/EUR history and schema untouched; existing US mappings untouched (insert-only writer); the 7 drift, 26 non-common and 6 corporate-action rows are never safe; accepted cohorts exact; unrelated dirt preserved.
Subagents: none
Updated artifacts:
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/B-US-UNIVERSE-B1-REVIEW-1-RETURN.md
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/b-us-universe-b1-review-1/review-transcript.txt
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/b-us-universe-b1-review-1/review_gates.sh
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/b-us-universe-b1-review-1/check_manifest.py
(all local, untracked, uncommitted)
Requested Mastermind decision: Accept the B1 code/review gate with F6 and R1 recorded as Low, non-blocking carries. Rule whether R1 gets a tiny bounded pre-apply correction or an operational mitigation. Record F6's apply-time operational rule and its B2 requirement.
Next bounded action recommendation: Record B1 review acceptance and put the uncommitted candidate's commit/integration decision to the owner. Keep the real 114-row apply separately gated, behind the F6 operational rule, the R1 ruling and, ideally, a disposable-MariaDB rehearsal of the lock+writer path. Do not authorize the real apply from this review.

Read the current handoff, ledger, all B1 rulings and returns, verify Git/artifact evidence, make the product ruling, and update repository continuity. Do not implement, commit, deploy, or apply mappings yourself.
```
