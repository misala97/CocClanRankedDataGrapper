# H2 evidence: chatter, research and search

Captured 2026-09-09 at commit for task H2, against a local server on port 5051.

## What the data in these screenshots is

**Real server output, at a past instant, and it is labelled here because the images
cannot label themselves.**

The disposable database is a clone taken while the ingest daemon was not running here, so
its newest bucket is 2026-09-01 18:15 UTC. A board built at today's wall clock is
legitimately empty — the first capture of `#chatter` showed exactly that, and the empty
state is in the suite. To photograph a populated page, `build_payload` and
`detail_panel.build` were called for 2026-09-01 18:22 and their **unmodified serialized
output** was served to the browser in place of the live endpoints. Every number, name,
mark and clause in these images was produced by the production serializer from rows that
were really collected. Only the instant is historical.

Nothing was invented, and no fixture was hand-written for these images.

| File | Route | Viewport |
| --- | --- | --- |
| hub-chatter-1440.png | `/radar/hub/#chatter` | 1440 x 1000 |
| hub-chatter-390.png | `/radar/hub/#chatter` | 390 x 844 |
| hub-research-1440.png | `/radar/hub/#research/SNDK` | 1440 x 1000 |
| hub-research-768.png | `/radar/hub/#research/SNDK` | 768 x 1024 |
| hub-research-390.png | `/radar/hub/#research/SNDK` | 390 x 844 |

All five: **no document horizontal scroll, no console errors, no page errors.**

## What the images show that the tests do not

- The chart draws. Its renderer paints from CSS variables belonging to the old board's
  stylesheet, which the hub deliberately does not load — so every fill and stroke fell
  back to black and the first capture was a solid rectangle. Fixed by mapping those names
  to the hub palette; the second capture is the price line in green, the chatter lane in
  sage, session bands behind, the normal-rate line dashed.
- The row was repeating itself. The server's phrase ("3.2x its normal, 2 venues, 6
  people, price +3%") restated the Attention, Sources, Voices and Price columns beside it.
  Removed from the list; it stays on Research, where it is the summary rather than a
  second copy of the table.
- Two headings said the same thing. The breakdown and posts components bring their own
  heading and caption, and both captions name the window.
- **The price was off-screen at 390.** Six columns scrolling sideways put Tone and Price
  past the right edge, which the spec forbids for exactly those fields. The row is now
  stacked below 700px with each cell labelled, so every field is visible without
  scrolling.

## Composition against the approved prototype

Kept: pine navigation with grouped destinations and Administration separated at the foot;
the warm near-white workspace and white bounded surfaces; green for the one action;
company mark, ticker and name in the first column; attention as a multiple with "its
normal rate" beneath it; the research page as identity, price, chart, evidence, with a
washed summary rail at desk width that falls below the evidence when the rail would
squeeze the chart.

Deliberately not carried over: the prototype's "Verified on Scalable" filter (broker
availability is unverified and the spec forbids implying otherwise); its generated
"Consider entry" thesis (the summary states the server's clauses and the concentration
figures and nothing else); and the News, Combined, Portfolio and Analysis destinations,
which are roadmap.

## Honest gaps visible in these images

- Tone reads "Not read yet" on every row. That is true of this snapshot: the sentiment
  pass had not judged these mentions. It is not a rendering failure.
- The research breakdown and posts are empty for SNDK in this window, and say so. Also
  true of the snapshot.
- Every row carries "Warming up" and "Partial window". Real marks from thin baselines in
  the cloned data.
