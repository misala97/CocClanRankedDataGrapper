# B-US-UNIVERSE-B1-CORRECTION-1 — Implementer return

Date: 2026-09-18 · Role: Implementer (Claude Opus 5, no subagents) · Status:
**C1–C5 CORRECTED — ONE UNCOMMITTED CANDIDATE, READY FOR MASTERMIND
VERIFICATION. NO REAL APPLY.**

## 0. Result

All five ruled defects are corrected test-first, each with regression tests
that fail on the pre-correction candidate and pass now. Nothing else in the
candidate changed.

- **Proof that the tests bite.** The pre-correction candidate was rebuilt
  byte for byte: every rebuilt file matches the SHA-256 the original B1 return
  pinned, and the ingest module matches its HEAD blob. The corrected tests
  were then replayed against it: **22 failed, 131 passed**. The 22 are
  exactly the new regression tests (C1 2, C2 6, C3 6, C4 6, C5 2).
- **The corrected candidate:** **153 passed** in the three B1 modules plus the
  focused C5 module, all through the DB-free harness.
- **Nothing the evidence pins moved.**
  - The Evidence-2 verifier passes 31/31, and its JSON output is
    byte-identical to the original B1 run (`830b464c…`).
  - The real CLI's dry-run report over the retained evidence is
    byte-identical to the accepted report (`c3cfb922…`), from 2 `SELECT`s.
- **Scope.** Ten B1 files the correction did not touch still hash to the B1
  manifest. `models.py` and `migrations/` have no diff.
- **No real apply**, database, network or provider access, commit or
  deployment.

## 1. Start gate (fresh, per-command `safe.directory`)

| Check | Observed |
|---|---|
| Workspace | `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts` |
| Branch | `codex/radar-selected-price-charts` |
| `HEAD` / `origin/main` / `origin/codex/radar-selected-price-charts` | `0fdad7327292cd3cd0b62dbe3f6b460873263053` (all three) |
| Index | empty |
| Dirt | 450 status lines, snapshotted before any edit and preserved (465 at the end: the 15 new entries are listed in §7) |
| Recent log | `0fdad73 docs(radar): record US USD-only removal` at the tip |
| Baseline, three B1 modules via the harness | **125 passed** (the ruling's number) |

Required reads were done in the prompt's order: root `HANDOFF.md`,
`WORKFLOW.md`, the B brief, ledger, B1 plan, B1 ruling, B1 return,
Authority-1 ruling, the release-A closure, and the newest notices in
`radar-design/HANDOFF.md`, `ASSIGNMENTS.md` and `MASTERMIND-STATE.md`. The
complete B1 diff was inspected before editing.

**Ruling validation.** Each of C1–C5 was checked against the code first
(`checkpoints.md` §1). All five were confirmed exactly as ruled. None was
contradicted, so no item was stopped.

## 2. Corrections

Full RED and GREEN output for each item is in `checkpoints.md`. The exact
change is `correction-delta.patch` (8 files, 23 hunks).

### C1 — fresh writer transaction under the lock

- **The fix.** `apply_approved_mappings` (`universe_reconcile.py:641`) no
  longer reads or writes through the caller's session. It uses that session
  only for its bind.
  - Once the lock is held, it opens its own
    `sa.orm.Session(bind=…, autobegin=False)` (`:685`) and begins one
    explicit transaction.
  - Every recheck, the insert, the flush, the invariant check and the commit
    or rollback run in that transaction.
  - The transaction ends inside the lock block, so the lock is released only
    after the commit or rollback.
  - With `autobegin=False`, a stray read outside that transaction raises
    instead of silently opening another one.
- **The CLI.** It now ends its report read transaction (`session.rollback()`,
  `reconcile_radar_universe.py:154`) before it asks for the lock.
- **Unchanged.** `named_lock` (MySQL `GET_LOCK`/`RELEASE_LOCK` on one
  dedicated connection, refusing any other bind) and the injected-lock seam.
- **Proof.** A new `snapshot_engine` fixture is a file SQLite database in WAL
  mode. It emits an explicit `BEGIN` on every transaction, so a
  transaction's first read fixes its snapshot: this is the REPEATABLE READ
  behaviour that matters.
  - A lock adapter commits a conflicting `XNCM` US row on its own connection
    as the lock is granted, standing in for the previous lock holder.
  - `test_a_snapshot_read_before_the_lock_cannot_satisfy_the_rechecks` covers
    the apply level; `test_the_cli_ends_its_report_read_before_it_asks_for_the_lock`
    covers the CLI.
  - **RED:** both failed. The stale snapshot missed the committed row, so the
    apply tried to insert a second US primary; SQLite then refused to promote
    the stale read (`database is locked`). MySQL would have accepted that
    insert.
  - **GREEN:** both refuse cleanly, and the only row left is the committed
    `XNCM` one.
  - Removing the CLI rollback alone fails the CLI test (`caller_in_transaction`
    `True`), so that half is load-bearing too.
  - A guard, `test_the_lock_is_held_until_the_writer_has_committed`, pins the
    lock span. It passes before and after the correction.
- **Test rewrite.** The two failure-injection tests now patch
  `sa.orm.Session.commit` on the class. They passed unchanged on the
  pre-correction code too, so they were not weakened.

### C2 — every safety check before an idempotent skip

- **One path for every approval.** `_already_applied` and
  `_apply_time_problem` are replaced by one `_recheck` (`:745`). Every
  approval runs through it before it may be inserted **or** skipped.
- **The checks, in order:**
  - the source/code/MIC rule;
  - the approval digest against the directory bytes this run parsed;
  - the current reconciliation binding: the symbol must be this run's safe
    candidate or its unchanged mapped listing, with the approval's source
    kind and code;
  - the planned row against the contract row;
  - the identity exists, is active, and keeps its name (see C3);
  - no other mapped US primary owns the provider symbol;
  - the existing US rows.
- **Skip only on an exact row.** A skip needs exactly one US row equal to
  the contract row on ticker, market, venue, MIC, provider symbol, currency,
  primary flag and status (`_contract_row` `:731` / `_differences` `:738`).
- **Refusal.** Any failure refuses the whole batch with zero inserts.
- **Binding the fresh-reconcile rerun.** The reconciler now records the
  listings it found fully in sync (`SyncedListing`, `:206`; the
  `Reconciliation.in_sync` field, `:240`). This is a non-report field, so the
  report is unchanged.
- **Tests** (companion candidate NEWC in each refusal, so any partial insert
  shows):
  - stale digest;
  - identity deleted;
  - identity delisted;
  - wrong venue;
  - the directory now disagrees (drift);
  - shared provider symbol;
  - the valid exact rerun beside a new insert.
- **RED:** 6 failed with `assert ('NEWC',) == ()` — SAFE skipped unchecked
  and NEWC inserted. The valid-rerun control passed.
- **GREEN:** all pass. The existing plan-reuse and fresh-plan rerun tests
  still skip.

### C3 — D2 for unmapped identities

- **Reconciler.** `_classify_unmapped` (`:411`) compares the stored identity
  name with the directory name before safe admission.
  - It uses the importer's own `_name_change` and the same predicate as
    mapped rows: every non-`none` kind goes to `name_review` with
    `review_no_mutation`, and never to the safe set.
  - The check sits after the D3 `non_common`/quarantine routing, which never
    maps anyway, and immediately before admission.
- **Apply time.** D2 is enforced again under the lock (`:804`). An identity
  renamed between the report and the apply is refused on both the insert and
  the skip path. The directory name travels as a non-report `name` field on
  `SafeCandidate` (`:143`) and `SyncedListing`.
- **Tests:** unmapped `first_token_changed`, `rename_same_first_token`,
  `security_description` and `cosmetic` drift, plus the rename between report
  and apply on both paths.
- **RED:** 6 failed — the renamed identity was a safe candidate, and was
  mapped or skipped.
- **Retained snapshot:** unchanged. There are no symbol exceptions: 114 / 26 /
  6 / 7 / 87, with the verifier output byte-identical.

### C4 — pair validation in the legacy seed path

- **The fix.** `seed_radar_universe.read_pair` (`:60`) runs in `main` before
  the application is imported (`:94`). It:
  - binds every argument by basename;
  - refuses unknown, duplicate and missing kinds together, in one
    `DirectoryValidationError`;
  - parses both files;
  - calls `validate_pair`.

  Overlap is refused whatever the argument order.
- **Unchanged.** Rows still reach the unchanged `universe.upsert_symbols` in
  argument order, with the same dicts and the same `utcnow()` timestamp.
  First-file-wins is gone, because a valid pair cannot overlap.
- **Tests.** A fake `app` module records the import itself (module-level
  `__getattr__`), `app_context()` and the stubbed upsert. The cases:
  - `only_nasdaq`, `only_other`, `nasdaq_twice`, `other_twice` and
    `unknown_file` refuse with no event at all;
  - overlap refuses in both orders;
  - a positive control shows a valid pair, in either order, is imported and
    upserted.
- **RED:** 6 `DID NOT RAISE`. **The importer was not run.**

### C5 — all-unmapped ingest batch

- **The fix.** `_run_us_price_cycle` now resolves mapped instruments before
  it constructs a provider (`run_radar_ingest.py:454`). When none are due, it
  returns `{'skipped': 'no_mapped_instruments', 'stored': 0, 'error': False}`,
  the shape of the other structured no-ops:
  - no provider is constructed or called;
  - `record_quotes` is never called;
  - nothing is logged as an error.
- **Removed.** The old unmapped `else` branch (`provider.quotes(due)` then
  `record_quotes`).
- **Unchanged.** The mixed-batch path.
- **Tests** (new module `tests/test_radar_ingest_unmapped_batch.py`, every
  seam stubbed, no database):
  - all-unmapped, for `finnhub` and `yahoo`: zero provider events, zero
    `record_quotes` calls, no WARNING+ log record;
  - a fairness test;
  - a mixed-batch control: only `MAPD` is requested and stored, under its own
    `XNMS`, and never `XNAS`.
- **RED:** `{'error': True} != {'error': False}`, `skipped None`, and a logged
  `ERROR … radar US quote cycle failed`.

## 3. Evidence

All under `radar-design/artifacts/b-us-universe-b1-correction-1/`. The final
transcript is `gate-transcript.txt`, run 2026-09-18T10:49:26Z by
`final_gates.sh`.

| Gate | Result |
|---|---|
| 3 B1 modules + C5 module, harness | **153 passed** (46 / 59 / 44 / 4), 2 warnings = the seed's pre-existing `utcnow` deprecation |
| Evidence-2 verifier | **31/31**, `ALL OK`; output `830b464c…` = the B1 original |
| Corrected CLI dry-run over retained evidence ×2 | 2 `SELECT`s each, 0 rows changed, both `c3cfb922…` = the accepted report |
| Pre-correction rebuild | 7/7 hash-exact; 10/10 untouched B1 files unchanged |
| RED replay against the rebuild | **22 failed / 131 passed** |
| `git diff --check` | exit 0 |
| `git diff -- personal_apps/models.py personal_apps/migrations` | 0 lines |
| Plan fallback sweep | unchanged: rejection tests plus the archival migration `ELSE 'XXXX'` |
| Unmapped provider request in the ingest loop | none |
| Trailing whitespace / `py_compile` | 0 / exit 0 |
| Original B1 evidence (10 hashes in B1 return §8) | identical |
| Evidence-2 `hash-manifest.json` | 19/19 identical |

The exact commands:

```text
cd personal_apps
py -3.12 ../radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py tests/test_radar_ingest_unmapped_batch.py -q -p no:cacheprovider --tb=short
cd ..
py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/verify_against_evidence_2.py . radar-design/artifacts/b-us-universe-b1-correction-1/evidence-2-reconciliation.json
bash radar-design/artifacts/b-us-universe-b1-correction-1/final_gates.sh <worktree> <new scratch dir>
```

Evidence file SHA-256:

| File | SHA-256 |
|---|---|
| `candidate-manifest.txt` (per-file hashes of the corrected candidate) | `a3af63953aa127a8bfe5234991875d36b86e34c41c220f3e45b6245107ec916d` |
| `checkpoints.md` | `3c6a563bbaa06fc4c32929fa9c49a2d0e15d44c138a3e8b681e2420b290c11d8` |
| `correction-delta.patch` | `a0b91f4a7ddb6396d8873fe336f1c33db2b7063230ee742a71f5c39fffb25646` |
| `dry-run-report.json` | `c3cfb922be0875ab1fe045a68aca8a82c564f78ffc0f0b6861a3e2a3485e5ed8` |
| `dry-run-summary.json` | `0ac94304ed5ec0df1c322522595306d9e7f776f1180e7e8b8782c7ae3e09baae` |
| `evidence-2-reconciliation.json` | `830b464cba0078307b0edb85eb5620072bfba0a79b6c483395b1855ecb48bd39` |
| `final_gates.sh` | `520614c86d3b9c3d380dc866530a03e6ea4aec00af76ee20f3344d408e450e6d` |
| `gate-transcript.txt` | `1fa58c5d1df6180fec945bf011369146e432b5c3bb6276b19655c31ee8a0cdf2` |
| `pre-correction-hashes.json` | `8f3d11bfb7e1ed2ea3b75073498976ecd1f93265350b2cef0b5dd2287efaa8a8` |
| `reconstruct_pre_correction.py` | `95acb213c8140713d6673b5e0a1135d7f8daf1cb0420f2a614d8a557ee2e3609` |
| `replay_red_against_pre_correction.sh` | `d6942005ad170d1fc72367f7baf364171593c89cd4d2be4cc137ec499e5be421` |
| `reproduce_dry_run_report.py` | `8529f5999535100987d6006f606dea79f27f13f2181eb27b4ef6c4bca9b7af83` |

No evidence file contains a user-profile path, host, credential or
environment value (scanned).

## 4. Evidence attribution

- **Fresh worker execution (this session):**
  - every RED/GREEN run, gate, count and hash above;
  - the rebuild and the replay;
  - the verifier and dry-run reruns;
  - the re-hash of the B1 and Evidence-2 artifacts;
  - the status comparison.
- **Accepted prior evidence, not re-measured:**
  - Evidence-2's captured state and cohort CSVs;
  - Authority-1's code and MIC authority;
  - the B1 return's pinned hashes (re-checked, not regenerated);
  - release-A facts.
- **Inference:**
  - that MySQL/MariaDB REPEATABLE READ behaves like the WAL snapshot model
    here. It is documented engine behaviour and was not executed;
  - that the production pool gives the lock and the writer separate
    connections. That follows from the defaults (`pool_pre_ping`,
    `pool_recycle` only, so QueuePool 5 + 10 overflow).

## 5. Database safety

- **The harness.** Every pytest run went through
  `radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py`
  (unchanged, sha256 `4003b070…`): dotenv is a no-op, and the application
  bound `b1-gate.invalid/b1_gate_no_database`. Every run printed the
  poisoned-bind confirmation.
- **Test databases.** The B1 tests use per-test in-memory SQLite. The C1
  tests use a file SQLite database under pytest's `tmp_path`, asserted to be
  sqlite inside `tmp_path`. The C4 and C5 tests replace every database seam.
- **The replay tree.** It is a `git archive HEAD` export in the scratchpad,
  outside the repository.
- **Not accessed:** local `personal_apps`, production, the VPS, the network
  and any provider. No schema action.
- **Not run:** the real 114-row apply, the importer, any broad selector,
  `test_radar_activity.py` or any migration test.
- **Not run by choice:** `tests/test_radar_daemon.py`. It contains
  DB-writing tests, and its only quote-cycle test returns at the
  closed-calendar gate before the changed code.

## 6. Findings and limitations

1. **C5 keeps the poll-stamp write — ruling requested.**
   - What happens: the all-unmapped branch makes zero provider calls and
     zero quote writes, but it still calls `scheduling.record_fixed_poll` for
     the due symbols. A mixed batch already stamps its unmapped symbols this
     way.
   - Why: `due_symbols_from` orders by oldest `next_due_at`, with a cap of 55
     for Finnhub. Unstamped unmapped symbols would head every cycle, so 55 or
     more of them would starve every mapped quote.
   - The test pins this. I read "zero writes" as zero quote writes.
   - If the Mastermind wants no poll-state write either, that needs a
     different starvation remedy. That is a ruling, not a one-line change.
2. **The C3 recheck under the lock goes beyond C2's literal list.**
   - C2 asked the apply to revalidate the "active/current identity". I
     included "still carries the name the directory lists", because D2
     forbids mapping a changed-name identity and C1 now makes a fresh read
     available.
   - It costs one column and one comparison.
3. **Non-report fields added to the reconciliation.**
   - `Reconciliation.in_sync`, `SyncedListing`, and `name` on `SafeCandidate`
     and `SyncedListing`.
   - None of them is serialized, so the report and the verifier output are
     byte-identical.
4. **B1 F6 remains.** Corporate-action pairing is not recomputed at apply
   time. It could shift only if an identity import ran between the report
   and the apply. Names are now rechecked; the absent set is not.
5. **Unavailable gates.**
   - The MySQL named-lock plus fresh-writer path, live. No verified
     disposable `personal_apps_radar_wt` exists here, and this return claims
     no MySQL proof.
   - The 59 DB-backed regression tests and the wider selector. B-R13 and F4
     are unchanged, and the migration test is still unguarded.
6. **Behaviour note.** On an exception, the apply now rolls back its own
   writer, not the caller's session. The CLI has already ended its report
   transaction by then.
7. **Pre-existing.** The seed's `dt.datetime.utcnow()` deprecation warning is
   now executed by a test. It was left unchanged, to keep the upsert call
   identical.

## 7. Actions taken

- **Modified (owned):**
  - `personal_apps/features/radar/universe_reconcile.py`;
  - `personal_apps/scripts/reconcile_radar_universe.py`;
  - `personal_apps/scripts/seed_radar_universe.py`;
  - `personal_apps/run_radar_ingest.py`;
  - `personal_apps/tests/test_radar_universe_directory.py`;
  - `personal_apps/tests/test_radar_universe_reconcile.py`;
  - `personal_apps/tests/test_radar_universe_mapping_apply.py`.
- **Created:**
  - `personal_apps/tests/test_radar_ingest_unmapped_batch.py`, the smallest
    focused C5 module;
  - this return;
  - `radar-design/artifacts/b-us-universe-b1-correction-1/`, 12 files;
  - the current-B1 status in `radar-design/B-US-UNIVERSE-LEDGER.md` and root
    `HANDOFF.md`.
- **Temporary.** One temporary edit, removing the CLI rollback for the
  load-bearing check, was restored immediately and verified.
- **Explicitly none of:**
  - stage, commit, push, merge or deploy;
  - clean, reset, discard or delete of repository content;
  - a database mutation outside test-created SQLite;
  - network or provider access;
  - a config, env, schema, migration, frontend, service or scheduler change;
  - the importer or the real apply;
  - subagents.

## 8. Protected state

- Radar A is untouched: live, verified and closed at `0fdad73`.
- Existing mappings, quote history, the seven drift rows, the 26 non-common
  identities and the six corporate-action identities are unchanged. The
  writer stays insert-only, and the reconciler emits the same cohorts.
- Historical DE/EUR data and schema are untouched. `models.py` and the
  migrations have no diff.
- Evidence-1 and Authority-1, the B1 return and its evidence, and the
  Evidence-2 artifacts are unchanged. The re-hash matched.
- All pre-existing dirt is preserved. The status delta is only the owned
  paths and this evidence.

---

## Mastermind return prompt

```text
You are Radar's Mastermind / Overview. Assess this Implementer return for assignment B-US-UNIVERSE-B1-CORRECTION-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts; HEAD = origin/main = origin/codex/radar-selected-price-charts = 0fdad7327292cd3cd0b62dbe3f6b460873263053 (verified fresh at start and in the final gate transcript, 2026-09-18T10:49:26Z); index empty.
Working tree: all pre-existing dirt preserved (450 status lines at start, 465 at the end). Correction-owned, uncommitted, unstaged:
- modified personal_apps/features/radar/universe_reconcile.py, personal_apps/scripts/reconcile_radar_universe.py, personal_apps/tests/test_radar_universe_directory.py, personal_apps/tests/test_radar_universe_reconcile.py, personal_apps/tests/test_radar_universe_mapping_apply.py (all untracked B1 files);
- modified personal_apps/scripts/seed_radar_universe.py (tracked, already B1-modified) and personal_apps/run_radar_ingest.py (tracked; newly modified);
- new personal_apps/tests/test_radar_ingest_unmapped_batch.py;
- new radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md and radar-design/artifacts/b-us-universe-b1-correction-1/ (12 files);
- current-B1 status only in radar-design/B-US-UNIVERSE-LEDGER.md and root HANDOFF.md.
The status delta versus the start snapshot is exactly run_radar_ingest.py, the new test module, the return and the evidence directory. Nothing staged, committed or pushed.
Binding artifacts: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/{B-US-UNIVERSE-B1-IMPLEMENT-1-RULING.md, B-US-UNIVERSE-B1-IMPLEMENT-1-RETURN.md, B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md, B-US-UNIVERSE-B1-PLAN.md, B-US-UNIVERSE-LEDGER.md, B-US-UNIVERSE-AUTHORITY-1-RULING.md}. Original evidence: .../radar-design/artifacts/b-us-universe-b1-implement-1/ (unchanged). Correction evidence: .../radar-design/artifacts/b-us-universe-b1-correction-1/ (checkpoints.md, gate-transcript.txt, final_gates.sh, correction-delta.patch, reconstruct_pre_correction.py, pre-correction-hashes.json, replay_red_against_pre_correction.sh, reproduce_dry_run_report.py, dry-run-report.json, dry-run-summary.json, evidence-2-reconciliation.json, candidate-manifest.txt).

Objective and authorized scope: Correct C1–C5 only in the existing uncommitted B1 candidate; no real apply, production access, commit or deployment.
Correction C1:
- apply_approved_mappings (universe_reconcile.py:641) uses the caller's session only for its bind. Once the lock is held it opens sa.orm.Session(bind, autobegin=False) (:685) and begins one explicit transaction; every recheck, insert/flush, invariant check and commit/rollback runs there, and the transaction ends inside the lock block.
- The CLI ends its report read transaction (session.rollback(), reconcile_radar_universe.py:154) before requesting the lock.
- named_lock (MySQL GET_LOCK/RELEASE_LOCK on one dedicated connection) and the injected-lock seam are unchanged.
- Proof: a WAL-mode file-SQLite fixture whose transactions hold a real snapshot, and a lock adapter that commits a conflicting XNCM US row as it grants the lock. The apply-level and CLI-level tests failed RED: the stale pre-lock snapshot made the apply insert, and SQLite raised "database is locked" on the stale promotion; MySQL would have accepted it. Both now refuse cleanly.
- Removing only the CLI rollback fails the CLI test (caller_in_transaction True). A guard pins that the lock is released only after commit.
- The failure-injection tests now patch Session.commit on the class; they passed on the pre-correction code too.
Correction C2:
- One _recheck (:745) replaces _already_applied/_apply_time_problem; every approval passes it before an insert OR a skip.
- Order: source/code/MIC rule; approval digest; current reconciliation binding (safe candidate, or the new non-report Reconciliation.in_sync / SyncedListing for the fresh rerun, with matching kind and code); planned row versus the contract row; identity exists, active, name unchanged; no provider-symbol collision; existing US rows.
- A skip needs exactly one US row equal to the contract on ticker, market, venue, MIC, provider symbol, currency, primary flag and status. Any failure refuses the whole batch with zero inserts.
- Tests: stale digest, identity deleted, identity delisted, wrong venue, directory-now-disagrees, shared provider symbol, valid exact rerun beside a new insert. RED: 6 × assert ('NEWC',) == () (SAFE skipped unchecked, NEWC partially inserted).
Correction C3:
- _classify_unmapped (:411) applies the importer's _name_change before safe admission, with the same predicate as mapped rows: every non-'none' kind goes to name_review/review_no_mutation. It sits after the D3 non_common/quarantine routing and before admission.
- D2 is enforced again at apply time under the lock (:804), on the insert and skip paths.
- Tests: unmapped first_token_changed / rename_same_first_token / security_description / cosmetic, and rename-between-report-and-apply ×2. RED 6.
- The retained snapshot is unchanged (114/26/6/7/87, no symbol exceptions).
Correction C4:
- seed_radar_universe.read_pair (:60) runs before the app import (:94). It binds by basename, refuses unknown/duplicate/missing kinds together, parses both files, and calls validate_pair; overlap is refused in either argument order.
- The upsert rows, their argument order and the timestamp are unchanged; first-file-wins is gone.
- Tests use a fake app module that records its own import, app_context and the stubbed upsert. only_nasdaq, only_other, nasdaq_twice, other_twice, unknown_file and overlap in both orders refuse with zero events; the positive control reaches import+upsert in either order.
- RED: 6 DID NOT RAISE. The importer was never run.
Correction C5:
- _run_us_price_cycle resolves mapped instruments before constructing any provider (run_radar_ingest.py:454). With none due it returns {'skipped': 'no_mapped_instruments', 'stored': 0, 'error': False}: no provider constructed or called, record_quotes never called, no error log. The old unmapped provider.quotes(due)/record_quotes branch is removed; the mixed batch is unchanged.
- The due symbols' poll attempts are still stamped, like unmapped symbols in a mixed batch, to avoid starvation. Ruling requested.
- New module tests/test_radar_ingest_unmapped_batch.py: finnhub+yahoo all-unmapped (zero provider events, zero record_quotes, no WARNING+), fairness, and a mixed-batch control (only MAPD stored, under XNMS). RED: error True, skipped None, logged "radar US quote cycle failed".
Evidence:
- All pytest runs via run_db_free_gate.py. `py -3.12 ../radar-design/artifacts/b-us-universe-b1-implement-1/run_db_free_gate.py tests/test_radar_universe_directory.py tests/test_radar_universe_reconcile.py tests/test_radar_universe_mapping_apply.py tests/test_radar_ingest_unmapped_batch.py -q -p no:cacheprovider --tb=short` → 153 passed (46/59/44/4), 0 failed, 0 skipped, 2 warnings (the seed's pre-existing utcnow deprecation). Baseline before the correction: 125 passed.
- `py -3.12 radar-design/artifacts/b-us-universe-b1-implement-1/verify_against_evidence_2.py .` → 31/31 ALL OK; its JSON output is byte-identical to the B1 original (830b464c…).
- Corrected CLI dry-run over the retained evidence ×2: 2 SELECTs, 0 rows changed, report c3cfb922… = the accepted report.
- Pre-correction candidate rebuilt: 7/7 files hash-exact to the B1 manifest / HEAD blob; 10/10 untouched B1 files unchanged.
- RED replay of the corrected tests against the rebuild: 22 failed / 131 passed (exactly the 22 regression tests).
- git diff --check exit 0; git diff -- personal_apps/models.py personal_apps/migrations = 0 lines; plan sweep unchanged; trailing whitespace 0; py_compile ok.
- The original B1 evidence (10 hashes) and Evidence-2 (19/19) re-hash identical.
Evidence attribution:
- Fresh worker execution: all runs, counts, hashes, the rebuild, the replay and the re-hashes above.
- Accepted prior evidence: Evidence-2 state and cohorts, Authority-1 MICs, the B1 return's pinned hashes (re-checked), release-A facts.
- Inference: that MySQL REPEATABLE READ matches the WAL snapshot model (not executed), and that the pool gives the lock and the writer separate connections (default QueuePool).
Database safety:
- Harness run_db_free_gate.py sha256 4003b070… (unchanged): dotenv disabled, application bound to b1-gate.invalid/b1_gate_no_database, confirmed on every run.
- Test databases: in-memory SQLite, a tmp_path file SQLite, and stubbed seams. The replay tree is a git-archive export in the scratchpad.
- No local personal_apps, production, VPS, network or provider access. No real apply, importer, broad selector, test_radar_activity.py or migration test. test_radar_daemon.py was deliberately not run (it has DB-writing tests).
Findings and limitations:
(1) C5 keeps the poll-stamp scheduling write (zero provider calls, zero quote writes) to prevent starvation; ruling requested if "zero writes" was meant to include poll state.
(2) The D2 name recheck under the lock goes beyond C2's literal list.
(3) Non-report fields: in_sync, SyncedListing, and name on SafeCandidate/SyncedListing; the report is byte-identical.
(4) B1 F6 remains: corporate-action pairing is not recomputed at apply time.
(5) Unavailable: the live MySQL lock+writer path (no verified disposable personal_apps_radar_wt; no MySQL proof claimed), the 59 DB-backed tests, the wider selector; F4/B-R13 unchanged.
(6) On an exception the apply rolls back its own writer, not the caller's session.
Actions taken: the files listed under Working tree only. Explicitly no stage, commit, push, deploy, clean, reset or delete; no network, provider, config, env, schema, migration, frontend, service or scheduler change; no historical-row mutation; no importer run; no real apply; no subagents.
Protected state: release A untouched (LIVE/VERIFIED/CLOSED at 0fdad73). Existing mappings, history, the 7 drift, 26 non-common and 6 corporate-action rows unchanged (insert-only writer; identical cohorts). DE/EUR data and schema untouched; models/migrations 0 diff. Evidence-1/2, Authority-1 and the original B1 return and evidence unchanged. Unrelated dirt preserved.
Subagents: none
Updated artifacts (local, uncommitted):
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/B-US-UNIVERSE-B1-CORRECTION-1-RETURN.md
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/artifacts/b-us-universe-b1-correction-1/
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/B-US-UNIVERSE-LEDGER.md (current B1 status)
- C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/HANDOFF.md (current B1 notice)
Requested Mastermind decision: Verify only the bounded correction and, if accepted, prepare one fresh independent Reviewer/QA prompt; do not implement further fixes, commit, deploy or run the real mapping apply.
Next bounded action recommendation: One fresh independent Reviewer/QA inspects the complete B1 candidate plus correction evidence.

Read the current handoff, ledger, B1 ruling, original return, correction return and evidence. Verify Git/artifact evidence, make the product ruling, and update repository continuity. Do not implement, commit, deploy or apply mappings yourself.
```
