# MD-SELECTED-PRICE-ALPACA-C2-M1-FIX — Implementer return

2026-09-16. Implementer: Claude Opus 5, no subagents.

**Outcome: M1 corrected test-first and verified locally.** The candidate is still
uncommitted and all flags are off.

## 0. Provenance disclosure

This correction ran in the **same session** that wrote
`MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RETURN.md`, which is the review that
raised M1. The binding ruling
(`MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RULING.md`) asks only for a Mastermind
changed-lines review after this return. The changed-lines check should therefore
come from the Mastermind, not from this session.

## 1. Files and behaviour changed

Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`,
branch `codex/radar-selected-price-charts`. HEAD = `origin/main` =
`f632e5db5dd92e27480cbfccdf7b0638b26533ed`, verified before and after.

Both files were already part of the uncommitted C1 delta. The snapshots and
digests below isolate this patch from that delta.

| File | SHA-256 before | SHA-256 after |
| --- | --- | --- |
| `personal_apps/features/radar/price_chart_acquisition.py` | `47bbad44…689ff8` | `63561fbe…01b022` |
| `personal_apps/tests/selected_price_unit/test_acquisition.py` | `0554dbab…d984baa` | `3745b6e9…bdbf18` |

### Product change

The whole product change is in `price_chart_acquisition.py`; the diff below is
taken against the pre-edit snapshot.

```diff
@@ -451,9 +451,9 @@
-                self._settle(key, outcome, data)
+                self._settle(key, spec, outcome, data)
 
-    def _settle(self, key, outcome, data):
+    def _settle(self, key, spec, outcome, data):
@@ -471,12 +471,19 @@
         if kind == 'ok':
-            # A source this process cannot profile is not a publishable series:
-            # ...
+            # Only a series from the source this child was ADMITTED for is
+            # publishable: ... Equality, not a table lookup -- `source` is
+            # untrusted JSON ... A result or a spec without one is the
+            # historical Yahoo shape.
+            if (result.get('source', contract.YAHOO_SOURCE)
+                    != spec.get('source', contract.YAHOO_SOURCE)):
+                self.counters['invalid'] += 1
+                self._cool(key, mono, COOLDOWN_S, 'backoff',
+                           'the series named a source other than the one requested')
+                return
             if (len(data) > ENTRY_BYTES or not isinstance(result.get('bars'), list)
-                    or result.get('source', contract.YAHOO_SOURCE) not in contract.PROVIDER_PROFILES
                     or not isinstance(result.get('received_at'), (int, float))):
```

The changes are at `price_chart_acquisition.py:454`, `:456` and `:474-486`.

1. `_supervise` now passes the admitted `spec` into `_settle`. `_supervise`
   already held that spec, and `_settle` has no other caller.
2. The membership guard is replaced by an equality test against the admitted
   source. Specs are built only by `request_spec_for`, so equality with the
   admitted source also implies a known profile. `PROVIDER_PROFILES` is no
   longer referenced in this module; `provider_price` still uses it.
3. The historical Yahoo rule is kept: a missing `source` counts as
   `yahoo_chart`, both in a result and in a spec.
4. A mismatched, unknown, null or unhashable source now does all of the following:
   - it counts `invalid`;
   - it caches nothing;
   - it gets the normal 60 s `backoff`;
   - it gives the reader no series;
   - it raises no exception. `!=` never hashes its operands, so arrays and
     objects are compared safely.
5. The refusal reason is now accurate: "the series named a source other than
   the one requested". The byte-bound, `bars` and `received_at` check keeps its
   own reason and is otherwise unchanged. The source check runs first.

Nothing else changed. Specifically untouched: provider adapters, request bounds,
retries, cache policy, fallback, ops/admin output, segments, rendering, flags,
child credential scoping, the non-finite `received_at` observation, the browser
harness and the frontend.

### Test changes

All test changes are in `test_acquisition.py`, following the existing `Harness`
pattern.

- **Helpers.**
  - `forged_source(value)` (`:361`) builds an otherwise valid `ok` result with
    exactly the given `source`, including an explicit JSON null.
  - `assert_refused_source(h, admitted)` (`:369`) checks that the result counts
    invalid and never success, and that nothing is cached (0 bytes). The next
    read must be `backoff` with a 60 s retry, `series is None`, and a reason that
    names the source and does not mention a bound. After 60 s the chart must be
    re-admitted, with exactly one child started.
- **Strengthened.** `test_a_child_result_whose_source_cannot_be_profiled_is_invalid_and_never_cached`
  (`:391`) is now parametrised over `'not_a_source'`, `null`, `7` and `''`, all
  with Alpaca admitted.
- **New** `test_an_unhashable_source_is_an_invalid_result_not_a_supervisor_exception`
  (`:402`): `["alpaca_sip"]` and `{"source": "alpaca_sip"}`.
- **New** `test_a_known_source_other_than_the_admitted_one_is_invalid_and_never_cached`
  (`:418`) covers three pairs of returned → admitted source:
  - `yahoo_chart` → `alpaca_sip`;
  - `alpaca_sip` → `yahoo_chart`;
  - a missing source → `alpaca_sip`.
- **New** `test_a_spec_without_a_source_admits_only_the_historical_yahoo_result`
  (`:431`) calls `_supervise` directly with a spec whose `source` was removed:
  - a missing or `yahoo_chart` result counts `success` and caches one entry;
  - an `alpaca_sip` result counts `invalid` and caches nothing.
- **Kept unchanged.**
  - `test_a_profiled_source_and_the_historical_missing_one_still_succeed`:
    matching `alpaca_sip`, matching `yahoo_chart`, and the missing source with
    Yahoo admitted, each resolved through `provider_price`.
  - `test_an_alpaca_acquisition_builds_the_alpaca_request_and_keeps_its_own_cache_key`.

## 2. Commands and exact results

All commands ran from `personal_apps` with `PYTHONDONTWRITEBYTECODE=1`.

| Step | Command | Result |
| --- | --- | --- |
| RED (tests written, product unchanged) | `py -3.12 -m pytest tests/selected_price_unit/test_acquisition.py -q -p no:cacheprovider` | **10 failed, 53 passed** (see the failure list below) |
| GREEN | same command | **63 passed** in 0.29 s |
| Full suite | `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **256 passed** in 18.57 s (245 before, plus 11 new parametrised cases) |
| Outbound guard | same, plus `-p c2final_no_outbound` (session-scratchpad plugin refusing non-loopback sockets) | **256 passed**; `REVIEW GUARD OUTBOUND ATTEMPTS: []` |
| Diff check | `git diff --check` (worktree root) | exit 0; line-ending warnings only |
| Real-thread probe | session-scratchpad `c2_final_probe_settle.py` (real `Coordinator` with `threading.Thread`, real reader, fake child, Alpaca admitted) | see the probe results below |

The RED run failed for exactly the intended reasons:

- the four unknown/null/int/empty cases failed on
  `'source' in 'the series exceeded its bound'`;
- the two unhashable cases failed with `TypeError: unhashable type: 'list'` and
  `TypeError: unhashable type: 'dict'`, which escaped `_supervise`;
- the three mismatch cases failed on `assert 0 == 1` for `invalid`, because they
  had been counted as success;
- the source-less spec with an `alpaca_sip` result failed on `assert 0 == 1`.

The real-thread probe gave these results:

- The `"not_a_source"`, `null`, `7`, `["alpaca_sip"]` and `{"x":1}` sources each:
  - counted `invalid: 1`, with 0 cache entries;
  - left `thread_errors: []`;
  - made the next read `backoff` with a 60 s retry and the new reason;
  - let the reader serve the whole `finnhub` stored fallback (3 observations);
  - were re-admitted after 61 s.
- A `yahoo_chart` result and a result with no source, both answering Alpaca,
  were also invalid and not cached.
- A matching `alpaca_sip` result counted `success: 1`, was cached, and read back
  as `ready` with source `alpaca_sip`.

## 3. Resulting state

- `git rev-parse HEAD origin/main`: both
  `f632e5db5dd92e27480cbfccdf7b0638b26533ed`.
- `git status --short` is line-for-line identical to the pre-edit capture: 71
  entries, 31 modified tracked and 40 untracked. The two edited files were
  already listed as ` M`.
- This return adds one untracked entry, making **72** entries. It is
  `?? radar-design/MD-SELECTED-PRICE-ALPACA-C2-M1-FIX-RETURN.md`.
- The pre-existing untracked entries include the final-review return, the
  ruling, and the M1 prompt.

## 4. Scope confirmation

- Product edits: only `personal_apps/features/radar/price_chart_acquisition.py`.
  Test edits: only `personal_apps/tests/selected_price_unit/test_acquisition.py`.
- The only new repository artifact is this return. The pre-edit snapshots, the
  guard plugin and the probe are in the session scratchpad, outside the repository.
- No browser-harness, frontend, adapter, bounds, retry, cache-policy, fallback,
  ops/admin, segment, rendering, flag, credential-scoping or `received_at` change.
- No private credential value or `.env` was opened, read, searched or hashed.
  The existing tests use only sentinel values.
- No network or provider request: the guarded run recorded zero outbound attempts.
- No dependency install, build, activation, configuration, DB, schema, service
  or production action. No commit, push or deploy.
- No reset, clean, stash, restore, checkout or stage. Every unrelated dirty or
  untracked file was preserved. No continuity file was updated. No subagents.

## 5. Residual risk and blockers

- **No blocker.**
- **Stricter than before.** An `ok` result now must name exactly the admitted
  source. The fixed child already does this: `normalize_alpaca` stamps
  `alpaca_sip` and `normalize_yahoo` stamps `yahoo_chart`, and the adapter is
  chosen from the spec's `source`. The real-child launcher test passed in the
  256-test suite.
- **A future adapter** must stamp the `source` its spec names, or every one of
  its results will be refused as invalid. This fails safe, onto the stored
  fallback.
- **Carries unchanged:**
  - M2 (evidence harness);
  - non-finite `received_at`;
  - Alpaca-only credential scoping;
  - the release carries in the final-review return, including explicitly
    committing untracked `prices/alpaca.py` and `test_alpaca_bounded.py`;
  - the frontend and whole-Radar gates, not re-run because no frontend file
    changed.

---

## Return prompt (copy/paste)

```text
You are Radar's Mastermind / Overview. Perform the changed-lines assessment for assignment MD-SELECTED-PRICE-ALPACA-C2-M1-FIX.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts / f632e5db5dd92e27480cbfccdf7b0638b26533ed / f632e5db5dd92e27480cbfccdf7b0638b26533ed (= origin/main; candidate uncommitted)
Binding: radar-design/MD-SELECTED-PRICE-ALPACA-C2-FINAL-REVIEW-RULING.md
Return: radar-design/MD-SELECTED-PRICE-ALPACA-C2-M1-FIX-RETURN.md

PROVENANCE: Implementer Claude Opus 5, no subagents. SAME session that wrote the final-review return that raised M1. The ruling asks only for your changed-lines review; this session did not review its own patch as independent evidence.

OUTCOME: M1 corrected test-first; candidate uncommitted; all flags off.

PRODUCT CHANGE (only personal_apps/features/radar/price_chart_acquisition.py; sha256 47bbad44…689ff8 -> 63561fbe…01b022):
- :454 _supervise calls self._settle(key, spec, outcome, data).
- :456 _settle(self, key, spec, outcome, data).
- :474-486, inside `if kind == 'ok'`: new first check
  `if result.get('source', contract.YAHOO_SOURCE) != spec.get('source', contract.YAHOO_SOURCE):`
  -> counters['invalid'] += 1; _cool(key, mono, COOLDOWN_S, 'backoff', 'the series named a source other than the one requested'); return.
  The old `... not in contract.PROVIDER_PROFILES` clause was removed from the bound check, which otherwise stays identical with its own reason.
- Missing source is still yahoo_chart for both the result and the spec. Equality never hashes, so arrays/objects are invalid, not exceptions. The spec source always comes from request_spec_for, so equality also implies a known profile.
- Nothing else changed.

TEST CHANGE (only personal_apps/tests/selected_price_unit/test_acquisition.py; sha256 0554dbab…d984baa -> 3745b6e9…bdbf18):
- Helpers forged_source (:361) and assert_refused_source (:369): invalid 1, success 0, cache empty/0 bytes, backoff 60, series None, reason names "source" and not "bound", re-admitted after 60 s, one child.
- Strengthened (:391): unknown-source test parametrised over 'not_a_source', null, 7, ''.
- New unhashable test (:402): ["alpaca_sip"] and {"source": "alpaca_sip"}.
- New mismatch test (:418): yahoo_chart->alpaca_sip, alpaca_sip->yahoo_chart, missing->alpaca_sip.
- New sourceless-spec test (:431): missing/yahoo_chart succeed and cache 1; alpaca_sip is invalid and caches 0.
- Existing matching alpaca_sip / yahoo_chart / missing-with-Yahoo success test kept unchanged.

COMMANDS (from personal_apps, PYTHONDONTWRITEBYTECODE=1):
- RED, tests only: pytest tests/selected_price_unit/test_acquisition.py -q -p no:cacheprovider -> 10 failed, 53 passed. Reasons: 4 x reason 'the series exceeded its bound'; 2 x "TypeError: unhashable type: 'list'/'dict'" escaping _supervise; 3 x invalid 0==1 for mismatches counted as success; 1 x sourceless spec accepting alpaca_sip.
- GREEN: 63 passed.
- Full selected_price_unit: 256 passed (245 + 11 new cases).
- Same under a scratchpad non-loopback socket guard: 256 passed, OUTBOUND ATTEMPTS [].
- git diff --check: exit 0.
- Real-thread scratchpad probe (real Coordinator + threading.Thread + real reader, Alpaca admitted):
  - not_a_source / null / 7 / ["alpaca_sip"] / {"x":1}: invalid 1, cache 0, thread_errors [], backoff 60 with the new reason, whole finnhub fallback, re-admitted after 61 s;
  - yahoo_chart and missing source: invalid, not cached;
  - matching alpaca_sip: success, ready.

STATE: HEAD = origin/main = f632e5d. git status --short identical to the pre-edit capture (71 entries: 31 M, 40 ??), plus this return = 72. Both edited files were already " M".

SCOPE CONFIRMED: only the two named files edited, plus this one return. No harness/frontend/adapter/bounds/retry/cache-policy/fallback/ops/segment/rendering/flag/credential-scoping/received_at change. No credential or .env inspection. No network/provider request. No install, build, activation, configuration, DB/schema/service/production action, commit, push or deploy. No reset/clean/stash/restore/checkout/stage. No continuity update. No subagents.

RESIDUAL: no blocker. The guard is now stricter: any future adapter must stamp the source its spec names, or its results fail safe to the stored fallback. Carries unchanged: M2 harness, non-finite received_at, Alpaca-only credential scoping, and the final-review release carries (explicitly commit untracked prices/alpaca.py and test_alpaca_bounded.py). Frontend/whole-Radar gates not re-run (no frontend change).

Requested Mastermind decision: complete the changed-lines assessment and focused verification. If satisfied, close M1 and record the candidate as ready for the owner's activation/deployment decision.
Next bounded action recommendation: Mastermind reruns test_acquisition.py and selected_price_unit and reads the two isolated hunks above. No further implementer or full review is needed if the patch is accepted. Do not dispatch activation/deployment work without the owner.
```
