# Gym Tracker — the frontend on Preact islands

**Date:** 2026-08-08
**Status:** designed, not implemented
**Branch:** `dev_personal`

## The problem

The live workout screen has produced a regression on nearly every change made to
it over the last several sessions: sheets showing stale content after a
mutation, the reorder toggle losing its listeners after a refresh, transient
state vanishing, orphan sheets left in the DOM. Each was found, each was fixed,
and the next change produced another.

The code is not careless. Every workaround in `session_detail.html` carries a
comment explaining a real subtlety — the reentrant-blur guard in `commit()`
(`session_detail.html:538`), the precision-versus-display split in the steppers
(`session_detail.html:501`), why the save sweep waits 300 ms
(`session_detail.html:1056`). The problems were understood. What is missing is a
structure that holds the solutions in place.

### One root cause

**Server-rendered HTML is treated as the source of truth for everything —
including the state the server cannot know.**

Every mutation posts, receives a freshly rendered page, and replaces
`#session-body` wholesale (`refreshBody`, `session_detail.html:1017`). That swap
destroys or endangers eleven distinct pieces of state that exist only in the
browser:

| # | Client-only state | Where it lives today |
|---|---|---|
| 1 | Reorder mode unlocked | `window.GymReorder.unlocked` (`session_detail.html:1239`) |
| 2 | This device is push-subscribed | `pushSubscribed`, a cached one-time probe (`session_detail.html:1177`) |
| 3 | Which sheet is open | `dialog.open` on the DOM node |
| 4 | Which pane inside that sheet | `pane.hidden` (`session_detail.html:456`) |
| 5 | Add-list search query | `#exadd-search.value` |
| 6 | Number-entry overlay mid-edit | a detached `.field-num__entry` node (`session_detail.html:517`) |
| 7 | In-flight save count and sweep timer | `pendingSaves`, `sweepTimer` (`session_detail.html:1062`) |
| 8 | Which forms are locked | `formsInFlight` WeakSet (`session_detail.html:1121`) |
| 9 | Scroll position | read and restored around the swap (`session_detail.html:1018`) |
| 10 | Rest countdown tick | `startRestTick()` |
| 11 | Save-error banner and its retry closure | `showSaveError` (`session_detail.html:1088`) |

Four functions exist for no reason other than rebuilding that list after the
swap:

- `syncSheets` (`session_detail.html:955`) — 37 lines, carries a comment
  beginning "THE RULE this function exists to enforce, for the next control
  added to a…". A framework invariant maintained by documentation, because the
  code cannot enforce it.
- `syncAfterSwap` (`session_detail.html:921`)
- `applyReorderUI` (`session_detail.html:1252`)
- `applyNotifyState` (`session_detail.html:1185`)

Plus the focus-recovery block inside `refreshBody`
(`session_detail.html:1040-1050`).

Each regression is one more control that was added without being registered in
that manual rebuild. The rule is real, correct, and unenforceable. That is the
defect — not any individual bug it produced.

### Scale

| Template | Lines of `<script>` |
|---|---|
| `session_detail.html` | 953 |
| `uebungen.html` | 230 |
| `verlauf.html` | 170 |
| `heute.html` | 66 |
| `exercise_detail.html` | 29 |
| `session_finished.html` | 16 |
| `statistik.html` | 0 |
| `shared_confirm.html` | 0 |

`session_detail.html` is 1379 lines of which 953 are script. It carries roughly
twice as much client code as the other seven pages combined (511).

## Goal

The owner's stated goal is **user experience**, not defect reduction: the app
should feel instant, and it should feel like an app rather than a website in a
costume. Defect reduction is a consequence, not the target.

That distinction decides the architecture. The two things wanted most — a tap
that responds before the network does, and a screen that never flashes white —
require the client to render its own optimistic state. Server-rendered HTML
cannot do it: between the tap and the round trip there is nothing to show.

## Decisions

| Decision | Chosen | Rejected, and why |
|---|---|---|
| Renderer | Preact | React — 45 KB against 3 KB, identical API, and this runs on gym wifi. |
| Language | TypeScript | Plain JS — types across the new JSON boundary are half the reason the boundary is worth having. |
| Bundler | Vite, eight entry points, one shared component library | `htm` with no build step — avoids the toolchain but forfeits JSX ergonomics and typing, which is most of the value. |
| Server contract | JSON | Continuing to return HTML — optimistic rendering is impossible without client-owned markup. |
| Navigation | Flask keeps routing; one Preact root per page | An SPA with a client router (see below). |
| Offline | None. Optimistic writes with rollback, plus a service-worker cache | A local-first sync queue — the owner confirmed gym wifi is reliable; a sync engine would be scope paid for nothing. |
| Scope | All eight gym pages | `session_detail` alone — the owner chose the full set after being shown that seven of eight pages have no defect problem. |
| Build location | VPS, via `npm ci && npm run build` in the deploy script | Committing `dist/` — a merge conflict on every `dev_personal` → `main` merge, and merges are frequent. |

### Why not an SPA

1. **It cannot ship incrementally.** Half a router does not merge. The
   commitment that the app works at every commit dies with it, and the work
   becomes exactly the multi-week big-bang branch that stalls.
2. **Flask already routes correctly.** Deep links, back button, 404s, scroll
   restoration all work today.
3. **The auth gate would be duplicated.**
   `_require_login_on_full_access_host` (`app.py:70`) gates on both hostname and
   blueprint. A client router needs that logic expressed client-side while it
   still must be enforced server-side. Two copies of an authorization rule is
   how a hole appears.
4. **Instant navigation is no longer the SPA's to sell.** Cross-document View
   Transitions ship in Safari 18.2+ and give animated, flash-free navigation on
   a multi-page app for roughly two lines of CSS.

Components must not assume they own the page, so that adding a router later
stays a contained change if it is ever wanted.

## Architecture

Eight Flask routes at unchanged URLs. Each renders a thin Jinja shell that
mounts one Preact root. Flask keeps routing, the auth gate, and 404s exactly as
today.

```
personal_apps/static/gym/src/
  components/     sheet, stepper, set-row, exercise-row, badge, rail
  state/          signals — one module per client-state concern
  api/            typed fetch wrappers, one per mutation
  pages/          heute.tsx      session.tsx    uebungen.tsx
                  verlauf.tsx    statistik.tsx  exercise.tsx
                  finished.tsx   shared.tsx
```

Build output lands in `static/gym/dist/` with a manifest the Jinja shell reads
for hashed filenames.

### Two stores, and the split is the point

**Server state** — sessions, exercises, sets. Owned by Flask, arrives as JSON,
replaced wholesale on every mutation response. The same authority model as
today: the server recomputes which exercise is live, and the client does not
argue.

**Client state** — the eleven pieces above. Preact signals. Never derived from
server output, therefore never destroyed by a refresh.

`syncSheets`, `syncAfterSwap`, `applyReorderUI`, `applyNotifyState` and the
focus-recovery block are deleted. Not repaired — made structurally impossible to
need, because there is no longer a DOM swap for client state to survive.

### Data flow

**First paint.** The server embeds initial data in the shell as
`<script type="application/json">`. Preact reads it synchronously. No fetch
waterfall on load, so first paint does not regress — this is what keeps
`statistik`, which is entirely static, from getting slower.

**Mutation.** The signal updates immediately, so the UI is correct before the
network is involved. The POST fires. The server's JSON replaces server state on
success. On failure the pre-mutation snapshot is restored and the existing error
banner appears with its existing retry.

**Shared sessions.** The existing poll continues unchanged — `gym_session_sync`
(`features/gym/routes.py:1466`) already returns JSON.

### Server-side

Pydantic models on the 30 POST routes in the gym blueprint, validating inbound
and serializing outbound. `features/gym/routes.py` currently performs 44
`int()`/`float()` coercions on request data behind 3 `ValueError` handlers; a
malformed request 500s today. Those paths close as a consequence of the
models rather than as separate work.

`features/gym/routes.py` is 2863 lines and will grow before it shrinks.
Splitting it by concern is part of the `session_detail` step, not a separate
project.

## Verification

**The rule: no intentional visual change during the port.** Layout, spacing,
copy and behaviour stay as they are because no one decided to change them.

This is deliberately *not* a pixel gate. The page has live clocks
(`startClocks`, `startRestTick`), so a strict diff would require freezing time
and masking regions — a harness built to serve a rule that was never the goal.
Antialiasing noise produces false positives, and some differences are legitimate
(`{{ x|round(1) }}` in Jinja and `toFixed(1)` in JS disagree at the edges).

What the rule is actually for:

1. **Debuggability.** A visual difference should mean something is wrong. Once
   "the new component just renders it a bit differently" becomes acceptable, the
   cheapest signal of breakage is gone.
2. **Scope.** Redesigning during a rewrite is the most reliable way to make a
   rewrite never land.

So verification is:

- Side-by-side before/after screenshots per page and per state, reviewed by a
  human, captured with python-playwright in batched scripts.
- Automated diff at a loose threshold as a smoke check, not a gate.
- The real gate: the existing pytest suite, moved from asserting on HTML to
  asserting on JSON, plus walking one real workout end to end.

Deviation is acceptable, consciously and listed, in three cases: genuine
inconsistencies the component library exposes (three set rows at 14/15/16 px
padding become one value), accessibility gaps in the old markup, and anything
the owner looks at and dislikes — which is noted, shipped as-is, and handled as
its own cycle afterwards.

## Sequence

Each step ships working and merges on its own.

1. **`exercise_detail`** (29 lines of script). Proves Vite, the deploy change,
   the component library and the JSON contract at minimal blast radius. Carries
   all one-time setup.
2. **`session_detail`** (953 lines). The payoff, on infrastructure already
   proven. Includes the `routes.py` split.
3. **`uebungen`** (230) → **`verlauf`** (170) → **`heute`** (66) →
   **`session_finished`** (16) → **`statistik`** (0) →
   **`shared_confirm`** (0). The last three are mechanical.

Smallest page first to de-risk the pipeline, then straight to the page that
actually hurts. Not biggest-first: that is how a branch stalls in week two with
nothing merged.

## Risks

- **German copy moves from Jinja into TSX.** The highest-probability source of
  silent drift. Screenshot review is the guard.
- **`statistik` and `shared_confirm` gain a runtime they do not need** —
  roughly 3 KB, rendered once, on pages with no client behaviour at all. Paid
  deliberately, so that one component library exists rather than two markup
  systems on one app.
- **The component library is designed against `exercise_detail`, the simplest
  page, and then meets `session_detail`, the hardest.** Expect one round of
  reshaping at step 2. Budget for it rather than treating it as a failure.

## Out of scope

Deliberately excluded, each worth its own cycle:

- **Offline write queue.** Ruled out above; the write path goes through a single
  module so it could be added later without touching components.
- **Visual redesign.** Cheaper after the component library exists, which is the
  argument for doing it later rather than never.
- **CSRF tokens on the 30 gym POST routes.** Those routes are currently
  defended by `SESSION_COOKIE_SAMESITE = 'Lax'` (`app.py:33`), which is real
  protection and was set deliberately — `_valid_csrf` (`auth.py:149`) is called
  only from the four auth routes. Token checks would be defence in depth. Worth
  doing, unrelated to this work.
- **Service-worker caching and View Transitions.** Both are the UX work this
  design enables rather than performs. `static/gym/sw.js` currently has no
  `fetch` handler, so the installed PWA has no offline shell and no cache.
- **The other three apps** in `personal_apps` — pubquiz, tips, quizbank — and
  the shared `auth` module. Whether the component library is worth extending to
  them is a question for after the gym pages are done, not now.
