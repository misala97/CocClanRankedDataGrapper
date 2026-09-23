# MD-SELECTED-PRICE-ALPACA-C2-FIX — correction Implementer return

2026-09-16, Implementer (Claude Opus 5, no subagents). Return to the Mastermind.

**Outcome: all four accepted corrections applied test-first and locally
verified. Candidate still uncommitted, all flags off.** No live/outbound
provider request, no credential inspection, no activation, configuration,
database, service, production action, commit, push or deploy.

Workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`,
branch `codex/radar-selected-price-charts`, HEAD = `origin/main` =
`f632e5db5dd92e27480cbfccdf7b0638b26533ed` (verified before and after).

## 1. Files changed, and why

| File | Correction | Change |
| --- | --- | --- |
| `features/radar/price_chart_acquisition.py` | 1, 4 | `_settle()` now refuses an `ok` result whose `source` is not in `contract.PROVIDER_PROFILES`, keeping the historical missing-source default for Yahoo; new `intended_source()` and `'source': source or intended_source()` in the ops snapshot. |
| `tests/selected_price_unit/test_acquisition.py` | 1, 4 | `ok_result()` helper; the unknown-source regression; a parametrised proof that `alpaca_sip`, `yahoo_chart` and the missing-source shape all still succeed AND resolve through `provider_price` (the call that used to raise); the actually-selected-source ops test; the existing ops test's `source` expectation corrected. |
| `tests/selected_price_unit/test_route_ops.py` | 4 | The `/api/ops` assertion corrected to "no source claimed"; a new case proving the route reports `yahoo_chart` when that is the selected source. |
| `static/radar/src/hub/SelectedPriceChart.tsx` | 2, 3 | New exported pure `panOffset()`; the pan effect rewritten around explicit `placedFor` / `readerMoved` / `placing` refs keyed on `ticker|span`, with a passive `scroll` listener. |
| `static/radar/src/hub/SelectedPriceChart.test.tsx` | 2 | Five `panOffset` cases at the widths measured on the built hub. |
| `static/radar/src/hub/Admin.tsx` | 4 | Renders "None selected" instead of inventing Alpaca when the server reports no source. |
| `static/radar/src/hub/Admin.test.tsx` | 4 | Fixture corrected to a producible shape; the state table extended with the `yahoo_chart` and no-source rows. |
| `static/radar/src/hub/priceChart.ts` | 4 | `SelectedPriceOps.source` widened to `string \| null`. Not in the prompt's file list, but the backend can now send `null` and the type had to admit it; one word, no behaviour. |
| `radar-design/artifacts/md-selected-price-alpaca-c1/browser/verify_browser.py` | 2, 3 | A `PAN` probe reporting gutter visibility and whether both could have fitted; a `the_gutter_is_visible_at_rest_wherever_it_fits` check; an `AnyStateMocks` route and a `run_reader_scroll_case` proving reader ownership and identity reset. |
| Radar `dist` | — | Rebuilt through the normal build (Git-ignored). |

Untouched on purpose: `ALPACA_REFUSALS` keeps its name, no credential-presence
helper was added, no pre-existing bar-element shape was hardened, and nothing
about the source contract, child isolation, segment model or area rendering
moved.

## 2. Correction 1 — an unknown child-result source is refused before caching

**Failing first** (`tests/selected_price_unit/test_acquisition.py`, before the
guard):

```text
test_a_child_result_whose_source_cannot_be_profiled_is_invalid_and_never_cached
>       assert h.coordinator.counters['invalid'] == 1
E       assert 0 == 1
1 failed, 3 passed
```

**Change** — one clause in the existing invalid test at `_settle()`:

```python
or result.get('source', contract.YAHOO_SOURCE) not in contract.PROVIDER_PROFILES
```

**Passing, and what it proves.** The forged `source: "not_a_source"` result now
increments `invalid` (not `success`), stores nothing (`_cache` empty,
`_cache_bytes` 0), enters the bounded 60-second invalid cooldown as `backoff`,
and hands the reader `series: None` — so the reader goes on to its own coherent
stored fallback instead of resolving an unknown profile. After the cooldown the
chart is admitted again, and only one child was ever started.

The companion parametrised test runs `alpaca_sip`, `yahoo_chart` and the
historical **missing** `source` through the supervisor and then through
`provider_price(...)` — the request-thread call that used to raise — asserting
each resolves to its own source. That is the direct proof that the fallback path
no longer raises.

## 3. Correction 2 — the gutter is kept whenever it fits

**Failing first**: `TypeError: panOffset is not a function`, 5 failed.

**Rule** (`panOffset`, pure and exported):

```ts
const maxLeft = scrollWidth - clientWidth
if (maxLeft <= 0) return null
if (latestX === null) return maxLeft
const latest = (latestX * drawingWidth) / CHART_W
if (maxLeft <= latest - clientWidth / 2) return maxLeft      // gutter fits too
return Math.round(Math.max(0, Math.min(maxLeft, latest + TRAILING_PX - clientWidth)))
```

**Measured at rest on the built hub** (`verify_browser.py`, `pan` facts):

| case | left | clientWidth | latest marker | price gutter | both could fit |
| --- | --- | --- | --- | --- | --- |
| sparse FT 1200 | 134 | 816 | visible | **visible** | yes |
| sparse FT 768 | 250 | 700 | visible | **visible** | yes |
| sparse FT 390 | 411 | 322 | visible | not | no |
| dense 1D 390 | 628 | 322 | visible | visible | yes |
| 1W 390 | 628 | 322 | visible | visible | yes |
| fallback 1D 390 | 628 | 322 | visible | visible | yes |

Before this correction the sparse case was `left 0 / 33 / 411` with the gutter
hidden at **all three** widths. It is now the rightmost position wherever that
does not hide the line, and unchanged at 390 where it would. Dense, 1W and the
stored fallback are unaffected. The new
`the_gutter_is_visible_at_rest_wherever_it_fits` check enforces the rule for
every case in the harness. No document overflow anywhere, and no motion was
added — the assignment is a plain `scrollLeft`, and `hub.css` already forces
`scroll-behavior: auto` under `prefers-reduced-motion`.

The 912-unit canvas, the lane proportions and the area rendering are unchanged.

## 4. Correction 3 — a deliberate scroll survives refreshes

`scrollLeft === 0` is gone. The effect now keys on `ticker|span` and keeps three
refs: `placedFor` (which chart has been placed), `readerMoved` (the reader has
taken it over), and `placing` (this scroll event is the component's own, not the
reader's).

**Measured** (new `reader-scroll-*` cases; each "refresh" sets a position, then
resizes to re-run the effect and the ResizeObserver):

| | 1200 | 390 |
| --- | --- | --- |
| placed once on open | 134 | 411 |
| reader scrolls into history | 67 → **67** | 314 → **314** |
| reader scrolls to the very start | 0 → **0** | 0 → **0** |
| reader switches ticker | re-placed at 134 | re-placed at 628 |

The zero row is the defect: before this correction those readers were moved to
410 and 621 on the next refresh. Programmatic placement does not mark itself as
a reader scroll (the `placing` flag is consumed by the event it caused), and if
that flag is ever consumed by the wrong event the chart simply stops
auto-placing — it errs toward respecting the reader.

*(One harness bug surfaced and was fixed while proving this: the probe first
scrolled to a fixed 200 px, which at 1200 is past the 134 px scroll range, so the
browser clamped it and fired no event at all. The probe now scrolls to half of
whatever range the width actually has.)*

## 5. Correction 4 — operations names the source it actually selected

**Failing first**: 2 backend ops tests and 2 Admin tests.

`intended_source()` returns Alpaca when its switch is on, Yahoo when that is the
one enabled, and `None` when neither is; `ops_snapshot()['source']` is the
selected source, or the one a refusal is about, or `None`.

| flags | `source` | `source_state` |
| --- | --- | --- |
| charts + Yahoo | `yahoo_chart` | `yahoo` |
| charts + Alpaca + credentials | `alpaca_sip` | `active` |
| charts + Alpaca, credentials missing | `alpaca_sip` | `credentials_missing` |
| charts on, neither source | `None` | `disabled` |
| charts off | `None` (or the intended source if a switch is on) | `charts_off` |

Proven at the coordinator (`test_ops_names_the_source_that_is_actually_selected`),
through the real `/radar/api/ops` route
(`test_ops_names_the_historical_source_when_that_is_the_one_selected`), and in
the Admin panel, whose state table now covers `yahoo_chart` ("Yahoo chart — the
historical Yahoo source is active instead") and the no-source row ("None
selected — switched off"). The panel still reports only
`credentials_present: bool`, and the Admin test still asserts the rendered page
contains no `APCA`/`key`/`secret` text.

## 6. Commands and exact results

From `personal_apps`, `PYTHONDONTWRITEBYTECODE=1`:

| Command | Result |
| --- | --- |
| `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **245 passed** (239 before this patch: +6) |
| the same under the outbound-socket guard | **245 passed**, `OUTBOUND ATTEMPTS: []` |
| `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` | **269 passed, 1 skipped, 3 failed** — the same three date-dependent `test_daily_closes_*` baseline failures, unchanged |
| `npx vitest run -c vite.radar.config.ts` (the five focused suites) | **5 files, 97 passed** (90 before: +7) |
| `npx vitest run -c vite.radar.config.ts` (whole Radar suite) | **883 passed, 28 failed** — the same 28 pre-existing `hub/pending.test.tsx` failures |
| `npx tsc --noEmit` | 0 errors |
| `npm run build` | passed; `assets/hub-Dycy3Xpo.js`, `assets/hub-Czy1AMuW.css` |
| `py -3.12 -u radar-design/artifacts/md-selected-price-alpaca-c1/browser/verify_browser.py` | **39 cases, 891 checks, 0 failures**, 0 unmocked requests, 0 stray server hits, 94 s, port 5043 free afterwards |

Baseline failures are reported, not hidden: three date-dependent Yahoo
`daily_closes` tests and 28 `pending.test.tsx` tests were failing before this
work and fail identically after it.

## 7. Screenshots inspected

`radar-design/artifacts/md-selected-price-alpaca-c1/browser/screenshots/`
(96 PNGs, regenerated against `hub-Dycy3Xpo.js`). Inspected for this return:

- `sparse_1d-research-1200.png` — the whole FT line, its after-hours dot, **and**
  `$7.43` / `$7.36` and `02:00 session end CEST` now on screen together. This is
  the C2-2 fix; the same frame previously had the gutter clipped.
- `sparse_1d-research-390-chart.png` — unchanged and still correct: the line and
  the marker on screen, the gutter traded away because both cannot fit.
- `week_1w-research-1200.png`, `dense_1d-research-1200.png`,
  `fallback_1d-research-1200.png`, `unavailable_1w-research-1200.png`,
  `chatter_gaps-research-768.png` — segment, fallback and absence behaviour
  unchanged.
- `zoom200-sparse_1d-research-390css-chart.png` — real 200% zoom, readable,
  nothing clipped.

## 8. Confirmations

No real credential value and no private root `.env` was opened, parsed, hashed
or searched at any point in this correction; only synthetic sentinels
(`PKSENTINELKEYID0000`, `sentinel-secret-not-a-real-credential`) appear in the
tests. No live or outbound provider request (the guarded suite recorded zero
attempts; the browser harness recorded zero unmocked requests and zero stray
server hits). No dependency install, flag activation, configuration, database,
schema, migration, service, production action, commit, push or deployment. No
second worktree, reset, clean, stash, restore or stage. No subagents.

Effective flag state is unchanged and off: `charts False yahoo False alpaca
False`, `selected_source (None, 'charts_off')`, no coordinator created.

## 9. State

Branch `codex/radar-selected-price-charts`; HEAD = `origin/main` =
`f632e5db5dd92e27480cbfccdf7b0638b26533ed`; `git diff --check` clean. Dirty
status: 31 modified tracked files (8 pre-existing continuity documents including
root `HANDOFF.md`, and the application/test files this family owns) and 34
untracked entries, including `prices/alpaca.py`, `test_alpaca_bounded.py`, the
C1 evidence directory, the C1/C2 returns and this return. All pre-existing dirty
and untracked files preserved.

## 10. Recommendation

**One FRESH-SESSION independent Reviewer/QA** — not dispatched by me, and not
this session. Per the C2 ruling the same-session review did not satisfy the
independent gate, so the reviewer should confirm C2-1 through C2-4 in the
corrected delta and independently sample the original source contract, child
isolation, fallback and observation-preservation behaviour before recommending
acceptance. Activation and release remain separate owner decisions.

---

## Return prompt (copy/paste)

```text
You are Radar's Mastermind / Overview. Assess this correction Implementer return for assignment MD-SELECTED-PRICE-ALPACA-C2-FIX.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts / f632e5db5dd92e27480cbfccdf7b0638b26533ed / f632e5db5dd92e27480cbfccdf7b0638b26533ed (= origin/main; candidate uncommitted)
Binding artifacts: .../radar-design/MD-SELECTED-PRICE-ALPACA-C2-RULING.md ; .../MD-SELECTED-PRICE-ALPACA-C2-RETURN.md ; .../MD-SELECTED-PRICE-ALPACA-C2-FIX-RETURN.md ; .../MD-SELECTED-PRICE-ALPACA-C1-SPEC.md ; .../artifacts/md-selected-price-alpaca-c1/

Outcome: all four accepted corrections applied test-first and locally verified; candidate uncommitted, all flags off.

C2-1: _settle() now refuses an `ok` child result whose `source` is not in contract.PROVIDER_PROFILES, keeping the historical missing-source Yahoo default. Failing first: "assert 0 == 1" on the invalid counter. Passing: the forged source counts invalid not success, caches nothing (_cache empty, 0 bytes), enters the bounded 60 s backoff, hands the reader series None so it reaches its own coherent stored fallback, re-admits after the cooldown, and started exactly one child. A companion parametrised test drives alpaca_sip, yahoo_chart and the missing-source shape through provider_price -- the request-thread call that used to raise -- and each resolves to its own source.

C2-2: new exported pure panOffset(). It takes the rightmost scroll position while that still leaves half a viewport of line to the left of the latest observation, and otherwise keeps the latest observation on screen. Failing first: "panOffset is not a function", 5 failed. Measured at rest on the built hub: sparse FT now 134/816 at 1200 and 250/700 at 768 with BOTH the latest marker and the price gutter visible (previously left 0 and 33 with the gutter hidden at every width), and unchanged at 411/322 at 390 where both cannot fit; dense 1D, 1W and the stored fallback take the rightmost position at every width. A new harness check, the_gutter_is_visible_at_rest_wherever_it_fits, enforces it for every case. No document overflow, no motion added, canvas/lanes/area rendering untouched.

C2-3: the scrollLeft === 0 sentinel is replaced by explicit placedFor / readerMoved / placing refs keyed on ticker|span, with a passive scroll listener. Measured at 1200 and 390: placed once on open (134 / 411); a reader at 67 / 314 is left there across a refresh and a resize; a reader at exactly 0 is left at 0 (previously moved to 410 / 621); switching ticker re-places the new chart at 134 / 628. Programmatic placement does not mark itself as a reader scroll, and a mis-consumed flag only makes the chart stop auto-placing -- it errs toward the reader.

C2-4: new intended_source(); ops_snapshot()['source'] is the selected source, or the one a refusal is about, or None. charts+Yahoo -> yahoo_chart/yahoo; charts+Alpaca+credentials -> alpaca_sip/active; credentials missing -> alpaca_sip/credentials_missing; neither switch -> None/disabled. Proven at the coordinator, through the real /radar/api/ops route, and in the Admin panel, which now renders "None selected" rather than inventing Alpaca and still reports only credentials_present: bool. SelectedPriceOps.source was widened to string | null in priceChart.ts -- one word, outside the prompt's file list but required by the new payload. ALPACA_REFUSALS was NOT renamed and no credential helper was added, per the ruling.

Commands (worker-executed, from personal_apps, PYTHONDONTWRITEBYTECODE=1): selected_price_unit 245 passed (was 239); the same 245 passed under the outbound-socket guard with OUTBOUND ATTEMPTS: []; tone/Yahoo/HA1 269 passed, 1 skipped, 3 failed -- the same date-dependent daily_closes baseline; five focused Radar suites 97 passed (was 90); whole Radar Vitest 883 passed, 28 failed -- the same pre-existing pending.test.tsx baseline; tsc 0; npm run build passed (hub-Dycy3Xpo.js); browser harness 39 cases / 891 checks / 0 failures, 0 unmocked requests, 0 stray server hits, port free afterwards. Baseline failures are reported, not hidden. One harness bug was found and fixed while proving C2-3: the probe had scrolled to a fixed 200 px, which at 1200 is past the 134 px range, so the browser clamped it and fired no event.

Screenshots inspected: sparse_1d 1200 (now showing the line, the after-hours dot, $7.43/$7.36 and "02:00 session end CEST" together), sparse_1d 390-chart (unchanged and correct), week_1w 1200, dense_1d 1200, fallback_1d 1200, unavailable_1w 1200, chatter_gaps 768, and a 200%-zoom frame.

Actions taken: the file changes listed in the return; created radar-design/MD-SELECTED-PRICE-ALPACA-C2-FIX-RETURN.md; updated only the current notices in root HANDOFF.md and radar-design/MD-SELECTED-PRICE-LEDGER.md. Explicitly NO real credential or private .env inspection, no live/outbound provider request, no dependency install, flag activation, configuration, database, schema, migration, service, production action, commit, push or deployment; no second worktree, reset, clean, stash, restore or stage; no subagents.
Protected state: production 194.164.29.97, databases, services, other worktrees, Remote Control sessions, saved credentials and provider flags (charts/Yahoo/Alpaca all off locally) untouched; all pre-existing dirty and untracked files preserved.
Requested Mastermind decision: accept the correction and dispatch ONE FRESH-SESSION independent Reviewer/QA, per the C2 independence ruling.
Next bounded action recommendation: prepare the fresh-session C2 reviewer prompt covering C2-1..C2-4 in the corrected delta plus an independent sample of the source contract, child isolation, fallback and observation preservation. Do not reopen the provider decision, source contract, child isolation design, segment model or accepted area language; do not rerun provider validation; do not activate, commit, push or deploy.
```
