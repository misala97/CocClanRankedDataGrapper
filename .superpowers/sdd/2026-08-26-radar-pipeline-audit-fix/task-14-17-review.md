# Review: Tasks 14-17 (radar-pipeline-audit-fix)

Reviewer: independent (did not write this code).
Range reviewed: `f1dddee..5ba81e1` (4 commits: 9629a86, c9a4840, bc42187, 5ba81e1).
Status: COMPLETE.

---

## Spec compliance per task

### Task 14 — the detail breakdown reads the model verdict (`9629a86`)
- ✅ `_tone_of(lexicon, verdict)` added exactly as specified: model outranks
  lexicon, `unclear` blocks and votes neither way, NULL verdict falls back to
  lexicon. Verified all four `_tone_of` cases via the brief's own test AND via
  the diff — matches verbatim.
- ✅ `breakdown_for` (brief calls it `_breakdown`) now selects
  `RadarMention.llm_sentiment` alongside `lexicon_sentiment`, uses `_tone_of`
  for bullish/bearish, and counts `disagreements` per the given algorithm.
- ✅ `Breakdown.disagreements: int` added to the dataclass.
- ✅ Test appended verbatim from the brief; observed red
  (`AttributeError: … no attribute '_tone_of'`) then green, matching the
  brief's prediction exactly (re-confirmed independently, see Teeth).
- ⚠️ **Gap, not a brief violation**: the brief's own test only unit-tests
  `_tone_of`; nothing in this commit or Task 15 exercises the *counting loop*
  in `breakdown_for` (lines 204-214) against real DB rows with genuine
  lexicon/llm disagreement. See Findings (Important) — manually verified the
  logic is currently correct, but it is unprotected by any test.

### Task 15 — render the disagreement (`c9a4840`)
- ✅ `serialize_detail` emits `'disagreements': b.disagreements` in the
  breakdown dict, exact key name.
- ✅ `types.ts` — `Breakdown.disagreements: number` added.
- ✅ `Breakdown.tsx` — renders `<b>{n}</b> read differently by the model`
  guarded on `> 0`, using the file's existing `.q` (muted) class — no new
  colour. Confirmed against actual CSS values, not just class names (see risk
  area 4): `--muted`/`--ink-2` are near-zero-chroma neutrals, wholly distinct
  from `--up`/`--down` (green/red hues 150/27) which are never referenced by
  `.wording`/`.q`.
- ✅ Test appended verbatim from the brief (`_stub_detail` + the sarcasm-signal
  test); observed red (`KeyError: 'disagreements'`) then green.
- ➕ Extra: `BoardPage.test.tsx` fixture literal updated (mechanical
  consequence of the type becoming required) — in scope per brief's own Step 5
  ("tests pass, build succeeds").
- Nothing missing from this brief's explicit requirements.

### Task 16 — make `provisional` mean something (`bc42187`)
- ✅ `scoring.py` — `baseline_days = span.total_seconds() / 86400.0`,
  fractional, matches brief exactly (comment included).
- ✅ `models.py` — column widened `SmallInteger` → `Float`, comment matches
  brief's given text.
- ✅ Migration `35c3ae366677` added, chained from `08316d3e4d77`; upgrade/
  downgrade match the brief's given code verbatim. Applied; single head
  confirmed independently (`flask db heads`/`flask db current`).
- ✅ `leaderboard.py` — mark split: `'provisional' if baseline_days >= 1.0
  else 'warming-up'`, matches brief exactly.
- ✅ Frontend taught the new mark: `Mark` union, `UNIVERSAL` record,
  `Finding()`'s header branch, `marks.test.tsx` coverage — all present and,
  per risk area 3 above, independently traced to actually reach a pixel on
  both the per-row and board-wide paths.
- ✅ Scoring test appended (docstring and final assertion verbatim per brief);
  supporting `row()` helper deviates from a literal reading of the brief — see
  "Adjudication" section below. Judged: correct and necessary, not a
  weakening.
- ✅ Leaderboard tests: existing `provisional` test strengthened with an
  explicit `'warming-up' not in row.marks`; new
  `test_a_baseline_under_a_day_is_marked_warming_up_not_provisional` added.
  Both independently re-run and mutation-tested (see Teeth).
- ⚠️ **Gap, not a brief violation**: `phrasing.py:173-177`'s narrative "read"
  clause interpolates the raw fractional `baseline_days` into user-facing
  prose with no rounding — not in the brief's file list, but a direct,
  reproduced consequence of this task's own core change. See Findings
  (Important).
- Minor stylistic asymmetry in `leaderboard.py`'s `min()` fold (no `float()`
  coercion unlike its sibling aggregates) — see Findings (Minor).

### Task 17 — correct the cost record (`5ba81e1`)
- ✅ Docstring paragraph replaced **verbatim**, word-for-word match against
  `task-17-brief.md` (diffed by eye, confirmed identical text for both the
  `COST.` and `No daily ceiling.` paragraphs).
- ✅ Step 2's own verification instruction (`grep -rn "twenty cents|1335"`)
  independently re-run — only the corrected docstring's self-referential
  mention of the old numbers remains (plus stale `.pyc` cache hits, not
  source).
- ➕ Three extra files changed beyond the brief's single-file list
  (`test_radar_llm_sentiment.py`, `Spend.tsx`, `Spend.test.tsx`) — all are
  compliance with the brief's own Step 2 ("no remaining hits outside the
  corrected docstring"), not unrelated scope creep. Confirmed each edit is a
  comment/docstring change only, no logic touched (`Spend.tsx`'s `usd()`
  function body is byte-for-byte identical before/after; `Spend.test.tsx`'s
  assertions unchanged).
- Nothing missing; nothing unexplained.

---

## Risk-area audit

### 1. Migration chain (Task 16)
- `grep down_revision = '08316d3e4d77'` across `migrations/versions/` → only
  `35c3ae366677_widen_radar_bucket_sources_baseline_days.py` matches. No fork.
- `flask db heads` → `35c3ae366677 (head)`. Single head.
- `flask db current` → `35c3ae366677 (head)`. DB is at head, matches.
- Dev DB confirmed MySQL `8.0.46` (via `SELECT VERSION()`), not MariaDB — so
  the MariaDB claim cannot be *executed* here, only reasoned about.
- The migration is a single `op.alter_column(...)` statement in `upgrade()`
  (and one in `downgrade()`) — nothing else in the file. Because MySQL/MariaDB
  DDL auto-commits per-statement, "half-applied" only becomes a risk when a
  migration contains *multiple* DDL ops and an earlier one lands before a
  later one fails. This migration has exactly one op, so there is no
  intermediate state to leave behind: it either applies (both engines,
  `MODIFY COLUMN` / widening SMALLINT→FLOAT is supported identically on both
  MySQL and MariaDB) or it doesn't run at all. Verdict: safe by construction,
  not just by luck.
- Downgrade: `type_=mysql.SMALLINT()` — narrows Float back to SmallInteger,
  silently truncating any fractional value written since the upgrade (e.g.
  `0.375` → `0`), which is exactly the destructive case the review brief
  warned about. The migration carries **no comment acknowledging this data
  loss** in `downgrade()` — worth flagging (see Findings), though note the
  downgrade code is copied verbatim from the brief itself (task-16-brief.md
  lines 79-83), which also has no such comment. **Did not run the downgrade**,
  per instructions; DB stays at `35c3ae366677`.

### 2. Decimal-at-the-boundary audit (Task 16)
Traced every read site of `baseline_days`:
- `scoring.py:155` — computed in Python from a `timedelta` (`span.total_seconds()
  / 86400.0`), never touches the DB round-trip. No Decimal exposure on write.
- `leaderboard.py:160` — `sa.func.min(bucket.baseline_days)` (SQL `MIN()`),
  fed into a Python `min()` again at line 259-260 with **no `float()` coercion
  applied** — unlike the sibling aggregates two lines above it (`mentions`,
  `expected`, `variance`, `text_ratio` are all explicitly coerced with a
  comment at line 192-196 explaining `SUM()` over an INTEGER column returns
  `Decimal` from MySQL/MariaDB). Empirically verified on the live dev DB:
  `SELECT MIN(distinct_text_ratio) …` (an existing Float column) returns a
  Python `float`, not `Decimal`, while `SELECT SUM(mention_count) …` (an
  Integer column) returns `Decimal` — confirming `MIN()`/`MAX()` do not
  promote to `DECIMAL` the way `SUM()` does, on this MySQL 8 instance. No
  rows in the local DB currently carry a non-NULL `baseline_days` (fresh
  migration, scoring hasn't repopulated it), so this could not be checked
  against the *new* Float column directly — the equivalent existing Float
  column stands in as the closest available evidence. Not re-verified against
  MariaDB. Net: the missing coercion is very likely benign, but it's an
  asymmetry with the surrounding code's own defensive pattern that a future
  reader could reasonably read as an oversight — flagged as Minor.
- `api.py:160` (`'baseline_days': r.baseline_days`) and `api.py:233`
  (`baseline_days=d.baseline_days`) — plain pass-through into `jsonify`;
  given the above, not currently at risk of hitting a `Decimal`.
- **`phrasing.py:173-177` — real, reproducible defect, not flagged by the
  implementer.** `read_clauses()` interpolates the raw float directly into
  user-facing prose: `f'The baseline is {baseline_days} {days} old, not 30…'`.
  Reproduced live: a 1-hour span (`baseline_days = 3600/86400.0 =
  0.041666666666666664`) renders as **"The baseline is
  0.041666666666666664 days old, not 30, so this rests on very little
  history."** — full float precision leaking into the sentence the panel
  shows readers. `phrasing.py` is not in Task 16's file list and was not
  touched by this batch (confirmed: absent from the diff), but the type/value
  change that causes this originates entirely in this batch's `scoring.py`
  edit. Existing tests only exercise integer-valued `baseline_days` (`2`,
  `30`), so nothing caught it. This is exactly the class of thing area #2
  asked to check for. See Findings (Important).

### 3. Does `'warming-up'` reach a pixel? — YES, traced end to end.
- `leaderboard.py:295` — `marks.append('provisional' if baseline_days >= 1.0
  else 'warming-up')`.
- `api.py:161` — `'marks': r.marks` — plain pass-through, no allowlist to fall
  afoul of.
- `types.ts` — `Mark` union now includes `'warming-up'` (was missing before
  this batch).
- `types.ts` — `Row.marks: Mark[]` — typed against the union.
- `TickerRow.tsx:73-75` — per-row marks render via `row.marks.filter(...).map
  ((mark) => <span>{mark}</span>)` — a **generic pass-through of the raw
  string**, so it renders fine with or without an explicit entry. No dead end
  here even before the fix.
- `ListPane.tsx:18-27` — `UNIVERSAL: Record<Mark, string>` is genuinely
  exhaustive (TypeScript `Record<Mark, string>` forces every union member to
  have a key) — confirmed this is a real compile gate, not aspirational, by
  the type signature itself (verified independently of the implementer's
  narrative claim of having watched `tsc` fail). `'warming-up'` has an entry.
- `ListPane.tsx`'s `Finding()` — the "baselines" header logic was rewritten
  from a single `provisional`-only ternary to a three-way `thinBaseline`
  selector that also recognizes `'warming-up'`, and both are stripped from
  `rest` so they don't double-render. Confirmed correct: only one of the two
  marks can be universal at a time (leaderboard picks exactly one per row),
  so the `provisional`-first order in `thinBaseline` is not a bug, just
  unreachable ambiguity.
- `marks.test.tsx` — three new tests, mirroring the existing `provisional`
  coverage (lifted when universal, stays put when partial, renders the raw
  string on the row). Re-ran these independently (see Gates) — pass.
- **Conclusion: `'warming-up'` reaches a pixel on both the per-row path and
  the board-wide header path.** This is not a repeat of Task 14's defect.

### 4. Task 15's colour
- `Breakdown.tsx:81-85` — the new disagreement span reuses the existing `.q`
  class (already used for the neighbouring "carried no wording at all"
  neutral-count span), no new class introduced.
- `radar.css:564-565` — `.wording .q { color: var(--muted); }` /
  `.wording .q b { color: var(--ink-2); }`.
- `radar.css:68-69` (light) / `134-135`, `160-161` (dark) —
  `--muted: oklch(0.48 0.016 285)` / `--ink-2: oklch(0.395 0.018 285)` — both
  near-zero chroma (0.016-0.018), i.e. genuinely neutral grey, not a
  disguised green/red.
- `radar.css:82-83` / `143-144`, `169-170` — `--up: oklch(… 0.130 150)` (green
  hue) / `--down: oklch(… 0.175 27)` (red hue) — confirmed these are a
  *different* token pair, used only for `.c-price-up`/`.c-price-down`/
  `.mv.up`/`.mv.down`, never referenced by `.wording` or `.q`.
- **Verdict: no colour violation.** The constraint is satisfied by construction
  (reusing an existing neutral-styled sibling), not just by the absence of an
  inline colour.

### 5. Task 16's scoring-test helper deviation — adjudicated
See separate section below (reproduced the brief's literal form).

### 6. Teeth
See Teeth audit section below.

### 7. Scope
- Task 15 folded in `BoardPage.test.tsx`'s one-line fixture fix (adding
  `disagreements: 1` to a hand-built `Breakdown` literal) — mechanical
  consequence of the type becoming required, not a behaviour change. Within
  scope of "make the build pass" implied by the brief's own Step 5.
- Task 16 folded in `format.ts`'s `MARK_WHY['warming-up']` entry — confirmed
  by grep that `MARK_WHY` is dead code (defined, never imported) both before
  and after this batch; adding a fourth entry for symmetry is inert, not a new
  behaviour, and correctly flagged by the implementer as such.
- Task 16 also updated `detail_panel.py`'s and `leaderboard.py`'s
  `baseline_days: int | None` → `float | None` type hints, and
  `test_radar_phrasing.py`'s `FakeRow` dataclass default type hint — these are
  necessary consequences of the column type change, not scope creep.
- Task 17 pulled in three extra files (`test_radar_llm_sentiment.py`,
  `Spend.tsx`, `Spend.test.tsx`) beyond its stated single-file brief — but the
  brief's own Step 2 explicitly instructs grepping for stale figures
  repo-wide and expects zero remaining hits, so this is compliance with the
  brief's own verification step, not drift. Confirmed via
  `grep -rn "twenty cents|1335" personal_apps/ --exclude-dir=node_modules` —
  only the corrected docstring's self-referential mention of the old numbers
  remains (see Gates).
- No unexplained extra files found in any commit. `git show --stat` per
  commit matches the report's file lists exactly.

---

## Adjudication: Task 16's scoring-test helper deviation

The brief's literal Step 1 body calls `row(external_id='zz-%d' % hour,
minute=0)` inside `for hour in (14, 20, 23)`, relying on some pre-existing
`row()` — the only candidate in the suite is `test_radar_buckets.row()`
(already cross-file-imported by `test_radar_bucket_sources.py`). That helper
hardcodes `created_utc=dt.datetime(2026, 4, 15, 14, minute, 0)` — hour fixed
at 14 regardless of the loop variable.

**Reproduced independently** with a standalone script (not part of the test
suite, cleaned up by exact ticker/external_id identity afterward) that calls
`buckets.roll_up` exactly as the brief's literal snippet does, using the
unmodified `test_radar_buckets.row()`, against the *current* (already fixed,
already migrated) codebase:

```
hour=14 roll_up wrote 1 bucket(s)
hour=20 roll_up wrote 0 bucket(s)
hour=23 roll_up wrote 0 bucket(s)
total RadarBucketSource rows for ZZA/bluesky: 1
scored.baseline_days = 0.0
ASSERTION FAILED: 0 < 0.0 < 1 is false
```

This confirms the implementer's diagnosis exactly: `buckets.roll_up`'s window
filter (`buckets.py:169-170`) recomputes only buckets whose *row's own*
`bucket_start_for(created_utc)` falls in `touched` — with every row's
`created_utc` hardcoded to 14:00 regardless of the loop's `hour`, only the
`hour=14` call ever writes anything. One bucket → `span == timedelta(0)` →
`baseline_days == 0.0` → the assertion `0 < scored.baseline_days < 1` is false
**forever**, independent of the `.days`-truncation fix this task exists to
make. The brief's literal form could never have gone green.

**Verdict: legitimate, correctly resolved.** The implementer's local `row()`
(this file only, accepting an explicit `hour` and threading `hour=hour`
through the loop) is the smallest fix that makes the given docstring and
final assertion achievable at all — it doesn't loosen what's being tested,
it's the only way to test it. Re-ran the actual committed test independently:
passes (`1 passed`). This is a supporting-code judgment call, not a
spec-loosening rewrite-to-green.

---

## Teeth audit

Re-verified independently (own mutations, not trusting the implementer's
table), on top of the already-clean worktree. Every mutation below was
reverted and confirmed via `git status --short` / `git diff --stat` returning
empty before moving to the next.

| # | Target | Mutation | Command | Exact failure observed | Reverted |
|---|---|---|---|---|---|
| 1 | `detail_panel.py` disagreement counting loop (lines 204-214) — **not** the brief's own `_tone_of` unit test, which the implementer already covered | `if llm is not None and lexicon_only is not None and tone != lexicon_only:` → `if False:` (permanently disables counting) | `pytest tests/test_radar_detail.py tests/test_radar_api.py -q` | **No failure** — `69 passed` | ✓ (`git diff --stat` empty after) |
| 2 | `leaderboard.py:295` mark selection | `marks.append('provisional' if baseline_days >= 1.0 else 'warming-up')` → unconditional `marks.append('provisional')` | `pytest tests/test_radar_leaderboard.py -q -k "provisional or warming"` | `AssertionError: assert 'warming-up' in ['provisional']` (in `test_a_baseline_under_a_day_is_marked_warming_up_not_provisional`) | ✓ |
| 3 | `scoring.py:155` fractional fix | `span.total_seconds() / 86400.0` → `span.days` (the pre-fix form) | `pytest tests/test_radar_scoring.py -q -k baseline` | `AssertionError: assert 0 < 0.0` (`scored.baseline_days == 0.0`) — matches the brief's own Step 2 prediction | ✓ |
| 4 | `ListPane.tsx` `universalMarks` | `rows.every(...)` → `rows.some(...)` | `npx vitest run -c vite.radar.config.ts static/radar/src/list/marks.test.tsx` | Both "stays on the row when only some rows carry it" tests fail: `expected [ 'provisional' ] to deeply equal []` and `expected [ 'warming-up' ] to deeply equal []` | ✓ |

**Finding #1 is the significant one**: disabling the disagreement-counting
loop entirely — the actual mechanism Task 14 exists to build — produces **zero
test failures** anywhere in the two most relevant test files. Manually
verified the logic is currently *correct* (see below), so this is a
test-coverage gap, not a live bug, but it means a future regression in this
exact loop would go undetected. See Findings (Important).

Manual correctness check (throwaway script, `ZZDISAGREE` ticker, cleaned up
by exact `ticker ==`/`external_id.in_([...])` identity, not `LIKE`): built 4
posts through `detail_panel.breakdown_for` — (lexicon=0.8, llm=bearish),
(lexicon=-0.8, llm=bullish), (lexicon=0.8, llm=bullish), (lexicon=None,
llm=None) — expected 2 disagreements (the first two rows, where the model
outranks and reverses the lexicon's read); got exactly
`bullish=2 bearish=1 neutral=1 disagreements=2`. The implementation is
correct; only the test net around it is missing.

Teeth count: **4 independently re-verified, all with exact matching failure
messages, all cleanly reverted.** (The brief's other reported mutations —
Task 14's `unclear`/None cases on the pure `_tone_of` function — were not
re-run since they test a pure function already exercised directly by the
brief's own assertions and are lower-risk than the four above; spot-checked
by reading the function instead.)

---

## Gates

| # | Command (from `personal_apps/`) | Result |
|---|---|---|
| 1 | `python -m pytest tests/ -k radar -q` | **637 passed, 646 deselected**, 2 pre-existing `utcnow()` deprecation warnings (SQLAlchemy internal, unrelated to this batch). Manifest was present so the "2 permitted template failures" case did not apply — 0 failures. Matches the report exactly. |
| 2 | `npx tsc --noEmit` | Clean, no output. |
| 3 | `npx vitest run -c vite.radar.config.ts` | `9 test files, 84 tests passed`. |
| 4 | `npm run build` | Both Vite builds succeed (gym + radar); `static/radar/dist/.vite/manifest.json` regenerated. |
| 5 | `python -c "from features.radar import buckets"` | OK |
| 5 | `python -c "from features.radar import journal"` | OK |
| 5 | `python -c "from features.radar import ingest"` | OK |
| 5 | `python -c "from run_radar_ingest import build_fetchers"` | OK |
| 6 | `flask db heads` | `35c3ae366677 (head)` — single head |
| 6 | `flask db current` | `35c3ae366677 (head)` — DB at head, matches |

Dev DB confirmed **MySQL 8.0.46** (`SELECT VERSION()`), not MariaDB — no
MariaDB instance available in this environment, so the migration's MariaDB
safety claim is reasoned (see risk area 1), not executed.

---

## Findings

### Critical
None.

### Important

**I1. `phrasing.py:173-177` — fractional `baseline_days` renders as an
unrounded raw float in user-facing prose.**
`read_clauses()` builds the detail panel's narrative "read" clause with
`f'The baseline is {baseline_days} {days} old, not 30, so this rests on very
little history.'`. This function is not in Task 16's file list and was not
touched by this batch, but it is fed directly from `d.baseline_days`
(`routes/api.py:233`), which Task 16 turned from a truncated int into an
unrounded float. Reproduced live: a 1-hour-old baseline
(`3600/86400.0 == 0.041666666666666664`) renders as:
> "The baseline is 0.041666666666666664 days old, not 30, so this rests on
> very little history."

This is exactly the population `'warming-up'` was built to correctly label —
so the fix that makes the *mark* stop lying makes the *sentence* underneath
it start looking broken. No test covers a fractional value (existing tests
only use `baseline_days=2` and `=30`). Concrete fix: round for display, e.g.
`f'{baseline_days:.1f}'` or a "under a day" / "N days" branch, in
`phrasing.py`'s `read_clauses`.

**I2. `detail_panel.py`'s disagreement-counting loop (lines 204-214) has zero
test coverage of its actual integration path.**
Mutation-tested: replacing the counting condition with `if False:` (permanent
no-op) leaves all 69 tests in `test_radar_detail.py` + `test_radar_api.py`
green. The brief's own Task 14 test exercises only the pure `_tone_of`
helper; Task 15's test exercises only `serialize_detail`'s pass-through of a
hand-built `Breakdown` literal. Nothing exercises `breakdown_for` with real
rows carrying both a lexicon score and a disagreeing model verdict. Manually
verified the logic is currently *correct* (4-row scenario:
`bullish=2 bearish=1 neutral=1 disagreements=2`, matching hand-computed
expectations) — so this is a coverage gap, not a live bug, but it is the
exact "an absence is never a zero" / "teeth" class of risk this audit is
built to catch, on the very deliverable ("11,789 paid-for verdicts reach no
pixel") this two-task story is about. Concrete fix: add one test to
`test_radar_detail.py` building 2-3 `RadarPost`/`RadarMention` rows with
disagreeing lexicon/llm values (via the existing `post_for`-style helper,
extended to accept `llm_sentiment`) and asserting `breakdown.disagreements`
directly.

### Minor

**M1. Migration `35c3ae366677`'s `downgrade()` has no comment noting the data
loss it causes.** Narrowing Float back to SMALLINT truncates any fractional
value written since the upgrade (e.g. `0.375` → `0`) — precisely reversing
the fix. The code is copied verbatim from the brief (which also has no such
comment), so this isn't an implementer deviation, but given the review's
explicit focus on this exact risk, it's worth a one-line comment before this
migration is trusted as a rollback path. `migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py:34-37`.

**M2. `leaderboard.py:259-260` — `baseline_days = min(...)` lacks the
explicit `float()`/coercion its sibling aggregates two lines above have
(with a comment explaining `SUM()` over an INTEGER column returns `Decimal`
from MySQL/MariaDB).** Empirically checked on the live dev DB: `MIN()` over
an existing Float column (`distinct_text_ratio`) returns a Python `float`,
not `Decimal` — unlike `SUM()` over an Integer column, which does return
`Decimal`. This strongly suggests `MIN(baseline_days)` (now Float) is safe
uncoerced, and is consistent with MySQL's aggregate-function type-promotion
rules (`MIN`/`MAX` preserve column type; `SUM`/`AVG` promote). Not verified
against the *actual* `baseline_days` column directly (no non-NULL rows exist
yet in this dev DB post-migration) nor against MariaDB. Given the file's own
established defensive pattern one line above, adding the same coercion here
would remove any ambiguity for a future reader, at zero cost.
`personal_apps/features/radar/leaderboard.py:259-260`.

**M3. Pre-existing broad `LIKE 'ZZ%'` teardown hazard: found in six files, not
five.** `test_radar_bucket_sources.py`, `test_radar_buckets.py`,
`test_radar_daemon.py`, `test_radar_journal.py`, `test_radar_retention.py`,
`test_radar_universe.py` all contain a literal `.like('ZZ%')` delete. The
task brief for this review stated five pre-existing files carry this hazard;
I count six. **None of the six were touched by this batch** (confirmed: none
appear in the `f1dddee..5ba81e1` diff), so this batch did not add a sixth (or
seventh) — it's purely a discrepancy in the pre-existing count for whoever
does final triage, not a defect introduced here. `test_radar_scoring.py`'s
new test reuses the existing `clean_buckets` fixture (imported from
`test_radar_buckets.py`, one of the six) rather than defining a new
broad-delete pattern of its own.

---

## ⚠️ Cannot verify from diff / this environment

- **MariaDB-specific behaviour of `ALTER TABLE … MODIFY COLUMN` widening
  SMALLINT→FLOAT.** No MariaDB instance available here; dev DB is MySQL
  8.0.46 only. Reasoned safe (single-statement migration, standard supported
  widening on both engines, matching `MODIFY COLUMN` syntax) but not executed
  against MariaDB directly.
- **Whether `MIN(baseline_days)` returns `Decimal` on MariaDB specifically.**
  Checked the equivalent case on MySQL 8 via a proxy Float column
  (`distinct_text_ratio`) since no `baseline_days` rows are populated yet in
  this dev DB post-migration; consistent with the general MySQL protocol
  type-promotion rule, but not a direct measurement, and not cross-checked on
  MariaDB.

---

## Findings

(filling in below)

---

## Verdict

**NEEDS_FIXES** — critical: 0, important: 2, minor: 3.

All four tasks meet their brief's explicit, literal requirements: Task 14's
verdict-precedence logic is correct and matches the brief exactly; Task 15's
disagreement count is wired through the serializer and rendered without a
colour violation; Task 16's migration is a safe single-head, single-statement
widening, `'warming-up'` genuinely reaches a pixel on both the per-row and
board-wide paths, and the test-helper deviation is a legitimate, necessary
fix rather than a loosened spec; Task 17's docstring matches the brief
verbatim and its extra files are compliance with the brief's own verification
step, not scope creep. All four re-run gates are green, and four independent
mutation tests (not just a re-read of the implementer's table) produced
exact matching failures and reverted cleanly.

What keeps this from a clean APPROVE is two things the implementer's own
report did not surface, both found by following exactly the risk areas this
review was asked to chase to the boundary rather than stopping at the
brief's literal file list:

1. Task 16's own core change (fractional `baseline_days`) reaches
   `phrasing.py`'s narrative text with no rounding, producing reproducible
   garbage like "0.041666666666666664 days old" for the exact population
   `'warming-up'` exists to describe correctly (I1).
2. The disagreement-counting loop that is the entire point of Task 14 —
   "nothing performed it until now" — has no test with real disagreeing data
   behind it; disabling it entirely passes all 69 relevant tests (I2). The
   logic is currently correct (manually verified), so this is a coverage gap
   rather than a live bug, but it's the load-bearing gap the whole audit
   exists to find.

Neither is data-corrupting, crash-inducing, or a security issue; both are
real, reproducible, and cheap to fix (a display-format change in one function;
one new test). Recommend fixing I1 and I2 before merge, at which point this
batch is approvable. The three Minor items are lower-priority documentation/
consistency/triage notes, not blockers.

worming-up-reaches-UI: **yes**, independently traced end to end (leaderboard
→ api.py pass-through → types.ts `Mark` union → `TickerRow.tsx` generic
render + `ListPane.tsx`'s exhaustive `UNIVERSAL` record → `marks.test.tsx`,
all re-run).

---

## Fix round 1 re-review

Reviewer: independent (did not write the fix, did not write the original
review). Scope: **only** the fix diff `5ba81e1..d7fc03d`
(`.superpowers/sdd/review-5ba81e1..d7fc03d.diff`, 1 commit `d7fc03d`, 5 files,
94 insertions / 7 deletions). The base batch's own behaviour (Tasks 14-17) was
not re-litigated.

### I2 — the load-bearing check

Re-applied the review's own mutation to `detail_panel.py`'s counting loop
(lines 212-214), independently, from scratch:

```python
lexicon_only = _tone_of(sentiment, None)
if False:  # MUTATION re-review
    disagreements += 1
```

`pytest tests/test_radar_detail.py tests/test_radar_api.py -q` →
**`1 failed, 69 passed`**, exact same shape as the original finding:

```
AssertionError: assert 0 == 1
 +  where 0 = Breakdown(..., bullish=3, neutral=2, bearish=1, disagreements=0, ...).disagreements
```

Only `test_the_breakdown_counts_real_disagreements_not_just_the_tone_helper`
caught it; the other 69 (including the base batch's own `_tone_of`-only test
and the serializer pass-through test) stayed green under the mutation, exactly
reproducing the pre-fix gap. Reverted immediately after
(`git diff --stat -- personal_apps/features/radar/detail_panel.py` empty).
**The coverage gap is closed — confirmed, not just re-read.**

Also checked the new test drives the real path, not a stub: it calls
`post_for(...)` (real `RadarPost`/`RadarMention` inserts via the existing
`panel_ticker` fixture, ticker `DTA`) three times and reads
`detail_panel.build(...).breakdown.disagreements` — the actual `breakdown_for`
query path, not a hand-built `Breakdown` literal (that was Task 15's test,
different file, not this one). Hand-verified the test's own arithmetic
independently against `_tone_of`'s rules: base fixture (3 posts, all
`llm_sentiment=None`) contributes bullish=1/neutral=2; the three new rows
contribute bearish=1 (moon+bearish, model reverses lexicon's bullish read →
counted), bullish=1 (moon+bullish, agrees → not counted), bullish=1 (no
directional word + bullish, lexicon never took a side → not counted per
`_tone_of`'s `lexicon and lexicon > 0` guard on `0.0` being falsy) — totals
bullish=3/neutral=2/bearish=1/disagreements=1, matching the mutated run's own
printed `Breakdown` repr exactly (down to `bullish=3, neutral=2, bearish=1`).
The test is not tautological or hand-computed-then-asserted; it is driven
entirely by real rows and the real query.

No new fixture was added — the test reuses the file's existing `panel_ticker`
fixture (PREFIX `DT`, pre-existing convention, not introduced by this fix) and
the existing broad-`LIKE` teardown that fixture already had before this batch.
Nothing new to namespace on `ZZ` here since nothing new was added.

### I1 — rendered strings checked directly

Ran `phrasing.read_clauses` directly (not just via pytest) for
`baseline_days` = `1/24`, `2`, `2.7`, `30`:

```
1/24 -> 'The baseline is under a day old, not 30, so this rests on very little history.'
2    -> 'The baseline is 2 days old, not 30, so this rests on very little history.'
2.7  -> 'The baseline is 3 days old, not 30, so this rests on very little history.'
30   -> [] (no baseline clause — unchanged, 30 >= PROVISIONAL_BASELINE_DAYS)
```

Sub-day case is now sensible prose, no float leakage. The `baseline_days=2`
and `=30` existing tests (`test_the_read_names_its_own_weak_baseline`,
`test_a_full_baseline_earns_no_caveat`) were not touched and still hold: the
`=2` test only asserts a generic "some warn clause mentions baseline" (not
exact text), and `=30` short-circuits before the branch entirely (`30 >=
14`, the real `PROVISIONAL_BASELINE_DAYS`, not the hardcoded "not 30" prose,
which is pre-existing and correctly left out of this finding's scope). Two
new tests pin the fractional cases exactly. Confirmed via the full run:
`pytest tests/test_radar_phrasing.py -q` → 18 passed.

One low-confidence, non-blocking observation, not raised as a finding: `round()`
on the multi-day branch uses Python's banker's rounding, so a value landing
exactly on a `.5` boundary (e.g. `1.5`) rounds to the nearest even day rather
than always up. This only affects prose cosmetics at a boundary real
`baseline_days` values will rarely land on exactly, has no numeric or
comparison consequence, and is not worth gating on.

### M2 — coercion checked against the sibling pattern

`leaderboard.py:263` now reads
`min((float(part.baseline_days) for part in parts if part.baseline_days is
not None), default=None)` — `float()` applied per-element inside the same
filtered generator, directly analogous to the existing `text_ratio =
float(min(part.text_ratio for part in parts))` pattern two lines above (line
206). Correct placement (coercion happens before `min`, only on the non-None
branch), consistent with the file's established defensive idiom, no
behaviour change on the local MySQL 8 dev DB (full leaderboard suite still
green inside the `pytest tests/ -k radar -q` run).

### M1, M3 — addressed as described

M1: `downgrade()` in
`migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py`
now carries a comment stating the narrowing truncates fractional values and
must not be run against a database with real scored history. Comment-only;
confirmed the downgrade was never invoked (`flask db current` /
`flask db heads` both still `35c3ae366677 (head)`).

M3: re-ran `grep -rln "like('ZZ%')" personal_apps/tests/` myself — six files
(`test_radar_bucket_sources.py`, `test_radar_buckets.py`,
`test_radar_daemon.py`, `test_radar_journal.py`, `test_radar_retention.py`,
`test_radar_universe.py`), matching the fix round's corrected count. None
appear in the `5ba81e1..d7fc03d` diff — no code change was made for M3, as
the review recommended (documentation-only correction of the prior brief's
count, for final triage).

### Anything new introduced / rewritten-to-green

None found. The diff is exactly five files and stays within the five
findings' scope: `leaderboard.py` (M2, comment+coercion),
`phrasing.py` (I1, display branch), the migration file (M1, comment only),
`test_radar_detail.py` (I2, one new test + a backward-compatible optional
param on `post_for`), `test_radar_phrasing.py` (I1, two new tests). No
existing test was weakened, reworded, or had an assertion loosened to pass —
the only existing-test touch is `post_for`'s new `llm_sentiment=None` default
parameter, which changes nothing for any existing caller. No fixture was
added; the one new DB-backed test reuses an existing fixture and existing
teardown convention untouched by this batch.

### Gates (fix round re-run independently)

| # | Command | Result |
|---|---|---|
| 1 | `python -m pytest tests/ -k radar -q` (from `personal_apps/`) | `640 passed, 646 deselected, 2 warnings` — matches the fixer's report exactly (637 + 3 new: 2 phrasing + 1 detail). Vite manifest present, so 0 of the "2 permitted template failures" applied. |
| 2 | `npx tsc --noEmit` | Clean, no output. |
| 2 | `npx vitest run -c vite.radar.config.ts` | `9 test files, 84 tests passed`. |
| 3 | `flask db current` | `35c3ae366677 (head)` |
| 3 | `flask db heads` | `35c3ae366677 (head)` — single head, no fork. Downgrade not run. |

### Worktree state after review

`git status --short` → empty. `git diff --stat` → empty. `HEAD` →
`d7fc03d143ab205b2943738aa9a0214818678af5`, unchanged. The `if False:` teeth
mutation to `detail_panel.py` was applied, observed, and reverted during this
review; no other file was touched. Nothing committed.

### Verdict

**APPROVED.** All 5 findings from the original review (I1, I2, M1, M2, M3)
are correctly and completely addressed by `d7fc03d`. I2's coverage gap is
independently confirmed closed — re-applying the exact `if False:` mutation
that originally slipped through all 69 tests now produces exactly one
failure, from the new test, with the same `Breakdown` shape the fixer
reported. I1's display fix was checked by direct rendering, not just by
reading the diff, and does not regress the pre-existing integer-valued
(`=2`, `=30`) cases. M2's coercion is correctly placed and consistent with
its sibling pattern. M1 and M3 are documentation-only, exactly as scoped. No
new Critical, Important, or Minor issues were found in the fix diff itself;
no test was rewritten to go green rather than to test real behaviour; no
fixture was added, so the `ZZ`-namespacing/exact-identity-teardown
requirement does not apply here. Worktree left exactly as found.
