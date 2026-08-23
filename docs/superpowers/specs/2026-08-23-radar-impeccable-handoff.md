# Radar visual pass — handoff prompt

Paste the block below into a fresh chat opened at
`C:\Users\michi\Desktop\CodingStuff`.

---

Run `/impeccable` on the radar board surface in `personal_apps`. Scope the
brief with `IMPECCABLE_CONTEXT_DIR=personal_apps/features/radar` — the repo has
no JS workspace markers, so `context.mjs` otherwise only ever reads the root
PRODUCT.md.

## What this is

`/radar/` — a day-trading discovery board. It finds stocks that social chatter
is unusually loud about **before** they are obvious, aimed squarely at penny
stocks and names nobody has heard of. Read at a desk beside a broker terminal,
desktop only.

The brief is `personal_apps/features/radar/PRODUCT.md`. Read it first.

## What state it is in

The structure was rebuilt from scratch today (main, `7d119fd`) against two
approved mockups:

- `docs/superpowers/mockups/2026-08-23-radar-board-busy.html`
- `docs/superpowers/mockups/2026-08-23-radar-board-quiet.html`
- Spec: `docs/superpowers/specs/2026-08-23-radar-board-rebuild-design.md`

The CSS is the problem. `static/radar/radar.css` has a considered token block
at the top and then ~250 lines of deliberately plain layout, written only so
the page would render — grid, column widths, row shape, chart box. No type
scale, no rhythm, no signature, no craft. Michi's words: *"right now it's the
basic base version that looks like the Temu version."*

**Your job is to make this look genuinely excellent.** Treat every line of CSS
below the token block as replaceable. Rewrite it wholesale if that serves.

## How much you may change

**Structural redesign is in scope.** If the arrangement is holding the visual
back, say so and propose the better one — the current layout is a strong
default arrived at by argument, not a boundary. Michi's standing preference is
to decide fresh rather than to work around what already exists.

Two categories, and they are different:

**Principles.** Each of these cost a session to reach and one of them has been
re-broken twice. Changing one is allowed, but make the argument first and get
agreement — do not simply build over it.

- **Green and red mean price direction and nothing else.** Not a button, not a
  badge, not a brand colour. On a stock tool a green accent reads as a buy
  signal, and PRODUCT.md's scope boundary forbids the surface implying a
  recommendation. Violet carries chatter, selection and focus. A green/red
  bull/bear tone bar has been built and deleted **twice** — don't be the third.
- **An absence is never a zero.** Chatter history begins 2026-08-21 and price
  goes back three years, so most of a long chart is a stretch nobody observed.
  It must not render as silence. Same for a shut exchange versus a frozen tape:
  different facts, and only one of them is about the stock.
- **Row phrases are typed clauses from the server.** `features/radar/phrasing.py`
  decides the wording; the client styles by `kind` and never parses text. Kinds:
  `ratio venues people price-up price-down price-flat new warn plain`. New kinds
  are fine — add them server-side. Reconstructing wording in the client is not.
- **Nothing may read as advice.** Every figure describes what was observed.

**Open — change these freely if you have something better.** Two panes at
404px/rest. The five-zone order in the panel. Chatter in a lane beneath price
rather than overlaid (the reasoning was that three observed days out of a
thousand vanish when overlaid — beat that and it's yours). The row's
three-line composition. Where the span buttons live. Fixed-slot segment chips
(they must not reorder or vanish as data changes, but how they look is open).
Markup, component boundaries, and the SVG structure, as long as the tests stay
green.

**Mobile is out of scope.** A single-column fallback exists below 900px and
gets no design attention. Do not spend effort there.

## Files

```
personal_apps/static/radar/radar.css          the visual system (yours)
personal_apps/static/radar/src/
  board/BoardPage.tsx      two-pane shell, selection, URL
  board/Controls.tsx       segment / sources / venues / window chips
  list/ListPane.tsx        header, the state line, rows
  list/TickerRow.tsx       ticker, name, sparkline, phrase, meta
  list/Excluded.tsx        "14 other tickers were not listed: ..."
  detail/DetailPane.tsx    span buttons, zone order
  detail/Identity.tsx      ticker, full name, facts, price
  detail/PriceChart.tsx    the two-lane SVG
  detail/Breakdown.tsx     venue table, wording counts, concentration stats
  detail/Posts.tsx         the posts themselves
```

## Running it

```bash
cd personal_apps && PYTHONPATH=. python scratchpad/seed_radar_dev.py
```

That fills the local database with a realistic board — twelve tickers, three
years of daily closes, 1400 posts. Without it the dev board has almost nothing
on it.

Start a server on **5002** (5001 is Michi's own instance, 5000 is coc_stats):

```bash
cd personal_apps && FLASK_APP=app.py python -m flask run --port 5002 --no-reload
```

`/radar/` is login-gated and multi-user. Mint a cookie rather than driving the
login form:

```python
from flask.sessions import SecureCookieSessionInterface
ser = SecureCookieSessionInterface().get_signing_serializer(app)
# session payload is {'user_id': <first AppUser id>} -- not {'logged_in': True}
```

**Screenshot with python-playwright via Bash, then view the PNG with Read.**
Do not use the Browser MCP for screenshots — it has repeatedly failed to
composite frames on this machine. Desktop viewport 1341×950.

After CSS changes: `cd personal_apps && npx vite build -c vite.radar.config.ts`
(only needed for TS/TSX; the stylesheet is served directly).

## Gates

```bash
cd personal_apps && npx tsc --noEmit
cd personal_apps && npm test
cd personal_apps && python -m pytest tests -q -k radar
```

All must stay green. Four gym pytest failures
(`test_gym_exercise_ownership`, `test_gym_ownership`, two in
`test_gym_routes_smoke`) are pre-existing dev-database issues, unrelated —
ignore them.

## Two states to design, not one

A quiet board is the **normal** case, not the exception: market closed, two or
three rows, every live number frozen. The busy mockup and the quiet mockup are
both approved and both have to look deliberate. A design that only sings with
twelve rows and a live tape has solved the wrong problem.

## Working method

Michi's standing preference: **real HTML mockups before code.** One screen per
turn, and the quiet state gets its own — two visual systems have been rejected
after shipping for want of this. Show screenshots and get a yes before
rewriting the stylesheet.

If you land on a structural change, mock that up too rather than describing it.
