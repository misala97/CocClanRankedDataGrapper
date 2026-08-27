# Review: Tasks 10-13 batch (4264036..d5997c9)

Reviewer: independent pass, read-only. HEAD at review start/end: `5f9d486`.

Status: COMPLETE.

## Spec compliance per task

### Task 10 — a failed read is not a measured zero

- ✅ `reddit.py:fetch_one` — empty-parse branch now returns `[], 'ok', None` instead of `[], 'ok', 0.0`. Docstring updated to explain the ceiling/floor asymmetry.
- ✅ `ingest.py:run_cycle` exception handler — `depths[source] = None` instead of `0`, with an explanatory comment.
- ✅ Tests added exactly as specified: `test_a_feed_that_parses_to_nothing_reports_no_rate` (brief's version, close paraphrase: actual name `test_an_empty_feed_is_quiet_rather_than_broken`, pre-existing test edited in place) and `test_a_failed_fetch_reports_no_catchup_depth` in `test_radar_ingest.py`.
- Extra beyond brief: `test_an_unparseable_feed_is_unknown_to_the_scheduler` in `test_radar_reddit.py`. This exercises `reddit.fetch()`'s pre-existing `RedditUnavailable` handling (already set `rates[sub] = None` before this batch) — it is a good regression but does not exercise code this batch changed. Not a defect, just noted as scope-adjacent, not scope-creep (it strengthens coverage of the same "no rate" contract from the caller's side).
- Verified end-to-end wiring: `scheduling.interval_for_rate` checks `rate is None` (→ floor) *before* `rate <= 0` (→ ceiling) — order is correct and pre-existing; `record_poll` passes rate straight through. `run_radar_ingest.py:169` feeds Reddit's per-sub `rate` into `record_poll`. Chain is intact.
- Task 9 not-due ruling check: the `except Exception` edit is scoped only to that branch; the untouched not-due path (`result.per_source_status == {}` → `result_statuses = {}` → no zero-valued root status written) is unmodified by this diff. `depths[source] = result.catchup_depth` for the non-exception path is unchanged (still whatever `FetchResult.catchup_depth` defaults to, `0`, for every source except fourchan — this is pre-existing and orthogonal to the reddit "rate" concept Task 10 addresses; the review brief's "catchup_depth" and reddit's own "observed_rate" are two different fields on two different structures, and Task 10 correctly touches only the one specified in each file). No regression found here.

### Task 11 — an unpriced model does not cost nothing

- ✅ `spend.cost_micros` returns `None` for unknown model, unchanged formula otherwise.
- ✅ `record()` guards the accumulation with `if cost is not None`.
- ✅ `summary()` adds `unpriced_tokens`, computed via a separate query scoped to `model.notin_(MODEL_RATES)`, `int()`'d at the boundary (Decimal-safe).
- ✅ `types.ts` widened; `Spend.tsx` renders the caveat conditionally, no new color, folded into the existing `.below` paragraph rather than a separate `<span className="caveat">` as literally suggested — functionally equivalent, no rule violated (brief said "whatever class the file already uses", implementer used none/inherited, which is a legitimate reading).
- ✅ `routes/api.py` needed no change — `serialize` already forwards `spend.summary()` wholesale; confirmed by reading `routes/api.py:130` (`'spend': spend.summary()`). A new API-boundary test (`test_the_board_payload_surfaces_unpriced_tokens`) proves this against the live route via `monkeypatch`.
- ✅ Frontend test updates keep all four pre-existing `Spend` tests green by widening the fixture payload, plus one new test for the caveat.
- Traced the aggregation defect end to end as instructed: unpriced tokens are counted from `RadarLlmSpend.input_tokens + RadarLlmSpend.output_tokens` for rows whose model isn't in `MODEL_RATES`; this is additive with the dollar total (separate query), so an unpriced model's tokens can never silently vanish into `$0.00`. Confirmed with `test_the_summary_surfaces_what_it_could_not_price`.
- Cleanup: `clean_spend` fixture rewritten from a broad `day >= 2026-08-01` range delete to an exact `(day, model)` tuple identity list (`SPEND_IDENTITIES`). Cross-checked every `spend.record(...)` call in the file against the tuple list — all seven identities are covered, none missing, none extra.

### Task 12 — interior gaps in the intraday chart

- ✅ `_watched_from_index` replaced by `watched_slots`, returning a `set[int]` of covered slot indices, using the same `status.in_(('ok','truncated'))` + `.distinct()` filter pattern as `board._covered_hours` (confirmed by direct comparison of both functions — identical shape).
- ✅ `intraday_chart_for` now nulls any slot outside `covered`, not just before the first one.
- ✅ Test added, but rewritten from the brief's draft (which reused `buckets.roll_up`) into a version that inserts `RadarBucketSource` rows directly with an explicit `status='truncated'` on the second (post-gap) bucket. This is a stronger test than the brief's draft: it separately asserts the *measured* slots keep their real values (`chatter[first_index] == 3`, `chatter[last_index] == 0`) in addition to the interior gap being `None`, and asserts `watched_from` still points at the earliest covered slot. Own fixture `clean_intraday_gap` cleans up ticker `DTGAP12` by exact identity, before and after.

### Task 13 — three small corrections

- ✅ Breadth exclusion count: `board.build` now tracks `removed = len(ranked) - len(kept)` and adds it into `ranking.excluded['one_venue']`. Confirmed `Ranking.excluded` is freshly constructed per call (`Ranking(rows=..., excluded=dict(excluded))` in `leaderboard.build_rows`) so there is no cross-request mutable-default leak, and `Board.excluded` is the same dict object handed through, so the API payload reflects it.
- ✅ Named floor: `leaderboard.py` now imports `VARIANCE_FLOOR` from `.config` and uses it in the `mention_z` formula, replacing the hardcoded `0.25`. Cross-checked: `board.py`, `scoring.py`, `baselines.py` already used the named constant — `leaderboard.py` was the sole straggler, now consistent.
- ✅ Extract-once, hardened form: implementer used the explicit `if raw.external_id not in extracted: extracted[raw.external_id] = _extract_for(raw, lookup)` branch specified in the brief's "Controller hardening" section, NOT the eager `setdefault` draft. Confirmed by reading `ingest.py` directly (see below). `fresh_ids` is computed once before the second loop, not rebuilt per iteration, also per the hardening note.
- ✅ Docstring corrected to describe extraction as "once per post per cycle" plus journal-level upsert, matching the hardening note's replacement text (paraphrased, same meaning).
- ✅ Regression test `test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement` added, instrumenting `_extract_for` via monkeypatch, asserting `calls == ['dup-extract']` (called exactly once for the duplicate identity) plus correctness of stored/refreshed state (`stored.score == 900`, i.e., the *second* occurrence's engagement won) and `mention_count == 1` (rollup didn't double count).

No unexplained extras found in the diff; nothing asked for in any of the four briefs is missing.

## Risk-area audit

1. **Task 10 not-due distinction**: verified above — untouched, no reintroduced measured zero.
2. **Task 11 API/UI boundary**: verified — `None` survives to `unpriced_tokens` as `int`, dollars stay separate, UI renders honestly, no color used.
3. **Task 12 measured zero vs uncovered slot**: verified — `watched_slots` mirrors `board._covered_hours` exactly (same status filter), so the Task-9-Critical failure shape (mixed selections marking hours measured while omitting a source) is not reintroduced; a `truncated` bucket still counts as "covered" (i.e., its own real zero stays zero), matching the model established elsewhere.
4. **Task 13 three things**: exact count verified (arithmetic on filtered list lengths, not an approximation); named floor verified consulted at the formula call site in `leaderboard.py` (not merely imported and unused — grep confirms it appears in the one formula line); extract-once hardened form verified directly in source, not just from the report's claim.
5. **Teeth**: see below — mutation-tested the load-bearing ones myself.
6. **Scope**: 15 files changed matches the four brief's file lists plus test files; no drive-by changes to unrelated modules found in the diff.

## Teeth audit

Every mutation below was applied with Edit, the targeted test run to observe the exact failure, then reverted with Edit. Final state verified byte-identical to HEAD via `git hash-object` vs `git rev-parse HEAD:<path>` for all six touched production files (see Gates). Worktree confirmed clean (`git status --short` empty) and HEAD unchanged (`5f9d486`) at the end.

1. **Task 10 — reddit rate.** `features/radar/sources/reddit.py:169`: `return [], 'ok', None` → `return [], 'ok', 0.0`.
   Test: `test_an_empty_feed_is_quiet_rather_than_broken`.
   Failure: `assert ([] == [] and 'ok' == 'ok' and 0.0 is None)` → `AssertionError`.
   Reverted ✓ (confirmed via hash match).

2. **Task 10 — catchup depth on exception.** `features/radar/ingest.py` exception handler: `depths[source] = None` → `depths[source] = 0`.
   Test: `test_a_failed_fetch_reports_no_catchup_depth`.
   Failure: `assert 0 is None`.
   Reverted ✓.

3. **Task 11 — cost_micros unknown rate.** `features/radar/spend.py:cost_micros`: `return None` → `return 0`.
   Test: `test_an_unpriced_model_costs_null_not_nothing`.
   Failure: `assert 0 is None`.
   Reverted ✓.

4. **Task 11 — summary unpriced_tokens.** `features/radar/spend.py:summary.unpriced`: `return int(total or 0)` → `return 0` (query result discarded).
   Test: `test_the_summary_surfaces_what_it_could_not_price`.
   Failure: `assert 0 == 501000`.
   Reverted ✓.

5. **Task 11 — record() guard, secondary check.** Removed the `if cost is not None:` guard entirely (`row.cost_micros += cost` unconditionally, `cost` being `None` for an unpriced model).
   Test: `test_an_unpriced_model_records_tokens_and_no_cost`.
   Failure: `TypeError: unsupported operand type(s) for +=: 'int' and 'NoneType'` at `spend.py:73`.
   Note: a *softer* mutation (`row.cost_micros += cost or 0`, i.e., same numeric outcome without the crash) passed all 11 spend tests unchanged — this is expected and not a teeth gap, since `+= 0` and "skip the add" are arithmetically identical in every case this code can reach (there is no state where the guarded and unguarded-but-safe forms diverge in the value written; the guard's only observable job is crash-avoidance, which the harder mutation confirms is tested).
   Reverted ✓.

6. **Task 12 — mid-window gap.** `features/radar/detail.py:intraday_chart_for`: replaced `counts[index] if index in covered else None` with a leading-edge-only null (reproducing the pre-Task-12 `_watched_from_index` behavior: null only before `min(covered)`, zero-fill everything after including the interior gap).
   Test: `test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet`.
   Failure: `assert all(value is None for value in chart.chatter[first_index+1:last_index])` → `AssertionError: assert False`.
   Cross-check: `test_a_slot_before_observation_began_is_unknown_not_zero` (the pre-existing leading-edge test) still PASSED under this mutation, confirming the new test is the only one that catches the reintroduced defect — i.e., the two tests are not redundant.
   Reverted ✓.

7. **Task 13 — breadth exclusion count.** `features/radar/board.py:build`: removed the `removed`/`ranking.excluded['one_venue']` accounting, restoring the plain `ranked = [row for row in ranked if row.venues >= min_venues]`.
   Test: `test_the_breadth_filter_reports_what_it_removed`.
   Failure: `assert 0 >= 1` (`filtered.excluded == {}`).
   Reverted ✓.

8. **Task 13 — named variance floor.** `features/radar/leaderboard.py`: `max(variance, VARIANCE_FLOOR) ** 0.5` → `max(variance, 0.25) ** 0.5` (hardcoded literal, ignoring the monkeypatched `VARIANCE_FLOOR = 4.0`).
   Test: `test_the_leaderboard_uses_the_named_variance_floor`.
   Failure: `assert 18.0 == 4.5` (exactly the literal-floor arithmetic: `(10-1)/sqrt(max(0.01,0.25)) = 9/0.5 = 18.0`) — matches the implementer's own reported mutation result number, independently reproduced.
   Reverted ✓.

9. **Task 13 — extract-once (the hardened tooth).** `features/radar/ingest.py:_store_mentioning_posts`: restored the draft's eager form `tickers = extracted.setdefault(raw.external_id, _extract_for(raw, lookup))` in place of the explicit membership branch.
   Test: `test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement`.
   Failure: `assert ['dup-extract', 'dup-extract'] == ['dup-extract']` — exactly the eager-evaluation defect the brief's Stage-4 hardening note predicted (Python evaluates `setdefault`'s second argument before the call, so a duplicate external ID still invokes `_extract_for` twice even though the key already exists).
   Reverted ✓.

9/9 targeted mutations produced the predicted failure. All absence-shaped assertions in this batch that I judged load-bearing survived mutation testing; no dead/decorative assertions found among them.

## Gates

| Gate | Command | Result |
|---|---|---|
| Backend suite | `python -m pytest tests/ -k radar -q` (run from `personal_apps/`) | **633 passed, 646 deselected**, 2 pre-existing `utcnow()` deprecation warnings (unrelated to this batch). Matches implementer's report exactly. Re-ran a second time after all mutation testing to confirm no residual DB leakage — still 633 passed. |
| Vite manifest precondition | `ls static/radar/dist/.vite/manifest.json` | Present — explains why 0 (not 2) page-embed tests failed, consistent with instructions. |
| TypeScript | `npx tsc --noEmit` | Clean, no output, exit 0. |
| Frontend tests | `npm test` (from `personal_apps/`) | **403 passed** (main Vitest config) + **81 passed** (`-c vite.radar.config.ts`) = 484, matches implementer's "403 + 81 passed" claim. |
| Fresh-process imports | `python -c "from features.radar import buckets"` / `... import journal` / `... import ingest` / `python -c "from run_radar_ingest import build_fetchers"` | All four succeeded independently (separate `python -c` processes) — the fragile `buckets`↔`journal` circular import is intact and this batch did not touch either file. |
| Migration head | `flask db current` | `08316d3e4d77 (head)` — single head, matches pre-batch state. No downgrade run. |
| Worktree cleanliness | `git status --short` / `git rev-parse HEAD` | Empty / `5f9d486f2178524d9b6a02c15bd23339a1813ca3` — unchanged from session start. All mutation edits reverted and confirmed via `git hash-object` vs `git rev-parse HEAD:<path>` byte-identity for all six touched files. |

No `flask db` downgrade was run, per instructions.

## Findings

None survived verification. No Critical, Important, or Minor defects found in the four production diffs, the tests added for them, or the two frontend files.

Observations recorded during review that are explicitly **not** findings against this batch:

- `test_radar_board.py`'s pre-existing `clean` fixture (untouched by this batch) tears down by `TickerUniverse.symbol.like('BD%')` / `RadarBucketSource.ticker.like('BD%')` etc. `BD` is not a namespaced `ZZ`-style prefix and could in principle collide with a real ticker (e.g. `BDX`) if one is ever seeded into the same dev database. This predates the batch, is not in the four task briefs' file list, and was not touched by any of the four commits — the two NEW fixtures this batch adds (`clean_breadth_reporting`, `clean_intraday_gap`) both correctly use exact-identity teardown instead of a prefix `LIKE`, which is the right call given the hazard. Flagging for final triage, not against this batch.
- Six test files carry a broad `.like('ZZ%')` teardown pattern, pre-existing and untouched by this batch: `test_radar_bucket_sources.py`, `test_radar_buckets.py`, `test_radar_daemon.py`, `test_radar_journal.py`, `test_radar_retention.py`, `test_radar_universe.py`. (The task brief's framing mentioned "five" such files; my own grep found six — flagging the discrepancy for final triage rather than reconciling it myself, since none of the six were touched by this batch either way.) `test_radar_backfill.py` explicitly documents in a comment that it does NOT use a broad `LIKE` and cleans up by exact identity instead.
- `features/radar/spend.py:summary.unpriced`'s local variable `total` shadows the outer `summary.total` function name. Not a bug (no recursive call, closures resolve correctly, confirmed by mutation testing above), just a minor readability nit not worth a fix-it-yourself edit on an otherwise-passing review.

## ⚠️ Cannot verify from diff

- Production behavior of `RadarBucketSource.status` values in practice (whether a `missing` source ever actually gets a row written) was not independently re-derived from `buckets.roll_up`'s full source in this pass — I relied on the codebase's own repeated documentation/comments (Task 9-era rulings, restated in this diff) that `missing` never writes a row, which the `watched_slots`/`_covered_hours` `.status.in_(('ok','truncated'))` filter is consistent with. I did not re-audit `buckets.py` itself since it is unmodified by this batch and out of the stated review range.
- Live daemon/scheduler behavior (`run_radar_ingest.py`'s actual polling loop against real Reddit traffic) was not exercised; only the unit-level wiring (`interval_for_rate`, `record_poll`, the `rates` dict) was traced statically and via the existing test suite.

## Verdict

**APPROVED.** All four briefs' requirements are met with no missing pieces and no unexplained scope creep. All nine targeted mutations of absence-shaped assertions failed as expected and were fully reverted. All gates pass, matching the implementer's reported numbers exactly. Worktree left clean, HEAD unchanged.

