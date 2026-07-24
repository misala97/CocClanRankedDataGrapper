# Login / Register Redesign — Design Spec

**Date:** 2026-07-23
**Pages:** `coc_stats/templates/auth/login.html`, `coc_stats/templates/auth/register.html`
**Routes:** `coc_stats/features/auth/routes.py` — `login()` (~line 61), `register()` (~line 89)
**Type:** Single design cycle covering both pages (two states of one moment).

This is a *structure contract*: layout, content mapping, behavior, responsive
arrangement. Palette, type, spacing, component styling, and the actual CSS
are `impeccable`'s to decide (see "Open questions for impeccable"). These are
the last two pages on the site with no redesign commit behind them — this
replaces the generic centered-card-with-`DM Sans` pattern.

---

## 1. Route contract (the actual data — not the old template)

**`login()`** — GET/POST.
- Already-authenticated visitor (`_any_access()`) → redirect to `/`.
- POST checks username/password against either an `AppUser` row (bcrypt via
  `werkzeug`) or a silent env-credential admin backdoor — same form fields,
  no UI difference. Never expose or hint at the backdoor.
- Template vars: `error` only. One error state, one message at a time:
  either `'Your account is pending approval.'` or
  `'Invalid username or password.'`. No other states.

**`register()`** — GET/POST.
- Same already-authenticated redirect.
- POST validates: username+password required, username ≥3 chars (also
  capped 30 client-side), username not already taken. On success, creates
  an unapproved `AppUser` row.
- Template vars: `error`, `success`. `success` is exactly
  `'Account created — an admin will approve it shortly.'` — the account is
  **not usable yet**; a super-admin must approve it via `/admin/users`
  afterward. This wait is real and load-bearing, not a formality.
- No confirm-password field exists and none is being added.

**Scope confirmed:** visual/UX only. No changes to auth logic, the
env-credential login, or form fields.

---

## 2. Navigation / chrome

**No shared site nav, no `_page_header.html`.** This is the one moment
before any access exists — the sitewide nav (Ranked/War/CWL/Roster/Admin)
has nothing functional to offer a visitor who can't reach any of it yet.

Instead: a **minimal brand mark** (wordmark, page-local) top-left of the
content panel, acting as the way back to `/`. No separate "back to home"
link — the brand mark is the only, sufficient home affordance.

---

## 3. Layout — split screen

Two-panel desktop layout, chosen over a centered card and over an
off-center/no-panel anchor after considering both (see wireframe gate):

```
+------------------------------------------------------------------+
| [BRAND MARK]                                                      |
|                                                                    |
| CONTENT PANEL (left)                    | FORM PANEL (right)      |
| - Product pitch, static                 | - Sign In / Register    |
| - Same on both pages/states             |   toggle                |
|                                          | - Active form           |
|                                          | - Error / success state |
+------------------------------------------------------------------+
```

- **Content panel (left):** static brand/product context. Identical on
  login and register — it does not change when the toggle switches states.
- **Form panel (right):** everything that changes — the toggle, the active
  form, error messages, and register's success takeover.

---

## 4. Login/register relationship — toggle mechanics

Single shared visual shell, both pages render it identically. The
"toggle" at the top of the form panel is **two real links** — `Sign In`
pointing at `/login`, `Register` pointing at `/register` — not a JS tab
panel with both forms hidden/shown in the DOM. Each click is a normal page
navigation; because both pages render the exact same shell markup/styling,
it *reads* as a toggle even though it's a real route change. `Sign In`
carries `aria-current="page"` on `/login`, `Register` carries it on
`/register`.

This keeps each route's existing server-rendered `error`/`success` handling
untouched — no client-side state to reconcile with what the server already
decided to render.

The old cross-links ("Don't have an account? Register" / "Already have an
account? Sign in") are removed — the toggle replaces them.

---

## 5. Content panel — copy (structural content, not decoration)

Static on both pages/all states:

- **Brand mark:** "COC ANALYTICS" (wordmark, page-local, top-left, links to `/`).
- **Headline:** one line pulling from `PRODUCT.md`'s positioning — the
  clan's command center, not a generic "Welcome" line.
- **Body:** one short sentence — war/CWL/raid/ranked/roster in one place,
  verdicts instead of spreadsheets.
- **Three short points**, restating `PRODUCT.md`'s Design Principles in
  visitor-facing language:
  - Verdicts over raw numbers
  - Built for leaders and members alike
  - Live war & raid tracking

Exact wording is copy, not locked verbatim — `impeccable` may tighten
phrasing, but the four content blocks (mark, headline, body sentence, three
points) are the structural contract; don't drop or add a block.

---

## 6. Form panel — states

**Login (default form):**
- Username field, password field, submit ("Sign In").
- Error slot above the fields, rendered only when `error` is set. Single
  message, no field-level errors (route only ever returns one message).

**Register (default form):**
- Username field (3–30 chars), password field (6+ chars), submit
  ("Register" or equivalent).
- Error slot above the fields when `error` is set — messages are
  route-driven ("Username and password are required.", "Username must be
  at least 3 characters.", "Username already taken.").

**Register — success (takeover, not a toast):**
- When `success` is set, the entire form block in the form panel is
  replaced by a dedicated pending-approval state: the route's exact
  message ("Account created — an admin will approve it shortly."), plus a
  link back to `/login`.
- This must read as a distinct, deliberate state — comparable visual
  weight to the form it replaced, not a small inline confirmation. The
  content panel stays as-is; only the form panel's content changes.
- No toggle needed in this state (there's nothing to switch to — the
  account isn't usable yet); the "back to login" link is the only action.

---

## 7. Responsive — mobile is genuinely different here, not just reflow

Below the split-screen breakpoint, the content panel does **not** just
stack full-height above the form (that would push the form below a full
screen of static copy on a page whose entire job is "get to the form
fast"). Instead:

- **Content panel compresses to a thin band**: brand mark + headline only.
  The body sentence and three points are **dropped** on mobile, not
  wrapped or scrolled to.
- **Form panel** (toggle + active form + error/success state) follows
  directly below, full width.
- No horizontal overflow, no truncated labels, at 390px.

This is a deliberate content-level difference (drop two of four content
blocks), not a purely visual reflow — recorded per the mobile
non-negotiable.

---

## 8. Accessibility

- Toggle is real anchor markup with `aria-current="page"` on the active
  route — keyboard and screen-reader equivalent to any other nav link, no
  hover-only or JS-only interaction.
- Brand mark is a real link (`<a href="/">`), not a div with a click
  handler.
- Standard form labeling (`<label for>`), visible focus states, and
  `prefers-reduced-motion` respect follow `DESIGN.md`'s existing baseline —
  no page-specific exception.

---

## 9. Backend / route changes

**None.** `error`/`success` template variables are unchanged. No new
fields, no confirm-password, no change to the env-credential path.

---

## 10. Implementation note (structural, not visual)

Both templates render the same shell shape (brand mark + content panel +
toggle + form panel). Factoring the content panel + toggle markup into a
small shared partial under `templates/auth/` (e.g.
`_auth_shell.html`) so the two pages can't drift is reasonable — as with
the shared War Detail unit, this is a "reuse one source" call, not a new
site-wide component. Exact file split is an implementation detail, not a
gate.

---

## 11. Open questions for impeccable

Deliberately unresolved — look decisions:

1. Split ratio (content panel vs form panel width) at desktop, and where
   the layout collapses to the mobile arrangement.
2. Brand mark treatment — wordmark only, or paired with a mark/icon; how
   it differs (if at all) from the sitewide nav's crest.
3. Content panel background/atmosphere — flat surface, subtle texture, a
   static (or live, reduced-motion-respecting) visual echo of the
   "thermal-scope" identity. Full color/gradient use stays within
   `DESIGN.md`'s existing rules (no gradient text, no shadows-as-elevation,
   gradients confined to brand marks).
4. How the three content-panel points are presented (plain list, icon +
   text, mono-figure treatment) — component choice is open, reuse an
   existing `DESIGN.md` vocabulary (e.g. Compact Row) rather than inventing
   a new list style if one fits.
5. Toggle visual treatment — segmented control, underline tabs, pill pair;
   how the active/inactive states read.
6. Error state styling — inline banner treatment already exists in
   `DESIGN.md`'s semantic colors (Raid Red family); confirm/adapt.
7. Register success-state visual weight and treatment — how it
   communicates "this matters, you're not done yet" without a toast.
8. Whether the form panel gets any atmosphere of its own or stays fully
   neutral against the content panel's identity.

---

## 12. Validation (before sign-off)

Playwright screenshots at **390×844**, **768×1024**, **1200×800** of:
- `/login` — default state, and the error state (bad credentials).
- `/register` — default state, an error state (e.g. taken username), and
  the success takeover state.

Check: split-screen renders correctly at desktop/tablet, mobile drops to
the compressed content band (brand + headline only, no body/points), no
horizontal overflow at 390px, toggle correctly reflects active route via
`aria-current`, register success state visually replaces the form without
touching the content panel. Run `/impeccable critique` on both built pages.
Show all screenshots + critique summary at the final gate.
