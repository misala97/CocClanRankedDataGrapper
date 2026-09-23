# MD-SELECTED-PRICE-ALPACA-C2 — Reviewer/QA return

2026-09-16. Read-only focused review of the uncommitted C1 candidate against
`MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md`, `MD-SELECTED-PRICE-ALPACA-C1-SPEC.md`,
`MD-SELECTED-PRICE-ALPACA-C1-PLAN.md` and `MD-SELECTED-PRICE-ALPACA-C1-RULING.md`.
No application or test code was changed.

## 0. Independence qualification — read this first

**This review ran in the SAME session that implemented C1, not a separate one.**
The C2 prompt asks for an independent reviewer and says to start it in a
separate review task; the owner pasted it here instead. Everything below is
real, executed verification, and the two findings were both produced by
experiment rather than by reading — but this is *same-session* verification with
the reviewer's knowledge of the implementation, exactly the qualification
`MD-SELECTED-PRICE-REVIEW-2` carried on 2026-09-15. It is not an independent
second opinion. The Mastermind should record it as such and decide whether a
fresh-session check is still wanted before release.

## 1. Verdict

**FIX REQUIRED BEFORE C1 ACCEPTANCE**

One Important finding (C2-1). Three Minor findings. No Critical finding. The
fix packet is small and bounded (§4).

The Important finding is a latent validation gap in new C1 code, not a live
break: nothing reachable from a request, a provider response or a configuration
can trigger it today. If the Mastermind rules that unreachability is decisive,
downgrading it to Minor and accepting is a defensible alternative — but as the
contract is written, a child result the renderer cannot profile is stored,
counted as `success`, and then raises in the request thread instead of falling
back.

Acceptance of C1 would still not authorize activation, configuration change,
commit, push, database/service/production action or deployment.

## 2. Strengths

- **The source contract is implemented as ruled, and the tests prove it rather
  than assert it.** One pinned symbol, one request, `feed=sip`,
  `adjustment=raw`, `sort=asc`, `limit=10000`, `end = min(window end, now-16m)`,
  verified against a loopback server that counts requests
  (`test_alpaca_bounded.py:143`). No pagination, retry, redirect, IEX, asset
  call or alternate-symbol path exists in the module at all —
  `prices/alpaca.py` contains exactly one path constant, `BARS_PATH`.
- **The refusals are built so the request cannot be made rather than checked
  after the fact.** An empty clamp returns `(None, 'waiting_for_delay')` in the
  parent before admission (`price_chart_contract.py:408`), and the child
  re-checks structurally and answers `waiting` with no HTTP call
  (`price_chart_fetch.py:_run_alpaca`).
- **Secret isolation is proved end to end with digests, not claims.** The
  launcher test starts a real file-path parent carrying sentinel credentials, a
  decoy secret and Python/proxy overrides; the child reports SHA-256 digests of
  the two credentials, never values, and the decoy does not cross
  (`test_launcher_isolation.py:115`). I confirmed the parent template sets the
  sentinels unconditionally at its own top level, so a developer's real
  environment cannot leak a real digest into the saved evidence file.
- **`normalize_alpaca` treats absence as absence.** A null, zero or negative
  close invalidates the whole answer because Alpaca omits a minute it has
  nothing for — the opposite of the Yahoo path, and correct for this provider.
- **The closing-minute ruling is implemented by the interval algebra, not by a
  special case.** No calendar change, no timestamp subtraction: the 20:00:00Z
  bar falls outside `[regular_open, regular_close)` on 1W and inside the 1D
  extended interval, where `state_at` classifies it `afterhours`, which makes it
  a different `segment` key and therefore its own hard segment. Visible in
  `sparse_1d-*` as one 64-point line plus one separate dot.
- **The connecting line is never inspectable.** The readout is per chatter slot
  and reports `latestValid(pointsInSlot(...))`; a slot with no observation says
  "no price bar in this interval". Geometry adds two baseline vertices and
  nothing else, asserted exactly
  (`selectedPriceGeometry.test.ts` "the area adds only its two baseline corners").
- **Reduced motion is sound by construction**: the chart has no transition or
  animation, `.rh-chartwrap` has no `scroll-behavior: smooth`, and `hub.css:2122`
  already forces `scroll-behavior: auto` under `prefers-reduced-motion`.

## 3. Findings

### Important

**C2-1 — a child result with an unrecognised `source` is stored, counted as
`success`, and then raises an uncaught `KeyError` in the request thread.**
`personal_apps/features/radar/price_chart_acquisition.py:473-483` and
`personal_apps/features/radar/price_chart_contract.py:735-736`.

`_settle` is the boundary that validates the child's result envelope: it bounds
the bytes, requires `bars` to be a list and `received_at` to be numeric. C1 added
one new field, `source`, and it is the only one `_settle` does not check — and
the only one that raises. `provider_price` does `PROVIDER_PROFILES[source]` with
no fallback, inside `price_chart_reader.build_response`, which runs on the Flask
request thread. `routes/price_chart.py` catches only `ChartError`, so the request
becomes an HTTP 500 rather than the coherent stored fallback the spec requires
("Only a fully valid Alpaca result is stored/published as provider data. On every
other result, use one complete stored fallback").

Reproduced in-process against the real `Coordinator` and the real reader, with a
forged child result `{"kind":"ok","source":"not_a_source","bars":[[…]],…}`:

```text
supervisor counters: {'success': 1}
cached entries     : 1
reader: UNCAUGHT KeyError -> 'not_a_source'
```

**Reachability:** not reachable today. The only writer of `source` is
`features/radar/price_chart_fetch`, started by an argument array with a fixed
module name in an isolated process. This is a defence-in-depth and
contract-fidelity defect, plus a counter that reports `success` for a series
that cannot be rendered.

**Smallest fix:** extend the existing invalid test in `_settle`:

```python
if (len(data) > ENTRY_BYTES or not isinstance(result.get('bars'), list)
        or result.get('source', contract.YAHOO_SOURCE) not in contract.PROVIDER_PROFILES
        or not isinstance(result.get('received_at'), (int, float))):
```

plus one unit test in `test_acquisition.py` asserting an unknown `source`
counts `invalid`, caches nothing and cools the chart.

*(Related, pre-existing, NOT a C1 finding: `provider_points` unpacks
`for stamp, value in bars`, so a malformed bars ELEMENT raises the same way.
`git show HEAD:...price_chart_contract.py` contains the identical loop, so this
predates C1 and is out of this review's scope.)*

### Minor

**C2-2 — after the new pan rule the price axis and the window-end label are off
screen at rest for exactly the sparse case the feature targets.**
`personal_apps/static/radar/src/hub/SelectedPriceChart.tsx:262-276`.

Measured at rest on the built hub, with the deterministic fixture harness:

```text
case                left    cw   price-axis  end-label  latest-marker
sparse_1d-1200         0   816   False       False      True
sparse_1d-768         33   700   False       False      True
sparse_1d-390        411   322   False       False      True
week_1w-1200         128   816   True        True       True
dense_1d-390         621   322   True        True       True
```

`week_1w` and `dense_1d` are unaffected because their latest observation sits at
the window end. FT's does not: it stops trading four hours before the extended
close, so `wanted = latestX + 96 - clientWidth` lands well left of
`scrollWidth - clientWidth` and the gutter (SVG x 856) is clipped. Before C1 the
pan used `scrollLeft = scrollWidth`, which always showed the gutter — so this is
a C1-introduced regression at 1200 and 768, where **both** the line and the axis
fit and only the axis is now given up. At 390 they genuinely cannot both fit and
the new rule correctly prefers the data (that was the defect C1 fixed).

Not blocking: the axis is reachable by scrolling, the latest value is in the
summary text, every focused interval reports its own price, and there is no
document overflow.

**Smallest fix:** prefer the rightmost scroll position that still leaves a
usable amount of line on screen, else keep the current rule:

```ts
const maxLeft = box.scrollWidth - box.clientWidth
const latest = (latestX * drawing) / CHART_W
const wanted = Math.max(0, latest + TRAILING_PX - box.clientWidth)
box.scrollLeft = maxLeft <= latest - box.clientWidth / 2
  ? maxLeft                       // the gutter fits without hiding the line
  : Math.min(wanted, maxLeft)
```

**C2-3 — a reader who scrolls fully left is silently returned to the latest
observation on the next refresh or resize.**
`personal_apps/static/radar/src/hub/SelectedPriceChart.tsx:263`.

The guard is `box.scrollLeft !== 0`, which treats "the reader deliberately
scrolled to the oldest history" and "nothing has positioned this yet" as the same
state. Measured:

```text
sparse_1d-390: scrolled to 316 -> after a re-render still 316   (respected)
sparse_1d-390: scrolled to   0 -> after a re-render        410  (overridden)
week_1w-390:   scrolled to   0 -> after a re-render        621  (overridden)
```

The effect re-runs on every `data` change, so a reader looking at the session
open is moved away on the 60-second refetch. Earlier observations remain
reachable (`oldest_reachable: true` in both cases), so this is annoyance, not
lost data. The behaviour class is pre-existing — the base code had the same
guard and jumped to `scrollWidth` — but C1 touched this effect, so it is
recorded here.

**Smallest fix:** replace the overloaded `scrollLeft === 0` test with an explicit
"not positioned yet" ref that is set once per `data` identity and cleared on the
reader's first `scroll` event.

**C2-4 — two naming/labelling inaccuracies in the new operations surface.**

- `price_chart_acquisition.py:665` hardcodes `'source': contract.ALPACA_SOURCE`
  even when `source_state` is `'yahoo'`, so Admin renders "Alpaca consolidated
  SIP (delayed) — the historical Yahoo source is active instead".
- `price_chart_contract.py:401` names the shared refusal table
  `ALPACA_REFUSALS`, but `price_chart_acquisition.py:341` uses it for the Yahoo
  path too.

Neither is untrue to a careful reader and neither affects behaviour. Also noted,
below the threshold for a numbered finding: `selected_source()` and
`ops_snapshot()` call `alpaca.credentials()`, which materialises the two values
in the parent purely to test that they are non-blank; a `credentials_present()`
helper that never returns them would narrow the blast radius by a line.

### Not findings (checked, sound)

- Fallback truthfulness: eight acquisition refusal states through the real
  reader each produce ONE whole stored series with its own labels, and a
  provider success never appends a stored point
  (`test_reader.py` "every alpaca refusal serves one whole stored series or
  nothing", "a provider series is never spliced with a stored point").
- `observations` reconciliation cannot falsely reject a fallback: both stored
  paths filter through `_finite_positive` before a point is built
  (`analysis_contract.py:238,273`), so no point can carry a null value while
  being counted.
- Chatter and tone are untouched by the diff; observed/partial/zero/unknown
  meanings and their independent timestamps pass through unchanged
  (`test_reader.py` "real chatter states and tone are untouched beside a
  provider series").
- Body, raw-bar, point and result caps are all comfortably above the shapes the
  validation recorded (single-symbol week 91,802 B against a 512 KiB body bound;
  847 bars against `MAX_RAW_BARS` 4,000).
- `iso_z` truncates the clamped `end` down to whole seconds, which makes the
  16-minute margin very slightly more conservative, never less.

## 4. Fix packet (smallest that clears the verdict)

1. **C2-1** — add the `source` membership test to `_settle`'s existing invalid
   branch, plus one unit test. *(required)*
2. **C2-2** — the three-line pan expression above, plus a browser assertion that
   the price axis is visible at rest whenever it fits without hiding the line.
   *(recommended; presentation only)*
3. **C2-3** — an explicit "not positioned yet" ref. *(optional)*
4. **C2-4** — rename `ALPACA_REFUSALS` to `SOURCE_REFUSALS`/`REQUEST_REFUSALS`
   and report the actually selected source in ops. *(optional)*

No other change is warranted. Do not reopen the source contract, the child
isolation design, the segment model or the accepted area language.

## 5. Commands and exact results

Run by this reviewer, from `personal_apps`, with `PYTHONDONTWRITEBYTECODE=1`:

| Command | Result |
| --- | --- |
| `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` | **239 passed** in 17.8 s |
| `npx vitest run -c vite.radar.config.ts static/radar/src/hub/{selectedPriceGeometry.test.ts,SelectedPriceChart.test.tsx,SelectedPriceSection.test.tsx,priceChart.test.ts,Admin.test.tsx}` | **5 files, 90 passed** |
| `npx tsc --noEmit` | 0 errors |
| In-process forged-child probe (real `Coordinator` + real reader) | `success: 1`, cached 1, `UNCAUGHT KeyError` — evidence for C2-1 |
| Playwright pan probe (C1 fixture harness, 390 px, `sparse_1d` + `week_1w`) | evidence for C2-3; 0 unmocked, 0 server 404s |
| Playwright axis-visibility probe (C1 fixture harness, 1200/768/390, three states) | evidence for C2-2; 0 unmocked, 0 server 404s |

Both probes are throwaway scripts in the session scratchpad, not repository
files. They reuse the candidate's own deterministic local fixture harness; no
outbound request was made and the recorded `server_404` list was empty in both
runs. The broader recorded gates (outbound-guarded suite, tone/Yahoo/HA1,
whole-Radar Vitest, production build, 37-case/850-check browser proof) were
sampled from `results.json` and `evidence.md` and not re-executed in full.

## 6. Screenshots inspected and visual ruling

From `radar-design/artifacts/md-selected-price-alpaca-c1/browser/screenshots/`:
`sparse_1d-research-1200.png` (plus a magnified crop of its right edge),
`sparse_1d-research-390-chart.png`, `sparse_1d-research-390-focus.png`,
`week_1w-research-1200.png` (plus a magnified crop of its price lane),
`dense_1d-research-1200.png`, `fallback_1d-research-1200.png`,
`unavailable_1w-research-1200.png`, `chatter_gaps-research-768.png`,
`zoom200-sparse_1d-research-390css-chart.png`,
`zoom200-fallback_1d-research-390css-chart.png`.

**Ruling: the accepted area language is present and truthful.** One calm cyan
line through the reported prices with a subtle baseline-closing fill, one latest
marker, no dot cloud, hard breaks at every session, market state and source
change — the 1W frame shows five separate filled sessions with nothing drawn or
filled across a night, and the sparse FT frame shows 64 regular minutes as one
segment plus the closing bar as its own dot. Provenance reads "Alpaca
consolidated SIP (delayed) … 1-minute bar closes · 65 of 960 reported" and
"Adjustment basis raw"; nothing anywhere says real-time. The stored fallback and
the credential refusal state say exactly what they are, and the refusal names
itself without naming a credential.

Per the Mastermind's presentation ruling I did not treat the 912-unit panned
canvas as a defect in itself. The concrete defects I did look for: the latest
marker is visible at rest in every measured case (true); earlier observations are
reachable (true, measured); focus is visible and the canvas is keyboard
reachable in all 37 cases; the readout is never clipped; no case has document
overflow; real 200% zoom stays readable. The two demonstrated problems are
C2-2 (axis clipped at rest in the sparse case) and C2-3 (left-scroll snap-back),
both Minor.

## 7. Conclusions on the required questions

- **Source and identity:** compliant. One pinned symbol, one fixed-host request,
  ruled parameters, 16-minute clamp with no call on an empty interval, no
  redirect/proxy/cookie/retry/pagination/IEX/asset path, exact bars-key match,
  strictly increasing RFC-3339 timestamps with fractional seconds accepted,
  finite positive closes, page-token rejection, bounded body/raw/points/result.
  Radar remains the US/USD authority and `BRK.B` is sent exactly. Missing minutes
  stay absent. The regular-close bar is excluded from 1W and kept in 1D as a
  separate after-hours segment.
- **Child isolation and secrets:** compliant. Platform minimum plus exactly the
  two `APCA_*` names, blank treated as absent; no value in arguments, the stdin
  spec, stdout, the result envelope, exceptions, logs, ops or `__repr__`;
  provider message text never crosses the pipe. Flags are independent and
  default off and admission needs charts + Alpaca + both names.
- **One call / no pagination:** compliant, and asserted against a counting
  loopback server.
- **Fallback:** compliant — one whole stored series or a truthful absence, never
  a splice, for every refusal state.
- **Observations:** compliant — plotted and inspectable pairs equal the actual
  non-null observations exactly; the connecting line is geometry only and is not
  inspectable anywhere.
- **Chatter:** compliant and untouched.
- **Operations status:** truthful and non-secret-bearing, with the two naming
  inaccuracies in C2-4.

## 8. Unresolved release carries

Unchanged by this review: no live Alpaca path has ever been exercised (the
intra-session clamp against a live session, a real too-recent-SIP refusal, real
401/403/429/5xx envelopes, real throttling); POSIX/gunicorn child behaviour on
the release host; MariaDB runtime, plans and DB-backed route suites; real worker
topology and `WEB_CONCURRENCY`. All browser evidence is fixture evidence. The
`422` + code `42210000` → `waiting` mapping is the documented form, not an
observed one.

## 9. State and confirmations

Branch `codex/radar-selected-price-charts`; HEAD = `origin/main` =
`f632e5db5dd92e27480cbfccdf7b0638b26533ed`; candidate uncommitted. Final status
unchanged apart from this file: 31 modified tracked files and the same untracked
set as before the review, plus new `radar-design/MD-SELECTED-PRICE-ALPACA-C2-RETURN.md`.

Confirmed: **no real credential value or the private root `.env` was opened,
parsed, hashed or searched** in this review — only variable names and code paths,
with synthetic sentinels; **no live or outbound provider request** (both probes
ran against the local fixture harness and recorded zero unmocked requests and
zero stray server hits); **no application or test file was edited**; no flag
activation, configuration, database, service, production action, commit, push or
deployment; no continuity file updated; no subagents.

---

## Return prompt (copy/paste)

```text
You are Radar's Mastermind / Overview. Assess this Reviewer/QA return for assignment MD-SELECTED-PRICE-ALPACA-C2.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: codex/radar-selected-price-charts / f632e5db5dd92e27480cbfccdf7b0638b26533ed / f632e5db5dd92e27480cbfccdf7b0638b26533ed (= origin/main; candidate uncommitted)
Binding artifacts: .../radar-design/MD-SELECTED-PRICE-ALPACA-SOURCE-RULING.md ; .../MD-SELECTED-PRICE-ALPACA-C1-SPEC.md ; .../MD-SELECTED-PRICE-ALPACA-C1-PLAN.md ; .../MD-SELECTED-PRICE-ALPACA-C1-RULING.md ; .../MD-SELECTED-PRICE-ALPACA-C1-RETURN.md ; .../MD-SELECTED-PRICE-ALPACA-C2-RETURN.md ; .../artifacts/md-selected-price-alpaca-c1/

INDEPENDENCE QUALIFICATION, read first: this review ran in the SAME session that implemented C1, not a separate one. The verification is real and both findings came from executed experiments, but it is same-session verification with the reviewer's knowledge of the implementation — the MD-SELECTED-PRICE-REVIEW-2 qualification of 2026-09-15, not an independent second opinion. Decide whether a fresh-session check is still wanted before release.

Verdict: FIX REQUIRED BEFORE C1 ACCEPTANCE. One Important, three Minor, no Critical.

C2-1 (Important) — price_chart_acquisition.py:473-483 with price_chart_contract.py:735-736. _settle validates the child's bytes, `bars` list and numeric `received_at`, but not the new `source` field; provider_price does PROVIDER_PROFILES[source] with no fallback on the Flask request thread, and routes/price_chart.py catches only ChartError. Reproduced in-process with a forged child result: supervisor counters {'success': 1}, one cached entry, then "reader: UNCAUGHT KeyError -> 'not_a_source'" — an HTTP 500 instead of the coherent stored fallback the spec requires. NOT reachable today (the only writer is our own fixed child module), so this is contract fidelity and defence in depth, plus a counter that reports success for an unrenderable series. Fix: add `result.get('source', contract.YAHOO_SOURCE) not in contract.PROVIDER_PROFILES` to the existing invalid test, plus one unit test.

C2-2 (Minor) — SelectedPriceChart.tsx:262-276. Measured at rest on the built hub: for sparse_1d (FT) the price axis and the window-end label are off screen at 1200 (left 0), 768 (left 33) and 390 (left 411); week_1w and dense_1d are unaffected because their latest observation sits at the window end. Before C1 the pan used scrollLeft = scrollWidth and the gutter was always visible, so this is a C1 regression at 1200/768, where both the line and the axis fit. At 390 they cannot both fit and preferring the data is correct. Axis reachable by scrolling; values still in the summary and the readout; no document overflow. Fix: prefer the rightmost scroll that still leaves at least half a viewport of line on screen, else the current rule.

C2-3 (Minor) — SelectedPriceChart.tsx:263. The guard `box.scrollLeft !== 0` conflates "the reader scrolled to the oldest history" with "not positioned yet". Measured at 390: a reader at 316 is respected across a re-render; a reader at 0 is moved to 410 (sparse_1d) and 621 (week_1w). The effect re-runs on every data change, so the 60-second refetch moves a reader looking at the session open. Earlier observations stay reachable. Behaviour class is pre-existing; C1 touched the effect. Fix: an explicit "not positioned yet" ref cleared on the first scroll event.

C2-4 (Minor) — price_chart_acquisition.py:665 hardcodes 'source': ALPACA_SOURCE even when source_state is 'yahoo'; price_chart_contract.py:401 names a shared refusal table ALPACA_REFUSALS that price_chart_acquisition.py:341 also uses for Yahoo. Also noted below finding threshold: selected_source()/ops_snapshot() call alpaca.credentials(), which materialises both values in the parent only to test non-blankness.

Checked and sound, not findings: fallback truthfulness across eight refusal states; no provider/stored splice; the observations reconciliation cannot falsely reject a fallback (both stored paths filter through _finite_positive first); chatter/tone untouched; all caps comfortably above the validated shapes; iso_z truncates the clamp down, never up; reduced motion sound by construction. Pre-existing and out of scope: provider_points unpacks `for stamp, value in bars`, identical in HEAD.

Commands (reviewer-executed): pytest tests/selected_price_unit 239 passed; focused Radar Vitest 5 files / 90 passed; tsc 0 errors; an in-process forged-child probe and two playwright probes against the candidate's own local fixture harness, both with zero unmocked requests and zero server 404s. Broader recorded gates were sampled from results.json and evidence.md, not re-executed.

Screenshots inspected: sparse_1d 1200 (plus a right-edge crop), sparse_1d 390-chart and 390-focus, week_1w 1200 (plus a price-lane crop), dense_1d 1200, fallback_1d 1200, unavailable_1w 1200, chatter_gaps 768, and two 200%-zoom frames. Visual ruling: the accepted area language is present and truthful — one calm line with a subtle fill, one latest marker, no dot cloud, five separate 1W sessions with nothing across a night, FT's 64 regular minutes as one segment plus the closing bar as its own dot, provenance naming delayed consolidated SIP and raw with "65 of 960 reported", never real-time. Per the presentation ruling the panned canvas itself was not treated as a defect; the latest marker is visible at rest in every measured case and earlier observations are reachable.

Release carries unchanged: no live Alpaca path ever exercised; POSIX/gunicorn on the release host; MariaDB runtime and DB-backed suites; real topology. All browser evidence is fixture evidence.

Confirmations: no real credential value and no private .env was opened, parsed, hashed or searched; no live or outbound provider request; no application or test edit; no activation, configuration, DB, service, production action, commit, push or deploy; no continuity file updated; no subagents. The only repository write is radar-design/MD-SELECTED-PRICE-ALPACA-C2-RETURN.md.

Requested Mastermind decision: rule on C2-1 (require the fix, or downgrade it on unreachability and accept), on whether C2-2/C2-3 join the same fix packet, and on whether a fresh-session independent check is still required given the independence qualification above.
Next bounded action recommendation: one small owner-dispatched correction packet covering C2-1 (required) and C2-2/C2-3 (recommended), then a short changed-lines check rather than a new full review. Do not reopen the source contract, the child isolation design, the segment model or the accepted area language; do not rerun provider validation; do not activate, commit, push or deploy.
```
