# Review: Tasks 18-19 (Radar pipeline audit-and-fix, final batch)

Reviewer: independent (subagent), no prior authorship of this diff.
Range reviewed: `5b91a9d..6f1afa8` (`6d098e7` Task 18, `6f1afa8` Task 19).
Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`, HEAD confirmed `6f1afa8913363eb4d0991813bb21bf64c1377035` throughout and after review.

All claims below were independently re-derived (re-run, re-counted, or re-mutated) rather than taken from the implementer's report. Where I reproduced a claim exactly, I say so; where I found something the report did not surface, it is called out as a finding.

---

## 1. Spec compliance per task

### Task 18 — discovery script yields to the daemon

`personal_apps/scripts/discover_reddit_sources.py`:

- `_daemon_is_running()` added exactly as specified: `shutil.which('systemctl') is None` short-circuits to `False` before any subprocess is spawned; otherwise `subprocess.run(['systemctl', 'is-active', 'radar_ingest'], capture_output=True, text=True)` (list argv, no `shell=True`) and compares `result.stdout.strip() == 'active'`.
- `main(argv=None)` + `parser.parse_args(argv)` — matches the brief's requirement for direct behavioral tests instead of `sys.argv` patching.
- `--anyway` flag added (`action='store_true'`).
- Guard placed immediately after `parser.parse_args(argv)` and strictly **before** `with app.app_context():`. Verified structurally (guard's `return 1` is textually and functionally before the app-context block) and behaviorally (see teeth, §4).
- `if __name__ == '__main__': sys.exit(main() or 0)` — correct exit-code plumbing.
- Stop/override guidance printed to `stderr` (not stdout) via `print(..., file=sys.stderr)`.

New file `personal_apps/tests/test_radar_discovery.py` (4 tests) covers exactly the four behaviors the hardened brief demanded: absent-systemctl, active-daemon-detected-via-exact-argv, refusal-before-app-context, and `--anyway`-override. Confirmed no network/DB/filesystem/sleep in any test — see §2.

**Verdict: Task 18 fully compliant.**

### Task 19 — prune the journal

`personal_apps/features/radar/retention.py`: `prune_mention_events(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS)` added verbatim to the brief's Step 3 code block — chunked `SELECT id ... WHERE created_utc < cutoff ORDER BY created_utc LIMIT chunk_size`, `DELETE ... WHERE id IN (ids)`, commit per chunk, loop until a chunk is empty, `total` accumulated from `len(ids)`. Both `.filter()`/`.limit()`/`.in_()` and the chunked-delete-then-commit shape are standard SQL constructs valid on MySQL 8 and MariaDB alike — no CTEs, no engine-specific syntax, no window functions in this function (unlike `prune_quotes`, which is untouched by this batch).

`personal_apps/run_radar_ingest.py`, `_scheduled_prune`: three added lines call `retention.prune_mention_events(now)` and log the count when nonzero, appended after the pre-existing posts/quotes pruning — matches the brief exactly.

`personal_apps/tests/test_radar_retention.py`: brief's test added verbatim, plus a new exact-identity `clean_events` fixture (not the brief's presumed reuse of a broader fixture — see §2, this is the right call).

**Verdict: Task 19 functionally compliant, but see Finding 1 (§6) — a real boundary-test gap that neither brief nor implementer caught.**

---

## 2. Shared-DB safety audit

### My own counts (independently run, not copied from the report)

| Checkpoint (mine) | `radar_mention_events` count | min `created_utc` | max `created_utc` |
|---|---|---|---|
| Before touching anything | 1432 | 2026-08-22 20:03:00 | 2026-08-23 20:00:00 |
| After `pytest tests/ -k radar -q` (645 passed) | 1432 | 2026-08-22 20:03:00 | 2026-08-23 20:00:00 |
| After my own mutation-teeth reproduction (below) | 1432 | 2026-08-22 20:03:00 | 2026-08-23 20:00:00 |

All three match the implementer's reported 1432→1432 exactly. **Confirmed independently: no real row was touched.**

### Structural vs incidental

- `prune_mention_events`'s own query is genuinely unscoped by ticker — it is the real production pruner. Safety therefore has to come from the *test's* choice of `now`, not from any row-level scoping in the function under test.
- The test fixes `now = dt.datetime(2026, 4, 20, 12, 0, 0)`. With `MENTION_EVENT_RETENTION_HOURS = 48`, cutoff is 2026-04-18 12:00 — **structurally** four months before the real dev data's earliest row (2026-08-22 20:03). This is not luck: the real rows would have to predate April 2026 to be at risk, and the real ingest daemon has only existed since August 2026, so there is no plausible way for the dev DB to grow rows that old. This is structural safety, not incidental — confirmed by my own count checks at every stage, including after deliberately re-running both retained mutations (§4).
- The new `clean_events` fixture cleans up by **exact identity** (`ticker == 'ZZA' AND external_id IN ('zz-new', 'zz-old')`), not a `LIKE 'ZZ%'` sweep. Correct per the standing constraint, and a real improvement over the pattern used elsewhere in this codebase.
- The implementer explicitly declined to reuse the existing broad `clean_events`/`aged_posts`-style fixture from other test files, citing the standing "no sixth hazard file" instruction. Correct call.

### Pre-existing hazards encountered (not introduced by this batch)

Confirmed via diff inspection (context lines only, no `+` prefix) that these predate `5b91a9d` and were not modified by either task commit:

- `personal_apps/tests/test_radar_retention.py`, `aged_posts` fixture (lines 20-44, pre-existing): teardown does `RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(...)`. The implementer's report flags this explicitly as a hazard it noticed but correctly left untouched (out of scope for this batch), while helpfully surfacing it for the final whole-branch triage. I confirm it is unchanged by this diff.
- `personal_apps/tests/test_radar_daemon.py`, `test_prepare_rollup_generation_fails_closed_on_unrecovered_legacy_evidence` (further down the file, untouched by this diff): `RadarBucketSource.query.filter(RadarBucketSource.ticker.like('ZZ%'))`. Also pre-existing, also untouched.

**This batch added no new broad-`LIKE 'ZZ%'` teardown.** Its one new fixture (`clean_events`) uses exact identity.

---

## 3. Concern adjudication (the implementer's two flagged concerns)

### Concern 1: patching the pre-existing `test_the_nightly_prune_covers_quotes_as_well_as_posts` in `test_radar_daemon.py`

**Claim**: unfaked, this test would call the real `prune_mention_events` with real wall-clock time against the shared dev DB, deleting all real rows, because they are already older than 48h.

**Verified true.** The real rows run 2026-08-22/23; today (per environment) is 2026-08-27 — already ~4-5 days past the 48-hour window. `_scheduled_prune` (as wired by this very batch) now unconditionally calls the real `retention.prune_mention_events(now)` unless faked. The pre-existing test called `daemon._scheduled_prune()` directly with only `prune_posts`/`prune_quotes` faked; after Task 19's wiring change this would reach the real pruner on every future run of this test file. This is a genuine, immediate hazard introduced by Task 19's *correct* implementation of what the brief asked for, not a hypothetical.

**Shape of the fix**: mirrors the exact pattern the test already used for `prune_posts`/`prune_quotes` (save-real/install-fake/try-finally-restore), extended uniformly to the third pruner. Does not hollow out the test — the assertion `called == ['posts', 'quotes', 'events']` still exercises the same regression the test exists for (a pruner that exists but is never reached), now covering all three instead of two.

**Scope justification**: `test_radar_daemon.py` was not in Task 19's file list, but the change is a direct, necessary consequence of the one file that *was* listed (`run_radar_ingest.py`). Modifying it was the right call, not scope creep. Confirmed by my own read of the test and the wiring change.

### Concern 2: abandoning the unsafe `>` mutation and substituting `total += 0`

**Claim**: flipping `created_utc < cutoff` to `created_utc > cutoff` would, if actually run, match every real row in `radar_mention_events` (all from Aug 2026, which is unconditionally `>` an April 2026 cutoff) and the chunked loop would delete all of them regardless of the test's own scoping, since the query itself carries no ticker filter.

**Verified true and the right call.** I did not re-attempt this mutation for real (correctly, per the implementer's own reasoning, which holds). The implementer's judgment to abandon it before executing was sound engineering under exactly the failure mode this review was primed to look for.

**But**: I independently checked whether the *substitute* mutation (`total += 0`, i.e. testing return-value bookkeeping) covers what the abandoned `>` mutation would have covered — the comparison operator's correctness at the boundary. **It does not.** See Finding 1 below: I mutated `<` to `<=` myself (safely, within the test's own April-2026 scope) and the full `test_radar_retention.py` suite (all 6 tests) still passed. The boundary is genuinely unpinned. The implementer's report does not claim otherwise — it only discusses the abandoned `>` flip, not a same-direction, safe `<`-vs-`<=` check — so this is a real gap, not a contradiction of anything claimed.

---

## 4. Teeth audit — independently reproduced

All four required mutations were reproduced by me from scratch (Edit → run → capture failure → revert → confirm `git diff` clean), not copied from the report.

| # | Task | Assertion | Mutation | Exact failure (mine) | Matches report | Reverted |
|---|---|---|---|---|---|---|
| 1 | 18 | `discovery._daemon_is_running() is True` | `return result.stdout.strip() == 'active'` → `return False` | `assert False is True` / `where False = <function _daemon_is_running ...>()` | Yes, verbatim | ✓ (`git diff` empty) |
| 2 | 18 | `result != 1` (`--anyway` override) | `if _daemon_is_running() and not args.anyway:` → `if _daemon_is_running():` | `assert 1 != 1` | Yes, verbatim | ✓ (`git diff` empty) |
| A | 19 | `deleted == 1` | `cutoff = now - dt.timedelta(hours=...)` → `cutoff = now` | `assert 2 == 1` | Yes, verbatim | ✓ (`git diff` empty) |
| C | 19 | `deleted == 1` | `total += len(ids)` → `total += 0` | `assert 0 == 1` | Yes, verbatim | ✓ (`git diff` empty) |

Real-row count checked after each of the above (mutation A in particular actually executes a delete against the real table with a fixed-past `now`, so it was the one worth checking): stayed at 1432 throughout.

### Additional mutation I ran that the implementer did not (boundary probe)

Mutated `RadarMentionEvent.created_utc < cutoff` → `<= cutoff` (safe: still scoped by the test's own April-2026 `now`, nowhere near real Aug-2026 data — verified real-row count unaffected before running). Result: **`python -m pytest tests/test_radar_retention.py -q` → `6 passed`, no failure.** The full existing test suite for this file does not notice this mutation at all. Reverted; `git diff` confirmed clean afterward.

This confirms Finding 1 (§6): the exact retention-window boundary is untested, and a safe substitute mutation that would have caught it was available but not used.

---

## 5. Gates

1. **`python -m pytest tests/ -k radar -q`** (from `personal_apps/`): my run → `645 passed, 646 deselected, 2 warnings in 88.20s`. Matches the implementer's reported 645 (640 baseline + 5 new) exactly. `static/radar/dist/.vite/manifest.json` **is present** in this worktree, so the 2-permitted-failure exception does not apply — 0 failures is correct, and that's what I got.
2. **Fresh-process imports** (from `personal_apps/`): `features.radar.buckets`, `features.radar.journal`, `features.radar.ingest`, `run_radar_ingest.build_fetchers`, `features.radar.retention`, `scripts.discover_reddit_sources` — all import cleanly in isolated `python -c` invocations.
3. **`flask db current` / `flask db heads`**: both report `35c3ae366677 (head)` — single head, unchanged. No downgrade run.
4. **My own before/after `radar_mention_events` count**: 1432 → 1432, confirmed at multiple independent checkpoints (see §2 and §4), including immediately after my own from-scratch mutation reproduction of mutation A (the one mutation that actually deletes rows).

Also spot-verified: `python -c ...; from scripts.discover_reddit_sources import _daemon_is_running; print(_daemon_is_running())` → `False` on this Windows machine, as required.

`personal_apps/reddit_candidates.json` does not exist anywhere in this worktree (never created here) — confirms no real discovery pass ever ran during this batch's test suite. `personal_apps/scripts/discover_telegram_sources.py` and `personal_apps/telegram_candidates.json` are unmodified (`git status --short` clean throughout, `git log` last touched 2026-08-23, well before this batch).

---

## 6. Findings

### Finding 1 — Important: the retention-window boundary is untested (`<` vs `<=` at `created_utc == cutoff`)

- **File**: `personal_apps/features/radar/retention.py:122` (`prune_mention_events`'s filter), test gap in `personal_apps/tests/test_radar_retention.py:119-141`.
- **Summary**: `test_the_journal_is_pruned_by_when_the_post_was_written` places its two rows at `now - 1h` (deep inside the 48h window) and `now - 72h` (deep outside it). No row sits at or near `now - 48h` exactly. I independently mutated the implementation's `created_utc < cutoff` to `created_utc <= cutoff` and the entire `test_radar_retention.py` suite (6 tests) still passed unchanged.
- **Failure scenario**: if a future edit (or the eventual `<=` typo this class of bug is famous for) changes the comparison operator, a mention event created at exactly the retention cutoff would be pruned one cycle earlier than intended (or vice versa) — silently, since it's an absence, and this suite would not catch it. This is precisely the off-by-one class of bug this whole audit was created to hunt down (see the retained standing note "An absence is never a zero" and the review brief's explicit callout of this exact risk).
- **Why it's not disqualifying**: the abandoned `>` mutation really was unsafe (verified above), and the substitute used (`total += 0`) is a legitimate, safe test for a different failure mode (bookkeeping), not a stand-in for the boundary. The implementer's safety judgment was correct; the boundary coverage was simply never re-attempted with a safe alternative.
- **Concrete fix**: add a third row in the same test, at `created_utc = now - dt.timedelta(hours=MENTION_EVENT_RETENTION_HOURS)` exactly (e.g. `ident='zz-boundary'`), still safely inside the April-2026 scope (nowhere near real Aug-2026 data). Assert its fate under the `<` semantics already implemented (a row exactly at cutoff is not `< cutoff`, so it should survive — assert `'zz-boundary' in remaining` and `deleted == 1` unchanged, or adjust the count if the intended semantics are actually inclusive). This pins the boundary without touching real data.

No other Critical or Important findings.

### Minor / informational (not blocking)

- `personal_apps/tests/test_radar_discovery.py:92` (`test_anyway_proceeds_past_the_guard_when_daemon_runs`): asserts `result != 1` rather than `result in (None, 0)`. Weak on its own, but the test's real proof of "proceeded past the guard" comes from `fake_app.entered >= 1` and the `fake_open.assert_called_once_with(...)` call — both of which are strong, so this doesn't leave the behavior actually unpinned. Cosmetic tightening only; not counted against the verdict.
- `prune_mention_events` (`retention.py:105-136`) always sleeps once more than strictly necessary at the tail of the loop (unlike `prune_posts`, which has a `if len(ids) < chunk_size: break` short-circuit before the sleep). This is copied verbatim from the brief's own Step 3 code block, so it is not an implementer deviation — noted for completeness only, not a finding against this diff.
- Pre-existing `LIKE 'ZZ%'` hazards in `test_radar_retention.py` (`aged_posts`) and `test_radar_daemon.py` (`test_prepare_rollup_generation_fails_closed_on_unrecovered_legacy_evidence`) — confirmed pre-existing and untouched by this batch (§2). Carry forward to the whole-branch triage as the implementer's own report already recommends.

---

## 7. Worktree state after review

- All four mutations I applied to reproduce teeth were reverted; `git diff` after each revert showed no differences.
- `git status --short` → clean (no output).
- `HEAD` → `6f1afa8913363eb4d0991813bb21bf64c1377035`, unchanged.
- `radar_mention_events`: 1432 rows, unchanged, confirmed by direct count immediately before writing this report.
- No commits made. No downgrade run. `personal_apps/reddit_candidates.json`, `personal_apps/telegram_candidates.json`, `personal_apps/scripts/discover_telegram_sources.py` untouched.

---

## 8. Verdict

Both tasks are spec-compliant and the shared-DB safety story is structural, not incidental — independently verified by direct counts and by reproducing every claimed mutation myself, plus one the implementer did not run. The only substantive gap is Finding 1: the retention window's exact boundary comparison is not pinned by any test, discovered by a mutation the implementer could safely have run but did not. This is a real, in-class defect for a data-pruning feature but does not indicate any actual data-loss risk in the current implementation — it's a test-coverage gap, not a shipped bug, and the fix is small and safe to apply.

Given the one Important finding is a missing-test gap (not a code defect) with a concrete, low-risk fix, and every other requirement (spec compliance, shared-DB safety, gates, teeth, worktree cleanliness) checks out independently: **NEEDS_FIXES** (add the boundary test before merge) rather than a hard block.

`VERDICT: NEEDS_FIXES | critical:0 | important:1 | minor:2 | db-rows: 1432/1432 | scoping: structural | teeth:4/4 | worktree clean: yes`
