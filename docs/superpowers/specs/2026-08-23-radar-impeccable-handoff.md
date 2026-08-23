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
approved mockups and is **not up for redesign**:

- `docs/superpowers/mockups/2026-08-23-radar-board-busy.html`
- `docs/superpowers/mockups/2026-08-23-radar-board-quiet.html`
- Spec: `docs/superpowers/specs/2026-08-23-radar-board-rebuild-design.md`

The CSS is the problem. `static/radar/radar.css` has a considered token block
at the top and then ~250 lines of deliberately plain layout I wrote only so the
page would render — grid, column widths, row shape, chart box. No type scale,
no rhythm, no signature, no craft. Michi's words: *"right now it's the basic
base version that looks like the Temu version."*

**Your job is to make this look genuinely excellent.** Treat every line of CSS
below the token block as replaceable. Rewrite it wholesale if that serves.
Change markup where the visual demands it, as long as tests stay green.

## Do not relitigate

- **Green and red mean price direction and nothing else.** Not a button, not a
  badge, not a brand colour. On a stock tool a green accent reads as a buy
  signal, and PRODUCT.md's scope boundary forbids implying a recommendation.
  Violet carries chatter, selection and focus. A green/red bull/bear tone bar
  has been built and deleted **twice** — don't be the third.
- **Two panes, list left and detail right.** Chosen over a separate ticker page
  after argument.
- **Chatter gets its own lane under the price line, not an overlay.** Chatter
  history starts 2026-08-21 and grows a day per day; price goes back three
  years. Overlaid, three days out of a thousand is invisible.
- **The boundary where observation begins is drawn on purpose.** An absence is
  never a zero — that rule runs through the whole project.
- **Row phrases are typed clauses from the server.** `features/radar/phrasing.py`
  decides the wording; the client styles by `kind` and never parses text. Kinds:
  `ratio venues people price-up price-down price-flat new warn plain`. Style
  them well — this is the main typographic problem on the list.
- **Segment chips render at a fixed count**, zero-count ones dimmed, never
  removed and never reordered. They used to vanish at zero and the strip
  changed shape between loads.
- **Mobile is out of scope.** A single-column fallback exists below 900px and
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

Show Michi screenshots before committing.
