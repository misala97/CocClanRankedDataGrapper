# Task 18-19 report

Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`, started at HEAD `5b91a9d`

---

## Task 18: The discovery script stops fighting the daemon

### What changed

`personal_apps/scripts/discover_reddit_sources.py`:
- Added `_daemon_is_running()` — checks `shutil.which('systemctl')` first (returns
  `False` immediately if absent, e.g. on Windows dev machines), otherwise runs
  `systemctl is-active radar_ingest` and compares stdout to `'active'`.
- `main()` signature changed to `main(argv=None)`, parses with
  `parser.parse_args(argv)`.
- Added `--anyway` flag (`action='store_true'`).
- Immediately after arg parsing, refuses (`return 1`, prints stop/override
  guidance to stderr) when `_daemon_is_running() and not args.anyway` — this
  check happens **before** `with app.app_context():`, so refusal never enters
  the app context.
- `if __name__ == '__main__':` now does `sys.exit(main() or 0)`.

New file `personal_apps/tests/test_radar_discovery.py` — 4 behavioral tests,
none of which execute a real discovery pass (no network, sleep, DB or
filesystem write; `personal_apps/reddit_candidates.json` was never touched —
confirmed via `git status --porcelain` before/after, which shows only the
script diff and the new test file, no candidates-file change).

### Red output (first run, before implementation)

```
tests/test_radar_discovery.py::test_absent_systemctl_means_not_running_and_never_shells_out FAILED
tests/test_radar_discovery.py::test_an_active_daemon_is_detected_via_the_exact_argv FAILED
tests/test_radar_discovery.py::test_main_refuses_before_entering_the_app_context_when_daemon_runs FAILED
tests/test_radar_discovery.py::test_anyway_proceeds_past_the_guard_when_daemon_runs FAILED

E       AttributeError: module 'scripts.discover_reddit_sources' has no attribute '_daemon_is_running'
(repeated for all four tests -- the guard and flag did not exist yet)
4 failed in 1.97s
```

After implementation, all 4 pass:
```
tests/test_radar_discovery.py::test_absent_systemctl_means_not_running_and_never_shells_out PASSED
tests/test_radar_discovery.py::test_an_active_daemon_is_detected_via_the_exact_argv PASSED
tests/test_radar_discovery.py::test_main_refuses_before_entering_the_app_context_when_daemon_runs PASSED
tests/test_radar_discovery.py::test_anyway_proceeds_past_the_guard_when_daemon_runs PASSED
4 passed in 0.10s
```

### How the guard was tested without running a real discovery pass

- **Absent systemctl / active daemon** tests exercise the real
  `_daemon_is_running()` directly, monkeypatching only `shutil.which` and
  `subprocess.run` (patched on the real `shutil`/`subprocess` modules, which
  the function's local `import shutil` / `import subprocess` resolve to via
  `sys.modules` — same object, so the patch is visible either way). No real
  subprocess is spawned.
- **Refusal / `--anyway`** tests monkeypatch `discovery._daemon_is_running`
  directly to `lambda: True` (isolating `main()`'s behavior from the
  systemctl mechanics, which the two tests above already cover), and replace
  `discovery.app` with a fake object (`_FakeApp`) whose `.app_context()`
  increments a counter instead of opening a real Flask/DB context — so
  "does not enter the app context" is an observable assertion
  (`fake_app.entered == 0`), not an inference.
  - The refusal test also patches `sys.stderr` to capture the printed
    guidance text and asserts on its content.
  - The `--anyway` test additionally stubs `CANDIDATES` to `[]` (so the
    fetch/sleep loop body never runs), `universe.load_lookup` to `lambda: {}`
    (no DB query), and `discovery.open` to `unittest.mock.mock_open()` (no
    real file is opened or written) — verified with
    `fake_open.assert_called_once_with('reddit_candidates.json', 'w', encoding='utf-8')`,
    proving the write path was reached without ever touching disk.

### Teeth

| # | Assertion | Mutation | Exact failure message | Reverted |
|---|---|---|---|---|
| 1 | `discovery._daemon_is_running() is True` (active-daemon detection) | In `_daemon_is_running`, replaced `return result.stdout.strip() == 'active'` with `return False` | `assert False is True`<br>`where False = <function _daemon_is_running ...>()` | ✓ (confirmed via `git diff` showing only the intended additions afterward) |
| 2 | `result != 1` (`--anyway` overrides the guard) | In `main()`, changed `if _daemon_is_running() and not args.anyway:` to `if _daemon_is_running():` | `assert 1 != 1` | ✓ |

Both mutations were applied with `Edit`, the affected test file re-run to
capture the exact failure, then reverted with `Edit` back to the original
text (confirmed clean via `git diff`).

### Commit

`fix(radar): the discovery script yields to the running daemon` — see final
SHA at the end of this report.

---

## Task 19: Prune the journal

### Shared-DB safety approach (read this before the rest)

`prune_mention_events`'s own delete query is unscoped by ticker (it is the
real production pruner, not a test helper) -- it deletes every row across the
whole table whose `created_utc` is older than the cutoff. Before writing any
test, I queried the real shared dev database directly:

```
total= 1432
min created_utc= 2026-08-22 20:03:00
max created_utc= 2026-08-23 20:00:00
```

Every real row is from 2026-08-22/23. The test (per the brief) calls
`prune_mention_events(now)` with a fixed historical `now = dt.datetime(2026,
4, 20, 12, 0, 0)`. With `MENTION_EVENT_RETENTION_HOURS = 48`, cutoff is
2026-04-18 12:00 -- four months before any real row -- so `created_utc <
cutoff` can never match a real row regardless of how the fixture's own
teardown behaves. This holds for the intended mutation testing too, as long
as `now` stays in the test's fixed past and the mutation never inverts the
comparison to `>` (see the abandoned mutation below).

On top of that, I did **not** reuse the existing `clean_events` fixture from
`test_radar_journal.py` (`RadarMentionEvent.query.filter(ticker.like('ZZ%'))`)
-- that pattern is one of the pre-existing broad-sweep hazards flagged for
final triage, and I was told not to add a sixth file using it. I wrote a new,
narrower `clean_events` fixture local to `test_radar_retention.py` that
cleans up by **exact identity** (`ticker == 'ZZA'` AND `external_id IN
('zz-new', 'zz-old')`), before and after.

### Before/after real-row counts

| Checkpoint | `radar_mention_events` count |
|---|---|
| Before any Task 19 work (baseline) | 1432 |
| After the red run (function missing, `AttributeError` before any delete) | 1432 |
| After the green run (implementation in place, single focused test) | 1432 |
| After teeth mutation A (cutoff = now, ignoring retention hours) | 1432 |
| After teeth mutation C (count accumulator broken) | 1432 |
| After `pytest tests/test_radar_daemon.py` (updated `_scheduled_prune` wiring) | 1432 |
| After `pytest tests/ -k radar -q` (645 passed) | 1432 |

No real row was ever touched. `min`/`max` `created_utc` were also re-checked
after the full radar run and were unchanged.

### What changed

- `personal_apps/features/radar/retention.py`: added `RadarMentionEvent` to
  the `models` import and `MENTION_EVENT_RETENTION_HOURS` to the `.config`
  import; added `prune_mention_events(now, chunk_size=5000, pause=...)`
  exactly per the brief -- chunked delete by `id`, ordered by `created_utc`,
  looping until a chunk comes back empty, returning a plain Python `int`
  (`total` is built entirely from `len(ids)`, never a SQL `COUNT()`/`SUM()`,
  so there is no MySQL/MariaDB `Decimal` boundary to cross here).
- `personal_apps/run_radar_ingest.py`: `_scheduled_prune` now also calls
  `retention.prune_mention_events(now)` and logs the count when nonzero,
  appended after the existing posts/quotes pruning.
- `personal_apps/tests/test_radar_retention.py`: added the brief's test
  (`test_the_journal_is_pruned_by_when_the_post_was_written`) plus the new
  exact-identity `clean_events` fixture, and an `isinstance(deleted, int)`
  assertion alongside the count check.
- `personal_apps/tests/test_radar_daemon.py`: **updated the pre-existing**
  `test_the_nightly_prune_covers_quotes_as_well_as_posts` to also fake
  `daemon.retention.prune_mention_events` (previously it faked only
  `prune_posts`/`prune_quotes`). This was not explicitly in the brief, but it
  was necessary: once `_scheduled_prune` calls the real pruner, this
  pre-existing test would otherwise invoke the REAL `prune_mention_events`
  with the REAL current time against the shared dev DB -- and since real
  journal rows are already older than 48 hours by the time this suite runs,
  that unfaked call would have deleted all 1432 real rows the first time the
  daemon suite ran after this change. Caught by reading the test before
  running it, not by an incident.

### Red output (first run, before implementation)

```
tests/test_radar_retention.py::test_the_journal_is_pruned_by_when_the_post_was_written FAILED

    deleted = retention.prune_mention_events(now)
E       AttributeError: module 'features.radar.retention' has no attribute 'prune_mention_events'

1 failed in 1.96s
```

After implementation: `6 passed in 0.50s` (all of `test_radar_retention.py`).

### Teeth

| # | Assertion | Mutation | Exact failure message | Reverted |
|---|---|---|---|---|
| A | `deleted == 1` (only the row past the retention window is removed) | `cutoff = now  # ignoring MENTION_EVENT_RETENTION_HOURS entirely` (was `now - dt.timedelta(hours=MENTION_EVENT_RETENTION_HOURS)`) | `assert 2 == 1` | ✓ |
| C | `deleted == 1` (the returned count reflects what was actually deleted) | `total += 0` (was `total += len(ids)`) -- the delete itself still ran correctly, only the reported count was wrong | `assert 0 == 1` | ✓ |

Both confirmed via `git diff features/radar/retention.py` afterward, which
shows only the intended `prune_mention_events` addition (no stray mutation
text left behind).

**A third mutation was planned and deliberately abandoned before running
it**: flipping `created_utc < cutoff` to `created_utc > cutoff`, to try to
prove the "correct row survives" half of the assertion
(`remaining == ['zz-new']`) independently of the count. On inspection this
mutation is unsafe: with `>`, the filter would match every real row in
`radar_mention_events` too (2026-08-22/23 is after the test's April 2026
cutoff either way), and the chunked loop deletes everything matching until a
chunk comes back empty -- i.e. it would delete all 1432 real rows the moment
it ran, test-scoped `now` or not, because the query itself carries no ticker
scope. I reverted the edit before ever executing it and used mutation C
instead, which is bounded by the same (correct, safe) `<` comparison and only
breaks the return-value bookkeeping.

### Verification gates

1. **Focused, red then green** -- shown above for both tasks.
2. **`python -m pytest tests/ -k radar -q`**:
   ```
   645 passed, 646 deselected, 2 warnings in 79.34s
   ```
   Baseline was 640; +5 for the 4 new discovery tests and 1 new retention
   test = 645, matches exactly. `static/radar/dist/.vite/manifest.json` was
   present in this run (confirmed with `ls`), so the "exactly two permitted
   API template failures" clause does not apply here -- 0 failures is the
   correct outcome, not 2.
3. **Fresh-process imports** (all from `personal_apps/`):
   ```
   python -c "from features.radar import buckets"       -> OK
   python -c "from features.radar import journal"       -> OK
   python -c "from features.radar import ingest"        -> OK
   python -c "from run_radar_ingest import build_fetchers" -> OK
   ```
4. **`flask db current` / `flask db heads`**:
   ```
   35c3ae366677 (head)
   35c3ae366677 (head)
   ```
   Single head, unchanged from before this batch.
5. **Real-row count check** -- see table above: 1432 before, 1432 after,
   throughout every step of this batch.
6. **`git diff` clean of teeth mutations** -- confirmed after each mutation
   was reverted, and again at commit time (see final `git diff`/`git show`
   before committing, below).

`npm run build` (from `personal_apps/`) also succeeded:
```
✓ 134 modules transformed  (gym)
✓ 39 modules transformed   (radar)
built in 2.25s / 1.63s
```

Full un-filtered `python -m pytest tests/ -q` was also run as an extra check
beyond the required radar-scoped gate:
```
1291 passed, 1193 warnings in 197.93s (0:03:17)
exit code 0
```
No failures anywhere in the whole suite (the warnings are all the
pre-existing, unrelated `datetime.utcnow()` deprecation notices in the gym
suites). Real-row count re-checked immediately after: still 1432.

### Commit

`feat(radar): prune the journal past its retention window` -- `6f1afa8`.

---

## Final state

- **Commits**: `6d098e7` (Task 18), `6f1afa8` (Task 19), both on
  `codex/radar-pipeline-audit`, working tree clean afterward
  (`git status --porcelain` empty).
- **`radar_mention_events` real-row count**: 1432 before this entire batch,
  1432 after -- checked at seven separate checkpoints (baseline, post-red,
  post-green, after each of the two teeth mutations, after the daemon suite,
  after the full radar-scoped suite, and after the full unfiltered suite);
  never changed.
- **Gate summary**:
  1. Focused red-then-green: both tasks, shown above.
  2. `python -m pytest tests/ -k radar -q`: `645 passed, 646 deselected` (640
     baseline + 5 new tests). Vite manifest was present, so 0 permitted
     failures applies (not the 2-failure exception).
  3. Fresh-process imports (`buckets`, `journal`, `ingest`, `build_fetchers`):
     all OK.
  4. `flask db current` / `flask db heads`: single head `35c3ae366677`,
     unchanged.
  5. Real-row count: 1432 -> 1432 (table above).
  6. `git diff` after each teeth mutation was reverted showed only the
     intended additions -- confirmed clean at commit time via the `git diff`
     output shown above and the final `git status --porcelain` (empty).
  - Bonus: full unfiltered `pytest tests/ -q`: `1291 passed`, exit 0.
  - Bonus: `npm run build`: both `gym` and `radar` bundles built
    successfully.

### Concerns / notes for the final whole-branch review

- The pre-existing `test_the_nightly_prune_covers_quotes_as_well_as_posts` in
  `test_radar_daemon.py` had to be modified beyond what either brief
  specified, because wiring `prune_mention_events` into `_scheduled_prune`
  (exactly as Task 19 asks) would otherwise have made that unmodified,
  already-committed-style test call the real pruner with real wall-clock
  time against the shared dev database on every future run of the daemon
  suite -- a live hazard from this point forward if anyone reverted just my
  test change while keeping the `_scheduled_prune` wiring. Flagging this
  explicitly since it's outside the two files each brief named for that
  test's home file, even though it is fully in-scope for Task 19's own
  change.
- The five (now six, including `test_radar_retention.py`'s pre-existing
  `RadarBucket.query.filter(ticker.like('ZZ%'))` teardown in the `aged_posts`
  fixture) files with the broad `LIKE 'ZZ%'` teardown hazard were left
  untouched, per instructions -- they are logged for the final whole-branch
  triage, not this batch.
- No other concerns. Both tasks' behavior matches their briefs; the only
  deviation from the literal brief text is the safety-motivated
  `clean_events` fixture (exact-identity instead of the brief's presumed
  reuse of the `LIKE 'ZZ%'` fixture) and the abandoned unsafe third teeth
  mutation for Task 19, both explained above.

---

## Fix round 1

Independent review (`task-18-19-review.md`, range `5b91a9d..6f1afa8`) returned
`NEEDS_FIXES: 0 Critical, 1 Important, 2 Minor`. All three addressed below.
No redesign of the batch's behavior — only the review's findings were touched.

### Finding 1 (Important) — the retention-window boundary was untested

**File**: `personal_apps/tests/test_radar_retention.py`
(`test_the_journal_is_pruned_by_when_the_post_was_written` +
`clean_events` fixture).

The reviewer had mutated `created_utc < cutoff` to `<= cutoff` (safely, inside
the test's own April-2026 window) and the whole `test_radar_retention.py`
suite still passed — the exact-cutoff boundary was never exercised.

**Fix**: added a third row to the existing test, at
`created_utc = now - timedelta(hours=retention.MENTION_EVENT_RETENTION_HOURS)`
— i.e. sitting at exactly the cutoff, still inside the test's fixed
April-2026 `now`, months away from the real Aug-2026 dev rows. Under the
implementation's strict `<` semantics this row has not yet aged out, so it
must survive. Extended `clean_events`'s exact-identity teardown tuple to
include the new `'zz-boundary'` ident (still exact-identity, not a `LIKE`
sweep). Switched the `remaining` assertion from a list to a set comparison
since two rows now survive and query order isn't guaranteed.

### Finding 2 (Minor) — weak assertion in the `--anyway` test

**File**: `personal_apps/tests/test_radar_discovery.py:92`
(`test_anyway_proceeds_past_the_guard_when_daemon_runs`).

Changed `assert result != 1` to `assert result in (None, 0)`, matching the
reviewer's suggested tightening. (The reviewer noted this was cosmetic — the
real proof of "proceeded past the guard" was already `fake_app.entered >= 1`
plus the `fake_open.assert_called_once_with(...)` call, both untouched.)

### Finding 3 (Minor) — `prune_mention_events` sleeps once more than necessary

**File**: `personal_apps/features/radar/retention.py:105-136`.

Added the same short-circuit `prune_posts` already has: `if len(ids) <
chunk_size: break` immediately after `total += len(ids)`, before the `pause`
check. Brings `prune_mention_events`'s tail behavior in line with
`prune_posts` — no sleep after the loop's final (necessarily partial) chunk.

### Teeth table (this round)

| # | Finding | Assertion | Mutation | Exact failure message | Reverted |
|---|---|---|---|---|---|
| Boundary | 1 (Important) | `deleted == 1` / `remaining == {'zz-new', 'zz-boundary'}` | In `prune_mention_events`, `created_utc < cutoff` → `created_utc <= cutoff` | `assert 2 == 1` at `tests\test_radar_retention.py:149` | Yes — `git diff personal_apps/features/radar/retention.py` after revert showed only the Finding-3 short-circuit addition, no `<=` left behind |

Reproduced exactly as the review specified: mutate `<`→`<=`, run the boundary
test (not the whole file, to isolate the signal), capture the failure,
revert, re-run to confirm green again, confirm `git diff` clean.

### Before/after `radar_mention_events` real-row counts (this round)

| Checkpoint | count | min `created_utc` | max `created_utc` |
|---|---|---|---|
| Before any fix-round-1 work | 1432 | 2026-08-22 20:03:00 | 2026-08-23 20:00:00 |
| After adding the boundary row + green run | 1432 | (unchanged) | (unchanged) |
| After the `<`→`<=` teeth mutation run (boundary test only) | 1432 | (unchanged) | (unchanged) |
| After revert + full `pytest tests/ -k radar -q` | 1432 | 2026-08-22 20:03:00 | 2026-08-23 20:00:00 |

No real row touched at any point. Matches the review's own 1432/1432.

### Gates (this round)

1. Covering tests for all three touched files
   (`test_radar_retention.py`, `test_radar_discovery.py`,
   `retention.py`): `python -m pytest tests/test_radar_retention.py
   tests/test_radar_discovery.py -v` → **10 passed**.
2. `python -m pytest tests/ -k radar -q` (from `personal_apps/`) →
   **645 passed, 646 deselected, 2 warnings** — matches the 645 baseline
   exactly. `static/radar/dist/.vite/manifest.json` is present in this
   worktree, so the 2-permitted-failure exception does not apply — 0
   failures is correct, and that's what happened.
3. `flask db current` / `flask db heads` → `35c3ae366677 (head)` both before
   and after — single head, unchanged. No downgrade run.
4. `radar_mention_events`: **1432 → 1432** (table above).
5. `git diff` at commit time: staged exactly the three touched files
   (`retention.py`, `test_radar_discovery.py`, `test_radar_retention.py`);
   no leftover `<=` or any other mutation text — confirmed by reading the
   full diff before staging.

### Commit

`test(radar): pin the retention cutoff boundary` — `200bde3`, on
`codex/radar-pipeline-audit` (parent `6f1afa8`). Working tree clean
afterward.

### Concerns for final triage

None new. The three pre-existing broad `LIKE 'ZZ%'` teardown hazards the
review confirmed (`aged_posts` in `test_radar_retention.py`,
`test_prepare_rollup_generation_fails_closed_on_unrecovered_legacy_evidence`
in `test_radar_daemon.py`, plus whichever others the whole-branch triage
already tracks) remain untouched, per the standing instruction not to fix
them in this batch.

