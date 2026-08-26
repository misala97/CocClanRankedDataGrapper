# Task 6 Review: Backfill the buckets the old rollup truncated

Reviewer: independent audit pass, mutation-tested against the real local dev
MySQL database. Worktree confirmed clean (`git status --short` empty) at
start and end of review.

## Spec compliance

| Requirement | Status | Notes |
|---|---|---|
| Create `personal_apps/scripts/backfill_radar_buckets.py` | ✅ | |
| Create `personal_apps/tests/test_radar_backfill.py` | ✅ | |
| `repair(apply=False, ticker_prefix=None) -> dict` signature | ✅ | Matches exactly. |
| `ticker_prefix` not reachable from CLI | ✅ | `main()` calls `repair(apply=args.apply)`; `argparse` only defines `--apply`. |
| Fixtures namespaced `ZZBF...`, exact-identity cleanup, no broad `LIKE 'ZZ%'` | ✅ | `_wipe()` uses `ticker.in_(TICKERS)` and `channel == CHANNEL`, both exact. Verified empirically: 0 `ZZBF%` bucket rows and 0 `zzbf-backfill-test` post rows remain after the full suite runs. |
| Every `repair()` call in tests passes `ticker_prefix='ZZBF'` | ✅ | Confirmed by reading all 4 test bodies. |
| Dry-run is a genuine DB-level rollback | ✅ | Confirmed by mutation (see Teeth Audit #1) and independently by direct DB query after a dry run. |
| Apply is idempotent (`repaired == 0` on second call) | ✅ | Confirmed by test and by mutation (#2, #9). |
| All four score columns cleared on repair | ✅ | `expected`, `variance`, `mention_z`, `baseline_days` all set to `None`; each individually pinned by mutation (baseline_days shown in #2, others follow the same code shape). |
| Stale-cleanup keys on ANY of the four columns, not just `mention_z` | ✅ | `sa.or_(...isnot(None)...)` over all four; confirmed by mutation #3. |
| `status` and `source_config_version` preserved; repair never restamps current generation | ✅ | Neither field is ever assigned in the repair path; confirmed by mutation #6 (adding a restamp line breaks the pinned assertion). |
| Absence never a zero | ✅ | Score columns set to `None`, never `0`. `float(engagement or 0)` is defensive-only: `radar_posts.score`/`num_comments` are `nullable=False` (confirmed in `models.py`), so `SUM(p.score + p.num_comments)` can never actually be NULL for a matched group — this branch is unreachable in practice, not a live "silent zero" risk. |
| Equal `high_confidence_count` doesn't block other repairs | ✅ | Confirmed by test 3 and by mutation #7 (short-circuiting on `high_confidence_count` alone breaks the test). |
| `int()`/`float()` at the query boundary for Decimal | ✅ (with a documentation nit) | Empirically, on this driver (`mysql+pymysql`), `COUNT(*)` / `COUNT(DISTINCT ...)` already come back as native Python `int`, and only `SUM(...)` comes back as `decimal.Decimal`. The `int()` calls on the three COUNT-derived values are harmless no-ops; `float(engagement or 0)` is the one call that is actually load-bearing. The inline comment ("COUNT and SUM come back Decimal from both MySQL and MariaDB") is technically imprecise for COUNT under this driver, but this exact phrasing is a pre-existing house convention (identical comment in `features/radar/journal.py:204`), so it's not something this task introduced, and the redundant `int()` calls cause no harm. Minor finding below. |
| Both MySQL 8 and MariaDB accept every query | ✅ (MySQL 8 verified directly; MariaDB verified by reasoning only) | `_TRUTH` uses only `DATE_ADD`, `DATE_FORMAT`, `FLOOR`, `MINUTE`, `COUNT`, `COUNT DISTINCT`, `SUM`, `GROUP BY` — no `CAST(...AS JSON)`, no MySQL-8-only syntax (window functions, CTEs). Bucket-flooring math verified correct at every 15-minute boundary (minutes 0,14,15,16,29,30,31,44,45,46,59) directly against the real MySQL 8 dev DB. MariaDB itself was not available to test directly in this environment — flagged as ⚠️ below. |
| Every datetime naive UTC | ✅ | No `datetime.utcnow()` or any datetime construction in the script at all; all datetimes flow from the DB (`created_utc`, `bucket_start`) or are literal test fixtures. |
| SQL NULL vs Python `None` handled correctly | ✅ | Score-column checks use `.isnot(None)` throughout (generates `IS NOT NULL`), never a bare `!=`. `status` is `nullable=False` so no NULL-vs-`!=` hazard there either. |
| Protected files untouched | ✅ | `git diff 449e9fb..d11ccb5 --stat` shows exactly the two task files, +414/-0, nothing else. |

Nothing was found in the diff that exceeds what the brief asked for — the only
addition beyond a literal transcription of the brief's Step 2 script is the
`_unchanged()` / `_FLOAT_FIELDS` / `math.isclose` tolerance, which is called
out explicitly in the report as a deviation.

### On the reported deviation (float tolerance for `distinct_text_ratio` / `engagement_weighted_count`)

Verified directly against the real dev DB: writing `2/3` into
`distinct_text_ratio` (a MySQL `FLOAT` column, confirmed via `SHOW COLUMNS`)
and rereading in a fresh transaction gives back a value that differs from the
written double by roughly 3.3e-7 relative — confirmed `==` is false and
`math.isclose(..., rel_tol=1e-6, abs_tol=1e-9)` is true. The reasoning is
sound and the tolerance is appropriately sized (comfortably above float32
epsilon, several orders below any realistic true difference in the buckets
this repairs — corpus volumes here are tens to low hundreds of mentions per
bucket, not the thousands that would be needed to make two distinct
`n_hashes/n_high` fractions collide within 1e-6 relative). It does not appear
to risk masking a genuine repair: `distinct_text_ratio` is already the
`min(old, truth)` of a lower-bound estimate under a documented partial-repair
model, so a difference small enough to fall inside this tolerance is
immaterial to begin with. `engagement_weighted_count` is confirmed (by
reading `features/radar/ingest.py:178,192`, `engagement=float(raw.score +
raw.num_comments)`) to always be an integer-valued float in production, so
the tolerance is inert there in practice, applied only for type-consistency
as the report states. This deviation is correctly identified, correctly
scoped, and does not weaken the idempotency guarantee it was added to fix —
without it, the literal brief code would in fact never converge to
`repaired == 0` on a second apply, which I did not need to separately
mutation-test since the deviation's absence *is* effectively mutation #9's
scenario in spirit (the brief's own `==` would misbehave the same way an
`if False: continue` does, for any bucket whose `distinct_text_ratio` isn't
exactly float32-representable).

## Teeth audit

All mutations were applied directly to
`personal_apps/scripts/backfill_radar_buckets.py`, the named test run, output
captured, then the file was reverted to the original and a full 4/4 pass of
`test_radar_backfill.py` was confirmed before moving to the next mutation.
`git status --short` was empty at the end of the whole session.

| # | Assertion under test | Mutation | Result | Verdict |
|---|---|---|---|---|
| 1 | Dry-run leaves every DB field unchanged | Replaced the dry-run `db.session.rollback()` with `db.session.commit()` | `test_dry_run_...`: `assert row.high_confidence_count == 1` → `AssertionError: assert 2 == 1` | **Teeth confirmed** |
| 2 | All four score columns cleared on repair | Dropped `bucket.baseline_days = None` | `test_apply_...`: `assert row.baseline_days is None` → `AssertionError: assert 10 is None` | **Teeth confirmed** |
| 3 | Stale predicate keyed on any of 4 columns | `sa.or_(expected/variance/mention_z/baseline_days)` → `mention_z.isnot(None)` alone | `test_stale_scores_...`: `assert dry['stale_scores'] == 1` → `AssertionError: assert 0 == 1` | **Teeth confirmed** |
| 4 | `ticker_prefix` scopes the repair loop | Removed `if ticker_prefix and not tk.startswith(ticker_prefix): continue` | `test_dry_run_...`: `assert report['examined'] == 1` → `AssertionError: assert 211 == 1` (211 = the real dev DB's 210 real buckets + the test's 1 fixture). Confirmed safe: the dry-run rollback was untouched by this mutation, so no real row was actually written. | **Teeth confirmed** |
| 5 | `ticker_prefix` scopes the stale-score query | Removed the `if ticker_prefix: stale = stale.filter(...)` block entirely | **All 4 tests still passed.** Verified by direct read-only query first: the real dev DB currently has **0** non-`ZZBF` rows matching `status != 'ok' AND (any score column is not null)`, so the unfiltered global stale-count happens to equal the ZZBF-only count (1) by coincidence of current data, not because scoping was enforced. | **Teeth NOT confirmed — see Finding (Important) below** |
| 6 | Repair never restamps `source_config_version` to the current generation | Added `bucket.source_config_version = source_config_version()` before the count writes | `test_apply_...`: `assert row.source_config_version == 'old-gen-2'` → `AssertionError: assert 'fc1a0ee4cab51d65' == 'old-gen-2'` | **Teeth confirmed** |
| 7 | Equal `high_confidence_count` doesn't short-circuit other columns | Changed the `all(_unchanged(...))` guard to check `high_confidence_count` only | `test_equal_high_confidence_count_...`: `assert report['repaired'] == 1` → `AssertionError: assert 0 == 1` | **Teeth confirmed** |
| 8 | An `ok` row's legitimate score is never touched by the stale pass | Dropped `RadarBucketSource.status != 'ok'` from the stale filter | `test_stale_scores_...`: `assert dry['stale_scores'] == 1` → `AssertionError: assert 2 == 1` | **Teeth confirmed** |
| 9 | Second apply is idempotent | Replaced the whole `all(_unchanged(...))` guard with `if False: continue` | `test_apply_...`: `assert second['repaired'] == 0` → `AssertionError: assert 1 == 0` | **Teeth confirmed** |
| bonus | (report's own disclosed edge case) | Removed only the *inner* `if apply and stale_count:` guard, leaving the outer `if apply: commit() else: rollback()` intact | All 4 tests passed — the outer rollback alone still protects a dry run even with the inner guard gone. | Matches the report's own honest disclosure exactly; not a new finding, confirms the report was truthful about this nuance rather than papering over it. |

**Score: 8 of 9 distinct protections tested have confirmed teeth. One
(`ticker_prefix` isolation specifically on the stale-score query) passes
today only because the local dev database happens to hold zero real
non-`ZZBF` rows matching the stale predicate — it is not actually pinned by
the test suite.**

## Findings

### Important

**1. `ticker_prefix` isolation on the stale-score query has no working test — it passes by environmental luck, not by proof.**
`personal_apps/tests/test_radar_backfill.py` (the `test_stale_scores_clear_on_any_column_and_only_for_non_ok_status` test, ~L206-241) never exercises a scenario where removing `personal_apps/scripts/backfill_radar_buckets.py:142-144` (`if ticker_prefix: stale = stale.filter(...)`) would be caught. It happens to pass today purely because this specific dev DB currently has 0 real rows matching `status != 'ok' AND any-score-column-not-null` outside `ZZBF`. If that ever changes (which is plausible — this is exactly the population the production run is meant to find and clear), a future accidental regression of this filter would go undetected by the suite and, on `--apply`, would bulk-clear real score columns on arbitrary tickers via `stale.update(...)` (`backfill_radar_buckets.py:170-173`) — precisely the "broad sweep touches real data" failure mode the brief calls out as having been caught twice already, just relocated from test fixtures to the stale-score query.
*Failure scenario*: a later refactor drops or narrows the `ticker_prefix` filter on the stale query (e.g. while "simplifying" the two near-duplicate filter blocks); the test suite stays green because this DB has no matching non-`ZZBF` rows; the change ships; the next environment (or this one, once real stale rows exist) has its real `expected`/`variance`/`mention_z`/`baseline_days` silently cleared on `--apply` for tickers nobody intended to touch.
*Fix*: add a deterministic, data-independent assertion, e.g. in the same test: `assert backfill.repair(apply=False, ticker_prefix='ZZNOPE')['stale_scores'] == 0` right after asserting `dry['stale_scores'] == 1` with `ticker_prefix='ZZBF'`. This proves the filter actually restricts the stale query without depending on what else happens to be in the database — with the mutation from row 5 above, this exact assertion would correctly fail (`assert 1 == 0`, since an unscoped query still finds the `ZZBF4` fixture regardless of which prefix string was passed).

### Minor

**2. Comment overstates COUNT's Decimal-ness (documentation nit, not a functional bug).**
`personal_apps/scripts/backfill_radar_buckets.py:83-85` — the comment "COUNT and SUM come back Decimal from both MySQL and MariaDB" is empirically only true for `SUM`; `COUNT(*)`/`COUNT(DISTINCT ...)` already return native Python `int` via this app's `mysql+pymysql` driver (confirmed directly against the real dev DB). The `int()` calls on `n_high`/`n_authors`/`n_hashes` are therefore harmless no-ops rather than load-bearing conversions; only `float(engagement or 0)` (over a `SUM`) is actually necessary. This exact phrasing is a pre-existing house convention already used verbatim in `features/radar/journal.py:204`, so it isn't something this task invented, and it causes no incorrect behavior — flagging only because a future reader might infer COUNT needs defending against `TypeError` in a context where it doesn't. No fix required; optional: soften the comment to "SUM (and, defensively, COUNT) come back Decimal-shaped from some drivers."

**3. `_TRUTH`'s computed `bucket_start` (`bs`) comes back as a Python `str`, not a `datetime`, relying on implicit DB-side coercion for the ORM `filter_by(bucket_start=bs, ...)` lookup.**
Confirmed empirically: `db.session.execute(_TRUTH).all()` yields `bs` as e.g. `'2026-08-22 20:30:00'` (type `str`), because `sa.text()` without explicit `.columns(...)` typing does not apply a `DateTime` type processor to a computed `DATE_ADD(...)` expression. The subsequent `RadarBucketSource.query.filter_by(..., bucket_start=bs, ...)` (`backfill_radar_buckets.py:102-103`) works correctly against MySQL 8 today — confirmed by the real Gate-3-style dry run finding 165 genuinely understated rows out of 210 examined — because MySQL implicitly coerces the string literal for comparison against the `DATETIME(6)` column. This is functionally fine on the tested engine, but it is implicit rather than explicit, and MariaDB parity for this specific ORM-level string-to-datetime comparison was not directly testable in this environment (no MariaDB instance available here). ⚠️ Not fully verified on MariaDB. Suggested low-cost hardening (optional, not blocking): parse `bs` with `datetime.strptime(bs, '%Y-%m-%d %H:%M:%S')` right after the query, or add `.columns(bs=sa.DateTime)` to `_TRUTH`, to remove the dependency on implicit coercion entirely.

## ⚠️ Cannot verify from diff

- **MariaDB execution of `_TRUTH`** was not directly tested (no MariaDB instance in this environment). The SQL uses only portable functions (`DATE_ADD`, `DATE_FORMAT`, `FLOOR`, `MINUTE`, standard `COUNT`/`COUNT DISTINCT`/`SUM`/`GROUP BY`) with no MySQL-8-only or JSON-cast syntax, so parse-validity risk looks low by inspection, but this is reasoning, not a run.
- **Production-scale idempotency** (the real 399-row stale count mentioned in the brief) was not exercised — Gate 3's dry run against local dev data found `0` stale rows and `165` understated rows; the actual `--apply` run against production is explicitly deferred to Michi per the brief and the report, and this review did not run it either.

## Other observations (not findings)

- Reading `features/radar/scoring.py:255` (`'text_ratio': min((r.distinct_text_ratio for r in rows), default=1.0)`) confirms the repair script's `min(old, truth)` choice for `distinct_text_ratio` is consistent with how the rest of the system already treats this column (lower = more conservative), not an ad hoc choice specific to this script.
- `radar_mentions.post_id` really does carry `ON DELETE CASCADE` at the database level (confirmed via `information_schema.REFERENTIAL_CONSTRAINTS`), so the test's `_wipe()` relying on cascade rather than a separate `RadarMention` delete is correct, not merely asserted in a comment.
- Bucket-flooring math (`DATE_ADD(DATE_FORMAT(...), INTERVAL FLOOR(MINUTE(...)/15)*15 MINUTE)`) was independently verified correct at every quarter-hour boundary in the hour (:00, :14/:15/:16, :29/:30/:31, :44/:45/:46, :59) against the real MySQL 8 dev database.
- No stray fixture rows (`ZZBF%` tickers, `zzbf-backfill-test` channel) were left in the real dev database at the end of this review; a probe row (`ZZBFPROBE`) created solely to verify float round-tripping behavior was inserted and deleted within the same script invocation and confirmed absent afterward.

## Verdict

**APPROVED.**

The implementation is a faithful, correct transcription of the brief's Step 2
script, with one well-reasoned and correctly-scoped deviation (float
tolerance) that the report called out honestly and I independently
reproduced. Eight of nine distinct safety/correctness protections have
confirmed teeth via live mutation testing against the real dev database, the
worktree is clean, and no protected files were touched. The one gap found —
`ticker_prefix` isolation on the stale-score query lacking a
data-independent test — is a real test-coverage gap worth fixing, but it is
a latent risk in the *test suite*, not a defect in the shipped script: the
production code itself correctly scopes both the repair loop and the stale
query by `ticker_prefix` when one is supplied, and the CLI never supplies
one broader than "all," which matches the brief's intent for the production
run. I'm marking this Important rather than blocking because fixing it is a
small, mechanical test addition (shown above) that does not require touching
`backfill_radar_buckets.py` itself.

## Fix round 1 re-review

Scoped re-review of commit `8b0a07d` (`d11ccb5..8b0a07d`) against the two
findings raised above: the Important test-coverage gap and Minor #3
(datetime coercion). Base commit `d11ccb5` was already reviewed and approved
above; not relitigated here.

### Fix 1 (Important) -- `ticker_prefix` scoping test, teeth verified independently

Re-ran the exact teeth experiment myself rather than trusting the report's
transcript:

1. `git status --short` at the worktree root was clean before starting.
2. Deleted the `if ticker_prefix: stale = stale.filter(...)` block at
   `personal_apps/scripts/backfill_radar_buckets.py:152-154` (post-fix line
   numbers).
3. `python -m pytest tests/test_radar_backfill.py -v` (from `personal_apps/`):
   `test_stale_scores_clear_on_any_column_and_only_for_non_ok_status` FAILED
   with `assert 1 == 0` at the new assertion line, 3 passed / 1 failed --
   matches the report's transcript exactly.
4. Reverted the mutation completely (re-added the `if ticker_prefix:` block,
   verbatim).
5. Re-ran the same test file: 4/4 passed.
6. `git status --short` (worktree root) and `git diff --stat`: both empty --
   no leftover mutation.

The new assertion has real teeth and does not pass vacuously.

**Sentinel prefix check** -- `grep -n "ZZNOPE\|ZZBF" tests/test_radar_backfill.py`
confirms `ZZNOPE` appears exactly once, at the new assertion line. The
file's `TICKERS` tuple (`ZZBF1`..`ZZBF5`) is the only thing the `clean`
fixture creates or deletes (`RadarBucketSource.ticker.in_(TICKERS)`,
lines ~29-37); `ZZNOPE` is never created and never targeted by the cleanup
delete, so it isn't a row the fixture happens to also own. This was also
confirmed empirically: with the shipped fix in place, the real dev database
(which does hold unrelated non-`ZZBF` rows -- e.g. the `stale_scores`
production-shaped data) returns `0` for `ticker_prefix='ZZNOPE'`, i.e. no
real ticker in this dev DB happens to start with that string either.

### Fix 2 (Minor #3) -- datetime conversion, verified against the live query

Ran the `_TRUTH` query directly against the dev database (bypassing
`repair()`) to inspect the raw driver return type and format independently
of the fix's own assumptions:

```
>>> rows = db.session.execute(_TRUTH).all()
>>> repr(rows[0].bs), type(rows[0].bs)
('2026-08-22 20:30:00', <class 'str'>)
```

459 rows, all plain `str` values in exactly `%Y-%m-%d %H:%M:%S` form, zero
fractional-seconds suffixes anywhere. This is not a coincidence of the
sample: `DATE_FORMAT(p.created_utc, '%Y-%m-%d %H:00:00')` has no `%f`
specifier, so MySQL's implicit string-to-datetime cast for the outer
`DATE_ADD(...)` gets fsp=0 from the literal itself, regardless of
`bucket_start`'s own `MYSQL_DATETIME(fsp=6)` column definition (confirmed at
`personal_apps/models.py:638,680`) and regardless of the interval unit
(`MINUTE`, which never introduces a fractional component). There is no
fractional-seconds case this particular expression can produce, so
`strptime(bs, '%Y-%m-%d %H:%M:%S')` is complete, not just currently lucky.

- **Naive UTC**: confirmed -- `dt.datetime.strptime(...)` with a format
  string carrying no timezone directive produces a naive `datetime`; no
  `utcnow()`, no `tzinfo` attached anywhere in the changed lines.
- **Type guard**: `isinstance(bs, str)` covers the case reproduced above;
  the `else` branch (driver already returns `datetime.datetime`) is passed
  through untouched. No third type is realistically returned by a MySQL/
  MariaDB driver for this computed expression (str or datetime are the only
  two observed across PyMySQL/mysqlclient for a `DATE_ADD` result); if one
  ever were, the value would flow unmodified into `filter_by(bucket_start=bs)`
  and most likely fail to match (safe `continue` via `one_or_none() is None`)
  rather than silently succeeding on wrong data -- not a silent swallow.
- **ORM lookup still matches rows**: re-ran
  `python -m scripts.backfill_radar_buckets` myself (fresh process, not
  reusing the fixer's run): `examined 210 bucket rows, 165 understated` /
  `0 rows carry a score they earned under a different status` / `dry run --
  nothing written, pass --apply`. Identical to the report's Gate 2 and to
  the pre-fix baseline in the original review -- the explicit conversion is
  behaviorally a no-op relative to the implicit coercion it replaces, on
  this driver.

### Scope

`git show --stat 8b0a07d`: exactly the two in-scope files, +10/-0 and
+5/-0, matching the report. `discover_telegram_sources.py`,
`telegram_candidates.json`, and `reddit_candidates.json` are untouched by
this commit (not present in its diff at all).

### Verdict

**APPROVED.** Both fixes do exactly what the report claims. Fix 1's new
assertion has genuine teeth (independently reproduced fail-then-pass) and
its sentinel prefix is provably inert. Fix 2's datetime conversion is
correct, complete (no fractional-seconds case exists for this SQL
expression to produce), naive-UTC, and behaviorally verified against the
live dry run (`210/165`, unchanged). No scope creep; worktree left clean.
