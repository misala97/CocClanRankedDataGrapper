> HISTORICAL EVIDENCE — copied unchanged from codex/radar-b1 at 6c63959c3553607fd96e45ed43136256e9390d96 on 2026-09-13 for the B1C packet. This is NOT the current ledger; the current one is B1C-LEDGER.md and the current handoff is HANDOFF.md.

# B1 progress

2026-09-10, Codex planning. Binding brief: B1-IMPLEMENTATION-PLAN.md.

| Item | State |
| --- | --- |
| B image direction | Owner approved |
| Separate interactive prototype | Explicitly declined; actual app is review surface |
| Current app inspection | HEAD 472f345; Hub/Research/navigation inspected; Codex docs dirty |
| Implementation brief | Written; shell + integrated Chatter, Overview composition later |
| B1.1 shell | **Built** — `ad07be4` |
| B1.2 workspace | **Built** — `ad07be4` |
| B1.3 verification | **Done** — tests, build and measured browser checks below |
| B1.3 independent review | **Done** — both lanes returned; every finding resolved |
| Owner review of working B1 | Open |
| Deployment | Not authorized |

Capture off. Production state is recorded in release records, not inferred from local branch tip. The original green hub at `/radar/` remains functional and untouched.

## Implementation base, 2026-09-10 (Claude)

| Fact | Value |
| --- | --- |
| Worktree | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1` |
| Branch | `codex/radar-b1`, created from `472f345` |
| Base HEAD | `472f345` — the tip of `codex/radar-release-candidate` the brief names |
| Carried in | B1-IMPLEMENTATION-PLAN.md, B1-LEDGER.md, CLAUDE-B1.md, b-direction/, and the dirty CODEX-DECISIONS.md / HANDOFF.md from the candidate worktree |
| Not carried | Stale planning copies of execution ledgers; the candidate worktree is untouched |
| Baseline tests | 40 files, 532 radar tests, all passing before any edit |

`AGENTS.md` does not exist in this repository — searched the worktree and the
primary checkout. The brief's instruction to read it has no target; CLAUDE.md,
the plan and the handoff are the standing instructions that were followed.

**The database is NOT TE1.** The brief points at `personal_apps_radar_te1`, but
the board needs seeded rows to be looked at, and `scratchpad/seed_radar_dev.py`
begins by DELETING `radar_mentions`, `radar_posts`, `radar_mention_events`,
`radar_bucket_sources`, `radar_buckets`, `radar_quotes` and
`radar_daily_closes`. TE1 held 557,604 buckets, 108,540 quotes and 862,124
daily closes that another workstream may still want. So B1 got its own
disposable schema, `personal_apps_radar_b1`, built from TE1's structure and
seeded fresh; TE1 was read once and never written. The worktree `.env` names
the B1 database. No migration was written or run.

**Correction, per Codex's B1 ruling item 5.** An earlier version of this
paragraph said `flask db upgrade` fails locally and that TE1 was therefore
"built by a structure copy". The second half was wrong, and it generalised a
failure that is not TE1's. What actually failed here is `flask db upgrade`
from an EMPTY schema, at `Duplicate check constraint name
'ck_radar_quotes_market'`. TE1 never took that path:
VISUAL-CORRECTION-LEDGER.md records it as a schema-preserving `mysqldump` of
local `personal_apps`, restored into a new database at alembic
`b3d9e1f5a274`, then `flask db upgrade` to the deployed head `a7c31f0b52d4`
— 43 tables restored, 45 after the two migrations, with 29 foreign keys and
62 unique indexes identical to the source. `CREATE TABLE ... LIKE` is what
the OLD clone `personal_apps_radar_wt` used, and carrying none of those 29
foreign keys is exactly why it was replaced.

The B1 database is a structure copy of TE1's tables plus a stamp, which is
weaker than TE1's own provenance, and it is not TE1-equivalent: no
schema/constraint/session verification was run against it. It was adequate
for rendering a board and for the frontend suites, which is all it was used
for. Anything needing constraint fidelity should use TE1's method, not this
one.

## Commits

| Commit | What |
| --- | --- |
| `6320163` | The B1 package carried in, plus Codex's uncommitted CODEX-DECISIONS/HANDOFF edits, unrewritten |
| `909bf85` | `detail_panel` called a move unknown that the board had measured |
| `ad07be4` | B1.1 and B1.2: the dark horizontal shell and the Human chatter workspace |
| `f4d777e` | Every finding from the two independent reviews |

## What was built

**The shell.** The fixed 224px left rail and the workspace margin it reserved
are gone. A 64px identity bar (mark, global search, market/session context)
sits over a 48px destination band — Overview, Human chatter, Watching,
Activity, with Administration right-aligned and rendered for admins only.
Standalone research gets a contextual tab naming the company. Below 860 the
band collapses into a sheet under the identity bar; the skip link, Escape,
focus return and the `aria-controls` target are unchanged.

**The tokens.** Canvas `#091722`, raised surface `#112331`, selection
`#1a3042`, border `#2b4355`, text `#edf3fa` / `#b1c1d3`, orange `#ff9e48`,
cyan `#28c8db`, positive `#45dda0`, negative `#ff6b7c`. Green and red are data
now — a move, a tone, a qualification — and the application's identity is
orange. Everything stays scoped to `.rh`; `/radar/` was opened afterwards and
is the light board it was, with no `.rh` element and no console error.

**The workspace.** Candidates left, the selected company centre, its evidence
right, at three columns from 1600 up — see the review section for why that is
1600 and not the brief's 1280. The right rail is the selected company's own
BOARD ROW — not the detail response's counts, which come from per-post
evidence with a shorter retention and legitimately differ — and a company with
no row on this board says its figures are unknown rather than borrowing
someone else's. Below 1600 the evidence rail moves under the centre before the
chart gives up any width. Below 860 the rail and the company become sequential
screens with a Back to candidates control.

**The address.** `#chatter/<ticker>` carries the selection. `#chatter`,
`#research/<ticker>` and every existing query link resolve to exactly what they
did. The opening selection replaces rather than pushes; an explicit choice
pushes and Back/Forward restore it; refresh, sort and filter never move the
reader off the company they are reading; a selection the filter excludes keeps
its panel and says it is outside the list.

**The table survives.** A Research/Table toggle by the heading. Same rows, same
filters, same ordering, same cached response, all seven columns and every sort
key. Opening a company from the table switches to the reading that can show
one.

**Extracted, not duplicated.** `hub/ResearchContent.tsx` holds the panels both
readings share; `hub/SortPicker.tsx` and `hub/Disclosure.tsx` are one
implementation each now that two callers want them. Standalone `Research.tsx`
consumes the same pieces and its data semantics are unchanged.

## The backend change, and why it is in scope

`leaderboard._assemble` stopped discarding a measured move on 2026-09-10
(`c139856`, deployed). `detail_panel` carried the identical gate and was
missed. The two readings used to live on different pages; the workspace puts
them side by side, so the defect became literal — measured locally at
pre-market, the candidate rail printed `+4.6%` for NVDA while the panel one
column right printed `move unknown`, at the same instant, about the same
number and the same window. Completing an already-ruled fix, not a new design
decision. The panel computes no divergence, so nothing is weakened; the score's
frozen-tape gate lives in the leaderboard and tests `score_eligible` itself.
The new test fails against the old line and passes against the new one.

The centre also names the session the move belongs to, as the row has since
that correction: `at close` when the exchange is shut, `· no print since` when
the tape has frozen while it is open, `today` while it is trading.

## Tests

| Suite | Result |
| --- | --- |
| `npx tsc --noEmit` | clean |
| `npm run build` (both bundles) | clean |
| root vitest | 32 files, 403 tests, all pass |
| radar vitest | 41 files, 563 tests, all pass (25 new) |
| `pytest tests/ -k radar` | 1749 pass, 6 fail, 5 skip — see below |

New behaviour tests, in `hub/ChatterWorkspace.test.tsx` unless noted: opening
selection replaces rather than pushes; one detail request for fourteen
candidates; an empty board asks for nothing; push/Back/Forward; `aria-current`
on the chosen candidate; no previous company under the new one's heading;
selection survives a reordering refresh; a selection the filter excludes; an
unknown deep link; a failed detail scoped to the centre with a working retry; a
malformed company in the address; filter and ordering across the mode toggle;
opening from the table; the evidence rail reading the board row; the rail
saying unknown for a company with no row; the watch mutation and its refusal.
In `navigation.test.ts`: the `#chatter/<ticker>` round trip, a ticker with a
slash, `#chatter/` and a broken escape resolving to the bare list, `#chatter`
unchanged, and the span riding along only when there is a chart.

**The six backend failures are not this work.** Four fail identically on
unmodified code in the release-candidate worktree — three in
`test_radar_yahoo.py` (`daily_closes` returning `[]` from a fake payload, no
database involved) and
`test_radar_trial_writes.py::test_a_lexicon_tone_carries_no_model_name`. The
other two depend on an EMPTY database and this one is seeded: both in
`test_radar_profile.py`, asserting a flat profile for a source with no
history. They pass on TE1 and fail on the seeded schema; no code change is
involved.

## Measured on the running application

`radar-design/b1-shots/b1-checks.json` holds the raw numbers, computed from
what the browser painted rather than from the stylesheet.

- **Contrast**: lowest of 25 sampled roles is 6.62:1 (candidate ticker). Focus
  ring `rgb(255,158,72)` 3px solid, 8.9:1 on the canvas.
- **Type**: no text under 12px anywhere on the workspace.
- **Chart axis**: 12.2–13px rendered at every width, in both the side-by-side
  and the sequential layout. The size is written in viewBox units, so it is
  divided by the scale the browser applies.
- **Requests**: 14 candidates, 1 detail request, for `NVDA` only.
- **Overflow**: 0px of horizontal document overflow at 1920, 1440, 1024, 860,
  768, 390 and 320.
- **Tap targets**: nothing under 44px at 390.
- **Escape** closes an evidence disclosure, returns focus to its toggle, and
  leaves `#chatter/NVDA` untouched.

## Screenshots

`radar-design/b1-shots/`, all captured against the running application.
`chatter-research-*`, `chatter-table-*`, `chatter-mobile-*`, `overview-*`,
`watching-*`, `activity-*`, `admin-w1440`, `research-standalone-w1440`,
`menu-open-w390`, `focus-candidate-w1440`, `chatter-unknown-ticker-w1440` and
`old-board-unaffected-w1440` are live data from the seeded database.

The `fixture-edge-*` files are the only ones that are not: each starts as the
real response and has named fields rewritten in flight, which is why they are
prefixed. They cover an empty candidate list with a selection outside it, a
failed refresh with the previous answer on screen, a board that could not be
loaded at all, and a 1D chart priced from daily closes.

## Running it

The application, not a preview. Its database is the disposable B1 schema and
the two accounts exist only there.

```
cd C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1/personal_apps
PYTHONPATH=. py -3.12 -c "from app import app; app.run(host='127.0.0.1', port=5002)"
```

Then `http://127.0.0.1:5002/radar/hub/?market=us&segment=#chatter`, signed in
as `b1admin` / `b1-local-only` (or `b1plain`, same password, to see the shell
without Administration).

## Independent review

Two read-only reviewers, dispatched after the first three commits landed: one
across the code, the tests and contract fidelity, one across the rendered
application at every viewport the brief names, judged against the two
reference images. Both returned findings. All are resolved in `f4d777e`, and
every new test was checked by breaking the code and watching it fail.

### One root cause under four separate symptoms

`.rh button, .rh input, .rh select, .rh textarea { font: inherit; color:
inherit }` is (0,1,1). `.rh-textbutton` is (0,1,0). The reset therefore beat
every component rule that styled a control, and through the `font` shorthand
it took the size as well as the colour. Measured on the running page:

- the **skip link** was `#edf3fa` on orange — **1.84:1**, and it is the first
  thing a keyboard reader meets;
- every **text button** rendered 14px white instead of 12px orange;
- a plain **`.rh-button`** had neither its border nor its background, which is
  why the sort-direction control and the Radar-order reset read as bare text
  rather than as objects — the UI reviewer's "controls are drawn as text where
  the reference draws them as objects".

`:where()` costs no specificity, so the reset drops to (0,1,0) and the
components below it win on source order. The file had already met one instance
of this and patched it by hand; this fixes the class.

### The other correctness findings

| Finding | Resolution |
| --- | --- |
| The evidence rail rendered only on the detail query's success path, so it vanished on **every** company switch and stayed gone on a failure — taking the Watch control with it | It renders in all three states. Every figure in it is the board row, which is in hand before the detail request is made |
| The opening selection was a per-mount ref, and the workspace unmounts on every mode toggle — a cleared selection came back, with `replaceState`, destroying the `#chatter` entry the reader was on | Moved to hub state beside `mode`, `filter` and `sort`. Two tests, one per path |
| The width guard used `min-width: 860` against a stylesheet saying `max-width: 859` — at 859.5 both are false — and never re-evaluated on resize | `859.98px`, plus a `change` listener |
| A deep link to a candidate far down the list left the rail at the top with nothing marked | The selected row is scrolled into view when it is out of it, and never smoothly |
| Opening Filters left **one** candidate row on screen at 1440×1000 | Thirteen. The rail stops being a fixed-height sticky column while its disclosure is open |
| Placeholder text was the browser's `#757575` — **3.48:1**, the low-contrast placeholder the brief names specifically | `--dim`, 7.00:1 |
| The sort direction read `Highest first` and answered only to `Sort lowest first` — WCAG 2.5.3, the rule the row disclosures were already corrected for | The name leads with the visible text |
| `no print since` ended mid-sentence; "Outside this candidate list" and the no-panel copy blamed the filter for absences it did not cause | All three say what is actually true |
| The candidate row was 143px against a specified 100–124, with a hollow band where the right column stacked six lines against the left's four | 124px |
| Text under 12px on five surfaces; two controls under 44px at 390 on the company screen, one of them 22px above another 22px target | None of either, measured across seven routes |

### The chart, which both reviewers reached from different directions

Its labels are written in viewBox units and the browser scaled the drawing to
fit its column, so one number produced a different size at every width. A 12px
label measured **7.7px at 1280 and 13px at 1920**; the two gutter prices are
drawn outside the 912-unit box and were clipped — `$28.53` rendered as
`$28.5:` at 1440 and as a flatly **wrong `$28`** at 1024; and on a phone the
scroller opened at the oldest end, putting the price axis, the last time tick
and the peak annotation all off screen, so the reader met a rising cyan line
with no vertical scale at all.

The drawing is now pinned 1:1. Twelve units are twelve pixels at every width;
it pans where the column is narrower, which is what this surface has always
done rather than scale an axis into illegibility; it paints its gutter into
reserved space; and it rests on the newest price both on load and after a
resize. The session-band captions are sized the same and carry a halo in the
panel's own colour, so the price line passing through them cannot swallow
them. Measured at 1920, 1600, 1440, 1280, 1024, 768, 390 and 320: **axis and
band labels 12px, zero clipped labels, zero document overflow, resting on the
newest price at all eight.**

### One deliberate departure from the brief's numbers

**Three columns now start at 1600, not 1280.** The brief puts the third column
at 1280 and then rules, of 1440: *"if it cannot [fit without clipping], move
the right rail below the center before shrinking chart labels."* Measured,
three columns leave the centre 708px at 1440 and 548px at 1280, against a
drawing 912 wide plus its gutter — so at both widths the choice was the one
the brief forbids. 1600 is the first width where all three columns fit with
the chart at 1:1. Below it the evidence rail sits under the centre, which is
the fallback the brief itself specifies, and the two-column rail widens to
360px because the chart caps at 912 and stops taking the width.

### Two findings recorded rather than fixed

- **"78 voices" in the rail, "78 people" on Overview, "78 distinct authors" in
  the evidence rail** — one quantity, three words, in one session. The two
  this dispatch owns agree (the label and its gloss); `Overview`'s "people" is
  pre-existing copy and contradicts the glossary's own "this is not a count of
  investors". Overview is B2's, and this belongs in that pass.
- **The chatter series reads as a wash rather than as counts**, especially on
  1M and 3Y where it degrades into a filled block. The reference draws a crisp
  bar histogram. Changing it means changing `PriceChart`'s geometry, which
  `/radar/` also draws from — outside this dispatch, and worth its own.

### Verified correct by the reviewers, not merely unreported

The code lane confirmed: the route contract, including `#chatter` resolving to
the identical object it always did and a broken escape falling back to the
list; one board query and one detail query, with the placeholder guard genuinely
preventing a previous company rendering under a new heading; selection
stability under refresh, sort and filter; the evidence rail never mixing the
board row's population with the detail's while claiming one window; the table
sharing one `rows`, one `sortRows` and one cached response; `aria-current` on
a real anchor with no nested interactive controls; every figure traceable to
an API field, with the tone contract's single denominator and stated residual
intact; and the backend change safe — it traced every consumer of
`detail_panel`'s `price_move` and found the score's frozen-tape gate tests
`score_eligible` directly, so nulling the move was never what protected it.

The rendered lane confirmed: no horizontal document scroll at thirteen widths;
the shell's 64px and 48px bands with no surviving rail; the grid at every
breakpoint; sequential screens with a 44px Back control at 768, 390 and 320;
the evidence rail present and readable on mobile rather than hidden; no hidden
tab stops in the closed menu, which closes on Escape and returns focus; real
3px orange focus rings driven by actual Tab presses; the tokens rendering
exactly as specified; the table view intact at 1920 and 390; honest chart
captions on the daily-fallback spans with gaps left as gaps; long names
ellipsised with a `title`; and — asked directly — that the result reads as B's
research desk rather than a dark repaint of the old table.

## Limitations and follow-ups

Named, not fixed, and none of them blocking the owner's look:

- **The chatter series is an area, not a histogram.** See the review section
  above: it needs `PriceChart` geometry that `/radar/` also draws from.
- **Overview says "people" where the rest of the surface says "voices".**
  B2 owns Overview.
- **QQQ has no universe profile in the seeded database**, so its candidate row
  reads `Name unknown` / `Price unavailable` and its panel is the honest
  no-panel state, which now says the company is ranked here and the profile is
  what is missing. That is the seed, not the surface.
- **The identity bar is sparse** — a mark, a centred search and one status
  string across 1920px. The brief forbids inventing the reference's theme,
  language and account controls, so this is a gap to the image by instruction
  rather than a defect.
- Overview keeps its existing composition. B2 is its own dispatch, and its
  saved queue and aggregate activity need their own data design.
- No light/dark switch was added; none was requested.

Codex B1 return ruling added to CODEX-DECISIONS.md: owner preview now; 1600 breakpoint accepted, shared price narrative needs bounded correction before deployment. TE1 historical explanation must be reconciled. No deployment authorized. Reviewed HEAD df139ff; Codex documentation edits intentional.

