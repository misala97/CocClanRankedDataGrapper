# Gym Tracker — Statistik page

**Date:** 2026-07-29
**Feature:** `personal_apps` / gym
**Status:** design approved, ready for planning

---

## 1. Problem

The app answers four questions well, and all four are about *now*: am I
progressing, am I training everything, am I training regularly, is load going
up. Heute answers them over deliberately bounded windows — a 28-day rolling
balance, eight weeks of tonnage, the last five workouts, the exercises
currently stalling.

Nothing answers the other kind of question: **what does my whole training
history say about me?** Not "is anything stalling this month" but "I have never
once trained below six reps", "my morning sessions are 28 % bigger than my
evening ones", "I have lifted 142 tonnes since June".

Those are not available anywhere in the app, and several of them are not
derivable by eye from the pages that exist. A mining pass over the current
384 completed sets produced findings the owner had not seen, which is the
evidence this page has something to show.

## 2. Goals

1. A fourth navigation destination, **desktop-only**, presenting all-time
   analytics across the whole training history.
2. State findings in words, backed by the figures — not a wall of charts the
   reader has to interpret unaided.
3. Never state a finding the data cannot carry.

## 3. Non-goals

- **Not a second Heute.** Heute is windowed; this page is all-time. The rule
  for deciding where any future statistic belongs is *is this about now, or
  about everything?*
- **No stored plans, goals or targets.** `PRODUCT.md` rules out a routine
  builder, a scheduler and per-exercise targets. The principle behind that ban:
  **the app never holds a plan, it reads history and reacts.** Standing state
  the app maintains on the user's behalf can go stale and start lying; a
  recomputed observation cannot. Advice *derived from history* is explicitly in
  scope — the app already does it (`session_finished.html` names an exact next
  weight for a stalled lift, and the deload suggestion fires off measured
  fatigue). A stored goal weight is what stays out.
- **No mobile layout work.** The page renders on a phone if the URL is opened
  directly, but it is composed for the desktop width and is not linked from the
  mobile tab bar.
- **No duration-based statistics.** The session duration data contains a
  0-minute and a 180-minute session; any total built on it would be fiction.

## 4. Register and voice

Findings are stated, not merely plotted. Each zone leads with the observation
in German — *"Du trainierst ausschließlich im 6–12er Bereich"* — with the
figures beneath as evidence. This matches the app's existing voice (the
finished-session verdict line, the stall advice) and is what makes the page
worth opening rather than a table dump.

### 4.1 The silence rule

**A stated finding must never outrun its sample.** Every finding carries a
minimum-sample threshold, declared as a named constant in `analytics.py` so it
is visible and adjustable in one place. Below it the chart still renders,
annotated with its sample size, and the sentence is replaced by *"noch zu wenig
Daten"*.

| Finding | Constant | Threshold | Counts |
|---|---|---|---|
| Time of day | `MIN_SESSIONS_PER_DAYPART` | 8 | sessions in **each** bucket being compared |
| Rest-day effect | `MIN_SESSIONS_PER_GAP_BUCKET` | 5 | sessions in **each** gap bucket |
| Rep-range concentration | `MIN_SETS_FOR_REP_RANGE` | 50 | completed sets |
| Intra-session fatigue | `MIN_ROWS_FOR_FATIGUE` | 30 | exercise-rows with ≥2 sets |
| Weekday distribution | `MIN_SESSIONS_FOR_WEEKDAY` | 14 | finished sessions |

These are judgement calls, not derived values: they are set where a pattern
stops being plausibly coincidental for a single lifter's log, and they are
deliberately low enough that the page says something in its first months. They
gate **the sentence only** — never the chart.

Measured against the current 21 sessions:

| Finding | Sample today | Statable |
|---|---|---|
| Rep-range concentration | 384 of 384 sets | yes — unarguable |
| Intra-session fatigue curve | 128 exercise-rows | yes |
| Time of day | 11 morning vs 9 evening sessions | yes, thin but real |
| Rest-day effect | buckets of n=3, n=2, n=3 | **no** — noise dressed as insight |

The page therefore gets smarter as the history grows, rather than being
confidently wrong in week six.

## 5. Scope: the five zones

All figures below are from the live database at time of writing and are
included to show the shape of real output, not as fixtures.

### 5.1 Das Werk — the body of work

One divided readout band, full width, all-time: total tonnage, completed sets,
total reps, finished sessions, training span (first session to today), and the
largest single session **measured by tonnage**, shown with its date. Currently
142 t · 384 sets · 21 sessions · since 14.06.2026.

Deliberately excludes time under the bar (§3).

### 5.2 Fortschritt — progression

Every exercise ranked by all-time change in estimated 1RM: exercise, sessions,
first e1RM, current e1RM, change %, current best weight, and a sparkline.
Sortable by any column.

Currently every one of the 14 qualifying exercises is positive, from Military
Press at +57.9 % (12.7 → 20.0) to Preacher Curl at +2.6 %. That fact is itself
the zone's finding, and it explains why Heute's stall panel is empty.

Exercises with fewer than two qualifying sessions are excluded — there is no
first-versus-current to compute.

### 5.3 Wie du trainierst — the behavioural layer

**The zone the page exists for.** None of this is derivable from any other
surface in the app.

- **Time of day** — volume per session by training hour. Currently 7 890 kg
  (08–14 h) versus 6 172 kg (19–23 h), a 28 % difference.
- **Rep-range distribution** — currently 63.8 % at 6–8 and 36.2 % at 9–12, with
  **zero** sets below 6 or above 12.
- **Intra-session fatigue** — first set versus last set within an exercise.
  Currently −5.1 % weight, 9.1 → 8.0 reps, across 128 rows.
- **Weekday distribution** — which days actually get trained.
- **Rest-day effect** — volume as a function of days since the previous
  session. Below threshold today; renders with its sample size and no sentence.

### 5.4 Wohin die Arbeit geht — distribution of effort

All-time tonnage and set share per muscle group and per exercise, two columns
side by side, using the existing `.hbar` primitive. Currently Rücken 27.9 %,
Brust 23.8 %, Bizeps 16.6 %, Trizeps 16.4 %, Schultern 15.3 % — and no leg
training at all, which is a finding worth stating.

### 5.5 Rekorde — the record timeline

Every personal record ever set, newest first, dated, each naming the value it
beat. A timeline rather than a count; the count already lives on Verlauf.

## 6. Architecture

### 6.1 A new module

`stats.py` is 764 lines and `routes.py` is 1 338. Adding a page's worth of
analytics to either makes an existing problem worse.

**`features/gym/analytics.py`** — new, pure, zero SQLAlchemy imports,
consuming the same `stats.PerformedExercise` shape. The split mirrors the
product boundary:

| Module | Answers | Feeds |
|---|---|---|
| `stats.py` | windowed, per-session judgements: is this a record, is this stalling, what is the 28-day balance | Heute, session pages |
| `analytics.py` | all-time aggregates and descriptions: totals, rankings, distributions, behaviour | Statistik |

The same question that decides which page a statistic belongs on decides which
module it lives in.

Where a figure Statistik needs already exists in `stats.py` (`epley_1rm`,
`row_volume`, `best_e1rm`, `progression_rows`), `analytics.py` imports and
reuses it rather than reimplementing. `analytics.py` may depend on `stats.py`;
never the reverse.

### 6.2 Route

`GET /gym/statistik` → `gym_statistik()`. Thin: **one** `load_performed()`
call — the page's single query, the same bulk-loading discipline Heute,
Übungen and Verlauf follow — then hand the rows to `analytics` and render. No
analysis in the route.

### 6.3 Deload handling

Follows the rule already established across the feature:

- **Excluded** from the progression ranking (§5.2) and the record timeline
  (§5.5) — those are judgements, and a deliberately light session is not an
  attempt at either.
- **Included** in tonnage, set counts, muscle share, rep range, fatigue curve
  and time-of-day — those describe what happened, and a deload session
  genuinely happened.

### 6.4 Navigation

`gym_nav_items` in `_nav.html` gains a fourth entry carrying a `desktop_only`
flag, which the `.tabbar` loop filters out and the `.topbar` loop does not. The
mobile bar keeps its hardcoded `repeat(3, 1fr)` untouched.

The URL stays reachable on a phone. Opening it directly renders the page
single-column; nothing is hidden and no redirect fires.

### 6.5 Charts

The app already has token-native CSS bar primitives — `.vbars` / `.vbar` and
`.hbar` — driven by inline percentage heights and needing no JavaScript.

- Zones 1, 3 and 4 use those. Distributions and shares do not need a chart
  library.
- Zone 2's sparklines are **inline SVG polylines, no chart library**.
  *(Superseded during planning: this originally specified lazy-loaded Chart.js.
  Fourteen sparklines in fourteen table cells is the case a chart library is
  worst at — a 208 KB payload for decoration, canvas unable to resolve `var()`
  so every line would need its tokens resolved in JavaScript first, fourteen
  render loops, and no axes, legend, tooltip or interaction to justify any of
  it. An SVG polyline inherits `currentColor`, scales with its row, and prints.
  Net result: the page loads no charting library at all.)*

## 7. Composition

Composed for the width rather than stacked, per `PRODUCT.md`'s requirement that
desktop "use the width meaningfully, not stretch the phone layout".

- **Das Werk** — full-width divided readout band across the top.
- **Fortschritt** — full width; the table is the point.
- **Wie du trainierst** — **not a card grid**, which §4.5 of the design brief
  bans outright. Two tiers instead: one featured finding, the rest as divided
  rows in a single shared panel, reusing the `.row` component (`__main` for the
  sentence, `__wide` for its inline bar, `__trail` for the headline number).
- **Wohin die Arbeit geht** — two columns side by side.
- **Rekorde** — a dated list, newest first.

Finding order within zone 3 is **fixed and editorial**, not computed. Ranking
by "most surprising" would need a definition of surprise the data cannot
supply, and a lead item that reshuffles between loads reads as broken.

## 8. Edge cases

| Case | Behaviour |
|---|---|
| No finished sessions at all | Every zone renders its own empty state; no chart of nothing |
| Sample below a finding's threshold | Chart renders with its sample size; sentence replaced by *"noch zu wenig Daten"* |
| Exercise with fewer than two qualifying sessions | Excluded from the progression ranking |
| Exercise whose only history is deloads | Excluded from progression and records; still counted in tonnage and set share |
| Exercise never trained | Absent from distributions; not rendered as a zero row |
| Muscle group with no exercises | Absent rather than shown at 0 % |
| The 0-minute and 180-minute sessions | Duration is unused on this page, so they cannot distort it |
| Viewed on a phone | Renders single-column; wide tables scroll inside `overflow-x: auto`, never the body |

## 9. Verification

- **`tests/test_gym_analytics.py`** — pure, no app context, no database, same
  style as `test_gym_stats.py`. Covers every analytics function, the deload
  inclusion/exclusion split of §6.3, and the silence gates of §4.1 (a finding
  must go silent below threshold and appear above it).
- **`tests/test_gym_routes_smoke.py`** — one line asserting `/gym/statistik`
  renders.
- **Browser pass** at 1280 and 390 px: no horizontal page overflow at 100 % or
  200 % text, wide tables scrolling in their own containers, and the mobile tab
  bar still showing exactly three tabs.

## 10. Risks

- **Six weeks of history is thin.** Several findings sit near or below their
  thresholds today. This is handled rather than avoided (§4.1), and every one
  improves on its own as training continues — but the page will feel fuller in
  three months than it does on the day it ships.
- **Zone 3 is the one carrying the page.** If its findings turn out to be
  obvious in practice rather than surprising, the page degrades to a
  well-presented restatement of Heute over a longer window. The mining pass
  suggests otherwise, but that is a judgement made on one lifter's data.
- **`analytics.py` will grow.** It starts with roughly a dozen functions. The
  boundary against `stats.py` has to be defended on every future addition, or
  the split silently stops meaning anything.
