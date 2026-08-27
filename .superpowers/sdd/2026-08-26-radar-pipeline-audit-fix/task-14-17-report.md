# Tasks 14-17 report

Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`, started at HEAD `f1dddee` (clean).

Status: DONE. Final HEAD `5ba81e1`. See "Final verification gates" and
"Commits" sections at the end for the full closing summary.

---

## Task 14: The detail breakdown reads the model verdict

### What changed
- `personal_apps/features/radar/detail_panel.py`: added `_tone_of(lexicon, verdict)`
  precedence helper; `breakdown_for` now selects `RadarMention.llm_sentiment`
  alongside `lexicon_sentiment`, computes tone via `_tone_of`, and counts
  `disagreements` (lexicon-only tone differs from model-outranked tone).
  `Breakdown` dataclass gains `disagreements: int`.
- `personal_apps/tests/test_radar_detail.py`: appended
  `test_the_breakdown_prefers_the_model_verdict_over_the_lexicon` verbatim
  from the brief.

### Red output (verbatim, first run)
```
tests/test_radar_detail.py::test_the_breakdown_prefers_the_model_verdict_over_the_lexicon FAILED
...
>       assert detail_panel._tone_of(lexicon=0.8, verdict='bearish') == 'bearish'
               ^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: module 'features.radar.detail_panel' has no attribute '_tone_of'
```
Matched the brief's prediction exactly.

### Green
`python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -q` -> `68 passed in 2.02s`.

### Teeth (Task 14)
Two assertions in the new test are absence-shaped (`is None`):

| assertion | mutation | exact failure | reverted |
|---|---|---|---|
| `_tone_of(lexicon=0.8, verdict='unclear') is None` | Changed the blocking guard from `if verdict is not None:` to `if verdict not in (None, 'unclear'):` so `'unclear'` falls through to the lexicon instead of blocking it | `AssertionError: assert 'bullish' is None` (`_tone_of(lexicon=0.8, verdict='unclear')` returned `'bullish'`) | Yes, confirmed via `git diff` showing no MUTATION marker left |
| `_tone_of(lexicon=None, verdict=None) is None` | Changed the final `return None` to `return 'bullish'` | `AssertionError: assert 'bullish' is None` (`_tone_of(lexicon=None, verdict=None)` returned `'bullish'`) | Yes |

After each mutation+observe+revert cycle, `python -m pytest tests/test_radar_detail.py::test_the_breakdown_prefers_the_model_verdict_over_the_lexicon -v` was re-run to confirm the mutation had been fully undone (green).

### Commit
`9629a86` — `fix(radar): the panel's tone bar reads the verdicts it has been paying for`
Staged: `personal_apps/features/radar/detail_panel.py`, `personal_apps/tests/test_radar_detail.py`.

---

## Task 15: Render the disagreement

### What changed
- `personal_apps/features/radar/routes/api.py`: `serialize_detail` now emits
  `breakdown.disagreements` from `b.disagreements`.
- `personal_apps/static/radar/src/types.ts`: `Breakdown` interface gains
  `disagreements: number`.
- `personal_apps/static/radar/src/detail/Breakdown.tsx`: renders
  `<b>{b.disagreements}</b> read differently by the model` as another muted
  (`q`-class) child span inside the existing `<p className="wording">` block
  (next to the "carried no wording at all" span), guarded on
  `b.disagreements > 0`. No new colour introduced — green/red stay reserved
  for price direction (file's own comment at the top already states this; the
  file's own history notes a green/red tone bar "has been built and removed
  twice" for exactly this collision).
- `personal_apps/static/radar/src/board/BoardPage.test.tsx`: had its own
  hand-built `Breakdown`-shaped literal (in the `detail()` test fixture) that
  became a `tsc` error once `disagreements` became a required field; added
  `disagreements: 1` to keep it exhaustive. Not in the brief's file list but
  a mechanical consequence of the type change; folded into this commit since
  it is purely a test-fixture fix, not a behaviour change.
- `personal_apps/tests/test_radar_api.py`: added `_stub_detail(breakdown)`
  helper (built by hand from `detail_panel.Detail`/`detail.Chart`, no DB) and
  `test_the_detail_payload_carries_the_sarcasm_signal`, both verbatim from
  the brief (the helper's field list matches the brief's enumeration exactly).

### Red output (verbatim, first run)
```
tests/test_radar_api.py::test_the_detail_payload_carries_the_sarcasm_signal FAILED
...
>       assert payload['breakdown']['disagreements'] == 2
E       KeyError: 'disagreements'
```
Matched the brief's prediction exactly.

### Teeth
The new assertion (`payload['breakdown']['disagreements'] == 2`) is a
positive-value equality check, not absence-shaped -- no NULL, no exclusion, no
mark withheld. No teeth mutation applicable/performed for Task 15.

### Green
- `python -m pytest tests/test_radar_api.py -q` -> `35 passed in 0.50s`
- `npx tsc --noEmit` -> clean (after fixing `BoardPage.test.tsx`)
- `npx vitest run -c vite.radar.config.ts` -> `9 test files, 81 tests passed`
- `npm run build` -> both Vite builds succeed; `static/radar/dist/.vite/manifest.json`
  regenerated.

### Commit
`c9a4840` — `feat(radar): show where the model and the word list disagree`
Staged: `personal_apps/features/radar/routes/api.py`,
`personal_apps/static/radar/src/board/BoardPage.test.tsx`,
`personal_apps/static/radar/src/detail/Breakdown.tsx`,
`personal_apps/static/radar/src/types.ts`,
`personal_apps/tests/test_radar_api.py`.

---

## Task 16: Make `provisional` mean something

### What changed
- `personal_apps/features/radar/scoring.py`: `baseline_days = span.days`
  (truncating) -> `span.total_seconds() / 86400.0` (fractional).
- `personal_apps/models.py`: `RadarBucketSource.baseline_days` column
  `db.SmallInteger` -> `db.Float`.
- New migration `personal_apps/migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py`,
  chained after `08316d3e4d77` (the branch's prior single head). Applied with
  `flask db upgrade`; downgrade written (mirrors the upgrade, narrows back to
  SMALLINT) but **not run**, per instructions.
- `personal_apps/features/radar/leaderboard.py`: the `provisional` mark is
  now `'provisional' if baseline_days >= 1.0 else 'warming-up'` -- splits "a
  new ticker" from "the whole board just changed config version."
- Type-hint follow-through (float, not behaviour): `baseline_days: int | None`
  -> `float | None` in `detail_panel.py`'s `Detail`, `leaderboard.py`'s `Row`,
  and the `FakeRow` test double in `tests/test_radar_phrasing.py`.
- Frontend: `static/radar/src/types.ts` -- `Mark` union gains `'warming-up'`.
  `static/radar/src/list/ListPane.tsx` -- `UNIVERSAL: Record<Mark, string>` is
  declared exhaustive over `Mark` on purpose (its own comment says so), so
  this was a *compile error*, not a style choice, until `'warming-up'` got an
  entry; also fixed `Finding`'s "baselines over 30 days" branch, which
  special-cased only `'provisional'` -- left alone, a board universally
  `warming-up` would still have said "baselines over 30 days" while every row
  disagreed, the exact bug this section's own docstring says it exists to
  prevent. `static/radar/src/format.ts` -- added a `MARK_WHY['warming-up']`
  entry for parity with the other three marks (this record is currently
  unused/dead in the codebase -- not wired to any tooltip -- so this is
  documentation parity, not a behaviour change).
- `personal_apps/tests/test_radar_scoring.py`: imported `clean_buckets` from
  `test_radar_buckets` (reusing the existing fixture, not adding a new
  hazardous one) and added a local `row(external_id, minute=0, hour=14, ...)`
  helper plus `test_a_baseline_shorter_than_a_day_is_not_reported_as_zero_days`.
  See **Resolution notes** below for why the helper differs from the brief's
  literal call.
- `personal_apps/tests/test_radar_leaderboard.py`: strengthened
  `test_a_thin_baseline_is_marked_provisional` with an explicit
  `'warming-up' not in row.marks`, and added
  `test_a_baseline_under_a_day_is_marked_warming_up_not_provisional`.
- `personal_apps/static/radar/src/list/marks.test.tsx`: added a
  `describe('warming-up, a second thin-baseline mark')` block mirroring the
  existing `'provisional'` coverage (lifted when universal, stays on the row
  when partial, renders on the row).

### Resolution note: the brief's scoring test helper doesn't vary by hour
The brief's Step 1 test calls `row(external_id='zz-%d' % hour, minute=0)`
inside a loop over `hour in (14, 20, 23)`, implying reuse of
`test_radar_buckets.row()` (the only existing `row()` in the suite, already
imported cross-file by two other test modules). That helper hardcodes
`created_utc=dt.datetime(2026, 4, 15, 14, minute, 0)` -- the hour is fixed at
14 regardless of the loop variable, which the call site never threads through
(only `minute=0` and `external_id` vary). Traced the consequence with a
throwaway probe (not part of the test suite): all three `roll_up` calls
target `touched={start}` where `start` varies (14:00/20:00/23:00), but
`buckets.roll_up`'s `windows` filter only recomputes a bucket whose *row*
`bucket_start_for(created_utc)` is *in* `touched` -- with every row dated
14:00, only the `hour=14` iteration ever writes anything; the other two are
no-ops. Net effect: one bucket, `span == timedelta(0)`, so
`0 < scored.baseline_days < 1` would be false forever, on the fixed code too
-- not just before the fix. Confirmed with a standalone script
(`bucket count: 3` only after the row helper was hour-aware; before that the
literal helper produces exactly one row).

Resolved by defining a local `row()` for this test file that also accepts
`hour` (default 14) and passing `hour=hour` explicitly in the loop -- the
smallest, most legible fix (no implicit parsing of the id string), preserving
the given docstring and final assertion verbatim. This is a supporting-code
judgment call under "decide implementation trade-offs," not a deviation from
the required test body/assertion.

### Red output (verbatim, first run — scoring test)
```
tests/test_radar_scoring.py::test_a_baseline_shorter_than_a_day_is_not_reported_as_zero_days FAILED
...
>       assert 0 < scored.baseline_days < 1
E       assert 0 < 0
E        +  where 0 = <RadarBucketSource ZZA, 2026-04-15 14:00:00, bluesky>.baseline_days
```
(Differs from the brief's predicted `assert 0 < 0.0` only in that the column
was still `SmallInteger` at this point in the TDD sequence -- an int `0`, not
a float. After the scoring.py fix but *before* the migration was applied, the
same test failed again as `assert 0 < 0.0`, because the ORM-side type had
become Float while the DB column was still SMALLINT and silently rounded the
written `0.375` down to `0` on insert -- this is exactly why the migration is
load-bearing, not optional, confirmed live rather than assumed.)

### Green
- Scoring test green after scoring.py fix + migration applied:
  `python -m pytest tests/test_radar_scoring.py -v -k baseline` -> 4 passed.
- `python -m pytest tests/test_radar_scoring.py tests/test_radar_buckets.py tests/test_radar_bucket_sources.py tests/test_radar_backfill.py tests/test_radar_journal.py tests/test_radar_board.py tests/test_radar_detail.py tests/test_radar_phrasing.py -q`
  -> `155 passed`.
- `python -m pytest tests/test_radar_leaderboard.py -q` -> `29 passed`.
- `npx tsc --noEmit` -> clean.
- `npx vitest run -c vite.radar.config.ts` -> `9 files, 84 passed`.
- `npm run build` -> both builds succeed.

### Teeth
| assertion | mutation | exact failure | reverted |
|---|---|---|---|
| `0 < scored.baseline_days < 1` (scoring) | Ran the test on the pre-fix code (`baseline_days = span.days`) -- functionally identical to a targeted mutation, since the fix was applied immediately after and reverted to observe this | `AssertionError: assert 0 < 0` (SmallInteger stage); re-observed as `assert 0 < 0.0` once the ORM Float/DB SMALLINT mismatch existed, before the migration | Yes -- fix applied for real afterward, not left mutated |
| `'warming-up' not in row.marks` (thin-but-not-warming case) + `'provisional' not in row.marks` (warming-up case) | First swapped the ternary (`'warming-up' if baseline_days >= 1.0 else 'provisional'`); both tests failed but only on their *positive* assertion (short-circuited before reaching the absence check) | `AssertionError: assert 'provisional' in ['warming-up']` / `assert 'warming-up' in ['provisional']` | reverted, then re-mutated |
| (same two, isolated) | Made both marks fire together (`marks.append('provisional'); marks.append('warming-up')` unconditionally) so the positive assertions still pass and only the absence assertions are exercised | `AssertionError: assert 'warming-up' not in ['provisional', 'warming-up']` / `assert 'provisional' not in ['provisional', 'warming-up']` | Yes, confirmed via `git diff` clean |
| `universalMarks` returns `[]` when only some rows carry `'warming-up'` (and the pre-existing `'provisional'` case, exercised incidentally) | `rows.every(...)` -> `rows.some(...)` in `universalMarks` | `AssertionError: expected [ 'warming-up' ] to deeply equal []` (and `[ 'provisional' ]` for the sibling case) | Yes, confirmed via `git diff` clean |

Not teeth-tested: `ListPane.tsx`'s `Finding` "baselines" text branch has no
dedicated test file (no `ListPane.test.tsx` exists at all, and the
pre-existing `'provisional'` half of that branch was equally untested before
this batch) -- noted under Concerns rather than invented as new scope.

### Commit
`bc42187` — `fix(radar): provisional now means a thin baseline, not every row`
Staged (12 files): `personal_apps/features/radar/detail_panel.py`,
`personal_apps/features/radar/leaderboard.py`,
`personal_apps/features/radar/scoring.py`,
`personal_apps/migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py`,
`personal_apps/models.py`, `personal_apps/static/radar/src/format.ts`,
`personal_apps/static/radar/src/list/ListPane.tsx`,
`personal_apps/static/radar/src/list/marks.test.tsx`,
`personal_apps/static/radar/src/types.ts`,
`personal_apps/tests/test_radar_leaderboard.py`,
`personal_apps/tests/test_radar_phrasing.py`,
`personal_apps/tests/test_radar_scoring.py`.

### Migration / schema note (one of the "things the brief may not tell you")
`RadarBucketSource.baseline_days` was `db.SmallInteger` (confirmed by reading
`models.py:712` before editing). Added migration `35c3ae366677`, chained from
`08316d3e4d77` (the branch's prior single head), applying
`op.alter_column(..., type_=sa.Float())`; model and migration agree.
`flask db upgrade` applied it against the local dev MySQL 8 database;
`flask db current` / `flask db heads` both report `35c3ae366677 (head)` --
single head, no fork. Downgrade written but never invoked.

---

## Task 17: Correct the cost record

### What changed
- `personal_apps/features/radar/llm_sentiment.py`: replaced the `COST.`
  paragraph verbatim per the brief (measured 2026-08-25: 344 calls, 798,198
  input tokens, 89,281 output, $1.2446; plus the "no daily ceiling" paragraph
  explaining PASS_LIMIT's real theoretical maximum against the observed rate).
- Beyond the brief's file list, but required by the brief's own Step 2
  verification (`grep -rn "twenty cents\|1335" personal_apps/` — "Expected: no
  remaining hits outside the corrected docstring"), three more stale
  references to the same wrong numbers were found and fixed:
  - `personal_apps/tests/test_radar_llm_sentiment.py`:
    `test_the_model_is_haiku`'s docstring quoted "1335 scored mentions ...
    twenty cents"; replaced with the measured figures.
  - `personal_apps/static/radar/src/list/Spend.tsx`: the `usd()` formatter's
    doc comment justified its 3-decimal-place threshold by citing "twenty
    cents a day." The **logic itself was already correct** (handles `>= 1`
    and `< 1` separately, so it renders `$1.24` fine today) -- only the
    rationale comment was stale. Reworded to justify the threshold on its own
    terms without hanging it on a number that is now wrong by 6x.
  - `personal_apps/static/radar/src/list/Spend.test.tsx`: matching comment in
    `'drops to cents once there are dollars to round'`; the test's own
    assertions were already correct (uses `1.5` and `0.196` as example
    values, not the stale figure) and needed no change.

### Teeth
Docs/comments only, no behaviour change, no assertions added or altered in a
way that changes what passes or fails. No teeth applicable.

### Green
- `grep -rn "twenty cents\|1335" personal_apps/ --exclude-dir=node_modules` ->
  only the corrected docstring's own quoted reference to the old numbers (as
  the brief itself expects), plus two stale `.pyc` cache-file hits (not
  source).
- `python -m pytest tests/test_radar_llm_sentiment.py -q` -> `21 passed`.
- `npx vitest run -c vite.radar.config.ts static/radar/src/list/Spend.test.tsx`
  -> `1 file, 5 passed`.

### Commit
`5ba81e1` — `docs(radar): the tone pass costs six times what the docstring claimed`
Staged: `personal_apps/features/radar/llm_sentiment.py`,
`personal_apps/static/radar/src/list/Spend.test.tsx`,
`personal_apps/static/radar/src/list/Spend.tsx`,
`personal_apps/tests/test_radar_llm_sentiment.py`.

---

# Final verification gates (run after all four commits)

1. **Per-task focused gates**: reported inline above each task; all green,
   each preceded by an observed red.

2. **`python -m pytest tests/ -k radar -q`** (from `personal_apps/`, Vite
   manifest present):
   ```
   637 passed, 646 deselected, 2 warnings in 67.39s
   ```
   Baseline was 633 passed, 0 failures. +4 = Task 14's test, Task 15's test,
   Task 16's scoring test, Task 16's new leaderboard test (the other modified
   leaderboard test already existed in the 633 baseline and only gained
   assertions). Matches exactly.

3. **Frontend**:
   - `npx tsc --noEmit` -> clean, no output.
   - `npm run test` (both configs) -> gym: `32 files, 403 passed`; radar:
     `9 files, 84 passed`.
   - `npm run build` -> both Vite builds succeed;
     `static/radar/dist/.vite/manifest.json` present and current.

4. **Fresh-process imports** (from `personal_apps/`):
   ```
   python -c "from features.radar import buckets"    -> OK
   python -c "from features.radar import journal"     -> OK
   python -c "from features.radar import ingest"      -> OK
   python -c "from run_radar_ingest import build_fetchers" -> OK
   ```

5. **`flask db current`** / **`flask db heads`**:
   ```
   35c3ae366677 (head)
   ```
   Single head, no fork. This is the migration Task 16 added.

6. **`git diff` / `git status` at commit time**: working tree clean after
   each commit; `git diff f1dddee..HEAD | grep -in mutation` -> no matches.
   No leftover teeth mutations anywhere in the four commits.

---

# Resolution of the three "things the briefs may not tell you"

1. **`baseline_days` int -> float, migration needed.** Confirmed
   `RadarBucketSource.baseline_days` was `db.SmallInteger` at `models.py:712`
   before touching it. Added Alembic migration `35c3ae366677`, chained from
   `08316d3e4d77` (the branch's single head at task start), converting the
   column to `sa.Float()`; model and migration agree (both say Float).
   Applied with `flask db upgrade` against the local dev MySQL 8 database (not
   downgraded, per instructions). Verified live: running the scoring test
   *after* the scoring.py fix but *before* the migration produced
   `assert 0 < 0.0` (ORM said Float, DB column silently rounded 0.375 -> 0 on
   insert) -- direct evidence the migration is load-bearing, not cosmetic.

2. **Green/red are reserved for price direction; Task 15's indicator must not
   use them.** `Breakdown.tsx`'s own top-of-file comment already states this
   rule and notes a green/red tone bar "has been built and removed twice" for
   exactly this collision. The disagreement count was rendered as plain
   wording (`<b>{n}</b> read differently by the model`, `q`-class/muted,
   matching the neighbouring "carried no wording at all" span) inside the
   existing `<p className="wording">` block -- no colour introduced anywhere,
   consistent with the file's established pattern of describing bull/bear
   counts in words rather than a coloured bar.

3. **`'warming-up'` must be taught to the frontend or it is a repeat of Task
   14's defect.** Checked: `static/radar/src/list/ListPane.tsx` declares
   `UNIVERSAL: Record<Mark, string>` exhaustive over `Mark` on purpose (its
   own comment: "a new mark will not compile until someone decides what the
   board says when every row carries it") -- confirmed this is a real compile
   gate, not aspirational, by adding `'warming-up'` to the `Mark` union first
   and watching `tsc` fail with `Property '"warming-up"' is missing`. Taught
   it: added the `UNIVERSAL` entry, fixed `Finding`'s "baselines over 30 days"
   branch (which special-cased only `'provisional'` and would otherwise have
   repeated its own documented bug for the new mark), added a `MARK_WHY` entry
   for parity, and added `marks.test.tsx` coverage mirroring the existing
   `'provisional'` tests. The per-row rendering in `TickerRow.tsx` prints the
   raw mark string generically (no exhaustive switch there), so it needed no
   change and does not silently swallow a new mark.

---

# Concerns

- **Task 16 scoring test's supporting helper deviates from the brief's
  literal call.** See the "Resolution note" under Task 16 above: the brief's
  given `row(...)` call, if it reused `test_radar_buckets.row()` verbatim,
  would collapse all three `roll_up` calls onto one bucket (hour hardcoded to
  14 there) and make the final assertion false forever, not just before the
  fix -- confirmed with a standalone probe before writing any test code. Wrote
  a local `row()` for this file that also accepts `hour`, and passed
  `hour=hour` explicitly; the given docstring and final assertion are
  unchanged. Flagging this clearly in case a reviewer wants a different
  resolution.
- **`ListPane.tsx`'s `Finding` component has no dedicated test file.** The
  "baselines over 30 days" vs `UNIVERSAL[...]` branch (both the pre-existing
  `'provisional'` half and the `'warming-up'` half added this batch) is
  exercised only by the manual reasoning above, not a unit test -- there is no
  `ListPane.test.tsx` in the repo at all, and the `'provisional'` half of this
  same branch was equally untested before this batch. Left as-is rather than
  inventing new test-file scope beyond what the four briefs asked for; noting
  it here rather than silently leaving it.
- **`MARK_WHY` in `format.ts` is dead code.** Confirmed by grep: defined but
  never imported/consumed anywhere in the frontend. Added a `'warming-up'`
  entry for parity with its three siblings, but this does not make it live;
  pre-existing condition, not introduced by this batch.
- Everything else: no open issues. All six verification gates green, all
  teeth mutations observed failing and cleanly reverted, migration is a
  single head, fresh-process imports all succeed, working tree clean at each
  commit.

---

# Commits

| Task | SHA | Message |
|---|---|---|
| 14 | `9629a86` | `fix(radar): the panel's tone bar reads the verdicts it has been paying for` |
| 15 | `c9a4840` | `feat(radar): show where the model and the word list disagree` |
| 16 | `bc42187` | `fix(radar): provisional now means a thin baseline, not every row` |
| 17 | `5ba81e1` | `docs(radar): the tone pass costs six times what the docstring claimed` |

Status: **DONE**.

---

## Fix round 1

Independent review (`task-14-17-review.md`) returned **NEEDS_FIXES: 0
Critical, 2 Important, 3 Minor**. All five findings fixed. Started at HEAD
`5ba81e1` (clean); final HEAD `d7fc03d`.

### I1 — `phrasing.py`: fractional `baseline_days` rendered as a raw float

`read_clauses()` interpolated the unrounded float straight into the "read"
sentence: a 1-hour baseline read *"The baseline is 0.041666666666666664 days
old, not 30, so this rests on very little history."* — the exact population
`'warming-up'` was built to describe correctly.

**Fix** (`personal_apps/features/radar/phrasing.py:173-186`): branch instead
of interpolate. `baseline_days < 1` reads as `'under a day'`; otherwise round
to the nearest whole day (`round(baseline_days)`) and keep the existing
day/days singular rule. The hardcoded `"not 30"` comparison text is unchanged
(pre-existing, out of this finding's scope — `PROVISIONAL_BASELINE_DAYS` is
actually 14, not 30; not touched here).

**Tests added** (`personal_apps/tests/test_radar_phrasing.py`):
- `test_a_fractional_baseline_reads_as_words_not_a_raw_float` — `baseline_days=1/24`
  (one hour) must read exactly *"The baseline is under a day old, not 30, so
  this rests on very little history."*
- `test_a_multi_day_fractional_baseline_rounds_to_a_whole_day` — `baseline_days=2.7`
  must contain `"3 days"` and must not contain `"2.7"`.

Both pass: `python -m pytest tests/test_radar_phrasing.py -q` → `18 passed`
(16 pre-existing + 2 new).

### I2 — `detail_panel.py`: the disagreement-counting loop had zero integration coverage

The review mutation-tested the loop at `detail_panel.py:212-214` by replacing
its condition with `if False:` — a permanent no-op — and all 69 tests in
`test_radar_detail.py` + `test_radar_api.py` stayed green. Nothing drove
`breakdown_for` with real DB rows carrying a lexicon score AND a disagreeing
model verdict; both existing tests only exercised the pure `_tone_of` helper
or a hand-built `Breakdown` literal.

**Fix** — no production code changed (the logic was already correct, per the
review's own hand-verification); added test coverage:
- `personal_apps/tests/test_radar_detail.py`'s `post_for()` helper gained an
  `llm_sentiment=None` parameter, threaded into the `RadarMention` it builds,
  so a test can drive a real disagreeing row instead of a hand-built
  `Breakdown`.
- New test `test_the_breakdown_counts_real_disagreements_not_just_the_tone_helper`
  (uses the existing `panel_ticker` fixture, ticker `DTA`, cleaned up by the
  fixture's existing exact-prefix teardown): three real posts —
  - `'to the moon'` (lexicon bullish) + `llm_sentiment='bearish'` → model
    outranks and reverses the read → **counted**.
  - `'to the moon'` (lexicon bullish) + `llm_sentiment='bullish'` → agrees →
    not counted.
  - `'still holding'` (lexicon carried no directional word) +
    `llm_sentiment='bullish'` → the lexicon never took a side, so there is
    nothing to disagree *with* → not counted, even though its final tone
    differs from the model's.

  Asserts `detail_panel.build(...).breakdown.disagreements == 1` directly
  against `breakdown_for`'s real query path (through `build()`), not a stub.

Green: `python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -q`
→ `70 passed` (69 baseline + 1 new).

### M1 — migration `downgrade()` had no comment noting the data loss it causes

**Fix** (`personal_apps/migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py`):
added a comment above the `op.alter_column(...)` call in `downgrade()`
explaining that narrowing Float back to SMALLINT silently truncates any
fractional value written since the upgrade (e.g. `0.375` → `0`), reversing
the fix, and that it must not be run against a database carrying real scored
history. **Comment only — the downgrade was not executed.** Confirmed after:
`flask db current` / `flask db heads` both still report `35c3ae366677 (head)`.

### M2 — `leaderboard.py:259-260` `min(...)` lacked the `float()` coercion its siblings have

**Fix** (`personal_apps/features/radar/leaderboard.py:256-262`): wrapped the
generator's `part.baseline_days` in `float(...)`, matching the coercion
pattern the two aggregates above it already use, and extended the comment to
explain why (MIN/MAX don't promote to Decimal the way SUM does, but the
coercion removes the ambiguity for a future reader rather than relying on
that distinction silently — same reasoning the review used to judge this
"very likely benign" but worth hardening). No behaviour change on the local
MySQL 8 dev DB (verified: `test_radar_leaderboard.py` unaffected).

Green: `python -m pytest tests/test_radar_leaderboard.py -q` → `29 passed`
(unchanged from baseline — this is a defensive-only change, not a behaviour
fix, so no new test was added; a teeth mutation would not be meaningful here
since there is no observable-difference to assert against on this engine).

### M3 — pre-existing broad `LIKE 'ZZ%'` teardown hazard: six files, not five

Re-confirmed via `grep -rln "like('ZZ%')" personal_apps/tests/`: exactly six
files carry the literal pattern —`test_radar_bucket_sources.py`,
`test_radar_buckets.py`, `test_radar_daemon.py`, `test_radar_journal.py`,
`test_radar_retention.py`, `test_radar_universe.py`. This review's own count
(six) is correct; the brief that preceded it said five. **No code change**:
per the review's own recommendation, none of the six were touched (touching
them was explicitly out of scope — "do not go fix those five \[six\], they
are logged for final triage"). This entry corrects the count for whoever
does that final triage: **six files, not five**, none introduced or modified
by any commit in this batch (`9629a86`..`5ba81e1`..`d7fc03d`).

### Teeth table

| # | Assertion | Mutation | Command | Exact failure message | Reverted |
|---|---|---|---|---|---|
| 1 | `warn.text == 'The baseline is under a day old, ...'` (I1, fractional < 1 day) | Restored the pre-fix raw-float interpolation: `span = f'{baseline_days} day' if baseline_days == 1 else f'{baseline_days} days'` | `pytest tests/test_radar_phrasing.py -q -k fractional` | `AssertionError: assert 'The baseline...ttle history.' == 'The baseline...ttle history.'` — diff shows `- ... under a day ...` vs `+ ... 0.041666666666666664 days ...` | ✓ (`git diff --stat` on `phrasing.py` empty after; full suite re-confirmed 18 passed) |
| 2 | `'3 days' in warn.text` and `'2.7' not in warn.text` (I1, multi-day fractional) | Same mutation as #1 | Same command as #1 | `AssertionError: assert '3 days' in 'The baseline is 2.7 days old, not 30, so this rests on very little history.'` | ✓ (same revert) |
| 3 | `breakdown.disagreements == 1` (I2, the load-bearing one — **the reviewer's own `if False:` mutation, re-applied**) | `if llm is not None and lexicon_only is not None and tone != lexicon_only:` → `if False:  # MUTATION` | `pytest tests/test_radar_detail.py::test_the_breakdown_counts_real_disagreements_not_just_the_tone_helper -q` | `AssertionError: assert 0 == 1` (`b.disagreements` was `0`, `Breakdown(... bullish=3, neutral=2, bearish=1, disagreements=0 ...)`) | ✓ — confirmed via `git diff -- personal_apps/features/radar/detail_panel.py` returning **empty** after revert |

Re-ran the full pair (`test_radar_detail.py` + `test_radar_api.py`) under
mutation #3 to reproduce the reviewer's own observation from the other
direction: **69 passed, 1 failed** (only the new test caught it — the
existing 69 stayed green exactly as the review found, confirming this test
is the one that closes the gap). Reverted, re-ran: `70 passed`.

### Verification gates (fix round 1)

1. **Focused, per file touched**:
   - `pytest tests/test_radar_phrasing.py -q` → `18 passed`
   - `pytest tests/test_radar_detail.py tests/test_radar_api.py -q` → `70 passed`
   - `pytest tests/test_radar_leaderboard.py -q` → `29 passed`
   - `flask db current` / `flask db heads` → `35c3ae366677 (head)` (migration
     file only gained a comment; not re-applied, nothing to re-verify beyond
     head state)

2. **`python -m pytest tests/ -k radar -q`** (from `personal_apps/`):
   ```
   640 passed, 646 deselected, 2 warnings in 67.60s
   ```
   Baseline was 637 passed. +3 = I1's two new phrasing tests + I2's one new
   detail test. Same 2 pre-existing `utcnow()` deprecation warnings as
   before this round (unrelated, SQLAlchemy-internal). Vite manifest was
   present, so 0 of the "2 permitted template failures" applied.

3. **Frontend** (no frontend files touched this round; run for completeness):
   - `npx tsc --noEmit` → clean, no output.
   - `npx vitest run -c vite.radar.config.ts` → `9 test files, 84 tests passed`.
   - `npm run build` → both Vite builds succeed (gym: 20 chunks; radar:
     `board-398cO68g.js`); `static/radar/dist/.vite/manifest.json`
     regenerated.

4. **Fresh-process imports** (from `personal_apps/`):
   ```
   python -c "from features.radar import buckets"              -> OK
   python -c "from features.radar import journal"               -> OK
   python -c "from features.radar import ingest"                 -> OK
   python -c "from run_radar_ingest import build_fetchers"        -> OK
   ```

5. **`flask db current`** / **`flask db heads`**:
   ```
   35c3ae366677 (head)
   ```
   Single head, no fork. Downgrade was NOT run (M1 was a comment-only fix).

6. **`git diff` / `git status` at commit time**: `git diff | grep -in mutation`
   → no matches (exit 1). `git status --short` before commit showed exactly
   the 5 intended files, nothing else.

### Commit

`d7fc03d` — `fix(radar): a baseline measured in hours reads like one`
Staged (5 files): `personal_apps/features/radar/leaderboard.py`,
`personal_apps/features/radar/phrasing.py`,
`personal_apps/migrations/versions/35c3ae366677_widen_radar_bucket_sources_baseline_days.py`,
`personal_apps/tests/test_radar_detail.py`,
`personal_apps/tests/test_radar_phrasing.py`.

### Concerns

- None outstanding. All five findings fixed; the two Important ones each
  carry a teeth mutation reproduced independently (I1: the pre-fix raw-float
  format; I2: the reviewer's own `if False:` mutation) with exact failure
  messages recorded above and every mutation cleanly reverted
  (`git diff` empty on both touched-then-reverted files: `phrasing.py` shows
  only the intended fix, `detail_panel.py` shows no diff at all).
- M2's fix is defensive-only (no observable behaviour change on this MySQL 8
  dev DB, consistent with the review's own "very likely benign" finding) —
  no new test was added for it, matching M1's treatment (a hardening/
  documentation fix, not a behaviour fix).
- M3 required no code change; the six-file count is now correctly recorded
  here for whoever performs the final `LIKE 'ZZ%'` teardown-hazard triage
  the review deferred.

Status: **DONE**.
