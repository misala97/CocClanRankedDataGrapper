# VC1 progress ledger

Binding plan: VISUAL-CORRECTION-PLAN.md. Planning by Codex, 2026-09-09.
Implementation and verification by Claude, 2026-09-09, in
`C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate` on
`codex/radar-release-candidate`.

| Task | Status | Evidence / next action |
| --- | --- | --- |
| Owner visual review of deployed Chatter | Corrections required | Owner compared screenshots against interactive prototype; bar/percentage, sources, density and hierarchy rejected |
| Source/prototype investigation | Complete | Candidate d3bc795 source inspected; source aggregation admits zero-mention feeds; tone fallback semantics inspected; no fresh VPS inspection |
| VC1 design contract | Complete | VISUAL-CORRECTION-PLAN.md; approved light/green direction retained |
| **TE1** | **Complete** | New disposable `personal_apps_radar_te1`, 29 FKs, both migrations, integrity tests pass. See below. |
| **VC1a data/helpers** | **Complete** | `c90cf92`. Additive `activity_sources`; pure `tonePresentation`/`sourcePresentation`. Mutation-checked. |
| **VC1b Chatter correction** | **Complete** | `db9f153`. Composition, tone bar + percentage, source summary, column proportions, responsive rules. |
| **VC1c visual verification** | **Complete** | Matched before/after screenshots, 50 browser checks, measurements in `reports/vc1/`. |
| **Two defects found by looking** | **Fixed** | `b1cf313` the class collision, `43526e8` the tone bar's invisible rare share. Both below. |
| **Independent review** | **Performed, findings resolved** | Read-only reviewer against this contract, the source and the actual screenshots. Twelve findings, none blocking; every one addressed below. |
| **VC1-close (Eighth return A, B, D)** | **Complete** | `20dfc03`. Approximate-bar sentence, table breakpoints scoped back to Chatter, responsive cell labels. |
| **Sortable Chatter** | **Complete** | `20dfc03`. Owner-approved 2026-09-10; the binding contract is in VISUAL-CORRECTION-PLAN.md. |
| **Second independent review** | **Performed, findings resolved** | Fourteen items on VC1-close and sorting, none blocking. Every one addressed; see below. |
| Owner acceptance | **Open — this is the ask** | Run the preview and look at it. Command below. |
| Deployment | Not authorized | Separate decision, after visual acceptance |

Baseline: release-candidate branch `d3bc795`; production `ba1c381` per accepted
RELEASE-RECORD.md. The work below ends at **`79235db`**, plus the one
commit that carries this line -- verify with `git rev-parse --short HEAD`,
because a document cannot name the commit that carries it.

| commit | what |
| --- | --- |
| `c90cf92` | VC1a — additive `activity_sources`, pure tone/source presentation helpers |
| `db9f153` | VC1b/VC1c — the corrected Chatter, filters disclosure, CSS, responsive rules, screenshots |
| `ea98c50` | Codex's brief, dispatch and reference images carried in, plus this ledger |
| `b1cf313` | the panel's company filter had taken the topbar search's class |
| `43526e8` | the tone bar drew a rare share as nothing |
| `fc578b8` | the loading state, and one test flake reported rather than hidden |
| `79235db` | the independent review's twelve findings |
| `d66b52e` | the documents name their commits |
| `20dfc03` | **VC1-close**: sortable Chatter, and the Eighth return's A, B and D |
| `fea864f` | the VC1-close ledger, and a fixture that showed an impossible state |
| `d21788e` | the Eighth return and the sorting contract, carried in |

---

## TE1 — the test environment is repaired

The old clone `personal_apps_radar_wt` carried **none** of the 29 foreign keys
that production and local development both have — the signature of
`CREATE TABLE ... LIKE`. It has NOT been dropped; it is preserved, and every
result recorded against it stays labelled as constraint-free.

**The replacement.** `personal_apps_radar_te1`, built by a schema-preserving
`mysqldump` of the local development `personal_apps` and a restore into a new
database, then `flask db upgrade` to the production head.

| check | result |
| --- | --- |
| foreign keys | **29**, identical definitions and delete rules to the source |
| unique indexes | **62**, identical |
| tables | 43 restored, **45** after the two migrations |
| engine / collation | InnoDB / `utf8mb4_0900_ai_ci` throughout, identical |
| alembic | `b3d9e1f5a274` restored → **`a7c31f0b52d4`** after upgrade, the deployed head |
| the six projection columns | present, correct types |
| `radar_watch_ibfk_1` | `radar_watch.user_id → app_user.id ON DELETE CASCADE` — the exact constraint production has and the old clone lacked |
| `@@foreign_key_checks` in the test session | **1** |

The comparison of source and restored schema facts is exact: the two JSON
dumps of foreign keys, unique indexes, tables, engines and collations are
string-identical.

**The discriminating evidence.** The two integrity tests that fail on the old
clone pass on the rebuild, and they failed for the right reason:

```
personal_apps_radar_wt   test_deleting_the_account_deletes_its_marks           FAILED
                         test_a_mark_for_an_account_that_does_not_exist_is_an_error
                             Failed: DID NOT RAISE <class 'sqlalchemy.exc.IntegrityError'>
personal_apps_radar_te1  both PASS, with 38 others: 40 passed
```

**Application-level tests on the repaired database**, not the SQL probe:

| suite | result |
| --- | --- |
| `test_radar_watch.py`, `test_radar_watch_api.py`, `test_auth.py` | **40 passed** |
| activity, activity_projection, observations, operations_api, projection_migration, migration, daemon, api, hub_page, leaderboard, board, vite_assets | **367 passed, 5 skipped** |
| gym ownership, sharing, exercise ownership, routes smoke | **209 passed** |
| `test_radar_ingest.py` | **37 passed**, twice in a row |

That last line corrects the record rather than claiming a fix. The handoff
describes three ingest tests that fail on every run after the first against a
persistent database. On the rebuilt database they pass on consecutive runs.
Nothing in the suite changed; the residue that caused it was in the old clone.
If it reappears, the `_wipe()` helper is still the suspect.

**Not covered by TE1.** The rebuild's schema comes from the local development
database, not from a production backup restore. Those two agree on all 29
foreign keys, so the constraint gap is closed — but a constraint production had
and local development did not would still be invisible here.

---

## VC1a — `activity_sources`, `c90cf92`

`sources` is every scored feed a ticker has a bucket on in the window,
**including feeds that counted nothing**: `_aggregate` admits a bucket on
`mention_z IS NOT NULL`, not on a positive mention count. On production, with
36 scored feeds, that made "36" the answer for every row and filled the column
with repeated labels. It was answering "which feeds were looked at" while
reading as "which feeds were talking".

`Row.activity_sources` answers the second question: concrete feeds whose summed
mentions over the selected window are above zero. Folded out of the aggregate
`parts` the board already has — **no new query, and none that grows with the
row count**, asserted by a test that builds a one-row board and a four-row
board and compares statement counts.

It is additive and nothing else moved. `sources`, `venues`, the eligibility
floor and the breadth filter are untouched, so no ticker enters or leaves the
board because this field exists. A test records that deliberately:
`test_the_breadth_filter_still_counts_feeds_looked_at_not_feeds_talking`.
Moving `min_venues` onto the new field would change which companies appear,
which is a ranking change and not a display one, and it belongs to a separate
follow-up.

**Mutation-checked.** Replacing the positive-mention filter with the full
`contributing` list fails five of the nine new leaderboard tests.

On real local rows the two genuinely differ: NVDA has four feeds looked at and
three talking; TTWO two and one.

`chatterPresentation.ts` holds every wording rule as pure functions, tested
against the contract's own worked examples: B=10, S=16, U=45 → `38.5% bullish`,
bar 10:16, `26 directional / 71 total`.

---

## VC1b — the corrected Chatter, `db9f153`

**Sources**: `3 platforms`, with `Reddit · 4chan /biz/ · Bluesky` beneath it.
Concrete identifiers — `r/options`, not a thirtieth copy of "Reddit" — are
behind that summary, and the summary is itself the disclosure control, so they
cost the row no height.

**Tone**: the percentage, a 104×6px bar over the same denominator, and the
sample size. The residual is named rather than folded in. A row with no sample
gets no breakdown control: there is nothing to break down.

**Columns**: a colgroup with `table-layout: fixed` at 26/13/10/18/17/12/4.
Sources needs three points more than the contract's 15 % or
`Reddit · 4chan /biz/ · Bluesky` wraps; they come from Voices and Tone and
deliberately NOT from Attention, which the contract names specifically. An
earlier revision took one from Attention anyway and the review caught it.
Measured at 1440: 285 / 142 / 110 / 197 / 186 / 132 / 44 px.

**Filters**: market, window and size on the bar; breadth and the feed
checkboxes behind a **More filters** disclosure that names what it is set to
(`Any venue · all 3 feeds`). The R1 last-feed refusal is unchanged and still
tested.

**Breakpoints**: navigation collapses at **1080** and the table stacks at
**860**; they used to be one breakpoint at 700. The skip link moves with the
NAVIGATION, not the table -- it was left behind at 860 in the first revision
and floated 184 px into a rail-less page at 1024 until the review found it. With seven columns that was
wrong in both directions — at 1024 a 184px rail left 726px of table and every
column shrank; at 768 the same rail left 580px. Nothing changes across 700/701
any more, and that was verified at 1081/1080/861/860/701/700.

---

## VC1c — what was measured, and where to look

Every screenshot is the **built production bundle**, served with an embedded
payload in the same envelope the Flask view uses.

**Two datasets, never mixed.** `real` is the local development database — real
tickers, counts and prices, a 24-hour window ending 2026-09-01 18:15, which is
where the local copy's data stops. It is not production and it is not today.
`fixture` is fictional and every row exists to exercise one edge.

### Row heights and column balance at 1440

Same payload, same viewport, same browser; the only difference is the bundle.

Every figure below is read out of `reports/vc1/*-measurements.json`. Where a
number is arithmetic rather than a measurement, it says so.

| fixture at 1440 | before (`d3bc795`) | after |
| --- | --- | --- |
| KSTR, NRLN, OLDCACHE — no warnings, tone sample | 166 px | **86 px** |
| QUIET — no warnings, no tone sample | 120 px | **90 px** |
| VELA — one warning | 165 px | **105 px** |
| ORBT — one warning | 166 px | **106 px** |
| ARDR — two warnings | 166 px | **106 px** |
| the whole first five rows (`fiveRows`) | **784 px** | **474 px** |
| tone bar | none | **104 × 6 px** |

| fixture at 768 | before | after |
| --- | --- | --- |
| every row | **664 px** | **236–285 px** |
| document scrolls sideways | **yes** | no |

Five *plain* rows would be 430 px (5 × 86), inside the contract's 440. That is
arithmetic, not a measurement: the measured `fiveRows` for this fixture is
**474 px**, because two of its first five rows carry warnings and the contract
allows those to reach 108. Type sizes measured from the rendered page: row
values 13 px, secondary 12 px, headings 12 px. Column widths at 1440:
285 / 142 / 110 / 197 / 186 / 132 / 44 px.

**Where it is measurably worse, in full.** On the local **real** board every
row reads `No tone sample`, because the development copy holds **zero**
`radar_posts` and `radar_mentions` rows.

| real at 1440 | before | after | |
| --- | --- | --- | --- |
| the fourteen rows with two warnings | 97–98 px | 105–106 px | **+8 px** |
| ABCL and FWRG, three warnings | 98 px | **133 px** | **+35 px, +36%** |

An earlier draft of this table printed an em dash for the three-warning row's
before figure and summarised the whole regression as "~8 px". It was measured,
it is 98 px, and the honest number is +35 px on those two rows. The 133 px is
permitted by the contract — "the row may grow for multiple warnings" — and the
badges genuinely wrap onto a second line at 142 px of Attention. Omitting it
was the defect, not the height.

Production is not the local board's case: the owner's own rejected screenshot
shows real tone counts, and on a row that HAS a tone sample the correction is
166 px → 106 px (ORBT) and 165 px → 105 px (VELA).

**Errata on `db9f153`'s commit message.** Two figures in it are wrong and are
corrected here rather than by rewriting a reviewed commit. It says "at 768 the
old build produced a 3320px row" — no row was 3320 px; every row was **664 px**
and 3320 is the five-row sum. It says a row "went from 165px to 106px" — no
measured pair is exactly that; the real pairs are 165 → 105 and 166 → 106. It
gives the after range at 768 as "271-285px", which omits QUIET at **236 px**.

### The evidence

`radar-design/reports/vc1/`

| file | what |
| --- | --- |
| `comparison-1440.png` | the annotated before/after, three matched pairs |
| `after-fixture-1440.png` … `-1920`, `-1024`, `-768`, `-390`, `-320` | every required width |
| `after-real-1440.png` | real local rows |
| `after-dense-1440.png` | 45 rows |
| `after-empty-1440.png` | empty board with the exclusion account |
| `before-*.png` | the rejected build on the same payloads |
| `reflow-720.png`, `reflow-320.png` | 200% and 400% zoom |
| `page-*.png` | Overview, Watching, Activity, Administration, Research — all fifteen, five routes at three widths |
| `state-nomatch-1440.png` | the in-page filter matching nothing |
| `state-refresh-failed-1440.png` | a refresh that failed; the rows stay |
| `state-loading-1440.png` | a filter change still in flight |
| `after-measurements.json`, `before-measurements.json` | the numbers above, as measured |

### Two defects the screenshots caught and the tests did not

**The panel's company filter had taken the topbar search's class.**
`.rh-search` already belonged to the global search field in the topbar. The
new "Filter companies" box reused it, so a capture script that typed into
`.rh-search input` put the string in the topbar instead: the suggestion
popover opened over the page heading and the table underneath was completely
unfiltered. Every hub test still passed, because none of them addresses either
field by class. Renamed to `.rh-tablefilter`. Fixed in `b1cf313`.

**The tone bar was telling the rounding lie the label refuses to.** Measured
at 1440: a `0.5% bullish` share drew a **0.52px** segment and a `>99.9%` one
drew **0.02px**, on a 104px track. Both invisible — so the bar read 0% and
100% under labels that deliberately do not, reintroducing exactly the rounding
the wording exists to prevent, in the more persuasive channel. A segment that
exists is now at least 2px, which slightly over-states a rare share; that is
the honest direction to err, because the percentage above it is the reading
and the bar only has to say "present, and very small". A TRUE zero still draws
no segment. Fixed in `43526e8` and pinned by three browser checks, since it is
a layout fact jsdom cannot have an opinion about.

Measured segments after the fix, at 1440:

```
38.5% bullish     bull 39.23px   bear 62.77px     (10/26 of 102px, unrounded)
0.5% bullish      bull  2.00px   bear 100.00px
>99.9% bullish    bull 100.00px  bear   2.00px
100% bullish      bull 104.00px  — one segment, no bear at all
No directional signal / No tone sample   one 104px neutral track
```

### The other states

`state-nomatch-1440.png` — the in-page filter matching nothing. It says the
filter runs over the seven already listed, and the count reads `0 of 7 shown`;
it is not confused with an empty board.
`state-refresh-failed-1440.png` — a refresh that fails keeps all seven rows on
screen rather than blanking, which is what the stale-response protection is
for.

`state-loading-1440.png` — a filter change still in flight, with the board
request held open. This is the only loading state Chatter really has: the
first board is embedded in the page, so first paint has nothing to wait for —
a capture of it came back byte-identical to the failed-refresh one, and one
image was deleted rather than presented as two states. In flight, the Window
control reads `Last hour` (what was asked for) while the context line still
reads `last 24 hours` (what is on screen). That is the payload's own echo
doing its job: the heading describes the rows the reader is looking at, not
the request that has not landed.

### Browser checks — 50, all passing, no console or page errors

Disclosures open and close, Escape closes and returns focus, opening one does
not navigate, the source detail names concrete `r/…` feeds, every row control
is keyboard reachable, the row is not itself a click target, More filters
opens, unchecking one feed leaves the others alone, the company control opens
research and Back restores the list, no sideways scroll at 720 or 320 px with
tone still visible, no sideways scroll on any of the six hub pages at 1440,
768 and 390.

### Tests

| command | result |
| --- | --- |
| `npx vitest run -c vite.radar.config.ts` | **476 passed**, 39 files |
| `npx vitest run` (root config) | **403 passed**, 32 files |
| `npm run build` (includes `tsc --noEmit`) | exit 0 |
| `pytest` — leaderboard, api, board, hub_page, watch, watch_api, chatter_eligibility, board_sort, phrasing, vite_assets | **216 passed** |

Every backend run is on `personal_apps_radar_te1`, asserted by name first.

**One intermittent failure seen once, and reported rather than hidden.** In a
single radar run, one test in `static/radar/src/board/BoardPage.test.tsx` —
the OLD board at `/radar/`, which this work does not touch — failed, and that
file took 8.7s against its usual 6.7s. It did not reproduce: the file alone
passes 22/22, and three consecutive full radar runs afterwards are 475/475.
The run that failed was sharing the machine with an independent reviewer
running its own suites. Recorded as a suspected timing flake under load, not
as a clean result.

---

## Run the preview

```
cd C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate/personal_apps
PYTHONPATH=. py -3.12 scratchpad/vc1_serve.py 5071
```

Then open:

- `http://127.0.0.1:5071/scratchpad/vc1/real.html#chatter` — real local rows
- `http://127.0.0.1:5071/scratchpad/vc1/fixture.html#chatter` — the edge cases
- `http://127.0.0.1:5071/scratchpad/vc1/dense.html#chatter` — 45 rows
- `http://127.0.0.1:5071/scratchpad/vc1/empty.html#chatter` — nothing cleared

The filters, the disclosures, the company links, Research, Activity,
Administration and Back all work; the server answers `/radar/api/board`,
`/radar/api/ticker/…`, `/radar/api/activity` and `/radar/api/ops` from the same
data. It is a preview and not the application: no login, no database, no watch
writes, and no detail payload for the fictional tickers.

Regenerate it after a code change:

```
npm run build && PYTHONPATH=. py -3.12 scratchpad/vc1_preview.py scratchpad/vc1
```

`personal_apps/scratchpad/vc1/` is gitignored — it holds whole board payloads
rebuilt from the disposable database. The curated screenshots in
`radar-design/reports/vc1/` are the committed evidence.

---

## The independent review, and what it changed

A read-only reviewer went through the contract, the diff, the measurement
files and the screenshots, re-ran every suite, and mutation-checked the
contract from scratch copies in a temp directory. **Nothing blocking.** It
confirmed the tone contract exact against the plan clause by clause, the
source field genuinely additive, the CSS scoping clean, `[hidden]` not
defeated by any later `display` rule, and — reading the PNGs rather than the
DOM — that the result does not fall short of the prototype: "The rejected
build's failure modes are gone: no repeated Reddit, no 664 px rows at 768, no
sideways document scroll at any width."

Its own mutation checks are worth recording because they were independent of
mine: a pytest plugin overriding `_assemble` to set `activity_sources = sources`
fails exactly five leaderboard tests plus the API serializer test; drawing the
bar over T instead of D fails two; dropping the `<0.1%` guard fails one;
loosening the count validation fails one.

**Most of what it found was wrong with the RECORD, not the code**, and that is
the more embarrassing half. Every item is addressed:

| # | finding | resolution |
| --- | --- | --- |
| 1 | this ledger printed an em dash for a measured before-figure and summarised a +35 px regression as "~8 px" | the row-height tables above are rewritten from the measurement files, with the +36 % case named |
| 2 | WCAG 2.5.3 Label in Name: `aria-label` REPLACED the visible text on both row disclosures, so "click 26 directional" had no handle | the visible text now leads the accessible name; pinned by a test |
| 3 | "five rows are 430 px" was presented as measured when the measured `fiveRows` is 474 | both numbers stated, and which is arithmetic |
| 4 | two false figures in `db9f153`'s commit message (a "3320px row"; a "165px to 106px" pair that does not exist) | errata above, rather than rewriting a reviewed commit |
| 5 | this ledger claimed the independent review Complete before it had run | this section |
| 6 | the columns took a point from Attention, which the contract names specifically: "do not compress Attention to make room for source prose" | restored to 13 %; the three points now come from Voices and Tone alone. Measured 142 px |
| 7 | the skip link was stranded: its `left: 16px` reset stayed at 860 while the rail moved to 1080, so at 1024 it floated 184 px into a page with no rail | reset moved into the 1080 block; checked at all six boundary widths |
| 8 | Activity and Watching now stack at 860 rather than 700 — an uncommanded change to pages VC1 was only to check | accepted and recorded. Between 861 and 1080 those pages gain the rail's width back, so they are strictly wider there; Administration is untouched because it uses `rh-opsgrid`, not `.rh-table` |
| 9 | the Administration screenshot showed only its refusal banner, and 8 of 15 page shots were committed | the preview now declares `is_admin`, so the page renders its real panels; all 15 page shots are committed |
| 10 | a superseded tone-bar prohibition comment survived on the Research surface | rewritten to say what Research decides and why, without the ban |
| 11 | `min-width: 2px` on a bar segment deviates from "segment widths use unrounded ratios" | **flagged for Codex to ratify.** It is a deliberate deviation: without it a 0.5 % share drew 0.52 px and the bar contradicted its own label. Ratios stay unrounded above ~2 % of the track |
| 12 | dead `.rh-filters-note`, a stale "below 700px" comment, and the breadth-versus-display distinction living only in the footer glossary | rule deleted, comment corrected, and the explanation now sits beside the Breadth control itself with `aria-describedby` |

One finding is **not** resolved and is left as it is: every cell carries a
visually hidden column label, so a screen reader on the desk layout hears the
column header and then the label again on all seven cells. That is deliberate
and documented in `Chatter.tsx` — below 860 px the header row is gone and the
label is the only thing naming the figure — but it does double the announced
text per row, and a future pass could make it responsive rather than constant.

## VC1-close — the Eighth return's A, B and D, `20dfc03`

Codex accepted TE1 and the principal correction and set three narrow items
before a deployment proposal. This is a small closure, **not** a redispatch of
VC1a-c: nothing in the earlier work was reopened.

**A. The bar says it approximates.** The tone detail now ends with the ruling's
own sentence: *"Tiny nonzero shares are drawn at a minimum width so they remain
visible; use the percentage and counts for the exact balance."* It is in the
accessible detail, not the row. The rare-share geometry and percentage tests
are retained unchanged, and the geometry is not described anywhere as strictly
proportional.

**B. The 860 table breakpoint is Chatter's alone.** Watching and Activity keep
the 700px table breakpoint they always had. Carrying them to 860 was an
uncommanded change to pages this work was asked only to check, and the capture
that seemed to justify it was of an **empty** table. Navigation still collapses
at 1080 and the skip-link correction stands.

Chatter's stacking rules are written `.rh-table.rh-chatter`, so they outrank
the generic `.rh-table` block by specificity below 700 rather than by which
media query the file happens to list last.

Verified on **populated** fixtures — a five-row watch list and seven days of
labelled fictional activity, because the local database records no ingest runs
and its real activity payload is seven days of nulls:

| width | Chatter | Watching | Activity |
| --- | --- | --- | --- |
| 861 | table | table | table |
| 860 | **stacked** | table | table |
| 768 | stacked | table | table |
| 701 | stacked | table | table |
| 700 | stacked | **stacked** | **stacked** |

No page scrolls sideways at any of those widths.

**D. The duplicate cell labels are gone from the desk layout.** They were
`rh-visually-hidden`, which hides from the eye and keeps in the accessibility
tree — so a screen reader heard the column name from the header and again from
the cell, seven times a row, every row. They are now `display: none` on the
desk layout, which removes them from both trees, and `display: block` in the
stacked layout where the header row no longer exists and they are the only
thing naming each figure. One CSS switch; no JavaScript watching the viewport;
the explicit ARIA roles that survive `display: block` on table elements are
unchanged.

Activity and Watching still carry the same duplicate on their desk layouts.
That is the same defect and it is **not fixed here** — those pages were out of
scope — and it is recorded below as a named follow-up.

---

## Sortable Chatter, `20dfc03`

Owner-approved on 2026-09-10 after using the preview. The binding contract is
the "VC1-close addition" section of VISUAL-CORRECTION-PLAN.md.

**It is a view, and the page says so.** Sorting issues no request, touches no
server sort parameter and cannot add a company the response did not carry. A
browser check asserts the board-request count does not move when a header is
clicked. The note above the table reads *"Sorts these 7 candidates, not the
whole market — Radar's ranking and eligibility are unchanged"*, because
"sorted by tone" otherwise reads as "the most bullish companies in the market"
and it is not that.

**Every key reads what its cell displays.** Sorting a formatted percentage
would put 10% before 2%; sorting the bar's geometry would rank rows by the 2px
minimum that exists so a rare share stays visible. So:

| column | sorts on | unknown when |
| --- | --- | --- |
| Company | the ticker, locale-aware and numeric-aware, never the clamped name | never |
| Attention | `row.ratio`, the server's guard, never recomputed | no baseline |
| Voices | `authors` | not a finite number |
| Sources | platforms from validated `activity_sources`; never legacy `sources` | the field is missing (an empty list is a measured zero and sorts) |
| Tone | the unrounded bullish share of the DIRECTIONAL sample | no directional sample, or malformed counts |
| Price | the displayed price, **grouped by currency** | unavailable quote, no price, or no currency |
| Today | the raw `price_move` fraction; zero is a value | no move, or no usable quote |

**Unknown is not zero and not smallest.** Rows with nothing measured stay last
in **both** directions — reversing a sort must not promote the companies nobody
has a reading for. Equal keys keep the response order, with an explicit index
tiebreak rather than borrowing the engine's sort stability.

**Price groups rather than pretends.** €4.44 is not "less than" $18.20 in any
sense a reader would accept and this board has no conversion to make it one, so
a German fallback row sorts among the euro rows and the page names the
currencies when more than one is present. Today's move does **not** group: a
percentage is comparable across currencies where a price is not.

**Where the state lives.** In the hub, not in Chatter — Chatter unmounts when
the reader opens a company, so Back would otherwise throw the ordering away. In
memory only: it is a view over whichever response is current, so it survives a
refresh and a server-filter change, and "Radar order" resets to the **newest**
response rather than the one that was sorted. Not in the URL either; the query
string is the SELECTION, which decides what the server builds, and this decides
nothing the server does.

**Both layouts can sort.** Desk: the column headers are real buttons, with
`aria-sort` on the header cell and the visible column name as the button's own
accessible name. Price and Today are two controls, because one combined
control cannot say whether the reader asked for the dearest company or the one
that rose most — and the shared header takes an explicit name saying which of
them `aria-sort` is describing. Below 860 the header row is `display: none`,
which takes it out of the accessibility tree too, so the stacked layout gets a
labelled **Sort by** selector and a direction button with the same seven keys.
Same CSS breakpoint as everything else; no JavaScript watching the viewport.

**One defect the screenshots caught.** Raising specificity for item B made
`.rh-table.rh-chatter td { display: block }` outrank the chevron column's
`display: none`, so on mobile a stray chevron reappeared as a block with no
grid area and sat alone at the bottom of every row. Every test still passed.
Fixed, and pinned by a check that every visible stacked cell has a named grid
area.

### Tests and checks at `20dfc03`

| command | result |
| --- | --- |
| `npx vitest run -c vite.radar.config.ts` | **527 passed**, 40 files (was 476) |
| `npx vitest run` (root config) | **403 passed**, 32 files |
| `npm run build` (includes `tsc --noEmit`) | exit 0 |

Browser checks: **128 passing**, no console or page errors — **50** from the
earlier VC1c pass, re-run unchanged against this build, plus **78** covering
sorting, the responsive labels and the breakpoints on populated tables at five
widths across three pages. Counted from the scripts' own output, not estimated.

Backend code was not touched by this work.

### New evidence

| file | what |
| --- | --- |
| `close-sorted-1440.png` | sorted by Tone, desk layout, with the arrow and the scope note |
| `close-sorted-390.png` | sorted by Voices from the stacked layout's selector |
| `close-chatter-768.png`, `close-chatter-700.png` | Chatter stacked at both |
| `close-watching-768.png`, `close-watching-700.png` | populated Watching: table, then stacked |
| `close-activity-768.png`, `close-activity-700.png` | populated Activity: table, then stacked |

The watch list and the activity days in those captures are **labelled
fictional fixtures**. The local database has no watch marks and records no
ingest runs, so its real payloads are an empty list and seven days of nulls —
and an empty table cannot verify a table layout, which is the Eighth return's
own point.

---

## The second independent review, and what it changed

A read-only reviewer went through the Eighth return's items, the sorting
contract clause by clause, the diff, the measurement files and the screenshots,
re-ran every suite, and verified item B's specificity claim empirically —
computing ten properties on sixteen Chatter selectors at 701 and 700 and
confirming they are identical. **Nothing blocking.** Fourteen items; every one
is addressed.

| # | finding | resolution |
| --- | --- | --- |
| 1 | pressing "Radar order" unmounted the control holding focus, so focus fell to `<body>` and a keyboard reader's next Tab restarted at the top of the document | focus is handed to the table region; pinned by a unit test and a browser check that reads `document.activeElement` |
| 2 | **three of my own browser checks did not test what they claimed** — a hardcoded `check(..., True)`, a tautological `A or B` where B was unconditionally true, and a `break` that made the second half of a loop dead code while mislabelling the one direction that ran | all three rewritten to assert the thing named; the currency check now reads the note while PRICE is active rather than after switching away |
| 3 | `move` inherited Price's currency requirement, so a row the page renders as `12.34 / +5.0%` sorted as "no today's move reading" | `move` now needs a usable price, not a currency; `price` still needs one because it groups by it |
| 4 | "1 with no **today** reading" — `SORT_LABELS` are column headings, not sentence words | a separate `readingWord` map: "today's move", "ticker", "source" |
| 5 | the reset was invisible as a control — `.rh-textbutton`'s green lost to `.rh button { color: inherit }`, so it read as the tail of the sentence beside it | explicit green and an underline at higher specificity; a browser check compares its computed colour against the prose next to it |
| 6 | sorting was silent to assistive technology beyond `aria-sort`, which says nothing to a reader who just pressed a control and nothing at all on the stacked layout; and the direction button's name stated the CURRENT order rather than the action | a polite status region announces the new order; the direction button's accessible name is what pressing it does, and it claims no order while disabled |
| 7 | "58 browser checks" in `20dfc03`'s message was false — the script emits 60 | already self-corrected in `fea864f`; the count above is now 128, counted |
| 8 | "Sorts these **0** candidates" above "No company here matches that." | the note says "Nothing is left to sort under the current filter", and the way back is still there |
| 9 | the arrow sat flush against "Today" — `display: inline` in the price header drops `.rh-sortbutton`'s gap | an explicit margin on the arrow in that header |
| 10 | comparator edge cases: the currency GROUPS swap with direction; `Intl.Collator` can return 0 for distinct tickers; `sortRows(rows, null)` returns the input array | the note now warns that reversing moves the groups too; the other two are deliberate and documented in the source rather than changed |
| 11 | item A's required sentence was pinned by no test, so re-wording it would have failed nothing | a test asserts it verbatim, and asserts it is absent from the label and the sample line |
| 12 | item B verified, with two residues (below) | recorded, not changed |
| 13 | item D and the interaction contract | verified, no findings |
| 14 | density and column widths | verified byte-identical to `d66b52e` apart from the header string `"Price · today"` → `"Price · Today"` |

**Item B's two residues, recorded rather than changed.** Non-table mobile chrome
— table padding, 44px button heights, 16px inputs — still switches at 860 for
Watching and Activity, where it used to switch at 700; the ruling's letter is
about the TABLE breakpoint, which is restored, and the 768 captures look
correct. And `.rh-table td { align-items / justify-content / gap }` still lands
on Chatter's cells below 700, inert because `display: block` wins, but live the
moment any Chatter cell becomes a flex container.

**One thing the reviewer confirmed rather than found:** the `BoardPage.test.tsx`
flake reappeared once under concurrent load, in the same file and the same
shape already recorded above, and passed on its own and in a quiet full run. It
is the old `/radar/` board and no commit here touches it.

## Limitations, stated

1. **No tone reading on local data.** The development copy has no
   `radar_posts` or `radar_mentions` rows, so every real local row reads
   `No tone sample`. The percentage, the bar and the rare-share wording are
   exercised by the labelled fixture and by unit tests, not by local real data.
2. **Eleven feeds locally, thirty-six in production.** The source summary's
   worst case — many platforms and a `+N` — is exercised by the fixture, not by
   local real data.
3. **No fresh production inspection.** Nothing here was compared against the
   live site; the "before" is the deployed build rendered locally on the same
   payloads, which is the same code and not the same data.
4. **The other five hub pages were checked, not corrected.** They render
   without errors or overflow at three widths after the shared breakpoint
   change. They are not claimed to be prototype-identical, and no page-specific
   fidelity work was done on them.
5. **TE1's schema comes from local development, not from a production restore.**
   Codex accepted it as closing the constraint-free TEST ENVIRONMENT defect
   while noting it is not a production clone: MySQL 8 and `utf8mb4_0900_ai_ci`
   differ from the target's MariaDB and collation, and matching local foreign
   keys does not establish every production constraint.
6. **Sorting was verified in Chromium only**, through the built bundle. The
   `Intl.Collator` ordering of tickers and the `display: none` breakpoint
   switch are standard, but no second engine was checked.
   `Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })` can
   return 0 for two distinct tickers — `A007` against `A7`, or a case
   difference — and those rows then keep response order in both directions
   rather than swapping. Stable and harmless; not what "Z–A" implies.
7. **The duplicate cell labels persist on Activity and Watching.** Chatter's
   are fixed; those two were out of scope and are a named follow-up.
8. **No screen reader was run.** The accessibility claims here rest on the DOM,
   computed styles and `aria-*` attributes as measured in the browser — not on
   an actual assistive-technology pass.

## Named follow-ups

- **The duplicate cell labels on Activity and Watching.** Same defect Chatter's
  item D fixed, same one-line shape. Out of scope here by ruling.
- **Watching's tone and source presentation.** Eighth return E: reuse these
  helpers where Watching shows those metrics, with a populated mockup first.
  Not a Watching redesign, and not in this delivery.
- **The zero-feed question in legacy `sources` / `venues` / breadth filtering.**
  Changing it can change which companies appear, so it is a ranking decision
  and not a display one.
- **Whether 860 is right for Watching and Activity too.** This delivery
  restored their 700, and the question is open rather than answered.

## Not done, deliberately

No merge, no push, no deploy. Capture stays off. `/radar/` is unchanged and no
root-route promotion. OT1 — the retired encoder-trial watchdog — was not
touched. Historical analysis remains the next new feature after this
correction.

## Codex review update — 2026-09-10

See CODEX-DECISIONS.md Eighth return. TE1 accepted with local-schema limits;
principal VC1 accepted for owner preview. VC1-close remains before deployment:
approximate-bar explanation, scope table breakpoint changes to Chatter, responsive
accessible labels. Do not redispatch completed work. Owner may review now;
no deployment authorized. Current reviewed HEAD d66b52e; Codex documentation
edits are intentional and uncommitted. Fresh focused Vitest: 56 passed/2 files.

2026-09-10 owner addition: sortable Chatter is OPEN within VC1-close. Read the appended binding sorting contract in VISUAL-CORRECTION-PLAN.md. Preserve completed tasks; return sorting with the same closure review/preview. No deployment authorized.

