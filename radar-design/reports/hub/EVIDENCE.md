# Hub visual and browser evidence

Captured 2026-09-09 against a local server on port 5051, after the H1–H4 reviews and
their fixes. Supersedes the H2-only capture this file first held.

## What the data in these screenshots is

**Real server output, at a past instant, with one labelled fixture — and it is written
down here because an image cannot label itself.**

The disposable database is a clone taken while the ingest daemon was not running, so its
newest bucket is 2026-09-01 18:15 UTC. A board built at today's wall clock is
legitimately empty, and the first capture of `#chatter` showed exactly that; the empty
state is in the suite. To photograph a populated page, `build_payload` and
`detail_panel.build` were called for 2026-09-01 18:22 and their **unmodified serialized
output** was served in place of the live board and detail endpoints. Every number, name,
mark and clause in those images was produced by the production serializer from rows that
were really collected. Only the instant is historical.

**The one fixture:** Watching and Overview need marks, and this account has none. Their
`watching` and `watch_rows` are the board's own top three rows presented as marks, with
the second flagged ineligible so the quiet state is visible. Real rows, an invented
membership.

**No fixture at all** on Activity and Admin: those two are the live endpoints against a
database with no recorded runs and capture switched off, which is exactly the state both
pages have to describe honestly.

| File | Route | Viewport | Data |
| --- | --- | --- | --- |
| hub-overview-1440 / -390 | `#overview` | 1440x1000, 390x844 | real board, marks fixture |
| hub-chatter-1440 / -390 | `#chatter` | 1440x1000, 390x844 | real board |
| hub-watching-1440 / -390 | `#watching` | 1440x1000, 390x844 | real rows, marks fixture |
| hub-research-1440 / -768 / -390 | `#research/SNDK` | 1440, 768, 390 | real detail |
| hub-activity-1440 / -390 | `#activity` | 1440x1000, 390x844 | live endpoint |
| hub-admin-1440 / -390 | `#admin` | 1440x1000, 390x844 | live endpoint |
| hub-missing-1440 | `#portfolio` | 1440x1000 | the recovery view |

All thirteen: **no document horizontal scroll, no console errors, no page errors.**

## The separate accessibility and real-API pass

`verify_hub.py` drives all five destinations at 1440, 768 and 390 against the **live**
endpoints with no interception at all, and reports:

- no document horizontal scroll and no console or page errors on any page at any width;
- the skip link is the first tab stop, carries a 3px focus ring, moves focus to
  `#rh-main`, and does not replace the page — which it used to;
- no page renders the recovery view by accident.

## What the images caught that the tests did not

- The chart rendered as a **solid black rectangle**. Its renderer paints from CSS
  variable names belonging to the old board's stylesheet, which the hub deliberately does
  not load, so every fill and stroke fell back to black.
- Each row **repeated its own columns as prose** underneath itself.
- At 390 the **price sat past the right edge** of a sideways-scrolling table, which the
  spec forbids for exactly that field. Rows stack below 700px now, every field labelled.
- The reused posts and breakdown components lost the flex gaps that separate a heading
  from its qualifier, so the page read "What people are saying· 0 posts".

## Reviewer findings visible here, and what changed

- **Absent evidence was printed as zero.** SNDK's summary read "0 independent voices
  across 0 posts" beside a clause from the same payload saying 80 mentions. The bucket
  totals outlive the per-mention rows behind them, so an older window legitimately has
  totals and no evidence. It now says so instead of reporting an absence as a
  measurement.
- **A tone percentage the server forbids.** `board.py` returns three counts and explains
  why: the lexicon scores 0.0 both for "balanced" and for "no word matched", so a single
  "% bullish" is "noise wearing a percentage sign". The list drew that percentage, and it
  rounded — one bullish post in two hundred would have read 0% positive. Three counts now.
- **A caption claiming a resolution the line lacked.** A 1D chart drawn from daily closes
  was labelled "intraday quotes"; the guard the board panel has for exactly this was not
  copied with the table it belongs to.
- **The previous company under the new company's heading.** Cached placeholder data
  rendered as though it were the requested ticker.
- Activity said "Partial coverage" — the one word its own endpoint refuses — and called a
  day with three crashed runs "Not recorded", beside a cell saying "3 failed".

## Composition against the approved prototype

Kept: pine navigation with grouped destinations and Administration separated at the foot;
warm near-white workspace and white bounded surfaces; green for the one action; company
mark, ticker and name in the first column; attention as a multiple with "its normal rate"
beneath it; research as identity, price, chart, evidence, with a washed summary rail at
desk width that falls below the evidence when the rail would squeeze the chart.

Deliberately not carried over: the prototype's "Verified on Scalable" filter (broker
availability is unverified and the spec forbids implying otherwise); its generated
"Consider entry" thesis (the summary states the server's clauses and the concentration
figures and nothing else); and News, Combined, Portfolio and Analysis, which are roadmap.

## Honest gaps still visible in these images

- Tone reads "Not read yet" on every row. True of this snapshot: the sentiment pass had
  not judged these mentions.
- Research's breakdown and posts are empty for SNDK in this window, and now say the
  per-post evidence is not held rather than showing zeros.
- Every row carries "Warming up" and "Partial window" — real marks from thin baselines in
  the cloned data.
- Activity is seven gaps and Admin's archive age is "Nothing captured yet", because
  nothing has been recorded and capture is off. That is the truth about this database.
