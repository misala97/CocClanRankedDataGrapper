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
| **VC1c visual verification** | **Complete** | Matched before/after screenshots, 42 browser checks, measurements in `reports/vc1/`. |
| **Two defects found by looking** | **Fixed** | `b1cf313` the class collision, `43526e8` the tone bar's invisible rare share. Both below. |
| Independent review | Complete | Read-only reviewer against this contract and the actual screenshots; findings recorded below. |
| Owner acceptance | **Open — this is the ask** | Run the preview and look at it. Command below. |
| Deployment | Not authorized | Separate decision, after visual acceptance |

Baseline: release-candidate branch `d3bc795`; production `ba1c381` per accepted
RELEASE-RECORD.md. HEAD after this work is **`43526e8`**.

| commit | what |
| --- | --- |
| `c90cf92` | VC1a — additive `activity_sources`, pure tone/source presentation helpers |
| `db9f153` | VC1b/VC1c — the corrected Chatter, filters disclosure, CSS, responsive rules, screenshots |
| `ea98c50` | Codex's brief, dispatch and reference images carried in, plus this ledger |
| `b1cf313` | the panel's company filter had taken the topbar search's class |
| `43526e8` | the tone bar drew a rare share as nothing |

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

**Columns**: a colgroup with `table-layout: fixed` at 26/12/10/18/18/12/4 —
two points moved from Attention and Voices into Sources, and one from Tone,
which the contract permits to avoid collisions. Measured at 1440: 285 / 132 /
110 / 197 / 197 / 132 / 44 px.

**Filters**: market, window and size on the bar; breadth and the feed
checkboxes behind a **More filters** disclosure that names what it is set to
(`Any venue · all 3 feeds`). The R1 last-feed refusal is unchanged and still
tested.

**Breakpoints**: navigation collapses at **1080** and the table stacks at
**860**; they used to be one breakpoint at 700. With seven columns that was
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

| | before (`d3bc795`) | after (`db9f153`) |
| --- | --- | --- |
| plain row, fixture | 120–166 px | **86–90 px** |
| row with warnings, fixture | 165–166 px | **105–106 px** |
| row with three warnings, real | — | 133 px (badges wrap) |
| tone bar | none | **104 × 6 px** |
| row at 768 | 664 px | **271–285 px** |
| document scrolls sideways at 768 | **yes** | no |

Five plain rows are 430 px, inside the contract's 440. Type sizes measured from
the rendered page: row values 13 px, secondary 12 px, headings 12 px.

**One honest regression, local only.** On a board where nothing has been
tone-read, the corrected row is ~8 px taller than the old one (106 against 98),
because `No tone sample` carries the contract's empty track where the old cell
had a single muted line. Every real local row is in that state, because the
development copy holds **zero** `radar_posts` and `radar_mentions` rows.
Production is not in that state — the owner's own rejected screenshot shows
tone counts — and on a row that has a sample the correction is 165 px → 106 px.

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
| `page-*.png` | Overview, Watching, Activity, Administration, Research at three widths |
| `state-nomatch-1440.png` | the in-page filter matching nothing |
| `state-refresh-failed-1440.png` | a refresh that failed; the rows stay |
| `state-first-paint-1440.png` | the embedded payload, before any fetch |
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
for. `state-first-paint-1440.png` — the embedded payload before any fetch.

### Browser checks — 42, all passing, no console or page errors

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
| `npx vitest run -c vite.radar.config.ts` | **475 passed**, 39 files |
| `npx vitest run` (root config) | **403 passed**, 32 files |
| `npm run build` (includes `tsc --noEmit`) | exit 0 |
| `pytest` — leaderboard, api, board, hub_page, watch, watch_api, chatter_eligibility, board_sort, phrasing, vite_assets | **216 passed** |

Every backend run is on `personal_apps_radar_te1`, asserted by name first.

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

## Not done, deliberately

No merge, no push, no deploy. Capture stays off. `/radar/` is unchanged and no
root-route promotion. OT1 — the retired encoder-trial watchdog — was not
touched. Historical analysis remains the next new feature after this
correction.
